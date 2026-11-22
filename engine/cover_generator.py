"""
High-CTR Flashy Cover & Thumbnail Generator for Instagram Reels.

Generates 1080x1920 vertical cover images optimized for maximum clickability:
1. 1:1 and 4:5 Instagram Profile Grid Safe (no vital text cut off in grid view)
2. Ultra-high-contrast typography (Dual-tone Neon Yellow + Crisp White)
3. Heavy 3D drop-shadows & dark contrast outlines
4. Curiosity badge / sticker ("HOW IT WORKS", "SECRET REVEALED", "100% VACUUM")
5. Visual click magnets (glowing accent rings, curiosity callout, glassmorphic pill)
6. Clean @curio__motion profile branding
"""

import math
import re
from pathlib import Path
from typing import Optional, Tuple
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageEnhance
from engine.fonts import load_headline_font, load_sub_font

# Canvas Dimensions
WIDTH = 1080
HEIGHT = 1920
GRID_SAFE_Y1 = 420   # 1080x1080 Instagram profile square top
GRID_SAFE_Y2 = 1500  # 1080x1080 Instagram profile square bottom

# System fonts
FONT_HEADLINE_LARGE = "/System/Library/Fonts/Supplemental/Impact.ttf"
FONT_BADGE = "/System/Library/Fonts/Supplemental/Impact.ttf"
FONT_SUB = "/System/Library/Fonts/Helvetica.ttc"


def sanitize_font_text(text: str) -> str:
    """Strip emojis and non-standard symbols that Impact.ttf lacks glyphs for."""
    # Keep standard ascii letters, digits, punctuation, and common symbols
    clean = re.sub(r'[^\x20-\x7E]', '', text)
    return clean.strip()


class ReelCoverGenerator:
    """Generates high-CTR, click-magnet covers for vertical reels."""

    @staticmethod
    def generate_cover(
        base_image_path: Path,
        hook_line_1: str,
        hook_line_2: str,
        category_tag: str = "ENGINEERING EXPLAINED",
        curiosity_sticker: str = "SECRET REVEALED",
        accent_color: Tuple[int, int, int] = (255, 230, 0),  # Neon Yellow
        output_path: Optional[Path] = None,
    ) -> Image.Image:
        """Create a flashy 1080x1920 cover image."""
        
        hook_line_1 = sanitize_font_text(hook_line_1)
        hook_line_2 = sanitize_font_text(hook_line_2)
        category_tag = sanitize_font_text(category_tag)
        curiosity_sticker = sanitize_font_text(curiosity_sticker)

        # 1. Base Image Processing (Enhance saturation, contrast, and depth)
        if base_image_path and Path(base_image_path).exists():
            base = Image.open(base_image_path).convert("RGBA")
            base = base.resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS)
            
            # Boost saturation and contrast for scroll-stopping visual impact
            enhancer_col = ImageEnhance.Color(base)
            base = enhancer_col.enhance(1.25)
            enhancer_con = ImageEnhance.Contrast(base)
            base = enhancer_con.enhance(1.15)
        else:
            base = Image.new("RGBA", (WIDTH, HEIGHT), (12, 16, 26, 255))

        # 2. Add cinematic dark radial vignette & top/bottom gradients
        vignette = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
        d_vig = ImageDraw.Draw(vignette)
        
        # Top gradient (for header bar)
        for y in range(0, 360):
            alpha = int(210 * (1.0 - (y / 360) ** 1.3))
            d_vig.line([(0, y), (WIDTH, y)], fill=(0, 0, 0, alpha))
            
        # Center-lower gradient (under headline in 1:1 grid safe zone)
        for y in range(700, 1600):
            dist = abs(y - 1100) / 450.0
            factor = max(0.0, 1.0 - dist)
            alpha = int(190 * factor)
            d_vig.line([(0, y), (WIDTH, y)], fill=(0, 0, 0, alpha))

        # Bottom gradient (for branding & UI safe zone)
        for y in range(1600, HEIGHT):
            alpha = int(220 * ((y - 1600) / 320.0))
            d_vig.line([(0, y), (WIDTH, y)], fill=(0, 0, 0, alpha))

        base = Image.alpha_composite(base, vignette)
        draw = ImageDraw.Draw(base)

        # 3. Top Category Pill: "// ENGINEERING EXPLAINED //"
        font_cat = load_headline_font(36)
        cat_text = f"// {category_tag.upper()} //"
        bbox_cat = draw.textbbox((0, 0), cat_text, font=font_cat)
        cat_w = bbox_cat[2] - bbox_cat[0]
        cat_h = bbox_cat[3] - bbox_cat[1]
        
        pill_pad_x, pill_pad_y = 32, 14
        cat_box_w = cat_w + pill_pad_x * 2
        cat_box_h = cat_h + pill_pad_y * 2
        cat_box_x = (WIDTH - cat_box_w) // 2
        cat_box_y = 220
        
        # Outer neon glow outline
        draw.rounded_rectangle(
            [cat_box_x - 3, cat_box_y - 3, cat_box_x + cat_box_w + 3, cat_box_y + cat_box_h + 3],
            radius=20,
            fill=(*accent_color, 60),
        )
        # Main dark glassmorphic pill
        draw.rounded_rectangle(
            [cat_box_x, cat_box_y, cat_box_x + cat_box_w, cat_box_y + cat_box_h],
            radius=18,
            fill=(12, 16, 26, 240),
            outline=accent_color,
            width=3,
        )
        draw.text(
            (cat_box_x + pill_pad_x, cat_box_y + pill_pad_y - 2),
            cat_text,
            font=font_cat,
            fill=accent_color,
        )

        # 4. Curiosity Sticker: "[ ZERO AIR MOLECULES ]"
        font_sticker = load_headline_font(42)
        stk_text = f"[ {curiosity_sticker.upper()} ]"
        bbox_stk = draw.textbbox((0, 0), stk_text, font=font_sticker)
        stk_w = bbox_stk[2] - bbox_stk[0]
        stk_box_x = (WIDTH - stk_w - 60) // 2
        stk_box_y = 860
        
        # Sticker appearance with white outline
        draw.rounded_rectangle(
            [stk_box_x, stk_box_y, stk_box_x + stk_w + 60, stk_box_y + 68],
            radius=12,
            fill=(255, 30, 60, 245),  # High-alert red
            outline=(255, 255, 255, 220),
            width=3,
        )
        draw.text(
            (stk_box_x + 30, stk_box_y + 12),
            stk_text,
            font=font_sticker,
            fill=(255, 255, 255),
        )

        # 5. Dual-Tone Giant Headline (1:1 Instagram profile grid safe zone)
        # Line 1: Pure White with deep shadow
        # Line 2: Neon Electric Yellow with black stroke
        font_h1 = load_headline_font(92)
        font_h2 = load_headline_font(102)

        # Measure Line 1
        bbox_1 = draw.textbbox((0, 0), hook_line_1, font=font_h1)
        w1 = bbox_1[2] - bbox_1[0]
        # Auto-scale Line 1 if exceeds safe 920px
        if w1 > 920:
            scale1 = 920 / w1
            font_h1 = load_headline_font(int(92 * scale1))
            bbox_1 = draw.textbbox((0, 0), hook_line_1, font=font_h1)
            w1 = bbox_1[2] - bbox_1[0]
        x1 = (WIDTH - w1) // 2
        y1 = 960

        # Measure Line 2
        bbox_2 = draw.textbbox((0, 0), hook_line_2, font=font_h2)
        w2 = bbox_2[2] - bbox_2[0]
        # Auto-scale Line 2 if exceeds safe 940px
        if w2 > 940:
            scale2 = 940 / w2
            font_h2 = load_headline_font(int(102 * scale2))
            bbox_2 = draw.textbbox((0, 0), hook_line_2, font=font_h2)
            w2 = bbox_2[2] - bbox_2[0]
        x2 = (WIDTH - w2) // 2
        y2 = y1 + (bbox_1[3] - bbox_1[1]) + 26

        # Draw 3D shadow for Line 1
        for offset_x, offset_y in [(6, 8), (4, 6), (2, 4)]:
            draw.text((x1 + offset_x, y1 + offset_y), hook_line_1, font=font_h1, fill=(0, 0, 0, 220))
        # Draw Line 1 with bold stroke
        draw.text(
            (x1, y1),
            hook_line_1,
            font=font_h1,
            fill=(255, 255, 255),
            stroke_width=10,
            stroke_fill=(0, 0, 0),
        )

        # Draw 3D shadow for Line 2
        for offset_x, offset_y in [(8, 10), (6, 8), (3, 5)]:
            draw.text((x2 + offset_x, y2 + offset_y), hook_line_2, font=font_h2, fill=(0, 0, 0, 230))
        # Draw Line 2 with Neon Accent & bold stroke
        draw.text(
            (x2, y2),
            hook_line_2,
            font=font_h2,
            fill=accent_color,
            stroke_width=12,
            stroke_fill=(0, 0, 0),
        )

        # 6. Click Magnet Callout Pill: "HOW DOES IT WORK? >>"
        font_sub = load_headline_font(44)
        cta_text = "HOW DOES IT WORK? >>"
        bbox_cta = draw.textbbox((0, 0), cta_text, font=font_sub)
        cta_w = bbox_cta[2] - bbox_cta[0]
        cta_box_w = cta_w + 64
        cta_box_x = (WIDTH - cta_box_w) // 2
        cta_box_y = y2 + (bbox_2[3] - bbox_2[1]) + 40

        draw.rounded_rectangle(
            [cta_box_x, cta_box_y, cta_box_x + cta_box_w, cta_box_y + 68],
            radius=18,
            fill=(0, 0, 0, 220),
            outline=(255, 255, 255, 180),
            width=3,
        )
        draw.text(
            (cta_box_x + 32, cta_box_y + 10),
            cta_text,
            font=font_sub,
            fill=(255, 255, 255),
        )

        # 7. Bottom Branding Pill: "@curio__motion"
        font_brand = load_sub_font(32)
        brand_text = "@curio__motion"
        bbox_br = draw.textbbox((0, 0), brand_text, font=font_brand)
        br_w = bbox_br[2] - bbox_br[0]
        br_x = (WIDTH - br_w) // 2
        br_y = 1760

        draw.rounded_rectangle(
            [br_x - 24, br_y - 10, br_x + br_w + 24, br_y + 44],
            radius=16,
            fill=(10, 14, 24, 220),
            outline=(*accent_color, 120),
            width=2,
        )
        draw.text((br_x, br_y), brand_text, font=font_brand, fill=(240, 240, 240))

        # Save if output path provided
        if output_path:
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            base.convert("RGB").save(str(output_path), "JPEG", quality=95)

        return base


if __name__ == "__main__":
    test_out = Path("export/sample_frames/test_flashy_cover.jpg")
    ReelCoverGenerator.generate_cover(
        base_image_path=Path("tmp/scenes/scene_1.jpg"),
        hook_line_1="YOUR THERMAL FLASK",
        hook_line_2="USES OUTER SPACE?!",
        category_tag="PHYSICS SECRETS",
        curiosity_sticker="ZERO AIR MOLECULES",
        output_path=test_out,
    )
    print("Generated test cover:", test_out)
