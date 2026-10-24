import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, type ApiError } from "../api";
import { IndustryFilter } from "../components/IndustryFilter";
import { Chip, ErrorBox, INSPECTION_TONE, IndustryChip, ModeBadge, useAsync } from "../components/ui";
import { useSession } from "../session";

export default function Catalog() {
  const { data, error } = useAsync(() => api.products(), []);
  const { name, industry } = useSession();
  const nav = useNavigate();
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<ApiError | null>(null);

  const start = async (serial: string, mode: "live" | "demo") => {
    setBusy(`${serial}:${mode}`);
    setErr(null);
    try {
      const r = await api.startInspection(serial, name, mode);
      nav(`/inspections/${r.inspection_id}`);
    } catch (e) {
      setErr(e as ApiError);
    } finally {
      setBusy(null);
    }
  };

  const assets = (data ?? []).filter((p) => industry === "All" || p.industry === industry);
  return (
    <div className="page">
      <div className="card-head">
        <h1>Assets</h1>
        <IndustryFilter industries={[...new Set((data ?? []).map((p) => p.industry))]} />
      </div>
      <p className="muted small">The same inspection engine runs every asset. Only the asset definition (3D model, components, technical data) and its inspection profile change.</p>
      {error && <ErrorBox error={{ message: error }} />}
      <ErrorBox error={err} />
      {assets.map((p) => (
        <section className="card" key={p.id}>
          <div className="card-head">
            <div>
              <h2>{p.product_name}</h2>
              <div className="muted small">{p.manufacturer} · {p.product_id} · Engineering revision {p.revision}</div>
            </div>
            <div className="row">
              <IndustryChip industry={p.industry} />
              {p.demonstration_package && <Chip tone="amber">Demonstration package</Chip>}
            </div>
          </div>
          <p className="small">{p.description}</p>
          <p className="small muted">{p.asset_category} · {p.component_count} components · {p.requirement_count} inspection points{p.demo_evidence_count ? ` · ${p.demo_evidence_count} prepared demo photos` : ""}</p>
          <Link className="btn btn-ghost" to={`/products/${encodeURIComponent(p.id)}`}>View 3D assembly &amp; technical data</Link>
          <h3>Units</h3>
          <ul className="list">
            {p.instances.map((i) => {
              const open = i.last_inspection_status === "in_progress" || i.last_inspection_status === "changes_requested";
              return (
                <li key={i.serial_number} className="instance">
                  <div>
                    <Link to={`/p/${i.serial_number}`}><b>{i.serial_number}</b></Link>
                    <div className="muted small">{i.metadata.location}</div>
                  </div>
                  {i.last_inspection_status && (
                    <>
                      <ModeBadge mode={i.last_inspection_mode} />
                      <Chip tone={INSPECTION_TONE[i.last_inspection_status]}>{i.last_inspection_status.replace("_", " ")}</Chip>
                    </>
                  )}
                  {i.last_inspection_status === "submitted" ? (
                    <Link className="btn btn-ghost" to={`/p/${i.serial_number}`}>Under review</Link>
                  ) : open ? (
                    <button className="btn" disabled={!!busy}
                      onClick={() => start(i.serial_number, (i.last_inspection_mode as "live" | "demo") ?? "live")}>Resume</button>
                  ) : (
                    <>
                      <button className="btn" disabled={!!busy} onClick={() => start(i.serial_number, "live")}>
                        {busy === `${i.serial_number}:live` ? "Opening…" : "Inspect"}
                      </button>
                      {p.demo_evidence_count > 0 && (
                        <button className="btn btn-demo" disabled={!!busy} onClick={() => start(i.serial_number, "demo")}
                          aria-describedby="demo-hint">
                          {busy === `${i.serial_number}:demo` ? "Opening…" : "Demo inspection"}
                        </button>
                      )}
                    </>
                  )}
                </li>
              );
            })}
          </ul>
        </section>
      ))}
      {data && assets.length === 0 && <p className="muted">No assets in this industry.</p>}
      <p id="demo-hint" className="tiny muted">Demo inspections use prepared, clearly labelled demonstration photos and never mix with live inspection records.</p>
    </div>
  );
}
