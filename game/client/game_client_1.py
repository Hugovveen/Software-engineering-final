"""Main pygame client for GROVE.

Responsibilities:
- open the pygame window
- read keyboard input and send PLAYER_MOVE to server
- receive GAME_STATE from server
- pass state to Renderer for drawing

Controls:
    A / Left arrow  — move left
    D / Right arrow — move right
    W / Up arrow    — climb ladder (when on ladder)
    S / Down arrow  — descend ladder
    F               — throw item (redirects The Hollow)
    ESC             — quit
"""

from __future__ import annotations

import sys
import pygame

from client.client_network import ClientNetwork
from rendering.renderer import Renderer
from rendering.camera import Camera
from systems.sound_system import SoundSystem

try:
    from config import (
        SCREEN_WIDTH, SCREEN_HEIGHT, FPS,
        SERVER_HOST, SERVER_PORT,
    )
except ImportError:
    SCREEN_WIDTH  = 1024
    SCREEN_HEIGHT = 576
    FPS           = 60
    SERVER_HOST   = "127.0.0.1"
    SERVER_PORT   = 5000

# Width of the world (should match FacilityMap.world_width)
WORLD_WIDTH = 1600


class GameClient:
    """Pygame client that connects to the GROVE game server.

    Attributes:
        host:         Server host address.
        port:         Server port.
        network:      TCP client network wrapper.
        renderer:     Renderer instance.
        camera:       Camera for side-view scrolling.
        sound:        SoundSystem placeholder.
        game_state:   Latest GAME_STATE dict received from server.
        self_id:      This client's assigned player_id.
        facing_right: True if local player is facing right.
        running:      False when the game loop should exit.
    """

    def __init__(self, host: str | None = None, port: int | None = None) -> None:
        self.host = host or SERVER_HOST
        self.port = port or SERVER_PORT

        self.network      = ClientNetwork(self.host, self.port)
        self.renderer     = Renderer(SCREEN_WIDTH, SCREEN_HEIGHT)
        self.camera       = Camera(world_width=WORLD_WIDTH)
        self.sound        = SoundSystem()

        self.game_state:   dict       = {}
        self.self_id:      str | None = None
        self.facing_right: bool       = True
        self.running:      bool       = True

        # Local facing map for lighting (includes remote players too,
        # but we only know our own — others default to True)
        self._facing_map: dict[str, bool] = {}

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def _connect(self) -> None:
        """Connect to server and send PLAYER_JOIN."""
        print(f"[CLIENT] Connecting to {self.host}:{self.port}...")
        self.network.connect()
        self.network.send({"type": "PLAYER_JOIN", "name": "Player"})
        print("[CLIENT] Connected. Waiting for server...")

    # ------------------------------------------------------------------
    # Input
    # ------------------------------------------------------------------

    def _read_input(self) -> dict | None:
        """Read keyboard state and return a PLAYER_MOVE message, or None to quit.

        Returns:
            Move message dict, or None if ESC/window close pressed.
        """
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return None
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return None
                if event.key == pygame.K_f:
                    self._throw_item()

        keys = pygame.key.get_pressed()

        move_x = 0.0
        if keys[pygame.K_a] or keys[pygame.K_LEFT]:
            move_x = -1.0
            self.facing_right = False
        if keys[pygame.K_d] or keys[pygame.K_RIGHT]:
            move_x = 1.0
            self.facing_right = True

        climb = 0.0
        on_ladder = False
        if keys[pygame.K_w] or keys[pygame.K_UP]:
            climb     = -1.0
            on_ladder = True
        if keys[pygame.K_s] or keys[pygame.K_DOWN]:
            climb     = 1.0
            on_ladder = True

        if self.self_id:
            self._facing_map[self.self_id] = self.facing_right

        return {
            "type":      "PLAYER_MOVE",
            "move_x":    move_x,
            "climb":     climb,
            "on_ladder": on_ladder,
        }

    def _throw_item(self) -> None:
        """Send an ITEM_THROW message toward the facing direction."""
        # Estimate a landing position 200px ahead in facing direction
        players = self.game_state.get("players", [])
        my_pos  = next((p for p in players if p.get("id") == self.self_id), None)
        if my_pos:
            offset  = 200 if self.facing_right else -200
            land_x  = my_pos["x"] + offset
            land_y  = my_pos["y"]
            self.network.send({"type": "ITEM_THROW", "land_x": land_x, "land_y": land_y})
            self.sound.play_footstep(self.self_id or "")   # placeholder SFX

    # ------------------------------------------------------------------
    # Network receive
    # ------------------------------------------------------------------

    def _process_messages(self) -> None:
        """Read and apply all pending server messages."""
        for msg in self.network.receive_many():
            mtype = msg.get("type")

            if mtype == "PLAYER_JOIN":
                self.self_id = msg.get("id")
                print(f"[CLIENT] Joined as {self.self_id}")

            elif mtype == "GAME_STATE":
                self.game_state = msg
                # Update camera to follow our player
                if self.self_id:
                    players = msg.get("players", [])
                    me = next((p for p in players if p.get("id") == self.self_id), None)
                    if me:
                        self.camera.follow(me["x"])

            elif mtype == "SAMPLE_SOLD":
                total = msg.get("total", 0)
                print(f"[CLIENT] Sold samples for {total} credits.")

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Initialise pygame and run the game loop until exit."""
        pygame.init()
        screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        pygame.display.set_caption("GROVE")
        clock  = pygame.time.Clock()

        try:
            self._connect()
        except ConnectionRefusedError:
            print("[CLIENT] Could not connect to server. Is it running?")
            print(f"         Try: python main.py server")
            pygame.quit()
            sys.exit(1)

        print("[CLIENT] Running. Controls: WASD to move, F to throw item, ESC to quit.")

        while self.running:
            move_msg = self._read_input()
            if move_msg is None:
                self.running = False
                break

            self.network.send(move_msg)
            self._process_messages()

            # Build sanity map from game state
            sanity_map = self.game_state.get("sanity", {})

            if self.game_state:
                self.renderer.draw(
                    screen      = screen,
                    camera      = self.camera,
                    game_state  = self.game_state,
                    self_id     = self.self_id,
                    facing_map  = self._facing_map,
                    sanity_map  = sanity_map,
                )

            clock.tick(FPS)

        self.network.close()
        pygame.quit()
        print("[CLIENT] Disconnected.")
