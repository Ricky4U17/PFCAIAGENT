#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
powder_core_inductor.py  -- Reference implementation of the
"Powder-Core Inductor Magnetic Design — Calculation Standard v1.0".

Deterministic, material-agnostic engine for boost / interleaved-boost PFC inductors
on Magnetics distributed-gap powder toroids (MPP, High Flux, Kool Mu, XFlux, Edge),
any size / permeability.  Same inputs -> identical outputs every run.

Comment tags map to the standard:
   E*  = canonical equation number        G*  = guardrail
   GATE = mandatory self-check (halts run on failure)

Dependencies: numpy only (no scipy).  Python 3.9+.

The engine produces the IMPROVED calculation (cycle-averaged iGSE core loss,
LF+HF copper loss, biased-L guarantee, datasheet B_sat, per-quantity worst case,
two-node/forced-convection thermal).  A `core_loss_method` switch reproduces the
legacy peak-point method for side-by-side comparison/training.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional
import math
import json
import numpy as np

MU0 = 4 * math.pi * 1e-7          # H/m
RHO_CU_20 = 1.72e-8               # ohm*m
ALPHA_CU = 0.00393                # 1/K
OE_PER_AM = 1.0 / 79.577          # 1 Oe = 79.577 A/m

# ====================================================================================
#  MATERIAL LIBRARY  (Appendix A: verified Magnetics Edge toroid coefficients, 2023)
#  Forms:  core loss  P[mW/cm^3] = a * B[T]^b * f[kHz]^c
#          DC bias    %mu        = 1 / (a + b * H[Oe]^c)   (a~0.01 -> 100% at H=0)
#  For ANY other material/permeability, fetch (a,b,c) from the Magnetics Curve Fit
#  Equation Tool (rev. Aug-2024) and populate a MaterialModel; the validation gate
#  (Section 3.3) then proves the coefficients reproduce the datasheet before use.
# ====================================================================================
EDGE_TOROID = {
    "Bsat": 1.5,                                   # T  (FeNi alloy, datasheet)
    "core_loss": {                                 # mu : (a, b, c)
        14: (212.96, 2.263, 1.390), 19: (200.53, 2.263, 1.369),
        26: (207.90, 2.263, 1.322), 40: (150.40, 2.263, 1.369),
        60: (156.18, 2.263, 1.321), 75: (121.47, 2.263, 1.403),
        90: (481.77, 2.263, 1.139), 125: (481.77, 2.263, 1.139),
    },
    "dc_bias": {                                   # mu : (a, b, c)
        14: (0.01, 1.17e-11, 3.106), 19: (0.01, 6.39e-11, 2.950),
        26: (0.01, 3.65e-11, 3.192), 40: (0.01, 2.59e-9, 2.683),
        60: (0.01, 9.20e-10, 3.044), 75: (0.01, 1.58e-9, 3.067),
        90: (0.01, 1.85e-9, 3.138), 125: (0.01, 1.23e-9, 3.419),
    },
}


# ====================================================================================
#  INPUT DATACLASSES  (Section 2 -- run gate)
# ====================================================================================
@dataclass
class OperatingPoint:
    Vin: float       # line RMS input voltage [V]
    Pout: float      # output power at this corner [W]
    eta: float       # efficiency (0-1)
    PF: float        # power factor (0-1)

@dataclass
class ConverterSpec:
    Vout: float                       # bus voltage [V]
    fsw: float                        # switching frequency [Hz]
    fline: float                      # line frequency [Hz]
    nph: int                          # number of interleaved phases
    r: float                          # crest INPUT-ripple ratio target (G1)
    points: List[OperatingPoint]

@dataclass
class MaterialModel:
    name: str
    mu: int
    Bsat: float                       # [T] datasheet (G5)
    loss_abc: Tuple[float, float, float]    # P = a*B^b*f^c  (mW/cm^3, T, kHz)
    bias_abc: Tuple[float, float, float]    # %mu = 1/(a + b*H^c)  (H in Oe)
    loss_max_scale: float = 1.286     # typ->max core-loss anchor (catalog ratio)
    # validation anchors (Section 3.3 GATE)
    loss_anchor: Optional[Tuple[float, float, float]] = None  # (B[T], f[kHz], P_datasheet[mW/cm^3])
    bias_anchors: Tuple[Tuple[float, float], ...] = ()        # ((H[Oe], %mu), ...)

    @classmethod
    def edge(cls, mu: int) -> "MaterialModel":
        return cls(name="Edge", mu=mu, Bsat=EDGE_TOROID["Bsat"],
                   loss_abc=EDGE_TOROID["core_loss"][mu],
                   bias_abc=EDGE_TOROID["dc_bias"][mu])

    # --- material physics ---
    def core_loss_density(self, Bac_pk_T, f_kHz):          # E15 kernel [mW/cm^3]
        a, b, c = self.loss_abc
        return a * np.power(np.abs(Bac_pk_T), b) * np.power(f_kHz, c)

    def k_bias(self, H_oe):                                # E10 retention fraction
        a, b, c = self.bias_abc
        return 1.0 / (a + b * np.power(np.maximum(H_oe, 1e-9), c)) / 100.0

    def Fd_integral(self):                                 # E14 I_c = int|cos|^c
        c = self.loss_abc[2]
        th = np.linspace(0, 2 * math.pi, 200001)
        return np.trapezoid(np.abs(np.cos(th)) ** c, th)

    def F_D(self, D, Ic):                                  # E14 iGSE triangular factor
        c = self.loss_abc[2]
        D = np.clip(D, 1e-4, 1 - 1e-4)
        return (2.0 ** c) * (D ** (1 - c) + (1 - D) ** (1 - c)) / ((2 * math.pi) ** (c - 1) * Ic)

    def validate(self, tol_loss=0.03, tol_bias=1.0) -> List[str]:
        """GATE (3.3): coefficients must reproduce datasheet anchors. Returns failures."""
        fails = []
        if self.loss_anchor:
            B, f, P = self.loss_anchor
            pred = float(self.core_loss_density(B, f))
            if abs(pred - P) / P > tol_loss:
                fails.append(f"LOSS gate: pred {pred:.1f} vs datasheet {P:.1f} mW/cm^3 (>{tol_loss:.0%})")
        for H, pm in self.bias_anchors:
            pred = float(self.k_bias(H) * 100)
            if abs(pred - pm) > tol_bias:
                fails.append(f"BIAS gate: at {H} Oe pred {pred:.1f}% vs {pm:.1f}%")
        return fails

@dataclass
class CoreGeometry:
    Ae_mm2: float          # effective area, single core
    le_mm: float           # path length, single core (UNCHANGED by stacking, G7)
    Ve_cm3: float          # effective volume, single core
    Wa_mm2: float          # window/bore area, single core (UNCHANGED by stacking, G7)
    OD_mm: float
    ID_mm: float
    HT_mm: float           # single-core height
    AL_nom_nH: float       # nH/T^2, single core
    AL_tol: float = 0.08
    stacks: int = 1
    # --- stacking rules (Section 3.5) ---
    @property
    def Ae(self):  return self.Ae_mm2 * self.stacks * 1e-6      # m^2 (G7: Ae stacks)
    @property
    def Ve(self):  return self.Ve_cm3 * self.stacks             # cm^3 (stacks)
    @property
    def le_cm(self): return self.le_mm / 10.0                   # cm  (no stack)
    @property
    def Wa(self):  return self.Wa_mm2                           # mm^2 (G7: NO stack)
    @property
    def AL_total(self): return self.AL_nom_nH * self.stacks * 1e-9   # H/T^2
    @property
    def width_mm(self): return (self.OD_mm - self.ID_mm) / 2.0
    @property
    def stack_height_mm(self): return self.HT_mm * self.stacks

@dataclass
class Winding:
    N: int
    strand_d_mm: float
    n_strands: int
    n_par: int                  # parallel conductors per turn
    build_mm: float = 3.8       # MLT build allowance
    Rac_Rdc: float = 1.15       # litz AC/DC ratio at f_sw (G10; replace with Dowell/Sullivan/FEA for Tier-2)
    @property
    def A_strand_mm2(self):  return math.pi / 4 * self.strand_d_mm ** 2
    @property
    def A_bundle_mm2(self):  return self.n_strands * self.A_strand_mm2          # one parallel path
    @property
    def A_cu_mm2(self):      return self.n_par * self.A_bundle_mm2              # total Cu/turn

@dataclass
class AcceptanceLimits:
    L_target_uH: float
    Tamb_C: float = 50.0
    Thot_C: float = 110.0
    FFcu_limit: float = 0.45
    Jtarget_AperMM2: Tuple[float, float] = (3.0, 7.0)
    sat_margin_min: float = 0.43         # require B_max <= (1-0.43)*Bsat -> ~0.57*Bsat
    Twind_C: float = 100.0               # winding temp for DCR/loss reporting


# ====================================================================================
#  ENGINE
# ====================================================================================
def skin_depth_m(f_hz, rho=RHO_CU_20):                 # E19
    return math.sqrt(rho / (math.pi * f_hz * MU0))

def H_oe(N, I, le_cm):                                 # E9   H[Oe] = 0.4*pi*N*I/le[cm]
    return 0.4 * math.pi * N * I / le_cm

def Kd(D):                                             # E5 interleaving residual
    D = np.asarray(D, float)
    out = np.where(D < 0.5, (1 - 2 * D) / (1 - D), (2 * D - 1) / np.maximum(D, 1e-9))
    return np.where(np.isclose(D, 0.5, atol=1e-3), 0.0, out)

def harmonic_ac_excess_factor(Rac_Rdc):
    """E21: triangular ripple AC-excess multiplier vs single-freq lumped model (G-refinement).
       Harmonics amplitude ~1/h^2 (odd h); proximity excess ~ (Rac_Rdc-1)*h^2."""
    odd = np.arange(1, 200, 2)
    num = np.sum((1 / odd ** 2) ** 2 * odd ** 2)       # sum 1/h^2
    den = np.sum((1 / odd ** 2) ** 2)                  # sum 1/h^4
    return num / den                                   # ~1.213

def analyze(spec: ConverterSpec, core: CoreGeometry, mat: MaterialModel,
            wind: Winding, lim: AcceptanceLimits,
            core_loss_method: str = "cycle_avg_igse",   # or "peak_point" (legacy)
            cooling: str = "natural",                    # or "forced"
            airflow_mps: float = 2.0,
            n_theta: int = 40001) -> dict:
    """Execute S1..S12. Returns a machine-readable result dict (Section 9)."""
    # ---------- S2: validate material (GATE 3.3) ----------
    mat_fails = mat.validate()
    Ic = mat.Fd_integral()

    # ---------- constants ----------
    Vout, fsw, fline, nph = spec.Vout, spec.fsw, spec.fline, spec.nph
    N, le_cm, Ae = wind.N, core.le_cm, core.Ae
    L0_nom = core.AL_total * N ** 2
    L0_min = L0_nom * (1 - core.AL_tol)
    L0_max = L0_nom * (1 + core.AL_tol)

    # ---------- winding statics ----------
    MLT_mm = 2 * (core.width_mm + core.stack_height_mm) + wind.build_mm       # E17 (G8)
    ell_cu = N * MLT_mm / 1000.0                                              # m
    A_cu_m2 = wind.A_cu_mm2 * 1e-6
    DCR25 = RHO_CU_20 * (1 + ALPHA_CU * 5) * ell_cu / (wind.n_par * wind.A_bundle_mm2 * 1e-6)  # E18
    def DCR(T):  return DCR25 * (1 + ALPHA_CU * (T - 25))
    FFcu = wind.A_cu_mm2 * N / core.Wa                                        # window fill
    delta = skin_depth_m(fsw)                                                # E19
    skin_ok = wind.strand_d_mm / 1000.0 < 2 * delta
    harm_fac = harmonic_ac_excess_factor(wind.Rac_Rdc)                        # E21

    theta = np.linspace(1e-3, math.pi - 1e-3, n_theta)
    rows = []
    for op in spec.points:
        # ---------- S3: currents & duty (E1-E4) ----------
        Pin = op.Pout / op.eta
        Vpk = math.sqrt(2) * op.Vin
        Iin_rms = Pin / (op.Vin * op.PF)
        Iin_pk = math.sqrt(2) * Iin_rms
        Iphi_crest = Iin_pk / nph                                # E3  (G2: /nph, NOT /2nph)
        Dpk = 1 - Vpk / Vout                                     # E4

        # ---------- S6: DC bias & biased inductance (E9-E10, G6/G12) ----------
        Hc = H_oe(N, Iphi_crest, le_cm)
        kc = float(mat.k_bias(Hc))            # catalog bias curve == small-AC incremental perm (G12)
        L_nom = kc * L0_nom

        # ---------- waveforms over half line cycle ----------
        Vin_t = Vpk * np.sin(theta)
        D_t = np.clip(1 - Vin_t / Vout, 0, 1)
        iavg = Iphi_crest * np.sin(theta)                        # per-phase avg current
        dIpp = Vin_t * D_t / (L_nom * fsw)                       # E6/ripple (uses biased L)
        Bac_t = Vin_t * D_t / (2 * N * Ae * fsw)                 # E13 B_ac,pk(theta)
        Bac_crest = Vpk * Dpk / (2 * N * Ae * fsw)
        Bac_max = float(Bac_t.max())

        # ---------- S7: flux density (E11-E12, G4/G5) ----------
        ipk_inst = iavg + dIpp / 2
        Bmax = float((L_nom * ipk_inst / (N * Ae)).max())
        Ipk_inst = float(ipk_inst.max())
        Hpk = H_oe(N, Ipk_inst, le_cm)
        Lfull_min_pk = float(mat.k_bias(Hpk)) * L0_min           # min-L guarantee point

        # ---------- S9: per-phase RMS (E20) & copper loss (E21) ----------
        Irms_LF = Iphi_crest / math.sqrt(2)
        Irms_HF = math.sqrt(np.trapezoid((dIpp / (2 * math.sqrt(3))) ** 2, theta) / math.pi)
        Iphi_rms = math.sqrt(Irms_LF ** 2 + Irms_HF ** 2)
        def Pcu(T):
            return Iphi_rms ** 2 * DCR(T) + Irms_HF ** 2 * (wind.Rac_Rdc - 1) * harm_fac * DCR(T)
        Pcu100 = Pcu(lim.Twind_C); Pcu25 = Pcu(25.0)

        # ---------- S8: core loss (E13-E16, G11: no DC-bias adder) ----------
        if core_loss_method == "cycle_avg_igse":
            Pcore_t = mat.core_loss_density(Bac_t, fsw / 1e3) * mat.F_D(D_t, Ic) * core.Ve / 1e3
            Pcore = float(np.trapezoid(Pcore_t, theta) / math.pi)
            Pcore_pk = float(Pcore_t.max())
        elif core_loss_method == "peak_point":               # legacy method (for comparison)
            Pcore = float(mat.core_loss_density(Bac_crest, fsw / 1e3) * core.Ve / 1e3)
            Pcore_pk = Pcore
        else:
            raise ValueError("core_loss_method must be 'cycle_avg_igse' or 'peak_point'")
        Pcore_max = Pcore * mat.loss_max_scale

        Ptot_typ = Pcore + Pcu100
        Ptot_max = Pcore_max + Pcu100

        rows.append(dict(Vin=op.Vin, Pout=op.Pout, eta=op.eta, PF=op.PF, Pin=Pin,
                         Vpk=Vpk, Iin_rms=Iin_rms, Iin_pk=Iin_pk, Iphi_crest=Iphi_crest,
                         Dpk=Dpk, Hc=Hc, k=kc, L_nom_uH=L_nom*1e6,
                         L_min_uH=kc*L0_min*1e6, L_max_uH=kc*L0_max*1e6,
                         Bac_crest=Bac_crest, Bac_max=Bac_max, Bmax=Bmax,
                         Iphi_rms=Iphi_rms, Irms_HF=Irms_HF,
                         dIpp_crest=float(Vpk*Dpk/(L_nom*fsw)), dIpp_max=float(dIpp.max()),
                         Ipk_inst=Ipk_inst, Hpk=Hpk, Lfull_min_pk_uH=Lfull_min_pk*1e6,
                         Pcu25=Pcu25, Pcu100=Pcu100,
                         Pcore=Pcore, Pcore_max=Pcore_max, Pcore_pk=Pcore_pk,
                         Ptot_typ=Ptot_typ, Ptot_max=Ptot_max))

    # ---------- S10: thermal (E22-E25) ----------
    OD_w = core.OD_mm + 2 * (wind.A_bundle_mm2 ** 0.5)        # crude wound-OD estimate
    OH = core.stack_height_mm + 2 * (wind.A_bundle_mm2 ** 0.5) + 6.6
    hole = max(core.ID_mm - 2 * (wind.A_bundle_mm2 ** 0.5), 1.0)
    SA = (math.pi*OD_w*OH + (math.pi/2)*(OD_w**2 - hole**2) + math.pi*hole*OH) / 100.0  # cm^2
    # forced-convection h ratio (Hilpert cross-flow) vs embedded-radiation natural law
    def dT_natural(P_W):  return (P_W * 1e3 / SA) ** 0.833                 # E23 (radiation embedded)
    def dT_forced(P_W):
        L = OD_w / 1000.0; Re = airflow_mps * L / 1.57e-5
        Nu = 0.466 * Re ** 0.5 * 0.71 ** (1 / 3); h = Nu * 0.0263 / L
        Ts = lim.Tamb_C + dT_natural(P_W)                                  # iterate-free estimate
        hrad = 0.9 * 5.67e-8 * 4 * ((Ts + lim.Tamb_C) / 2 + 273.15) ** 3
        return P_W / (SA / 1e4 * (h + hrad))                               # E24 (conv + radiation)
    for r in rows:
        r["dT_nat"] = dT_natural(r["Ptot_max"])
        r["dT_forced"] = dT_forced(r["Ptot_max"])
        r["dT"] = r["dT_forced"] if cooling == "forced" else r["dT_nat"]

    # ---------- S11: worst-case extraction (G4) & verdict ----------
    wc_loss = max(rows, key=lambda r: r["Ptot_max"])
    wc_B = max(rows, key=lambda r: r["Bmax"])
    wc_dT = max(rows, key=lambda r: r["dT"])
    Lmin_guarantee = min(r["Lfull_min_pk_uH"] for r in rows)
    J = max(r["Iphi_rms"] for r in rows) / wind.A_cu_mm2

    asserts = {
        "material_validated": (len(mat_fails) == 0, mat_fails),
        "L_guarantee": (Lmin_guarantee >= lim.L_target_uH,
                        f"{Lmin_guarantee:.1f} >= {lim.L_target_uH} uH"),
        "saturation": (wc_B["Bmax"] <= (1 - lim.sat_margin_min) * mat.Bsat,
                       f"Bmax {wc_B['Bmax']:.3f} T vs Bsat {mat.Bsat} T"),
        "window_fill": (FFcu <= lim.FFcu_limit, f"FFcu {FFcu*100:.1f}% <= {lim.FFcu_limit*100:.0f}%"),
        "skin_depth": (skin_ok, f"strand {wind.strand_d_mm} mm < 2*delta {2*delta*1e3:.3f} mm"),
        "thermal": (wc_dT["dT"] <= (lim.Thot_C - lim.Tamb_C),
                    f"dT {wc_dT['dT']:.1f} <= {lim.Thot_C-lim.Tamb_C:.0f} C"),
    }
    verdict = "APPROVE" if all(v[0] for v in asserts.values()) else "REJECT"

    return dict(
        meta=dict(material=f"{mat.name} {mat.mu}u", Bsat=mat.Bsat, stacks=core.stacks,
                  N=N, core_loss_method=core_loss_method, cooling=cooling,
                  airflow_mps=airflow_mps if cooling == "forced" else None),
        statics=dict(L0_nom_uH=L0_nom*1e6, L0_min_uH=L0_min*1e6, L0_max_uH=L0_max*1e6,
                     MLT_mm=MLT_mm, ell_cu_m=ell_cu, DCR25_mohm=DCR25*1e3,
                     DCR100_mohm=DCR(100)*1e3, FFcu=FFcu, J_AperMM2=J,
                     skin_depth_mm=delta*1e3, SA_cm2=SA, Fd_integral=Ic,
                     harm_factor=harm_fac),
        points=rows,
        worst=dict(loss=dict(Vin=wc_loss["Vin"], Ptot_typ=wc_loss["Ptot_typ"], Ptot_max=wc_loss["Ptot_max"]),
                   Bmax=dict(Vin=wc_B["Vin"], Bmax=wc_B["Bmax"],
                             sat_margin_pct=(mat.Bsat-wc_B["Bmax"])/wc_B["Bmax"]*100),
                   dT=dict(Vin=wc_dT["Vin"], dT=wc_dT["dT"]),
                   Lmin_guarantee_uH=Lmin_guarantee),
        asserts=asserts, verdict=verdict, material_failures=mat_fails)


# ====================================================================================
#  REPORTING HELPERS
# ====================================================================================
def print_report(res: dict):
    m = res["meta"]; s = res["statics"]
    print(f"\n=== {m['material']} x{m['stacks']}  N={m['N']}  ({m['core_loss_method']}, {m['cooling']}) ===")
    print(f"L0 = {s['L0_min_uH']:.1f}/{s['L0_nom_uH']:.1f}/{s['L0_max_uH']:.1f} uH   "
          f"MLT={s['MLT_mm']:.1f} mm  DCR25/100={s['DCR25_mohm']:.3f}/{s['DCR100_mohm']:.3f} mOhm")
    print(f"FFcu={s['FFcu']*100:.1f}%  J={s['J_AperMM2']:.2f} A/mm2  skin_d={s['skin_depth_mm']:.3f} mm  "
          f"SA={s['SA_cm2']:.0f} cm2")
    h = ("Vin","Iphi_rms","Dpk","H(Oe)","k%","Lnom","Bac_cr","Bmax","Pcu100","Pcore","Ptot_typ","dT")
    print("".join(f"{x:>9}" for x in h))
    for r in res["points"]:
        print(f"{r['Vin']:>9.0f}{r['Iphi_rms']:>9.3f}{r['Dpk']:>9.3f}{r['Hc']:>9.1f}{r['k']*100:>9.2f}"
              f"{r['L_nom_uH']:>9.1f}{r['Bac_crest']:>9.4f}{r['Bmax']:>9.3f}{r['Pcu100']:>9.3f}"
              f"{r['Pcore']:>9.3f}{r['Ptot_typ']:>9.3f}{r['dT']:>9.1f}")
    w = res["worst"]
    print(f"WORST loss {w['loss']['Vin']:.0f}V: {w['loss']['Ptot_typ']:.2f}W typ / {w['loss']['Ptot_max']:.2f}W max"
          f"   Bmax {w['Bmax']['Bmax']:.3f}T @{w['Bmax']['Vin']:.0f}V (margin {w['Bmax']['sat_margin_pct']:.0f}%)"
          f"   dT {w['dT']['dT']:.1f}C @{w['dT']['Vin']:.0f}V")
    print(f"L_guarantee min = {w['Lmin_guarantee_uH']:.1f} uH    VERDICT: {res['verdict']}")
    for k, v in res["asserts"].items():
        print(f"   [{'PASS' if v[0] else 'FAIL'}] {k}: {v[1]}")


# ====================================================================================
#  DEMO -- reproduces the EDGE 0059214A2 x3 (75u) / Vout=394 corrected report
# ====================================================================================
if __name__ == "__main__":
    spec = ConverterSpec(
        Vout=394.0, fsw=70e3, fline=60.0, nph=2, r=0.095,
        points=[OperatingPoint(90,1700,0.945,0.9987), OperatingPoint(110,1700,0.955,0.9986),
                OperatingPoint(120,1700,0.965,0.9985), OperatingPoint(132,1700,0.975,0.9980),
                OperatingPoint(180,3600,0.965,0.9889), OperatingPoint(200,3600,0.975,0.9884),
                OperatingPoint(220,3600,0.985,0.9790), OperatingPoint(230,3600,0.988,0.9789),
                OperatingPoint(264,3600,0.990,0.9520)])
    core = CoreGeometry(Ae_mm2=144.0, le_mm=143.0, Ve_cm3=62.1/3, Wa_mm2=948.0,
                        OD_mm=58.04, ID_mm=34.75, HT_mm=14.86, AL_nom_nH=94.0, stacks=3)
    mat = MaterialModel.edge(75)
    mat.loss_anchor = (0.1, 100.0, 424.0)          # 75u typical curve anchor
    mat.bias_anchors = ((105.0, 80.0),)            # 80% retention at 105 Oe (75u curve)
    wind = Winding(N=31, strand_d_mm=0.1, n_strands=800, n_par=2, build_mm=3.8)
    lim = AcceptanceLimits(L_target_uH=239.0)

    improved = analyze(spec, core, mat, wind, lim, core_loss_method="cycle_avg_igse")
    legacy   = analyze(spec, core, mat, wind, lim, core_loss_method="peak_point")
    print_report(improved)
    print("\n--- LEGACY peak-point core loss (for comparison) ---")
    for r in legacy["points"]:
        print(f"  {r['Vin']:.0f}V  Pcore_peak={r['Pcore']:.3f}W  (vs improved cyc-avg)")
    # machine-readable verdict block (Section 9)
    with open("result.json", "w") as f:
        json.dump({k: improved[k] for k in ("meta","statics","worst","verdict")}, f, indent=2)
    print("\nWrote result.json")
