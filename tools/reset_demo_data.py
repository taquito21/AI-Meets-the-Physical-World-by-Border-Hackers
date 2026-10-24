"""Delete all demo data: inspections, evidence photos, findings and the loaded catalog (development only).

Released engineering revisions are immutable once loaded. While adapting the demo
packages (e.g. after venue photographs), reset the demo data so the edited revision A
can be loaded fresh. Packages are re-imported automatically on the next server start.

Works on the configured backend (DATA_BACKEND in backend/.env):
- local: deletes backend/data (SQLite + photo files). Stop the server first.
- supabase: deletes every row and every evidence photo in the bucket. Restart the server afterwards
  so it re-imports the packages.

Usage:
    backend/.venv/bin/python tools/reset_demo_data.py --yes
"""
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.config import settings  # noqa: E402

if __name__ == "__main__":
    target = (f"the Supabase project {settings.supabase_url}" if settings.data_backend == "supabase"
              else str(settings.data_dir))
    if "--yes" not in sys.argv:
        sys.exit(f"This permanently deletes all inspections, evidence and catalog data in {target}. Re-run with --yes.")
    if settings.data_backend == "supabase":
        from app import db  # noqa: E402
        from app.blobs import blobs  # noqa: E402
        paths = db.reset_all()
        blobs.delete(paths)
        print(f"deleted all rows and {len(paths)} photos in {target}; restart the server to re-import packages")
    elif settings.data_dir.exists():
        shutil.rmtree(settings.data_dir)
        print(f"deleted {settings.data_dir}")
    else:
        print("nothing to delete")
