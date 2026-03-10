"""Placeholder sound manager for future horror audio systems.

This scaffold keeps sound logic centralized so ambient and proximity systems can
be added later without touching unrelated gameplay code.
"""

from __future__ import annotations


class SoundSystem:
    """Minimal sound manager stub used by the client."""

    def __init__(self) -> None:
        self.enabled = True

    def play_footstep(self, player_id: str) -> None:
        """Placeholder for player footstep audio playback."""
        if not self.enabled:
            return
        # Future: route to pygame.mixer with positional audio.

    def play_ambient(self, zone_name: str) -> None:
        """Placeholder for ambient horror loop playback."""
        if not self.enabled:
            return
        # Future: change ambient track based on game tension.

    def play_proximity_warning(self, intensity: float) -> None:
        """Placeholder for mimic-nearby warning sound."""
        if not self.enabled:
            return
        # Future: map intensity to volume/pitch.
