"""Persistence. One small query interface with two backends:

- "supabase": Postgres through the Supabase REST API (PostgREST) over HTTPS, using the server-side secret key.
  The schema lives in backend/supabase/schema.sql and is applied once in the Supabase SQL editor.
- "local": SQLite in DATA_DIR (tests, offline development). The schema below mirrors schema.sql.

Callers express queries as table + equality/IN filters + order + limit; joins happen in Python. Every call is its
own transaction (that is what the REST API offers), so multi-step workflow writes use conditional updates
(`update(..., where={"status": expected})`) and unique indexes instead of a surrounding transaction.
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


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


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


# --------------------------------------------------------- local (SQLite) --

SCHEMA = """
CREATE TABLE IF NOT EXISTS manufacturers (
  id TEXT PRIMARY KEY, name TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS product_models (
  id TEXT PRIMARY KEY, manufacturer_id TEXT NOT NULL REFERENCES manufacturers(id),
  name TEXT NOT NULL, description TEXT
);
CREATE TABLE IF NOT EXISTS engineering_packages (
  id TEXT PRIMARY KEY, product_model_id TEXT NOT NULL REFERENCES product_models(id),
  revision TEXT NOT NULL, package_version TEXT NOT NULL, source_dir TEXT NOT NULL,
  manifest TEXT NOT NULL, content_hash TEXT NOT NULL, status TEXT NOT NULL,
  validation TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS product_revisions (
  id TEXT PRIMARY KEY, product_model_id TEXT NOT NULL REFERENCES product_models(id),
  revision TEXT NOT NULL, engineering_package_id TEXT NOT NULL REFERENCES engineering_packages(id),
  procedure TEXT NOT NULL, created_at TEXT NOT NULL,
  UNIQUE (product_model_id, revision)
);
CREATE TABLE IF NOT EXISTS components (
  product_revision_id TEXT NOT NULL REFERENCES product_revisions(id),
  id TEXT NOT NULL, parent_component_id TEXT, part_number TEXT NOT NULL, name TEXT NOT NULL,
  quantity INTEGER NOT NULL, category TEXT, material TEXT, description TEXT,
  model_node_ids TEXT NOT NULL, explosion TEXT NOT NULL, documents TEXT NOT NULL, sort INTEGER NOT NULL,
  definition TEXT NOT NULL DEFAULT '{}',
  PRIMARY KEY (product_revision_id, id)
);
CREATE TABLE IF NOT EXISTS inspection_requirements (
  product_revision_id TEXT NOT NULL REFERENCES product_revisions(id),
  id TEXT NOT NULL, component_id TEXT NOT NULL, title TEXT NOT NULL, instructions TEXT NOT NULL,
  evidence_type TEXT NOT NULL, required INTEGER NOT NULL, definition TEXT NOT NULL, sort INTEGER NOT NULL,
  PRIMARY KEY (product_revision_id, id)
);
CREATE TABLE IF NOT EXISTS product_instances (
  id TEXT PRIMARY KEY, product_model_id TEXT NOT NULL REFERENCES product_models(id),
  product_revision_id TEXT NOT NULL REFERENCES product_revisions(id),
  serial_number TEXT NOT NULL UNIQUE, metadata TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS inspections (
  id TEXT PRIMARY KEY, product_instance_id TEXT NOT NULL REFERENCES product_instances(id),
  product_revision_id TEXT NOT NULL REFERENCES product_revisions(id),
  procedure_id TEXT NOT NULL, inspector TEXT NOT NULL, status TEXT NOT NULL,
  started_at TEXT NOT NULL, submitted_at TEXT, decided_at TEXT, updated_at TEXT NOT NULL,
  mode TEXT NOT NULL DEFAULT 'live'
);
CREATE TABLE IF NOT EXISTS inspection_items (
  id TEXT PRIMARY KEY, inspection_id TEXT NOT NULL REFERENCES inspections(id),
  requirement_id TEXT NOT NULL, component_id TEXT NOT NULL,
  requirement_snapshot TEXT NOT NULL, required INTEGER NOT NULL, status TEXT NOT NULL, status_reason TEXT,
  observation TEXT, manual_confirmed INTEGER NOT NULL DEFAULT 0, override_note TEXT,
  decided_by TEXT, sort INTEGER NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS evidence (
  id TEXT PRIMARY KEY, inspection_id TEXT REFERENCES inspections(id),
  inspection_item_id TEXT REFERENCES inspection_items(id),
  finding_id TEXT, kind TEXT NOT NULL, storage_path TEXT NOT NULL, content_type TEXT NOT NULL,
  note TEXT, image_checks TEXT, submitted_by TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS evidence_assessments (
  id TEXT PRIMARY KEY, evidence_id TEXT NOT NULL REFERENCES evidence(id),
  provider TEXT NOT NULL, model TEXT, status TEXT NOT NULL, result TEXT,
  error TEXT, latency_ms INTEGER, created_at TEXT NOT NULL,
  origin TEXT NOT NULL DEFAULT 'live', captured_at TEXT
);
CREATE TABLE IF NOT EXISTS findings (
  id TEXT PRIMARY KEY, inspection_id TEXT NOT NULL REFERENCES inspections(id),
  product_instance_id TEXT NOT NULL, component_id TEXT NOT NULL, requirement_id TEXT,
  inspection_item_id TEXT, description TEXT NOT NULL, severity TEXT NOT NULL, status TEXT NOT NULL,
  assigned_to TEXT, created_by TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, closed_at TEXT
);
CREATE TABLE IF NOT EXISTS corrective_actions (
  id TEXT PRIMARY KEY, finding_id TEXT NOT NULL REFERENCES findings(id),
  assigned_to TEXT, description TEXT, status TEXT NOT NULL,
  recorded_by TEXT, verified_by TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS reviews (
  id TEXT PRIMARY KEY, inspection_id TEXT NOT NULL REFERENCES inspections(id),
  reviewer TEXT NOT NULL, decision TEXT NOT NULL, comments TEXT, item_ids TEXT, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS activity_events (
  id TEXT PRIMARY KEY, entity_type TEXT NOT NULL, entity_id TEXT NOT NULL,
  event_type TEXT NOT NULL, actor TEXT, metadata TEXT, created_at TEXT NOT NULL,
  inspection_id TEXT
);
CREATE INDEX IF NOT EXISTS ix_items_inspection ON inspection_items(inspection_id);
CREATE INDEX IF NOT EXISTS ix_evidence_item ON evidence(inspection_item_id);
CREATE INDEX IF NOT EXISTS ix_findings_inspection ON findings(inspection_id);
CREATE INDEX IF NOT EXISTS ix_activity_entity ON activity_events(entity_type, entity_id);
"""

# Run after MIGRATIONS so older databases have the columns these refer to.
POST_MIGRATION_SQL = [
    # Backfill the timeline column for events recorded before it existed.
    "UPDATE activity_events SET inspection_id = CASE WHEN entity_type = 'inspection' THEN entity_id "
    "ELSE json_extract(metadata, '$.inspection_id') END WHERE inspection_id IS NULL",
    "UPDATE activity_events SET inspection_id = (SELECT inspection_id FROM inspection_items i "
    "WHERE i.id = activity_events.entity_id) WHERE inspection_id IS NULL AND entity_type = 'inspection_item'",
    "CREATE INDEX IF NOT EXISTS ix_activity_inspection ON activity_events(inspection_id)",
    # At most one open (or awaiting-review) inspection per unit, even under concurrent starts.
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_inspections_open ON inspections(product_instance_id) "
    "WHERE status IN ('in_progress','changes_requested','submitted')",
]

# Columns added after the first release. Existing local databases are upgraded in place (additive only).
MIGRATIONS: list[tuple[str, str, str]] = [
    ("components", "definition", "TEXT NOT NULL DEFAULT '{}'"),        # full component JSON (specs, articulation)
    ("inspections", "mode", "TEXT NOT NULL DEFAULT 'live'"),            # live | demo
    ("evidence_assessments", "origin", "TEXT NOT NULL DEFAULT 'live'"),  # live | precomputed
    ("evidence_assessments", "captured_at", "TEXT"),                    # when a precomputed result was produced
    ("activity_events", "inspection_id", "TEXT"),                       # timeline lookup without JSON queries
]

JSON_COLUMNS = {
    "manifest", "validation", "procedure", "model_node_ids", "explosion", "documents", "definition",
    "metadata", "requirement_snapshot", "image_checks", "result", "item_ids",
}
BOOL_COLUMNS = {"required", "manual_confirmed"}


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
                for table, column, decl in MIGRATIONS:
                    cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
                    if column not in cols:
                        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")
                for sql in POST_MIGRATION_SQL:
                    try:
                        conn.execute(sql)
                    except sqlite3.IntegrityError as exc:  # old data that predates the rule
                        print(f"[db] skipped '{sql[:60]}…': {exc}", flush=True)
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
        self._request("GET", "/manufacturers", params={"select": "id", "limit": "1"})  # fails early if no schema

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
        self._request("DELETE", f"/{table}", params={"id": "not.is.null"}, headers={"Prefer": "return=minimal"})


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

# Children before parents (foreign keys). Used by tools/reset_demo_data.py and the opt-in Supabase test run.
TABLES_CHILD_FIRST = [
    "activity_events", "reviews", "corrective_actions", "evidence_assessments", "evidence", "findings",
    "inspection_items", "inspections", "product_instances", "inspection_requirements", "components",
    "product_revisions", "engineering_packages", "product_models", "manufacturers",
]


def reset_all() -> list[str]:
    """Delete every row (catalog included; packages reload on the next start). Returns stored photo paths."""
    paths = [e["storage_path"] for e in select("evidence", columns="storage_path")]
    for table in TABLES_CHILD_FIRST:
        store.clear(table)
    return paths


def first(table: str, where: Where | None = None, *, columns: str = "*", order: Order = None) -> dict[str, Any] | None:
    found = select(table, where, columns=columns, order=order, limit=1)
    return found[0] if found else None


def log_event(entity_type: str, entity_id: str, event_type: str, actor: str | None,
              metadata: dict | None = None, *, inspection_id: str | None = None) -> None:
    metadata = metadata or {}
    if inspection_id is None:
        inspection_id = entity_id if entity_type == "inspection" else metadata.get("inspection_id")
    insert("activity_events", {
        "id": new_id("evt"), "entity_type": entity_type, "entity_id": entity_id, "event_type": event_type,
        "actor": actor, "metadata": metadata, "created_at": now(), "inspection_id": inspection_id})
