"""Simple side-view facility map with floor platforms and ladders.

The map data is deliberately tiny and readable for prototype iteration.
"""

from __future__ import annotations


class FacilityMap:
    """Stores map geometry used by server and renderer."""

    def __init__(self) -> None:
        self.world_width = 1600
        self.world_height = 900

        # Rectangles are (x, y, w, h).
        self.platforms = [
            (0, 420, 1600, 36),
            (220, 300, 320, 24),
            (760, 260, 380, 24),
            (1220, 340, 240, 24),
        ]

        # Ladders are (x, y, w, h).
        self.ladders = [
            (360, 300, 28, 120),
            (900, 260, 28, 160),
        ]

    def floor_y(self) -> float:
        """Return the ground/floor y coordinate for simple collision."""
        return 372.0
