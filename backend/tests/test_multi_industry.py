"""Multi-industry extension: electrical panel asset, live vs demo inspections, shared dashboard."""
from __future__ import annotations

import io
import json
import shutil

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app import ai, catalog
from app.config import settings
from app.main import app
from app.packages import validate_package

INSPECTOR = "Inspector Ana"


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def photo() -> bytes:
    img = Image.new("RGB", (800, 600), (120, 120, 125))
    for x in range(0, 800, 40):
        for y in range(600):
            img.putpixel((x, y), (20, 20, 20))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def test_electrical_package_is_valid_and_rich():
    r = validate_package(settings.packages_dir / "electrical-panel-icp-001")
    assert r.ok, r.errors
    assert r.manifest["industry"] == "Electrical"
    door = next(c for c in r.components if c["component_id"] == "ICP-001-DOOR")
    assert door["articulation"]["type"] == "hinge"
    psu = next(c for c in r.components if c["component_id"] == "ICP-001-PSU-01")
    assert all(s["demo_value"] for s in psu["specs"]), "fictional ratings must be flagged as demo values"


def test_invalid_articulation_and_spec_are_rejected(tmp_path):
    pkg = tmp_path / "panel"
    shutil.copytree(settings.packages_dir / "electrical-panel-icp-001", pkg)
    comps = json.loads((pkg / "components.json").read_text(encoding="utf-8"))
    comps["components"][1]["articulation"] = {"type": "hinge", "pivot": [0, 0], "axis": [0, 0, 0], "angle_deg": 90}
    comps["components"][0]["specs"] = [{"value": "no label"}]
    (pkg / "components.json").write_text(json.dumps(comps), encoding="utf-8")
    errors = " | ".join(validate_package(pkg).errors)
    assert "articulation" in errors and "spec" in errors


def test_catalog_exposes_industry_specs_and_demo_evidence(client):
    products = {p["id"]: p for p in client.get("/api/products").json()}
    assert products["ICP-001@A"]["industry"] == "Electrical"
    assert products["CHAIR-001@A"]["industry"] == "Furniture"
    assert products["ICP-001@A"]["demo_evidence_count"] >= 1
    rev = client.get("/api/revisions/ICP-001@A").json()
    psu = next(c for c in rev["components"] if c["id"] == "ICP-001-PSU-01")
    assert psu["specs"][0]["label"] == "Nominal output"
    assert next(c for c in rev["components"] if c["id"] == "ICP-001-DOOR")["articulation"]
    req = next(r for r in rev["requirements"] if r["requirement_id"] == "PSU-VISUAL")
    assert req["possible_findings"] and req["human_review_required"] is True
    assert rev["procedure"]["safety_notes"]
    assert all(d["url"].startswith("/package-files/") for d in rev["demo_evidence"])


def test_live_inspection_cannot_use_demo_material(client):
    r = client.post("/api/inspections", json={"serial_number": "ICP-001-SN-0001", "inspector": INSPECTOR})
    state = r.json()["state"]
    assert state["inspection"]["mode"] == "live"
    item = next(i for i in state["items"] if i["requirement_id"] == "MCB-CIRCUIT-ID")
    r = client.post(f"/api/inspections/{state['inspection']['id']}/items/{item['id']}/demo-evidence",
                    json={"demo_id": "DEMO-MCB", "actor": INSPECTOR})
    assert r.status_code == 409
    # The open live inspection cannot be resumed as a demo
    r = client.post("/api/inspections", json={"serial_number": "ICP-001-SN-0001", "inspector": INSPECTOR, "mode": "demo"})
    assert r.status_code == 409
    # Live upload on an electrical asset runs through the same engine
    r = client.post(f"/api/inspections/{state['inspection']['id']}/items/{item['id']}/evidence",
                    data={"actor": INSPECTOR}, files={"file": ("p.jpg", photo(), "image/jpeg")})
    assert r.status_code == 200 and r.json()["assessment"]["status"] == "unavailable"


def test_demo_inspection_replays_labelled_precomputed_result(client):
    r = client.post("/api/inspections", json={"serial_number": "ICP-001-SN-0002", "inspector": INSPECTOR, "mode": "demo"})
    state = r.json()["state"]
    iid = state["inspection"]["id"]
    assert state["inspection"]["mode"] == "demo"
    items = {i["requirement_id"]: i for i in state["items"]}

    # Demo photo must match the requirement it was prepared for
    r = client.post(f"/api/inspections/{iid}/items/{items['PSU-VISUAL']['id']}/demo-evidence",
                    json={"demo_id": "DEMO-MCB", "actor": INSPECTOR})
    assert r.status_code == 422

    entry = catalog.demo_evidence_entry("electrical-panel-icp-001", "DEMO-MCB")[1]
    r = client.post(f"/api/inspections/{iid}/items/{items['MCB-CIRCUIT-ID']['id']}/demo-evidence",
                    json={"demo_id": "DEMO-MCB", "actor": INSPECTOR, "live_ai": True})
    assert r.status_code == 200, r.text
    a = r.json()["assessment"]
    ev = next(i for i in r.json()["state"]["items"] if i["requirement_id"] == "MCB-CIRCUIT-ID")["evidence"][0]
    assert ev["kind"] == "demo" and ev["note"].startswith("DEMO PHOTO")
    if entry.get("precomputed_assessment"):
        # AI is disabled in tests, so the earlier real result is replayed and clearly labelled
        assert a["origin"] == "precomputed" and a["captured_at"] == entry["precomputed_assessment"]["captured_at"]
        assert a["result"] == entry["precomputed_assessment"]["result"]
    else:
        assert a["status"] == "unavailable"
    # Attaching a photo never makes a component "inspected"
    assert r.json()["state"]["component_status"]["ICP-001-MCB"] != "accepted"


def test_demo_without_precomputed_result_is_honestly_unavailable(client, monkeypatch):
    path, entry = catalog.demo_evidence_entry("electrical-panel-icp-001", "DEMO-PSU")
    stripped = {k: v for k, v in entry.items() if k != "precomputed_assessment"}
    monkeypatch.setattr(catalog, "demo_evidence_entry", lambda src, did: (path, stripped))
    state = client.post("/api/inspections", json={"serial_number": "ICP-001-SN-0002", "inspector": INSPECTOR,
                                                  "mode": "demo"}).json()["state"]
    item = next(i for i in state["items"] if i["requirement_id"] == "PSU-VISUAL")
    r = client.post(f"/api/inspections/{state['inspection']['id']}/items/{item['id']}/demo-evidence",
                    json={"demo_id": "DEMO-PSU", "actor": INSPECTOR})
    assert r.json()["assessment"]["status"] == "unavailable"
    assert r.json()["assessment"]["result"] is None


def test_prompt_carries_industry_profile_and_demo_markers():
    r = validate_package(settings.packages_dir / "electrical-panel-icp-001")
    comp = next(c for c in r.components if c["component_id"] == "ICP-001-PSU-01")
    req = next(q for q in r.procedure["requirements"] if q["requirement_id"] == "PSU-VISUAL")
    ctx = ai.build_context(manifest=r.manifest, procedure=r.procedure, component=comp, requirement=req,
                           serial_number="X", worker_note=None, image_checks={})
    prompt = ai.build_prompt(ctx)
    assert "Industry: Electrical" in prompt and "demonstration value" in prompt and "Suspected overheating" in prompt
    assert "de-energized" in ai.SYSTEM_PROMPT


def test_dashboard_filters_by_industry(client):
    all_ = client.get("/api/dashboard").json()
    elec = client.get("/api/dashboard?industry=Electrical").json()
    furn = client.get("/api/dashboard?industry=Furniture").json()
    assert {"Electrical", "Furniture"} <= set(all_["industries"])
    assert elec["totals"]["inspections"] == 2 and elec["totals"]["live"] == 1 and elec["totals"]["demo"] == 1
    assert furn["totals"]["inspections"] == 0
    assert all_["by_industry"] == {"Electrical": 2}
    assert all(r["industry"] == "Electrical" for r in elec["recent"])
    assert client.get("/api/inspections?industry=Furniture").json() == []
