"""String-board based level layout generator.

Board format:
- `-` means empty tile
- `@` means solid platform tile
- `$` means loot spawn tile
- `|` means stair/ladder tile

The parser validates board dimensions and converts contiguous `@` runs
on each row into platform rectangles.
"""

from __future__ import annotations

from dataclasses import dataclass

GRID_COLS = 24
GRID_ROWS = 16
TILE_SIZE = 64
EMPTY_TILE = "-"
PLATFORM_TILE = "@"
LOOT_TILE = "$"
STAIR_TILE = "|"


@dataclass(frozen=True)
class LayoutBuildResult:
    """Generated geometry and board metadata."""

    board_rows: tuple[str, ...]
    platforms: list[tuple[int, int, int, int]]
    stair_positions: list[tuple[int, int, int, int]]
    world_width: int
    world_height: int
    lowest_platform_row: int | None
    loot_spawn_points: list[tuple[float, float]]


def normalize_board_rows(board_text: str) -> tuple[str, ...]:
    """Return board rows without blank leading/trailing lines."""
    rows = [line.rstrip("\n\r") for line in board_text.splitlines()]
    trimmed = [line for line in rows if line.strip() != ""]
    return tuple(trimmed)


def validate_board(
    board_rows: tuple[str, ...],
    cols: int = GRID_COLS,
    rows: int = GRID_ROWS,
    empty_tile: str = EMPTY_TILE,
    platform_tile: str = PLATFORM_TILE,
    loot_tile: str = LOOT_TILE,
    stair_tile: str = STAIR_TILE,
) -> None:
    """Validate board dimensions and characters."""
    if len(board_rows) != rows:
        raise ValueError(f"Board must have exactly {rows} rows, got {len(board_rows)}")

    allowed = {empty_tile, platform_tile, loot_tile, stair_tile}
    for row_index, row in enumerate(board_rows):
        if len(row) != cols:
            raise ValueError(
                f"Row {row_index} must have exactly {cols} columns, got {len(row)}"
            )
        invalid = {character for character in row if character not in allowed}
        if invalid:
            invalid_list = ", ".join(sorted(invalid))
            raise ValueError(
                f"Row {row_index} has invalid tile characters: {invalid_list}"
            )


def compact_platform_runs(
    board_rows: tuple[str, ...],
    tile_size: int = TILE_SIZE,
    platform_tile: str = PLATFORM_TILE,
) -> list[tuple[int, int, int, int]]:
    """Convert contiguous platform tiles into world-space rectangles."""
    platforms: list[tuple[int, int, int, int]] = []

    for row_index, row in enumerate(board_rows):
        col = 0
        while col < len(row):
            if row[col] != platform_tile:
                col += 1
                continue

            run_start = col
            while col < len(row) and row[col] == platform_tile:
                col += 1
            run_end = col

            x = run_start * tile_size
            y = row_index * tile_size
            width = (run_end - run_start) * tile_size
            height = tile_size
            platforms.append((x, y, width, height))

    return platforms


def extract_loot_spawn_points(
    board_rows: tuple[str, ...],
    tile_size: int = TILE_SIZE,
    loot_tile: str = LOOT_TILE,
) -> list[tuple[float, float]]:
    """Extract world-space loot spawn points from board rows."""
    spawn_points: list[tuple[float, float]] = []
    half = tile_size * 0.5

    for row_index, row in enumerate(board_rows):
        for col_index, cell in enumerate(row):
            if cell != loot_tile:
                continue
            x = col_index * tile_size + half
            y = row_index * tile_size
            spawn_points.append((float(x), float(y)))

    return spawn_points


def extract_stair_positions(
    board_rows: tuple[str, ...],
    tile_size: int = TILE_SIZE,
    stair_tile: str = STAIR_TILE,
) -> list[tuple[int, int, int, int]]:
    """Extract ladder rects from stair tiles.

    Each | tile becomes a (x, y, w, h) ladder rect sized to one tile,
    with a small upward extension so players standing on the platform
    above can reach it.
    """
    positions: list[tuple[int, int, int, int]] = []
    for row_index, row in enumerate(board_rows):
        for col_index, cell in enumerate(row):
            if cell != stair_tile:
                continue
            x = col_index * tile_size
            y = row_index * tile_size - 4
            w = tile_size
            h = tile_size + 4
            positions.append((x, y, w, h))
    return positions


def build_layout_from_board(
    board_text: str,
    cols: int = GRID_COLS,
    rows: int = GRID_ROWS,
    tile_size: int = TILE_SIZE,
    empty_tile: str = EMPTY_TILE,
    platform_tile: str = PLATFORM_TILE,
    loot_tile: str = LOOT_TILE,
    stair_tile: str = STAIR_TILE,
) -> LayoutBuildResult:
    """Build a complete layout result from a board string."""
    board_rows = normalize_board_rows(board_text)
    validate_board(
        board_rows=board_rows,
        cols=cols,
        rows=rows,
        empty_tile=empty_tile,
        platform_tile=platform_tile,
        loot_tile=loot_tile,
        stair_tile=stair_tile,
    )

    platforms = compact_platform_runs(
        board_rows=board_rows,
        tile_size=tile_size,
        platform_tile=platform_tile,
    )

    stair_positions = extract_stair_positions(
        board_rows=board_rows,
        tile_size=tile_size,
        stair_tile=stair_tile,
    )

    loot_spawn_points = extract_loot_spawn_points(
        board_rows=board_rows,
        tile_size=tile_size,
        loot_tile=loot_tile,
    )

    lowest_row: int | None = None
    for row_index, row in enumerate(board_rows):
        if platform_tile in row:
            lowest_row = row_index

    return LayoutBuildResult(
        board_rows=board_rows,
        platforms=platforms,
        stair_positions=stair_positions,
        world_width=cols * tile_size,
        world_height=rows * tile_size,
        lowest_platform_row=lowest_row,
        loot_spawn_points=loot_spawn_points,
    )
