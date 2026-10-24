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


@dataclass(frozen=True)
class Settings:
    app_label: str = os.environ.get("APP_LABEL", "Field Assistant")
    # On Vercel the deployment is read-only; only /tmp is writable, and it is per-instance and temporary.
    data_dir: Path = Path(os.environ.get("DATA_DIR") or ("/tmp/field-platform" if os.environ.get("VERCEL")
                                                          else BACKEND_DIR / "data"))
    # "persistent" for a laptop/server disk, "ephemeral" on serverless hosts where data may reset at any time.
    storage_mode: str = os.environ.get("STORAGE_MODE") or ("ephemeral" if os.environ.get("VERCEL") else "persistent")
    # When set, every request requires this shared password (HTTP Basic auth; any username).
    access_password: str = os.environ.get("ACCESS_PASSWORD", "")
    packages_dir: Path = Path(os.environ.get("PACKAGES_DIR", ROOT_DIR / "engineering-packages"))
    web_dist_dir: Path = Path(os.environ.get("WEB_DIST_DIR", ROOT_DIR / "web" / "dist"))
    # AI provider: "anthropic" (needs ANTHROPIC_API_KEY or an `ant auth login` profile) or "none".
    ai_provider: str = os.environ.get("AI_PROVIDER", "anthropic")
    ai_model: str = os.environ.get("AI_MODEL", "claude-opus-5-5")
    ai_effort: str = os.environ.get("AI_EFFORT", "low")
    ai_timeout_s: float = float(os.environ.get("AI_TIMEOUT_S", "60"))
    ai_fallbacks: bool = _bool("AI_FALLBACKS", True)
    # Closure policy: may an inspection be submitted while critical findings are still open?
    block_submit_on_open_critical: bool = _bool("BLOCK_SUBMIT_ON_OPEN_CRITICAL", False)
    seed_instances: bool = _bool("SEED_INSTANCES", True)
    max_upload_mb: int = int(os.environ.get("MAX_UPLOAD_MB", "15"))
    cors_origins: list[str] = field(default_factory=lambda: os.environ.get("CORS_ORIGINS", "*").split(","))

    @property
    def db_path(self) -> Path:
        return self.data_dir / "field_platform.db"

    @property
    def evidence_dir(self) -> Path:
        return self.data_dir / "evidence"


settings = Settings()
