"""Regression tests for issues found in the 2026-10-24 audit (see docs/AUDIT.md)."""
from __future__ import annotations

import io
import os
import tempfile
from pathlib import Path

import pytest

os.environ.setdefault("DATA_DIR", str(Path(tempfile.mkdtemp(prefix="fep-audit-")) / "data"))
os.environ["AI_PROVIDER"] = "none"

from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image  # noqa: E402

from app import ai, db  # noqa: E402
from app.main import app  # noqa: E402

INSPECTOR, SUPERVISOR = "Inspector Ana", "Supervisor Ben"


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def photo() -> bytes:
    img = Image.new("RGB", (800, 600), (150, 110, 70))
    for x in range(0, 800, 40):
        for y in range(600):
            img.putpixel((x, y), (20, 20, 20))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def start(client, serial):
    r = client.post("/api/inspections", json={"serial_number": serial, "inspector": INSPECTOR})
    assert r.status_code == 200, r.text
    return r.json()["inspection_id"], {i["requirement_id"]: i for i in r.json()["state"]["items"]}


def upload(client, iid, item_id):
    return client.post(f"/api/inspections/{iid}/items/{item_id}/evidence", data={"actor": INSPECTOR},
                       files={"file": ("p.jpg", photo(), "image/jpeg")})


def complete_all(client, iid, items):
    for it in items.values():
        if it["requirement_snapshot"]["evidence_type"] != "manual_confirmation":
            upload(client, iid, it["id"])
        r = client.post(f"/api/inspections/{iid}/items/{it['id']}/decision",
                        json={"decision": "pass", "actor": INSPECTOR, "manual_confirmed": True})
        assert r.status_code == 200, r.text


def test_upload_to_unknown_item_or_inspection_is_404_not_500(client):
    iid, _ = start(client, "CHAIR-001-SN-0026")
    assert upload(client, iid, "item_doesnotexist").status_code == 404
    assert upload(client, "insp_doesnotexist", "item_x").status_code == 404


def test_blank_actor_rejected(client):
    r = client.post("/api/inspections", json={"serial_number": "CHAIR-001-SN-0026", "inspector": "   "})
    assert r.status_code == 422


def test_supervisor_request_on_manual_item_can_be_resolved(client):
    iid, items = start(client, "TABLE-001-SN-0108")
    complete_all(client, iid, items)
    assert client.post(f"/api/inspections/{iid}/submit", json={"actor": INSPECTOR}).status_code == 200
    leg = items["LEG-FL-CONDITION"]  # manual_confirmation only: no photo can be uploaded
    r = client.post(f"/api/inspections/{iid}/review", json={"reviewer": SUPERVISOR, "decision": "request_evidence",
                                                            "comments": "Re-check", "item_ids": [leg["id"]]})
    assert r.status_code == 200
    r = client.post(f"/api/inspections/{iid}/items/{leg['id']}/decision",
                    json={"decision": "pass", "actor": INSPECTOR, "manual_confirmed": True})
    assert r.status_code == 422  # must say what was re-checked
    r = client.post(f"/api/inspections/{iid}/items/{leg['id']}/decision",
                    json={"decision": "pass", "actor": INSPECTOR, "manual_confirmed": True,
                          "observation": "Re-checked joint, no movement"})
    assert r.status_code == 200, r.text
    assert client.post(f"/api/inspections/{iid}/submit", json={"actor": INSPECTOR}).status_code == 200

    # No second inspection may be opened while one is awaiting review
    r = client.post("/api/inspections", json={"serial_number": "TABLE-001-SN-0108", "inspector": INSPECTOR})
    assert r.status_code == 409

    # Evidence cannot be re-assessed once the inspection left the inspector's hands
    ev = next(e for it in client.get(f"/api/inspections/{iid}").json()["items"] for e in it["evidence"])
    assert client.post(f"/api/evidence/{ev['id']}/assess").status_code == 409


def test_not_applicable_blocked_while_finding_open(client):
    iid, items = start(client, "CHAIR-001-SN-0026")
    seat = items["SEAT-SURFACE"]
    upload(client, iid, seat["id"])
    r = client.post(f"/api/inspections/{iid}/items/{seat['id']}/decision",
                    json={"decision": "fail", "actor": INSPECTOR, "finding": {"description": "crack", "severity": "high"}})
    assert r.status_code == 200
    r = client.post(f"/api/inspections/{iid}/items/{seat['id']}/decision",
                    json={"decision": "not_applicable", "actor": INSPECTOR, "observation": "n/a"})
    assert r.status_code == 422


def test_stale_assessment_does_not_override_newer_evidence(client, monkeypatch):
    iid, items = start(client, "TABLE-001-SN-0107")
    item = items["TOP-SURFACE"]
    first = upload(client, iid, item["id"]).json()["evidence_id"]
    upload(client, iid, item["id"])  # newer evidence supersedes the first one

    class Retake:
        name = "test-double"

        def available(self):
            return True, "test"

        def assess(self, image_jpeg, context):
            return ai.AssessmentOutcome("test-double", "x", "completed", {
                "summary": "s", "correct_area_visible": "no", "image_quality": "poor", "evidence_sufficient": False,
                "observations": [], "conditions_for_human_review": [], "missing_information": [],
                "recommended_action": "retake_photo", "retake_guidance": "g", "uncertainty": "low",
                "limitations": []}, None, 1)

    monkeypatch.setattr(ai, "get_provider", lambda: Retake())
    assert client.post(f"/api/evidence/{first}/assess").status_code == 200  # late result for the OLD photo
    state = client.get(f"/api/inspections/{iid}").json()
    it = next(i for i in state["items"] if i["id"] == item["id"])
    assert it["status"] == "evidence_submitted"
    r = client.post(f"/api/inspections/{iid}/items/{item['id']}/decision", json={"decision": "pass", "actor": INSPECTOR})
    assert r.status_code == 200, r.text  # judged on the latest photo, which has no retake recommendation


def test_ai_flagged_condition_is_visible_to_supervisor(client, monkeypatch):
    iid, items = start(client, "CHAIR-001-SN-0025")
    item = items["BACKREST-SURFACE"]

    class Flag:
        name = "test-double"

        def available(self):
            return True, "test"

        def assess(self, image_jpeg, context):
            return ai.AssessmentOutcome("test-double", "x", "completed", {
                "summary": "s", "correct_area_visible": "yes", "image_quality": "good", "evidence_sufficient": True,
                "observations": [], "conditions_for_human_review": ["possible crack at top edge"],
                "missing_information": [], "recommended_action": "flag_for_human_review", "retake_guidance": "",
                "uncertainty": "medium", "limitations": []}, None, 1)

    monkeypatch.setattr(ai, "get_provider", lambda: Flag())
    upload(client, iid, item["id"])
    r = client.post(f"/api/inspections/{iid}/items/{item['id']}/decision", json={"decision": "pass", "actor": INSPECTOR})
    assert r.status_code == 200
    assert any("flagged" in w["reason"] for w in r.json()["readiness"]["warnings"])


def test_timestamps_have_subsecond_precision():
    assert "." in db.now()


def test_access_password_gate(client, monkeypatch):
    import base64
    from app.config import settings
    monkeypatch.setattr(settings.__class__, "access_password", property(lambda self: "s3cret"))
    assert client.get("/api/health").status_code == 401
    bad = base64.b64encode(b"x:wrong").decode()
    assert client.get("/api/health", headers={"Authorization": f"Basic {bad}"}).status_code == 401
    good = base64.b64encode(b"anyone:s3cret").decode()
    r = client.get("/api/health", headers={"Authorization": f"Basic {good}"})
    assert r.status_code == 200 and r.json()["storage"] in ("persistent", "ephemeral")
