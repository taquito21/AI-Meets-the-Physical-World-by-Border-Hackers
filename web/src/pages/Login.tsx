import { useState } from "react";
import { ErrorBox } from "../components/ui";
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
      <h1>Field Assistant</h1>
      <p className="muted">Jobs, tasks and photo evidence for field work.</p>
      <form className="card" onSubmit={submit}>
        <label>Email<input type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} required /></label>
        <label>Password<input type="password" autoComplete="current-password" value={password}
          onChange={(e) => setPassword(e.target.value)} required /></label>
        <button className="btn btn-primary" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button>
        <ErrorBox error={error ?? sessionError} />
      </form>
    </div>
  );
}
