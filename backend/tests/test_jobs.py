"""Jobs, tasks, evidence, media and document search, on local storage with AI stubbed."""
from __future__ import annotations

import hashlib
import io
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
GLB = ROOT / "engineering-packages" / "fire-extinguisher-fe-001" / "assembly.glb"


def photo() -> bytes:
    img = Image.new("RGB", (800, 600), (120, 130, 140))
    for x in range(0, 800, 40):  # some edges so the sharpness check passes
        for y in range(600):
            img.putpixel((x, y), (250, 250, 250))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def make_job(world, tasks=None, assignee="acme-employee"):
    c = world.login("acme-employer")
    r = c.post("/api/jobs", json={"title": "Monthly check", "assigned_to": world.users[assignee]["id"],
                                  "tasks": tasks or [{"description": "Check the gauge"},
                                                     {"description": "Check the hose"}]})
    assert r.status_code == 200, r.text
    return r.json()


def test_roles_and_company_isolation(world):
    job = make_job(world)
    assert [t["description"] for t in job["tasks"]] == ["Check the gauge", "Check the hose"]
    assert job["counts"] == {"total": 2, "pending": 2, "passed": 0, "failed": 0, "flagged": 0}

    assert [j["id"] for j in world.login("acme-employee").get("/api/jobs").json()] == [job["id"]]
    assert world.login("other-employer").get("/api/jobs").json() == []
    assert world.login("other-employer").get(f"/api/jobs/{job['id']}").status_code == 404
    assert world.login("other-employee").get(f"/api/jobs/{job['id']}").status_code == 404

    emp = world.login("acme-employee")
    r = emp.post("/api/jobs", json={"title": "x", "assigned_to": world.users["acme-employee"]["id"],
                                    "tasks": [{"description": "y"}]})
    assert r.status_code == 403
    assert emp.delete(f"/api/jobs/{job['id']}").status_code == 403

    boss = world.login("acme-employer")
    for assignee in ("acme-employer", "other-employee"):  # only employees of the same company
        r = boss.post("/api/jobs", json={"title": "x", "assigned_to": world.users[assignee]["id"],
                                         "tasks": [{"description": "y"}]})
        assert r.status_code == 422, assignee
    assert boss.post("/api/jobs", json={"title": "x", "assigned_to": world.users["acme-employee"]["id"],
                                        "tasks": []}).status_code == 422


def test_evidence_status_and_flag_escalation(world):
    job = make_job(world)
    task = job["tasks"][0]["id"]
    emp = world.login("acme-employee")

    assert emp.post(f"/api/tasks/{task}/evidence", data={"text": "  "}).status_code == 422
    r = emp.post(f"/api/tasks/{task}/evidence", data={"text": "Needle in the green"},
                 files={"file": ("p.jpg", photo(), "image/jpeg")})
    assert r.status_code == 200, r.text
    ev = r.json()["tasks"][0]["evidence"][0]
    assert ev["text"] == "Needle in the green" and ev["created_by"]["username"] == "acme-employee"
    assert ev["ai_assessment"]["status"] == "unavailable"  # AI disabled in tests: recorded, never invented
    assert ev["ai_assessment"]["image_checks"]["width"] == 800
    assert emp.get(ev["photo_url"]).headers["content-type"] == "image/jpeg"

    r = emp.post(f"/api/tasks/{task}/status", json={"status": "flagged"})
    assert r.json()["counts"]["flagged"] == 1
    assert emp.post(f"/api/tasks/{task}/status", json={"status": "done"}).status_code == 422

    boss = world.login("acme-employer")
    assert [j["counts"]["flagged"] for j in boss.get("/api/jobs").json()] == [1]
    r = boss.post(f"/api/tasks/{task}/evidence", data={"text": "my photo"}, files={"file": ("p.jpg", photo(), "image/jpeg")})
    assert r.status_code == 403  # the employer replies with notes; photos come from the field
    boss.post(f"/api/tasks/{task}/evidence", data={"text": "Fine, pass it."})
    r = boss.post(f"/api/tasks/{task}/status", json={"status": "passed"})
    t = r.json()["tasks"][0]
    assert t["status"] == "passed"
    assert [e["created_by"]["user_class"] for e in t["evidence"]] == ["employee", "employer"]

    other = world.login("other-employer")
    assert other.post(f"/api/tasks/{task}/evidence", data={"text": "hi"}).status_code == 404
    assert other.post(f"/api/tasks/{task}/status", json={"status": "failed"}).status_code == 404


def test_media_parts_links_and_delete(world):
    boss = world.login("acme-employer")
    r = boss.post("/api/media", data={"title": "Extinguisher"}, files={"file": ("fe.glb", GLB.read_bytes(), "x")})
    assert r.status_code == 200, r.text
    model = r.json()
    assert model["kind"] == "model_3d" and model["metadata"]["parts"]
    part = model["metadata"]["parts"][0]["id"]
    assert boss.post("/api/media", files={"file": ("x.exe", b"MZ", "x")}).status_code == 415
    assert boss.post("/api/media", files={"file": ("bad.glb", b"not a glb at all, really", "x")}).status_code == 415

    job = make_job(world, tasks=[{"description": "Check it", "media": [{"media_id": model["id"], "node_ids": [part]}]}])
    linked = job["tasks"][0]["media"][0]
    assert linked["node_ids"] == [part] and linked["url"]
    assert world.login("acme-employee").get(linked["url"]).status_code == 200

    other = world.login("other-employer")
    r = other.post("/api/jobs", json={"title": "x", "assigned_to": world.users["other-employee"]["id"],
                                      "tasks": [{"description": "y", "media": [{"media_id": model["id"]}]}]})
    assert r.status_code == 422  # cannot link another company's media
    assert other.get("/api/media").json() == []
    assert world.login("acme-employee").get("/api/media").status_code == 403

    assert boss.delete(f"/api/media/{model['id']}").status_code == 200
    assert boss.get(f"/api/jobs/{job['id']}").json()["tasks"][0]["media"] == []


def test_delete_job_removes_tasks_and_photos(world):
    from app import db
    job = make_job(world)
    task = job["tasks"][0]["id"]
    emp = world.login("acme-employee")
    url = emp.post(f"/api/tasks/{task}/evidence", files={"file": ("p.jpg", photo(), "image/jpeg")},
                   data={"assess": "false"}).json()["tasks"][0]["evidence"][0]["photo_url"]
    assert world.login("acme-employer").delete(f"/api/jobs/{job['id']}").status_code == 200
    assert db.count("tasks", {"job_id": job["id"]}) == 0 and db.count("evidence") == 0
    assert emp.get(url).status_code == 404


# ---------------------------------------------------------- document search --

def fake_embed(texts, input_type):
    """Deterministic bag-of-words vectors: texts sharing words are close."""
    out = []
    for t in texts:
        v = [0.0] * 64
        for w in t.lower().split():
            v[int(hashlib.md5(w.strip(".,()").encode()).hexdigest(), 16) % 64] += 1.0
        out.append(v)
    return out


class FakeClaude:
    def __init__(self):
        self.messages = self
        self.last = None

    def create(self, **kw):
        self.last = kw
        return SimpleNamespace(stop_reason="end_turn", content=[
            SimpleNamespace(type="text", text="Pull the pin first.",
                            citations=[SimpleNamespace(document_index=0, cited_text="pull the pin")]),
            SimpleNamespace(type="text", text=" Then squeeze.", citations=None)])


def test_document_search_is_company_scoped_and_cited(world, monkeypatch):
    from app import ai, rag
    monkeypatch.setattr(rag, "embed", fake_embed)
    claude = FakeClaude()
    monkeypatch.setattr(ai, "claude_available", lambda: (True, ""))
    monkeypatch.setattr(ai, "claude_client", lambda: claude)

    r = world.login("acme-employer").post("/api/media", files={"file": (
        "manual.txt", b"To use the extinguisher pull the pin, aim at the base and squeeze the handle.", "text/plain")})
    assert r.json()["indexing"] == {"indexed": True, "chunks": 1}
    world.login("other-employer").post("/api/media", files={"file": (
        "secret.txt", b"Other company secret: pull the pin on the secret machine.", "text/plain")})

    r = world.login("acme-employee").post("/api/ask", json={"question": "How do I pull the pin?"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["answer"] == "Pull the pin first.[1] Then squeeze."
    assert [s["title"] for s in body["sources"]] == ["manual"]
    assert body["sources"][0]["url"] and "#page=" not in body["sources"][0]["url"]  # text files have no pages
    sent = [b["source"]["data"] for b in claude.last["messages"][0]["content"] if b["type"] == "document"]
    assert sent and all("secret" not in d for d in sent)  # the other company's document never reaches Claude

    assert world.login("acme-employee").post("/api/ask", json={"question": "?"}).status_code == 422


def test_pdf_chunks_keep_page_numbers():
    from app import rag
    chunks = rag.chunk_pages([(1, "short page"), (2, "x " * 1200)])
    assert chunks[0] == "(page 1) short page"
    assert all(c.startswith("(page 2) ") for c in chunks[1:]) and len(chunks) >= 3


def test_scanned_document_is_kept_but_not_searchable(world, monkeypatch):
    from app import rag
    monkeypatch.setattr(rag, "embed", fake_embed)
    r = world.login("acme-employer").post("/api/media", files={"file": ("blank.txt", b"   ", "text/plain")})
    assert r.status_code == 200 and r.json()["indexing"]["indexed"] is False


# ------------------------------------------------------------------- login --

def test_login_tokens_are_verified(monkeypatch):
    import jwt
    from cryptography.hazmat.primitives.asymmetric import ec
    from fastapi import HTTPException
    from app import auth
    from app.config import settings

    key = ec.generate_private_key(ec.SECP256R1())
    monkeypatch.setattr(auth, "_jwks_client", lambda: SimpleNamespace(
        get_signing_key_from_jwt=lambda token: SimpleNamespace(key=key.public_key())))

    def token(**over):
        claims = {"sub": "user-1", "aud": "authenticated", "iss": f"{settings.supabase_url}/auth/v1",
                  "exp": int(time.time()) + 600, **over}
        return jwt.encode(claims, key, algorithm="ES256")

    assert auth.verify_token(token()) == "user-1"
    for bad in (token(exp=int(time.time()) - 10), token(aud="anon"), token(iss="https://evil.example/auth/v1")):
        with pytest.raises(HTTPException) as exc:
            auth.verify_token(bad)
        assert exc.value.status_code == 401
    other_key = ec.generate_private_key(ec.SECP256R1())
    with pytest.raises(HTTPException):
        auth.verify_token(jwt.encode({"sub": "x", "aud": "authenticated", "iss": f"{settings.supabase_url}/auth/v1",
                                      "exp": int(time.time()) + 600}, other_key, algorithm="ES256"))


def test_requests_without_login_are_rejected(world):
    from app.main import app
    app.dependency_overrides.clear()
    assert world.client.get("/api/jobs").status_code == 401
    assert world.client.get("/api/health").status_code == 200


# ----------------------------------------------------------------- dashboard --

def test_due_dates_order_jobs_and_are_validated(world):
    boss = world.login("acme-employer")
    emp = world.users["acme-employee"]["id"]
    later = boss.post("/api/jobs", json={"title": "Later", "assigned_to": emp, "due_date": "2030-05-01",
                                         "tasks": [{"description": "a"}]}).json()
    soon = boss.post("/api/jobs", json={"title": "Soon", "assigned_to": emp, "due_date": "2030-01-15",
                                        "tasks": [{"description": "a"}]}).json()
    undated = boss.post("/api/jobs", json={"title": "Undated", "assigned_to": emp,
                                           "tasks": [{"description": "a"}]}).json()
    assert soon["due_date"] == "2030-01-15" and undated["due_date"] is None
    assert [j["title"] for j in world.login("acme-employee").get("/api/jobs").json()] == ["Soon", "Later", "Undated"]
    assert boss.post("/api/jobs", json={"title": "x", "assigned_to": emp, "due_date": "next week",
                                        "tasks": [{"description": "a"}]}).status_code == 422

    # A finished job (no task pending or flagged) moves below the open ones.
    boss.post(f"/api/tasks/{soon['tasks'][0]['id']}/status", json={"status": "passed"})
    jobs = world.login("acme-employee").get("/api/jobs").json()
    assert [j["title"] for j in jobs] == ["Later", "Undated", "Soon"] and jobs[-1]["finished"] is True
    assert later["finished"] is False


def test_dashboard_lists_what_needs_the_employer_and_team_workload(world):
    job = make_job(world)  # two tasks for acme-employee
    emp = world.login("acme-employee")
    emp.post(f"/api/tasks/{job['tasks'][0]['id']}/status", json={"status": "flagged"})
    emp.post(f"/api/tasks/{job['tasks'][1]['id']}/status", json={"status": "failed"})

    r = world.login("acme-employer").get("/api/dashboard")
    assert r.status_code == 200
    d = r.json()
    assert sorted(a["status"] for a in d["attention"]) == ["failed", "flagged"]
    flagged = next(a for a in d["attention"] if a["status"] == "flagged")
    assert flagged["job_title"] == "Monthly check" and flagged["description"] == "Check the gauge"
    assert flagged["assigned_to"]["username"] == "acme-employee"
    assert d["team"] == [{"id": world.users["acme-employee"]["id"], "username": "acme-employee",
                          "user_class": "employee", "open_jobs": 1, "tasks_done": 1, "tasks_total": 2}]
    assert [j["id"] for j in d["jobs"]] == [job["id"]]

    assert emp.get("/api/dashboard").status_code == 403
    other = world.login("other-employer").get("/api/dashboard").json()
    assert other["jobs"] == [] and other["attention"] == []


def test_embedding_rate_limit_is_retried_then_reported(monkeypatch):
    import httpx
    from app import rag
    calls, sleeps = [], []
    responses = [httpx.Response(429, headers={"retry-after": "1"}, json={"detail": "slow down"}),
                 httpx.Response(200, json={"data": [{"index": 0, "embedding": [0.1, 0.2]}]})]
    monkeypatch.setattr(rag.httpx, "post", lambda *a, **kw: calls.append(1) or responses[len(calls) - 1])
    monkeypatch.setattr(rag.time, "sleep", sleeps.append)
    assert rag.embed(["x"], "query") == [[0.1, 0.2]] and sleeps == [1.0]

    monkeypatch.setattr(rag.httpx, "post", lambda *a, **kw: httpx.Response(429, json={"detail": "slow down"}))
    with pytest.raises(rag.RagError) as exc:
        rag.embed(["x"], "query")
    assert exc.value.status_code == 429 and "busy" in exc.value.message


def test_reindex_makes_a_saved_document_searchable(world, monkeypatch):
    from app import ai, rag

    def down(texts, input_type):
        raise rag.RagError("Document search is busy right now. Try again in a minute.", 429)

    monkeypatch.setattr(rag, "embed", down)
    boss = world.login("acme-employer")
    doc = boss.post("/api/media", files={"file": ("manual.txt", b"Pull the pin, aim, squeeze.", "text/plain")}).json()
    assert doc["indexing"]["indexed"] is False
    assert boss.get("/api/media").json()[0]["chunks"] == 0  # saved, shown as not searchable

    monkeypatch.setattr(rag, "embed", down)
    r = boss.post(f"/api/media/{doc['id']}/reindex").json()
    assert r["indexing"]["indexed"] is False and r["chunks"] == 0  # still down: nothing changes

    monkeypatch.setattr(rag, "embed", fake_embed)
    r = boss.post(f"/api/media/{doc['id']}/reindex").json()
    assert r["indexing"] == {"indexed": True, "chunks": 1} and r["chunks"] == 1
    r = boss.post(f"/api/media/{doc['id']}/reindex").json()
    assert r["chunks"] == 1  # re-indexing again replaces the chunks instead of adding more

    monkeypatch.setattr(ai, "claude_available", lambda: (True, ""))
    monkeypatch.setattr(ai, "claude_client", lambda: FakeClaude())
    sources = world.login("acme-employee").post("/api/ask", json={"question": "pull the pin?"}).json()["sources"]
    assert sources and sources[0]["media_id"] == doc["id"]

    model = boss.post("/api/media", files={"file": ("fe.glb", GLB.read_bytes(), "x")}).json()
    assert boss.post(f"/api/media/{model['id']}/reindex").status_code == 422  # only documents
    assert world.login("acme-employee").post(f"/api/media/{doc['id']}/reindex").status_code == 403
    assert world.login("other-employer").post(f"/api/media/{doc['id']}/reindex").status_code == 404


def test_pdf_sources_link_to_the_cited_page(world, monkeypatch):
    import sys
    sys.path.insert(0, str(ROOT / "tools"))
    from smoke_test_supabase import MANUAL_PAGES, sample_pdf
    from app import ai, rag
    monkeypatch.setattr(rag, "embed", fake_embed)
    monkeypatch.setattr(ai, "claude_available", lambda: (True, ""))
    monkeypatch.setattr(ai, "claude_client", lambda: FakeClaude())  # cites the top-ranked chunk
    boss = world.login("acme-employer")
    r = boss.post("/api/media", files={"file": ("manual.pdf", sample_pdf(MANUAL_PAGES), "application/pdf")}).json()
    assert r["indexing"] == {"indexed": True, "chunks": 3}
    src = world.login("acme-employee").post("/api/ask", json={
        "question": "after use recharge the extinguisher immediately"}).json()["sources"][0]
    assert src["page"] == 3 and src["url"].endswith("#page=3")
    assert world.login("acme-employee").get(src["url"].split("#")[0]).headers["content-type"] == "application/pdf"


def test_questions_about_a_task_carry_its_context(world, monkeypatch):
    from app import ai, rag
    queries = []
    monkeypatch.setattr(rag, "embed", lambda texts, kind: (queries.extend(texts) if kind == "query" else None)
                        or fake_embed(texts, kind))
    world.login("acme-employer").post("/api/media", files={"file": (
        "manual.txt", b"The gauge needle must be in the green zone. Pull the pin to use.", "text/plain")})
    job = make_job(world)
    task = job["tasks"][0]["id"]
    emp = world.login("acme-employee")
    emp.post(f"/api/tasks/{task}/evidence", data={"text": "Needle is slightly left of green"},
             files={"file": ("p.jpg", photo(), "image/jpeg")})
    claude = FakeClaude()  # only the question goes to this fake (saving runs the real, disabled-in-tests AI paths)
    monkeypatch.setattr(ai, "claude_available", lambda: (True, ""))
    monkeypatch.setattr(ai, "claude_client", lambda: claude)

    r = emp.post("/api/ask", json={"question": "Is this reading OK?", "task_id": task})
    assert r.status_code == 200, r.text
    content = claude.last["messages"][0]["content"]
    context = next(b["text"] for b in content if b["type"] == "text" and "question is about this task" in b["text"])
    assert "Task: Check the gauge" in context and "Job: Monthly check" in context
    assert "Note from the employee" in context and "slightly left of green" in context
    assert [b["type"] for b in content].count("image") == 1  # the latest photo goes along
    assert [b["type"] for b in content].count("document") >= 1  # documents are still the citable sources
    assert content[-1]["text"] == "Question: Is this reading OK?"
    assert queries[-1] == "Is this reading OK?\nCheck the gauge"  # the task sharpens the search

    other = world.login("other-employee").post("/api/ask", json={"question": "Is this OK?", "task_id": task})
    assert other.status_code == 404  # another company's task: nothing leaks into the answer
    general = emp.post("/api/ask", json={"question": "How do I use it?"})
    assert general.status_code == 200
    assert not any("question is about this task" in b.get("text", "") for b in claude.last["messages"][0]["content"])
