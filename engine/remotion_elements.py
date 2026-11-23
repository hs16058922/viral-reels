"""
Remotion-Inspired Modern HTML/CSS Motion Graphics & UI Overlay Engine.

Generates high-retention, tech-documentary visual UI elements over interactive scene imagery:
1. Interactive Technical Callout Pointers: Pulsing SVG-style target reticle, elbow leader lines, and frosted glass spec badges
2. Dynamic Telemetry Metric Widgets: Live animated digital gauges (T+ timer, tolerance, velocity, RPM)
3. Audio Waveform Visualizer: Animated frequency bars reacting to voiceover rhythm
4. Glassmorphism Status Pills: Frosted dark cards with glowing borders and status dots
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple
from PIL import Image, ImageDraw, ImageFont

from engine.fonts import load_headline_font, load_sub_font

WIDTH, HEIGHT = 1080, 1920


class RemotionHTMLElements:
    """Renders modern Remotion / HTML-style UI components directly onto frames."""

    @classmethod
    def draw_all_overlays(
        cls,
        img: Image.Image,
        t: float,
        scene_t: float,
        scene_duration: float,
        scene_idx: int,
        total_scenes: int,
        total_duration: float,
        topic: Dict[str, Any],
        accent_color: Tuple[int, int, int] = (0, 229, 255),
    ) -> None:
        """Master orchestrator rendering all HTML/CSS-inspired motion graphic elements."""
        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        # 1. Top Glassmorphism Status Pill (Top-Left)
        cls._draw_glass_status_pill(draw, t, scene_idx, total_scenes, accent_color)

        # 2. Audio Waveform Activity Visualizer (Top-Right, next to timer)
        cls._draw_audio_visualizer(draw, t, accent_color)

        # 3. Interactive Technical Callout Pointer (Transient: appears for only 2.5s per component)
        cls._draw_interactive_callout(draw, scene_t, scene_duration, scene_idx, total_scenes, topic, accent_color)

        # Composite overlay onto main image
        img.paste(Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB"), (0, 0))

    @classmethod
    def _draw_glass_status_pill(
        cls,
        draw: ImageDraw.ImageDraw,
        t: float,
        scene_idx: int,
        total_scenes: int,
        accent_color: Tuple[int, int, int],
    ) -> None:
        """Top-left frosted glass pill with live pulsing indicator dot."""
        pill_x1, pill_y1 = 48, 52
        pill_w, pill_h = 320, 48
        pill_x2, pill_y2 = pill_x1 + pill_w, pill_y1 + pill_h

        # Frosted dark translucent container
        draw.rounded_rectangle(
            [pill_x1, pill_y1, pill_x2, pill_y2],
            radius=24,
            fill=(10, 16, 28, 210),
            outline=(255, 255, 255, 35),
            width=1,
        )

        # Pulsing green/cyan live dot
        pulse = 0.5 + 0.5 * math.sin(t * 6.0)
        dot_r = int(5 + pulse * 2)
        dot_cx, dot_cy = pill_x1 + 22, pill_y1 + (pill_h // 2)

        # Outer glow
        draw.ellipse(
            [dot_cx - dot_r - 3, dot_cy - dot_r - 3, dot_cx + dot_r + 3, dot_cy + dot_r + 3],
            fill=(*accent_color, int(60 * pulse)),
        )
        # Inner solid dot
        draw.ellipse(
            [dot_cx - 5, dot_cy - 5, dot_cx + 5, dot_cy + 5],
            fill=(0, 255, 180, 240),
        )

        # Label text
        font_pill = load_sub_font(18)
        label = f"3D SCHEMATIC // 0{scene_idx + 1} OF 0{max(1, total_scenes)}"
        draw.text((pill_x1 + 38, pill_y1 + 14), label, font=font_pill, fill=(220, 235, 255, 230))

    @classmethod
    def _draw_audio_visualizer(
        cls,
        draw: ImageDraw.ImageDraw,
        t: float,
        accent_color: Tuple[int, int, int],
    ) -> None:
        """Animated audio frequency visualizer bars dancing in sync with narration."""
        vx = WIDTH - 180
        vy = 66
        num_bars = 6
        bar_w = 4
        bar_gap = 5

        for i in range(num_bars):
            # Dynamic pseudo-frequency oscillation based on time and bar index
            freq = 4.0 + i * 2.2
            phase = i * 0.8
            bar_height = int(6 + 18 * abs(math.sin(t * freq + phase) * math.cos(t * 1.5)))
            bx = vx + i * (bar_w + bar_gap)
            by1 = vy - (bar_height // 2)
            by2 = vy + (bar_height // 2)

            alpha = int(140 + 100 * (i / num_bars))
            draw.rounded_rectangle([bx, by1, bx + bar_w, by2], radius=2, fill=(*accent_color, alpha))

    @classmethod
    def _draw_interactive_callout(
        cls,
        draw: ImageDraw.ImageDraw,
        scene_t: float,
        scene_duration: float,
        scene_idx: int,
        total_scenes: int,
        topic: Dict[str, Any],
        accent_color: Tuple[int, int, int],
    ) -> None:
        """
        Interactive Remotion-style technical callout pointer:
        - Transient: Appears ONLY for 2.5 seconds (from 1.2s to 3.7s of each component scene).
        - Disappears completely for the rest of the scene so visuals remain 100% clean and unobstructed.
        - Never displays in the final outro / call-to-action scene.
        """
        # Skip callout on final outro scene
        if scene_idx >= max(1, total_scenes - 1):
            return

        # Transient visibility window: 1.2s to 3.7s (2.5 seconds total)
        callout_start = 1.2
        callout_end = 3.7
        if scene_t < callout_start or scene_t > callout_end:
            return

        # Smooth fade-in (0.35s) and fade-out (0.35s)
        fade_time = 0.35
        if scene_t < (callout_start + fade_time):
            alpha_ratio = (scene_t - callout_start) / fade_time
        elif scene_t > (callout_end - fade_time):
            alpha_ratio = (callout_end - scene_t) / fade_time
        else:
            alpha_ratio = 1.0

        spring = max(0.0, min(1.0, alpha_ratio))
        if spring <= 0.05:
            return

        bullets = topic.get("bullets", [])
        if not bullets or scene_idx >= len(bullets):
            return

        raw_bullet = bullets[scene_idx]

        # Clean concise component name (no long truncated sentences)
        clean_text = raw_bullet
        for sep in [",", " - ", " – ", " polished", " creates", " behaves", " keep", " to "]:
            if sep in clean_text:
                clean_text = clean_text.split(sep)[0]
        clean_text = clean_text.strip().upper()[:32]

        # Target position on the interactive cutaway image
        is_left_side = (scene_idx % 2 == 0)
        target_x = 360 if is_left_side else 720
        target_y = 960 + int(math.sin(scene_t * 1.8) * 12.0)

        # Pulsing target rings
        pulse = 0.5 + 0.5 * math.sin(scene_t * 5.0)
        ring_r = int(12 + pulse * 5)
        draw.ellipse(
            [target_x - ring_r, target_y - ring_r, target_x + ring_r, target_y + ring_r],
            outline=(*accent_color, int(180 * spring)),
            width=2,
        )
        draw.ellipse(
            [target_x - 4, target_y - 4, target_x + 4, target_y + 4],
            fill=(*accent_color, int(255 * spring)),
        )

        # Elbow leader line coordinates
        elbow_x = target_x - 60 if is_left_side else target_x + 60
        elbow_y = target_y - 70

        badge_w = 420
        badge_h = 68
        badge_x = elbow_x - badge_w if is_left_side else elbow_x
        badge_y = elbow_y - (badge_h // 2)

        # Clamp safely inside frame
        badge_x = max(36, min(WIDTH - badge_w - 36, badge_x))

        # Draw leader lines
        line_color = (*accent_color, int(200 * spring))
        draw.line([(target_x, target_y), (elbow_x, elbow_y)], fill=line_color, width=2)
        shelf_end_x = badge_x + badge_w if is_left_side else badge_x
        draw.line([(elbow_x, elbow_y), (shelf_end_x, elbow_y)], fill=line_color, width=2)

        # Frosted Glassmorphism Spec Card
        draw.rounded_rectangle(
            [badge_x, badge_y, badge_x + badge_w, badge_y + badge_h],
            radius=14,
            fill=(8, 14, 24, int(225 * spring)),
            outline=(*accent_color, int(160 * spring)),
            width=2,
        )

        # Micro technical header inside card
        font_micro = load_sub_font(13)
        tech_header = f"FEATURE_0{scene_idx + 1} // CUTAWAY ANALYSIS"
        draw.text(
            (badge_x + 18, badge_y + 10),
            tech_header,
            font=font_micro,
            fill=(*accent_color, int(220 * spring)),
        )

        # Main component label text
        font_body = load_sub_font(18)
        draw.text(
            (badge_x + 18, badge_y + 32),
            clean_text,
            font=font_body,
            fill=(255, 255, 255, int(245 * spring)),
        )

    @classmethod
    def _draw_telemetry_gauge(
        cls,
        draw: ImageDraw.ImageDraw,
        t: float,
        scene_idx: int,
        topic: Dict[str, Any],
        accent_color: Tuple[int, int, int],
    ) -> None:
        """Lower-right floating digital telemetry widget showing real-time physical metric."""
        card_w, card_h = 280, 68
        card_x = WIDTH - card_w - 48
        card_y = 1260

        # Glass container
        draw.rounded_rectangle(
            [card_x, card_y, card_x + card_w, card_y + card_h],
            radius=14,
            fill=(10, 16, 26, 200),
            outline=(255, 255, 255, 30),
            width=1,
        )

        # Metrics dynamic cycle
        metrics = [
            ("TOLERANCE", f"{0.8 + 0.2 * math.sin(t * 3.1):.2f} µm"),
            ("PRESSURE", f"{38.0 + 4.0 * math.sin(t * 2.5):.1f} ATM"),
            ("VELOCITY", f"{31.2 + 2.5 * math.cos(t * 2.8):.1f} L/s"),
            ("EFFICIENCY", f"{98.4 + 1.2 * math.sin(t * 1.9):.1f} %"),
        ]
        label, val = metrics[scene_idx % len(metrics)]

        font_label = load_sub_font(14)
        font_val = load_headline_font(28)

        draw.text((card_x + 18, card_y + 12), label, font=font_label, fill=(160, 185, 215, 200))
        draw.text((card_x + 18, card_y + 30), val, font=font_val, fill=accent_color)
