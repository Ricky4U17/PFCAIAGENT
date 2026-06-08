from __future__ import annotations
from typing import Dict, Any
import math
import numpy as np

def reconstruct_piecewise_pwm_ripple(vac_rms: float, vout: float, pout: float, eff: float, pf: float, l_phase: float, fsw: float, f_line: float = 60.0, samples_per_period: int = 80) -> Dict[str, Any]:
    ts = 1.0 / fsw
    t_half = 1.0 / (2.0 * f_line)
    dt = ts / samples_per_period
    t = np.arange(0.0, t_half, dt)
    vpk = math.sqrt(2.0) * vac_rms
    pin = pout / eff
    iin_rms = pin / (vac_rms * pf)
    iin_pk = math.sqrt(2.0) * iin_rms
    vin = np.clip(vpk * np.sin(2.0 * math.pi * f_line * t), 0.0, None)
    duty = np.clip(1.0 - vin / vout, 0.0, 1.0)
    iin_avg = np.clip(iin_pk * np.sin(2.0 * math.pi * f_line * t), 0.0, None)
    iL_avg_phi = 0.5 * iin_avg
    phase_A = (t * fsw) % 1.0
    phase_B = (phase_A + 0.5) % 1.0
    on_slope = vin / l_phase
    off_slope = (vin - vout) / l_phase
    ripple_A = np.zeros_like(t)
    ripple_B = np.zeros_like(t)
    on_A = phase_A < duty
    ripple_A[on_A] = on_slope[on_A] * (phase_A[on_A] * ts)
    ripple_A[~on_A] = on_slope[~on_A] * (duty[~on_A] * ts) + off_slope[~on_A] * ((phase_A[~on_A] - duty[~on_A]) * ts)
    on_B = phase_B < duty
    ripple_B[on_B] = on_slope[on_B] * (phase_B[on_B] * ts)
    ripple_B[~on_B] = on_slope[~on_B] * (duty[~on_B] * ts) + off_slope[~on_B] * ((phase_B[~on_B] - duty[~on_B]) * ts)
    ripple_A = ripple_A - 0.5 * (np.max(ripple_A) + np.min(ripple_A))
    ripple_B = ripple_B - 0.5 * (np.max(ripple_B) + np.min(ripple_B))
    iL_A = iL_avg_phi + ripple_A
    iL_B = iL_avg_phi + ripple_B
    delta_iin_signed = ripple_A + ripple_B
    iin_total = iin_avg + delta_iin_signed
    idx_crest = int(np.argmax(vin))
    return {
        "time_s": t.tolist(),
        "vin_v": vin.tolist(),
        "duty": duty.tolist(),
        "iin_avg_a": iin_avg.tolist(),
        "iL_avg_phi_a": iL_avg_phi.tolist(),
        "ripple_A_a": ripple_A.tolist(),
        "ripple_B_a": ripple_B.tolist(),
        "iL_A_a": iL_A.tolist(),
        "iL_B_a": iL_B.tolist(),
        "delta_iin_signed_a": delta_iin_signed.tolist(),
        "iin_total_a": iin_total.tolist(),
        "crest": {"time_s": float(t[idx_crest]), "vin_v": float(vin[idx_crest]), "duty": float(duty[idx_crest]), "ripple_A_a": float(ripple_A[idx_crest]), "ripple_B_a": float(ripple_B[idx_crest])},
    }
