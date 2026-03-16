"""Siren enemy behavior for patrol, chase, and pulse casting."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from config import (
    SIREN_AGGRO_RANGE,
    SIREN_CAST_TIME,
    SIREN_CHARM_DURATION,
    SIREN_CHARM_PULL_SPEED_L1,
    SIREN_CHARM_PULL_SPEED_L2,
    SIREN_CHARM_PULL_SPEED_L3,
    SIREN_CHASE_SPEED,
    SIREN_INITIAL_CAST_DELAY,
    SIREN_PATROL_SPEED,
    SIREN_PULSE_COOLDOWN,
    SIREN_PULSE_RADIUS,
    SIREN_SIZE,
)
from entities.enemy_base import EnemyBase


@dataclass
class Siren(EnemyBase):
    """Patrols until a player enters aggro range, then chases and pulses."""

    enemy_id: str = "siren-1"
    enemy_type: str = "siren"
    x: float = 1200.0
    y: float = 360.0
    vx: float = -90.0
    vy: float = 0.0
    width: int = field(default=SIREN_SIZE[0])
    height: int = field(default=SIREN_SIZE[1])
    state: str = "patrol"
    target_id: str | None = None
    pulse_cooldown_remaining: float = field(default=SIREN_INITIAL_CAST_DELAY)
    cast_time_remaining: float = 0.0
    charmed_targets: dict[str, dict[str, float | int]] = field(default_factory=dict)

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

    def _update_patrol(self, dt: float, world: Any) -> None:
        world_min_x = 0.0
        world_max_x = max(world_min_x, float(getattr(world, "world_width", 1600)) - float(self.width))

        if self.vx == 0.0:
            self.vx = SIREN_PATROL_SPEED

        self.x += self.vx * dt
        if self.x <= world_min_x:
            self.x = world_min_x
            self.vx = abs(SIREN_PATROL_SPEED)
        elif self.x >= world_max_x:
            self.x = world_max_x
            self.vx = -abs(SIREN_PATROL_SPEED)

    def _get_charm_level(self, distance: float) -> int:
        if distance <= SIREN_PULSE_RADIUS * 0.33:
            return 3
        if distance <= SIREN_PULSE_RADIUS * 0.66:
            return 2
        return 1

    def _get_pull_speed(self, charm_level: int, distance: float) -> float:
        base_speeds = {
            1: SIREN_CHARM_PULL_SPEED_L1,
            2: SIREN_CHARM_PULL_SPEED_L2,
            3: SIREN_CHARM_PULL_SPEED_L3,
        }
        base_speed = base_speeds.get(charm_level, SIREN_CHARM_PULL_SPEED_L1)
        closeness = 1.0 - min(distance, SIREN_PULSE_RADIUS) / SIREN_PULSE_RADIUS
        return base_speed * (0.65 + (1.1 * closeness))

    def _apply_charm_pulse(self, players: dict[str, Any]) -> None:
        for player_id, player in players.items():
            distance = self._distance_to_player(player)
            if distance > SIREN_PULSE_RADIUS:
                continue

            charm_level = self._get_charm_level(distance)
            self.charmed_targets[player_id] = {
                "remaining": SIREN_CHARM_DURATION,
                "level": charm_level,
            }
            player.charmed_by = self.enemy_id
            player.charm_timer = SIREN_CHARM_DURATION
            player.charm_level = charm_level

    def _apply_charm_effects(self, dt: float, world: Any, players: dict[str, Any]) -> None:
        world_min_x = 0.0

        expired_targets: list[str] = []
        for player_id, effect in self.charmed_targets.items():
            player = players.get(player_id)
            if player is None:
                expired_targets.append(player_id)
                continue

            remaining = max(0.0, float(effect["remaining"]) - dt)
            charm_level = int(effect["level"])
            effect["remaining"] = remaining

            if remaining <= 0.0:
                player.charmed_by = None
                player.charm_timer = 0.0
                player.charm_level = 0
                expired_targets.append(player_id)
                continue

            horizontal_delta = self.x - float(player.x)
            distance = abs(horizontal_delta)
            direction = 0.0 if distance < 1.0 else (1.0 if horizontal_delta > 0.0 else -1.0)
            pull_speed = self._get_pull_speed(charm_level, distance)
            world_max_x = max(world_min_x, float(getattr(world, "world_width", 1600)) - float(player.width))

            player.x += direction * pull_speed * dt
            player.x = max(world_min_x, min(world_max_x, player.x))
            player.charmed_by = self.enemy_id
            player.charm_timer = remaining
            player.charm_level = charm_level

        for player_id in expired_targets:
            self.charmed_targets.pop(player_id, None)

    def update(self, dt: float, world: Any, players: dict[str, Any]) -> None:
        floor_y = float(world.floor_y()) if hasattr(world, "floor_y") else self.y
        self.y = floor_y

        self.pulse_cooldown_remaining = max(0.0, self.pulse_cooldown_remaining - dt)
        self._apply_charm_effects(dt, world, players)

        if self.cast_time_remaining > 0.0:
            self.cast_time_remaining = max(0.0, self.cast_time_remaining - dt)
            self.state = "casting"
            self.vx = 0.0
            if self.cast_time_remaining <= 0.0:
                self._apply_charm_pulse(players)
                self.state = "cooldown"
                self.pulse_cooldown_remaining = SIREN_PULSE_COOLDOWN
            return

        if not players:
            self.target_id = None
            self.state = "patrol"
            self._update_patrol(dt, world)
            return

        nearest_id, nearest_player, nearest_dist = self._get_nearest_player(players)

        if nearest_player is None:
            self.target_id = None
            self.state = "patrol"
            self._update_patrol(dt, world)
            return

        self.target_id = nearest_id

        if nearest_dist <= SIREN_PULSE_RADIUS and self.pulse_cooldown_remaining <= 0.0:
            self.cast_time_remaining = SIREN_CAST_TIME
            self.state = "casting"
            self.vx = 0.0
            return

        if nearest_dist <= SIREN_AGGRO_RANGE:
            direction = 1.0 if float(nearest_player.x) > self.x else -1.0
            self.vx = direction * SIREN_CHASE_SPEED
            self.x += self.vx * dt
            self.state = "chasing"
        else:
            self.state = "patrol"
            self._update_patrol(dt, world)

        world_min_x = 0.0
        world_max_x = max(world_min_x, float(getattr(world, "world_width", 1600)) - float(self.width))
        self.x = max(world_min_x, min(world_max_x, self.x))

    def to_dict(self) -> dict:
        payload = super().to_dict()
        payload["pulse_cooldown_remaining"] = self.pulse_cooldown_remaining
        payload["cast_time_remaining"] = self.cast_time_remaining
        payload["charmed_target_ids"] = sorted(self.charmed_targets.keys())
        return payload
