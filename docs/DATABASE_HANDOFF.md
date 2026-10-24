# Persistent storage: handoff guide (for Xavier)

> **This is only a recommendation.** Xavier, choose whatever you think works best: the database, the provider, how
> to store the photos, or a completely different approach. This guide just describes how the code is organized
> today and what I would do, so you don't have to work it all out from scratch.

## Current state
- Locally: SQLite in `backend/data/field_platform.db` + photos in `backend/data/evidence/`. This is persistent.
- On Vercel (`storage: "ephemeral"`): the same SQLite in `/tmp/field-platform`. **It is temporary**: each function instance has its own
  copy and it is wiped on a cold start. The app shows a banner warning about this. Engineering packages (3D, components, profiles) are
  reloaded automatically on every start, so only operational data is lost (inspections, photos, findings).

## Goal
Persistent data shared across instances, ideally Postgres (Neon or Supabase, available from the Vercel Marketplace),
plus storage for photos. Since the original plan was Supabase, the schema already mirrors that model.

## What to touch (and nothing else)

### 1. Data layer: `backend/app/db.py` (the only file that opens connections)
- `_connect`, `tx()`, `read()`: switch to `psycopg` (v3) using `DATABASE_URL`. Keep the same API: `tx()` = serialized
  read/write transaction (`BEGIN IMMEDIATE` → in Postgres a normal transaction is enough), `read()` = read-only.
- `row()`/`rows()`: today they convert `sqlite3.Row` and decode the JSON columns listed in `JSON_COLUMNS`. With `psycopg` +
  `dict_row`, and `jsonb` columns, decoding becomes automatic (keep the conversion of `BOOL_COLUMNS`).
- `SCHEMA`: TEXT JSON → `jsonb`; `INTEGER` booleans → `boolean`; timestamps can stay as ISO `text` (or move to `timestamptz`).
- `MIGRATIONS` + `PRAGMA table_info` → `ALTER TABLE ... ADD COLUMN IF NOT EXISTS ...`.
- Placeholders: the code uses `?`. Either translate `?` → `%s` inside a small `execute()` wrapper in db.py, or replace them in bulk.

### 2. SQLite-specific SQL (exact locations)
| File:line (approx.) | SQLite | Postgres |
|---|---|---|
| `catalog.py:56`, `catalog.py:95` | `INSERT OR IGNORE` | `INSERT ... ON CONFLICT DO NOTHING` |
| `main.py:193`, `main.py:267` | `json_extract(metadata,'$.inspection_id')` | `metadata->>'inspection_id'` |
| `main.py:293-308` | `json_extract(p.manifest, '$.industry')` | `p.manifest->>'industry'` |
| `workflow.py:70`, `workflow.py:81` | `ORDER BY created_at DESC, rowid DESC` | `ORDER BY created_at DESC, id DESC` (or add `bigserial seq`) |
| `db.py:118-119, 136, 147` | `PRAGMA`, `BEGIN IMMEDIATE` | remove / `ADD COLUMN IF NOT EXISTS` |
| `catalog.py`, `workflow.py`, `main.py` | `INSERT INTO t VALUES (?,?,...)` positional | they work if the column order is preserved; better to name the columns |

`ON CONFLICT(id) DO UPDATE` (catalog.py) and `COALESCE` already work in Postgres.

### 3. Photos
Today: `_store()` writes to `settings.evidence_dir`, and `evidence_file()` reads it back (`main.py` ~420 and ~574); there are also 3
inserts with `storage_path`. Simple options:
- **A (easiest):** an `evidence_blobs(id, data bytea)` table, with `_store()` inserting and `evidence_file()` returning `Response(data)`.
  Images are ≤ ~300 KB (compressed on the phone and normalized to 1568 px), which is fine at demo scale.
- **B (production):** Vercel Blob or Supabase Storage. Save the URL/key in `storage_path` and serve or redirect from `evidence_file()`.

### 4. Configuration
- New variable `DATABASE_URL` (Vercel adds it automatically when you connect Neon/Supabase to the project).
- In `config.py`: when `DATABASE_URL` is set, `storage_mode = "persistent"` (that removes the banner).
- Add `psycopg[binary]` to `pyproject.toml` (Vercel) and `backend/requirements.txt` (local).

## How to know it works
- `backend/.venv/Scripts/python -m pytest -q backend/tests` must pass (all tests; 31 at the time of writing). The tests create a clean database per module.
  Using a Postgres test database or SQLite locally both work, as long as `db.py` supports both.
- In production: start an inspection on the phone, open it from another device or browser, and redeploy. It should still be there.

## Don't change
`workflow.py` (rules), the endpoints, or the package format. The engine shouldn't care which database is underneath.
