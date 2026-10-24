import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, type Job } from "../api";
import { AskBox } from "../components/AskBox";
import { TaskCard } from "../components/TaskCard";
import { CountChips, ErrorBox, Lightbox, Progress, usePolling } from "../components/ui";
import { useSession } from "../session";

export default function JobDetail() {
  const { id = "" } = useParams();
  const { me } = useSession();
  const nav = useNavigate();
  const [job, setJobRaw] = useState<Job | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [lightbox, setLightbox] = useState<string | null>(null);
  // Every write bumps the version; a poll that started before a write is discarded so it can't
  // overwrite the fresher job returned by that write.
  const version = useRef(0);
  const setJob = (j: Job) => {
    version.current += 1;
    setJobRaw(j);
  };

  useEffect(() => {
    api.job(id).then(setJob).catch((e) => setError(e.message));
  }, [id]);
  usePolling(() => {
    const started = version.current;
    api.job(id).then((j) => { if (version.current === started) setJob(j); }).catch(() => undefined);
  }, 6000, [id]); // picks up changes made on the other person's device

  if (error) return <div className="page"><ErrorBox error={error} /><Link to="/">Back to jobs</Link></div>;
  if (!job || !me) return <div className="page muted">Loading job…</div>;

  const remove = async () => {
    if (!confirm(`Delete "${job.title}" with all its tasks and evidence? This cannot be undone.`)) return;
    try {
      await api.deleteJob(job.id);
      nav("/");
    } catch (e) {
      setError((e as Error).message);
    }
  };
  return (
    <div className="page">
      <Link to="/" className="small">← Jobs</Link>
      <div className="card-head">
        <div>
          <h1>{job.title}</h1>
          <div className="small muted">Assigned to {job.assigned_to?.username ?? "nobody"}</div>
        </div>
        <CountChips counts={job.counts} />
      </div>
      <Progress counts={job.counts} />
      {job.tasks.map((t) => (
        <TaskCard key={t.id} task={t} role={me.user_class} onJob={setJob} onOpenImage={setLightbox} />
      ))}
      <AskBox />
      {me.user_class === "employer" && (
        <button className="btn btn-red-ghost" onClick={remove}>Delete job</button>
      )}
      <Lightbox src={lightbox} onClose={() => setLightbox(null)} />
    </div>
  );
}
