// Front camera + face check for sign-in and face registration. Everything happens on this device: frames are drawn
// to an off-screen canvas, the face is found and turned into 128 numbers by ./engine, and only those numbers are
// handed to onDone. No picture is stored or sent.
import { useCallback, useEffect, useRef, useState } from "react";
import { Camera, CameraOff, CircleCheck, KeyRound, LoaderCircle, RefreshCw, ShieldCheck, TriangleAlert, X } from "lucide-react";
import { t } from "../i18n";
import { align, cosine, detect, embed, loadModels, modelsReady, type LoadProgress } from "./engine";
import "./face.css";

const NEEDED = 5; // embeddings in a row that agree with each other
const AGREE = 0.6; // cosine to the first sample of the series
const MIN_SCORE = 0.8; // detector confidence
const MIN_FACE = 0.25; // face size (√(w·h) of the box) as a share of the frame's shorter side
const INTERVAL_MS = 250; // about 4 samples per second (slower if the phone needs longer per sample)
const MAX_FRAME = 640; // longest side of the analysed frame, like a 640×480 webcam frame in the desktop app
const DARK = 50; // mean brightness (0–255) of the centre of the frame below which we ask for more light
// Phone-as-webcam and streaming apps install virtual cameras that a laptop often makes its default, so the video shows
// the app's "start me" picture instead of the person. Never chosen automatically when a real camera exists.
const VIRTUAL_CAMERA = /\b(droidcam|virtual|obs|manycam|snap camera|xsplit|epoccam|iriun|camo|ndi|mmhmm|vcam|splitcam|youcam)\b/i;
const CAMERA_KEY = "fep.faceCamera"; // the camera the person picked on this device

type CameraState = "starting" | "on" | "denied" | "missing" | "busy" | "unavailable" | "error";
type Hint =
  | "Put your face inside the oval"
  | "Move closer"
  | "Only one person in front of the camera"
  | "Look at the camera"
  | "More light"
  | "Hold still"
  | "Turn your head slightly";

const GOOD_HINTS: Hint[] = ["Hold still", "Turn your head slightly"];

const PROBLEMS: Record<Exclude<CameraState, "starting" | "on"> | "models", { title: string; text: string }> = {
  denied: {
    title: "Camera access is blocked",
    text: "Allow the camera for this site in your browser settings, then try again.",
  },
  missing: { title: "No camera found", text: "This device has no camera that the app can use." },
  busy: { title: "The camera is busy", text: "Another app is using the camera. Close it and try again." },
  unavailable: {
    title: "The camera is not available here",
    text: "The browser only allows the camera on a secure (https) page.",
  },
  error: { title: "Something went wrong. Try again.", text: "The camera or the face check stopped working." },
  models: { title: "Face recognition could not be loaded", text: "Check the internet connection and try again." },
};

function cameraProblem(e: unknown): CameraState {
  const name = e instanceof DOMException || e instanceof Error ? e.name : "";
  if (name === "NotAllowedError" || name === "SecurityError" || name === "PermissionDeniedError") return "denied";
  if (name === "NotFoundError" || name === "DevicesNotFoundError" || name === "OverconstrainedError") return "missing";
  if (name === "NotReadableError" || name === "TrackStartError" || name === "AbortError") return "busy";
  return "error";
}

function savedCamera(): string {
  try {
    return localStorage.getItem(CAMERA_KEY) ?? "";
  } catch {
    return ""; // storage unavailable
  }
}

function saveCamera(id: string) {
  try {
    if (id) localStorage.setItem(CAMERA_KEY, id);
    else localStorage.removeItem(CAMERA_KEY);
  } catch {
    /* keep the choice for this visit only */
  }
}

/** A camera by id, or with "" the browser's default front camera. */
function openCamera(deviceId: string): Promise<MediaStream> {
  const size = { width: { ideal: 640 }, height: { ideal: 480 } };
  return navigator.mediaDevices.getUserMedia({
    audio: false,
    video: deviceId ? { deviceId: { exact: deviceId }, ...size } : { facingMode: "user", ...size },
  });
}

const stopTracks = (stream: MediaStream) => stream.getTracks().forEach((track) => track.stop());

/** Mean brightness of the middle of the frame, sampling every 4th pixel. */
function brightness(rgba: Uint8ClampedArray, w: number, h: number): number {
  let sum = 0, n = 0;
  for (let y = Math.floor(h * 0.2); y < h * 0.8; y += 4) {
    for (let x = Math.floor(w * 0.25); x < w * 0.75; x += 4) {
      const i = (y * w + x) * 4;
      sum += 0.299 * rgba[i] + 0.587 * rgba[i + 1] + 0.114 * rgba[i + 2];
      n++;
    }
  }
  return n ? sum / n : 0;
}

export default function FaceCamera(props: {
  purpose: "login" | "enroll";
  onDone: (embeddings: number[][]) => void;
  onCancel: () => void;
}) {
  const { purpose } = props;
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const onDoneRef = useRef(props.onDone);
  useEffect(() => {
    onDoneRef.current = props.onDone;
  });

  const [attempt, setAttempt] = useState(0);
  const [camera, setCamera] = useState<CameraState>("starting");
  const [models, setModels] = useState<"loading" | "ready" | "failed">(modelsReady() ? "ready" : "loading");
  const [progress, setProgress] = useState<LoadProgress | null>(null);
  const [hint, setHint] = useState<Hint>("Put your face inside the oval");
  const [count, setCount] = useState(0);
  const [finished, setFinished] = useState(false);
  const [failed, setFailed] = useState(false);
  const [cameraId, setCameraId] = useState(savedCamera); // "" = the browser's default
  const [cameras, setCameras] = useState<{ id: string; label: string }[]>([]);
  const [activeId, setActiveId] = useState("");

  const stopCamera = useCallback(() => {
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    if (videoRef.current) videoRef.current.srcObject = null;
  }, []);

  // Camera: open on mount (and on "Try again" or another camera), always stop every track on unmount.
  useEffect(() => {
    let alive = true;
    (async () => {
      if (!navigator.mediaDevices?.getUserMedia) {
        setCamera("unavailable"); // no camera API: old browser or a page that is not https
        return;
      }
      try {
        let stream: MediaStream;
        let chosen = cameraId;
        try {
          stream = await openCamera(cameraId);
        } catch (e) {
          const name = e instanceof DOMException || e instanceof Error ? e.name : "";
          if (!cameraId || (name !== "OverconstrainedError" && name !== "NotFoundError")) throw e;
          saveCamera(""); // the remembered camera is gone (e.g. unplugged): use the default one
          chosen = "";
          stream = await openCamera(chosen);
        }
        // Camera names can only be read once access is granted, so the list comes after opening one.
        const inputs = (await navigator.mediaDevices.enumerateDevices().catch(() => []))
          .filter((d) => d.kind === "videoinput" && d.deviceId);
        if (!alive) return stopTracks(stream);
        const track = stream.getVideoTracks()[0];
        setCameras(inputs.map((d) => ({ id: d.deviceId, label: d.label })));
        setActiveId(track?.getSettings().deviceId ?? chosen);
        const real = inputs.find((d) => d.label && !VIRTUAL_CAMERA.test(d.label));
        if (!chosen && track && VIRTUAL_CAMERA.test(track.label) && real) {
          stopTracks(stream); // the default is a virtual camera (e.g. DroidCam): open the real one instead
          setCameraId(real.deviceId);
          return;
        }
        streamRef.current = stream;
        // e.g. the camera is unplugged or the system takes it away (track.stop() does not fire this)
        stream.getVideoTracks()[0]?.addEventListener("ended", () => alive && setCamera("error"));
        const video = videoRef.current;
        if (video) {
          video.srcObject = stream;
          await video.play().catch(() => undefined); // autoplay is allowed for a muted inline video
        }
        if (alive) setCamera("on");
      } catch (e) {
        console.error("Camera", e);
        if (alive) setCamera(cameraProblem(e));
      }
    })();
    return () => {
      alive = false;
      stopCamera();
    };
  }, [attempt, cameraId, stopCamera]);

  // Models: downloaded once (about 40 MB), then served from the browser's cache.
  useEffect(() => {
    let alive = true;
    if (modelsReady()) {
      setModels("ready");
      return;
    }
    setModels("loading");
    loadModels((p) => alive && setProgress(p)).then(
      () => alive && setModels("ready"),
      (e: unknown) => {
        console.error("Face models", e);
        if (alive) setModels("failed");
      },
    );
    return () => {
      alive = false;
    };
  }, [attempt]);

  // Sampling loop: about 4 frames per second; never two at once.
  useEffect(() => {
    if (camera !== "on" || models !== "ready" || finished || failed) return;
    let alive = true;
    let timer = 0;
    const canvas = document.createElement("canvas");
    const ctx = canvas.getContext("2d", { willReadFrequently: true });
    const samples: Float32Array[] = [];
    const reset = (h: Hint) => {
      samples.length = 0;
      setCount(0);
      setHint(h);
    };

    const sample = async () => {
      const video = videoRef.current;
      if (!ctx || !video || video.readyState < 2 || !video.videoWidth) return; // no frame yet
      const scale = Math.min(1, MAX_FRAME / Math.max(video.videoWidth, video.videoHeight));
      const w = Math.round(video.videoWidth * scale), h = Math.round(video.videoHeight * scale);
      if (canvas.width !== w || canvas.height !== h) {
        canvas.width = w;
        canvas.height = h;
      }
      ctx.drawImage(video, 0, 0, w, h); // not mirrored: the mirror is only for the on-screen preview
      const { data } = ctx.getImageData(0, 0, w, h);
      const faces = (await detect(data, w, h)).filter((f) => f.score >= MIN_SCORE);
      if (!alive) return;
      if (faces.length === 0) return reset(brightness(data, w, h) < DARK ? "More light" : "Look at the camera");
      if (faces.length > 1) return reset("Only one person in front of the camera");
      const face = faces[0];
      if (Math.sqrt(face.box.width * face.box.height) < MIN_FACE * Math.min(w, h)) return reset("Move closer");
      const embedding = await embed(align(data, w, h, face.landmarks));
      if (!alive) return;
      if (samples.length && cosine(embedding, samples[0]) < AGREE) samples.length = 0; // disagrees: start over from here
      samples.push(embedding);
      setCount(samples.length);
      if (samples.length >= NEEDED) {
        alive = false;
        stopCamera();
        setFinished(true);
        onDoneRef.current(samples.map((s) => Array.from(s)));
        return;
      }
      setHint(purpose === "enroll" ? "Turn your head slightly" : "Hold still");
    };

    const tick = async () => {
      const started = performance.now();
      try {
        await sample();
      } catch (e) {
        console.error("Face check", e);
        if (alive) {
          alive = false;
          setFailed(true);
        }
        return;
      }
      if (alive) timer = window.setTimeout(tick, Math.max(0, INTERVAL_MS - (performance.now() - started)));
    };
    timer = window.setTimeout(tick, 0);
    return () => {
      alive = false;
      window.clearTimeout(timer);
    };
  }, [camera, models, finished, failed, purpose, stopCamera]);

  const retry = () => {
    setFailed(false);
    setFinished(false);
    setCount(0);
    setHint("Put your face inside the oval");
    setCamera("starting");
    setAttempt((a) => a + 1);
  };

  const pickCamera = (id: string) => {
    saveCamera(id);
    setCount(0);
    setHint("Put your face inside the oval");
    setCamera("starting");
    setCameraId(id);
  };

  const cancel = () => {
    stopCamera();
    props.onCancel();
  };

  const problem = failed ? PROBLEMS.error
    : camera !== "starting" && camera !== "on" ? PROBLEMS[camera]
    : models === "failed" ? PROBLEMS.models
    : null;
  const cancelLabel = purpose === "login" ? t("Use username and password instead") : t("Cancel");
  const pct = progress && progress.total ? Math.floor((100 * progress.loaded) / progress.total) : 0;
  const tone = count > 0 && GOOD_HINTS.includes(hint) ? "ok" : hint !== "Put your face inside the oval" ? "warn" : "";

  return (
    <div className="face-cam">
      {problem && (
        <div className="face-cam-problem" role="alert">
          {camera === "denied" || camera === "missing" || camera === "unavailable" ? <CameraOff aria-hidden /> : <TriangleAlert aria-hidden />}
          <h3>{t(problem.title)}</h3>
          <p>{t(problem.text)}</p>
        </div>
      )}

      <div className="face-cam-stage" hidden={!!problem}>
        <video ref={videoRef} className="face-cam-video" playsInline muted autoPlay aria-hidden="true" />
        <div className={`face-cam-oval ${tone}`} aria-hidden="true" />
        {finished ? (
          <div className="face-cam-status">
            <CircleCheck aria-hidden />
            <b>{t("Face captured")}</b>
          </div>
        ) : models === "loading" ? (
          <div className="face-cam-status" role="status">
            <LoaderCircle className="face-spin" aria-hidden />
            <b>{t("Preparing face recognition… {pct}%", { pct })}</b>
            <div className="face-cam-bar" aria-hidden="true"><span style={{ width: `${pct}%` }} /></div>
            <span className="face-cam-small">{t("The first time this downloads about 40 MB (Wi-Fi is best). After that it starts quickly.")}</span>
          </div>
        ) : camera === "starting" ? (
          <div className="face-cam-status" role="status">
            <LoaderCircle className="face-spin" aria-hidden />
            <b>{t("Starting the camera…")}</b>
          </div>
        ) : null}
      </div>

      {!problem && !finished && (
        <>
          <div className="face-cam-dots" role="progressbar" aria-label={t("Face samples")} aria-valuemin={0} aria-valuemax={NEEDED} aria-valuenow={count}>
            {Array.from({ length: NEEDED }, (_, i) => <span key={i} className={i < count ? "on" : ""} />)}
          </div>
          <p className="face-cam-hint" aria-live="polite">{t(hint)}</p>
          <p className="face-cam-privacy"><ShieldCheck aria-hidden />{t("Your picture never leaves this phone. Only numbers calculated from your face are sent.")}</p>
        </>
      )}

      {cameras.length > 1 && !finished && (
        <label className="face-cam-pick">
          <Camera aria-hidden />
          <span>{t("Camera")}</span>
          <select value={activeId || cameraId} onChange={(e) => pickCamera(e.target.value)}>
            {cameras.map((c, i) => <option key={c.id} value={c.id}>{c.label || t("Camera {n}", { n: i + 1 })}</option>)}
          </select>
        </label>
      )}

      <div className="face-cam-actions">
        {problem && (
          <button type="button" className="btn btn-primary btn-big" onClick={retry}>
            <RefreshCw aria-hidden />{t("Try again")}
          </button>
        )}
        {!finished && (
          <button type="button" className="btn btn-big" onClick={cancel}>
            {purpose === "login" ? <KeyRound aria-hidden /> : <X aria-hidden />}{cancelLabel}
          </button>
        )}
      </div>
    </div>
  );
}
