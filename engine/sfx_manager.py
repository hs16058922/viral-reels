"""
Sound Effects (SFX) & Audio Design Engine for CurioMotion Reels.

Inspired by Openverse, Earshot, and RealSFX sound design libraries:
- Hook Sub Impact: 0.4s scroll-stopping sub-bass drop & whoosh
- Scene Swooshes: Fast stereo camera-pan transitions at each cut
- UI Pops & Clicks: High-tech digital bubbles for floating callout badges
- Ambient Tech Drone: Low-frequency sci-fi harmonic bed ducked under voiceover
- Dynamic Multi-Track Audio Mixing: Composite all SFX with voiceover via FFmpeg
"""

import logging
import math
import shutil
import struct
import subprocess
from pathlib import Path
from typing import List, Optional, Tuple
import numpy as np

logger = logging.getLogger("viral_reels.sfx")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SFX_DIR = PROJECT_ROOT / "assets" / "sfx"
SAMPLE_RATE = 48000


class SFXManager:
    """Manages, synthesizes, and mixes broadcast-quality sound effects for reels."""

    @classmethod
    def ensure_sfx_library(cls) -> None:
        """Ensure core sound effects exist in assets/sfx. Synthesizes them if missing."""
        SFX_DIR.mkdir(parents=True, exist_ok=True)

        whoosh_impact = SFX_DIR / "whoosh_impact.wav"
        scene_swoosh = SFX_DIR / "scene_swoosh.wav"
        ui_pop = SFX_DIR / "ui_pop.wav"
        ambient_drone = SFX_DIR / "ambient_drone.wav"
        mech_click = SFX_DIR / "mechanical_click.wav"

        if not whoosh_impact.exists():
            logger.info("Synthesizing broadcast-quality 'whoosh_impact.wav'...")
            cls._synthesize_whoosh_impact(whoosh_impact)

        if not scene_swoosh.exists():
            logger.info("Synthesizing broadcast-quality 'scene_swoosh.wav'...")
            cls._synthesize_scene_swoosh(scene_swoosh)

        if not ui_pop.exists():
            logger.info("Synthesizing broadcast-quality 'ui_pop.wav'...")
            cls._synthesize_ui_pop(ui_pop)

        if not mech_click.exists():
            logger.info("Synthesizing broadcast-quality 'mechanical_click.wav'...")
            cls._synthesize_mechanical_click(mech_click)

        if not ambient_drone.exists():
            logger.info("Synthesizing broadcast-quality 'ambient_drone.wav'...")
            cls._synthesize_ambient_drone(ambient_drone, duration=70.0)

    # ── Procedural Sound Synthesis (48kHz, 16-bit Stereo) ─────────────

    @staticmethod
    def _write_wav(path: Path, left_channel: np.ndarray, right_channel: np.ndarray) -> None:
        """Write 48kHz 16-bit Stereo WAV file using standard library."""
        l_int = np.clip(left_channel * 32767, -32768, 32767).astype(np.int16)
        r_int = np.clip(right_channel * 32767, -32768, 32767).astype(np.int16)

        interleaved = np.empty((len(l_int) * 2,), dtype=np.int16)
        interleaved[0::2] = l_int
        interleaved[1::2] = r_int
        raw_bytes = interleaved.tobytes()

        num_channels = 2
        sample_width = 2
        byte_rate = SAMPLE_RATE * num_channels * sample_width
        block_align = num_channels * sample_width

        with open(path, "wb") as f:
            # RIFF header
            f.write(b"RIFF")
            f.write(struct.pack("<I", 36 + len(raw_bytes)))
            f.write(b"WAVE")
            # fmt chunk
            f.write(b"fmt ")
            f.write(struct.pack("<I", 16))
            f.write(struct.pack("<H", 1))  # PCM
            f.write(struct.pack("<H", num_channels))
            f.write(struct.pack("<I", SAMPLE_RATE))
            f.write(struct.pack("<I", byte_rate))
            f.write(struct.pack("<H", block_align))
            f.write(struct.pack("<H", 16))  # bits per sample
            # data chunk
            f.write(b"data")
            f.write(struct.pack("<I", len(raw_bytes)))
            f.write(raw_bytes)

    @classmethod
    def _synthesize_whoosh_impact(cls, output_path: Path) -> None:
        """Cinematic Sub-bass boom + fast air whoosh for the 0.4s hook impact."""
        duration = 0.85
        t = np.linspace(0, duration, int(SAMPLE_RATE * duration), endpoint=False)

        # 1. Sub-bass exponential drop (75Hz down to 28Hz)
        freq = 75.0 * np.exp(-t * 3.5) + 28.0
        phase = 2 * np.pi * np.cumsum(freq) / SAMPLE_RATE
        sub = np.sin(phase) * np.exp(-t * 4.2)

        # Harmonic saturation
        sub = np.tanh(sub * 1.5)

        # 2. Air whoosh (swept noise)
        noise = np.random.uniform(-1.0, 1.0, len(t))
        # Whoosh envelope peaks at t=0.18s
        whoosh_env = np.exp(-((t - 0.18) ** 2) / 0.015)
        whoosh = noise * whoosh_env * 0.45

        combined_l = sub * 0.75 + whoosh * 0.5
        combined_r = sub * 0.75 + whoosh * 0.55

        cls._write_wav(output_path, combined_l, combined_r)

    @classmethod
    def _synthesize_scene_swoosh(cls, output_path: Path) -> None:
        """Fast, airy stereo camera-pan swoosh for scene cuts."""
        duration = 0.42
        t = np.linspace(0, duration, int(SAMPLE_RATE * duration), endpoint=False)

        noise = np.random.uniform(-1.0, 1.0, len(t))
        # Gaussian envelope centered at 0.18s
        env = np.exp(-((t - 0.18) ** 2) / 0.008)

        # Subtle tonal formant
        f_sweep = 900.0 * np.exp(-((t - 0.18) ** 2) / 0.02) + 300.0
        tone = np.sin(2 * np.pi * np.cumsum(f_sweep) / SAMPLE_RATE) * 0.25

        audio = (noise * 0.75 + tone) * env

        # Dynamic Stereo Panning from Left (-0.7) to Right (+0.7)
        pan_progress = t / duration
        pan_l = np.cos(pan_progress * (np.pi / 2))
        pan_r = np.sin(pan_progress * (np.pi / 2))

        cls._write_wav(output_path, audio * pan_l, audio * pan_r)

    @classmethod
    def _synthesize_ui_pop(cls, output_path: Path) -> None:
        """Clean high-tech bubble pop / blip for floating callout cards."""
        duration = 0.11
        t = np.linspace(0, duration, int(SAMPLE_RATE * duration), endpoint=False)

        # Fast pitch glide downwards: 1600Hz down to 520Hz
        freq = 1600.0 * np.exp(-t * 26.0) + 520.0
        phase = 2 * np.pi * np.cumsum(freq) / SAMPLE_RATE
        env = np.exp(-t * 32.0)

        audio = np.sin(phase) * env * 0.65
        cls._write_wav(output_path, audio, audio)

    @classmethod
    def _synthesize_mechanical_click(cls, output_path: Path) -> None:
        """Sharp mechanical relay click with dual transient pulses."""
        duration = 0.08
        t = np.linspace(0, duration, int(SAMPLE_RATE * duration), endpoint=False)

        # Dual micro-clicks 14ms apart
        pulse1 = np.exp(-((t - 0.01) ** 2) / 0.00008) * np.sin(2 * np.pi * 3200 * t)
        pulse2 = np.exp(-((t - 0.024) ** 2) / 0.00008) * np.sin(2 * np.pi * 2100 * t) * 0.75
        audio = (pulse1 + pulse2) * 0.55
        cls._write_wav(output_path, audio, audio)

    @classmethod
    def _synthesize_ambient_drone(cls, output_path: Path, duration: float = 70.0) -> None:
        """Low-frequency sci-fi harmonic drone (55Hz / 82.4Hz) for ambient bed."""
        t = np.linspace(0, duration, int(SAMPLE_RATE * duration), endpoint=False)

        # Root A1 (55Hz) + Fifth E2 (82.4Hz) + Octave A2 (110Hz)
        lfo = 1.0 + 0.18 * np.sin(2 * np.pi * 0.15 * t)
        drone_55 = np.sin(2 * np.pi * 55.0 * t) * 0.5 * lfo
        drone_82 = np.sin(2 * np.pi * 82.41 * t + 0.5) * 0.3
        drone_110 = np.sin(2 * np.pi * 110.0 * t + 1.2) * 0.15

        # Subtle pink noise warmth
        noise = np.random.uniform(-0.04, 0.04, len(t))

        audio = (drone_55 + drone_82 + drone_110 + noise) * 0.35
        # Soft 1.5s fade-in and 2.0s fade-out
        fade_in = np.clip(t / 1.5, 0.0, 1.0)
        fade_out = np.clip((duration - t) / 2.0, 0.0, 1.0)
        audio = audio * fade_in * fade_out

        cls._write_wav(output_path, audio, audio)

    # ── Multi-Track Audio Mixing Engine ───────────────────────────────

    @classmethod
    def build_mixed_soundtrack(
        cls,
        voice_path: Path,
        scene_cut_times: List[float],
        callout_times: List[float],
        total_duration: float,
        output_path: Path,
        events: Optional[List[Tuple[float, str]]] = None,
    ) -> Path:
        """Composite voiceover, hook impact, scene swooshes, UI pops, and ambient bed into master audio."""
        cls.ensure_sfx_library()

        whoosh_impact = SFX_DIR / "whoosh_impact.wav"
        scene_swoosh = SFX_DIR / "scene_swoosh.wav"
        ui_pop = SFX_DIR / "ui_pop.wav"
        ambient_drone = SFX_DIR / "ambient_drone.wav"

        ffmpeg_bin = shutil.which("ffmpeg") or "ffmpeg"

        # Build FFmpeg complex audio filter graph
        # Input 0: Voiceover
        # Input 1: Ambient Drone
        # Input 2: Whoosh Impact (0.4s)
        # Input 3: Scene Swoosh
        # Input 4: UI Pop
        inputs = [
            "-i", str(voice_path),
            "-i", str(ambient_drone),
            "-i", str(whoosh_impact),
            "-i", str(scene_swoosh),
            "-i", str(ui_pop),
            "-i", str(SFX_DIR / "mechanical_click.wav"),
        ]

        filter_parts = []
        mix_inputs = ["[0:a]"]  # Start with voiceover

        # 1. Ambient Drone (Ducked at -20dB / volume 0.12)
        filter_parts.append(f"[1:a]volume=0.12,atrim=0:{total_duration:.2f},asetpts=PTS-STARTPTS[ambient]")
        mix_inputs.append("[ambient]")

        # 2. Hook Sub Impact at t=0.4s
        filter_parts.append("[2:a]adelay=400|400,volume=0.85[sfx_hook]")
        mix_inputs.append("[sfx_hook]")

        # 3. Scene Swooshes at each scene transition
        swoosh_labels = []
        for idx, cut_t in enumerate(scene_cut_times):
            delay_ms = max(0, int((cut_t - 0.15) * 1000))
            label = f"[sfx_cut_{idx}]"
            filter_parts.append(f"[3:a]adelay={delay_ms}|{delay_ms},volume=0.48{label}")
            mix_inputs.append(label)

        # 4. UI Pops when callout badges appear
        for idx, pop_t in enumerate(callout_times):
            delay_ms = max(0, int(pop_t * 1000))
            label = f"[sfx_pop_{idx}]"
            filter_parts.append(f"[4:a]adelay={delay_ms}|{delay_ms},volume=0.40{label}")
            mix_inputs.append(label)

        # 5. Typed animation events: (seconds, "pop" | "click" | "swoosh" | "impact")
        event_input = {"pop": 4, "click": 5, "swoosh": 3, "impact": 2}
        for idx, (ev_t, kind) in enumerate(events or []):
            delay_ms = max(0, int(ev_t * 1000))
            label = f"[sfx_ev_{idx}]"
            filter_parts.append(f"[{event_input[kind]}:a]adelay={delay_ms}|{delay_ms},volume=0.45{label}")
            mix_inputs.append(label)

        # Mix all tracks together. normalize=0 keeps the voice at full level
        # (amix otherwise divides every input by the input count); the limiter
        # catches peaks where SFX overlap speech.
        mix_count = len(mix_inputs)
        mix_chain = "".join(mix_inputs) + f"amix=inputs={mix_count}:duration=first:dropout_transition=2:normalize=0,alimiter=limit=0.95[outa]"
        filter_parts.append(mix_chain)

        filter_str = ";".join(filter_parts)

        cmd = [
            ffmpeg_bin, "-y",
            *inputs,
            "-filter_complex", filter_str,
            "-map", "[outa]",
            "-c:a", "aac",
            "-b:a", "192k",
            "-ar", "48000",
            "-ac", "2",
            "-t", f"{total_duration:.2f}",
            str(output_path),
        ]

        logger.info("Mastering multi-track audio soundtrack with SFX...")
        res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        if res.returncode != 0:
            logger.warning("FFmpeg multi-track mix fallback: %s. Using original voiceover.", res.stderr[:160])
            shutil.copy(voice_path, output_path)

        return output_path
