"""
magnetic_fea/advisory_engine.py
I-10 fix: when enable_magnetic_design_v2 is off, magnetic_design_v2_results has no
derived_estimates. Now falls back to magnetic_design_data (from core magnetic_design step)
for Bmax and saturation estimates so FEA screening always uses real values.
"""
from __future__ import annotations
from typing import Dict, Any, Tuple


def _safe_float(v, d=0.0):
    try:
        return float(v)
    except Exception:
        return d


def _extract_fea_inputs(state: Dict[str, Any]) -> Tuple[float, float]:
    """
    Returns (bmax, sat_margin) by trying sources in priority order:
      1. magnetic_design_v2_results.details.derived_estimates  (v2 enabled)
      2. magnetic_design_data (core step — always present when v2 disabled)
      3. Static defaults (0.28, 1.2) as last resort
    """
    # Source 1 — v2 advisory derived estimates
    mag_v2   = state.get("magnetic_design_v2_results", {})
    details  = mag_v2.get("details", {}) if isinstance(mag_v2, dict) else {}
    derived  = details.get("derived_estimates", {}) if isinstance(details, dict) else {}
    bmax_v2  = derived.get("Bmax_est_T")  if isinstance(derived, dict) else None
    sat_v2   = derived.get("saturation_margin_est") if isinstance(derived, dict) else None

    if bmax_v2 is not None and sat_v2 is not None:
        return _safe_float(bmax_v2, 0.28), _safe_float(sat_v2, 1.2)

    # Source 2 — core magnetic_design_data (always written by magnetic_design_node)
    mag_data = state.get("magnetic_design_data", {})
    if isinstance(mag_data, dict):
        bmax_core = mag_data.get("Bpk") or mag_data.get("B_peak_T")
        # Rough sat margin from i_sat and i_peak if stored
        i_sat = mag_data.get("i_sat_a")
        i_pk  = (state.get("step_results", {})
                     .get("input_processing", {})
                     .get("Ipk"))
        if bmax_core is not None:
            bmax = _safe_float(bmax_core, 0.28)
            if i_sat is not None and i_pk is not None and float(i_pk) > 0:
                sat_margin = _safe_float(i_sat) / _safe_float(i_pk)
            else:
                sat_margin = 1.2  # conservative default
            return bmax, sat_margin

    # Source 3 — static defaults
    return 0.28, 1.2


def build_magnetic_fea_advisory(state: Dict[str, Any]) -> Dict[str, Any]:
    bmax, sat_margin = _extract_fea_inputs(state)

    local_flux_risk = "moderate"
    if bmax > 0.35 or sat_margin < 1.15:
        local_flux_risk = "high"
    elif bmax < 0.25 and sat_margin > 1.25:
        local_flux_risk = "low"

    # Determine which data source was actually used
    mag_v2  = state.get("magnetic_design_v2_results", {})
    details = mag_v2.get("details", {}) if isinstance(mag_v2, dict) else {}
    derived = details.get("derived_estimates", {}) if isinstance(details, dict) else {}
    data_source = "magnetic_design_v2 derived_estimates" if derived.get("Bmax_est_T") \
                  else ("magnetic_design_data (v2 disabled fallback)"
                        if state.get("magnetic_design_data") else "static defaults")

    return {
        "status":  "advisory_ready",
        "blocking": False,
        "fea_screening_summary": {
            "estimated_bulk_Bmax_T":             round(bmax, 4),
            "estimated_saturation_margin":       round(sat_margin, 3),
            "estimated_local_flux_crowding_risk": local_flux_risk,
            "air_gap_fringing_attention":        "yes" if local_flux_risk != "low" else "monitor",
            "recommended_next_tool":             "FEMM / PyFEMM starter path",
            "data_source":                       data_source,
        },
        "notes": [
            "Magnetic FEA Agent is advisory-only in Phase 3.",
            f"Input data sourced from: {data_source}.",
            "Screening layer before real FEMM/Maxwell integration.",
        ],
    }
