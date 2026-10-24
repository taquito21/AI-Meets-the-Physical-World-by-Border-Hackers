# Architecture

```
 Phone / laptop browser  ──HTTP/JSON──►  FastAPI (single process, port 8000)  ──►  SQLite (backend/data)
 React + R3F web client                  ├─ packages.py  validate engineering package       evidence/*.jpg
   AssemblyViewer (GLB, explode)         ├─ catalog.py   import → immutable revision
   Inspection / Review / Findings        ├─ workflow.py  ALL state transitions + rules
                                         ├─ ai.py        image checks + AI provider ──► Claude (vision, structured JSON)
                                         └─ /package-files, /api/evidence/*/file, SPA
```

## Key decisions (and why)

| Decision | Rationale |
|---|---|
| **Mobile-first web app instead of Expo for the hackathon** | The master prompt allows a standalone mobile web viewer if WebView adds complexity. One codebase gives the phone, laptop and supervisor screens. The camera works through `<input capture>` over plain HTTP on the LAN, and nothing needs installing on the presentation phones. An Expo shell can wrap this later (WebView), and all business logic is already server-side and REST-based, so a future Flutter client consumes the same API. |
| **SQLite + local files instead of Supabase** | No Supabase credentials were available, and the venue Wi-Fi is a risk. The schema mirrors the target PostgreSQL model (TEXT JSON → `jsonb`), and storage paths are relative, so the migration is mechanical. |
| **Workflow rules only in `workflow.py`** | The client renders state. Colors in the 3D view come from `component_status`, which the server derives from persisted items and findings. |
| **AI is advisory and bounded** | AI can move an item to `more_evidence_requested`, but it can never pass one. Passing needs an inspector disposition. Overriding an AI retake recommendation needs a written justification, which is shown to the supervisor. Supervisor-requested evidence cannot be overridden. |
| **Requirement snapshot per inspection** | `inspection_items.requirement_snapshot` freezes the requirement text, so later revisions never rewrite history. |
| **Immutable revisions** | Loading a package whose `(product_id, revision)` exists with a different content hash is refused (409). |
| **Primitive geometry source → GLB** | `tools/build_package.py` builds the GLB from `source/geometry.json` with one named node per part. Any GLB (Blender/CAD export) works if node names match `components.json`. |
| **Prepared explosion vectors** | Each component has `explosion.direction` + `distance`. The viewer interpolates `base + t·offset` without touching stored data. AI never infers assembly mechanics. |
| **Segregation of duties** | The reviewer must differ from the inspector, and the corrective-action verifier must differ from the person who recorded the work. Names are free text in the MVP (no auth). |

## State machines

Inspection: `in_progress → submitted → approved | rejected | changes_requested → (resubmit) submitted`

Item: `pending → evidence_submitted ⇄ more_evidence_requested → passed | failed | not_applicable` (new evidence reopens an item)

Finding / corrective action: `open → assigned → action_recorded → awaiting_verification → closed` (also `open → void`, `awaiting_verification → assigned` for rework)

Completing, approving, closing corrective actions and releasing a product are separate decisions. Approval does not close findings, and the MVP has no release step.

Component color (server-derived): red if any failed item or open finding; amber if any item awaits evidence or a decision, or is only partially done; green if all items are passed or N/A; grey if not inspected. Blue = client-side selection.

## AI integration

`ai.AnthropicProvider` sends the normalized JPEG (EXIF-stripped, ≤1568 px) and the requirement context. It uses `output_config.format` (JSON schema) and validates the response with Pydantic. It handles timeout, rate-limit, auth, connection and refusal errors, and stores the result as `failed` / `refused` / `unavailable` instead of fabricating one. The model is configurable (`AI_MODEL`, default `claude-opus-5-5`, effort `low` for latency). The server-side refusal fallback (`fallbacks: "default"`) is enabled and can be switched off with `AI_FALLBACKS=false`. The key lives only in `backend/.env`.
