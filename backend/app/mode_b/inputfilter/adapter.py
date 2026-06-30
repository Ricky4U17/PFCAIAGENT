"""
Input EMI-filter design adapter
===============================
The only bridge between our design pipeline and the vendored EMI synthesis engine
(`emi_filter_design`). It builds the engine's `DesignContext` from values already fixed upstream —
the PFC operating grid (V_ac range, V_bus, P_out, f_sw, channels, efficiency), the inductor ripple,
the approved capacitor ESR, plus any Y-capacitance already committed by the protection stage — and
returns a JSON-safe `EMIResult`.

This stage is the LAST in the chain (PFC → semiconductors → protection → EMI). It is a pure,
read-only consumer of the earlier results: it changes nothing upstream.
"""
from __future__ import annotations

from . import emi_filter_design as emi
from app.mode_b.semiconductor.adapter import build_design_ops


def _grid_ripple_and_eff(design: dict):
    """Worst-case per-phase peak-to-peak inductor ripple [A] and a representative efficiency,
    from the same operating grid every chapter shares."""
    ops, s2, L_phi, iph, L_pts = build_design_ops(design)
    fsw = float(design["fsw"])
    dil_pp = 0.0
    for i in range(len(ops)):
        v = s2["Vin_pk"][i] * s2["Dpk"][i] / (L_pts[i] * fsw)
        if v > dil_pp:
            dil_pp = float(v)
    eff = float(min(ops[:, 2]))                 # conservative (lowest efficiency point)
    return dil_pp, eff


def _native(o):
    import numpy as np
    from dataclasses import is_dataclass, asdict
    if is_dataclass(o):
        return _native(asdict(o))
    if isinstance(o, dict):
        return {k: _native(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_native(v) for v in o]
    if isinstance(o, np.floating):
        return float(o)
    if isinstance(o, np.integer):
        return int(o)
    return o


def calculate_emi(design: dict, cap: dict | None = None, protection: dict | None = None,
                  ntc: dict | None = None, opts: dict | None = None) -> dict:
    """Synthesize the conducted-EMI filter. Returns {result, basis} (JSON-safe).

    design : the operating context (vin_min/max, vout, pout_hi, fsw, fline, nch, …)
    cap    : approved capacitor (ESR for the DM-noise estimate)
    protection : {committed_y_cap_nf} already-placed Y-caps from the protection stage
    ntc    : {r25_pick} (bookkeeping only)
    opts   : designer choices — safety_standard, compliance_profile, margin_db, detector,
             esr_bulk_mohm, c_para_earth_pf, sw_rise_time_ns, leakage_use_fraction, bleeder_r_ohm,
             cx_max_uF, ldm_sat_max_uH
    """
    cap = cap or {}; protection = protection or {}; ntc = ntc or {}; opts = opts or {}
    dil_pp, eff = _grid_ripple_and_eff(design)

    esr = opts.get("esr_bulk_mohm")
    if esr is None:
        esr = cap.get("ESR_parallel_mohm") or cap.get("ESR_mOhm")
    esr_bulk = (float(esr) / 1e3) if esr else None

    pfc = emi.PFCResult(
        vac_min=float(design["vin_min"]), vac_max=float(design["vin_max"]),
        f_line=float(design.get("fline", 60)), v_bus=float(design["vout"]),
        p_out=float(design.get("pout_hi") or design.get("pout_lo") or 1700),
        eff=eff, f_sw=float(design["fsw"]), n_phases=int(design.get("nch", 2)),
        i_ripple_pp=float(opts.get("i_ripple_pp_A") or dil_pp),
        esr_bulk=esr_bulk,
        c_para_earth=(float(opts["c_para_earth_pf"]) * 1e-12) if opts.get("c_para_earth_pf") else None,
        sw_rise_time=(float(opts["sw_rise_time_ns"]) * 1e-9) if opts.get("sw_rise_time_ns") else 20e-9,
    )
    y_committed = float(protection.get("committed_y_cap_nf") or 0.0) * 1e-9
    prot = emi.ProtectionResult(committed_y_cap_total=y_committed)
    ntc_r = emi.NTCResult(r_ntc_cold=float(ntc.get("r25_pick") or 0.0))

    ein = emi.EMIInputs(
        safety_standard=str(opts.get("safety_standard", "IEC_62368_1")),
        compliance_profile=int(opts.get("compliance_profile", 5)),
        margin_db=float(opts.get("margin_db", 6.0)),
        detector=opts.get("detector") or None,
        cx_max=(float(opts["cx_max_uF"]) * 1e-6) if opts.get("cx_max_uF") else 4.7e-6,
        ldm_sat_max=(float(opts["ldm_sat_max_uH"]) * 1e-6) if opts.get("ldm_sat_max_uH") else 100e-6,
        leakage_use_fraction=float(opts.get("leakage_use_fraction", 0.90)),
        bleeder_r=(float(opts["bleeder_r_ohm"])) if opts.get("bleeder_r_ohm") else None,
    )

    ctx = emi.DesignContext(pfc=pfc, protection=prot, ntc=ntc_r, emi_in=ein)
    res = emi.design_emi_filter(ctx)
    return _native({
        "result": res,
        "basis": {
            "i_ripple_pp_A": pfc.i_ripple_pp, "eff": eff, "esr_bulk_mohm": (esr_bulk * 1e3) if esr_bulk else None,
            "v_bus": pfc.v_bus, "f_sw": pfc.f_sw, "n_phases": pfc.n_phases,
            "vac_max": pfc.vac_max, "f_line": pfc.f_line,
        },
    })


# choices for the GUI dropdowns
def emi_options() -> dict:
    return {
        "safety_standards": list(emi.SAFETY_LEAKAGE_LIMIT.keys()),
        "leakage_mA": {k: v * 1e3 for k, v in emi.SAFETY_LEAKAGE_LIMIT.items()},
        "compliance_profiles": {str(k): v[3] for k, v in emi.COMPLIANCE_PROFILE.items()},
    }


# reference smoke test:  python -m app.mode_b.inputfilter.adapter
REFERENCE_DESIGN = {
    "vin_min": 90, "vin_max": 264, "pout_lo": 1700, "pout_hi": 3600,
    "vout": 393.7, "fsw": 70000, "fline": 60, "nch": 2, "r_input": 0.20, "L_phi_uH": 240,
}
if __name__ == "__main__":
    import json
    out = calculate_emi(REFERENCE_DESIGN, cap={"ESR_parallel_mohm": 5},
                        opts={"safety_standard": "IEC_62368_1", "compliance_profile": 5, "margin_db": 6})
    r = out["result"]
    print("feasible:", r["feasible"], "| class", r["conducted_class"], r["detector"])
    print("DM: %.0f dB @ %.0f kHz -> %d stage, corner %.1f kHz" %
          (r["dm_req_att_db"], r["dm_req_att_f"] / 1e3, r["dm_stages"], r["dm_corner_hz"] / 1e3))
    print("CM: %.0f dB @ %.0f kHz -> %d stage, corner %.1f kHz" %
          (r["cm_req_att_db"], r["cm_req_att_f"] / 1e3, r["cm_stages"], r["cm_corner_hz"] / 1e3))
    print("L_DM=%.1f uH  C_X=%.3f uF  L_CM=%.2f mH  C_Y=%.2f nF total" %
          (r["l_dm"] * 1e6, r["c_x"] * 1e6, r["l_cm"] * 1e3, r["c_y_emi_total"] * 1e9))
    print("leakage %.3f mA (limit %.2f)  stability_ok=%s" %
          (r["leakage_actual_A"] * 1e3, r["leakage_limit_A"] * 1e3, r["stability_ok"]))
    print("basis:", json.dumps(out["basis"]))
