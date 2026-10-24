# Development log

## 2026-10-23 (Milestones 0–6)
- **Environment**: Windows 11, Node 24, Python 3.12, no Supabase or Anthropic credentials present, empty project folder.
- **Architecture**: FastAPI + SQLite + local evidence storage; mobile-first React/R3F web client served by the backend.
  Expo deferred (see ARCHITECTURE.md for the rationale). Branding configurable (`APP_LABEL`).
- **Packages**: chair (14 components, 26 nodes, 15 requirements) and table (12 components, 21 nodes, 9 requirements),
  generated GLBs + drawings from primitive geometry sources. The validator found 0 errors (3 table warnings: apron rails
  covered by one frame requirement).
- **Backend**: validation, import with immutable revisions, workflow engine, AI provider (Claude vision, structured output),
  findings/corrective actions, review, passport, activity log.
- **Tests**: `backend/tests/test_platform.py`, 8 passing: package validation (positive + negative), immutable revision,
  the full chair workflow (blocked submit, photo/manual guards, AI-unavailable path, finding, N/A justification, submit,
  self-review blocked, request-evidence loop, approve, corrective-action lifecycle with segregation of duties),
  the AI retake hold + override on the table, and health.
- **Browser check** (desktop + 375 px mobile emulation): catalog → inspection, 3D render, explode/assemble, 3D selection,
  pass-without-photo rejected, photo upload, AI-unavailable message, component turned green, submit blocked with an issue list,
  table product page, Import Studio, drawing.
- **Not yet verified**: real phones on venue Wi-Fi; venue furniture fit.

## 2026-10-24: live AI verification
- Key added to `backend/.env`. The loader requires `KEY=value`; a `KEY: value` line is silently ignored (fixed in place).
- Live call 1 (claude-opus-5-5, effort low): a striped test pattern submitted for *Seat surface condition* came back
  `correct_area_visible: no`, `evidence_sufficient: false`, `retake_photo` with specific retake guidance; 8.6 s.
  The item moved to `more_evidence_requested` (AI retake), the seat turned amber, and passing without an override was rejected (422).
- Live call 2: a screenshot of the app's 3D chair render, as a "retake". The model said it looked like a rendered model in an app
  screenshot, not a photo of SN-0025, and flagged the low resolution and oblique angle. It recommended a retake with high
  uncertainty and did not claim the seat was undamaged; 5.6 s. The item stayed held.
- Both results rendered in the inspector UI (AI card, retake guidance, limitations, provider/model/latency).
- **Still unverified**: the positive path (`accept_for_human_review`) with a real photo of a physical chair. Test it on the demo phone.

## 2026-10-24: full audit
- 17 findings (2 high), all fixed. See AUDIT.md. Backend: 15 tests pass (8 original + 7 audit regressions).
- The table procedure now has one requirement per apron rail (12 requirements); both packages validate with 0 warnings.
- Packages changed, so the local demo data was reset (revision A is immutable once loaded).

## 2026-10-24: multi-industry extension (Scenario B: electrical panel ICP-001)
- New package `electrical-panel-icp-001`: 15 components, 71 nodes, hinged door, technical sheets (demo values flagged), 15-point profile.
- Engine unchanged; additive migrations (`components.definition`, `inspections.mode`, assessment `origin`/`captured_at`).
- Live vs demo inspections; 8 rendered demo images with real precomputed `claude-opus-5-5` results.
- Shared dashboard with industry filter; scenario selector on Home; asset selector with industry filter.
- Tests: 24 passing. Details and the demo script are in MULTI_INDUSTRY.md.

## 2026-10-24: Vercel test deployment
- https://field-execution-platform.vercel.app (project machinno-x/field-execution-platform), shared password, temporary storage + banner.
- Verified in production: password gate (401 without it), health, 3 assets, GLB, demo images, real upload + live AI (6.7 s), demo + live AI (6.6 s).
- 52 files uploaded (no `.env`). Client-side photo compression for the 4.5 MB limit. 25 tests passing.
- Persistence is delegated to Xavier: DATABASE_HANDOFF.md.

## 2026-10-24: audit 2
- 9 findings (1 high: vulnerable dependencies), all fixed or documented. See AUDIT.md "Audit 2". 31 tests passing.
- Not redeployed and not pushed yet (pending approval).

## 2026-10-24: real venue chair asset (UTEP-CHAIR-RW)
- Built from 5 team photos: new package `utep-conference-chair-rw` (12 components, 33 nodes, 12 requirements), with a torus primitive added to the GLB builder.
- **AI positive path verified on real photos**: 5 of 7 accept_for_human_review, 1 genuine flag (empty fastener holes on the mechanism plate), 1 retake (label cut off).
  The same verdicts were reproduced through a live inspection upload (6–8 s).
- 32 tests passing. The local demo data was reset (immutable revision reloaded). See REAL_CHAIR.md.

## 2026-10-24: fire extinguisher FE-001 + platform improvements
- New illustrative asset FE-001 (12 components, textured GLB, 12 requirements, conservative AI guidance). See FIRE_EXTINGUISHER.md.
- GLB builder: lathe, tube, arc_panel, disc and plane shapes, embedded textures, face-orientation check; existing assets rebuild byte-identically.
- Assets without a 3D model are supported (assembly_file optional).
- Viewer: tapping empty space clears the selection; the selected part is strongly highlighted.
- 36 tests passing; 10 real AI calls on synthetic test images (behaviour matched expectations); no real extinguisher photos yet.
