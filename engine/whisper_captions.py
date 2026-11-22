"""
OpenAI Whisper transcription → SRT / ASS caption generator.

Provides word-level timestamps for the viral "karaoke-style" caption
effect where the currently spoken word is highlighted in a different
colour.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from config.settings import settings
from engine.utils import format_ass_timestamp, format_timestamp, get_temp_path, run_ffmpeg, validate_media

logger = logging.getLogger("viral_reels.whisper_captions")


@dataclass
class WordTiming:
    """A single word with its start and end timestamps."""
    word: str
    start: float
    end: float


@dataclass
class Transcription:
    """Full transcription result containing segments and word timings."""
    text: str = ""
    segments: List[Dict[str, Any]] = field(default_factory=list)
    words: List[WordTiming] = field(default_factory=list)
    language: str = "en"


class CaptionGenerator:
    """Generate SRT and ASS captions from audio using OpenAI Whisper.

    Supports word-level timing for the viral highlight style.

    Example::

        gen = CaptionGenerator()
        txn = gen.transcribe(Path("audio.mp3"))
        gen.generate_srt(txn, Path("out.srt"))
        gen.generate_ass(txn, "bold_pop", Path("out.ass"))
        gen.burn_captions(Path("video.mp4"), Path("out.ass"), Path("final.mp4"))
    """

    def __init__(self, model_size: Optional[str] = None) -> None:
        self.model_size = model_size or settings.WHISPER_MODEL
        self._model: Any = None

    # ── Transcription ───────────────────────────────────────────────

    def transcribe(
        self,
        audio_path: Path,
        model_size: Optional[str] = None,
    ) -> Transcription:
        """Transcribe *audio_path* and return word-level timestamps.

        Args:
            audio_path: Path to an audio file.
            model_size: Override the default whisper model.

        Returns:
            A :class:`Transcription` with segments and word timings.
        """
        validate_media(audio_path)
        size = model_size or self.model_size
        logger.info("Loading Whisper model '%s'…", size)

        import whisper  # Lazy import — heavy dependency.

        if self._model is None or size != self.model_size:
            self._model = whisper.load_model(size)
            self.model_size = size

        result = self._model.transcribe(
            str(audio_path),
            word_timestamps=True,
            verbose=False,
        )

        txn = Transcription(
            text=result.get("text", "").strip(),
            segments=result.get("segments", []),
            language=result.get("language", "en"),
        )

        # Extract word-level timings from segments.
        for seg in txn.segments:
            for w in seg.get("words", []):
                txn.words.append(WordTiming(
                    word=w.get("word", "").strip(),
                    start=float(w.get("start", 0)),
                    end=float(w.get("end", 0)),
                ))

        logger.info(
            "Transcribed %s — %d words, language=%s",
            audio_path.name, len(txn.words), txn.language,
        )
        return txn

    # ── SRT output ──────────────────────────────────────────────────

    def generate_srt(
        self,
        transcription: Transcription,
        output_path: Path,
    ) -> Path:
        """Write an SRT subtitle file from a transcription.

        Groups words into ~8-word subtitle lines.

        Args:
            transcription: The transcription result.
            output_path: Destination ``.srt`` path.

        Returns:
            The *output_path*.
        """
        lines: List[str] = []
        groups = self._group_words(transcription.words, max_words=8)

        for idx, group in enumerate(groups, 1):
            start = format_timestamp(group[0].start)
            end = format_timestamp(group[-1].end)
            text = " ".join(w.word for w in group)
            lines.append(f"{idx}")
            lines.append(f"{start} --> {end}")
            lines.append(text)
            lines.append("")

        output_path.write_text("\n".join(lines), encoding="utf-8")
        logger.info("Generated SRT: %s (%d cues)", output_path.name, len(groups))
        return output_path

    # ── ASS output ──────────────────────────────────────────────────

    def generate_ass(
        self,
        transcription: Transcription,
        style_name: str = "bold_pop",
        output_path: Optional[Path] = None,
    ) -> Path:
        """Write an ASS subtitle file with styled formatting.

        Args:
            transcription: The transcription result.
            style_name: Caption style template name.
            output_path: Destination; auto-generated if ``None``.

        Returns:
            The output path.
        """
        if output_path is None:
            output_path = get_temp_path("captions.ass")

        template_path = (
            settings.project_root / "templates" / "caption_styles" / f"{style_name}.ass"
        )

        # Read template header.
        if template_path.is_file():
            header = template_path.read_text(encoding="utf-8")
            # Strip any existing [Events] section — we regenerate it.
            if "[Events]" in header:
                header = header[: header.index("[Events]")]
        else:
            header = self._default_ass_header(style_name)
            logger.warning("Template '%s' not found — using built-in header.", style_name)

        # Build events.
        events = ["[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]
        if style_name == "bold_pop" and transcription.words:
            events.extend(self.highlight_active_word(transcription.words, template=style_name))
        else:
            groups = self._group_words(transcription.words, max_words=3)
            for group in groups:
                start = format_ass_timestamp(group[0].start)
                end = format_ass_timestamp(group[-1].end)
                text = " ".join(w.word for w in group)
                events.append(
                    f"Dialogue: 0,{start},{end},Default,,0,0,0,,{text}"
                )

        output_path.write_text(header + "\n".join(events) + "\n", encoding="utf-8")
        event_count = len(events) - 2  # subtract header lines
        logger.info("Generated ASS: %s (%d events, style=%s)", output_path.name, max(0, event_count), style_name)
        return output_path

    # ── Word-level captions ─────────────────────────────────────────

    def word_level_captions(
        self,
        transcription: Transcription,
    ) -> List[Dict[str, Any]]:
        """Return per-word timing data for viral karaoke-style captions.

        Returns:
            List of dicts with ``word``, ``start``, ``end`` keys.
        """
        return [
            {"word": w.word, "start": w.start, "end": w.end}
            for w in transcription.words
        ]

    def highlight_active_word(
        self,
        words: List[WordTiming],
        template: str = "bold_pop",
    ) -> List[str]:
        """Generate ASS dialogue lines with the active word highlighted.

        Shows 2–3 words at a time; the currently spoken word is
        rendered in a highlight colour.

        Args:
            words: Word timing list.
            template: Style template name (determines highlight colour).

        Returns:
            List of ASS ``Dialogue`` lines.
        """
        highlight_color = "&H0000D7FF&"  # FFD700 in ASS BGR order
        normal_color = "&H00FFFFFF&"

        groups = self._group_words(words, max_words=3)
        events: List[str] = []

        for group in groups:
            group_start = format_ass_timestamp(group[0].start)
            group_end = format_ass_timestamp(group[-1].end)

            for active_idx, active_word in enumerate(group):
                w_start = format_ass_timestamp(active_word.start)
                w_end = format_ass_timestamp(active_word.end)

                parts: List[str] = []
                for j, w in enumerate(group):
                    if j == active_idx:
                        parts.append(f"{{\\c{highlight_color}\\b1}}{w.word}{{\\c{normal_color}\\b0}}")
                    else:
                        parts.append(w.word)

                text = " ".join(parts)
                events.append(
                    f"Dialogue: 0,{w_start},{w_end},Default,,0,0,0,,{text}"
                )

        logger.info("Word-highlight captions: %d events", len(events))
        return events

    # ── Burn captions into video ────────────────────────────────────

    def burn_captions(
        self,
        video_path: Path,
        caption_path: Path,
        output_path: Path,
    ) -> Path:
        """Hard-code subtitles into a video via ffmpeg ``ass`` filter.

        Args:
            video_path: Source video.
            caption_path: ASS or SRT subtitle file.
            output_path: Destination video.

        Returns:
            The *output_path*.
        """
        validate_media(video_path)
        # Escape colons and backslashes for ffmpeg filter syntax.
        escaped = str(caption_path.resolve()).replace("\\", "/").replace(":", "\\:")

        run_ffmpeg([
            "-i", str(video_path),
            "-vf", f"ass='{escaped}'",
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "18",
            "-c:a", "copy",
            str(output_path),
        ])
        logger.info("Burned captions → %s", output_path.name)
        return output_path

    # ── Private helpers ─────────────────────────────────────────────

    @staticmethod
    def _group_words(
        words: List[WordTiming],
        max_words: int = 8,
    ) -> List[List[WordTiming]]:
        """Split a word list into groups of *max_words*."""
        groups: List[List[WordTiming]] = []
        for i in range(0, len(words), max_words):
            group = words[i : i + max_words]
            if group:
                groups.append(group)
        return groups

    @staticmethod
    def _default_ass_header(style_name: str) -> str:
        """Return a minimal built-in ASS header."""
        return (
            "[Script Info]\n"
            f"Title: Viral Reels Captions ({style_name})\n"
            "ScriptType: v4.00+\n"
            "PlayResX: 1080\n"
            "PlayResY: 1920\n"
            "WrapStyle: 0\n"
            "\n"
            "[V4+ Styles]\n"
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
            "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
            "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
            "Alignment, MarginL, MarginR, MarginV, Encoding\n"
            "Style: Default,Impact,72,&H00FFFFFF,&H000000FF,"
            "&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,4,2,2,40,40,120,1\n"
            "\n"
        )
