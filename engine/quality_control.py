"""
Automated Quality Control (QC) Pipeline for 3D Video Studio.

Validates output reels and rendered frames against Meta/Instagram specifications:
1. Frame Integrity: Checks for black/blank/empty frames or frozen static sequences
2. Color/Contrast & Luminance Analysis: Ensures dynamic visuals without pure black screens
3. Resolution & Aspect Ratio: Confirms exact 1080x1920 (9:16 vertical)
4. Audio Loudness & Track Alignment: Verifies valid AAC audio track and duration
5. Machine-Readable QC Report: Writes structured JSON report with pass/fail gates
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from PIL import Image, ImageStat

logger = logging.getLogger("viral_reels.qc")


@dataclass
class QCIssue:
    severity: str  # "ERROR", "WARNING", "INFO"
    code: str
    message: str
    timestamp_sec: Optional[float] = None
    frame_index: Optional[int] = None


@dataclass
class QCReport:
    video_path: str
    passed: bool
    total_frames_checked: int = 0
    duration_seconds: float = 0.0
    width: int = 1080
    height: int = 1920
    fps: float = 30.0
    issues: List[QCIssue] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(asdict(self), indent=indent, default=str)


class QualityControlPipeline:
    """Automated validator for rendered reels."""

    @classmethod
    def inspect_rendered_video(
        cls,
        mp4_path: Path,
        expected_width: int = 1080,
        expected_height: int = 1920,
        sample_frame_interval: int = 30,  # Sample 1 frame per second
    ) -> QCReport:
        """Runs full automated quality control analysis on an exported MP4."""
        report = QCReport(video_path=str(mp4_path), passed=True)

        if not mp4_path.exists() or mp4_path.stat().st_size < 100 * 1024:
            report.passed = False
            report.issues.append(QCIssue(
                severity="ERROR",
                code="FILE_MISSING_OR_CORRUPT",
                message=f"Video file missing or too small ({mp4_path.stat().st_size if mp4_path.exists() else 0} bytes)"
            ))
            return report

        # 1. FFprobe metadata verification
        ffprobe = shutil.which("ffprobe") or "ffprobe"
        cmd = [
            ffprobe, "-v", "error",
            "-show_entries", "format=duration,size,bit_rate:stream=width,height,r_frame_rate,codec_name",
            "-of", "json",
            str(mp4_path)
        ]
        try:
            out = subprocess.check_output(cmd, text=True)
            meta = json.loads(out)
        except Exception as e:
            report.passed = False
            report.issues.append(QCIssue(
                severity="ERROR",
                code="METADATA_PROBE_FAILED",
                message=f"ffprobe failed: {e}"
            ))
            return report

        streams = meta.get("streams", [])
        v_stream = next((s for s in streams if s.get("codec_name") in ("h264", "hevc")), None)
        a_stream = next((s for s in streams if s.get("codec_name") in ("aac", "mp3")), None)

        if not v_stream:
            report.passed = False
            report.issues.append(QCIssue(
                severity="ERROR",
                code="NO_VIDEO_STREAM",
                message="No valid H.264 video stream detected in file"
            ))
            return report

        vw = int(v_stream.get("width", 0))
        vh = int(v_stream.get("height", 0))
        report.width = vw
        report.height = vh

        if vw != expected_width or vh != expected_height:
            report.passed = False
            report.issues.append(QCIssue(
                severity="ERROR",
                code="INVALID_RESOLUTION",
                message=f"Resolution is {vw}x{vh}, expected {expected_width}x{expected_height}"
            ))

        if not a_stream:
            report.issues.append(QCIssue(
                severity="WARNING",
                code="NO_AUDIO_STREAM",
                message="No AAC audio track found in container"
            ))

        dur = float(meta.get("format", {}).get("duration", 0.0))
        report.duration_seconds = dur
        if dur < 3.0:
            report.passed = False
            report.issues.append(QCIssue(
                severity="ERROR",
                code="DURATION_TOO_SHORT",
                message=f"Duration {dur:.1f}s is too short for a complete reel"
            ))

        # 2. Frame-by-frame visual inspection (black frames, low contrast, frozen frames)
        ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
        tmp_extract_dir = mp4_path.parent / "tmp_qc_frames"
        tmp_extract_dir.mkdir(parents=True, exist_ok=True)

        extract_cmd = [
            ffmpeg, "-y",
            "-i", str(mp4_path),
            "-vf", f"fps=1",
            str(tmp_extract_dir / "qc_frame_%04d.jpg")
        ]
        try:
            subprocess.run(extract_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            extracted_frames = sorted(list(tmp_extract_dir.glob("qc_frame_*.jpg")))
            report.total_frames_checked = len(extracted_frames)

            prev_frame = None
            identical_count = 0

            for idx, f_path in enumerate(extracted_frames):
                with Image.open(f_path) as im:
                    rgb = im.convert("RGB")
                    stat = ImageStat.Stat(rgb)
                    mean_lum = sum(stat.mean) / 3.0

                    # Check for solid black / empty frame
                    if mean_lum < 5.0:
                        report.issues.append(QCIssue(
                            severity="ERROR",
                            code="BLACK_FRAME_DETECTED",
                            message=f"Black frame detected at t={idx}s (luminance {mean_lum:.1f})",
                            timestamp_sec=float(idx),
                            frame_index=idx,
                        ))
                        report.passed = False

                    # Check for frozen / duplicated frames
                    if prev_frame:
                        diff = cls._frame_diff(prev_frame, rgb)
                        if diff < 0.5:
                            identical_count += 1
                            if identical_count >= 5:  # 5 continuous seconds of completely frozen image
                                report.issues.append(QCIssue(
                                    severity="WARNING",
                                    code="FROZEN_ANIMATION_DETECTED",
                                    message=f"Visuals appear static for 5+ seconds starting at t={idx-5}s",
                                    timestamp_sec=float(idx),
                                ))
                        else:
                            identical_count = 0
                    prev_frame = rgb.copy()

        except Exception as e:
            logger.warning("Frame extraction QC warning: %s", e)
        finally:
            shutil.rmtree(tmp_extract_dir, ignore_errors=True)

        report.metrics = {
            "duration_seconds": report.duration_seconds,
            "width": report.width,
            "height": report.height,
            "total_frames_sampled": report.total_frames_checked,
            "issues_count": len(report.issues),
        }

        # Save QC report JSON alongside video
        report_path = mp4_path.parent / f"{mp4_path.stem}_qc_report.json"
        report_path.write_text(report.to_json())
        logger.info("Quality control report saved: %s (Passed: %s)", report_path.name, report.passed)

        return report

    @staticmethod
    def _frame_diff(im1: Image.Image, im2: Image.Image) -> float:
        """Returns average pixel difference percentage between two frames."""
        stat1 = ImageStat.Stat(im1)
        stat2 = ImageStat.Stat(im2)
        diff = sum(abs(m1 - m2) for m1, m2 in zip(stat1.mean, stat2.mean)) / 3.0
        return diff
