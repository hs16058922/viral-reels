"""Headless Blender interpreter for one resolved SceneSpec v2 scene.

    blender -b --factory-startup --disable-autoexec -noaudio \
        -P engine/studio/blender_scene.py -- --plan scene.json --out DIR ...

Only whitelisted object kinds and actions are understood; nothing from the
spec is ever eval'd. Everything is keyframed per integer frame from data,
so any frame renders identically on its own (frame-addressable, resumable).
"""

import argparse
import json
import math
import re
import sys
import time
from pathlib import Path

import bmesh
import bpy
from bpy_extras import anim_utils
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Matrix, Vector

# ── Style ────────────────────────────────────────────────────────────────

BACKGROUNDS = {"light": "#EEECE7", "blue": "#2C55C7", "dark": "#14181F"}
# name: (hex, metallic, roughness, alpha, emission_strength, coat)
PALETTE = {
    "clay": ("#F6F4F0", 0.0, 0.62, 1, 0, 0.0),
    "clay_dark": ("#2A2D33", 0.0, 0.55, 1, 0, 0.0),
    "accent": ("#E8452C", 0.0, 0.45, 1, 0, 0.2),
    "accent2": ("#F28C28", 0.0, 0.45, 1, 0, 0.2),
    "blue": ("#2F5BD3", 0.0, 0.45, 1, 0, 0.2),
    "brass": ("#D9A441", 1.0, 0.28, 1, 0, 0.0),
    "steel": ("#A3ABB4", 1.0, 0.3, 1, 0, 0.0),
    "chrome": ("#E8EBEE", 1.0, 0.1, 1, 0, 0.0),
    "dark_steel": ("#5C636D", 1.0, 0.34, 1, 0, 0.0),
    "ruby": ("#D0103A", 0.0, 0.08, 1, 0.15, 1.0),
    "glass": ("#DCE8F2", 0.0, 0.05, 0.16, 0, 1.0),
    "tissue": ("#B8323A", 0.0, 0.5, 1, 0, 0.35),
    "tissue_glass": ("#D44A52", 0.0, 0.35, 0.3, 0, 0.5),
    "blood_red": ("#E0222E", 0.0, 0.3, 1, 0.8, 0.0),
    "blood_blue": ("#3B5BDB", 0.0, 0.3, 1, 0.8, 0.0),
    "flame": ("#FF6A14", 0.0, 0.4, 1, 2.5, 0.0),
    "air": ("#9FD3FF", 0.0, 0.3, 1, 1.6, 0.0),
    "ink": ("#17191E", 0.0, 0.5, 1, 0, 0.0),
    "white": ("#FFFFFF", 0.0, 0.5, 1, 1.0, 0.0),
}
SAFE = (0.04, 0.96, 0.14, 0.80)  # x0, x1, y0 (bottom UI), y1 (top captions) in camera-view units
CONTINUOUS = {"spin", "tick", "oscillate", "pulse", "cycle"}
DEFAULT_DUR = {"pop_in": 0.45, "pop_out": 0.35, "highlight": 1.6}
EASE = {"linear": ("LINEAR", "AUTO"), "smooth": ("BEZIER", "AUTO"), "back": ("BACK", "EASE_OUT"),
        "bounce": ("BOUNCE", "EASE_OUT"), "elastic": ("ELASTIC", "EASE_OUT"), "expo": ("EXPO", "EASE_IN_OUT")}
AXIS = {"x": 0, "y": 1, "z": 2}


def lin(hex_color, alpha=1.0):
    h = str(hex_color).lstrip("#")
    if not re.fullmatch(r"[0-9a-fA-F]{6}", h):  # the AI sometimes writes a name ("#chrome"); don't crash the render
        h = "E8452C"
    c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    return tuple(x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c) + (alpha,)


def make_material(name, key):
    hx, metal, rough, alpha, emit, coat = PALETTE[key]
    m = bpy.data.materials.new(name)
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = lin(hx)
    b.inputs["Metallic"].default_value = metal
    b.inputs["Roughness"].default_value = rough
    b.inputs["Alpha"].default_value = alpha
    b.inputs["Coat Weight"].default_value = coat
    b.inputs["Emission Color"].default_value = lin(hx)
    b.inputs["Emission Strength"].default_value = emit
    m.diffuse_color = lin(hx)
    if alpha < 1:
        m.surface_render_method = "BLENDED"
    if emit == 0:
        surface_detail(m, key)
    return m


def surface_detail(m, key):
    """Break up CG-perfect surfaces: roughness variation + fine bump (machining marks, tissue grain)."""
    nt, b = m.node_tree, bsdf(m)
    organic = key in ("tissue", "tissue_glass")
    metal = PALETTE[key][1] > 0.5
    tc, noise = nt.nodes.new("ShaderNodeTexCoord"), nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 9.0 if organic else 60.0
    noise.inputs["Detail"].default_value = 6.0
    nt.links.new(tc.outputs["Object"], noise.inputs["Vector"])
    rr = nt.nodes.new("ShaderNodeMapRange")
    base = b.inputs["Roughness"].default_value
    rr.inputs["To Min"].default_value, rr.inputs["To Max"].default_value = max(0.02, base - 0.08), base + 0.1
    nt.links.new(noise.outputs["Fac"], rr.inputs["Value"])
    nt.links.new(rr.outputs["Result"], b.inputs["Roughness"])
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.18 if organic else 0.015
    bump.inputs["Distance"].default_value = 0.02 if organic else 0.002
    nt.links.new(noise.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], b.inputs["Normal"])
    if metal:
        b.inputs["Anisotropic"].default_value = 0.35
    if organic:
        b.inputs["Subsurface Weight"].default_value = 0.3
        b.inputs["Subsurface Radius"].default_value = (0.9, 0.25, 0.12)
        b.inputs["Subsurface Scale"].default_value = 0.08
        b.inputs["Coat Weight"].default_value = 0.45  # wet sheen
        b.inputs["Coat Roughness"].default_value = 0.15
    if key == "glass":
        b.inputs["Transmission Weight"].default_value = 1.0


def bsdf(mat):
    return mat.node_tree.nodes["Principled BSDF"]


# ── Keyframing ───────────────────────────────────────────────────────────

def fcurve(owner, prop, index):
    idb = owner.id_data
    ad = idb.animation_data
    if not ad or not ad.action:
        return None
    cb = anim_utils.action_get_channelbag_for_slot(ad.action, ad.action_slot)
    return cb.fcurves.find(owner.path_from_id(prop), index=max(index, 0)) if cb else None


def value_at(owner, prop, index, frame):
    fc = fcurve(owner, prop, index)
    if fc:
        return fc.evaluate(frame)
    v = getattr(owner, prop)
    return v[index] if index >= 0 else v


def key(owner, prop, frame, value, index=-1, ease="smooth"):
    if index >= 0:
        getattr(owner, prop)[index] = value
    else:
        setattr(owner, prop, value)
    owner.keyframe_insert(prop, index=index, frame=frame)
    fc = fcurve(owner, prop, index)
    interp, easing = EASE.get(ease, (ease, "AUTO"))
    for kp in fc.keyframe_points:
        if abs(kp.co.x - frame) < 0.5:
            kp.interpolation, kp.easing = interp, easing
    return fc


# ── Geometry ─────────────────────────────────────────────────────────────

def to_axis(bm, axis):
    if axis == "x":
        bmesh.ops.rotate(bm, verts=bm.verts, matrix=Matrix.Rotation(math.pi / 2, 3, "Y"))
    elif axis == "y":
        bmesh.ops.rotate(bm, verts=bm.verts, matrix=Matrix.Rotation(-math.pi / 2, 3, "X"))


def mesh_object(name, bm, smooth=False):
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for p in me.polygons:
        p.use_smooth = smooth
    return bpy.data.objects.new(name, me)


def bevel(obj, width, segments=2):
    mod = obj.modifiers.new("Bevel", "BEVEL")
    mod.width, mod.segments, mod.limit_method = width, segments, "ANGLE"
    return mod


def ring_prism(bm, outer, inner_r, z0, z1):
    """Prism from a closed outer 2D profile with a concentric circular bore."""
    n = len(outer)
    inner = [(inner_r * math.cos(2 * math.pi * i / n), inner_r * math.sin(2 * math.pi * i / n)) for i in range(n)]
    ot = [bm.verts.new((x, y, z1)) for x, y in outer]
    ob = [bm.verts.new((x, y, z0)) for x, y in outer]
    it = [bm.verts.new((x, y, z1)) for x, y in inner]
    ib = [bm.verts.new((x, y, z0)) for x, y in inner]
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new((ob[i], ob[j], ot[j], ot[i]))
        bm.faces.new((it[i], it[j], ib[j], ib[i]))
        bm.faces.new((ot[i], ot[j], it[j], it[i]))
        bm.faces.new((ib[i], ib[j], ob[j], ob[i]))


def gear_profile(teeth, module):
    r = module * teeth / 2
    ra, rr, p = r + module, r - 1.25 * module, 2 * math.pi / teeth
    pts = []
    for k in range(teeth):
        c = k * p
        for rad, f in ((rr, -0.5), (rr, -0.3), (ra, -0.13), (ra, 0.13), (rr, 0.3)):
            pts.append((rad * math.cos(c + f * p), rad * math.sin(c + f * p)))
    return pts, rr


def build_gear(name, p):
    """Spur wheel (optionally with arms/spokes like a real watch wheel), pinion, arbor, jewel."""
    teeth, m = int(p["teeth"]), float(p.get("module", 0.1))
    t = float(p.get("thickness", 0.15))
    arms = int(p.get("arms", 0))
    bm = bmesh.new()
    prof, rr = gear_profile(teeth, m)
    bore = float(p.get("bore", min(0.06, rr * 0.4)))
    if arms:
        rim_in = rr - max(1.6 * m, 0.12 * rr)
        hub = max(bore * 2.4, 0.16 * rr)
        ring_prism(bm, prof, rim_in, -t / 2, t / 2)
        circle = [(hub * math.cos(2 * math.pi * i / 48), hub * math.sin(2 * math.pi * i / 48)) for i in range(48)]
        ring_prism(bm, circle, bore, -t / 2, t / 2)
        length = rim_in - hub * 0.7
        for k in range(arms):
            a = 2 * math.pi * k / arms + math.pi / arms
            mid = (hub * 0.7 + rim_in * 1.03) / 2
            mtx = (Matrix.Translation((mid * math.cos(a), mid * math.sin(a), 0)) @ Matrix.Rotation(a, 4, "Z")
                   @ Matrix.Diagonal((length * 1.03, max(0.09 * rr, 1.2 * m), t * 0.85, 1)))
            bmesh.ops.create_cube(bm, size=1.0, matrix=mtx)
    else:
        ring_prism(bm, prof, bore, -t / 2, t / 2)
    bottom = -t / 2
    if p.get("pinion_teeth"):
        pl = float(p.get("pinion_length", 0.3))
        pprof, prr = gear_profile(int(p["pinion_teeth"]), m)
        ring_prism(bm, pprof, min(bore, prr * 0.6), -t / 2 - pl, -t / 2)
        bottom -= pl
    bmesh.ops.create_cone(bm, cap_ends=True, segments=24, radius1=bore, radius2=bore,
                          depth=(t / 2 - bottom) + 0.12,
                          matrix=Matrix.Translation((0, 0, (t / 2 + bottom) / 2)))
    if p.get("jewel"):  # ruby jewel bearing seated on the arbor (material slot 1)
        before = set(bm.faces)
        bmesh.ops.create_cone(bm, cap_ends=True, segments=32, radius1=bore * 2.6, radius2=bore * 2.2,
                              depth=0.035, matrix=Matrix.Translation((0, 0, t / 2 + 0.045)))
        for f in set(bm.faces) - before:
            f.material_index = 1
    obj = mesh_object(name, bm)
    bevel(obj, m * 0.12)
    obj["spin_axis"] = "z"
    if p.get("jewel"):
        obj["extra_material"] = "ruby"
    return obj


def build_rotor(name, p):
    n = int(p.get("blades", 18))
    r_in, r_out = float(p.get("r_in", 0.4)), float(p.get("r_out", 1.2))
    chord, th = float(p.get("chord", 0.3)), float(p.get("thickness", 0.03))
    pitch, twist = math.radians(float(p.get("pitch", 35))), math.radians(float(p.get("twist", 20)))
    hub_len = float(p.get("hub_length", chord * 1.2))
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=48, radius1=r_in * 1.04, radius2=r_in * 1.04, depth=hub_len)
    if p.get("nose"):
        bmesh.ops.create_cone(bm, cap_ends=True, segments=48, radius1=r_in * 1.04, radius2=0.02,
                              depth=r_in * 1.6, matrix=Matrix.Translation((0, 0, hub_len / 2 + r_in * 0.8)))
    for k in range(n):
        th_k = 2 * math.pi * k / n
        u = Vector((math.cos(th_k), math.sin(th_k), 0))
        v = Vector((-math.sin(th_k), math.cos(th_k), 0))
        w = Vector((0, 0, 1))
        corners = []
        for r, beta in ((r_in * 0.98, pitch + twist), (r_out, pitch - twist)):
            d = v * math.cos(beta) + w * math.sin(beta)
            nrm = -v * math.sin(beta) + w * math.cos(beta)
            c = u * r
            corners += [c + d * (sx * chord / 2) + nrm * (sy * th / 2) for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
        vs = [bm.verts.new(c) for c in corners]
        for f in ((0, 1, 2, 3), (7, 6, 5, 4), (0, 4, 5, 1), (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0)):
            bm.faces.new([vs[i] for i in f])
    axis = p.get("axis", "z")
    to_axis(bm, axis)
    obj = mesh_object(name, bm)
    bevel(obj, th * 0.3, 1)
    obj["spin_axis"] = axis
    return obj


def build_lathe(name, p):
    prof = [(float(r), float(a)) for r, a in p["profile"]]
    sweep = float(p.get("sweep", 360))
    start = math.radians(float(p.get("start_angle", 0)))
    full = sweep >= 359.9
    seg = max(6, int(int(p.get("segments", 64)) * sweep / 360))
    rings = seg if full else seg + 1
    bm = bmesh.new()
    grid = []
    for i in range(rings):
        a = start + math.radians(sweep) * i / seg
        grid.append([bm.verts.new((r * math.cos(a), r * math.sin(a), z)) for r, z in prof])
    for i in range(seg):
        j = (i + 1) % rings
        for k in range(len(prof) - 1):
            bm.faces.new((grid[i][k], grid[j][k], grid[j][k + 1], grid[i][k + 1]))
    axis = p.get("axis", "z")
    to_axis(bm, axis)
    obj = mesh_object(name, bm, smooth=True)
    sol = obj.modifiers.new("Shell", "SOLIDIFY")
    sol.thickness, sol.offset, sol.use_rim = float(p.get("thickness", 0.04)), 0, True
    sol.material_offset_rim = 1
    obj["extra_material"] = p.get("cut_material", "accent")
    obj["spin_axis"] = axis
    return obj


def curve_object(name, pts, radius, poly=False, closed=False):
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth, cu.bevel_resolution, cu.use_fill_caps = radius, 6, True
    if poly:
        sp = cu.splines.new("POLY")
        sp.points.add(len(pts) - 1)
        for i, q in enumerate(pts):
            sp.points[i].co = (*q, 1)
    else:
        sp = cu.splines.new("BEZIER")
        sp.bezier_points.add(len(pts) - 1)
        for i, q in enumerate(pts):
            bp = sp.bezier_points[i]
            bp.co = q
            bp.handle_left_type = bp.handle_right_type = "AUTO"
    sp.use_cyclic_u = closed
    return bpy.data.objects.new(name, cu)


def build_spring(name, p):
    coils, r, wire = float(p.get("coils", 6)), float(p.get("radius", 0.5)), float(p.get("wire", 0.04))
    steps = int(coils * 32)
    if p.get("flat"):
        r0 = float(p.get("inner_radius", r * 0.2))
        pts = [((r0 + (r - r0) * i / steps) * math.cos(2 * math.pi * coils * i / steps),
                (r0 + (r - r0) * i / steps) * math.sin(2 * math.pi * coils * i / steps), 0) for i in range(steps + 1)]
    else:
        h = float(p.get("height", 1.5))
        pts = [(r * math.cos(2 * math.pi * coils * i / steps), r * math.sin(2 * math.pi * coils * i / steps),
                h * (i / steps - 0.5)) for i in range(steps + 1)]
    obj = curve_object(name, pts, wire, poly=True)
    obj["spin_axis"] = "z"
    return obj


def build_box(name, p):
    sx, sy, sz = p.get("size", (1, 1, 1)) if isinstance(p.get("size", 1), (list, tuple)) else (p.get("size", 1),) * 3
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=(sx, sy, sz), verts=bm.verts)
    if p.get("pivot"):
        bmesh.ops.translate(bm, vec=-Vector(p["pivot"]), verts=bm.verts)
    obj = mesh_object(name, bm)
    if p.get("bevel", 0.02):
        bevel(obj, min(float(p.get("bevel", 0.02)), min(sx, sy, sz) * 0.3), 3)
    return obj


def build_cylinder(name, p):
    r, d = float(p.get("radius", 0.5)), float(p.get("depth", 1.0))
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=int(p.get("segments", 48)), radius1=r, radius2=r, depth=d)
    if p.get("pivot"):
        bmesh.ops.translate(bm, vec=-Vector(p["pivot"]), verts=bm.verts)
    axis = p.get("axis", "z")
    to_axis(bm, axis)
    obj = mesh_object(name, bm)
    bevel(obj, float(p.get("bevel", min(r, d) * 0.08)), 2)
    obj["spin_axis"] = axis
    return obj


def build_sphere(name, p):
    bm = bmesh.new()
    s = int(p.get("segments", 48))
    bmesh.ops.create_uvsphere(bm, u_segments=s, v_segments=s // 2, radius=float(p.get("radius", 0.5)))
    return mesh_object(name, bm, smooth=True)


def build_torus(name, p):
    R, r, n, m = float(p.get("major", 1)), float(p.get("minor", 0.1)), 64, 16
    bm = bmesh.new()
    grid = [[bm.verts.new(((R + r * math.cos(b)) * math.cos(a), (R + r * math.cos(b)) * math.sin(a), r * math.sin(b)))
             for b in (2 * math.pi * j / m for j in range(m))] for a in (2 * math.pi * i / n for i in range(n))]
    for i in range(n):
        for j in range(m):
            bm.faces.new((grid[i][j], grid[(i + 1) % n][j], grid[(i + 1) % n][(j + 1) % m], grid[i][(j + 1) % m]))
    axis = p.get("axis", "z")
    to_axis(bm, axis)
    obj = mesh_object(name, bm, smooth=True)
    obj["spin_axis"] = axis
    return obj


def build_blob(name, p):
    """Organic shape from merged metaball elements: [[x, y, z, radius], ...]."""
    mb = bpy.data.metaballs.new(name)
    mb.resolution = mb.render_resolution = float(p.get("resolution", 0.06))
    for x, y, z, r in p["elements"]:
        e = mb.elements.new()
        e.co, e.radius = (x, y, z), r
    return bpy.data.objects.new(name, mb)


def build_stage(name, p):
    nx, ny = int(p.get("nx", 8)), int(p.get("ny", 8))
    tile, gap, h = float(p.get("tile", 0.5)), float(p.get("gap", 0.04)), float(p.get("height", 0.25))
    bm = bmesh.new()
    step = tile + gap
    for i in range(nx):
        for j in range(ny):
            m = Matrix.Translation(((i - (nx - 1) / 2) * step, (j - (ny - 1) / 2) * step, -h / 2)) @ Matrix.Diagonal((tile, tile, h, 1))
            bmesh.ops.create_cube(bm, size=1.0, matrix=m)
    obj = mesh_object(name, bm)
    bevel(obj, tile * 0.08, 3)
    return obj


def build_arrow(name, p, start):
    d = Vector(p["to"]) - Vector(start)
    length, r = d.length, float(p.get("radius", 0.05))
    head = min(length * 0.35, r * 5)
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=24, radius1=r, radius2=r, depth=length - head,
                          matrix=Matrix.Translation((0, 0, (length - head) / 2)))
    bmesh.ops.create_cone(bm, cap_ends=True, segments=24, radius1=r * 2.6, radius2=0.0, depth=head,
                          matrix=Matrix.Translation((0, 0, length - head / 2)))
    obj = mesh_object(name, bm, smooth=True)
    obj.rotation_mode = "QUATERNION"
    obj.rotation_quaternion = d.to_track_quat("Z", "Y")
    return obj


def build_label(name, p, font, link):
    size = float(p.get("size", 0.22))
    cu = bpy.data.curves.new(name + "_text", "FONT")
    cu.body = str(p["text"])
    cu.size, cu.align_x, cu.align_y = size, "CENTER", "CENTER"
    if font:
        cu.font = font
    txt = bpy.data.objects.new(name + "_text", cu)
    link(txt)
    bpy.context.view_layer.update()
    w, h = txt.dimensions.x + size * 0.9, size * 1.5
    plate = build_box(name, {"size": (w, h, size * 0.25), "bevel": size * 0.08})
    txt.parent = plate
    txt.location = (0, 0, size * 0.13 + 0.002)
    return plate, txt


def build_flow(name, p, fps, link, mat):
    """Particles riding a path forever; offset animated with a Cycles modifier."""
    base = [Vector(q) for q in p["points"]]
    count, rad, speed = int(p.get("count", 16)), float(p.get("radius", 0.05)), float(p.get("speed", 1.0))
    copies, axis = int(p.get("radial_copies", 1)), p.get("axis", "x")
    holder = bpy.data.objects.new(name, None)
    members = []
    sm = bmesh.new()
    bmesh.ops.create_uvsphere(sm, u_segments=12, v_segments=8, radius=rad)
    sphere = bpy.data.meshes.new(name + "_dot")
    sm.to_mesh(sphere)
    sm.free()
    for poly in sphere.polygons:
        poly.use_smooth = True
    sphere.materials.append(mat)
    length = sum((b - a).length for a, b in zip(base, base[1:]))
    period = max(2.0, length / max(speed, 1e-3) * fps)
    for c in range(copies):
        rot = Matrix.Rotation(2 * math.pi * c / copies, 3, axis.upper())
        path = curve_object(f"{name}_path{c}", [tuple(rot @ q) for q in base], 0.0)
        path.data.use_path = True
        path.parent = holder
        link(path)
        for i in range(count):
            dot = bpy.data.objects.new(f"{name}_{c}_{i}", sphere)
            con = dot.constraints.new("FOLLOW_PATH")
            con.target, con.use_fixed_location = path, True
            phase = -((i + c / copies) / count) * period
            key(con, "offset_factor", phase, 0.0, ease="linear")
            fc = key(con, "offset_factor", phase + period, 1.0, ease="linear")
            fc.modifiers.new("CYCLES")
            link(dot)
            members.append(dot)
    return holder, members


# ── Scene build ──────────────────────────────────────────────────────────

class Build:
    def __init__(self, plan, args):
        self.plan, self.args, self.fps = plan, args, plan["fps"]
        self.n = plan["frames"]
        self.objs, self.members, self.mats, self.warnings, self.cutters = {}, {}, {}, [], {}
        self.col = bpy.context.scene.collection

    def link(self, o):
        self.col.objects.link(o)

    def build_objects(self):
        font = None
        if self.args.font and Path(self.args.font).exists():
            font = bpy.data.fonts.load(self.args.font)
        for o in self.plan["objects"]:
            oid, kind, p = o["id"], o["kind"], o["params"]
            mat = make_material(f"{oid}_mat", o["material"])
            members = []
            if kind == "gear":
                obj = build_gear(oid, p)
            elif kind == "rotor":
                obj = build_rotor(oid, p)
            elif kind == "lathe":
                obj = build_lathe(oid, p)
            elif kind == "spring":
                obj = build_spring(oid, p)
            elif kind == "tube":
                obj = curve_object(oid, [tuple(q) for q in p["points"]], float(p.get("radius", 0.08)))
            elif kind == "box":
                obj = build_box(oid, p)
            elif kind == "sphere":
                obj = build_sphere(oid, p)
            elif kind == "cylinder":
                obj = build_cylinder(oid, p)
            elif kind == "torus":
                obj = build_torus(oid, p)
            elif kind == "stage":
                obj = build_stage(oid, p)
            elif kind == "blob":
                obj = build_blob(oid, p)
            elif kind == "arrow":
                obj = build_arrow(oid, p, o["position"])
            elif kind == "label":
                obj, txt = build_label(oid, p, font, self.link)
                txt.data.materials.append(make_material(f"{oid}_txt", "white"))
                members = [txt]
            elif kind == "flow":
                obj, members = build_flow(oid, p, self.fps, self.link, mat)
            elif kind == "asset":
                obj = self.import_asset(oid, p)
            elif kind == "empty":
                obj = bpy.data.objects.new(oid, None)
            else:  # unreachable: schema rejects unknown kinds
                raise ValueError(kind)
            if obj.type in ("MESH", "CURVE", "FONT", "META") and kind != "flow":
                obj.data.materials.append(mat)
                if "extra_material" in obj:
                    obj.data.materials.append(make_material(f"{oid}_cut", obj["extra_material"]))
            obj.location = o["position"]
            if obj.rotation_mode != "QUATERNION":
                obj.rotation_euler = [math.radians(a) for a in o["rotation"]]
            s = o["scale"]
            obj.scale = (s, s, s) if isinstance(s, (int, float)) else s
            obj["base_scale"] = list(obj.scale)
            if kind == "label":
                obj.constraints.new("TRACK_TO").track_axis = "TRACK_Z"
            self.link(obj)
            if o.get("cut") and obj.type == "MESH":
                self.section(obj, o)
            self.objs[oid], self.members[oid], self.mats[oid] = obj, members, mat
        for o in self.plan["objects"]:
            if o["parent"]:
                self.objs[o["id"]].parent = self.objs[o["parent"]]
                if o["id"] in self.cutters:
                    self.cutters[o["id"]].parent = self.objs[o["parent"]]
            if o.get("driver"):
                self.add_gear_driver(self.objs[o["id"]], o["driver"])

    def section(self, obj, o):
        """Dissect: remove the half-space on the `cut` normal's side, cap with accent colour."""
        n = Vector(o["cut"]).normalized()
        size = 60.0
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=size)
        cutter = mesh_object(obj.name + "_cutter", bm)
        cutter.data.materials.append(make_material(obj.name + "_cap", o.get("cut_material") or "accent"))
        cutter.location = Vector(o["position"]) + n * (size / 2 + float(o.get("cut_offset", 0.0)))
        cutter.rotation_mode = "QUATERNION"
        cutter.rotation_quaternion = n.to_track_quat("Z", "Y")
        cutter.hide_render = True
        cutter.display_type = "WIRE"
        self.link(cutter)
        self.cutters[o["id"]] = cutter  # parented with obj's parent: the plane is in the same local frame
        mod = obj.modifiers.new("Section", "BOOLEAN")
        mod.operation, mod.object, mod.solver = "DIFFERENCE", cutter, "EXACT"
        mod.material_mode = "TRANSFER"

    def import_asset(self, oid, p):
        before = set(bpy.data.objects)
        bpy.ops.import_scene.gltf(filepath=p["_path"])
        new = [o for o in bpy.data.objects if o not in before]
        root = bpy.data.objects.new(oid, None)
        bpy.context.view_layer.update()
        pts = [o.matrix_world @ Vector(c) for o in new if o.type == "MESH" for c in o.bound_box]
        lo = Vector([min(q[i] for q in pts) for i in range(3)])
        hi = Vector([max(q[i] for q in pts) for i in range(3)])
        k = float(p.get("size", 1.0)) / max(hi - lo)
        for o in new:
            if o.parent is None:
                o.parent = root
                o.matrix_parent_inverse = Matrix.Diagonal((k, k, k, 1)) @ Matrix.Translation(-(lo + hi) / 2)
        return root

    def add_gear_driver(self, obj, d):
        fc = obj.driver_add("rotation_euler", 2)
        drv = fc.driver
        drv.type = "SCRIPTED"
        v = drv.variables.new()
        v.name, v.type = "r", "SINGLE_PROP"
        v.targets[0].id_type, v.targets[0].id = "OBJECT", self.objs[d["root"]]
        v.targets[0].data_path = "rotation_euler[2]"
        drv.expression = f"{d['phase0']:.6f} + ({d['ratio']:.6f})*(r - ({d['root0']:.6f}))"

    # Every object (and its descendants/members) whose materials an action should touch.
    def materials(self, oid, first_only=False):
        root = self.objs[oid]
        out = {}
        for o in [root] + list(root.children_recursive) + self.members[oid]:
            if o.type in ("MESH", "CURVE", "FONT", "META"):
                for m in (o.data.materials[:1] if first_only else o.data.materials):
                    out[m.name] = m
        return list(out.values())

    def apply_actions(self):
        for a in self.plan["actions"]:
            obj = self.objs[a["target"]]
            f0, p, ease = a["f0"], a["params"], a["ease"]
            if a["f1"] is None:
                f1 = self.n - 1 if a["do"] in CONTINUOUS else min(self.n - 1, f0 + round(DEFAULT_DUR.get(a["do"], 0.6) * self.fps))
            else:
                f1 = a["f1"]
            f1 = max(f1, f0 + 1)
            getattr(self, "do_" + a["do"])(obj, a, f0, f1, p, ease)

    def channel(self, obj, p, default="rotation"):
        prop = {"rotation": "rotation_euler", "location": "location", "scale": "scale"}[p.get("prop", default)]
        return prop, AXIS.get(p.get("axis", obj.get("spin_axis", "z")), 0)

    def do_spin(self, obj, a, f0, f1, p, ease):
        prop, i = self.channel(obj, p)
        rate = math.radians(float(p.get("rate", 90))) / self.fps
        ramp = min(round(float(p.get("ramp", 0.5)) * self.fps), (f1 - f0) // 2)
        v0 = value_at(obj, prop, i, f0)
        if ramp:
            key(obj, prop, f0, v0, i, ease="QUAD")
            for kp in fcurve(obj, prop, i).keyframe_points:
                if abs(kp.co.x - f0) < 0.5:
                    kp.easing = "EASE_IN"
        v_r = v0 + rate * ramp / 2
        key(obj, prop, f0 + ramp, v_r, i, ease="linear")
        key(obj, prop, f1, v_r + rate * (f1 - f0 - ramp), i, ease="linear")

    def do_tick(self, obj, a, f0, f1, p, ease):
        prop, i = self.channel(obj, p)
        step = math.radians(float(p.get("step", 12)))
        per = self.fps / float(p.get("rate", 2))
        snap = max(1, int(p.get("snap_frames", 3)))
        v = value_at(obj, prop, i, f0)
        k = 0
        while f0 + k * per + snap <= f1:
            t = f0 + k * per
            key(obj, prop, t, v, i, ease="QUART")
            v += step
            key(obj, prop, t + snap, v, i, ease="CONSTANT")
            k += 1

    def do_cycle(self, obj, a, f0, f1, p, ease):
        prop, i = self.channel(obj, p, p.get("prop", "rotation"))
        keys = [(float(u), float(val)) for u, val in p["keys"]]
        per = self.fps / float(p.get("hz", 1.0))
        shift = float(p.get("phase", 0.0)) * per
        idxs = [0, 1, 2] if p.get("axis") == "all" else [i]
        for j in idxs:
            base = value_at(obj, prop, j, f0)
            conv = (lambda x: base * x) if prop == "scale" else ((lambda x: base + math.radians(x)) if prop == "rotation_euler" else (lambda x: base + x))

            def at(frame):
                u = ((frame - f0 + shift) / per) % 1.0
                for (ua, va), (ub, vb) in zip(keys, keys[1:]):
                    if ua <= u <= ub:
                        return va + (vb - va) * ((u - ua) / (ub - ua) if ub > ua else 0)
                return keys[-1][1]
            key(obj, prop, f0, conv(at(f0)), j)
            c = -1
            while True:
                start = f0 - shift + c * per
                if start > f1:
                    break
                for u, val in keys:
                    t = start + u * per
                    if f0 < t < f1:
                        key(obj, prop, round(t), conv(val), j)
                c += 1
            key(obj, prop, f1, conv(at(f1)), j)

    def do_oscillate(self, obj, a, f0, f1, p, ease):
        amp = float(p.get("amplitude", 15))
        self.do_cycle(obj, a, f0, f1, {**p, "keys": [[0, 0], [0.25, amp], [0.75, -amp], [1, 0]]}, ease)

    def do_pulse(self, obj, a, f0, f1, p, ease):
        amt, duty = float(p.get("amount", 0.12)), float(p.get("duty", 0.5))
        keys = [[0, 1], [duty * 0.45, 1 + amt], [duty, 1], [1, 1]]
        self.do_cycle(obj, a, f0, f1, {"prop": "scale", "axis": p.get("axis", "all"), "hz": p.get("hz", 1),
                                       "phase": p.get("phase", 0), "keys": keys}, ease)

    def vec_action(self, obj, prop, f0, f1, target, ease):
        for i in range(3):
            key(obj, prop, f0, value_at(obj, prop, i, f0), i, ease=ease)
            key(obj, prop, f1, target[i], i)

    def do_move(self, obj, a, f0, f1, p, ease):
        cur = Vector([value_at(obj, "location", i, f0) for i in range(3)])
        tgt = Vector(p["to"]) if "to" in p else cur + Vector(p["by"])
        self.vec_action(obj, "location", f0, f1, tgt, ease)

    def do_explode(self, obj, a, f0, f1, p, ease):
        by = Vector(p.get("by", (0, 0, 0.6))) * ((a["index"] + 1) if p.get("progressive", True) else 1)
        self.do_move(obj, a, f0, f1, {"by": by}, ease)

    def do_rotate(self, obj, a, f0, f1, p, ease):
        cur = [value_at(obj, "rotation_euler", i, f0) for i in range(3)]
        tgt = [math.radians(x) for x in p["to"]] if "to" in p else [c + math.radians(d) for c, d in zip(cur, p["by"])]
        self.vec_action(obj, "rotation_euler", f0, f1, tgt, ease)

    def do_scale(self, obj, a, f0, f1, p, ease):
        s = p["to"]
        self.vec_action(obj, "scale", f0, f1, s if isinstance(s, (list, tuple)) else (s, s, s), ease)

    def do_pop_in(self, obj, a, f0, f1, p, ease):
        base = obj["base_scale"]
        for i in range(3):
            key(obj, "scale", 0, 0.0, i, ease="CONSTANT")
            key(obj, "scale", f0, 0.0, i, ease="back")
            key(obj, "scale", f1, base[i], i)
        self.do_show(obj, a, f0, f1, p, ease, only_members=True)

    def do_pop_out(self, obj, a, f0, f1, p, ease):
        for i in range(3):
            key(obj, "scale", f0, value_at(obj, "scale", i, f0), i, ease="BACK")
            for kp in fcurve(obj, "scale", i).keyframe_points:
                if abs(kp.co.x - f0) < 0.5:
                    kp.easing = "EASE_IN"
            key(obj, "scale", f1, 0.0, i)
        self.do_hide(obj, a, f1, f1 + 1, p, ease, only_members=True)

    def do_show(self, obj, a, f0, f1, p, ease, only_members=False, hidden=(True, False)):
        targets = self.members[a["target"]] if only_members else [obj] + self.members[a["target"]]
        for o in targets:
            for prop in ("hide_render", "hide_viewport"):
                key(o, prop, 0, hidden[0], ease="CONSTANT")
                key(o, prop, f0, hidden[1], ease="CONSTANT")

    def do_hide(self, obj, a, f0, f1, p, ease, only_members=False):
        self.do_show(obj, a, f0, f1, p, ease, only_members, hidden=(False, True))

    def do_fade(self, obj, a, f0, f1, p, ease):
        for m in self.materials(a["target"]):
            m.surface_render_method = "BLENDED"
            sock = bsdf(m).inputs["Alpha"]
            key(sock, "default_value", f0, value_at(sock, "default_value", -1, f0), ease=ease)
            key(sock, "default_value", f1, float(p.get("to", 0.25)))

    def do_highlight(self, obj, a, f0, f1, p, ease):
        col = lin(p.get("color", PALETTE["accent"][0]))
        strength = float(p.get("strength", 1.4))
        if bpy.context.scene.render.engine == "CYCLES":  # path-traced emission reads much stronger
            strength *= 0.4
        rise = max(1, round(0.25 * self.fps))
        for m in self.materials(a["target"], first_only=True):
            b = bsdf(m)
            b.inputs["Emission Color"].default_value = col
            sock = b.inputs["Emission Strength"]
            base = value_at(sock, "default_value", -1, f0)
            key(sock, "default_value", f0, base)
            key(sock, "default_value", f0 + rise, strength)
            if a["f1"] is not None or not p.get("hold"):
                key(sock, "default_value", max(f0 + rise + 1, f1 - rise), strength)
                key(sock, "default_value", f1, base)

    # ── Camera ──
    def subject_points(self, ids, frames):
        pts = []
        sc = bpy.context.scene
        for f in frames:
            sc.frame_set(f)
            for oid in ids:
                root = self.objs[oid]
                for o in [root] + list(root.children_recursive):
                    if o.type in ("MESH", "CURVE", "FONT", "META") and not o.hide_render:
                        pts += [o.matrix_world @ Vector(c) for c in o.bound_box]
                if not pts:
                    pts.append(root.matrix_world.translation.copy())
        return pts

    def camera_setup(self):
        cd = bpy.data.cameras.new("Camera")
        self.cam = bpy.data.objects.new("Camera", cd)
        self.tgt = bpy.data.objects.new("CamTarget", None)
        self.link(self.cam)
        self.link(self.tgt)
        bpy.context.scene.camera = self.cam
        tr = self.cam.constraints.new("TRACK_TO")
        tr.target, tr.track_axis, tr.up_axis = self.tgt, "TRACK_NEGATIVE_Z", "UP_Y"
        cd.clip_start, cd.clip_end, cd.shift_y = 0.05, 500, 0.05
        if self.args.quality in ("cycles", "realistic", "production"):
            cd.dof.use_dof, cd.dof.focus_object, cd.dof.aperture_fstop = True, self.tgt, 7.0
        for o in self.objs.values():
            for c in o.constraints:
                if c.type == "TRACK_TO" and c.target is None:
                    c.target, c.up_axis = self.cam, "UP_Y"
        sc = bpy.context.scene
        self.aspect = sc.render.resolution_x / sc.render.resolution_y
        self.shots = []
        for s in self.plan["shots"]:
            solid = [o["id"] for o in self.plan["objects"] if o["kind"] not in ("flow", "label", "empty", "stage")
                     and not o["parent"]]
            ids = s["frame"] or ([s["target"]] if isinstance(s["target"], str) else solid)
            frames = sorted({s["f0"], (s["f0"] + s["f1"]) // 2, max(s["f0"], s["f1"] - 1)})
            pts = self.subject_points(ids, frames) if ids else [Vector(s["target"])]
            if isinstance(s["target"], str):
                tp = self.subject_points([s["target"]], frames)
                lo = Vector([min(q[i] for q in tp) for i in range(3)])
                hi = Vector([max(q[i] for q in tp) for i in range(3)])
                center = (lo + hi) / 2
            else:
                center = Vector(s["target"])
            radius = max([(q - center).length for q in pts] + [0.3])
            self.shots.append({**s, "center": center, "radius": radius, "margin": 1.0, "ids": ids})

    def pose(self, s, u):
        kind, lens = s["type"], max(s["lens"], 85) if s["type"] == "macro" else s["lens"]
        orbit = s["orbit"] if s["orbit"] is not None else {"orbit": 40, "top_down": 25, "static": 5}.get(kind, 12)
        el = 78.0 if kind == "top_down" else s["elevation"]
        d_scale = {"push_in": (1.15, 0.88), "pull_out": (0.88, 1.2), "macro": (1.1, 0.92)}.get(kind, (1.0, 1.0))
        half_v = math.atan(18 / lens)
        half_h = math.atan(18 * self.aspect / lens)
        use = min(math.atan(math.tan(half_h) * (SAFE[1] - SAFE[0])), math.atan(math.tan(half_v) * (SAFE[3] - SAFE[2])))
        d = s["distance"] or s["radius"] / math.sin(use)
        e = 0.5 - 0.5 * math.cos(math.pi * u)
        dist = d * s["margin"] * (d_scale[0] + (d_scale[1] - d_scale[0]) * e)
        az, elr = math.radians(s["azimuth"] + orbit * (e - 0.5)), math.radians(el)
        off = Vector((math.sin(az) * math.cos(elr), -math.cos(az) * math.cos(elr), math.sin(elr)))
        return s["center"] + off * dist, lens

    def key_camera(self):
        for o in (self.cam, self.tgt, self.cam.data):
            o.animation_data_clear()
        for k, s in enumerate(self.shots):
            b = 0 if k == 0 else min(round(s["blend"] * self.fps), (s["f1"] - s["f0"]) // 2)
            a0, a1 = s["f0"] + b, max(s["f0"] + b + 1, s["f1"])
            frames = list(range(a0, a1, 4)) + [a1]
            for f in frames:
                u = (f - a0) / max(1, a1 - a0)
                loc, lens = self.pose(s, u)
                ease = "linear" if f != frames[-1] else "smooth"
                for i in range(3):
                    key(self.cam, "location", f, loc[i], i, ease=ease)
                    key(self.tgt, "location", f, s["center"][i], i, ease=ease)
                key(self.cam.data, "lens", f, lens, ease=ease)

    def framing_overflow(self, s):
        sc = bpy.context.scene
        a0 = s["f0"] + (0 if s is self.shots[0] else round(s["blend"] * self.fps))
        worst = 0.0
        for f in range(a0, max(a0 + 1, s["f1"]), 5):
            for q in self.subject_points(s["ids"], [f]):
                x, y, z = world_to_camera_view(sc, self.cam, q)
                over = max(SAFE[0] - x, x - SAFE[1], SAFE[2] - y, y - SAFE[3], 0.0 if z > 0 else 1.0)
                worst = max(worst, over)
        return worst

    def screen_bounds(self, s):
        """Union of the subject's projected bounds over the shot (camera-view units)."""
        sc = bpy.context.scene
        a0 = s["f0"] + (0 if s is self.shots[0] else round(s["blend"] * self.fps))
        xs, ys = [], []
        for f in range(a0, max(a0 + 1, s["f1"]), 6):
            sc.frame_set(f)
            for q in self.subject_points(s["ids"], [f]):
                x, y, z = world_to_camera_view(sc, self.cam, q)
                if z <= 0:
                    return None
                xs.append(x)
                ys.append(y)
        return min(xs), max(xs), min(ys), max(ys)

    def frame_camera(self, fill=0.9):
        """Centre each shot's subject in the 9:16 safe area and scale it to `fill`,
        then repair any remaining overflow by widening the shot."""
        sc = bpy.context.scene
        report = []
        for _ in range(4):
            self.key_camera()
            for s in self.shots:
                if not s["ids"]:
                    continue
                bnd = self.screen_bounds(s)
                if bnd is None:
                    s["margin"] *= 1.5
                    continue
                x0, x1, y0, y1 = bnd
                sc.frame_set((s["f0"] + s["f1"]) // 2)
                mw = self.cam.matrix_world
                dist = (mw.translation - s["center"]).length
                half_v = math.atan(18 / self.cam.data.lens)
                half_h = math.atan(18 * self.aspect / self.cam.data.lens)
                dx = (x0 + x1) / 2 - (SAFE[0] + SAFE[1]) / 2
                dy = (y0 + y1) / 2 - (SAFE[2] + SAFE[3]) / 2
                s["center"] = s["center"] + mw.col[0].xyz.normalized() * dx * 2 * dist * math.tan(half_h) \
                    + mw.col[1].xyz.normalized() * dy * 2 * dist * math.tan(half_v)
                if not s["distance"]:
                    util = max((x1 - x0) / (SAFE[1] - SAFE[0]), (y1 - y0) / (SAFE[3] - SAFE[2]))
                    s["margin"] *= max(0.3, min(3.0, util / fill))
        for _ in range(6):
            self.key_camera()
            bad = [(s, self.framing_overflow(s)) for s in self.shots if s["ids"]]
            bad = [(s, o) for s, o in bad if o > 0.01]
            if not bad:
                break
            for s, o in bad:
                s["margin"] *= 1.0 + max(0.08, min(o * 2.5, 0.5))
        else:
            self.key_camera()
        for s in self.shots:
            o = self.framing_overflow(s) if s["ids"] else 0.0
            report.append({"f0": s["f0"], "type": s["type"], "subjects": s["ids"], "margin": round(s["margin"], 3),
                           "overflow": round(o, 4), "ok": o <= 0.01})
        return report

    # ── World & lights ──
    def world_and_lights(self):
        sc = bpy.context.scene
        bg = lin(BACKGROUNDS[self.plan["background"]])
        sc.world = bpy.data.worlds.new("World")
        nt = sc.world.node_tree
        nodes, links = nt.nodes, nt.links
        cam_bg = nodes["Background"]
        cam_bg.inputs["Color"].default_value = bg
        env = nodes.new("ShaderNodeBackground")
        coord, sep = nodes.new("ShaderNodeTexCoord"), nodes.new("ShaderNodeSeparateXYZ")
        ramp = nodes.new("ShaderNodeValToRGB")
        ramp.color_ramp.elements[0].position, ramp.color_ramp.elements[0].color = 0.42, lin("#3A3D44")
        ramp.color_ramp.elements[1].position, ramp.color_ramp.elements[1].color = 0.62, lin("#FFFFFF")
        links.new(coord.outputs["Generated"], sep.inputs[0])
        mr = nodes.new("ShaderNodeMapRange")
        mr.inputs["From Min"].default_value, mr.inputs["From Max"].default_value = -1.0, 1.0
        links.new(sep.outputs["Z"], mr.inputs["Value"])
        links.new(mr.outputs["Result"], ramp.inputs["Fac"])
        links.new(ramp.outputs["Color"], env.inputs["Color"])
        env.inputs["Strength"].default_value = 0.55 if self.plan["background"] == "light" else 0.4
        if self.args.hdri and Path(self.args.hdri).exists():  # real studio reflections (CC0)
            tex = nodes.new("ShaderNodeTexEnvironment")
            tex.image = bpy.data.images.load(self.args.hdri)
            links.new(tex.outputs["Color"], env.inputs["Color"])
            env.inputs["Strength"].default_value = 0.7
        lp, mix = nodes.new("ShaderNodeLightPath"), nodes.new("ShaderNodeMixShader")
        links.new(lp.outputs["Is Camera Ray"], mix.inputs[0])
        links.new(env.outputs[0], mix.inputs[1])
        links.new(cam_bg.outputs[0], mix.inputs[2])
        links.new(mix.outputs[0], nodes["World Output"].inputs["Surface"])
        pts = self.subject_points([o["id"] for o in self.plan["objects"] if o["kind"] not in ("flow", "label")], [0])
        lo = Vector([min(q[i] for q in pts) for i in range(3)])
        hi = Vector([max(q[i] for q in pts) for i in range(3)])
        c, R = (lo + hi) / 2, max((hi - lo).length / 2, 1.0)
        dark = self.plan["background"] != "light"
        rig = [("Key", (-0.6, -0.9, 1.1), 1.0, 1.8, "#FFF4E8"),
               ("Fill", (1.0, -0.6, 0.35), 0.35, 2.5, "#E8F0FF"),
               ("Rim", (0.3, 1.0, 0.8), 0.9 if dark else 0.5, 1.2, "#FFFFFF")]
        for name, dirv, power, size, col in rig:
            ld = bpy.data.lights.new(name, "AREA")
            ld.size, ld.color = size * R, lin(col)[:3]
            dist = 3.2 * R
            ld.energy = power * 8 * dist * dist
            lo_ = bpy.data.objects.new(name, ld)
            lo_.location = c + Vector(dirv).normalized() * dist
            lo_.rotation_euler = (c - lo_.location).to_track_quat("-Z", "Y").to_euler()
            self.link(lo_)
        self.floor(bg, c, R, lo.z)

    def floor(self, bg, c, R, z):
        """Ground plane that fades to the background colour: contact shadows, no horizon line."""
        bm = bmesh.new()
        bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=R * 12)
        fl = mesh_object("Floor", bm)
        fl.location = (c.x, c.y, z - 0.05 * R)
        m = bpy.data.materials.new("FloorMat")
        nt = m.node_tree
        b = nt.nodes["Principled BSDF"]
        b.inputs["Base Color"].default_value = bg
        b.inputs["Roughness"].default_value = 0.95
        tc, mp, gr = nt.nodes.new("ShaderNodeTexCoord"), nt.nodes.new("ShaderNodeMapping"), nt.nodes.new("ShaderNodeTexGradient")
        gr.gradient_type = "SPHERICAL"
        mp.inputs["Scale"].default_value = (1 / (3.5 * R),) * 3
        nt.links.new(tc.outputs["Object"], mp.inputs["Vector"])
        nt.links.new(mp.outputs["Vector"], gr.inputs["Vector"])
        pw = nt.nodes.new("ShaderNodeMath")
        pw.operation, pw.inputs[1].default_value = "POWER", 1.6
        nt.links.new(gr.outputs["Fac"], pw.inputs[0])
        nt.links.new(pw.outputs[0], b.inputs["Alpha"])
        m.surface_render_method = "BLENDED"
        fl.data.materials.append(m)
        self.link(fl)

    def configure_render(self):
        sc, a = bpy.context.scene, self.args
        r = sc.render
        r.resolution_x, r.resolution_y, r.resolution_percentage = a.width, a.height, 100
        r.fps, r.film_transparent = self.fps, False
        sc.view_settings.view_transform = "Standard"
        sc.frame_start, sc.frame_end = 0, self.n - 1
        if a.quality in ("cycles", "realistic"):
            r.engine = "CYCLES"
            cy = sc.cycles
            cy.samples, cy.adaptive_threshold, cy.use_denoising = a.samples, 0.03, True
            cy.denoiser = "OPENIMAGEDENOISE"
            cy.max_bounces, cy.transparent_max_bounces = 6, 8
            r.use_persistent_data = True
            cy.device = "CPU"
            prefs = bpy.context.preferences.addons["cycles"].preferences
            for backend in () if a.cpu else ("METAL", "OPTIX", "CUDA", "HIP", "ONEAPI"):
                try:
                    prefs.compute_device_type = backend
                    prefs.refresh_devices()
                    gpus = [d for d in prefs.devices if d.type != "CPU"]
                except Exception:
                    continue
                if gpus:
                    for d in prefs.devices:
                        d.use = d.type != "CPU"
                    cy.device = "GPU"
                    break
            print("STUDIO_CYCLES_DEVICE", cy.device)
        else:
            r.engine = "BLENDER_EEVEE"
            sc.eevee.taa_render_samples = 8 if a.quality == "preview" else 32
        r.use_motion_blur = a.quality != "preview"
        if a.frame_end >= 0:  # render a shard of the scene (CI fan-out)
            sc.frame_start, sc.frame_end = a.frame_start, min(a.frame_end, self.n - 1)
        r.image_settings.file_format, r.image_settings.color_mode = "PNG", "RGB"
        r.use_overwrite, r.use_placeholder = False, True  # resume interrupted renders
        r.filepath = str(Path(a.out) / "frame_####")


def main():
    argv = sys.argv[sys.argv.index("--") + 1:]
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--quality", default="preview", choices=["preview", "production", "cycles", "realistic"])
    ap.add_argument("--samples", type=int, default=64)
    ap.add_argument("--cpu", action="store_true", help="force Cycles CPU (CI runners have no GPU)")
    ap.add_argument("--hdri", default="")
    ap.add_argument("--frame-start", dest="frame_start", type=int, default=0)
    ap.add_argument("--frame-end", dest="frame_end", type=int, default=-1)
    ap.add_argument("--width", type=int, default=540)
    ap.add_argument("--height", type=int, default=960)
    ap.add_argument("--blend", default="")
    ap.add_argument("--font", default="")
    ap.add_argument("--no-render", action="store_true")
    ap.add_argument("--stills", default="", help="comma-separated frames to render as stills only")
    args = ap.parse_args(argv)
    plan = json.loads(Path(args.plan).read_text())
    Path(args.out).mkdir(parents=True, exist_ok=True)

    bpy.ops.wm.read_factory_settings(use_empty=True)
    b = Build(plan, args)
    b.configure_render()
    b.build_objects()
    b.apply_actions()
    b.world_and_lights()
    b.camera_setup()
    framing = b.frame_camera()
    bpy.context.scene.frame_set(0)
    empty = [o.name for o in bpy.data.objects if o.type == "MESH" and not o.data.vertices]
    report = {"scene": plan["id"], "frames": b.n, "objects": len(bpy.data.objects),
              "framing": framing, "empty_meshes": empty, "warnings": b.warnings}
    if args.blend:
        bpy.ops.wm.save_as_mainfile(filepath=args.blend, copy=True)
    t = time.time()
    if args.stills:
        sc = bpy.context.scene
        for f in (int(x) for x in args.stills.split(",")):
            sc.frame_set(min(f, b.n - 1))
            sc.render.filepath = str(Path(args.out) / f"still_{f:04d}.png")
            bpy.ops.render.render(write_still=True)
    elif not args.no_render:
        bpy.ops.render.render(animation=True)
    report["render_seconds"] = round(time.time() - t, 1)
    (Path(args.out) / "report.json").write_text(json.dumps(report, indent=2))
    print("STUDIO_SCENE_DONE", json.dumps(report))


if __name__ == "__main__":
    main()
