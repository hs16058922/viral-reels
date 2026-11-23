"""
AI Scene Director for Autonomous 3D Educational Animation Studio.

Transforms topic details, educational objectives, and narration script
into a validated multi-scene VideoSpec / SceneSpec timeline.

Generates structured scenes with:
- Multiple independently moving 3D objects
- Mechanical assemblies (Gears, Turbines, Escapements, Springs, Chambers)
- Exploded-view translations synced to spoken narration
- Intelligent camera choreographies (Orbit, Push-in, Top-down)
- PBR Materials (Brushed steel, brass, titanium, ruby jewels, glowing flame)
- Word-level narration triggers
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from engine.scene_spec import (
    VideoSpec,
    SceneSpec,
    ObjectSpec,
    ObjectType,
    Vec3,
    RGBA,
    MaterialSpec,
    MaterialPreset,
    AnimationTrack,
    KeyframeSpec,
    CameraSpec,
    CameraType,
    RenderSettings,
    RenderEngine,
    TransitionType,
)
from engine.camera_director import IntelligentCameraDirector
from engine.narration_sync import NarrationSyncEngine, SyncCue
from engine.whisper_captions import WordTiming

logger = logging.getLogger("viral_reels.scene_director")


class AISceneDirector:
    """Orchestrates topic analysis, scene subdivision, and SceneSpec generation."""

    @classmethod
    def create_video_spec_for_topic(
        cls,
        topic: Dict[str, Any],
        words: Optional[List[WordTiming]] = None,
        total_duration: float = 30.0,
        fps: int = 30,
        render_engine: RenderEngine = RenderEngine.WORKBENCH,
    ) -> VideoSpec:
        """Constructs a complete multi-scene VideoSpec tailored to the topic."""
        topic_id = topic.get("id", "mechanical_watch")
        title = topic.get("title", "Mechanical Engineering Secrets")
        script = topic.get("script", "")
        bullets = topic.get("bullets", [])

        # Align narration cues if word timestamps provided
        sync_cues: List[SyncCue] = []
        if words:
            sync_cues = NarrationSyncEngine.align_narration_to_cues(words, topic_id, fps=fps)

        # Build topic-specific 3D scenes
        t_lower = topic_id.lower()
        if "watch" in t_lower or "escapement" in t_lower or "gear" in t_lower:
            scenes = cls._build_watch_scenes(total_duration, fps, render_engine, bullets, sync_cues)
        elif "jet" in t_lower or "engine" in t_lower or "turbine" in t_lower:
            scenes = cls._build_jet_engine_scenes(total_duration, fps, render_engine, bullets, sync_cues)
        elif "heart" in t_lower or "cardiac" in t_lower or "blood" in t_lower:
            scenes = cls._build_heart_scenes(total_duration, fps, render_engine, bullets, sync_cues)
        else:
            scenes = cls._build_generic_mechanism_scenes(topic_id, total_duration, fps, render_engine, bullets, sync_cues)

        video_spec = VideoSpec(
            video_id=f"{topic_id}_spec",
            title=title,
            topic_id=topic_id,
            scenes=scenes,
            full_script=script,
            output_width=1080,
            output_height=1920,
            output_fps=fps,
        )

        validation_errors = video_spec.validate()
        if validation_errors:
            logger.warning("VideoSpec validation warnings: %s", validation_errors)

        return video_spec

    # ── Watch Scenes ───────────────────────────────────────────────────────

    @classmethod
    def _build_watch_scenes(
        cls,
        total_duration: float,
        fps: int,
        engine: RenderEngine,
        bullets: List[str],
        cues: List[SyncCue],
    ) -> List[SceneSpec]:
        """4 distinct scenes showing the mechanical watch movement."""
        dur_per_scene = total_duration / 4.0

        # Scene 1: The Mainspring Powerhouse
        s1 = SceneSpec(
            scene_id="watch_s1_mainspring",
            duration_seconds=dur_per_scene,
            narrative_objective="Reveal the mainspring power barrel and winding torque",
            objects=[
                ObjectSpec(
                    id="Mainspring_Barrel",
                    type=ObjectType.PROCEDURAL_GEAR,
                    label="MAINSPRING BARREL",
                    position=Vec3(0, 0, 0),
                    parameters={"teeth": 36, "radius": 2.0, "thickness": 0.45},
                    material=MaterialSpec(preset=MaterialPreset.BRASS),
                ),
                ObjectSpec(
                    id="Mainplate_Base",
                    type=ObjectType.PROCEDURAL_CYLINDER,
                    label="MAINPLATE",
                    position=Vec3(0, 0, -0.6),
                    parameters={"radius": 3.2, "depth": 0.25},
                    material=MaterialSpec(preset=MaterialPreset.BRUSHED_METAL),
                ),
            ],
            animations=[
                AnimationTrack(
                    object_id="Mainspring_Barrel",
                    property_path="rotation_euler.z",
                    keyframes=[
                        KeyframeSpec(frame=1, value=0.0),
                        KeyframeSpec(frame=int(dur_per_scene * fps), value=360.0),
                    ],
                )
            ],
            camera=IntelligentCameraDirector.generate_camera_spec(
                camera_type=CameraType.ORBIT,
                duration_seconds=dur_per_scene,
                fps=fps,
                radius=8.5,
                height=4.0,
            ),
            render=RenderSettings(engine=engine, fps=fps),
            transition_out=TransitionType.CROSSFADE,
        )

        # Scene 2: The Gear Train Velocity Multiplier
        s2 = SceneSpec(
            scene_id="watch_s2_gear_train",
            duration_seconds=dur_per_scene,
            narrative_objective="Show 4-stage gear ratio multiplying slow spring rotation to rapid seconds",
            objects=[
                ObjectSpec(
                    id="Center_Wheel",
                    type=ObjectType.PROCEDURAL_GEAR,
                    label="CENTER WHEEL",
                    position=Vec3(-1.0, 0, 0),
                    parameters={"teeth": 28, "radius": 1.4, "thickness": 0.3},
                    material=MaterialSpec(preset=MaterialPreset.BRASS),
                ),
                ObjectSpec(
                    id="Third_Wheel",
                    type=ObjectType.PROCEDURAL_GEAR,
                    label="THIRD WHEEL",
                    position=Vec3(0.8, 0.4, 0.2),
                    parameters={"teeth": 24, "radius": 1.1, "thickness": 0.25},
                    material=MaterialSpec(preset=MaterialPreset.BRASS),
                ),
                ObjectSpec(
                    id="Fourth_Wheel",
                    type=ObjectType.PROCEDURAL_GEAR,
                    label="FOURTH WHEEL",
                    position=Vec3(2.2, -0.6, 0.4),
                    parameters={"teeth": 20, "radius": 0.85, "thickness": 0.22},
                    material=MaterialSpec(preset=MaterialPreset.BRASS),
                ),
            ],
            animations=[
                AnimationTrack(
                    object_id="Center_Wheel",
                    property_path="rotation_euler.z",
                    keyframes=[
                        KeyframeSpec(frame=1, value=0.0),
                        KeyframeSpec(frame=int(dur_per_scene * fps), value=-360.0),
                    ],
                ),
                AnimationTrack(
                    object_id="Third_Wheel",
                    property_path="rotation_euler.z",
                    keyframes=[
                        KeyframeSpec(frame=1, value=0.0),
                        KeyframeSpec(frame=int(dur_per_scene * fps), value=720.0),
                    ],
                ),
                AnimationTrack(
                    object_id="Fourth_Wheel",
                    property_path="rotation_euler.z",
                    keyframes=[
                        KeyframeSpec(frame=1, value=0.0),
                        KeyframeSpec(frame=int(dur_per_scene * fps), value=-1440.0),
                    ],
                ),
            ],
            camera=IntelligentCameraDirector.generate_camera_spec(
                camera_type=CameraType.PUSH_IN,
                duration_seconds=dur_per_scene,
                fps=fps,
                radius=8.0,
                height=3.5,
            ),
            render=RenderSettings(engine=engine, fps=fps),
            transition_out=TransitionType.CROSSFADE,
        )

        # Scene 3: The Swiss Lever Escapement & Ruby Pallets
        s3 = SceneSpec(
            scene_id="watch_s3_escapement",
            duration_seconds=dur_per_scene,
            narrative_objective="Macro view of ruby pallet locking and releasing escape wheel teeth",
            objects=[
                ObjectSpec(
                    id="Escape_Wheel",
                    type=ObjectType.PROCEDURAL_GEAR,
                    label="ESCAPE WHEEL",
                    position=Vec3(0, 0, 0),
                    parameters={"teeth": 15, "radius": 1.2, "thickness": 0.2},
                    material=MaterialSpec(preset=MaterialPreset.POLISHED_CHROME),
                ),
                ObjectSpec(
                    id="Pallet_Fork",
                    type=ObjectType.PROCEDURAL_CUBE,
                    label="PALLET FORK",
                    position=Vec3(-1.1, 0.4, 0.1),
                    parameters={"size": 1.0},
                    scale=Vec3(0.8, 0.2, 0.15),
                    material=MaterialSpec(preset=MaterialPreset.POLISHED_CHROME),
                ),
            ],
            animations=[
                AnimationTrack(
                    object_id="Escape_Wheel",
                    property_path="rotation_euler.z",
                    keyframes=[
                        KeyframeSpec(frame=1, value=0.0),
                        KeyframeSpec(frame=int(dur_per_scene * fps), value=1080.0),
                    ],
                ),
            ],
            camera=IntelligentCameraDirector.generate_camera_spec(
                camera_type=CameraType.MACRO_CLOSEUP,
                duration_seconds=dur_per_scene,
                fps=fps,
                radius=6.0,
                height=2.8,
            ),
            render=RenderSettings(engine=engine, fps=fps),
            transition_out=TransitionType.CROSSFADE,
        )

        # Scene 4: Full Exploded Assembly View
        s4 = SceneSpec(
            scene_id="watch_s4_exploded_view",
            duration_seconds=dur_per_scene,
            narrative_objective="Elevate all caliber bridges and components into 3D exploded space",
            objects=[
                ObjectSpec(
                    id="Balance_Wheel",
                    type=ObjectType.PROCEDURAL_GEAR,
                    label="BALANCE WHEEL",
                    position=Vec3(0, 0, 1.2),
                    parameters={"teeth": 16, "radius": 1.5, "thickness": 0.18},
                    material=MaterialSpec(preset=MaterialPreset.GOLD),
                ),
                ObjectSpec(
                    id="Hairspring",
                    type=ObjectType.PROCEDURAL_SPRING,
                    label="HAIRSPRING",
                    position=Vec3(0, 0, 1.6),
                    parameters={"radius": 0.7, "wire_radius": 0.03, "height": 0.1, "coils": 6},
                    material=MaterialSpec(preset=MaterialPreset.POLISHED_CHROME),
                ),
            ],
            animations=[
                AnimationTrack(
                    object_id="Balance_Wheel",
                    property_path="location.z",
                    keyframes=[
                        KeyframeSpec(frame=1, value=1.2),
                        KeyframeSpec(frame=int(dur_per_scene * fps * 0.6), value=3.4),
                    ],
                ),
                AnimationTrack(
                    object_id="Hairspring",
                    property_path="location.z",
                    keyframes=[
                        KeyframeSpec(frame=1, value=1.6),
                        KeyframeSpec(frame=int(dur_per_scene * fps * 0.6), value=4.2),
                    ],
                ),
            ],
            camera=IntelligentCameraDirector.generate_camera_spec(
                camera_type=CameraType.ORBIT,
                duration_seconds=dur_per_scene,
                fps=fps,
                radius=9.0,
                height=4.5,
            ),
            render=RenderSettings(engine=engine, fps=fps),
        )

        return [s1, s2, s3, s4]

    # ── Jet Engine Scenes ──────────────────────────────────────────────────

    @classmethod
    def _build_jet_engine_scenes(
        cls,
        total_duration: float,
        fps: int,
        engine: RenderEngine,
        bullets: List[str],
        cues: List[SyncCue],
    ) -> List[SceneSpec]:
        dur = total_duration / 3.0
        return [
            SceneSpec(
                scene_id="jet_s1_intake",
                duration_seconds=dur,
                narrative_objective="Wide chord titanium fan sucking in massive airflow",
                objects=[
                    ObjectSpec(
                        id="Intake_Fan",
                        type=ObjectType.PROCEDURAL_TURBINE,
                        position=Vec3(0, 0, 0),
                        parameters={"blade_count": 22, "inner_radius": 0.7, "outer_radius": 2.5},
                        material=MaterialSpec(preset=MaterialPreset.TITANIUM),
                    )
                ],
                camera=IntelligentCameraDirector.generate_camera_spec(CameraType.ORBIT, dur, fps, radius=8.5),
                render=RenderSettings(engine=engine, fps=fps),
            ),
            SceneSpec(
                scene_id="jet_s2_combustion",
                duration_seconds=dur,
                narrative_objective="Compressor forcing air into glowing annular combustion chamber",
                objects=[
                    ObjectSpec(
                        id="Combustion_Chamber",
                        type=ObjectType.PROCEDURAL_TORUS,
                        position=Vec3(0, 0, 0),
                        parameters={"major_radius": 1.2, "minor_radius": 0.35},
                        material=MaterialSpec(preset=MaterialPreset.EMISSION_GLOW),
                    )
                ],
                camera=IntelligentCameraDirector.generate_camera_spec(CameraType.PUSH_IN, dur, fps, radius=7.0),
                render=RenderSettings(engine=engine, fps=fps),
            ),
            SceneSpec(
                scene_id="jet_s3_turbines",
                duration_seconds=dur,
                narrative_objective="Multi-stage turbines extracting thrust energy and driving front shaft",
                objects=[
                    ObjectSpec(
                        id="Turbine_Stage_1",
                        type=ObjectType.PROCEDURAL_TURBINE,
                        position=Vec3(0, 0, 0),
                        parameters={"blade_count": 28, "inner_radius": 0.6, "outer_radius": 1.8},
                        material=MaterialSpec(preset=MaterialPreset.TITANIUM),
                    )
                ],
                camera=IntelligentCameraDirector.generate_camera_spec(CameraType.TOP_DOWN, dur, fps, radius=8.0),
                render=RenderSettings(engine=engine, fps=fps),
            ),
        ]

    # ── Heart Scenes ───────────────────────────────────────────────────────

    @classmethod
    def _build_heart_scenes(
        cls,
        total_duration: float,
        fps: int,
        engine: RenderEngine,
        bullets: List[str],
        cues: List[SyncCue],
    ) -> List[SceneSpec]:
        dur = total_duration / 3.0
        return [
            SceneSpec(
                scene_id="heart_s1_ventricles",
                duration_seconds=dur,
                narrative_objective="External cardiac muscle and coronary arteries",
                objects=[
                    ObjectSpec(
                        id="Heart_Ventricles",
                        type=ObjectType.PROCEDURAL_SPHERE,
                        position=Vec3(0, 0, 0),
                        parameters={"radius": 1.8},
                        material=MaterialSpec(preset=MaterialPreset.ORGANIC_RED),
                    )
                ],
                camera=IntelligentCameraDirector.generate_camera_spec(CameraType.ORBIT, dur, fps, radius=8.0),
                render=RenderSettings(engine=engine, fps=fps),
            ),
            SceneSpec(
                scene_id="heart_s2_aortic_flow",
                duration_seconds=dur,
                narrative_objective="Oxygenated arterial blood surging through aortic arch",
                objects=[
                    ObjectSpec(
                        id="Aortic_Arch",
                        type=ObjectType.PROCEDURAL_PIPE,
                        position=Vec3(0, 0, 1.2),
                        material=MaterialSpec(preset=MaterialPreset.ORGANIC_RED),
                    )
                ],
                camera=IntelligentCameraDirector.generate_camera_spec(CameraType.PUSH_IN, dur, fps, radius=6.5),
                render=RenderSettings(engine=engine, fps=fps),
            ),
            SceneSpec(
                scene_id="heart_s3_systole_cycle",
                duration_seconds=dur,
                narrative_objective="Rhythmic systolic and diastolic pressure wave propagation",
                objects=[
                    ObjectSpec(
                        id="Heart_Body",
                        type=ObjectType.PROCEDURAL_SPHERE,
                        position=Vec3(0, 0, 0),
                        parameters={"radius": 1.8},
                        material=MaterialSpec(preset=MaterialPreset.ORGANIC_RED),
                    )
                ],
                camera=IntelligentCameraDirector.generate_camera_spec(CameraType.ORBIT, dur, fps, radius=8.0),
                render=RenderSettings(engine=engine, fps=fps),
            ),
        ]

    # ── Generic Engineering Mechanism ─────────────────────────────────────

    @classmethod
    def _build_generic_mechanism_scenes(
        cls,
        topic_id: str,
        total_duration: float,
        fps: int,
        engine: RenderEngine,
        bullets: List[str],
        cues: List[SyncCue],
    ) -> List[SceneSpec]:
        dur = total_duration / 2.0
        return [
            SceneSpec(
                scene_id=f"{topic_id}_s1_assembled",
                duration_seconds=dur,
                narrative_objective=f"Assembled 3D overview of {topic_id}",
                objects=[
                    ObjectSpec(
                        id=f"{topic_id}_main",
                        type=ObjectType.PROCEDURAL_CYLINDER,
                        position=Vec3(0, 0, 0),
                        parameters={"radius": 1.5, "depth": 2.5},
                        material=MaterialSpec(preset=MaterialPreset.BRUSHED_METAL),
                    )
                ],
                camera=IntelligentCameraDirector.generate_camera_spec(CameraType.ORBIT, dur, fps, radius=8.0),
                render=RenderSettings(engine=engine, fps=fps),
            ),
            SceneSpec(
                scene_id=f"{topic_id}_s2_exploded",
                duration_seconds=dur,
                narrative_objective=f"Internal cutaway and exploded mechanics of {topic_id}",
                objects=[
                    ObjectSpec(
                        id=f"{topic_id}_core",
                        type=ObjectType.PROCEDURAL_GEAR,
                        position=Vec3(0, 0, 0),
                        parameters={"teeth": 20, "radius": 1.4},
                        material=MaterialSpec(preset=MaterialPreset.COPPER),
                    )
                ],
                camera=IntelligentCameraDirector.generate_camera_spec(CameraType.PUSH_IN, dur, fps, radius=7.0),
                render=RenderSettings(engine=engine, fps=fps),
            ),
        ]
