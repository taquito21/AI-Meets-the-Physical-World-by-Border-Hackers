import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ArrowRight, ChartColumn, ClipboardCheck, CloudOff, Pointer, Search, Send, Upload, UserRound, Wrench } from "lucide-react";
import { api } from "../api";
import { INDUSTRY_ICON, InspectionChip, ModeBadge, useAsync, when } from "../components/ui";
import { t } from "../i18n";
import { useSession } from "../session";

const SCENARIOS = [
  { industry: "Furniture", cls: "", tag: "Furniture", title: "Chairs and tables", text: "Includes a real chair from the venue, rebuilt in 3D from photos." },
  { industry: "Electrical", cls: "scenario-electrical", tag: "Electrical", title: "Electrical control panel", text: "Visual and paperwork check. You never open the panel or touch live parts." },
  { industry: "Facility Safety", cls: "scenario-safety", tag: "Fire safety", title: "Fire extinguisher", text: "Look at the gauge, pin, hose, label and tag without handling it." },
];

export default function Home() {
  const { name, setName, role, setRole, health, label, setIndustry } = useSession();
  const nav = useNavigate();
  const { data: all } = useAsync(() => api.inspections(), []);
  const [editingName, setEditingName] = useState(!name.trim());
  const ongoing = (all ?? []).filter((i) => ["in_progress", "changes_requested"].includes(i.status)).slice(0, 5);
  const waitingReview = (all ?? []).filter((i) => i.status === "submitted").length;

  return (
    <div className="page">
      <section className="hero">
        <h1>{label}</h1>
        <p>{t("Check equipment step by step from your phone. The app shows you what to look at, the AI tells you if your photo is clear, and you decide the result.")}</p>
      </section>

      {ongoing.length > 0 && (
        <section className="card">
          <h2>{t("Continue where you left off")}</h2>
          <ul className="list">
            {ongoing.map((i) => (
              <li key={i.id} className="resume">
                <span className="grow">
                  <b>{i.product_name}</b> <span className="muted small">{i.serial_number} · {i.inspector}, {when(i.updated_at)}</span>
                </span>
                <ModeBadge mode={i.mode} />
                <InspectionChip status={i.status} />
                <Link className="btn btn-primary btn-small" to={`/inspections/${i.id}`}>{t("Continue")} <ArrowRight aria-hidden /></Link>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section>
        <h2>{ongoing.length ? t("Or start a new inspection") : t("Start an inspection")}</h2>
        <p className="muted small">{t("What kind of equipment are you checking?")}</p>
        <div className="scenarios">
          {SCENARIOS.map((s) => {
            const Icon = INDUSTRY_ICON[s.industry];
            return (
              <button key={s.industry} className={`scenario ${s.cls}`} onClick={() => { setIndustry(s.industry); nav("/catalog"); }}>
                <span className="scenario-icon" aria-hidden><Icon /></span>
                <span className="scenario-tag">{t(s.tag)}</span>
                <b>{t(s.title)}</b>
                <span>{t(s.text)}</span>
                <span className="scenario-go">{t("Choose")} <ArrowRight aria-hidden /></span>
              </button>
            );
          })}
        </div>
      </section>

      <section className="card">
        <h2>{t("How it works")}</h2>
        <ol className="how-steps">
          <li><b className="with-icon"><Search aria-hidden />{t("Choose the equipment")}</b><span>{t("Pick the unit in front of you. First time? Choose")} <i>{t("Practice")}</i> {t("to try it with sample photos.")}</span></li>
          <li><b className="with-icon"><Pointer aria-hidden />{t("Follow the steps")}</b><span>{t("The app tells you which part to check next. Take a photo and the AI says if it is clear enough.")}</span></li>
          <li><b className="with-icon"><Send aria-hidden />{t("Choose a result and send it")}</b><span>{t("For each check tap")} <i>{t("Looks good")}</i> {t("or")} <i>{t("Report a problem")}</i>. {t("At the end, send it for review.")}</span></li>
        </ol>
        <p className="muted small">{t("The AI only helps. A person always makes the decision.")}</p>
      </section>

      {health && !health.ai.available && (
        <div className="notice small" title={health.ai.detail}>
          <b className="with-icon"><CloudOff aria-hidden />{t("AI photo feedback is off right now.")}</b> {t("You can still inspect: look at each part yourself and choose the result.")}
        </div>
      )}

      <section className="card">
        {editingName ? (
          <>
            <h2 className="with-icon"><UserRound aria-hidden />{t("Who is working?")}</h2>
            <div className="row">
              <input value={name} onChange={(e) => setName(e.target.value)} aria-label={t("Your name")} placeholder={t("Your name")} />
              <div className="segmented">
                <button className={role === "inspector" ? "on" : ""} onClick={() => setRole("inspector")}>{t("Inspector")}</button>
                <button className={role === "supervisor" ? "on" : ""} onClick={() => setRole("supervisor")}>{t("Supervisor")}</button>
              </div>
              <button className="btn btn-primary" disabled={!name.trim()} onClick={() => setEditingName(false)}>{t("Save")}</button>
            </div>
            <p className="muted small">{t("Your name is saved with everything you do. A supervisor must be a different person from the inspector. This demo has no passwords.")}</p>
          </>
        ) : (
          <div className="row">
            <span className="grow with-icon"><UserRound aria-hidden /><span>{t("Working as")} <b>{name}</b> ({role === "supervisor" ? t("supervisor") : t("inspector")})</span></span>
            <button className="btn btn-ghost btn-small" onClick={() => setEditingName(true)}>{t("Change")}</button>
          </div>
        )}
      </section>

      <section>
        <h2>{t("For supervisors")}</h2>
        <div className="tiles">
          <Link to="/supervisor" className="tile">
            <b className="with-icon"><ClipboardCheck aria-hidden />{t("Review inspections")}</b>
            <span>{waitingReview ? t("{n} waiting for your review", { n: waitingReview }) : t("Approve or ask for changes")}</span>
          </Link>
          <Link to="/findings" className="tile"><b className="with-icon"><Wrench aria-hidden />{t("Problems to fix")}</b><span>{t("Assign a fix, add photos, close it")}</span></Link>
          <Link to="/dashboard" className="tile"><b className="with-icon"><ChartColumn aria-hidden />{t("Dashboard")}</b><span>{t("All inspections and problems at a glance")}</span></Link>
        </div>
      </section>
      <p className="tiny muted"><Link to="/import" className="with-icon"><Upload aria-hidden />{t("Add equipment from a manufacturer package (administrators)")}</Link></p>
    </div>
  );
}
