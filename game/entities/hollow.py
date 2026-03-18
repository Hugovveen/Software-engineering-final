"""The Hollow monster entity for GROVE.

Completely invisible. No sprite. Stalks the nearest player.
Kills by standing still on top of a player for 3 seconds.
Thrown items redirect it. Group throw (3+ simultaneous) repels it longer.

Behavioral additions:
- Stalks nearest player instead of group centroid
- Stays out of flashlight cone (player facing direction)
- Approaches closer when player is alone and low-sanity
- Stays on platforms

Environmental cues returned via get_effects() — the renderer draws these
instead of a sprite:
  - footprint:  appears 1 second after each step
  - dust:       disturbed air around it
  - breath:     visible when very close to a player
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

try:
    from config import (
        HOLLOW_SPEED, HOLLOW_KILL_RANGE,
        HOLLOW_DWELL_FRAMES, HOLLOW_REDIRECT_FRAMES,
    )
except ImportError:
    HOLLOW_SPEED          = 30.0
    HOLLOW_KILL_RANGE     = 22
    HOLLOW_DWELL_FRAMES   = 180
    HOLLOW_REDIRECT_FRAMES = 180

# Flashlight cone parameters (match rendering/lighting.py)
_FLASHLIGHT_CONE_HALF_ANGLE = 0.45  # radians (~25 degrees)
_FLASHLIGHT_RANGE = 280.0

# Sanity threshold below which hollow gets bolder
_LOW_SANITY_THRESHOLD = 40.0


@dataclass
class Hollow:
    """Invisible entity that stalks the nearest player.

    Attributes:
        x, y:            World position.
        redirect_timer:  Frames remaining in confused/redirected state.
        redirect_target: (x, y) position of thrown item distraction.
        dwell_timers:    {player_id: int} frames overlapping each player.
    """

    x: float = 200.0
    y: float = 360.0
    redirect_timer: int = 0
    redirect_target: tuple[float, float] | None = None
    dwell_timers: dict = field(default_factory=dict)
    _wander_angle: float = field(default=0.0, repr=False)
    _step_timer: int = field(default=0, repr=False)

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    def update(
        self,
        dt: float,
        players: dict,
        floor_y: float,
        world_min_x: float,
        world_max_x: float,
        sanity_values: dict | None = None,
    ) -> list[str]:
        """Advance Hollow state one server tick.

        Args:
            dt:            Delta time in seconds.
            players:       {player_id: Player}.
            floor_y:       Ground y coordinate.
            world_min_x:   Left world bound.
            world_max_x:   Right world bound.
            sanity_values: {player_id: float} sanity levels (0-100).

        Returns:
            List of player_ids killed this tick.
        """
        killed: list[str] = []
        self._step_timer += 1
        sanity_values = sanity_values or {}

        # Redirected — move toward thrown item
        if self.redirect_timer > 0:
            self.redirect_timer -= 1
            if self.redirect_target:
                tx, ty = self.redirect_target
                self._move_toward(tx, dt)
            self.y = floor_y
            return killed

        # Find nearest alive player
        target = self._get_stalk_target(players, sanity_values)

        if target is not None:
            player = players[target]
            px, py = float(player.x), float(player.y)
            player_facing = float(getattr(player, "facing", 1))
            player_sanity = sanity_values.get(target, 100.0)
            is_solo = sum(1 for p in players.values() if getattr(p, "alive", True)) <= 1

            # Determine approach distance based on sanity / solo
            if is_solo and player_sanity < _LOW_SANITY_THRESHOLD:
                # Bold: get very close
                desired_dist = 15.0
                speed_mult = 1.4
            else:
                desired_dist = 60.0
                speed_mult = 1.0

            # Check if we're in the flashlight cone
            in_cone = self._in_flashlight_cone(px, py, player_facing)

            if in_cone:
                # Circle around to approach from behind
                behind_x = px - player_facing * 100
                dx = behind_x - self.x
                if abs(dx) > 4:
                    self.x += math.copysign(HOLLOW_SPEED * speed_mult * dt, dx)
            else:
                # Move toward target
                dx = px - self.x
                dist = abs(dx)
                if dist > desired_dist:
                    self._wander_angle += random.uniform(-0.05, 0.05)
                    self.x += math.copysign(HOLLOW_SPEED * speed_mult * dt, dx)
                    self.x += math.cos(self._wander_angle) * 0.3

        self.x = max(world_min_x, min(world_max_x, self.x))
        self.y = floor_y

        # Dwell kill check
        for pid, player in players.items():
            if not getattr(player, "alive", True):
                continue
            dist = math.hypot(player.x - self.x, player.y - self.y)
            if dist <= HOLLOW_KILL_RANGE:
                self.dwell_timers[pid] = self.dwell_timers.get(pid, 0) + 1
                if self.dwell_timers[pid] >= HOLLOW_DWELL_FRAMES:
                    killed.append(pid)
                    self.dwell_timers[pid] = 0
            else:
                self.dwell_timers[pid] = 0

        return killed

    # ------------------------------------------------------------------
    # Target selection
    # ------------------------------------------------------------------

    def _get_stalk_target(self, players: dict, sanity_values: dict) -> str | None:
        """Pick the best player to stalk.

        Prioritize low-sanity solo players, otherwise nearest.
        """
        best_id: str | None = None
        best_score = float("inf")

        for pid, player in players.items():
            if not getattr(player, "alive", True):
                continue
            dist = math.hypot(player.x - self.x, player.y - self.y)
            sanity = sanity_values.get(pid, 100.0)
            # Lower sanity = lower score = higher priority
            score = dist + sanity * 3.0
            if score < best_score:
                best_score = score
                best_id = pid

        return best_id

    def _in_flashlight_cone(self, px: float, py: float, facing: float) -> bool:
        """Check if hollow is inside a player's flashlight cone."""
        dx = self.x - px
        dy = self.y - py
        dist = math.hypot(dx, dy)
        if dist > _FLASHLIGHT_RANGE or dist < 1.0:
            return False

        angle_to_hollow = math.atan2(dy, dx)
        flashlight_angle = 0.0 if facing >= 0 else math.pi
        angle_diff = abs(angle_to_hollow - flashlight_angle)
        if angle_diff > math.pi:
            angle_diff = 2 * math.pi - angle_diff

        return angle_diff < _FLASHLIGHT_CONE_HALF_ANGLE

    # ------------------------------------------------------------------
    # Redirection API — called by game server when item is thrown
    # ------------------------------------------------------------------

    def redirect(self, item_x: float, item_y: float) -> None:
        """Redirect Hollow toward a thrown item position."""
        self.redirect_target = (item_x, item_y)
        self.redirect_timer = HOLLOW_REDIRECT_FRAMES
        self.dwell_timers.clear()

    def group_redirect(self, positions: list[tuple[float, float]]) -> bool:
        """Attempt group redirect — 3+ simultaneous throws repel it 5x longer."""
        if len(positions) < 3:
            return False
        cx = sum(p[0] for p in positions) / len(positions)
        cy = sum(p[1] for p in positions) / len(positions)
        self.redirect_target = (cx, cy)
        self.redirect_timer = HOLLOW_REDIRECT_FRAMES * 5
        self.dwell_timers.clear()
        return True

    # ------------------------------------------------------------------
    # Environmental effects — returned to renderer
    # ------------------------------------------------------------------

    def get_effects(self, players: dict) -> list[dict]:
        """Return list of environmental effects for the renderer to draw."""
        effects: list[dict] = []

        # Footprint every ~30 frames
        if self._step_timer % 30 == 0:
            effects.append({"type": "footprint", "x": self.x, "y": self.y + 40, "intensity": 1.0})

        # Dust cloud around position
        if self._step_timer % 8 == 0:
            effects.append({"type": "dust", "x": self.x + random.uniform(-12, 12),
                            "y": self.y + random.uniform(20, 44), "intensity": 0.5})

        # Breath when very close to any player
        for p in players.values():
            if not getattr(p, "alive", True):
                continue
            dist = math.hypot(p.x - self.x, p.y - self.y)
            if dist < 70:
                intensity = 1.0 - dist / 70
                effects.append({"type": "breath", "x": self.x, "y": self.y + 10, "intensity": intensity})

        return effects

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _move_toward(self, tx: float, dt: float) -> None:
        """Move toward target x at redirect speed."""
        dx = tx - self.x
        if abs(dx) > 4:
            self.x += math.copysign(HOLLOW_SPEED * 0.6 * dt, dx)

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        """Convert to JSON-safe dict. No position revealed to clients."""
        return {
            "type": "hollow",
            "effects": [],      # effects list filled in per-client by server
            "redirected": self.redirect_timer > 0,
        }
