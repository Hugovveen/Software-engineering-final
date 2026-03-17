"""Sanity system for GROVE.

Tracks per-player sanity independently of Hugo's Player dataclass
(so we don't need to modify his file). Uses player_id as keys.

Sanity drains when:
  - Alone (no teammate within 180px)
  - A monster is within 200px

Sanity regens when:
  - Near a teammate (within 180px)

Visual effects are requested via get_effects(player_id) and consumed
by the renderer each frame.
"""

from __future__ import annotations

import math
import random

try:
    from config import (
        SANITY_MAX, SANITY_DRAIN_ALONE, SANITY_DRAIN_MONSTER,
        SANITY_REGEN_GROUP, SANITY_LOW_THRESHOLD, SANITY_CRIT_THRESHOLD,
    )
except ImportError:
    SANITY_MAX            = 100.0
    SANITY_DRAIN_ALONE    = 0.015
    SANITY_DRAIN_MONSTER  = 0.12
    SANITY_REGEN_GROUP    = 0.008
    SANITY_LOW_THRESHOLD  = 35.0
    SANITY_CRIT_THRESHOLD = 12.0

MONSTER_DRAIN_RADIUS  = 200.0
TEAMMATE_REGEN_RADIUS = 180.0


class SanitySystem:
    """Manages per-player sanity values and visual effect requests.

    Usage (server-side each tick):
        sanity.update(players, monsters)

    Usage (client-side each frame):
        effects = sanity.get_effects(my_player_id)
        renderer.apply_sanity_effects(screen, effects)

    Attributes:
        values:              {player_id: float} sanity 0–100.
        _hallucination_cd:   {player_id: int} cooldown frames.
    """

    def __init__(self) -> None:
        self.values: dict[str, float] = {}
        self._hallucination_cd: dict[str, int] = {}

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    def register(self, player_id: str) -> None:
        """Register a new player at full sanity.

        Args:
            player_id: Unique player identifier.
        """
        self.values[player_id] = SANITY_MAX
        self._hallucination_cd[player_id] = 0

    def remove(self, player_id: str) -> None:
        """Remove a disconnected player.

        Args:
            player_id: Player to remove.
        """
        self.values.pop(player_id, None)
        self._hallucination_cd.pop(player_id, None)

    # ------------------------------------------------------------------
    # Per-tick update (server)
    # ------------------------------------------------------------------

    def update(self, players: dict, monsters: list) -> None:
        """Update all player sanity values for one server tick.

        Args:
            players:  {player_id: Player} — Hugo's Player dataclass objects.
            monsters: List of monster objects with x, y attributes.
        """
        for pid, player in players.items():
            if pid not in self.values:
                self.register(pid)

            near_teammate = self._has_teammate_nearby(pid, player, players)
            near_monster  = self._has_monster_nearby(player, monsters)

            if near_monster:
                self._drain(pid, SANITY_DRAIN_MONSTER)
            elif near_teammate:
                self._regen(pid, SANITY_REGEN_GROUP)
            else:
                self._drain(pid, SANITY_DRAIN_ALONE)

            # Tick hallucination cooldown
            if pid in self._hallucination_cd:
                self._hallucination_cd[pid] = max(0, self._hallucination_cd[pid] - 1)

    # ------------------------------------------------------------------
    # Query API (client + server)
    # ------------------------------------------------------------------

    def get(self, player_id: str) -> float:
        """Return current sanity for a player (0.0–100.0).

        Args:
            player_id: Target player.

        Returns:
            Sanity value, or 100.0 if not registered.
        """
        return self.values.get(player_id, SANITY_MAX)

    def set(self, player_id: str, value: float) -> None:
        """Directly set sanity — used for testing and server sync.

        Args:
            player_id: Target player.
            value:     New sanity value (clamped to 0–100).
        """
        self.values[player_id] = max(0.0, min(SANITY_MAX, value))

    def level(self, player_id: str) -> str:
        """Return sanity level label for a player.

        Args:
            player_id: Target player.

        Returns:
            One of: 'normal', 'low', 'critical'.
        """
        v = self.get(player_id)
        if v > SANITY_LOW_THRESHOLD:
            return "normal"
        if v > SANITY_CRIT_THRESHOLD:
            return "low"
        return "critical"

    def get_effects(self, player_id: str) -> dict:
        """Return rendering effect parameters for a player's sanity state.

        The renderer applies these each frame on the client side.

        Args:
            player_id: The local player's id.

        Returns:
            Dict with keys:
              shake_x, shake_y  (int): Screen shake pixels.
              vignette_alpha    (int): Edge darkening 0–200.
              hallucinate       (bool): Spawn a phantom player this frame.
        """
        v = self.get(player_id)
        effects = {"shake_x": 0, "shake_y": 0, "vignette_alpha": 0, "hallucinate": False}

        if v <= SANITY_LOW_THRESHOLD:
            intensity = int(5 * (1 - v / SANITY_LOW_THRESHOLD))
            effects["shake_x"] = random.randint(-intensity, intensity)
            effects["shake_y"] = random.randint(-intensity, intensity)
            effects["vignette_alpha"] = int(160 * (1 - v / SANITY_LOW_THRESHOLD))

        if v <= SANITY_CRIT_THRESHOLD:
            cd = self._hallucination_cd.get(player_id, 0)
            if cd == 0 and random.random() < 0.003:
                effects["hallucinate"] = True
                self._hallucination_cd[player_id] = 300

        return effects

    def to_dict(self) -> dict:
        """Serialise all sanity values for network broadcast.

        Returns:
            {player_id: sanity_float} mapping.
        """
        return dict(self.values)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _drain(self, player_id: str, amount: float) -> None:
        self.values[player_id] = max(0.0, self.values.get(player_id, SANITY_MAX) - amount)

    def _regen(self, player_id: str, amount: float) -> None:
        self.values[player_id] = min(SANITY_MAX, self.values.get(player_id, SANITY_MAX) + amount)

    def _has_teammate_nearby(self, pid: str, player, players: dict) -> bool:
        """Check if any other player is within regen radius."""
        for other_id, other in players.items():
            if other_id == pid:
                continue
            if math.hypot(other.x - player.x, other.y - player.y) <= TEAMMATE_REGEN_RADIUS:
                return True
        return False

    def _has_monster_nearby(self, player, monsters: list) -> bool:
        """Check if any monster is within drain radius."""
        for m in monsters:
            if math.hypot(m.x - player.x, m.y - player.y) <= MONSTER_DRAIN_RADIUS:
                return True
        return False
