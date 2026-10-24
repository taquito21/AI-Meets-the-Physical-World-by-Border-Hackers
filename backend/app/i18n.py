"""Display language for API responses and AI replies.

The client sends the reader's language in the X-Lang header ("es" or "en"). The interface text is translated in the
browser; the server translates two things:
- AI replies (photo review, document answers) are written in the reader's language.
- Media display text: a 3D model's metadata may carry `translations.<lang>` with the product name and per-part
  names, descriptions and spec labels/values (copied from engineering-packages/<pkg>/translations/<lang>.json by
  tools/load_demo_media.py). Ids, part numbers and the text sent to the AI as context stay as published.
"""
from __future__ import annotations

from contextvars import ContextVar
from typing import Any

SUPPORTED = ("en", "es")
LANGUAGE_NAMES = {"en": "English", "es": "Spanish"}
current_lang: ContextVar[str] = ContextVar("current_lang", default="en")

# Appended to AI prompts when the reader uses Spanish.
SPANISH_REPLY = ("Language: write every free-text field in plain, neutral Latin-American Spanish for a "
                 "non-technical field worker, using informal imperatives for instructions. Keep enum values exactly as "
                 "defined in the schema (they are codes, not display text).")


def pick(value: str | None) -> str:
    v = (value or "").strip().lower()[:2]
    return v if v in SUPPORTED else "en"


def component(c: dict[str, Any], tr: dict[str, Any]) -> dict[str, Any]:
    """A part with its name, description and specs in the reader's language, when a translation lines up."""
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


def media(title: str, metadata: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Title and metadata of a media item in the current language (English is the source)."""
    tr = ((metadata or {}).get("translations") or {}).get(current_lang.get())
    if not tr:
        return title, metadata
    out = dict(metadata)
    if out.get("parts"):
        out["parts"] = [component(p, tr) for p in out["parts"]]
    return (tr.get("product") or {}).get("product_name") or title, out
