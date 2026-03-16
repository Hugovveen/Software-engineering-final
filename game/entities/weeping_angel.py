"""Weeping Angel enemy behavior for the authoritative server."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from config import (
    WEEPING_ANGEL_ATTACK_RANGE,
    WEEPING_ANGEL_CHASE_SPEED,
    WEEPING_ANGEL_OBSERVE_RANGE,
    WEEPING_ANGEL_SIZE,
)
from entities.enemy_base import EnemyBase


@dataclass
class WeepingAngel(EnemyBase):
    """Chases the closest player when not being observed."""

    enemy_id: str = "weeping-angel-1"
    enemy_type: str = "weeping_angel"
    x: float = 860.0
    y: float = 360.0
    vx: float = 0.0
    vy: float = 0.0
    width: int = field(default=WEEPING_ANGEL_SIZE[0])
    height: int = field(default=WEEPING_ANGEL_SIZE[1])
    state: str = "idle"
    target_id: str | None = None

    def _distance_to_player(self, player: Any) -> float:
        dx = float(player.x) - self.x
        dy = float(player.y) - self.y
        return math.hypot(dx, dy)

    def _get_nearest_player(self, players: dict[str, Any]) -> tuple[str | None, Any, float]:
        nearest_id: str | None = None
        nearest_player: Any = None
        nearest_dist = float("inf")

        for player_id in sorted(players.keys()):
            player = players[player_id]
            dist = self._distance_to_player(player)
            if dist < nearest_dist:
                nearest_dist = dist
                nearest_id = player_id
                nearest_player = player

        return nearest_id, nearest_player, nearest_dist

    def _is_observed(self, players: dict[str, Any]) -> bool:
        for player in players.values():
            distance = self._distance_to_player(player)
            if distance > WEEPING_ANGEL_OBSERVE_RANGE:
                continue

            horizontal_delta = self.x - float(player.x)
            player_facing = float(getattr(player, "facing", 1))

            if horizontal_delta == 0.0:
                return True
            if horizontal_delta * player_facing > 0.0:
                return True
        return False

    def update(self, dt: float, world: Any, players: dict[str, Any]) -> None:
        floor_y = float(world.floor_y()) if hasattr(world, "floor_y") else self.y
        self.y = floor_y

        if not players:
            self.state = "idle"
            self.vx = 0.0
            self.target_id = None
            return

        nearest_id, nearest_player, nearest_dist = self._get_nearest_player(players)
        self.target_id = nearest_id

        if self._is_observed(players):
            self.state = "frozen"
            self.vx = 0.0
            return

        if nearest_player is None:
            self.state = "idle"
            self.vx = 0.0
            return

        if nearest_dist <= WEEPING_ANGEL_ATTACK_RANGE:
            self.state = "attacking"
            self.vx = 0.0
            return

        direction = 1.0 if float(nearest_player.x) > self.x else -1.0
        self.vx = direction * WEEPING_ANGEL_CHASE_SPEED
        self.x += self.vx * dt
        self.state = "chasing"

        world_min_x = 0.0
        world_max_x = max(world_min_x, float(getattr(world, "world_width", 1600)) - float(self.width))
        self.x = max(world_min_x, min(world_max_x, self.x))
