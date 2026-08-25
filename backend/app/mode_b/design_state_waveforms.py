"""Per-operating-point waveform series for the Design Explorer. Phase 2.

WHY THIS IS A SEPARATE MODULE FROM `design_state.py`. That module is a pure projection and a test
fails the build if it ever imports an engine, because the moment it can compute, someone will
reasonably make it derive "just one" missing value. This module DOES call the engine — deliberately
and in one place — so the boundary stays a visible architectural line rather than an eroding
convention.

CALLING THE ENGINE IS NOT RECOMPUTING. `build_view_contract` is the same entry point
`doc_report_builder` uses for report Section 4.6.2, so the explorer and the document plot the
identical series by construction. What would be recomputation is re-deriving the physics here — for
example rebuilding the ripple as `Vin*D/(L*fsw)` from a single scalar L, which is exactly what the
reference animation package does and exactly the flat-inductance divergence fixed at C255.

THE ONE CONVERSION THIS MODULE PERFORMS, and why it is safe:

    the engine stores    Ihf = dIpp / (2*sqrt(3))          (step7_magnetic_calc, line ~495)
    so we return         dIpp = 2*sqrt(3) * Ihf

That inverts the engine's own identity on the engine's own per-angle value, so `dIpp` inherits the
per-angle inductance automatically. It is arithmetic, not a model. The alternative — leaving `Ihf`
raw and letting the browser apply 2*sqrt(3) — puts a physics constant in the presentation layer,
where nothing tests it and a future reader cannot tell an identity from an assumption.
"""
from __future__ import annotations

import math
from typing import Any, Dict, Optional

# How far the magnetics engine's DCM and the Chapter-7 loss engine's DCM_% may differ before it is
# a defect rather than sampling resolution. ONE definition, read by the note below AND by
# tests/test_dcm_cross_engine.py — so the payload cannot claim a tolerance the suite does not
# enforce. The note used to state this figure as typed prose and went stale within a day of C263
# fixing the underlying disagreement, while its test kept passing because it only checked that the
# note EXISTED. Presence assertions do not protect content.
DCM_AGREEMENT_TOLERANCE_PCT = 3.0

# The engine's own RMS→peak-to-peak factor for a triangular ripple.
_TRI_RMS_TO_PP = 2.0 * math.sqrt(3.0)

# Series the explorer consumes. Anything not listed is dropped so the payload stays small and the
# contract stays explicit — a consumer cannot start depending on a key we did not mean to publish.
SERIES_KEYS = ("t_ms", "Vin", "D", "Iavg", "Ihf", "H_Oe", "Bdc", "Bac_pk", "Bmax",
               "Pcore", "Pcu", "Ptot", "dcm")


def build_capacitor_view(state: Optional[dict],
                         step15_result: Optional[dict]) -> Dict[str, Any]:
    """Per-line-voltage capacitor loading, from Chapter 5's own bank model.

    `bank_loss_table` is the same function report Chapter 5 uses for its ripple/ESR/temperature
    table, so the explorer's capacitor scene and the document cannot disagree.

    THE SELECTED PART IS THE GATE. `bank_loss_table` needs `selected_cap`, and without it Chapter 5
    silently drops its later sections — the defect that made a headless report read 171 pages
    instead of 178 until `verify_combined_report` started attaching one. Here the same absence has
    to be reported, not worked around, or the scene would show an empty panel that reads as "no
    ripple" rather than "no part chosen yet".
    """
    if not isinstance(step15_result, dict) or not step15_result:
        return {"available": False, "reason": "no approved capacitor design", "rows": []}
    if not step15_result.get("selected_cap"):
        return {"available": False,
                "reason": "no capacitor part selected yet — Chapter 5's bank model needs one",
                "rows": []}
    try:
        from app.mode_b.step15_capacitor import bank_loss_table
        tbl = bank_loss_table(step15_result, state or {}) or {}
    except Exception as exc:                      # pragma: no cover - defensive
        return {"available": False, "reason": f"engine error: {exc}", "rows": []}

    rows = tbl.get("rows") or []
    if not rows:
        return {"available": False, "reason": "the bank model produced no rows", "rows": []}
    return {
        "available": True,
        "reason": None,
        "n_caps": tbl.get("n_cap"),
        "rows": [dict(r) for r in rows],
        "worst": dict(tbl["worst"]) if tbl.get("worst") else None,
        "notes": {
            "basis": "Chapter 5's bank_loss_table — the same model the report's capacitor tables "
                     "use. T_cap is the case temperature at the entered ambient, not a rise.",
            "esr": "ESR falls as the part warms, so self-heating is self-limiting; a case rise "
                   "below 1:1 with ambient is the model working, not a bug.",
        },
    }


def build_thermal_view(semiconductor: Optional[dict],
                       approved_design: Optional[dict] = None) -> Dict[str, Any]:
    """Per-operating-point junction temperatures and the loss budget — the steady-state dashboard.

    Runs the SAME sweep `/mode-b/semiconductor/calculate` runs, through the same adapter, so the
    dashboard cannot show a different loss or a different Tj from the Results tab or Chapter 7.

    THE AS-BUILT INDUCTANCE IS APPLIED HERE TOO. Without it the sweep runs on a flat nominal and
    reports different ripple, different DCM and different losses from every other surface — which
    is C255 in one direction and B23 in the other. Both were fixed by making sure every consumer
    of this engine feeds it the same inductance, and this is a consumer.
    """
    if not isinstance(semiconductor, dict) or not semiconductor:
        return {"available": False, "reason": "no approved semiconductor selection", "rows": []}
    try:
        from app.mode_b.semiconductor import adapter as AD
        from app.mode_b.semiconductor import pfc_loss_model as engine
        from app.main import _apply_asbuilt_L

        design = dict(semiconductor.get("design") or {})
        if not design:
            return {"available": False, "reason": "the semiconductor block carries no design",
                    "rows": []}
        _apply_asbuilt_L(design, approved_design)
        cfg, _ref = AD.build_semi_cfg(design, semiconductor.get("mosfet") or {},
                                      semiconductor.get("diode") or {},
                                      semiconductor.get("bridge") or {},
                                      semiconductor.get("thermal") or {})
        rows = engine.simulate_vac_sweep(cfg)
    except Exception as exc:
        return {"available": False, "reason": f"loss engine error: {exc}", "rows": []}

    lim = semiconductor.get("tj_limit") or {}
    keep = ("Vac", "P_FET_total", "P_DIODE_total", "P_BRIDGE_total", "P_SEMI_total",
            "P_gate_driver", "Tj_FET", "Tj_DIODE", "Tj_BRIDGE_top", "T_sink_main", "DCM_%")
    out = [{k: (float(r[k]) if isinstance(r.get(k), (int, float)) else r.get(k))
            for k in keep if k in r} for r in rows]
    worst = max(out, key=lambda r: r.get("P_SEMI_total", 0.0)) if out else None
    return {
        "available": bool(out),
        "reason": None if out else "the engine produced no rows",
        "rows": out,
        "worst": worst,
        "limits": {"fet": lim.get("fet"), "diode": lim.get("diode"), "bridge": lim.get("bridge")},
        "notes": {
            "basis": "the same sweep /mode-b/semiconductor/calculate runs, with the as-built "
                     "per-point and per-angle inductance applied — so this dashboard, the Results "
                     "tab and Chapter 7 are one number.",
            "gate_drive": "P_FET_total excludes gate drive; P_gate_driver is separate because the "
                          "gate charge is dissipated in the driver and the gate resistors, not in "
                          "the channel, so it belongs in the budget but not the thermal path.",
        },
    }


def _composite(avg, t_s, vout, ripple_half, f_ripple):
    """Cycle-average bus plus the steady-state 2*f_line ripple — the scope view.

    Built server-side ON PURPOSE. A page that synthesises a waveform has started deciding what the
    design does, and the explorer's guard rejects Math.sin in the browser for exactly that reason.

    THE RIPPLE PHASE IS CONTINUOUS because it is line-locked: a load step changes its AMPLITUDE,
    not its phase, and a phase jump at t=0 would read as an artefact. The amplitude here is the
    full-load spec value and does NOT yet scale with the step — that needs Chapter 5's ripple at
    each transition's before/after load, which is settled in ANIMATION_PLAN but not wired.
    """
    if not avg or ripple_half <= 0 or not t_s:
        return []
    n = min(len(avg), len(t_s))
    return [round(vout + float(avg[k]) + ripple_half * math.sin(2.0 * math.pi * f_ripple * t_s[k]), 4)
            for k in range(n)]


def build_control_view(control_inputs: Optional[dict],
                       fline_Hz: Optional[float] = None,
                       bus_ripple_pp_V: Optional[float] = None) -> Dict[str, Any]:
    """Both loop Bodes, the compensation values and the step-load transient. Phase 4.

    TAKES ALREADY-MAPPED INPUTS ON PURPOSE. `main._control_inputs_from_step16` turns the GUI's
    `step16_params` into the engine's input dict, and the combined report calls it before building
    Chapter 6. This function accepts that same dict rather than re-deriving it, so there is exactly
    one mapper and the Bode this page draws is the Bode the document draws. Re-mapping here would
    be a second interpretation of the designer's control specs — the C255 shape.

    THE BODE IS A STATIC PLOT, and the page must keep it that way. A frequency response has no time
    coordinate, so a marker sliding along it while a transient plays would be meaningless; the
    scenes connect the two by annotation instead (ANIMATION_PLAN, transient-scene traps).

    THE TRANSIENT IS A SMALL-SIGNAL RESULT. `compute_step12_transient` takes the step response of
    the closed-loop output impedance built from this design's compensator — a genuine closed-loop
    response, not the shaped exponential the reference package uses. But it is linear: a 0→100 %
    load step is not small-signal, and there is no slew limit or error-amp clamp in it. The caller
    must say so on the page.
    """
    if not isinstance(control_inputs, dict) or not control_inputs:
        return {"available": False, "reason": "no approved control design", "loops": {}}

    out: Dict[str, Any] = {"available": False, "reason": None, "loops": {}}
    try:
        from app.mode_b.step16_step10_iloop import compute_step10_iloop
        from app.mode_b.step16_step11_vloop import compute_step11_vloop
        from app.mode_b.step16_step12_transient import compute_step12_transient
    except Exception as exc:                      # pragma: no cover - defensive
        return {"available": False, "reason": f"control engine unavailable: {exc}", "loops": {}}

    def _loop(fn, name):
        d = fn(control_inputs) or {}
        bode = d.get("bode") or []
        rows = d.get("rows") or []
        return {
            "bode": [{"vac": b.get("vac"), "pout": b.get("pout"), "f": list(b.get("f") or []),
                      "ogain": list(b.get("ogain") or []), "ophase": list(b.get("ophase") or [])}
                     for b in bode],
            # crossover and phase margin per operating point — the two numbers a reviewer looks for
            "points": [{"vac": r.get("vac"), "pout": r.get("pout"),
                        "fco": r.get("fco"), "pm": r.get("pm")} for r in rows],
            "name": name,
        }, d

    try:
        iloop, d10 = _loop(compute_step10_iloop, "current loop")
        vloop, d11 = _loop(compute_step11_vloop, "voltage loop")
    except Exception as exc:
        return {"available": False, "reason": f"loop engine error: {exc}", "loops": {}}

    # compensation values for the loop block diagram — scalars the engine already resolved
    iloop["comp"] = {k: d10.get(k) for k in ("ric", "cic1", "cic2", "fz", "fp", "fco_nom", "pm_nom")
                     if d10.get(k) is not None}
    src11 = d11.get("src") or {}
    vloop["comp"] = {k: src11.get(k) for k in ("fcv", "gmv", "hv", "r1", "r4", "r_c", "vramp")
                     if src11.get(k) is not None}
    out["loops"] = {"current": iloop, "voltage": vloop}

    try:
        d12 = compute_step12_transient(control_inputs) or {}
        # `t` and the traces are numpy arrays. `arr or []` asks an array for its truth value and
        # raises "ambiguous" — never use `or` as a None-guard on engine output.
        def _seq(v):
            return list(v) if v is not None else []
        t = _seq(d12.get("t"))
        vout_v = float(d12.get("vout") or 0.0)
        f_ripple = 2.0 * float(fline_Hz or 60.0)          # bus ripple is at TWICE line frequency
        ripple_half = float(bus_ripple_pp_V or 0.0) / 2.0
        # 40 000 samples per trace is a simulation horizon, not a plot. Decimate for transport;
        # the peak and the recovery time come from the ENGINE's own metrics below, never from the
        # decimated trace, so thinning cannot move a reported number.
        step = max(1, len(t) // 1200)
        t_dec = [round(v, 6) for v in t[::step]]
        out["transient"] = {
            "available": bool(t),
            "vout": d12.get("vout"), "band": d12.get("band"),
            "t": t_dec,
            "transitions": [{
                "label": w.get("label"),
                "ll": [round(float(v), 4) for v in _seq(w.get("ll"))[::step]],
                "hl": [round(float(v), 4) for v in _seq(w.get("hl"))[::step]],
                # The scope view the designer asked for: cycle-average PLUS the steady-state
                # twice-line-frequency ripple. Built here, not in the browser — a page that
                # synthesises a waveform has started deciding what the design does, and the guard
                # on the explorer files rejects Math.sin for exactly that reason.
                "ll_composite": _composite(_seq(w.get("ll"))[::step], t_dec, vout_v, ripple_half,
                                           f_ripple),
                "hl_composite": _composite(_seq(w.get("hl"))[::step], t_dec, vout_v, ripple_half,
                                           f_ripple),
            } for w in (d12.get("waves") or [])],
            "rows": [dict(r) for r in (d12.get("rows") or [])],
            "worst_ll": dict(d12["worst_ll"]) if d12.get("worst_ll") else None,
            "worst_hl": dict(d12["worst_hl"]) if d12.get("worst_hl") else None,
            "notes": {
                "basis": "step response of the closed-loop output impedance built from this "
                         "design's compensator — a real closed-loop result, not a shaped curve.",
                "small_signal": "LINEAR small-signal model. A 0-100 % load step is not "
                                "small-signal: no slew limit, no error-amp clamp. Say so on the "
                                "page.",
                "band_vs_ripple": "the recovery band is measured on the CYCLE-AVERAGE bus, not on "
                                  "the instantaneous trace — steady-state 2*f_line ripple is "
                                  "larger than the band and would otherwise read as a permanent "
                                  "violation.",
                "decimation": f"traces thinned by {step}x for transport; peak and t_rec come from "
                              "the engine's own metrics, not from these samples.",
            },
        }
    except Exception as exc:
        out["transient"] = {"available": False, "reason": f"transient engine error: {exc}"}

    out["available"] = bool(out["loops"])
    return out


def _summary(s: Dict[str, Any]) -> Dict[str, Any]:
    """Where the crest is, and where the ripple actually peaks — which are NOT the same point.

    THIS IS A TRAP WORTH NAMING. `points[].dIL_pp_A` in the design-state export is the ripple AT
    THE LINE CREST, and it matches this series at the crest to within 0.02 % at every operating
    point. But the ripple peaks where `Vin·D` peaks, and at high line that is nowhere near the
    crest: at 264 Vac the crest ripple is 1.77 A while the worst in the cycle is 8.38 A at
    t = 1.55 ms — 4.7x larger.

    Both numbers are correct and they answer different questions. A scene that draws the envelope
    beside a panel reading the crest value, with neither labelled, looks exactly like a defect. So
    the indices and both values are published here and the UI names them.
    """
    dipp, vin_s, t_ms = s.get("dIpp") or [], s.get("Vin") or [], s.get("t_ms") or []
    if not dipp or not vin_s:
        return {}
    i_crest = max(range(len(vin_s)), key=lambda i: vin_s[i])
    i_max = max(range(len(dipp)), key=lambda i: dipp[i])
    return {
        "i_crest": i_crest,
        "i_dIpp_max": i_max,
        "dIpp_at_crest_A": round(float(dipp[i_crest]), 4),
        "dIpp_cycle_max_A": round(float(dipp[i_max]), 4),
        "t_ms_at_dIpp_max": round(float(t_ms[i_max]), 4) if t_ms else None,
        "t_ms_at_crest": round(float(t_ms[i_crest]), 4) if t_ms else None,
    }


def build_waveforms(state: Optional[dict],
                    approved_design: Optional[dict]) -> Dict[str, Any]:
    """Per-Vin half-line-cycle series, as the report's Section 4.6.2 plots them.

    Returns `{"available": bool, "reason": str|None, "vins": [...], "series": {vin: {...}}}`.
    Never raises for missing inputs: an explorer scene must be able to say *why* it has nothing to
    draw, and an exception one layer down cannot say anything.
    """
    if not isinstance(approved_design, dict) or not approved_design:
        return {"available": False, "reason": "no approved inductor design", "vins": [], "series": {}}

    try:
        from app.mode_b.step7_magnetic_calc import build_view_contract
        contract = build_view_contract(approved_design, state or {}) or {}
    except Exception as exc:                      # pragma: no cover - defensive
        return {"available": False, "reason": f"engine error: {exc}", "vins": [], "series": {}}

    wbv = contract.get("waveforms_by_vin") or {}
    if not wbv:
        return {"available": False,
                "reason": "the engine produced no per-Vin waveforms for this design",
                "vins": [], "series": {}}

    series: Dict[str, Dict[str, Any]] = {}
    for vin, w in wbv.items():
        if not isinstance(w, dict):
            continue
        out = {k: list(w[k]) for k in SERIES_KEYS if k in w}
        ihf = out.get("Ihf")
        if ihf:
            # peak-to-peak ripple, inverted from the engine's own RMS (see module docstring)
            out["dIpp"] = [round(_TRI_RMS_TO_PP * float(v), 6) for v in ihf]
        out["summary"] = _summary(out)
        series[str(vin)] = out

    return {
        "available": bool(series),
        "reason": None if series else "no usable series",
        # numeric order, so a consumer can zip these against design_state points[]
        "vins": sorted(series.keys(), key=lambda v: float(v)),
        "series": series,
        "n_points": len(next(iter(series.values())).get("t_ms", [])) if series else 0,
        "notes": {
            "dIpp": "peak-to-peak inductor ripple, = 2*sqrt(3) * Ihf (the engine stores the "
                    "triangular RMS). Inverted server-side so no physics constant lives in the "
                    "browser.",
            "dIpp_crest_vs_max": "points[].dIL_pp_A is the ripple AT THE LINE CREST. The cycle "
                    "maximum is a different and often much larger number at high line (1.77 A vs "
                    "8.38 A at 264 Vac on the reference design). Both are in `summary`; label "
                    "whichever you draw.",
            "dcm": "Per-angle DCM flag from the MAGNETICS engine (`Iavg < dIpp/2`, "
                   "step7_magnetic_calc), exported at C259 so a scene can shade exactly the "
                   "angles the engine flagged instead of restating the criterion here.",
            "dcm_basis": (
                "This is the MAGNETICS engine's DCM. Until C263 it disagreed sharply with "
                "Chapter 7's `DCM_%` (22.2 % here against 29.0 % at 264 Vac, 3.3 vs 18.3 at 220) "
                "because the loss engine used one full-load inductance across the whole cycle "
                "while this one uses the per-angle L. That is fixed: the two now agree within "
                f"{DCM_AGREEMENT_TOLERANCE_PCT:g} percentage points and never disagree about "
                "WHETHER a point runs discontinuous. A small residual remains — this engine "
                "evaluates k_bias(H) continuously, the loss engine interpolates L from ten "
                "samples — so a scene showing both should still name which basis it is on."),
            "dcm_tolerance_pct": DCM_AGREEMENT_TOLERANCE_PCT,
        },
    }
