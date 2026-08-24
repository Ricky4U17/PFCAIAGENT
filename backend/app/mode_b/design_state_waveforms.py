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

# The engine's own RMS→peak-to-peak factor for a triangular ripple.
_TRI_RMS_TO_PP = 2.0 * math.sqrt(3.0)

# Series the explorer consumes. Anything not listed is dropped so the payload stays small and the
# contract stays explicit — a consumer cannot start depending on a key we did not mean to publish.
SERIES_KEYS = ("t_ms", "Vin", "D", "Iavg", "Ihf", "H_Oe", "Bdc", "Bac_pk", "Bmax",
               "Pcore", "Pcu", "Ptot", "dcm")


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
            "dcm_basis": "THIS IS THE MAGNETICS ENGINE'S DCM, and it does not equal Chapter 7's "
                   "`DCM_%`. Measured on the reference design with the as-built L applied: "
                   "22.2 % here against 29.0 % in Chapter 7 at 264 Vac (10.0 vs 22.0 at 230, "
                   "3.3 vs 18.3 at 220). The two engines define the current and the ripple "
                   "differently — the loss model works from a per-channel instantaneous current "
                   "and an L backed out of the requested peak ripple, this one from the "
                   "per-phase average and the as-built per-angle L. Both are self-consistent. "
                   "Any scene that shades DCM must say which basis it is on, and a scene showing "
                   "Chapter 7 numbers must not reuse this mask. Logged for the designer.",
        },
    }
