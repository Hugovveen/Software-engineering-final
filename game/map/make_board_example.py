"""Writes a starter board template for manual level design.

Usage:
    python map/make_board_example.py

Output:
    map/board.example.txt
"""

from __future__ import annotations

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from map.facility_map import DEFAULT_LAYOUT_BOARD


def main() -> None:
    output_path = Path(__file__).with_name("board.example.txt")
    output_path.write_text(DEFAULT_LAYOUT_BOARD + "\n", encoding="utf-8")
    print(f"Wrote starter board to: {output_path}")
    print("Tip: copy it to map/board.txt, then edit @ and - tiles.")


if __name__ == "__main__":
    main()
