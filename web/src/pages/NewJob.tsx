import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Check, Plus, Trash2 } from "lucide-react";
import { api, type MediaItem } from "../api";
import { ErrorBox, today, useAsync } from "../components/ui";
import { t } from "../i18n";

interface DraftTask { description: string; mediaId: string; parts: string[] }

const blank = (): DraftTask => ({ description: "", mediaId: "", parts: [] });

const KIND_PREFIX: Record<MediaItem["kind"], string> = { model_3d: "3D model", document: "Document", image: "Image" };

export default function NewJob() {
  const nav = useNavigate();
  const { data: users } = useAsync(api.users, []);
  const { data: media } = useAsync(api.media, []);
  const employees = (users ?? []).filter((u) => u.user_class === "employee");
  const [title, setTitle] = useState("");
  const [assignee, setAssignee] = useState("");
  const [dueDate, setDueDate] = useState("");
  const [tasks, setTasks] = useState<DraftTask[]>([blank()]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const update = (i: number, patch: Partial<DraftTask>) =>
    setTasks((ts) => ts.map((task, n) => (n === i ? { ...task, ...patch } : task)));
  const mediaById = (id: string): MediaItem | undefined => media?.find((m) => m.id === id);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const job = await api.createJob({
        title, assigned_to: assignee || employees[0]?.id || "", due_date: dueDate || null,
        tasks: tasks.filter((task) => task.description.trim()).map((task) => ({
          description: task.description,
          media: task.mediaId ? [{ media_id: task.mediaId, node_ids: task.parts }] : [],
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
      <h1>{t("New job")}</h1>
      <form onSubmit={submit}>
        <section className="card">
          <label>{t("Title")}<input value={title} onChange={(e) => setTitle(e.target.value)}
            placeholder={t("e.g. Monthly extinguisher check, building A")} required /></label>
          <label>{t("Assign to")}
            <select value={assignee || employees[0]?.id || ""} onChange={(e) => setAssignee(e.target.value)}>
              {employees.length === 0 && <option value="">{t("No employees in your company yet")}</option>}
              {employees.map((u) => <option key={u.id} value={u.id}>{u.username}</option>)}
            </select>
          </label>
          <label>{t("Due date (optional)")}<input type="date" value={dueDate} min={today()}
            onChange={(e) => setDueDate(e.target.value)} /></label>
        </section>

        {tasks.map((task, i) => {
          const linked = mediaById(task.mediaId);
          return (
            <section className="card" key={i}>
              <div className="card-head">
                <h2>{t("Task {n}", { n: i + 1 })}</h2>
                {tasks.length > 1 && (
                  <button type="button" className="btn btn-small btn-ghost" onClick={() => setTasks(tasks.filter((_, n) => n !== i))}>
                    <Trash2 aria-hidden />{t("Remove")}
                  </button>
                )}
              </div>
              <textarea rows={2} value={task.description} placeholder={t("What should be checked or done?")}
                onChange={(e) => update(i, { description: e.target.value })} />
              <label className="small">{t("Reference material (optional)")}
                <select value={task.mediaId} onChange={(e) => update(i, { mediaId: e.target.value, parts: [] })}>
                  <option value="">{t("None")}</option>
                  {(media ?? []).map((m) => <option key={m.id} value={m.id}>{t(KIND_PREFIX[m.kind])}: {m.title}</option>)}
                </select>
              </label>
              {linked?.kind === "model_3d" && (linked.metadata.parts?.length ?? 0) > 0 && (
                <fieldset className="parts">
                  <legend className="small">{t("Parts this task is about (highlighted in the 3D view)")}</legend>
                  {linked.metadata.parts!.map((p) => (
                    <label key={p.id} className="check small">
                      <input type="checkbox" checked={task.parts.includes(p.id)} onChange={(e) =>
                        update(i, { parts: e.target.checked ? [...task.parts, p.id] : task.parts.filter((x) => x !== p.id) })} />
                      {p.name}
                    </label>
                  ))}
                </fieldset>
              )}
            </section>
          );
        })}
        <div className="row">
          <button type="button" className="btn btn-big" onClick={() => setTasks([...tasks, blank()])}><Plus aria-hidden />{t("Add task")}</button>
          <button className="btn btn-big btn-primary" disabled={busy || !employees.length}>
            <Check aria-hidden />{busy ? t("Creating…") : t("Create job")}
          </button>
        </div>
        <ErrorBox error={error} />
      </form>
    </div>
  );
}
