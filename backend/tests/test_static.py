"""The built web app is served so that a new deploy always reaches browsers (needs web/dist; skipped without it)."""
from __future__ import annotations

import hashlib

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app

pytestmark = pytest.mark.skipif(not (settings.web_dist_dir / "index.html").exists(), reason="web/dist not built")


def test_page_fingerprint_comes_from_its_content():
    # Vercel answers 304 when the browser's ETag matches; with the old size+date ETag every build of index.html
    # matched (same size, same fixed date), so browsers kept the previous app. The ETag must follow the content.
    c = TestClient(app)
    r = c.get("/")
    assert r.status_code == 200 and r.headers["cache-control"] == "no-cache"
    content = (settings.web_dist_dir / "index.html").read_bytes()
    assert r.headers["etag"] == f'"{hashlib.sha256(content).hexdigest()[:32]}"'
    assert r.headers["etag"] != '"d354725e9ea38c56243ff6e1ce59c2aa"'  # the stuck fingerprint seen in production
    assert c.get("/jobs/123").headers["etag"] == r.headers["etag"]  # app routes get the same page


def test_missing_script_is_404_not_the_html_page():
    c = TestClient(app)
    r = c.get("/assets/index-doesnotexist.js")
    assert r.status_code == 404 and "text/html" not in r.headers.get("content-type", "")


def test_hashed_assets_are_cached_for_a_year():
    c = TestClient(app)
    script = next(p.name for p in (settings.web_dist_dir / "assets").glob("index-*.js"))
    r = c.get(f"/assets/{script}")
    assert r.status_code == 200 and "immutable" in r.headers["cache-control"]
