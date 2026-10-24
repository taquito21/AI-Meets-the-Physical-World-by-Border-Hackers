import { useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "../api";
import AssemblyViewer from "../components/AssemblyViewer";
import { ProfileDetails } from "../components/ProfileDetails";
import { TechSheet } from "../components/TechSheet";
import { useAssemblyControls } from "../components/useAssemblyControls";
import { Chip, ErrorBox, IndustryChip, useAsync } from "../components/ui";
import { t } from "../i18n";

// Evidence type codes from the package, in plain words.
const EVIDENCE_TYPE_LABEL: Record<string, string> = {
  photo: "Photo",
  manual_confirmation: "Manual confirmation",
  photo_and_manual_confirmation: "Photo and manual confirmation",
};

export default function ProductDetail() {
  const { revisionId = "" } = useParams();
  const { data: rev, error } = useAsync(() => api.revision(revisionId), [revisionId]);
  const [selected, setSelected] = useState<string | null>(null);
  const { viewerProps, controls } = useAssemblyControls(rev?.components, selected);

  if (error) return <div className="page"><ErrorBox error={{ message: error }} /></div>;
  if (!rev) return <div className="page muted">{t("Loading…")}</div>;
  const comp = rev.components.find((c) => c.id === selected);
  const reqs = rev.requirements.filter((r) => r.component_id === selected);

  return (
    <div className="split">
      <div className="split-viewer">
        {rev.assembly_url ? (
          <>
            <AssemblyViewer assemblyUrl={rev.assembly_url} components={rev.components} selectedId={selected}
              onSelect={setSelected} {...viewerProps} />
            {controls}
          </>
        ) : (
          <div className="viewer-none">{t("No 3D model for this asset. Choose components from the list.")}</div>
        )}
      </div>
      <div className="split-panel">
        <h1>{rev.product_name} <small>{t("rev {rev}", { rev: rev.revision })}</small></h1>
        <div className="row small"><IndustryChip industry={rev.industry} /><span className="muted">{rev.asset_category} · {rev.manufacturer} · {t("package {id}", { id: rev.engineering_package_id })} · v{rev.package_version}</span></div>
        {rev.manifest.demonstration_package && <p><Chip tone="amber">{t("Demonstration package")}</Chip> <span className="small muted">{rev.manifest.provenance}</span></p>}
        <p className="small">{rev.product_description}</p>
        {rev.procedure?.safety_notes?.length > 0 && (
          <div className="notice small"><b>{t("Safety:")}</b> {rev.procedure.safety_notes.join(" ")}</div>
        )}
        <div className="row small">
          {rev.documents.map((d) => <a key={d.id} href={d.url} target="_blank" rel="noreferrer" className="btn btn-ghost btn-small">{d.title}</a>)}
          <a href={rev.bom_url} className="btn btn-ghost btn-small">{t("BOM (CSV)")}</a>
        </div>
        {comp ? (
          <section className="card">
            <div className="card-head"><h2>{comp.name}</h2><button className="btn btn-small btn-ghost" onClick={() => setSelected(null)}>{t("Close")}</button></div>
            <p className="small">{comp.description}</p>
            <TechSheet comp={comp} />
            <h3>{t("Inspection profile")}</h3>
            {reqs.length ? reqs.map((r) => (
              <div key={r.requirement_id} className="req-static">
                <b>{r.title}</b> {r.required ? <Chip tone="blue">{t("Required")}</Chip> : <Chip>{t("Optional")}</Chip>} <Chip>{EVIDENCE_TYPE_LABEL[r.evidence_type] ? t(EVIDENCE_TYPE_LABEL[r.evidence_type]) : r.evidence_type.replace(/_/g, " ")}</Chip>
                <p className="small">{r.instructions}</p>
                <div className="small"><ProfileDetails req={r} /></div>
              </div>
            )) : <p className="muted small">{t("No requirements defined for this component.")}</p>}
          </section>
        ) : <p className="muted small">{t("Tap a component in the 3D view or in the table below.")}</p>}
        <h3>{t("Bill of materials")}</h3>
        <table className="table">
          <thead><tr><th>{t("Part")}</th><th>{t("Component")}</th><th>{t("Qty")}</th></tr></thead>
          <tbody>
            {rev.components.map((c) => (
              <tr key={c.id} className={c.id === selected ? "sel" : ""} onClick={() => setSelected(c.id)}>
                <td>{c.part_number}</td><td>{c.name}</td><td>{c.quantity}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
