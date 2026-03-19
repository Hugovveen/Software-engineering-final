"""Side-view lighting and darkness overlay for GROVE.

Renders a near-black overlay over the screen with a flashlight cone
cut out for each player. Supports sanity-based radius shrink and
campfire radial light sources.

Designed as a drop-in addition to Hugo's renderer.py — call
lighting.apply(screen, camera, players, ...) at the END of each draw call,
just before pygame.display.flip().
"""

from __future__ import annotations

import math
import random

import pygame

try:
    from config import (
        SCREEN_WIDTH, SCREEN_HEIGHT,
        FLASHLIGHT_RADIUS, FLASHLIGHT_ANGLE_DEG, DARKNESS_ALPHA,
        FLASHLIGHT_CONE_ALPHA, FLASHLIGHT_GLOW_ALPHA,
    )
except ImportError:
    SCREEN_WIDTH       = 1536
    SCREEN_HEIGHT      = 1024
    FLASHLIGHT_RADIUS  = 800
    FLASHLIGHT_ANGLE_DEG = 30
    DARKNESS_ALPHA     = 230
    FLASHLIGHT_CONE_ALPHA = 150
    FLASHLIGHT_GLOW_ALPHA = 52

# Flicker
FLICKER_INTERVAL = 4        # re-roll every N frames
FLICKER_RANGE    = 0.03     # ±3 %


class LightingSystem:
    """Manages per-frame darkness overlay with flashlight cone cutouts."""

    def __init__(
        self,
        width: int = SCREEN_WIDTH,
        height: int = SCREEN_HEIGHT,
    ) -> None:
        self.width  = width
        self.height = height
        self._overlay = pygame.Surface((width, height), pygame.SRCALPHA)
        self._frame_count = 0
        self._flicker = 1.0

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def apply(
        self,
        screen: pygame.Surface,
        camera,
        players_data: list[dict],
        facing_map: dict,
        campfires: list[tuple],
        sanity_map: dict,
        self_id: str | None,
        is_night: bool = False,
    ) -> None:
        self._frame_count += 1
        if self._frame_count % FLICKER_INTERVAL == 0:
            self._flicker = 1.0 + random.uniform(-FLICKER_RANGE, FLICKER_RANGE)

        alpha = min(250, DARKNESS_ALPHA + (15 if is_night else 0))
        self._overlay.fill((0, 0, 0, 0))
        pygame.draw.rect(self._overlay, (5, 8, 20, alpha),
                         pygame.Rect(0, 0, self.width, self.height))

        for p in players_data:
            pid      = p.get("id", "")
            sanity   = sanity_map.get(pid, 100.0)
            facing_r = facing_map.get(pid, True)
            flashlight_on = p.get("flashlight_on", True)

            if flashlight_on:
                self._cut_cone(
                    float(p.get("x", 0)),
                    float(p.get("y", 0)),
                    int(p.get("w", 30)),
                    int(p.get("h", 48)),
                    camera, facing_r, sanity,
                )
            else:
                # Flashlight off — nearly invisible, tiny 12px ambient glow
                sx, sy = camera.world_to_screen(
                    float(p.get("x", 0)), float(p.get("y", 0)))
                cx = int(sx + int(p.get("w", 30)) / 2)
                cy = int(sy + int(p.get("h", 48)) / 2)
                self._cut_radial(cx, cy, 12, cut_alpha=int(FLASHLIGHT_GLOW_ALPHA))

        for (cx, cy, cr) in campfires:
            sx, sy = camera.world_to_screen(cx, cy)
            self._cut_radial(int(sx), int(sy), cr, warm=True)

        screen.blit(self._overlay, (0, 0))

        if self_id:
            sanity = sanity_map.get(self_id, 100.0)
            if sanity < 15:
                self._draw_vignette(screen, sanity)

    # ------------------------------------------------------------------
    # Flashlight cone — original radial approach, slightly elliptical
    # ------------------------------------------------------------------

    def _cut_cone(
        self,
        world_x: float,
        world_y: float,
        width: int,
        height: int,
        camera,
        facing_right: bool,
        sanity: float,
    ) -> None:
        sx, sy = camera.world_to_screen(world_x, world_y)
        cx = sx + width / 2
        cy = sy - height * 0.45

        sanity_factor = max(0.35, sanity / 100.0)
        radius = FLASHLIGHT_RADIUS * sanity_factor * self._flicker

        # Slightly elliptical: 1.25x wider horizontally than vertically
        radius_x = radius * 1.25
        radius_y = radius

        base_angle = 0.0 if facing_right else 180.0
        half = FLASHLIGHT_ANGLE_DEG / 2
        segments = 18

        points = [(cx, cy)]
        for i in range(segments + 1):
            angle_deg = base_angle - half + (FLASHLIGHT_ANGLE_DEG * i / segments)
            angle_rad = math.radians(angle_deg)
            points.append((
                cx + math.cos(angle_rad) * radius_x,
                cy + math.sin(angle_rad) * radius_y,
            ))

        if len(points) >= 3:
            cone_alpha = max(0, min(255, int(FLASHLIGHT_CONE_ALPHA + (1.0 - sanity_factor) * 35.0)))
            pygame.draw.polygon(self._overlay, (0, 0, 0, cone_alpha), points)

        # Local glow around player
        torso_radius = max(30, int(height * 1.4 * self._flicker))
        feet_radius = max(18, int(height * 0.75))
        self._cut_radial(int(cx), int(cy), torso_radius, cut_alpha=int(FLASHLIGHT_GLOW_ALPHA))
        self._cut_radial(int(cx), int(sy + height * 0.35), feet_radius, cut_alpha=int(FLASHLIGHT_GLOW_ALPHA))

    # ------------------------------------------------------------------
    # Radial cutout (campfires, ambient glow)
    # ------------------------------------------------------------------

    def _cut_radial(
        self,
        sx: int,
        sy: int,
        radius: int,
        warm: bool = False,
        cut_alpha: int = 0,
    ) -> None:
        safe_alpha = max(0, min(255, int(cut_alpha)))
        pygame.draw.circle(self._overlay, (0, 0, 0, safe_alpha), (sx, sy), radius)

        if warm:
            for r in range(radius, radius + 30, 5):
                fade_alpha = max(0, 80 - (r - radius) * 4)
                glow_surf  = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
                pygame.draw.circle(glow_surf, (255, 130, 20, fade_alpha), (r, r), r)
                self._overlay.blit(glow_surf, (sx - r, sy - r),
                                   special_flags=pygame.BLEND_RGBA_MIN)

    # ------------------------------------------------------------------
    # Sanity vignette
    # ------------------------------------------------------------------

    def _draw_vignette(self, screen: pygame.Surface, sanity: float) -> None:
        intensity = int(180 * (1.0 - sanity / 35.0))
        vig = pygame.Surface((self.width, self.height), pygame.SRCALPHA)

        steps = 10
        for i in range(steps):
            margin = i * 6
            alpha  = max(0, intensity - i * 15)
            rect   = pygame.Rect(margin, margin,
                                 self.width  - margin * 2,
                                 self.height - margin * 2)
            pygame.draw.rect(vig, (10, 0, 0, alpha), rect, 6)

        screen.blit(vig, (0, 0))
