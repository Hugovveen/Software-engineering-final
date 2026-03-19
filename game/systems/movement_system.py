"""Movement helper functions for side-view platform and ladder controls.

Keeping movement logic in its own module makes it easier to test and adjust.
"""

from __future__ import annotations

from collections.abc import Sequence

from config import (
    CLIMB_SPEED,
    GRAVITY,
    JUMP_SPEED,
    PLAYER_SPEED,
    SPRINT_DRAIN_PER_SECOND,
    SPRINT_MAX_ENERGY,
    SPRINT_MIN_START_ENERGY,
    SPRINT_RECHARGE_PER_SECOND,
    SPRINT_SPEED_MULTIPLIER,
)


def _clamp_axis(value: float) -> float:
    return max(-1.0, min(1.0, value))


def _overlaps_ladder(player, ladders: Sequence[tuple[float, float, float, float]]) -> bool:
    player_center_x = float(player.x) + float(player.width) * 0.5
    player_top = float(player.y)
    player_bottom = player_top + float(player.height)

    for ladder_x, ladder_y, ladder_w, ladder_h in ladders:
        ladder_left = float(ladder_x)
        ladder_right = ladder_left + float(ladder_w)
        ladder_top = float(ladder_y)
        ladder_bottom = ladder_top + float(ladder_h)

        # Player center x must be within ladder horizontal bounds (±20px tolerance)
        if player_center_x < ladder_left - 20 or player_center_x > ladder_right + 20:
            continue
        if player_bottom <= ladder_top:
            continue
        if player_top >= ladder_bottom:
            continue
        return True

    return False


def _horizontal_overlap(
    left_a: float,
    right_a: float,
    left_b: float,
    right_b: float,
) -> bool:
    return right_a > left_b and left_a < right_b


def _resolve_platform_landing(
    player,
    previous_y: float,
    platforms: Sequence[tuple[float, float, float, float]],
) -> bool:
    player_left = float(player.x)
    player_right = player_left + float(player.width)
    previous_bottom = previous_y + float(player.height)
    current_bottom = float(player.y) + float(player.height)

    landing_y: float | None = None
    for platform_x, platform_y, platform_w, _platform_h in platforms:
        platform_left = float(platform_x)
        platform_right = platform_left + float(platform_w)
        platform_top = float(platform_y)

        if not _horizontal_overlap(player_left, player_right, platform_left, platform_right):
            continue

        # Crossing platform top from above this frame.
        if previous_bottom <= platform_top and current_bottom >= platform_top:
            candidate_y = platform_top - float(player.height)
            if landing_y is None or candidate_y < landing_y:
                landing_y = candidate_y

    if landing_y is None:
        return False

    player.y = landing_y
    player.vy = 0.0
    return True


def _is_grounded(
    player,
    floor_y: float,
    platforms: Sequence[tuple[float, float, float, float]],
) -> bool:
    player_top = float(player.y)
    if abs(player_top - float(floor_y)) <= 1.0:
        return True

    player_left = float(player.x)
    player_right = player_left + float(player.width)
    for platform_x, platform_y, platform_w, _platform_h in platforms:
        platform_left = float(platform_x)
        platform_right = platform_left + float(platform_w)
        if not _horizontal_overlap(player_left, player_right, platform_left, platform_right):
            continue
        landing_y = float(platform_y) - float(player.height)
        if abs(player_top - landing_y) <= 1.0:
            return True
    return False


def _update_sprint_state(
    player,
    wants_sprint: bool,
    move_x: float,
    dt: float,
) -> float:
    sprint_energy = float(getattr(player, "sprint_energy", SPRINT_MAX_ENERGY))
    sprinting = bool(getattr(player, "sprinting", False))
    can_sprint_move = abs(move_x) > 0.01 and not bool(getattr(player, "on_ladder", False))

    if sprinting and not (wants_sprint and can_sprint_move):
        sprinting = False

    if not sprinting and wants_sprint and can_sprint_move and sprint_energy >= SPRINT_MIN_START_ENERGY:
        sprinting = True

    if sprinting:
        sprint_energy = max(0.0, sprint_energy - (SPRINT_DRAIN_PER_SECOND * dt))
        if sprint_energy <= 0.0:
            sprinting = False
    else:
        sprint_energy = min(SPRINT_MAX_ENERGY, sprint_energy + (SPRINT_RECHARGE_PER_SECOND * dt))

    player.sprinting = sprinting
    player.sprint_energy = sprint_energy
    return SPRINT_SPEED_MULTIPLIER if sprinting else 1.0


def apply_player_input(
    player,
    input_state: dict,
    dt: float,
    floor_y: float,
    world_width: float | None = None,
    ladders: Sequence[tuple[float, float, float, float]] = (),
    platforms: Sequence[tuple[float, float, float, float]] = (),
    world_height: float | None = None,
) -> None:
    """Apply simple horizontal and ladder movement to a player object."""
    del world_height

    move_x = _clamp_axis(float(input_state.get("move_x", 0.0)))
    climb = _clamp_axis(float(input_state.get("climb", 0.0)))
    requested_ladder = bool(input_state.get("on_ladder", False))
    wants_jump = bool(input_state.get("jump", False))
    wants_sprint = bool(input_state.get("sprint", False))
    previous_y = float(player.y)

    if move_x > 0.01:
        player.facing = 1
    elif move_x < -0.01:
        player.facing = -1

    overlap_ladder = _overlaps_ladder(player, ladders)
    if requested_ladder and not overlap_ladder:
        import time as _time
        now = _time.monotonic()
        if not hasattr(apply_player_input, "_last_climb_debug") or now - apply_player_input._last_climb_debug >= 2.0:
            apply_player_input._last_climb_debug = now
            print(f"[CLIMB] Player y={player.y:.1f} x={player.x:.1f} w={player.width} h={player.height} — no ladder overlap. Ladders checked: {len(ladders)}")
    player.on_ladder = overlap_ladder and (requested_ladder or abs(climb) > 0.01)

    sprint_multiplier = _update_sprint_state(player, wants_sprint=wants_sprint, move_x=move_x, dt=dt)
    carry_count = int(getattr(player, "carried_loot_count", 0))
    carry_penalty = max(0.40, 1.0 - carry_count * 0.08)
    player.vx = move_x * PLAYER_SPEED * sprint_multiplier * carry_penalty

    if wants_jump and not player.on_ladder and _is_grounded(player, floor_y, platforms):
        player.vy = -float(JUMP_SPEED)

    if player.on_ladder:
        player.vy = climb * CLIMB_SPEED
    else:
        player.vy += GRAVITY * dt

    player.x += player.vx * dt
    player.y += player.vy * dt

    width_limit = float(world_width) if world_width is not None else float(player.x + player.width)
    max_x = max(0.0, width_limit - float(player.width))
    if player.x < 0.0:
        player.x = 0.0
    elif player.x > max_x:
        player.x = max_x

    if not player.on_ladder and player.vy >= 0.0:
        if _resolve_platform_landing(player, previous_y, platforms):
            return

    # Floor collision fallback to keep prototype in-bounds.
    if float(player.y) > floor_y:
        player.y = floor_y
        player.vy = 0.0
