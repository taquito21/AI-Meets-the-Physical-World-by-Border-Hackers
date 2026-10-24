import { Link } from "react-router-dom";
import { CalendarClock, CircleX, ClipboardList, Flag, FolderOpen, Plus, Users, type LucideIcon } from "lucide-react";
import { api, type Dashboard, type JobSummary } from "../api";
import {
  CountChips, DueChip, ErrorBox, Progress, StatusChip, daysUntil, isOverdue, useAsync, usePolling, when,
} from "../components/ui";
import { t } from "../i18n";
import { useSession } from "../session";

function JobRow({ job, employer }: { job: JobSummary; employer: boolean }) {
  return (
    <li>
      <Link to={`/jobs/${job.id}`} className="job-row">
        <div className="grow">
          <b>{job.title}</b>
          <div className="tiny muted">{employer ? `${job.assigned_to?.username ?? t("Nobody")} · ` : ""}{when(job.created_at)}</div>
          <Progress counts={job.counts} />
        </div>
        <span className="row-inline"><DueChip job={job} /><CountChips counts={job.counts} /></span>
      </Link>
    </li>
  );
}

function Tile({ icon: Icon, value, label, tone }: { icon: LucideIcon; value: number; label: string; tone: string }) {
  return (
    <div className={`stat stat-${value ? tone : "neutral"}`}>
      <Icon aria-hidden />
      <b>{value}</b>
      <span>{t(label)}</span>
    </div>
  );
}

// The employer's home: what needs them now, deadlines, the team's workload, then every job.
function EmployerHome({ data }: { data: Dashboard }) {
  const open = data.jobs.filter((j) => !j.finished);
  const deadlines = open.filter((j) => j.due_date && daysUntil(j.due_date) <= 3);
  const flagged = data.attention.filter((a) => a.status === "flagged");
  const failed = data.attention.filter((a) => a.status === "failed");
  return (
    <>
      <div className="stats">
        <Tile icon={ClipboardList} value={open.length} label="Open jobs" tone="blue" />
        <Tile icon={CalendarClock} value={open.filter(isOverdue).length} label="Overdue" tone="red" />
        <Tile icon={Flag} value={flagged.length} label="Waiting for you" tone="purple" />
        <Tile icon={CircleX} value={failed.length} label="Failed tasks" tone="red" />
      </div>

      {data.attention.length > 0 && (
        <section className="card card-flag">
          <h2 className="with-icon"><Flag aria-hidden />{t("Needs your input")}</h2>
          <ul className="list">
            {[...flagged, ...failed].map((a) => (
              <li key={a.id}>
                <Link to={`/jobs/${a.job_id}`} className="job-row">
                  <div className="grow">
                    <b>{a.description}</b>
                    <div className="tiny muted">{a.job_title} · {a.assigned_to?.username ?? t("Nobody")} · {when(a.updated_at)}</div>
                  </div>
                  <StatusChip status={a.status} />
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}

      {deadlines.length > 0 && (
        <section className="card">
          <h2 className="with-icon"><CalendarClock aria-hidden />{t("Overdue and due soon")}</h2>
          <ul className="list">{deadlines.map((j) => <JobRow key={j.id} job={j} employer />)}</ul>
        </section>
      )}

      {data.team.length > 0 && (
        <section className="card">
          <h2 className="with-icon"><Users aria-hidden />{t("Team")}</h2>
          <ul className="list">
            {data.team.map((m) => (
              <li key={m.id} className="team-row">
                <b className="grow">{m.username}</b>
                <span className="small muted">{t("{n} open jobs", { n: m.open_jobs })}</span>
                <span className="small muted">{t("{done} of {total} tasks done", { done: m.tasks_done, total: m.tasks_total })}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="card">
        <h2 className="with-icon"><ClipboardList aria-hidden />{t("All jobs")}</h2>
        {data.jobs.length === 0
          ? <p className="muted">{t("No jobs yet. Create one and assign it to an employee.")}</p>
          : <ul className="list">{data.jobs.map((j) => <JobRow key={j.id} job={j} employer />)}</ul>}
      </section>
    </>
  );
}

function EmployeeJobs({ jobs }: { jobs: JobSummary[] }) {
  return (
    <>
      <p className="muted">{t("Open a job and work through its tasks, one by one.")}</p>
      <section className="card">
        {jobs.length === 0
          ? <p className="muted">{t("No jobs assigned to you yet.")}</p>
          : <ul className="list">{jobs.map((j) => <JobRow key={j.id} job={j} employer={false} />)}</ul>}
      </section>
    </>
  );
}

export default function Jobs() {
  const { me } = useSession();
  const employer = me?.user_class === "employer";
  const dash = useAsync(() => (employer ? api.dashboard() : Promise.resolve(null)), [employer]);
  const jobs = useAsync(() => (employer ? Promise.resolve(null) : api.jobs()), [employer]);
  usePolling(() => (employer ? dash.reload() : jobs.reload()), 8000, [employer]);
  const error = dash.error ?? jobs.error;
  const loaded = employer ? dash.data : jobs.data;

  return (
    <div className="page">
      <div className="card-head">
        <h1>{t(employer ? "Overview" : "My jobs")} <small>{me?.company.name}</small></h1>
        {employer && (
          <div className="row">
            <Link className="btn" to="/media"><FolderOpen aria-hidden />{t("Media")}</Link>
            <Link className="btn btn-big btn-primary" to="/jobs/new"><Plus aria-hidden />{t("New job")}</Link>
          </div>
        )}
      </div>
      <ErrorBox error={error} />
      {!loaded && !error && <p className="muted">{t("Loading…")}</p>}
      {employer && dash.data && <EmployerHome data={dash.data} />}
      {!employer && jobs.data && <EmployeeJobs jobs={jobs.data} />}
    </div>
  );
}
