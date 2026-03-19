"""Weeping Angel enemy behavior for the authoritative server."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from config import (
    ANGEL_MAX_SPEED_FRACTION,
    ANGEL_REPULSION_DISTANCE,
    ANGEL_REPULSION_PX,
    ANGEL_STARTUP_DURATION,
    ANGEL_STARTUP_SPEED_FACTOR,
    ANGEL_STOP_DISTANCE,
    ANGEL_TELEPORT_COOLDOWN,
    PLAYER_SPEED,
    WEEPING_ANGEL_ATTACK_RANGE,
    WEEPING_ANGEL_CHASE_SPEED,
    WEEPING_ANGEL_SIZE,
)
from entities.enemy_base import EnemyBase

_ANGEL_MAX_SPEED = PLAYER_SPEED * ANGEL_MAX_SPEED_FRACTION


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
    attacking: bool = False
    _teleport_timer: float = field(default=0.0, repr=False)
    _debug_timer: float = field(default=0.0, repr=False)
    _startup_timer: float = field(default=0.0, repr=False)

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

    def _is_observed(self, players: dict[str, Any], facing_map: dict[str, bool] | None = None) -> bool:
        if facing_map is None:
            facing_map = {}
        for pid, player in players.items():
            if not getattr(player, "alive", True):
                continue

            horizontal_delta = self.x - float(player.x)
            facing_right = facing_map.get(pid, True)

            if horizontal_delta == 0.0:
                return True
            # Angel is to the RIGHT of player → player must face RIGHT to see her
            # Angel is to the LEFT  of player → player must face LEFT  to see her
            if horizontal_delta > 0 and facing_right:
                return True
            if horizontal_delta < 0 and not facing_right:
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
        if self._teleport_timer < ANGEL_TELEPORT_COOLDOWN:
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

    def update(self, dt: float, world: Any, players: dict[str, Any], facing_map: dict[str, bool] | None = None) -> None:
        # Snap to whichever platform the angel is on (upper, middle, or ground)
        self._snap_to_platform(world)
        plat_left, plat_right = self._find_platform_bounds(world)

        if not players:
            self.state = "idle"
            self.vx = 0.0
            self.target_id = None
            self.frozen = False
            self.attacking = False
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

        observed = self._is_observed(players, facing_map)

        # Debug print every 2 seconds
        self._debug_timer += dt
        if self._debug_timer >= 2.0:
            self._debug_timer = 0.0
            print(f"[ANGEL] vx={self.vx:.1f}, dist={nearest_dist:.1f}, frozen={self.frozen}, attacking={self.attacking}")

        if observed:
            self.state = "frozen"
            self.frozen = True
            self.vx = 0.0
            self.attacking = False
            return

        # Transition from frozen → moving: brief startup ramp
        was_frozen = self.frozen
        self.frozen = False
        if was_frozen:
            self._startup_timer = ANGEL_STARTUP_DURATION

        if nearest_player is None:
            self.state = "idle"
            self.vx = 0.0
            return

        # Tick startup timer
        if self._startup_timer > 0:
            self._startup_timer = max(0.0, self._startup_timer - dt)

        # --- Repulsion: if player walks into angel, push angel away ---
        angel_cx = self.x + self.width * 0.5
        player_cx = float(nearest_player.x) + float(getattr(nearest_player, 'width', 30)) * 0.5
        dx_centers = abs(angel_cx - player_cx)
        if dx_centers < ANGEL_REPULSION_DISTANCE:
            push_dir = 1.0 if angel_cx >= player_cx else -1.0
            self.x += push_dir * ANGEL_REPULSION_PX
            self.x = max(plat_left, min(plat_right, self.x))
            self.vx = 0.0
            self.state = "chasing"
            return

        # --- Within stop distance: hold position, don't nudge ---
        if nearest_dist <= ANGEL_STOP_DISTANCE:
            self.vx = 0.0
            self.state = "chasing"
            return

        # --- Normal chase movement ---
        direction = 1.0 if player_cx > angel_cx else -1.0
        chase_speed = min(WEEPING_ANGEL_CHASE_SPEED, _ANGEL_MAX_SPEED)
        if self._startup_timer > 0:
            chase_speed *= ANGEL_STARTUP_SPEED_FACTOR
        self.vx = direction * chase_speed
        self.x += self.vx * dt
        self.state = "chasing"

        # Clamp to platform edges
        self.x = max(plat_left, min(plat_right, self.x))

    def to_dict(self) -> dict:
        payload = super().to_dict()
        payload["frozen"] = self.frozen
        payload["attacking"] = self.attacking
        return payload
