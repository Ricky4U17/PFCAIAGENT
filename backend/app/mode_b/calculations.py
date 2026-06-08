"""
app/mode_b/calculations.py
Core PFC calculations for Mode B report generation.
All functions accept primitive floats/arrays — no DesignParams dependency.
"""
from __future__ import annotations
import numpy as np
from typing import Dict, Any


def K_of_D(D: np.ndarray | float) -> np.ndarray | float:
    """2-phase interleaved boost ripple-cancellation factor K(D)."""
    D = np.clip(D, 1e-9, 1 - 1e-9)
    return np.where(D < 0.5, (1 - 2 * D) / (1 - D), (2 * D - 1) / D)


def step2_input_params(Vout: float, OPS: np.ndarray) -> Dict[str, np.ndarray]:
    """Step 2: Compute Vpk, Dpk, Pin, Iin_rms, Iin_pk for all operating points."""
    Vin_rms = OPS[:, 0];  Pout = OPS[:, 1]
    eta     = OPS[:, 2];  PF   = OPS[:, 3]
    Vin_pk  = np.sqrt(2) * Vin_rms
    Dpk     = 1.0 - Vin_pk / Vout
    Pin     = Pout / eta
    Iin_rms = Pin / (Vin_rms * PF)
    Iin_pk  = np.sqrt(2) * Iin_rms
    KDpk    = K_of_D(Dpk)
    return dict(Vin_rms=Vin_rms, Pout=Pout, eta=eta, PF=PF,
                Vin_pk=Vin_pk, Dpk=Dpk, Pin=Pin,
                Iin_rms=Iin_rms, Iin_pk=Iin_pk, KDpk=KDpk)


def step4_inductance(s2: Dict, r_input: float, fsw: float, Vout: float) -> Dict:
    """Step 4: Size Lphi at 90 Vac low-line."""
    i = 0
    dIin = r_input * s2['Iin_pk'][i]
    dIL  = dIin / s2['KDpk'][i]
    L    = s2['Vin_pk'][i] * s2['Dpk'][i] / (dIL * fsw)
    return dict(ref_idx=i, dIin_ref=dIin, dIL_ref=dIL, L_calc=L)


def step5_phase_rms(Vin_pk_v: float, Iin_pk_v: float,
                    L_phi: float, fsw: float, Vout: float) -> tuple:
    """Step 5: Per-phase inductor RMS components over half line cycle."""
    th = np.linspace(1e-6, np.pi - 1e-6, 3000)
    Vt = Vin_pk_v * np.sin(th)
    Dt = np.clip(1 - Vt / Vout, 0, 1)
    ia = (Iin_pk_v / 2) * np.sin(th)
    dI = Vt * Dt / (L_phi * fsw)
    hf = dI / (2 * np.sqrt(3))
    rms  = np.sqrt(np.trapezoid(ia**2 + hf**2, th) / np.pi)
    lf   = np.sqrt(np.trapezoid(ia**2, th)          / np.pi)
    hf2  = np.sqrt(np.trapezoid(hf**2, th)          / np.pi)
    dILc = Vin_pk_v * max(0.0, 1 - Vin_pk_v / Vout) / (L_phi * fsw)
    return rms, lf, hf2, dILc


def step7_8_worst_case(s2: Dict, L_phi: float, fsw: float,
                        Vout: float, f_line: float) -> Dict:
    """Steps 7-8: Worst-case line angle and maximum per-phase ripple."""
    Vin_pk = s2['Vin_pk']; Iin_pk = s2['Iin_pk']; Dpk = s2['Dpk']
    Vh = Vout / 2
    Vin_w  = np.where(Vin_pk >= Vh, Vh, Vin_pk)
    th1    = np.where(Vin_pk >= Vh, np.arcsin(Vh / Vin_pk), np.pi / 2)
    th2    = np.pi - th1
    D_w    = np.where(Vin_pk >= Vh, 0.5, Dpk)
    t1_ms  = th1 / (2 * np.pi * f_line) * 1000
    t2_ms  = th2 / (2 * np.pi * f_line) * 1000
    dIL    = Vin_w * D_w / (L_phi * fsw)
    iinst  = Iin_pk * np.sin(th1)
    dIin_w = K_of_D(D_w) * dIL
    return dict(Vhalf=Vh, Vin_w=Vin_w, th1=th1, th2=th2,
                D_w=D_w, t1_ms=t1_ms, t2_ms=t2_ms,
                dIL_max=dIL, iinst=iinst, dIin_w=dIin_w)


def gen_waveforms(Vin_pk_v: float, Iin_pk_v: float,
                  L_phi: float, fsw: float, f_line: float,
                  Vout: float, n_sw: int = 20):
    """Generate per-phase A/B switching waveforms over half line cycle."""
    T_half = 1 / (2 * f_line)
    n      = int(fsw * T_half * n_sw)
    t      = np.linspace(0, T_half, n)
    th     = 2 * np.pi * f_line * t
    Vt     = Vin_pk_v * np.sin(th)
    Dt     = np.clip(1 - Vt / Vout, 0, 1)
    iavg   = (Iin_pk_v / 2) * np.sin(th)
    dIL    = Vt * Dt / (L_phi * fsw)
    phA    = (t * fsw) % 1.0
    phB    = (t * fsw + 0.5) % 1.0

    def rip(ph: np.ndarray, D: np.ndarray) -> np.ndarray:
        Ds = np.where(D > 1e-7, D, 1e-7)
        Rs = np.where(1 - D > 1e-7, 1 - D, 1e-7)
        return np.where(ph <= D,
                        dIL * (ph / Ds - 0.5),
                        dIL * (0.5 - (ph - D) / Rs))

    rA = rip(phA, Dt); rB = rip(phB, Dt)
    return t * 1000, iavg + rA, iavg + rB, rA, rB, rA + rB, dIL, iavg
