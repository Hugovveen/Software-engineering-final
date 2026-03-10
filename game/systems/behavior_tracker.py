"""Tracks basic movement history as a base for future mimic learning logic.

The current implementation is intentionally simple and transparent for a student
team to extend incrementally.
"""

from __future__ import annotations

from collections import deque


class BehaviorTracker:
    """Records recent player positions for pattern analysis."""

    def __init__(self, max_samples: int = 120) -> None:
        self.history: dict[str, deque[tuple[float, float]]] = {}
        self.max_samples = max_samples

    def record(self, player_id: str, x: float, y: float) -> None:
        """Save one position sample for a player."""
        if player_id not in self.history:
            self.history[player_id] = deque(maxlen=self.max_samples)
        self.history[player_id].append((x, y))

    def get_recent_path(self, player_id: str) -> list[tuple[float, float]]:
        """Return recent positions for one player."""
        if player_id not in self.history:
            return []
        return list(self.history[player_id])
