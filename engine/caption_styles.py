"""
Dynamic Multi-Theme Viral Caption Styler for CurioMotion Reels.

Provides 5 distinctive, high-retention visual aesthetic themes:
1. CYBER_GOLD: Classic viral science look (Cyan + Gold highlights, dark glass pill)
2. MINIMAL_DROP_SHADOW: Clean modern documentary aesthetic (Heavy 3D shadow, electric yellow pop, no pill)
3. CRIMSON_PULSE: High-urgency alert aesthetic (Obsidian red pill, fire-orange pop)
4. MATRIX_HUD: Technical blueprint HUD aesthetic (Emerald/Lime pop with bracket accents)
5. DEEP_VIOLET: Futuristic cyberpunk aesthetic (Frosted purple glass, hot neon magenta pop)

Automatically rotates or selects themes based on topic attributes so each reel looks unique!
"""

import hashlib
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
from PIL import Image, ImageDraw, ImageFont

from engine.fonts import load_headline_font


@dataclass
class CaptionTheme:
    name: str
    has_pill: bool
    pill_bg: Tuple[int, int, int, int]
    pill_border: Tuple[int, int, int, int]
    pill_radius: int
    normal_color: Tuple[int, int, int]
    normal_stroke_color: Tuple[int, int, int]
    normal_stroke_width: int
    active_color: Tuple[int, int, int]
    active_stroke_color: Tuple[int, int, int]
    active_stroke_width: int
    drop_shadow: bool
    shadow_offset: Tuple[int, int]
    shadow_color: Tuple[int, int, int, int]
    active_bracket: bool = False


THEMES: Dict[str, CaptionTheme] = {
    "CYBER_GOLD": CaptionTheme(
        name="CYBER_GOLD",
        has_pill=True,
        pill_bg=(10, 14, 24, 215),
        pill_border=(255, 215, 0, 180),
        pill_radius=22,
        normal_color=(255, 255, 255),
        normal_stroke_color=(0, 0, 0),
        normal_stroke_width=5,
        active_color=(255, 215, 0),  # Gold
        active_stroke_color=(0, 0, 0),
        active_stroke_width=6,
        drop_shadow=True,
        shadow_offset=(3, 4),
        shadow_color=(0, 0, 0, 220),
    ),
    "MINIMAL_DROP_SHADOW": CaptionTheme(
        name="MINIMAL_DROP_SHADOW",
        has_pill=False,
        pill_bg=(0, 0, 0, 0),
        pill_border=(0, 0, 0, 0),
        pill_radius=0,
        normal_color=(255, 255, 255),
        normal_stroke_color=(0, 0, 0),
        normal_stroke_width=6,
        active_color=(255, 235, 59),  # Vibrant Electric Yellow
        active_stroke_color=(0, 0, 0),
        active_stroke_width=8,
        drop_shadow=True,
        shadow_offset=(5, 6),
        shadow_color=(0, 0, 0, 245),
    ),
    "CRIMSON_PULSE": CaptionTheme(
        name="CRIMSON_PULSE",
        has_pill=True,
        pill_bg=(28, 8, 12, 225),
        pill_border=(255, 65, 85, 200),
        pill_radius=20,
        normal_color=(255, 255, 255),
        normal_stroke_color=(15, 0, 0),
        normal_stroke_width=5,
        active_color=(255, 75, 43),  # Fire Coral Orange
        active_stroke_color=(0, 0, 0),
        active_stroke_width=7,
        drop_shadow=True,
        shadow_offset=(3, 4),
        shadow_color=(0, 0, 0, 230),
    ),
    "MATRIX_HUD": CaptionTheme(
        name="MATRIX_HUD",
        has_pill=True,
        pill_bg=(8, 18, 14, 230),
        pill_border=(0, 255, 136, 190),
        pill_radius=16,
        normal_color=(230, 245, 235),
        normal_stroke_color=(0, 10, 5),
        normal_stroke_width=5,
        active_color=(0, 255, 136),  # Electric Lime
        active_stroke_color=(0, 0, 0),
        active_stroke_width=7,
        drop_shadow=True,
        shadow_offset=(2, 3),
        shadow_color=(0, 0, 0, 230),
        active_bracket=True,
    ),
    "DEEP_VIOLET": CaptionTheme(
        name="DEEP_VIOLET",
        has_pill=True,
        pill_bg=(22, 10, 36, 225),
        pill_border=(180, 80, 255, 200),
        pill_radius=24,
        normal_color=(255, 255, 255),
        normal_stroke_color=(10, 0, 20),
        normal_stroke_width=5,
        active_color=(255, 40, 160),  # Hot Neon Magenta
        active_stroke_color=(0, 0, 0),
        active_stroke_width=7,
        drop_shadow=True,
        shadow_offset=(3, 4),
        shadow_color=(0, 0, 0, 230),
    ),
}

THEME_ORDER = ["CYBER_GOLD", "MINIMAL_DROP_SHADOW", "CRIMSON_PULSE", "MATRIX_HUD", "DEEP_VIOLET"]


class CaptionStyleRotator:
    """Selects and applies dynamic caption themes per topic."""

    @classmethod
    def get_theme_for_topic(cls, topic: Dict[str, Any]) -> CaptionTheme:
        """Deterministically pick a theme based on topic ID and title hash."""
        # Check if topic explicitly requested a style
        req = topic.get("caption_style")
        if req and req in THEMES:
            return THEMES[req]

        # Use MD5 hash of topic ID to cycle through available themes
        seed = topic.get("id", "default")
        h = int(hashlib.md5(seed.encode("utf-8")).hexdigest(), 16)
        theme_key = THEME_ORDER[h % len(THEME_ORDER)]
        return THEMES[theme_key]

    @classmethod
    def render_caption_to_frame(
        cls,
        img: Image.Image,
        words: List[str],
        active_idx: int,
        theme: CaptionTheme,
        center_y: int = 1420,
        max_safe_w: int = 860,
    ) -> None:
        """Render word-level highlighted captions onto frame with the active theme."""
        if not words:
            return

        spacing = 22
        base_normal_sz = 64
        base_active_sz = 72

        font_normal = load_headline_font(base_normal_sz)
        font_active = load_headline_font(base_active_sz)

        draw_temp = ImageDraw.Draw(img)

        # Pre-measure words with current theme rules
        def measure(fn, fa):
            boxes = []
            for i, w in enumerate(words):
                f = fa if (i == active_idx) else fn
                txt = f"[{w}]" if (theme.active_bracket and i == active_idx) else w
                bb = draw_temp.textbbox((0, 0), txt, font=f)
                boxes.append((txt, f, bb[2] - bb[0], bb[3] - bb[1]))
            tot = sum(b[2] for b in boxes) + max(0, len(boxes) - 1) * spacing
            max_h = max(b[3] for b in boxes) if boxes else 0
            return boxes, tot, max_h

        word_boxes, total_w, max_h = measure(font_normal, font_active)

        # Scale down if caption exceeds safe reading margins
        scale_iter = 0
        while total_w > max_safe_w and scale_iter < 8:
            base_normal_sz -= 4
            base_active_sz -= 4
            font_normal = load_headline_font(base_normal_sz)
            font_active = load_headline_font(base_active_sz)
            word_boxes, total_w, max_h = measure(font_normal, font_active)
            scale_iter += 1

        width, height = img.size
        cur_x = (width - total_w) // 2

        # 1. Render Background Pill if enabled for this theme
        if theme.has_pill:
            pad_x = 28
            pad_y = 16
            pill_x1 = cur_x - pad_x
            pill_x2 = cur_x + total_w + pad_x
            pill_y1 = center_y - (max_h // 2) - pad_y
            pill_y2 = center_y + (max_h // 2) + pad_y + 4

            overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            d_ov = ImageDraw.Draw(overlay)
            d_ov.rounded_rectangle(
                [pill_x1, pill_y1, pill_x2, pill_y2],
                radius=theme.pill_radius,
                fill=theme.pill_bg,
                outline=theme.pill_border if active_idx >= 0 else (255, 255, 255, 50),
                width=2,
            )
            img.paste(Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB"), (0, 0))

        draw = ImageDraw.Draw(img)

        # 2. Render Words
        word_x = cur_x
        for idx, (word, font, w_w, w_h) in enumerate(word_boxes):
            is_active = (idx == active_idx)
            fill_color = theme.active_color if is_active else theme.normal_color
            stroke_color = theme.active_stroke_color if is_active else theme.normal_stroke_color
            stroke_width = theme.active_stroke_width if is_active else theme.normal_stroke_width

            y_pos = center_y - (w_h // 2)

            # Drop Shadow
            if theme.drop_shadow:
                sx, sy = theme.shadow_offset
                draw.text(
                    (word_x + sx, y_pos + sy),
                    word,
                    font=font,
                    fill=theme.shadow_color,
                    stroke_width=stroke_width,
                    stroke_fill=(0, 0, 0, 200),
                )

            # Main text
            draw.text(
                (word_x, y_pos),
                word,
                font=font,
                fill=fill_color,
                stroke_width=stroke_width,
                stroke_fill=stroke_color,
            )
            word_x += w_w + spacing
