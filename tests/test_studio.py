"""Unit tests for SceneSpec v2: schema strictness, narration alignment,
gear-train meshing, timing resolution, asset license gate, captions."""

import json
import math
import tempfile
import unittest
from pathlib import Path

from pydantic import ValidationError

from engine.studio import pipeline
from engine.studio.spec import VideoSpec, align, resolve, resolve_gear_trains, tokens

SPECS = Path(__file__).resolve().parents[1] / "engine" / "studio" / "specs"


def tiny_spec(**scene_overrides) -> dict:
    scene = {
        "id": "s1", "narration": "The gear turns fast.",
        "objects": [{"id": "g", "kind": "gear", "params": {"teeth": 20}}],
        "actions": [{"target": "g", "do": "spin", "at": "turns"}],
        "shots": [{"target": "g"}],
    }
    scene.update(scene_overrides)
    return {"title": "t", "scenes": [scene]}


def fake_heard(spec: VideoSpec, wps: float = 2.5):
    return [(t, i / wps, i / wps + 0.3) for i, t in enumerate(tokens(spec.script))]


class TestSchema(unittest.TestCase):
    def test_shipped_specs_validate(self):
        for p in SPECS.glob("*.json"):
            with self.subTest(spec=p.name):
                spec = VideoSpec.model_validate_json(p.read_text())
                self.assertGreaterEqual(len(spec.scenes), 3)

    def test_rejects_unknown_param(self):
        bad = tiny_spec(objects=[{"id": "g", "kind": "gear", "params": {"teeth": 20, "teef": 3}}])
        with self.assertRaisesRegex(ValidationError, "teef"):
            VideoSpec.model_validate(bad)

    def test_rejects_unknown_target_and_missing_phrase(self):
        with self.assertRaisesRegex(ValidationError, "unknown 'nope'"):
            VideoSpec.model_validate(tiny_spec(actions=[{"target": "nope", "do": "spin"}]))
        with self.assertRaisesRegex(ValidationError, "not in narration"):
            VideoSpec.model_validate(tiny_spec(actions=[{"target": "g", "do": "spin", "at": "explodes"}]))

    def test_rejects_code_like_fields(self):
        with self.assertRaises(ValidationError):
            VideoSpec.model_validate(tiny_spec(objects=[{"id": "g", "kind": "python", "params": {}}]))

    def test_prefab_scene_object_overrides(self):
        d = tiny_spec(use=["kit"], objects=[{"id": "g", "kind": "gear", "material": "brass", "params": {"teeth": 30}}])
        d["prefabs"] = {"kit": [{"id": "g", "kind": "gear", "params": {"teeth": 10}}, {"id": "h", "kind": "sphere"}]}
        sc = VideoSpec.model_validate(d).scenes[0]
        self.assertEqual({o.id: o.params.get("teeth") for o in sc.objects}, {"h": None, "g": 30})


class TestAlignment(unittest.TestCase):
    def test_misheard_words_are_interpolated(self):
        script = tokens("the escapement locks the wheel")
        heard = [("the", 0.0, 0.2), ("escape", 0.2, 0.5), ("mint", 0.5, 0.8), ("locks", 0.8, 1.0),
                 ("the", 1.0, 1.1), ("wheel", 1.1, 1.5)]
        t = align(script, heard)
        self.assertEqual(len(t), 5)
        self.assertAlmostEqual(t[2][0], 0.8)  # "locks" matched exactly
        self.assertTrue(0.2 <= t[1][0] < t[2][0])  # "escapement" interpolated between neighbours
        self.assertEqual([x[0] for x in t], sorted(x[0] for x in t))

    def test_no_overlap_raises(self):
        with self.assertRaises(ValueError):
            align(["a", "b"], [("zzz", 0, 1)])


class TestGearTrain(unittest.TestCase):
    def objs(self):
        g = lambda i, t, mw=None, a=0.0, p=None: {"id": i, "kind": "gear", "position": (0, 0, 0), "rotation": (0, 0, 0),
                                                  "params": {k: v for k, v in dict(teeth=t, module=0.1, pinion_teeth=p,
                                                                                   mesh_with=mw, angle=a).items() if v is not None}}
        return [g("a", 40), g("b", 30, "a", 35.0, 10), g("c", 24, "b", 100.0)]

    def test_positions_ratios_and_tooth_phase(self):
        o = self.objs()
        resolve_gear_trains(o)
        a, b, c = o
        self.assertAlmostEqual(math.dist(a["position"][:2], b["position"][:2]), 0.1 * (40 + 10) / 2)
        self.assertAlmostEqual(math.dist(b["position"][:2], c["position"][:2]), 0.1 * (30 + 24) / 2)
        self.assertAlmostEqual(b["driver"]["ratio"], -40 / 10)
        self.assertAlmostEqual(c["driver"]["ratio"], (-40 / 10) * (-30 / 24))
        # Mesh condition: parent tooth phase + child tooth phase on the line of centres ≡ 1/2 (mod 1).
        for par, ch, tp, tc, ang in ((a, b, 40, 10, 35.0), (b, c, 30, 24, 100.0)):
            s = (ang - par["rotation"][2]) / (360 / tp) + (ang + 180 - ch["rotation"][2]) / (360 / tc)
            self.assertAlmostEqual(s % 1.0, 0.5, places=6)

    def test_module_mismatch_rejected(self):
        o = self.objs()
        o[1]["params"]["module"] = 0.2
        with self.assertRaisesRegex(ValueError, "module"):
            resolve_gear_trains(o)


class TestResolve(unittest.TestCase):
    def test_scene_frames_tile_the_timeline_and_anchors_land_on_words(self):
        spec = VideoSpec.model_validate_json((SPECS / "mechanical_watch.json").read_text())
        heard = fake_heard(spec)
        plan = resolve(spec, heard, heard[-1][2])
        self.assertEqual(sum(s["frames"] for s in plan["scenes"]), round(plan["duration"] * plan["fps"]))
        for a, b in zip(plan["scenes"], plan["scenes"][1:]):
            self.assertEqual(a["frame_offset"] + a["frames"], b["frame_offset"])
        hook = plan["scenes"][0]
        pop = next(a for a in hook["actions"] if a["target"] == "battery" and a["do"] == "pop_in")
        k = next(i for i, w in enumerate(plan["words"]) if w["token"] == "battery")
        word = plan["words"][k - 1]  # anchor phrase is "no battery"
        self.assertEqual(word["token"], "no")
        self.assertEqual(pop["f0"], round(word["start"] * 30))
        spin = next(a for a in hook["actions"] if a["do"] == "spin")
        self.assertIsNone(spin["f1"])  # continuous actions run to scene end inside Blender

    def test_slower_narration_stretches_scenes(self):
        spec = VideoSpec.model_validate_json((SPECS / "jet_engine.json").read_text())
        fast, slow = fake_heard(spec, 3.0), fake_heard(spec, 2.0)
        p1, p2 = resolve(spec, fast, fast[-1][2]), resolve(spec, slow, slow[-1][2])
        self.assertTrue(all(b["frames"] > a["frames"] for a, b in zip(p1["scenes"], p2["scenes"])))


class TestPipelineHelpers(unittest.TestCase):
    def test_find_spec(self):
        self.assertEqual(pipeline.find_spec("How does a mechanical watch work?").stem, "mechanical_watch")
        self.assertEqual(pipeline.find_spec("How a jet engine works").stem, "jet_engine")
        self.assertEqual(pipeline.find_spec("How the human heart pumps blood").stem, "human_heart")
        with self.assertRaises(LookupError):
            pipeline.find_spec("How do volcanoes erupt?")

    def test_asset_license_gate(self):
        d = tiny_spec(objects=[{"id": "m", "kind": "asset", "params": {"asset_id": "teapot"}}],
                      actions=[], shots=[{"target": "m"}])
        with tempfile.TemporaryDirectory() as tmp:
            old, pipeline.ASSETS = pipeline.ASSETS, Path(tmp)
            try:
                (Path(tmp) / "manifest.json").write_text(json.dumps(
                    {"teapot": {"file": "teapot.glb", "license": "CC-BY-NC-4.0", "source": "example"}}))
                with self.assertRaises(PermissionError):
                    pipeline.resolve_assets(VideoSpec.model_validate(d))
                (Path(tmp) / "manifest.json").write_text(json.dumps(
                    {"teapot": {"file": "teapot.glb", "license": "CC0-1.0", "source": "example"}}))
                rows = pipeline.resolve_assets(spec := VideoSpec.model_validate(d))
                self.assertEqual(rows[0]["license"], "CC0-1.0")
                self.assertTrue(spec.scenes[0].objects[0].params["_path"].endswith("teapot.glb"))
            finally:
                pipeline.ASSETS = old

    def test_caption_groups_stay_inside_scenes(self):
        spec = VideoSpec.model_validate_json((SPECS / "human_heart.json").read_text())
        heard = fake_heard(spec)
        words = resolve(spec, heard, heard[-1][2])["words"]
        for g in pipeline.caption_groups(words):
            self.assertEqual(len({words[i]["scene"] for i in g}), 1)
            self.assertLessEqual(len(g), 6)


if __name__ == "__main__":
    unittest.main()


class TestStudioCI(unittest.TestCase):
    def test_shard_list_covers_every_frame_once(self):
        plan = {"scenes": [{"index": 0, "frames": 150}, {"index": 1, "frames": 61}, {"index": 2, "frames": 20}]}
        shards = pipeline.shard_list(plan, 60)
        for sc in plan["scenes"]:
            mine = [s for s in shards if s["scene"] == sc["index"]]
            frames = [f for s in mine for f in range(s["start"], s["end"] + 1)]
            self.assertEqual(frames, list(range(sc["frames"])))
            self.assertTrue(all(s["end"] - s["start"] + 1 <= 60 for s in mine))

    def test_pick_prefers_ready_then_spec_then_director(self):
        from automation import studio_ci
        from automation.topic_queue import TopicQueue
        with tempfile.TemporaryDirectory() as tmp:
            q = TopicQueue(Path(tmp) / "topics.json", Path(tmp) / "history.json")
            q.save_topics([
                {"id": "old", "status": "published"},
                {"id": "no_spec", "status": "pending"},
                {"id": "jet", "status": "pending", "spec": "jet_engine"},
                {"id": "parked", "status": "needs_spec", "spec": "jet_engine"},
            ])
            self.assertEqual([x for x in studio_ci.pick(q)][1], "render")
            self.assertEqual(studio_ci.pick(q)[0]["id"], "jet")
            q.save_topics([{"id": "no_spec", "status": "pending"}])
            self.assertEqual(studio_ci.pick(q)[1], "direct")
            q.save_topics([])
            self.assertEqual(studio_ci.pick(q), (None, "none"))

    def test_gemini_outage_keeps_topic_pending(self):
        from unittest import mock
        from automation import studio_ci
        from automation.topic_queue import TopicQueue
        from engine.studio.director import GeminiUnavailable
        with tempfile.TemporaryDirectory() as tmp:
            q = TopicQueue(Path(tmp) / "topics.json", Path(tmp) / "history.json")
            q.replenish_if_needed = lambda **k: None
            q.save_topics([{"id": "airbag", "status": "pending"}])
            with mock.patch.object(studio_ci, "TopicQueue", lambda: q), \
                 mock.patch.object(studio_ci, "direct_spec", side_effect=GeminiUnavailable("503")):
                studio_ci.cmd_prepare(Path(tmp) / "build")
            self.assertEqual(q.load_topics()[0]["status"], "pending")
            self.assertEqual(json.loads((Path(tmp) / "build" / "ci.json").read_text())["mode"], "none")


class TestBranding(unittest.TestCase):
    def test_finalize_adds_cover_and_follow_outro(self):
        import subprocess
        from engine.studio import branding
        with tempfile.TemporaryDirectory() as tmp:
            src, dst = Path(tmp) / "raw.mp4", Path(tmp) / "t_reel.mp4"
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=blue:s=270x480:r=30:d=2",
                            "-f", "lavfi", "-i", "sine=d=2", "-shortest", "-pix_fmt", "yuv420p", str(src)], check=True)
            branding.finalize(src, dst, {"id": "t", "title": "Inside X: How it works"})
            cta = branding._probe(branding.CTA_AUDIO)["dur"]
            self.assertAlmostEqual(branding._probe(dst)["dur"], 2 + cta + 0.5, delta=0.2)
            self.assertTrue((Path(tmp) / "t_cover.jpg").exists())
            first = branding._frame(dst, "0.05", Path(tmp) / "f.png")
            self.assertNotEqual(first.getpixel((135, 20)), (0, 0, 255))  # cover, not the raw blue frame


class TestKit(unittest.TestCase):
    def _spec(self, obj):
        return VideoSpec.model_validate({"title": "t", "scenes": [{"id": "a", "narration": "hello there", "objects": [obj],
                                         "actions": [], "shots": [{"frame": [obj["id"]]}]}]})

    def test_every_kit_expands_and_validates(self):
        from engine.studio import kit
        for name in kit.KIT:
            objs = self._spec({"id": "k", "kit": name, "cut": [0, -1, 0]}).scenes[0].objects
            self.assertEqual(objs[0].id, "k")
            self.assertTrue(all(o.id.startswith("k_") and o.parent for o in objs[1:]), name)

    def test_cut_plane_passes_through_kit_origin_and_gears_remap(self):
        objs = {o.id: o for o in self._spec({"id": "m", "kit": "clock_movement", "cut": [0, -1, 0]}).scenes[0].objects}
        self.assertEqual(objs["m_gear_mid"].params["mesh_with"], "m_gear_drive")
        self.assertIsNone(objs["m_gear_mid"].cut)  # moving internals stay whole
        plate = objs["m_plate"]  # at y=0.25 in kit space: plane offset compensates so it cuts at y=0
        self.assertAlmostEqual(plate.cut_offset, 0.25)

    def test_kit_example_passes_lint_and_round_trips_through_draft_spec(self):
        from engine.studio import director
        text = (Path(director.SPECS) / "examples" / "cordless_drill.json").read_text()
        self.assertEqual(director._lint(VideoSpec.model_validate_json(text)), "")
        spec = VideoSpec.model_validate_json(text)
        director._lint(spec)  # must not leave render-only params behind
        saved = spec.model_dump_json(indent=1, exclude_defaults=True)  # what a draft looks like after a save/load
        VideoSpec.model_validate_json(saved)  # what the director re-reads before rendering

    def test_unknown_kit_is_rejected(self):
        with self.assertRaises(ValidationError):
            self._spec({"id": "k", "kit": "flux_capacitor"})


class TestSceneRevision(unittest.TestCase):
    """Weak scenes are rewritten; good scenes are never touched; a worse rewrite is not accepted."""

    def test_only_weak_scenes_are_rewritten_and_kept_only_if_better(self):
        import copy
        from unittest import mock
        from engine.studio import director
        base = json.loads((Path(director.SPECS) / "examples" / "cordless_drill.json").read_text())
        extra = []
        for i in range(2):  # pad the 3-scene example to a valid 5-scene spec
            sc = copy.deepcopy(base["scenes"][1])
            sc["id"] = f"extra{i}"
            extra.append(sc)
        base["scenes"] += extra
        ids = [sc["id"] for sc in base["scenes"]]
        rewrites = []

        def fake_revise(topic, src, weak, notes, images, call=None):
            rewrites.append(list(weak))
            out = copy.deepcopy(src)
            for sc in out["scenes"]:
                if sc["id"] in weak:
                    sc["objective"] = f"v{len(rewrites)}"
            return out

        def fake_review(scenes, stills, key):
            # round 0: 'motor' weak (3), 'gears' weak (2); rewrite: motor improves to 8, gears gets worse (1)
            score = {"hook": 9, "motor": 3, "gears": 2, "extra0": 8, "extra1": 8}
            if rewrites:
                score = {"motor": 8, "gears": 1}
            return [{"id": sc.id, "score": score[sc.id], "problems": "p", "fix": "f"} for sc in scenes], ""

        fake_still = lambda plan, out: [Path(f"{sp['id']}.png") for sp in plan["scenes"]]
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(director, "_drafters", return_value=[("fake", None)]), \
                mock.patch.object(director, "draft_spec", return_value=copy.deepcopy(base)), \
                mock.patch.object(director, "revise_scenes", side_effect=fake_revise), \
                mock.patch.object(director, "_review", side_effect=fake_review):
            res = director._direct_rounds({"id": "t"}, Path(d) / "out.json", Path(d), 1, "k", [], fake_still)
            out = json.loads((Path(d) / "out.json").read_text())
        self.assertEqual(rewrites, [["motor", "gears"]])
        by_id = {sc["id"]: sc for sc in out["scenes"]}
        self.assertEqual(by_id["motor"].get("objective"), "v1")  # better rewrite accepted
        self.assertNotEqual(by_id["gears"].get("objective"), "v1")  # worse rewrite rejected
        self.assertEqual([sc["id"] for sc in out["scenes"]], ids)
        self.assertEqual(res["history"][-1]["scores"], {"hook": 9, "motor": 8, "gears": 2, "extra0": 8, "extra1": 8})
        self.assertFalse(res["passed"])


    def test_rewrite_that_fails_to_render_is_rejected_not_fatal(self):
        import copy
        from unittest import mock
        from engine.studio import director
        base = json.loads((Path(director.SPECS) / "examples" / "cordless_drill.json").read_text())
        for i in range(2):
            sc = copy.deepcopy(base["scenes"][1])
            sc["id"] = f"extra{i}"
            base["scenes"].append(sc)
        calls = []

        def still(plan, out):  # round 0 renders fine; every rewrite crashes Blender
            calls.append(out)
            if len(calls) > 1:
                raise RuntimeError("still render failed for scene motor")
            return [Path(f"{sp['id']}.png") for sp in plan["scenes"]]

        review = lambda scenes, stills, key: ([{"id": sc.id, "score": 3 if sc.id == "motor" else 8} for sc in scenes], "")
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(director, "_drafters", return_value=[("fake", None)]), \
                mock.patch.object(director, "draft_spec", return_value=copy.deepcopy(base)), \
                mock.patch.object(director, "revise_scenes", side_effect=lambda t, src, *a, **k: copy.deepcopy(src)), \
                mock.patch.object(director, "_review", side_effect=review):
            res = director._direct_rounds({"id": "t"}, Path(d) / "out.json", Path(d), 2, "k", [], still)
            self.assertTrue((Path(d) / "out.json").exists())
        self.assertEqual(len(calls), 3)  # both rounds attempted despite the crash
        self.assertFalse(res["passed"])


    def test_revise_scenes_merges_only_requested_scenes(self):
        import copy
        from engine.studio import director
        src = json.loads((Path(director.SPECS) / "examples" / "cordless_drill.json").read_text())
        for i in range(2):
            sc = copy.deepcopy(src["scenes"][1])
            sc["id"] = f"extra{i}"
            src["scenes"].append(sc)
        new_gears = copy.deepcopy(src["scenes"][2])
        new_gears["background"] = "light"
        reply = "Sure!\n```json\n" + json.dumps({"scenes": [new_gears, {"id": "hook", "narration": "hijack"}]}) + "\n```"
        out = director.revise_scenes({"id": "t"}, src, ["gears"], {"gears": "too dark"}, [], call=lambda parts: reply)
        self.assertEqual(out["scenes"][2]["background"], "light")
        self.assertEqual(out["scenes"][0], src["scenes"][0])  # scenes not asked for are ignored


class TestDirectorBudget(unittest.TestCase):
    def test_rate_limited_model_is_skipped_for_the_rest_of_the_run(self):
        from unittest import mock
        import requests
        from engine.studio import director
        r429 = mock.Mock(status_code=429, text="quota")
        r429.raise_for_status.side_effect = requests.HTTPError("429")
        with mock.patch.object(director.requests, "post", return_value=r429) as post, \
                mock.patch.object(director, "_backoff"):
            for _ in range(2):
                with self.assertRaises(requests.HTTPError):
                    director._call_gemini("hi", "m-test", "k")
        self.assertEqual(post.call_count, 2)  # one retry, then never called again this run
        director._EXHAUSTED.discard("m-test")

    def test_calls_refuse_to_start_past_the_deadline(self):
        import time
        from engine.studio import director
        director._DEADLINE[0] = time.time() + 10
        try:
            with self.assertRaises(director.GeminiUnavailable):
                director._timeout()
        finally:
            director._DEADLINE[0] = float("inf")
        self.assertEqual(director._timeout(), director.CALL_TIMEOUT)
