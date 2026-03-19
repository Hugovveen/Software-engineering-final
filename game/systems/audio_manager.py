"""
GROVE — Audio Manager
Drop into your project root and import from game.py / server.py.

Folder structure expected:
  assets/
    audio/
      music/
        lobby_ambient.ogg
        game_ambient_1.ogg
        game_ambient_2.ogg
        tension_sting.ogg
        end_of_story.ogg
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
"""

import array
import math
import os
import wave
from enum import Enum, auto
from pathlib import Path

import pygame

# Resolve paths relative to the game root (parent of systems/)
_GAME_ROOT = Path(__file__).resolve().parent.parent
_AUDIO_DIR = _GAME_ROOT / "assets" / "audio"


class MusicState(Enum):
    LOBBY   = auto()
    GAME    = auto()
    TENSION = auto()
    ENDING  = auto()
    SILENT  = auto()


MUSIC_TRACKS = {
    MusicState.LOBBY:   str(_AUDIO_DIR / "music" / "lobby_ambient.ogg"),
    MusicState.GAME:    str(_AUDIO_DIR / "music" / "game_ambient.ogg"),
    MusicState.TENSION: str(_AUDIO_DIR / "music" / "tension_sting.ogg"),
    MusicState.ENDING:  str(_AUDIO_DIR / "music" / "end_of_story.ogg"),
}

# Dual game ambient tracks
_GAME_AMBIENT_1 = str(_AUDIO_DIR / "music" / "game_ambient_1.ogg")
_GAME_AMBIENT_2 = str(_AUDIO_DIR / "music" / "game_ambient_2.ogg")
_LOBBY_AMBIENT  = str(_AUDIO_DIR / "music" / "lobby_ambient.ogg")

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


def _resolve_path(ogg_path: str) -> str | None:
    """Return the ogg path if it exists, else try .wav fallback."""
    if os.path.exists(ogg_path):
        return ogg_path
    wav = ogg_path.replace(".ogg", ".wav")
    if os.path.exists(wav):
        return wav
    return None


class AudioManager:
    """
    Singleton-style audio manager.
    Usage:
        audio = AudioManager()
        audio.play_music(MusicState.LOBBY)
        audio.play_sfx("footstep")
        audio.set_sanity(player.sanity)   # drives dynamic music + sfx
    """

    def __init__(self) -> None:
        if not pygame.get_init():
            pygame.init()
        pygame.mixer.pre_init(44100, -16, 2, 512)
        if not pygame.mixer.get_init():
            pygame.mixer.init()
        pygame.mixer.set_num_channels(22)

        self._current_state: MusicState = MusicState.SILENT
        self._sfx: dict[str, list[pygame.mixer.Sound] | pygame.mixer.Sound] = {}
        self._footstep_idx = 0

        # Dedicated channels
        self._sanity_channel = pygame.mixer.Channel(14)
        self._heartbeat_channel = pygame.mixer.Channel(15)
        self._siren_channel = pygame.mixer.Channel(16)
        self._game_ambient_1_channel = pygame.mixer.Channel(17)
        self._game_ambient_2_channel = pygame.mixer.Channel(18)
        self._lobby_under_channel = pygame.mixer.Channel(19)
        self._lobby_main_channel = pygame.mixer.Channel(20)
        self._ending_channel = pygame.mixer.Channel(21)

        # Loaded sounds for channel-based playback
        self._game_ambient_1_sound: pygame.mixer.Sound | None = None
        self._game_ambient_2_sound: pygame.mixer.Sound | None = None
        self._siren_sound: pygame.mixer.Sound | None = None
        self._lobby_sound: pygame.mixer.Sound | None = None
        self._ending_sound: pygame.mixer.Sound | None = None
        self._game_over_sound: pygame.mixer.Sound | None = None

        # Heartbeat smooth ramp state
        self._hb_target_vol: float = 0.0
        self._hb_current_vol: float = 0.0
        self._hb_ramp_speed: float = 0.5  # volume units per second (0→1 in 2s)

        # Game over → lobby transition
        self._game_over_playing: bool = False

        self._generate_missing_audio()
        self._load_sfx()
        self._load_channel_sounds()
        print(f"[AudioManager] Init complete. SFX loaded: {list(self._sfx.keys())}")

    # ------------------------------------------------------------------ #
    #  Placeholder audio generation                                        #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _write_wav(path: str, samples: array.array, sample_rate: int = 44100) -> None:
        """Write mono 16-bit PCM samples to a .wav file (pygame loads .wav natively)."""
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with wave.open(path, "w") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(samples.tobytes())

    @staticmethod
    def _gen_tone(freq: float, duration: float, volume: float = 0.3, sample_rate: int = 44100) -> array.array:
        """Generate a sine wave tone with fade in/out."""
        n = int(sample_rate * duration)
        buf = array.array("h", [0] * n)
        fade_samples = int(sample_rate * 0.02)
        for i in range(n):
            t = i / sample_rate
            fade = min(1.0, i / max(1, fade_samples), (n - i) / max(1, fade_samples))
            buf[i] = int(32000 * volume * fade * math.sin(2 * math.pi * freq * t))
        return buf

    @staticmethod
    def _gen_noise(duration: float, volume: float = 0.15, sample_rate: int = 44100) -> array.array:
        """Generate filtered noise (for ambient/drone sounds)."""
        import random
        n = int(sample_rate * duration)
        buf = array.array("h", [0] * n)
        prev = 0.0
        for i in range(n):
            fade = min(1.0, i / max(1, int(sample_rate * 0.5)), (n - i) / max(1, int(sample_rate * 0.5)))
            raw = random.uniform(-1.0, 1.0)
            prev = prev * 0.95 + raw * 0.05  # low-pass filter
            buf[i] = int(32000 * volume * fade * prev)
        return buf

    @staticmethod
    def _gen_heartbeat(duration: float, bpm: float = 72.0, sample_rate: int = 44100) -> array.array:
        """Generate a heartbeat-like pulse pattern."""
        n = int(sample_rate * duration)
        buf = array.array("h", [0] * n)
        beat_interval = 60.0 / bpm
        for i in range(n):
            t = i / sample_rate
            beat_phase = (t % beat_interval) / beat_interval
            amp = 0.0
            if beat_phase < 0.08:
                amp = math.sin(beat_phase / 0.08 * math.pi) * 0.5
            elif 0.12 < beat_phase < 0.18:
                amp = math.sin((beat_phase - 0.12) / 0.06 * math.pi) * 0.35
            fade = min(1.0, i / max(1, int(sample_rate * 0.1)), (n - i) / max(1, int(sample_rate * 0.1)))
            buf[i] = int(32000 * amp * fade * math.sin(2 * math.pi * 55 * t))
        return buf

    def _generate_missing_audio(self) -> None:
        """Generate placeholder .wav files for any missing audio assets."""
        generated = 0

        music_specs = {
            "lobby_ambient": ("drone", 8.0, 80, 0.12),
            "game_ambient": ("drone", 8.0, 55, 0.15),
            "game_ambient_1": ("drone", 8.0, 55, 0.15),
            "game_ambient_2": ("drone", 8.0, 70, 0.10),
            "tension_sting": ("tone", 2.0, 220, 0.25),
            "end_of_story": ("drone", 10.0, 40, 0.12),
        }
        for name, (kind, dur, freq, vol) in music_specs.items():
            wav_path = str(_AUDIO_DIR / "music" / f"{name}.wav")
            ogg_path = str(_AUDIO_DIR / "music" / f"{name}.ogg")
            if os.path.exists(ogg_path) or os.path.exists(wav_path):
                continue
            if kind == "drone":
                samples = self._gen_noise(dur, vol)
            else:
                samples = self._gen_tone(freq, dur, vol)
            self._write_wav(wav_path, samples)
            generated += 1

        sfx_specs = {
            "footstep_01": ("tone", 0.1, 180, 0.2),
            "footstep_02": ("tone", 0.1, 200, 0.2),
            "footstep_03": ("tone", 0.1, 160, 0.2),
            "door_creak": ("tone", 0.5, 300, 0.2),
            "item_pickup": ("tone", 0.2, 600, 0.25),
            "item_drop": ("tone", 0.2, 400, 0.2),
            "sanity_low": ("noise", 1.5, 0, 0.1),
            "monster_nearby": ("tone", 0.8, 120, 0.2),
            "monster_siren": ("tone", 1.0, 350, 0.3),
            "player_death": ("tone", 0.6, 100, 0.3),
            "game_over": ("tone", 1.5, 80, 0.25),
            "heartbeat": ("heartbeat", 8.0, 72, 0.3),
        }
        for name, (kind, dur, freq, vol) in sfx_specs.items():
            wav_path = str(_AUDIO_DIR / "sfx" / f"{name}.wav")
            ogg_path = str(_AUDIO_DIR / "sfx" / f"{name}.ogg")
            if os.path.exists(ogg_path) or os.path.exists(wav_path):
                continue
            if kind == "noise":
                samples = self._gen_noise(dur, vol)
            elif kind == "heartbeat":
                samples = self._gen_heartbeat(dur, freq)
            else:
                samples = self._gen_tone(freq, dur, vol)
            self._write_wav(wav_path, samples)
            generated += 1

        if generated:
            print(f"[AudioManager] Generated {generated} placeholder audio files")

        # Update paths to check for .wav fallbacks
        for state, ogg_path in list(MUSIC_TRACKS.items()):
            resolved = _resolve_path(ogg_path)
            if resolved and resolved != ogg_path:
                MUSIC_TRACKS[state] = resolved

        for name, path in list(SFX_PATHS.items()):
            if isinstance(path, list):
                SFX_PATHS[name] = [_resolve_path(p) or p for p in path]
            else:
                SFX_PATHS[name] = _resolve_path(path) or path

    # ------------------------------------------------------------------ #
    #  Loading                                                             #
    # ------------------------------------------------------------------ #

    def _load_sfx(self) -> None:
        for name, path in SFX_PATHS.items():
            if isinstance(path, list):
                sounds = []
                for p in path:
                    if os.path.exists(p):
                        s = pygame.mixer.Sound(p)
                        s.set_volume(SFX_VOLUME)
                        sounds.append(s)
                    else:
                        print(f"[AudioManager] Missing SFX: {p}")
                self._sfx[name] = sounds
            else:
                if os.path.exists(path):
                    s = pygame.mixer.Sound(path)
                    s.set_volume(SFX_VOLUME)
                    self._sfx[name] = s
                else:
                    print(f"[AudioManager] Missing SFX: {path}")

    def _load_channel_sounds(self) -> None:
        """Load sounds that play on dedicated channels."""
        # Dual game ambient tracks
        p1 = _resolve_path(_GAME_AMBIENT_1)
        if p1:
            self._game_ambient_1_sound = pygame.mixer.Sound(p1)
        p2 = _resolve_path(_GAME_AMBIENT_2)
        if p2:
            self._game_ambient_2_sound = pygame.mixer.Sound(p2)

        # Siren continuous loop
        siren_path = _resolve_path(str(_AUDIO_DIR / "sfx" / "monster_siren.ogg"))
        if siren_path:
            self._siren_sound = pygame.mixer.Sound(siren_path)

        # Lobby ambient for layering
        lobby_path = _resolve_path(_LOBBY_AMBIENT)
        if lobby_path:
            self._lobby_sound = pygame.mixer.Sound(lobby_path)

        # End of story for title/ending layering
        ending_path = _resolve_path(str(_AUDIO_DIR / "music" / "end_of_story.ogg"))
        if ending_path:
            self._ending_sound = pygame.mixer.Sound(ending_path)

        # Game over sound for polling completion
        go_path = _resolve_path(str(_AUDIO_DIR / "sfx" / "game_over.ogg"))
        if go_path:
            self._game_over_sound = pygame.mixer.Sound(go_path)

    # ------------------------------------------------------------------ #
    #  Music                                                               #
    # ------------------------------------------------------------------ #

    def _stop_all_music_channels(self) -> None:
        """Fade out all music channels."""
        self._game_ambient_1_channel.fadeout(FADE_MS)
        self._game_ambient_2_channel.fadeout(FADE_MS)
        self._siren_channel.fadeout(FADE_MS)
        self._lobby_under_channel.fadeout(FADE_MS)
        self._lobby_main_channel.fadeout(FADE_MS)
        self._ending_channel.fadeout(FADE_MS)

    def play_music(self, state: MusicState) -> None:
        """Switch music state with a crossfade."""
        if state == self._current_state:
            return
        self._current_state = state

        self._stop_all_music_channels()
        self._game_over_playing = False

        if state == MusicState.SILENT:
            return

        if state == MusicState.GAME:
            # Dual layered game ambient on channels
            if self._game_ambient_1_sound:
                self._game_ambient_1_sound.set_volume(0.6)
                self._game_ambient_1_channel.play(self._game_ambient_1_sound, loops=-1)
            if self._game_ambient_2_sound:
                self._game_ambient_2_sound.set_volume(0.25)
                self._game_ambient_2_channel.play(self._game_ambient_2_sound, loops=-1)
            # Start siren singing at very low volume
            if self._siren_sound:
                self._siren_sound.set_volume(0.05)
                self._siren_channel.play(self._siren_sound, loops=-1)
            return

        if state == MusicState.ENDING:
            # end_of_story as main + lobby ambient underneath — all on channels
            if self._ending_sound:
                self._ending_sound.set_volume(MUSIC_VOLUME)
                self._ending_channel.play(self._ending_sound, loops=-1)
            if self._lobby_sound:
                self._lobby_sound.set_volume(0.2)
                self._lobby_under_channel.play(self._lobby_sound, loops=-1)
            return

        if state == MusicState.LOBBY:
            # Lobby ambient main + end_of_story layered quietly — all on channels
            if self._lobby_sound:
                self._lobby_sound.set_volume(MUSIC_VOLUME)
                self._lobby_main_channel.play(self._lobby_sound, loops=-1)
            if self._ending_sound:
                self._ending_sound.set_volume(0.18)
                self._ending_channel.play(self._ending_sound, loops=-1)
            return

        if state == MusicState.TENSION:
            # Tension sting — load as Sound for channel playback
            track = MUSIC_TRACKS.get(MusicState.TENSION)
            resolved = _resolve_path(track) if track else None
            if resolved:
                try:
                    tension_snd = pygame.mixer.Sound(resolved)
                    tension_snd.set_volume(MUSIC_VOLUME)
                    self._lobby_main_channel.play(tension_snd, loops=0)
                except Exception:
                    pass
            return

    def set_music_volume(self, volume: float) -> None:
        v = max(0.0, min(1.0, volume))
        self._lobby_main_channel.set_volume(v)
        self._lobby_under_channel.set_volume(v * 0.5)
        self._ending_channel.set_volume(v * 0.4)
        self._game_ambient_1_channel.set_volume(v)
        self._game_ambient_2_channel.set_volume(v * 0.5)

    # ------------------------------------------------------------------ #
    #  SFX                                                                 #
    # ------------------------------------------------------------------ #

    def play_sfx(self, name: str, volume_override: float | None = None) -> None:
        """Play a sound effect by name."""
        sound = self._sfx.get(name)
        if sound is None:
            return

        if isinstance(sound, list):
            if not sound:
                return
            s = sound[self._footstep_idx % len(sound)]
            self._footstep_idx += 1
        else:
            s = sound

        if volume_override is not None:
            s.set_volume(max(0.0, min(1.0, volume_override)))

        s.play()

    def stop_sfx(self, name: str) -> None:
        sound = self._sfx.get(name)
        if sound and not isinstance(sound, list):
            sound.stop()

    # ------------------------------------------------------------------ #
    #  Per-frame update (call from client loop)                            #
    # ------------------------------------------------------------------ #

    def update_frame(self, dt: float) -> None:
        """Call every frame for smooth audio transitions."""
        # Smooth heartbeat volume ramp
        if self._hb_current_vol != self._hb_target_vol:
            if self._hb_current_vol < self._hb_target_vol:
                self._hb_current_vol = min(self._hb_target_vol, self._hb_current_vol + self._hb_ramp_speed * dt)
            else:
                self._hb_current_vol = max(self._hb_target_vol, self._hb_current_vol - self._hb_ramp_speed * dt)
            if self._heartbeat_channel.get_busy():
                self._heartbeat_channel.set_volume(self._hb_current_vol)

        # Game over → lobby ambient transition
        if self._game_over_playing:
            if self._game_over_sound and not self._game_over_sound.get_num_channels():
                # Game over sound finished — fade in lobby ambient
                self._game_over_playing = False
                self.play_music(MusicState.LOBBY)

    # ------------------------------------------------------------------ #
    #  Siren distance-based volume                                         #
    # ------------------------------------------------------------------ #

    def update_siren_distance(self, distance: float) -> None:
        """Update siren singing volume based on distance to local player.

        At 600px+ → volume 0.05, at 0px → volume 0.85, linear scale.
        """
        if not self._siren_channel.get_busy():
            return
        max_dist = 600.0
        clamped = max(0.0, min(max_dist, distance))
        vol = 0.05 + (0.80 * (1.0 - clamped / max_dist))
        self._siren_channel.set_volume(vol)

    # ------------------------------------------------------------------ #
    #  Dynamic audio driven by sanity                                      #
    # ------------------------------------------------------------------ #

    def set_sanity(self, sanity: float) -> None:
        """Update audio layers based on current sanity (0.0=insane, 1.0=calm)."""
        import time as _time
        now = _time.monotonic()
        if not hasattr(self, "_last_sanity_debug") or now - self._last_sanity_debug >= 1.0:
            self._last_sanity_debug = now
            print(f"[AUDIO] set_sanity called: sanity={sanity:.2f}, heartbeat_busy={self._heartbeat_channel.get_busy()}")

        # Heartbeat — smooth ramp as sanity drops below 0.55
        hb_sound = self._sfx.get("heartbeat")
        if hb_sound and not isinstance(hb_sound, list):
            if sanity < 0.55:
                self._hb_target_vol = ((0.55 - sanity) / 0.55) * 0.6  # 0 → 0.6
                if not self._heartbeat_channel.get_busy():
                    self._hb_current_vol = 0.0
                    hb_sound.set_volume(0.0)
                    self._heartbeat_channel.play(hb_sound, loops=-1)
                    print(f"[AUDIO] Heartbeat STARTED at sanity={sanity:.2f}")
            else:
                self._hb_target_vol = 0.0
                if self._heartbeat_channel.get_busy() and self._hb_current_vol <= 0.01:
                    self._heartbeat_channel.fadeout(1500)

        # Whispers at very low sanity
        if sanity < 0.15:
            whisper = self._sfx.get("sanity_low")
            if whisper and not isinstance(whisper, list):
                if not self._sanity_channel.get_busy():
                    whisper.set_volume(0.3 + (0.15 - sanity) * 2)
                    self._sanity_channel.play(whisper)

        # Tension sting at critical sanity (only once per dip below 15%)
        if sanity < 0.15 and self._current_state == MusicState.GAME:
            self.play_music(MusicState.TENSION)

    # ------------------------------------------------------------------ #
    #  Monster proximity                                                   #
    # ------------------------------------------------------------------ #

    def monster_nearby(self, distance: float, max_distance: float = 300.0) -> None:
        if distance > max_distance:
            return
        vol = 1.0 - (distance / max_distance)
        sound = self._sfx.get("monster_nearby")
        if sound and not isinstance(sound, list):
            if not sound.get_num_channels():
                sound.set_volume(vol * SFX_VOLUME)
                sound.play()

    def siren_scream(self) -> None:
        self.play_sfx("monster_siren", volume_override=0.9)

    # ------------------------------------------------------------------ #
    #  Events                                                              #
    # ------------------------------------------------------------------ #

    def on_player_death(self) -> None:
        self.play_sfx("player_death")

    def on_game_over(self) -> None:
        # Stop all music channels
        self._stop_all_music_channels()
        self._heartbeat_channel.fadeout(500)
        # Play game_over sound and track its completion
        if self._game_over_sound:
            self._game_over_sound.set_volume(SFX_VOLUME)
            self._game_over_sound.play()
            self._game_over_playing = True
        else:
            self.play_sfx("game_over")

    def is_game_over_playing(self) -> bool:
        """True while the game over voiceover is still playing."""
        return self._game_over_playing

    def on_item_pickup(self) -> None:
        self.play_sfx("item_pickup", volume_override=0.7)

    def on_item_drop(self) -> None:
        self.play_sfx("item_drop")

    def on_door(self) -> None:
        self.play_sfx("door_creak")
