"""
Unit and Integration Tests for Autonomous 3D Video Studio Engine.
"""

import unittest
from pathlib import Path

from engine.scene_spec import (
    SceneSpec,
    VideoSpec,
    ObjectSpec,
    ObjectType,
    Vec3,
    MaterialSpec,
    MaterialPreset,
    AnimationTrack,
    KeyframeSpec,
    CameraSpec,
    CameraType,
    RenderSettings,
    RenderEngine,
    spec_to_json,
    spec_from_json,
)
from engine.camera_director import IntelligentCameraDirector
from engine.narration_sync import NarrationSyncEngine
from engine.whisper_captions import WordTiming
from engine.quality_control import QualityControlPipeline


class TestSceneSpec(unittest.TestCase):
    def test_spec_serialization_roundtrip(self):
        scene = SceneSpec(
            scene_id="test_scene",
            duration_seconds=5.0,
            narrative_objective="Test gear rotation",
            objects=[
                ObjectSpec(
                    id="gear_1",
                    type=ObjectType.PROCEDURAL_GEAR,
                    position=Vec3(0, 0, 0),
                    material=MaterialSpec(preset=MaterialPreset.BRASS),
                )
            ],
            animations=[
                AnimationTrack(
                    object_id="gear_1",
                    property_path="rotation_euler.z",
                    keyframes=[KeyframeSpec(frame=1, value=0.0), KeyframeSpec(frame=150, value=720.0)],
                )
            ],
            camera=CameraSpec(type=CameraType.ORBIT),
            render=RenderSettings(engine=RenderEngine.WORKBENCH),
        )
        video = VideoSpec(
            video_id="test_video",
            title="Test Video",
            topic_id="test_topic",
            scenes=[scene],
        )

        json_str = spec_to_json(video)
        reloaded = spec_from_json(json_str)

        self.assertEqual(reloaded.video_id, "test_video")
        self.assertEqual(len(reloaded.scenes), 1)
        self.assertEqual(reloaded.scenes[0].objects[0].id, "gear_1")
        self.assertEqual(reloaded.scenes[0].objects[0].material.preset, MaterialPreset.BRASS)

    def test_spec_validation(self):
        # Invalid: unknown object in animation track
        scene = SceneSpec(
            scene_id="bad_scene",
            duration_seconds=3.0,
            objects=[ObjectSpec(id="obj_a", type=ObjectType.PROCEDURAL_SPHERE)],
            animations=[AnimationTrack(object_id="unknown_obj", property_path="location.z")],
        )
        issues = scene.validate()
        self.assertTrue(any("unknown object" in i for i in issues))


class TestCameraDirector(unittest.TestCase):
    def test_camera_generation(self):
        cam = IntelligentCameraDirector.generate_camera_spec(
            camera_type=CameraType.ORBIT,
            duration_seconds=2.0,
            fps=30,
            radius=8.0,
        )
        self.assertEqual(cam.type, CameraType.ORBIT)
        self.assertEqual(len(cam.keyframes), 60)
        self.assertAlmostEqual(cam.keyframes[0].position.z, 3.6 + 0.3, delta=0.5)


class TestNarrationSync(unittest.TestCase):
    def test_cue_alignment(self):
        words = [
            WordTiming(word="The", start=0.0, end=0.2),
            WordTiming(word="escapement", start=0.3, end=0.8),
            WordTiming(word="wheel", start=0.9, end=1.2),
        ]
        cues = NarrationSyncEngine.align_narration_to_cues(words, topic_id="mechanical_watch")
        self.assertGreater(len(cues), 0)
        self.assertEqual(cues[0].target_object_id, "Escape_Wheel")


if __name__ == "__main__":
    unittest.main()
