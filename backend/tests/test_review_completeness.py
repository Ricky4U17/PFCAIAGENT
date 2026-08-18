"""EVERY VALUE THE FLOW HOLDS MUST REACH ITS REVIEW ROW — checked across every datasheet on file.

WHY THIS FILE EXISTS. `_scalar_entry` was added at C227 to keep a digitised curve out of a slot
expecting one value, and was written as an allow-list: "a number in typ or max". It then swallowed
one whole category of legitimate value per release:

    C228   a LOWER bound   V_DSS, 650 V, so the screen asked the designer to retype it
    C229   a TEXT value    device_class, on all seven datasheets - the "1 value still
                           unsupplied" banner that appeared on every parameters tab

Both times the value had been extracted perfectly and was discarded three layers downstream, and
both times it presented as an extraction bug. Both were found by a designer running the GUI, not
by this suite, because every existing test asserts a SPECIFIC key and none asked the general
question: is anything being dropped?

That is what this file asks. It is deliberately not written against a list of keys — a list would
have to be extended for each new parameter and would go stale exactly when it mattered. It walks
whatever the profile actually contains.

The audit that found C229 lived in a scratchpad and would have vanished with the session; this is
that audit, promoted so the class of defect is closed rather than fixed twice.
"""
import os
import shutil
import tempfile

import pytest

from app.mode_b.semiconductor import datasheet_flow as DF

_SPECS = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "specs")

# (path, upload kind, device class). Every real vendor datasheet in the repo, all three kinds.
DATASHEETS = [
    ("Review/IMZA65R033M2HXKSA1.pdf", "mosfet", "sic_mosfet"),
    ("Review/PFC Boost Diode/vs-4c16ep07l-m3.pdf", "diode", "sic_schottky"),
    ("Review/PFC Boost Diode/vs-3c40cp12l-m3.pdf", "diode", "sic_schottky"),
    ("Review/PFC Boost Diode/SFAF1601G SERIES_H2105.pdf", "diode", "si_diode"),
    ("Review/PFC Boost Diode/TRS12E65H_datasheet_en_20230411.pdf", "diode", "sic_schottky"),
    ("Review/Bridge Rectifier Update/lve5060e.pdf", "bridge", "bridge_rectifier"),
    ("Bridge Rectifier Configuration/GBJ40L06.pdf", "bridge", "bridge_rectifier"),
]


def _ids(case):
    return os.path.basename(case[0])


@pytest.fixture(scope="module")
def store():
    d = tempfile.mkdtemp(prefix="review_completeness_")
    try:
        yield d
    finally:
        shutil.rmtree(d, ignore_errors=True)


def _uploaded(case, store):
    rel, kind, cls = case
    path = os.path.join(_SPECS, rel.replace("/", os.sep))
    if not os.path.exists(path):
        pytest.skip(f"{os.path.basename(rel)} not available")
    with open(path, "rb") as f:
        up = DF.upload(f.read(), kind, cls, part_number=os.path.basename(rel)[:16], root=store)
    if not up.get("ok"):
        pytest.skip(f"{os.path.basename(rel)}: {up.get('reason')}")
    return up


def _is_curve(v):
    return isinstance(v, (list, tuple))


@pytest.mark.parametrize("case", DATASHEETS, ids=_ids)
def test_no_value_the_profile_holds_is_dropped_before_the_review_row(case, store):
    """THE INVARIANT. If the profile holds a usable value for a key, the row for that key must be
    marked supplied. A row that says "unsupplied" while the value sits in the profile sends the
    designer to look up a number the agent already read."""
    up = _uploaded(case, store)
    rows = {r["key"]: r for r in up["rows"]}
    dropped = []
    for p in up["profile"].get("parameters", []):
        row = rows.get(p["key"])
        if row is None:
            continue            # not every parameter is reviewable; that is a separate decision
        best = DF._pick_entry(p.get("entries", []))
        if best is None:
            continue
        value = next((best[k] for k in ("typ", "max", "min")
                      if best.get(k) is not None), None)
        if value is None or _is_curve(value):
            continue            # a curve is not a scalar, and absent is absent
        if not row["supplied"]:
            dropped.append((p["key"], type(value).__name__, value))
    assert not dropped, f"held by the profile but reported unsupplied: {dropped}"


@pytest.mark.parametrize("case", DATASHEETS, ids=_ids)
def test_a_supplied_row_actually_carries_something(case, store):
    """The converse, so the invariant above cannot be satisfied by marking everything supplied."""
    up = _uploaded(case, store)
    for r in up["rows"]:
        if r["supplied"]:
            assert r["value"] is not None or r.get("has_curve"), (
                f"{r['key']} claims to be supplied with nothing behind it")


@pytest.mark.parametrize("case", DATASHEETS, ids=_ids)
def test_the_check_actually_examines_something(case, store):
    """A "nothing was dropped" test passes trivially if it inspects nothing. This is the guard on
    the guard: each datasheet must present a real review screen."""
    up = _uploaded(case, store)
    supplied = [r for r in up["rows"] if r["supplied"]]
    assert len(up["rows"]) >= 8, "too few review rows to be a real screen"
    assert len(supplied) >= 5, f"only {len(supplied)} supplied rows - is extraction working?"


@pytest.mark.parametrize("case", DATASHEETS, ids=_ids)
def test_the_screen_only_asks_for_what_nobody_can_supply(case, store):
    """What the parameters tab counts as outstanding. `design` rows are the designer's own inputs
    and `derived` rows are computed by the flow, so neither is a gap — anything else that remains
    must be genuinely absent from the datasheet, never something already in hand.

    This is the banner from C229, asserted rather than eyeballed.
    """
    up = _uploaded(case, store)
    outstanding = [r for r in up["rows"]
                   if not r["supplied"] and r["source_kind"] not in ("design", "derived")]
    for r in outstanding:
        assert r["value"] is None and not r.get("has_curve"), (
            f"{r['key']} is being asked for although the flow has it")
        assert r["source_kind"] == "datasheet", (
            f"{r['key']} is asked for but is sourced from {r['source_kind']!r}")
