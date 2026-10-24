# API contracts

The live OpenAPI schema is at `http://<host>:8000/docs` (`/openapi.json`). All bodies are JSON unless noted.
Workflow rule violations return `409` (state conflict) or `422` (missing evidence or justification), with
`{"detail": str, "issues": [{reason, item_id?, requirement_id?, component_id?, title?}]}`.

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | App label, AI provider availability |
| GET | `/api/products` | Revisions + instances |
| GET | `/api/revisions/{product_id@rev}` | Components, requirements, `assembly_url`, documents |
| GET | `/api/instances/{serial}` | Product passport: inspections, findings, timeline |
| GET | `/api/packages` | Packages on disk + validation report + load status |
| POST | `/api/packages/{dir}/load` `{actor}` | Validate + import (409 on immutable-revision conflict) |
| POST | `/api/inspections` `{serial_number, inspector}` | Start (or resume the open) inspection |
| GET | `/api/inspections?status=` | List |
| GET | `/api/inspections/{id}` | Full state: items (with evidence + assessments), findings, `component_status`, `progress`, `readiness`, activity |
| POST | `/api/inspections/{id}/items/{item}/evidence` *(multipart: file, actor, note?, assess?)* | Store photo, run image checks + AI, return assessment + state |
| POST | `/api/evidence/{id}/assess` | Re-run the AI assessment |
| GET | `/api/evidence/{id}/file` | Image |
| POST | `/api/inspections/{id}/items/{item}/decision` `{decision: pass/fail/not_applicable, actor, observation?, manual_confirmed?, override_note?, finding?: {description, severity}}` | Inspector disposition |
| POST | `/api/inspections/{id}/submit` `{actor}` | Completion validation (409 + blocking issues) |
| POST | `/api/inspections/{id}/review` `{reviewer, decision: approve/reject/request_evidence, comments?, item_ids?}` | Supervisor decision (reviewer ≠ inspector) |
| GET | `/api/findings?status=` | Findings + corrective action + evidence |
| POST | `/api/findings/{id}/transition` `{to, actor, assigned_to?, note?}` | Finding lifecycle |
| POST | `/api/findings/{id}/evidence` *(multipart: file, actor, kind=corrective_before/after)* | Before/after photos |
| GET | `/api/activity` | Recent activity events |
| GET | `/package-files/{dir}/...` | Package files (GLB, drawings, BOM) |

AI assessment result (validated schema): `summary, correct_area_visible (yes/no/uncertain), image_quality,
evidence_sufficient, observations[], conditions_for_human_review[], missing_information[],
recommended_action (accept_for_human_review/retake_photo/flag_for_human_review), retake_guidance, uncertainty, limitations[]`.
Assessment `status`: `completed | unavailable | failed | refused`.

## Multi-industry additions
| Method | Path | Purpose |
|---|---|---|
| POST | `/api/inspections` `{serial_number, inspector, mode: live/demo}` | Mode is fixed per inspection |
| GET | `/api/inspections?status=&industry=` | Rows include `mode`, `industry`, `asset_category` |
| POST | `/api/inspections/{id}/items/{item}/demo-evidence` `{demo_id, actor, live_ai}` | Demo inspections only; live AI first, else the labelled precomputed result, else "unavailable" |
| GET | `/api/dashboard?industry=` | Totals, by industry, asset, status, finding severity, recent |
Revisions include `industry`, `asset_category`, `demo_evidence[]`, components' `specs`/`articulation`. Assessments include `origin` and `captured_at`.
