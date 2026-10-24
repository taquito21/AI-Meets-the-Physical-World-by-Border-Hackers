import { Fragment, useState } from "react";
import { GraduationCap, History, Play, TriangleAlert } from "lucide-react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, ApiError } from "../api";
import { Chip, ErrorBox, InspectionChip, ModeBadge, useAsync, when } from "../components/ui";
import { t } from "../i18n";
import { useSession } from "../session";

// Unit record fields, finding statuses and activity events arrive as codes; these are their plain-language names.
const FIELD_LABEL: Record<string, string> = {
  location: "Location",
  manufactured: "Manufactured",
  commissioned: "In service since",
  identified_by: "Identified by",
  note: "Note",
};

const FINDING_LABEL: Record<string, string> = {
  open: "Reported",
  assigned: "Assigned",
  action_recorded: "Fix recorded",
  awaiting_verification: "Waiting for a check",
  closed: "Closed: fixed",
  void: "Cancelled",
};

const EVENT_LABEL: Record<string, string> = {
  inspection_started: "Inspection started",
  item_reopened: "Check reopened",
  evidence_submitted: "Photo added",
  more_evidence_recommended: "AI suggested another photo",
  finding_created: "Problem reported",
  item_passed: "Check marked as good",
  item_failed: "Check marked with a problem",
  item_not_applicable: "Check marked as doesn't apply",
  inspection_submitted: "Sent for review",
  more_evidence_requested: "Supervisor asked for a new photo",
  review_approve: "Inspection approved",
  review_reject: "Inspection rejected",
  review_request_evidence: "Changes requested",
  finding_assigned: "Problem assigned",
  finding_action_recorded: "Fix recorded",
  finding_awaiting_verification: "Fix waiting for a check",
  finding_closed: "Problem closed: fixed",
  finding_void: "Problem cancelled",
  evidence_corrective_before: "Before photo added",
  evidence_corrective_after: "After photo added",
  assessment_completed: "AI checked the photo",
  assessment_unavailable: "AI photo feedback not available",
  assessment_failed: "AI could not check the photo",
  assessment_refused: "AI could not check the photo",
  package_loaded: "Equipment data loaded",
};

const label = (map: Record<string, string>, code: string) => (map[code] ? t(map[code]) : code.replace(/_/g, " "));

export default function Passport() {
  const { serial = "" } = useParams();
  const { data, error } = useAsync(() => api.passport(serial), [serial]);
  const { name } = useSession();
  const nav = useNavigate();
  const [err, setErr] = useState<ApiError | null>(null);

  if (error) return <div className="page"><ErrorBox error={{ message: error }} /></div>;
  if (!data) return <div className="page muted">{t("Loading…")}</div>;
  const start = async () => {
    try {
      const r = await api.startInspection(serial, name);
      nav(`/inspections/${r.inspection_id}`);
    } catch (e) {
      setErr(e as ApiError);
    }
  };
  return (
    <div className="page">
      <h1>{t("Product passport")}</h1>
      <p className="muted small">{t("Record for one physical unit. Opening it via a QR code or link identifies the record. It does not prove the unit is physically present.")}</p>
      <dl className="kv card">
        <dt>{t("Serial number")}</dt><dd><b>{data.instance.serial_number}</b></dd>
        <dt>{t("Product")}</dt><dd>{data.revision.product_name} · {data.revision.manufacturer}</dd>
        <dt>{t("Engineering revision")}</dt><dd><Link to={`/products/${encodeURIComponent(data.revision.id)}`}>{data.revision.revision}</Link></dd>
        {Object.entries(data.instance.metadata as Record<string, string>).map(([k, v]) => <Fragment key={k}><dt>{FIELD_LABEL[k] ? t(FIELD_LABEL[k]) : k}</dt><dd>{v}</dd></Fragment>)}
      </dl>
      <button className="btn btn-primary" onClick={start}><Play aria-hidden />{t("Start or continue inspection")}</button>
      <ErrorBox error={err} />
      <section className="card">
        <h2 className="with-icon"><History aria-hidden />{t("Inspection history")}</h2>
        {data.inspections.length === 0 && <p className="muted small">{t("No inspections yet.")}</p>}
        <ul className="list">
          {data.inspections.map((i: any) => (
            <li key={i.id}>
              <Link to={`/inspections/${i.id}/summary`}>{when(i.started_at)}, {i.inspector}</Link> <ModeBadge mode={i.mode} /> <InspectionChip status={i.status} />
            </li>
          ))}
        </ul>
      </section>
      <section className="card">
        <h2 className="with-icon"><TriangleAlert aria-hidden />{t("Problems")}</h2>
        {data.findings.length === 0 && <p className="muted small">{t("No findings.")}</p>}
        {data.findings.map((f: any) => <div key={f.id} className="small">{when(f.created_at)}: {f.mode === "demo" && <span className="chip chip-demo"><GraduationCap aria-hidden />{t("Practice")}</span>} <b>{f.component_name ?? f.component_id}</b> {f.description} <Chip>{label(FINDING_LABEL, f.status)}</Chip></div>)}
      </section>
      <section className="card">
        <h2>{t("Timeline")}</h2>
        <ul className="timeline">
          {data.activity.map((a: any) => <li key={a.id}><span className="tiny muted">{when(a.created_at)}</span> <b>{a.actor === "ai" ? t("AI") : a.actor ?? t("system")}</b> {label(EVENT_LABEL, a.event_type)}</li>)}
        </ul>
      </section>
    </div>
  );
}
