import { useEffect, useRef, useState } from "react";
import type { ComponentStatus, Issue, ItemStatus } from "../api";

export const ITEM_LABEL: Record<ItemStatus, string> = {
  pending: "Not inspected",
  evidence_submitted: "Awaiting decision",
  more_evidence_requested: "More evidence needed",
  passed: "Passed",
  failed: "Failed",
  not_applicable: "Not applicable",
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
  not_inspected: "Pending",
  in_progress: "In progress",
  pending: "Requires review",
  accepted: "Inspected",
  finding: "Finding reported",
};

export function ModeBadge({ mode }: { mode: string | undefined | null }) {
  if (mode !== "demo") return <Chip tone="blue">Live inspection</Chip>;
  return <span className="chip chip-demo" title="Uses prepared demonstration material">DEMO inspection</span>;
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
      <span>{done}/{total} required</span>
    </div>
  );
}

export function ErrorBox({ error, onSelect }: { error: { message: string; issues?: Issue[] } | null; onSelect?: (i: Issue) => void }) {
  if (!error) return null;
  return (
    <div className="error-box" role="alert">
      <strong>{error.message}</strong>
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
