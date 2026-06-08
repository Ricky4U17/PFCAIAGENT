"""
app/mode_b/magnetic_design.py
Step 6: Magnetic Design — core selection, turns, gap, Litz wire, loss budget.
Pure Python, no external API required.
"""
from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import Optional


MU0 = 4 * math.pi * 1e-7   # H/m
RHO_CU_20 = 1.72e-8         # Ω·m  at 20 °C
RHO_CU_100 = 2.10e-8        # Ω·m  at 100 °C (used for losses)


@dataclass
class CoreSpec:
    name: str
    Ae: float        # m²
    Le: float        # m
    Ve: float        # m³
    mu_r: float      # relative permeability (use 60 for powder, ~2500 for ferrite)
    Bsat: float      # T at 100 °C
    # Steinmetz: Pv = Pv_ref * (f/f_ref)^alpha * (dB/dB_ref)^beta
    Pv_ref: float    # W/m³
    f_ref: float     # Hz
    dB_ref: float    # T (half-swing)
    alpha: float
    beta: float
    Wa: float        # m² window area (both halves)
    MLT: float       # m  mean length per turn
    # Physical
    OD: float = 0.0  # m  outer dim (for thermal)
    Ht: float = 0.0  # m  height


CORE_LIBRARY = [
    CoreSpec("ETD49/3C95 (Ferroxcube)",
             Ae=211e-6, Le=0.114, Ve=24e-6, mu_r=2500, Bsat=0.43,
             Pv_ref=130e3, f_ref=100e3, dB_ref=0.10, alpha=1.25, beta=2.50,
             Wa=178e-6, MLT=0.100, OD=0.049, Ht=0.025),
    CoreSpec("ETD59/3C95 (Ferroxcube)",
             Ae=368e-6, Le=0.139, Ve=51e-6, mu_r=2500, Bsat=0.43,
             Pv_ref=80e3,  f_ref=100e3, dB_ref=0.10, alpha=1.25, beta=2.50,
             Wa=280e-6, MLT=0.120, OD=0.059, Ht=0.040),
    CoreSpec("E65/32/27 N87 (TDK)",
             Ae=265e-6, Le=0.147, Ve=40e-6, mu_r=2200, Bsat=0.41,
             Pv_ref=90e3,  f_ref=100e3, dB_ref=0.10, alpha=1.20, beta=2.70,
             Wa=242e-6, MLT=0.110, OD=0.065, Ht=0.035),
    CoreSpec("Kool Mµ 77907 (Magnetics Inc.)",
             Ae=267e-6, Le=0.184, Ve=89e-6, mu_r=60,   Bsat=1.00,
             Pv_ref=50e3,  f_ref=100e3, dB_ref=0.05,  alpha=1.32, beta=2.08,
             Wa=400e-6, MLT=0.111, OD=0.078, Ht=0.025),
]


@dataclass
class DesignResult:
    core: CoreSpec
    N: int               # turns
    lg_mm: float         # total air gap (mm); 0 for powder
    Bpk: float           # T
    dBpp: float          # T pk-pk
    n_strands: int
    d_strand_mm: float   # mm
    Ku: float            # window fill
    A_wire_mm2: float    # mm²
    J: float             # A/mm²
    Rdc_mOhm: float      # mΩ at 100°C
    P_core: float        # W
    P_cu: float          # W
    P_total: float       # W
    dT_rise: float       # °C  (forced air estimate)
    passed: bool
    fail_reasons: list[str] = field(default_factory=list)


def design_inductor(
    L: float,            # H
    IL_pk: float,        # A
    IL_rms: float,       # A
    dIL: float,          # A pk-pk
    fsw: float,          # Hz
    T_budget: float = 60.0,   # °C thermal headroom
    J_target: float = 5.0,    # A/mm² winding current density
    Bpk_target: float = 0.28, # T target peak flux (gapped ferrite)
) -> tuple[Optional[DesignResult], list[DesignResult]]:
    """Evaluate all cores; return (best, all_results)."""

    # Skin depth → max strand diameter
    delta = math.sqrt(RHO_CU_20 / (math.pi * fsw * MU0))   # m
    d_strand_m = min(2 * delta, 0.25e-3)                    # cap at 0.25 mm commercial

    results: list[DesignResult] = []

    for core in CORE_LIBRARY:
        is_powder = core.mu_r < 200

        # ── Turns ──────────────────────────────────────────────────────────
        if is_powder:
            N = math.ceil(math.sqrt(L * core.Le / (MU0 * core.mu_r * core.Ae)))
        else:
            N = math.ceil(L * IL_pk / (Bpk_target * core.Ae))

        # ── Gap ────────────────────────────────────────────────────────────
        lg = 0.0 if is_powder else MU0 * N**2 * core.Ae / L
        lg_mm = lg * 1e3

        # ── Flux density ───────────────────────────────────────────────────
        if is_powder:
            Bpk  = MU0 * core.mu_r * N * IL_pk    / core.Le
            dBpk = MU0 * core.mu_r * N * (dIL/2)  / core.Le
        else:
            denom = lg + core.Le / core.mu_r
            Bpk   = MU0 * N * IL_pk    / denom
            dBpk  = MU0 * N * (dIL/2)  / denom
        dBpp = 2 * dBpk

        # ── Core loss (Steinmetz) ──────────────────────────────────────────
        Pv = core.Pv_ref * (fsw / core.f_ref)**core.alpha * (dBpp/2 / core.dB_ref)**core.beta
        P_core = Pv * core.Ve

        # ── Winding ────────────────────────────────────────────────────────
        A_strand = math.pi / 4 * d_strand_m**2         # m²
        A_need   = IL_rms / J_target * 1e-6             # m²
        n_str    = math.ceil(A_need / A_strand)
        A_wire   = n_str * A_strand                      # m²

        d_bundle = d_strand_m * 1.05 * math.sqrt(n_str) * 1.20   # m
        A_bundle = math.pi / 4 * d_bundle**2                      # m²
        Ku       = N * A_bundle / core.Wa

        # Copper resistance at 100 °C
        Rdc   = RHO_CU_100 * N * core.MLT / A_wire                # Ω
        P_cu  = IL_rms**2 * Rdc

        P_tot = P_core + P_cu

        # ── Thermal (forced air, h ≈ 17.5 W/m²K) ─────────────────────────
        if is_powder:
            # Toroid outer surface
            A_surf = (math.pi/4 * core.OD**2) * 2 + math.pi * core.OD * core.Ht
        else:
            A_surf = 2 * core.Ae * 2 + core.Le * math.sqrt(4 * core.Ae) * 1.5
        dT = P_tot / max(1e-6, 17.5 * A_surf)

        # ── Pass/fail ──────────────────────────────────────────────────────
        fails: list[str] = []
        if Ku   > 0.50:               fails.append(f"Ku={Ku:.2f} > 0.50 (window overflow)")
        if Bpk  > core.Bsat * 0.90:   fails.append(f"Bpk={Bpk:.3f}T > 0.9×Bsat")
        if dT   > T_budget:           fails.append(f"ΔT={dT:.0f}°C > {T_budget:.0f}°C budget")

        r = DesignResult(
            core=core, N=N, lg_mm=lg_mm, Bpk=Bpk, dBpp=dBpp,
            n_strands=n_str, d_strand_mm=d_strand_m*1e3,
            Ku=Ku, A_wire_mm2=A_wire*1e6,
            J=IL_rms / (A_wire * 1e6), Rdc_mOhm=Rdc*1e3,
            P_core=P_core, P_cu=P_cu, P_total=P_tot,
            dT_rise=dT, passed=len(fails)==0, fail_reasons=fails,
        )
        results.append(r)

    passed = [r for r in results if r.passed]
    best   = min(passed, key=lambda r: r.P_total) if passed else None
    return best, results


def design_to_dict(r: DesignResult) -> dict:
    """Serialise a DesignResult to a plain dict (JSON-safe)."""
    return {
        "core_name":      r.core.name,
        "N_turns":        r.N,
        "air_gap_mm":     round(r.lg_mm, 3),
        "Bpk_T":          round(r.Bpk, 4),
        "dBpp_mT":        round(r.dBpp * 1e3, 1),
        "litz_strands":   r.n_strands,
        "strand_dia_mm":  round(r.d_strand_mm, 3),
        "Ku":             round(r.Ku, 3),
        "wire_area_mm2":  round(r.A_wire_mm2, 3),
        "J_A_mm2":        round(r.J, 2),
        "Rdc_mOhm":       round(r.Rdc_mOhm, 2),
        "P_core_W":       round(r.P_core, 3),
        "P_cu_W":         round(r.P_cu, 3),
        "P_total_W":      round(r.P_total, 3),
        "dT_rise_C":      round(r.dT_rise, 1),
        "passed":         r.passed,
        "fail_reasons":   r.fail_reasons,
    }
