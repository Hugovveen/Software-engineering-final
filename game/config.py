"""Central configuration values for the game scaffold.

This file keeps constants in one place so teammates can easily tweak gameplay,
rendering, and networking values without searching through many modules.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# --- Networking ---
# ---------------------------------------------------------------------------
SERVER_HOST = "127.0.0.1"               # IP address the server listens on
SERVER_PORT = 5000                       # TCP port for client connections
TICK_RATE = 15                           # Server broadcasts per second (10-20 is smooth)

# ---------------------------------------------------------------------------
# --- Display ---
# ---------------------------------------------------------------------------
SCREEN_WIDTH = 1280                      # Window width in pixels
SCREEN_HEIGHT = 720                      # Window height in pixels
FPS = 60                                 # Target frames per second (client)

# ---------------------------------------------------------------------------
# --- Player Movement ---
# ---------------------------------------------------------------------------
PLAYER_SPEED = 143.0                     # Base horizontal walk speed (px/s)
CLIMB_SPEED = 110.0                      # Vertical ladder/rope climb speed (px/s)
GRAVITY = 900.0                          # Downward acceleration (px/s^2)
JUMP_SPEED = 400.0                       # Initial upward velocity on jump (px/s)
SPRINT_SPEED_MULTIPLIER = 1.45           # Walk speed multiplier while sprinting
SPRINT_MAX_ENERGY = 2.4                  # Maximum sprint energy (seconds of sprint)
SPRINT_DRAIN_PER_SECOND = 1.0            # Energy consumed per second while sprinting
SPRINT_RECHARGE_PER_SECOND = 0.8         # Energy recovered per second while not sprinting
SPRINT_MIN_START_ENERGY = 0.25           # Minimum energy required to begin sprinting

# ---------------------------------------------------------------------------
# --- Player Stats ---
# ---------------------------------------------------------------------------
PLAYER_STARTING_HEALTH = 75              # HP players spawn with
PLAYER_MAX_CARRY_SOLO = 5                # Max loot items carried in solo mode
PLAYER_MAX_CARRY_MULTI = 3               # Max loot items carried in multiplayer

# ---------------------------------------------------------------------------
# --- Loot ---
# ---------------------------------------------------------------------------
LOOT_PICKUP_RADIUS = 64.0               # Distance (px) within which loot can be picked up
LOOT_SAMPLE_MIN_VALUE = 8               # Minimum value of a single loot sample
LOOT_SAMPLE_MAX_VALUE = 15              # Maximum value of a single loot sample
LOOT_RESPAWN_TIME_NORMAL = 15.0         # Seconds before loot respawns (normal difficulty)
LOOT_RESPAWN_TIME_EXPERT = 10.0         # Seconds before loot respawns (expert difficulty)
LOOT_MIN_ACTIVE_COUNT = 6               # Minimum number of loot items on the map
LOOT_MAX_ACTIVE_COUNT = 12              # Maximum number of loot items on the map

# ---------------------------------------------------------------------------
# --- Entity Sizes ---
# ---------------------------------------------------------------------------
PLAYER_SIZE = (34, 54)                   # (width, height) of the player hitbox in px
MIMIC_SIZE = (34, 54)                    # (width, height) of the mimic hitbox in px
WEEPING_ANGEL_SIZE = (36, 58)            # (width, height) of the weeping angel hitbox in px
SIREN_SIZE = (38, 58)                    # (width, height) of the siren hitbox in px

# ---------------------------------------------------------------------------
# --- Sanity ---
# ---------------------------------------------------------------------------
SANITY_MAX = 100.0                       # Maximum sanity value
SANITY_DRAIN_ALONE = 0.015               # Sanity lost per frame when no teammate is nearby
SANITY_DRAIN_MONSTER = 0.12              # Sanity lost per frame when a monster is within 200 px
SANITY_REGEN_GROUP = 0.008               # Sanity recovered per frame when teammate within 180 px
SANITY_LOW_THRESHOLD = 35.0              # Sanity below this triggers visual distortion
SANITY_CRIT_THRESHOLD = 12.0             # Sanity below this triggers hallucination chance
SANITY_ZERO_HP_DRAIN = 2.0               # HP lost per second when sanity reaches 0

# ---------------------------------------------------------------------------
# --- Quota ---
# ---------------------------------------------------------------------------
BASE_QUOTA = 200                         # Starting loot quota for round one
QUOTA_SCALE = 1.6                        # Multiplier applied to the quota each week
SAMPLE_MIN_VALUE = 15                    # Minimum random value for a quota sample
SAMPLE_MAX_VALUE = 80                    # Maximum random value for a quota sample
DAY_LENGTH_FRAMES = 18000                # Total frames in a full day cycle (5 min at 60 fps)
NIGHT_FRACTION = 0.72                    # Fraction of the day cycle at which night begins
ESCAPE_ROOF_Y = 150                      # Y-coordinate threshold that triggers an escape

# ---------------------------------------------------------------------------
# --- Monsters (shared) ---
# ---------------------------------------------------------------------------
DAMAGE_INVINCIBILITY = 2.0               # Seconds of invincibility after taking damage
RESPAWN_DELAY = 10.0                     # Seconds before a dead player respawns
MIMIC_SPAWN_THRESHOLD = 180.0            # Seconds remaining in the round when mimics begin spawning

# ---------------------------------------------------------------------------
# --- Siren ---
# ---------------------------------------------------------------------------
SIREN_DETECT_RANGE = 280                 # Distance (px) at which the siren detects players
SIREN_SANITY_DRAIN = 0.18               # Extra sanity drain per frame when siren is nearby
SIREN_SPEED = 55.0                       # Base movement speed (px/s)
SIREN_KILL_RANGE = 30                    # Distance (px) at which the siren kills on contact
SIREN_DPS = 22                           # Damage per second dealt by the siren
SIREN_DAMAGE_RADIUS = 150.0             # Radius (px) within which siren deals damage
SIREN_AGGRO_RANGE = 360.0               # Distance (px) at which the siren becomes aggressive
SIREN_PULSE_RADIUS = 560.0              # Radius (px) of the siren's pulse ability
SIREN_CAST_DURATION = 1.0               # Duration (s) the siren spends casting a pulse
SIREN_CAST_TIME = 1.5                   # Total time (s) for a cast animation cycle
SIREN_PATROL_SPEED = 90.0               # Movement speed (px/s) while patrolling
SIREN_CHASE_SPEED = 140.0               # Movement speed (px/s) while chasing a player
SIREN_PULSE_COOLDOWN = 6.0              # Seconds between consecutive pulse abilities
SIREN_INITIAL_CAST_DELAY = 2.0          # Seconds before the siren's first cast after aggro
SIREN_CHARM_DURATION = 2.5              # Duration (s) the charm effect lasts on a player
SIREN_CHARM_PULL_SPEED_L1 = 120.0       # Pull speed (px/s) during charm level 1
SIREN_CHARM_PULL_SPEED_L2 = 200.0       # Pull speed (px/s) during charm level 2
SIREN_CHARM_PULL_SPEED_L3 = 300.0       # Pull speed (px/s) during charm level 3
SIREN_FORCE_FLASHLIGHT_COOLDOWN = 15.0  # Seconds between forced flashlight activations
SIREN_FORCE_FLASHLIGHT_RANGE = 350.0    # Range (px) within which siren forces flashlight on
SIREN_FORCE_FLASHLIGHT_LINGER = 4.0     # Seconds the forced flashlight effect lingers

# ---------------------------------------------------------------------------
# --- Weeping Angel ---
# ---------------------------------------------------------------------------
WEEPING_ANGEL_SPEED = 170.0              # Base movement speed (px/s)
WEEPING_ANGEL_CHASE_SPEED = WEEPING_ANGEL_SPEED  # Alias used by the WeepingAngel class
WEEPING_ANGEL_ATTACK_RANGE = 34.0        # Distance (px) at which the angel can attack
WEEPING_ANGEL_OBSERVE_RANGE = 400.0      # Distance (px) within which the angel is observable
ANGEL_TELEPORT_PX = 55                   # Pixels closed per teleport blink
ANGEL_TELEPORT_COOLDOWN = 8.0            # Seconds between teleport blinks
ANGEL_COOLDOWN_FRAMES = 50              # Frames between teleport movements
ANGEL_HIT_DAMAGE = 35                    # Damage dealt per angel hit
ANGEL_HIT_RADIUS = 70.0                 # Radius (px) of an angel melee hit
ANGEL_HIT_COOLDOWN = 3.0                # Seconds between angel hits
ANGEL_MAX_SPEED_FRACTION = 0.85         # Fraction of player walk speed (angel max speed)
ANGEL_STOP_DISTANCE = 50.0              # Distance (px) at which the angel stops approaching
ANGEL_REPULSION_DISTANCE = 40.0         # Distance (px) at which the angel is pushed back
ANGEL_REPULSION_PX = 2.0                # Pixels pushed back per frame when too close
ANGEL_STARTUP_DURATION = 0.2            # Seconds of startup lag before full speed
ANGEL_STARTUP_SPEED_FACTOR = 0.3        # Speed multiplier during startup phase

# ---------------------------------------------------------------------------
# --- Mimic ---
# ---------------------------------------------------------------------------
MIMIC_SPEED = 90.0                       # Base movement speed (px/s)
MIMIC_HIT_DAMAGE = 25                    # Damage dealt per mimic hit

# ---------------------------------------------------------------------------
# --- Hollow (legacy) ---
# ---------------------------------------------------------------------------
HOLLOW_SPEED = 30.0                      # Base movement speed (px/s)
HOLLOW_KILL_RANGE = 22                   # Distance (px) at which the hollow kills on contact
HOLLOW_DWELL_FRAMES = 180               # Frames of overlap before hollow triggers a kill
HOLLOW_REDIRECT_FRAMES = 180            # Frames the hollow is confused after item throw

# ---------------------------------------------------------------------------
# --- Lighting ---
# ---------------------------------------------------------------------------
FLASHLIGHT_RADIUS = 800                  # Reach of the flashlight beam (px)
FLASHLIGHT_ANGLE_DEG = 30               # Half-angle of the flashlight cone (degrees)
DARKNESS_ALPHA = 248                     # Opacity outside flashlight (0=clear, 255=black)
FLASHLIGHT_CONE_ALPHA = 150             # Residual darkness kept inside flashlight cone
FLASHLIGHT_GLOW_ALPHA = 52              # Residual darkness in the local glow around player

# ---------------------------------------------------------------------------
# --- Damage & Combat ---
# ---------------------------------------------------------------------------
# Most damage values live alongside their monster section above. This section
# is reserved for cross-cutting combat rules that are not monster-specific.
# See DAMAGE_INVINCIBILITY and RESPAWN_DELAY under "Monsters (shared)".
