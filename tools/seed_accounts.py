"""Create the demo companies and their logins in Supabase (idempotent).

For every user in backend/seed.json this creates the Supabase Auth account (already confirmed, so no email
is sent) and the matching row in the `users` table. Existing companies and accounts are kept as they are:
the script never changes a password or deletes anything.

Setup:
    cp backend/seed.example.json backend/seed.json   # then edit it (it is gitignored: it holds passwords)

Usage:
    backend/.venv/bin/python tools/seed_accounts.py
"""
import json
import sys
import uuid
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app import db  # noqa: E402
from app.config import settings  # noqa: E402

SEED_FILE = ROOT / "backend" / "seed.json"


def auth_client() -> httpx.Client:
    key = settings.supabase_secret_key
    return httpx.Client(base_url=f"{settings.supabase_url}/auth/v1", timeout=20,
                        headers={"apikey": key, "Authorization": f"Bearer {key}"})


def existing_auth_users(client: httpx.Client) -> dict[str, str]:
    """email -> auth user id, for every account in the project."""
    out, page = {}, 1
    while True:
        resp = client.get("/admin/users", params={"page": page, "per_page": 200})
        resp.raise_for_status()
        users = resp.json().get("users", [])
        out.update({u["email"].lower(): u["id"] for u in users if u.get("email")})
        if len(users) < 200:
            return out
        page += 1


def main() -> int:
    if settings.data_backend != "supabase":
        print("Supabase is not configured: set SUPABASE_URL and SUPABASE_SECRET_KEY in backend/.env")
        return 1
    if not SEED_FILE.exists():
        print(f"Missing {SEED_FILE.relative_to(ROOT)}: copy backend/seed.example.json and edit it")
        return 1
    seed = json.loads(SEED_FILE.read_text(encoding="utf-8"))
    client = auth_client()
    accounts = existing_auth_users(client)
    for company in seed["companies"]:
        row = db.first("companies", {"name": company["name"]})
        if row:
            company_id = row["id"]
            print(f"company  {company['name']}: exists")
        else:
            company_id = str(uuid.uuid4())
            db.insert("companies", {"id": company_id, "name": company["name"]})
            print(f"company  {company['name']}: created")
        for u in company["users"]:
            email = u["email"].strip().lower()
            if u["user_class"] not in ("employer", "employee"):
                print(f"  {email}: user_class must be 'employer' or 'employee', skipped")
                continue
            user_id = accounts.get(email)
            if user_id:
                status = "login exists"
            else:
                resp = client.post("/admin/users", json={
                    "email": email, "password": u["password"], "email_confirm": True,
                    "user_metadata": {"username": u["username"]}})
                if resp.status_code >= 400:
                    print(f"  {email}: could not create login ({resp.status_code}: {resp.text[:200]})")
                    continue
                user_id = resp.json()["id"]
                status = "login created"
            if db.first("users", {"id": user_id}):
                print(f"  {email}: {status}, profile exists")
                continue
            db.insert("users", {"id": user_id, "company_id": company_id, "username": u["username"],
                                "user_class": u["user_class"]})
            print(f"  {email}: {status}, profile created ({u['user_class']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
