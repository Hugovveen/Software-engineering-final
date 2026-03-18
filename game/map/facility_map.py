"""String-board based facility map.

Board legend:
- `-` empty tile
- `@` solid platform tile
- `$` loot spawn tile

Grid size is 24x16 at 64px per tile, matching 1536x1024 world bounds.
"""

from __future__ import annotations

from pathlib import Path

from config import PLAYER_SIZE
from map.layout_generator import GRID_COLS, GRID_ROWS, TILE_SIZE, build_layout_from_board


def _paint_run(rows: list[list[str]], row: int, start_col: int, end_col_exclusive: int) -> None:
    for col in range(start_col, end_col_exclusive):
        rows[row][col] = "@"


def _build_default_board() -> str:
    rows = [["-" for _ in range(GRID_COLS)] for _ in range(GRID_ROWS)]

    _paint_run(rows, 15, 0, 24)

    _paint_run(rows, 12, 2, 8)
    _paint_run(rows, 12, 10, 16)
    _paint_run(rows, 12, 18, 23)

    _paint_run(rows, 10, 4, 10)
    _paint_run(rows, 10, 13, 19)

    _paint_run(rows, 8, 1, 5)
    _paint_run(rows, 8, 7, 12)
    _paint_run(rows, 8, 15, 21)

    _paint_run(rows, 6, 3, 7)
    _paint_run(rows, 6, 9, 14)
    _paint_run(rows, 6, 16, 21)

    _paint_run(rows, 4, 6, 11)
    _paint_run(rows, 4, 13, 18)

    _paint_run(rows, 2, 9, 15)

    rows[11][3] = "$"
    rows[9][8] = "$"
    rows[7][17] = "$"
    rows[5][10] = "$"
    rows[3][14] = "$"
    rows[13][21] = "$"

    return "\n".join("".join(row) for row in rows)


DEFAULT_LAYOUT_BOARD = _build_default_board()
BOARD_FILE_PATH = Path(__file__).with_name("board.txt")


def _load_board_text() -> str:
    if BOARD_FILE_PATH.exists():
        return BOARD_FILE_PATH.read_text(encoding="utf-8")
    return DEFAULT_LAYOUT_BOARD


class FacilityMap:
    """Stores map geometry used by server and renderer."""

    def __init__(self) -> None:
        board_text = _load_board_text()
        try:
            layout = build_layout_from_board(board_text)
        except ValueError:
            layout = build_layout_from_board(DEFAULT_LAYOUT_BOARD)
        self.layout_board = layout.board_rows
        self.world_width = layout.world_width
        self.world_height = layout.world_height
        self.platforms = layout.platforms
        self.ladders: list[tuple[int, int, int, int]] = list(layout.stair_positions)

        self.lowest_platform_row = layout.lowest_platform_row

        self.loot_spawn_points = list(layout.loot_spawn_points)
        if not self.loot_spawn_points:
            self.loot_spawn_points = [
                (128.0, 896.0),
                (384.0, 768.0),
                (704.0, 640.0),
                (960.0, 512.0),
                (1216.0, 640.0),
                (1408.0, 768.0),
            ]

        # Extraction/deposit zone rectangle (x, y, w, h).
        self.extraction_zone = (32, 848, 160, 96)

        self.enemy_spawn_points = {
            "mimic": (384, 912),
            "siren": (300, 390),
            "weeping_angel": (1200, 912),
            "hollow": (800, 912),
        }

    def floor_y(self) -> float:
        """Return the player top-y for standing on the lowest solid board row."""
        if self.lowest_platform_row is None:
            return float(self.world_height - PLAYER_SIZE[1])
        return float(self.lowest_platform_row * TILE_SIZE - PLAYER_SIZE[1])
