"""
vendor_templates.py — Layer C: one adapter per datasheet layout family.
=======================================================================
A template supplies VOCABULARY (symbol spellings, column header synonyms, caption patterns) and
nothing else. No page number, no coordinate, no bounding box: those are derived at runtime from the
document by `datasheet_extract`.

That separation is the whole point. If onboarding a second vendor needs a change anywhere above
this file, the layering has failed and should be fixed before a third vendor is added.
"""
from __future__ import annotations

import json
import os
from typing import Optional

_HERE = os.path.dirname(os.path.abspath(__file__))
_PATH = os.path.join(_HERE, "vendor_templates.json")

_CACHE: Optional[dict] = None


def load() -> dict:
    global _CACHE
    if _CACHE is None:
        with open(_PATH, encoding="utf-8") as f:
            _CACHE = json.load(f)
        _validate(_CACHE)
    return _CACHE


def _validate(data: dict) -> None:
    from app.mode_b.semiconductor import registry as R
    ids = set()
    known = {p["key"] for p in R.load()["parameters"]}
    for t in data["templates"]:
        tid = t.get("template_id")
        if not tid or tid in ids:
            raise ValueError(f"duplicate or missing template_id: {tid!r}")
        ids.add(tid)
        for sym, key in (t.get("symbol_map") or {}).items():
            if key not in known:
                raise ValueError(
                    f"template {tid!r} maps {sym!r} to {key!r}, which is not a canonical key. "
                    f"Every mapping must land in the registry — inventing a name here is exactly "
                    f"what the registry exists to prevent.")
    if not any(t.get("match", {}).get("always") for t in data["templates"]):
        raise ValueError("no fallback template: one template must declare match.always")


def templates() -> list[dict]:
    return list(load()["templates"])


def get(template_id: str) -> dict:
    for t in load()["templates"]:
        if t["template_id"] == template_id:
            return t
    raise KeyError(template_id)


def match(pdf_bytes: bytes, sample_chars: int = 4000) -> dict:
    """Pick the layout family for this document. Falls back to the generic template, and says so —
    `extraction.vendor_template` records which one was used, so a bad mapping is traceable to the
    adapter rather than looking like a bad datasheet."""
    head, meta = "", {}
    try:
        import fitz
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        head = "\n".join(doc[i].get_text() for i in range(min(2, doc.page_count)))[:sample_chars]
        meta = {k: str(v or "") for k, v in (doc.metadata or {}).items()}
    except Exception:
        pass
    author = " ".join((meta.get("author", ""), meta.get("producer", ""),
                       meta.get("creator", ""))).lower()

    for t in load()["templates"]:
        m = t.get("match") or {}
        if m.get("always"):
            continue
        # Document METADATA beats page text. The vendor name is reliably in the properties, while
        # the visible header may carry only a website — which is how the first attempt at this
        # template matched nothing and silently fell back to generic.
        want_author = (m.get("metadata_author") or "").lower()
        if want_author and want_author in author:
            return t
        markers = m.get("text_markers") or []
        if markers and all(mk.lower() in head.lower() for mk in markers):
            return t
    return next(t for t in load()["templates"] if (t.get("match") or {}).get("always"))
