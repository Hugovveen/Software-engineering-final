"""Helpers for loading and playing sprite animations."""

from __future__ import annotations

from pathlib import Path

import pygame


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}


class AnimationPlayer:
    """Simple frame-based animation player."""

    def __init__(self, frames: list[pygame.Surface], fps: float = 10.0, loop: bool = True) -> None:
        self.frames = frames
        self.fps = fps
        self.loop = loop
        self.time_accumulator = 0.0
        self.frame_index = 0

    def update(self, dt: float) -> None:
        """Advance the animation by elapsed time."""
        if not self.frames or self.fps <= 0:
            return

        frame_time = 1.0 / self.fps
        self.time_accumulator += max(0.0, dt)

        while self.time_accumulator >= frame_time:
            self.time_accumulator -= frame_time
            if self.loop:
                self.frame_index = (self.frame_index + 1) % len(self.frames)
            else:
                self.frame_index = min(self.frame_index + 1, len(self.frames) - 1)

    def reset(self) -> None:
        """Reset animation playback to first frame."""
        self.time_accumulator = 0.0
        self.frame_index = 0

    def current_frame(self) -> pygame.Surface | None:
        """Return the current frame surface, if any."""
        if not self.frames:
            return None
        return self.frames[self.frame_index]


def load_frames(folder: Path) -> list[pygame.Surface]:
    """Load sorted image files from a folder as animation frames."""
    if not folder.exists() or not folder.is_dir():
        return []

    frame_paths = sorted(
        [
            path
            for path in folder.iterdir()
            if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
        ]
    )

    frames: list[pygame.Surface] = []
    for frame_path in frame_paths:
        frame_surface = pygame.image.load(str(frame_path)).convert_alpha()
        frames.append(frame_surface)

    return frames
