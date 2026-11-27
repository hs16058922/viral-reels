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

    def test_unsupported_topic_is_parked_and_next_topic_renders_in_same_run(self):
        from unittest import mock
        from automation import studio_ci
        from automation.topic_queue import TopicQueue
        with tempfile.TemporaryDirectory() as tmp:
            q = TopicQueue(Path(tmp) / "topics.json", Path(tmp) / "history.json")
            q.replenish_if_needed = lambda **k: None
            q.save_topics([{"id": "airbag", "status": "pending"}, {"id": "microwave", "status": "pending"}])
            spec = SPECS / "jet_engine.json"
            made = []

            def fake_direct(topic, work):
                made.append(topic["id"])
                return spec if topic["id"] == "microwave" else None
            with mock.patch.object(studio_ci, "TopicQueue", lambda: q), \
                 mock.patch.object(studio_ci, "direct_spec", side_effect=fake_direct), \
                 mock.patch.object(studio_ci, "spec_for", lambda t: spec if t["id"] in made[1:] else None), \
                 mock.patch.object(studio_ci.pipeline, "prepare", return_value=(None, {"scenes": [], "duration": 1}, [])), \
                 mock.patch.object(studio_ci.pipeline, "shard_list", return_value=[]):
                studio_ci.cmd_prepare(Path(tmp) / "build")
            self.assertEqual(made, ["airbag", "microwave"])
            self.assertEqual({t["id"]: t["status"] for t in q.load_topics()}["airbag"], "needs_spec")
            meta = json.loads((Path(tmp) / "build" / "ci.json").read_text())
            self.assertEqual((meta["topic"], meta["mode"]), ("microwave", "render"))


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

    def test_unknown_kit_is_rejected(self):
        with self.assertRaises(ValidationError):
            self._spec({"id": "k", "kit": "flux_capacitor"})


BOARD = {"title": "How a Microwave Heats Soup", "scenes": [
    {"id": "hook", "shot": "microwave_hero", "narration": "Your microwave never heats the plate first, it heats the "
     "water hiding inside your food.", "keywords": ["water"]},
    {"id": "mag", "shot": "magnetron_electrons", "narration": "Inside, a magnetron boils electrons off a hot "
     "cathode and whips them past copper vanes.", "callouts": [{"part": "mag_cathode", "at": "a hot cathode"}]},
    {"id": "path", "shot": "microwave_wave_path", "narration": "That makes microwaves, which travel down a "
     "metal waveguide into the cooking box.", "callouts": [{"part": "oven_waveguide", "at": "metal waveguide"}]},
    {"id": "inside", "shot": "microwave_inside", "narration": "They bounce off the metal walls while the "
     "turntable spins the soup through the hot spots.", "label": "2.45 GHZ"},
    {"id": "flip", "shot": "water_dipole_flip", "narration": "Each water molecule is lopsided, so it flips to follow "
     "the field, billions of times a second."},
    {"id": "heat", "shot": "water_molecules_jostle", "narration": "All that twisting rubs molecules together, and "
     "the friction becomes heat right inside the food."}]}


class TestShots(unittest.TestCase):
    def test_every_shot_builds_and_validates(self):
        from engine.studio import shots
        board = {"title": "t", "scenes": [{"id": n, "shot": n, "narration": "This part is working right now."}
                                          for n in shots.SHOTS]}
        spec = VideoSpec.model_validate(shots.build(board))
        self.assertEqual(len(spec.scenes), len(shots.SHOTS))
        for sc in spec.scenes:  # every advertised callout part exists in its scene
            ids = {o.id for o in sc.objects}
            self.assertLessEqual(set(shots.SHOTS[sc.id]["parts"]), ids, sc.id)

    def test_every_shot_keeps_moving_for_the_whole_scene(self):
        # QC fails a reel if any render segment is frozen; a shot must move until its last frame.
        from engine.studio import shots
        for name, s in shots.SHOTS.items():
            # camera moves ease to a stop at scene end, so the subject itself must keep moving
            moving = any(a["do"] in shots.CONTINUOUS and "duration" not in a for a in s["actions"]) or \
                any(o.get("kind") == "flow" for o in VideoSpec.model_validate(
                    shots.build({"scenes": [{"id": "x", "shot": name, "narration": "x"}]})).scenes[0].model_dump()["objects"])
            self.assertTrue(moving, f"{name}: needs a continuous action (spin/oscillate/cycle...) or flow particles")

    def test_storyboard_builds_and_survives_save_and_reload(self):
        from engine.studio import director, shots
        src = shots.build(BOARD)
        spec, err = director._check(src)
        self.assertEqual(err, "")
        self.assertEqual(spec.scenes[1].actions[-1].target, "mag_cathode")
        director._plan(spec)  # resolving assets must not leak render-only params into the saved spec
        VideoSpec.model_validate_json(json.dumps(src))

    def test_bad_shot_and_callout_are_reported_for_repair(self):
        from engine.studio import shots
        with self.assertRaisesRegex(ValueError, "unknown shot 'flux'"):
            shots.build({"scenes": [{"id": "a", "shot": "flux", "narration": "x"}]})
        with self.assertRaisesRegex(ValueError, "callout part 'oven_door'"):
            shots.build({"scenes": [{"id": "a", "shot": "soup_heating", "narration": "hot soup",
                                     "callouts": [{"part": "oven_door", "at": "hot"}]}]})


class TestDirector(unittest.TestCase):
    def _direct(self, replies, still=None):
        from unittest import mock
        from engine.studio import director
        drafters = [(n, (lambda r: lambda parts: r.pop(0))(list(r))) for n, r in replies]
        still = still or (lambda plan, out: [Path(f"{sp['id']}.png") for sp in plan["scenes"]])
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(director, "_drafters", return_value=drafters), \
                mock.patch("engine.studio.pipeline.render_stills", side_effect=still), \
                mock.patch.object(director, "_review", return_value=([], "")):
            res = director.direct({"id": "t"}, Path(d) / "out.json", Path(d))
            if res.get("passed"):
                VideoSpec.model_validate_json((Path(d) / "out.json").read_text())
        return res

    def test_invalid_answer_is_repaired_then_accepted(self):
        bad = dict(BOARD, scenes=[dict(BOARD["scenes"][0], shot="nope")] + BOARD["scenes"][1:])
        res = self._direct([("gemini", ["chatter " + json.dumps(bad), json.dumps(BOARD)])])
        self.assertTrue(res["passed"])
        self.assertEqual(res["drafter"], "gemini")

    def test_render_failure_falls_through_to_next_drafter(self):
        calls = []

        def still(plan, out):
            calls.append(out.name)
            if len(calls) == 1:
                raise RuntimeError("still render failed")
            return [Path("x.png")] * len(plan["scenes"])
        res = self._direct([("a", [json.dumps(BOARD)]), ("b", [json.dumps(BOARD)])], still)
        self.assertEqual((res["passed"], res["drafter"]), (True, "b"))

    def test_unsupported_topic_is_not_forced(self):
        res = self._direct([("gemini", ['{"unsupported": "needs an airbag inflator shot"}'])])
        self.assertFalse(res["passed"])
        self.assertIn("airbag", res["unsupported"])


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
