"""Add English and Spanish translations to jobs, tasks, notes and AI reviews saved without them.

New text is translated when it is saved, and a job's missing translations are filled in when someone opens it, so
this is only needed for job lists and dashboards right after rows were saved without translations (before the
feature existed, or while the AI was unavailable). Safe to re-run: rows that already have a translation are skipped.

Usage:
    backend/.venv/bin/python tools/translate_existing.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app import ai, db, translate  # noqa: E402

BATCH = 40  # rows per model call

if __name__ == "__main__":
    ok, why = ai.claude_available()
    if not ok:
        sys.exit(why)
    for table in ("jobs", "tasks", "evidence"):
        rows = db.select(table)
        done = 0
        for target in ("en", "es"):
            for i in range(0, len(rows), BATCH):
                changed = translate.fill([(table, r) for r in rows[i:i + BATCH]], target)
                translate.save(changed)
                done += len(changed)
        print(f"{table}: {len(rows)} rows, {done} translations added")
