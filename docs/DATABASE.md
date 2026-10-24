# Persistent storage (Supabase)

Data lives in **Supabase Postgres**, and evidence photos live in a private **Supabase Storage** bucket. The backend
reaches both over HTTPS through the Supabase REST API, using the server-side secret key. There is no direct Postgres
connection, so it also works on networks that only allow port 443 (the venue Wi-Fi blocks 5432/6543).

Without Supabase keys, the same code runs on **local SQLite + files** in `backend/data` (tests, offline work).

| Setting (`backend/.env`, Vercel env) | Purpose |
|---|---|
| `SUPABASE_URL`, `SUPABASE_SECRET_KEY` | Turn on the Supabase backend. The secret key is server side only. |
| `STORAGE_BUCKET` | Photo bucket (default `evidence`). |
| `DATA_BACKEND=local` | Force local storage even when the keys are set. |

## First-time setup (once per Supabase project)
1. Supabase dashboard → **SQL Editor** → New query → paste `backend/supabase/schema.sql` → **Run**. It is safe to re-run.
   It creates the tables, indexes, the private `evidence` bucket, and enables row-level security with no policies,
   so the publishable (browser) key cannot read or write any table.
2. Start the server. It imports the engineering packages and seeds the demo units on first start.

## How the code is organized
- `backend/app/db.py`: the only data-access module. A small interface (`select`, `first`, `count`, `insert`,
  `upsert`, `update`, `delete`) with two backends: `RestStore` (PostgREST over HTTPS) and `SqliteStore`.
  Filters are equality, `None` (is null) and lists (IN). Joins happen in Python.
- `backend/app/blobs.py`: photo storage (`put`, `get`, `delete`) on Supabase Storage or local disk. Photos are always
  served through `/api/evidence/{id}/file`, never through a public bucket URL.
- `backend/supabase/schema.sql` (Postgres) and `SCHEMA` in `db.py` (SQLite) must be kept in sync.

## No multi-statement transactions
Each REST call is its own transaction. The workflow stays safe this way:
- Every state change is a **conditional update** on the status that was read (`where status = <what we read>`). If
  someone changed the record in between, the request fails with 409 instead of overwriting their change.
- A **partial unique index** allows only one open inspection per unit, so concurrent starts cannot create two.
- Validation runs before the first write. Multi-row inserts (inspection items, components) are a single request.
- Package import is idempotent and **self-repairing**: if an import was interrupted, the next start completes it.
- Remaining gap: if a request fails between two writes (e.g. after the status change, before the activity event),
  the state change is kept without its follow-up rows. It is rare, and acceptable for the MVP. Wrap a critical
  sequence in a Postgres function (called through `/rpc`) if it ever needs to be atomic.

## Switching to a direct Postgres connection later
Add a third store class in `db.py` (e.g. `psycopg`) that implements the same interface, and select it with
`DATA_BACKEND`. Nothing outside `db.py` changes. A direct connection needs a network that allows port 5432/6543.

## Resetting data (development)
Revisions are immutable once loaded. To reload an edited revision, wipe the data:
`backend/.venv/bin/python tools/reset_demo_data.py --yes` (Supabase: deletes every row and photo, then restart the
server; local: deletes `backend/data`, stop the server first).

## Tests
`pytest backend/tests` always runs on a temporary SQLite database. `TEST_DATA_BACKEND=supabase pytest backend/tests`
runs the same suite against the Supabase project in `backend/.env` and **wipes all its data** before each module.
Use it only with a development project.
