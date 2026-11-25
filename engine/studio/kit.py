"""Kit: pre-built, art-directed assemblies the AI director places by name.

Free LLMs can't model a convincing magnetron from boxes in one shot, but they can place one. A scene object
`{"id": "mag", "kit": "magnetron", "position": [...], "rotation": [...], "scale": 1, "cut": [0,-1,0]}` expands
(before validation) into an `empty` called `mag` plus every part as `mag_<part>` parented to it, so actions can
move the whole kit (`mag`) or one part (`mag_cathode`). All geometry is plain SceneSpec objects: same sandbox.

Conventions: Z up, camera looks along +Y (front faces -Y), each kit is centred on its origin and ~2-3 units tall.
`cut` on an instance slices every solid part with one plane through the kit origin (cutaway view); parts marked
"nocut" (moving internals) stay whole.
"""

from __future__ import annotations

import copy
import math
from typing import Any


def P(id, kind, mat="clay", pos=(0, 0, 0), rot=(0, 0, 0), parent=None, nocut=False, scale=1.0, **params) -> dict:
    o = {"id": id, "kind": kind, "material": mat, "position": list(pos), "rotation": list(rot), "params": params,
         "scale": list(scale) if isinstance(scale, tuple) else scale}
    if parent:
        o["parent"] = parent
    if nocut:
        o["nocut"] = True
    return o


def ring(n, r, z=0.0, a0=0.0):
    return [(r * math.cos(a0 + 2 * math.pi * i / n), r * math.sin(a0 + 2 * math.pi * i / n), z, math.degrees(a0 + 2 * math.pi * i / n))
            for i in range(n)]


def _sine(length, amp, waves, axis_pts=60):
    return [[-length / 2 + length * i / axis_pts, 0, amp * math.sin(2 * math.pi * waves * i / axis_pts)] for i in range(axis_pts + 1)]


# ── Kits ─────────────────────────────────────────────────────────────────
# Each: desc (what it is), moving (part ids + how they really move, for the prompt), parts.

KIT: dict[str, dict[str, Any]] = {}


def kit(name, desc, moving, parts):
    KIT[name] = {"desc": desc, "moving": moving, "parts": parts}


kit("magnetron", "microwave-oven magnetron tube: copper anode ring with resonant vanes, glowing cathode, ring magnets, "
    "cooling fins, antenna dome on top", "cathode glows (highlight); electrons = flow spiralling outwards; antenna emits",
    [P("anode", "lathe", "brass", profile=[[0.62, -0.32], [0.62, 0.32]], thickness=0.12, cut_material="accent2"),
     *[P(f"vane_{i}", "box", "brass", (x * 0.78, y * 0.78, 0), (0, 0, a), size=[0.38, 0.06, 0.6], bevel=0.01)
       for i, (x, y, _, a) in enumerate(ring(8, 0.5))],
     P("cathode", "cylinder", "flame", radius=0.07, depth=0.9, nocut=True),
     P("cathode_coil", "spring", "accent2", coils=8, radius=0.09, wire=0.012, height=0.6, nocut=True),
     P("magnet_top", "cylinder", "dark_steel", (0, 0, 0.62), radius=0.72, depth=0.22, bevel=0.04),
     P("magnet_bottom", "cylinder", "dark_steel", (0, 0, -0.62), radius=0.72, depth=0.22, bevel=0.04),
     *[P(f"fin_{i}", "box", "steel", (0, 0, -0.28 + i * 0.14), size=[1.9, 1.9, 0.03], bevel=0.005) for i in range(5)],
     P("antenna_stem", "cylinder", "chrome", (0, 0, 0.95), radius=0.05, depth=0.5),
     P("antenna_dome", "lathe", "steel", (0, 0, 1.2), profile=[[0.2, -0.1], [0.2, 0.05], [0.14, 0.16], [0.0, 0.2]], thickness=0.03),
     P("filament_leads", "tube", "chrome", points=[[0.04, 0, -0.45], [0.05, 0, -0.9], [0.3, 0, -1.2]], radius=0.025, nocut=True),
     P("electrons", "flow", "air", nocut=True, count=24, radius=0.025, speed=0.5, radial_copies=8, axis="z",
       points=[[(0.1 + 0.03 * i) * math.cos(i * 0.45), (0.1 + 0.03 * i) * math.sin(i * 0.45), 0] for i in range(14)])])

kit("microwave_cavity", "cutaway microwave oven: metal cooking cavity, glass door, glass turntable on a drive motor, "
    "waveguide on the right wall where the magnetron mounts, control panel",
    "turntable spins about Z (~30 deg/s); door can rotate on its hinge (pivot at left edge)",
    [P("floor", "box", "steel", (0, 0, -0.75), size=[2.4, 1.8, 0.06]),
     P("ceiling", "box", "steel", (0, 0, 0.75), size=[2.4, 1.8, 0.06]),
     P("back_wall", "box", "steel", (0, 0.9, 0), size=[2.4, 0.06, 1.56]),
     P("left_wall", "box", "steel", (-1.2, 0, 0), size=[0.06, 1.8, 1.56]),
     P("right_wall", "box", "steel", (1.2, 0, 0), size=[0.06, 1.8, 1.56]),
     P("shell_top", "box", "clay", (0.35, 0.05, 0.86), size=[3.3, 2.1, 0.12], bevel=0.05),
     P("shell_bottom", "box", "clay", (0.35, 0.05, -0.86), size=[3.3, 2.1, 0.12], bevel=0.05),
     P("shell_left", "box", "clay", (-1.3, 0.05, 0), size=[0.12, 2.1, 1.6], bevel=0.05),
     P("shell_right", "box", "clay", (2.0, 0.05, 0), size=[0.12, 2.1, 1.6], bevel=0.05),
     P("shell_back", "box", "clay", (0.35, 1.05, 0), size=[3.3, 0.1, 1.6], bevel=0.03),
     P("control_panel", "box", "clay_dark", (1.6, -1.0, 0), size=[0.5, 0.06, 1.6], bevel=0.03),
     *[P(f"button_{i}", "cylinder", "accent", (1.6, -1.05, 0.5 - i * 0.3), (90, 0, 0), radius=0.08, depth=0.05) for i in range(3)],
     P("door", "box", "glass", (-1.25, -0.95, 0), size=[2.5, 0.05, 1.55], pivot=[-1.25, 0, 0], bevel=0.02, nocut=True),
     P("waveguide", "box", "dark_steel", (1.45, 0.2, 0.45), size=[0.4, 0.7, 0.3], bevel=0.02),
     P("turntable", "cylinder", "glass", (0, 0, -0.6), radius=0.75, depth=0.04, nocut=True),
     P("roller_ring", "torus", "ink", (0, 0, -0.66), major=0.45, minor=0.03, nocut=True),
     P("drive_motor", "cylinder", "dark_steel", (0, 0, -0.95), radius=0.18, depth=0.25)])

kit("water_molecule", "water molecule H2O: red oxygen with two white hydrogens at 104.5 deg (a polar dipole)",
    "whole molecule rotates/oscillates to align with an electric field", [
        P("oxygen", "sphere", "accent", radius=0.5),
        *[P(f"hydrogen_{i}", "sphere", "white", (0.62 * math.sin(math.radians(a)), 0, -0.62 * math.cos(math.radians(a))), radius=0.3)
          for i, a in enumerate((52.25, -52.25))],
        P("charge_neg", "label", "ink", (0, -0.2, 0.75), text="-", size=0.3),
        P("charge_pos", "label", "ink", (0, -0.2, -0.95), text="+", size=0.3)])

kit("bowl_of_soup", "ceramic bowl filled with soup", "soup can highlight (warming); steam = flow upwards", [
    P("bowl", "lathe", "clay", profile=[[0.0, -0.35], [0.45, -0.33], [0.75, -0.1], [0.9, 0.3]], thickness=0.05, cut_material="clay"),
    P("soup", "cylinder", "accent2", (0, 0, 0.18), radius=0.82, depth=0.04, nocut=True),
    P("steam", "flow", "white", (0, 0, 0.25), nocut=True, count=10, radius=0.03, speed=0.4, radial_copies=3,
      points=[[0.3, 0, 0], [0.35, 0, 0.4], [0.25, 0, 0.8], [0.35, 0, 1.2]])])

kit("disc_brake", "car disc brake: vented steel brake rotor on a hub, red caliper at the top with two pads and a "
    "hydraulic piston, brake line", "rotor spins about Y; pads move in Y to clamp; piston pushes pad_inner",
    [P("rotor", "cylinder", "steel", radius=1.1, depth=0.22, axis="y", segments=96, nocut=True),
     P("rotor_vents", "torus", "dark_steel", major=0.85, minor=0.06, axis="y", nocut=True),
     P("hub", "cylinder", "dark_steel", (0, -0.2, 0), radius=0.45, depth=0.25, axis="y", nocut=True),
     *[P(f"stud_{i}", "cylinder", "chrome", (x, -0.36, z), radius=0.05, depth=0.12, axis="y", nocut=True)
       for i, (x, z, _, _) in enumerate(ring(5, 0.28))],
     P("caliper", "box", "accent", (0, 0, 1.05), size=[0.9, 0.7, 0.4], bevel=0.08),
     P("pad_outer", "box", "ink", (0, -0.17, 0.95), size=[0.7, 0.08, 0.28]),
     P("pad_inner", "box", "ink", (0, 0.17, 0.95), size=[0.7, 0.08, 0.28]),
     P("piston", "cylinder", "chrome", (0, 0.3, 0.95), radius=0.14, depth=0.16, axis="y"),
     P("brake_line", "tube", "ink", points=[[0.4, 0.3, 1.2], [0.9, 0.5, 1.5], [1.4, 0.6, 1.4]], radius=0.04)])

kit("car_wheel", "car wheel: rubber tyre on a 5-spoke alloy rim with hub", "whole wheel spins about Y", [
    P("tyre", "torus", "ink", major=1.05, minor=0.32, axis="y"),
    P("rim", "lathe", "chrome", axis="y", profile=[[0.78, -0.2], [0.8, 0.0], [0.78, 0.2]], thickness=0.06, cut_material="chrome"),
    *[P(f"spoke_{i}", "box", "chrome", (0.4 * math.cos(math.radians(a)), -0.12, 0.4 * math.sin(math.radians(a))), (0, -a, 0), size=[0.75, 0.06, 0.14])
      for i, a in enumerate(range(90, 450, 72))],
    P("hub_cap", "cylinder", "steel", (0, -0.14, 0), radius=0.16, depth=0.08, axis="y")])

kit("abs_modulator", "ABS hydraulic modulator: aluminium valve block with four solenoid valves, pump motor, "
    "accumulator and brake-line ports", "valves pulse (open/close several times per second); pump motor spins",
    [P("block", "box", "steel", size=[1.6, 1.0, 0.9], bevel=0.06),
     *[P(f"valve_{i}", "cylinder", "accent", (-0.54 + i * 0.36, 0, 0.62), radius=0.13, depth=0.35) for i in range(4)],
     *[P(f"valve_coil_{i}", "spring", "brass", (-0.54 + i * 0.36, 0, 0.62), coils=10, radius=0.145, wire=0.012, height=0.28, nocut=True) for i in range(4)],
     P("pump_motor", "cylinder", "clay_dark", (0, -0.85, 0), radius=0.35, depth=0.7, axis="y"),
     P("accumulator", "cylinder", "dark_steel", (0.95, 0, -0.1), radius=0.18, depth=0.6),
     *[P(f"port_{i}", "cylinder", "brass", (-0.6 + i * 0.4, 0.55, 0.2), radius=0.06, depth=0.15, axis="y") for i in range(4)],
     P("plunger", "cylinder", "chrome", (-0.54, 0, 0.3), radius=0.05, depth=0.35, nocut=True)])

kit("wheel_speed_sensor", "ABS wheel-speed sensor: toothed tone ring on the axle with a magnetic pickup reading the teeth",
    "tone_ring spins about Z; pulses = highlight the sensor tip", [
        P("tone_ring", "gear", "steel", teeth=48, module=0.05, thickness=0.18, bore=0.4, nocut=True),
        P("axle", "cylinder", "dark_steel", radius=0.38, depth=1.0, nocut=True),
        P("sensor", "cylinder", "clay_dark", (0, -1.55, 0), (90, 0, 0), radius=0.12, depth=0.7),
        P("sensor_tip", "cylinder", "accent", (0, -1.27, 0), (90, 0, 0), radius=0.08, depth=0.1),
        P("sensor_wire", "tube", "ink", points=[[0, -1.9, 0], [0.3, -2.2, 0.4], [0.8, -2.3, 0.6]], radius=0.035)])

kit("electric_motor", "brushless electric motor in a cutaway housing: stator with copper windings, magnetic rotor, "
    "shaft and bearings", "rotor and shaft spin about Z together; windings highlight in sequence (rotating field)",
    [P("housing", "lathe", "steel", profile=[[1.0, -0.8], [1.05, -0.7], [1.05, 0.7], [1.0, 0.8]], sweep=270, start_angle=-45,
       thickness=0.06),
     *[P(f"winding_{i}", "torus", "brass", (0.75 * math.cos(math.radians(a)), 0.75 * math.sin(math.radians(a)), 0), (0, 90, a),
         major=0.22, minor=0.07) for i, (_, _, _, a) in enumerate(ring(6, 1.0))],
     *[P(f"tooth_{i}", "box", "dark_steel", (0.75 * x, 0.75 * y, 0), (0, 0, a), size=[0.3, 0.16, 1.1]) for i, (x, y, _, a) in enumerate(ring(6, 1.0))],
     P("rotor", "cylinder", "dark_steel", radius=0.42, depth=1.1, nocut=True),
     *[P(f"magnet_{i}", "box", "accent" if i % 2 else "blue", (0.44 * x, 0.44 * y, 0), (0, 0, a), parent="rotor", nocut=True,
         size=[0.06, 0.3, 1.0]) for i, (x, y, _, a) in enumerate(ring(4, 1.0, a0=math.pi / 4))],
     P("shaft", "cylinder", "chrome", (0, 0, 0.3), radius=0.08, depth=2.4, nocut=True, parent="rotor"),
     P("bearing_top", "torus", "steel", (0, 0, 0.85), major=0.14, minor=0.05),
     P("bearing_bottom", "torus", "steel", (0, 0, -0.85), major=0.14, minor=0.05)])

kit("electromagnet", "electromagnet: iron core wrapped in a copper coil, with lead wires", "core highlights when energised", [
    P("core", "cylinder", "dark_steel", radius=0.25, depth=2.0),
    P("coil", "spring", "brass", coils=22, radius=0.32, wire=0.045, height=1.5),
    P("lead_a", "tube", "accent", points=[[0.32, 0, 0.75], [0.6, 0, 1.0], [0.9, 0, 1.0]], radius=0.03),
    P("lead_b", "tube", "ink", points=[[0.32, 0, -0.75], [0.6, 0, -1.0], [0.9, 0, -1.0]], radius=0.03)])

kit("bar_magnet", "bar magnet with red north and blue south poles", "", [
    P("north", "box", "accent", (0, 0, 0.5), size=[0.5, 0.5, 1.0], bevel=0.04),
    P("south", "box", "blue", (0, 0, -0.5), size=[0.5, 0.5, 1.0], bevel=0.04),
    P("label_n", "label", "ink", (0, -0.4, 0.5), text="N", size=0.25),
    P("label_s", "label", "ink", (0, -0.4, -0.5), text="S", size=0.25)])

kit("quartz_resonator", "quartz crystal tuning-fork resonator (watch crystal): glassy quartz fork with silver electrodes, "
    "in a metal can with two leads", "prong_l and prong_r oscillate in X in opposite directions (tiny amplitude, "
    "32768 Hz shown slowed)", [
        P("can", "lathe", "steel", profile=[[0.0, 1.5], [0.42, 1.45], [0.45, 1.3], [0.45, -0.9], [0.5, -1.0]],
          sweep=200, start_angle=-10, thickness=0.03),
        P("base", "cylinder", "dark_steel", (0, 0, -1.05), radius=0.5, depth=0.15),
        P("fork_base", "box", "glass", (0, 0, -0.65), size=[0.6, 0.12, 0.4], bevel=0.02, nocut=True),
        P("prong_l", "box", "glass", (-0.2, 0, 0.35), size=[0.16, 0.12, 1.6], bevel=0.02, nocut=True),
        P("prong_r", "box", "glass", (0.2, 0, 0.35), size=[0.16, 0.12, 1.6], bevel=0.02, nocut=True),
        P("electrode_l", "box", "chrome", (0, -0.065, -0.05), size=[0.1, 0.01, 1.3], parent="prong_l", nocut=True),
        P("electrode_r", "box", "chrome", (0, -0.065, -0.05), size=[0.1, 0.01, 1.3], parent="prong_r", nocut=True),
        P("lead_a", "cylinder", "chrome", (-0.2, 0, -1.6), radius=0.03, depth=1.0, nocut=True),
        P("lead_b", "cylinder", "chrome", (0.2, 0, -1.6), radius=0.03, depth=1.0, nocut=True)])

kit("clock_movement", "quartz clock movement: AA battery, stepper motor coil, gear train driving hour/minute/second hands",
    "spin ONLY gear_drive (the train follows at true ratios); hands are children of their gears", [
        P("plate", "box", "clay_dark", (0.6, 0.25, 0.0), size=[3.8, 0.08, 3.8], bevel=0.04),
        P("battery", "cylinder", "accent2", (-0.4, 0, -1.6), radius=0.22, depth=1.0, axis="x"),
        P("battery_cap", "cylinder", "chrome", (0.12, 0, -1.6), radius=0.1, depth=0.06, axis="x"),
        P("motor_coil", "spring", "brass", (1.7, 0, -1.55), coils=14, radius=0.2, wire=0.03, height=0.5),
        P("train", "empty", pos=(0, -0.1, 0.2), rot=(90, 0, 0), nocut=True),
        P("gear_drive", "gear", "brass", (0.75, 0.05, 0), parent="train", teeth=12, module=0.06, thickness=0.06, nocut=True),
        P("gear_mid", "gear", "brass", parent="train", teeth=40, module=0.06, thickness=0.06, arms=4,
          pinion_teeth=10, mesh_with="gear_drive", angle=170, nocut=True),
        P("gear_out", "gear", "steel", parent="train", teeth=20, module=0.06, thickness=0.06, arms=5,
          mesh_with="gear_mid", angle=-30, nocut=True),
        P("hand", "box", "ink", (0, 0.45, 0.08), size=[0.06, 0.9, 0.02], parent="gear_out", nocut=True)])

kit("maglev", "maglev train section over its guideway: streamlined car body wrapping a T-shaped concrete beam, "
    "levitation electromagnets under the beam lip, guidance magnets on the sides, 1 cm air gap",
    "car moves in X along the guideway (and can oscillate slightly in Z when levitating); magnets highlight", [
        P("beam", "box", "clay_dark", (0, 0, -0.9), size=[6.0, 1.0, 0.8], bevel=0.03),
        P("beam_top", "box", "clay_dark", (0, 0, -0.4), size=[6.0, 2.0, 0.3], bevel=0.03),
        P("rail_l", "box", "dark_steel", (0, -0.95, -0.6), size=[6.0, 0.12, 0.12]),
        P("rail_r", "box", "dark_steel", (0, 0.95, -0.6), size=[6.0, 0.12, 0.12]),
        P("car", "empty", nocut=True),
        P("body", "box", "white", (0, 0, 0.55), size=[3.6, 2.4, 1.3], bevel=0.25, parent="car"),
        P("nose", "lathe", "white", (1.79, 0, 0.5), axis="x", profile=[[1.0, 0], [0.95, 0.4], [0.75, 0.9], [0.4, 1.3], [0.0, 1.45]],
          thickness=0.03, parent="car", cut_material="white", scale=(1.0, 1.2, 0.65)),
        P("nose_window", "box", "glass", (2.4, 0, 0.85), (0, 25, 0), size=[0.7, 1.7, 0.03], parent="car"),
        P("window_band", "box", "glass", (0.1, -1.21, 0.8), size=[3.2, 0.02, 0.3], parent="car"),
        P("stripe", "box", "accent", (0, -1.21, 0.35), size=[3.6, 0.02, 0.12], parent="car"),
        *[P(f"skirt_{s}", "box", "white", (0, side * 1.15, -0.45), size=[3.4, 0.1, 0.8], parent="car")
          for s, side in (("l", -1), ("r", 1))],
        *[P(f"lift_magnet_{s}", "box", "accent", (0, side * 0.85, -0.67), size=[3.0, 0.28, 0.12], parent="car")
          for s, side in (("l", -1), ("r", 1))],
        *[P(f"guide_magnet_{s}", "box", "blue", (0, side * 1.07, -0.55), size=[3.0, 0.06, 0.25], parent="car")
          for s, side in (("l", -1), ("r", 1))]])

kit("piston_engine", "single cylinder of a 4-stroke engine in cutaway: cylinder with head, piston with rings, "
    "connecting rod, crankshaft with counterweight, intake and exhaust valves, spark plug",
    "crank rotates about Y; piston moves in Z (cycle, 2 x crank radius); valves move in Z; spark = highlight", [
        P("cylinder", "lathe", "steel", profile=[[0.62, -0.3], [0.62, 1.8]], sweep=200, start_angle=-10, thickness=0.1),
        P("head", "box", "dark_steel", (0, 0, 1.95), size=[1.6, 1.4, 0.35], bevel=0.05),
        P("piston", "cylinder", "chrome", (0, 0, 0.7), radius=0.58, depth=0.6, nocut=True),
        *[P(f"ring_{i}", "torus", "dark_steel", (0, 0, 0.88 - i * 0.1), major=0.58, minor=0.02, parent=None, nocut=True) for i in range(2)],
        P("conrod", "box", "steel", (0, 0, -0.1), size=[0.18, 0.12, 1.4], bevel=0.04, nocut=True),
        P("crank", "cylinder", "dark_steel", (0, 0, -0.9), radius=0.12, depth=1.4, axis="y", nocut=True),
        P("counterweight", "cylinder", "dark_steel", (0, -0.3, 0.2), radius=0.45, depth=0.12, axis="y", parent="crank", nocut=True),
        P("intake_valve", "cylinder", "steel", (-0.3, 0, 1.75), radius=0.04, depth=0.7, nocut=True),
        P("exhaust_valve", "cylinder", "steel", (0.3, 0, 1.75), radius=0.04, depth=0.7, nocut=True),
        P("spark_plug", "cylinder", "white", (0, 0, 2.3), radius=0.08, depth=0.5),
        P("spark_tip", "sphere", "flame", (0, 0, 1.6), radius=0.05, nocut=True)])

kit("centrifugal_pump", "centrifugal pump: cutaway volute casing, curved-vane impeller, axial inlet pipe and tangential "
    "outlet", "impeller spins about Y; fluid = flow from inlet through outlet", [
        P("casing", "lathe", "accent", axis="y", profile=[[1.2, -0.3], [1.25, 0], [1.2, 0.3]], sweep=260, start_angle=40, thickness=0.06),
        P("back_plate", "cylinder", "dark_steel", (0, 0.32, 0), radius=1.25, depth=0.06, axis="y"),
        P("impeller", "rotor", "steel", blades=7, r_in=0.25, r_out=1.05, chord=0.5, pitch=80, twist=25, thickness=0.05,
          axis="y", nocut=True),
        P("inlet", "lathe", "steel", axis="y", profile=[[0.32, -0.3], [0.32, -1.4]], thickness=0.04),
        P("outlet", "box", "steel", (1.0, 0, 1.2), size=[0.5, 0.5, 0.9], bevel=0.04),
        P("water", "flow", "air", nocut=True, count=30, radius=0.04, speed=1.2,
          points=[[0, -1.4, 0], [0, -0.3, 0], [0.6, 0, 0.4], [1.0, 0, 0.9], [1.0, 0, 1.8]])])

kit("ball_bearing", "ball bearing: outer race, inner race, steel balls in a brass cage", "inner_race spins about Z; "
    "balls_cage spins about Z at ~40% of that speed", [
        P("outer_race", "lathe", "steel", profile=[[1.0, -0.25], [1.0, 0.25]], thickness=0.12),
        P("inner_race", "lathe", "steel", profile=[[0.5, -0.25], [0.5, 0.25]], thickness=0.12, nocut=True),
        P("balls_cage", "empty", nocut=True),
        P("cage", "torus", "brass", major=0.75, minor=0.04, parent="balls_cage", nocut=True),
        *[P(f"ball_{i}", "sphere", "chrome", (x * 0.75, y * 0.75, 0), parent="balls_cage", radius=0.17, nocut=True)
          for i, (x, y, _, _) in enumerate(ring(10, 1.0))]])

kit("battery_cell", "cylindrical lithium-ion cell in cutaway: steel can, rolled anode/separator/cathode layers, "
    "positive cap", "ions = flow between layers (charging/discharging)", [
        P("can", "lathe", "accent2", profile=[[0.5, -1.2], [0.5, 1.2]], sweep=270, start_angle=-45, thickness=0.03),
        P("jelly_roll", "spring", "dark_steel", flat=True, coils=7, radius=0.45, inner_radius=0.08, wire=0.02, nocut=True),
        *[P(f"layer_{i}", "lathe", m, profile=[[0.15 + i * 0.1, -1.1], [0.15 + i * 0.1, 1.1]], sweep=270, start_angle=-45,
            thickness=0.025) for i, m in enumerate(["clay_dark", "brass", "white", "steel"])],
        P("cap", "cylinder", "chrome", (0, 0, 1.25), radius=0.2, depth=0.1),
        P("ions", "flow", "air", nocut=True, count=12, radius=0.025, speed=0.4, radial_copies=6, axis="z",
          points=[[0.15, 0, 0], [0.45, 0, 0]])])

kit("em_wave", "electromagnetic wave travelling along +X (glowing particles riding a sine path) with a direction arrow",
    "it animates by itself (flow)", [
        P("wave", "flow", "air", count=40, radius=0.05, speed=1.5, points=_sine(4.0, 0.45, 2)),
        P("axis_line", "tube", "white", points=[[-2, 0, 0], [2, 0, 0]], radius=0.01),
        P("direction", "arrow", "air", (1.6, 0, -0.8), to=[2.4, 0, -0.8], radius=0.04)])

kit("heating_coil", "glowing resistive heating element (nichrome coil in a ceramic holder)", "coil highlight = heating", [
    P("coil", "spring", "flame", coils=14, radius=0.25, wire=0.05, height=2.0),
    P("holder_top", "box", "clay", (0, 0, 1.15), size=[0.8, 0.5, 0.25], bevel=0.05),
    P("holder_bottom", "box", "clay", (0, 0, -1.15), size=[0.8, 0.5, 0.25], bevel=0.05)])

kit("spring_damper", "car suspension coil-over: shock absorber body, piston rod, coil spring, mounts",
    "rod moves in Z (cycle) while the spring compresses (scale Z)", [
        P("body", "cylinder", "dark_steel", (0, 0, -0.5), radius=0.22, depth=1.6),
        P("rod", "cylinder", "chrome", (0, 0, 0.7), radius=0.07, depth=1.2, nocut=True),
        P("spring", "spring", "accent", coils=8, radius=0.45, wire=0.06, height=2.2),
        P("top_mount", "cylinder", "steel", (0, 0, 1.3), radius=0.55, depth=0.08),
        P("bottom_mount", "cylinder", "steel", (0, 0, -1.0), radius=0.55, depth=0.08),
        P("eye", "torus", "steel", (0, 0, -1.45), major=0.15, minor=0.05, axis="y")])

kit("gear_pair", "two meshing spur gears on shafts (2:1 ratio)", "spin ONLY gear_big; gear_small follows at the true ratio", [
    P("train", "empty", rot=(90, 0, 0), nocut=True),
    P("gear_big", "gear", "brass", (-0.45, 0, 0), parent="train", teeth=32, module=0.06, thickness=0.2, arms=5, nocut=True),
    P("gear_small", "gear", "steel", parent="train", teeth=16, module=0.06, thickness=0.2, mesh_with="gear_big", angle=0, nocut=True)])

kit("housing_cutaway", "generic device enclosure with the front wall removed (beveled box shell), to put other kits inside; "
    "use instance scale [x,y,z] to resize", "", [
        P("back", "box", "clay", (0, 0.95, 0), size=[2.0, 0.1, 2.0]),
        P("left", "box", "clay", (-0.95, 0, 0), size=[0.1, 2.0, 2.0]),
        P("right", "box", "clay", (0.95, 0, 0), size=[0.1, 2.0, 2.0]),
        P("top", "box", "clay", (0, 0, 0.95), size=[2.0, 2.0, 0.1]),
        P("bottom", "box", "clay", (0, 0, -0.95), size=[2.0, 2.0, 0.1])])


# ── Expansion ────────────────────────────────────────────────────────────

INSTANCE_KEYS = {"id", "kit", "position", "rotation", "scale", "parent", "cut", "cut_offset", "materials"}
NOCUT_KINDS = {"label", "flow", "tube", "arrow", "spring", "empty"}


def _kit_pos(parts: dict, o: dict) -> list[float]:
    """Kit-space position of a part (sum of the parent chain; ponytail: assumes parents inside a kit are unrotated)."""
    x = list(o["position"])
    while o.get("parent"):
        o = parts[o["parent"]]
        x = [a + b for a, b in zip(x, o["position"])]
    return x


def expand(objs: list) -> list:
    """Replace every {"kit": ...} entry with its parts; other objects pass through untouched."""
    out = []
    for o in objs:
        if not isinstance(o, dict) or "kit" not in o:
            out.append(o)
            continue
        name, iid = o["kit"], o.get("id")
        if name not in KIT:
            raise ValueError(f"{iid}: unknown kit '{name}'. Kits: {sorted(KIT)}")
        extra = set(o) - INSTANCE_KEYS
        if extra:
            raise ValueError(f"{iid}: kit instances only take {sorted(INSTANCE_KEYS)}; got {sorted(extra)}")
        root = {"id": iid, "kind": "empty", **{k: o[k] for k in ("position", "rotation", "scale", "parent") if k in o}}
        out.append(root)
        parts = {p["id"]: p for p in KIT[name]["parts"]}
        mats = o.get("materials") or {}
        for p in KIT[name]["parts"]:
            q = copy.deepcopy(p)
            q["id"] = f"{iid}_{p['id']}"
            q["parent"] = f"{iid}_{p['parent']}" if p.get("parent") else iid
            if "mesh_with" in q["params"]:
                q["params"]["mesh_with"] = f"{iid}_{q['params']['mesh_with']}"
            if p["id"] in mats:
                q["material"] = mats[p["id"]]
            nocut = q.pop("nocut", False)
            if o.get("cut") and not nocut and q["kind"] not in NOCUT_KINDS:
                n = o["cut"]
                ln = math.sqrt(sum(c * c for c in n)) or 1.0
                q["cut"] = n
                q["cut_offset"] = float(o.get("cut_offset", 0.0)) - sum(a * b / ln for a, b in zip(n, _kit_pos(parts, p)))
            out.append(q)
    return out


def catalog() -> str:
    """Prompt text: every kit, its part ids and how they move."""
    lines = []
    for name, k in KIT.items():
        ids = [p["id"] for p in k["parts"]]
        lines.append(f"- {name}: {k['desc']}. Parts: {', '.join(ids)}." + (f" Motion: {k['moving']}." if k["moving"] else ""))
    return "\n".join(lines)
