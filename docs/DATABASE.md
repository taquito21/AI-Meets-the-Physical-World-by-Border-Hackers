# Data, storage and login (Supabase)

Data lives in **Supabase Postgres**, files in a private **Supabase Storage** bucket (`files`), and logins in
**Supabase Auth**. The backend reaches all of them over HTTPS (REST API + the server-side secret key). There is
no direct Postgres connection, so it also works on networks that only allow port 443 (the venue Wi-Fi blocks
5432/6543).

| Setting (`backend/.env`, Vercel env) | Purpose |
|---|---|
| `SUPABASE_URL`, `SUPABASE_SECRET_KEY` | Data, storage, token verification. The secret key is server side only. |
| `SUPABASE_PUBLISHABLE_KEY` | Public; handed to the browser (via `/api/config`) for login. |
| `VOYAGE_API_KEY` | Document search embeddings (MongoDB Atlas → AI Model APIs). |
| `ANTHROPIC_API_KEY` | Photo review and document answers. |
| `STORAGE_BUCKET` | Default `files`. |

## First-time setup (once per Supabase project)
1. SQL Editor → paste `backend/supabase/schema.sql` → Run (safe to re-run). It creates the 8 tables, the
   `match_document_chunks` search function, the private `files` bucket, and enables row-level security with no
   policies (the publishable key can read or write nothing).
2. Authentication → Sign In / Providers → Email: turn **Confirm email** off.
3. `cp backend/seed.example.json backend/seed.json`, edit it (gitignored: it holds passwords), then
   `backend/.venv/bin/python tools/seed_accounts.py` creates companies, logins and profiles together.
4. `backend/.venv/bin/python tools/load_demo_media.py` uploads the demo 3D models to their companies.
5. `backend/.venv/bin/python tools/smoke_test_supabase.py` checks everything end to end with a throwaway company
   and cleans up after itself.

## How the code is organized
- `backend/app/db.py`: the only data-access module. A small interface (`select`, `first`, `count`, `insert`,
  `upsert`, `update`, `delete`, `rpc`) with two backends: `RestStore` (PostgREST over HTTPS) and `SqliteStore`
  (local, used by the tests). Filters are equality, `None` (is null) and lists (IN). Joins happen in Python.
- `backend/app/blobs.py`: file storage (`put`, `get`, `delete`, `signed_urls`) on Supabase Storage or local disk.
- `backend/supabase/schema.sql` (Postgres) and `SCHEMA` in `db.py` (SQLite) must be kept in sync.

## No multi-statement transactions
Each REST call is its own transaction. The code validates before the first write, writes parents before children,
and undoes a half-created job or upload if a later write fails. Deletes rely on `on delete cascade`.

## Adding people later
Add them to `backend/seed.json` and re-run `tools/seed_accounts.py`; existing accounts are left untouched.

## Resetting data (development)
`backend/.venv/bin/python tools/reset_demo_data.py --yes` deletes all jobs, tasks, evidence and media (and their
files); companies and logins are kept. Reload the demo models with `tools/load_demo_media.py`.

## Tests
`backend/.venv/bin/python -m pytest -q backend/tests` runs on a temporary SQLite database with AI and embeddings
stubbed; it never touches Supabase or paid APIs.

## Switching to a direct Postgres connection later
Add a third store class in `db.py` (e.g. `psycopg`) with the same interface and select it with `DATA_BACKEND`.
