"""Pygame renderer for map, players, and mimic entity.

Rendering code is isolated here to keep the main client loop uncluttered.
"""

from __future__ import annotations

from pathlib import Path

import pygame

from rendering.sprite_loader import AnimationPlayer, load_frames


class Renderer:
    """Draws the full frame based on received game state."""

    BG_COLOR = (8, 12, 20)
    PLATFORM_COLOR = (75, 75, 95)
    LADDER_COLOR = (130, 100, 70)
    PLAYER_COLOR = (90, 170, 255)
    SELF_COLOR = (90, 255, 160)
    MIMIC_COLOR = (220, 60, 90)

    def __init__(self) -> None:
        self.assets_loaded = False
        self.animation_sources: dict[str, list[pygame.Surface]] = {}
        self.animation_players: dict[tuple[str, str], AnimationPlayer] = {}
        self.scaled_frames_cache: dict[tuple[str, int, int], list[pygame.Surface]] = {}
        self.facing_by_entity: dict[str, int] = {}

    def _load_assets(self) -> None:
        if self.assets_loaded:
            return

        assets_root = Path(__file__).resolve().parents[1] / "assets"
        self.animation_sources = {
            "player_walk": load_frames(assets_root / "player" / "walking"),
            "secondplayer_walk": load_frames(assets_root / "secondplayer" / "walking"),
            "mimic_walk": load_frames(assets_root / "enemies" / "mimic" / "mimic_player" / "walking"),
        }
        self.assets_loaded = True

    def _get_scaled_frames(self, animation_key: str, width: int, height: int) -> list[pygame.Surface]:
        cache_key = (animation_key, int(width), int(height))
        if cache_key in self.scaled_frames_cache:
            return self.scaled_frames_cache[cache_key]

        source_frames = self.animation_sources.get(animation_key, [])
        if not source_frames:
            self.scaled_frames_cache[cache_key] = []
            return []

        scaled_frames = [
            pygame.transform.scale(frame, (int(width), int(height)))
            for frame in source_frames
        ]
        self.scaled_frames_cache[cache_key] = scaled_frames
        return scaled_frames

    def _get_entity_frame(
        self,
        entity_id: str,
        animation_key: str,
        dt: float,
        is_moving: bool,
        width: int,
        height: int,
    ) -> pygame.Surface | None:
        frames = self._get_scaled_frames(animation_key, width, height)
        if not frames:
            return None

        player_key = (entity_id, animation_key)
        animation = self.animation_players.get(player_key)
        if animation is None or animation.frames is not frames:
            animation = AnimationPlayer(frames, fps=10.0, loop=True)
            self.animation_players[player_key] = animation

        if is_moving:
            animation.update(dt)
            return animation.current_frame()
        return animation.frames[0]

    def _resolve_facing_direction(self, entity_id: str, x: float, vx: float) -> int:
        previous_facing = self.facing_by_entity.get(entity_id, 1)
        if vx > 0.01:
            self.facing_by_entity[entity_id] = 1
        elif vx < -0.01:
            self.facing_by_entity[entity_id] = -1
        else:
            self.facing_by_entity[entity_id] = previous_facing
        return self.facing_by_entity[entity_id]

    def draw(
        self,
        screen: pygame.Surface,
        camera,
        game_state: dict,
        self_id: str | None,
        dt: float,
    ) -> None:
        """Render world and entities from the latest game state snapshot."""
        self._load_assets()
        screen.fill(self.BG_COLOR)

        map_data = game_state.get("map", {})
        for x, y, w, h in map_data.get("platforms", []):
            sx, sy = camera.world_to_screen(x, y)
            pygame.draw.rect(screen, self.PLATFORM_COLOR, pygame.Rect(sx, sy, w, h))

        for x, y, w, h in map_data.get("ladders", []):
            sx, sy = camera.world_to_screen(x, y)
            pygame.draw.rect(screen, self.LADDER_COLOR, pygame.Rect(sx, sy, w, h))

        for player in game_state.get("players", []):
            sx, sy = camera.world_to_screen(player["x"], player["y"])
            color = self.SELF_COLOR if player.get("id") == self_id else self.PLAYER_COLOR
            player_id = str(player.get("id", "unknown-player"))
            player_vx = float(player.get("vx", 0.0))
            player_w = int(player.get("w", 0))
            player_h = int(player.get("h", 0))
            facing = self._resolve_facing_direction(player_id, float(player.get("x", 0.0)), player_vx)

            animation_key = "player_walk" if player.get("id") == self_id else "secondplayer_walk"
            frame = self._get_entity_frame(
                entity_id=player_id,
                animation_key=animation_key,
                dt=dt,
                is_moving=abs(player_vx) > 0.01,
                width=player_w,
                height=player_h,
            )

            if frame is not None:
                if facing < 0:
                    frame = pygame.transform.flip(frame, True, False)
                screen.blit(frame, (sx, sy))
            else:
                pygame.draw.rect(screen, color, pygame.Rect(sx, sy, player_w, player_h))

        mimic = game_state.get("mimic")
        if mimic:
            sx, sy = camera.world_to_screen(mimic["x"], mimic["y"])
            mimic_id = "mimic"
            mimic_vx = float(mimic.get("vx", 0.0))
            mimic_w = int(mimic.get("w", 0))
            mimic_h = int(mimic.get("h", 0))
            facing = self._resolve_facing_direction(mimic_id, float(mimic.get("x", 0.0)), mimic_vx)

            frame = self._get_entity_frame(
                entity_id=mimic_id,
                animation_key="mimic_walk",
                dt=dt,
                is_moving=abs(mimic_vx) > 0.01,
                width=mimic_w,
                height=mimic_h,
            )

            if frame is not None:
                if facing < 0:
                    frame = pygame.transform.flip(frame, True, False)
                screen.blit(frame, (sx, sy))
            else:
                pygame.draw.rect(screen, self.MIMIC_COLOR, pygame.Rect(sx, sy, mimic_w, mimic_h))

        pygame.display.flip()
