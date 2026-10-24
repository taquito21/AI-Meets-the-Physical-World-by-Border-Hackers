import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, ApiError, type InspectionState, type Issue, type Revision } from "../api";
import AssemblyViewer from "../components/AssemblyViewer";
import { StatusLegend } from "../components/ExplodeControl";
import { TechSheet } from "../components/TechSheet";
import { useAssemblyControls } from "../components/useAssemblyControls";
import RequirementCard from "../components/RequirementCard";
import { Chip, COMPONENT_LABEL, COMPONENT_TONE, ErrorBox, INSPECTION_TONE, Lightbox, ModeBadge, Progress, usePolling } from "../components/ui";
import { useSession } from "../session";

export default function Inspection() {
  const { id = "" } = useParams();
  const { name } = useSession();
  const nav = useNavigate();
  const [state, setStateRaw] = useState<InspectionState | null>(null);
  // Every write bumps the version; a poll that started before a write is discarded so it can't
  // overwrite fresher state returned by that write.
  const version = useRef(0);
  const setState = (s: InspectionState) => {
    version.current += 1;
    setStateRaw(s);
  };
  const [rev, setRev] = useState<Revision | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [lightbox, setLightbox] = useState<string | null>(null);
  const [submitErr, setSubmitErr] = useState<ApiError | null>(null);
  const [loadErr, setLoadErr] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const refresh = () => {
    const started = version.current;
    return api.inspection(id)
      .then((s) => { if (version.current === started) setState(s); })
      .catch(() => undefined); // transient poll failures keep the last good state
  };
  useEffect(() => {
    api.inspection(id).then((s) => {
      setState(s);
      return api.revision(s.revision_id).then(setRev);
    }).catch((e) => setLoadErr(e.message));
  }, [id]);
  usePolling(refresh, 5000, [id]); // picks up supervisor decisions made on another device

  const editable = !!state && ["in_progress", "changes_requested"].includes(state.inspection.status);
  const comp = rev?.components.find((c) => c.id === selected) ?? null;
  const items = useMemo(() => state?.items.filter((i) => i.component_id === selected) ?? [], [state, selected]);
  const compOrder = useMemo(() => (rev?.components ?? []).filter((c) => state?.items.some((i) => i.component_id === c.id)), [rev, state]);
  const { viewerProps, controls } = useAssemblyControls(rev?.components, selected);

  if (loadErr) return <div className="page"><ErrorBox error={{ message: loadErr }} /></div>;
  if (!state || !rev) return <div className="page muted">Loading inspection…</div>;

  const select = (cid: string | null) => {
    setSelected(cid);
    setSubmitErr(null);
  };
  const nextComponent = () => {
    const pending = compOrder.filter((c) => !["accepted"].includes(state.component_status[c.id]));
    const idx = pending.findIndex((c) => c.id === selected);
    const next = pending[(idx + 1) % Math.max(pending.length, 1)];
    if (next) select(next.id);
  };
  const submit = async () => {
    setSubmitting(true);
    setSubmitErr(null);
    try {
      setState(await api.submit(id, name));
      nav(`/inspections/${id}/summary`);
    } catch (e) {
      setSubmitErr(e as ApiError);
    } finally {
      setSubmitting(false);
    }
  };
  const onIssue = (i: Issue) => i.component_id && select(i.component_id);
  const findingsForComp = state.findings.filter((f) => f.component_id === selected);

  return (
    <div className="split">
      <div className="split-viewer">
        <div className="viewer-head">
          <div>
            <b>{rev.product_name}</b> · {state.instance.serial_number}
            <div className="tiny muted">{rev.industry} · Rev {rev.revision} · {state.inspection.procedure_id} · {state.inspection.inspector}</div>
          </div>
          <div className="row">
            <ModeBadge mode={state.inspection.mode} />
            <Chip tone={INSPECTION_TONE[state.inspection.status]}>{state.inspection.status.replace("_", " ")}</Chip>
          </div>
        </div>
        <AssemblyViewer assemblyUrl={rev.assembly_url} components={rev.components} status={state.component_status}
          selectedId={selected} onSelect={select} {...viewerProps} />
        {controls}
        <StatusLegend />
      </div>

      <div className="split-panel">
        <Progress done={state.progress.required_done} total={state.progress.required_total} />
        {state.inspection.mode === "demo" && (
          <div className="notice notice-demo"><b>Demo inspection.</b> Prepared photos are marked as demonstration material. AI results are either real calls made now or earlier real results labelled as precomputed. Live inspections never use demo material.</div>
        )}
        {rev.procedure?.safety_notes?.length > 0 && !selected && (
          <div className="notice small"><b>Safety:</b> {rev.procedure.safety_notes.join(" ")}</div>
        )}
        {!editable && (
          <div className="notice">This inspection is <b>{state.inspection.status.replace("_", " ")}</b> and is read-only. <Link to={`/inspections/${id}/summary`}>Open summary</Link></div>
        )}
        {state.inspection.status === "changes_requested" && (
          <div className="notice">The supervisor requested changes: {state.reviews[state.reviews.length - 1]?.comments}</div>
        )}

        {comp ? (
          <section className="card component">
            <div className="card-head">
              <div>
                <h2>{comp.name}</h2>
                <div className="muted small">{comp.part_number} · qty {comp.quantity} · {comp.id}</div>
              </div>
              <Chip tone={COMPONENT_TONE[state.component_status[comp.id] ?? "not_inspected"]}>
                {COMPONENT_LABEL[state.component_status[comp.id] ?? "not_inspected"]}
              </Chip>
            </div>
            <p className="small">{comp.description}</p>
            <details className="techsheet-wrap" open={!!comp.specs?.length}>
              <summary>Technical sheet</summary>
              <TechSheet comp={comp} />
            </details>
            <div className="row small">
              {rev.documents.filter((d) => comp.documents.includes(d.id)).map((d) => (
                <a key={d.id} href={d.url} target="_blank" rel="noreferrer" className="btn btn-ghost btn-small">{d.title}</a>
              ))}
            </div>
            {items.length === 0 && <p className="muted small">No inspection requirements are defined for this component in revision {rev.revision}.</p>}
            {items.map((it) => (
              <RequirementCard key={it.id} item={it} inspectionId={id} editable={editable} actor={name}
                onState={setState} onOpenImage={setLightbox} onRefresh={refresh}
                demoEvidence={state.inspection.mode === "demo" ? rev.demo_evidence.filter((d) => d.requirement_id === it.requirement_id) : []} />
            ))}
            {findingsForComp.map((f) => (
              <div key={f.id} className="finding-inline">
                <Chip tone="red">Finding · {f.severity}</Chip> {f.description} <span className="muted small">({f.status.replace(/_/g, " ")})</span>
              </div>
            ))}
            <div className="row">
              <button className="btn btn-ghost" onClick={() => select(null)}>All components</button>
              <button className="btn" onClick={nextComponent}>Next component →</button>
            </div>
          </section>
        ) : (
          <section className="card">
            <h2>Components</h2>
            <p className="muted small">Tap a part on the model or choose one below.</p>
            <ul className="list comp-list">
              {compOrder.map((c) => {
                const st = state.component_status[c.id] ?? "not_inspected";
                const its = state.items.filter((i) => i.component_id === c.id);
                return (
                  <li key={c.id} onClick={() => select(c.id)}>
                    <span className={`dot dot-${COMPONENT_TONE[st]}`} />
                    <span className="grow"><b>{c.name}</b> <span className="muted small">{c.part_number}</span></span>
                    <span className="small muted">{its.filter((i) => ["passed", "failed", "not_applicable"].includes(i.status)).length}/{its.length}</span>
                  </li>
                );
              })}
            </ul>
          </section>
        )}

        {editable && (
          <section className="card">
            <h2>Complete inspection</h2>
            {state.readiness.ready
              ? <p className="small">All mandatory requirements are dispositioned.</p>
              : <p className="small muted">{state.readiness.blocking.length} item(s) still block submission. The server checks this again on submit.</p>}
            {state.readiness.warnings.length > 0 && (
              <ul className="small warn-list">{state.readiness.warnings.map((w, i) => <li key={i}>{w.title ? <b>{w.title}: </b> : null}{w.reason}</li>)}</ul>
            )}
            <button className="btn btn-primary" disabled={submitting} onClick={submit}>
              {submitting ? "Submitting…" : "Submit for supervisor review"}
            </button>
            <ErrorBox error={submitErr} onSelect={onIssue} />
          </section>
        )}
        <Link className="btn btn-ghost" to={`/inspections/${id}/summary`}>Inspection summary</Link>
      </div>
      <Lightbox src={lightbox} onClose={() => setLightbox(null)} />
    </div>
  );
}
