"""A MEASUREMENT'S TEMPERATURE IS WHATEVER THE VENDOR STATED IT AT.

C278, closing PENDING B29. Found at C277 by the B19 end-to-end flow: the Toshiba TRS12E65H states
its hot forward drop as **Ta = 150**, which extracts and stores correctly as
`{"I_F": 12.0, "T_amb": 150.0}` — and every consumer asked for `conditions["T_j"]`, got nothing,
and filed a 150 degC measurement as a 25 degC one.

C277 fixed the two V_F sites, where the damage was worst: `_vf_curve_from(_vf_points(hot=False))`
builds the ENGINE's room-temperature forward-drop curve, so the hot point was being mixed into the
cold curve while the hot curve got nothing at all. This file covers the rest of the family.

THE SPLIT IS THE POINT, and it is not "convert everything". Two kinds of site read a temperature
out of a conditions dict and they want different things:

  * VENDOR-STATED conditions — leakage against temperature, the hot R_DS(on) entry, the Q_rr
    temperature coefficient, the switching-energy test point. These mean "the temperature this
    measurement was taken at", and the vendor chooses how to say it. They go through
    `measurement_temperature`.
  * OUR OWN conditions on a DIGITISED curve. `confirm_figure` writes those from the Curves tab,
    which offers a single T_j field, so `T_j` is the only key that can be there. They keep reading
    `T_j`, and a comment at each says so — otherwise the next person to run the grep "fixes" four
    sites that were already right.
"""
from __future__ import annotations

import io
import os
import re

import pytest

from app.mode_b.semiconductor.datasheet_flow import (measurement_temperature,
                                                     measurement_temperature_named)

_FLOW = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "app", "mode_b", "semiconductor", "datasheet_flow.py")


# ── the helper ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("conditions,expected", [
    ({"T_j": 150.0}, 150.0),
    ({"T_c": 100.0}, 100.0),
    ({"T_amb": 150.0}, 150.0),                 # the Toshiba's own shape
    ({"I_F": 12.0, "T_amb": 150.0}, 150.0),    # exactly what that datasheet stores
    ({"I_F": 12.0}, None),
    ({}, None),
    (None, None),
])
def test_it_reads_whichever_temperature_is_stated(conditions, expected):
    assert measurement_temperature(conditions) == expected


def test_junction_temperature_wins_when_more_than_one_is_stated():
    """T_j is what the loss model actually wants; the others are accepted as what the vendor
    published when there is nothing better."""
    assert measurement_temperature({"T_j": 150.0, "T_c": 100.0, "T_amb": 25.0}) == 150.0
    assert measurement_temperature({"T_c": 100.0, "T_amb": 25.0}) == 100.0


def test_a_junk_value_does_not_stop_a_good_one_behind_it():
    """A condition that will not parse should be skipped, not swallow the entry."""
    assert measurement_temperature({"T_j": "n/a", "T_amb": 150.0}) == 150.0
    assert measurement_temperature({"T_j": None, "T_c": 125.0}) == 125.0


def test_the_named_form_reports_which_key_it_used():
    """Anywhere the number is PRINTED, the name has to travel with it — saying T_j when the
    datasheet said T_amb is a false statement that reads exactly like a true one."""
    assert measurement_temperature_named({"T_amb": 150.0}) == (150.0, "T_amb")
    assert measurement_temperature_named({"T_j": 25.0}) == (25.0, "T_j")
    assert measurement_temperature_named({"I_F": 12.0}) == (None, None)


# ── the family ───────────────────────────────────────────────────────────────

def test_the_only_remaining_T_j_reads_are_the_deliberate_ones():
    """A COUNT, NOT A LIST — C2 and C3 each grew a site nobody re-counted, and a written-down list
    of offending sites goes stale exactly when it matters.

    Four sites legitimately read `T_j` directly: the digitised-curve conditions on the diode and
    bridge paths (`dig_vf` and `dig_hot`, twice each). Those are written by `confirm_figure` from
    the Curves tab's single T_j field, so no other key can be there.

    If this count RISES, a new site has joined the family and should almost certainly be going
    through `measurement_temperature` instead. If it FALLS, the digitised-curve conditions have
    changed shape and this test should be re-pointed rather than deleted.
    """
    src = io.open(_FLOW, encoding="utf-8").read()
    reads = re.findall(r'get\("T_j"\)', src)
    assert len(reads) == 4, (
        f"{len(reads)} direct T_j reads in datasheet_flow.py, expected 4 (the digitised-curve "
        f"conditions). A new one should use measurement_temperature() unless it genuinely "
        f"requires a junction temperature — see PENDING B29.")


def test_each_deliberate_site_says_why_it_is_deliberate():
    """A bare `get("T_j")` is indistinguishable from the defect it survived. Each of the four
    carries the reason, so the next person running the grep does not 'fix' them."""
    src = io.open(_FLOW, encoding="utf-8").read()
    assert src.count("T_j DELIBERATELY") == 4


# ── the part that actually broke ─────────────────────────────────────────────

_TOSHIBA = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "specs", "Review", "PFC Boost Diode",
    "TRS12E65H_datasheet_en_20230411.pdf")


@pytest.fixture(scope="module")
def toshiba_profile():
    """The profile as the UPLOAD path produces it, which is the only path that produces one.

    `datasheet_extract.extract()` called directly returns no parameters for this file — the vendor
    templates are applied by the upload endpoint. An earlier draft of this test called `extract`
    and skipped when it came back empty, which would have shipped the regression test for B29 in a
    permanently-skipping state: green, and covering nothing. That is the failure mode this repo
    keeps recording, so the test drives the real path instead.
    """
    if not os.path.exists(_TOSHIBA):
        pytest.skip("TRS12E65H datasheet not available")
    import shutil
    import tempfile

    from fastapi.testclient import TestClient
    from app.mode_b.semiconductor import parts_store as PS
    import app.main as main

    root = tempfile.mkdtemp(prefix="b29_")
    original = PS.DEFAULT_ROOT
    PS.DEFAULT_ROOT = root
    try:
        with io.open(_TOSHIBA, "rb") as f:
            data = f.read()
        with TestClient(main.app) as client:
            r = client.post("/mode-b/semiconductor/datasheet/upload",
                            files={"file": ("ds.pdf", io.BytesIO(data), "application/pdf")},
                            data={"kind": "diode", "device_class": "sic_schottky",
                                  "part_number": "B29-TOSHIBA"})
            assert r.status_code == 200, r.text
        yield PS.load_profile("B29-TOSHIBA", kind="extracted")
    finally:
        PS.DEFAULT_ROOT = original
        shutil.rmtree(root, ignore_errors=True)


def test_the_toshiba_states_its_hot_point_as_an_AMBIENT(toshiba_profile):
    """The premise. If the extractor ever starts writing T_j here, this part stops exercising the
    defect and the test below would pass for the wrong reason."""
    from app.mode_b.semiconductor.datasheet_flow import _entries_of
    conds = [e.get("conditions") or {} for e in _entries_of(toshiba_profile, "V_F_vs_IF")]
    assert any("T_amb" in c for c in conds), (
        f"no entry states T_amb any more, so this file no longer covers B29: {conds}")
    assert not any("T_j" in c for c in conds), (
        "an entry now states T_j, which is the key the old code already read")


def test_the_toshiba_hot_point_is_not_read_as_room_temperature(toshiba_profile):
    """THE REGRESSION THIS ENTRY EXISTS FOR, on the real part.

    Its table states V_F = 1.0 V at 6 A and 1.2 V at 12 A (25 degC), and 1.36 V at 12 A with
    **Ta = 150**. The cold set must hold the first two and NOT the third — before C277 it held all
    three, so the engine's room-temperature forward-drop curve carried a 150 degC point and the hot
    curve was empty.
    """
    from app.mode_b.semiconductor.datasheet_flow import _vf_points

    cold = [v for _i, v, _t in _vf_points(toshiba_profile, hot=False)]
    hot = [v for _i, v, _t in _vf_points(toshiba_profile, hot=True)]
    assert 1.36 not in cold, (
        f"the 150 degC forward drop is in the ROOM-TEMPERATURE set {cold} - B29 has regressed")
    assert 1.36 in hot, f"the 150 degC point should be the hot set, got {hot}"
    assert 1.0 in cold and 1.2 in cold, f"the 25 degC points went missing: {cold}"
