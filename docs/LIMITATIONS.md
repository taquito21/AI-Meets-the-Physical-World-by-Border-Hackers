# Implemented vs simulated vs future

## Functional (tested)
- Engineering package format, validation (node ↔ component ↔ BOM ↔ requirement integrity), import and immutable revisions.
- Interactive 3D assembly: rotate, zoom, select, highlight, label, explode/assemble animation, status colors from the server.
- Component-level inspection with requirement snapshots, photo evidence (phone camera), deterministic image checks.
- AI-assisted evidence assessment (Claude vision, structured and validated output), with error, timeout and refusal handling.
- Completion validation, findings, corrective-action lifecycle with before/after photos, supervisor review with
  request-evidence loop, segregation-of-duties checks, product passport, activity timeline, printable summary.
- Supervisor screen refreshes by polling (4–5 s), not push.

## Simulated / demonstration only
- **Manufacturer and engineering packages are fictional**, prepared by the team (`demonstration_package: true`).
- **Engineering Import Studio** loads prepared packages. **No native CAD/STEP parsing or conversion exists.**
- **3D models are provisional primitive-geometry fixtures**, not verified representations of the venue furniture.
  Dimensions, materials and fastener specifications are labelled demonstration assumptions.
- Drawings are auto-generated simplified projections ("not for manufacture").
- Product instances and serial numbers are sample data.

## Not implemented / limits
- No authentication: names are free text, and role separation is checked by name only. CORS is open (`*`) for LAN use.
- No rate limiting on AI calls; each photo costs one model call (~6–9 s).
- Photos must be JPEG/PNG/WebP. iOS normally converts camera captures to JPEG for web uploads; HEIC files from other sources are rejected (415).
- Not the Expo/React Native app: the MVP is a mobile web app (see ARCHITECTURE.md). No offline mode.
- SQLite + local disk instead of Supabase; a single server process.
- Running it needs the laptop server reachable on the LAN.
- AI cannot verify torque, tightness, dimensions, load capacity or internal condition, and is instructed not to claim so.
  AI output is advisory and is never a certification.
- QR codes are not generated in-app yet (the passport URL `/p/<serial>` can be encoded with any QR tool). A QR code identifies a record; it does not prove the unit is present.
- No product release step, PLM/ERP integration, analytics, AR or document Q&A.

## Multi-industry (electrical panel)
- ICP-001 is a fictional, simplified representative panel. It is not a certified design, has no electrical simulation, and all ratings are demo values.
- Demo-mode images are 3D renders, not photographs, and are labelled as such. Precomputed AI results are real earlier calls, replayed and labelled.
- The AI never establishes electrical safety, de-energization, wiring correctness, conformity, voltage, continuity, insulation or torque.
- Dependencies: 2 moderate advisories remain in react-router v6 (fixed only in v7); not applicable to this app (see AUDIT.md, audit 2).
