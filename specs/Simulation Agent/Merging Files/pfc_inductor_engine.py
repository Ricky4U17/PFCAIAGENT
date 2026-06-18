#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pfc_inductor_engine.py
======================
Material-AGNOSTIC reference engine for boost / interleaved-boost PFC inductors on
distributed-gap powder toroids. Python counterpart of the browser `SimAgentField`
module: it consumes the SAME injected package contract (model + optional solved
`fields`) and produces the same physics, so the viewer and this engine never drift.

DESIGN PRINCIPLES (per project decisions)
-----------------------------------------
* NOTHING about the design is hard-coded. Material characteristics, core geometry,
  stack-up, wire, ambient and (optionally) solved field grids ALL arrive in the
  injected package from previous pipeline steps (the upstream magnetics database +
  the designer's finalized selection). The engine owns only physics/unit constants.
* No built-in material library, no core selection, no catalog logic. This engine is
  a calculator, not a database or a design authority.
* validate() fails LOUDLY on structurally broken / physically impossible input
  (errors -> hard stop, no result). Soft issues travel WITH the result as warnings.
* If a solved `fields` block is supplied, its values OVERRIDE the analytic model and
  every quantity carries provenance: 'fea' | 'measured' | 'input' | 'computed' | 'analytic'.
* Headless: compute(package) -> dict. JSON in/out for the parent agent.

Dependencies: numpy only. Python 3.9+.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional, Any
import math, json, sys
import numpy as np

# ---- intrinsic physics / unit constants ONLY (never design data) ----
MU0 = 4 * math.pi * 1e-7            # H/m
OE_TO_AM = 79.577                   # 1 Oe = 79.577 A/m
RHO_CU_20_DEFAULT = 1.724e-8        # ohm*m  (copper; overridable via package)
ALPHA_CU_DEFAULT = 0.00393          # 1/K    (overridable)
SCHEMA_VERSION = "1.0"
__version__ = "1.0.0"


class SpecError(ValueError):
    """Raised when the injected package fails validation (hard errors)."""
    def __init__(self, errors: List[str]):
        super().__init__("invalid package: " + "; ".join(errors))
        self.errors = errors


@dataclass
class ValidationResult:
    ok: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    def as_dict(self): return {"ok": self.ok, "errors": self.errors, "warnings": self.warnings}


# ====================================================================================
#  CONTRACT
# ====================================================================================
def schema() -> dict:
    """Return the package contract (mirrors SimAgentField.SCHEMA on the JS side)."""
    return {
      "schemaVersion": SCHEMA_VERSION,
      "model": {
        "design": "{Vout, fsw, lineHz, nph, rippleRatio?, Prated?, specLowLineMaxPct?, specHighLineMaxPct?}",
        "environment": "{Tamb_C, Thot_C?}",
        "winding": "{N, stacks, build_mm?, leadLength_mm?}",
        "geometry": "{OD_mm, ID_mm, HT_mm(single core), Ae_mm2(single), Le_mm(single), "
                    "Ve_mm3(single)|Ve_cm3, Wa_mm2(single), AL_nH(single), AL_tol?}",
        "material": "{name, Bsat, steinmetz{a,b,c}  (P=a*B^b*f[kHz]^c, mW/cm^3), "
                    "retention{k0,k1,p}  (%mu=1/(k0+k1*H[Oe]^p)), lossMaxScale?, "
                    "anchors?{loss:[B,f_kHz,P], bias:[[H,%mu],...]}}",
        "copper": "{wire{type('litz'|'magnet'|'solid'), strands, strandDia_mm, parallel, fillFactor?}, "
                  "measured{RdcTotal_20C?|RdcPerMeter_20C?}, alphaCu?, rho20_ohm_m?, RacRdc?}",
        "cooling": "{mode('natural'|'forced'), airflow_mps?}",
        "maps": "{etaByVin?{}, crestByVin?{}}  (optional; used only if operating.points absent)",
      },
      "operating": "{points:[{Vin, Pout, eta, PF}, ...]}  "
                   "(preferred). If absent, derived from model.maps + design.Prated + spec*Pct.",
      "acceptance": "{L_target_uH, sat_margin_min?, FFcu_limit?, J_min?, J_max?}",
      "fields": "{ inductance?{H:[Oe],L_uH:[],provenance}, windingAC?{freq_Hz:[],RacOverRdc:[],provenance}, "
                "thermal?{nodes{Rca_KperW,Rwa_KperW,Rcw_KperW}|{thetaSA_KperW},provenance}, "
                "flux?{radial{r_mm,crowd},provenance} }   (OPTIONAL solved ROM; absent => analytic)",
    }


# ====================================================================================
#  VALIDATION  (errors -> hard stop;  warnings -> travel with result)
# ====================================================================================
def _get(d, path, default=None):
    cur = d
    for k in path.split('.'):
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur

def _is_num(x): return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)

def validate(package: dict) -> ValidationResult:
    errors: List[str] = []
    warnings: List[str] = []
    if not isinstance(package, dict):
        return ValidationResult(False, ["package is not an object"], [])
    m = package.get("model")
    if not isinstance(m, dict):
        return ValidationResult(False, ["missing 'model' block"], [])

    # ---- 1. presence of required blocks/fields (no silent defaults for design data) ----
    required_num = {
        "model.design.Vout": _get(m, "design.Vout"),
        "model.design.fsw": _get(m, "design.fsw"),
        "model.design.lineHz": _get(m, "design.lineHz"),
        "model.design.nph": _get(m, "design.nph"),
        "model.environment.Tamb_C": _get(m, "environment.Tamb_C"),
        "model.winding.N": _get(m, "winding.N"),
        "model.winding.stacks": _get(m, "winding.stacks"),
        "model.geometry.OD_mm": _get(m, "geometry.OD_mm"),
        "model.geometry.ID_mm": _get(m, "geometry.ID_mm"),
        "model.geometry.HT_mm": _get(m, "geometry.HT_mm"),
        "model.geometry.Ae_mm2": _get(m, "geometry.Ae_mm2"),
        "model.geometry.Le_mm": _get(m, "geometry.Le_mm"),
        "model.geometry.Wa_mm2": _get(m, "geometry.Wa_mm2"),
        "model.geometry.AL_nH": _get(m, "geometry.AL_nH"),
        "model.material.Bsat": _get(m, "material.Bsat"),
        "model.material.steinmetz.a": _get(m, "material.steinmetz.a"),
        "model.material.steinmetz.b": _get(m, "material.steinmetz.b"),
        "model.material.steinmetz.c": _get(m, "material.steinmetz.c"),
        "model.material.retention.k0": _get(m, "material.retention.k0"),
        "model.material.retention.k1": _get(m, "material.retention.k1"),
        "model.material.retention.p": _get(m, "material.retention.p"),
        "model.copper.wire.strands": _get(m, "copper.wire.strands"),
        "model.copper.wire.strandDia_mm": _get(m, "copper.wire.strandDia_mm"),
    }
    if _get(m, "geometry.Ve_mm3") is None and _get(m, "geometry.Ve_cm3") is None:
        errors.append("missing model.geometry.Ve_mm3 (or Ve_cm3)")
    for pth, val in required_num.items():
        if val is None:
            errors.append("missing required " + pth)
        elif not _is_num(val):
            errors.append("non-numeric " + pth + " = " + repr(val))

    # operating points present OR derivable
    pts = _get(package, "operating.points")
    if not (isinstance(pts, list) and pts):
        if _get(m, "design.Prated") is None or not isinstance(_get(m, "maps.etaByVin"), dict):
            errors.append("no operating.points and cannot derive them "
                          "(need model.design.Prated + model.maps.etaByVin)")
    if isinstance(pts, list):
        for i, p in enumerate(pts):
            for kk in ("Vin", "Pout", "eta", "PF"):
                if not _is_num(p.get(kk)):
                    errors.append(f"operating.points[{i}].{kk} missing/non-numeric")

    if errors:  # don't run domain/cross checks on structurally broken input
        return ValidationResult(False, errors, warnings)

    # ---- 2. domain / physical sanity ----
    g = m["geometry"]
    if g["ID_mm"] >= g["OD_mm"]:
        errors.append(f"geometry: ID_mm ({g['ID_mm']}) >= OD_mm ({g['OD_mm']})")
    for pth in ("design.fsw", "design.Vout", "geometry.Ae_mm2", "geometry.Le_mm",
                "geometry.Wa_mm2", "geometry.AL_nH", "material.Bsat"):
        v = _get(m, pth)
        if v is not None and v <= 0:
            errors.append(f"{pth} must be > 0 (got {v})")
    if m["winding"]["N"] < 1: errors.append("winding.N must be >= 1")
    if m["winding"]["stacks"] < 1: errors.append("winding.stacks must be >= 1")
    if m["copper"]["wire"]["strands"] < 1: errors.append("copper.wire.strands must be >= 1")
    if m["copper"]["wire"]["strandDia_mm"] <= 0: errors.append("copper.wire.strandDia_mm must be > 0")
    p_ret = _get(m, "material.retention.p")
    if p_ret is not None and p_ret <= 0: errors.append("material.retention.p must be > 0")
    wt = _get(m, "copper.wire.type")
    if wt is not None and str(wt).lower() not in ("litz", "magnet", "solid", "round"):
        warnings.append(f"copper.wire.type '{wt}' unrecognized (expected litz|magnet|solid)")

    if errors:
        return ValidationResult(False, errors, warnings)

    # ---- 3. cross-field consistency ----
    # window fit (physical feasibility): FFcu = N * A_cu / Wa  must be <= 1
    A_strand = math.pi / 4 * (m["copper"]["wire"]["strandDia_mm"] ** 2)
    n_par = m["copper"]["wire"].get("parallel", 1) or 1
    A_cu = n_par * m["copper"]["wire"]["strands"] * A_strand
    FFcu = m["winding"]["N"] * A_cu / g["Wa_mm2"]
    if FFcu > 1.0:
        errors.append(f"window overflow: copper fill FFcu={FFcu*100:.0f}% > 100% "
                      f"(N*A_cu={m['winding']['N']*A_cu:.1f} mm^2 vs Wa={g['Wa_mm2']} mm^2)")
    # measured-R vs geometry sanity (warn, do not reject)
    meas = _get(m, "copper.measured") or {}
    rho = _get(m, "copper.rho20_ohm_m") or RHO_CU_20_DEFAULT
    width = (g["OD_mm"] - g["ID_mm"]) / 2.0
    stack_h = g["HT_mm"] * m["winding"]["stacks"]
    mlt_mm = 2 * (width + stack_h) + (m["winding"].get("build_mm", 3.8))
    ell = m["winding"]["N"] * mlt_mm / 1000.0
    Rdc_geom20 = rho * ell / (A_cu * 1e-6)
    if _is_num(meas.get("RdcTotal_20C")):
        ratio = meas["RdcTotal_20C"] / max(Rdc_geom20, 1e-12)
        if ratio > 2.0 or ratio < 0.5:
            warnings.append(f"measured RdcTotal_20C ({meas['RdcTotal_20C']*1e3:.1f} mOhm) disagrees with "
                            f"geometry estimate ({Rdc_geom20*1e3:.1f} mOhm) by {ratio:.1f}x")
    # fields envelope: warn if op points fall outside an attached inductance/windingAC table
    fld = package.get("fields") or {}
    if isinstance(fld.get("windingAC"), dict):
        fr = fld["windingAC"].get("freq_Hz") or []
        if fr and not (fr[0] <= m["design"]["fsw"] <= fr[-1]):
            warnings.append("design.fsw outside fields.windingAC.freq_Hz range -> edge-clamped")

    # ---- 4. measured-material (Tier-3) self-consistency: warn, NEVER silently accept ----
    meas_mat = _get(m, "material.measured") or {}
    sm = m["material"]["steinmetz"]
    def _cat(B, f): return sm["a"] * B ** sm["b"] * f ** sm["c"]
    clm = meas_mat.get("coreLoss") or {}
    if isinstance(clm.get("steinmetz"), dict):
        ms = clm["steinmetz"]
        if not all(_is_num(ms.get(k)) for k in ("a", "b", "c")):
            errors.append("material.measured.coreLoss.steinmetz must have numeric a,b,c")
        else:
            ratio = (ms["a"] * 0.1 ** ms["b"] * 100 ** ms["c"]) / max(_cat(0.1, 100), 1e-12)
            if ratio > 1.5 or ratio < 0.67:
                warnings.append(f"measured coreLoss Steinmetz differs from catalog by {ratio:.2f}x "
                                f"at (0.1 T, 100 kHz) - verify bench data before trusting T3")
    if clm.get("points") is not None:
        cp = clm["points"]
        if not (isinstance(cp, list) and len(cp) >= 3
                and all(isinstance(p, (list, tuple)) and len(p) == 3 and all(_is_num(x) and x > 0 for x in p) for p in cp)):
            errors.append("material.measured.coreLoss.points must be >=3 positive rows of [B_T, f_kHz, P_mWcm3]")
        else:
            ratios = sorted(p[2] / max(_cat(p[0], p[1]), 1e-12) for p in cp)
            med = ratios[len(ratios) // 2]
            if med > 1.5 or med < 0.67:
                warnings.append(f"measured coreLoss points differ from catalog (median {med:.2f}x) - verify bench data")
    mim = meas_mat.get("inductance") or {}
    if mim:
        xs = mim.get("H_Oe") or mim.get("I_A")
        if not (xs and mim.get("L_uH")):
            errors.append("material.measured.inductance needs L_uH plus H_Oe or I_A arrays")
        elif len(xs) != len(mim["L_uH"]) or len(xs) < 2:
            errors.append("material.measured.inductance arrays must be equal length (>=2)")
        else:
            L0_uH = g["AL_nH"] * 1e-9 * m["winding"]["stacks"] * m["winding"]["N"] ** 2 * 1e6
            Lm0 = float(mim["L_uH"][int(np.argmin(np.asarray(xs, float)))])
            if abs(Lm0 - L0_uH) / max(L0_uH, 1e-9) > 0.25:
                warnings.append(f"measured L at lowest bias ({Lm0:.0f} uH) differs from analytic L0 "
                                f"({L0_uH:.0f} uH) by >25% - check N/stacks/AL or the measurement")

    # ---- 5. eta vs eta*PF mixing guard: points and maps must agree where they overlap ----
    op_pts = _get(package, "operating.points")
    eta_map = _get(m, "maps.etaByVin")
    if isinstance(op_pts, list) and isinstance(eta_map, dict):
        for p in op_pts:
            for k, v in eta_map.items():
                try: kv = float(k)
                except (TypeError, ValueError): continue
                if _is_num(v) and abs(kv - p["Vin"]) < 0.5:
                    prod = p["eta"] * p["PF"]
                    if abs(prod - v) / max(v, 1e-9) > 0.05:
                        warnings.append(f"maps.etaByVin[{k}]={v} disagrees with points eta*PF={prod:.4f} "
                                        f"at Vin={p['Vin']} (>5%): etaByVin must be the eta*PF PRODUCT")

    return ValidationResult(len(errors) == 0, errors, warnings)


# ====================================================================================
#  INPUT DATACLASSES (pure inputs; NO embedded material library)
# ====================================================================================
@dataclass
class OperatingPoint:
    Vin: float; Pout: float; eta: float; PF: float

@dataclass
class ConverterSpec:
    Vout: float; fsw: float; fline: float; nph: int; points: List[OperatingPoint]

@dataclass
class MaterialModel:
    name: str; Bsat: float
    loss_abc: Tuple[float, float, float]     # P = a*B^b*f[kHz]^c  (mW/cm^3, T, kHz)
    bias_abc: Tuple[float, float, float]     # %mu = 1/(a + b*H^c)  (H in Oe)
    loss_max_scale: float = 1.286
    loss_anchor: Optional[Tuple[float, float, float]] = None
    bias_anchors: Tuple[Tuple[float, float], ...] = ()
    def core_loss_density(self, Bac_pk_T, f_kHz):
        a, b, c = self.loss_abc
        return a * np.power(np.abs(Bac_pk_T), b) * np.power(f_kHz, c)
    def k_bias(self, H_oe):
        a, b, c = self.bias_abc
        return 1.0 / (a + b * np.power(np.maximum(H_oe, 1e-9), c)) / 100.0
    def Fd_integral(self):
        th = np.linspace(0, 2 * math.pi, 200001)
        return float(np.trapezoid(np.abs(np.cos(th)) ** self.loss_abc[2], th))
    def F_D(self, D, Ic):
        c = self.loss_abc[2]; D = np.clip(D, 1e-4, 1 - 1e-4)
        return (2.0 ** c) * (D ** (1 - c) + (1 - D) ** (1 - c)) / ((2 * math.pi) ** (c - 1) * Ic)
    def anchor_failures(self, tol_loss=0.03, tol_bias=1.0) -> List[str]:
        fails = []
        if self.loss_anchor:
            B, f, P = self.loss_anchor
            pred = float(self.core_loss_density(B, f))
            if abs(pred - P) / P > tol_loss:
                fails.append(f"loss anchor: pred {pred:.1f} vs {P:.1f} mW/cm^3")
        for H, pm in self.bias_anchors:
            pred = float(self.k_bias(H) * 100)
            if abs(pred - pm) > tol_bias:
                fails.append(f"bias anchor: {H} Oe pred {pred:.1f}% vs {pm:.1f}%")
        return fails

@dataclass
class CoreGeometry:
    Ae_mm2: float; le_mm: float; Ve_cm3: float; Wa_mm2: float
    OD_mm: float; ID_mm: float; HT_mm: float; AL_nom_nH: float
    AL_tol: float = 0.08; stacks: int = 1
    @property
    def Ae(self): return self.Ae_mm2 * self.stacks * 1e-6
    @property
    def Ve(self): return self.Ve_cm3 * self.stacks
    @property
    def le_cm(self): return self.le_mm / 10.0
    @property
    def Wa(self): return self.Wa_mm2
    @property
    def AL_total(self): return self.AL_nom_nH * self.stacks * 1e-9
    @property
    def width_mm(self): return (self.OD_mm - self.ID_mm) / 2.0
    @property
    def stack_height_mm(self): return self.HT_mm * self.stacks

@dataclass
class Winding:
    N: int; strand_d_mm: float; n_strands: int; n_par: int
    build_mm: float = 3.8; Rac_Rdc: float = 1.15
    @property
    def A_strand_mm2(self): return math.pi / 4 * self.strand_d_mm ** 2
    @property
    def A_bundle_mm2(self): return self.n_strands * self.A_strand_mm2
    @property
    def A_cu_mm2(self): return self.n_par * self.A_bundle_mm2

@dataclass
class AcceptanceLimits:
    L_target_uH: float
    Tamb_C: float = 50.0; Thot_C: float = 110.0
    FFcu_limit: float = 0.45; Jtarget: Tuple[float, float] = (3.0, 7.0)
    sat_margin_min: float = 0.43; Twind_C: float = 100.0
    Binner_max_T: Optional[float] = None   # optional upstream limit on crowded inner-radius B


# ====================================================================================
#  FIELD-PACKAGE LOADER (solved ROM overrides analytic; tracks provenance)
# ====================================================================================
class FieldOverrides:
    def __init__(self, fields: dict, mat: MaterialModel, core: CoreGeometry, N: int):
        self.f = fields or {}
        self.mat, self.core, self.N = mat, core, N
        self.prov = {
            "inductance": (self.f.get("inductance", {}) or {}).get("provenance", "fea") if "inductance" in self.f else "analytic",
            "windingAC":  (self.f.get("windingAC", {}) or {}).get("provenance", "fea")  if "windingAC"  in self.f else "analytic",
            "thermal":    (self.f.get("thermal", {}) or {}).get("provenance", "fea")    if "thermal"    in self.f else "analytic",
            "flux":       (self.f.get("flux", {}) or {}).get("provenance", "fea")       if "flux"       in self.f else "analytic",
        }
    @staticmethod
    def _interp(xs, ys, x):
        xs = np.asarray(xs, float); ys = np.asarray(ys, float)
        return float(np.interp(x, xs, ys))
    def L_henries(self, H_oe, L0_analytic):
        fi = self.f.get("inductance")
        if fi and fi.get("H") and fi.get("L_uH"):
            return self._interp(fi["H"], fi["L_uH"], H_oe) * 1e-6
        return float(self.mat.k_bias(H_oe)) * L0_analytic    # analytic biased L
    def rac_rdc(self, f_hz, analytic_value):
        w = self.f.get("windingAC")
        if w and w.get("freq_Hz") and w.get("RacOverRdc"):
            return self._interp(w["freq_Hz"], w["RacOverRdc"], f_hz)
        return analytic_value
    def thermal_nodes(self):
        t = self.f.get("thermal")
        if t and isinstance(t.get("nodes"), dict):
            n = t["nodes"]
            if _is_num(n.get("Rca_KperW")) and _is_num(n.get("Rwa_KperW")):
                return dict(Rca=n["Rca_KperW"], Rwa=n["Rwa_KperW"],
                            Rcw=n.get("Rcw_KperW", n["Rca_KperW"] * 0.5))
            if _is_num(n.get("thetaSA_KperW")):
                th = n["thetaSA_KperW"]; return dict(Rca=th * 2, Rwa=th * 2, Rcw=th * 0.5)
        return None
    def crowd_peak(self):
        fl = self.f.get("flux")
        if fl and fl.get("radial") and fl["radial"].get("r_mm") and fl["radial"].get("crowd"):
            return self._interp(fl["radial"]["r_mm"], fl["radial"]["crowd"], self.core.ID_mm / 2.0)
        return self.core.width_mm and ((self.core.ID_mm/2 + self.core.OD_mm/2)/2) / (self.core.ID_mm/2)


# ====================================================================================
#  PACKAGE -> dataclasses
# ====================================================================================
def build_inputs(package: dict):
    m = package["model"]; g = m["geometry"]; w = m["copper"]["wire"]; mat_d = m["material"]
    Ve_cm3 = (g["Ve_mm3"] / 1000.0) if g.get("Ve_mm3") is not None else g["Ve_cm3"]
    stacks = int(m["winding"]["stacks"])
    core = CoreGeometry(Ae_mm2=g["Ae_mm2"], le_mm=g["Le_mm"], Ve_cm3=Ve_cm3, Wa_mm2=g["Wa_mm2"],
                        OD_mm=g["OD_mm"], ID_mm=g["ID_mm"], HT_mm=g["HT_mm"], AL_nom_nH=g["AL_nH"],
                        AL_tol=g.get("AL_tol", 0.08), stacks=stacks)
    sm = mat_d["steinmetz"]; rt = mat_d["retention"]
    mat = MaterialModel(name=mat_d.get("name", "material"), Bsat=mat_d["Bsat"],
                        loss_abc=(sm["a"], sm["b"], sm["c"]), bias_abc=(rt["k0"], rt["k1"], rt["p"]),
                        loss_max_scale=mat_d.get("lossMaxScale", 1.286))
    anch = mat_d.get("anchors") or {}
    if anch.get("loss"): mat.loss_anchor = tuple(anch["loss"])
    if anch.get("bias"): mat.bias_anchors = tuple(tuple(x) for x in anch["bias"])
    wind = Winding(N=int(m["winding"]["N"]), strand_d_mm=w["strandDia_mm"], n_strands=int(w["strands"]),
                   n_par=int(w.get("parallel", 1) or 1), build_mm=m["winding"].get("build_mm", 3.8),
                   Rac_Rdc=m["copper"].get("RacRdc", 1.15))
    env = m["environment"]; acc = package.get("acceptance") or {}
    lim = AcceptanceLimits(L_target_uH=acc.get("L_target_uH", 0.0),
                           Tamb_C=env["Tamb_C"], Thot_C=env.get("Thot_C", 110.0),
                           FFcu_limit=acc.get("FFcu_limit", 0.45),
                           Jtarget=(acc.get("J_min", 3.0), acc.get("J_max", 7.0)),
                           sat_margin_min=acc.get("sat_margin_min", 0.43),
                           Binner_max_T=acc.get("Binner_max_T"))
    # operating points: explicit, else derived from maps + Prated + spec pcts
    pts_d = _get(package, "operating.points")
    if isinstance(pts_d, list) and pts_d:
        pts = [OperatingPoint(p["Vin"], p["Pout"], p["eta"], p["PF"]) for p in pts_d]
    else:
        Prated = m["design"]["Prated"]; eta_map = m["maps"]["etaByVin"]
        loPct = m["design"].get("specLowLineMaxPct", 100.0); hiPct = m["design"].get("specHighLineMaxPct", 100.0)
        pts = []
        for vs in sorted(eta_map.keys(), key=lambda x: float(x)):
            v = float(vs); pct = loPct if v <= 132 else hiPct
            # etaByVin is the eta*PF product; fold into eta with PF=1 (Iin_rms uses product)
            pts.append(OperatingPoint(v, Prated * pct / 100.0, eta_map[vs], 1.0))
    spec = ConverterSpec(Vout=m["design"]["Vout"], fsw=m["design"]["fsw"],
                         fline=m["design"]["lineHz"], nph=int(m["design"]["nph"]), points=pts)
    cooling = (m.get("cooling") or {}).get("mode", "natural")
    airflow = (m.get("cooling") or {}).get("airflow_mps", 2.0)
    rho = m["copper"].get("rho20_ohm_m", RHO_CU_20_DEFAULT)
    alpha = m["copper"].get("alphaCu", ALPHA_CU_DEFAULT)
    measured = m["copper"].get("measured") or {}

    # ---- real-world (Tier-3) material overrides: measured > FEA fields > analytic ----
    fields = dict(package.get("fields") or {})
    meas_mat = mat_d.get("measured") or {}
    coreLoss_prov = "analytic"
    clm = meas_mat.get("coreLoss") or {}
    if isinstance(clm.get("steinmetz"), dict):          # bench-refit Steinmetz supplied directly
        ms = clm["steinmetz"]
        mat.loss_abc = (ms["a"], ms["b"], ms["c"]); coreLoss_prov = "measured"
    elif clm.get("points"):                             # raw bench P(B,f) points -> fit here
        mat.loss_abc = _fit_steinmetz(clm["points"]); coreLoss_prov = "measured"
    if coreLoss_prov == "measured":
        mat.loss_anchor = None   # catalog-transcription anchor no longer applies to a measured fit;
                                 # measured-vs-catalog consistency is checked in validate() instead
    if coreLoss_prov == "measured" and _is_num(clm.get("maxScale")):
        mat.loss_max_scale = clm["maxScale"]            # measured uncertainty band (upstream-supplied;
                                                        # otherwise the catalog band is kept, conservative)
    mim = meas_mat.get("inductance") or {}
    if mim.get("L_uH") and (mim.get("H_Oe") or mim.get("I_A")):
        if mim.get("H_Oe"):
            Hax = [float(h) for h in mim["H_Oe"]]
        else:                                           # convert bench bias current to H via N, le
            Hax = [0.4 * math.pi * int(m["winding"]["N"]) * float(i) / (g["Le_mm"] / 10.0)
                   for i in mim["I_A"]]
        order = np.argsort(Hax)
        fields["inductance"] = {"H": [Hax[i] for i in order],
                                "L_uH": [float(mim["L_uH"][i]) for i in order],
                                "provenance": "measured"}   # outranks any FEA table
    return spec, core, mat, wind, lim, cooling, airflow, rho, alpha, measured, fields, coreLoss_prov


# ====================================================================================
#  ENGINE (S1..S12) — physics identical to the verified reference
# ====================================================================================
def skin_depth_m(f_hz, rho): return math.sqrt(rho / (math.pi * f_hz * MU0))
def H_oe(N, I, le_cm): return 0.4 * math.pi * N * I / le_cm

def _fit_steinmetz(points):
    """Fit P = a*B^b*f^c (mW/cm^3; B in T, f in kHz) to measured rows [[B_T, f_kHz, P_mWcm3],...]
    by log-linear least squares. Needs >=3 points spanning B and f. (Tier-3 path.)"""
    pts = np.asarray(points, float)
    if pts.ndim != 2 or pts.shape[1] != 3 or pts.shape[0] < 3 or np.any(pts <= 0):
        raise SpecError(["material.measured.coreLoss.points must be >=3 positive rows of [B_T, f_kHz, P_mWcm3]"])
    X = np.column_stack([np.ones(len(pts)), np.log(pts[:, 0]), np.log(pts[:, 1])])
    coef, *_ = np.linalg.lstsq(X, np.log(pts[:, 2]), rcond=None)
    return (float(np.exp(coef[0])), float(coef[1]), float(coef[2]))

def harmonic_ac_excess_factor():
    odd = np.arange(1, 200, 2)
    return float(np.sum((1/odd**2)**2 * odd**2) / np.sum((1/odd**2)**2))   # ~1.213

def analyze(spec, core, mat, wind, lim, cooling, airflow, rho, alpha, measured, fields, coreLoss_prov="analytic",
            core_loss_method="cycle_avg_igse", n_theta=40001) -> dict:
    fo = FieldOverrides(fields, mat, core, wind.N)
    mat_fails = mat.anchor_failures()
    Ic = mat.Fd_integral()
    Vout, fsw, nph, N = spec.Vout, spec.fsw, spec.nph, wind.N
    le_cm, Ae = core.le_cm, core.Ae
    L0_nom = core.AL_total * N ** 2
    L0_min, L0_max = L0_nom * (1 - core.AL_tol), L0_nom * (1 + core.AL_tol)

    MLT_mm = 2 * (core.width_mm + core.stack_height_mm) + wind.build_mm
    ell_cu = N * MLT_mm / 1000.0
    # Rdc: measured (provenance) else geometry
    if _is_num(measured.get("RdcTotal_20C")):
        DCR25 = measured["RdcTotal_20C"] * (1 + alpha * 5); rdc_src = "measured"
    elif _is_num(measured.get("RdcPerMeter_20C")):
        DCR25 = measured["RdcPerMeter_20C"] * ell_cu * (1 + alpha * 5); rdc_src = "measured"
    else:
        DCR25 = rho * (1 + alpha * 5) * ell_cu / (wind.n_par * wind.A_bundle_mm2 * 1e-6); rdc_src = "computed"
    def DCR(T): return DCR25 * (1 + alpha * (T - 25))
    FFcu = wind.A_cu_mm2 * N / core.Wa
    delta = skin_depth_m(fsw, rho)
    skin_ok = wind.strand_d_mm / 1000.0 < 2 * delta
    rac_rdc = fo.rac_rdc(fsw, wind.Rac_Rdc)
    harm_fac = harmonic_ac_excess_factor()
    crowd = fo.crowd_peak()

    theta = np.linspace(1e-3, math.pi - 1e-3, n_theta)
    rows = []
    for op in spec.points:
        Pin = op.Pout / op.eta
        Vpk = math.sqrt(2) * op.Vin
        Iin_rms = Pin / (op.Vin * op.PF)
        Iin_pk = math.sqrt(2) * Iin_rms
        Iphi_crest = Iin_pk / nph
        Dpk = 1 - Vpk / Vout
        Hc = H_oe(N, Iphi_crest, le_cm)
        L_nom = fo.L_henries(Hc, L0_nom)          # biased L (fea table or analytic k*L0)
        kc = L_nom / L0_nom if L0_nom else 0.0
        Vin_t = Vpk * np.sin(theta)
        D_t = np.clip(1 - Vin_t / Vout, 0, 1)
        iavg = Iphi_crest * np.sin(theta)
        dIpp = Vin_t * D_t / (L_nom * fsw)
        Bac_t = Vin_t * D_t / (2 * N * Ae * fsw)
        Bac_crest = Vpk * Dpk / (2 * N * Ae * fsw)
        ipk_inst = iavg + dIpp / 2
        Bmax = float((L_nom * ipk_inst / (N * Ae)).max())
        Ipk_inst = float(ipk_inst.max())
        Hpk = H_oe(N, Ipk_inst, le_cm)
        Lfull_min_pk = (fo.L_henries(Hpk, L0_min))      # min-L guarantee point (AL_min)
        Irms_LF = Iphi_crest / math.sqrt(2)
        Irms_HF = math.sqrt(np.trapezoid((dIpp / (2 * math.sqrt(3))) ** 2, theta) / math.pi)
        Iphi_rms = math.sqrt(Irms_LF ** 2 + Irms_HF ** 2)
        def Pcu(T): return Iphi_rms ** 2 * DCR(T) + Irms_HF ** 2 * (rac_rdc - 1) * harm_fac * DCR(T)
        Pcu100, Pcu25 = Pcu(lim.Twind_C), Pcu(25.0)
        if core_loss_method == "cycle_avg_igse":
            Pcore_t = mat.core_loss_density(Bac_t, fsw / 1e3) * mat.F_D(D_t, Ic) * core.Ve / 1e3
            Pcore = float(np.trapezoid(Pcore_t, theta) / math.pi)
        elif core_loss_method == "peak_point":
            Pcore = float(mat.core_loss_density(Bac_crest, fsw / 1e3) * core.Ve / 1e3)
        else:
            raise ValueError("core_loss_method must be 'cycle_avg_igse' or 'peak_point'")
        Pcore_max = Pcore * mat.loss_max_scale
        rows.append(dict(Vin=op.Vin, Iphi_crest=Iphi_crest, Iphi_rms=Iphi_rms, Irms_HF=Irms_HF,
                         Dpk=Dpk, Hc=Hc, k=kc, L_nom_uH=L_nom*1e6,
                         Bac_crest=Bac_crest, Bmax=Bmax, B_inner=Bmax*crowd,
                         Hpk=Hpk, Lfull_min_pk_uH=Lfull_min_pk*1e6,
                         Pcu25=Pcu25, Pcu100=Pcu100, Pcore=Pcore, Pcore_max=Pcore_max,
                         Ptot_typ=Pcore+Pcu100, Ptot_max=Pcore_max+Pcu100))

    # thermal
    nodes = fo.thermal_nodes()
    OD_w = core.OD_mm + 2 * (wind.A_bundle_mm2 ** 0.5)
    OH = core.stack_height_mm + 2 * (wind.A_bundle_mm2 ** 0.5) + 6.6
    hole = max(core.ID_mm - 2 * (wind.A_bundle_mm2 ** 0.5), 1.0)
    SA = (math.pi*OD_w*OH + (math.pi/2)*(OD_w**2 - hole**2) + math.pi*hole*OH) / 100.0
    def dT_natural(P): return (P * 1e3 / SA) ** 0.833
    def dT_forced(P):
        L = OD_w/1000.0; Re = airflow*L/1.57e-5; Nu = 0.466*Re**0.5*0.71**(1/3); h = Nu*0.0263/L
        Ts = lim.Tamb_C + dT_natural(P); hrad = 0.9*5.67e-8*4*((Ts+lim.Tamb_C)/2+273.15)**3
        return P / (SA/1e4 * (h + hrad))
    for r in rows:
        if nodes:                                   # FEA/CFD node resistances -> winding-node rise
            r["dT"] = (r["Ptot_max"]) * (nodes["Rwa"])   # simple node rise at winding
            thermal_src = fo.prov["thermal"]
        else:
            r["dT"] = dT_forced(r["Ptot_max"]) if cooling == "forced" else dT_natural(r["Ptot_max"])
            thermal_src = "analytic"

    wc_loss = max(rows, key=lambda r: r["Ptot_max"])
    wc_B = max(rows, key=lambda r: r["Bmax"])
    wc_Bi = max(rows, key=lambda r: r["B_inner"])
    wc_dT = max(rows, key=lambda r: r["dT"])
    Lmin_guarantee = min(r["Lfull_min_pk_uH"] for r in rows)
    J = max(r["Iphi_rms"] for r in rows) / wind.A_cu_mm2

    asserts = {
        "material_anchors": (len(mat_fails) == 0, mat_fails),
        "L_guarantee": (Lmin_guarantee >= lim.L_target_uH, f"{Lmin_guarantee:.1f} >= {lim.L_target_uH} uH"),
        "saturation": (wc_B["Bmax"] <= (1 - lim.sat_margin_min) * mat.Bsat,
                       f"Bmax {wc_B['Bmax']:.3f} T vs Bsat {mat.Bsat} T"),
        "window_fill": (FFcu <= lim.FFcu_limit, f"FFcu {FFcu*100:.1f}% <= {lim.FFcu_limit*100:.0f}%"),
        "skin_depth": (skin_ok, f"strand {wind.strand_d_mm} mm < 2*delta {2*delta*1e3:.3f} mm"),
        "thermal": (wc_dT["dT"] <= (lim.Thot_C - lim.Tamb_C), f"dT {wc_dT['dT']:.1f} <= {lim.Thot_C-lim.Tamb_C:.0f} C"),
        "current_density": (lim.Jtarget[0] <= J <= lim.Jtarget[1] or J < lim.Jtarget[1],
                            f"J {J:.2f} A/mm^2 (limit {lim.Jtarget[1]})"),
    }
    # B-basis parity rule: 'saturation' checks MEAN-PATH B (verification basis).
    # The crowded inner-radius value is checked ONLY if upstream supplies Binner_max_T.
    if lim.Binner_max_T is not None:
        asserts["inner_flux"] = (wc_Bi["B_inner"] <= lim.Binner_max_T,
                                 f"B_inner {wc_Bi['B_inner']:.3f} T <= {lim.Binner_max_T} T (crowded)")
    verdict = "APPROVE" if all(v[0] for v in asserts.values()) else "REJECT"
    provenance = {"inductance": fo.prov["inductance"], "windingAC": fo.prov["windingAC"],
                  "thermal": thermal_src, "flux": fo.prov["flux"], "copperRdc": rdc_src,
                  "coreLoss": coreLoss_prov, "window": "computed"}
    # provenance -> confidence tier (parity with the browser viewer): T0 input, T1 analytic,
    # T2 FEA-corrected, T3 measured. Tells the parent agent the confidence of each quantity.
    _TIER = {"input": "T0", "analytic": "T1", "computed": "T1", "fea": "T2", "measured": "T3"}
    tier = {k: _TIER.get(v, "T1") for k, v in provenance.items()}
    return dict(
        meta=dict(material=mat.name, Bsat=mat.Bsat, stacks=core.stacks, N=N,
                  core_loss_method=core_loss_method, cooling=cooling,
                  schemaVersion=SCHEMA_VERSION),
        statics=dict(L0_min_uH=L0_min*1e6, L0_nom_uH=L0_nom*1e6, L0_max_uH=L0_max*1e6,
                     MLT_mm=MLT_mm, ell_cu_m=ell_cu, DCR25_mohm=DCR25*1e3, DCR100_mohm=DCR(100)*1e3,
                     FFcu=FFcu, J_AperMM2=J, skin_depth_mm=delta*1e3, SA_cm2=SA, crowd_peak=crowd,
                     Rac_Rdc=rac_rdc),
        points=rows,
        worst=dict(loss=dict(Vin=wc_loss["Vin"], Ptot_typ=wc_loss["Ptot_typ"], Ptot_max=wc_loss["Ptot_max"]),
                   Bmax=dict(Vin=wc_B["Vin"], Bmax=wc_B["Bmax"],
                             sat_margin_pct=(mat.Bsat-wc_B["Bmax"])/wc_B["Bmax"]*100),
                   Binner=dict(Vin=wc_Bi["Vin"], B_inner=wc_Bi["B_inner"]),
                   dT=dict(Vin=wc_dT["Vin"], dT=wc_dT["dT"]),
                   Lmin_guarantee_uH=Lmin_guarantee),
        asserts=asserts, verdict=verdict, provenance=provenance, tier=tier)


# ====================================================================================
#  PUBLIC API  (headless; JSON in/out)
# ====================================================================================
def compute(package: dict, core_loss_method: str = "cycle_avg_igse") -> dict:
    """Validate then compute. Raises SpecError on hard errors; warnings ride with the result."""
    vr = validate(package)
    if not vr.ok:
        raise SpecError(vr.errors)
    inputs = build_inputs(package)
    res = analyze(*inputs, core_loss_method=core_loss_method)
    res["validation"] = vr.as_dict()
    return res

def _json_default(o):
    if isinstance(o, (np.floating,)): return float(o)
    if isinstance(o, (np.integer,)): return int(o)
    if isinstance(o, np.ndarray): return o.tolist()
    raise TypeError(str(type(o)))

def compute_from_json(text_or_obj, core_loss_method: str = "cycle_avg_igse") -> str:
    pkg = json.loads(text_or_obj) if isinstance(text_or_obj, str) else text_or_obj
    try:
        res = compute(pkg, core_loss_method=core_loss_method)
        return json.dumps(res, default=_json_default)
    except SpecError as e:
        return json.dumps({"ok": False, "errors": e.errors}, default=_json_default)

if __name__ == "__main__":
    raw = open(sys.argv[1]).read() if len(sys.argv) > 1 else sys.stdin.read()
    print(compute_from_json(raw))
