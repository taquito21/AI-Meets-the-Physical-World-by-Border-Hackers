import { useState } from "react";
import { LogIn } from "lucide-react";
import { LanguageSwitch } from "../components/LanguageSwitch";
import { ErrorBox } from "../components/ui";
import { t } from "../i18n";
import { useSession } from "../session";

export default function Login() {
  const { signIn, error: sessionError } = useSession();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await signIn(email, password);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="page login">
      <div className="card-head">
        <h1 className="login-logo">
          <img src="/brand/fieldsight-logo.jpg" alt="FieldSight: AI-powered 3D field inspections" width={900} height={626} />
        </h1>
        <LanguageSwitch />
      </div>
      <p className="muted">{t("Your jobs, step by step: take photos, write notes, and mark each task done.")}</p>
      <form className="card" onSubmit={submit}>
        <label>{t("Email")}<input type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} required /></label>
        <label>{t("Password")}<input type="password" autoComplete="current-password" value={password}
          onChange={(e) => setPassword(e.target.value)} required /></label>
        <button className="btn btn-big btn-primary" disabled={busy}><LogIn aria-hidden />{busy ? t("Signing in…") : t("Sign in")}</button>
        <ErrorBox error={error ?? sessionError} />
      </form>
    </div>
  );
}
