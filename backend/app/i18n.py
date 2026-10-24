"""Display language for API responses and AI replies.

The client sends the reader's language in the X-Lang header ("es" or "en"). Each package may ship
translations/<lang>.json with display text only (names, titles, instructions, captions, locations). Engineering data
(ids, part numbers, values) and the text sent to the AI as context stay as published in the package. Translation files
are excluded from the package content hash, so adding a language never creates a new revision.
"""
from __future__ import annotations

import json
from contextvars import ContextVar
from functools import lru_cache
from typing import Any

from .config import settings

SUPPORTED = ("en", "es")
LANGUAGE_NAMES = {"en": "English", "es": "Spanish"}
current_lang: ContextVar[str] = ContextVar("current_lang", default="en")

REQ_TEXT = ("title", "instructions", "photo_guidance")
REQ_LISTS = ("inspection_points", "acceptance_criteria", "possible_findings", "risks", "recommended_actions",
             "visual_limitations")


def pick(value: str | None) -> str:
    v = (value or "").strip().lower()[:2]
    return v if v in SUPPORTED else "en"


@lru_cache(maxsize=64)
def _read(path: str, mtime: float) -> dict[str, Any]:  # mtime in the key: edited files are re-read
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def overlay(source_dir: str | None, lang: str | None = None) -> dict[str, Any]:
    """Translated display text for a package in the current language ({} when none: English is the source)."""
    lang = lang or current_lang.get()
    if lang == "en" or not source_dir:
        return {}
    path = settings.packages_dir / source_dir / "translations" / f"{lang}.json"
    try:
        return _read(str(path), path.stat().st_mtime)
    except (OSError, ValueError):
        return {}


def _list(src: Any, tr: Any) -> Any:
    # A translated list replaces the source only if it lines up item for item.
    return tr if isinstance(src, list) and isinstance(tr, list) and len(tr) == len(src) else src


def requirement(req: dict[str, Any], requirement_id: str, tr: dict[str, Any]) -> dict[str, Any]:
    t = (tr.get("requirements") or {}).get(requirement_id)
    if not t:
        return req
    out = dict(req)
    for k in REQ_TEXT:
        if out.get(k) and t.get(k):
            out[k] = t[k]
    for k in REQ_LISTS:
        if k in out:
            out[k] = _list(out[k], t.get(k))
    return out


def component(c: dict[str, Any], tr: dict[str, Any]) -> dict[str, Any]:
    t = (tr.get("components") or {}).get(c.get("id") or c.get("component_id"))
    if not t:
        return c
    out = dict(c)
    for k in ("name", "description"):
        if out.get(k) and t.get(k):
            out[k] = t[k]
    specs, tspecs = out.get("specs"), t.get("specs")
    if isinstance(specs, list) and isinstance(tspecs, list) and len(specs) == len(tspecs):
        out["specs"] = [{**s, **{k: ts[k] for k in ("label", "value") if ts.get(k)}} for s, ts in zip(specs, tspecs)]
    return out


def product_fields(row: dict[str, Any], tr: dict[str, Any], description_key: str = "description") -> None:
    p = tr.get("product") or {}
    if p.get("product_name") and "product_name" in row:
        row["product_name"] = p["product_name"]
    if p.get("product_description") and row.get(description_key):
        row[description_key] = p["product_description"]
    if p.get("asset_category") and row.get("asset_category"):
        row["asset_category"] = p["asset_category"]


def location(serial: str, metadata: dict[str, Any] | None, tr: dict[str, Any]) -> dict[str, Any] | None:
    loc = (tr.get("locations") or {}).get(serial)
    return {**metadata, "location": loc} if metadata and loc else metadata


def revision(rev: dict[str, Any]) -> dict[str, Any]:
    tr = overlay(rev.get("source_dir"))
    if not tr:
        return rev
    product_fields(rev, tr, "product_description")
    provenance = (tr.get("product") or {}).get("provenance")
    if provenance and isinstance(rev.get("manifest"), dict) and rev["manifest"].get("provenance"):
        rev["manifest"] = {**rev["manifest"], "provenance": provenance}
    rev["components"] = [component(c, tr) for c in rev.get("components", [])]
    rev["requirements"] = [requirement(r, r["requirement_id"], tr) for r in rev.get("requirements", [])]
    proc, tp = rev.get("procedure"), tr.get("procedure") or {}
    if isinstance(proc, dict):
        rev["procedure"] = {**proc, **{k: tp[k] for k in ("title", "scope") if tp.get(k)},
                            "safety_notes": _list(proc.get("safety_notes"), tp.get("safety_notes"))}
    docs = tr.get("documents") or {}
    rev["documents"] = [{**d, "title": docs.get(d.get("id"), d.get("title"))} for d in rev.get("documents", [])]
    demo = tr.get("demo_evidence") or {}
    rev["demo_evidence"] = [{**d, **{k: v for k, v in (demo.get(d["id"]) or {}).items() if k in ("caption", "source") and v}}
                            for d in rev.get("demo_evidence", [])]
    return rev
