"""Loot entity with simple gravity and platform collision."""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Sequence


def _horizontal_overlap(left_a: float, right_a: float, left_b: float, right_b: float) -> bool:
    return right_a > left_b and left_a < right_b


@dataclass
class Loot:
    """Server-authoritative loot object that falls and settles on geometry."""

    loot_id: str
    x: float
    y: float
    value: int
    width: int = 18
    height: int = 18
    vx: float = 0.0
    vy: float = 0.0
    collected: bool = False

    GRAVITY = 1400.0
    TERMINAL_VELOCITY = 900.0

    def center(self) -> tuple[float, float]:
        return self.x + self.width * 0.5, self.y + self.height * 0.5

    def update(
        self,
        dt: float,
        floor_y: float,
        world_width: float,
        world_height: float,
        platforms: Sequence[tuple[float, float, float, float]],
    ) -> None:
        if self.collected:
            return

        previous_y = float(self.y)
        self.vy = min(self.TERMINAL_VELOCITY, self.vy + self.GRAVITY * dt)
        self.x += self.vx * dt
        self.y += self.vy * dt

        max_x = max(0.0, float(world_width) - float(self.width))
        self.x = max(0.0, min(max_x, self.x))

        if self._resolve_platform_landing(previous_y, platforms):
            return

        fallback_floor_y = min(float(world_height) - float(self.height), float(floor_y) + float(self.height))
        if self.y > fallback_floor_y:
            self.y = fallback_floor_y
            self.vy = 0.0

    def _resolve_platform_landing(
        self,
        previous_y: float,
        platforms: Sequence[tuple[float, float, float, float]],
    ) -> bool:
        left = float(self.x)
        right = left + float(self.width)
        prev_bottom = previous_y + float(self.height)
        curr_bottom = float(self.y) + float(self.height)

        landing_y: float | None = None
        for platform_x, platform_y, platform_w, _platform_h in platforms:
            p_left = float(platform_x)
            p_right = p_left + float(platform_w)
            p_top = float(platform_y)

            if not _horizontal_overlap(left, right, p_left, p_right):
                continue
            if prev_bottom <= p_top and curr_bottom >= p_top:
                candidate = p_top - float(self.height)
                if landing_y is None or candidate < landing_y:
                    landing_y = candidate

        if landing_y is None:
            return False

        self.y = landing_y
        self.vy = 0.0
        return True

    def to_dict(self) -> dict:
        return {
            "id": self.loot_id,
            "x": self.x,
            "y": self.y,
            "w": self.width,
            "h": self.height,
            "value": self.value,
        }
