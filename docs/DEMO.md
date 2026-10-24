# Demo script (~120 s)

**Setup (before the pitch)**
1. Laptop: run the server; open `http://localhost:8000/supervisor` on the projector as "Supervisor B" (Home → set name/role).
2. Phone: same Wi-Fi, open `http://<laptop-IP>:8000`, set name "Inspector A". Add it to the home screen.
3. Make sure the AI is on: the Home screen shows a yellow "AI photo feedback is off" notice only when it isn't
   (`ANTHROPIC_API_KEY` in `backend/.env`). Do one test photo.
4. Rehearsal inspection: on `CHAIR-001-SN-0025`, do all manual-confirmation items and the brackets photo **for real** beforehand.
   Leave **Seat surface** and **Backrest attachment** for the live demo. Never pre-fill AI results.
5. Have a backup screen recording (`docs/` → record the rehearsal) in case of network failure.

| Time | Scene | Action | Say |
|---|---|---|---|
| 0:00 | 1 Engineering | Import Studio (small link at the bottom of Home) → chair package (Valid, demo package) | "A manufacturer already has this engineering: assembly, BOM, procedure. Here it's a fictional manufacturer's package we prepared, run through our real validation pipeline." |
| 0:15 | 2 Digital product | Open inspection → rotate → **Separate parts** → tap **Backrest** | "Every part is a real record: part number, quantity, and the manufacturer's inspection requirements." |
| 0:35 | 3 Physical | Point at the real chair. **Backrest attachment** → Take photo of a joint (deliberately far away or blurry) | "The worker photographs the actual part." |
| 0:50 | 4 Evidence | AI result: *retake recommended*, item stays amber | "The AI checks the evidence, not the product. The photo doesn't show the fastener, so it asks for another. It can't approve anything." |
| 1:00 | 4 | Retake a close-up → "Clear photo" → tick *I checked this myself* → **Looks good** | "The human confirms the physical check. AI assists, people decide." |
| 1:10 | 5 Progress | **Put back together** → green/amber parts. Tap **Send for review**: blocked, with a tappable list of what's missing | "The server refuses premature completion. The 3D colors come from persisted workflow state." |
| 1:25 | 4b Finding | Seat surface → photo → **Report a problem** → "DEMO: scratch on seat edge", Minor → seat turns red | "Findings attach to the exact component and revision." |
| 1:40 | 6 Record | **Send for review** → report; projector shows it under Review → **Approve** | "Evidence, AI assessments, findings and decisions, all traceable to engineering revision A." |
| 1:55 | Close | | "We turn the manufacturer's engineering into evidence-driven inspections of physical products." |

**AI latency:** expect roughly 6–9 s per photo (measured with `claude-opus-5-5` at effort `low`). Talk over the spinner
("it's checking the photo against the manufacturer's requirement…"). A deliberately far-away shot reliably triggers a retake.

**If AI is unavailable live:** the card says "AI feedback isn't available right now", and the inspector decides. Say so honestly; never fake a result.
**If 3D fails on a device:** the component list still drives the full workflow.

## Electrical segment (+20–30 s)
After Scene 6: Equipment → **Electrical** → open the prepared ICP-001 practice inspection → **Open door** → breakers → **Zoom to part** →
**Use this photo** (live AI; offline fallback: **No internet: use saved AI result**, labelled) → **Report a problem → Save problem** →
**Dashboard → All industries**.
The full script is in MULTI_INDUSTRY.md §6.

## Real chair segment (preferred for the live demo)
Use the UTEP Conference Chair asset with the physical chair in the room. The script is in REAL_CHAIR.md.

## Fire extinguisher segment (15–25 s)
See FIRE_EXTINGUISHER.md: Fire extinguisher → FE-001 **Practice** → Separate parts → gauge → saved (labelled) pin analysis → Report a problem.
