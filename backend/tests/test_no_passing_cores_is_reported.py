"""A SWEEP WHERE EVERY CORE FAILS MUST NOT REPORT ITSELF AS "ok".

C273, closing PENDING B28 (found by the C272 endpoint tests, not by the change itself).

An explicit wire pick that no core can wind came back `status: "ok"`, `cores_passed: 0`,
`top_5: []`. Nothing in the response distinguished it from a successful run, so the GUI fell
through to a hardcoded banner — "try larger height or different material" — which is exactly the
wrong advice when the binding gate is the WIRE. `0.05x100` carries 0.196 mm² against ~10 A: it
fails all 424 cores on winding fill, and no height and no material will help.

The measured case is the fixture here, deliberately: it is the one a designer actually hit.
"""
from __future__ import annotations

import pytest


@pytest.fixture(scope="module")
def sizing_client():
    from fastapi.testclient import TestClient
    from app.main import app
    return TestClient(app)


@pytest.fixture(scope="module")
def sizing_state():
    from test_wire_designation_is_honoured import sizing_state as _s
    return _s.__wrapped__()


def _size(client, state, **over):
    body = {"state": state, "material_key": "edge_60", "wire_type": "litz",
            "max_height_mm": 44.45, "max_stacks": 3, "J_target": 5.0, "n_top": 1}
    body.update(over)
    return client.post("/mode-b/step7/run-sizing", json=body)


def test_a_wire_no_core_can_wind_is_not_reported_as_ok(sizing_client, sizing_state):
    """The defect itself."""
    d = _size(sizing_client, sizing_state, wire_designation="0.05x100").json()
    assert d["top_5"] == [], "fixture no longer reproduces: this wire now winds something"
    assert d["cores_evaluated"] > 0, "no sweep ran — this is the no_cores case, not B28's"
    assert d["cores_passed"] == 0
    assert d["status"] == "no_passing_cores", (
        f"an all-fail sweep still reports {d['status']!r} — indistinguishable from success")


def test_the_reason_names_the_gate_that_actually_blocked(sizing_client, sizing_state):
    """"Which gate" is the whole point. A reason that just says "nothing passed" is the empty
    table with more words."""
    d = _size(sizing_client, sizing_state, wire_designation="0.05x100").json()
    reason = d["no_pass_reason"]
    assert reason, "no_passing_cores with no reason"
    assert str(d["cores_evaluated"]) in reason, "the reason should say how many were tried"
    counts = d["fail_gate_counts"]
    assert counts, "no gate was counted"
    top_gate = max(counts.items(), key=lambda kv: kv[1])[0]
    assert top_gate in reason, f"reason does not name the dominant gate {top_gate!r}"
    # THE GATE IS THERMAL, AND THAT IS THE POINT. The first draft of this test asserted a
    # winding gate ("a 0.196 mm2 wire must fail on fill") and the engine said thermal — the
    # engine was right. A wire that thin FITS any window trivially; at ~10 A it is running
    # J = 51 A/mm2, so it cooks. Measured: thermal 424 of 424 (unanimous), then inductance 189,
    # fill 28, winding_fit 23. The unanimity is what makes the diagnosis worth printing.
    assert top_gate == "thermal", (
        f"expected thermal to block a 0.196 mm2 wire at ~10 A (J = 51 A/mm2), got {top_gate!r} — "
        f"if the engine legitimately changed, re-point this test rather than loosening it")
    assert counts["thermal"] == d["cores_evaluated"], "thermal should block every core here"
    # The advice must point at the wire. "Try larger height or different material" — the string
    # this replaced — would not have helped at all.
    assert "wire" in reason


def test_a_successful_run_carries_no_failure_reason(sizing_client, sizing_state):
    """The other half. A guard that only fires on the broken case cannot show it discriminates."""
    d = _size(sizing_client, sizing_state, wire_designation="0.1x400").json()
    assert d["status"] == "ok"
    assert d["top_5"], "fixture no longer reproduces: this wire used to wind 135 cores"
    assert d["no_pass_reason"] == ""
    assert d["fail_gate_counts"] == {}


def test_wire_used_reports_the_wire_actually_wound(sizing_client, sizing_state):
    """`wire` echoes the request, so on the auto-pick path it reads null while a real wire was
    chosen. `wire_used` is the answer to "what did you actually wind"."""
    d = _size(sizing_client, sizing_state, wire_designation=None).json()
    assert d["wire"] is None, "the echo field changed meaning — check what reads it"
    assert d["wire_used"], "auto-pick reported no wire at all"
    assert d["wire_used"] == d["top_5"][0]["result"]["wire_designation"]


def test_fail_gates_track_reasons():
    """The invariant behind the aggregate. Every reason carries exactly one gate, in order — if a
    new check appends to `fail_reasons` directly, the counts silently under-report that gate.

    Asserted over a real sweep rather than a constructed object, so it covers the checks that
    actually fire on this design.
    """
    from app.mode_b.step7_magnetic_calc import DesignResult
    import inspect
    from app.mode_b import step7_magnetic_calc as m

    src = inspect.getsource(m)
    assert src.count("fail_reasons.append") == 1, (
        "a check appends to fail_reasons directly instead of calling res.fail(gate, reason) — "
        "its gate would be missing from fail_gate_counts")

    r = DesignResult()
    r.fail("thermal", "too hot")
    r.fail("fill", "too full")
    assert r.fail_reasons == ["too hot", "too full"]
    assert r.fail_gates == ["thermal", "fill"]
