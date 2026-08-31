"""AN NTC THAT MEETS A CORRELATION IS NOT AN NTC THAT MEETS A RATING.

C284, PENDING A1. `ICL_Database.xlsx` (997 parts) carries no pulse-energy column, so the capability
is computed from disc diameter by `_energy_est_J` — a correlation, not a measurement.

THE ENTRY'S PREMISE WAS INVERTED, and measuring it is what found this. A1 says every candidate
"can only ever reach CONDITIONAL". Run against the reference design, all twelve reach **PASS** — on
the estimate. The problem is not that the soft gate refuses to pass parts; it is that it passes
them on a correlation and nothing downstream could tell. `energy_estimated` was hardcoded `True` at
the single place it was set and read NOWHERE in the codebase.

So the fix is provenance, not a new gate:

  * `resolve_pulse_energy()` returns the value AND where it came from, preferring a published Joule
    rating, then a published max-switchable-capacitance (E = ½CV², an exact conversion — a part
    that publishes only this was never a data gap), then the diameter correlation.
  * `energy_estimated` is derived from that source instead of asserted.
  * The candidate's reason line names the source rather than always saying "est.".

The verdict logic is deliberately unchanged: an adequate estimate still yields PASS, which is what
it did before. Making it stricter would remove parts from the designer's list for want of a
datasheet column, which is the failure this repo has settled against (D0b, and PENDING B27).
"""
from __future__ import annotations

import collections

import pytest

from app.mode_b.inputprotection import database as DB

DESIGN = {"vin_min": 90, "vin_max": 264, "vout": 394, "fline": 60,
          "pout_hi": 3600, "pout_lo": 1700, "eta": 0.95}


@pytest.fixture(scope="module")
def candidates():
    from app.mode_b.inputprotection.adapter import calculate_ntc
    return calculate_ntc(DESIGN, {"cout_uF": 2200})["candidates"]


# ── the resolver ─────────────────────────────────────────────────────────────

def test_a_published_joule_rating_beats_the_diameter_estimate():
    e, src = DB.resolve_pulse_energy({"energy_J": 300.0, "energy_est_J": 120.0})
    assert (e, src) == (300.0, "datasheet")


def test_a_published_switchable_capacitance_is_a_real_rating_not_a_gap():
    """E = ½CV² is exact. A vendor who publishes 'max switchable 2200 µF at 264 V' HAS stated the
    energy capability, and treating that part as DATA MISSING would be wrong."""
    e, src = DB.resolve_pulse_energy({"max_switch_uF": 2200.0, "max_switch_V": 264.0,
                                      "energy_est_J": 120.0})
    assert src == "datasheet_capacitance"
    # Compared at the precision the value is STORED at: the resolver rounds to 1 dp, the same as
    # `_energy_est_J` beside it, so asserting on the unrounded product fails on the rounding rather
    # than on the physics.
    assert e == pytest.approx(round(0.5 * 2200e-6 * 264 ** 2, 1), abs=1e-9)


def test_the_estimate_is_used_only_when_nothing_is_published():
    assert DB.resolve_pulse_energy({"energy_est_J": 120.0}) == (120.0, "estimated")
    assert DB.resolve_pulse_energy({}) == (None, None)


def test_a_capacitance_without_its_voltage_is_not_an_energy():
    """½CV² needs both. A µF figure with no stated V_ref cannot be converted, and guessing the
    voltage would manufacture a rating out of half a datasheet."""
    e, src = DB.resolve_pulse_energy({"max_switch_uF": 2200.0, "energy_est_J": 120.0})
    assert src == "estimated" and e == 120.0


# ── today's state, and the claim A1 got backwards ────────────────────────────

def test_the_catalogue_still_publishes_no_energy_rating(candidates):
    """A1's data premise. When this changes, the entry can close."""
    rows = DB.ingest()
    assert rows, "the ICL workbook did not load"
    assert not [r for r in rows if r.get("energy_J") or r.get("max_switch_uF")], (
        "the ICL catalogue now carries a published energy rating — A1 is (partly) closed")


def test_every_candidate_passes_on_an_ESTIMATE_and_says_so(candidates):
    """THE FINDING THAT CORRECTS A1. The entry says candidates can only reach CONDITIONAL; they
    all reach PASS, on a diameter correlation. That is defensible only while the record says which
    it was — which is what `energy_source` now does and a hardcoded `True` never could."""
    assert candidates, "no NTC candidates were produced"
    assert all(c.get("energy_source") == "estimated" for c in candidates)
    assert all(c.get("energy_estimated") is True for c in candidates)
    # and the reason line has to carry it into anything that renders the candidate
    assert any("est. from" in r for r in candidates[0]["reasons"])


def test_the_flag_is_derived_not_asserted():
    """`energy_estimated` was hardcoded True. A hardcoded flag cannot distinguish anything, and
    this one was also read nowhere — so it looked like provenance and carried none."""
    import inspect
    src = inspect.getsource(DB.rank)
    assert '"energy_estimated": True' not in src, "the flag is hardcoded again"
    assert "energy_source" in src


# ── the half that was unreachable: a supplied rating must arrive ─────────────

@pytest.mark.parametrize("header", [
    "Pulse energy (J)", "Pulse Energy J", "Max energy (J)", "Joule rating",
])
def test_a_supplied_energy_column_is_read(header):
    assert DB._num_any({header: 265.0}, ("pulse", "energy"), ("energy", "j"), ("joule",)) == 265.0


@pytest.mark.parametrize("header", [
    "Max switchable C (uF)", "Max Switchable Capacitance (uF)", "Switchable Capacitance uF",
])
def test_a_supplied_switchable_capacitance_column_is_read(header):
    got = DB._num_any({header: 2200.0}, ("max", "switch", "uf"), ("switchable", "capacit"),
                      ("max", "switch", "µf"))
    assert got == 2200.0


def test_the_new_lookups_do_not_match_an_existing_ICL_column():
    """The risk of widening a matcher: grabbing a column that is already there and means something
    else. A false energy rating would let a part PASS on a number nobody published."""
    rows = DB.ingest()
    assert all(r.get("energy_J") is None for r in rows)
    assert all(r.get("max_switch_uF") is None for r in rows)
    # ...while the columns that DO exist still read
    assert any(r.get("r25") for r in rows) and any(r.get("diameter_mm") for r in rows)
