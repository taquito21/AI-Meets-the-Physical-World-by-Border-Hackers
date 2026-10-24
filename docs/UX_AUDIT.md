# UX audit 3: first-time, non-technical users (2026-10-24)

**Goal:** someone who has never used the app, and is not comfortable with technology, can complete an inspection
without help. The app itself should say what to do next.

**Method:** walked through every flow on a 375 px phone screen as a first-time user:
- start,
- choose equipment,
- inspect each part,
- read the AI feedback,
- decide,
- report a problem,
- send for review,
- review as supervisor,
- fix a problem.

Each point below is a place where that person would get stuck or confused.

The workflow rules did not change. The server still enforces every rule: photo required, in-person confirmation,
the AI is advisory only, supervisor ≠ inspector, and closure needs an after photo. What changed is how the app explains
those rules and guides people through them.

## Findings and fixes

| # | Sev. | Problem for a first-time user | Fix |
|---|---|---|---|
| 1 | High | No guidance on the inspection screen. Eleven checks in a list, no "start here", and no way to know what comes next. | **Step guide** at the top: "Step N of M", the part and check, the one action to take, and a big **Go to this step** button. When a part is finished: "✓ This part is done. Next: X →". When all are done, **Send for review** appears in the guide itself. |
| 2 | High | On a phone, tapping a part opened its card below the 3D view and ~3 screens of other content, so it looked like nothing happened. | The app scrolls to the part (or to the exact check) and stops below the sticky menu. |
| 3 | High | Jargon throughout: Assets, Findings, N/A, Pass/Fail, "dispositioned", "0/11 required", requirement codes, revision codes, "manual confirmation", "evidence". | Plain words: Equipment, Problems, **Looks good / Report a problem / Doesn't apply**, "1 of 11 required checks done", "I checked this myself, in person". Codes moved into collapsed "Technical details". |
| 4 | High | The AI card was dense (verdict codes, grids, model names) and didn't say what to do. | One headline with an icon: **✓ Clear photo**, **↻ Please take another photo** + tip, or **! Something to check** + the list. Details sit under "What the AI saw". Footer: "The AI only helps. You decide the result." |
| 5 | Medium | Each check card didn't say what to do now, and the result buttons were small and equal in weight. | A "now" line ("Step 1: take a photo. Step 2: choose a result."). A "Check that" list. Big **Take photo** and result buttons. "Looks good" stays disabled until there is a photo, with the reason shown. |
| 6 | Medium | Server errors were technical ("Requirement cannot be dispositioned", "manual confirmation", "Not yet inspected"). | Rewritten at the source: "Before you can save this: Tick 'I checked this myself, in person' first." / "A few checks are still missing. Tap one to go there:". Each missing check is a link that opens it. |
| 7 | Medium | The home screen started with an identity form and a technical AI status. Its "Server unreachable" message flashed while loading, and it never explained what the app does. | One-line purpose, then **Continue where you left off**, then the three equipment types, then **How it works** in 3 numbered steps. Identity collapses to "Working as … Change". The AI notice appears only when the AI is actually off, with the action to take. Supervisor tools sit in their own section. |
| 8 | Medium | On a phone the top menu overflowed ("Import" cut off). | Four items (Equipment, Review, Problems, Dashboard) on their own row on phones. Import moved to a small admin link on Home. |
| 9 | Medium | No hint that the 3D model can be turned, zoomed or tapped. | A hint over the model ("Drag to turn · Pinch to zoom · Tap a part") that goes away on first touch. Buttons renamed **Separate parts / Put back together / Reset view**. Legend: Not checked yet / Selected / In progress / Done / Problem. |
| 10 | Medium | The equipment list led with manufacturer, product IDs and revisions. Units were listed by serial number, and "Demo inspection" was unclear. | Each card has the name and one sentence, then the unit **by location**, with **Start inspection** and **Practice** (try it with sample photos). The engineering details are under "About this equipment". This also hides a stale "Provisional development fixture" sentence. |
| 11 | Medium | The problems page showed the raw lifecycle ("action_recorded", "awaiting verification"). | Status in words (Reported, Assigned, Fix recorded, Waiting for a check, Closed: fixed, Cancelled). A "Next:" line says what to do. Buttons read "Assign to this person", "Save what was done", "Fix confirmed: close" and "Not fixed: send back". |
| 12 | Low | The supervisor decision didn't explain how to request changes ("Request evidence (0)" was disabled with no reason). | Three numbered steps. **Approve / Ask for changes / Reject**, with a hint on the disabled button. |
| 13 | Low | Muted text was low contrast and some chips were 0.7 rem. | `--muted` darkened to `#526071` and small text raised to 0.78 rem. Large touch targets (48 px) for the main actions. |
| 14 | Low | Severity codes (low/medium/high/critical). | Minor / Moderate / Serious / Critical: stop using it. |

Practice (demo) material is still labelled everywhere: "Practice" chips, "PRACTICE PHOTO", "SAVED PRACTICE RESULT", and
the practice-mode notice. It is never mixed with real inspections.

## Verification
- **Automated:** TypeScript check clean, production build OK, `pytest backend/tests`: **36 passed** (the reworded server messages
  keep the substrings the tests rely on).
- **Phone-size walkthrough (375 × 812) in the in-app browser**, on a practice inspection of FE-001-SN-0002:
  - The step guide opened step 1 and scrolled the check into view, right below the menu.
  - Saved practice result → **Clear photo** → **Looks good** → "This part is done. Next: Carrying handle →", and the guide moved to step 2.
  - Tapping "Looks good" without the in-person tick showed the new plain message; after ticking, it saved.
  - Safety pin: the saved AI result showed **Something to check** with the AI's list. **Report a problem** → Serious → the problem was saved and the part turned red.
  - **Send for review** too early: the list of missing checks appeared, and tapping one opened that check.
  - Problems page: plain status and the "Next:" line.
  - Home, Equipment and Problems at phone width: no sideways scrolling, and the menu fits.
- **Desktop (1280 px):** the model on the left; the step guide, progress and parts list on the right.

## Icons (follow-up)
Every action and status now has an icon next to its words, so it can be recognised at a glance, even by someone who
doesn't read English well. The icons come from [lucide-react](https://lucide.dev) 1.52.0; only the icons used are
bundled (about 9 KB gzipped).
- **Menu:** on phones it is a tab bar with the icon above the word.
- **Equipment types:**
  - Furniture: an armchair.
  - Electrical: a lightning bolt.
  - Fire safety: an extinguisher.
- **What to do, as a picture:** these appear in the step guide and on each check.
  - A camera means take a photo.
  - A hand means check it in person.
  - A pointing hand means it is your turn to choose.
  - Circular arrows mean take a new photo.
- **Result buttons:** ✓ Looks good, ⚠ Report a problem, ⊘ Doesn't apply.
- **Status chips (one icon per status, the same on every page):** ○ to do, ✓ done, ⚠ problem, ◌ partly done.
- **AI feedback:**
  - A ✓ means the photo is clear.
  - Circular arrows mean retake the photo.
  - An eye means something to check.
  - Practice material always shows the graduation-cap icon.
- **3D controls:** expand / shrink (separate parts / put back together), rotate-back (reset view), zoom (zoom to part), door open / closed.
- **Problems page:**
  - Each status has its own icon.
  - So does each next action: assign, save the fix, ask for a check, close, send back.
- **Review page:** approve, ask for changes, reject.
- **Dashboard:** each number tile has an icon.

The icons never replace the words: each one sits next to its label, and decorative icons are hidden from screen readers.

## Not done (worth doing next)
- ~~Spanish interface~~: done. The app opens in Spanish with an ES | EN switch; equipment content and AI feedback
  follow the language (see [LANGUAGES.md](LANGUAGES.md)).
- A test with real non-technical people on real phones (the walkthrough above was done by us, not by them).
- A screen-reader and keyboard pass, and a check in bright sunlight / high contrast.
- Import Studio and Dashboard were not simplified. They are for administrators and supervisors.
