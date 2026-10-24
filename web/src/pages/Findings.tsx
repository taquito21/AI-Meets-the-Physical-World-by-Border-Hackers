import { useState } from "react";
import { Link } from "react-router-dom";
import { api, ApiError, type Finding } from "../api";
import { Chip, ErrorBox, Lightbox, SEVERITY_LABEL, useAsync, when } from "../components/ui";
import { useSession } from "../session";

const NEXT: Record<string, { to: string; label: string; needs?: "assignee" | "note" }[]> = {
  open: [{ to: "assigned", label: "Assign to this person", needs: "assignee" }, { to: "void", label: "Cancel: reported by mistake", needs: "note" }],
  assigned: [{ to: "action_recorded", label: "Save what was done", needs: "note" }],
  action_recorded: [{ to: "awaiting_verification", label: "Ask someone to check the fix" }],
  awaiting_verification: [{ to: "closed", label: "Fix confirmed: close" }, { to: "assigned", label: "Not fixed: send back" }],
};

// Plain-language status, plus the one thing to do next.
const STATUS: Record<string, { label: string; next: string }> = {
  open: { label: "Reported", next: "Write who will fix it and tap “Assign to this person”." },
  assigned: { label: "Assigned", next: "When the work is done, add an after photo and describe what was done." },
  action_recorded: { label: "Fix recorded", next: "Ask another person to check the fix." },
  awaiting_verification: { label: "Waiting for a check", next: "A different person checks the fix and closes it, or sends it back." },
  closed: { label: "Closed: fixed", next: "" },
  void: { label: "Cancelled", next: "" },
};

function FindingCard({ f, onChange, onOpen }: { f: Finding; onChange: () => void; onOpen: (u: string) => void }) {
  const { name } = useSession();
  const [text, setText] = useState("");
  const [err, setErr] = useState<ApiError | null>(null);
  const [busy, setBusy] = useState(false);

  const go = async (to: string) => {
    setBusy(true);
    setErr(null);
    try {
      await api.transitionFinding(f.id, { to, actor: name, assigned_to: text, note: text });
      setText("");
      onChange();
    } catch (e) {
      setErr(e as ApiError);
    } finally {
      setBusy(false);
    }
  };
  const photo = async (file: File | undefined, kind: "corrective_before" | "corrective_after") => {
    if (!file) return;
    setBusy(true);
    try {
      await api.findingEvidence(f.id, file, name, kind, "");
      onChange();
    } catch (e) {
      setErr(e as ApiError);
    } finally {
      setBusy(false);
    }
  };
  const actions = NEXT[f.status] ?? [];
  const tone = f.status === "closed" ? "green" : f.status === "void" ? "neutral" : "red";
  return (
    <section className="card">
      <div className="card-head">
        <div>
          <h2>{f.component_name ?? f.component_id}</h2>
          <div className="muted small">{f.product_instance_id} · reported {when(f.created_at)} by {f.created_by} · <Link to={`/inspections/${f.inspection_id}/summary`}>see the inspection</Link></div>
        </div>
        <div>{f.mode === "demo" && <span className="chip chip-demo" title="From a practice inspection">Practice</span>} <Chip tone={tone}>{STATUS[f.status]?.label ?? f.status}</Chip> <Chip tone="red">{SEVERITY_LABEL[f.severity] ?? f.severity}</Chip></div>
      </div>
      <p>{f.description}</p>
      {STATUS[f.status]?.next && <div className="now now-todo">Next: {STATUS[f.status].next}</div>}
      {f.corrective_action && (
        <p className="small">
          {f.corrective_action.assigned_to && <>Assigned to <b>{f.corrective_action.assigned_to}</b></>}
          {f.corrective_action.description && ` · “${f.corrective_action.description}” (${f.corrective_action.recorded_by})`}
          {f.corrective_action.verified_by && ` · verified by ${f.corrective_action.verified_by}`}
        </p>
      )}
      <div className="thumbs">
        {f.evidence.map((e) => (
          <figure key={e.id}><img src={e.url} alt="" onClick={() => onOpen(e.url)} /><figcaption className="tiny">{e.kind === "corrective_before" ? "before fix" : e.kind === "corrective_after" ? "after fix" : e.kind === "demo" ? "practice photo" : "from inspection"}</figcaption></figure>
        ))}
      </div>
      {actions.length > 0 && (
        <div className="actions">
          {actions.some((a) => a.needs) && (
            <input value={text} onChange={(e) => setText(e.target.value)}
              placeholder={f.status === "open" ? "Who will fix it? (or why it was a mistake)" : "What was done to fix it?"} />
          )}
          <div className="row">
            {actions.map((a, n) => <button key={a.to} className={n === 0 ? "btn btn-primary" : "btn btn-ghost"} disabled={busy} onClick={() => go(a.to)}>{a.label}</button>)}
            {!["closed", "void"].includes(f.status) && (
              <>
                <label className="btn btn-ghost">Photo before the fix<input type="file" accept="image/*" capture="environment" hidden onChange={(e) => photo(e.target.files?.[0], "corrective_before")} /></label>
                <label className="btn btn-ghost">Photo after the fix<input type="file" accept="image/*" capture="environment" hidden onChange={(e) => photo(e.target.files?.[0], "corrective_after")} /></label>
              </>
            )}
          </div>
          <p className="tiny muted">To close it you need a photo after the fix, and the person who checks it must be different from the person who did the work.</p>
        </div>
      )}
      <ErrorBox error={err} />
    </section>
  );
}

export default function Findings() {
  const { data, reload } = useAsync(() => api.findings(), []);
  const [lightbox, setLightbox] = useState<string | null>(null);
  return (
    <div className="page">
      <h1>Problems to fix</h1>
      <p className="muted small">Every problem reported during an inspection goes through: reported → assigned → fix recorded → checked by another person → closed.</p>
      {data?.length === 0 && <p className="muted">No problems reported.</p>}
      {data?.map((f) => <FindingCard key={f.id} f={f} onChange={reload} onOpen={setLightbox} />)}
      <Lightbox src={lightbox} onClose={() => setLightbox(null)} />
    </div>
  );
}
