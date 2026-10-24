import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api";
import { Chip, INSPECTION_LABEL, INSPECTION_TONE, ModeBadge, useAsync, when } from "../components/ui";
import { useSession } from "../session";

const SCENARIOS = [
  { industry: "Furniture", cls: "", tag: "Furniture", title: "Chairs and tables", text: "Includes a real chair from the venue, rebuilt in 3D from photos." },
  { industry: "Electrical", cls: "scenario-electrical", tag: "Electrical", title: "Electrical control panel", text: "Visual and paperwork check. You never open the panel or touch live parts." },
  { industry: "Facility Safety", cls: "scenario-safety", tag: "Fire safety", title: "Fire extinguisher", text: "Look at the gauge, pin, hose, label and tag without handling it." },
];

export default function Home() {
  const { name, setName, role, setRole, health, label, setIndustry } = useSession();
  const nav = useNavigate();
  const { data: all } = useAsync(() => api.inspections(), []);
  const [editingName, setEditingName] = useState(!name.trim());
  const ongoing = (all ?? []).filter((i) => ["in_progress", "changes_requested"].includes(i.status)).slice(0, 5);
  const waitingReview = (all ?? []).filter((i) => i.status === "submitted").length;

  return (
    <div className="page">
      <section className="hero">
        <h1>{label}</h1>
        <p>Check equipment step by step from your phone. The app shows you what to look at, the AI tells you if your photo is clear, and you decide the result.</p>
      </section>

      {ongoing.length > 0 && (
        <section className="card">
          <h2>Continue where you left off</h2>
          <ul className="list">
            {ongoing.map((i) => (
              <li key={i.id} className="resume">
                <span className="grow">
                  <b>{i.product_name}</b> <span className="muted small">{i.serial_number} · {i.inspector}, {when(i.updated_at)}</span>
                </span>
                <ModeBadge mode={i.mode} />
                <Chip tone={INSPECTION_TONE[i.status]}>{INSPECTION_LABEL[i.status] ?? i.status}</Chip>
                <Link className="btn btn-primary btn-small" to={`/inspections/${i.id}`}>Continue →</Link>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section>
        <h2>{ongoing.length ? "Or start a new inspection" : "Start an inspection"}</h2>
        <p className="muted small">What kind of equipment are you checking?</p>
        <div className="scenarios">
          {SCENARIOS.map((s) => (
            <button key={s.industry} className={`scenario ${s.cls}`} onClick={() => { setIndustry(s.industry); nav("/catalog"); }}>
              <span className="scenario-tag">{s.tag}</span>
              <b>{s.title}</b>
              <span>{s.text}</span>
              <span className="scenario-go">Choose →</span>
            </button>
          ))}
        </div>
      </section>

      <section className="card">
        <h2>How it works</h2>
        <ol className="how-steps">
          <li><b>Choose the equipment</b><span>Pick the unit in front of you. First time? Choose <i>Practice</i> to try it with sample photos.</span></li>
          <li><b>Follow the steps</b><span>The app tells you which part to check next. Take a photo and the AI says if it is clear enough.</span></li>
          <li><b>Choose a result and send it</b><span>For each check tap <i>Looks good</i> or <i>Report a problem</i>. At the end, send it for review.</span></li>
        </ol>
        <p className="muted small">The AI only helps. A person always makes the decision.</p>
      </section>

      {health && !health.ai.available && (
        <div className="notice small" title={health.ai.detail}>
          <b>AI photo feedback is off right now.</b> You can still inspect: look at each part yourself and choose the result.
        </div>
      )}

      <section className="card">
        {editingName ? (
          <>
            <h2>Who is working?</h2>
            <div className="row">
              <input value={name} onChange={(e) => setName(e.target.value)} aria-label="Your name" placeholder="Your name" />
              <div className="segmented">
                <button className={role === "inspector" ? "on" : ""} onClick={() => setRole("inspector")}>Inspector</button>
                <button className={role === "supervisor" ? "on" : ""} onClick={() => setRole("supervisor")}>Supervisor</button>
              </div>
              <button className="btn btn-primary" disabled={!name.trim()} onClick={() => setEditingName(false)}>Save</button>
            </div>
            <p className="muted small">Your name is saved with everything you do. A supervisor must be a different person from the inspector. This demo has no passwords.</p>
          </>
        ) : (
          <div className="row">
            <span className="grow">Working as <b>{name}</b> ({role === "supervisor" ? "supervisor" : "inspector"})</span>
            <button className="btn btn-ghost btn-small" onClick={() => setEditingName(true)}>Change</button>
          </div>
        )}
      </section>

      <section>
        <h2>For supervisors</h2>
        <div className="tiles">
          <Link to="/supervisor" className="tile">
            <b>Review inspections</b>
            <span>{waitingReview ? `${waitingReview} waiting for your review` : "Approve or ask for changes"}</span>
          </Link>
          <Link to="/findings" className="tile"><b>Problems to fix</b><span>Assign a fix, add photos, close it</span></Link>
          <Link to="/dashboard" className="tile"><b>Dashboard</b><span>All inspections and problems at a glance</span></Link>
        </div>
      </section>
      <p className="tiny muted"><Link to="/import">Add equipment from a manufacturer package (administrators)</Link></p>
    </div>
  );
}
