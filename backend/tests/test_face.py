"""Face login: registration with consent, matching, lockout and the Supabase session hand-off.

Uses synthetic 128-number vectors (never real face data) and a fake Supabase Auth server (never the real project)."""
from __future__ import annotations

import json
import random

import httpx
import pytest

from app import face
from app.config import settings


def vec(seed: int, noise: float, rng: random.Random) -> list[float]:
    base = random.Random(seed)
    return [base.gauss(0, 1) + rng.gauss(0, noise) for _ in range(128)]


@pytest.fixture(autouse=True)
def fresh_lockout():
    face.lockout._fails.clear()
    face.lockout._until.clear()


@pytest.fixture()
def fake_session(monkeypatch):
    monkeypatch.setattr(face, "supabase_session", lambda uid: {"access_token": f"token-for-{uid}", "refresh_token": "r"})


def test_register_needs_consent_and_one_person(world):
    rng = random.Random(1)
    me = world.login("acme-employee")
    samples = [vec(7, 0.15, rng) for _ in range(5)]
    assert me.post("/api/me/face", json={"embeddings": samples}).status_code == 422  # no consent
    mixed = samples[:4] + [vec(99, 0.15, rng)]
    assert me.post("/api/me/face", json={"embeddings": mixed, "consent": True}).status_code == 422
    assert me.get("/api/me").json()["has_face"] is False
    assert me.post("/api/me/face", json={"embeddings": samples, "consent": True}).json() == {"has_face": True}
    assert me.get("/api/me").json()["has_face"] is True
    # The same face cannot be registered to a second account.
    boss = world.login("acme-employer")
    r = boss.post("/api/me/face", json={"embeddings": [vec(7, 0.15, rng) for _ in range(5)], "consent": True})
    assert r.status_code == 409
    assert me.delete("/api/me/face").json() == {"has_face": False}
    assert me.get("/api/me").json()["has_face"] is False


def test_face_login_matches_only_the_registered_person(world, fake_session):
    rng = random.Random(2)
    employee = world.users["acme-employee"]
    world.login("acme-employee").post("/api/me/face", json={"embeddings": [vec(11, 0.15, rng) for _ in range(5)],
                                                             "consent": True})
    world.login("acme-employer").post("/api/me/face", json={"embeddings": [vec(22, 0.15, rng) for _ in range(5)],
                                                             "consent": True})
    anon = world.client
    r = anon.post("/api/auth/face-login", json={"embeddings": [vec(11, 0.2, rng) for _ in range(5)]})
    assert r.status_code == 200 and r.json()["access_token"] == f"token-for-{employee['id']}"
    # A stranger, a mix of two people, or malformed data never logs in.
    assert anon.post("/api/auth/face-login", json={"embeddings": [vec(99, 0.2, rng) for _ in range(5)]}).status_code == 401
    mixed = [vec(11, 0.2, rng) for _ in range(4)] + [vec(22, 0.2, rng)]
    assert anon.post("/api/auth/face-login", json={"embeddings": mixed}).status_code == 401
    assert anon.post("/api/auth/face-login", json={"embeddings": [[0.1] * 5] * 5}).status_code == 422
    assert anon.post("/api/auth/face-login", json={"embeddings": [vec(11, 0.2, rng)]}).status_code == 422


def test_repeated_failures_lock_the_device(world, fake_session):
    rng = random.Random(3)
    world.login("acme-employee").post("/api/me/face", json={"embeddings": [vec(33, 0.15, rng) for _ in range(5)],
                                                             "consent": True})
    for _ in range(8):
        assert world.client.post("/api/auth/face-login",
                                 json={"embeddings": [vec(98, 0.2, rng) for _ in range(5)]}).status_code == 401
    r = world.client.post("/api/auth/face-login", json={"embeddings": [vec(33, 0.2, rng) for _ in range(5)]})
    assert r.status_code == 429


def test_supabase_session_uses_a_one_time_link_and_sends_no_email(monkeypatch):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path, json.loads(request.content or b"{}")))
        assert request.headers["apikey"] == "sb_secret_test"
        if request.url.path.endswith("/admin/users/u-1"):
            return httpx.Response(200, json={"id": "u-1", "email": "tech@example.com"})
        if request.url.path.endswith("/admin/generate_link"):
            return httpx.Response(200, json={"hashed_token": "hash-123", "action_link": "https://example/verify"})
        if request.url.path.endswith("/verify"):
            return httpx.Response(200, json={"access_token": "at", "refresh_token": "rt", "expires_in": 3600})
        return httpx.Response(404)

    real_client = httpx.Client
    monkeypatch.setattr(face.httpx, "Client", lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw))
    fake = {"data_backend": "supabase", "supabase_url": "https://proj.supabase.co", "supabase_secret_key": "sb_secret_test"}
    saved = {k: getattr(settings, k) for k in fake}
    for k, v in fake.items():
        object.__setattr__(settings, k, v)  # Settings is a frozen dataclass
    try:
        assert face.supabase_session("u-1") == {"access_token": "at", "refresh_token": "rt", "expires_in": 3600}
    finally:
        for k, v in saved.items():
            object.__setattr__(settings, k, v)
    paths = [c[1] for c in calls]
    assert paths == ["/auth/v1/admin/users/u-1", "/auth/v1/admin/generate_link", "/auth/v1/verify"]
    assert calls[1][2] == {"type": "magiclink", "email": "tech@example.com"}  # generate_link never emails
    assert calls[2][2] == {"type": "magiclink", "token_hash": "hash-123"}


def test_face_login_without_supabase_is_refused(world):
    rng = random.Random(4)
    world.login("other-employee").post("/api/me/face", json={"embeddings": [vec(44, 0.15, rng) for _ in range(5)],
                                                              "consent": True})
    r = world.client.post("/api/auth/face-login", json={"embeddings": [vec(44, 0.2, rng) for _ in range(5)]})
    assert r.status_code == 503  # local SQLite mode cannot mint Supabase sessions
