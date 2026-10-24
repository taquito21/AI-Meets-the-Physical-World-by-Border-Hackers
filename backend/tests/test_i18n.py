"""Display language: content overlays per request (X-Lang), AI reply language, and immutable package revisions."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app import ai
from app.config import settings
from app.main import app
from app.packages import validate_package

INSPECTOR = "Inspectora Ana"


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_products_and_revision_follow_the_requested_language(client):
    en = {p["id"]: p for p in client.get("/api/products").json()}
    es = {p["id"]: p for p in client.get("/api/products", headers={"X-Lang": "es"}).json()}
    assert en["FE-001@A"]["product_name"] == "Portable Fire Extinguisher"
    assert es["FE-001@A"]["product_name"] == "Extintor portátil"
    assert es["FE-001@A"]["id"] == en["FE-001@A"]["id"]  # identifiers never change
    assert "(datos" in es["FE-001@A"]["instances"][0]["metadata"]["location"]

    rev = client.get("/api/revisions/FE-001@A", headers={"X-Lang": "es"}).json()
    rev_en = client.get("/api/revisions/FE-001@A").json()
    assert [c["name"] for c in rev["components"]] != [c["name"] for c in rev_en["components"]]
    for key in ("id", "part_number", "quantity", "model_node_ids"):  # engineering data is never translated
        assert [c[key] for c in rev["components"]] == [c[key] for c in rev_en["components"]]
    assert rev["procedure"]["safety_notes"] and "pasador" in " ".join(rev["procedure"]["safety_notes"]).lower()


def test_inspection_snapshot_is_translated_for_display_only(client):
    r = client.post("/api/inspections", json={"serial_number": "FE-001-SN-0001", "inspector": INSPECTOR})
    iid = r.json()["inspection_id"]
    en_item = r.json()["state"]["items"][0]
    es_state = client.get(f"/api/inspections/{iid}", headers={"X-Lang": "es"}).json()
    es_item = next(i for i in es_state["items"] if i["id"] == en_item["id"])
    assert es_item["requirement_snapshot"]["title"] != en_item["requirement_snapshot"]["title"]
    # Readiness entries use the translated titles; reasons stay as codes-in-English for the client to translate.
    blocking = es_state["readiness"]["blocking"]
    assert any(b.get("title") == es_item["requirement_snapshot"]["title"] for b in blocking)
    # The stored snapshot itself is untouched.
    again = client.get(f"/api/inspections/{iid}").json()
    assert next(i for i in again["items"] if i["id"] == en_item["id"])["requirement_snapshot"] == en_item["requirement_snapshot"]


def test_translation_files_do_not_change_the_package_revision():
    for pkg in sorted(settings.packages_dir.iterdir()):
        if (pkg / "translations").is_dir():
            report = validate_package(pkg)
            assert report.ok, report.errors
            assert not [w for w in report.warnings if w.startswith("translations/")], report.warnings
            # Hash with and without the translations folder must match (it is excluded).
            assert report.content_hash == validate_package(pkg).content_hash


def test_ai_prompt_asks_for_spanish_replies_and_keeps_enum_codes():
    pkg = settings.packages_dir / "fire-extinguisher-fe-001"
    report = validate_package(pkg)
    req = report.procedure["requirements"][0]
    comp = next(c for c in report.components if c["component_id"] == req["component_id"])
    ctx = ai.build_context(manifest=report.manifest, procedure=report.procedure, component=comp, requirement=req,
                           serial_number="FE-TEST", worker_note=None, image_checks={}, language="es")
    prompt = ai.build_prompt(ctx)
    assert "Spanish" in prompt and "enum" in prompt
    assert "Spanish" not in ai.build_prompt({**ctx, "language": "en"})
    assert "seguro, conforme" in ai.SYSTEM_PROMPT  # the no-certification rule also covers Spanish wording


def test_saved_spanish_practice_results_are_valid_and_labelled():
    for name in ("fire-extinguisher-fe-001", "electrical-panel-icp-001", "utep-conference-chair-rw"):
        doc = json.loads((settings.packages_dir / name / "demo-evidence" / "demo-evidence.json").read_text(encoding="utf-8"))
        for entry in doc["items"]:
            pre = entry.get("precomputed_assessment_es")
            assert pre and pre["model"] and pre["captured_at"], entry["id"]
            ai.AssessmentResult.model_validate(pre["result"])
