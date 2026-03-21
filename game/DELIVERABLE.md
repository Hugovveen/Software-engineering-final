# GROVE Final Deliverable

## 1) Project Summary

`GROVE` is a multiplayer 2D side-view horror prototype built with Python and `pygame`, using a server-authoritative architecture over TCP JSON messaging.

Players explore a facility, avoid enemies, collect loot samples, and deposit them in an extraction zone to meet quota targets before failure conditions trigger game over.

## 2) Delivered Scope

### Gameplay Loop
- Multiplayer movement (walk, jump, ladder movement, gravity).
- Sprint system with energy drain/recharge.
- Loot pickup (`E`) and deposit (`E`) mechanics.
- Extraction zone objective flow and quota progression.
- Day/night and sanity pressure systems.

### Enemy Systems
- `Mimic`: roaming/patrol behavior.
- `Siren`: aggro, casting pulse, charm tiers, pull behavior.
- `Weeping Angel`: freezes when observed, advances when unobserved.
- `Hollow`: invisible threat with environmental cues and redirect behavior.

### Rendering / UX
- Animated sprites for players and visible enemies.
- Textured floor/walls with fallback rendering.
- Dynamic lighting + flashlight cone.
- HUD for sanity, quota progress, carry value, and time state.
- Context interaction prompts.

### Tooling
- Playable local preview mode.
- Manual layout editor.
- Board-driven map workflow (`map/board.txt` with `-`, `@`, `$`).

## 3) Technical Architecture

### Runtime Components
- `server/game_server.py`: authoritative simulation and broadcast loop.
- `client/game_client.py`: main playable client input/network/render loop.
- `rendering/renderer.py`: world/entity/UI drawing pipeline.
- `rendering/lighting.py`: darkness, flashlight, sanity visual effects.
- `systems/`: movement, sanity, quota, behavior support systems.
- `entities/`: player, loot, and enemy model/behavior classes.

### Networking Model
- Transport: TCP sockets.
- Message format: newline-delimited JSON.
- Key messages:
  - `PLAYER_JOIN`
  - `PLAYER_MOVE`
  - `PLAYER_INTERACT`
  - `ITEM_THROW` (alternate client path)
  - `GAME_STATE` broadcast

### World / Map Data
- Grid format: `24 x 16` tiles, `64` px tile size.
- World size: `1536 x 1024`.
- Board symbols:
  - `-` empty
  - `@` platform tile
  - `$` loot spawn tile

## 4) How To Run

Run commands from the `game/` directory.

### Install dependency

```powershell
pip install pygame
```

### Start server

```powershell
python main.py server
```

### Start client

```powershell
python main.py client
```

### Start preview (local, no networking)

```powershell
python main.py preview
```

### Start layout editor

```powershell
python main.py editor
```

### Optional host/port overrides

```powershell
python main.py server --host 0.0.0.0 --port 5000
python main.py client --host 127.0.0.1 --port 5000
```

## 5) Controls

### Client / Preview
- `A` / `Left`: move left
- `D` / `Right`: move right
- `W` / `Up`: climb up
- `S` / `Down`: climb down
- `Space`: jump
- `Shift`: sprint
- `E`: interact (pickup/deposit)

### Editor
- `1`: platform mode
- `2`: ladder mode
- Left mouse drag: draw rectangle
- `Backspace`: delete last
- `C`: clear current mode list
- `E`: export to `map/layout_export.txt`
- `G`: grid size toggle (`8/16`)
- `Esc`: exit

## 6) Verification and Test Evidence

### Automated tests

```powershell
python -m unittest tests/test_layout_generator.py -v
python -m unittest tests/test_integration.py -v
```

### Manual acceptance checklist
- Server starts without crash.
- At least one client can join and move.
- Loot can be picked and deposited.
- Quota value increases after deposit.
- Lighting and HUD render correctly.
- Preview mode runs locally.
- Editor launches and exports layout file.

## 7) Known Limitations

- Balance tuning (enemy aggressiveness, lighting intensity, sanity pressure) is still configurable and may require playtest iteration.
- Some content flows still rely on placeholder audio/UX polish.
- Alternate client (`client/game_client_1.py`) is retained for experimentation and may differ slightly from main client behavior.

## 8) Team Contributions (Fill Before Submission)

| Member | Main Contributions |
|---|---|
| `Member 1` | `Networking / server loop / integration` |
| `Member 2` | `Gameplay systems / movement / quota / loot` |
| `Member 3` | `Rendering / lighting / asset integration` |
| `Member 4` | `Map tooling / editor / tests / docs` |

## 9) Demo Script (2–4 min)

1. Start `server`.
2. Start one or two `client` instances.
3. Show movement + sprint + climbing.
4. Collect loot and deposit it in extraction zone.
5. Show HUD/quota update and enemy pressure.
6. Exit and launch `preview` mode.
7. Launch `editor`, draw objects, and export.

## 10) Submission Checklist

- [ ] `README.md` is current and accurate.
- [ ] `DELIVERABLE.md` is complete (including contribution table).
- [ ] Required media captured (screenshots/video).
- [ ] Tests executed and results documented.
- [ ] Final code tagged/released (example: `v1.0-deliverable`).
