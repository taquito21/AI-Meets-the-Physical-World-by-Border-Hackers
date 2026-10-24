# Architecture

```
 Phone / laptop browser ──HTTPS──► FastAPI backend ──HTTPS (REST)──► Supabase: Postgres + Storage + Auth
 React + R3F web client              ├─ auth.py      verify login token (JWKS), load profile
   login via supabase-js             ├─ workflow.py  access rules, jobs/tasks/evidence
   jobs, tasks, 3D viewer            ├─ media.py     uploads (.glb/.pdf/.txt/images)
                                     ├─ rag.py       document search ──► Voyage AI (embeddings)
                                     ├─ ai.py        photo review + answers ──► Claude
                                     └─ db.py / blobs.py   data + file access (Supabase or local SQLite for tests)
```

## Data model (backend/supabase/schema.sql)
`companies` 1─n `users` (one per login: employer | employee) · `companies` 1─n `jobs` (assigned to one employee)
1─n `tasks` (ordered; pending | passed | failed | flagged) 1─n `evidence` (photo and/or text, AI review) ·
`companies` 1─n `media` (3D models, documents, images) n─n `tasks` via `task_media` (with the model parts the task
is about) · `media` 1─n `document_chunks` (text + embedding, for search).

## Key decisions (and why)

| Decision | Rationale |
|---|---|
| **Supabase through its REST API** | The venue Wi-Fi only allows HTTPS, so the backend reaches Postgres and Storage through the Supabase REST API instead of a direct connection. All data access goes through `db.py` (one small interface), so a direct Postgres driver can be added later in that one file. See [DATABASE.md](DATABASE.md). |
| **Supabase Auth, verified by the backend** | The browser logs in with supabase-js and sends the access token; the backend verifies it locally with the project's public keys. Row-level security is on with no policies, so the browser's publishable key can't read any table: all data goes through the backend, which enforces the rules in `workflow.py`. |
| **Company is the isolation boundary** | Every job, media item and document chunk has a `company_id`; every query filters on the user's company. Requests for another company's ids answer 404. |
| **Statuses are set by people** | The AI photo review is advisory and stored on the evidence row. Only the worker or employer sets a task's status; `flagged` escalates to the employer. |
| **Signed URLs for files** | Photos and models are in a private bucket. The API returns one-hour signed links after its access check, so the browser downloads directly from Supabase (no large responses through the backend). |
| **Document search with Voyage + Claude** | Uploaded PDFs/text are chunked and embedded with Voyage AI (`voyage-4`, 1024 dimensions); a question is embedded, matched by `match_document_chunks` within the user's company, and answered by Claude with citations to document and page. |
| **3D parts from the model's parts list** | A 3D model's `metadata.parts` holds part ids, mesh node names, explosion vectors and specs. The demo models keep their full engineering parts list; uploaded `.glb` files get one part per mesh node. |

## AI integration
`ai.AnthropicProvider` sends the normalized JPEG (EXIF-stripped, ≤1568 px) with the job, task and linked parts as
context. It uses structured output (JSON schema) validated with Pydantic, and stores `failed` / `refused` /
`unavailable` instead of inventing a result. Document answers (`rag.answer`) send the retrieved chunks as
citation-enabled documents. Both use `AI_MODEL` (default `claude-opus-5-5`) at `AI_EFFORT` (default `low`) with
the server-side refusal fallback (`AI_FALLBACKS=false` turns it off). Keys live only in `backend/.env`.
