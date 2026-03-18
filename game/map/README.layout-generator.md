# Board Layout Generator

This map workflow uses a string board to build platform geometry.

## Tile Legend
- `-` = empty
- `@` = platform/solid tile
- `$` = loot spawn point

## Grid
- Columns: `24`
- Rows: `16`
- Tile size: `64x64`
- World size: `1536x1024`

## Where it is used
- Parser/generator: `map/layout_generator.py`
- Default board + map integration: `map/facility_map.py`

`FacilityMap` now auto-loads `map/board.txt` if it exists.
If `map/board.txt` is missing, it falls back to the built-in default board.

## Start from an example
Generate a starter board file:

```powershell
python map/make_board_example.py
```

Copy it as your active layout:

```powershell
Copy-Item "map/board.example.txt" "map/board.txt" -Force
```

Now edit `map/board.txt` directly.

## Quick demo
Run:

```powershell
python map/layout_generator_demo.py
```

Use a custom board file:

```powershell
python map/layout_generator_demo.py --board-file map/custom_board.txt
```

Validate your active `board.txt`:

```powershell
python map/layout_generator_demo.py --board-file map/board.txt
```

Run the game preview with your board:

```powershell
python main.py preview
```

`custom_board.txt` must contain exactly 16 lines, each 24 characters long, with only `-`, `@`, and `$`.
