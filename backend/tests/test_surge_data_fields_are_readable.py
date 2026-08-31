"""THE MISSING SURGE FIELDS CAN NOW BE READ WHEN SOMEBODY SUPPLIES THEM.

C283, opening up PENDING A2 (MOV `Vc @ In`, missing on 1140/1140) and A3 (GDT impulse sparkover and
follow current, missing on 172/172). Both are DATA gaps — the values live in vendor datasheets and
the Digi-Key parametric export does not carry them — but investigating them turned up a CODE
problem underneath, which is what this file guards.

NEITHER FIELD COULD HAVE BEEN READ EVEN AFTER THE DATA ARRIVED:

  * MOV used `_pick(r, "vc", "imax")`, which requires BOTH substrings. It accepts `Vc @ Imax (V)`
    and misses `Vc @ In (V)` — the exact header A2's own "done when" tells you to add. Five of six
    realistic spellings missed, so the workbook edit that was supposed to close A2 would have
    changed nothing and the check would have gone on printing DATA MISSING.
  * GDT was worse: `v_impulse_spark` and `follow_current` were HARDCODED to `None`. No column of
    any name could ever have been read.

So the tests below are in two halves. The first asserts the fields are absent TODAY — that is the
honest state and the reason Chapter 9 reports DATA MISSING. The second feeds a workbook row that
HAS the values and asserts they arrive, which is the half that was broken and silent.
"""
from __future__ import annotations

import pytest

from app.mode_b.inputprotection import database as DB


# ── today: the data is genuinely absent, and that must stay visible ──────────

def test_the_mov_catalogue_still_has_no_clamping_voltage():
    """PENDING A2's premise. If this ever starts passing, the data has arrived and A2 can close —
    so the test names that rather than being deleted as 'wrong'."""
    movs = DB.ingest_mov()
    assert movs, "the MOV workbook did not load at all"
    have = [m for m in movs if m.get("vc_imax") is not None]
    assert not have, (
        f"{len(have)} MOV parts now carry Vc@In — the A2 data gap is (partly) closed; update the "
        f"entry and re-point this test rather than removing it")


def test_the_gdt_catalogue_still_has_neither_surge_field():
    """PENDING A3's premise, same reasoning."""
    gdts = DB.ingest_gdt()
    assert gdts, "the GDT workbook did not load at all"
    assert not [g for g in gdts if g.get("v_impulse_spark") is not None]
    assert not [g for g in gdts if g.get("follow_current") is not None]


def test_the_loosened_header_rules_do_not_match_an_existing_column():
    """THE RISK THE C283 FIX INTRODUCED. Widening the matcher from one spelling to several could
    make it grab a column that is already there and mean something else — a false value is far
    worse than the DATA MISSING it replaces, because Criterion A would then PASS on it."""
    movs, gdts = DB.ingest_mov(), DB.ingest_gdt()
    assert all(m.get("vc_imax") is None for m in movs)
    # the GDT workbook HAS an `Impulse Discharge Current` column; "impulse"+"spark" must not take it
    assert all(g.get("v_impulse_spark") is None for g in gdts)
    assert any(g.get("imax_impulse") for g in gdts), "the discharge-current column stopped reading"


# ── the half that was broken: a supplied value must actually arrive ──────────

@pytest.mark.parametrize("header", [
    "Vc @ In (V)",                     # exactly what PENDING A2 asks for — used to MISS
    "Vc @ In",
    "Vc @ Imax (V)",                   # the only spelling the old matcher accepted
    "Max Clamping Voltage @ In (V)",
    "Maximum Clamping Voltage",
    "Clamping Voltage Vc @ In (V)",
])
def test_a_supplied_mov_clamping_voltage_is_read_under_any_reasonable_header(header):
    got = DB._num_any({header: 775.0}, ("vc", "in"), ("vc", "imax"),
                      ("clamp", "volt"), ("clamping",))
    assert got == 775.0, f"a Vc column headed {header!r} would still be ignored"


@pytest.mark.parametrize("header", [
    "Impulse Sparkover (V)",
    "Impulse Spark Over @ 1kV/us",
    "Impulse Sparkover @ dV/dt (V)",
    "Dynamic Sparkover (V)",
])
def test_a_supplied_gdt_impulse_sparkover_is_read(header):
    assert DB._num_any({header: 800.0}, ("impulse", "spark"), ("dynamic", "spark")) == 800.0


@pytest.mark.parametrize("header", ["Follow Current (A)", "Follow Current", "Holdover Current (A)"])
def test_a_supplied_gdt_follow_current_is_read(header):
    assert DB._num_any({header: 0.15}, ("follow", "current"), ("holdover",)) == 0.15


def test_the_discharge_current_column_is_not_mistaken_for_sparkover():
    """The one collision that matters, asserted directly: `Impulse Discharge Current` is already in
    the GDT workbook and is a CURRENT, not a voltage."""
    row = {"Impulse Discharge Current (8/20us)": 3000.0}
    assert DB._num_any(row, ("impulse", "spark"), ("dynamic", "spark")) is None
    assert DB._num_any(row, ("follow", "current"), ("holdover",)) is None


def test_a_blank_or_dash_cell_reads_as_missing_not_zero():
    """A dash is how this export writes 'not published'. Read as 0 it would be a clamping voltage
    of zero volts — which would PASS every margin check ever written."""
    for empty in ("", "-", "—", None, "N/A"):
        assert DB._num_any({"Vc @ In (V)": empty}, ("vc", "in")) is None, repr(empty)
