# API contracts

The live OpenAPI schema is at `http://<host>:8000/docs` (`/openapi.json`). Bodies are JSON unless noted.
Errors return `{"detail": str}`: `401` not logged in or expired, `403` wrong role, `404` not found **or not
visible to you** (other company, or a job not assigned to you), `409` conflict, `415` file type, `422` validation,
`503` a service is not configured (AI, document search, login keys).

**Login:** the web client signs in with Supabase Auth (email + password) and sends
`Authorization: Bearer <access token>` on every call. The backend verifies the token against the project's public
keys and loads the profile from `users`.

| Method | Path | Who | Purpose |
|---|---|---|---|
| GET | `/api/health` | anyone | Version, data backend, AI and document search availability |
| GET | `/api/config` | anyone | Supabase URL + publishable key for the browser login |
| GET | `/api/me` | logged in | Profile: `id, username, user_class, company_id, company{id,name}` |
| GET | `/api/users` | logged in | People in your company (for assigning jobs) |
| GET | `/api/jobs` | logged in | Employer: all company jobs. Employee: jobs assigned to them. Each with `counts` per task status, `due_date`, `finished`; open jobs first, soonest due date first |
| GET | `/api/dashboard` | employer | `{jobs, attention, team}`: every job, the flagged and failed tasks (with job title and employee), and each employee's open jobs and tasks done |
| POST | `/api/jobs` `{title, assigned_to, due_date?, tasks:[{description, media:[{media_id, node_ids}]}]}` | employer | Create a job (`due_date` as `YYYY-MM-DD`); returns the job detail |
| GET | `/api/jobs/{id}` | logged in | Job detail: tasks in order, each with `evidence` and linked `media` (signed URLs) |
| DELETE | `/api/jobs/{id}` | employer | Delete the job, its tasks, evidence and photos |
| POST | `/api/tasks/{id}/status` `{status}` | logged in | `pending`, `passed`, `failed` or `flagged`; returns the job detail |
| POST | `/api/tasks/{id}/evidence` *(multipart: file?, text?, assess?)* | logged in | Photo and/or note. Photos get image checks + the AI review unless `assess=false`; returns the job detail |
| POST | `/api/evidence/{id}/assess` | logged in | Re-run the AI review of a photo |
| GET | `/api/media` | employer | Company media library (signed URLs, searchable chunk counts) |
| POST | `/api/media` *(multipart: file, title?)* | employer | Upload `.glb`, `.pdf`, `.txt`, `.jpg/.png/.webp`. Documents are indexed for search; the response's `indexing` says whether that worked |
| DELETE | `/api/media/{id}` | employer | Delete a file, its search chunks and task links |
| POST | `/api/ask` `{question}` | logged in | Answer from the company's documents: `{answer, sources:[{n, title, page, cited_text}]}` |

## Shapes
- **Jobs:** `finished` is true when no task is `pending` or `flagged`. The web client marks an unfinished job as
  overdue when its `due_date` has passed (in the viewer's own time zone).
- **Task status** is set only by people. `flagged` = escalated to the employer, who replies with a text evidence
  entry and then sets `passed` or `failed`.
- **Evidence:** `{id, task_id, created_by{id,username,user_class}, text, photo_url, ai_assessment, created_at}`.
  `ai_assessment` is `{status: completed|unavailable|failed|refused, provider, model, result, error, latency_ms,
  image_checks}`. `result` follows `AssessmentResult` in `backend/app/ai.py` (advisory, never a certification).
- **Media:** `{id, title, kind: model_3d|document|image, url, metadata, created_at}`. For 3D models,
  `metadata.parts` lists the selectable parts (`id, name, model_node_ids, explosion, articulation, specs...`);
  a task's `node_ids` are part ids from that list.
- **Signed URLs** (photos, media) expire after one hour; reload the job to get fresh ones.
