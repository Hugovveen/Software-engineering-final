"""Main multiplayer server loop.

Responsibilities:
- track connected players
- update mimic state
- receive movement commands
- broadcast game state at a fixed tick rate
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


class GameServer:
    """Simple authoritative server for the prototype game world."""

    def __init__(self, host: str | None = None, port: int | None = None) -> None:
        self.host = host or SERVER_HOST
        self.port = port or SERVER_PORT
        self.network = ServerNetwork(self.host, self.port)

        self.players: dict[str, Player] = {}
        self.connections: dict[socket.socket, str] = {}
        self.buffers: dict[socket.socket, str] = {}

        self.world = FacilityMap()
        self.mimic = Mimic()
        self.behavior_tracker = BehaviorTracker()

    def _handle_join(self, conn: socket.socket, message: dict) -> None:
        player_id = str(uuid.uuid4())[:8]
        name = str(message.get("name", "Player"))
        player = Player(player_id=player_id, name=name)
        self.players[player_id] = player
        self.connections[conn] = player_id

        ServerNetwork.send(
            conn,
            {
                "type": "PLAYER_JOIN",
                "id": player_id,
                "name": name,
            },
        )

    def _handle_move(self, conn: socket.socket, message: dict, dt: float) -> None:
        player_id = self.connections.get(conn)
        if not player_id or player_id not in self.players:
            return

        input_state = {
            "move_x": message.get("move_x", 0),
            "climb": message.get("climb", 0),
            "on_ladder": message.get("on_ladder", False),
        }
        player = self.players[player_id]
        apply_player_input(player, input_state, dt, floor_y=self.world.floor_y())
        self.behavior_tracker.record(player_id, player.x, player.y)

    def _cleanup_connection(self, conn: socket.socket) -> None:
        player_id = self.connections.pop(conn, None)
        self.buffers.pop(conn, None)
        if player_id:
            self.players.pop(player_id, None)
        try:
            conn.close()
        except OSError:
            pass

    def _broadcast_game_state(self) -> None:
        state_message = {
            "type": "GAME_STATE",
            "players": [p.to_dict() for p in self.players.values()],
            "mimic": self.mimic.to_dict(),
            "map": {
                "platforms": self.world.platforms,
                "ladders": self.world.ladders,
            },
        }

        dead_connections: list[socket.socket] = []
        for conn in list(self.connections.keys()):
            try:
                ServerNetwork.send(conn, state_message)
            except OSError:
                dead_connections.append(conn)

        for conn in dead_connections:
            self._cleanup_connection(conn)

    def run(self) -> None:
        """Run the server loop until interrupted."""
        print(f"[SERVER] Listening on {self.host}:{self.port}")
        target_dt = 1.0 / TICK_RATE
        last_tick = time.perf_counter()

        while True:
            accepted = self.network.accept_client()
            if accepted:
                conn, addr = accepted
                print(f"[SERVER] Client connected: {addr}")
                self.buffers[conn] = ""

            now = time.perf_counter()
            dt = max(0.0, now - last_tick)

            for conn in list(self.buffers.keys()):
                try:
                    messages, updated_buffer = ServerNetwork.receive_many(conn, self.buffers[conn])
                    self.buffers[conn] = updated_buffer
                except OSError:
                    self._cleanup_connection(conn)
                    continue

                for msg in messages:
                    msg_type = msg.get("type")
                    if msg_type == "PLAYER_JOIN":
                        self._handle_join(conn, msg)
                    elif msg_type == "PLAYER_MOVE":
                        self._handle_move(conn, msg, dt)

            if now - last_tick >= target_dt:
                self.mimic.update_random_walk(
                    dt=target_dt,
                    world_min_x=10,
                    world_max_x=self.world.world_width - 40,
                )
                self._broadcast_game_state()
                last_tick = now

            time.sleep(0.001)
