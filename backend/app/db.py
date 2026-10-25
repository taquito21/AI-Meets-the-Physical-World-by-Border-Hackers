"""Persistence. One small query interface with two backends:

- "supabase": Postgres through the Supabase REST API (PostgREST) over HTTPS, using the server-side secret key.
  The schema lives in backend/supabase/schema.sql and is applied once in the Supabase SQL editor.
- "local": SQLite in DATA_DIR, used by the tests. The schema below mirrors schema.sql (minus Supabase Auth and
  pgvector: embeddings are stored as JSON text and searched in Python).

Callers express queries as table + equality/IN filters + order + limit; joins happen in Python. Every call is its
own transaction (that is what the REST API offers): validate first, then write, children after parents.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Protocol

import httpx

from .config import settings

Where = dict[str, Any]  # column -> value (equals), None (is null), or a list/tuple/set (in)
Order = str | list[str] | None  # "created_at" ascending, "-created_at" descending


class Conflict(Exception):
    """A unique constraint was violated (e.g. a second open inspection for the same unit)."""


class SchemaMissing(RuntimeError):
    pass


# ------------------------------------------------------------------ helpers --

_clock_lock = threading.Lock()
_last_ts: datetime | None = None


def now() -> str:
    """UTC ISO timestamp, strictly increasing within this process so events keep their order."""
    global _last_ts
    with _clock_lock:
        ts = datetime.now(timezone.utc)
        if _last_ts and ts <= _last_ts:
            ts = _last_ts + timedelta(microseconds=1)
        _last_ts = ts
    return ts.isoformat(timespec="microseconds")


def ts_key(value: str | None) -> datetime:
    """Sort key for timestamps merged in Python (Postgres drops trailing zero fractions)."""
    return datetime.fromisoformat(value) if value else datetime.min.replace(tzinfo=timezone.utc)


def new_id() -> str:
    return str(uuid.uuid4())


def _orders(order: Order) -> list[tuple[str, bool]]:
    if not order:
        return []
    items = [order] if isinstance(order, str) else order
    return [(o.lstrip("-"), o.startswith("-")) for o in items]


def _is_multi(value: Any) -> bool:
    return isinstance(value, (list, tuple, set, frozenset))


def _empty_in(where: Where | None) -> bool:
    return any(_is_multi(v) and not v for v in (where or {}).values())


class Store(Protocol):
    name: str

    def init(self) -> None: ...
    def select(self, table: str, where: Where | None = None, *, columns: str = "*", order: Order = None,
               limit: int | None = None) -> list[dict[str, Any]]: ...
    def count(self, table: str, where: Where | None = None) -> int: ...
    def insert(self, table: str, rows: dict | list[dict], *, ignore_duplicates_on: str | None = None) -> None: ...
    def upsert(self, table: str, rows: dict | list[dict], *, on_conflict: str) -> None: ...
    def update(self, table: str, values: dict[str, Any], where: Where) -> list[dict[str, Any]]: ...
    def delete(self, table: str, where: Where) -> None: ...
    def clear(self, table: str) -> None: ...
    def rpc(self, name: str, params: dict[str, Any]) -> list[dict[str, Any]]: ...


# --------------------------------------------------------- local (SQLite) --

SCHEMA = """
CREATE TABLE IF NOT EXISTS companies (
  id TEXT PRIMARY KEY, name TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY, company_id TEXT NOT NULL REFERENCES companies(id), username TEXT NOT NULL,
  user_class TEXT NOT NULL CHECK (user_class IN ('employer', 'employee'))
);
CREATE TABLE IF NOT EXISTS jobs (
  id TEXT PRIMARY KEY, company_id TEXT NOT NULL REFERENCES companies(id),
  assigned_to TEXT NOT NULL REFERENCES users(id), title TEXT NOT NULL, due_date TEXT, created_at TEXT NOT NULL,
  lang TEXT, translations TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS tasks (
  id TEXT PRIMARY KEY, job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE, position INTEGER NOT NULL,
  description TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'passed', 'failed', 'flagged')),
  updated_at TEXT NOT NULL, lang TEXT, translations TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS evidence (
  id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
  created_by TEXT NOT NULL REFERENCES users(id), photo_path TEXT, text TEXT, ai_assessment TEXT,
  created_at TEXT NOT NULL, lang TEXT, translations TEXT NOT NULL DEFAULT '{}',
  CHECK (photo_path IS NOT NULL OR text IS NOT NULL)
);
CREATE TABLE IF NOT EXISTS media (
  id TEXT PRIMARY KEY, company_id TEXT NOT NULL REFERENCES companies(id),
  kind TEXT NOT NULL CHECK (kind IN ('model_3d', 'document', 'image')), title TEXT NOT NULL,
  storage_path TEXT NOT NULL, metadata TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS task_media (
  task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
  media_id TEXT NOT NULL REFERENCES media(id) ON DELETE CASCADE,
  node_ids TEXT NOT NULL DEFAULT '[]', PRIMARY KEY (task_id, media_id)
);
CREATE TABLE IF NOT EXISTS document_chunks (
  id TEXT PRIMARY KEY, company_id TEXT NOT NULL REFERENCES companies(id),
  media_id TEXT NOT NULL REFERENCES media(id) ON DELETE CASCADE, chunk_index INTEGER NOT NULL,
  content TEXT NOT NULL, embedding TEXT NOT NULL, UNIQUE (media_id, chunk_index)
);
CREATE TABLE IF NOT EXISTS face_embeddings (
  user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE, embeddings TEXT NOT NULL,
  consent_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
"""

# Decoded from / encoded to JSON text by the SQLite store (Postgres uses jsonb and does this itself).
JSON_COLUMNS = {"ai_assessment", "metadata", "node_ids", "embeddings", "translations"}
# Columns added after the first release, for local databases created before them.
ADDED_COLUMNS = {table: {"lang": "TEXT", "translations": "TEXT NOT NULL DEFAULT '{}'"}
                 for table in ("jobs", "tasks", "evidence")}
BOOL_COLUMNS: set[str] = set()


class SqliteStore:
    name = "local"

    def __init__(self, path: Path):
        self.path = path
        self._write_lock = threading.Lock()

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path, timeout=15)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    def _write(self, sql: str, args: Iterable = (), many: bool = False) -> list[sqlite3.Row]:
        with self._write_lock:
            conn = self._connect()
            try:
                conn.execute("BEGIN IMMEDIATE")
                cur = conn.executemany(sql, args) if many else conn.execute(sql, tuple(args))
                fetched = cur.fetchall() if cur.description else []
                conn.commit()
                return fetched
            except sqlite3.IntegrityError as exc:
                conn.rollback()
                if "UNIQUE" in str(exc) or "PRIMARY KEY" in str(exc):
                    raise Conflict(str(exc)) from exc
                raise
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

    def init(self) -> None:
        with self._write_lock:
            conn = self._connect()
            try:
                conn.executescript(SCHEMA)
                for table, columns in ADDED_COLUMNS.items():
                    have = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
                    for name, decl in columns.items():
                        if name not in have:
                            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")
                conn.commit()
            finally:
                conn.close()

    @staticmethod
    def _decode(r: sqlite3.Row) -> dict[str, Any]:
        out = dict(r)
        for k, v in out.items():
            if k in JSON_COLUMNS and isinstance(v, str):
                out[k] = json.loads(v)
            elif k in BOOL_COLUMNS and v is not None:
                out[k] = bool(v)
        return out

    @staticmethod
    def _encode(row: dict[str, Any]) -> dict[str, Any]:
        out = {}
        for k, v in row.items():
            if k in JSON_COLUMNS and v is not None:
                out[k] = json.dumps(v, ensure_ascii=False)
            elif isinstance(v, bool):
                out[k] = int(v)
            else:
                out[k] = v
        return out

    @staticmethod
    def _where(where: Where | None) -> tuple[str, list[Any]]:
        parts, args = [], []
        for col, val in (where or {}).items():
            if val is None:
                parts.append(f"{col} IS NULL")
            elif _is_multi(val):
                vals = list(val)
                parts.append(f"{col} IN ({','.join('?' * len(vals))})")
                args.extend(vals)
            else:
                parts.append(f"{col} = ?")
                args.append(int(val) if isinstance(val, bool) else val)
        return (" WHERE " + " AND ".join(parts) if parts else ""), args

    def select(self, table, where=None, *, columns="*", order=None, limit=None):
        if _empty_in(where):
            return []
        clause, args = self._where(where)
        sql = f"SELECT {columns} FROM {table}{clause}"
        if order:
            sql += " ORDER BY " + ", ".join(f"{c} {'DESC' if d else 'ASC'}" for c, d in _orders(order))
        if limit is not None:
            sql += f" LIMIT {int(limit)}"
        conn = self._connect()
        try:
            return [self._decode(r) for r in conn.execute(sql, args).fetchall()]
        finally:
            conn.close()

    def count(self, table, where=None):
        if _empty_in(where):
            return 0
        clause, args = self._where(where)
        conn = self._connect()
        try:
            return conn.execute(f"SELECT COUNT(*) FROM {table}{clause}", args).fetchone()[0]
        finally:
            conn.close()

    def _insert(self, table, rows, suffix):
        rows = [self._encode(r) for r in ([rows] if isinstance(rows, dict) else rows)]
        if not rows:
            return
        cols = list(rows[0])
        sql = f"INSERT INTO {table} ({','.join(cols)}) VALUES ({','.join('?' * len(cols))}){suffix}"
        self._write(sql, [tuple(r[c] for c in cols) for r in rows], many=True)

    def insert(self, table, rows, *, ignore_duplicates_on=None):
        self._insert(table, rows, f" ON CONFLICT({ignore_duplicates_on}) DO NOTHING" if ignore_duplicates_on else "")

    def upsert(self, table, rows, *, on_conflict):
        sample = rows if isinstance(rows, dict) else (rows[0] if rows else {})
        keys = {k.strip() for k in on_conflict.split(",")}
        sets = ", ".join(f"{c}=excluded.{c}" for c in sample if c not in keys)
        self._insert(table, rows, f" ON CONFLICT({on_conflict}) DO UPDATE SET {sets}")

    def update(self, table, values, where):
        if _empty_in(where):
            return []
        clause, args = self._where(where)
        enc = self._encode(values)
        sets = ", ".join(f"{c} = ?" for c in enc)
        return [self._decode(r) for r in self._write(f"UPDATE {table} SET {sets}{clause} RETURNING *",
                                                     list(enc.values()) + args)]

    def delete(self, table, where):
        if _empty_in(where):
            return
        clause, args = self._where(where)
        self._write(f"DELETE FROM {table}{clause}", args)

    def clear(self, table):
        self._write(f"DELETE FROM {table}")

    def rpc(self, name, params):
        """Python versions of the Postgres functions in schema.sql (local backend only)."""
        if name != "match_document_chunks":
            raise ValueError(f"unknown function {name}")
        query = json.loads(params["p_query_embedding"])
        out = []
        for c in self.select("document_chunks", {"company_id": params["p_company_id"]}):
            vec = json.loads(c["embedding"])
            dot = sum(a * b for a, b in zip(vec, query))
            norm = (sum(a * a for a in vec) ** 0.5) * (sum(b * b for b in query) ** 0.5) or 1.0
            out.append({k: c[k] for k in ("id", "media_id", "chunk_index", "content")} | {"similarity": dot / norm})
        out.sort(key=lambda r: r["similarity"], reverse=True)
        return out[:params.get("p_match_count", 5)]


# ------------------------------------------------- supabase (REST / HTTPS) --

class RestStore:
    """PostgREST client. Uses the secret key, so row-level security is bypassed server-side only."""
    name = "supabase"
    MAX_IN = 80  # keep long IN lists inside URL limits by splitting them

    def __init__(self, url: str, key: str):
        self.client = httpx.Client(
            base_url=f"{url}/rest/v1", timeout=20,
            headers={"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"})

    @staticmethod
    def _literal(v: Any) -> str:
        if isinstance(v, bool):
            return "true" if v else "false"
        return str(v)

    @classmethod
    def _quoted(cls, v: Any) -> str:
        s = cls._literal(v).replace("\\", "\\\\").replace('"', '\\"')
        return f'"{s}"'

    @classmethod
    def _params(cls, where: Where | None) -> list[tuple[str, str]]:
        params = []
        for col, val in (where or {}).items():
            if val is None:
                params.append((col, "is.null"))
            elif _is_multi(val):
                params.append((col, "in.(" + ",".join(cls._quoted(v) for v in val) + ")"))
            else:
                params.append((col, "eq." + cls._literal(val)))
        return params

    def _check(self, resp: httpx.Response) -> httpx.Response:
        if resp.status_code < 400:
            return resp
        try:
            body = resp.json()
        except ValueError:
            body = {"message": resp.text}
        code, message = body.get("code"), body.get("message") or resp.text
        if code == "23505":
            raise Conflict(message)
        if code in ("PGRST205", "42P01", "PGRST204", "42703"):
            raise SchemaMissing(f"{message}. Apply backend/supabase/schema.sql in the Supabase SQL editor.")
        raise RuntimeError(f"Supabase REST {resp.status_code}: {message}")

    def _request(self, method: str, path: str, **kw) -> httpx.Response:
        try:
            return self._check(self.client.request(method, path, **kw))
        except httpx.TransportError:
            if method != "GET":
                raise
            return self._check(self.client.request(method, path, **kw))  # one retry for reads

    def _split(self, where: Where | None) -> list[Where | None]:
        """Split the first oversized IN filter into several queries."""
        for col, val in (where or {}).items():
            if _is_multi(val) and len(val) > self.MAX_IN:
                vals = list(val)
                return [{**where, col: vals[i:i + self.MAX_IN]} for i in range(0, len(vals), self.MAX_IN)]
        return [where]

    def init(self) -> None:
        self._request("GET", "/companies", params={"select": "id", "limit": "1"})  # fails early if no schema

    def select(self, table, where=None, *, columns="*", order=None, limit=None):
        if _empty_in(where):
            return []
        parts = self._split(where)
        out: list[dict[str, Any]] = []
        for w in parts:
            params = [("select", columns.replace(" ", ""))] + self._params(w)
            if order:
                params.append(("order", ",".join(f"{c}.{'desc' if d else 'asc'}" for c, d in _orders(order))))
            if limit is not None:
                params.append(("limit", str(int(limit))))
            out.extend(self._request("GET", f"/{table}", params=params).json())
        if len(parts) > 1:  # chunks were each ordered/limited; restore the overall order and limit
            for c, d in reversed(_orders(order)):
                out.sort(key=lambda r: (r.get(c) is None, r.get(c)), reverse=d)
            out = out[:limit] if limit is not None else out
        return out

    def count(self, table, where=None):
        if _empty_in(where):
            return 0
        total = 0
        for w in self._split(where):
            resp = self._request("HEAD", f"/{table}", params=[("select", "*")] + self._params(w),
                                 headers={"Prefer": "count=exact"})
            total += int(resp.headers.get("content-range", "*/0").split("/")[-1])
        return total

    def _post(self, table, rows, prefer, on_conflict=None):
        rows = [rows] if isinstance(rows, dict) else rows
        if not rows:
            return
        params = {"on_conflict": on_conflict} if on_conflict else None
        self._request("POST", f"/{table}", params=params, content=json.dumps(rows, ensure_ascii=False),
                      headers={"Prefer": prefer})

    def insert(self, table, rows, *, ignore_duplicates_on=None):
        if ignore_duplicates_on:
            self._post(table, rows, "return=minimal,resolution=ignore-duplicates", ignore_duplicates_on)
        else:
            self._post(table, rows, "return=minimal")

    def upsert(self, table, rows, *, on_conflict):
        self._post(table, rows, "return=minimal,resolution=merge-duplicates", on_conflict)

    def update(self, table, values, where):
        if not where:
            raise ValueError("update without a filter")
        if _empty_in(where):
            return []
        out = []
        for w in self._split(where):
            out.extend(self._request("PATCH", f"/{table}", params=self._params(w),
                                     content=json.dumps(values, ensure_ascii=False),
                                     headers={"Prefer": "return=representation"}).json())
        return out

    def delete(self, table, where):
        if not where:
            raise ValueError("delete without a filter")
        if _empty_in(where):
            return
        for w in self._split(where):
            self._request("DELETE", f"/{table}", params=self._params(w), headers={"Prefer": "return=minimal"})

    def clear(self, table):
        key = "task_id" if table == "task_media" else "id"  # every other table has an id column
        self._request("DELETE", f"/{table}", params={key: "not.is.null"}, headers={"Prefer": "return=minimal"})

    def rpc(self, name, params):
        return self._request("POST", f"/rpc/{name}", content=json.dumps(params)).json()


# ---------------------------------------------------------------- facade --

def _make_store() -> Store:
    if settings.data_backend == "supabase":
        if not (settings.supabase_url and settings.supabase_secret_key):
            raise RuntimeError("DATA_BACKEND=supabase needs SUPABASE_URL and SUPABASE_SECRET_KEY")
        return RestStore(settings.supabase_url, settings.supabase_secret_key)
    return SqliteStore(settings.db_path)


store: Store = _make_store()

init_db = store.init
select = store.select
count = store.count
insert = store.insert
upsert = store.upsert
update = store.update
delete = store.delete
rpc = store.rpc

# Children before parents (foreign keys). Used by tools/reset_demo_data.py and the opt-in Supabase test run.
TABLES_CHILD_FIRST = ["face_embeddings", "document_chunks", "task_media", "evidence", "tasks", "jobs", "media", "users", "companies"]


def first(table: str, where: Where | None = None, *, columns: str = "*", order: Order = None) -> dict[str, Any] | None:
    found = select(table, where, columns=columns, order=order, limit=1)
    return found[0] if found else None


def reset_all(include_accounts: bool = False) -> list[str]:
    """Delete jobs, tasks, evidence and media (plus companies and user profiles when include_accounts).
    Returns the storage paths of the deleted files so the caller can remove them from storage."""
    paths = [e["photo_path"] for e in select("evidence", columns="photo_path") if e["photo_path"]]
    paths += [m["storage_path"] for m in select("media", columns="storage_path")]
    for table in TABLES_CHILD_FIRST:
        if include_accounts or table not in ("users", "companies"):
            store.clear(table)
    return paths
