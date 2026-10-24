import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, ApiError, type InspectionState, type Issue, type Item, type Revision } from "../api";
import AssemblyViewer from "../components/AssemblyViewer";
import { StatusLegend } from "../components/ExplodeControl";
import { TechSheet } from "../components/TechSheet";
import { useAssemblyControls } from "../components/useAssemblyControls";
import RequirementCard from "../components/RequirementCard";
import { Chip, COMPONENT_LABEL, COMPONENT_TONE, ErrorBox, INSPECTION_LABEL as STATUS_LABEL, INSPECTION_TONE, Lightbox, ModeBadge, Progress, usePolling } from "../components/ui";
import { useSession } from "../session";

const FINAL = ["passed", "failed", "not_applicable"];

// The single next thing to do for a check, in plain words.
function actionFor(it: Item): string {
  const photo = it.requirement_snapshot.evidence_type !== "manual_confirmation";
  if (it.status === "more_evidence_requested") return photo ? "Take a new photo, then choose a result." : "Check it again, then choose a result.";
  if (it.status === "evidence_submitted") return "Read the AI feedback, look at the part yourself, then choose a result.";
  return photo ? "Take a photo, then choose a result." : "Check it in person, then choose a result.";
}

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
  // Element to bring into view after the next render, so on a phone nobody has to hunt below the 3D view.
  const [scrollTo, setScrollTo] = useState<string | null>(null);

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
  useEffect(() => {
    if (!scrollTo) return;
    const t = setTimeout(() => {
      document.getElementById(scrollTo)?.scrollIntoView({ behavior: "smooth", block: "start" });
      setScrollTo(null);
    }, 80);
    return () => clearTimeout(t);
  }, [scrollTo, selected]);

  const editable = !!state && ["in_progress", "changes_requested"].includes(state.inspection.status);
  const comp = rev?.components.find((c) => c.id === selected) ?? null;
  const items = useMemo(() => state?.items.filter((i) => i.component_id === selected) ?? [], [state, selected]);
  const compOrder = useMemo(() => (rev?.components ?? []).filter((c) => state?.items.some((i) => i.component_id === c.id)), [rev, state]);
  const { viewerProps, controls } = useAssemblyControls(rev?.components, selected);

  if (loadErr) return <div className="page"><ErrorBox error={{ message: loadErr }} /></div>;
  if (!state || !rev) return <div className="page muted">Loading inspection…</div>;

  const select = (cid: string | null, target?: string) => {
    setSelected(cid);
    setSubmitErr(null);
    if (cid) setScrollTo(target ?? "component-card");
  };
  // Guided flow: required checks in the order of the parts; the first unfinished one is "the next step".
  const ordered = compOrder.flatMap((c) => state.items.filter((i) => i.component_id === c.id));
  const requiredItems = ordered.filter((i) => i.required);
  const nextItem = requiredItems.find((i) => !FINAL.includes(i.status)) ?? null;
  const optionalLeft = ordered.filter((i) => !i.required && !FINAL.includes(i.status)).length;
  const partName = (cid: string) => rev.components.find((c) => c.id === cid)?.name ?? cid;
  const goNext = () => nextItem && select(nextItem.component_id, `req-${nextItem.id}`);
  // "Seat cushion: Seat cushion upholstery" reads badly; only prefix the part when the check doesn't name it.
  const stepTitle = (it: Item) => {
    const part = partName(it.component_id), title = it.requirement_snapshot.title;
    return title.toLowerCase().startsWith(part.toLowerCase()) ? title : `${part}: ${title}`;
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
      setScrollTo("submit-error");
    } finally {
      setSubmitting(false);
    }
  };
  const onIssue = (i: Issue) => i.component_id && select(i.component_id, i.item_id ? `req-${i.item_id}` : undefined);
  const findingsForComp = state.findings.filter((f) => f.component_id === selected);
  const status = state.inspection.status;
  const compDone = items.length > 0 && items.every((i) => FINAL.includes(i.status));

  return (
    <div className="split">
      <div className="split-viewer">
        <div className="viewer-head">
          <div>
            <b>{rev.product_name}</b>
            <div className="tiny muted">{state.instance.metadata?.location ? `${state.instance.metadata.location} · ` : ""}{state.instance.serial_number}</div>
          </div>
          <div className="row">
            <ModeBadge mode={state.inspection.mode} />
            <Chip tone={INSPECTION_TONE[status]}>{STATUS_LABEL[status] ?? status.replace("_", " ")}</Chip>
          </div>
        </div>
        {rev.assembly_url ? (
          <>
            <AssemblyViewer assemblyUrl={rev.assembly_url} components={rev.components} status={state.component_status}
              selectedId={selected} onSelect={(cid) => select(cid)} {...viewerProps} />
            {controls}
            <StatusLegend />
          </>
        ) : (
          <div className="viewer-none">This equipment has no 3D model. Choose a part from the list.</div>
        )}
      </div>

      <div className="split-panel">
        {editable && nextItem && (
          <section className="coach">
            <div className="coach-step">Step {requiredItems.indexOf(nextItem) + 1} of {requiredItems.length}</div>
            <div className="coach-title">{stepTitle(nextItem)}</div>
            <div className="coach-action">{actionFor(nextItem)}</div>
            <button className="btn btn-primary btn-big" onClick={goNext}>
              {selected === nextItem.component_id ? "Show me where" : "Go to this step"}
            </button>
          </section>
        )}
        {editable && !nextItem && (
          <section className="coach coach-done">
            <div className="coach-title">All required checks are done ✓</div>
            <div className="coach-action">
              Send the inspection so a supervisor can review it.
              {optionalLeft > 0 && ` ${optionalLeft} optional check${optionalLeft > 1 ? "s are" : " is"} left; you can skip ${optionalLeft > 1 ? "them" : "it"}.`}
            </div>
            <button className="btn btn-green btn-big" disabled={submitting} onClick={submit}>{submitting ? "Sending…" : "Send for review"}</button>
          </section>
        )}
        <Progress done={state.progress.required_done} total={state.progress.required_total} />
        {state.inspection.mode === "demo" && (
          <div className="notice notice-demo"><b>Practice mode.</b> You can use photos prepared in advance. They are always labelled as practice and never count as a real inspection.</div>
        )}
        {rev.procedure?.safety_notes?.length > 0 && !selected && (
          <div className="notice small"><b>Before you start:</b> {rev.procedure.safety_notes.join(" ")}</div>
        )}
        {!editable && (
          <div className="notice">
            {status === "submitted" ? "Sent for review. A supervisor will check it; you don't need to do anything else."
              : status === "approved" ? "A supervisor approved this inspection."
              : status === "rejected" ? "A supervisor rejected this inspection."
              : `This inspection is ${STATUS_LABEL[status] ?? status} and can't be changed.`}{" "}
            <Link to={`/inspections/${id}/summary`}>See the report</Link>
          </div>
        )}
        {status === "changes_requested" && (
          <div className="notice">Your supervisor asked for changes: “{state.reviews[state.reviews.length - 1]?.comments}”. The step above shows what to redo.</div>
        )}

        {comp ? (
          <section className="card component" id="component-card">
            <div className="card-head">
              <div>
                <h2>{comp.name}</h2>
                {comp.quantity > 1 && <div className="muted small">{comp.quantity} pieces</div>}
              </div>
              <Chip tone={COMPONENT_TONE[state.component_status[comp.id] ?? "not_inspected"]}>
                {COMPONENT_LABEL[state.component_status[comp.id] ?? "not_inspected"]}
              </Chip>
            </div>
            <p className="small">{comp.description}</p>
            {items.length === 0 && <p className="muted small">Nothing to check on this part.</p>}
            {items.map((it) => (
              <RequirementCard key={it.id} item={it} inspectionId={id} editable={editable} actor={name}
                onState={setState} onOpenImage={setLightbox} onRefresh={refresh}
                demoEvidence={state.inspection.mode === "demo" ? rev.demo_evidence.filter((d) => d.requirement_id === it.requirement_id) : []} />
            ))}
            {findingsForComp.map((f) => (
              <div key={f.id} className="finding-inline">
                <Chip tone="red">Problem reported</Chip> {f.description}
              </div>
            ))}
            {editable && compDone && (
              <div className="next-bar">
                {nextItem
                  ? <><span>✓ This part is done.</span><button className="btn btn-primary" onClick={goNext}>Next: {partName(nextItem.component_id)} →</button></>
                  : <><span>✓ All required checks are done.</span><button className="btn btn-green" disabled={submitting} onClick={submit}>Send for review</button></>}
              </div>
            )}
            <details className="techsheet-wrap">
              <summary>Technical details and documents</summary>
              <div className="muted small">Part number {comp.part_number} · ID {comp.id}</div>
              <TechSheet comp={comp} />
              <div className="row small">
                {rev.documents.filter((d) => comp.documents.includes(d.id)).map((d) => (
                  <a key={d.id} href={d.url} target="_blank" rel="noreferrer" className="btn btn-ghost btn-small">{d.title}</a>
                ))}
              </div>
            </details>
            <div className="row">
              <button className="btn btn-ghost" onClick={() => select(null)}>← All parts</button>
              <button className="btn btn-ghost" onClick={nextComponent}>Another part</button>
            </div>
          </section>
        ) : (
          <section className="card">
            <h2>Parts to check</h2>
            <p className="muted small">Follow the step above, or tap any part here or on the 3D model.</p>
            <ul className="list comp-list">
              {compOrder.map((c) => {
                const st = state.component_status[c.id] ?? "not_inspected";
                const its = state.items.filter((i) => i.component_id === c.id);
                return (
                  <li key={c.id} onClick={() => select(c.id)}>
                    <span className={`dot dot-${COMPONENT_TONE[st]}`} />
                    <span className="grow"><b>{c.name}</b></span>
                    <span className="small muted">{its.filter((i) => FINAL.includes(i.status)).length} of {its.length} done</span>
                  </li>
                );
              })}
            </ul>
          </section>
        )}

        {editable && (
          <section className="card">
            <h2>Finish</h2>
            {state.readiness.ready
              ? <p className="small">Everything required is done. You can send it now.</p>
              : <p className="small muted">{state.readiness.blocking.length} required check{state.readiness.blocking.length === 1 ? "" : "s"} still to do. If you try to send now, the app shows you which ones.</p>}
            {state.readiness.warnings.length > 0 && (
              <details className="small">
                <summary>Notes for the supervisor ({state.readiness.warnings.length})</summary>
                <ul className="warn-list">{state.readiness.warnings.map((w, i) => <li key={i}>{w.title ? <b>{w.title}: </b> : null}{w.reason}</li>)}</ul>
              </details>
            )}
            <button className="btn btn-primary" disabled={submitting} onClick={submit}>
              {submitting ? "Sending…" : "Send for review"}
            </button>
            <div id="submit-error"><ErrorBox error={submitErr} onSelect={onIssue} /></div>
          </section>
        )}
        <Link className="btn btn-ghost" to={`/inspections/${id}/summary`}>See the report</Link>
      </div>
      <Lightbox src={lightbox} onClose={() => setLightbox(null)} />
    </div>
  );
}
