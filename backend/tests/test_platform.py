"""End-to-end tests of package validation and the inspection workflow through the REST API."""
from __future__ import annotations

import io
import json
import os
import shutil
import tempfile
from pathlib import Path

import pytest

TMP = Path(tempfile.mkdtemp(prefix="fep-test-"))
os.environ["DATA_DIR"] = str(TMP / "data")
os.environ["AI_PROVIDER"] = "none"

from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image  # noqa: E402

from app import ai, catalog  # noqa: E402
from app.config import settings  # noqa: E402
from app.main import app  # noqa: E402
from app.packages import validate_package  # noqa: E402

INSPECTOR, SUPERVISOR = "Inspector Ana", "Supervisor Ben"


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def photo(color=(160, 120, 80), size=(800, 600)) -> bytes:
    img = Image.new("RGB", size, color)
    for x in range(0, size[0], 40):  # add edges so the sharpness heuristic has texture
        for y in range(size[1]):
            img.putpixel((x, y), (20, 20, 20))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def items_by_req(state):
    return {i["requirement_id"]: i for i in state["items"]}


# ---------------------------------------------------------------- packages --

@pytest.mark.parametrize("name", ["chair-model-001", "table-model-001", "electrical-panel-icp-001", "utep-conference-chair-rw", "fire-extinguisher-fe-001"])
def test_demo_packages_validate(name):
    report = validate_package(settings.packages_dir / name)
    assert report.ok, report.errors
    assert report.glb_nodes, "GLB should expose named mesh nodes"


def test_validation_catches_broken_references(tmp_path):
    pkg = tmp_path / "broken"
    shutil.copytree(settings.packages_dir / "chair-model-001", pkg)
    comps = json.loads((pkg / "components.json").read_text())
    comps["components"][0]["model_node_ids"] = ["does_not_exist"]
    (pkg / "components.json").write_text(json.dumps(comps))
    proc = json.loads((pkg / "inspection-procedure.json").read_text())
    proc["requirements"][0]["component_id"] = "CHAIR-001-NOPE"
    (pkg / "inspection-procedure.json").write_text(json.dumps(proc))
    (pkg / "bom.csv").write_text((pkg / "bom.csv").read_text().replace("CH-200,Front leg,2", "CH-200,Front leg,3"))
    errors = " | ".join(validate_package(pkg).errors)
    assert "does_not_exist" in errors
    assert "CHAIR-001-NOPE" in errors
    assert "CH-200" in errors


def test_catalog_loaded(client):
    products = client.get("/api/products").json()
    assert {p["id"] for p in products} == {"CHAIR-001@A", "TABLE-001@A", "ICP-001@A", "UTEP-CHAIR-RW@A", "FE-001@A"}
    rev = client.get("/api/revisions/CHAIR-001@A").json()
    assert rev["assembly_url"].endswith("assembly.glb")
    assert client.get(rev["assembly_url"]).status_code == 200
    assert all(c["model_node_ids"] for c in rev["components"])


def test_released_revision_is_immutable(client, tmp_path, monkeypatch):
    pkg = tmp_path / "chair-model-001"
    shutil.copytree(settings.packages_dir / "chair-model-001", pkg)
    assert catalog.load_package(pkg)["status"] == "unchanged"
    proc = json.loads((pkg / "inspection-procedure.json").read_text())
    proc["requirements"][0]["title"] = "Silently changed"
    (pkg / "inspection-procedure.json").write_text(json.dumps(proc))
    with pytest.raises(catalog.PackageConflict):
        catalog.load_package(pkg)


# ---------------------------------------------------------------- workflow --

def test_full_inspection_workflow(client):
    r = client.post("/api/inspections", json={"serial_number": "CHAIR-001-SN-0025", "inspector": INSPECTOR})
    assert r.status_code == 200
    insp_id = r.json()["inspection_id"]
    state = r.json()["state"]
    assert state["inspection"]["product_revision_id"] == "CHAIR-001@A"
    assert set(state["component_status"].values()) == {"not_inspected"}
    items = items_by_req(state)

    # Resuming returns the same open inspection
    again = client.post("/api/inspections", json={"serial_number": "CHAIR-001-SN-0025", "inspector": INSPECTOR})
    assert again.json()["inspection_id"] == insp_id and again.json()["resumed"]

    # Premature submission is blocked server-side
    r = client.post(f"/api/inspections/{insp_id}/submit", json={"actor": INSPECTOR})
    assert r.status_code == 409 and len(r.json()["issues"]) >= 10

    # Photo requirement cannot pass without a photo
    seat = items["SEAT-SURFACE"]
    r = client.post(f"/api/inspections/{insp_id}/items/{seat['id']}/decision",
                    json={"decision": "pass", "actor": INSPECTOR})
    assert r.status_code == 422

    # Manual requirement needs explicit confirmation
    leg = items["LEG-FL-CONDITION"]
    r = client.post(f"/api/inspections/{insp_id}/items/{leg['id']}/decision",
                    json={"decision": "pass", "actor": INSPECTOR})
    assert r.status_code == 422

    # Upload evidence; with AI disabled the assessment is honestly reported as unavailable
    r = client.post(f"/api/inspections/{insp_id}/items/{seat['id']}/evidence",
                    data={"actor": INSPECTOR, "note": "seat top"}, files={"file": ("seat.jpg", photo(), "image/jpeg")})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["assessment"]["status"] == "unavailable"
    assert items_by_req(body["state"])["SEAT-SURFACE"]["status"] == "evidence_submitted"
    assert body["state"]["component_status"]["CHAIR-001-SEAT"] == "pending"
    ev_url = items_by_req(body["state"])["SEAT-SURFACE"]["evidence"][0]["url"]
    assert client.get(ev_url).headers["content-type"] == "image/jpeg"

    # Non-image upload rejected
    r = client.post(f"/api/inspections/{insp_id}/items/{seat['id']}/evidence",
                    data={"actor": INSPECTOR}, files={"file": ("x.txt", b"hello", "text/plain")})
    assert r.status_code == 415

    r = client.post(f"/api/inspections/{insp_id}/items/{seat['id']}/decision",
                    json={"decision": "pass", "actor": INSPECTOR, "observation": "No damage"})
    assert r.status_code == 200
    assert r.json()["component_status"]["CHAIR-001-SEAT"] == "accepted"

    # Fail a requirement -> finding is mandatory and component turns red
    brackets = items["SEAT-BRACKETS-VISUAL"]
    client.post(f"/api/inspections/{insp_id}/items/{brackets['id']}/evidence",
                data={"actor": INSPECTOR}, files={"file": ("b.jpg", photo(), "image/jpeg")})
    r = client.post(f"/api/inspections/{insp_id}/items/{brackets['id']}/decision",
                    json={"decision": "fail", "actor": INSPECTOR})
    assert r.status_code == 422
    r = client.post(f"/api/inspections/{insp_id}/items/{brackets['id']}/decision",
                    json={"decision": "fail", "actor": INSPECTOR,
                          "finding": {"description": "DEMO: rear-left bracket bent", "severity": "medium"}})
    assert r.status_code == 200
    state = r.json()
    assert state["component_status"]["CHAIR-001-SEAT-BRACKETS"] == "finding"
    assert len(state["findings"]) == 1

    # Not applicable needs a justification
    rail = items["RAIL-FRONT-CONDITION"]
    r = client.post(f"/api/inspections/{insp_id}/items/{rail['id']}/decision",
                    json={"decision": "not_applicable", "actor": INSPECTOR})
    assert r.status_code == 422

    # Complete everything else
    for req_id, it in items.items():
        if req_id in ("SEAT-SURFACE", "SEAT-BRACKETS-VISUAL"):
            continue
        etype = it["requirement_snapshot"]["evidence_type"]
        if etype != "manual_confirmation":
            client.post(f"/api/inspections/{insp_id}/items/{it['id']}/evidence",
                        data={"actor": INSPECTOR}, files={"file": ("p.jpg", photo(), "image/jpeg")})
        r = client.post(f"/api/inspections/{insp_id}/items/{it['id']}/decision",
                        json={"decision": "pass", "actor": INSPECTOR, "manual_confirmed": True})
        assert r.status_code == 200, (req_id, r.text)

    state = client.get(f"/api/inspections/{insp_id}").json()
    assert state["readiness"]["ready"], state["readiness"]
    assert state["progress"]["required_done"] == state["progress"]["required_total"]

    r = client.post(f"/api/inspections/{insp_id}/submit", json={"actor": INSPECTOR})
    assert r.status_code == 200 and r.json()["inspection"]["status"] == "submitted"

    # Inspector cannot edit after submission, nor review their own work
    r = client.post(f"/api/inspections/{insp_id}/items/{seat['id']}/decision",
                    json={"decision": "pass", "actor": INSPECTOR})
    assert r.status_code == 409
    r = client.post(f"/api/inspections/{insp_id}/review", json={"reviewer": INSPECTOR, "decision": "approve"})
    assert r.status_code == 403

    # Supervisor requests more evidence on one item -> back to inspector
    r = client.post(f"/api/inspections/{insp_id}/review",
                    json={"reviewer": SUPERVISOR, "decision": "request_evidence", "comments": "Closer seat photo",
                          "item_ids": [seat["id"]]})
    assert r.status_code == 200 and r.json()["inspection"]["status"] == "changes_requested"
    r = client.post(f"/api/inspections/{insp_id}/items/{seat['id']}/decision",
                    json={"decision": "pass", "actor": INSPECTOR, "override_note": "fine"})
    assert r.status_code == 422  # supervisor request cannot be overridden
    client.post(f"/api/inspections/{insp_id}/items/{seat['id']}/evidence",
                data={"actor": INSPECTOR}, files={"file": ("s2.jpg", photo(), "image/jpeg")})
    client.post(f"/api/inspections/{insp_id}/items/{seat['id']}/decision",
                json={"decision": "pass", "actor": INSPECTOR})
    assert client.post(f"/api/inspections/{insp_id}/submit", json={"actor": INSPECTOR}).status_code == 200
    r = client.post(f"/api/inspections/{insp_id}/review",
                    json={"reviewer": SUPERVISOR, "decision": "approve", "comments": "OK"})
    assert r.json()["inspection"]["status"] == "approved"

    passport = client.get("/api/instances/CHAIR-001-SN-0025").json()
    assert passport["inspections"][0]["status"] == "approved"
    assert passport["findings"][0]["status"] == "open"  # approval != corrective action closure

    # Corrective action lifecycle with segregation of duties
    fid = passport["findings"][0]["id"]
    tr = lambda to, actor, **kw: client.post(f"/api/findings/{fid}/transition", json={"to": to, "actor": actor, **kw})
    assert tr("closed", SUPERVISOR).status_code == 409
    assert tr("assigned", SUPERVISOR, assigned_to="Tech Carla").status_code == 200
    assert tr("action_recorded", "Tech Carla").status_code == 422
    assert tr("action_recorded", "Tech Carla", note="Replaced bracket").status_code == 200
    assert tr("awaiting_verification", "Tech Carla").status_code == 200
    assert tr("closed", SUPERVISOR).status_code == 422  # needs after photo
    client.post(f"/api/findings/{fid}/evidence", data={"actor": "Tech Carla", "kind": "corrective_after"},
                files={"file": ("after.jpg", photo(), "image/jpeg")})
    assert tr("closed", "Tech Carla").status_code == 403
    assert tr("closed", SUPERVISOR).status_code == 200


def test_ai_retake_recommendation_holds_item(client, monkeypatch):
    class RetakeProvider:
        name = "test-double"

        def available(self):
            return True, "test double"

        def assess(self, image_jpeg, context):
            assert context["requirement"]["requirement_id"] == "BRACKETS-VISUAL"
            return ai.AssessmentOutcome("test-double", "none", "completed", {
                "summary": "Fastening area not visible", "correct_area_visible": "no", "image_quality": "acceptable",
                "evidence_sufficient": False, "observations": [], "conditions_for_human_review": [],
                "missing_information": ["hanger bolt"], "recommended_action": "retake_photo",
                "retake_guidance": "Photograph from below", "uncertainty": "medium", "limitations": []}, None, 5)

    monkeypatch.setattr(ai, "get_provider", lambda: RetakeProvider())
    r = client.post("/api/inspections", json={"serial_number": "TABLE-001-SN-0107", "inspector": INSPECTOR})
    insp_id = r.json()["inspection_id"]
    item = items_by_req(r.json()["state"])["BRACKETS-VISUAL"]
    r = client.post(f"/api/inspections/{insp_id}/items/{item['id']}/evidence",
                    data={"actor": INSPECTOR}, files={"file": ("b.jpg", photo(), "image/jpeg")})
    state = r.json()["state"]
    assert items_by_req(state)["BRACKETS-VISUAL"]["status"] == "more_evidence_requested"
    assert state["component_status"]["TABLE-001-BRACKETS"] == "pending"
    r = client.post(f"/api/inspections/{insp_id}/items/{item['id']}/decision",
                    json={"decision": "pass", "actor": INSPECTOR})
    assert r.status_code == 422
    r = client.post(f"/api/inspections/{insp_id}/items/{item['id']}/decision",
                    json={"decision": "pass", "actor": INSPECTOR, "override_note": "Bolt visible in second angle"})
    assert r.status_code == 200
    assert any("overridden" in w["reason"] for w in r.json()["readiness"]["warnings"])


def test_health_reports_ai_status(client):
    h = client.get("/api/health").json()
    assert h["ai"]["available"] is False and h["ai"]["provider"] == "none"
