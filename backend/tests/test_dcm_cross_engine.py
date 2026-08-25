"""PENDING B23 — the two engines must agree about how much of the cycle runs discontinuous.

The magnetics engine and the Chapter-7 loss engine both compute a DCM fraction for the same
design, and before C263 they disagreed badly: 18.3 % against 3.3 % at 220 Vac, 29.0 % against
22.2 % at 264. Same criterion (`i < Δi/2`), same currents, same per-operating-point inductance —
the difference was WHICH inductance.

`step7_magnetic_calc` has always used a PER-ANGLE inductance: `Lth = L0_nom · k_bias(H)`, so as the
current falls through the line cycle the core's permeability recovers and L rises. The loss engine
used one value per operating point — the full-load, worst-bias figure — everywhere in the cycle.
That overstates the ripple exactly where the current is small, which is exactly where DCM is
decided, so it reported more DCM than the design has.

The fix supplies L against instantaneous current, read off the approved design's own
`L_vs_Vin_table` (each row is the as-built L at that point's crest current) and anchored at zero
bias with `L0_nom_uH`. THE ANCHOR IS NOT COSMETIC: DCM happens near the zero crossings, `np.interp`
clamps below the lowest sampled current, and without the anchor the engine still held L at the
lightest tabulated value across the very region that decides the answer — 4.0 % versus 13.0 % at
220 Vac with and without it.
"""
import copy

import pytest


@pytest.fixture(scope="module")
def built_state(sweeps):
    """State + approved design, for callers that need to rebuild a view."""
    import verify_combined_report as VCR
    return {"state": VCR._std_state(), "approved": sweeps["approved"]}


@pytest.fixture(scope="module")
def sweeps():
    import matplotlib
    matplotlib.use("Agg")
    import logging
    from fastapi.testclient import TestClient
    import app.main as main
    import verify_combined_report as VCR
    from app.mode_b.semiconductor import adapter as AD, pfc_loss_model as E
    from app.mode_b.design_state_waveforms import build_waveforms

    logging.disable(logging.WARNING)
    try:
        client = TestClient(main.app)
        state = VCR._std_state()
        r = client.post("/mode-b/step7/run-sizing", json={
            "state": state, "material_key": "edge_60", "wire_type": "magnet",
            "wire_designation": None, "max_stacks": 3, "n_top": 5})
        approved = copy.deepcopy(r.json()["top_5"][0]["result"])
        thermal = dict(AD.REFERENCE_PARTS["thermal"]); thermal["t_ambient"] = 50.0

        def run(with_bias):
            d = dict(AD.REFERENCE_DESIGN)
            d.update({"eta": 0.95, "pf": 0.99, "R_th_cs": 0.3, "nch": 2})
            main._apply_asbuilt_L(d, approved)
            if not with_bias:
                d.pop("L_bias_curve", None)
            cfg, _ = AD.build_semi_cfg(d, AD.REFERENCE_PARTS["mosfet"], AD.REFERENCE_PARTS["diode"],
                                       AD.REFERENCE_PARTS["bridge"], thermal)
            return {int(round(float(x["Vac"]))): x for x in E.simulate_vac_sweep(cfg)}

        mag = {int(float(v)): sum(s["dcm"]) / len(s["dcm"]) * 100
               for v, s in build_waveforms(state, approved)["series"].items()}
    finally:
        logging.disable(logging.NOTSET)
    return {"with": run(True), "without": run(False), "magnetics": mag, "approved": approved}


def test_the_as_built_design_supplies_an_inductance_against_current(sweeps):
    """Without the curve the fix cannot engage, and the engine silently keeps its old behaviour."""
    import app.main as main
    from app.mode_b.semiconductor import adapter as AD
    d = dict(AD.REFERENCE_DESIGN)
    main._apply_asbuilt_L(d, sweeps["approved"])
    lbc = d.get("L_bias_curve")
    assert lbc and len(lbc) == 2 and len(lbc[0]) >= 3, f"no usable L_bias_curve: {lbc}"
    xs, ys = lbc
    assert xs == sorted(xs), "currents must be increasing for interpolation"
    assert xs[0] == 0.0, "the curve is not anchored at zero bias — see the module docstring"
    assert ys[0] > ys[-1], (
        "inductance must FALL as current rises (bias roll-off); got "
        f"{ys[0]*1e6:.1f} uH at {xs[0]} A and {ys[-1]*1e6:.1f} uH at {xs[-1]:.1f} A")


def test_the_two_engines_now_agree_on_dcm(sweeps):
    """The B23 acceptance test. Before: gaps up to 15 percentage points.

    The tolerance is imported, not typed: `DCM_AGREEMENT_TOLERANCE_PCT` is the same constant the
    payload's `dcm_basis` note is generated from, so the note cannot advertise a figure the suite
    does not enforce.
    """
    from app.mode_b.design_state_waveforms import DCM_AGREEMENT_TOLERANCE_PCT as TOL
    worst = 0.0
    for vac, mag_pct in sweeps["magnetics"].items():
        got = float(sweeps["with"][vac]["DCM_%"])
        worst = max(worst, abs(got - mag_pct))
        assert abs(got - mag_pct) <= TOL, (
            f"{vac} Vac: loss engine says {got:.1f} % DCM, magnetics says {mag_pct:.1f} % — "
            f"outside the {TOL:g}-point tolerance the payload advertises (PENDING B23)")
    assert worst > 0.0, "suspiciously exact agreement — check the fixture is really comparing two engines"


def test_the_payload_note_cannot_advertise_a_tolerance_reality_does_not_meet(sweeps, built_state):
    """THE FIX FOR THE STALENESS ITSELF.

    `notes.dcm_basis` is a field the explorer can put in front of a reviewer, and it makes a live
    claim: that the two engines agree within N points. It went stale within a day of C263 — written
    at C259 when they disagreed, still asserting 29.0 % after the disagreement was fixed — and its
    test kept passing because it only checked the note EXISTED.

    So this reads the number OUT OF THE PUBLISHED NOTE and measures reality against it. Hand-editing
    the prose to claim a tighter agreement than the engines actually achieve now fails here.
    """
    import re
    from app.mode_b.design_state_waveforms import build_waveforms, DCM_AGREEMENT_TOLERANCE_PCT

    notes = build_waveforms(built_state["state"], built_state["approved"])["notes"]
    claimed = re.search(r"agree within ([\d.]+) percentage points", notes["dcm_basis"])
    assert claimed, f"the note no longer states a tolerance: {notes['dcm_basis']!r}"
    claimed_pct = float(claimed.group(1))
    assert claimed_pct == DCM_AGREEMENT_TOLERANCE_PCT, (
        f"the note advertises {claimed_pct} points but the constant is "
        f"{DCM_AGREEMENT_TOLERANCE_PCT} — the text is no longer generated from it")
    assert notes.get("dcm_tolerance_pct") == DCM_AGREEMENT_TOLERANCE_PCT

    worst = max(abs(float(sweeps["with"][v]["DCM_%"]) - m)
                for v, m in sweeps["magnetics"].items())
    assert worst <= claimed_pct, (
        f"the payload tells a reviewer the engines agree within {claimed_pct} points, but the "
        f"worst measured gap is {worst:.2f}. The note is making a false claim.")


def test_every_ccm_point_is_ccm_in_both_engines(sweeps):
    """A point either runs discontinuous or it does not; the engines must not disagree about
    WHETHER, only slightly about how much."""
    for vac, mag_pct in sweeps["magnetics"].items():
        got = float(sweeps["with"][vac]["DCM_%"])
        assert (mag_pct == 0.0) == (got == 0.0), (
            f"{vac} Vac: magnetics says {'DCM' if mag_pct else 'CCM'} but the loss engine says "
            f"{'DCM' if got else 'CCM'}")


def test_the_fix_moved_the_numbers_and_in_the_right_direction(sweeps):
    """It must actually change something, and DCM must FALL: the old model overstated the ripple
    where the current is low, so it over-reported DCM."""
    moved = [v for v in sweeps["with"]
             if abs(sweeps["with"][v]["DCM_%"] - sweeps["without"][v]["DCM_%"]) > 0.05]
    assert moved, "the bias curve changed nothing — it is probably not reaching the engine"
    for v in moved:
        assert sweeps["with"][v]["DCM_%"] < sweeps["without"][v]["DCM_%"], (
            f"{v} Vac: DCM rose after the fix ({sweeps['without'][v]['DCM_%']:.1f} -> "
            f"{sweeps['with'][v]['DCM_%']:.1f} %) — expected it to fall")


def test_the_loss_impact_is_small_and_negative(sweeps):
    """Chapter 7's numbers move, so the size and sign are recorded rather than discovered later.
    Measured worst case 66.320 -> 66.114 W."""
    for v in sweeps["with"]:
        d = sweeps["with"][v]["P_SEMI_total"] - sweeps["without"][v]["P_SEMI_total"]
        assert -0.5 < d <= 0.0, f"{v} Vac: semiconductor loss moved {d:+.3f} W, outside the recorded band"


def test_an_explicit_ripple_target_still_wins(sweeps):
    """A designer who states a peak ripple is specifying the ripple. Backing an L out of that and
    then re-biasing it would be circular, so the bias curve stands down when a target is given."""
    from app.mode_b.semiconductor import pfc_loss_model as E
    import app.main as main
    from app.mode_b.semiconductor import adapter as AD
    d = dict(AD.REFERENCE_DESIGN); d.update({"eta": 0.95, "pf": 0.99, "R_th_cs": 0.3, "nch": 2})
    main._apply_asbuilt_L(d, sweeps["approved"])
    thermal = dict(AD.REFERENCE_PARTS["thermal"]); thermal["t_ambient"] = 50.0
    cfg, _ = AD.build_semi_cfg(d, AD.REFERENCE_PARTS["mosfet"], AD.REFERENCE_PARTS["diode"],
                               AD.REFERENCE_PARTS["bridge"], thermal)
    cfg["spec"]["pct_ripple"] = 0.30          # designer states the ripple

    with_curve = {int(round(float(x["Vac"]))): x for x in E.simulate_vac_sweep(cfg)}
    cfg["spec"].pop("L_bias_curve", None)
    without = {int(round(float(x["Vac"]))): x for x in E.simulate_vac_sweep(cfg)}

    # With a stated target the bias curve must stand down entirely: results identical either way.
    for v in with_curve:
        assert with_curve[v]["DCM_%"] == without[v]["DCM_%"], (
            f"{v} Vac: the bias curve changed the result despite a stated ripple target "
            f"({without[v]['DCM_%']} -> {with_curve[v]['DCM_%']} %) — that would be circular, "
            "re-biasing an inductance that was itself backed out of the requested ripple")
        assert abs(with_curve[v]["P_SEMI_total"] - without[v]["P_SEMI_total"]) < 1e-9
