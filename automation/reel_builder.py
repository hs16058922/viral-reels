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
from engine.blender_runner import BlenderMechanismRunner
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

        # 3. Fail fast if no photorealistic 3D cutaways exist for this topic
        raise FileNotFoundError(
            f"No dedicated 3D visual scenes found for topic '{topic_id}' in {topic_scene_dir}. "
            "Please ensure assets/scenes/{topic_id}/scene_1.jpg to scene_5.jpg are committed before building the reel."
        )

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
        # Studio reels only: real 3D SceneSpec renders (see automation/studio_ci.py).
        from automation.studio_ci import build_local
        return build_local(topic)

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
