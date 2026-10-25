"""FastAPI application: REST API (OpenAPI at /docs) and the built web client.

Every /api route except /api/health and /api/config needs a Supabase login (see auth.py). Access rules live in
workflow.py; this module only translates HTTP to those calls.
"""
from __future__ import annotations

import threading
from contextlib import asynccontextmanager
from datetime import date
from typing import Annotated, Any

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, Field, StringConstraints
from starlette.concurrency import run_in_threadpool

from . import ai, db, face, i18n, media, rag, workflow
from .auth import current_user, employer
from .blobs import blobs
from .config import settings
from .workflow import WorkflowError

API_VERSION = "0.2.0"

User = Annotated[dict[str, Any], Depends(current_user)]
Employer = Annotated[dict[str, Any], Depends(employer)]

_ready = False
_ready_lock = threading.Lock()


def _local_db_missing() -> bool:
    return settings.data_backend == "local" and not settings.db_path.exists()


def ensure_ready() -> None:
    """Create the schema (local) or check it exists (Supabase). Idempotent."""
    global _ready
    if _ready and not _local_db_missing():
        return
    with _ready_lock:  # concurrent first requests on a cold instance initialize once
        if _ready and not _local_db_missing():
            return
        db.init_db()
        _ready = True


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        ensure_ready()
    except db.SchemaMissing as exc:  # keep serving; requests answer 503 with the fix until the schema exists
        print(f"[db] {exc}", flush=True)
    yield


app = FastAPI(title="FieldSight API", version=API_VERSION, lifespan=lifespan,
              description="Jobs, tasks and evidence for field work (hackathon MVP).")
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["*"], allow_headers=["*"])


@app.middleware("http")
async def readiness(request: Request, call_next):
    i18n.current_lang.set(i18n.pick(request.headers.get("x-lang") or request.query_params.get("lang")))
    if request.url.path.startswith("/api/") and (not _ready or _local_db_missing()):
        try:
            await run_in_threadpool(ensure_ready)
        except db.SchemaMissing as exc:
            return JSONResponse(status_code=503, content={"detail": str(exc)})
    return await call_next(request)


@app.exception_handler(WorkflowError)
async def workflow_error(_: Request, exc: WorkflowError):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})


@app.exception_handler(rag.RagError)
async def rag_error(_: Request, exc: rag.RagError):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})


@app.exception_handler(db.Conflict)
async def conflict(_: Request, exc: db.Conflict):
    return JSONResponse(status_code=409, content={"detail": "This record already exists or was just changed. "
                                                            "Reload and try again."})


# ------------------------------------------------------------------ models --

class TaskMediaIn(BaseModel):
    media_id: str
    node_ids: list[str] = []  # part ids from the model's parts list; empty = the whole model


class TaskIn(BaseModel):
    description: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
    media: list[TaskMediaIn] = []


class JobIn(BaseModel):
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    assigned_to: str
    due_date: date | None = None  # "YYYY-MM-DD"
    tasks: list[TaskIn] = Field(min_length=1, max_length=100)


class StatusIn(BaseModel):
    status: str


class AskIn(BaseModel):
    question: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=1000)]
    task_id: str | None = None  # ask about one task: its description, notes, AI findings and photos go along


# ------------------------------------------------------------------ system --

@app.get("/api/health")
def health() -> dict[str, Any]:
    available, detail = ai.get_provider().available()
    return {"status": "ok", "version": API_VERSION, "app_label": settings.app_label,
            "data_backend": settings.data_backend, "storage": settings.storage_mode,
            "ai": {"available": available, "detail": detail},
            "document_search": bool(settings.voyage_api_key)}


@app.get("/api/config")
def client_config() -> dict[str, Any]:
    """Public settings the web client needs to log in (the publishable key is meant for browsers)."""
    return {"app_label": settings.app_label, "supabase_url": settings.supabase_url,
            "supabase_publishable_key": settings.supabase_publishable_key}


@app.get("/api/me")
def me(user: User) -> dict[str, Any]:
    company = db.first("companies", {"id": user["company_id"]})
    return {**user, "company": company, "has_face": face.has_face(user["id"])}


class FaceIn(BaseModel):
    embeddings: list[list[float]] = Field(max_length=10)
    consent: bool = False


def _client(request: Request) -> str:
    return request.headers.get("x-forwarded-for", "").split(",")[0].strip() or \
        (request.client.host if request.client else "unknown")


@app.post("/api/auth/face-login")
def face_login(body: FaceIn, request: Request) -> dict[str, Any]:
    """No login needed: the face is the login. Returns a Supabase session for the browser to adopt."""
    return face.supabase_session(face.identify(body.embeddings, _client(request)))


@app.post("/api/me/face")
def register_face(body: FaceIn, user: User) -> dict[str, Any]:
    face.register(user, body.embeddings, body.consent)
    return {"has_face": True}


@app.delete("/api/me/face")
def delete_face(user: User) -> dict[str, Any]:
    face.remove(user)
    return {"has_face": False}


@app.get("/api/users")
def users(user: User) -> list[dict[str, Any]]:
    """People in the user's company (the employer uses this to assign jobs)."""
    return sorted(workflow.company_users(user["company_id"]).values(), key=lambda u: (u["user_class"], u["username"]))


# -------------------------------------------------------------------- jobs --

@app.get("/api/jobs")
def list_jobs(user: User) -> list[dict[str, Any]]:
    return workflow.list_jobs(user)


@app.get("/api/dashboard")
def dashboard(user: Employer) -> dict[str, Any]:
    """Employer overview: all jobs (open first, by due date), flagged and failed tasks, each employee's workload."""
    return workflow.dashboard(user)


@app.post("/api/jobs")
def create_job(body: JobIn, user: Employer) -> dict[str, Any]:
    job_id = workflow.create_job(user, title=body.title, assigned_to=body.assigned_to, due_date=body.due_date,
                                 tasks=[t.model_dump() for t in body.tasks])
    return workflow.job_detail(user, job_id)


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str, user: User) -> dict[str, Any]:
    return workflow.job_detail(user, job_id)


@app.delete("/api/jobs/{job_id}")
def delete_job(job_id: str, user: Employer) -> dict[str, Any]:
    workflow.delete_job(user, job_id)
    return {"deleted": job_id}


# ------------------------------------------------------------------- tasks --

@app.post("/api/tasks/{task_id}/status")
def set_status(task_id: str, body: StatusIn, user: User) -> dict[str, Any]:
    job = workflow.set_status(user, task_id, body.status)
    return workflow.job_detail(user, job["id"])


async def _read_photo(file: UploadFile) -> tuple[bytes, dict[str, Any]]:
    """Decode, strip metadata, downscale and run image checks, off the event loop."""
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


@app.post("/api/tasks/{task_id}/evidence")
async def add_evidence(task_id: str, user: User, file: UploadFile | None = File(None),
                       text: str | None = Form(None), assess: bool = Form(True)) -> dict[str, Any]:
    """A photo, a text note, or both. Photos get the advisory AI review unless assess=false."""
    photo, checks = await _read_photo(file) if file is not None else (None, None)
    row = await run_in_threadpool(lambda: workflow.add_evidence(user, task_id, text=text, photo=photo))
    if photo is not None and assess:
        await run_in_threadpool(workflow.assess_evidence, row["id"], checks)
    elif photo is not None:
        await run_in_threadpool(lambda: db.update("evidence", {"ai_assessment": {"image_checks": checks}},
                                                  {"id": row["id"]}))
    _, job = await run_in_threadpool(workflow.task_for, user, task_id)
    return await run_in_threadpool(workflow.job_detail, user, job["id"])


@app.post("/api/evidence/{evidence_id}/assess")
def reassess(evidence_id: str, user: User) -> dict[str, Any]:
    e = db.first("evidence", {"id": evidence_id})
    if not e or not e["photo_path"]:
        raise HTTPException(404, "Photo evidence not found")
    _, job = workflow.task_for(user, e["task_id"])
    workflow.assess_evidence(evidence_id)
    return workflow.job_detail(user, job["id"])


@app.post("/api/evidence/{evidence_id}/translate")
def translate_review(evidence_id: str, user: User) -> dict[str, Any]:
    """Sent by the client right after a photo review, so the review is ready in the other language too."""
    return {"translated": workflow.translate_review(user, evidence_id)}


# ------------------------------------------------------------------- media --

@app.get("/api/media")
def list_media(user: Employer) -> list[dict[str, Any]]:
    rows = db.select("media", {"company_id": user["company_id"]}, order="-created_at")
    urls = blobs.signed_urls([m["storage_path"] for m in rows])
    chunks: dict[str, int] = {}
    for c in db.select("document_chunks", {"company_id": user["company_id"]}, columns="media_id"):
        chunks[c["media_id"]] = chunks.get(c["media_id"], 0) + 1
    return [{**workflow.media_view(m, urls), "chunks": chunks.get(m["id"], 0)} for m in rows]


@app.post("/api/media")
async def upload_media(user: Employer, file: UploadFile = File(...),
                       title: str | None = Form(None)) -> dict[str, Any]:
    data = await file.read()
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(413, f"File larger than {settings.max_upload_mb} MB")
    row = await run_in_threadpool(media.create_media, user["company_id"], file.filename or "upload", data, title)
    urls = await run_in_threadpool(blobs.signed_urls, [row["storage_path"]])
    return {**workflow.media_view(row, urls), "indexing": row["indexing"]}


@app.post("/api/media/{media_id}/reindex")
def reindex_media(media_id: str, user: Employer) -> dict[str, Any]:
    """Make a stored document searchable (again). Returns the media item with an `indexing` report."""
    m = workflow.media_for(user, media_id)
    indexing = media.reindex(m)
    chunks = db.count("document_chunks", {"media_id": media_id})
    return {**workflow.media_view(m, blobs.signed_urls([m["storage_path"]])), "chunks": chunks, "indexing": indexing}


@app.delete("/api/media/{media_id}")
def delete_media(media_id: str, user: Employer) -> dict[str, Any]:
    media.delete_media(workflow.media_for(user, media_id))
    return {"deleted": media_id}


# --------------------------------------------------------- document search --

@app.post("/api/ask")
def ask(body: AskIn, user: User) -> dict[str, Any]:
    """Answer a question from the company's documents, with numbered sources that link to the cited page."""
    task = workflow.task_context(user, body.task_id) if body.task_id else None
    # The task description sharpens the search ("what does this reading mean?" finds the gauge section).
    query = f"{body.question}\n{task['description']}" if task else body.question
    out = rag.answer(body.question, rag.search(user["company_id"], query), task)
    docs = {m["id"]: m for m in db.select("media", {"id": sorted({s["media_id"] for s in out["sources"]}),
                                                     "company_id": user["company_id"]}, columns="id,storage_path")}
    urls = blobs.signed_urls([m["storage_path"] for m in docs.values()])
    for s in out["sources"]:
        path = (docs.get(s["media_id"]) or {}).get("storage_path")
        url = urls.get(path) if path else None
        # PDF viewers open at a page given as #page=N (browsers ignore it for text files)
        s["url"] = f"{url}#page={s['page']}" if url and s["page"] and path.endswith(".pdf") else url
    return out


# ------------------------------------------------------------ static files --

if settings.data_backend == "local":
    @app.get("/api/local-files/{path:path}", include_in_schema=False)
    def local_file(path: str):
        """Stand-in for Supabase signed URLs when running on local storage (tests, offline development)."""
        data = blobs.get(path)
        if data is None:
            raise HTTPException(404, "File not found")
        return Response(data, media_type=media.KINDS.get("." + path.rsplit(".", 1)[-1].lower(),
                                                         ("", "application/octet-stream"))[1])

if settings.web_dist_dir.exists():
    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        candidate = (settings.web_dist_dir / full_path).resolve()
        if full_path and candidate.is_file() and settings.web_dist_dir.resolve() in candidate.parents:
            if full_path.startswith("assets/"):  # Vite content-hashes these names, so they never change
                return FileResponse(candidate, headers={"Cache-Control": "public, max-age=31536000, immutable"})
            return FileResponse(candidate)
        # A missing file (e.g. a bundle from an older deploy) must 404, not fall back to the HTML page
        if full_path.startswith(("api/", "assets/")) or "." in full_path.rsplit("/", 1)[-1]:
            raise HTTPException(404, "Not found")
        # Sent without ETag/Last-Modified: Vercel stamps every file with the same mtime and new builds keep the
        # same size, so FileResponse's validators never change and browsers would keep a stale page forever.
        return Response((settings.web_dist_dir / "index.html").read_bytes(), media_type="text/html",
                        headers={"Cache-Control": "no-cache"})
