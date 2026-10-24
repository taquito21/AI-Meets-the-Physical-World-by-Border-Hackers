import { Link } from "react-router-dom";
import { Inbox, TriangleAlert } from "lucide-react";
import { api } from "../api";
import { IndustryFilter } from "../components/IndustryFilter";
import { Chip, IndustryChip, InspectionChip, ModeBadge, useAsync, usePolling, when } from "../components/ui";
import { t } from "../i18n";
import { useSession } from "../session";

export default function Supervisor() {
  const { industry } = useSession();
  const { data, reload } = useAsync(() => api.inspections(), []);
  usePolling(reload, 4000);
  const all = data ?? [];
  const rows = all.filter((r) => industry === "All" || r.industry === industry);
  const queue = rows.filter((r) => r.status === "submitted");
  const rest = rows.filter((r) => r.status !== "submitted");

  const Row = ({ r }: { r: (typeof rows)[number] }) => (
    <li>
      <IndustryChip industry={r.industry} />
      <Link to={r.status === "submitted" ? `/supervisor/${r.id}` : `/inspections/${r.id}/summary`}>
        <b>{r.product_name}</b> · {r.serial_number}
      </Link>
      <span className="small muted"> {r.inspector} · {when(r.submitted_at ?? r.updated_at)}</span>
      <ModeBadge mode={r.mode} />
      {r.open_findings > 0 && <Chip tone="red" icon={TriangleAlert}>{r.open_findings > 1 ? t("{n} problems to fix", { n: r.open_findings }) : t("{n} problem to fix", { n: r.open_findings })}</Chip>}
      <InspectionChip status={r.status} />
    </li>
  );

  return (
    <div className="page">
      <div className="card-head">
        <h1>{t("Review inspections")}</h1>
        <IndustryFilter industries={[...new Set(all.map((r) => r.industry))]} />
      </div>
      <section className="card">
        <h2 className="with-icon"><Inbox aria-hidden />{t("Waiting for your review ({n})", { n: queue.length })}</h2>
        {queue.length ? <><p className="muted small">{t("Tap one to open it, look at the photos and results, then approve it or ask for changes.")}</p><ul className="list">{queue.map((r) => <Row key={r.id} r={r} />)}</ul></>
          : <p className="muted small">{t("Nothing to review right now. This list updates by itself.")}</p>}
      </section>
      <section className="card">
        <h2>{t("Other inspections")}</h2>
        <ul className="list">{rest.map((r) => <Row key={r.id} r={r} />)}</ul>
      </section>
    </div>
  );
}
