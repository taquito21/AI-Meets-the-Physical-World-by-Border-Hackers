import { Link } from "react-router-dom";
import { Flag, Plus } from "lucide-react";
import { api, type JobSummary } from "../api";
import { CountChips, ErrorBox, Progress, useAsync, usePolling, when } from "../components/ui";
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
        <CountChips counts={job.counts} />
      </Link>
    </li>
  );
}

export default function Jobs() {
  const { me } = useSession();
  const { data: jobs, error, reload } = useAsync(api.jobs, []);
  usePolling(reload, 8000);
  const employer = me?.user_class === "employer";
  const flagged = (jobs ?? []).filter((j) => j.counts.flagged > 0);

  return (
    <div className="page">
      <div className="card-head">
        <h1>{t(employer ? "Jobs" : "My jobs")} <small>{me?.company.name}</small></h1>
        {employer && <Link className="btn btn-big btn-primary" to="/jobs/new"><Plus aria-hidden />{t("New job")}</Link>}
      </div>
      {!employer && <p className="muted">{t("Open a job and work through its tasks, one by one.")}</p>}
      <ErrorBox error={error} />
      {!jobs && !error && <p className="muted">{t("Loading…")}</p>}
      {employer && flagged.length > 0 && (
        <section className="card card-flag">
          <h2 className="with-icon"><Flag aria-hidden />{t("Needs your input")}</h2>
          <ul className="list">{flagged.map((j) => <JobRow key={j.id} job={j} employer />)}</ul>
        </section>
      )}
      {jobs && (
        <section className="card">
          {jobs.length === 0
            ? <p className="muted">{t(employer ? "No jobs yet. Create one and assign it to an employee." : "No jobs assigned to you yet.")}</p>
            : <ul className="list">{jobs.map((j) => <JobRow key={j.id} job={j} employer={employer} />)}</ul>}
        </section>
      )}
    </div>
  );
}
