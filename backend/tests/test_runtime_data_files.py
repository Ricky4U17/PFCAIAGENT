"""A DELETED WORKBOOK BREAKS A SELECTOR SILENTLY, AND NOTHING SAYS SO UNTIL A DESIGNER RUNS IT.

PENDING A10 action 2. The accident that opened A10 was a DETECTION failure, not a protection
failure: `specs/` files were deleted and nobody noticed for a whole session, because the code that
loads them only runs when a designer opens the relevant page. Everything imports, the suite passes,
and the NTC/fuse/MOV/GDT/semiconductor selectors come up empty.

This turns that silence into an immediate red test.

WHY THE PATHS COME FROM THE MODULE'S OWN RESOLVERS. The first draft of this file reimplemented the
lookup — `_DATA` then `_SPEC` — and was wrong within minutes: the fuse family searches `_FUSE_SPEC`
(`specs/Improvements/FUSE`), a directory the reimplementation had never heard of, and the fuse sheet
needs `_fuse_rows` because it has TITLE rows above the real header, so the generic `_rows` read the
title as a one-column header. A check that reimplements what it is checking verifies a different
thing than production does. So this calls `*_src_path()` and the family's own reader.

WHY THE FAMILY LIST IS ENUMERATED AND NOT WRITTEN OUT. Every hand-written list in this repo has
gone stale: A10 action 1 said there was ONE untracked workbook and there were two, the download
guard named seven sites and there were eight, the iframe guard named two and there were three. The
resolvers are discovered by name, so a sixth family is covered without editing this file.
`test_the_enumeration_found_something` is the backstop — rename the resolvers and the scan would
silently cover nothing.

THREE SEPARATE PROPERTIES, because each fails on its own:
  * resolves  — production's own resolver finds a file (the selector has a source at all)
  * loads     — that file yields a real header and a data row (presence is not content: a zero-byte
                or half-synced file passes `os.path.exists` and still breaks the page)
  * tracked   — git holds a copy, so a deletion is recoverable rather than permanent
"""
from __future__ import annotations

import itertools
import os
import pathlib
import subprocess

import pytest

from app.mode_b.inputprotection import database as ip_db
from app.mode_b.semiconductor import database as sc_db

_REPO = pathlib.Path(__file__).resolve().parents[2]

# Families whose absence is a DESIGN CHOICE, not a breakage: `load_mov`/`load_gdt` return [] when
# their resolver finds nothing and the engine falls back to the built-in MOV_CATALOG (see the
# comment above `_MOV_XLSX`). If present they must still load and be tracked — only "must exist"
# is relaxed. Everything else feeds a selector that has no fallback at all.
OPTIONAL = {"inputprotection:mov", "inputprotection:gdt"}


def _ip_families():
    """Pair each `*_src_path` resolver with its own row reader, both read off the module."""
    out = []
    for attr in sorted(dir(ip_db)):
        if not attr.endswith("_src_path"):
            continue
        resolver = getattr(ip_db, attr)
        if not callable(resolver):
            continue
        prefix = attr[:-len("_src_path")]              # "_mov_src_path" -> "_mov"; "_src_path" -> ""
        kind = prefix.strip("_") or "icl"
        reader = getattr(ip_db, f"{prefix}_rows", None) or ip_db._rows
        out.append((f"inputprotection:{kind}", resolver, reader))
    return out


def _sc_families():
    """`ingest()` reads strictly from `_SPEC` — there is no local ./data copy for these three."""
    return [(f"semiconductor:{kind}",
             (lambda n=name: os.path.join(sc_db._SPEC, n)),
             sc_db._rows)
            for kind, name in sorted(sc_db._SRC.items())]


FAMILIES = _ip_families() + _sc_families()
_IDS = [f[0] for f in FAMILIES]


def _resolve(resolver):
    p = resolver()
    return p if p and os.path.exists(p) else None


def test_the_enumeration_found_something():
    """The backstop. If the resolvers are renamed this scan covers nothing, silently and greenly."""
    assert len(FAMILIES) >= 8, (
        f"only {len(FAMILIES)} workbook families discovered: {_IDS}. Families are found by looking "
        "for `*_src_path` resolvers and the `_SRC` dict — if those were renamed, every check below "
        "would pass while checking nothing.")
    for expected in ("inputprotection:icl", "inputprotection:fuse", "inputprotection:relay",
                     "semiconductor:mosfet"):
        assert expected in _IDS, f"{expected} vanished from the enumeration; found {_IDS}"


@pytest.mark.parametrize("fam", FAMILIES, ids=_IDS)
def test_every_runtime_workbook_resolves(fam):
    fam_id, resolver, _ = fam
    path = _resolve(resolver)
    if path is None and fam_id in OPTIONAL:
        pytest.skip(f"{fam_id} is optional — the engine falls back to its built-in catalog")
    assert path is not None, (
        f"{fam_id}: its resolver found no workbook. The selector that loads this comes up EMPTY at "
        "run time with no error raised anywhere — this is the A10 failure exactly.")


@pytest.mark.parametrize("fam", FAMILIES, ids=_IDS)
def test_the_resolved_workbook_actually_loads(fam):
    """Presence is not content. A truncated or zero-byte file passes `exists` and breaks the page."""
    fam_id, resolver, reader = fam
    path = _resolve(resolver)
    if path is None:
        pytest.skip("resolution is covered by its own test")
    pytest.importorskip("openpyxl")
    try:
        rows = list(itertools.islice(reader(path), 1))
    except Exception as exc:                                   # corrupt / not a workbook / no sheet
        pytest.fail(f"{fam_id}: {os.path.basename(path)} did not open with {reader.__name__}: {exc!r}")
    assert rows, f"{fam_id}: {os.path.basename(path)} has a header but no data rows"
    header = [k for k in rows[0].keys() if k not in (None, "", "None")]
    assert len(header) >= 3, (
        f"{fam_id}: {os.path.basename(path)} parsed only {len(header)} named columns {header} via "
        f"{reader.__name__} — the header row is not where that reader expects it")


@pytest.mark.parametrize("fam", FAMILIES, ids=_IDS)
def test_the_resolved_workbook_is_recoverable_from_git(fam):
    """Untracked means a deletion is PERMANENT — the thing that made A10 urgent."""
    fam_id, resolver, _ = fam
    path = _resolve(resolver)
    if path is None:
        pytest.skip("resolution is covered by its own test")
    if not (_REPO / ".git").exists():
        pytest.skip("not a git checkout")
    rel = os.path.relpath(path, _REPO).replace(os.sep, "/")
    tracked = subprocess.run(["git", "ls-files", "--error-unmatch", rel],
                             cwd=_REPO, capture_output=True).returncode == 0
    assert tracked, (
        f"{fam_id}: {rel} is UNTRACKED, so deleting it is permanent — no branch, no stash and no "
        "checkout brings it back. `git add` it.")
