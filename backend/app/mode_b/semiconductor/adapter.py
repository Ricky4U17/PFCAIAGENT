"""
Semiconductor loss — design adapter + consistency gate
======================================================
The ONLY bridge between our central design pipeline and the vendored loss engine
(pfc_loss_model). It builds the engine `cfg` entirely from the single-source-of-truth
operating grid every report chapter uses (`build_design_ops_table` + step2/step5), so the
semiconductor loss step can never diverge from the rest of the design.

Hard rule: the engine receives our η / PF / Pout / Iin_rms / Lφ verbatim (via its override
hooks) and recomputes nothing we already computed. After it runs, `verify_consistency`
asserts the engine's echoed operating point equals our upstream values for every quantity —
if anything drifts beyond tolerance the run is rejected (no silent discrepancy).

Losses are evaluated at EVERY input voltage (all 9 operating points); the per-point rows are
returned for the documentation agent to build the final total-loss tables.
"""
from __future__ import annotations
import numpy as np

from . import pfc_loss_model as engine
from . import pfc_component_intake as intake
from app.mode_b.calculations import (
    canonical_ops_table, build_design_ops_table, step2_input_params, step5_phase_rms,
)


# ── 1. operating grid: the single source of truth ────────────────────────────
def build_design_ops(design: dict):
    """Return (ops, s2, L_phi, iph, L_pts) from THIS design's corners — identical to every
    other chapter. ops cols = [Vin_rms, Pout, eta, PF, Iph_rms]; s2 carries Pin / Iin_rms /
    Iin_pk / Dpk; L_phi is the nominal/scalar per-channel inductance; L_pts[H] is the per-operating-
    point inductance (powder-core bias roll-off via design['L_phi_curve'], else constant = L_phi).
    Iph_rms is recomputed with the per-point L so ripple tracks the real inductance at each line.
    """
    vin_min = float(design["vin_min"]);  vin_max = float(design["vin_max"])
    pout_lo = float(design["pout_lo"]);  pout_hi = float(design["pout_hi"])
    vout    = float(design["vout"]);     fsw     = float(design["fsw"])
    r_input = float(design["r_input"])
    ops, L_auto = build_design_ops_table(vin_min, vin_max, pout_lo, pout_hi, vout, fsw, r_input)
    # prefer the designer-approved inductor value; recompute Iph_rms with the L actually used
    L_phi = float(design["L_phi_uH"]) * 1e-6 if design.get("L_phi_uH") else L_auto
    # per-operating-point inductance: powder cores roll off with DC bias, so L varies with line.
    lc = design.get("L_phi_curve")
    if lc:
        xs = [float(p[0]) for p in lc]; ys = [float(p[1]) * 1e-6 for p in lc]
        L_pts = np.array([float(np.interp(float(ops[i, 0]), xs, ys)) for i in range(len(ops))])
    else:
        L_pts = np.full(len(ops), L_phi)
    s2 = step2_input_params(vout, ops[:, :4])
    iph = np.array([step5_phase_rms(s2["Vin_pk"][i], s2["Iin_pk"][i], L_pts[i], fsw, vout)[0]
                    for i in range(len(s2["Vin_rms"]))])
    ops = ops.copy(); ops[:, 4] = iph
    return ops, s2, L_phi, iph, L_pts


# metadata kept with each part for the report but NOT passed to the engine dataclasses
_META_KEYS = ("manufacturer", "part_number", "mpn", "notes", "datasheet_url", "_estimated")

def _clean_block(block: dict):
    """Split a component block into (engine params, metadata). Drops metadata keys and any
    empty/None values so the engine uses its built-in default for unset optional fields."""
    block = dict(block or {})
    meta = {k: block.pop(k) for k in list(block) if k in _META_KEYS}
    params = {k: v for k, v in block.items() if v not in (None, "", [])}
    return params, meta


# ── 2. assemble the engine cfg from our design + the 3 confirmed parts ────────
def build_semi_cfg(design: dict, mosfet: dict, diode: dict, bridge: dict, thermal: dict):
    """Build the engine `cfg` dict. Every operating-point quantity comes from our grid and is
    handed to the engine via its override hooks (curves keyed by the exact Vac points, so the
    engine never interpolates). Returns (cfg, ref) where `ref` holds the upstream values the
    consistency gate checks against."""
    ops, s2, L_phi, iph, L_pts = build_design_ops(design)
    vac  = [round(float(v), 4) for v in ops[:, 0]]
    nch  = int(design["nch"]); vout = float(design["vout"]); fsw = float(design["fsw"])
    fline = float(design["fline"])
    mos_p, mos_m = _clean_block(mosfet); dio_p, dio_m = _clean_block(diode)
    br_p,  br_m  = _clean_block(bridge); th_p,  _     = _clean_block(thermal)
    cfg = {
        "spec": {
            "vo": vout, "fsw": fsw, "fline": fline, "nch": nch, "L": L_phi,
            "eta_curve":     [vac, [float(x) for x in ops[:, 2]]],
            "pf_curve":      [vac, [float(x) for x in ops[:, 3]]],
            "po_curve":      [vac, [float(x) for x in ops[:, 1]]],
            "iin_rms_curve": [vac, [float(x) for x in s2["Iin_rms"]]],   # TOTAL input RMS
            "L_curve":       [vac, [float(x) for x in L_pts]],           # per-point bias inductance
        },
        "mosfet": mos_p, "diode": dio_p, "bridge": br_p, "thermal": th_p,
        "run": {"vac_list": vac},
    }
    ref = {
        "nch": nch, "L_phi_uH": L_phi * 1e6, "vout": vout,
        "parts": {"mosfet": mos_m, "diode": dio_m, "bridge": br_m},
        "points": [{
            "Vac": vac[i], "Pout": float(ops[i, 1]), "eta": float(ops[i, 2]),
            "PF": float(ops[i, 3]), "Pin": float(s2["Pin"][i]),
            "Iin_rms": float(s2["Iin_rms"][i]), "Iin_pk": float(s2["Iin_pk"][i]),
            "Ipk_ch": float(s2["Iin_pk"][i]) / nch, "Iph_rms": float(iph[i]),
            "Dpk": float(s2["Dpk"][i]), "L_pt_uH": float(L_pts[i]) * 1e6,
        } for i in range(len(vac))],
    }
    return cfg, ref


# ── 3. the consistency gate ──────────────────────────────────────────────────
def _rel(got, exp, eps=1e-9):
    return abs(float(got) - float(exp)) / max(abs(float(exp)), eps)

def verify_consistency(rows: list, cfg: dict, ref: dict, tol: float = 0.02):
    """Compare the engine's echoed operating point against our upstream values for every
    quantity. Returns (ok, issues). ok=False ⇒ the loss numbers are NOT consistent with the
    rest of the design and must not be shipped."""
    issues = []
    nch = ref["nch"]; vout = ref["vout"]
    checks = [  # (label, engine key, ref key, transform of ref)
        ("Vac",      "Vac",       "Vac",     lambda p: p["Vac"]),
        ("Pout",     "Po",        "Pout",    lambda p: p["Pout"]),
        ("Pin",      "Pin",       "Pin",     lambda p: p["Pin"]),
        ("eta_%",    "eta_in_%",  "eta",     lambda p: 100.0 * p["eta"]),
        ("PF",       "PF_in",     "PF",      lambda p: p["PF"]),
        ("Iin_rms",  "Iin_rms",   "Iin_rms", lambda p: p["Iin_rms"]),
        ("Ipk_ch",   "Ipk_ch",    "Ipk_ch",  lambda p: p["Ipk_ch"]),
        ("L_eff_uH", "L_eff_uH",  "L_pt",    lambda p: p.get("L_pt_uH", ref["L_phi_uH"])),
    ]
    for i, (r, p) in enumerate(zip(rows, ref["points"])):
        for label, ekey, _rk, fexp in checks:
            exp = fexp(p); got = r.get(ekey)
            if got is None or _rel(got, exp) > tol:
                issues.append({"point": i, "Vac": p["Vac"], "quantity": label,
                               "design": round(float(exp), 6), "engine": (None if got is None else round(float(got), 6))})
        # structural duty check: engine d(θ)=1−Vin/Vo ⇒ peak-of-line duty must equal our Dpk
        d_eng = 1.0 - np.sqrt(2.0) * p["Vac"] / vout
        if _rel(d_eng, p["Dpk"]) > tol:
            issues.append({"point": i, "Vac": p["Vac"], "quantity": "Dpk",
                           "design": round(p["Dpk"], 6), "engine": round(float(d_eng), 6)})
    return (len(issues) == 0), issues


def _native(o):
    """Recursively convert numpy scalars/arrays to plain Python so the result is JSON-safe."""
    if isinstance(o, dict):
        return {k: _native(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_native(v) for v in o]
    if isinstance(o, np.generic):
        return o.item()
    if isinstance(o, np.ndarray):
        return _native(o.tolist())
    return o


# ── 4. the public entry point ────────────────────────────────────────────────
def calculate_semiconductor_losses(design: dict, mosfet: dict, diode: dict,
                                    bridge: dict, thermal: dict, tj_limit: dict | None = None,
                                    tol: float = 0.02):
    """Full chain: validate → sweep all 9 input voltages → consistency gate.

    Returns a dict:
      validation : {ok, issues}            — the intake gate (refuse if not ok)
      consistency: {ok, issues}            — design-vs-engine cross-check
      per_point  : [flattened row, ...]    — losses + Tj at EVERY input voltage
      summary    : worst-case losses / temperatures across the sweep
      cfg        : the assembled engine cfg (for the report / debugging)
    """
    cfg, ref = build_semi_cfg(design, mosfet, diode, bridge, thermal)

    ok, vissues = intake.validate_design(cfg)
    vissues_list = vissues.to_dict("records") if hasattr(vissues, "to_dict") else vissues
    if not ok:
        return _native({"validation": {"ok": False, "issues": vissues_list},
                        "consistency": None, "per_point": [], "summary": None, "cfg": cfg})

    rows = [engine.flatten_result(r) for r in engine.simulate_vac_sweep(cfg)]
    cok, cissues = verify_consistency(rows, cfg, ref, tol=tol)

    # worst-case across the sweep (for the headline / Tj-limit checks)
    def _worst(key): return max(rows, key=lambda r: r.get(key, 0.0))
    summary = {
        "P_SEMI_max":   max(r["P_SEMI_total"]  for r in rows),
        "P_FET_max":    max(r["P_FET_total"]   for r in rows),
        "P_DIODE_max":  max(r["P_DIODE_total"] for r in rows),
        "P_BRIDGE_max": max(r["P_BRIDGE_total"]for r in rows),
        "Tj_FET_max":   max(r["Tj_FET"]        for r in rows),
        "Tj_DIODE_max": max(r["Tj_DIODE"]      for r in rows),
        "Tj_BRIDGE_max":max(r["Tj_BRIDGE_top"] for r in rows),
        "worst_loss_Vac": _worst("P_SEMI_total")["Vac"],
        "worst_TjFET_Vac": _worst("Tj_FET")["Vac"],
    }
    if tj_limit:
        summary["tj_pass"] = {
            "fet":    summary["Tj_FET_max"]   <= tj_limit.get("fet", 1e9),
            "diode":  summary["Tj_DIODE_max"] <= tj_limit.get("diode", 1e9),
            "bridge": summary["Tj_BRIDGE_max"]<= tj_limit.get("bridge", 1e9),
        }
    return _native({"validation": {"ok": True, "issues": []},
                    "consistency": {"ok": cok, "issues": cissues},
                    "per_point": rows, "summary": summary, "cfg": cfg})


def trace_point(design: dict, mosfet: dict, diode: dict, bridge: dict, thermal: dict,
                vac: float | None = None):
    """Converged intermediate quantities at ONE operating point (default: the worst-case loss
    point) so the report can show each loss mechanism's step-by-step substitution with the
    engine's OWN numbers. Returns the engine `trace` dict (JSON-safe)."""
    cfg, _ = build_semi_cfg(design, mosfet, diode, bridge, thermal)
    sp, mos, dio, br, th = engine.design_from_dict(cfg)
    vac_list = cfg["run"]["vac_list"]
    if vac is None:                                   # pick the worst-case semiconductor-loss point
        rows = [engine.simulate_point(float(v), sp, mos, dio, br, th) for v in vac_list]
        vac = float(max(rows, key=lambda r: r["P_SEMI_total"])["Vac"])
    r = engine.simulate_point(float(vac), sp, mos, dio, br, th, return_trace=True)
    return _native(r["trace"])


# ── reference design + smoke test (run: python -m app.mode_b.semiconductor.adapter) ──
REFERENCE_DESIGN = {
    "vin_min": 90, "vin_max": 264, "pout_lo": 1700, "pout_hi": 3600,
    "vout": 393.7, "fsw": 70000, "fline": 60, "nch": 2, "r_input": 0.20, "L_phi_uH": 235,
}
REFERENCE_PARTS = {
    "mosfet": {"tech": "sic", "rdson_25": 0.060, "rdson_tj": [[25, 125], [1.0, 1.4]],
               "ciss": 1500e-12, "qgd": 18e-9, "vth": 4.0, "vpl": 7.0, "qg": 60e-9,
               "eoss_at_v": [[100, 400], [1.5e-6, 6e-6]], "rth_jc": 0.6,
               "vg": 18.0, "rg": 4.0, "rth_cs": 0.3},
    "diode":  {"is_sic": True, "vf_curve": [[1, 5, 16], [1.05, 1.35, 1.7]], "qc": 20e-9,
               "rth_jc": 0.7, "rth_cs": 0.3},
    "bridge": {"topology": "diode", "vf_curve": [[1, 12, 24], [0.75, 0.95, 1.15]],
               "n_parallel": 2, "rth_jc": 1.0, "rth_cs": 0.5},
    "thermal": {"t_ambient": 45.0, "rth_sa": 0.35},
}

if __name__ == "__main__":
    r = calculate_semiconductor_losses(REFERENCE_DESIGN, REFERENCE_PARTS["mosfet"],
            REFERENCE_PARTS["diode"], REFERENCE_PARTS["bridge"], REFERENCE_PARTS["thermal"],
            tj_limit={"fet": 150, "diode": 150, "bridge": 130})
    assert r["validation"]["ok"], r["validation"]["issues"]
    assert r["consistency"]["ok"], r["consistency"]["issues"]
    assert len(r["per_point"]) == 9
    print(f"OK — validation + consistency passed for all {len(r['per_point'])} operating points")
    print("worst-case semi loss %.1f W @ %.0f Vac; Tj_FET_max %.0f C"
          % (r["summary"]["P_SEMI_max"], r["summary"]["worst_loss_Vac"], r["summary"]["Tj_FET_max"]))
