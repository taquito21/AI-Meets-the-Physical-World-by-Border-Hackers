# Portable Fire Extinguisher: FE-001

Generic, illustrative asset (industry "Facility Safety", category "Fire Safety Equipment"). It is not attributed to any
manufacturer and contains no certified ratings, capacities or pressures (they are marked "manufacturer-dependent").
Package: `engineering-packages/fire-extinguisher-fe-001`. Units: `FE-001-SN-0001`, `FE-001-SN-0002`.

## What was reused (no new viewer, engine, AI service or dashboard)
- Package format, validator, catalog import, inspection engine, findings, review, dashboard: unchanged.
- The 3D viewer is the same `AssemblyViewer` (selection, highlight, explode, zoom-to-part).
- Claude assessment uses the same structured schema; the procedure's `ai_guidance` adds conservative rules for this asset.

## What was added to the platform (generic, usable by any asset)
- **GLB builder** (`tools/build_package.py`): new shapes `lathe` (rounded cylinder, nozzle), `tube` (hose along a curve),
  `arc_panel` (wrap-around label), `disc` (gauge face) and `plane` (tag); **embedded PNG textures**; and a face-orientation
  check. Existing assets rebuild byte-identically.
- **Assets without a 3D model** (mode B): `assembly_file` is now optional. Such assets are inspected from the component
  list, and the inspection engine never depends on the viewer (covered by a test).
- **Viewer**: tapping empty space clears the selection and restores colours; the selected part is clearly blue (all assets).
- **AI system prompt**: for safety equipment, never state charged / pressurized / ready / serviceable / compliant;
  describe a gauge needle only against clearly legible markings; never invent unreadable text, dates or values.

## Model (illustrative)
21 nodes, about 5,300 triangles, 185 KB including 3 small textures:
- red cylinder with rounded shoulders and a black base boot,
- valve with outlet,
- gauge (textured dial marked "DEMO"),
- carrying handle and operating lever,
- safety pin with ring, tamper seal,
- hose along a curve and nozzle,
- wrap-around label ("DEMONSTRATION MODEL … NOT A REAL PRODUCT LABEL"),
- yellow inspection tag (blank, "DEMO: not a record"),
- wall bracket with strap and hook.

Exploded view: valve up; handle and lever up and back; pin and seal outward; gauge forward along its axis; hose and nozzle
to the side; label forward; tag outward; bracket back; the cylinder stays. Safety notes state that this is **not a disassembly
or service procedure**. No internals are modelled.

## Components (12) and inspection (12 requirements)
CYL exterior (photo) · VAL condition (manual, optional) · HND handle (manual) · LEV lever (manual) · PIN pin + seal (photo) ·
SEA seal confirmed (manual) · GAU gauge visibility (photo, human review) · HOS hose + nozzle (photo) · NOZ opening (manual) ·
LBL label legible (photo) · TAG documented (photo; N/A with justification if absent) · BRK mounting and accessibility (photo).

## Test results (2026-10-24)
Automated (`pytest backend/tests`): **36 passed**, including FE-001 end to end (textured GLB, IDs shared with the engine,
demo flow, failed decision → finding → dashboard) and an asset with no 3D model.

Real AI (claude-opus-5-5), 10 synthetic test images (no real extinguisher photos were available):

| Case | Result |
|---|---|
| Synthetic render, full view | Recognized as a render; too small to judge → retake |
| Unrelated photo (real chair) | Identified a chair, no extinguisher → not usable |
| Blurry | Surface not judgeable → retake |
| Missing pin and seal | "Possible missing pin" flagged for human review |
| Simulated damage patch | "Could be obstruction, stain or damage" flagged |
| Legible synthetic gauge | "Needle within the green band"; noted it is a graphic; no certification |
| Unreadable gauge | Text not legible → retake |
| Missing label | No label visible |
| Label too small | Label panel seen; no text invented |
| Very dark | Underexposed → retake |

Scanning all outputs found no certification language ("is safe", "ready", "charged", "compliant"). Live through the
server: photo upload + AI in 6.4 s, then fail → finding, and premature submit blocked (409).

**Not executed:** a relevant *real* photograph of an extinguisher (none available) and an on-screen check of the 3D
(the app window was not visible). Visual 3D verification used offline renders of the GLB, and the app loaded and parsed
the textured GLB without errors.

## Demo (15–25 s)
1. Home → **Fire extinguisher** → FE-001-SN-0002 → **Practice**.
2. Rotate → **Separate parts** → tap the **gauge** → its check and technical details.
3. Follow the step guide to "Safety pin and tamper seal" and use the prepared photo with **No internet: use saved AI
   result**: the AI flags a possible missing pin (labelled SAVED PRACTICE RESULT, synthetic image). **Report a problem**.
4. Line: *"The same platform guides workers from office furniture to electrical systems and fire safety assets. The 3D
   model identifies components, the engine guides the workflow, the AI analyses evidence, and the human decides."*

## Using a real extinguisher at the venue
Take photos **without handling it** (do not remove it from the bracket, pull the pin or touch the seal): full view, gauge
close-up, pin and seal, hose and nozzle, label, tag, and the mounting with its surroundings. Put them in
`demo-evidence/`, add entries to `demo-evidence.json` (source: "Real photograph…"), then run
`tools/precompute_demo_assessments.py engineering-packages/fire-extinguisher-fe-001 --force`. No data reset is needed.
