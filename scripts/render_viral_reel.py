#!/usr/bin/env python3
"""
Direct High-Speed Viral Reel Renderer.

Renders 1080x1920 30fps video by streaming Pillow-composited frames
directly into FFmpeg's rawvideo stdin. Combines:
- 3D photorealistic science visualization scenes
- Smooth Ken Burns dynamic camera motions (zoom/pan)
- HyperFrames scientific badges & glassmorphic pill cards
- Whisper word-by-word viral karaoke captions with gold highlight (#FFD700)
- Edge TTS crisp neural audio track
"""

import math
import shutil
import subprocess
import sys
import time
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.cover_generator import ReelCoverGenerator
TMP_DIR = PROJECT_ROOT / "tmp"
SCENES_DIR = TMP_DIR / "scenes"
EXPORT_DIR = PROJECT_ROOT / "export"
AUDIO_PATH = TMP_DIR / "thermal_voice.mp3"
FINAL_OUTPUT = EXPORT_DIR / "thermal_bottle_reel.mp4"

WIDTH, HEIGHT = 1080, 1920
FPS = 30

# Load fonts
FONT_IMPACT_TITLE = ImageFont.truetype("/System/Library/Fonts/Supplemental/Impact.ttf", 50)
FONT_HELV_SUB = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 28)
FONT_CAPTION_NORMAL = ImageFont.truetype("/System/Library/Fonts/Supplemental/Impact.ttf", 66)
FONT_CAPTION_ACTIVE = ImageFont.truetype("/System/Library/Fonts/Supplemental/Impact.ttf", 74)

# 6 Scientific Scenes timeline matching Edge TTS voiceover
SCENES = [
    {
        "id": "scene_1",
        "path": SCENES_DIR / "scene_1.jpg",
        "start": 0.0,
        "end": 6.8,
        "title": "HOW A THERMAL BOTTLE WORKS",
        "subtitle": "THE SECRET BEHIND 24H HOT & COLD",
        "accent": (255, 215, 0),  # Gold
        "zoom_start": 1.0,
        "zoom_end": 1.18,
        "pan_y": 0.0,
    },
    {
        "id": "scene_2",
        "path": SCENES_DIR / "scene_2.jpg",
        "start": 6.8,
        "end": 15.0,
        "title": "DOUBLE-WALL STEEL CHAMBER",
        "subtitle": "TWO FLASKS WELDED TOGETHER",
        "accent": (0, 220, 255),  # Cyan
        "zoom_start": 1.10,
        "zoom_end": 1.10,
        "pan_y": 0.12,  # Slow pan down
    },
    {
        "id": "scene_3",
        "path": SCENES_DIR / "scene_3.jpg",
        "start": 15.0,
        "end": 25.0,
        "title": "THE VACUUM GAP",
        "subtitle": "ZERO ATOMS = ZERO CONDUCTION",
        "accent": (255, 90, 90),  # Red/Coral
        "zoom_start": 1.0,
        "zoom_end": 1.22,
        "pan_y": 0.0,
    },
    {
        "id": "scene_4",
        "path": SCENES_DIR / "scene_4.jpg",
        "start": 25.0,
        "end": 32.5,
        "title": "MIRROR RADIATION BARRIER",
        "subtitle": "INFRARED HEAT BOUNCES BACK",
        "accent": (255, 215, 0),  # Gold
        "zoom_start": 1.20,
        "zoom_end": 1.02,
        "pan_y": 0.0,
    },
    {
        "id": "scene_5",
        "path": SCENES_DIR / "scene_5.jpg",
        "start": 32.5,
        "end": 35.8,
        "title": "AIRTIGHT VACUUM STOPPER",
        "subtitle": "BLOCKS CONVECTION HEAT LEAK",
        "accent": (40, 255, 160),  # Emerald
        "zoom_start": 1.0,
        "zoom_end": 1.15,
        "pan_y": -0.05,
    },
    {
        "id": "scene_6",
        "path": SCENES_DIR / "scene_6.jpg",
        "start": 35.8,
        "end": 38.5,
        "title": "TRAPPED IN TIME",
        "subtitle": "PIPING HOT 24H • ICE COLD 48H",
        "accent": (0, 230, 255),  # Ice cyan
        "zoom_start": 1.0,
        "zoom_end": 1.20,
        "pan_y": 0.0,
    },
]


def load_and_prep_scenes():
    """Pre-load scene images and pre-render their header badges."""
    prepared = []
    base_w, base_h = int(WIDTH * 1.3), int(HEIGHT * 1.3)  # Extra margin for smooth zoom
    
    for s in SCENES:
        raw_im = Image.open(s["path"]).convert("RGBA")
        im_hires = raw_im.resize((base_w, base_h), Image.Resampling.LANCZOS)
        
        # Pre-render top badge layer
        badge = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
        draw = ImageDraw.Draw(badge)
        
        box_w, box_h = 920, 140
        box_x = (WIDTH - box_w) // 2
        box_y = 170
        
        # Rounded pill with glow outline
        draw.rounded_rectangle(
            [box_x, box_y, box_x + box_w, box_y + box_h],
            radius=24,
            fill=(10, 14, 24, 230),
            outline=s["accent"],
            width=3,
        )
        
        # Title text with auto-scaling
        t_font = FONT_IMPACT_TITLE
        t_box = draw.textbbox((0, 0), s["title"], font=t_font)
        tw = t_box[2] - t_box[0]
        max_title_w = box_w - 60
        if tw > max_title_w:
            t_font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Impact.ttf", max(28, int(50 * (max_title_w / tw))))
            t_box = draw.textbbox((0, 0), s["title"], font=t_font)
            tw = t_box[2] - t_box[0]
        draw.text(((WIDTH - tw) // 2, box_y + 20), s["title"], font=t_font, fill=(255, 255, 255, 255))
        
        # Subtitle text
        s_box = draw.textbbox((0, 0), s["subtitle"], font=FONT_HELV_SUB)
        sw = s_box[2] - s_box[0]
        draw.text(((WIDTH - sw) // 2, box_y + 86), s["subtitle"], font=FONT_HELV_SUB, fill=(*s["accent"], 255))
        
        prepared.append({
            "config": s,
            "hires_image": im_hires,
            "badge_overlay": badge,
        })
    return prepared


def load_whisper_word_timings():
    """Load word timings from Whisper."""
    from engine.whisper_captions import CaptionGenerator
    gen = CaptionGenerator(model_size="base")
    txn = gen.transcribe(AUDIO_PATH)
    return txn.words


def get_active_caption(t: float, words: list, max_words: int = 2):
    """Find the 1-to-2 word group and which word is active at timestamp t.
    
    Using 2 words per pop maximizes mobile retention, keeps font massive,
    and prevents any text cut-off on vertical 9:16 reels.
    """
    groups = []
    i = 0
    while i < len(words):
        chunk = words[i:i + max_words]
        groups.append(chunk)
        i += len(chunk)

    for group in groups:
        g_start = group[0].start
        g_end = group[-1].end + 0.18
        if g_start <= t <= g_end:
            active_idx = 0
            for idx, w in enumerate(group):
                if w.start <= t <= (w.end + 0.12):
                    active_idx = idx
            return [w.word for w in group], active_idx
    return None, -1


def draw_viral_caption(img: Image.Image, words: list, active_idx: int):
    """Draw viral bold-pop karaoke captions with auto-fitting and symmetric bounds."""
    draw = ImageDraw.Draw(img)
    
    spacing = 22
    max_safe_w = 820  # Safe zone: leaves 130px padding on left and right
    
    # Base font sizes
    base_normal_sz = 64
    base_active_sz = 72
    font_normal = ImageFont.truetype("/System/Library/Fonts/Supplemental/Impact.ttf", base_normal_sz)
    font_active = ImageFont.truetype("/System/Library/Fonts/Supplemental/Impact.ttf", base_active_sz)
    
    # Calculate word dimensions
    def measure(fn, fa):
        boxes = []
        tot_w = 0
        max_h = 0
        for idx, w in enumerate(words):
            f = fa if idx == active_idx else fn
            bbox = draw.textbbox((0, 0), w, font=f)
            w_w = bbox[2] - bbox[0]
            w_h = bbox[3] - bbox[1]
            boxes.append((w, f, w_w, w_h))
            tot_w += w_w
            max_h = max(max_h, w_h)
        tot_w += spacing * max(0, len(words) - 1)
        return boxes, tot_w, max_h

    word_boxes, total_w, max_h = measure(font_normal, font_active)
    
    # Auto-scale down if long words exceed the safe area
    if total_w > max_safe_w:
        scale = max_safe_w / total_w
        font_normal = ImageFont.truetype("/System/Library/Fonts/Supplemental/Impact.ttf", max(34, int(base_normal_sz * scale)))
        font_active = ImageFont.truetype("/System/Library/Fonts/Supplemental/Impact.ttf", max(38, int(base_active_sz * scale)))
        word_boxes, total_w, max_h = measure(font_normal, font_active)

    # Cohesive symmetric pill bounding box
    center_y = 1380
    cur_x = (WIDTH - total_w) // 2
    pad_x = 28
    pad_y = 16
    
    pill_x1 = cur_x - pad_x
    pill_x2 = cur_x + total_w + pad_x
    pill_y1 = center_y - (max_h // 2) - pad_y
    pill_y2 = center_y + (max_h // 2) + pad_y + 4
    
    # Semi-transparent dark pill background
    overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    d_ov = ImageDraw.Draw(overlay)
    d_ov.rounded_rectangle(
        [pill_x1, pill_y1, pill_x2, pill_y2],
        radius=20,
        fill=(0, 0, 0, 195),
        outline=(255, 215, 0, 170) if active_idx >= 0 else (255, 255, 255, 70),
        width=2,
    )
    img.paste(Image.alpha_composite(img.convert("RGBA"), overlay), (0, 0))
    draw = ImageDraw.Draw(img)
    
    # Draw words with drop shadow and outline
    word_x = cur_x
    for idx, (word, font, w_w, w_h) in enumerate(word_boxes):
        is_active = (idx == active_idx)
        fill_color = (255, 215, 0) if is_active else (255, 255, 255)
        stroke_color = (0, 0, 0)
        stroke_width = 6 if is_active else 5
        
        y_pos = center_y - (w_h // 2)
        
        # Drop shadow
        draw.text((word_x + 3, y_pos + 4), word, font=font, fill=(0, 0, 0, 210))
        # Main text with stroke
        draw.text(
            (word_x, y_pos),
            word,
            font=font,
            fill=fill_color,
            stroke_width=stroke_width,
            stroke_fill=stroke_color,
        )
        word_x += w_w + spacing


def main():
    print("=" * 60)
    print("🚀 VIRAL REELS STUDIO — Direct Fast-Pipe Rendering")
    print("=" * 60)
    
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    
    # 1. Prepare assets & flashy cover
    print("\n[1/4] Pre-processing 3D scene visual assets & flashy cover card...")
    scenes_data = load_and_prep_scenes()
    
    covers_dir = EXPORT_DIR / "covers"
    covers_dir.mkdir(parents=True, exist_ok=True)
    cover_path = covers_dir / "thermal_bottle_cover.jpg"
    print(f"  ⚡ Generating high-CTR flashy cover: {cover_path}")
    cover_img = ReelCoverGenerator.generate_cover(
        base_image_path=SCENES_DIR / "scene_1.jpg",
        hook_line_1="YOUR THERMAL FLASK",
        hook_line_2="USES OUTER SPACE?!",
        category_tag="PHYSICS SECRETS",
        curiosity_sticker="ZERO AIR MOLECULES",
        output_path=cover_path,
    ).convert("RGB")
    
    # 2. Transcribe voiceover
    print("\n[2/4] Transcribing voiceover & syncing word-level timestamps...")
    words = load_whisper_word_timings()
    print(f"  ✅ Transcribed {len(words)} words for karaoke synchronization")
    
    # 3. Setup FFmpeg stream pipe
    print("\n[3/4] Initializing FFmpeg video encoding pipeline...")
    total_duration = SCENES[-1]["end"]
    total_frames = int(total_duration * FPS)
    print(f"  Target: 1080x1920 @ {FPS}fps, Total Frames: {total_frames} ({total_duration:.1f}s)")
    
    ffmpeg_bin = shutil.which("ffmpeg") or "ffmpeg"
    ffmpeg_cmd = [
        ffmpeg_bin, "-y",
        "-f", "rawvideo",
        "-vcodec", "rawvideo",
        "-s", f"{WIDTH}x{HEIGHT}",
        "-pix_fmt", "rgb24",
        "-r", str(FPS),
        "-i", "-",  # Read from stdin
        "-i", str(AUDIO_PATH),
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-preset", "fast",
        "-crf", "18",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        str(FINAL_OUTPUT),
    ]
    
    process = subprocess.Popen(
        ffmpeg_cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    
    # 4. Render frames and stream to FFmpeg
    print("\n[4/4] Rendering frames with motion, badges & viral captions...")
    t_start = time.time()
    
    cur_scene_idx = 0
    for frame_idx in range(total_frames):
        t = frame_idx / FPS
        
        # First 0.4s (frames 0-11): Flashy high-CTR Cover Card hook & thumbnail anchor
        if frame_idx < 12:
            frame_img = cover_img.copy()
            process.stdin.write(frame_img.tobytes())
            continue

        # Advance scene index if needed
        while cur_scene_idx < len(scenes_data) - 1 and t >= scenes_data[cur_scene_idx]["config"]["end"]:
            cur_scene_idx += 1
            
        scene_item = scenes_data[cur_scene_idx]
        cfg = scene_item["config"]
        s_start, s_end = cfg["start"], cfg["end"]
        s_dur = max(0.1, s_end - s_start)
        progress = min(1.0, max(0.0, (t - s_start) / s_dur))
        
        # Ken Burns zoom calculation
        zoom = cfg["zoom_start"] + (cfg["zoom_end"] - cfg["zoom_start"]) * progress
        crop_w = int(WIDTH / zoom)
        crop_h = int(HEIGHT / zoom)
        
        # Calculate crop center
        hires = scene_item["hires_image"]
        hw, hh = hires.size
        center_x = hw // 2
        pan_offset_y = int(cfg["pan_y"] * hh * progress)
        center_y = (hh // 2) + pan_offset_y
        
        x1 = max(0, min(hw - crop_w, center_x - crop_w // 2))
        y1 = max(0, min(hh - crop_h, center_y - crop_h // 2))
        x2 = x1 + crop_w
        y2 = y1 + crop_h
        
        cropped = hires.crop((x1, y1, x2, y2))
        frame_img = cropped.resize((WIDTH, HEIGHT), Image.Resampling.BILINEAR).convert("RGB")
        
        # Composite top badge
        frame_img.paste(scene_item["badge_overlay"], (0, 0), scene_item["badge_overlay"])
        
        # Draw viral caption
        c_words, active_idx = get_active_caption(t, words)
        if c_words:
            draw_viral_caption(frame_img, c_words, active_idx)
            
        # Stream raw RGB bytes to FFmpeg stdin
        process.stdin.write(frame_img.tobytes())
        
        if frame_idx % 150 == 0 or frame_idx == total_frames - 1:
            pct = (frame_idx + 1) / total_frames * 100
            elapsed = time.time() - t_start
            fps_speed = (frame_idx + 1) / max(0.01, elapsed)
            print(f"  🎬 Rendered {frame_idx + 1:4d}/{total_frames} frames ({pct:5.1f}%) — {fps_speed:4.1f} fps")
            
    process.stdin.close()
    stderr_output = process.stderr.read()
    process.wait()
    
    if process.returncode != 0:
        print("❌ FFmpeg error:", stderr_output.decode(errors="replace"))
        return
        
    total_time = time.time() - t_start
    print("\n" + "=" * 60)
    print(f"🎉 SUCCESS! Reel rendered in {total_time:.1f}s")
    print(f"📁 Output file: {FINAL_OUTPUT}")
    print("=" * 60)
    
    # Probe file
    ffprobe_bin = shutil.which("ffprobe") or "ffprobe"
    probe = subprocess.run([
        ffprobe_bin, "-v", "error",
        "-show_entries", "format=duration,size,bit_rate",
        "-show_entries", "stream=width,height,codec_name,r_frame_rate",
        "-of", "json",
        str(FINAL_OUTPUT)
    ], capture_output=True, text=True)
    print(probe.stdout)


if __name__ == "__main__":
    main()
