"""Player entity model used by both client and server.

This class stores only simple positional and identity data for clarity.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from config import PLAYER_SIZE, SPRINT_MAX_ENERGY


@dataclass
class Player:
    """Represents a connected player's state in the world."""

    player_id: str
    name: str = "Player"
    x: float = 64.0
    y: float = 360.0
    vx: float = 0.0
    vy: float = 0.0
    width: int = field(default=PLAYER_SIZE[0])
    height: int = field(default=PLAYER_SIZE[1])
    on_ladder: bool = False
    facing: int = 1
    charmed_by: str | None = None
    charm_timer: float = 0.0
    charm_level: int = 0
    sprinting: bool = False
    sprint_energy: float = SPRINT_MAX_ENERGY
    health: int = 100
    alive: bool = True
    skin: str = "researcher"
    carried_loot_count: int = 0
    carried_loot_value: int = 0

    def to_dict(self) -> dict:
        """Convert to a JSON-friendly dictionary for networking."""
        return {
            "id": self.player_id,
            "name": self.name,
            "x": self.x,
            "y": self.y,
            "vx": self.vx,
            "vy": self.vy,
            "w": self.width,
            "h": self.height,
            "on_ladder": self.on_ladder,
            "facing": self.facing,
            "charmed_by": self.charmed_by,
            "charm_timer": self.charm_timer,
            "charm_level": self.charm_level,
            "sprinting": self.sprinting,
            "sprint_energy": self.sprint_energy,
            "carried_loot_count": self.carried_loot_count,
            "carried_loot_value": self.carried_loot_value,
            "health": self.health,
            "alive": self.alive,
            "skin": self.skin,
        }
