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


# ── capacitor view (C260) ───────────────────────────────────────────────────
@pytest.fixture(scope="module")
def cap_view(built):
    import logging
    from app.mode_b.step15_capacitor import run_capacitor_design
    from app.mode_b.design_state_waveforms import build_capacitor_view
    import verify_combined_report as VCR
    logging.disable(logging.WARNING)
    try:
        cap = run_capacitor_design(built["state"])
        cap["selected_cap"] = VCR.pick_selected_cap(cap)
    finally:
        logging.disable(logging.NOTSET)
    return build_capacitor_view(built["state"], cap), cap


def test_the_capacitor_view_needs_a_selected_part_and_says_so(built):
    """`bank_loss_table` is gated on `selected_cap`, and its absence is what silently dropped seven
    pages of Chapter 5 from a headless report before the harness started attaching one. An empty
    panel reads as "no ripple"; the reason has to be reported instead."""
    from app.mode_b.step15_capacitor import run_capacitor_design
    from app.mode_b.design_state_waveforms import build_capacitor_view
    import logging
    logging.disable(logging.WARNING)
    try:
        cap = run_capacitor_design(built["state"])          # no selected_cap
    finally:
        logging.disable(logging.NOTSET)
    out = build_capacitor_view(built["state"], cap)
    assert out["available"] is False and "select" in out["reason"].lower(), out
    assert out["rows"] == []
    for empty in (None, {}):
        assert build_capacitor_view(built["state"], empty)["available"] is False


def test_the_capacitor_rows_cover_every_operating_point(built, cap_view):
    view, _ = cap_view
    assert view["available"] is True, view["reason"]
    vacs = {round(float(r["Vin_rms"])) for r in view["rows"]}
    exported = {int(p["vac_V"]) for p in built["d"]["points"]}
    assert vacs == exported, f"capacitor rows {sorted(vacs)} vs points {sorted(exported)}"


def test_the_case_sits_above_ambient_and_esr_falls_as_it_warms(built, cap_view):
    """The ESR(T) feedback, which has been mistaken for a defect before: ESR drops as the part
    warms, so the self-heating that sets the temperature is self-limiting."""
    view, _ = cap_view
    amb = float(built["state"]["intake"]["thermal"]["ambient_temp_c_max"])
    for r in view["rows"]:
        assert r["T_cap_C"] > amb, f"{r['Vin_rms']} Vac: case {r['T_cap_C']} below ambient {amb}"
    hot = max(view["rows"], key=lambda r: r["T_cap_C"])
    cold = min(view["rows"], key=lambda r: r["T_cap_C"])
    assert hot["ESR_per_cap_mohm"] < cold["ESR_per_cap_mohm"], (
        f"ESR should fall as the case warms: {cold['T_cap_C']} °C -> "
        f"{cold['ESR_per_cap_mohm']:.1f} mΩ vs {hot['T_cap_C']} °C -> "
        f"{hot['ESR_per_cap_mohm']:.1f} mΩ")


def test_the_capacitor_view_declares_its_basis(cap_view):
    view, _ = cap_view
    notes = view.get("notes") or {}
    assert "basis" in notes and "bank_loss_table" in notes["basis"], (
        "the capacitor view does not say which model produced it")


# ── control view (C261) ─────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def control_view():
    """Driven through the endpoint, so the SAME `_control_inputs_from_step16` mapping the combined
    report uses is exercised — the point of the design being that there is one mapper."""
    import matplotlib
    matplotlib.use("Agg")
    import logging
    from fastapi.testclient import TestClient
    import app.main as main
    import verify_combined_report as VCR
    logging.disable(logging.WARNING)
    try:
        r = TestClient(main.app).post("/mode-b/design-state/waveforms", json={
            "state": VCR._std_state(),
            "step16_params": {"L_uH": 235.0, "DCR_mOhm": 95.0, "C_uF": 2400.0, "ESR_mOhm": 12.7,
                              "Vout_V": 393.0, "fsw_Hz": 70000.0, "Pout_lo_W": 1700.0,
                              "Pout_hi_W": 3600.0, "eta_lo": 0.945, "eta_hi": 0.965,
                              "nch": 2, "fci_Hz": 8000.0, "fcv_Hz": 17.0}})
    finally:
        logging.disable(logging.NOTSET)
    assert r.status_code == 200, r.text
    return r.json()["control"]


def test_both_loops_publish_bode_arrays_and_their_margins(control_view):
    assert control_view["available"] is True, control_view.get("reason")
    for key in ("current", "voltage"):
        loop = control_view["loops"][key]
        assert loop["bode"] and loop["bode"][0]["f"], f"{key} loop has no Bode arrays"
        assert len(loop["bode"][0]["ogain"]) == len(loop["bode"][0]["f"])
        assert loop["points"] and loop["points"][0]["fco"] is not None, f"{key}: no crossover"
        assert loop["points"][0]["pm"] is not None, f"{key}: no phase margin"


def test_the_two_loops_are_decades_apart(control_view):
    """The design's central idea, and the thing the scene exists to show: the inner current loop
    closes inside a switching period while the outer voltage loop is deliberately far below the
    120 Hz bus ripple so it does NOT chase it and distort the input current."""
    fi = control_view["loops"]["current"]["points"][0]["fco"]
    fv = control_view["loops"]["voltage"]["points"][0]["fco"]
    assert fi > 100 * fv, f"expected wide loop separation; got fci {fi:.1f} Hz, fcv {fv:.1f} Hz"
    assert fv < 120, (
        f"the voltage loop crosses at {fv:.1f} Hz, at or above the 120 Hz bus ripple — it would "
        "modulate the current reference and distort the input current")


def test_the_recovery_band_is_narrower_than_the_bus_ripple(control_view):
    """THE TRAP THIS SCENE IS BUILT AROUND.

    The ±1 % recovery band is smaller than the steady-state 2·f_line ripple, so an absolute band
    drawn against the instantaneous trace shows the design permanently out of regulation before any
    step fires — which is what the reference package does with its own numbers. The band belongs on
    the cycle-average, and this asserts the inequality that makes that necessary.
    """
    t = control_view["transient"]
    assert t["available"] is True, t.get("reason")
    w = t["transitions"][0]
    avg_span = max(w["ll"]) - min(w["ll"])
    comp_span = max(w["ll_composite"]) - min(w["ll_composite"])
    assert comp_span > avg_span, "the composite should be wider than the average — no ripple added"
    assert t["band"] * 2 < comp_span, (
        f"band ±{t['band']:.2f} V is not narrower than the composite swing {comp_span:.1f} V; "
        "the whole reason the band is measured on the average is that ripple exceeds it")


def test_the_composite_is_built_server_side_and_aligns_with_the_time_axis(control_view):
    t = control_view["transient"]
    for w in t["transitions"]:
        for k in ("ll_composite", "hl_composite"):
            assert len(w[k]) == len(t["t"]), f"{w['label']}: {k} length != time axis"


def test_the_transient_declares_its_small_signal_basis(control_view):
    """A 0-100 % load step is not small-signal. The model has no slew limit and no error-amp clamp,
    and a page that does not say so invites "where is the clamp?" as the first question."""
    notes = control_view["transient"]["notes"]
    assert "small_signal" in notes and "clamp" in notes["small_signal"].lower()
    assert "band_vs_ripple" in notes, "the band/ripple distinction is not declared"


def test_decimation_cannot_move_a_reported_number(control_view):
    """Traces are thinned for transport; the peak and recovery time come from the engine's own
    metrics, so thinning is a display concern and can never change what is reported."""
    t = control_view["transient"]
    assert t["rows"], "no per-transition metrics"
    row = t["rows"][0]
    assert "dv_lo" in row and "trec_lo" in row
    # the reported peak must be at least as deep as anything the decimated trace shows
    assert abs(row["dv_lo"]) >= abs(min(t["transitions"][0]["ll"])) - 1e-6


def test_missing_inputs_explain_themselves_rather_than_raising(built):
    """A scene must be able to say why it has nothing to draw."""
    from app.mode_b.design_state_waveforms import build_waveforms
    for bad in (None, {}):
        out = build_waveforms(built["state"], bad)
        assert out["available"] is False and out["reason"], out
        assert out["series"] == {} and out["vins"] == []
