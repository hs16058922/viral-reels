"""
Unified Public Video Generation Studio API.

Single entry point to generate complete autonomous 3D educational animations
from any topic and narration script:
1. Synthesizes voiceover via EdgeTTS
2. Transcribes word-level timestamps via Whisper
3. Builds structured intermediate representation (SceneSpec / VideoSpec)
4. Renders procedural 3D mechanical components & cameras via headless Blender
5. Generates frame-accurate subtitles (.srt)
6. Masters multi-track audio soundtrack with SFX
7. Composites 1080x1920 30fps vertical video via FFmpeg
8. Runs automated Quality Control (QC) inspection
9. Exports inspectable project artifacts (.blend, .srt, SceneSpec JSON, QC report)
"""

from __future__ import annotations

import time
import shutil
import logging
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from PIL import Image, ImageDraw

from config.settings import settings
from engine.scene_spec import (
    VideoSpec,
    RenderEngine,
    save_spec,
)
from engine.scene_director import AISceneDirector
from engine.narration_sync import NarrationSyncEngine
from engine.edge_voice import VoiceEngine
from engine.whisper_captions import CaptionGenerator
from engine.quality_control import QualityControlPipeline, QCReport
from engine.blender_runner import BlenderMechanismRunner
from engine.sfx_manager import SFXManager
from engine.video_formats import FormatCompositor, VideoFormatRotator, ReelVideoFormat
from engine.caption_styles import CaptionStyleRotator
from engine.cover_generator import ReelCoverGenerator
from engine.isometric_animator import IsometricMotionEngine
import subprocess

logger = logging.getLogger("viral_reels.generator")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
EXPORT_DIR = PROJECT_ROOT / "export"
TMP_DIR = PROJECT_ROOT / "tmp"


@dataclass
class VideoResult:
    """Complete inspectable output payload from generate_video()."""
    video_path: Path
    spec_path: Path
    blend_path: Optional[Path]
    subtitles_path: Path
    cover_path: Path
    qc_report_path: Path
    duration_seconds: float
    total_frames: int
    render_time_seconds: float
    fps: int
    qc_passed: bool
    metrics: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "video_path": str(self.video_path),
            "spec_path": str(self.spec_path),
            "blend_path": str(self.blend_path) if self.blend_path else None,
            "subtitles_path": str(self.subtitles_path),
            "cover_path": str(self.cover_path),
            "qc_report_path": str(self.qc_report_path),
            "duration_seconds": self.duration_seconds,
            "total_frames": self.total_frames,
            "render_time_seconds": self.render_time_seconds,
            "fps": self.fps,
            "qc_passed": self.qc_passed,
            "metrics": self.metrics,
        }


def generate_video(
    topic: str,
    script: Optional[str] = None,
    style: Optional[str] = None,
    output_path: Optional[Path] = None,
    preview_mode: bool = False,
    render_engine: str = "workbench",  # "eevee" or "workbench"
    duration_target: Optional[float] = None,
) -> VideoResult:
    """
    Main public API to generate complete autonomous 3D educational animation reels.

    Args:
        topic: Topic identifier or title (e.g. 'mechanical_watch', 'jet_engine', 'human_heart')
        script: Optional custom narration script. If omitted, default topic script is used.
        style: Presentation format override ('CINEMATIC_FULLSCREEN', 'ISOMETRIC_STAGE', etc.)
        output_path: Optional destination path for the final MP4.
        preview_mode: If True, renders a fast low-resolution draft for verification.
        render_engine: 'workbench' (ultra-fast CPU) or 'eevee' (PBR materials & lighting)
        duration_target: Optional duration constraint in seconds.

    Returns:
        VideoResult containing paths to video, .blend file, .srt, SceneSpec JSON, and QC report.
    """
    t_start = time.time()
    topic_clean = topic.lower().replace(" ", "_").replace("-", "_")

    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    covers_dir = EXPORT_DIR / "covers"
    covers_dir.mkdir(parents=True, exist_ok=True)

    final_mp4 = output_path or (EXPORT_DIR / f"{topic_clean}_reel.mp4")
    spec_path = EXPORT_DIR / f"{topic_clean}_scenespec.json"
    blend_path = EXPORT_DIR / f"{topic_clean}_project.blend"
    srt_path = EXPORT_DIR / f"{topic_clean}_subtitles.srt"
    cover_path = covers_dir / f"{topic_clean}_cover.jpg"
    qc_path = EXPORT_DIR / f"{topic_clean}_reel_qc_report.json"

    # 1. Topic definition lookup
    topic_data: Dict[str, Any] = {
        "id": topic_clean,
        "title": topic.replace("_", " ").title(),
        "script": script or _get_default_script_for_topic(topic_clean),
        "bullets": _get_default_bullets_for_topic(topic_clean),
    }
    if style:
        topic_data["video_format"] = style

    logger.info("🎬 [generate_video] Starting Autonomous 3D Studio for: '%s'", topic_data["title"])

    # 2. Voice synthesis via EdgeTTS
    voice_mp3 = TMP_DIR / f"{topic_clean}_voice.mp3"
    logger.info("🎙️ Synthesizing neural voiceover...")
    ve = VoiceEngine()
    ve.synthesize(text=topic_data["script"], output_path=voice_mp3)

    # 3. Whisper word transcription & timestamps
    logger.info("⏱️ Transcribing word timestamps with Whisper...")
    cap_gen = CaptionGenerator(model_size="base")
    txn = cap_gen.transcribe(voice_mp3)
    words = txn.words

    # Measure exact audio duration
    ffprobe = shutil.which("ffprobe") or "ffprobe"
    dur_cmd = [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(voice_mp3)]
    total_duration = float(subprocess.check_output(dur_cmd, text=True).strip())
    if duration_target:
        total_duration = min(total_duration, duration_target)

    # 4. Export SRT subtitles
    srt_content = NarrationSyncEngine.generate_subtitles_srt(words)
    srt_path.write_text(srt_content)
    logger.info("📝 Exported subtitles to: %s", srt_path.name)

    # 5. Build SceneSpec via AI Scene Director
    logger.info("📐 Building structured 3D SceneSpec...")
    engine_enum = RenderEngine.WORKBENCH if "workbench" in render_engine.lower() else RenderEngine.EEVEE
    fps = 30
    video_spec = AISceneDirector.create_video_spec_for_topic(
        topic=topic_data,
        words=words,
        total_duration=total_duration,
        fps=fps,
        render_engine=engine_enum,
    )
    save_spec(video_spec, spec_path)
    logger.info("💾 Saved SceneSpec JSON to: %s", spec_path.name)

    # 6. Render 3D Blender Mechanism Sequence & save .blend file
    b_frames_count = 75 if not preview_mode else 30
    b_engine = "BLENDER_WORKBENCH" if "workbench" in render_engine.lower() else "BLENDER_EEVEE"
    b_out_dir = TMP_DIR / "blender_renders" / topic_clean
    b_out_dir.mkdir(parents=True, exist_ok=True)

    blender_bin = BlenderMechanismRunner.get_blender_binary()
    blender_frames: List[Image.Image] = []

    if blender_bin:
        script_path = PROJECT_ROOT / "scripts" / "blender_advanced_engine.py"
        cmd = [
            blender_bin, "-b",
            "-P", str(script_path),
            "--",
            "--topic", topic_clean,
            "--frames", str(b_frames_count),
            "--width", "720",
            "--height", "1280",
            "--engine", b_engine,
            "--out_dir", str(b_out_dir),
            "--save_blend", str(blend_path),
        ]
        logger.info("🚀 Rendering true 3D mechanism in Blender (%d frames via %s)...", b_frames_count, b_engine)
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

        png_files = sorted(list(b_out_dir.glob("frame_*.png")))
        for p in png_files:
            try:
                blender_frames.append(Image.open(p).convert("RGBA"))
            except Exception:
                pass
        logger.info("✅ Loaded %d true 3D Blender frames for '%s'", len(blender_frames), topic_clean)

    # 7. Select Style Theme & Generate Cover
    theme = CaptionStyleRotator.get_theme_for_topic(topic_data)
    accent_color = theme.active_color
    video_format = VideoFormatRotator.get_format_for_topic(topic_data)

    cover_base = blender_frames[0].convert("RGB") if blender_frames else None
    cover_img = ReelCoverGenerator.generate_cover(
        base_image_path=cover_base,
        hook_line_1=topic_data["title"][:22].upper(),
        hook_line_2="3D MECHANICAL SECRETS",
        category_tag="ENGINEERING EXPLAINED",
        curiosity_sticker="REAL 3D SIMULATION",
        accent_color=accent_color,
        output_path=cover_path,
    )

    # 8. Master multi-track soundtrack with SFX
    master_audio = TMP_DIR / f"{topic_clean}_master.aac"
    num_scenes = max(1, len(video_spec.scenes))
    scene_dur = total_duration / num_scenes
    cut_times = [i * scene_dur for i in range(1, num_scenes)]
    call_times = [(i + 0.3) * scene_dur for i in range(num_scenes)]

    SFXManager.build_mixed_soundtrack(
        voice_path=voice_mp3,
        scene_cut_times=cut_times,
        callout_times=call_times,
        total_duration=total_duration,
        output_path=master_audio,
    )

    # 9. Frame-by-frame compositing pipe via FFmpeg
    total_frames = int(total_duration * fps)
    ffmpeg_bin = shutil.which("ffmpeg") or "ffmpeg"
    ffmpeg_cmd = [
        ffmpeg_bin, "-y",
        "-f", "rawvideo",
        "-vcodec", "rawvideo",
        "-s", "1080x1920",
        "-pix_fmt", "rgb24",
        "-r", str(fps),
        "-i", "-",
        "-i", str(master_audio),
        "-c:v", "libx264",
        "-profile:v", "main",
        "-level", "3.1",
        "-pix_fmt", "yuv420p",
        "-r", str(fps),
        "-g", "60",
        "-keyint_min", "60",
        "-sc_threshold", "0",
        "-preset", "fast",
        "-crf", "20",
        "-c:a", "aac",
        "-b:a", "192k",
        "-ar", "48000",
        "-ac", "2",
        "-movflags", "+faststart",
        "-t", f"{total_duration:.3f}",
        str(final_mp4),
    ]

    logger.info("🎥 Compositing final 1080x1920 30fps reel to: %s...", final_mp4.name)
    proc = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # Clean cinematic studio backdrop (NO cover text baked into background)
    raw_dummy = Image.new("RGB", (1080, 1920), (8, 12, 20))
    d_raw = ImageDraw.Draw(raw_dummy)
    for r in range(1100, 200, -30):
        d_raw.ellipse([(540 - r, 960 - r), (540 + r, 960 + r)], fill=(14, 22, 36))

    framed_dummy = IsometricMotionEngine.prepare_framed_subject(
        raw_scene=raw_dummy,
        target_w=780,
        target_h=1000,
        radius=36,
        accent_color=accent_color,
    )

    try:
        for f_idx in range(total_frames):
            t = f_idx / fps
            if f_idx < 12:  # First 0.4s: Cover hook
                proc.stdin.write(cover_img.convert("RGB").tobytes())
                continue

            scene_idx = min(num_scenes - 1, int(t / scene_dur))
            scene_t = t - (scene_idx * scene_dur)

            # Active caption
            c_words, active_idx = _get_active_caption(t, words)

            # Active 3D Blender frame
            b_frame = None
            if blender_frames:
                b_idx = int((t * 25.0) % len(blender_frames))
                b_frame = blender_frames[b_idx]

            frame_img = FormatCompositor.render_format_frame(
                video_format=ReelVideoFormat.CINEMATIC_FULLSCREEN if preview_mode else video_format,
                t=t,
                total_duration=total_duration,
                scene_idx=scene_idx,
                scene_t=scene_t,
                scene_duration=scene_dur,
                raw_scene_img=raw_dummy,
                framed_scene_img=framed_dummy,
                theme=theme,
                accent_color=accent_color,
                bullets=topic_data["bullets"],
                active_words=c_words,
                active_word_idx=active_idx,
                blender_frame=b_frame,
            )
            proc.stdin.write(frame_img.convert("RGB").tobytes())

        proc.stdin.close()
        proc.wait()
    except Exception as e:
        proc.stdin.close()
        proc.wait()
        raise RuntimeError(f"FFmpeg compositing failed: {e}")

    # 10. Run Quality Control pipeline
    logger.info("🔍 Running automated Quality Control inspection...")
    qc_report = QualityControlPipeline.inspect_rendered_video(final_mp4)

    render_time = time.time() - t_start
    logger.info("🎉 Autonomous 3D Video Studio finished in %.1fs: %s (QC Passed: %s)",
                render_time, final_mp4.name, qc_report.passed)

    return VideoResult(
        video_path=final_mp4,
        spec_path=spec_path,
        blend_path=blend_path if blend_path.exists() else None,
        subtitles_path=srt_path,
        cover_path=cover_path,
        qc_report_path=qc_path,
        duration_seconds=total_duration,
        total_frames=total_frames,
        render_time_seconds=render_time,
        fps=fps,
        qc_passed=qc_report.passed,
        metrics=qc_report.metrics,
    )


# ── Helper Utilities ──────────────────────────────────────────────────────

def _get_active_caption(t: float, words: list, max_words: int = 2) -> tuple:
    groups = []
    i = 0
    while i < len(words):
        chunk = words[i:i + max_words]
        groups.append(chunk)
        i += len(chunk)

    for group in groups:
        g_start = group[0].start
        g_end = group[-1].end + 0.18
        if g_start <= t <= g_end:
            active_idx = 0
            for idx, w in enumerate(group):
                if w.start <= t <= (w.end + 0.12):
                    active_idx = idx
            return [w.word for w in group], active_idx
    return None, -1


def _get_default_script_for_topic(topic: str) -> str:
    if "watch" in topic:
        return (
            "Inside a mechanical watch, there is zero electricity and zero batteries. "
            "It runs entirely on a curled ribbon of spring steel called the mainspring. "
            "As it uncoils, it turns a train of interlocking brass gears that step up rotational speed. "
            "To prevent the power from releasing all at once, the Swiss lever escapement catches and releases "
            "the escape wheel five times every single second using synthetic ruby jewel pallets. "
            "This pulses the balance wheel harmonic hairspring, giving the watch its signature ticking heartbeat."
        )
    elif "jet" in topic:
        return (
            "A commercial jet engine doesn't just push air backward. It swallows twenty tons of atmosphere every minute. "
            "First, the wide-chord titanium fan directs massive bypass airflow around the core for eighty percent of total thrust. "
            "Inside the core, alternating stages of spinning compressor blades squeeze the air to over forty times atmospheric pressure. "
            "Fuel sprays into the annular combustion chamber, exploding into a glowing three-thousand-degree plasma jet. "
            "This roaring inferno spins high-pressure turbine discs that extract thousands of horsepower to drive the front fan."
        )
    elif "heart" in topic:
        return (
            "Your heart is a dual-stage muscular fluid pump that beats over one hundred thousand times every day. "
            "Oxygen-poor blood enters the right atrium and drops into the right ventricle, which fires it into the pulmonary arteries. "
            "Once refreshed with oxygen from your lungs, the arterial blood rushes into the left atrium and fills the thick muscular left ventricle. "
            "During ventricular systole, a massive squeeze forces high-pressure blood through the aortic valve and up into the aortic arch, "
            "delivering life to trillions of cells across your body."
        )
    else:
        return (
            "Every mechanical assembly is a masterpiece of precision engineering and physics. "
            "By balancing kinetic energy, friction, and harmonic resonance, internal components interact "
            "in flawless synchronization to transform raw power into controlled motion."
        )


def _get_default_bullets_for_topic(topic: str) -> List[str]:
    if "watch" in topic:
        return [
            "Coiled spring steel stores pure mechanical potential energy",
            "4-stage gear train multiplies rotational speed to 28,800 VPH",
            "Synthetic ruby pallets lock and release escape wheel teeth",
            "Harmonic hairspring resonates at exact physical frequency",
        ]
    elif "jet" in topic:
        return [
            "Wide-chord titanium fan provides 80% bypass thrust",
            "Multi-stage axial compressors squeeze air by 40 to 1",
            "Annular combustion chamber ignites 3000 degree plasma",
            "High-pressure turbine discs drive central power shaft",
        ]
    elif "heart" in topic:
        return [
            "Right ventricle pumps deoxygenated blood to lung capillaries",
            "Oxygenated blood returns to thick-walled left ventricle",
            "Systolic contraction exerts 120 mmHg arterial pressure",
            "Aortic arch distributes blood flow across arterial branches",
        ]
    else:
        return [
            "Precision mechanical components mesh with zero slippage",
            "Engineered tolerances maintain kinetic equilibrium",
            "Internal cutaway reveals moving physical mechanisms",
        ]


def generate_gemini_video(
    topic: str,
    script: Optional[str] = None,
    output_path: Optional[Path] = None,
    bullets: Optional[List[str]] = None,
) -> VideoResult:
    """Generate complete educational reel using Gemini Veo video base and synchronized audio/captions."""
    from engine.gemini_video_engine import GeminiVideoStudio
    topic_clean = topic.lower().replace(" ", "_")
    topic_data = {
        "id": topic_clean,
        "title": topic.replace("_", " ").title(),
        "script": script or _get_default_script_for_topic(topic_clean),
        "bullets": bullets or _get_default_bullets_for_topic(topic_clean),
        "engine": "gemini",
    }
    out_file = output_path or (EXPORT_DIR / f"{topic_clean}_gemini_reel.mp4")
    final_mp4 = GeminiVideoStudio.build_gemini_reel(topic_data, output_mp4=out_file, mock_if_no_key=True)

    # Run Quality Control
    qc = QualityControlPipeline.inspect_rendered_video(final_mp4)
    qc_path = final_mp4.parent / f"{topic_clean}_qc_report.json"
    with open(qc_path, "w", encoding="utf-8") as f:
        f.write(qc.to_json())

    return VideoResult(
        video_path=final_mp4,
        spec_path=final_mp4.parent / f"{topic_clean}_scenespec.json",
        blend_path=None,
        subtitles_path=final_mp4.parent / f"{topic_clean}_subtitles.srt",
        cover_path=TMP_DIR / f"{topic_clean}_cover.jpg",
        qc_report_path=qc_path,
        duration_seconds=qc.duration_seconds,
        total_frames=qc.total_frames_checked,
        render_time_seconds=0.0,
        fps=30,
        qc_passed=qc.passed,
        metrics=qc.metrics,
    )
