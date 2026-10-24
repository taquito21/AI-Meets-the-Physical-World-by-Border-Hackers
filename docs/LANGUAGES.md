# Languages (Spanish / English)

The app opens in **Spanish**. The **ES | EN** switch (top bar, and on the login screen) changes the language on any
screen, and the choice is remembered on that device. Switching reloads the current page in the new language.

## What is translated, and where it comes from

| Text | Source |
|---|---|
| Buttons, menus, statuses, help text | `web/src/i18n/es-app.ts` (English text is the key; missing entries fall back to English) |
| Server messages (validation, access, errors) | Sent in English, translated by the client dictionary `web/src/i18n/es-server.ts` (incl. patterns for messages with values) |
| Demo 3D models: product name, part names, descriptions, specs | `engineering-packages/<pkg>/translations/es.json`, stored with the model by `tools/load_demo_media.py` and applied per request by the server (`backend/app/i18n.py`) |
| AI photo review and document answers | The model is asked to reply in the reader's language; codes (`recommended_action`, etc.) stay fixed |

Not translated: identifiers, part numbers, values and units; anything people type (job titles, task descriptions,
notes); titles of files the employer uploads; the content of uploaded documents (answers are written in the reader's
language, the cited excerpts stay in the document's language).

## How it works
- The client sends `X-Lang: es|en` with every API call (`web/src/api.ts`); the server reads it per request.
- The AI always receives the original text as context; only its reply language changes. The no-certification rule
  also names the Spanish words it must never use (seguro, conforme, aprobado, listo, cargado…).
- `translations/` is excluded from the package content hash and checked by the package validator (unknown ids, lists
  that don't line up with the source).

## Adding or correcting text
- **Interface:** wrap the English string in `t("…")` and add its Spanish to `es-app.ts` (or `es-server.ts` for a
  server message). In development, `window.__missingEs` in the browser console lists strings shown in Spanish mode
  without a translation.
- **Demo models:** edit `translations/es.json` in the package (same ids, lists in the same order), then
  `backend/.venv/bin/python tools/load_demo_media.py --replace` to store the new text. Note that `--replace` uploads
  the models again, so tasks linked to the old copies lose their link.

The previous inspection prototype also translated inspection requirements and saved Spanish practice results; those
features went away with that prototype (see git history before the Supabase rebuild).
