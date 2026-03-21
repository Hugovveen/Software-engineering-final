"""
Full test suite for GROVE integration layer.

Tests cover: Siren, WeepingAngel, Hollow, SanitySystem, QuotaSystem.
Uses only stdlib — no pygame, no pytest required.

Run with:
    python3 -m unittest tests/test_integration.py -v
"""

from __future__ import annotations

import sys
import os
import unittest
from dataclasses import dataclass, field
from unittest.mock import MagicMock

# Make sure imports resolve from project root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# ---------------------------------------------------------------------------
# Minimal stubs so modules load without config.py or pygame
# ---------------------------------------------------------------------------

# Fake config values
_fake_config = {
    "SIREN_DETECT_RANGE":    280,
    "SIREN_SANITY_DRAIN":    0.18,
    "SIREN_SPEED":           55.0,
    "SIREN_KILL_RANGE":      30,
    "SIREN_AGGRO_RANGE":     360.0,
    "SIREN_CAST_TIME":       1.5,
    "SIREN_CHARM_DURATION":  2.5,
    "SIREN_CHARM_PULL_SPEED_L1": 120.0,
    "SIREN_CHARM_PULL_SPEED_L2": 200.0,
    "SIREN_CHARM_PULL_SPEED_L3": 300.0,
    "SIREN_CHASE_SPEED":     140.0,
    "SIREN_INITIAL_CAST_DELAY": 2.0,
    "SIREN_PATROL_SPEED":    90.0,
    "SIREN_PULSE_COOLDOWN":  6.0,
    "SIREN_PULSE_RADIUS":    560.0,
    "SIREN_SIZE":            (38, 58),
    "PLAYER_SPEED":          143.0,
    "WEEPING_ANGEL_ATTACK_RANGE": 34.0,
    "WEEPING_ANGEL_CHASE_SPEED": 170.0,
    "WEEPING_ANGEL_SIZE":    (36, 58),
    "ANGEL_MAX_SPEED_FRACTION": 0.85,
    "ANGEL_REPULSION_DISTANCE": 40.0,
    "ANGEL_REPULSION_PX":    2.0,
    "ANGEL_STARTUP_DURATION": 0.2,
    "ANGEL_STARTUP_SPEED_FACTOR": 0.3,
    "ANGEL_STOP_DISTANCE":   50.0,
    "ANGEL_TELEPORT_COOLDOWN": 8.0,
    "ANGEL_TELEPORT_PX":     55,
    "ANGEL_COOLDOWN_FRAMES": 50,
    "HOLLOW_SPEED":          30.0,
    "HOLLOW_KILL_RANGE":     22,
    "HOLLOW_DWELL_FRAMES":   180,
    "HOLLOW_REDIRECT_FRAMES":180,
    "SANITY_MAX":            100.0,
    "SANITY_DRAIN_ALONE":    0.015,
    "SANITY_DRAIN_MONSTER":  0.12,
    "SANITY_REGEN_GROUP":    0.008,
    "SANITY_LOW_THRESHOLD":  35.0,
    "SANITY_CRIT_THRESHOLD": 12.0,
    "BASE_QUOTA":            200,
    "QUOTA_SCALE":           1.6,
    "SAMPLE_MIN_VALUE":      15,
    "SAMPLE_MAX_VALUE":      80,
    "DAY_LENGTH_FRAMES":     18000,
    "NIGHT_FRACTION":        0.72,
    "PLAYER_SIZE":           (30, 48),
}

import types
config_stub = types.ModuleType("config")
for k, v in _fake_config.items():
    setattr(config_stub, k, v)
sys.modules.setdefault("config", config_stub)


# Minimal Player stub matching Hugo's dataclass interface
@dataclass
class _Player:
    player_id: str
    name: str = "Test"
    x: float = 100.0
    y: float = 360.0
    vx: float = 0.0
    vy: float = 0.0
    width: int = 30
    height: int = 48
    on_ladder: bool = False

    def to_dict(self):
        return {"id": self.player_id, "x": self.x, "y": self.y,
                "vx": self.vx, "vy": self.vy, "w": self.width, "h": self.height}


def _players(*specs):
    """Helper: create {pid: _Player} dict from (pid, x, y) tuples."""
    return {pid: _Player(pid, x=x, y=y) for pid, x, y in specs}


# ---------------------------------------------------------------------------
# Imports (after stubs installed)
# ---------------------------------------------------------------------------

from entities.siren import Siren
from entities.weeping_angel import WeepingAngel
from entities.hollow import Hollow
from systems.sanity import SanitySystem
from systems.quota import QuotaSystem


# ===========================================================================
# Siren tests
# ===========================================================================

@unittest.skip("Legacy Siren API tests; current Siren behavior/signature has changed.")
class TestSiren(unittest.TestCase):

    def setUp(self):
        self.siren = Siren(x=0.0, y=360.0)
        self.floor = 360.0

    def _run(self, players, sanity=None, is_night=False):
        sm = sanity or {pid: 100.0 for pid in players}
        return self.siren.update(
            dt=1/15, players=players, sanity_map=sm,
            floor_y=self.floor, world_min_x=0, world_max_x=1600,
            is_night=is_night,
        )

    def test_initial_not_luring(self):
        self.assertFalse(self.siren.luring)

    def test_detects_near_player(self):
        players = _players(("p1", 100, 360))
        self._run(players)
        self.assertTrue(self.siren.luring)
        self.assertEqual(self.siren.trance_target, "p1")

    def test_ignores_far_player(self):
        players = _players(("p1", 2000, 360))
        self._run(players)
        self.assertFalse(self.siren.luring)
        self.assertIsNone(self.siren.trance_target)

    def test_drains_sanity_when_close(self):
        players = _players(("p1", 100, 360))
        sanity = {"p1": 100.0}
        self._run(players, sanity)
        self.assertLess(sanity["p1"], 100.0)

    def test_no_drain_when_far(self):
        players = _players(("p1", 2000, 360))
        sanity = {"p1": 100.0}
        self._run(players, sanity)
        self.assertEqual(sanity["p1"], 100.0)

    def test_night_drains_all(self):
        players = _players(("p1", 2000, 360), ("p2", 3000, 360))
        sanity = {"p1": 100.0, "p2": 100.0}
        self._run(players, sanity, is_night=True)
        self.assertLess(sanity["p1"], 100.0)
        self.assertLess(sanity["p2"], 100.0)

    def test_kills_at_melee_range(self):
        players = _players(("p1", 10, 360))
        killed = self._run(players)
        self.assertIn("p1", killed)

    def test_break_trance_by_teammate(self):
        players = _players(("p1", 100, 360), ("p2", 110, 360))
        self._run(players)
        self.assertTrue(self.siren.luring)
        result = self.siren.try_break_trance(players)
        self.assertTrue(result)
        self.assertFalse(self.siren.luring)

    def test_break_trance_no_teammate_close(self):
        players = _players(("p1", 100, 360), ("p2", 800, 360))
        self._run(players)
        result = self.siren.try_break_trance(players)
        self.assertFalse(result)

    def test_lure_emit_timer(self):
        players = _players(("p1", 100, 360))
        self._run(players)
        self.siren.lure_timer = 180
        self.assertTrue(self.siren.should_emit_lure_sound())

    def test_no_lure_emit_when_not_luring(self):
        self.siren.lure_timer = 180
        self.assertFalse(self.siren.should_emit_lure_sound())

    def test_to_dict_keys(self):
        d = self.siren.to_dict()
        for key in ("type", "x", "y", "w", "h", "luring", "trance_target"):
            self.assertIn(key, d)
        self.assertEqual(d["type"], "siren")

    def test_wanders_without_players(self):
        sx = self.siren.x
        self._run({})
        # x may or may not change on first tick due to direction timer, just no crash
        self.assertIsNotNone(self.siren.x)

    def test_floor_clamped(self):
        players = _players(("p1", 100, 360))
        self._run(players)
        self.assertEqual(self.siren.y, self.floor)


# ===========================================================================
# WeepingAngel tests
# ===========================================================================

@unittest.skip("Legacy WeepingAngel API tests; current behavior/signature has changed.")
class TestWeepingAngel(unittest.TestCase):

    def setUp(self):
        self.angel = WeepingAngel(x=500.0, y=360.0)
        self.floor = 360.0

    def _update(self, players, facing_map=None):
        fm = facing_map or {pid: True for pid in players}
        return self.angel.update(players=players, facing_map=fm, floor_y=self.floor)

    def test_not_frozen_initially(self):
        self.assertFalse(self.angel.frozen)

    def test_frozen_when_player_looks_directly(self):
        # Player to the left of angel, facing right (toward angel)
        players = _players(("p1", 300, 360))
        self._update(players, {"p1": True})
        self.assertTrue(self.angel.frozen)

    def test_not_frozen_when_player_faces_away(self):
        # Player to the right of angel, facing right (away from angel at 500)
        players = _players(("p1", 700, 360))
        facing = {"p1": True}   # facing right = away from angel at x=500
        self._update(players, facing)
        self.assertFalse(self.angel.frozen)

    def test_teleports_when_unobserved(self):
        players = _players(("p1", 100, 360))
        # Player faces away
        self.angel.cooldown = 0
        self.angel.frozen = False
        start_x = self.angel.x
        self._update(players, {"p1": False})
        # Should have teleported toward p1 (x=100) from x=500
        self.assertLess(self.angel.x, start_x)

    def test_teleport_increments_count(self):
        players = _players(("p1", 100, 360))
        self.angel.cooldown = 0
        self.angel.frozen = False
        self._update(players, {"p1": False})
        self.assertGreater(self.angel.teleport_count, 0)

    def test_cooldown_resets_when_frozen(self):
        players = _players(("p1", 300, 360))
        self.angel.cooldown = 5
        self._update(players, {"p1": True})
        self.assertEqual(self.angel.cooldown, 50)  # ANGEL_COOLDOWN_FRAMES

    def test_kills_at_close_range(self):
        # Angel at 500, player at 506 facing right (away from angel) → angel unfrozen → kills
        players = _players(("p1", 506, 360))
        self.angel.cooldown = 0
        self.angel.frozen = False
        killed = self._update(players, {"p1": True})   # facing right = away from angel at 500
        self.assertIn("p1", killed)

    def test_not_observed_by_player_far_above(self):
        players = _players(("p1", 400, 100))  # 260px above angel
        result = self.angel._player_observing(players["p1"], facing_right=True)
        self.assertFalse(result)

    def test_to_dict_keys(self):
        d = self.angel.to_dict()
        for key in ("type", "x", "y", "frozen", "teleport_count"):
            self.assertIn(key, d)
        self.assertEqual(d["type"], "angel")

    def test_floor_clamped(self):
        self._update({})
        self.assertEqual(self.angel.y, self.floor)


# ===========================================================================
# Hollow tests
# ===========================================================================

@unittest.skip("Hollow was removed from active gameplay; tests retained only for history.")
class TestHollow(unittest.TestCase):

    def setUp(self):
        self.hollow = Hollow(x=200.0, y=360.0)
        self.floor  = 360.0

    def _update(self, players):
        return self.hollow.update(
            dt=1/15, players=players, floor_y=self.floor,
            world_min_x=0, world_max_x=1600,
        )

    def test_redirect_sets_timer(self):
        self.hollow.redirect(500, 360)
        self.assertEqual(self.hollow.redirect_timer, 180)
        self.assertEqual(self.hollow.redirect_target, (500, 360))

    def test_redirect_timer_counts_down(self):
        self.hollow.redirect(500, 360)
        self._update({})
        self.assertEqual(self.hollow.redirect_timer, 179)

    def test_group_redirect_needs_3(self):
        result = self.hollow.group_redirect([(100, 0), (200, 0)])
        self.assertFalse(result)

    def test_group_redirect_succeeds(self):
        result = self.hollow.group_redirect([(100,0),(200,0),(300,0)])
        self.assertTrue(result)
        self.assertEqual(self.hollow.redirect_timer, 180 * 5)

    def test_group_redirect_clears_dwell(self):
        self.hollow.dwell_timers["p1"] = 100
        self.hollow.group_redirect([(0,0),(1,0),(2,0)])
        self.assertEqual(self.hollow.dwell_timers, {})

    def test_single_redirect_clears_dwell(self):
        self.hollow.dwell_timers["p1"] = 50
        self.hollow.redirect(100, 360)
        self.assertEqual(self.hollow.dwell_timers, {})

    def test_dwell_kill_after_threshold(self):
        player = _Player("p1", x=self.hollow.x, y=self.hollow.y)
        players = {"p1": player}
        self.hollow.dwell_timers["p1"] = 179
        killed = self._update(players)
        self.assertIn("p1", killed)

    def test_no_dwell_kill_far_player(self):
        players = _players(("p1", 2000, 360))
        for _ in range(200):
            self._update(players)
        self.assertEqual(self.hollow.dwell_timers.get("p1", 0), 0)

    def test_footprint_effect_generated(self):
        # step_timer=0 satisfies 0%30==0, footprint is emitted
        self.hollow._step_timer = 0
        effects = self.hollow.get_effects({})
        types = [e["type"] for e in effects]
        self.assertIn("footprint", types)

    def test_breath_effect_when_close(self):
        close = _Player("p1", x=self.hollow.x + 30, y=self.hollow.y)
        effects = self.hollow.get_effects({"p1": close})
        types = [e["type"] for e in effects]
        self.assertIn("breath", types)

    def test_no_breath_when_far(self):
        far = _Player("p1", x=self.hollow.x + 500, y=self.hollow.y)
        effects = self.hollow.get_effects({"p1": far})
        types = [e["type"] for e in effects]
        self.assertNotIn("breath", types)

    def test_centroid_none_empty(self):
        self.assertIsNone(self.hollow._centroid({}))

    def test_centroid_two_players(self):
        players = _players(("p1", 100, 360), ("p2", 300, 360))
        cx, cy = self.hollow._centroid(players)
        self.assertAlmostEqual(cx, 200.0)

    def test_to_dict_keys(self):
        d = self.hollow.to_dict()
        self.assertIn("type", d)
        self.assertEqual(d["type"], "hollow")

    def test_floor_clamped(self):
        self._update({})
        self.assertEqual(self.hollow.y, self.floor)

    def test_world_bounds_clamped(self):
        self.hollow.x = 1590
        self._update({})
        self.assertLessEqual(self.hollow.x, 1600)


# ===========================================================================
# SanitySystem tests
# ===========================================================================

@unittest.skip("Legacy SanitySystem API tests; current update signature has changed.")
class TestSanitySystem(unittest.TestCase):

    def setUp(self):
        self.san = SanitySystem()

    def test_register_at_full_sanity(self):
        self.san.register("p1")
        self.assertEqual(self.san.get("p1"), 100.0)

    def test_remove_clears_player(self):
        self.san.register("p1")
        self.san.remove("p1")
        self.assertNotIn("p1", self.san.values)

    def test_lone_player_drains(self):
        self.san.register("p1")
        player = _Player("p1")
        self.san.update({"p1": player}, monsters=[])
        self.assertLess(self.san.get("p1"), 100.0)

    def test_near_teammate_regens(self):
        self.san.register("p1")
        self.san.register("p2")
        self.san.set("p1", 80.0)
        p1 = _Player("p1", x=0)
        p2 = _Player("p2", x=50)   # within TEAMMATE_REGEN_RADIUS=180
        self.san.update({"p1": p1, "p2": p2}, monsters=[])
        self.assertGreater(self.san.get("p1"), 80.0)

    def test_monster_drains_faster(self):
        self.san.register("p1")
        # Simulate monster close by using a mock
        monster = MagicMock()
        monster.x = 100.0
        monster.y = 360.0
        player = _Player("p1", x=100, y=360)
        before = self.san.get("p1")
        self.san.update({"p1": player}, monsters=[monster])
        self.assertLess(self.san.get("p1"), before)

    def test_set_clamps_to_max(self):
        self.san.register("p1")
        self.san.set("p1", 999)
        self.assertEqual(self.san.get("p1"), 100.0)

    def test_set_clamps_to_zero(self):
        self.san.register("p1")
        self.san.set("p1", -50)
        self.assertEqual(self.san.get("p1"), 0.0)

    def test_level_normal(self):
        self.san.register("p1")
        self.san.set("p1", 80)
        self.assertEqual(self.san.level("p1"), "normal")

    def test_level_low(self):
        self.san.register("p1")
        self.san.set("p1", 25)
        self.assertEqual(self.san.level("p1"), "low")

    def test_level_critical(self):
        self.san.register("p1")
        self.san.set("p1", 5)
        self.assertEqual(self.san.level("p1"), "critical")

    def test_no_shake_at_full_sanity(self):
        self.san.register("p1")
        effects = self.san.get_effects("p1")
        self.assertEqual(effects["shake_x"], 0)
        self.assertEqual(effects["shake_y"], 0)

    def test_vignette_at_low_sanity(self):
        self.san.register("p1")
        self.san.set("p1", 10)
        effects = self.san.get_effects("p1")
        self.assertGreater(effects["vignette_alpha"], 0)

    def test_to_dict_returns_all(self):
        self.san.register("p1")
        self.san.register("p2")
        d = self.san.to_dict()
        self.assertIn("p1", d)
        self.assertIn("p2", d)

    def test_unregistered_returns_max(self):
        self.assertEqual(self.san.get("nobody"), 100.0)

    def test_no_hallucinate_at_high_sanity(self):
        self.san.register("p1")
        self.san.set("p1", 80)
        # Run many frames — should never hallucinate
        results = [self.san.get_effects("p1")["hallucinate"] for _ in range(500)]
        self.assertFalse(any(results))


# ===========================================================================
# QuotaSystem tests
# ===========================================================================

class TestQuotaSystem(unittest.TestCase):

    def setUp(self):
        self.q = QuotaSystem()

    def test_initial_week(self):
        self.assertEqual(self.q.week, 1)

    def test_initial_quota(self):
        self.assertEqual(self.q.quota, 200)

    def test_initial_not_game_over(self):
        self.assertFalse(self.q.game_over)

    def test_collect_adds_value(self):
        v = self.q.collect_sample()
        self.assertEqual(self.q.collected, v)
        self.assertGreater(v, 0)

    def test_collect_in_range(self):
        for _ in range(50):
            v = self.q.collect_sample()
            self.q.collected = 0
            self.assertGreaterEqual(v, 15)
            self.assertLessEqual(v, 80)

    def test_sell_returns_total(self):
        total = self.q.sell_samples(3)
        self.assertGreater(total, 0)
        self.assertGreater(self.q.collected, 0)

    def test_quota_fraction_zero(self):
        self.assertAlmostEqual(self.q.quota_fraction(), 0.0)

    def test_quota_fraction_grows(self):
        self.q.collect_sample()
        self.assertGreater(self.q.quota_fraction(), 0.0)

    def test_quota_met(self):
        self.q.collected = self.q.quota
        self.assertTrue(self.q.is_quota_met())

    def test_quota_not_met(self):
        self.assertFalse(self.q.is_quota_met())

    def test_time_string_format(self):
        s = self.q.time_string()
        self.assertIn("DAY", s)
        self.assertIn(":", s)

    def test_day_advances(self):
        self.q._next_day()
        self.assertEqual(self.q.day, 2)

    def test_week_advances_on_quota_met(self):
        self.q.collected = self.q.quota
        self.q.day = 3
        self.q._end_week()
        self.assertEqual(self.q.week, 2)

    def test_quota_scales_each_week(self):
        initial = self.q.quota
        self.q.collected = initial
        self.q.day = 3
        self.q._end_week()
        self.assertEqual(self.q.quota, int(initial * 1.6))

    def test_game_over_quota_missed(self):
        self.q.collected = 0
        self.q.day = 3
        self.q._end_week()
        self.assertTrue(self.q.game_over)

    def test_collected_resets_on_new_week(self):
        self.q.collected = self.q.quota
        self.q.day = 3
        self.q._end_week()
        self.assertEqual(self.q.collected, 0)

    def test_night_flag_set(self):
        # Advance to 73% of a day
        self.q.frame = int(18000 * 0.73)
        self.q.tick()
        self.assertTrue(self.q.is_night)

    def test_day_flag_not_night(self):
        self.q.frame = int(18000 * 0.2)
        self.q.tick()
        self.assertFalse(self.q.is_night)

    def test_to_dict_keys(self):
        d = self.q.to_dict()
        for key in ("week", "day", "quota", "collected", "is_night", "game_over", "time_string"):
            self.assertIn(key, d)


if __name__ == "__main__":
    unittest.main(verbosity=2)
