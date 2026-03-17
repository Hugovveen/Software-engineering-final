"""Main pygame client loop for rendering and sending movement input.

This client demonstrates a readable prototype architecture where networking,
rendering, and systems are separated into small modules.
"""

from __future__ import annotations

import time

import pygame

from client.client_network import ClientNetwork
from config import FPS, SCREEN_HEIGHT, SCREEN_WIDTH, SERVER_HOST, SERVER_PORT
from map.facility_map import FacilityMap
from rendering.camera import Camera
from rendering.renderer import Renderer
from systems.sound_system import SoundSystem


class GameClient:
    """Pygame client that communicates with the server and renders game state."""

    def __init__(self, host: str | None = None, port: int | None = None) -> None:
        self.host = host or SERVER_HOST
        self.port = port or SERVER_PORT

        self.network = ClientNetwork(self.host, self.port)
        self.renderer = Renderer()
        self.sound = SoundSystem()
        self.map = FacilityMap()
        self.camera = Camera(self.map.world_width)

        self.self_id: str | None = None
        self.game_state: dict = {"players": [], "mimic": {}, "map": {}}
        self.recent_events: list[dict] = []
        self.round_info: dict = {"state": "LOBBY", "number": 1, "time_remaining": 0.0}

    def _push_event(self, text: str, ttl: float = 3.0) -> None:
        self.recent_events.append(
            {
                "text": text,
                "expires_at": time.perf_counter() + max(0.1, ttl),
            }
        )
        if len(self.recent_events) > 12:
            self.recent_events = self.recent_events[-12:]

    def _ingest_gameplay_events(self, events: list[dict]) -> None:
        for event in events:
            event_type = str(event.get("type", ""))
            if event_type == "PLAYER_CHARMED":
                self._push_event(
                    f"Player {event.get('player_id', '?')} charmed (L{event.get('charm_level', 0)})",
                    ttl=3.0,
                )
            elif event_type == "ROUND_STATE_CHANGED":
                state = str(event.get("state", "LOBBY"))
                round_number = int(event.get("round_number", 1))
                reason = event.get("reason")
                reason_suffix = f" ({reason})" if reason else ""
                self._push_event(f"Round {round_number}: {state}{reason_suffix}", ttl=3.5)
            elif event_type == "SIREN_PULSE":
                target_count = len(event.get("target_ids", []))
                self._push_event(f"Siren pulse hit {target_count} target(s)", ttl=3.0)
            elif event_type == "ENEMY_ATTACK":
                enemy_type = str(event.get("enemy_type", "enemy"))
                target_id = event.get("target_id") or "?"
                self._push_event(f"{enemy_type} attacking {target_id}", ttl=2.0)

    def _prune_events(self) -> None:
        now = time.perf_counter()
        self.recent_events = [event for event in self.recent_events if float(event.get("expires_at", 0.0)) > now]

    def _send_join(self) -> None:
        self.network.send({"type": "PLAYER_JOIN", "name": "Student"})

    def _build_input_message(self) -> dict:
        keys = pygame.key.get_pressed()

        move_x = 0
        if keys[pygame.K_a] or keys[pygame.K_LEFT]:
            move_x -= 1
        if keys[pygame.K_d] or keys[pygame.K_RIGHT]:
            move_x += 1

        climb = 0
        if keys[pygame.K_w] or keys[pygame.K_UP]:
            climb -= 1
        if keys[pygame.K_s] or keys[pygame.K_DOWN]:
            climb += 1

        on_ladder = keys[pygame.K_w] or keys[pygame.K_UP] or keys[pygame.K_s] or keys[pygame.K_DOWN]

        return {
            "type": "PLAYER_MOVE",
            "move_x": move_x,
            "climb": climb,
            "on_ladder": bool(on_ladder),
        }

    def _handle_network_messages(self) -> None:
        for msg in self.network.receive_many():
            msg_type = msg.get("type")
            if msg_type == "PLAYER_JOIN":
                self.self_id = msg.get("id")
            elif msg_type == "PLAYER_CONNECTED":
                self._push_event(f"{msg.get('name', 'Player')} joined", ttl=2.0)
            elif msg_type == "PLAYER_DISCONNECTED":
                self._push_event(f"{msg.get('name', 'Player')} left", ttl=2.0)
            elif msg_type == "GAME_STATE":
                self.game_state = msg
                self.round_info = dict(msg.get("round", self.round_info))
                self._ingest_gameplay_events(list(msg.get("events", [])))

    def _update_camera(self) -> None:
        if not self.self_id:
            return
        for player in self.game_state.get("players", []):
            if player.get("id") == self.self_id:
                self.camera.follow(player.get("x", 0.0))
                break

    def run(self) -> None:
        """Run the pygame window loop and client networking."""
        pygame.init()
        pygame.display.set_caption("2D Horror Multiplayer Scaffold")
        screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        clock = pygame.time.Clock()

        self.network.connect()
        self._send_join()

        running = True
        while running:
            dt = clock.tick(FPS) / 1000.0

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False

            # Send input to server each frame for simple responsiveness.
            self.network.send(self._build_input_message())
            self._handle_network_messages()
            self._prune_events()
            self._update_camera()
            self.renderer.draw(
                screen,
                self.camera,
                self.game_state,
                self.self_id,
                dt,
                recent_events=self.recent_events,
            )

            if dt > 0:
                pass  # Placeholder for future local interpolation systems.

        self.network.close()
        pygame.quit()
