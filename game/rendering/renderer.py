"""Pygame renderer for map, players, mimic, and monster entities.

Rendering code is isolated here to keep the main client loop uncluttered.
"""

from __future__ import annotations

import math
import random
import time
from pathlib import Path

import pygame

from config import LOOT_PICKUP_RADIUS
from rendering.lighting import LightingSystem
from rendering.sprite_loader import AnimationPlayer, load_frames


class Renderer:
    """Draws the full frame based on received game state."""

    BG_COLOR      = (8,   12,  20)
    PLATFORM_COLOR = (75,  75,  95)
    LADDER_COLOR  = (130, 100, 70)
    PLAYER_COLOR  = (90,  170, 255)
    SELF_COLOR    = (90,  255, 160)
    MIMIC_COLOR   = (220, 60,  90)
    SIREN_COLOR   = (160, 80,  200)
    ANGEL_COLOR   = (180, 175, 170)
    LOOT_COLOR    = (255, 208, 80)
    EXTRACTION_COLOR = (80, 220, 140)
    HUD_BG        = (10,  10,  20,  180)
    ENTITY_RENDER_SCALE = 1.15
    PLAYER_SPRITE_SCALE = 2.6
    ENEMY_SPRITE_SCALE = PLAYER_SPRITE_SCALE
    INTERACT_PROMPT_BG = (12, 14, 24, 205)
    INTERACT_PROMPT_COLOR = (250, 246, 220)

    def __init__(self, screen_width: int, screen_height: int) -> None:
        # Lighting system
        self.lighting = LightingSystem(screen_width, screen_height)
        self._screen_width = screen_width
        self._screen_height = screen_height
        self._font    = None   # lazy init after pygame.init()
        self._assets_loaded = False
        self._wall_surface: pygame.Surface | None = None
        self._ground_floor_surface: pygame.Surface | None = None
        self._basement_floor_surface: pygame.Surface | None = None
        self._loot_surfaces: list[pygame.Surface] = []
        self._player_frames: list[pygame.Surface] = []
        self._skin_frames: dict[str, list[pygame.Surface]] = {}
        self._player_animation: dict[str, AnimationPlayer] = {}
        self._enemy_frames: dict[str, list[pygame.Surface]] = {}
        self._enemy_animation: dict[str, AnimationPlayer] = {}
        self._scaled_player_frame_cache: dict[tuple[int, int], list[pygame.Surface]] = {}
        self._scaled_skin_frame_cache: dict[tuple[str, int, int], list[pygame.Surface]] = {}
        self._scaled_enemy_frame_cache: dict[tuple[str, int, int], list[pygame.Surface]] = {}
        self._scaled_floor_cache: dict[tuple[str, int, int], pygame.Surface] = {}
        self._scaled_loot_cache: dict[tuple[int, int, int], pygame.Surface] = {}
        self._screen_image_cache: dict[str, pygame.Surface] = {}
        self._char_preview_cache: dict[str, pygame.Surface] = {}
        self._stairs_surface: pygame.Surface | None = None
        self._scaled_stairs_cache: dict[tuple[int, int], pygame.Surface] = {}
        self._death_particles: dict[str, list[dict]] = {}
        self._death_finished: set[str] = set()
        # Falling stars background effect
        self._falling_stars: list[dict] = []
        self._star_spawn_timer: float = 0.0
        # Ending screen state
        self._ending_fade_timer: float = 0.0
        self._ending_phase_timer: float = 0.0
        self._ending_stars: list[dict] = []
        self._ending_star_timer: float = 0.0
        self._ending_started: bool = False
        # Quota met state tracking
        self._quota_met: bool = False
        self._quota_met_flash_timer: float = 0.0
        # Game elapsed timer (for flashlight hint)
        self._game_elapsed: float = 0.0
        # Fade overlay system
        self._fade_alpha: float = 0.0  # 0=transparent, 255=black
        self._fade_speed: float = 0.0  # alpha change per second (negative = fading in)

    def _get_font(self, size: int = 14) -> pygame.font.Font:
        """Lazy-load a monospace font."""
        if self._font is None:
            self._font = pygame.font.SysFont("monospace", size)
        return self._font

    def _load_assets(self) -> None:
        if self._assets_loaded:
            return

        assets_root = Path(__file__).resolve().parents[1] / "assets"
        wall_dir = assets_root / "wall"
        floor_dir = assets_root / "floor"
        loot_dir = assets_root / "loot"
        enemy_root = assets_root / "enemies"
        player_walk_dir = assets_root / "player" / "walking"

        if wall_dir.exists():
            wall_images = sorted(
                [
                    p
                    for p in wall_dir.iterdir()
                    if p.is_file() and p.suffix.lower() in {".png", ".jpg", ".jpeg", ".bmp", ".webp"}
                ]
            )
            if wall_images:
                self._wall_surface = pygame.image.load(str(wall_images[0])).convert_alpha()

        if floor_dir.exists():
            floor_images = sorted(
                [
                    p
                    for p in floor_dir.iterdir()
                    if p.is_file() and p.suffix.lower() in {".png", ".jpg", ".jpeg", ".bmp", ".webp"}
                ]
            )

            ground_candidate = floor_dir / "groundfloor.png"
            basement_candidate = floor_dir / "basementfloor.png"

            if ground_candidate.exists():
                self._ground_floor_surface = pygame.image.load(str(ground_candidate)).convert_alpha()
            elif floor_images:
                self._ground_floor_surface = pygame.image.load(str(floor_images[0])).convert_alpha()

            if basement_candidate.exists():
                self._basement_floor_surface = pygame.image.load(str(basement_candidate)).convert_alpha()
            elif len(floor_images) >= 2:
                self._basement_floor_surface = pygame.image.load(str(floor_images[1])).convert_alpha()
            elif self._ground_floor_surface is not None:
                self._basement_floor_surface = self._ground_floor_surface

        if loot_dir.exists():
            loot_images = sorted(
                [
                    p
                    for p in loot_dir.iterdir()
                    if p.is_file() and p.suffix.lower() in {".png", ".jpg", ".jpeg", ".bmp", ".webp"}
                ]
            )
            self._loot_surfaces = [pygame.image.load(str(path)).convert_alpha() for path in loot_images]
            print(f"[RENDERER] Loaded {len(self._loot_surfaces)} loot variants: {[p.name for p in loot_images]}")

        self._enemy_frames["mimic"] = load_frames(enemy_root / "mimic" / "mimic_player" / "walking")
        self._enemy_frames["siren_idle"] = load_frames(enemy_root / "siren" / "floating_anim")
        self._enemy_frames["siren_cast"] = load_frames(enemy_root / "siren" / "casting_spell")
        self._enemy_frames["angel"] = load_frames(enemy_root / "weeping_angel" / "weeping_show")

        siren_idle_still = enemy_root / "siren" / "idle.png"
        if not self._enemy_frames["siren_idle"] and siren_idle_still.exists():
            self._enemy_frames["siren_idle"] = [pygame.image.load(str(siren_idle_still)).convert_alpha()]

        angel_idle_still = enemy_root / "weeping_angel" / "idle.png"
        if not self._enemy_frames["angel"] and angel_idle_still.exists():
            self._enemy_frames["angel"] = [pygame.image.load(str(angel_idle_still)).convert_alpha()]

        stairs_path = assets_root / "stairs" / "stairs.png"
        if stairs_path.exists():
            self._stairs_surface = pygame.image.load(str(stairs_path)).convert_alpha()

        self._player_frames = load_frames(player_walk_dir)
        self._skin_frames["researcher"] = self._player_frames
        student_raw = load_frames(assets_root / "secondplayer" / "walking")
        self._skin_frames["student"] = [
            pygame.transform.flip(frame, True, False) for frame in student_raw
        ]
        self._assets_loaded = True

    def _get_scaled_player_frames(self, target_w: int, target_h: int) -> list[pygame.Surface]:
        cache_key = (target_w, target_h)
        if cache_key in self._scaled_player_frame_cache:
            return self._scaled_player_frame_cache[cache_key]

        if not self._player_frames:
            self._scaled_player_frame_cache[cache_key] = []
            return []

        scaled = [pygame.transform.scale(frame, (target_w, target_h)) for frame in self._player_frames]
        self._scaled_player_frame_cache[cache_key] = scaled
        return scaled

    def _get_scaled_skin_frames(self, skin: str, target_w: int, target_h: int) -> list[pygame.Surface]:
        cache_key = (skin, target_w, target_h)
        if cache_key in self._scaled_skin_frame_cache:
            return self._scaled_skin_frame_cache[cache_key]
        source = self._skin_frames.get(skin, self._player_frames)
        if not source:
            self._scaled_skin_frame_cache[cache_key] = []
            return []
        scaled = [pygame.transform.scale(f, (target_w, target_h)) for f in source]
        self._scaled_skin_frame_cache[cache_key] = scaled
        return scaled

    def _get_scaled_enemy_frames(self, sprite_key: str, target_w: int, target_h: int) -> list[pygame.Surface]:
        cache_key = (sprite_key, target_w, target_h)
        if cache_key in self._scaled_enemy_frame_cache:
            return self._scaled_enemy_frame_cache[cache_key]

        source_frames = self._enemy_frames.get(sprite_key, [])
        if not source_frames:
            self._scaled_enemy_frame_cache[cache_key] = []
            return []

        scaled = [pygame.transform.scale(frame, (target_w, target_h)) for frame in source_frames]
        self._scaled_enemy_frame_cache[cache_key] = scaled
        return scaled

    def _draw_enemy_sprite(
        self,
        screen: pygame.Surface,
        draw_rect: pygame.Rect,
        entity_id: str,
        sprite_key: str,
        facing_right: bool = True,
        fps: float = 10.0,
    ) -> bool:
        frames = self._get_scaled_enemy_frames(sprite_key, draw_rect.w, draw_rect.h)
        if not frames:
            return False

        animation_key = f"{entity_id}:{sprite_key}"
        animation = self._enemy_animation.get(animation_key)
        if animation is None or animation.frames is not frames:
            animation = AnimationPlayer(frames, fps=fps, loop=True)
            self._enemy_animation[animation_key] = animation

        animation.update(1.0 / 60.0)
        frame = animation.current_frame()
        if frame is None:
            return False

        if not facing_right:
            frame = pygame.transform.flip(frame, True, False)

        screen.blit(frame, draw_rect.topleft)
        return True

    def _draw_enemy_sprite_frozen(
        self,
        screen: pygame.Surface,
        draw_rect: pygame.Rect,
        sprite_key: str,
        facing_right: bool = True,
    ) -> bool:
        """Draw frame 0 of an enemy sprite without advancing animation."""
        frames = self._get_scaled_enemy_frames(sprite_key, draw_rect.w, draw_rect.h)
        if not frames:
            return False
        frame = frames[0]
        if not facing_right:
            frame = pygame.transform.flip(frame, True, False)
        screen.blit(frame, draw_rect.topleft)
        return True

    def _draw_background(self, screen: pygame.Surface, camera) -> None:
        if self._wall_surface is None:
            return
        sx, sy = camera.world_to_screen(0, 0)
        screen.blit(self._wall_surface, (int(sx), int(sy)))

    def _get_scaled_floor_surface(self, texture_kind: str, width: int, height: int) -> pygame.Surface | None:
        source: pygame.Surface | None
        if texture_kind == "basement":
            source = self._basement_floor_surface
        else:
            source = self._ground_floor_surface

        if source is None:
            return None

        cache_key = (texture_kind, width, height)
        cached = self._scaled_floor_cache.get(cache_key)
        if cached is not None:
            return cached

        scaled = pygame.transform.scale(source, (width, height))
        self._scaled_floor_cache[cache_key] = scaled
        return scaled

    def _draw_platforms(self, screen: pygame.Surface, camera, platforms: list) -> None:
        if not platforms:
            return

        has_textures = self._ground_floor_surface is not None or self._basement_floor_surface is not None
        if not has_textures:
            for x, y, w, h in platforms:
                sx, sy = camera.world_to_screen(x, y)
                pygame.draw.rect(screen, self.PLATFORM_COLOR, pygame.Rect(sx, sy, w, h))
            return

        basement_row_y = max(float(y) for _x, y, _w, _h in platforms)

        for x, y, w, h in platforms:
            sx, sy = camera.world_to_screen(x, y)
            tile_size = max(1, int(h))
            texture_kind = "basement" if float(y) >= basement_row_y else "ground"

            for offset_x in range(0, int(w), tile_size):
                draw_w = min(tile_size, int(w) - offset_x)
                texture = self._get_scaled_floor_surface(texture_kind, draw_w, int(h))
                if texture is not None:
                    screen.blit(texture, (int(sx) + offset_x, int(sy)))
                else:
                    pygame.draw.rect(
                        screen,
                        self.PLATFORM_COLOR,
                        pygame.Rect(int(sx) + offset_x, int(sy), draw_w, int(h)),
                    )

    def _spawn_death_particles(self, player_id: str, cx: float, cy: float) -> None:
        particles = []
        for i in range(12):
            angle = (i / 12.0) * math.pi * 2
            speed = random.uniform(60.0, 140.0)
            color = random.choice([(220, 50, 30), (255, 120, 30), (255, 80, 20), (200, 40, 40)])
            particles.append({
                "x": cx, "y": cy,
                "vx": math.cos(angle) * speed,
                "vy": math.sin(angle) * speed - 40.0,
                "life": 0.8,
                "max_life": 0.8,
                "radius": random.randint(3, 6),
                "color": color,
            })
        self._death_particles[player_id] = particles

    def _update_and_draw_death_particles(self, screen: pygame.Surface, player_id: str, dt: float) -> bool:
        particles = self._death_particles.get(player_id)
        if not particles:
            return False
        alive = []
        for p in particles:
            p["life"] -= dt
            if p["life"] <= 0:
                continue
            p["x"] += p["vx"] * dt
            p["y"] += p["vy"] * dt
            p["vy"] += 120.0 * dt
            alpha = max(0, min(255, int(255 * (p["life"] / p["max_life"]))))
            radius = max(1, int(p["radius"] * (p["life"] / p["max_life"])))
            s = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
            pygame.draw.circle(s, (*p["color"], alpha), (radius, radius), radius)
            screen.blit(s, (int(p["x"]) - radius, int(p["y"]) - radius))
            alive.append(p)
        self._death_particles[player_id] = alive
        return len(alive) > 0

    def _draw_player(self, screen: pygame.Surface, camera, player: dict, is_self: bool, facing_right: bool) -> None:
        px = float(player.get("x", 0.0))
        py = float(player.get("y", 0.0))
        pw = int(player.get("w", 30))
        ph = int(player.get("h", 48))
        vx = float(player.get("vx", 0.0))
        player_id = str(player.get("id", "player"))
        skin = str(player.get("skin", "researcher"))
        is_dead = not player.get("alive", True)
        sx, sy = camera.world_to_screen(px, py)

        if is_dead:
            center_sx = sx + pw * 0.5
            center_sy = sy + ph * 0.5
            # Start particle burst on first dead frame
            if player_id not in self._death_particles and player_id not in self._death_finished:
                self._spawn_death_particles(player_id, center_sx, center_sy)
            # Draw active particles
            if player_id in self._death_particles:
                still_alive = self._update_and_draw_death_particles(screen, player_id, 1.0 / 60.0)
                if not still_alive:
                    del self._death_particles[player_id]
                    self._death_finished.add(player_id)
                return
            # After particles finish — draw collapsed silhouette
            sil_w = int(pw * 1.4)
            sil_h = int(ph * 0.25)
            sil_rect = pygame.Rect(int(sx + pw // 2 - sil_w // 2), int(sy + ph - sil_h), sil_w, sil_h)
            sil = pygame.Surface((sil_w, sil_h), pygame.SRCALPHA)
            pygame.draw.ellipse(sil, (50, 20, 20, 180), sil.get_rect())
            screen.blit(sil, sil_rect.topleft)
            return

        # Clear death state if player is alive again (respawn)
        self._death_particles.pop(player_id, None)
        self._death_finished.discard(player_id)

        base_scale = self.PLAYER_SPRITE_SCALE * self.ENTITY_RENDER_SCALE
        draw_w = max(1, int(pw * base_scale))
        draw_h = max(1, int(ph * base_scale))
        # Student skin is shorter (85% height)
        if skin == "student":
            draw_h = max(1, int(draw_h * 0.85))
        frames = self._get_scaled_skin_frames(skin, draw_w, draw_h)
        frame: pygame.Surface | None = None

        if frames:
            anim_key = f"{player_id}:{skin}"
            anim = self._player_animation.get(anim_key)
            if anim is None or anim.frames is not frames:
                anim = AnimationPlayer(frames, fps=10.0, loop=True)
                self._player_animation[anim_key] = anim

            if abs(vx) > 0.01:
                anim.update(1.0 / 60.0)
            frame = anim.current_frame()

        if frame is not None:
            if not facing_right:
                frame = pygame.transform.flip(frame, True, False)
            draw_x = int(sx - (draw_w - pw) / 2)
            draw_y = int(sy - (draw_h - ph))
            screen.blit(frame, (draw_x, draw_y))
            # Spawn flash — brief white outline when mimic first appears
            if player.get("spawn_flash"):
                outline_rect = pygame.Rect(draw_x - 2, draw_y - 2, draw_w + 4, draw_h + 4)
                pygame.draw.rect(screen, (255, 255, 255, 200), outline_rect, 2)
        else:
            color = self.SELF_COLOR if is_self else self.PLAYER_COLOR
            draw_rect = self._scaled_entity_rect(sx, sy, pw, ph)
            pygame.draw.rect(screen, color, draw_rect)

    def _draw_extraction_zone(self, screen: pygame.Surface, camera, extraction_zone) -> None:
        if extraction_zone is None:
            return
        if len(extraction_zone) != 4:
            return
        zone_x, zone_y, zone_w, zone_h = extraction_zone
        sx, sy = camera.world_to_screen(zone_x, zone_y)
        zone_rect = pygame.Rect(int(sx), int(sy), int(zone_w), int(zone_h))

        fill = pygame.Surface((zone_rect.w, zone_rect.h), pygame.SRCALPHA)
        fill.fill((*self.EXTRACTION_COLOR, 55))
        screen.blit(fill, (zone_rect.x, zone_rect.y))
        pygame.draw.rect(screen, self.EXTRACTION_COLOR, zone_rect, 2)

    def _draw_loot(self, screen: pygame.Surface, camera, loot_items: list[dict]) -> None:
        has_loot_assets = len(self._loot_surfaces) > 0
        for loot in loot_items:
            sx, sy = camera.world_to_screen(float(loot.get("x", 0.0)), float(loot.get("y", 0.0)))
            loot_w = max(56, int(loot.get("w", 18)))
            loot_h = max(56, int(loot.get("h", 18)))
            loot_rect = pygame.Rect(int(sx), int(sy), loot_w, loot_h)

            if has_loot_assets:
                loot_id = str(loot.get("id", "loot"))
                variant_index = self._loot_variant_index(loot_id)
                scaled_sprite = self._get_scaled_loot_surface(variant_index, loot_w, loot_h)
                if scaled_sprite is not None:
                    screen.blit(scaled_sprite, loot_rect.topleft)
                    continue

            # Glow ring for visibility in dark environments
            glow_size = loot_w + 32
            glow = pygame.Surface((glow_size, glow_size), pygame.SRCALPHA)
            pygame.draw.circle(glow, (255, 210, 60, 45), (glow_size // 2, glow_size // 2), glow_size // 2)
            screen.blit(glow, (loot_rect.centerx - glow_size // 2, loot_rect.centery - glow_size // 2))

            pygame.draw.rect(screen, (255, 215, 80), loot_rect, border_radius=5)
            pygame.draw.rect(screen, (180, 140, 40), loot_rect, 1, border_radius=5)

    def _loot_variant_index(self, loot_id: str) -> int:
        if not self._loot_surfaces:
            return 0
        return hash(loot_id) % len(self._loot_surfaces)

    def _get_scaled_loot_surface(self, variant_index: int, width: int, height: int) -> pygame.Surface | None:
        if not self._loot_surfaces:
            return None

        safe_index = max(0, min(variant_index, len(self._loot_surfaces) - 1))
        cache_key = (safe_index, width, height)
        cached = self._scaled_loot_cache.get(cache_key)
        if cached is not None:
            return cached

        source = self._loot_surfaces[safe_index]
        scaled = pygame.transform.scale(source, (max(1, width), max(1, height)))
        self._scaled_loot_cache[cache_key] = scaled
        return scaled

    def _player_center(self, player: dict) -> tuple[float, float]:
        px = float(player.get("x", 0.0))
        py = float(player.get("y", 0.0))
        pw = float(player.get("w", 0.0))
        ph = float(player.get("h", 0.0))
        return px + pw * 0.5, py + ph * 0.5

    def _is_in_extraction_zone(self, player: dict, extraction_zone) -> bool:
        if extraction_zone is None or len(extraction_zone) != 4:
            return False

        zone_x, zone_y, zone_w, zone_h = (float(extraction_zone[0]), float(extraction_zone[1]), float(extraction_zone[2]), float(extraction_zone[3]))
        player_left = float(player.get("x", 0.0))
        player_top = float(player.get("y", 0.0))
        player_w = float(player.get("w", 0.0))
        player_h = float(player.get("h", 0.0))
        player_right = player_left + player_w
        player_bottom = player_top + player_h

        zone_right = zone_x + zone_w
        zone_bottom = zone_y + zone_h
        return not (
            player_right <= zone_x
            or player_left >= zone_right
            or player_bottom <= zone_y
            or player_top >= zone_bottom
        )

    def _nearest_loot_distance(self, player: dict, loot_items: list[dict]) -> float | None:
        if not loot_items:
            return None
        center_x, center_y = self._player_center(player)
        nearest: float | None = None
        for loot in loot_items:
            lx = float(loot.get("x", 0.0))
            ly = float(loot.get("y", 0.0))
            distance = math.hypot(lx - center_x, ly - center_y)
            if nearest is None or distance < nearest:
                nearest = distance
        return nearest

    def _draw_interaction_prompt(self, screen: pygame.Surface, prompt_text: str | None) -> None:
        if not prompt_text:
            return

        font = self._get_font(18)
        text_surface = font.render(prompt_text, True, self.INTERACT_PROMPT_COLOR)
        padding_x = 14
        padding_y = 10
        panel = pygame.Surface((text_surface.get_width() + padding_x * 2, text_surface.get_height() + padding_y * 2), pygame.SRCALPHA)
        panel.fill(self.INTERACT_PROMPT_BG)

        sw, sh = screen.get_size()
        panel_x = (sw - panel.get_width()) // 2
        panel_y = sh - panel.get_height() - 28
        screen.blit(panel, (panel_x, panel_y))
        screen.blit(text_surface, (panel_x + padding_x, panel_y + padding_y))

    def _scaled_entity_rect(
        self,
        sx: float,
        sy: float,
        width: int,
        height: int,
        scale: float | None = None,
    ) -> pygame.Rect:
        effective_scale = float(scale) if scale is not None else self.ENTITY_RENDER_SCALE
        draw_w = max(1, int(width * effective_scale))
        draw_h = max(1, int(height * effective_scale))
        draw_x = int(sx - (draw_w - width) / 2)
        draw_y = int(sy - (draw_h - height))
        return pygame.Rect(draw_x, draw_y, draw_w, draw_h)

    # ------------------------------------------------------------------
    # Falling stars background effect
    # ------------------------------------------------------------------

    def _draw_falling_stars(self, screen: pygame.Surface, dt: float) -> None:
        """Draw subtle falling star streaks in the background."""
        sw, sh = screen.get_size()

        # Spawn new stars every 3-4 seconds
        self._star_spawn_timer += dt
        if self._star_spawn_timer >= random.uniform(3.0, 4.0):
            self._star_spawn_timer = 0.0
            for _ in range(random.randint(2, 3)):
                self._falling_stars.append({
                    "x": random.uniform(0, sw),
                    "y": random.uniform(-20, sh * 0.3),
                    "speed": random.uniform(30.0, 80.0),
                    "angle": random.uniform(1.2, 1.6),  # mostly downward, slight diagonal
                    "life": random.uniform(2.0, 4.0),
                    "max_life": 0.0,  # set below
                    "color": random.choice([(255, 255, 255), (200, 220, 255), (220, 230, 255)]),
                })
                self._falling_stars[-1]["max_life"] = self._falling_stars[-1]["life"]

        alive = []
        for star in self._falling_stars:
            star["life"] -= dt
            if star["life"] <= 0:
                continue
            dx = math.cos(star["angle"]) * star["speed"] * dt
            dy = math.sin(star["angle"]) * star["speed"] * dt
            star["x"] += dx
            star["y"] += dy

            frac = star["life"] / star["max_life"]
            alpha = int(140 * frac)
            trail_len = int(star["speed"] * 0.15)

            # Draw trail
            end_x = star["x"] - math.cos(star["angle"]) * trail_len
            end_y = star["y"] - math.sin(star["angle"]) * trail_len
            trail_surf = pygame.Surface((sw, sh), pygame.SRCALPHA)
            pygame.draw.line(
                trail_surf,
                (*star["color"], alpha // 2),
                (int(end_x), int(end_y)),
                (int(star["x"]), int(star["y"])),
                1,
            )
            screen.blit(trail_surf, (0, 0))

            # Draw dot
            dot_surf = pygame.Surface((4, 4), pygame.SRCALPHA)
            pygame.draw.circle(dot_surf, (*star["color"], alpha), (2, 2), 2)
            screen.blit(dot_surf, (int(star["x"]) - 2, int(star["y"]) - 2))
            alive.append(star)

        self._falling_stars = alive

    # ------------------------------------------------------------------
    # Main draw call
    # ------------------------------------------------------------------

    def draw(
        self,
        screen: pygame.Surface,
        camera,
        game_state: dict,
        self_id: str | None,
        facing_map: dict | None = None,
        sanity_map: dict | None = None,
        enable_lighting: bool = True,
        skip_wall: bool = False,
    ) -> None:
        """Render world and entities from the latest game state snapshot.

        Args:
            screen:     Main pygame surface.
            camera:     Hugo's Camera object.
            game_state: Latest GAME_STATE dict from server.
            self_id:    Local player's id.
            facing_map: {player_id: bool} facing direction (client-local).
            sanity_map: {player_id: float} sanity values from GAME_STATE.
        """
        sanity_map  = sanity_map  or {}
        facing_map  = facing_map  or {}
        self._load_assets()
        is_night    = game_state.get("quota", {}).get("is_night", False)

        # --- Sanity screen shake ---
        my_sanity   = sanity_map.get(self_id, 100.0) if self_id else 100.0
        effects     = {}
        if self_id:
            effects = self._sanity_effects(my_sanity)
            if effects.get("shake_x") or effects.get("shake_y"):
                # Offset entire draw by shake amount
                orig_offset = (camera.offset_x, 0)
                camera.offset_x -= effects["shake_x"]

        # --- World ---
        if not skip_wall:
            screen.fill(self.BG_COLOR)
            # Falling stars behind everything
            self._draw_falling_stars(screen, 1.0 / 60.0)
            self._draw_background(screen, camera)

        map_data = game_state.get("map", {})
        self._draw_platforms(screen, camera, map_data.get("platforms", []))
        self._draw_extraction_zone(screen, camera, map_data.get("extraction_zone"))
        self._draw_loot(screen, camera, list(game_state.get("loot", [])))

        for x, y, w, h in map_data.get("ladders", []):
            sx, sy = camera.world_to_screen(x, y)
            if self._stairs_surface is not None:
                cache_key = (int(w), int(h))
                if cache_key not in self._scaled_stairs_cache:
                    self._scaled_stairs_cache[cache_key] = pygame.transform.scale(
                        self._stairs_surface, cache_key
                    )
                screen.blit(self._scaled_stairs_cache[cache_key], (sx, sy))
            else:
                pygame.draw.rect(screen, self.LADDER_COLOR, pygame.Rect(sx, sy, w, h))

        # --- DEPOSIT HERE label on extraction zone ---
        extraction_zone = map_data.get("extraction_zone")
        if extraction_zone and len(extraction_zone) == 4:
            ez_x, ez_y, ez_w, ez_h = extraction_zone
            dsx, dsy = camera.world_to_screen(ez_x, ez_y)
            deposit_font = pygame.font.SysFont("monospace", 12)
            deposit_surf = deposit_font.render("DEPOSIT HERE [E]", True, (80, 220, 140))
            deposit_bg = pygame.Surface((deposit_surf.get_width() + 8, deposit_surf.get_height() + 4), pygame.SRCALPHA)
            deposit_bg.fill((0, 0, 0, 100))
            label_x = int(dsx) + int(ez_w) // 2 - deposit_bg.get_width() // 2
            label_y = int(dsy) - deposit_bg.get_height() - 4
            screen.blit(deposit_bg, (label_x, label_y))
            screen.blit(deposit_surf, (label_x + 4, label_y + 2))

        # --- Escape ladder hint (visible after quota met) ---
        round_state = game_state.get("round", {}).get("state", "")
        escape_ladder = map_data.get("escape_ladder")
        if round_state in ("QUOTA_MET", "ENDING") and escape_ladder:
            el_x, el_y, el_w, el_h = escape_ladder
            esx, esy = camera.world_to_screen(el_x, el_y)

            # Bright glow around escape ladder
            glow_w, glow_h = int(el_w) + 40, int(el_h) + 40
            glow_surf = pygame.Surface((glow_w, glow_h), pygame.SRCALPHA)
            pulse = 0.5 + 0.5 * math.sin(time.time() * 4.0)
            glow_alpha = int(40 + 30 * pulse)
            pygame.draw.rect(glow_surf, (255, 220, 80, glow_alpha), glow_surf.get_rect(), border_radius=8)
            screen.blit(glow_surf, (int(esx) - 20, int(esy) - 20))

            # Draw the ladder rungs
            for ry in range(0, int(el_h), 32):
                rung_y = int(esy) + ry
                pygame.draw.line(screen, (180, 150, 60), (int(esx) + 10, rung_y), (int(esx) + int(el_w) - 10, rung_y), 3)

            # "ESCAPE" label + animated arrow
            escape_font = pygame.font.SysFont("monospace", 16)
            blink = int(time.time() * 3) % 2 == 0
            escape_surf = escape_font.render("ESCAPE", True, (255, 220, 80))
            screen.blit(escape_surf, (int(esx) + int(el_w) // 2 - escape_surf.get_width() // 2, int(esy) + int(el_h) + 4))
            if blink:
                ax = int(esx) + int(el_w) // 2
                ay = int(esy) - 8
                pygame.draw.polygon(screen, (255, 220, 80), [(ax, ay - 12), (ax - 8, ay), (ax + 8, ay)])

        # --- Players (includes mimic copies from server) ---
        self_player: dict | None = None
        for player in game_state.get("players", []):
            try:
                player_id = str(player.get("id", ""))
                facing_right = facing_map.get(player_id, True)
                if player.get("id") == self_id:
                    self_player = player
                self._draw_player(
                    screen=screen,
                    camera=camera,
                    player=player,
                    is_self=player.get("id") == self_id,
                    facing_right=bool(facing_right),
                )
            except Exception as exc:
                print(f"[RENDERER] Error drawing player {player.get('id', '?')}: {exc}")

        # Monsters
        self._draw_monsters(screen, camera, game_state.get("monsters", []))

        # Lighting overlay (applied after all entities)
        if enable_lighting:
            self.lighting.apply(
                screen        = screen,
                camera        = camera,
                players_data  = game_state.get("players", []),
                facing_map    = facing_map,
                campfires     = [],          # TODO: add campfire positions to game state
                sanity_map    = sanity_map,
                self_id       = self_id,
                is_night      = is_night,
            )

        # HUD
        quota_data = game_state.get("quota", {})
        carried_count = int(self_player.get("carried_loot_count", 0)) if self_player else 0
        carried_value = int(self_player.get("carried_loot_value", 0)) if self_player else 0

        interaction_prompt: str | None = None
        if self_player is not None:
            extraction_zone = map_data.get("extraction_zone")
            if carried_value > 0 and self._is_in_extraction_zone(self_player, extraction_zone):
                interaction_prompt = f"Press E to deposit loot ({carried_value} value)"
            else:
                nearest_loot_distance = self._nearest_loot_distance(self_player, list(game_state.get("loot", [])))
                if nearest_loot_distance is not None and nearest_loot_distance <= float(LOOT_PICKUP_RADIUS):
                    interaction_prompt = "Press E to pick up loot"

        self_health = int(self_player.get("health", 100)) if self_player else 100
        time_remaining = float(game_state.get("round", {}).get("time_remaining", 300.0))
        difficulty = game_state.get("round", {}).get("difficulty", "RESEARCHER")
        loot_respawn_remaining = 0.0
        loot_respawn_timer = float(game_state.get("loot_respawn_timer", 0.0))
        loot_respawn_max = float(game_state.get("loot_respawn_max", 15.0))
        if loot_respawn_timer > 0:
            loot_respawn_remaining = max(0.0, loot_respawn_max - loot_respawn_timer)
        player_count = len(game_state.get("players", []))
        flashlight_on = bool(self_player.get("flashlight_on", True)) if self_player else True
        self._game_elapsed += 1.0 / 60.0
        self._draw_hud(screen, self_id, my_sanity, quota_data, carried_count, carried_value, self_health, time_remaining, difficulty, loot_respawn_remaining, player_count, flashlight_on)
        self._draw_interaction_prompt(screen, interaction_prompt)

        # Respawn countdown overlay
        if self_player and not self_player.get("alive", True):
            respawn_timer = float(self_player.get("respawn_timer", 0.0))
            if respawn_timer > 0:
                self._draw_respawn_overlay(screen, respawn_timer)

        # Restore camera offset after shake
        if effects.get("shake_x") and self_id:
            camera.offset_x = orig_offset[0]

    # ------------------------------------------------------------------
    # Monster rendering
    # ------------------------------------------------------------------

    def _draw_monsters(
        self,
        screen: pygame.Surface,
        camera,
        monsters: list[dict],
    ) -> None:
        """Draw visible monster sprites.

        Args:
            screen:   Main surface.
            camera:   Camera for coordinate transform.
            monsters: Monster dicts from GAME_STATE.
        """
        for m in monsters:
            mtype = m.get("type")

            if mtype == "siren":
                sx, sy = camera.world_to_screen(float(m.get("x", 0)), float(m.get("y", 0)))
                siren_rect = self._scaled_entity_rect(
                    sx,
                    sy,
                    int(m.get("w", 30)),
                    int(m.get("h", 48)),
                    scale=self.ENEMY_SPRITE_SCALE,
                )
                siren_state = str(m.get("state", ""))
                siren_sprite_key = "siren_cast" if siren_state == "casting" else "siren_idle"
                siren_facing_right = float(m.get("vx", 0.0)) <= 0.0
                drew_siren = self._draw_enemy_sprite(
                    screen=screen,
                    draw_rect=siren_rect,
                    entity_id=str(m.get("id", "siren")),
                    sprite_key=siren_sprite_key,
                    facing_right=siren_facing_right,
                    fps=9.0,
                )
                # Glow ring — pulses larger when luring/screaming
                is_luring = m.get("luring", False)
                is_screaming = m.get("scream_active", False)
                glow_mult = 1.8
                glow_alpha = 40
                if is_screaming:
                    glow_mult = 3.0
                    glow_alpha = 80
                elif is_luring:
                    pulse = 0.5 + 0.5 * math.sin(time.time() * 6.0)
                    glow_mult = 2.2 + 0.6 * pulse
                    glow_alpha = int(50 + 30 * pulse)
                glow_size = max(80, int(max(siren_rect.w, siren_rect.h) * glow_mult))
                glow = pygame.Surface((glow_size, glow_size), pygame.SRCALPHA)
                glow_center = glow_size // 2
                glow_color = (255, 100, 255, glow_alpha) if is_screaming else (*self.SIREN_COLOR, glow_alpha)
                pygame.draw.circle(glow, glow_color, (glow_center, glow_center), glow_center)
                screen.blit(glow, (siren_rect.centerx - glow_center, siren_rect.centery - glow_center))
                if not drew_siren:
                    pygame.draw.rect(screen, self.SIREN_COLOR, siren_rect)
                if is_luring:
                    pygame.draw.circle(screen, (255, 255, 80),
                                       (int(siren_rect.centerx), int(siren_rect.y) - 8), 5)

            elif mtype == "weeping_angel":
                sx, sy = camera.world_to_screen(float(m.get("x", 0)), float(m.get("y", 0)))
                angel_rect = self._scaled_entity_rect(
                    sx,
                    sy,
                    int(m.get("w", 30)),
                    int(m.get("h", 48)),
                    scale=self.ENEMY_SPRITE_SCALE,
                )
                angel_facing_right = float(m.get("vx", 0.0)) <= 0.0
                angel_frozen = bool(m.get("frozen", False))
                if angel_frozen:
                    # Frozen: draw frame 0 only, no animation advance
                    drew_angel = self._draw_enemy_sprite_frozen(
                        screen=screen,
                        draw_rect=angel_rect,
                        sprite_key="angel",
                        facing_right=angel_facing_right,
                    )
                else:
                    drew_angel = self._draw_enemy_sprite(
                        screen=screen,
                        draw_rect=angel_rect,
                        entity_id=str(m.get("id", "angel")),
                        sprite_key="angel",
                        facing_right=angel_facing_right,
                        fps=7.0,
                    )
                if angel_frozen:
                    # Crouched — covering face
                    arm_h = max(2, int(angel_rect.h * 0.16))
                    if not drew_angel:
                        pygame.draw.rect(screen, self.ANGEL_COLOR,
                                         pygame.Rect(
                                             angel_rect.x + int(angel_rect.w * 0.15),
                                             angel_rect.y + int(angel_rect.h * 0.2),
                                             max(2, int(angel_rect.w * 0.7)),
                                             max(2, int(angel_rect.h * 0.6)),
                                         ))
                        pygame.draw.rect(screen, self.ANGEL_COLOR,
                                         pygame.Rect(
                                             angel_rect.x - int(angel_rect.w * 0.1),
                                             angel_rect.y + int(angel_rect.h * 0.12),
                                             max(2, int(angel_rect.w * 1.1)),
                                             arm_h,
                                         ))
                elif not drew_angel:
                    pygame.draw.rect(screen, self.ANGEL_COLOR, angel_rect)

                # Red warning indicator when angel is chasing (not frozen)
                if not m.get("frozen") and m.get("state") == "chasing":
                    warn_radius = 6
                    warn_x = angel_rect.centerx
                    warn_y = angel_rect.y - 14
                    pulse = 0.5 + 0.5 * math.sin(time.time() * 10.0)
                    warn_alpha = int(180 * pulse + 50)
                    warn_surf = pygame.Surface((warn_radius * 2 + 2, warn_radius * 2 + 2), pygame.SRCALPHA)
                    pygame.draw.circle(warn_surf, (220, 40, 40, warn_alpha), (warn_radius + 1, warn_radius + 1), warn_radius)
                    screen.blit(warn_surf, (warn_x - warn_radius - 1, warn_y - warn_radius))

    # ------------------------------------------------------------------
    # HUD
    # ------------------------------------------------------------------

    # HUD layout constants
    _HUD_MARGIN = 14
    _HUD_BAR_W = 140
    _HUD_BAR_H = 10
    _HUD_BAR_LABEL_OFFSET = 55

    def _draw_hud(
        self,
        screen: pygame.Surface,
        self_id: str | None,
        sanity: float,
        quota_data: dict,
        carried_count: int,
        carried_value: int,
        health: int = 100,
        time_remaining: float = 300.0,
        difficulty: str = "RESEARCHER",
        loot_respawn_remaining: float = 0.0,
        player_count: int = 1,
        flashlight_on: bool = True,
    ) -> None:
        """Draw clean minimal HUD: health bar, sanity bar, countdown timer, quota."""
        sw, sh = screen.get_size()
        font = pygame.font.SysFont("monospace", 14)

        self._draw_hud_bars(screen, font, health, sanity, sw, sh)
        self._draw_hud_flashlight_icon(screen, font, sw, sanity, flashlight_on)
        self._draw_hud_timer(screen, sw, time_remaining)
        self._draw_hud_right_panel(screen, font, sw, quota_data, difficulty, carried_count, carried_value, loot_respawn_remaining, player_count)
        self._draw_hud_quota_flash(screen, sw, sh, quota_data)
        self._draw_hud_hints(screen, sw, sh, quota_data, carried_count)

    def _draw_hud_bars(self, screen: pygame.Surface, font: pygame.font.Font, health: int, sanity: float, sw: int, sh: int) -> None:
        bar_x = self._HUD_BAR_LABEL_OFFSET + self._HUD_MARGIN
        hp_y = self._HUD_MARGIN

        # HP bar
        hp_label = font.render("HP", True, (220, 220, 220))
        screen.blit(hp_label, (self._HUD_MARGIN, hp_y - 1))
        hp_frac = max(0.0, min(1.0, health / 100.0))
        hp_filled = int(self._HUD_BAR_W * hp_frac)
        hp_color = (200, 50, 50) if hp_frac < 0.3 else (220, 160, 40) if hp_frac < 0.6 else (200, 60, 60)
        pygame.draw.rect(screen, (40, 40, 40), pygame.Rect(bar_x, hp_y, self._HUD_BAR_W, self._HUD_BAR_H))
        pygame.draw.rect(screen, hp_color, pygame.Rect(bar_x, hp_y, hp_filled, self._HUD_BAR_H))
        pygame.draw.rect(screen, (80, 80, 80), pygame.Rect(bar_x, hp_y, self._HUD_BAR_W, self._HUD_BAR_H), 1)

        # Sanity bar
        san_y = hp_y + self._HUD_BAR_H + 8
        san_frac = max(0.0, min(1.0, sanity / 100.0))
        san_filled = int(self._HUD_BAR_W * san_frac)

        san_status, san_status_color = self._sanity_status_label(sanity)
        san_label = font.render(san_status, True, san_status_color)
        screen.blit(san_label, (self._HUD_MARGIN, san_y - 1))

        san_color = self._sanity_bar_color(san_frac)
        pygame.draw.rect(screen, (40, 40, 40), pygame.Rect(bar_x, san_y, self._HUD_BAR_W, self._HUD_BAR_H))
        pygame.draw.rect(screen, san_color, pygame.Rect(bar_x, san_y, san_filled, self._HUD_BAR_H))
        pygame.draw.rect(screen, (80, 80, 80), pygame.Rect(bar_x, san_y, self._HUD_BAR_W, self._HUD_BAR_H), 1)

        if san_frac < 0.15:
            vignette_alpha = int(80 * (1.0 - san_frac / 0.15))
            vig = pygame.Surface((sw, sh), pygame.SRCALPHA)
            vig.fill((120, 0, 0, vignette_alpha))
            screen.blit(vig, (0, 0))

    def _draw_hud_flashlight_icon(
        self, screen: pygame.Surface, font: pygame.font.Font,
        sw: int, sanity: float, flashlight_on: bool,
    ) -> None:
        """Draw a small torch icon next to the sanity bar + hint text."""
        # Position: right of the sanity bar
        icon_x = self._HUD_BAR_LABEL_OFFSET + self._HUD_MARGIN + self._HUD_BAR_W + 12
        icon_y = self._HUD_MARGIN + self._HUD_BAR_H + 6

        # Torch body (small rectangle)
        body_w, body_h = 6, 14
        body_rect = pygame.Rect(icon_x + 3, icon_y + 4, body_w, body_h)
        body_color = (180, 150, 60) if flashlight_on else (60, 55, 50)
        pygame.draw.rect(screen, body_color, body_rect)

        # Flame / light tip (triangle above body)
        if flashlight_on:
            tip_color = (255, 220, 80)
            tip_points = [
                (icon_x + 6, icon_y),
                (icon_x + 1, icon_y + 6),
                (icon_x + 11, icon_y + 6),
            ]
            pygame.draw.polygon(screen, tip_color, tip_points)
            # Small glow
            glow_surf = pygame.Surface((16, 16), pygame.SRCALPHA)
            pygame.draw.circle(glow_surf, (255, 220, 80, 40), (8, 8), 8)
            screen.blit(glow_surf, (icon_x - 2, icon_y - 5))
        else:
            tip_color = (80, 70, 60)
            tip_points = [
                (icon_x + 6, icon_y + 1),
                (icon_x + 2, icon_y + 6),
                (icon_x + 10, icon_y + 6),
            ]
            pygame.draw.polygon(screen, tip_color, tip_points)

        # "F — flashlight" hint during first 30 seconds
        if self._game_elapsed < 30.0:
            hint_alpha = min(255, int(255 * max(0.0, 1.0 - self._game_elapsed / 30.0)))
            hint_font = pygame.font.SysFont("monospace", 11)
            hint_surf = hint_font.render("F - flashlight", True, (180, 180, 160))
            hint_s = pygame.Surface(hint_surf.get_size(), pygame.SRCALPHA)
            hint_s.blit(hint_surf, (0, 0))
            hint_s.set_alpha(hint_alpha)
            screen.blit(hint_s, (icon_x + 16, icon_y + 2))

    def _sanity_status_label(self, sanity: float) -> tuple[str, tuple[int, int, int]]:
        if sanity > 60:
            return "SANE", (80, 200, 80)
        if sanity > 30:
            return "UNEASY", (200, 180, 60)
        if sanity > 10:
            return "LOSING IT", (220, 100, 40)
        return "GONE", (220, 40, 40)

    def _sanity_bar_color(self, san_frac: float) -> tuple[int, int, int]:
        if san_frac > 0.5:
            return (80, 200, 80)
        if san_frac > 0.30:
            return (200, 160, 40)
        if san_frac > 0.15:
            pulse = 0.7 + 0.3 * math.sin(time.time() * 5.0)
            return (int(220 * pulse + 35), int(60 * pulse), 40)
        flash = 0.5 + 0.5 * math.sin(time.time() * 10.0)
        return (int(255 * flash), 20, 20)

    def _draw_hud_timer(self, screen: pygame.Surface, sw: int, time_remaining: float) -> None:
        font_timer = pygame.font.SysFont("monospace", 20)
        remaining = max(0.0, time_remaining)
        minutes = int(remaining) // 60
        seconds = int(remaining) % 60
        timer_text = f"{minutes:02d}:{seconds:02d}"

        if remaining < 30:
            pulse = 0.5 + 0.5 * math.sin(time.time() * 6.0)
            r = int(200 + 55 * pulse)
            timer_color = (min(255, r), 50, 50)
        elif remaining < 60:
            timer_color = (230, 160, 40)
        else:
            timer_color = (200, 200, 200)

        timer_surf = font_timer.render(timer_text, True, timer_color)
        timer_x = sw // 2 - timer_surf.get_width() // 2
        timer_backing = pygame.Surface((timer_surf.get_width() + 20, timer_surf.get_height() + 8), pygame.SRCALPHA)
        timer_backing.fill((0, 0, 0, 120))
        screen.blit(timer_backing, (timer_x - 10, 10))
        screen.blit(timer_surf, (timer_x, self._HUD_MARGIN))

    def _draw_hud_right_panel(
        self, screen: pygame.Surface, font: pygame.font.Font, sw: int,
        quota_data: dict, difficulty: str, carried_count: int, carried_value: int,
        loot_respawn_remaining: float, player_count: int = 1,
    ) -> None:
        m = self._HUD_MARGIN
        collected = quota_data.get("collected", 0)
        quota = quota_data.get("quota", 200)
        shortfall = max(0, quota - collected)
        if shortfall > 0:
            quota_text = f"SAMPLES: {collected}/{quota} — need {shortfall} more"
        else:
            quota_text = f"SAMPLES: {collected}/{quota} — QUOTA MET"
        quota_surf = font.render(quota_text, True, (220, 200, 140))
        screen.blit(quota_surf, (sw - quota_surf.get_width() - m, m))

        diff_colors = {"STUDENT": (80, 200, 80), "RESEARCHER": (200, 200, 80), "EXPERT": (220, 60, 60)}
        diff_surf = font.render(difficulty, True, diff_colors.get(difficulty, (200, 200, 80)))
        screen.blit(diff_surf, (sw - diff_surf.get_width() - m, 32))

        # Carry slots — dynamic based on player count
        slot_size = 18
        slot_gap = 4
        slot_y = 48
        max_carry = 5 if player_count <= 1 else 3
        total_slot_w = max_carry * slot_size + (max_carry - 1) * slot_gap
        slot_start_x = sw - total_slot_w - m
        carry_label = font.render("CARRY", True, (200, 200, 180))
        screen.blit(carry_label, (slot_start_x - carry_label.get_width() - 6, slot_y))
        for i in range(max_carry):
            sx = slot_start_x + i * (slot_size + slot_gap)
            rect = pygame.Rect(sx, slot_y, slot_size, slot_size)
            if i < carried_count:
                pygame.draw.rect(screen, (255, 208, 80), rect)
                pygame.draw.rect(screen, (200, 170, 50), rect, 1)
            else:
                pygame.draw.rect(screen, (30, 30, 40), rect)
                pygame.draw.rect(screen, (60, 60, 70), rect, 1)
        if carried_count > 0:
            penalty_pct = int(carried_count * 8)
            pen_surf = font.render(f"-{penalty_pct}% speed", True, (200, 140, 60))
            screen.blit(pen_surf, (slot_start_x, slot_y + slot_size + 3))

        if quota_data.get("is_night"):
            night_surf = font.render("NIGHT", True, (100, 140, 255))
            screen.blit(night_surf, (sw - night_surf.get_width() - m, 64))

        if loot_respawn_remaining > 0:
            respawn_surf = font.render(f"New loot in: {int(loot_respawn_remaining)}s", True, (200, 180, 80))
            screen.blit(respawn_surf, (sw - respawn_surf.get_width() - m, 80))

    def _draw_hud_quota_flash(self, screen: pygame.Surface, sw: int, sh: int, quota_data: dict) -> None:
        quota_val = int(quota_data.get("quota", 200))
        collected_val = int(quota_data.get("collected", 0))
        was_quota_met = self._quota_met
        self._quota_met = collected_val >= quota_val
        if self._quota_met and not was_quota_met:
            self._quota_met_flash_timer = 3.0
        if self._quota_met_flash_timer > 0:
            self._quota_met_flash_timer -= 1.0 / 60.0
            flash_alpha = min(255, int(255 * (self._quota_met_flash_timer / 3.0)))
            flash_font = pygame.font.SysFont("monospace", 32)
            flash_surf = flash_font.render("CONTRACT FULFILLED — FIND THE ESCAPE!", True, (80, 255, 120))
            flash_s = pygame.Surface(flash_surf.get_size(), pygame.SRCALPHA)
            flash_s.blit(flash_surf, (0, 0))
            flash_s.set_alpha(flash_alpha)
            screen.blit(flash_s, (sw // 2 - flash_surf.get_width() // 2, sh // 2 - 80))

    def _draw_hud_hints(self, screen: pygame.Surface, sw: int, sh: int, quota_data: dict, carried_count: int) -> None:
        hint_font = pygame.font.SysFont("monospace", 13)
        quota_val = int(quota_data.get("quota", 200))
        collected_val = int(quota_data.get("collected", 0))
        hints: list[str] = []
        if collected_val < quota_val:
            hints.append(f"Collect {quota_val - collected_val} more loot value")
            if carried_count > 0:
                hints.append("Return to extraction to deposit")
        else:
            hints.append("Quota met! Find the escape ladder")
            hints.append("Look for the glowing ladder above")
        if hints:
            hint_line_h = 18
            hint_panel_w = max(hint_font.size(h)[0] for h in hints) + 16
            hint_panel_h = len(hints) * hint_line_h + 8
            hint_panel = pygame.Surface((hint_panel_w, hint_panel_h), pygame.SRCALPHA)
            hint_panel.fill((0, 0, 0, 130))
            hint_x = sw - hint_panel_w - self._HUD_MARGIN
            hint_y = sh - hint_panel_h - self._HUD_MARGIN
            screen.blit(hint_panel, (hint_x, hint_y))
            for i, h in enumerate(hints):
                h_surf = hint_font.render(h, True, (180, 200, 160))
                screen.blit(h_surf, (hint_x + 8, hint_y + 4 + i * hint_line_h))

    def _draw_respawn_overlay(self, screen: pygame.Surface, timer: float) -> None:
        """Draw dark overlay with respawn countdown."""
        sw, sh = screen.get_size()
        overlay = pygame.Surface((sw, sh), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 160))
        screen.blit(overlay, (0, 0))

        font_big = pygame.font.SysFont("monospace", 48)
        font_sub = pygame.font.SysFont("monospace", 20)

        seconds = max(1, int(math.ceil(timer)))
        text = font_big.render(f"RESPAWNING IN {seconds}", True, (220, 60, 60))
        screen.blit(text, (sw // 2 - text.get_width() // 2, sh // 2 - 30))

        sub = font_sub.render("you have fallen...", True, (140, 100, 100))
        screen.blit(sub, (sw // 2 - sub.get_width() // 2, sh // 2 + 30))

    def _draw_sound_toggle(self, screen: pygame.Surface, sw: int, muted: bool) -> None:
        """Draw a small sound icon in the top-right corner."""
        btn_size = 24
        btn_x = sw - btn_size - 14
        btn_y = 14
        btn_rect = pygame.Rect(btn_x, btn_y, btn_size, btn_size)
        panel = pygame.Surface((btn_size, btn_size), pygame.SRCALPHA)
        panel.fill((0, 0, 0, 120))
        screen.blit(panel, btn_rect.topleft)
        font_icon = pygame.font.SysFont("monospace", 16)
        icon = font_icon.render("M" if muted else "S", True, (180, 60, 60) if muted else (160, 200, 160))
        screen.blit(icon, (btn_x + (btn_size - icon.get_width()) // 2, btn_y + (btn_size - icon.get_height()) // 2))

    def _sanity_effects(self, sanity: float) -> dict:
        """Return screenshake values for current sanity level."""
        if sanity > 35:
            return {"shake_x": 0, "shake_y": 0}
        intensity = int(5 * (1 - sanity / 35))
        return {
            "shake_x": random.randint(-intensity, intensity),
            "shake_y": random.randint(-intensity, intensity),
        }

    # ------------------------------------------------------------------
    # Fade overlay system
    # ------------------------------------------------------------------

    def start_fade_in(self, duration: float = 1.5) -> None:
        """Start fading in from black. Screen goes from black → clear."""
        self._fade_alpha = 255.0
        self._fade_speed = -255.0 / max(0.01, duration * 60.0)  # per frame at 60fps

    def start_fade_out(self, duration: float = 0.5) -> None:
        """Start fading out to black. Screen goes from clear → black."""
        self._fade_alpha = 0.0
        self._fade_speed = 255.0 / max(0.01, duration * 60.0)

    def is_fading(self) -> bool:
        """Return True if a fade is in progress."""
        if self._fade_speed < 0 and self._fade_alpha > 0:
            return True
        if self._fade_speed > 0 and self._fade_alpha < 255:
            return True
        return False

    def is_black(self) -> bool:
        """Return True if screen is fully faded to black."""
        return self._fade_alpha >= 254.0

    def draw_fade_overlay(self, screen: pygame.Surface) -> None:
        """Update and draw the fade overlay. Call at end of every frame."""
        if self._fade_speed == 0.0 and self._fade_alpha <= 0:
            return
        self._fade_alpha += self._fade_speed
        self._fade_alpha = max(0.0, min(255.0, self._fade_alpha))
        if self._fade_alpha <= 0:
            self._fade_speed = 0.0
            return
        if self._fade_alpha >= 255.0 and self._fade_speed > 0:
            self._fade_speed = 0.0  # hold at black until something starts a fade-in
        alpha = int(self._fade_alpha)
        if alpha > 0:
            fade_surf = pygame.Surface(screen.get_size(), pygame.SRCALPHA)
            fade_surf.fill((0, 0, 0, alpha))
            screen.blit(fade_surf, (0, 0))

    # ------------------------------------------------------------------
    # Screen image helper (cached, scaled to screen size)
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Pause menu
    # ------------------------------------------------------------------

    def draw_pause_menu(self, screen: pygame.Surface, selected: int = 0) -> None:
        """Draw semi-transparent pause overlay with three options."""
        sw, sh = screen.get_size()
        overlay = pygame.Surface((sw, sh), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 160))
        screen.blit(overlay, (0, 0))

        font_title = pygame.font.SysFont("monospace", 36)
        font_option = pygame.font.SysFont("monospace", 22)

        title = font_title.render("PAUSED", True, (220, 200, 140))
        screen.blit(title, (sw // 2 - title.get_width() // 2, sh // 2 - 100))

        options = [
            ("RESUME", "ENTER / ESC"),
            ("LOBBY", "L"),
            ("QUIT", "Q"),
        ]
        for i, (label, hint) in enumerate(options):
            y = sh // 2 - 20 + i * 44
            if i == selected:
                color = (255, 240, 180)
                marker = "> "
            else:
                color = (220, 200, 140)
                marker = "  "
            text = font_option.render(f"{marker}{label}", True, color)
            hint_surf = font_option.render(f"  ({hint})", True, (120, 110, 90))
            screen.blit(text, (sw // 2 - 100, y))
            screen.blit(hint_surf, (sw // 2 - 100 + text.get_width(), y))

    # ------------------------------------------------------------------
    # Screen image helper (cached, scaled to screen size)
    # ------------------------------------------------------------------

    def _get_screen_image(self, key: str, path: Path) -> pygame.Surface | None:
        cached = self._screen_image_cache.get(key)
        if cached is not None:
            return cached
        if not path.exists():
            return None
        raw = pygame.image.load(str(path)).convert()
        scaled = pygame.transform.scale(raw, (self._screen_width, self._screen_height))
        self._screen_image_cache[key] = scaled
        return scaled

    # ------------------------------------------------------------------
    # Static screen draws (title, lobby, loading, game over)
    # ------------------------------------------------------------------

    LOADING_LINES = [
        (0.05, "initialising map..."),
        (0.15, "loading entities..."),
        (0.30, "waking the siren..."),
        (0.50, "calibrating sanity systems..."),
        (0.65, "seeding the forest..."),
        (0.80, "suppressing emergency protocols..."),
        (0.95, "ready."),
    ]

    def _get_char_preview(self, skin: str) -> pygame.Surface | None:
        if skin in self._char_preview_cache:
            return self._char_preview_cache[skin]
        assets_root = Path(__file__).resolve().parents[1] / "assets"
        if skin == "researcher":
            path = assets_root / "player" / "idle.png"
        else:
            path = assets_root / "secondplayer" / "idle.png"
        if not path.exists():
            return None
        raw = pygame.image.load(str(path)).convert_alpha()
        # Flip student to match researcher facing direction
        if skin == "student":
            raw = pygame.transform.flip(raw, True, False)
        # Scale to fit inside a 100x130 box with padding
        max_w, max_h = 90, 110
        raw_w, raw_h = raw.get_width(), raw.get_height()
        scale = min(max_w / raw_w, max_h / raw_h)
        scaled = pygame.transform.scale(raw, (int(raw_w * scale), int(raw_h * scale)))
        self._char_preview_cache[skin] = scaled
        return scaled

    DIFFICULTY_PRESETS = {
        "STUDENT":    {"quota": 150, "dmg_mult": 0.5, "time": 420, "label": "STUDENT", "color": (80, 200, 80)},
        "RESEARCHER": {"quota": 300, "dmg_mult": 1.0, "time": 300, "label": "RESEARCHER", "color": (200, 200, 80)},
        "EXPERT":     {"quota": 500, "dmg_mult": 2.0, "time": 240, "label": "EXPERT", "color": (220, 60, 60)},
    }

    def draw_title_screen(
        self,
        screen: pygame.Surface,
        player_name: str,
        selected_skin: str,
        cursor_visible: bool,
        selected_difficulty: str = "RESEARCHER",
    ) -> None:
        sw, sh = screen.get_size()
        assets_root = Path(__file__).resolve().parents[1] / "assets"
        bg = self._get_screen_image("title", assets_root / "wall" / "start_loading" / "title_screen_grove.png")
        if bg is not None:
            screen.blit(bg, (0, 0))
        else:
            screen.fill((8, 12, 7))

        font_label = pygame.font.SysFont("monospace", 20)
        font_input = pygame.font.SysFont("monospace", 28)
        font_prompt = pygame.font.SysFont("monospace", 22)
        font_skin = pygame.font.SysFont("monospace", 16)
        diff_font = pygame.font.SysFont("monospace", 16)

        # --- Very top (y=20): difficulty selector ---
        diff_y = 20
        diff_keys = ["STUDENT", "RESEARCHER", "EXPERT"]
        diff_total_w = len(diff_keys) * 120 + (len(diff_keys) - 1) * 10
        diff_start_x = sw // 2 - diff_total_w // 2
        self._difficulty_btn_rects: dict[str, pygame.Rect] = {}
        for idx, dkey in enumerate(diff_keys):
            preset = self.DIFFICULTY_PRESETS[dkey]
            btn_x = diff_start_x + idx * 130
            btn_w, btn_h = 120, 28
            btn_rect = pygame.Rect(btn_x, diff_y, btn_w, btn_h)
            self._difficulty_btn_rects[dkey] = btn_rect
            is_sel = dkey == selected_difficulty
            btn_panel = pygame.Surface((btn_w, btn_h), pygame.SRCALPHA)
            btn_panel.fill((40, 60, 40, 180) if is_sel else (0, 0, 0, 120))
            screen.blit(btn_panel, btn_rect.topleft)
            if is_sel:
                pygame.draw.rect(screen, preset["color"], btn_rect, 2)
            else:
                pygame.draw.rect(screen, (60, 60, 60), btn_rect, 1)
            d_text = diff_font.render(preset["label"], True, preset["color"] if is_sel else (120, 120, 120))
            screen.blit(d_text, (btn_x + btn_w // 2 - d_text.get_width() // 2, diff_y + 5))

        # Difficulty description below buttons
        sel_preset = self.DIFFICULTY_PRESETS.get(selected_difficulty, self.DIFFICULTY_PRESETS["RESEARCHER"])
        desc_font = pygame.font.SysFont("monospace", 13)
        desc_time = sel_preset["time"] // 60
        desc_text = f"Quota: {sel_preset['quota']}  |  Damage: x{sel_preset['dmg_mult']}  |  Time: {desc_time}min"
        desc_surf = desc_font.render(desc_text, True, (140, 150, 130))
        screen.blit(desc_surf, (sw // 2 - desc_surf.get_width() // 2, diff_y + 32))

        # --- Below difficulty (y=80): ENTER prompt ---
        if player_name.strip():
            prompt_text = font_prompt.render("Press ENTER to start", True, (220, 200, 140))
        else:
            prompt_text = font_prompt.render("type a name to continue", True, (100, 110, 90))
        prompt_panel = pygame.Surface((prompt_text.get_width() + 24, prompt_text.get_height() + 10), pygame.SRCALPHA)
        prompt_panel.fill((0, 0, 0, 150))
        screen.blit(prompt_panel, (sw // 2 - prompt_panel.get_width() // 2, 76))
        screen.blit(prompt_text, (sw // 2 - prompt_text.get_width() // 2, 81))

        # --- Lower half (sh * 0.60): character selection boxes ---
        box_w, box_h = 120, 150
        box_top = int(sh * 0.60)
        spacing = 180
        skins = ["researcher", "student"]

        for i, skin in enumerate(skins):
            cx = sw // 2 + (i * 2 - 1) * (spacing // 2)
            is_selected = skin == selected_skin

            box_rect = pygame.Rect(cx - box_w // 2, box_top, box_w, box_h)
            panel = pygame.Surface((box_w, box_h), pygame.SRCALPHA)
            if is_selected:
                panel.fill((40, 80, 40, 180))
            else:
                panel.fill((0, 0, 0, 120))
            screen.blit(panel, box_rect.topleft)
            if is_selected:
                pygame.draw.rect(screen, (100, 220, 100), box_rect, 2)

            preview = self._get_char_preview(skin)
            if preview is not None:
                px = cx - preview.get_width() // 2
                py = box_top + (box_h - 24 - preview.get_height()) // 2 + 4
                screen.blit(preview, (px, py))

            label = font_skin.render(skin, True, (200, 212, 168) if is_selected else (120, 130, 110))
            screen.blit(label, (cx - label.get_width() // 2, box_top + box_h - 22))

        # --- Name input below character selection ---
        name_y = box_top + box_h + 12
        name_panel_w = 380
        name_panel_h = 44
        name_panel = pygame.Surface((name_panel_w, name_panel_h), pygame.SRCALPHA)
        name_panel.fill((0, 0, 0, 170))
        name_panel_x = sw // 2 - name_panel_w // 2
        screen.blit(name_panel, (name_panel_x, name_y))
        pygame.draw.rect(screen, (80, 100, 70), pygame.Rect(name_panel_x, name_y, name_panel_w, name_panel_h), 1)

        display_name = player_name
        if cursor_visible:
            display_name += "_"
        name_surf = font_input.render(display_name, True, (220, 230, 200))
        screen.blit(name_surf, (name_panel_x + 12, name_y + 8))

        # --- Very bottom: up/down hint ---
        bottom_hint = font_skin.render("up/down: difficulty  |  left/right: skin", True, (100, 110, 90))
        screen.blit(bottom_hint, (sw // 2 - bottom_hint.get_width() // 2, sh - 30))

    def draw_lobby_background(self, screen: pygame.Surface) -> None:
        """Blit the lobby background image fullscreen."""
        assets_root = Path(__file__).resolve().parents[1] / "assets"
        bg = self._get_screen_image("lobby_bg", assets_root / "wall" / "lobby" / "lobby_background.png")
        if bg is not None:
            screen.blit(bg, (0, 0))

    def draw_lobby_overlay(self, screen: pygame.Surface, game_state: dict, audio_muted: bool = False) -> None:
        """Draw lobby overlay with player-count-aware text."""
        sw, sh = screen.get_size()

        # Sound toggle top-right
        self._draw_sound_toggle(screen, sw, audio_muted)
        font_name = pygame.font.SysFont("monospace", 22)
        text_color = (220, 200, 140)

        players = game_state.get("players", [])
        player_count = len(players)

        def _draw_backed_text(surf: pygame.Surface, cx: int, cy: int) -> None:
            pad_x, pad_y = 20, 10
            backing = pygame.Surface(
                (surf.get_width() + pad_x * 2, surf.get_height() + pad_y * 2),
                pygame.SRCALPHA,
            )
            backing.fill((0, 0, 0, 170))
            screen.blit(backing, (cx - backing.get_width() // 2, cy - pad_y))
            screen.blit(surf, (cx - surf.get_width() // 2, cy))

        if player_count <= 1:
            # Waiting state — blinking text
            blink_on = int(time.time() * 2) % 2 == 0
            if blink_on:
                wait_surf = font_name.render("Waiting for second player...", True, text_color)
                _draw_backed_text(wait_surf, sw // 2, sh // 2 - 10)

            solo_surf = font_name.render("Press ENTER to start solo", True, text_color)
            _draw_backed_text(solo_surf, sw // 2, sh - 60)
        else:
            # Both players connected — show names + prompt
            total_height = player_count * 30
            start_y = sh // 2 - total_height // 2
            for i, p in enumerate(players):
                name = str(p.get("name", "Player"))
                row_y = start_y + i * 30
                name_surf = font_name.render(name, True, (200, 230, 180))
                row_w = 14 + 8 + name_surf.get_width()
                row_x = sw // 2 - row_w // 2

                # Dark backing behind player row
                row_backing = pygame.Surface((row_w + 20, 28), pygame.SRCALPHA)
                row_backing.fill((0, 0, 0, 150))
                screen.blit(row_backing, (row_x - 10, row_y - 3))

                pygame.draw.circle(screen, (100, 220, 100), (row_x + 5, row_y + 10), 5)
                screen.blit(name_surf, (row_x + 14, row_y - 1))

            prompt_surf = font_name.render("Press ENTER to start", True, text_color)
            _draw_backed_text(prompt_surf, sw // 2, sh - 60)

        # TEST SOUND button — bottom left
        test_btn_w, test_btn_h = 140, 32
        test_btn_x, test_btn_y = 14, sh - test_btn_h - 14
        self._test_sound_btn_rect = pygame.Rect(test_btn_x, test_btn_y, test_btn_w, test_btn_h)
        btn_panel = pygame.Surface((test_btn_w, test_btn_h), pygame.SRCALPHA)
        btn_panel.fill((0, 0, 0, 150))
        screen.blit(btn_panel, (test_btn_x, test_btn_y))
        pygame.draw.rect(screen, (120, 160, 120), self._test_sound_btn_rect, 1)
        btn_font = pygame.font.SysFont("monospace", 16)
        btn_text = btn_font.render("TEST SOUND", True, (180, 220, 160))
        screen.blit(btn_text, (test_btn_x + (test_btn_w - btn_text.get_width()) // 2,
                               test_btn_y + (test_btn_h - btn_text.get_height()) // 2))

    def draw_loading_screen(self, screen: pygame.Surface, progress: float) -> None:
        sw, sh = screen.get_size()
        assets_root = Path(__file__).resolve().parents[1] / "assets"
        bg = self._get_screen_image("loading", assets_root / "wall" / "start_loading" / "loading_screen.png")
        if bg is not None:
            screen.blit(bg, (0, 0))
        else:
            screen.fill((6, 8, 6))

        font = pygame.font.SysFont("monospace", 14)
        clamped = max(0.0, min(1.0, progress))

        # --- Log lines ---
        log_x = sw // 2 - 200
        log_y = sh // 2 + 40
        for threshold, text in self.LOADING_LINES:
            if clamped >= threshold:
                color = (80, 180, 80) if text == "ready." else (140, 160, 130)
                surf = font.render(f"> {text}", True, color)
                screen.blit(surf, (log_x, log_y))
                log_y += 20

        # --- Loading bar ---
        bar_w = 400
        bar_h = 14
        bar_x = (sw - bar_w) // 2
        bar_y = sh - 80
        filled = int(bar_w * clamped)

        pygame.draw.rect(screen, (30, 30, 30), pygame.Rect(bar_x, bar_y, bar_w, bar_h))
        pygame.draw.rect(screen, (80, 180, 80), pygame.Rect(bar_x, bar_y, filled, bar_h))
        pygame.draw.rect(screen, (100, 120, 80), pygame.Rect(bar_x, bar_y, bar_w, bar_h), 1)

        pct = font.render(f"{int(clamped * 100)}%", True, (200, 200, 180))
        screen.blit(pct, (sw // 2 - pct.get_width() // 2, bar_y + bar_h + 8))

        # --- Scanline effect (cached) ---
        scanline = self._screen_image_cache.get("_scanline")
        if scanline is None:
            scanline = pygame.Surface((sw, sh), pygame.SRCALPHA)
            for y in range(0, sh, 3):
                pygame.draw.line(scanline, (0, 0, 0, 25), (0, y), (sw, y))
            self._screen_image_cache["_scanline"] = scanline
        screen.blit(scanline, (0, 0))

    def draw_quota_met(self, screen: pygame.Surface, game_state: dict) -> None:
        sw, sh = screen.get_size()
        screen.fill((6, 12, 6))

        font_title = pygame.font.SysFont("monospace", 36)
        font_info = pygame.font.SysFont("monospace", 18)

        title = font_title.render("CONTRACT FULFILLED", True, (80, 220, 100))
        screen.blit(title, (sw // 2 - title.get_width() // 2, sh // 2 - 60))

        quota = game_state.get("quota", {})
        collected = quota.get("collected", 0)
        target = quota.get("quota", 200)
        info = font_info.render(f"samples collected: {collected} / {target}", True, (160, 200, 140))
        screen.blit(info, (sw // 2 - info.get_width() // 2, sh // 2 + 10))

        prompt = font_info.render("Press ENTER to return", True, (140, 160, 120))
        screen.blit(prompt, (sw // 2 - prompt.get_width() // 2, sh - 60))

    def draw_game_over(self, screen: pygame.Surface, game_state: dict, show_prompt: bool = True) -> None:
        sw, sh = screen.get_size()
        assets_root = Path(__file__).resolve().parents[1] / "assets"
        players = game_state.get("players", [])
        real_players = [p for p in players if not p.get("is_mimic", False)]
        if len(real_players) <= 1:
            bg = self._get_screen_image("game_over_solo", assets_root / "wall" / "dead_screen" / "dead_screen_player_1.png")
        else:
            bg = self._get_screen_image("game_over_multi", assets_root / "wall" / "dead_screen" / "dead_screen_multiplayer.png")
        if bg is not None:
            screen.blit(bg, (0, 0))
        else:
            screen.fill((8, 6, 6))

        font_name = pygame.font.SysFont("monospace", 22)
        font_info = pygame.font.SysFont("monospace", 18)

        # Player names + "CONSUMED" text only — background image has the visuals
        shown = [p for p in real_players if not p.get("is_mimic", False)]
        name_y = sh // 2 + 20

        if len(shown) == 1:
            positions = [sw // 2]
        elif len(shown) >= 2:
            positions = [sw // 3, 2 * sw // 3]
        else:
            positions = []

        for idx, p in enumerate(shown):
            if idx >= len(positions):
                break
            cx = positions[idx]
            name = str(p.get("name", "player"))
            name_surf = font_name.render(name, True, (160, 60, 60))
            screen.blit(name_surf, (cx - name_surf.get_width() // 2, name_y))
            consumed_surf = font_info.render("CONSUMED", True, (100, 40, 40))
            screen.blit(consumed_surf, (cx - consumed_surf.get_width() // 2, name_y + 28))

        quota = game_state.get("quota", {})
        collected = quota.get("collected", 0)
        target = quota.get("quota", 200)
        info = font_info.render(f"samples collected: {collected} / {target}", True, (120, 90, 70))
        screen.blit(info, (sw // 2 - info.get_width() // 2, sh - 100))

        if show_prompt:
            prompt = font_info.render("Press ENTER to return", True, (140, 120, 100))
            screen.blit(prompt, (sw // 2 - prompt.get_width() // 2, sh - 60))

    # ------------------------------------------------------------------
    # Ending rooftop scene — playable level with shooting stars overlay
    # ------------------------------------------------------------------

    def draw_ending_screen(self, screen: pygame.Surface, dt: float, player_data: dict | None = None) -> None:
        """Draw the rooftop ending as a playable scene with overlays."""
        sw, sh = screen.get_size()
        assets_root = Path(__file__).resolve().parents[1] / "assets"

        # Background image
        bg = self._get_screen_image("rooftop_ending", assets_root / "wall" / "ending" / "rooftop_ending.png")
        if bg is not None:
            screen.blit(bg, (0, 0))
        else:
            # Deep indigo fallback — never just black
            screen.fill((12, 8, 35))
        if not hasattr(self, '_ending_draw_logged'):
            self._ending_draw_logged = True
            print(f"[ENDING] Drawing rooftop, image_loaded={bg is not None}")

        # Draw rooftop platform (floor at y=650 relative to screen, full width)
        platform_y = int(sh * 0.9)
        pygame.draw.rect(screen, (50, 50, 65), pygame.Rect(0, platform_y, sw, sh - platform_y))

        # Draw player on the rooftop if provided
        if player_data:
            px = float(player_data.get("x", sw // 2))
            py = float(player_data.get("y", platform_y - 54))
            pw = int(player_data.get("w", 34))
            ph = int(player_data.get("h", 54))
            skin = str(player_data.get("skin", "researcher"))

            base_scale = self.PLAYER_SPRITE_SCALE * self.ENTITY_RENDER_SCALE
            draw_w = max(1, int(pw * base_scale))
            draw_h = max(1, int(ph * base_scale))
            if skin == "student":
                draw_h = max(1, int(draw_h * 0.85))
            frames = self._get_scaled_skin_frames(skin, draw_w, draw_h)
            if frames:
                anim_key = f"ending_player:{skin}"
                anim = self._player_animation.get(anim_key)
                if anim is None or anim.frames is not frames:
                    anim = AnimationPlayer(frames, fps=10.0, loop=True)
                    self._player_animation[anim_key] = anim
                vx = float(player_data.get("vx", 0.0))
                if abs(vx) > 0.01:
                    anim.update(dt)
                frame = anim.current_frame()
                if frame is not None:
                    facing_right = player_data.get("facing_right", True)
                    if not facing_right:
                        frame = pygame.transform.flip(frame, True, False)
                    draw_x = int(px - (draw_w - pw) / 2)
                    draw_y = int(py - (draw_h - ph))
                    screen.blit(frame, (draw_x, draw_y))

        # Shooting stars overlay
        self._ending_star_timer += dt
        if self._ending_star_timer >= random.uniform(0.8, 1.5):
            self._ending_star_timer = 0.0
            self._ending_stars.append({
                "x": random.uniform(sw * 0.5, sw + 50),
                "y": random.uniform(-30, sh * 0.2),
                "speed": random.uniform(100, 200),
                "angle": random.uniform(2.5, 3.0),  # top-right to bottom-left
                "life": random.uniform(1.5, 3.0),
                "max_life": 0.0,
                "radius": random.uniform(1.5, 3.0),
            })
            self._ending_stars[-1]["max_life"] = self._ending_stars[-1]["life"]

        alive_stars = []
        for star in self._ending_stars:
            star["life"] -= dt
            if star["life"] <= 0:
                continue
            star["x"] += math.cos(star["angle"]) * star["speed"] * dt
            star["y"] += math.sin(star["angle"]) * star["speed"] * dt
            frac = star["life"] / star["max_life"]
            alpha = int(200 * frac)
            trail_len = int(star["speed"] * 0.12)
            ex = star["x"] - math.cos(star["angle"]) * trail_len
            ey = star["y"] - math.sin(star["angle"]) * trail_len
            # Trail line
            trail_s = pygame.Surface((sw, sh), pygame.SRCALPHA)
            pygame.draw.line(trail_s, (255, 255, 255, alpha // 3),
                             (int(ex), int(ey)), (int(star["x"]), int(star["y"])), 1)
            screen.blit(trail_s, (0, 0))
            # Star dot
            r = max(1, int(star["radius"] * frac))
            dot = pygame.Surface((r * 2 + 2, r * 2 + 2), pygame.SRCALPHA)
            pygame.draw.circle(dot, (255, 255, 255, alpha), (r + 1, r + 1), r)
            screen.blit(dot, (int(star["x"]) - r - 1, int(star["y"]) - r - 1))
            alive_stars.append(star)
        self._ending_stars = alive_stars

        # Text overlays — subtle at the top
        self._ending_phase_timer += dt

        font_main = pygame.font.SysFont("monospace", 22)
        font_sub = pygame.font.SysFont("monospace", 18)
        font_prompt = pygame.font.SysFont("monospace", 16)

        if self._ending_phase_timer >= 3.0:
            alpha1 = min(255, int((self._ending_phase_timer - 3.0) * 120))
            text1 = font_main.render("you made it out.", True, (220, 220, 220))
            t1s = pygame.Surface(text1.get_size(), pygame.SRCALPHA)
            t1s.fill((0, 0, 0, 0))
            t1s.blit(text1, (0, 0))
            t1s.set_alpha(alpha1)
            screen.blit(t1s, (sw // 2 - text1.get_width() // 2, 40))

        if self._ending_phase_timer >= 5.0:
            alpha2 = min(255, int((self._ending_phase_timer - 5.0) * 120))
            text2 = font_sub.render("thanks for playing GROVE", True, (180, 200, 160))
            t2s = pygame.Surface(text2.get_size(), pygame.SRCALPHA)
            t2s.fill((0, 0, 0, 0))
            t2s.blit(text2, (0, 0))
            t2s.set_alpha(alpha2)
            screen.blit(t2s, (sw // 2 - text2.get_width() // 2, 72))

        if self._ending_phase_timer >= 7.0:
            alpha3 = min(255, int((self._ending_phase_timer - 7.0) * 120))
            text3 = font_prompt.render("up for another adventure? press ENTER", True, (140, 160, 120))
            t3s = pygame.Surface(text3.get_size(), pygame.SRCALPHA)
            t3s.fill((0, 0, 0, 0))
            t3s.blit(text3, (0, 0))
            t3s.set_alpha(alpha3)
            screen.blit(t3s, (sw // 2 - text3.get_width() // 2, sh - 40))
