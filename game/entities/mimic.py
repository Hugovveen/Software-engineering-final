"""Mimic enemy entity with a very simple prototype behavior.

For this scaffold, the mimic randomly changes horizontal direction so the team
has a concrete starting point for later AI improvements.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from config import MIMIC_SIZE


@dataclass
class Mimic:
    """Represents the mimic entity synchronized by the server."""

    x: float = 480.0
    y: float = 360.0
    vx: float = 60.0
    vy: float = 0.0
    width: int = field(default=MIMIC_SIZE[0])
    height: int = field(default=MIMIC_SIZE[1])

    def update_random_walk(self, dt: float, world_min_x: float, world_max_x: float) -> None:
        """Move in a basic random pattern along the floor for prototype gameplay."""
        if random.random() < 0.02:
            self.vx = random.choice([-80.0, -60.0, 60.0, 80.0])

        self.x += self.vx * dt
        if self.x < world_min_x:
            self.x = world_min_x
            self.vx *= -1
        elif self.x > world_max_x:
            self.x = world_max_x
            self.vx *= -1

    def to_dict(self) -> dict:
        """Convert mimic state to a JSON-friendly dictionary."""
        return {
            "x": self.x,
            "y": self.y,
            "vx": self.vx,
            "vy": self.vy,
            "w": self.width,
            "h": self.height,
        }
