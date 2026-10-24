import os
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
# Must be set before app.config is imported by any test module. Tests always run on local SQLite + files, with
# AI and document search stubbed, so they never touch the shared Supabase project or paid APIs.
os.environ["DATA_DIR"] = str(Path(tempfile.mkdtemp(prefix="fep-test-")) / "data")
os.environ["DATA_BACKEND"] = "local"
os.environ["AI_PROVIDER"] = "none"
os.environ["VOYAGE_API_KEY"] = "test-key"


@pytest.fixture()
def world():
    """Two companies, each with an employer and an employee; requests act as whoever `world.login(...)` names."""
    from fastapi.testclient import TestClient
    from app import auth, db
    from app.main import app

    db.init_db()
    db.reset_all(include_accounts=True)
    people = {}
    for company in ("acme", "other"):
        cid = db.new_id()
        db.insert("companies", {"id": cid, "name": company.title()})
        for role in ("employer", "employee"):
            uid = db.new_id()
            db.insert("users", {"id": uid, "company_id": cid, "username": f"{company}-{role}", "user_class": role})
            people[f"{company}-{role}"] = db.first("users", {"id": uid})

    client = TestClient(app)

    class As:
        """A client that acts as one user on every request (several can be used side by side)."""
        def __init__(self, name: str):
            self.name = name

        def __getattr__(self, method: str):
            def call(*args, **kwargs):
                app.dependency_overrides[auth.current_user] = lambda: people[self.name]
                return getattr(client, method)(*args, **kwargs)
            return call

    class World:
        users = people

        def __init__(self):
            self.client = client

        def login(self, name: str) -> As:
            return As(name)

    yield World()
    app.dependency_overrides.clear()
