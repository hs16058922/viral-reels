"""
SceneSpec — Typed Intermediate Representation for 3D Animation Scenes.

Transforms topic+script into a timeline of executable animation instructions
that the Blender renderer can directly interpret.

Each scene defines objects, materials, animations, camera movements, overlays,
and audio synchronization cues as a structured, validated JSON-serializable spec.
"""

from __future__ import annotations

import json
import hashlib
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ── Enums ────────────────────────────────────────────────────────────────

class ObjectType(str, Enum):
    """Supported 3D object generation methods."""
    PROCEDURAL_GEAR = "procedural_gear"
    PROCEDURAL_SPRING = "procedural_spring"
    PROCEDURAL_PISTON = "procedural_piston"
    PROCEDURAL_PIPE = "procedural_pipe"
    PROCEDURAL_TURBINE = "procedural_turbine"
    PROCEDURAL_CYLINDER = "procedural_cylinder"
    PROCEDURAL_SPHERE = "procedural_sphere"
    PROCEDURAL_TORUS = "procedural_torus"
    PROCEDURAL_CONE = "procedural_cone"
    PROCEDURAL_CUBE = "procedural_cube"
    PROCEDURAL_PLATE = "procedural_plate"
    PROCEDURAL_COIL = "procedural_coil"
    PROCEDURAL_VALVE = "procedural_valve"
    PROCEDURAL_CHAMBER = "procedural_chamber"
    PROCEDURAL_BLADE_FAN = "procedural_blade_fan"
    PROCEDURAL_CONVEYOR = "procedural_conveyor"
    PROCEDURAL_RING = "procedural_ring"
    PROCEDURAL_ARROW = "procedural_arrow"
    PROCEDURAL_TEXT_3D = "procedural_text_3d"
    IMPORTED_GLTF = "imported_gltf"
    IMPORTED_OBJ = "imported_obj"
    EMPTY_AXIS = "empty_axis"


class InterpolationType(str, Enum):
    LINEAR = "linear"
    BEZIER = "bezier"
    EASE_IN = "ease_in"
    EASE_OUT = "ease_out"
    EASE_IN_OUT = "ease_in_out"
    BOUNCE = "bounce"
    ELASTIC = "elastic"
    CONSTANT = "constant"


class CameraType(str, Enum):
    ORBIT = "orbit"
    DOLLY = "dolly"
    TRACKING = "tracking"
    PUSH_IN = "push_in"
    PULL_OUT = "pull_out"
    TOP_DOWN = "top_down"
    MACRO_CLOSEUP = "macro_closeup"
    STATIC = "static"
    SPIRAL = "spiral"
    FLYTHROUGH = "flythrough"


class MaterialPreset(str, Enum):
    """PBR material presets for Eevee/Cycles rendering."""
    BRUSHED_METAL = "brushed_metal"
    POLISHED_CHROME = "polished_chrome"
    COPPER = "copper"
    BRASS = "brass"
    GOLD = "gold"
    TITANIUM = "titanium"
    CAST_IRON = "cast_iron"
    STAINLESS_STEEL = "stainless_steel"
    GLASS = "glass"
    CERAMIC = "ceramic"
    RUBBER = "rubber"
    PLASTIC_MATTE = "plastic_matte"
    PLASTIC_GLOSS = "plastic_gloss"
    CARBON_FIBER = "carbon_fiber"
    CONCRETE = "concrete"
    WOOD = "wood"
    BONE = "bone"
    ORGANIC_RED = "organic_red"
    FLUID_BLUE = "fluid_blue"
    EMISSION_GLOW = "emission_glow"
    TRANSPARENT = "transparent"
    WIREFRAME = "wireframe"
    CUSTOM = "custom"


class TransitionType(str, Enum):
    CUT = "cut"
    CROSSFADE = "crossfade"
    WIPE_LEFT = "wipe_left"
    ZOOM_IN = "zoom_in"
    ZOOM_OUT = "zoom_out"
    ROTATE_TRANSITION = "rotate_transition"


class OverlayType(str, Enum):
    LABEL = "label"
    ARROW = "arrow"
    DIMENSION_LINE = "dimension_line"
    CALLOUT = "callout"
    HIGHLIGHT_RING = "highlight_ring"
    MOTION_TRAIL = "motion_trail"
    PROGRESS_BAR = "progress_bar"


class RenderEngine(str, Enum):
    WORKBENCH = "BLENDER_WORKBENCH"
    EEVEE = "BLENDER_EEVEE"
    CYCLES = "CYCLES"


# ── Data Classes ─────────────────────────────────────────────────────────

@dataclass
class Vec3:
    """3D vector/point."""
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0

    def to_tuple(self) -> Tuple[float, float, float]:
        return (self.x, self.y, self.z)


@dataclass
class RGBA:
    """Color with alpha."""
    r: float = 0.8
    g: float = 0.8
    b: float = 0.8
    a: float = 1.0

    def to_tuple(self) -> Tuple[float, float, float, float]:
        return (self.r, self.g, self.b, self.a)


@dataclass
class MaterialSpec:
    """Material definition for a 3D object."""
    preset: MaterialPreset = MaterialPreset.BRUSHED_METAL
    color: Optional[RGBA] = None
    metallic: float = 0.8
    roughness: float = 0.3
    emission_strength: float = 0.0
    alpha: float = 1.0
    # Custom node properties (only used when preset == CUSTOM)
    custom_nodes: Optional[Dict[str, Any]] = None


@dataclass
class ObjectSpec:
    """Definition of a 3D object in a scene."""
    id: str
    type: ObjectType
    label: Optional[str] = None  # Human-readable label for overlays
    position: Vec3 = field(default_factory=Vec3)
    rotation: Vec3 = field(default_factory=Vec3)  # Euler angles in degrees
    scale: Vec3 = field(default_factory=lambda: Vec3(1.0, 1.0, 1.0))
    material: MaterialSpec = field(default_factory=MaterialSpec)
    parent_id: Optional[str] = None  # For hierarchical assemblies
    # Procedural parameters (type-specific)
    parameters: Dict[str, Any] = field(default_factory=dict)
    # Mesh quality
    segments: int = 64
    smooth_shading: bool = True
    # Modifiers
    subdivision_level: int = 0
    boolean_operand_id: Optional[str] = None  # For cutaway views
    # Visibility
    visible: bool = True
    cast_shadow: bool = True


@dataclass
class KeyframeSpec:
    """Single keyframe for an animation track."""
    frame: int
    value: float
    interpolation: InterpolationType = InterpolationType.BEZIER


@dataclass
class AnimationTrack:
    """Animation track for a single property of a single object."""
    object_id: str
    property_path: str  # e.g. "location.x", "rotation_euler.z", "scale.x"
    keyframes: List[KeyframeSpec] = field(default_factory=list)
    # Narration sync
    sync_phrase: Optional[str] = None  # Trigger when narrator says this phrase
    sync_offset_seconds: float = 0.0  # Offset from phrase start


@dataclass
class AnimationPreset:
    """Pre-built animation macro that expands to multiple tracks."""
    type: str  # "explode", "rotate_continuous", "vibrate", "pulse_scale", "path_follow"
    object_ids: List[str] = field(default_factory=list)
    start_frame: int = 1
    end_frame: int = 75
    parameters: Dict[str, Any] = field(default_factory=dict)
    sync_phrase: Optional[str] = None


@dataclass
class CameraKeyframe:
    """Camera position and target at a specific frame."""
    frame: int
    position: Vec3
    look_at: Vec3 = field(default_factory=lambda: Vec3(0, 0, 0))
    focal_length: float = 50.0
    dof_distance: Optional[float] = None
    interpolation: InterpolationType = InterpolationType.BEZIER


@dataclass
class CameraSpec:
    """Camera choreography for a scene."""
    type: CameraType = CameraType.ORBIT
    # For orbit/spiral cameras
    target: Vec3 = field(default_factory=Vec3)
    radius: float = 8.0
    height: float = 4.0
    start_angle_degrees: float = -25.0
    end_angle_degrees: float = 30.0
    # For push-in/pull-out
    start_distance: float = 12.0
    end_distance: float = 5.0
    # Focal length
    focal_length: float = 50.0
    # Depth of field
    dof_enabled: bool = False
    dof_target_id: Optional[str] = None
    dof_fstop: float = 2.8
    # Custom keyframes (overrides type-based generation)
    keyframes: List[CameraKeyframe] = field(default_factory=list)
    # 9:16 safe region padding (pixels from edges)
    safe_margin_top: int = 180
    safe_margin_bottom: int = 280


@dataclass
class OverlaySpec:
    """2D/3D overlay element (labels, arrows, dimension lines)."""
    type: OverlayType
    text: Optional[str] = None
    position: Vec3 = field(default_factory=Vec3)
    target_position: Optional[Vec3] = None  # For arrows/dimension lines
    color: RGBA = field(default_factory=lambda: RGBA(1.0, 1.0, 1.0, 1.0))
    font_size: float = 24.0
    start_frame: int = 1
    end_frame: int = 75
    animation: Optional[str] = None  # "fade_in", "slide_in", "pulse"


@dataclass
class LightSpec:
    """Light source definition."""
    type: str = "area"  # "point", "sun", "spot", "area"
    position: Vec3 = field(default_factory=lambda: Vec3(5.0, -5.0, 8.0))
    rotation: Vec3 = field(default_factory=Vec3)
    color: RGBA = field(default_factory=lambda: RGBA(1.0, 1.0, 1.0, 1.0))
    energy: float = 500.0
    size: float = 3.0
    cast_shadow: bool = True


@dataclass
class RenderSettings:
    """Render configuration."""
    engine: RenderEngine = RenderEngine.EEVEE
    width: int = 1080
    height: int = 1920
    fps: int = 30
    samples: int = 64  # For Eevee/Cycles
    transparent_background: bool = True
    # Eevee-specific
    bloom_enabled: bool = True
    bloom_threshold: float = 0.8
    ambient_occlusion: bool = True
    screen_space_reflections: bool = True
    # Quality presets
    preview_mode: bool = False  # Low-res quick preview


@dataclass
class SceneSpec:
    """Complete scene specification — the core intermediate representation."""
    scene_id: str
    duration_seconds: float
    narrative_objective: str = ""  # What this scene teaches
    # Scene content
    objects: List[ObjectSpec] = field(default_factory=list)
    animations: List[AnimationTrack] = field(default_factory=list)
    animation_presets: List[AnimationPreset] = field(default_factory=list)
    camera: CameraSpec = field(default_factory=CameraSpec)
    lights: List[LightSpec] = field(default_factory=list)
    overlays: List[OverlaySpec] = field(default_factory=list)
    render: RenderSettings = field(default_factory=RenderSettings)
    # Audio sync
    narration_text: str = ""
    sync_phrases: List[str] = field(default_factory=list)
    # Transitions
    transition_in: TransitionType = TransitionType.CUT
    transition_out: TransitionType = TransitionType.CUT
    transition_duration_frames: int = 8

    def total_frames(self) -> int:
        """Total frames based on duration and FPS."""
        return int(self.duration_seconds * self.render.fps)

    def content_hash(self) -> str:
        """Hash of spec content for caching rendered output."""
        raw = json.dumps(asdict(self), sort_keys=True, default=str)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def validate(self) -> List[str]:
        """Validate the scene spec and return list of issues."""
        issues = []
        if not self.scene_id:
            issues.append("scene_id is required")
        if self.duration_seconds <= 0:
            issues.append("duration_seconds must be positive")
        if not self.objects:
            issues.append("Scene must have at least one object")

        # Check animation references
        obj_ids = {o.id for o in self.objects}
        for anim in self.animations:
            if anim.object_id not in obj_ids:
                issues.append(f"Animation references unknown object '{anim.object_id}'")
        for preset in self.animation_presets:
            for oid in preset.object_ids:
                if oid not in obj_ids:
                    issues.append(f"Animation preset references unknown object '{oid}'")

        # Check parent references
        for obj in self.objects:
            if obj.parent_id and obj.parent_id not in obj_ids:
                issues.append(f"Object '{obj.id}' references unknown parent '{obj.parent_id}'")

        return issues


@dataclass
class VideoSpec:
    """Complete video specification — multiple scenes composited together."""
    video_id: str
    title: str
    topic_id: str
    scenes: List[SceneSpec] = field(default_factory=list)
    # Narration
    full_script: str = ""
    voice_id: str = "en-US-ChristopherNeural"
    # Output
    output_width: int = 1080
    output_height: int = 1920
    output_fps: int = 30

    def total_duration(self) -> float:
        return sum(s.duration_seconds for s in self.scenes)

    def total_frames(self) -> int:
        return sum(s.total_frames() for s in self.scenes)

    def validate(self) -> List[str]:
        issues = []
        if not self.video_id:
            issues.append("video_id is required")
        if not self.scenes:
            issues.append("Video must have at least one scene")
        for scene in self.scenes:
            scene_issues = scene.validate()
            for si in scene_issues:
                issues.append(f"Scene '{scene.scene_id}': {si}")
        return issues

    def content_hash(self) -> str:
        raw = json.dumps(asdict(self), sort_keys=True, default=str)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]


# ── Serialization ────────────────────────────────────────────────────────

def spec_to_json(spec: VideoSpec | SceneSpec, indent: int = 2) -> str:
    """Serialize a spec to JSON string."""
    return json.dumps(asdict(spec), indent=indent, default=str)


def spec_from_json(json_str: str) -> VideoSpec:
    """Deserialize a VideoSpec from JSON string."""
    data = json.loads(json_str)
    scenes = []
    for sd in data.get("scenes", []):
        objects = [ObjectSpec(**{
            **o,
            "type": ObjectType(o["type"]),
            "position": Vec3(**o.get("position", {})),
            "rotation": Vec3(**o.get("rotation", {})),
            "scale": Vec3(**o.get("scale", {"x": 1, "y": 1, "z": 1})),
            "material": MaterialSpec(**{
                **o.get("material", {}),
                "preset": MaterialPreset(o.get("material", {}).get("preset", "brushed_metal")),
                "color": RGBA(**o["material"]["color"]) if o.get("material", {}).get("color") else None,
            }),
        }) for o in sd.get("objects", [])]

        animations = [AnimationTrack(**{
            **a,
            "keyframes": [KeyframeSpec(**{
                **kf,
                "interpolation": InterpolationType(kf.get("interpolation", "bezier")),
            }) for kf in a.get("keyframes", [])],
        }) for a in sd.get("animations", [])]

        camera_data = sd.get("camera", {})
        camera = CameraSpec(**{
            **camera_data,
            "type": CameraType(camera_data.get("type", "orbit")),
            "target": Vec3(**camera_data.get("target", {})),
            "keyframes": [CameraKeyframe(**{
                **ck,
                "position": Vec3(**ck.get("position", {})),
                "look_at": Vec3(**ck.get("look_at", {})),
                "interpolation": InterpolationType(ck.get("interpolation", "bezier")),
            }) for ck in camera_data.get("keyframes", [])],
        })

        render_data = sd.get("render", {})
        render = RenderSettings(**{
            **render_data,
            "engine": RenderEngine(render_data.get("engine", "BLENDER_EEVEE_NEXT")),
        })

        scene = SceneSpec(
            scene_id=sd["scene_id"],
            duration_seconds=sd["duration_seconds"],
            narrative_objective=sd.get("narrative_objective", ""),
            objects=objects,
            animations=animations,
            animation_presets=[AnimationPreset(**ap) for ap in sd.get("animation_presets", [])],
            camera=camera,
            lights=[LightSpec(**{
                **l,
                "position": Vec3(**l.get("position", {})),
                "rotation": Vec3(**l.get("rotation", {})),
                "color": RGBA(**l.get("color", {})),
            }) for l in sd.get("lights", [])],
            overlays=[OverlaySpec(**{
                **ov,
                "type": OverlayType(ov["type"]),
                "position": Vec3(**ov.get("position", {})),
                "target_position": Vec3(**ov["target_position"]) if ov.get("target_position") else None,
                "color": RGBA(**ov.get("color", {})),
            }) for ov in sd.get("overlays", [])],
            render=render,
            narration_text=sd.get("narration_text", ""),
            sync_phrases=sd.get("sync_phrases", []),
            transition_in=TransitionType(sd.get("transition_in", "cut")),
            transition_out=TransitionType(sd.get("transition_out", "cut")),
            transition_duration_frames=sd.get("transition_duration_frames", 8),
        )
        scenes.append(scene)

    return VideoSpec(
        video_id=data["video_id"],
        title=data.get("title", ""),
        topic_id=data.get("topic_id", ""),
        scenes=scenes,
        full_script=data.get("full_script", ""),
        voice_id=data.get("voice_id", "en-US-ChristopherNeural"),
        output_width=data.get("output_width", 1080),
        output_height=data.get("output_height", 1920),
        output_fps=data.get("output_fps", 30),
    )


def save_spec(spec: VideoSpec | SceneSpec, path: Path) -> None:
    """Save spec to a JSON file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(spec_to_json(spec))


def load_spec(path: Path) -> VideoSpec:
    """Load a VideoSpec from a JSON file."""
    return spec_from_json(path.read_text())
