import { Link } from "react-router-dom";
import { api } from "../api";
import { IndustryFilter } from "../components/IndustryFilter";
import { Chip, INSPECTION_TONE, IndustryChip, ModeBadge, useAsync, usePolling, when } from "../components/ui";
import { useSession } from "../session";

function Bars({ data, title }: { data: Record<string, number>; title: string }) {
  const entries = Object.entries(data).sort((a, b) => b[1] - a[1]);
  const max = Math.max(1, ...entries.map(([, v]) => v));
  return (
    <section className="card">
      <h2>{title}</h2>
      {entries.length === 0 && <p className="muted small">No data yet.</p>}
      {entries.map(([k, v]) => (
        <div key={k} className="bar-row">
          <span className="bar-label">{k.replace(/_/g, " ")}</span>
          <span className="bar-track"><span className="bar-fill" style={{ width: `${(v / max) * 100}%` }} /></span>
          <span className="bar-value">{v}</span>
        </div>
      ))}
    </section>
  );
}

export default function Dashboard() {
  const { industry } = useSession();
  const filter = industry === "All" ? undefined : industry;
  const { data, reload } = useAsync(() => api.dashboard(filter), [industry]);
  usePolling(reload, 5000, [industry]);
  if (!data) return <div className="page muted">Loading…</div>;
  const t = data.totals;
  const kpis: [string, string | number, string?][] = [
    ["Inspections", t.inspections, `${t.live} live · ${t.demo} demo`],
    ["Pending", t.pending, "in progress / changes requested"],
    ["Requires review", t.requires_review, "submitted to supervisor"],
    ["Approved", t.approved],
    ["Components inspected", t.components_inspected, `of ${t.components_total} in these inspections`],
    ["Findings", t.findings, `${t.open_findings} open`],
  ];
  return (
    <div className="page">
      <div className="card-head">
        <h1>Dashboard</h1>
        <IndustryFilter industries={data.industries} />
      </div>
      <p className="muted small">One data model for every industry: inspections, assets, components and evidence share the same records. Demo inspections are counted separately.</p>
      <div className="kpis">
        {kpis.map(([label, value, sub]) => (
          <div className="kpi" key={label}>
            <span className="kpi-label">{label}</span>
            <span className="kpi-value">{value}</span>
            {sub && <span className="kpi-sub">{sub}</span>}
          </div>
        ))}
      </div>
      <div className="grid-2">
        <Bars title="Inspections by industry" data={data.by_industry} />
        <Bars title="Inspections by asset type" data={data.by_asset} />
        <Bars title="Inspections by status" data={data.by_status} />
        <Bars title="Findings by severity" data={data.findings_by_severity} />
      </div>
      <section className="card">
        <h2>Recent inspections</h2>
        {data.recent.length === 0 && <p className="muted small">No inspections yet. Start one from <Link to="/catalog">Equipment</Link>.</p>}
        <ul className="list">
          {data.recent.map((r) => (
            <li key={r.id}>
              <IndustryChip industry={r.industry} />
              <Link to={["in_progress", "changes_requested"].includes(r.status) ? `/inspections/${r.id}` : `/inspections/${r.id}/summary`}>
                <b>{r.product_name}</b> · {r.serial_number}
              </Link>
              <span className="small muted">{r.inspector} · {when(r.updated_at)}</span>
              <ModeBadge mode={r.mode} />
              {r.open_findings > 0 && <Chip tone="red">{r.open_findings} open finding(s)</Chip>}
              <Chip tone={INSPECTION_TONE[r.status]}>{r.status.replace("_", " ")}</Chip>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
