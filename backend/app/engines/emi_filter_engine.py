import math
from typing import Dict, Any

def max_total_y_cap_from_leakage(i_leak_max_a: float, f_line_hz: float, v_line_max_rms: float) -> float:
    return i_leak_max_a / (2.0 * math.pi * f_line_hz * v_line_max_rms)

def estimate_x_cap_for_dm_attenuation(f_sw_hz: float, dm_atten_db: float, line_impedance_ohm: float = 50.0) -> float:
    attenuation_ratio = 10 ** (dm_atten_db / 20.0)
    f_c_dm = max(100.0, f_sw_hz / max(attenuation_ratio, 10.0))
    return 1.0 / (2.0 * math.pi * line_impedance_ohm * f_c_dm)

def min_cm_choke_inductance(f_sw_hz: float, total_y_cap_f: float, cm_cutoff_ratio: float = 0.1) -> float:
    f_c = max(100.0, cm_cutoff_ratio * f_sw_hz)
    if total_y_cap_f <= 0: return 0.0
    return 1.0 / (((2.0 * math.pi * f_c) ** 2) * total_y_cap_f)

def design_emi_filter(inputs: Dict[str, Any]) -> Dict[str, Any]:
    f_sw, vac_max, f_line = float(inputs["fsw"]), float(inputs["Vac_max"]), float(inputs.get("line_freq_hz", 60.0))
    leakage_limit_ma, dm_atten_db = float(inputs.get("leakage_limit_ma", 3.5)), float(inputs.get("dm_atten_db", 40.0))
    cy_max = max_total_y_cap_from_leakage(leakage_limit_ma*1e-3, f_line, vac_max)
    x_cap = estimate_x_cap_for_dm_attenuation(f_sw, dm_atten_db)
    l_cm = min_cm_choke_inductance(f_sw, cy_max)
    return {"inputs": {"fsw_hz": f_sw, "vac_max_rms_v": vac_max, "line_freq_hz": f_line, "leakage_limit_ma": leakage_limit_ma, "dm_atten_db": dm_atten_db}, "results": {"cy_max_f": cy_max, "cy_max_nf": cy_max*1e9, "x_cap_f_est": x_cap, "x_cap_uF_est": x_cap*1e6, "l_cm_h_min": l_cm, "l_cm_mH_min": l_cm*1e3}}
