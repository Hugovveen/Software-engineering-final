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
from entities.enemy_base import EnemyBase
from entities.enemy_registry import EnemyRegistry
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
        self.pending_inputs: dict[str, dict] = {}

        self.world = FacilityMap()
        self.enemies: dict[str, EnemyBase] = {}
        self.mimic_id: str = "mimic-1"
        self._spawn_initial_enemies()
        self.behavior_tracker = BehaviorTracker()
        self.previous_enemy_states: dict[str, str] = {}
        self.previous_player_charm_levels: dict[str, int] = {}

    def _spawn_initial_enemies(self) -> None:
        try:
            mimic = EnemyRegistry.create("mimic", enemy_id=self.mimic_id)
        except ValueError:
            mimic = Mimic(enemy_id=self.mimic_id)
        self.enemies[mimic.enemy_id] = mimic

        for enemy_type, enemy_id, spawn_x in (
            ("weeping_angel", "weeping-angel-1", 860.0),
            ("siren", "siren-1", 1220.0),
        ):
            try:
                enemy = EnemyRegistry.create(enemy_type, enemy_id=enemy_id, x=spawn_x)
                self.enemies[enemy.enemy_id] = enemy
            except ValueError:
                continue

    @property
    def mimic(self) -> EnemyBase:
        return self.enemies[self.mimic_id]

    @staticmethod
    def _sanitize_input(message: dict) -> dict:
        move_x = float(message.get("move_x", 0.0))
        climb = float(message.get("climb", 0.0))
        move_x = max(-1.0, min(1.0, move_x))
        climb = max(-1.0, min(1.0, climb))
        return {
            "move_x": move_x,
            "climb": climb,
            "on_ladder": bool(message.get("on_ladder", False)),
        }

    def _send_to_all(self, message: dict) -> None:
        dead_connections: list[socket.socket] = []
        for conn in list(self.connections.keys()):
            try:
                ServerNetwork.send(conn, message)
            except OSError:
                dead_connections.append(conn)

        for conn in dead_connections:
            self._cleanup_connection(conn)

    def _handle_join(self, conn: socket.socket, message: dict) -> None:
        if conn in self.connections:
            return

        player_id = str(uuid.uuid4())[:8]
        name = str(message.get("name", "Player"))
        player = Player(player_id=player_id, name=name)
        self.players[player_id] = player
        self.connections[conn] = player_id
        self.pending_inputs[player_id] = {"move_x": 0.0, "climb": 0.0, "on_ladder": False}

        ServerNetwork.send(
            conn,
            {
                "type": "PLAYER_JOIN",
                "id": player_id,
                "name": name,
            },
        )

        self._send_to_all(
            {
                "type": "PLAYER_CONNECTED",
                "id": player_id,
                "name": name,
            }
        )

    def _handle_move(self, conn: socket.socket, message: dict) -> None:
        player_id = self.connections.get(conn)
        if not player_id or player_id not in self.players:
            return

        self.pending_inputs[player_id] = self._sanitize_input(message)

    def _fixed_update(self, dt: float) -> None:
        for player_id in sorted(self.players.keys()):
            player = self.players[player_id]
            input_state = self.pending_inputs.get(
                player_id,
                {"move_x": 0.0, "climb": 0.0, "on_ladder": False},
            )
            apply_player_input(
                player,
                input_state,
                dt,
                floor_y=self.world.floor_y(),
                world_width=float(self.world.world_width),
                ladders=self.world.ladders,
            )
            self.behavior_tracker.record(player_id, player.x, player.y)

        for enemy_id in sorted(self.enemies.keys()):
            self.enemies[enemy_id].update(dt=dt, world=self.world, players=self.players)

    def _cleanup_connection(self, conn: socket.socket) -> None:
        player_id = self.connections.pop(conn, None)
        self.buffers.pop(conn, None)
        if player_id:
            departed = self.players.pop(player_id, None)
            self.pending_inputs.pop(player_id, None)
            self._send_to_all(
                {
                    "type": "PLAYER_DISCONNECTED",
                    "id": player_id,
                    "name": departed.name if departed else "Player",
                }
            )
        try:
            conn.close()
        except OSError:
            pass

    def _broadcast_game_state(self) -> None:
        enemies_payload = [enemy.to_dict() for enemy in self.enemies.values()]
        mimic_payload = self.mimic.to_dict() if self.mimic_id in self.enemies else {}
        players_payload = [p.to_dict() for p in self.players.values()]
        events = self._build_gameplay_events(players_payload, enemies_payload)

        state_message = {
            "type": "GAME_STATE",
            "players": players_payload,
            "mimic": mimic_payload,
            "enemies": enemies_payload,
            "events": events,
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

    def _build_gameplay_events(self, players_payload: list[dict], enemies_payload: list[dict]) -> list[dict]:
        events: list[dict] = []

        current_enemy_states: dict[str, str] = {}
        for enemy in enemies_payload:
            enemy_id = str(enemy.get("id", ""))
            enemy_type = str(enemy.get("type", "enemy"))
            enemy_state = str(enemy.get("state", "idle"))
            previous_state = self.previous_enemy_states.get(enemy_id)

            if enemy_state == "attacking" and previous_state != "attacking":
                events.append(
                    {
                        "type": "ENEMY_ATTACK",
                        "enemy_id": enemy_id,
                        "enemy_type": enemy_type,
                        "target_id": enemy.get("target_id"),
                    }
                )

            if (
                enemy_type == "siren"
                and previous_state == "casting"
                and enemy_state == "cooldown"
            ):
                events.append(
                    {
                        "type": "SIREN_PULSE",
                        "enemy_id": enemy_id,
                        "target_ids": enemy.get("charmed_target_ids", []),
                    }
                )

            current_enemy_states[enemy_id] = enemy_state

        current_player_charm_levels: dict[str, int] = {}
        for player in players_payload:
            player_id = str(player.get("id", ""))
            charm_level = int(player.get("charm_level", 0))
            previous_level = self.previous_player_charm_levels.get(player_id, 0)

            if charm_level > 0 and previous_level == 0:
                events.append(
                    {
                        "type": "PLAYER_CHARMED",
                        "player_id": player_id,
                        "by_enemy_id": player.get("charmed_by"),
                        "charm_level": charm_level,
                        "duration": float(player.get("charm_timer", 0.0)),
                    }
                )

            current_player_charm_levels[player_id] = charm_level

        self.previous_enemy_states = current_enemy_states
        self.previous_player_charm_levels = current_player_charm_levels
        return events

    def run(self) -> None:
        """Run the server loop until interrupted."""
        print(f"[SERVER] Listening on {self.host}:{self.port}")
        target_dt = 1.0 / TICK_RATE
        last_tick = time.perf_counter()
        accumulator = 0.0

        while True:
            accepted = self.network.accept_client()
            if accepted:
                conn, addr = accepted
                print(f"[SERVER] Client connected: {addr}")
                self.buffers[conn] = ""

            now = time.perf_counter()
            frame_dt = max(0.0, now - last_tick)
            if frame_dt > 0.25:
                frame_dt = target_dt
            last_tick = now
            accumulator += frame_dt

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
                        self._handle_move(conn, msg)

            while accumulator >= target_dt:
                self._fixed_update(target_dt)
                self._broadcast_game_state()
                accumulator -= target_dt

            time.sleep(0.001)
