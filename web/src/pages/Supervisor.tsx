import { Link } from "react-router-dom";
import { api } from "../api";
import { IndustryFilter } from "../components/IndustryFilter";
import { Chip, INSPECTION_LABEL, INSPECTION_TONE, IndustryChip, ModeBadge, useAsync, usePolling, when } from "../components/ui";
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
      {r.open_findings > 0 && <Chip tone="red">{r.open_findings} problem{r.open_findings > 1 ? "s" : ""} to fix</Chip>}
      <Chip tone={INSPECTION_TONE[r.status]}>{INSPECTION_LABEL[r.status] ?? r.status}</Chip>
    </li>
  );

  return (
    <div className="page">
      <div className="card-head">
        <h1>Review inspections</h1>
        <IndustryFilter industries={[...new Set(all.map((r) => r.industry))]} />
      </div>
      <section className="card">
        <h2>Waiting for your review ({queue.length})</h2>
        {queue.length ? <><p className="muted small">Tap one to open it, look at the photos and results, then approve it or ask for changes.</p><ul className="list">{queue.map((r) => <Row key={r.id} r={r} />)}</ul></>
          : <p className="muted small">Nothing to review right now. This list updates by itself.</p>}
      </section>
      <section className="card">
        <h2>Other inspections</h2>
        <ul className="list">{rest.map((r) => <Row key={r.id} r={r} />)}</ul>
      </section>
    </div>
  );
}
