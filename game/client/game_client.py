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

try:
    from systems.audio_manager import AudioManager, MusicState
    _HAS_AUDIO = True
except Exception:
    _HAS_AUDIO = False

LOADING_DURATION = 3.0  # seconds minimum for loading screen


class GameClient:
    """Pygame client that communicates with the server and renders game state."""

    def __init__(self, host: str | None = None, port: int | None = None) -> None:
        self.host = host or SERVER_HOST
        self.port = port or SERVER_PORT

        self.network = ClientNetwork(self.host, self.port)
        self.renderer = Renderer(SCREEN_WIDTH, SCREEN_HEIGHT)
        self.sound = SoundSystem()
        self._audio: AudioManager | None = None
        if _HAS_AUDIO:
            try:
                self._audio = AudioManager()
                print("[AUDIO] AudioManager initialized successfully")
            except Exception as e:
                print(f"[AUDIO] AudioManager init failed: {e}")
                self._audio = None
        else:
            print("[AUDIO] AudioManager module not available")
        # Start title/lobby music immediately (lobby_ambient + end_of_story layered)
        self._safe_audio("play_music", MusicState.LOBBY if _HAS_AUDIO else None)
        self._audio_muted: bool = False
        self._prev_alive: dict[str, bool] = {}
        self.map = FacilityMap()
        self.camera = Camera(self.map.world_width, self.map.world_height)

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

        # Lights-out blackout
        self._lights_out_timer: float = 0.0
        # Ending state
        self._ending_fade_timer: float = 0.0
        self._ending_player: dict = {}
        self._ending_player_vx: float = 0.0
        self._ending_player_x: float = 0.0
        self._ending_player_facing: bool = True

        # Fade transition state
        self._fade_to_game: bool = False

        # Title screen state
        self._title_name: str = ""
        self._title_skin: str = "researcher"
        self._title_difficulty: str = "RESEARCHER"
        self._cursor_timer: float = 0.0

    def _play_test_beep(self) -> None:
        """Generate and play a 440Hz sine wave test beep (0.3s)."""
        import array
        import math as _math
        try:
            sample_rate = 44100
            duration = 0.3
            n_samples = int(sample_rate * duration)
            buf = array.array("h", [0] * n_samples)
            for i in range(n_samples):
                t = i / sample_rate
                fade = min(1.0, min(t / 0.01, (duration - t) / 0.01))
                buf[i] = int(16000 * fade * _math.sin(2 * _math.pi * 440 * t))
            sound = pygame.mixer.Sound(buffer=buf)
            sound.play()
            print("[CLIENT] Test beep played successfully")
        except Exception as e:
            print(f"[CLIENT] Test beep failed: {e}")

    def _safe_audio(self, method: str, *args, **kwargs):
        """Call an AudioManager method, silently ignoring errors."""
        if self._audio is None:
            return None
        fn = getattr(self._audio, method, None)
        if fn is None:
            return None
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            print(f"[AUDIO] {method}() failed: {e}")
            return None

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
                self._safe_audio("on_item_pickup")
            elif event_type == "LOOT_DEPOSITED":
                self._push_event(
                    f"{event.get('player_id', '?')} deposited {int(event.get('value', 0))}",
                    ttl=2.5,
                )
            elif event_type == "LIGHTS_OUT":
                self._lights_out_timer = 1.5

    def _prune_events(self) -> None:
        now = time.perf_counter()
        self.recent_events = [event for event in self.recent_events if float(event.get("expires_at", 0.0)) > now]

    def _send_join(self) -> None:
        self.network.send({
            "type": "PLAYER_JOIN",
            "name": self._title_name.strip() or "Player",
            "skin": self._title_skin,
            "difficulty": self._title_difficulty,
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

                # Read sanity from top-level sanity dict (server-authoritative)
                server_sanity = msg.get("sanity", {})
                for pid, san_val in server_sanity.items():
                    self.sanity_map[pid] = float(san_val)

    def _update_camera(self) -> None:
        if not self.self_id:
            return
        for player in self.game_state.get("players", []):
            if player.get("id") == self.self_id:
                self.camera.follow(player.get("x", 0.0), player.get("y", 0.0))
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
        self._prev_alive.clear()
        self.renderer._death_particles.clear()
        self.renderer._death_finished.clear()
        # Reset ending state
        self._ending_fade_timer = 0.0
        self._ending_player = {}
        self._ending_player_vx = 0.0
        self._ending_player_x = 0.0
        self._ending_player_facing = True
        self._lights_out_timer = 0.0
        self._fade_to_game = False
        if hasattr(self, '_ending_faded_in'):
            del self._ending_faded_in

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
        print(f"[CLIENT] MIXER STATUS: {pygame.mixer.get_init()}")
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
                        elif event.key in (pygame.K_UP, pygame.K_DOWN):
                            diffs = ["STUDENT", "RESEARCHER", "EXPERT"]
                            idx = diffs.index(self._title_difficulty) if self._title_difficulty in diffs else 1
                            if event.key == pygame.K_UP:
                                idx = max(0, idx - 1)
                            else:
                                idx = min(len(diffs) - 1, idx + 1)
                            self._title_difficulty = diffs[idx]

                    # --- LOBBY state input ---
                    elif self.client_state == "LOBBY":
                        if event.key == pygame.K_RETURN:
                            self.network.send({"type": "START_GAME"})
                        elif event.key == pygame.K_e:
                            self.network.send({"type": "PLAYER_INTERACT"})
                        elif event.key == pygame.K_m:
                            self._audio_muted = not self._audio_muted
                            self._safe_audio("set_music_volume", 0.0 if self._audio_muted else 0.45)

                    # --- PLAYING state input ---
                    elif self.client_state == "PLAYING":
                        if event.key == pygame.K_e:
                            self.network.send({"type": "PLAYER_INTERACT"})
                        elif event.key == pygame.K_m:
                            self._audio_muted = not self._audio_muted
                            self._safe_audio("set_music_volume", 0.0 if self._audio_muted else 0.45)

                    # --- QUOTA_MET state input ---
                    elif self.client_state == "QUOTA_MET":
                        if event.key == pygame.K_e:
                            self.network.send({"type": "PLAYER_INTERACT"})

                    # --- ENDING state input ---
                    elif self.client_state == "ENDING":
                        if event.key == pygame.K_RETURN:
                            self._disconnect()
                            self._title_name = ""
                            self._title_skin = "researcher"
                            self._title_difficulty = "RESEARCHER"
                            self.renderer._ending_phase_timer = 0.0
                            self.renderer._ending_stars.clear()
                            self.renderer._quota_met = False
                            # Restart title/lobby music (lobby_ambient + end_of_story)
                            self._safe_audio("play_music", MusicState.SILENT if _HAS_AUDIO else None)
                            self._safe_audio("play_music", MusicState.LOBBY if _HAS_AUDIO else None)
                            # Reinitialize network for clean reconnection
                            self.network = ClientNetwork(self.host, self.port)
                            self.renderer.start_fade_in(1.5)
                            self.client_state = "TITLE"

                    # --- GAME_OVER state input ---
                    elif self.client_state == "GAME_OVER":
                        if event.key == pygame.K_RETURN and not self._safe_audio("is_game_over_playing"):
                            self._disconnect()
                            self._title_name = ""
                            self._title_skin = "researcher"
                            self._title_difficulty = "RESEARCHER"
                            self.renderer._quota_met = False
                            # Restart title/lobby music (lobby_ambient + end_of_story)
                            self._safe_audio("play_music", MusicState.SILENT if _HAS_AUDIO else None)
                            self._safe_audio("play_music", MusicState.LOBBY if _HAS_AUDIO else None)
                            # Reinitialize network for clean reconnection
                            self.network = ClientNetwork(self.host, self.port)
                            self.renderer.start_fade_in(1.5)
                            self.client_state = "TITLE"

                elif event.type == pygame.TEXTINPUT:
                    if self.client_state == "TITLE":
                        if len(self._title_name) < 16:
                            self._title_name += event.text

                elif event.type == pygame.MOUSEBUTTONDOWN:
                    if self.client_state == "LOBBY" and event.button == 1:
                        btn_rect = getattr(self.renderer, '_test_sound_btn_rect', None)
                        if btn_rect and btn_rect.collidepoint(event.pos):
                            self._play_test_beep()
                    if self.client_state == "TITLE" and event.button == 1:
                        mx, my = event.pos
                        sw, sh = screen.get_size()
                        # Match renderer layout: boxes at sh*0.62, spacing 180
                        box_top = int(sh * 0.62)
                        box_w, box_h = 120, 150
                        spacing = 180
                        r_cx = sw // 2 - spacing // 2  # researcher (left)
                        s_cx = sw // 2 + spacing // 2  # student (right)
                        if box_top <= my <= box_top + box_h:
                            if r_cx - box_w // 2 <= mx <= r_cx + box_w // 2:
                                self._title_skin = "researcher"
                            elif s_cx - box_w // 2 <= mx <= s_cx + box_w // 2:
                                self._title_skin = "student"
                        # Difficulty button clicks
                        diff_rects = getattr(self.renderer, '_difficulty_btn_rects', {})
                        for dkey, drect in diff_rects.items():
                            if drect.collidepoint(mx, my):
                                self._title_difficulty = dkey

            # --- State rendering ---

            if self.client_state == "TITLE":
                cursor_vis = int(self._cursor_timer * 2) % 2 == 0
                self.renderer.draw_title_screen(screen, self._title_name, self._title_skin, cursor_vis, self._title_difficulty)

            elif self.client_state == "LOADING":
                self._handle_network_messages()
                self._loading_progress += dt / LOADING_DURATION
                self.renderer.draw_loading_screen(screen, self._loading_progress)
                if self._loading_progress >= 1.0:
                    self.client_state = "LOBBY"
                    # LOBBY music already playing from title screen
                    self.renderer.start_fade_in(1.5)

            elif self.client_state == "LOBBY":
                self._handle_network_messages()
                server_state = self.round_info.get("state", "LOBBY")
                if server_state == "PLAYING":
                    self.client_state = "PLAYING"
                    self.renderer.start_fade_out(0.5)
                    self._safe_audio("play_music", MusicState.GAME if _HAS_AUDIO else None)
                    self._fade_to_game = True  # trigger fade-in after fade-out
                elif server_state == "QUOTA_MET":
                    self.client_state = "QUOTA_MET"
                elif server_state == "ENDING":
                    self.client_state = "ENDING"
                    self._ending_fade_timer = 1.5
                    self.renderer._ending_phase_timer = 0.0
                    self.renderer._ending_stars.clear()
                    self.renderer.start_fade_out(1.5)
                    self._safe_audio("play_music", MusicState.ENDING if _HAS_AUDIO else None)
                elif server_state == "GAME_OVER":
                    self.client_state = "GAME_OVER"
                    self._game_over_lobby_started = False
                    self.renderer.start_fade_out(1.0)
                    self._safe_audio("on_game_over")

                self._prune_events()
                self.renderer.draw_lobby_background(screen)
                self.renderer.draw_lobby_overlay(screen, self.game_state, audio_muted=self._audio_muted)

            elif self.client_state == "PLAYING":
                self._handle_network_messages()
                server_state = self.round_info.get("state", "PLAYING")
                if server_state == "QUOTA_MET":
                    self.client_state = "QUOTA_MET"
                elif server_state == "ENDING":
                    self.client_state = "ENDING"
                    self._ending_fade_timer = 1.5
                    self.renderer._ending_phase_timer = 0.0
                    self.renderer._ending_stars.clear()
                    for p in self.game_state.get("players", []):
                        if p.get("id") == self.self_id:
                            self._ending_player = dict(p)
                            self._ending_player_x = float(screen.get_width()) / 2.0
                            break
                    self.renderer.start_fade_out(1.5)
                    self._safe_audio("play_music", MusicState.ENDING if _HAS_AUDIO else None)
                elif server_state == "GAME_OVER":
                    self.client_state = "GAME_OVER"
                    self._game_over_lobby_started = False
                    self.renderer.start_fade_out(1.0)
                    self._safe_audio("on_game_over")

                # Per-frame audio updates
                self._safe_audio("update_frame", dt)

                # Siren distance-based volume + scream pulse
                siren_data = None
                for mon in self.game_state.get("monsters", []):
                    if mon.get("type") == "siren":
                        siren_data = mon
                        break
                if siren_data and self.self_id:
                    for p in self.game_state.get("players", []):
                        if p.get("id") == self.self_id:
                            sx, sy = float(siren_data.get("x", 0)), float(siren_data.get("y", 0))
                            px, py = float(p.get("x", 0)), float(p.get("y", 0))
                            siren_dist = ((sx - px) ** 2 + (sy - py) ** 2) ** 0.5
                            # Scream pulse — volume spike when siren screams
                            if siren_data.get("scream_active"):
                                self._safe_audio("update_siren_distance", max(0, siren_dist - 200))
                            else:
                                self._safe_audio("update_siren_distance", siren_dist)
                            break

                # Sanity-driven audio each frame
                if self.self_id and self.self_id in self.sanity_map:
                    self._safe_audio("set_sanity", self.sanity_map[self.self_id] / 100.0)

                # Detect player deaths
                for player in self.game_state.get("players", []):
                    pid = str(player.get("id", ""))
                    alive_now = bool(player.get("alive", True))
                    was_alive = self._prev_alive.get(pid, True)
                    if was_alive and not alive_now:
                        self._safe_audio("on_player_death")
                    self._prev_alive[pid] = alive_now

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

                # Lights-out blackout overlay
                if self._lights_out_timer > 0.0:
                    self._lights_out_timer -= dt
                    blackout = pygame.Surface(screen.get_size(), pygame.SRCALPHA)
                    alpha = min(255, int(255 * (self._lights_out_timer / 1.5)))
                    blackout.fill((0, 0, 0, alpha))
                    screen.blit(blackout, (0, 0))

            elif self.client_state == "QUOTA_MET":
                self._handle_network_messages()
                server_state = self.round_info.get("state", "QUOTA_MET")
                if server_state == "ENDING":
                    self.client_state = "ENDING"
                    self._ending_fade_timer = 1.5
                    self.renderer._ending_phase_timer = 0.0
                    self.renderer._ending_stars.clear()
                    # Save player info for ending scene
                    for p in self.game_state.get("players", []):
                        if p.get("id") == self.self_id:
                            self._ending_player = dict(p)
                            self._ending_player_x = float(screen.get_width()) / 2.0
                            break
                    self.renderer.start_fade_out(1.5)
                    self._safe_audio("play_music", MusicState.ENDING if _HAS_AUDIO else None)
                elif server_state == "GAME_OVER":
                    self.client_state = "GAME_OVER"
                    self._game_over_lobby_started = False
                    self.renderer.start_fade_out(1.0)
                    self._safe_audio("on_game_over")

                # Draw game world with escape ladder visible
                self._update_camera()
                if time_since_input_send >= input_send_interval:
                    self.network.send(self._build_input_message())
                    time_since_input_send -= input_send_interval
                self.renderer.draw(
                    screen,
                    self.camera,
                    self.game_state,
                    self.self_id,
                    facing_map=self.facing_map,
                    sanity_map=self.sanity_map,
                )

            elif self.client_state == "ENDING":
                self._safe_audio("update_frame", dt)
                # Fade to black first, then show rooftop scene
                if self._ending_fade_timer > 0:
                    self._ending_fade_timer -= dt
                    fade_alpha = min(255, int(255 * (1.0 - self._ending_fade_timer / 1.5)))
                    screen.fill((0, 0, 0))
                    fade_overlay = pygame.Surface(screen.get_size(), pygame.SRCALPHA)
                    fade_overlay.fill((0, 0, 0, fade_alpha))
                    screen.blit(fade_overlay, (0, 0))
                else:
                    # Start fade-in on first frame of rooftop scene
                    if self._ending_fade_timer == 0 and not hasattr(self, '_ending_faded_in'):
                        self.renderer.start_fade_in(2.0)
                        self._ending_faded_in = True
                    # Playable rooftop scene
                    sw_end, sh_end = screen.get_size()
                    keys = pygame.key.get_pressed()
                    move_x = 0
                    if keys[pygame.K_a] or keys[pygame.K_LEFT]:
                        move_x -= 1
                    if keys[pygame.K_d] or keys[pygame.K_RIGHT]:
                        move_x += 1
                    speed = 180.0
                    self._ending_player_vx = move_x * speed
                    self._ending_player_x += self._ending_player_vx * dt
                    self._ending_player_x = max(0, min(sw_end - 34, self._ending_player_x))
                    if move_x > 0:
                        self._ending_player_facing = True
                    elif move_x < 0:
                        self._ending_player_facing = False

                    platform_y = int(sh_end * 0.9) - 54
                    ending_data = dict(self._ending_player)
                    ending_data["x"] = self._ending_player_x
                    ending_data["y"] = platform_y
                    ending_data["vx"] = self._ending_player_vx
                    ending_data["facing_right"] = self._ending_player_facing
                    self.renderer.draw_ending_screen(screen, dt, player_data=ending_data)

            elif self.client_state == "GAME_OVER":
                self._safe_audio("update_frame", dt)
                self._handle_network_messages()
                vo_playing = self._safe_audio("is_game_over_playing")
                if not vo_playing and not getattr(self, "_game_over_lobby_started", False):
                    self._game_over_lobby_started = True
                    self._safe_audio("play_music", MusicState.LOBBY if _HAS_AUDIO else None)
                self.renderer.draw_game_over(screen, self.game_state, show_prompt=not vo_playing)

            # Fade-to-game: once fade-out completes, start fade-in
            if self._fade_to_game and self.renderer.is_black():
                self._fade_to_game = False
                self.renderer.start_fade_in(2.0)

            # Draw fade overlay on top of everything
            self.renderer.draw_fade_overlay(screen)

            pygame.display.flip()

        if self._connected:
            self.network.close()
        pygame.quit()
