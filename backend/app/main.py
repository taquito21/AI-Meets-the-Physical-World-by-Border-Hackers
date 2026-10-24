"""FastAPI application: REST API (OpenAPI at /docs), package files, evidence files and the web client."""
from __future__ import annotations

import base64
import hmac
import threading
from contextlib import asynccontextmanager
from typing import Annotated, Any, Literal

from fastapi import FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, StringConstraints
from starlette.concurrency import run_in_threadpool

from . import ai, catalog, db, workflow
from .blobs import blobs
from .config import settings
from .packages import discover_packages, validate_package
from .workflow import WorkflowError

API_VERSION = "0.1.0"


_ready = False
_ready_lock = threading.Lock()


def _local_db_missing() -> bool:
    return settings.data_backend == "local" and not settings.db_path.exists()


def ensure_ready() -> None:
    """Create the schema (local) or check it exists (Supabase), and load packages. Idempotent; re-runs if a
    serverless /tmp was wiped."""
    global _ready
    if _ready and not _local_db_missing():
        return
    with _ready_lock:  # concurrent first requests on a cold instance initialize once
        if _ready and not _local_db_missing():
            return
        db.init_db()
        if settings.data_backend == "local":
            settings.evidence_dir.mkdir(parents=True, exist_ok=True)
        for result in catalog.bootstrap():
            print(f"[packages] {result.get('status')}: {result.get('revision_id') or result.get('package_dir')} "
                  f"{result.get('error', '')}")
        _ready = True


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        ensure_ready()
    except db.SchemaMissing as exc:  # keep serving; requests answer 503 with the fix until the schema exists
        print(f"[db] {exc}", flush=True)
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
    if not _ready or _local_db_missing():
        try:
            await run_in_threadpool(ensure_ready)
        except db.SchemaMissing as exc:
            return JSONResponse(status_code=503, content={"detail": str(exc)})
    return await call_next(request)


@app.exception_handler(WorkflowError)
async def workflow_error_handler(_: Request, exc: WorkflowError):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message, "issues": exc.details})


@app.exception_handler(db.Conflict)
async def conflict_handler(_: Request, exc: db.Conflict):
    return JSONResponse(status_code=409, content={"detail": "This record was just changed by someone else. "
                                                            "Reload and try again.", "issues": []})


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
            "storage": settings.storage_mode, "data_backend": settings.data_backend,
            "ai": {"provider": provider.name, "available": available, "detail": detail}}


def _count_by(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for r in rows:
        out[r[key]] = out.get(r[key], 0) + 1
    return out


def _latest_per(rows: list[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    """Last row per key (rows must be in ascending order)."""
    return {r[key]: r for r in rows}


# ----------------------------------------------------------------- catalog --

@app.get("/api/products")
def list_products() -> list[dict[str, Any]]:
    index = catalog.revision_index()
    comp_counts = _count_by(db.select("components", columns="product_revision_id"), "product_revision_id")
    req_counts = _count_by(db.select("inspection_requirements", columns="product_revision_id"), "product_revision_id")
    instances = db.select("product_instances", columns="id,serial_number,metadata,product_revision_id",
                          order="serial_number")
    last: dict[str, dict[str, Any]] = {}
    for s in db.select("inspections", columns="product_instance_id,status,mode", order="-started_at"):
        last.setdefault(s["product_instance_id"], s)
    revs = []
    for r in sorted(index.values(), key=lambda r: (r["product_name"] or "", r["revision"])):
        manifest = r.pop("manifest")
        r["component_count"] = comp_counts.get(r["id"], 0)
        r["requirement_count"] = req_counts.get(r["id"], 0)
        r["instances"] = [{"serial_number": i["serial_number"], "metadata": i["metadata"],
                           "last_inspection_status": last.get(i["id"], {}).get("status"),
                           "last_inspection_mode": last.get(i["id"], {}).get("mode")}
                          for i in instances if i["product_revision_id"] == r["id"]]
        r["demonstration_package"] = bool(manifest.get("demonstration_package"))
        r["has_3d"] = bool(manifest.get("assembly_file"))
        r["demo_evidence_count"] = len(catalog.demo_evidence(r["source_dir"]))
        revs.append(r)
    return revs


@app.get("/api/revisions/{revision_id}")
def get_revision(revision_id: str) -> dict[str, Any]:
    rev = catalog.get_revision(revision_id)
    if not rev:
        raise HTTPException(404, "Revision not found")
    return rev


@app.get("/api/instances/{serial_number}")
def product_passport(serial_number: str) -> dict[str, Any]:
    inst = db.first("product_instances", {"serial_number": serial_number})
    if not inst:
        raise HTTPException(404, "Product instance not found")
    r = catalog.revision_index().get(inst["product_revision_id"], {})
    rev = {"id": r.get("id"), "revision": r.get("revision"), "product_name": r.get("product_name"),
           "manufacturer": r.get("manufacturer")}
    inspections = db.select("inspections", {"product_instance_id": inst["id"]}, order="-started_at")
    modes = {i["id"]: i["mode"] for i in inspections}
    findings = db.select("findings", {"product_instance_id": inst["id"]}, order="-created_at")
    findings = [{**f, "mode": modes.get(f["inspection_id"])} for f in findings if f["inspection_id"] in modes]
    ids = [inst["id"]] + [i["id"] for i in inspections] + [f["id"] for f in findings]
    events = {e["id"]: e for e in db.select("activity_events", {"entity_id": ids}, order="-created_at", limit=200)}
    events.update({e["id"]: e for e in db.select("activity_events", {"inspection_id": list(modes)},
                                                 order="-created_at", limit=200)})
    activity = sorted(events.values(), key=lambda e: db.ts_key(e["created_at"]), reverse=True)[:200]
    return {"instance": inst, "revision": rev, "inspections": inspections, "findings": findings, "activity": activity}


# ---------------------------------------------------------------- packages --

@app.get("/api/packages")
def list_packages() -> list[dict[str, Any]]:
    loaded_by_dir: dict[str, dict[str, Any]] = {}
    for p in db.select("engineering_packages", columns="source_dir,content_hash,created_at", order="-created_at"):
        loaded_by_dir.setdefault(p["source_dir"], p)
    out = []
    for pkg in discover_packages(settings.packages_dir):
        summary = validate_package(pkg).summary()
        loaded = loaded_by_dir.get(pkg.name)
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

def inspection_state(inspection_id: str) -> dict[str, Any]:
    bundle = workflow.load_bundle(inspection_id)
    insp, items, findings = bundle["inspection"], bundle["items"], bundle["findings"]
    latest = _latest_per(bundle["assessments"], "evidence_id")
    evidence = [{**e, "url": f"/api/evidence/{e['id']}/file", "assessment": latest.get(e["id"])}
                for e in bundle["evidence"]]
    by_item: dict[str, list] = {}
    for e in evidence:
        if e["inspection_item_id"]:
            by_item.setdefault(e["inspection_item_id"], []).append(e)
    items = [{**it, "evidence": by_item.get(it["id"], [])} for it in items]
    actions = _latest_per(db.select("corrective_actions", {"finding_id": [f["id"] for f in findings]},
                                    order=["created_at", "id"]), "finding_id")
    findings_out = [{**f, "evidence": [e for e in evidence if e["finding_id"] == f["id"]],
                     "corrective_action": actions.get(f["id"])} for f in findings]
    instance = db.first("product_instances", {"id": insp["product_instance_id"]})
    reviews = db.select("reviews", {"inspection_id": inspection_id}, order=["created_at", "id"])
    activity = db.select("activity_events", {"inspection_id": inspection_id}, order=["created_at", "id"])
    required = [i for i in items if i["required"]]
    return {
        "inspection": insp, "instance": instance, "revision_id": insp["product_revision_id"],
        "items": items, "findings": findings_out, "reviews": reviews, "activity": activity,
        "component_status": workflow.component_statuses(items, findings),
        "progress": {
            "total": len(items), "done": sum(i["status"] in workflow.FINAL_ITEM for i in items),
            "required_total": len(required), "required_done": sum(i["status"] in workflow.FINAL_ITEM for i in required),
        },
        "readiness": workflow.readiness(inspection_id, bundle),
    }


@app.post("/api/inspections")
def start_inspection(body: StartInspection) -> dict[str, Any]:
    result = workflow.start_inspection(body.serial_number, body.inspector, body.mode)
    return {**result, "state": inspection_state(result["inspection_id"])}


def _inspection_rows(status: str | None = None, industry: str | None = None,
                     index: dict[str, dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """Inspections with product, serial number, industry and open-finding count, newest activity first."""
    index = index if index is not None else catalog.revision_index()
    serials = {i["id"]: i["serial_number"] for i in db.select("product_instances", columns="id,serial_number")}
    open_counts = _count_by(db.select("findings", {"status": sorted(workflow.OPEN_FINDING)}, columns="inspection_id"),
                            "inspection_id")
    out = []
    for s in db.select("inspections", {"status": status} if status else None, order="-updated_at"):
        rev = index.get(s["product_revision_id"], {})
        row = {**s, "serial_number": serials.get(s["product_instance_id"]), "product_name": rev.get("product_name"),
               "revision": rev.get("revision"), "industry": rev.get("industry") or "General",
               "asset_category": rev.get("asset_category"), "open_findings": open_counts.get(s["id"], 0)}
        if not industry or row["industry"] == industry:
            out.append(row)
    return out


@app.get("/api/inspections")
def list_inspections(status: str | None = None, industry: str | None = None) -> list[dict[str, Any]]:
    return _inspection_rows(status, industry)


@app.get("/api/dashboard")
def dashboard(industry: str | None = None) -> dict[str, Any]:
    """Cross-industry metrics computed from the same inspection records (one data model for every asset type)."""
    index = catalog.revision_index()
    insp = _inspection_rows(index=index)
    industries = sorted({i["industry"] for i in insp} | {r["industry"] for r in index.values()})
    if industry:
        insp = [i for i in insp if i["industry"] == industry]
    ids = [i["id"] for i in insp]
    scope = {"inspection_id": ids} if industry else None  # unfiltered: read everything, no long IN list
    items = db.select("inspection_items", scope, columns="inspection_id,component_id,status")
    modes = {i["id"]: i["mode"] for i in insp}
    findings = [{**f, "mode": modes[f["inspection_id"]]} for f in db.select("findings", scope)
                if f["inspection_id"] in modes]
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
    return inspection_state(inspection_id)


@app.post("/api/inspections/{inspection_id}/items/{item_id}/decision")
def decide(inspection_id: str, item_id: str, body: Decision) -> dict[str, Any]:
    workflow.decide_item(inspection_id, item_id, decision=body.decision, actor=body.actor.strip(),
                         observation=body.observation, manual_confirmed=body.manual_confirmed,
                         override_note=body.override_note,
                         finding=body.finding.model_dump() if body.finding else None)
    return inspection_state(inspection_id)


@app.post("/api/inspections/{inspection_id}/submit")
def submit(inspection_id: str, body: Actor) -> dict[str, Any]:
    workflow.submit(inspection_id, body.actor.strip())
    return inspection_state(inspection_id)


@app.post("/api/inspections/{inspection_id}/review")
def review(inspection_id: str, body: ReviewIn) -> dict[str, Any]:
    workflow.review(inspection_id, reviewer=body.reviewer.strip(), decision=body.decision,
                    comments=body.comments, item_ids=body.item_ids)
    return inspection_state(inspection_id)


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


def _save_evidence(row: dict[str, Any], jpeg: bytes, after_insert=None) -> None:
    """Store the photo, then its record; undo both if the record (or the follow-up step) fails."""
    blobs.put(row["storage_path"], jpeg, "image/jpeg")
    try:
        db.insert("evidence", row)
        if after_insert:
            after_insert()
    except Exception:
        db.delete("evidence", {"id": row["id"]})
        blobs.delete([row["storage_path"]])  # no orphan files
        raise


def _evidence_row(evidence_id: str, inspection_id: str, item_id: str | None, finding_id: str | None, kind: str,
                  storage_path: str, note: str | None, checks: dict[str, Any], actor: str) -> dict[str, Any]:
    return {"id": evidence_id, "inspection_id": inspection_id, "inspection_item_id": item_id,
            "finding_id": finding_id, "kind": kind, "storage_path": storage_path, "content_type": "image/jpeg",
            "note": note, "image_checks": checks, "submitted_by": actor, "created_at": db.now()}


def _assessment_context(evidence_id: str, worker_note: str | None) -> dict[str, Any]:
    e = db.first("evidence", {"id": evidence_id})
    item = db.first("inspection_items", {"id": e["inspection_item_id"]})
    insp = db.first("inspections", {"id": item["inspection_id"]})
    c = db.first("components", {"product_revision_id": insp["product_revision_id"], "id": item["component_id"]})
    # Rows imported before the 'definition' column existed fall back to the base columns.
    comp = {"component_id": c["id"], "name": c["name"], "part_number": c["part_number"], "quantity": c["quantity"],
            "category": c["category"], "description": c["description"], **(c.get("definition") or {})}
    rev = db.first("product_revisions", {"id": insp["product_revision_id"]},
                   columns="procedure,engineering_package_id")
    manifest = db.first("engineering_packages", {"id": rev["engineering_package_id"]}, columns="manifest")["manifest"]
    return ai.build_context(
        manifest=manifest, procedure=rev["procedure"], component=comp,
        requirement={"requirement_id": item["requirement_id"], **item["requirement_snapshot"]},
        serial_number=insp["product_instance_id"], worker_note=worker_note, image_checks=e["image_checks"],
        inspection_id=insp["id"])


def _store_assessment(evidence_id: str, inspection_id: str, outcome: ai.AssessmentOutcome,
                      origin: str = "live", captured_at: str | None = None) -> dict[str, Any]:
    assessment = {"id": db.new_id("asmt"), "evidence_id": evidence_id, "provider": outcome.provider,
                  "model": outcome.model, "status": outcome.status, "result": outcome.result or None,
                  "error": outcome.error, "latency_ms": outcome.latency_ms, "created_at": db.now(),
                  "origin": origin, "captured_at": captured_at}
    db.insert("evidence_assessments", assessment)
    item_id = db.first("evidence", {"id": evidence_id}, columns="inspection_item_id")["inspection_item_id"]
    workflow.apply_assessment(item_id, assessment)
    db.log_event("evidence", evidence_id, f"assessment_{outcome.status}", "ai",
                 {"inspection_id": inspection_id, "origin": origin,
                  "provider": outcome.provider, "model": outcome.model, "latency_ms": outcome.latency_ms,
                  "recommended_action": (outcome.result or {}).get("recommended_action"), "error": outcome.error})
    return assessment


def _run_assessment(evidence_id: str, worker_note: str | None) -> dict[str, Any]:
    ctx = _assessment_context(evidence_id, worker_note)
    data = blobs.get(db.first("evidence", {"id": evidence_id}, columns="storage_path")["storage_path"])
    if data is None:
        raise HTTPException(404, "Evidence file missing")
    outcome = ai.get_provider().assess(data, ctx)
    return _store_assessment(evidence_id, ctx["inspection_id"], outcome)


@app.post("/api/inspections/{inspection_id}/items/{item_id}/evidence")
async def upload_evidence(inspection_id: str, item_id: str, file: UploadFile = File(...),
                          actor: str = Form(...), note: str | None = Form(None),
                          assess: bool = Form(True)) -> dict[str, Any]:
    actor = _form_name(actor)

    def validate():  # before touching storage (404/409 instead of FK errors)
        workflow._require_editable(workflow._inspection(inspection_id))
        workflow._item(inspection_id, item_id)

    await run_in_threadpool(validate)
    jpeg, checks = await _read_image(file)
    evidence_id = db.new_id("ev")
    row = _evidence_row(evidence_id, inspection_id, item_id, None, "inspection", f"{inspection_id}/{evidence_id}.jpg",
                        note, checks, actor)
    await run_in_threadpool(_save_evidence, row, jpeg,
                            lambda: workflow.record_evidence(inspection_id, item_id, evidence_id, actor))
    assessment = await run_in_threadpool(_run_assessment, evidence_id, note) if assess else None
    state = await run_in_threadpool(inspection_state, inspection_id)
    return {"evidence_id": evidence_id, "image_checks": checks, "assessment": assessment, "state": state}


@app.post("/api/inspections/{inspection_id}/items/{item_id}/demo-evidence")
async def use_demo_evidence(inspection_id: str, item_id: str, body: UseDemoEvidence) -> dict[str, Any]:
    """Attach a prepared demonstration photo (demo-mode inspections only).

    The AI result is either a real call made now, or a precomputed result that was produced earlier by a
    real model call and is stored with origin='precomputed' and its capture date. Nothing is fabricated."""
    def lookup():
        insp = workflow._inspection(inspection_id)
        workflow._require_editable(insp)
        item = workflow._item(inspection_id, item_id)
        if insp.get("mode") != "demo":
            raise WorkflowError("Prepared demo photos can only be used in a demo inspection", 409)
        rev = db.first("product_revisions", {"id": insp["product_revision_id"]}, columns="engineering_package_id")
        pkg = db.first("engineering_packages", {"id": rev["engineering_package_id"]}, columns="source_dir")
        return item, pkg["source_dir"]

    item, source_dir = await run_in_threadpool(lookup)
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
    note = f"DEMO PHOTO: {entry.get('caption') or entry['id']}"
    row = _evidence_row(evidence_id, inspection_id, item_id, None, "demo", f"{inspection_id}/{evidence_id}.jpg",
                        note, checks, body.actor)
    await run_in_threadpool(_save_evidence, row, jpeg,
                            lambda: workflow.record_evidence(inspection_id, item_id, evidence_id, body.actor))

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
    state = await run_in_threadpool(inspection_state, inspection_id)
    return {"evidence_id": evidence_id, "image_checks": checks, "assessment": assessment, "state": state}


@app.post("/api/evidence/{evidence_id}/assess")
def reassess(evidence_id: str) -> dict[str, Any]:
    e = db.first("evidence", {"id": evidence_id})
    if not e or not e["inspection_item_id"]:
        raise HTTPException(404, "Inspection evidence not found")
    workflow._require_editable(workflow._inspection(e["inspection_id"]))
    return _run_assessment(evidence_id, e["note"])


@app.get("/api/evidence/{evidence_id}/file")
def evidence_file(evidence_id: str):
    e = db.first("evidence", {"id": evidence_id}, columns="storage_path,content_type")
    if not e:
        raise HTTPException(404, "Evidence not found")
    data = blobs.get(e["storage_path"])
    if data is None:
        raise HTTPException(404, "Evidence file missing")
    # A photo never changes after upload (new photos get new ids), so the browser may keep it.
    return Response(data, media_type=e["content_type"], headers={"Cache-Control": "private, max-age=86400"})


# ---------------------------------------------------------------- findings --

@app.get("/api/findings")
def list_findings(status: str | None = None) -> list[dict[str, Any]]:
    findings = db.select("findings", {"status": status} if status else None, order="-updated_at")
    insps = {i["id"]: i for i in db.select("inspections", {"id": sorted({f["inspection_id"] for f in findings})},
                                           columns="id,product_revision_id,mode")}
    comps = {(c["product_revision_id"], c["id"]): c for c in db.select(
        "components", {"product_revision_id": sorted({i["product_revision_id"] for i in insps.values()})},
        columns="product_revision_id,id,name,part_number")}
    actions = _latest_per(db.select("corrective_actions", {"finding_id": [f["id"] for f in findings]},
                                    order=["created_at", "id"]), "finding_id")
    cols = "id,kind,note,created_at,submitted_by,finding_id,inspection_item_id"
    ev_by_finding: dict[str, list] = {}
    for e in db.select("evidence", {"finding_id": [f["id"] for f in findings]}, columns=cols):
        ev_by_finding.setdefault(e["finding_id"], []).append(e)
    ev_by_item: dict[str, list] = {}
    for e in db.select("evidence", {"inspection_item_id": sorted({f["inspection_item_id"] for f in findings
                                                                   if f["inspection_item_id"]}),
                                    "kind": ["inspection", "demo"]}, columns=cols):
        ev_by_item.setdefault(e["inspection_item_id"], []).append(e)
    out = []
    for f in findings:
        s = insps.get(f["inspection_id"])
        if not s:
            continue
        c = comps.get((s["product_revision_id"], f["component_id"]), {})
        evidence = ev_by_finding.get(f["id"], []) + ev_by_item.get(f["inspection_item_id"], [])
        evidence = sorted({e["id"]: e for e in evidence}.values(), key=lambda e: db.ts_key(e["created_at"]))
        out.append({**f, "component_name": c.get("name"), "part_number": c.get("part_number"),
                    "product_revision_id": s["product_revision_id"], "mode": s["mode"],
                    "corrective_action": actions.get(f["id"]),
                    "evidence": [{"id": e["id"], "kind": e["kind"], "note": e["note"], "created_at": e["created_at"],
                                  "submitted_by": e["submitted_by"], "url": f"/api/evidence/{e['id']}/file"}
                                 for e in evidence]})
    return out


@app.post("/api/findings/{finding_id}/transition")
def finding_transition(finding_id: str, body: FindingTransition) -> dict[str, Any]:
    return workflow.transition_finding(finding_id, to=body.to, actor=body.actor.strip(),
                                       assigned_to=body.assigned_to, note=body.note)


@app.post("/api/findings/{finding_id}/evidence")
async def finding_evidence(finding_id: str, file: UploadFile = File(...), actor: str = Form(...),
                           kind: Literal["corrective_before", "corrective_after"] = Form(...),
                           note: str | None = Form(None)) -> dict[str, Any]:
    f = await run_in_threadpool(db.first, "findings", {"id": finding_id})
    if not f:
        raise HTTPException(404, "Finding not found")
    if f["status"] in ("closed", "void"):
        raise HTTPException(409, "Finding is closed")
    actor = _form_name(actor)
    jpeg, checks = await _read_image(file)
    evidence_id = db.new_id("ev")
    row = _evidence_row(evidence_id, f["inspection_id"], None, finding_id, kind,
                        f"findings/{finding_id}/{evidence_id}.jpg", note, checks, actor)
    await run_in_threadpool(_save_evidence, row, jpeg)
    await run_in_threadpool(db.log_event, "finding", finding_id, f"evidence_{kind}", actor,
                            {"evidence_id": evidence_id, "inspection_id": f["inspection_id"]})
    return {"evidence_id": evidence_id, "url": f"/api/evidence/{evidence_id}/file"}


@app.get("/api/activity")
def activity(limit: int = 100) -> list[dict[str, Any]]:
    return db.select("activity_events", order=["-created_at", "-id"], limit=min(max(limit, 1), 500))


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
