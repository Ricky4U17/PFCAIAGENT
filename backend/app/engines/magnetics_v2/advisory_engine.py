from __future__ import annotations
from typing import Dict, Any

def _safe_float(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return default

def build_magnetic_design_v2_advisory(state: Dict[str, Any]) -> Dict[str, Any]:
    legacy = state.get("magnetic_design_data", {})
    legacy_results = legacy.get("results", {}) if isinstance(legacy, dict) else {}
    legacy_inputs = legacy.get("inputs", {}) if isinstance(legacy, dict) else {}

    L_uH = _safe_float(legacy_inputs.get("L_uH"), _safe_float(state.get("step_results", {}).get("inductor_sizing", {}).get("L_required_uH"), 235.0))
    i_pk = _safe_float(legacy_inputs.get("I_pk"), 10.0)
    i_rms = _safe_float(legacy_inputs.get("I_rms"), 7.0)
    turns_est = _safe_float(legacy_results.get("Turns_est"), 10.0)
    wire_area_mm2 = _safe_float(legacy_results.get("Wire_Area_mm2"), 2.0)
    ap_required_cm4 = _safe_float(legacy_results.get("Ap_required_cm4"), 1.0)

    recommended_core_family = "Kool Mµ / ferrite shortlist"
    turns_integerized = max(1, int(round(turns_est)))
    bmax_est_t = min(0.55, 0.18 + 0.008 * turns_integerized)
    dc_copper_loss_w = max(0.1, 0.015 * (i_rms ** 2) * max(turns_integerized, 1) / max(wire_area_mm2, 0.2))
    ac_copper_loss_w = max(0.05, 0.35 * dc_copper_loss_w)
    total_copper_loss_w = dc_copper_loss_w + ac_copper_loss_w
    saturation_margin_est = max(1.0, 1.35 - 0.002 * i_pk)
    winding_fill_comment = "acceptable" if wire_area_mm2 < 10 else "review window utilization"

    return {
        "status": "advisory_ready",
        "blocking": False,
        "recommended_core_family": recommended_core_family,
        "derived_estimates": {
            "L_target_uH": L_uH,
            "I_pk_A": i_pk,
            "I_rms_A": i_rms,
            "Ap_required_cm4_legacy": ap_required_cm4,
            "turns_est_legacy": turns_est,
            "turns_integerized": turns_integerized,
            "wire_area_mm2_legacy": wire_area_mm2,
            "Bmax_est_T": round(bmax_est_t, 4),
            "dc_copper_loss_W_est": round(dc_copper_loss_w, 4),
            "ac_copper_loss_W_est": round(ac_copper_loss_w, 4),
            "total_copper_loss_W_est": round(total_copper_loss_w, 4),
            "saturation_margin_est": round(saturation_margin_est, 4),
        },
        "notes": [
            "Magnetic Design v2 is advisory-only in Phase 1.",
            "This starter implementation does not yet use real B-H curves or Dowell equations.",
            "Run in parallel with the legacy magnetic engine until validated.",
            f"Winding fill assessment: {winding_fill_comment}.",
        ],
        "recommended_next_upgrades": [
            "Add manufacturer core database (Magnetics Inc / Ferroxcube).",
            "Replace AC copper estimate with Dowell-based calculation.",
            "Validate Bmax against actual material curve.",
        ],
    }
