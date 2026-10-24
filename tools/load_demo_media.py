"""Upload the demo 3D models in engineering-packages/ as company media (idempotent).

Each model keeps its full engineering parts list (names, part numbers, specs, explosion vectors, the hinged
door of the electrical panel), so tasks can point at specific parts and the viewer can explode the assembly.
The package's display translations (translations/<lang>.json: product name, part names, descriptions, specs) are
stored with it, so the app shows them in the reader's language.
A model whose title already exists in that company is skipped; pass --replace to upload it again
(also to pick up edited translations).

Usage:
    backend/.venv/bin/python tools/load_demo_media.py [--replace]
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app import db, media  # noqa: E402
from app.config import settings  # noqa: E402
from app.packages import validate_package  # noqa: E402

ASSIGNMENTS = {
    "Border Workplace Inspectors": ["fire-extinguisher-fe-001", "chair-model-001", "utep-conference-chair-rw",
                                    "table-model-001"],
    "Machinnox Electrical": ["electrical-panel-icp-001"],
}
PART_FIELDS = ("name", "part_number", "quantity", "category", "material", "description", "model_node_ids",
               "explosion", "articulation", "specs", "inspection_type")


def parts_of(report) -> list[dict]:
    return [{"id": c["component_id"], **{k: c[k] for k in PART_FIELDS if c.get(k) is not None}}
            for c in report.components]


def translations_of(pkg: Path) -> dict:
    """{lang: {"product": {...}, "components": {...}}} from the package's translation files."""
    out = {}
    for f in sorted((pkg / "translations").glob("*.json")):
        doc = json.loads(f.read_text(encoding="utf-8"))
        out[f.stem] = {"product": doc.get("product") or {}, "components": doc.get("components") or {}}
    return out


def main(replace: bool) -> int:
    for company_name, packages in ASSIGNMENTS.items():
        company = db.first("companies", {"name": company_name})
        if not company:
            print(f"company {company_name!r} not found, skipped (check tools/seed_accounts.py)")
            continue
        existing = {m["title"]: m for m in db.select("media", {"company_id": company["id"], "kind": "model_3d"})}
        for pkg_name in packages:
            report = validate_package(settings.packages_dir / pkg_name)
            if not report.ok:
                print(f"  {pkg_name}: invalid package, skipped: {report.errors[:3]}")
                continue
            title = report.manifest["product_name"]
            if title in existing:
                if not replace:
                    print(f"  {company_name}: {title} already loaded")
                    continue
                media.delete_media(existing[title])
            glb = settings.packages_dir / pkg_name / report.manifest["assembly_file"]
            row = media.create_media(company["id"], glb.name, glb.read_bytes(), title, parts_of(report))
            langs = translations_of(settings.packages_dir / pkg_name)
            if langs:
                db.update("media", {"metadata": {**row["metadata"], "translations": langs}}, {"id": row["id"]})
            print(f"  {company_name}: {title} loaded ({len(row['metadata']['parts'])} parts"
                  f"{', translations: ' + ', '.join(langs) if langs else ''})")
    return 0


if __name__ == "__main__":
    sys.exit(main("--replace" in sys.argv))
