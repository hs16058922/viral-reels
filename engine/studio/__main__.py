"""CLI: python -m engine.studio "How does a mechanical watch work?" --quality preview"""

import argparse
import json
import logging

from engine.studio.spec import VideoSpec


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("topic", nargs="?")
    ap.add_argument("--quality", default="preview", choices=["preview", "production", "cycles", "realistic"])
    ap.add_argument("--duration", type=float, default=45)
    ap.add_argument("--spec", help="explicit SceneSpec JSON path")
    ap.add_argument("--out", help="output job directory")
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--schema", action="store_true", help="print the SceneSpec JSON schema and exit")
    a = ap.parse_args()
    if a.schema:
        print(json.dumps(VideoSpec.model_json_schema(), indent=2))
        return
    if not a.topic and not a.spec:
        ap.error("topic or --spec required")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    from engine.studio import generate_video
    print(json.dumps(generate_video(topic=a.topic or a.spec, duration_seconds=a.duration, quality=a.quality,
                                    spec_path=a.spec, out_dir=a.out, workers=a.workers), indent=2))


if __name__ == "__main__":
    main()
