"""Shot library: finished, visually checked scenes the AI director sequences by name.

Free LLMs write good scripts but bad 3D layouts. So the layout (objects, motion, camera) lives here, authored and
rendered once by hand; the AI only writes a storyboard: narration per scene + which shot plays under it + optional
callouts (highlight a listed part when a phrase is spoken) and one short label. `build()` turns that storyboard
into an ordinary SceneSpec, so the renderer, timing and captions are unchanged.

Every kit gets automatic shots (`<kit>` and, for kits with a casing, `<kit>_cutaway`) from MOTION below; topic
shots (microwave, ...) compose several kits. Check new shots visually: `python -m engine.studio.shots <dir> [names]`.
"""

from __future__ import annotations

import copy
import math
import re
from typing import Any

from engine.studio import kit

SHOTS: dict[str, dict[str, Any]] = {}
BACKGROUNDS = ["light", "dark", "blue"]


def shot(name, desc, objects, actions=(), camera=(), parts=(), background=None, note=None, label_at=(0.0, -1.0, 1.9)):
    """Register a shot. `parts` = object ids the AI may call out (highlight) by name."""
    SHOTS[name] = {"desc": desc, "objects": list(objects), "actions": list(actions), "shots": list(camera),
                   "parts": list(parts), "background": background, "note": note, "label_at": list(label_at)}


def A(target, do, at=0.0, **params) -> dict:
    a = {"target": target, "do": do, "at": at}
    for k in ("duration", "stagger", "ease", "offset"):
        if k in params:
            a[k] = params.pop(k)
    a["params"] = params
    return a


def cam(type_, target, frame, az=-30, el=20, **kw) -> dict:
    return {"type": type_, "target": target, "frame": frame, "azimuth": az, "elevation": el, **kw}


# ── Per-kit motion: how each kit really moves (targets are part ids; "" = the whole kit) ──
WARM = "#FF7A1A"
MOTION: dict[str, list[dict]] = {
    "magnetron": [A("cathode", "highlight", 0.2, color=WARM, strength=3, hold=True)],
    "microwave_cavity": [A("turntable", "spin", rate=35, axis="z")],
    "water_molecule": [A("", "oscillate", amplitude=55, hz=0.9, axis="y")],
    "bowl_of_soup": [A("soup", "highlight", 0.3, color=WARM, strength=1.2, hold=True)],
    "disc_brake": [A(["pad_outer"], "cycle", prop="location", axis="y", hz=0.8,
                                           keys=[[0, 0], [0.4, 0.06], [0.7, 0.06], [1, 0]]),
                   A(["pad_inner", "piston"], "cycle", prop="location", axis="y", hz=0.8,
                     keys=[[0, 0], [0.4, -0.06], [0.7, -0.06], [1, 0]])],
    "car_wheel": [A("", "spin", rate=90, axis="y")],
    "abs_modulator": [A("plunger", "cycle", prop="location", axis="z", hz=3, keys=[[0, 0], [0.5, 0.12], [1, 0]]),
                      A([f"valve_{i}" for i in range(4)], "highlight", 0.4, stagger=0.3, color=WARM, strength=1.5)],
    "wheel_speed_sensor": [A("tone_ring", "spin", rate=60, axis="z"),
                           A("sensor_tip", "highlight", 0.3, color="#3DA5FF", strength=2, hold=True)],
    "electric_motor": [A("rotor", "spin", rate=120, axis="z"),
                       A([f"winding_{i}" for i in range(6)], "highlight", 0.2, stagger=0.25, color=WARM, strength=1.5)],
    "electromagnet": [A("coil", "highlight", 0.4, color=WARM, strength=1.5, hold=True)],
    "bar_magnet": [A("", "rotate", by=[0, 0, 25], duration=6)],
    "quartz_resonator": [A("prong_l", "oscillate", amplitude=-0.04, hz=3, axis="x", prop="location"),
                         A("prong_r", "oscillate", amplitude=0.04, hz=3, axis="x", prop="location")],
    "clock_movement": [A("gear_drive", "spin", rate=-120, axis="z")],
    "maglev": [A("car", "oscillate", amplitude=0.03, hz=0.7, axis="z", prop="location")],
    "piston_engine": [A("crank", "spin", rate=180, axis="y"),
                      A(["piston", "ring_0", "ring_1"], "cycle", prop="location", axis="z", hz=0.5,
                        keys=[[0, 0.45], [0.25, 0], [0.5, -0.45], [0.75, 0], [1, 0.45]]),
                      A("conrod", "cycle", prop="location", axis="z", hz=0.5,
                        keys=[[0, 0.22], [0.25, 0], [0.5, -0.22], [0.75, 0], [1, 0.22]]),
                      A("spark_tip", "highlight", 0.2, color="#FFD24A", strength=4, duration=0.3)],
    "centrifugal_pump": [A("impeller", "spin", rate=150, axis="y")],
    "ball_bearing": [A("inner_race", "spin", rate=100, axis="z"), A("balls_cage", "spin", rate=40, axis="z")],
    "battery_cell": [A("cap", "highlight", 0.3, color="#3DA5FF", strength=1.5, hold=True)],
    "em_wave": [],
    "heating_coil": [A("coil", "highlight", 0.3, color=WARM, strength=2, hold=True)],
    "spring_damper": [A("rod", "cycle", prop="location", axis="z", hz=0.8, keys=[[0, 0], [0.5, -0.3], [1, 0]]),
                      A("spring", "cycle", prop="scale", axis="z", hz=0.8, keys=[[0, 1], [0.5, 0.86], [1, 1]])],
    "gear_pair": [A("gear_big", "spin", rate=45, axis="z")],
    "housing_cutaway": [],
}
# kits whose casing hides the interesting parts: also get a `<kit>_cutaway` shot
CUTAWAY = {"magnetron", "electric_motor", "abs_modulator", "piston_engine", "centrifugal_pump", "battery_cell",
           "spring_damper", "electromagnet", "quartz_resonator"}


def motion(kit_name: str, iid: str) -> list[dict]:
    """A kit's MOTION, retargeted at instance `iid` (part `x` -> `iid_x`, "" -> `iid`)."""
    out = []
    for a in copy.deepcopy(MOTION.get(kit_name, [])):
        t = a["target"]
        a["target"] = [f"{iid}_{x}" if x else iid for x in t] if isinstance(t, list) else (f"{iid}_{t}" if t else iid)
        out.append(a)
    return out


def _part_ids(kit_name: str, iid: str) -> list[str]:
    return [f"{iid}_{p['id']}" for p in kit.KIT[kit_name]["parts"] if p["kind"] not in ("empty", "label")]


for _k, _v in kit.KIT.items():
    if _k in ("housing_cutaway", "em_wave"):  # building blocks only: nothing to look at on their own
        continue
    _first = _v["desc"].split(":")[0]
    shot(_k, f"{_first}: the whole part, slowly orbiting, moving as it does in reality",
         [{"id": _k, "kit": _k}], motion(_k, _k), [cam("orbit", _k, [_k], -32, 20, orbit=24)],
         parts=_part_ids(_k, _k))
    if _k in CUTAWAY:
        shot(f"{_k}_cutaway", f"{_first}: sliced open (front half removed) to show the internal parts working",
             [{"id": _k, "kit": _k, "cut": [0, -1, 0]}], motion(_k, _k), [cam("push_in", _k, [_k], -22, 18)],
             parts=_part_ids(_k, _k))


# ── Topic shots: compositions of several kits ──

ILLUS = "Illustrative - slowed"
HIDE_PANEL = ["oven_door", "oven_control_panel", "oven_shell_right"] + [f"oven_button_{i}" for i in range(3)]

shot("microwave_hero", "a real countertop microwave oven, camera slowly pushing in (hook / outro)",
     [{"id": "oven", "kind": "asset", "params": {"asset_id": "vintage_microwave", "size": 3.0}}],
     [A("oven", "rotate", by=[0, 0, 18], duration=7, ease="smooth")],
     [cam("push_in", "oven", ["oven"], -38, 18, lens=50)], background="light", label_at=(0, -0.6, 1.4))

_wave_in = [[1.45, 0.2, 0.45], [0.9, 0.1, 0.5], [0.4, 0.3, 0.1], [-0.3, -0.2, 0.55], [-0.9, 0.3, 0.0],
            [-0.4, -0.3, -0.35], [0.3, 0.2, 0.3], [0.9, -0.2, -0.1]]
shot("microwave_inside", "inside a microwave oven (front cut away): microwaves bouncing between the metal walls "
     "while a bowl of soup turns on the glass turntable",
     [{"id": "oven", "kit": "microwave_cavity"},
      {"id": "soup", "kit": "bowl_of_soup", "parent": "oven_turntable", "position": [0, 0, 0.32], "scale": 0.62},
      {"id": "waves", "kind": "flow", "material": "air",
       "params": {"points": _wave_in, "count": 26, "radius": 0.035, "speed": 1.4}}],
     motion("microwave_cavity", "oven") + motion("bowl_of_soup", "soup") + [A("oven_door", "hide")],
     [cam("push_in", "oven_turntable", ["oven_left_wall", "oven_right_wall"], -8, 10, lens=50)],
     parts=["oven_turntable", "oven_waveguide", "oven_back_wall", "soup_soup", "soup_bowl", "waves"],
     background="dark", note=ILLUS)

shot("microwave_wave_path", "energy path inside a microwave: the magnetron on the side wall fires microwaves "
     "down the waveguide into the metal cooking box",
     [{"id": "oven", "kit": "microwave_cavity"},
      {"id": "mag", "kit": "magnetron", "position": [1.62, 0.25, 0.1], "scale": 0.36, "cut": [0, -1, 0]},
      {"id": "soup", "kit": "bowl_of_soup", "parent": "oven_turntable", "position": [0, 0, 0.32], "scale": 0.62},
      {"id": "waves", "kind": "flow", "material": "air",
       "params": {"points": [[1.62, 0.25, 0.5], [1.5, 0.2, 0.62], [1.2, 0.2, 0.5]] + _wave_in[1:], "count": 30,
                  "radius": 0.035, "speed": 1.4}}],
     motion("microwave_cavity", "oven") + motion("magnetron", "mag") + [A(HIDE_PANEL, "hide"),
      A("oven_waveguide", "highlight", 1.0, color="#3DA5FF", strength=1.5)],
     [cam("orbit", "oven_waveguide", ["oven_turntable", "mag"], 30, 16, orbit=10)],
     parts=["mag", "mag_cathode", "oven_waveguide", "soup_soup", "waves"], background="blue", note=ILLUS)

shot("magnetron_electrons", "top view into a cut-open magnetron: electrons spiral out from the glowing cathode "
     "past the copper vanes (this is what makes the microwaves)",
     [{"id": "mag", "kit": "magnetron", "cut": [0, 0, 1], "cut_offset": 0.05}],
     motion("magnetron", "mag") + [A("mag", "rotate", by=[0, 0, 30], duration=8),
                                   A([f"mag_fin_{i}" for i in range(5)] + ["mag_filament_leads"], "hide")],
     [cam("static", "mag_anode", ["mag_anode"], -10, 70, lens=60)],
     parts=["mag_cathode", "mag_anode", "mag_electrons"] + [f"mag_vane_{i}" for i in range(8)],
     background="dark", note=ILLUS, label_at=(0, 1.2, 0.2))

_grid = [(x, 0.0, z) for z in (1.3, 0.0, -1.3) for x in (-1.3, 0.0, 1.3)]
shot("water_molecules_jostle", "a crowd of water molecules twisting back and forth with the flipping field, "
     "rubbing together: the friction becomes heat (they glow warmer)",
     [{"id": f"w{i}", "kit": "water_molecule", "position": list(p), "rotation": [0, 37 * i % 90, 0], "scale": 0.7}
      for i, p in enumerate(_grid)],
     [A([f"w{i}_charge_{c}" for i in range(9) for c in ("neg", "pos")], "hide")] +
     [A(f"w{i}", "oscillate", amplitude=50, hz=1.6, phase=(i * 0.37) % 1, axis="y") for i in range(9)] +
     [A([f"w{i}_oxygen" for i in range(9)], "highlight", 1.8, stagger=0.12, color=WARM, strength=1.2, hold=True)],
     [cam("push_in", "w4", [f"w{i}" for i in range(9)], -12, 8, lens=55)],
     parts=["w4", "w4_oxygen"], background="blue", note=ILLUS)

shot("water_dipole_flip", "one water molecule (a tiny magnet-like dipole) flipping to follow the microwave's "
     "electric field, billions of times per second",
     [{"id": "w", "kit": "water_molecule", "scale": 1.1},
      {"id": "field", "kit": "em_wave", "position": [0, 0.9, 0], "scale": 0.9}],
     [A("w", "oscillate", amplitude=80, hz=1.2, axis="y")],
     [cam("static", "w", ["w", "field_direction"], -18, 10, lens=50)],
     parts=["w_oxygen", "w_hydrogen_0", "w_charge_neg", "w_charge_pos", "field"], background="dark", note=ILLUS)

shot("soup_heating", "close-up of a bowl of soup heating up, steam rising",
     [{"id": "soup", "kit": "bowl_of_soup", "scale": 1.3}], motion("bowl_of_soup", "soup"),
     [cam("macro", "soup", ["soup_bowl"], -15, 30, lens=60)],
     parts=["soup_soup", "soup_bowl", "soup_steam"], background="light")


# ── Storyboard -> SceneSpec ──

def catalog() -> str:
    """Prompt text: every shot, what it shows, and the part ids it can call out."""
    return "\n".join(f"- {n}: {s['desc']}." + (f" Callout parts: {', '.join(s['parts'][:14])}." if s["parts"] else "")
                     for n, s in SHOTS.items())


LABEL_MAX, MAX_LABELS = 18, 2  # chars per label; labels per reel (more is clutter)


def build(board: dict) -> dict:
    """Storyboard {"title", "scenes": [{"id", "shot", "narration", "keywords"?, "callouts"?, "label"?}]}
    -> SceneSpec source dict. Raises ValueError with a message the AI can act on."""
    scenes, errs, labels = [], [], 0
    for i, sb in enumerate(board.get("scenes") or []):
        sid = re.sub(r"[^A-Za-z0-9_]", "_", str(sb.get("id") or f"s{i}"))
        name = sb.get("shot")
        if name not in SHOTS:
            errs.append(f"scene {sid}: unknown shot {name!r}; pick one from SHOT LIBRARY")
            continue
        s = copy.deepcopy(SHOTS[name])
        acts = s["actions"]
        for c in sb.get("callouts") or []:
            if c.get("part") not in s["parts"]:
                errs.append(f"scene {sid}: callout part {c.get('part')!r} not in {name}'s callout parts {s['parts']}")
                continue
            acts.append({"target": c["part"], "do": "highlight", "at": c.get("at", 0.5), "duration": 2.0,
                         "params": {"color": "#FFD24A", "strength": 1.2}, "sfx": "pop"})
        objs = s["objects"]
        if sb.get("label") and labels < MAX_LABELS:
            labels += 1
            text = str(sb["label"]).upper()[:LABEL_MAX]
            objs.append({"id": "callout_label", "kind": "label", "material": "ink", "position": s["label_at"],
                         "params": {"text": text, "size": 0.32}})
            acts.append({"target": "callout_label", "do": "pop_in", "at": 0.6, "sfx": "pop"})
            for c in s["shots"]:  # the camera keeps the label inside the frame
                c["frame"] = c["frame"] + ["callout_label"]
        scenes.append({"id": sid, "narration": sb.get("narration", ""), "objective": s["desc"],
                       "background": s["background"] or BACKGROUNDS[i % len(BACKGROUNDS)],
                       "keywords": sb.get("keywords") or [], **({"note": s["note"]} if s["note"] else {}),
                       "objects": objs, "actions": acts, "shots": s["shots"]})
    if errs:
        raise ValueError("\n".join(errs))
    return {"title": board.get("title") or "Untitled", "scenes": scenes}


if __name__ == "__main__":  # render one still per shot into a contact sheet
    import sys
    from pathlib import Path

    from PIL import Image, ImageDraw

    from engine.studio import pipeline
    from engine.studio.spec import VideoSpec, resolve, tokens

    out = Path(sys.argv[1])
    names = sys.argv[2].split(",") if len(sys.argv) > 2 else list(SHOTS)
    board = {"title": "shots", "scenes": [{"id": n, "shot": n, "narration": "This is the part we are looking at "
                                           "today, and it is working right now in front of you."} for n in names]}
    spec = VideoSpec.model_validate(build(board))
    pipeline.resolve_assets(spec)
    toks = tokens(spec.script)
    plan = resolve(spec, [(t, i / 2.6, i / 2.6 + 0.3) for i, t in enumerate(toks)], len(toks) / 2.6)
    stills = pipeline.render_stills(plan, out)
    ims = [Image.open(p).resize((270, 480)) for p in stills]
    cols = min(6, len(ims))
    sheet = Image.new("RGB", (270 * cols, 500 * math.ceil(len(ims) / cols)), "white")
    d = ImageDraw.Draw(sheet)
    for i, (im, n) in enumerate(zip(ims, names)):
        x, y = (i % cols) * 270, (i // cols) * 500
        sheet.paste(im, (x, y))
        d.text((x + 5, y + 482), n, fill="black")
    sheet.save(out / "sheet.jpg")
    print(out / "sheet.jpg")
