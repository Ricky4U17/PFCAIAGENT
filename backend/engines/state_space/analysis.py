import math
import numpy as np
from scipy import signal
from typing import Tuple, Dict
from app.engines.state_space.schemas import BodeData, StepResponseData

def ss_to_siso_tf(A, B, C, D, output_idx: int, input_idx: int):
    sys_tf = signal.ss2tf(A, B, C, D, input=input_idx)
    num = np.squeeze(sys_tf[0][output_idx]); den = np.squeeze(sys_tf[1])
    return np.array(num, dtype=float), np.array(den, dtype=float)

def bode_from_tf(num, den, f_min, f_max, points=2000):
    w = np.logspace(np.log10(2*math.pi*f_min), np.log10(2*math.pi*f_max), points)
    w, mag, phase = signal.bode((num, den), w=w)
    return w/(2*math.pi), mag, phase

def closed_loop_tf(num_loop, den_loop):
    return np.array(num_loop), np.polyadd(np.array(den_loop), np.array(num_loop))

def margins_from_bode(freq_hz, mag_db, phase_deg) -> Tuple[float, float]:
    idx_fc = int(np.argmin(np.abs(mag_db)))
    pm = 180.0 + phase_deg[idx_fc]
    idx_pm = int(np.argmin(np.abs(np.array(phase_deg) + 180.0)))
    gm = -mag_db[idx_pm]
    return float(pm), float(gm)

def step_metrics(t, y) -> Dict[str, float]:
    final = float(y[-1]) if len(y) else 0.0
    if abs(final) < 1e-12:
        return {"overshoot_percent": 0.0, "settling_time_s": 0.0, "rise_time_s": 0.0}
    peak = float(np.max(y))
    overshoot = max(0.0, (peak-final)/abs(final)*100.0)
    band = 0.02*abs(final)
    settling_idx = len(y)-1
    for i in range(len(y)):
        if np.all(np.abs(y[i:]-final) <= band):
            settling_idx = i; break
    lo, hi = 0.1*final, 0.9*final
    rs = re = 0
    for i in range(len(y)):
        if y[i] >= lo: rs = i; break
    for i in range(len(y)):
        if y[i] >= hi: re = i; break
    return {"overshoot_percent": float(overshoot), "settling_time_s": float(t[settling_idx]), "rise_time_s": float(max(0.0, t[re]-t[rs]))}

def build_loop_analysis(plant_num, plant_den, comp_num, comp_den, f_min, f_max, step_t_end, step_points=2000):
    num_loop = np.polymul(comp_num, plant_num); den_loop = np.polymul(comp_den, plant_den)
    freq_hz, pmag, pphase = bode_from_tf(plant_num, plant_den, f_min, f_max)
    _, lmag, lphase = bode_from_tf(num_loop, den_loop, f_min, f_max)
    num_cl, den_cl = closed_loop_tf(num_loop, den_loop)
    _, cmag, cphase = bode_from_tf(num_cl, den_cl, f_min, f_max)
    pm, gm = margins_from_bode(freq_hz, lmag, lphase)
    sys = signal.TransferFunction(num_cl, den_cl); t = np.linspace(0.0, step_t_end, step_points); t, y = signal.step(sys, T=t); m = step_metrics(t, y)
    bode = BodeData(frequency_hz=freq_hz.tolist(), plant_mag_db=pmag.tolist(), plant_phase_deg=pphase.tolist(), loop_mag_db=lmag.tolist(), loop_phase_deg=lphase.tolist(), closed_mag_db=cmag.tolist(), closed_phase_deg=cphase.tolist())
    step = StepResponseData(time_s=t.tolist(), response=y.tolist(), reference=[1.0 for _ in t], overshoot_percent=m["overshoot_percent"], settling_time_s=m["settling_time_s"], rise_time_s=m["rise_time_s"])
    return bode, step, {"phase_margin_deg": pm, "gain_margin_db": gm}
