"""Deterministic inspection workflow rules. All state transitions happen here, server side.

Each database call is its own transaction (see db.py), so every state change is a conditional update on the
status that was read: if someone else changed the record in between, the request fails with 409 instead of
overwriting their change. Validation always happens before the first write.

AI output is advisory: it can move an item to "more evidence requested" but never to
"passed". Only an inspector disposition passes or fails a requirement, and only a
supervisor (different person from the inspector) approves an inspection.
"""
from __future__ import annotations

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

def _inspection(inspection_id: str) -> dict[str, Any]:
    insp = db.first("inspections", {"id": inspection_id})
    if not insp:
        raise WorkflowError("Inspection not found", 404)
    return insp


def _item(inspection_id: str, item_id: str) -> dict[str, Any]:
    item = db.first("inspection_items", {"id": item_id, "inspection_id": inspection_id})
    if not item:
        raise WorkflowError("Inspection item not found", 404)
    return item


def _require_editable(insp: dict[str, Any]) -> None:
    if insp["status"] not in EDITABLE:
        raise WorkflowError(f"Inspection is '{insp['status']}' and can no longer be edited by the inspector")


def _changed_concurrently() -> WorkflowError:
    return WorkflowError("This record was just changed by someone else. Reload and try again.", 409)


def latest_evidence_id(item_id: str) -> str | None:
    e = db.first("evidence", {"inspection_item_id": item_id}, columns="id", order=["-created_at", "-id"])
    return e["id"] if e else None


def _latest_assessment(item_id: str) -> dict[str, Any] | None:
    """Assessment of the most recent photo only; older photos are superseded."""
    ev = latest_evidence_id(item_id)
    if not ev:
        return None
    return db.first("evidence_assessments", {"evidence_id": ev}, order=["-created_at", "-id"])


def _has_open_finding(item_id: str) -> bool:
    return db.count("findings", {"inspection_item_id": item_id, "status": sorted(OPEN_FINDING)}) > 0


def _evidence_count(item_id: str) -> int:
    return db.count("evidence", {"inspection_item_id": item_id})


def _touch(inspection_id: str) -> None:
    db.update("inspections", {"updated_at": db.now()}, {"id": inspection_id})


def assessment_flags_insufficient(assessment: dict[str, Any] | None) -> bool:
    if not assessment or assessment.get("status") != "completed" or not assessment.get("result"):
        return False
    res = assessment["result"]
    return res.get("recommended_action") == "retake_photo" or res.get("evidence_sufficient") is False


def load_bundle(inspection_id: str) -> dict[str, Any]:
    """Everything recorded for one inspection, in a fixed number of queries (no per-item lookups)."""
    insp = _inspection(inspection_id)
    items = db.select("inspection_items", {"inspection_id": inspection_id}, order="sort")
    findings = db.select("findings", {"inspection_id": inspection_id}, order=["created_at", "id"])
    evidence = db.select("evidence", {"inspection_id": inspection_id}, order=["created_at", "id"])
    assessments = db.select("evidence_assessments", {"evidence_id": [e["id"] for e in evidence]},
                            order=["created_at", "id"])
    return {"inspection": insp, "items": items, "findings": findings, "evidence": evidence,
            "assessments": assessments}


def _latest_by_item(bundle: dict[str, Any]) -> tuple[dict[str, int], dict[str, dict[str, Any] | None]]:
    """Photo count per item, and the latest assessment of each item's most recent photo."""
    counts: dict[str, int] = {}
    latest_ev: dict[str, str] = {}
    for e in bundle["evidence"]:  # ascending, so the last one wins
        if e["inspection_item_id"]:
            counts[e["inspection_item_id"]] = counts.get(e["inspection_item_id"], 0) + 1
            latest_ev[e["inspection_item_id"]] = e["id"]
    latest_asmt: dict[str, dict[str, Any]] = {}
    for a in bundle["assessments"]:
        latest_asmt[a["evidence_id"]] = a
    return counts, {item: latest_asmt.get(ev) for item, ev in latest_ev.items()}


# -------------------------------------------------------------- lifecycle --

MODES = ("live", "demo")


def start_inspection(serial_number: str, inspector: str, mode: str = "live") -> dict[str, Any]:
    """mode 'live': real photos from the device. mode 'demo': may also use the package's prepared demo photos.
    The mode is fixed for the life of the inspection and shown everywhere it appears."""
    if mode not in MODES:
        raise WorkflowError(f"Unknown inspection mode '{mode}'", 400)
    inst = db.first("product_instances", {"serial_number": serial_number})
    if not inst:
        raise WorkflowError(f"Unknown product instance {serial_number}", 404)
    rev_id = inst["product_revision_id"]
    for attempt in range(2):
        open_insp = db.first("inspections", {"product_instance_id": inst["id"],
                                             "status": ["in_progress", "changes_requested"]},
                             columns="id,mode", order="-started_at")
        if open_insp:
            if open_insp["mode"] != mode:
                raise WorkflowError(f"A {open_insp['mode']} inspection of this unit is already open. "
                                    "Finish it before starting a different mode.")
            return {"inspection_id": open_insp["id"], "resumed": True}
        if db.count("inspections", {"product_instance_id": inst["id"], "status": "submitted"}):
            raise WorkflowError("An inspection of this unit is awaiting supervisor review. Wait for the decision first.")
        proc = db.first("product_revisions", {"id": rev_id}, columns="procedure")["procedure"]
        reqs = db.select("inspection_requirements", {"product_revision_id": rev_id}, order="sort")
        if not reqs:
            raise WorkflowError("This product revision has no inspection requirements")
        ts = db.now()
        insp_id = db.new_id("insp")
        try:
            # A unique index allows one open inspection per unit, so a concurrent start loses here.
            db.insert("inspections", {
                "id": insp_id, "product_instance_id": inst["id"], "product_revision_id": rev_id,
                "procedure_id": proc.get("procedure_id", ""), "inspector": inspector, "status": "in_progress",
                "started_at": ts, "submitted_at": None, "decided_at": None, "updated_at": ts, "mode": mode})
            break
        except db.Conflict:
            if attempt:
                raise WorkflowError("Another inspection of this unit was just started. Reload and try again.")
    try:
        # The requirement definition is snapshotted so later revisions never rewrite this record.
        db.insert("inspection_items", [{
            "id": db.new_id("item"), "inspection_id": insp_id, "requirement_id": r["id"],
            "component_id": r["component_id"], "requirement_snapshot": r["definition"],
            "required": bool(r["required"]), "status": "pending", "sort": r["sort"], "updated_at": ts}
            for r in reqs])
    except Exception:
        db.delete("inspection_items", {"inspection_id": insp_id})  # do not leave an inspection without items
        db.delete("inspections", {"id": insp_id})
        raise
    db.log_event("inspection", insp_id, "inspection_started", inspector,
                 {"serial_number": serial_number, "revision": rev_id, "mode": mode})
    return {"inspection_id": insp_id, "resumed": False}


def record_evidence(inspection_id: str, item_id: str, evidence_id: str, actor: str) -> None:
    insp = _inspection(inspection_id)
    _require_editable(insp)
    item = _item(inspection_id, item_id)
    if item["status"] in FINAL_ITEM:
        db.log_event("inspection_item", item_id, "item_reopened", actor,
                     {"previous_status": item["status"], "reason": "new evidence submitted"},
                     inspection_id=inspection_id)
    db.update("inspection_items", {"status": "evidence_submitted", "status_reason": None, "updated_at": db.now()},
              {"id": item_id})
    db.log_event("inspection_item", item_id, "evidence_submitted", actor,
                 {"evidence_id": evidence_id, "inspection_id": inspection_id})
    _touch(inspection_id)


def apply_assessment(item_id: str, assessment: dict[str, Any]) -> None:
    """AI may only hold an item back for more evidence; it never accepts one."""
    item = db.first("inspection_items", {"id": item_id})
    if not item or item["status"] not in AWAITING_ITEM:
        return
    if assessment.get("evidence_id") != latest_evidence_id(item_id):
        return  # a late result for a superseded photo must not override the newer one
    if assessment_flags_insufficient(assessment):
        changed = db.update("inspection_items", {"status": "more_evidence_requested", "status_reason": "ai_retake",
                                                 "updated_at": db.now()},
                            {"id": item_id, "status": sorted(AWAITING_ITEM)})
        if changed:
            db.log_event("inspection_item", item_id, "more_evidence_recommended", "ai",
                         {"assessment_id": assessment.get("id")}, inspection_id=item["inspection_id"])


def decide_item(inspection_id: str, item_id: str, *, decision: str, actor: str,
                observation: str | None = None, manual_confirmed: bool = False, override_note: str | None = None,
                finding: dict[str, Any] | None = None) -> dict[str, Any]:
    insp = _inspection(inspection_id)
    _require_editable(insp)
    item = _item(inspection_id, item_id)
    etype = item["requirement_snapshot"]["evidence_type"]
    observation = (observation or "").strip() or None
    override_note = (override_note or "").strip() or None
    problems: list[str] = []

    if decision == "pass":
        if needs_photo(etype) and _evidence_count(item_id) == 0:
            problems.append("Photo evidence is required before this requirement can pass.")
        if needs_manual(etype) and not manual_confirmed:
            problems.append("The inspector must confirm the physical check (manual confirmation).")
        if item["status"] == "more_evidence_requested" and item.get("status_reason") == "supervisor_request":
            if needs_photo(etype):
                problems.append("The supervisor requested new evidence for this requirement. Submit a new photo first.")
            elif not observation:
                problems.append("The supervisor asked for this check to be repeated. Describe what you re-checked "
                                "in the observation.")
        elif assessment_flags_insufficient(_latest_assessment(item_id)) and not override_note:
            problems.append("The AI assessment recommends another photo. Retake the photo, or record an override "
                            "justification explaining why the evidence is sufficient.")
        if _has_open_finding(item_id):
            problems.append("This requirement has an open finding. Void it (if raised in error) before passing.")
        new_status = "passed"
    elif decision == "fail":
        if needs_photo(etype) and _evidence_count(item_id) == 0:
            problems.append("Photo evidence of the condition is required to fail this requirement.")
        if not finding or not (finding.get("description") or "").strip():
            problems.append("A finding description is required when a requirement fails.")
        elif finding.get("severity") not in SEVERITIES:
            problems.append(f"Finding severity must be one of {', '.join(SEVERITIES)}.")
        new_status = "failed"
    elif decision == "not_applicable":
        if not observation:
            problems.append("A justification is required to mark a requirement not applicable.")
        if _has_open_finding(item_id):
            problems.append("This requirement has an open finding. Void it (if raised in error) first.")
        new_status = "not_applicable"
    else:
        raise WorkflowError(f"Unknown decision '{decision}'", 400)
    if problems:
        raise WorkflowError("Requirement cannot be dispositioned", 422, [{"reason": p} for p in problems])

    ts = db.now()
    changed = db.update("inspection_items", {
        "status": new_status, "status_reason": None, "observation": observation,
        "manual_confirmed": bool(manual_confirmed), "override_note": override_note, "decided_by": actor,
        "updated_at": ts}, {"id": item_id, "status": item["status"]})
    if not changed:
        raise _changed_concurrently()
    finding_id = None
    if decision == "fail":
        existing = db.first("findings", {"inspection_item_id": item_id, "status": "open"}, columns="id")
        if existing:
            finding_id = existing["id"]
            db.update("findings", {"description": finding["description"].strip(), "severity": finding["severity"],
                                   "updated_at": ts}, {"id": finding_id})
        else:
            finding_id = db.new_id("fnd")
            db.insert("findings", {
                "id": finding_id, "inspection_id": inspection_id, "product_instance_id": insp["product_instance_id"],
                "component_id": item["component_id"], "requirement_id": item["requirement_id"],
                "inspection_item_id": item_id, "description": finding["description"].strip(),
                "severity": finding["severity"], "status": "open", "assigned_to": None, "created_by": actor,
                "created_at": ts, "updated_at": ts, "closed_at": None})
            db.log_event("finding", finding_id, "finding_created", actor,
                         {"inspection_id": inspection_id, "component_id": item["component_id"],
                          "severity": finding["severity"]})
    db.log_event("inspection_item", item_id, f"item_{new_status}", actor,
                 {"inspection_id": inspection_id, "override_note": override_note, "finding_id": finding_id})
    _touch(inspection_id)
    return {"item_id": item_id, "status": new_status, "finding_id": finding_id}


def readiness(inspection_id: str, bundle: dict[str, Any] | None = None) -> dict[str, Any]:
    bundle = bundle or load_bundle(inspection_id)
    insp, items, findings = bundle["inspection"], bundle["items"], bundle["findings"]
    evidence_count, latest_assessment = _latest_by_item(bundle)
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
        if it["status"] in ("passed", "failed") and needs_photo(etype) and not evidence_count.get(it["id"]):
            blocking.append(entry(it, "Required photo evidence missing"))
        if it["status"] == "failed" and not any(f["inspection_item_id"] == it["id"] for f in findings):
            blocking.append(entry(it, "Failed requirement has no recorded finding"))
        if it["status"] == "not_applicable" and it["required"]:
            warnings.append(entry(it, "Mandatory requirement marked not applicable (documented exception for supervisor)"))
        if it["override_note"] and it["status"] == "passed":
            warnings.append(entry(it, "Passed with AI evidence recommendation overridden"))
        if it["status"] == "passed":
            latest = latest_assessment.get(it["id"])
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


def submit(inspection_id: str, actor: str) -> dict[str, Any]:
    insp = _inspection(inspection_id)
    check = readiness(inspection_id)
    if not check["ready"]:
        raise WorkflowError("Inspection cannot be submitted yet", 409, check["blocking"])
    ts = db.now()
    if not db.update("inspections", {"status": "submitted", "submitted_at": ts, "updated_at": ts},
                     {"id": inspection_id, "status": insp["status"]}):
        raise _changed_concurrently()
    db.log_event("inspection", inspection_id, "inspection_submitted", actor,
                 {"previous_status": insp["status"], "warnings": len(check["warnings"])})
    return {"inspection_id": inspection_id, "status": "submitted", "warnings": check["warnings"]}


def review(inspection_id: str, *, reviewer: str, decision: str,
           comments: str | None, item_ids: list[str] | None) -> dict[str, Any]:
    insp = _inspection(inspection_id)
    if insp["status"] != "submitted":
        raise WorkflowError(f"Only submitted inspections can be reviewed (status is '{insp['status']}')")
    if reviewer.strip().lower() == insp["inspector"].strip().lower():
        raise WorkflowError("The reviewer must be a different person from the inspector", 403)
    if decision == "approve":
        status = "approved"
    elif decision == "reject":
        if not (comments or "").strip():
            raise WorkflowError("A comment is required to reject an inspection", 422)
        status = "rejected"
    elif decision == "request_evidence":
        if not item_ids:
            raise WorkflowError("Select at least one requirement that needs additional evidence", 422)
        valid = {r["id"] for r in db.select("inspection_items", {"inspection_id": inspection_id}, columns="id")}
        if not set(item_ids) <= valid:
            raise WorkflowError("Unknown inspection item in request", 422)
        status = "changes_requested"
    else:
        raise WorkflowError(f"Unknown review decision '{decision}'", 400)
    ts = db.now()
    # Claim the decision first: a second reviewer acting at the same time gets a 409 instead of a double review.
    if not db.update("inspections", {"status": status, "decided_at": ts if status in ("approved", "rejected") else None,
                                     "updated_at": ts}, {"id": inspection_id, "status": "submitted"}):
        raise _changed_concurrently()
    if decision == "request_evidence":
        db.update("inspection_items", {"status": "more_evidence_requested", "status_reason": "supervisor_request",
                                       "updated_at": ts}, {"id": list(item_ids)})
        for iid in item_ids:
            db.log_event("inspection_item", iid, "more_evidence_requested", reviewer, {"comments": comments},
                         inspection_id=inspection_id)
    db.insert("reviews", {"id": db.new_id("rev"), "inspection_id": inspection_id, "reviewer": reviewer,
                          "decision": decision, "comments": comments, "item_ids": item_ids or [], "created_at": ts})
    db.log_event("inspection", inspection_id, f"review_{decision}", reviewer, {"comments": comments})
    return {"inspection_id": inspection_id, "status": status}


# ---------------------------------------------------------------- findings --

def transition_finding(finding_id: str, *, to: str, actor: str,
                       assigned_to: str | None = None, note: str | None = None) -> dict[str, Any]:
    f = db.first("findings", {"id": finding_id})
    if not f:
        raise WorkflowError("Finding not found", 404)
    if to not in FINDING_TRANSITIONS.get(f["status"], set()):
        raise WorkflowError(f"Finding cannot move from '{f['status']}' to '{to}'")
    ca = db.first("corrective_actions", {"finding_id": finding_id}, order=["-created_at", "-id"])
    note = (note or "").strip() or None
    finding_values: dict[str, Any] = {}
    # Validate everything before the first write.
    if to == "assigned":
        assigned_to = (assigned_to or f.get("assigned_to") or "").strip()
        if not assigned_to:
            raise WorkflowError("assigned_to is required", 422)
        finding_values["assigned_to"] = assigned_to
    elif to == "void":
        if not note:
            raise WorkflowError("A reason is required to void a finding", 422)
    elif to == "action_recorded":
        if not note:
            raise WorkflowError("Describe the corrective action taken", 422)
    elif to == "closed":
        if ca and ca.get("recorded_by") and ca["recorded_by"].strip().lower() == actor.strip().lower():
            raise WorkflowError("Verification must be performed by someone other than the person who did the work", 403)
        if not db.count("evidence", {"finding_id": finding_id, "kind": "corrective_after"}):
            raise WorkflowError("An 'after' photo of the corrected condition is required to close the finding", 422)
    ts = db.now()
    if not db.update("findings", {**finding_values, "status": to, "updated_at": ts,
                                  "closed_at": ts if to in ("closed", "void") else None},
                     {"id": finding_id, "status": f["status"]}):
        raise _changed_concurrently()
    if to == "assigned":
        if ca:
            db.update("corrective_actions", {"status": "assigned", "assigned_to": assigned_to, "updated_at": ts},
                      {"id": ca["id"]})
        else:
            db.insert("corrective_actions", {
                "id": db.new_id("ca"), "finding_id": finding_id, "assigned_to": assigned_to, "description": None,
                "status": "assigned", "recorded_by": None, "verified_by": None, "created_at": ts, "updated_at": ts})
    elif to == "action_recorded":
        db.update("corrective_actions", {"status": "action_recorded", "description": note, "recorded_by": actor,
                                         "updated_at": ts}, {"id": ca["id"]})
    elif to == "awaiting_verification":
        db.update("corrective_actions", {"status": "awaiting_verification", "updated_at": ts}, {"id": ca["id"]})
    elif to == "closed" and ca:
        db.update("corrective_actions", {"status": "closed", "verified_by": actor, "updated_at": ts}, {"id": ca["id"]})
    db.log_event("finding", finding_id, f"finding_{to}", actor,
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
