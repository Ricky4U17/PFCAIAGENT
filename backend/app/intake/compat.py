from __future__ import annotations
from typing import Any, Dict

def app_line_frequency_hz(app: Dict[str, Any]) -> float:
    return float(app.get("nominal_line_frequency_hz", app.get("line_frequency_hz_nom", 60.0)))

def app_efficiency_fraction(app: Dict[str, Any], default: float = 0.945) -> float:
    if app.get("efficiency_target_percent") is not None:
        try:
            return float(app["efficiency_target_percent"]) / 100.0
        except Exception:
            return default
    try:
        return float(app.get("efficiency_target", default))
    except Exception:
        return default

def compliance_leakage_limit_ua(comp: Dict[str, Any]) -> float:
    if comp.get("leakage_current_limit_ua") is not None:
        return float(comp["leakage_current_limit_ua"])
    if comp.get("leakage_current_limit_ma") is not None:
        return float(comp["leakage_current_limit_ma"]) * 1000.0
    return 3500.0

def compliance_leakage_limit_ma(comp: Dict[str, Any]) -> float:
    return compliance_leakage_limit_ua(comp) / 1000.0
