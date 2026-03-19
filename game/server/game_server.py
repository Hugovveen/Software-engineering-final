"""Main multiplayer server loop.

Responsibilities:
- track connected players
- update mimic state + monsters (Siren, Weeping Angel)
- manage sanity, day/night, and sample quota
- receive movement commands
- broadcast game state at a fixed tick rate
"""

from __future__ import annotations

import math
import random
import socket
import time
import uuid

from config import (
    ANGEL_HIT_COOLDOWN,
    ANGEL_HIT_DAMAGE,
    ANGEL_HIT_RADIUS,
    DAMAGE_INVINCIBILITY,
    LOOT_PICKUP_RADIUS,
    LOOT_SAMPLE_MAX_VALUE,
    LOOT_SAMPLE_MIN_VALUE,
    MIMIC_HIT_DAMAGE,
    MIMIC_SPAWN_THRESHOLD,
    PLAYER_SPEED,
    RESPAWN_DELAY,
    SERVER_HOST,
    SERVER_PORT,
    SIREN_DAMAGE_RADIUS,
    SIREN_DPS,
    TICK_RATE,
)
from entities.loot import Loot
from entities.mimic import Mimic
from entities.player import Player
from entities.siren import Siren
from entities.weeping_angel import WeepingAngel
from map.facility_map import FacilityMap
from server.server_network import ServerNetwork
from systems.behavior_tracker import BehaviorTracker
from systems.movement_system import apply_player_input
from systems.quota import QuotaSystem
from systems.sanity import SanitySystem


_THROW_WINDOW_FRAMES = 30


class GameServer:
    """Simple authoritative server for the prototype game world."""

    def __init__(self, host: str | None = None, port: int | None = None) -> None:
        self.host = host or SERVER_HOST
        self.port = port or SERVER_PORT
        self.network = ServerNetwork(self.host, self.port)

        self.players: dict[str, Player] = {}
        self.connections: dict[socket.socket, str] = {}
        self.buffers: dict[socket.socket, str] = {}

        self.world            = FacilityMap()
        self.behavior_tracker = BehaviorTracker()

        # Mimic system — delayed spawn after lights-out
        self._mimics: list[Mimic] = []
        self._mimics_active: bool = False
        self._mimic_timer: float = 0.0
        self._mimic_next_id: int = 1
        self._game_timer: float = 300.0  # 5-minute countdown
        self._respawn_timers: dict[str, float] = {}  # player_id → seconds remaining
        self._invincibility_timers: dict[str, float] = {}  # player_id → seconds remaining
        self._angel_hit_cooldown: float = 0.0  # server-side angel attack cooldown

        spawns = self.world.enemy_spawn_points
        self.siren  = Siren(x=float(spawns["siren"][0]),  y=float(spawns["siren"][1]))
        self.angel  = WeepingAngel(x=float(spawns["weeping_angel"][0]), y=float(spawns["weeping_angel"][1]))
        self.sanity = SanitySystem()
        self.quota  = QuotaSystem()

        self.facing_map: dict[str, bool] = {}   # player_id → facing_right
        self._siren_near_timer: dict[str, float] = {}  # player_id → seconds near siren with flashlight off
        self._siren_force_cooldown: dict[str, float] = {}  # player_id → seconds before siren can force again

        self._pending_throws: list[tuple[float, float]] = []
        self._throw_window = 0   # frame counter for simultaneous throw window
        self._events: list[dict] = []
        self.round_state: str = "LOBBY"
        self.taken_skins: set[str] = set()

        # Difficulty settings (set by first player to join)
        self._difficulty: str = "RESEARCHER"
        self._difficulty_presets = {
            "STUDENT":    {"quota": 150, "dmg_mult": 0.5, "time": 420, "loot_min": 12, "loot_max": 20},
            "RESEARCHER": {"quota": 300, "dmg_mult": 1.0, "time": 300, "loot_min": 15, "loot_max": 25},
            "EXPERT":     {"quota": 500, "dmg_mult": 2.0, "time": 240, "loot_min": 10, "loot_max": 18},
        }
        self._dmg_mult: float = 1.0
        self._loot_min: int = LOOT_SAMPLE_MIN_VALUE
        self._loot_max: int = LOOT_SAMPLE_MAX_VALUE

        self._loot_items: list[Loot] = []
        self._next_loot_id = 1
        self._loot_respawn_timer: float = 0.0  # countdown to next batch respawn
        self._spawn_loot_items()

    def _spawn_loot_items(self, count: int | None = None) -> None:
        loot_min = self._loot_min
        loot_max = self._loot_max
        spawn_points = list(getattr(self.world, "loot_spawn_points", []))

        if count is None:
            # Full respawn: clear everything and spawn at all points
            self._loot_items.clear()
            for spawn_x, spawn_y in spawn_points:
                self._loot_items.append(
                    Loot(
                        loot_id=f"loot-{self._next_loot_id}",
                        x=float(spawn_x),
                        y=float(spawn_y),
                        value=int(random.randint(loot_min, loot_max)),
                    )
                )
                self._next_loot_id += 1
            print(f"[MAP] {len(self._loot_items)} loot items spawned (value {loot_min}-{loot_max})")
        else:
            # Partial respawn: append new items at random spawn points
            selected = random.sample(spawn_points, min(count, len(spawn_points)))
            for spawn_x, spawn_y in selected:
                self._loot_items.append(
                    Loot(
                        loot_id=f"loot-{self._next_loot_id}",
                        x=float(spawn_x),
                        y=float(spawn_y),
                        value=int(random.randint(loot_min, loot_max)),
                    )
                )
                self._next_loot_id += 1

        self._loot_respawn_timer = 0.0

    def _update_loot_entities(self, dt: float) -> None:
        floor_y = float(self.world.floor_y())
        world_width = float(getattr(self.world, "world_width", 1536.0))
        world_height = float(getattr(self.world, "world_height", 1024.0))
        platforms = tuple(getattr(self.world, "platforms", ()))

        for loot in self._loot_items:
            loot.update(
                dt=dt,
                floor_y=floor_y,
                world_width=world_width,
                world_height=world_height,
                platforms=platforms,
            )

    def _emit_event(self, event: dict) -> None:
        self._events.append(event)

    def _player_center(self, player: Player) -> tuple[float, float]:
        return float(player.x) + float(player.width) * 0.5, float(player.y) + float(player.height) * 0.5

    def _is_player_in_extraction_zone(self, player: Player) -> bool:
        zone = tuple(getattr(self.world, "extraction_zone", (0, 0, 0, 0)))
        if len(zone) != 4:
            return False
        zone_x, zone_y, zone_w, zone_h = (float(zone[0]), float(zone[1]), float(zone[2]), float(zone[3]))

        player_left = float(player.x)
        player_top = float(player.y)
        player_right = player_left + float(player.width)
        player_bottom = player_top + float(player.height)

        zone_left = zone_x
        zone_top = zone_y
        zone_right = zone_left + zone_w
        zone_bottom = zone_top + zone_h

        return not (
            player_right <= zone_left
            or player_left >= zone_right
            or player_bottom <= zone_top
            or player_top >= zone_bottom
        )

    def _try_pickup_loot(self, player: Player) -> bool:
        max_carry = 5 if len(self.players) == 1 else 3
        if player.carried_loot_count >= max_carry:
            return False
        center_x, center_y = self._player_center(player)
        nearest_loot: Loot | None = None
        nearest_distance = float("inf")

        for loot in self._loot_items:
            if loot.collected:
                continue

            loot_x, loot_y = loot.center()
            dx = loot_x - center_x
            dy = loot_y - center_y
            distance = math.hypot(dx, dy)
            if distance > LOOT_PICKUP_RADIUS:
                continue
            if distance < nearest_distance:
                nearest_distance = distance
                nearest_loot = loot

        if nearest_loot is None:
            return False

        nearest_loot.collected = True

        value = int(nearest_loot.value)
        player.carried_loot_count += 1
        player.carried_loot_value += value

        self._emit_event(
            {
                "type": "LOOT_PICKED",
                "player_id": player.player_id,
                "value": value,
                "loot_id": nearest_loot.loot_id,
            }
        )
        return True

    def _try_deposit_loot(self, player: Player) -> bool:
        if player.carried_loot_value <= 0:
            return False
        if not self._is_player_in_extraction_zone(player):
            return False

        deposited_value = int(player.carried_loot_value)
        deposited_count = int(player.carried_loot_count)
        self.quota.add_value(deposited_value)

        player.carried_loot_value = 0
        player.carried_loot_count = 0

        self._emit_event(
            {
                "type": "LOOT_DEPOSITED",
                "player_id": player.player_id,
                "value": deposited_value,
                "count": deposited_count,
            }
        )
        return True

    # ------------------------------------------------------------------
    # Connection handlers (Hugo's code, unchanged)
    # ------------------------------------------------------------------

    def _handle_join(self, conn: socket.socket, message: dict) -> None:
        player_id = str(uuid.uuid4())[:8]
        name      = str(message.get("name", "Player"))

        # Skin assignment — first player gets their choice, second gets the other
        all_skins = {"researcher", "student"}
        requested_skin = str(message.get("skin", "researcher"))
        if requested_skin not in all_skins:
            requested_skin = "researcher"
        if requested_skin in self.taken_skins:
            remaining = all_skins - self.taken_skins
            requested_skin = next(iter(remaining)) if remaining else "researcher"
        self.taken_skins.add(requested_skin)

        player = Player(player_id=player_id, name=name, skin=requested_skin)
        self.players[player_id]   = player
        self.connections[conn]    = player_id
        self.facing_map[player_id] = True

        self.sanity.register(player_id)

        # First player sets difficulty
        if len(self.players) == 1:
            req_diff = str(message.get("difficulty", "RESEARCHER"))
            if req_diff in self._difficulty_presets:
                self._difficulty = req_diff
            preset = self._difficulty_presets[self._difficulty]
            self._dmg_mult = preset["dmg_mult"]

        ServerNetwork.send(
            conn,
            {
                "type": "PLAYER_JOIN",
                "id": player_id,
                "name": name,
                "skin": requested_skin,
                "taken_skins": list(self.taken_skins),
                "difficulty": self._difficulty,
            },
        )

    def _handle_move(self, conn: socket.socket, message: dict, dt: float) -> None:
        player_id = self.connections.get(conn)
        if not player_id or player_id not in self.players:
            return
        player = self.players[player_id]
        if not player.alive:
            return

        input_state = {
            "move_x":    message.get("move_x", 0),
            "climb":     message.get("climb", 0),
            "on_ladder": message.get("on_ladder", False),
            "jump":      message.get("jump", False),
            "sprint":    message.get("sprint", False),
        }
        # Include escape ladder when quota met so players can climb it
        ladders = self.world.ladders
        if self.round_state == "QUOTA_MET":
            escape = getattr(self.world, "escape_ladder", None)
            if escape:
                ladders = list(ladders) + [escape]

        apply_player_input(
            player,
            input_state,
            dt,
            floor_y=self.world.floor_y(),
            world_width=float(self.world.world_width),
            ladders=ladders,
            platforms=self.world.platforms,
            world_height=float(getattr(self.world, "world_height", 0.0)),
        )
        self.behavior_tracker.record(player_id, player.x, player.y)

        # Update facing direction from move_x
        if input_state["move_x"] > 0:
            self.facing_map[player_id] = True
        elif input_state["move_x"] < 0:
            self.facing_map[player_id] = False

        # Sync flashlight state
        if "flashlight_on" in message:
            player.flashlight_on = bool(message["flashlight_on"])

    def _handle_item_throw(self, conn: socket.socket, message: dict) -> None:
        """Process a thrown item message from a client.

        Args:
            conn:    Client socket.
            message: Message dict with 'land_x' and 'land_y' keys.
        """
        land_x = float(message.get("land_x", 0))
        land_y = float(message.get("land_y", 0))
        self._pending_throws.append((land_x, land_y))
        self._throw_window = _THROW_WINDOW_FRAMES

    def _handle_sell_samples(self, conn: socket.socket, message: dict) -> None:
        """Sell samples when a player reaches the dropzone.

        Args:
            conn:    Client socket.
            message: Message dict with 'count' key.
        """
        count = int(message.get("count", 0))
        total = self.quota.sell_samples(count)
        ServerNetwork.send(conn, {"type": "SAMPLE_SOLD", "total": total,
                                  "collected": self.quota.collected,
                                  "quota": self.quota.quota})

    def _handle_start_game(self, conn: socket.socket) -> None:
        if self.round_state != "LOBBY":
            return
        if len(self.players) < 1:
            return
        self.round_state = "PLAYING"
        preset = self._difficulty_presets[self._difficulty]
        self._game_timer = float(preset["time"])
        self._dmg_mult = preset["dmg_mult"]
        self._loot_min = preset["loot_min"]
        self._loot_max = preset["loot_max"]
        self._mimic_timer = 0.0
        self._mimics_active = False
        self._mimics.clear()
        self._respawn_timers.clear()
        self._invincibility_timers.clear()
        self._siren_near_timer.clear()
        self._siren_force_cooldown.clear()
        self._angel_hit_cooldown = 0.0
        # Reset quota for new round with difficulty target
        self.quota = QuotaSystem(target_quota=preset["quota"])
        # Respawn loot
        self._next_loot_id = 1
        self._loot_batch_count = 0
        self._spawn_loot_items()
        # Reset player health/loot
        for player in self.players.values():
            player.health = 100
            player.alive = True
            player.x = 64.0
            player.y = 848.0
            player.vx = 0.0
            player.vy = 0.0
            player.carried_loot_count = 0
            player.carried_loot_value = 0
        self._emit_event({
            "type": "ROUND_STATE_CHANGED",
            "state": "PLAYING",
            "round_number": 1,
            "reason": "host started",
        })

    def _handle_interact(self, conn: socket.socket) -> None:
        player_id = self.connections.get(conn)
        if not player_id:
            return
        player = self.players.get(player_id)
        if player is None:
            return

        if self._try_deposit_loot(player):
            return
        self._try_pickup_loot(player)

    def _cleanup_connection(self, conn: socket.socket) -> None:
        player_id = self.connections.pop(conn, None)
        self.buffers.pop(conn, None)
        if player_id is not None:
            self.facing_map.pop(player_id, None)
            self._respawn_timers.pop(player_id, None)
            player = self.players.get(player_id)
            if player is not None:
                self.taken_skins.discard(player.skin)
        if player_id:
            self.sanity.remove(player_id)
            self.players.pop(player_id, None)
        try:
            conn.close()
        except OSError:
            pass

        # Reset server state when all clients disconnect
        if not self.players:
            self.round_state = "LOBBY"
            self._mimic_timer = 0.0
            self._mimics_active = False
            self._mimics.clear()
            self._game_timer = 300.0
            self._respawn_timers.clear()
            self._invincibility_timers.clear()
            self.taken_skins.clear()
            self._events.clear()
            self._next_loot_id = 1
            self._spawn_loot_items()
            self.quota = QuotaSystem()

    # ------------------------------------------------------------------
    # Game state broadcast
    # ------------------------------------------------------------------

    def _update_respawns(self, dt: float) -> None:
        """Tick down respawn timers and revive players at extraction zone."""
        finished = []
        for pid, remaining in self._respawn_timers.items():
            remaining -= dt
            if remaining <= 0:
                player = self.players.get(pid)
                if player is not None:
                    player.health = 100
                    player.alive = True
                    player.x = 64.0
                    player.y = 848.0
                    player.vx = 0.0
                    player.vy = 0.0
                    print(f"[SERVER] RESPAWNING {pid} at extraction zone (64, 848)")
                finished.append(pid)
            else:
                self._respawn_timers[pid] = remaining
        for pid in finished:
            self._respawn_timers.pop(pid, None)

    def _apply_monster_damage(self, dt: float) -> None:
        """Apply damage from all monsters to nearby players."""
        self._tick_cooldowns(dt)

        for player in self.players.values():
            if not player.alive:
                if player.player_id not in self._respawn_timers:
                    if len(self.players) == 1:
                        print(f"[DEATH] {player.player_id} died. Solo=True — instant game over")
                        self.round_state = "GAME_OVER"
                        self._emit_event({
                            "type": "ROUND_STATE_CHANGED",
                            "state": "GAME_OVER",
                            "round_number": 1,
                            "reason": "solo_death",
                        })
                    else:
                        print(f"[DEATH] {player.player_id} died. Solo=False — respawn in {RESPAWN_DELAY}s")
                        self._respawn_timers[player.player_id] = RESPAWN_DELAY
                continue
            if self._invincibility_timers.get(player.player_id, 0.0) > 0:
                continue

            px, py = self._player_center(player)
            took_damage = self._apply_damage_to_player(player, px, py, dt)

            if took_damage:
                self._invincibility_timers[player.player_id] = DAMAGE_INVINCIBILITY

    def _tick_cooldowns(self, dt: float) -> None:
        for pid in list(self._invincibility_timers):
            self._invincibility_timers[pid] = max(0.0, self._invincibility_timers[pid] - dt)
            if self._invincibility_timers[pid] <= 0:
                del self._invincibility_timers[pid]

    def _apply_damage_to_player(self, player: Player, px: float, py: float, dt: float) -> bool:
        took_damage = False

        # Siren: DPS within radius (scaled by difficulty)
        sx = self.siren.x + self.siren.width * 0.5
        sy = self.siren.y + self.siren.height * 0.5
        if math.hypot(px - sx, py - sy) < SIREN_DAMAGE_RADIUS:
            dmg = max(1, int(SIREN_DPS * dt * self._dmg_mult))
            player.take_damage(dmg)
            took_damage = True

        # Weeping Angel: simple proximity damage when not frozen
        ax = self.angel.x + self.angel.width * 0.5
        ay = self.angel.y + self.angel.height * 0.5
        angel_dist = math.hypot(px - ax, py - ay)

        # Debug: print when any player is within 200px
        if angel_dist < 200.0:
            print(f"[ANGEL] checking damage: dist={angel_dist:.1f}, frozen={self.angel.frozen}, cooldown={self._angel_hit_cooldown:.1f}")

        if not self.angel.frozen and angel_dist < ANGEL_HIT_RADIUS and self._angel_hit_cooldown <= 0:
            dmg = max(1, int(ANGEL_HIT_DAMAGE * self._dmg_mult))
            player.take_damage(dmg)
            self._angel_hit_cooldown = ANGEL_HIT_COOLDOWN
            self.angel.attacking = True  # visual feedback for renderer
            print(f"[ANGEL] Hit {player.player_id} for {dmg} damage (dist={angel_dist:.1f})")
            took_damage = True

        return took_damage

    def _apply_siren_pull(self, dt: float) -> None:
        """Apply gentle pull toward Siren for players within 200px with sanity < 50."""
        _PULL_RADIUS = 200.0
        _PULL_STRENGTH = 0.8
        _MAX_PULL_FRAC = 0.30  # never exceed 30% of walk speed
        max_pull_speed = PLAYER_SPEED * _MAX_PULL_FRAC

        sx = self.siren.x + self.siren.width * 0.5
        sy = self.siren.y + self.siren.height * 0.5

        for pid, player in self.players.items():
            if not player.alive:
                continue
            px = float(player.x) + float(player.width) * 0.5
            py = float(player.y) + float(player.height) * 0.5
            dist = math.hypot(px - sx, py - sy)
            if dist > _PULL_RADIUS:
                continue
            sanity = self.sanity.get(pid)
            if sanity >= 50:
                continue
            dx = sx - px
            direction = 1.0 if dx > 0 else -1.0 if dx < 0 else 0.0
            pull = min(_PULL_STRENGTH, max_pull_speed) * direction * dt
            player.x += pull
            # Clamp to world
            player.x = max(0.0, min(float(self.world.world_width) - float(player.width), player.x))
            if not hasattr(self, '_siren_pull_log') or (time.perf_counter() - self._siren_pull_log) >= 2.0:
                self._siren_pull_log = time.perf_counter()
                print(f"[SIREN] Charm pull applied to {pid}: sanity={sanity:.1f}, dist={dist:.1f}")

    def _find_distant_spawn(self, player: Player) -> tuple[float, float]:
        """Find a spawn point on a platform edge at least 400px from the player."""
        platforms = getattr(self.world, "platforms", [])
        candidates: list[tuple[float, float]] = []
        for px, py, pw, ph in platforms:
            # Left edge and right edge of each platform
            candidates.append((float(px) + 10, float(py) - 48))
            candidates.append((float(px + pw) - 40, float(py) - 48))
        # Filter to those at least 400px from player
        far = [(cx, cy) for cx, cy in candidates
               if math.hypot(cx - player.x, cy - player.y) >= 400]
        if far:
            return random.choice(far)
        # Fallback: pick the farthest candidate
        if candidates:
            candidates.sort(key=lambda c: math.hypot(c[0] - player.x, c[1] - player.y), reverse=True)
            return candidates[0]
        # Ultimate fallback
        return (float(self.world.world_width) - 100, float(self.world.floor_y()) - 48)

    def _trigger_lights_out(self) -> None:
        """Spawn one mimic per player and broadcast LIGHTS_OUT event."""
        solo = len(self.players) == 1
        print(f"[SERVER] LIGHTS OUT — spawning mimics for {len(self.players)} player(s), solo={solo}")
        self._mimics_active = True
        self._mimics.clear()
        for player_id, player in self.players.items():
            if solo:
                mimic_skin = "student" if player.skin == "researcher" else "researcher"
                mimic_name = "???"
            else:
                mimic_skin = player.skin
                mimic_name = player.name
            # Spawn mimic at least 400px from the player on a platform edge
            spawn_x, spawn_y = self._find_distant_spawn(player)
            mimic = Mimic(
                enemy_id=f"mimic-{self._mimic_next_id}",
                x=spawn_x,
                y=spawn_y,
            )
            self._mimic_next_id += 1
            mimic.activate(
                target_player_id=player_id,
                skin=mimic_skin,
                name=mimic_name,
                start_x=spawn_x,
                start_y=spawn_y,
                solo=solo,
            )
            self._mimics.append(mimic)
        self._emit_event({
            "type": "LIGHTS_OUT",
        })

    def _broadcast_game_state(self) -> None:
        active = self.round_state in ("PLAYING", "QUOTA_MET")
        all_monsters = [
            self.siren.to_dict(),
            self.angel.to_dict(),
        ] if active else []

        # Include mimic copies in the players list so they render identically
        player_dicts = []
        for p in self.players.values():
            pd = p.to_dict()
            pd["respawn_timer"] = self._respawn_timers.get(p.player_id, 0.0)
            player_dicts.append(pd)
        if active and self._mimics_active:
            for mimic in self._mimics:
                player_dicts.append(mimic.to_player_dict())

        active_loot = [loot.to_dict() for loot in self._loot_items if not loot.collected] if active else []
        state_message = {
            "type": "GAME_STATE",
            "players": player_dicts,
            "mimic":   {},
            "map": {
                "platforms": self.world.platforms,
                "ladders":   self.world.ladders,
                "extraction_zone": getattr(self.world, "extraction_zone", (0, 0, 0, 0)),
                "escape_ladder": getattr(self.world, "escape_ladder", None),
            },
            "round": {"state": self.round_state, "number": 1, "time_remaining": self._game_timer, "difficulty": self._difficulty},
            # Monster and system fields
            "monsters":   all_monsters,
            "sanity":     self.sanity.to_dict(),
            "quota":      self.quota.to_dict(),
            "loot":       active_loot,
            "loot_respawn_timer": self._loot_respawn_timer if all(loot.collected for loot in self._loot_items) else 0.0,
            "loot_respawn_max": 10.0 if self._difficulty == "EXPERT" else 15.0,
            "events":     list(self._events),
        }
        self._events.clear()

        dead: list[socket.socket] = []
        for conn in list(self.connections.keys()):
            try:
                ServerNetwork.send(conn, state_message)
            except OSError:
                dead.append(conn)
        for conn in dead:
            self._cleanup_connection(conn)

    # ------------------------------------------------------------------
    # Main server loop
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Run the server loop until interrupted."""
        print(f"[SERVER] Listening on {self.host}:{self.port}")
        target_dt = 1.0 / TICK_RATE
        last_tick  = time.perf_counter()

        while True:
            accepted = self.network.accept_client()
            if accepted:
                conn, addr = accepted
                print(f"[SERVER] Client connected: {addr}")
                self.buffers[conn] = ""

            now = time.perf_counter()
            dt  = max(0.0, now - last_tick)

            for conn in list(self.buffers.keys()):
                try:
                    messages, updated = ServerNetwork.receive_many(conn, self.buffers[conn])
                    self.buffers[conn] = updated
                except OSError:
                    self._cleanup_connection(conn)
                    continue

                for msg in messages:
                    msg_type = msg.get("type")
                    if msg_type == "PLAYER_JOIN":
                        self._handle_join(conn, msg)
                    elif msg_type == "PLAYER_MOVE":
                        self._handle_move(conn, msg, dt)
                    elif msg_type == "ITEM_THROW":
                        self._handle_item_throw(conn, msg)
                    elif msg_type == "PLAYER_INTERACT":
                        self._handle_interact(conn)
                    elif msg_type == "SELL_SAMPLES":
                        self._handle_sell_samples(conn, msg)
                    elif msg_type == "PLAYER_FLASHLIGHT":
                        pid = self.connections.get(conn)
                        if pid and pid in self.players:
                            self.players[pid].flashlight_on = bool(msg.get("on", True))
                    elif msg_type == "START_GAME":
                        self._handle_start_game(conn)

            if now - last_tick >= target_dt:
                # Monsters active during PLAYING and QUOTA_MET
                if self.round_state in ("PLAYING", "QUOTA_MET"):
                    # Mimic spawn — triggers at 3 minutes remaining
                    if not self._mimics_active and int(self._game_timer) % 30 == 0 and int(self._game_timer) != int(self._game_timer + target_dt):
                        print(f"[MIMIC] Timer={self._game_timer:.1f}, threshold=180, active={self._mimics_active}")
                    if not self._mimics_active and self._game_timer <= MIMIC_SPAWN_THRESHOLD:
                        self._trigger_lights_out()

                    # Update active mimics
                    for mimic in self._mimics:
                        stolen = mimic.update(dt=target_dt, world=self.world, players=self.players, loot_items=self._loot_items)
                        for loot_id in stolen:
                            for loot in self._loot_items:
                                if loot.loot_id == loot_id and not loot.collected:
                                    loot.collected = True

                    all_monsters = [self.siren, self.angel]

                    self.siren.update(dt=target_dt, world=self.world, players=self.players)
                    self.angel.update(dt=target_dt, world=self.world, players=self.players, facing_map=self.facing_map)

                    # Tick siren force cooldowns
                    for pid in list(self._siren_force_cooldown):
                        self._siren_force_cooldown[pid] -= target_dt
                        if self._siren_force_cooldown[pid] <= 0:
                            del self._siren_force_cooldown[pid]

                    # Siren forces flashlight on — if player lingers nearby with flashlight off
                    sx = self.siren.x + self.siren.width * 0.5
                    sy = self.siren.y + self.siren.height * 0.5
                    for pid, player in self.players.items():
                        if not player.alive:
                            self._siren_near_timer.pop(pid, None)
                            continue
                        if not player.flashlight_on:
                            # Skip if force cooldown is active for this player
                            if self._siren_force_cooldown.get(pid, 0.0) > 0:
                                self._siren_near_timer.pop(pid, None)
                                continue
                            px = float(player.x) + float(player.width) * 0.5
                            py = float(player.y) + float(player.height) * 0.5
                            dist = math.hypot(px - sx, py - sy)
                            if dist <= 350.0:
                                self._siren_near_timer[pid] = self._siren_near_timer.get(pid, 0.0) + target_dt
                                if self._siren_near_timer[pid] >= 4.0:
                                    player.flashlight_on = True
                                    self._siren_near_timer[pid] = 0.0
                                    self._siren_force_cooldown[pid] = 15.0
                                    print(f"[SIREN] Forced flashlight ON for {pid} — 15s cooldown started")
                                    self._emit_event({
                                        "type": "SIREN_NOTICED",
                                        "player_id": pid,
                                    })
                            else:
                                self._siren_near_timer.pop(pid, None)
                        else:
                            self._siren_near_timer.pop(pid, None)

                    self._update_loot_entities(target_dt)

                    # Loot respawn — partial batches based on active count
                    active_count = sum(1 for loot in self._loot_items if not loot.collected)
                    if active_count >= 12:
                        self._loot_respawn_timer = 0.0
                    elif active_count < 6:
                        self._loot_respawn_timer += target_dt
                        respawn_time = 10.0 if self._difficulty == "EXPERT" else 15.0
                        if self._loot_respawn_timer >= respawn_time:
                            spawn_count = 12 - active_count
                            print(f"[LOOT] Active: {active_count}, spawning {spawn_count} new items")
                            self._loot_batch_count = getattr(self, '_loot_batch_count', 0) + 1
                            self._spawn_loot_items(count=spawn_count)
                    else:
                        self._loot_respawn_timer = 0.0

                    # Siren charm pull — gentle pull when close + low sanity
                    self._apply_siren_pull(target_dt)

                    # Tick angel hit cooldown and reset visual attack flag
                    if self._angel_hit_cooldown > 0:
                        self._angel_hit_cooldown = max(0.0, self._angel_hit_cooldown - target_dt)
                    else:
                        self.angel.attacking = False

                    # Damage system
                    self._apply_monster_damage(target_dt)
                    self._update_respawns(target_dt)

                    self.sanity.update(self.players, self.siren, self.angel, None, self._mimics, dt=target_dt)

                    # Sanity at zero → slow HP drain (2 HP/sec)
                    for pid, player in self.players.items():
                        if not player.alive:
                            continue
                        if self._invincibility_timers.get(pid, 0.0) > 0:
                            continue
                        if self.sanity.get(pid) <= 0:
                            dmg = 2 * target_dt
                            player.take_damage(dmg)
                            print(f"[SANITY] {pid} at 0 sanity — taking {dmg:.2f} HP damage")
                            if not player.alive:
                                self._invincibility_timers[pid] = DAMAGE_INVINCIBILITY

                    self.quota.tick()
                    self._game_timer -= target_dt
                    # Timer debug — print every 10 seconds
                    if int(self._game_timer) % 10 == 0 and int(self._game_timer) != int(self._game_timer + target_dt):
                        print(f"[TIMER] {self._game_timer:.1f}s remaining")
                if self.round_state == "PLAYING" and self.players:
                    if self.quota.is_quota_met():
                        self.round_state = "QUOTA_MET"
                        self._emit_event({
                            "type": "ROUND_STATE_CHANGED",
                            "state": "QUOTA_MET",
                            "round_number": 1,
                            "reason": "quota_reached",
                        })
                    elif self._game_timer <= 0:
                        self._game_timer = 0.0
                        print("[TIMER] EXPIRED — triggering GAME_OVER")
                        self.round_state = "GAME_OVER"
                        self._emit_event({
                            "type": "ROUND_STATE_CHANGED",
                            "state": "GAME_OVER",
                            "round_number": 1,
                            "reason": "time_expired",
                        })
                    elif self.quota.to_dict().get("game_over", False):
                        self.round_state = "GAME_OVER"
                    elif all(not p.alive for p in self.players.values()) and not self._respawn_timers:
                        self.round_state = "GAME_OVER"

                # Check for rooftop escape during QUOTA_MET
                if self.round_state == "QUOTA_MET" and self.players:
                    for p in self.players.values():
                        if p.y < 100:
                            print(f"[ESCAPE] Player {p.player_id} at y={p.y:.1f}, quota={self.quota.collected}/{self.quota.quota}, met={self.quota.collected >= self.quota.quota}")
                        if p.alive and p.y <= 150:
                            print(f"[ESCAPE] TRIGGERED — Player {p.player_id} reached y={p.y:.1f}")
                            self.round_state = "ENDING"
                            self._emit_event({
                                "type": "ROUND_STATE_CHANGED",
                                "state": "ENDING",
                                "round_number": 1,
                                "reason": "escape_reached",
                            })
                            break

                # Periodic server state log (every 5 seconds)
                if not hasattr(self, '_state_log_timer'):
                    self._state_log_timer = 0.0
                self._state_log_timer += target_dt
                if self._state_log_timer >= 5.0:
                    self._state_log_timer = 0.0
                    print(f"[SERVER] State: {self.round_state}, Players: {len(self.players)}, Quota: {self.quota.collected}/{self.quota.quota}, Timer: {self._game_timer:.0f}s")

                self._broadcast_game_state()
                last_tick = now

            time.sleep(0.001)
