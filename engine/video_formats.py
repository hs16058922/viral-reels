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
from engine.kinetic_mechanism import KineticMechanismRenderer

WIDTH, HEIGHT = 1080, 1920


class ReelVideoFormat(str, Enum):
    ISOMETRIC_STAGE = "ISOMETRIC_STAGE"
    CINEMATIC_FULLSCREEN = "CINEMATIC_FULLSCREEN"
    SPLIT_DIAGNOSTIC = "SPLIT_DIAGNOSTIC"
    DARK_CARBON_LAB = "DARK_CARBON_LAB"
    GEMINI_VEO = "GEMINI_VEO"


class VideoFormatRotator:
    """Selects and cycles distinct video presentation formats per topic."""

    FORMAT_CYCLE = [
        ReelVideoFormat.CINEMATIC_FULLSCREEN,
        ReelVideoFormat.ISOMETRIC_STAGE,
        ReelVideoFormat.CINEMATIC_FULLSCREEN,
        ReelVideoFormat.DARK_CARBON_LAB,
    ]

    @classmethod
    def get_format_for_topic(cls, topic: Dict[str, Any]) -> ReelVideoFormat:
        """Always return CINEMATIC_FULLSCREEN for immersive, edge-to-edge 3D visuals."""
        return ReelVideoFormat.CINEMATIC_FULLSCREEN


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
        blender_frame: Optional[Image.Image] = None,
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
                blender_frame=blender_frame,
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
                blender_frame=blender_frame,
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
                blender_frame=blender_frame,
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
                blender_frame=blender_frame,
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
        blender_frame: Optional[Image.Image] = None,
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

        subject_cy = int(1020 + math.sin(t * 2.4) * 16.0)
        if blender_frame:
            # Composite true 3D Blender mechanism directly above the podium
            bx = (WIDTH - blender_frame.width) // 2
            by = int(520 + math.sin(t * 2.4) * 16.0)
            bg.paste(blender_frame, (bx, by), blender_frame)
        else:
            IsometricMotionEngine.composite_floating_subject(
                canvas=bg,
                framed_subject=framed_scene,
                cx=WIDTH // 2,
                base_cy=1020,
                t=t,
                float_amp=16.0,
                float_freq=2.4,
            )

        # 3D Gyroscopic calibration ring rotating around the floating subject
        d_kinetic = ImageDraw.Draw(bg)
        KineticMechanismRenderer.draw_rotating_gyro_ring(
            draw=d_kinetic,
            cx=WIDTH // 2,
            cy=subject_cy,
            radius=380,
            t=t,
            accent_color=accent_color,
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
        blender_frame: Optional[Image.Image] = None,
    ) -> Image.Image:
        """Edge-to-edge cinematic frame with dynamic continuous Ken Burns drift and Vox typography."""
        bw, bh = raw_scene.size
        progress = min(1.0, max(0.0, scene_t / max(0.1, scene_duration)))

        # Dynamic zoom & pan
        zoom = 1.05 + 0.12 * math.sin(progress * math.pi)
        pan_y = 0.04 * math.sin(progress * math.pi)

        # Scale raw_scene to fully cover 1080x1920 without any black side margins
        cov_scale = max(WIDTH / bw, HEIGHT / bh) * zoom
        sw, sh = int(bw * cov_scale), int(bh * cov_scale)
        scaled_scene = raw_scene.resize((sw, sh), Image.Resampling.BILINEAR)

        cx = max(0, min(sw - WIDTH, (sw - WIDTH) // 2))
        cy = max(0, min(sh - HEIGHT, int((sh - HEIGHT) // 2 + pan_y * sh)))

        cropped = scaled_scene.crop((cx, cy, cx + WIDTH, cy + HEIGHT)).convert("RGBA")
        draw = ImageDraw.Draw(cropped)

        # 1. Subtle Cinematic Letterbox Top & Bottom Mattes (Sleek dark gradient vignette)
        for y in range(0, 180, 4):
            alpha = int(220 * (1.0 - y / 180))
            draw.rectangle([0, y, WIDTH, y + 4], fill=(0, 0, 0, alpha))
        for y in range(HEIGHT - 220, HEIGHT, 4):
            alpha = int(240 * ((y - (HEIGHT - 220)) / 220))
            draw.rectangle([0, y, WIDTH, y + 4], fill=(0, 0, 0, alpha))

        # 2. Remotion-Inspired HTML/CSS Motion Graphics (Callouts, Visualizer, Telemetry)
        from engine.remotion_elements import RemotionHTMLElements
        RemotionHTMLElements.draw_all_overlays(
            img=cropped,
            t=t,
            scene_t=scene_t,
            scene_duration=scene_duration,
            scene_idx=scene_idx,
            total_scenes=max(1, len(bullets) if bullets else 4),
            total_duration=total_duration,
            topic={"bullets": bullets},
            accent_color=accent_color,
        )

        # 3. Modern Floating Viewfinder HUD (Minimal top progress bar and timestamp)
        HUDGraphicsEngine.draw_hud_overlay(
            img=cropped,
            t=t,
            total_duration=total_duration,
            scene_idx=scene_idx,
            accent_color=accent_color,
        )

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
        blender_frame: Optional[Image.Image] = None,
    ) -> Image.Image:
        """Top 58% 3D cutaway + Bottom 42% live oscilloscope telemetry dashboard."""
        frame = Image.new("RGBA", (WIDTH, HEIGHT), (8, 12, 20, 255))

        # 1. Top Viewport: Kinetic 3D Scene with Active Mechanisms (y: 0 to 1100)
        top_h = 1100
        scene_progress = min(1.0, max(0.0, scene_t / max(0.1, scene_duration)))
        kinetic_top = KineticMechanismRenderer.render_kinetic_exploded_cutaway(
            base_scene=raw_scene,
            t=t,
            scene_progress=scene_progress,
            width=WIDTH,
            height=top_h,
            accent_color=accent_color,
            show_phase_cancellation=True,
        )
        frame.paste(kinetic_top, (0, 0))

        # Overlay 3D Blender mechanism in top viewport if available
        if blender_frame:
            bw = int(blender_frame.width * 0.85)
            bh = int(blender_frame.height * 0.85)
            scaled_b = blender_frame.resize((bw, bh), Image.Resampling.LANCZOS)
            bx = (WIDTH - bw) // 2
            by = int(140 + math.sin(t * 2.2) * 10.0)
            frame.paste(scaled_b, (bx, by), scaled_b)

        draw = ImageDraw.Draw(frame)

        # 2. Middle Divider: Clean Dark Separation Line (No harsh colored bar)
        draw.line([(0, top_h), (WIDTH, top_h)], fill=(40, 50, 70, 180), width=2)
        font_div = load_sub_font(20)
        div_text = f"REALTIME_TELEMETRY // SENSOR_ARRAY_0{scene_idx + 1}"
        draw.text((40, top_h - 38), div_text, font=font_div, fill=(255, 255, 255, 220))

        # 3. Bottom Dashboard (y: 1100 to 1920)
        # Background dark carbon
        draw.rectangle([0, top_h + 2, WIDTH, HEIGHT], fill=(10, 15, 26, 255))

        # Animated Oscilloscope Waveform
        wave_cy = 1320
        wave_points = []
        for gx in range(60, WIDTH - 60, 8):
            rad = gx * 0.024 + t * 6.0
            gy = int(wave_cy + math.sin(rad) * 42.0 * math.cos(t * 1.5))
            wave_points.append((gx, gy))

        # Draw grid lines in waveform box
        draw.rectangle([60, 1240, WIDTH - 60, 1400], fill=(14, 22, 38, 220), outline=(255, 255, 255, 40), width=1)
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
            if len(b_text) > 42:
                # Wrap cleanly at word boundary
                words_list = b_text.split()
                line1_words, line2_words = [], []
                cur_len = 0
                for w in words_list:
                    if cur_len + len(w) + 1 <= 38 and not line2_words:
                        line1_words.append(w)
                        cur_len += len(w) + 1
                    else:
                        line2_words.append(w)
                line1 = " ".join(line1_words)
                line2 = " ".join(line2_words)[:42]
                draw.rounded_rectangle([60, 1430, WIDTH - 60, 1540], radius=18, fill=(18, 28, 48, 240), outline=(255, 255, 255, 40), width=1)
                draw.text((90, 1446), line1, font=font_data, fill=(255, 255, 255))
                draw.text((90, 1476), line2, font=font_data, fill=(255, 255, 255))
                draw.text((90, 1506), "DYNAMIC CAD TELEMETRY ACTIVE", font=load_sub_font(16), fill=(*accent_color, 210))
            else:
                draw.rounded_rectangle([60, 1430, WIDTH - 60, 1530], radius=18, fill=(18, 28, 48, 240), outline=(255, 255, 255, 40), width=1)
                draw.text((90, 1450), b_text, font=font_data, fill=(255, 255, 255))
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
        blender_frame: Optional[Image.Image] = None,
    ) -> Image.Image:
        """Stealth obsidian lab with dual measurement columns and neon rim lighting."""
        frame = Image.new("RGBA", (WIDTH, HEIGHT), (6, 9, 14, 255))
        draw = ImageDraw.Draw(frame)

        # Diagonal carbon texture lines
        for y in range(-WIDTH, HEIGHT + WIDTH, 60):
            draw.line([(0, y), (WIDTH, y + WIDTH)], fill=(16, 24, 38, 55), width=1)

        # Clean obsidian carbon background (No harsh outer border frames)
        # Floating 3D Subject Cutaway
        if blender_frame:
            bx = (WIDTH - blender_frame.width) // 2
            by = int(500 + math.sin(t * 2.2) * 14.0)
            frame.paste(blender_frame, (bx, by), blender_frame)
        else:
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
