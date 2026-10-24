# Audit (2026-10-24)

Scope: backend workflow rules, REST API, AI integration, security, web client, 3D viewer, engineering packages, docs.
Method: code review, plus a regression test written for every backend issue *before* fixing it
(`backend/tests/test_audit.py`; all 7 failed against the old code and pass now).

| # | Severity | Area | Finding | Fix |
|---|---|---|---|---|
| 1 | **High** | Workflow | When a supervisor requested more evidence on a *manual-confirmation* requirement, the inspector could not resolve it: no photo can be uploaded and "pass" was refused. The inspection deadlocked. | A manual requirement can be passed again with an observation describing the re-check. Photo requirements still need a new photo. The UI explains which. |
| 2 | **High** | AI / workflow | A late AI result for an older photo could put an item back to "more evidence" after a newer photo was submitted. The "latest assessment" lookup could also pick an old photo's result. | Assessments only affect the item if they belong to its latest photo; the pass rule only looks at the latest photo's assessment. |
| 3 | Medium | API | Uploading to an unknown inspection or item caused a 500 (FK error) and left an orphan file on disk. | Validated before storing (404/409); the file is removed if the transaction fails. |
| 4 | Medium | Workflow | A second inspection of the same unit could be started while one was awaiting supervisor review. | Refused (409); the catalog shows "Under review" instead of "Inspect". |
| 5 | Medium | Workflow | Evidence could be re-assessed by AI after submission or approval, adding records to a closed inspection. | Re-assessment is only allowed while the inspection is editable. |
| 6 | Medium | Workflow | An item with an open finding could be changed to "not applicable", hiding the failure. | Blocked until the finding is voided. |
| 7 | Medium | Traceability | Passing an item whose photo the AI flagged for human review left no trace for the supervisor. | A readiness warning lists the flagged conditions. |
| 8 | Medium | Client | A background refresh started before a decision could briefly overwrite the newer state (status flicker, possible double click). | Stale poll responses are discarded. |
| 9 | Low | API | Whitespace-only names were accepted as inspector, reviewer or actor, weakening the reviewer ≠ inspector check. | Names are stripped and must be non-empty (≤ 80 chars). |
| 10 | Low | Data | Timestamps had 1-second resolution, so events in the same second could be misordered. | Millisecond timestamps, plus rowid as a tie-breaker. |
| 11 | Low | Performance | Image decoding and re-encoding of phone photos ran on the event loop, stalling other requests (supervisor polling). | Moved to a worker thread. Malformed or decompression-bomb images now return 415 instead of 500. |
| 12 | Low | Config | A `.env` line without `=` (e.g. `KEY: value`) was silently ignored. This happened with the API key. | A warning is logged with the line number only (never the content). |
| 13 | Low | Traceability | AI assessment and corrective-action events were missing from the inspection timeline. | `inspection_id` is added to their event metadata. |
| 14 | Low | Package | Three table apron rails had no inspection requirement (validator warnings), so they could never turn green. | One requirement per rail; 0 warnings. |
| 15 | Low | Drawing | Dimension and title text overflowed the drawing border. | Wider canvas. |
| 16 | Low | 3D viewer | Cloned materials were never disposed; the pointer cursor could stay "hand" after leaving; the label allocated objects every frame. | Dispose on unmount, cursor reset, reused objects. |
| 17 | Low | UX | No way to cancel after pressing "Fail…". | Cancel button. |

Reviewed with no change needed: path traversal (package files, evidence, SPA), XSS (React escaping; AI text rendered as text),
API key exposure (server-side only), SQL injection (parameterized queries), revision immutability, segregation of duties,
GLB face winding and normals.

Accepted risks (documented in LIMITATIONS.md): no authentication, CORS `*` on the LAN, single SQLite process,
polling instead of push, no rate limiting on AI calls.

Note: during the AI verification an API key value was printed in a development tool log. Rotating it after the event is recommended.

---

# Audit 2 (2026-10-24, after the electrical scenario, Vercel deploy and GitHub repo)

Scope: multi-industry code, demo mode, dashboard, Vercel configuration, password gate, photo compression, dependencies, repository.
Method: same as audit 1. Each backend issue got a test first (`backend/tests/test_audit2.py`); 5 of 6 failed before the fix.

| # | Severity | Area | Finding | Fix |
|---|---|---|---|---|
| 1 | **High** | Dependencies | `react-router-dom` 6.26.2: 3 high advisories (open redirect / XSS via redirects). `drei` 9.114 pulled a vulnerable `uuid`. | Upgraded to `react-router-dom` 6.30.6 and `drei` 9.122.0 (same major versions). 3D, door, explode and navigation re-verified in the browser. |
| 2 | Medium | Deployment | On Vercel the AI call could run 60 s × 2 attempts while the function is killed at 60 s, leaving a photo without an assessment and a 504 error. | On Vercel the AI timeout is 40 s with no retry (`AI_TIMEOUT_S`, `AI_MAX_RETRIES` configurable); locally it stays 60 s with 1 retry. |
| 3 | Medium | Traceability | Demo inspections and their findings appeared without a "demo" mark in the product passport and the findings list, so they could be mistaken for real records. | `mode` returned for passport inspections/findings and the findings list; DEMO chips shown. |
| 4 | Medium | Dashboard | "Components inspected" counted a component as soon as one of its requirements was done. | Counts a component only when all of its requirements have a final disposition. |
| 5 | Low | Packages | A malformed precomputed AI result in `demo-evidence.json` passed validation and would fail (500) during the demo. | The validator checks it against the assessment schema and requires `model` and `captured_at`. |
| 6 | Low | Client | Photo compression used a `createImageBitmap` option unsupported by older Safari; the fallback sent the original photo, which can exceed Vercel's 4.5 MB limit. A 413 from Vercel showed a generic error. | Fallback decoding through `<img>`; a clear "photo too large" message. |
| 7 | Low | Serverless | Two simultaneous first requests on a cold instance could initialize the database at the same time. | Initialization guarded by a lock (idempotent). |
| 8 | Low | UX | If the server was starting when the page loaded, Home showed "Server unreachable" until a manual reload. | The health check retries every 5 s until it answers. |
| 9 | Low | Accessibility | The "Demo inspection" button's tooltip replaced its accessible name. | Uses `aria-describedby` with a visible hint instead. |

Reviewed with no change needed: password gate (constant-time compare, all routes including `/docs`), no secrets in git or the
Vercel bundle (98 tracked files, 52 deployed), upload size limit (413 with a clear message), path traversal, demo/live separation rules.

Accepted risks: 2 moderate advisories remain in `react-router` 6 that are fixed only in v7, a breaking major upgrade. Neither
applies here: we use no untrusted redirect paths and no SSR hydration. The API key value appeared in a development tool log
earlier; rotate it after the event.
