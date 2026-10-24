import { useState } from "react";
import {
  Ban, Camera, Check, CircleCheck, Eye, GraduationCap, Hand, ImagePlus, Images, Info, Lightbulb, Pointer, RefreshCw,
  Save, TriangleAlert, WifiOff, X, type LucideIcon,
} from "lucide-react";
import { api, ApiError, type DemoEvidence, type InspectionState, type Item } from "../api";
import { t } from "../i18n";
import { EvidenceCard } from "./EvidenceCard";
import { ProfileDetails } from "./ProfileDetails";
import { Chip, ErrorBox, ITEM_TONE, ItemChip, SEVERITY_LABEL, when } from "./ui";

interface Props {
  item: Item;
  inspectionId: string;
  editable: boolean;
  actor: string;
  onState: (s: InspectionState) => void;
  onOpenImage: (url: string) => void;
  onRefresh: () => void;
  demoEvidence?: DemoEvidence[]; // only passed for demo-mode inspections
}

export default function RequirementCard({ item, inspectionId, editable, actor, onState, onOpenImage, onRefresh, demoEvidence = [] }: Props) {
  const req = item.requirement_snapshot;
  const needsPhoto = req.evidence_type !== "manual_confirmation";
  const needsManual = req.evidence_type !== "photo";
  const [note, setNote] = useState("");
  const [observation, setObservation] = useState(item.observation ?? "");
  const [confirmed, setConfirmed] = useState(item.manual_confirmed);
  const [override, setOverride] = useState("");
  const [showOverride, setShowOverride] = useState(false);
  const [failing, setFailing] = useState(false);
  const [findingText, setFindingText] = useState("");
  const [severity, setSeverity] = useState("medium");
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<ApiError | null>(null);
  const [open, setOpen] = useState(item.status !== "passed" && item.status !== "not_applicable");

  const latest = item.evidence[item.evidence.length - 1];
  const aiFlagged = item.status === "more_evidence_requested" && item.status_reason === "ai_retake";
  const supervisorRequest = item.status === "more_evidence_requested" && item.status_reason === "supervisor_request";
  const done = ["passed", "failed", "not_applicable"].includes(item.status);
  const checkList: string[] = req.inspection_points?.length ? req.inspection_points : req.acceptance_criteria ?? [];

  const upload = async (file: File | undefined) => {
    if (!file) return;
    setBusy("upload");
    setErr(null);
    try {
      const r = await api.uploadEvidence(inspectionId, item.id, file, actor, note);
      setNote("");
      onState(r.state);
    } catch (e) {
      setErr(e as ApiError);
    } finally {
      setBusy(null);
    }
  };

  const attachDemo = async (demoId: string, liveAi: boolean) => {
    setBusy("upload");
    setErr(null);
    try {
      const r = await api.useDemoEvidence(inspectionId, item.id, demoId, actor, liveAi);
      onState(r.state);
    } catch (e) {
      setErr(e as ApiError);
    } finally {
      setBusy(null);
    }
  };

  const decide = async (decision: "pass" | "fail" | "not_applicable") => {
    setBusy(decision);
    setErr(null);
    try {
      const s = await api.decide(inspectionId, item.id, {
        decision, actor, observation, manual_confirmed: confirmed,
        override_note: showOverride ? override : undefined,
        finding: decision === "fail" ? { description: findingText, severity } : undefined,
      });
      setFailing(false);
      setShowOverride(false);
      onState(s);
    } catch (e) {
      setErr(e as ApiError);
    } finally {
      setBusy(null);
    }
  };

  // One plain sentence, with a matching picture, telling the person what to do right now.
  const [NowIcon, nowText]: [LucideIcon, string] =
    done ? [CircleCheck, t("Done. You can change the result below if needed.")]
    : busy === "upload" ? [RefreshCw, t("Checking your photo… this takes a few seconds.")]
    : supervisorRequest ? (needsPhoto ? [Camera, t("Your supervisor asked for a new photo.")]
      : [Hand, t("Your supervisor asked you to check this again. Write what you checked in the notes.")])
    : aiFlagged ? [RefreshCw, t("Take another photo, following the tip from the AI below.")]
    : needsPhoto && !latest ? [Camera, needsManual ? t("Step 1: take a photo. Step 2: check it in person and choose a result.") : t("Step 1: take a photo. Step 2: choose a result.")]
    : needsPhoto ? [Pointer, t("Step 2: read the AI feedback, look at the part yourself, then choose a result.")]
    : [Hand, t("Check it in person, then choose a result.")];
  const photoMissing = needsPhoto && !latest;

  return (
    <div className={`req req-${ITEM_TONE[item.status]}`} id={`req-${item.id}`}>
      <button className="req-head" onClick={() => setOpen(!open)} aria-expanded={open}>
        <span className="req-title">{req.title}</span>
        <span className="req-chips">
          {!item.required && <Chip>{t("Optional")}</Chip>}
          <ItemChip status={item.status} />
        </span>
      </button>
      {open && (
        <div className="req-body">
          {editable && <div className={`now now-${done ? "done" : "todo"}`}>{busy === "upload" ? <span className="spinner" /> : <NowIcon aria-hidden />} {nowText}</div>}
          <p>{req.instructions}</p>
          {checkList.length > 0 && (
            <>
              <h4 className="with-icon"><Eye aria-hidden />{t("Check that")}</h4>
              <ul className="checklist">{checkList.map((c) => <li key={c}>{c}</li>)}</ul>
            </>
          )}
          {needsPhoto && req.photo_guidance && <p className="small with-icon-block"><Lightbulb aria-hidden className="ico-amber" /><span><b>{t("Photo tip:")}</b> {req.photo_guidance}</span></p>}

          {item.evidence.map((e) => <EvidenceCard key={e.id} e={e} onOpen={onOpenImage} onChanged={editable ? onRefresh : undefined} />)}
          {item.observation && !editable && <p className="small"><b>{t("Notes:")}</b> {item.observation}</p>}
          {item.override_note && <p className="small"><b>{t("Photo used despite the AI tip, because:")}</b> {item.override_note}</p>}
          {item.decided_by && <p className="tiny muted">{t("Result chosen by {name}", { name: item.decided_by })}</p>}

          {editable && (
            <div className="actions">
              {needsPhoto && (
                <div className="capture">
                  <label className={`btn btn-primary btn-big ${busy === "upload" ? "disabled" : ""}`}>
                    {busy === "upload" ? <><span className="spinner" /> {t("Checking photo…")}</> : <><Camera aria-hidden />{latest ? t("Take another photo") : t("Take photo")}</>}
                    <input type="file" accept="image/*" capture="environment" hidden disabled={busy === "upload"}
                      onChange={(e) => { upload(e.target.files?.[0]); e.target.value = ""; }} />
                  </label>
                  <label className={`btn btn-ghost ${busy === "upload" ? "disabled" : ""}`}>
                    <Images aria-hidden />{t("Choose from gallery")}
                    <input type="file" accept="image/*" hidden disabled={busy === "upload"}
                      onChange={(e) => { upload(e.target.files?.[0]); e.target.value = ""; }} />
                  </label>
                  <input className="photo-note" value={note} onChange={(e) => setNote(e.target.value)} placeholder={t("Note for the photo (optional)")} />
                </div>
              )}
              {needsPhoto && demoEvidence.length > 0 && (
                <div className="demo-picker">
                  <div className="tiny"><span className="chip chip-demo"><GraduationCap aria-hidden />{t("PRACTICE")}</span> {t("Photos prepared in advance for practice. They are not from a real inspection.")}</div>
                  {demoEvidence.map((d) => (
                    <div key={d.id} className="demo-item">
                      <img src={d.url} alt={d.caption ?? t("Practice photo")} onClick={() => onOpenImage(d.url)} />
                      <div className="small">
                        <div>{d.caption}</div>
                        <div className="tiny muted">{d.source}</div>
                        <div className="row">
                          <button className="btn btn-small btn-demo" disabled={busy === "upload"} onClick={() => attachDemo(d.id, true)}>
                            <ImagePlus aria-hidden />{t("Use this photo")}
                          </button>
                          {d.has_precomputed_assessment && (
                            <button className="btn btn-small btn-ghost" disabled={busy === "upload"} onClick={() => attachDemo(d.id, false)}
                              title={t("Real result captured earlier with {model} on {when}", { model: String(d.precomputed_model), when: when(d.precomputed_at) })}>
                              <WifiOff aria-hidden />{t("No internet: use saved AI result")}
                            </button>
                          )}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {needsManual && (
                <label className="check">
                  <input type="checkbox" checked={confirmed} onChange={(e) => setConfirmed(e.target.checked)} />
                  <span className="with-icon"><Hand aria-hidden />{t("I checked this myself, in person")}</span>
                </label>
              )}
              {aiFlagged && !showOverride && (
                <div className="notice small">{t("Sure the photo is fine?")} <button className="link" onClick={() => setShowOverride(true)}>{t("Use it anyway and explain why")}</button>.</div>
              )}
              {showOverride && (
                <input value={override} onChange={(e) => setOverride(e.target.value)} placeholder={t("Why this photo is good enough")} />
              )}
              {failing && (
                <div className="finding-form">
                  <label className="small"><b>{t("What is wrong?")}</b>
                    <textarea value={findingText} onChange={(e) => setFindingText(e.target.value)} rows={2}
                      placeholder={t("For example: crack on the front left edge, about 3 cm")} />
                  </label>
                  <label className="small"><b>{t("How serious is it?")}</b>
                    <select value={severity} onChange={(e) => setSeverity(e.target.value)}>
                      {Object.entries(SEVERITY_LABEL).map(([v, l]) => <option key={v} value={v}>{t(l)}</option>)}
                    </select>
                  </label>
                </div>
              )}

              <div className="decide">
                <span className="decide-label">{done ? t("Change the result:") : t("Result:")}</span>
                <div className="row">
                  {failing ? (
                    <>
                      <button className="btn btn-red btn-big" disabled={!!busy} onClick={() => decide("fail")}>{busy === "fail" ? t("Saving…") : <><Save aria-hidden />{t("Save problem")}</>}</button>
                      <button className="btn btn-ghost" disabled={!!busy} onClick={() => setFailing(false)}><X aria-hidden />{t("Cancel")}</button>
                    </>
                  ) : (
                    <>
                      <button className="btn btn-green btn-big" disabled={!!busy || photoMissing} onClick={() => decide("pass")}
                        title={photoMissing ? t("Take a photo first") : undefined}>
                        {busy === "pass" ? t("Saving…") : <><Check aria-hidden />{t("Looks good")}</>}
                      </button>
                      <button className="btn btn-red-ghost btn-big" disabled={!!busy} onClick={() => setFailing(true)}><TriangleAlert aria-hidden />{t("Report a problem")}</button>
                      <button className="btn btn-ghost" disabled={!!busy} onClick={() => decide("not_applicable")}><Ban aria-hidden />{t("Doesn't apply")}</button>
                    </>
                  )}
                </div>
                {photoMissing && !failing && <p className="tiny muted">{t("Take a photo first to enable \"Looks good\".")}</p>}
                <textarea value={observation} onChange={(e) => setObservation(e.target.value)} rows={2}
                  placeholder={t("Notes (optional). If it doesn't apply, say why.")} />
              </div>
              <ErrorBox error={err} />
            </div>
          )}

          <details className="more">
            <summary><Info aria-hidden />{t("More details about this check")}</summary>
            <div className="small">
              <ProfileDetails req={req} skipPoints={!!req.inspection_points?.length} />
              {req.visual_limitations?.length > 0 && (
                <><h4>{t("What a photo cannot show")}</h4><ul className="muted">{req.visual_limitations.map((l: string) => <li key={l}>{l}</li>)}</ul></>
              )}
            </div>
          </details>
        </div>
      )}
    </div>
  );
}
