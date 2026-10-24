"""Generate source/geometry.json for the venue chair (UTEP Conference Chair, real-world demo).

Approximate geometric model built from five photographs taken at the venue on 2026-10-24.
NOT manufacturer CAD: every dimension below is an estimate read from the photos and should be
treated as a demonstration assumption. Edit the constants and re-run, then rebuild the GLB:

    backend/.venv/Scripts/python engineering-packages/utep-conference-chair-rw/source/generate_geometry.py
    backend/.venv/Scripts/python tools/build_package.py engineering-packages/utep-conference-chair-rw

Axes: Y up, +Z = front of the chair, +X = sitter's left. Units: metres.
"""
import json
import math
from pathlib import Path

# ---- estimated dimensions (from photos; not measured) ------------------------------------------
CASTER_R, CASTER_W, CASTER_DIST = 0.030, 0.040, 0.330
BASE_ARM_LEN, BASE_ARM_W, BASE_ARM_H = 0.300, 0.050, 0.035
HUB_R, HUB_H, HUB_Y = 0.048, 0.060, 0.110
ARM_TIP_Y, ARM_ROOT_Y = 0.070, 0.100
LIFT_R, LIFT_BOTTOM, LIFT_TOP = 0.024, 0.140, 0.507
RING_R, RING_TUBE, RING_Y = 0.190, 0.016, 0.490  # sits just under the seat (photos)
SEAT_W, SEAT_D, SEAT_T, SEAT_TOP = 0.480, 0.460, 0.075, 0.647
SUPPORT_T = 0.030
BACK_PIVOT_Y, BACK_PIVOT_Z, BACK_TILT = 0.600, -0.215, 8.0
BACK_W, FRAME_T = 0.450, 0.035
ARM_X, ARM_TOP_Y, ARM_FRONT_Z, ARM_BAR = 0.268, 0.830, 0.130, 0.030

nodes = []


def box(nid, size, pos, mat, rot=(0, 0, 0)):
    nodes.append({"id": nid, "shape": "box", "size": [round(v, 4) for v in size],
                  "position": [round(v, 4) for v in pos], "rotation_deg": [round(v, 3) for v in rot], "material": mat})


def cyl(nid, r, h, pos, mat, rot=(0, 0, 0)):
    nodes.append({"id": nid, "shape": "cylinder", "radius": r, "height": round(h, 4),
                  "position": [round(v, 4) for v in pos], "rotation_deg": [round(v, 3) for v in rot], "material": mat})


# ---- five-star base, hub and casters -----------------------------------------------------------
cyl("base_hub", HUB_R, HUB_H, (0, HUB_Y, 0), "frame")
slope = math.degrees(math.atan2(ARM_ROOT_Y - ARM_TIP_Y, BASE_ARM_LEN))
for k in range(5):
    a = math.radians(90 + 72 * k)  # first arm points to the front (+Z)
    r_mid = 0.04 + BASE_ARM_LEN / 2
    # rotation: tilt the arm down (about Z), then turn it to its direction (about Y)
    box(f"base_arm_{k + 1}", (BASE_ARM_LEN, BASE_ARM_H, BASE_ARM_W),
        (r_mid * math.cos(a), (ARM_ROOT_Y + ARM_TIP_Y) / 2, r_mid * math.sin(a)), "frame",
        rot=(0, -math.degrees(a), -slope))
    # caster wheel: axis horizontal and perpendicular to the arm, so it rolls radially
    cyl(f"caster_{k + 1}", CASTER_R, CASTER_W, (CASTER_DIST * math.cos(a), CASTER_R, CASTER_DIST * math.sin(a)),
        "caster", rot=(0, -math.degrees(a) + 90, 90))

# ---- gas lift ------------------------------------------------------------------------------------
cyl("gas_lift", LIFT_R, LIFT_TOP - LIFT_BOTTOM, (0, (LIFT_TOP + LIFT_BOTTOM) / 2, 0), "black")

# ---- circular foot ring with collar and three spokes -------------------------------------------
nodes.append({"id": "foot_ring", "shape": "torus", "radius": RING_R, "tube": RING_TUBE,
              "position": [0, RING_Y, 0], "material": "frame"})
cyl("foot_ring_collar", 0.040, 0.045, (0, RING_Y, 0), "frame")
for k, deg in enumerate((270, 30, 150)):  # one spoke to the rear, two to the front sides
    a = math.radians(deg)
    length = RING_R - 0.035
    r_mid = 0.035 + length / 2
    box(f"foot_ring_spoke_{k + 1}", (length, 0.020, 0.028), (r_mid * math.cos(a), RING_Y, r_mid * math.sin(a)),
        "frame", rot=(0, -deg, 0))

# ---- seat ----------------------------------------------------------------------------------------
seat_bottom = SEAT_TOP - SEAT_T
support_y = seat_bottom - SUPPORT_T / 2
box("seat_support", (SEAT_W - 0.02, SUPPORT_T, SEAT_D - 0.02), (0, support_y, 0), "frame")
box("seat_cushion", (SEAT_W, SEAT_T, SEAT_D), (0, seat_bottom + SEAT_T / 2, 0.01), "navy")
box("mechanism", (0.180, 0.035, 0.220), (0, support_y - SUPPORT_T / 2 - 0.0175, -0.010), "black")
box("underside_label", (0.070, 0.002, 0.045), (0.120, support_y - SUPPORT_T / 2 - 0.001, -0.110), "label")

# ---- backrest: frame + mesh in a plane tilted back by BACK_TILT around a pivot behind the seat ---
t = math.radians(BACK_TILT)


def back(h, z_local=0.0):
    """World (y, z) of a point h metres up the back plane (z_local = offset normal to the plane)."""
    return (BACK_PIVOT_Y + h * math.cos(t) + z_local * math.sin(t),
            BACK_PIVOT_Z - h * math.sin(t) + z_local * math.cos(t))


tilt = (-BACK_TILT, 0, 0)
# the frame comes down to seat level behind the cushion and continues under the seat (side photo)
y, z = back(-0.01)
box("back_frame_bottom", (BACK_W - 0.05, 0.050, FRAME_T), (0, y, z), "frame", tilt)
for side, x in (("left", 1), ("right", -1)):
    y, z = back(0.27)
    box(f"back_frame_{side}", (FRAME_T, 0.620, FRAME_T), (x * (BACK_W / 2 - FRAME_T / 2), y, z), "frame", tilt)
box("back_frame_spine", (0.070, 0.030, 0.170), (0, support_y - 0.015, BACK_PIVOT_Z + 0.085), "frame")
y, z = back(0.585)
box("back_frame_top", (BACK_W, 0.045, 0.040), (0, y, z), "frame", tilt)
y, z = back(0.2875, -0.003)
box("back_mesh", (BACK_W - 2 * FRAME_T, 0.535, 0.010), (0, y, z), "mesh", tilt)

# ---- loop armrests: top bar from the back frame, front post down to the seat, lower return bar ---
h_top = (ARM_TOP_Y - BACK_PIVOT_Y) / math.cos(t)
z_back = BACK_PIVOT_Z - h_top * math.sin(t)
top_len = ARM_FRONT_Z - z_back
post_bottom = (SEAT_TOP - 0.045, ARM_FRONT_Z - 0.050)
dy, dz = ARM_TOP_Y - post_bottom[0], ARM_FRONT_Z - post_bottom[1]
post_len = math.hypot(dy, dz)
post_angle = math.degrees(math.atan2(dz, dy))
lower_back_z = BACK_PIVOT_Z + 0.015
for side, x in (("l", 1), ("r", -1)):
    box(f"arm_{side}_top", (ARM_BAR, ARM_BAR, top_len), (x * ARM_X, ARM_TOP_Y, z_back + top_len / 2), "frame")
    box(f"arm_{side}_post", (ARM_BAR, post_len, ARM_BAR),
        (x * ARM_X, (ARM_TOP_Y + post_bottom[0]) / 2, (ARM_FRONT_Z + post_bottom[1]) / 2), "frame", (post_angle, 0, 0))
    low_len = post_bottom[1] - lower_back_z
    box(f"arm_{side}_lower", (ARM_BAR, ARM_BAR, low_len),
        (x * ARM_X, post_bottom[0], lower_back_z + low_len / 2), "frame")

geometry = {
    "name": "UTEP-CHAIR-RW rev A (approximate, from photos)",
    "units": "m",
    "axes": "Y up, +Z = front of chair, +X = sitter's left",
    "provenance": "Generated by source/generate_geometry.py from dimensions estimated in five venue photographs. Not CAD.",
    "materials": {
        "frame":   {"color": [0.80, 0.81, 0.82], "metallic": 0.05, "roughness": 0.55},
        "navy":    {"color": [0.11, 0.15, 0.30], "metallic": 0.0, "roughness": 0.70},
        "mesh":    {"color": [0.16, 0.20, 0.34], "metallic": 0.0, "roughness": 0.95},
        "black":   {"color": [0.05, 0.05, 0.06], "metallic": 0.1, "roughness": 0.45},
        "caster":  {"color": [0.09, 0.09, 0.10], "metallic": 0.0, "roughness": 0.60},
        "label":   {"color": [0.97, 0.97, 0.97], "metallic": 0.0, "roughness": 0.80},
    },
    "nodes": nodes,
}
out = Path(__file__).with_name("geometry.json")
out.write_text(json.dumps(geometry, indent=1) + "\n", encoding="utf-8")
print(f"wrote {out} ({len(nodes)} nodes)")
