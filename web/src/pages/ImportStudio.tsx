import { useState } from "react";
import { Link } from "react-router-dom";
import { api, ApiError } from "../api";
import { Chip, ErrorBox, useAsync, when } from "../components/ui";
import { useSession } from "../session";

export default function ImportStudio() {
  const { data, reload } = useAsync(() => api.packages(), []);
  const { name } = useSession();
  const [result, setResult] = useState<Record<string, string>>({});
  const [err, setErr] = useState<ApiError | null>(null);

  const load = async (dir: string) => {
    setErr(null);
    try {
      const r = await api.loadPackage(dir, name);
      setResult({ ...result, [dir]: r.status === "unchanged" ? "Already loaded (content identical)" : "Loaded" });
      reload();
    } catch (e) {
      setErr(e as ApiError);
    }
  };

  return (
    <div className="page">
      <h1>Engineering Import Studio</h1>
      <div className="notice">
        <b>Demonstration.</b> These packages were prepared by our team to simulate a manufacturer's engineering handoff.
        Loading a package runs the platform's real validation and import pipeline. Native CAD / STEP conversion is <b>not implemented</b> and is on the roadmap.
      </div>
      <ErrorBox error={err} />
      {data?.map((p) => (
        <section className="card" key={p.package_dir}>
          <div className="card-head">
            <div>
              <h2>{p.product_name}, revision {p.engineering_revision}</h2>
              <div className="muted small">{p.manufacturer} · {p.package_id} · {p.package_dir}</div>
            </div>
            <div>
              {p.ok ? <Chip tone="green">Valid</Chip> : <Chip tone="red">{p.errors.length} error(s)</Chip>}{" "}
              {p.demonstration_package && <Chip tone="amber">Demo package</Chip>}
            </div>
          </div>
          <div className="pkg-files small">
            <span>Assembly: <code>{p.files.assembly}</code></span>
            <span>Components: <code>{p.files.components}</code></span>
            <span>BOM: <code>{p.files.bom}</code></span>
            <span>Procedure: <code>{p.files.inspection_procedure}</code></span>
            {p.files.documents.map((d: string) => <span key={d}>Drawing: <code>{d}</code></span>)}
          </div>
          <div className="stats small">
            {Object.entries(p.stats).map(([k, v]) => <span key={k}><b>{v}</b> {k.replace(/_/g, " ")}</span>)}
          </div>
          {p.errors.length > 0 && <ul className="small err-list">{p.errors.map((e) => <li key={e}>{e}</li>)}</ul>}
          {p.warnings.length > 0 && <details className="small"><summary>{p.warnings.length} warning(s)</summary><ul>{p.warnings.map((w) => <li key={w}>{w}</li>)}</ul></details>}
          <div className="tiny muted">Content hash {p.content_hash.slice(0, 16)}… · {p.loaded ? `loaded ${when(p.loaded_at)}${p.loaded_matches_disk ? "" : " (files changed on disk since loading: publish a new revision)"}` : "not loaded"}</div>
          <div className="row">
            <button className="btn btn-primary" disabled={!p.ok} onClick={() => load(p.package_dir)}>Load demonstration package</button>
            {p.loaded && <Link className="btn btn-ghost" to={`/products/${encodeURIComponent(`${p.product_id}@${p.engineering_revision}`)}`}>Open product</Link>}
            {result[p.package_dir] && <Chip tone="green">{result[p.package_dir]}</Chip>}
          </div>
        </section>
      ))}
      <section className="card disabled-zone">
        <h2>Upload native CAD (STEP, SolidWorks, Inventor…)</h2>
        <p className="small muted">Roadmap. A future importer will convert CAD assemblies into this same validated package format, with stable component IDs, BOM linkage and web geometry. The inspection engine does not depend on where a package came from.</p>
        <button className="btn" disabled>Not available in this demo</button>
      </section>
    </div>
  );
}
