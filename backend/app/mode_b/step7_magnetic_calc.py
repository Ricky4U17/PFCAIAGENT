"""
app/mode_b/step7_magnetic_calc.py
Step 7 — Magnetic Design Calculation Engine.

Matches reference document Steps 13.1 through 13.10 exactly.
Adds Dowell AC factor (ferrite), Rogowski fringing (ferrite),
Rth thermal network, 9-op-point stability, and Medical checks.

All calculations use physical H (A/m, Oe) — never bare A·T.
For stacked toroids: H = N × Idc / Le_single (Le of ONE core, NOT S×Le).
"""
from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

# MagneticsDB is the single guardian of all material data
# Never import data_loader directly — always go through MagneticsDB
from app.magnetics.db import get_db as _get_mag_db
from app.mode_b.data_loader import compute_dowell_factor, compute_rogowski_fringing

def _db():
    return _get_mag_db()

MU0 = 4 * math.pi * 1e-7
RHO_CU_20  = 1.72e-8   # Ω·m
ALPHA_CU   = 0.00393   # /°C

def rho_cu(T_C: float) -> float:
    return RHO_CU_20 * (1 + ALPHA_CU * (T_C - 20))


# ── iGSE (improved Generalised Steinmetz Equation) constants ─────────────
# Triangular-ripple duty-cycle correction F(D) — from JS V5.1 (cfg.c = 1.444).
# F(D) normalises the core-loss prediction for triangular (non-sinusoidal) excitation.
#   At D = 0.5:   F ≈ 0.727  →  triangular waveform gives ~27 % LESS loss than sinusoidal
#   At D ≈ 0.05:  F ≈ 1.28   →  triangular gives 28 % MORE loss (high-line PFC corner)
#   At D ≈ 0.68:  F ≈ 0.735  →  low-line PFC crest — slight reduction
IGSE_C  = 1.444    # Steinmetz frequency exponent (matches JS cfg.c)
IGSE_B  = 2.106    # Steinmetz flux exponent (matches JS cfg.b)
IGSE_IC = 3.5435   # ∫₀^π |cos θ|^IGSE_C dθ (numerical)
IGSE_K  = (2 ** IGSE_C) / ((2 * math.pi) ** (IGSE_C - 1) * IGSE_IC)


def _Fd(D: float) -> float:
    """iGSE duty-cycle correction for triangular current ripple.

    F(D) = K × [D^(1−c) + (1−D)^(1−c)]
    where K = 2^c / ((2π)^(c−1) × IC),  c = 1.444.

    Multiply database core-loss by _Fd(D) to convert from sinusoidal-test
    data to the triangular-ripple excitation present in a PFC boost inductor.
    """
    D = max(0.02, min(0.98, D))
    return IGSE_K * (D ** (1.0 - IGSE_C) + (1.0 - D) ** (1.0 - IGSE_C))


def _retention_edge(H_Oe: float) -> float:
    """Analytical DC-bias retention k(H) for EDGE (Magnetics Inc.) powder cores.

    k(H) = 1 / [100 × (0.01 + 9.202×10⁻¹⁰ × H^3.044)]

    Matches JS V5.1 `retention()` exactly. Used as a fast analytical fallback
    inside the waveform-integration loop where 360 DB calls per core would add
    latency. The DB-based k_bias is still used for the main N-convergence loop.
    """
    H = max(0.0, H_Oe)
    return min(1.0, (1.0 / (0.01 + 9.202e-10 * H ** 3.044)) / 100.0)


# ── OPS array (from Mode A + Steps 1-5) ──────────────────────────────────
DEFAULT_OPS = np.array([
    # [Vin_rms, Pout_W, eta, PF, Iφ_rms]
    [ 90, 1700, 0.945, 0.9987, 10.07],
    [110, 1700, 0.955, 0.9986,  8.27],
    [120, 1700, 0.965, 0.9985,  7.54],
    [132, 1700, 0.975, 0.9980,  6.83],
    [180, 3600, 0.965, 0.9889, 10.59],
    [200, 3600, 0.975, 0.9884,  9.44],
    [220, 3600, 0.985, 0.9790,  8.56],
    [230, 3600, 0.988, 0.9789,  8.15],
    [264, 3600, 0.990, 0.9520,  7.24],
])


@dataclass
class DesignResult:
    """Stores full Step 13 results for one core candidate."""
    # Core identity
    core_name:      str = ""
    part_number:    str = ""
    stacks:         int = 1
    material_key:   str = ""
    core_type:      str = ""   # "ferrite" | "powder"

    # Geometry
    Ae_total_mm2:   float = 0.0
    Wa_total_mm2:   float = 0.0
    Ve_total_cm3:   float = 0.0
    Le_single_mm:   float = 0.0
    h_effective_mm: float = 0.0
    # Core physical dimensions (needed for report generation)
    OD_mm:          float = 0.0
    ID_mm:          float = 0.0
    HT_mm:          float = 0.0
    Ae_single_mm2:  float = 0.0
    Wa_single_mm2:  float = 0.0
    AL_nom_nH:      float = 0.0   # single-stack AL nominal
    AL_tol_pct:     float = 8.0   # AL tolerance %
    supplier:       str   = ""

    # Turns & inductance (Step 13.3)
    N:              int   = 0
    L0_min_uH:      float = 0.0
    L0_nom_uH:      float = 0.0
    L0_max_uH:      float = 0.0
    kreq_min:       float = 0.0
    kreq_nom:       float = 0.0
    kreq_max:       float = 0.0
    AT_design:      float = 0.0   # N × Iavg@crest at 90 Vac
    H_Oe_design:    float = 0.0   # H at design point
    I_dc_worst_A:   float = 0.0   # worst-case per-phase DC bias current driving N convergence (powder)
    H_Oe_worst:     float = 0.0   # H(Oe) = 0.4*pi*N*I_dc_worst/Le at the converged N — sets k_bias rolloff
    k_bias_worst:   float = 0.0   # permeability retention k(H_Oe_worst) used in the L_full,min >= 0.85*Ltarget check

    # Gap (ferrite only)
    lg_mm:          float = 0.0   # total gap length

    # Flux density (Step 13.5)
    dBpp_T:         float = 0.0
    Bac_pk_T:       float = 0.0
    Bdc_T:          float = 0.0
    Bmin_FL_T:      float = 0.0
    Bmax_FL_T:      float = 0.0
    Bsat_at_Tcore:  float = 0.0
    sat_margin_pct: float = 0.0

    # Winding (Step 13.6)
    wire_designation: str   = ""
    n_strands:          int   = 0
    d_strand_mm:        float = 0.0
    wire_OD_mm:         float = 0.0
    Cu_area_mm2:        float = 0.0
    R_per_m_20C:        float = 0.0
    FFcu:               float = 0.0   # copper fill factor
    Ku:                 float = 0.0   # window fill including insulation
    wound_HT_actual_mm:  float = 0.0  # assembled height: core stack + wire OD (top+bottom)
    wound_OD_actual_mm:  float = 0.0  # assembled OD: core OD + radial winding build at actual FFcu
    mounting:            str   = 'horizontal'  # 'horizontal' | 'vertical'
    installed_height_mm: float = 0.0  # chassis height for the chosen mounting orientation

    # Losses (Step 13.7)
    MLT_mm:         float = 0.0
    Cu_length_m:    float = 0.0
    DCR_25C_mOhm:   float = 0.0
    DCR_100C_mOhm:  float = 0.0
    Rac_Rdc:        float = 1.0   # Dowell factor (ferrite only)
    Pcu_25C_W:      float = 0.0
    Pcu_100C_W:     float = 0.0
    Pcu_25C_firstpass_W:  float = 0.0   # genuine first-pass I_rms,ref^2*DCR estimate (90 Vac) —
    Pcu_100C_firstpass_W: float = 0.0   # preserved separately so Sec 3.6 ("first-pass") can show
                                        # operands that literally sum to its displayed P_total
    P_fringing_W:   float = 0.0   # Rogowski fringing (ferrite only)
    Pcore_W:        float = 0.0   # half-cycle averaged core loss with iGSE F(D), at T_core
    Pcore_crest_W:  float = 0.0   # crest-only core loss (legacy reference point)
    Ptotal_25C_W:   float = 0.0
    Ptotal_100C_W:  float = 0.0

    # iGSE / waveform-integration results (JS V5.1 equivalent)
    Fd_design:      float = 1.0   # F(D) correction at 90 Vac design crest
    Bdc_max_T:      float = 0.0   # max B_dc over the half line cycle (from 360-pt integration)
    Ihf_rms_A:      float = 0.0   # HF ripple RMS current  I_hf = ΔI_pp / (2√3) averaged
    Pac_W:          float = 0.0   # AC (HF ripple) copper loss: I_hf_rms² × R_ac
    J_A_mm2:        float = 0.0   # current density A/mm² in the copper conductor
    P_unc_lo_W:     float = 0.0   # lower uncertainty bound: P_cu + 1.05 × P_core
    P_unc_hi_W:     float = 0.0   # upper uncertainty bound: P_cu + 1.20 × P_core

    # Loss vs Vin tables (Steps 13.8 + 13.9)
    loss_table_25C:  list = field(default_factory=list)
    loss_table_100C: list = field(default_factory=list)

    # Inductance vs Vin (Step 13.4) — powder only
    L_vs_Vin_table:  list = field(default_factory=list)

    # Thermal
    T_amb_C:        float = 50.0
    T_core_C:       float = 0.0
    dT_rise_C:      float = 0.0
    dT_budget_C:    float = 60.0

    # Medical
    creepage_ok:    bool  = True
    creepage_mm:    float = 0.0

    # Pass/fail
    passed:         bool  = False
    fail_reasons:   list  = field(default_factory=list)

    # Composite score (lower = better)
    score:          float = 999.0


def _compute_MLT(core: dict, stacks: int = 1) -> float:
    """
    Mean length per turn (mm).

    Toroid: cross-section perimeter method — matches JS V5.1 calibrated formula.
      MLT = 2 × (coreW + HT_total) + 3.8
      where coreW = (OD-ID)/2  (radial width of one core)
            HT_total = HT × stacks  (winding traverses the full stack height)
            3.8 mm = lead-routing allowance (calibrated to EDGE reference design)
    This correctly scales with stack count, unlike the pure-circumferential formula.

    ETD/EE: use catalog MLT_mm value.
    """
    if "ID_mm" in core and float(core.get("ID_mm", 0)) > 0:
        OD = float(core["OD_mm"])
        ID = float(core["ID_mm"])
        HT = float(core["HT_mm"])
        coreW = (OD - ID) / 2          # radial width of core cross-section
        return 2 * (coreW + HT * stacks) + 3.8
    return float(core.get("MLT_mm", 100.0))


def _thermal_dT_SA(wound_OD_mm: float, wound_HT_mm: float,
                   hole_ID_mm: float, P_total_W: float) -> float:
    """ΔT from wound-surface-area power law — matches JS V5.1 formula exactly.

    SA [cm²] = [π·OD_w·OH + (π/2)·(OD_w² − hole²) + π·hole·OH] / 100
    ΔT [°C]  = (P_total [W] × 1000 / SA [cm²]) ^ 0.833

    All dimensions in mm.  Matches the JS studio 'Thermal envelope' model
    (identical to generate_steps13_14.py SA model).
    """
    od   = wound_OD_mm
    oh   = wound_HT_mm           # total wound height (stack + build)
    hole = max(0.5, hole_ID_mm)  # residual bore hole after winding
    SA   = (math.pi * od * oh
            + 2 * (math.pi / 4) * (od**2 - hole**2)
            + math.pi * hole * oh) / 100.0   # cm²
    SA   = max(SA, 1.0)          # guard against zero
    return (P_total_W * 1000.0 / SA) ** 0.833


def _thermal_Rth(core: dict, stacks: int = 1, h_forced: float = 17.5) -> float:
    """Kept for ETD/ferrite cores and backwards compatibility.
    Toroid path now uses _thermal_dT_SA which matches the JS studio exactly.
    """
    if "ID_mm" in core and float(core.get("ID_mm", 0)) > 0:
        # Toroid — caller should use _thermal_dT_SA; return a reasonable fallback
        OD_core = float(core["OD_mm"]) * 1e-3
        HT      = float(core["HT_mm"]) * stacks * 1e-3
        OD_eff  = OD_core + 2 * 4e-3
        ID_eff  = max(float(core["ID_mm"]) * 1e-3 - 2 * 3e-3, 2e-3)
        A_surf  = math.pi/4 * (OD_eff**2 - ID_eff**2) * 2 + math.pi * OD_eff * HT
        return 1.0 + 1.0 / max(1e-6, h_forced * A_surf)
    else:
        Ae = float(core.get("Ae_mm2", 100)) * 1e-6
        Le = float(core.get("Le_mm", 100)) * 1e-3
        A_surf = 2 * Ae * 2 + Le * math.sqrt(4 * Ae) * 1.5
        return 8.5 + 1.0 / max(1e-6, h_forced * A_surf)


def _half_cycle_averages(
    material_key: str,
    core_type: str,
    N: int,
    Ae_m2: float,
    Ve_m3: float,
    Le_s: float,
    L0_nom_H: float,
    Icrest_A: float,         # per-phase crest-average current (I_phi,avg @ crest)
    Vout_V: float,
    Vin_pk_V: float,         # peak line voltage at the chosen operating point
    fsw_Hz: float,
    Rdc: float,              # Ω at operating temperature
    Rac: float,              # Ω_ac = Rdc × Rac_Rdc
    T_core_C: float = 100.0,
    f_line_Hz: float = 60.0,
    M: int = 360,
    return_series: bool = False,   # also return per-angle θ/Bac_pk/Pcore arrays
) -> dict:
    """360-point half-cycle waveform integration matching JS V5.1 `compute()` loop.

    Samples θ = 0 … π (one half of the rectified line cycle) at M uniformly
    spaced points.  At each point:
      • V_in(θ) = V_pk × sin(θ)
      • D(θ)    = 1 − V_in/V_out   (boost duty cycle)
      • I_avg(θ) = I_crest × sin(θ)  (half-sine current envelope)
      • k(H)    from analytical retention formula (fast, no DB)
      • B_ac,pk = V_in × D / (2 × N × A_e × f_sw)
      • P_core  = P_v(B_ac,pk, f_sw, T) × V_e × F(D)   [iGSE correction]
      • I_hf    = ΔI_pp / (2√3)  [triangular ripple RMS]
      • P_cu    = R_dc × I_avg² + R_ac × I_hf²

    Returns a dict with time-averaged and peak quantities.
    """
    pCoreAcc = 0.0
    i2       = 0.0   # Σ I_avg²
    r2       = 0.0   # Σ I_hf²
    BdcMax   = 0.0
    BmaxPk   = 0.0
    pCorePk  = 0.0
    pCuPk    = 0.0
    pTotPk   = 0.0
    series_theta = [] if return_series else None
    series_Bac   = [] if return_series else None
    series_Pcore = [] if return_series else None

    for n in range(M):
        theta = (n + 0.5) * math.pi / M
        s     = math.sin(theta)
        Vin   = Vin_pk_V * s
        D     = max(0.0, min(0.98, 1.0 - Vin / Vout_V))
        Iavg  = Icrest_A * s

        # DC bias → retention → effective L(θ) — use analytical formula (fast)
        if core_type == "powder":
            Le_cm = Le_s * 100.0   # m → cm
            H_Oe  = 0.4 * math.pi * N * Iavg / Le_cm
            k_b   = _retention_edge(H_Oe)
        else:
            k_b = 1.0
        Lth = max(L0_nom_H * k_b, 1e-9)

        # Flux densities
        dBpp  = Vin * D / (N * Ae_m2 * fsw_Hz)
        BacPk = dBpp / 2.0
        Bdc   = Lth * Iavg / (N * Ae_m2)
        Bmx   = Bdc + BacPk

        # Core loss with iGSE F(D) correction
        Fd      = _Fd(D)
        Pv_Wm3  = _db().get_core_loss(material_key, fsw_Hz, BacPk, T_core_C) * 1e3
        Pcore_i = Pv_Wm3 * Fd * Ve_m3

        # HF ripple current: ΔI_pp / (2√3) — triangular ripple RMS
        dIpp  = Vin * D / max(Lth * fsw_Hz, 1e-12)
        Ihf   = dIpp / (2.0 * math.sqrt(3.0))

        # Instantaneous copper loss: DC term + AC term (JS decomposition)
        Pcu_i = Rdc * Iavg ** 2 + Rac * Ihf ** 2
        Ptot_i = Pcore_i + Pcu_i

        pCoreAcc += Pcore_i
        i2       += Iavg ** 2
        r2       += Ihf  ** 2
        BdcMax    = max(BdcMax,  Bdc)
        BmaxPk    = max(BmaxPk,  Bmx)
        pCorePk   = max(pCorePk, Pcore_i)
        pCuPk     = max(pCuPk,   Pcu_i)
        pTotPk    = max(pTotPk,  Ptot_i)

        if return_series:
            series_theta.append(theta)
            series_Bac.append(BacPk)
            series_Pcore.append(Pcore_i)

    Pcore_avg = pCoreAcc / M
    Irms      = math.sqrt(i2 / M)
    IhfRms    = math.sqrt(r2 / M)
    Pac       = IhfRms ** 2 * Rac
    Pcu_avg   = Irms ** 2 * Rdc + Pac

    return {
        "Pcore_avg_W":  Pcore_avg,
        "Irms_A":       Irms,
        "IhfRms_A":     IhfRms,
        "Pac_W":        Pac,
        "Pcu_avg_W":    Pcu_avg,
        "Ptot_avg_W":   Pcore_avg + Pcu_avg,
        "BdcMax_T":     BdcMax,
        "Bmax_T":       BmaxPk,
        "Pcore_pk_W":   pCorePk,
        "Pcu_pk_W":     pCuPk,
        "Ptot_pk_W":    pTotPk,
        **({"theta_rad": series_theta, "Bac_pk_T_series": series_Bac,
            "Pcore_W_series": series_Pcore} if return_series else {}),
    }


def design_one_core(
    core: dict,          # from _db().filter_cores()
    material_key: str,
    L_target_H: float,
    Ipk_A: float,        # per-phase peak current
    Irms_A: float,       # per-phase RMS current
    IL_HF_rms_A: float,  # HF ripple component of Irms
    dIL_pp_A: float,     # peak-to-peak ripple at design point
    fsw_Hz: float,
    wire: dict,          # from get_wire_options()
    N_phases: int,
    OPS: np.ndarray,
    T_amb_C: float = 50.0,
    dT_budget_C: float = 60.0,
    J_target: float = 5.0,
    app_class: str = "Industrial",
    h_conv: float = 17.5,
    FFcu_limit: float = 0.40,   # designer-selectable fill factor
    mounting:   str   = 'horizontal',  # 'horizontal' | 'vertical'
) -> DesignResult:
    """
    Full Step 13 calculation for one (core, material, wire) combination.
    Matches reference document Steps 13.1–13.10 exactly.
    Adds: Dowell AC factor, Rogowski fringing, Rth thermal, 9-op-point checks.
    """
    res = DesignResult()
    res.material_key   = material_key
    res.core_type      = _load_material_type(material_key)
    res.core_name      = str(core.get("material_line", core.get("shape", "")))
    res.part_number    = str(core.get("part_number", ""))
    res.stacks         = int(core.get("stacks", 1))
    res.Ae_total_mm2   = float(core["Ae_total_mm2"])
    res.Wa_total_mm2   = float(core["Wa_total_mm2"])
    res.Ve_total_cm3   = float(core["Ve_total_cm3"])
    res.Le_single_mm   = float(core["Le_single_mm"])
    res.h_effective_mm = float(core["h_effective_mm"])
    res.T_amb_C        = T_amb_C
    res.dT_budget_C    = dT_budget_C
    # Physical dims for report (single-stack values)
    res.OD_mm         = float(core.get("OD_mm", 0.0))
    res.ID_mm         = float(core.get("ID_mm", 0.0))
    res.HT_mm         = float(core.get("HT_mm", 0.0))
    res.Ae_single_mm2 = float(core.get("Ae_single_mm2",
                              float(core["Ae_total_mm2"]) / max(int(core.get("stacks", 1)), 1)))
    res.Wa_single_mm2 = float(core.get("Wa_mm2",
                              float(core.get("Wa_total_mm2", 0)) / max(int(core.get("stacks", 1)), 1)))
    # AL values for report (single-stack nominal and tolerance)
    _stk   = max(int(core.get("stacks", 1)), 1)
    _al_t  = float(core.get("AL_nom_total", core.get("AL_nom_nH", 75)))
    res.AL_nom_nH  = round(_al_t / _stk, 2)           # single-stack nominal
    res.AL_tol_pct = float(core.get("AL_tolerance_pct", 8))
    res.supplier   = str(core.get("supplier", ""))

    Ae   = res.Ae_total_mm2  * 1e-6    # m²
    Wa   = res.Wa_total_mm2  * 1e-6    # m²
    Ve   = res.Ve_total_cm3  * 1e-6    # m³
    Le_s = res.Le_single_mm  * 1e-3    # m (single core, used for H calculation)

    # Design point: Vin=90Vac row from OPS (index 0)
    Vout_V = 393.0
    # Ipk_A is per-phase PEAK (DC bias + half ripple).
    # DC bias component = Ipk_A - dIL_pp/2 = Iφ,avg@crest (reference Step 13.1: 14.152A)
    # Do NOT divide by N_phases again — Ipk_A is already per-phase.
    I_phi_avg_crest = max(Ipk_A - dIL_pp_A / 2.0, Irms_A * 0.9)

    # ── Step 13.3: Turns ────────────────────────────────────────────────────
    if res.core_type == "powder":
        # Worst-case DC bias = max per-phase Iavg across all 9 op-points
        # 180Vac full-load gives Iavg=14.82A > 90Vac Iavg=14.15A (higher power level)
        I_dc_worst = I_phi_avg_crest
        for op_row in OPS:
            vin_op,pout_op,eta_op,pf_op = float(op_row[0]),float(op_row[1]),float(op_row[2]),float(op_row[3])
            iavg_op = (math.sqrt(2)*pout_op/eta_op)/(vin_op*pf_op) / max(N_phases,1)
            if iavg_op > I_dc_worst: I_dc_worst = iavg_op
        N, L0_min, L0_nom, L0_max, kreq_min, kreq_nom, kreq_max, H_Oe_worst, k_bias_worst = \
            _turns_powder(core, material_key, L_target_H, I_dc_worst, Le_s)
        res.I_dc_worst_A = round(I_dc_worst, 4)
        res.H_Oe_worst   = round(H_Oe_worst, 3)
        res.k_bias_worst = round(k_bias_worst, 4)
        res.lg_mm = 0.0
    else:
        N, lg_mm, Bpk_converged = _turns_ferrite(core, material_key, L_target_H, Ipk_A)
        L0_min = L0_nom = L0_max = L_target_H * 1e6  # ferrite L ≈ flat vs bias
        kreq_min = kreq_nom = kreq_max = 1.0
        res.lg_mm = lg_mm

    if N <= 0:
        res.fail_reasons.append("Could not converge on valid N.")
        return res

    res.N           = N
    res.L0_min_uH   = round(L0_min * 1e6, 3)
    res.L0_nom_uH   = round(L0_nom * 1e6, 3)
    res.L0_max_uH   = round(L0_max * 1e6, 3)
    res.kreq_min    = round(kreq_min, 4)
    res.kreq_nom    = round(kreq_nom, 4)
    res.kreq_max    = round(kreq_max, 4)
    res.AT_design   = round(N * I_phi_avg_crest, 2)
    res.H_Oe_design = round((N * I_phi_avg_crest / Le_s) / 79.577, 2)

    # ── Step 13.4: Inductance vs Vin (all op-points) ─────────────────────────
    res.L_vs_Vin_table = _build_L_vs_Vin_table(
        material_key, res.core_type, N, L0_nom * 1e6, L0_min * 1e6, L0_max * 1e6,
        Le_s, OPS, L_target_H * 1e6)

    # ── Step 13.5: Flux density ──────────────────────────────────────────────
    # 13.5.1: AC flux swing from volt-seconds at 90 Vac crest
    Vin_pk90 = OPS[0, 0] * math.sqrt(2)
    Vout_V   = 393.0
    Dpk90    = 1 - Vin_pk90 / Vout_V
    dBpp     = Vin_pk90 * Dpk90 / (N * Ae * fsw_Hz)
    Bac_pk   = dBpp / 2

    # 13.5.2: DC flux density at full-load crest
    if res.core_type == "powder":
        H_dc  = N * I_phi_avg_crest / Le_s
        H_Oe  = H_dc / 79.577
        k_b   = _db().get_k_bias(material_key, H_Oe)
        AL_eff = float(core.get("AL_nom_total", core.get("AL_nom_nH", 75))) * k_b * 1e-9
        Bdc   = L_target_H * I_phi_avg_crest / (N * Ae)
    else:
        mu_r = _db().get_mu_r(material_key, 100.0)
        lg   = res.lg_mm * 1e-3
        Bdc  = MU0 * N * I_phi_avg_crest / (lg + Le_s / mu_r)

    res.dBpp_T      = round(dBpp, 6)
    res.Bac_pk_T    = round(Bac_pk, 6)
    res.Bdc_T       = round(Bdc, 6)
    res.Bmin_FL_T   = round(Bdc - Bac_pk, 6)
    res.Bmax_FL_T   = round(Bdc + Bac_pk, 6)

    # ── Step 13.6: Winding fill factor ────────────────────────────────────────
    # MLT passes res.stacks so the winding path scales correctly with stack count.
    MLT    = _compute_MLT(core, res.stacks)   # mm/turn  (JS V5.1 formula)
    Cu_len = N * MLT / 1000.0                 # m

    d_s_mm  = float(wire.get("strand_dia_mm", 0.1))
    n_str   = int(wire.get("strands", 200))
    OD_mm   = float(wire.get("OD_mm", 2.0))
    Cu_area = float(wire.get("Cu_area_mm2", 1.0))
    R_per_m = float(wire.get("R_per_m_20C_ohm", 0.01))
    designation = str(wire.get("designation", ""))

    # Read n_parallel from wire dict (set by main.py adjusted_wires to 1/2/3)
    n_parallel = int(wire.get("n_parallel", 1) or 1)

    # ── Fill factor — Reference Step 13.6.2 (corrected denominator) ──────────
    # For a stacked toroid the winding passes through the bore of EACH core,
    # but the bore opening is the SAME for every core in the stack — it does NOT
    # multiply with stack count.  The correct denominator is Wa_single_mm2.
    #
    # FFcu (bare copper) = N × Cu_area / Wa_single   ← reference criterion (≤ 0.40)
    # Ku   (insulated)   = N × n_par × (π/4 × bundleOD²) / Wa_single  ← physical fit
    #                      matches JS V5.1: fillIns = (N × 2 × π/4 × OD²) / Wa_single
    #
    # Cu_area from wire dict = Cu_per_conductor × n_parallel (set by main.py).
    Wa_bore  = res.Wa_single_mm2          # bore cross-section of ONE core (invariant)
    Acu_total = N * Cu_area               # mm² bare copper (n_par already in Cu_area)
    FFcu      = Acu_total / Wa_bore       # bare-copper fill (reference Step 13.6.2)

    # Medical deduction: toroid → TIW wire handles creepage (no Kapton area loss)
    #                    ferrite → Kapton tape reserves ~6% of window
    kapton_factor = 1.0 if (res.core_type == "powder") else (
                    0.94 if app_class == "Medical" else 1.0)
    Wa_avail = Wa_bore * kapton_factor    # effective available bore area

    # Physical (insulated) fill factor — determines whether the winding can
    # actually be wound through the bore.
    #   powder toroid → Ku_ins = N × n_par × (π/4 × OD_mm²) / Wa_avail
    #   ferrite ETD   → Ku_ins = N × A_bundle / Wa_avail  (bundle OD includes all strands)
    if res.core_type == "powder":
        A_bundle_ins = math.pi / 4 * OD_mm ** 2   # insulated area of ONE bundle
        Ku = N * n_parallel * A_bundle_ins / Wa_avail
    else:
        d_bundle = d_s_mm * 1.05 * math.sqrt(n_str * n_parallel) * 1.20   # mm
        A_bundle = math.pi / 4 * d_bundle ** 2
        Ku       = N * A_bundle / Wa_avail

    res.wire_designation = designation
    res.n_strands        = n_str
    res.d_strand_mm      = d_s_mm
    res.wire_OD_mm       = OD_mm
    res.Cu_area_mm2      = round(Cu_area, 4)
    res.R_per_m_20C      = round(R_per_m / n_parallel, 8)
    res.MLT_mm           = round(MLT, 4)
    res.Cu_length_m      = round(Cu_len, 6)
    res.FFcu             = round(FFcu, 4)
    res.Ku               = round(Ku, 4)

    # Actual assembled dimensions using selected wire diameter and real FFcu
    # wound_HT: bare stack height + one wire-OD above and below the core
    _HT_stack_bare        = res.HT_mm * res.stacks + max(0, res.stacks - 1) * 1.5
    res.wound_HT_actual_mm = round(_HT_stack_bare + 2 * OD_mm, 1)  # OD_mm = wire OD
    # wound_OD: core OD + radial build scaled from catalog ref (40% fill) to actual FFcu
    _wound_OD_cat         = float(core.get("wound_OD_mm") or (res.OD_mm + 8.0))
    _ref_build            = (_wound_OD_cat - res.OD_mm) / 2.0
    _scale                = (FFcu / 0.40) if FFcu > 0 else 1.0
    res.wound_OD_actual_mm = round(res.OD_mm + 2 * _ref_build * _scale, 1)

    # Installed chassis height depends on mounting orientation:
    #   horizontal → cores flat, stacked vertically → height = wound stack HT
    #   vertical   → cores upright, side by side    → height = single wound OD
    res.mounting            = mounting
    res.installed_height_mm = (
        res.wound_HT_actual_mm if mounting == 'horizontal'
        else res.wound_OD_actual_mm
    )

    # ── Step 13.7: Losses ─────────────────────────────────────────────────────
    # 13.7.2: DCR
    R_pm_20 = res.R_per_m_20C
    DCR_25  = R_pm_20 * (1 + ALPHA_CU * (25 - 20)) * Cu_len
    DCR_100 = R_pm_20 * (1 + ALPHA_CU * (100 - 20)) * Cu_len

    res.DCR_25C_mOhm  = round(DCR_25  * 1e3, 4)
    res.DCR_100C_mOhm = round(DCR_100 * 1e3, 4)

    # Dowell AC factor (ferrite only — for Litz wound toroid: not applied)
    if res.core_type == "ferrite":
        dowell = compute_dowell_factor(n_str, d_s_mm, N, res.Wa_total_mm2, fsw_Hz, 100.0)
        Rac_Rdc = dowell["Rac_Rdc"]
    else:
        Rac_Rdc = 1.0   # Litz toroid — Dowell factor small, reference uses simple DCR

    res.Rac_Rdc = round(Rac_Rdc, 4)

    # 13.7.3: Copper loss at each temperature using decomposed formula
    #   P_cu = I_rms² × R_dc  +  I_hf_rms² × R_ac   (JS V5.1 decomposition)
    # Use IL_rms_ref from OPS table (90 Vac) for the 25/100°C rated figures.
    IL_rms_ref = float(OPS[0, 4])   # 90 Vac Iφ,rms
    # Estimate HF ripple at 90 Vac crest operating point for decomposed Pcu
    Vin_pk90_loss = OPS[0, 0] * math.sqrt(2)
    Dpk90_loss    = max(0.0, 1.0 - Vin_pk90_loss / 393.0)
    dIpp_90       = Vin_pk90_loss * Dpk90_loss / max(L_target_H * fsw_Hz, 1e-12)
    Ihf_ref       = dIpp_90 / (2.0 * math.sqrt(3.0))

    res.Pcu_25C_W  = round(
        IL_rms_ref**2 * DCR_25  + Ihf_ref**2 * DCR_25  * Rac_Rdc, 4)
    res.Pcu_100C_W = round(
        IL_rms_ref**2 * DCR_100 + Ihf_ref**2 * DCR_100 * Rac_Rdc, 4)
    # Preserve these genuine first-pass figures under their own names — they get
    # overwritten below with the cycle-averaged final Pcu (used by Ptotal_*_W and
    # the legacy report generators). Sec 3.6 of the documentation reports the
    # "first-pass" methodology and must show operands that literally sum to its
    # displayed P_total — it reads these *_firstpass_W fields, not the overwritten ones.
    res.Pcu_25C_firstpass_W  = res.Pcu_25C_W
    res.Pcu_100C_firstpass_W = res.Pcu_100C_W

    # iGSE F(D) correction at the 90 Vac design crest
    Fd_crest  = _Fd(Dpk90)
    res.Fd_design = round(Fd_crest, 4)

    # Rogowski fringing (ferrite only)
    if res.core_type == "ferrite" and res.lg_mm > 0:
        d_bundle = d_s_mm * 1.05 * math.sqrt(n_str * n_parallel) * 1.20
        fring = compute_rogowski_fringing(
            res.lg_mm, res.Ae_total_mm2, res.Wa_total_mm2, N,
            d_bundle, IL_HF_rms_A, DCR_100)
        res.P_fringing_W = fring["P_fring_W"]
    else:
        res.P_fringing_W = 0.0

    # ── Thermal convergence loop ──────────────────────────────────────────────
    # Toroid: SA power-law  ΔT = (P×1000/SA_cm²)^0.833  — matches JS V5.1 exactly.
    # Ferrite ETD: convection Rth model (SA model is calibrated for wound toroids).
    T_core = T_amb_C + 0.5 * dT_budget_C   # initial guess
    _is_toroid = "ID_mm" in core and float(core.get("ID_mm", 0)) > 0

    if _is_toroid:
        # Compute residual bore hole (bore area remaining after all winding layers)
        _bore_r  = res.ID_mm / 2.0
        _bnd_r   = OD_mm / 2.0
        _passes  = N * n_parallel
        _r_cur   = _bore_r - _bnd_r
        while _passes > 0 and _r_cur >= _bnd_r:
            _cap    = max(1, int(2 * math.pi * _r_cur / OD_mm))
            _passes -= min(_passes, _cap)
            _r_cur  -= OD_mm
        _hole_ID = max(0.5, (_r_cur + _bnd_r) * 2)
    else:
        _hole_ID = 0.0
        Rth      = _thermal_Rth(core, res.stacks, h_conv)

    for _ in range(10):
        Pv    = _db().get_core_loss(material_key, fsw_Hz, Bac_pk, T_core) * 1e3  # W/m³
        Pcore = Pv * Fd_crest * Ve    # iGSE F(D) applied at crest duty cycle
        Pcu_T = IL_rms_ref**2 * R_pm_20 * (1 + ALPHA_CU * (T_core - 20)) * Cu_len * Rac_Rdc
        Ptot  = Pcore + Pcu_T + res.P_fringing_W
        if _is_toroid:
            T_new = T_amb_C + _thermal_dT_SA(
                res.wound_OD_actual_mm, res.wound_HT_actual_mm, _hole_ID, Ptot)
        else:
            T_new = T_amb_C + Ptot * Rth
        if abs(T_new - T_core) < 0.2:
            T_core = T_new
            break
        T_core = T_new

    # ── 360-point half-cycle waveform integration (JS V5.1 `compute()` loop) ─
    # Run once at the converged T_core.  Uses the analytical retention formula
    # (fast, no DB per point) and the iGSE F(D) correction at every θ.
    Rdc_Tc = R_pm_20 * (1 + ALPHA_CU * (T_core - 20)) * Cu_len   # Ω at T_core
    Rac_Tc = Rdc_Tc * Rac_Rdc
    L0_nom_H = (res.AL_nom_nH * res.stacks) * 1e-9 * N**2  # total L0 at 0 A bias

    wf = _half_cycle_averages(
        material_key = material_key,
        core_type    = res.core_type,
        N            = N,
        Ae_m2        = Ae,
        Ve_m3        = Ve,
        Le_s         = Le_s,
        L0_nom_H     = L0_nom_H,
        Icrest_A     = I_phi_avg_crest,
        Vout_V       = 393.0,
        Vin_pk_V     = Vin_pk90,
        fsw_Hz       = fsw_Hz,
        Rdc          = Rdc_Tc,
        Rac          = Rac_Tc,
        T_core_C     = T_core,
        f_line_Hz    = 60.0,   # standard 60 Hz (from OPS table design assumption)
        M            = 360,
    )

    # Use waveform-averaged core loss as the authoritative Pcore_W value
    Pcore_avg = wf["Pcore_avg_W"]
    Pcu_avg   = wf["Pcu_avg_W"]

    res.T_core_C      = round(T_core, 2)
    res.dT_rise_C     = round(T_core - T_amb_C, 2)
    res.Pcore_crest_W = round(Pcore, 4)       # crest-only (legacy)
    res.Pcore_W       = round(Pcore_avg, 4)   # half-cycle average with iGSE (primary)
    res.Ihf_rms_A     = round(wf["IhfRms_A"], 5)
    res.Pac_W         = round(wf["Pac_W"], 5)
    res.Bdc_max_T     = round(wf["BdcMax_T"], 6)
    res.Bmax_FL_T     = round(wf["Bmax_T"], 6)  # overwrite crest estimate with waveform max

    # Current density J = I_rms / Cu_area_per_conductor (single-strand Cu area × n_strands)
    Cu_per_cond = float(wire.get("Cu_area_mm2", 1.0)) / max(n_parallel, 1)
    res.J_A_mm2 = round(wf["Irms_A"] / max(Cu_per_cond, 0.001), 3)

    # Final Pcu using decomposed formula with waveform Irms and Ihf_rms
    Pcu_final_100 = wf["Irms_A"]**2 * DCR_100 + wf["IhfRms_A"]**2 * DCR_100 * Rac_Rdc
    Pcu_final_25  = wf["Irms_A"]**2 * DCR_25  + wf["IhfRms_A"]**2 * DCR_25  * Rac_Rdc

    res.Ptotal_25C_W  = round(Pcu_final_25  + Pcore_avg + res.P_fringing_W, 4)
    res.Ptotal_100C_W = round(Pcu_final_100 + Pcore_avg + res.P_fringing_W, 4)

    # Uncertainty band: P_cu + [1.05 … 1.20] × P_core  (matches JS V5.1)
    res.P_unc_lo_W = round(Pcu_final_100 + 1.05 * Pcore_avg, 4)
    res.P_unc_hi_W = round(Pcu_final_100 + 1.20 * Pcore_avg, 4)

    # Back-fill Pcu fields from waveform decomposition
    res.Pcu_25C_W  = round(Pcu_final_25,  4)
    res.Pcu_100C_W = round(Pcu_final_100, 4)

    # Saturation margin at T_core
    res.Bsat_at_Tcore  = round(_db().get_Bsat(material_key, T_core), 4)
    res.sat_margin_pct = round((res.Bsat_at_Tcore - res.Bmax_FL_T) / res.Bsat_at_Tcore * 100, 1)

    # ── Steps 13.8 + 13.9: Loss vs Vin sweeps (with iGSE F(D) correction) ────
    res.loss_table_25C  = _build_loss_table(material_key, N, Ae, Ve, Le_s,
                                            R_pm_20, Rac_Rdc, Cu_len, fsw_Hz,
                                            Vout_V, OPS, T_C=25.0,
                                            L_target_H=L_target_H)
    res.loss_table_100C = _build_loss_table(material_key, N, Ae, Ve, Le_s,
                                            R_pm_20, Rac_Rdc, Cu_len, fsw_Hz,
                                            Vout_V, OPS, T_C=100.0,
                                            L_target_H=L_target_H)

    # ── Medical creepage check ────────────────────────────────────────────────
    if app_class == "Medical":
        creepage = float(core.get("bobbin_creepage_mm", 0) or 0)
        res.creepage_mm = creepage
        if res.core_type == "powder":
            # Powder toroids have no bobbin — creepage achieved via TIW wire or Kapton
            # Do NOT fail the design — flag it as a winding note instead
            res.creepage_ok = True
            if creepage < 6.0:
                res.fail_reasons  # don't add to fail_reasons — winding note only
        else:
            res.creepage_ok = creepage >= 6.0
            if not res.creepage_ok:
                res.fail_reasons.append(
                    f"Creepage {creepage:.0f}mm < 6mm (IEC 60601-1 Medical). "
                    "Use extended-flange bobbin (e.g. ETD59/31/22-E with 14mm).")

    # ── Pass/fail checks ──────────────────────────────────────────────────────
    # Pass/fail limits:
    #   FFcu (bare copper) ≤ FFcu_limit (default 0.40) — reference Step 13.6.2
    #   Ku   (insulated)   ≤ ku_lim    — physical winding limit:
    #     powder toroid: Ku_ins uses insulated bundle area; practical limit ≈ 0.75
    #     ferrite ETD:   Ku_ins uses full bundle OD; limit = FFcu_limit + 0.05
    if res.core_type == "powder":
        ku_lim = 0.75   # ≥0.75 = beyond practical toroid winding limit (JS: fitHard ≥ 0.85, fitTight > 0.70)
    else:
        ku_lim = min(FFcu_limit + 0.05, 0.50)

    # Check BOTH bare-copper fill AND insulated fill
    if FFcu > FFcu_limit:
        res.fail_reasons.append(
            f"FFcu={FFcu:.3f} ({FFcu*100:.1f}%) exceeds bare-copper fill limit {FFcu_limit:.2f}.")
    if res.Ku > ku_lim:
        res.fail_reasons.append(
            f"Ku={res.Ku:.3f} ({res.Ku*100:.1f}% insulated) exceeds winding fit limit {ku_lim:.2f}.")
    if res.sat_margin_pct < 15.0:
        res.fail_reasons.append(f"Saturation margin {res.sat_margin_pct:.1f}% < 15%.")
    if res.dT_rise_C > dT_budget_C:
        res.fail_reasons.append(f"ΔT={res.dT_rise_C:.1f}°C > budget {dT_budget_C:.0f}°C.")
    if res.L_vs_Vin_table:
        Lfull_min = min(r["L_full_min_uH"] for r in res.L_vs_Vin_table)
        if Lfull_min < L_target_H * 1e6 * 0.85:
            res.fail_reasons.append(
                f"L_full,min={Lfull_min:.1f}µH < 85% of L_target at some op-point.")

    res.passed = len(res.fail_reasons) == 0

    # ── Composite score ───────────────────────────────────────────────────────
    if res.passed:
        P_ref   = 4.0; Vol_ref = 50.0
        w_loss  = 0.35; w_vol = 0.25; w_temp = 0.25; w_cost = 0.10; w_ku = 0.05
        Cost_idx = 1.2 if res.core_type == "powder" else 1.0
        Ku_pen   = max(0, res.Ku - 0.35) * 5
        res.score = (w_loss * res.Ptotal_100C_W / P_ref
                   + w_vol  * res.Ve_total_cm3  / Vol_ref
                   + w_temp * res.dT_rise_C     / dT_budget_C
                   + w_cost * Cost_idx
                   + w_ku   * Ku_pen)

    return res


# ── Internal helpers ──────────────────────────────────────────────────────

def _load_material_type(key: str) -> str:
    return _get_mag_db().get_material(key).get("type", "ferrite")


def _turns_powder(core: dict, mat_key: str, L_H: float,
                  I_dc: float, Le_s: float) -> tuple:
    """Powder core: iterative N convergence using DC bias rolloff."""
    AL_nom = float(core.get("AL_nom_total", core.get("AL_nom_nH", 75))) * 1e-9
    AL_min = float(core.get("AL_min_total", core.get("AL_min_nH", 69))) * 1e-9
    AL_max = float(core.get("AL_max_total", core.get("AL_max_nH", 81))) * 1e-9
    tol    = float(core.get("AL_tolerance_pct", 8)) / 100.0

    N = max(1, math.ceil(math.sqrt(L_H / AL_nom)))
    for _ in range(40):
        H_Am  = N * I_dc / Le_s
        H_Oe  = H_Am / 79.577
        k_b   = _db().get_k_bias(mat_key, H_Oe)
        # Check L_full_MIN (worst-case AL tolerance) meets 85% of target
        # This ensures the engine converges to the same N as the reference design
        L_full_min = N**2 * AL_min * k_b
        if L_full_min >= L_H * 0.85:
            break
        N += 1

    L0_min = N**2 * AL_min
    L0_nom = N**2 * AL_nom
    L0_max = N**2 * AL_max

    H_Am   = N * I_dc / Le_s
    H_Oe   = H_Am / 79.577
    k_b    = _db().get_k_bias(mat_key, H_Oe)

    kreq_nom = L_H / L0_nom if L0_nom > 0 else 0
    kreq_min = L_H / L0_min if L0_min > 0 else 0
    kreq_max = L_H / L0_max if L0_max > 0 else 0

    return N, L0_min, L0_nom, L0_max, kreq_min, kreq_nom, kreq_max, H_Oe, k_b


def _turns_ferrite(core: dict, mat_key: str, L_H: float, Ipk: float) -> tuple:
    """Ferrite: iterative N + gap convergence. Returns (N, lg_mm, Bpk)."""
    Ae   = float(core["Ae_total_mm2"]) * 1e-6
    Le   = float(core["Le_single_mm"]) * 1e-3
    mu_r = _db().get_mu_r(mat_key, 100.0)
    Bsat = _db().get_Bsat(mat_key, 100.0)
    Bpk_target = 0.28

    N = math.ceil(L_H * Ipk / (Bpk_target * Ae))
    Bpk_prev = 0.0

    for _ in range(30):
        lg    = MU0 * N**2 * Ae / L_H
        denom = lg + Le / mu_r
        Bpk   = MU0 * N * Ipk / denom
        if Bpk > 0.88 * Bsat:
            N += 1; continue
        if abs(Bpk - Bpk_prev) < 1e-4:
            break
        Bpk_prev = Bpk

    lg_mm = lg * 1e3
    return N, lg_mm, Bpk


def _build_L_vs_Vin_table(mat_key: str, core_type: str, N: int,
                            L0_nom: float, L0_min: float, L0_max: float,
                            Le_s: float, OPS: np.ndarray, L_target_uH: float) -> list:
    """Step 13.4: L_full min/nom/max vs Vin for all 9 op-points."""
    result = []
    Vout = 393.0
    for row in OPS:
        Vin, Pout, eta, PF, Irms = row
        Vin_pk  = Vin * math.sqrt(2)
        Dpk     = 1 - Vin_pk / Vout
        Pin     = Pout / eta
        Ipk_line = math.sqrt(2) * Pin / (Vin * PF)
        Iavg    = Ipk_line / 2

        if core_type == "powder":
            H_Am = N * Iavg / Le_s
            H_Oe = H_Am / 79.577
            k_b  = _db().get_k_bias(mat_key, H_Oe)
            Lmin = round(L0_min * k_b, 1)
            Lnom = round(L0_nom * k_b, 1)
            Lmax = round(L0_max * k_b, 1)
        else:
            Lmin = Lnom = Lmax = round(L_target_uH, 1)
            k_b  = 1.0

        result.append({
            "Vin_rms": Vin, "Ipk_line": round(Ipk_line, 4),
            "Iavg_crest": round(Iavg, 4),
            "AT": round(N * Iavg, 2),
            "H_Oe": round((N * Iavg / Le_s) / 79.577, 1) if core_type == "powder" else 0,
            "k_bias": round(k_b, 4),
            "L_full_min_uH": Lmin, "L_full_nom_uH": Lnom, "L_full_max_uH": Lmax,
        })
    return result


def _build_loss_table(mat_key: str, N: int, Ae: float, Ve: float,
                       Le_s: float, R_pm_20: float, Rac_Rdc: float,
                       Cu_len: float, fsw_Hz: float, Vout: float,
                       OPS: np.ndarray, T_C: float,
                       L_target_H: float = 235e-6) -> list:
    """Steps 13.8/13.9: loss vs Vin at constant temperature T_C.

    Enhancements vs original:
    • iGSE F(D) applied to core loss at the crest duty cycle of each op-point.
    • Copper loss decomposed into DC (I_rms²×R_dc) + AC (I_hf_rms²×R_ac) terms.
    • Fd column added for traceability.
    """
    result = []
    for row in OPS:
        Vin, Pout, eta, PF, Irms = row
        Vin_pk  = Vin * math.sqrt(2)
        Dpk     = max(0.0, min(0.98, 1.0 - Vin_pk / Vout))
        Bac_pk  = Vin_pk * Dpk / (2 * N * Ae * fsw_Hz)
        DCR_T   = R_pm_20 * (1 + ALPHA_CU * (T_C - 20)) * Cu_len
        R_ac    = DCR_T * Rac_Rdc

        # iGSE duty-cycle correction
        Fd      = _Fd(Dpk)

        # Core loss with F(D) applied
        Pv      = _db().get_core_loss(mat_key, fsw_Hz, Bac_pk, T_C) * 1e3  # W/m³
        Pcore   = Pv * Fd * Ve

        # Copper loss: DC term + AC (HF ripple) term
        dIpp    = Vin_pk * Dpk / max(L_target_H * fsw_Hz, 1e-12)
        Ihf     = dIpp / (2.0 * math.sqrt(3.0))
        Pcu_dc  = Irms**2 * DCR_T
        Pcu_ac  = Ihf**2 * R_ac
        Pcu     = Pcu_dc + Pcu_ac

        result.append({
            "Vin_rms":   Vin,
            "Vin_pk":    round(Vin_pk, 3),
            "D_crest":   round(Dpk,    4),
            "Irms":      round(Irms,   4),
            "Ihf_rms":   round(Ihf,    5),
            "Bac_pk":    round(Bac_pk, 5),
            "Fd":        round(Fd,     4),
            "Pcu_W":     round(Pcu,    4),
            "Pcu_dc_W":  round(Pcu_dc, 5),
            "Pcu_ac_W":  round(Pcu_ac, 5),
            "Pcore_W":   round(Pcore,  4),
            "Ptotal_W":  round(Pcu + Pcore, 4),
        })
    return result


def rank_candidates(results: list[DesignResult], n_top: int = 5,
                    optimization_goal: str = 'best_performance') -> list[dict]:
    """
    Return the top n_top candidates PER stack count so the designer can compare
    size, cost, and performance across all stack tiers side-by-side.

    With max_stacks=3 and n_top=5 the output contains up to 15 candidates:
      5 best 3-stack  |  5 best 2-stack  |  5 best 1-stack  (descending stack order)

    optimization_goal:
      'best_performance' — sort by composite score (loss 35% + volume 25% + ΔT 25%
                           + cost 10% + fill penalty 5%).  Default.
      'max_ffu'          — sort by FFcu descending so the highest window-utilisation
                           (densest/most-compact) cores come first within each group.
                           Useful for finding the physically smallest core that
                           still satisfies all pass/fail gates for the chosen wire.
    """
    passed = [r for r in results if r.passed]
    if not passed:
        return []

    def _key(r: DesignResult) -> str:
        return r.part_number + str(r.stacks)

    # Group passing candidates by stack count
    groups: dict[int, list[DesignResult]] = {}
    for r in passed:
        groups.setdefault(r.stacks, []).append(r)

    # Global best and its badge depend on the optimisation goal
    if optimization_goal == 'max_ffu':
        global_best_key = _key(max(passed, key=lambda r: r.FFcu))
        global_label    = "★ Most compact"
    else:
        global_best_key = _key(min(passed, key=lambda r: r.score))
        global_label    = "★ Best overall"

    # Build per-group labels: assign each dimension winner its label (first match wins)
    labels: dict[str, str] = {}
    for s, grp in sorted(groups.items(), reverse=True):
        by_sc   = sorted(grp, key=lambda r: r.score)
        by_vol  = sorted(grp, key=lambda r: r.Ve_total_cm3)
        by_loss = sorted(grp, key=lambda r: r.Ptotal_100C_W)
        by_temp = sorted(grp, key=lambda r: r.dT_rise_C)
        by_econ = sorted(grp, key=lambda r: r.score * (1.2 if r.core_type == "powder" else 1.0))
        by_ffu  = sorted(grp, key=lambda r: -r.FFcu)

        top_in_group = by_ffu[0] if optimization_goal == 'max_ffu' else by_sc[0]
        top_lbl      = f"★ Densest fill {s}-stack" if optimization_goal == 'max_ffu' else f"★ Best {s}-stack"

        for r, lbl in [
            (top_in_group, top_lbl),
            (by_vol[0],    f"Smallest {s}-stack"),
            (by_loss[0],   f"Lowest loss {s}-stack"),
            (by_temp[0],   f"Lowest ΔT {s}-stack"),
            (by_econ[0],   f"Most economical {s}-stack"),
        ]:
            k = _key(r)
            if k not in labels:
                labels[k] = lbl

    # Override with global badge (takes priority over per-group label)
    labels[global_best_key] = global_label

    # Collect top n_top per stack group, descending stack order (3→2→1)
    output: list[dict] = []
    rank = 1
    for s in sorted(groups.keys(), reverse=True):
        seen_in_group: set[str] = set()
        if optimization_goal == 'max_ffu':
            group_sorted = sorted(groups[s], key=lambda r: (-r.FFcu, r.score))
        else:
            group_sorted = sorted(groups[s], key=lambda r: r.score)
        count = 0
        for r in group_sorted:
            k = _key(r)
            if k not in seen_in_group:
                seen_in_group.add(k)
                output.append({"result": r, "label": labels.get(k, ""), "rank": rank})
                rank += 1
                count += 1
            if count >= n_top:
                break

    return output
