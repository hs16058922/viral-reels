"""
Topic Queue & Deduplication Manager for Daily Automated Reels.

Maintains an organized library of viral mechanical & engineering mysteries.
Ensures:
1. Queue is automatically replenished with fresh, non-duplicate topics
2. Published history is immutably tracked with MD5 hashes
3. Prevents re-posting any previously published video or topic
"""

import datetime
import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger("viral_reels.topic_queue")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
QUEUE_FILE = PROJECT_ROOT / "automation" / "topics.json"
HISTORY_FILE = PROJECT_ROOT / "automation" / "published_history.json"


def compute_video_hash(video_path: Path) -> str:
    """Compute MD5 checksum of video file to prevent duplicate binary uploads."""
    hasher = hashlib.md5()
    with open(video_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


class TopicQueue:
    """Manages the topic queue, automatic replenishment, and publication deduplication."""

    def __init__(self, queue_path: Optional[Path] = None, history_path: Optional[Path] = None):
        self.queue_path = queue_path or QUEUE_FILE
        self.history_path = history_path or HISTORY_FILE
        self._ensure_files()

    def _ensure_files(self):
        """Ensure topics.json and published_history.json exist."""
        if not self.history_path.exists():
            with open(self.history_path, "w", encoding="utf-8") as f:
                json.dump([], f, indent=2)

    def load_topics(self) -> List[Dict[str, Any]]:
        if not self.queue_path.exists():
            return []
        with open(self.queue_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def save_topics(self, topics: List[Dict[str, Any]]):
        with open(self.queue_path, "w", encoding="utf-8") as f:
            json.dump(topics, f, indent=2)

    def load_history(self) -> List[Dict[str, Any]]:
        if not self.history_path.exists():
            return []
        try:
            with open(self.history_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    def save_history(self, history: List[Dict[str, Any]]):
        with open(self.history_path, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2)

    def get_published_ids(self) -> Set[str]:
        """Collect all topic IDs that have already been published."""
        history = self.load_history()
        published_ids = {h.get("id", "").lower() for h in history if "id" in h}
        # Also check topics with status='published'
        for t in self.load_topics():
            if t.get("status") == "published" and "id" in t:
                published_ids.add(t["id"].lower())
        return published_ids

    def get_published_video_hashes(self) -> Set[str]:
        """Collect all video MD5 hashes that have already been published."""
        history = self.load_history()
        return {h.get("video_hash", "").lower() for h in history if h.get("video_hash")}

    def is_video_already_published(self, video_path: Path) -> bool:
        """Check if this exact video file has ever been published to Instagram."""
        if not video_path.exists():
            return False
        v_hash = compute_video_hash(video_path).lower()
        published_hashes = self.get_published_video_hashes()
        return v_hash in published_hashes

    def replenish_if_needed(self, min_pending: int = 5):
        """Invoke topic generator to auto-replenish queue if low."""
        try:
            from automation.topic_generator import ViralTopicGenerator
            added = ViralTopicGenerator.replenish_queue(min_pending=min_pending)
            if added > 0:
                logger.info("Automatically replenished topic queue with %d fresh topics.", added)
        except Exception as e:
            logger.warning("Could not auto-replenish queue: %s", e)

    def get_next_ready_topic(self, auto_replenish: bool = True) -> Optional[Dict[str, Any]]:
        """Find the next unposted topic. Auto-replenishes queue if low."""
        if auto_replenish:
            self.replenish_if_needed(min_pending=5)

        topics = self.load_topics()
        published_ids = self.get_published_ids()

        for t in topics:
            t_id = t.get("id", "").lower()
            status = t.get("status", "")
            # Skip if already published or in history
            if t_id in published_ids or status == "published":
                continue
            if status in ("ready", "pending"):
                return t

        return None

    def mark_published(self, topic_id: str, permalink: str, video_path: Optional[Path] = None):
        """Record topic as published in both topics.json and immutable published_history.json."""
        timestamp = datetime.datetime.now().isoformat()
        video_hash = compute_video_hash(video_path) if (video_path and video_path.exists()) else ""

        # 1. Update topics.json
        topics = self.load_topics()
        target_title = topic_id
        for t in topics:
            if t.get("id") == topic_id:
                t["status"] = "published"
                t["permalink"] = permalink
                t["published_at"] = timestamp
                target_title = t.get("title", topic_id)
        self.save_topics(topics)

        # 2. Append to published_history.json
        history = self.load_history()
        history.append({
            "id": topic_id,
            "title": target_title,
            "permalink": permalink,
            "published_at": timestamp,
            "video_path": str(video_path) if video_path else "",
            "video_hash": video_hash,
            "account": "curio__motion",
        })
        self.save_history(history)
        logger.info("✅ Marked topic '%s' as permanently published (hash: %s)", topic_id, video_hash[:8] if video_hash else "none")
