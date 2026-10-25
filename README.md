# field-execution-platform

Hackathon MVP for the **1881 International Hackathon 2026, Track 3: AI Meets the Physical World**.
Interface label: **FieldSight** (configurable via `APP_LABEL`).

Employers create **jobs** with ordered **tasks** and assign them to an employee. Employees log in, work through their
jobs, add **evidence** (photos and notes) to each task, and mark it **passed**, **failed** or **flagged** (escalated to
the employer for input). Photos get an advisory **AI review** (Claude vision). Tasks can link company **media**:
interactive, explodable **3D models** with the relevant parts highlighted, documents and images. Uploaded PDFs and
text files are **searchable**: "Ask the documents" answers questions with citations to document and page.

Data, files and logins live in **Supabase**, reached over HTTPS only. Each company only ever sees its own data.
The interface is in **Spanish by default** with an ES | EN switch; AI replies follow the chosen language
(see [docs/LANGUAGES.md](docs/LANGUAGES.md)).

## Quick start (macOS / Linux)

```bash
# backend
python3.12 -m venv backend/.venv
backend/.venv/bin/python -m pip install -r backend/requirements.txt
cp backend/.env.example backend/.env      # then fill in the Supabase, Anthropic and Voyage keys

# web client (built once, then served by the backend)
cd web && npm install && npm run build && cd ..

# run (serves API + web app on port 8000, all interfaces)
backend/.venv/bin/python -m uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8000
```

On Windows (Git Bash) use `py -3.12 -m venv backend/.venv` and `backend/.venv/Scripts/python`.

First time on a new Supabase project: follow [docs/DATABASE.md](docs/DATABASE.md) (apply the schema, seed the
accounts, load the demo models). Then open `http://localhost:8000` (or `http://<laptop-LAN-IP>:8000` on a phone on
the same Wi-Fi) and sign in. The phone camera opens through the photo button.

Without `ANTHROPIC_API_KEY` the AI review reports "unavailable"; without `VOYAGE_API_KEY` document search does. The rest
works.

Development with hot reload: run the backend as above, then `cd web && npm run dev` and open port 5173 (it proxies
`/api` to the backend).

## Useful commands

```bash
backend/.venv/bin/python -m pytest -q backend/tests        # tests (local SQLite, AI stubbed)
backend/.venv/bin/python tools/smoke_test_supabase.py      # end-to-end check against Supabase (cleans up)
backend/.venv/bin/python tools/seed_accounts.py            # create companies + logins from backend/seed.json
backend/.venv/bin/python tools/load_demo_media.py          # upload the demo 3D models to their companies
backend/.venv/bin/python tools/reset_demo_data.py --yes    # delete all jobs and media (keeps logins)
backend/.venv/bin/python tools/build_package.py engineering-packages/chair-model-001   # rebuild a demo GLB
```

## Layout

```
backend/app/          FastAPI: main.py (REST), auth.py (login), workflow.py (rules), media.py, rag.py (search),
                      ai.py (Claude), db.py + blobs.py (Supabase / local), packages.py (demo package reader)
backend/supabase/     schema.sql: the Postgres schema, applied once in the Supabase SQL editor
backend/tests/        API tests
web/src/              React + React Three Fiber client; components/AssemblyViewer.tsx is the 3D viewer
engineering-packages/ source of the demo 3D models (fire extinguisher, chairs, table, electrical panel)
tools/                seeding, demo media loader, smoke test, reset, GLB builder
docs/                 architecture, database, API, deployment, limitations
```

Docs describing the previous inspection prototype (kept for reference, no longer match the app):
DEMO.md, MULTI_INDUSTRY.md, FIRE_EXTINGUISHER.md, REAL_CHAIR.md, MODEL_REPLACEMENT.md, PHOTO_CAPTURE_CHECKLIST.md,
AUDIT.md. UX_AUDIT.md describes the plain-language principles (still applied) as reviewed on the old screens. ENGINEERING_PACKAGE_SPEC.md still describes the format of the demo packages in `engineering-packages/`.

Test deployment: https://field-execution-platform.vercel.app (see [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)).
