import { useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "../api";
import AssemblyViewer from "../components/AssemblyViewer";
import { ProfileDetails } from "../components/ProfileDetails";
import { TechSheet } from "../components/TechSheet";
import { useAssemblyControls } from "../components/useAssemblyControls";
import { Chip, ErrorBox, IndustryChip, useAsync } from "../components/ui";

export default function ProductDetail() {
  const { revisionId = "" } = useParams();
  const { data: rev, error } = useAsync(() => api.revision(revisionId), [revisionId]);
  const [selected, setSelected] = useState<string | null>(null);
  const { viewerProps, controls } = useAssemblyControls(rev?.components, selected);

  if (error) return <div className="page"><ErrorBox error={{ message: error }} /></div>;
  if (!rev) return <div className="page muted">Loading…</div>;
  const comp = rev.components.find((c) => c.id === selected);
  const reqs = rev.requirements.filter((r) => r.component_id === selected);

  return (
    <div className="split">
      <div className="split-viewer">
        <AssemblyViewer assemblyUrl={rev.assembly_url} components={rev.components} selectedId={selected}
          onSelect={setSelected} {...viewerProps} />
        {controls}
      </div>
      <div className="split-panel">
        <h1>{rev.product_name} <small>rev {rev.revision}</small></h1>
        <div className="row small"><IndustryChip industry={rev.industry} /><span className="muted">{rev.asset_category} · {rev.manufacturer} · package {rev.engineering_package_id} · v{rev.package_version}</span></div>
        {rev.manifest.demonstration_package && <p><Chip tone="amber">Demonstration package</Chip> <span className="small muted">{rev.manifest.provenance}</span></p>}
        <p className="small">{rev.product_description}</p>
        {rev.procedure?.safety_notes?.length > 0 && (
          <div className="notice small"><b>Safety:</b> {rev.procedure.safety_notes.join(" ")}</div>
        )}
        <div className="row small">
          {rev.documents.map((d) => <a key={d.id} href={d.url} target="_blank" rel="noreferrer" className="btn btn-ghost btn-small">{d.title}</a>)}
          <a href={rev.bom_url} className="btn btn-ghost btn-small">BOM (CSV)</a>
        </div>
        {comp ? (
          <section className="card">
            <div className="card-head"><h2>{comp.name}</h2><button className="btn btn-small btn-ghost" onClick={() => setSelected(null)}>Close</button></div>
            <p className="small">{comp.description}</p>
            <TechSheet comp={comp} />
            <h3>Inspection profile</h3>
            {reqs.length ? reqs.map((r) => (
              <div key={r.requirement_id} className="req-static">
                <b>{r.title}</b> {r.required ? <Chip tone="blue">Required</Chip> : <Chip>Optional</Chip>} <Chip>{r.evidence_type.replace(/_/g, " ")}</Chip>
                <p className="small">{r.instructions}</p>
                <div className="small"><ProfileDetails req={r} /></div>
              </div>
            )) : <p className="muted small">No requirements defined for this component.</p>}
          </section>
        ) : <p className="muted small">Tap a component in the 3D view or in the table below.</p>}
        <h3>Bill of materials</h3>
        <table className="table">
          <thead><tr><th>Part</th><th>Component</th><th>Qty</th></tr></thead>
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
