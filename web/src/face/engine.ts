// Face login on the device: YuNet finds the face, SFace turns it into 128 numbers (the "embedding").
// This reproduces OpenCV's cv::FaceDetectorYN + cv::FaceRecognizerSF, which the original desktop app used, with
// onnxruntime-web. Checked in Node against OpenCV 5.0 on the same pixels: embeddings agree to cosine ≥ 0.9999996 and
// landmarks to within 0.0001 px. Only embeddings leave this module; frames and face crops stay in memory on the device.
//
// The math has no React and no DOM, so it also runs in Node (tests feed raw RGBA pixels through initEngine).
//
// What OpenCV does, and what is copied here:
//  - Detector input: the frame at the size given to setInputSize, BGR channel order, 0–255 floats, no mean and no
//    scaling (blobFromImage defaults), zero-padded on the right and bottom up to a multiple of 32. OpenCV itself
//    neither resizes nor letterboxes; the app picks the size (the desktop app shrank frames to 320 px wide).
//    Here frames larger than `maxSide` (640 by default) are shrunk to fit first, bit-exactly like cv2.resize
//    INTER_LINEAR. The YuNet file declares a fixed 1×3×640×640 input, which onnxruntime would enforce, so the two
//    640s in that declaration are rewritten in memory as free dimensions (the network is fully convolutional,
//    which is how OpenCV runs it at any size); if that ever fails, the frame is zero-padded to 640×640 instead.
//    Results are mapped back to the input's pixels (pixel-centre aligned).
//  - Decoding: one prior per cell at strides 8/16/32, score = sqrt(clamp(cls)·clamp(obj)), centre = (cell + d)·stride,
//    size = exp(d)·stride, landmarks = (cell + d)·stride; then cv::dnn::NMSBoxes on integer-truncated boxes
//    (score 0.8, IoU 0.3, top 50 candidates), only when there is more than one face.
//  - Alignment: similarity transform (Umeyama, rotation + uniform scale) from the 5 landmarks to the ArcFace
//    112×112 template, then warpAffine with bilinear sampling and black outside the frame.
//  - Recognizer input: blobFromImage(crop, 1, 112×112, mean 0, swapRB = true): RGB, 0–255 floats. The SFace model
//    itself subtracts 127.5 and multiplies by 1/128 (its first two nodes), so nothing else is done here.
import type { InferenceSession } from "onnxruntime-web";

type Ort = typeof import("onnxruntime-web");

/** RGBA pixels, row by row, 4 bytes per pixel (what canvas getImageData returns). */
export type Pixels = Uint8ClampedArray | Uint8Array;
export type Point = [number, number];

export interface Face {
  /** Detector confidence, 0–1. */
  score: number;
  /** Face box in the input's pixel coordinates. */
  box: { x: number; y: number; width: number; height: number };
  /** Right eye, left eye, nose tip, right mouth corner, left mouth corner (the person's right is the image's left). */
  landmarks: Point[];
}

export interface LoadProgress {
  loaded: number;
  total: number;
}

export const DET_SIZE = 640;
export const SCORE_THRESHOLD = 0.8;
export const NMS_THRESHOLD = 0.3;
export const TOP_K = 50;
export const CROP_SIZE = 112;
export const EMBEDDING_SIZE = 128;
/** Same-person threshold used for matching (as in the original app; OpenCV suggests 0.363 for SFace). */
export const MATCH_THRESHOLD = 0.4;

export const YUNET_FILE = "face_detection_yunet_2023mar.onnx";
export const SFACE_FILE = "face_recognition_sface_2021dec.onnx";

const STRIDES = [8, 16, 32] as const;
// ArcFace 5-point template for a 112×112 crop, and its mean exactly as hard-coded in OpenCV.
const TEMPLATE: readonly Point[] = [
  [38.2946, 51.6963],
  [73.5318, 51.5014],
  [56.0252, 71.7366],
  [41.5493, 92.3655],
  [70.7299, 92.2041],
];
const TEMPLATE_MEAN: Point = [56.0262, 71.9008];

// --------------------------------------------------------------------------- detection math

/** Size of the image the detector sees: the input shrunk (never enlarged) to fit side × side. */
export function fitSize(width: number, height: number, side = DET_SIZE): [number, number] {
  const s = Math.min(1, side / width, side / height);
  return [Math.min(side, Math.max(1, Math.round(width * s))), Math.min(side, Math.max(1, Math.round(height * s)))];
}

/** Round half to even, like cvRound. */
function rint(x: number): number {
  const f = Math.floor(x), d = x - f;
  return d > 0.5 ? f + 1 : d < 0.5 ? f : f % 2 === 0 ? f : f + 1;
}

function taps(dst: number, src: number) {
  // cv2.resize INTER_LINEAR: pixel-centre aligned, edges clamped, source position in float32,
  // weights in 11-bit fixed point (INTER_RESIZE_COEF_SCALE = 2048).
  const i0 = new Int32Array(dst), i1 = new Int32Array(dst), w0 = new Int32Array(dst), w1 = new Int32Array(dst);
  const scale = src / dst;
  for (let d = 0; d < dst; d++) {
    const f = Math.fround((d + 0.5) * scale - 0.5);
    let s = Math.floor(f);
    let t = Math.fround(f - s);
    if (s < 0) (s = 0), (t = 0);
    if (s >= src - 1) (s = src - 1), (t = 0);
    i0[d] = s;
    i1[d] = Math.min(s + 1, src - 1);
    w0[d] = rint(Math.fround(1 - t) * 2048);
    w1[d] = rint(t * 2048);
  }
  return { i0, i1, w0, w1 };
}

/**
 * cv2.resize(src, (dw, dh), INTER_LINEAR) on RGBA pixels, bit-exact with OpenCV's 8-bit path (integer horizontal
 * pass, then its vectorised vertical pass); alpha is set to 255. Pure JS, so browser and Node give identical results.
 */
export function resizeBilinear(src: Pixels, width: number, height: number, dw: number, dh: number): Uint8ClampedArray {
  const xs = taps(dw, width), ys = taps(dh, height);
  const rows = new Map<number, Int32Array>();
  const row = (sy: number) => {
    let r = rows.get(sy);
    if (!r) {
      r = new Int32Array(dw * 3);
      const base = sy * width * 4;
      for (let x = 0; x < dw; x++) {
        const c0 = base + xs.i0[x] * 4, c1 = base + xs.i1[x] * 4, a0 = xs.w0[x], a1 = xs.w1[x];
        for (let k = 0; k < 3; k++) r[x * 3 + k] = src[c0 + k] * a0 + src[c1 + k] * a1;
      }
      rows.set(sy, r);
    }
    return r;
  };
  const out = new Uint8ClampedArray(dw * dh * 4);
  for (let y = 0; y < dh; y++) {
    const s0 = row(ys.i0[y]), s1 = row(ys.i1[y]), b0 = ys.w0[y], b1 = ys.w1[y];
    for (let x = 0; x < dw; x++) {
      const o = (y * dw + x) * 4;
      for (let k = 0; k < 3; k++) out[o + k] = ((((s0[x * 3 + k] >> 4) * b0) >> 16) + (((s1[x * 3 + k] >> 4) * b1) >> 16) + 2) >> 2;
      out[o + 3] = 255;
    }
    for (const k of rows.keys()) if (k < ys.i0[y]) rows.delete(k); // rows are visited in order; drop used-up ones
  }
  return out;
}

/**
 * YuNet input tensor data (1×3×padH×padW, BGR planes, 0–255, zeros on the right and bottom) and the scale applied.
 * freeSize: pad to a multiple of 32 like OpenCV; otherwise pad to the model's declared 640×640.
 */
export function detectorInput(rgba: Pixels, width: number, height: number, maxSide = DET_SIZE, freeSize = true, buffer?: Float32Array) {
  const [dw, dh] = fitSize(width, height, freeSize ? maxSide : Math.min(maxSide, DET_SIZE));
  const padW = freeSize ? Math.ceil(dw / 32) * 32 : DET_SIZE;
  const padH = freeSize ? Math.ceil(dh / 32) * 32 : DET_SIZE;
  const img = dw === width && dh === height ? rgba : resizeBilinear(rgba, width, height, dw, dh);
  const plane = padW * padH;
  const input = buffer && buffer.length === 3 * plane ? buffer : new Float32Array(3 * plane);
  input.fill(0);
  for (let y = 0; y < dh; y++) {
    for (let x = 0; x < dw; x++) {
      const i = (y * dw + x) * 4, o = y * padW + x;
      input[o] = img[i + 2];
      input[plane + o] = img[i + 1];
      input[2 * plane + o] = img[i];
    }
  }
  return { input, padW, padH, scaleX: dw / width, scaleY: dh / height };
}

// The input declaration in the YuNet file, as protobuf bytes: dims 1, 3, 640, 640 (TensorShapeProto.dim entries with
// dim_value). The replacement has the same length, so no enclosing message length changes: dim_param "h" and "w".
const FIXED_INPUT = [0x0a, 0x02, 0x08, 0x01, 0x0a, 0x02, 0x08, 0x03, 0x0a, 0x03, 0x08, 0x80, 0x05, 0x0a, 0x03, 0x08, 0x80, 0x05];
const FREE_HW = [0x0a, 0x03, 0x12, 0x01, 0x68, 0x0a, 0x03, 0x12, 0x01, 0x77];

/** Copy of the YuNet model whose input height and width are free, or null if the file is not laid out as expected. */
export function freeDetectorInputSize(model: Uint8Array): Uint8Array | null {
  const find = (from: number) => {
    outer: for (let i = from; i <= model.length - FIXED_INPUT.length; i++) {
      for (let k = 0; k < FIXED_INPUT.length; k++) if (model[i + k] !== FIXED_INPUT[k]) continue outer;
      return i;
    }
    return -1;
  };
  const at = find(0);
  if (at < 0 || find(at + 1) >= 0) return null; // missing or ambiguous: keep the original
  const out = model.slice();
  out.set(FREE_HW, at + 8);
  return out;
}

const clamp01 = (v: number) => (v < 0 ? 0 : v > 1 ? 1 : v);

/**
 * Decode YuNet's 12 output heads for a padW × padH input into faces (in detector-input pixels), then NMS.
 * `out(name)` returns a head's data.
 */
export function decodeYuNet(
  out: (name: string) => ArrayLike<number>,
  padW = DET_SIZE,
  padH = DET_SIZE,
  scoreThreshold = SCORE_THRESHOLD,
  nmsThreshold = NMS_THRESHOLD,
  topK = TOP_K,
): Face[] {
  const faces: Face[] = [];
  for (const st of STRIDES) {
    const cols = Math.floor(padW / st), rows = Math.floor(padH / st);
    const cls = out(`cls_${st}`), obj = out(`obj_${st}`), bbox = out(`bbox_${st}`), kps = out(`kps_${st}`);
    for (let r = 0; r < rows; r++) {
      for (let c = 0; c < cols; c++) {
        const i = r * cols + c;
        const score = Math.sqrt(clamp01(cls[i]) * clamp01(obj[i]));
        if (score < scoreThreshold) continue;
        const cx = (c + bbox[i * 4]) * st, cy = (r + bbox[i * 4 + 1]) * st;
        const w = Math.exp(bbox[i * 4 + 2]) * st, h = Math.exp(bbox[i * 4 + 3]) * st;
        const landmarks: Point[] = [];
        for (let n = 0; n < 5; n++) landmarks.push([(kps[i * 10 + 2 * n] + c) * st, (kps[i * 10 + 2 * n + 1] + r) * st]);
        faces.push({ score, box: { x: cx - w / 2, y: cy - h / 2, width: w, height: h }, landmarks });
      }
    }
  }
  // OpenCV skips NMS (and its stricter "score > threshold" filter) when there is a single candidate.
  return faces.length > 1 ? nms(faces, scoreThreshold, nmsThreshold, topK) : faces;
}

/** cv::dnn::NMSBoxes as FaceDetectorYN calls it: boxes truncated to integers, top-k taken before suppression. */
export function nms(faces: Face[], scoreThreshold: number, iouThreshold: number, topK: number): Face[] {
  const boxes = faces.map((f) => [Math.trunc(f.box.x), Math.trunc(f.box.y), Math.trunc(f.box.width), Math.trunc(f.box.height)]);
  const order = faces
    .map((_, i) => i)
    .filter((i) => faces[i].score > scoreThreshold)
    .sort((a, b) => faces[b].score - faces[a].score); // stable, like std::stable_sort
  if (topK > 0 && order.length > topK) order.length = topK;
  const keep: number[] = [];
  for (const i of order) if (keep.every((k) => iou(boxes[i], boxes[k]) <= iouThreshold)) keep.push(i);
  return keep.map((i) => faces[i]);
}

function iou(a: number[], b: number[]): number {
  const areas = a[2] * a[3] + b[2] * b[3];
  if (areas <= 0) return 1;
  const iw = Math.min(a[0] + a[2], b[0] + b[2]) - Math.max(a[0], b[0]);
  const ih = Math.min(a[1] + a[3], b[1] + b[3]) - Math.max(a[1], b[1]);
  const inter = iw > 0 && ih > 0 ? iw * ih : 0;
  return inter / (areas - inter);
}

function toImageCoords(f: Face, sx: number, sy: number): Face {
  if (sx === 1 && sy === 1) return f;
  const X = (x: number) => (x + 0.5) / sx - 0.5, Y = (y: number) => (y + 0.5) / sy - 0.5;
  return {
    score: f.score,
    box: { x: X(f.box.x), y: Y(f.box.y), width: f.box.width / sx, height: f.box.height / sy },
    landmarks: f.landmarks.map(([x, y]): Point => [X(x), Y(y)]),
  };
}

// --------------------------------------------------------------------------- alignment math

/**
 * 2×3 matrix [a, -b, tx, b, a, ty] mapping the 5 landmarks onto the ArcFace template: least-squares rotation +
 * uniform scale + translation. This is Umeyama's method as in OpenCV's alignCrop; for 2-D points its SVD solution
 * reduces exactly to this closed form (checked against a literal port of OpenCV's code: identical matrices).
 */
export function similarityTransform(landmarks: ReadonlyArray<readonly [number, number]>): number[] {
  if (landmarks.length !== 5) throw new Error("Expected 5 face landmarks");
  let mx = 0, my = 0;
  for (const [x, y] of landmarks) (mx += x), (my += y);
  mx /= 5;
  my /= 5;
  let dot = 0, cross = 0, norm = 0;
  for (let i = 0; i < 5; i++) {
    const sx = landmarks[i][0] - mx, sy = landmarks[i][1] - my;
    const dx = TEMPLATE[i][0] - TEMPLATE_MEAN[0], dy = TEMPLATE[i][1] - TEMPLATE_MEAN[1];
    dot += sx * dx + sy * dy;
    cross += sx * dy - sy * dx;
    norm += sx * sx + sy * sy;
  }
  if (!(norm > 0)) throw new Error("Face landmarks are degenerate");
  const a = dot / norm, b = cross / norm;
  return [a, -b, TEMPLATE_MEAN[0] - (a * mx - b * my), b, a, TEMPLATE_MEAN[1] - (b * mx + a * my)];
}

/** cv2.warpAffine(src, m, (size, size), INTER_LINEAR, BORDER_CONSTANT 0) on RGBA pixels, in plain JS (no canvas). */
export function warpAffine(src: Pixels, width: number, height: number, m: readonly number[], size = CROP_SIZE): Uint8ClampedArray {
  let det = m[0] * m[4] - m[1] * m[3];
  det = det !== 0 ? 1 / det : 0;
  const i00 = m[4] * det, i01 = -m[1] * det, i10 = -m[3] * det, i11 = m[0] * det;
  const i02 = -i00 * m[2] - i01 * m[5], i12 = -i10 * m[2] - i11 * m[5];
  const out = new Uint8ClampedArray(size * size * 4);
  const at = (x: number, y: number) => (x >= 0 && x < width && y >= 0 && y < height ? (y * width + x) * 4 : -1);
  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      const sx = i00 * x + i01 * y + i02, sy = i10 * x + i11 * y + i12;
      const x0 = Math.floor(sx), y0 = Math.floor(sy);
      const ax = sx - x0, ay = sy - y0;
      const p00 = at(x0, y0), p01 = at(x0 + 1, y0), p10 = at(x0, y0 + 1), p11 = at(x0 + 1, y0 + 1);
      const w00 = (1 - ax) * (1 - ay), w01 = ax * (1 - ay), w10 = (1 - ax) * ay, w11 = ax * ay;
      const o = (y * size + x) * 4;
      for (let k = 0; k < 3; k++) {
        out[o + k] =
          (p00 >= 0 ? src[p00 + k] * w00 : 0) +
          (p01 >= 0 ? src[p01 + k] * w01 : 0) +
          (p10 >= 0 ? src[p10 + k] * w10 : 0) +
          (p11 >= 0 ? src[p11 + k] * w11 : 0);
      }
      out[o + 3] = 255;
    }
  }
  return out;
}

/** 112×112 RGBA face crop aligned to the ArcFace template, like OpenCV's FaceRecognizerSF::alignCrop. */
export function align(rgba: Pixels, width: number, height: number, landmarks: ReadonlyArray<readonly [number, number]>): Uint8ClampedArray {
  checkSize(rgba, width, height);
  return warpAffine(rgba, width, height, similarityTransform(landmarks), CROP_SIZE);
}

/** SFace input tensor data (1×3×112×112): RGB planes, 0–255. */
export function recognizerInput(crop: Pixels): Float32Array {
  const plane = CROP_SIZE * CROP_SIZE;
  if (crop.length !== plane * 4) throw new Error(`Face crop must be ${CROP_SIZE}×${CROP_SIZE} RGBA`);
  const out = new Float32Array(3 * plane);
  for (let i = 0; i < plane; i++) {
    out[i] = crop[i * 4];
    out[plane + i] = crop[i * 4 + 1];
    out[2 * plane + i] = crop[i * 4 + 2];
  }
  return out;
}

/** Cosine similarity of two embeddings (1 = same direction). */
export function cosine(a: ArrayLike<number>, b: ArrayLike<number>): number {
  if (a.length !== b.length) throw new Error("Embeddings have different lengths");
  let dot = 0, na = 0, nb = 0;
  for (let i = 0; i < a.length; i++) {
    dot += a[i] * b[i];
    na += a[i] * a[i];
    nb += b[i] * b[i];
  }
  return na > 0 && nb > 0 ? dot / Math.sqrt(na * nb) : 0;
}

function checkSize(rgba: Pixels, width: number, height: number) {
  if (!(width > 0 && height > 0) || rgba.length !== width * height * 4) throw new Error("Pixel buffer does not match width × height × 4");
}

// --------------------------------------------------------------------------- models

interface Runtime {
  ort: Ort;
  det: InferenceSession;
  rec: InferenceSession;
  /** The detector accepts any input size (true unless the in-memory patch of the model failed). */
  freeSize: boolean;
}

let runtime: Runtime | null = null;
let loading: Promise<void> | null = null;
let lastProgress: LoadProgress | null = null;
const listeners = new Set<(p: LoadProgress) => void>();
let queue: Promise<unknown> = Promise.resolve();
let detBuffer: Float32Array | undefined;

/** Start the engine with an onnxruntime module and the two model files (used directly by Node tests). */
export async function initEngine(ort: Ort, yunetModel: Uint8Array, sfaceModel: Uint8Array): Promise<void> {
  // logSeverityLevel 3: hide SFace's harmless "initializer appears in graph inputs" warnings
  const options: InferenceSession.SessionOptions = { executionProviders: ["wasm"], graphOptimizationLevel: "all", logSeverityLevel: 3 };
  const free = freeDetectorInputSize(yunetModel);
  let det: InferenceSession | null = null;
  if (free) det = await ort.InferenceSession.create(free, options).catch(() => null);
  const freeSize = det !== null;
  det ??= await ort.InferenceSession.create(yunetModel, options);
  const rec = await ort.InferenceSession.create(sfaceModel, options);
  runtime = { ort, det, rec, freeSize };
}

export const modelsReady = (): boolean => runtime !== null;

/** Whether the detector runs at the frame's own size (OpenCV's behaviour) rather than the 640×640 fallback. */
export const detectorHasFreeSize = (): boolean => runtime?.freeSize ?? false;

/**
 * Browser: download onnxruntime-web and both models once (about 40 MB the first time, then from the browser's cache)
 * and start the engine. Safe to call many times; every caller's onProgress gets updates.
 */
export function loadModels(onProgress?: (p: LoadProgress) => void): Promise<void> {
  if (runtime) return Promise.resolve();
  if (onProgress) {
    listeners.add(onProgress);
    if (lastProgress) onProgress(lastProgress);
  }
  if (!loading) {
    loading = loadInBrowser().then(
      () => listeners.clear(),
      (e: unknown) => {
        loading = null;
        lastProgress = null;
        listeners.clear();
        throw e;
      },
    );
  }
  return loading;
}

// Bump to make browsers fetch the model files again if they are ever replaced under the same name.
const CACHE_NAME = "face-models-v1";

async function loadInBrowser(): Promise<void> {
  // Both imports are dynamic: onnxruntime-web becomes its own chunk, and the wasm file is served from this site
  // (Vite copies it into the build), never from a CDN.
  const [ort, wasmUrl] = await Promise.all([
    import("onnxruntime-web/wasm"),
    import("onnxruntime-web/ort-wasm-simd-threaded.wasm?url").then((m) => m.default),
  ]);
  ort.env.wasm.numThreads = 1; // no worker threads: works without cross-origin isolation headers
  ort.env.wasm.proxy = false;
  ort.env.logLevel = "error";

  const base = `${import.meta.env.BASE_URL}models/face/`;
  const version = ort.env.versions.web ?? ort.env.versions.common;
  const files = [
    // expected sizes only drive the progress bar until the real sizes are known
    { url: wasmUrl, key: `${wasmUrl}?ort=${version}`, size: 14_240_000 },
    { url: base + YUNET_FILE, key: base + YUNET_FILE, size: 232_589 },
    { url: base + SFACE_FILE, key: base + SFACE_FILE, size: 38_696_353 },
  ];
  const cache = await openCache();
  const got = files.map(() => 0);
  const report = () => {
    const total = files.reduce((s, f) => s + f.size, 0);
    lastProgress = { loaded: Math.min(total, got.reduce((s, n) => s + n, 0)), total };
    for (const l of listeners) l(lastProgress);
  };
  report();
  const [wasm, yunet, sface] = await Promise.all(
    files.map((f, i) =>
      fetchBytes(f.url, f.key, cache, (n, size) => {
        if (size) f.size = size;
        got[i] = n;
        report();
      }),
    ),
  );
  ort.env.wasm.wasmBinary = wasm;
  try {
    await initEngine(ort, yunet, sface);
  } catch (e) {
    // a damaged cached file would otherwise fail the same way on every retry
    if (cache) await caches.delete(CACHE_NAME).catch(() => undefined);
    throw e;
  }
}

async function openCache(): Promise<Cache | null> {
  try {
    if (typeof caches === "undefined") return null; // e.g. plain http on a LAN address
    for (const name of await caches.keys()) if (name.startsWith("face-models-") && name !== CACHE_NAME) await caches.delete(name);
    return await caches.open(CACHE_NAME);
  } catch {
    return null; // private mode or storage disabled: just download every time
  }
}

async function fetchBytes(url: string, key: string, cache: Cache | null, onBytes: (n: number, size?: number) => void): Promise<Uint8Array> {
  const keyUrl = new URL(key, location.href).href;
  let res = cache ? await cache.match(keyUrl).catch(() => undefined) : undefined;
  const fromCache = !!res;
  if (!res) {
    res = await fetch(url);
    if (!res.ok) throw new Error(`Download failed (HTTP ${res.status}): ${url}`);
  }
  const length = Number(res.headers.get("Content-Length")) || 0;
  const size = length && !res.headers.get("Content-Encoding") ? length : undefined;
  let bytes: Uint8Array;
  if (res.body) {
    const reader = res.body.getReader();
    const chunks: Uint8Array[] = [];
    let n = 0;
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      chunks.push(value);
      n += value.length;
      onBytes(n, size);
    }
    bytes = new Uint8Array(n);
    let o = 0;
    for (const c of chunks) bytes.set(c, o), (o += c.length);
  } else {
    bytes = new Uint8Array(await res.arrayBuffer());
  }
  if (size && bytes.length !== size) throw new Error(`Download incomplete: ${url}`);
  onBytes(bytes.length, bytes.length);
  if (cache && !fromCache) {
    const type = res.headers.get("Content-Type") ?? "application/octet-stream";
    await cache.put(keyUrl, new Response(bytes, { headers: { "Content-Type": type } })).catch(() => undefined);
  }
  return bytes;
}

function need(): Runtime {
  if (!runtime) throw new Error("Face models are not loaded yet");
  return runtime;
}

// onnxruntime-web runs one inference at a time per session; queue calls so overlapping requests cannot collide.
function serial<T>(fn: () => Promise<T>): Promise<T> {
  const p = queue.then(fn, fn);
  queue = p.catch(() => undefined);
  return p;
}

// --------------------------------------------------------------------------- pipeline

/**
 * Faces (score ≥ 0.8) in the input's pixel coordinates, highest score first. `maxSide` caps the detector's input
 * (default 640; 320 behaves like the desktop app and is about 4× faster, with coarser landmarks).
 */
export function detect(rgba: Pixels, width: number, height: number, maxSide = DET_SIZE): Promise<Face[]> {
  const rt = need();
  checkSize(rgba, width, height);
  return serial(async () => {
    const { input, padW, padH, scaleX, scaleY } = detectorInput(rgba, width, height, maxSide, rt.freeSize, detBuffer);
    detBuffer = input;
    const res = await rt.det.run({ input: new rt.ort.Tensor("float32", input, [1, 3, padH, padW]) });
    const faces = decodeYuNet((name) => res[name].data as Float32Array, padW, padH);
    return faces.map((f) => toImageCoords(f, scaleX, scaleY));
  });
}

/** 128-number SFace embedding of a 112×112 RGBA crop from align(). */
export function embed(crop: Pixels): Promise<Float32Array> {
  const rt = need();
  const input = recognizerInput(crop);
  return serial(async () => {
    const res = await rt.rec.run({ data: new rt.ort.Tensor("float32", input, [1, 3, CROP_SIZE, CROP_SIZE]) });
    return Float32Array.from(res.fc1.data as Float32Array);
  });
}
