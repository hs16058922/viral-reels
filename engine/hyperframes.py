"""
Motion graphics renderer — Pillow-based frame-by-frame generation.

Generates title cards, lower thirds, and animated text sequences as
PNG frame sequences, then compiles them to video via ``ffmpeg``.
"""

from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Sequence, Tuple

from PIL import Image, ImageDraw, ImageFont

from config.settings import settings
from engine.utils import ensure_dirs, get_temp_path, run_ffmpeg

logger = logging.getLogger("viral_reels.hyperframes")

AnimationType = Literal["fade_in", "slide_up", "scale_bounce", "typewriter"]

# Default colour palette
_DEFAULT_BG = (0, 0, 0, 255)
_DEFAULT_FG = (255, 255, 255, 255)
_ACCENT = (255, 215, 0, 255)  # #FFD700


def _load_font(name: str = "Arial", size: int = 72, bold: bool = False) -> ImageFont.FreeTypeFont:
    """Try to load a TrueType font, falling back to the default bitmap font."""
    candidates = [
        name,
        f"{name} Bold" if bold else name,
        "Impact",
        "DejaVuSans-Bold",
        "DejaVuSans",
    ]
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size)
        except (OSError, IOError):
            continue
    logger.warning("No TrueType font found — using Pillow default.")
    return ImageFont.load_default()


class HyperframeRenderer:
    """Create motion-graphics frames with Pillow and compile to video.

    All rendering targets the resolution defined in
    :pydata:`config.settings.settings` (default 1080×1920 @ 30 fps).
    """

    def __init__(
        self,
        width: Optional[int] = None,
        height: Optional[int] = None,
        fps: Optional[int] = None,
    ) -> None:
        self.width = width or settings.TARGET_WIDTH
        self.height = height or settings.TARGET_HEIGHT
        self.fps = fps or settings.FPS

    # ── Single-frame generators ─────────────────────────────────────

    def create_text_frame(
        self,
        text: str,
        style: Optional[Dict[str, Any]] = None,
        animation_type: AnimationType = "fade_in",
        progress: float = 1.0,
    ) -> Image.Image:
        """Render a single text frame with optional animation progress.

        Args:
            text: The text string to render.
            style: Dict with optional keys ``font_size``, ``font_name``,
                ``fg_color``, ``bg_color``, ``bold``.
            animation_type: Animation curve to apply.
            progress: A float in [0, 1] representing animation progress.

        Returns:
            A Pillow ``Image`` (RGBA).
        """
        style = style or {}
        font_size: int = style.get("font_size", 80)
        font_name: str = style.get("font_name", "Impact")
        fg: Tuple[int, ...] = style.get("fg_color", _DEFAULT_FG)
        bg: Tuple[int, ...] = style.get("bg_color", _DEFAULT_BG)
        bold: bool = style.get("bold", True)

        img = Image.new("RGBA", (self.width, self.height), bg)
        draw = ImageDraw.Draw(img)
        font = _load_font(font_name, font_size, bold)

        bbox = draw.textbbox((0, 0), text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        x = (self.width - tw) // 2
        y = (self.height - th) // 2

        # Apply animation transforms.
        alpha = int(255 * min(progress, 1.0))
        if animation_type == "fade_in":
            fg = (*fg[:3], alpha)
        elif animation_type == "slide_up":
            offset = int((1.0 - progress) * self.height * 0.3)
            y += offset
        elif animation_type == "scale_bounce":
            scale = 0.5 + 0.5 * self._bounce_ease(progress)
            scaled_size = max(8, int(font_size * scale))
            font = _load_font(font_name, scaled_size, bold)
            bbox = draw.textbbox((0, 0), text, font=font)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            x = (self.width - tw) // 2
            y = (self.height - th) // 2
        elif animation_type == "typewriter":
            char_count = max(1, int(len(text) * progress))
            text = text[:char_count]

        # Outline / shadow
        for dx, dy in [(-2, -2), (-2, 2), (2, -2), (2, 2)]:
            draw.text((x + dx, y + dy), text, font=font, fill=(0, 0, 0, alpha))
        draw.text((x, y), text, font=font, fill=fg)

        return img

    def create_title_card(
        self,
        title: str,
        subtitle: str = "",
        duration: float = 3.0,
    ) -> List[Image.Image]:
        """Generate a full frame sequence for a title card.

        Args:
            title: Primary title text.
            subtitle: Secondary smaller text.
            duration: Length in seconds.

        Returns:
            List of RGBA ``Image`` frames.
        """
        total_frames = int(duration * self.fps)
        fade_frames = min(int(0.5 * self.fps), total_frames // 4)
        frames: List[Image.Image] = []

        for i in range(total_frames):
            # Fade in / out progress
            if i < fade_frames:
                prog = i / fade_frames
            elif i > total_frames - fade_frames:
                prog = (total_frames - i) / fade_frames
            else:
                prog = 1.0

            img = Image.new("RGBA", (self.width, self.height), _DEFAULT_BG)
            draw = ImageDraw.Draw(img)
            alpha = int(255 * prog)

            # Title
            title_font = _load_font("Impact", 96, bold=True)
            tb = draw.textbbox((0, 0), title, font=title_font)
            tw = tb[2] - tb[0]
            tx = (self.width - tw) // 2
            ty = self.height // 2 - 80
            for dx, dy in [(-3, -3), (-3, 3), (3, -3), (3, 3)]:
                draw.text((tx + dx, ty + dy), title, font=title_font, fill=(0, 0, 0, alpha))
            draw.text((tx, ty), title, font=title_font, fill=(255, 255, 255, alpha))

            # Subtitle
            if subtitle:
                sub_font = _load_font("Arial", 48, bold=False)
                sb = draw.textbbox((0, 0), subtitle, font=sub_font)
                sw = sb[2] - sb[0]
                sx = (self.width - sw) // 2
                sy = ty + 130
                draw.text((sx, sy), subtitle, font=sub_font, fill=(*_ACCENT[:3], alpha))

            frames.append(img)

        logger.info("Title card: '%s' — %d frames (%.1fs)", title, len(frames), duration)
        return frames

    def create_lower_third(
        self,
        name: str,
        title: str,
        duration: float = 4.0,
    ) -> List[Image.Image]:
        """Generate a lower-third name strap animation.

        Args:
            name: Person's name (large text).
            title: Role or descriptor (smaller text).
            duration: Length in seconds.

        Returns:
            List of RGBA ``Image`` frames.
        """
        total_frames = int(duration * self.fps)
        slide_frames = int(0.4 * self.fps)
        frames: List[Image.Image] = []

        bar_height = 160
        bar_y = self.height - 350

        for i in range(total_frames):
            img = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)

            # Slide-in progress
            if i < slide_frames:
                prog = i / slide_frames
            elif i > total_frames - slide_frames:
                prog = (total_frames - i) / slide_frames
            else:
                prog = 1.0

            bar_w = int(self.width * 0.85 * prog)
            x_off = (self.width - int(self.width * 0.85)) // 2

            # Background bar
            draw.rectangle(
                [x_off, bar_y, x_off + bar_w, bar_y + bar_height],
                fill=(0, 0, 0, 200),
            )
            # Accent stripe
            draw.rectangle(
                [x_off, bar_y, x_off + 6, bar_y + bar_height],
                fill=_ACCENT,
            )

            if prog > 0.3:
                alpha = int(255 * min((prog - 0.3) / 0.3, 1.0))
                name_font = _load_font("Arial", 52, bold=True)
                draw.text(
                    (x_off + 30, bar_y + 20),
                    name,
                    font=name_font,
                    fill=(255, 255, 255, alpha),
                )
                title_font = _load_font("Arial", 36, bold=False)
                draw.text(
                    (x_off + 30, bar_y + 85),
                    title,
                    font=title_font,
                    fill=(*_ACCENT[:3], alpha),
                )

            frames.append(img)

        logger.info("Lower third: '%s' — %d frames (%.1fs)", name, len(frames), duration)
        return frames

    # ── Sequence animation ──────────────────────────────────────────

    def animate_sequence(
        self,
        frames: Sequence[Image.Image],
        motion_type: AnimationType = "fade_in",
    ) -> List[Image.Image]:
        """Apply a secondary motion pass over an existing frame sequence.

        Args:
            frames: Input frames.
            motion_type: Animation curve to apply globally.

        Returns:
            New list of transformed frames.
        """
        total = len(frames)
        if total == 0:
            return []

        result: List[Image.Image] = []
        for i, frame in enumerate(frames):
            progress = i / max(total - 1, 1)

            if motion_type == "fade_in":
                alpha_factor = min(progress * 2, 1.0)
                out = frame.copy()
                out.putalpha(
                    out.getchannel("A").point(lambda a: int(a * alpha_factor))
                )
                result.append(out)
            elif motion_type == "slide_up":
                offset = int((1.0 - min(progress * 2, 1.0)) * self.height * 0.1)
                canvas = Image.new("RGBA", (self.width, self.height), _DEFAULT_BG)
                canvas.paste(frame, (0, offset), frame)
                result.append(canvas)
            else:
                result.append(frame.copy())

        logger.debug("animate_sequence: applied '%s' to %d frames", motion_type, total)
        return result

    # ── Export ───────────────────────────────────────────────────────

    def export_frames_to_video(
        self,
        frames: Sequence[Image.Image],
        output_path: Path,
        fps: Optional[int] = None,
    ) -> Path:
        """Write a frame sequence to an MP4 video via ffmpeg.

        Frames are written as numbered PNGs into a temp directory, then
        compiled with ``ffmpeg``.

        Args:
            frames: Ordered RGBA images.
            output_path: Destination ``.mp4`` path.
            fps: Frames per second (defaults to instance fps).

        Returns:
            The *output_path*.
        """
        fps = fps or self.fps
        frame_dir = get_temp_path("hyperframes")
        ensure_dirs(frame_dir)

        for idx, frame in enumerate(frames):
            rgb = frame.convert("RGB")
            rgb.save(frame_dir / f"frame_{idx:06d}.png")

        run_ffmpeg([
            "-framerate", str(fps),
            "-i", str(frame_dir / "frame_%06d.png"),
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "18",
            "-pix_fmt", "yuv420p",
            str(output_path),
        ])
        logger.info("Exported %d frames → %s (%d fps)", len(frames), output_path.name, fps)
        return output_path

    # ── Private helpers ─────────────────────────────────────────────

    @staticmethod
    def _bounce_ease(t: float) -> float:
        """Simple bounce-out easing function."""
        if t < 0.5:
            return 2 * t * t
        t = 2 * t - 1
        return -0.5 * (t * (t - 2) - 1)
