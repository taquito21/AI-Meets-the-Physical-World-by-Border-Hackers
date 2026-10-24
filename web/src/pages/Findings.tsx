import { useState } from "react";
import { Camera, CircleCheck, CircleX, Eye, GraduationCap, Pointer, TriangleAlert, Undo2, UserPlus, UserRound, Wrench, type LucideIcon } from "lucide-react";
import { Link } from "react-router-dom";
import { api, ApiError, type Finding } from "../api";
import { Chip, ErrorBox, Lightbox, SEVERITY_LABEL, useAsync, when } from "../components/ui";
import { t } from "../i18n";
import { useSession } from "../session";

// Labels and "next" sentences are English keys; they are translated with t() where they are shown.
const NEXT: Record<string, { to: string; label: string; icon: LucideIcon; needs?: "assignee" | "note" }[]> = {
  open: [{ to: "assigned", label: "Assign to this person", icon: UserPlus, needs: "assignee" },
    { to: "void", label: "Cancel: reported by mistake", icon: CircleX, needs: "note" }],
  assigned: [{ to: "action_recorded", label: "Save what was done", icon: Wrench, needs: "note" }],
  action_recorded: [{ to: "awaiting_verification", label: "Ask someone to check the fix", icon: Eye }],
  awaiting_verification: [{ to: "closed", label: "Fix confirmed: close", icon: CircleCheck },
    { to: "assigned", label: "Not fixed: send back", icon: Undo2 }],
};

// Plain-language status, plus the one thing to do next.
const STATUS: Record<string, { label: string; icon: LucideIcon; next: string }> = {
  open: { label: "Reported", icon: TriangleAlert, next: "Write who will fix it and tap “Assign to this person”." },
  assigned: { label: "Assigned", icon: UserRound, next: "When the work is done, add an after photo and describe what was done." },
  action_recorded: { label: "Fix recorded", icon: Wrench, next: "Ask another person to check the fix." },
  awaiting_verification: { label: "Waiting for a check", icon: Eye, next: "A different person checks the fix and closes it, or sends it back." },
  closed: { label: "Closed: fixed", icon: CircleCheck, next: "" },
  void: { label: "Cancelled", icon: CircleX, next: "" },
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
          <div className="muted small">{f.product_instance_id} · {t("reported {when} by {who}", { when: when(f.created_at), who: f.created_by })} · <Link to={`/inspections/${f.inspection_id}/summary`}>{t("see the inspection")}</Link></div>
        </div>
        <div>{f.mode === "demo" && <span className="chip chip-demo" title={t("From a practice inspection")}><GraduationCap aria-hidden />{t("Practice")}</span>} <Chip tone={tone} icon={STATUS[f.status]?.icon}>{t(STATUS[f.status]?.label ?? f.status)}</Chip> <Chip tone="red" icon={TriangleAlert}>{t(SEVERITY_LABEL[f.severity] ?? f.severity)}</Chip></div>
      </div>
      <p>{f.description}</p>
      {STATUS[f.status]?.next && <div className="now now-todo"><Pointer aria-hidden />{t("Next:")} {t(STATUS[f.status].next)}</div>}
      {f.corrective_action && (
        <p className="small">
          {f.corrective_action.assigned_to && <>{t("Assigned to")} <b>{f.corrective_action.assigned_to}</b></>}
          {f.corrective_action.description && ` · “${f.corrective_action.description}” (${f.corrective_action.recorded_by})`}
          {f.corrective_action.verified_by && ` · ${t("verified by {who}", { who: f.corrective_action.verified_by })}`}
        </p>
      )}
      <div className="thumbs">
        {f.evidence.map((e) => (
          <figure key={e.id}><img src={e.url} alt="" onClick={() => onOpen(e.url)} /><figcaption className="tiny">{e.kind === "corrective_before" ? t("before fix") : e.kind === "corrective_after" ? t("after fix") : e.kind === "demo" ? t("practice photo") : t("from inspection")}</figcaption></figure>
        ))}
      </div>
      {actions.length > 0 && (
        <div className="actions">
          {actions.some((a) => a.needs) && (
            <input value={text} onChange={(e) => setText(e.target.value)}
              placeholder={f.status === "open" ? t("Who will fix it? (or why it was a mistake)") : t("What was done to fix it?")} />
          )}
          <div className="row">
            {actions.map((a, n) => <button key={a.to} className={n === 0 ? "btn btn-primary" : "btn btn-ghost"} disabled={busy} onClick={() => go(a.to)}><a.icon aria-hidden />{t(a.label)}</button>)}
            {!["closed", "void"].includes(f.status) && (
              <>
                <label className="btn btn-ghost"><Camera aria-hidden />{t("Photo before the fix")}<input type="file" accept="image/*" capture="environment" hidden onChange={(e) => photo(e.target.files?.[0], "corrective_before")} /></label>
                <label className="btn btn-ghost"><Camera aria-hidden />{t("Photo after the fix")}<input type="file" accept="image/*" capture="environment" hidden onChange={(e) => photo(e.target.files?.[0], "corrective_after")} /></label>
              </>
            )}
          </div>
          <p className="tiny muted">{t("To close it you need a photo after the fix, and the person who checks it must be different from the person who did the work.")}</p>
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
      <h1 className="with-icon"><Wrench aria-hidden />{t("Problems to fix")}</h1>
      <p className="muted small">{t("Every problem reported during an inspection goes through: reported → assigned → fix recorded → checked by another person → closed.")}</p>
      {data?.length === 0 && <p className="muted">{t("No problems reported.")}</p>}
      {data?.map((f) => <FindingCard key={f.id} f={f} onChange={reload} onOpen={setLightbox} />)}
      <Lightbox src={lightbox} onClose={() => setLightbox(null)} />
    </div>
  );
}
