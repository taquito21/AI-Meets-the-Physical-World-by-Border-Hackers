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


def _catalog_rows(report: PackageReport, rev_id: str) -> tuple[list[dict], list[dict]]:
    comps = [{
        "product_revision_id": rev_id, "id": c["component_id"], "parent_component_id": c.get("parent_component_id"),
        "part_number": c["part_number"], "name": c["name"], "quantity": c["quantity"], "category": c.get("category"),
        "material": c.get("material"), "description": c.get("description"),
        "model_node_ids": c.get("model_node_ids") or [],
        "explosion": c.get("explosion") or {"direction": [0, 1, 0], "distance": 0},
        "documents": c.get("documents", []), "sort": i, "definition": c}
        for i, c in enumerate(report.components)]
    reqs = [{
        "product_revision_id": rev_id, "id": r["requirement_id"], "component_id": r["component_id"],
        "title": r["title"], "instructions": r["instructions"], "evidence_type": r["evidence_type"],
        "required": bool(r["required"]), "definition": r, "sort": i}
        for i, r in enumerate(report.procedure.get("requirements", []))]
    return comps, reqs


def load_package(package_dir: Path, actor: str = "system", loaded: dict[str, Any] | None = None) -> dict[str, Any]:
    """Import a validated package. `loaded` (from bootstrap) avoids re-querying what is already in the catalog.

    The REST API has no multi-statement transaction, so every insert is idempotent (ignore duplicates) and a
    revision whose components or requirements are incomplete (an import interrupted mid-way) is completed."""
    report = validate_package(package_dir)
    if not report.ok:
        raise PackageInvalid(report)
    m = report.manifest
    rev_id = revision_id(m["product_id"], m["engineering_revision"])
    pkg_id = m.get("package_id") or f"PKG-{m['product_id']}-{m['engineering_revision']}"
    comps, reqs = _catalog_rows(report, rev_id)
    if loaded is None:
        loaded = _loaded_state([rev_id])
    existing_hash = loaded["hashes"].get(rev_id)
    if existing_hash and existing_hash != report.content_hash:
        raise PackageConflict(
            f"Revision {m['engineering_revision']} of {m['product_id']} is already loaded with different content. "
            "Released revisions are immutable: publish a new engineering_revision, or reset demo data during development.")
    complete = (existing_hash and loaded["components"].get(rev_id, 0) == len(comps)
                and loaded["requirements"].get(rev_id, 0) == len(reqs))
    if complete:
        return {"status": "unchanged", "revision_id": rev_id, "report": report.summary()}

    ts = db.now()
    mfr_id = m.get("manufacturer_id") or m["manufacturer"]
    db.insert("manufacturers", {"id": mfr_id, "name": m["manufacturer"]}, ignore_duplicates_on="id")
    db.upsert("product_models", {"id": m["product_id"], "manufacturer_id": mfr_id, "name": m["product_name"],
                                 "description": m.get("product_description")}, on_conflict="id")
    db.insert("engineering_packages", {
        "id": pkg_id, "product_model_id": m["product_id"], "revision": m["engineering_revision"],
        "package_version": m["package_version"], "source_dir": package_dir.name, "manifest": m,
        "content_hash": report.content_hash, "status": "loaded", "validation": report.summary(), "created_at": ts},
        ignore_duplicates_on="id")
    proc = {k: v for k, v in report.procedure.items() if k != "requirements"}
    db.insert("product_revisions", {"id": rev_id, "product_model_id": m["product_id"],
                                    "revision": m["engineering_revision"], "engineering_package_id": pkg_id,
                                    "procedure": proc, "created_at": ts}, ignore_duplicates_on="id")
    db.insert("components", comps, ignore_duplicates_on="product_revision_id,id")
    db.insert("inspection_requirements", reqs, ignore_duplicates_on="product_revision_id,id")
    if existing_hash:
        db.log_event("product_revision", rev_id, "package_import_completed", actor, {"package_id": pkg_id})
        return {"status": "repaired", "revision_id": rev_id, "report": report.summary()}
    db.log_event("product_revision", rev_id, "package_loaded", actor,
                 {"package_id": pkg_id, "content_hash": report.content_hash, "warnings": report.warnings})
    return {"status": "loaded", "revision_id": rev_id, "report": report.summary()}


def _loaded_state(rev_ids: list[str] | None = None) -> dict[str, Any]:
    """Content hash per loaded revision and how many components/requirements it has (3 queries in total)."""
    where = {"id": rev_ids} if rev_ids is not None else None
    revs = db.select("product_revisions", where, columns="id,engineering_package_id")
    pkgs = {p["id"]: p["content_hash"] for p in db.select(
        "engineering_packages", {"id": [r["engineering_package_id"] for r in revs]}, columns="id,content_hash")}
    by_rev = {"product_revision_id": [r["id"] for r in revs]}

    def per_rev(table: str) -> dict[str, int]:
        out: dict[str, int] = {}
        for row in db.select(table, by_rev, columns="product_revision_id"):
            out[row["product_revision_id"]] = out.get(row["product_revision_id"], 0) + 1
        return out

    return {"hashes": {r["id"]: pkgs.get(r["engineering_package_id"]) for r in revs},
            "components": per_rev("components"), "requirements": per_rev("inspection_requirements")}


def seed_instances() -> None:
    seed_file = Path(__file__).with_name("seed_instances.json")
    instances = json.loads(seed_file.read_text(encoding="utf-8"))
    known = {r["id"] for r in db.select("product_revisions", {"id": [i["product_revision_id"] for i in instances]},
                                        columns="id")}
    db.insert("product_instances", [{
        "id": inst["serial_number"], "product_model_id": inst["product_model_id"],
        "product_revision_id": inst["product_revision_id"], "serial_number": inst["serial_number"],
        "metadata": inst.get("metadata", {}), "created_at": db.now()}
        for inst in instances if inst["product_revision_id"] in known], ignore_duplicates_on="id")


def bootstrap() -> list[dict[str, Any]]:
    """Load every valid package found on disk (idempotent) and seed demo product instances."""
    results = []
    loaded = _loaded_state()
    for pkg in discover_packages(settings.packages_dir):
        try:
            results.append(load_package(pkg, loaded=loaded))
        except (PackageInvalid, PackageConflict) as exc:
            results.append({"status": "error", "package_dir": pkg.name, "error": str(exc)})
    if settings.seed_instances:
        seed_instances()
    return results


def get_revision(rev_id: str) -> dict[str, Any] | None:
    rev = db.first("product_revisions", {"id": rev_id})
    if not rev:
        return None
    model = db.first("product_models", {"id": rev["product_model_id"]})
    mfr = db.first("manufacturers", {"id": model["manufacturer_id"]})
    pkg = db.first("engineering_packages", {"id": rev["engineering_package_id"]},
                   columns="manifest,source_dir,content_hash,package_version")
    rev.update(product_name=model["name"], product_description=model["description"], manufacturer=mfr["name"], **pkg)
    comps = db.select("components", {"product_revision_id": rev_id}, order="sort")
    for c in comps:
        d = c.pop("definition", None) or {}
        c["specs"] = d.get("specs", [])                    # technical sheet entries
        c["inspection_type"] = d.get("inspection_type")
        c["articulation"] = d.get("articulation")          # e.g. a hinged door
    rev["components"] = comps
    reqs = db.select("inspection_requirements", {"product_revision_id": rev_id}, order="sort")
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


def revision_index() -> dict[str, dict[str, Any]]:
    """Display fields for every revision (product, manufacturer, industry), joined in Python: 4 queries."""
    models = {m["id"]: m for m in db.select("product_models")}
    mfrs = {m["id"]: m["name"] for m in db.select("manufacturers")}
    pkgs = {p["id"]: p for p in db.select("engineering_packages", columns="id,source_dir,manifest")}
    out = {}
    for r in db.select("product_revisions", columns="id,revision,product_model_id,engineering_package_id"):
        model, pkg = models.get(r["product_model_id"], {}), pkgs.get(r["engineering_package_id"], {})
        manifest = pkg.get("manifest") or {}
        out[r["id"]] = {
            "id": r["id"], "revision": r["revision"], "product_id": r["product_model_id"],
            "product_name": model.get("name"), "description": model.get("description"),
            "manufacturer": mfrs.get(model.get("manufacturer_id")), "package_id": r["engineering_package_id"],
            "source_dir": pkg.get("source_dir"), "manifest": manifest,
            "industry": manifest.get("industry") or "General", "asset_category": manifest.get("asset_category")}
    return out


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
