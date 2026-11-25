"""AI Scene Director: topic → validated SceneSpec JSON via a free-tier LLM.

Uses the Gemini API free tier (GEMINI_API_KEY; keep billing disabled on that
Google project so it can never charge). Output is never trusted: every draft
is validated against the strict SceneSpec schema and timing-resolved; errors
are sent back for repair, up to `attempts` rounds. Specs are data only — the
Blender interpreter executes no code from them.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from pathlib import Path

import requests
from pydantic import ValidationError

from engine.studio.spec import KIND_PARAMS, VideoSpec, resolve, tokens

log = logging.getLogger("viral_reels.director")
SPECS = Path(__file__).parent / "specs"
# Free OpenRouter models (":free" = $0) that draft alongside Gemini; best-scoring draft wins each round.
OPENROUTER_MODELS = [m.strip() for m in os.getenv(
    "OPENROUTER_MODELS",
    "nvidia/nemotron-3-ultra-550b-a55b:free,nvidia/nemotron-3.5-super-vl:free,google/gemma-4-31b-it:free",
).split(",") if m.strip()]
OPENROUTER_REVIEWER = os.getenv("OPENROUTER_REVIEWER", "nvidia/nemotron-3.5-super-vl:free")
MODELS = [m.strip() for m in os.getenv("GEMINI_DIRECTOR_MODELS", "gemini-3.8-flash,gemini-3.5-flash,gemini-flash-latest,gemini-3-flash-preview").split(",") if m.strip()]

REFERENCE = """
OBJECT KINDS (params) — units are scene units (~1 = a large part), angles in degrees:
- gear: teeth, module (tooth size, e.g. 0.06), thickness, bore, pinion_teeth (+ pinion_length) for a compound
  wheel, arms (spokes, 0 = solid disc), jewel (true = ruby bearing). mesh_with: <gear id>, angle: <deg> places this
  gear so it truly meshes the parent and drives it at the exact tooth ratio (only spin the root gear!). Meshing
  gears must share `module`. Gears lie in the XY plane, axis Z.
- rotor: blades, r_in, r_out, chord, twist, pitch, hub_length, thickness, axis ("x"|"y"|"z"), nose (true = spinner).
  Fans, propellers, turbines, impellers, compressor stages.
- lathe: profile [[radius, axial], ...] revolved around axis; sweep < 360 makes a CUTAWAY shell (start_angle picks
  which part is open), thickness, cut_material (colour of the cut rim). Housings, casings, pipes, nozzles, pots,
  bottles, chambers, cylinders of engines, bulbs.
- spring: coils, radius, wire, height; flat: true (+ inner_radius) makes a flat spiral (hairspring/mainspring).
- tube: points [[x,y,z],...] (smooth curve), radius. Pipes, wires, vessels, hoses.
- flow: points path, count, radius, speed (units/s), radial_copies + axis. Moving particles showing air, fluid,
  blood, electrons, heat. They loop forever along the path.
- box: size [x,y,z], bevel, pivot [x,y,z] (rotation origin offset, e.g. hinge at an edge).
- cylinder: radius, depth, axis, segments, bevel, pivot. sphere: radius, segments. torus: major, minor, axis.
- blob: elements [[x,y,z,radius],...] merged organic shape (organs, cells, droplets, dough). resolution.
- label: text, size (3D tag that always faces camera; use few, short, UPPERCASE or numbers).
- arrow: to [x,y,z] (from = position), radius.
- stage: nx, ny, tile, gap, height (tiled display floor). empty: group/pivot for children.
Every object: id, kind, params, material, position, rotation, scale, parent (children move/rotate with parent),
cut [nx,ny,nz] = SECTION CUT (removes the half of the object the normal points into, showing the inside with
a coloured cut face; e.g. [0,-1,0] removes the half facing the default camera), cut_offset, cut_material.
MATERIALS: clay, clay_dark, accent, accent2, blue, brass, steel, chrome, dark_steel, ruby, glass, tissue,
tissue_glass, blood_red, blood_blue, flame, air, ink, white.

ACTIONS (target can be a list; stagger = seconds between list items). at = seconds OR an exact phrase copied from
THAT scene's narration (the action starts when the narrator says it). duration null = continuous actions run to
scene end, others use a short default. ease: linear|smooth|back|bounce|elastic|expo. sfx: pop|click|swoosh|impact.
- spin: rate (deg/s, negative = clockwise), ramp (s), axis. Keep visible speeds <= 150 deg/s.
- tick: rate (steps/s), step (deg), axis. Stepping motion (escapements, counters).
- oscillate: amplitude, hz, axis. pulse: amount (negative = contract), hz, duty, axis ("all").
- cycle: prop ("rotation"|"location"|"scale"), axis, hz, phase, keys [[u 0..1, value], ...] first u=0 last u=1.
  Values are degrees / units added to the rest pose, or scale multipliers. Valves, pistons, pumps, cams.
- move: to [x,y,z] or by [dx,dy,dz]. rotate: to/by [deg x,y,z]. scale: to (number or [x,y,z]).
- explode: by [dx,dy,dz] — list item i moves (i+1)*by (exploded assembly views; reverse sign to assemble).
- pop_in / pop_out (appear/disappear with overshoot), show / hide (instant), fade (to alpha 0..1),
  highlight (color "#RRGGBB", strength, hold true = stay lit).

SHOTS (camera): at, type orbit|push_in|pull_out|top_down|static|macro, target (object id or [x,y,z]),
frame [ids that must stay fully visible — the camera auto-fits them in the 9:16 safe area], azimuth (0 = camera
on -Y), elevation, orbit (deg swept), lens (mm, 50-85), blend (s).

SCENE: id, narration (1-3 sentences), objective, background light|blue|dark (alternate them), keywords (exact
phrases from the narration to highlight in captions), note (on-screen disclaimer like "Illustrative - slowed 4x"
whenever speed/scale/simplification is not literal), use [prefab names], objects, actions, shots.
"""

RULES = """
You are the scene director of a premium 3D educational Reels channel. Write ONE SceneSpec JSON for the topic.
Hard rules:
1. 5-7 scenes, 100-135 narration words total (about 40-50 s). Scene 1 is a strong 3-second hook.
   Plain spoken English, no emojis, no hashtags, no "follow us".
2. SHOW THE REAL MECHANISM, DISSECTED: build the actual internal parts at realistic relative proportions and
   positions; open housings with lathe sweep < 360 or `cut` section planes; use exploded views to reveal layers;
   make the parts the narration mentions move exactly as they do in reality (correct directions, sequence,
   couplings). Prefer many simple accurate parts over one vague blob. No flat diagrams, no text-heavy scenes.
3. Every scene needs visible motion from its first second, and each important phrase triggers an action.
4. Anchors (`at`) and keywords must be phrases copied verbatim from that scene's narration.
5. Reuse parts across scenes with `prefabs` + `use`; ids are unique per scene, letters/digits/underscore only.
6. Keep the main subject within roughly a 4 x 7 unit volume, taller than wide when possible (vertical video).
7. Physically faithful directions and ratios; when you exaggerate speed or simplify, add a scene `note`.
8. Build every recognisable object from several parts, the way a 3D artist would block it out: e.g. an
   aircraft = lathe fuselage with tapered nose/tail + box wings + fin; a valve = lathe housing + cylinder disc +
   stem + handle; a phone = beveled box body + glass screen + camera bump. 6-20 solid parts per scene.
9. Every shot lists the ids it must keep visible in `frame`. Never put the camera inside a large object;
   use cutaways (lathe sweep / `cut`) to look inside things.
10. ONE HERO ASSEMBLY: build the device once in `prefabs` at realistic proportions with its real internal parts
    (housing, shafts, bearings, coils, chambers, seals, fasteners...) and `use` it in most scenes. Each scene
    reveals a different part of the SAME object (cutaway, explode, highlight, push_in/macro shots on that part).
    Do not invent unrelated props per scene.
11. NO STAND-INS: never use a lone sphere/box/cylinder to stand for a complex thing (a person, a car, a circuit
    board, a bag, a cloud of gas). Model its recognisable silhouette from several shaped parts (lathe profiles,
    beveled boxes, tubes) or leave it out. Gas/liquid/electricity = `flow` particles inside a cutaway.
12. FILL THE FRAME: parts sit close together the way they are really assembled (no floating gaps); each shot
    frames only the parts being explained so they appear large; keep labels to 0-2 per scene.
13. Output ONLY the JSON object. No markdown fences, no comments.
"""


class GeminiUnavailable(RuntimeError):
    """Every model was overloaded/unreachable: retry next run instead of judging the topic."""


def _call_gemini(prompt: str | list, model: str, key: str, temperature: float = 0.6) -> str:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    parts = [{"text": prompt}] if isinstance(prompt, str) else prompt
    for attempt in range(5):  # free tier: back off on 429 (rate limit) and 5xx (overloaded)
        r = requests.post(url, headers={"x-goog-api-key": key}, timeout=300, json={
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": {"response_mime_type": "application/json", "temperature": temperature,
                                 "maxOutputTokens": 32768}})
        if (r.status_code == 429 or r.status_code >= 500) and attempt < 4:
            time.sleep(30 * (attempt + 1))
            continue
        r.raise_for_status()
        parts_out = r.json()["candidates"][0]["content"]["parts"]
        return "".join(p.get("text", "") for p in parts_out)
    raise RuntimeError("unreachable")


def _call_openrouter(parts: list, model: str, key: str, temperature: float = 0.6) -> str:
    """OpenAI-compatible chat call; images become data URLs. Free models only (":free")."""
    if not model.endswith(":free"):
        raise ValueError(f"refusing non-free OpenRouter model {model}")
    content = [{"type": "text", "text": p["text"]} if "text" in p else
               {"type": "image_url", "image_url": {"url": f"data:{p['inline_data']['mime_type']};base64,"
                                                          f"{p['inline_data']['data']}"}} for p in parts]
    for attempt in range(4):
        r = requests.post("https://openrouter.ai/api/v1/chat/completions", timeout=600,
                          headers={"Authorization": f"Bearer {key}"},
                          json={"model": model, "messages": [{"role": "user", "content": content}],
                                "temperature": temperature, "max_tokens": 32000})
        if (r.status_code == 429 or r.status_code >= 500) and attempt < 3:
            time.sleep(20 * (attempt + 1))
            continue
        r.raise_for_status()
        data = r.json()
        if "choices" not in data:
            raise requests.HTTPError(f"OpenRouter error: {str(data.get('error', data))[:300]}")
        return data["choices"][0]["message"].get("content") or ""
    raise RuntimeError("unreachable")


def _gemini_any(parts: list, temperature: float = 0.6) -> str:
    key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not key:
        raise GeminiUnavailable("GEMINI_API_KEY not set")
    for model in MODELS:
        try:
            return _call_gemini(parts, model, key, temperature)
        except requests.RequestException as e:
            log.warning("gemini %s failed (%s), trying next", model, e)
    raise GeminiUnavailable("no Gemini model available")


def _drafters() -> list[tuple[str, callable]]:
    """(name, call(parts) -> text) for every free model we can draft with."""
    out = [("gemini", _gemini_any)]
    key = os.getenv("OPENROUTER_API_KEY")
    for m in OPENROUTER_MODELS if key else []:
        def call(parts, m=m):
            try:
                return _call_openrouter(parts, m, key)
            except requests.HTTPError:
                if len(parts) == 1:
                    raise
                return _call_openrouter(parts[:1], m, key)  # text-only model: drop the images
        out.append((m.split("/")[-1].replace(":free", ""), call))
    return out


def _check(text: str) -> tuple[VideoSpec | None, str]:
    """Validate a draft; returns (spec, "") or (None, error message for the repair round)."""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    if "{" in text:  # chatty models wrap the JSON in prose
        text = text[text.index("{"):text.rindex("}") + 1]
    try:
        spec = VideoSpec.model_validate_json(text)
    except ValidationError as e:
        return None, "Schema validation errors:\n" + "\n".join(
            f"- {'.'.join(map(str, er['loc']))}: {er['msg']}" for er in e.errors()[:25])
    words = len(tokens(spec.script))
    if not 70 <= words <= 170 or not 4 <= len(spec.scenes) <= 8:
        return None, f"Need 5-7 scenes and 100-135 words; got {len(spec.scenes)} scenes, {words} words."
    toks = tokens(spec.script)
    try:  # simulate narration at 2.6 words/s to catch too-short scenes / bad anchors
        resolve(spec, [(t, i / 2.6, i / 2.6 + 0.3) for i, t in enumerate(toks)], len(toks) / 2.6)
    except ValueError as e:
        return None, f"Timing error: {e}"
    return spec, ""


LINT_MIN_OBJECTS, LINT_MIN_ACTIONS = 6, 3
PASS_MIN, PASS_AVG = 5, 6.5


def _lint(spec: VideoSpec) -> str:
    """Density rules the schema can't express: thin scenes look like slideshows."""
    probs = []
    for sc in spec.scenes:
        solid = [o for o in sc.objects if o.kind not in ("label", "empty", "flow")]
        if len(solid) < LINT_MIN_OBJECTS:
            probs.append(f"scene {sc.id}: only {len(solid)} solid parts; build the real mechanism from >= {LINT_MIN_OBJECTS}")
        if len(sc.actions) < LINT_MIN_ACTIONS:
            probs.append(f"scene {sc.id}: only {len(sc.actions)} actions; animate what the narration describes")
        for sh in sc.shots:
            if not sh.frame:
                probs.append(f"scene {sc.id}: every shot needs `frame` ids so the camera can fit the subject")
    return "\n".join(probs)


def _img_parts(stills: list[Path]) -> list[dict]:
    import base64
    import io
    from PIL import Image

    out = []
    for png in stills:
        buf = io.BytesIO()
        Image.open(png).convert("RGB").save(buf, "JPEG", quality=85)
        out.append({"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(buf.getvalue()).decode()}})
    return out


def _review(spec: VideoSpec, stills: list[Path], key: str) -> tuple[list[dict], str]:
    """Free-tier Gemini vision review of one still per scene. Returns (scores, feedback)."""
    parts = [{"text": (
        "You are a strict art director for a premium 3D educational Reels channel. For each still (one per scene, "
        "in order) score 1-10 how clearly and REALISTICALLY it depicts the scene's objective: recognisable, "
        "correctly built objects/mechanism, well framed (subject fully visible, not cropped or tiny), not a "
        "vague arrangement of boxes. Be harsh: 9-10 = looks like a professional 3D explainer, 5 = understandable "
        "but crude, 1-3 = unrecognisable or broken. Return JSON: {\"scenes\": [{\"id\": str, \"score\": int, "
        "\"problems\": str, \"fix\": str}]}. Scenes:\n" +
        "\n".join(f"{i + 1}. {sc.id}: objective={sc.objective!r}; narration={sc.narration!r}" for i, sc in enumerate(spec.scenes)))}]
    parts += _img_parts(stills)
    reviewers = [(m, lambda p, m=m: _call_gemini(p, m, key, temperature=0.2)) for m in MODELS if key]
    if os.getenv("OPENROUTER_API_KEY"):
        reviewers.append((OPENROUTER_REVIEWER, lambda p: _call_openrouter(
            p, OPENROUTER_REVIEWER, os.environ["OPENROUTER_API_KEY"], temperature=0.2)))
    for name, call in reviewers:
        try:
            text = call(parts)
            scores = json.loads(text[text.index("{"):text.rindex("}") + 1])["scenes"]
            break
        except Exception as e:  # noqa: BLE001 — try the next reviewer
            log.warning("review: %s failed (%s)", name, e)
    else:
        raise GeminiUnavailable("visual review unavailable")
    feedback = "\n".join(f"- scene {s.get('id')}: score {s.get('score')}/10. Problems: {s.get('problems')}. "
                          f"Fix: {s.get('fix')}" for s in scores)
    return scores, feedback


def direct(topic: dict, out_path: Path, work: Path, visual_rounds: int = 4, budget_s: float = 100 * 60) -> dict:
    """Draft -> validate -> render stills -> vision review -> revise (seeing its own renders).

    Each revision starts from the best-scoring draft so far, so a bad round can't undo progress.
    Stops early on a pass, or when the time budget (free-tier rate-limit waits included) runs out.
    """
    from engine.studio.pipeline import render_stills

    key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    t0, history, best = time.time(), [], None
    feedback, images = "", []
    for rnd in range(visual_rounds + 1):
        outage = True  # stays True only if every drafter failed for network/availability reasons
        for name, call in _drafters():
            cand = out_path.with_name(f"{out_path.stem}.r{rnd}.{name}.json")
            try:
                draft_spec(topic, cand, attempts=3 if name == "gemini" else 2, feedback=feedback,
                           images=images, call=call)
            except Exception as e:  # noqa: BLE001 — one drafter failing must not stop the others
                if not isinstance(e, (GeminiUnavailable, requests.RequestException)):
                    outage = False
                log.warning("director: %s produced no valid draft in round %d (%s)", name, rnd, str(e)[:200])
                continue
            outage = False
            spec = VideoSpec.model_validate_json(cand.read_text())
            toks = tokens(spec.script)
            plan = resolve(spec, [(t, i / 2.6, i / 2.6 + 0.3) for i, t in enumerate(toks)], len(toks) / 2.6)
            stills = render_stills(plan, work / f"review_{rnd}_{name}")
            scores, fb = _review(spec, stills, key)
            vals = [int(s.get("score", 0)) for s in scores] or [0]
            avg = sum(vals) / len(vals)
            history.append({"round": rnd, "drafter": name, "scores": vals, "avg": round(avg, 2),
                            "feedback": fb, "stills": [str(p) for p in stills]})
            log.info("director: round %d %s scores %s (avg %.1f)", rnd, name, vals, avg)
            text = cand.read_text()
            cand.unlink()
            if min(vals) >= PASS_MIN and avg >= PASS_AVG:
                out_path.write_text(text)
                return {"spec": str(out_path), "passed": True, "drafter": name, "history": history}
            if best is None or avg > best["avg"]:
                best = {"avg": avg, "text": text, "fb": fb, "stills": stills, "drafter": name}
        if best is None:
            if outage:
                raise GeminiUnavailable("every drafter was unavailable")
            raise RuntimeError("no drafter produced a valid spec")
        if time.time() - t0 > budget_s:
            log.info("director: time budget used after round %d", rnd)
            break
        feedback = ("The attached images are renders of the best spec so far, one per scene, in order. LOOK at "
                    "them: anything that does not read as the real object must be rebuilt. Keep scenes that scored "
                    ">= 7 unchanged; rebuild the rest with more accurate, detailed, tightly framed parts.\n"
                    f"Reviewer notes:\n{best['fb']}\nBEST SPEC SO FAR:\n{best['text']}")
        images = best["stills"]
    out_path.write_text(best["text"])
    return {"spec": str(out_path), "passed": False, "drafter": best["drafter"], "history": history}


def draft_spec(topic: dict, out_path: Path, attempts: int = 3, feedback: str = "",
               images: list[Path] | None = None, call=None) -> Path:
    """Write a validated SceneSpec for `topic` to out_path, or raise RuntimeError."""
    call = call or _gemini_any
    examples = "\n\n".join(f"EXAMPLE SPEC ({p.stem}):\n{p.read_text()}" for p in
                           (SPECS / "mechanical_watch.json", SPECS / "jet_engine.json"))
    schema = json.dumps(VideoSpec.model_json_schema(), separators=(",", ":"))
    brief = {k: topic.get(k) for k in ("title", "hook", "script", "bullets") if topic.get(k)}
    base = (f"{RULES}\n{REFERENCE}\nJSON SCHEMA:\n{schema}\nAllowed params per kind: "
            f"{json.dumps({k: sorted(v) for k, v in KIND_PARAMS.items()})}\n\n{examples}\n\n"
            f"TOPIC BRIEF (facts to cover; rewrite the narration for the scenes):\n{json.dumps(brief, indent=1)}\n"
            + (f"\nREVIEW OF YOUR LAST VERSION:\n{feedback}\n" if feedback else ""))
    prompt, last_err = base, ""
    for i in range(attempts):
        text = call([{"text": prompt}] + _img_parts(images or []))
        spec, err = _check(text)
        if spec and (lint := _lint(spec)):
            spec, err = None, "Quality rules failed:\n" + lint
        if spec:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(spec.model_dump_json(indent=1, exclude_defaults=True))
            log.info("director: spec for %r accepted on round %d", topic.get("id"), i + 1)
            return out_path
        last_err = err
        log.warning("director round %d rejected: %s", i + 1, err[:500])
        prompt = f"{base}\nYOUR PREVIOUS DRAFT:\n{text[:60000]}\n\nIT WAS REJECTED:\n{err}\nReturn the corrected full JSON."
    raise RuntimeError(f"AI director could not produce a valid spec for {topic.get('id')}: {last_err[:300]}")
