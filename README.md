# Viral Reels Studio 🎬

A production-grade Python video engine for creating viral short-form reels with AI-powered voiceover, word-level captions, motion graphics, and dynamic editing.

## Features

- **Edge TTS Voiceover** — Microsoft Edge neural voices with word-level timing
- **Whisper Captions** — OpenAI Whisper transcription → SRT / ASS with viral word-highlight style
- **Motion Graphics** — Pillow-based title cards, lower thirds, and animated text sequences
- **Dynamic Cuts** — FFmpeg-powered trimming, transitions (xfade), speed ramping, and 9:16 reframing
- **Full Pipeline** — One command from script → finished reel

## Project Structure

```
viral-reels-studio/
├── config/settings.py          # Pydantic settings (all configurable via .env)
├── engine/
│   ├── pipeline.py             # ReelPipeline orchestrator
│   ├── hyperframes.py          # Motion graphics renderer
│   ├── ffmpeg_cuts.py          # FFmpeg wrapper
│   ├── whisper_captions.py     # Whisper → SRT/ASS captions
│   ├── edge_voice.py           # Edge TTS synthesis
│   └── utils.py                # Shared utilities
├── templates/                  # Caption styles & transition presets
├── scripts/
│   ├── generate_reel.py        # CLI entry point
│   └── test_engines.py         # Smoke tests
├── raw-footage/                # Drop your source clips here
├── export/                     # Finished reels land here
└── tmp/                        # Working directory (gitignored)
```

## Quick Start

### 1. Prerequisites

- **Python 3.10+**
- **ffmpeg** installed and on `PATH` ([download](https://ffmpeg.org/download.html))

### 2. Install

```bash
# Clone and set up
cp .env.example .env        # Adjust settings if needed

# Using Make
make install

# Or manually
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Verify

```bash
make test
# or
python scripts/test_engines.py
```

### 4. Generate a Reel

```bash
# From a script (generates voice + captions automatically)
python scripts/generate_reel.py \
  --input raw-footage/clip.mp4 \
  --script "Check out this amazing product!" \
  --output export/my_reel.mp4

# Skip voiceover, just add captions to existing audio
python scripts/generate_reel.py \
  --input raw-footage/clip.mp4 \
  --no-voice \
  --style minimal

# With custom cuts (keep seconds 0-5 and 8-15)
python scripts/generate_reel.py \
  --input raw-footage/clip.mp4 \
  --script "Wow!" \
  --cuts 0 5 8 15
```

### 5. Use as a Library

```python
from engine.pipeline import ReelPipeline, PipelineConfig

pipeline = ReelPipeline()
result = pipeline.run(PipelineConfig(
    script="This product is incredible!",
    input_path=Path("raw-footage/demo.mp4"),
    output_path=Path("export/demo_reel.mp4"),
    caption_style="bold_pop",
))

print(f"Done in {result.timings['total']:.1f}s → {result.final_output_path}")
```

## Configuration

All settings are defined in `config/settings.py` and can be overridden via `.env`:

| Variable | Default | Description |
|---|---|---|
| `OUTPUT_DIR` | `export` | Where finished reels are saved |
| `TEMP_DIR` | `tmp` | Working directory for intermediates |
| `RAW_FOOTAGE_DIR` | `raw-footage` | Source clips directory |
| `FFMPEG_PATH` | `ffmpeg` | Path to ffmpeg binary |
| `WHISPER_MODEL` | `base` | Whisper model size |
| `EDGE_TTS_VOICE` | `en-US-ChristopherNeural` | Default TTS voice |
| `TARGET_WIDTH` | `1080` | Output width (px) |
| `TARGET_HEIGHT` | `1920` | Output height (px) |
| `FPS` | `30` | Output framerate |
| `CAPTION_STYLE` | `bold_pop` | Caption template name |

## Caption Styles

- **`bold_pop`** — Large Impact font, white text, black outline, yellow word highlight. The viral look.
- **`minimal`** — Clean Arial, smaller text, subtle shadow. Professional and understated.

## Transition Presets

Defined in `templates/transitions/presets.json`. Available: `fade`, `wipeleft`, `slideup`, `circleopen`, `radial`, `dissolve`, `pixelize`, and more.

## 3D Animation Studio (SceneSpec v2)

`engine/studio/` turns a topic into a narrated, captioned **real 3D** vertical reel:
independently animated procedural parts (meshing gear trains, rotors, cutaway shells,
flow particles, valves), narration-synced timing, and an auto-framing camera.

```bash
make studio TOPIC="How does a mechanical watch work?" QUALITY=preview     # 540x960, ~10 min
make studio TOPIC="How does a jet engine work?" QUALITY=production        # 1080x1920 + motion blur
python -m engine.studio --schema                                          # SceneSpec JSON schema
```

```python
from engine.studio import generate_video
result = generate_video(topic="How does a mechanical watch work?", quality="preview")
```

How it works:

1. **SceneSpec** (`engine/studio/specs/*.json`, schema in `spec.py`) — pure data. Objects are
   whitelisted procedural kinds; actions (`spin`, `tick`, `cycle`, `explode`, `pop_in`, `highlight`,
   `fade`, …) are anchored to **narration phrases** (`"at": "escape wheel"`), not frames.
   No spec ever executes code in Blender — that is the sandbox for AI-authored specs.
2. **Narration** — EdgeTTS voice, Whisper word timings, `difflib` alignment back to the script.
   Phrase anchors become frames, so scenes re-time automatically when the voice changes.
3. **Blender** (`blender_scene.py`, headless, `--factory-startup --disable-autoexec`) builds and
   keyframes each scene. Meshing gears are placed and coupled by drivers with exact tooth ratios.
   The camera auto-fits each shot's subjects into the Instagram safe area and repairs overflow
   before rendering.
4. **Cache/resume** — each scene is keyed by a hash of its resolved plan + quality + renderer
   source under `tmp/studio_cache/`; interrupted renders resume frame-by-frame.
5. **Assembly + QC** — word-synced captions (Pillow overlay), SFX at animation events,
   FFmpeg mux, then `qc_report.json` (dimensions, duration, audio, alignment coverage, framing,
   empty/frozen scenes, caption overflow, render budget) and a `contact_sheet.jpg` for visual review.

Artifacts land in `export/studio/<topic>_<quality>/`: final MP4, `scenespec.json`, resolved
`plan.json`, `narration.txt`, `voice.mp3`, `audio_master.aac`, `captions.srt`, per-scene `.blend`
files, `logs/`, `qc_report.json`, `contact_sheet.jpg`.

Quality presets: `preview` (540x960 Eevee), `production` (1080x1920 Eevee, motion blur, DOF),
`realistic` (1080x1920 Cycles path tracing, CC0 studio HDRI, surface micro-detail, SSS tissue, DOF).
Requires Blender 4.2+ (tested on 5.3).

### Automated publishing (GitHub Actions, free)

`.github/workflows/reels_publisher.yml` runs 3x daily and only ever posts studio reels:

1. **prepare** — `automation/studio_ci.py` picks the next topic: a pre-rendered `ready` video, else a topic
   with an approved SceneSpec (`"spec": "<name>"` in `topics.json`, or an AI draft in
   `engine/studio/specs/generated/` whose `.review.json` passed). Otherwise the **AI director**
   (Gemini free tier) drafts one: schema validation → density lint → still renders → vision review →
   revision. Drafts that never score well enough are parked as `needs_spec` instead of posted.
2. **render** — the reel is split into ~60-frame shards rendered with Cycles on up to 20 CPU runners in
   parallel (~1 h wall time). Each shard is cached by content hash, so a re-run resumes.
3. **publish** — segments are assembled, captioned, mixed and QC'd. Only a QC pass is posted, through the
   existing `automation/scheduler.py --now --topic <id>` route; queue/history are committed back.

Costs: public-repo Actions minutes are free; Blender, FFmpeg, Whisper and the HDRI are free/open; EdgeTTS
is free. The only external API is Gemini (director/reviewer) — keep billing **disabled** on that Google
Cloud project so the free tier can never charge. Pushing to the `studio-ci` branch runs the whole
render+assemble pipeline without posting.

New topics: write a SceneSpec JSON (any LLM can target `--schema`; validation rejects unknown kinds,
params, targets and phrases that are not in the narration). Imported models go in
`assets/models/` with a `manifest.json` entry (`file`, `license`, `source`); only open licenses
(CC0, CC-BY, MIT, Apache-2.0, self-made) are accepted.

## License

MIT
