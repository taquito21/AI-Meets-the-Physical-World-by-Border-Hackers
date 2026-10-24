import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  ArrowDown, ArrowLeft, ArrowRight, Camera, CircleCheck, FileText, Flag, GraduationCap, Hand, Info, ListChecks, Pointer,
  RefreshCw, Send, ShieldAlert, SkipForward, TriangleAlert, Undo2, type LucideIcon,
} from "lucide-react";
import { api, ApiError, type InspectionState, type Issue, type Item, type Revision } from "../api";
import AssemblyViewer from "../components/AssemblyViewer";
import { StatusLegend } from "../components/ExplodeControl";
import { TechSheet } from "../components/TechSheet";
import { useAssemblyControls } from "../components/useAssemblyControls";
import RequirementCard from "../components/RequirementCard";
import { COMPONENT_ICON, COMPONENT_TONE, Chip, ComponentChip, ErrorBox, INSPECTION_LABEL as STATUS_LABEL, InspectionChip, Lightbox, ModeBadge, Progress, usePolling } from "../components/ui";
import { t } from "../i18n";
import { useSession } from "../session";

const FINAL = ["passed", "failed", "not_applicable"];

// The single next thing to do for a check, in plain words.
function actionFor(it: Item): string {
  const photo = it.requirement_snapshot.evidence_type !== "manual_confirmation";
  if (it.status === "more_evidence_requested") return photo ? t("Take a new photo, then choose a result.") : t("Check it again, then choose a result.");
  if (it.status === "evidence_submitted") return t("Read the AI feedback, look at the part yourself, then choose a result.");
  return photo ? t("Take a photo, then choose a result.") : t("Check it in person, then choose a result.");
}

// The same action as a picture: camera = take a photo, hand = check it in person, pointer = your turn to choose.
function actionIcon(it: Item): LucideIcon {
  const photo = it.requirement_snapshot.evidence_type !== "manual_confirmation";
  if (it.status === "more_evidence_requested") return photo ? RefreshCw : Hand;
  if (it.status === "evidence_submitted") return Pointer;
  return photo ? Camera : Hand;
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
    const timer = setTimeout(() => {
      document.getElementById(scrollTo)?.scrollIntoView({ behavior: "smooth", block: "start" });
      setScrollTo(null);
    }, 80);
    return () => clearTimeout(timer);
  }, [scrollTo, selected]);

  const editable = !!state && ["in_progress", "changes_requested"].includes(state.inspection.status);
  const comp = rev?.components.find((c) => c.id === selected) ?? null;
  const items = useMemo(() => state?.items.filter((i) => i.component_id === selected) ?? [], [state, selected]);
  const compOrder = useMemo(() => (rev?.components ?? []).filter((c) => state?.items.some((i) => i.component_id === c.id)), [rev, state]);
  const { viewerProps, controls } = useAssemblyControls(rev?.components, selected);

  if (loadErr) return <div className="page"><ErrorBox error={{ message: loadErr }} /></div>;
  if (!state || !rev) return <div className="page muted">{t("Loading inspection…")}</div>;

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
  // Submit errors name each check in English; show the title the page already has in the reader's language.
  const shownSubmitErr = submitErr && {
    message: submitErr.message,
    issues: submitErr.issues?.map((i) => ({ ...i, title: state.items.find((it) => it.id === i.item_id)?.requirement_snapshot.title ?? i.title })),
  };
  const findingsForComp = state.findings.filter((f) => f.component_id === selected);
  const NextIcon = nextItem ? actionIcon(nextItem) : null;
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
            <InspectionChip status={status} />
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
          <div className="viewer-none with-icon"><Info aria-hidden />{t("This equipment has no 3D model. Choose a part from the list.")}</div>
        )}
      </div>

      <div className="split-panel">
        {editable && nextItem && NextIcon && (
          <section className="coach">
            <div className="coach-step">{t("Step {n} of {total}", { n: requiredItems.indexOf(nextItem) + 1, total: requiredItems.length })}</div>
            <div className="coach-main">
              <span className="coach-icon" aria-hidden><NextIcon /></span>
              <div>
                <div className="coach-title">{stepTitle(nextItem)}</div>
                <div className="coach-action">{actionFor(nextItem)}</div>
              </div>
            </div>
            <button className="btn btn-primary btn-big" onClick={goNext}>
              {selected === nextItem.component_id ? <>{t("Show me where")} <ArrowDown aria-hidden /></> : <>{t("Go to this step")} <ArrowRight aria-hidden /></>}
            </button>
          </section>
        )}
        {editable && !nextItem && (
          <section className="coach coach-done">
            <div className="coach-main">
              <span className="coach-icon" aria-hidden><CircleCheck /></span>
              <div className="coach-title">{t("All required checks are done")}</div>
            </div>
            <div className="coach-action">
              {t("Send the inspection so a supervisor can review it.")}
              {optionalLeft > 0 && " " + (optionalLeft > 1
                ? t("{n} optional checks are left; you can skip them.", { n: optionalLeft })
                : t("{n} optional check is left; you can skip it.", { n: optionalLeft }))}
            </div>
            <button className="btn btn-green btn-big" disabled={submitting} onClick={submit}>{submitting ? t("Sending…") : <><Send aria-hidden />{t("Send for review")}</>}</button>
          </section>
        )}
        <Progress done={state.progress.required_done} total={state.progress.required_total} />
        {state.inspection.mode === "demo" && (
          <div className="notice notice-demo with-icon-block"><GraduationCap aria-hidden /><span><b>{t("Practice mode.")}</b> {t("You can use photos prepared in advance. They are always labelled as practice and never count as a real inspection.")}</span></div>
        )}
        {rev.procedure?.safety_notes?.length > 0 && !selected && (
          <div className="notice small with-icon-block"><ShieldAlert aria-hidden className="ico-amber" /><span><b>{t("Before you start:")}</b> {rev.procedure.safety_notes.join(" ")}</span></div>
        )}
        {!editable && (
          <div className="notice with-icon-block">
            <Info aria-hidden />
            <span>
            {status === "submitted" ? t("Sent for review. A supervisor will check it; you don't need to do anything else.")
              : status === "approved" ? t("A supervisor approved this inspection.")
              : status === "rejected" ? t("A supervisor rejected this inspection.")
              : t("This inspection is {status} and can't be changed.", { status: t(STATUS_LABEL[status] ?? status) })}{" "}
            <Link to={`/inspections/${id}/summary`}>{t("See the report")}</Link>
            </span>
          </div>
        )}
        {status === "changes_requested" && (
          <div className="notice with-icon-block"><Undo2 aria-hidden className="ico-amber" /><span>{t("Your supervisor asked for changes: “{comments}”. The step above shows what to redo.", { comments: state.reviews[state.reviews.length - 1]?.comments ?? "" })}</span></div>
        )}

        {comp ? (
          <section className="card component" id="component-card">
            <div className="card-head">
              <div>
                <h2>{comp.name}</h2>
                {comp.quantity > 1 && <div className="muted small">{t("{n} pieces", { n: comp.quantity })}</div>}
              </div>
              <ComponentChip status={state.component_status[comp.id] ?? "not_inspected"} />
            </div>
            <p className="small">{comp.description}</p>
            {items.length === 0 && <p className="muted small">{t("Nothing to check on this part.")}</p>}
            {items.map((it) => (
              <RequirementCard key={it.id} item={it} inspectionId={id} editable={editable} actor={name}
                onState={setState} onOpenImage={setLightbox} onRefresh={refresh}
                demoEvidence={state.inspection.mode === "demo" ? rev.demo_evidence.filter((d) => d.requirement_id === it.requirement_id) : []} />
            ))}
            {findingsForComp.map((f) => (
              <div key={f.id} className="finding-inline">
                <Chip tone="red" icon={TriangleAlert}>{t("Problem reported")}</Chip> {f.description}
              </div>
            ))}
            {editable && compDone && (
              <div className="next-bar">
                {nextItem
                  ? <><span className="with-icon"><CircleCheck aria-hidden />{t("This part is done.")}</span><button className="btn btn-primary" onClick={goNext}>{t("Next: {part}", { part: partName(nextItem.component_id) })} <ArrowRight aria-hidden /></button></>
                  : <><span className="with-icon"><CircleCheck aria-hidden />{t("All required checks are done.")}</span><button className="btn btn-green" disabled={submitting} onClick={submit}><Send aria-hidden />{t("Send for review")}</button></>}
              </div>
            )}
            <details className="techsheet-wrap">
              <summary><Info aria-hidden />{t("Technical details and documents")}</summary>
              <div className="muted small">{t("Part number {number} · ID {id}", { number: comp.part_number, id: comp.id })}</div>
              <TechSheet comp={comp} />
              <div className="row small">
                {rev.documents.filter((d) => comp.documents.includes(d.id)).map((d) => (
                  <a key={d.id} href={d.url} target="_blank" rel="noreferrer" className="btn btn-ghost btn-small">{d.title}</a>
                ))}
              </div>
            </details>
            <div className="row">
              <button className="btn btn-ghost" onClick={() => select(null)}><ArrowLeft aria-hidden />{t("All parts")}</button>
              <button className="btn btn-ghost" onClick={nextComponent}><SkipForward aria-hidden />{t("Another part")}</button>
            </div>
          </section>
        ) : (
          <section className="card">
            <h2 className="with-icon"><ListChecks aria-hidden />{t("Parts to check")}</h2>
            <p className="muted small">{t("Follow the step above, or tap any part here or on the 3D model.")}</p>
            <ul className="list comp-list">
              {compOrder.map((c) => {
                const st = state.component_status[c.id] ?? "not_inspected";
                const its = state.items.filter((i) => i.component_id === c.id);
                const StatusIcon = COMPONENT_ICON[st];
                return (
                  <li key={c.id} onClick={() => select(c.id)}>
                    <StatusIcon aria-hidden className={`ico-${COMPONENT_TONE[st]}`} />
                    <span className="grow"><b>{c.name}</b></span>
                    <span className="small muted">{t("{done} of {total} done", { done: its.filter((i) => FINAL.includes(i.status)).length, total: its.length })}</span>
                  </li>
                );
              })}
            </ul>
          </section>
        )}

        {editable && (
          <section className="card">
            <h2 className="with-icon"><Flag aria-hidden />{t("Finish")}</h2>
            {state.readiness.ready
              ? <p className="small">{t("Everything required is done. You can send it now.")}</p>
              : <p className="small muted">{state.readiness.blocking.length === 1
                ? t("{n} required check still to do. If you try to send now, the app shows you which ones.", { n: state.readiness.blocking.length })
                : t("{n} required checks still to do. If you try to send now, the app shows you which ones.", { n: state.readiness.blocking.length })}</p>}
            {state.readiness.warnings.length > 0 && (
              <details className="small">
                <summary>{t("Notes for the supervisor ({n})", { n: state.readiness.warnings.length })}</summary>
                <ul className="warn-list">{state.readiness.warnings.map((w, i) => <li key={i}>{w.title ? <b>{w.title}: </b> : null}{t(w.reason)}</li>)}</ul>
              </details>
            )}
            <button className="btn btn-primary" disabled={submitting} onClick={submit}>
              {submitting ? t("Sending…") : <><Send aria-hidden />{t("Send for review")}</>}
            </button>
            <div id="submit-error"><ErrorBox error={shownSubmitErr} onSelect={onIssue} /></div>
          </section>
        )}
        <Link className="btn btn-ghost" to={`/inspections/${id}/summary`}><FileText aria-hidden />{t("See the report")}</Link>
      </div>
      <Lightbox src={lightbox} onClose={() => setLightbox(null)} />
    </div>
  );
}
