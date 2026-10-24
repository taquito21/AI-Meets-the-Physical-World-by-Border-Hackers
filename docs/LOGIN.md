# Sign-in: workers and supervisors

The app opens on a sign-in screen with two options:
- **Trabajador / Worker:** does inspections.
- **Jefe / Supervisor:** reviews and approves inspections, and adds workers.

Each person signs in with **username + password** or with **their face**. Every action (photo, result, problem,
review) is recorded under the signed-in person's name. The server sets that name from the session and ignores any
name the browser sends.

## Reused from the HK Vision login (Mechatronics AI project)
- **Passwords:** stored only as PBKDF2-HMAC-SHA256 hashes (200 000 iterations, random salt per user) and compared in
  constant time. An unknown username takes as long as a wrong password, so nobody can probe which accounts exist.
- **Lockout:** 5 failed password attempts lock that username for 30 s. 8 failed face attempts lock that device for 60 s.
- **Faces:**
  - Same models: YuNet (detection, MIT) and SFace (128-number embedding, Apache-2.0), from the OpenCV Zoo.
  - Same match rule: cosine similarity ≥ 0.40 (slightly stricter than OpenCV's 0.363).
  - Same multi-frame check: every one of 5 consecutive frames must match the same account.

What changed for the web: detection and the embedding run **in the phone's browser** (onnxruntime-web,
`web/src/face/`), and only the 128 numbers are sent. **No face image leaves the device.** The server only compares
vectors (`backend/app/auth.py`). OpenCV on the server would not fit within Vercel's function size limit.

## Face data and consent
- A person registers their own face in **My account**, after signing in with their password and ticking a consent
  box. The box explains that only 128 numbers are stored (never a photo), what they are used for, and that they can
  be deleted at any time ("Delete my face data").
- A face that is already registered to another account cannot be registered again.
- A worker's face cannot open the supervisor sign-in (403), and the reverse is also blocked.
- **Limitation:** like the original, there is no liveness check, so a printed photo might pass. Password sign-in
  always remains available. Use face sign-in for convenience, not as the only control for sensitive actions.
- Face vectors are biometric data. They are never committed, never logged, and never returned by the API.

## Roles enforced by the server
| Action | Worker | Supervisor |
|---|---|---|
| Inspect, take photos, decide results, report problems | ✓ | ✓ |
| Review (approve, ask for changes, reject) | | ✓ |
| Add worker accounts, see the worker list | | ✓ |
| Load engineering packages (Import Studio) | | ✓ |
The existing rules still apply: the reviewer must be a different person from the inspector, and a problem's fix must
be verified by someone other than the person who did it.

## Demo accounts
- `jefe` (supervisor) and `trabajador` (worker) are created at startup from `backend/app/demo_users.json`, which holds
  **only usernames and PBKDF2 hashes**.
- The passwords are in **`backend/.env.demo-accounts`**, on the laptop that generated them. That file is excluded from
  git and from Vercel uploads. Share them only in person or privately.
- To rotate them, run `backend/.venv/Scripts/python tools/make_demo_accounts.py` and then reset the local data. To add
  more people, use My account → Add a worker.

## Sessions
- **Cookie:** a signed `HttpOnly`, `SameSite=Lax` cookie (`Secure` over HTTPS) that expires after 12 h (`SESSION_HOURS`).
  It is stateless, so it works across serverless instances.
- **Signing key:**
  - `AUTH_SECRET` if set; otherwise derived from `ACCESS_PASSWORD` on the hosted deployment.
  - Otherwise a random key in the local data folder.
  - Setting `AUTH_SECRET` in Vercel is recommended. Changing it signs everyone out.
- `AUTH_REQUIRED=false` turns enforcement off; only the automated workflow tests use it.

## Current storage and what moves to Supabase (for Xavier)
Accounts currently live in the `users` table of the app database (SQLite). On the test deployment that database is
temporary, per instance:
- The demo accounts always work, because they are re-created from the hashes.
- Workers added there and faces registered there may disappear when the server restarts.

That is why the login should move to Xavier's Supabase database. Everything storage-related sits in the "store"
section of `backend/app/auth.py` (`get_user`, `list_users`, `create_user`, `seed_demo_users`, and the queries in
`face_login` / `register_face` / `delete_face`). Suggested mapping:
- **Users and passwords:** either a `users` table in Postgres with the same columns, or Supabase Auth.
  - With Supabase Auth, `password_login` calls Supabase, and the role lives in `app_metadata.role` or a `profiles` table.
  - Our session cookie can stay as it is, or be replaced by Supabase's JWT (verified with `SUPABASE_JWKS_URL`).
- **Faces:** a table `face_embeddings(user_id, vector float4[128] or jsonb, consent_at, created_at)` with RLS on, and
  no policy for the anon or authenticated roles, so only the server (secret key) can read it.
- **Lockout counters** are in memory per instance today. With several instances, a small table, or Supabase Auth's
  own rate limits, makes them global.

## Tests
`backend/tests/test_auth.py` uses synthetic vectors, never real face data. It covers:
- sign-in required, forged cookies, wrong password, unknown user and lockout;
- role checks (sign-in door, reviews, worker management, package loading);
- actions recorded under the session name;
- face registration with consent, face sign-in, mixed frames refused, duplicate faces refused and deletion;
- demo accounts holding hashes only.
