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
