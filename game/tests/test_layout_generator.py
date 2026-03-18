"""Focused tests for board-string map layout generation."""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from map.facility_map import FacilityMap
from map.layout_generator import GRID_COLS, GRID_ROWS, TILE_SIZE, build_layout_from_board


class TestLayoutGenerator(unittest.TestCase):
    def _blank_board(self) -> list[list[str]]:
        return [["-" for _ in range(GRID_COLS)] for _ in range(GRID_ROWS)]

    def _board_text(self, rows: list[list[str]]) -> str:
        return "\n".join("".join(row) for row in rows)

    def test_full_ground_row_compacts_to_one_rect(self) -> None:
        rows = self._blank_board()
        rows[GRID_ROWS - 1] = ["@" for _ in range(GRID_COLS)]
        layout = build_layout_from_board(self._board_text(rows))

        self.assertEqual(layout.world_width, GRID_COLS * TILE_SIZE)
        self.assertEqual(layout.world_height, GRID_ROWS * TILE_SIZE)
        self.assertEqual(layout.lowest_platform_row, GRID_ROWS - 1)
        self.assertEqual(
            layout.platforms,
            [(0, (GRID_ROWS - 1) * TILE_SIZE, GRID_COLS * TILE_SIZE, TILE_SIZE)],
        )

    def test_two_runs_in_row_become_two_rectangles(self) -> None:
        rows = self._blank_board()
        row_index = GRID_ROWS // 2
        for column in range(2, 7):
            rows[row_index][column] = "@"
        for column in range(10, 14):
            rows[row_index][column] = "@"

        layout = build_layout_from_board(self._board_text(rows))
        self.assertEqual(
            layout.platforms,
            [
                (2 * TILE_SIZE, row_index * TILE_SIZE, 5 * TILE_SIZE, TILE_SIZE),
                (10 * TILE_SIZE, row_index * TILE_SIZE, 4 * TILE_SIZE, TILE_SIZE),
            ],
        )

    def test_invalid_character_raises(self) -> None:
        rows = self._blank_board()
        rows[10][10] = "X"
        with self.assertRaises(ValueError):
            build_layout_from_board(self._board_text(rows))

    def test_loot_spawn_tile_is_extracted(self) -> None:
        rows = self._blank_board()
        rows[5][7] = "$"

        layout = build_layout_from_board(self._board_text(rows))
        self.assertEqual(layout.platforms, [])
        self.assertEqual(layout.loot_spawn_points, [(7 * TILE_SIZE + TILE_SIZE * 0.5, 5 * TILE_SIZE)])

    def test_facility_map_uses_generator_dimensions(self) -> None:
        world = FacilityMap()
        self.assertEqual(world.world_width, GRID_COLS * TILE_SIZE)
        self.assertEqual(world.world_height, GRID_ROWS * TILE_SIZE)
        self.assertGreater(len(world.platforms), 0)


if __name__ == "__main__":
    unittest.main()
