"""End-to-end check against the real Supabase project: login, jobs, photo upload, signed URLs, cleanup.

Creates a throwaway company with one employer and one employee (random passwords), signs both in through
Supabase Auth, runs a job through the API, then deletes everything it created. Your real companies, logins
and data are not touched. The photo review and document search run only if their API keys are configured.

Usage:
    backend/.venv/bin/python tools/smoke_test_supabase.py
"""
import io
import secrets
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image  # noqa: E402

from app import db  # noqa: E402
from app.blobs import blobs  # noqa: E402
from app.config import settings  # noqa: E402
from app.main import app  # noqa: E402

GLB = ROOT / "engineering-packages" / "fire-extinguisher-fe-001" / "assembly.glb"


def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        raise SystemExit(1)


def main() -> int:
    if settings.data_backend != "supabase" or not settings.supabase_publishable_key:
        print("Needs SUPABASE_URL, SUPABASE_SECRET_KEY and SUPABASE_PUBLISHABLE_KEY in backend/.env")
        return 1
    admin = httpx.Client(base_url=f"{settings.supabase_url}/auth/v1", timeout=20, headers={
        "apikey": settings.supabase_secret_key, "Authorization": f"Bearer {settings.supabase_secret_key}"})
    tag = secrets.token_hex(4)
    company_id, user_ids, job_id = db.new_id(), [], None
    try:
        db.insert("companies", {"id": company_id, "name": f"Smoke test {tag}"})
        tokens = {}
        for role in ("employer", "employee"):
            email, password = f"smoke-{tag}-{role}@example.com", secrets.token_urlsafe(16)
            r = admin.post("/admin/users", json={"email": email, "password": password, "email_confirm": True})
            r.raise_for_status()
            user_ids.append(r.json()["id"])
            db.insert("users", {"id": user_ids[-1], "company_id": company_id, "username": f"smoke {role}",
                                "user_class": role})
            r = httpx.post(f"{settings.supabase_url}/auth/v1/token", params={"grant_type": "password"},
                           headers={"apikey": settings.supabase_publishable_key},
                           json={"email": email, "password": password}, timeout=20)
            r.raise_for_status()
            tokens[role] = {"Authorization": f"Bearer {r.json()['access_token']}"}
        check(True, "created throwaway company and two logins, signed in through Supabase Auth")

        c = TestClient(app)
        check(c.get("/api/jobs").status_code == 401, "no token -> 401")
        check(c.get("/api/jobs", headers={"Authorization": "Bearer nonsense"}).status_code == 401, "bad token -> 401")
        me = c.get("/api/me", headers=tokens["employee"]).json()
        check(me["user_class"] == "employee" and me["company"]["id"] == company_id, "token verified, profile loaded")

        r = c.post("/api/media", headers=tokens["employer"], data={"title": "Smoke model"},
                   files={"file": ("fe.glb", GLB.read_bytes(), "model/gltf-binary")})
        check(r.status_code == 200, f"employer uploads a 3D model ({r.status_code})")
        model = r.json()
        check(httpx.get(model["url"], timeout=20).status_code == 200, "signed model URL downloads from Storage")

        r = c.post("/api/jobs", headers=tokens["employer"], json={
            "title": "Smoke job", "assigned_to": user_ids[1],
            "tasks": [{"description": "Photograph the gauge",
                       "media": [{"media_id": model["id"], "node_ids": [model["metadata"]["parts"][0]["id"]]}]},
                      {"description": "Note the hose condition"}]})
        check(r.status_code == 200, f"employer creates a job ({r.status_code})")
        job_id = r.json()["id"]
        task = r.json()["tasks"][0]["id"]
        check(c.post("/api/jobs", headers=tokens["employee"], json={
            "title": "x", "assigned_to": user_ids[1], "tasks": [{"description": "y"}]}).status_code == 403,
            "employee cannot create jobs")
        check([j["id"] for j in c.get("/api/jobs", headers=tokens["employee"]).json()] == [job_id],
              "employee sees the assigned job")

        buf = io.BytesIO()
        Image.new("RGB", (640, 480), (90, 120, 160)).save(buf, format="JPEG")
        r = c.post(f"/api/tasks/{task}/evidence", headers=tokens["employee"], data={"text": "Gauge photo"},
                   files={"file": ("p.jpg", buf.getvalue(), "image/jpeg")})
        check(r.status_code == 200, f"employee uploads photo evidence ({r.status_code})")
        ev = r.json()["tasks"][0]["evidence"][0]
        check(httpx.get(ev["photo_url"], timeout=20).status_code == 200, "signed photo URL downloads from Storage")
        print(f"     AI review: {ev['ai_assessment']['status']} ({ev['ai_assessment'].get('error') or 'ok'})")

        r = c.post(f"/api/tasks/{task}/status", headers=tokens["employee"], json={"status": "flagged"})
        check(r.json()["counts"]["flagged"] == 1, "employee flags the task")
        r = c.post(f"/api/tasks/{task}/status", headers=tokens["employer"], json={"status": "passed"})
        check(r.json()["tasks"][0]["status"] == "passed", "employer resolves it")

        r = c.post("/api/ask", headers=tokens["employee"], json={"question": "How do I check the gauge?"})
        print(f"     document search: HTTP {r.status_code} {str(r.json())[:120]}")
        return 0
    finally:
        try:
            if job_id:
                TestClient(app).delete(f"/api/jobs/{job_id}", headers=tokens["employer"])
            blobs.delete([m["storage_path"] for m in db.select("media", {"company_id": company_id})])
            db.delete("media", {"company_id": company_id})
            db.delete("jobs", {"company_id": company_id})
            for uid in user_ids:
                admin.delete(f"/admin/users/{uid}")  # profile rows cascade
            db.delete("companies", {"id": company_id})
            print("ok   cleaned up the throwaway company, logins, job and files")
        except Exception as exc:  # noqa: BLE001 - report, never hide, a failed cleanup
            print(f"FAIL cleanup: {exc} (delete company 'Smoke test {tag}' by hand)")


if __name__ == "__main__":
    sys.exit(main())
