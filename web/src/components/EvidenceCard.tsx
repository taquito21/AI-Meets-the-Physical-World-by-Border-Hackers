import { useState } from "react";
import { Check, CircleAlert, CloudOff, Eye, GraduationCap, Hand, Info, Lightbulb, RefreshCw, Sparkles, type LucideIcon } from "lucide-react";
import { api, type Assessment, type Evidence } from "../api";
import { t } from "../i18n";
import { when } from "./ui";

// Plain-language headline first; the full AI output stays one tap away for supervisors and auditors.
// English keys here; translated with t() when shown.
const HEADLINE: Record<string, { tone: string; icon: LucideIcon; title: string; text: string }> = {
  accept_for_human_review: { tone: "green", icon: Check, title: "Clear photo",
    text: "The AI can see what it needs. Now look at the part yourself and choose a result." },
  retake_photo: { tone: "amber", icon: RefreshCw, title: "Please take another photo", text: "" },
  flag_for_human_review: { tone: "red", icon: Eye, title: "Something to check",
    text: "The AI noticed something a person should look at:" },
};

export function AssessmentView({ a, onRetry }: { a: Assessment | null | undefined; onRetry?: () => void }) {
  if (!a) return <div className="ai ai-muted">{t("No AI feedback for this photo.")}</div>;
  if (a.status !== "completed" || !a.result) {
    return (
      <div className="ai ai-muted">
        <div className="ai-head"><CloudOff aria-hidden /><b>{t("AI feedback isn't available right now")}</b> {onRetry && <button className="link with-icon" onClick={onRetry}><RefreshCw aria-hidden />{t("Try again")}</button>}</div>
        <div className="small">{t("You can still check the part yourself and choose a result.")}</div>
        <details className="small"><summary>{t("Technical details")}</summary>{a.status}: {a.error}</details>
      </div>
    );
  }
  const r = a.result;
  const known = HEADLINE[r.recommended_action];
  const h = known
    ? { ...known, title: t(known.title), text: known.text && t(known.text) }
    : { tone: "neutral", icon: Info, title: r.recommended_action, text: "" };
  const HeadIcon = h.icon;
  const sure = { low: "very", medium: "fairly", high: "not very" }[r.uncertainty];
  return (
    <div className={`ai ai-${h.tone}`}>
      <div className="ai-head">
        <span className={`ai-icon ai-icon-${h.tone}`} aria-hidden="true"><HeadIcon /></span>
        <b className="ai-title">{h.title}</b>
        {a.origin === "precomputed" && <span className="chip chip-demo" title={t("Not a live inference")}><GraduationCap aria-hidden />{t("SAVED PRACTICE RESULT")}</span>}
      </div>
      {h.text && <p>{h.text}</p>}
      {r.recommended_action === "retake_photo" && r.retake_guidance && <p className="retake with-icon-block"><Lightbulb aria-hidden className="ico-amber" /><span><b>{t("Tip:")}</b> {r.retake_guidance}</span></p>}
      {r.recommended_action === "flag_for_human_review" && r.conditions_for_human_review.length > 0 && (
        <ul className="flag">{r.conditions_for_human_review.map((o, i) => <li key={i}>{o}</li>)}</ul>
      )}
      <details className="ai-more">
        <summary><Sparkles aria-hidden />{t("What the AI saw")}</summary>
        <p>{r.summary}</p>
        <div className="ai-grid small">
          <span>{t("Right part visible:")} <b>{t(r.correct_area_visible)}</b></span>
          <span>{t("Photo quality:")} <b>{t(r.image_quality)}</b></span>
          <span>{t("How sure:")} <b>{sure ? t(sure) : r.uncertainty}</b></span>
        </div>
        {r.observations.length > 0 && <><h4>{t("Seen in the photo")}</h4><ul>{r.observations.map((o, i) => <li key={i}>{o}</li>)}</ul></>}
        {r.missing_information.length > 0 && <><h4>{t("Not visible")}</h4><ul>{r.missing_information.map((o, i) => <li key={i}>{o}</li>)}</ul></>}
        {r.limitations.length > 0 && <><h4>{t("What a photo cannot prove")}</h4><ul className="muted">{r.limitations.map((o, i) => <li key={i}>{o}</li>)}</ul></>}
        <div className="tiny muted">
          {a.origin === "precomputed"
            ? (a.captured_at
              ? t("Real {model} result saved {when} for this practice photo, shown without internet. Not a live analysis.", { model: String(a.model), when: when(a.captured_at) })
              : t("Real {model} result saved earlier for this practice photo, shown without internet. Not a live analysis.", { model: String(a.model) })) + " "
            : `${a.provider} · ${a.model} · ${(a.latency_ms / 1000).toFixed(1)}s · `}
        </div>
      </details>
      <div className="tiny muted with-icon"><Hand aria-hidden />{t("The AI only helps. You decide the result.")}</div>
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
      <img src={e.url} alt={t("Evidence")} onClick={() => onOpen(e.url)} loading="lazy" />
      <div className="evidence-body">
        <div className="tiny muted">{e.kind === "demo" && <span className="chip chip-demo"><GraduationCap aria-hidden />{t("PRACTICE PHOTO")}</span>} {e.submitted_by} · {when(e.created_at)}{e.note ? ` · “${e.note}”` : ""}</div>
        {e.image_checks && !e.image_checks.passed && (
          <div className="small checks with-icon"><CircleAlert aria-hidden />{t("Photo quality:")} {e.image_checks.issues.map((i) => t(i)).join(", ").toLowerCase()}</div>
        )}
        {retrying ? <div className="ai ai-muted"><span className="spinner" /> {t("Checking the photo again…")}</div>
          : <AssessmentView a={e.assessment} onRetry={onChanged ? retry : undefined} />}
      </div>
    </div>
  );
}
