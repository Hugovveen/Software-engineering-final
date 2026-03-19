"""Quota and day/night cycle system for GROVE.

Tracks sample collection, weekly quotas, and the in-game clock.
Designed to live entirely on the server — state is broadcast in GAME_STATE.

Week structure:
  - 3 in-game days per week
  - Night phase starts at 72% of each day
  - Miss quota at week end → game over for all players
"""

from __future__ import annotations

import random

try:
    from config import (
        BASE_QUOTA, QUOTA_SCALE, SAMPLE_MIN_VALUE,
        SAMPLE_MAX_VALUE, DAY_LENGTH_FRAMES, NIGHT_FRACTION,
    )
except ImportError:
    BASE_QUOTA        = 200
    QUOTA_SCALE       = 1.6
    SAMPLE_MIN_VALUE  = 15
    SAMPLE_MAX_VALUE  = 80
    DAY_LENGTH_FRAMES = 18000
    NIGHT_FRACTION    = 0.72

DAYS_PER_WEEK = 3


class QuotaSystem:
    """Manages the economic pressure loop of GROVE.

    Attributes:
        week:       Current week number (starts at 1).
        day:        Current day within week (1–3).
        quota:      Sample value required this week.
        collected:  Sample value collected so far this week.
        frame:      Current frame counter within the day.
        is_night:   True during night phase.
        game_over:  True if quota was missed.
    """

    def __init__(self, target_quota: int | None = None) -> None:
        self.week      = 1
        self.day       = 1
        self.quota     = target_quota if target_quota is not None else BASE_QUOTA
        self.collected = 0
        self.frame     = 0
        self.is_night  = False
        self.game_over = False

    # ------------------------------------------------------------------
    # Per-tick update
    # ------------------------------------------------------------------

    def tick(self) -> None:
        """Advance one server frame. Call once per tick in game_server."""
        self.frame += 1
        fraction = self.frame / DAY_LENGTH_FRAMES
        self.is_night = fraction >= NIGHT_FRACTION

        if self.frame >= DAY_LENGTH_FRAMES:
            self._next_day()

    def _next_day(self) -> None:
        """Roll over to next day or end week."""
        self.frame = 0
        if self.day >= DAYS_PER_WEEK:
            self._end_week()
        else:
            self.day += 1

    def _end_week(self) -> None:
        """Check quota and either advance week or trigger game over."""
        if self.collected < self.quota:
            self.game_over = True
        else:
            self.week     += 1
            self.quota     = int(self.quota * QUOTA_SCALE)
            self.collected = 0
            self.day       = 1
            self.frame     = 0

    # ------------------------------------------------------------------
    # Sample collection
    # ------------------------------------------------------------------

    def collect_sample(self) -> int:
        """Add one randomly-valued sample to the weekly total.

        Returns:
            Value of the sample collected.
        """
        value = random.randint(SAMPLE_MIN_VALUE, SAMPLE_MAX_VALUE)
        self.collected += value
        return value

    def sell_samples(self, count: int) -> int:
        """Sell a batch of samples (called when player reaches dropzone).

        Args:
            count: Number of samples to sell.

        Returns:
            Total credits earned.
        """
        total = 0
        for _ in range(count):
            total += self.collect_sample()
        return total

    def add_value(self, amount: int) -> int:
        """Add deterministic value directly to collected quota progress.

        Args:
            amount: Non-negative score/value to add.

        Returns:
            Updated collected total.
        """
        increment = max(0, int(amount))
        self.collected += increment
        return self.collected

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    def quota_fraction(self) -> float:
        """Return collected/quota as a 0.0–1.0+ fraction."""
        return self.collected / max(1, self.quota)

    def is_quota_met(self) -> bool:
        """True when collected >= quota."""
        return self.collected >= self.quota

    def time_string(self) -> str:
        """Return readable in-game time string, e.g. 'DAY 2 - 09:14 AM'.

        Returns:
            Formatted time string.
        """
        frac  = self.frame / DAY_LENGTH_FRAMES
        hours = int(6 + frac * 18)
        mins  = int((frac * 18 * 60) % 60)
        ampm  = "AM" if hours < 12 else "PM"
        h12   = hours % 12 or 12
        return f"DAY {self.day} - {h12:02d}:{mins:02d} {ampm}"

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        """Convert state to JSON-safe dict for GAME_STATE broadcast."""
        return {
            "week":        self.week,
            "day":         self.day,
            "quota":       self.quota,
            "collected":   self.collected,
            "is_night":    self.is_night,
            "game_over":   self.game_over,
            "time_string": self.time_string(),
            "fraction":    self.quota_fraction(),
        }
