import { useEffect, useRef, useState, type ReactNode } from "react";
import type { Counts, TaskStatus } from "../api";

export const TASK_LABEL: Record<TaskStatus, string> = {
  pending: "Pending",
  passed: "Passed",
  failed: "Failed",
  flagged: "Flagged",
};

export const TASK_TONE: Record<TaskStatus, string> = {
  pending: "neutral",
  passed: "green",
  failed: "red",
  flagged: "purple",
};

export function Chip({ tone = "neutral", children }: { tone?: string; children: ReactNode }) {
  return <span className={`chip chip-${tone}`}>{children}</span>;
}

export function StatusChip({ status }: { status: TaskStatus }) {
  return <Chip tone={TASK_TONE[status]}>{TASK_LABEL[status]}</Chip>;
}

// Progress of a job: tasks with a decision (passed or failed) out of all tasks.
export function Progress({ counts }: { counts: Counts }) {
  const done = counts.passed + counts.failed;
  const pct = counts.total ? Math.round((done / counts.total) * 100) : 0;
  return (
    <div className="progress" aria-label={`${done} of ${counts.total} tasks done`}>
      <div className="progress-bar" style={{ width: `${pct}%` }} />
      <span>{done}/{counts.total} done</span>
    </div>
  );
}

export function CountChips({ counts }: { counts: Counts }) {
  return (
    <span className="row-inline">
      {counts.flagged > 0 && <Chip tone="purple">{counts.flagged} flagged</Chip>}
      {counts.failed > 0 && <Chip tone="red">{counts.failed} failed</Chip>}
      {counts.passed > 0 && <Chip tone="green">{counts.passed} passed</Chip>}
      {counts.pending > 0 && <Chip>{counts.pending} pending</Chip>}
    </span>
  );
}

export function ErrorBox({ error }: { error: string | null }) {
  if (!error) return null;
  return <div className="error-box" role="alert">{error}</div>;
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
