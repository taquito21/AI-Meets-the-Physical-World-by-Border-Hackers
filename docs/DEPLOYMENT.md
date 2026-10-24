# Deployment on Vercel (test environment)

- URL: https://field-execution-platform.vercel.app (Vercel project `machinno-x/field-execution-platform`)
- Access: the browser asks for a username and password. **Any username**; the password is in `backend/.env.vercel`
  (local file, excluded from git and from the deploy). Share it only with the team.
- Storage: **temporary** (`/tmp` on each function instance). Data may reset at any time; the app shows a banner.
  Persistence is pending: see `docs/DATABASE_HANDOFF.md`.

## How it is configured
- `pyproject.toml`: dependencies and `tool.vercel.entrypoint = "backend.app.main:app"` (Python 3.12).
- `vercel.json`: `maxDuration` 60 s (AI calls take ~6–9 s).
- `.vercelignore`: excludes `**/.env*`, local data, venv, node_modules, tests, docs and tools. The web client is uploaded **already built** (`web/dist`).
- Environment variables (Production, encrypted): `ANTHROPIC_API_KEY`, `ACCESS_PASSWORD`.
- Photos are compressed on the device (≤1568 px JPEG) before upload because of Vercel's 4.5 MB per-request limit.

## Redeploy
```bash
cd web && npm run build && cd ..
vercel deploy --prod --scope machinno-x
```

## Change the password
```bash
vercel env rm ACCESS_PASSWORD production --scope machinno-x
vercel env add ACCESS_PASSWORD production --sensitive --scope machinno-x
vercel deploy --prod --scope machinno-x
```
Update `backend/.env.vercel` too, so the local copy stays in sync.

## Limitations of this deployment
- Temporary data that is not shared between instances (fixed once the database from DATABASE_HANDOFF.md is done).
- No user accounts: one shared password. The name typed on the home screen is recorded on every action.
- The local laptop server (`uvicorn`) is still the most reliable option for the live pitch on the venue network.

## AI time budget
On Vercel the AI timeout is 40 s with no automatic retry, so that a call never outlives the function's 60 s `maxDuration`.
Override with `AI_TIMEOUT_S` / `AI_MAX_RETRIES` if `maxDuration` changes.
