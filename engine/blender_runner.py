"""
Blender Headless 3D Mechanism Runner for CurioMotion Reels.

Orchestrates headless Blender execution to render true 3D mechanical
components, orbital camera movements, and exploded assemblies.
"""

import os
import shutil
import logging
import subprocess
from pathlib import Path
from typing import List, Optional
from PIL import Image

logger = logging.getLogger("viral_reels.blender")
PROJECT_ROOT = Path(__file__).resolve().parent.parent


class BlenderMechanismRunner:
    """Detects Blender and generates true 3D animated mechanism sequences."""

    _cached_frames: dict = {}

    @classmethod
    def get_blender_binary(cls) -> Optional[str]:
        """Find Blender CLI binary across macOS and Linux CI environments."""
        # 1. Standard PATH lookup
        found = shutil.which("blender")
        if found:
            return found

        # 2. macOS Application bundle locations
        mac_paths = [
            "/Applications/Blender.app/Contents/MacOS/Blender",
            "~/Applications/Blender.app/Contents/MacOS/Blender",
            "/opt/homebrew/bin/blender",
            "/usr/local/bin/blender",
        ]
        for p in mac_paths:
            expanded = os.path.expanduser(p)
            if os.path.isfile(expanded) and os.access(expanded, os.X_OK):
                return expanded

        # 3. Linux common paths
        linux_paths = [
            "/usr/bin/blender",
            "/snap/bin/blender",
        ]
        for p in linux_paths:
            if os.path.isfile(p) and os.access(p, os.X_OK):
                return p

        return None

    @classmethod
    def is_available(cls) -> bool:
        """Check if Blender is installed and callable."""
        return cls.get_blender_binary() is not None

    @classmethod
    def render_mechanism_sequence(
        cls,
        topic_id: str,
        frames: int = 75,
        width: int = 720,
        height: int = 1280,
    ) -> List[Image.Image]:
        """
        Renders transparent PNG sequence of 3D exploded mechanism.
        Returns list of RGBA PIL Images ready for composite overlay.
        """
        cache_key = (topic_id, frames, width, height)
        if cache_key in cls._cached_frames:
            return cls._cached_frames[cache_key]

        blender_bin = cls.get_blender_binary()
        if not blender_bin:
            logger.warning("Blender binary not found. Falling back to procedural 2.5D engine.")
            return []

        # Route advanced technical studio topics to blender_advanced_engine.py
        adv_topics = ["watch", "escapement", "jet", "heart", "cardiac", "engine", "gear"]
        use_advanced = any(k in topic_id.lower() for k in adv_topics)

        if use_advanced:
            script_path = PROJECT_ROOT / "scripts" / "blender_advanced_engine.py"
        else:
            script_path = PROJECT_ROOT / "scripts" / "blender_render_mechanism.py"

        out_dir = PROJECT_ROOT / "tmp" / "blender_renders" / topic_id
        out_dir.mkdir(parents=True, exist_ok=True)

        cmd = [
            blender_bin,
            "-b",
            "-P", str(script_path),
            "--",
            "--topic", topic_id,
            "--frames", str(frames),
            "--width", str(width),
            "--height", str(height),
            "--out_dir", str(out_dir),
        ]

        logger.info("🎬 Launching Blender Headless 3D render for '%s' (%d frames)...", topic_id, frames)
        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=120)
            if res.returncode != 0:
                logger.error("Blender render failed: %s", res.stderr[-500:])
                return []
        except Exception as e:
            logger.error("Blender execution error: %s", e)
            return []

        # Load rendered PNG frames
        png_files = sorted(list(out_dir.glob("frame_*.png")))
        if not png_files:
            logger.warning("No PNG frames found in Blender output dir: %s", out_dir)
            return []

        loaded_images = []
        for p in png_files:
            try:
                loaded_images.append(Image.open(p).convert("RGBA"))
            except Exception:
                pass

        logger.info("✅ Loaded %d true 3D Blender frames for '%s'", len(loaded_images), topic_id)
        cls._cached_frames[cache_key] = loaded_images
        return loaded_images
