"""
parts_store.py — the per-part datasheet library (M2).
=====================================================
One folder per part, holding the PDF and everything derived from it:

    parts/<MPN>/
        datasheet.pdf          the bytes as supplied
        source.json            sha256, size, vendor revision, filename, when it was added
        extracted_v<N>.json    what the machine read       — NEVER overwritten
        confirmed_v<N>.json    what the designer agreed    — written by M3
        curves/                phase 2 (M7), with each curve's axis calibration beside it

TWO RULES THIS ENFORCES.

  1. THE EXTRACTION IS IMMUTABLE. A new extraction of the same part writes v2; v1 stays. When a
     number is questioned later the library can answer "the machine read X, you confirmed Y", which
     is the entire point of keeping both.
  2. A PART NUMBER IS NOT THE IDENTITY. Vendors revise datasheets silently and keep the ordering
     code, so the SHA-256 of the PDF bytes is part of the key. Re-adding the identical file is a
     no-op; a changed file is a new revision that must be re-approved rather than an overwrite.

ALIASES. One PDF yields a base type, one or more ordering codes and a package marking. We have
already been bitten by this: our catalogue says `IMZA65R033M2HXKSA1` while the review report says
`IMZA65R033M2H`. Every observed spelling is written into the alias table so a designer's input
resolves to one canonical folder however they type it.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from typing import Any, Optional

_HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_ROOT = os.path.join(_HERE, "parts")
_ALIAS_FILE = "_aliases.json"


class PartsStoreError(RuntimeError):
    pass


# ── identity ──────────────────────────────────────────────────────────────────────────────────
def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def normalise_mpn(mpn: str) -> str:
    """Fold the spellings of one part number together: case, whitespace and separators all vary
    between a catalogue row, a datasheet header and what a designer types."""
    return re.sub(r"[\s\-_/.]", "", str(mpn or "")).upper()


def _root(root: Optional[str] = None) -> str:
    r = root or DEFAULT_ROOT
    os.makedirs(r, exist_ok=True)
    return r


def _alias_path(root: Optional[str] = None) -> str:
    return os.path.join(_root(root), _ALIAS_FILE)


def load_aliases(root: Optional[str] = None) -> dict[str, str]:
    p = _alias_path(root)
    if not os.path.exists(p):
        return {}
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def add_aliases(canonical: str, variants: list[str], root: Optional[str] = None) -> dict[str, str]:
    table = load_aliases(root)
    for v in [canonical, *variants]:
        if v:
            table[normalise_mpn(v)] = canonical
    with open(_alias_path(root), "w", encoding="utf-8") as f:
        json.dump(table, f, indent=1, sort_keys=True)
    return table


def resolve(mpn: str, root: Optional[str] = None) -> Optional[str]:
    """A designer's input -> the canonical part folder name, or None for a genuine miss."""
    return load_aliases(root).get(normalise_mpn(mpn))


# ── the folder ────────────────────────────────────────────────────────────────────────────────
def part_dir(mpn: str, root: Optional[str] = None, create: bool = False) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", str(mpn))
    d = os.path.join(_root(root), safe)
    if create:
        os.makedirs(os.path.join(d, "curves"), exist_ok=True)
    return d


def store_datasheet(mpn: str, pdf_bytes: bytes, filename: str = "datasheet.pdf",
                    revision: Optional[str] = None, aliases: Optional[list[str]] = None,
                    root: Optional[str] = None) -> dict:
    """Put the PDF in the part's folder and record its identity.

    Re-storing byte-identical content is a NO-OP: `changed` comes back False and no version is
    created. That makes re-running the pipeline safe and keeps the library from growing a new
    revision every time someone re-uploads the same file.
    """
    d = part_dir(mpn, root, create=True)
    digest = sha256(pdf_bytes)
    src_path = os.path.join(d, "source.json")
    prev = {}
    if os.path.exists(src_path):
        with open(src_path, encoding="utf-8") as f:
            prev = json.load(f)

    if prev.get("sha256") == digest:
        add_aliases(mpn, aliases or [], root)
        return {**prev, "changed": False, "dir": d}

    with open(os.path.join(d, "datasheet.pdf"), "wb") as f:
        f.write(pdf_bytes)
    rec = {
        "part_number": mpn, "filename": filename, "sha256": digest,
        "bytes": len(pdf_bytes), "revision": revision,
        "stored_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "previous_sha256": prev.get("sha256"),
        # PROVISIONAL UNTIL PUBLISHED. Uploading a PDF has to write it somewhere — the review
        # screen, the confirm step and the figure digitiser all work from the stored profile — but
        # writing it is not the same as adding it to the library. A datasheet uploaded by mistake
        # would otherwise be in the shared parts database before anyone had looked at it, and a
        # store whose provenance is its whole purpose cannot afford to fill with wrong parts.
        # Re-uploading a corrected file for the same part number resets this: a new revision has
        # not been vouched for just because its predecessor was.
        "published": False,
    }
    with open(src_path, "w", encoding="utf-8") as f:
        json.dump(rec, f, indent=1)
    add_aliases(mpn, aliases or [], root)
    return {**rec, "changed": True, "dir": d,
            "note": ("new datasheet revision — every extracted value must be re-approved"
                     if prev else "")}


# ── immutable versioned artefacts ─────────────────────────────────────────────────────────────
def _versions(d: str, stem: str) -> list[int]:
    if not os.path.isdir(d):
        return []
    out = []
    for name in os.listdir(d):
        m = re.match(rf"^{stem}_v(\d+)\.json$", name)
        if m:
            out.append(int(m.group(1)))
    return sorted(out)


def write_extracted(mpn: str, profile: dict, root: Optional[str] = None) -> dict:
    """Write the next extraction version. Never overwrites — an earlier extraction is evidence."""
    d = part_dir(mpn, root, create=True)
    n = (_versions(d, "extracted")[-1] if _versions(d, "extracted") else 0) + 1
    profile = dict(profile)
    profile["profile_version"] = n
    profile["reviewed"] = False
    profile["reviewed_by"] = None
    path = os.path.join(d, f"extracted_v{n}.json")
    if os.path.exists(path):                       # belt and braces
        raise PartsStoreError(f"{path} already exists; extractions are immutable")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(profile, f, indent=1, ensure_ascii=False)
    return {"path": path, "version": n}


def write_confirmed(mpn: str, profile: dict, reviewed_by: str,
                    root: Optional[str] = None) -> dict:
    """Write what the designer approved (M3 uses this). Also versioned and never overwritten."""
    d = part_dir(mpn, root, create=True)
    n = (_versions(d, "confirmed")[-1] if _versions(d, "confirmed") else 0) + 1
    profile = dict(profile)
    profile["profile_version"] = n
    profile["reviewed"] = True
    profile["reviewed_by"] = reviewed_by
    profile["reviewed_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    path = os.path.join(d, f"confirmed_v{n}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(profile, f, indent=1, ensure_ascii=False)
    return {"path": path, "version": n}


def load_profile(mpn: str, kind: str = "confirmed", version: Optional[int] = None,
                 root: Optional[str] = None) -> Optional[dict]:
    """Latest (or a specific) profile. `confirmed` is what the engine may use; `extracted` is
    evidence only."""
    canonical = resolve(mpn, root) or mpn
    d = part_dir(canonical, root)
    vs = _versions(d, kind)
    if not vs:
        return None
    v = version or vs[-1]
    path = os.path.join(d, f"{kind}_v{v}.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def publish(mpn: str, published: bool = True, root: Optional[str] = None) -> dict:
    """Add a part to the library, or take it back out.

    Deliberately an explicit act. Everything up to here — upload, review, confirm, digitise — is
    about ONE design; publishing says the part is worth keeping for the next one.
    """
    d = part_dir(mpn, root, create=False)
    src = os.path.join(d, "source.json")
    if not os.path.exists(src):
        raise PartsStoreError(f"no datasheet on file for {mpn!r}")
    with open(src, encoding="utf-8") as f:
        rec = json.load(f)
    rec["published"] = bool(published)
    rec["published_utc"] = (time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                            if published else None)
    with open(src, "w", encoding="utf-8") as f:
        json.dump(rec, f, indent=1)
    return {**rec, "dir": d}


def discard(mpn: str, root: Optional[str] = None) -> dict:
    """Delete a PROVISIONAL part and everything under it.

    Guarded to unpublished parts only. A published part is in the library precisely so the report
    can answer "the machine read X, you confirmed Y" later, and deleting one would break the
    provenance trail the store exists to keep. A provisional part was never in the library, so a
    datasheet uploaded by mistake can be taken back without leaving a hole.
    """
    import shutil
    d = part_dir(mpn, root, create=False)
    src = os.path.join(d, "source.json")
    if not os.path.exists(src):
        raise PartsStoreError(f"no datasheet on file for {mpn!r}")
    with open(src, encoding="utf-8") as f:
        rec = json.load(f)
    if rec.get("published"):
        raise PartsStoreError(
            f"{mpn!r} is published, so it stays. Un-publish it first if it should leave the "
            f"library — but the stored profile is what lets the report say what was read and what "
            f"was confirmed, so removing it outright is not offered.")
    shutil.rmtree(d, ignore_errors=True)
    return {"part_number": mpn, "discarded": True}


def library(root: Optional[str] = None) -> list[dict]:
    """What the library holds — the payoff of storing anything at all. If the flow always demands a
    PDF the library never accumulates value."""
    r = _root(root)
    out = []
    for name in sorted(os.listdir(r)):
        d = os.path.join(r, name)
        if not os.path.isdir(d):
            continue
        src = os.path.join(d, "source.json")
        rec: dict[str, Any] = {"part_number": name}
        if os.path.exists(src):
            with open(src, encoding="utf-8") as f:
                s = json.load(f)
            rec.update({"sha256": s.get("sha256"), "revision": s.get("revision"),
                        "stored_utc": s.get("stored_utc"),
                        "published": bool(s.get("published")),
                        "published_utc": s.get("published_utc")})
        rec["extracted_versions"] = _versions(d, "extracted")
        rec["confirmed_versions"] = _versions(d, "confirmed")
        rec["ready"] = bool(rec["confirmed_versions"])
        rec.setdefault("published", False)
        out.append(rec)
    return out


def diff_profiles(old: dict, new: dict) -> list[dict]:
    """What changed between two profiles, so a new datasheet revision asks for re-approval of the
    CHANGED items only rather than the whole part."""
    def flat(p):
        out = {}
        for param in p.get("parameters", []):
            for i, e in enumerate(param.get("entries", [])):
                for f in ("min", "typ", "max"):
                    if f in e:
                        out[(param["key"], i, f)] = e[f]
        return out

    a, b = flat(old or {}), flat(new or {})
    rows = []
    for k in sorted(set(a) | set(b), key=lambda x: (x[0], x[1], x[2])):
        va, vb = a.get(k), b.get(k)
        if va != vb:
            rows.append({"key": k[0], "entry": k[1], "field": k[2], "was": va, "now": vb,
                         "change": ("added" if va is None else
                                    "removed" if vb is None else "changed")})
    return rows
