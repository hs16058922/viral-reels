"""generate_video(): topic → narrated, captioned, 3D-animated vertical reel.

Flow: SceneSpec v2 (specs/*.json) → EdgeTTS voice → Whisper word timings →
resolve phrase anchors to frames → headless Blender per scene (cached by
content hash, resumable) → Pillow caption overlay → SFX mix → FFmpeg mux →
QC report + contact sheet. Every stage writes inspectable artifacts.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from engine.blender_runner import BlenderMechanismRunner
from engine.studio.spec import VideoSpec, phrase_index, resolve, scene_hash, tokens

log = logging.getLogger("viral_reels.studio")
ROOT = Path(__file__).resolve().parents[2]
SPECS = Path(__file__).parent / "specs"
BLENDER_SCRIPT = Path(__file__).parent / "blender_scene.py"
CACHE = ROOT / "tmp" / "studio_cache"
ASSETS = ROOT / "assets" / "models"
QUALITY = {"preview": (540, 960), "production": (1080, 1920), "cycles": (1080, 1920), "realistic": (1080, 1920)}
# Generous per-frame timeouts: "realistic" on a 4-vCPU CI runner is ~40 s/frame.
SECONDS_PER_FRAME_BUDGET = {"preview": 2.0, "production": 8.0, "cycles": 120.0, "realistic": 120.0}
HDRI = ROOT / "assets" / "hdri" / "studio_small_09_1k.hdr"
SAMPLES = int(os.getenv("STUDIO_SAMPLES", "32"))
FORCE_CPU = os.getenv("STUDIO_CPU", "") == "1"
FONTS = ["/System/Library/Fonts/Supplemental/Arial Rounded Bold.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
         "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf"]
OPEN_LICENSES = {"CC0-1.0", "CC-BY-4.0", "MIT", "Apache-2.0", "self-made"}
ACCENT = (232, 69, 44)
STOP = {"how", "does", "do", "a", "an", "the", "work", "works", "of", "what", "is", "why"}


def _sha(*parts: str | bytes) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(p if isinstance(p, bytes) else p.encode())
    return h.hexdigest()[:16]


def _run(cmd: list[str], log_path: Optional[Path] = None, timeout: Optional[float] = None) -> subprocess.CompletedProcess:
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)  # list args, never shell=True
    if log_path:
        with log_path.open("a") as f:
            f.write(f"$ {' '.join(cmd)}\n{res.stdout[-20000:]}\n{res.stderr[-20000:]}\n")
    return res


def _duration(path: Path) -> float:
    out = _run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)])
    return float(out.stdout.strip())


def find_spec(topic: str) -> Path:
    """Pick the authored SceneSpec whose filename best matches the topic."""
    want = set(tokens(topic.replace("_", " "))) - STOP
    best, score = None, 0
    for p in sorted(SPECS.glob("*.json")):
        s = len(want & set(tokens(p.stem.replace("_", " "))))
        if s > score:
            best, score = p, s
    if not best:
        raise LookupError(
            f"No SceneSpec for topic {topic!r}. Author one in {SPECS}/ (schema: "
            f"`python -m engine.studio --schema`). Available: {[p.stem for p in SPECS.glob('*.json')]}")
    return best


def resolve_assets(spec: VideoSpec) -> list[dict]:
    """License-gate imported models; returns provenance rows for the QC report."""
    manifest_path = ASSETS / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    rows = []
    for sc in spec.scenes:
        for o in sc.objects:
            if o.kind != "asset":
                continue
            aid = o.params["asset_id"]
            entry = manifest.get(aid)
            if not entry:
                raise LookupError(f"asset '{aid}' not in {manifest_path}")
            if entry.get("license") not in OPEN_LICENSES:
                raise PermissionError(f"asset '{aid}' license {entry.get('license')!r} is not in the open allowlist")
            o.params["_path"] = str((ASSETS / entry["file"]).resolve())
            rows.append({"asset_id": aid, **entry})
    return rows


# ── Rendering ────────────────────────────────────────────────────────────

def shard_list(plan: dict, max_frames: int = 10**9) -> list[dict]:
    """Split scenes into frame ranges (inclusive) of at most max_frames, for CI fan-out."""
    out = []
    for sp in plan["scenes"]:
        n = sp["frames"]
        k = max(1, -(-n // max_frames))
        bounds = [round(i * n / k) for i in range(k + 1)]
        out += [{"scene": sp["index"], "start": a, "end": b - 1} for a, b in zip(bounds, bounds[1:])]
    return out


def shard_key(sp: dict, quality: str, start: int, end: int) -> str:
    """Content hash of everything that affects a segment's pixels (plan, range, quality, renderer source)."""
    w, h = QUALITY[quality]
    font = next((f for f in FONTS if Path(f).exists()), "")
    extra = f"{quality}{w}x{h}{font}{start}-{end}"
    if quality in ("cycles", "realistic"):
        extra += f"s{SAMPLES}{HDRI.name}"
    return scene_hash(sp, extra + _sha(BLENDER_SCRIPT.read_bytes()))


def render_shard(sp: dict, quality: str, job: Path, start: int = 0, end: Optional[int] = None,
                 retries: int = 1) -> dict:
    """Render frames [start, end] of one resolved scene to an MP4 segment (cached + resumable)."""
    end = sp["frames"] - 1 if end is None else end
    w, h = QUALITY[quality]
    font = next((f for f in FONTS if Path(f).exists()), "")
    realistic = quality in ("cycles", "realistic")
    key = shard_key(sp, quality, start, end)
    cache = CACHE / key
    name = f"{sp['index']:02d}_{sp['id']}" + ("" if (start, end) == (0, sp["frames"] - 1) else f"_{start:04d}-{end:04d}")
    mp4, blend = cache / "segment.mp4", job / "blender" / f"{sp['index']:02d}_{sp['id']}.blend"
    blend.parent.mkdir(parents=True, exist_ok=True)
    log_path = job / "logs" / f"{name}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    base = {"id": sp["id"], "name": name, "start": start, "end": end, "frames": end - start + 1, "mp4": str(mp4),
            "cache": str(cache)}
    if mp4.exists():
        log.info("%s: cache hit (%s)", name, key)
        if (cache / "scene.blend").exists() and start == 0:
            shutil.copy(cache / "scene.blend", blend)
        return {**json.loads((cache / "report.json").read_text()), **base, "cached": True}
    cache.mkdir(parents=True, exist_ok=True)
    for f in cache.glob("frame_*.png"):  # placeholders left by an interrupted render
        if f.stat().st_size == 0:
            f.unlink()
    (cache / "plan.json").write_text(json.dumps(sp, indent=1))
    blender = BlenderMechanismRunner.get_blender_binary()
    if not blender:
        raise RuntimeError("Blender not found: install Blender 4.2+ or put `blender` on PATH")
    cmd = [blender, "-b", "--factory-startup", "--disable-autoexec", "-noaudio", "-P", str(BLENDER_SCRIPT), "--",
           "--plan", str(cache / "plan.json"), "--out", str(cache), "--quality", quality,
           "--width", str(w), "--height", str(h), "--font", font,
           "--frame-start", str(start), "--frame-end", str(end), "--samples", str(SAMPLES)]
    if start == 0:
        cmd += ["--blend", str(cache / "scene.blend")]
    if realistic and HDRI.exists():
        cmd += ["--hdri", str(HDRI)]
    if FORCE_CPU:
        cmd.append("--cpu")
    timeout = 300 + (end - start + 1) * SECONDS_PER_FRAME_BUDGET[quality]
    t0 = time.time()
    want = [cache / f"frame_{f:04d}.png" for f in range(start, end + 1)]
    for attempt in range(retries + 1):
        try:
            res = _run(cmd, log_path, timeout=timeout)
            ok = res.returncode == 0 and all(f.exists() and f.stat().st_size > 0 for f in want)
        except subprocess.TimeoutExpired:
            ok = False
        if ok:
            break
        log.warning("%s: render attempt %d failed, see %s", name, attempt + 1, log_path)
        for f in cache.glob("frame_*.png"):
            if f.stat().st_size == 0:
                f.unlink()
    else:
        raise RuntimeError(f"{name} failed to render after {retries + 1} attempts; log: {log_path}")
    enc = _run(["ffmpeg", "-y", "-v", "error", "-framerate", str(sp["fps"]), "-start_number", str(start),
                "-i", str(cache / "frame_%04d.png"), "-frames:v", str(end - start + 1), "-c:v", "libx264",
                "-pix_fmt", "yuv420p", "-crf", "16", "-preset", "medium", str(cache / "segment.tmp.mp4")], log_path)
    if enc.returncode:
        raise RuntimeError(f"{name}: encode failed; log: {log_path}")
    (cache / "segment.tmp.mp4").rename(mp4)  # written last: marks the cache entry complete
    for f in want:  # frames are re-derivable; keep the cache small
        f.unlink(missing_ok=True)
    if start == 0 and (cache / "scene.blend").exists():
        shutil.copy(cache / "scene.blend", blend)
    report = json.loads((cache / "report.json").read_text())
    report["wall_seconds"] = round(time.time() - t0, 1)
    (cache / "report.json").write_text(json.dumps(report, indent=2))
    return {**report, **base, "cached": False}


def render_stills(plan: dict, out: Path, frac: float = 0.6) -> list[Path]:
    """One quick path-traced still per scene (540x960) for visual review."""
    blender = BlenderMechanismRunner.get_blender_binary()
    if not blender:
        raise RuntimeError("Blender not found")
    font = next((f for f in FONTS if Path(f).exists()), "")
    stills = []
    for sp in plan["scenes"]:
        d = out / f"{sp['index']:02d}_{sp['id']}"
        d.mkdir(parents=True, exist_ok=True)
        (d / "plan.json").write_text(json.dumps(sp))
        f = int(sp["frames"] * frac)
        cmd = [blender, "-b", "--factory-startup", "--disable-autoexec", "-noaudio", "-P", str(BLENDER_SCRIPT), "--",
               "--plan", str(d / "plan.json"), "--out", str(d), "--quality", "realistic", "--width", "540",
               "--height", "960", "--samples", "12", "--stills", str(f), "--font", font, "--hdri", str(HDRI)]
        if FORCE_CPU:
            cmd.append("--cpu")
        _run(cmd, out / "stills.log", timeout=900)
        png = d / f"still_{f:04d}.png"
        if not png.exists():
            raise RuntimeError(f"still render failed for scene {sp['id']}; see {out / 'stills.log'}")
        stills.append(png)
    return stills


# ── Captions ─────────────────────────────────────────────────────────────

def caption_groups(words: list[dict], max_tokens: int = 6, max_chars: int = 30) -> list[list[int]]:
    groups, cur = [], []
    for i, w in enumerate(words):
        if cur and (w["scene"] != words[cur[0]]["scene"] or len(cur) >= max_tokens
                    or sum(len(words[j]["text"]) + 1 for j in cur) + len(w["text"]) > max_chars):
            groups.append(cur)
            cur = []
        cur.append(i)
        if re.search(r"[.?!,;:]$", w["text"]):
            groups.append(cur)
            cur = []
    return groups + ([cur] if cur else [])


def _font(size: int) -> ImageFont.ImageFont:
    path = next((f for f in FONTS if Path(f).exists()), None)
    return ImageFont.truetype(path, size) if path else ImageFont.load_default()


def draw_caption(words: list[dict], group: list[int], spoken: int, bg: str, note: Optional[str],
                 W: int, H: int) -> tuple[Image.Image, bool]:
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    ink = (27, 29, 34) if bg == "light" else (255, 255, 255)
    overflow = False
    if group:
        items = [(words[i]["text"], words[i].get("key", False), k < spoken) for k, i in enumerate(group) if words[i]["text"]]
        for fs in (int(H * 0.036), int(H * 0.031), int(H * 0.027)):
            font, max_w = _font(fs), W * 0.84
            lines, line, lw = [], [], 0.0
            space = font.getlength(" ")
            for it in items:
                wlen = font.getlength(it[0])
                if line and lw + space + wlen > max_w:
                    lines.append((line, lw))
                    line, lw = [], 0.0
                lw += (space if line else 0) + wlen
                line.append((it, wlen))
            lines.append((line, lw))
            if len(lines) <= 2:
                break
        overflow = len(lines) > 2
        y = H * 0.105
        pad = fs * 0.18
        for line, lw in lines:
            x = (W - lw) / 2
            for (text, is_key, done), wlen in line:
                if is_key and done:
                    d.rounded_rectangle([x - pad, y - pad * 0.6, x + wlen + pad, y + fs * 1.08], radius=pad, fill=ACCENT + (255,))
                    d.text((x, y), text, font=font, fill=(255, 255, 255, 255))
                else:
                    d.text((x, y), text, font=font, fill=ink + ((255,) if done else (70,)))
                x += wlen + font.getlength(" ")
            y += fs * 1.3
    if note:
        f = _font(int(H * 0.017))
        tw = f.getlength(note)
        x0, y0 = (W - tw) / 2, H * 0.80
        d.rounded_rectangle([x0 - 14, y0 - 8, x0 + tw + 14, y0 + H * 0.017 + 10], radius=12,
                            fill=(0, 0, 0, 90) if bg == "light" else (255, 255, 255, 60))
        d.text((x0, y0), note, font=f, fill=(255, 255, 255, 235))
    return img, overflow


def render_captions(plan: dict, spec: VideoSpec, W: int, H: int, out: Path) -> tuple[Path, list[str]]:
    """Word-synced caption overlay as PNG states + an ffconcat timeline."""
    out.mkdir(parents=True, exist_ok=True)
    words, fps = plan["words"], plan["fps"]
    for si, sc in enumerate(spec.scenes):
        idx = [i for i, w in enumerate(words) if w["scene"] == si]
        st = [words[i]["token"] for i in idx]
        for kw in sc.keywords:
            k = phrase_index(st, kw)
            for j in range(k, k + len(tokens(kw))) if k is not None else []:
                words[idx[j]]["key"] = True
    groups = caption_groups(words)
    starts = [words[g[0]]["start"] - 0.05 for g in groups]
    scene_f0 = [s["frame_offset"] for s in plan["scenes"]]
    total = round(plan["duration"] * fps)
    entries, cache, overflow = [], {}, []
    for f in range(total):
        t = f / fps
        si = max(i for i, s0 in enumerate(scene_f0) if s0 <= f)
        g = max((k for k, s0 in enumerate(starts) if s0 <= t), default=None)
        if g is not None:
            last_end = words[groups[g][-1]]["end"] + 0.6
            nxt = starts[g + 1] if g + 1 < len(starts) else 1e9
            if t > min(last_end, nxt) or words[groups[g][0]]["scene"] != si:
                g = None
        spoken = sum(1 for i in groups[g] if words[i]["start"] <= t) if g is not None else 0
        state = (si, g, spoken)
        if state not in cache:
            img, ov = draw_caption(words, groups[g] if g is not None else [], spoken,
                                   plan["scenes"][si]["background"], spec.scenes[si].note, W, H)
            name = f"cap_{len(cache):04d}.png"
            img.save(out / name)
            cache[state] = name
            if ov:
                overflow.append(" ".join(words[i]["text"] for i in groups[g]))
        if entries and entries[-1][0] == cache[state]:
            entries[-1][1] += 1
        else:
            entries.append([cache[state], 1])
    lines = ["ffconcat version 1.0"]
    for name, n in entries:
        lines += [f"file '{name}'", f"duration {n / fps:.6f}"]
    lines.append(f"file '{entries[-1][0]}'")
    (out / "captions.ffconcat").write_text("\n".join(lines) + "\n")
    return out / "captions.ffconcat", overflow


def write_srt(plan: dict, path: Path) -> None:
    words = plan["words"]
    fmt = lambda t: f"{int(t // 3600):02d}:{int(t % 3600 // 60):02d}:{int(t % 60):02d},{int(t % 1 * 1000):03d}"
    rows = []
    for n, g in enumerate(caption_groups(words), 1):
        text = " ".join(words[i]["text"] for i in g if words[i]["text"])
        rows.append(f"{n}\n{fmt(words[g[0]]['start'])} --> {fmt(words[g[-1]]['end'])}\n{text}\n")
    path.write_text("\n".join(rows))


# ── QC ───────────────────────────────────────────────────────────────────

def frame_checks(mp4: Path, fps: int, frames: int, W: int, H: int) -> dict:
    """Black/empty frames and motion (frozen-scene) check on decoded pixels."""
    n = 6
    picks = [round(i * (frames - 1) / (n - 1)) for i in range(n)]
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(mp4), "-vf",
                          f"select='{'+'.join(f'eq(n,{p})' for p in picks)}',scale=180:320", "-fps_mode", "passthrough",
                          "-f", "rawvideo", "-pix_fmt", "gray", "-"], capture_output=True).stdout
    imgs = np.frombuffer(raw, np.uint8).reshape(-1, 320, 180).astype(float)
    if len(imgs) < 2:
        return {"sampled": len(imgs), "min_contrast": 0.0, "mean_motion": 0.0, "empty": True, "frozen": True}
    contrast = [float(im.std()) for im in imgs]
    motion = [float(np.abs(a - b).mean()) for a, b in zip(imgs, imgs[1:])]
    return {"sampled": len(imgs), "min_contrast": round(min(contrast), 2), "mean_motion": round(float(np.mean(motion)), 3),
            "empty": min(contrast) < 3.0, "frozen": max(motion, default=0) < 0.4}


def run_qc(job: Path, plan: dict, final: Path, scenes: list[dict], coverage: float, overflow: list[str],
           W: int, H: int, assets: list[dict], quality: str) -> dict:
    issues = []
    probe = json.loads(_run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height:format=duration",
                             "-of", "json", str(final)]).stdout)
    v = next(s for s in probe["streams"] if s["codec_type"] == "video")
    has_audio = any(s["codec_type"] == "audio" for s in probe["streams"])
    dur = float(probe["format"]["duration"])
    if (v["width"], v["height"]) != (W, H):
        issues.append(f"ERROR dimensions {v['width']}x{v['height']} != {W}x{H}")
    if abs(dur - plan["duration"]) > 0.15:
        issues.append(f"ERROR duration {dur:.2f}s != planned {plan['duration']:.2f}s")
    if not has_audio:
        issues.append("ERROR missing narration audio stream")
    if coverage < 0.8:
        issues.append(f"WARN only {coverage:.0%} of script words were matched in the audio")
    for t in overflow:
        issues.append(f"WARN caption overflow (3+ lines): {t!r}")
    scene_rows, seen = [], set()
    for s in scenes:
        fc = frame_checks(Path(s["mp4"]), plan["fps"], s["frames"], W, H)
        if fc["empty"]:
            issues.append(f"ERROR {s['name']}: empty/flat frame (contrast {fc['min_contrast']})")
        if fc["frozen"] and s["frames"] >= plan["fps"]:
            issues.append(f"ERROR {s['name']}: no visible motion")
        if s["id"] not in seen:  # framing/mesh checks are per scene, not per shard
            seen.add(s["id"])
            for f in (f for f in s["framing"] if not f["ok"]):
                issues.append(f"WARN scene {s['id']}: subject {f['subjects']} leaves safe area by {f['overflow']}")
            if s["empty_meshes"]:
                issues.append(f"ERROR scene {s['id']}: degenerate meshes {s['empty_meshes']}")
        budget = SECONDS_PER_FRAME_BUDGET[quality] * s["frames"]
        if s.get("render_seconds", 0) > budget:
            issues.append(f"WARN {s['name']}: render {s['render_seconds']}s over budget {budget:.0f}s")
        scene_rows.append({"segment": s["name"], "frames": s["frames"], "cached": s.get("cached"),
                           "render_seconds": s.get("render_seconds"), **fc})
    sheet = job / "contact_sheet.jpg"
    _run(["ffmpeg", "-y", "-v", "error", "-i", str(final), "-vf",
          f"fps={12 / max(dur, 1):.4f},scale=270:480,tile=6x2", "-frames:v", "1", str(sheet)])
    report = {"passed": not any(i.startswith("ERROR") for i in issues), "issues": issues,
              "video": {"width": v["width"], "height": v["height"], "duration": round(dur, 3), "audio": has_audio},
              "alignment_coverage": round(coverage, 3), "scenes": scene_rows, "assets": assets,
              "visual_review": "NOT YET INSPECTED — review contact_sheet.jpg (automated checks cannot judge aesthetics)",
              "contact_sheet": str(sheet)}
    (job / "qc_report.json").write_text(json.dumps(report, indent=2))
    return report


# ── Entry point ──────────────────────────────────────────────────────────

def prepare(spec_file: Path, job: Path, duration_seconds: float = 45) -> tuple[VideoSpec, dict, list[dict]]:
    """Validate spec, synthesize + transcribe narration (cached), resolve the frame-exact plan."""
    from engine.edge_voice import VoiceEngine
    from engine.whisper_captions import CaptionGenerator

    spec = VideoSpec.model_validate_json(Path(spec_file).read_text())
    job.mkdir(parents=True, exist_ok=True)
    assets = resolve_assets(spec)
    (job / "scenespec.json").write_text(spec.model_dump_json(indent=2))
    (job / "narration.txt").write_text(spec.script + "\n")
    akey = _sha(spec.script, spec.voice)
    voice, words_json = job / "voice.mp3", job / "words.json"
    if not (words_json.exists() and json.loads(words_json.read_text()).get("key") == akey and voice.exists()):
        VoiceEngine(voice=spec.voice).synthesize(text=spec.script, output_path=voice)
        txn = CaptionGenerator(model_size="base").transcribe(voice)
        words_json.write_text(json.dumps({"key": akey, "words": [[w.word, w.start, w.end] for w in txn.words]}))
    heard = [tuple(w) for w in json.loads(words_json.read_text())["words"]]
    audio_end = _duration(voice)
    if abs(audio_end - duration_seconds) > 0.25 * duration_seconds:
        log.warning("narration is %.1fs, requested %.0fs", audio_end, duration_seconds)
    plan = resolve(spec, heard, audio_end)
    import difflib
    script_toks = tokens(spec.script)
    sm = difflib.SequenceMatcher(None, script_toks, [x for w in heard for x in tokens(w[0])], autojunk=False)
    plan["alignment_coverage"] = sum(b.size for b in sm.get_matching_blocks()) / max(1, len(script_toks))
    plan["assets"] = assets
    (job / "plan.json").write_text(json.dumps(plan, indent=1))
    return spec, plan, assets


def assemble(spec: VideoSpec, plan: dict, segments: list[dict], quality: str, job: Path, final: Path) -> dict:
    """Segments → captions overlay → SFX mix → final MP4 → QC report."""
    from engine.sfx_manager import SFXManager

    W, H = QUALITY[quality]
    voice = job / "voice.mp3"
    concat = job / "segments.txt"
    concat.write_text("".join(f"file '{Path(s['mp4']).resolve()}'\n" for s in segments))
    video_only = job / "video_only.mp4"
    res = _run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(concat), "-c", "copy",
                str(video_only)], job / "logs" / "assemble.log")
    if res.returncode:
        raise RuntimeError(f"segment concat failed; see {job / 'logs' / 'assemble.log'}")
    captions, overflow = render_captions(plan, spec, W, H, job / "captions")
    write_srt(plan, job / "captions.srt")
    events = [((sp["frame_offset"] + a["f0"]) / plan["fps"], a["sfx"])
              for sp in plan["scenes"] for a in sp["actions"] if a["sfx"] and a["index"] == 0]
    cuts = [sp["frame_offset"] / plan["fps"] for sp in plan["scenes"][1:]]
    master = job / "audio_master.aac"
    SFXManager.build_mixed_soundtrack(voice_path=voice, scene_cut_times=cuts, callout_times=[],
                                      total_duration=plan["duration"], output_path=master, events=events)
    final.parent.mkdir(parents=True, exist_ok=True)
    res = _run(["ffmpeg", "-y", "-v", "error", "-i", str(video_only), "-f", "concat", "-safe", "0", "-i", str(captions),
                "-i", str(master), "-filter_complex",
                "[0:v][1:v]overlay=0:0:format=auto:eof_action=pass,format=yuv420p[v]",
                "-map", "[v]", "-map", "2:a", "-c:v", "libx264", "-crf", "18", "-preset", "medium",
                "-profile:v", "high", "-c:a", "copy", "-t", f"{plan['duration']:.3f}", "-movflags", "+faststart",
                str(final)], job / "logs" / "assemble.log")
    if res.returncode:
        raise RuntimeError(f"final mux failed; see {job / 'logs' / 'assemble.log'}")
    qc = run_qc(job, plan, final, segments, plan.get("alignment_coverage", 1.0), overflow, W, H,
                plan.get("assets", []), quality)
    result = {"video": str(final), "scenespec": str(job / "scenespec.json"), "plan": str(job / "plan.json"),
              "narration": str(job / "narration.txt"), "audio": [str(voice), str(master)],
              "subtitles": str(job / "captions.srt"),
              "blender_files": sorted(str(p) for p in (job / "blender").glob("*.blend")),
              "logs": str(job / "logs"), "qc_report": str(job / "qc_report.json"), "contact_sheet": qc["contact_sheet"],
              "qc_passed": qc["passed"], "issues": qc["issues"],
              "segments_cached": sum(bool(s.get("cached")) for s in segments), "segments_total": len(segments)}
    (job / "result.json").write_text(json.dumps(result, indent=2))
    return result


def generate_video(
    topic: str,
    duration_seconds: float = 45,
    aspect_ratio: str = "9:16",
    visual_style: str = "cinematic_3d_educational",
    animation_complexity: str = "high",
    quality: str = "preview",
    budget_mode: str = "free_local",
    spec_path: Optional[Path] = None,
    out_dir: Optional[Path] = None,
    workers: int = 1,
    final_path: Optional[Path] = None,
) -> dict:
    """Generate a narrated 3D educational reel on this machine. Returns paths to every artifact.

    quality: "preview" (540x960 Eevee), "production" (1080x1920 Eevee + motion blur + DOF) or
    "realistic"/"cycles" (1080x1920 path traced, HDRI lighting). Scenes are cached by content
    hash, so a re-run after a crash or an edit re-renders only what changed.
    budget_mode "free_local" is the only mode: nothing here calls a paid service.
    """
    if aspect_ratio != "9:16":
        raise ValueError("only 9:16 is supported (safe areas and captions are tuned for Reels/Shorts/TikTok)")
    if quality not in QUALITY:
        raise ValueError(f"quality must be one of {list(QUALITY)}")
    if budget_mode != "free_local":
        raise ValueError("only budget_mode='free_local' is implemented")
    t0 = time.time()
    spec_file = Path(spec_path) if spec_path else find_spec(topic)
    job = Path(out_dir) if out_dir else ROOT / "export" / "studio" / f"{spec_file.stem}_{quality}"
    spec, plan, _ = prepare(spec_file, job, duration_seconds)
    if spec.style != visual_style:
        raise ValueError(f"spec style {spec.style!r} != requested {visual_style!r}")
    shards = shard_list(plan)  # locally: one segment per scene
    # ponytail: one GPU shared by all workers; >1 mainly helps CPU-bound Cycles.
    with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        segments = list(ex.map(lambda sh: render_shard(plan["scenes"][sh["scene"]], quality, job, sh["start"], sh["end"]),
                               shards))
    result = assemble(spec, plan, segments, quality, job, Path(final_path) if final_path else job / f"{spec_file.stem}.mp4")
    result["timings"] = {"total": round(time.time() - t0, 1)}
    return result
