"""Manual pygame map layout editor for platforms and ladders."""

from __future__ import annotations

from pathlib import Path

import pygame

from config import FPS, SCREEN_HEIGHT, SCREEN_WIDTH
from map.facility_map import FacilityMap


class LevelLayoutEditor:
    """Interactive editor for drawing platform and ladder rectangles."""

    GRID_SIZE = 8

    def __init__(self) -> None:
        base_map = FacilityMap()
        def rect4(values: tuple[float, float, float, float]) -> tuple[int, int, int, int]:
            return int(values[0]), int(values[1]), int(values[2]), int(values[3])

        self.platforms: list[tuple[int, int, int, int]] = [
            rect4(rect) for rect in base_map.platforms
        ]
        self.ladders: list[tuple[int, int, int, int]] = [
            rect4(rect) for rect in base_map.ladders
        ]

        self.mode = "platform"
        self.drag_start: tuple[int, int] | None = None
        self.drag_current: tuple[int, int] | None = None
        self.font: pygame.font.Font | None = None

    def _snap(self, value: int) -> int:
        return int(round(value / self.GRID_SIZE) * self.GRID_SIZE)

    def _mouse_world(self) -> tuple[int, int]:
        mouse_x, mouse_y = pygame.mouse.get_pos()
        return self._snap(mouse_x), self._snap(mouse_y)

    def _normalize_rect(
        self,
        start: tuple[int, int],
        end: tuple[int, int],
    ) -> tuple[int, int, int, int] | None:
        x1, y1 = start
        x2, y2 = end
        left = min(x1, x2)
        top = min(y1, y2)
        width = abs(x2 - x1)
        height = abs(y2 - y1)
        if width < self.GRID_SIZE or height < self.GRID_SIZE:
            return None
        return left, top, width, height

    def _append_current_rect(self) -> None:
        if self.drag_start is None or self.drag_current is None:
            return
        rect = self._normalize_rect(self.drag_start, self.drag_current)
        if rect is None:
            return
        if self.mode == "platform":
            self.platforms.append(rect)
        else:
            self.ladders.append(rect)

    def _delete_last(self) -> None:
        if self.mode == "platform" and self.platforms:
            self.platforms.pop()
        elif self.mode == "ladder" and self.ladders:
            self.ladders.pop()

    def _clear_mode(self) -> None:
        if self.mode == "platform":
            self.platforms.clear()
        else:
            self.ladders.clear()

    def _render_text(self, screen: pygame.Surface) -> None:
        if self.font is None:
            return

        instructions = [
            f"Mode: {self.mode.upper()} (press 1=platform, 2=ladder)",
            "Left-drag: draw rectangle",
            "Backspace: delete last in current mode",
            "C: clear current mode list",
            "E: export rectangles to map/layout_export.txt",
            "G: toggle grid 8/16",
            "Esc: quit",
            f"Platforms: {len(self.platforms)} | Ladders: {len(self.ladders)}",
        ]

        panel_h = 24 * len(instructions) + 14
        panel = pygame.Surface((760, panel_h), pygame.SRCALPHA)
        panel.fill((10, 10, 20, 180))
        screen.blit(panel, (12, 12))

        y = 20
        for line in instructions:
            text = self.font.render(line, True, (235, 235, 242))
            screen.blit(text, (22, y))
            y += 24

    def _draw_grid(self, screen: pygame.Surface) -> None:
        color = (44, 48, 58)
        for x in range(0, SCREEN_WIDTH, self.GRID_SIZE):
            pygame.draw.line(screen, color, (x, 0), (x, SCREEN_HEIGHT), 1)
        for y in range(0, SCREEN_HEIGHT, self.GRID_SIZE):
            pygame.draw.line(screen, color, (0, y), (SCREEN_WIDTH, y), 1)

    def _draw_rects(self, screen: pygame.Surface) -> None:
        for x, y, w, h in self.platforms:
            pygame.draw.rect(screen, (110, 115, 140), pygame.Rect(x, y, w, h))
        for x, y, w, h in self.ladders:
            pygame.draw.rect(screen, (166, 130, 85), pygame.Rect(x, y, w, h))

        if self.drag_start is not None and self.drag_current is not None:
            preview = self._normalize_rect(self.drag_start, self.drag_current)
            if preview is not None:
                color = (120, 200, 255) if self.mode == "platform" else (255, 205, 120)
                pygame.draw.rect(screen, color, pygame.Rect(*preview), 2)

    def _export_text(self) -> str:
        platform_text = ",\n            ".join(str(rect) for rect in self.platforms)
        ladder_text = ",\n            ".join(str(rect) for rect in self.ladders)
        return (
            "platforms = [\n"
            f"            {platform_text}\n"
            "        ]\n\n"
            "ladders = [\n"
            f"            {ladder_text}\n"
            "        ]\n"
        )

    def _export_to_file(self) -> Path:
        output_dir = Path(__file__).resolve().parents[0] / "map"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / "layout_export.txt"
        output_path.write_text(self._export_text(), encoding="utf-8")
        print(f"[EDITOR] Exported layout to {output_path}")
        return output_path

    def run(self) -> None:
        pygame.init()
        pygame.display.set_caption("Level Layout Editor")
        screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("consolas", 20)

        running = True
        while running:
            clock.tick(FPS)

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        running = False
                    elif event.key == pygame.K_1:
                        self.mode = "platform"
                    elif event.key == pygame.K_2:
                        self.mode = "ladder"
                    elif event.key == pygame.K_BACKSPACE:
                        self._delete_last()
                    elif event.key == pygame.K_c:
                        self._clear_mode()
                    elif event.key == pygame.K_e:
                        self._export_to_file()
                    elif event.key == pygame.K_g:
                        self.GRID_SIZE = 16 if self.GRID_SIZE == 8 else 8
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    self.drag_start = self._mouse_world()
                    self.drag_current = self.drag_start
                elif event.type == pygame.MOUSEMOTION and self.drag_start is not None:
                    self.drag_current = self._mouse_world()
                elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                    self.drag_current = self._mouse_world()
                    self._append_current_rect()
                    self.drag_start = None
                    self.drag_current = None

            screen.fill((18, 20, 28))
            self._draw_grid(screen)
            self._draw_rects(screen)
            self._render_text(screen)
            pygame.display.flip()

        pygame.quit()


def run_layout_editor() -> None:
    """Convenience entrypoint for local map editing mode."""
    LevelLayoutEditor().run()
