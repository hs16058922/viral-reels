"""
Centralised application settings loaded from environment / .env file.

Uses ``pydantic-settings`` so every field can be overridden via an
environment variable of the same name.  Defaults are tuned for a
standard 9:16 reel workflow.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal, Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


_PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Global configuration for the Viral Reels Studio engine."""

    model_config = SettingsConfigDict(
        env_file=_PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Directories ─────────────────────────────────────────────────
    OUTPUT_DIR: Path = _PROJECT_ROOT / "export"
    TEMP_DIR: Path = _PROJECT_ROOT / "tmp"
    RAW_FOOTAGE_DIR: Path = _PROJECT_ROOT / "raw-footage"

    # ── FFmpeg ──────────────────────────────────────────────────────
    FFMPEG_PATH: str = "ffmpeg"

    # ── Whisper ─────────────────────────────────────────────────────
    WHISPER_MODEL: Literal["tiny", "base", "small", "medium", "large"] = "base"

    # ── Edge TTS ────────────────────────────────────────────────────
    EDGE_TTS_VOICE: str = "en-US-ChristopherNeural"

    # ── Video output ────────────────────────────────────────────────
    TARGET_WIDTH: int = 1080
    TARGET_HEIGHT: int = 1920
    FPS: int = 30

    # ── Captions ────────────────────────────────────────────────────
    CAPTION_STYLE: str = "bold_pop"

    # ── Gemini / Veo Video Generation ──────────────────────────────
    GEMINI_API_KEY: Optional[str] = None
    GEMINI_VIDEO_MODEL: str = "veo-2.0-generate-001"

    # ── Derived helpers ─────────────────────────────────────────────
    @property
    def project_root(self) -> Path:
        """Return the resolved project root directory."""
        return _PROJECT_ROOT

    @property
    def caption_template_path(self) -> Path:
        """Return the path to the active caption ASS template."""
        return _PROJECT_ROOT / "templates" / "caption_styles" / f"{self.CAPTION_STYLE}.ass"

    @property
    def transition_presets_path(self) -> Path:
        """Return the path to the transition presets JSON."""
        return _PROJECT_ROOT / "templates" / "transitions" / "presets.json"


# Singleton — importable as ``from config.settings import settings``
settings = Settings()
