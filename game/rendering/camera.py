"""Simple side-view camera helper.

The camera follows a target position and converts world coordinates into
screen coordinates for rendering.
"""

from __future__ import annotations

from config import SCREEN_HEIGHT, SCREEN_WIDTH


class Camera:
    """Tracks horizontal and vertical offset for side-view rendering."""

    def __init__(self, world_width: int, world_height: int = 1024) -> None:
        self.world_width = world_width
        self.world_height = world_height
        self.offset_x = 0.0
        self.offset_y = 0.0

    def follow(self, target_x: float, target_y: float | None = None) -> None:
        """Center camera around a target while keeping map bounds."""
        desired_x = target_x - (SCREEN_WIDTH / 2)
        self.offset_x = max(0.0, min(desired_x, max(0.0, self.world_width - SCREEN_WIDTH)))

        if target_y is not None:
            desired_y = target_y - (SCREEN_HEIGHT / 2)
            self.offset_y = max(0.0, min(desired_y, max(0.0, self.world_height - SCREEN_HEIGHT)))

    def world_to_screen(self, x: float, y: float) -> tuple[float, float]:
        """Convert a world coordinate into screen space."""
        return x - self.offset_x, y - self.offset_y
