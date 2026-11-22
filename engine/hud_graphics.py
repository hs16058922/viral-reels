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

        # ── 1. Corner Framing Brackets (Cinematic Viewfinder) ─────────────
        corner_len = 40
        corner_pad = 48
        bracket_color = (*accent_color, 160)

        # Top-Left
        draw.line([(corner_pad, corner_pad), (corner_pad + corner_len, corner_pad)], fill=accent_color, width=3)
        draw.line([(corner_pad, corner_pad), (corner_pad, corner_pad + corner_len)], fill=accent_color, width=3)

        # Top-Right
        draw.line([(width - corner_pad, corner_pad), (width - corner_pad - corner_len, corner_pad)], fill=accent_color, width=3)
        draw.line([(width - corner_pad, corner_pad), (width - corner_pad, corner_pad + corner_len)], fill=accent_color, width=3)

        # Bottom-Left
        draw.line([(corner_pad, height - corner_pad), (corner_pad + corner_len, height - corner_pad)], fill=accent_color, width=3)
        draw.line([(corner_pad, height - corner_pad), (corner_pad, height - corner_pad - corner_len)], fill=accent_color, width=3)

        # Bottom-Right
        draw.line([(width - corner_pad, height - corner_pad), (width - corner_pad - corner_len, height - corner_pad)], fill=accent_color, width=3)
        draw.line([(width - corner_pad, height - corner_pad), (width - corner_pad, height - corner_pad - corner_len)], fill=accent_color, width=3)

        # ── 2. Rotating Telemetry Reticle (Top-Right HUD) ─────────────────
        reticle_cx = width - 110
        reticle_cy = 100
        radius = 28

        # Static outer ring
        draw.ellipse(
            [reticle_cx - radius, reticle_cy - radius, reticle_cx + radius, reticle_cy + radius],
            outline=(*accent_color, 120),
            width=2,
        )

        # Rotating crosshair ticks
        angle_rad = math.radians((t * 70.0) % 360)
        cos_a = math.cos(angle_rad)
        sin_a = math.sin(angle_rad)

        tick_inner = 14
        tick_outer = 26
        p1 = (reticle_cx + cos_a * tick_inner, reticle_cy + sin_a * tick_inner)
        p2 = (reticle_cx + cos_a * tick_outer, reticle_cy + sin_a * tick_outer)
        draw.line([p1, p2], fill=accent_color, width=2)

        # Opposite tick
        p3 = (reticle_cx - cos_a * tick_inner, reticle_cy - sin_a * tick_inner)
        p4 = (reticle_cx - cos_a * tick_outer, reticle_cy - sin_a * tick_outer)
        draw.line([p3, p4], fill=accent_color, width=2)

        # Center dot
        draw.ellipse([reticle_cx - 3, reticle_cy - 3, reticle_cx + 3, reticle_cy + 3], fill=accent_color)

        # ── 3. Technical Telemetry Labels ─────────────────────────────────
        font_hud = load_sub_font(20)
        hud_text_left = f"ISO_CAD // CAM_0{scene_idx + 1}"
        draw.text((corner_pad + 12, corner_pad + 8), hud_text_left, font=font_hud, fill=(*accent_color, 200))

        progress_pct = int((t / max(0.1, total_duration)) * 100)
        hud_text_right = f"T+{t:.1f}s // {progress_pct}%"
        rb = draw.textbbox((0, 0), hud_text_right, font=font_hud)
        rw = rb[2] - rb[0]
        draw.text((width - corner_pad - rw - 80, corner_pad + 8), hud_text_right, font=font_hud, fill=(200, 220, 240, 180))
