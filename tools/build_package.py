"""Build the derived artifacts of an engineering package from its geometry source.

Usage:
    python tools/build_package.py engineering-packages/chair-model-001

Reads  <package>/source/geometry.json   (primitive-based authoring source)
Writes <package>/assembly.glb           (one named glTF node per inspectable part)
       <package>/drawings/general-arrangement.svg (simplified orthographic views)

The GLB is the artifact consumed by the platform. It can equally be replaced by a
GLB exported from Blender/CAD, as long as node names match components.json
(see docs/MODEL_REPLACEMENT.md). No third-party dependencies.
"""
from __future__ import annotations

import json
import math
import struct
import sys
from pathlib import Path


# ---------------------------------------------------------------- geometry --

def box_mesh(sx: float, sy: float, sz: float):
    hx, hy, hz = sx / 2, sy / 2, sz / 2
    faces = [
        ((1, 0, 0), [(hx, -hy, hz), (hx, -hy, -hz), (hx, hy, -hz), (hx, hy, hz)]),
        ((-1, 0, 0), [(-hx, -hy, -hz), (-hx, -hy, hz), (-hx, hy, hz), (-hx, hy, -hz)]),
        ((0, 1, 0), [(-hx, hy, hz), (hx, hy, hz), (hx, hy, -hz), (-hx, hy, -hz)]),
        ((0, -1, 0), [(-hx, -hy, -hz), (hx, -hy, -hz), (hx, -hy, hz), (-hx, -hy, hz)]),
        ((0, 0, 1), [(-hx, -hy, hz), (hx, -hy, hz), (hx, hy, hz), (-hx, hy, hz)]),
        ((0, 0, -1), [(hx, -hy, -hz), (-hx, -hy, -hz), (-hx, hy, -hz), (hx, hy, -hz)]),
    ]
    pos, nrm, idx = [], [], []
    for n, quad in faces:
        base = len(pos)
        pos.extend(quad)
        nrm.extend([n] * 4)
        idx.extend([base, base + 1, base + 2, base, base + 2, base + 3])
    return pos, nrm, idx


def cylinder_mesh(r: float, h: float, segments: int = 20):
    """Cylinder along local Y axis, centred on origin."""
    pos, nrm, idx = [], [], []
    hy = h / 2
    # side
    for i in range(segments + 1):
        a = 2 * math.pi * i / segments
        c, s = math.cos(a), math.sin(a)
        pos += [(r * c, -hy, r * s), (r * c, hy, r * s)]
        nrm += [(c, 0, s), (c, 0, s)]
    for i in range(segments):
        a, b = 2 * i, 2 * i + 2
        idx += [a, a + 1, b + 1, a, b + 1, b]
    # caps
    for y, ny in ((hy, 1), (-hy, -1)):
        centre = len(pos)
        pos.append((0, y, 0))
        nrm.append((0, ny, 0))
        for i in range(segments + 1):
            a = 2 * math.pi * i / segments
            pos.append((r * math.cos(a), y, r * math.sin(a)))
            nrm.append((0, ny, 0))
        for i in range(segments):
            p, q = centre + 1 + i, centre + 2 + i
            idx += [centre, q, p] if ny > 0 else [centre, p, q]
    return pos, nrm, idx


def euler_deg_to_quat(rx: float, ry: float, rz: float):
    """XYZ intrinsic euler (degrees) -> glTF quaternion [x, y, z, w]."""
    x, y, z = (math.radians(v) / 2 for v in (rx, ry, rz))
    cx, sx, cy, sy, cz, sz = math.cos(x), math.sin(x), math.cos(y), math.sin(y), math.cos(z), math.sin(z)
    return [
        sx * cy * cz + cx * sy * sz,
        cx * sy * cz - sx * cy * sz,
        cx * cy * sz + sx * sy * cz,
        cx * cy * cz - sx * sy * sz,
    ]


# --------------------------------------------------------------------- GLB --

def build_glb(geometry: dict) -> bytes:
    materials_src = geometry["materials"]
    mat_names = list(materials_src.keys())
    gltf = {
        "asset": {"version": "2.0", "generator": "field-execution-platform build_package.py"},
        "scene": 0,
        "scenes": [{"name": geometry.get("name", "assembly"), "nodes": [0]}],
        "nodes": [{"name": "assembly_root", "children": []}],
        "meshes": [],
        "materials": [],
        "accessors": [],
        "bufferViews": [],
        "buffers": [],
    }
    for name in mat_names:
        m = materials_src[name]
        gltf["materials"].append({
            "name": name,
            "pbrMetallicRoughness": {
                "baseColorFactor": list(m["color"]) + [1.0],
                "metallicFactor": m.get("metallic", 0.0),
                "roughnessFactor": m.get("roughness", 0.8),
            },
        })

    blob = bytearray()

    def add_view(data: bytes, target: int) -> int:
        while len(blob) % 4:
            blob.append(0)
        offset = len(blob)
        blob.extend(data)
        gltf["bufferViews"].append({"buffer": 0, "byteOffset": offset, "byteLength": len(data), "target": target})
        return len(gltf["bufferViews"]) - 1

    seen = set()
    for node in geometry["nodes"]:
        nid = node["id"]
        if nid in seen:
            raise ValueError(f"duplicate node id {nid}")
        seen.add(nid)
        if node["shape"] == "box":
            pos, nrm, idx = box_mesh(*node["size"])
        elif node["shape"] == "cylinder":
            pos, nrm, idx = cylinder_mesh(node["radius"], node["height"])
        else:
            raise ValueError(f"unsupported shape {node['shape']} on {nid}")

        pos_bytes = b"".join(struct.pack("<3f", *p) for p in pos)
        nrm_bytes = b"".join(struct.pack("<3f", *n) for n in nrm)
        idx_bytes = struct.pack(f"<{len(idx)}H", *idx)
        pv, nv, iv = add_view(pos_bytes, 34962), add_view(nrm_bytes, 34962), add_view(idx_bytes, 34963)
        mins = [min(p[i] for p in pos) for i in range(3)]
        maxs = [max(p[i] for p in pos) for i in range(3)]
        acc = gltf["accessors"]
        acc.append({"bufferView": pv, "componentType": 5126, "count": len(pos), "type": "VEC3", "min": mins, "max": maxs})
        acc.append({"bufferView": nv, "componentType": 5126, "count": len(nrm), "type": "VEC3"})
        acc.append({"bufferView": iv, "componentType": 5123, "count": len(idx), "type": "SCALAR"})
        a0 = len(acc) - 3
        gltf["meshes"].append({
            "name": f"{nid}_mesh",
            "primitives": [{"attributes": {"POSITION": a0, "NORMAL": a0 + 1}, "indices": a0 + 2,
                            "material": mat_names.index(node["material"])}],
        })
        gnode = {"name": nid, "mesh": len(gltf["meshes"]) - 1, "translation": list(node["position"])}
        if any(node.get("rotation_deg", [0, 0, 0])):
            gnode["rotation"] = euler_deg_to_quat(*node["rotation_deg"])
        gltf["nodes"].append(gnode)
        gltf["nodes"][0]["children"].append(len(gltf["nodes"]) - 1)

    while len(blob) % 4:
        blob.append(0)
    gltf["buffers"].append({"byteLength": len(blob)})
    json_bytes = json.dumps(gltf, separators=(",", ":")).encode()
    while len(json_bytes) % 4:
        json_bytes += b" "
    total = 12 + 8 + len(json_bytes) + 8 + len(blob)
    out = struct.pack("<4sII", b"glTF", 2, total)
    out += struct.pack("<I4s", len(json_bytes), b"JSON") + json_bytes
    out += struct.pack("<I4s", len(blob), b"BIN\x00") + bytes(blob)
    return out


# ---------------------------------------------------------------- drawings --

def node_bounds(node: dict):
    """Axis-aligned extents (ignores rotation except 90-degree swaps for cylinders)."""
    if node["shape"] == "box":
        sx, sy, sz = node["size"]
    else:
        r, h = node["radius"], node["height"]
        sx, sy, sz = 2 * r, h, 2 * r
        rx, _, rz = node.get("rotation_deg", [0, 0, 0])
        if abs(abs(rx) - 90) < 1:
            sy, sz = sz, sy
        elif abs(abs(rz) - 90) < 1:
            sx, sy = sy, sx
    x, y, z = node["position"]
    return (x - sx / 2, y - sy / 2, z - sz / 2), (x + sx / 2, y + sy / 2, z + sz / 2)


def build_drawing(geometry: dict, manifest: dict) -> str:
    scale = 300  # px per metre
    views = [("FRONT VIEW (looking -Z)", 0, 1, False), ("SIDE VIEW (looking -X)", 2, 1, True), ("TOP VIEW", 0, 2, False)]
    bounds = [node_bounds(n) for n in geometry["nodes"]]
    lo = [min(b[0][i] for b in bounds) for i in range(3)]
    hi = [max(b[1][i] for b in bounds) for i in range(3)]
    pad, gap = 40, 60
    widths = [(hi[a] - lo[a]) * scale for _, a, _, _ in views]
    heights = [(hi[b] - lo[b]) * scale for _, _, b, _ in views]
    W = max(int(sum(widths) + gap * 2 + pad * 2 + 140), 780)  # room for dimension labels and title block
    H = int(max(heights) + pad * 2 + 150)
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" font-family="monospace">',
             f'<rect width="{W}" height="{H}" fill="#fff"/>',
             f'<rect x="4" y="4" width="{W-8}" height="{H-8}" fill="none" stroke="#000" stroke-width="2"/>']
    ox = pad
    for (title, a, b, flip), w, h in zip(views, widths, heights):
        oy = pad + max(heights)
        parts.append(f'<text x="{ox}" y="{pad - 12}" font-size="13" font-weight="bold">{title}</text>')
        for n, (bl, bh) in zip(geometry["nodes"], bounds):
            x0 = ox + ((hi[a] - bh[a]) if flip else (bl[a] - lo[a])) * scale
            if b == 1:
                y0 = oy - (bh[b] - lo[b]) * scale
            else:
                y0 = pad + (bl[b] - lo[b]) * scale
            ww, hh = (bh[a] - bl[a]) * scale, (bh[b] - bl[b]) * scale
            fill = "#e8e8e8" if n["material"] == "wood" else "#cfd8e3"
            parts.append(f'<rect x="{x0:.1f}" y="{y0:.1f}" width="{max(ww,1):.1f}" height="{max(hh,1):.1f}" '
                         f'fill="{fill}" fill-opacity="0.5" stroke="#000" stroke-width="0.8"><title>{n["id"]}</title></rect>')
        dim_a = (hi[a] - lo[a]) * 1000
        dim_b = (hi[b] - lo[b]) * 1000
        parts.append(f'<text x="{ox}" y="{oy + 22}" font-size="11">overall {dim_a:.0f} x {dim_b:.0f} mm (nominal)</text>')
        ox += w + gap
    ty = H - 80
    parts.append(f'<line x1="4" y1="{ty}" x2="{W-4}" y2="{ty}" stroke="#000"/>')
    info = [
        f'{manifest["manufacturer"]} - {manifest["product_name"]} ({manifest["product_id"]})',
        f'Engineering revision {manifest["engineering_revision"]} - General arrangement - generated from source/geometry.json',
        'DEMONSTRATION DRAWING - simplified projection, nominal dimensions, not for manufacture.',
    ]
    for i, line in enumerate(info):
        parts.append(f'<text x="16" y="{ty + 22 + i * 18}" font-size="12">{line}</text>')
    parts.append("</svg>")
    return "\n".join(parts)


def main(package_dir: str) -> None:
    pkg = Path(package_dir)
    geometry = json.loads((pkg / "source" / "geometry.json").read_text(encoding="utf-8"))
    manifest = json.loads((pkg / "manifest.json").read_text(encoding="utf-8"))
    glb = build_glb(geometry)
    (pkg / manifest["assembly_file"]).write_bytes(glb)
    (pkg / "drawings").mkdir(exist_ok=True)
    (pkg / "drawings" / "general-arrangement.svg").write_text(build_drawing(geometry, manifest), encoding="utf-8")
    print(f"built {pkg / manifest['assembly_file']} ({len(glb)} bytes, {len(geometry['nodes'])} nodes)")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
