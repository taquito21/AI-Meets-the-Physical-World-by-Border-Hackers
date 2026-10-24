import { useState } from "react";
import { Link } from "react-router-dom";
import { api, ApiError, type Finding } from "../api";
import { Chip, ErrorBox, Lightbox, useAsync, when } from "../components/ui";
import { useSession } from "../session";

const NEXT: Record<string, { to: string; label: string; needs?: "assignee" | "note" }[]> = {
  open: [{ to: "assigned", label: "Assign", needs: "assignee" }, { to: "void", label: "Void (raised in error)", needs: "note" }],
  assigned: [{ to: "action_recorded", label: "Record corrective action", needs: "note" }],
  action_recorded: [{ to: "awaiting_verification", label: "Request verification" }],
  awaiting_verification: [{ to: "closed", label: "Verify & close" }, { to: "assigned", label: "Rework" }],
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
          <div className="muted small">{f.part_number} · {f.product_instance_id} · <Link to={`/inspections/${f.inspection_id}/summary`}>inspection</Link> · {when(f.created_at)} by {f.created_by}</div>
        </div>
        <div><Chip tone={tone}>{f.status.replace(/_/g, " ")}</Chip> <Chip tone="red">{f.severity}</Chip></div>
      </div>
      <p>{f.description}</p>
      {f.corrective_action && (
        <p className="small">
          Corrective action: <b>{f.corrective_action.status.replace(/_/g, " ")}</b>
          {f.corrective_action.assigned_to && ` · assigned to ${f.corrective_action.assigned_to}`}
          {f.corrective_action.description && ` · “${f.corrective_action.description}” (${f.corrective_action.recorded_by})`}
          {f.corrective_action.verified_by && ` · verified by ${f.corrective_action.verified_by}`}
        </p>
      )}
      <div className="thumbs">
        {f.evidence.map((e) => (
          <figure key={e.id}><img src={e.url} alt="" onClick={() => onOpen(e.url)} /><figcaption className="tiny">{e.kind === "inspection" ? "inspection" : e.kind.replace("corrective_", "")}</figcaption></figure>
        ))}
      </div>
      {actions.length > 0 && (
        <div className="actions">
          {actions.some((a) => a.needs) && (
            <input value={text} onChange={(e) => setText(e.target.value)}
              placeholder={f.status === "open" ? "Assignee name, or reason to void" : "Describe the corrective action taken"} />
          )}
          <div className="row">
            {actions.map((a) => <button key={a.to} className="btn" disabled={busy} onClick={() => go(a.to)}>{a.label}</button>)}
            {!["closed", "void"].includes(f.status) && (
              <>
                <label className="btn btn-ghost">Before photo<input type="file" accept="image/*" capture="environment" hidden onChange={(e) => photo(e.target.files?.[0], "corrective_before")} /></label>
                <label className="btn btn-ghost">After photo<input type="file" accept="image/*" capture="environment" hidden onChange={(e) => photo(e.target.files?.[0], "corrective_after")} /></label>
              </>
            )}
          </div>
          <p className="tiny muted">Closing requires an after photo and a verifier who is different from the person who recorded the work.</p>
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
      <h1>Findings &amp; corrective actions</h1>
      <p className="muted small">Lifecycle: open → assigned → action recorded → awaiting verification → closed.</p>
      {data?.length === 0 && <p className="muted">No findings recorded.</p>}
      {data?.map((f) => <FindingCard key={f.id} f={f} onChange={reload} onOpen={setLightbox} />)}
      <Lightbox src={lightbox} onClose={() => setLightbox(null)} />
    </div>
  );
}
