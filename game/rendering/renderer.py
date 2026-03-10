"""Pygame renderer for map, players, and mimic entity.

Rendering code is isolated here to keep the main client loop uncluttered.
"""

from __future__ import annotations

import pygame


class Renderer:
    """Draws the full frame based on received game state."""

    BG_COLOR = (8, 12, 20)
    PLATFORM_COLOR = (75, 75, 95)
    LADDER_COLOR = (130, 100, 70)
    PLAYER_COLOR = (90, 170, 255)
    SELF_COLOR = (90, 255, 160)
    MIMIC_COLOR = (220, 60, 90)

    def draw(self, screen: pygame.Surface, camera, game_state: dict, self_id: str | None) -> None:
        """Render world and entities from the latest game state snapshot."""
        screen.fill(self.BG_COLOR)

        map_data = game_state.get("map", {})
        for x, y, w, h in map_data.get("platforms", []):
            sx, sy = camera.world_to_screen(x, y)
            pygame.draw.rect(screen, self.PLATFORM_COLOR, pygame.Rect(sx, sy, w, h))

        for x, y, w, h in map_data.get("ladders", []):
            sx, sy = camera.world_to_screen(x, y)
            pygame.draw.rect(screen, self.LADDER_COLOR, pygame.Rect(sx, sy, w, h))

        for player in game_state.get("players", []):
            sx, sy = camera.world_to_screen(player["x"], player["y"])
            color = self.SELF_COLOR if player.get("id") == self_id else self.PLAYER_COLOR
            pygame.draw.rect(screen, color, pygame.Rect(sx, sy, player["w"], player["h"]))

        mimic = game_state.get("mimic")
        if mimic:
            sx, sy = camera.world_to_screen(mimic["x"], mimic["y"])
            pygame.draw.rect(screen, self.MIMIC_COLOR, pygame.Rect(sx, sy, mimic["w"], mimic["h"]))

        pygame.display.flip()
