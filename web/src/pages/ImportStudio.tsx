import { useState } from "react";
import { Link } from "react-router-dom";
import { api, ApiError } from "../api";
import { Chip, ErrorBox, useAsync, when } from "../components/ui";
import { t } from "../i18n";
import { useSession } from "../session";

// Package statistics sent by the server; unknown ones are shown with underscores replaced.
const STAT_LABEL: Record<string, string> = {
  components: "components",
  geometry_nodes: "geometry nodes",
  bom_lines: "bom lines",
  requirements: "requirements",
  required_requirements: "required requirements",
};

export default function ImportStudio() {
  const { data, reload } = useAsync(() => api.packages(), []);
  const { name } = useSession();
  const [result, setResult] = useState<Record<string, string>>({});
  const [err, setErr] = useState<ApiError | null>(null);

  const load = async (dir: string) => {
    setErr(null);
    try {
      const r = await api.loadPackage(dir, name);
      setResult({ ...result, [dir]: r.status === "unchanged" ? t("Already loaded (content identical)") : t("Loaded") });
      reload();
    } catch (e) {
      setErr(e as ApiError);
    }
  };

  return (
    <div className="page">
      <h1>{t("Engineering Import Studio")}</h1>
      <div className="notice">
        <b>{t("Demonstration.")}</b> {t("These packages were prepared by our team to simulate a manufacturer's engineering handoff.")}{" "}
        {t("Loading a package runs the platform's real validation and import pipeline.")} {t("Native CAD / STEP conversion is")} <b>{t("not implemented")}</b> {t("and is on the roadmap.")}
      </div>
      <ErrorBox error={err} />
      {data?.map((p) => (
        <section className="card" key={p.package_dir}>
          <div className="card-head">
            <div>
              <h2>{t("{name}, revision {revision}", { name: p.product_name, revision: p.engineering_revision })}</h2>
              <div className="muted small">{p.manufacturer} · {p.package_id} · {p.package_dir}</div>
            </div>
            <div>
              {p.ok ? <Chip tone="green">{t("Valid")}</Chip> : <Chip tone="red">{p.errors.length === 1 ? t("{n} error", { n: p.errors.length }) : t("{n} errors", { n: p.errors.length })}</Chip>}{" "}
              {p.demonstration_package && <Chip tone="amber">{t("Demo package")}</Chip>}
            </div>
          </div>
          <div className="pkg-files small">
            <span>{t("Assembly:")} <code>{p.files.assembly}</code></span>
            <span>{t("Components:")} <code>{p.files.components}</code></span>
            <span>{t("BOM:")} <code>{p.files.bom}</code></span>
            <span>{t("Procedure:")} <code>{p.files.inspection_procedure}</code></span>
            {p.files.documents.map((d: string) => <span key={d}>{t("Drawing:")} <code>{d}</code></span>)}
          </div>
          <div className="stats small">
            {Object.entries(p.stats).map(([k, v]) => <span key={k}><b>{v}</b> {STAT_LABEL[k] ? t(STAT_LABEL[k]) : k.replace(/_/g, " ")}</span>)}
          </div>
          {p.errors.length > 0 && <ul className="small err-list">{p.errors.map((e) => <li key={e}>{e}</li>)}</ul>}
          {p.warnings.length > 0 && <details className="small"><summary>{p.warnings.length === 1 ? t("{n} warning", { n: p.warnings.length }) : t("{n} warnings", { n: p.warnings.length })}</summary><ul>{p.warnings.map((w) => <li key={w}>{w}</li>)}</ul></details>}
          <div className="tiny muted">{t("Content hash {hash}…", { hash: p.content_hash.slice(0, 16) })} · {p.loaded ? `${t("loaded {when}", { when: when(p.loaded_at) })}${p.loaded_matches_disk ? "" : ` ${t("(files changed on disk since loading: publish a new revision)")}`}` : t("not loaded")}</div>
          <div className="row">
            <button className="btn btn-primary" disabled={!p.ok} onClick={() => load(p.package_dir)}>{t("Load demonstration package")}</button>
            {p.loaded && <Link className="btn btn-ghost" to={`/products/${encodeURIComponent(`${p.product_id}@${p.engineering_revision}`)}`}>{t("Open product")}</Link>}
            {result[p.package_dir] && <Chip tone="green">{result[p.package_dir]}</Chip>}
          </div>
        </section>
      ))}
      <section className="card disabled-zone">
        <h2>{t("Upload native CAD (STEP, SolidWorks, Inventor…)")}</h2>
        <p className="small muted">{t("Roadmap. A future importer will convert CAD assemblies into this same validated package format, with stable component IDs, BOM linkage and web geometry. The inspection engine does not depend on where a package came from.")}</p>
        <button className="btn" disabled>{t("Not available in this demo")}</button>
      </section>
    </div>
  );
}
