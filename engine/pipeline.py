"""
Main ReelPipeline orchestrator.

Coordinates the full video-creation workflow: voice synthesis →
motion graphics → clip cutting → caption generation → final render.
Each step is timed and produces intermediate artefacts in ``tmp/``.

Usable both as an importable library and from the CLI via
``scripts/generate_reel.py``.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from config.settings import Settings, settings
from engine.edge_voice import VoiceEngine
from engine.ffmpeg_cuts import DynamicCutter
from engine.hyperframes import HyperframeRenderer
from engine.utils import cleanup_temp, ensure_dirs, get_temp_path, setup_logging, validate_media
from engine.whisper_captions import CaptionGenerator, Transcription

logger = logging.getLogger("viral_reels.pipeline")


@dataclass
class PipelineResult:
    """Collects outputs from a pipeline run."""
    voiceover_path: Optional[Path] = None
    caption_path: Optional[Path] = None
    motion_graphics_path: Optional[Path] = None
    cut_video_path: Optional[Path] = None
    final_output_path: Optional[Path] = None
    timings: Dict[str, float] = field(default_factory=dict)
    transcription: Optional[Transcription] = None


@dataclass
class PipelineConfig:
    """Runtime configuration for a single pipeline run."""
    input_path: Optional[Path] = None
    script: Optional[str] = None
    voice: Optional[str] = None
    caption_style: Optional[str] = None
    output_path: Optional[Path] = None
    skip_voice: bool = False
    skip_captions: bool = False
    cut_points: Optional[List[float]] = None
    motion_elements: Optional[List[Dict[str, Any]]] = None


class ReelPipeline:
    """End-to-end reel production pipeline.

    Example::

        pipeline = ReelPipeline()
        config = PipelineConfig(
            script="Check out this amazing product!",
            output_path=Path("export/my_reel.mp4"),
        )
        result = pipeline.run(config)
    """

    def __init__(self, app_settings: Optional[Settings] = None) -> None:
        self.settings = app_settings or settings
        self.voice_engine = VoiceEngine(voice=self.settings.EDGE_TTS_VOICE)
        self.cutter = DynamicCutter()
        self.renderer = HyperframeRenderer(
            width=self.settings.TARGET_WIDTH,
            height=self.settings.TARGET_HEIGHT,
            fps=self.settings.FPS,
        )
        self.caption_gen = CaptionGenerator(model_size=self.settings.WHISPER_MODEL)
        self._result = PipelineResult()

    # ── Individual pipeline steps ───────────────────────────────────

    def load_footage(self, path: Optional[Path] = None) -> Path:
        """Locate and validate the input footage file.

        Args:
            path: Explicit path; if ``None``, looks for the first
                video in ``RAW_FOOTAGE_DIR``.

        Returns:
            Validated media path.

        Raises:
            FileNotFoundError: If no footage is found.
        """
        if path:
            return validate_media(path)

        raw_dir = self.settings.RAW_FOOTAGE_DIR
        if raw_dir.is_dir():
            for f in sorted(raw_dir.iterdir()):
                if f.suffix.lower() in {".mp4", ".mov", ".avi", ".mkv", ".webm"}:
                    logger.info("Auto-detected footage: %s", f)
                    return validate_media(f)

        raise FileNotFoundError(
            f"No video footage found in {raw_dir}. "
            "Provide --input or place files in raw-footage/."
        )

    def generate_voiceover(self, script: str, voice: Optional[str] = None) -> Path:
        """Synthesize a voiceover from *script* text.

        Args:
            script: Text to speak.
            voice: Edge TTS voice name override.

        Returns:
            Path to the generated MP3 audio.
        """
        t0 = time.perf_counter()
        audio_path, timing_data = self.voice_engine.synthesize_with_timestamps(
            script, voice=voice, output_path=get_temp_path("voiceover.mp3")
        )
        self._result.voiceover_path = audio_path
        self._result.timings["voiceover"] = time.perf_counter() - t0
        logger.info("Voiceover generated in %.2fs", self._result.timings["voiceover"])
        return audio_path

    def transcribe_audio(self, audio_path: Optional[Path] = None) -> Transcription:
        """Run Whisper transcription on an audio file.

        Args:
            audio_path: Path to audio. Defaults to the generated
                voiceover.

        Returns:
            :class:`Transcription` with word-level timing.
        """
        t0 = time.perf_counter()
        path = audio_path or self._result.voiceover_path
        if path is None:
            raise ValueError("No audio path provided and no voiceover generated yet.")

        txn = self.caption_gen.transcribe(path)
        self._result.transcription = txn
        self._result.timings["transcription"] = time.perf_counter() - t0
        logger.info("Transcription completed in %.2fs", self._result.timings["transcription"])
        return txn

    def generate_captions(
        self,
        transcription: Optional[Transcription] = None,
        style: Optional[str] = None,
    ) -> Path:
        """Generate styled ASS captions from a transcription.

        Args:
            transcription: Transcription data. Defaults to the last
                transcription.
            style: Caption style name override.

        Returns:
            Path to the ASS caption file.
        """
        t0 = time.perf_counter()
        txn = transcription or self._result.transcription
        if txn is None:
            raise ValueError("No transcription available. Run transcribe_audio() first.")

        style_name = style or self.settings.CAPTION_STYLE
        caption_path = get_temp_path("captions.ass")
        self.caption_gen.generate_ass(txn, style_name=style_name, output_path=caption_path)
        self._result.caption_path = caption_path
        self._result.timings["captions"] = time.perf_counter() - t0
        logger.info("Captions generated in %.2fs", self._result.timings["captions"])
        return caption_path

    def create_motion_graphics(
        self,
        elements: Optional[List[Dict[str, Any]]] = None,
    ) -> Optional[Path]:
        """Render motion-graphics overlays (title cards, lower thirds).

        Args:
            elements: List of element dicts with keys like
                ``type`` (``"title_card"`` | ``"lower_third"``),
                ``text``, ``subtitle``, ``duration``, etc.

        Returns:
            Path to the rendered motion-graphics video, or ``None``
            if no elements are provided.
        """
        if not elements:
            logger.debug("No motion-graphics elements requested.")
            return None

        t0 = time.perf_counter()
        all_frames = []

        for elem in elements:
            elem_type = elem.get("type", "title_card")
            if elem_type == "title_card":
                frames = self.renderer.create_title_card(
                    title=elem.get("text", ""),
                    subtitle=elem.get("subtitle", ""),
                    duration=elem.get("duration", 3.0),
                )
            elif elem_type == "lower_third":
                frames = self.renderer.create_lower_third(
                    name=elem.get("text", ""),
                    title=elem.get("subtitle", ""),
                    duration=elem.get("duration", 4.0),
                )
            else:
                logger.warning("Unknown motion element type: %s", elem_type)
                continue
            all_frames.extend(frames)

        if not all_frames:
            return None

        mgfx_path = get_temp_path("motion_graphics.mp4")
        self.renderer.export_frames_to_video(all_frames, mgfx_path)
        self._result.motion_graphics_path = mgfx_path
        self._result.timings["motion_graphics"] = time.perf_counter() - t0
        logger.info("Motion graphics rendered in %.2fs", self._result.timings["motion_graphics"])
        return mgfx_path

    def apply_cuts(
        self,
        cut_points: Optional[List[float]] = None,
        source: Optional[Path] = None,
    ) -> Path:
        """Trim and re-assemble footage based on cut points.

        Cut points define the boundaries of segments to **keep**.
        E.g. ``[0, 5, 8, 15]`` → keep [0–5] and [8–15].

        Args:
            cut_points: Pairs of (start, end) flattened into a list.
            source: Source video; defaults to loaded footage.

        Returns:
            Path to the reassembled video.
        """
        t0 = time.perf_counter()

        if source is None:
            source = self.load_footage()

        if not cut_points or len(cut_points) < 2:
            # No cuts — just resize.
            output = get_temp_path("cut_video.mp4")
            self.cutter.resize_for_reel(source, output)
            self._result.cut_video_path = output
            self._result.timings["cuts"] = time.perf_counter() - t0
            return output

        # Build clip pairs.
        clips: List[Path] = []
        for i in range(0, len(cut_points) - 1, 2):
            start, end = cut_points[i], cut_points[i + 1]
            clip_path = get_temp_path(f"clip_{i // 2:04d}.mp4")
            self.cutter.trim_clip(source, start, end, clip_path)
            clips.append(clip_path)

        output = get_temp_path("cut_video.mp4")
        if len(clips) == 1:
            clips[0].rename(output)
        else:
            self.cutter.concat_clips(clips, output)

        # Resize to 9:16.
        resized = get_temp_path("cut_video_reel.mp4")
        self.cutter.resize_for_reel(output, resized)

        self._result.cut_video_path = resized
        self._result.timings["cuts"] = time.perf_counter() - t0
        logger.info("Cuts applied in %.2fs (%d segments)", self._result.timings["cuts"], len(clips))
        return resized

    def render_final(
        self,
        output_path: Optional[Path] = None,
    ) -> Path:
        """Compose all intermediate outputs into the final reel.

        Layers: cut video + voiceover audio + burned-in captions.

        Args:
            output_path: Final output path.

        Returns:
            Path to the finished reel MP4.
        """
        t0 = time.perf_counter()
        ensure_dirs(self.settings.OUTPUT_DIR)

        if output_path is None:
            output_path = self.settings.OUTPUT_DIR / "reel_final.mp4"

        base_video = self._result.cut_video_path
        if base_video is None:
            raise ValueError("No video has been cut yet. Run apply_cuts() first.")

        current = base_video

        # Mix in voiceover audio.
        if self._result.voiceover_path is not None:
            with_audio = get_temp_path("with_audio.mp4")
            self.cutter.add_audio_track(current, self._result.voiceover_path, with_audio)
            current = with_audio

        # Burn in captions.
        if self._result.caption_path is not None:
            with_caps = get_temp_path("with_captions.mp4")
            self.caption_gen.burn_captions(current, self._result.caption_path, with_caps)
            current = with_caps

        # Prepend motion graphics if available.
        if self._result.motion_graphics_path is not None:
            final_with_mgfx = get_temp_path("with_mgfx.mp4")
            self.cutter.concat_clips(
                [self._result.motion_graphics_path, current],
                final_with_mgfx,
            )
            current = final_with_mgfx

        # Copy to final output location.
        import shutil
        shutil.copy2(current, output_path)

        self._result.final_output_path = output_path
        self._result.timings["render_final"] = time.perf_counter() - t0
        logger.info("Final render → %s (%.2fs)", output_path, self._result.timings["render_final"])
        return output_path

    # ── Full orchestration ──────────────────────────────────────────

    def run(self, config: Optional[PipelineConfig] = None) -> PipelineResult:
        """Execute the complete pipeline end-to-end.

        Args:
            config: Runtime options. Uses defaults if ``None``.

        Returns:
            :class:`PipelineResult` with all output paths and timing data.
        """
        config = config or PipelineConfig()
        t_start = time.perf_counter()
        setup_logging()

        logger.info("=" * 60)
        logger.info("VIRAL REELS STUDIO — Pipeline Start")
        logger.info("=" * 60)

        ensure_dirs(self.settings.TEMP_DIR, self.settings.OUTPUT_DIR)

        # 1. Voice synthesis.
        if config.script and not config.skip_voice:
            self.generate_voiceover(config.script, voice=config.voice)

        # 2. Motion graphics.
        self.create_motion_graphics(config.motion_elements)

        # 3. Clip cutting / assembly.
        self.apply_cuts(cut_points=config.cut_points, source=config.input_path)

        # 4. Transcription + captions.
        if not config.skip_captions and self._result.voiceover_path:
            self.transcribe_audio()
            self.generate_captions(style=config.caption_style)

        # 5. Final render.
        self.render_final(output_path=config.output_path)

        total = time.perf_counter() - t_start
        self._result.timings["total"] = total

        logger.info("=" * 60)
        logger.info("Pipeline complete in %.2fs", total)
        for step, dur in self._result.timings.items():
            if step != "total":
                logger.info("  %-20s %.2fs", step, dur)
        logger.info("Output: %s", self._result.final_output_path)
        logger.info("=" * 60)

        return self._result
