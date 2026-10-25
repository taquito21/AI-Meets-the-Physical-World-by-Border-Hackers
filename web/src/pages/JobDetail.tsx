import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, Trash2 } from "lucide-react";
import { api, type Job } from "../api";
import { TaskCard } from "../components/TaskCard";
import { CountChips, DueChip, ErrorBox, Lightbox, Progress, Typed, usePolling } from "../components/ui";
import { t } from "../i18n";
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

  if (error) return <div className="page"><ErrorBox error={error} /><Link to="/">{t("Back to jobs")}</Link></div>;
  if (!job || !me) return <div className="page muted">{t("Loading…")}</div>;

  const remove = async () => {
    if (!confirm(t("Delete \"{title}\" with all its tasks, photos and notes? This cannot be undone.", { title: job.title }))) return;
    try {
      await api.deleteJob(job.id);
      nav("/");
    } catch (e) {
      setError((e as Error).message);
    }
  };
  return (
    <div className="page">
      <Link to="/" className="small with-icon"><ArrowLeft aria-hidden />{t("Jobs")}</Link>
      <div className="card-head">
        <div>
          <h1><Typed text={job.title} original={job.original?.title} /></h1>
          <div className="small muted">{t("Assigned to {name}", { name: job.assigned_to?.username ?? t("Nobody") })} <DueChip job={job} /></div>
        </div>
        <CountChips counts={job.counts} />
      </div>
      <Progress counts={job.counts} />
      {job.tasks.map((task) => (
        <TaskCard key={task.id} task={task} role={me.user_class} onJob={setJob} onOpenImage={setLightbox} />
      ))}
      {me.user_class === "employer" && (
        <button className="btn btn-red-ghost" onClick={remove}><Trash2 aria-hidden />{t("Delete job")}</button>
      )}
      <Lightbox src={lightbox} onClose={() => setLightbox(null)} />
    </div>
  );
}
