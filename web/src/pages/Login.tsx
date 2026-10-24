import { Suspense, lazy, useState, type FormEvent } from "react";
import { ArrowLeft, HardHat, KeyRound, LogIn, ScanFace, ShieldCheck } from "lucide-react";
import { api, ApiError, type Role } from "../api";
import { LanguageSwitch } from "../components/LanguageSwitch";
import { t } from "../i18n";
import { useSession } from "../session";

// Loaded only when someone chooses face sign-in (the models are large).
const FaceCamera = lazy(() => import("../face/FaceCamera"));

const ROLE_INFO: Record<Role, { icon: typeof HardHat; title: string; text: string }> = {
  inspector: { icon: HardHat, title: "Worker", text: "I do inspections in the field" },
  supervisor: { icon: ShieldCheck, title: "Supervisor|card", text: "I review and approve inspections" },
};

// Server answers turned into plain advice for the person in front of the screen.
export function signInMessage(e: unknown): string {
  const err = e as ApiError;
  if (err?.message === "worker_account") return t("This is a worker account. Go back and choose “Worker”.");
  if (err?.message === "supervisor_account") return t("This is a supervisor account. Go back and choose “Supervisor”.");
  if (err?.message === "Face not recognized") return t("We didn't recognize your face. Try again with more light, or sign in with your password.");
  return t(err?.message ?? "Something went wrong. Try again.");
}

export default function Login() {
  const { setUser, label } = useSession();
  const [role, setRole] = useState<Role | null>(null);
  const [usingFace, setUsingFace] = useState(false);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const passwordSignIn = async (e: FormEvent) => {
    e.preventDefault();
    if (!role) return;
    setBusy(true);
    setError(null);
    try {
      setUser((await api.login(username, password, role)).user);
    } catch (err) {
      setError(signInMessage(err));
    } finally {
      setBusy(false);
    }
  };

  const faceSignIn = async (embeddings: number[][]) => {
    if (!role) return;
    setUsingFace(false);
    setBusy(true);
    setError(null);
    try {
      setUser((await api.faceLogin(embeddings, role)).user);
    } catch (err) {
      setError(signInMessage(err));
    } finally {
      setBusy(false);
    }
  };

  const info = role ? ROLE_INFO[role] : null;
  return (
    <div className="login">
      <header className="login-top">
        <b>{label}</b>
        <LanguageSwitch />
      </header>
      <main className="login-main">
        {!role ? (
          <>
            <h1>{t("Welcome")}</h1>
            <p className="muted">{t("Who are you? Choose to sign in.")}</p>
            <div className="role-cards">
              {(Object.keys(ROLE_INFO) as Role[]).map((r) => {
                const { icon: Icon, title, text } = ROLE_INFO[r];
                return (
                  <button key={r} className={`role-card role-${r}`} onClick={() => setRole(r)}>
                    <span className="role-icon" aria-hidden><Icon /></span>
                    <b>{t(title)}</b>
                    <span>{t(text)}</span>
                  </button>
                );
              })}
            </div>
          </>
        ) : (
          <section className="card login-card">
            <button className="btn btn-ghost btn-small" onClick={() => { setRole(null); setError(null); setUsingFace(false); }}>
              <ArrowLeft aria-hidden />{t("Change")}
            </button>
            {info && (
              <h1 className="with-icon"><info.icon aria-hidden />{t("Sign in as {role}", { role: t(info.title).toLowerCase() })}</h1>
            )}
            {usingFace ? (
              <Suspense fallback={<p className="muted">{t("Preparing the camera…")}</p>}>
                <FaceCamera purpose="login" onDone={faceSignIn} onCancel={() => setUsingFace(false)} />
              </Suspense>
            ) : (
              <>
                <button className="btn btn-primary btn-big login-face" disabled={busy} onClick={() => { setError(null); setUsingFace(true); }}>
                  <ScanFace aria-hidden />{t("Sign in with my face")}
                </button>
                <p className="tiny muted">{t("To use your face, first sign in with your password and register it in “My account”.")}</p>
                <div className="login-or"><span>{t("or")}</span></div>
                <form onSubmit={passwordSignIn} className="login-form">
                  <label>
                    <span>{t("Username")}</span>
                    <input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username"
                      autoCapitalize="none" autoCorrect="off" spellCheck={false} required />
                  </label>
                  <label>
                    <span>{t("Password")}</span>
                    <input type="password" value={password} onChange={(e) => setPassword(e.target.value)}
                      autoComplete="current-password" required />
                  </label>
                  <button className="btn btn-big" type="submit" disabled={busy || !username || !password}>
                    {busy ? t("Signing in…") : <><LogIn aria-hidden />{t("Sign in")}</>}
                  </button>
                </form>
              </>
            )}
            {error && <div className="error-box" role="alert"><strong className="with-icon"><KeyRound aria-hidden />{error}</strong></div>}
            <p className="tiny muted">{role === "inspector" ? t("No account? Ask your supervisor to add you.") : t("Supervisor accounts are created by the administrator.")}</p>
          </section>
        )}
      </main>
    </div>
  );
}
