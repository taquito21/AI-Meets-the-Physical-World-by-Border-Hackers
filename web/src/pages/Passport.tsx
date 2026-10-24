import { Fragment, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, ApiError } from "../api";
import { Chip, ErrorBox, INSPECTION_TONE, ModeBadge, useAsync, when } from "../components/ui";
import { useSession } from "../session";

export default function Passport() {
  const { serial = "" } = useParams();
  const { data, error } = useAsync(() => api.passport(serial), [serial]);
  const { name } = useSession();
  const nav = useNavigate();
  const [err, setErr] = useState<ApiError | null>(null);

  if (error) return <div className="page"><ErrorBox error={{ message: error }} /></div>;
  if (!data) return <div className="page muted">Loading…</div>;
  const start = async () => {
    try {
      const r = await api.startInspection(serial, name);
      nav(`/inspections/${r.inspection_id}`);
    } catch (e) {
      setErr(e as ApiError);
    }
  };
  return (
    <div className="page">
      <h1>Product passport</h1>
      <p className="muted small">Record for one physical unit. Opening it via a QR code or link identifies the record. It does not prove the unit is physically present.</p>
      <dl className="kv card">
        <dt>Serial number</dt><dd><b>{data.instance.serial_number}</b></dd>
        <dt>Product</dt><dd>{data.revision.product_name} · {data.revision.manufacturer}</dd>
        <dt>Engineering revision</dt><dd><Link to={`/products/${encodeURIComponent(data.revision.id)}`}>{data.revision.revision}</Link></dd>
        {Object.entries(data.instance.metadata as Record<string, string>).map(([k, v]) => <Fragment key={k}><dt>{k}</dt><dd>{v}</dd></Fragment>)}
      </dl>
      <button className="btn btn-primary" onClick={start}>Start or resume inspection</button>
      <ErrorBox error={err} />
      <section className="card">
        <h2>Inspection history</h2>
        {data.inspections.length === 0 && <p className="muted small">No inspections yet.</p>}
        <ul className="list">
          {data.inspections.map((i: any) => (
            <li key={i.id}>
              <Link to={`/inspections/${i.id}/summary`}>{when(i.started_at)}, {i.inspector}</Link> <ModeBadge mode={i.mode} /> <Chip tone={INSPECTION_TONE[i.status]}>{i.status.replace("_", " ")}</Chip>
            </li>
          ))}
        </ul>
      </section>
      <section className="card">
        <h2>Findings</h2>
        {data.findings.length === 0 && <p className="muted small">No findings.</p>}
        {data.findings.map((f: any) => <div key={f.id} className="small">{when(f.created_at)}: {f.mode === "demo" && <span className="chip chip-demo">Practice</span>} <b>{f.component_id}</b> {f.description} <Chip>{f.status.replace(/_/g, " ")}</Chip></div>)}
      </section>
      <section className="card">
        <h2>Timeline</h2>
        <ul className="timeline">
          {data.activity.map((a: any) => <li key={a.id}><span className="tiny muted">{when(a.created_at)}</span> <b>{a.actor ?? "system"}</b> {a.event_type.replace(/_/g, " ")}</li>)}
        </ul>
      </section>
    </div>
  );
}
