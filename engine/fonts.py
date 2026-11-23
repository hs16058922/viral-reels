"""
Cross-platform font loader for macOS and Linux (Ubuntu / GitHub Actions).
"""

import os
from pathlib import Path
from PIL import ImageFont

CANDIDATE_HEADLINE_FONTS = {
    "IMPACT": [
        "/System/Library/Fonts/Supplemental/Impact.ttf",
        "/Library/Fonts/Impact.ttf",
        "/usr/share/fonts/truetype/msttcorefonts/Impact.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    ],
    "FUTURA": [
        "/System/Library/Fonts/Supplemental/Futura.ttc",
        "/System/Library/Fonts/Supplemental/DIN Alternate Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    ],
    "ARIAL_BLACK": [
        "/System/Library/Fonts/Supplemental/Arial Black.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    ],
    "DIN_ALTERNATE": [
        "/System/Library/Fonts/Supplemental/DIN Alternate Bold.ttf",
        "/System/Library/Fonts/Supplemental/Futura.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ],
}

CANDIDATE_SUB_FONTS = [
    # macOS
    "/System/Library/Fonts/Helvetica.ttc",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    # Linux (Ubuntu)
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
]


def get_headline_font_path(font_family: str = "IMPACT") -> str:
    candidates = CANDIDATE_HEADLINE_FONTS.get(font_family.upper(), CANDIDATE_HEADLINE_FONTS["IMPACT"])
    for path in candidates:
        if os.path.exists(path):
            return path
    # Fallback to any headline font
    for paths in CANDIDATE_HEADLINE_FONTS.values():
        for path in paths:
            if os.path.exists(path):
                return path
    return ""


def get_sub_font_path() -> str:
    for path in CANDIDATE_SUB_FONTS:
        if os.path.exists(path):
            return path
    return ""


def load_headline_font(size: int, font_family: str = "IMPACT") -> ImageFont.FreeTypeFont:
    p = get_headline_font_path(font_family=font_family)
    if p:
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            pass
    return ImageFont.load_default()


def load_sub_font(size: int) -> ImageFont.FreeTypeFont:
    p = get_sub_font_path()
    if p:
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            pass
    return ImageFont.load_default()
