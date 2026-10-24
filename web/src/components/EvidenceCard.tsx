import { useState } from "react";
import { api, type Assessment, type Evidence } from "../api";
import { when } from "./ui";

// Plain-language headline first; the full AI output stays one tap away for supervisors and auditors.
const HEADLINE: Record<string, { tone: string; icon: string; title: string; text: string }> = {
  accept_for_human_review: { tone: "green", icon: "✓", title: "Clear photo",
    text: "The AI can see what it needs. Now look at the part yourself and choose a result." },
  retake_photo: { tone: "amber", icon: "↻", title: "Please take another photo", text: "" },
  flag_for_human_review: { tone: "red", icon: "!", title: "Something to check",
    text: "The AI noticed something a person should look at:" },
};

export function AssessmentView({ a, onRetry }: { a: Assessment | null | undefined; onRetry?: () => void }) {
  if (!a) return <div className="ai ai-muted">No AI feedback for this photo.</div>;
  if (a.status !== "completed" || !a.result) {
    return (
      <div className="ai ai-muted">
        <div className="ai-head"><b>AI feedback isn't available right now</b> {onRetry && <button className="link" onClick={onRetry}>Try again</button>}</div>
        <div className="small">You can still check the part yourself and choose a result.</div>
        <details className="small"><summary>Technical details</summary>{a.status}: {a.error}</details>
      </div>
    );
  }
  const r = a.result;
  const h = HEADLINE[r.recommended_action] ?? { tone: "neutral", icon: "i", title: r.recommended_action, text: "" };
  return (
    <div className={`ai ai-${h.tone}`}>
      <div className="ai-head">
        <span className={`ai-icon ai-icon-${h.tone}`} aria-hidden="true">{h.icon}</span>
        <b className="ai-title">{h.title}</b>
        {a.origin === "precomputed" && <span className="chip chip-demo" title="Not a live inference">SAVED PRACTICE RESULT</span>}
      </div>
      {h.text && <p>{h.text}</p>}
      {r.recommended_action === "retake_photo" && r.retake_guidance && <p className="retake"><b>Tip:</b> {r.retake_guidance}</p>}
      {r.recommended_action === "flag_for_human_review" && r.conditions_for_human_review.length > 0 && (
        <ul className="flag">{r.conditions_for_human_review.map((o, i) => <li key={i}>{o}</li>)}</ul>
      )}
      <details className="ai-more">
        <summary>What the AI saw</summary>
        <p>{r.summary}</p>
        <div className="ai-grid small">
          <span>Right part visible: <b>{r.correct_area_visible}</b></span>
          <span>Photo quality: <b>{r.image_quality}</b></span>
          <span>How sure: <b>{{ low: "very", medium: "fairly", high: "not very" }[r.uncertainty] ?? r.uncertainty}</b></span>
        </div>
        {r.observations.length > 0 && <><h4>Seen in the photo</h4><ul>{r.observations.map((o, i) => <li key={i}>{o}</li>)}</ul></>}
        {r.missing_information.length > 0 && <><h4>Not visible</h4><ul>{r.missing_information.map((o, i) => <li key={i}>{o}</li>)}</ul></>}
        {r.limitations.length > 0 && <><h4>What a photo cannot prove</h4><ul className="muted">{r.limitations.map((o, i) => <li key={i}>{o}</li>)}</ul></>}
        <div className="tiny muted">
          {a.origin === "precomputed"
            ? `Real ${a.model} result saved ${a.captured_at ?? "earlier"} for this practice photo, shown without internet. Not a live analysis. `
            : `${a.provider} · ${a.model} · ${(a.latency_ms / 1000).toFixed(1)}s · `}
        </div>
      </details>
      <div className="tiny muted">The AI only helps. You decide the result.</div>
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
        <div className="tiny muted">{e.kind === "demo" && <span className="chip chip-demo">PRACTICE PHOTO</span>} {e.submitted_by} · {when(e.created_at)}{e.note ? ` · “${e.note}”` : ""}</div>
        {e.image_checks && !e.image_checks.passed && (
          <div className="small checks">Photo quality: {e.image_checks.issues.join(", ").toLowerCase()}</div>
        )}
        {retrying ? <div className="ai ai-muted"><span className="spinner" /> Checking the photo again…</div>
          : <AssessmentView a={e.assessment} onRetry={onChanged ? retry : undefined} />}
      </div>
    </div>
  );
}
