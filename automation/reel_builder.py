"""
Autonomous Reel Builder for Viral Reels Studio.

Generates complete 1080x1920 30fps vertical reels from any topic in topics.json:
1. Synthesizes voiceover via Edge TTS
2. Transcribes word-level timestamps via Whisper
3. Loads or procedurally synthesizes topic-specific 3D scenes (NEVER reuses another topic's images)
4. Multi-scene cinematic cuts with dynamic Ken Burns zooms, pans, and cuts
5. Real-time animated 3D HUD graphics (rotating reticle, laser scanline, telemetry)
6. Dynamic rotating caption styling (Cyber Gold, Minimal 3D Drop Shadow, Crimson Alert, Matrix HUD, Deep Violet)
7. Meta-compliant MP4 encoding: 2.0s Closed GOP, 48kHz Stereo AAC, FastStart moov atom
8. Automatic scratch & export directory cleanup
"""

import asyncio
import logging
import math
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from PIL import Image, ImageDraw, ImageFont

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.caption_styles import CaptionStyleRotator, CaptionTheme
from engine.cover_generator import ReelCoverGenerator
from engine.edge_voice import VoiceEngine
from engine.fonts import load_headline_font, load_sub_font
from engine.hud_graphics import HUDGraphicsEngine
from engine.isometric_animator import IsometricMotionEngine
from engine.sfx_manager import SFXManager
from engine.video_formats import FormatCompositor, ReelVideoFormat, VideoFormatRotator
from engine.whisper_captions import CaptionGenerator

logger = logging.getLogger("viral_reels.reel_builder")

WIDTH, HEIGHT = 1080, 1920
FPS = 30
EXPORT_DIR = PROJECT_ROOT / "export"
TMP_DIR = PROJECT_ROOT / "tmp"
ASSETS_DIR = PROJECT_ROOT / "assets" / "scenes"


class AutonomousReelBuilder:
    """Builds complete cinematic 3D reels with dynamic cuts, HUD graphics, and variable caption styles."""

    @classmethod
    def load_or_generate_scenes(cls, topic: Dict[str, Any]) -> List[Image.Image]:
        """Load topic-specific 3D visual scenes, or procedurally generate CAD renders for the topic.
        
        Strict Guarantee: NEVER uses images belonging to a different topic.
        """
        topic_id = topic["id"]
        topic_scene_dir = ASSETS_DIR / topic_id
        scenes: List[Image.Image] = []

        # 1. Check if dedicated scenes exist for this topic
        if topic_scene_dir.exists():
            image_files = sorted(list(topic_scene_dir.glob("scene_*.jpg")) + list(topic_scene_dir.glob("scene_*.png")))
            # Exclude badged variants
            image_files = [f for f in image_files if "_badged" not in f.name]
            for f in image_files:
                try:
                    im = Image.open(f).convert("RGB")
                    scenes.append(im)
                except Exception as e:
                    logger.warning("Could not open scene %s: %s", f.name, e)

        if scenes:
            logger.info("Loaded %d dedicated 3D scenes for topic '%s'", len(scenes), topic_id)
            return scenes

        # 2. Check if scenes exist in tmp/scenes for this exact topic ID
        tmp_topic_dir = TMP_DIR / "scenes" / topic_id
        if tmp_topic_dir.exists():
            image_files = sorted(list(tmp_topic_dir.glob("scene_*.jpg")))
            for f in image_files:
                try:
                    scenes.append(Image.open(f).convert("RGB"))
                except Exception:
                    pass
            if scenes:
                return scenes

        # 3. Procedural 3D CAD Blueprint Generator (Fallback that never shows wrong imagery)
        logger.info("Generating procedural 3D technical blueprint scenes for '%s'...", topic_id)
        return cls._generate_procedural_scenes(topic)

    @classmethod
    def _generate_procedural_scenes(cls, topic: Dict[str, Any], count: int = 5) -> List[Image.Image]:
        """Generate high-tech procedural 3D blueprint scenes specific to this topic."""
        scenes = []
        accent_color = (0, 229, 255)
        for i in range(count):
            im = Image.new("RGB", (WIDTH, HEIGHT), (8, 12, 20))
            draw = ImageDraw.Draw(im)

            # Draw 3D isometric perspective grid
            grid_color = (18, 30, 48)
            horizon_y = 600
            for gy in range(horizon_y, HEIGHT, 40):
                draw.line([(0, gy), (WIDTH, gy)], fill=grid_color, width=1)
            for gx in range(-WIDTH, WIDTH * 2, 80):
                draw.line([(gx, HEIGHT), (WIDTH // 2, horizon_y)], fill=grid_color, width=1)

            # Center geometric wireframe
            cx, cy = WIDTH // 2, HEIGHT // 2 - 50
            r = 280 + i * 20
            draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(*accent_color, 120), width=3)
            draw.ellipse([cx - r // 2, cy - r // 2, cx + r // 2, cy + r // 2], outline=(255, 215, 0, 90), width=2)
            draw.line([(cx - r - 40, cy), (cx + r + 40, cy)], fill=(*accent_color, 80), width=2)
            draw.line([(cx, cy - r - 40), (cx, cy + r + 40)], fill=(*accent_color, 80), width=2)

            # Topic Technical Label in Center
            font_title = load_headline_font(42)
            tag_text = topic.get("bullets", ["PHYSICS MECHANISM"])[i % len(topic.get("bullets", ["PHYSICS MECHANISM"]))]
            tb = draw.textbbox((0, 0), tag_text[:28].upper(), font=font_title)
            tw = tb[2] - tb[0]
            draw.text(((WIDTH - tw) // 2, cy + r + 80), tag_text[:28].upper(), font=font_title, fill=(255, 255, 255))

            scenes.append(im)
        return scenes

    @classmethod
    def build_reel_for_topic(cls, topic: Dict[str, Any]) -> Path:
        """Fully render video, cover, and audio for a topic with cinematic cuts and unique style."""
        topic_id = topic["id"]
        EXPORT_DIR.mkdir(parents=True, exist_ok=True)
        covers_dir = EXPORT_DIR / "covers"
        covers_dir.mkdir(parents=True, exist_ok=True)

        output_mp4 = EXPORT_DIR / f"{topic_id}_reel.mp4"
        cover_path = covers_dir / f"{topic_id}_cover.jpg"

        # Check if already rendered and valid
        if output_mp4.exists() and output_mp4.stat().st_size > 1024 * 1024:
            logger.info("Reel already built at %s (%.2f MB). Reusing.", output_mp4.name, output_mp4.stat().st_size / (1024 * 1024))
            return output_mp4

        logger.info("🎬 Building automated 3D cinematic reel for topic '%s'...", topic["title"])

        # ── 1. Synthesize Neural Voiceover ─────────────────────────────
        audio_path = TMP_DIR / f"{topic_id}_voice.mp3"
        TMP_DIR.mkdir(parents=True, exist_ok=True)
        logger.info("Synthesizing neural voiceover...")
        ve = VoiceEngine()
        ve.synthesize(text=topic["script"], output_path=audio_path)

        # ── 2. Transcribe Word Timings with Whisper ─────────────────────
        logger.info("Transcribing audio timestamps with Whisper...")
        cap_gen = CaptionGenerator(model_size="base")
        txn = cap_gen.transcribe(audio_path)
        words = txn.words
        total_duration = 35.0
        if words:
            total_duration = words[-1].end + 0.8
        try:
            ffprobe_bin = shutil.which("ffprobe") or "ffprobe"
            cmd = [ffprobe_bin, "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(audio_path)]
            out = subprocess.check_output(cmd, text=True).strip()
            total_duration = float(out)
        except Exception:
            pass

        # ── 3. Select Dynamic Presentation Format & Caption Style ──────
        video_format = VideoFormatRotator.get_format_for_topic(topic)
        theme = CaptionStyleRotator.get_theme_for_topic(topic)
        accent_color = theme.active_color if theme.name != "MINIMAL_DROP_SHADOW" else (0, 229, 255)
        logger.info("Selected unique presentation format for '%s': %s (Caption Theme: %s)",
                    topic["id"], video_format.value, theme.name)

        # ── 4. Load Topic-Specific 3D Visual Scenes ────────────────────
        raw_scenes = cls.load_or_generate_scenes(topic)
        logger.info("Preparing 3D rounded cutaway cards with wireframe edge lighting...")
        framed_scenes = [
            IsometricMotionEngine.prepare_framed_subject(
                raw_scene=s,
                target_w=780,
                target_h=1000,
                radius=36,
                accent_color=accent_color,
            )
            for s in raw_scenes
        ]

        # ── 5. Generate Topic Cover Card ──────────────────────────────
        logger.info("Generating high-CTR flashy cover card...")
        cover_base = raw_scenes[0] if raw_scenes else None
        cover_img = ReelCoverGenerator.generate_cover(
            base_image_path=None,
            hook_line_1=topic.get("cover_hook_1") or topic["title"][:22].upper(),
            hook_line_2=topic.get("cover_hook_2") or "HOW IT WORKS?!",
            category_tag=topic.get("cover_tag") or "ENGINEERING EXPLAINED",
            curiosity_sticker=topic.get("cover_sticker") or "SECRET REVEALED",
            output_path=cover_path,
        )

        # ── 6. Master Multi-Track Soundtrack with SFX (Impacts, Swooshes, UI Pops, Drone) ───
        master_audio_path = TMP_DIR / f"{topic_id}_master_soundtrack.aac"
        num_scenes = max(1, len(raw_scenes))
        scene_duration = total_duration / num_scenes
        scene_cut_times = [i * scene_duration for i in range(1, num_scenes)]
        callout_times = [(i + 0.3) * scene_duration for i in range(num_scenes)]

        logger.info("Mastering multi-track audio soundtrack with SFX (Whooshes, Pops, Sub Impact)...")
        SFXManager.build_mixed_soundtrack(
            voice_path=audio_path,
            scene_cut_times=scene_cut_times,
            callout_times=callout_times,
            total_duration=total_duration,
            output_path=master_audio_path,
        )

        # ── 7. Setup Rendering Pipe ───────────────────────────────────
        total_frames = int(total_duration * FPS)
        logger.info("Rendering %d frames (%.1fs) with %s format and %d 3D scenes to %s...",
                    total_frames, total_duration, video_format.value, len(raw_scenes), output_mp4.name)

        ffmpeg_bin = shutil.which("ffmpeg") or "ffmpeg"
        ffmpeg_cmd = [
            ffmpeg_bin, "-y",
            "-f", "rawvideo",
            "-vcodec", "rawvideo",
            "-s", f"{WIDTH}x{HEIGHT}",
            "-pix_fmt", "rgb24",
            "-r", str(FPS),
            "-i", "-",
            "-i", str(master_audio_path),
            "-c:v", "libx264",
            "-profile:v", "main",
            "-level", "3.1",
            "-pix_fmt", "yuv420p",
            "-r", str(FPS),
            "-g", "60",
            "-keyint_min", "60",
            "-sc_threshold", "0",
            "-preset", "fast",
            "-crf", "18",
            "-c:a", "aac",
            "-b:a", "192k",
            "-ar", "48000",
            "-ac", "2",
            "-movflags", "+faststart",
            "-shortest",
            str(output_mp4),
        ]

        process = subprocess.Popen(
            ffmpeg_cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )

        bullets = topic.get("bullets", [])

        # Main frame-by-frame multi-layer compositing loop
        for frame_idx in range(total_frames):
            t = frame_idx / FPS

            # First 0.4s (frames 0-11): Flashy high-CTR Cover Card hook & thumbnail anchor
            if frame_idx < 12:
                frame_img = cover_img.copy()
                process.stdin.write(frame_img.tobytes())
                continue

            # Active scene index & progress
            scene_idx = min(num_scenes - 1, int(t / scene_duration))
            scene_t = t - (scene_idx * scene_duration)

            c_words, active_idx = cls.get_active_caption(t, words)

            # Render frame using the topic's unique presentation format
            frame_img = FormatCompositor.render_format_frame(
                video_format=video_format,
                t=t,
                total_duration=total_duration,
                scene_idx=scene_idx,
                scene_t=scene_t,
                scene_duration=scene_duration,
                raw_scene_img=raw_scenes[scene_idx],
                framed_scene_img=framed_scenes[scene_idx],
                theme=theme,
                accent_color=accent_color,
                bullets=bullets,
                active_words=c_words,
                active_word_idx=active_idx,
            )

            process.stdin.write(frame_img.convert("RGB").tobytes())

        process.stdin.close()
        _, stderr_data = process.communicate()

        if process.returncode != 0:
            err = stderr_data.decode(errors="replace") if stderr_data else "Unknown"
            raise RuntimeError(f"FFmpeg render failed: {err}")

        logger.info("🎉 Reel successfully built: %s (%.2f MB)", output_mp4.name, output_mp4.stat().st_size / (1024 * 1024))

        # ── 8. Cleanup Temporary Scratch Files ─────────────────────────
        try:
            if audio_path.exists():
                audio_path.unlink()
            cls.cleanup_export_directory(keep_topic_id=topic_id)
        except Exception as e:
            logger.warning("Post-render cleanup: %s", e)

        return output_mp4

    @staticmethod
    def cleanup_export_directory(keep_topic_id: str) -> None:
        """Keep ONLY the current topic's final reel and clean up scratch/intermediate files."""
        if not EXPORT_DIR.exists():
            return
        keep_name = f"{keep_topic_id}_reel.mp4"
        for item in EXPORT_DIR.glob("*"):
            if item.is_file() and item.name != keep_name and item.suffix in (".mp4", ".tmp", ".wav"):
                try:
                    item.unlink()
                    logger.info("Cleaned previous build artifact: %s", item.name)
                except Exception:
                    pass

    @staticmethod
    def get_active_caption(t: float, words: list, max_words: int = 2) -> Tuple[Optional[List[str]], int]:
        """Group transcription words into atomic 2-word caption pills and determine active word index."""
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
