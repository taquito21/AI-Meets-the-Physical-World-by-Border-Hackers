"""Deterministic inspection workflow rules. All state transitions happen here, server side.

AI output is advisory: it can move an item to "more evidence requested" but never to
"passed". Only an inspector disposition passes or fails a requirement, and only a
supervisor (different person from the inspector) approves an inspection.
"""
from __future__ import annotations

import sqlite3
from typing import Any

from . import db
from .config import settings

EDITABLE = {"in_progress", "changes_requested"}
FINAL_ITEM = {"passed", "failed", "not_applicable"}
AWAITING_ITEM = {"evidence_submitted", "more_evidence_requested"}
SEVERITIES = ("low", "medium", "high", "critical")
OPEN_FINDING = {"open", "assigned", "action_recorded", "awaiting_verification"}

FINDING_TRANSITIONS: dict[str, set[str]] = {
    "open": {"assigned", "void"},
    "assigned": {"action_recorded"},
    "action_recorded": {"awaiting_verification"},
    "awaiting_verification": {"closed", "assigned"},
    "closed": set(),
    "void": set(),
}


class WorkflowError(Exception):
    def __init__(self, message: str, status_code: int = 409, details: list[dict] | None = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.details = details or []


def needs_photo(evidence_type: str) -> bool:
    return evidence_type in ("photo", "photo_and_manual_confirmation")


def needs_manual(evidence_type: str) -> bool:
    return evidence_type in ("manual_confirmation", "photo_and_manual_confirmation")


# ------------------------------------------------------------------ lookup --

def _inspection(conn: sqlite3.Connection, inspection_id: str) -> dict[str, Any]:
    insp = db.row(conn.execute("SELECT * FROM inspections WHERE id = ?", (inspection_id,)).fetchone())
    if not insp:
        raise WorkflowError("Inspection not found", 404)
    return insp


def _item(conn: sqlite3.Connection, inspection_id: str, item_id: str) -> dict[str, Any]:
    item = db.row(conn.execute("SELECT * FROM inspection_items WHERE id = ? AND inspection_id = ?",
                               (item_id, inspection_id)).fetchone())
    if not item:
        raise WorkflowError("Inspection item not found", 404)
    return item


def _require_editable(insp: dict[str, Any]) -> None:
    if insp["status"] not in EDITABLE:
        raise WorkflowError(f"Inspection is '{insp['status']}' and can no longer be edited by the inspector")


def latest_evidence_id(conn: sqlite3.Connection, item_id: str) -> str | None:
    r = conn.execute("SELECT id FROM evidence WHERE inspection_item_id = ? ORDER BY created_at DESC, rowid DESC LIMIT 1",
                     (item_id,)).fetchone()
    return r["id"] if r else None


def _latest_assessment(conn: sqlite3.Connection, item_id: str) -> dict[str, Any] | None:
    """Assessment of the most recent photo only; older photos are superseded."""
    ev = latest_evidence_id(conn, item_id)
    if not ev:
        return None
    return db.row(conn.execute("SELECT * FROM evidence_assessments WHERE evidence_id = ? "
                               "ORDER BY created_at DESC, rowid DESC LIMIT 1", (ev,)).fetchone())


def _has_open_finding(conn: sqlite3.Connection, item_id: str) -> bool:
    return bool(conn.execute("SELECT COUNT(*) FROM findings WHERE inspection_item_id = ? AND status IN "
                             "('open','assigned','action_recorded','awaiting_verification')", (item_id,)).fetchone()[0])


def _evidence_count(conn: sqlite3.Connection, item_id: str) -> int:
    return conn.execute("SELECT COUNT(*) FROM evidence WHERE inspection_item_id = ?", (item_id,)).fetchone()[0]


def _touch(conn: sqlite3.Connection, inspection_id: str) -> None:
    conn.execute("UPDATE inspections SET updated_at = ? WHERE id = ?", (db.now(), inspection_id))


def assessment_flags_insufficient(assessment: dict[str, Any] | None) -> bool:
    if not assessment or assessment.get("status") != "completed" or not assessment.get("result"):
        return False
    res = assessment["result"]
    return res.get("recommended_action") == "retake_photo" or res.get("evidence_sufficient") is False


# -------------------------------------------------------------- lifecycle --

MODES = ("live", "demo")


def start_inspection(conn: sqlite3.Connection, serial_number: str, inspector: str, mode: str = "live") -> dict[str, Any]:
    """mode 'live': real photos from the device. mode 'demo': may also use the package's prepared demo photos.
    The mode is fixed for the life of the inspection and shown everywhere it appears."""
    if mode not in MODES:
        raise WorkflowError(f"Unknown inspection mode '{mode}'", 400)
    inst = db.row(conn.execute("SELECT * FROM product_instances WHERE serial_number = ?", (serial_number,)).fetchone())
    if not inst:
        raise WorkflowError(f"Unknown product instance {serial_number}", 404)
    open_insp = conn.execute(
        "SELECT id, mode FROM inspections WHERE product_instance_id = ? AND status IN ('in_progress','changes_requested') "
        "ORDER BY started_at DESC LIMIT 1", (inst["id"],)).fetchone()
    if open_insp:
        if open_insp["mode"] != mode:
            raise WorkflowError(f"A {open_insp['mode']} inspection of this unit is already open. "
                                "Finish it before starting a different mode.")
        return {"inspection_id": open_insp["id"], "resumed": True}
    if conn.execute("SELECT 1 FROM inspections WHERE product_instance_id = ? AND status = 'submitted'",
                    (inst["id"],)).fetchone():
        raise WorkflowError("An inspection of this unit is awaiting supervisor review. Wait for the decision first.")
    rev_id = inst["product_revision_id"]
    proc = db.row(conn.execute("SELECT procedure FROM product_revisions WHERE id = ?", (rev_id,)).fetchone())["procedure"]
    reqs = db.rows(conn.execute(
        "SELECT * FROM inspection_requirements WHERE product_revision_id = ? ORDER BY sort", (rev_id,)).fetchall())
    if not reqs:
        raise WorkflowError("This product revision has no inspection requirements")
    ts = db.now()
    insp_id = db.new_id("insp")
    conn.execute("INSERT INTO inspections (id, product_instance_id, product_revision_id, procedure_id, inspector, "
                 "status, started_at, submitted_at, decided_at, updated_at, mode) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                 (insp_id, inst["id"], rev_id, proc.get("procedure_id", ""), inspector, "in_progress", ts, None, None,
                  ts, mode))
    for r in reqs:
        # The requirement definition is snapshotted so later revisions never rewrite this record.
        conn.execute(
            "INSERT INTO inspection_items (id, inspection_id, requirement_id, component_id, requirement_snapshot, "
            "required, status, sort, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (db.new_id("item"), insp_id, r["id"], r["component_id"], db.dumps(r["definition"]), int(r["required"]),
             "pending", r["sort"], ts))
    db.log_event(conn, "inspection", insp_id, "inspection_started", inspector,
                 {"serial_number": serial_number, "revision": rev_id, "mode": mode})
    return {"inspection_id": insp_id, "resumed": False}


def record_evidence(conn: sqlite3.Connection, inspection_id: str, item_id: str, evidence_id: str, actor: str) -> None:
    insp = _inspection(conn, inspection_id)
    _require_editable(insp)
    item = _item(conn, inspection_id, item_id)
    if item["status"] in FINAL_ITEM:
        db.log_event(conn, "inspection_item", item_id, "item_reopened", actor,
                     {"previous_status": item["status"], "reason": "new evidence submitted"})
    conn.execute("UPDATE inspection_items SET status='evidence_submitted', status_reason=NULL, updated_at=? WHERE id=?",
                 (db.now(), item_id))
    db.log_event(conn, "inspection_item", item_id, "evidence_submitted", actor,
                 {"evidence_id": evidence_id, "inspection_id": inspection_id})
    _touch(conn, inspection_id)


def apply_assessment(conn: sqlite3.Connection, item_id: str, assessment: dict[str, Any]) -> None:
    """AI may only hold an item back for more evidence; it never accepts one."""
    item = db.row(conn.execute("SELECT * FROM inspection_items WHERE id = ?", (item_id,)).fetchone())
    if not item or item["status"] not in AWAITING_ITEM:
        return
    if assessment.get("evidence_id") != latest_evidence_id(conn, item_id):
        return  # a late result for a superseded photo must not override the newer one
    if assessment_flags_insufficient(assessment):
        conn.execute("UPDATE inspection_items SET status='more_evidence_requested', status_reason='ai_retake', "
                     "updated_at=? WHERE id=?", (db.now(), item_id))
        db.log_event(conn, "inspection_item", item_id, "more_evidence_recommended", "ai",
                     {"assessment_id": assessment.get("id")})


def decide_item(conn: sqlite3.Connection, inspection_id: str, item_id: str, *, decision: str, actor: str,
                observation: str | None = None, manual_confirmed: bool = False, override_note: str | None = None,
                finding: dict[str, Any] | None = None) -> dict[str, Any]:
    insp = _inspection(conn, inspection_id)
    _require_editable(insp)
    item = _item(conn, inspection_id, item_id)
    etype = item["requirement_snapshot"]["evidence_type"]
    observation = (observation or "").strip() or None
    override_note = (override_note or "").strip() or None
    problems: list[str] = []

    if decision == "pass":
        if needs_photo(etype) and _evidence_count(conn, item_id) == 0:
            problems.append("Photo evidence is required before this requirement can pass.")
        if needs_manual(etype) and not manual_confirmed:
            problems.append("The inspector must confirm the physical check (manual confirmation).")
        if item["status"] == "more_evidence_requested" and item.get("status_reason") == "supervisor_request":
            if needs_photo(etype):
                problems.append("The supervisor requested new evidence for this requirement. Submit a new photo first.")
            elif not observation:
                problems.append("The supervisor asked for this check to be repeated. Describe what you re-checked "
                                "in the observation.")
        elif assessment_flags_insufficient(_latest_assessment(conn, item_id)) and not override_note:
            problems.append("The AI assessment recommends another photo. Retake the photo, or record an override "
                            "justification explaining why the evidence is sufficient.")
        if _has_open_finding(conn, item_id):
            problems.append("This requirement has an open finding. Void it (if raised in error) before passing.")
        new_status = "passed"
    elif decision == "fail":
        if needs_photo(etype) and _evidence_count(conn, item_id) == 0:
            problems.append("Photo evidence of the condition is required to fail this requirement.")
        if not finding or not (finding.get("description") or "").strip():
            problems.append("A finding description is required when a requirement fails.")
        elif finding.get("severity") not in SEVERITIES:
            problems.append(f"Finding severity must be one of {', '.join(SEVERITIES)}.")
        new_status = "failed"
    elif decision == "not_applicable":
        if not observation:
            problems.append("A justification is required to mark a requirement not applicable.")
        if _has_open_finding(conn, item_id):
            problems.append("This requirement has an open finding. Void it (if raised in error) first.")
        new_status = "not_applicable"
    else:
        raise WorkflowError(f"Unknown decision '{decision}'", 400)
    if problems:
        raise WorkflowError("Requirement cannot be dispositioned", 422, [{"reason": p} for p in problems])

    ts = db.now()
    conn.execute("UPDATE inspection_items SET status=?, status_reason=NULL, observation=?, manual_confirmed=?, "
                 "override_note=?, decided_by=?, updated_at=? WHERE id=?",
                 (new_status, observation, int(bool(manual_confirmed)), override_note, actor, ts, item_id))
    finding_id = None
    if decision == "fail":
        existing = conn.execute("SELECT id FROM findings WHERE inspection_item_id = ? AND status = 'open'",
                                (item_id,)).fetchone()
        if existing:
            finding_id = existing["id"]
            conn.execute("UPDATE findings SET description=?, severity=?, updated_at=? WHERE id=?",
                         (finding["description"].strip(), finding["severity"], ts, finding_id))
        else:
            finding_id = db.new_id("fnd")
            conn.execute("INSERT INTO findings VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                         (finding_id, inspection_id, insp["product_instance_id"], item["component_id"],
                          item["requirement_id"], item_id, finding["description"].strip(), finding["severity"],
                          "open", None, actor, ts, ts, None))
            db.log_event(conn, "finding", finding_id, "finding_created", actor,
                         {"inspection_id": inspection_id, "component_id": item["component_id"],
                          "severity": finding["severity"]})
    db.log_event(conn, "inspection_item", item_id, f"item_{new_status}", actor,
                 {"inspection_id": inspection_id, "override_note": override_note, "finding_id": finding_id})
    _touch(conn, inspection_id)
    return {"item_id": item_id, "status": new_status, "finding_id": finding_id}


def readiness(conn: sqlite3.Connection, inspection_id: str) -> dict[str, Any]:
    insp = _inspection(conn, inspection_id)
    items = db.rows(conn.execute("SELECT * FROM inspection_items WHERE inspection_id = ? ORDER BY sort",
                                 (inspection_id,)).fetchall())
    findings = db.rows(conn.execute("SELECT * FROM findings WHERE inspection_id = ?", (inspection_id,)).fetchall())
    blocking: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    def entry(item, reason):
        return {"item_id": item["id"], "requirement_id": item["requirement_id"],
                "component_id": item["component_id"], "title": item["requirement_snapshot"]["title"], "reason": reason}

    if insp["status"] not in EDITABLE:
        blocking.append({"reason": f"Inspection status is '{insp['status']}'"})
    for it in items:
        etype = it["requirement_snapshot"]["evidence_type"]
        if it["required"] and it["status"] not in FINAL_ITEM:
            reason = {"pending": "Not yet inspected",
                      "evidence_submitted": "Evidence submitted, awaiting inspector decision",
                      "more_evidence_requested": "Additional evidence requested"}.get(it["status"], it["status"])
            blocking.append(entry(it, reason))
        if not it["required"] and it["status"] not in FINAL_ITEM:
            warnings.append(entry(it, "Optional requirement not completed"))
        if it["status"] in ("passed", "failed") and needs_photo(etype) and _evidence_count(conn, it["id"]) == 0:
            blocking.append(entry(it, "Required photo evidence missing"))
        if it["status"] == "failed" and not any(f["inspection_item_id"] == it["id"] for f in findings):
            blocking.append(entry(it, "Failed requirement has no recorded finding"))
        if it["status"] == "not_applicable" and it["required"]:
            warnings.append(entry(it, "Mandatory requirement marked not applicable (documented exception for supervisor)"))
        if it["override_note"] and it["status"] == "passed":
            warnings.append(entry(it, "Passed with AI evidence recommendation overridden"))
        if it["status"] == "passed":
            latest = _latest_assessment(conn, it["id"])
            if latest and latest.get("result") and latest["result"].get("conditions_for_human_review"):
                warnings.append(entry(it, "Passed although the AI flagged conditions for human review: "
                                      + "; ".join(latest["result"]["conditions_for_human_review"])))
    open_findings = [f for f in findings if f["status"] in OPEN_FINDING]
    for f in open_findings:
        if f["severity"] == "critical" and settings.block_submit_on_open_critical:
            blocking.append({"finding_id": f["id"], "component_id": f["component_id"],
                             "reason": "Open critical finding must be closed before submission (closure policy)"})
        else:
            warnings.append({"finding_id": f["id"], "component_id": f["component_id"],
                             "reason": f"Open {f['severity']} finding will be submitted for review and corrective action"})
    return {"ready": not blocking, "blocking": blocking, "warnings": warnings}


def submit(conn: sqlite3.Connection, inspection_id: str, actor: str) -> dict[str, Any]:
    insp = _inspection(conn, inspection_id)
    check = readiness(conn, inspection_id)
    if not check["ready"]:
        raise WorkflowError("Inspection cannot be submitted yet", 409, check["blocking"])
    ts = db.now()
    conn.execute("UPDATE inspections SET status='submitted', submitted_at=?, updated_at=? WHERE id=?",
                 (ts, ts, inspection_id))
    db.log_event(conn, "inspection", inspection_id, "inspection_submitted", actor,
                 {"previous_status": insp["status"], "warnings": len(check["warnings"])})
    return {"inspection_id": inspection_id, "status": "submitted", "warnings": check["warnings"]}


def review(conn: sqlite3.Connection, inspection_id: str, *, reviewer: str, decision: str,
           comments: str | None, item_ids: list[str] | None) -> dict[str, Any]:
    insp = _inspection(conn, inspection_id)
    if insp["status"] != "submitted":
        raise WorkflowError(f"Only submitted inspections can be reviewed (status is '{insp['status']}')")
    if reviewer.strip().lower() == insp["inspector"].strip().lower():
        raise WorkflowError("The reviewer must be a different person from the inspector", 403)
    ts = db.now()
    if decision == "approve":
        status = "approved"
    elif decision == "reject":
        if not (comments or "").strip():
            raise WorkflowError("A comment is required to reject an inspection", 422)
        status = "rejected"
    elif decision == "request_evidence":
        if not item_ids:
            raise WorkflowError("Select at least one requirement that needs additional evidence", 422)
        valid = {r["id"] for r in conn.execute("SELECT id FROM inspection_items WHERE inspection_id = ?",
                                                (inspection_id,)).fetchall()}
        if not set(item_ids) <= valid:
            raise WorkflowError("Unknown inspection item in request", 422)
        for iid in item_ids:
            conn.execute("UPDATE inspection_items SET status='more_evidence_requested', status_reason='supervisor_request', "
                         "updated_at=? WHERE id=?", (ts, iid))
            db.log_event(conn, "inspection_item", iid, "more_evidence_requested", reviewer, {"comments": comments})
        status = "changes_requested"
    else:
        raise WorkflowError(f"Unknown review decision '{decision}'", 400)
    conn.execute("INSERT INTO reviews VALUES (?,?,?,?,?,?,?)",
                 (db.new_id("rev"), inspection_id, reviewer, decision, comments, db.dumps(item_ids or []), ts))
    conn.execute("UPDATE inspections SET status=?, decided_at=?, updated_at=? WHERE id=?",
                 (status, ts if status in ("approved", "rejected") else None, ts, inspection_id))
    db.log_event(conn, "inspection", inspection_id, f"review_{decision}", reviewer, {"comments": comments})
    return {"inspection_id": inspection_id, "status": status}


# ---------------------------------------------------------------- findings --

def transition_finding(conn: sqlite3.Connection, finding_id: str, *, to: str, actor: str,
                       assigned_to: str | None = None, note: str | None = None) -> dict[str, Any]:
    f = db.row(conn.execute("SELECT * FROM findings WHERE id = ?", (finding_id,)).fetchone())
    if not f:
        raise WorkflowError("Finding not found", 404)
    if to not in FINDING_TRANSITIONS.get(f["status"], set()):
        raise WorkflowError(f"Finding cannot move from '{f['status']}' to '{to}'")
    ts = db.now()
    ca = db.row(conn.execute("SELECT * FROM corrective_actions WHERE finding_id = ? ORDER BY created_at DESC LIMIT 1",
                             (finding_id,)).fetchone())
    note = (note or "").strip() or None
    if to == "assigned":
        assigned_to = (assigned_to or f.get("assigned_to") or "").strip()
        if not assigned_to:
            raise WorkflowError("assigned_to is required", 422)
        conn.execute("UPDATE findings SET assigned_to=? WHERE id=?", (assigned_to, finding_id))
        if ca:
            conn.execute("UPDATE corrective_actions SET status='assigned', assigned_to=?, updated_at=? WHERE id=?",
                         (assigned_to, ts, ca["id"]))
        else:
            conn.execute("INSERT INTO corrective_actions VALUES (?,?,?,?,?,?,?,?,?)",
                         (db.new_id("ca"), finding_id, assigned_to, None, "assigned", None, None, ts, ts))
    elif to == "void":
        if not note:
            raise WorkflowError("A reason is required to void a finding", 422)
    elif to == "action_recorded":
        if not note:
            raise WorkflowError("Describe the corrective action taken", 422)
        conn.execute("UPDATE corrective_actions SET status='action_recorded', description=?, recorded_by=?, updated_at=? "
                     "WHERE id=?", (note, actor, ts, ca["id"]))
    elif to == "awaiting_verification":
        conn.execute("UPDATE corrective_actions SET status='awaiting_verification', updated_at=? WHERE id=?", (ts, ca["id"]))
    elif to == "closed":
        if ca and ca.get("recorded_by") and ca["recorded_by"].strip().lower() == actor.strip().lower():
            raise WorkflowError("Verification must be performed by someone other than the person who did the work", 403)
        after = conn.execute("SELECT COUNT(*) FROM evidence WHERE finding_id = ? AND kind = 'corrective_after'",
                             (finding_id,)).fetchone()[0]
        if not after:
            raise WorkflowError("An 'after' photo of the corrected condition is required to close the finding", 422)
        conn.execute("UPDATE corrective_actions SET status='closed', verified_by=?, updated_at=? WHERE id=?",
                     (actor, ts, ca["id"]))
    conn.execute("UPDATE findings SET status=?, updated_at=?, closed_at=? WHERE id=?",
                 (to, ts, ts if to in ("closed", "void") else None, finding_id))
    db.log_event(conn, "finding", finding_id, f"finding_{to}", actor,
                 {"note": note, "assigned_to": assigned_to, "inspection_id": f["inspection_id"]})
    return {"finding_id": finding_id, "status": to}


# ------------------------------------------------------------------- views --

def component_statuses(items: list[dict[str, Any]], findings: list[dict[str, Any]]) -> dict[str, str]:
    by_comp: dict[str, list[dict[str, Any]]] = {}
    for it in items:
        by_comp.setdefault(it["component_id"], []).append(it)
    open_by_comp = {f["component_id"] for f in findings if f["status"] in OPEN_FINDING}
    out: dict[str, str] = {}
    for comp, its in by_comp.items():
        statuses = {i["status"] for i in its}
        if "failed" in statuses or comp in open_by_comp:
            out[comp] = "finding"
        elif statuses & AWAITING_ITEM:
            out[comp] = "pending"
        elif statuses <= {"passed", "not_applicable"}:
            out[comp] = "accepted"
        elif statuses & {"passed", "not_applicable"}:
            out[comp] = "in_progress"
        else:
            out[comp] = "not_inspected"
    for comp in open_by_comp - set(out):
        out[comp] = "finding"
    return out
