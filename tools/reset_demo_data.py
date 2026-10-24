"""Delete the local demo database and evidence photos (development only).

Released engineering revisions are immutable once loaded. While adapting the demo
packages (e.g. after venue photographs), reset the demo data so the edited revision A
can be loaded fresh. Stop the server first.

Usage:
    backend/.venv/Scripts/python tools/reset_demo_data.py --yes
"""
import shutil
import sys
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "backend" / "data"

if __name__ == "__main__":
    if "--yes" not in sys.argv:
        sys.exit(f"This permanently deletes {DATA} (all inspections and evidence). Re-run with --yes.")
    if DATA.exists():
        shutil.rmtree(DATA)
        print(f"deleted {DATA}")
    else:
        print("nothing to delete")
