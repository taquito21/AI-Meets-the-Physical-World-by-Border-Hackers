import { useState } from "react";
import { api, type Assessment, type Evidence, type Job } from "../api";
import { Chip, when } from "./ui";

const ACTION_LABEL: Record<string, [string, string]> = {
  accept_for_human_review: ["Usable evidence", "green"],
  retake_photo: ["Retake recommended", "amber"],
  flag_for_human_review: ["Condition needs a human look", "red"],
};

export function AssessmentView({ a, onRetry }: { a: Assessment | null | undefined; onRetry?: () => void }) {
  if (!a?.status) return null; // photo stored without an AI review
  if (a.status !== "completed" || !a.result) {
    return (
      <div className="ai ai-muted">
        <div className="ai-head"><b>AI review {a.status}</b> {onRetry && <button className="link" onClick={onRetry}>Retry</button>}</div>
        <div className="small">{a.error}</div>
      </div>
    );
  }
  const r = a.result;
  const [label, tone] = ACTION_LABEL[r.recommended_action] ?? [r.recommended_action, "neutral"];
  return (
    <div className={`ai ai-${tone}`}>
      <div className="ai-head"><b>AI photo review</b> <Chip tone={tone}>{label}</Chip></div>
      <p>{r.summary}</p>
      <div className="ai-grid small">
        <span>Right area visible: <b>{r.correct_area_visible}</b></span>
        <span>Image quality: <b>{r.image_quality}</b></span>
        <span>Uncertainty: <b>{r.uncertainty}</b></span>
      </div>
      {r.observations.length > 0 && <><h4>Visible observations</h4><ul>{r.observations.map((o, i) => <li key={i}>{o}</li>)}</ul></>}
      {r.conditions_for_human_review.length > 0 && <><h4>Needs a human look</h4><ul className="flag">{r.conditions_for_human_review.map((o, i) => <li key={i}>{o}</li>)}</ul></>}
      {r.missing_information.length > 0 && <><h4>Missing</h4><ul>{r.missing_information.map((o, i) => <li key={i}>{o}</li>)}</ul></>}
      {r.retake_guidance && <p className="retake"><b>Retake guidance:</b> {r.retake_guidance}</p>}
      {r.limitations.length > 0 && <><h4>Limitations</h4><ul className="muted">{r.limitations.map((o, i) => <li key={i}>{o}</li>)}</ul></>}
      <div className="tiny muted">
        {a.model} · {((a.latency_ms ?? 0) / 1000).toFixed(1)}s · Advisory only: the worker and employer decide.
      </div>
    </div>
  );
}

export function EvidenceCard({ e, onOpen, onJob }: { e: Evidence; onOpen: (url: string) => void; onJob: (j: Job) => void }) {
  const [retrying, setRetrying] = useState(false);
  const retry = async () => {
    setRetrying(true);
    try {
      onJob(await api.reassess(e.id));
    } finally {
      setRetrying(false);
    }
  };
  const checks = e.ai_assessment?.image_checks;
  const byEmployer = e.created_by?.user_class === "employer";
  return (
    <div className={`evidence${e.photo_url ? "" : " evidence-text"}${byEmployer ? " evidence-employer" : ""}`}>
      {e.photo_url && <img src={e.photo_url} alt="Evidence" onClick={() => onOpen(e.photo_url!)} loading="lazy" />}
      <div className="evidence-body">
        <div className="tiny muted">
          <b>{e.created_by?.username ?? "Unknown"}</b>{byEmployer && " (employer)"} · {when(e.created_at)}
        </div>
        {e.text && <p className="evidence-note">{e.text}</p>}
        {checks && !checks.passed && <div className="small checks">Image checks: {checks.issues.join(", ")}</div>}
        {e.photo_url && (retrying ? <div className="ai ai-muted"><span className="spinner" /> Re-assessing…</div>
          : <AssessmentView a={e.ai_assessment} onRetry={retry} />)}
      </div>
    </div>
  );
}
