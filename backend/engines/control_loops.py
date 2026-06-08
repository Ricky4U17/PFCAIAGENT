from __future__ import annotations
from typing import Dict, Any
import math, os
import numpy as np
import matplotlib.pyplot as plt

def bode_mag_phase(num: np.ndarray, den: np.ndarray, w: np.ndarray):
    s = 1j * w
    h = np.polyval(num, s) / np.polyval(den, s)
    return 20 * np.log10(np.abs(h)), np.angle(h, deg=True)

def type2_compensator(k: float, wz: float, wp: float):
    num = np.array([k / wz, k]); den = np.array([1 / wp, 1, 0]); return num, den

def estimate_current_loop_plant(inputs: Dict[str, Any]):
    L = inputs["L"]; return {"num": np.array([1.0]), "den": np.array([L, 0.0])}

def estimate_voltage_loop_plant(inputs: Dict[str, Any]):
    C = inputs.get("Cout", 2200e-6); return {"num": np.array([1.0]), "den": np.array([C, 0.0])}

def find_crossover_frequency(num, den, w):
    mag, _ = bode_mag_phase(num, den, w); idx = np.argmin(np.abs(mag)); return float(w[idx] / (2 * math.pi))

def estimate_phase_margin(num, den, w):
    mag, phase = bode_mag_phase(num, den, w); idx = np.argmin(np.abs(mag)); return float(180.0 + phase[idx])

def plot_bode(num, den, title, filepath):
    w = np.logspace(0, 6, 2000); mag, phase = bode_mag_phase(num, den, w); f = w / (2 * math.pi)
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(7, 6), sharex=True)
    ax1.semilogx(f, mag); ax1.set_ylabel("Magnitude (dB)"); ax1.set_title(title); ax1.grid(True, which="both")
    ax2.semilogx(f, phase); ax2.set_ylabel("Phase (deg)"); ax2.set_xlabel("Frequency (Hz)"); ax2.grid(True, which="both")
    fig.tight_layout(); fig.savefig(filepath); plt.close(fig)

def design_control_loops(inputs: Dict[str, Any], output_dir: str) -> Dict[str, Any]:
    os.makedirs(output_dir, exist_ok=True)
    fsw = inputs["fsw"]; line_freq = inputs.get("line_freq", 60.0)
    # current loop
    plant = estimate_current_loop_plant(inputs); target_fc = fsw / 10.0
    wz, wp, k = 2*math.pi*(target_fc/5), 2*math.pi*(target_fc*5), 1.0
    cnum, cden = type2_compensator(k, wz, wp)
    lnum, lden = np.polymul(cnum, plant["num"]), np.polymul(cden, plant["den"])
    w = np.logspace(1, 6, 2000); fc_i = find_crossover_frequency(lnum, lden, w); pm_i = estimate_phase_margin(lnum, lden, w)
    cur_plot = os.path.join(output_dir, "current_loop_bode.png"); plot_bode(lnum, lden, "Current Loop Bode Plot", cur_plot)
    # voltage loop
    plantv = estimate_voltage_loop_plant(inputs); target_fv = max(5.0, line_freq / 10.0)
    wzv, wpv, kv = 2*math.pi*(target_fv/3), 2*math.pi*(target_fv*10), 1.0
    cnumv, cdenv = type2_compensator(kv, wzv, wpv)
    lnumv, ldenv = np.polymul(cnumv, plantv["num"]), np.polymul(cdenv, plantv["den"])
    wv = np.logspace(-1, 4, 2000); fc_v = find_crossover_frequency(lnumv, ldenv, wv); pm_v = estimate_phase_margin(lnumv, ldenv, wv)
    vol_plot = os.path.join(output_dir, "voltage_loop_bode.png"); plot_bode(lnumv, ldenv, "Voltage Loop Bode Plot", vol_plot)
    return {
        "current_loop": {"target_fc_hz": target_fc, "achieved_fc_hz": fc_i, "phase_margin_deg": pm_i, "compensator": {"type": "type_2", "k": k, "wz_rad_s": wz, "wp_rad_s": wp}, "bode_plot": cur_plot},
        "voltage_loop": {"target_fc_hz": target_fv, "achieved_fc_hz": fc_v, "phase_margin_deg": pm_v, "compensator": {"type": "type_2", "k": kv, "wz_rad_s": wzv, "wp_rad_s": wpv}, "bode_plot": vol_plot},
        "notes": ["Starter control-loop design uses simplified plant models."],
    }
