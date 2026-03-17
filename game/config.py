"""Central configuration values for the game scaffold.

This file keeps constants in one place so teammates can easily tweak gameplay,
rendering, and networking values without searching through many modules.
"""

from __future__ import annotations

SERVER_HOST = "127.0.0.1"
SERVER_PORT = 5000
TICK_RATE = 15  # Server broadcasts per second (10-20 requested in brief)

SCREEN_WIDTH = 1024
SCREEN_HEIGHT = 576
FPS = 60

PLAYER_SPEED = 220.0
CLIMB_SPEED = 170.0
GRAVITY = 900.0

PLAYER_SIZE = (30, 48)
MIMIC_SIZE = (30, 48)

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

ANGEL_TELEPORT_PX      = 55      # pixels closed per teleport
ANGEL_COOLDOWN_FRAMES  = 50      # frames between teleports

HOLLOW_SPEED           = 30.0
HOLLOW_KILL_RANGE      = 22
HOLLOW_DWELL_FRAMES    = 180     # frames of overlap before kill
HOLLOW_REDIRECT_FRAMES = 180     # frames confused after item throw

# --- Lighting ---
FLASHLIGHT_RADIUS      = 190
FLASHLIGHT_ANGLE_DEG   = 55
DARKNESS_ALPHA         = 215     # 0=clear 255=black
