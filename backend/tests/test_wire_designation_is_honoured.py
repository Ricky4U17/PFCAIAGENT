"""A NAMED WIRE IS EITHER USED OR REFUSED — NEVER QUIETLY SWAPPED.

C272, closing PENDING B27 at the designer's instruction ("make it raise instead of substituting").

`/mode-b/step7/run-sizing` resolved the chosen wire by designation and, on no match, took
`wire_opts[0]` — the LARGEST wire in the list — with no error and nothing on screen. The design was
then sized, wound, costed and reported against a conductor the designer never picked. "I cannot
find what you asked for" must not resolve to "here is something else".

THREE BEHAVIOURS, and the middle one is why this could not be a one-line change:

  1. NO designation (`None`) -> auto-pick the best available. This is documented on the request
     model as "None = agent sweeps all AWG" and it runs through the same code path the fallback
     used. Deleting the fallback outright would have broken the sweep.
  2. A designation the SWEEP filtered out -> still honoured. The picker lists the catalog with
     min_cu_fraction=0 ("show all wires so designer can choose from full table") while the sweep
     filters at 0.10 and queries at J_max, so a wire can be visible and clickable yet absent from
     the sweep list — at 20 A per conductor, four of them are. Refusing those would 400 on a
     legitimate pick, which is a different way of not doing what the designer asked. Re-resolved
     against the unfiltered catalog; the under-sizing still shows through `current_ok=False`.
  3. A designation that is nowhere in the catalog -> 400, naming what IS available.
"""
from __future__ import annotations

import pytest

from app.magnetics.db import get_db

FSW = 70000.0
T_C = 100.0


def _opts(irms, j, min_cu):
    return get_db().get_wire_options("litz", irms, FSW, T_C, j,
                                     n_options=200, min_cu_fraction=min_cu)


def test_the_picker_offers_wires_the_sweep_filters_out():
    """The premise of behaviour 2. If this stops being true the re-resolve is dead code, and a
    test that silently guards nothing is worse than no test."""
    shown = {r["designation"] for r in _opts(20.0, 5.0, 0.0)}
    swept = {r["designation"] for r in _opts(20.0, 5.0, 0.10)}
    assert shown - swept, (
        "the picker and the sweep now agree, so the unfiltered re-resolve in run-sizing is no "
        "longer exercised — simplify it or re-point this test")


def test_every_wire_the_picker_shows_can_be_resolved():
    """Whatever is clickable must be usable. Mirrors run-sizing's resolution, including the
    unfiltered retry, for every wire the designer can actually see."""
    shown = _opts(20.0, 5.0, 0.0)
    swept = _opts(20.0, 5.0, 0.10)

    def resolve(want):
        def matches(w):
            return want in ([w.get("designation", "")]
                            + list(w.get("equivalent_designations") or []))
        hit = next((w for w in swept if matches(w)), None)
        return hit or next((w for w in shown if matches(w)), None)

    unresolvable = [r["designation"] for r in shown if resolve(r["designation"]) is None]
    assert not unresolvable, f"the picker offers wires run-sizing would refuse: {unresolvable}"


def test_a_vendor_code_still_resolves():
    """C271's equivalents must keep working through the stricter path (a saved `VS0.1x200`)."""
    swept = _opts(10.07, 5.0, 0.10)
    hit = next((w for w in swept
                if "VS0.1x200" in ([w.get("designation", "")]
                                   + list(w.get("equivalent_designations") or []))), None)
    assert hit is not None, "VS0.1x200 no longer resolves"
    assert hit["strands"] == 200.0 and hit["strand_dia_mm"] == 0.1


def test_an_unknown_designation_is_not_silently_substituted():
    """The defect itself. A name that is in no catalog must resolve to NOTHING, so the endpoint
    raises rather than sizing against `wire_opts[0]`."""
    shown = _opts(10.07, 5.0, 0.0)
    swept = _opts(10.07, 5.0, 0.10)
    for bogus in ("0.1x999", "NOT-A-WIRE", "VS9.9x9"):
        def matches(w):
            return bogus in ([w.get("designation", "")]
                             + list(w.get("equivalent_designations") or []))
        assert not any(matches(w) for w in swept), f"{bogus} matched the sweep list"
        assert not any(matches(w) for w in shown), f"{bogus} matched the full catalog"
    # and the list the error message draws on is non-empty, so the 400 is actionable
    assert swept, "no wires available at all — the error message would name nothing"


@pytest.mark.parametrize("designation", [None, "", "   "])
def test_no_designation_still_auto_picks(designation):
    """Behaviour 1. `None` means "no designer pick"; it must NOT raise."""
    want = (designation or "").strip()
    assert not want, "fixture is wrong: this should be the empty/auto-pick case"
    swept = _opts(10.07, 5.0, 0.10)
    assert swept, "auto-pick needs a non-empty list to choose from"


# ── The same three behaviours, through the real endpoint ─────────────────────
#
# Everything above resolves wires against the DB the way run-sizing does. That is a
# RE-IMPLEMENTATION, and this repo has already been bitten by a test asserting against its own
# copy of the logic while the shipped path stayed broken (FINDINGS_LOG; the first draft of
# test_inductor_loss_budget.py). The seven endpoint cases in C272's log entry were checked by
# hand and then nothing guarded them, so the 400 — the whole point of B27 — had no test at all.
#
# These drive the route. The assertion with teeth is on `result.wire_designation`, the wire the
# engine ACTUALLY WOUND, not on the response's `wire` field: that one echoes the request back
# verbatim (`"wire": req.wire_designation`), so it would have read correct all through the
# substitution bug.

@pytest.fixture(scope="module")
def sizing_client():
    from fastapi.testclient import TestClient
    from app.main import app
    return TestClient(app)


@pytest.fixture(scope="module")
def sizing_state():
    """The standard 3.6 kW Medical intake, same shape as test_regression's confirmed_state."""
    return {
        "selected_topology": "interleaved_boost_ccm",
        "selected_mode": "ccm",
        "selected_channels": 2,
        "selected_controller_mode": "analog",
        "topology_specific_inputs": {
            "switching_frequency_style": "fixed",
            "recommended_frequency_hz": 70000.0,
            "default_crest_ripple_ratio": 0.095,
            "ask_crest_ripple_ratio": True,
        },
        "intake": {
            "application": {
                "vin_rms_min": 90, "vin_rms_max": 264,
                "output_bus_voltage_v": 394,
                "output_power_w_high_line": 3600,
                "output_power_w_low_line": 1700,
                "power_factor_target": 0.99,
                "efficiency_target_percent": 98.0,
                "dc_bus_voltage_ripple_pk_pk_v": 20,
                "nominal_line_frequency_hz": 60,
                "hold_up_time_ms": 20,
                "output_power_w_nom": 3600,
            },
            "thermal": {
                "cooling_type": "fan_cooled",
                "ambient_temp_c_max": 50,
                "hotspot_limit_c": 110,
            },
            "compliance": {
                "application_class": "Medical",
                "leakage_current_limit_ua": 500,
            },
            "control": {"control_preference": "Recommend"},
            "business": {
                "cost_priority": 7, "efficiency_priority": 9,
                "power_density_priority": 8, "implementation_risk_priority": 6,
                "preferred_switch_technology": ["Si", "SiC"],
            },
            "supply": {"preferred_vendors": [], "avoid_vendors": []},
        },
    }


def _size(client, state, **over):
    body = {
        "state": state,
        "material_key": "edge_60",
        "wire_type": "litz",
        "max_height_mm": 44.45,
        "max_stacks": 3,
        "J_target": 5.0,
        "n_top": 1,
    }
    body.update(over)
    return client.post("/mode-b/step7/run-sizing", json=body)


def _wound(resp) -> str:
    """The designation the ENGINE used, off the winning candidate."""
    return resp.json()["top_5"][0]["result"]["wire_designation"]


@pytest.mark.parametrize("designation", ["0.1x400", "0.1x200"])
def test_endpoint_winds_the_wire_that_was_asked_for(sizing_client, sizing_state, designation):
    resp = _size(sizing_client, sizing_state, wire_designation=designation)
    assert resp.status_code == 200, resp.text
    assert _wound(resp) == designation


def test_endpoint_resolves_a_vendor_equivalent_to_its_primary(sizing_client, sizing_state):
    """C271's equivalents survive the stricter path: a design saved against Rupalit's own code
    still sizes, and it sizes onto the SAME physical wire rather than being refused."""
    resp = _size(sizing_client, sizing_state, wire_designation="VS0.1x200")
    assert resp.status_code == 200, resp.text
    assert _wound(resp) == "0.1x200"


def test_endpoint_honours_a_wire_only_the_picker_offers(sizing_client, sizing_state):
    """Behaviour 2, end to end. `0.05x100` is clickable in the picker and absent from the sweep;
    an explicit designer choice is not the sweep's to veto, so it must NOT be refused.

    It must not be SUBSTITUTED either, and that is the part worth asserting. This wire carries
    0.196 mm² of copper, so at ~10 A per conductor it fails every core in the catalog — 424
    evaluated, 0 passed, `top_5` empty. That is the honest physical answer for this wire, and it
    is the reason the assertion here is not `_wound(resp) == "0.05x100"`: there is no candidate to
    read a designation off. The old fallback would have returned a full set of candidates here,
    wound with the LARGEST wire in the list, and looked like a better result than the correct one.
    """
    resp = _size(sizing_client, sizing_state, wire_designation="0.05x100")
    assert resp.status_code == 200, resp.text
    d = resp.json()
    assert d["cores_evaluated"] > 0, "the pick was accepted but no sweep ran"
    # Whatever comes back must be wound with the wire that was asked for, never a substitute.
    for cand in d["top_5"]:
        assert cand["result"]["wire_designation"] == "0.05x100", (
            "run-sizing substituted a different wire for an explicit designer pick")


@pytest.mark.parametrize("bogus", ["0.1x999", "NOT-A-WIRE"])
def test_endpoint_refuses_an_unknown_designation(sizing_client, sizing_state, bogus):
    """THE DEFECT B27 CLOSED. This used to return 200 having wound the largest wire in the list."""
    resp = _size(sizing_client, sizing_state, wire_designation=bogus)
    assert resp.status_code == 400, (
        f"{bogus!r} was accepted — check what it was wound with: "
        f"{resp.json().get('top_5', [{}])[0] if resp.status_code == 200 else resp.text}")
    detail = resp.json()["detail"]
    assert bogus in detail, "the error must name what was asked for"
    assert "Available" in detail, "a refusal that lists nothing is not actionable"


def test_endpoint_reports_the_wrong_wire_type_rather_than_an_empty_list(sizing_client, sizing_state):
    """`wire_type` defaults to "magnet", so a litz designation sent without it searches the wrong
    catalog. That is how a regression test came to assert a design wound with MEW-AWG14 while
    naming 0.1x400. The 400 must say so instead of just listing magnet wires."""
    resp = _size(sizing_client, sizing_state, wire_type="magnet", wire_designation="0.1x400")
    assert resp.status_code == 400, resp.text
    assert "litz" in resp.json()["detail"]


def test_endpoint_auto_picks_when_no_wire_is_named(sizing_client, sizing_state):
    """Behaviour 1 end to end: the documented sweep path must still return a real winding."""
    resp = _size(sizing_client, sizing_state, wire_designation=None)
    assert resp.status_code == 200, resp.text
    assert _wound(resp), "auto-pick returned a candidate with no wire on it"
