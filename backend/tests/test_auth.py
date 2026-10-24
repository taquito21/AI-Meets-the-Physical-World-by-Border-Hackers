"""Sign-in for workers and supervisors: passwords, lockout, sessions, roles and face matching.

Face tests use synthetic 128-number vectors, never real face data."""
from __future__ import annotations

import json
import random

import pytest
from fastapi.testclient import TestClient

from app import auth, db
from app.config import settings
from app.main import app

WORKER_PW = "Trabajo2026x"
BOSS_PW = "Jefatura2026y"


@pytest.fixture(scope="module", autouse=True)
def enforce_sign_in():
    object.__setattr__(settings, "auth_required", True)
    yield
    object.__setattr__(settings, "auth_required", False)


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        with db.tx() as conn:
            auth.create_user(conn, "ana", "Ana López", WORKER_PW, "inspector", "test")
            auth.create_user(conn, "beto", "Beto Ruiz", BOSS_PW, "supervisor", "test")
        yield c


@pytest.fixture(autouse=True)
def reset_lockouts():
    for t in (auth.password_throttle, auth.face_throttle):
        t._fails.clear()
        t._until.clear()
    yield


def login(c: TestClient, username: str, password: str, role: str):
    c.cookies.clear()
    return c.post("/api/auth/login", json={"username": username, "password": password, "role": role})


def face(seed: int, noise: float = 0.0, rng: random.Random | None = None) -> list[float]:
    base = random.Random(seed)
    rng = rng or random.Random(seed * 7 + 1)
    return [base.gauss(0, 1) + rng.gauss(0, noise) for _ in range(128)]


def test_api_requires_sign_in_except_health_and_login(client):
    client.cookies.clear()
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/products").status_code == 401
    assert client.get("/api/auth/me").status_code == 401
    client.cookies.set(auth.COOKIE, "forged.token")
    assert client.get("/api/products").status_code == 401


def test_password_sign_in_sets_a_session_and_checks_the_role(client):
    assert login(client, "ana", "wrong-Password1", "inspector").status_code == 401
    assert login(client, "nobody", WORKER_PW, "inspector").status_code == 401  # same answer: no user probing
    r = login(client, "ana", WORKER_PW, "supervisor")
    assert r.status_code == 403 and r.json()["detail"] == "worker_account"
    r = login(client, "ana", WORKER_PW, "inspector")
    assert r.status_code == 200 and r.json()["user"]["display_name"] == "Ana López"
    assert "pw_hash" not in r.json()["user"] and "faces" not in r.json()["user"]
    assert client.get("/api/auth/me").json()["user"]["role"] == "inspector"
    assert client.get("/api/products").status_code == 200
    client.post("/api/auth/logout")
    assert client.get("/api/products").status_code == 401


def test_lockout_after_repeated_failures(client):
    for _ in range(5):
        assert login(client, "beto", "Nope12345", "supervisor").status_code == 401
    r = login(client, "beto", BOSS_PW, "supervisor")
    assert r.status_code == 429 and "Try again" in r.json()["detail"]


def test_actions_are_recorded_under_the_signed_in_person(client):
    login(client, "ana", WORKER_PW, "inspector")
    r = client.post("/api/inspections", json={"serial_number": "CHAIR-001-SN-0026", "inspector": "Someone Else"})
    assert r.status_code == 200
    assert r.json()["state"]["inspection"]["inspector"] == "Ana López"


def test_only_supervisors_review_and_manage_workers(client):
    login(client, "ana", WORKER_PW, "inspector")
    assert client.get("/api/users").status_code == 403
    insp = client.get("/api/inspections").json()[0]["id"]
    r = client.post(f"/api/inspections/{insp}/review", json={"reviewer": "Ana López", "decision": "approve"})
    assert r.status_code == 403
    assert client.post("/api/packages/chair-model-001/load", json={"actor": "Ana"}).status_code == 403

    login(client, "beto", BOSS_PW, "supervisor")
    r = client.post("/api/users", json={"username": "carla", "display_name": "Carla Méndez", "password": "Campo2026z"})
    assert r.status_code == 200 and r.json()["role"] == "inspector" and r.json()["created_by"] == "Beto Ruiz"
    assert client.post("/api/users", json={"username": "carla2", "display_name": "carla méndez",
                                           "password": "Campo2026z"}).status_code == 409
    assert client.post("/api/users", json={"username": "dani", "display_name": "Dani",
                                           "password": "weak"}).status_code == 422
    names = [u["username"] for u in client.get("/api/users").json()]
    assert {"ana", "beto", "carla"} <= set(names)


def test_face_registration_and_face_sign_in(client):
    rng = random.Random(3)
    login(client, "ana", WORKER_PW, "inspector")
    samples = [face(11, 0.15, rng) for _ in range(5)]
    assert client.post("/api/auth/face", json={"embeddings": samples}).status_code == 422  # no consent
    r = client.post("/api/auth/face", json={"embeddings": samples, "consent": True})
    assert r.status_code == 200 and r.json()["user"]["has_face"] is True
    with db.read() as conn:
        stored = auth.get_user(conn, "ana")
    assert len(stored["faces"]) == 5 and stored["face_consent_at"]

    client.cookies.clear()
    r = client.post("/api/auth/face-login", json={"embeddings": [face(11, 0.2, rng) for _ in range(5)],
                                                   "role": "inspector"})
    assert r.status_code == 200 and r.json()["user"]["username"] == "ana"
    # Right face, wrong door: a worker's face cannot open the supervisor sign-in.
    r = client.post("/api/auth/face-login", json={"embeddings": [face(11, 0.2, rng) for _ in range(5)],
                                                   "role": "supervisor"})
    assert r.status_code == 403
    # A different face, or one frame from someone else, is refused.
    r = client.post("/api/auth/face-login", json={"embeddings": [face(99, 0.2, rng) for _ in range(5)],
                                                   "role": "inspector"})
    assert r.status_code == 401
    mixed = [face(11, 0.2, rng) for _ in range(4)] + [face(99, 0.2, rng)]
    assert client.post("/api/auth/face-login", json={"embeddings": mixed, "role": "inspector"}).status_code == 401
    # Malformed data is rejected.
    assert client.post("/api/auth/face-login", json={"embeddings": [[0.1] * 5] * 5,
                                                      "role": "inspector"}).status_code == 422

    # The same face cannot be registered to a second account.
    login(client, "beto", BOSS_PW, "supervisor")
    r = client.post("/api/auth/face", json={"embeddings": [face(11, 0.15, rng) for _ in range(5)], "consent": True})
    assert r.status_code == 409

    # Deleting the face disables face sign-in.
    login(client, "ana", WORKER_PW, "inspector")
    assert client.delete("/api/auth/face").json()["user"]["has_face"] is False
    client.cookies.clear()
    r = client.post("/api/auth/face-login", json={"embeddings": [face(11, 0.2, rng) for _ in range(5)],
                                                   "role": "inspector"})
    assert r.status_code == 401


def test_demo_accounts_hold_hashes_only():
    data = json.loads(auth.DEMO_USERS_FILE.read_text(encoding="utf-8"))
    roles = {u["role"] for u in data["users"]}
    assert roles == {"inspector", "supervisor"}
    for u in data["users"]:
        assert set(u) == {"username", "display_name", "role", "salt", "pw_hash", "iters"}
    with db.read() as conn:
        assert all(auth.get_user(conn, u["username"]) for u in data["users"])  # seeded at startup
