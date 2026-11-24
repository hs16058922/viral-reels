"""3D studio reels for the scheduler: pick topic → spec → render shards → assemble → publish.

GitHub Actions fans the expensive part out across runners:

    python -m automation.studio_ci prepare  --build build      # topic, spec, narration, plan, shard list
    python -m automation.studio_ci render   --build build --index N   # one frame range (matrix job)
    python -m automation.studio_ci assemble --build build      # segments → final MP4 + QC → topic "ready"
    python automation/scheduler.py --now --topic <id>           # existing publish route

Locally, AutonomousReelBuilder calls build_local() which runs the same stages in one process.
Nothing here costs money: Blender/FFmpeg/Whisper are local, EdgeTTS is free, the optional AI
director uses the Gemini free tier, and public-repo Actions minutes are free.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import sys
import traceback
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from automation.topic_queue import TopicQueue  # noqa: E402
from engine.studio import branding, pipeline  # noqa: E402
from engine.studio.spec import VideoSpec  # noqa: E402

log = logging.getLogger("viral_reels.studio_ci")
SPECS = ROOT / "engine" / "studio" / "specs"
GENERATED = SPECS / "generated"
QUALITY = os.getenv("STUDIO_QUALITY", "realistic")
MAX_SHARD_FRAMES = int(os.getenv("STUDIO_SHARD_FRAMES", "60"))


def spec_for(topic: dict) -> Optional[Path]:
    """Approved spec for a topic: hand-authored (`spec` field) or an AI draft that passed visual review."""
    if topic.get("spec"):
        p = SPECS / f"{topic['spec']}.json"
        return p if p.exists() else None
    p = GENERATED / f"{topic['id']}.json"
    review = GENERATED / f"{topic['id']}.review.json"
    if p.exists() and review.exists() and json.loads(review.read_text()).get("passed"):
        return p
    return None


def direct_spec(topic: dict, work: Path) -> Optional[Path]:
    """Ask the free AI director for a spec; record the review either way. None if it isn't good enough."""
    from engine.studio.director import GeminiUnavailable, direct

    out = GENERATED / f"{topic['id']}.json"
    try:
        res = direct(topic, out, work)
    except GeminiUnavailable as e:  # Gemini overloaded/down: not the topic's fault, retry next run
        log.warning("director skipped for %s (Gemini unavailable: %s); topic stays pending", topic["id"], e)
        raise
    except Exception as e:  # noqa: BLE001 — a bad draft must never crash the run
        res = {"passed": False, "error": str(e)[:500]}
        log.warning("director failed for %s: %s", topic["id"], e)
    GENERATED.mkdir(parents=True, exist_ok=True)
    (GENERATED / f"{topic['id']}.review.json").write_text(json.dumps(
        {k: v for k, v in res.items() if k != "spec"}, indent=1, default=str))
    return out if res.get("passed") else None


def pick(queue: TopicQueue, topic_id: str = "") -> tuple[Optional[dict], str]:
    """(topic, mode): mode "ready" = pre-rendered video in repo, "render" = studio build, "none"."""
    topics = queue.load_topics()
    published = queue.get_published_ids()
    live = [t for t in topics if t.get("id", "").lower() not in published and t.get("status") != "published"]
    if topic_id:
        live = [t for t in live if t["id"] == topic_id]
    for t in live:
        vp = t.get("video_path")
        if t.get("status") == "ready" and vp and (ROOT / vp).exists():
            return t, "ready"
    for t in live:
        if t.get("status") in ("pending", "ready") and spec_for(t):
            return t, "render"
    # No approved spec: try the AI director on ONE topic per run (free-tier rate limits).
    for t in live:
        if t.get("status") == "pending":
            return t, "direct"
    return None, "none"


def set_topic(topic_id: str, **fields) -> None:
    q = TopicQueue()
    topics = q.load_topics()
    for t in topics:
        if t["id"] == topic_id:
            t.update(fields)
    q.save_topics(topics)


def _out(**kv) -> None:
    """Expose values to later workflow steps/jobs."""
    path = os.getenv("GITHUB_OUTPUT")
    for k, v in kv.items():
        line = f"{k}={v if isinstance(v, str) else json.dumps(v)}"
        print(line)
        if path:
            with open(path, "a") as f:
                f.write(line + "\n")


def cmd_prepare(build: Path, topic_id: str = "") -> None:
    build.mkdir(parents=True, exist_ok=True)
    queue = TopicQueue()
    try:
        queue.replenish_if_needed(min_pending=5)
    except Exception as e:  # noqa: BLE001
        log.warning("replenish skipped: %s", e)
    topic, mode = pick(queue, topic_id)
    if mode == "direct":
        from engine.studio.director import GeminiUnavailable
        try:
            spec = direct_spec(topic, build / "director")
        except GeminiUnavailable:
            topic, mode = None, "none"  # leave it pending; this slot just skips
        else:
            if not spec:
                set_topic(topic["id"], status="needs_spec")
                log.warning("topic %s parked as needs_spec (see %s)", topic["id"], GENERATED)
                topic, mode = pick(queue, topic_id)
                mode = "none" if mode == "direct" else mode
    meta = {"topic": topic["id"] if topic else "", "mode": mode, "quality": QUALITY, "shards": []}
    if mode == "render":
        spec_path = spec_for(topic)
        shutil.copy(spec_path, build / "spec.json")
        meta["spec_path"] = str(spec_path.relative_to(ROOT))
        _, plan, _ = pipeline.prepare(build / "spec.json", build)
        shards = pipeline.shard_list(plan, MAX_SHARD_FRAMES)
        for i, sh in enumerate(shards):
            sp = plan["scenes"][sh["scene"]]
            sh.update(index=i, key=pipeline.shard_key(sp, QUALITY, sh["start"], sh["end"]))
        meta["shards"] = shards
        meta["duration"] = plan["duration"]
    (build / "ci.json").write_text(json.dumps(meta, indent=1))
    _out(topic=meta["topic"], mode=mode, matrix=[{"index": s["index"], "key": s["key"]} for s in meta["shards"]] or [{"index": -1, "key": "none"}])
    log.info("prepare: topic=%s mode=%s shards=%d", meta["topic"], mode, len(meta["shards"]))


def cmd_render(build: Path, index: int) -> None:
    meta = json.loads((build / "ci.json").read_text())
    plan = json.loads((build / "plan.json").read_text())
    sh = meta["shards"][index]
    res = pipeline.render_shard(plan["scenes"][sh["scene"]], meta["quality"], build, sh["start"], sh["end"], retries=2)
    seg = build / "segments"
    seg.mkdir(parents=True, exist_ok=True)
    shutil.copy(res["mp4"], seg / f"{index:03d}.mp4")
    res["mp4"] = str(seg / f"{index:03d}.mp4")
    (seg / f"{index:03d}.json").write_text(json.dumps(res, default=str))


def cmd_assemble(build: Path) -> bool:
    """Returns True when the reel passed QC and the topic is marked ready for the scheduler."""
    meta = json.loads((build / "ci.json").read_text())
    tid = meta["topic"]
    spec = VideoSpec.model_validate_json((build / "spec.json").read_text())
    plan = json.loads((build / "plan.json").read_text())
    segs = [json.loads((build / "segments" / f"{i:03d}.json").read_text()) for i in range(len(meta["shards"]))]
    for i, s in enumerate(segs):  # artifact paths differ between jobs
        s["mp4"] = str(build / "segments" / f"{i:03d}.mp4")
    final = ROOT / "export" / f"{tid}_reel.mp4"
    res = pipeline.assemble(spec, plan, segs, meta["quality"], build, build / "raw_reel.mp4")
    errors = [i for i in res["issues"] if i.startswith("ERROR")]
    if errors:
        set_topic(tid, status="failed_qc", qc_issues=errors[:10])
        log.error("QC failed for %s — NOT publishing: %s", tid, errors)
        _out(ready="false")
        return False
    topic = next(t for t in TopicQueue().load_topics() if t["id"] == tid)
    branding.finalize(build / "raw_reel.mp4", final, topic)
    set_topic(tid, status="ready", video_path=str(final.relative_to(ROOT)))
    _out(ready="true")
    return True


def build_local(topic: dict) -> Path:
    """Single-machine build used by AutonomousReelBuilder / scheduler --now."""
    spec = spec_for(topic) or direct_spec(topic, ROOT / "tmp" / "director" / topic["id"])
    if not spec:
        raise RuntimeError(f"no approved SceneSpec for topic {topic['id']}; see {GENERATED}")
    final = ROOT / "export" / f"{topic['id']}_reel.mp4"
    out_dir = ROOT / "export" / "studio" / f"{topic['id']}_{QUALITY}"
    res = pipeline.generate_video(topic=topic["id"], spec_path=spec, quality=QUALITY,
                                  out_dir=out_dir, final_path=out_dir / "raw_reel.mp4")
    if not res["qc_passed"]:
        raise RuntimeError(f"QC failed, not publishing: {res['issues']}")
    return branding.finalize(out_dir / "raw_reel.mp4", final, topic)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=["prepare", "render", "assemble"])
    ap.add_argument("--build", type=Path, default=ROOT / "build")
    ap.add_argument("--index", type=int, default=0)
    ap.add_argument("--topic", default="")
    a = ap.parse_args()
    if a.stage == "prepare":
        try:
            cmd_prepare(a.build, a.topic)
        except Exception:  # noqa: BLE001 — never crash the scheduled run; just skip this slot
            traceback.print_exc()
            _out(topic="", mode="none", matrix=[{"index": -1, "key": "none"}])
    elif a.stage == "render":
        cmd_render(a.build, a.index)
    else:
        cmd_assemble(a.build)


if __name__ == "__main__":
    main()
