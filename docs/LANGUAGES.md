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
| What people type: job titles, task descriptions, notes | Machine-translated into the other language when saved (`backend/app/translate.py`) |
| Saved AI photo reviews | Machine-translated into the other language right after the review, in a separate request, so the employer and the employee each read it in theirs |

Not translated: identifiers, part numbers, values and units; titles of files the employer uploads; the content of uploaded documents (answers are written in the reader's
language, the cited excerpts stay in the document's language).

## How it works
- The client sends `X-Lang: es|en` with every API call (`web/src/api.ts`); the server reads it per request.
- The AI always receives the original text as context; only its reply language changes. The no-certification rule
  also names the Spanish words it must never use (seguro, conforme, aprobado, listo, cargado…).
- `translations/` is excluded from the package content hash and checked by the package validator (unknown ids, lists
  that don't line up with the source).

## Typed text (machine translation)
- The interface language is taken as the writer's language. When a job, task or note is saved, the server stores
  that language (`lang`) and asks Claude Haiku (`TRANSLATE_MODEL`, default `claude-haiku-5-5`) for the other one in
  a single call per save, stored in `translations` (`{"es": {"title": "…"}}`).
- AI reviews keep both keys inside `ai_assessment`, but are not translated inside the photo upload: that request
  already waits on the review, and on Vercel it must finish within 60 s (the translation timeout there is 8 s,
  `TRANSLATE_TIMEOUT_S`). Instead the browser sends `POST /api/evidence/{id}/translate` as soon as the upload (or a
  "Try again" review) returns, without waiting for it; the review is normally in both languages before anyone else
  opens the job.
- Readers get their language; when that is a translation, the response carries `original` and the page shows
  "Translated · show original". The AI always receives the original text as context.
- If the translation call fails or the AI is off, the text is saved anyway and readers see the original. Opening the
  job in the other language fills in what is missing. `tools/translate_existing.py` fills in everything at once
  (useful for job lists after an outage, or for rows saved before this feature existed).

## Adding or correcting text
- **Interface:** wrap the English string in `t("…")` and add its Spanish to `es-app.ts` (or `es-server.ts` for a
  server message). In development, `window.__missingEs` in the browser console lists strings shown in Spanish mode
  without a translation.
- **Demo models:** edit `translations/es.json` in the package (same ids, lists in the same order), then
  `backend/.venv/bin/python tools/load_demo_media.py --replace` to store the new text. Note that `--replace` uploads
  the models again, so tasks linked to the old copies lose their link.

The previous inspection prototype also translated inspection requirements and saved Spanish practice results; those
features went away with that prototype (see git history before the Supabase rebuild).
