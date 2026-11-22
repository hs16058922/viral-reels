"""
Multi-Format Dynamic Video Engine for CurioMotion Reels.

Guarantees visual uniqueness across reels by rotating distinct visual layouts:
1. FORMAT_ISOMETRIC: 3D perspective grid, extruded podium, floating cutaway, upper-third typography
2. FORMAT_FULLSCREEN: Edge-to-edge cinematic macro camera drift, Vox-style bold typography, letterbox mattes
3. FORMAT_SPLIT_CAD: Top 3D cutaway viewport + bottom live oscilloscope telemetry dashboard
4. FORMAT_DARK_LAB: Stealth obsidian carbon fiber lab, dual measurement columns, neon rim lighting
"""

import math
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from engine.caption_styles import CaptionTheme
from engine.fonts import load_headline_font, load_sub_font
from engine.hud_graphics import HUDGraphicsEngine
from engine.isometric_animator import IsometricMotionEngine

WIDTH, HEIGHT = 1080, 1920


class ReelVideoFormat(str, Enum):
    ISOMETRIC_STAGE = "ISOMETRIC_STAGE"
    CINEMATIC_FULLSCREEN = "CINEMATIC_FULLSCREEN"
    SPLIT_DIAGNOSTIC = "SPLIT_DIAGNOSTIC"
    DARK_CARBON_LAB = "DARK_CARBON_LAB"


class VideoFormatRotator:
    """Selects and cycles distinct video presentation formats per topic."""

    FORMAT_CYCLE = [
        ReelVideoFormat.ISOMETRIC_STAGE,
        ReelVideoFormat.CINEMATIC_FULLSCREEN,
        ReelVideoFormat.SPLIT_DIAGNOSTIC,
        ReelVideoFormat.DARK_CARBON_LAB,
    ]

    @classmethod
    def get_format_for_topic(cls, topic: Dict[str, Any]) -> ReelVideoFormat:
        """Deterministically assign a unique format to each topic."""
        # Check explicit override
        if "video_format" in topic and topic["video_format"]:
            fmt_str = topic["video_format"].upper()
            for f in ReelVideoFormat:
                if f.value == fmt_str:
                    return f

        # Deterministic rotation by topic ID hash
        t_id = topic.get("id", "")
        idx = abs(hash(t_id)) % len(cls.FORMAT_CYCLE)
        return cls.FORMAT_CYCLE[idx]


class FormatCompositor:
    """Renders individual frames based on the active topic's format."""

    @classmethod
    def render_format_frame(
        cls,
        video_format: ReelVideoFormat,
        t: float,
        total_duration: float,
        scene_idx: int,
        scene_t: float,
        scene_duration: float,
        raw_scene_img: Image.Image,
        framed_scene_img: Image.Image,
        theme: CaptionTheme,
        accent_color: Tuple[int, int, int],
        bullets: List[str],
        active_words: Optional[List[str]],
        active_word_idx: int,
    ) -> Image.Image:
        """Dispatch to format-specific multi-layer renderer."""
        if video_format == ReelVideoFormat.CINEMATIC_FULLSCREEN:
            return cls._render_fullscreen_cinematic(
                t=t,
                total_duration=total_duration,
                scene_idx=scene_idx,
                scene_t=scene_t,
                scene_duration=scene_duration,
                raw_scene=raw_scene_img,
                theme=theme,
                accent_color=accent_color,
                bullets=bullets,
                words=active_words,
                active_idx=active_word_idx,
            )
        elif video_format == ReelVideoFormat.SPLIT_DIAGNOSTIC:
            return cls._render_split_diagnostic(
                t=t,
                total_duration=total_duration,
                scene_idx=scene_idx,
                scene_t=scene_t,
                scene_duration=scene_duration,
                raw_scene=raw_scene_img,
                theme=theme,
                accent_color=accent_color,
                bullets=bullets,
                words=active_words,
                active_idx=active_word_idx,
            )
        elif video_format == ReelVideoFormat.DARK_CARBON_LAB:
            return cls._render_dark_carbon_lab(
                t=t,
                total_duration=total_duration,
                scene_idx=scene_idx,
                framed_scene=framed_scene_img,
                theme=theme,
                accent_color=accent_color,
                bullets=bullets,
                words=active_words,
                active_idx=active_word_idx,
            )
        else:  # ISOMETRIC_STAGE (Default)
            return cls._render_isometric_stage(
                t=t,
                total_duration=total_duration,
                scene_idx=scene_idx,
                framed_scene=framed_scene_img,
                theme=theme,
                accent_color=accent_color,
                bullets=bullets,
                words=active_words,
                active_idx=active_word_idx,
            )

    # ── Format 1: 3D Isometric Stage ──────────────────────────────────

    @classmethod
    def _render_isometric_stage(
        cls,
        t: float,
        total_duration: float,
        scene_idx: int,
        framed_scene: Image.Image,
        theme: CaptionTheme,
        accent_color: Tuple[int, int, int],
        bullets: List[str],
        words: Optional[List[str]],
        active_idx: int,
    ) -> Image.Image:
        bg = IsometricMotionEngine.render_blueprint_background(
            width=WIDTH,
            height=HEIGHT,
            t=t,
            theme_name="OBSIDIAN" if theme.name == "MATRIX_HUD" else ("CRIMSON" if theme.name == "CRIMSON_PULSE" else "BLUEPRINT"),
        )
        d_bg = ImageDraw.Draw(bg)

        IsometricMotionEngine.draw_isometric_podium(
            d_bg,
            cx=WIDTH // 2,
            cy=1440,
            radius_x=440,
            radius_y=220,
            height_extrude=54,
            t=t,
            accent_color=accent_color,
        )

        IsometricMotionEngine.render_energy_stream(
            d_bg,
            t=t,
            accent_color=(255, 90, 31) if theme.name != "CRIMSON_PULSE" else (0, 229, 255),
        )

        IsometricMotionEngine.composite_floating_subject(
            canvas=bg,
            framed_subject=framed_scene,
            cx=WIDTH // 2,
            base_cy=1020,
            t=t,
            float_amp=16.0,
            float_freq=2.4,
        )

        IsometricMotionEngine.render_floating_callouts(
            img=bg,
            t=t,
            bullets=bullets,
            scene_idx=scene_idx,
            accent_color=accent_color,
        )

        HUDGraphicsEngine.draw_hud_overlay(
            img=bg,
            t=t,
            total_duration=total_duration,
            scene_idx=scene_idx,
            accent_color=accent_color,
        )

        if words:
            IsometricMotionEngine.render_upper_third_captions(
                img=bg,
                words=words,
                active_idx=active_idx,
                theme=theme,
                center_y=360,
            )

        return bg

    # ── Format 2: Cinematic Fullscreen Macro ──────────────────────────

    @classmethod
    def _render_fullscreen_cinematic(
        cls,
        t: float,
        total_duration: float,
        scene_idx: int,
        scene_t: float,
        scene_duration: float,
        raw_scene: Image.Image,
        theme: CaptionTheme,
        accent_color: Tuple[int, int, int],
        bullets: List[str],
        words: Optional[List[str]],
        active_idx: int,
    ) -> Image.Image:
        """Edge-to-edge cinematic frame with dynamic continuous Ken Burns drift and Vox typography."""
        bw, bh = raw_scene.size
        progress = min(1.0, max(0.0, scene_t / max(0.1, scene_duration)))

        # Dynamic zoom & pan
        zoom = 1.05 + 0.12 * math.sin(progress * math.pi)
        pan_y = 0.04 * math.sin(progress * math.pi)

        cw, ch = int(WIDTH / zoom), int(HEIGHT / zoom)
        cx = int((bw - cw) // 2)
        cy = int((bh - ch) // 2 + pan_y * bh)
        cx = max(0, min(bw - cw, cx))
        cy = max(0, min(bh - ch, cy))

        cropped = raw_scene.crop((cx, cy, cx + cw, cy + ch)).resize((WIDTH, HEIGHT), Image.Resampling.BILINEAR).convert("RGBA")
        draw = ImageDraw.Draw(cropped)

        # 1. Subtle Cinematic Letterbox Top & Bottom Mattes (Sleek dark gradient vignette)
        for y in range(0, 180, 4):
            alpha = int(220 * (1.0 - y / 180))
            draw.rectangle([0, y, WIDTH, y + 4], fill=(0, 0, 0, alpha))
        for y in range(HEIGHT - 220, HEIGHT, 4):
            alpha = int(240 * ((y - (HEIGHT - 220)) / 220))
            draw.rectangle([0, y, WIDTH, y + 4], fill=(0, 0, 0, alpha))

        # 2. Modern Floating Viewfinder HUD
        HUDGraphicsEngine.draw_hud_overlay(
            img=cropped,
            t=t,
            total_duration=total_duration,
            scene_idx=scene_idx,
            accent_color=accent_color,
        )

        # 3. Floating Micro Tag Card in lower-third
        if bullets:
            b_text = bullets[scene_idx % len(bullets)].upper()[:28]
            font_sub = load_sub_font(20)
            tag_w, tag_h = 440, 56
            tag_x = (WIDTH - tag_w) // 2
            tag_y = 1260
            draw.rounded_rectangle([tag_x, tag_y, tag_x + tag_w, tag_y + tag_h], radius=16, fill=(10, 14, 22, 220), outline=accent_color, width=2)
            tb = draw.textbbox((0, 0), b_text, font=font_sub)
            tw = tb[2] - tb[0]
            draw.text((tag_x + (tag_w - tw) // 2, tag_y + 16), b_text, font=font_sub, fill=(255, 255, 255))

        # 4. Centered Vox-Style Bold Captions with Heavy 3D Drop Shadow
        if words:
            IsometricMotionEngine.render_upper_third_captions(
                img=cropped,
                words=words,
                active_idx=active_idx,
                theme=theme,
                center_y=380,
            )

        return cropped

    # ── Format 3: Split Diagnostic (CAD Telemetry Dashboard) ──────────

    @classmethod
    def _render_split_diagnostic(
        cls,
        t: float,
        total_duration: float,
        scene_idx: int,
        scene_t: float,
        scene_duration: float,
        raw_scene: Image.Image,
        theme: CaptionTheme,
        accent_color: Tuple[int, int, int],
        bullets: List[str],
        words: Optional[List[str]],
        active_idx: int,
    ) -> Image.Image:
        """Top 58% 3D cutaway + Bottom 42% live oscilloscope telemetry dashboard."""
        frame = Image.new("RGBA", (WIDTH, HEIGHT), (8, 12, 20, 255))

        # 1. Top Viewport: 3D Scene (y: 0 to 1100)
        top_h = 1100
        bw, bh = raw_scene.size
        crop_h = int(bh * 0.62)
        top_crop = raw_scene.crop((0, 0, bw, crop_h)).resize((WIDTH, top_h), Image.Resampling.LANCZOS)
        frame.paste(top_crop, (0, 0))

        draw = ImageDraw.Draw(frame)

        # 2. Middle Divider: Glowing Status Bar
        draw.rectangle([0, top_h - 4, WIDTH, top_h + 4], fill=accent_color)
        font_div = load_sub_font(20)
        div_text = f"REALTIME_TELEMETRY // SENSOR_ARRAY_0{scene_idx + 1}"
        draw.text((40, top_h - 38), div_text, font=font_div, fill=(255, 255, 255))

        # 3. Bottom Dashboard (y: 1100 to 1920)
        # Background dark carbon
        draw.rectangle([0, top_h + 4, WIDTH, HEIGHT], fill=(10, 15, 26, 255))

        # Animated Oscilloscope Waveform
        wave_cy = 1320
        wave_points = []
        for gx in range(60, WIDTH - 60, 8):
            rad = gx * 0.024 + t * 6.0
            gy = int(wave_cy + math.sin(rad) * 42.0 * math.cos(t * 1.5))
            wave_points.append((gx, gy))

        # Draw grid lines in waveform box
        draw.rectangle([60, 1240, WIDTH - 60, 1400], fill=(14, 22, 38, 220), outline=(*accent_color, 120), width=1)
        for gy in range(1260, 1400, 35):
            draw.line([(60, gy), (WIDTH - 60, gy)], fill=(*accent_color, 45), width=1)

        # Draw the live green/cyan sine wave
        if len(wave_points) > 1:
            draw.line(wave_points, fill=accent_color, width=3)

        # Telemetry Text Labels
        font_data = load_sub_font(22)
        draw.text((80, 1250), "OSCILLATION // HARMONICS", font=font_data, fill=(*accent_color, 240))
        freq_val = f"FREQ: {1400 + int(math.sin(t * 4) * 80)} RPM"
        draw.text((WIDTH - 300, 1250), freq_val, font=font_data, fill=(255, 255, 255))

        # Active Specification Pill
        if bullets:
            b_text = bullets[scene_idx % len(bullets)].upper()
            draw.rounded_rectangle([60, 1430, WIDTH - 60, 1530], radius=18, fill=(18, 28, 48, 240), outline=accent_color, width=2)
            draw.text((90, 1450), b_text[:34], font=font_data, fill=(255, 255, 255))
            draw.text((90, 1484), "DYNAMIC INERTIAL ABSORPTION ACTIVE", font=load_sub_font(18), fill=(*accent_color, 210))

        # Upper-Third Captions (Placed in top viewport over 3D cutaway)
        if words:
            IsometricMotionEngine.render_upper_third_captions(
                img=frame,
                words=words,
                active_idx=active_idx,
                theme=theme,
                center_y=320,
            )

        # Corner HUD
        HUDGraphicsEngine.draw_hud_overlay(
            img=frame,
            t=t,
            total_duration=total_duration,
            scene_idx=scene_idx,
            accent_color=accent_color,
        )

        return frame

    # ── Format 4: Dark Carbon Stealth Lab ──────────────────────────────

    @classmethod
    def _render_dark_carbon_lab(
        cls,
        t: float,
        total_duration: float,
        scene_idx: int,
        framed_scene: Image.Image,
        theme: CaptionTheme,
        accent_color: Tuple[int, int, int],
        bullets: List[str],
        words: Optional[List[str]],
        active_idx: int,
    ) -> Image.Image:
        """Stealth obsidian lab with dual measurement columns and neon rim lighting."""
        frame = Image.new("RGBA", (WIDTH, HEIGHT), (6, 9, 14, 255))
        draw = ImageDraw.Draw(frame)

        # Diagonal carbon texture lines
        for y in range(-WIDTH, HEIGHT + WIDTH, 60):
            draw.line([(0, y), (WIDTH, y + WIDTH)], fill=(16, 24, 38, 55), width=1)

        # Dual Measurement Columns on Left and Right borders
        col_w = 48
        # Left column
        draw.line([(col_w, 200), (col_w, HEIGHT - 200)], fill=(*accent_color, 120), width=2)
        for my in range(200, HEIGHT - 200, 40):
            tick_len = 16 if (my % 120 == 0) else 8
            draw.line([(col_w - tick_len, my), (col_w, my)], fill=(*accent_color, 160), width=1)

        # Right column
        draw.line([(WIDTH - col_w, 200), (WIDTH - col_w, HEIGHT - 200)], fill=(*accent_color, 120), width=2)
        for my in range(200, HEIGHT - 200, 40):
            tick_len = 16 if (my % 120 == 0) else 8
            draw.line([(WIDTH - col_w, my), (WIDTH - col_w + tick_len, my)], fill=(*accent_color, 160), width=1)

        # Floating 3D Subject Cutaway
        IsometricMotionEngine.composite_floating_subject(
            canvas=frame,
            framed_subject=framed_scene,
            cx=WIDTH // 2,
            base_cy=1000,
            t=t,
            float_amp=14.0,
            float_freq=2.2,
        )

        # Floating Callout Cards with Laser Pointers
        IsometricMotionEngine.render_floating_callouts(
            img=frame,
            t=t,
            bullets=bullets,
            scene_idx=scene_idx,
            accent_color=accent_color,
        )

        # HUD Viewfinder
        HUDGraphicsEngine.draw_hud_overlay(
            img=frame,
            t=t,
            total_duration=total_duration,
            scene_idx=scene_idx,
            accent_color=accent_color,
        )

        # Upper-Third Captions
        if words:
            IsometricMotionEngine.render_upper_third_captions(
                img=frame,
                words=words,
                active_idx=active_idx,
                theme=theme,
                center_y=360,
            )

        return frame
