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

## License

MIT
