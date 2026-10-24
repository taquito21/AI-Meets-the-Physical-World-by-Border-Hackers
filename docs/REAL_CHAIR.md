# UTEP Conference Chair: real-world demo asset

Asset `UTEP-CHAIR-RW` rev A, package `engineering-packages/utep-conference-chair-rw`, unit `UTEP-CHAIR-RW-01`
(the physical chair in the pitch room). Added alongside the earlier assets; nothing was removed or changed in them.

## How the model was made
- Five photographs taken by the team at the venue on 2026-10-24 (front, rear, side, underside, mechanism close-up).
  They are kept as reference images (`reference-images/`), re-encoded without metadata.
- `source/generate_geometry.py` builds the geometry from primitives (boxes, cylinders and a new **torus** for the foot ring)
  using **dimensions estimated from the photos**. It is not manufacturer CAD and not a dimensional reconstruction.
- `tools/build_package.py` turns it into `assembly.glb`: 33 nodes, about 2,000 triangles, 81 KB, fine for phones.
- Observed facts are recorded as observed (e.g. "HON logo visible on the lower rear rail", 3 ring spokes, 5 arms).
  The manufacturer field says "Unverified". No load ratings, materials or certifications are claimed.

## Components (12, stable IDs)
Seat cushion, seat support (shell), backrest mesh, backrest frame, left/right loop armrests, circular foot ring
(ring + collar + 3 spokes), central gas lift, five-star base, casters (5), under-seat mechanism, underside label.
Each has a technical sheet (estimated values marked "demo"), exploded-view vector, reference photos and requirements.

## Inspection profile (12 requirements, 7 with photos)
Upholstery, seat stability, mesh, frame, both armrests, foot ring, gas-lift function, mechanism and fasteners,
label documentation (optional), base, casters. No load testing, measurement or manufacturer criteria.

## AI results on the real photos (claude-opus-5-5, captured 2026-10-24)
| Requirement | Result |
|---|---|
| Seat cushion (front photo) | Usable evidence: no visible tears, peeling or open seams |
| Backrest mesh (rear photo) | Usable evidence: no holes or runs |
| Backrest frame (rear photo) | Usable evidence: four corners and the lower rail (HON logo) visible, no cracks |
| Foot ring (underside photo) | Usable evidence: ring, 3 spokes and collar visible; clamp firmness needs the hand check |
| Mechanism (close-up) | **Flagged for human review**: some star-shaped holes in the mounting plate look empty; confirm whether fasteners are missing |
| Label (close-up) | Retake: label is cut off and angled |
| Base (side photo) | Usable evidence: five arms, hub and casters visible |

These are stored as precomputed demo results and also reproduce live: the same photos uploaded through a live
inspection gave the same verdicts in 6–8 s.

## Demo with the physical chair (about 40 s)
1. Assets → Furniture → **UTEP Conference Chair → Inspect** (live) on `UTEP-CHAIR-RW-01`.
2. Point at the real chair, then rotate the model and tap **Explode** (seat up, back away, ring forward, base down).
3. Tap the seat → **Take photo** of the real seat → AI: usable evidence → **Pass**: the seat turns green.
4. Optional: tap the mechanism → photograph the underside → AI flags the empty holes for human review.
   This is a genuine observation on this chair; confirm it by hand before calling it a finding.
5. Offline fallback: start a **Demo inspection** instead and use the prepared real photos (results labelled precomputed).

## Limitations
- Approximate geometry: rounded edges, the curved back profile and the exact loop shape of the armrests are simplified.
- Dimensions are estimates from photos, not measurements.
- Some photos show people in the background. They are stored in the private repo and the password-protected
  deployment, and were sent to the AI provider for analysis. Crop them if they will be shown publicly.
