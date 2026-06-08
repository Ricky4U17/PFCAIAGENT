"""
app/mode_b/data_loader.py
DataLoader: loads and interpolates material and wire data from /data/ directory.
All computation uses physical H (A/m or Oe) — never bare A·T, which is geometry-dependent.
"""
from __future__ import annotations
import json, csv, math, os
from pathlib import Path
from typing import Optional
import numpy as np

DATA_ROOT = Path(__file__).parent.parent.parent / "data"

# ── Supplier / material key → JSON file path ──────────────────────────────
_MAT_PATHS: dict[str, Path] = {
    "3C95":        DATA_ROOT / "magnetic_materials/ferroxcube/3C95.json",
    "3C97":        DATA_ROOT / "magnetic_materials/ferroxcube/3C97.json",
    "N87":         DATA_ROOT / "magnetic_materials/tdk/N87.json",
    "N95":         DATA_ROOT / "magnetic_materials/tdk/N95.json",
    "kool_mu_60":  DATA_ROOT / "magnetic_materials/magnetics_inc/kool_mu_60.json",
    "edge_60":     DATA_ROOT / "magnetic_materials/magnetics_inc/edge_60.json",
}

_CORE_CATALOGS: dict[str, Path] = {
    "ferroxcube": DATA_ROOT / "magnetic_materials/ferroxcube/etd_catalog.csv",
    "tdk":        DATA_ROOT / "magnetic_materials/tdk/etd_catalog.csv",
    "magnetics_inc": DATA_ROOT / "magnetic_materials/magnetics_inc/toroid_catalog.csv",
}

_WIRE_CATALOG = DATA_ROOT / "wire/litz_catalog.csv"

# ── In-memory cache ───────────────────────────────────────────────────────
_mat_cache:  dict[str, dict] = {}
_core_cache: dict[str, list] = {}
_wire_cache: Optional[list]  = None


def _load_material(key: str) -> dict:
    if key not in _mat_cache:
        path = _MAT_PATHS.get(key)
        if path is None or not path.exists():
            raise FileNotFoundError(f"Material '{key}' not found. Available: {list(_MAT_PATHS)}")
        with open(path) as f:
            _mat_cache[key] = json.load(f)
    return _mat_cache[key]


def _load_core_catalog(supplier: str) -> list[dict]:
    key = supplier.lower().replace(" ", "_")
    if key not in _core_cache:
        path = _CORE_CATALOGS.get(key)
        if path is None or not path.exists():
            raise FileNotFoundError(f"Core catalog for '{supplier}' not found.")
        with open(path) as f:
            _core_cache[key] = list(csv.DictReader(f))
    return _core_cache[key]


def _load_wire_catalog() -> list[dict]:
    global _wire_cache
    if _wire_cache is None:
        with open(_WIRE_CATALOG) as f:
            _wire_cache = list(csv.DictReader(f))
    return _wire_cache


def _bilinear(f_axis: list, B_axis: list, table: list,
               f_val: float, B_val: float) -> float:
    """
    Bilinear interpolation on a 2D core-loss grid in LOG-LOG space.
    table[i][j] = Pv at (B_axis[i], f_axis[j])

    WHY LOG-LOG:  Core-loss data follows Steinmetz: Pv = k·f^α·B^β
    In log space: ln(Pv) = ln(k) + α·ln(f) + β·ln(B) — a perfect bilinear
    surface.  Interpolating in log(Pv) vs log(f)×log(B) gives ZERO error
    for data computed from Steinmetz, and <1% error for digitized datasheet
    data (which closely follows the power law).

    Linear bilinear on the same data gives ~13% error at operating points
    between grid nodes (e.g. B=0.054 T between 0.05 and 0.10 T grid points).
    """
    f_arr = np.array(f_axis, dtype=float)
    B_arr = np.array(B_axis, dtype=float)
    Pv    = np.array(table,  dtype=float)   # shape (len(B), len(f))
    lPv   = np.log(np.maximum(Pv, 1e-30))   # log grid — safe against zeros

    f_c = float(np.clip(f_val, f_arr[0], f_arr[-1]))
    B_c = float(np.clip(B_val, B_arr[0], B_arr[-1]))

    # Surrounding indices
    fi = max(0, min(len(f_arr)-2, int(np.searchsorted(f_arr, f_c)) - 1))
    bi = max(0, min(len(B_arr)-2, int(np.searchsorted(B_arr, B_c)) - 1))

    # Fractional position in LOG space (exact for power-law)
    lf_lo = math.log(f_arr[fi]);   lf_hi = math.log(f_arr[fi+1])
    lB_lo = math.log(B_arr[bi]);   lB_hi = math.log(B_arr[bi+1])
    tf = (math.log(f_c) - lf_lo) / (lf_hi - lf_lo) if lf_hi != lf_lo else 0.0
    tb = (math.log(B_c) - lB_lo) / (lB_hi - lB_lo) if lB_hi != lB_lo else 0.0

    # Bilinear on log(Pv) — exact for Steinmetz, <1% for digitized data
    lv = ((1-tb)*(1-tf)*lPv[bi  ][fi  ] + (1-tb)*tf*lPv[bi  ][fi+1] +
              tb*(1-tf)*lPv[bi+1][fi  ] +      tb*tf*lPv[bi+1][fi+1])
    return float(math.exp(lv))


# ═══════════════════════════════════════════════════════════════════════════
# PUBLIC API
# ═══════════════════════════════════════════════════════════════════════════

def get_core_loss_kW_m3(material_key: str, f_Hz: float, Bac_pk_T: float,
                         T_C: float = 25.0) -> float:
    """
    Returns Pv (kW/m³) using bilinear interpolation on the digitized core-loss
    surface. Interpolates linearly between 25°C and 100°C tables.

    For powder cores only one temperature table exists (25°C) — use that.
    """
    d = _load_material(material_key)
    f_kHz = f_Hz / 1e3

    if "core_loss_surface_100C" in d:
        # Ferrite: two temperature tables
        s25  = d["core_loss_surface_25C"]
        s100 = d["core_loss_surface_100C"]
        Pv25  = _bilinear(s25["f_kHz"],  s25["B_pk_T"],  s25["Pv_kW_m3"],  f_kHz, Bac_pk_T)
        Pv100 = _bilinear(s100["f_kHz"], s100["B_pk_T"], s100["Pv_kW_m3"], f_kHz, Bac_pk_T)
        frac = max(0.0, min(1.0, (T_C - 25.0) / (100.0 - 25.0)))
        return Pv25 + frac * (Pv100 - Pv25)
    else:
        # Powder: single table (loss ≈ constant with temperature in 20-120°C range)
        s = d["core_loss_surface_25C"]
        return _bilinear(s["f_kHz"], s["B_pk_T"], s["Pv_kW_m3"], f_kHz, Bac_pk_T)


def get_Bsat(material_key: str, T_C: float) -> float:
    """Returns Bsat (T) at operating temperature by linear interpolation."""
    d = _load_material(material_key)
    if d["type"] == "powder":
        return d["basic"]["Bsat_T"]   # powder: Bsat essentially flat with T
    bv = d["Bsat_vs_T"]
    return float(np.interp(T_C, bv["T_C"], bv["Bsat"]))


def get_mu_r(material_key: str, T_C: float) -> float:
    """Returns µr at temperature T_C (ferrite only). Powder: returns mu_initial."""
    d = _load_material(material_key)
    if d["type"] == "powder":
        return float(d.get("mu_initial", d["basic"].get("mu_initial", 60)))
    mv = d["mu_r_vs_T"]
    return float(np.interp(T_C, mv["T_C"], mv["mu_r"]))


def get_k_bias(material_key: str, H_Oe: float) -> float:
    """
    Returns µ_eff / µ_initial (0–1) at DC bias field H (Oersteds).
    Powder cores only. Piecewise-linear interpolation of digitized rolloff curve.

    H_Oe = H_Am / 79.577
    H_Am = N × I_dc / Le_single   (Le of ONE toroid, regardless of stack count)

    This is the correct physics: each toroid has its own flux path of Le_single.
    """
    d = _load_material(material_key)
    if d["type"] != "powder":
        raise TypeError(f"k_bias only valid for powder cores. '{material_key}' is ferrite.")
    bias = d["dc_bias_rolloff"]
    mu_pct = float(np.interp(H_Oe, bias["H_Oe"], bias["mu_pct"],
                              left=100.0, right=float(bias["mu_pct"][-1])))
    return mu_pct / 100.0


def get_material_info(material_key: str) -> dict:
    """Return full material dict (for display in HITL screens)."""
    return _load_material(material_key)


def filter_cores(supplier: str, shape: str = None,
                 max_height_mm: float = 9999,
                 min_Ae_mm2: float = 0,
                 max_stacks: int = 3) -> list[dict]:
    """
    Return list of (core_dict, stacks) tuples that satisfy constraints.
    For toroids, tries stacks = 1..max_stacks. For ETD/EE, stacks always = 1.
    """
    catalog = _load_core_catalog(supplier)
    result  = []
    for row in catalog:
        if shape and row.get("shape","").upper() != shape.upper():
            continue
        Ae = float(row["Ae_mm2"])
        HT = float(row["HT_mm"])

        if supplier.lower() in ("magnetics_inc",):
            # Toroid: try different stack counts
            for S in range(1, max_stacks + 1):
                Ae_stack = Ae * S   # stacked Ae — check THIS against min_Ae
                h_eff = HT * S + 5.0   # 5 mm clearance each end
                if h_eff <= max_height_mm and Ae_stack >= min_Ae_mm2:
                    result.append({**{k: _cast(v) for k, v in row.items()},
                                   "stacks": S,
                                   "h_effective_mm": round(h_eff, 2),
                                   "Ae_total_mm2": round(Ae * S, 2),
                                   "Wa_total_mm2": round(float(row["Wa_mm2"]) * S, 2),  # Wa scales with stacks per Magnetics reference design
                                   "Ve_total_cm3": round(float(row["Ve_cm3"]) * S, 4),
                                   "AL_min_total": float(row["AL_min_nH"]) * S,
                                   "AL_nom_total": float(row["AL_nom_nH"]) * S,
                                   "AL_max_total": float(row["AL_max_nH"]) * S,
                                   "Le_single_mm": float(row["Le_mm"])})
        else:
            # Ferrite: single core, stacks=1
            h_eff = float(row.get("max_height_mm", HT))
            if h_eff <= max_height_mm:
                result.append({**{k: _cast(v) for k, v in row.items()},
                               "stacks": 1,
                               "h_effective_mm": h_eff,
                               "Ae_total_mm2": Ae,
                               "Wa_total_mm2": float(row["Wa_mm2"]),
                               "Ve_total_cm3": float(row["Ve_mm3"]) / 1000.0,
                               "Le_single_mm": float(row["Le_mm"])})
    return result


def get_wire_options(wire_type: str, IL_rms: float, fsw_Hz: float,
                     T_C: float = 100.0, J_target: float = 5.0,
                     n_options: int = 3) -> list[dict]:
    """
    Return top n_options wire specs matching type (litz/solid) that:
      - Have Cu_area ≥ IL_rms / J_target
      - For Litz: strand_dia ≤ 2 × skin_depth (skin_depth at fsw_Hz)
    Sorted by Cu_area (smallest sufficient first).

    Also returns Rdc at T_C.
    """
    catalog  = _load_wire_catalog()
    rho_20   = 1.72e-8   # Ω·m
    alpha_Cu = 0.00393
    rho_T    = rho_20 * (1 + alpha_Cu * (T_C - 20))
    mu0      = 4 * math.pi * 1e-7
    delta_m  = math.sqrt(rho_T / (math.pi * fsw_Hz * mu0))   # skin depth at T

    A_min = IL_rms / J_target   # mm²

    results = []
    for row in catalog:
        if row["type"].lower() != wire_type.lower():
            continue
        Cu_area = float(row["Cu_area_mm2"])
        if Cu_area < A_min * 0.90:
            continue
        if wire_type.lower() == "litz":
            d_s_mm = float(row["strand_dia_mm"])
            if d_s_mm > 2 * delta_m * 1e3 * 1.05:   # 5% tolerance
                continue
        R_per_m_20 = float(row["R_per_m_20C_ohm"])
        R_per_m_T  = R_per_m_20 * (1 + alpha_Cu * (T_C - 20))
        results.append({
            **{k: _cast(v) for k, v in row.items()},
            "skin_depth_mm": round(delta_m * 1e3, 4),
            "max_strand_dia_mm": round(2 * delta_m * 1e3, 4),
            "R_per_m_at_T": round(R_per_m_T, 6),
            "J_at_Irms": round(IL_rms / Cu_area, 2),
        })

    results.sort(key=lambda r: (abs(float(r["Cu_area_mm2"]) - A_min)))
    return results[:n_options]


def _cast(v: str):
    """Convert CSV string to float if possible, else return string."""
    try:
        return float(v)
    except (ValueError, TypeError):
        return v


def compute_dowell_factor(n_strands: int, d_strand_mm: float,
                           N_turns: int, Wa_mm2: float, fsw_Hz: float,
                           T_C: float = 100.0) -> dict:
    """
    Computes Rac/Rdc using simplified Dowell model for Litz wire.
    Valid for Δ = d_strand/(2δ) < 1.5.

    Returns dict with Rac_Rdc, layers, delta_mm, Delta, valid.
    """
    rho_T  = 1.72e-8 * (1 + 0.00393 * (T_C - 20))
    mu0    = 4 * math.pi * 1e-7
    delta  = math.sqrt(rho_T / (math.pi * fsw_Hz * mu0))    # m
    Delta  = (d_strand_mm * 1e-3) / (2 * delta)

    # Estimate winding layers
    d_bundle = d_strand_mm * 1.05 * math.sqrt(n_strands) * 1.20   # mm
    Wa_h = math.sqrt(Wa_mm2)   # approximate square window height
    m = max(1, math.ceil(N_turns * d_bundle / Wa_h))

    # Dowell simplified (valid for Delta < 1.5)
    M_d = Delta
    D_d = 2 * Delta**3
    F_R = (Delta / 2) * (M_d + (2 * (m**2 - 1) / 3) * D_d)
    Rac_Rdc = 1.0 + F_R

    return {
        "Rac_Rdc":  round(Rac_Rdc, 4),
        "layers":   m,
        "delta_mm": round(delta * 1e3, 4),
        "Delta":    round(Delta, 4),
        "F_R":      round(F_R, 4),
        "valid":    Delta < 1.5,
        "note":     "Dowell simplified model. Valid for Δ<1.5." if Delta < 1.5
                    else f"WARNING: Δ={Delta:.2f} > 1.5 — use larger strand count or smaller strand dia.",
    }


def compute_rogowski_fringing(lg_mm: float, Ae_mm2: float,
                               Wa_mm2: float, N: int,
                               d_bundle_mm: float, IL_HF_rms: float,
                               Rdc_ohm: float) -> dict:
    """
    Estimates fringing-field induced extra copper loss for gapped ferrite inductors.
    Powder cores: set lg_mm=0 → returns P_fring=0.

    Rogowski-Dowell fringing factor:
      F_fring = 1 + (lg/√Ae) × ln(2·hw/lg)
    where hw = winding height adjacent to gap ≈ √(Wa/2)

    Fringing clearance rule (Medical): keep winding ≥ 2×lg from gap face.
    """
    if lg_mm < 0.01:
        return {"P_fring_W": 0.0, "F_fring": 1.0, "N_affected": 0,
                "clearance_required_mm": 0.0, "note": "No air gap — no fringing loss."}

    Ae_m2 = Ae_mm2 * 1e-6
    lg_m  = lg_mm * 1e-3
    hw_mm = math.sqrt(Wa_mm2 / 2)   # approximate half-window height
    hw_m  = hw_mm * 1e-3

    if hw_m < lg_m:
        hw_m = lg_m * 2   # safety fallback

    F_fring = 1 + (lg_m / math.sqrt(Ae_m2)) * math.log(2 * hw_m / lg_m)

    # Turns within 2×lg of gap face (affected by fringing)
    N_affected = min(N, max(1, math.ceil(2 * lg_mm / d_bundle_mm)))

    # Additional resistance from fringing field on affected turns
    Rfringe_add = Rdc_ohm * (F_fring - 1) * N_affected / N
    P_fring     = IL_HF_rms**2 * Rfringe_add

    clearance = 2 * lg_mm   # minimum winding clearance from gap face

    return {
        "P_fring_W":             round(P_fring, 4),
        "F_fring":               round(F_fring, 4),
        "N_affected":            N_affected,
        "clearance_required_mm": round(clearance, 2),
        "Rfringe_add_ohm":       round(Rfringe_add, 6),
        "note": (f"Rogowski fringing factor {F_fring:.3f}. "
                 f"Keep winding ≥ {clearance:.1f} mm from gap face (Medical IEC 60601-1)."),
    }
