# Multiplayer 2D Horror Game Scaffold

This folder contains a clean starter architecture for a university Software Engineering group project.

## Game Concept

Players explore a **2D side-view research facility** together.  
Movement supports:
- left/right movement on the x-axis
- vertical movement through ladders and platforms

A **Mimic Entity** exists in the same world and will later evolve to learn player movement patterns. In this scaffold it moves randomly.

## Architecture Overview

- `client/`: networking + pygame client loop
- `server/`: authoritative game server + TCP message handling
- `entities/`: shared data models (`Player`, `Mimic`)
- `systems/`: isolated systems (movement, sound placeholder, behavior tracking)
- `map/`: simple side-view test map data
- `rendering/`: camera and renderer
- `config.py`: central constants
- `main.py`: start either server or client

## Networking Design

- Transport: **TCP sockets**
- Message format: **newline-delimited JSON**
- Main message types:
  - `PLAYER_JOIN`
  - `PLAYER_MOVE`
  - `GAME_STATE`

Server responsibilities:
- track connected players
- update mimic state
- receive movement input
- broadcast `GAME_STATE` at `TICK_RATE` (15 updates/sec)

Client responsibilities:
- capture input
- send movement messages
- receive and render game state

## How to Run

From this `game/` folder:

1. Install dependencies:
   - `pip install pygame`

2. Start server:
   - `python main.py server`
   - or `python main.py --server`

3. Start one or more clients (new terminals):
   - `python main.py client`
   - or `python main.py --client`

Optional host/port overrides:
- `python main.py server --host 0.0.0.0 --port 5000`
- `python main.py client --host 127.0.0.1 --port 5000`

## Notes for Team Extension

Good next steps:
- add real ladder overlap checks in movement
- add animation and sprite assets
- add mimic behavior based on `BehaviorTracker`
- implement proximity and ambient sounds in `SoundSystem`
- add collision handling with all platforms

## Week 1 Planning TODO

### Objective System (Core Goal)

- [ ] Define round objective as **collect loot and survive extraction**.
- [ ] Add a server-side `loot_items` state list (id, position, collected_by, collected_at).
- [ ] Add player loot inventory count to player state payload.
- [ ] Add collectible interaction rule (pickup range + one-time collection).
- [ ] Add round completion condition: collect required loot amount before timer ends.
- [ ] Add loss condition: round timer ends before required loot is collected.

### Level Design TODO

- [ ] Define first playable facility layout pass (rooms, corridors, vertical connectors).
- [ ] Place loot spawn zones with risk/reward balance (safe, medium, high danger areas).
- [ ] Add enemy pressure zones for `mimic`, `weeping_angel`, and `siren` patrol influence.
- [ ] Mark intended player routes: fast route vs safe route.
- [ ] Add extraction zone location and clear pathing constraints.
- [ ] Validate traversal: every loot zone must be reachable using current movement systems.

### UX Scaffolding TODO

- [ ] Add HUD element showing `loot_collected / loot_required`.
- [ ] Add objective banner text for current round state (`LOBBY`, `RUNNING`, `GAME_OVER`).
- [ ] Add event feed messages for loot pickup, objective progress, and extraction readiness.
