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


@pytest.fixture(autouse=True, scope="module")
def fresh_database():
    """Each test module starts from an empty database (packages are re-imported on app startup)."""
    from app.config import settings
    shutil.rmtree(settings.data_dir, ignore_errors=True)
    yield
