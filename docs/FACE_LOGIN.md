# Face login

An optional second way to sign in to an existing Supabase account. The password always keeps working.

## How a person uses it
1. Sign in with email and password, as usual.
2. Open **My face** (top bar), tick the consent box, and look at the camera. Five samples are taken.
3. Next time, on the login screen, tap **Sign in with my face**.

**My face** can delete the face data at any time.

## How it works
- **In the browser** (`web/src/face`): YuNet finds the face and SFace turns it into 128 numbers, with onnxruntime-web.
  - These are the same models and rules as the HK Vision login (Mechatronics AI project).
  - The result matches OpenCV 5 (cosine ≥ 0.9999996 on public-domain test images).
  - **No image ever leaves the device**; only the 128-number vectors are sent.
- **On the server** (`backend/app/face.py`):
  - The vectors are stored in `face_embeddings`, only with consent. A face already registered to another account
    is refused.
  - Login needs 5 frames that all match the same account, with cosine ≥ 0.40 (`FACE_THRESHOLD`).
  - 8 failures lock that device out for 60 s.
- **The session:** after a match, the server asks Supabase Auth for a one-time login link for that user, through the
  admin API with the secret key. It redeems the link at once, so no email is sent, and returns an ordinary Supabase
  session. The browser adopts it with `supabase.auth.setSession`. From then on everything works as after a
  password login.
- **Limitation:** there is no liveness check, so a printed photo might pass. Use the password for anything sensitive.

## One-time setup in Supabase
Run the new part of `backend/supabase/schema.sql` (the whole file is safe to re-run): the `face_embeddings` table
and its row-level security line. Until then, the app works normally, **My face** answers that face login is not set
up, and the login button cannot recognize anyone.

## Why the model files are split
On Vercel every file goes through the Python function, whose responses are capped at 4.5 MB. The SFace model is
39 MB and the onnxruntime wasm is 14 MB. So:
- `npm run build` first runs `web/scripts/split-face-assets.mjs`. It splits `web/face-models/*.onnx` and the wasm
  into pieces of 3.5 MB or less in `public/face-assets/` (generated, not committed), with a manifest that holds each
  file's SHA-256.
- After the build, `scripts/drop-unused-wasm.mjs` removes the 14 MB wasm copy that Vite still emits and the app
  never requests.
- The browser downloads the pieces once (about 53 MB), joins them, checks the hash, and keeps them in Cache Storage.
- Camera access needs HTTPS. `localhost` also works.
- Virtual cameras (DroidCam, OBS, Iriun, Camo…) are often a laptop's default and only show a "start the app"
  picture. The face camera skips them when a real camera exists. With more than one camera it shows a **Camera**
  list, and the choice is remembered on that device.

## Tests
`backend/tests/test_face.py` uses synthetic vectors and a fake Supabase Auth server. It never contacts the real
project. It covers:
- consent;
- one person per registration;
- duplicate faces;
- matching, strangers and mixed frames;
- lockout;
- the one-time-link exchange, which sends no email;
- the refusal without Supabase.
