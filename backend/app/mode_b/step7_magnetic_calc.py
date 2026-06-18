"""
app/mode_b/step7_magnetic_calc.py
Step 7 — Magnetic Design Calculation Engine.

Matches reference document Steps 13.1 through 13.10 exactly.
Adds Dowell AC factor (ferrite), Rogowski fringing (ferrite),
Rth thermal network, 9-op-point stability, and Medical checks.

Phase 1 v10 accuracy improvements (2026-06-08):
  - MLT uses actual bundle OD (2×OD) instead of fixed 3.8mm allowance
  - Litz/TIW Rac/Rdc: physics-based Dowell-proximity (kSkin, kProx, kCrowd)
    replaces hardcoded 1.0 for powder toroid winding
  - Layer count computed from bore geometry; feeds proximity model
  - Two-node thermal network (core + winding) gives separate temperatures
    and hotspot estimate (×1.12 factor)
  - B(r) radial crowding: inner-bore peak = Bmax_mean × (rmean/rin)
  - Lead wire length added to total Cu length (default 150mm)
  - Inner-bore saturation check added to pass/fail

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
IGSE_C  = 1.444
IGSE_B  = 2.106
IGSE_IC = 3.5435
IGSE_K  = (2 ** IGSE_C) / ((2 * math.pi) ** (IGSE_C - 1) * IGSE_IC)

# Harmonic AC-excess factor for the triangular switching ripple (n = 1,3,5,…).
# Amplifies ONLY the AC excess (Rac/Rdc − 1) of the HF copper loss — the ripple's
# higher harmonics see a higher Rac. ≈1.213 (adopted from the simulation-agent engine).
K_HARM = 1.213


# ── v10 proximity model constants (Dowell-like, calibrated) ──────────────
# Source: pfc_sim_agent_v10.html model.copper.prox
_PROX_kSkin  = 0.50   # skin-effect coefficient (small-x Dowell approximation)
_PROX_kProx  = 0.40   # inter-layer proximity coefficient
_PROX_kCrowd = 0.25   # radial crowding amplification for inner-bore layers

# ── v10 thermal 2-node split parameters (calibrated for wound toroid) ────
# Source: pfc_sim_agent_v10.html model.cooling defaults
_THERM_sC      = 1.00   # splitCoreAmbient — relative Rca weight
_THERM_sW      = 0.90   # splitWdgAmbient  — relative Rwa weight
_THERM_couple  = 0.50   # coupleCoreWdg    — Rcw = theta_total × couple
_THERM_hotspot = 1.12   # hotspot factor over node average (interior vs surface)

# ── Default lead wire length per inductor ────────────────────────────────
_LEAD_MM_DEFAULT = 150.0   # mm total (entry + exit, 75mm each side)


def _Fd(D: float) -> float:
    """iGSE duty-cycle correction for triangular current ripple."""
    D = max(0.02, min(0.98, D))
    return IGSE_K * (D ** (1.0 - IGSE_C) + (1.0 - D) ** (1.0 - IGSE_C))


def _retention_edge(H_Oe: float) -> float:
    """Analytical DC-bias retention k(H) for EDGE powder cores (fast loop fallback)."""
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
    OD_mm:          float = 0.0
    ID_mm:          float = 0.0
    HT_mm:          float = 0.0
    Ae_single_mm2:  float = 0.0
    Wa_single_mm2:  float = 0.0
    AL_nom_nH:      float = 0.0
    AL_tol_pct:     float = 8.0
    supplier:       str   = ""

    # Turns & inductance (Step 13.3)
    N:              int   = 0
    L0_min_uH:      float = 0.0
    L0_nom_uH:      float = 0.0
    L0_max_uH:      float = 0.0
    kreq_min:       float = 0.0
    kreq_nom:       float = 0.0
    kreq_max:       float = 0.0
    AT_design:      float = 0.0
    H_Oe_design:    float = 0.0
    I_phi_avg_crest_A: float = 0.0   # crest-avg per-phase current used for the 90 V waveform
    I_dc_worst_A:   float = 0.0
    H_Oe_worst:     float = 0.0
    k_bias_worst:   float = 0.0

    # Gap (ferrite only)
    lg_mm:          float = 0.0

    # Flux density (Step 13.5)
    dBpp_T:         float = 0.0
    Bac_pk_T:       float = 0.0
    Bdc_T:          float = 0.0
    Bmin_FL_T:      float = 0.0
    Bmax_FL_T:      float = 0.0
    Bsat_at_Tcore:  float = 0.0
    sat_margin_pct: float = 0.0

    # v10 B(r) radial crowding
    crowd_axial:          float = 1.0  # rmean/rin — inner-bore crowding factor
    Bmax_inner_FL_T:      float = 0.0  # inner-bore peak flux = Bmax × crowd_axial
    sat_margin_inner_pct: float = 0.0  # saturation margin at inner bore (%)

    # Winding (Step 13.6)
    wire_designation:    str   = ""
    n_strands:           int   = 0
    d_strand_mm:         float = 0.0
    wire_OD_mm:          float = 0.0
    Cu_area_mm2:         float = 0.0
    R_per_m_20C:         float = 0.0
    FFcu:                float = 0.0
    Ku:                  float = 0.0
    wound_HT_actual_mm:  float = 0.0
    wound_OD_actual_mm:  float = 0.0
    mounting:            str   = 'horizontal'
    installed_height_mm: float = 0.0

    # v10 winding geometry (from bore/layer computation)
    bundle_OD_computed_mm: float = 0.0  # catalog OD (primary) or computed from strand geom
    layers_needed:         int   = 1    # bore layers required to fit N×n_par turns
    turns_per_layer:       int   = 0    # turns fitting in innermost bore layer
    bore_hole_r_mm:        float = 0.0  # residual bore clearance after winding (mm)
    lead_length_mm:        float = 0.0  # lead wire added to Cu length (mm)

    # Losses (Step 13.7)
    MLT_mm:         float = 0.0   # legacy MLT (3.8mm fixed — kept for report compat)
    MLT_v10_mm:     float = 0.0   # v10 MLT using 2×bundleOD
    Cu_length_m:    float = 0.0   # total Cu length including lead wire
    DCR_25C_mOhm:   float = 0.0
    DCR_100C_mOhm:  float = 0.0
    Rac_Rdc:        float = 1.0   # AC/DC resistance ratio (Dowell/proximity)
    Rac_Rdc_litz:   float = 1.0   # v10 physics-based value (same for litz/TIW)
    Pcu_25C_W:      float = 0.0
    Pcu_100C_W:     float = 0.0
    Pcu_25C_firstpass_W:  float = 0.0
    Pcu_100C_firstpass_W: float = 0.0
    P_fringing_W:   float = 0.0
    Pcore_W:        float = 0.0
    Pcore_crest_W:  float = 0.0
    Ptotal_25C_W:   float = 0.0
    Ptotal_100C_W:  float = 0.0

    # iGSE / waveform-integration results
    Fd_design:      float = 1.0
    Bdc_max_T:      float = 0.0
    Ihf_rms_A:      float = 0.0
    Pac_W:          float = 0.0
    J_A_mm2:        float = 0.0
    P_unc_lo_W:     float = 0.0
    P_unc_hi_W:     float = 0.0
    Lfull_min_at_peak_uH: float = 0.0   # min-L guarantee at worst INSTANTANEOUS peak bias
    dcm_fraction:         float = 0.0   # fraction of half-cycle in DCM (i_avg < ΔIpp/2)

    # Loss vs Vin tables
    loss_table_25C:  list = field(default_factory=list)
    loss_table_100C: list = field(default_factory=list)

    # Inductance vs Vin (powder only)
    L_vs_Vin_table:  list = field(default_factory=list)

    # Thermal — SA single-node (preserved for backward compat + pass/fail)
    T_amb_C:        float = 50.0
    T_core_C:       float = 0.0   # surface temperature from SA model
    dT_rise_C:      float = 0.0   # surface ΔT (SA model — used for pass/fail + score)
    dT_budget_C:    float = 60.0

    # v10 two-node thermal (core + winding separate)
    dT_core_C:      float = 0.0   # core node ΔT above ambient
    dT_wdg_C:       float = 0.0   # winding node ΔT above ambient
    dT_hotspot_C:   float = 0.0   # hotspot ΔT = max(dTc,dTw) × hotspotFactor
    T_hotspot_C:    float = 0.0   # absolute hotspot temperature
    Rca_KperW:      float = 0.0   # core-to-ambient thermal resistance
    Rwa_KperW:      float = 0.0   # winding-to-ambient thermal resistance
    Rcw_KperW:      float = 0.0   # core-winding coupling resistance

    # Medical
    creepage_ok:    bool  = True
    creepage_mm:    float = 0.0

    # Pass/fail
    passed:         bool  = False
    fail_reasons:   list  = field(default_factory=list)

    # Composite score (lower = better)
    score:          float = 999.0


# ── v10 helper functions ──────────────────────────────────────────────────

def _bundle_OD_mm(d_strand_mm: float, n_strands: int, n_parallel: int,
                  OD_catalog_mm: float, fill_factor: float = 0.55) -> float:
    """Bundle outer diameter in mm.
    Uses catalog OD as primary source (measured/specified by manufacturer).
    Falls back to computed value only if catalog OD is absent.
    """
    if OD_catalog_mm > 0:
        return OD_catalog_mm
    n_total = max(1, n_strands * n_parallel)
    Cu_area_m2 = n_total * math.pi * (d_strand_mm * 0.5e-3) ** 2
    return 2.0 * math.sqrt(Cu_area_m2 * 1e6 / max(fill_factor, 0.2) / math.pi)


def _compute_layers(N: int, n_parallel: int, ID_mm: float,
                    bundle_OD_mm: float) -> tuple:
    """Layer count and geometry through toroid bore (v10 formula).

    Returns (layers, turns_per_layer, bore_hole_r_mm).
    bore_hole_r_mm < 0 means winding does not fit (overfull).
    """
    if bundle_OD_mm <= 0 or ID_mm <= 0:
        return 1, N, ID_mm / 2.0
    od  = bundle_OD_mm
    rin = ID_mm / 2.0
    # Turns fitting in innermost layer (v10: tpl = floor(2π×max(rin-od/2, od)/od))
    tpl     = max(1, int(math.floor(2.0 * math.pi * max(rin - od / 2.0, od) / od)))
    layers  = max(1, math.ceil((N * n_parallel) / tpl))
    bore_r  = rin - layers * od
    return layers, tpl, bore_r


def _rac_rdc_litz(d_strand_mm: float, layers: int,
                  OD_core_mm: float, ID_core_mm: float,
                  fsw_Hz: float, T_C: float = 100.0) -> float:
    """Physics-based Rac/Rdc for litz/TIW wire (v10 Dowell-proximity model).

    Accounts for:
      - Fskin: skin effect within individual strands (kSkin = 0.50)
      - Fprox: inter-layer proximity effect (kProx = 0.40)
      - kCrowd = 0.25: radial crowding amplifies proximity for inner-bore layers

    For a single-layer winding Fprox = 1.0 (no proximity between layers).
    For litz strands (d << 2δ): Fskin ≈ 1.0; Fprox dominates at >1 layer.
    """
    rho_T  = RHO_CU_20 * (1.0 + ALPHA_CU * (T_C - 20.0))
    delta  = math.sqrt(rho_T / (math.pi * fsw_Hz * MU0))   # skin depth, m
    if delta <= 0:
        return 1.0
    x = (d_strand_mm * 1e-3) / (2.0 * delta)   # strand radius / skin depth

    # Radial crowding factor at inner bore (v10: crowdAxial = rmean/rin)
    if ID_core_mm > 0 and OD_core_mm > 0:
        rin       = ID_core_mm / 2.0
        rmean     = (ID_core_mm / 2.0 + OD_core_mm / 2.0) / 2.0
        crowd_ax  = rmean / max(rin, 1e-9)
    else:
        crowd_ax  = 1.0

    Fskin = 1.0 + _PROX_kSkin * x ** 2
    Fprox = 1.0 + _PROX_kProx * max(layers - 1, 0) * x ** 2 * (
        1.0 + _PROX_kCrowd * (crowd_ax - 1.0))
    return max(1.0, Fskin * Fprox)


def _two_node_thermal(wound_OD_mm: float, wound_HT_mm: float,
                       hole_ID_mm: float, Pcore_W: float, Pcu_W: float,
                       T_amb_C: float) -> tuple:
    """v10 two-node thermal network for wound toroid.

    Derives Rca/Rwa from the calibrated SA power-law (preserves empirical baseline),
    splits by _THERM_sC/_THERM_sW fractions, couples via Rcw = theta × _THERM_couple.

    Returns (dT_core_C, dT_wdg_C, dT_hotspot_C, Rca_KperW, Rwa_KperW, Rcw_KperW).
    dT_hotspot = max(dTc, dTw) × _THERM_hotspot (1.12) accounts for interior gradient.
    """
    Ptot = Pcore_W + Pcu_W
    if Ptot < 1e-6:
        return 0.0, 0.0, 0.0, 1e6, 1e6, 1e6

    # Total theta from calibrated SA formula
    dT_sa = _thermal_dT_SA(wound_OD_mm, wound_HT_mm, hole_ID_mm, Ptot)
    theta  = dT_sa / Ptot     # K/W total

    # Split by surface fractions (v10 defaults)
    sC  = _THERM_sC; sW = _THERM_sW
    Rca = theta * (sC + sW) / sC           # core-to-ambient (higher R — less exposed area)
    Rwa = theta * (sC + sW) / sW           # winding-to-ambient (lower R — outer surface)
    Rcw = max(theta * _THERM_couple, 1e-3)  # core-winding coupling

    # 2-node KCL solve:
    #   dTc × (1/Rca + 1/Rcw) − dTw × (1/Rcw) = Pcore
    #   dTw × (1/Rwa + 1/Rcw) − dTc × (1/Rcw) = Pcu
    a11 = 1.0 / Rca + 1.0 / Rcw
    a12 = -1.0 / Rcw
    a22 = 1.0 / Rwa + 1.0 / Rcw
    det = a11 * a22 - a12 * a12    # a12 = a21 (symmetric)
    if abs(det) < 1e-20:
        det = 1e-20
    dTc = max(0.0, ( Pcore_W * a22 + Pcu_W  / Rcw) / det)
    dTw = max(0.0, ( Pcu_W   * a11 + Pcore_W / Rcw) / det)

    dT_hotspot = max(dTc, dTw) * _THERM_hotspot
    return dTc, dTw, dT_hotspot, Rca, Rwa, Rcw


# ── MLT ───────────────────────────────────────────────────────────────────

def _compute_MLT(core: dict, stacks: int = 1, wire_OD_mm: float = 0.0) -> float:
    """Mean length per turn (mm).

    Toroid (v10 formula when wire_OD_mm > 0):
      MLT = 2 × (coreW + HT_total) + 2 × wire_OD_mm
    Toroid (legacy, wire_OD_mm = 0):
      MLT = 2 × (coreW + HT_total) + 3.8  (fixed routing allowance)
    ETD/EE: use catalog MLT_mm value.
    """
    if "ID_mm" in core and float(core.get("ID_mm", 0)) > 0:
        OD     = float(core["OD_mm"])
        ID     = float(core["ID_mm"])
        HT     = float(core["HT_mm"])
        coreW  = (OD - ID) / 2.0
        build  = (2.0 * wire_OD_mm) if wire_OD_mm > 0 else 3.8
        return 2.0 * (coreW + HT * stacks) + build
    return float(core.get("MLT_mm", 100.0))


# ── Thermal helpers ───────────────────────────────────────────────────────

def _thermal_dT_SA(wound_OD_mm: float, wound_HT_mm: float,
                   hole_ID_mm: float, P_total_W: float) -> float:
    """ΔT from wound-surface-area power law — matches JS V5.1 formula exactly.

    SA [cm²] = [π·OD_w·OH + (π/2)·(OD_w² − hole²) + π·hole·OH] / 100
    ΔT [°C]  = (P_total [W] × 1000 / SA [cm²]) ^ 0.833
    """
    od   = wound_OD_mm
    oh   = wound_HT_mm
    hole = max(0.5, hole_ID_mm)
    SA   = (math.pi * od * oh
            + 2 * (math.pi / 4) * (od**2 - hole**2)
            + math.pi * hole * oh) / 100.0
    SA   = max(SA, 1.0)
    return (P_total_W * 1000.0 / SA) ** 0.833


def _thermal_Rth(core: dict, stacks: int = 1, h_forced: float = 17.5) -> float:
    """Kept for ETD/ferrite cores. Toroid path uses _thermal_dT_SA."""
    if "ID_mm" in core and float(core.get("ID_mm", 0)) > 0:
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


# ── 360-point half-cycle waveform integration ────────────────────────────

def _half_cycle_averages(
    material_key: str,
    core_type: str,
    N: int,
    Ae_m2: float,
    Ve_m3: float,
    Le_s: float,
    L0_nom_H: float,
    Icrest_A: float,
    Vout_V: float,
    Vin_pk_V: float,
    fsw_Hz: float,
    Rdc: float,
    Rac: float,
    T_core_C: float = 100.0,
    f_line_Hz: float = 60.0,
    M: int = 360,
    return_series: bool = False,
) -> dict:
    """360-point half-cycle waveform integration matching JS V5.1 compute() loop."""
    pCoreAcc = 0.0
    i2       = 0.0
    r2       = 0.0
    BdcMax   = 0.0
    BmaxPk   = 0.0
    pCorePk  = 0.0
    pCuPk    = 0.0
    pTotPk   = 0.0
    dcm_count = 0                      # half-cycle points where i_avg < ΔIpp/2 (DCM)
    series_theta = [] if return_series else None
    series_Bac   = [] if return_series else None
    series_Pcore = [] if return_series else None
    series_t_ms  = [] if return_series else None
    series_Vin   = [] if return_series else None
    series_D     = [] if return_series else None
    series_Iavg  = [] if return_series else None
    series_H     = [] if return_series else None
    series_Bdc   = [] if return_series else None
    series_Bmax  = [] if return_series else None
    series_Ihf   = [] if return_series else None
    series_Pcu   = [] if return_series else None
    series_Ptot  = [] if return_series else None

    for n in range(M):
        theta = (n + 0.5) * math.pi / M
        s     = math.sin(theta)
        Vin   = Vin_pk_V * s
        D     = max(0.0, min(0.98, 1.0 - Vin / Vout_V))
        Iavg  = Icrest_A * s

        if core_type == "powder":
            Le_cm = Le_s * 100.0
            H_Oe  = 0.4 * math.pi * N * Iavg / Le_cm
            # Material-specific DC-bias curve from the MagneticsDB for the SELECTED material —
            # never an EDGE-hardcoded fallback. (Fixes wrong k(H)/Bmax for non-EDGE materials
            # and makes step7's biased flux match the field-engine, which reads the same DB curve.)
            k_b   = _db().get_k_bias(material_key, H_Oe)
        else:
            k_b = 1.0
        Lth = max(L0_nom_H * k_b, 1e-9)

        dBpp  = Vin * D / (N * Ae_m2 * fsw_Hz)
        BacPk = dBpp / 2.0
        Bdc   = Lth * Iavg / (N * Ae_m2)
        Bmx   = Bdc + BacPk

        Fd      = _Fd(D)
        Pv_Wm3  = _db().get_core_loss(material_key, fsw_Hz, BacPk, T_core_C) * 1e3
        Pcore_i = Pv_Wm3 * Fd * Ve_m3

        dIpp  = Vin * D / max(Lth * fsw_Hz, 1e-12)
        Ihf   = dIpp / (2.0 * math.sqrt(3.0))
        if Iavg < dIpp / 2.0:          # inductor current rings to zero → DCM at this angle
            dcm_count += 1

        # HF copper loss: DC-resistance part + AC excess (Rac−Rdc) amplified by the
        # triangular-ripple harmonic factor K_HARM (K_HARM=1 ⇒ original Rac·Ihf²).
        Pcu_i  = Rdc * Iavg ** 2 + Ihf ** 2 * (Rdc + (Rac - Rdc) * K_HARM)
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
            series_t_ms.append(theta / math.pi * 1000.0 / (2.0 * f_line_Hz))
            series_Vin.append(Vin)
            series_D.append(D)
            series_Iavg.append(Iavg)
            series_H.append(0.4 * math.pi * N * Iavg / (Le_s * 100.0))
            series_Bdc.append(Bdc)
            series_Bmax.append(Bmx)
            series_Ihf.append(Ihf)
            series_Pcu.append(Pcu_i)
            series_Ptot.append(Ptot_i)

    Pcore_avg = pCoreAcc / M
    Irms      = math.sqrt(i2 / M)
    IhfRms    = math.sqrt(r2 / M)
    Pac       = IhfRms ** 2 * (Rdc + (Rac - Rdc) * K_HARM)
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
        "dcm_fraction": dcm_count / M,
        **({"theta_rad": series_theta, "Bac_pk_T_series": series_Bac,
            "Pcore_W_series": series_Pcore,
            "t_ms": series_t_ms, "Vin": series_Vin, "D": series_D, "Iavg": series_Iavg,
            "H_Oe": series_H, "Bdc": series_Bdc, "Bac_pk": series_Bac, "Bmax": series_Bmax,
            "Ihf": series_Ihf, "Pcore": series_Pcore, "Pcu": series_Pcu, "Ptot": series_Ptot}
           if return_series else {}),
    }


# ── Main design function ──────────────────────────────────────────────────

def design_one_core(
    core: dict,
    material_key: str,
    L_target_H: float,
    Ipk_A: float,
    Irms_A: float,
    IL_HF_rms_A: float,
    dIL_pp_A: float,
    fsw_Hz: float,
    wire: dict,
    N_phases: int,
    OPS: np.ndarray,
    T_amb_C: float = 50.0,
    dT_budget_C: float = 60.0,
    J_target: float = 5.0,
    app_class: str = "Industrial",
    h_conv: float = 17.5,
    FFcu_limit: float = 0.40,
    mounting:   str   = 'horizontal',
    lead_length_mm: float = _LEAD_MM_DEFAULT,
) -> DesignResult:
    """
    Full Step 13 calculation for one (core, material, wire) combination.

    Phase 1 v10 improvements applied:
      - v10 MLT (2×bundleOD) replaces fixed 3.8mm build allowance
      - Lead wire added to total Cu length (default 150mm)
      - Litz/TIW Rac/Rdc from physics-based proximity model (not hardcoded 1.0)
      - Layer count computed from bore geometry; feeds proximity model
      - Two-node thermal network gives dT_core, dT_wdg, dT_hotspot
      - B(r) radial crowding: Bmax_inner = Bmax × (rmean/rin)
      - Inner-bore saturation check added to pass/fail
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
    res.OD_mm         = float(core.get("OD_mm", 0.0))
    res.ID_mm         = float(core.get("ID_mm", 0.0))
    res.HT_mm         = float(core.get("HT_mm", 0.0))
    res.Ae_single_mm2 = float(core.get("Ae_single_mm2",
                              float(core["Ae_total_mm2"]) / max(int(core.get("stacks", 1)), 1)))
    res.Wa_single_mm2 = float(core.get("Wa_mm2",
                              float(core.get("Wa_total_mm2", 0)) / max(int(core.get("stacks", 1)), 1)))
    _stk   = max(int(core.get("stacks", 1)), 1)
    _al_t  = float(core.get("AL_nom_total", core.get("AL_nom_nH", 75)))
    res.AL_nom_nH  = round(_al_t / _stk, 2)
    res.AL_tol_pct = float(core.get("AL_tolerance_pct", 8))
    res.supplier   = str(core.get("supplier", ""))

    Ae   = res.Ae_total_mm2  * 1e-6
    Wa   = res.Wa_total_mm2  * 1e-6
    Ve   = res.Ve_total_cm3  * 1e-6
    Le_s = res.Le_single_mm  * 1e-3

    Vout_V = 393.0
    I_phi_avg_crest = max(Ipk_A - dIL_pp_A / 2.0, Irms_A * 0.9)
    res.I_phi_avg_crest_A = round(I_phi_avg_crest, 4)

    # ── Step 13.3: Turns ────────────────────────────────────────────────────
    if res.core_type == "powder":
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
        L0_min = L0_nom = L0_max = L_target_H * 1e6
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

    # ── Step 13.4: Inductance vs Vin ─────────────────────────────────────────
    res.L_vs_Vin_table = _build_L_vs_Vin_table(
        material_key, res.core_type, N, L0_nom * 1e6, L0_min * 1e6, L0_max * 1e6,
        Le_s, OPS, L_target_H * 1e6)

    # ── Step 13.5: Flux density ──────────────────────────────────────────────
    Vin_pk90 = OPS[0, 0] * math.sqrt(2)
    Dpk90    = 1 - Vin_pk90 / Vout_V
    dBpp     = Vin_pk90 * Dpk90 / (N * Ae * fsw_Hz)
    Bac_pk   = dBpp / 2

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

    # Radial crowding factor (v10: crowdAxial = rmean/rin)
    if res.ID_mm > 0 and res.OD_mm > 0:
        _rin      = res.ID_mm / 2.0
        _rmean    = (res.ID_mm / 2.0 + res.OD_mm / 2.0) / 2.0
        crowd_ax  = _rmean / max(_rin, 1e-9)
    else:
        crowd_ax  = 1.0
    res.crowd_axial = round(crowd_ax, 4)

    # ── Step 13.6: Winding ───────────────────────────────────────────────────
    # Extract wire parameters first (needed for v10 MLT and layer-count geometry)
    d_s_mm        = float(wire.get("strand_dia_mm", 0.1))
    n_str         = int(wire.get("strands", 200))
    OD_mm         = float(wire.get("OD_mm", 2.0))
    Cu_area       = float(wire.get("Cu_area_mm2", 1.0))
    R_per_m       = float(wire.get("R_per_m_20C_ohm", 0.01))
    designation   = str(wire.get("designation", ""))
    wire_type_str = str(wire.get("type", "litz")).lower()
    n_parallel    = int(wire.get("n_parallel", 1) or 1)

    # Bundle OD: catalog value is authoritative (measured); computation is fallback
    bundleOD = _bundle_OD_mm(d_s_mm, n_str, n_parallel, OD_mm)

    # Layer count through toroid bore (v10)
    layers, tpl, bore_r = _compute_layers(N, n_parallel, res.ID_mm, bundleOD)
    _hole_ID = max(0.5, bore_r * 2)   # residual bore diameter mm

    # v10 MLT: 2*(coreW + HT*stacks) + 2*bundleOD  (vs fixed 3.8mm)
    MLT_old = _compute_MLT(core, res.stacks)              # legacy (3.8mm)
    MLT_v10 = _compute_MLT(core, res.stacks, bundleOD)   # v10 formula
    MLT = MLT_v10

    # Total Cu length: N turns × MLT + lead wire (entry + exit)
    Cu_len = N * MLT / 1000.0 + lead_length_mm / 1000.0   # m

    # Fill factor computation (Wa_bore = bore area of ONE core — invariant with stacks)
    Wa_bore   = res.Wa_single_mm2
    Acu_total = N * Cu_area
    FFcu      = Acu_total / Wa_bore

    kapton_factor = 1.0 if (res.core_type == "powder") else (
                    0.94 if app_class == "Medical" else 1.0)
    Wa_avail = Wa_bore * kapton_factor

    if res.core_type == "powder":
        A_bundle_ins = math.pi / 4 * OD_mm ** 2
        Ku = N * n_parallel * A_bundle_ins / Wa_avail
    else:
        d_bundle = d_s_mm * 1.05 * math.sqrt(n_str * n_parallel) * 1.20
        A_bundle = math.pi / 4 * d_bundle ** 2
        Ku       = N * A_bundle / Wa_avail

    res.wire_designation      = designation
    res.n_strands             = n_str
    res.d_strand_mm           = d_s_mm
    res.wire_OD_mm            = OD_mm
    res.Cu_area_mm2           = round(Cu_area, 4)
    res.R_per_m_20C           = round(R_per_m / n_parallel, 8)
    res.MLT_mm                = round(MLT_old, 4)      # legacy (3.8mm) — kept for report compat
    res.MLT_v10_mm            = round(MLT_v10, 4)      # v10 (2×bundleOD)
    res.Cu_length_m           = round(Cu_len, 6)
    res.lead_length_mm        = lead_length_mm
    res.FFcu                  = round(FFcu, 4)
    res.Ku                    = round(Ku, 4)
    res.bundle_OD_computed_mm = round(bundleOD, 3)
    res.layers_needed         = layers
    res.turns_per_layer       = tpl
    res.bore_hole_r_mm        = round(max(0.0, bore_r), 2)

    # Actual assembled dimensions
    _HT_stack_bare        = res.HT_mm * res.stacks + max(0, res.stacks - 1) * 1.5
    res.wound_HT_actual_mm = round(_HT_stack_bare + 2 * OD_mm, 1)
    _wound_OD_cat         = float(core.get("wound_OD_mm") or (res.OD_mm + 8.0))
    _ref_build            = (_wound_OD_cat - res.OD_mm) / 2.0
    _scale                = (FFcu / 0.40) if FFcu > 0 else 1.0
    res.wound_OD_actual_mm = round(res.OD_mm + 2 * _ref_build * _scale, 1)

    res.mounting            = mounting
    res.installed_height_mm = (
        res.wound_HT_actual_mm if mounting == 'horizontal'
        else res.wound_OD_actual_mm
    )

    # ── Step 13.7: Losses ─────────────────────────────────────────────────────
    R_pm_20 = res.R_per_m_20C
    DCR_25  = R_pm_20 * (1 + ALPHA_CU * (25 - 20)) * Cu_len
    DCR_100 = R_pm_20 * (1 + ALPHA_CU * (100 - 20)) * Cu_len

    res.DCR_25C_mOhm  = round(DCR_25  * 1e3, 4)
    res.DCR_100C_mOhm = round(DCR_100 * 1e3, 4)

    # Rac/Rdc: physics-based for all winding types
    if res.core_type == "ferrite":
        # Ferrite ETD: Dowell factor (unchanged)
        dowell  = compute_dowell_factor(n_str, d_s_mm, N, res.Wa_total_mm2, fsw_Hz, 100.0)
        Rac_Rdc = dowell["Rac_Rdc"]
    else:
        # Powder toroid — v10 physics-based proximity model
        if wire_type_str in ("solid", "solid-enamel"):
            # Solid/enamel: exact Bessel skin-effect formula
            rho_100   = RHO_CU_20 * (1.0 + ALPHA_CU * (100.0 - 20.0))
            delta_mm  = math.sqrt(rho_100 / (math.pi * fsw_Hz * MU0)) * 1e3
            Rac_Rdc   = max(1.0, _db()._rac_rdc_solid(d_s_mm, delta_mm))
        else:
            # Litz / TIW: skin + inter-layer proximity (v10 Dowell-like)
            Rac_Rdc = _rac_rdc_litz(d_s_mm, layers, res.OD_mm, res.ID_mm, fsw_Hz, 100.0)

    res.Rac_Rdc      = round(Rac_Rdc, 4)
    res.Rac_Rdc_litz = round(Rac_Rdc, 4)   # v10 alias; same value

    # First-pass Pcu at reference Irms (90 Vac) — stored for report
    IL_rms_ref    = float(OPS[0, 4])
    Vin_pk90_loss = OPS[0, 0] * math.sqrt(2)
    Dpk90_loss    = max(0.0, 1.0 - Vin_pk90_loss / 393.0)
    dIpp_90       = Vin_pk90_loss * Dpk90_loss / max(L_target_H * fsw_Hz, 1e-12)
    Ihf_ref       = dIpp_90 / (2.0 * math.sqrt(3.0))

    res.Pcu_25C_W  = round(IL_rms_ref**2 * DCR_25  + Ihf_ref**2 * DCR_25  * Rac_Rdc, 4)
    res.Pcu_100C_W = round(IL_rms_ref**2 * DCR_100 + Ihf_ref**2 * DCR_100 * Rac_Rdc, 4)
    res.Pcu_25C_firstpass_W  = res.Pcu_25C_W
    res.Pcu_100C_firstpass_W = res.Pcu_100C_W

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

    # ── Thermal convergence loop (SA single-node, used for dT_rise_C pass/fail) ──
    T_core = T_amb_C + 0.5 * dT_budget_C
    _is_toroid = "ID_mm" in core and float(core.get("ID_mm", 0)) > 0

    if not _is_toroid:
        Rth = _thermal_Rth(core, res.stacks, h_conv)

    for _ in range(10):
        Pv    = _db().get_core_loss(material_key, fsw_Hz, Bac_pk, T_core) * 1e3
        Pcore = Pv * Fd_crest * Ve
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

    # ── 360-point half-cycle waveform integration ─────────────────────────────
    Rdc_Tc  = R_pm_20 * (1 + ALPHA_CU * (T_core - 20)) * Cu_len
    Rac_Tc  = Rdc_Tc * Rac_Rdc
    L0_nom_H = (res.AL_nom_nH * res.stacks) * 1e-9 * N**2

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
        f_line_Hz    = 60.0,
        M            = 360,
    )

    Pcore_avg = wf["Pcore_avg_W"]
    Pcu_avg   = wf["Pcu_avg_W"]

    res.T_core_C      = round(T_core, 2)
    res.dT_rise_C     = round(T_core - T_amb_C, 2)   # SA surface ΔT (pass/fail criterion)
    res.Pcore_crest_W = round(Pcore, 4)
    res.Pcore_W       = round(Pcore_avg, 4)
    res.Ihf_rms_A     = round(wf["IhfRms_A"], 5)
    res.Pac_W         = round(wf["Pac_W"], 5)
    res.Bdc_max_T     = round(wf["BdcMax_T"], 6)
    res.Bmax_FL_T     = round(wf["Bmax_T"], 6)

    Cu_per_cond = float(wire.get("Cu_area_mm2", 1.0)) / max(n_parallel, 1)
    res.J_A_mm2 = round(wf["Irms_A"] / max(Cu_per_cond, 0.001), 3)

    # HF copper loss: AC excess (Rac/Rdc − 1) amplified by the harmonic factor K_HARM
    _hf = (1.0 + (Rac_Rdc - 1.0) * K_HARM)
    Pcu_final_100 = wf["Irms_A"]**2 * DCR_100 + wf["IhfRms_A"]**2 * DCR_100 * _hf
    Pcu_final_25  = wf["Irms_A"]**2 * DCR_25  + wf["IhfRms_A"]**2 * DCR_25  * _hf
    res.dcm_fraction = round(wf.get("dcm_fraction", 0.0), 4)

    res.Ptotal_25C_W  = round(Pcu_final_25  + Pcore_avg + res.P_fringing_W, 4)
    res.Ptotal_100C_W = round(Pcu_final_100 + Pcore_avg + res.P_fringing_W, 4)
    res.P_unc_lo_W = round(Pcu_final_100 + 1.05 * Pcore_avg, 4)
    res.P_unc_hi_W = round(Pcu_final_100 + 1.20 * Pcore_avg, 4)

    # Min-L guarantee at the worst INSTANTANEOUS peak bias (i_avg,crest + ΔIpp/2) using the
    # SELECTED material's DB curve — more conservative than crest-average bias. Informational:
    # turns selection / pass-fail are unchanged (adopted from the simulation-agent engine).
    if res.core_type == "powder":
        try:
            _ipk = I_phi_avg_crest + dIL_pp_A / 2.0
            _Hpk = (N * _ipk / Le_s) / 79.577
            res.Lfull_min_at_peak_uH = round(L0_min * _db().get_k_bias(material_key, _Hpk) * 1e6, 3)
        except Exception:
            res.Lfull_min_at_peak_uH = res.L0_min_uH
    else:
        res.Lfull_min_at_peak_uH = res.L0_min_uH

    res.Pcu_25C_W  = round(Pcu_final_25,  4)
    res.Pcu_100C_W = round(Pcu_final_100, 4)

    # Saturation margin at T_core
    res.Bsat_at_Tcore  = round(_db().get_Bsat(material_key, T_core), 4)
    res.sat_margin_pct = round(
        (res.Bsat_at_Tcore - res.Bmax_FL_T) / res.Bsat_at_Tcore * 100, 1)

    # v10 inner-bore B(r) crowding: peak inner-bore flux = Bmax × (rmean/rin)
    res.Bmax_inner_FL_T   = round(res.Bmax_FL_T * crowd_ax, 6)
    res.sat_margin_inner_pct = round(
        (res.Bsat_at_Tcore - res.Bmax_inner_FL_T) / max(res.Bsat_at_Tcore, 1e-9) * 100, 1)

    # ── v10 Two-node thermal (core + winding separate temperatures) ───────────
    # Uses waveform-averaged losses for maximum accuracy
    if _is_toroid:
        dT_c, dT_w, dT_hs, Rca, Rwa, Rcw = _two_node_thermal(
            res.wound_OD_actual_mm, res.wound_HT_actual_mm, _hole_ID,
            Pcore_avg, Pcu_final_100, T_amb_C)
        res.dT_core_C    = round(dT_c,  2)
        res.dT_wdg_C     = round(dT_w,  2)
        res.dT_hotspot_C = round(dT_hs, 2)
        res.T_hotspot_C  = round(T_amb_C + dT_hs, 2)
        res.Rca_KperW    = round(Rca, 4)
        res.Rwa_KperW    = round(Rwa, 4)
        res.Rcw_KperW    = round(Rcw, 4)
    else:
        # ETD: single-node as before (2-node needs toroid geometry)
        res.dT_core_C    = res.dT_rise_C
        res.dT_wdg_C     = res.dT_rise_C
        res.dT_hotspot_C = round(res.dT_rise_C * _THERM_hotspot, 2)
        res.T_hotspot_C  = round(T_amb_C + res.dT_hotspot_C, 2)

    # Loss vs Vin sweeps
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
            res.creepage_ok = True
        else:
            res.creepage_ok = creepage >= 6.0
            if not res.creepage_ok:
                res.fail_reasons.append(
                    f"Creepage {creepage:.0f}mm < 6mm (IEC 60601-1 Medical). "
                    "Use extended-flange bobbin.")

    # ── Pass/fail checks ──────────────────────────────────────────────────────
    if res.core_type == "powder":
        ku_lim = 0.75
    else:
        ku_lim = min(FFcu_limit + 0.05, 0.50)

    if FFcu > FFcu_limit:
        res.fail_reasons.append(
            f"FFcu={FFcu:.3f} ({FFcu*100:.1f}%) exceeds bare-copper fill limit {FFcu_limit:.2f}.")
    if res.Ku > ku_lim:
        res.fail_reasons.append(
            f"Ku={res.Ku:.3f} ({res.Ku*100:.1f}% insulated) exceeds winding fit limit {ku_lim:.2f}.")
    if res.sat_margin_pct < 15.0:
        res.fail_reasons.append(f"Saturation margin {res.sat_margin_pct:.1f}% < 15%.")
    # v10 inner-bore saturation check (radial crowding): fails if inner bore saturates
    if _is_toroid and res.Bmax_inner_FL_T >= res.Bsat_at_Tcore:
        res.fail_reasons.append(
            f"Inner-bore flux saturates: Bmax_inner={res.Bmax_inner_FL_T:.3f}T "
            f">= Bsat={res.Bsat_at_Tcore:.3f}T "
            f"(crowd×{res.crowd_axial:.2f} at rin={res.ID_mm/2:.1f}mm).")
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

    N = max(1, math.ceil(math.sqrt(L_H / AL_nom)))
    for _ in range(40):
        H_Am  = N * I_dc / Le_s
        H_Oe  = H_Am / 79.577
        k_b   = _db().get_k_bias(mat_key, H_Oe)
        L_full_min = N**2 * AL_min * k_b
        if L_full_min >= L_H * 0.85:
            break
        N += 1

    L0_min = N**2 * AL_min
    L0_nom = N**2 * AL_nom
    L0_max = N**2 * AL_max

    H_Am  = N * I_dc / Le_s
    H_Oe  = H_Am / 79.577
    k_b   = _db().get_k_bias(mat_key, H_Oe)

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
    """Steps 13.8/13.9: loss vs Vin at constant temperature T_C."""
    result = []
    for row in OPS:
        Vin, Pout, eta, PF, Irms = row
        Vin_pk  = Vin * math.sqrt(2)
        Dpk     = max(0.0, min(0.98, 1.0 - Vin_pk / Vout))
        Bac_pk  = Vin_pk * Dpk / (2 * N * Ae * fsw_Hz)
        DCR_T   = R_pm_20 * (1 + ALPHA_CU * (T_C - 20)) * Cu_len
        R_ac    = DCR_T * Rac_Rdc
        Fd      = _Fd(Dpk)
        Pv      = _db().get_core_loss(mat_key, fsw_Hz, Bac_pk, T_C) * 1e3
        Pcore   = Pv * Fd * Ve
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
    Return the top n_top candidates PER stack count.

    optimization_goal:
      'best_performance' — sort by composite score (loss/volume/ΔT/cost/fill).
      'max_ffu'          — sort by FFcu descending (densest/most-compact first).
    """
    passed = [r for r in results if r.passed]
    if not passed:
        return []

    def _key(r: DesignResult) -> str:
        return r.part_number + str(r.stacks)

    groups: dict[int, list[DesignResult]] = {}
    for r in passed:
        groups.setdefault(r.stacks, []).append(r)

    if optimization_goal == 'max_ffu':
        global_best_key = _key(max(passed, key=lambda r: r.FFcu))
        global_label    = "★ Most compact"
    else:
        global_best_key = _key(min(passed, key=lambda r: r.score))
        global_label    = "★ Best overall"

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

    labels[global_best_key] = global_label

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


# ── Phase B: step7 "view contract" — single source every screen renders ──────────
def build_view_contract(result: dict, state: dict) -> dict:
    """Authoritative render payload for Result / Review / Simulation screens.

    Returns step7's scalars + the design-point (90 Vac) per-θ waveforms + the 9-point
    sweep, ALL from step7's own physics (re-runs `_half_cycle_averages` with the stored
    design so the arrays carry the exact converged numbers). Screens RENDER this; they do
    not recompute — guaranteeing identical values across all three. Additive/read-only.
    """
    R   = result or {}
    tsi = (state or {}).get("topology_specific_inputs", {}) or {}
    fsw = float(tsi.get("recommended_frequency_hz", 70000) or 70000)
    Vout = 393.0                                   # matches step7 design_one_core internal Vout
    N        = int(R.get("N", 0) or 0)
    core_type= str(R.get("core_type", "powder")).lower()
    mat_key  = str(R.get("material_key", ""))
    Ae_m2    = float(R.get("Ae_total_mm2", 0) or 0) * 1e-6
    Ve_m3    = float(R.get("Ve_total_cm3", 0) or 0) * 1e-6
    Le_s     = float(R.get("Le_single_mm", 0) or 0) * 1e-3
    L0_nom_H = float(R.get("L0_nom_uH", 0) or 0) * 1e-6
    Icrest   = float(R.get("I_phi_avg_crest_A", 0) or 0)
    T_core   = float(R.get("T_core_C", 0) or 0) or 100.0
    DCR25    = float(R.get("DCR_25C_mOhm", 0) or 0) * 1e-3
    Rac_Rdc  = float(R.get("Rac_Rdc", 1.0) or 1.0)
    # All view-contract waveforms use the 100 °C copper resistance so their Pcu equals the
    # reported result.Pcu_100C_W (the basis the readouts and anchored sweep use). Core loss is
    # temperature-independent; the studios apply their own T scaling for exploration.
    Rdc_100 = float(R.get("DCR_100C_mOhm", 0) or 0) * 1e-3
    Rac_100 = Rdc_100 * Rac_Rdc

    waveform = {}
    if N > 0 and Ae_m2 > 0 and Le_s > 0 and Icrest > 0:
        wf = _half_cycle_averages(
            material_key=mat_key, core_type=core_type, N=N, Ae_m2=Ae_m2, Ve_m3=Ve_m3,
            Le_s=Le_s, L0_nom_H=L0_nom_H, Icrest_A=Icrest, Vout_V=Vout,
            Vin_pk_V=90.0 * math.sqrt(2), fsw_Hz=fsw, Rdc=Rdc_100, Rac=Rac_100,
            T_core_C=T_core, f_line_Hz=60.0, M=360, return_series=True)
        waveform = {k: wf[k] for k in
                    ("t_ms", "Vin", "D", "Iavg", "H_Oe", "Bdc", "Bac_pk", "Bmax",
                     "Ihf", "Pcore", "Pcu", "Ptot") if k in wf}

    # 9-point sweep: join the loss table with the L-vs-Vin table (both already in result)
    loss = R.get("loss_table_100C", []) or []
    lvt  = R.get("L_vs_Vin_table", []) or []
    def _lv(vin):
        for r in lvt:
            if abs(float(r.get("Vin_rms", -1)) - vin) < 0.5:
                return r
        return {}
    # design-Vin reference crest (the L-vs-Vin sweep current at 90 V) — used to anchor the per-Vin
    # waveform crest to I_phi_avg_crest so peaks equal H_Oe_design / Bmax_FL_T at the design corner.
    _ref_ic = next((float(r.get("Iavg_crest", 0) or 0) for r in lvt
                    if abs(float(r.get("Vin_rms", 0) or 0) - 90) < 1.0), 0.0)
    # Anchor the per-Vin loss table to the authoritative DESIGN values at 90 V — the SAME anchor
    # the Review page applies — so the sweep's anchored loss equals Result/Review at every Vin.
    _lt90 = next((r for r in loss if abs(float(r.get("Vin_rms", 0) or 0) - 90) < 1.0), {})
    _pc90 = float(_lt90.get("Pcore_W", 0) or 0); _pu90 = float(_lt90.get("Pcu_W", 0) or 0)
    _pcoreAnc = (float(R.get("Pcore_W", 0) or 0) / _pc90) if _pc90 > 0 else 1.0
    _pcuAnc   = (float(R.get("Pcu_100C_W", 0) or 0) / _pu90) if _pu90 > 0 else 1.0
    sweep = []
    for row in loss:
        vin = float(row.get("Vin_rms", 0)); lv = _lv(vin)
        _pc = float(row.get("Pcore_W", 0) or 0); _pu = float(row.get("Pcu_W", 0) or 0)
        sweep.append(dict(
            Vin=vin, Icrest=float(lv.get("Iavg_crest", 0) or 0),
            Lfull=float(lv.get("L_full_nom_uH", 0) or 0), H_Oe=float(lv.get("H_Oe", 0) or 0),
            k_bias=float(lv.get("k_bias", 1) or 1), Bac=float(row.get("Bac_pk", 0) or 0),
            Pcore=_pc, Pcu=_pu, Ptot=float(row.get("Ptotal_W", 0) or 0),
            Pcore_anc=round(_pc * _pcoreAnc, 4), Pcu_anc=round(_pu * _pcuAnc, 4),
            Ptot_anc=round(_pc * _pcoreAnc + _pu * _pcuAnc, 4)))

    # Per-Vin waveforms for the studio's Vin EXPLORER — step7-exact at each OPS point
    # (M=180 keeps the payload light; the studio interpolates between OPS Vins).
    waveforms_by_vin = {}
    if N > 0 and Ae_m2 > 0 and Le_s > 0:
        for lv in lvt:
            vin = float(lv.get("Vin_rms", 0) or 0)
            ic  = float(lv.get("Iavg_crest", 0) or 0)
            if vin <= 0 or ic <= 0:
                continue
            # anchor to I_phi_avg_crest (so the design corner equals the readouts) while following
            # the per-Vin sweep-current shape; use the 100 °C copper resistance for Pcu consistency.
            ic = Icrest * (ic / _ref_ic) if (Icrest > 0 and _ref_ic > 0) else ic
            w = _half_cycle_averages(
                material_key=mat_key, core_type=core_type, N=N, Ae_m2=Ae_m2, Ve_m3=Ve_m3,
                Le_s=Le_s, L0_nom_H=L0_nom_H, Icrest_A=ic, Vout_V=Vout,
                Vin_pk_V=vin * math.sqrt(2), fsw_Hz=fsw, Rdc=Rdc_100, Rac=Rac_100,
                T_core_C=T_core, f_line_Hz=60.0, M=180, return_series=True)
            waveforms_by_vin[str(int(round(vin)))] = {k: w[k] for k in
                ("t_ms", "Vin", "D", "Iavg", "H_Oe", "Bdc", "Bac_pk", "Bmax",
                 "Ihf", "Pcore", "Pcu", "Ptot") if k in w}

    scalar_keys = ("N", "stacks", "part_number", "material_key", "L0_nom_uH", "L_full_load_uH",
                   "Bmax_FL_T", "Bmax_inner_FL_T", "Bac_pk_T", "H_Oe_design", "DCR_100C_mOhm",
                   "Pcore_W", "Pcu_100C_W", "Ptotal_100C_W", "dT_rise_C", "dT_hotspot_C",
                   "T_hotspot_C", "J_A_mm2", "FFcu", "Ku", "sat_margin_pct", "Rac_Rdc",
                   "Lfull_min_at_peak_uH", "dcm_fraction")
    # step7's AUTHORITATIVE design verdict for the viewer's acceptance panel
    def _f(k): return float(R.get(k, 0) or 0)
    _bsat, _bmax = _f("Bsat_at_Tcore"), _f("Bmax_FL_T")
    _ku, _j = _f("Ku"), _f("J_A_mm2")
    _dths = _f("dT_hotspot_C") or _f("dT_rise_C")
    _dtb = _f("dT_budget_C") or 60.0
    _lf, _ltgt = _f("L_full_load_uH"), _f("L_target_uH")
    acc_rows = []
    if _bsat > 0 and _bmax > 0:
        acc_rows.append(dict(name="B_max", val=f"{_bmax:.3f} T", ok=(_bmax < _bsat), limTxt=f"< {_bsat:.2f} T (Bsat)"))
    if _ku > 0:
        acc_rows.append(dict(name="window K_u", val=f"{_ku*100:.0f}%", ok=(_ku <= 0.6), limTxt="<= 60%"))
    if _dths > 0:
        acc_rows.append(dict(name="dT", val=f"{_dths:.0f} K", ok=(_dths <= _dtb), limTxt=f"<= {_dtb:.0f} K"))
    if _j > 0:
        acc_rows.append(dict(name="J", val=f"{_j:.2f} A/mm2", ok=None, limTxt="design metric"))
    if _lf > 0 and _ltgt > 0:
        acc_rows.append(dict(name="L_guarantee", val=f"{_lf:.0f} uH", ok=(_lf >= _ltgt), limTxt=f">= {_ltgt:.0f} uH"))
    _passed = bool(R.get("passed", True))
    acceptance = dict(verdict=("APPROVE" if _passed else "REJECT"), passed=_passed,
                      reasons=list(R.get("fail_reasons", []) or []), rows=acc_rows)

    return dict(
        scalars={k: R.get(k) for k in scalar_keys},
        waveform=waveform, waveforms_by_vin=waveforms_by_vin, sweep=sweep, L_vs_Vin=lvt,
        acceptance=acceptance,
        meta=dict(Vout_V=Vout, fsw_Hz=fsw, vin_design=90.0,
                  vins=sorted(int(k) for k in waveforms_by_vin), source="step7"),
    )
