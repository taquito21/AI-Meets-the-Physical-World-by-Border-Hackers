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


def test_asset_without_3d_model_is_fully_inspectable(client, tmp_path):
    """Mode B: no assembly_file. The inspection engine must work from the component list alone."""
    from app import catalog, db
    pkg = tmp_path / "no3d"
    shutil.copytree(settings.packages_dir / "table-model-001", pkg)
    m = json.loads((pkg / "manifest.json").read_text(encoding="utf-8"))
    m.pop("assembly_file")
    m["product_id"], m["package_id"], m["product_name"] = "NO3D-001", "PKG-NO3D-001-A", "Asset without 3D"
    (pkg / "manifest.json").write_text(json.dumps(m), encoding="utf-8")
    (pkg / "assembly.glb").unlink()
    comps = json.loads((pkg / "components.json").read_text(encoding="utf-8"))
    comps["product_id"] = "NO3D-001"
    for c in comps["components"]:
        c["component_id"] = c["component_id"].replace("TABLE-001", "NO3D-001")
        c.pop("model_node_ids"); c.pop("explosion")
    (pkg / "components.json").write_text(json.dumps(comps), encoding="utf-8")
    proc = json.loads((pkg / "inspection-procedure.json").read_text(encoding="utf-8"))
    proc["product_id"] = "NO3D-001"
    for r in proc["requirements"]:
        r["component_id"] = r["component_id"].replace("TABLE-001", "NO3D-001")
    (pkg / "inspection-procedure.json").write_text(json.dumps(proc), encoding="utf-8")

    report = validate_package(pkg)
    assert report.ok, report.errors
    assert catalog.load_package(pkg)["status"] == "loaded"
    with db.tx() as conn:
        conn.execute("INSERT INTO product_instances VALUES (?,?,?,?,?,?)",
                     ("NO3D-SN-1", "NO3D-001", "NO3D-001@A", "NO3D-SN-1", "{}", db.now()))
    rev = client.get("/api/revisions/NO3D-001@A").json()
    assert rev["assembly_url"] is None and len(rev["components"]) == 12
    s = client.post("/api/inspections", json={"serial_number": "NO3D-SN-1", "inspector": INSPECTOR}).json()
    item = next(i for i in s["state"]["items"] if i["requirement_id"] == "TOP-SURFACE")
    r = client.post(f"/api/inspections/{s['inspection_id']}/items/{item['id']}/evidence",
                    data={"actor": INSPECTOR}, files={"file": ("p.jpg", photo(), "image/jpeg")})
    assert r.status_code == 200
    r = client.post(f"/api/inspections/{s['inspection_id']}/items/{item['id']}/decision",
                    json={"decision": "fail", "actor": INSPECTOR, "finding": {"description": "chip", "severity": "low"}})
    assert r.status_code == 200 and r.json()["component_status"]["NO3D-001-TOP"] == "finding"


def test_fire_extinguisher_asset_end_to_end(client):
    """FE-001: textured 3D model, stable component IDs shared with the inspection engine, demo flow, dashboard."""
    import struct
    pkg = settings.packages_dir / "fire-extinguisher-fe-001"
    report = validate_package(pkg)
    assert report.ok and not report.warnings, (report.errors, report.warnings)
    data = (pkg / "assembly.glb").read_bytes()
    gltf = json.loads(data[20:20 + struct.unpack_from("<I", data, 12)[0]])
    assert len(gltf["images"]) == 3 and all(i["mimeType"] == "image/png" for i in gltf["images"])  # label, gauge, tag
    textured = [m for m in gltf["meshes"] if "TEXCOORD_0" in m["primitives"][0]["attributes"]]
    assert {m["name"] for m in textured} == {"gauge_face_mesh", "instructions_label_mesh", "tag_card_mesh"}
    ids = {c["component_id"] for c in report.components}
    assert {"FE-001-CYL", "FE-001-GAU", "FE-001-PIN", "FE-001-SEA", "FE-001-HOS", "FE-001-NOZ", "FE-001-BRK"} <= ids
    assert {r["component_id"] for r in report.procedure["requirements"]} == ids  # every component is inspectable
    assert any("not a disassembly" in n for n in report.procedure["safety_notes"])

    rev = client.get("/api/revisions/FE-001@A").json()
    assert rev["industry"] == "Facility Safety" and rev["assembly_url"].endswith("assembly.glb")
    s = client.post("/api/inspections", json={"serial_number": "FE-001-SN-0002", "inspector": INSPECTOR, "mode": "demo"}).json()
    iid = s["inspection_id"]
    item = next(i for i in s["state"]["items"] if i["requirement_id"] == "PIN-AND-SEAL")
    r = client.post(f"/api/inspections/{iid}/items/{item['id']}/demo-evidence",
                    json={"demo_id": "DEMO-FE-PIN", "actor": INSPECTOR, "live_ai": True})
    assert r.status_code == 200
    assert r.json()["assessment"]["origin"] == "precomputed"  # AI disabled in tests -> labelled replay
    assert r.json()["state"]["component_status"]["FE-001-PIN"] != "accepted"  # a photo never passes a part by itself
    r = client.post(f"/api/inspections/{iid}/items/{item['id']}/decision",
                    json={"decision": "fail", "actor": INSPECTOR, "finding": {"description": "Safety pin missing", "severity": "high"}})
    assert r.status_code == 200 and r.json()["component_status"]["FE-001-PIN"] == "finding"
    d = client.get("/api/dashboard?industry=Facility%20Safety").json()
    assert d["totals"]["inspections"] == 1 and d["totals"]["open_findings"] == 1
    assert "Facility Safety" in client.get("/api/dashboard").json()["industries"]


def test_system_prompt_has_safety_equipment_rule():
    assert "never state that it is charged" in ai.SYSTEM_PROMPT
