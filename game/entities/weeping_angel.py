"""Weeping Angel enemy behavior for the authoritative server."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Any

from config import (
    PLAYER_SPEED,
    WEEPING_ANGEL_ATTACK_RANGE,
    WEEPING_ANGEL_CHASE_SPEED,
    WEEPING_ANGEL_OBSERVE_RANGE,
    WEEPING_ANGEL_SIZE,
)
from entities.enemy_base import EnemyBase

# Teleport cooldown in seconds — angel can teleport when fully off-screen
_TELEPORT_COOLDOWN = 8.0
_MIN_APPROACH_DISTANCE = 30.0  # stop this far from player
_LUNGE_FREEZE_DURATION = 4.0   # freeze after touching a player
_ANGEL_MAX_SPEED = PLAYER_SPEED * 0.4  # 40% of player walk speed


@dataclass
class WeepingAngel(EnemyBase):
    """Chases the closest player when not being observed.

    Freezes when any player faces it.  Can teleport behind a player
    when it has been off-screen for long enough.
    """

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
    frozen: bool = False
    _teleport_timer: float = field(default=0.0, repr=False)
    _lunge_freeze_timer: float = field(default=0.0, repr=False)

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
            if not getattr(player, "alive", True):
                continue
            dist = self._distance_to_player(player)
            if dist < nearest_dist:
                nearest_dist = dist
                nearest_id = player_id
                nearest_player = player

        return nearest_id, nearest_player, nearest_dist

    def _is_observed(self, players: dict[str, Any]) -> bool:
        for player in players.values():
            if not getattr(player, "alive", True):
                continue
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

    def _snap_to_platform(self, world: Any) -> None:
        """Place angel on the nearest platform beneath it."""
        platforms = getattr(world, "platforms", [])
        my_cx = self.x + self.width * 0.5
        best_y: float | None = None

        for px, py, pw, ph in platforms:
            plat_top = float(py)
            if plat_top < self.y - 16:
                continue
            if float(px) <= my_cx <= float(px + pw):
                if best_y is None or plat_top < best_y:
                    best_y = plat_top

        if best_y is not None:
            self.y = best_y - self.height

    def _snap_to_ground(self, world: Any) -> None:
        """Place angel on the ground floor (lowest platform) only."""
        platforms = getattr(world, "platforms", [])
        if not platforms:
            return
        # Find the lowest platform row
        ground_y = max(float(py) for _px, py, _pw, _ph in platforms)
        my_cx = self.x + self.width * 0.5
        for px, py, pw, ph in platforms:
            if float(py) == ground_y and float(px) <= my_cx <= float(px + pw):
                self.y = ground_y - self.height
                return
        # Fallback: snap to ground y anyway
        self.y = ground_y - self.height

    def _find_platform_bounds(self, world: Any) -> tuple[float, float]:
        """Find edges of the platform the angel stands on."""
        platforms = getattr(world, "platforms", [])
        my_bottom = self.y + self.height
        my_cx = self.x + self.width * 0.5

        for px, py, pw, ph in platforms:
            plat_top = float(py)
            if abs(my_bottom - plat_top) > 8:
                continue
            if float(px) <= my_cx <= float(px + pw):
                return float(px), float(px + pw - self.width)

        return 0.0, float(getattr(world, "world_width", 1536) - self.width)

    def _is_off_screen_for_all(self, players: dict[str, Any]) -> bool:
        """Check if angel is far from every player (off all screens)."""
        for player in players.values():
            if not getattr(player, "alive", True):
                continue
            if self._distance_to_player(player) < 900:
                return False
        return True

    def _try_teleport(self, players: dict[str, Any], world: Any) -> bool:
        """Teleport behind the nearest player if off-screen long enough."""
        if self._teleport_timer < _TELEPORT_COOLDOWN:
            return False

        _, nearest_player, _ = self._get_nearest_player(players)
        if nearest_player is None:
            return False

        facing = float(getattr(nearest_player, "facing", 1))
        # Appear behind the player (opposite their facing direction)
        offset = -facing * 120
        new_x = float(nearest_player.x) + offset

        # Clamp to world bounds
        world_w = float(getattr(world, "world_width", 1536))
        new_x = max(0.0, min(world_w - self.width, new_x))

        self.x = new_x
        self.y = float(nearest_player.y)
        self._snap_to_platform(world)
        self._teleport_timer = 0.0
        return True

    def on_touched_player(self) -> None:
        """Called by server when angel damages a player — triggers lunge freeze."""
        self._lunge_freeze_timer = _LUNGE_FREEZE_DURATION

    def update(self, dt: float, world: Any, players: dict[str, Any]) -> None:
        # Snap to whichever platform the angel is on (upper, middle, or ground)
        self._snap_to_platform(world)
        plat_left, plat_right = self._find_platform_bounds(world)

        # Lunge cooldown — frozen after touching a player
        if self._lunge_freeze_timer > 0:
            self._lunge_freeze_timer -= dt
            self.state = "frozen"
            self.frozen = True
            self.vx = 0.0
            return

        if not players:
            self.state = "idle"
            self.vx = 0.0
            self.target_id = None
            self.frozen = False
            return

        nearest_id, nearest_player, nearest_dist = self._get_nearest_player(players)
        self.target_id = nearest_id

        # Track off-screen time for teleport
        if self._is_off_screen_for_all(players):
            self._teleport_timer += dt
            if self._try_teleport(players, world):
                self.state = "chasing"
                self.frozen = False
                return
        else:
            self._teleport_timer = 0.0

        if self._is_observed(players):
            self.state = "frozen"
            self.frozen = True
            self.vx = 0.0
            return

        self.frozen = False

        if nearest_player is None:
            self.state = "idle"
            self.vx = 0.0
            return

        # Stop at minimum distance — don't corner players
        if nearest_dist <= _MIN_APPROACH_DISTANCE:
            self.state = "idle"
            self.vx = 0.0
            return

        # Cap speed to player walk speed
        chase_speed = min(WEEPING_ANGEL_CHASE_SPEED, _ANGEL_MAX_SPEED)
        direction = 1.0 if float(nearest_player.x) > self.x else -1.0
        self.vx = direction * chase_speed
        self.x += self.vx * dt
        self.state = "chasing"

        # Clamp to platform edges
        self.x = max(plat_left, min(plat_right, self.x))

    def to_dict(self) -> dict:
        payload = super().to_dict()
        payload["frozen"] = self.frozen
        return payload
