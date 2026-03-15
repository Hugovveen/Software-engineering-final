"""Pygame renderer for map, players, and mimic entity.

Rendering code is isolated here to keep the main client loop uncluttered.
"""

from __future__ import annotations

from pathlib import Path

import pygame

from rendering.sprite_loader import AnimationPlayer, load_frames


class Renderer:
    """Draws the full frame based on received game state."""

    BG_COLOR = (8, 12, 20)
    PLATFORM_COLOR = (75, 75, 95)
    LADDER_COLOR = (130, 100, 70)
    PLAYER_COLOR = (90, 170, 255)
    SELF_COLOR = (90, 255, 160)
    MIMIC_COLOR = (220, 60, 90)
    WEEPING_ANGEL_COLOR = (220, 220, 230)
    SIREN_COLOR = (120, 200, 255)
    ENTITY_RENDER_SCALE = 5.0
    TILE_SIZE = 64

    def __init__(self) -> None:
        self.assets_loaded = False
        self.animation_sources: dict[str, list[pygame.Surface]] = {}
        self.animation_players: dict[tuple[str, str], AnimationPlayer] = {}
        self.scaled_frames_cache: dict[tuple[str, int, int], list[pygame.Surface]] = {}
        self.facing_by_entity: dict[str, int] = {}
        self.floor_texture: pygame.Surface | None = None
        self.wall_texture: pygame.Surface | None = None
        self.wall_background_cache: dict[tuple[int, int], pygame.Surface] = {}
        self.ui_font: pygame.font.Font | None = None

    def _ensure_ui_font(self) -> pygame.font.Font | None:
        if self.ui_font is None and pygame.font.get_init():
            self.ui_font = pygame.font.SysFont("consolas", 20)
        return self.ui_font

    def _draw_player_status(
        self,
        screen: pygame.Surface,
        camera,
        player: dict,
        is_self: bool,
        font: pygame.font.Font | None,
    ) -> None:
        if font is None:
            return

        player_x = float(player.get("x", 0.0))
        player_y = float(player.get("y", 0.0))
        player_w = int(player.get("w", 0))
        player_h = int(player.get("h", 0))
        charm_level = int(player.get("charm_level", 0))
        charm_timer = float(player.get("charm_timer", 0.0))

        if charm_level > 0:
            sx, sy = camera.world_to_screen(player_x, player_y)
            highlight_color = (255, 110, 200) if is_self else (220, 110, 255)
            pygame.draw.rect(
                screen,
                highlight_color,
                pygame.Rect(int(sx) - 3, int(sy) - 3, player_w + 6, player_h + 6),
                width=2,
            )
            label = f"CHARMED L{charm_level} {charm_timer:.1f}s"
            text = font.render(label, True, highlight_color)
            screen.blit(text, (int(sx), int(sy) - 28))

    def _draw_enemy_status(
        self,
        screen: pygame.Surface,
        camera,
        enemy: dict,
        font: pygame.font.Font | None,
    ) -> None:
        if font is None:
            return

        enemy_state = str(enemy.get("state", "idle")).upper()
        enemy_type = str(enemy.get("type", "enemy"))
        enemy_x = float(enemy.get("x", 0.0))
        enemy_y = float(enemy.get("y", 0.0))

        if enemy_state in {"ATTACKING", "CASTING", "FROZEN"}:
            sx, sy = camera.world_to_screen(enemy_x, enemy_y)
            color = (255, 90, 90)
            if enemy_state == "FROZEN":
                color = (200, 230, 255)
            elif enemy_state == "CASTING":
                color = (120, 225, 255)
            label = f"{enemy_type}:{enemy_state}"
            text = font.render(label, True, color)
            screen.blit(text, (int(sx), int(sy) - 30))

    def _draw_event_feed(self, screen: pygame.Surface, recent_events: list[dict], font: pygame.font.Font | None) -> None:
        if font is None or not recent_events:
            return

        visible_events = recent_events[-6:]
        panel_width = 520
        line_height = 22
        padding = 10
        panel_height = padding * 2 + line_height * len(visible_events)
        screen_width, _ = screen.get_size()
        panel_x = max(0, screen_width - panel_width - 16)
        panel_y = 16

        panel = pygame.Surface((panel_width, panel_height), pygame.SRCALPHA)
        panel.fill((12, 12, 20, 175))
        screen.blit(panel, (panel_x, panel_y))

        y = panel_y + padding
        for event in reversed(visible_events):
            text = font.render(str(event.get("text", "")), True, (235, 235, 240))
            screen.blit(text, (panel_x + padding, y))
            y += line_height

    def _draw_round_hud(self, screen: pygame.Surface, game_state: dict, font: pygame.font.Font | None) -> None:
        if font is None:
            return

        round_info = dict(game_state.get("round", {}))
        state = str(round_info.get("state", "LOBBY"))
        number = int(round_info.get("number", 1))
        time_remaining = float(round_info.get("time_remaining", 0.0))
        min_players = int(round_info.get("min_players", 1))
        current_players = len(game_state.get("players", []))

        lines = [
            f"Round {number} | {state}",
            f"Time: {time_remaining:05.1f}s",
            f"Players: {current_players}/{min_players}+",
        ]

        panel_width = 340
        line_height = 22
        padding = 10
        panel_height = padding * 2 + line_height * len(lines)
        panel = pygame.Surface((panel_width, panel_height), pygame.SRCALPHA)
        panel.fill((12, 12, 20, 175))
        screen.blit(panel, (16, 16))

        y = 16 + padding
        for line in lines:
            text = font.render(line, True, (236, 236, 240))
            screen.blit(text, (26, y))
            y += line_height

        if state in {"LOBBY", "GAME_OVER"}:
            banner_text = "Waiting for players..." if state == "LOBBY" else "Round Over"
            if state == "GAME_OVER":
                reason = round_info.get("end_reason")
                if reason:
                    banner_text = f"Round Over: {reason}"

            banner = font.render(banner_text, True, (255, 230, 180))
            screen_width, _ = screen.get_size()
            banner_rect = banner.get_rect(center=(screen_width // 2, 42))
            bg = pygame.Surface((banner_rect.width + 20, banner_rect.height + 10), pygame.SRCALPHA)
            bg.fill((30, 20, 20, 170))
            bg_rect = bg.get_rect(center=banner_rect.center)
            screen.blit(bg, bg_rect.topleft)
            screen.blit(banner, banner_rect.topleft)

    def _load_first_texture(self, folder: Path) -> pygame.Surface | None:
        if not folder.exists() or not folder.is_dir():
            return None
        image_paths = sorted(
            [
                path
                for path in folder.iterdir()
                if path.is_file() and path.suffix.lower() in {".png", ".jpg", ".jpeg", ".bmp", ".webp"}
            ]
        )
        if not image_paths:
            return None
        return pygame.image.load(str(image_paths[0])).convert_alpha()

    def _load_assets(self) -> None:
        if self.assets_loaded:
            return

        assets_root = Path(__file__).resolve().parents[1] / "assets"
        self.animation_sources = {
            "player_walk": load_frames(assets_root / "player" / "walking"),
            "secondplayer_walk": load_frames(assets_root / "secondplayer" / "walking"),
            "mimic_walk": load_frames(assets_root / "enemies" / "mimic" / "mimic_player" / "walking"),
            "weeping_angel_idle": load_frames(assets_root / "enemies" / "weeping_angel"),
            "siren_float": load_frames(assets_root / "enemies" / "siren" / "floating_anim"),
        }
        self.floor_texture = self._load_first_texture(assets_root / "floor")
        self.wall_texture = self._load_first_texture(assets_root / "wall")
        self.assets_loaded = True

    def _get_enemy_visuals(self, enemy_type: str) -> tuple[str, tuple[int, int, int]]:
        if enemy_type == "mimic":
            return "mimic_walk", self.MIMIC_COLOR
        if enemy_type == "weeping_angel":
            return "weeping_angel_idle", self.WEEPING_ANGEL_COLOR
        if enemy_type == "siren":
            return "siren_float", self.SIREN_COLOR
        return "", self.MIMIC_COLOR

    def _draw_actor(
        self,
        screen: pygame.Surface,
        camera,
        entity_id: str,
        world_x: float,
        world_y: float,
        velocity_x: float,
        width: int,
        height: int,
        animation_key: str,
        fallback_color: tuple[int, int, int],
        dt: float,
    ) -> None:
        screen_x, screen_y = camera.world_to_screen(world_x, world_y)
        facing = self._resolve_facing_direction(entity_id, world_x, velocity_x)

        frame = None
        if animation_key:
            scaled_width, scaled_height = self._get_scaled_entity_size(width, height)
            frame = self._get_entity_frame(
                entity_id=entity_id,
                animation_key=animation_key,
                dt=dt,
                is_moving=abs(velocity_x) > 0.01,
                width=scaled_width,
                height=scaled_height,
            )

        if frame is not None:
            self._draw_entity_frame(
                screen=screen,
                frame=frame,
                world_x=world_x,
                world_y=world_y,
                width=width,
                height=height,
                facing=facing,
                camera=camera,
            )
        else:
            pygame.draw.rect(screen, fallback_color, pygame.Rect(screen_x, screen_y, width, height))

    def _get_scaled_entity_size(self, width: int, height: int) -> tuple[int, int]:
        scaled_width = max(1, int(width * self.ENTITY_RENDER_SCALE))
        scaled_height = max(1, int(height * self.ENTITY_RENDER_SCALE))
        return scaled_width, scaled_height

    def _draw_tiled_world_rect(
        self,
        screen: pygame.Surface,
        camera,
        texture: pygame.Surface,
        x: int,
        y: int,
        width: int,
        height: int,
    ) -> None:
        tile_surface = pygame.transform.scale(texture, (self.TILE_SIZE, self.TILE_SIZE))
        sx, sy = camera.world_to_screen(x, y)
        tile_start_x = int(sx)
        tile_start_y = int(sy)
        tile_end_x = tile_start_x + int(width)
        tile_end_y = tile_start_y + int(height)

        for draw_y in range(tile_start_y, tile_end_y, self.TILE_SIZE):
            for draw_x in range(tile_start_x, tile_end_x, self.TILE_SIZE):
                screen.blit(tile_surface, (draw_x, draw_y))

    def _get_wall_background(self, world_width: int, world_height: int) -> pygame.Surface | None:
        if self.wall_texture is None:
            return None

        cache_key = (world_width, world_height)
        if cache_key in self.wall_background_cache:
            return self.wall_background_cache[cache_key]

        background = pygame.transform.scale(self.wall_texture, (world_width, world_height))
        self.wall_background_cache[cache_key] = background
        return background

    def _estimate_world_size(self, map_data: dict, screen: pygame.Surface) -> tuple[int, int]:
        max_x = 0
        max_y = 0

        for x, y, width, height in map_data.get("platforms", []):
            max_x = max(max_x, int(x + width))
            max_y = max(max_y, int(y + height))

        for x, y, width, height in map_data.get("ladders", []):
            max_x = max(max_x, int(x + width))
            max_y = max(max_y, int(y + height))

        screen_width, screen_height = screen.get_size()
        world_width = max(max_x, screen_width)
        world_height = max(max_y, screen_height)
        return world_width, world_height

    def _draw_wall_background(self, screen: pygame.Surface, camera, map_data: dict) -> None:
        world_width, world_height = self._estimate_world_size(map_data, screen)
        background = self._get_wall_background(world_width, world_height)
        if background is None:
            return

        draw_x, draw_y = camera.world_to_screen(0, 0)
        screen.blit(background, (int(draw_x), int(draw_y)))

    def _draw_entity_frame(
        self,
        screen: pygame.Surface,
        frame: pygame.Surface,
        world_x: float,
        world_y: float,
        width: int,
        height: int,
        facing: int,
        camera,
    ) -> None:
        frame_to_draw = frame
        if facing < 0:
            frame_to_draw = pygame.transform.flip(frame_to_draw, True, False)

        scaled_width, scaled_height = self._get_scaled_entity_size(width, height)
        screen_x, screen_y = camera.world_to_screen(world_x, world_y)

        draw_x = int(screen_x - (scaled_width - width) / 2)
        draw_y = int(screen_y - (scaled_height - height))
        screen.blit(frame_to_draw, (draw_x, draw_y))

    def _get_scaled_frames(self, animation_key: str, width: int, height: int) -> list[pygame.Surface]:
        cache_key = (animation_key, int(width), int(height))
        if cache_key in self.scaled_frames_cache:
            return self.scaled_frames_cache[cache_key]

        source_frames = self.animation_sources.get(animation_key, [])
        if not source_frames:
            self.scaled_frames_cache[cache_key] = []
            return []

        scaled_frames = [
            pygame.transform.scale(frame, (int(width), int(height)))
            for frame in source_frames
        ]
        self.scaled_frames_cache[cache_key] = scaled_frames
        return scaled_frames

    def _get_entity_frame(
        self,
        entity_id: str,
        animation_key: str,
        dt: float,
        is_moving: bool,
        width: int,
        height: int,
    ) -> pygame.Surface | None:
        frames = self._get_scaled_frames(animation_key, width, height)
        if not frames:
            return None

        player_key = (entity_id, animation_key)
        animation = self.animation_players.get(player_key)
        if animation is None or animation.frames is not frames:
            animation = AnimationPlayer(frames, fps=10.0, loop=True)
            self.animation_players[player_key] = animation

        if is_moving:
            animation.update(dt)
            return animation.current_frame()
        return animation.frames[0]

    def _resolve_facing_direction(self, entity_id: str, x: float, vx: float) -> int:
        previous_facing = self.facing_by_entity.get(entity_id, 1)
        if vx > 0.01:
            self.facing_by_entity[entity_id] = 1
        elif vx < -0.01:
            self.facing_by_entity[entity_id] = -1
        else:
            self.facing_by_entity[entity_id] = previous_facing
        return self.facing_by_entity[entity_id]

    def draw(
        self,
        screen: pygame.Surface,
        camera,
        game_state: dict,
        self_id: str | None,
        dt: float,
        recent_events: list[dict] | None = None,
    ) -> None:
        """Render world and entities from the latest game state snapshot."""
        self._load_assets()
        screen.fill(self.BG_COLOR)
        if recent_events is None:
            recent_events = []

        map_data = game_state.get("map", {})
        self._draw_wall_background(screen, camera, map_data)
        for x, y, w, h in map_data.get("platforms", []):
            if self.floor_texture is not None:
                self._draw_tiled_world_rect(screen, camera, self.floor_texture, int(x), int(y), int(w), int(h))
            else:
                sx, sy = camera.world_to_screen(x, y)
                pygame.draw.rect(screen, self.PLATFORM_COLOR, pygame.Rect(sx, sy, w, h))

        for x, y, w, h in map_data.get("ladders", []):
            sx, sy = camera.world_to_screen(x, y)
            pygame.draw.rect(screen, self.LADDER_COLOR, pygame.Rect(sx, sy, w, h))

        for player in game_state.get("players", []):
            color = self.SELF_COLOR if player.get("id") == self_id else self.PLAYER_COLOR
            player_id = str(player.get("id", "unknown-player"))
            player_vx = float(player.get("vx", 0.0))
            player_w = int(player.get("w", 0))
            player_h = int(player.get("h", 0))

            animation_key = "player_walk" if player.get("id") == self_id else "secondplayer_walk"
            self._draw_actor(
                screen=screen,
                camera=camera,
                entity_id=player_id,
                world_x=float(player.get("x", 0.0)),
                world_y=float(player.get("y", 0.0)),
                velocity_x=player_vx,
                width=player_w,
                height=player_h,
                animation_key=animation_key,
                fallback_color=color,
                dt=dt,
            )

        enemies = list(game_state.get("enemies", []))
        if enemies:
            for enemy in enemies:
                enemy_type = str(enemy.get("type", ""))
                enemy_id = str(enemy.get("id", enemy_type or "enemy"))
                enemy_vx = float(enemy.get("vx", 0.0))
                enemy_w = int(enemy.get("w", 0))
                enemy_h = int(enemy.get("h", 0))
                animation_key, fallback_color = self._get_enemy_visuals(enemy_type)
                self._draw_actor(
                    screen=screen,
                    camera=camera,
                    entity_id=enemy_id,
                    world_x=float(enemy.get("x", 0.0)),
                    world_y=float(enemy.get("y", 0.0)),
                    velocity_x=enemy_vx,
                    width=enemy_w,
                    height=enemy_h,
                    animation_key=animation_key,
                    fallback_color=fallback_color,
                    dt=dt,
                )
        else:
            mimic = game_state.get("mimic")
            if mimic:
                self._draw_actor(
                    screen=screen,
                    camera=camera,
                    entity_id=str(mimic.get("id", "mimic")),
                    world_x=float(mimic.get("x", 0.0)),
                    world_y=float(mimic.get("y", 0.0)),
                    velocity_x=float(mimic.get("vx", 0.0)),
                    width=int(mimic.get("w", 0)),
                    height=int(mimic.get("h", 0)),
                    animation_key="mimic_walk",
                    fallback_color=self.MIMIC_COLOR,
                    dt=dt,
                )

        ui_font = self._ensure_ui_font()
        self._draw_round_hud(screen, game_state, ui_font)
        for player in game_state.get("players", []):
            self._draw_player_status(screen, camera, player, player.get("id") == self_id, ui_font)
        for enemy in enemies:
            self._draw_enemy_status(screen, camera, enemy, ui_font)
        self._draw_event_feed(screen, recent_events, ui_font)

        pygame.display.flip()
