"""
app/mode_b/calculations.py
Core PFC calculations for Mode B report generation.
All functions accept primitive floats/arrays — no DesignParams dependency.
"""
from __future__ import annotations
import math
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
    """Step 4: Size Lphi for the WORST-CASE crest ripple ratio across all nine
    operating points — not only 90 Vac low-line. At each point the L required
    to hold ΔI_in,pp/I_in,pk ≤ r is L_i = Vpk·Dpk·K(Dpk)/(r·I_in,pk·f_sw); the
    target is the maximum (governing point recorded in ref_idx). Sizing only at
    index 0 let r_act reach ~25% at 200–230 Vac high line with r = 20% selected
    (interleave cancellation K(D) is weak at low duty)."""
    n = len(s2['Vin_pk'])
    L_all = np.zeros(n)
    for i in range(n):
        dIin_i   = r_input * s2['Iin_pk'][i]
        dIL_i    = dIin_i / s2['KDpk'][i]
        L_all[i] = s2['Vin_pk'][i] * s2['Dpk'][i] / (dIL_i * fsw)
    i = int(np.argmax(L_all))
    dIin = r_input * s2['Iin_pk'][i]
    dIL  = dIin / s2['KDpk'][i]
    return dict(ref_idx=i, dIin_ref=dIin, dIL_ref=dIL, L_calc=float(L_all[i]),
                L_per_point_uH=[round(float(x) * 1e6, 2) for x in L_all])


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


def canonical_ops_table(vin_min: float, vin_max: float,
                        pout_lo: float, pout_hi: float,
                        eta_target: float | None = None,
                        pf_target: float | None = None) -> np.ndarray:
    """Nine-point eta/PF operating grid for this design, DERIVED from the internal
    reference curve. Single source of truth for the operating-point grid — both the
    sizing engine and every report chapter must build their OPS arrays from this same
    table (directly or via build_design_ops_table) so that derived figures such as
    Iph_rms never diverge between Table 3.2.4 and Table 3.4.1.

    Derivation rules (designer-specified 2026-07-22):
      • Voltages: the 7 middle points (110..230) are kept; only the endpoints move to
        the designer's vin_min / vin_max.
      • eta/PF at the two moved endpoints are EXTRAPOLATED along the internal curve
        (linear from the two nearest reference points), so 85 Vac ≠ the 90 Vac value.
      • eta is scaled by a single ratio to hit eta_target at the high-line best corner
        (last row); PF is scaled by a single ratio to hit pf_target at the low-line best
        corner (first row). The internal reference values below are NOT changed — they
        are the ratio/extrapolation basis only."""
    # Internal reference design curve at the 90..264 corners — DO NOT change these values.
    # (High-line efficiencies are the loss-derived re-estimate from Ch 7.9.)
    _ref = np.array([
        [90.0,   pout_lo,  0.945, 0.9987],
        [110.0,  pout_lo,  0.955, 0.9986],
        [120.0,  pout_lo,  0.965, 0.9985],
        [132.0,  pout_lo,  0.975, 0.9980],
        [180.0,  pout_hi,  0.965, 0.9889],
        [200.0,  pout_hi,  0.970, 0.9884],
        [220.0,  pout_hi,  0.973, 0.9790],
        [230.0,  pout_hi,  0.975, 0.9789],
        [264.0,  pout_hi,  0.980, 0.9520],
    ], dtype=float)
    Vref = _ref[:, 0]

    def _extrap(ys, x):   # linear interp, linear extrapolation beyond the reference corners
        if x <= Vref[0]:
            return ys[0] + (ys[1] - ys[0]) / (Vref[1] - Vref[0]) * (x - Vref[0])
        if x >= Vref[-1]:
            return ys[-1] + (ys[-1] - ys[-2]) / (Vref[-1] - Vref[-2]) * (x - Vref[-1])
        return float(np.interp(x, Vref, ys))

    m = _ref.copy()
    # move the endpoints to the designer's corners + extrapolate their eta/PF for the new voltage
    m[0, 0], m[0, 2], m[0, 3] = vin_min, _extrap(_ref[:, 2], vin_min), _extrap(_ref[:, 3], vin_min)
    m[-1, 0], m[-1, 2], m[-1, 3] = vin_max, _extrap(_ref[:, 2], vin_max), _extrap(_ref[:, 3], vin_max)
    if eta_target:   # scale eta ladder → target at the high-line best corner (last row)
        m[:, 2] = np.clip(m[:, 2] * (float(eta_target) / m[-1, 2]), 0.0, 0.999)
    if pf_target:    # scale PF ladder → target at the low-line best corner (first row)
        m[:, 3] = np.clip(m[:, 3] * (float(pf_target) / m[0, 3]), 0.0, 1.0)
    return m


def build_design_ops_table(vin_min: float, vin_max: float, pout_lo: float, pout_hi: float,
                           vout: float, fsw: float, r_input: float,
                           eta_target: float | None = None,
                           pf_target: float | None = None):
    """Nine-point [Vin_rms, Pout, eta, PF, Iph_rms] operating matrix derived
    from THIS design's actual corner conditions, via the same rigorous
    step2_input_params -> step4_inductance -> step5_phase_rms chain that
    produces the 'accurate' per-phase RMS figures in Table 3.2.4. The sizing
    engine (design_one_core, via step7_run_sizing) and the documentation
    chapters must both source their OPS array from this function so that
    turns/loss/thermal results and the report tables always agree.

    Returns (OPS, L_phi) where OPS columns are [Vin_rms, Pout, eta, PF, Iph_rms]
    and L_phi is the low-line target inductance (H) used to derive Iph_rms.
    """
    ops_ref = canonical_ops_table(vin_min, vin_max, pout_lo, pout_hi, eta_target, pf_target)
    s2 = step2_input_params(vout, ops_ref)
    s4 = step4_inductance(s2, r_input, fsw, vout)
    # ceil to the 5 µH grid (matches Chapter 3): rounding down would violate the
    # designer's ripple-ratio ceiling at the governing operating point.
    L_phi = math.ceil(s4["L_calc"] * 1e6 / 5) * 5 * 1e-6
    n9 = len(s2["Vin_rms"])
    iph_rms = np.zeros(n9)
    for i in range(n9):
        iph_rms[i], _, _, _ = step5_phase_rms(s2["Vin_pk"][i], s2["Iin_pk"][i], L_phi, fsw, vout)
    OPS = np.column_stack([s2["Vin_rms"], s2["Pout"], s2["eta"], s2["PF"], iph_rms])
    return OPS, L_phi
