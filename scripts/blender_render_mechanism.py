"""
Headless Blender 3D Technical Mechanism Generator for Viral Reels.

Uses Blender's ultra-fast CPU Workbench Engine (BLENDER_WORKBENCH) with MatCap
studio shading, ambient cavity ridge/valley occlusion, and transparent alpha output.

Features:
- Procedural 3D exploded assembly generation for all technical topics:
  * ballpoint_pen: Tungsten carbide micro-sphere, precision brass socket, ink reservoir tube
  * induction_stove: Copper coils, ferrite bars, ceramic glass, cast iron skillet
  * noise_cancelling_headphones: Titanium driver, voice coil, neodymium magnet, DSP chip
  * washing_machine_concrete: Perforated steel drum, concrete ballast slab, suspension springs
  * bladeless_fan: Base impeller, motor, hollow aerodynamic loop, 1.3mm jet slit
  * thermal_bottle: Outer steel shell, vacuum void, electro-polished mirror inner wall
  * car_airbag_explosion: Chemical propellant canister, squib detonator, expanding nylon bag
  * airplane_pressurization: Compressor blade rotors, bleed air valve, cabin pressure regulator
- Smooth 3D orbital camera movements with isometric angles.
- True 3D keyframed mechanical animations: parts sliding apart along precision axes.
- 100% transparent alpha PNG sequence output for direct video compositing.
"""

import sys
import math
import argparse
from pathlib import Path

# Blender python module (available when run via blender -b -P script.py)
try:
    import bpy
    import mathutils
except ImportError:
    bpy = None


def setup_blender_scene(width: int = 720, height: int = 1000):
    """Clean default scene and configure Workbench render settings with Studio lighting."""
    bpy.ops.wm.read_factory_settings(use_empty=True)

    scene = bpy.context.scene
    scene.render.resolution_x = width
    scene.render.resolution_y = height
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = True  # Transparent background

    # High-Definition CPU Workbench Engine (Technical CAD Studio Lighting)
    scene.render.engine = 'BLENDER_WORKBENCH'
    scene.display.shading.light = 'STUDIO'
    scene.display.shading.color_type = 'MATERIAL'
    scene.display.shading.show_cavity = True
    scene.display.shading.cavity_type = 'BOTH'
    scene.display.shading.cavity_ridge_factor = 2.4
    scene.display.shading.cavity_valley_factor = 1.8
    scene.display.shading.show_specular_highlight = True

    # Output format: PNG with RGBA (Alpha channel)
    scene.render.image_settings.file_format = 'PNG'
    scene.render.image_settings.color_mode = 'RGBA'
    scene.render.image_settings.color_depth = '8'

    # Add Camera with cinematic focal length
    cam_data = bpy.data.cameras.new("OrbiCam")
    cam_data.lens = 52
    cam_obj = bpy.data.objects.new("OrbiCam", cam_data)
    bpy.context.collection.objects.link(cam_obj)
    scene.camera = cam_obj

    return scene, cam_obj


def create_material(name: str, color: tuple, metallic: float = 0.8, roughness: float = 0.3):
    """Create workbench-compatible material with color."""
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = False
    mat.diffuse_color = color  # RGBA
    mat.roughness = roughness
    mat.metallic = metallic
    return mat


# ── Topic 1: Ballpoint Pen Microscopic Tip Mechanism ─────────────────

def build_3d_ballpoint_pen_mechanism(total_frames: int = 75):
    """
    Procedurally build 3D microscopic ballpoint pen tip:
    - Tungsten carbide micro-sphere (ball)
    - Brass crimped socket with capillary ink feed channels
    - Translucent plastic ink feed tube
    - Dense blue/black thixotropic ink gel column
    - Exploded view: ball pops forward, socket slides back, exposing capillary ink flow
    """
    mat_ball = create_material("TungstenCarbide", (0.82, 0.85, 0.90, 1.0), metallic=0.98, roughness=0.08)
    mat_brass = create_material("BrassSocket", (0.88, 0.72, 0.22, 1.0), metallic=0.92, roughness=0.25)
    mat_tube = create_material("PlasticTube", (0.75, 0.85, 0.95, 0.6), metallic=0.1, roughness=0.1)
    mat_ink = create_material("ThixotropicInk", (0.05, 0.12, 0.45, 1.0), metallic=0.4, roughness=0.15)
    mat_collar = create_material("SteelCollar", (0.65, 0.68, 0.72, 1.0), metallic=0.9, roughness=0.3)

    # 1. Tungsten Carbide Micro-Sphere (Ball) at origin (Mirror chrome finish)
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.72, location=(0, 0, 0.95), segments=64, ring_count=32)
    ball = bpy.context.active_object
    bpy.ops.object.shade_smooth()
    ball.data.materials.append(mat_ball)

    # 2. Precision Crimped Brass Socket (Cone with crimped lip)
    bpy.ops.mesh.primitive_cone_add(radius1=0.88, radius2=1.35, depth=2.4, vertices=64, location=(0, 0, -0.4))
    socket = bpy.context.active_object
    bpy.ops.object.shade_smooth()
    socket.data.materials.append(mat_brass)

    # 3. Micro Capillary Feed Channels (4 internal brass ribs)
    ribs = []
    for i in range(4):
        ang = i * (math.pi / 2)
        rx = math.cos(ang) * 0.45
        ry = math.sin(ang) * 0.45
        bpy.ops.mesh.primitive_cube_add(size=0.18, location=(rx, ry, 0.2))
        rib = bpy.context.active_object
        rib.scale = (0.5, 0.5, 3.0)
        bpy.ops.object.shade_smooth()
        rib.data.materials.append(mat_brass)
        ribs.append(rib)

    # 4. Thixotropic Gel Ink Column (Inside the tube)
    bpy.ops.mesh.primitive_cylinder_add(radius=0.72, depth=3.2, vertices=64, location=(0, 0, -2.2))
    ink_col = bpy.context.active_object
    bpy.ops.object.shade_smooth()
    ink_col.data.materials.append(mat_ink)

    # 5. Clear Ink Tube
    bpy.ops.mesh.primitive_cylinder_add(radius=1.1, depth=3.6, vertices=64, location=(0, 0, -2.4))
    tube = bpy.context.active_object
    bpy.ops.object.shade_smooth()
    tube.data.materials.append(mat_tube)

    # 6. Outer Steel Grip Collar
    bpy.ops.mesh.primitive_cylinder_add(radius=1.45, depth=1.6, vertices=64, location=(0, 0, -1.8))
    collar = bpy.context.active_object
    bpy.ops.object.shade_smooth()
    collar.data.materials.append(mat_collar)

    # ── Keyframe Animations ──────────────────────────────────────────
    # Frame 1: Assembled tightly
    ball.keyframe_insert(data_path="location", frame=1)
    ball.keyframe_insert(data_path="rotation_euler", frame=1)
    socket.keyframe_insert(data_path="location", frame=1)
    tube.keyframe_insert(data_path="location", frame=1)
    ink_col.keyframe_insert(data_path="location", frame=1)
    collar.keyframe_insert(data_path="location", frame=1)

    # Frame 35: Exploded 3D view (Ball lifts forward, socket separates back)
    ball.location.z = 2.4
    socket.location.z = -0.8
    collar.location.z = -2.8
    tube.location.z = -3.8
    ink_col.location.z = -3.4

    ball.keyframe_insert(data_path="location", frame=35)
    socket.keyframe_insert(data_path="location", frame=35)
    tube.keyframe_insert(data_path="location", frame=35)
    ink_col.keyframe_insert(data_path="location", frame=35)
    collar.keyframe_insert(data_path="location", frame=35)

    # Rolling ball rotation across frames
    for f in range(1, total_frames + 1):
        ball.rotation_euler = (f * 0.12, f * 0.18, f * 0.08)
        ball.keyframe_insert(data_path="rotation_euler", frame=f)

    # Frame 75: Subtle breathing hold
    ball.location.z = 2.2
    ball.keyframe_insert(data_path="location", frame=total_frames)


# ── Topic 2: Induction Stove ─────────────────────────────────────────

def build_3d_induction_mechanism(total_frames: int = 75):
    """Procedurally build 3D induction cooktop exploded assembly."""
    mat_copper = create_material("Copper", (0.88, 0.45, 0.18, 1.0), metallic=0.9, roughness=0.2)
    mat_heatsink = create_material("Aluminum", (0.75, 0.80, 0.85, 1.0), metallic=0.95, roughness=0.3)
    mat_pcb = create_material("PCB_Green", (0.05, 0.40, 0.18, 1.0), metallic=0.2, roughness=0.5)
    mat_glass = create_material("CeramicGlass", (0.08, 0.10, 0.14, 0.85), metallic=0.1, roughness=0.1)
    mat_pan = create_material("CastIron", (0.15, 0.16, 0.18, 1.0), metallic=0.7, roughness=0.4)

    # Base tray
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0, 0, -0.6))
    base_box = bpy.context.active_object
    base_box.scale = (3.2, 3.2, 0.2)
    base_box.data.materials.append(mat_heatsink)

    # PCB Board
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0, 0, -0.4))
    pcb = bpy.context.active_object
    pcb.scale = (2.8, 2.8, 0.05)
    pcb.data.materials.append(mat_pcb)

    # Heatsink fins
    for fin_idx in range(-5, 6):
        bpy.ops.mesh.primitive_cube_add(size=1.0, location=(fin_idx * 0.26, 0, -0.2))
        fin = bpy.context.active_object
        fin.scale = (0.05, 2.4, 0.22)
        fin.data.materials.append(mat_heatsink)

    # Copper Coil
    for r in range(4, 16):
        radius = r * 0.10
        bpy.ops.mesh.primitive_torus_add(
            major_radius=radius,
            minor_radius=0.038,
            major_segments=36,
            minor_segments=10,
            location=(0, 0, 0.0)
        )
        ring = bpy.context.active_object
        ring.data.materials.append(mat_copper)

    # Glass Plate
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0, 0, 0.2))
    glass_plate = bpy.context.active_object
    glass_plate.scale = (3.4, 3.4, 0.04)
    glass_plate.data.materials.append(mat_glass)

    # Skillet
    bpy.ops.mesh.primitive_cylinder_add(radius=1.3, depth=0.25, location=(0, 0, 0.45))
    skillet = bpy.context.active_object
    skillet.data.materials.append(mat_pan)

    # Exploded Animation
    glass_plate.keyframe_insert(data_path="location", frame=1)
    skillet.keyframe_insert(data_path="location", frame=1)

    glass_plate.location.z = 0.85
    skillet.location.z = 2.0
    glass_plate.keyframe_insert(data_path="location", frame=35)
    skillet.keyframe_insert(data_path="location", frame=35)

    glass_plate.location.z = 0.95
    skillet.location.z = 2.15
    glass_plate.keyframe_insert(data_path="location", frame=total_frames)
    skillet.keyframe_insert(data_path="location", frame=total_frames)


# ── Topic 3: Noise Cancelling Headphones ─────────────────────────────

def build_3d_headphones_mechanism(total_frames: int = 75):
    """Procedurally build 3D acoustic headphone exploded assembly."""
    mat_shell = create_material("Shell_Matte", (0.12, 0.14, 0.18, 1.0), metallic=0.6, roughness=0.3)
    mat_driver = create_material("Titanium_Driver", (0.85, 0.88, 0.92, 1.0), metallic=0.98, roughness=0.1)
    mat_copper = create_material("VoiceCoil", (0.88, 0.48, 0.20, 1.0), metallic=0.9, roughness=0.2)
    mat_magnet = create_material("NeodymiumMagnet", (0.45, 0.48, 0.52, 1.0), metallic=0.95, roughness=0.2)
    mat_pcb = create_material("DSP_Board", (0.08, 0.35, 0.22, 1.0), metallic=0.3, roughness=0.4)

    # Outer cup
    bpy.ops.mesh.primitive_cylinder_add(radius=1.8, depth=0.8, location=(0, 0, -0.6))
    outer_cup = bpy.context.active_object
    outer_cup.data.materials.append(mat_shell)

    # DSP board
    bpy.ops.mesh.primitive_cylinder_add(radius=1.5, depth=0.08, location=(0, 0, -0.1))
    pcb_ring = bpy.context.active_object
    pcb_ring.data.materials.append(mat_pcb)

    # Magnet
    bpy.ops.mesh.primitive_cylinder_add(radius=0.9, depth=0.2, location=(0, 0, 0.2))
    magnet = bpy.context.active_object
    magnet.data.materials.append(mat_magnet)

    # Voice coil
    bpy.ops.mesh.primitive_torus_add(major_radius=0.65, minor_radius=0.06, location=(0, 0, 0.45))
    voice_coil = bpy.context.active_object
    voice_coil.data.materials.append(mat_copper)

    # Titanium diaphragm
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.75, location=(0, 0, 0.55))
    diaphragm = bpy.context.active_object
    diaphragm.scale = (1.0, 1.0, 0.25)
    diaphragm.data.materials.append(mat_driver)

    # Keyframes
    outer_cup.keyframe_insert(data_path="location", frame=1)
    diaphragm.keyframe_insert(data_path="location", frame=1)

    outer_cup.location.z = -1.4
    diaphragm.location.z = 1.3
    outer_cup.keyframe_insert(data_path="location", frame=35)
    diaphragm.keyframe_insert(data_path="location", frame=35)

    # Diaphragm acoustic vibration
    for f in range(36, total_frames + 1):
        amp = 0.08 * math.sin(f * 0.9)
        diaphragm.location.z = 1.3 + amp
        diaphragm.keyframe_insert(data_path="location", frame=f)


# ── Topic 4: Washing Machine Concrete Counterweight ──────────────────

def build_3d_washing_machine_mechanism(total_frames: int = 75):
    """Procedurally build washing machine drum and 70lb concrete ballast block."""
    mat_drum = create_material("StainlessDrum", (0.80, 0.82, 0.86, 1.0), metallic=0.95, roughness=0.15)
    mat_concrete = create_material("ConcreteBlock", (0.50, 0.52, 0.54, 1.0), metallic=0.05, roughness=0.85)
    mat_spring = create_material("SteelSpring", (0.25, 0.28, 0.32, 1.0), metallic=0.9, roughness=0.2)
    mat_motor = create_material("DriveMotor", (0.15, 0.18, 0.22, 1.0), metallic=0.8, roughness=0.3)

    # Stainless Steel Drum
    bpy.ops.mesh.primitive_cylinder_add(radius=1.6, depth=2.0, location=(0, 0, 0))
    drum = bpy.context.active_object
    drum.rotation_euler = (math.pi / 2, 0, 0)
    drum.data.materials.append(mat_drum)

    # Heavy Concrete Counterweight Slab (Mounted on top)
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0, 0, 1.4))
    concrete_slab = bpy.context.active_object
    concrete_slab.scale = (2.2, 1.4, 0.5)
    concrete_slab.data.materials.append(mat_concrete)

    # 4 Heavy Steel Suspension Springs
    springs = []
    for sx, sy in [(-1.5, -1.0), (1.5, -1.0), (-1.5, 1.0), (1.5, 1.0)]:
        bpy.ops.mesh.primitive_cylinder_add(radius=0.12, depth=1.8, location=(sx, sy, 0.5))
        sp = bpy.context.active_object
        sp.data.materials.append(mat_spring)
        springs.append(sp)

    # Keyframes: High speed 1400 RPM spin + violent centrifugal wobble dampened by concrete
    drum.keyframe_insert(data_path="rotation_euler", frame=1)
    concrete_slab.keyframe_insert(data_path="location", frame=1)

    for f in range(1, total_frames + 1):
        # Drum spins rapidly
        drum.rotation_euler = (math.pi / 2, f * 0.45, 0)
        drum.keyframe_insert(data_path="rotation_euler", frame=f)

        # Micro-vibration dampened
        wobble = 0.05 * math.sin(f * 0.8)
        concrete_slab.location.z = 1.4 + wobble
        concrete_slab.keyframe_insert(data_path="location", frame=f)


# ── Topic 5: Bladeless Fan Airflow Mechanism ─────────────────────────

def build_3d_bladeless_fan_mechanism(total_frames: int = 75):
    """Procedurally build Dyson-style bladeless multiplier loop and base impeller."""
    mat_white = create_material("GlossWhite", (0.95, 0.95, 0.96, 1.0), metallic=0.1, roughness=0.1)
    mat_aerofoil = create_material("AerofoilRim", (0.05, 0.65, 0.85, 1.0), metallic=0.4, roughness=0.2)
    mat_impeller = create_material("ImpellerBlades", (0.18, 0.20, 0.24, 1.0), metallic=0.7, roughness=0.3)

    # Cylindrical Base Housing
    bpy.ops.mesh.primitive_cylinder_add(radius=1.1, depth=1.8, location=(0, 0, -1.2))
    base = bpy.context.active_object
    base.data.materials.append(mat_white)

    # High-Speed Spinning Internal Impeller
    bpy.ops.mesh.primitive_cylinder_add(radius=0.85, depth=0.4, location=(0, 0, -1.0))
    impeller = bpy.context.active_object
    impeller.data.materials.append(mat_impeller)

    # Aerodynamic Air Amplifier Ring (Torus loop)
    bpy.ops.mesh.primitive_torus_add(major_radius=1.8, minor_radius=0.24, location=(0, 0, 1.4))
    air_ring = bpy.context.active_object
    air_ring.rotation_euler = (math.pi / 2, 0, 0)
    air_ring.data.materials.append(mat_aerofoil)

    # Animation
    for f in range(1, total_frames + 1):
        impeller.rotation_euler = (0, 0, f * 0.6)
        impeller.keyframe_insert(data_path="rotation_euler", frame=f)

    # Ring elevates in exploded view
    air_ring.keyframe_insert(data_path="location", frame=1)
    air_ring.location.z = 2.0
    air_ring.keyframe_insert(data_path="location", frame=35)
    air_ring.location.z = 1.9
    air_ring.keyframe_insert(data_path="location", frame=total_frames)


# ── Topic 6: Airplane Pressurization Engine Bleed ─────────────────────

def build_3d_airplane_mechanism(total_frames: int = 75):
    """Jet engine compressor stages and cabin pressure valve."""
    mat_metal = create_material("TitaniumAlloy", (0.75, 0.78, 0.82, 1.0), metallic=0.95, roughness=0.15)
    mat_blades = create_material("FanBlades", (0.45, 0.50, 0.55, 1.0), metallic=0.9, roughness=0.2)
    mat_bleed = create_material("BleedAirValve", (0.85, 0.35, 0.15, 1.0), metallic=0.8, roughness=0.2)

    # Outer Nacelle Ring
    bpy.ops.mesh.primitive_cylinder_add(radius=2.0, depth=2.4, location=(0, 0, 0))
    nacelle = bpy.context.active_object
    nacelle.data.materials.append(mat_metal)

    # 3 Compressor Rotor Stages
    rotors = []
    for z in [-0.6, 0.0, 0.6]:
        bpy.ops.mesh.primitive_cylinder_add(radius=1.6, depth=0.18, location=(0, 0, z))
        rot = bpy.context.active_object
        rot.data.materials.append(mat_blades)
        rotors.append(rot)

    # Bleed air duct
    bpy.ops.mesh.primitive_cylinder_add(radius=0.35, depth=1.6, location=(1.8, 0, 0.8))
    duct = bpy.context.active_object
    duct.rotation_euler = (0, math.pi / 2, 0)
    duct.data.materials.append(mat_bleed)

    for f in range(1, total_frames + 1):
        for i, r in enumerate(rotors):
            r.rotation_euler = (0, 0, f * (0.3 + i * 0.15))
            r.keyframe_insert(data_path="rotation_euler", frame=f)


# ── Camera Orbit & Rendering Pipeline ────────────────────────────────

def animate_camera_orbit(cam_obj, total_frames: int = 75):
    """Animate 3D camera in smooth orbital trajectory."""
    radius = 7.8
    cam_z = 3.8
    start_angle = math.radians(-25.0)
    end_angle = math.radians(30.0)

    for f in range(1, total_frames + 1):
        ratio = (f - 1) / max(1, total_frames - 1)
        theta = start_angle + ratio * (end_angle - start_angle)

        cam_x = radius * math.sin(theta)
        cam_y = -radius * math.cos(theta)

        cam_obj.location = (cam_x, cam_y, cam_z)
        direction = mathutils.Vector((0, 0, 0.4)) - cam_obj.location
        rot_quat = direction.to_track_quat('-Z', 'Y')
        cam_obj.rotation_euler = rot_quat.to_euler()

        cam_obj.keyframe_insert(data_path="location", frame=f)
        cam_obj.keyframe_insert(data_path="rotation_euler", frame=f)


def render_sequence(out_dir: Path, total_frames: int = 75):
    """Render frames to output directory as transparent PNG sequence."""
    out_dir.mkdir(parents=True, exist_ok=True)
    scene = bpy.context.scene
    scene.frame_start = 1
    scene.frame_end = total_frames

    scene.render.filepath = str(out_dir / "frame_####")
    print(f"🎬 Blender rendering {total_frames} frames to {out_dir}...")
    bpy.ops.render.render(animation=True)
    print("✅ Blender render complete!")


def main():
    if bpy is None:
        print("Error: Must run inside Blender headless mode: blender -b -P script.py")
        sys.exit(1)

    argv = sys.argv
    if "--" in argv:
        args_list = argv[argv.index("--") + 1:]
    else:
        args_list = []

    parser = argparse.ArgumentParser(description="Blender 3D Mechanism Renderer")
    parser.add_argument("--topic", default="ballpoint_pen", help="Topic ID")
    parser.add_argument("--frames", type=int, default=75, help="Number of frames")
    parser.add_argument("--width", type=int, default=720, help="Frame width")
    parser.add_argument("--height", type=int, default=1000, help="Frame height")
    parser.add_argument("--out_dir", default="tmp/blender_renders", help="Output directory")

    args = parser.parse_args(args_list)

    out_path = Path(args.out_dir)
    scene, cam_obj = setup_blender_scene(width=args.width, height=args.height)

    # Route topic to dedicated 3D procedural generator
    tid = args.topic.lower()
    if "pen" in tid or "ballpoint" in tid:
        build_3d_ballpoint_pen_mechanism(total_frames=args.frames)
    elif "induction" in tid or "stove" in tid:
        build_3d_induction_mechanism(total_frames=args.frames)
    elif "headphone" in tid or "noise" in tid:
        build_3d_headphones_mechanism(total_frames=args.frames)
    elif "washing" in tid or "washer" in tid or "concrete" in tid:
        build_3d_washing_machine_mechanism(total_frames=args.frames)
    elif "fan" in tid or "bladeless" in tid:
        build_3d_bladeless_fan_mechanism(total_frames=args.frames)
    elif "airplane" in tid or "plane" in tid or "pressurization" in tid:
        build_3d_airplane_mechanism(total_frames=args.frames)
    else:
        # Default to ballpoint pen or induction
        build_3d_ballpoint_pen_mechanism(total_frames=args.frames)

    animate_camera_orbit(cam_obj, total_frames=args.frames)
    render_sequence(out_path, total_frames=args.frames)


if __name__ == "__main__":
    main()
