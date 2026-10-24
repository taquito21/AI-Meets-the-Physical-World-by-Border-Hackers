"""Accounts and sign-in for workers (role "inspector") and supervisors.

Same design as the HK Vision login (Mechatronics AI project, hkvision/auth.py):
- Passwords are never stored: PBKDF2-HMAC-SHA256 (200 000 iterations, random salt per user), compared in constant
  time; an unknown user costs the same time as a wrong password, so usernames cannot be probed.
- Temporary lockout after repeated failures.
- Faces are stored only as 128-number SFace embeddings (never photos), registered by the person themselves after
  signing in with their password, with explicit consent; deletable at any time. A face sign-in needs several frames
  that all match the same account (cosine >= 0.40, slightly stricter than OpenCV's 0.363).
- Face detection and the embedding run in the browser (web/src/face); this server only compares vectors.
Limitation (as in the original): no liveness check, so a printed photo might pass a face sign-in. The password
sign-in is always available.

Sessions are a signed, HttpOnly cookie (stateless, so they work across serverless instances). Storage is the app
database; moving users to another database (e.g. Supabase) only touches the functions in the "store" section.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import math
import re
import secrets
import time
from contextvars import ContextVar
from pathlib import Path
from typing import Any

from . import db
from .config import settings

PBKDF2_ITERS = 200_000
USERNAME_RE = re.compile(r"^[a-z0-9_.-]{3,32}$")
MIN_PASSWORD = 8
ROLES = ("inspector", "supervisor")
FACE_DIM = 128
COOKIE = "fep_session"
DEMO_USERS_FILE = Path(__file__).with_name("demo_users.json")

current_user: ContextVar[dict[str, Any] | None] = ContextVar("current_user", default=None)


class AuthError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


# ------------------------------------------------------------------ passwords --

def hash_password(password: str, salt: bytes | None = None, iters: int = PBKDF2_ITERS) -> tuple[str, str]:
    salt = salt or secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iters)
    return base64.b64encode(salt).decode(), base64.b64encode(dk).decode()


def check_password(password: str, salt_b64: str, hash_b64: str, iters: int = PBKDF2_ITERS) -> bool:
    _, dk = hash_password(password, base64.b64decode(salt_b64), iters)
    return hmac.compare_digest(dk, hash_b64)


_DUMMY = hash_password("x" * 12)  # equal-cost check for unknown usernames


def validate_username(username: str) -> str:
    username = (username or "").strip().lower()
    if not USERNAME_RE.match(username):
        raise AuthError("Username: 3-32 lowercase letters, numbers, '_', '.' or '-'", 422)
    return username


def validate_password(password: str) -> None:
    if len(password or "") < MIN_PASSWORD:
        raise AuthError(f"Password: at least {MIN_PASSWORD} characters", 422)
    if password.lower() == password or password.upper() == password or not any(c.isdigit() for c in password):
        raise AuthError("Password: mix uppercase, lowercase and numbers", 422)


# ------------------------------------------------------------------- lockout --

class LoginThrottle:
    """After `max_attempts` failures in a row for one key, refuse that key for `lockout_s` seconds."""

    def __init__(self, max_attempts: int = 5, lockout_s: float = 30.0, clock=time.monotonic):
        self.max_attempts, self.lockout_s, self.clock = max_attempts, lockout_s, clock
        self._fails: dict[str, int] = {}
        self._until: dict[str, float] = {}

    def remaining(self, key: str) -> float:
        return max(0.0, self._until.get(key, 0.0) - self.clock())

    def failure(self, key: str) -> None:
        n = self._fails.get(key, 0) + 1
        if n >= self.max_attempts:
            self._until[key] = self.clock() + self.lockout_s
            n = 0
        self._fails[key] = n

    def success(self, key: str) -> None:
        self._fails.pop(key, None)
        self._until.pop(key, None)


password_throttle = LoginThrottle(5, 30.0)
face_throttle = LoginThrottle(8, 60.0)


def check_throttle(throttle: LoginThrottle, key: str) -> None:
    wait = throttle.remaining(key)
    if wait > 0:
        raise AuthError(f"Too many attempts. Try again in {math.ceil(wait)} seconds.", 429)


# --------------------------------------------------------------------- store --

def _public(u: dict[str, Any]) -> dict[str, Any]:
    return {"username": u["username"], "display_name": u["display_name"], "role": u["role"],
            "has_face": bool(u.get("faces")), "active": bool(u.get("active", 1)),
            "created_at": u.get("created_at"), "created_by": u.get("created_by")}


def get_user(conn, username: str) -> dict[str, Any] | None:
    return db.row(conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone())


def list_users(conn) -> list[dict[str, Any]]:
    return [_public(u) for u in db.rows(conn.execute("SELECT * FROM users ORDER BY role DESC, display_name").fetchall())]


def create_user(conn, username: str, display_name: str, password: str, role: str, created_by: str | None,
                pw: tuple[str, str] | None = None) -> dict[str, Any]:
    username = validate_username(username)
    display_name = (display_name or "").strip()[:60]
    if not display_name:
        raise AuthError("Write the person's name", 422)
    if role not in ROLES:
        raise AuthError("Unknown role", 422)
    if get_user(conn, username):
        raise AuthError("That username is already taken", 409)
    # Actions are recorded under the person's name, so names must be unique (supervisor != inspector rule).
    if conn.execute("SELECT 1 FROM users WHERE lower(display_name) = lower(?)", (display_name,)).fetchone():
        raise AuthError("Someone already has that name; add a surname or initial", 409)
    if pw is None:
        validate_password(password)
        pw = hash_password(password)
    conn.execute("INSERT INTO users (username, display_name, role, salt, pw_hash, iters, faces, active, created_at, "
                 "created_by) VALUES (?,?,?,?,?,?,?,?,?,?)",
                 (username, display_name, role, pw[0], pw[1], PBKDF2_ITERS, "[]", 1, db.now(), created_by))
    db.log_event(conn, "user", username, "user_created", created_by, {"role": role})
    return _public(get_user(conn, username))


def seed_demo_users() -> None:
    """Demo accounts (one supervisor, one worker) from demo_users.json: username + PBKDF2 hash only, no faces.
    The passwords are not in the repository; see docs/LOGIN.md."""
    if not DEMO_USERS_FILE.exists():
        return
    data = json.loads(DEMO_USERS_FILE.read_text(encoding="utf-8"))
    with db.tx() as conn:
        for u in data.get("users", []):
            if not get_user(conn, u["username"]):
                conn.execute("INSERT INTO users (username, display_name, role, salt, pw_hash, iters, faces, active, "
                             "created_at, created_by) VALUES (?,?,?,?,?,?,?,?,?,?)",
                             (u["username"], u["display_name"], u["role"], u["salt"], u["pw_hash"],
                              u.get("iters", PBKDF2_ITERS), "[]", 1, db.now(), "seed"))


# ------------------------------------------------------------------- sign-in --

def password_login(username: str, password: str, role: str, client: str) -> dict[str, Any]:
    username = (username or "").strip().lower()
    key = f"{client}|{username}"
    check_throttle(password_throttle, key)
    with db.read() as conn:
        u = get_user(conn, username)
    ok = check_password(password or "", u["salt"], u["pw_hash"], u["iters"]) if u else \
        check_password(password or "", *_DUMMY) and False
    if not ok or not u["active"]:
        password_throttle.failure(key)
        raise AuthError("Wrong username or password", 401)
    password_throttle.success(key)
    if u["role"] != role:
        raise AuthError("supervisor_account" if u["role"] == "supervisor" else "worker_account", 403)
    with db.tx() as conn:
        db.log_event(conn, "user", u["username"], "signed_in", u["display_name"], {"method": "password"})
    return _public(u)


def _vectors(embeddings: list[list[float]], min_n: int = 3, max_n: int = 10) -> list[list[float]]:
    if not (min_n <= len(embeddings) <= max_n):
        raise AuthError("Face data incomplete; try again", 422)
    out = []
    for e in embeddings:
        if len(e) != FACE_DIM or not all(isinstance(x, (int, float)) and math.isfinite(x) for x in e):
            raise AuthError("Face data incomplete; try again", 422)
        out.append([float(x) for x in e])
    return out


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb + 1e-9)


def _best_match(vec: list[float], users: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, float]:
    best, score = None, -1.0
    for u in users:
        for f in u["faces"]:
            c = cosine(vec, f)
            if c > score:
                best, score = u, c
    return best, score


def face_login(embeddings: list[list[float]], role: str, client: str) -> dict[str, Any]:
    """Every submitted frame must match the same active account of this role above the threshold."""
    check_throttle(face_throttle, client)
    vecs = _vectors(embeddings)
    with db.read() as conn:
        users = [u for u in db.rows(conn.execute(
            "SELECT * FROM users WHERE active = 1 AND faces != '[]'").fetchall())]
    matches = [_best_match(v, users) for v in vecs]
    first = matches[0][0]
    if first is None or any(m[0] is None or m[0]["username"] != first["username"] or m[1] < settings.face_threshold
                            for m in matches):
        face_throttle.failure(client)
        raise AuthError("Face not recognized", 401)
    face_throttle.success(client)
    if first["role"] != role:
        raise AuthError("supervisor_account" if first["role"] == "supervisor" else "worker_account", 403)
    with db.tx() as conn:
        db.log_event(conn, "user", first["username"], "signed_in", first["display_name"],
                     {"method": "face", "min_score": round(min(m[1] for m in matches), 3)})
    return _public(first)


def register_face(username: str, embeddings: list[list[float]], consent: bool) -> dict[str, Any]:
    if not consent:
        raise AuthError("Consent is required to save your face", 422)
    vecs = _vectors(embeddings)
    # The samples must be one person, and that face must not already belong to another account.
    if any(cosine(vecs[0], v) < 0.6 for v in vecs[1:]):
        raise AuthError("The samples don't look like the same face; try again with good light", 422)
    with db.tx() as conn:
        others = [u for u in db.rows(conn.execute(
            "SELECT * FROM users WHERE username != ? AND faces != '[]'", (username,)).fetchall())]
        other, score = _best_match(vecs[0], others)
        if other is not None and score >= settings.face_threshold:
            raise AuthError("This face is already registered to another account", 409)
        conn.execute("UPDATE users SET faces = ?, face_consent_at = ? WHERE username = ?",
                     (db.dumps(vecs), db.now(), username))
        u = get_user(conn, username)
        db.log_event(conn, "user", username, "face_registered", u["display_name"], {"samples": len(vecs)})
    return _public(u)


def delete_face(username: str) -> dict[str, Any]:
    with db.tx() as conn:
        conn.execute("UPDATE users SET faces = '[]', face_consent_at = NULL WHERE username = ?", (username,))
        u = get_user(conn, username)
        db.log_event(conn, "user", username, "face_deleted", u["display_name"])
    return _public(u)


# ------------------------------------------------------------------ sessions --

def _secret() -> bytes:
    if settings.auth_secret:
        return settings.auth_secret.encode()
    if settings.access_password:
        # Hosted test deployment: derive a stable key from the existing shared secret (same on every instance).
        return hmac.new(settings.access_password.encode(), b"field-platform session key v1", hashlib.sha256).digest()
    path = settings.data_dir / "session.key"  # local development: a random key kept with the local data
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(secrets.token_bytes(32))
    return path.read_bytes()


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def make_token(user: dict[str, Any]) -> str:
    payload = _b64(json.dumps({"u": user["username"], "n": user["display_name"], "r": user["role"],
                               "exp": int(time.time() + settings.session_hours * 3600)}).encode())
    return f"{payload}.{_b64(hmac.new(_secret(), payload.encode(), hashlib.sha256).digest())}"


def read_token(token: str | None) -> dict[str, Any] | None:
    if not token or "." not in token:
        return None
    payload, sig = token.rsplit(".", 1)
    expected = _b64(hmac.new(_secret(), payload.encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(sig, expected):
        return None
    try:
        data = json.loads(_unb64(payload))
    except ValueError:
        return None
    if data.get("exp", 0) < time.time() or data.get("r") not in ROLES:
        return None
    return {"username": data["u"], "display_name": data["n"], "role": data["r"]}


def actor(fallback: str) -> str:
    """The signed-in person's name; a name sent by the client is only used when nobody is signed in
    (development and tests with AUTH_REQUIRED=false)."""
    u = current_user.get()
    return u["display_name"] if u else fallback


def require_role(role: str) -> None:
    u = current_user.get()
    if settings.auth_required and (u is None or u["role"] != role):
        raise AuthError("Only a supervisor can do this", 403)
