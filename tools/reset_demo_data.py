"""Delete all jobs, tasks, evidence and media (development only). Companies and logins are kept.

Works on the configured backend (DATA_BACKEND in backend/.env):
- supabase: deletes those rows and their files in the storage bucket.
- local: deletes backend/data (SQLite + files). Stop the server first.

Re-load the demo 3D models afterwards with tools/load_demo_media.py.

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
        sys.exit(f"This permanently deletes all jobs, tasks, evidence and media in {target}. Re-run with --yes.")
    if settings.data_backend == "supabase":
        from app import db  # noqa: E402
        from app.blobs import blobs  # noqa: E402
        paths = db.reset_all()
        blobs.delete(paths)
        print(f"deleted all jobs and media and {len(paths)} files in {target} (companies and logins kept)")
    elif settings.data_dir.exists():
        shutil.rmtree(settings.data_dir)
        print(f"deleted {settings.data_dir}")
    else:
        print("nothing to delete")
