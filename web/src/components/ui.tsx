import { useEffect, useRef, useState } from "react";
import {
  Armchair, Ban, BadgeCheck, Circle, CircleAlert, CircleCheck, CircleDashed, CircleX, Clock, FireExtinguisher,
  GraduationCap, Pointer, RefreshCw, Send, Shapes, TriangleAlert, Undo2, Zap, type LucideIcon,
} from "lucide-react";
import type { ComponentStatus, Issue, ItemStatus } from "../api";
import { locale, t } from "../i18n";

// Every status also has an icon, so it can be recognised at a glance (and without reading English).
export const ITEM_ICON: Record<ItemStatus, LucideIcon> = {
  pending: Circle,
  evidence_submitted: Pointer,
  more_evidence_requested: RefreshCw,
  passed: CircleCheck,
  failed: TriangleAlert,
  not_applicable: Ban,
};

export const COMPONENT_ICON: Record<ComponentStatus, LucideIcon> = {
  not_inspected: Circle,
  in_progress: CircleDashed,
  pending: CircleAlert,
  accepted: CircleCheck,
  finding: TriangleAlert,
};

export const INSPECTION_ICON: Record<string, LucideIcon> = {
  in_progress: Clock,
  submitted: Send,
  changes_requested: Undo2,
  approved: CircleCheck,
  rejected: CircleX,
};

export const INDUSTRY_ICON: Record<string, LucideIcon> = {
  Furniture: Armchair,
  Electrical: Zap,
  "Facility Safety": FireExtinguisher,
};

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
  if (mode !== "demo") return <Chip tone="blue" icon={BadgeCheck}>{t("Real inspection")}</Chip>;
  return <span className="chip chip-demo" title={t("Uses photos prepared in advance")}><GraduationCap aria-hidden />{t("Practice")}</span>;
}

export function IndustryChip({ industry }: { industry: string | undefined | null }) {
  const slug = (industry ?? "general").toLowerCase().replace(/[^a-z0-9]+/g, "-");
  const Icon = INDUSTRY_ICON[industry ?? ""] ?? Shapes;
  return <span className={`chip chip-industry chip-ind-${slug}`}><Icon aria-hidden />{t(industry ?? "General")}</span>;
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

export function Chip({ tone = "neutral", icon: Icon, children }: { tone?: string; icon?: LucideIcon; children: React.ReactNode }) {
  return <span className={`chip chip-${tone}`}>{Icon && <Icon aria-hidden />}{children}</span>;
}

// Status chips: colour + icon + plain words, the same everywhere.
export const ItemChip = ({ status }: { status: ItemStatus }) =>
  <Chip tone={ITEM_TONE[status]} icon={ITEM_ICON[status]}>{t(ITEM_LABEL[status])}</Chip>;
export const ComponentChip = ({ status }: { status: ComponentStatus }) =>
  <Chip tone={COMPONENT_TONE[status]} icon={COMPONENT_ICON[status]}>{t(COMPONENT_LABEL[status])}</Chip>;
export const InspectionChip = ({ status }: { status: string }) =>
  <Chip tone={INSPECTION_TONE[status]} icon={INSPECTION_ICON[status]}>{t(INSPECTION_LABEL[status] ?? status.replace(/_/g, " "))}</Chip>;

export function Progress({ done, total }: { done: number; total: number }) {
  const pct = total ? Math.round((done / total) * 100) : 0;
  return (
    <div className="progress" aria-label={t("{done} of {total} required checks done", { done, total })}>
      <div className="progress-bar" style={{ width: `${pct}%` }} />
      <span>{t("{done} of {total} required checks done", { done, total })}</span>
    </div>
  );
}

export function ErrorBox({ error, onSelect }: { error: { message: string; issues?: Issue[] } | null; onSelect?: (i: Issue) => void }) {
  if (!error) return null;
  return (
    <div className="error-box" role="alert">
      <strong className="with-icon"><CircleAlert aria-hidden />{t(FRIENDLY_ERRORS[error.message] ?? error.message)}</strong>
      {!!error.issues?.length && (
        <ul>
          {error.issues.map((i, n) => (
            <li key={n}>
              {onSelect && i.component_id ? (
                <button className="link" onClick={() => onSelect(i)}>{i.title ?? i.component_id}</button>
              ) : i.title ? <b>{i.title}</b> : null}
              {i.title || i.component_id ? ": " : ""}{t(i.reason)}
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
  return d.toLocaleString(locale(), { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

export function Lightbox({ src, onClose }: { src: string | null; onClose: () => void }) {
  if (!src) return null;
  return (
    <div className="lightbox" onClick={onClose} role="dialog">
      <img src={src} alt={t("Evidence")} />
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
