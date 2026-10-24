# Adapting the chair/table to the venue furniture (Oct 24)

Goal: change **product data only**. No changes to the engine, API or schema.

1. **Review photos** (see PHOTO_CAPTURE_CHECKLIST.md). Pick the chair and table for the demo. List the visible parts:
   panels, legs, rails/stretchers, brackets, visible fasteners, glides. Note what is *not* visible (hidden joints).
2. **Choose the closest package** (`chair-model-001` / `table-model-001`). Keep the directory, `product_id` and revision `A`
   (nothing has been released yet. After the pitch freeze, any change means revision `B`).
3. **Edit geometry** in `source/geometry.json`: adjust `size` / `position` (metres, Y up, +Z front), and add or remove nodes.
   Approximate proportions from the photos; dimensions are *demonstration assumptions*.
   - Alternative: model in Blender and export `assembly.glb`, with one object per part and object names equal to node IDs.
4. **Rebuild**: `backend/.venv/Scripts/python tools/build_package.py engineering-packages/chair-model-001`
5. **Update `components.json`**: one entry per inspectable part. Set `model_node_ids`, `part_number`, `quantity`,
   material/description ("assumed" where unknown), and `explosion` direction and distance (outward from the part's position; fasteners further).
6. **Update `bom.csv`** so per-part-number quantities equal the sum of component quantities.
7. **Update `inspection-procedure.json`**: requirements for the parts actually visible on the venue furniture.
   Choose 2–4 photo requirements that are easy to photograph live, and use manual confirmation for the rest.
8. **Validate**: `backend/.venv/Scripts/python tools/validate_packages.py`. It must report zero errors.
9. **Reset and load**: stop the server, run `tools/reset_demo_data.py --yes`, then start the server (packages auto-load).
10. **Check in the browser**: product page, explode, tap each part (label and requirements correct), BOM table.
11. **Test with the real furniture**: run a full inspection with real photos from the demo phone and check the AI feedback.
12. **Freeze**: copy the `engineering-packages/` directory as a backup and do not edit it after the final rehearsal.

If the venue furniture is too complex, keep a clearly labelled representative model and say so in the pitch.
