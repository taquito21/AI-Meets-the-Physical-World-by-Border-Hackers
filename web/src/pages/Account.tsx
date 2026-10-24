import { Suspense, lazy, useState, type FormEvent } from "react";
import { CircleCheck, LogOut, ScanFace, ShieldCheck, Trash2, UserPlus, UserRound, Users } from "lucide-react";
import { api, ApiError, type User } from "../api";
import { Chip, ErrorBox, useAsync, when } from "../components/ui";
import { t } from "../i18n";
import { signInMessage } from "./Login";
import { useSession } from "../session";

const FaceCamera = lazy(() => import("../face/FaceCamera"));

function FaceSection() {
  const { user, setUser } = useSession();
  const [consent, setConsent] = useState(false);
  const [capturing, setCapturing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (!user) return null;

  const save = async (embeddings: number[][]) => {
    setCapturing(false);
    setBusy(true);
    setError(null);
    try {
      setUser((await api.registerFace(embeddings)).user);
    } catch (e) {
      setError(signInMessage(e));
    } finally {
      setBusy(false);
    }
  };
  const remove = async () => {
    if (!window.confirm(t("Delete your face data? You can register it again later."))) return;
    setBusy(true);
    try {
      setUser((await api.deleteFace()).user);
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="card">
      <h2 className="with-icon"><ScanFace aria-hidden />{t("Sign in with your face")}</h2>
      {user.has_face ? (
        <>
          <p className="with-icon"><CircleCheck aria-hidden className="ico-green" />{t("Your face is registered. Next time, choose “Sign in with my face”.")}</p>
          <button className="btn btn-red-ghost" disabled={busy} onClick={remove}><Trash2 aria-hidden />{t("Delete my face data")}</button>
        </>
      ) : capturing ? (
        <Suspense fallback={<p className="muted">{t("Preparing the camera…")}</p>}>
          <FaceCamera purpose="enroll" onDone={save} onCancel={() => setCapturing(false)} />
        </Suspense>
      ) : (
        <>
          <ul className="small face-facts">
            <li>{t("We save only 128 numbers calculated from your face, never a photo.")}</li>
            <li>{t("They are used only to sign you in to this app, and you can delete them at any time.")}</li>
            <li>{t("It does not detect printed photos, so your password always keeps working.")}</li>
          </ul>
          <label className="check">
            <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} />
            <span>{t("I agree to register my face to sign in.")}</span>
          </label>
          <button className="btn btn-primary btn-big" disabled={!consent || busy} onClick={() => { setError(null); setCapturing(true); }}>
            <ScanFace aria-hidden />{busy ? t("Saving…") : t("Register my face")}
          </button>
        </>
      )}
      {error && <div className="error-box" role="alert"><strong>{error}</strong></div>}
    </section>
  );
}

function WorkersSection() {
  const { data, reload } = useAsync(() => api.users(), []);
  const { health } = useSession();
  const [form, setForm] = useState({ display_name: "", username: "", password: "" });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<ApiError | null>(null);
  const [added, setAdded] = useState<User | null>(null);

  const add = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      setAdded(await api.addWorker(form));
      setForm({ display_name: "", username: "", password: "" });
      reload();
    } catch (e2) {
      setErr(e2 as ApiError);
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="card">
      <h2 className="with-icon"><Users aria-hidden />{t("Workers")}</h2>
      <ul className="list">
        {(data ?? []).map((u) => (
          <li key={u.username}>
            <span className="grow"><b>{u.display_name}</b> <span className="muted small">{u.username}</span></span>
            <Chip tone={u.role === "supervisor" ? "blue" : "neutral"} icon={u.role === "supervisor" ? ShieldCheck : UserRound}>
              {u.role === "supervisor" ? t("Supervisor|card") : t("Worker")}
            </Chip>
            {u.has_face && <Chip tone="green" icon={ScanFace}>{t("Face registered")}</Chip>}
          </li>
        ))}
      </ul>
      <h3 className="with-icon"><UserPlus aria-hidden />{t("Add a worker")}</h3>
      <form className="login-form" onSubmit={add}>
        <label><span>{t("Full name")}</span>
          <input value={form.display_name} onChange={(e) => setForm({ ...form, display_name: e.target.value })} required /></label>
        <label><span>{t("Username")}</span>
          <input value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value.toLowerCase() })}
            autoCapitalize="none" autoCorrect="off" spellCheck={false} placeholder={t("e.g. juan.perez")} required /></label>
        <label><span>{t("Temporary password")}</span>
          <input value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })}
            autoComplete="new-password" required /></label>
        <p className="tiny muted">{t("At least 8 characters, with uppercase, lowercase and numbers. Give it to the worker in person.")}</p>
        <button className="btn btn-primary" type="submit" disabled={busy}><UserPlus aria-hidden />{t("Add worker")}</button>
      </form>
      {added && <p className="small with-icon"><CircleCheck aria-hidden className="ico-green" />{t("{name} can now sign in as a worker.", { name: added.display_name })}</p>}
      <ErrorBox error={err} />
      {health?.storage === "ephemeral" && (
        <p className="tiny muted">{t("Test version: new accounts and registered faces may be erased when the server restarts. The demo accounts always work.")}</p>
      )}
    </section>
  );
}

export default function Account() {
  const { user, signOut } = useSession();
  if (!user) return null;
  return (
    <div className="page">
      <h1 className="with-icon"><UserRound aria-hidden />{t("My account")}</h1>
      <section className="card">
        <div className="row">
          <span className="grow"><b>{user.display_name}</b> <span className="muted small">{user.username}</span></span>
          <Chip tone={user.role === "supervisor" ? "blue" : "neutral"} icon={user.role === "supervisor" ? ShieldCheck : UserRound}>
            {user.role === "supervisor" ? t("Supervisor|card") : t("Worker")}
          </Chip>
        </div>
        {user.created_at && <p className="tiny muted">{t("Account created {when}", { when: when(user.created_at) })}</p>}
        <button className="btn btn-ghost" onClick={signOut}><LogOut aria-hidden />{t("Sign out")}</button>
      </section>
      <FaceSection />
      {user.role === "supervisor" && <WorkersSection />}
    </div>
  );
}
