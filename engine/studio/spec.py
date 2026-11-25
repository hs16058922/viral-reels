"""SceneSpec v2 — typed, narration-anchored scene description.

A VideoSpec is pure data: Blender never executes spec-provided code. The
Blender interpreter (blender_scene.py) only understands the whitelisted
object kinds and actions declared here, which is the sandbox for
AI-authored specs.

Timing is anchored to narration, not absolute frames: an action's ``at`` is
either seconds from scene start or a phrase from that scene's narration.
After TTS + Whisper, ``resolve()`` turns phrases into frames, so scenes
re-time automatically when narration length changes.
"""

from __future__ import annotations

import copy
import difflib
import hashlib
import json
import math
import re
from typing import Any, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from engine.studio import kit

Vec3 = tuple[float, float, float]
Anchor = Union[float, str]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# Allowed params per object kind. Unknown keys are rejected so typos in
# AI-authored specs fail loudly instead of silently rendering defaults.
KIND_PARAMS: dict[str, set[str]] = {
    "gear": {"teeth", "module", "thickness", "bore", "pinion_teeth", "pinion_length", "mesh_with", "angle",
             "arms", "jewel"},
    "rotor": {"blades", "r_in", "r_out", "chord", "twist", "pitch", "hub_length", "thickness", "axis", "nose"},
    "lathe": {"profile", "sweep", "start_angle", "segments", "thickness", "axis", "cut_material"},
    "spring": {"coils", "radius", "wire", "height", "flat", "inner_radius"},
    "tube": {"points", "radius"},
    "flow": {"points", "count", "radius", "speed", "radial_copies", "axis"},
    "box": {"size", "bevel", "pivot"},
    "sphere": {"radius", "segments"},
    "cylinder": {"radius", "depth", "axis", "segments", "bevel", "pivot"},
    "torus": {"major", "minor", "axis"},
    "label": {"text", "size"},
    "arrow": {"to", "radius"},
    "stage": {"nx", "ny", "tile", "gap", "height"},
    "asset": {"asset_id", "size"},
    "blob": {"elements", "resolution"},
    "empty": set(),
}

ObjectKind = Literal[
    "gear", "rotor", "lathe", "spring", "tube", "flow", "box", "sphere",
    "cylinder", "torus", "label", "arrow", "stage", "asset", "empty", "blob",
]
Material = Literal[
    "clay", "clay_dark", "accent", "accent2", "blue", "brass", "steel", "chrome",
    "dark_steel", "ruby", "glass", "tissue", "tissue_glass", "blood_red",
    "blood_blue", "flame", "air", "ink", "white",
]
ActionKind = Literal[
    "spin", "tick", "oscillate", "pulse", "cycle", "move", "rotate", "scale",
    "pop_in", "pop_out", "explode", "highlight", "fade", "show", "hide",
]
Ease = Literal["linear", "smooth", "back", "bounce", "elastic", "expo"]


class Obj(Strict):
    id: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_]*$")
    kind: ObjectKind
    params: dict[str, Any] = {}
    material: Material = "clay"
    parent: Optional[str] = None
    position: Vec3 = (0, 0, 0)
    rotation: Vec3 = (0, 0, 0)  # degrees
    scale: Union[float, Vec3] = 1.0
    cut: Optional[Vec3] = None  # dissect: remove the half-space this normal points into
    cut_offset: float = 0.0     # move the section plane along the normal
    cut_material: Optional[Material] = None  # colour of the exposed cut face (default accent)

    @model_validator(mode="after")
    def _params_known(self) -> "Obj":
        unknown = set(self.params) - KIND_PARAMS[self.kind]
        if unknown:
            raise ValueError(f"{self.id}: unknown params for kind '{self.kind}': {sorted(unknown)}")
        return self


class Action(Strict):
    target: Union[str, list[str]]
    do: ActionKind
    at: Anchor = 0.0           # seconds from scene start, or a narration phrase
    offset: float = 0.0        # seconds added to the resolved anchor
    duration: Optional[float] = None  # None → until scene end
    stagger: float = 0.0       # seconds between targets when target is a list
    ease: Ease = "smooth"
    params: dict[str, Any] = {}
    sfx: Optional[Literal["pop", "click", "swoosh", "impact"]] = None


class Shot(Strict):
    at: Anchor = 0.0
    offset: float = 0.0
    type: Literal["orbit", "push_in", "pull_out", "top_down", "static", "macro"] = "orbit"
    target: Union[str, Vec3] = (0, 0, 0)
    frame: list[str] = []      # objects that must stay in the safe area (default: target)
    azimuth: float = -35.0     # degrees around Z, 0 = camera on -Y looking +Y
    elevation: float = 28.0
    orbit: Optional[float] = None  # degrees swept over the shot
    distance: Optional[float] = None  # None → auto-fit `frame` into the safe area
    lens: float = 50.0
    blend: float = 0.7         # seconds to ease from previous shot


class Scene(Strict):
    id: str = Field(pattern=r"^[A-Za-z0-9_]+$")
    narration: str = Field(min_length=1)
    objective: str = ""
    background: Literal["light", "blue", "dark"] = "light"
    keywords: list[str] = []   # caption words to highlight
    note: Optional[str] = None  # e.g. "Illustrative · slowed 8×" — shown on screen
    use: list[str] = []        # prefab groups merged into objects (scene objects win by id)
    objects: list[Obj] = Field(min_length=1)
    actions: list[Action] = []
    shots: list[Shot] = Field(min_length=1)

    @model_validator(mode="after")
    def _references(self) -> "Scene":
        ids = [o.id for o in self.objects]
        if len(ids) != len(set(ids)):
            raise ValueError(f"scene {self.id}: duplicate object ids")
        known = set(ids)
        for o in self.objects:
            if o.parent and o.parent not in known:
                raise ValueError(f"scene {self.id}: {o.id}.parent '{o.parent}' unknown")
            mw = o.params.get("mesh_with")
            if mw and mw not in known:
                raise ValueError(f"scene {self.id}: {o.id}.mesh_with '{mw}' unknown")
        for a in self.actions:
            for t in _as_list(a.target):
                if t not in known:
                    raise ValueError(f"scene {self.id}: action {a.do} targets unknown '{t}'")
        for s in self.shots:
            for t in ([s.target] if isinstance(s.target, str) else []) + s.frame:
                if t not in known:
                    raise ValueError(f"scene {self.id}: shot references unknown '{t}'")
        anchors = [a.at for a in self.actions] + [s.at for s in self.shots]
        for p in (x for x in anchors if isinstance(x, str)):
            if phrase_index(tokens(self.narration), p) is None:
                raise ValueError(f"scene {self.id}: anchor phrase '{p}' not in narration")
        return self


class VideoSpec(Strict):
    title: str
    style: Literal["cinematic_3d_educational"] = "cinematic_3d_educational"
    voice: str = "en-US-ChristopherNeural"
    fps: int = 30
    prefabs: dict[str, list[dict[str, Any]]] = {}
    scenes: list[Scene] = Field(min_length=1)

    @model_validator(mode="before")
    @classmethod
    def _expand_prefabs(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        data = copy.deepcopy(data)
        pre = {k: kit.expand(v) for k, v in data.get("prefabs", {}).items()}
        data["prefabs"] = pre
        for sc in data.get("scenes", []):
            have = {o["id"] for o in sc.get("objects", [])}
            extra = []
            for name in sc.get("use", []):
                if name not in pre:
                    raise ValueError(f"scene {sc.get('id')}: unknown prefab '{name}'")
                for o in pre[name]:
                    if o["id"] not in have:
                        have.add(o["id"])
                        extra.append(o)
            sc["objects"] = extra + kit.expand(sc.get("objects", []))
        return data

    @field_validator("scenes")
    @classmethod
    def _unique_scene_ids(cls, v: list[Scene]) -> list[Scene]:
        if len({s.id for s in v}) != len(v):
            raise ValueError("duplicate scene ids")
        return v

    @property
    def script(self) -> str:
        return " ".join(s.narration.strip() for s in self.scenes)


def _as_list(x: Union[str, list[str]]) -> list[str]:
    return [x] if isinstance(x, str) else list(x)


# ── Narration alignment ──────────────────────────────────────────────────

def tokens(text: str) -> list[str]:
    """Lowercase word tokens; hyphens split ("lub-dub" → lub, dub)."""
    return re.findall(r"[a-z0-9']+", text.lower().replace("’", "'"))


def display_words(text: str) -> list[str]:
    """Original-cased words aligned 1:1 with tokens() (for captions)."""
    out = []
    for raw in text.replace("—", " ").split():
        n = len(tokens(raw))
        out += [raw] + [""] * (n - 1) if n else []
    return out


def phrase_index(toks: list[str], phrase: str) -> Optional[int]:
    p = tokens(phrase)
    for i in range(len(toks) - len(p) + 1):
        if toks[i:i + len(p)] == p:
            return i
    return None


def align(script_tokens: list[str], heard: list[tuple[str, float, float]]) -> list[tuple[float, float]]:
    """Map every script token to (start, end) seconds using Whisper words.

    Matches via difflib on normalized tokens; unmatched script tokens are
    linearly interpolated between their matched neighbours, so a Whisper
    misspelling never breaks timing.
    """
    heard_toks = []
    for w, s, e in heard:
        parts = tokens(w) or ["_"]
        span = (e - s) / len(parts)
        heard_toks += [(p, s + i * span, s + (i + 1) * span) for i, p in enumerate(parts)]
    times: list[Optional[tuple[float, float]]] = [None] * len(script_tokens)
    sm = difflib.SequenceMatcher(None, script_tokens, [h[0] for h in heard_toks], autojunk=False)
    for a, b, n in sm.get_matching_blocks():
        for k in range(n):
            times[a + k] = heard_toks[b + k][1:]
    end_t = heard_toks[-1][2] if heard_toks else 0.0
    known = [i for i, t in enumerate(times) if t]
    if not known:
        raise ValueError("narration alignment failed: no script words heard in the audio")
    for i, t in enumerate(times):
        if t:
            continue
        lo = max((k for k in known if k < i), default=None)
        hi = min((k for k in known if k > i), default=None)
        t0 = times[lo][1] if lo is not None else 0.0
        t1 = times[hi][0] if hi is not None else end_t
        n_lo = lo if lo is not None else -1
        n_hi = hi if hi is not None else len(times)
        f0 = (i - n_lo) / (n_hi - n_lo)
        f1 = (i + 1 - n_lo) / (n_hi - n_lo)
        times[i] = (t0 + (t1 - t0) * f0, t0 + (t1 - t0) * f1)
    return times  # type: ignore[return-value]


# ── Gear trains ──────────────────────────────────────────────────────────

def resolve_gear_trains(objs: list[dict]) -> None:
    """Place meshing gears and compute drive ratios in-place.

    A gear with ``mesh_with: parent`` is positioned so its pinion (or its
    wheel when it has no pinion) meshes the parent's wheel at ``angle``
    degrees around the parent, on the parent's wheel layer. It gets
    ``driver = {root, ratio, phase0, root0}`` so Blender couples its
    rotation to the root gear exactly: ω_child = -ω_parent · T_parent / T_child.
    """
    by_id = {o["id"]: o for o in objs}
    done: set[str] = set()

    def place(o: dict) -> None:
        if o["id"] in done:
            return
        p = o["params"]
        mw = p.get("mesh_with")
        if not mw:
            o["_ratio"], o["_root"] = 1.0, o["id"]
            done.add(o["id"])
            return
        par = by_id[mw]
        if par["kind"] != "gear" or o["kind"] != "gear":
            raise ValueError(f"{o['id']}: mesh_with must link two gears")
        place(par)
        pp = par["params"]
        m = float(p.get("module", 0.1))
        if abs(m - float(pp.get("module", 0.1))) > 1e-9:
            raise ValueError(f"{o['id']}: module differs from '{mw}', teeth cannot mesh")
        t_par = int(pp["teeth"])
        t_me = int(p.get("pinion_teeth") or p["teeth"])
        dist = m * (t_par + t_me) / 2.0
        a = math.radians(float(p.get("angle", 0.0)))
        px, py, pz = par["position"]
        # Pinion sits below the wheel by pinion_length/2 + thickness/2; align
        # that layer with the parent's wheel plane.
        dz = 0.0
        if p.get("pinion_teeth"):
            dz = float(p.get("pinion_length", 0.3)) / 2 + float(p.get("thickness", 0.15)) / 2
        o["position"] = (px + dist * math.cos(a), py + dist * math.sin(a), pz + dz)
        ratio_rel = -t_par / t_me
        o["_ratio"] = par["_ratio"] * ratio_rel
        o["_root"] = par["_root"]
        # Phase so a gap of this gear faces the parent's tooth on the line of centres.
        pitch_p, pitch_c = 360.0 / t_par, 360.0 / t_me
        phi_p = par["rotation"][2]
        ad = math.degrees(a)
        phi_c = ad + 180.0 - pitch_c * (0.5 - ((ad - phi_p) / pitch_p) % 1.0)
        o["rotation"] = (o["rotation"][0], o["rotation"][1], phi_c)
        root = by_id[o["_root"]]
        o["driver"] = {
            "root": o["_root"],
            "ratio": o["_ratio"],
            "phase0": math.radians(phi_c),
            "root0": math.radians(root["rotation"][2]),
        }
        done.add(o["id"])

    for o in objs:
        if o["kind"] == "gear":
            place(o)
    for o in objs:
        o.pop("_ratio", None)
        o.pop("_root", None)


# ── Resolution: spec + word timings → frame-exact render jobs ────────────

def resolve(spec: VideoSpec, heard: list[tuple[str, float, float]], audio_end: float) -> dict:
    """Return a JSON-able plan: per-scene frame ranges, frame-exact actions/shots,
    and per-word caption timings (using script spelling, Whisper timing)."""
    fps = spec.fps
    scene_toks = [tokens(s.narration) for s in spec.scenes]
    flat = [t for st in scene_toks for t in st]
    times = align(flat, heard)

    words, starts, k = [], [], 0
    for si, (sc, st) in enumerate(zip(spec.scenes, scene_toks)):
        starts.append(0.0 if si == 0 else times[k][0])
        for disp, tok in zip(display_words(sc.narration), st):
            words.append({"scene": si, "text": disp, "token": tok, "start": times[k][0], "end": times[k][1]})
            k += 1
    end = audio_end + 0.6
    frame_starts = [round(s * fps) for s in starts] + [round(end * fps)]

    scenes_out = []
    k = 0
    for si, sc in enumerate(spec.scenes):
        f0, f1 = frame_starts[si], frame_starts[si + 1]
        n = f1 - f0
        if n < fps // 2:
            raise ValueError(f"scene {sc.id} is only {n} frames; merge it or lengthen narration")
        st = scene_toks[si]
        tok_times = times[k:k + len(st)]
        k += len(st)

        def to_frame(at: Anchor, offset: float) -> int:
            if isinstance(at, str):
                t = tok_times[phrase_index(st, at)][0] - starts[si]
            else:
                t = float(at)
            return max(0, min(n - 1, round((t + offset) * fps)))

        objs = [o.model_dump() for o in sc.objects]
        resolve_gear_trains(objs)
        actions = []
        for a in sc.actions:
            for j, tgt in enumerate(_as_list(a.target)):
                a0 = to_frame(a.at, a.offset + j * a.stagger)
                a1 = None if a.duration is None else min(n - 1, a0 + max(1, round(a.duration * fps)))
                actions.append({"target": tgt, "do": a.do, "f0": a0, "f1": a1, "ease": a.ease,
                                "params": a.params, "sfx": a.sfx, "index": j})
        shots = []
        for s in sc.shots:
            d = s.model_dump()
            d["f0"] = to_frame(s.at, s.offset)
            shots.append(d)
        shots.sort(key=lambda d: d["f0"])
        shots[0]["f0"] = 0
        for a, b in zip(shots, shots[1:] + [None]):
            a["f1"] = (b["f0"] if b else n)
        scenes_out.append({
            "id": sc.id, "index": si, "frames": n, "frame_offset": f0, "fps": fps,
            "background": sc.background, "objects": objs, "actions": actions, "shots": shots,
        })
    return {"title": spec.title, "fps": fps, "duration": frame_starts[-1] / fps,
            "scenes": scenes_out, "words": words}


def scene_hash(scene_plan: dict, extra: str) -> str:
    raw = json.dumps(scene_plan, sort_keys=True) + extra
    return hashlib.sha256(raw.encode()).hexdigest()[:16]
