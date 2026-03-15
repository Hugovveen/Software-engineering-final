"""Main pygame client loop for rendering and sending movement input.

This client demonstrates a readable prototype architecture where networking,
rendering, and systems are separated into small modules.
"""

from __future__ import annotations

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
            elif msg_type == "GAME_STATE":
                self.game_state = msg

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
            self._update_camera()
            self.renderer.draw(screen, self.camera, self.game_state, self.self_id, dt)

            if dt > 0:
                pass  # Placeholder for future local interpolation systems.

        self.network.close()
        pygame.quit()
