"""The Hollow monster entity for GROVE.

Completely invisible. No sprite. Wanders toward the group.
Kills by standing still on top of a player for 3 seconds.
Thrown items redirect it. Group throw (3+ simultaneous) repels it longer.

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


@dataclass
class Hollow:
    """Invisible entity that drifts toward the player group.

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
    ) -> list[str]:
        """Advance Hollow state one server tick.

        Args:
            dt:          Delta time in seconds.
            players:     {player_id: Player}.
            floor_y:     Ground y coordinate.
            world_min_x: Left world bound.
            world_max_x: Right world bound.

        Returns:
            List of player_ids killed this tick.
        """
        killed: list[str] = []
        self._step_timer += 1

        # Redirected — move toward thrown item
        if self.redirect_timer > 0:
            self.redirect_timer -= 1
            if self.redirect_target:
                tx, ty = self.redirect_target
                self._move_toward(tx, dt)
            self.y = floor_y
            return killed

        # Drift toward group centroid
        centroid = self._centroid(players)
        if centroid:
            self._wander_angle += random.uniform(-0.08, 0.08)
            cx, cy = centroid
            dx = cx - self.x
            if abs(dx) > 4:
                self.x += math.copysign(HOLLOW_SPEED * dt, dx)
            self.x += math.cos(self._wander_angle) * 0.4

        self.x = max(world_min_x, min(world_max_x, self.x))
        self.y = floor_y

        # Dwell kill check
        for pid, player in players.items():
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
    # Redirection API — called by game server when item is thrown
    # ------------------------------------------------------------------

    def redirect(self, item_x: float, item_y: float) -> None:
        """Redirect Hollow toward a thrown item position.

        Args:
            item_x: Landing x of the thrown item.
            item_y: Landing y of the thrown item.
        """
        self.redirect_target = (item_x, item_y)
        self.redirect_timer = HOLLOW_REDIRECT_FRAMES
        self.dwell_timers.clear()

    def group_redirect(self, positions: list[tuple[float, float]]) -> bool:
        """Attempt group redirect — 3+ simultaneous throws repel it 5x longer.

        Args:
            positions: List of (x, y) item landing positions.

        Returns:
            True if group redirect succeeded.
        """
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
        """Return list of environmental effects for the renderer to draw.

        These are the ONLY visual evidence of The Hollow's presence.

        Args:
            players: {player_id: Player} dict.

        Returns:
            List of effect dicts: {type, x, y, intensity}.
        """
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
            dist = math.hypot(p.x - self.x, p.y - self.y)
            if dist < 70:
                intensity = 1.0 - dist / 70
                effects.append({"type": "breath", "x": self.x, "y": self.y + 10, "intensity": intensity})

        return effects

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _centroid(self, players: dict) -> tuple[float, float] | None:
        """Return average (x, y) of all players."""
        if not players:
            return None
        xs = [p.x for p in players.values()]
        ys = [p.y for p in players.values()]
        return sum(xs) / len(xs), sum(ys) / len(ys)

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
