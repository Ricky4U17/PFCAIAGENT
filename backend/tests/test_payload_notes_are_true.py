"""Every note a payload publishes must be TRUE OF THE DESIGN IN HAND.

`notes.*` fields are prose the Design Explorer can put in front of a reviewer. They are the least
tested thing in the system and the most quotable, which is a bad combination: a note is believed
precisely because it reads like an explanation rather than a number.

THE FAILURE THIS FILE EXISTS FOR. `notes.dcm_basis` claimed the two engines disagreed at 29.0 %.
It was written at C259 when that was true and falsified by C263 the same day, and its test kept
passing throughout because it only checked the note EXISTED and mentioned Chapter 7. An assertion
about presence does not protect content.

THE RULE. A note may state history freely — "until C263 it disagreed" is a claim about the past and
cannot rot. A note may NOT state a fact about the current design as typed prose: those figures are
generated from the payload and published alongside it as data, and this file checks the two agree.
"""
import re

import pytest


@pytest.fixture(scope="module")
def payload():
    import matplotlib
    matplotlib.use("Agg")
    import copy
    import logging
    from fastapi.testclient import TestClient
    import app.main as main
    import verify_combined_report as VCR
    from app.mode_b.design_state_waveforms import build_waveforms

    logging.disable(logging.WARNING)
    try:
        client = TestClient(main.app)
        state = VCR._std_state()
        r = client.post("/mode-b/step7/run-sizing", json={
            "state": state, "material_key": "edge_60", "wire_type": "magnet",
            "wire_designation": None, "max_stacks": 3, "n_top": 5})
        approved = copy.deepcopy(r.json()["top_5"][0]["result"])
        from app.mode_b.step15_capacitor import run_capacitor_design
        from app.mode_b.design_state_waveforms import build_capacitor_view, build_thermal_view
        from app.mode_b.semiconductor import adapter as AD
        w = build_waveforms(state, approved)
        cap = run_capacitor_design(state)
        cap["selected_cap"] = VCR.pick_selected_cap(cap)
        w["capacitor"] = build_capacitor_view(state, cap)
        design = dict(AD.REFERENCE_DESIGN)
        design.update({"eta": 0.95, "pf": 0.99, "R_th_cs": 0.3, "nch": 2})
        th = dict(AD.REFERENCE_PARTS["thermal"]); th["t_ambient"] = 50.0
        w["thermal"] = build_thermal_view(
            {"design": design, "mosfet": AD.REFERENCE_PARTS["mosfet"],
             "diode": AD.REFERENCE_PARTS["diode"], "bridge": AD.REFERENCE_PARTS["bridge"],
             "thermal": th, "tj_limit": {"fet": 150, "diode": 150, "bridge": 130}}, approved)
    finally:
        logging.disable(logging.NOTSET)
    return w


def _all_note_blocks(payload):
    """EVERY notes block in the payload, not just the top-level one.

    The first version of this file scanned only `payload["notes"]` while calling itself "every note
    a payload publishes". A probe that typed a bare current fact into the CAPACITOR note passed
    cleanly — the guard was weaker than its own name, which is the precise failure it exists to
    prevent, committed by the test itself.
    """
    out = {}
    if isinstance(payload.get("notes"), dict):
        out["notes"] = payload["notes"]
    for block in ("capacitor", "thermal", "control"):
        b = payload.get(block)
        if not isinstance(b, dict):
            continue
        if isinstance(b.get("notes"), dict):
            out[block + ".notes"] = b["notes"]
        tr = b.get("transient")
        if isinstance(tr, dict) and isinstance(tr.get("notes"), dict):
            out[block + ".transient.notes"] = tr["notes"]
    return out


def test_the_crest_versus_maximum_example_is_this_designs_own(payload):
    """The note quotes an operating point where the crest ripple and the worst-in-cycle ripple
    diverge. Those numbers used to be typed in from the reference design and would have been wrong
    for any other inductor, on a note the page displays."""
    notes = payload["notes"]
    ex = notes.get("dIpp_crest_vs_max_example")
    assert ex, "the crest-vs-max example is not published as data"

    series = payload["series"][str(int(ex["vac"]))]["summary"]
    assert abs(series["dIpp_at_crest_A"] - ex["crest"]) < 1e-3, "the example's crest is not the series' crest"
    assert abs(series["dIpp_cycle_max_A"] - ex["max"]) < 1e-3, "the example's maximum is not the series' maximum"

    # and the prose must quote the same figures it publishes
    text = notes["dIpp_crest_vs_max"]
    quoted = [float(x) for x in re.findall(r"([\d.]+) A", text)]
    assert len(quoted) >= 2, f"the note stopped quoting its figures: {text!r}"
    assert abs(quoted[0] - ex["crest"]) < 0.02 and abs(quoted[1] - ex["max"]) < 0.02, (
        f"the note says {quoted[:2]} A but the data says {ex['crest']} / {ex['max']} A")


def test_the_example_really_is_the_worst_divergence(payload):
    """If the note picked an unrepresentative point the reader would under-estimate the effect."""
    ex = payload["notes"]["dIpp_crest_vs_max_example"]
    for vin, s in payload["series"].items():
        sm = s.get("summary") or {}
        c, m = sm.get("dIpp_at_crest_A"), sm.get("dIpp_cycle_max_A")
        if c and m and c > 0:
            assert m / c <= ex["ratio"] + 1e-6, (
                f"{vin} Vac diverges by {m/c:.2f}x, more than the quoted example's {ex['ratio']}x")


def test_no_note_states_a_current_fact_as_a_bare_typed_number(payload):
    """The general rule, mechanically.

    Any note citing a decimal figure must either be talking about the PAST (history cannot rot) or
    publish that figure as data next to itself. A bare decimal describing the present is the shape
    that went stale in six hours.
    """
    # a note is historical if it says so; those may quote whatever they like
    HISTORICAL = re.compile(r"\b(until|was|used to|previously|before)\b", re.I)
    offenders = []
    for block, notes in _all_note_blocks(payload).items():
        # every non-string field in the same block is available as backing data
        flat = str({k: v for k, v in notes.items() if not isinstance(v, str)})
        for key, text in notes.items():
            if not isinstance(text, str) or HISTORICAL.search(text):
                continue
            for num in re.findall(r"\b\d+\.\d+\b", text):
                if num not in flat and float(num) not in (2.0, 3.0):
                    offenders.append(f"{block}.{key}: {num}")
    assert not offenders, (
        "these notes state a current fact as typed prose with nothing backing it: "
        + "; ".join(offenders)
        + ". Generate the figure from the payload and publish it alongside, or say it is history.")


def test_every_note_key_is_prose_or_a_published_number(payload):
    """Structural: notes must be readable strings or machine-usable numbers, not half-formed."""
    blocks = _all_note_blocks(payload)
    assert len(blocks) >= 3, (
        f"only found note blocks {sorted(blocks)} — the scan is missing some, which is how the "
        "first version of this file passed a probe it should have caught")
    for block, notes in blocks.items():
        for key, v in notes.items():
            assert isinstance(v, (str, int, float, dict)), f"{block}.{key} is a {type(v).__name__}"
            if isinstance(v, str):
                assert len(v) > 20, f"{block}.{key} is too short to be an explanation: {v!r}"
