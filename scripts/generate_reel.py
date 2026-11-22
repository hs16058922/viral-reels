#!/usr/bin/env python3
"""
CLI entry point for the Viral Reels Studio pipeline.

Usage::

    python scripts/generate_reel.py --input raw-footage/clip.mp4 \\
        --script "Check out this product!" --style bold_pop \\
        --output export/my_reel.mp4

Run ``python scripts/generate_reel.py --help`` for all options.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# Ensure the project root is on sys.path so config/engine are importable.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from config.settings import settings
from engine.pipeline import PipelineConfig, ReelPipeline
from engine.utils import setup_logging


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser."""
    parser = argparse.ArgumentParser(
        prog="generate_reel",
        description="Viral Reels Studio — generate a short-form reel from footage and/or a script.",
    )
    parser.add_argument(
        "--input", "-i",
        type=Path,
        default=None,
        help="Path to input video file. If omitted, the first video in raw-footage/ is used.",
    )
    parser.add_argument(
        "--script", "-s",
        type=str,
        default=None,
        help="Voiceover script text. Triggers TTS synthesis.",
    )
    parser.add_argument(
        "--voice", "-v",
        type=str,
        default=None,
        help=f"Edge TTS voice name (default: {settings.EDGE_TTS_VOICE}).",
    )
    parser.add_argument(
        "--style",
        type=str,
        default=None,
        help=f"Caption style template name (default: {settings.CAPTION_STYLE}).",
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=None,
        help="Output file path (default: export/reel_final.mp4).",
    )
    parser.add_argument(
        "--no-voice",
        action="store_true",
        help="Skip voiceover generation even if --script is provided.",
    )
    parser.add_argument(
        "--no-captions",
        action="store_true",
        help="Skip caption generation.",
    )
    parser.add_argument(
        "--cuts",
        type=float,
        nargs="*",
        default=None,
        help="Cut points as pairs of start/end seconds (e.g. 0 5 8 15).",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug-level logging.",
    )
    return parser


def main() -> None:
    """Parse arguments and run the pipeline."""
    parser = build_parser()
    args = parser.parse_args()

    import logging
    setup_logging(level=logging.DEBUG if args.debug else logging.INFO)

    config = PipelineConfig(
        input_path=args.input,
        script=args.script,
        voice=args.voice,
        caption_style=args.style,
        output_path=args.output,
        skip_voice=args.no_voice,
        skip_captions=args.no_captions,
        cut_points=args.cuts,
    )

    pipeline = ReelPipeline()
    t0 = time.perf_counter()

    try:
        result = pipeline.run(config)
    except Exception as exc:
        logging.getLogger("viral_reels").error("Pipeline failed: %s", exc, exc_info=True)
        sys.exit(1)

    total = time.perf_counter() - t0
    print("\n" + "=" * 60)
    print("✅  Reel generated successfully!")
    print(f"   Output : {result.final_output_path}")
    print(f"   Total  : {total:.2f}s")
    print("-" * 60)
    for step, dur in result.timings.items():
        if step != "total":
            print(f"   {step:<20s} {dur:.2f}s")
    print("=" * 60)


if __name__ == "__main__":
    main()
