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


def torus_mesh(radius: float, tube: float, radial: int = 48, tubular: int = 12):
    """Ring lying in the local XZ plane (axis = local Y), e.g. a chair foot ring."""
    pos, nrm, idx = [], [], []
    for i in range(radial + 1):
        u = 2 * math.pi * i / radial
        cu, su = math.cos(u), math.sin(u)
        for j in range(tubular + 1):
            v = 2 * math.pi * j / tubular
            cv, sv = math.cos(v), math.sin(v)
            pos.append(((radius + tube * cv) * cu, tube * sv, (radius + tube * cv) * su))
            nrm.append((cv * cu, sv, cv * su))
    row = tubular + 1
    for i in range(radial):
        for j in range(tubular):
            a, b = i * row + j, (i + 1) * row + j
            idx += [a, a + 1, b + 1, a, b + 1, b]
    return pos, nrm, idx


# Shapes below also return UVs (u, v with v=0 at the top of the image, glTF convention), so they can carry textures.

def lathe_mesh(profile: list, segments: int = 36):
    """Surface of revolution around local Y from a (radius, y) profile listed bottom to top."""
    pos, nrm, idx, uv = [], [], [], []
    n = len(profile)
    for i in range(segments + 1):
        a = 2 * math.pi * i / segments
        ca, sa = math.cos(a), math.sin(a)
        for j, (r, y) in enumerate(profile):
            pr, py = profile[max(j - 1, 0)]
            nr, ny = profile[min(j + 1, n - 1)]
            dr, dy = nr - pr, ny - py
            ln = math.hypot(dr, dy) or 1.0
            n_r, n_y = dy / ln, -dr / ln  # outward for a profile walked bottom -> top
            pos.append((r * ca, y, r * sa))
            nrm.append((n_r * ca, n_y, n_r * sa))
            uv.append((i / segments, 1 - j / (n - 1)))
    for i in range(segments):
        for j in range(n - 1):
            a, b = i * n + j, (i + 1) * n + j
            idx += [a, a + 1, b + 1, a, b + 1, b]
    return pos, nrm, idx, uv


def tube_mesh(path: list, radius: float, radial: int = 12):
    """Tube of constant radius swept along a polyline (e.g. a flexible hose). Open ends."""
    pts = [tuple(p) for p in path]
    m = len(pts)

    def sub(p, q): return (p[0] - q[0], p[1] - q[1], p[2] - q[2])
    def dot(p, q): return p[0] * q[0] + p[1] * q[1] + p[2] * q[2]
    def cross(p, q): return (p[1] * q[2] - p[2] * q[1], p[2] * q[0] - p[0] * q[2], p[0] * q[1] - p[1] * q[0])
    def norm(p):
        ln = math.sqrt(dot(p, p)) or 1.0
        return (p[0] / ln, p[1] / ln, p[2] / ln)

    tangents = [norm(sub(pts[min(i + 1, m - 1)], pts[max(i - 1, 0)])) for i in range(m)]
    ref = (0, 0, 1) if abs(tangents[0][2]) < 0.9 else (1, 0, 0)
    normal = norm(cross(tangents[0], ref))
    pos, nrm, idx, uv = [], [], [], []
    for i, (p, t) in enumerate(zip(pts, tangents)):
        normal = norm(sub(normal, tuple(t_ * dot(normal, t) for t_ in t)))  # parallel transport
        binormal = cross(t, normal)
        for j in range(radial + 1):
            v = 2 * math.pi * j / radial
            d = tuple(math.cos(v) * normal[k] + math.sin(v) * binormal[k] for k in range(3))
            pos.append(tuple(p[k] + radius * d[k] for k in range(3)))
            nrm.append(d)
            uv.append((i / (m - 1), j / radial))
    row = radial + 1
    for i in range(m - 1):
        for j in range(radial):
            a, b = i * row + j, (i + 1) * row + j
            idx += [a, a + 1, b + 1, a, b + 1, b]
    return pos, nrm, idx, uv


def arc_panel_mesh(radius: float, height: float, a0_deg: float, a1_deg: float, segments: int = 24):
    """Curved strip on a cylinder of the given radius (axis local Y), e.g. a wrap-around label.
    Angles in the XZ plane: 90 deg faces +Z. The texture reads left-to-right when seen from outside."""
    pos, nrm, idx, uv = [], [], [], []
    hy = height / 2
    for i in range(segments + 1):
        a = math.radians(a0_deg + (a1_deg - a0_deg) * i / segments)
        c, s = math.cos(a), math.sin(a)
        u = 1 - i / segments
        pos += [(radius * c, -hy, radius * s), (radius * c, hy, radius * s)]
        nrm += [(c, 0, s), (c, 0, s)]
        uv += [(u, 1.0), (u, 0.0)]
    for i in range(segments):
        a, b = 2 * i, 2 * i + 2
        idx += [a, a + 1, b + 1, a, b + 1, b]
    return pos, nrm, idx, uv


def disc_mesh(radius: float, segments: int = 36):
    """Flat disc in the local XY plane facing +Z (e.g. a gauge face)."""
    pos, nrm, idx, uv = [(0, 0, 0)], [(0, 0, 1)], [], [(0.5, 0.5)]
    for i in range(segments + 1):
        a = 2 * math.pi * i / segments
        x, y = radius * math.cos(a), radius * math.sin(a)
        pos.append((x, y, 0))
        nrm.append((0, 0, 1))
        uv.append((0.5 + 0.5 * x / radius, 0.5 - 0.5 * y / radius))
    for i in range(segments):
        idx += [0, i + 1, i + 2]
    return pos, nrm, idx, uv


def plane_mesh(width: float, height: float):
    """Double-sided rectangle in the local XY plane (front faces +Z), e.g. a hanging tag."""
    hx, hy = width / 2, height / 2
    pos = [(-hx, -hy, 0), (hx, -hy, 0), (hx, hy, 0), (-hx, hy, 0),
           (hx, -hy, 0), (-hx, -hy, 0), (-hx, hy, 0), (hx, hy, 0)]
    nrm = [(0, 0, 1)] * 4 + [(0, 0, -1)] * 4
    uv = [(0, 1), (1, 1), (1, 0), (0, 0)] * 2
    idx = [0, 1, 2, 0, 2, 3, 4, 5, 6, 4, 6, 7]
    return pos, nrm, idx, uv


def make_mesh(node: dict):
    """(positions, normals, indices, uvs or None) for a geometry node."""
    shape = node["shape"]
    if shape == "box":
        return (*box_mesh(*node["size"]), None)
    if shape == "cylinder":
        return (*cylinder_mesh(node["radius"], node["height"]), None)
    if shape == "torus":
        return (*torus_mesh(node["radius"], node["tube"]), None)
    if shape == "lathe":
        return lathe_mesh(node["profile"], node.get("segments", 36))
    if shape == "tube":
        return tube_mesh(node["path"], node["radius"], node.get("radial", 12))
    if shape == "arc_panel":
        return arc_panel_mesh(node["radius"], node["height"], node["a0_deg"], node["a1_deg"], node.get("segments", 24))
    if shape == "disc":
        return disc_mesh(node["radius"], node.get("segments", 36))
    if shape == "plane":
        return plane_mesh(*node["size"])
    raise ValueError(f"unsupported shape {shape} on {node['id']}")


def check_winding(nid: str, pos, nrm, idx) -> None:
    """Every triangle must face the same way as its vertex normals (outward), or it renders inside-out."""
    bad = total = 0
    for k in range(0, len(idx), 3):
        a, b, c = (pos[i] for i in idx[k:k + 3])
        e1 = [b[i] - a[i] for i in range(3)]
        e2 = [c[i] - a[i] for i in range(3)]
        fn = (e1[1] * e2[2] - e1[2] * e2[1], e1[2] * e2[0] - e1[0] * e2[2], e1[0] * e2[1] - e1[1] * e2[0])
        if sum(v * v for v in fn) < 1e-18:
            continue  # degenerate (e.g. lathe pole)
        vn = [sum(nrm[i][j] for i in idx[k:k + 3]) for j in range(3)]
        total += 1
        bad += sum(fn[j] * vn[j] for j in range(3)) <= 0
    if total and bad / total > 0.02:
        raise ValueError(f"{nid}: {bad}/{total} triangles face inward")


def rotate(v, q):
    """Rotate vector v by quaternion q = [x, y, z, w]."""
    x, y, z, w = q
    tx, ty, tz = 2 * (y * v[2] - z * v[1]), 2 * (z * v[0] - x * v[2]), 2 * (x * v[1] - y * v[0])
    return (v[0] + w * tx + y * tz - z * ty, v[1] + w * ty + z * tx - x * tz, v[2] + w * tz + x * ty - y * tx)


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

def build_glb(geometry: dict, base_dir: Path | None = None) -> bytes:
    """base_dir: folder that material "texture" paths are relative to (the package's source/ folder)."""
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
    blob = bytearray()

    def add_view(data: bytes, target: int | None) -> int:
        while len(blob) % 4:
            blob.append(0)
        offset = len(blob)
        blob.extend(data)
        view = {"buffer": 0, "byteOffset": offset, "byteLength": len(data)}
        if target is not None:
            view["target"] = target
        gltf["bufferViews"].append(view)
        return len(gltf["bufferViews"]) - 1

    textured: set[str] = set()
    for name in mat_names:
        m = materials_src[name]
        pbr = {
            "baseColorFactor": list(m["color"]) + [1.0],
            "metallicFactor": m.get("metallic", 0.0),
            "roughnessFactor": m.get("roughness", 0.8),
        }
        if m.get("texture"):
            # Embedded PNG (no extra request on mobile). Only materials that use one get UVs on their meshes.
            png = (Path(base_dir or ".") / m["texture"]).read_bytes()
            for key in ("images", "textures", "samplers"):
                gltf.setdefault(key, [])
            if not gltf["samplers"]:
                gltf["samplers"].append({"magFilter": 9729, "minFilter": 9987, "wrapS": 33071, "wrapT": 33071})
            gltf["images"].append({"bufferView": add_view(png, None), "mimeType": "image/png", "name": name})
            gltf["textures"].append({"sampler": 0, "source": len(gltf["images"]) - 1})
            pbr["baseColorTexture"] = {"index": len(gltf["textures"]) - 1}
            textured.add(name)
        gltf["materials"].append({"name": name, "pbrMetallicRoughness": pbr})

    seen = set()
    for node in geometry["nodes"]:
        nid = node["id"]
        if nid in seen:
            raise ValueError(f"duplicate node id {nid}")
        seen.add(nid)
        pos, nrm, idx, uv = make_mesh(node)
        check_winding(nid, pos, nrm, idx)
        if node["material"] in textured and uv is None:
            raise ValueError(f"{nid}: shape {node['shape']} cannot carry the texture of material {node['material']}")

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
        attributes = {"POSITION": a0, "NORMAL": a0 + 1}
        if node["material"] in textured:
            uv_view = add_view(b"".join(struct.pack("<2f", *t) for t in uv), 34962)
            acc.append({"bufferView": uv_view, "componentType": 5126, "count": len(uv), "type": "VEC2"})
            attributes["TEXCOORD_0"] = len(acc) - 1
        gltf["meshes"].append({
            "name": f"{nid}_mesh",
            "primitives": [{"attributes": attributes, "indices": a0 + 2,
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
    if node["shape"] not in ("box", "torus", "cylinder"):
        # Newer shapes: exact bounds from the transformed mesh vertices.
        q = euler_deg_to_quat(*node.get("rotation_deg", [0, 0, 0]))
        pts = [rotate(p, q) for p in make_mesh(node)[0]]
        x, y, z = node["position"]
        lo = tuple(min(p[i] for p in pts) + (x, y, z)[i] for i in range(3))
        hi = tuple(max(p[i] for p in pts) + (x, y, z)[i] for i in range(3))
        return lo, hi
    if node["shape"] == "box":
        sx, sy, sz = node["size"]
    elif node["shape"] == "torus":
        d = 2 * (node["radius"] + node["tube"])
        sx, sy, sz = d, 2 * node["tube"], d
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
    glb = build_glb(geometry, pkg / "source")
    (pkg / manifest["assembly_file"]).write_bytes(glb)
    (pkg / "drawings").mkdir(exist_ok=True)
    (pkg / "drawings" / "general-arrangement.svg").write_text(build_drawing(geometry, manifest), encoding="utf-8")
    print(f"built {pkg / manifest['assembly_file']} ({len(glb)} bytes, {len(geometry['nodes'])} nodes)")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
