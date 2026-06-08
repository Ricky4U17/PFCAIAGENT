from __future__ import annotations
from typing import Dict, Any, Tuple

def validate_topology_specific_inputs(selected_mode: str | None, data: Dict[str, Any]) -> Tuple[bool, list[str]]:
    errors: list[str] = []
    mode = (selected_mode or "").lower()
    style = data.get("switching_frequency_style")
    fixed = data.get("recommended_frequency_hz")
    rng = data.get("recommended_frequency_range_hz")
    crest = data.get("default_crest_ripple_ratio")

    if mode == "ccm":
        if style not in {"fixed", "recommend"}:
            errors.append("CCM requires fixed or recommended switching-frequency style.")
        if style == "fixed" and not fixed:
            errors.append("CCM requires a fixed switching-frequency value.")
        try:
            c = float(crest)
            if not (0.05 <= c <= 0.6):
                errors.append("CCM crest ripple ratio should usually be between 0.05 and 0.6.")
        except Exception:
            errors.append("CCM requires a valid crest ripple ratio.")
    elif mode == "crcm":
        if style not in {"variable", "recommend"}:
            errors.append("CrCM requires variable or recommended switching-frequency style.")
        if style == "variable" and not (isinstance(rng, (list, tuple)) and len(rng) == 2):
            errors.append("CrCM variable-frequency mode requires a min/max range.")
        try:
            c = float(crest)
            if abs(c - 2.0) > 1e-6:
                errors.append("CrCM crest ripple ratio should remain 2.0 in the hardened flow.")
        except Exception:
            errors.append("CrCM crest ripple ratio must default to 2.0.")
    elif mode == "dcm":
        if style not in {"fixed", "variable", "recommend"}:
            errors.append("DCM requires fixed, variable, or recommended switching-frequency style.")
        if style == "fixed" and not fixed:
            errors.append("DCM fixed-frequency mode requires a frequency value.")
        if style == "variable" and not (isinstance(rng, (list, tuple)) and len(rng) == 2):
            errors.append("DCM variable-frequency mode requires a min/max range.")
        try:
            c = float(crest)
            if c <= 2.0:
                errors.append("DCM crest ripple ratio must be greater than 2.0.")
        except Exception:
            errors.append("DCM requires a valid default crest ripple ratio > 2.0.")
    return (len(errors) == 0), errors
