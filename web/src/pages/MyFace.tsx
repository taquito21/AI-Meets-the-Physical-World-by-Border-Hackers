import { Suspense, lazy, useState } from "react";
import { CircleCheck, ScanFace, Trash2 } from "lucide-react";
import { api } from "../api";
import { ErrorBox } from "../components/ui";
import { t } from "../i18n";
import { useSession } from "../session";

// Loaded only when the camera opens (the face models are large).
const FaceCamera = lazy(() => import("../face/FaceCamera"));

// Register or delete the signed-in person's face for face login. Only 128 numbers per sample are stored.
export default function MyFace() {
  const { me, reloadProfile } = useSession();
  const [consent, setConsent] = useState(false);
  const [capturing, setCapturing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (!me) return null;

  const save = async (embeddings: number[][]) => {
    setCapturing(false);
    setBusy(true);
    setError(null);
    try {
      await api.registerFace(embeddings);
      await reloadProfile();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const remove = async () => {
    if (!window.confirm(t("Delete your face data? You can register it again later."))) return;
    setBusy(true);
    try {
      await api.deleteFace();
      await reloadProfile();
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="page">
      <h1 className="with-icon"><ScanFace aria-hidden />{t("My face")}</h1>
      <section className="card">
        {me.has_face ? (
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
            <p>{t("Sign in by looking at the camera instead of typing your password.")}</p>
            <ul className="small face-facts">
              <li>{t("We save only 128 numbers calculated from your face, never a photo.")}</li>
              <li>{t("They are used only to sign you in to this app, and you can delete them at any time.")}</li>
              <li>{t("It does not detect printed photos, so your password always keeps working.")}</li>
            </ul>
            <label className="check">
              <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} />
              <span>{t("I agree to register my face to sign in.")}</span>
            </label>
            <button className="btn btn-big btn-primary" disabled={!consent || busy} onClick={() => { setError(null); setCapturing(true); }}>
              <ScanFace aria-hidden />{busy ? t("Saving…") : t("Register my face")}
            </button>
          </>
        )}
        <ErrorBox error={error} />
      </section>
    </div>
  );
}
