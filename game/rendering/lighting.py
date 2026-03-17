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
import pygame

try:
    from config import (
        SCREEN_WIDTH, SCREEN_HEIGHT,
        FLASHLIGHT_RADIUS, FLASHLIGHT_ANGLE_DEG, DARKNESS_ALPHA,
    )
except ImportError:
    SCREEN_WIDTH       = 1024
    SCREEN_HEIGHT      = 576
    FLASHLIGHT_RADIUS  = 190
    FLASHLIGHT_ANGLE_DEG = 55
    DARKNESS_ALPHA     = 215


class LightingSystem:
    """Manages per-frame darkness overlay with flashlight cone cutouts.

    Approach:
        1. Fill a full-screen SRCALPHA surface with near-black.
        2. For each player: cut out a cone in their facing direction.
        3. For each campfire: cut out a warm radial circle.
        4. Blit the overlay onto the main surface.
        5. Optionally draw vignette for low-sanity players.

    Usage:
        lighting = LightingSystem()
        # inside draw loop, after drawing world + entities:
        lighting.apply(screen, players_data, facing_map, campfires, sanity)
    """

    def __init__(
        self,
        width: int = SCREEN_WIDTH,
        height: int = SCREEN_HEIGHT,
    ) -> None:
        self.width  = width
        self.height = height
        self._overlay = pygame.Surface((width, height), pygame.SRCALPHA)

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
        """Draw darkness overlay with light cutouts onto screen.

        Args:
            screen:       Main pygame surface.
            camera:       Hugo's Camera object for coordinate conversion.
            players_data: List of player dicts from GAME_STATE.
            facing_map:   {player_id: bool} True = facing right.
            campfires:    List of (world_x, world_y, radius) tuples.
            sanity_map:   {player_id: float} sanity values.
            self_id:      Local player's id (for sanity effect application).
            is_night:     Increases base darkness at night.
        """
        alpha = min(245, DARKNESS_ALPHA + (30 if is_night else 0))
        self._overlay.fill((0, 0, 0, 0))
        pygame.draw.rect(self._overlay, (0, 0, 0, alpha),
                         pygame.Rect(0, 0, self.width, self.height))

        for p in players_data:
            pid      = p.get("id", "")
            sanity   = sanity_map.get(pid, 100.0)
            facing_r = facing_map.get(pid, True)
            self._cut_cone(p["x"], p["y"], p["w"], p["h"],
                           camera, facing_r, sanity)

        for (cx, cy, cr) in campfires:
            sx, sy = camera.world_to_screen(cx, cy)
            self._cut_radial(int(sx), int(sy), cr, warm=True)

        screen.blit(self._overlay, (0, 0))

        # Sanity vignette for local player only
        if self_id:
            sanity = sanity_map.get(self_id, 100.0)
            if sanity < 35:
                self._draw_vignette(screen, sanity)

    # ------------------------------------------------------------------
    # Light cutouts
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
        """Cut a flashlight cone for one player.

        Args:
            world_x, world_y: Player world position.
            width, height:    Player sprite dimensions.
            camera:           Camera for coordinate conversion.
            facing_right:     True = cone points right, False = left.
            sanity:           Sanity value — shrinks cone at low sanity.
        """
        sx, sy = camera.world_to_screen(world_x, world_y)
        cx = sx + width  / 2
        cy = sy + height / 2

        # Sanity shrinks radius
        sanity_factor = max(0.35, sanity / 100.0)
        radius        = FLASHLIGHT_RADIUS * sanity_factor

        # Cone angle: 0° = right, 180° = left
        base_angle = 0.0 if facing_right else 180.0
        half       = FLASHLIGHT_ANGLE_DEG / 2
        segments   = 18

        points = [(cx, cy)]
        for i in range(segments + 1):
            angle_deg = base_angle - half + (FLASHLIGHT_ANGLE_DEG * i / segments)
            angle_rad = math.radians(angle_deg)
            points.append((
                cx + math.cos(angle_rad) * radius,
                cy + math.sin(angle_rad) * radius,
            ))

        if len(points) >= 3:
            pygame.draw.polygon(self._overlay, (0, 0, 0, 0), points)

        # Small ambient glow at player feet
        pygame.draw.circle(self._overlay, (0, 0, 0, 0), (int(cx), int(cy)), 20)

    def _cut_radial(
        self,
        sx: int,
        sy: int,
        radius: int,
        warm: bool = False,
    ) -> None:
        """Cut a circular light area (campfire / flare).

        Args:
            sx, sy:  Screen coordinates of light center.
            radius:  Light radius in pixels.
            warm:    If True, add warm amber gradient ring.
        """
        pygame.draw.circle(self._overlay, (0, 0, 0, 0), (sx, sy), radius)

        if warm:
            # Amber glow fringe
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
        """Draw darkening screen edges that intensify at low sanity.

        Args:
            screen: Main pygame surface.
            sanity: Player's current sanity value.
        """
        intensity = int(180 * (1.0 - sanity / 35.0))
        vig       = pygame.Surface((self.width, self.height), pygame.SRCALPHA)

        steps = 10
        for i in range(steps):
            margin = i * 6
            alpha  = max(0, intensity - i * 15)
            rect   = pygame.Rect(margin, margin,
                                 self.width  - margin * 2,
                                 self.height - margin * 2)
            pygame.draw.rect(vig, (10, 0, 0, alpha), rect, 6)

        screen.blit(vig, (0, 0))
