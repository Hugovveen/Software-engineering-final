"""Shared base model for all server-authoritative enemy types."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class EnemyBase(ABC):
    """Common state and contract for enemy implementations."""

    enemy_id: str
    enemy_type: str
    x: float
    y: float
    vx: float
    vy: float
    width: int
    height: int
    state: str = "idle"
    target_id: str | None = None

    @abstractmethod
    def update(self, dt: float, world: Any, players: dict[str, Any]) -> None:
        """Advance enemy simulation by one fixed server tick."""

    def to_dict(self) -> dict:
        """Serialize to a JSON-friendly payload for client sync."""
        return {
            "id": self.enemy_id,
            "type": self.enemy_type,
            "x": self.x,
            "y": self.y,
            "vx": self.vx,
            "vy": self.vy,
            "w": self.width,
            "h": self.height,
            "state": self.state,
            "target_id": self.target_id,
        }
