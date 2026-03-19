# GROVE

**A cooperative 2D horror survival game where you collect samples, meet quota, and escape before the lights go out.**

---

## Premise

You and a fellow researcher have been deployed to a derelict underground facility to collect biological samples for a shadowy employer. Each round you must gather enough loot to meet an escalating quota while navigating a multi-level facility crawling with monsters. Fail the quota, run out of time, or lose your sanity -- and it is game over for everyone.

---

## How to Run

**Requirements:** Python 3.13+, Pygame 2.6+

```bash
# Install dependencies
pip install pygame

# Start the server (terminal 1)
python main.py server

# Start a client (terminal 2 -- repeat for a second player)
python main.py client

# Optional: host/port overrides
python main.py server --host 0.0.0.0 --port 7000
python main.py client --host 192.168.1.5 --port 7000
```

Additional modes:

```bash
python main.py preview   # Enemy behavior preview window
python main.py editor    # Level layout editor
```

---

## Controls

| Action                             | Key(s)                        |
|------------------------------------|-------------------------------|
| Move left                          | `A` / Left Arrow              |
| Move right                         | `D` / Right Arrow             |
| Climb up                           | `W` / Up Arrow                |
| Climb down                         | `S` / Down Arrow              |
| Jump                               | `Space`                       |
| Sprint                             | `Left Shift` / `Right Shift`  |
| Interact (pick up / deposit loot)  | `E`                           |
| Start game (lobby)                 | `Enter`                       |
| Toggle music mute                  | `M`                           |
| Type name (title screen)           | Keyboard input, `Enter` to confirm |
| Select skin (title screen)         | Left / Right Arrow            |
| Select difficulty (title screen)   | Up / Down Arrow               |

---

## Game Flow

```
TITLE  -->  LOBBY  -->  PLAYING  -->  QUOTA_MET  -->  ENDING
                           |              |
                           |              +--> (timer expires) --> GAME_OVER
                           |
                           +--> LIGHTS OUT (mimics spawn at 3:00 remaining)
                           |
                           +--> (timer expires / all dead) --> GAME_OVER
```

1. **Title Screen** -- Enter your name, choose a skin (Researcher or Student), and pick a difficulty.
2. **Lobby** -- Wait for both players to connect. The host presses Enter to start.
3. **Playing** -- Explore the facility, pick up loot with `E`, and return it to the extraction zone (bottom-left) to deposit. A countdown timer is running.
4. **Lights Out** -- At 3 minutes remaining, mimics spawn for each player. Monsters become harder to track.
5. **Quota Met** -- Once deposited loot meets the target, a hidden escape ladder appears (column 12). Climb to the rooftop (y <= 32) to win.
6. **Ending / Game Over** -- Press Enter to return to the title screen.

---

## Enemies

### Weeping Angel
- **Freezes** when any player faces it within 400 px.
- When unobserved, **creeps toward the nearest player** at 65% of player walk speed.
- Deals **5 damage** on touch (scaled by difficulty), then freezes for 4 seconds.
- If off-screen for all players for 8+ seconds, **teleports behind** the nearest player.
- Server enforces a 2-second global attack cooldown between angel hits.

### Siren
- **Patrols** the middle platform, guarding the nearest cluster of loot spawn points.
- When a player comes within 350 px it **chases** at 140 px/s; within 250 px it emits a **lure scream** every 4 seconds.
- Deals **12 DPS** to players within 150 px (scaled by difficulty).
- Has a pulse/cast mechanic on a 6-second cooldown (charm pull is currently disabled; damage and audio remain active).
- Returns to its guard post if the player retreats beyond 500 px.

### Mimic
- Spawns at **Lights Out** (3 minutes remaining) -- one mimic per player.
- Copies the target player's **skin, name, and movement** with a 1.2-second delay, making it visually identical to a real player.
- **Touches** its target for 20 damage (scaled by difficulty), then flees at sprint speed for 5 seconds.
- **Flees** from non-target players within 300 px.
- Periodically pauses idle for 2--3 seconds every 30--45 seconds to mimic natural player behavior.

---

## Systems

### Sanity
- Each player has 0--100 sanity tracked server-side.
- **Drains** from multiple stacking sources:
  - Alone (no teammate within 180 px): 1/sec
  - Siren within 300 px: 15/sec
  - Weeping Angel within 200 px (unfrozen): 5/sec
  - Mimics active (global): 2/sec
- **Regenerates** at 1/sec only when no monster is within 400 px.
- **Low sanity** (below 35): screen shake and vignette darkening.
- **Critical sanity** (below 12): chance of hallucinations (phantom player sprites).

### Quota
- A target loot value must be deposited at the extraction zone before time runs out.
- Pick up loot scattered across the facility (`E`), carry it back to the extraction zone (bottom-left), and press `E` to deposit.
- Quota target and loot values are set by difficulty (see table below).

### Timer
- A countdown runs from the difficulty's starting time (240--420 seconds).
- If it hits zero before quota is met, the round ends in Game Over.

### Loot Respawn
- When all loot on the map is collected, a respawn timer starts.
- Respawn delay: 15 seconds (10 seconds on Expert).
- A fresh batch spawns at the same map positions with randomized values.

### Sprint
- Sprint energy pool: 2.4 seconds at full charge.
- Drains at 1.0/sec while sprinting; recharges at 0.8/sec while walking.
- Speed multiplier while sprinting: 1.45x.
- Cannot start sprinting unless energy is above 0.25.

### Health and Respawn
- Players have 100 HP. Taking any damage grants 2 seconds of invincibility.
- On death, a 10-second respawn timer starts. The player revives at the extraction zone.
- If all players are dead simultaneously with no pending respawns, the round ends.

---

## Difficulty

| Setting        | Quota | Damage Multiplier | Timer (sec) | Loot Value Range |
|----------------|------:|:-----------------:|:-----------:|:----------------:|
| **STUDENT**    |   150 |       0.5x        |     420     |     12 -- 20     |
| **RESEARCHER** |   300 |       1.0x        |     300     |     15 -- 25     |
| **EXPERT**     |   500 |       2.0x        |     240     |     10 -- 18     |

The first player to connect sets the difficulty. Expert features faster loot respawn (10 sec vs 15 sec) but tighter loot values and a shorter timer.

---

## Win / Lose Conditions

**Win:**
- Deposit enough loot to meet the quota, then climb the escape ladder to the rooftop before time runs out.

**Lose (any of the following):**
- The countdown timer reaches zero before quota is met.
- All players die with no respawns pending.
- The quota system's weekly cycle ends with insufficient collection (week-end game over).

---

## Tech Stack

| Component    | Technology                          |
|--------------|-------------------------------------|
| Language     | Python 3.13                         |
| Rendering    | Pygame 2.6                          |
| Networking   | Raw TCP sockets (JSON framing)      |
| Architecture | Authoritative server + thin client  |
| Tick rate    | 15 Hz server, 60 FPS client         |
| Resolution   | 1280 x 720                          |
| Map          | 24x16 tile grid, 64 px/tile (1536 x 1024 world) |

---

## Team

- **Justus** -- monsters, rendering, audio, game systems
- **Hugo** -- server architecture, networking, movement system

---

## Known Issues

- Siren charm-pull mechanic (forced player movement toward siren) is currently **disabled**; only proximity damage and audio lure are active.
- Mimic loot-stealing logic returns an empty list every tick (steal behavior is stubbed out).
- No `requirements.txt` file is present; the only external dependency is `pygame`.
- The quota week/day cycle (`QUOTA_SCALE`, `DAYS_PER_WEEK`) exists in code but the primary game flow uses a single-round timer model. The weekly escalation path is not fully exercised in normal play.
