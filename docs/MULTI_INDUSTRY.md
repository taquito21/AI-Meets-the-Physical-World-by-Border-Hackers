# Multi-industry extension: Scenario B, Industrial Electrical Panel (ICP-001)

## 1. Audit of the existing system (before changes)

| Area | Finding | Decision |
|---|---|---|
| Architecture | FastAPI + SQLite backend; React/Vite/R3F web client served by the backend | Kept as is |
| Navigation | react-router, mobile-first split view | Added Dashboard and an industry filter; no new flows |
| 3D | Product-agnostic `AssemblyViewer` (GLB nodes ↔ stable component IDs, explosion vectors, status tint) | Reused; added generic **hinge articulation** and **zoom-to-part** |
| Components / explosion | `components.json` + prepared vectors, validated against the GLB | Reused; added optional `specs`, `inspection_type`, `articulation` |
| Photos / evidence | Camera upload, EXIF strip, heuristic checks | Reused; added "Attach photo" (gallery) and demo evidence |
| AI | Claude vision, JSON-schema output, advisory only | Reused; prompt now carries industry, profile guidance, possible findings and demo-value flags |
| Inspections / checklists | `workflow.py` state machine, requirement snapshots | **Unchanged engine**; added inspection `mode` (live/demo) |
| Data | Packages → immutable revisions | Reused; additive migrations only |
| Dashboard | None (review queue only) | Added one shared dashboard with an industry filter |

There was no parallel architecture to introduce. The three concepts already existed and were extended:

- **Inspection Engine** = `backend/app/workflow.py` + the evidence/AI endpoints in `main.py`. Industry-agnostic.
- **Asset Definition** = engineering package: `manifest.json` (now with `industry`, `asset_category`), `assembly.glb`,
  `components.json` (now with `specs`, `inspection_type`, `articulation`), `bom.csv`, drawings.
- **Inspection Profile** = `inspection-procedure.json` (now with `safety_notes`, `ai_guidance`, and per requirement
  `inspection_points`, `possible_findings`, `risks`, `recommended_actions`, `human_review_required`).

Adding ICP-001 needed **no engine or schema rewrite**. It is a new package directory.

## 2. Files

Created:
- `engineering-packages/electrical-panel-icp-001/` (manifest, source geometry, GLB, components, BOM, profile, drawing, `demo-evidence/`)
- `backend/tests/test_multi_industry.py` (9 tests)
- `tools/precompute_demo_assessments.py`
- `web/src/pages/Dashboard.tsx`, `web/src/pages/Render.tsx` (dev image capture)
- `web/src/components/IndustryFilter.tsx`, `TechSheet.tsx`, `ProfileDetails.tsx`, `useAssemblyControls.tsx`

Modified:
- Backend: `db.py` (additive migrations), `packages.py` (new optional fields, demo evidence, hash exclusion),
  `catalog.py` (component definition, demo evidence), `workflow.py` (inspection mode), `ai.py` (shared context builder,
  electrical prohibitions), `main.py` (industry/mode in lists, demo evidence, dashboard), `seed_instances.json`
- Packages: chair/table `manifest.json` (+ `industry`, `asset_category`; no other change)
- Web: `api.ts`, `session.tsx`, `App.tsx`, `AssemblyViewer.tsx`, `ExplodeControl.tsx`, `RequirementCard.tsx`, `EvidenceCard.tsx`,
  `ui.tsx` (status labels), `Home.tsx` (scenario selector), `Catalog.tsx` (asset selector), `ProductDetail.tsx`, `Inspection.tsx`,
  `Summary.tsx`, `Supervisor.tsx`, `styles.css`

## 3. Data model changes (additive)

| Table.column | Purpose |
|---|---|
| `components.definition` | Full component JSON (technical sheet, articulation) |
| `inspections.mode` | `live` or `demo`; fixed for the life of the inspection |
| `evidence_assessments.origin` | `live` or `precomputed` |
| `evidence_assessments.captured_at` | When a precomputed result was actually produced |
| `evidence.kind = 'demo'` | Prepared demonstration photo (existing column, new value) |

Industry is read from the package manifest, so there is no new table and no second database. Existing databases are upgraded at startup.

## 4. Technical decisions

- **Door = generic hinge articulation**, declared in data (`pivot`, `axis`, `angle_deg`). Any asset can have doors, covers or lids without code changes.
- **Primitive-geometry model** (71 nodes) built by the existing `tools/build_package.py`. No new dependencies or heavy assets.
- **Status labels** now read *Pending / In progress / Requires review / Inspected / Finding reported* for every
  industry. They are derived server-side from persisted states. A photo alone never makes a component "Inspected".
- **Demo mode integrity**:
  - Demo photos are accepted only in `demo` inspections, and only for the requirement they were prepared for.
  - The AI result is either a live call made now, or a result produced earlier by a real call
    (`tools/precompute_demo_assessments.py`), stored with model and capture time and shown as "DEMO RESULT · precomputed".
  - If neither is available, the assessment says "unavailable". Nothing is fabricated.
- **Demo images are 3D renders** of the model, captured via the `/render/<revision>` dev page and labelled "3D render, not a photograph".
  The AI correctly identifies them as renders and usually asks for a real photo. On the breakers it flagged "no circuit labels visible (0 of 4)".
- **Electrical safety language**: the system prompt forbids claiming safety, de-energization, correct wiring,
  conformity, voltage, continuity, insulation or torque. The profile carries safety notes. All ratings are flagged as demo values.
  The panel builder is fictional, and no real brands or part numbers are used.

## 5. Validation

- `pytest backend/tests`: **24 passed** (8 original + 7 audit + 9 multi-industry).
- `tools/validate_packages.py`: 3 packages, 0 errors, 0 warnings.
- Real AI: 8 demo renders assessed by `claude-opus-5-5` (≈6–7 s each), plus one live call from the UI.
- Browser (desktop + 375 px):
  - Scenario selector → electrical assets.
  - 3D load; open door; select a part; zoom to part; technical sheet; inspection profile.
  - Demo photo with live AI → flagged condition → finding recorded → component shows "Finding reported".
  - Offline precomputed result clearly labelled.
  - Dashboard All/Electrical filters.
  - Chair inspection unchanged.
- Not verified: performance on the actual presentation phones; real photographs of a real panel.

## 6. Demo script for the electrical segment (20–30 s)

Before the pitch, have a **demo inspection already open** on `ICP-001-SN-0002`, or start one from Equipment → Electrical → *Practice*.

1. (Chair segment ends) Tap **Equipment** → **Electrical**. *"Same platform, different industry."*
2. Open the ICP-001 practice inspection → **Open door** → tap the breakers (or pick them from the list) → **Zoom to part**.
3. Show the technical sheet and inspection points (*"defined by the asset's inspection profile, not hard-coded"*).
4. **Use this photo** (live AI): the AI flags missing circuit labels for human review. If the network is slow,
   use **No internet: use saved AI result**, which is labelled as a saved practice result.
5. **Report a problem → Save problem** → the breakers turn red → **Dashboard → All industries** shows both scenarios.

Line: *"We didn't build a chair inspection app. We built an AI-powered inspection platform that adapts to different
industries, assets and field workflows."*

Fallbacks: precomputed results (offline); the component list works without 3D; the backup video.

## 7. Replacing the demo renders with real photos

Put photos in `engineering-packages/electrical-panel-icp-001/demo-evidence/`. Update `file`, `caption` and `source`
(credit the source; use your own photos or properly licensed ones). Then run:
`backend/.venv/Scripts/python tools/precompute_demo_assessments.py engineering-packages/electrical-panel-icp-001 --force`.
Demo evidence is excluded from the revision hash, so no data reset is needed.

## 8. Known limitations

- Demo images are renders; the AI says so. Real panel photos make a stronger demo.
- The panel is a simplified representative model, not a wiring design. No electrical simulation.
- One articulation type (hinge). No sliding parts.
- The dashboard is computed on request (fine at demo scale) and refreshes by polling.

## 9. Next scenarios (data-only additions)

Plumbing manifold / pump skid; HVAC rooftop unit; conveyor or packaging machine maintenance; fire-extinguisher and
emergency-equipment rounds; vehicle pre-use checks. Each needs a package (geometry + components + profile) and optional demo evidence.
