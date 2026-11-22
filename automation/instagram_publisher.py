"""
Instagram Graph API Reels Publisher.

Official, safe, ban-resistant publisher using Meta's Content Publishing API.
Handles:
1. Public video staging (upload to temporary hosting or direct URL)
2. Media container initialization (media_type=REELS)
3. Container readiness polling (waiting for Meta's encoding pipeline)
4. Final publishing and permalink extraction
"""

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
import urllib.parse
import urllib.request
import requests
from dotenv import load_dotenv

load_dotenv()

from config.settings import settings

logger = logging.getLogger("viral_reels.instagram")


class InstagramPublisher:
    """Publishes reels to Instagram using the official Meta Graph API."""

    GRAPH_API_VERSION = "v19.0"
    GRAPH_API_BASE = f"https://graph.facebook.com/{GRAPH_API_VERSION}"

    def __init__(
        self,
        access_token: Optional[str] = None,
        ig_user_id: Optional[str] = None,
    ) -> None:
        self.access_token = access_token or os.getenv("INSTAGRAM_ACCESS_TOKEN", "")
        self.ig_user_id = ig_user_id or os.getenv("INSTAGRAM_ACCOUNT_ID", "")

    def is_configured(self) -> bool:
        """Check if Instagram API credentials are present."""
        return bool(self.access_token and self.ig_user_id)

    # ── Temporary Video Hosting Helper ──────────────────────────────

    @staticmethod
    def upload_to_temp_hosting(local_path: Path) -> str:
        """Upload local MP4 to Catbox / Filebin temporary hosting for Meta ingestion.
        
        Meta Graph API requires a publicly accessible HTTPS URL to ingest video.
        """
        logger.info("Uploading %s to temporary public storage for Meta ingestion...", local_path.name)
        
        # 1. Try Catbox.moe (fast, reliable, free direct mp4 url)
        try:
            with open(local_path, "rb") as f:
                resp = requests.post(
                    "https://catbox.moe/user/api.php",
                    data={"reqtype": "fileupload"},
                    files={"fileToUpload": (local_path.name, f, "video/mp4")},
                    timeout=120,
                )
            if resp.status_code == 200 and resp.text.startswith("http"):
                public_url = resp.text.strip()
                logger.info("Temporary public video URL: %s", public_url)
                return public_url
        except Exception as e:
            logger.warning("Catbox upload failed: %s. Trying fallback...", e)

        # 2. Fallback: Transfer.sh
        try:
            with open(local_path, "rb") as f:
                resp = requests.put(
                    f"https://transfer.sh/{local_path.name}",
                    data=f,
                    timeout=120,
                )
            if resp.status_code in (200, 201) and resp.text.startswith("http"):
                public_url = resp.text.strip()
                logger.info("Fallback public video URL: %s", public_url)
                return public_url
        except Exception as e:
            logger.error("Temporary hosting upload failed: %s", e)

        raise RuntimeError(
            "Could not stage video to public URL. Please configure a cloud storage bucket "
            "(AWS S3, Cloudflare R2, or Supabase Storage) in .env."
        )

    def create_resumable_container(
        self,
        file_size: int,
        caption: str,
        share_to_feed: bool = True,
    ) -> Tuple[str, str]:
        """Step 1: Initialize a direct resumable upload session on Meta."""
        if not self.is_configured():
            raise ValueError("Instagram credentials missing in .env.")

        url = f"{self.GRAPH_API_BASE}/{self.ig_user_id}/media"
        payload = {
            "upload_type": "resumable",
            "media_type": "REELS",
            "caption": caption,
            "share_to_feed": "true" if share_to_feed else "false",
            "thumb_offset": "100",  # Flashy cover frame at 100ms
            "access_token": self.access_token,
        }

        resp = requests.post(url, data=payload, timeout=30)
        data = resp.json()

        if "id" not in data or "uri" not in data:
            error_msg = data.get("error", {}).get("message", "Unknown error")
            raise RuntimeError(f"Meta Graph API error creating resumable session: {error_msg} (Response: {data})")

        container_id = data["id"]
        upload_uri = data["uri"]
        logger.info("Initialized Meta direct upload: container=%s, uri=%s", container_id, upload_uri)
        return container_id, upload_uri

    def upload_binary_to_meta(
        self,
        upload_uri: str,
        video_path: Path,
    ) -> None:
        """Step 2: Stream raw video bytes directly to Meta's rupload servers."""
        file_size = video_path.stat().st_size
        logger.info("Streaming %s (%.2f MB) directly to Meta rupload servers...", video_path.name, file_size / (1024 * 1024))

        headers = {
            "Authorization": f"OAuth {self.access_token}",
            "offset": "0",
            "file_size": str(file_size),
            "Content-Type": "application/octet-stream",
        }

        with open(video_path, "rb") as f:
            resp = requests.post(upload_uri, headers=headers, data=f, timeout=300)

        data = resp.json() if resp.text else {}
        if resp.status_code not in (200, 201) or data.get("success") is False:
            raise RuntimeError(f"Direct video upload to Meta failed (HTTP {resp.status_code}): {resp.text}")

        logger.info("✅ Direct binary upload to Meta completed successfully!")

    # ── Step 3: Poll Container Status ───────────────────────────────

    def wait_for_container_ready(
        self,
        container_id: str,
        max_wait_seconds: int = 180,
        poll_interval: int = 5,
    ) -> None:
        """Poll the container until Meta finishes processing the video."""
        url = f"{self.GRAPH_API_BASE}/{container_id}"
        params = {
            "fields": "status_code,status",
            "access_token": self.access_token,
        }

        start_time = time.time()
        logger.info("Waiting for Meta to process Reel container %s...", container_id)

        while time.time() - start_time < max_wait_seconds:
            resp = requests.get(url, params=params, timeout=20)
            data = resp.json()
            status_code = data.get("status_code", "UNKNOWN")

            if status_code == "FINISHED":
                logger.info("🎉 Container %s is FINISHED and ready to publish!", container_id)
                return
            elif status_code == "ERROR":
                err = data.get("status", "Unknown processing error")
                raise RuntimeError(f"Meta failed to process Reel container {container_id}: {err}")
            elif status_code == "EXPIRED":
                raise TimeoutError(f"Container {container_id} expired before publishing.")

            logger.info("Status: %s... waiting %ds", status_code, poll_interval)
            time.sleep(poll_interval)

        raise TimeoutError(f"Timed out after {max_wait_seconds}s waiting for container {container_id}.")

    # ── Step 4: Publish Container ───────────────────────────────────

    def publish_container(self, container_id: str) -> str:
        """Publish the ready container to the Instagram profile and Reels tab."""
        url = f"{self.GRAPH_API_BASE}/{self.ig_user_id}/media_publish"
        payload = {
            "creation_id": container_id,
            "access_token": self.access_token,
        }

        resp = requests.post(url, data=payload, timeout=30)
        data = resp.json()

        if "id" not in data:
            error_msg = data.get("error", {}).get("message", "Publish error")
            raise RuntimeError(f"Meta error publishing reel: {error_msg} (Response: {data})")

        media_id = data["id"]
        logger.info("Successfully published Reel! Media ID: %s", media_id)
        return media_id

    # ── Step 5: Get Permalink ───────────────────────────────────────

    def get_permalink(self, media_id: str) -> str:
        """Fetch the public Instagram permalink for the published reel."""
        url = f"{self.GRAPH_API_BASE}/{media_id}"
        params = {
            "fields": "permalink,timestamp",
            "access_token": self.access_token,
        }
        try:
            resp = requests.get(url, params=params, timeout=15)
            data = resp.json()
            return data.get("permalink", f"https://www.instagram.com/reel/{media_id}")
        except Exception:
            return f"https://www.instagram.com/reel/{media_id}"

    # ── Full Publish Workflow ───────────────────────────────────────

    def publish_reel(
        self,
        video_path_or_url: str,
        caption: str,
        share_to_feed: bool = True,
    ) -> Dict[str, Any]:
        """Complete direct upload workflow without requiring external hosting."""
        local_path = Path(video_path_or_url)
        if not local_path.exists():
            raise FileNotFoundError(f"Video file not found: {local_path}")

        file_size = local_path.stat().st_size

        # 1. Initialize direct resumable session
        container_id, upload_uri = self.create_resumable_container(
            file_size=file_size,
            caption=caption,
            share_to_feed=share_to_feed,
        )

        # 2. Upload raw binary directly to Meta
        self.upload_binary_to_meta(upload_uri, local_path)

        # 3. Wait for Meta processing
        self.wait_for_container_ready(container_id)

        # 4. Publish
        media_id = self.publish_container(container_id)

        # 5. Get permalink
        permalink = self.get_permalink(media_id)

        return {
            "status": "success",
            "media_id": media_id,
            "container_id": container_id,
            "permalink": permalink,
        }
