# 🌲 GROVE

> *A shady corporation sends you and your crew into an abandoned research facility to collect biological samples. You get paid per sample. You have a quota. The facility is not empty.*

GROVE is a 2D side-view co-op horror game built in Python with Pygame. 1–4 players explore a procedurally hostile facility while surviving monsters that each target a different player behavior — your hearing, your trust, your eyes, and your spatial awareness.

**University Software Engineering project — UvA 2025/26**

---

## 🎮 Game Concept

Players cooperate to explore a side-view research facility, collect biological samples, and extract before nightfall. A weekly quota forces increasingly risky decisions. The monsters get worse every week.

The horror comes from **uncertainty and communication** — limited visibility, proximity-based sound, and monsters that exploit the gaps between what you can see and what you can hear.

---

## 👾 Monsters

| Monster | Targets | Mechanic |
|---|---|---|
| **The Mimic** | Your movement | Learns player paths via BehaviorTracker, blends in and attacks |
| **The Siren** | Your hearing | Emits fake sample sounds, drains sanity on approach, trance broken by teammates |
| **The Weeping Angel** | Your eyes | Frozen when observed, teleports toward you the moment everyone looks away |
| **The Hollow** | Your spatial awareness | Completely invisible — detected only through footprints, dust, and breath |

---

## 🗂 Project Structure

```
game/
├── main.py                     # Entry point: python main.py server / client
├── config.py                   # All constants and tuning values
├── README.md
│
├── client/
│   ├── client_network.py       # TCP socket wrapper, JSON messaging
│   └── game_client.py          # Pygame loop, input, rendering
│
├── server/
│   ├── game_server.py          # Authoritative game loop, monster AI, broadcast
│   └── server_network.py       # TCP server wrapper
│
├── entities/
│   ├── player.py               # Player dataclass + serialisation
│   ├── mimic.py                # Mimic entity, random walk → pattern mimicry
│   ├── siren.py                # Siren monster — audio lure + sanity drain
│   ├── weeping_angel.py        # Weeping Angel — FOV freeze + teleport
│   └── hollow.py               # The Hollow — invisible, environmental cues only
│
├── systems/
│   ├── movement_system.py      # Gravity, ladders, horizontal movement
│   ├── sound_system.py         # SFX manager (proximity, ambient, footsteps)
│   ├── behavior_tracker.py     # Records player positions for Mimic AI
│   ├── sanity.py               # Per-player sanity drain/regen + visual effects
│   └── quota.py                # Weekly quota, day/night cycle, game over
│
├── map/
│   └── facility_map.py         # Map geometry: platforms, ladders, floor
│
├── rendering/
│   ├── renderer.py             # Pygame draw calls: world, players, monsters, HUD
│   ├── camera.py               # Side-view camera, world→screen coordinates
│   └── lighting.py             # Darkness overlay, flashlight cones, campfire light
│
└── tests/
    └── test_integration.py     # 74 unit tests, no display required
```

---

## 🚀 How to Run

### Requirements

```bash
pip install pygame
```

### Start the server

```bash
python main.py server
```

### Start a client (in a separate terminal)

```bash
python main.py client
```

### Custom host/port

```bash
python main.py server --host 0.0.0.0 --port 6000
python main.py client --host 192.168.1.x --port 6000
```

### Run tests (no pygame needed)

```bash
python3 -m unittest tests/test_integration.py -v
```

---

## 🌐 Networking

GROVE uses **TCP sockets with newline-delimited JSON messages**. The server runs at 15 ticks/second and is the single source of truth for all game state — clients send input, server sends world.

### Message types

**Client → Server**

| Type | Description |
|---|---|
| `PLAYER_JOIN` | Connect with player name |
| `PLAYER_MOVE` | Send `move_x`, `climb`, `on_ladder` each frame |
| `ITEM_THROW` | Throw an item at `land_x`, `land_y` — redirects The Hollow |
| `SELL_SAMPLES` | Sell `count` samples at the dropzone |

**Server → Client**

| Type | Description |
|---|---|
| `PLAYER_JOIN` | Confirms join, returns assigned `player_id` |
| `GAME_STATE` | Full world snapshot broadcast 15×/sec |
| `SAMPLE_SOLD` | Confirms sale, returns `total`, `collected`, `quota` |

### GAME_STATE format

```json
{
  "type": "GAME_STATE",
  "players": [{"id": "a1b2c3", "name": "Hugo", "x": 340, "y": 372, "vx": 220, "vy": 0, "w": 30, "h": 48}],
  "mimic":   {"x": 480, "y": 372, "vx": -60, "w": 30, "h": 48},
  "map":     {"platforms": [...], "ladders": [...]},
  "monsters": [
    {"type": "siren",  "x": 900, "luring": false, "trance_target": null},
    {"type": "angel",  "x": 1100, "frozen": true, "teleport_count": 4},
    {"type": "hollow", "effects": [], "redirected": false}
  ],
  "sanity":  {"a1b2c3": 87.4},
  "quota":   {"week": 1, "day": 2, "quota": 200, "collected": 80,
              "is_night": false, "game_over": false, "time_string": "DAY 2 - 09:14 AM"}
}
```

---

## 🔦 Key Systems

### Sanity
Each player has an independent sanity meter (0–100). It drains when you're alone or near a monster, and regens when you're near a teammate. Below 35: screen edges darken and shake. Below 12: hallucinations.

### Quota
3 in-game days per week. Night starts at 72% of each day — monsters become more active and flashlight range shrinks. Miss your quota at end of week → **CONTRACT TERMINATED** for everyone.

### Lighting
Full darkness overlay with a flashlight cone cut out per player. Cone angle and radius shrink at low sanity. Campfires create warm radial safe zones. The Hollow has no sprite — it's detected only through environmental effects the renderer draws.

### Sound
Centralized `SoundSystem` class handles footsteps, ambient horror loops, and proximity warnings. Volume and pitch are tied to monster distance. The Siren's lure sound is intentionally identical to a sample pickup.

---

## 👥 Team

| Dev | Ownership |
|---|---|
| Hugo | `player`, `mimic`, `facility_map`, `camera`, `movement_system`, `sound_system`, `behavior_tracker`, `client_network`, `server_network`, `main` |
| Justus | `siren`, `weeping_angel`, `hollow`, `sanity`, `quota`, `lighting`, `renderer` additions |
| Dev 3 | Proximity voice chat, client item-throw UI, Hollow sound cues |

---

## 🧪 Tests

74 unit tests covering all monsters and systems. Run without pygame or a display:

```bash
python3 -m unittest tests/test_integration.py -v
```

Tests use an in-file stub for `config.py` so they run anywhere — CI, teammate machines, GitHub Actions.

---

## 📋 Rubric

| Criterion | Implementation |
|---|---|
| Polymorphism | Monster hierarchy: Mimic, Siren, WeepingAngel, Hollow — shared interface, unique behavior |
| Special effects | Flashlight cones, fog of war, sanity distortion, screenshake, Hollow environmental cues, campfire glow |
| Git from start | Repository initialized before first commit |
| Clean code | Single-responsibility modules, all constants in `config.py`, no magic numbers |
| DocStrings | All classes and public methods documented |
| README | This file |
| Multiplayer bonus | Full TCP client-server, 15 ticks/sec, proximity voice chat (in progress) |
