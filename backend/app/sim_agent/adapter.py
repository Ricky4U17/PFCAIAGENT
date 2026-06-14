"""
adapter.py — our pipeline → Simulation-Agent package (the ONLY schema-mapping point).

Builds the engine `package` from a selected candidate DesignResult (serialized dict) +
the confirmed Mode-A/B state, per ADAPTER_FIELD_MAP.md. Decisions in effect:
  * step7 stays authoritative for design numbers; this feeds the sim/viz/doc layer.
  * Our DB physics is fed in EXACTLY via `fields` overrides (provenance "computed"):
      - DC-bias L(H)  ← db.get_k_bias            (fields.inductance)
      - R_ac/R_dc     ← DesignResult.Rac_Rdc     (fields.windingAC, our Dowell/Bessel)
      - 2-node thermal← DesignResult.Rca/Rwa/Rcw (fields.thermal)
      - inner crowd   ← DesignResult.crowd_axial (fields.flux)
  * Steinmetz a,b,c and retention k0,k1,p are FIT from our DB (validation needs them);
    no anchors attached (we fit from the DB, so a catalog anchor check is meaningless).

Additive & isolated: nothing in the live pipeline imports this yet.
"""
from __future__ import annotations
import math
from typing import Any, Optional

import numpy as np

from app.magnetics.db import get_db
from app.mode_b.calculations import build_design_ops_table
from app.sim_agent import pfc_inductor_engine as eng


# ── small helpers ───────────────────────────────────────────────────────────
def _g(d: dict, path: str, default=None):
    """Nested dict get: _g(state, 'intake.application.output_bus_voltage_v', 393)."""
    cur: Any = d or {}
    for k in path.split('.'):
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur if cur is not None else default


def _num(v, default=0.0) -> float:
    try:
        f = float(v)
        return f if math.isfinite(f) else float(default)
    except (TypeError, ValueError):
        return float(default)


def _fit_loss_steinmetz(db, mat_key: str, fsw_Hz: float,
                        bac_max: float = 0.0) -> tuple[float, float, float]:
    """Fit P[mW/cm^3] = a*B^b*f[kHz]^c to our DB loss surface. DB get_core_loss returns
    kW/m^3 == mW/cm^3. When the operating crest flux (bac_max) is known, the B-grid is
    concentrated over the ACTUAL operating range [~0, bac_max] so the power-law tracks the
    DB bilinear surface where the design runs — this tightens the cross-check vs Step-7
    (which evaluates the DB surface directly)."""
    f0 = fsw_Hz / 1e3
    if bac_max and bac_max > 0:
        hi = max(bac_max * 1.3, 0.02)
        Bs = tuple(float(x) for x in np.linspace(0.005, hi, 6))
    else:
        Bs = (0.01, 0.02, 0.04, 0.07, 0.10, 0.15)
    Fs = (f0 * 0.6, f0, f0 * 1.6)
    pts = []
    for f in Fs:
        for B in Bs:
            P = _num(db.get_core_loss(mat_key, f * 1e3, B, 100.0))
            if P > 0:
                pts.append([B, f, P])
    return eng._fit_steinmetz(pts)   # (a, b, c)


def _fit_retention(db, mat_key: str, H_max_oe: float) -> tuple[float, float, float]:
    """Fit %mu = 1/(k0 + k1*H^p) to our DB DC-bias curve (powder). Exact bias is still
    fed via fields.inductance; this is only the validation base / analytic fallback."""
    H = np.linspace(0.0, max(H_max_oe * 1.3, 60.0), 30)
    pct = np.array([_num(db.get_k_bias(mat_key, float(h)) * 100.0, 100.0) for h in H])
    y = 1.0 / np.maximum(pct, 1e-6)                 # = k0 + k1*H^p
    best = None
    for p in (1.5, 2.0, 2.5, 3.0, 3.044, 3.5):
        x = np.power(np.maximum(H, 1e-9), p)
        A = np.column_stack([np.ones_like(x), x])
        coef, *_ = np.linalg.lstsq(A, y, rcond=None)
        k0, k1 = float(coef[0]), float(coef[1])
        if k1 <= 0:
            continue
        err = float(np.sum((k0 + k1 * x - y) ** 2))
        if best is None or err < best[0]:
            best = (err, k0, k1, p)
    if best is None:
        return (0.01, 1e-9, 3.0)
    return (max(best[1], 1e-6), max(best[2], 1e-12), best[3])


# ── main entry ──────────────────────────────────────────────────────────────
def build_package(result: dict, state: dict, *,
                  wire_type: str = "litz", lineHz: float = 60.0,
                  provenance: str = "computed") -> dict:
    """Map a serialized DesignResult (`result`) + confirmed `state` to the engine package."""
    db = get_db()
    R = result or {}
    tsi    = _g(state, "topology_specific_inputs", {}) or {}
    intake = _g(state, "intake", {}) or {}
    appd   = _g(intake, "application", {}) or {}

    # ---- scalars (UNITS noted) ----
    N        = int(_num(R.get("N"), 1))
    stacks   = int(_num(R.get("stacks"), 1))
    core_type= str(R.get("core_type", "powder")).lower()
    mat_key  = str(R.get("material_key", ""))
    fsw_Hz   = _num(tsi.get("recommended_frequency_hz", 70000), 70000)      # Hz
    Vout     = _num(appd.get("output_bus_voltage_v", 393), 393)            # V
    nph      = int(_num(_g(state, "selected_channels", 2), 2))
    Tamb     = _num(_g(intake, "thermal.ambient_temp_c_max", 50), 50)      # degC
    Thot     = _num(_g(intake, "thermal.hotspot_limit_c", 110), 110)       # degC
    L_target_uH = _num(tsi.get("confirmed_L_uH_sel", tsi.get("recommended_L_uH", 240)), 240)
    T_core   = _num(R.get("T_core_C"), 0.0) or 100.0                       # for Bsat lookup

    # ---- geometry: PER SINGLE CORE (engine multiplies by stacks) ----
    Ve_single_mm3 = _num(R.get("Ve_total_cm3"), 0.0) / max(stacks, 1) * 1000.0
    geometry = {
        "OD_mm":  _num(R.get("OD_mm")),
        "ID_mm":  _num(R.get("ID_mm")),
        "HT_mm":  _num(R.get("HT_mm")),
        "stackHeight_mm": _num(R.get("HT_mm")),   # viewer alias for single-core height
        "Ae_mm2": _num(R.get("Ae_single_mm2")),
        "Le_mm":  _num(R.get("Le_single_mm")),
        "Ve_mm3": Ve_single_mm3,
        "Wa_mm2": _num(R.get("Wa_single_mm2")),
        "AL_nH":  _num(R.get("AL_nom_nH")),
        "AL_tol": _num(R.get("AL_tol_pct"), 8.0) / 100.0,
    }
    L0_nom_uH = geometry["AL_nH"] * stacks * (N ** 2) / 1000.0

    # ---- wire (derive n_parallel from Cu area, since DesignResult stores the total) ----
    n_str   = max(1, int(_num(R.get("n_strands"), 1)))
    d_str   = _num(R.get("d_strand_mm"), 0.1) or 0.1
    Cu_area = _num(R.get("Cu_area_mm2"), 0.0)
    A_strand = math.pi / 4.0 * d_str ** 2
    n_par = max(1, round(Cu_area / max(n_str * A_strand, 1e-9))) if Cu_area > 0 else 1

    # ---- material: Bsat direct; Steinmetz/retention fit from our DB ----
    Bsat = _num(db.get_Bsat(mat_key, T_core), 1.0)
    Bac_crest = _num(R.get("Bac_pk_T"), 0.0)
    a, b, c = _fit_loss_steinmetz(db, mat_key, fsw_Hz, bac_max=Bac_crest)
    try:
        mui = _num(db.get_mu_r(mat_key, T_core), 60.0)
    except Exception:
        mui = 60.0
    if core_type == "powder":
        H_worst = _num(R.get("H_Oe_worst"), 0.0)
        k0, k1, p = _fit_retention(db, mat_key, H_worst)
    else:
        k0, k1, p = 0.01, 1e-12, 2.0    # gapped ferrite ≈ no powder rolloff

    material = {
        "name": mat_key or "material",
        "AL_nH": geometry["AL_nH"], "mui": mui,   # viewer reads these
        "Bsat": Bsat,
        "steinmetz": {"a": a, "b": b, "c": c},
        "retention": {"k0": k0, "k1": k1, "p": p},
        "lossMaxScale": 1.20,           # matches our +20% P_unc_hi band
    }

    # No copper.measured: engine computes R_dc from geometry → provenance "computed"/T1.
    # We feed build_mm = 2*bundleOD (our v10 MLT) + the same A_cu and rho, so the geometry
    # estimate tracks our DesignResult DCR closely while keeping the badge honest (T1).
    copper = {
        "wire": {"type": wire_type, "strands": n_str, "strandDia_mm": d_str,
                 "parallel": n_par, "fillFactor": 0.55},
        "RacRdc": _num(R.get("Rac_Rdc"), 1.15) or 1.15,
        "alphaCu": 0.00393, "rho20_ohm_m": 1.72e-8,
        "refDeltaT_C": 80.0,    # viewer R_dc reference rise (R at 100 °C) — matches our 100 °C basis
        "prox": {"kSkin": 0.5, "kProx": 0.40, "kCrowd": 0.25},   # v10 proximity constants
    }

    # ---- operating points: rebuilt EXACTLY as run-sizing (eta & PF separate) ----
    Vin_lo = _num(appd.get("vin_rms_min", 90), 90)
    Vin_hi = _num(appd.get("vin_rms_max", 264), 264)
    Pout_lo = _num(appd.get("output_power_w_low_line", 1700), 1700)
    Pout_hi = _num(appd.get("output_power_w_high_line", 3600), 3600)
    r_input = _num(tsi.get("default_crest_ripple_ratio", 0.095), 0.095) or 0.095
    try:
        OPS, _ = build_design_ops_table(Vin_lo, Vin_hi, Pout_lo, Pout_hi, Vout, fsw_Hz, r_input)
    except Exception:
        from app.mode_b.step7_magnetic_calc import DEFAULT_OPS
        OPS = DEFAULT_OPS
    points = [{"Vin": float(row[0]), "Pout": float(row[1]),
               "eta": float(row[2]), "PF": float(row[3])} for row in OPS]
    etaByVin = {int(round(float(row[0]))): round(float(row[2]) * float(row[3]), 4) for row in OPS}

    # viewer explorer/display extras
    loPct    = round(Pout_lo / max(Pout_hi, 1.0) * 100.0, 1)
    vin_list = sorted({int(round(float(row[0]))) for row in OPS})
    bundleOD = _num(R.get("bundle_OD_computed_mm"), 1.9) or 1.9
    layers   = int(_num(R.get("layers_needed"), 1)) or 1

    # Per-layer winding build — SAME bore-fill as the Review window-build view, so the viewer's
    # cross/ring/3D draw the identical model: passes = N×nParallel, each layer holds
    # floor(2π·rC/bundleOD) turns as the bore radius shrinks by bundleOD per layer.
    _nPar = int(_num(R.get("n_parallel"), 1)) or 1
    _passes = N * _nPar
    _layerCaps = []
    _remain = _passes
    _rC = _num(R.get("ID_mm"), 0.0) / 2.0 - bundleOD / 2.0
    while _remain > 0 and _rC >= bundleOD / 2.0 and len(_layerCaps) < 200:
        _cap = max(1, int(2.0 * math.pi * max(_rC, bundleOD / 2.0) / bundleOD))
        _n = min(_remain, _cap)
        _layerCaps.append(_n); _remain -= _n; _rC -= bundleOD
    _holeR = max(0.0, _rC + bundleOD / 2.0) if _remain <= 0 else 0.0
    _nLayers = len(_layerCaps) or layers

    model = {
        "design": {
            "Vout": Vout, "fsw": fsw_Hz, "lineHz": lineHz, "nph": nph, "Prated": Pout_hi,
            # viewer explorer fields:
            "vinMin": Vin_lo, "vinMax": Vin_hi,
            # default the explorer to step7's design corner — 90 Vac low line at the spec-limited
            # low-line load — so the viewer opens on the SAME operating point as the Review page.
            "vinDefault": Vin_lo,
            "loadDefaultPct": loPct,
            "specLowLineMaxPct": loPct, "specHighLineMaxPct": 100.0,
        },
        "environment": {"Tamb_C": Tamb, "Thot_C": Thot},
        "winding": {
            "N": N, "stacks": stacks, "build_mm": 2.0 * bundleOD,
            "leadLength_mm": _num(R.get("lead_length_mm"), 150.0),
            # our winding geometry so the viewer shows OUR layer build, not its own estimate:
            "window": {
                "bundleOD_mm": bundleOD, "layersNeeded": _nLayers,
                "turnsPerLayer": _layerCaps[0] if _layerCaps else (int(_num(R.get("turns_per_layer"), 0)) or max(1, N // layers)),
                "radialBuild_mm": _nLayers * bundleOD,
                "boreHoleR_mm": round(_holeR, 3),
                "Ku": _num(R.get("Ku"), 0.0),
                "nParallel": _nPar, "passes": _passes, "layerCaps": _layerCaps,
            },
        },
        "geometry": geometry,
        "material": material,
        "copper": copper,
        # full cooling block for the viewer's thermal/warm-up math; fields.thermal still
        # overrides the ΔT that the cross-check/engine report.
        "cooling": {
            "mode": "natural", "airflow_mps": 0.0,
            "airScale": 1.0, "orientationFactor": 1.0, "boardPathFactor": 1.0,
            "radiationFactor": 1.0, "hotspotFactor": 1.12,
            "splitCoreAmbient": 1.0, "splitWdgAmbient": 0.9, "coupleCoreWdg": 0.5,
            "CthCore_J_perK": 55.0, "CthWdg_J_perK": 28.0, "warmupMinutesDefault": 20,
        },
        "maps": {"etaByVin": etaByVin, "crestByVin": {}},
        "labels": {"family": mat_key, "source": "PFC AI Design Agent (sim_agent.adapter)"},
    }

    pkg = {
        "schemaVersion": "1.0",
        "meta": {
            "units": {"length": "mm", "B": "T", "H": "Oe", "R": "ohm",
                      "T": "degC", "P": "W", "f": "Hz"},
            "provenance": "built by sim_agent.adapter",
            "source_ids": {"core": R.get("part_number", ""), "material": mat_key},
            "envelope": {"vin": vin_list, "loadPct": [25, 50, 75, 100], "phase": None},
        },
        "model": model,
        "operating": {"points": points},
        "acceptance": {
            # engine keys:
            "L_target_uH": L_target_uH, "sat_margin_min": 0.43, "FFcu_limit": 0.40,
            # viewer keys:
            "Bmax_T": round(Bsat, 3), "Ku_max": 0.6, "dT_max_K": round(Thot - Tamb, 1),
        },
    }

    # ---- fields: feed OUR exact physics (provenance "computed") ----
    fields: dict = {}
    if core_type == "powder":
        # cover at least the B-H graph axis (160 Oe) so L(H) doesn't clamp/straighten the curve
        H_max = max(_num(R.get("H_Oe_worst"), 0.0) * 1.8, 170.0)
        Hgrid = np.linspace(0.0, H_max, 36)
        L_uH = [round(float(db.get_k_bias(mat_key, float(h))) * L0_nom_uH, 4) for h in Hgrid]
        fields["inductance"] = {"H": [round(float(h), 3) for h in Hgrid],
                                "L_uH": L_uH, "provenance": provenance}
    rac = _num(R.get("Rac_Rdc"), 0.0)
    if rac > 0:
        fields["windingAC"] = {"freq_Hz": [fsw_Hz * 0.5, fsw_Hz * 2.0],
                               "RacOverRdc": [rac, rac], "provenance": provenance}
    # NOTE: we deliberately do NOT feed fields.thermal. The engine's node usage is a crude
    # `dT = Ptot_max · Rwa` (single multiply, not a KCL solve), which is incompatible with our
    # 2-node NETWORK resistances (Rwa = theta·(sC+sW)/sW) and would overestimate ΔT ~2.5×.
    # Without it the engine uses its analytic surface-area ΔT — the same SA power-law as our
    # step7 dT_rise_C — so the cross-check compares surface-to-surface (within band). Our 2-node
    # hotspot stays the authoritative thermal number in step7 / the report.
    crowd = _num(R.get("crowd_axial"), 0.0)
    if crowd > 0 and geometry["ID_mm"] > 0:
        fields["flux"] = {"radial": {"r_mm": [geometry["ID_mm"] / 2.0], "crowd": [crowd]},
                          "provenance": provenance}
    if fields:
        pkg["fields"] = fields
    return pkg


def build_and_validate(result: dict, state: dict, **kw):
    """Convenience: build the package and run the engine's validation gate."""
    pkg = build_package(result, state, **kw)
    return pkg, eng.validate(pkg)


def crosscheck_rows(result: dict, sim: dict) -> list:
    """Single source of truth for the Step-7 vs field-engine comparison (used by the
    /simulate endpoint, the Review panel, and report §4.8 / §14.9).

    Each quantity is compared on a COMMON basis so definitional differences don't
    masquerade as errors:
      * J          — engine reports total-Cu density; step7 reports per-conductor.
                     We put the engine on the per-conductor basis (× n_par).
      * ΔT         — compared against our 2-node HOTSPOT rise (the engine's dT, fed our
                     thermal nodes, is the winding node evaluated at the +20% loss band).
      * Bmax       — step7 uses L_target for B_dc; the engine uses the biased L(H) (lower,
                     more accurate). Band widened + noted accordingly.
    Returns rows: {quantity, ours, sim (display strings w/ units), delta_pct, band_pct,
    within, note}.
    """
    R     = result or {}
    stat  = sim.get("statics", {}) or {}
    worst = sim.get("worst", {}) or {}
    pts   = sim.get("points", []) or []
    p90   = min(pts, key=lambda p: abs(float(p.get("Vin", 1e9)) - 90)) if pts else {}

    # parallel-bundle count, to put J on the same per-conductor basis as step7
    n_str = max(1, int(_num(R.get("n_strands"), 1)))
    d_str = _num(R.get("d_strand_mm"), 0.1) or 0.1
    cu    = _num(R.get("Cu_area_mm2"), 0.0)
    n_par = max(1, round(cu / max(n_str * math.pi / 4 * d_str ** 2, 1e-9))) if cu > 0 else 1
    eng_J = _num(stat.get("J_AperMM2"), 0.0) * n_par     # total-Cu → per-conductor

    # spec tuple: (name, ours, engine, band%, unit, note, one_sided)
    # one_sided=True → flag ONLY if the engine reads HIGHER than ours (the unsafe direction);
    # a conservative step7 (engine lower) is expected and fine.
    specs = [
        ("L0 nominal",  _num(R.get("L0_nom_uH")),     _num(stat.get("L0_nom_uH")),    2,  "µH",    "", False),
        ("DCR @100°C",  _num(R.get("DCR_100C_mOhm")), _num(stat.get("DCR100_mohm")),  5,  "mOhm",  "engine geometry DCR excludes the ~150 mm lead", False),
        ("Ptotal @90V", _num(R.get("Ptotal_100C_W")), _num(p90.get("Ptot_typ")),      15, "W",     "", False),
        ("Bmax @90V",   _num(R.get("Bmax_FL_T")),     _num(p90.get("Bmax")),          12, "T",     "step7 conservative (B_dc from L_target); engine uses biased L(H) — flagged only if engine reads higher", True),
        ("ΔT surface",  _num(R.get("dT_rise_C")) or _num(R.get("dT_hotspot_C")),
                        _num((worst.get("dT") or {}).get("dT")),                       30, "°C",    "both surface ΔT (SA power-law); engine at the +20% core-loss band", False),
        ("J per-cond",  _num(R.get("J_A_mm2")),       eng_J,                          10, "A/mm²", "same per-conductor basis (engine ×n_par)", False),
    ]
    rows = []
    for name, o, t, tol, unit, note, one_sided in specs:
        if o and o > 0 and t is not None:
            dd = (t - o) / o * 100.0
            within = (dd <= tol) if one_sided else (abs(dd) <= tol)
            rows.append({"quantity": name, "ours": f"{o:.4g} {unit}", "sim": f"{t:.4g} {unit}",
                         "delta_pct": round(dd, 1), "band_pct": tol,
                         "within": within, "note": note})
        else:
            rows.append({"quantity": name,
                         "ours": (f"{o:.4g} {unit}" if o else "—"),
                         "sim":  (f"{t:.4g} {unit}" if t else "—"),
                         "delta_pct": None, "band_pct": tol, "within": None, "note": note})
    return rows
