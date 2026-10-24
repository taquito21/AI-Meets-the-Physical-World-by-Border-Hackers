"""SQLite persistence. Schema mirrors the target PostgreSQL (Supabase) model; JSON columns are TEXT."""
from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from .config import settings

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
  started_at TEXT NOT NULL, submitted_at TEXT, decided_at TEXT, updated_at TEXT NOT NULL
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
  error TEXT, latency_ms INTEGER, created_at TEXT NOT NULL
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
  event_type TEXT NOT NULL, actor TEXT, metadata TEXT, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_items_inspection ON inspection_items(inspection_id);
CREATE INDEX IF NOT EXISTS ix_evidence_item ON evidence(inspection_item_id);
CREATE INDEX IF NOT EXISTS ix_findings_inspection ON findings(inspection_id);
CREATE INDEX IF NOT EXISTS ix_activity_entity ON activity_events(entity_type, entity_id);
"""

_write_lock = threading.Lock()


def now() -> str:
    # Millisecond precision so events within the same second keep their order.
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


# Columns added after the first release. Existing databases are upgraded in place (additive only).
MIGRATIONS: list[tuple[str, str, str]] = [
    ("components", "definition", "TEXT NOT NULL DEFAULT '{}'"),        # full component JSON (specs, articulation)
    ("inspections", "mode", "TEXT NOT NULL DEFAULT 'live'"),            # live | demo
    ("evidence_assessments", "origin", "TEXT NOT NULL DEFAULT 'live'"),  # live | precomputed
    ("evidence_assessments", "captured_at", "TEXT"),                    # when a precomputed result was produced
]


def init_db() -> None:
    with _connect(settings.db_path) as conn:
        conn.executescript(SCHEMA)
        for table, column, decl in MIGRATIONS:
            cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
            if column not in cols:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")


@contextmanager
def tx() -> Iterator[sqlite3.Connection]:
    """A serialized read-write transaction (SQLite allows one writer)."""
    with _write_lock:
        conn = _connect(settings.db_path)
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


@contextmanager
def read() -> Iterator[sqlite3.Connection]:
    conn = _connect(settings.db_path)
    try:
        yield conn
    finally:
        conn.close()


JSON_COLUMNS = {
    "manifest", "validation", "procedure", "model_node_ids", "explosion", "documents", "definition",
    "metadata", "requirement_snapshot", "image_checks", "result", "item_ids",
}
BOOL_COLUMNS = {"required", "manual_confirmed"}


def row(r: sqlite3.Row | None) -> dict[str, Any] | None:
    if r is None:
        return None
    out = dict(r)
    for k, v in out.items():
        if k in JSON_COLUMNS and isinstance(v, str):
            out[k] = json.loads(v)
        elif k in BOOL_COLUMNS and v is not None:
            out[k] = bool(v)
    return out


def rows(rs: list[sqlite3.Row]) -> list[dict[str, Any]]:
    return [row(r) for r in rs]  # type: ignore[misc]


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def log_event(conn: sqlite3.Connection, entity_type: str, entity_id: str, event_type: str,
              actor: str | None, metadata: dict | None = None) -> None:
    conn.execute(
        "INSERT INTO activity_events VALUES (?,?,?,?,?,?,?)",
        (new_id("evt"), entity_type, entity_id, event_type, actor, dumps(metadata or {}), now()),
    )
