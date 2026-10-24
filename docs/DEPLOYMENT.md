# Deployment on Vercel (test environment)

- URL: https://field-execution-platform.vercel.app (Vercel project `machinno-x/field-execution-platform`)
- Access: Supabase login (email + password) for the accounts created with `tools/seed_accounts.py`. The old shared
  password (`ACCESS_PASSWORD`) is no longer used and can be removed from the Vercel environment.
- Data, files and logins: **Supabase** (see `docs/DATABASE.md`). The Vercel functions keep no state.

## How it is configured
- `pyproject.toml`: dependencies and `tool.vercel.entrypoint = "backend.app.main:app"` (Python 3.12).
- `vercel.json`: `maxDuration` 60 s (AI calls take ~6–9 s).
- `.vercelignore`: excludes `**/.env*`, local data, venv, node_modules, tests, docs and tools. The web client is uploaded **already built** (`web/dist`).
- Environment variables (Production, encrypted): `SUPABASE_URL`, `SUPABASE_SECRET_KEY`, `SUPABASE_PUBLISHABLE_KEY`,
  `ANTHROPIC_API_KEY`, `VOYAGE_API_KEY`.
- Photos are compressed on the device (≤1568 px JPEG) before upload because of Vercel's 4.5 MB per-request limit.
  Media uploads (PDFs, models) go through the same limit, so files over ~4.5 MB must be uploaded from a local server.

## Redeploy
```bash
cd web && npm run build && cd ..
vercel deploy --prod --scope machinno-x
```

## Limitations of this deployment
- Uploads are limited to ~4.5 MB per request (Vercel).
- The local laptop server (`uvicorn`) is still the most reliable option for the live pitch on the venue network.

## AI time budget
On Vercel the AI timeout is 40 s with no automatic retry, so that a call never outlives the function's 60 s `maxDuration`.
Override with `AI_TIMEOUT_S` / `AI_MAX_RETRIES` if `maxDuration` changes.
