"""Local pygame preview for testing enemy behavior on the current map."""

from __future__ import annotations

import pygame

from config import FPS, SCREEN_HEIGHT, SCREEN_WIDTH
from entities.enemy_registry import EnemyRegistry
from entities.player import Player
from map.facility_map import FacilityMap
from rendering.camera import Camera
from rendering.renderer import Renderer
from systems.movement_system import apply_player_input


class EnemyPreview:
    """Runs a local preview scene without networking."""

    def __init__(self) -> None:
        self.world = FacilityMap()
        self.camera = Camera(self.world.world_width)
        self.renderer = Renderer()
        self.player = Player(player_id="preview-player", name="Previewer")
        self.hud_font: pygame.font.Font | None = None
        self.enemies = {
            "mimic-1": EnemyRegistry.create("mimic", enemy_id="mimic-1", x=460.0),
            "weeping-angel-1": EnemyRegistry.create("weeping_angel", enemy_id="weeping-angel-1", x=860.0),
            "siren-1": EnemyRegistry.create("siren", enemy_id="siren-1", x=1220.0),
        }

    def _build_input_state(self) -> dict:
        keys = pygame.key.get_pressed()

        move_x = 0
        if keys[pygame.K_a] or keys[pygame.K_LEFT]:
            move_x -= 1
        if keys[pygame.K_d] or keys[pygame.K_RIGHT]:
            move_x += 1

        climb = 0
        if keys[pygame.K_w] or keys[pygame.K_UP]:
            climb -= 1
        if keys[pygame.K_s] or keys[pygame.K_DOWN]:
            climb += 1

        return {
            "move_x": move_x,
            "climb": climb,
            "on_ladder": bool(climb),
        }

    def _update_player(self, dt: float) -> None:
        apply_player_input(
            self.player,
            self._build_input_state(),
            dt,
            floor_y=self.world.floor_y(),
            world_width=float(self.world.world_width),
            ladders=self.world.ladders,
        )

    def _update_enemies(self, dt: float) -> None:
        players = {self.player.player_id: self.player}
        for enemy_id in sorted(self.enemies.keys()):
            self.enemies[enemy_id].update(dt=dt, world=self.world, players=players)

    def _build_game_state(self) -> dict:
        return {
            "players": [self.player.to_dict()],
            "mimic": self.enemies["mimic-1"].to_dict(),
            "enemies": [enemy.to_dict() for enemy in self.enemies.values()],
            "map": {
                "platforms": self.world.platforms,
                "ladders": self.world.ladders,
            },
        }

    def _draw_debug_hud(self, screen: pygame.Surface, dt: float) -> None:
        if self.hud_font is None:
            return

        angel = self.enemies.get("weeping-angel-1")
        siren = self.enemies.get("siren-1")

        lines = [
            f"FPS: {int(1.0 / dt) if dt > 0 else 0}",
            f"Player x={self.player.x:.1f} facing={self.player.facing:+d}",
            f"Charm level={self.player.charm_level} timer={self.player.charm_timer:.2f}",
        ]

        if angel is not None:
            lines.append(
                f"Angel state={angel.state} target={angel.target_id or '-'} x={angel.x:.1f}"
            )

        if siren is not None:
            siren_cooldown = float(getattr(siren, "pulse_cooldown_remaining", 0.0))
            siren_cast = float(getattr(siren, "cast_time_remaining", 0.0))
            lines.append(
                f"Siren state={siren.state} cooldown={siren_cooldown:.2f} cast={siren_cast:.2f}"
            )
            charmed_targets = sorted(getattr(siren, "charmed_targets", {}).keys())
            lines.append(f"Siren charmed={','.join(charmed_targets) if charmed_targets else '-'}")

        panel_padding = 10
        line_height = 22
        panel_width = 660
        panel_height = panel_padding * 2 + line_height * len(lines)
        panel_surface = pygame.Surface((panel_width, panel_height), pygame.SRCALPHA)
        panel_surface.fill((10, 10, 18, 180))
        screen.blit(panel_surface, (16, 16))

        y = 16 + panel_padding
        for line in lines:
            text_surface = self.hud_font.render(line, True, (236, 236, 240))
            screen.blit(text_surface, (26, y))
            y += line_height

    def run(self) -> None:
        pygame.init()
        pygame.display.set_caption("Enemy Preview")
        screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        self.hud_font = pygame.font.SysFont("consolas", 20)
        clock = pygame.time.Clock()

        running = True
        while running:
            dt = clock.tick(FPS) / 1000.0

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False

            self._update_player(dt)
            self._update_enemies(dt)
            self.camera.follow(self.player.x)
            self.renderer.draw(screen, self.camera, self._build_game_state(), self.player.player_id, dt)
            self._draw_debug_hud(screen, dt)
            pygame.display.flip()

        pygame.quit()


def run_preview() -> None:
    """Convenience entrypoint for local preview mode."""
    EnemyPreview().run()
