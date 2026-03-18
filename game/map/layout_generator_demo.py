"""Tiny runner for validating board-string layouts.

Usage:
    python map/layout_generator_demo.py
    python map/layout_generator_demo.py --board-file map/custom_board.txt
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from map.facility_map import DEFAULT_LAYOUT_BOARD
from map.layout_generator import build_layout_from_board


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Board layout generator demo")
    parser.add_argument(
        "--board-file",
        type=Path,
        default=None,
        help="Optional path to a text file containing 16 lines x 24 chars board",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    board_text = DEFAULT_LAYOUT_BOARD
    if args.board_file is not None:
        board_text = args.board_file.read_text(encoding="utf-8")

    layout = build_layout_from_board(board_text)

    print(f"world: {layout.world_width}x{layout.world_height}")
    print(f"rows: {len(layout.board_rows)} cols: {len(layout.board_rows[0]) if layout.board_rows else 0}")
    print(f"platform_rects: {len(layout.platforms)}")
    print(f"loot_spawns: {len(layout.loot_spawn_points)}")
    print(f"lowest_platform_row: {layout.lowest_platform_row}")
    print("sample_rects:")
    for rect in layout.platforms[:12]:
        print(f"  {rect}")


if __name__ == "__main__":
    main()
