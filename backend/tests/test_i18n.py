"""Display language (X-Lang): media text overlays, AI reply language, and the package translation files."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))


def load_extinguisher(company_id: str) -> dict:
    """The demo loader's path: package parts list + translations stored with the media row."""
    import load_demo_media as loader
    from app import db, media
    from app.config import settings
    from app.packages import validate_package
    pkg = settings.packages_dir / "fire-extinguisher-fe-001"
    report = validate_package(pkg)
    row = media.create_media(company_id, "assembly.glb", (pkg / "assembly.glb").read_bytes(),
                             report.manifest["product_name"], loader.parts_of(report))
    db.update("media", {"metadata": {**row["metadata"], "translations": loader.translations_of(pkg)}}, {"id": row["id"]})
    return row


def test_media_follows_the_requested_language(world):
    boss = world.users["acme-employer"]
    row = load_extinguisher(boss["company_id"])
    c = world.login("acme-employer")
    en = c.get("/api/media").json()[0]
    es = c.get("/api/media", headers={"X-Lang": "es"}).json()[0]
    assert en["title"] == "Portable Fire Extinguisher" and es["title"] == "Extintor portátil"
    en_parts = {p["id"]: p for p in en["metadata"]["parts"]}
    es_parts = {p["id"]: p for p in es["metadata"]["parts"]}
    assert en_parts.keys() == es_parts.keys()  # identifiers never change
    assert en_parts["FE-001-CYL"]["name"] == "Pressure cylinder" and es_parts["FE-001-CYL"]["name"] == "Cilindro a presión"
    assert es_parts["FE-001-CYL"]["part_number"] == en_parts["FE-001-CYL"]["part_number"]
    assert "translations" not in es["metadata"]  # the reader gets one language
    assert c.get("/api/media", headers={"X-Lang": "fr"}).json()[0]["title"] == "Portable Fire Extinguisher"

    job = c.post("/api/jobs", headers={"X-Lang": "es"}, json={
        "title": "Revisión", "assigned_to": world.users["acme-employee"]["id"],
        "tasks": [{"description": "Revisa el cilindro", "media": [{"media_id": row["id"], "node_ids": ["FE-001-CYL"]}]}]})
    assert job.json()["tasks"][0]["media"][0]["title"] == "Extintor portátil"


def test_ai_prompts_ask_for_the_readers_language(world, monkeypatch):
    from app import ai, rag
    ctx = ai.build_context(company="Acme", job_title="J", task="T", parts=[], media_titles=[], worker_note=None,
                           image_checks=None, language="es")
    assert "Latin-American Spanish" in ai.build_prompt(ctx)
    assert "Latin-American Spanish" not in ai.build_prompt({**ctx, "language": "en"})
    assert "seguro, conforme" in ai.SYSTEM_PROMPT  # safety wording rules hold in Spanish too

    sent = {}

    class Claude:
        messages = SimpleNamespace(create=lambda **kw: sent.update(kw) or SimpleNamespace(
            stop_reason="end_turn", content=[SimpleNamespace(type="text", text="Respuesta.", citations=None)]))

    monkeypatch.setattr(ai, "claude_available", lambda: (True, ""))
    monkeypatch.setattr(ai, "claude_client", lambda: Claude())
    hits = [{"media_id": "m", "title": "Manual", "page": 1, "content": "(page 1) text"}]
    from app import i18n
    token = i18n.current_lang.set("es")
    try:
        assert rag.answer("¿Cómo?", hits)["answer"] == "Respuesta."
        assert "Spanish" in sent["system"]
    finally:
        i18n.current_lang.reset(token)
    rag.answer("How?", hits)
    assert "Spanish" not in sent["system"]


def test_package_translation_files_line_up_with_their_packages():
    from app.config import settings
    from app.packages import validate_package
    for pkg in sorted(settings.packages_dir.iterdir()):
        for f in (pkg / "translations").glob("*.json"):
            doc = json.loads(f.read_text(encoding="utf-8"))
            report = validate_package(pkg)
            assert report.ok, report.errors
            ids = {c["component_id"] for c in report.components}
            assert set(doc.get("components", {})) <= ids, f"{pkg.name}/{f.name}: unknown component ids"


def fake_translator(monkeypatch, calls: list | None = None):
    """Stands in for the model: marks each text with its target language."""
    from app import translate

    def fake(texts, target, sources=None):
        if calls is not None:
            calls.append((list(texts), target))
        return [f"[{target}] {t}" for t in texts]
    monkeypatch.setattr(translate, "translate", fake)


def test_typed_text_is_translated_on_save_and_shown_in_the_readers_language(world, monkeypatch):
    calls = []
    fake_translator(monkeypatch, calls)
    boss, emp = world.login("acme-employer"), world.login("acme-employee")
    job = boss.post("/api/jobs", json={"title": "Check extinguisher", "assigned_to": world.users["acme-employee"]["id"],
                                       "tasks": [{"description": "Read the gauge"}]}).json()
    assert len(calls) == 1 and calls[0] == (["Check extinguisher", "Read the gauge"], "es")  # one call per save
    assert job["title"] == "Check extinguisher" and "original" not in job  # the writer sees what they wrote

    task = job["tasks"][0]["id"]
    emp.post(f"/api/tasks/{task}/evidence", headers={"X-Lang": "es"}, data={"text": "La aguja está en verde"})
    assert calls[-1] == (["La aguja está en verde"], "en")

    es = emp.get(f"/api/jobs/{job['id']}", headers={"X-Lang": "es"}).json()
    assert es["title"] == "[es] Check extinguisher"
    assert es["original"] == {"lang": "en", "title": "Check extinguisher"}
    assert es["tasks"][0]["description"] == "[es] Read the gauge"
    assert es["tasks"][0]["evidence"][0]["text"] == "La aguja está en verde"
    en = boss.get(f"/api/jobs/{job['id']}").json()
    assert en["tasks"][0]["evidence"][0]["text"] == "[en] La aguja está en verde"
    assert en["tasks"][0]["evidence"][0]["original"]["text"] == "La aguja está en verde"
    assert emp.get("/api/jobs", headers={"X-Lang": "es"}).json()[0]["title"] == "[es] Check extinguisher"
    assert len(calls) == 2  # reading never re-translates what was saved


def test_missing_translations_are_filled_when_the_job_is_opened(world, monkeypatch):
    from app import db, translate
    monkeypatch.setattr(translate, "translate", lambda *args: None)  # AI unavailable at save time
    boss = world.login("acme-employer")
    job = boss.post("/api/jobs", json={"title": "Revisar panel", "assigned_to": world.users["acme-employee"]["id"],
                                       "tasks": [{"description": "Mira las etiquetas"}]}, headers={"X-Lang": "es"}).json()
    assert boss.get(f"/api/jobs/{job['id']}").json()["title"] == "Revisar panel"  # falls back to the original

    fake_translator(monkeypatch)
    assert boss.get(f"/api/jobs/{job['id']}").json()["title"] == "[en] Revisar panel"
    assert db.first("jobs", {"id": job["id"]})["translations"] == {"en": {"title": "[en] Revisar panel"}}  # stored


def test_ai_review_is_translated_when_the_job_is_opened_not_on_upload(world, monkeypatch):
    from app import db
    from test_jobs import photo
    calls = []
    fake_translator(monkeypatch, calls)
    boss, emp = world.login("acme-employer"), world.login("acme-employee")
    job = boss.post("/api/jobs", json={"title": "Check", "assigned_to": world.users["acme-employee"]["id"],
                                       "tasks": [{"description": "Gauge"}]}).json()
    task = job["tasks"][0]["id"]
    ev = emp.post(f"/api/tasks/{task}/evidence", headers={"X-Lang": "es"},
                  files={"file": ("p.jpg", photo(), "image/jpeg")}).json()["tasks"][0]["evidence"][0]
    review = {"status": "completed", "lang": "es", "result": {"summary": "Se ve el manómetro.", "observations": []}}
    db.update("evidence", {"ai_assessment": review}, {"id": ev["id"]})  # as the photo review would store it
    saves = len(calls)

    shown = boss.get(f"/api/jobs/{job['id']}").json()["tasks"][0]["evidence"][0]["ai_assessment"]
    assert shown["result"]["summary"] == "[en] Se ve el manómetro." and shown["translated_from"] == "es"
    assert len(calls) == saves + 1
    boss.get(f"/api/jobs/{job['id']}")
    assert len(calls) == saves + 1  # stored: the next view does not translate again


def test_ai_review_is_translated_for_the_other_reader(monkeypatch):
    from app import i18n, translate
    fake_translator(monkeypatch)
    result = {"summary": "Gauge visible.", "observations": ["Needle in green"], "retake_guidance": "",
              "recommended_action": "accept_for_human_review", "limitations": []}
    review = {"status": "completed", "result": dict(result), "lang": "en"}
    translate.fill([("evidence", {"ai_assessment": review})], "es")
    assert review["translations"]["es"] == {"summary": "[es] Gauge visible.", "observations": ["[es] Needle in green"]}
    token = i18n.current_lang.set("es")
    try:
        shown = i18n.review(review)
    finally:
        i18n.current_lang.reset(token)
    assert shown["result"]["summary"] == "[es] Gauge visible." and shown["translated_from"] == "en"
    assert shown["result"]["recommended_action"] == "accept_for_human_review"  # codes never change
    assert "translations" not in shown
    assert i18n.review(review)["result"] == result  # the writer's language is shown as saved


def test_client_requests_the_review_translation_right_after_upload(world, monkeypatch):
    from app import db
    from test_jobs import photo
    calls = []
    fake_translator(monkeypatch, calls)
    boss, emp = world.login("acme-employer"), world.login("acme-employee")
    job = boss.post("/api/jobs", json={"title": "Check", "assigned_to": world.users["acme-employee"]["id"],
                                       "tasks": [{"description": "Gauge"}]}).json()
    task = job["tasks"][0]["id"]
    ev = emp.post(f"/api/tasks/{task}/evidence", headers={"X-Lang": "es"},
                  files={"file": ("p.jpg", photo(), "image/jpeg")}).json()["tasks"][0]["evidence"][0]
    review = {"status": "completed", "lang": "es", "result": {"summary": "Se ve el manómetro.", "observations": []}}
    db.update("evidence", {"ai_assessment": review}, {"id": ev["id"]})  # as the photo review would store it

    assert world.login("other-employer").post(f"/api/evidence/{ev['id']}/translate").status_code == 404
    assert emp.post(f"/api/evidence/{ev['id']}/translate", headers={"X-Lang": "es"}).json() == {"translated": True}
    assert calls[-1] == (["Se ve el manómetro."], "en")
    assert emp.post(f"/api/evidence/{ev['id']}/translate").json() == {"translated": False}  # already there
    saves = len(calls)
    shown = boss.get(f"/api/jobs/{job['id']}").json()["tasks"][0]["evidence"][0]["ai_assessment"]
    assert shown["result"]["summary"] == "[en] Se ve el manómetro."
    assert len(calls) == saves  # the employer's first view does not wait on a translation


def test_translator_is_told_each_texts_language_when_known(monkeypatch):
    from app import translate
    seen = {}
    monkeypatch.setattr(translate, "translate", lambda texts, target, sources=None: seen.update(
        texts=texts, sources=sources) or [f"[{target}] {t}" for t in texts])
    rows = [("evidence", {"text": "Ya se, que hacemos?", "lang": "es"}), ("jobs", {"title": "Old job"})]
    translate.fill(rows, "en")
    assert seen == {"texts": ["Ya se, que hacemos?", "Old job"], "sources": ["es", None]}  # None: saved before lang
