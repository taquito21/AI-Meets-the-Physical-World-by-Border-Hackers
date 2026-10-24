"""Evidence photo storage: a private Supabase Storage bucket, or local files in DATA_DIR/evidence.

Paths are relative ("<inspection_id>/<evidence_id>.jpg"), so records do not depend on the backend.
Photos are always served through the API (never a public bucket URL), behind the same access checks.
"""
from __future__ import annotations

from pathlib import Path
from typing import Protocol
from urllib.parse import quote

import httpx

from .config import settings


class BlobStore(Protocol):
    def put(self, path: str, data: bytes, content_type: str) -> None: ...
    def get(self, path: str) -> bytes | None: ...
    def delete(self, paths: list[str]) -> None: ...


class LocalBlobs:
    def __init__(self, root: Path):
        self.root = root

    def _path(self, rel: str) -> Path | None:
        path = (self.root / rel).resolve()
        return path if self.root.resolve() in path.parents else None

    def put(self, path, data, content_type):
        target = self._path(path)
        if target is None:
            raise ValueError("invalid storage path")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    def get(self, path):
        target = self._path(path)
        return target.read_bytes() if target and target.exists() else None

    def delete(self, paths):
        for p in paths:
            target = self._path(p)
            if target:
                target.unlink(missing_ok=True)


class SupabaseBlobs:
    def __init__(self, url: str, key: str, bucket: str):
        self.bucket = bucket
        self.client = httpx.Client(base_url=f"{url}/storage/v1", timeout=30,
                                   headers={"apikey": key, "Authorization": f"Bearer {key}"})

    def _object(self, path: str) -> str:
        return f"/object/{self.bucket}/{quote(path)}"

    def put(self, path, data, content_type):
        resp = self.client.post(self._object(path), content=data,
                                headers={"Content-Type": content_type, "x-upsert": "true"})
        if resp.status_code >= 400:
            hint = " (create the bucket: see backend/supabase/schema.sql)" if "not found" in resp.text.lower() else ""
            raise RuntimeError(f"Supabase Storage upload failed {resp.status_code}: {resp.text[:200]}{hint}")

    def get(self, path):
        resp = self.client.get(self._object(path))
        if resp.status_code in (400, 404):
            return None
        resp.raise_for_status()
        return resp.content

    def delete(self, paths):
        for i in range(0, len(paths), 100):
            resp = self.client.request("DELETE", f"/object/{self.bucket}", json={"prefixes": paths[i:i + 100]})
            if resp.status_code >= 400:
                raise RuntimeError(f"Supabase Storage delete failed {resp.status_code}: {resp.text[:200]}")


def _make() -> BlobStore:
    if settings.data_backend == "supabase":
        return SupabaseBlobs(settings.supabase_url, settings.supabase_secret_key, settings.storage_bucket)
    return LocalBlobs(settings.evidence_dir)


blobs: BlobStore = _make()
