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

MANUAL_PAGES = [
    ["Portable fire extinguisher - inspection manual (smoke test sample)", "",
     "Monthly visual inspection:", "1. The pressure gauge needle must be in the green zone.",
     "2. The safety pin and tamper seal must be in place and unbroken.", "3. The extinguisher must be on its hanger."],
    ["Hose and nozzle", "Check the hose for cracks, cuts or blockage, and the nozzle for dirt or nests.", "",
     "Professional maintenance:", "A certified technician must service the extinguisher every 12 months.",
     "A hydrostatic test of the cylinder is required every 5 years."],
    ["After use", "Recharge the extinguisher immediately after any use, even if it was only partly discharged.",
     "Never return a used extinguisher to its hanger without recharging it."],
]


def sample_pdf(pages: list[list[str]]) -> bytes:
    """A small text PDF (one Helvetica text block per page), so search is tested on a real PDF file."""
    objs = ["<< /Type /Catalog /Pages 2 0 R >>", None, "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    kids = []
    for lines in pages:
        esc = [l.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)") for l in lines]
        stream = "BT /F1 11 Tf 50 760 Td 16 TL " + " ".join(f"({l}) '" for l in esc) + " ET"
        objs.append(f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream")
        objs.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {len(objs)} 0 R "
                    "/Resources << /Font << /F1 3 0 R >> >> >>")
        kids.append(f"{len(objs)} 0 R")
    objs[1] = f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(kids)} >>"
    out, offsets = b"%PDF-1.4\n", []
    for i, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n{body}\nendobj\n".encode("latin-1")
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    out += "".join(f"{o:010d} 00000 n \n" for o in offsets).encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return out


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
            "title": "Smoke job", "assigned_to": user_ids[1], "due_date": "2030-01-15",
            "tasks": [{"description": "Photograph the gauge",
                       "media": [{"media_id": model["id"], "node_ids": [model["metadata"]["parts"][0]["id"]]}]},
                      {"description": "Note the hose condition"}]})
        check(r.status_code == 200, f"employer creates a job ({r.status_code})")
        job_id = r.json()["id"]
        check(r.json()["due_date"] == "2030-01-15", "due date stored")
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
        d = c.get("/api/dashboard", headers=tokens["employer"]).json()
        check([a["status"] for a in d["attention"]] == ["flagged"] and d["team"][0]["open_jobs"] == 1,
              "employer overview shows the flagged task and the team workload")
        check(c.get("/api/dashboard", headers=tokens["employee"]).status_code == 403, "employee cannot open the overview")
        r = c.post(f"/api/tasks/{task}/status", headers=tokens["employer"], json={"status": "passed"})
        check(r.json()["tasks"][0]["status"] == "passed", "employer resolves it")

        if not settings.voyage_api_key:
            print("     document search: skipped (no VOYAGE_API_KEY)")
            return 0
        r = c.post("/api/media", headers=tokens["employer"], data={"title": "Extinguisher manual"},
                   files={"file": ("manual.pdf", sample_pdf(MANUAL_PAGES), "application/pdf")})
        idx = r.json().get("indexing") or {}
        check(r.status_code == 200 and idx.get("indexed"), f"PDF uploaded and indexed ({idx})")
        stored = db.select("document_chunks", {"company_id": company_id}, columns="chunk_index,content")
        check(len(stored) == idx["chunks"] and all(ch["content"].startswith("(page ") for ch in stored),
              f"{len(stored)} chunks with page numbers stored in Supabase (pgvector)")
        hits = __import__("app.rag", fromlist=["rag"]).search(company_id, "How often does a technician service it?")
        check(hits and hits[0]["page"] == 2, f"vector search ranks page 2 first (pages: {[h['page'] for h in hits]})")
        if not settings.anthropic_ok:
            print("     document answers: skipped (no ANTHROPIC_API_KEY)")
            return 0
        r = c.post("/api/ask", headers=tokens["employee"],
                   json={"question": "How often does the extinguisher need professional maintenance?"})
        body = r.json()
        print(f"     answer: {str(body.get('answer', body))[:160]}")
        check(r.status_code == 200 and "12" in body["answer"], "answer from the manual mentions 12 months")
        check(any(src["page"] == 2 and src["title"] == "Extinguisher manual" for src in body["sources"]),
              f"answer cites the manual, page 2 ({[(src['title'], src['page']) for src in body['sources']]})")
        r = c.post("/api/ask", headers={**tokens["employee"], "X-Lang": "es"},
                   json={"question": "¿Qué hago después de usar el extintor?"})
        body = r.json()
        if r.status_code == 429:  # Voyage without a payment method allows 3 requests per minute
            print("     Spanish question: skipped, Voyage rate limit (add a payment method in Voyage to lift it)")
            return 0
        print(f"     respuesta: {str(body.get('answer', body))[:160]}")
        check(r.status_code == 200 and any(w in body["answer"].lower() for w in (" el ", " la ", "recarg")),
              "Spanish question gets a Spanish answer")
        check(any(src["page"] == 3 for src in body["sources"]), "Spanish answer cites page 3 (after use)")
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
