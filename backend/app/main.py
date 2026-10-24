"""FastAPI application: REST API (OpenAPI at /docs), package files, evidence files and the web client."""
from __future__ import annotations

import base64
import hmac
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, StringConstraints
from starlette.concurrency import run_in_threadpool

from . import ai, catalog, db, workflow
from .config import settings
from .packages import discover_packages, validate_package
from .workflow import WorkflowError

API_VERSION = "0.1.0"


_ready = False
_ready_lock = threading.Lock()


def ensure_ready() -> None:
    """Create the schema and load packages. Idempotent; re-runs if a serverless /tmp was wiped."""
    global _ready
    if _ready and settings.db_path.exists():
        return
    with _ready_lock:  # concurrent first requests on a cold instance initialize once
        if _ready and settings.db_path.exists():
            return
        db.init_db()
        settings.evidence_dir.mkdir(parents=True, exist_ok=True)
        for result in catalog.bootstrap():
            print(f"[packages] {result.get('status')}: {result.get('revision_id') or result.get('package_dir')} "
                  f"{result.get('error', '')}")
        _ready = True


@asynccontextmanager
async def lifespan(_: FastAPI):
    ensure_ready()
    yield


app = FastAPI(title="Field Execution Platform API", version=API_VERSION, lifespan=lifespan,
              description="Engineering-driven inspection platform (hackathon MVP). Internal id: field-execution-platform.")
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["*"], allow_headers=["*"])


@app.middleware("http")
async def access_and_readiness(request: Request, call_next):
    # Shared-password gate for hosted test deployments (no user accounts in the MVP).
    if settings.access_password:
        ok = False
        header = request.headers.get("authorization", "")
        if header.lower().startswith("basic "):
            try:
                _, _, password = base64.b64decode(header[6:]).decode("utf-8").partition(":")
                ok = hmac.compare_digest(password.encode(), settings.access_password.encode())
            except (ValueError, UnicodeDecodeError):
                ok = False
        if not ok:
            return Response("Password required", status_code=401,
                            headers={"WWW-Authenticate": 'Basic realm="Field Assistant", charset="UTF-8"'})
    if not _ready or not settings.db_path.exists():
        await run_in_threadpool(ensure_ready)
    return await call_next(request)


@app.exception_handler(WorkflowError)
async def workflow_error_handler(_: Request, exc: WorkflowError):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message, "issues": exc.details})


# ------------------------------------------------------------------ models --

# Names are recorded on every action; blank or whitespace-only names are rejected.
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]


class StartInspection(BaseModel):
    serial_number: str
    inspector: Name
    mode: Literal["live", "demo"] = "live"


class UseDemoEvidence(BaseModel):
    demo_id: str
    actor: Name
    live_ai: bool = True  # try a real model call first; fall back to the labelled precomputed result


class FindingIn(BaseModel):
    description: str
    severity: Literal["low", "medium", "high", "critical"] = "medium"


class Decision(BaseModel):
    decision: Literal["pass", "fail", "not_applicable"]
    actor: Name
    observation: str | None = None
    manual_confirmed: bool = False
    override_note: str | None = None
    finding: FindingIn | None = None


class Actor(BaseModel):
    actor: Name


class ReviewIn(BaseModel):
    reviewer: Name
    decision: Literal["approve", "reject", "request_evidence"]
    comments: str | None = None
    item_ids: list[str] = []


class FindingTransition(BaseModel):
    to: Literal["assigned", "void", "action_recorded", "awaiting_verification", "closed"]
    actor: Name
    assigned_to: str | None = None
    note: str | None = None


# ------------------------------------------------------------------ system --

@app.get("/api/health")
def health() -> dict[str, Any]:
    provider = ai.get_provider()
    available, detail = provider.available()
    return {"status": "ok", "version": API_VERSION, "app_label": settings.app_label,
            "storage": settings.storage_mode,
            "ai": {"provider": provider.name, "available": available, "detail": detail}}


# ----------------------------------------------------------------- catalog --

@app.get("/api/products")
def list_products() -> list[dict[str, Any]]:
    with db.read() as conn:
        revs = db.rows(conn.execute(
            "SELECT r.id, r.revision, r.product_model_id AS product_id, m.name AS product_name, "
            "m.description, mf.name AS manufacturer, p.id AS package_id, p.source_dir, p.manifest, "
            "(SELECT COUNT(*) FROM components c WHERE c.product_revision_id = r.id) AS component_count, "
            "(SELECT COUNT(*) FROM inspection_requirements q WHERE q.product_revision_id = r.id) AS requirement_count "
            "FROM product_revisions r JOIN product_models m ON m.id = r.product_model_id "
            "JOIN manufacturers mf ON mf.id = m.manufacturer_id "
            "JOIN engineering_packages p ON p.id = r.engineering_package_id ORDER BY m.name, r.revision").fetchall())
        for r in revs:
            r["instances"] = db.rows(conn.execute(
                "SELECT i.serial_number, i.metadata, (SELECT status FROM inspections s WHERE s.product_instance_id = i.id "
                "ORDER BY s.started_at DESC LIMIT 1) AS last_inspection_status, (SELECT mode FROM inspections s "
                "WHERE s.product_instance_id = i.id ORDER BY s.started_at DESC LIMIT 1) AS last_inspection_mode "
                "FROM product_instances i WHERE i.product_revision_id = ? ORDER BY i.serial_number", (r["id"],)).fetchall())
            manifest = r.pop("manifest")
            r["demonstration_package"] = bool(manifest.get("demonstration_package"))
            r["has_3d"] = bool(manifest.get("assembly_file"))
            r["industry"] = manifest.get("industry") or "General"
            r["asset_category"] = manifest.get("asset_category")
            r["demo_evidence_count"] = len(catalog.demo_evidence(r["source_dir"]))
    return revs


@app.get("/api/revisions/{revision_id}")
def get_revision(revision_id: str) -> dict[str, Any]:
    with db.read() as conn:
        rev = catalog.get_revision(conn, revision_id)
    if not rev:
        raise HTTPException(404, "Revision not found")
    return rev


@app.get("/api/instances/{serial_number}")
def product_passport(serial_number: str) -> dict[str, Any]:
    with db.read() as conn:
        inst = db.row(conn.execute("SELECT * FROM product_instances WHERE serial_number = ?",
                                   (serial_number,)).fetchone())
        if not inst:
            raise HTTPException(404, "Product instance not found")
        rev = db.row(conn.execute(
            "SELECT r.id, r.revision, m.name AS product_name, mf.name AS manufacturer FROM product_revisions r "
            "JOIN product_models m ON m.id = r.product_model_id JOIN manufacturers mf ON mf.id = m.manufacturer_id "
            "WHERE r.id = ?", (inst["product_revision_id"],)).fetchone())
        inspections = db.rows(conn.execute(
            "SELECT * FROM inspections WHERE product_instance_id = ? ORDER BY started_at DESC", (inst["id"],)).fetchall())
        findings = db.rows(conn.execute(
            "SELECT f.*, s.mode FROM findings f JOIN inspections s ON s.id = f.inspection_id "
            "WHERE f.product_instance_id = ? ORDER BY f.created_at DESC", (inst["id"],)).fetchall())
        ids = [inst["id"]] + [i["id"] for i in inspections] + [f["id"] for f in findings]
        marks = ",".join("?" * len(ids))
        activity = db.rows(conn.execute(
            f"SELECT * FROM activity_events WHERE entity_id IN ({marks}) OR json_extract(metadata,'$.inspection_id') "
            f"IN ({marks}) ORDER BY created_at DESC LIMIT 200", ids + ids).fetchall())
    return {"instance": inst, "revision": rev, "inspections": inspections, "findings": findings, "activity": activity}


# ---------------------------------------------------------------- packages --

@app.get("/api/packages")
def list_packages() -> list[dict[str, Any]]:
    out = []
    with db.read() as conn:
        for pkg in discover_packages(settings.packages_dir):
            summary = validate_package(pkg).summary()
            loaded = db.row(conn.execute(
                "SELECT id, content_hash, created_at FROM engineering_packages WHERE source_dir = ? "
                "ORDER BY created_at DESC LIMIT 1", (pkg.name,)).fetchone())
            summary["loaded"] = bool(loaded)
            summary["loaded_at"] = loaded["created_at"] if loaded else None
            summary["loaded_matches_disk"] = bool(loaded and loaded["content_hash"] == summary["content_hash"])
            out.append(summary)
    return out


@app.post("/api/packages/{package_dir}/load")
def load_package(package_dir: str, body: Actor) -> dict[str, Any]:
    try:
        path = catalog.find_package_dir(package_dir)
    except FileNotFoundError:
        raise HTTPException(404, "Package not found")
    try:
        return catalog.load_package(path, actor=body.actor)
    except catalog.PackageInvalid as exc:
        raise HTTPException(422, {"message": "Package failed validation", "errors": exc.report.errors})
    except catalog.PackageConflict as exc:
        raise HTTPException(409, str(exc))


# ------------------------------------------------------------- inspections --

def inspection_state(conn, inspection_id: str) -> dict[str, Any]:
    insp = db.row(conn.execute("SELECT * FROM inspections WHERE id = ?", (inspection_id,)).fetchone())
    if not insp:
        raise HTTPException(404, "Inspection not found")
    items = db.rows(conn.execute("SELECT * FROM inspection_items WHERE inspection_id = ? ORDER BY sort",
                                 (inspection_id,)).fetchall())
    evidence = db.rows(conn.execute("SELECT * FROM evidence WHERE inspection_id = ? ORDER BY created_at",
                                    (inspection_id,)).fetchall())
    assessments = db.rows(conn.execute(
        "SELECT a.* FROM evidence_assessments a JOIN evidence e ON e.id = a.evidence_id WHERE e.inspection_id = ? "
        "ORDER BY a.created_at", (inspection_id,)).fetchall())
    latest: dict[str, dict] = {}
    for a in assessments:
        latest[a["evidence_id"]] = a
    for e in evidence:
        e["url"] = f"/api/evidence/{e['id']}/file"
        e["assessment"] = latest.get(e["id"])
    by_item: dict[str, list] = {}
    for e in evidence:
        if e["inspection_item_id"]:
            by_item.setdefault(e["inspection_item_id"], []).append(e)
    for it in items:
        it["evidence"] = by_item.get(it["id"], [])
    findings = db.rows(conn.execute("SELECT * FROM findings WHERE inspection_id = ? ORDER BY created_at",
                                    (inspection_id,)).fetchall())
    for f in findings:
        f["evidence"] = [e for e in evidence if e["finding_id"] == f["id"]]
        f["corrective_action"] = db.row(conn.execute(
            "SELECT * FROM corrective_actions WHERE finding_id = ? ORDER BY created_at DESC LIMIT 1",
            (f["id"],)).fetchone())
    instance = db.row(conn.execute("SELECT * FROM product_instances WHERE id = ?",
                                   (insp["product_instance_id"],)).fetchone())
    reviews = db.rows(conn.execute("SELECT * FROM reviews WHERE inspection_id = ? ORDER BY created_at",
                                   (inspection_id,)).fetchall())
    activity = db.rows(conn.execute(
        "SELECT * FROM activity_events WHERE entity_id = ? OR json_extract(metadata,'$.inspection_id') = ? "
        "OR entity_id IN (SELECT id FROM inspection_items WHERE inspection_id = ?) ORDER BY created_at",
        (inspection_id, inspection_id, inspection_id)).fetchall())
    required = [i for i in items if i["required"]]
    return {
        "inspection": insp, "instance": instance, "revision_id": insp["product_revision_id"],
        "items": items, "findings": findings, "reviews": reviews, "activity": activity,
        "component_status": workflow.component_statuses(items, findings),
        "progress": {
            "total": len(items), "done": sum(i["status"] in workflow.FINAL_ITEM for i in items),
            "required_total": len(required), "required_done": sum(i["status"] in workflow.FINAL_ITEM for i in required),
        },
        "readiness": workflow.readiness(conn, inspection_id),
    }


@app.post("/api/inspections")
def start_inspection(body: StartInspection) -> dict[str, Any]:
    with db.tx() as conn:
        result = workflow.start_inspection(conn, body.serial_number, body.inspector, body.mode)
    with db.read() as conn:
        return {**result, "state": inspection_state(conn, result["inspection_id"])}


INSPECTION_LIST_SQL = (
    "SELECT s.*, i.serial_number, m.name AS product_name, r.revision, "
    "COALESCE(json_extract(p.manifest, '$.industry'), 'General') AS industry, "
    "json_extract(p.manifest, '$.asset_category') AS asset_category, "
    "(SELECT COUNT(*) FROM findings f WHERE f.inspection_id = s.id AND f.status NOT IN ('closed','void')) "
    "AS open_findings FROM inspections s JOIN product_instances i ON i.id = s.product_instance_id "
    "JOIN product_revisions r ON r.id = s.product_revision_id JOIN product_models m ON m.id = r.product_model_id "
    "JOIN engineering_packages p ON p.id = r.engineering_package_id")


@app.get("/api/inspections")
def list_inspections(status: str | None = None, industry: str | None = None) -> list[dict[str, Any]]:
    where, args = [], []
    if status:
        where.append("s.status = ?")
        args.append(status)
    if industry:
        where.append("COALESCE(json_extract(p.manifest, '$.industry'), 'General') = ?")
        args.append(industry)
    sql = INSPECTION_LIST_SQL + (" WHERE " + " AND ".join(where) if where else "")
    with db.read() as conn:
        return db.rows(conn.execute(sql + " ORDER BY s.updated_at DESC", args).fetchall())


@app.get("/api/dashboard")
def dashboard(industry: str | None = None) -> dict[str, Any]:
    """Cross-industry metrics computed from the same inspection records (one data model for every asset type)."""
    with db.read() as conn:
        insp = db.rows(conn.execute(INSPECTION_LIST_SQL).fetchall())
        industries = sorted({i["industry"] for i in insp} | {
            (r["manifest"] or {}).get("industry") or "General" for r in
            db.rows(conn.execute("SELECT manifest FROM engineering_packages").fetchall())})
        if industry:
            insp = [i for i in insp if i["industry"] == industry]
        ids = [i["id"] for i in insp]
        marks = ",".join("?" * len(ids)) or "''"
        items = db.rows(conn.execute(
            f"SELECT inspection_id, component_id, status FROM inspection_items WHERE inspection_id IN ({marks})",
            ids).fetchall())
        findings = db.rows(conn.execute(
            f"SELECT f.*, s.mode FROM findings f JOIN inspections s ON s.id = f.inspection_id "
            f"WHERE f.inspection_id IN ({marks})", ids).fetchall())
    count = lambda rows, key: {k: sum(1 for r in rows if r[key] == k) for k in sorted({r[key] for r in rows})}
    # A component counts as inspected only when every one of its requirements has a final disposition.
    per_comp: dict[tuple[str, str], list[str]] = {}
    for i in items:
        per_comp.setdefault((i["inspection_id"], i["component_id"]), []).append(i["status"])
    comp_done = {k for k, sts in per_comp.items() if all(st in workflow.FINAL_ITEM for st in sts)}
    comp_all = set(per_comp)
    return {
        "industries": industries,
        "filter": industry or "All",
        "totals": {
            "inspections": len(insp),
            "live": sum(1 for i in insp if i["mode"] == "live"),
            "demo": sum(1 for i in insp if i["mode"] == "demo"),
            "pending": sum(1 for i in insp if i["status"] in ("in_progress", "changes_requested")),
            "requires_review": sum(1 for i in insp if i["status"] == "submitted"),
            "approved": sum(1 for i in insp if i["status"] == "approved"),
            "components_inspected": len(comp_done),
            "components_total": len(comp_all),
            "findings": len(findings),
            "open_findings": sum(1 for f in findings if f["status"] in workflow.OPEN_FINDING),
        },
        "by_industry": count(insp, "industry"),
        "by_asset": count(insp, "product_name"),
        "by_status": count(insp, "status"),
        "findings_by_severity": count(findings, "severity"),
        "recent": insp[:15],
    }


@app.get("/api/inspections/{inspection_id}")
def get_inspection(inspection_id: str) -> dict[str, Any]:
    with db.read() as conn:
        return inspection_state(conn, inspection_id)


@app.post("/api/inspections/{inspection_id}/items/{item_id}/decision")
def decide(inspection_id: str, item_id: str, body: Decision) -> dict[str, Any]:
    with db.tx() as conn:
        workflow.decide_item(conn, inspection_id, item_id, decision=body.decision, actor=body.actor.strip(),
                             observation=body.observation, manual_confirmed=body.manual_confirmed,
                             override_note=body.override_note,
                             finding=body.finding.model_dump() if body.finding else None)
    with db.read() as conn:
        return inspection_state(conn, inspection_id)


@app.post("/api/inspections/{inspection_id}/submit")
def submit(inspection_id: str, body: Actor) -> dict[str, Any]:
    with db.tx() as conn:
        workflow.submit(conn, inspection_id, body.actor.strip())
    with db.read() as conn:
        return inspection_state(conn, inspection_id)


@app.post("/api/inspections/{inspection_id}/review")
def review(inspection_id: str, body: ReviewIn) -> dict[str, Any]:
    with db.tx() as conn:
        workflow.review(conn, inspection_id, reviewer=body.reviewer.strip(), decision=body.decision,
                        comments=body.comments, item_ids=body.item_ids)
    with db.read() as conn:
        return inspection_state(conn, inspection_id)


# ---------------------------------------------------------------- evidence --

def _form_name(value: str) -> str:
    value = (value or "").strip()
    if not value:
        raise HTTPException(422, "actor is required")
    return value[:80]


async def _read_image(file: UploadFile) -> tuple[bytes, dict[str, Any]]:
    """Decode/re-encode and run image checks off the event loop (CPU-bound for phone photos)."""
    raw = await file.read()
    if len(raw) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(413, f"Image larger than {settings.max_upload_mb} MB")

    def work():
        jpeg, img = ai.normalize_image(raw)
        return jpeg, ai.image_checks(img)

    try:
        return await run_in_threadpool(work)
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, ValueError):
        raise HTTPException(415, "Uploaded file is not a supported image (use JPEG or PNG)")


def _store(evidence_id: str, folder: str, jpeg: bytes) -> str:
    rel = Path(folder) / f"{evidence_id}.jpg"
    path = settings.evidence_dir / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(jpeg)
    return rel.as_posix()


def _assessment_context(conn, evidence_id: str, worker_note: str | None) -> dict[str, Any]:
    e = db.row(conn.execute("SELECT * FROM evidence WHERE id = ?", (evidence_id,)).fetchone())
    item = db.row(conn.execute("SELECT * FROM inspection_items WHERE id = ?", (e["inspection_item_id"],)).fetchone())
    insp = db.row(conn.execute("SELECT * FROM inspections WHERE id = ?", (item["inspection_id"],)).fetchone())
    c = db.row(conn.execute("SELECT * FROM components WHERE product_revision_id = ? AND id = ?",
                            (insp["product_revision_id"], item["component_id"])).fetchone())
    # Rows imported before the 'definition' column existed fall back to the base columns.
    comp = {"component_id": c["id"], "name": c["name"], "part_number": c["part_number"], "quantity": c["quantity"],
            "category": c["category"], "description": c["description"], **(c.get("definition") or {})}
    rev = db.row(conn.execute("SELECT r.procedure, p.manifest FROM product_revisions r JOIN engineering_packages p "
                              "ON p.id = r.engineering_package_id WHERE r.id = ?",
                              (insp["product_revision_id"],)).fetchone())
    return ai.build_context(
        manifest=rev["manifest"], procedure=rev["procedure"], component=comp,
        requirement={"requirement_id": item["requirement_id"], **item["requirement_snapshot"]},
        serial_number=insp["product_instance_id"], worker_note=worker_note, image_checks=e["image_checks"],
        inspection_id=insp["id"])


def _store_assessment(evidence_id: str, inspection_id: str, outcome: ai.AssessmentOutcome,
                      origin: str = "live", captured_at: str | None = None) -> dict[str, Any]:
    assessment = {"id": db.new_id("asmt"), "evidence_id": evidence_id, "provider": outcome.provider,
                  "model": outcome.model, "status": outcome.status, "result": outcome.result,
                  "error": outcome.error, "latency_ms": outcome.latency_ms, "created_at": db.now(),
                  "origin": origin, "captured_at": captured_at}
    with db.tx() as conn:
        conn.execute("INSERT INTO evidence_assessments (id, evidence_id, provider, model, status, result, error, "
                     "latency_ms, created_at, origin, captured_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                     (assessment["id"], evidence_id, outcome.provider, outcome.model, outcome.status,
                      db.dumps(outcome.result) if outcome.result else None, outcome.error, outcome.latency_ms,
                      assessment["created_at"], origin, captured_at))
        item_id = conn.execute("SELECT inspection_item_id FROM evidence WHERE id = ?", (evidence_id,)).fetchone()[0]
        workflow.apply_assessment(conn, item_id, assessment)
        db.log_event(conn, "evidence", evidence_id, f"assessment_{outcome.status}", "ai",
                     {"inspection_id": inspection_id, "origin": origin,
                      "provider": outcome.provider, "model": outcome.model, "latency_ms": outcome.latency_ms,
                      "recommended_action": (outcome.result or {}).get("recommended_action"), "error": outcome.error})
    return assessment


def _run_assessment(evidence_id: str, worker_note: str | None) -> dict[str, Any]:
    with db.read() as conn:
        ctx = _assessment_context(conn, evidence_id, worker_note)
        path = settings.evidence_dir / db.row(conn.execute("SELECT storage_path FROM evidence WHERE id = ?",
                                                           (evidence_id,)).fetchone())["storage_path"]
    outcome = ai.get_provider().assess(path.read_bytes(), ctx)  # no DB lock held during the model call
    return _store_assessment(evidence_id, ctx["inspection_id"], outcome)


@app.post("/api/inspections/{inspection_id}/items/{item_id}/evidence")
async def upload_evidence(inspection_id: str, item_id: str, file: UploadFile = File(...),
                          actor: str = Form(...), note: str | None = Form(None),
                          assess: bool = Form(True)) -> dict[str, Any]:
    actor = _form_name(actor)
    with db.read() as conn:  # validate before touching the disk (404/409 instead of FK errors)
        workflow._require_editable(workflow._inspection(conn, inspection_id))
        workflow._item(conn, inspection_id, item_id)
    jpeg, checks = await _read_image(file)
    evidence_id = db.new_id("ev")
    storage_path = _store(evidence_id, inspection_id, jpeg)
    try:
        with db.tx() as conn:
            conn.execute("INSERT INTO evidence VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                         (evidence_id, inspection_id, item_id, None, "inspection", storage_path, "image/jpeg",
                          note, db.dumps(checks), actor, db.now()))
            workflow.record_evidence(conn, inspection_id, item_id, evidence_id, actor)
    except Exception:
        (settings.evidence_dir / storage_path).unlink(missing_ok=True)  # no orphan files
        raise
    assessment = await run_in_threadpool(_run_assessment, evidence_id, note) if assess else None
    with db.read() as conn:
        return {"evidence_id": evidence_id, "image_checks": checks, "assessment": assessment,
                "state": inspection_state(conn, inspection_id)}


@app.post("/api/inspections/{inspection_id}/items/{item_id}/demo-evidence")
async def use_demo_evidence(inspection_id: str, item_id: str, body: UseDemoEvidence) -> dict[str, Any]:
    """Attach a prepared demonstration photo (demo-mode inspections only).

    The AI result is either a real call made now, or a precomputed result that was produced earlier by a
    real model call and is stored with origin='precomputed' and its capture date. Nothing is fabricated."""
    with db.read() as conn:
        insp = workflow._inspection(conn, inspection_id)
        workflow._require_editable(insp)
        item = workflow._item(conn, inspection_id, item_id)
        if insp.get("mode") != "demo":
            raise WorkflowError("Prepared demo photos can only be used in a demo inspection", 409)
        source_dir = conn.execute("SELECT p.source_dir FROM product_revisions r JOIN engineering_packages p "
                                  "ON p.id = r.engineering_package_id WHERE r.id = ?",
                                  (insp["product_revision_id"],)).fetchone()[0]
    found = catalog.demo_evidence_entry(source_dir, body.demo_id)
    if not found:
        raise HTTPException(404, "Demo evidence not found")
    path, entry = found
    if entry["requirement_id"] != item["requirement_id"]:
        raise WorkflowError("This demo photo belongs to a different requirement", 422)

    def prepare():
        jpeg, img = ai.normalize_image(path.read_bytes())
        return jpeg, ai.image_checks(img)

    jpeg, checks = await run_in_threadpool(prepare)
    evidence_id = db.new_id("ev")
    storage_path = _store(evidence_id, inspection_id, jpeg)
    note = f"DEMO PHOTO: {entry.get('caption') or entry['id']}"
    try:
        with db.tx() as conn:
            conn.execute("INSERT INTO evidence VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                         (evidence_id, inspection_id, item_id, None, "demo", storage_path, "image/jpeg",
                          note, db.dumps(checks), body.actor, db.now()))
            workflow.record_evidence(conn, inspection_id, item_id, evidence_id, body.actor)
    except Exception:
        (settings.evidence_dir / storage_path).unlink(missing_ok=True)
        raise

    pre = entry.get("precomputed_assessment")
    assessment = None
    if body.live_ai and ai.get_provider().available()[0]:
        assessment = await run_in_threadpool(_run_assessment, evidence_id, note)
    if (assessment is None or assessment["status"] != "completed") and pre:
        outcome = ai.AssessmentOutcome(pre.get("provider", "anthropic"), pre.get("model"), "completed",
                                       ai.AssessmentResult.model_validate(pre["result"]).model_dump(), None,
                                       int(pre.get("latency_ms") or 0))
        assessment = await run_in_threadpool(_store_assessment, evidence_id, inspection_id, outcome,
                                             "precomputed", pre.get("captured_at"))
    if assessment is None:
        assessment = await run_in_threadpool(
            _store_assessment, evidence_id, inspection_id,
            ai.AssessmentOutcome("none", None, "unavailable", None,
                                 "No live AI available and no precomputed result for this demo photo.", 0))
    with db.read() as conn:
        return {"evidence_id": evidence_id, "image_checks": checks, "assessment": assessment,
                "state": inspection_state(conn, inspection_id)}


@app.post("/api/evidence/{evidence_id}/assess")
def reassess(evidence_id: str) -> dict[str, Any]:
    with db.read() as conn:
        e = db.row(conn.execute("SELECT * FROM evidence WHERE id = ?", (evidence_id,)).fetchone())
        if not e or not e["inspection_item_id"]:
            raise HTTPException(404, "Inspection evidence not found")
        workflow._require_editable(workflow._inspection(conn, e["inspection_id"]))
    return _run_assessment(evidence_id, e["note"])


@app.get("/api/evidence/{evidence_id}/file")
def evidence_file(evidence_id: str):
    with db.read() as conn:
        e = db.row(conn.execute("SELECT storage_path, content_type FROM evidence WHERE id = ?",
                                (evidence_id,)).fetchone())
    if not e:
        raise HTTPException(404, "Evidence not found")
    path = (settings.evidence_dir / e["storage_path"]).resolve()
    if settings.evidence_dir.resolve() not in path.parents or not path.exists():
        raise HTTPException(404, "Evidence file missing")
    return FileResponse(path, media_type=e["content_type"])


# ---------------------------------------------------------------- findings --

@app.get("/api/findings")
def list_findings(status: str | None = None) -> list[dict[str, Any]]:
    sql = ("SELECT f.*, c.name AS component_name, c.part_number, s.product_revision_id, s.mode FROM findings f "
           "JOIN inspections s ON s.id = f.inspection_id "
           "LEFT JOIN components c ON c.id = f.component_id AND c.product_revision_id = s.product_revision_id")
    args: tuple = ()
    if status:
        sql += " WHERE f.status = ?"
        args = (status,)
    with db.read() as conn:
        findings = db.rows(conn.execute(sql + " ORDER BY f.updated_at DESC", args).fetchall())
        for f in findings:
            f["corrective_action"] = db.row(conn.execute(
                "SELECT * FROM corrective_actions WHERE finding_id = ? ORDER BY created_at DESC LIMIT 1",
                (f["id"],)).fetchone())
            f["evidence"] = db.rows(conn.execute(
                "SELECT id, kind, note, created_at, submitted_by FROM evidence WHERE finding_id = ? "
                "OR (inspection_item_id = ? AND kind IN ('inspection','demo')) ORDER BY created_at",
                (f["id"], f["inspection_item_id"])).fetchall())
            for e in f["evidence"]:
                e["url"] = f"/api/evidence/{e['id']}/file"
    return findings


@app.post("/api/findings/{finding_id}/transition")
def finding_transition(finding_id: str, body: FindingTransition) -> dict[str, Any]:
    with db.tx() as conn:
        return workflow.transition_finding(conn, finding_id, to=body.to, actor=body.actor.strip(),
                                           assigned_to=body.assigned_to, note=body.note)


@app.post("/api/findings/{finding_id}/evidence")
async def finding_evidence(finding_id: str, file: UploadFile = File(...), actor: str = Form(...),
                           kind: Literal["corrective_before", "corrective_after"] = Form(...),
                           note: str | None = Form(None)) -> dict[str, Any]:
    with db.read() as conn:
        f = db.row(conn.execute("SELECT * FROM findings WHERE id = ?", (finding_id,)).fetchone())
    if not f:
        raise HTTPException(404, "Finding not found")
    if f["status"] in ("closed", "void"):
        raise HTTPException(409, "Finding is closed")
    actor = _form_name(actor)
    jpeg, checks = await _read_image(file)
    evidence_id = db.new_id("ev")
    storage_path = _store(evidence_id, f"findings/{finding_id}", jpeg)
    with db.tx() as conn:
        conn.execute("INSERT INTO evidence VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                     (evidence_id, f["inspection_id"], None, finding_id, kind, storage_path, "image/jpeg", note,
                      db.dumps(checks), actor, db.now()))
        db.log_event(conn, "finding", finding_id, f"evidence_{kind}", actor,
                     {"evidence_id": evidence_id, "inspection_id": f["inspection_id"]})
    return {"evidence_id": evidence_id, "url": f"/api/evidence/{evidence_id}/file"}


@app.get("/api/activity")
def activity(limit: int = 100) -> list[dict[str, Any]]:
    with db.read() as conn:
        return db.rows(conn.execute("SELECT * FROM activity_events ORDER BY created_at DESC LIMIT ?",
                                    (min(limit, 500),)).fetchall())


# ------------------------------------------------------------ static files --

app.mount("/package-files", StaticFiles(directory=settings.packages_dir), name="package-files")

if settings.web_dist_dir.exists():
    app.mount("/assets", StaticFiles(directory=settings.web_dist_dir / "assets"), name="web-assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        candidate = (settings.web_dist_dir / full_path).resolve()
        if full_path and candidate.is_file() and settings.web_dist_dir.resolve() in candidate.parents:
            return FileResponse(candidate)
        if full_path.startswith("api/"):
            raise HTTPException(404, "Not found")
        return FileResponse(settings.web_dist_dir / "index.html")
