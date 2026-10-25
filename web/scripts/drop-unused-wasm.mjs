// Runs after every build (npm "postbuild"). Vite still copies onnxruntime's 14 MB wasm into dist/assets because the
// library references it, but the app never requests it: the face engine loads the same wasm from
// face-assets/ in pieces (see split-face-assets.mjs). Removing it keeps every deployed file under 4.5 MB.
import { readdirSync, rmSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const assets = join(dirname(fileURLToPath(import.meta.url)), "..", "dist", "assets");
for (const f of readdirSync(assets)) {
  if (/^ort-wasm-.*\.wasm$/.test(f)) {
    rmSync(join(assets, f));
    console.log(`removed unused ${f}`);
  }
}
