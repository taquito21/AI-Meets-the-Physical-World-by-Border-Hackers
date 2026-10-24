import { useRef, useState } from "react";
import { Box, Camera, CircleCheck, CircleX, FileText, Flag, Image, RotateCcw, Send, type LucideIcon } from "lucide-react";
import { api, type Job, type Task, type TaskStatus, type UserClass } from "../api";
import { t } from "../i18n";
import { EvidenceCard } from "./EvidenceCard";
import { ModelView } from "./ModelView";
import { ErrorBox, StatusChip } from "./ui";

const ACTIONS: { status: TaskStatus; label: string; className: string; icon: LucideIcon }[] = [
  { status: "passed", label: "Passed", className: "btn-green", icon: CircleCheck },
  { status: "failed", label: "Failed", className: "btn-red", icon: CircleX },
  { status: "flagged", label: "Ask my employer", className: "btn-purple", icon: Flag },
];

// One plain sentence: what this person should do now on this task.
function nowLine(task: Task, role: UserClass): string {
  if (task.status === "flagged") {
    return role === "employer" ? "Your employee asked for your input. Write a reply below, then choose Passed or Failed."
      : "Waiting for your employer's reply.";
  }
  if (task.status !== "pending") return "Done. You can still add a photo or change the result.";
  return task.evidence.length ? "Now choose a result." : "Take a photo or write a note, then choose a result.";
}

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
    if (await run(file ? "Uploading the photo and asking the AI…" : "Saving…", () => api.addEvidence(task.id, text, file))) {
      setText("");
      setFile(null);
      if (fileInput.current) fileInput.current.value = "";
    }
  };

  const models = task.media.filter((m) => m.kind === "model_3d");
  const others = task.media.filter((m) => m.kind !== "model_3d");
  const done = task.status !== "pending" && task.status !== "flagged";
  return (
    <section className={`card task task-${task.status}`}>
      <div className="card-head">
        <div><span className="muted small">{t("Task {n}", { n: task.position + 1 })}</span><h2>{task.description}</h2></div>
        <StatusChip status={task.status} />
      </div>
      <div className={`now ${done ? "now-done" : "now-todo"}`}>{t(nowLine(task, role))}</div>

      {(models.length > 0 || others.length > 0) && (
        <div className="row small">
          {models.map((m) => (
            <button key={m.id} className="btn btn-small" onClick={() => setShowModel(showModel === m.id ? null : m.id)}>
              <Box aria-hidden />{showModel === m.id ? t("Hide 3D model") : t("Show 3D model")}: {m.title}
            </button>
          ))}
          {others.map((m) => m.url && (
            <a key={m.id} className="btn btn-small btn-ghost" href={m.url} target="_blank" rel="noreferrer">
              {m.kind === "document" ? <FileText aria-hidden /> : <Image aria-hidden />}{m.title}
            </a>
          ))}
        </div>
      )}
      {models.filter((m) => m.id === showModel).map((m) => (
        <ModelView key={m.id} model={m} highlight={m.node_ids} status={task.status} />
      ))}

      {task.evidence.map((e) => <EvidenceCard key={e.id} e={e} onOpen={onOpenImage} onJob={onJob} />)}

      <div className="actions">
        <textarea rows={2} value={text} onChange={(e) => setText(e.target.value)}
          placeholder={t(role === "employer" ? "Write a reply or a note…" : "Write a note: what you saw, what you did…")} />
        <div className="capture">
          <label className="btn btn-big">
            <Camera aria-hidden />{file ? t("Photo ready: {name}", { name: file.name }) : t("Take photo")}
            <input ref={fileInput} type="file" accept="image/*" capture="environment" hidden
              onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          </label>
          <button className="btn btn-big btn-primary" disabled={!!busy || (!text.trim() && !file)} onClick={addEvidence}>
            <Send aria-hidden />{t(file ? "Save photo" : "Save note")}
          </button>
        </div>
        <div className="decide">
          <span className="decide-label">{t("Result")}</span>
          <div className="row">
            {ACTIONS.filter((a) => a.status !== task.status && (role === "employee" || a.status !== "flagged")).map((a) => (
              <button key={a.status} className={`btn btn-big ${a.className}`} disabled={!!busy}
                onClick={() => run("Saving…", () => api.setStatus(task.id, a.status))}><a.icon aria-hidden />{t(a.label)}</button>
            ))}
            {task.status !== "pending" && (
              <button className="btn btn-ghost" disabled={!!busy}
                onClick={() => run("Saving…", () => api.setStatus(task.id, "pending"))}><RotateCcw aria-hidden />{t("Undo result")}</button>
            )}
          </div>
        </div>
        {busy && <div className="small muted"><span className="spinner" /> {t(busy)}</div>}
        <ErrorBox error={error} />
      </div>
    </section>
  );
}
