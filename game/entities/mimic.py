"""Mimic enemy entity — a loot thief that steals quota items.

In solo mode the mimic uses the OPPOSITE skin. In multiplayer it copies
the target player's skin and name. It never attacks — its threat is purely
economic: every item it steals is permanently removed from the pool.

Stays on its current platform level, lands on platforms with gravity,
and never floats or spins.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Any

from config import GRAVITY, MIMIC_SIZE, PLAYER_SPEED, SPRINT_SPEED_MULTIPLIER

# Tuning constants
_FLEE_RADIUS = 250.0
_FLEE_SPEED = PLAYER_SPEED * SPRINT_SPEED_MULTIPLIER
_SEEK_SPEED = PLAYER_SPEED * 0.9       # 90% of player walk speed
_COLLECT_TIME = 2.0                     # seconds near loot to steal it
_COLLECT_RADIUS = 40.0
_TAUNT_INTERVAL_MIN = 20.0
_TAUNT_INTERVAL_MAX = 30.0
_TAUNT_DURATION = 1.5
_SPAWN_FLASH_DURATION = 0.5
_TERMINAL_VELOCITY = 600.0


@dataclass
class Mimic:
    """Mimic enemy that steals loot items from the map."""

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
    stolen_loot_count: int = 0

    # ---- Internal fields ----
    _active: bool = field(default=False, repr=False)
    _solo: bool = field(default=False, repr=False)
    _facing: int = field(default=1, repr=False)
    _on_ladder: bool = field(default=False, repr=False)
    _collect_timer: float = field(default=0.0, repr=False)
    _collecting_loot_id: str | None = field(default=None, repr=False)
    _taunt_countdown: float = field(default=0.0, repr=False)
    _taunt_remaining: float = field(default=0.0, repr=False)
    _spawn_flash_timer: float = field(default=0.0, repr=False)

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
        solo: bool = False,
    ) -> None:
        """Bind this mimic to a specific player and start thieving."""
        self.target_player_id = target_player_id
        self.copied_skin = skin
        self.copied_name = name
        self.x = start_x
        self.y = start_y
        self._active = True
        self._solo = solo
        self._facing = 1
        self._on_ladder = False
        self._collect_timer = 0.0
        self._collecting_loot_id = None
        self._taunt_countdown = random.uniform(_TAUNT_INTERVAL_MIN, _TAUNT_INTERVAL_MAX)
        self._taunt_remaining = 0.0
        self._spawn_flash_timer = _SPAWN_FLASH_DURATION
        self.stolen_loot_count = 0

    # ------------------------------------------------------------------

    def update(
        self,
        dt: float,
        world: Any,
        players: dict[str, Any],
        loot_items: list | None = None,
    ) -> list[str]:
        """Advance mimic simulation by one server tick.

        Returns a list of loot_ids stolen this tick.
        """
        if not self._active:
            return []

        self._on_ladder = False

        stolen_ids: list[str] = []

        # Tick spawn flash
        if self._spawn_flash_timer > 0:
            self._spawn_flash_timer -= dt

        # Get geometry from world
        platforms = getattr(world, "platforms", []) if world else []
        floor_y = float(world.floor_y()) if world and hasattr(world, "floor_y") else 960.0

        # Check if any player is nearby — flee takes priority
        nearest_player_dist = self._nearest_player_distance(players)

        if nearest_player_dist is not None and nearest_player_dist < _FLEE_RADIUS:
            # Flee — just run horizontally away
            nearest_p = self._nearest_player(players)
            if nearest_p is not None:
                dx = self.x - nearest_p.x
                self._flee_dir = 1 if dx >= 0 else -1
                self.vx = self._flee_dir * _FLEE_SPEED
                self._on_ladder = False
                self.state = "fleeing"
                self._collect_timer = 0.0
                self._collecting_loot_id = None
        elif self._taunt_remaining > 0:
            # Taunt — face nearest player and stand still
            self._taunt_remaining -= dt
            self.vx = 0.0
            self._on_ladder = False
            target = players.get(self.target_player_id)
            if target is not None:
                self._facing = 1 if target.x > self.x else -1
            self.state = "idle"
        else:
            # Tick taunt countdown
            self._taunt_countdown -= dt
            if self._taunt_countdown <= 0:
                self._taunt_remaining = _TAUNT_DURATION
                self._taunt_countdown = random.uniform(_TAUNT_INTERVAL_MIN, _TAUNT_INTERVAL_MAX)

            # Seek and collect loot with navigation
            stolen_ids = self._seek_loot_navigated(dt, loot_items)

        # --- Physics ---
        self.vy += GRAVITY * dt
        self.vy = min(self.vy, _TERMINAL_VELOCITY)

        self.x += self.vx * dt
        self.y += self.vy * dt

        self._resolve_collisions(world, platforms, floor_y)

        # Update facing
        if self.vx > 0.5:
            self._facing = 1
        elif self.vx < -0.5:
            self._facing = -1

        return stolen_ids

    @property
    def touched_target_this_tick(self) -> bool:
        """Always False — mimic no longer attacks."""
        return False

    # ------------------------------------------------------------------
    # Loot seeking with stair navigation
    # ------------------------------------------------------------------

    def _seek_loot_navigated(self, dt: float, loot_items: list | None) -> list[str]:
        """Move toward nearest same-level loot."""
        stolen: list[str] = []
        if not loot_items:
            self.vx = 0.0
            self.state = "idle"
            return stolen

        # Find nearest uncollected loot on the same platform level
        nearest_loot = None
        nearest_dist = float("inf")
        for loot in loot_items:
            if getattr(loot, "collected", False):
                continue
            lx = float(getattr(loot, "x", 0))
            ly = float(getattr(loot, "y", 0))
            # Only consider loot on the same level
            if abs(self.y - ly) >= 40:
                continue
            dist = math.hypot(lx - self.x, ly - self.y)
            if dist < nearest_dist:
                nearest_dist = dist
                nearest_loot = loot

        if nearest_loot is None:
            self.vx = 0.0
            self.state = "idle"
            return stolen

        loot_id = getattr(nearest_loot, "loot_id", "")
        loot_x = float(getattr(nearest_loot, "x", 0))
        loot_y = float(getattr(nearest_loot, "y", 0))

        if nearest_dist <= _COLLECT_RADIUS:
            # Standing near loot — collecting
            self.vx = 0.0
            self.state = "collecting"
            if self._collecting_loot_id == loot_id:
                self._collect_timer += dt
                if self._collect_timer >= _COLLECT_TIME:
                    stolen.append(loot_id)
                    self.stolen_loot_count += 1
                    self._collect_timer = 0.0
                    self._collecting_loot_id = None
                    print(f"[MIMIC] Stole loot at ({self.x:.0f},{self.y:.0f}), carrying {self.stolen_loot_count} items")
            else:
                self._collecting_loot_id = loot_id
                self._collect_timer = 0.0
        else:
            # Same level — walk directly toward loot
            dx = loot_x - self.x
            self.vx = math.copysign(min(_SEEK_SPEED, abs(dx) / max(dt, 0.001)), dx)
            self.state = "seeking"
            self._collect_timer = 0.0
            self._collecting_loot_id = None

        return stolen

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _nearest_player(self, players: dict[str, Any]) -> Any | None:
        best = None
        best_dist = float("inf")
        for pid, p in players.items():
            if not getattr(p, "alive", True):
                continue
            dist = math.hypot(p.x - self.x, p.y - self.y)
            if dist < best_dist:
                best_dist = dist
                best = p
        return best

    def _nearest_player_distance(self, players: dict[str, Any]) -> float | None:
        best_dist: float | None = None
        for pid, p in players.items():
            if not getattr(p, "alive", True):
                continue
            dist = math.hypot(p.x - self.x, p.y - self.y)
            if best_dist is None or dist < best_dist:
                best_dist = dist
        return best_dist

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_player_dict(self) -> dict:
        """Serialize as a player dict so the renderer draws it identically."""
        d = {
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
            "carried_loot_count": self.stolen_loot_count,
            "carried_loot_value": 0,
            "health": 100,
            "alive": True,
            "skin": self.copied_skin,
            "is_mimic": True,
            "flashlight_on": False,
        }
        if self._spawn_flash_timer > 0:
            d["spawn_flash"] = True
        return d

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
    # Physics
    # ------------------------------------------------------------------

    def _resolve_collisions(self, world: Any, platforms: list, floor_y: float) -> None:
        """Keep mimic inside world bounds and on top of platforms."""
        w_width = getattr(world, "world_width", 1536) if world else 1536
        w_height = getattr(world, "world_height", 1024) if world else 1024

        # Horizontal bounds
        if self.x < 0:
            self.x = 0
            self.vx = abs(self.vx) * 0.5
        elif self.x + self.width > w_width:
            self.x = w_width - self.width
            self.vx = -abs(self.vx) * 0.5

        # Floor
        if self.y + self.height > w_height:
            self.y = w_height - self.height
            self.vy = 0.0
            self._on_ladder = False

        # Platform landing (only when falling)
        if self.vy >= 0:
            for px, py, pw, ph in platforms:
                plat_left = float(px)
                plat_right = plat_left + float(pw)
                plat_top = float(py)
                # Must overlap horizontally
                if self.x + self.width <= plat_left or self.x >= plat_right:
                    continue
                feet_y = self.y + self.height
                # Landing on top of platform
                if plat_top <= feet_y <= plat_top + float(ph):
                    self.y = plat_top - self.height
                    self.vy = 0.0
                    break

        # Floor y check
        if self.y + self.height > floor_y + self.height:
            self.y = floor_y
            self.vy = 0.0
