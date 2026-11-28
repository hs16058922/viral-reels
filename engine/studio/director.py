"""AI Scene Director: topic -> storyboard over the shot library (engine/studio/shots.py) -> SceneSpec.

Free models (Gemini free tier first, then OpenRouter ":free") write the narration and pick a pre-built, visually
checked shot for each scene; they never lay out 3D geometry. Output is never trusted: the storyboard must name
real shots and parts, and the built spec is schema-validated and timing-resolved; errors go back for repair.
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

from engine.studio import shots
from engine.studio.pipeline import resolve_assets
from engine.studio.spec import VideoSpec, resolve, tokens

log = logging.getLogger("viral_reels.director")
SPECS = Path(__file__).parent / "specs"
# Free OpenRouter models (":free" = $0) that draft alongside Gemini; best-scoring draft wins each round.
OPENROUTER_MODELS = [m.strip() for m in os.getenv(
    "OPENROUTER_MODELS",
    "nvidia/nemotron-3-ultra-550b-a55b:free,nvidia/nemotron-3.5-super-vl:free,google/gemma-4-31b-it:free",
).split(",") if m.strip()]
OPENROUTER_REVIEWER = os.getenv("OPENROUTER_REVIEWER", "nvidia/nemotron-3.5-super-vl:free")
MODELS = [m.strip() for m in os.getenv("GEMINI_DIRECTOR_MODELS", "gemini-3.8-flash,gemini-3.5-flash,gemini-flash-latest,gemini-3-flash-preview").split(",") if m.strip()]

RULES = """
You are the writer-director of a premium 3D educational Reels channel. The 3D scenes are already built: you
write the narration and pick, for each scene, the SHOT from the SHOT LIBRARY that shows what the narration says.
Return ONLY a JSON storyboard:
{"title": str,
 "hook_text": "2-5 WORD on-screen hook shown huge over scene 1, e.g. IT'S A BOMB",
 "scenes": [{"id": "hook", "shot": "<shot name>", "narration": "1-3 spoken sentences",
             "keywords": ["exact phrase from this narration"],
             "callouts": [{"part": "<one of that shot's callout parts>", "at": "exact phrase from this narration"}],
             "label": "optional on-screen tag, max 18 chars, e.g. 2.45 GHZ"}]}
RETENTION (the viewer swipes away in under 2 seconds unless you give them a reason to stay):
A. HOOK = scene 1, max 2 sentences, first sentence max 10 words. Open a curiosity gap: a shocking claim, a
   danger, an impossible-sounding number, or a "why" question about something the viewer uses daily. Do NOT
   give the answer away: the hook asks, the last scene answers. Never open with "Did you know", "Have you ever",
   "In this video", "Here's how", "Let's", or the topic's name. Pick the most dramatic, moving shot for it.
   Think of 3 hooks silently and use the one that makes the viewer most need the answer.
B. RE-HOOK every middle scene: end it with a short teaser that pulls into the next scene, e.g. "But that
   creates a problem.", "And this part is insane.", "So why doesn't it melt?". Never repeat a teaser.
C. ESCALATE: every scene must be more surprising than the last; save the most mind-blowing fact or number for
   the second-to-last scene.
D. PAYOFF: the last scene answers the hook's question in one punchy line that echoes the hook's words, so the
   loop closes and replaying feels natural. No summary, no "and that's how".
E. Talk to "you", short sentences (max 14 words), concrete numbers, vivid verbs. No textbook tone.
Rules:
1. 5-7 scenes, 85-120 narration words total (about 32-42 s). Plain spoken English, no emojis, no hashtags,
   no "follow us".
2. The narration of each scene describes exactly what its shot shows; read the shot descriptions carefully.
   Use each shot at most once unless the story returns to it (hook and outro may share one).
3. Labels: at most 2 in the whole reel, only for a key number or term. 0-2 callouts per scene: highlight the part at the moment the narration names it. `at` and keywords must be
   copied word for word from that scene's narration.
4. Physically correct facts only; the shots are already marked "Illustrative" where they are slowed down.
5. If the SHOT LIBRARY cannot show this topic's mechanism (most scenes would not match), return
   {"unsupported": "<which shots would be needed>"} instead of a storyboard.
"""

EXAMPLE = {"title": "Why an Electric Toothbrush Hums", "hook_text": "30,000 RPM. IN YOUR MOUTH.", "scenes": [
    {"id": "hook", "shot": "electric_motor_cutaway", "narration": "There's a motor in your mouth spinning thirty "
     "thousand times a minute. So why doesn't it rip your gums apart?", "keywords": ["thirty thousand"],
     "callouts": [{"part": "electric_motor_rotor", "at": "a motor in your mouth"}]},
    {"id": "gears", "shot": "gear_pair", "narration": "A tiny gear trades that speed for force, rocking the brush "
     "head instead of spinning it. But that's not the clever part.",
     "callouts": [{"part": "gear_pair_gear_small", "at": "A tiny gear"}], "label": "5:1"}]}


class GeminiUnavailable(RuntimeError):
    """Every model was overloaded/unreachable: retry next run instead of judging the topic."""


_DEADLINE = [float("inf")]  # wall-clock end of the current direct() run; every API call respects it
CALL_TIMEOUT = 240


def _timeout() -> float:
    """Per-request timeout that never runs past the deadline."""
    left = _DEADLINE[0] - time.time()
    if left < 30:
        raise GeminiUnavailable("director time budget exhausted")
    return min(CALL_TIMEOUT, left)


def _backoff(seconds: float) -> None:
    time.sleep(max(0, min(seconds, _DEADLINE[0] - time.time() - 30)))


_EXHAUSTED: set[str] = set()  # models that ran out of free quota in this process; skipped until the next run


def _post(url: str, model: str, **kw) -> requests.Response:
    """POST with free-tier etiquette: one short retry on 429, then the model is skipped for the rest of the run
    (a daily quota won't come back in minutes, and waiting burned the whole budget); brief retries on 5xx."""
    if model in _EXHAUSTED:
        raise requests.HTTPError(f"{model}: free quota exhausted earlier this run")
    for attempt in range(3):
        try:
            r = requests.post(url, timeout=_timeout(), **kw)
        except requests.Timeout:
            _EXHAUSTED.add(model)
            log.warning("%s timed out; skipping it for the rest of this run", model)
            raise
        if r.status_code == 429:
            if attempt == 0:
                log.warning("%s rate-limited: %s", model, r.text[:400].replace("\n", " "))
                _backoff(20)
                continue
            _EXHAUSTED.add(model)
            log.warning("%s still rate-limited; skipping it for the rest of this run", model)
        elif r.status_code >= 500 and attempt < 2:
            _backoff(20 * (attempt + 1))
            continue
        r.raise_for_status()
        return r
    raise RuntimeError("unreachable")


def _call_gemini(prompt: str | list, model: str, key: str, temperature: float = 0.6) -> str:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    parts = [{"text": prompt}] if isinstance(prompt, str) else prompt
    r = _post(url, model, headers={"x-goog-api-key": key}, json={
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {"response_mime_type": "application/json", "temperature": temperature,
                             "maxOutputTokens": 32768}})
    parts_out = r.json()["candidates"][0]["content"]["parts"]
    return "".join(p.get("text", "") for p in parts_out)


def _call_openrouter(parts: list, model: str, key: str, temperature: float = 0.6) -> str:
    """OpenAI-compatible chat call; images become data URLs. Free models only (":free")."""
    if not model.endswith(":free"):
        raise ValueError(f"refusing non-free OpenRouter model {model}")
    content = [{"type": "text", "text": p["text"]} if "text" in p else
               {"type": "image_url", "image_url": {"url": f"data:{p['inline_data']['mime_type']};base64,"
                                                          f"{p['inline_data']['data']}"}} for p in parts]
    r = _post("https://openrouter.ai/api/v1/chat/completions", model, headers={"Authorization": f"Bearer {key}"},
              json={"model": model, "messages": [{"role": "user", "content": content}],
                    "temperature": temperature, "max_tokens": 32000})
    data = r.json()
    if "choices" not in data:
        raise requests.HTTPError(f"OpenRouter error: {str(data.get('error', data))[:300]}")
    return data["choices"][0]["message"].get("content") or ""


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


def _clean(text: str) -> str:
    """Strip reasoning blocks, code fences and chatty prose around the JSON object."""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    if "{" in text:
        text = text[text.index("{"):text.rindex("}") + 1]
    return text




BANNED_OPENERS = ("did you know", "have you ever", "in this video", "here's how", "here is how", "let's", "today")


def _hook_problem(text: str) -> str:
    """Why scene 1 won't stop the scroll, or "" if it is fine."""
    first = re.split(r"(?<=[.?!])\s+", text.strip())[0]
    if text.strip().lower().startswith(BANNED_OPENERS):
        return f"it opens with a banned phrase ({text.split()[0]!r}...)"
    if len(first.split()) > 12:
        return f"its first sentence has {len(first.split())} words; max 10 so it lands in under 3 seconds"
    return ""


def _check(src: dict) -> tuple[VideoSpec | None, str]:
    """Validate a built spec; returns (spec, "") or (None, error message for the repair round)."""
    try:
        spec = VideoSpec.model_validate(src)
    except ValidationError as e:
        return None, "Schema validation errors:\n" + "\n".join(
            f"- {'.'.join(map(str, er['loc']))}: {er['msg']}" for er in e.errors()[:25])
    words = len(tokens(spec.script))
    if not 80 <= words <= 165 or not 4 <= len(spec.scenes) <= 8:
        return None, f"Need 5-7 scenes and 85-120 words; got {len(spec.scenes)} scenes, {words} words."
    hook = _hook_problem(spec.scenes[0].narration)
    if hook:
        return None, f"Weak hook (scene 1): {hook}. Rewrite it following RETENTION rule A."
    try:  # simulate narration at 2.6 words/s to catch too-short scenes / bad anchors
        _plan(spec)
    except ValueError as e:
        return None, f"Timing error: {e}"
    return spec, ""


def draft_board(topic: dict, call=None, attempts: int = 3) -> dict:
    """{"board", "spec"} (spec = SceneSpec source dict) or {"unsupported": reason}; RuntimeError if no valid draft."""
    call = call or _gemini_any
    brief = {k: topic.get(k) for k in ("title", "hook", "script", "bullets") if topic.get(k)}
    base = (f"{RULES}\nSHOT LIBRARY:\n{shots.catalog()}\n\nEXAMPLE (2 of the 5-7 scenes):\n{json.dumps(EXAMPLE)}\n\n"
            f"TOPIC BRIEF (facts to cover; write your own narration):\n{json.dumps(brief, indent=1)}\n")
    prompt, err = base, ""
    for i in range(attempts):
        text = call([{"text": prompt}])
        try:
            board = json.loads(_clean(text))
        except ValueError as e:
            board, err = None, f"Not valid JSON: {e}"
        if isinstance(board, dict) and board.get("unsupported"):
            return {"unsupported": str(board["unsupported"])[:300]}
        if board is not None:
            try:
                src = shots.build(board)
            except (ValueError, TypeError, AttributeError) as e:
                err = str(e)
            else:
                spec, err = _check(src)
                if spec:
                    log.info("director: storyboard for %r accepted on attempt %d", topic.get("id"), i + 1)
                    return {"board": board, "spec": src}
        log.warning("director attempt %d rejected: %s", i + 1, err[:500])
        prompt = f"{base}\nYOUR PREVIOUS ANSWER:\n{text[:20000]}\n\nIT WAS REJECTED:\n{err}\nReturn the corrected JSON."
    raise RuntimeError(f"no valid storyboard for {topic.get('id')}: {err[:300]}")


def direct(topic: dict, out_path: Path, work: Path, budget_s: float = 40 * 60) -> dict:
    """Topic -> storyboard over the shot library -> SceneSpec at out_path.

    Drafters are tried in order (Gemini first); the first valid storyboard whose stills all render wins. The
    vision review is advisory (logged for tuning shots), not a gate: the shots themselves are pre-checked.
    """
    from engine.studio.pipeline import render_stills

    key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    history, outage = [], True
    _DEADLINE[0] = time.time() + budget_s
    try:
        for name, call in _drafters():
            try:
                res = draft_board(topic, call)
            except Exception as e:  # noqa: BLE001 — one drafter failing must not stop the others
                outage &= isinstance(e, (GeminiUnavailable, requests.RequestException))
                log.warning("director: %s produced no storyboard (%s)", name, str(e)[:200])
                history.append({"drafter": name, "error": str(e)[:300]})
                continue
            outage = False
            if "unsupported" in res:
                log.warning("director: %s says the shot library can't show %r: %s", name, topic.get("id"), res["unsupported"])
                return {"passed": False, "unsupported": res["unsupported"], "drafter": name, "history": history}
            spec = VideoSpec.model_validate(res["spec"])
            try:
                stills = render_stills(_plan(spec), work / f"stills_{name}")
            except Exception as e:  # noqa: BLE001 — a scene that won't render: try the next drafter
                log.warning("director: %s storyboard failed to render (%s)", name, str(e)[:200])
                history.append({"drafter": name, "board": res["board"], "error": str(e)[:300]})
                continue
            entry = {"drafter": name, "board": res["board"]}
            try:
                entry["review"], _ = _review(spec.scenes, stills, key)
            except Exception as e:  # noqa: BLE001 — advisory only
                log.warning("director: advisory review skipped (%s)", str(e)[:200])
            history.append(entry)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps(res["spec"], indent=1))
            return {"spec": str(out_path), "passed": True, "drafter": name, "history": history}
    finally:
        _DEADLINE[0] = float("inf")
    if outage:
        raise GeminiUnavailable("every drafter was unavailable")
    return {"passed": False, "error": "no drafter produced a valid storyboard", "history": history}


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


def _review(scenes: list, stills: list[Path], key: str) -> tuple[list[dict], str]:
    """Advisory vision check: does each scene's still match its narration? Returns (scores, feedback)."""
    parts = [{"text": (
        "You check a 3D educational Reel. For each still (one per scene, in order) score 1-10 how well the image "
        "matches what the narration says at that moment (right object, right part visible, readable framing). "
        "Return JSON: {\"scenes\": [{\"id\": str, \"score\": int, "
        "\"problems\": str, \"fix\": str}]}. Scenes:\n" +
        "\n".join(f"{i + 1}. {sc.id}: objective={sc.objective!r}; narration={sc.narration!r}" for i, sc in enumerate(scenes)))}]
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



def _plan(spec: VideoSpec) -> dict:
    spec = spec.model_copy(deep=True)
    resolve_assets(spec)
    toks = tokens(spec.script)
    return resolve(spec, [(t, i / 2.6, i / 2.6 + 0.3) for i, t in enumerate(toks)], len(toks) / 2.6)


