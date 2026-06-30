"""
Input-protection design adapter  (MOV surge  +  NTC inrush)
===========================================================
The only bridge between our central design pipeline and the two vendored sizing engines
(`mov_surge_select`, `ntc_bypass_select`). It builds each engine's Spec from the single-source
operating grid + the parts already chosen upstream, so input-protection sizing can never
diverge from the rest of the design:

  NTC  : V_ac range + worst-case I_in,rms (from the design grid), C_out and bus voltage
         (from the approved capacitor / Step 15).
  MOV  : V_ac range (grid), the downstream device withstand V_ds (from the SELECTED MOSFET),
         and the bulk-cap voltage rating (approved capacitor).

Designer knobs (inrush target, IEC test level / performance criterion, margins) ride on top as
explicit overrides — everything else is carried in, not re-entered.
"""
from __future__ import annotations

from . import ntc_bypass_select as ntc
from . import mov_surge_select as mov
# reuse the SAME operating grid every chapter uses (worst-case input RMS current)
from app.mode_b.semiconductor.adapter import build_design_ops


# ── helpers ───────────────────────────────────────────────────────────────────
def _worst_iin_rms(design: dict) -> float:
    """Worst-case (maximum) total input RMS current across the 9-point grid."""
    _, s2, *_ = build_design_ops(design)
    return float(max(s2["Iin_rms"]))


def _native(o):
    """Make dataclass / numpy payloads JSON-safe."""
    import numpy as np
    from dataclasses import is_dataclass, asdict
    if is_dataclass(o):
        return _native(asdict(o))
    if isinstance(o, dict):
        return {k: _native(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_native(v) for v in o]
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    return o


# ── NTC inrush limiter ────────────────────────────────────────────────────────
def build_ntc_spec(design: dict, cap: dict | None = None, opts: dict | None = None) -> ntc.Spec:
    cap = cap or {}; opts = opts or {}
    cout_f = opts.get("cout")
    if cout_f is None:                                   # from the approved capacitor (Step 15)
        c_uf = cap.get("C_total_uF") or cap.get("C_uF") or cap.get("cout_uF")
        cout_f = (float(c_uf) * 1e-6) if c_uf else 2200e-6
    iin_worst = opts.get("i_rms_worst")
    if iin_worst is None:
        try:
            iin_worst = _worst_iin_rms(design)
        except Exception:
            iin_worst = 0.0
    return ntc.Spec(
        vac_min=float(design.get("vin_min", 90)),
        vac_max=float(design.get("vin_max", 264)),
        vac_nom=float(opts.get("vac_nom", 230)),
        f_line=float(design.get("fline", 60)),
        vout_bus=float(design.get("vout", 390)),
        cout=float(cout_f),
        i_inrush_target=float(opts.get("i_inrush_target", 60.0)),
        p_out=0.0,                                        # use the grid's I_rms verbatim
        i_rms_worst=float(iin_worst or 0.0),
        r_line=float(opts.get("r_line", 0.0)), r_emi=float(opts.get("r_emi", 0.0)),
        r_esr=float(opts.get("r_esr", 0.0)), r_bridge=float(opts.get("r_bridge", 0.0)),
        energy_margin=float(opts.get("energy_margin", 1.5)),
        r25_margin=float(opts.get("r25_margin", 1.10)),
        vref_pulse=float(opts.get("vref_pulse", 345.0)),
        tau_multiple=float(opts.get("tau_multiple", 4.0)),
        relay_v_margin=float(opts.get("relay_v_margin", 1.25)),
        ambient_c=float(opts.get("ambient_c", 45.0)),
    )


def calculate_ntc(design: dict, cap: dict | None = None, opts: dict | None = None) -> dict:
    """Size the NTC inrush limiter + bypass relay; returns sizing + catalog screen (JSON-safe)."""
    s = build_ntc_spec(design, cap, opts)
    r = ntc.compute(s)
    screen = [{"name": n, "ok": bool(ok), "reasons": rs} for n, ok, rs in ntc.screen_catalog(s, r)]
    return _native({"spec": s, "result": r, "catalog": screen,
                    "sources": {"cout_uF": s.cout * 1e6, "i_rms_worst": s.i_rms_worst,
                                "vac_max": s.vac_max, "vout_bus": s.vout_bus}})


# ── MOV surge protector ───────────────────────────────────────────────────────
def build_mov_spec(design: dict, mosfet: dict | None = None, cap: dict | None = None,
                   opts: dict | None = None) -> mov.Spec:
    mosfet = mosfet or {}; cap = cap or {}; opts = opts or {}
    vds = opts.get("device_vds")
    if vds is None:                                       # downstream withstand = SELECTED MOSFET V_DS
        vds = mosfet.get("vdss") or mosfet.get("v_rating") or 650.0
    vds = float(vds)
    absmax = float(opts.get("device_absmax", vds))
    cap_v = opts.get("cap_v_rating")
    if cap_v is None:
        cap_v = cap.get("V_rating") or cap.get("v_rating_V") or cap.get("Vdc_rating") or 450.0
    level = opts.get("level", 3)                          # engine keys are ints 1-4 or "X"
    if isinstance(level, str):
        level = int(level) if level.strip().isdigit() else level.strip().upper()
    return mov.Spec(
        vac_max=float(design.get("vin_max", 264)),
        vac_nom=float(opts.get("vac_nom", 230)),
        level=level,
        criterion=str(opts.get("criterion", "A")).strip().upper(),
        custom_v_ll=(float(opts["custom_v_ll"]) if opts.get("custom_v_ll") not in (None, "") else None),
        custom_v_le=(float(opts["custom_v_le"]) if opts.get("custom_v_le") not in (None, "") else None),
        common_mode_protection=bool(opts.get("common_mode_protection", True)),
        device_vds=vds, device_absmax=max(absmax, vds),
        cap_v_rating=float(cap_v),
        v1ma_ratio=float(opts.get("v1ma_ratio", 1.60)),
        varistor_alpha=float(opts.get("varistor_alpha", 30.0)),
        imax_margin=float(opts.get("imax_margin", 3.0)),
        pulse_count=int(opts.get("pulse_count", 10)),
        repetitive_derate=float(opts.get("repetitive_derate", 0.70)),
        phase_superposition=bool(opts.get("phase_superposition", True)),
    )


def calculate_mov(design: dict, mosfet: dict | None = None, cap: dict | None = None,
                  opts: dict | None = None) -> dict:
    """Size the MOV(s) per IEC 61000-4-5; returns stress / MCOV / per-path target + catalog screen."""
    s = build_mov_spec(design, mosfet, cap, opts)
    mov.validate(s)
    pol = mov.CRITERION_POLICY[s.criterion]
    paths, v_le, v_ll = mov.resolve_stress(s)
    mcov_req, mcov_adv, mcov_cls = mov.resolve_mcov(s)
    v1ma = mcov_cls * s.v1ma_ratio
    gov = max(paths, key=lambda p: p.i_sc) if paths else None

    targets = []
    for p in paths:
        t = mov.size_path(s, p, v1ma, pol)
        targets.append({"path": p.name, "mode": p.mode, "z": p.z, "v_oc": p.v_oc, "i_sc": p.i_sc,
                        "v_drive": t.v_drive, "i_op": t.i_op, "vc": t.vc,
                        "imax_required": t.imax_required, "energy_8_20": t.energy_8_20,
                        "device_gate": t.device_gate, "coord": t.coord_status, "cap_status": t.cap_status})
    screen = []
    if gov:
        for name, ok, reasons in mov.screen_catalog(s, gov, mcov_req, pol):
            screen.append({"name": name, "ok": bool(ok), "reasons": reasons})
    return _native({
        "spec": s,
        "stress": {"v_le": v_le, "v_ll": v_ll, "governing": (gov.name if gov else None),
                   "paths": [{"name": p.name, "mode": p.mode, "z": p.z, "v_oc": p.v_oc, "i_sc": p.i_sc}
                             for p in paths]},
        "mcov": {"required": mcov_req, "advisory": mcov_adv, "class": mcov_cls, "v1ma": v1ma},
        "criterion": {"name": pol.name, "ride_through": pol.ride_through,
                      "gate_uses_absmax": pol.gate_uses_absmax, "dev_margin_V": pol.dev_margin_V,
                      "energy_safety": pol.energy_safety},
        "targets": targets, "catalog": screen,
        "sources": {"vac_max": s.vac_max, "device_vds": s.device_vds, "cap_v_rating": s.cap_v_rating},
    })


# ── reference smoke test:  python -m app.mode_b.inputprotection.adapter ──
REFERENCE_DESIGN = {
    "vin_min": 90, "vin_max": 264, "pout_lo": 1700, "pout_hi": 3600,
    "vout": 393.7, "fsw": 70000, "fline": 60, "nch": 2, "r_input": 0.20, "L_phi_uH": 235,
}
REFERENCE_CAP = {"C_total_uF": 2350, "V_rating": 450}
REFERENCE_MOSFET = {"vdss": 650}

if __name__ == "__main__":
    import json
    n = calculate_ntc(REFERENCE_DESIGN, REFERENCE_CAP)
    print("NTC:", json.dumps({"r25_pick": n["result"]["r25_pick"], "e_cap": n["result"]["e_cap"],
                              "e_pulse_required": n["result"]["e_pulse_required"],
                              "i_rms_worst": n["result"]["i_rms_worst"],
                              "t_bypass_ms": n["result"]["t_bypass"] * 1e3,
                              "pass": [c["name"] for c in n["catalog"] if c["ok"]]}, indent=2))
    m = calculate_mov(REFERENCE_DESIGN, REFERENCE_MOSFET, REFERENCE_CAP)
    print("MOV:", json.dumps({"mcov_class": m["mcov"]["class"], "governing": m["stress"]["governing"],
                              "targets": [(t["path"], round(t["vc"]), t["coord"]) for t in m["targets"]],
                              "pass": [c["name"] for c in m["catalog"] if c["ok"]]}, indent=2))
