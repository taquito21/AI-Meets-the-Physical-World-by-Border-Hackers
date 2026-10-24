import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
# Must be set before app.config is imported by any test module.
os.environ["DATA_DIR"] = str(Path(tempfile.mkdtemp(prefix="fep-test-")) / "data")
os.environ["AI_PROVIDER"] = "none"
# Tests run on local SQLite. TEST_DATA_BACKEND=supabase runs them against the Supabase project in backend/.env
# instead, and WIPES ALL ITS DATA before every test module (use a development project only).
os.environ["DATA_BACKEND"] = os.environ.get("TEST_DATA_BACKEND", "local")


@pytest.fixture(autouse=True, scope="module")
def fresh_database():
    """Each test module starts from an empty database (packages are re-imported on app startup)."""
    from app.config import settings
    if settings.data_backend == "supabase":
        from app import db, main
        from app.blobs import blobs
        blobs.delete(db.reset_all())
        main._ready = False
    else:
        shutil.rmtree(settings.data_dir, ignore_errors=True)
    yield
