import { useEffect, useState } from "react";
import { ArrowLeft, CircleCheck, CircleX, ClipboardCheck, GraduationCap, History, ListChecks, MessageSquare, Printer, TriangleAlert, Undo2, Wrench } from "lucide-react";
import { Link, useParams } from "react-router-dom";
import { api, ApiError, type InspectionState, type Revision } from "../api";
import { AssessmentView } from "../components/EvidenceCard";
import { Chip, ComponentChip, ErrorBox, IndustryChip, InspectionChip, ItemChip, Lightbox, ModeBadge, SEVERITY_LABEL, usePolling, when } from "../components/ui";
import { t } from "../i18n";
import { useSession } from "../session";

// Activity codes logged by the server (log_event), in plain words. Unknown codes are shown as they come.
const EVENT: Record<string, string> = {
  inspection_started: "started the inspection",
  evidence_submitted: "added a photo",
  item_reopened: "reopened a check",
  more_evidence_recommended: "suggested another photo",
  assessment_completed: "reviewed a photo",
  assessment_unavailable: "could not review a photo (not available)",
  assessment_failed: "could not review a photo (error)",
  assessment_refused: "declined to review a photo",
  item_passed: "marked a check as “Looks good”",
  item_failed: "marked a check as “Problem reported”",
  item_not_applicable: "marked a check as “Doesn't apply”",
  finding_created: "reported a problem",
  inspection_submitted: "sent the inspection for review",
  more_evidence_requested: "asked for changes on a check",
  review_approve: "approved the inspection",
  review_reject: "rejected the inspection",
  review_request_evidence: "asked for changes",
  finding_assigned: "assigned a problem",
  finding_void: "cancelled a problem (reported by mistake)",
  finding_action_recorded: "recorded a fix",
  finding_awaiting_verification: "asked someone to check a fix",
  finding_closed: "confirmed a fix and closed the problem",
  evidence_corrective_before: "added a photo before the fix",
  evidence_corrective_after: "added a photo after the fix",
  package_loaded: "loaded the engineering package",
};

// Supervisor decisions as stored by the server.
const DECISION: Record<string, string> = {
  approve: "approved the inspection",
  reject: "rejected the inspection",
  request_evidence: "asked for changes",
};

export default function Summary({ review = false }: { review?: boolean }) {
  const { id = "" } = useParams();
  const { name } = useSession();
  const [state, setState] = useState<InspectionState | null>(null);
  const [rev, setRev] = useState<Revision | null>(null);
  const [lightbox, setLightbox] = useState<string | null>(null);
  const [comments, setComments] = useState("");
  const [requested, setRequested] = useState<Set<string>>(new Set());
  const [err, setErr] = useState<ApiError | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.inspection(id).then((s) => { setState(s); return api.revision(s.revision_id).then(setRev); })
      .catch((e) => setErr(e));
  }, [id]);
  usePolling(() => api.inspection(id).then(setState).catch(() => undefined), 4000, [id]);

  if (!state || !rev) return <div className="page">{err ? <ErrorBox error={err} /> : <span className="muted">{t("Loading…")}</span>}</div>;
  const s = state.inspection;
  const compName = (cid: string) => rev.components.find((c) => c.id === cid)?.name ?? cid;

  const decide = async (decision: "approve" | "reject" | "request_evidence") => {
    setBusy(true);
    setErr(null);
    try {
      setState(await api.review(id, { reviewer: name, decision, comments, item_ids: [...requested] }));
      setRequested(new Set());
    } catch (e) {
      setErr(e as ApiError);
    } finally {
      setBusy(false);
    }
  };
  const toggle = (itemId: string) => {
    const n = new Set(requested);
    n.has(itemId) ? n.delete(itemId) : n.add(itemId);
    setRequested(n);
  };
  const canReview = review && s.status === "submitted";

  return (
    <div className="page report">
      <div className="card-head">
        <div>
          <h1>{review ? t("Inspection review") : t("Inspection summary")}</h1>
          <div className="muted small">{s.id}</div>
        </div>
        <div className="row">
          <IndustryChip industry={rev.industry} />
          <ModeBadge mode={s.mode} />
          <InspectionChip status={s.status} />
        </div>
      </div>
      {s.mode === "demo" && <div className="notice notice-demo with-icon-block"><GraduationCap aria-hidden /><span><b>{t("Practice inspection.")}</b> {t("It uses photos prepared in advance; it is not a record of a real inspection.")}</span></div>}
      <dl className="kv card">
        <dt>{t("Asset")}</dt><dd>{rev.product_name} ({rev.product_model_id}) · {rev.asset_category}</dd>
        <dt>{t("Serial number")}</dt><dd><Link to={`/p/${state.instance.serial_number}`}>{state.instance.serial_number}</Link></dd>
        <dt>{t("Engineering revision")}</dt><dd>{rev.revision} · {t("package {id}", { id: rev.engineering_package_id })}{rev.manifest.demonstration_package ? ` ${t("(demonstration)")}` : ""}</dd>
        <dt>{t("Procedure")}</dt><dd>{s.procedure_id}</dd>
        <dt>{t("Inspector")}</dt><dd>{s.inspector}</dd>
        <dt>{t("Started / submitted")}</dt><dd>{when(s.started_at)} / {when(s.submitted_at)}</dd>
        <dt>{t("Progress")}</dt><dd>{t("{rdone}/{rtotal} required · {done}/{total} total", { rdone: state.progress.required_done, rtotal: state.progress.required_total, done: state.progress.done, total: state.progress.total })}</dd>
        <dt>{t("Open findings")}</dt><dd>{state.findings.filter((f) => !["closed", "void"].includes(f.status)).length}</dd>
      </dl>

      {canReview && (
        <section className="card review-box">
          <h2 className="with-icon"><ClipboardCheck aria-hidden />{t("Your decision")}</h2>
          <ol className="small review-steps">
            <li>{t("Look at the photos and results below.")}</li>
            <li>{t("If a check needs a new photo or a second look, tick its box below.")}</li>
            <li>{t("Write a comment for the inspector, then choose.")}</li>
          </ol>
          <textarea rows={2} value={comments} onChange={(e) => setComments(e.target.value)} placeholder={t("Comment for the inspector (optional)")} />
          <div className="row">
            <button className="btn btn-green btn-big" disabled={busy} onClick={() => decide("approve")}><CircleCheck aria-hidden />{t("Approve")}</button>
            <button className="btn btn-big" disabled={busy || requested.size === 0} onClick={() => decide("request_evidence")}
              title={requested.size === 0 ? t("Tick at least one check below first") : undefined}><Undo2 aria-hidden />{t("Ask for changes ({n})", { n: requested.size })}</button>
            <button className="btn btn-red-ghost" disabled={busy} onClick={() => decide("reject")}><CircleX aria-hidden />{t("Reject")}</button>
          </div>
          <p className="tiny muted">{t("Reviewing as {name}. Approving does not close the problems found or release the equipment.", { name })}</p>
          <ErrorBox error={err} />
        </section>
      )}

      {state.findings.length > 0 && (
        <section className="card">
          <h2 className="with-icon"><TriangleAlert aria-hidden className="ico-red" />{t("Problems found")}</h2>
          {state.findings.map((f) => (
            <div key={f.id} className="finding-inline">
              <Chip tone={f.status === "closed" ? "green" : f.status === "void" ? "neutral" : "red"}>{t(SEVERITY_LABEL[f.severity] ?? f.severity)}</Chip>{" "}
              <b>{compName(f.component_id)}</b>: {f.description} <span className="muted small">· {f.created_by}</span>
            </div>
          ))}
          <Link to="/findings" className="small with-icon"><Wrench aria-hidden />{t("Go to problems to fix")}</Link>
        </section>
      )}

      <section className="card">
        <h2 className="with-icon"><ListChecks aria-hidden />{t("Parts and checks")}</h2>
        {rev.components.filter((c) => state.items.some((i) => i.component_id === c.id)).map((c) => {
          const st = state.component_status[c.id] ?? "not_inspected";
          return (
            <div key={c.id} className="sum-comp">
              <div className="card-head">
                <h3>{c.name} <span className="muted small">{c.part_number}</span></h3>
                <ComponentChip status={st} />
              </div>
              {state.items.filter((i) => i.component_id === c.id).map((it) => (
                <div key={it.id} className="sum-item">
                  <div className="row">
                    {canReview && <input type="checkbox" checked={requested.has(it.id)} onChange={() => toggle(it.id)} aria-label={t("Request evidence")} />}
                    <span className="grow">{it.requirement_snapshot.title}{!it.required && <span className="muted small"> {t("(optional)")}</span>}</span>
                    <ItemChip status={it.status} />
                  </div>
                  {(it.observation || it.override_note || it.manual_confirmed) && (
                    <div className="small muted">
                      {it.manual_confirmed && `${t("✓ Manual check confirmed.")} `}
                      {it.observation && `${t("Observation: {text}.", { text: it.observation })} `}
                      {it.override_note && t("AI recommendation overridden: {text}", { text: it.override_note })}
                    </div>
                  )}
                  {it.evidence.map((e) => (
                    <div className="sum-evidence" key={e.id}>
                      <img src={e.url} alt="" onClick={() => setLightbox(e.url)} />
                      <AssessmentView a={e.assessment} />
                    </div>
                  ))}
                </div>
              ))}
            </div>
          );
        })}
      </section>

      {state.reviews.length > 0 && (
        <section className="card">
          <h2 className="with-icon"><MessageSquare aria-hidden />{t("Supervisor decisions")}</h2>
          {state.reviews.map((r) => <div key={r.id} className="small">{when(r.created_at)}: <b>{r.reviewer}</b> {DECISION[r.decision] ? t(DECISION[r.decision]) : r.decision.replace("_", " ")}{r.comments ? `: “${r.comments}”` : ""}</div>)}
        </section>
      )}

      <section className="card">
        <h2 className="with-icon"><History aria-hidden />{t("Everything that happened")}</h2>
        <ul className="timeline">
          {state.activity.map((a) => (
            <li key={a.id}><span className="tiny muted">{when(a.created_at)}</span> <b>{a.actor === "ai" ? t("AI") : a.actor ?? t("system")}</b> {EVENT[a.event_type] ? t(EVENT[a.event_type]) : a.event_type.replace(/_/g, " ")}</li>
          ))}
        </ul>
      </section>
      <div className="row no-print">
        {["in_progress", "changes_requested"].includes(s.status) && <Link className="btn" to={`/inspections/${id}`}><ArrowLeft aria-hidden />{t("Back to inspection")}</Link>}
        <button className="btn btn-ghost" onClick={() => window.print()}><Printer aria-hidden />{t("Print / PDF")}</button>
      </div>
      <Lightbox src={lightbox} onClose={() => setLightbox(null)} />
    </div>
  );
}
