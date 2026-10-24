"""File storage: a private Supabase Storage bucket, or local files in DATA_DIR/files (tests).

Paths are relative ("<company_id>/evidence/<task_id>/<evidence_id>.jpg", "<company_id>/media/<media_id>.glb"),
so records do not depend on the backend. Browsers never get a permanent link: the API hands out short-lived
signed URLs, created only after it has checked that the user may see the file.
"""
from __future__ import annotations

from pathlib import Path
from typing import Protocol
from urllib.parse import quote

import httpx

from .config import settings

SIGNED_URL_SECONDS = 3600


class BlobStore(Protocol):
    def put(self, path: str, data: bytes, content_type: str) -> None: ...
    def get(self, path: str) -> bytes | None: ...
    def delete(self, paths: list[str]) -> None: ...
    def signed_urls(self, paths: list[str]) -> dict[str, str]: ...


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

    def signed_urls(self, paths):
        return {p: f"/api/local-files/{quote(p)}" for p in paths}  # served by main.py in local mode only


class SupabaseBlobs:
    def __init__(self, url: str, key: str, bucket: str):
        self.url = url
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

    def signed_urls(self, paths):
        paths = sorted(set(paths))
        if not paths:
            return {}
        resp = self.client.post(f"/object/sign/{self.bucket}",
                                json={"expiresIn": SIGNED_URL_SECONDS, "paths": paths})
        resp.raise_for_status()
        return {r["path"]: f"{self.url}/storage/v1{r['signedURL']}" for r in resp.json()
                if r.get("signedURL") and not r.get("error")}


def _make() -> BlobStore:
    if settings.data_backend == "supabase":
        return SupabaseBlobs(settings.supabase_url, settings.supabase_secret_key, settings.storage_bucket)
    return LocalBlobs(settings.files_dir)


blobs: BlobStore = _make()
