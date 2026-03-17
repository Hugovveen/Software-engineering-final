"""Siren monster entity for GROVE.

Lures players with fake item pickup sounds. The closer you get the faster
your sanity drains. At night it sings — all players on the map are affected.
Teammate can break your trance by standing next to you (within 40px).

Side-view: Siren walks on platforms like players do.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

# Pulled from config — paste config_additions.py into Hugo's config.py first.
try:
    from config import (
        SIREN_DETECT_RANGE, SIREN_SANITY_DRAIN,
        SIREN_SPEED, SIREN_KILL_RANGE, PLAYER_SIZE,
    )
except ImportError:
    SIREN_DETECT_RANGE = 280
    SIREN_SANITY_DRAIN = 0.18
    SIREN_SPEED        = 55.0
    SIREN_KILL_RANGE   = 30
    PLAYER_SIZE        = (30, 48)


@dataclass
class Siren:
    """Lures players with deceptive audio cues and drains sanity on approach.

    Attributes:
        x, y:          World position (pixels).
        vx:            Horizontal velocity.
        luring:        True when actively pulling a target.
        trance_target: player_id of the player currently being lured.
        night_mode:    True during night phase — song affects entire map.
        lure_timer:    Counts frames; used to emit lure sound periodically.
    """

    x: float = 900.0
    y: float = 360.0
    vx: float = 0.0
    width: int = field(default=PLAYER_SIZE[0])
    height: int = field(default=PLAYER_SIZE[1])
    luring: bool = False
    trance_target: str | None = None   # player_id
    night_mode: bool = False
    lure_timer: int = 0
    _wander_dir: float = field(default=1.0, repr=False)
    _wander_timer: int = field(default=0, repr=False)

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    def update(
        self,
        dt: float,
        players: dict,          # {player_id: Player}
        sanity_map: dict,       # {player_id: float} — managed by SanitySystem
        floor_y: float,
        world_min_x: float,
        world_max_x: float,
        is_night: bool = False,
    ) -> list[str]:
        """Advance Siren state one server tick.

        Args:
            dt:          Delta time in seconds.
            players:     All connected Player objects keyed by id.
            sanity_map:  Mutable sanity dict — Siren writes drain values.
            floor_y:     Ground y coordinate for platform clamping.
            world_min_x: Left bound.
            world_max_x: Right bound.
            is_night:    Whether night phase is active.

        Returns:
            List of player_ids killed this tick (instant kill at melee range).
        """
        self.night_mode = is_night
        self.lure_timer += 1
        killed: list[str] = []

        alive = {pid: p for pid, p in players.items()}

        # Night song — drain all players slightly
        if self.night_mode:
            for pid in alive:
                sanity_map[pid] = max(0.0, sanity_map.get(pid, 100.0) - SIREN_SANITY_DRAIN * 0.25)

        if not alive:
            self._wander(dt, floor_y, world_min_x, world_max_x)
            return killed

        nearest_id, nearest_dist = self._nearest_player(alive)

        if nearest_dist <= SIREN_KILL_RANGE:
            killed.append(nearest_id)
            self.luring = False
            self.trance_target = None
            return killed

        if nearest_dist <= SIREN_DETECT_RANGE:
            # Lure and drift toward
            self.luring = True
            self.trance_target = nearest_id
            target = alive[nearest_id]
            self._move_toward(target.x, dt)
            # Sanity drain scales with proximity
            scale = 1.0 - (nearest_dist / SIREN_DETECT_RANGE)
            sanity_map[nearest_id] = max(
                0.0,
                sanity_map.get(nearest_id, 100.0) - SIREN_SANITY_DRAIN * scale
            )
        else:
            self.luring = False
            self.trance_target = None
            self._wander(dt, floor_y, world_min_x, world_max_x)

        # Floor clamp
        self.y = floor_y

        return killed

    # ------------------------------------------------------------------
    # Trance breaking
    # ------------------------------------------------------------------

    def try_break_trance(self, players: dict) -> bool:
        """Break the trance if a teammate is close to the victim.

        Args:
            players: All connected Player objects.

        Returns:
            True if trance was broken.
        """
        if not self.trance_target or self.trance_target not in players:
            return False
        victim = players[self.trance_target]
        for pid, p in players.items():
            if pid == self.trance_target:
                continue
            dist = math.hypot(p.x - victim.x, p.y - victim.y)
            if dist < 40:
                self.luring = False
                self.trance_target = None
                return True
        return False

    def should_emit_lure_sound(self) -> bool:
        """True every ~3 seconds when luring — client plays fake sample sound."""
        return self.luring and self.lure_timer % 180 == 0

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _nearest_player(self, players: dict) -> tuple[str, float]:
        """Return (player_id, distance) for the closest player."""
        best_id = ""
        best_dist = float("inf")
        for pid, p in players.items():
            d = math.hypot(p.x - self.x, p.y - self.y)
            if d < best_dist:
                best_dist = d
                best_id = pid
        return best_id, best_dist

    def _move_toward(self, target_x: float, dt: float) -> None:
        """Slowly drift toward target x position."""
        dx = target_x - self.x
        if abs(dx) > 4:
            self.x += math.copysign(SIREN_SPEED * dt, dx)

    def _wander(self, dt: float, floor_y: float, mn: float, mx: float) -> None:
        """Random horizontal wander on the floor."""
        self._wander_timer += 1
        if self._wander_timer > 90 or random.random() < 0.01:
            self._wander_dir *= -1
            self._wander_timer = 0
        self.x = max(mn, min(mx, self.x + self._wander_dir * SIREN_SPEED * 0.4 * dt))

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        """Convert to JSON-safe dict for network broadcast."""
        return {
            "type": "siren",
            "x": self.x,
            "y": self.y,
            "w": self.width,
            "h": self.height,
            "luring": self.luring,
            "trance_target": self.trance_target,
        }
