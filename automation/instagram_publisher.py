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
        """Upload local MP4 to temporary public hosting for Meta ingestion.
        
        Meta Graph API requires a publicly accessible HTTPS URL when direct rupload
        encounters strict ingestion timeouts or ProcessingFailedError.
        """
        logger.info("Uploading %s to temporary public storage for Meta ingestion...", local_path.name)
        
        # 1. Try Catbox.moe (fast, reliable direct mp4 URL)
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
                logger.info("✅ Staged to Catbox: %s", public_url)
                return public_url
        except Exception as e:
            logger.warning("Catbox upload failed: %s. Trying TmpFiles...", e)

        # 2. Try TmpFiles.org (direct mp4 link via dl path)
        try:
            with open(local_path, "rb") as f:
                resp = requests.post(
                    "https://tmpfiles.org/api/v1/upload",
                    files={"file": (local_path.name, f, "video/mp4")},
                    timeout=120,
                )
            if resp.status_code == 200:
                data = resp.json()
                page_url = data.get("data", {}).get("url", "")
                if page_url:
                    dl_url = page_url.replace("tmpfiles.org/", "tmpfiles.org/dl/")
                    logger.info("✅ Staged to TmpFiles: %s", dl_url)
                    return dl_url
        except Exception as e:
            logger.warning("TmpFiles upload failed: %s. Trying Transfer.sh...", e)

        # 3. Fallback: Transfer.sh
        try:
            with open(local_path, "rb") as f:
                resp = requests.put(
                    f"https://transfer.sh/{local_path.name}",
                    data=f,
                    timeout=120,
                )
            if resp.status_code in (200, 201) and resp.text.startswith("http"):
                public_url = resp.text.strip()
                logger.info("✅ Staged to Transfer.sh: %s", public_url)
                return public_url
        except Exception as e:
            logger.warning("Transfer.sh upload failed: %s. Trying 0x0.st...", e)

        # 4. Fallback: 0x0.st
        try:
            with open(local_path, "rb") as f:
                resp = requests.post(
                    "https://0x0.st",
                    files={"file": (local_path.name, f, "video/mp4")},
                    timeout=120,
                )
            if resp.status_code == 200 and resp.text.startswith("http"):
                public_url = resp.text.strip()
                logger.info("✅ Staged to 0x0.st: %s", public_url)
                return public_url
        except Exception as e:
            logger.error("0x0.st upload failed: %s", e)

        raise RuntimeError(
            "Could not stage video to public URL for Meta ingestion."
        )

    def create_video_url_container(
        self,
        video_url: str,
        caption: str,
        share_to_feed: bool = True,
    ) -> str:
        """Create media container via public video_url (Meta fetches asynchronously)."""
        if not self.is_configured():
            raise ValueError("Instagram credentials missing in .env.")

        url = f"{self.GRAPH_API_BASE}/{self.ig_user_id}/media"
        payload = {
            "media_type": "REELS",
            "video_url": video_url,
            "caption": caption,
            "share_to_feed": "true" if share_to_feed else "false",
            "thumb_offset": "100",  # Flashy cover frame at 100ms
            "access_token": self.access_token,
        }

        resp = requests.post(url, data=payload, timeout=30)
        data = resp.json()

        if "id" not in data:
            error_msg = data.get("error", {}).get("message", "Unknown error")
            raise RuntimeError(f"Meta Graph API error creating video_url container: {error_msg} (Response: {data})")

        container_id = data["id"]
        logger.info("Initialized Meta video_url container: %s", container_id)
        return container_id

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

    def get_container_status(self, container_id: str) -> Tuple[str, str]:
        """Fetch (status_code, status_detail) from Meta Graph API."""
        url = f"{self.GRAPH_API_BASE}/{container_id}"
        params = {
            "fields": "status_code,status",
            "access_token": self.access_token,
        }
        try:
            resp = requests.get(url, params=params, timeout=15)
            data = resp.json()
            return data.get("status_code", "UNKNOWN"), data.get("status", "")
        except Exception as e:
            logger.warning("Failed to query container %s status: %s", container_id, e)
            return "UNKNOWN", str(e)

    def upload_binary_to_meta(
        self,
        upload_uri: str,
        video_path: Path,
        max_retries: int = 3,
    ) -> None:
        """Step 2: Stream raw video bytes directly to Meta's rupload servers.
        
        Handles Meta's resumable offset protocol and handles cases where Meta
        transitions the container to IN_PROGRESS/FINISHED despite HTTP timeout.
        """
        file_size = video_path.stat().st_size
        container_id = upload_uri.rstrip("/").split("/")[-1]
        logger.info("Streaming %s (%.2f MB) directly to Meta rupload servers (container=%s)...",
                    video_path.name, file_size / (1024 * 1024), container_id)

        headers = {
            "Authorization": f"OAuth {self.access_token}",
            "offset": "0",
            "file_size": str(file_size),
            "Content-Length": str(file_size),
            "Content-Type": "application/octet-stream",
        }

        with open(video_path, "rb") as f:
            video_bytes = f.read()

        current_offset = 0

        for attempt in range(1, max_retries + 1):
            logger.info("Uploading binary to Meta rupload servers (attempt %d/%d, offset=%d)...",
                        attempt, max_retries, current_offset)
            
            headers["offset"] = str(current_offset)
            headers["Content-Length"] = str(file_size - current_offset)
            data_to_send = video_bytes[current_offset:]

            resp = requests.post(upload_uri, headers=headers, data=data_to_send, timeout=300)
            data = resp.json() if resp.text else {}
            if resp.status_code in (200, 201) and data.get("success") is not False:
                logger.info("✅ Direct binary upload to Meta completed successfully!")
                return
            
            logger.warning("Upload attempt %d returned HTTP %d: %s", attempt, resp.status_code, resp.text)

            # Check if Meta already accepted and transitioned the container to IN_PROGRESS / FINISHED
            time.sleep(3)
            status_code, status_detail = self.get_container_status(container_id)
            logger.info("Container %s status on Meta: %s (%s)", container_id, status_code, status_detail)

            if status_code in ("IN_PROGRESS", "FINISHED"):
                logger.info("🎉 Container %s is already %s on Meta! Video was accepted.", container_id, status_code)
                return

            if status_code == "ERROR":
                logger.error("❌ Container %s failed on Meta: %s", container_id, status_detail)
                raise RuntimeError(f"Meta rejected video in container {container_id}: {status_detail}")

            # Query rupload offset to see how many bytes were safely received
            try:
                offset_resp = requests.get(
                    upload_uri,
                    headers={"Authorization": f"OAuth {self.access_token}"},
                    timeout=15,
                )
                if offset_resp.status_code == 200:
                    offset_data = offset_resp.json() if offset_resp.text else {}
                    server_offset = offset_data.get("offset")
                    if server_offset is None and "offset" in offset_resp.headers:
                        server_offset = int(offset_resp.headers["offset"])
                    
                    if server_offset is not None and server_offset > current_offset:
                        current_offset = server_offset
                        logger.info("Meta acknowledged %d / %d bytes. Resuming remaining %d bytes...",
                                    current_offset, file_size, file_size - current_offset)
                        if current_offset >= file_size:
                            logger.info("✅ All bytes (%d) acknowledged by Meta!", file_size)
                            return
            except Exception as e:
                logger.warning("Could not query rupload offset: %s", e)

            if attempt < max_retries:
                time.sleep(5)

        raise RuntimeError(f"Direct video upload to Meta failed after {max_retries} attempts.")

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
        """Publish a reel using Meta Graph API official direct resumable upload with session renewal."""
        local_path = Path(video_path_or_url)
        if not local_path.exists():
            raise FileNotFoundError(f"Video file not found: {local_path}")

        file_size = local_path.stat().st_size
        max_container_attempts = 2
        container_id = None

        for c_attempt in range(1, max_container_attempts + 1):
            try:
                # 1. Initialize direct resumable session on Meta
                logger.info("Initializing direct resumable upload on Meta (attempt %d/%d, file size: %.2f MB)...",
                            c_attempt, max_container_attempts, file_size / (1024 * 1024))
                c_id, upload_uri = self.create_resumable_container(
                    file_size=file_size,
                    caption=caption,
                    share_to_feed=share_to_feed,
                )
                container_id = c_id

                # 2. Upload raw binary directly to Meta rupload servers
                self.upload_binary_to_meta(upload_uri, local_path)
                break
            except Exception as e:
                logger.warning("Resumable container attempt %d failed: %s", c_attempt, e)
                if c_attempt == max_container_attempts:
                    raise
                logger.info("Retrying with a fresh Meta container session in 5s...")
                time.sleep(5)

        # 3. Wait for Meta encoding pipeline to finish
        self.wait_for_container_ready(container_id)

        # 4. Publish container
        media_id = self.publish_container(container_id)

        # 5. Get permalink
        permalink = self.get_permalink(media_id)

        return {
            "status": "success",
            "media_id": media_id,
            "container_id": container_id,
            "permalink": permalink,
        }
