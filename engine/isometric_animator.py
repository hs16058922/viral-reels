"""
Multi-Layer 3D Isometric Motion Graphics Engine for Viral Reels.

Inspired by top-performing 3D isometric engineering motion graphics:
- Layer 0: Deep blueprint tech gradient background
- Layer 1: Seamless animated 3D isometric perspective grid with camera drift
- Layer 2: 3D extruded isometric pedestals & podiums with wireframe edge lighting
- Layer 3: Organic harmonic floating/levitation physics & dynamic ground contact shadows
- Layer 4: Animated energy/airflow particle streams moving along 3D grid tracks
- Layer 5: Floating glassmorphism callout cards with animated laser pointers & anchor reticles
- Layer 6: Modern upper-third kinetic viral typography (matching top aesthetic reels)
"""

import math
from typing import Any, Dict, List, Optional, Tuple
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from engine.caption_styles import CaptionTheme
from engine.fonts import load_headline_font, load_sub_font

WIDTH, HEIGHT = 1080, 1920


class IsometricMotionEngine:
    """Renders layered 3D isometric environments, floating physics, and kinetic motion overlays."""

    # Cached backgrounds for render speed
    _bg_cache: Dict[Tuple[int, int, str], Image.Image] = {}

    @classmethod
    def get_base_gradient(cls, width: int = WIDTH, height: int = HEIGHT, theme_name: str = "BLUEPRINT") -> Image.Image:
        """Get or render cached base gradient."""
        key = (width, height, theme_name)
        if key in cls._bg_cache:
            return cls._bg_cache[key].copy()

        img = Image.new("RGBA", (width, height), (10, 18, 36, 255))
        draw = ImageDraw.Draw(img)

        if theme_name == "OBSIDIAN":
            top_color = (18, 22, 32)
            bot_color = (8, 10, 16)
        elif theme_name == "CRIMSON":
            top_color = (28, 14, 20)
            bot_color = (12, 6, 10)
        else:  # Classic Blueprint Royal Blue
            top_color = (18, 48, 108)
            bot_color = (8, 20, 50)

        for y in range(0, height, 4):
            ratio = y / height
            r = int(top_color[0] * (1 - ratio) + bot_color[0] * ratio)
            g = int(top_color[1] * (1 - ratio) + bot_color[1] * ratio)
            b = int(top_color[2] * (1 - ratio) + bot_color[2] * ratio)
            draw.rectangle([0, y, width, y + 4], fill=(r, g, b, 255))

        cls._bg_cache[key] = img
        return img.copy()

    # ── Layer 0 & 1: 3D Blueprint Background & Drift Grid ─────────────

    @classmethod
    def render_blueprint_background(
        cls,
        width: int = WIDTH,
        height: int = HEIGHT,
        t: float = 0.0,
        theme_name: str = "BLUEPRINT",
    ) -> Image.Image:
        """Create a deep tech canvas with animated isometric grid lines."""
        img = cls.get_base_gradient(width, height, theme_name)
        draw = ImageDraw.Draw(img)

        if theme_name == "OBSIDIAN":
            grid_col = (45, 60, 85, 90)
        elif theme_name == "CRIMSON":
            grid_col = (90, 40, 55, 90)
        else:
            grid_col = (40, 100, 210, 95)

        # Seamless Panning Isometric Grid (30-degree isometric projection)
        drift = (t * 22.0) % 90.0
        grid_spacing = 90
        iso_angle = math.radians(28.0)
        tan_iso = math.tan(iso_angle)
        horizon_y = 480

        # Draw diagonal isometric parallel grid lines (Left-to-Right down)
        for offset in range(-height, width + height, grid_spacing):
            x0 = offset - drift * 1.6
            y0 = horizon_y
            x1 = x0 + height / tan_iso
            y1 = height
            draw.line([(x0, y0), (x1, y1)], fill=grid_col, width=1)

        # Draw diagonal isometric parallel grid lines (Right-to-Left down)
        for offset in range(-height, width + height, grid_spacing):
            x0 = offset + drift * 1.6
            y0 = horizon_y
            x1 = x0 - height / tan_iso
            y1 = height
            draw.line([(x0, y0), (x1, y1)], fill=grid_col, width=1)

        return img

    # ── Layer 2: 3D Extruded Isometric Pedestal / Stage ───────────────

    @staticmethod
    def draw_isometric_podium(
        draw: ImageDraw.ImageDraw,
        cx: int = WIDTH // 2,
        cy: int = 1440,
        radius_x: int = 440,
        radius_y: int = 220,
        height_extrude: int = 54,
        t: float = 0.0,
        accent_color: Tuple[int, int, int] = (0, 229, 255),
    ) -> None:
        """Render a 3D extruded hexagonal/rhombus isometric stage with glowing wireframe edges."""
        p_top = (cx, cy - radius_y)
        p_right = (cx + radius_x, cy)
        p_bot = (cx, cy + radius_y)
        p_left = (cx - radius_x, cy)

        p_bot_ext = (cx, cy + radius_y + height_extrude)
        p_right_ext = (cx + radius_x, cy + height_extrude)
        p_left_ext = (cx - radius_x, cy + height_extrude)

        # 1. Floor Ambient Shadow
        shadow_box = [cx - radius_x - 30, cy - radius_y + height_extrude, cx + radius_x + 30, cy + radius_y + height_extrude + 60]
        draw.ellipse(shadow_box, fill=(0, 0, 0, 130))

        # 2. Extruded Left Face
        draw.polygon([p_left, p_bot, p_bot_ext, p_left_ext], fill=(12, 28, 60, 230), outline=(*accent_color, 140))

        # 3. Extruded Right Face
        draw.polygon([p_bot, p_right, p_right_ext, p_bot_ext], fill=(16, 36, 76, 230), outline=(*accent_color, 140))

        # 4. Top Platform
        draw.polygon([p_top, p_right, p_bot, p_left], fill=(22, 50, 104, 215), outline=(*accent_color, 240))

        # Inner grid tile on platform top
        inner_scale = 0.68
        ip_top = (cx, cy - int(radius_y * inner_scale))
        ip_right = (cx + int(radius_x * inner_scale), cy)
        ip_bot = (cx, cy + int(radius_y * inner_scale))
        ip_left = (cx - int(radius_x * inner_scale), cy)
        draw.polygon([ip_top, ip_right, ip_bot, ip_left], outline=(*accent_color, 160), width=1)

    # ── Layer 3: Organic Floating Physics & Rounded Panel Prep ────────

    @classmethod
    def prepare_framed_subject(
        cls,
        raw_scene: Image.Image,
        target_w: int = 760,
        target_h: int = 980,
        radius: int = 36,
        accent_color: Tuple[int, int, int] = (0, 229, 255),
    ) -> Image.Image:
        """Frame a 3D cutaway scene with smooth rounded corners, wireframe border, and drop shadow."""
        subj = raw_scene.resize((target_w, target_h), Image.Resampling.LANCZOS).convert("RGB")

        # Rounded corner alpha mask
        mask = Image.new("L", (target_w, target_h), 0)
        d_m = ImageDraw.Draw(mask)
        d_m.rounded_rectangle([0, 0, target_w, target_h], radius=radius, fill=255)

        pad = 20
        total_w = target_w + pad * 2
        total_h = target_h + pad * 2

        framed = Image.new("RGBA", (total_w, total_h), (0, 0, 0, 0))
        d_f = ImageDraw.Draw(framed)

        # Soft drop shadow
        d_f.rounded_rectangle([pad, pad + 6, pad + target_w, pad + target_h + 6], radius=radius, fill=(0, 0, 0, 180))
        framed = framed.filter(ImageFilter.GaussianBlur(8))

        # Paste subject with mask
        subj_rgba = subj.convert("RGBA")
        subj_rgba.putalpha(mask)
        framed.paste(subj_rgba, (pad, pad), subj_rgba)

        # Clean edge: No harsh outer border frame
        return framed

    @classmethod
    def composite_floating_subject(
        cls,
        canvas: Image.Image,
        framed_subject: Image.Image,
        cx: int = WIDTH // 2,
        base_cy: int = 1020,
        t: float = 0.0,
        float_amp: float = 16.0,
        float_freq: float = 2.4,
    ) -> None:
        """Composite subject with smooth harmonic levitation and dynamic shadow dilation."""
        dy = math.sin(t * float_freq) * float_amp
        current_cy = int(base_cy + dy)

        # Dynamic Ground Contact Shadow on the Stage
        elevation_ratio = (dy + float_amp) / (2 * float_amp)
        shadow_w = int(framed_subject.width * (0.68 + 0.10 * (1.0 - elevation_ratio)))
        shadow_h = int(shadow_w * 0.30)
        shadow_y = base_cy + int(framed_subject.height * 0.46)

        shadow_img = Image.new("RGBA", (canvas.width, canvas.height), (0, 0, 0, 0))
        d_sh = ImageDraw.Draw(shadow_img)
        shadow_alpha = int(120 - 45 * (1.0 - elevation_ratio))
        d_sh.ellipse(
            [cx - shadow_w // 2, shadow_y - shadow_h // 2, cx + shadow_w // 2, shadow_y + shadow_h // 2],
            fill=(0, 0, 0, shadow_alpha),
        )
        shadow_blurred = shadow_img.filter(ImageFilter.GaussianBlur(12))
        canvas.paste(shadow_blurred, (0, 0), shadow_blurred)

        # Subject Breathing Scale Pulse (Micro organic movement)
        breathe_scale = 1.0 + 0.015 * math.sin(t * 1.8)
        new_w = int(framed_subject.width * breathe_scale)
        new_h = int(framed_subject.height * breathe_scale)

        if new_w != framed_subject.width or new_h != framed_subject.height:
            scaled_sub = framed_subject.resize((new_w, new_h), Image.Resampling.BILINEAR)
        else:
            scaled_sub = framed_subject

        sub_x = cx - scaled_sub.width // 2
        sub_y = current_cy - scaled_sub.height // 2

        if scaled_sub.mode == "RGBA":
            canvas.paste(scaled_sub, (sub_x, sub_y), scaled_sub)
        else:
            canvas.paste(scaled_sub, (sub_x, sub_y))

    # ── Layer 4: Real-Time Particle Stream Tracks ─────────────────────

    @staticmethod
    def render_energy_stream(
        draw: ImageDraw.ImageDraw,
        t: float,
        accent_color: Tuple[int, int, int] = (255, 90, 31),
    ) -> None:
        """Render high-speed energy or airflow packet pulses along isometric track lines."""
        tracks = [
            [(160, 920), (380, 1030), (540, 1120)],
            [(920, 920), (700, 1030), (540, 1120)],
            [(540, 1120), (320, 1260), (180, 1360)],
        ]

        for tr_idx, pts in enumerate(tracks):
            for i in range(len(pts) - 1):
                draw.line([pts[i], pts[i + 1]], fill=(*accent_color, 65), width=2)

            speed = 1.4 + tr_idx * 0.2
            progress = (t * speed + tr_idx * 0.33) % 1.0

            if progress < 0.5:
                sub_p = progress / 0.5
                p0, p1 = pts[0], pts[1]
            else:
                sub_p = (progress - 0.5) / 0.5
                p0, p1 = pts[1], pts[2]

            px = int(p0[0] + (p1[0] - p0[0]) * sub_p)
            py = int(p0[1] + (p1[1] - p0[1]) * sub_p)

            draw.ellipse([px - 5, py - 5, px + 5, py + 5], fill=accent_color)
            draw.ellipse([px - 10, py - 10, px + 10, py + 10], outline=(*accent_color, 120), width=1)

    # ── Layer 5: Floating 3D Callout Cards with Laser Pointers ────────

    @classmethod
    def render_floating_callouts(
        cls,
        img: Image.Image,
        t: float,
        bullets: List[str],
        scene_idx: int,
        accent_color: Tuple[int, int, int] = (0, 229, 255),
    ) -> None:
        """Render floating glassmorphism callout cards with animated laser pointers."""
        if not bullets:
            return

        bullet_idx = scene_idx % len(bullets)
        raw_text = bullets[bullet_idx]

        parts = raw_text.split(" ", 3)
        headline = " ".join(parts[:3]).upper() if len(parts) >= 3 else raw_text.upper()
        sub = parts[3][:32].upper() if len(parts) > 3 else "CRITICAL SPECIFICATION"

        draw = ImageDraw.Draw(img)
        font_head = load_headline_font(26)
        font_sub = load_sub_font(18)

        is_left = (scene_idx % 2 == 0)
        card_w, card_h = 360, 96
        card_bob = math.sin(t * 3.2 + scene_idx) * 8.0

        if is_left:
            card_x = 80
            card_y = int(820 + card_bob)
            target_x = WIDTH // 2 - 80
            target_y = 980
            line_start = (card_x + card_w, card_y + card_h // 2)
        else:
            card_x = WIDTH - card_w - 80
            card_y = int(840 + card_bob)
            target_x = WIDTH // 2 + 80
            target_y = 990
            line_start = (card_x, card_y + card_h // 2)

        elbow_x = (line_start[0] + target_x) // 2
        elbow_y = line_start[1]
        draw.line([line_start, (elbow_x, elbow_y)], fill=(*accent_color, 180), width=2)
        draw.line([(elbow_x, elbow_y), (target_x, target_y)], fill=(*accent_color, 180), width=2)

        draw.ellipse([target_x - 6, target_y - 6, target_x + 6, target_y + 6], fill=accent_color)
        draw.ellipse([target_x - 14, target_y - 14, target_x + 14, target_y + 14], outline=(*accent_color, 160), width=1)

        card_overlay = Image.new("RGBA", (img.width, img.height), (0, 0, 0, 0))
        d_cov = ImageDraw.Draw(card_overlay)
        d_cov.rounded_rectangle(
            [card_x + 6, card_y + 8, card_x + card_w + 6, card_y + card_h + 8],
            radius=18,
            fill=(0, 0, 0, 160),
        )
        d_cov.rounded_rectangle(
            [card_x, card_y, card_x + card_w, card_y + card_h],
            radius=18,
            fill=(10, 16, 26, 215),
            outline=(255, 255, 255, 40),
            width=1,
        )
        img.paste(Image.alpha_composite(img.convert("RGBA"), card_overlay), (0, 0))

        draw = ImageDraw.Draw(img)
        dot_cx = card_x + 28
        dot_cy = card_y + card_h // 2
        draw.ellipse([dot_cx - 5, dot_cy - 5, dot_cx + 5, dot_cy + 5], fill=accent_color)
        draw.ellipse([dot_cx - 9, dot_cy - 9, dot_cx + 9, dot_cy + 9], outline=(*accent_color, 120), width=1)

        draw.text((card_x + 48, card_y + 18), headline[:24], font=font_head, fill=(255, 255, 255))
        draw.text((card_x + 48, card_y + 54), sub[:26], font=font_sub, fill=(*accent_color, 220))

    # ── Layer 6: Upper-Third Kinetic Viral Captions ───────────────────

    @classmethod
    def render_upper_third_captions(
        cls,
        img: Image.Image,
        words: List[str],
        active_idx: int,
        theme: CaptionTheme,
        center_y: int = 360,
    ) -> None:
        """Render modern, clean 2-tone kinetic typography in the upper-third viral zone."""
        if not words:
            return

        draw = ImageDraw.Draw(img)
        font_family = getattr(theme, "font_family", "IMPACT")
        font_lead = load_headline_font(54, font_family=font_family)
        font_active = load_headline_font(62, font_family=font_family)

        lead_color = (255, 255, 255)
        active_accent = theme.active_color

        spacing = 18
        measured_words = []
        total_w = 0
        max_h = 0

        for idx, w in enumerate(words):
            is_active = (idx == active_idx)
            f = font_active if is_active else font_lead
            bb = draw.textbbox((0, 0), w, font=f)
            w_w = bb[2] - bb[0]
            w_h = bb[3] - bb[1]
            measured_words.append((w, f, is_active, w_w, w_h))
            total_w += w_w
            max_h = max(max_h, w_h)

        total_w += spacing * max(0, len(words) - 1)
        cur_x = (WIDTH - total_w) // 2

        for w, f, is_active, w_w, w_h in measured_words:
            y_pos = center_y - (w_h // 2)

            if is_active:
                # Active word: Punchy dynamic accent with 3D drop shadow and thick stroke
                draw.text((cur_x + 5, y_pos + 6), w, font=f, fill=(0, 0, 0, 240))
                draw.text((cur_x, y_pos), w, font=f, fill=active_accent, stroke_width=6, stroke_fill=(0, 0, 0))
            else:
                # Inactive words: Bold white with clean drop shadow
                draw.text((cur_x + 4, y_pos + 5), w, font=f, fill=(0, 0, 0, 220))
                draw.text((cur_x, y_pos), w, font=f, fill=lead_color, stroke_width=4, stroke_fill=(0, 0, 0))

            cur_x += w_w + spacing
