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

LOADING_DURATION = 3.0  # seconds minimum for loading screen


class GameClient:
    """Pygame client that communicates with the server and renders game state."""

    def __init__(self, host: str | None = None, port: int | None = None) -> None:
        self.host = host or SERVER_HOST
        self.port = port or SERVER_PORT

        self.network = ClientNetwork(self.host, self.port)
        self.renderer = Renderer(SCREEN_WIDTH, SCREEN_HEIGHT)
        self.sound = SoundSystem()
        self.map = FacilityMap()
        self.camera = Camera(self.map.world_width)

        self.self_id: str | None = None
        self.game_state: dict = {"players": [], "mimic": {}, "map": {}}
        self.recent_events: list[dict] = []
        self.round_info: dict = {"state": "LOBBY", "number": 1, "time_remaining": 0.0}
        self.facing_map: dict[str, bool] = {}
        self.sanity_map: dict[str, float] = {}

        # Client-side screen state
        self.client_state: str = "TITLE"
        self._loading_progress: float = 0.0
        self._connected: bool = False

        # Title screen state
        self._title_name: str = ""
        self._title_skin: str = "researcher"
        self._cursor_timer: float = 0.0

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
            elif event_type == "LOOT_PICKED":
                self._push_event(
                    f"{event.get('player_id', '?')} picked loot (+{int(event.get('value', 0))})",
                    ttl=2.0,
                )
            elif event_type == "LOOT_DEPOSITED":
                self._push_event(
                    f"{event.get('player_id', '?')} deposited {int(event.get('value', 0))}",
                    ttl=2.5,
                )

    def _prune_events(self) -> None:
        now = time.perf_counter()
        self.recent_events = [event for event in self.recent_events if float(event.get("expires_at", 0.0)) > now]

    def _send_join(self) -> None:
        self.network.send({
            "type": "PLAYER_JOIN",
            "name": self._title_name.strip() or "Player",
            "skin": self._title_skin,
        })

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
        jump = keys[pygame.K_SPACE]
        sprint = keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]

        if self.self_id:
            if move_x > 0:
                self.facing_map[self.self_id] = True
            elif move_x < 0:
                self.facing_map[self.self_id] = False

        return {
            "type": "PLAYER_MOVE",
            "move_x": move_x,
            "climb": climb,
            "on_ladder": bool(on_ladder),
            "jump": bool(jump),
            "sprint": bool(sprint),
        }

    def _handle_network_messages(self) -> None:
        if not self._connected:
            return
        for msg in self.network.receive_many():
            msg_type = msg.get("type")
            if msg_type == "PLAYER_JOIN":
                self.self_id = msg.get("id")
                assigned_skin = msg.get("skin")
                if assigned_skin:
                    self._title_skin = assigned_skin
            elif msg_type == "PLAYER_CONNECTED":
                self._push_event(f"{msg.get('name', 'Player')} joined", ttl=2.0)
            elif msg_type == "PLAYER_DISCONNECTED":
                self._push_event(f"{msg.get('name', 'Player')} left", ttl=2.0)
            elif msg_type == "GAME_STATE":
                self.game_state = msg
                self.round_info = dict(msg.get("round", self.round_info))
                self._ingest_gameplay_events(list(msg.get("events", [])))
                for player in self.game_state.get("players", []):
                    player_id = str(player.get("id", ""))
                    if player_id and player_id not in self.facing_map:
                        self.facing_map[player_id] = True
                    self.sanity_map[player_id] = float(player.get("sanity", 100.0))

    def _update_camera(self) -> None:
        if not self.self_id:
            return
        for player in self.game_state.get("players", []):
            if player.get("id") == self.self_id:
                self.camera.follow(player.get("x", 0.0))
                break

    def _connect_to_server(self) -> None:
        self.network.connect()
        self._send_join()
        self._connected = True

    def _disconnect(self) -> None:
        if self._connected:
            self.network.close()
            self._connected = False
        self.self_id = None
        self.game_state = {"players": [], "mimic": {}, "map": {}}
        self.round_info = {"state": "LOBBY", "number": 1, "time_remaining": 0.0}
        self.facing_map.clear()
        self.sanity_map.clear()
        self.recent_events.clear()

    def _draw_game_world(
        self,
        screen: pygame.Surface,
        skip_wall: bool = False,
        enable_lighting: bool = True,
    ) -> None:
        """Render the game world (used by both LOBBY and PLAYING states)."""
        self._update_camera()
        self.renderer.draw(
            screen,
            self.camera,
            self.game_state,
            self.self_id,
            facing_map=self.facing_map,
            sanity_map=self.sanity_map,
            skip_wall=skip_wall,
            enable_lighting=enable_lighting,
        )

    def _send_movement(self, dt: float) -> None:
        """Send movement input at a throttled rate."""
        if not self._connected:
            return
        self.network.send(self._build_input_message())

    def run(self) -> None:
        """Run the pygame window loop and client networking."""
        pygame.init()
        pygame.display.set_caption("GROVE")
        screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        clock = pygame.time.Clock()

        input_send_interval = 1.0 / 30.0
        time_since_input_send = input_send_interval

        running = True
        while running:
            dt = clock.tick_busy_loop(FPS) / 1000.0
            time_since_input_send += dt
            self._cursor_timer += dt

            # --- Event handling ---
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False

                elif event.type == pygame.KEYDOWN:
                    # --- TITLE state input ---
                    if self.client_state == "TITLE":
                        if event.key == pygame.K_RETURN:
                            if self._title_name.strip():
                                self._connect_to_server()
                                self._loading_progress = 0.0
                                self.client_state = "LOADING"
                        elif event.key == pygame.K_BACKSPACE:
                            self._title_name = self._title_name[:-1]
                        elif event.key in (pygame.K_LEFT, pygame.K_RIGHT):
                            self._title_skin = "student" if self._title_skin == "researcher" else "researcher"

                    # --- LOBBY state input ---
                    elif self.client_state == "LOBBY":
                        if event.key == pygame.K_RETURN:
                            player_count = len(self.game_state.get("players", []))
                            if player_count >= 2:
                                self.network.send({"type": "START_GAME"})
                        elif event.key == pygame.K_e:
                            self.network.send({"type": "PLAYER_INTERACT"})

                    # --- PLAYING state input ---
                    elif self.client_state == "PLAYING":
                        if event.key == pygame.K_e:
                            self.network.send({"type": "PLAYER_INTERACT"})

                    # --- GAME_OVER state input ---
                    elif self.client_state == "GAME_OVER":
                        if event.key == pygame.K_RETURN:
                            self._disconnect()
                            self._title_name = ""
                            self._title_skin = "researcher"
                            self.client_state = "TITLE"

                elif event.type == pygame.TEXTINPUT:
                    if self.client_state == "TITLE":
                        if len(self._title_name) < 16:
                            self._title_name += event.text

                elif event.type == pygame.MOUSEBUTTONDOWN:
                    if self.client_state == "TITLE" and event.button == 1:
                        mx, my = event.pos
                        sw, sh = screen.get_size()
                        # Match renderer layout: boxes at sh*0.15, spacing 180
                        box_top = int(sh * 0.15)
                        box_w, box_h = 120, 150
                        spacing = 180
                        r_cx = sw // 2 - spacing // 2  # researcher (left)
                        s_cx = sw // 2 + spacing // 2  # student (right)
                        if box_top <= my <= box_top + box_h:
                            if r_cx - box_w // 2 <= mx <= r_cx + box_w // 2:
                                self._title_skin = "researcher"
                            elif s_cx - box_w // 2 <= mx <= s_cx + box_w // 2:
                                self._title_skin = "student"

            # --- State rendering ---

            if self.client_state == "TITLE":
                cursor_vis = int(self._cursor_timer * 2) % 2 == 0
                self.renderer.draw_title_screen(screen, self._title_name, self._title_skin, cursor_vis)

            elif self.client_state == "LOADING":
                self._handle_network_messages()
                self._loading_progress += dt / LOADING_DURATION
                self.renderer.draw_loading_screen(screen, self._loading_progress)
                if self._loading_progress >= 1.0:
                    self.client_state = "LOBBY"

            elif self.client_state == "LOBBY":
                self._handle_network_messages()
                server_state = self.round_info.get("state", "LOBBY")
                if server_state == "PLAYING":
                    self.client_state = "PLAYING"
                elif server_state == "GAME_OVER":
                    self.client_state = "GAME_OVER"

                # Send movement input — lobby is playable
                if time_since_input_send >= input_send_interval:
                    self._send_movement(dt)
                    time_since_input_send -= input_send_interval

                self._prune_events()
                self.renderer.draw_lobby_background(screen)
                self._draw_game_world(screen, skip_wall=True, enable_lighting=False)
                self.renderer.draw_lobby_overlay(screen, self.game_state)

            elif self.client_state == "PLAYING":
                self._handle_network_messages()
                server_state = self.round_info.get("state", "PLAYING")
                if server_state == "GAME_OVER":
                    self.client_state = "GAME_OVER"

                if time_since_input_send >= input_send_interval:
                    self.network.send(self._build_input_message())
                    time_since_input_send -= input_send_interval
                self._prune_events()
                self._update_camera()
                self.renderer.draw(
                    screen,
                    self.camera,
                    self.game_state,
                    self.self_id,
                    facing_map=self.facing_map,
                    sanity_map=self.sanity_map,
                )

            elif self.client_state == "GAME_OVER":
                self._handle_network_messages()
                self.renderer.draw_game_over(screen, self.game_state)

            pygame.display.flip()

        if self._connected:
            self.network.close()
        pygame.quit()
