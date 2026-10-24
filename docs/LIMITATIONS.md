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
- Accounts are created by script (`tools/seed_accounts.py`); there is no sign-up, invite or password-reset screen.
  One employer and its employees per company; no finer permissions.
- No rate limiting on AI calls; each photo costs one model call (~6–9 s), each question one embedding + one model call.
- Photos must be JPEG/PNG/WebP. HEIC files are rejected (415).
- Document search reads text PDFs and .txt files. Scanned PDFs (images of pages) are stored but not searchable.
- Supabase is reached through its REST API, which has no multi-statement transactions (see DATABASE.md).
- Signed file links expire after an hour; a page left open longer needs a reload to show photos and models again.
- Updates from the other person's device appear by polling (6–8 s), not push. No offline mode.
- AI cannot verify torque, tightness, dimensions, load capacity or internal condition, and is instructed not to claim so.
  AI output is advisory and is never a certification.

## Multi-industry (electrical panel)
- ICP-001 is a fictional, simplified representative panel. It is not a certified design, has no electrical simulation, and all ratings are demo values.
- Demo-mode images are 3D renders, not photographs, and are labelled as such. Precomputed AI results are real earlier calls, replayed and labelled.
- The AI never establishes electrical safety, de-energization, wiring correctness, conformity, voltage, continuity, insulation or torque.
- Dependencies: 2 moderate advisories remain in react-router v6 (fixed only in v7); not applicable to this app (see AUDIT.md, audit 2).
- UTEP Conference Chair: an approximate model built from photos (estimated dimensions, simplified shapes). Some reference photos show bystanders.
- FE-001 extinguisher: an illustrative model (no manufacturer, no certified values). The exploded view is not a disassembly procedure. Demo images are synthetic until real photos are added.
