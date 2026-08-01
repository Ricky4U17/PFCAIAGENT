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
        vout_bus=float(design.get("vout", 394)),
        cout=float(cout_f),
        i_inrush_target=float(opts.get("i_inrush_target", 60.0)),
        p_out=0.0,                                        # use the grid's I_rms verbatim
        i_rms_worst=float(iin_worst or 0.0),
        r_line=float(opts.get("r_line") or 0.0), r_emi=float(opts.get("r_emi") or 0.0),
        r_esr=float(opts.get("r_esr") or 0.0), r_bridge=float(opts.get("r_bridge") or 0.0),
        energy_margin=float(opts.get("energy_margin", 1.5)),
        r25_margin=float(opts.get("r25_margin", 1.10)),
        vref_pulse=float(opts.get("vref_pulse", 345.0)),
        tau_multiple=float(opts.get("tau_multiple", 4.0)),
        relay_v_margin=float(opts.get("relay_v_margin", 1.25)),
        ambient_c=float(opts.get("ambient_c", 45.0)),
        # worst-case / coordination inputs (review upgrade) — datasheet/layout values; 0 = open item
        r25_tol_default=float(opts.get("r25_tol_default", 0.20)),
        rsource_min=float(opts.get("rsource_min", 0.0)),
        fuse_i2t_rating=float(opts.get("fuse_i2t_rating", 0.0) or 0.0),
        relay_make_rating_a=float(opts.get("relay_make_rating_a", 0.0) or 0.0),
        relay_path_ohm=float(opts.get("relay_path_ohm", 0.0) or 0.0),
        off_time_min_ms=float(opts.get("off_time_min_ms", 0.0) or 0.0),
        restart_protection=str(opts.get("restart_protection", "")),
        # round-2 review: startup-path resistances + bridge IFSM + relay timing (0/blank -> OPEN)
        r_wiring_ohm=float(opts.get("r_wiring_ohm", 0.0) or 0.0),
        r_pcb_ohm=float(opts.get("r_pcb_ohm", 0.0) or 0.0),
        bridge_ifsm_a=float(opts.get("bridge_ifsm_a", 0.0) or 0.0),
        relay_operate_ms=float(opts.get("relay_operate_ms", 0.0) or 0.0),
        relay_delay_tol_ms=float(opts.get("relay_delay_tol_ms", 0.0) or 0.0),
    )


def calculate_ntc(design: dict, cap: dict | None = None, opts: dict | None = None) -> dict:
    """Size the NTC inrush limiter + bypass relay; returns sizing + catalog screen (JSON-safe).

    opts.selected_part (a part number from the ICL DB) recalculates the design around that
    specific NTC (actual inrush peak, RC precharge timing, energy margin) → out["selected"]."""
    opts = opts or {}
    s = build_ntc_spec(design, cap, opts)
    r = ntc.compute(s)
    screen = [{"name": n, "ok": bool(ok), "reasons": rs} for n, ok, rs in ntc.screen_catalog(s, r)]
    out = {"spec": s, "result": r, "catalog": screen,
           "sources": {"cout_uF": s.cout * 1e6, "i_rms_worst": s.i_rms_worst,
                       "vac_max": s.vac_max, "vout_bus": s.vout_bus}}
    try:                                             # rich, selectable candidates from the ICL DB
        from . import database as db
        out["candidates"] = db.rank(s, r, top=12)
        sel_pn = (opts.get("selected_part") or "").strip()
        if sel_pn:
            rec = db.find_part(sel_pn)
            if rec:
                out["selected"] = db.selected_metrics(s, r, rec)
                out["worst_case"] = ntc.worst_case_startup(s, r, rec)   # review-upgrade proof
    except Exception:
        pass                                          # DB unavailable → sizing + built-in screen only
    if "worst_case" not in out:
        # No specific part selected yet — prove the worst case around the generic R25 pick so the
        # report's tolerance / restart / fuse / phase-angle sections always render (default tolerance,
        # no datasheet r_hot → warm restart falls back to the off-time requirement).
        out["worst_case"] = ntc.worst_case_startup(s, r, {"r25": r.r25_pick})
    return _native(out)


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
        # survival / coordination inputs (None -> engine's named defaults / DATA-MISSING gates)
        mov_energy_derate=float(opts.get("mov_energy_derate", 0.80)),
        lead_inductance_nH=float(opts.get("lead_inductance_nH", 20.0)),
        surge_current_rise_us=float(opts.get("surge_current_rise_us", 8.0)),
        is_tmov=bool(opts.get("is_tmov", False)),
        mains_fault_current_A=(float(opts["mains_fault_current_A"]) if opts.get("mains_fault_current_A") not in (None, "") else None),
        fuse_i2t_rating_A2s=(float(opts["fuse_i2t_rating_A2s"]) if opts.get("fuse_i2t_rating_A2s") not in (None, "") else None),
        fuse_rating_A=(float(opts["fuse_rating_A"]) if opts.get("fuse_rating_A") not in (None, "") else None),
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
    candidates = []
    selected = None
    if gov:
        for name, ok, reasons in mov.screen_catalog(s, gov, mcov_req, pol):
            screen.append({"name": name, "ok": bool(ok), "reasons": reasons})
        try:
            from . import database as _db
            candidates = _db.screen_table_mov(s, gov, mcov_req, pol, top=40)
        except Exception:
            candidates = []
        # designer selection: pick a specific part from the screen (never blocked — CONDITIONAL is OK)
        sel_pn = (opts.get("selected_part") or "").strip() if opts else ""
        if sel_pn:
            selected = next((c for c in candidates if (c.get("part_number") or "") == sel_pn), None)

    # ---- Phase-2 survival + coordination (review Part A additions) ----
    gov_t = next((t for t in targets if t["path"] == (gov.name if gov else None)), targets[0] if targets else None)
    # Datasheet energy rating. Once the designer has SELECTED a part, its own rating governs — using
    # "first candidate that happens to publish an energy" would judge survival against a different part.
    # No selection yet -> fall back to the best available among the screened candidates (else DATA MISSING).
    e_rating = (selected or {}).get("energy_2ms_J") if selected else None
    e_rating_from_selected = e_rating is not None
    if e_rating is None:
        e_rating = next((c["energy_2ms_J"] for c in candidates if c.get("energy_2ms_J")), None)
    energy = overshoot = fuse = None
    if gov and gov_t:
        energy = mov.energy_survival(s, gov_t["vc"], gov_t["i_op"], pol, e_rating_J=e_rating)
        overshoot = mov.layout_overshoot(s, gov_t["i_op"], gov_t["vc"])
        fuse = mov.fuse_coordination(s, gov)
    mcov_cmp = mov.mcov_comparison(s)
    crit_matrix = mov.criterion_matrix(s, gov_t["vc"]) if gov_t else []
    # Selection gates stated BEFORE the candidate screen (MOV review: the screen must filter against
    # declared numbers, not be a conclusion), and the recalculation around the ACTUAL selected PART —
    # the class-level clamp above is a voltage-CLASS result, not a part result.
    gates = mov.selection_gates(s, gov, mcov_req, pol) if gov else []
    sel_recalc = None
    if gov and selected:
        try:
            sel_recalc = mov.selected_metrics_mov(s, gov, pol, selected, mcov_req)
        except Exception:
            sel_recalc = None
    if sel_recalc:                       # part-specific clamp supersedes the class figure downstream
        crit_matrix = mov.criterion_matrix(s, sel_recalc["vc"])

    return _native({
        "spec": s,
        "stress": {"v_le": v_le, "v_ll": v_ll, "governing": (gov.name if gov else None),
                   "paths": [{"name": p.name, "mode": p.mode, "z": p.z, "v_oc": p.v_oc, "i_sc": p.i_sc}
                             for p in paths]},
        "mcov": {"required": mcov_req, "advisory": mcov_adv, "class": mcov_cls, "v1ma": v1ma},
        "criterion": {"name": pol.name, "ride_through": pol.ride_through,
                      "gate_uses_absmax": pol.gate_uses_absmax, "dev_margin_V": pol.dev_margin_V,
                      "energy_safety": pol.energy_safety},
        "targets": targets, "catalog": screen, "candidates": candidates, "selected": selected,
        "energy": energy, "overshoot": overshoot, "fuse_coord": fuse,
        "mcov_comparison": mcov_cmp, "criterion_matrix": crit_matrix,
        # M1: gates declared before the screen; recalculation on the selected PART (vs the class)
        "gates": gates, "selected_recalc": sel_recalc,
        "energy_basis": ("selected part" if e_rating_from_selected
                         else ("best screened candidate" if e_rating else "DATA MISSING")),
        "sources": {"vac_max": s.vac_max, "device_vds": s.device_vds, "cap_v_rating": s.cap_v_rating},
    })


# ── GDT surge diverter (common-mode) ──────────────────────────────────────────
def build_gdt_spec(design: dict, opts: dict | None = None):
    from . import gdt_surge_select as gdt
    opts = opts or {}
    level = opts.get("level", 3)
    if isinstance(level, str):
        level = int(level) if level.strip().isdigit() else level.strip().upper()
    _o = lambda k: (float(opts[k]) if opts.get(k) not in (None, "") else None)
    return gdt.GdtSpec(
        vac_max=float(design.get("vin_max", 264)),
        vac_nom=float(opts.get("vac_nom", 230)),
        line_swell=float(opts.get("line_swell", 1.0)),
        k_line_margin=float(opts.get("k_line_margin", 1.20)),
        level=level,
        custom_v_le=_o("custom_v_le"),
        imax_margin=float(opts.get("imax_margin", 3.0)),
        insulation_withstand_V=_o("insulation_withstand_V"),
        follow_current_extinguish_A=_o("follow_current_extinguish_A"),
        mains_fault_current_A=_o("mains_fault_current_A"),
        fuse_i2t_rating_A2s=_o("fuse_i2t_rating_A2s"),
        fuse_rating_A=_o("fuse_rating_A"),
    )


def calculate_gdt(design: dict, opts: dict | None = None, environment: str | None = None) -> dict:
    """Screen GDTs for the common-mode paths per IEC 61000-4-5 + the Ch9 review: no-fire, surge-current
    class, dynamic (impulse) sparkover [DATA MISSING in the export], follow-current & fail-short safety,
    and a level/environment-driven MOV-vs-MOV+GDT recommendation. Returns {} shape with DATA-MISSING gates."""
    from . import gdt_surge_select as gdt
    from . import database as _db
    gs = build_gdt_spec(design, opts)
    gdt.validate(gs)
    v_le, i_sc, i_req = gdt.resolve_stress(gs)
    rec = gdt.gdt_required(gs, environment=environment)
    follow = gdt.follow_current(gs)
    fshort = gdt.fail_short(gs)
    try:
        candidates = _db.screen_table_gdt(gs)
    except Exception:
        candidates = []
    return _native({
        "spec": gs, "environment": environment,
        "required": rec,
        "stress": {"v_le": v_le, "i_sc": i_sc, "i_required": i_req,
                   "preferred_class_A": gdt.snap_gdt_class(i_req) if i_req else None,
                   "no_fire_need_V": gdt.v_line_peak(gs) * gs.k_line_margin},
        "follow_current": follow, "fail_short": fshort,
        "candidates": candidates,
    })


# ── line fuse (upstream protection + NTC/MOV/GDT coordination) ─────────────────
def calculate_fuse(design: dict, cap: dict | None = None, opts: dict | None = None) -> dict:
    """Select the line fuse and coordinate it with the startup pulse + fault path. Reuses the NTC grid
    for the worst-case continuous I_rms and the worst-case startup I2t; the available fault current +
    margins come from `opts` (reusing mains_fault_current_A from the NTC/MOV inputs). Returns the
    selection, the candidate screen, the requirement thresholds, and the fuse melting I2t to feed back
    into the NTC §8.11 / MOV-GDT fail-short checks. Missing inputs stay OPEN / DATA MISSING."""
    from . import fuse_select as fz
    from . import database as _db
    opts = opts or {}
    # worst-case continuous I_rms + startup I2t from the NTC calc (single source of the grid).
    ntc = calculate_ntc(design, cap or {}, opts)
    i_rms = float((ntc.get("result") or {}).get("i_rms_worst") or 0.0)
    if i_rms <= 0:                       # grid not fully specified -> worst-case = low-line power / low line
        _pout = design.get("pout_lo") or design.get("pout_hi")   # sustained low-line power draws the most current
        _eff = float(opts.get("eff", 0.95)); _pf = float(opts.get("pf", 0.99))
        _vmin = float(design.get("vin_min", 90))
        if _pout and _vmin:
            i_rms = float(_pout) / (_vmin * _eff * _pf)
    _wc = ntc.get("worst_case") or {}
    startup_i2t = _wc.get("i2t_worst")
    # cold-start inrush peak (NTC-limited, nominal R25) — REPORTED for context. Per the designer review the
    # peak does NOT gate the continuous rating: a fuse survives a high peak when the pulse is short and the
    # melting-I²t margin holds (gate 3). Set fuse_inrush_gates_rating to restore the old, over-strict rule.
    inrush_peak = _wc.get("i_inrush_nom_A") or _wc.get("i_inrush_max_A")
    _o = lambda k: (float(opts[k]) if opts.get(k) not in (None, "") else None)
    # gate 5 — a fitted MOV/GDT means a fail-short is a bolted line fault; a stuck bypass relay is the
    # other failed-protection path. Ch9 supplies the surge devices; the NTC opts supply the relay.
    _mov_gdt = opts.get("mov_gdt_present")
    if _mov_gdt in (None, ""):
        _mov_gdt = bool(opts.get("mov_selected_part") or opts.get("gdt_selected_part")) or None
    fs = fz.FuseSpec(
        vac_max=float(design.get("vin_max", 264)),
        i_rms=i_rms,
        inrush_peak_A=inrush_peak,
        available_fault_current_A=(_o("mains_fault_current_A")),
        current_margin=float(opts.get("fuse_current_margin", 1.5)),
        i2t_margin=float(opts.get("fuse_i2t_margin", 2.0)),
        load_factor=float(opts.get("fuse_load_factor", fz.DEFAULT_LOAD_FACTOR)),
        ambient_derate=float(opts.get("fuse_ambient_derate", 1.0)),
        # gate 6 — thermal implementation (all optional; absent -> OPEN / ESTIMATED, never a silent pass)
        t_ambient_C=_o("fuse_ambient_C"),
        t_rating_ref_C=float(opts.get("fuse_rating_ref_C", fz.DEFAULT_T_RATING_REF_C)),
        derate_per_C=_o("fuse_derate_per_C"),
        fuseholder_rise_C=_o("fuseholder_rise_C"),
        # gate 5 — fault coordination
        mov_fail_short_current_A=_o("mov_fail_short_current_A"),
        gdt_follow_current_A=_o("gdt_follow_current_A"),
        relay_stuck_fault_current_A=_o("relay_stuck_fault_current_A"),
        mov_gdt_present=(bool(_mov_gdt) if _mov_gdt not in (None, "") else None),
        inrush_gates_rating=bool(opts.get("fuse_inrush_gates_rating", False)),
    )
    req = fz.requirements(fs, startup_i2t)
    try:
        candidates = _db.screen_table_fuse(fs, startup_i2t, top=40)
    except Exception:
        candidates = []
    # designer selection (never blocked). Uses a fuse-specific key so it can't collide with the NTC's
    # selected_part when they share an opts dict. Default pick = best non-FAIL (PASS, else CONDITIONAL).
    sel_pn = (opts.get("fuse_selected_part") or "").strip() if opts else ""
    selected = (next((c for c in candidates if (c.get("part_number") or "") == sel_pn), None) if sel_pn
                else next((c for c in candidates if c.get("verdict") in ("PASS", "CONDITIONAL")), None))
    gates = fz.gate_summary(fs, req, selected)
    _open = [g for g in gates if g["status"] == "DATA MISSING"]
    _fail = [g for g in gates if g["status"] == "FAIL"]
    _cond = [g for g in gates if g["status"] == "CONDITIONAL"]
    return _native({
        "spec": fs, "i_rms": i_rms, "startup_i2t": startup_i2t, "inrush_peak_A": inrush_peak,
        "requirements": req, "candidates": candidates, "selected": selected,
        "selected_i2t": (selected or {}).get("melting_i2t") if selected else None,
        "gates": gates,
        "gate_status": ("FAIL" if _fail else ("DATA MISSING" if _open else ("CONDITIONAL" if _cond else "PASS"))),
        "gates_open": [g["n"] for g in _open], "gates_conditional": [g["n"] for g in _cond],
        "fast_blow_only": all((c.get("response_time") or "").lower().startswith("fast") for c in candidates) if candidates else None,
    })


# ── reference smoke test:  python -m app.mode_b.inputprotection.adapter ──
REFERENCE_DESIGN = {
    "vin_min": 90, "vin_max": 264, "pout_lo": 1700, "pout_hi": 3600,
    "vout": 394.0, "fsw": 70000, "fline": 60, "nch": 2, "r_input": 0.20, "L_phi_uH": 235,
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
