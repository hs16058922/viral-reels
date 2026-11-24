#!/usr/bin/env python3
"""
3x Daily Instagram Reels Automation Scheduler.

Triggers 3 times a day at high-engagement viral peak hours:
- Slot 1: 09:30 AM (Morning commute & wake-up scroll)
- Slot 2: 02:00 PM (Afternoon break)
- Slot 3: 07:30 PM (Evening prime-time discovery)

Can run as:
1. Immediate post: `python automation/scheduler.py --now`
2. Daemon scheduler: `python automation/scheduler.py --daemon`
3. Crontab setup: `python automation/scheduler.py --install-cron`
"""

import argparse
import datetime
import logging
import os
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from automation.instagram_direct import DirectInstagramPublisher
from automation.instagram_publisher import InstagramPublisher
from automation.reel_analytics import ReelAnalyticsEngine
from automation.reel_builder import AutonomousReelBuilder
from automation.topic_queue import TopicQueue
from automation.viral_captions import ViralCaptionGenerator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("viral_reels.scheduler")


def post_next_reel(dry_run: bool = False, topic_id: str = "") -> bool:
    """Select the next topic (or `topic_id`), construct the viral caption, and post to Instagram."""
    queue = TopicQueue()
    if topic_id:
        topic = next((t for t in queue.load_topics() if t.get("id") == topic_id), None)
    else:
        topic = queue.get_next_ready_topic(auto_replenish=True)

    if not topic:
        logger.warning("No pending topics found in queue even after auto-replenishment.")
        return False

    logger.info("Found topic to post: '%s' (ID: %s)", topic["title"], topic["id"])

    # 1. Deduplication Safety Check: Has this topic ID already been posted?
    published_ids = queue.get_published_ids()
    if topic["id"].lower() in published_ids and topic.get("status") == "published":
        logger.critical("🛑 DUPLICATE BLOCKED: Topic ID '%s' has already been published. Aborting.", topic["id"])
        return False

    # 2. Locate or Build Video File (Reuse existing render if upload failed previously)
    video_path_str = topic.get("video_path")
    video_path = (PROJECT_ROOT / video_path_str) if video_path_str else None
    standard_export = PROJECT_ROOT / "export" / f"{topic['id']}_reel.mp4"

    if (not video_path or not video_path.exists()) and standard_export.exists() and standard_export.stat().st_size > 1024 * 1024:
        video_path = standard_export
        logger.info("🎬 Found existing rendered video at '%s' (%.1f MB). Skipping re-render!",
                    video_path.name, standard_export.stat().st_size / (1024 * 1024))
        topic["video_path"] = str(video_path.relative_to(PROJECT_ROOT))
        topic["status"] = "ready"
        queue.save_topics(queue.load_topics())

    if not video_path or not video_path.exists():
        if dry_run:
            logger.info("🔍 DRY-RUN: Video for '%s' would be generated on the fly via AutonomousReelBuilder.", topic["id"])
            video_path = standard_export
        else:
            logger.info("Video for topic '%s' not found. Launching AutonomousReelBuilder...", topic["id"])
            video_path = AutonomousReelBuilder.build_reel_for_topic(topic)
            topic["video_path"] = str(video_path.relative_to(PROJECT_ROOT))
            topic["status"] = "ready"
            queue.save_topics(queue.load_topics())

    # 3. Binary Deduplication Safety Check: Has this exact video binary ever been posted?
    if not dry_run and queue.is_video_already_published(video_path):
        logger.critical(
            "🛑 DUPLICATE VIDEO BLOCKED: The video file '%s' has ALREADY been published to Instagram! "
            "Aborting publication to protect profile integrity.",
            video_path.name,
        )
        return False

    # Build viral caption
    caption = ViralCaptionGenerator.generate(
        topic_title=topic["title"],
        hook=topic["hook"],
        bullet_points=topic["bullets"],
        niche_tags=topic.get("niche_tags"),
    )

    logger.info("Generated viral caption (%d characters):\n%s\n%s\n%s",
                len(caption), "-" * 40, caption[:200] + "...", "-" * 40)

    if dry_run:
        logger.info("🔍 DRY-RUN MODE: Video and caption validated successfully. No API call made.")
        return True

    # 1. Official Meta Graph API (Permanent, ban-safe) - First Priority
    publisher = InstagramPublisher()
    if publisher.is_configured():
        logger.info("🚀 Publishing Reel to Instagram via Official Meta Graph API (Account ID: %s)...", publisher.ig_user_id)
        try:
            result = publisher.publish_reel(
                video_path_or_url=str(video_path),
                caption=caption,
                share_to_feed=True,
            )
            logger.info("🎉 Reel successfully published!")
            logger.info("🔗 Link: %s", result["permalink"])
            queue.mark_published(topic["id"], result["permalink"], video_path=video_path)
            AutonomousReelBuilder.cleanup_export_directory(keep_topic_id=topic["id"])
            try:
                logger.info("📊 Running automated post-publish Reels Analytics Audit...")
                ReelAnalyticsEngine().analyze_all_reels()
            except Exception as e:
                logger.warning("Post-publish analytics note: %s", e)
            return True
        except Exception as exc:
            logger.exception("Failed to publish reel via Meta Graph API: %s", exc)
            return False

    # 2. Fallback: Direct Mobile Login
    direct_pub = DirectInstagramPublisher()
    if direct_pub.is_configured():
        logger.info("🚀 Publishing Reel via Direct Instagram Mobile API (@%s)...", direct_pub.username)
        try:
            thumb_path = PROJECT_ROOT / "export" / f"{topic['id']}_cover.jpg"
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", "1.5", "-i", str(video_path), "-frames:v", "1",
                            str(thumb_path)], check=False)
            result = direct_pub.publish_reel(
                video_path=video_path,
                caption=caption,
                thumbnail_path=thumb_path if thumb_path.exists() else None,
            )
            logger.info("🎉 Reel successfully published!")
            logger.info("🔗 Link: %s", result["permalink"])
            queue.mark_published(topic["id"], result["permalink"], video_path=video_path)
            AutonomousReelBuilder.cleanup_export_directory(keep_topic_id=topic["id"])
            try:
                logger.info("📊 Running automated post-publish Reels Analytics Audit...")
                ReelAnalyticsEngine().analyze_all_reels()
            except Exception as e:
                logger.warning("Post-publish analytics note: %s", e)
            return True
        except Exception as exc:
            logger.exception("Failed to publish reel via direct login: %s", exc)
            return False

    logger.error(
        "❌ No Instagram credentials found in environment.\n"
        "Please add either:\n"
        "  - INSTAGRAM_USERNAME and INSTAGRAM_PASSWORD (Direct simple login), OR\n"
        "  - INSTAGRAM_ACCESS_TOKEN and INSTAGRAM_ACCOUNT_ID (Meta Graph API)\n"
        "to your /Users/hitesh/Desktop/viral-reels-studio/.env file."
    )
    return False


def run_daemon():
    """Simple schedule daemon checking for 09:30, 14:00, and 19:30 slots."""
    SLOT_HOURS = [(9, 30), (14, 0), (19, 30)]
    logger.info("Starting 3x Daily Automation Daemon for slots: %s", SLOT_HOURS)
    
    last_posted_slot = None

    while True:
        now = datetime.datetime.now()
        current_time = (now.hour, now.minute)

        for sh, sm in SLOT_HOURS:
            # Check if within 5-minute window of the scheduled slot
            if now.hour == sh and abs(now.minute - sm) <= 2:
                slot_key = f"{now.strftime('%Y-%m-%d')}_{sh}:{sm}"
                if last_posted_slot != slot_key:
                    logger.info("⏰ Triggering scheduled publication slot: %02d:%02d", sh, sm)
                    post_next_reel()
                    last_posted_slot = slot_key
                break

        time.sleep(30)  # Check every 30 seconds


def print_cron_instructions():
    """Print macOS crontab commands for 3x daily posting."""
    py_path = PROJECT_ROOT / ".venv" / "bin" / "python"
    script_path = PROJECT_ROOT / "automation" / "scheduler.py"
    
    print("\n" + "=" * 60)
    print("📋 macOS Crontab Schedule (3x Daily: 9:30 AM, 2:00 PM, 7:30 PM)")
    print("=" * 60)
    print("To install, run: crontab -e and paste these 3 lines:\n")
    print(f"30 9 * * * cd {PROJECT_ROOT} && {py_path} {script_path} --now >> tmp/cron.log 2>&1")
    print(f"0 14 * * * cd {PROJECT_ROOT} && {py_path} {script_path} --now >> tmp/cron.log 2>&1")
    print(f"30 19 * * * cd {PROJECT_ROOT} && {py_path} {script_path} --now >> tmp/cron.log 2>&1")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Instagram Reels 3x Daily Automation")
    parser.add_argument("--now", action="store_true", help="Post the next ready reel immediately")
    parser.add_argument("--dry-run", action="store_true", help="Test execution without publishing to Instagram")
    parser.add_argument("--daemon", action="store_true", help="Run background daemon polling for schedule slots")
    parser.add_argument("--install-cron", action="store_true", help="Print crontab commands for macOS")
    parser.add_argument("--topic", default="", help="Publish this topic id (CI passes the reel it just built)")

    args = parser.parse_args()

    if args.install_cron:
        print_cron_instructions()
    elif args.now or args.dry_run:
        success = post_next_reel(dry_run=args.dry_run, topic_id=args.topic)
        if not success:
            sys.exit(1)
    elif args.daemon:
        run_daemon()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
