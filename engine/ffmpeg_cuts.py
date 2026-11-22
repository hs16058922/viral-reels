"""
FFmpeg wrapper for dynamic cuts, transitions, concatenation, and filters.

All operations shell out to ``ffmpeg`` / ``ffprobe`` via :func:`subprocess.run`
so there is no dependency on python-ffmpeg bindings.
"""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from config.settings import settings
from engine.utils import get_temp_path, run_ffmpeg, validate_media

logger = logging.getLogger("viral_reels.ffmpeg_cuts")


class DynamicCutter:
    """High-level FFmpeg wrapper for clip editing and composition.

    Wraps ``ffmpeg`` and ``ffprobe`` subprocess calls for trimming,
    transitions, concatenation, speed ramping, and arbitrary filter
    chains.  Transition presets are loaded from
    ``templates/transitions/presets.json``.
    """

    def __init__(self) -> None:
        self._presets: Dict[str, Any] = self._load_presets()

    # ── Introspection ───────────────────────────────────────────────

    def probe_media(self, filepath: Path) -> Dict[str, Any]:
        """Return duration, codec, and resolution for *filepath*.

        Args:
            filepath: Path to a media file.

        Returns:
            Dict with keys ``duration``, ``width``, ``height``,
            ``codec_name``, and the full ``streams`` list.

        Raises:
            FileNotFoundError: If the file or ``ffprobe`` is missing.
            subprocess.CalledProcessError: On probe failure.
        """
        filepath = validate_media(filepath)
        cmd = [
            "ffprobe",
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            str(filepath),
        ]
        logger.debug("probe cmd: %s", " ".join(cmd))
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)

        info: Dict[str, Any] = {
            "streams": data.get("streams", []),
            "duration": float(data.get("format", {}).get("duration", 0)),
        }

        # Extract first video stream dimensions / codec.
        for stream in info["streams"]:
            if stream.get("codec_type") == "video":
                info["width"] = int(stream.get("width", 0))
                info["height"] = int(stream.get("height", 0))
                info["codec_name"] = stream.get("codec_name", "unknown")
                break

        logger.info(
            "Probed %s — %.2fs, %sx%s, %s",
            filepath.name,
            info["duration"],
            info.get("width", "?"),
            info.get("height", "?"),
            info.get("codec_name", "?"),
        )
        return info

    # ── Trimming ────────────────────────────────────────────────────

    def trim_clip(
        self,
        input_path: Path,
        start: float,
        end: float,
        output_path: Path,
    ) -> Path:
        """Extract a time range from *input_path*.

        Args:
            input_path: Source media file.
            start: Start time in seconds.
            end: End time in seconds.
            output_path: Destination file.

        Returns:
            The *output_path*.
        """
        validate_media(input_path)
        duration = end - start
        run_ffmpeg([
            "-ss", str(start),
            "-i", str(input_path),
            "-t", str(duration),
            "-c", "copy",
            str(output_path),
        ])
        logger.info("Trimmed %s [%.2f–%.2f] → %s", input_path.name, start, end, output_path.name)
        return output_path

    # ── Transitions ─────────────────────────────────────────────────

    def apply_transition(
        self,
        clip_a: Path,
        clip_b: Path,
        transition_type: str = "fade",
        duration: float = 0.5,
        output: Optional[Path] = None,
    ) -> Path:
        """Join two clips with an xfade transition.

        Args:
            clip_a: First clip.
            clip_b: Second clip.
            transition_type: One of the preset names or any valid
                ffmpeg xfade transition string.
            duration: Transition duration in seconds.
            output: Output path; auto-generated if ``None``.

        Returns:
            Path to the resulting file.
        """
        validate_media(clip_a)
        validate_media(clip_b)

        if output is None:
            output = get_temp_path(f"xfade_{clip_a.stem}_{clip_b.stem}.mp4")

        # Resolve preset.
        preset = self._presets.get(transition_type, {})
        xfade_name = preset.get("filter", transition_type)
        dur = preset.get("duration", duration)

        # Need offset = duration_of_clip_a - transition_duration
        info_a = self.probe_media(clip_a)
        offset = max(0, info_a["duration"] - dur)

        run_ffmpeg([
            "-i", str(clip_a),
            "-i", str(clip_b),
            "-filter_complex",
            f"xfade=transition={xfade_name}:duration={dur}:offset={offset}",
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "18",
            str(output),
        ])
        logger.info(
            "Transition '%s' (%.1fs) %s + %s → %s",
            xfade_name, dur, clip_a.name, clip_b.name, output.name,
        )
        return output

    # ── Concatenation ───────────────────────────────────────────────

    def concat_clips(self, clips: Sequence[Path], output: Path) -> Path:
        """Concatenate multiple clips using the concat demuxer.

        Args:
            clips: Ordered list of clip paths.
            output: Destination file.

        Returns:
            The *output* path.
        """
        if not clips:
            raise ValueError("No clips provided for concatenation.")

        list_file = get_temp_path("concat_list.txt")
        with list_file.open("w") as fh:
            for clip in clips:
                validate_media(clip)
                fh.write(f"file '{clip.resolve()}'\n")

        run_ffmpeg([
            "-f", "concat",
            "-safe", "0",
            "-i", str(list_file),
            "-c", "copy",
            str(output),
        ])
        logger.info("Concatenated %d clips → %s", len(clips), output.name)
        return output

    # ── Audio mixing ────────────────────────────────────────────────

    def add_audio_track(
        self,
        video: Path,
        audio: Path,
        output: Path,
        *,
        replace: bool = True,
    ) -> Path:
        """Mux an audio track onto a video file.

        Args:
            video: Source video.
            audio: Audio file to add.
            output: Destination file.
            replace: If ``True`` replace existing audio; otherwise mix.

        Returns:
            The *output* path.
        """
        validate_media(video)
        map_args: List[str]
        if replace:
            map_args = ["-map", "0:v:0", "-map", "1:a:0"]
        else:
            map_args = [
                "-filter_complex", "amix=inputs=2:duration=first",
                "-map", "0:v:0",
            ]

        run_ffmpeg([
            "-i", str(video),
            "-i", str(audio),
            *map_args,
            "-c:v", "copy",
            "-c:a", "aac",
            "-shortest",
            str(output),
        ])
        logger.info("Added audio %s → %s", audio.name, output.name)
        return output

    # ── 9:16 reframing ──────────────────────────────────────────────

    def resize_for_reel(self, input_path: Path, output: Path) -> Path:
        """Crop and/or pad video to 9:16 portrait (1080×1920).

        Centre-crops landscape footage or pads portrait footage to fill
        the target resolution defined in settings.

        Args:
            input_path: Source video.
            output: Destination file.

        Returns:
            The *output* path.
        """
        validate_media(input_path)
        w = settings.TARGET_WIDTH
        h = settings.TARGET_HEIGHT

        vf = (
            f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
            f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:black,"
            f"setsar=1"
        )
        run_ffmpeg([
            "-i", str(input_path),
            "-vf", vf,
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "18",
            "-c:a", "copy",
            str(output),
        ])
        logger.info("Resized for reel → %s (%dx%d)", output.name, w, h)
        return output

    # ── Speed ramp ──────────────────────────────────────────────────

    def speed_ramp(
        self,
        input_path: Path,
        output: Path,
        segments: Sequence[Tuple[float, float, float]],
    ) -> Path:
        """Apply variable speed to segments of a video.

        Args:
            input_path: Source video.
            output: Destination file.
            segments: List of ``(start, end, speed_factor)`` tuples.
                A *speed_factor* of ``2.0`` plays at double speed;
                ``0.5`` plays at half speed.

        Returns:
            The *output* path.
        """
        validate_media(input_path)
        # Build per-segment clips, then concatenate.
        parts: List[Path] = []
        for idx, (start, end, factor) in enumerate(segments):
            part = get_temp_path(f"ramp_part_{idx}.mp4")
            pts = 1.0 / factor
            atempo = self._atempo_chain(factor)
            run_ffmpeg([
                "-ss", str(start),
                "-i", str(input_path),
                "-t", str(end - start),
                "-filter_complex",
                f"[0:v]setpts={pts}*PTS[v];[0:a]{atempo}[a]",
                "-map", "[v]",
                "-map", "[a]",
                "-c:v", "libx264",
                "-preset", "fast",
                "-crf", "18",
                str(part),
            ])
            parts.append(part)

        self.concat_clips(parts, output)
        logger.info("Speed-ramped %d segments → %s", len(segments), output.name)
        return output

    # ── Arbitrary filter chain ──────────────────────────────────────

    def apply_filter_chain(
        self,
        input_path: Path,
        filters: str,
        output: Path,
    ) -> Path:
        """Apply an arbitrary ffmpeg video filter chain.

        Args:
            input_path: Source media file.
            filters: Raw ffmpeg ``-vf`` / ``-filter_complex`` string.
            output: Destination file.

        Returns:
            The *output* path.
        """
        validate_media(input_path)
        run_ffmpeg([
            "-i", str(input_path),
            "-filter_complex", filters,
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "18",
            str(output),
        ])
        logger.info("Applied filter chain → %s", output.name)
        return output

    # ── Private helpers ─────────────────────────────────────────────

    @staticmethod
    def _load_presets() -> Dict[str, Any]:
        """Load transition presets from the JSON template."""
        path = settings.transition_presets_path
        if path.is_file():
            with path.open() as fh:
                return json.load(fh)
        logger.warning("Transition presets not found at %s — using defaults.", path)
        return {}

    @staticmethod
    def _atempo_chain(factor: float) -> str:
        """Build an atempo filter chain for *factor*.

        ``atempo`` only accepts values in [0.5, 100.0].  For extreme
        values we chain multiple filters.
        """
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
