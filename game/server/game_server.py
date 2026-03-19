"""Main multiplayer server loop.

Responsibilities:
- track connected players
- update mimic state + new monsters (Siren, Weeping Angel, Hollow)
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
    LOOT_PICKUP_RADIUS,
    LOOT_SAMPLE_MAX_VALUE,
    LOOT_SAMPLE_MIN_VALUE,
    SERVER_HOST,
    SERVER_PORT,
    TICK_RATE,
)
from entities.hollow import Hollow
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


# Damage constants (per-hit or per-second base values, before difficulty scaling)
_SIREN_DPS = 12
_SIREN_DAMAGE_RADIUS = 150.0
_ANGEL_HIT_DAMAGE = 35
_ANGEL_HIT_RADIUS = 80.0
_ANGEL_HIT_COOLDOWN = 2.0
_HOLLOW_DPS = 8
_HOLLOW_DAMAGE_RADIUS = 100.0
_MIMIC_HIT_DAMAGE = 20
_DAMAGE_INVINCIBILITY = 2.0
_RESPAWN_DELAY = 10.0
_MIMIC_SPAWN_THRESHOLD = 180.0
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
        self._angel_hit_cooldown: float = 0.0  # global angel attack cooldown

        spawns = self.world.enemy_spawn_points
        self.siren  = Siren(x=float(spawns["siren"][0]),  y=float(spawns["siren"][1]))
        self.angel  = WeepingAngel(x=float(spawns["weeping_angel"][0]), y=float(spawns["weeping_angel"][1]))
        self.hollow = Hollow(x=float(spawns["hollow"][0]), y=float(spawns["hollow"][1]))

        self.sanity = SanitySystem()
        self.quota  = QuotaSystem()

        self.facing_map: dict[str, bool] = {}   # player_id → facing_right

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

    def _spawn_loot_items(self) -> None:
        self._loot_items.clear()
        loot_min = self._loot_min
        loot_max = self._loot_max
        for spawn_x, spawn_y in getattr(self.world, "loot_spawn_points", []):
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
        print(f"[MAP] {len(self._loot_items)} loot items spawned (value {loot_min}-{loot_max})")

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
            self._angel_hit_cooldown = 0.0
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
                    self._respawn_timers[player.player_id] = _RESPAWN_DELAY
                continue
            if self._invincibility_timers.get(player.player_id, 0.0) > 0:
                continue

            px, py = self._player_center(player)
            took_damage = self._apply_damage_to_player(player, px, py, dt)

            if took_damage:
                self._invincibility_timers[player.player_id] = _DAMAGE_INVINCIBILITY

    def _tick_cooldowns(self, dt: float) -> None:
        self._angel_hit_cooldown = max(0.0, self._angel_hit_cooldown - dt)
        for pid in list(self._invincibility_timers):
            self._invincibility_timers[pid] = max(0.0, self._invincibility_timers[pid] - dt)
            if self._invincibility_timers[pid] <= 0:
                del self._invincibility_timers[pid]

    def _apply_damage_to_player(self, player: Player, px: float, py: float, dt: float) -> bool:
        took_damage = False

        # Siren: DPS within radius (scaled by difficulty)
        sx = self.siren.x + self.siren.width * 0.5
        sy = self.siren.y + self.siren.height * 0.5
        if math.hypot(px - sx, py - sy) < _SIREN_DAMAGE_RADIUS:
            dmg = max(1, int(_SIREN_DPS * dt * self._dmg_mult))
            player.take_damage(dmg)
            took_damage = True

        # Weeping Angel: instant hit on touch, with cooldown + lunge freeze
        if not self.angel.frozen and self._angel_hit_cooldown <= 0:
            ax = self.angel.x + self.angel.width * 0.5
            ay = self.angel.y + self.angel.height * 0.5
            if math.hypot(px - ax, py - ay) < _ANGEL_HIT_RADIUS:
                dmg = max(1, int(_ANGEL_HIT_DAMAGE * self._dmg_mult))
                player.take_damage(dmg)
                self._angel_hit_cooldown = _ANGEL_HIT_COOLDOWN
                self.angel.on_touched_player()
                took_damage = True

        # Hollow: DPS within radius (scaled by difficulty)
        if math.hypot(px - self.hollow.x, py - self.hollow.y) < _HOLLOW_DAMAGE_RADIUS:
            dmg = max(1, int(_HOLLOW_DPS * dt * self._dmg_mult))
            player.take_damage(dmg)
            took_damage = True

        # Mimics: instant damage on touch
        for mimic in self._mimics:
            if not getattr(mimic, '_active', False):
                continue
            if not mimic.touched_target_this_tick:
                continue
            if player.player_id != mimic.target_player_id:
                continue
            dmg = max(1, int(_MIMIC_HIT_DAMAGE * self._dmg_mult))
            player.take_damage(dmg)
            took_damage = True

        return took_damage

    def _trigger_lights_out(self) -> None:
        """Spawn one mimic per player and broadcast LIGHTS_OUT event."""
        print(f"[SERVER] LIGHTS OUT — spawning mimics for {len(self.players)} player(s)")
        self._mimics_active = True
        self._mimics.clear()
        for player_id, player in self.players.items():
            mimic = Mimic(
                enemy_id=f"mimic-{self._mimic_next_id}",
                x=player.x,
                y=player.y,
            )
            self._mimic_next_id += 1
            mimic.activate(
                target_player_id=player_id,
                skin=player.skin,
                name=player.name,
                start_x=player.x,
                start_y=player.y,
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
            self.hollow.to_dict(),
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
                    elif msg_type == "START_GAME":
                        self._handle_start_game(conn)

            if now - last_tick >= target_dt:
                # Monsters active during PLAYING and QUOTA_MET
                if self.round_state in ("PLAYING", "QUOTA_MET"):
                    # Mimic spawn — triggers at 3 minutes remaining
                    if not self._mimics_active and int(self._game_timer) % 30 == 0 and int(self._game_timer) != int(self._game_timer + target_dt):
                        print(f"[MIMIC] Timer={self._game_timer:.1f}, threshold=180, active={self._mimics_active}")
                    if not self._mimics_active and self._game_timer <= _MIMIC_SPAWN_THRESHOLD:
                        self._trigger_lights_out()

                    # Update active mimics
                    for mimic in self._mimics:
                        stolen = mimic.update(dt=target_dt, world=self.world, players=self.players, loot_items=self._loot_items)
                        for loot_id in stolen:
                            for loot in self._loot_items:
                                if loot.loot_id == loot_id and not loot.collected:
                                    loot.collected = True

                    all_monsters = [self.siren, self.angel, self.hollow]

                    self.siren.update(dt=target_dt, world=self.world, players=self.players)
                    self.angel.update(dt=target_dt, world=self.world, players=self.players)

                    if self._throw_window > 0:
                        self._throw_window -= 1
                        if self._throw_window == 0 and self._pending_throws:
                            if not self.hollow.group_redirect(self._pending_throws):
                                lx, ly = self._pending_throws[-1]
                                self.hollow.redirect(lx, ly)
                            self._pending_throws.clear()

                    self.hollow.update(
                        dt=target_dt,
                        players=self.players,
                        floor_y=self.world.floor_y(),
                        world_min_x=10,
                        world_max_x=self.world.world_width - 40,
                        sanity_values=self.sanity.to_dict(),
                    )

                    self._update_loot_entities(target_dt)

                    # Loot respawn — when all collected, countdown based on difficulty
                    all_collected = all(loot.collected for loot in self._loot_items) if self._loot_items else False
                    if all_collected:
                        self._loot_respawn_timer += target_dt
                        respawn_time = 10.0 if self._difficulty == "EXPERT" else 15.0
                        if self._loot_respawn_timer >= respawn_time:
                            self._loot_batch_count = getattr(self, '_loot_batch_count', 0) + 1
                            total_value = sum(random.randint(self._loot_min, self._loot_max) for _ in self.world.loot_spawn_points)
                            print(f"[LOOT] Batch {self._loot_batch_count} spawned, {len(self.world.loot_spawn_points)} items, total possible value: {total_value}")
                            self._spawn_loot_items()
                    else:
                        self._loot_respawn_timer = 0.0

                    # Damage system
                    self._apply_monster_damage(target_dt)
                    self._update_respawns(target_dt)

                    self.sanity.update(self.players, all_monsters, dt=target_dt, mimics_active=self._mimics_active)
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
                        if p.alive and p.y <= 32:
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
