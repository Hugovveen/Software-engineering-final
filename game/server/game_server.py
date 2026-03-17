"""Main multiplayer server loop.

Responsibilities:
- track connected players
- update mimic state + new monsters (Siren, Weeping Angel, Hollow)
- manage sanity, day/night, and sample quota
- receive movement commands
- broadcast game state at a fixed tick rate

CHANGES FROM HUGO'S VERSION (marked with # NEW):
  - Import new monster + system classes
  - Instantiate siren, angel, hollow, sanity_system, quota in __init__
  - Update all monsters and systems inside the tick block
  - Include them in _broadcast_game_state
  - Handle ITEM_THROW message type for Hollow redirection
  - Handle SELL_SAMPLES message type for quota
"""

from __future__ import annotations

import socket
import time
import uuid

from config import SERVER_HOST, SERVER_PORT, TICK_RATE
from entities.mimic import Mimic
from entities.player import Player
from map.facility_map import FacilityMap
from server.server_network import ServerNetwork
from systems.behavior_tracker import BehaviorTracker
from systems.movement_system import apply_player_input

# NEW — monster imports
from entities.siren import Siren
from entities.weeping_angel import WeepingAngel
from entities.hollow import Hollow

# NEW — system imports
from systems.sanity import SanitySystem
from systems.quota import QuotaSystem


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
        self.mimic            = Mimic()
        self.behavior_tracker = BehaviorTracker()

        # NEW — monsters
        self.siren  = Siren(x=900.0,  y=self.world.floor_y())
        self.angel  = WeepingAngel(x=1100.0, y=self.world.floor_y())
        self.hollow = Hollow(x=200.0, y=self.world.floor_y())

        # NEW — systems
        self.sanity = SanitySystem()
        self.quota  = QuotaSystem()

        # NEW — track player facing direction for angel line-of-sight
        self.facing_map: dict[str, bool] = {}   # player_id → facing_right

        # NEW — pending group throws for hollow group-redirect
        self._pending_throws: list[tuple[float, float]] = []
        self._throw_window = 0   # frame counter for simultaneous throw window

    # ------------------------------------------------------------------
    # Connection handlers (Hugo's code, unchanged)
    # ------------------------------------------------------------------

    def _handle_join(self, conn: socket.socket, message: dict) -> None:
        player_id = str(uuid.uuid4())[:8]
        name      = str(message.get("name", "Player"))
        player    = Player(player_id=player_id, name=name)
        self.players[player_id]   = player
        self.connections[conn]    = player_id
        self.facing_map[player_id] = True   # NEW — default facing right

        # NEW — register with sanity system
        self.sanity.register(player_id)

        ServerNetwork.send(
            conn,
            {"type": "PLAYER_JOIN", "id": player_id, "name": name},
        )

    def _handle_move(self, conn: socket.socket, message: dict, dt: float) -> None:
        player_id = self.connections.get(conn)
        if not player_id or player_id not in self.players:
            return

        input_state = {
            "move_x":    message.get("move_x", 0),
            "climb":     message.get("climb", 0),
            "on_ladder": message.get("on_ladder", False),
        }
        player = self.players[player_id]
        apply_player_input(player, input_state, dt, floor_y=self.world.floor_y())
        self.behavior_tracker.record(player_id, player.x, player.y)

        # NEW — update facing direction from move_x
        if input_state["move_x"] > 0:
            self.facing_map[player_id] = True
        elif input_state["move_x"] < 0:
            self.facing_map[player_id] = False

    # NEW — handle item throw (redirects Hollow)
    def _handle_item_throw(self, conn: socket.socket, message: dict) -> None:
        """Process a thrown item message from a client.

        Args:
            conn:    Client socket.
            message: Message dict with 'land_x' and 'land_y' keys.
        """
        land_x = float(message.get("land_x", 0))
        land_y = float(message.get("land_y", 0))
        self._pending_throws.append((land_x, land_y))
        self._throw_window = 30   # 30 frames = ~0.5s window for group throw

    # NEW — handle sample sell at dropzone
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

    def _cleanup_connection(self, conn: socket.socket) -> None:
        player_id = self.connections.pop(conn, None)
        self.buffers.pop(conn, None)
        self.facing_map.pop(player_id, None)   # NEW
        if player_id:
            self.sanity.remove(player_id)      # NEW
            self.players.pop(player_id, None)
        try:
            conn.close()
        except OSError:
            pass

    # ------------------------------------------------------------------
    # Game state broadcast
    # ------------------------------------------------------------------

    def _broadcast_game_state(self) -> None:
        # NEW — include new monsters and systems in state
        all_monsters = [
            self.siren.to_dict(),
            self.angel.to_dict(),
            self.hollow.to_dict(),
        ]

        state_message = {
            "type": "GAME_STATE",
            "players": [p.to_dict() for p in self.players.values()],
            "mimic":   self.mimic.to_dict(),
            "map": {
                "platforms": self.world.platforms,
                "ladders":   self.world.ladders,
            },
            # NEW fields
            "monsters":   all_monsters,
            "sanity":     self.sanity.to_dict(),
            "quota":      self.quota.to_dict(),
        }

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
                    elif msg_type == "ITEM_THROW":      # NEW
                        self._handle_item_throw(conn, msg)
                    elif msg_type == "SELL_SAMPLES":    # NEW
                        self._handle_sell_samples(conn, msg)

            if now - last_tick >= target_dt:
                # Hugo's mimic (unchanged)
                self.mimic.update_random_walk(
                    dt=target_dt,
                    world_min_x=10,
                    world_max_x=self.world.world_width - 40,
                )

                # NEW — update all new monsters
                all_monsters = [self.siren, self.angel, self.hollow]

                self.siren.update(
                    dt=target_dt,
                    players=self.players,
                    sanity_map=self.sanity.values,
                    floor_y=self.world.floor_y(),
                    world_min_x=10,
                    world_max_x=self.world.world_width - 40,
                    is_night=self.quota.is_night,
                )
                self.siren.try_break_trance(self.players)

                self.angel.update(
                    players=self.players,
                    facing_map=self.facing_map,
                    floor_y=self.world.floor_y(),
                )

                # Hollow — handle group throw window
                if self._throw_window > 0:
                    self._throw_window -= 1
                    if self._throw_window == 0 and self._pending_throws:
                        if not self.hollow.group_redirect(self._pending_throws):
                            # Not enough throws for group — use last one
                            lx, ly = self._pending_throws[-1]
                            self.hollow.redirect(lx, ly)
                        self._pending_throws.clear()

                self.hollow.update(
                    dt=target_dt,
                    players=self.players,
                    floor_y=self.world.floor_y(),
                    world_min_x=10,
                    world_max_x=self.world.world_width - 40,
                )

                # NEW — tick sanity and quota
                self.sanity.update(self.players, all_monsters)
                self.quota.tick()

                self._broadcast_game_state()
                last_tick = now

            time.sleep(0.001)
