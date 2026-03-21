```
 ██████╗ ██████╗  ██████╗ ██╗   ██╗███████╗
██╔════╝ ██╔══██╗██╔═══██╗██║   ██║██╔════╝
██║  ███╗██████╔╝██║   ██║██║   ██║█████╗
██║   ██║██╔══██╗██║   ██║╚██╗ ██╔╝██╔══╝
╚██████╔╝██║  ██║╚██████╔╝ ╚████╔╝ ███████╗
 ╚═════╝ ╚═╝  ╚═╝ ╚═════╝   ╚═══╝  ╚══════╝
```

> A cooperative 2D horror survival game — collect samples, meet quota, and escape before time runs out.

## Overview

You and a fellow researcher have been deployed to a derelict underground facility by a shadowy employer. Your mission: collect biological samples scattered throughout a multi-level complex and meet an escalating quota before time runs out. The facility is not empty — three distinct monsters stalk its corridors, each with unique behaviors that demand different survival strategies.

The game is a side-scrolling 2D experience with server-authoritative multiplayer. Players collect loot samples scattered across platforms throughout the facility and deposit them at the extraction zone. A central flashlight toggle mechanic forces tough decisions — turning your flashlight off hides you from the Siren but leaves you vulnerable to the Angel. Meanwhile, your sanity drains from monster proximity and isolation, warping your perception the longer you stay underground.

Meet the quota and an escape ladder appears — climb to the rooftop and you win. But if the timer expires or all players die, the facility claims another crew.

## Quick Start

```bash
# Install dependencies
pip install pygame numpy

# Run server (terminal 1)
python main.py server

# Run client (terminal 2)
python main.py client

# Other modes
python main.py preview   # enemy behavior preview, no networking
python main.py editor    # level layout editor
```

## Controls

| Key | Action |
|-----|--------|
| `A` / `D` or `←` / `→` | Move left / right |
| `W` or `↑` | Climb ladder |
| `SPACE` | Jump |
| `SHIFT` | Sprint |
| `E` | Pick up / deposit loot |
| `F` | Toggle flashlight |
| `M` | Mute / unmute audio |
| `ESC` | Pause menu |
| `ENTER` | Confirm / start game |

## Game Flow

Title screen → character select (researcher / student) + difficulty → lobby (wait for players, Enter to start) → PLAYING (collect loot, survive) → LIGHTS OUT (mimics spawn at 3:00 remaining) → QUOTA MET (escape ladder appears at column 12) → ENDING (rooftop cutscene) or GAME OVER.

## Characters

- **Researcher**: Dark olive field jacket with equipment vest, sturdy boots. The experienced operative.
- **Student**: Deep burgundy astronomy sweater, slim jeans. The eager newcomer.

In solo mode, both skins are available. In multiplayer, each player gets a unique skin.

## Enemies

### Siren
- Patrols the middle platform, guarding loot clusters
- Detects players by flashlight — turning flashlight OFF hides you from detection
- Chases at 140 px/s within 350px, emits lure scream every 4s within 250px
- Deals 22 DPS within 150px (scaled by difficulty)
- Forces flashlight back ON if you linger nearby with it off for 4+ seconds (15s cooldown)
- Gentle charm pull toward siren when sanity < 50 and within 200px

### Weeping Angel
- Freezes instantly when any player faces her (direction-based, not distance-limited)
- Chases nearest player at 85% of player walk speed when unobserved
- Deals 35 damage on proximity (70px) when not frozen, 3s cooldown
- If player walks into her, she pushes back 2px/tick (repulsion, no magnet)
- Teleports behind nearest player if off-screen for 8+ seconds
- Brief 0.2s startup at 30% speed when unfreezing (no sudden jerk)

### Mimic
- Spawns at LIGHTS OUT (3 minutes remaining) — one per player
- Copies target player's skin and name in multiplayer; uses opposite skin in solo
- Steals loot items from the map (2s collection time, purely economic threat)
- Flees from nearby players within 250px at sprint speed
- Always has flashlight OFF (dark silhouette) — visual tell for observant players
- Periodic idle taunts every 20-30 seconds

## Systems

### Sanity
- 0–100 per player, tracked server-side
- Drains from: isolation (no teammate within 180px), Siren proximity (300px), Angel proximity (200px, unfrozen), active mimics
- Regenerates when no monster is within 400px
- Low sanity (< 35): screen shake, vignette
- Critical (< 12): hallucination chance
- At zero: 2 HP/sec drain until death

### Flashlight
- Toggle with F key
- ON: full flashlight cone illumination, Siren can detect you
- OFF: tiny 12px ambient glow, hidden from Siren, vulnerable to other threats
- Siren forces flashlight back on if you linger nearby too long (4s timer, 15s cooldown)
- Mimics always have flashlight off

### Quota & Loot
- Collect samples with E, carry to extraction zone (bottom-left), deposit with E
- Quota target set by difficulty. When met, escape ladder appears
- Loot respawns in batches when < 6 items remain (15s normal, 10s Expert)
- Solo players can carry 5 items; multiplayer players carry 3

### Health & Respawn
- Starting HP: 75. Damage grants 2s invincibility
- Multiplayer: 10s respawn timer at extraction zone
- Solo: death = instant game over

### Lighting
- Near-opaque darkness overlay with flashlight cone cutouts
- Sanity affects flashlight radius (shrinks as sanity drops)
- Campfire radial light sources
- Low-sanity vignette effect

### Audio
- Layered music system: lobby ambient, game tension, ending
- Distance-based siren audio (louder when closer, spike during scream)
- Heartbeat at low sanity, intensifies as sanity drops
- Programmatic SFX generation for missing audio assets

## Difficulty

| Mode | Quota | Timer | Damage | Loot Range | Carry Limit |
|------|------:|------:|-------:|-----------:|:-----------:|
| **STUDENT** | 150 | 7 min | ×0.5 | 12–20 | 5 solo / 3 multi |
| **RESEARCHER** | 300 | 5 min | ×1.0 | 15–25 | 5 solo / 3 multi |
| **EXPERT** | 500 | 4 min | ×2.0 | 10–18 | 5 solo / 3 multi |

First player to connect sets the difficulty.

## Win / Lose Conditions

**Win:** Deposit enough loot to meet quota → escape ladder appears at column 12 → climb to rooftop (y ≤ 150) → ending cutscene with playable rooftop walk.

**Lose (any):**
- Timer reaches zero before quota met
- All players die with no pending respawns (multiplayer)
- Solo player dies (instant game over)

## Project Structure

```
game/
├── main.py                  # Entry point — server, client, preview, editor
├── config.py                # All game constants in one place
├── client/
│   ├── client_network.py    # TCP client connection and message framing
│   └── game_client.py       # Pygame loop, input, state machine
├── server/
│   ├── server_network.py    # TCP server socket and message framing
│   └── game_server.py       # Authoritative game loop and state management
├── entities/
│   ├── enemy_base.py        # Abstract base class for enemies
│   ├── enemy_registry.py    # Enemy type factory
│   ├── loot.py              # Loot entity with gravity and platform collision
│   ├── mimic.py             # Mimic enemy — loot thief
│   ├── player.py            # Player data model
│   ├── siren.py             # Siren enemy — patrol, chase, pulse
│   └── weeping_angel.py     # Weeping Angel — freeze, chase, teleport
├── map/
│   ├── facility_map.py      # Tile-based level definition
│   └── layout_generator.py  # Procedural layout tools
├── rendering/
│   ├── camera.py            # Viewport tracking
│   ├── lighting.py          # Darkness overlay and flashlight cones
│   ├── renderer.py          # Full-frame rendering pipeline
│   └── sprite_loader.py     # Sprite sheet loading and animation
├── systems/
│   ├── audio_manager.py     # Music states, SFX, distance audio
│   ├── behavior_tracker.py  # Player position history
│   ├── movement_system.py   # Physics, ladders, platforms, sprint
│   ├── quota.py             # Quota tracking and weekly cycles
│   ├── sanity.py            # Per-player sanity drain and regen
│   └── sound_system.py      # Simple sound effect player
├── tests/
│   ├── test_integration.py  # Server-side integration tests
│   └── test_layout_generator.py
└── assets/                  # Sprites, audio, textures
```

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Language | Python 3.13 |
| Rendering | Pygame 2.6 |
| Audio | Pygame mixer + NumPy waveform generation |
| Networking | Raw TCP sockets with JSON framing |
| Architecture | Authoritative server (15 Hz) + thin client (60 FPS) |
| Resolution | 1280×720 (1536×1024 world, 24×16 tiles at 64px) |

## Team

- **Hugo** — backend architecture, networking, server game loop, entity systems, movement physics
- **Justus** — frontend rendering pipeline, audio system, level design, UI/UX, enemy AI, game screens

## Known Issues / Future Work

- Hollow enemy removed (stub kept for import compatibility)
- Mimic loot-stealing could be more aggressive in higher difficulties
- Integration tests include legacy suites that are currently skipped while enemy APIs are refactored
- Quota weekly escalation system exists in code but single-round model is primary
- Siren charm pull is intentionally gentle (0.8 px/s) to avoid feeling unfair
