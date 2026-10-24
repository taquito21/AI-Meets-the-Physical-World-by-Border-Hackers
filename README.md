# field-execution-platform

Hackathon MVP for the **1881 International Hackathon 2026, Track 3: AI Meets the Physical World**.
Interface label: **Field Assistant** (temporary, configurable via `APP_LABEL`; the product name is not final).

It turns manufacturer engineering packages (3D assembly, components, BOM, inspection procedure) into
component-aware field inspections. Inspectors explore an interactive and explodable 3D assembly, select parts,
capture photo evidence, get an AI-assisted evidence review, record findings, and submit for supervisor review.
Every decision is persisted and traceable to the engineering revision used.

The chair and table are **replaceable product data**. The inspection engine is product-agnostic.

## Quick start (Windows, Git Bash)

```bash
# backend
py -3.12 -m venv backend/.venv
backend/.venv/Scripts/python -m pip install -r backend/requirements.txt
cp backend/.env.example backend/.env      # then set ANTHROPIC_API_KEY for live AI assessment

# web client (built once, then served by the backend)
cd web && npm install && npm run build && cd ..

# run (serves API + web app on port 8000, all interfaces)
backend/.venv/Scripts/python -m uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8000
```

Open `http://localhost:8000` on the laptop, or `http://<laptop-LAN-IP>:8000` on a phone on the same Wi-Fi
(allow Python through Windows Firewall when prompted). The phone camera opens through the photo button.
No HTTPS is needed for this.

Without an API key, everything works except AI assessment, which honestly reports "unavailable". The inspector still decides.

Development with hot reload: run the backend as above, then `cd web && npm run dev` and open port 5173 (it proxies `/api` to the backend).

## Useful commands

```bash
backend/.venv/Scripts/python -m pytest -q backend/tests          # backend + workflow tests
backend/.venv/Scripts/python tools/validate_packages.py          # validate engineering packages
backend/.venv/Scripts/python tools/build_package.py engineering-packages/chair-model-001   # rebuild GLB + drawing
backend/.venv/Scripts/python tools/reset_demo_data.py --yes      # wipe local DB + evidence (stop server first)
```

## Layout

```
backend/app/        FastAPI app: packages.py (validation), catalog.py (import), workflow.py (rules), ai.py, main.py (REST)
backend/tests/      end-to-end API tests
web/src/            React + Three.js (React Three Fiber) client; AssemblyViewer.tsx is the reusable 3D viewer
engineering-packages/  chair, table, electrical panel ICP-001, real venue chair, fire extinguisher FE-001
tools/              package builder, validator, data reset, demo AI precompute
docs/               architecture, package spec, API, demo script, limitations, model replacement, photo checklist
```

Three scenarios run on the same engine: **Furniture** (chair, table, real venue chair), **Electrical** (control panel ICP-001) and **Facility Safety** (fire extinguisher FE-001). See [docs/MULTI_INDUSTRY.md](docs/MULTI_INDUSTRY.md) and [docs/FIRE_EXTINGUISHER.md](docs/FIRE_EXTINGUISHER.md).

Test deployment: https://field-execution-platform.vercel.app (see [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)).

See [docs/DEMO.md](docs/DEMO.md) for the 2-minute pitch flow and [docs/LIMITATIONS.md](docs/LIMITATIONS.md) for what is simulated.
