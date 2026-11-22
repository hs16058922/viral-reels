"""
Edge TTS voice synthesis wrapper.

Uses the ``edge-tts`` async library to generate speech audio and
word-level timing metadata via Microsoft Edge's online TTS service.
Provides a synchronous public API by wrapping calls with
``asyncio.run()``.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from config.settings import settings
from engine.utils import get_temp_path, run_ffmpeg

logger = logging.getLogger("viral_reels.edge_voice")


class VoiceEngine:
    """Text-to-speech engine backed by Microsoft Edge TTS.

    Example::

        ve = VoiceEngine()
        ve.synthesize("Hello world", output_path=Path("hello.mp3"))
        audio, timing = ve.synthesize_with_timestamps(
            "Hello world", output_path=Path("hello.mp3")
        )
    """

    def __init__(self, voice: Optional[str] = None) -> None:
        self.voice = voice or settings.EDGE_TTS_VOICE

    # ── Voice listing ───────────────────────────────────────────────

    def list_voices(self, language: str = "en") -> List[Dict[str, Any]]:
        """Return available Edge TTS voices filtered by *language* prefix.

        Args:
            language: BCP-47 language prefix (e.g. ``"en"``, ``"es"``).

        Returns:
            List of voice info dicts with ``Name``, ``ShortName``,
            ``Gender``, ``Locale`` etc.
        """
        return asyncio.run(self._list_voices_async(language))

    # ── Synthesis ───────────────────────────────────────────────────

    def synthesize(
        self,
        text: str,
        voice: Optional[str] = None,
        output_path: Optional[Path] = None,
    ) -> Path:
        """Generate speech audio from *text*.

        Args:
            text: The text to speak.
            voice: Override the default voice.
            output_path: Where to save the audio (MP3). Auto-generated
                if ``None``.

        Returns:
            Path to the generated audio file.
        """
        voice = voice or self.voice
        if output_path is None:
            output_path = get_temp_path("voiceover.mp3")
        else:
            output_path = Path(output_path)

        asyncio.run(self._synthesize_async(text, voice, output_path))
        logger.info("Synthesized %d chars → %s (voice=%s)", len(text), output_path.name, voice)
        return output_path

    def synthesize_with_timestamps(
        self,
        text: str,
        voice: Optional[str] = None,
        output_path: Optional[Union[str, Path]] = None,
    ) -> Tuple[Path, List[Dict[str, Any]]]:
        """Generate speech audio **and** word-level timing metadata.

        The timing data is also saved as a JSON sidecar file next to
        the audio.

        Args:
            text: The text to speak.
            voice: Override the default voice.
            output_path: Where to save the audio.

        Returns:
            Tuple of (audio_path, word_timings) where each timing dict
            has keys ``word``, ``start``, ``end`` (seconds).
        """
        voice = voice or self.voice
        if output_path is None:
            output_path = get_temp_path("voiceover.mp3")
        else:
            output_path = Path(output_path)

        timings = asyncio.run(
            self._synthesize_with_timestamps_async(text, voice, output_path)
        )

        # Save sidecar JSON.
        json_path = output_path.with_suffix(".json")
        json_path.write_text(json.dumps(timings, indent=2), encoding="utf-8")
        logger.info(
            "Synthesized with timestamps: %d words, audio=%s, timing=%s",
            len(timings), output_path.name, json_path.name,
        )
        return output_path, timings

    # ── Speed adjustment ────────────────────────────────────────────

    def adjust_speed(
        self,
        audio_path: Path,
        speed_factor: float,
        output_path: Optional[Path] = None,
    ) -> Path:
        """Change playback speed of an audio file via ffmpeg atempo.

        Args:
            audio_path: Source audio.
            speed_factor: Multiplier (e.g. ``1.25`` for 25 % faster).
            output_path: Destination; auto-generated if ``None``.

        Returns:
            Path to the speed-adjusted audio.
        """
        if output_path is None:
            output_path = get_temp_path(f"voice_speed_{speed_factor:.2f}.mp3")

        atempo = self._build_atempo_chain(speed_factor)
        run_ffmpeg([
            "-i", str(audio_path),
            "-filter:a", atempo,
            str(output_path),
        ])
        logger.info("Adjusted speed ×%.2f → %s", speed_factor, output_path.name)
        return output_path

    # ── Batch synthesis ─────────────────────────────────────────────

    def batch_synthesize(
        self,
        segments: List[str],
        voice: Optional[str] = None,
    ) -> List[Path]:
        """Synthesize multiple text segments to separate audio files.

        Args:
            segments: List of text strings.
            voice: Voice name override.

        Returns:
            Ordered list of audio file paths.
        """
        voice = voice or self.voice
        paths: List[Path] = []
        for idx, segment in enumerate(segments):
            out = get_temp_path(f"voice_seg_{idx:04d}.mp3")
            self.synthesize(segment, voice=voice, output_path=out)
            paths.append(out)
        logger.info("Batch-synthesized %d segments", len(segments))
        return paths

    # ── Async internals ─────────────────────────────────────────────

    @staticmethod
    async def _list_voices_async(language: str) -> List[Dict[str, Any]]:
        """Async helper: list voices via edge-tts."""
        import edge_tts  # Lazy import.

        voices = await edge_tts.list_voices()
        filtered = [
            v for v in voices
            if v.get("Locale", "").lower().startswith(language.lower())
        ]
        return filtered

    @staticmethod
    async def _synthesize_async(text: str, voice: str, output_path: Path) -> None:
        """Async helper: basic synthesis."""
        import edge_tts

        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(str(output_path))

    @staticmethod
    async def _synthesize_with_timestamps_async(
        text: str,
        voice: str,
        output_path: Path,
    ) -> List[Dict[str, Any]]:
        """Async helper: synthesis with word boundary events."""
        import edge_tts

        communicate = edge_tts.Communicate(text, voice)
        timings: List[Dict[str, Any]] = []

        with output_path.open("wb") as audio_file:
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_file.write(chunk["data"])
                elif chunk["type"] == "WordBoundary":
                    offset_ms = chunk.get("offset", 0)
                    duration_ms = chunk.get("duration", 0)
                    # edge-tts returns offset in 100-nanosecond units
                    start_sec = offset_ms / 10_000_000
                    end_sec = start_sec + duration_ms / 10_000_000
                    timings.append({
                        "word": chunk.get("text", ""),
                        "start": round(start_sec, 3),
                        "end": round(end_sec, 3),
                    })

        return timings

    # ── Private helpers ─────────────────────────────────────────────

    @staticmethod
    def _build_atempo_chain(factor: float) -> str:
        """Build an ``atempo`` filter chain (valid range per filter: 0.5–100)."""
        parts: List[str] = []
        remaining = factor
        while remaining > 100.0:
            parts.append("atempo=100.0")
            remaining /= 100.0
        while remaining < 0.5:
            parts.append("atempo=0.5")
            remaining /= 0.5
        parts.append(f"atempo={remaining:.4f}")
        return ",".join(parts)
