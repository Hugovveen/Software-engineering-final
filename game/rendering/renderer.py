"""Pygame renderer for map, players, mimic, and new monster entities.

Rendering code is isolated here to keep the main client loop uncluttered.

CHANGES FROM HUGO'S VERSION (marked # NEW):
  - draw_monsters() renders Siren and Angel (Hollow is invisible)
  - draw_hollow_effects() renders Hollow environmental cues
  - draw_hud() renders quota, sanity bar, day/night clock
  - apply_sanity_effects() applies screen shake and vignette
  - LightingSystem is applied at end of draw()
"""

from __future__ import annotations

import math
import random
import time
from pathlib import Path

import pygame

from config import LOOT_PICKUP_RADIUS

# NEW — lighting system

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
        # NEW — lighting system instance
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

    def _draw_player(self, screen: pygame.Surface, camera, player: dict, is_self: bool, facing_right: bool) -> None:
        px = float(player.get("x", 0.0))
        py = float(player.get("y", 0.0))
        pw = int(player.get("w", 30))
        ph = int(player.get("h", 48))
        vx = float(player.get("vx", 0.0))
        player_id = str(player.get("id", "player"))
        skin = str(player.get("skin", "researcher"))
        sx, sy = camera.world_to_screen(px, py)

        base_scale = self.PLAYER_SPRITE_SCALE * self.ENTITY_RENDER_SCALE
        draw_w = max(1, int(pw * base_scale))
        draw_h = max(1, int(ph * base_scale))
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
            loot_w = int(loot.get("w", 18))
            loot_h = int(loot.get("h", 18))
            loot_rect = pygame.Rect(int(sx), int(sy), loot_w, loot_h)

            if has_loot_assets:
                loot_id = str(loot.get("id", "loot"))
                variant_index = self._loot_variant_index(loot_id)
                scaled_sprite = self._get_scaled_loot_surface(variant_index, loot_w, loot_h)
                if scaled_sprite is not None:
                    screen.blit(scaled_sprite, loot_rect.topleft)
                    continue

            pygame.draw.rect(screen, self.LOOT_COLOR, loot_rect, border_radius=4)
            pygame.draw.rect(screen, (80, 50, 20), loot_rect, 1, border_radius=4)

    def _loot_variant_index(self, loot_id: str) -> int:
        if not self._loot_surfaces:
            return 0
        checksum = sum(ord(character) for character in loot_id)
        return checksum % len(self._loot_surfaces)

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
    # Main draw call
    # ------------------------------------------------------------------

    def draw(
        self,
        screen: pygame.Surface,
        camera,
        game_state: dict,
        self_id: str | None,
        facing_map: dict | None = None,     # NEW
        sanity_map: dict | None = None,     # NEW
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

        # --- Sanity screen shake (NEW) ---
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
            self._draw_background(screen, camera)

        map_data = game_state.get("map", {})
        self._draw_platforms(screen, camera, map_data.get("platforms", []))
        self._draw_extraction_zone(screen, camera, map_data.get("extraction_zone"))
        self._draw_loot(screen, camera, list(game_state.get("loot", [])))

        for x, y, w, h in map_data.get("ladders", []):
            sx, sy = camera.world_to_screen(x, y)
            pygame.draw.rect(screen, self.LADDER_COLOR, pygame.Rect(sx, sy, w, h))

        # --- Players ---
        self_player: dict | None = None
        for player in game_state.get("players", []):
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

        # --- Mimic (Hugo's, unchanged) ---
        mimic = game_state.get("mimic")
        if mimic:
            sx, sy = camera.world_to_screen(mimic["x"], mimic["y"])
            mimic_rect = self._scaled_entity_rect(
                sx,
                sy,
                int(mimic["w"]),
                int(mimic["h"]),
                scale=self.ENEMY_SPRITE_SCALE,
            )
            mimic_facing_right = float(mimic.get("vx", 0.0)) >= 0.0
            drew_mimic = self._draw_enemy_sprite(
                screen=screen,
                draw_rect=mimic_rect,
                entity_id=str(mimic.get("id", "mimic")),
                sprite_key="mimic",
                facing_right=mimic_facing_right,
                fps=8.0,
            )
            if not drew_mimic:
                pygame.draw.rect(screen, self.MIMIC_COLOR, mimic_rect)

        # NEW — new monsters
        self._draw_monsters(screen, camera, game_state.get("monsters", []))

        # NEW — Hollow environmental effects
        for monster in game_state.get("monsters", []):
            if monster.get("type") == "hollow":
                self._draw_hollow_effects(screen, camera, monster.get("effects", []))

        # NEW — lighting overlay (applied after all entities)
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

        # NEW — HUD
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

        self._draw_hud(screen, self_id, my_sanity, quota_data, carried_count, carried_value)
        self._draw_interaction_prompt(screen, interaction_prompt)

        # Restore camera offset after shake
        if effects.get("shake_x") and self_id:
            camera.offset_x = orig_offset[0]

    # ------------------------------------------------------------------
    # NEW — monster rendering
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
                sx, sy = camera.world_to_screen(m["x"], m["y"])
                siren_rect = self._scaled_entity_rect(
                    sx,
                    sy,
                    int(m["w"]),
                    int(m["h"]),
                    scale=self.ENEMY_SPRITE_SCALE,
                )
                siren_state = str(m.get("state", ""))
                siren_sprite_key = "siren_cast" if siren_state == "casting" else "siren_idle"
                siren_facing_right = float(m.get("vx", 0.0)) >= 0.0
                drew_siren = self._draw_enemy_sprite(
                    screen=screen,
                    draw_rect=siren_rect,
                    entity_id=str(m.get("id", "siren")),
                    sprite_key=siren_sprite_key,
                    facing_right=siren_facing_right,
                    fps=9.0,
                )
                # Glow ring
                glow_size = max(80, int(max(siren_rect.w, siren_rect.h) * 1.8))
                glow = pygame.Surface((glow_size, glow_size), pygame.SRCALPHA)
                glow_center = glow_size // 2
                pygame.draw.circle(glow, (*self.SIREN_COLOR, 40), (glow_center, glow_center), glow_center)
                screen.blit(glow, (siren_rect.centerx - glow_center, siren_rect.centery - glow_center))
                if not drew_siren:
                    pygame.draw.rect(screen, self.SIREN_COLOR, siren_rect)
                if m.get("luring"):
                    pygame.draw.circle(screen, (255, 255, 80),
                                       (int(siren_rect.centerx), int(siren_rect.y) - 8), 5)

            elif mtype == "angel":
                sx, sy = camera.world_to_screen(m["x"], m["y"])
                angel_rect = self._scaled_entity_rect(
                    sx,
                    sy,
                    int(m["w"]),
                    int(m["h"]),
                    scale=self.ENEMY_SPRITE_SCALE,
                )
                angel_facing_right = float(m.get("vx", 0.0)) >= 0.0
                drew_angel = self._draw_enemy_sprite(
                    screen=screen,
                    draw_rect=angel_rect,
                    entity_id=str(m.get("id", "angel")),
                    sprite_key="angel",
                    facing_right=angel_facing_right,
                    fps=7.0,
                )
                if m.get("frozen"):
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

            # Hollow: no sprite — handled by _draw_hollow_effects

    def _draw_hollow_effects(
        self,
        screen: pygame.Surface,
        camera,
        effects: list[dict],
    ) -> None:
        """Render Hollow environmental cues (only visual evidence of it).

        Args:
            screen:  Main surface.
            camera:  Camera for coordinate transform.
            effects: Effect dicts from Hollow.get_effects().
        """
        for effect in effects:
            etype = effect.get("type")
            ex, ey = effect.get("x", 0), effect.get("y", 0)
            sx, sy = camera.world_to_screen(ex, ey)
            intensity = effect.get("intensity", 1.0)

            if etype == "footprint":
                alpha = int(180 * intensity)
                s = pygame.Surface((14, 7), pygame.SRCALPHA)
                pygame.draw.ellipse(s, (200, 200, 200, alpha), s.get_rect())
                screen.blit(s, (int(sx) - 7, int(sy) - 3))

            elif etype == "dust":
                alpha = int(80 * intensity)
                s = pygame.Surface((18, 18), pygame.SRCALPHA)
                pygame.draw.circle(s, (200, 200, 200, alpha), (9, 9), 9)
                screen.blit(s, (int(sx) - 9, int(sy) - 9))

            elif etype == "breath":
                alpha = int(120 * intensity)
                s = pygame.Surface((24, 14), pygame.SRCALPHA)
                pygame.draw.ellipse(s, (230, 240, 255, alpha), s.get_rect())
                screen.blit(s, (int(sx) - 12, int(sy) - 7))

    # ------------------------------------------------------------------
    # NEW — HUD
    # ------------------------------------------------------------------

    def _draw_hud(
        self,
        screen: pygame.Surface,
        self_id: str | None,
        sanity: float,
        quota_data: dict,
        carried_count: int,
        carried_value: int,
    ) -> None:
        """Draw heads-up display: sanity bar, quota progress, day/time.

        Args:
            screen:     Main surface.
            self_id:    Local player id.
            sanity:     Local player sanity 0–100.
            quota_data: Quota dict from GAME_STATE.
        """
        font = self._get_font(13)
        sw, sh = screen.get_size()

        # --- Top-left panel ---
        lines = [
            f"HP:       {100}",          # placeholder until HP added
            f"SANITY:   {int(sanity)}%",
            f"SAMPLES:  {quota_data.get('collected', 0)}/{quota_data.get('quota', 200)}",
            f"CARRY:    {carried_count} item(s), {carried_value} value",
            quota_data.get("time_string", ""),
        ]
        for i, line in enumerate(lines):
            color = (255, 255, 255)
            if i == 1 and sanity < 35:
                color = (255, 80, 80)
            surf = font.render(line, True, color)
            screen.blit(surf, (12, 12 + i * 18))

        # --- Sanity bar ---
        bar_w  = 140
        bar_h  = 6
        bar_x  = 12
        bar_y  = 86
        filled = int(bar_w * max(0.0, sanity / 100.0))
        bar_color = (80, 200, 80) if sanity > 50 else (200, 80, 80) if sanity < 25 else (200, 160, 40)
        pygame.draw.rect(screen, (40, 40, 40), pygame.Rect(bar_x, bar_y, bar_w, bar_h))
        pygame.draw.rect(screen, bar_color,    pygame.Rect(bar_x, bar_y, filled, bar_h))

        # Night indicator
        if quota_data.get("is_night"):
            night_surf = font.render("[ NIGHT ]", True, (100, 140, 255))
            screen.blit(night_surf, (sw - 100, 12))

        # Game over overlay
        if quota_data.get("game_over"):
            go = pygame.Surface((sw, sh), pygame.SRCALPHA)
            go.fill((0, 0, 0, 180))
            screen.blit(go, (0, 0))
            big = pygame.font.SysFont("monospace", 40, bold=True)
            msg = big.render("CONTRACT TERMINATED", True, (200, 50, 50))
            screen.blit(msg, (sw // 2 - msg.get_width() // 2,
                               sh // 2 - msg.get_height() // 2))

    def _sanity_effects(self, sanity: float) -> dict:
        """Return screenshake values for current sanity level."""
        import random
        if sanity > 35:
            return {"shake_x": 0, "shake_y": 0}
        intensity = int(5 * (1 - sanity / 35))
        return {
            "shake_x": random.randint(-intensity, intensity),
            "shake_y": random.randint(-intensity, intensity),
        }

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

    def draw_title_screen(
        self,
        screen: pygame.Surface,
        player_name: str,
        selected_skin: str,
        cursor_visible: bool,
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
        font_prompt = pygame.font.SysFont("monospace", 26)
        font_skin = pygame.font.SysFont("monospace", 16)

        # --- Layout: character boxes ABOVE the baked-in "GROVE" title ---
        box_w, box_h = 120, 150
        box_top = int(sh * 0.15)
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

            # Character preview sprite — centered inside the box
            preview = self._get_char_preview(skin)
            if preview is not None:
                px = cx - preview.get_width() // 2
                py = box_top + (box_h - 24 - preview.get_height()) // 2 + 4
                screen.blit(preview, (px, py))

            # Skin label at bottom of box
            label = font_skin.render(skin, True, (200, 212, 168) if is_selected else (120, 130, 110))
            screen.blit(label, (cx - label.get_width() // 2, box_top + box_h - 22))

        # Arrow hint below boxes
        hint_y = box_top + box_h + 6
        arrow_hint = font_skin.render("<  arrow keys to select  >", True, (140, 150, 120))
        screen.blit(arrow_hint, (sw // 2 - arrow_hint.get_width() // 2, hint_y))

        # --- Name input below character selection ---
        name_y = hint_y + 36
        name_label = font_label.render("enter your name:", True, (160, 170, 140))
        name_panel_w = 380
        name_panel_h = 44
        name_panel = pygame.Surface((name_panel_w, name_panel_h), pygame.SRCALPHA)
        name_panel.fill((0, 0, 0, 170))
        name_panel_x = sw // 2 - name_panel_w // 2
        screen.blit(name_label, (name_panel_x, name_y - 24))
        screen.blit(name_panel, (name_panel_x, name_y))
        pygame.draw.rect(screen, (80, 100, 70), pygame.Rect(name_panel_x, name_y, name_panel_w, name_panel_h), 1)

        display_name = player_name
        if cursor_visible:
            display_name += "_"
        name_surf = font_input.render(display_name, True, (220, 230, 200))
        screen.blit(name_surf, (name_panel_x + 12, name_y + 8))

        # --- ENTER prompt at the very bottom ---
        prompt_y = sh - 60
        if player_name.strip():
            text = font_prompt.render("Press ENTER to connect", True, (220, 200, 140))
        else:
            text = font_prompt.render("type a name to continue", True, (100, 110, 90))
        text_panel = pygame.Surface((text.get_width() + 32, text.get_height() + 16), pygame.SRCALPHA)
        text_panel.fill((0, 0, 0, 150))
        screen.blit(text_panel, (sw // 2 - text_panel.get_width() // 2, prompt_y))
        screen.blit(text, (sw // 2 - text.get_width() // 2, prompt_y + 8))

    def draw_lobby_background(self, screen: pygame.Surface) -> None:
        """Blit the lobby background image fullscreen."""
        assets_root = Path(__file__).resolve().parents[1] / "assets"
        bg = self._get_screen_image("lobby_bg", assets_root / "wall" / "lobby" / "lobby_background.png")
        if bg is not None:
            screen.blit(bg, (0, 0))

    def draw_lobby_overlay(self, screen: pygame.Surface, game_state: dict) -> None:
        """Draw minimal lobby overlay: player names + bottom prompt."""
        sw, sh = screen.get_size()
        font_name = pygame.font.SysFont("monospace", 22)
        font_prompt = pygame.font.SysFont("monospace", 18)

        players = game_state.get("players", [])
        player_count = len(players)

        # Player names with green dots — centered on screen
        total_height = player_count * 30
        start_y = sh // 2 - total_height // 2
        for i, p in enumerate(players):
            name = str(p.get("name", "Player"))
            row_y = start_y + i * 30
            name_surf = font_name.render(name, True, (200, 230, 180))
            row_w = 14 + 8 + name_surf.get_width()  # dot + gap + text
            row_x = sw // 2 - row_w // 2
            pygame.draw.circle(screen, (100, 220, 100), (row_x + 5, row_y + 10), 5)
            screen.blit(name_surf, (row_x + 14, row_y - 1))

        # Bottom prompt
        bottom_y = sh - 50
        prompt_text = "ready to embark on this adventure? press ENTER when ready"
        if player_count < 2:
            # Blink slowly (toggle every ~1s)
            blink = int(time.perf_counter()) % 2 == 0
            if blink:
                surf = font_prompt.render(prompt_text, True, (180, 170, 130))
                screen.blit(surf, (sw // 2 - surf.get_width() // 2, bottom_y))
        else:
            surf = font_prompt.render(prompt_text, True, (220, 200, 140))
            screen.blit(surf, (sw // 2 - surf.get_width() // 2, bottom_y))

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

    def draw_game_over(self, screen: pygame.Surface, game_state: dict) -> None:
        sw, sh = screen.get_size()
        assets_root = Path(__file__).resolve().parents[1] / "assets"
        bg = self._get_screen_image("game_over", assets_root / "wall" / "dead_screen" / "dead_screen_multiplayer.png")
        if bg is not None:
            screen.blit(bg, (0, 0))
        else:
            screen.fill((8, 6, 6))

        font_name = pygame.font.SysFont("monospace", 22)
        font_info = pygame.font.SysFont("monospace", 18)

        players = game_state.get("players", [])
        start_y = sh // 2 - 20
        for i, p in enumerate(players):
            name = str(p.get("name", "player"))
            line = font_name.render(f"{name}  —  CONSUMED", True, (160, 60, 60))
            screen.blit(line, (sw // 2 - line.get_width() // 2, start_y + i * 28))

        quota = game_state.get("quota", {})
        collected = quota.get("collected", 0)
        target = quota.get("quota", 200)
        info = font_info.render(f"samples collected: {collected} / {target}", True, (120, 90, 70))
        screen.blit(info, (sw // 2 - info.get_width() // 2, sh - 100))

        prompt = font_info.render("Press ENTER to return", True, (140, 120, 100))
        screen.blit(prompt, (sw // 2 - prompt.get_width() // 2, sh - 60))
