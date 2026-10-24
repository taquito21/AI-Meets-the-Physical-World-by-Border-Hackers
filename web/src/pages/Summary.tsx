import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, ApiError, type InspectionState, type Revision } from "../api";
import { AssessmentView } from "../components/EvidenceCard";
import { Chip, COMPONENT_LABEL, COMPONENT_TONE, ErrorBox, INSPECTION_TONE, IndustryChip, ITEM_LABEL, ITEM_TONE, Lightbox, ModeBadge, usePolling, when } from "../components/ui";
import { useSession } from "../session";

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

  if (!state || !rev) return <div className="page">{err ? <ErrorBox error={err} /> : <span className="muted">Loading…</span>}</div>;
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
          <h1>Inspection {review ? "review" : "summary"}</h1>
          <div className="muted small">{s.id}</div>
        </div>
        <div className="row">
          <IndustryChip industry={rev.industry} />
          <ModeBadge mode={s.mode} />
          <Chip tone={INSPECTION_TONE[s.status]}>{s.status.replace("_", " ")}</Chip>
        </div>
      </div>
      {s.mode === "demo" && <div className="notice notice-demo"><b>Demo inspection.</b> Contains prepared demonstration photos; not a record of a real inspection.</div>}
      <dl className="kv card">
        <dt>Asset</dt><dd>{rev.product_name} ({rev.product_model_id}) · {rev.asset_category}</dd>
        <dt>Serial number</dt><dd><Link to={`/p/${state.instance.serial_number}`}>{state.instance.serial_number}</Link></dd>
        <dt>Engineering revision</dt><dd>{rev.revision} · package {rev.engineering_package_id}{rev.manifest.demonstration_package ? " (demonstration)" : ""}</dd>
        <dt>Procedure</dt><dd>{s.procedure_id}</dd>
        <dt>Inspector</dt><dd>{s.inspector}</dd>
        <dt>Started / submitted</dt><dd>{when(s.started_at)} / {when(s.submitted_at)}</dd>
        <dt>Progress</dt><dd>{state.progress.required_done}/{state.progress.required_total} required · {state.progress.done}/{state.progress.total} total</dd>
        <dt>Open findings</dt><dd>{state.findings.filter((f) => !["closed", "void"].includes(f.status)).length}</dd>
      </dl>

      {canReview && (
        <section className="card review-box">
          <h2>Supervisor decision</h2>
          <p className="small muted">Reviewing as <b>{name}</b>. To request more evidence, tick the requirements below. Approving the inspection does not close corrective actions or release the product.</p>
          <textarea rows={2} value={comments} onChange={(e) => setComments(e.target.value)} placeholder="Comments" />
          <div className="row">
            <button className="btn btn-green" disabled={busy} onClick={() => decide("approve")}>Approve inspection</button>
            <button className="btn" disabled={busy || requested.size === 0} onClick={() => decide("request_evidence")}>Request evidence ({requested.size})</button>
            <button className="btn btn-red-ghost" disabled={busy} onClick={() => decide("reject")}>Reject</button>
          </div>
          <ErrorBox error={err} />
        </section>
      )}

      {state.findings.length > 0 && (
        <section className="card">
          <h2>Findings</h2>
          {state.findings.map((f) => (
            <div key={f.id} className="finding-inline">
              <Chip tone={f.status === "closed" ? "green" : f.status === "void" ? "neutral" : "red"}>{f.severity}</Chip>{" "}
              <b>{compName(f.component_id)}</b>: {f.description} <span className="muted small">· {f.status.replace(/_/g, " ")} · {f.created_by}</span>
            </div>
          ))}
          <Link to="/findings" className="small">Manage corrective actions →</Link>
        </section>
      )}

      <section className="card">
        <h2>Components and requirements</h2>
        {rev.components.filter((c) => state.items.some((i) => i.component_id === c.id)).map((c) => {
          const st = state.component_status[c.id] ?? "not_inspected";
          return (
            <div key={c.id} className="sum-comp">
              <div className="card-head">
                <h3>{c.name} <span className="muted small">{c.part_number}</span></h3>
                <Chip tone={COMPONENT_TONE[st]}>{COMPONENT_LABEL[st]}</Chip>
              </div>
              {state.items.filter((i) => i.component_id === c.id).map((it) => (
                <div key={it.id} className="sum-item">
                  <div className="row">
                    {canReview && <input type="checkbox" checked={requested.has(it.id)} onChange={() => toggle(it.id)} aria-label="Request evidence" />}
                    <span className="grow">{it.requirement_snapshot.title}{!it.required && <span className="muted small"> (optional)</span>}</span>
                    <Chip tone={ITEM_TONE[it.status]}>{ITEM_LABEL[it.status]}</Chip>
                  </div>
                  {(it.observation || it.override_note || it.manual_confirmed) && (
                    <div className="small muted">
                      {it.manual_confirmed && "✓ Manual check confirmed. "}
                      {it.observation && `Observation: ${it.observation}. `}
                      {it.override_note && `AI recommendation overridden: ${it.override_note}`}
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
          <h2>Reviews</h2>
          {state.reviews.map((r) => <div key={r.id} className="small">{when(r.created_at)}: <b>{r.reviewer}</b> {r.decision.replace("_", " ")}{r.comments ? `: “${r.comments}”` : ""}</div>)}
        </section>
      )}

      <section className="card">
        <h2>Activity timeline</h2>
        <ul className="timeline">
          {state.activity.map((a) => (
            <li key={a.id}><span className="tiny muted">{when(a.created_at)}</span> <b>{a.actor ?? "system"}</b> {a.event_type.replace(/_/g, " ")}</li>
          ))}
        </ul>
      </section>
      <div className="row no-print">
        {["in_progress", "changes_requested"].includes(s.status) && <Link className="btn" to={`/inspections/${id}`}>Back to inspection</Link>}
        <button className="btn btn-ghost" onClick={() => window.print()}>Print / PDF</button>
      </div>
      <Lightbox src={lightbox} onClose={() => setLightbox(null)} />
    </div>
  );
}
