"""THE BRIDGE'S TEMPERATURE MODEL: MEASURED HOT DATA vs AN ASSUMED SCALAR (PENDING B3).

B3's original premise was `rd = 0`; that was CORRECTED on 2026-08-01 — `rd = 0.0` is right, because
`Bridge.vf()` returns the curve value and the model adds `rd·i` on top, so deriving `rd` from the
same curve slope double-counts. The real issue is the temperature model.

WHAT THE ENGINE DOES. `Bridge.vf()` interpolates between a cold and a hot V–I curve per current
point. With no hot curve it falls back to a single scalar `vf_tco`, applied at EVERY current. A real
silicon rectifier's tempco is negative only below its crossover (near rated current) and positive
above, so a constant negative tempco makes a cooler device look worse — which is why paralleling
measured as a LOSS INCREASE on 54 of 70 sampled parts. That is an artifact of the scalar.

WHAT ACTUALLY CLOSES IT, measured on 2026-08-22 rather than assumed:

    catalogue part   no hot data at all      -> vf_tco = -0.002 V/degC, dV = -0.200 V at every current
    LVE5060E         hot V_F from the table  -> dV = -0.120 V, the part's OWN measured shift

So the datasheet path does not merely add a curve, it replaces an ASSUMED tempco with a MEASURED
one — a 40% difference on this part. What it does NOT yet do is capture convergence: this datasheet
publishes V_F at a single current per temperature, so both "curves" are single points and the drop
is constant in current. Capturing the crossover needs a hot V–I FIGURE, which this vendor does not
print. The flow already warns when only one of the two figures is digitised.

WHY THESE TESTS. `test_bridge_datasheet.py` asserts the hot curve's VALUES. Nothing asserted the
consequence — that a catalogue part still runs on the scalar and says so, while a datasheet part
does not. Those are the two states a designer can actually be in.
"""
import io
import os

import pytest

from app.mode_b.semiconductor import database as sdb
from app.mode_b.semiconductor import datasheet_extract as DX
from app.mode_b.semiconductor import datasheet_flow as DF
from app.mode_b.semiconductor.adapter import _clean_block
from app.mode_b.semiconductor.pfc_loss_model import Bridge

DESIGN = {"vin_min": 90, "vin_max": 264, "vout": 393, "fline": 60, "fsw": 65000,
          "L_phi_uH": 235, "nch": 2, "pout_lo": 1700, "pout_hi": 3600, "eta": 0.95,
          "r_input": 0.2, "pf": 0.99, "R_th_cs": 0.5}
_LVE = os.path.join(os.path.dirname(__file__), "..", "..", "specs", "Review",
                    "Bridge Rectifier Update", "lve5060e.pdf")


@pytest.fixture(scope="module")
def datasheet_block():
    if not os.path.exists(_LVE):
        pytest.skip("LVE5060E datasheet not available")
    with io.open(_LVE, "rb") as f:
        prof = DX.extract(f.read(), "bridge_rectifier")["profile"]
    return DF.profile_to_block(prof, "bridge_rectifier", DESIGN)


@pytest.fixture(scope="module")
def catalogue_block():
    parts = sdb.load("bridge")
    if not parts:
        pytest.skip("bridge catalogue empty")
    return sdb.to_block(parts[0], "bridge")


def _bridge(blk):
    params, _meta = _clean_block(blk)
    return Bridge(**params)


def test_a_datasheet_bridge_carries_a_measured_hot_curve(datasheet_block):
    """The datasheet path must reach the engine's hot-curve mechanism, not the scalar fallback."""
    assert datasheet_block.get("vf_curve_hot"), \
        "no hot curve on a datasheet bridge — the engine will fall back to vf_tco"
    assert datasheet_block.get("vf_thot"), "hot curve present but its temperature is unrecorded"
    prov = datasheet_block.get("_provenance") or {}
    assert prov.get("V_F_vs_IF_hot") in ("extracted", "digitised"), (
        f"the hot curve must come from the datasheet, not be inferred "
        f"(provenance: {prov.get('V_F_vs_IF_hot')!r})")


def test_a_catalogue_bridge_has_no_hot_curve_and_falls_back_to_the_scalar(catalogue_block):
    """The state the limitation note exists for. If this ever starts passing a hot curve, the
    note in Section 7.3 must stop firing — the two are a pair."""
    assert not catalogue_block.get("vf_curve_hot"), \
        "a catalogue bridge now has a hot curve — Section 7.3's limitation note is now wrong"
    assert catalogue_block.get("vf_tco"), "no hot curve AND no tempco: temperature is unmodelled"


def test_the_measured_tempco_differs_from_the_assumed_one(datasheet_block, catalogue_block):
    """The point of the datasheet path: an assumed -0.002 V/degC is replaced by the part's own
    measured shift. On this part that is 0.120 V against 0.200 V over the same 100 degC - a 40%
    difference in the entire temperature correction, which is why it is worth uploading."""
    ds, cat = _bridge(datasheet_block), _bridge(catalogue_block)
    i = 20.0
    d_meas = float(ds.vf(i, 125.0) - ds.vf(i, 25.0))
    d_assumed = float(cat.vf(i, 125.0) - cat.vf(i, 25.0))
    assert d_meas < 0 and d_assumed < 0, "both should fall with temperature below crossover"
    assert abs(d_meas - d_assumed) > 0.02, (
        f"measured {d_meas:.3f} V and assumed {d_assumed:.3f} V agree too closely for this test to "
        "be meaningful — check the fixture parts")


def test_the_scalar_shifts_every_current_by_the_same_amount(catalogue_block):
    """The artifact itself, stated directly.

    A real rectifier's cold and hot curves converge and cross near rated current. The scalar cannot
    do that: it applies one offset everywhere, so a cooler (paralleled) device is penalised at every
    operating point. This asserts the fallback IS that flat shift, so the limitation note in
    Section 7.3 is describing something true rather than hedging.
    """
    b = _bridge(catalogue_block)
    deltas = [float(b.vf(i, 125.0) - b.vf(i, 25.0)) for i in (1.0, 5.0, 20.0, 50.0, 100.0)]
    assert max(deltas) - min(deltas) < 1e-9, (
        f"the scalar fallback is no longer a flat shift ({deltas}) — if the model gained current "
        "dependence, Section 7.3's limitation wording needs revisiting")


def test_pairing_one_digitised_curve_with_a_tabulated_point_is_flagged(datasheet_block):
    """The engine interpolates BETWEEN the two curves, so they must be the same kind of object.

    Digitising the cold V-I figure while the hot side stays a single tabulated point interpolates a
    300-point shape against a flat line. The flow raises a `check` note for exactly this, and this
    datasheet is the case that provokes it: it prints a cold V-I figure but no hot one.
    """
    notes = {n.get("key"): n for n in (datasheet_block.get("_notes") or [])
             if isinstance(n, dict)}
    hot = notes.get("V_F_vs_IF_hot")
    if hot is None:
        pytest.skip("both curves came from the same source — nothing to pair-check here")
    assert hot.get("severity") == "check"
    assert "interpolat" in hot.get("message", "").lower()
