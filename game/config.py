"""Central configuration values for the game scaffold.

This file keeps constants in one place so teammates can easily tweak gameplay,
rendering, and networking values without searching through many modules.
"""

from __future__ import annotations

SERVER_HOST = "127.0.0.1"
SERVER_PORT = 5000
TICK_RATE = 15  # Server broadcasts per second (10-20 requested in brief)

SCREEN_WIDTH = 1920
SCREEN_HEIGHT = 1080
FPS = 60

PLAYER_SPEED = 220.0
CLIMB_SPEED = 170.0
GRAVITY = 900.0

PLAYER_SIZE = (30, 48)
MIMIC_SIZE = (30, 48)
