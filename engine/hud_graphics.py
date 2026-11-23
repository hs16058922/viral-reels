"""
Dynamic 3D HUD & Scientific Graphic Overlays for CurioMotion Reels.

Provides dynamic, animated technical engineering visual elements:
1. Rotating Tech Reticle: Smooth rotating circular angle gauge with technical crosshair
2. HUD Engineering Telemetry: Camera tracking brackets, coordinates, and CAD labels
3. Laser Scanline: High-tech vertical scanning analysis beam
4. Dynamic Scene Badging: Glassmorphism header card with glowing accent borders
"""

import math
from typing import Any, Dict, List, Optional, Tuple
from PIL import Image, ImageDraw, ImageFont

from engine.fonts import load_headline_font, load_sub_font


class HUDGraphicsEngine:
    """Overlays dynamic animated HUD elements onto video frames."""

    @staticmethod
    def draw_hud_overlay(
        img: Image.Image,
        t: float,
        total_duration: float,
        scene_idx: int,
        accent_color: Tuple[int, int, int] = (0, 229, 255),
    ) -> None:
        """Render animated HUD elements directly onto the PIL image frame."""
        width, height = img.size
        draw = ImageDraw.Draw(img)

        # ── 1. Clean Sleek Top Progress Bar (No clunky corner brackets) ──
        # Subtle 2px glowing progress bar at the very top edge
        progress_ratio = min(1.0, max(0.0, t / max(0.1, total_duration)))
        bar_w = int(width * progress_ratio)
        if bar_w > 0:
            draw.line([(0, 2), (bar_w, 2)], fill=accent_color, width=3)

        # ── 2. Minimalist Floating Header Indicator ───────────────────────
        font_hud = load_sub_font(18)
        # Format time e.g. 0:04 / 0:52
        cur_min, cur_sec = divmod(int(t), 60)
        tot_min, tot_sec = divmod(int(total_duration), 60)
        time_text = f"{cur_min:02d}:{cur_sec:02d} / {tot_min:02d}:{tot_sec:02d}"
        
        # Micro pill in top right corner (very subtle, 18px text, 140 alpha)
        draw.text((width - 180, 48), time_text, font=font_hud, fill=(255, 255, 255, 160))
