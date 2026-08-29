"""ONE ROW PER WIRE, AND THE VENDOR NAMES TRAVEL WITH IT.

C271, designer finding on the Magnetics → Wire page: the litz table showed `VS0.1x200`.

`VS` is NOT a formatting bug — it is Rupalit's real product code, carried verbatim from
`backend/data/wire/litz_catalog.csv`. The actual defect was that the SAME PHYSICAL WIRE was listed
once per vendor: 200 strands of 0.1 mm appears as TRW `0.1x200`, Rupalit `VS0.1x200` and Pack
`200x0.1`, identical in OD, Cu area, resistance and frequency limits. Three rows, nothing saying
they are one wire, and — because they rank identically — competing for the same candidate slots.

TWO WAYS A CARELESS DEDUPE GETS THIS WRONG, both asserted below:

  * KEYING ON Cu AREA OR OD. `0.1x800` and `0.2x200` share OD 3.33 mm and Cu 6.2832 mm² and are
    NOT the same wire — 800 strands of 0.1 against 200 of 0.2, different strand diameter and
    therefore different skin behaviour. Collapsing them would merge two real choices.
  * FORGETTING THE DUAL-BUNDLE CONSTRUCTIONS. `2x(0.1x100)` is also 200 strands of 0.1 mm, but it
    is wound as two bundles ("1.18 per bundle") — a different winding job with a different build
    height. OD is in the key so it stays separate.

AND THE ONE THAT WOULD HAVE BEEN SILENT: `/step7/run-sizing` resolves the chosen wire by
designation, and on no match it does NOT raise — it falls back to `wire_opts[0]`, the largest wire
in the list. So collapsing without making the vendor names resolvable would have quietly rewound a
saved design onto a different wire. `equivalent_designations` is what prevents that.
"""
from __future__ import annotations

import pytest

from app.magnetics.db import get_db

# (strands, strand_dia_mm) -> every designation that is the SAME single-bundle wire
KNOWN_EQUIVALENTS = {
    (100.0, 0.1):  {"0.1x100", "VS0.1x100"},
    (200.0, 0.1):  {"0.1x200", "VS0.1x200", "200x0.1"},
    (400.0, 0.1):  {"0.1x400", "VS0.1x400", "400x0.1"},
    (200.0, 0.15): {"0.15x200", "VS0.15x200"},
}

# pairs that LOOK identical on OD/Cu but are different wires and must never be merged
MUST_STAY_SEPARATE = [
    ("0.1x800", "0.2x200",     "same OD 3.33 and Cu 6.2832, but 0.1 mm vs 0.2 mm strands"),
    ("0.1x200", "2x(0.1x100)", "same 200x0.1, but one bundle vs two — different winding"),
]


@pytest.fixture(scope="module")
def litz():
    # min_cu_fraction=0 is the display table: show everything, exclude nothing
    return get_db().get_wire_options("litz", 10.07, 70000.0, 100.0, 5.0,
                                     n_options=200, min_cu_fraction=0.0)


def _by_designation(rows):
    return {r["designation"]: r for r in rows}


def test_each_wire_appears_exactly_once(litz):
    seen = [r["designation"] for r in litz]
    assert len(seen) == len(set(seen)), f"duplicate primary designations: {seen}"
    # and no vendor alias survives as its own row
    aliases = {d for group in KNOWN_EQUIVALENTS.values() for d in group}
    primaries = set(seen)
    extra = {d for d in aliases if d in primaries} - {"0.1x100", "0.1x200", "0.1x400", "0.15x200"}
    assert not extra, f"vendor aliases still listed as separate rows: {sorted(extra)}"


@pytest.mark.parametrize("key,designations", sorted(KNOWN_EQUIVALENTS.items()),
                         ids=[f"{int(k[0])}x{k[1]}" for k in sorted(KNOWN_EQUIVALENTS)])
def test_the_vendor_names_are_kept_and_resolvable(litz, key, designations):
    """The designer asked for the vendor names to stay visible — and run-sizing needs them."""
    rows = [r for r in litz if set(r.get("equivalent_designations") or []) & designations]
    assert len(rows) == 1, (
        f"{designations} should collapse to exactly one row, found {len(rows)}: "
        f"{[r['designation'] for r in rows]}")
    row = rows[0]
    assert set(row["equivalent_designations"]) == designations, (
        f"lost a vendor name: have {set(row['equivalent_designations'])}, want {designations}")
    for e in row["equivalents"]:
        assert e.get("series"), f"{e} has no vendor/series name to display"


@pytest.mark.parametrize("a,b,why", MUST_STAY_SEPARATE, ids=[m[0] + "-vs-" + m[1]
                                                             for m in MUST_STAY_SEPARATE])
def test_different_wires_are_not_merged(litz, a, b, why):
    d = _by_designation(litz)
    assert a in d and b in d, f"{a} and {b} must both remain selectable — {why}"
    assert b not in (d[a].get("equivalent_designations") or []), f"{a} swallowed {b}: {why}"


def test_a_design_saved_against_a_vendor_code_still_resolves():
    """The silent one. run-sizing falls back to the FIRST wire on no match, so a stranded
    designation changes the winding without an error."""
    from app.main import _mag_db

    opts = _mag_db().get_wire_options("litz", 10.07, 70000.0, 100.0, 5.0,
                                      n_options=50, min_cu_fraction=0.10)

    def resolve(want):
        return next((w for w in opts
                     if want in ([w.get("designation", "")]
                                 + list(w.get("equivalent_designations") or []))), None)

    for want in ("0.1x200", "VS0.1x200", "200x0.1"):
        hit = resolve(want)
        assert hit is not None, f"{want} no longer resolves — run-sizing would silently substitute"
        assert hit["strands"] == 200.0 and hit["strand_dia_mm"] == 0.1, \
            f"{want} resolved to the wrong wire: {hit['designation']}"
