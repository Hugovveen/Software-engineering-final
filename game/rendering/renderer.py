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

import pygame

# NEW — lighting system
from rendering.lighting import LightingSystem


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
    HUD_BG        = (10,  10,  20,  180)

    def __init__(self, screen_width: int, screen_height: int) -> None:
        # NEW — lighting system instance
        self.lighting = LightingSystem(screen_width, screen_height)
        self._font    = None   # lazy init after pygame.init()

    def _get_font(self, size: int = 14) -> pygame.font.Font:
        """Lazy-load a monospace font."""
        if self._font is None:
            self._font = pygame.font.SysFont("monospace", size)
        return self._font

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
        screen.fill(self.BG_COLOR)

        map_data = game_state.get("map", {})
        for x, y, w, h in map_data.get("platforms", []):
            sx, sy = camera.world_to_screen(x, y)
            pygame.draw.rect(screen, self.PLATFORM_COLOR, pygame.Rect(sx, sy, w, h))

        for x, y, w, h in map_data.get("ladders", []):
            sx, sy = camera.world_to_screen(x, y)
            pygame.draw.rect(screen, self.LADDER_COLOR, pygame.Rect(sx, sy, w, h))

        # --- Players ---
        for player in game_state.get("players", []):
            sx, sy = camera.world_to_screen(player["x"], player["y"])
            color  = self.SELF_COLOR if player.get("id") == self_id else self.PLAYER_COLOR
            pygame.draw.rect(screen, color, pygame.Rect(sx, sy, player["w"], player["h"]))

        # --- Mimic (Hugo's, unchanged) ---
        mimic = game_state.get("mimic")
        if mimic:
            sx, sy = camera.world_to_screen(mimic["x"], mimic["y"])
            pygame.draw.rect(screen, self.MIMIC_COLOR,
                             pygame.Rect(sx, sy, mimic["w"], mimic["h"]))

        # NEW — new monsters
        self._draw_monsters(screen, camera, game_state.get("monsters", []))

        # NEW — Hollow environmental effects
        for monster in game_state.get("monsters", []):
            if monster.get("type") == "hollow":
                self._draw_hollow_effects(screen, camera, monster.get("effects", []))

        # NEW — lighting overlay (applied after all entities)
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
        self._draw_hud(screen, self_id, my_sanity, quota_data)

        # Restore camera offset after shake
        if effects.get("shake_x") and self_id:
            camera.offset_x = orig_offset[0]

        pygame.display.flip()

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
                # Glow ring
                glow = pygame.Surface((80, 80), pygame.SRCALPHA)
                pygame.draw.circle(glow, (*self.SIREN_COLOR, 40), (40, 40), 40)
                screen.blit(glow, (sx - 25, sy - 20))
                pygame.draw.rect(screen, self.SIREN_COLOR,
                                 pygame.Rect(sx, sy, m["w"], m["h"]))
                if m.get("luring"):
                    pygame.draw.circle(screen, (255, 255, 80),
                                       (int(sx + m["w"] / 2), int(sy) - 8), 5)

            elif mtype == "angel":
                sx, sy = camera.world_to_screen(m["x"], m["y"])
                if m.get("frozen"):
                    # Crouched — covering face
                    pygame.draw.rect(screen, self.ANGEL_COLOR,
                                     pygame.Rect(sx + 4, sy + 10, 22, 26))
                    pygame.draw.rect(screen, self.ANGEL_COLOR,
                                     pygame.Rect(sx - 2, sy + 6, 34, 8))
                else:
                    pygame.draw.rect(screen, self.ANGEL_COLOR,
                                     pygame.Rect(sx, sy, m["w"], m["h"]))

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
