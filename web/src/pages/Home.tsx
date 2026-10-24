import { Link, useNavigate } from "react-router-dom";
import { api } from "../api";
import { Chip, INSPECTION_TONE, useAsync, when } from "../components/ui";
import { useSession } from "../session";

export default function Home() {
  const { name, setName, role, setRole, health, label, setIndustry } = useSession();
  const nav = useNavigate();
  const { data: open } = useAsync(() => api.inspections(), []);
  const active = (open ?? []).filter((i) => ["in_progress", "changes_requested", "submitted"].includes(i.status));

  return (
    <div className="page">
      <section className="hero">
        <h1>{label}</h1>
        <p>An AI-assisted inspection platform for field work in any industry. Each asset's engineering data drives the inspection, findings are tied to components, and every decision is traceable.</p>
      </section>

      <section className="card">
        <h2>Who is working?</h2>
        <div className="row">
          <input value={name} onChange={(e) => setName(e.target.value)} aria-label="Your name" placeholder="Your name" />
          <div className="segmented">
            <button className={role === "inspector" ? "on" : ""} onClick={() => setRole("inspector")}>Inspector</button>
            <button className={role === "supervisor" ? "on" : ""} onClick={() => setRole("supervisor")}>Supervisor</button>
          </div>
        </div>
        <p className="muted small">Demo identity only, with no authentication. Your name is recorded on every action, and a supervisor must be a different person from the inspector.</p>
        <p className="small">
          AI evidence assessment:{" "}
          {health ? (
            health.ai.available ? <Chip tone="green">{health.ai.detail}</Chip> : <Chip tone="amber">Unavailable: {health.ai.detail}</Chip>
          ) : <Chip tone="red">Server unreachable</Chip>}
        </p>
      </section>

      <section>
        <h2>Choose a scenario</h2>
        <div className="scenarios">
          <button className="scenario" onClick={() => { setIndustry("Furniture"); nav("/catalog"); }}>
            <span className="scenario-tag">Furniture · manufactured products</span>
            <b>Furniture Inspection</b>
            <span>Chair and table built from the manufacturer's engineering package</span>
          </button>
          <button className="scenario scenario-electrical" onClick={() => { setIndustry("Electrical"); nav("/catalog"); }}>
            <span className="scenario-tag">Electrical · industrial equipment</span>
            <b>Industrial Electrical Panel Inspection</b>
            <span>Low-voltage control panel ICP-001: visual and documentation inspection</span>
          </button>
          <button className="scenario scenario-safety" onClick={() => { setIndustry("Facility Safety"); nav("/catalog"); }}>
            <span className="scenario-tag">Facility safety · fire equipment</span>
            <b>Fire Safety Equipment Inspection</b>
            <span>Portable fire extinguisher FE-001: guided visual condition inspection</span>
          </button>
        </div>
        <p className="muted small">Same inspection engine, evidence workflow, AI assessment and dashboard. Only the asset definition and its inspection profile change.</p>
      </section>

      <section className="tiles">
        <Link to="/dashboard" className="tile"><b>Dashboard</b><span>Inspections and findings across industries</span></Link>
        <Link to="/supervisor" className="tile"><b>Supervisor review</b><span>Approve submitted inspections</span></Link>
        <Link to="/findings" className="tile"><b>Findings</b><span>Corrective actions and verification</span></Link>
        <Link to="/import" className="tile"><b>Engineering Import Studio</b><span>Manufacturer packages (demo)</span></Link>
      </section>

      {active.length > 0 && (
        <section className="card">
          <h2>Active inspections</h2>
          <ul className="list">
            {active.map((i) => (
              <li key={i.id}>
                <Link to={i.status === "submitted" ? `/supervisor/${i.id}` : `/inspections/${i.id}`}>
                  <b>{i.product_name}</b> · {i.serial_number} · rev {i.revision} {i.mode === "demo" && <span className="chip chip-demo">DEMO</span>}
                </Link>
                <span className="muted small"> {i.inspector}, {when(i.updated_at)} </span>
                <Chip tone={INSPECTION_TONE[i.status]}>{i.status.replace("_", " ")}</Chip>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
