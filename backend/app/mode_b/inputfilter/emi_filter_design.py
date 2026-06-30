#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
emi_filter_design.py
====================================================================
Conducted-EMI filter synthesis (DM + CM) for the universal-input
2-phase interleaved totem-pole PFC front end.

PIPELINE ROLE
  This is the LAST stage of a bigger design script (PFC -> MOV -> NTC
  -> EMI). It is written as a PURE function that consumes a shared
  DesignContext produced by the earlier stages and returns an EMIResult
  (also attached to ctx.emi). It does not print, use globals, or re-
  derive anything an upstream stage already provided.

  >>> ctx = DesignContext(...)            # populated by PFC/MOV/NTC
  >>> result = design_emi_filter(ctx)      # pure, deterministic
  >>> render_report(result)                # optional, standalone only

  NOTE: field names in the dataclasses below are a PROPOSED contract.
  During integration they get remapped to the bigger script's real
  schema; the physics/standards logic stays put.

DESIGN DISCIPLINE (two orthogonal designer inputs)
  - safety_standard    -> earth-leakage current ceiling (hard cap on
                          total Y-capacitance), X-cap discharge rule,
                          required cap class. (Verify numbers vs the
                          standard edition in force.)
  - compliance_standard-> conducted emission envelope (CISPR 11/EN55011,
                          CISPR 32/EN55032, FCC 15.107, VCCI), Class A/B,
                          detector; radiated lines flagged as guidance.
  - margin_db          -> separate scalar (your 6 dB).
  They pull opposite ways: compliance wants more C_Y (CM attenuation),
  safety caps C_Y (leakage). The synthesis finds the CM choke that meets
  compliance WITHIN the leakage ceiling, and flags infeasibility back to
  the pipeline rather than silently violating either.

METHOD (industry-standard required-attenuation flow)
  1. Noise at the LISN: DM from input ripple harmonics; CM from
     C_parasitic*dv/dt. Prefer an upstream-provided measured spectrum;
     else first-order ESTIMATE (clearly tagged).
  2. Interleaving: first in-band DM harmonic at n_phases*f_sw; peaks
     below 150 kHz are outside the measured band.
  3. Required attenuation = noise - (limit - margin) over 150k-30MHz.
  4. Corner from slope (40 dB/dec per LC stage); escalate to 2 stages
     (80 dB/dec) if one stage needs an impractical corner.
  5. Split corner into L,C under constraints: C_Y from leakage budget
     first then solve L_CM; C_X grown for DM then solve/limit L_DM.
  6. Damping (parallel R-C) + Middlebrook input-impedance stability.

Run:  python3 emi_filter_design.py            (demo report)
      python3 emi_filter_design.py --selftest  (prove the logic)
      python3 emi_filter_design.py --verify    (back-check PDF chain)
====================================================================
"""

from __future__ import annotations
from dataclasses import dataclass, field
from math import pi, sqrt, log10
from typing import Optional, List, Tuple, Dict
import sys


TWO_PI = 2.0 * pi


# ============================================================== #
#  EXCEPTIONS                                                    #
# ============================================================== #

class EMIContractError(ValueError):
    """Missing/invalid upstream field -- fail loud in a pipeline."""


# ============================================================== #
#  STANDARDS DATA (auditable lookup tables)                     #
# ============================================================== #
# Earth-leakage current ceilings [A]. REPRESENTATIVE values --
# confirm against the exact standard edition/condition at integration.
SAFETY_LEAKAGE_LIMIT = {
    "IEC_62368_1": 3.5e-3,   # AV/IT, pluggable Type A
    "IEC_60950_1": 3.5e-3,   # legacy IT
    "IEC_61010_1": 3.5e-3,   # measurement/lab
    "IEC_60335_1": 0.75e-3,  # household appliance (portable)
    "IEC_60601_1": 0.5e-3,   # medical earth leakage, normal condition
}
# X-cap discharge time limit [s] (bleeder must drain X-caps below safe V).
SAFETY_XCAP_DISCHARGE_S = {
    "IEC_62368_1": 1.0, "IEC_60950_1": 1.0, "IEC_61010_1": 1.0,
    "IEC_60335_1": 1.0, "IEC_60601_1": 1.0,
}

# Compliance profiles -> binding conducted class + default detector +
# radiated applicability. Conducted limits of CISPR11/CISPR32/FCC15.107
# are harmonized, so the strictest class present governs.
COMPLIANCE_PROFILE = {
    # id: (binding_conducted_class, detector, radiated_applies, label)
    1: ("B", "AV", True,  "EN55011 B + EN55032 B + FCC B (6 dB), all-Class-B"),
    2: ("B", "AV", False, "EN55011 B (6 dB) + EN55011 A -> Class B binds"),
    3: ("A", "AV", True,  "EN55032 A (6 dB)"),
    4: ("A", "AV", True,  "EN55011 A + EN55032 A + FCC 15.109 A + VCCI A"),
    5: ("B", "AV", True,  "EN55011 B + EN55032 B + FCC 15.107 B + VCCI B"),
}


def conducted_limit_dbuv(f_hz: float, klass: str, detector: str) -> float:
    """Mains-port conducted limit line [dBuV] vs frequency.
       Canonical CISPR/FCC values; 0.15-0.5 MHz slopes linearly in
       dB vs log(f)."""
    f = f_hz
    def slope(v1, v2, f1=150e3, f2=500e3):
        return v1 + (v2 - v1) * (log10(f / f1) / log10(f2 / f1))
    if klass == "B":
        if detector == "QP":
            if f < 500e3:  return slope(66, 56)
            if f <= 5e6:   return 56.0
            return 60.0
        else:  # AV
            if f < 500e3:  return slope(56, 46)
            if f <= 5e6:   return 46.0
            return 50.0
    else:  # Class A
        if detector == "QP":
            return 79.0 if f < 500e3 else 73.0
        else:
            return 66.0 if f < 500e3 else 60.0


# LISN modal impedances [ohm] (50ohm/50uH V-network, CISPR 16).
Z_LISN_DM = 100.0   # two 50 ohm in series (line-to-line)
Z_LISN_CM = 25.0    # two 50 ohm in parallel (lines-to-PE)

CONDUCTED_FMIN = 150e3
CONDUCTED_FMAX = 30e6


# ============================================================== #
#  DESIGN CONTEXT  (proposed shared-pipeline schema)            #
# ============================================================== #

@dataclass
class PFCResult:
    """Produced by the PFC stage."""
    vac_min: float            # V
    vac_max: float            # V
    f_line: float             # Hz
    v_bus: float              # V
    p_out: float              # W
    eff: float                # 0..1
    f_sw: float               # Hz, per-phase switching frequency
    n_phases: int             # interleave count (2)
    i_ripple_pp: float        # A, input current ripple peak-peak
    esr_bulk: Optional[float] = None   # ohm, bulk-cap ESR (DM noise est.)
    dvdt: Optional[float] = None       # V/s, switch-node slew (CM est.)
    c_para_earth: Optional[float] = None  # F, node-to-earth parasitic (CM est.)
    sw_rise_time: Optional[float] = 20e-9  # s, edge time (CM roll-off knee)


@dataclass
class ProtectionResult:
    """Produced by the MOV / protection stage."""
    committed_y_cap_total: float = 0.0   # F, Y-caps/GDT already placed


@dataclass
class NTCResult:
    """Produced by the NTC stage (bookkeeping for the DM path/BOM)."""
    r_ntc_cold: float = 0.0   # ohm (bypassed in steady state)


@dataclass
class NoiseSpectrum:
    """Optional measured/simulated bare-EUT noise (preferred over estimate).
       Each list is [(f_Hz, dBuV), ...]."""
    dm: Optional[List[Tuple[float, float]]] = None
    cm: Optional[List[Tuple[float, float]]] = None


@dataclass
class EMIInputs:
    """Designer choices for this stage."""
    safety_standard: str = "IEC_62368_1"
    compliance_profile: int = 5
    margin_db: float = 6.0
    detector: Optional[str] = None     # override profile default if set
    # synthesis practical bounds
    cx_max: float = 4.7e-6             # F, practical max single X-cap
    ldm_sat_max: float = 100e-6        # H, saturation-practical DM choke
    leakage_use_fraction: float = 0.90 # design to 90% of the leakage limit
    bleeder_r: Optional[float] = None  # ohm, X-cap discharge resistor (if known)


@dataclass
class DesignContext:
    pfc: PFCResult
    protection: ProtectionResult
    ntc: NTCResult
    emi_in: EMIInputs
    noise: NoiseSpectrum = field(default_factory=NoiseSpectrum)
    emi: Optional["EMIResult"] = None   # output slot (filled by the stage)


# ============================================================== #
#  RESULT                                                       #
# ============================================================== #

@dataclass
class EMIResult:
    feasible: bool
    # resolved basis
    conducted_class: str
    detector: str
    margin_db: float
    leakage_limit_A: float
    first_harmonic_hz: float
    # required attenuation
    dm_req_att_db: float
    dm_req_att_f: float
    cm_req_att_db: float
    cm_req_att_f: float
    dm_stages: int
    cm_stages: int
    dm_corner_hz: float
    cm_corner_hz: float
    # components
    c_x: float
    l_dm: float
    c_y_emi_total: float       # added by THIS stage
    c_y_system_total: float    # incl. upstream committed
    l_cm: float
    damp_r: float
    damp_c: float
    # checks
    leakage_actual_A: float
    xcap_discharge_s: Optional[float]
    stability_z0_dm: float
    stability_rin_conv: float
    stability_ok: bool
    # bookkeeping
    provenance: Dict[str, str] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    feedback: List[str] = field(default_factory=list)  # pipeline re-visit asks
    noise_source: str = "estimate"


# ============================================================== #
#  VALIDATION                                                    #
# ============================================================== #

def _require(cond, msg):
    if not cond:
        raise EMIContractError(msg)


def validate(ctx: DesignContext):
    p = ctx.pfc
    _require(p is not None, "ctx.pfc missing (PFC stage output required)")
    for nm in ("vac_min", "vac_max", "f_line", "v_bus", "p_out", "eff",
               "f_sw", "n_phases", "i_ripple_pp"):
        v = getattr(p, nm, None)
        _require(v is not None and v > 0, f"pfc.{nm} missing/invalid ({v!r})")
    _require(ctx.emi_in.safety_standard in SAFETY_LEAKAGE_LIMIT,
             f"safety_standard must be one of {list(SAFETY_LEAKAGE_LIMIT)}")
    _require(ctx.emi_in.compliance_profile in COMPLIANCE_PROFILE,
             f"compliance_profile must be one of {list(COMPLIANCE_PROFILE)}")


# ============================================================== #
#  NOISE MODELS  (prefer measured; else first-order estimate)   #
# ============================================================== #

def _interp_dbuv(spectrum, f):
    """Interpolate a measured spectrum (dBuV vs log f). Clamp to ends."""
    pts = sorted(spectrum)
    if f <= pts[0][0]:
        return pts[0][1]
    if f >= pts[-1][0]:
        return pts[-1][1]
    for (f0, v0), (f1, v1) in zip(pts, pts[1:]):
        if f0 <= f <= f1:
            return v0 + (v1 - v0) * (log10(f / f0) / log10(f1 / f0))
    return pts[-1][1]


def dm_noise_dbuv(ctx, f):
    """DM noise at the LISN [dBuV]."""
    if ctx.noise.dm:
        return _interp_dbuv(ctx.noise.dm, f), "measured"
    # ESTIMATE: triangular input ripple, harmonics ~1/n^2, develop voltage
    # across the bulk-cap ESR (HF-dominant shunt) -> seen by the LISN.
    p = ctx.pfc
    esr = p.esr_bulk if p.esr_bulk else 0.03   # ohm, flagged if defaulted
    f_first = p.n_phases * p.f_sw
    i_h1 = (4.0 / pi ** 2) * p.i_ripple_pp      # fundamental zero-to-peak
    n = max(1.0, round(f / f_first))
    i_h = i_h1 / (n ** 2)
    v = i_h * esr
    return 20.0 * log10(max(v, 1e-12) / 1e-6), "estimate"


def cm_noise_dbuv(ctx, f):
    """CM noise at the LISN [dBuV]."""
    if ctx.noise.cm:
        return _interp_dbuv(ctx.noise.cm, f), "measured"
    # ESTIMATE: I_cm ~ C_para*dv/dt; charge-per-edge Q=C*dV, envelope
    # I(f) ~ 2*Q*f_sw flat up to knee 1/(pi*t_r), then -20 dB/dec.
    p = ctx.pfc
    c_para = p.c_para_earth if p.c_para_earth else 50e-12
    dv = p.v_bus
    q = c_para * dv
    i_flat = 2.0 * q * p.f_sw
    f_knee = 1.0 / (pi * (p.sw_rise_time or 20e-9))
    i_cm = i_flat if f <= f_knee else i_flat * (f_knee / f)
    v = i_cm * Z_LISN_CM
    return 20.0 * log10(max(v, 1e-12) / 1e-6), "estimate"


# ============================================================== #
#  REQUIRED ATTENUATION + CORNER                                #
# ============================================================== #

def _freq_grid(f_lo, f_hi, n=240):
    out, r = [], (f_hi / f_lo) ** (1.0 / (n - 1))
    f = f_lo
    for _ in range(n):
        out.append(f); f *= r
    return out


def required_attenuation(ctx, noise_fn, klass, detector, margin):
    """Worst-case required attenuation over the conducted band, and the
       binding corner for a given number of LC stages."""
    p = ctx.pfc
    f_first = p.n_phases * p.f_sw
    f_lo = max(CONDUCTED_FMIN, f_first)        # interleaving: sub-150k is OOB
    grid = _freq_grid(f_lo, CONDUCTED_FMAX)
    worst_att, worst_f = -1e9, f_lo
    src = "estimate"
    for f in grid:
        nz, src = noise_fn(ctx, f)
        lim = conducted_limit_dbuv(f, klass, detector) - margin
        att = nz - lim
        if att > worst_att:
            worst_att, worst_f = att, f
    return max(worst_att, 0.0), worst_f, f_first, src


def corner_for(att_db, f_noise, order):
    """f_c such that an `order`-pole filter gives att_db at f_noise.
       slope = 20*order dB/decade."""
    return f_noise / (10 ** (att_db / (20.0 * order)))


def choose_stages_and_corner(att_db, f_noise, f_floor):
    """Single LC (order 2) if its corner is practical (>= f_floor), else
       two LC stages (order 4)."""
    fc1 = corner_for(att_db, f_noise, 2)
    if fc1 >= f_floor:
        return 1, fc1
    fc2 = corner_for(att_db, f_noise, 4)
    return 2, fc2


# ============================================================== #
#  CORE SYNTHESIS                                               #
# ============================================================== #

def design_emi_filter(ctx: DesignContext) -> EMIResult:
    """Pure function: DesignContext -> EMIResult (also set on ctx.emi)."""
    validate(ctx)
    p, prot, ein = ctx.pfc, ctx.protection, ctx.emi_in
    klass, prof_det, _rad, _label = COMPLIANCE_PROFILE[ein.compliance_profile]
    detector = ein.detector or prof_det
    margin = ein.margin_db
    prov: Dict[str, str] = {}
    warn: List[str] = []
    fb: List[str] = []

    # corner floor: a few x line freq (avoid disturbing line operation)
    f_floor = 20.0 * p.f_line

    # ---- required attenuation per mode ----
    dm_att, dm_f, f_first, dm_src = required_attenuation(
        ctx, dm_noise_dbuv, klass, detector, margin)
    cm_att, cm_f, _, cm_src = required_attenuation(
        ctx, cm_noise_dbuv, klass, detector, margin)
    noise_source = "measured" if (dm_src == "measured" and cm_src == "measured") \
        else "estimate"
    if noise_source == "estimate":
        warn.append("Noise is a first-order ESTIMATE; replace with measured "
                    "bare-EUT spectrum for compliance sign-off.")
    if not p.esr_bulk and not ctx.noise.dm:
        warn.append("pfc.esr_bulk defaulted (0.03 ohm) for DM estimate.")
    if not p.c_para_earth and not ctx.noise.cm:
        warn.append("pfc.c_para_earth defaulted (50 pF) for CM estimate.")
    prov["dm_req_att"] = f"DM noise({dm_src}) - (ClassB/A limit - {margin}dB) @ {dm_f/1e3:.0f}kHz"
    prov["cm_req_att"] = f"CM noise({cm_src}) - (limit - {margin}dB) @ {cm_f/1e3:.0f}kHz"

    # ---- stages + corners ----
    dm_stages, dm_fc = choose_stages_and_corner(dm_att, dm_f, f_floor)
    cm_stages, cm_fc = choose_stages_and_corner(cm_att, cm_f, f_floor)
    prov["dm_corner"] = f"{dm_stages} LC stage(s), {20*2*dm_stages} dB/dec to meet {dm_att:.0f} dB"
    prov["cm_corner"] = f"{cm_stages} LC stage(s) to meet {cm_att:.0f} dB"

    # ---- CM: leakage budget fixes C_Y, then solve L_CM ----
    leak_limit = SAFETY_LEAKAGE_LIMIT[ein.safety_standard]
    v_ln = p.vac_max
    cy_total_max = (ein.leakage_use_fraction * leak_limit) / (TWO_PI * p.f_line * v_ln)
    cy_remaining = cy_total_max - prot.committed_y_cap_total
    prov["c_y"] = (f"C_Y ceiling from {ein.safety_standard} leakage "
                   f"{leak_limit*1e3:.2f}mA -> {cy_total_max*1e9:.2f}nF total; "
                   f"upstream committed {prot.committed_y_cap_total*1e9:.2f}nF")
    if cy_remaining <= 0:
        fb.append(f"INFEASIBLE: upstream Y-cap ({prot.committed_y_cap_total*1e9:.2f}nF) "
                  f"already exceeds the {ein.safety_standard} leakage ceiling "
                  f"({cy_total_max*1e9:.2f}nF). Revisit protection-stage Y-caps or "
                  f"the safety standard.")
        cy_emi = 0.0
        l_cm = float("inf")
    else:
        cy_emi = cy_remaining
        # CM corner: f0 = 1/(2*pi*sqrt(L_cm * 2*C_Y))  (two Y-caps in parallel for CM)
        c_cm = 2.0 * cy_emi
        l_cm = 1.0 / ((TWO_PI * cm_fc) ** 2 * c_cm)
        prov["l_cm"] = f"L_CM = 1/((2*pi*{cm_fc/1e3:.1f}kHz)^2 * 2*C_Y)"

    cy_system = prot.committed_y_cap_total + cy_emi

    # ---- DM: grow C_X (cheap) then solve/limit L_DM ----
    c_x = min(ein.cx_max, ein.cx_max)   # start at practical max for headroom
    l_dm = 1.0 / ((TWO_PI * dm_fc) ** 2 * c_x)
    if l_dm > ein.ldm_sat_max:
        # need more C_X than cx_max OR another stage; flag and clamp
        l_dm = ein.ldm_sat_max
        c_needed = 1.0 / ((TWO_PI * dm_fc) ** 2 * l_dm)
        warn.append(f"DM corner needs C_X ~ {c_needed*1e6:.2f}uF (> cx_max "
                    f"{ein.cx_max*1e6:.2f}uF). Add an X-cap bank or a 2nd DM stage.")
        c_x = ein.cx_max
    prov["l_dm"] = f"L_DM from DM corner {dm_fc/1e3:.1f}kHz with C_X {c_x*1e6:.2f}uF (sat-limited {ein.ldm_sat_max*1e6:.0f}uH)"

    # ---- damping (parallel R-C) + Middlebrook stability ----
    z0_dm = sqrt(l_dm / c_x)
    damp_c = 4.0 * c_x
    damp_r = z0_dm                      # ~characteristic impedance (near-optimal)
    rin_conv = (p.vac_min ** 2) / (p.p_out / max(p.eff, 1e-3))  # |neg input R|
    stability_ok = z0_dm < rin_conv
    prov["damping"] = f"R_d ~ sqrt(L/C)={z0_dm:.1f} ohm, C_d=4*C_X={damp_c*1e6:.2f}uF"
    prov["stability"] = (f"Middlebrook: Z0_dm {z0_dm:.1f} ohm vs |Rin_conv| "
                         f"{rin_conv:.1f} ohm")
    if not stability_ok:
        warn.append(f"Filter Z0 {z0_dm:.1f} ohm not << converter input "
                    f"{rin_conv:.1f} ohm; increase damping / C_X to ensure stability.")

    # ---- leakage check (system) ----
    leak_actual = TWO_PI * p.f_line * v_ln * cy_system
    if leak_actual > leak_limit:
        fb.append(f"Leakage {leak_actual*1e3:.2f}mA exceeds {ein.safety_standard} "
                  f"limit {leak_limit*1e3:.2f}mA.")

    # ---- X-cap discharge ----
    xcap_disc = None
    if ein.bleeder_r:
        xcap_disc = ein.bleeder_r * c_x
        lim = SAFETY_XCAP_DISCHARGE_S[ein.safety_standard]
        if xcap_disc > lim:
            warn.append(f"X-cap discharge {xcap_disc:.2f}s > {lim:.1f}s limit; "
                        f"lower bleeder R.")
    else:
        warn.append("No bleeder_r given; verify X-cap discharge-time safety rule.")

    feasible = (len(fb) == 0)

    res = EMIResult(
        feasible=feasible,
        conducted_class=klass, detector=detector, margin_db=margin,
        leakage_limit_A=leak_limit, first_harmonic_hz=f_first,
        dm_req_att_db=dm_att, dm_req_att_f=dm_f,
        cm_req_att_db=cm_att, cm_req_att_f=cm_f,
        dm_stages=dm_stages, cm_stages=cm_stages,
        dm_corner_hz=dm_fc, cm_corner_hz=cm_fc,
        c_x=c_x, l_dm=l_dm, c_y_emi_total=cy_emi, c_y_system_total=cy_system,
        l_cm=l_cm, damp_r=damp_r, damp_c=damp_c,
        leakage_actual_A=leak_actual, xcap_discharge_s=xcap_disc,
        stability_z0_dm=z0_dm, stability_rin_conv=rin_conv,
        stability_ok=stability_ok,
        provenance=prov, warnings=warn, feedback=fb, noise_source=noise_source,
    )
    ctx.emi = res
    return res


# ============================================================== #
#  VERIFY MODE  (back-check an existing chain, e.g. the PDF)     #
# ============================================================== #

def verify_corners(l_dm, c_x, l_cm, c_y_each):
    """Recompute DM/CM LC corners for an existing chain."""
    f_dm = 1.0 / (TWO_PI * sqrt(l_dm * c_x))
    f_cm = 1.0 / (TWO_PI * sqrt(l_cm * 2.0 * c_y_each))
    return f_dm, f_cm


# ============================================================== #
#  REPORT  (standalone only; pipeline uses the structured result)#
# ============================================================== #

def render_report(r: EMIResult) -> str:
    L = []; o = L.append
    o("=" * 70)
    o(" EMI FILTER (DM+CM) -- SYNTHESIS REPORT")
    o("=" * 70)
    o(f"\n[BASIS]  conducted Class {r.conducted_class} / {r.detector} detector, "
      f"margin {r.margin_db:.0f} dB, noise={r.noise_source}")
    o(f"         leakage limit {r.leakage_limit_A*1e3:.2f} mA; "
      f"first in-band harmonic {r.first_harmonic_hz/1e3:.0f} kHz")
    o(f"         FEASIBLE: {r.feasible}")

    o("\n[REQUIRED ATTENUATION]")
    o(f"    DM : {r.dm_req_att_db:5.1f} dB @ {r.dm_req_att_f/1e3:6.0f} kHz  "
      f"-> {r.dm_stages} stage(s), corner {r.dm_corner_hz/1e3:.1f} kHz")
    o(f"    CM : {r.cm_req_att_db:5.1f} dB @ {r.cm_req_att_f/1e3:6.0f} kHz  "
      f"-> {r.cm_stages} stage(s), corner {r.cm_corner_hz/1e3:.1f} kHz")

    o("\n[COMPONENTS]")
    o(f"    DM choke  L_DM   : {r.l_dm*1e6:8.2f} uH")
    o(f"    X-cap     C_X    : {r.c_x*1e6:8.3f} uF")
    o(f"    CM choke  L_CM   : "
      + ("inf (infeasible)" if r.l_cm == float('inf') else f"{r.l_cm*1e3:8.3f} mH"))
    o(f"    Y-cap (this stg) : {r.c_y_emi_total*1e9:8.3f} nF total "
      f"({r.c_y_emi_total*1e9/2:.3f} nF each L-PE / N-PE)")
    o(f"    Y-cap (system)   : {r.c_y_system_total*1e9:8.3f} nF total (incl. upstream)")
    o(f"    Damping  R_d/C_d : {r.damp_r:6.1f} ohm + {r.damp_c*1e6:.3f} uF")

    o("\n[CHECKS]")
    o(f"    Earth leakage    : {r.leakage_actual_A*1e3:.3f} mA "
      f"(limit {r.leakage_limit_A*1e3:.2f} mA) "
      f"-> {'OK' if r.leakage_actual_A <= r.leakage_limit_A else 'OVER'}")
    o(f"    Stability (MBK)  : Z0_dm {r.stability_z0_dm:.1f} ohm vs |Rin| "
      f"{r.stability_rin_conv:.1f} ohm -> {'OK' if r.stability_ok else 'CHECK'}")
    if r.xcap_discharge_s is not None:
        o(f"    X-cap discharge  : {r.xcap_discharge_s:.2f} s")

    o("\n[PROVENANCE]  (every output traces to an input)")
    for k, v in r.provenance.items():
        o(f"    {k:12}: {v}")

    if r.warnings:
        o("\n[WARNINGS]")
        for w in r.warnings:
            o(f"    - {w}")
    if r.feedback:
        o("\n[PIPELINE FEEDBACK -- revisit an earlier stage]")
        for f in r.feedback:
            o(f"    !! {f}")

    o("\n" + "=" * 70)
    o(" Numbers are TARGETS. Confirm core saturation/leakage-inductance vs")
    o(" datasheet, and re-run against a measured bare-EUT spectrum.")
    o("=" * 70)
    return "\n".join(L)


# ============================================================== #
#  DEMO CONTEXT  (stands in for the bigger pipeline)            #
# ============================================================== #

def demo_context() -> DesignContext:
    return DesignContext(
        pfc=PFCResult(
            vac_min=90, vac_max=264, f_line=60, v_bus=390, p_out=1900,
            eff=0.95, f_sw=70e3, n_phases=2, i_ripple_pp=4.0,
            esr_bulk=0.03, dvdt=20e9, c_para_earth=100e-12, sw_rise_time=20e-9),
        protection=ProtectionResult(committed_y_cap_total=2 * 22e-12),  # GDT-side Y
        ntc=NTCResult(r_ntc_cold=6.8),
        emi_in=EMIInputs(safety_standard="IEC_62368_1", compliance_profile=5,
                         margin_db=6.0, bleeder_r=1e6),
    )


# ============================================================== #
#  SELF-TEST  (proves the input steering)                       #
# ============================================================== #

def self_test():
    print("Running self-test (EMI synthesis steering)...")

    # 1) Class B demands a lower corner than Class A (stricter -> more atten).
    cb = demo_context(); cb.emi_in.compliance_profile = 5   # Class B
    ca = demo_context(); ca.emi_in.compliance_profile = 4   # Class A
    rb, ra = design_emi_filter(cb), design_emi_filter(ca)
    assert rb.dm_corner_hz <= ra.dm_corner_hz, "Class B should need <= DM corner"
    assert rb.cm_corner_hz <= ra.cm_corner_hz, "Class B should need <= CM corner"
    print(f"  [ok] Class B corner <= Class A (DM {rb.dm_corner_hz/1e3:.1f} "
          f"<= {ra.dm_corner_hz/1e3:.1f} kHz)")

    # 2) +margin lowers the corner (needs more attenuation).
    c0 = demo_context(); c0.emi_in.margin_db = 0
    c6 = demo_context(); c6.emi_in.margin_db = 6
    r0, r6 = design_emi_filter(c0), design_emi_filter(c6)
    assert r6.cm_corner_hz <= r0.cm_corner_hz, "more margin -> lower corner"
    print(f"  [ok] +6dB margin lowers CM corner "
          f"({r6.cm_corner_hz/1e3:.1f} <= {r0.cm_corner_hz/1e3:.1f} kHz)")

    # 3) Tighter safety standard -> smaller Y-cap ceiling -> larger L_CM.
    c_it = demo_context(); c_it.emi_in.safety_standard = "IEC_62368_1"   # 3.5mA
    c_med = demo_context(); c_med.emi_in.safety_standard = "IEC_60601_1" # 0.5mA
    r_it, r_med = design_emi_filter(c_it), design_emi_filter(c_med)
    assert r_med.c_y_emi_total < r_it.c_y_emi_total, "medical -> less Y-cap"
    assert r_med.l_cm > r_it.l_cm, "less Y-cap -> bigger CM choke"
    print(f"  [ok] medical leakage -> smaller C_Y ({r_med.c_y_emi_total*1e9:.2f} "
          f"< {r_it.c_y_emi_total*1e9:.2f} nF) and bigger L_CM")

    # 4) Leakage stays within the limit by construction.
    r = design_emi_filter(demo_context())
    assert r.leakage_actual_A <= r.leakage_limit_A + 1e-9, "leakage over limit"
    print(f"  [ok] leakage {r.leakage_actual_A*1e3:.3f} mA within "
          f"{r.leakage_limit_A*1e3:.2f} mA")

    # 5) System leakage budget: huge upstream Y-cap -> infeasible feedback.
    cbad = demo_context(); cbad.protection.committed_y_cap_total = 100e-9
    rbad = design_emi_filter(cbad)
    assert rbad.feasible is False and rbad.feedback, "should flag infeasible"
    print("  [ok] over-committed upstream Y-cap raises pipeline feedback")

    # 6) Interleaving sets the first in-band harmonic at n*f_sw.
    assert abs(r.first_harmonic_hz - 2 * 70e3) < 1, "first harmonic = 2*f_sw"
    print("  [ok] interleaving: first harmonic = n_phases * f_sw = 140 kHz")

    # 7) Contract validation rejects missing upstream fields.
    try:
        bad = demo_context(); bad.pfc.f_sw = 0
        validate(bad); assert False
    except EMIContractError:
        pass
    print("  [ok] contract validation rejects invalid PFC field")

    # 8) Verify mode reproduces the reference PDF corners.
    f_dm, f_cm = verify_corners(l_dm=15e-6, c_x=330e-9, l_cm=10e-3, c_y_each=470e-12)
    assert abs(f_dm - 71.53e3) < 300, f"DM corner {f_dm}"
    assert abs(f_cm - 51.91e3) < 300, f"CM corner {f_cm}"
    print(f"  [ok] verify mode matches PDF (DM {f_dm/1e3:.2f}kHz, CM {f_cm/1e3:.2f}kHz)")

    print("ALL SELF-TESTS PASSED.")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        self_test()
    elif "--verify" in sys.argv:
        f_dm, f_cm = verify_corners(15e-6, 330e-9, 10e-3, 470e-12)
        print(f"PDF chain check: DM corner {f_dm/1e3:.2f} kHz (report 71.53), "
              f"CM corner {f_cm/1e3:.2f} kHz (report 51.91)")
    else:
        ctx = demo_context()
        design_emi_filter(ctx)
        print(render_report(ctx.emi))
