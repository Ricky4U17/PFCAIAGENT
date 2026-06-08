import math
from typing import Dict, Any

def required_area_product_cm4(L_h: float, i_pk_a: float, b_max_t: float = 0.6, j_a_per_mm2: float = 5.0, ku: float = 0.3) -> float:
    j_a_per_m2 = j_a_per_mm2 * 1e6
    ap_m4 = (L_h * (i_pk_a ** 2)) / max(ku * b_max_t * j_a_per_m2, 1e-12)
    return ap_m4 * 1e8

def turns_from_inductance_and_ae(L_h: float, i_pk_a: float, b_max_t: float, ae_m2: float) -> float:
    return (L_h * i_pk_a) / max(b_max_t * ae_m2, 1e-12)

def wire_area_mm2(i_rms_a: float, j_a_per_mm2: float = 5.0) -> float:
    return i_rms_a / max(j_a_per_mm2, 1e-12)

def design_magnetics(inputs: Dict[str, Any]) -> Dict[str, Any]:
    L_uH, i_pk = float(inputs["L_uH"]), float(inputs["I_pk"])
    i_rms = float(inputs.get("I_rms", i_pk / math.sqrt(2.0))); b_max = float(inputs.get("b_max_t", 0.6)); j = float(inputs.get("j_a_per_mm2", 5.0)); ae = float(inputs.get("ae_m2_guess", 250e-6))
    L_h = L_uH * 1e-6
    return {"inputs": inputs, "results": {"Ap_required_cm4": required_area_product_cm4(L_h, i_pk, b_max, j), "Turns_est": turns_from_inductance_and_ae(L_h, i_pk, b_max, ae), "Wire_Area_mm2": wire_area_mm2(i_rms, j)}}
