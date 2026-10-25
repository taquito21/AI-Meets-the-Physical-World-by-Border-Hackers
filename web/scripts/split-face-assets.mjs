// Runs before every build (npm "prebuild"). Splits the face models and the onnxruntime wasm into ~3.5 MB pieces in
// public/face-assets/, plus a manifest with each file's size and SHA-256.
// Why: on Vercel every file is served by the Python function, and a function response is capped at 4.5 MB; the
// SFace model is 39 MB and the wasm 14 MB. The browser downloads the pieces, joins them and checks the hash.
import { createHash } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const web = join(dirname(fileURLToPath(import.meta.url)), "..");
const out = join(web, "public", "face-assets");
const PART = 3_500_000;

const wasm = join(dirname(createRequire(import.meta.url).resolve("onnxruntime-web")), "ort-wasm-simd-threaded.wasm");
const sources = {
  yunet: join(web, "face-models", "face_detection_yunet_2023mar.onnx"),
  sface: join(web, "face-models", "face_recognition_sface_2021dec.onnx"),
  wasm,
};

rmSync(out, { recursive: true, force: true });
mkdirSync(out, { recursive: true });
const files = {};
const versionHash = createHash("sha256");
for (const [name, path] of Object.entries(sources)) {
  if (!existsSync(path)) throw new Error(`Missing face asset: ${path}`);
  const bytes = readFileSync(path);
  const sha256 = createHash("sha256").update(bytes).digest("hex");
  versionHash.update(sha256);
  const parts = [];
  for (let i = 0, n = 0; i < bytes.length; i += PART, n++) {
    const file = `${name}.part${String(n).padStart(2, "0")}.bin`;
    writeFileSync(join(out, file), bytes.subarray(i, i + PART));
    parts.push(file);
  }
  files[name] = { size: bytes.length, sha256, parts };
}
writeFileSync(join(out, "manifest.json"), JSON.stringify({ version: versionHash.digest("hex").slice(0, 16), files }, null, 1));
writeFileSync(join(out, "LICENSE.txt"), readFileSync(join(web, "face-models", "LICENSE.txt")));
console.log(`face assets: ${Object.entries(files).map(([k, f]) => `${k} ${(f.size / 1e6).toFixed(1)} MB in ${f.parts.length} parts`).join(", ")}`);
