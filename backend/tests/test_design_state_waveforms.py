"""Waveform series for the Design Explorer — Phase 2.

These arrays are what the animation actually draws, so the thing worth testing is not that they
exist but that they are THE SAME NUMBERS the rest of the system already reports. An animation that
disagrees with the document beside it is worse than no animation.
"""
import copy
import math

import pytest


@pytest.fixture(scope="module")
def built():
    import matplotlib
    matplotlib.use("Agg")
    import logging
    from fastapi.testclient import TestClient
    import app.main as main
    import verify_combined_report as VCR
    from app.mode_b.design_state import build_design_state
    from app.mode_b.design_state_waveforms import build_waveforms

    logging.disable(logging.WARNING)
    try:
        client = TestClient(main.app)
        state = VCR._std_state()
        r = client.post("/mode-b/step7/run-sizing", json={
            "state": state, "material_key": "edge_60", "wire_type": "magnet",
            "wire_designation": None, "max_stacks": 3, "n_top": 5})
        assert r.status_code == 200, r.text
        approved = copy.deepcopy(r.json()["top_5"][0]["result"])
    finally:
        logging.disable(logging.NOTSET)
    return {"state": state, "approved": approved,
            "w": build_waveforms(state, approved),
            "d": build_design_state(state=state, approved_design=approved)}


def test_a_series_exists_for_every_operating_point(built):
    w, d = built["w"], built["d"]
    assert w["available"] is True, w["reason"]
    assert w["n_points"] > 100, f"only {w['n_points']} samples per half cycle"
    exported = {str(int(p["vac_V"])) for p in d["points"]}
    assert set(w["vins"]) == exported, (
        f"waveform Vins {sorted(w['vins'])} do not match the export's points {sorted(exported)} — "
        "a scene would have operating points it cannot draw")


def test_the_ripple_at_the_crest_equals_the_scalar_the_export_publishes(built):
    """THE IDENTITY THAT PROVES ARRAYS AND SCALARS ARE THE SAME ENGINE.

    `points[].dIL_pp_A` is the crest ripple. If the series were rebuilt from a scalar inductance
    instead of carrying the per-angle value, this would drift at exactly the operating points where
    the bias curve matters most — which is the C255 failure in a new place.
    """
    w, d = built["w"], built["d"]
    for p in d["points"]:
        s = w["series"].get(str(int(p["vac_V"])))
        assert s and s.get("summary"), f"no series for {p['vac_V']} Vac"
        crest, scalar = s["summary"]["dIpp_at_crest_A"], p["dIL_pp_A"]
        assert abs(crest - scalar) / scalar < 0.005, (
            f"{p['vac_V']:.0f} Vac: series says {crest} A at the crest, the export's scalar says "
            f"{scalar} A — arrays and scalars have diverged")


def test_the_cycle_maximum_is_reported_separately_from_the_crest(built):
    """Both numbers are correct and they answer different questions.

    The ripple peaks where Vin*D peaks, which at high line is nowhere near the crest: measured
    1.77 A at the crest against 8.38 A worst-in-cycle at 264 Vac. A scene drawing the envelope
    beside a panel showing the crest value, unlabelled, looks precisely like a defect — so both
    have to be available for the UI to name them.
    """
    w = built["w"]
    hi = w["series"][max(w["vins"], key=float)]["summary"]
    assert hi["dIpp_cycle_max_A"] > hi["dIpp_at_crest_A"] * 2, (
        "at the highest line voltage the cycle-maximum ripple should be far above the crest "
        f"value; got max {hi['dIpp_cycle_max_A']} A vs crest {hi['dIpp_at_crest_A']} A")
    assert hi["t_ms_at_dIpp_max"] < hi["t_ms_at_crest"], (
        "the ripple peak should occur before the line crest at high line")

    lo = w["series"][min(w["vins"], key=float)]["summary"]
    assert abs(lo["dIpp_cycle_max_A"] - lo["dIpp_at_crest_A"]) / lo["dIpp_at_crest_A"] < 0.02, (
        "at low line the ripple peak and the crest should essentially coincide; got "
        f"{lo['dIpp_cycle_max_A']} vs {lo['dIpp_at_crest_A']}")


def test_dIpp_is_the_engines_own_rms_inverted_not_a_reconstruction(built):
    """The one conversion the module performs must be the exact identity, on every sample.

    Rebuilding the ripple as Vin*D/(L*fsw) from a scalar L is what the reference animation package
    does, and it is the flat-inductance divergence. Inverting the engine's own Ihf inherits the
    per-angle inductance for free.
    """
    w = built["w"]
    k = 2.0 * math.sqrt(3.0)
    for vin, s in w["series"].items():
        for ihf, dipp in zip(s["Ihf"], s["dIpp"]):
            assert abs(dipp - k * ihf) < 1e-6, f"{vin} Vac: dIpp {dipp} != 2*sqrt(3)*Ihf {k*ihf}"


def test_duty_never_leaves_the_physical_range(built):
    for vin, s in built["w"]["series"].items():
        d = s["D"]
        assert all(0.0 < v < 1.0 for v in d), (
            f"{vin} Vac: duty out of range, {min(d)}..{max(d)}")


def test_the_per_angle_dcm_mask_comes_from_the_engine(built):
    """C259. The mask is exported by the engine that owns the criterion, not restated here.

    Before C259 the engine applied `Iavg < dIpp/2` at every angle but only totalled it, so
    `dcm_fraction` could say "22 % of the half cycle" with no way to say WHICH 22 %. Shading
    without the mask would have meant a second definition of DCM in a second module, free to drift
    from the first.
    """
    w = built["w"]
    for vin, s in w["series"].items():
        assert "dcm" in s, f"{vin} Vac has no per-angle DCM mask"
        assert len(s["dcm"]) == len(s["t_ms"]), f"{vin} Vac: mask length != series length"
        assert all(isinstance(v, bool) for v in s["dcm"]), f"{vin} Vac: mask is not boolean"


def test_dcm_appears_only_at_high_line_and_grows_with_it(built):
    """The physical signature: DCM shows up near the zero crossings at high line, where the
    current is low and the ripple is not. If it ever appeared at low line, something is wrong with
    the mask or with the inductance reaching the engine."""
    w = built["w"]
    frac = {float(v): sum(s["dcm"]) / len(s["dcm"]) for v, s in w["series"].items()}
    low = [f for v, f in frac.items() if v <= 180]
    assert all(f == 0.0 for f in low), f"DCM reported at low line: { {v: f for v, f in frac.items() if v <= 180} }"
    hi = sorted((v, f) for v, f in frac.items() if v >= 220)
    assert hi and hi[-1][1] > 0, "no DCM anywhere at high line — the mask may not be wired"
    assert [f for _, f in hi] == sorted(f for _, f in hi), (
        f"DCM fraction should grow with line voltage; got {hi}")


def test_the_dcm_basis_is_declared_because_chapter_7_disagrees(built):
    """C259, and the reason this is not a bug.

    The magnetics engine and the Chapter-7 loss engine both compute a DCM fraction and they do not
    agree: 22.2 % here against 29.0 % in Chapter 7 at 264 Vac on the reference design. They define
    the current and the ripple differently and each is self-consistent. A scene that shades using
    this mask while quoting Chapter 7's percentage would be presenting two engines as one, so the
    payload has to say which basis it is publishing.
    """
    notes = built["w"].get("notes") or {}
    assert "dcm_basis" in notes, "the payload does not declare which engine's DCM this is"
    assert "Chapter 7" in notes["dcm_basis"], "the basis note does not warn about the disagreement"


def test_missing_inputs_explain_themselves_rather_than_raising(built):
    """A scene must be able to say why it has nothing to draw."""
    from app.mode_b.design_state_waveforms import build_waveforms
    for bad in (None, {}):
        out = build_waveforms(built["state"], bad)
        assert out["available"] is False and out["reason"], out
        assert out["series"] == {} and out["vins"] == []
