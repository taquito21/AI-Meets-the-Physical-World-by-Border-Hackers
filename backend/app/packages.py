"""Engineering package loading and validation.

Every product source (hand-prepared package, future manufacturer upload, future CAD
conversion pipeline) must produce this same validated representation before the
inspection engine sees it. See docs/ENGINEERING_PACKAGE_SPEC.md.
"""
from __future__ import annotations

import csv
import hashlib
import json
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

EVIDENCE_TYPES = {"photo", "manual_confirmation", "photo_and_manual_confirmation"}
REQUIRED_MANIFEST_FIELDS = [
    "package_version", "manufacturer", "product_id", "product_name", "engineering_revision",
    "components_file", "bom_file", "inspection_procedure_file",
]


@dataclass
class PackageReport:
    package_dir: str
    manifest: dict[str, Any] = field(default_factory=dict)
    components: list[dict[str, Any]] = field(default_factory=list)
    procedure: dict[str, Any] = field(default_factory=dict)
    bom: list[dict[str, Any]] = field(default_factory=list)
    glb_nodes: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    content_hash: str = ""

    @property
    def ok(self) -> bool:
        return not self.errors

    def summary(self) -> dict[str, Any]:
        reqs = self.procedure.get("requirements", [])
        return {
            "package_dir": self.package_dir,
            "package_id": self.manifest.get("package_id"),
            "product_id": self.manifest.get("product_id"),
            "product_name": self.manifest.get("product_name"),
            "manufacturer": self.manifest.get("manufacturer"),
            "engineering_revision": self.manifest.get("engineering_revision"),
            "industry": self.manifest.get("industry") or "General",
            "asset_category": self.manifest.get("asset_category"),
            "demonstration_package": bool(self.manifest.get("demonstration_package")),
            "ok": self.ok,
            "errors": self.errors,
            "warnings": self.warnings,
            "content_hash": self.content_hash,
            "stats": {
                "components": len(self.components),
                "geometry_nodes": len(self.glb_nodes),
                "bom_lines": len(self.bom),
                "requirements": len(reqs),
                "required_requirements": sum(1 for r in reqs if r.get("required")),
            },
            "files": {
                "assembly": self.manifest.get("assembly_file"),
                "components": self.manifest.get("components_file"),
                "bom": self.manifest.get("bom_file"),
                "inspection_procedure": self.manifest.get("inspection_procedure_file"),
                "documents": [d.get("path") for d in self.manifest.get("documents", [])],
            },
        }


def read_glb_node_names(path: Path) -> list[str]:
    """Return the names of glTF nodes that carry a mesh (selectable geometry)."""
    data = path.read_bytes()
    magic, version, _length = struct.unpack_from("<4sII", data, 0)
    if magic != b"glTF" or version != 2:
        raise ValueError("not a glTF 2.0 binary file")
    chunk_len, chunk_type = struct.unpack_from("<I4s", data, 12)
    if chunk_type != b"JSON":
        raise ValueError("first GLB chunk is not JSON")
    gltf = json.loads(data[20:20 + chunk_len])
    return [n["name"] for n in gltf.get("nodes", []) if "mesh" in n and n.get("name")]


def _hash_dir(pkg: Path) -> str:
    h = hashlib.sha256()
    for f in sorted(p for p in pkg.rglob("*") if p.is_file()):
        rel = f.relative_to(pkg).as_posix()
        if rel.startswith(("reference-images/", "demo-evidence/")):
            continue  # reference/demo photos may be added without changing the engineering content
        h.update(rel.encode())
        h.update(f.read_bytes())
    return h.hexdigest()


def _load_json(pkg: Path, name: str | None, report: PackageReport) -> Any:
    if not name:
        return None
    path = pkg / name
    if not path.exists():
        report.errors.append(f"missing file: {name}")
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        report.errors.append(f"{name}: invalid JSON ({exc})")
        return None


def validate_package(package_dir: Path) -> PackageReport:
    pkg = Path(package_dir)
    report = PackageReport(package_dir=pkg.name)
    manifest = _load_json(pkg, "manifest.json", report)
    if not isinstance(manifest, dict):
        report.errors.append("manifest.json missing or not an object")
        return report
    report.manifest = manifest
    for f in REQUIRED_MANIFEST_FIELDS:
        if not manifest.get(f):
            report.errors.append(f"manifest: missing field '{f}'")
    if report.errors:
        return report
    product_id, revision = manifest["product_id"], manifest["engineering_revision"]
    if not manifest.get("industry"):
        report.warnings.append("manifest: no 'industry' (shown as 'General')")

    # --- geometry (optional: assets without a 3D model are inspected from the component list)
    has_3d = bool(manifest.get("assembly_file"))
    glb_path = pkg / manifest["assembly_file"] if has_3d else None
    if glb_path is None:
        pass
    elif not glb_path.exists():
        report.errors.append(f"missing assembly file: {manifest['assembly_file']}")
    else:
        try:
            report.glb_nodes = read_glb_node_names(glb_path)
        except Exception as exc:  # noqa: BLE001 - surface any parse failure as a validation error
            report.errors.append(f"assembly file unreadable: {exc}")

    # --- components
    comp_doc = _load_json(pkg, manifest["components_file"], report) or {}
    components = comp_doc.get("components", []) if isinstance(comp_doc, dict) else []
    report.components = components
    if comp_doc and (comp_doc.get("product_id") != product_id or comp_doc.get("engineering_revision") != revision):
        report.errors.append("components file product_id/engineering_revision does not match manifest")
    doc_ids = {d.get("id") for d in manifest.get("documents", [])}
    for d in manifest.get("documents", []):
        if not (pkg / d.get("path", "")).exists():
            report.errors.append(f"document {d.get('id')}: file not found ({d.get('path')})")

    seen_ids: set[str] = set()
    node_owner: dict[str, str] = {}
    glb_set = set(report.glb_nodes)
    for c in components:
        cid = c.get("component_id")
        if not cid:
            report.errors.append("component without component_id")
            continue
        if cid in seen_ids:
            report.errors.append(f"duplicate component_id {cid}")
        seen_ids.add(cid)
        if not cid.startswith(product_id + "-"):
            report.warnings.append(f"{cid}: component_id does not start with product id {product_id}")
        if not c.get("part_number"):
            report.errors.append(f"{cid}: missing part_number")
        qty = c.get("quantity")
        if not isinstance(qty, int) or qty < 1:
            report.errors.append(f"{cid}: quantity must be a positive integer")
        nodes = c.get("model_node_ids") or []
        if has_3d and not nodes:
            report.errors.append(f"{cid}: no model_node_ids")
        if not has_3d and nodes:
            report.errors.append(f"{cid}: model_node_ids given but the package has no assembly_file")
        for n in nodes:
            if report.glb_nodes and n not in glb_set:
                report.errors.append(f"{cid}: model node '{n}' not found in {manifest['assembly_file']}")
            if n in node_owner:
                report.errors.append(f"model node '{n}' assigned to both {node_owner[n]} and {cid}")
            node_owner[n] = cid
        # A single part may be modelled with several nodes; a set of n identical parts should have n nodes.
        if isinstance(qty, int) and qty > 1 and nodes and qty != len(nodes):
            report.warnings.append(f"{cid}: quantity {qty} but {len(nodes)} geometry nodes")
        for spec in c.get("specs", []) or []:
            if not isinstance(spec, dict) or not spec.get("label") or "value" not in spec:
                report.errors.append(f"{cid}: each spec needs 'label' and 'value'")
        art = c.get("articulation")
        if art is not None:
            ok = (isinstance(art, dict) and art.get("type") == "hinge"
                  and all(isinstance(art.get(k), list) and len(art[k]) == 3 for k in ("pivot", "axis"))
                  and any(art["axis"]) and isinstance(art.get("angle_deg"), (int, float)))
            if not ok:
                report.errors.append(f"{cid}: articulation must be {{type: hinge, pivot[3], axis[3], angle_deg}}")
        exp = c.get("explosion")
        if has_3d or exp is not None:
            exp = exp or {}
            direction = exp.get("direction")
            if not (isinstance(direction, list) and len(direction) == 3 and any(direction)):
                report.errors.append(f"{cid}: explosion.direction must be a non-zero 3-vector")
            if not isinstance(exp.get("distance"), (int, float)) or exp.get("distance") < 0:
                report.errors.append(f"{cid}: explosion.distance must be >= 0")
        for doc in c.get("documents", []):
            if doc not in doc_ids:
                report.errors.append(f"{cid}: references unknown document {doc}")
    for n in report.glb_nodes:
        if n not in node_owner:
            report.warnings.append(f"geometry node '{n}' is not mapped to any component")

    # --- BOM
    bom_path = pkg / manifest["bom_file"]
    if not bom_path.exists():
        report.errors.append(f"missing BOM file: {manifest['bom_file']}")
    else:
        with bom_path.open(newline="", encoding="utf-8") as f:
            report.bom = list(csv.DictReader(f))
        bom_qty: dict[str, int] = {}
        for line in report.bom:
            pn = (line.get("part_number") or "").strip()
            try:
                bom_qty[pn] = bom_qty.get(pn, 0) + int(line.get("quantity") or 0)
            except ValueError:
                report.errors.append(f"BOM {pn}: quantity is not an integer")
        comp_qty: dict[str, int] = {}
        for c in components:
            if isinstance(c.get("quantity"), int):
                comp_qty[c.get("part_number", "")] = comp_qty.get(c.get("part_number", ""), 0) + c["quantity"]
        for pn, q in bom_qty.items():
            if pn not in comp_qty:
                report.errors.append(f"BOM part {pn} has no component in {manifest['components_file']}")
            elif comp_qty[pn] != q:
                report.errors.append(f"BOM part {pn}: BOM quantity {q} != component quantity {comp_qty[pn]}")
        for pn in comp_qty:
            if pn not in bom_qty:
                report.errors.append(f"component part {pn} missing from BOM")

    # --- inspection procedure
    proc = _load_json(pkg, manifest["inspection_procedure_file"], report) or {}
    report.procedure = proc if isinstance(proc, dict) else {}
    if proc and (proc.get("product_id") != product_id or proc.get("engineering_revision") != revision):
        report.errors.append("inspection procedure product_id/engineering_revision does not match manifest")
    req_ids: set[str] = set()
    covered: set[str] = set()
    for r in report.procedure.get("requirements", []):
        rid = r.get("requirement_id")
        if not rid:
            report.errors.append("requirement without requirement_id")
            continue
        if rid in req_ids:
            report.errors.append(f"duplicate requirement_id {rid}")
        req_ids.add(rid)
        if r.get("component_id") not in seen_ids:
            report.errors.append(f"requirement {rid}: unknown component {r.get('component_id')}")
        covered.add(r.get("component_id"))
        if r.get("evidence_type") not in EVIDENCE_TYPES:
            report.errors.append(f"requirement {rid}: invalid evidence_type {r.get('evidence_type')}")
        if not isinstance(r.get("required"), bool):
            report.errors.append(f"requirement {rid}: 'required' must be true/false")
        if not r.get("title") or not r.get("instructions"):
            report.errors.append(f"requirement {rid}: title and instructions are required")
        for key in ("acceptance_criteria", "inspection_points", "possible_findings", "risks",
                    "recommended_actions", "visual_limitations"):
            if key in r and not (isinstance(r[key], list) and all(isinstance(x, str) for x in r[key])):
                report.errors.append(f"requirement {rid}: '{key}' must be a list of strings")
    for cid in seen_ids - covered:
        report.warnings.append(f"{cid}: no inspection requirements defined")

    # --- optional demo evidence (prepared, clearly labelled photos for demo-mode inspections)
    for entry in load_demo_evidence(pkg):
        if entry.get("requirement_id") not in req_ids:
            report.errors.append(f"demo evidence {entry.get('id')}: unknown requirement {entry.get('requirement_id')}")
        if not (pkg / "demo-evidence" / str(entry.get("file", ""))).is_file():
            report.errors.append(f"demo evidence {entry.get('id')}: file not found ({entry.get('file')})")
        pre = entry.get("precomputed_assessment")
        if pre is not None:
            from .ai import AssessmentResult  # local import: keeps package validation light for tools
            try:
                AssessmentResult.model_validate(pre.get("result"))
                if not pre.get("model") or not pre.get("captured_at"):
                    raise ValueError("model and captured_at are required")
            except Exception as exc:  # noqa: BLE001 - report any schema problem as a validation error
                report.errors.append(f"demo evidence {entry.get('id')}: invalid precomputed assessment ({str(exc)[:120]})")

    report.content_hash = _hash_dir(pkg)
    return report


def load_demo_evidence(pkg: Path) -> list[dict[str, Any]]:
    path = pkg / "demo-evidence" / "demo-evidence.json"
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("items", []) if isinstance(data, dict) else []


def discover_packages(packages_dir: Path) -> list[Path]:
    if not packages_dir.exists():
        return []
    return sorted(p for p in packages_dir.iterdir() if (p / "manifest.json").exists())
