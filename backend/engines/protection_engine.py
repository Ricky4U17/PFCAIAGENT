import math
from typing import Dict, Any

def design_protection(inputs: Dict[str, Any]) -> Dict[str, Any]:
    i_pk = float(inputs["i_pk"]); i_transient = float(inputs.get("i_transient_margin", 0.2 * i_pk))
    i_pk_max = i_pk + i_transient
    i_trip = float(inputs.get("ocp_multiplier", 1.0)) * i_pk_max
    i_sat_min = 1.2 * i_trip
    v_bus = float(inputs["v_bus"])
    ovp_soft = float(inputs.get("ovp_soft_v", 410.0))
    ovp_hard = float(inputs.get("ovp_hard_v", 425.0))
    cap_min = 450.0 if v_bus <= 390 else 500.0
    i_leak_max = float(inputs.get("leakage_limit_ma", 3.5)) * 1e-3
    f_line = float(inputs.get("line_freq_hz", 60.0))
    v_line_max = float(inputs.get("vac_max_rms", 264.0))
    cy_max = i_leak_max / (2 * math.pi * f_line * v_line_max)
    return {
        "ocp": {"i_pk_max_a": i_pk_max, "i_trip_a": i_trip, "i_sat_min_a": i_sat_min},
        "ovp": {"ovp_soft_v": ovp_soft, "ovp_hard_v": ovp_hard, "bulk_cap_min_rating_v": cap_min},
        "surge": {"mov_required": "select per surge class", "fuse_i2t_check": "required"},
        "leakage": {"cy_max_f": cy_max, "cy_max_nf": cy_max * 1e9},
        "design_impacts": ["Pass cy_max_nf into EMI filter synthesis.", "Verify inductor saturation exceeds 1.2x OCP trip."],
    }
