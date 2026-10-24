import { Link } from "react-router-dom";
import { CircleCheck, ClipboardList, Clock, ListChecks, Send, TriangleAlert, type LucideIcon } from "lucide-react";
import { api } from "../api";
import { IndustryFilter } from "../components/IndustryFilter";
import { Chip, INSPECTION_LABEL, IndustryChip, InspectionChip, ModeBadge, SEVERITY_LABEL, useAsync, usePolling, when } from "../components/ui";
import { t } from "../i18n";
import { useSession } from "../session";

const plain = (k: string) => k.replace(/_/g, " ");

function Bars({ data, title, label = plain }: { data: Record<string, number>; title: string; label?: (k: string) => string }) {
  const entries = Object.entries(data).sort((a, b) => b[1] - a[1]);
  const max = Math.max(1, ...entries.map(([, v]) => v));
  return (
    <section className="card">
      <h2>{title}</h2>
      {entries.length === 0 && <p className="muted small">{t("No data yet.")}</p>}
      {entries.map(([k, v]) => (
        <div key={k} className="bar-row">
          <span className="bar-label">{label(k)}</span>
          <span className="bar-track"><span className="bar-fill" style={{ width: `${(v / max) * 100}%` }} /></span>
          <span className="bar-value">{v}</span>
        </div>
      ))}
    </section>
  );
}

// The server sends codes for these breakdowns; show them as the same plain words used everywhere else.
const industryLabel = (k: string) => t(k);
const statusLabel = (k: string) => (INSPECTION_LABEL[k] ? t(INSPECTION_LABEL[k]) : plain(k));
const severityLabel = (k: string) => (SEVERITY_LABEL[k] ? t(SEVERITY_LABEL[k]) : plain(k));

export default function Dashboard() {
  const { industry } = useSession();
  const filter = industry === "All" ? undefined : industry;
  const { data, reload } = useAsync(() => api.dashboard(filter), [industry]);
  usePolling(reload, 5000, [industry]);
  if (!data) return <div className="page muted">{t("Loading…")}</div>;
  const n = data.totals;
  const kpis: [LucideIcon, string, string | number, string?][] = [
    [ClipboardList, t("Inspections"), n.inspections, t("{live} real · {demo} practice", { live: n.live, demo: n.demo })],
    [Clock, t("In progress"), n.pending, t("including changes requested")],
    [Send, t("Waiting for review"), n.requires_review, t("sent to a supervisor")],
    [CircleCheck, t("Approved inspections"), n.approved],
    [ListChecks, t("Parts checked"), n.components_inspected, t("of {n} in these inspections", { n: n.components_total })],
    [TriangleAlert, t("Problems"), n.findings, t("{n} still open", { n: n.open_findings })],
  ];
  return (
    <div className="page">
      <div className="card-head">
        <h1>{t("Dashboard")}</h1>
        <IndustryFilter industries={data.industries} />
      </div>
      <p className="muted small">{t("One data model for every industry: inspections, assets, components and evidence share the same records. Demo inspections are counted separately.")}</p>
      <div className="kpis">
        {kpis.map(([Icon, label, value, sub]) => (
          <div className="kpi" key={label}>
            <span className="kpi-label with-icon"><Icon aria-hidden />{label}</span>
            <span className="kpi-value">{value}</span>
            {sub && <span className="kpi-sub">{sub}</span>}
          </div>
        ))}
      </div>
      <div className="grid-2">
        <Bars title={t("Inspections by industry")} data={data.by_industry} label={industryLabel} />
        <Bars title={t("Inspections by asset type")} data={data.by_asset} />
        <Bars title={t("Inspections by status")} data={data.by_status} label={statusLabel} />
        <Bars title={t("Findings by severity")} data={data.findings_by_severity} label={severityLabel} />
      </div>
      <section className="card">
        <h2>{t("Recent inspections")}</h2>
        {data.recent.length === 0 && <p className="muted small">{t("No inspections yet. Start one from")} <Link to="/catalog">{t("Equipment")}</Link>.</p>}
        <ul className="list">
          {data.recent.map((r) => (
            <li key={r.id}>
              <IndustryChip industry={r.industry} />
              <Link to={["in_progress", "changes_requested"].includes(r.status) ? `/inspections/${r.id}` : `/inspections/${r.id}/summary`}>
                <b>{r.product_name}</b> · {r.serial_number}
              </Link>
              <span className="small muted">{r.inspector} · {when(r.updated_at)}</span>
              <ModeBadge mode={r.mode} />
              {r.open_findings > 0 && <Chip tone="red">{t(r.open_findings === 1 ? "{n} open finding" : "{n} open findings", { n: r.open_findings })}</Chip>}
              <InspectionChip status={r.status} />
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
