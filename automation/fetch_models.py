"""Download the curated CC0 Poly Haven models (1k glTF) into assets/models and write manifest.json.

    python -m automation.fetch_models

Models are committed, so CI renders never need the network. Poly Haven assets are CC0 (no attribution
required; credited in the manifest anyway). Add an id to MODELS and re-run to extend the library.
"""

from __future__ import annotations

import json
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets" / "models"
UA = {"User-Agent": "reel-studio-asset-fetch"}
# id: what the director is told it is (keep it literal; the AI picks by this text)
MODELS = {
    "vintage_microwave": "countertop microwave oven (closed door)",
    "wooden_bowl_01": "wooden bowl",
    "pot_enamel_01": "enamel cooking pot",
    "vintage_electric_kettle": "electric kettle",
    "electric_stove": "kitchen electric stove / oven",
    "alarm_clock_01": "twin-bell alarm clock",
    "wall_clock": "round wall clock",
    "vintage_pocket_watch": "pocket watch",
    "ceiling_fan": "ceiling fan",
    "Drill_01": "cordless power drill",
    "lightbulb_01": "incandescent light bulb",
    "lightbulb_led": "LED light bulb",
    "old_tyre": "car tyre",
    "rusted_wheel_rim_01": "steel car wheel rim",
    "tire_pump": "hand tyre pump",
    "Camera_01": "compact camera",
    "propane_tank": "propane gas tank",
    "Television_01": "old CRT television",
    "covered_car": "car under a cover (silhouette of a car)",
}


def main() -> None:
    manifest = {}
    for aid, desc in MODELS.items():
        files = requests.get(f"https://api.polyhaven.com/files/{aid}", headers=UA, timeout=60).json()
        g = files["gltf"]["1k"]["gltf"]
        info = requests.get(f"https://api.polyhaven.com/info/{aid}", headers=UA, timeout=60).json()
        d = OUT / aid
        for rel, entry in [(Path(g["url"]).name, g), *g["include"].items()]:
            dst = d / rel
            if not dst.exists():
                dst.parent.mkdir(parents=True, exist_ok=True)
                dst.write_bytes(requests.get(entry["url"], headers=UA, timeout=120).content)
        dims = [round(x / 1000, 3) for x in info.get("dimensions", [])]  # mm -> m
        manifest[aid] = {"file": f"{aid}/{Path(g['url']).name}", "license": "CC0-1.0", "description": desc,
                         "dimensions_m": dims, "source": f"https://polyhaven.com/a/{aid}",
                         "author": ", ".join(info.get("authors", {}))}
        print("ok", aid, dims)
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=1))


if __name__ == "__main__":
    main()
