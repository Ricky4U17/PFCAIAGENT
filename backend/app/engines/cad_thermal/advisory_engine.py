"""
cad_thermal/advisory_engine.py
I-9 fix: thermal_results from bidirectional_thermal_agent stores results as:
  {"thermal_data": {"total_loss_w":..., "rth_required_c_per_w":...}, "thermal_status":...}
This engine previously read top-level thermal_results["temperature_rise_c"] and
thermal_results["required_rth_c_per_w"] which don't exist, so both always defaulted.
Now reads nested thermal_data correctly, with fallback to top-level for forward compat.
"""
from __future__ import annotations
from typing import Dict, Any


def _safe_float(v, d=0.0):
    try:
        return float(v)
    except Exception:
        return d


def build_cad_thermal_integration_advisory(state: Dict[str, Any]) -> Dict[str, Any]:
    thermal_results = state.get("thermal_results", {})

    # I-9: read from nested thermal_data first, fall back to top-level for compat
    thermal_data = thermal_results.get("thermal_data", {}) \
        if isinstance(thermal_results, dict) else {}

    # rth_required is stored under thermal_data in bidirectional_thermal_agent output
    target_rth = _safe_float(
        thermal_data.get("rth_required_c_per_w")
        or thermal_results.get("required_rth_c_per_w"),  # legacy top-level fallback
        0.6,
    )

    # Derive temperature rise: Ploss * Rth_required (approximate)
    total_loss = _safe_float(thermal_data.get("total_loss_w"), 0.0)
    ambient    = _safe_float(
        state.get("intake", {}).get("thermal", {}).get("ambient_temp_c_max"), 50.0
    )
    # Use intake max_temp_rise when available (more accurate than back-calculating)
    max_rise = _safe_float(
        state.get("intake", {}).get("thermal", {}).get("max_temp_rise_c"), 40.0
    )
    hotspot = ambient + max_rise

    return {
        "status":  "advisory_ready",
        "blocking": False,
        "mechanical_summary": {
            "estimated_hotspot_temp_c":            round(hotspot, 2),
            "required_thermal_resistance_c_per_w": round(target_rth, 3),
            "estimated_total_loss_w":              round(total_loss, 2),
            "heatsink_strategy":                   "extruded fin heatsink candidate",
            "cad_template_recommendation":         "parametric baseplate + fin stack template",
            "cooling_context": state.get("intake", {}).get("thermal", {}).get("cooling_type", "unknown"),
        },
        "notes": [
            "CAD Thermal Integration Agent is advisory-only in Phase 3.",
            "thermal_data sourced from bidirectional_thermal step (nested thermal_data key).",
            "Does not yet drive SolidWorks/Fusion geometry automatically.",
        ],
    }
