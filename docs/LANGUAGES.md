# Languages (Spanish / English)

The app opens in **Spanish**. The **ES | EN** switch in the top bar changes the language on any screen, and the choice
is remembered on that device. Switching reloads the current page in the new language.

## What is translated, and where it comes from

| Text | Source |
|---|---|
| Buttons, menus, steps, statuses, help text | `web/src/i18n/` dictionaries (English text is the key; missing entries fall back to English) |
| Server messages (validation, "still missing", errors) | Sent in English, translated by the client dictionary (`es-server.ts`, incl. patterns for messages with values) |
| Equipment content: product and part names, check titles, instructions, "check that" lists, photo tips, safety notes, practice-photo captions, unit locations | `engineering-packages/<pkg>/translations/es.json`, applied by the server per request (`backend/app/i18n.py`) |
| AI feedback | The model is asked to write its free-text fields in the reader's language; the codes (`recommended_action`, etc.) stay fixed |
| Saved practice results (offline) | Real results captured separately per language: `precomputed_assessment` (English) and `precomputed_assessment_es` |

Not translated: identifiers, part numbers, serial numbers, values and units; text typed by people (notes, problem
descriptions, comments); the technical-sheet material field; server validation output in the admin Import Studio.

## How it works
- The client sends `X-Lang: es|en` with every API call. The server applies the package's translation file to the
  response only; the stored inspection snapshot and the engineering package stay exactly as published.
- `translations/` is excluded from the package content hash, like `demo-evidence/` and `reference-images/`, so adding
  or correcting a translation never creates a new engineering revision (covered by `backend/tests/test_i18n.py`).
- The AI always receives the published package text as context; only its reply language changes. The
  no-certification rule also names the Spanish words it must never use (seguro, conforme, aprobado, listo, cargado…).
- The package validator checks translation files: unknown component/requirement ids and lists that do not line up
  with the source are reported (`tools/validate_packages.py`).

## Adding or correcting text
- **Interface:** add the English string wrapped in `t("…")` and its Spanish in the dictionary for that area
  (`es-common`, `es-inspection`, `es-pages`, `es-review`, `es-server`). In development, `window.__missingEs` in the
  browser console lists strings shown in Spanish mode without a translation.
- **Equipment:** edit `translations/es.json` in the package (same ids, lists in the same order), then run
  `tools/validate_packages.py`. No data reset is needed.
- **Saved practice results in Spanish:**
  `backend/.venv/Scripts/python tools/precompute_demo_assessments.py engineering-packages/<pkg> --lang es [--force]`
  (real AI calls; nothing is written for a call that fails).

## Captured 2026-10-24
18 Spanish practice results (fire extinguisher 3, electrical panel 8, venue chair 7). 17 give the same verdict as the
English capture; the electrical panel's earth bar photo was "take another photo" in Spanish and "something to check"
in English (both cautious; normal model variation). None uses certification wording.
