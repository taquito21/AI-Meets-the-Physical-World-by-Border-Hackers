import { useRef, useState } from "react";
import { api, type Job, type Task, type TaskStatus, type UserClass } from "../api";
import { EvidenceCard } from "./EvidenceCard";
import { ModelView } from "./ModelView";
import { ErrorBox, StatusChip } from "./ui";

const ACTIONS: { status: TaskStatus; label: string; className: string }[] = [
  { status: "passed", label: "Passed", className: "btn-green" },
  { status: "failed", label: "Failed", className: "btn-red" },
  { status: "flagged", label: "Flag for employer", className: "btn-purple" },
];

export function TaskCard({ task, role, onJob, onOpenImage }:
  { task: Task; role: UserClass; onJob: (j: Job) => void; onOpenImage: (url: string) => void }) {
  const [text, setText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showModel, setShowModel] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  const run = async (label: string, fn: () => Promise<Job>) => {
    setBusy(label);
    setError(null);
    try {
      onJob(await fn());
      return true;
    } catch (e) {
      setError((e as Error).message);
      return false;
    } finally {
      setBusy(null);
    }
  };
  const addEvidence = async () => {
    if (await run(file ? "Uploading photo and running the AI review…" : "Saving…",
      () => api.addEvidence(task.id, text, file))) {
      setText("");
      setFile(null);
      if (fileInput.current) fileInput.current.value = "";
    }
  };

  const models = task.media.filter((m) => m.kind === "model_3d");
  const others = task.media.filter((m) => m.kind !== "model_3d");
  return (
    <section className={`card task task-${task.status}`}>
      <div className="card-head">
        <div><span className="muted small">Task {task.position + 1}</span><h2>{task.description}</h2></div>
        <StatusChip status={task.status} />
      </div>
      {task.status === "flagged" && (
        <div className="notice notice-flag small">
          {role === "employer" ? "Flagged for your input: add a note below, then mark it passed or failed."
            : "Flagged: waiting for your employer's input."}
        </div>
      )}

      {(models.length > 0 || others.length > 0) && (
        <div className="row small">
          {models.map((m) => (
            <button key={m.id} className="btn btn-small" onClick={() => setShowModel(showModel === m.id ? null : m.id)}>
              {showModel === m.id ? "Hide" : "Show"} 3D: {m.title}
            </button>
          ))}
          {others.map((m) => m.url && (
            <a key={m.id} className="btn btn-small btn-ghost" href={m.url} target="_blank" rel="noreferrer">
              {m.kind === "document" ? "📄" : "🖼"} {m.title}
            </a>
          ))}
        </div>
      )}
      {models.filter((m) => m.id === showModel).map((m) => (
        <ModelView key={m.id} model={m} highlight={m.node_ids} status={task.status} />
      ))}

      {task.evidence.map((e) => <EvidenceCard key={e.id} e={e} onOpen={onOpenImage} onJob={onJob} />)}

      <div className="actions">
        <textarea rows={2} placeholder={role === "employer" ? "Reply or add a note…" : "Add a note (what you saw, what you did)…"}
          value={text} onChange={(e) => setText(e.target.value)} />
        <div className="capture">
          <input ref={fileInput} type="file" accept="image/*" capture="environment"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          <button className="btn btn-primary" disabled={!!busy || (!text.trim() && !file)} onClick={addEvidence}>
            {file ? "Add photo" : "Add note"}
          </button>
        </div>
        <div className="row">
          {ACTIONS.filter((a) => a.status !== task.status && (role === "employee" || a.status !== "flagged")).map((a) => (
            <button key={a.status} className={`btn ${a.className}`} disabled={!!busy}
              onClick={() => run("Saving…", () => api.setStatus(task.id, a.status))}>{a.label}</button>
          ))}
          {task.status !== "pending" && (
            <button className="btn btn-ghost" disabled={!!busy}
              onClick={() => run("Saving…", () => api.setStatus(task.id, "pending"))}>Reset to pending</button>
          )}
        </div>
        {busy && <div className="small muted"><span className="spinner" /> {busy}</div>}
        <ErrorBox error={error} />
      </div>
    </section>
  );
}
