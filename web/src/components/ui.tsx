import { useEffect, useRef, useState } from "react";
import type { ComponentStatus, Issue, ItemStatus } from "../api";

// Plain-language labels: the people using the app are not necessarily technical.
export const ITEM_LABEL: Record<ItemStatus, string> = {
  pending: "To do",
  evidence_submitted: "Choose a result",
  more_evidence_requested: "New photo needed",
  passed: "Looks good",
  failed: "Problem reported",
  not_applicable: "Doesn't apply",
};

// Server messages rephrased for non-technical users (the reasons below them are already plain sentences).
const FRIENDLY_ERRORS: Record<string, string> = {
  "Requirement cannot be dispositioned": "Before you can save this:",
  "Inspection cannot be submitted yet": "A few checks are still missing. Tap one to go there:",
  "Cannot reach the server. Check the network connection.": "No connection to the server. Check the Wi-Fi or mobile data and try again.",
};

export const ITEM_TONE: Record<ItemStatus, string> = {
  pending: "neutral",
  evidence_submitted: "amber",
  more_evidence_requested: "amber",
  passed: "green",
  failed: "red",
  not_applicable: "neutral",
};

// Component-level states shared by every industry. "Inspected" means all requirements were dispositioned by a
// person (passed or N/A); attaching a photo alone never makes a component "Inspected".
export const COMPONENT_LABEL: Record<ComponentStatus, string> = {
  not_inspected: "Not checked yet",
  in_progress: "Partly done",
  pending: "Needs attention",
  accepted: "Done",
  finding: "Problem reported",
};

export const SEVERITY_LABEL: Record<string, string> = {
  low: "Minor", medium: "Moderate", high: "Serious", critical: "Critical: stop using it",
};

export const INSPECTION_LABEL: Record<string, string> = {
  in_progress: "In progress",
  submitted: "Sent for review",
  changes_requested: "Changes requested",
  approved: "Approved",
  rejected: "Rejected",
};

export function ModeBadge({ mode }: { mode: string | undefined | null }) {
  if (mode !== "demo") return <Chip tone="blue">Real inspection</Chip>;
  return <span className="chip chip-demo" title="Uses photos prepared in advance">Practice</span>;
}

export function IndustryChip({ industry }: { industry: string | undefined | null }) {
  const slug = (industry ?? "general").toLowerCase().replace(/[^a-z0-9]+/g, "-");
  return <span className={`chip chip-industry chip-ind-${slug}`}>{industry ?? "General"}</span>;
}

export const COMPONENT_TONE: Record<ComponentStatus, string> = {
  not_inspected: "neutral",
  in_progress: "amber",
  pending: "amber",
  accepted: "green",
  finding: "red",
};

export const INSPECTION_TONE: Record<string, string> = {
  in_progress: "blue",
  changes_requested: "amber",
  submitted: "amber",
  approved: "green",
  rejected: "red",
};

export function Chip({ tone = "neutral", children }: { tone?: string; children: React.ReactNode }) {
  return <span className={`chip chip-${tone}`}>{children}</span>;
}

export function Progress({ done, total }: { done: number; total: number }) {
  const pct = total ? Math.round((done / total) * 100) : 0;
  return (
    <div className="progress" aria-label={`${done} of ${total}`}>
      <div className="progress-bar" style={{ width: `${pct}%` }} />
      <span>{done} of {total} required checks done</span>
    </div>
  );
}

export function ErrorBox({ error, onSelect }: { error: { message: string; issues?: Issue[] } | null; onSelect?: (i: Issue) => void }) {
  if (!error) return null;
  return (
    <div className="error-box" role="alert">
      <strong>{FRIENDLY_ERRORS[error.message] ?? error.message}</strong>
      {!!error.issues?.length && (
        <ul>
          {error.issues.map((i, n) => (
            <li key={n}>
              {onSelect && i.component_id ? (
                <button className="link" onClick={() => onSelect(i)}>{i.title ?? i.component_id}</button>
              ) : i.title ? <b>{i.title}</b> : null}
              {i.title || i.component_id ? ": " : ""}{i.reason}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function usePolling(fn: () => void, ms: number, deps: unknown[] = []) {
  const saved = useRef(fn);
  saved.current = fn;
  useEffect(() => {
    const id = setInterval(() => {
      if (document.visibilityState === "visible") saved.current();
    }, ms);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ms, ...deps]);
}

export function when(ts: string | null | undefined): string {
  if (!ts) return "—";
  const d = new Date(ts);
  return d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

export function Lightbox({ src, onClose }: { src: string | null; onClose: () => void }) {
  if (!src) return null;
  return (
    <div className="lightbox" onClick={onClose} role="dialog">
      <img src={src} alt="Evidence" />
    </div>
  );
}

export function useAsync<T>(loader: () => Promise<T>, deps: unknown[]) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const reload = () => loader().then((d) => { setData(d); setError(null); }).catch((e) => setError(e.message));
  useEffect(() => {
    reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return { data, error, reload, setData };
}
