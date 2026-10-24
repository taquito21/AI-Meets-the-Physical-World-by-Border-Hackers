import { useState } from "react";
import { api, ApiError, type DemoEvidence, type InspectionState, type Item } from "../api";
import { EvidenceCard } from "./EvidenceCard";
import { ProfileDetails } from "./ProfileDetails";
import { Chip, ErrorBox, ITEM_LABEL, ITEM_TONE } from "./ui";

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

  return (
    <div className={`req req-${ITEM_TONE[item.status]}`}>
      <button className="req-head" onClick={() => setOpen(!open)}>
        <span className="req-title">{req.title}</span>
        <span className="req-chips">
          {item.required ? <Chip tone="blue">Required</Chip> : <Chip>Optional</Chip>}
          <Chip tone={ITEM_TONE[item.status]}>{ITEM_LABEL[item.status]}</Chip>
        </span>
      </button>
      {open && (
        <div className="req-body">
          <p>{req.instructions}</p>
          <ProfileDetails req={req} />
          {needsPhoto && req.photo_guidance && <p className="small"><b>Photo required:</b> {req.photo_guidance}</p>}
          {req.visual_limitations?.length > 0 && <p className="small muted">Limits of visual inspection: {req.visual_limitations.join(" ")}</p>}
          {supervisorRequest && (
            <div className="notice">
              The supervisor requested additional evidence for this requirement.{" "}
              {needsPhoto ? "Take a new photo." : "Repeat the check and describe what you re-checked in the observation."}
            </div>
          )}
          {item.evidence.map((e) => <EvidenceCard key={e.id} e={e} onOpen={onOpenImage} onChanged={editable ? onRefresh : undefined} />)}
          {item.observation && !editable && <p className="small"><b>Observation:</b> {item.observation}</p>}
          {item.override_note && <p className="small"><b>AI recommendation overridden:</b> {item.override_note}</p>}
          {item.decided_by && <p className="tiny muted">Decision by {item.decided_by}</p>}

          {editable && (
            <div className="actions">
              {needsPhoto && (
                <div className="capture">
                  <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Optional note for this photo" />
                  <label className={`btn btn-primary ${busy === "upload" ? "disabled" : ""}`}>
                    {busy === "upload" ? <><span className="spinner" /> Analyzing evidence…</> : latest ? "Retake / add photo" : "Take photo"}
                    <input type="file" accept="image/*" capture="environment" hidden disabled={busy === "upload"}
                      onChange={(e) => { upload(e.target.files?.[0]); e.target.value = ""; }} />
                  </label>
                  <label className={`btn btn-ghost ${busy === "upload" ? "disabled" : ""}`}>
                    Attach photo
                    <input type="file" accept="image/*" hidden disabled={busy === "upload"}
                      onChange={(e) => { upload(e.target.files?.[0]); e.target.value = ""; }} />
                  </label>
                </div>
              )}
              {needsPhoto && demoEvidence.length > 0 && (
                <div className="demo-picker">
                  <div className="tiny"><span className="chip chip-demo">DEMO MATERIAL</span> Prepared photo for demonstration. It is not evidence from a real inspection.</div>
                  {demoEvidence.map((d) => (
                    <div key={d.id} className="demo-item">
                      <img src={d.url} alt={d.caption ?? "Demo photo"} onClick={() => onOpenImage(d.url)} />
                      <div className="small">
                        <div>{d.caption}</div>
                        <div className="tiny muted">{d.source}</div>
                        <div className="row">
                          <button className="btn btn-small btn-demo" disabled={busy === "upload"} onClick={() => attachDemo(d.id, true)}>
                            Use demo photo (live AI)
                          </button>
                          {d.has_precomputed_assessment && (
                            <button className="btn btn-small btn-ghost" disabled={busy === "upload"} onClick={() => attachDemo(d.id, false)}
                              title={`Real result captured earlier with ${d.precomputed_model} on ${d.precomputed_at}`}>
                              Offline: precomputed result
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
                  I physically performed this check{req.acceptance_criteria?.length ? ` (${req.acceptance_criteria.join("; ")})` : ""}
                </label>
              )}
              <textarea value={observation} onChange={(e) => setObservation(e.target.value)} rows={2}
                placeholder="Observation (required for Not applicable)" />
              {aiFlagged && !showOverride && (
                <div className="notice">The AI recommends another photo. Retake it, or <button className="link" onClick={() => setShowOverride(true)}>override with a justification</button>.</div>
              )}
              {showOverride && (
                <input value={override} onChange={(e) => setOverride(e.target.value)} placeholder="Why the current evidence is sufficient" />
              )}
              {failing && (
                <div className="finding-form">
                  <textarea value={findingText} onChange={(e) => setFindingText(e.target.value)} rows={2}
                    placeholder="Describe the finding (what, where, extent)" />
                  <select value={severity} onChange={(e) => setSeverity(e.target.value)}>
                    <option value="low">Low</option><option value="medium">Medium</option>
                    <option value="high">High</option><option value="critical">Critical</option>
                  </select>
                </div>
              )}
              <div className="row">
                <button className="btn btn-green" disabled={!!busy} onClick={() => decide("pass")}>{busy === "pass" ? "…" : "Pass"}</button>
                {failing ? (
                  <>
                    <button className="btn btn-red" disabled={!!busy} onClick={() => decide("fail")}>{busy === "fail" ? "…" : "Record finding"}</button>
                    <button className="btn btn-ghost" disabled={!!busy} onClick={() => setFailing(false)}>Cancel</button>
                  </>
                ) : (
                  <>
                    <button className="btn btn-red-ghost" disabled={!!busy} onClick={() => setFailing(true)}>Fail…</button>
                    <button className="btn btn-ghost" disabled={!!busy} onClick={() => decide("not_applicable")}>N/A</button>
                  </>
                )}
              </div>
              <ErrorBox error={err} />
            </div>
          )}
        </div>
      )}
    </div>
  );
}
