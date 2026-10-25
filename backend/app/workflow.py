"""Jobs, tasks and evidence: every access rule and state change happens here, server side.

Who sees what: an employer sees every job of their company; an employee sees only the jobs assigned to them.
Anything outside that answers 404, so ids from another company reveal nothing.

Evidence: the employee adds photos and notes; the employer adds notes only (e.g. a reply to a flagged task).

Task status (pending | passed | failed | flagged) is always set by a person. "Flagged" escalates the task to the
employer, who answers with a text evidence entry and then sets passed or failed. The AI photo review is advisory:
it is stored on the evidence row and never changes a status.

Typed text and AI reviews are saved in the writer's language with a machine translation into the other one
(translate.py); views show each reader their language.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from . import ai, db, i18n, translate
from .blobs import blobs

TASK_STATUSES = ("pending", "passed", "failed", "flagged")
OPEN_STATUSES = ("pending", "flagged")  # a job is finished when none of its tasks is still open
MAX_TEXT = 4000


class WorkflowError(Exception):
    def __init__(self, message: str, status_code: int = 409):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


# ----------------------------------------------------------------- access --

def company_users(company_id: str) -> dict[str, dict[str, Any]]:
    return {u["id"]: u for u in db.select("users", {"company_id": company_id})}


def job_for(user: dict[str, Any], job_id: str) -> dict[str, Any]:
    job = db.first("jobs", {"id": job_id})
    if (not job or job["company_id"] != user["company_id"]
            or (user["user_class"] == "employee" and job["assigned_to"] != user["id"])):
        raise WorkflowError("Job not found", 404)
    return job


def task_for(user: dict[str, Any], task_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    task = db.first("tasks", {"id": task_id})
    if not task:
        raise WorkflowError("Task not found", 404)
    try:
        return task, job_for(user, task["job_id"])
    except WorkflowError:
        raise WorkflowError("Task not found", 404)


def media_for(user: dict[str, Any], media_id: str) -> dict[str, Any]:
    media = db.first("media", {"id": media_id})
    if not media or media["company_id"] != user["company_id"]:
        raise WorkflowError("Media not found", 404)
    return media


# ------------------------------------------------------------------- jobs --

def _counts(statuses: list[str]) -> dict[str, int]:
    return {"total": len(statuses), **{s: statuses.count(s) for s in TASK_STATUSES}}


def _person(u: dict[str, Any] | None) -> dict[str, Any] | None:
    return {"id": u["id"], "username": u["username"], "user_class": u["user_class"]} if u else None


def _summary(j: dict[str, Any], statuses: list[str], people: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return {"id": j["id"], **i18n.typed(j, ("title",)), "created_at": j["created_at"], "due_date": j.get("due_date"),
            "assigned_to": _person(people.get(j["assigned_to"])), "counts": _counts(statuses),
            "finished": bool(statuses) and not any(s in OPEN_STATUSES for s in statuses)}


def _by_due_date(jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Open jobs first, soonest due date first (no due date last), then newest."""
    jobs = sorted(jobs, key=lambda j: j["created_at"], reverse=True)
    return sorted(jobs, key=lambda j: (j["finished"], j["due_date"] is None, j["due_date"] or ""))


def list_jobs(user: dict[str, Any]) -> list[dict[str, Any]]:
    where = ({"company_id": user["company_id"]} if user["user_class"] == "employer"
             else {"company_id": user["company_id"], "assigned_to": user["id"]})
    jobs = db.select("jobs", where, order="-created_at")
    statuses: dict[str, list[str]] = {}
    for t in db.select("tasks", {"job_id": [j["id"] for j in jobs]}, columns="job_id,status"):
        statuses.setdefault(t["job_id"], []).append(t["status"])
    people = company_users(user["company_id"])
    return _by_due_date([_summary(j, statuses.get(j["id"], []), people) for j in jobs])


def dashboard(user: dict[str, Any]) -> dict[str, Any]:
    """The employer's overview: every job, the tasks that need them, and each employee's workload."""
    jobs = list_jobs(user)
    titles = {j["id"]: j for j in jobs}
    attention = db.select("tasks", {"job_id": list(titles), "status": ["flagged", "failed"]},
                          columns="id,job_id,position,description,lang,translations,status,updated_at",
                          order="-updated_at")
    people = company_users(user["company_id"])
    team = []
    for u in sorted(people.values(), key=lambda u: u["username"]):
        if u["user_class"] != "employee":
            continue
        mine = [j for j in jobs if (j["assigned_to"] or {}).get("id") == u["id"]]
        team.append({**_person(u), "open_jobs": sum(not j["finished"] for j in mine),
                     "tasks_done": sum(j["counts"]["passed"] + j["counts"]["failed"] for j in mine),
                     "tasks_total": sum(j["counts"]["total"] for j in mine)})
    return {"jobs": jobs, "team": team,
            "attention": [{**{k: t[k] for k in ("id", "job_id", "position", "status", "updated_at")},
                           **i18n.typed(t, ("description",)), "job_title": titles[t["job_id"]]["title"],
                           "assigned_to": titles[t["job_id"]]["assigned_to"]} for t in attention]}


def create_job(user: dict[str, Any], *, title: str, assigned_to: str, tasks: list[dict[str, Any]],
               due_date: date | None = None) -> str:
    title = (title or "").strip()
    if not title:
        raise WorkflowError("A job needs a title", 422)
    assignee = company_users(user["company_id"]).get(assigned_to)
    if not assignee or assignee["user_class"] != "employee":
        raise WorkflowError("Assign the job to an employee of your company", 422)
    if not tasks:
        raise WorkflowError("Add at least one task", 422)
    media_ids = {m["media_id"] for t in tasks for m in t.get("media") or []}
    known = {m["id"]: m for m in db.select("media", {"id": sorted(media_ids)})}
    for mid in media_ids:
        if mid not in known or known[mid]["company_id"] != user["company_id"]:
            raise WorkflowError("A linked media item does not exist in your company", 422)
    for t in tasks:
        if not (t.get("description") or "").strip():
            raise WorkflowError("Every task needs a description", 422)

    ts = db.now()
    lang = i18n.current_lang.get()
    job_id = db.new_id()
    job_row = {"id": job_id, "company_id": user["company_id"], "assigned_to": assigned_to, "title": title,
               "due_date": due_date.isoformat() if due_date else None, "created_at": ts, "lang": lang,
               "translations": {}}
    task_rows, links = [], []
    for pos, t in enumerate(tasks):
        tid = db.new_id()
        task_rows.append({"id": tid, "job_id": job_id, "position": pos, "description": t["description"].strip(),
                          "status": "pending", "updated_at": ts, "lang": lang, "translations": {}})
        links += [{"task_id": tid, "media_id": m["media_id"], "node_ids": list(m.get("node_ids") or [])}
                  for m in t.get("media") or []]
    translate.fill([("jobs", job_row), *[("tasks", t) for t in task_rows]], translate.other(lang))
    db.insert("jobs", job_row)
    try:
        db.insert("tasks", task_rows)
        db.insert("task_media", links)
    except Exception:
        db.delete("jobs", {"id": job_id})  # tasks and links cascade: never leave a half-created job
        raise
    return job_id


def delete_job(user: dict[str, Any], job_id: str) -> None:
    job_for(user, job_id)
    tasks = [t["id"] for t in db.select("tasks", {"job_id": job_id}, columns="id")]
    photos = [e["photo_path"] for e in db.select("evidence", {"task_id": tasks}, columns="photo_path")
              if e["photo_path"]]
    db.delete("jobs", {"id": job_id})  # tasks, evidence and media links cascade
    blobs.delete(photos)


def job_detail(user: dict[str, Any], job_id: str) -> dict[str, Any]:
    job = job_for(user, job_id)
    people = company_users(user["company_id"])
    tasks = db.select("tasks", {"job_id": job_id}, order="position")
    task_ids = [t["id"] for t in tasks]
    evidence = db.select("evidence", {"task_id": task_ids}, order=["created_at", "id"])
    links = db.select("task_media", {"task_id": task_ids})
    media = {m["id"]: m for m in db.select("media", {"id": sorted({l["media_id"] for l in links})})}
    # Fill in translations missing for this reader (saved before translation existed, or the call failed then).
    translate.save(translate.fill([("jobs", job), *[("tasks", t) for t in tasks], *[("evidence", e) for e in evidence]],
                                  i18n.current_lang.get()))
    urls = blobs.signed_urls([e["photo_path"] for e in evidence if e["photo_path"]]
                             + [m["storage_path"] for m in media.values()])
    out_tasks = []
    for t in tasks:
        out_tasks.append({
            **{k: t[k] for k in ("id", "position", "status", "updated_at")}, **i18n.typed(t, ("description",)),
            "evidence": [evidence_view(e, people, urls) for e in evidence if e["task_id"] == t["id"]],
            "media": [{**media_view(media[l["media_id"]], urls), "node_ids": l["node_ids"]}
                      for l in links if l["task_id"] == t["id"] and l["media_id"] in media],
        })
    return {**_summary(job, [t["status"] for t in tasks], people), "tasks": out_tasks}


def evidence_view(e: dict[str, Any], people: dict[str, dict[str, Any]], urls: dict[str, str]) -> dict[str, Any]:
    return {"id": e["id"], "task_id": e["task_id"], "created_by": _person(people.get(e["created_by"])),
            **(i18n.typed(e, ("text",)) if e["text"] else {"text": None}),
            "photo_url": urls.get(e["photo_path"]) if e["photo_path"] else None,
            "ai_assessment": i18n.review(e["ai_assessment"]), "created_at": e["created_at"]}


def media_view(m: dict[str, Any], urls: dict[str, str]) -> dict[str, Any]:
    title, metadata = i18n.media(m["title"], m["metadata"])
    metadata = {k: v for k, v in metadata.items() if k != "translations"}  # the reader gets one language
    return {"id": m["id"], "title": title, "kind": m["kind"], "metadata": metadata,
            "created_at": m["created_at"], "url": urls.get(m["storage_path"])}


# ------------------------------------------------------------------ tasks --

def set_status(user: dict[str, Any], task_id: str, status: str) -> dict[str, Any]:
    if status not in TASK_STATUSES:
        raise WorkflowError(f"Status must be one of {', '.join(TASK_STATUSES)}", 422)
    _, job = task_for(user, task_id)
    db.update("tasks", {"status": status, "updated_at": db.now()}, {"id": task_id})
    return job


def add_evidence(user: dict[str, Any], task_id: str, *, text: str | None, photo: bytes | None) -> dict[str, Any]:
    """Store a photo and/or text on a task. Returns the evidence row (the AI review runs separately).
    Photos come from the employee in the field; the employer answers with notes only."""
    text = (text or "").strip()[:MAX_TEXT] or None
    if photo and user["user_class"] != "employee":
        raise WorkflowError("Only the employee doing the job can add photos. Write a note instead.", 403)
    if not text and not photo:
        raise WorkflowError("Add a photo, a note, or both", 422)
    _, job = task_for(user, task_id)
    evidence_id = db.new_id()
    path = f"{job['company_id']}/evidence/{task_id}/{evidence_id}.jpg" if photo else None
    if photo:
        blobs.put(path, photo, "image/jpeg")
    lang = i18n.current_lang.get()
    row = {"id": evidence_id, "task_id": task_id, "created_by": user["id"], "photo_path": path, "text": text,
           "ai_assessment": None, "created_at": db.now(), "lang": lang, "translations": {}}
    translate.fill([("evidence", row)], translate.other(lang))
    try:
        db.insert("evidence", row)
    except Exception:
        if path:
            blobs.delete([path])  # no orphan files
        raise
    db.update("tasks", {"updated_at": db.now()}, {"id": task_id})
    return row


MAX_CONTEXT_PHOTOS = 2  # most recent photos sent with a question about a task


def task_context(user: dict[str, Any], task_id: str) -> dict[str, Any]:
    """What a question about one task should know: the job, the task, its notes, the AI photo findings, the
    linked model parts, and the latest photos. Raises 404 if the user may not see the task."""
    task, job = task_for(user, task_id)
    people = company_users(user["company_id"])
    evidence = db.select("evidence", {"task_id": task_id}, order=["created_at", "id"])
    links = db.select("task_media", {"task_id": task_id})
    media = db.select("media", {"id": [l["media_id"] for l in links]})
    lines = [f"Job: {job['title']}", f"Task: {task['description']}", f"Current task status: {task['status']}"]
    for m in media:
        wanted = next((set(l["node_ids"]) for l in links if l["media_id"] == m["id"]), set())
        parts = [p.get("name") for p in (m["metadata"] or {}).get("parts", []) if p.get("id") in wanted]
        lines.append(f"Linked {m['kind'].replace('_', ' ')}: {m['title']}" + (f" (parts: {', '.join(parts)})" if parts else ""))
    for e in evidence:
        who = people.get(e["created_by"], {})
        role = who.get("user_class", "person")
        if e["text"]:
            lines.append(f"Note from the {role} ({e['created_at'][:16]}): {e['text']}")
        result = (e["ai_assessment"] or {}).get("result") or {}
        if result.get("summary"):
            findings = "; ".join(result.get("observations", []) + result.get("conditions_for_human_review", []))
            lines.append(f"AI review of a photo ({e['created_at'][:16]}): {result['summary']}"
                         + (f" Findings: {findings}" if findings else ""))
    photos = [e for e in evidence if e["photo_path"]][-MAX_CONTEXT_PHOTOS:]
    images = [data for data in (blobs.get(e["photo_path"]) for e in photos) if data]
    return {"description": task["description"], "text": "\n".join(lines), "images": images}


def assess_evidence(evidence_id: str, image_checks: dict[str, Any] | None = None) -> dict[str, Any]:
    """Run the AI photo review for one evidence photo and store the outcome on the row."""
    e = db.first("evidence", {"id": evidence_id})
    task = db.first("tasks", {"id": e["task_id"]})
    job = db.first("jobs", {"id": task["job_id"]})
    company = db.first("companies", {"id": job["company_id"]})
    links = db.select("task_media", {"task_id": task["id"]})
    media = db.select("media", {"id": [l["media_id"] for l in links]})
    parts = []
    for m in media:
        wanted = next((set(l["node_ids"]) for l in links if l["media_id"] == m["id"]), set())
        parts += [p for p in (m["metadata"] or {}).get("parts", []) if p.get("id") in wanted]
    data = blobs.get(e["photo_path"])
    if data is None:
        raise WorkflowError("Evidence photo missing", 404)
    if image_checks is None:
        image_checks = (e["ai_assessment"] or {}).get("image_checks")
    ctx = ai.build_context(company=company["name"], job_title=job["title"], task=task["description"], parts=parts,
                           media_titles=[m["title"] for m in media], worker_note=e["text"],
                           image_checks=image_checks, language=i18n.current_lang.get())
    outcome = ai.get_provider().assess(data, ctx)
    assessment = {"status": outcome.status, "provider": outcome.provider, "model": outcome.model,
                  "result": outcome.result, "error": outcome.error, "latency_ms": outcome.latency_ms,
                  "image_checks": image_checks, "assessed_at": db.now(), "lang": ctx["language"]}
    # Not translated here: this request already waits on the review, and the hosted time limit is tight. The client
    # asks for it right after (translate_review); failing that, job_detail does when the job is opened.
    db.update("evidence", {"ai_assessment": assessment}, {"id": evidence_id})
    return assessment


def translate_review(user: dict[str, Any], evidence_id: str) -> bool:
    """Translate a saved AI review into the other language, in its own request. True when a translation was added;
    False when there is nothing to translate, it already exists, or the call failed (job_detail retries later)."""
    e = db.first("evidence", {"id": evidence_id})
    if not e:
        raise WorkflowError("Evidence not found", 404)
    task_for(user, e["task_id"])
    review = e["ai_assessment"] or {}
    if not review.get("result"):
        return False
    changed = translate.fill([("evidence", e)], translate.other(review.get("lang") or i18n.current_lang.get()))
    translate.save(changed)
    return bool(changed)
