"""Mimic enemy entity with a very simple prototype behavior.

For this scaffold, the mimic randomly changes horizontal direction so the team
has a concrete starting point for later AI improvements.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any

from config import MIMIC_SIZE
from entities.enemy_base import EnemyBase


@dataclass
class Mimic(EnemyBase):
    """Represents the mimic entity synchronized by the server."""

    enemy_id: str = "mimic-1"
    enemy_type: str = "mimic"
    x: float = 480.0
    y: float = 360.0
    vx: float = 60.0
    vy: float = 0.0
    width: int = field(default=MIMIC_SIZE[0])
    height: int = field(default=MIMIC_SIZE[1])
    state: str = "patrol"
    target_id: str | None = None

    def update(self, dt: float, world: Any, players: dict[str, Any]) -> None:
        """Advance mimic behavior in one fixed server update."""
        del players
        world_min_x = 10
        world_max_x = max(world_min_x, int(getattr(world, "world_width", 1600)) - int(self.width) - 10)
        self.update_random_walk(dt=dt, world_min_x=world_min_x, world_max_x=world_max_x)

        if hasattr(world, "floor_y"):
            self.y = float(world.floor_y())

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
        return super().to_dict()
