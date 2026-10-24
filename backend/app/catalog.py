"""Turns a validated engineering package into catalog records (product model, revision, components, requirements).

Revisions are immutable: loading a package whose revision already exists with different
content is refused, so historical inspections keep the requirements they were run against.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import db
from .config import settings
from .packages import PackageReport, discover_packages, load_demo_evidence, validate_package


class PackageConflict(Exception):
    pass


class PackageInvalid(Exception):
    def __init__(self, report: PackageReport):
        super().__init__("; ".join(report.errors))
        self.report = report


def revision_id(product_id: str, revision: str) -> str:
    return f"{product_id}@{revision}"


def find_package_dir(package_dir_name: str) -> Path:
    for p in discover_packages(settings.packages_dir):
        if p.name == package_dir_name:
            return p
    raise FileNotFoundError(package_dir_name)


def load_package(package_dir: Path, actor: str = "system") -> dict[str, Any]:
    report = validate_package(package_dir)
    if not report.ok:
        raise PackageInvalid(report)
    m = report.manifest
    rev_id = revision_id(m["product_id"], m["engineering_revision"])
    pkg_id = m.get("package_id") or f"PKG-{m['product_id']}-{m['engineering_revision']}"
    with db.tx() as conn:
        existing = conn.execute(
            "SELECT p.content_hash, p.id FROM product_revisions r JOIN engineering_packages p "
            "ON p.id = r.engineering_package_id WHERE r.id = ?", (rev_id,)).fetchone()
        if existing:
            if existing["content_hash"] == report.content_hash:
                return {"status": "unchanged", "revision_id": rev_id, "report": report.summary()}
            raise PackageConflict(
                f"Revision {m['engineering_revision']} of {m['product_id']} is already loaded with different content. "
                "Released revisions are immutable: publish a new engineering_revision, or reset demo data during development.")
        ts = db.now()
        conn.execute("INSERT OR IGNORE INTO manufacturers VALUES (?,?)",
                     (m.get("manufacturer_id") or m["manufacturer"], m["manufacturer"]))
        conn.execute(
            "INSERT INTO product_models VALUES (?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name, "
            "description=excluded.description",
            (m["product_id"], m.get("manufacturer_id") or m["manufacturer"], m["product_name"], m.get("product_description")))
        conn.execute("INSERT INTO engineering_packages VALUES (?,?,?,?,?,?,?,?,?,?)",
                     (pkg_id, m["product_id"], m["engineering_revision"], m["package_version"], package_dir.name,
                      db.dumps(m), report.content_hash, "loaded", db.dumps(report.summary()), ts))
        proc = {k: v for k, v in report.procedure.items() if k != "requirements"}
        conn.execute("INSERT INTO product_revisions VALUES (?,?,?,?,?,?)",
                     (rev_id, m["product_id"], m["engineering_revision"], pkg_id, db.dumps(proc), ts))
        for i, c in enumerate(report.components):
            conn.execute(
                "INSERT INTO components (product_revision_id, id, parent_component_id, part_number, name, quantity, "
                "category, material, description, model_node_ids, explosion, documents, sort, definition) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (rev_id, c["component_id"], c.get("parent_component_id"), c["part_number"], c["name"],
                 c["quantity"], c.get("category"), c.get("material"), c.get("description"),
                 db.dumps(c.get("model_node_ids") or []),
                 db.dumps(c.get("explosion") or {"direction": [0, 1, 0], "distance": 0}),
                 db.dumps(c.get("documents", [])), i,
                 db.dumps(c)))
        for i, r in enumerate(report.procedure.get("requirements", [])):
            conn.execute("INSERT INTO inspection_requirements VALUES (?,?,?,?,?,?,?,?,?)",
                         (rev_id, r["requirement_id"], r["component_id"], r["title"], r["instructions"],
                          r["evidence_type"], int(r["required"]), db.dumps(r), i))
        db.log_event(conn, "product_revision", rev_id, "package_loaded", actor,
                     {"package_id": pkg_id, "content_hash": report.content_hash, "warnings": report.warnings})
    return {"status": "loaded", "revision_id": rev_id, "report": report.summary()}


def seed_instances() -> None:
    seed_file = Path(__file__).with_name("seed_instances.json")
    instances = json.loads(seed_file.read_text(encoding="utf-8"))
    with db.tx() as conn:
        for inst in instances:
            rev = conn.execute("SELECT id FROM product_revisions WHERE id = ?", (inst["product_revision_id"],)).fetchone()
            if not rev:
                continue
            conn.execute(
                "INSERT OR IGNORE INTO product_instances VALUES (?,?,?,?,?,?)",
                (inst["serial_number"], inst["product_model_id"], inst["product_revision_id"], inst["serial_number"],
                 db.dumps(inst.get("metadata", {})), db.now()))


def bootstrap() -> list[dict[str, Any]]:
    """Load every valid package found on disk (idempotent) and seed demo product instances."""
    results = []
    for pkg in discover_packages(settings.packages_dir):
        try:
            results.append(load_package(pkg))
        except (PackageInvalid, PackageConflict) as exc:
            results.append({"status": "error", "package_dir": pkg.name, "error": str(exc)})
    if settings.seed_instances:
        seed_instances()
    return results


def get_revision(conn, rev_id: str) -> dict[str, Any] | None:
    rev = db.row(conn.execute(
        "SELECT r.*, m.name AS product_name, m.description AS product_description, mf.name AS manufacturer, "
        "p.manifest, p.source_dir, p.content_hash, p.package_version FROM product_revisions r "
        "JOIN product_models m ON m.id = r.product_model_id JOIN manufacturers mf ON mf.id = m.manufacturer_id "
        "JOIN engineering_packages p ON p.id = r.engineering_package_id WHERE r.id = ?", (rev_id,)).fetchone())
    if not rev:
        return None
    comps = db.rows(conn.execute(
        "SELECT * FROM components WHERE product_revision_id = ? ORDER BY sort", (rev_id,)).fetchall())
    for c in comps:
        d = c.pop("definition", None) or {}
        c["specs"] = d.get("specs", [])                    # technical sheet entries
        c["inspection_type"] = d.get("inspection_type")
        c["articulation"] = d.get("articulation")          # e.g. a hinged door
    rev["components"] = comps
    reqs = db.rows(conn.execute(
        "SELECT * FROM inspection_requirements WHERE product_revision_id = ? ORDER BY sort", (rev_id,)).fetchall())
    rev["requirements"] = [_public_requirement(r) for r in reqs]
    base = f"/package-files/{rev['source_dir']}"
    manifest = rev["manifest"]
    # None for assets without a 3D model; the inspection workflow does not depend on it.
    rev["assembly_url"] = f"{base}/{manifest['assembly_file']}" if manifest.get("assembly_file") else None
    rev["documents"] = [{**d, "url": f"{base}/{d['path']}"} for d in manifest.get("documents", [])]
    rev["bom_url"] = f"{base}/{manifest['bom_file']}"
    rev["industry"] = manifest.get("industry") or "General"
    rev["asset_category"] = manifest.get("asset_category")
    rev["demo_evidence"] = demo_evidence(rev["source_dir"])
    return rev


def demo_evidence(source_dir: str) -> list[dict[str, Any]]:
    """Prepared demonstration photos shipped with a package (never mixed with live inspections)."""
    try:
        pkg = find_package_dir(source_dir)
    except FileNotFoundError:
        return []
    out = []
    for e in load_demo_evidence(pkg):
        pre = e.get("precomputed_assessment")
        out.append({
            "id": e["id"], "requirement_id": e["requirement_id"], "caption": e.get("caption"),
            "source": e.get("source"), "url": f"/package-files/{source_dir}/demo-evidence/{e['file']}",
            "has_precomputed_assessment": bool(pre),
            "precomputed_model": (pre or {}).get("model"), "precomputed_at": (pre or {}).get("captured_at"),
        })
    return out


def demo_evidence_entry(source_dir: str, demo_id: str) -> tuple[Path, dict[str, Any]] | None:
    pkg = find_package_dir(source_dir)
    for e in load_demo_evidence(pkg):
        if e.get("id") == demo_id:
            return pkg / "demo-evidence" / e["file"], e
    return None


def _public_requirement(r: dict[str, Any]) -> dict[str, Any]:
    d = r["definition"]
    return {
        "requirement_id": r["id"], "component_id": r["component_id"], "title": r["title"],
        "instructions": r["instructions"], "evidence_type": r["evidence_type"], "required": r["required"],
        "acceptance_criteria": d.get("acceptance_criteria", []), "photo_guidance": d.get("photo_guidance"),
        "inspection_points": d.get("inspection_points", []), "possible_findings": d.get("possible_findings", []),
        "risks": d.get("risks", []), "recommended_actions": d.get("recommended_actions", []),
        "human_review_required": bool(d.get("human_review_required")),
        "visual_limitations": d.get("visual_limitations", []),
    }
