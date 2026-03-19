"""Central configuration values for the game scaffold.

This file keeps constants in one place so teammates can easily tweak gameplay,
rendering, and networking values without searching through many modules.
"""

from __future__ import annotations

SERVER_HOST = "127.0.0.1"
SERVER_PORT = 5000
TICK_RATE = 15  # Server broadcasts per second (10-20 requested in brief)

SCREEN_WIDTH = 1280
SCREEN_HEIGHT = 720
FPS = 60

PLAYER_SPEED = 143.0
CLIMB_SPEED = 110.0
GRAVITY = 900.0
JUMP_SPEED = 400.0
SPRINT_SPEED_MULTIPLIER = 1.45
SPRINT_MAX_ENERGY = 2.4
SPRINT_DRAIN_PER_SECOND = 1.0
SPRINT_RECHARGE_PER_SECOND = 0.8
SPRINT_MIN_START_ENERGY = 0.25

LOOT_PICKUP_RADIUS = 64.0
LOOT_SAMPLE_MIN_VALUE = 8
LOOT_SAMPLE_MAX_VALUE = 15

PLAYER_SIZE = (34, 54)
MIMIC_SIZE = (34, 54)
WEEPING_ANGEL_SIZE = (36, 58)
SIREN_SIZE = (38, 58)



# --- Sanity ---
SANITY_MAX             = 100.0
SANITY_DRAIN_ALONE     = 0.015   # per frame, no teammate nearby
SANITY_DRAIN_MONSTER   = 0.12    # per frame, monster within 200px
SANITY_REGEN_GROUP     = 0.008   # per frame, teammate within 180px
SANITY_LOW_THRESHOLD   = 35.0    # visual distortion starts
SANITY_CRIT_THRESHOLD  = 12.0    # hallucination chance starts

# --- Quota ---
BASE_QUOTA             = 200
QUOTA_SCALE            = 1.6     # multiplier each week
SAMPLE_MIN_VALUE       = 15
SAMPLE_MAX_VALUE       = 80
DAY_LENGTH_FRAMES      = 18000   # 5 minutes at 60fps
NIGHT_FRACTION         = 0.72    # time_of_day >= this = night

# --- Monsters ---
SIREN_DETECT_RANGE     = 280
SIREN_SANITY_DRAIN     = 0.18
SIREN_SPEED            = 55.0
SIREN_KILL_RANGE       = 30
ANGEL_TELEPORT_PX      = 55

ANGEL_TELEPORT_PX      = 55      # pixels closed per teleport
ANGEL_COOLDOWN_FRAMES  = 50      # frames between teleports

HOLLOW_SPEED           = 30.0
HOLLOW_KILL_RANGE      = 22
HOLLOW_DWELL_FRAMES    = 180     # frames of overlap before kill
HOLLOW_REDIRECT_FRAMES = 180     # frames confused after item throw

MIMIC_SPEED                    = 90.0

WEEPING_ANGEL_SPEED            = 170.0
WEEPING_ANGEL_ATTACK_RANGE     = 34.0
WEEPING_ANGEL_OBSERVE_RANGE    = 400.0

SIREN_AGGRO_RANGE              = 360.0
SIREN_PULSE_RADIUS             = 560.0
SIREN_CAST_DURATION            = 1.0
SIREN_CAST_TIME                = 1.5
SIREN_PATROL_SPEED             = 90.0
SIREN_CHASE_SPEED              = 140.0
SIREN_PULSE_COOLDOWN           = 6.0
SIREN_INITIAL_CAST_DELAY       = 2.0
SIREN_CHARM_DURATION           = 2.5
SIREN_CHARM_PULL_SPEED_L1      = 120.0
SIREN_CHARM_PULL_SPEED_L2      = 200.0
SIREN_CHARM_PULL_SPEED_L3      = 300.0

# Alias for current WeepingAngel implementation naming.
WEEPING_ANGEL_CHASE_SPEED      = WEEPING_ANGEL_SPEED

# --- Lighting ---
FLASHLIGHT_RADIUS      = 800
FLASHLIGHT_ANGLE_DEG   = 30
DARKNESS_ALPHA         = 230     # 0=clear 255=black
FLASHLIGHT_CONE_ALPHA  = 150     # darkness kept inside flashlight cone
FLASHLIGHT_GLOW_ALPHA  = 52      # darkness kept in local glow around player
