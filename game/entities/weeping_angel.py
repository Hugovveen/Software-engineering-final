"""Weeping Angel monster entity for GROVE.

Frozen while any player has line of sight. Teleports closer the instant
ALL players look away. Players must coordinate to keep it frozen.

Side-view adaptation: line-of-sight is horizontal distance + same floor check.
The Angel walks on platforms. It can only teleport when unobserved.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

try:
    from config import ANGEL_TELEPORT_PX, ANGEL_COOLDOWN_FRAMES, PLAYER_SIZE
except ImportError:
    ANGEL_TELEPORT_PX     = 55
    ANGEL_COOLDOWN_FRAMES = 50
    PLAYER_SIZE           = (30, 48)

# Horizontal range in which a player "sees" the angel (flashlight cone width).
PLAYER_VIEW_RANGE_X = 220


@dataclass
class WeepingAngel:
    """Teleports toward players when unobserved. Frozen when watched.

    Attributes:
        x, y:          World position.
        frozen:        True when at least one player has line of sight.
        cooldown:      Frames remaining before next teleport is allowed.
        teleport_count: Total teleports made this run (for debugging/display).
        kill_range:    Pixel distance for instant kill.
    """

    x: float = 1100.0
    y: float = 360.0
    width: int = field(default=PLAYER_SIZE[0])
    height: int = field(default=PLAYER_SIZE[1])
    frozen: bool = False
    cooldown: int = 0
    teleport_count: int = 0
    kill_range: float = 26.0

    # ------------------------------------------------------------------
    # Observation check
    # ------------------------------------------------------------------

    def _player_observing(self, player, facing_right: bool) -> bool:
        """Return True if this player is looking toward the angel.

        In side-view, "looking toward" means the angel is in the direction
        the player is facing and within horizontal view range.

        Args:
            player:       Player object with x, y attributes.
            facing_right: True if the player is moving/looking right.

        Returns:
            True if the player has line of sight on the angel.
        """
        dx = self.x - player.x
        dy = abs(self.y - player.y)

        # Must be on roughly the same vertical level (within 120px)
        if dy > 120:
            return False

        dist = abs(dx)
        if dist > PLAYER_VIEW_RANGE_X:
            return False

        # Facing check: player must be looking in the angel's direction
        if facing_right and dx < 0:
            return False
        if not facing_right and dx > 0:
            return False

        return True

    def is_observed(self, players: dict, facing_map: dict) -> bool:
        """Check whether any living player currently watches the angel.

        Args:
            players:    {player_id: Player} dict.
            facing_map: {player_id: bool} — True means facing right.

        Returns:
            True if at least one player has line of sight.
        """
        for pid, player in players.items():
            facing_right = facing_map.get(pid, True)
            if self._player_observing(player, facing_right):
                return True
        return False

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    def update(
        self,
        players: dict,
        facing_map: dict,
        floor_y: float,
    ) -> list[str]:
        """Advance angel state one server tick.

        Args:
            players:    {player_id: Player}.
            facing_map: {player_id: bool} — True = facing right.
            floor_y:    Ground y for floor clamping.

        Returns:
            List of player_ids killed this tick.
        """
        killed: list[str] = []

        self.frozen = self.is_observed(players, facing_map)

        if self.frozen:
            self.cooldown = ANGEL_COOLDOWN_FRAMES
            return killed

        # Not observed — attempt teleport
        self.cooldown -= 1
        if self.cooldown <= 0 and players:
            nearest_id, nearest_dist = self._nearest_player(players)
            if nearest_dist > self.kill_range:
                self._teleport_toward(players[nearest_id])
            else:
                killed.append(nearest_id)

        # Floor clamp
        self.y = floor_y

        return killed

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _nearest_player(self, players: dict) -> tuple[str, float]:
        """Return (player_id, distance) of nearest player."""
        best_id, best_dist = "", float("inf")
        for pid, p in players.items():
            d = math.hypot(p.x - self.x, p.y - self.y)
            if d < best_dist:
                best_dist = d
                best_id = pid
        return best_id, best_dist

    def _teleport_toward(self, player) -> None:
        """Move ANGEL_TELEPORT_PX pixels toward the target player."""
        dx = player.x - self.x
        if abs(dx) <= ANGEL_TELEPORT_PX:
            self.x = player.x
        else:
            self.x += math.copysign(ANGEL_TELEPORT_PX, dx)

        self.teleport_count += 1
        self.cooldown = ANGEL_COOLDOWN_FRAMES

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        """Convert to JSON-safe dict for network broadcast."""
        return {
            "type": "angel",
            "x": self.x,
            "y": self.y,
            "w": self.width,
            "h": self.height,
            "frozen": self.frozen,
            "teleport_count": self.teleport_count,
        }
