from __future__ import annotations
import math
from typing import Dict, Any
import numpy as np

def vpk_from_vac(vac: float) -> float:
    return math.sqrt(2.0) * vac

def irms_from_power(pout: float, vac: float, eff: float, pf: float) -> float:
    return pout / (vac * eff * pf)

def ipk_from_irms(irms: float) -> float:
    return math.sqrt(2.0) * irms

def duty_from_vin(vin: np.ndarray, vout: float) -> np.ndarray:
    d = 1.0 - vin / vout
    return np.clip(d, 0.0, 1.0)

def kd_exact_piecewise(duty: np.ndarray) -> np.ndarray:
    d = np.asarray(duty, dtype=float)
    k = np.zeros_like(d)
    lt = d < 0.5
    gt = d > 0.5
    eq = np.isclose(d, 0.5)
    k[lt] = (1.0 - 2.0 * d[lt]) / (1.0 - d[lt])
    k[gt] = (2.0 * d[gt] - 1.0) / d[gt]
    k[eq] = 0.0
    return np.clip(k, 0.0, 1.0)

def delta_il_pp(vin: np.ndarray, duty: np.ndarray, inductance: float, fsw: float) -> np.ndarray:
    return (vin * duty) / (inductance * fsw)

def input_processing(inputs: Dict[str, Any]) -> Dict[str, Any]:
    vac, pout, eff, pf = inputs["Vac"], inputs["Pout"], inputs["eff"], inputs["pf"]
    vpk = vpk_from_vac(vac); irms = irms_from_power(pout, vac, eff, pf); ipk = ipk_from_irms(irms)
    return {"Vac": vac, "Vpk": vpk, "Irms": irms, "Ipk": ipk}

def duty_and_ripple(inputs: Dict[str, Any]) -> Dict[str, Any]:
    vac, vout, inductance, fsw = inputs["Vac"], inputs["Vout"], inputs["L"], inputs["fsw"]
    vpk = vpk_from_vac(vac); irms = irms_from_power(inputs["Pout"], vac, inputs["eff"], inputs["pf"]); ipk = ipk_from_irms(irms)
    theta = np.linspace(0.0, np.pi, 2000)
    vin = vpk * np.sin(theta)
    duty = duty_from_vin(vin, vout)
    d_il = delta_il_pp(vin, duty, inductance, fsw)
    k_d = kd_exact_piecewise(duty)
    d_iin = d_il * k_d
    dpk = 1.0 - (vpk / vout)
    kpk = float(kd_exact_piecewise(np.array([dpk]))[0])
    d_il_pk = float((vpk * dpk) / (inductance * fsw))
    d_iin_pk = d_il_pk * kpk
    return {"Vpk": vpk, "Ipk": ipk, "D_at_crest": dpk, "K_at_crest": kpk, "per_phase_ripple_pp_at_crest": d_il_pk, "input_ripple_pp_at_crest": d_iin_pk}

def inductor_sizing(inputs: Dict[str, Any]) -> Dict[str, Any]:
    vac, vout, fsw, rr = inputs["Vac"], inputs["Vout"], inputs["fsw"], inputs["ripple_ratio_target"]
    vpk = vpk_from_vac(vac); irms = irms_from_power(inputs["Pout"], vac, inputs["eff"], inputs["pf"]); ipk = ipk_from_irms(irms)
    dpk = 1.0 - (vpk / vout); kpk = float(kd_exact_piecewise(np.array([dpk]))[0])
    d_iin_target = rr * ipk; d_il_required = d_iin_target / max(kpk, 1e-9)
    l_required = (vpk * dpk) / (d_il_required * fsw)
    return {"Vpk": vpk, "Irms": irms, "Ipk": ipk, "D_at_crest": dpk, "K_at_crest": kpk, "input_ripple_pp_target": d_iin_target, "required_per_phase_ripple_pp": d_il_required, "L_required_H": l_required, "L_required_uH": l_required * 1e6}

def worst_case_angle(inputs: Dict[str, Any]) -> Dict[str, Any]:
    vac, vout, inductance, fsw = inputs["Vac"], inputs["Vout"], inputs["L"], inputs["fsw"]
    vpk = vpk_from_vac(vac)
    theta = np.linspace(0.0, np.pi, 5000)
    vin = vpk * np.sin(theta)
    duty = duty_from_vin(vin, vout)
    d_il = delta_il_pp(vin, duty, inductance, fsw)
    idx = int(np.argmax(d_il))
    return {"Vpk": vpk, "theta_worst_deg": float(theta[idx] * 180.0 / math.pi), "delta_IL_pp_max": float(d_il[idx]), "Vin_at_worst": float(vin[idx])}

def run_interleaved_ccm_step(step_name: str, inputs: Dict[str, Any]) -> Dict[str, Any]:
    mapping = {"input_processing": input_processing, "duty_and_ripple": duty_and_ripple, "inductor_sizing": inductor_sizing, "worst_case_angle": worst_case_angle}
    if step_name not in mapping:
        raise ValueError(f"Unknown step: {step_name}")
    return mapping[step_name](inputs)
