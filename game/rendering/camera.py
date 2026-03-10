"""Simple side-view camera helper.

The camera follows a target x-position and converts world coordinates into
screen coordinates for rendering.
"""

from __future__ import annotations

from config import SCREEN_WIDTH


class Camera:
    """Tracks horizontal offset for side-view rendering."""

    def __init__(self, world_width: int) -> None:
        self.world_width = world_width
        self.offset_x = 0.0

    def follow(self, target_x: float) -> None:
        """Center camera around a target while keeping map bounds."""
        desired = target_x - (SCREEN_WIDTH / 2)
        self.offset_x = max(0.0, min(desired, max(0.0, self.world_width - SCREEN_WIDTH)))

    def world_to_screen(self, x: float, y: float) -> tuple[float, float]:
        """Convert a world coordinate into screen space."""
        return x - self.offset_x, y
