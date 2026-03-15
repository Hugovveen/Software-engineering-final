"""Movement helper functions for side-view platform and ladder controls.

Keeping movement logic in its own module makes it easier to test and adjust.
"""

from __future__ import annotations

from collections.abc import Sequence

from config import CLIMB_SPEED, GRAVITY, PLAYER_SPEED


def _clamp_axis(value: float) -> float:
    return max(-1.0, min(1.0, value))


def _overlaps_ladder(player, ladders: Sequence[tuple[float, float, float, float]]) -> bool:
    player_left = float(player.x)
    player_right = player_left + float(player.width)
    player_top = float(player.y)
    player_bottom = player_top + float(player.height)

    for ladder_x, ladder_y, ladder_w, ladder_h in ladders:
        ladder_left = float(ladder_x)
        ladder_right = ladder_left + float(ladder_w)
        ladder_top = float(ladder_y)
        ladder_bottom = ladder_top + float(ladder_h)

        if player_right <= ladder_left:
            continue
        if player_left >= ladder_right:
            continue
        if player_bottom <= ladder_top:
            continue
        if player_top >= ladder_bottom:
            continue
        return True

    return False


def apply_player_input(
    player,
    input_state: dict,
    dt: float,
    floor_y: float,
    world_width: float,
    ladders: Sequence[tuple[float, float, float, float]],
) -> None:
    """Apply simple horizontal and ladder movement to a player object."""
    move_x = _clamp_axis(float(input_state.get("move_x", 0.0)))
    climb = _clamp_axis(float(input_state.get("climb", 0.0)))
    requested_ladder = bool(input_state.get("on_ladder", False))

    player.vx = move_x * PLAYER_SPEED
    if move_x > 0.01:
        player.facing = 1
    elif move_x < -0.01:
        player.facing = -1

    overlap_ladder = _overlaps_ladder(player, ladders)
    player.on_ladder = overlap_ladder and (requested_ladder or abs(climb) > 0.01)

    if player.on_ladder:
        player.vy = climb * CLIMB_SPEED
    else:
        player.vy += GRAVITY * dt

    player.x += player.vx * dt
    player.y += player.vy * dt

    max_x = max(0.0, float(world_width) - float(player.width))
    if player.x < 0.0:
        player.x = 0.0
    elif player.x > max_x:
        player.x = max_x

    # Basic floor collision to keep prototype in-bounds.
    if player.y > floor_y:
        player.y = floor_y
        player.vy = 0.0
