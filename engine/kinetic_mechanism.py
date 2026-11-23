"""
Kinetic 3D Mechanism & Exploded-View Rendering Engine for Viral Reels.

Provides dynamic, cinematic 3D motion for technical/engineering explainers:
- Exploded-view kinetic disassembly: Outer casing slides away on isometric vectors
  to reveal internal mechanics (voice coils, magnets, DSP chips, micro-valves).
- Acoustic diaphragm / piston micro-vibration: High-frequency mechanical oscillation.
- Dynamic soundwave phase cancellation: Ambient noise waves colliding with anti-phase
  waves and flatlining into zero-amplitude green silence.
- Animated holographic laser calipers & dimension readouts ([ 40mm CORE ] <--- 18.2mm --->).
- Perspective-rotated 3D wireframe gears & calibration gyro rings.
- Sweeping CAD X-Ray inspection laser beam.
"""

import math
from typing import List, Optional, Tuple
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from engine.fonts import load_headline_font, load_sub_font

WIDTH, HEIGHT = 1080, 1920


class KineticMechanismRenderer:
    """Renders moving mechanical assemblies, exploded views, and physical simulations."""

    @classmethod
    def render_kinetic_exploded_cutaway(
        cls,
        base_scene: Image.Image,
        t: float,
        scene_progress: float,
        width: int = WIDTH,
        height: int = 1100,
        accent_color: Tuple[int, int, int] = (0, 240, 255),
        show_phase_cancellation: bool = True,
    ) -> Image.Image:
        """
        Renders an active mechanical cutaway where:
        1. Outer casing layer dynamically slides along the 3D isometric vector.
        2. Internal core diaphragm vibrates with acoustic energy.
        3. Laser calipers measure exploded distance in real time.
        4. Holographic X-Ray laser sweeps across the mechanism.
        5. Soundwave collision & phase cancellation are rendered live.
        """
        bw, bh = base_scene.size
        # Fit base scene into viewport
        crop_h = int(bh * (height / HEIGHT) * 1.05)
        crop_h = min(bh, max(100, crop_h))
        viewport = base_scene.crop((0, 0, bw, crop_h)).resize((width, height), Image.Resampling.LANCZOS).convert("RGBA")

        # ── 1. Acoustic / Mechanical Core Micro-Vibration ─────────────
        # The internal speaker diaphragm/core physically pulses with sound
        vib_offset = int(math.sin(t * 32.0) * (3.5 + 2.0 * math.sin(t * 4.0)))
        if abs(vib_offset) > 1:
            # Shift the inner region slightly to create high-frequency kinetic vibration
            core_box = (int(width * 0.35), int(height * 0.30), int(width * 0.75), int(height * 0.75))
            core_crop = viewport.crop(core_box)
            viewport.paste(core_crop, (core_box[0] + vib_offset, core_box[1] + vib_offset // 2))

        # ── 2. Exploded-View Dynamic Separation ───────────────────────
        # An isometric casing element smoothly slides away to expose the core
        # Explosion eases out in first 40% of scene, holds, then pulses
        ease_p = min(1.0, scene_progress / 0.35)
        # Smooth cubic ease-out
        slide_factor = 1.0 - math.pow(1.0 - ease_p, 3.0)
        # Subtle harmonic breathing once fully opened
        if scene_progress >= 0.35:
            slide_factor += 0.05 * math.sin(t * 2.5)

        max_explode_dx = 55.0
        max_explode_dy = -32.0
        cur_dx = int(slide_factor * max_explode_dx)
        cur_dy = int(slide_factor * max_explode_dy)

        # Draw kinetic overlay layers
        overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        # ── 3. Rotating Gyroscopic Calibration Dial ───────────────────
        # Centered around the speaker driver core (x: ~640, y: ~750)
        gear_cx = int(width * 0.62)
        gear_cy = int(height * 0.72)
        gear_rad = 120
        cls.draw_rotating_gyro_ring(
            draw=draw,
            cx=gear_cx,
            cy=gear_cy,
            radius=gear_rad,
            t=t,
            accent_color=accent_color,
        )

        # ── 4. Laser Calipers & Animated Dimension Lines ──────────────
        if slide_factor > 0.15:
            # Line connecting outer shell to inner driver core
            p_core = (gear_cx - 30, gear_cy - 10)
            p_shell = (p_core[0] - 120 - cur_dx, p_core[1] - 40 + cur_dy)

            # Laser dimension line
            draw.line([p_core, p_shell], fill=(*accent_color, 220), width=2)
            # Arrow ticks
            draw.ellipse([p_core[0] - 5, p_core[1] - 5, p_core[0] + 5, p_core[1] + 5], fill=accent_color)
            draw.ellipse([p_shell[0] - 5, p_shell[1] - 5, p_shell[0] + 5, p_shell[1] + 5], fill=(255, 255, 255))

            # Dynamic millimeter readout
            mm_dist = 14.0 + slide_factor * 16.5
            font_dim = load_sub_font(18)
            dim_text = f"< {mm_dist:.1f}mm GAP >"
            mid_x = (p_core[0] + p_shell[0]) // 2 - 60
            mid_y = (p_core[1] + p_shell[1]) // 2 - 24
            draw.text((mid_x, mid_y), dim_text, font=font_dim, fill=(*accent_color, 240))

        # ── 5. Real-Time Phase Cancellation Wave Simulation ───────────
        if show_phase_cancellation:
            cls.draw_phase_cancellation_wave(
                draw=draw,
                x_start=60,
                x_end=width - 60,
                y_center=int(height * 0.84),
                t=t,
                accent_color=accent_color,
            )

        # ── 6. Sweeping Holographic X-Ray Laser Inspection Beam ───────
        scan_progress = (t * 0.35) % 1.0
        # Laser moves left to right across cutaway
        scan_x = int(width * 0.12 + (width * 0.76) * (0.5 - 0.5 * math.cos(scan_progress * 2 * math.pi)))
        
        # Subtle glowing vertical laser line
        for glow_w in [12, 6, 2]:
            alpha = 40 if glow_w == 12 else (110 if glow_w == 6 else 230)
            draw.line(
                [(scan_x, int(height * 0.18)), (scan_x, int(height * 0.88))],
                fill=(*accent_color, alpha),
                width=glow_w,
            )
        # Laser head indicator
        draw.polygon(
            [(scan_x - 6, int(height * 0.18)), (scan_x + 6, int(height * 0.18)), (scan_x, int(height * 0.18) + 12)],
            fill=(255, 255, 255, 240),
        )
        draw.text(
            (scan_x + 10, int(height * 0.19)),
            "X-RAY CAD INSPECTION",
            font=load_sub_font(16),
            fill=(*accent_color, 210),
        )

        # Composite overlay
        return Image.alpha_composite(viewport, overlay)

    @classmethod
    def draw_rotating_gyro_ring(
        cls,
        draw: ImageDraw.ImageDraw,
        cx: int,
        cy: int,
        radius: int,
        t: float,
        accent_color: Tuple[int, int, int] = (0, 240, 255),
    ) -> None:
        """Draws a perspective-rotated 3D wireframe calibration ring orbiting the core."""
        # 3D tilt perspective (isometric compression)
        aspect_y = 0.48
        angle_rad = t * 2.2  # Rotation speed

        # Outer dashed elliptical ring
        num_ticks = 24
        for i in range(num_ticks):
            theta = angle_rad + (i / num_ticks) * 2 * math.pi
            px = int(cx + math.cos(theta) * radius)
            py = int(cy + math.sin(theta) * radius * aspect_y)

            # Draw tick
            tick_len = 6 if (i % 6 == 0) else 3
            nx = math.cos(theta)
            ny = math.sin(theta) * aspect_y
            tx = int(px + nx * tick_len)
            ty = int(py + ny * tick_len)

            alpha = 240 if (i % 6 == 0) else 120
            draw.line([(px, py), (tx, ty)], fill=(*accent_color, alpha), width=2 if (i % 6 == 0) else 1)

        # Center target reticle
        reticle_r = 14
        draw.ellipse([cx - reticle_r, cy - int(reticle_r * aspect_y), cx + reticle_r, cy + int(reticle_r * aspect_y)], outline=(255, 255, 255, 200), width=1)
        draw.line([(cx - 20, cy), (cx + 20, cy)], fill=(*accent_color, 200), width=1)
        draw.line([(cx, cy - 10), (cx, cy + 10)], fill=(*accent_color, 200), width=1)

    @classmethod
    def draw_phase_cancellation_wave(
        cls,
        draw: ImageDraw.ImageDraw,
        x_start: int,
        x_end: int,
        y_center: int,
        t: float,
        accent_color: Tuple[int, int, int] = (0, 240, 255),
    ) -> None:
        """
        Simulates the physical acoustic mechanism:
        - Left: Red noisy ambient soundwave (incoming).
        - Center: DSP speaker fires inverted Cyan anti-noise wave.
        - Collision zone: Waves collide and cancel out into a Neon Green flatline (0 dB Silence).
        """
        total_w = x_end - x_start
        collision_x = x_start + int(total_w * 0.52)

        # Wave 1: Incoming Noise (Red / Amber) from Left (x_start to collision_x)
        noise_points = []
        for gx in range(x_start, collision_x + 4, 6):
            phase = (gx * 0.045) - t * 8.0
            amp = 26.0 * (1.0 - (gx - x_start) / max(1, (collision_x - x_start)) * 0.3)
            # Add harmonic turbulence for noisy ambient sound
            gy = int(y_center + math.sin(phase) * amp + math.sin(phase * 2.3) * (amp * 0.3))
            noise_points.append((gx, gy))

        # Wave 2: Inverted Anti-Noise (Cyan) emitted from Speaker (collision_x to collision_x - 120)
        anti_points = []
        for gx in range(collision_x - 140, collision_x + 4, 6):
            phase = (gx * 0.045) - t * 8.0 + math.pi  # 180° inverted phase!
            amp = 24.0 * ((gx - (collision_x - 140)) / 140.0)
            gy = int(y_center + math.sin(phase) * amp)
            anti_points.append((gx, gy))

        # Wave 3: Neutralized Flatline (Neon Green) resulting from Destructive Interference
        flatline_points = []
        for gx in range(collision_x, x_end, 6):
            # Flat with micro residual fluctuation
            residual = math.sin((gx * 0.02) - t * 10.0) * 1.5
            flatline_points.append((gx, int(y_center + residual)))

        # Draw semi-transparent background monitor strip
        strip_h = 76
        draw.rounded_rectangle(
            [x_start, y_center - strip_h // 2, x_end, y_center + strip_h // 2],
            radius=12,
            fill=(6, 10, 18, 220),
            outline=(40, 60, 90, 140),
            width=1,
        )

        # Zero-axis centerline
        draw.line([(x_start + 8, y_center), (x_end - 8, y_center)], fill=(50, 70, 100, 110), width=1)

        # Draw incoming noise wave (Red)
        if len(noise_points) > 1:
            draw.line(noise_points, fill=(255, 60, 60, 240), width=3)

        # Draw anti-noise wave (Electric Cyan)
        if len(anti_points) > 1:
            draw.line(anti_points, fill=(0, 240, 255, 240), width=3)

        # Draw collision burst spark at collision_x
        spark_r = int(7 + 3 * math.sin(t * 24.0))
        draw.ellipse(
            [collision_x - spark_r, y_center - spark_r, collision_x + spark_r, y_center + spark_r],
            fill=(255, 255, 255, 240),
            outline=(*accent_color, 255),
            width=2,
        )

        # Draw resulting green silence line (0 dB)
        if len(flatline_points) > 1:
            draw.line(flatline_points, fill=(0, 255, 120, 255), width=4)

        # Status indicators
        font_lbl = load_sub_font(15)
        draw.text((x_start + 16, y_center - 32), "[ 85dB AMBIENT NOISE ]", font=font_lbl, fill=(255, 80, 80, 230))
        draw.text((collision_x + 18, y_center - 32), "[ ZERO SOUND // 0.0 dB ]", font=font_lbl, fill=(0, 255, 120, 240))
