"""Movement helper functions for side-view platform and ladder controls.

Keeping movement logic in its own module makes it easier to test and adjust.
"""

from __future__ import annotations

from config import CLIMB_SPEED, GRAVITY, PLAYER_SPEED


def apply_player_input(player, input_state: dict, dt: float, floor_y: float) -> None:
    """Apply simple horizontal and ladder movement to a player object."""
    move_x = float(input_state.get("move_x", 0.0))
    climb = float(input_state.get("climb", 0.0))
    on_ladder = bool(input_state.get("on_ladder", False))

    player.vx = move_x * PLAYER_SPEED
    player.on_ladder = on_ladder

    if player.on_ladder:
        player.vy = climb * CLIMB_SPEED
    else:
        player.vy += GRAVITY * dt

    player.x += player.vx * dt
    player.y += player.vy * dt

    # Basic floor collision to keep prototype in-bounds.
    if player.y > floor_y:
        player.y = floor_y
        player.vy = 0.0
