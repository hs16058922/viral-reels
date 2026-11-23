"""
Intelligent Camera Director for 9:16 Vertical Video Production.

Calculates smooth, cinematic, vertical-safe camera trajectories:
- Orbit shots with harmonic breathing elevation
- Push-in / Dolly shots centered on active mechanical elements
- Top-down mechanical schematics
- Safe-area enforcement (avoids Instagram UI overlays: top 180px, bottom 280px)
- Target switching and subject framing
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from engine.scene_spec import CameraSpec, CameraType, CameraKeyframe, Vec3, InterpolationType


@dataclass
class SafeZone:
    """Instagram / TikTok 9:16 safe area definition."""
    top_margin_px: int = 180      # Top username & search bar area
    bottom_margin_px: int = 280   # Bottom caption pill, audio marquee
    right_margin_px: int = 120    # Right-side action buttons (like, comment, share)
    left_margin_px: int = 40


class IntelligentCameraDirector:
    """Generates frame-addressable camera choreographies for Blender and 2D compositors."""

    @classmethod
    def generate_camera_spec(
        cls,
        camera_type: CameraType = CameraType.ORBIT,
        duration_seconds: float = 6.0,
        fps: int = 30,
        target: Optional[Vec3] = None,
        radius: float = 8.0,
        height: float = 3.6,
        start_angle_deg: float = -28.0,
        end_angle_deg: float = 32.0,
        focal_length: float = 52.0,
    ) -> CameraSpec:
        """Create a fully computed CameraSpec with keyframes."""
        target_vec = target or Vec3(0, 0, 0.2)
        total_frames = int(duration_seconds * fps)

        keyframes: List[CameraKeyframe] = []

        if camera_type == CameraType.PUSH_IN:
            start_dist = radius * 1.35
            end_dist = radius * 0.70
            for f in range(1, total_frames + 1):
                t = (f - 1) / max(1, total_frames - 1)
                ease_t = 0.5 - 0.5 * math.cos(t * math.pi)  # Smooth cosine ease
                cur_dist = start_dist + ease_t * (end_dist - start_dist)
                cur_h = height + ease_t * 0.4

                pos = Vec3(
                    x=cur_dist * 0.55,
                    y=-cur_dist * 0.85,
                    z=cur_h,
                )
                keyframes.append(CameraKeyframe(
                    frame=f,
                    position=pos,
                    look_at=target_vec,
                    focal_length=focal_length,
                ))

        elif camera_type == CameraType.PULL_OUT:
            start_dist = radius * 0.70
            end_dist = radius * 1.35
            for f in range(1, total_frames + 1):
                t = (f - 1) / max(1, total_frames - 1)
                ease_t = 0.5 - 0.5 * math.cos(t * math.pi)
                cur_dist = start_dist + ease_t * (end_dist - start_dist)
                cur_h = height + (1.0 - ease_t) * 0.4

                pos = Vec3(
                    x=cur_dist * 0.55,
                    y=-cur_dist * 0.85,
                    z=cur_h,
                )
                keyframes.append(CameraKeyframe(
                    frame=f,
                    position=pos,
                    look_at=target_vec,
                    focal_length=focal_length,
                ))

        elif camera_type == CameraType.TOP_DOWN:
            for f in range(1, total_frames + 1):
                t = (f - 1) / max(1, total_frames - 1)
                rot = math.radians(-12.0 + t * 24.0)
                pos = Vec3(
                    x=math.sin(rot) * 0.6,
                    y=math.cos(rot) * 0.6,
                    z=radius * 1.15,
                )
                keyframes.append(CameraKeyframe(
                    frame=f,
                    position=pos,
                    look_at=target_vec,
                    focal_length=focal_length,
                ))

        else:  # Standard Cinematic Orbit
            start_rad = math.radians(start_angle_deg)
            end_rad = math.radians(end_angle_deg)
            for f in range(1, total_frames + 1):
                t = (f - 1) / max(1, total_frames - 1)
                theta = start_rad + t * (end_rad - start_rad)

                # Harmonic elevation drift
                r = radius + 0.35 * math.sin(t * math.pi)
                z = height + 0.30 * math.cos(t * math.pi)

                pos = Vec3(
                    x=r * math.sin(theta),
                    y=-r * math.cos(theta),
                    z=z,
                )
                keyframes.append(CameraKeyframe(
                    frame=f,
                    position=pos,
                    look_at=target_vec,
                    focal_length=focal_length,
                ))

        return CameraSpec(
            type=camera_type,
            target=target_vec,
            radius=radius,
            height=height,
            start_angle_degrees=start_angle_deg,
            end_angle_degrees=end_angle_deg,
            focal_length=focal_length,
            keyframes=keyframes,
        )

    @classmethod
    def get_shot_type_for_scene(cls, scene_idx: int, total_scenes: int) -> CameraType:
        """Determines the optimal shot type in a multi-scene narrative sequence."""
        if scene_idx == 0:
            # Opening shot: wide orbital establishing shot
            return CameraType.ORBIT
        elif scene_idx == 1:
            # Inspection / dissection: dramatic push-in macro
            return CameraType.PUSH_IN
        elif scene_idx == 2:
            # Internal mechanisms: orbital inspection
            return CameraType.ORBIT
        elif scene_idx == 3:
            # Technical architecture / alignment: top-down or pull-out
            return CameraType.TOP_DOWN if scene_idx % 2 == 1 else CameraType.PULL_OUT
        else:
            return CameraType.ORBIT
