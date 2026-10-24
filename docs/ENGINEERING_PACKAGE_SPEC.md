# Engineering package specification (v1.0)

One directory per **approved product engineering revision**. Every product source (hand-prepared package,
future manufacturer upload, future CAD/PLM pipeline) must produce exactly this format and pass validation.

```
<package-dir>/
  manifest.json                 package + product identity, file pointers, documents
  assembly.glb                  glTF 2.0 binary; one NAMED node per inspectable part instance
  components.json               component definitions (stable IDs, part numbers, node mapping, explosion)
  bom.csv                       item,part_number,description,quantity,unit
  inspection-procedure.json     requirements per component
  drawings/                     documents referenced from manifest.documents
  reference-images/             optional venue/reference photos (excluded from content hash)
  source/geometry.json          optional authoring source for tools/build_package.py
```

## manifest.json
Required fields: `package_version`, `manufacturer`, `product_id`, `product_name`, `engineering_revision`,
`assembly_file`, `components_file`, `bom_file`, `inspection_procedure_file`.
Optional: `package_id`, `manufacturer_id`, `product_description`, `released_at`, `units` (m), `documents[]`
(`{id, title, type, path}`), `demonstration_package` (bool), `provenance`.

## components.json
```json
{ "product_id": "CHAIR-001", "engineering_revision": "A", "assembly_id": "CHAIR-001-ASSY",
  "components": [ {
    "component_id": "CHAIR-001-SEAT", "part_number": "CH-100", "name": "Seat panel", "quantity": 1,
    "category": "panel", "material": "...", "description": "...",
    "model_node_ids": ["seat_panel"],
    "explosion": { "direction": [0, 1, 0], "distance": 0.22 },
    "documents": ["DWG-CH-GA"] } ] }
```
- Each physically distinct, individually inspectable part (e.g. each leg) is its own component.
  Identical small parts inspected together (fasteners, glides) may be one component with `quantity = n` and n nodes.
- `explosion.direction` is in assembly space (Y up) and is normalized by the viewer. `distance` is in metres.

## inspection-procedure.json
```json
{ "procedure_id": "IP-CHAIR-001", "procedure_revision": "A", "product_id": "CHAIR-001", "engineering_revision": "A",
  "requirements": [ {
    "requirement_id": "SEAT-SURFACE", "component_id": "CHAIR-001-SEAT", "title": "...", "instructions": "...",
    "acceptance_criteria": ["..."], "evidence_type": "photo | manual_confirmation | photo_and_manual_confirmation",
    "required": true, "photo_guidance": "...", "visual_limitations": ["..."] } ] }
```

## Validation rules (enforced by `backend/app/packages.py`)
Errors (block loading):
- Missing manifest fields or files; invalid JSON; GLB not glTF 2.0.
- `product_id`/`engineering_revision` mismatch between manifest, components and procedure.
- Duplicate `component_id` or `requirement_id`; missing part number; quantity not a positive integer.
- `model_node_ids` empty, not present in the GLB, or one node mapped to two components.
- Explosion direction not a non-zero 3-vector, or a negative distance.
- BOM part numbers missing from components (or vice versa); BOM quantity ≠ sum of component quantities per part number.
- Requirement references an unknown component; invalid `evidence_type`; `required` not boolean; missing title or instructions.
- Component or manifest document references that do not resolve.

Warnings: component ID not prefixed by product ID; quantity ≠ node count; GLB mesh node not mapped; component without requirements.

## Revision integrity
The content hash covers every file except `reference-images/`. A loaded revision is immutable: changes require a new
`engineering_revision`, so old inspections keep their requirements, which are also snapshotted per inspection item.
During development, `tools/reset_demo_data.py --yes` wipes the local demo data.

## v1.0 optional extensions (multi-industry)
- manifest: `industry` (e.g. "Furniture", "Electrical"), `asset_category`.
- component: `specs: [{label, value, demo_value?}]` (technical sheet; mark fictional values `demo_value: true`),
  `inspection_type`, `articulation: {type: "hinge", label?, pivot[3], axis[3], angle_deg}` (e.g. a door).
- procedure: `safety_notes[]`, `ai_guidance`; requirement: `inspection_points[]`, `possible_findings[]`, `risks[]`,
  `recommended_actions[]`, `human_review_required`.
- `demo-evidence/demo-evidence.json`: `items: [{id, requirement_id, file, caption, source, precomputed_assessment?}]`.
  It is excluded from the content hash and is used only by demo-mode inspections.
- Validation: a quantity-1 part may have several nodes; a set with quantity n > 1 should have n nodes.

## Geometry source shapes and textures (tools/build_package.py)
`box`, `cylinder`, `torus`, `lathe` (profile of [r, y] bottom→top), `tube` (path of points + radius), `arc_panel`
(radius, height, a0_deg, a1_deg; 90° faces +Z), `disc` (faces +Z), `plane` (double-sided). A material can set
`"texture": "textures/x.png"` (relative to `source/`); the PNG is embedded in the GLB and the meshes using it get UVs
(lathe, tube, arc_panel, disc and plane only).

## Assets without a 3D model
`assembly_file` is optional. Without it, components need no `model_node_ids` or `explosion`, and the app inspects them
from the component list. The inspection engine is unchanged.
