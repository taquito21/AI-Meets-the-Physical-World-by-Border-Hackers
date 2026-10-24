"""Face login: an optional second way to sign in to an existing Supabase account (the password always stays).

Same rules as the HK Vision login (Mechatronics AI project):
- Faces are stored only as 128-number SFace vectors, never images. Detection and the vector run in the browser
  (web/src/face); this server only compares vectors. A person registers their own face after a normal password
  login, with explicit consent, and can delete it at any time.
- A face login needs several frames that all match the same account (cosine >= 0.40, a little stricter than
  OpenCV's 0.363). Repeated failures lock the device out for a while.
- No liveness check: a printed photo might pass. That is why the password stays available.

After a match the server asks Supabase Auth (admin API, secret key) for a one-time login link for that user and
redeems it at once, which yields an ordinary Supabase session. From then on the app works exactly as after a
password login. The vectors live in the `face_embeddings` table (RLS on, backend only).
"""
from __future__ import annotations

import math
import time
from typing import Any

import httpx
from fastapi import HTTPException

from . import db
from .config import settings

FACE_DIM = 128
MIN_SAMPLES, MAX_SAMPLES = 3, 10
SAME_PERSON = 0.6  # registration samples must agree with each other at least this much


class Lockout:
    """After `max_attempts` failures in a row for one key, refuse that key for `seconds` (kept per server instance)."""

    def __init__(self, max_attempts: int = 8, seconds: float = 60.0, clock=time.monotonic):
        self.max_attempts, self.seconds, self.clock = max_attempts, seconds, clock
        self._fails: dict[str, int] = {}
        self._until: dict[str, float] = {}

    def check(self, key: str) -> None:
        wait = self._until.get(key, 0.0) - self.clock()
        if wait > 0:
            raise HTTPException(429, f"Too many attempts. Try again in {math.ceil(wait)} seconds.")

    def failure(self, key: str) -> None:
        n = self._fails.get(key, 0) + 1
        if n >= self.max_attempts:
            self._until[key] = self.clock() + self.seconds
            n = 0
        self._fails[key] = n

    def success(self, key: str) -> None:
        self._fails.pop(key, None)
        self._until.pop(key, None)


lockout = Lockout()


def vectors(embeddings: list[list[float]]) -> list[list[float]]:
    if not (MIN_SAMPLES <= len(embeddings) <= MAX_SAMPLES):
        raise HTTPException(422, "Face data incomplete. Try again.")
    out = []
    for e in embeddings:
        if len(e) != FACE_DIM or not all(isinstance(x, (int, float)) and math.isfinite(x) for x in e):
            raise HTTPException(422, "Face data incomplete. Try again.")
        out.append([float(x) for x in e])
    return out


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    return dot / (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)) + 1e-9)


def _rows(where: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    try:
        return db.select("face_embeddings", where, columns="user_id,embeddings")
    except db.SchemaMissing:
        raise HTTPException(503, "Face login is not set up yet: apply backend/supabase/schema.sql in Supabase.")


def has_face(user_id: str) -> bool:
    try:
        return bool(db.select("face_embeddings", {"user_id": user_id}, columns="user_id"))
    except db.SchemaMissing:
        return False


def _best(vec: list[float], rows: list[dict[str, Any]]) -> tuple[str | None, float]:
    best, score = None, -1.0
    for r in rows:
        for f in r["embeddings"]:
            c = cosine(vec, f)
            if c > score:
                best, score = r["user_id"], c
    return best, score


def register(user: dict[str, Any], embeddings: list[list[float]], consent: bool) -> None:
    if not consent:
        raise HTTPException(422, "Consent is required to save your face.")
    vecs = vectors(embeddings)
    if any(cosine(vecs[0], v) < SAME_PERSON for v in vecs[1:]):
        raise HTTPException(422, "The samples don't look like the same face. Try again with good light.")
    other, score = _best(vecs[0], [r for r in _rows() if r["user_id"] != user["id"]])
    if other is not None and score >= settings.face_threshold:
        raise HTTPException(409, "This face is already registered to another account.")
    db.upsert("face_embeddings", {"user_id": user["id"], "embeddings": vecs, "consent_at": db.now(),
                                  "updated_at": db.now()}, on_conflict="user_id")


def remove(user: dict[str, Any]) -> None:
    try:
        db.delete("face_embeddings", {"user_id": user["id"]})
    except db.SchemaMissing:
        pass


def identify(embeddings: list[list[float]], client: str) -> str:
    """The user id that every submitted frame matches above the threshold (401 otherwise)."""
    lockout.check(client)
    vecs = vectors(embeddings)
    rows = _rows()
    matches = [_best(v, rows) for v in vecs]
    first = matches[0][0]
    if first is None or any(uid != first or score < settings.face_threshold for uid, score in matches):
        lockout.failure(client)
        raise HTTPException(401, "Face not recognized")
    lockout.success(client)
    return first


def supabase_session(user_id: str) -> dict[str, Any]:
    """An ordinary Supabase session for this user: admin one-time login link, redeemed immediately (no email sent)."""
    if settings.data_backend != "supabase" or not settings.supabase_secret_key:
        raise HTTPException(503, "Face login needs the Supabase login to be configured")
    key = settings.supabase_secret_key
    with httpx.Client(base_url=f"{settings.supabase_url}/auth/v1", timeout=20,
                      headers={"apikey": key, "Authorization": f"Bearer {key}"}) as client:
        user = client.get(f"/admin/users/{user_id}")
        if user.status_code != 200 or not user.json().get("email"):
            raise HTTPException(502, "Could not start the session. Log in with your password.")
        link = client.post("/admin/generate_link", json={"type": "magiclink", "email": user.json()["email"]})
        body = link.json() if link.status_code == 200 else {}
        token_hash = body.get("hashed_token") or (body.get("properties") or {}).get("hashed_token")
        if not token_hash:
            raise HTTPException(502, "Could not start the session. Log in with your password.")
        for kind in ("magiclink", "email"):  # Supabase accepts either name, depending on its version
            session = client.post("/verify", json={"type": kind, "token_hash": token_hash})
            if session.status_code == 200 and session.json().get("access_token"):
                s = session.json()
                return {"access_token": s["access_token"], "refresh_token": s["refresh_token"],
                        "expires_in": s.get("expires_in")}
    raise HTTPException(502, "Could not start the session. Log in with your password.")
