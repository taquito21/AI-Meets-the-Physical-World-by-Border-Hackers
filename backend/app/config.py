"""Runtime configuration, read from environment variables (and backend/.env if present)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = BACKEND_DIR.parent


def _load_dotenv() -> None:
    env_file = BACKEND_DIR / ".env"
    if not env_file.exists():
        return
    for n, line in enumerate(env_file.read_text(encoding="utf-8-sig").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            # Never echo the line: it may contain a secret.
            print(f"[config] backend/.env line {n} ignored: expected KEY=value", flush=True)
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()


def _bool(name: str, default: bool) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


_SUPABASE_URL = os.environ.get("SUPABASE_URL", "").strip().rstrip("/")
_SUPABASE_SECRET_KEY = os.environ.get("SUPABASE_SECRET_KEY", "").strip()
# "supabase" (Postgres + Storage over the Supabase REST API) or "local" (SQLite + files in DATA_DIR).
_DATA_BACKEND = os.environ.get("DATA_BACKEND") or ("supabase" if _SUPABASE_URL and _SUPABASE_SECRET_KEY else "local")


@dataclass(frozen=True)
class Settings:
    app_label: str = os.environ.get("APP_LABEL", "Field Assistant")
    # On Vercel the deployment is read-only; only /tmp is writable, and it is per-instance and temporary.
    data_dir: Path = Path(os.environ.get("DATA_DIR") or ("/tmp/field-platform" if os.environ.get("VERCEL")
                                                          else BACKEND_DIR / "data"))
    data_backend: str = _DATA_BACKEND
    supabase_url: str = _SUPABASE_URL
    supabase_secret_key: str = _SUPABASE_SECRET_KEY  # server side only; never sent to the web client
    # Public (browser) key: the web client uses it only to log in through Supabase Auth.
    supabase_publishable_key: str = os.environ.get("SUPABASE_PUBLISHABLE_KEY", "").strip()
    # Public keys that sign login tokens; defaults to the project's standard JWKS endpoint.
    supabase_jwks_url: str = os.environ.get("SUPABASE_JWKS_URL") or (
        f"{_SUPABASE_URL}/auth/v1/.well-known/jwks.json" if _SUPABASE_URL else "")
    storage_bucket: str = os.environ.get("STORAGE_BUCKET", "files")
    # "persistent" for Supabase or a laptop/server disk, "ephemeral" for local storage on serverless hosts
    # (data may reset at any time).
    storage_mode: str = os.environ.get("STORAGE_MODE") or (
        "ephemeral" if os.environ.get("VERCEL") and _DATA_BACKEND == "local" else "persistent")
    packages_dir: Path = Path(os.environ.get("PACKAGES_DIR", ROOT_DIR / "engineering-packages"))
    web_dist_dir: Path = Path(os.environ.get("WEB_DIST_DIR", ROOT_DIR / "web" / "dist"))
    # AI provider: "anthropic" (needs ANTHROPIC_API_KEY or an `ant auth login` profile) or "none".
    ai_provider: str = os.environ.get("AI_PROVIDER", "anthropic")
    ai_model: str = os.environ.get("AI_MODEL", "claude-opus-5-5")
    ai_effort: str = os.environ.get("AI_EFFORT", "low")
    # Hosted functions are killed at maxDuration (60 s in vercel.json), so there the worst case
    # (timeout x attempts) must fit inside it; locally there is no such limit.
    ai_timeout_s: float = float(os.environ.get("AI_TIMEOUT_S") or ("40" if os.environ.get("VERCEL") else "60"))
    ai_max_retries: int = int(os.environ.get("AI_MAX_RETRIES") or ("0" if os.environ.get("VERCEL") else "1"))
    ai_fallbacks: bool = _bool("AI_FALLBACKS", True)
    # Document search (RAG): Voyage AI embeddings through the MongoDB Atlas API.
    voyage_api_key: str = os.environ.get("VOYAGE_API_KEY", "").strip()
    voyage_model: str = os.environ.get("VOYAGE_MODEL", "voyage-4")  # 1024-dim vectors, matching schema.sql
    voyage_url: str = os.environ.get("VOYAGE_URL", "https://ai.mongodb.com/v1/embeddings")
    max_upload_mb: int = int(os.environ.get("MAX_UPLOAD_MB", "15"))
    cors_origins: list[str] = field(default_factory=lambda: os.environ.get("CORS_ORIGINS", "*").split(","))

    @property
    def db_path(self) -> Path:
        return self.data_dir / "field_platform.db"

    @property
    def files_dir(self) -> Path:
        return self.data_dir / "files"


settings = Settings()
