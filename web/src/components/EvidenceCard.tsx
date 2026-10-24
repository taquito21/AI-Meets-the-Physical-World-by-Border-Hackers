import { useState } from "react";
import { api, type Assessment, type Evidence } from "../api";
import { Chip, when } from "./ui";

const ACTION_LABEL: Record<string, [string, string]> = {
  accept_for_human_review: ["Usable evidence, inspector decides", "green"],
  retake_photo: ["Retake recommended", "amber"],
  flag_for_human_review: ["Condition flagged for human review", "red"],
};

export function AssessmentView({ a, onRetry }: { a: Assessment | null | undefined; onRetry?: () => void }) {
  if (!a) return <div className="ai ai-muted">No AI assessment recorded.</div>;
  if (a.status !== "completed" || !a.result) {
    return (
      <div className="ai ai-muted">
        <div className="ai-head"><b>AI assessment {a.status}</b> {onRetry && <button className="link" onClick={onRetry}>Retry</button>}</div>
        <div className="small">{a.error}</div>
        <div className="small muted">The requirement still needs the inspector's decision. No AI result was generated.</div>
      </div>
    );
  }
  const r = a.result;
  const [label, tone] = ACTION_LABEL[r.recommended_action] ?? [r.recommended_action, "neutral"];
  return (
    <div className={`ai ai-${tone}`}>
      <div className="ai-head">
        <b>AI-assisted evidence review</b> <Chip tone={tone}>{label}</Chip>
        {a.origin === "precomputed" && <span className="chip chip-demo" title="Not a live inference">DEMO RESULT · precomputed</span>}
      </div>
      <p>{r.summary}</p>
      <div className="ai-grid small">
        <span>Correct area visible: <b>{r.correct_area_visible}</b></span>
        <span>Image quality: <b>{r.image_quality}</b></span>
        <span>Uncertainty: <b>{r.uncertainty}</b></span>
      </div>
      {r.observations.length > 0 && <><h4>Visible observations</h4><ul>{r.observations.map((o, i) => <li key={i}>{o}</li>)}</ul></>}
      {r.conditions_for_human_review.length > 0 && <><h4>Needs human review</h4><ul className="flag">{r.conditions_for_human_review.map((o, i) => <li key={i}>{o}</li>)}</ul></>}
      {r.missing_information.length > 0 && <><h4>Missing</h4><ul>{r.missing_information.map((o, i) => <li key={i}>{o}</li>)}</ul></>}
      {r.retake_guidance && <p className="retake"><b>Retake guidance:</b> {r.retake_guidance}</p>}
      {r.limitations.length > 0 && <><h4>Limitations</h4><ul className="muted">{r.limitations.map((o, i) => <li key={i}>{o}</li>)}</ul></>}
      <div className="tiny muted">
        {a.origin === "precomputed"
          ? `Real ${a.model} result captured ${a.captured_at ?? "earlier"} for this demo photo, replayed offline. Not a live inference. `
          : `${a.provider} · ${a.model} · ${(a.latency_ms / 1000).toFixed(1)}s · `}
        Advisory only; does not certify the asset.
      </div>
    </div>
  );
}

export function EvidenceCard({ e, onOpen, onChanged }: { e: Evidence; onOpen: (url: string) => void; onChanged?: () => void }) {
  const [retrying, setRetrying] = useState(false);
  const retry = async () => {
    setRetrying(true);
    try {
      await api.reassess(e.id);
      onChanged?.();
    } finally {
      setRetrying(false);
    }
  };
  return (
    <div className="evidence">
      <img src={e.url} alt="Evidence" onClick={() => onOpen(e.url)} loading="lazy" />
      <div className="evidence-body">
        <div className="tiny muted">{e.kind === "demo" && <span className="chip chip-demo">DEMO PHOTO</span>} {e.submitted_by} · {when(e.created_at)}{e.note ? ` · “${e.note}”` : ""}</div>
        {e.image_checks && !e.image_checks.passed && (
          <div className="small checks">Image checks (heuristic): {e.image_checks.issues.join(", ")}</div>
        )}
        {retrying ? <div className="ai ai-muted"><span className="spinner" /> Re-assessing…</div>
          : <AssessmentView a={e.assessment} onRetry={onChanged ? retry : undefined} />}
      </div>
    </div>
  );
}
