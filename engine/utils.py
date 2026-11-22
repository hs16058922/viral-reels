"""
Shared utility functions used across all engine modules.

Provides structured logging, directory management, media validation,
temp-file helpers, timestamp formatting, and a safe ``ffmpeg`` subprocess
wrapper.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path
from typing import List, Optional, Sequence

from rich.logging import RichHandler

from config.settings import settings

logger = logging.getLogger("viral_reels")

# Media extensions considered valid by ``validate_media``.
_VALID_VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"}
_VALID_AUDIO_EXTS = {".mp3", ".wav", ".aac", ".ogg", ".flac", ".m4a"}
_VALID_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tiff"}
VALID_MEDIA_EXTS = _VALID_VIDEO_EXTS | _VALID_AUDIO_EXTS | _VALID_IMAGE_EXTS


def setup_logging(level: int = logging.INFO) -> None:
    """Configure structured logging with Rich console handler.

    Args:
        level: The root logging level (e.g. ``logging.DEBUG``).
    """
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[
            RichHandler(
                rich_tracebacks=True,
                tracebacks_show_locals=False,
                show_path=False,
            )
        ],
    )
    logger.setLevel(level)


def ensure_dirs(*paths: Path) -> None:
    """Create directories if they do not already exist.

    Args:
        *paths: One or more ``Path`` objects to create.
    """
    for p in paths:
        p.mkdir(parents=True, exist_ok=True)
        logger.debug("Ensured directory: %s", p)


def validate_media(path: Path) -> Path:
    """Check that *path* exists and has a recognised media extension.

    Args:
        path: Filesystem path to validate.

    Returns:
        The resolved ``Path`` if valid.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the file extension is not a known media type.
    """
    path = Path(path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Media file not found: {path}")
    if path.suffix.lower() not in VALID_MEDIA_EXTS:
        raise ValueError(
            f"Unsupported media extension '{path.suffix}'. "
            f"Valid: {sorted(VALID_MEDIA_EXTS)}"
        )
    return path


def get_temp_path(filename: str) -> Path:
    """Return a path inside the project ``tmp/`` directory.

    The directory is created automatically if it does not exist.

    Args:
        filename: Basename for the temporary file.

    Returns:
        Full ``Path`` to the temp file.
    """
    ensure_dirs(settings.TEMP_DIR)
    return settings.TEMP_DIR / filename


def cleanup_temp() -> None:
    """Remove all contents of the ``tmp/`` working directory."""
    temp = settings.TEMP_DIR
    if temp.exists():
        shutil.rmtree(temp)
        temp.mkdir(parents=True, exist_ok=True)
        logger.info("Cleaned temp directory: %s", temp)


def format_timestamp(seconds: float) -> str:
    """Convert a float of seconds to SRT timestamp format.

    Args:
        seconds: Time in seconds (e.g. ``63.250``).

    Returns:
        SRT-formatted string ``HH:MM:SS,mmm``.

    Example:
        >>> format_timestamp(63.25)
        '00:01:03,250'
    """
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int(round((seconds - int(seconds)) * 1000))
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def format_ass_timestamp(seconds: float) -> str:
    """Convert a float of seconds to ASS timestamp format.

    Args:
        seconds: Time in seconds.

    Returns:
        ASS-formatted string ``H:MM:SS.cc`` (centiseconds).
    """
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    centis = int(round((seconds - int(seconds)) * 100))
    return f"{hours}:{minutes:02d}:{secs:02d}.{centis:02d}"


def run_ffmpeg(
    args: Sequence[str],
    *,
    check: bool = True,
    capture_output: bool = True,
    timeout: Optional[int] = None,
) -> subprocess.CompletedProcess[str]:
    """Execute an ``ffmpeg`` command via subprocess.

    The ``ffmpeg`` binary path is read from settings.  ``-y`` (overwrite)
    is prepended automatically.

    Args:
        args: Arguments to pass **after** the ``ffmpeg`` binary name.
        check: Raise ``subprocess.CalledProcessError`` on non-zero exit.
        capture_output: Capture stdout and stderr.
        timeout: Timeout in seconds.

    Returns:
        The ``CompletedProcess`` result.

    Raises:
        FileNotFoundError: If ffmpeg is not found on the system.
        subprocess.CalledProcessError: If ffmpeg exits with an error
            and *check* is ``True``.
    """
    cmd: List[str] = [settings.FFMPEG_PATH, "-y", *args]
    logger.debug("ffmpeg cmd: %s", " ".join(cmd))

    try:
        result = subprocess.run(
            cmd,
            check=check,
            capture_output=capture_output,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError:
        logger.error(
            "ffmpeg binary not found at '%s'. "
            "Install ffmpeg or set FFMPEG_PATH in .env.",
            settings.FFMPEG_PATH,
        )
        raise
    except subprocess.CalledProcessError as exc:
        logger.error("ffmpeg failed (exit %d):\n%s", exc.returncode, exc.stderr)
        raise

    return result
