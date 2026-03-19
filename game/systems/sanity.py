"""Sanity system for GROVE.

Tracks per-player sanity independently of Hugo's Player dataclass
(so we don't need to modify his file). Uses player_id as keys.

Sanity drains when:
  - Siren within 300px: -6/sec scaled by (1 - dist/300)
  - Weeping Angel within 250px and NOT frozen: -4/sec
  - Mimic active anywhere on map: -1/sec flat (psychological dread)
  - Player alone in multiplayer (no teammate within 600px): -0.5/sec
  (drains from multiple sources stack)

Sanity regens when:
  - No monster within 400px safe zone: +1.5/sec

Visual effects are requested via get_effects(player_id) and consumed
by the renderer each frame.
"""

from __future__ import annotations

import math
import random
import time

try:
    from config import (
        SANITY_MAX, SANITY_DRAIN_ALONE, SANITY_DRAIN_MONSTER,
        SANITY_REGEN_GROUP, SANITY_LOW_THRESHOLD, SANITY_CRIT_THRESHOLD,
    )
except ImportError:
    SANITY_MAX            = 100.0
    SANITY_DRAIN_ALONE    = 0.5
    SANITY_DRAIN_MONSTER  = 0.12
    SANITY_REGEN_GROUP    = 0.008
    SANITY_LOW_THRESHOLD  = 30.0
    SANITY_CRIT_THRESHOLD = 10.0

# --- Drain radii and rates ---
_SIREN_DRAIN_RADIUS    = 300.0
_SIREN_DRAIN_PER_SEC   = 6.0
_ANGEL_DRAIN_RADIUS    = 250.0
_ANGEL_DRAIN_PER_SEC   = 4.0
_MIMIC_DRAIN_PER_SEC   = 1.0
_ALONE_DRAIN_PER_SEC   = 0.5
_REGEN_PER_SEC         = 1.5
_SAFE_ZONE_RADIUS      = 400.0
_TEAMMATE_RADIUS       = 600.0

# Debug print interval
_DEBUG_INTERVAL        = 3.0


class SanitySystem:
    """Manages per-player sanity values and visual effect requests.

    Usage (server-side each tick):
        sanity.update(players, siren, angel, hollow, mimics, dt)

    Usage (client-side each frame):
        effects = sanity.get_effects(my_player_id)
        renderer.apply_sanity_effects(screen, effects)

    Attributes:
        values:              {player_id: float} sanity 0-100.
        _hallucination_cd:   {player_id: int} cooldown frames.
    """

    def __init__(self) -> None:
        self.values: dict[str, float] = {}
        self._hallucination_cd: dict[str, int] = {}
        self._last_debug: dict[str, float] = {}

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
        self._last_debug.pop(player_id, None)

    # ------------------------------------------------------------------
    # Per-tick update (server)
    # ------------------------------------------------------------------

    def update(self, players: dict, siren, angel, hollow, mimics: list, dt: float = 1.0 / 15.0) -> None:
        """Update all player sanity values for one server tick.

        Args:
            players: {player_id: Player} - Player dataclass objects.
            siren:   Siren monster object (with .x, .y) or None.
            angel:   Weeping Angel monster object (with .x, .y) or None.
            hollow:  Unused (kept for API compatibility). Always None.
            mimics:  List of active mimic objects (with .x, .y).
            dt:      Delta time in seconds for this tick.
        """
        now = time.time()

        for pid, player in players.items():
            if pid not in self.values:
                self.register(pid)
            if not getattr(player, "alive", True):
                continue

            siren_drain = 0.0
            angel_drain = 0.0
            mimic_drain = 0.0
            alone_drain = 0.0
            recovery = 0.0

            any_monster_in_safe_zone = False

            # --- Siren drain: -6/sec scaled by (1 - dist/300) ---
            if siren is not None:
                dist = math.hypot(siren.x - player.x, siren.y - player.y)
                if dist <= _SAFE_ZONE_RADIUS:
                    any_monster_in_safe_zone = True
                if dist <= _SIREN_DRAIN_RADIUS:
                    siren_drain = _SIREN_DRAIN_PER_SEC * (1.0 - dist / _SIREN_DRAIN_RADIUS) * dt

            # --- Weeping Angel drain: -4/sec if within 250px and NOT frozen ---
            if angel is not None:
                dist = math.hypot(angel.x - player.x, angel.y - player.y)
                if dist <= _SAFE_ZONE_RADIUS:
                    any_monster_in_safe_zone = True
                if dist <= _ANGEL_DRAIN_RADIUS and not getattr(angel, "frozen", False):
                    angel_drain = _ANGEL_DRAIN_PER_SEC * dt

            # --- Mimic drain: -1/sec flat if any mimic active ---
            if mimics:
                mimic_drain = _MIMIC_DRAIN_PER_SEC * dt
                # Check if any mimic is within safe zone
                for m in mimics:
                    dist = math.hypot(m.x - player.x, m.y - player.y)
                    if dist <= _SAFE_ZONE_RADIUS:
                        any_monster_in_safe_zone = True
                        break

            # --- Alone drain: -0.5/sec if no teammate within 600px (multiplayer only) ---
            if len(players) > 1 and not self._has_teammate_within(pid, player, players, _TEAMMATE_RADIUS):
                alone_drain = _ALONE_DRAIN_PER_SEC * dt

            total_drain = siren_drain + angel_drain + mimic_drain + alone_drain

            if total_drain > 0:
                self._drain(pid, total_drain)
            elif not any_monster_in_safe_zone:
                recovery = _REGEN_PER_SEC * dt
                self._regen(pid, recovery)

            # Tick hallucination cooldown
            if pid in self._hallucination_cd:
                self._hallucination_cd[pid] = max(0, self._hallucination_cd[pid] - 1)

            # Debug print once every 3 seconds per player
            last = self._last_debug.get(pid, 0.0)
            if now - last >= _DEBUG_INTERVAL:
                self._last_debug[pid] = now
                sanity = self.values[pid]
                print(f"[SANITY] {pid}: {sanity:.1f} | drains: siren={siren_drain:.2f} angel={angel_drain:.2f} mimic={mimic_drain:.2f} alone={alone_drain:.2f} recovery={recovery:.2f}")

    # ------------------------------------------------------------------
    # Query API (client + server)
    # ------------------------------------------------------------------

    def get(self, player_id: str) -> float:
        """Return current sanity for a player (0.0-100.0).

        Args:
            player_id: Target player.

        Returns:
            Sanity value, or 100.0 if not registered.
        """
        return self.values.get(player_id, SANITY_MAX)

    def set(self, player_id: str, value: float) -> None:
        """Directly set sanity - used for testing and server sync.

        Args:
            player_id: Target player.
            value:     New sanity value (clamped to 0-100).
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
              vignette_alpha    (int): Edge darkening 0-200.
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

    def _has_teammate_within(self, pid: str, player, players: dict, radius: float = 600.0) -> bool:
        """Check if any other player is within the given radius."""
        for other_id, other in players.items():
            if other_id == pid:
                continue
            if math.hypot(other.x - player.x, other.y - player.y) <= radius:
                return True
        return False
