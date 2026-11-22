#!/usr/bin/env python3
"""
Custom reel builder for the thermal steel water bottle explanation.
Integrates HyperFrames badging, FFmpeg dynamic motion & cuts,
Edge TTS voiceover, and Whisper viral karaoke word-by-word captions.
"""

import os
import subprocess
import time
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TMP_DIR = PROJECT_ROOT / "tmp"
SCENES_DIR = TMP_DIR / "scenes"
EXPORT_DIR = PROJECT_ROOT / "export"

SCENES_CONFIG = [
    {
        "id": "scene_1",
        "img": SCENES_DIR / "scene_1.jpg",
        "duration": 6.8,
        "title": "HOW A THERMAL BOTTLE WORKS",
        "subtitle": "THE SECRET BEHIND 24H HOT & COLD",
        "accent": (255, 215, 0),  # Gold
        "zoom_expr": "z='min(zoom+0.0014,1.22)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'",
    },
    {
        "id": "scene_2",
        "img": SCENES_DIR / "scene_2.jpg",
        "duration": 8.2,
        "title": "DOUBLE-WALL STEEL CHAMBER",
        "subtitle": "TWO FLASKS WELDED TOGETHER",
        "accent": (0, 217, 255),  # Cyan
        "zoom_expr": "z=1.12:x='iw/2-(iw/zoom/2)':y='(ih-ih/zoom)*(on/{total_frames})'",
    },
    {
        "id": "scene_3",
        "img": SCENES_DIR / "scene_3.jpg",
        "duration": 10.0,
        "title": "THE VACUUM GAP",
        "subtitle": "ZERO ATOMS = ZERO HEAT CONDUCTION",
        "accent": (255, 100, 100),  # Coral
        "zoom_expr": "z='min(zoom+0.0012,1.25)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'",
    },
    {
        "id": "scene_4",
        "img": SCENES_DIR / "scene_4.jpg",
        "duration": 7.5,
        "title": "MIRROR RADIATION BARRIER",
        "subtitle": "INFRARED HEAT BOUNCES BACK",
        "accent": (255, 215, 0),  # Gold
        "zoom_expr": "z='max(1.22-0.0012*on,1.02)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'",
    },
    {
        "id": "scene_5",
        "img": SCENES_DIR / "scene_5.jpg",
        "duration": 3.5,
        "title": "AIRTIGHT VACUUM STOPPER",
        "subtitle": "BLOCKS CONVECTION HEAT LEAK",
        "accent": (50, 255, 150),  # Emerald
        "zoom_expr": "z='min(zoom+0.0015,1.18)':x='iw/2-(iw/zoom/2)':y='ih*0.22'",
    },
    {
        "id": "scene_6",
        "img": SCENES_DIR / "scene_6.jpg",
        "duration": 3.0,
        "title": "TRAPPED IN TIME",
        "subtitle": "PIPING HOT 24H • ICE COLD 48H",
        "accent": (0, 220, 255),  # Ice cyan
        "zoom_expr": "z='min(zoom+0.0020,1.22)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'",
    },
]


def render_scene_badge(img_path: Path, title: str, subtitle: str, accent: tuple) -> Path:
    """Create a 1080x1920 image with a stylish HyperFrames pill badge at the top."""
    im = Image.open(img_path).convert("RGBA")
    im = im.resize((1080, 1920), Image.Resampling.LANCZOS)
    
    overlay = Image.new("RGBA", (1080, 1920), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    
    try:
        font_title = ImageFont.truetype("/System/Library/Fonts/Supplemental/Impact.ttf", 52)
        font_sub = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 30)
    except Exception:
        font_title = ImageFont.load_default()
        font_sub = ImageFont.load_default()
        
    box_w, box_h = 920, 140
    box_x = (1080 - box_w) // 2
    box_y = 180
    
    # Rounded badge box
    draw.rounded_rectangle(
        [box_x, box_y, box_x + box_w, box_y + box_h],
        radius=24,
        fill=(12, 16, 26, 225),
        outline=accent,
        width=3,
    )
    
    # Title
    t_bbox = draw.textbbox((0, 0), title, font=font_title)
    tw, th = t_bbox[2] - t_bbox[0], t_bbox[3] - t_bbox[1]
    draw.text(((1080 - tw) // 2, box_y + 20), title, font=font_title, fill=(255, 255, 255, 255))
    
    # Subtitle
    s_bbox = draw.textbbox((0, 0), subtitle, font=font_sub)
    sw, sh = s_bbox[2] - s_bbox[0], s_bbox[3] - s_bbox[1]
    draw.text(((1080 - sw) // 2, box_y + 86), subtitle, font=font_sub, fill=(*accent, 255))
    
    out_img = Image.alpha_composite(im, overlay).convert("RGB")
    out_path = img_path.with_name(f"{img_path.stem}_badged.jpg")
    out_img.save(out_path, quality=95)
    return out_path


def render_scene_video(badged_path: Path, scene_cfg: dict) -> Path:
    """Render a single scene image into an animated MP4 with Ken Burns camera move."""
    duration = scene_cfg["duration"]
    total_frames = int(duration * 30)
    zoom_expr = scene_cfg["zoom_expr"].replace("{total_frames}", str(total_frames))
    
    out_mp4 = TMP_DIR / f"{scene_cfg['id']}_clip.mp4"
    
    vf = f"zoompan={zoom_expr}:d={total_frames}:s=1080x1920:fps=30"
    cmd = [
        "/opt/homebrew/bin/ffmpeg",
        "-y",
        "-loop", "1",
        "-i", str(badged_path),
        "-vf", vf,
        "-t", f"{duration:.3f}",
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-preset", "fast",
        "-crf", "18",
        str(out_mp4)
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return out_mp4


def main():
    print("=" * 60)
    print("🚀 VIRAL REELS STUDIO — Building Thermal Bottle Reel")
    print("=" * 60)
    
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    
    clips = []
    
    # 1. Generate badged images and animated scene clips
    print("\n[1/5] Rendering animated scene clips with HyperFrames & Ken Burns...")
    for idx, cfg in enumerate(SCENES_CONFIG, 1):
        print(f"  🎬 Scene {idx}: {cfg['title']} ({cfg['duration']}s)")
        badged = render_scene_badge(cfg["img"], cfg["title"], cfg["subtitle"], cfg["accent"])
        clip = render_scene_video(badged, cfg)
        clips.append(clip)
        
    # 2. Concat all clips into a unified visual video
    print("\n[2/5] Concatenating scenes into continuous video track...")
    concat_list_file = TMP_DIR / "concat_list.txt"
    with open(concat_list_file, "w") as f:
        for c in clips:
            f.write(f"file '{c.resolve()}'\n")
            
    visual_mp4 = TMP_DIR / "visual_track.mp4"
    subprocess.run([
        "/opt/homebrew/bin/ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", str(concat_list_file),
        "-c", "copy",
        str(visual_mp4)
    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(f"  ✅ Visual track generated: {visual_mp4}")
    
    # 3. Add audio track
    print("\n[3/5] Mixing Edge TTS voiceover audio...")
    audio_file = TMP_DIR / "thermal_voice.mp3"
    with_audio_mp4 = TMP_DIR / "with_audio.mp4"
    subprocess.run([
        "/opt/homebrew/bin/ffmpeg", "-y",
        "-i", str(visual_mp4),
        "-i", str(audio_file),
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        str(with_audio_mp4)
    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(f"  ✅ Audio synchronized: {with_audio_mp4}")
    
    # 4. Burn viral bold_pop ASS captions
    print("\n[4/5] Burning Whisper viral word-by-word karaoke captions...")
    captions_file = TMP_DIR / "thermal_captions.ass"
    escaped_ass = str(captions_file.resolve()).replace("\\", "/").replace(":", "\\:")
    
    final_output = EXPORT_DIR / "thermal_bottle_reel.mp4"
    subprocess.run([
        "/opt/homebrew/bin/ffmpeg", "-y",
        "-i", str(with_audio_mp4),
        "-vf", f"ass='{escaped_ass}'",
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "18",
        "-c:a", "copy",
        str(final_output)
    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(f"  ✅ Final reel rendered: {final_output}")
    
    # 5. Verify final output
    print("\n[5/5] Verifying final reel file...")
    probe_res = subprocess.run([
        "/opt/homebrew/bin/ffprobe", "-v", "error",
        "-show_entries", "format=duration,size",
        "-show_entries", "stream=width,height,codec_name",
        "-of", "json",
        str(final_output)
    ], capture_output=True, text=True, check=True)
    print(probe_res.stdout)
    
    print("=" * 60)
    print(f"🎉 COMPLETED! Your viral reel is ready at:\n{final_output}")
    print("=" * 60)


if __name__ == "__main__":
    main()
