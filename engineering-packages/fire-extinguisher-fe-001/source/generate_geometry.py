"""Generate source/geometry.json and label/gauge/tag textures for FE-001 (generic portable fire extinguisher).

Illustrative engineering model for component identification and inspection guidance. It is not a real
product, not manufacturer CAD and contains no certified specifications. Proportions are typical of a small
portable stored-pressure extinguisher; all dimensions are illustrative. The exploded view is NOT a
disassembly or service procedure.

    backend/.venv/Scripts/python engineering-packages/fire-extinguisher-fe-001/source/generate_geometry.py
    backend/.venv/Scripts/python tools/build_package.py engineering-packages/fire-extinguisher-fe-001

Axes: Y up, +Z = front (gauge and label side), +X = right when facing the front. Units: metres.
"""
import json
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).parent
TEX = HERE / "textures"
TEX.mkdir(exist_ok=True)

R = 0.060  # cylinder radius (illustrative)
nodes = []


def add(node):
    for k in ("position", "rotation_deg"):
        if k in node:
            node[k] = [round(v, 5) for v in node[k]]
    nodes.append(node)


# ---- pressure cylinder (lathe profile, bottom -> top) and protective base boot ----------------
cyl_profile = [(0.0, 0.004), (0.050, 0.004), (0.0565, 0.008), (0.0595, 0.016), (R, 0.030), (R, 0.330),
               (0.0588, 0.345), (0.0555, 0.360), (0.0495, 0.375), (0.040, 0.388), (0.030, 0.396),
               (0.022, 0.400), (0.0, 0.401)]
add({"id": "cylinder_body", "shape": "lathe", "profile": cyl_profile, "position": [0, 0, 0], "material": "red"})
add({"id": "cylinder_base", "shape": "lathe", "segments": 36,
     "profile": [(0.0, 0.0), (0.0612, 0.0), (0.0620, 0.006), (0.0620, 0.022), (0.0606, 0.025)],
     "position": [0, 0, 0], "material": "boot"})

# ---- valve assembly --------------------------------------------------------------------------
add({"id": "valve_collar", "shape": "cylinder", "radius": 0.021, "height": 0.016, "position": [0, 0.408, 0], "material": "valve"})
add({"id": "valve_body", "shape": "box", "size": [0.044, 0.040, 0.050], "position": [0, 0.436, 0], "material": "valve"})
add({"id": "valve_outlet", "shape": "cylinder", "radius": 0.008, "height": 0.022, "position": [0.031, 0.430, 0],
     "rotation_deg": [0, 0, 90], "material": "valve"})

# ---- pressure gauge on the valve front -----------------------------------------------------------
add({"id": "gauge_housing", "shape": "cylinder", "radius": 0.017, "height": 0.010, "position": [0, 0.442, 0.030],
     "rotation_deg": [90, 0, 0], "material": "gauge_rim"})
add({"id": "gauge_face", "shape": "disc", "radius": 0.0145, "position": [0, 0.442, 0.0352], "material": "gauge_face"})

# ---- carrying handle (fixed, lower) and operating lever (upper), both extending to the rear --------
add({"id": "handle_bar", "shape": "box", "size": [0.026, 0.005, 0.115], "position": [0, 0.458, -0.078],
     "rotation_deg": [-4, 0, 0], "material": "handle"})
add({"id": "handle_end", "shape": "box", "size": [0.026, 0.022, 0.005], "position": [0, 0.452, -0.136], "material": "handle"})
add({"id": "lever", "shape": "box", "size": [0.024, 0.005, 0.125], "position": [0, 0.479, -0.045],
     "rotation_deg": [10, 0, 0], "material": "lever"})

# ---- safety pin (through the valve between handle and lever) and tamper seal --------------------
add({"id": "pin_shaft", "shape": "cylinder", "radius": 0.0022, "height": 0.060, "position": [0, 0.465, -0.006],
     "rotation_deg": [0, 0, 90], "material": "pin"})
add({"id": "pin_ring", "shape": "torus", "radius": 0.011, "tube": 0.0018, "position": [-0.041, 0.465, -0.006],
     "rotation_deg": [0, 0, 90], "material": "pin"})
add({"id": "tamper_seal", "shape": "torus", "radius": 0.0065, "tube": 0.0013, "position": [-0.041, 0.452, -0.012],
     "rotation_deg": [90, 0, 0], "material": "seal"})


# ---- discharge hose (smoothed path from the valve outlet down the right side) and nozzle --------
def catmull_rom(points, samples=6):
    out = []
    pts = [points[0]] + points + [points[-1]]
    for i in range(1, len(pts) - 2):
        p0, p1, p2, p3 = pts[i - 1], pts[i], pts[i + 1], pts[i + 2]
        for k in range(samples):
            t = k / samples
            out.append(tuple(0.5 * (2 * p1[d] + (-p0[d] + p2[d]) * t + (2 * p0[d] - 5 * p1[d] + 4 * p2[d] - p3[d]) * t * t
                                    + (-p0[d] + 3 * p1[d] - 3 * p2[d] + p3[d]) * t ** 3) for d in range(3)))
    out.append(points[-1])
    return [[round(v, 5) for v in p] for p in out]


hose_ctrl = [(0.040, 0.430, 0.000), (0.062, 0.426, 0.004), (0.078, 0.405, 0.012), (0.082, 0.360, 0.022),
             (0.080, 0.280, 0.030), (0.076, 0.200, 0.034), (0.073, 0.150, 0.036)]
add({"id": "hose", "shape": "tube", "path": catmull_rom(hose_ctrl), "radius": 0.0075, "radial": 14,
     "position": [0, 0, 0], "material": "hose"})
nozzle_len = 0.062
add({"id": "nozzle", "shape": "lathe", "segments": 24,
     "profile": [(0.0040, 0.0), (0.0062, 0.004), (0.0078, 0.020), (0.0095, 0.050), (0.0098, nozzle_len), (0.0, nozzle_len)],
     "position": [0.073, 0.150 - nozzle_len, 0.036], "material": "nozzle"})

# ---- operating instructions label (wraps the front of the cylinder) and inspection tag ----------
add({"id": "instructions_label", "shape": "arc_panel", "radius": R + 0.0006, "height": 0.150, "a0_deg": 30, "a1_deg": 150,
     "position": [0, 0.200, 0], "material": "label"})
add({"id": "tag_card", "shape": "plane", "size": [0.038, 0.070], "position": [-0.072, 0.385, 0.012],
     "rotation_deg": [0, -30, 0], "material": "tag"})
add({"id": "tag_string", "shape": "tube", "radius": 0.0009, "radial": 6, "material": "string", "position": [0, 0, 0],
     "path": catmull_rom([(-0.040, 0.458, -0.008), (-0.058, 0.440, 0.002), (-0.070, 0.420, 0.010)], 4)})

# ---- wall mounting bracket (behind the cylinder) -------------------------------------------------
add({"id": "bracket_plate", "shape": "box", "size": [0.055, 0.140, 0.004], "position": [0, 0.300, -0.082], "material": "bracket"})
add({"id": "bracket_strap", "shape": "arc_panel", "radius": R + 0.0025, "height": 0.016, "a0_deg": 195, "a1_deg": 345,
     "position": [0, 0.300, 0], "material": "bracket"})
add({"id": "bracket_hook", "shape": "box", "size": [0.030, 0.006, 0.050], "position": [0, 0.394, -0.058], "material": "bracket"})


# ---- textures (Pillow; generic text only, no brand, ratings or certification marks) -------------
def font(size):
    return ImageFont.load_default(size=size)


def label_texture():
    w, h = 512, 604
    im = Image.new("RGB", (w, h), (250, 250, 246))
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, w, 64], fill=(25, 25, 28))
    d.text((w / 2, 32), "DEMONSTRATION MODEL", fill=(255, 255, 255), font=font(34), anchor="mm")
    d.text((w / 2, 100), "Portable fire extinguisher", fill=(20, 20, 20), font=font(30), anchor="mm")
    d.text((w / 2, 136), "ABC dry chemical (illustrative)", fill=(60, 60, 60), font=font(24), anchor="mm")
    d.rectangle([24, 166, w - 24, 214], fill=(200, 20, 20))
    d.text((w / 2, 190), "TO OPERATE", fill=(255, 255, 255), font=font(30), anchor="mm")
    steps = ["1  PULL the pin", "2  AIM at the base of the fire", "3  SQUEEZE the lever", "4  SWEEP side to side"]
    for i, s in enumerate(steps):
        d.text((40, 236 + i * 46), s, fill=(20, 20, 20), font=font(28))
    d.line([24, 430, w - 24, 430], fill=(120, 120, 120), width=2)
    d.text((w / 2, 462), "Ratings, capacity and pressure:", fill=(40, 40, 40), font=font(22), anchor="mm")
    d.text((w / 2, 492), "manufacturer-dependent (not specified)", fill=(40, 40, 40), font=font(22), anchor="mm")
    d.rectangle([24, 528, w - 24, 580], outline=(200, 20, 20), width=3)
    d.text((w / 2, 554), "NOT A REAL PRODUCT LABEL", fill=(200, 20, 20), font=font(26), anchor="mm")
    im.save(TEX / "label.png", optimize=True)


def gauge_texture():
    s = 256
    im = Image.new("RGB", (s, s), (245, 245, 240))
    d = ImageDraw.Draw(im)
    c = s / 2
    box = [24, 24, s - 24, s - 24]
    d.arc(box, 200, 250, fill=(200, 30, 30), width=18)   # low (left)
    d.arc(box, 250, 290, fill=(30, 150, 50), width=18)   # middle (top)
    d.arc(box, 290, 340, fill=(200, 30, 30), width=18)   # high (right)
    d.text((c, c + 40), "DEMO", fill=(90, 90, 90), font=font(22), anchor="mm")
    d.text((c, c + 66), "illustrative", fill=(90, 90, 90), font=font(16), anchor="mm")
    ang = math.radians(268)
    d.line([c, c, c + 88 * math.cos(ang), c + 88 * math.sin(ang)], fill=(20, 20, 20), width=6)
    d.ellipse([c - 9, c - 9, c + 9, c + 9], fill=(20, 20, 20))
    im.save(TEX / "gauge.png", optimize=True)


def tag_texture():
    w, h = 256, 472
    im = Image.new("RGB", (w, h), (250, 214, 60))
    d = ImageDraw.Draw(im)
    d.ellipse([w / 2 - 14, 14, w / 2 + 14, 42], fill=(70, 70, 70))
    d.text((w / 2, 72), "INSPECTION", fill=(20, 20, 20), font=font(30), anchor="mm")
    d.text((w / 2, 104), "TAG", fill=(20, 20, 20), font=font(30), anchor="mm")
    d.text((w / 2, 136), "DEMO - not a record", fill=(120, 30, 30), font=font(18), anchor="mm")
    d.text((20, 166), "DATE", fill=(20, 20, 20), font=font(18))
    d.text((150, 166), "BY", fill=(20, 20, 20), font=font(18))
    for i in range(7):
        y = 200 + i * 36
        d.line([16, y, w - 16, y], fill=(60, 60, 60), width=2)
    d.line([138, 192, 138, 200 + 6 * 36], fill=(60, 60, 60), width=2)
    im.save(TEX / "tag.png", optimize=True)


label_texture()
gauge_texture()
tag_texture()

geometry = {
    "name": "FE-001 rev A (illustrative portable fire extinguisher)",
    "units": "m",
    "axes": "Y up, +Z = front (gauge/label side), +X = right when facing the front",
    "provenance": "Generated by source/generate_geometry.py. Illustrative model; not a real product or manufacturer CAD.",
    "materials": {
        "red":        {"color": [0.72, 0.05, 0.04], "metallic": 0.25, "roughness": 0.35},
        "boot":       {"color": [0.06, 0.06, 0.07], "metallic": 0.0, "roughness": 0.70},
        "valve":      {"color": [0.30, 0.31, 0.33], "metallic": 0.35, "roughness": 0.40},
        "gauge_rim":  {"color": [0.75, 0.76, 0.78], "metallic": 0.40, "roughness": 0.30},
        "gauge_face": {"color": [1.0, 1.0, 1.0], "metallic": 0.0, "roughness": 0.40, "texture": "textures/gauge.png"},
        "handle":     {"color": [0.16, 0.16, 0.18], "metallic": 0.30, "roughness": 0.45},
        "lever":      {"color": [0.70, 0.71, 0.73], "metallic": 0.40, "roughness": 0.35},
        "pin":        {"color": [0.78, 0.79, 0.81], "metallic": 0.45, "roughness": 0.30},
        "seal":       {"color": [0.92, 0.78, 0.10], "metallic": 0.0, "roughness": 0.60},
        "hose":       {"color": [0.05, 0.05, 0.05], "metallic": 0.0, "roughness": 0.80},
        "nozzle":     {"color": [0.09, 0.09, 0.10], "metallic": 0.0, "roughness": 0.60},
        "label":      {"color": [1.0, 1.0, 1.0], "metallic": 0.0, "roughness": 0.70, "texture": "textures/label.png"},
        "tag":        {"color": [1.0, 1.0, 1.0], "metallic": 0.0, "roughness": 0.80, "texture": "textures/tag.png"},
        "string":     {"color": [0.85, 0.85, 0.80], "metallic": 0.0, "roughness": 0.90},
        "bracket":    {"color": [0.22, 0.23, 0.25], "metallic": 0.30, "roughness": 0.50},
    },
    "nodes": nodes,
}
(HERE / "geometry.json").write_text(json.dumps(geometry, indent=1) + "\n", encoding="utf-8")
print(f"wrote geometry.json ({len(nodes)} nodes) and textures in {TEX}")
