import { useEffect, useRef, useState, type ReactNode } from "react";
import { Circle, CircleAlert, CircleCheck, CircleX, Flag, type LucideIcon } from "lucide-react";
import type { Counts, TaskStatus } from "../api";
import { locale, t } from "../i18n";

// Every status has an icon too, so it can be recognised at a glance (and without reading).
export const TASK_ICON: Record<TaskStatus, LucideIcon> = {
  pending: Circle,
  passed: CircleCheck,
  failed: CircleX,
  flagged: Flag,
};

export const TASK_LABEL: Record<TaskStatus, string> = {
  pending: "To do",
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

export function Chip({ tone = "neutral", icon: Icon, children }: { tone?: string; icon?: LucideIcon; children: ReactNode }) {
  return <span className={`chip chip-${tone}`}>{Icon && <Icon aria-hidden />}{children}</span>;
}

export function StatusChip({ status }: { status: TaskStatus }) {
  return <Chip tone={TASK_TONE[status]} icon={TASK_ICON[status]}>{t(TASK_LABEL[status])}</Chip>;
}

// Progress of a job: tasks with a decision (passed or failed) out of all tasks.
export function Progress({ counts }: { counts: Counts }) {
  const done = counts.passed + counts.failed;
  const pct = counts.total ? Math.round((done / counts.total) * 100) : 0;
  return (
    <div className="progress" aria-label={t("{done} of {total} tasks done", { done, total: counts.total })}>
      <div className="progress-bar" style={{ width: `${pct}%` }} />
      <span>{t("{done} of {total} tasks done", { done, total: counts.total })}</span>
    </div>
  );
}

export function CountChips({ counts }: { counts: Counts }) {
  return (
    <span className="row-inline">
      {counts.flagged > 0 && <Chip tone="purple" icon={Flag}>{t("{n} flagged", { n: counts.flagged })}</Chip>}
      {counts.failed > 0 && <Chip tone="red" icon={CircleX}>{t("{n} failed", { n: counts.failed })}</Chip>}
      {counts.passed > 0 && <Chip tone="green" icon={CircleCheck}>{t("{n} passed", { n: counts.passed })}</Chip>}
      {counts.pending > 0 && <Chip icon={Circle}>{t("{n} pending", { n: counts.pending })}</Chip>}
    </span>
  );
}

// Server and client messages are English keys; shown in the reader's language.
export function ErrorBox({ error }: { error: string | null }) {
  if (!error) return null;
  return <div className="error-box with-icon-block" role="alert"><CircleAlert aria-hidden />{t(error)}</div>;
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
  return d.toLocaleString(locale(), { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

export function Lightbox({ src, onClose }: { src: string | null; onClose: () => void }) {
  if (!src) return null;
  return (
    <div className="lightbox" onClick={onClose} role="dialog">
      <img src={src} alt={t("Photo")} />
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
