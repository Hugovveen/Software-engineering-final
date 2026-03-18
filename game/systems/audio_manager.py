"""
GROVE — Audio Manager
Drop into your project root and import from game.py / server.py.

Folder structure expected:
  assets/
    audio/
      music/
        lobby_ambient.ogg
        game_ambient.ogg
        tension_sting.ogg
      sfx/
        footstep_01.ogg  footstep_02.ogg  footstep_03.ogg
        door_creak.ogg
        item_pickup.ogg
        item_drop.ogg
        sanity_low.ogg
        monster_nearby.ogg
        monster_siren.ogg
        player_death.ogg
        game_over.ogg
        heartbeat.ogg

All audio should be .ogg (best pygame compatibility cross-platform).
Free horror SFX sources listed at bottom of this file.
"""

import pygame
import os
from enum import Enum, auto
from pathlib import Path

# Resolve paths relative to the game root (parent of systems/)
_GAME_ROOT = Path(__file__).resolve().parent.parent
_AUDIO_DIR = _GAME_ROOT / "assets" / "audio"


class MusicState(Enum):
    LOBBY   = auto()
    GAME    = auto()
    TENSION = auto()
    SILENT  = auto()


MUSIC_TRACKS = {
    MusicState.LOBBY:   str(_AUDIO_DIR / "music" / "lobby_ambient.ogg"),
    MusicState.GAME:    str(_AUDIO_DIR / "music" / "game_ambient.ogg"),
    MusicState.TENSION: str(_AUDIO_DIR / "music" / "tension_sting.ogg"),
}

SFX_PATHS = {
    "footstep":      [str(_AUDIO_DIR / "sfx" / "footstep_01.ogg"),
                      str(_AUDIO_DIR / "sfx" / "footstep_02.ogg"),
                      str(_AUDIO_DIR / "sfx" / "footstep_03.ogg")],
    "door_creak":    str(_AUDIO_DIR / "sfx" / "door_creak.ogg"),
    "item_pickup":   str(_AUDIO_DIR / "sfx" / "item_pickup.ogg"),
    "item_drop":     str(_AUDIO_DIR / "sfx" / "item_drop.ogg"),
    "sanity_low":    str(_AUDIO_DIR / "sfx" / "sanity_low.ogg"),
    "monster_nearby":str(_AUDIO_DIR / "sfx" / "monster_nearby.ogg"),
    "monster_siren": str(_AUDIO_DIR / "sfx" / "monster_siren.ogg"),
    "player_death":  str(_AUDIO_DIR / "sfx" / "player_death.ogg"),
    "game_over":     str(_AUDIO_DIR / "sfx" / "game_over.ogg"),
    "heartbeat":     str(_AUDIO_DIR / "sfx" / "heartbeat.ogg"),
}

MUSIC_VOLUME  = 0.45   # keep music under SFX in a horror game
SFX_VOLUME    = 0.85
FADE_MS       = 2500   # ms for music crossfade


class AudioManager:
    """
    Singleton-style audio manager.
    Usage:
        audio = AudioManager()
        audio.play_music(MusicState.LOBBY)
        audio.play_sfx("footstep")
        audio.set_sanity(player.sanity)   # drives dynamic music + sfx
    """

    def __init__(self):
        pygame.mixer.pre_init(44100, -16, 2, 512)
        pygame.mixer.init()
        pygame.mixer.set_num_channels(16)

        self._current_state: MusicState = MusicState.SILENT
        self._sfx: dict[str, list[pygame.mixer.Sound] | pygame.mixer.Sound] = {}
        self._footstep_idx = 0
        self._sanity_channel = pygame.mixer.Channel(14)
        self._heartbeat_channel = pygame.mixer.Channel(15)

        self._load_sfx()

    # ------------------------------------------------------------------ #
    #  Loading                                                             #
    # ------------------------------------------------------------------ #

    def _load_sfx(self):
        for name, path in SFX_PATHS.items():
            if isinstance(path, list):
                sounds = []
                for p in path:
                    if os.path.exists(p):
                        s = pygame.mixer.Sound(p)
                        s.set_volume(SFX_VOLUME)
                        sounds.append(s)
                self._sfx[name] = sounds
            else:
                if os.path.exists(path):
                    s = pygame.mixer.Sound(path)
                    s.set_volume(SFX_VOLUME)
                    self._sfx[name] = s

    # ------------------------------------------------------------------ #
    #  Music                                                               #
    # ------------------------------------------------------------------ #

    def play_music(self, state: MusicState):
        """Switch music state with a crossfade."""
        if state == self._current_state:
            return
        self._current_state = state

        if state == MusicState.SILENT:
            pygame.mixer.music.fadeout(FADE_MS)
            return

        track = MUSIC_TRACKS.get(state)
        if not track or not os.path.exists(track):
            print(f"[AudioManager] Missing track: {track}")
            return

        pygame.mixer.music.fadeout(FADE_MS // 2)
        pygame.mixer.music.load(track)
        pygame.mixer.music.set_volume(MUSIC_VOLUME)

        # Lobby loops forever; tension sting plays once then returns to game
        loops = -1 if state != MusicState.TENSION else 0
        pygame.mixer.music.play(loops=loops, fade_ms=FADE_MS // 2)

        if state == MusicState.TENSION:
            # Queue game music to resume after sting ends
            pygame.mixer.music.queue(MUSIC_TRACKS[MusicState.GAME])

    def set_music_volume(self, volume: float):
        pygame.mixer.music.set_volume(max(0.0, min(1.0, volume)))

    # ------------------------------------------------------------------ #
    #  SFX                                                                 #
    # ------------------------------------------------------------------ #

    def play_sfx(self, name: str, volume_override: float | None = None):
        """Play a sound effect by name."""
        sound = self._sfx.get(name)
        if sound is None:
            return

        if isinstance(sound, list):
            if not sound:
                return
            # Round-robin footsteps
            s = sound[self._footstep_idx % len(sound)]
            self._footstep_idx += 1
        else:
            s = sound

        if volume_override is not None:
            s.set_volume(max(0.0, min(1.0, volume_override)))

        s.play()

    def stop_sfx(self, name: str):
        sound = self._sfx.get(name)
        if sound and not isinstance(sound, list):
            sound.stop()

    # ------------------------------------------------------------------ #
    #  Dynamic audio driven by sanity                                      #
    # ------------------------------------------------------------------ #

    def set_sanity(self, sanity: float):
        """
        Call every frame (or on sanity change).
        sanity: 0.0 (insane) → 1.0 (calm)

        Effects:
          - Music pitch/volume stays constant, but below 30% sanity
            a heartbeat loop fades in on its own channel.
          - Below 15% sanity: sanity_low whisper plays sporadically.
          - Below 5%: trigger tension sting.
        """
        # Heartbeat — fades in as sanity drops below 0.4
        hb_sound = self._sfx.get("heartbeat")
        if hb_sound and not isinstance(hb_sound, list):
            if sanity < 0.40:
                hb_vol = (0.40 - sanity) / 0.40  # 0 → 1
                if not self._heartbeat_channel.get_busy():
                    hb_sound.set_volume(hb_vol * 0.6)
                    self._heartbeat_channel.play(hb_sound, loops=-1)
                else:
                    self._heartbeat_channel.set_volume(hb_vol * 0.6)
            else:
                if self._heartbeat_channel.get_busy():
                    self._heartbeat_channel.fadeout(1500)

        # Whispers at very low sanity
        if sanity < 0.15:
            whisper = self._sfx.get("sanity_low")
            if whisper and not isinstance(whisper, list):
                if not self._sanity_channel.get_busy():
                    whisper.set_volume(0.3 + (0.15 - sanity) * 2)
                    self._sanity_channel.play(whisper)

        # Tension sting at critical sanity (only once per dip below 5%)
        if sanity < 0.05 and self._current_state == MusicState.GAME:
            self.play_music(MusicState.TENSION)

    # ------------------------------------------------------------------ #
    #  Monster proximity                                                   #
    # ------------------------------------------------------------------ #

    def monster_nearby(self, distance: float, max_distance: float = 300.0):
        """
        Call when a monster is close. distance in pixels/units.
        Plays monster_nearby SFX with volume scaled to proximity.
        """
        if distance > max_distance:
            return
        vol = 1.0 - (distance / max_distance)
        sound = self._sfx.get("monster_nearby")
        if sound and not isinstance(sound, list):
            if not sound.get_num_channels():   # not already playing
                sound.set_volume(vol * SFX_VOLUME)
                sound.play()

    def siren_scream(self):
        self.play_sfx("monster_siren", volume_override=0.9)

    # ------------------------------------------------------------------ #
    #  Events                                                              #
    # ------------------------------------------------------------------ #

    def on_player_death(self):
        self.play_sfx("player_death")

    def on_game_over(self):
        pygame.mixer.music.fadeout(1500)
        self.play_sfx("game_over")
        self._heartbeat_channel.fadeout(500)

    def on_item_pickup(self):
        self.play_sfx("item_pickup")

    def on_item_drop(self):
        self.play_sfx("item_drop")

    def on_door(self):
        self.play_sfx("door_creak")


# ------------------------------------------------------------------ #
#  Integration example (drop into your game loop)                     #
# ------------------------------------------------------------------ #
#
#  In main.py / game.py:
#
#    from audio_manager import AudioManager, MusicState
#    audio = AudioManager()
#
#  On lobby load:
#    audio.play_music(MusicState.LOBBY)
#
#  On game start:
#    audio.play_music(MusicState.GAME)
#
#  In game loop (every frame or on state change):
#    audio.set_sanity(local_player.sanity / 100.0)
#    if moving and on_ground:
#        audio.play_sfx("footstep")   # auto-rotates between 3 variants
#
#  On Siren detected:
#    audio.siren_scream()
#    audio.monster_nearby(dist_to_siren)
#
#  On all players dead:
#    audio.on_game_over()
#
# ------------------------------------------------------------------ #


# ------------------------------------------------------------------ #
#  Free horror SFX & music sources                                    #
# ------------------------------------------------------------------ #
#
#  MUSIC (royalty-free, loopable):
#  - https://freemusicarchive.org  → filter by "horror", "ambient"
#  - https://incompetech.com       → Kevin MacLeod, "Decomposing" series
#  - https://www.zapsplat.com      → ambient horror packs (free account)
#  - https://itch.io/game-assets   → search "horror ambient music"
#    Recommended packs:
#      "Horror Game Music Pack" by joshuuu
#      "Dark Forest Ambience" by various
#
#  SFX (footsteps, doors, monster sounds):
#  - https://freesound.org         → CC0 license, huge library
#    Good searches: "forest footstep", "door creak horror",
#                   "heartbeat horror", "whisper monster"
#  - https://www.zapsplat.com      → SFX packs
#  - https://opengameart.org       → horror SFX
#
#  CONVERT to .ogg:
#    ffmpeg -i input.mp3 -c:a libvorbis -q:a 4 output.ogg
#
