from __future__ import annotations
from typing import Dict, Any

def _safe_float(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return default

def build_reliability_mtbf_advisory(state: Dict[str, Any]) -> Dict[str, Any]:
    thermal = state.get("thermal_results", {})
    ambient = _safe_float(state.get("intake", {}).get("thermal", {}).get("ambient_temp_c_max"), 50.0)
    temp_rise = _safe_float(thermal.get("temperature_rise_c"), 35.0)
    hot_spot = ambient + temp_rise

    weakest = "bulk electrolytic capacitor"
    fit_rate = round(120.0 + max(0.0, hot_spot - 70.0) * 4.0, 2)
    mtbf_hours = round(1e9 / fit_rate, 2) if fit_rate > 0 else None

    risk_band = "moderate"
    if hot_spot > 95:
        risk_band = "high"
    elif hot_spot < 75:
        risk_band = "low"

    return {
        "status": "advisory_ready",
        "blocking": False,
        "reliability_summary": {
            "estimated_hotspot_temp_c": round(hot_spot, 2),
            "estimated_fit_rate": fit_rate,
            "estimated_mtbf_hours": mtbf_hours,
            "risk_band": risk_band,
            "weakest_link_estimate": weakest,
        },
        "notes": [
            "Reliability / MTBF Agent is advisory-only in Phase 2.",
            "This starter implementation uses simplified FIT/MTBF estimation and should not be treated as a formal Telcordia or MIL-HDBK result.",
            "Use this to flag weak links and motivate better thermal or component choices.",
        ],
    }
