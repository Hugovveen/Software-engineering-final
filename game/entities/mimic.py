"""Mimic enemy entity — copies a target player's movement with delay.

The mimic uses the same skin/name as its target player so it looks visually
identical. It replays the target's horizontal movement with a 1.2-second
delay, walks on platforms naturally, and flees from non-target players.
In multiplayer, neither player knows which entry is the mimic.
"""

from __future__ import annotations

import math
import random
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from config import GRAVITY, MIMIC_SIZE, PLAYER_SPEED, SPRINT_SPEED_MULTIPLIER

# Tuning constants
_POSITION_BUFFER_SIZE = 72       # ~4.8s at 15 ticks/sec
_REPLAY_DELAY_FRAMES = 18       # 1.2s delay at 15 ticks/sec
_FLEE_RADIUS = 300.0             # flee from non-target players within this
_TOUCH_RADIUS = 36.0             # distance to "touch" target player
_FLEE_DURATION = 5.0             # seconds to flee after touching or seeing non-target
_IDLE_PAUSE_MIN = 30.0           # seconds between random idle pauses
_IDLE_PAUSE_MAX = 45.0
_IDLE_DURATION_MIN = 2.0         # how long to stand still
_IDLE_DURATION_MAX = 3.0
_HUNT_SPEED = PLAYER_SPEED * 0.8


@dataclass
class Mimic:
    """Mimic enemy that replays its target's movement with a delay."""

    # ---- EnemyBase-compatible fields ----
    enemy_id: str = "mimic-1"
    enemy_type: str = "mimic"
    x: float = 480.0
    y: float = 360.0
    vx: float = 0.0
    vy: float = 0.0
    width: int = field(default=MIMIC_SIZE[0])
    height: int = field(default=MIMIC_SIZE[1])
    state: str = "idle"
    target_id: str | None = None

    # ---- Mimic-specific public fields ----
    target_player_id: str | None = None
    copied_skin: str = "researcher"
    copied_name: str = "Player"
    is_mimic: bool = True

    # ---- Internal fields ----
    _active: bool = field(default=False, repr=False)
    _facing: int = field(default=1, repr=False)
    _position_buffer: deque = field(default_factory=lambda: deque(maxlen=_POSITION_BUFFER_SIZE), repr=False)
    _flee_timer: float = field(default=0.0, repr=False)
    _flee_dir: int = field(default=1, repr=False)
    _idle_countdown: float = field(default=0.0, repr=False)
    _idle_remaining: float = field(default=0.0, repr=False)
    _touched_target: bool = field(default=False, repr=False)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def activate(
        self,
        target_player_id: str,
        skin: str,
        name: str,
        start_x: float,
        start_y: float,
    ) -> None:
        """Bind this mimic to a specific player and start following."""
        self.target_player_id = target_player_id
        self.copied_skin = skin
        self.copied_name = name
        self.x = start_x
        self.y = start_y
        self._active = True
        self._facing = 1
        self._position_buffer.clear()
        self._flee_timer = 0.0
        self._idle_countdown = random.uniform(_IDLE_PAUSE_MIN, _IDLE_PAUSE_MAX)
        self._idle_remaining = 0.0
        self._touched_target = False

    # ------------------------------------------------------------------

    def update(
        self,
        dt: float,
        world: Any,
        players: dict[str, Any],
        loot_items: list | None = None,
    ) -> list[str]:
        """Advance mimic simulation by one server tick.

        Returns a list of loot ids stolen this tick (always empty now).
        """
        if not self._active:
            return []

        target = players.get(self.target_player_id) if self.target_player_id else None

        # Record target's current position into the delay buffer
        if target is not None and getattr(target, "alive", True):
            self._position_buffer.append((
                float(target.x),
                float(target.y),
                float(target.vx),
                int(getattr(target, "facing", 1)),
            ))

        # Reset touched flag each tick
        self._touched_target = False

        # --- Flee logic ---
        if self._flee_timer > 0:
            self._flee_timer -= dt
            sprint_speed = PLAYER_SPEED * SPRINT_SPEED_MULTIPLIER
            self.vx = self._flee_dir * sprint_speed
            self.state = "fleeing"
        # --- Idle pause logic ---
        elif self._idle_remaining > 0:
            self._idle_remaining -= dt
            self.vx = 0.0
            self.state = "idle"
        else:
            # Check for non-target players nearby — flee from them
            flee_from = self._nearest_non_target_player(players)
            if flee_from is not None:
                dx = self.x - flee_from.x
                self._flee_dir = 1 if dx >= 0 else -1
                self._flee_timer = _FLEE_DURATION
                self.vx = self._flee_dir * PLAYER_SPEED * SPRINT_SPEED_MULTIPLIER
                self.state = "fleeing"
            # Check if touching target — deal damage and run
            elif target is not None and getattr(target, "alive", True):
                target_dist = math.hypot(target.x - self.x, target.y - self.y)
                if target_dist < _TOUCH_RADIUS:
                    self._touched_target = True
                    dx = self.x - target.x
                    self._flee_dir = 1 if dx >= 0 else -1
                    self._flee_timer = _FLEE_DURATION
                    self.vx = self._flee_dir * PLAYER_SPEED * SPRINT_SPEED_MULTIPLIER
                    self.state = "fleeing"
                else:
                    # Follow target with delay
                    self._follow_delayed(dt)
            else:
                # Target dead or missing — wander
                self._wander(dt)

            # Tick idle countdown
            self._idle_countdown -= dt
            if self._idle_countdown <= 0:
                self._idle_remaining = random.uniform(_IDLE_DURATION_MIN, _IDLE_DURATION_MAX)
                self._idle_countdown = random.uniform(_IDLE_PAUSE_MIN, _IDLE_PAUSE_MAX)

        # --- Physics ---
        self._apply_gravity(dt)
        self.x += self.vx * dt
        self._resolve_collisions(world)

        # Update facing
        if self.vx > 0.5:
            self._facing = 1
        elif self.vx < -0.5:
            self._facing = -1

        return []

    @property
    def touched_target_this_tick(self) -> bool:
        """True if the mimic touched its target this tick (server reads this for damage)."""
        return self._touched_target

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_player_dict(self) -> dict:
        """Serialize as a player dict so the renderer draws it identically."""
        return {
            "id": self.enemy_id,
            "name": self.copied_name,
            "x": self.x,
            "y": self.y,
            "vx": self.vx,
            "vy": self.vy,
            "w": self.width,
            "h": self.height,
            "on_ladder": False,
            "facing": self._facing,
            "charmed_by": None,
            "charm_timer": 0.0,
            "charm_level": 0,
            "sprinting": abs(self.vx) > PLAYER_SPEED * 1.1,
            "sprint_energy": 2.4,
            "carried_loot_count": 0,
            "carried_loot_value": 0,
            "health": 100,
            "alive": True,
            "skin": self.copied_skin,
            "is_mimic": True,
        }

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
            "target_id": self.target_player_id,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _follow_delayed(self, dt: float) -> None:
        """Follow target's x position from the delay buffer."""
        if len(self._position_buffer) > _REPLAY_DELAY_FRAMES:
            delayed = self._position_buffer[-_REPLAY_DELAY_FRAMES]
            target_x = delayed[0]
            target_facing = delayed[3]
        elif len(self._position_buffer) > 0:
            delayed = self._position_buffer[0]
            target_x = delayed[0]
            target_facing = delayed[3]
        else:
            return

        dx = target_x - self.x
        if abs(dx) > 4:
            speed = min(_HUNT_SPEED, abs(dx) / dt) if dt > 0 else _HUNT_SPEED
            self.vx = math.copysign(min(speed, _HUNT_SPEED), dx)
            self.state = "following"
        else:
            self.vx = 0.0
            self._facing = target_facing
            self.state = "idle"

    def _wander(self, dt: float) -> None:
        """Random wandering when target is unavailable."""
        if random.random() < 0.02:
            self.vx = random.choice([-1, 1]) * PLAYER_SPEED * 0.4
        self.state = "wandering"

    def _nearest_non_target_player(self, players: dict[str, Any]) -> Any | None:
        """Return the nearest non-target real player within flee radius."""
        best = None
        best_dist = _FLEE_RADIUS
        for pid, p in players.items():
            if pid == self.enemy_id:
                continue
            if pid == self.target_player_id:
                continue
            if not getattr(p, "alive", True):
                continue
            dist = math.hypot(p.x - self.x, p.y - self.y)
            if dist < best_dist:
                best_dist = dist
                best = p
        return best

    # ------------------------------------------------------------------
    # Physics helpers
    # ------------------------------------------------------------------

    def _apply_gravity(self, dt: float) -> None:
        """Apply downward acceleration."""
        self.vy += GRAVITY * dt

    def _resolve_collisions(self, world: Any) -> None:
        """Keep mimic inside world bounds and on top of platforms."""
        if world is None:
            return

        w_width = getattr(world, "world_width", 1536)
        w_height = getattr(world, "world_height", 1024)

        if self.x < 0:
            self.x = 0
            self.vx = abs(self.vx)
        elif self.x + self.width > w_width:
            self.x = w_width - self.width
            self.vx = -abs(self.vx)

        self.y += self.vy * (1.0 / 60.0)

        if self.y + self.height > w_height:
            self.y = w_height - self.height
            self.vy = 0.0

        platforms = getattr(world, "platforms", [])
        if self.vy >= 0:
            for px, py, pw, ph in platforms:
                if self.x + self.width > px and self.x < px + pw:
                    feet_y = self.y + self.height
                    if py <= feet_y <= py + ph:
                        self.y = py - self.height
                        self.vy = 0.0
                        break
