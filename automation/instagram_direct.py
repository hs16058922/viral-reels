"""
Direct Instagram Reels Publisher via instagrapi.

Simple, direct username + password authentication using Instagram's mobile client.
- No Meta Developer App or Facebook Page required.
- Uploads local MP4 files directly from disk without public hosting.
- Reuses saved session cookies (tmp/ig_session.json) to prevent repeat logins.
"""

import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("viral_reels.instagram_direct")
SESSION_FILE = Path(__file__).resolve().parent.parent / "tmp" / "ig_session.json"


class DirectInstagramPublisher:
    """Direct Instagram client using sessionid or username/password."""

    def __init__(
        self,
        username: Optional[str] = None,
        password: Optional[str] = None,
        sessionid: Optional[str] = None,
    ) -> None:
        self.username = username or os.getenv("INSTAGRAM_USERNAME", "").strip()
        self.password = password or os.getenv("INSTAGRAM_PASSWORD", "").strip()
        self.sessionid = sessionid or os.getenv("INSTAGRAM_SESSIONID", "").strip()
        self._client = None

    def is_configured(self) -> bool:
        """Check if sessionid or credentials are provided."""
        return bool(self.sessionid or (self.username and self.password))

    def get_client(self):
        """Initialize and authenticate the instagrapi client with session caching."""
        if self._client is not None:
            return self._client

        from instagrapi import Client

        cl = Client()
        cl.delay_range = [2, 5]

        SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)

        # 1. First priority: Check if sessionid cookie is provided in .env
        if self.sessionid:
            try:
                logger.info("Authenticating via INSTAGRAM_SESSIONID cookie...")
                cl.login_by_sessionid(self.sessionid)
                cl.dump_settings(SESSION_FILE)
                logger.info("✅ Logged in successfully via sessionid! (User ID: %s)", cl.user_id)
                self._client = cl
                return cl
            except Exception as e:
                logger.warning("Sessionid login failed: %s. Falling back to saved session/password...", e)

        # 2. Second priority: Existing session cache on disk
        if SESSION_FILE.exists():
            try:
                logger.info("Found existing Instagram session in %s. Loading...", SESSION_FILE.name)
                cl.load_settings(SESSION_FILE)
                cl.login(self.username, self.password)
                logger.info("✅ Resumed session for @%s successfully!", self.username)
                self._client = cl
                return cl
            except Exception as e:
                logger.warning("Session resume failed (%s). Performing fresh login...", e)

        # 3. Third priority: Fresh login with username & password
        if not (self.username and self.password):
            raise ValueError(
                "Instagram credentials missing. Set INSTAGRAM_SESSIONID or "
                "INSTAGRAM_USERNAME and INSTAGRAM_PASSWORD in your .env file."
            )

        logger.info("Logging in to Instagram as @%s...", self.username)
        cl.login(self.username, self.password)
        cl.dump_settings(SESSION_FILE)
        logger.info("✅ Logged in and saved session to %s", SESSION_FILE.name)
        self._client = cl
        return cl

    def publish_reel(
        self,
        video_path: Path,
        caption: str,
        thumbnail_path: Optional[Path] = None,
    ) -> Dict[str, Any]:
        """Upload an MP4 video directly as an Instagram Reel.

        Args:
            video_path: Path to the local 1080x1920 MP4 file.
            caption: Viral caption including bullet points & hashtags.
            thumbnail_path: Optional cover image for the reel.

        Returns:
            Dict containing post metadata, ID, and live permalink.
        """
        video_path = Path(video_path)
        if not video_path.exists():
            raise FileNotFoundError(f"Video file not found at {video_path}")

        cl = self.get_client()

        logger.info("📤 Uploading Reel '%s' directly to @%s...", video_path.name, self.username)
        
        media = cl.clip_upload(
            path=video_path,
            caption=caption,
            thumbnail=thumbnail_path if thumbnail_path and thumbnail_path.exists() else None,
        )

        permalink = f"https://www.instagram.com/reel/{media.code}/"
        logger.info("🎉 SUCCESS! Reel is live on Instagram:")
        logger.info("🔗 %s", permalink)

        # Refresh saved session cookies
        cl.dump_settings(SESSION_FILE)

        return {
            "status": "success",
            "media_id": media.id,
            "media_code": media.code,
            "permalink": permalink,
            "user": self.username,
        }
