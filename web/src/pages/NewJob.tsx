import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, type MediaItem } from "../api";
import { ErrorBox, useAsync } from "../components/ui";

interface DraftTask { description: string; mediaId: string; parts: string[] }

const blank = (): DraftTask => ({ description: "", mediaId: "", parts: [] });

export default function NewJob() {
  const nav = useNavigate();
  const { data: users } = useAsync(api.users, []);
  const { data: media } = useAsync(api.media, []);
  const employees = (users ?? []).filter((u) => u.user_class === "employee");
  const [title, setTitle] = useState("");
  const [assignee, setAssignee] = useState("");
  const [tasks, setTasks] = useState<DraftTask[]>([blank()]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const update = (i: number, patch: Partial<DraftTask>) =>
    setTasks((ts) => ts.map((t, n) => (n === i ? { ...t, ...patch } : t)));
  const mediaById = (id: string): MediaItem | undefined => media?.find((m) => m.id === id);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const job = await api.createJob({
        title, assigned_to: assignee || employees[0]?.id || "",
        tasks: tasks.filter((t) => t.description.trim()).map((t) => ({
          description: t.description,
          media: t.mediaId ? [{ media_id: t.mediaId, node_ids: t.parts }] : [],
        })),
      });
      nav(`/jobs/${job.id}`);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="page">
      <h1>New job</h1>
      <form onSubmit={submit}>
        <section className="card">
          <label>Title<input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. Monthly extinguisher check, building A" required /></label>
          <label>Assign to
            <select value={assignee || employees[0]?.id || ""} onChange={(e) => setAssignee(e.target.value)}>
              {employees.length === 0 && <option value="">No employees in your company yet</option>}
              {employees.map((u) => <option key={u.id} value={u.id}>{u.username}</option>)}
            </select>
          </label>
        </section>

        {tasks.map((t, i) => {
          const linked = mediaById(t.mediaId);
          return (
            <section className="card" key={i}>
              <div className="card-head">
                <h2>Task {i + 1}</h2>
                {tasks.length > 1 && (
                  <button type="button" className="btn btn-small btn-ghost" onClick={() => setTasks(tasks.filter((_, n) => n !== i))}>Remove</button>
                )}
              </div>
              <textarea rows={2} value={t.description} placeholder="What should be checked or done?"
                onChange={(e) => update(i, { description: e.target.value })} />
              <label className="small">Reference material (optional)
                <select value={t.mediaId} onChange={(e) => update(i, { mediaId: e.target.value, parts: [] })}>
                  <option value="">None</option>
                  {(media ?? []).map((m) => (
                    <option key={m.id} value={m.id}>{m.kind === "model_3d" ? "3D" : m.kind === "document" ? "Document" : "Image"}: {m.title}</option>
                  ))}
                </select>
              </label>
              {linked?.kind === "model_3d" && (linked.metadata.parts?.length ?? 0) > 0 && (
                <fieldset className="parts">
                  <legend className="small">Parts this task is about (highlighted in the 3D view)</legend>
                  {linked.metadata.parts!.map((p) => (
                    <label key={p.id} className="check small">
                      <input type="checkbox" checked={t.parts.includes(p.id)} onChange={(e) =>
                        update(i, { parts: e.target.checked ? [...t.parts, p.id] : t.parts.filter((x) => x !== p.id) })} />
                      {p.name}
                    </label>
                  ))}
                </fieldset>
              )}
            </section>
          );
        })}
        <div className="row">
          <button type="button" className="btn" onClick={() => setTasks([...tasks, blank()])}>Add task</button>
          <button className="btn btn-primary" disabled={busy || !employees.length}>{busy ? "Creating…" : "Create job"}</button>
        </div>
        <ErrorBox error={error} />
      </form>
    </div>
  );
}
