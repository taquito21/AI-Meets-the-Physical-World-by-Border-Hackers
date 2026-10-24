-- Field Assistant: Postgres schema for Supabase.
-- Apply once: Supabase dashboard -> SQL Editor -> New query -> paste this file -> Run. Safe to re-run.
--
-- Model: a company has one employer and its employees. The employer creates jobs, each assigned to one employee,
-- with n ordered tasks. Employees record evidence (photo and/or text) on tasks and set each task to passed,
-- failed or flagged (flagged = escalated to the employer, who answers with a text evidence entry).
-- Media (3D models, documents, images) belong to the company and can be linked to tasks. Documents are chunked
-- and embedded for retrieval (RAG), always filtered by company.
--
-- The backend reaches these tables through the Supabase REST API with the SECRET key, which bypasses row-level
-- security. RLS is enabled with no policies, so the publishable key (shipped to browsers) can neither read nor
-- write any table; browsers only use it to log in.

create extension if not exists vector with schema extensions;

create table if not exists companies (
  id uuid primary key default gen_random_uuid(),
  name text not null
);

-- One row per login. id is the Supabase Auth user id.
create table if not exists users (
  id uuid primary key references auth.users(id) on delete cascade,
  company_id uuid not null references companies(id),
  username text not null,
  user_class text not null check (user_class in ('employer', 'employee'))
);

create table if not exists jobs (
  id uuid primary key default gen_random_uuid(),
  company_id uuid not null references companies(id),
  assigned_to uuid not null references users(id),
  title text not null,
  due_date date,  -- optional; a job is overdue when this has passed and it still has open tasks
  created_at timestamptz not null default now()
);
alter table jobs add column if not exists due_date date;  -- for projects created before due dates existed

create table if not exists tasks (
  id uuid primary key default gen_random_uuid(),
  job_id uuid not null references jobs(id) on delete cascade,
  position integer not null,
  description text not null,
  status text not null default 'pending' check (status in ('pending', 'passed', 'failed', 'flagged')),
  updated_at timestamptz not null default now()
);

-- A photo, a text entry, or both. ai_assessment is null until a photo has been assessed.
create table if not exists evidence (
  id uuid primary key default gen_random_uuid(),
  task_id uuid not null references tasks(id) on delete cascade,
  created_by uuid not null references users(id),
  photo_path text,
  text text,
  ai_assessment jsonb,
  created_at timestamptz not null default now(),
  check (photo_path is not null or text is not null)
);

-- metadata holds kind-specific data, e.g. a 3D model's parts list (names, specs, explosion vectors).
create table if not exists media (
  id uuid primary key default gen_random_uuid(),
  company_id uuid not null references companies(id),
  kind text not null check (kind in ('model_3d', 'document', 'image')),
  title text not null,
  storage_path text not null,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

-- node_ids: the parts of a 3D model this task is about (highlighted in the viewer); empty = the whole model.
create table if not exists task_media (
  task_id uuid not null references tasks(id) on delete cascade,
  media_id uuid not null references media(id) on delete cascade,
  node_ids jsonb not null default '[]'::jsonb,
  primary key (task_id, media_id)
);

-- RAG. The vector size must match the embedding model (change it while the table is empty).
create table if not exists document_chunks (
  id uuid primary key default gen_random_uuid(),
  company_id uuid not null references companies(id),
  media_id uuid not null references media(id) on delete cascade,
  chunk_index integer not null,
  content text not null,
  embedding extensions.vector(1024) not null,
  unique (media_id, chunk_index)
);

create index if not exists ix_users_company on users(company_id);
create index if not exists ix_jobs_company on jobs(company_id);
create index if not exists ix_jobs_assigned on jobs(assigned_to);
create index if not exists ix_tasks_job on tasks(job_id, position);
create index if not exists ix_evidence_task on evidence(task_id, created_at);
create index if not exists ix_media_company on media(company_id);
create index if not exists ix_task_media_media on task_media(media_id);
create index if not exists ix_chunks_company on document_chunks(company_id);
create index if not exists ix_chunks_embedding on document_chunks
  using hnsw (embedding extensions.vector_cosine_ops);

-- Similarity search for one company (the REST API cannot order by vector distance, so it calls this via /rpc).
create or replace function match_document_chunks(
  p_company_id uuid, p_query_embedding extensions.vector(1024), p_match_count integer default 5)
returns table (id uuid, media_id uuid, chunk_index integer, content text, similarity double precision)
language sql stable
set search_path = public, extensions
as $$
  select c.id, c.media_id, c.chunk_index, c.content, 1 - (c.embedding <=> p_query_embedding) as similarity
  from document_chunks c
  where c.company_id = p_company_id
  order by c.embedding <=> p_query_embedding
  limit p_match_count;
$$;
revoke execute on function match_document_chunks(uuid, extensions.vector, integer) from public, anon, authenticated;
grant execute on function match_document_chunks(uuid, extensions.vector, integer) to service_role;

-- Lock every table to the backend (secret key) only.
alter table companies enable row level security;
alter table users enable row level security;
alter table jobs enable row level security;
alter table tasks enable row level security;
alter table evidence enable row level security;
alter table media enable row level security;
alter table task_media enable row level security;
alter table document_chunks enable row level security;

-- One private bucket for all files, organized as <company_id>/evidence/... and <company_id>/media/...
-- Files are served only through the API, never through public URLs.
insert into storage.buckets (id, name, public)
values ('files', 'files', false)
on conflict (id) do nothing;
