"""Regression tests for the second audit (2026-10-24, see docs/AUDIT.md section 2)."""
from __future__ import annotations

import io
import json
import shutil

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app import ai
from app.config import settings
from app.main import app
from app.packages import validate_package

INSPECTOR = "Inspector Ana"


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


def test_dashboard_counts_component_only_when_all_its_items_are_done(client):
    r = client.post("/api/inspections", json={"serial_number": "CHAIR-001-SN-0025", "inspector": INSPECTOR})
    iid = r.json()["inspection_id"]
    items = {i["requirement_id"]: i for i in r.json()["state"]["items"]}
    # Backrest has two requirements; complete only one of them.
    surf = items["BACKREST-SURFACE"]
    client.post(f"/api/inspections/{iid}/items/{surf['id']}/evidence", data={"actor": INSPECTOR},
                files={"file": ("p.jpg", photo(), "image/jpeg")})
    assert client.post(f"/api/inspections/{iid}/items/{surf['id']}/decision",
                       json={"decision": "pass", "actor": INSPECTOR}).status_code == 200
    d = client.get("/api/dashboard?industry=Furniture").json()
    assert d["totals"]["components_inspected"] == 0  # backrest is only half done


def test_demo_inspections_are_marked_in_passport_and_findings(client):
    r = client.post("/api/inspections", json={"serial_number": "ICP-001-SN-0002", "inspector": INSPECTOR, "mode": "demo"})
    iid = r.json()["inspection_id"]
    item = next(i for i in r.json()["state"]["items"] if i["requirement_id"] == "RELAYS-SEATED")
    client.post(f"/api/inspections/{iid}/items/{item['id']}/decision",
                json={"decision": "fail", "actor": INSPECTOR, "finding": {"description": "DEMO relay", "severity": "low"}})
    passport = client.get("/api/instances/ICP-001-SN-0002").json()
    assert passport["inspections"][0]["mode"] == "demo"
    assert passport["findings"][0]["mode"] == "demo"
    finding = next(f for f in client.get("/api/findings").json() if f["inspection_id"] == iid)
    assert finding["mode"] == "demo"


def test_invalid_precomputed_assessment_is_a_validation_error(tmp_path):
    pkg = tmp_path / "panel"
    shutil.copytree(settings.packages_dir / "electrical-panel-icp-001", pkg)
    path = pkg / "demo-evidence" / "demo-evidence.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["items"][0]["precomputed_assessment"] = {"model": "x", "captured_at": "2026-10-24", "result": {"summary": "only"}}
    path.write_text(json.dumps(doc), encoding="utf-8")
    errors = " | ".join(validate_package(pkg).errors)
    assert "precomputed" in errors


def test_ai_request_budget_fits_hosted_function_limit():
    # Worst case (timeout x attempts) must stay under the 60 s maxDuration configured in vercel.json.
    attempts = settings.ai_max_retries + 1
    assert settings.ai_timeout_s * attempts < 60 or not settings.storage_mode == "ephemeral"
    assert hasattr(settings, "ai_max_retries")


def test_large_upload_error_is_explained(client):
    r = client.post("/api/inspections", json={"serial_number": "TABLE-001-SN-0107", "inspector": INSPECTOR})
    iid = r.json()["inspection_id"]
    item = next(i for i in r.json()["state"]["items"] if i["requirement_id"] == "TOP-SURFACE")
    big = b"\xff\xd8" + b"0" * (settings.max_upload_mb * 1024 * 1024 + 10)
    r = client.post(f"/api/inspections/{iid}/items/{item['id']}/evidence", data={"actor": INSPECTOR},
                    files={"file": ("big.jpg", big, "image/jpeg")})
    assert r.status_code == 413 and "MB" in r.json()["detail"]


def test_provider_uses_configured_retries(monkeypatch):
    captured = {}

    class FakeAnthropic:
        def __init__(self, **kw):
            captured.update(kw)

    import anthropic
    monkeypatch.setattr(anthropic, "Anthropic", FakeAnthropic)
    ai.AnthropicProvider()._get_client()
    assert captured["max_retries"] == settings.ai_max_retries
