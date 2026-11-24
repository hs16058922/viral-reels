"""Channel branding for studio reels: cover card + follow-the-account outro.

- Cover: the flashy ReelCoverGenerator card over the first 0.4 s. Instagram's thumb_offset=100 ms
  (Graph API) and the direct publisher's 0.1 s frame grab both land on it.
- Outro: the reel's last frame, dimmed, with a FOLLOW card while a pre-recorded voice line
  (assets/branding/follow_cta.mp3, EdgeTTS, committed so CI needs no network) asks viewers to follow.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

from engine.cover_generator import ReelCoverGenerator
from engine.fonts import load_headline_font, load_sub_font

ROOT = Path(__file__).resolve().parents[2]
HANDLE = "@curio__motion"
CTA_AUDIO = ROOT / "assets" / "branding" / "follow_cta.mp3"
COVER_SECONDS = 0.4
ACCENT = (232, 69, 52)  # studio caption red


def _probe(path: Path) -> dict:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=width,height,r_frame_rate",
                          "-of", "json", str(path)], capture_output=True, text=True, check=True).stdout
    d = json.loads(out)
    v = next((s for s in d["streams"] if "width" in s), {"r_frame_rate": "0/1"})
    num, den = v["r_frame_rate"].split("/")
    return {"w": v.get("width"), "h": v.get("height"), "fps": round(int(num) / int(den)),
            "dur": float(d["format"]["duration"])}


def _frame(video: Path, at: str, out: Path) -> Image.Image:
    seek = ["-sseof", at] if at.startswith("-") else ["-ss", at]
    subprocess.run(["ffmpeg", "-y", "-v", "error", *seek, "-i", str(video), "-frames:v", "1", str(out)], check=True)
    return Image.open(out).convert("RGB")


def _strip_captions(img: Image.Image) -> Image.Image:
    """Burned-in captions sit in the top band (above the safe area); refill it from the row beneath."""
    W, H = img.size
    y = int(H * 0.2)
    img.paste(img.crop((0, y, W, y + 1)).resize((W, y)), (0, 0))
    return img


def cover_texts(topic: dict) -> dict:
    """Topic cover fields, falling back to the title ("Main: sub")."""
    head, _, sub = (topic.get("title") or topic["id"].replace("_", " ")).partition(":")
    return {"hook_line_1": topic.get("cover_hook_1") or head.strip().upper(),
            "hook_line_2": topic.get("cover_hook_2") or (sub.strip() or "How it really works").upper(),
            "category_tag": topic.get("cover_tag") or "3D BREAKDOWN",
            "curiosity_sticker": topic.get("cover_sticker") or "CUTAWAY VIEW"}


def end_card(last: Image.Image) -> Image.Image:
    W, H = last.size
    img = ImageEnhance.Brightness(last.filter(ImageFilter.GaussianBlur(18))).enhance(0.45).convert("RGBA")
    d = ImageDraw.Draw(img)
    s = W / 1080

    def centred(text, font, y, fill, pad=None, box=None):
        x0, y0, x1, y1 = d.textbbox((0, 0), text, font=font)
        x = (W - (x1 - x0)) // 2
        if box:
            px, py = pad
            d.rounded_rectangle([x - px, y - py, x + (x1 - x0) + px, y + (y1 - y0) + py + y0], radius=int(28 * s), fill=box)
        d.text((x - x0, y), text, font=font, fill=fill)

    centred("Enjoyed this?", load_sub_font(int(54 * s)), int(700 * s), (235, 235, 235))
    centred("FOLLOW", load_headline_font(int(120 * s)), int(800 * s), (255, 255, 255),
            pad=(int(60 * s), int(26 * s)), box=(*ACCENT, 255))
    centred(HANDLE, load_headline_font(int(64 * s)), int(1010 * s), (255, 255, 255))
    centred("A new 3D breakdown every day", load_sub_font(int(44 * s)), int(1110 * s), (210, 210, 210))
    return img.convert("RGB")


def finalize(src: Path, dst: Path, topic: dict) -> Path:
    """src reel -> dst with the cover card on the first 0.4 s and the follow outro appended."""
    p = _probe(src)
    cta_len = _probe(CTA_AUDIO)["dur"]
    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        hero = _strip_captions(_frame(src, "1.5", t / "hero.png"))
        cover = ReelCoverGenerator.generate_cover(base_image_path=hero, output_path=t / "cover.jpg",
                                                  **cover_texts(topic)).convert("RGB").resize((p["w"], p["h"]))
        cover.save(t / "cover.png")
        end_card(_frame(src, "-0.1", t / "last.png")).save(t / "card.png")
        outro = cta_len + 0.5
        fc = (f"[1:v]scale={p['w']}:{p['h']},setsar=1[cv];"
              f"[0:v]setsar=1[mv];[mv][cv]overlay=0:0:eof_action=pass,fps={p['fps']},format=yuv420p[main];"
              f"[2:v]scale={p['w']}:{p['h']},setsar=1,fps={p['fps']},format=yuv420p[card];"
              "[0:a]aformat=sample_rates=48000:channel_layouts=stereo[a0];"
              f"[3:a]aformat=sample_rates=48000:channel_layouts=stereo,apad=whole_dur={outro:.3f}[a1];"
              "[main][a0][card][a1]concat=n=2:v=1:a=1[v][a]")
        dst.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(src),
                        "-loop", "1", "-t", f"{COVER_SECONDS}", "-i", str(t / "cover.png"),
                        "-loop", "1", "-t", f"{outro:.3f}", "-i", str(t / "card.png"),
                        "-i", str(CTA_AUDIO), "-filter_complex", fc, "-map", "[v]", "-map", "[a]",
                        "-c:v", "libx264", "-crf", "18", "-preset", "medium", "-profile:v", "high",
                        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(dst)], check=True)
    cover.save(dst.with_name(dst.stem.replace("_reel", "") + "_cover.jpg"), quality=92)
    return dst
