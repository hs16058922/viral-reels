"""
Autonomous Reel Builder for Viral Reels Studio.

Generates complete 1080x1920 30fps vertical reels from any topic in topics.json:
1. Synthesizes voiceover via Edge TTS
2. Transcribes word-level timestamps via Whisper
3. Generates high-CTR flashy cover card
4. Renders 1080x1920 MP4 with dynamic zoom, safe karaoke captions, and badges
5. Updates topics.json with the generated video_path and status='ready'
"""

import asyncio
import logging
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
from PIL import Image, ImageDraw, ImageFont

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.cover_generator import ReelCoverGenerator
from engine.edge_voice import VoiceEngine
from engine.fonts import load_headline_font, load_sub_font
from engine.whisper_captions import CaptionGenerator

logger = logging.getLogger("viral_reels.reel_builder")

WIDTH, HEIGHT = 1080, 1920
FPS = 30
EXPORT_DIR = PROJECT_ROOT / "export"
TMP_DIR = PROJECT_ROOT / "tmp"


class AutonomousReelBuilder:
    """Builds a complete reel video for any topic."""

    @classmethod
    def build_reel_for_topic(cls, topic: Dict[str, Any]) -> Path:
        """Fully render video, cover, and audio for a topic."""
        topic_id = topic["id"]
        output_mp4 = EXPORT_DIR / f"{topic_id}_reel.mp4"
        covers_dir = EXPORT_DIR / "covers"
        covers_dir.mkdir(parents=True, exist_ok=True)
        cover_path = covers_dir / f"{topic_id}_cover.jpg"

        if output_mp4.exists():
            logger.info("Reel already built at %s", output_mp4)
            return output_mp4

        logger.info("🎬 Building automated reel for topic '%s'...", topic["title"])

        # 1. Synthesize Voiceover
        audio_path = TMP_DIR / f"{topic_id}_voice.mp3"
        TMP_DIR.mkdir(parents=True, exist_ok=True)
        logger.info("Synthesizing neural voiceover...")
        ve = VoiceEngine()
        ve.synthesize(text=topic["script"], output_path=audio_path)

        # 2. Transcribe word timings
        logger.info("Transcribing audio timestamps with Whisper...")
        cap_gen = CaptionGenerator(model_size="base")
        txn = cap_gen.transcribe(audio_path)
        words = txn.words
        total_duration = 35.0
        if words:
            total_duration = words[-1].end + 0.8
        try:
            ffprobe_bin = shutil.which("ffprobe") or "ffprobe"
            cmd = [ffprobe_bin, "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(audio_path)]
            out = subprocess.check_output(cmd, text=True).strip()
            total_duration = float(out)
        except Exception:
            pass

        # 3. Generate Flashy Cover Card
        logger.info("Generating high-CTR flashy cover...")
        # Use available scene image or fallback base
        base_img = TMP_DIR / "scenes" / "scene_1.jpg"
        if not base_img.exists():
            base_img = PROJECT_ROOT / "export" / "sample_frames" / "frame_02s.jpg"

        cover_img = ReelCoverGenerator.generate_cover(
            base_image_path=base_img if base_img.exists() else None,
            hook_line_1=topic.get("cover_hook_1") or topic["title"][:22].upper(),
            hook_line_2=topic.get("cover_hook_2") or "HOW IT WORKS?!",
            category_tag=topic.get("cover_tag") or "ENGINEERING EXPLAINED",
            curiosity_sticker=topic.get("cover_sticker") or "SECRET REVEALED",
            output_path=cover_path,
        ).convert("RGB")

        # 4. Render video frames into FFmpeg pipe
        total_frames = int(total_duration * FPS)
        logger.info("Rendering %d frames (%.1fs) to %s...", total_frames, total_duration, output_mp4.name)

        ffmpeg_bin = shutil.which("ffmpeg") or "ffmpeg"
        ffmpeg_cmd = [
            ffmpeg_bin, "-y",
            "-f", "rawvideo",
            "-vcodec", "rawvideo",
            "-s", f"{WIDTH}x{HEIGHT}",
            "-pix_fmt", "rgb24",
            "-r", str(FPS),
            "-i", "-",
            "-i", str(audio_path),
            "-c:v", "libx264",
            "-profile:v", "main",
            "-level", "3.1",
            "-pix_fmt", "yuv420p",
            "-r", str(FPS),
            "-g", "60",
            "-keyint_min", "60",
            "-sc_threshold", "0",
            "-preset", "fast",
            "-crf", "18",
            "-c:a", "aac",
            "-b:a", "128k",
            "-ar", "48000",
            "-ac", "2",
            "-movflags", "+faststart",
            "-shortest",
            str(output_mp4),
        ]

        process = subprocess.Popen(
            ffmpeg_cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )

        # Background visual base frame
        bg_im = Image.open(base_img).convert("RGBA").resize((int(WIDTH * 1.2), int(HEIGHT * 1.2))) if base_img.exists() else Image.new("RGBA", (int(WIDTH * 1.2), int(HEIGHT * 1.2)), (10, 14, 24, 255))
        bw, bh = bg_im.size

        # Pre-render top badge
        badge = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
        d_b = ImageDraw.Draw(badge)
        font_title = load_headline_font(46)
        font_sub = load_sub_font(26)

        b_w, b_h = 920, 130
        b_x = (WIDTH - b_w) // 2
        b_y = 170
        d_b.rounded_rectangle([b_x, b_y, b_x + b_w, b_y + b_h], radius=22, fill=(10, 14, 24, 230), outline=(255, 215, 0), width=3)
        
        # Auto-scale title
        t_box = d_b.textbbox((0, 0), topic["title"].upper(), font=font_title)
        tw = t_box[2] - t_box[0]
        if tw > (b_w - 60):
            font_title = load_headline_font(max(26, int(46 * (b_w - 60) / tw)))
            t_box = d_b.textbbox((0, 0), topic["title"].upper(), font=font_title)
            tw = t_box[2] - t_box[0]
        d_b.text(((WIDTH - tw) // 2, b_y + 18), topic["title"].upper(), font=font_title, fill=(255, 255, 255))
        
        sub_text = topic.get("cover_tag") or "HOW IT WORKS IN 3D"
        s_box = d_b.textbbox((0, 0), sub_text, font=font_sub)
        sw = s_box[2] - s_box[0]
        d_b.text(((WIDTH - sw) // 2, b_y + 82), sub_text, font=font_sub, fill=(255, 215, 0))

        # Render loop
        for frame_idx in range(total_frames):
            t = frame_idx / FPS

            # First 0.4s: Cover hook frame
            if frame_idx < 12:
                frame_img = cover_img.copy()
                process.stdin.write(frame_img.tobytes())
                continue

            # Gentle zoom motion
            zoom = 1.0 + 0.15 * (frame_idx / total_frames)
            cw, ch = int(WIDTH / zoom), int(HEIGHT / zoom)
            cx, cy = (bw - cw) // 2, (bh - ch) // 2
            cropped = bg_im.crop((cx, cy, cx + cw, cy + ch)).resize((WIDTH, HEIGHT), Image.Resampling.BILINEAR).convert("RGB")

            # Paste badge
            cropped.paste(badge, (0, 0), badge)

            # Karaoke caption
            c_words, active_idx = cls.get_active_caption(t, words)
            if c_words:
                cls.draw_caption(cropped, c_words, active_idx)

            process.stdin.write(cropped.tobytes())

        _, stderr_data = process.communicate()

        if process.returncode != 0:
            err = stderr_data.decode(errors="replace") if stderr_data else "Unknown"
            raise RuntimeError(f"FFmpeg render failed: {err}")

        logger.info("🎉 Reel successfully built: %s (%.2f MB)", output_mp4.name, output_mp4.stat().st_size / (1024 * 1024))
        return output_mp4

    @staticmethod
    def get_active_caption(t: float, words: list, max_words: int = 2):
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

    @staticmethod
    def draw_caption(img: Image.Image, words: list, active_idx: int):
        draw = ImageDraw.Draw(img)
        spacing = 22
        max_safe_w = 820
        base_normal_sz, base_active_sz = 64, 72
        font_normal = load_headline_font(base_normal_sz)
        font_active = load_headline_font(base_active_sz)

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
        if total_w > max_safe_w:
            scale = max_safe_w / total_w
            font_normal = load_headline_font(max(34, int(base_normal_sz * scale)))
            font_active = load_headline_font(max(38, int(base_active_sz * scale)))
            word_boxes, total_w, max_h = measure(font_normal, font_active)

        center_y = 1380
        cur_x = (WIDTH - total_w) // 2
        pad_x, pad_y = 28, 16

        pill_x1 = cur_x - pad_x
        pill_x2 = cur_x + total_w + pad_x
        pill_y1 = center_y - (max_h // 2) - pad_y
        pill_y2 = center_y + (max_h // 2) + pad_y + 4

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

        word_x = cur_x
        for idx, (word, font, w_w, w_h) in enumerate(word_boxes):
            is_active = (idx == active_idx)
            fill_color = (255, 215, 0) if is_active else (255, 255, 255)
            y_pos = center_y - (w_h // 2)

            draw.text((word_x + 3, y_pos + 4), word, font=font, fill=(0, 0, 0, 210))
            draw.text((word_x, y_pos), word, font=font, fill=fill_color, stroke_width=6 if is_active else 5, stroke_fill=(0, 0, 0))
            word_x += w_w + spacing
