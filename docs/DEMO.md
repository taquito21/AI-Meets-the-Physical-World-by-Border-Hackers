# Demo script (~120 s)

**Setup (before the pitch)**
1. Laptop: run the server; open `http://localhost:8000/supervisor` on the projector as "Supervisor B" (Home → set name/role).
2. Phone: same Wi-Fi, open `http://<laptop-IP>:8000`, set name "Inspector A". Add it to the home screen.
3. Make sure **AI shows "available"** on the Home screen (`ANTHROPIC_API_KEY` in `backend/.env`). Do one test photo.
4. Rehearsal inspection: on `CHAIR-001-SN-0025`, do all manual-confirmation items and the brackets photo **for real** beforehand.
   Leave **Seat surface** and **Backrest attachment** for the live demo. Never pre-fill AI results.
5. Have a backup screen recording (`docs/` → record the rehearsal) in case of network failure.

| Time | Scene | Action | Say |
|---|---|---|---|
| 0:00 | 1 Engineering | Import Studio → chair package (Valid, demo package) | "A manufacturer already has this engineering: assembly, BOM, procedure. Here it's a fictional manufacturer's package we prepared, run through our real validation pipeline." |
| 0:15 | 2 Digital product | Open inspection → rotate → **Explode** → tap **Backrest** | "Every part is a real record: part number, quantity, and the manufacturer's inspection requirements." |
| 0:35 | 3 Physical | Point at the real chair. **Backrest attachment** → Take photo of a joint (deliberately far away or blurry) | "The worker photographs the actual part." |
| 0:50 | 4 Evidence | AI result: *retake recommended*, item stays amber | "The AI checks the evidence, not the product. The photo doesn't show the fastener, so it asks for another. It can't approve anything." |
| 1:00 | 4 | Retake a close-up → usable evidence → tick manual check → Pass | "The human confirms the physical check. AI assists, people decide." |
| 1:10 | 5 Progress | Assemble → green/amber parts. Tap **Submit**: blocked, with the list of what's missing | "The server refuses premature completion. The 3D colors come from persisted workflow state." |
| 1:25 | 4b Finding | Seat surface → photo → **Fail…** → "DEMO: scratch on seat edge", low → seat turns red | "Findings attach to the exact component and revision." |
| 1:40 | 6 Record | Submit → summary; projector shows it in the supervisor queue → Approve | "Evidence, AI assessments, findings and decisions, all traceable to engineering revision A." |
| 1:55 | Close | | "We turn the manufacturer's engineering into evidence-driven inspections of physical products." |

**AI latency:** expect roughly 6–9 s per photo (measured with `claude-opus-5-5` at effort `low`). Talk over the spinner
("it's checking the photo against the manufacturer's requirement…"). A deliberately far-away shot reliably triggers a retake.

**If AI is unavailable live:** the card says "AI assessment unavailable", and the inspector decides. Say so honestly; never fake a result.
**If 3D fails on a device:** the component list still drives the full workflow.

## Electrical segment (+20–30 s)
After Scene 6: Assets → **Electrical** → open the prepared ICP-001 demo inspection → **Open door** → breakers → **Zoom to part** →
**Use demo photo (live AI)** (offline fallback: *precomputed result*, labelled) → **Fail… → Record finding** → **Dashboard → All industries**.
The full script is in MULTI_INDUSTRY.md §6.

## Real chair segment (preferred for the live demo)
Use the UTEP Conference Chair asset with the physical chair in the room. The script is in REAL_CHAIR.md.
