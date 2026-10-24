"""Create (or rotate) the two demo sign-in accounts: `jefe` (supervisor) and `trabajador` (worker).

Writes:
  backend/app/demo_users.json    usernames + PBKDF2 hashes only (committed; loaded at startup)
  backend/.env.demo-accounts     the plain passwords (ignored by git and by Vercel uploads; share them in person)

The passwords are never printed. Existing databases keep the old accounts until the data is reset
(tools/reset_demo_data.py --yes), because demo accounts are only inserted when missing.

Usage: backend/.venv/Scripts/python tools/make_demo_accounts.py
"""
import json
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.auth import AuthError, PBKDF2_ITERS, hash_password, validate_password  # noqa: E402

ALPHABET = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKMNPQRSTUVWXYZ23456789"  # no look-alikes (0/O, 1/l/I)
ACCOUNTS = [("jefe", "Jefe (demo)", "supervisor"), ("trabajador", "Trabajador (demo)", "inspector")]


def new_password() -> str:
    while True:  # 3 groups of 4: about 70 bits, easy to read out loud
        p = "-".join("".join(secrets.choice(ALPHABET) for _ in range(4)) for _ in range(3))
        try:
            validate_password(p)
            return p
        except AuthError:
            continue


def main() -> None:
    users = []
    lines = ["# Demo sign-in accounts for the Field Assistant (local only: never commit or upload).",
             "# The repository only holds PBKDF2 hashes of these passwords (backend/app/demo_users.json)."]
    for username, name, role in ACCOUNTS:
        password = new_password()
        salt, digest = hash_password(password)
        users.append({"username": username, "display_name": name, "role": role, "salt": salt, "pw_hash": digest,
                      "iters": PBKDF2_ITERS})
        lines += [f"{username.upper()}_USERNAME={username}", f"{username.upper()}_PASSWORD={password}"]
    (ROOT / "backend" / "app" / "demo_users.json").write_text(json.dumps({
        "note": "Demo accounts: username and PBKDF2-HMAC-SHA256 hash only (no passwords, no faces). "
                "Passwords are kept outside the repository.",
        "users": users}, indent=2) + "\n", encoding="utf-8")
    (ROOT / "backend" / ".env.demo-accounts").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("Written backend/app/demo_users.json (hashes) and backend/.env.demo-accounts (passwords, not printed).")


if __name__ == "__main__":
    main()
