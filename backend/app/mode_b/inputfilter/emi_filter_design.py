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
  6. Damping (series R-L across the DM choke, R_d grid-searched to minimise the
     computed output-impedance peak) + frequency-domain Middlebrook stability
     (|Z_out(f)| vs converter |Z_in(f)| at the DM resonance).

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
#  NAMED PARASITIC DEFAULTS  (App-B discipline)                 #
# ============================================================== #
# Every value below is a NAMED default, not a literal buried in the physics.
# Each is reported in the result provenance and, when used instead of a
# designer/measured value, downgrades the design grade (App B.2). They are
# generic assumptions — NOT reference-design-specific numbers. Override any of
# them through the input contract (DesignContext) with a real datasheet/measured
# value to raise the design grade.
DEFAULT_DVDT_PFC    = 10e9      # V/s  (10 V/ns)  PFC switch-node slew  (CM source)
DEFAULT_DIDT_PFC    = 500e9     # A/s  (500 A/us) PFC current slew      (DM HF corner)
DEFAULT_BULK_ESL    = 20e-9     # H    bulk-cap equivalent series inductance (DM shunt)
DEFAULT_BULK_ESR    = 5e-3      # ohm  bulk-cap equivalent series resistance
DEFAULT_C_NODE_PFC  = 47e-12    # F    PFC switch-node -> chassis parasitic (CM source)
DEFAULT_DVDT_PSFB   = 15e9      # V/s  (15 V/ns)  DC-DC primary switch-node slew
DEFAULT_C_NODE_PSFB = 33e-12    # F    DC-DC switch-node -> chassis parasitic
DEFAULT_C_PS        = 15e-12    # F    transformer primary<->secondary inter-winding
# ABCD real-component parasitics (self-resonance / ESR / ESL) — vendor data when known.
DEFAULT_XCAP_ESR    = 5e-3      # ohm  X-cap ESR
DEFAULT_XCAP_ESL    = 15e-9     # H    X-cap ESL  (X-cap SRF)
DEFAULT_YCAP_ESL    = 8e-9      # H    Y-cap ESL  (limits HF CM attenuation)
DEFAULT_LDM_CP      = 30e-12    # F    DM-choke self-capacitance (DM choke SRF)
DEFAULT_LCM_CP      = 15e-12    # F    CM-choke self-capacitance (CM choke SRF; caps HF CM)
# Choke DC resistances (copper loss, §15) and loss-estimate fractions.
DEFAULT_CMC1_DCR    = 15e-3     # ohm  CM choke 1 DCR (both conductors)
DEFAULT_CMC2_DCR    = 7e-3      # ohm  CM choke 2 DCR
DEFAULT_LDM_DCR     = 7e-3      # ohm  DM choke DCR
# Core and X-cap-ESR losses depend on core/vendor data not known pre-selection; default to a
# fraction of copper (the reference ratio ≈ 13% core, ≈ 1.2% ESR) — a named, reported ESTIMATE,
# overridable with a real figure. NOT an absolute hardcoded watt value.
DEFAULT_CORE_LOSS_FRAC = 0.13   # core loss ≈ 13% of total copper (estimate)
DEFAULT_XCAP_ESR_LOSS_FRAC = 0.012  # X-cap ESR loss ≈ 1.2% of total copper (estimate)


# ============================================================== #
#  COMPLEX-IMPEDANCE + ABCD TWO-PORT HELPERS                    #
# ============================================================== #

def _z_cap(f, c, esr=0.0, esl=0.0):
    """Series-RLC branch impedance of a real capacitor (ESR + jwESL + 1/jwC)."""
    if not c or c <= 0:
        return complex(1e18, 0.0)          # open (no cap)
    w = TWO_PI * f
    return complex(esr, w * esl - 1.0 / (w * c))


def _z_ind(f, l, dcr=0.0, cp=0.0):
    """Real inductor impedance: (DCR + jwL) in parallel with its self-capacitance
    Cp, giving a self-resonant peak then a capacitive HF tail (the physical reason
    a choke stops attenuating above its SRF)."""
    if not l or l <= 0:
        return complex(dcr, 0.0)
    w = TWO_PI * f
    zl = complex(dcr, w * l)
    if cp and cp > 0:
        zc = complex(0.0, -1.0 / (w * cp))
        return (zl * zc) / (zl + zc)
    return zl


def _abcd_series(z):
    """ABCD matrix of a series impedance."""
    return ((1.0 + 0j, z), (0j, 1.0 + 0j))


def _abcd_shunt(y):
    """ABCD matrix of a shunt admittance."""
    return ((1.0 + 0j, 0j), (y, 1.0 + 0j))


def _abcd_mul(m1, m2):
    (a1, b1), (c1, d1) = m1
    (a2, b2), (c2, d2) = m2
    return ((a1 * a2 + b1 * c2, a1 * b2 + b1 * d2),
            (c1 * a2 + d1 * c2, c1 * b2 + d1 * d2))


def _abcd_cascade(mats):
    """Cascade a list of ABCD sections (mains -> converter order)."""
    out = ((1.0 + 0j, 0j), (0j, 1.0 + 0j))
    for m in mats:
        out = _abcd_mul(out, m)
    return out


def _insertion_loss_db(abcd, z_src, z_load):
    """Insertion loss [dB] of a two-port between source Z_src and load Z_load:
    IL = 20 log10 |(A Z_L + B + C Z_S Z_L + D Z_S) / (Z_L + Z_S)|.  IL > 0 = attenuation."""
    (a, b), (c, d) = abcd
    num = a * z_load + b + c * z_src * z_load + d * z_src
    den = z_load + z_src
    return 20.0 * log10(abs(num / den))


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
    dvdt: Optional[float] = None       # V/s, switch-node slew (CM est.) [legacy]
    c_para_earth: Optional[float] = None  # F, node-to-earth parasitic (CM est.) [legacy]
    sw_rise_time: Optional[float] = 20e-9  # s, edge time (CM roll-off knee) [legacy]
    # --- computed-source-model inputs (Phase 1; all optional -> named defaults) ---
    l_boost: Optional[float] = None     # H, per-phase boost inductance (DM ripple ΔI)
    bulk_c: Optional[float] = None      # F, bulk-cap capacitance (DM shunt path)
    bulk_esl: Optional[float] = None    # H, bulk-cap ESL (DM shunt) [def DEFAULT_BULK_ESL]
    dvdt_pfc: Optional[float] = None    # V/s, PFC switch-node slew (CM) [def DEFAULT_DVDT_PFC]
    didt_pfc: Optional[float] = None    # A/s, PFC current slew (DM HF corner) [def DEFAULT_DIDT_PFC]
    c_node_pfc: Optional[float] = None  # F, PFC switch-node->chassis (CM) [def DEFAULT_C_NODE_PFC]
    points: Optional[List["OperatingPoint"]] = None  # per-op grid (V_in, duty, ΔI, I_in)


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
class OperatingPoint:
    """One line/load operating point from the shared PFC grid (source-model input)."""
    v_in: float                       # Vac rms
    duty: float                       # peak duty D
    i_in: float                       # A rms input current
    delta_i: Optional[float] = None   # A, per-phase input ripple pp (else computed from l_boost)
    f_line: float = 60.0              # Hz


@dataclass
class DCDCResult:
    """DC-DC stage inputs feeding the common-mode source model. `present=False` →
    PFC-only design: the DC-DC/transformer CM terms are dropped entirely (no hidden
    contribution). Designer-supplied placeholders now; wired from the DC-DC script later.
    All parasitics optional -> named defaults (provenance 'assumed')."""
    present: bool = False
    f_sw: Optional[float] = None        # Hz, DC-DC switching frequency
    topology: str = ""                  # e.g. 'psfb', 'llc'
    v_node: Optional[float] = None      # V, primary switch-node voltage swing (≈ V_bus)
    dvdt_psfb: Optional[float] = None   # V/s, primary switch-node slew [def DEFAULT_DVDT_PSFB]
    c_node_psfb: Optional[float] = None # F, switch-node->chassis [def DEFAULT_C_NODE_PSFB]
    c_ps: Optional[float] = None        # F, transformer primary<->secondary [def DEFAULT_C_PS]
    dvdt_sec: Optional[float] = None    # V/s, secondary slew (optional)


@dataclass
class FilterParasitics:
    """Real-component parasitics for the ABCD insertion-loss model. Vendor SPICE /
    S-parameter data when known; otherwise named defaults (provenance 'assumed')."""
    xcap_esr: Optional[float] = None    # ohm  [def DEFAULT_XCAP_ESR]
    xcap_esl: Optional[float] = None    # H    [def DEFAULT_XCAP_ESL]
    ycap_esl: Optional[float] = None    # H    [def DEFAULT_YCAP_ESL]
    ldm_cp: Optional[float] = None      # F    DM-choke self-capacitance [def DEFAULT_LDM_CP]
    lcm_cp: Optional[float] = None      # F    CM-choke self-capacitance [def DEFAULT_LCM_CP]
    # choke DC resistances (§15 copper loss) + optional explicit core / X-cap-ESR loss (W)
    cmc1_dcr: Optional[float] = None    # ohm  [def DEFAULT_CMC1_DCR]
    cmc2_dcr: Optional[float] = None    # ohm  [def DEFAULT_CMC2_DCR]
    ldm_dcr: Optional[float] = None     # ohm  [def DEFAULT_LDM_DCR]
    core_loss_w: Optional[float] = None      # W  measured/est; else fraction-of-copper estimate
    xcap_esr_loss_w: Optional[float] = None  # W  measured/est; else fraction-of-copper estimate


@dataclass
class DesignContext:
    pfc: PFCResult
    protection: ProtectionResult
    ntc: NTCResult
    emi_in: EMIInputs
    noise: NoiseSpectrum = field(default_factory=NoiseSpectrum)
    dcdc: DCDCResult = field(default_factory=DCDCResult)
    parasitics: FilterParasitics = field(default_factory=FilterParasitics)
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
    # damping (series-R-L) + frequency-domain Middlebrook
    damp_l: float = 0.0            # H, series-R-L damping-branch inductor (≈ L_DM)
    stability_margin_db: float = 0.0   # 20log10(|Zin|/|Zout,peak|) at the DM resonance
    dm_res_hz: float = 0.0         # DM LC resonance frequency
    # delivered insertion loss (ABCD two-port with real parasitics) + worst-case margins
    dm_il_db: float = 0.0          # delivered DM IL at the worst-margin frequency
    dm_margin_db: float = 0.0      # min over band of (DM IL - DM required attenuation)
    dm_margin_f: float = 0.0       # frequency of the worst DM margin
    cm_il_db: float = 0.0
    cm_margin_db: float = 0.0
    cm_margin_f: float = 0.0
    # per-operating-point verification (§2.5/Table 6) + loss budget (§15) + single-fault leakage (§13)
    per_point: List[Dict[str, float]] = field(default_factory=list)  # [{vac,i_in,cu_loss_w,i_cx_a,i_leak_a,worst_mode}]
    loss_rows: List[Tuple[str, float]] = field(default_factory=list)  # [(label, watts)] at the worst point
    loss_total_w: float = 0.0
    loss_worst_vac: float = 0.0
    leak_fault_A: float = 0.0       # single-fault (open-neutral) worst-branch leakage
    # render-ready sampled curves (results object carries plot data; renderer never re-computes)
    spectra: Dict[str, List[float]] = field(default_factory=dict)
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


def _dm_points(ctx):
    """Operating points for the DM source: the shared PFC grid if supplied, else one
    point synthesised from the aggregate PFC fields (worst-case low line)."""
    p = ctx.pfc
    if p.points:
        return p.points
    duty = max(0.0, 1.0 - (sqrt(2.0) * p.vac_min) / p.v_bus)   # peak duty at low line
    i_in = p.p_out / max(p.eff, 1e-3) / max(p.vac_min, 1e-3)
    return [OperatingPoint(v_in=p.vac_min, duty=duty, i_in=i_in,
                           delta_i=None, f_line=p.f_line)]


def _dm_delta_i(ctx, op):
    """Per-phase input-ripple amplitude ΔI at an operating point [A]. Uses the boost
    inductance when available (ΔI = V_in,pk·D/(L·f_sw)); else the aggregate ripple."""
    p = ctx.pfc
    if op.delta_i:
        return op.delta_i
    if p.l_boost:
        return (sqrt(2.0) * op.v_in) * op.duty / (p.l_boost * p.f_sw)
    return p.i_ripple_pp


def dm_noise_dbuv(ctx, f):
    """Differential-mode emission at the LISN [dBuV] (reference §4.2/§4.4).

    Measured spectrum wins. Otherwise COMPUTED per operating point from the PFC
    input-ripple current: a trapezoidal-pulse envelope (flat, then -20, then -40
    dB/dec at f1=1/(πD·T), f2=1/(π·t_r)) with interleaving cancellation, current-
    divided by the bulk capacitor (ESR + jωESL + 1/jωC) against the LISN DM
    impedance — the bulk cap shunts most of the ripple, so DM is usually modest.
    The worst operating point governs."""
    if ctx.noise.dm:
        return _interp_dbuv(ctx.noise.dm, f), "measured"
    p = ctx.pfc
    if not (p.l_boost or p.points):        # not enough data for the computed model
        esr = p.esr_bulk or DEFAULT_BULK_ESR
        f_first = p.n_phases * p.f_sw
        i_h = (4.0 / pi ** 2) * p.i_ripple_pp / max(1.0, round(f / f_first)) ** 2
        return 20.0 * log10(max(i_h * esr, 1e-12) / 1e-6), "estimate"
    esr = p.esr_bulk or DEFAULT_BULK_ESR
    esl = p.bulk_esl or DEFAULT_BULK_ESL
    c_bulk = p.bulk_c                       # may be None -> ESR/ESL-only shunt
    didt = p.didt_pfc or DEFAULT_DIDT_PFC
    z_bulk = _z_cap(f, c_bulk, esr, esl) if c_bulk else complex(esr, TWO_PI * f * esl)
    frac = abs(z_bulk / (z_bulk + Z_LISN_DM))     # ripple fraction reaching the LISN
    T = 1.0 / p.f_sw
    worst = 1e-18
    for op in _dm_points(ctx):
        d = min(max(op.duty, 1e-3), 0.999)
        di = _dm_delta_i(ctx, op)
        i0 = 2.0 * di * d / max(p.n_phases, 1)      # trapezoid flat-region amplitude, interleaved
        f1 = 1.0 / (pi * d * T)
        f2 = 1.0 / (pi * max(di / didt, 1e-12))
        env = i0
        if f > f1:
            env *= f1 / f                            # -20 dB/dec
        if f > f2:
            env *= f2 / f                            # further -20 -> -40 dB/dec
        v = env * frac * Z_LISN_DM
        worst = max(worst, v)
    return 20.0 * log10(max(worst, 1e-12) / 1e-6), "computed"


def _cm_generators(ctx):
    """CM displacement-current generators (C, ΔV, f_rep, dV/dt), one per coupling
    node. Always the PFC switch-node→chassis; plus the DC-DC switch-node and the
    transformer inter-winding when the DC-DC stage is present (else dropped entirely)."""
    p, dc = ctx.pfc, ctx.dcdc
    gens = [(p.c_node_pfc or p.c_para_earth or DEFAULT_C_NODE_PFC,
             p.v_bus, 2.0 * p.f_sw, p.dvdt_pfc or p.dvdt or DEFAULT_DVDT_PFC)]
    if dc and dc.present and dc.f_sw:
        v_node = dc.v_node or p.v_bus
        gens.append((dc.c_node_psfb or DEFAULT_C_NODE_PSFB, v_node,
                     2.0 * dc.f_sw, dc.dvdt_psfb or DEFAULT_DVDT_PSFB))
        gens.append((dc.c_ps or DEFAULT_C_PS, v_node,
                     2.0 * dc.f_sw, dc.dvdt_psfb or DEFAULT_DVDT_PSFB))
    return gens


def cm_noise_dbuv(ctx, f):
    """Common-mode emission at the LISN [dBuV] (reference §4.2, Table 8).

    Measured spectrum wins. Otherwise COMPUTED as the sum of displacement-current
    generators I = C·dV/dt through each coupling node (charge/edge Q=C·ΔV, envelope
    I_flat=2·Q·f_rep flat to f2=1/(π·t_r) then -20 dB/dec), into the LISN CM
    impedance. CM is line-independent because V_bus is regulated."""
    if ctx.noise.cm:
        return _interp_dbuv(ctx.noise.cm, f), "measured"
    i_cm = 0.0
    for c_node, dv, f_rep, dvdt in _cm_generators(ctx):
        q = c_node * dv
        i_flat = 2.0 * q * f_rep
        f2 = 1.0 / (pi * max(dv / dvdt, 1e-12))
        i_cm += i_flat if f <= f2 else i_flat * (f2 / f)
    v = i_cm * Z_LISN_CM
    return 20.0 * log10(max(v, 1e-12) / 1e-6), "computed"


# ============================================================== #
#  DELIVERED INSERTION LOSS  (ABCD two-port, real parasitics)   #
# ============================================================== #

def _resolve_parasitics(par: "FilterParasitics") -> Dict[str, float]:
    """Resolve ABCD parasitics to values, filling named defaults where absent."""
    return {
        "xcap_esr": par.xcap_esr or DEFAULT_XCAP_ESR,
        "xcap_esl": par.xcap_esl or DEFAULT_XCAP_ESL,
        "ycap_esl": par.ycap_esl or DEFAULT_YCAP_ESL,
        "ldm_cp":   par.ldm_cp   or DEFAULT_LDM_CP,
        "lcm_cp":   par.lcm_cp   or DEFAULT_LCM_CP,
        "cmc1_dcr": par.cmc1_dcr or DEFAULT_CMC1_DCR,
        "cmc2_dcr": par.cmc2_dcr or DEFAULT_CMC2_DCR,
        "ldm_dcr":  par.ldm_dcr  or DEFAULT_LDM_DCR,
    }


def insertion_loss_dm(l_dm, c_x, stages, par, f):
    """Delivered DM insertion loss [dB] from the cascaded ABCD model with real
    parasitics (X-cap ESR/ESL, DM-choke self-capacitance). The choke's self-
    capacitance floors the attenuation above its SRF — the physical reason ideal
    slope math over-predicts HF performance. Two-stage splits L and C evenly."""
    n = max(1, int(stages))
    l_i, c_i = l_dm / n, c_x / n
    mats = []
    for _ in range(n):                       # CL section facing the mains (shunt C, series L)
        mats.append(_abcd_shunt(1.0 / _z_cap(f, c_i, par["xcap_esr"], par["xcap_esl"])))
        mats.append(_abcd_series(_z_ind(f, l_i, 0.0, par["ldm_cp"])))
    return _insertion_loss_db(_abcd_cascade(mats), Z_LISN_DM, Z_LISN_DM)


def insertion_loss_cm(l_cm, c_y_total, stages, par, f):
    """Delivered CM insertion loss [dB] from the ABCD model (Y-cap ESL, CM-choke
    self-capacitance that floors HF CM attenuation). c_y_total is the total line-
    frequency Y network seen to earth (both L-PE and N-PE pairs in parallel)."""
    if not l_cm or l_cm == float("inf") or c_y_total <= 0:
        return 0.0
    n = max(1, int(stages))
    l_i, cy_i = l_cm / n, c_y_total / n
    mats = []
    for _ in range(n):
        mats.append(_abcd_shunt(1.0 / _z_cap(f, cy_i, 0.0, par["ycap_esl"])))
        mats.append(_abcd_series(_z_ind(f, l_i, 0.0, par["lcm_cp"])))
    return _insertion_loss_db(_abcd_cascade(mats), Z_LISN_CM, Z_LISN_CM)


def delivered_margin(noise_fn, il_fn, ctx, klass, detector, margin, f_lo):
    """Sweep the conducted band: worst-case margin = min over band of (delivered IL −
    required attenuation). Returns (il_at_worst_f, worst_margin_db, worst_margin_f)."""
    grid = _freq_grid(max(CONDUCTED_FMIN, f_lo), CONDUCTED_FMAX)
    worst_m, worst_mf, il_here = 1e9, grid[0], 0.0
    for f in grid:
        nz, _ = noise_fn(ctx, f)
        a_req = max(nz - (conducted_limit_dbuv(f, klass, detector) - margin), 0.0)
        il = il_fn(f)
        m = il - a_req
        if m < worst_m:
            worst_m, worst_mf, il_here = m, f, il
    return il_here, worst_m, worst_mf


def sample_spectra(ctx, klass, detector, l_dm, c_x, dm_stages, l_cm, cy_system, cm_stages,
                   par, damp_r, damp_l, f_lo, n=140):
    """Sample the render-ready curves ONCE (results object carries them; the report never
    re-computes): unfiltered DM/CM source, the limit line, delivered DM/CM insertion loss,
    and the Middlebrook |Z_out| / |Z_in| pair near the DM resonance."""
    grid = _freq_grid(max(CONDUCTED_FMIN, f_lo), CONDUCTED_FMAX, n)
    f, dm_src, cm_src, lim, dm_il, cm_il = [], [], [], [], [], []
    for fr in grid:
        f.append(fr)
        dm_src.append(dm_noise_dbuv(ctx, fr)[0])
        cm_src.append(cm_noise_dbuv(ctx, fr)[0])
        lim.append(conducted_limit_dbuv(fr, klass, detector))
        dm_il.append(insertion_loss_dm(l_dm, c_x, dm_stages, par, fr))
        cm_il.append(insertion_loss_cm(l_cm, cy_system, cm_stages, par, fr) if l_cm != float("inf") else 0.0)
    p = ctx.pfc
    f_res = 1.0 / (TWO_PI * sqrt(l_dm * c_x))
    mf, zo, zi = [], [], []
    for fr in _freq_grid(0.05 * f_res, 20.0 * f_res, 90):
        w = TWO_PI * fr
        z_ldm = complex(0.0, w * l_dm)
        z_br = complex(damp_r, w * damp_l)
        z_series = (z_ldm * z_br) / (z_ldm + z_br)
        z_cx = _z_cap(fr, c_x, par["xcap_esr"], par["xcap_esl"])
        z_shunt = (z_cx * Z_LISN_DM) / (z_cx + Z_LISN_DM)
        mf.append(fr); zo.append(abs(z_series + z_shunt))
        zi.append(w * (p.l_boost / max(p.n_phases, 1)) if p.l_boost else 1e9)
    return {"f": f, "dm_src": dm_src, "cm_src": cm_src, "limit": lim, "dm_il": dm_il, "cm_il": cm_il,
            "mbk_f": mf, "mbk_zout": zo, "mbk_zin": zi}


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


def binding_corner(ctx, noise_fn, klass, detector, margin, order, f_lo):
    """The BINDING corner for an `order`-pole filter: the minimum f_c over the band
    of the per-frequency corner f/10^(A_req(f)/(20·order)). Using the minimum (not the
    corner at the single worst-attenuation point) guarantees the roll-off clears the
    requirement at EVERY frequency — important now that the computed source can peak in
    the mid/high band (bulk-cap ESL), not only at 150 kHz."""
    grid = _freq_grid(max(CONDUCTED_FMIN, f_lo), CONDUCTED_FMAX)
    fc_min = 1e18
    for f in grid:
        nz, _ = noise_fn(ctx, f)
        att = nz - (conducted_limit_dbuv(f, klass, detector) - margin)
        if att > 0:
            fc_min = min(fc_min, f / (10 ** (att / (20.0 * order))))
    return fc_min if fc_min < 1e18 else CONDUCTED_FMAX


def choose_stages_and_corner(ctx, noise_fn, klass, detector, margin, f_floor, f_lo):
    """Single LC (order 2) if its binding corner is practical (>= f_floor), else two
    LC stages (order 4). Returns (stages, binding_corner_hz)."""
    fc1 = binding_corner(ctx, noise_fn, klass, detector, margin, 2, f_lo)
    if fc1 >= f_floor:
        return 1, fc1
    return 2, binding_corner(ctx, noise_fn, klass, detector, margin, 4, f_lo)


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
    _order = {"estimate": 0, "computed": 1, "measured": 2}      # weakest source governs
    noise_source = dm_src if _order.get(dm_src, 0) <= _order.get(cm_src, 0) else cm_src
    if noise_source == "estimate":
        warn.append("Noise is a first-order ESTIMATE (insufficient source-model inputs "
                    "— provide L_boost / bulk-cap / parasitics); confirm with a bare-EUT LISN sweep.")
    elif noise_source == "computed":
        warn.append("Noise is COMPUTED from the converter specs/parasitics (calculated baseline, "
                    "App-B) — confirm with a bare-EUT LISN sweep before compliance sign-off.")
    if not p.esr_bulk and not ctx.noise.dm:
        warn.append(f"bulk-cap ESR defaulted ({DEFAULT_BULK_ESR*1e3:.0f} mΩ) — assumed.")
    if not p.bulk_esl and not ctx.noise.dm:
        warn.append(f"bulk-cap ESL defaulted ({DEFAULT_BULK_ESL*1e9:.0f} nH) — assumed (DM shunt sensitive).")
    if not (p.c_node_pfc or p.c_para_earth) and not ctx.noise.cm:
        warn.append(f"PFC node→chassis C defaulted ({DEFAULT_C_NODE_PFC*1e12:.0f} pF) — assumed (CM sensitive; measure).")
    if ctx.dcdc and ctx.dcdc.present and not ctx.dcdc.c_ps and not ctx.noise.cm:
        warn.append(f"transformer C_ps defaulted ({DEFAULT_C_PS*1e12:.0f} pF) — assumed (CM sensitive; measure).")
    prov["dm_req_att"] = f"DM noise({dm_src}) - (ClassB/A limit - {margin}dB) @ {dm_f/1e3:.0f}kHz"
    prov["cm_req_att"] = f"CM noise({cm_src}) - (limit - {margin}dB) @ {cm_f/1e3:.0f}kHz"

    # ---- resolve ABCD parasitics (delivered-margin-driven sizing + damping need them) ----
    par = _resolve_parasitics(ctx.parasitics)

    # ---- CM: leakage budget fixes C_Y; size L_CM at the binding corner and ESCALATE 1->2
    #      stages if the DELIVERED (ABCD, real-parasitic) margin is short (2 = reference max) ----
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
        cy_emi = 0.0; l_cm = float("inf"); cm_stages = 1; cm_fc = 0.0
        cm_il_db = cm_margin_db = cm_margin_f = 0.0
    else:
        cy_emi = cy_remaining
        cy_system = prot.committed_y_cap_total + cy_emi

        def _size_cm(stages):
            fc = binding_corner(ctx, cm_noise_dbuv, klass, detector, margin, 2 * stages, f_first)
            # n cascaded LC sections: L_total = n^2 / ((2*pi*fc)^2 * 2*C_Y)
            l = (stages ** 2) / ((TWO_PI * fc) ** 2 * (2.0 * cy_emi))
            il, m, mf = delivered_margin(
                cm_noise_dbuv, lambda f: insertion_loss_cm(l, cy_system, stages, par, f),
                ctx, klass, detector, margin, f_first)
            return fc, l, il, m, mf

        cm_stages = 1
        cm_fc, l_cm, cm_il_db, cm_margin_db, cm_margin_f = _size_cm(1)
        if cm_margin_db < 0:                        # 1 stage short with real parasitics -> 2 stages
            cm_stages = 2
            cm_fc, l_cm, cm_il_db, cm_margin_db, cm_margin_f = _size_cm(2)
        prov["l_cm"] = f"L_CM {l_cm*1e3:.2f} mH, {cm_stages} stage(s), binding corner {cm_fc/1e3:.1f} kHz"

    cy_system = prot.committed_y_cap_total + cy_emi

    # ---- DM: C_X at the practical max; size L_DM at the binding corner and ESCALATE if short ----
    c_x = ein.cx_max

    def _size_dm(stages):
        fc = binding_corner(ctx, dm_noise_dbuv, klass, detector, margin, 2 * stages, f_first)
        l = (stages ** 2) / ((TWO_PI * fc) ** 2 * c_x)
        il, m, mf = delivered_margin(
            dm_noise_dbuv, lambda f: insertion_loss_dm(l, c_x, stages, par, f),
            ctx, klass, detector, margin, f_first)
        return fc, l, il, m, mf

    dm_stages = 1
    dm_fc, l_dm, dm_il_db, dm_margin_db, dm_margin_f = _size_dm(1)
    if dm_margin_db < 0:
        dm_stages = 2
        dm_fc, l_dm, dm_il_db, dm_margin_db, dm_margin_f = _size_dm(2)
    prov["dm_corner"] = f"{dm_stages} LC stage(s), {20*2*dm_stages} dB/dec; binding corner {dm_fc/1e3:.1f} kHz"
    prov["l_dm"] = f"L_DM {l_dm*1e6:.1f} uH total, {dm_stages} stage(s), C_X {c_x*1e6:.2f} uF"
    if (l_dm / max(dm_stages, 1)) > ein.ldm_sat_max:
        warn.append(f"per-stage DM inductance {l_dm/dm_stages*1e6:.0f} uH exceeds the "
                    f"saturation-practical {ein.ldm_sat_max*1e6:.0f} uH; split further or raise C_X.")

    # ---- damping (series R-L) + frequency-domain Middlebrook stability ----
    # Reference §10/§11: a series R_d-L_d branch across the DM choke (L_d ≈ L_DM) damps the
    # LC resonance WITHOUT the large blocking cap / reactive current of the parallel-R-C method.
    # R_d is grid-searched to minimise the computed filter output-impedance peak (target Q ≤ 1).
    z0_dm = sqrt(l_dm / c_x)                          # DM characteristic impedance
    damp_l = l_dm                                     # series-R-L inductor ≈ L_DM (n ≈ 1)
    f_res_dm = 1.0 / (TWO_PI * sqrt(l_dm * c_x))      # DM LC resonance

    def _zout_dm_peak(r_d):
        """Max |Z_out| of the damped DM filter near resonance (converter looks back into
        L_DM ∥ (R_d+jωL_d), then C_X ∥ LISN)."""
        peak = 0.0
        for f in _freq_grid(0.3 * f_res_dm, 3.0 * f_res_dm, 60):
            w = TWO_PI * f
            z_ldm = complex(0.0, w * l_dm)
            z_branch = complex(r_d, w * damp_l)
            z_series = (z_ldm * z_branch) / (z_ldm + z_branch)     # damping branch ∥ L_DM
            z_cx = _z_cap(f, c_x, par["xcap_esr"], par["xcap_esl"])
            z_shunt = (z_cx * Z_LISN_DM) / (z_cx + Z_LISN_DM)
            peak = max(peak, abs(z_series + z_shunt))
        return peak

    damp_r, zout_peak = z0_dm, 1e18
    for _k in (0.2, 0.3, 0.4, 0.5, 0.7, 1.0, 1.5, 2.0, 3.0):     # sweep R_d = k·Z0
        pk = _zout_dm_peak(z0_dm * _k)
        if pk < zout_peak:
            zout_peak, damp_r = pk, z0_dm * _k
    damp_c = 0.0                                      # series-R-L method: no blocking cap
    # Converter input impedance: negative resistance R_n = V_in²/P_in appears only below the
    # PFC voltage-loop bandwidth (tens of Hz); around the DM resonance |Z_in| is set by the boost
    # inductor (ω·L_boost/n_phases). Middlebrook: 20log10(|Z_in|/|Z_out,peak|) ≥ margin.
    rin_conv = (p.vac_min ** 2) / (p.p_out / max(p.eff, 1e-3))    # |neg input R| (LF)
    zin_res = (TWO_PI * f_res_dm * (p.l_boost / max(p.n_phases, 1))) if p.l_boost else rin_conv
    stability_margin_db = 20.0 * log10(max(zin_res, 1e-9) / max(zout_peak, 1e-9))
    stability_ok = stability_margin_db >= margin
    prov["damping"] = (f"series-R-L across L_DM: R_d={damp_r:.2f} ohm, L_d={damp_l*1e6:.1f} uH "
                       f"(grid-searched to min |Z_out| peak {zout_peak:.2f} ohm; Z0={z0_dm:.2f} ohm)")
    prov["stability"] = (f"Middlebrook @ f_res {f_res_dm/1e3:.1f} kHz: |Z_in| {zin_res:.2f} ohm / "
                         f"|Z_out| {zout_peak:.2f} ohm = {stability_margin_db:.1f} dB (need {margin:.0f})")
    if not stability_ok:
        warn.append(f"Middlebrook margin {stability_margin_db:.1f} dB < {margin:.0f} dB target at the DM "
                    f"resonance ({f_res_dm/1e3:.1f} kHz); lower R_d or raise C_X.")

    # ---- leakage check (system, normal + single-fault open-neutral) ----
    leak_actual = TWO_PI * p.f_line * v_ln * cy_system
    if leak_actual > leak_limit:
        fb.append(f"Leakage {leak_actual*1e3:.2f}mA exceeds {ein.safety_standard} "
                  f"limit {leak_limit*1e3:.2f}mA.")
    # Single fault (open neutral): the line-PE Y-caps see the full line; worst branch ≈ half the
    # network at full line voltage (§13). Reported and checked against the same limit.
    leak_fault_A = TWO_PI * p.f_line * v_ln * (cy_system / 2.0)
    if leak_fault_A > leak_limit:
        warn.append(f"Single-fault (open-neutral) leakage {leak_fault_A*1e3:.2f} mA exceeds the "
                    f"{leak_limit*1e3:.2f} mA limit.")

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

    # ---- per-operating-point verification (§2.5/Table 6) + loss budget (§15) ----
    # Choke copper loss = I_in²·ΣDCR (one CM-choke DCR per CM stage + one DM-choke DCR per DM stage).
    cm_dcrs = [par["cmc1_dcr"], par["cmc2_dcr"]][:max(cm_stages, 1)]
    ldm_dcr_total = dm_stages * par["ldm_dcr"]
    total_dcr = sum(cm_dcrs) + ldm_dcr_total
    per_point = []
    for op in _dm_points(ctx):
        cu = op.i_in ** 2 * total_dcr
        per_point.append({
            "vac": op.v_in, "i_in": op.i_in, "cu_loss_w": cu,
            "i_cx_a": TWO_PI * op.f_line * op.v_in * c_x,          # X-cap reactive current
            "i_leak_a": TWO_PI * op.f_line * op.v_in * cy_system,  # Y-cap earth leakage
            "worst_mode": "DM" if op.v_in < 180 else "CM",
        })
    # Loss breakdown at the worst (highest-current) operating point.
    worst = max(per_point, key=lambda d: d["cu_loss_w"]) if per_point else \
        {"vac": p.vac_min, "i_in": 0.0, "cu_loss_w": 0.0}
    i_w = worst["i_in"]
    loss_rows = [(f"CMC{i+1} copper", i_w ** 2 * dcr) for i, dcr in enumerate(cm_dcrs)]
    loss_rows.append(("L_DM copper", i_w ** 2 * ldm_dcr_total))
    cu_total = sum(w for _, w in loss_rows)
    core_w = ctx.parasitics.core_loss_w if ctx.parasitics.core_loss_w is not None \
        else DEFAULT_CORE_LOSS_FRAC * cu_total
    esr_w = ctx.parasitics.xcap_esr_loss_w if ctx.parasitics.xcap_esr_loss_w is not None \
        else DEFAULT_XCAP_ESR_LOSS_FRAC * cu_total
    loss_rows.append(("Core (est.)", core_w))
    loss_rows.append(("X-cap ESR (est.)", esr_w))
    if ein.bleeder_r:
        loss_rows.append(("Bleeder", (v_ln ** 2) / ein.bleeder_r))
    loss_total_w = sum(w for _, w in loss_rows)
    loss_worst_vac = worst["vac"]
    prov["loss"] = (f"copper {cu_total:.2f} W (ΣDCR {total_dcr*1e3:.0f} mΩ × I²) worst @ "
                    f"{loss_worst_vac:.0f} V; core/ESR estimated as {DEFAULT_CORE_LOSS_FRAC*100:.0f}%/"
                    f"{DEFAULT_XCAP_ESR_LOSS_FRAC*100:.1f}% of copper; total {loss_total_w:.2f} W")
    prov["leakage"] = (f"normal {leak_actual*1e3:.2f} mA, single-fault {leak_fault_A*1e3:.2f} mA "
                       f"(limit {leak_limit*1e3:.2f} mA) at {v_ln:.0f} V / {p.f_line:.0f} Hz")

    # ---- delivered insertion loss (ABCD two-port) — margins computed during sizing above ----
    prov["il_model"] = ("ABCD two-port with parasitics "
                        f"(X-cap ESR {par['xcap_esr']*1e3:.0f}mΩ/ESL {par['xcap_esl']*1e9:.0f}nH, "
                        f"DM-choke Cp {par['ldm_cp']*1e12:.0f}pF, Y-cap ESL {par['ycap_esl']*1e9:.0f}nH, "
                        f"CM-choke Cp {par['lcm_cp']*1e12:.0f}pF)")
    # After escalation, a residual shortfall means the requirement is not reachable with practical
    # parts — surface a SOURCE-REDUCTION target (achievability gate seed, App B.3) rather than an
    # impossible filter.
    if dm_margin_db < 0:
        warn.append(f"DM delivered IL still falls {abs(dm_margin_db):.1f} dB SHORT near "
                    f"{dm_margin_f/1e3:.0f} kHz at {dm_stages} stage(s) — raise C_X / add a DM stage, "
                    f"or reduce the input-ripple source.")
    if cm_margin_db < 0 and l_cm != float("inf"):
        warn.append(f"CM delivered IL still falls {abs(cm_margin_db):.1f} dB SHORT near "
                    f"{cm_margin_f/1e3:.0f} kHz at {cm_stages} stage(s) — HF CM is floored by choke self-"
                    f"resonance/parasitics; REDUCE THE CM SOURCE (C_ps, node capacitance, dV/dt) rather "
                    f"than adding Y-capacitance/stages.")

    spectra = sample_spectra(ctx, klass, detector, l_dm, c_x, dm_stages, l_cm, cy_system,
                             cm_stages, par, damp_r, damp_l, f_first)

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
        damp_l=damp_l, stability_margin_db=stability_margin_db, dm_res_hz=f_res_dm,
        dm_il_db=dm_il_db, dm_margin_db=dm_margin_db, dm_margin_f=dm_margin_f,
        cm_il_db=cm_il_db, cm_margin_db=cm_margin_db, cm_margin_f=cm_margin_f,
        per_point=per_point, loss_rows=loss_rows, loss_total_w=loss_total_w,
        loss_worst_vac=loss_worst_vac, leak_fault_A=leak_fault_A, spectra=spectra,
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
    o(f"    Damping (ser R-L): R_d {r.damp_r:6.2f} ohm + L_d {r.damp_l*1e6:.1f} uH "
      f"(across L_DM; no blocking cap)")

    o("\n[DELIVERED INSERTION LOSS -- ABCD model]")
    o(f"    DM : {r.dm_il_db:5.1f} dB, worst margin {r.dm_margin_db:+.1f} dB @ {r.dm_margin_f/1e3:.0f} kHz")
    o(f"    CM : {r.cm_il_db:5.1f} dB, worst margin {r.cm_margin_db:+.1f} dB @ {r.cm_margin_f/1e3:.0f} kHz")

    o("\n[CHECKS]")
    o(f"    Earth leakage    : {r.leakage_actual_A*1e3:.3f} mA normal / {r.leak_fault_A*1e3:.3f} mA "
      f"single-fault (limit {r.leakage_limit_A*1e3:.2f} mA) "
      f"-> {'OK' if max(r.leakage_actual_A, r.leak_fault_A) <= r.leakage_limit_A else 'OVER'}")
    o(f"    Stability (MBK)  : {r.stability_margin_db:+.1f} dB @ f_res {r.dm_res_hz/1e3:.1f} kHz "
      f"(|Zout| {r.stability_z0_dm:.2f} ohm Z0) -> {'OK' if r.stability_ok else 'CHECK'}")
    if r.xcap_discharge_s is not None:
        o(f"    X-cap discharge  : {r.xcap_discharge_s:.2f} s")

    if r.loss_rows:
        o(f"\n[LOSS BUDGET -- worst case @ {r.loss_worst_vac:.0f} V]")
        for lbl, w in r.loss_rows:
            o(f"    {lbl:18}: {w:6.2f} W")
        o(f"    {'TOTAL':18}: {r.loss_total_w:6.2f} W")

    if r.per_point:
        o("\n[PER-OPERATING-POINT SWEEP]")
        o(f"    {'V_ac':>6} {'I_in(A)':>8} {'Cu loss(W)':>11} {'I_Cx(mA)':>9} {'I_leak(uA)':>11} {'mode':>5}")
        for d in r.per_point:
            o(f"    {d['vac']:6.0f} {d['i_in']:8.2f} {d['cu_loss_w']:11.2f} "
              f"{d['i_cx_a']*1e3:9.0f} {d['i_leak_a']*1e6:11.0f} {d['worst_mode']:>5}")

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
            esr_bulk=0.03, dvdt=20e9, c_para_earth=100e-12, sw_rise_time=20e-9,
            # computed-source-model inputs (exercise the Phase-1 model)
            l_boost=250e-6, bulk_c=680e-6, bulk_esl=20e-9,
            c_node_pfc=47e-12, dvdt_pfc=10e9, didt_pfc=500e9),
        protection=ProtectionResult(committed_y_cap_total=2 * 22e-12),  # GDT-side Y
        ntc=NTCResult(r_ntc_cold=6.8),
        emi_in=EMIInputs(safety_standard="IEC_62368_1", compliance_profile=5,
                         margin_db=6.0, bleeder_r=1e6),
    )


def _reference_context() -> DesignContext:
    """The document's worked example (PFC + PSFB DC-DC), used to validate the computed
    source model against Appendix A / Table 8 (CM ~116 dBuV, DM ~83 dBuV at 150 kHz)."""
    return DesignContext(
        pfc=PFCResult(
            vac_min=90, vac_max=264, f_line=60, v_bus=400, p_out=2000,
            eff=0.94, f_sw=70e3, n_phases=2, i_ripple_pp=5.0,
            esr_bulk=5e-3, l_boost=250e-6, bulk_c=680e-6, bulk_esl=20e-9,
            c_node_pfc=47e-12, dvdt_pfc=10e9, didt_pfc=500e9,
            # reference Table 3/4 nine-point grid (V_in, duty, I_in, ΔI)
            points=[OperatingPoint(v, d, i, di, 60 if v <= 132 else 50) for v, d, i, di in [
                (90, 0.68, 23.88, 5.0), (110, 0.61, 19.54, 5.4), (120, 0.58, 17.91, 5.6),
                (132, 0.53, 16.28, 5.7), (180, 0.36, 21.49, 5.3), (200, 0.29, 19.34, 4.7),
                (220, 0.22, 17.58, 4.0), (230, 0.19, 16.82, 3.5), (264, 0.07, 14.65, 1.4)]]),
        protection=ProtectionResult(),
        ntc=NTCResult(),
        emi_in=EMIInputs(safety_standard="IEC_62368_1", compliance_profile=5, margin_db=6.0),
        dcdc=DCDCResult(present=True, f_sw=250e3, topology="psfb", v_node=400,
                        dvdt_psfb=15e9, c_node_psfb=33e-12, c_ps=15e-12),
    )


# ============================================================== #
#  SELF-TEST  (proves the input steering)                       #
# ============================================================== #

def self_test():
    print("Running self-test (EMI synthesis steering)...")

    # 1) Class B demands >= attenuation than Class A (stricter limit). (Corner comparison is no
    #    longer a clean invariant once the synthesiser escalates stages, so compare required att.)
    cb = demo_context(); cb.emi_in.compliance_profile = 5   # Class B
    ca = demo_context(); ca.emi_in.compliance_profile = 4   # Class A
    rb, ra = design_emi_filter(cb), design_emi_filter(ca)
    assert rb.dm_req_att_db >= ra.dm_req_att_db - 1e-6, "Class B should need >= DM attenuation"
    assert rb.cm_req_att_db >= ra.cm_req_att_db - 1e-6, "Class B should need >= CM attenuation"
    print(f"  [ok] Class B needs >= Class A attenuation (DM {rb.dm_req_att_db:.1f} "
          f">= {ra.dm_req_att_db:.1f} dB)")

    # 2) +margin raises the required attenuation.
    c0 = demo_context(); c0.emi_in.margin_db = 0
    c6 = demo_context(); c6.emi_in.margin_db = 6
    r0, r6 = design_emi_filter(c0), design_emi_filter(c6)
    assert r6.cm_req_att_db >= r0.cm_req_att_db - 1e-6, "more margin -> more required attenuation"
    print(f"  [ok] +6dB margin raises CM required att "
          f"({r6.cm_req_att_db:.1f} >= {r0.cm_req_att_db:.1f} dB)")

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

    # 9) Computed source model matches the reference worked example (Table 8 / App A).
    rc = _reference_context()
    cm150, cm_src = cm_noise_dbuv(rc, 150e3)
    dm150, dm_src = dm_noise_dbuv(rc, 150e3)
    assert cm_src == "computed" and dm_src == "computed", "reference ctx should compute the source"
    assert abs(cm150 - 116.0) < 3.0, f"CM source {cm150:.1f} dBuV (ref ~116)"
    assert abs(dm150 - 83.0) < 4.0, f"DM source {dm150:.1f} dBuV (ref ~83)"
    print(f"  [ok] computed source vs reference: CM {cm150:.1f} dBuV (~116), DM {dm150:.1f} dBuV (~83)")

    # 10) DM << CM (bulk cap shunts the ripple), and CM is line-independent (V_bus regulated).
    assert dm150 < cm150 - 20, "DM should be far below CM (bulk-cap shunt)"
    cm_hi = cm_noise_dbuv(_reference_context(), 1e6)[0]
    assert abs(cm_hi - cm150) < 6, "CM roughly flat 150k-1M (line-independent)"
    print(f"  [ok] DM << CM by {cm150-dm150:.0f} dB; CM flat ({cm150:.0f}->{cm_hi:.0f} dBuV 150k->1M)")

    # 11) ABCD insertion loss: real DM-choke self-capacitance floors HF attenuation
    #     (a real filter cannot keep gaining IL forever — the ideal-slope model would).
    par = _resolve_parasitics(FilterParasitics())
    il_lo = insertion_loss_dm(47e-6, 4.7e-6, 1, par, 150e3)
    il_srf = insertion_loss_dm(47e-6, 4.7e-6, 1, par, 20e6)   # above choke SRF
    assert il_lo > 40, f"DM IL at 150 kHz should be substantial ({il_lo:.1f} dB)"
    assert il_srf < il_lo, "HF IL must roll off past the choke self-resonance (parasitic floor)"
    print(f"  [ok] ABCD IL shows HF floor: DM IL {il_lo:.0f} dB @150k -> {il_srf:.0f} dB @20M")

    # 12) DC-DC present adds CM (transformer/switch-node); PFC-only drops those terms.
    pfc_only = _reference_context(); pfc_only.dcdc = DCDCResult(present=False)
    cm_pfc_only = cm_noise_dbuv(pfc_only, 150e3)[0]
    assert cm_pfc_only < cm150 - 3, "PFC-only CM must be lower (DC-DC terms dropped, no hidden add)"
    print(f"  [ok] DC-DC toggle: CM {cm150:.0f} dBuV (with) -> {cm_pfc_only:.0f} dBuV (PFC-only)")

    # 13) Delivered-margin-driven synthesis: escalates to 2 stages when 1 is short with real
    #     parasitics, and a residual CM shortfall emits a source-reduction target (App B.3).
    rr = design_emi_filter(_reference_context())
    assert rr.dm_stages >= 1 and rr.cm_stages >= 1
    assert rr.dm_margin_db > -1.0, f"DM should meet (or nearly) after escalation ({rr.dm_margin_db:.1f} dB)"
    assert any("REDUCE THE CM SOURCE" in w for w in rr.warnings) or rr.cm_margin_db >= 0, \
        "short CM must emit a source-reduction target"
    print(f"  [ok] escalation: DM {rr.dm_stages}-stage margin {rr.dm_margin_db:+.1f} dB; "
          f"CM {rr.cm_stages}-stage margin {rr.cm_margin_db:+.1f} dB (source-reduction if short)")

    # 14) Per-point loss + leakage sweep (§2.5/§15/§13): 9 points, copper worst at low line,
    #     total = copper + core + ESR (+bleeder), leakage rises with line voltage.
    assert len(rr.per_point) == 9, f"expected 9 operating points ({len(rr.per_point)})"
    cu = [d["cu_loss_w"] for d in rr.per_point]
    assert cu[0] == max(cu), "copper loss worst at the low-line (highest-current) point"
    assert rr.loss_total_w > sum(w for lbl, w in rr.loss_rows if "copper" in lbl), \
        "total loss includes core/ESR/bleeder on top of copper"
    assert rr.per_point[-1]["i_leak_a"] > rr.per_point[0]["i_leak_a"], "leakage rises with line voltage"
    assert rr.leak_fault_A < rr.leakage_actual_A, "single-fault leakage below the normal (summed) value"
    print(f"  [ok] loss/leakage sweep: 9 pts, total {rr.loss_total_w:.1f} W worst @ "
          f"{rr.loss_worst_vac:.0f} V; leak {rr.leakage_actual_A*1e3:.2f} mA / fault "
          f"{rr.leak_fault_A*1e3:.2f} mA")

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
