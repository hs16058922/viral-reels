#!/usr/bin/env python3
"""
Smoke tests for each engine module.

Verifies that all classes can be imported and instantiated, checks for
ffmpeg availability, and performs lightweight validation of Edge TTS
and Whisper readiness.

Usage::

    python scripts/test_engines.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# Ensure the project root is on sys.path.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


_PASS = "✅"
_FAIL = "❌"
_WARN = "⚠️ "

_results: list[tuple[str, bool, str]] = []


def _record(name: str, passed: bool, detail: str = "") -> None:
    _results.append((name, passed, detail))
    icon = _PASS if passed else _FAIL
    suffix = f" — {detail}" if detail else ""
    print(f"  {icon}  {name}{suffix}")


def test_config() -> None:
    """Import and instantiate Settings."""
    try:
        from config.settings import Settings, settings
        assert isinstance(settings.TARGET_WIDTH, int)
        _record("config.settings", True, f"TARGET={settings.TARGET_WIDTH}x{settings.TARGET_HEIGHT}")
    except Exception as exc:
        _record("config.settings", False, str(exc))


def test_utils() -> None:
    """Import engine.utils and verify key functions exist."""
    try:
        from engine.utils import (
            setup_logging,
            ensure_dirs,
            validate_media,
            get_temp_path,
            cleanup_temp,
            format_timestamp,
            run_ffmpeg,
        )
        assert format_timestamp(63.25) == "00:01:03,250"
        _record("engine.utils", True, "format_timestamp OK")
    except Exception as exc:
        _record("engine.utils", False, str(exc))


def test_ffmpeg_available() -> None:
    """Check that ffmpeg and ffprobe are on PATH."""
    for binary in ("ffmpeg", "ffprobe"):
        try:
            result = subprocess.run(
                [binary, "-version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            version_line = result.stdout.split("\n")[0] if result.stdout else "unknown"
            _record(f"{binary} available", result.returncode == 0, version_line)
        except FileNotFoundError:
            _record(f"{binary} available", False, "NOT FOUND — install ffmpeg")
        except Exception as exc:
            _record(f"{binary} available", False, str(exc))


def test_dynamic_cutter() -> None:
    """Instantiate DynamicCutter."""
    try:
        from engine.ffmpeg_cuts import DynamicCutter
        cutter = DynamicCutter()
        assert cutter is not None
        _record("engine.ffmpeg_cuts.DynamicCutter", True)
    except Exception as exc:
        _record("engine.ffmpeg_cuts.DynamicCutter", False, str(exc))


def test_hyperframe_renderer() -> None:
    """Instantiate HyperframeRenderer and generate a test frame."""
    try:
        from engine.hyperframes import HyperframeRenderer
        renderer = HyperframeRenderer()
        frame = renderer.create_text_frame("TEST", animation_type="fade_in")
        assert frame.size == (1080, 1920)
        _record("engine.hyperframes.HyperframeRenderer", True, f"frame={frame.size}")
    except Exception as exc:
        _record("engine.hyperframes.HyperframeRenderer", False, str(exc))


def test_caption_generator() -> None:
    """Instantiate CaptionGenerator (does NOT load Whisper model)."""
    try:
        from engine.whisper_captions import CaptionGenerator
        gen = CaptionGenerator()
        assert gen.model_size == "base"
        _record("engine.whisper_captions.CaptionGenerator", True, f"model={gen.model_size}")
    except Exception as exc:
        _record("engine.whisper_captions.CaptionGenerator", False, str(exc))


def test_voice_engine() -> None:
    """Instantiate VoiceEngine."""
    try:
        from engine.edge_voice import VoiceEngine
        ve = VoiceEngine()
        assert ve.voice == "en-US-ChristopherNeural"
        _record("engine.edge_voice.VoiceEngine", True, f"voice={ve.voice}")
    except Exception as exc:
        _record("engine.edge_voice.VoiceEngine", False, str(exc))


def test_edge_tts_voices() -> None:
    """List Edge TTS voices (requires network)."""
    try:
        from engine.edge_voice import VoiceEngine
        ve = VoiceEngine()
        voices = ve.list_voices("en")
        _record("edge-tts voice listing", len(voices) > 0, f"{len(voices)} English voices found")
    except Exception as exc:
        _record("edge-tts voice listing", False, f"{_WARN} {exc} (network required)")


def test_whisper_importable() -> None:
    """Check that the whisper package can be imported."""
    try:
        import whisper
        _record("whisper importable", True, f"version={getattr(whisper, '__version__', '?')}")
    except ImportError:
        _record("whisper importable", False, "openai-whisper not installed")
    except Exception as exc:
        _record("whisper importable", False, str(exc))


def test_pipeline() -> None:
    """Instantiate ReelPipeline."""
    try:
        from engine.pipeline import ReelPipeline
        pipeline = ReelPipeline()
        assert pipeline is not None
        _record("engine.pipeline.ReelPipeline", True)
    except Exception as exc:
        _record("engine.pipeline.ReelPipeline", False, str(exc))


def test_templates_exist() -> None:
    """Verify template files are present."""
    templates = [
        _PROJECT_ROOT / "templates" / "caption_styles" / "bold_pop.ass",
        _PROJECT_ROOT / "templates" / "caption_styles" / "minimal.ass",
        _PROJECT_ROOT / "templates" / "transitions" / "presets.json",
    ]
    for t in templates:
        _record(f"template: {t.name}", t.is_file(), str(t.relative_to(_PROJECT_ROOT)))


def main() -> None:
    """Run all smoke tests."""
    print("=" * 60)
    print("Viral Reels Studio — Engine Smoke Tests")
    print("=" * 60)
    print()

    test_config()
    test_utils()
    test_ffmpeg_available()
    test_dynamic_cutter()
    test_hyperframe_renderer()
    test_caption_generator()
    test_voice_engine()
    test_edge_tts_voices()
    test_whisper_importable()
    test_pipeline()
    test_templates_exist()

    print()
    print("-" * 60)
    passed = sum(1 for _, ok, _ in _results if ok)
    total = len(_results)
    failed = total - passed
    print(f"Results: {passed}/{total} passed", end="")
    if failed:
        print(f", {failed} failed")
    else:
        print(" — all clear! 🎉")
    print("=" * 60)

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
