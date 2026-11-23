"""
Advanced Procedural 3D Mechanism and Animation Studio for Headless Blender.

Interprets SceneSpec JSON or runs modular procedural generators for:
- Mechanical assemblies (Watches, Escapements, Interlocking Gear Trains)
- Turbomachinery (Jet Engines, Multi-stage Compressors, Turbines)
- Anatomical/Biological models (Pumping Human Heart, Valves, Vascular Paths)
- Exploded-view mechanical assemblies with cinematic easing
- Cutaway / cross-section boolean visualizations
- PBR Node-based materials (Metals, Glass, Chrome, Copper, Ruby Jewels, Blood, Glowing Plasma)
- Studio multi-point lighting and vertical 9:16 camera choreography
- Deterministic frame-by-frame rendering with transparent RGBA PNG output
"""

import sys
import os
import math
import json
import argparse
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import bpy
    import mathutils
except ImportError:
    bpy = None
    mathutils = None


def set_object_shade_smooth(obj):
    """Safely enable smooth shading on mesh polygons without requiring 3D viewport context."""
    if obj and obj.type == 'MESH' and hasattr(obj.data, 'polygons'):
        for p in obj.data.polygons:
            p.use_smooth = True

def reset_scene():
    """Clear all objects, collections, and materials to start clean."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    for c in list(bpy.data.collections):
        bpy.data.collections.remove(c)
    main_col = bpy.data.collections.new("MainScene")
    bpy.context.scene.collection.children.link(main_col)
    return main_col


def configure_render_engine(
    engine: str = "BLENDER_EEVEE",
    width: int = 1080,
    height: int = 1920,
    transparent_bg: bool = True,
    samples: int = 32,
):
    """Configure render settings for headless execution."""
    scene = bpy.context.scene
    scene.render.resolution_x = width
    scene.render.resolution_y = height
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = transparent_bg

    # Validate engine
    valid_engines = ["BLENDER_EEVEE", "BLENDER_WORKBENCH", "CYCLES"]
    if engine not in valid_engines:
        engine = "BLENDER_EEVEE"

    try:
        scene.render.engine = engine
    except Exception as e:
        print(f"Warning: Failed to set engine {engine}, falling back to BLENDER_WORKBENCH: {e}")
        scene.render.engine = "BLENDER_WORKBENCH"

    if scene.render.engine == "BLENDER_WORKBENCH":
        scene.display.shading.light = 'STUDIO'
        scene.display.shading.color_type = 'MATERIAL'
        scene.display.shading.show_cavity = True
        scene.display.shading.cavity_type = 'BOTH'
        scene.display.shading.cavity_ridge_factor = 2.5
        scene.display.shading.cavity_valley_factor = 1.8
        scene.display.shading.show_specular_highlight = True
    elif scene.render.engine == "BLENDER_EEVEE":
        if hasattr(scene, "eevee"):
            eevee = scene.eevee
            if hasattr(eevee, "taa_render_samples"):
                eevee.taa_render_samples = samples
            if hasattr(eevee, "use_bloom"):
                eevee.use_bloom = True
                eevee.bloom_threshold = 0.8
                eevee.bloom_intensity = 0.05
            if hasattr(eevee, "use_gtao"):
                eevee.use_gtao = True
            if hasattr(eevee, "use_ssr"):
                eevee.use_ssr = True

    # Output settings: PNG RGBA 8-bit
    scene.render.image_settings.file_format = 'PNG'
    scene.render.image_settings.color_mode = 'RGBA'
    scene.render.image_settings.color_depth = '8'

    return scene


def setup_studio_lighting(parent_collection=None):
    """Add a professional 3-point cinematic lighting rig."""
    col = parent_collection or bpy.context.scene.collection

    # 1. Key Light (Warm, high angle)
    key_data = bpy.data.lights.new(name="KeyLight", type='AREA')
    key_data.energy = 450.0
    key_data.size = 4.0
    key_data.color = (1.0, 0.95, 0.88)
    key_obj = bpy.data.objects.new("KeyLight", key_data)
    key_obj.location = (4.5, -5.0, 6.0)
    key_obj.rotation_euler = (math.radians(45), math.radians(15), math.radians(35))
    col.objects.link(key_obj)

    # 2. Fill Light (Cool cyan, soft, low intensity)
    fill_data = bpy.data.lights.new(name="FillLight", type='AREA')
    fill_data.energy = 200.0
    fill_data.size = 6.0
    fill_data.color = (0.75, 0.88, 1.0)
    fill_obj = bpy.data.objects.new("FillLight", fill_data)
    fill_obj.location = (-5.5, -4.0, 3.5)
    fill_obj.rotation_euler = (math.radians(35), math.radians(-20), math.radians(-45))
    col.objects.link(fill_obj)

    # 3. Rim / Edge Light (High intensity accent from behind to separate edges)
    rim_data = bpy.data.lights.new(name="RimLight", type='POINT')
    rim_data.energy = 550.0
    rim_data.color = (0.0, 0.9, 1.0)  # Neon cyan rim
    rim_obj = bpy.data.objects.new("RimLight", rim_data)
    rim_obj.location = (0.0, 6.0, 4.5)
    col.objects.link(rim_obj)

    # 4. Under Accent Light (Subtle gold bounce from below)
    under_data = bpy.data.lights.new(name="UnderLight", type='POINT')
    under_data.energy = 150.0
    under_data.color = (1.0, 0.7, 0.2)
    under_obj = bpy.data.objects.new("UnderLight", under_data)
    under_obj.location = (2.0, 2.0, -4.0)
    col.objects.link(under_obj)


# ── Material Creation (PBR Node-Based & Workbench Fallback) ───────────────

def create_pbr_material(
    name: str,
    base_color: Tuple[float, float, float, float] = (0.8, 0.8, 0.8, 1.0),
    metallic: float = 0.8,
    roughness: float = 0.2,
    transmission: float = 0.0,
    ior: float = 1.45,
    emission_color: Tuple[float, float, float, float] = (0, 0, 0, 1.0),
    emission_strength: float = 0.0,
) -> bpy.types.Material:
    """Create a PBR Principled BSDF node material compatible with Eevee and Workbench."""
    mat = bpy.data.materials.new(name=name)
    mat.diffuse_color = base_color
    mat.roughness = roughness
    mat.metallic = metallic

    # Enable nodes for Eevee/Cycles
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()

    output_node = nodes.new(type="ShaderNodeOutputMaterial")
    output_node.location = (300, 0)

    bsdf = nodes.new(type="ShaderNodeBsdfPrincipled")
    bsdf.location = (0, 0)

    # Set Base Color
    if hasattr(bsdf.inputs["Base Color"], "default_value"):
        bsdf.inputs["Base Color"].default_value = base_color

    # Set Metallic & Roughness
    if "Metallic" in bsdf.inputs:
        bsdf.inputs["Metallic"].default_value = metallic
    if "Roughness" in bsdf.inputs:
        bsdf.inputs["Roughness"].default_value = roughness

    # Transmission (for Glass)
    if transmission > 0.0 and "Transmission Weight" in bsdf.inputs:
        bsdf.inputs["Transmission Weight"].default_value = transmission
    elif transmission > 0.0 and "Transmission" in bsdf.inputs:
        bsdf.inputs["Transmission"].default_value = transmission

    # IOR
    if "IOR" in bsdf.inputs:
        bsdf.inputs["IOR"].default_value = ior

    # Emission
    if emission_strength > 0.0:
        if "Emission Color" in bsdf.inputs:
            bsdf.inputs["Emission Color"].default_value = emission_color
        elif "Emission" in bsdf.inputs:
            bsdf.inputs["Emission"].default_value = emission_color
        if "Emission Strength" in bsdf.inputs:
            bsdf.inputs["Emission Strength"].default_value = emission_strength

    # Blend mode for transparency (EEVEE compatibility across Blender versions)
    if base_color[3] < 0.99 or transmission > 0.0:
        if hasattr(mat, "blend_method"):
            mat.blend_method = 'BLEND'
        if hasattr(mat, "shadow_method"):
            mat.shadow_method = 'HASHED'

    links.new(bsdf.outputs["BSDF"], output_node.inputs["Surface"])
    return mat


def get_material_preset(preset_name: str) -> bpy.types.Material:
    """Fetch or create standard high-converting technical materials."""
    p = preset_name.lower()
    if p in ("brushed_metal", "steel"):
        return create_pbr_material("BrushedMetal", (0.75, 0.78, 0.82, 1.0), metallic=0.92, roughness=0.25)
    elif p in ("polished_chrome", "chrome"):
        return create_pbr_material("PolishedChrome", (0.92, 0.94, 0.96, 1.0), metallic=0.98, roughness=0.05)
    elif p in ("copper", "copper_coil"):
        return create_pbr_material("Copper", (0.88, 0.45, 0.18, 1.0), metallic=0.90, roughness=0.20)
    elif p in ("brass", "gold"):
        return create_pbr_material("GoldBrass", (0.95, 0.75, 0.15, 1.0), metallic=0.92, roughness=0.18)
    elif p in ("titanium", "dark_metal"):
        return create_pbr_material("Titanium", (0.45, 0.48, 0.52, 1.0), metallic=0.95, roughness=0.22)
    elif p in ("cast_iron", "gunmetal"):
        return create_pbr_material("CastIron", (0.18, 0.19, 0.22, 1.0), metallic=0.75, roughness=0.45)
    elif p in ("ruby", "jewel"):
        return create_pbr_material("RubyJewel", (0.95, 0.05, 0.25, 0.85), metallic=0.1, roughness=0.08, transmission=0.8, ior=1.77)
    elif p in ("glass", "translucent"):
        return create_pbr_material("TechnicalGlass", (0.85, 0.92, 0.98, 0.4), metallic=0.05, roughness=0.05, transmission=0.92, ior=1.52)
    elif p in ("blue_plasma", "glow_cyan"):
        return create_pbr_material("GlowCyan", (0.0, 0.85, 1.0, 1.0), metallic=0.1, roughness=0.1, emission_color=(0.0, 0.85, 1.0, 1.0), emission_strength=5.0)
    elif p in ("glow_orange", "flame"):
        return create_pbr_material("GlowOrange", (1.0, 0.4, 0.05, 1.0), metallic=0.1, roughness=0.2, emission_color=(1.0, 0.4, 0.05, 1.0), emission_strength=6.0)
    elif p in ("blood_red", "arterial_blood"):
        return create_pbr_material("ArterialBlood", (0.75, 0.04, 0.06, 1.0), metallic=0.2, roughness=0.25)
    elif p in ("venous_blood", "dark_blood"):
        return create_pbr_material("VenousBlood", (0.15, 0.25, 0.65, 1.0), metallic=0.2, roughness=0.25)
    elif p in ("muscle_tissue", "cardiac_muscle"):
        return create_pbr_material("CardiacMuscle", (0.55, 0.12, 0.14, 1.0), metallic=0.1, roughness=0.5)
    elif p in ("carbon_fiber", "matte_black"):
        return create_pbr_material("CarbonMatte", (0.08, 0.09, 0.11, 1.0), metallic=0.4, roughness=0.6)
    else:
        return create_pbr_material(f"Mat_{preset_name}", (0.7, 0.72, 0.75, 1.0), metallic=0.8, roughness=0.3)


# ── Procedural 3D Geometry Primitives ─────────────────────────────────────

def create_procedural_gear(
    name: str,
    teeth: int = 24,
    radius: float = 1.8,
    thickness: float = 0.35,
    hole_radius: float = 0.45,
    material=None,
    location=(0, 0, 0),
    rotation=(0, 0, 0),
) -> bpy.types.Object:
    """Procedurally create an involute-style spur gear with central hub and teeth."""
    teeth = max(6, teeth)  # Ensure minimum teeth for valid geometry
    tooth_height = (radius * 0.22)
    outer_radius = radius + tooth_height
    inner_radius = radius - (tooth_height * 0.8)

    # Clamp hole_radius safely inside inner_radius to prevent degenerate intersecting faces
    safe_hole_radius = min(hole_radius, inner_radius * 0.75)

    verts = []
    faces = []

    # Calculate 2D profile points around the circumference
    num_pts = teeth * 4
    top_verts = []
    bot_verts = []

    for i in range(num_pts):
        angle = (2.0 * math.pi * i) / num_pts
        tooth_phase = i % 4
        # Modulate radius for gear teeth
        if tooth_phase in (1, 2):
            r = outer_radius
        else:
            r = inner_radius

        x = r * math.cos(angle)
        y = r * math.sin(angle)
        top_verts.append((x, y, thickness / 2.0))
        bot_verts.append((x, y, -thickness / 2.0))

    # Inner hole vertices
    top_hole = []
    bot_hole = []
    for i in range(teeth * 2):
        angle = (2.0 * math.pi * i) / (teeth * 2)
        x = safe_hole_radius * math.cos(angle)
        y = safe_hole_radius * math.sin(angle)
        top_hole.append((x, y, thickness / 2.0))
        bot_hole.append((x, y, -thickness / 2.0))

    # Assemble mesh geometry
    all_verts = top_verts + bot_verts + top_hole + bot_hole
    n_rim = len(top_verts)
    n_hole = len(top_hole)
    bot_offset = n_rim
    top_hole_offset = n_rim * 2
    bot_hole_offset = top_hole_offset + n_hole

    # Side walls (teeth flanks)
    for i in range(n_rim):
        nxt = (i + 1) % n_rim
        faces.append([i, nxt, nxt + bot_offset, i + bot_offset])

    # Inner hole cylinder walls
    for i in range(n_hole):
        nxt = (i + 1) % n_hole
        faces.append([top_hole_offset + i, top_hole_offset + nxt, bot_hole_offset + nxt, bot_hole_offset + i])

    # Top & Bottom flat faces (triangulate between rim and hole)
    for i in range(n_rim):
        nxt = (i + 1) % n_rim
        h_idx = int((i / n_rim) * n_hole)
        h_nxt = int(((nxt) / n_rim) * n_hole)
        faces.append([i, top_hole_offset + h_idx, top_hole_offset + h_nxt, nxt])
        faces.append([nxt + bot_offset, bot_hole_offset + h_nxt, bot_hole_offset + h_idx, i + bot_offset])

    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(all_verts, [], faces)
    mesh.update()

    gear_obj = bpy.data.objects.new(name, mesh)
    gear_obj.location = location
    gear_obj.rotation_euler = rotation
    bpy.context.collection.objects.link(gear_obj)

    if material:
        gear_obj.data.materials.append(material)

    set_object_shade_smooth(gear_obj)
    return gear_obj


def create_procedural_spring(
    name: str,
    radius: float = 0.6,
    wire_radius: float = 0.08,
    height: float = 2.4,
    coils: int = 6,
    material=None,
    location=(0, 0, 0),
) -> bpy.types.Object:
    """Create a helical helical spring using curve spiral or mesh vertices."""
    # Create curve-based spring
    curve_data = bpy.data.curves.new(name=name, type='CURVE')
    curve_data.dimensions = '3D'
    curve_data.bevel_depth = wire_radius
    curve_data.bevel_resolution = 6

    spline = curve_data.splines.new(type='POLY')
    steps_per_coil = 24
    total_steps = coils * steps_per_coil
    spline.points.add(total_steps - 1)

    for i in range(total_steps):
        t = i / float(total_steps - 1)
        angle = t * coils * 2.0 * math.pi
        x = radius * math.cos(angle)
        y = radius * math.sin(angle)
        z = (t - 0.5) * height
        spline.points[i].co = (x, y, z, 1.0)

    spring_obj = bpy.data.objects.new(name, curve_data)
    spring_obj.location = location
    bpy.context.collection.objects.link(spring_obj)

    if material:
        spring_obj.data.materials.append(material)
    return spring_obj


def create_procedural_pipe(
    name: str,
    points: List[Tuple[float, float, float]],
    radius: float = 0.25,
    material=None,
) -> bpy.types.Object:
    """Create a smooth swept 3D pipe connecting 3D coordinates."""
    curve_data = bpy.data.curves.new(name=name, type='CURVE')
    curve_data.dimensions = '3D'
    curve_data.bevel_depth = radius
    curve_data.bevel_resolution = 12

    spline = curve_data.splines.new(type='BEZIER')
    spline.bezier_points.add(len(points) - 1)

    for i, pt in enumerate(points):
        bp = spline.bezier_points[i]
        bp.co = pt
        bp.handle_left_type = 'AUTO'
        bp.handle_right_type = 'AUTO'

    pipe_obj = bpy.data.objects.new(name, curve_data)
    bpy.context.collection.objects.link(pipe_obj)

    if material:
        pipe_obj.data.materials.append(material)
    return pipe_obj


def create_procedural_turbine_stage(
    name: str,
    blade_count: int = 18,
    inner_radius: float = 0.6,
    outer_radius: float = 1.6,
    blade_thickness: float = 0.06,
    pitch_angle_deg: float = 28.0,
    material=None,
    location=(0, 0, 0),
) -> bpy.types.Object:
    """Create an aerodynamic turbine rotor with twisted airfoil blades and central hub."""
    # 1. Central Hub Cylinder
    bpy.ops.mesh.primitive_cylinder_add(
        radius=inner_radius,
        depth=0.35,
        vertices=32,
        location=(0, 0, 0)
    )
    hub = bpy.context.active_object
    hub.name = f"{name}_Hub"

    # 2. Add blades attached to hub
    blade_objs = []
    pitch_rad = math.radians(pitch_angle_deg)
    blade_span = outer_radius - inner_radius

    for b in range(blade_count):
        theta = (2.0 * math.pi * b) / blade_count
        mid_r = inner_radius + blade_span / 2.0
        bx = mid_r * math.cos(theta)
        by = mid_r * math.sin(theta)

        bpy.ops.mesh.primitive_cube_add(
            size=1.0,
            location=(bx, by, 0)
        )
        blade = bpy.context.active_object
        blade.name = f"{name}_Blade_{b}"
        # Scale: thin chord, long span, thin profile
        blade.scale = (blade_span, 0.22, blade_thickness)
        # Rotate to point along radius and pitch
        blade.rotation_euler = (pitch_rad, 0, theta)
        blade.parent = hub
        set_object_shade_smooth(blade)
        blade_objs.append(blade)

    hub.name = name
    hub.location = location
    set_object_shade_smooth(hub)

    if material:
        hub.data.materials.append(material)
    return hub


# ── Complex Hero Assembly Generators ──────────────────────────────────────

# 1. Mechanical Watch Movement
def build_mechanical_watch_studio(total_frames: int = 90, exploded: bool = True):
    """
    Builds a high-precision mechanical watch caliber assembly:
    - Mainplate and bridges (brushed silver)
    - Mainspring Barrel (brass)
    - Center Wheel, Third Wheel, Fourth Wheel, Escape Wheel (gold brass)
    - Pallet Fork with synthetic ruby jewels (crimson ruby)
    - Balance Wheel with spiraling Hairspring (gold + blued steel)
    - Exploded view elevation keyframing + interlocking rotational kinematics
    """
    mat_mainplate = get_material_preset("brushed_metal")
    mat_brass = get_material_preset("brass")
    mat_ruby = get_material_preset("ruby")
    mat_steel = get_material_preset("polished_chrome")
    mat_hairspring = create_pbr_material("HairspringBlue", (0.1, 0.35, 0.85, 1.0), metallic=0.9, roughness=0.15)

    # 1. Mainplate Base
    bpy.ops.mesh.primitive_cylinder_add(radius=3.2, depth=0.25, vertices=64, location=(0, 0, -0.6))
    mainplate = bpy.context.active_object
    mainplate.name = "Watch_Mainplate"
    mainplate.data.materials.append(mat_mainplate)

    # 2. Mainspring Barrel (Large power source)
    barrel = create_procedural_gear(
        name="Mainspring_Barrel",
        teeth=36,
        radius=1.3,
        thickness=0.35,
        hole_radius=0.2,
        material=mat_brass,
        location=(-1.2, 0.9, -0.2),
    )

    # 3. Center Wheel (Drives hour/minute)
    center_wheel = create_procedural_gear(
        name="Center_Wheel",
        teeth=28,
        radius=0.95,
        thickness=0.22,
        hole_radius=0.15,
        material=mat_brass,
        location=(0.0, 0.0, 0.1),
    )

    # 4. Third Wheel (Stepping gear)
    third_wheel = create_procedural_gear(
        name="Third_Wheel",
        teeth=24,
        radius=0.80,
        thickness=0.20,
        hole_radius=0.12,
        material=mat_brass,
        location=(1.0, -0.7, 0.3),
    )

    # 5. Fourth Wheel (Seconds wheel)
    fourth_wheel = create_procedural_gear(
        name="Fourth_Wheel",
        teeth=20,
        radius=0.65,
        thickness=0.18,
        hole_radius=0.10,
        material=mat_brass,
        location=(0.3, -1.5, 0.5),
    )

    # 6. Escape Wheel (Club-tooth star shape)
    escape_wheel = create_procedural_gear(
        name="Escape_Wheel",
        teeth=15,
        radius=0.52,
        thickness=0.15,
        hole_radius=0.08,
        material=mat_steel,
        location=(-0.6, -1.8, 0.7),
    )

    # 7. Pallet Fork with Ruby Jewel Pallets
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(-1.1, -1.4, 0.85))
    pallet_fork = bpy.context.active_object
    pallet_fork.name = "Pallet_Fork"
    pallet_fork.scale = (0.7, 0.18, 0.12)
    pallet_fork.data.materials.append(mat_steel)

    # Add 2 Ruby Pallet Jewels on the fork ends
    for j_idx, j_pos in enumerate([(-1.4, -1.35, 0.86), (-0.8, -1.45, 0.86)]):
        bpy.ops.mesh.primitive_cube_add(size=0.12, location=j_pos)
        jewel = bpy.context.active_object
        jewel.name = f"Ruby_Jewel_{j_idx+1}"
        jewel.data.materials.append(mat_ruby)
        jewel.parent = pallet_fork

    # 8. Balance Wheel with Inertial Screws
    balance_wheel = create_procedural_gear(
        name="Balance_Wheel",
        teeth=16,  # Circular balance rim
        radius=1.1,
        thickness=0.14,
        hole_radius=0.55,
        material=mat_brass,
        location=(-1.5, -0.6, 1.1),
    )
    # Spokes for balance wheel
    for spk_angle in [0, math.pi / 2, math.pi]:
        bpy.ops.mesh.primitive_cube_add(size=1.0, location=(-1.5, -0.6, 1.1))
        spk = bpy.context.active_object
        spk.scale = (2.1, 0.08, 0.1)
        spk.rotation_euler = (0, 0, spk_angle)
        spk.data.materials.append(mat_brass)
        spk.parent = balance_wheel

    # 9. Coiled Hairspring (Archimedean blue spiral)
    hairspring = create_procedural_spring(
        name="Hairspring",
        radius=0.55,
        wire_radius=0.02,
        height=0.06,
        coils=7,
        material=mat_hairspring,
        location=(-1.5, -0.6, 1.25),
    )

    # 10. Top Bridge Plates (Holding pivots in place)
    bpy.ops.mesh.primitive_cylinder_add(radius=2.2, depth=0.18, vertices=48, location=(0.2, -0.6, 1.45))
    bridge = bpy.context.active_object
    bridge.name = "Balance_Bridge"
    bridge.scale = (1.2, 0.8, 1.0)
    bridge.data.materials.append(mat_mainplate)

    # ── KEYFRAME ANIMATIONS ───────────────────────────────────────
    # A. Continuous Gear Meshing Kinematics
    for f in range(1, total_frames + 1):
        # Barrel rotates slowly
        barrel.rotation_euler.z = f * 0.02
        barrel.keyframe_insert(data_path="rotation_euler", frame=f)

        # Center wheel gear ratio (faster)
        center_wheel.rotation_euler.z = -f * 0.06
        center_wheel.keyframe_insert(data_path="rotation_euler", frame=f)

        # Third wheel
        third_wheel.rotation_euler.z = f * 0.14
        third_wheel.keyframe_insert(data_path="rotation_euler", frame=f)

        # Fourth wheel
        fourth_wheel.rotation_euler.z = -f * 0.28
        fourth_wheel.keyframe_insert(data_path="rotation_euler", frame=f)

        # Escape wheel (rapid steps)
        escape_wheel.rotation_euler.z = f * 0.65
        escape_wheel.keyframe_insert(data_path="rotation_euler", frame=f)

        # Pallet fork ticks back and forth
        tick_angle = math.sin(f * 0.8) * 0.16
        pallet_fork.rotation_euler.z = tick_angle
        pallet_fork.keyframe_insert(data_path="rotation_euler", frame=f)

        # Balance wheel oscillates 28,800 vph harmonic resonance
        balance_osc = math.sin(f * 0.8) * 1.8
        balance_wheel.rotation_euler.z = balance_osc
        balance_wheel.keyframe_insert(data_path="rotation_euler", frame=f)
        hairspring.rotation_euler.z = balance_osc * 0.95
        hairspring.keyframe_insert(data_path="rotation_euler", frame=f)

    # B. Exploded View Elevation (Frame 25 to 55: expand vertically, Frame 70+: hold)
    if exploded:
        objects_to_explode = [
            (bridge, 1.45, 3.2),
            (hairspring, 1.25, 2.5),
            (balance_wheel, 1.1, 2.0),
            (pallet_fork, 0.85, 1.4),
            (escape_wheel, 0.7, 1.1),
            (fourth_wheel, 0.5, 0.8),
            (third_wheel, 0.3, 0.5),
            (center_wheel, 0.1, 0.2),
            (mainplate, -0.6, -1.8),
        ]
        for obj, start_z, exp_z in objects_to_explode:
            obj.location.z = start_z
            obj.keyframe_insert(data_path="location", frame=1)
            obj.keyframe_insert(data_path="location", frame=20)

            # Explode out with smooth bezier ease
            obj.location.z = exp_z
            obj.keyframe_insert(data_path="location", frame=50)

            # Hold exploded view with subtle drift
            obj.location.z = exp_z + 0.1
            obj.keyframe_insert(data_path="location", frame=total_frames)


# 2. Jet Engine (Turbofan) Studio
def build_jet_engine_studio(total_frames: int = 90, exploded: bool = True):
    """
    Builds a high-bypass commercial/military turbofan engine cutaway:
    - Titanium Wide-Chord Fan Blades
    - Low-Pressure and High-Pressure Compressor Stages
    - Annular Combustion Chamber with Fuel Injectors & Glowing Plasma Flame
    - High-Pressure and Low-Pressure Turbine Discs
    - Exhaust Core Nozzle
    - External Nacelle Cowling with cutaway window
    """
    mat_fan = get_material_preset("titanium")
    mat_shaft = get_material_preset("brushed_metal")
    mat_casing = get_material_preset("cast_iron")
    mat_flame = get_material_preset("glow_orange")
    mat_nozzle = get_material_preset("dark_metal")

    # Central Drive Shaft
    bpy.ops.mesh.primitive_cylinder_add(radius=0.22, depth=6.2, location=(0, 0, 0))
    shaft = bpy.context.active_object
    shaft.name = "Engine_Shaft"
    shaft.rotation_euler = (math.pi / 2, 0, 0)
    shaft.data.materials.append(mat_shaft)

    # 1. Front Intake Fan (Large titanium blades)
    front_fan = create_procedural_turbine_stage(
        name="Intake_Fan",
        blade_count=22,
        inner_radius=0.7,
        outer_radius=2.6,
        pitch_angle_deg=34.0,
        material=mat_fan,
        location=(0, -2.4, 0),
    )
    front_fan.rotation_euler = (math.pi / 2, 0, 0)

    # Nose Cone Spinner
    bpy.ops.mesh.primitive_cone_add(radius1=0.7, radius2=0.05, depth=1.1, location=(0, -3.1, 0))
    nose_cone = bpy.context.active_object
    nose_cone.name = "Nose_Cone"
    nose_cone.rotation_euler = (-math.pi / 2, 0, 0)
    nose_cone.data.materials.append(mat_fan)
    nose_cone.parent = front_fan

    # 2. Low-Pressure Compressor (3 Stages)
    lp_stages = []
    for i, y_pos in enumerate([-1.6, -1.2, -0.8]):
        stg = create_procedural_turbine_stage(
            name=f"LPC_Stage_{i+1}",
            blade_count=18 + i * 2,
            inner_radius=0.55,
            outer_radius=1.8 - i * 0.2,
            pitch_angle_deg=28.0,
            material=mat_shaft,
            location=(0, y_pos, 0),
        )
        stg.rotation_euler = (math.pi / 2, 0, 0)
        lp_stages.append(stg)

    # 3. High-Pressure Compressor (3 Dense Stages)
    hp_stages = []
    for i, y_pos in enumerate([-0.4, 0.0, 0.4]):
        stg = create_procedural_turbine_stage(
            name=f"HPC_Stage_{i+1}",
            blade_count=26 + i * 4,
            inner_radius=0.45,
            outer_radius=1.2 - i * 0.1,
            pitch_angle_deg=22.0,
            material=mat_fan,
            location=(0, y_pos, 0),
        )
        stg.rotation_euler = (math.pi / 2, 0, 0)
        hp_stages.append(stg)

    # 4. Combustion Chamber (Glowing annular ring)
    bpy.ops.mesh.primitive_torus_add(major_radius=0.9, minor_radius=0.25, location=(0, 0.9, 0))
    combustor = bpy.context.active_object
    combustor.name = "Combustion_Chamber"
    combustor.rotation_euler = (math.pi / 2, 0, 0)
    combustor.data.materials.append(mat_flame)

    # 5. High-Pressure & Low-Pressure Turbines
    turbines = []
    for i, y_pos in enumerate([1.5, 1.9, 2.3]):
        turb = create_procedural_turbine_stage(
            name=f"Turbine_Stage_{i+1}",
            blade_count=20 + i * 4,
            inner_radius=0.5,
            outer_radius=1.1 + i * 0.25,
            pitch_angle_deg=-30.0,  # Reverse pitch to extract power
            material=mat_fan,
            location=(0, y_pos, 0),
        )
        turb.rotation_euler = (math.pi / 2, 0, 0)
        turbines.append(turb)

    # 6. Exhaust Nozzle Cone
    bpy.ops.mesh.primitive_cone_add(radius1=1.4, radius2=0.8, depth=1.6, location=(0, 3.2, 0))
    exhaust = bpy.context.active_object
    exhaust.name = "Exhaust_Nozzle"
    exhaust.rotation_euler = (math.pi / 2, 0, 0)
    exhaust.data.materials.append(mat_nozzle)

    # 7. Cutaway Outer Nacelle Casing
    bpy.ops.mesh.primitive_cylinder_add(radius=2.9, depth=6.8, location=(0, 0.2, 0))
    nacelle = bpy.context.active_object
    nacelle.name = "Outer_Nacelle"
    nacelle.rotation_euler = (math.pi / 2, 0, 0)
    nacelle.data.materials.append(mat_casing)

    # Cutaway boolean box (removes half of the nacelle so internal stages are visible)
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(2.0, 0.2, 0))
    cutter = bpy.context.active_object
    cutter.name = "Nacelle_Cutter"
    cutter.scale = (4.0, 7.5, 3.5)
    cutter.display_type = 'WIRE'
    cutter.hide_render = True

    bool_mod = nacelle.modifiers.new("Cutaway", type='BOOLEAN')
    bool_mod.object = cutter
    bool_mod.operation = 'DIFFERENCE'

    # ── ROTATION & EXPLODED ANIMATION ────────────────────────────
    for f in range(1, total_frames + 1):
        front_fan.rotation_euler.y = f * 0.4
        front_fan.keyframe_insert(data_path="rotation_euler", frame=f)

        for i, s in enumerate(lp_stages):
            s.rotation_euler.y = f * (0.4 + i * 0.05)
            s.keyframe_insert(data_path="rotation_euler", frame=f)

        for i, s in enumerate(hp_stages):
            s.rotation_euler.y = f * (0.7 + i * 0.08)
            s.keyframe_insert(data_path="rotation_euler", frame=f)

        for i, t in enumerate(turbines):
            t.rotation_euler.y = f * (0.65 - i * 0.06)
            t.keyframe_insert(data_path="rotation_euler", frame=f)

    if exploded:
        # Separate nacelle and stages along Y axis
        nacelle.location.x = 0.0
        nacelle.keyframe_insert(data_path="location", frame=1)
        nacelle.keyframe_insert(data_path="location", frame=20)

        nacelle.location.x = 3.2
        nacelle.keyframe_insert(data_path="location", frame=50)
        nacelle.location.x = 3.4
        nacelle.keyframe_insert(data_path="location", frame=total_frames)

        front_fan.location.y = -2.4
        front_fan.keyframe_insert(data_path="location", frame=20)
        front_fan.location.y = -4.2
        front_fan.keyframe_insert(data_path="location", frame=50)


# 3. Pumping Human Heart Studio
def build_human_heart_studio(total_frames: int = 90, exploded: bool = False):
    """
    Builds a 3D anatomical human heart with 4 chambers, aorta, pulmonary vessels,
    and realistic dual-phase systolic/diastolic pumping animation:
    - Left & Right Ventricles (cardiac muscle tissue)
    - Left & Right Atria
    - Aortic Arch & Brachiocephalic arteries (oxygenated red)
    - Superior & Inferior Vena Cava / Pulmonary Artery (deoxygenated blue)
    - Animated heart valves and volumetric systolic contraction
    """
    mat_muscle = get_material_preset("cardiac_muscle")
    mat_aorta = get_material_preset("arterial_blood")
    mat_pulmonary = get_material_preset("venous_blood")
    mat_valve = create_pbr_material("HeartValve", (0.9, 0.85, 0.8, 0.75), metallic=0.05, roughness=0.2, transmission=0.5)

    # 1. Ventricular Base Body (Deformed ellipsoid heart shape)
    bpy.ops.mesh.primitive_uv_sphere_add(radius=1.8, segments=48, ring_count=24, location=(0, 0, 0))
    heart_body = bpy.context.active_object
    heart_body.name = "Heart_Ventricles"
    heart_body.scale = (1.1, 0.95, 1.45)
    heart_body.data.materials.append(mat_muscle)
    set_object_shade_smooth(heart_body)

    # 2. Right Ventricle / Left Ventricle Sulcus Groove (Anterior interventricular sulcus)
    bpy.ops.mesh.primitive_cylinder_add(radius=0.12, depth=2.4, location=(0.1, -0.9, -0.1))
    sulcus = bpy.context.active_object
    sulcus.name = "Coronary_Artery"
    sulcus.rotation_euler = (math.radians(20), math.radians(15), 0)
    sulcus.data.materials.append(mat_aorta)
    sulcus.parent = heart_body

    # 3. Right Atrium (Upper chamber right)
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.9, segments=32, ring_count=16, location=(-1.1, 0.2, 1.2))
    right_atrium = bpy.context.active_object
    right_atrium.name = "Right_Atrium"
    right_atrium.scale = (0.95, 0.85, 1.1)
    right_atrium.data.materials.append(mat_muscle)
    set_object_shade_smooth(right_atrium)

    # 4. Left Atrium (Upper chamber left)
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.85, segments=32, ring_count=16, location=(0.95, 0.3, 1.3))
    left_atrium = bpy.context.active_object
    left_atrium.name = "Left_Atrium"
    left_atrium.scale = (0.9, 0.8, 1.05)
    left_atrium.data.materials.append(mat_muscle)
    set_object_shade_smooth(left_atrium)

    # 5. Aortic Arch (Sweeping high-pressure arch)
    aorta_points = [
        (0.1, 0.0, 1.2),
        (0.0, -0.2, 2.2),
        (-0.5, 0.1, 2.8),
        (-1.2, 0.3, 2.4),
        (-1.4, 0.4, 1.1),
    ]
    aorta = create_procedural_pipe("Aortic_Arch", aorta_points, radius=0.45, material=mat_aorta)

    # 3 Branching Arteries off Aorta (Brachiocephalic, Carotid, Subclavian)
    for idx, (bx, by, bz) in enumerate([(-0.3, 0.0, 2.7), (-0.6, 0.1, 2.8), (-0.9, 0.2, 2.7)]):
        bpy.ops.mesh.primitive_cylinder_add(radius=0.14, depth=0.9, location=(bx, by, bz + 0.45))
        branch = bpy.context.active_object
        branch.name = f"Aortic_Branch_{idx+1}"
        branch.rotation_euler = (math.radians(-10), math.radians(12), 0)
        branch.data.materials.append(mat_aorta)

    # 6. Pulmonary Trunk & Artery (Blue deoxygenated outflow)
    pulm_points = [
        (-0.2, -0.4, 1.0),
        (-0.1, -0.2, 1.8),
        (0.6, 0.2, 2.1),
        (1.4, 0.5, 1.8),
    ]
    pulmonary_trunk = create_procedural_pipe("Pulmonary_Trunk", pulm_points, radius=0.42, material=mat_pulmonary)

    # 7. Superior Vena Cava (Large incoming blue vein)
    bpy.ops.mesh.primitive_cylinder_add(radius=0.38, depth=1.6, location=(-1.3, 0.1, 2.0))
    vena_cava = bpy.context.active_object
    vena_cava.name = "Superior_Vena_Cava"
    vena_cava.data.materials.append(mat_pulmonary)

    # ── PUMPING CARDIAC CYCLE KEYFRAME ANIMATION ─────────────────
    # Simulates ~72 BPM: ~25 frames per heartbeat cycle
    cycle_length = 24
    for f in range(1, total_frames + 1):
        phase = (f % cycle_length) / float(cycle_length)

        # Dual-phase heartbeat:
        # Phase 0.0 - 0.2: Atrial systole (atria squeeze, ventricles relax)
        # Phase 0.25 - 0.55: Ventricular systole (violent powerful contraction)
        # Phase 0.55 - 1.0: Diastole (ventricles fill and expand)

        if phase < 0.25:
            # Atria squeeze
            atria_scale = 1.0 - 0.15 * math.sin(phase * 4.0 * math.pi)
            ventricle_scale_x = 1.1 + 0.05 * math.sin(phase * 4.0 * math.pi)
            ventricle_scale_z = 1.45 + 0.06 * math.sin(phase * 4.0 * math.pi)
        elif phase < 0.6:
            # Ventricles contract strongly (lub-dub beat)
            v_prog = (phase - 0.25) / 0.35
            contract = math.sin(v_prog * math.pi)
            ventricle_scale_x = 1.1 - 0.22 * contract
            ventricle_scale_z = 1.45 - 0.18 * contract
            atria_scale = 1.0 + 0.12 * contract
        else:
            # Relaxation (diastole rebound)
            r_prog = (phase - 0.6) / 0.4
            ventricle_scale_x = 1.1 + 0.04 * math.sin(r_prog * math.pi)
            ventricle_scale_z = 1.45 + 0.04 * math.sin(r_prog * math.pi)
            atria_scale = 1.0

        heart_body.scale = (ventricle_scale_x, ventricle_scale_x * 0.9, ventricle_scale_z)
        heart_body.keyframe_insert(data_path="scale", frame=f)

        right_atrium.scale = (0.95 * atria_scale, 0.85 * atria_scale, 1.1 * atria_scale)
        right_atrium.keyframe_insert(data_path="scale", frame=f)

        left_atrium.scale = (0.9 * atria_scale, 0.8 * atria_scale, 1.05 * atria_scale)
        left_atrium.keyframe_insert(data_path="scale", frame=f)

        # Aorta pulses with arterial surge right after ventricular contraction
        if 0.35 <= phase <= 0.65:
            surge = math.sin((phase - 0.35) / 0.3 * math.pi) * 0.12
            aorta.scale = (1.0 + surge, 1.0 + surge, 1.0 + surge)
        else:
            aorta.scale = (1.0, 1.0, 1.0)
        aorta.keyframe_insert(data_path="scale", frame=f)


# ── Intelligent Camera Choreography ───────────────────────────────────────

def animate_intelligent_camera(
    cam_obj: bpy.types.Object,
    total_frames: int = 90,
    camera_type: str = "orbit",
    target_pos: Tuple[float, float, float] = (0, 0, 0),
    radius: float = 8.5,
    height: float = 3.6,
    focal_length: float = 54.0,
):
    """
    Creates cinematic, smooth camera movements tailored for 9:16 vertical reels:
    - Orbit with subtle vertical elevation drift
    - Push-in macro shot
    - Top-down mechanical view
    - Prevents sudden jarring motions
    """
    cam_obj.data.lens = focal_length
    target_vec = mathutils.Vector(target_pos)

    if camera_type == "push_in":
        start_dist = radius * 1.3
        end_dist = radius * 0.7
        for f in range(1, total_frames + 1):
            t = (f - 1) / max(1, total_frames - 1)
            # Smooth ease-in-out
            ease_t = 0.5 - 0.5 * math.cos(t * math.pi)
            cur_dist = start_dist + ease_t * (end_dist - start_dist)
            cur_height = height + ease_t * 0.5

            cam_obj.location = (cur_dist * 0.6, -cur_dist * 0.8, cur_height)
            direction = target_vec - cam_obj.location
            cam_obj.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()
            cam_obj.keyframe_insert(data_path="location", frame=f)
            cam_obj.keyframe_insert(data_path="rotation_euler", frame=f)

    elif camera_type == "top_down":
        for f in range(1, total_frames + 1):
            t = (f - 1) / max(1, total_frames - 1)
            rot = math.radians(-15 + t * 30)
            cam_x = math.sin(rot) * 0.8
            cam_y = math.cos(rot) * 0.8
            cam_obj.location = (cam_x, cam_y, radius * 1.1)
            direction = target_vec - cam_obj.location
            cam_obj.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()
            cam_obj.keyframe_insert(data_path="location", frame=f)
            cam_obj.keyframe_insert(data_path="rotation_euler", frame=f)

    else:  # Standard cinematic orbital drift
        start_ang = math.radians(-32.0)
        end_ang = math.radians(35.0)

        for f in range(1, total_frames + 1):
            t = (f - 1) / max(1, total_frames - 1)
            theta = start_ang + t * (end_ang - start_ang)

            # Subtle orbital breathing
            r = radius + 0.4 * math.sin(t * math.pi)
            z = height + 0.35 * math.cos(t * math.pi)

            cam_x = r * math.sin(theta)
            cam_y = -r * math.cos(theta)
            cam_obj.location = (cam_x, cam_y, z)

            direction = target_vec - cam_obj.location
            cam_obj.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()
            cam_obj.keyframe_insert(data_path="location", frame=f)
            cam_obj.keyframe_insert(data_path="rotation_euler", frame=f)


# ── SceneSpec JSON Interpreter ────────────────────────────────────────────

def render_from_scenespec(spec_dict: Dict[str, Any], total_frames: int):
    """Parse SceneSpec dictionary and build objects, materials, animations."""
    objects_data = spec_dict.get("objects", [])
    built_objects = {}

    for obj_data in objects_data:
        oid = obj_data["id"]
        otype = obj_data["type"]
        pos = obj_data.get("position", {"x": 0, "y": 0, "z": 0})
        rot = obj_data.get("rotation", {"x": 0, "y": 0, "z": 0})
        params = obj_data.get("parameters", {})
        mat_data = obj_data.get("material", {})
        preset_name = mat_data.get("preset", "brushed_metal")
        mat = get_material_preset(preset_name)

        loc = (pos.get("x", 0), pos.get("y", 0), pos.get("z", 0))
        rotation = (
            math.radians(rot.get("x", 0)),
            math.radians(rot.get("y", 0)),
            math.radians(rot.get("z", 0)),
        )

        if otype == "procedural_gear":
            obj = create_procedural_gear(
                name=oid,
                teeth=params.get("teeth", 20),
                radius=params.get("radius", 1.5),
                thickness=params.get("thickness", 0.3),
                material=mat,
                location=loc,
                rotation=rotation,
            )
        elif otype == "procedural_spring":
            obj = create_procedural_spring(
                name=oid,
                radius=params.get("radius", 0.6),
                wire_radius=params.get("wire_radius", 0.08),
                height=params.get("height", 2.0),
                coils=params.get("coils", 5),
                material=mat,
                location=loc,
            )
        elif otype == "procedural_turbine":
            obj = create_procedural_turbine_stage(
                name=oid,
                blade_count=params.get("blade_count", 18),
                inner_radius=params.get("inner_radius", 0.6),
                outer_radius=params.get("outer_radius", 1.8),
                pitch_angle_deg=params.get("pitch_angle_deg", 25.0),
                material=mat,
                location=loc,
            )
        elif otype == "procedural_cylinder":
            bpy.ops.mesh.primitive_cylinder_add(
                radius=params.get("radius", 1.0),
                depth=params.get("depth", 2.0),
                location=loc,
            )
            obj = bpy.context.active_object
            obj.name = oid
            obj.rotation_euler = rotation
            obj.data.materials.append(mat)
            set_object_shade_smooth(obj)
        elif otype == "procedural_sphere":
            bpy.ops.mesh.primitive_uv_sphere_add(
                radius=params.get("radius", 1.0),
                location=loc,
            )
            obj = bpy.context.active_object
            obj.name = oid
            obj.data.materials.append(mat)
            set_object_shade_smooth(obj)
        else:
            bpy.ops.mesh.primitive_cube_add(
                size=params.get("size", 1.0),
                location=loc,
            )
            obj = bpy.context.active_object
            obj.name = oid
            obj.rotation_euler = rotation
            obj.data.materials.append(mat)
            set_object_shade_smooth(obj)

        built_objects[oid] = obj

    # Apply animations
    anims = spec_dict.get("animations", [])
    for anim in anims:
        target_oid = anim.get("object_id")
        if target_oid in built_objects:
            obj = built_objects[target_oid]
            prop = anim.get("property_path", "rotation_euler.z")
            keyframes = anim.get("keyframes", [])
            for kf in keyframes:
                frame = kf.get("frame", 1)
                val = kf.get("value", 0.0)
                if prop == "rotation_euler.z":
                    obj.rotation_euler.z = math.radians(val) if abs(val) > 6.28 else val
                    obj.keyframe_insert(data_path="rotation_euler", frame=frame)
                elif prop == "location.z":
                    obj.location.z = val
                    obj.keyframe_insert(data_path="location", frame=frame)
                elif prop == "location.y":
                    obj.location.y = val
                    obj.keyframe_insert(data_path="location", frame=frame)


# ── Main Entrypoint & CLI ─────────────────────────────────────────────────

def main():
    if bpy is None:
        print("Error: Must run inside Blender headless mode: blender -b -P blender_advanced_engine.py")
        sys.exit(1)

    argv = sys.argv
    args_list = argv[argv.index("--") + 1:] if "--" in argv else []

    parser = argparse.ArgumentParser(description="Blender Advanced 3D Engine")
    parser.add_argument("--topic", default="mechanical_watch", help="Topic ID or mode")
    parser.add_argument("--spec_file", default="", help="Path to SceneSpec JSON file")
    parser.add_argument("--frames", type=int, default=75, help="Number of frames to render")
    parser.add_argument("--width", type=int, default=720, help="Resolution width")
    parser.add_argument("--height", type=int, default=1280, help="Resolution height")
    parser.add_argument("--engine", default="BLENDER_WORKBENCH", help="BLENDER_EEVEE or BLENDER_WORKBENCH")
    parser.add_argument("--camera_type", default="orbit", help="orbit, push_in, top_down")
    parser.add_argument("--out_dir", default="tmp/blender_renders", help="Output directory")
    parser.add_argument("--save_blend", default="", help="Optional path to save .blend file")

    args = parser.parse_args(args_list)

    main_col = reset_scene()
    configure_render_engine(
        engine=args.engine,
        width=args.width,
        height=args.height,
        transparent_bg=True,
    )
    setup_studio_lighting(main_col)

    # Setup Camera
    cam_data = bpy.data.cameras.new("StudioCamera")
    cam_obj = bpy.data.objects.new("StudioCamera", cam_data)
    main_col.objects.link(cam_obj)
    bpy.context.scene.camera = cam_obj

    topic = args.topic.lower()

    if args.spec_file and Path(args.spec_file).exists():
        print(f"Loading SceneSpec from: {args.spec_file}")
        with open(args.spec_file, "r") as f:
            spec_dict = json.load(f)
        render_from_scenespec(spec_dict, total_frames=args.frames)
        animate_intelligent_camera(cam_obj, total_frames=args.frames, camera_type=args.camera_type)
    elif "watch" in topic or "escapement" in topic or "gear" in topic:
        print("⚙️ Building 3D Mechanical Watch Caliber & Escapement Studio...")
        build_mechanical_watch_studio(total_frames=args.frames, exploded=True)
        animate_intelligent_camera(cam_obj, total_frames=args.frames, camera_type=args.camera_type, radius=8.0, height=4.2)
    elif "jet" in topic or "engine" in topic or "turbine" in topic or "airplane" in topic:
        print("✈️ Building 3D Jet Engine Turbofan Cutaway Studio...")
        build_jet_engine_studio(total_frames=args.frames, exploded=True)
        animate_intelligent_camera(cam_obj, total_frames=args.frames, camera_type=args.camera_type, radius=9.5, height=3.2)
    elif "heart" in topic or "cardiac" in topic or "blood" in topic:
        print("🫀 Building 3D Pumping Human Heart & Cardiac Cycle Studio...")
        build_human_heart_studio(total_frames=args.frames, exploded=False)
        animate_intelligent_camera(cam_obj, total_frames=args.frames, camera_type=args.camera_type, radius=7.8, height=2.4)
    else:
        # Default fallback to Mechanical Watch
        print(f"Topic '{topic}' mapped to Mechanical Assembly Studio...")
        build_mechanical_watch_studio(total_frames=args.frames, exploded=True)
        animate_intelligent_camera(cam_obj, total_frames=args.frames, camera_type=args.camera_type)

    out_path = Path(args.out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    bpy.context.scene.frame_start = 1
    bpy.context.scene.frame_end = args.frames
    bpy.context.scene.render.filepath = str(out_path / "frame_####")

    if args.save_blend:
        blend_path = Path(args.save_blend)
        blend_path.parent.mkdir(parents=True, exist_ok=True)
        bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
        print(f"💾 Saved .blend project file to: {blend_path}")

    print(f"🎬 Starting render of {args.frames} frames via {args.engine} to {out_path}...")
    bpy.ops.render.render(animation=True)
    print("✅ Render complete!")


if __name__ == "__main__":
    main()
