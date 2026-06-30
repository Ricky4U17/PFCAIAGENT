"""
app/main.py — PFC AI Agent v2.0
Mode A: 5 HITL gates (pure Python, no API key required)
Mode B: Steps 1-12 PDF report + Step 6 magnetic design
"""
from __future__ import annotations
import logging, math
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

log = logging.getLogger("pfc_ai")
logging.basicConfig(level=logging.INFO)

# ── DesignState validation helper (Phase 1 — called only when flag is True) ──
def _validate_state(state: dict) -> None:
    """Validate incoming state dict against the canonical DesignState schema.
    Enabled by feature_flags.enable_design_state_validation (default False).
    Extra fields are always allowed — only structural errors are raised.
    """
    from app.config.feature_flags import FEATURE_FLAGS
    if not FEATURE_FLAGS.enable_design_state_validation:
        return
    from app.design_state import DesignState
    from pydantic import ValidationError
    try:
        DesignState.model_validate(state)
    except ValidationError as exc:
        raise HTTPException(422, detail=exc.errors())

app = FastAPI(title="PFC AI Agent", version="2.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

INTERLEAVED = {"interleaved_boost_ccm", "totem_pole_interleaved_ccm"}

def _calc_l_py(pout_lo, vin_min, vout, fsw, crest, eta=0.945, PF=0.9987):
    Vin_pk = vin_min * math.sqrt(2)
    D      = max(0.001, 1 - Vin_pk / vout)
    Iin_pk = math.sqrt(2) * (pout_lo / eta) / (vin_min * PF)
    dIin   = crest * Iin_pk
    KD     = (2*D-1)/D if D >= 0.5 else (1-2*D)/(1-D)
    dIL    = dIin / max(0.001, KD)
    L      = Vin_pk * D / (fsw * dIL)
    return dict(L_uH=round(L*1e6,2), dIL=round(dIL,4), Iin_pk=round(Iin_pk,4), D=round(D,6), KD=round(KD,6), Vin_pk=round(Vin_pk,4))

def _fsw_defaults(mode):
    if mode == "ccm":
        return dict(switching_frequency_style="fixed", recommended_frequency_hz=70000.0,
                    recommended_frequency_range_hz=None, ask_crest_ripple_ratio=True,
                    default_crest_ripple_ratio=0.20,
                    crest_ripple_ratio_guidance="0.15-0.30 recommended; 0.05-0.15 for Medical/low-THD")
    elif mode == "crcm":
        return dict(switching_frequency_style="variable", recommended_frequency_hz=None,
                    recommended_frequency_range_hz=[30000,150000], ask_crest_ripple_ratio=False,
                    default_crest_ripple_ratio=2.0, crest_ripple_ratio_guidance="CrCM variable freq; r~2.0 at crest")
    else:
        return dict(switching_frequency_style="fixed_or_variable", recommended_frequency_hz=100000.0,
                    recommended_frequency_range_hz=[50000,200000], ask_crest_ripple_ratio=True,
                    default_crest_ripple_ratio=0.40, crest_ripple_ratio_guidance="DCM: 0.30-0.60 typical")

def _ctrl_strategy(state):
    topo      = state.get("selected_topology","")
    intake    = state.get("intake",{})
    ctrl_pref = (intake.get("control") or {}).get("control_preference","Recommend")
    tech      = (intake.get("business") or {}).get("preferred_switch_technology",["Si"])
    app_class = (intake.get("compliance") or {}).get("application_class","Industrial")
    is_ttp  = "totem_pole" in topo
    has_wbg = any(t in ["SiC","GaN"] for t in (tech or []))
    is_med  = app_class == "Medical"
    reasons = []
    if is_ttp:  reasons.append("Totem-pole PFC requires digital control for adaptive dead-time management.")
    else:       reasons.append("Conventional boost supports both analog and digital control.")
    if has_wbg: reasons.append("SiC/GaN preference favors digital — adaptive dead-time reduces switching loss.")
    if is_med:  reasons.append("Medical class: digital enables real-time leakage monitoring (IEC 60601-1 traceability).")
    if ctrl_pref in ("Analog","Digital","Digital ARM"):
        reasons.append(f'Designer intake specifies "{ctrl_pref}" as preference.')
    if ctrl_pref == "Digital ARM":
        reasons.append("Digital ARM controller selected — UCD3138 is well-suited for high-frequency PFC with on-chip PWM, ADC, and compensator hardware.")
    # Explicit designer preference always takes priority.
    # Topology/WBG/Medical signals only apply when "Recommend" is chosen.
    if ctrl_pref == "Digital ARM":
        rec = "digital_arm"
    elif ctrl_pref == "Digital":
        rec = "digital"
    elif ctrl_pref == "Analog":
        rec = "analog"
    else:  # "Recommend" — agent decides
        rec = "digital" if (is_ttp or has_wbg or is_med) else "analog"
    return dict(recommended_controller_mode=rec, reasoning=reasons, stated_control_preference=ctrl_pref)

class StartReq(BaseModel):
    project_id: str
    intake: Dict[str, Any]

class FbReq(BaseModel):
    state: Dict[str, Any]
    feedback: Dict[str, Any]

class ReportReq(BaseModel):
    state: Dict[str, Any]

@app.get("/health")
def health(): return {"status":"ok","version":"2.0.0"}

# ── Controller Reference Database agent ──────────────────────────────────────
class _RefQueryReq(BaseModel):
    question:   str
    controller: Optional[str] = None     # e.g. "fan9672"; None = search all
    k:          int  = 6                 # number of passages to return
    synthesize: bool = False             # also produce a cited LLM answer (needs ANTHROPIC_API_KEY)

@app.post("/controller-db/query", tags=["controller-db"])
def controller_db_query(req: _RefQueryReq):
    """Retrieve the most relevant reference passages (BM25 over the indexed PDFs),
    optionally with a grounded, cited LLM answer."""
    from app.reference_agent import get_agent
    try:
        return get_agent().query(req.question, controller=req.controller,
                                  k=req.k, synthesize=req.synthesize)
    except Exception as exc:
        log.exception("controller-db query failed")
        raise HTTPException(500, detail=str(exc))

@app.get("/controller-db/sources", tags=["controller-db"])
def controller_db_sources(controller: Optional[str] = None):
    """List the controllers and reference documents in the local database."""
    from app.reference_agent import get_agent
    try:
        return get_agent().sources(controller)
    except Exception as exc:
        raise HTTPException(500, detail=str(exc))

@app.post("/mode-a/start", tags=["mode-a"])
def start(req: StartReq):
    try:
        from app.intake.topology_selector import select_topology
        intake = req.intake
        if "vin_rms_min" in intake: intake = {"application": intake}
        res = select_topology(intake)
        state = {"intake": intake, "project_id": req.project_id,
                 "topology_recommendation": {"recommended_topology": res["recommended_topology"], "recommended_mode": res["recommended_mode"]}}
        return {"status":"wait_topology","ranking":res["ranking"],"mode_scores":res["mode_scores"],
                "recommended_topology":res["recommended_topology"],"recommended_mode":res["recommended_mode"],"state":state}
    except Exception as e:
        log.exception("topology scoring"); raise HTTPException(500, str(e))

@app.post("/mode-a/approve-topology", tags=["mode-a"])
def approve_topology(req: FbReq):
    fb = req.feedback; state = dict(req.state)
    _validate_state(state)
    sel_topo = fb.get("selected_topology") or state.get("topology_recommendation",{}).get("recommended_topology","interleaved_boost_ccm")
    sel_mode = fb.get("selected_mode")     or state.get("topology_recommendation",{}).get("recommended_mode","ccm")
    state.update(selected_topology=sel_topo, selected_mode=sel_mode)
    strat = _ctrl_strategy(state); state["controller_strategy"] = strat
    return {"status":"wait_controller","selected_topology":sel_topo,"selected_mode":sel_mode,"controller_strategy":strat,"state":state}

@app.post("/mode-a/approve-controller", tags=["mode-a"])
def approve_controller(req: FbReq):
    fb = req.feedback; state = dict(req.state)
    _validate_state(state)
    ctrl = fb.get("controller_mode") or state.get("controller_strategy",{}).get("recommended_controller_mode","digital")
    state["selected_controller_mode"] = ctrl
    sel_topo = state.get("selected_topology",""); sel_mode = state.get("selected_mode","ccm")
    is_int = sel_topo in INTERLEAVED
    if is_int:
        return {"status":"wait_channels","selected_controller_mode":ctrl,"is_interleaved":True,"state":state}
    mini = _fsw_defaults(sel_mode); state["topology_specific_inputs"] = mini; state["selected_channels"] = 1
    return {"status":"wait_mini_intake","selected_controller_mode":ctrl,"is_interleaved":False,"selected_channels":1,"mini_intake_defaults":mini,"state":state}

@app.post("/mode-a/approve-channels", tags=["mode-a"])
def approve_channels(req: FbReq):
    fb = req.feedback; state = dict(req.state)
    _validate_state(state)
    n_ch = int(fb.get("n_channels") or 2); sel_mode = state.get("selected_mode","ccm")
    mini = _fsw_defaults(sel_mode)
    intake = state.get("intake",{}); ap = intake.get("application",{})
    lpy = _calc_l_py(float(ap.get("output_power_w_low_line",1700)),float(ap.get("vin_rms_min",90)),
                     float(ap.get("output_bus_voltage_v",393)),float(mini["recommended_frequency_hz"] or 70000),float(mini["default_crest_ripple_ratio"]))
    mini["indicative_L_uH"] = lpy["L_uH"]; mini["indicative_Iin_pk_A"] = lpy["Iin_pk"]
    state["selected_channels"] = n_ch; state["topology_specific_inputs"] = mini
    return {"status":"wait_mini_intake","selected_channels":n_ch,"mini_intake_defaults":mini,"validation_errors":[],"state":state}

@app.post("/mode-a/submit-mini-intake", tags=["mode-a"])
def submit_mini(req: FbReq):
    fb = req.feedback; state = dict(req.state)
    _validate_state(state)
    sel_mode = state.get("selected_mode","ccm")
    ctrl = state.get("selected_controller_mode","digital")
    tsi  = dict(state.get("topology_specific_inputs") or _fsw_defaults(sel_mode))
    if "switching_frequency_hz" in fb:     tsi["recommended_frequency_hz"]     = float(fb["switching_frequency_hz"])
    if "crest_ripple_ratio" in fb:         tsi["default_crest_ripple_ratio"]   = float(fb["crest_ripple_ratio"])
    if "switching_frequency_style" in fb:  tsi["switching_frequency_style"]    = fb["switching_frequency_style"]
    errors = []
    if sel_mode == "ccm" and tsi.get("switching_frequency_style") == "variable":
        errors.append("CCM requires fixed switching frequency.")
    crest = float(tsi.get("default_crest_ripple_ratio",0.20))
    if not (0.05 <= crest <= 0.60): errors.append(f"Crest ripple ratio {crest:.3f} outside [0.05, 0.60].")
    if errors: return {"status":"wait_mini_intake","validation_errors":errors,"mini_intake_defaults":tsi,"state":state}
    intake = state.get("intake",{}); ap = intake.get("application",{})
    fsw = float(tsi.get("recommended_frequency_hz") or 70000)
    lpy = _calc_l_py(float(ap.get("output_power_w_low_line",1700)),float(ap.get("vin_rms_min",90)),
                     float(ap.get("output_bus_voltage_v",393)),fsw,crest)
    tsi["confirmed_L_uH"]     = lpy["L_uH"]
    tsi["confirmed_L_uH_sel"] = round(lpy["L_uH"]/5)*5
    tsi["confirmed_Iin_pk_A"] = lpy["Iin_pk"]
    tsi["confirmed_dIL_A"]    = lpy["dIL"]
    state["topology_specific_inputs"] = tsi
    return {"status":"done","selected_topology":state.get("selected_topology"),"selected_mode":state.get("selected_mode"),
            "selected_channels":state.get("selected_channels",1),"selected_controller_mode":ctrl,
            "topology_specific_inputs":tsi,"validation_errors":[],"state":state}

@app.post("/mode-b/generate-report", tags=["mode-b"])
def gen_report(req: ReportReq):
    try:
        _validate_state(req.state)
        from app.mode_b.generate_report import generate_full_report
        from fastapi.responses import Response
        pdf = generate_full_report(req.state)
        return Response(content=pdf, media_type="application/pdf",
                        headers={"Content-Disposition":"attachment; filename=PFC_Design_Report_Steps1_12.pdf"})
    except Exception as e:
        log.exception("report gen"); raise HTTPException(500, str(e))


class ControlReportReq(BaseModel):
    # Designer specs — all optional; any omitted field falls back to the
    # verified DEFAULT_INPUTS of the control-design calc engine.
    inputs: Optional[Dict[str, Any]] = None

@app.get("/mode-b/control-report/defaults", tags=["mode-b"])
def control_report_defaults():
    """Return the designer-editable control-design inputs and their defaults,
    so the GUI can render a spec form and round-trip them to /control-report."""
    from app.mode_b.step16_steps1_8 import DEFAULT_INPUTS as S18
    from app.mode_b.step16_step10_iloop import DEFAULT_INPUTS as S10
    from app.mode_b.step16_step11_vloop import DEFAULT_INPUTS as S11
    return {
        "power_stage": {k: S18[k] for k in
                        ("vout", "fsw", "lphi_uH", "nch", "cout_uF",
                         "pout_lo", "pout_hi", "eta_lo", "eta_hi")},
        "crossovers": {"fci": S18["fci"], "fcv": S18["fcv"]},
        "current_loop": {k: S10[k] for k in ("r_l", "r_c", "v_ramp", "g_mi",
                                             "r_m", "c_m", "f_z", "f_p")},
        "voltage_loop": {k: S11[k] for k in ("comp_type", "gmv",
                                             "fz1", "fz2", "fp1", "fp2", "fz", "fp")},
    }

@app.post("/mode-b/control-report", tags=["mode-b"])
def control_report(req: ControlReportReq):
    """Generate the full FAN9672 control-loop design report (Steps 1–14 +
    Appendices A–E) from designer specs. Returns a PDF."""
    try:
        from app.mode_b.report_steps1_8 import build_control_report
        from fastapi.responses import Response
        pdf = build_control_report(req.inputs or None)
        return Response(content=pdf, media_type="application/pdf",
                        headers={"Content-Disposition":
                                 "attachment; filename=FAN9672_Control_Loop_Design_Report.pdf"})
    except Exception as e:
        log.exception("control report gen"); raise HTTPException(500, str(e))


class _PowerPlantReq(BaseModel):
    vin_min: float = 90.0
    vin_max: float = 264.0
    pout_lo: float = 1700.0
    pout_hi: float = 3600.0
    vout:    float = 393.7

@app.post("/mode-b/control/power-plant", tags=["mode-b"])
def control_power_plant(req: _PowerPlantReq):
    """Control Design Screen 1 — power-plant parameters review.
    Returns the canonical operating-point grid (the same η/PF reference used in
    the report's Table 1.2.2) with per-point V_in,pk, duty and R_LOAD derived
    for the chosen V_OUT. Scalar fixed params (L, C, compliance, …) are rendered
    by the GUI from carried-in state."""
    try:
        import math
        from app.mode_b.calculations import canonical_ops_table
        m = canonical_ops_table(req.vin_min, req.vin_max, req.pout_lo, req.pout_hi)
        rows = []
        for r in m:
            vac, pout, eta, pf = float(r[0]), float(r[1]), float(r[2]), float(r[3])
            vin_pk = vac * math.sqrt(2.0)
            duty = max(0.0, 1.0 - vin_pk / req.vout)
            rload = req.vout ** 2 / pout
            rows.append({
                "vac": round(vac, 1), "pout": round(pout, 0),
                "eta_pct": round(eta * 100, 2), "pf": round(pf, 4),
                "vin_pk": round(vin_pk, 2), "duty": round(duty, 4),
                "rload": round(rload, 3),
                "line": "Low" if vac < 180 else "High",
            })
        return {"rows": rows}
    except Exception as e:
        log.exception("power-plant"); raise HTTPException(500, str(e))

class _ComponentsReq(BaseModel):
    inputs: Optional[Dict[str, Any]] = None

@app.post("/mode-b/control/components", tags=["mode-b"])
def control_components(req: _ComponentsReq):
    """Control Design Screen 2 — controller-fixed components + designer selections.
    Returns the components fixed/auto-calculated by the time we reach control
    design (display-only) and the designer-selectable items (R_CS over its valid
    band, filter caps, R_LS) with their calculated defaults and pin-filter poles."""
    try:
        import math
        from app.mode_b.step16_steps1_8 import compute_steps_1_8
        from app.mode_b.step16_step9_bibo import compute_step9_bibo
        inp = req.inputs or None
        d = compute_steps_1_8(inp); c = d["const"]; s4 = d["step4"]; s5 = d["step5"]
        s6 = d["step6"]; s8 = d["step8"]; b = compute_step9_bibo(inp)

        def ohm(x):
            return f"{x/1e6:.2f} MΩ" if x >= 1e6 else (f"{x/1e3:.1f} kΩ" if x >= 1e3 else f"{x:.1f} Ω")
        R_LPK = 4.7e3   # LPK series resistor (fixed)
        fixed = [
            {"name": "Oscillator resistor", "symbol": "R_RI", "value": ohm(s4["rri_selected"]),
             "role": f"sets f_sw ≈ {s4['fsw_at_selected']/1e3:.1f} kHz"},
            {"name": "FB divider top", "symbol": "R_FB1", "value": ohm(s5["rfb1"]), "role": "3 × 1.21 MΩ series"},
            {"name": "FB divider bottom", "symbol": "R_FB2", "value": ohm(s5["rfb2"]), "role": "sets V_OUT"},
            {"name": "IAC resistor — LL (FR)", "symbol": "R_IAC", "value": ohm(c["riac_fr"]), "role": "line sense, FR"},
            {"name": "IAC resistor — HL (HV)", "symbol": "R_IAC", "value": ohm(c["riac_hv"]), "role": "line sense, HV"},
            {"name": "Peak-detector resistor", "symbol": "R_RLPK", "value": ohm(c["r_rlpk"]), "role": "V_LPK scaling"},
            {"name": "VIR resistor — FR", "symbol": "R_VIR", "value": ohm(c["r_vir_fr"]), "role": "V_VIR < 1.5 V → FR"},
            {"name": "VIR resistor — HV", "symbol": "R_VIR", "value": ohm(c["r_vir_hv"]), "role": "V_VIR > 3.5 V → HV"},
            {"name": "BIBO R1", "symbol": "RB1", "value": ohm(b["rb1"]), "role": "brown-in/out divider"},
            {"name": "BIBO R2", "symbol": "RB2", "value": ohm(b["rb2"]), "role": "brown-in/out divider"},
            {"name": "BIBO R3", "symbol": "RB3", "value": ohm(b["rb3"]), "role": "filter pole 1"},
            {"name": "BIBO R4", "symbol": "RB4", "value": ohm(b["rb4"]), "role": "bottom leg, sets ratio"},
            {"name": "BIBO C1", "symbol": "CB1", "value": f"{b['cb1']*1e9:.0f} nF", "role": "filter pole 1"},
            {"name": "BIBO C2", "symbol": "CB2", "value": f"{b['cb2']*1e9:.0f} nF", "role": "filter pole 2"},
            {"name": "Gain-control resistor", "symbol": "R_GC", "value": ohm(s8["r_gc_sel"]), "role": "LPT gain align"},
            {"name": "LPK series resistor", "symbol": "R_LPK", "value": ohm(R_LPK), "role": "LPK series (fixed)"},
        ]
        m1_ll, m1_hl = s6["rcs1_ll"], s6["rcs1_hl"]
        rcs_max = min(m1_ll, m1_hl)
        rcs_min = 0.85 * rcs_max
        rec_mohm = round(s6["rcs_sel"] * 1e3, 2)
        STD_MOHM = [10, 11, 12, 13, 14, 15, 16, 18, 20, 22, 24]
        rcs_opts = sorted(set([v for v in STD_MOHM if rcs_min * 1e3 <= v <= rcs_max * 1e3] + [rec_mohm]))
        rcs = {
            "min_mohm": round(rcs_min * 1e3, 2), "max_mohm": round(rcs_max * 1e3, 2),
            "recommended_mohm": rec_mohm, "options_mohm": rcs_opts,
            "m1_ll_mohm": round(m1_ll * 1e3, 2), "m1_hl_mohm": round(m1_hl * 1e3, 2),
            "note": "Valid band satisfies the AN4165 (Method-1) VRM limit at both HL and LL.",
        }
        # standard E6 capacitor values (pF) offered in every cap dropdown
        CAP_PF = [100, 150, 220, 330, 470, 680, 1000, 1500, 2200, 3300, 4700, 6800,
                  10000, 15000, 22000, 33000, 47000, 68000, 100000]
        RLS_KOHM = [12, 13, 15, 16, 18, 20, 22, 24, 27, 30, 33, 36, 39, 43, 47, 51, 56, 62, 68, 75, 82]
        # designer-selectable filter caps: default + associated R (frontend computes the live pole)
        selectable = [
            {"key": "c_gc", "name": "Gain-control filter cap", "symbol": "C_GC",
             "default_pf": 470, "r_assoc_ohm": round(s8["r_gc_sel"], 1), "role": "with R_GC", "options_pf": CAP_PF},
            {"key": "c_rlpk", "name": "RLPK filter cap", "symbol": "C_RLPK",
             "default_pf": 10000, "r_assoc_ohm": round(c["r_rlpk"], 1), "role": "with R_RLPK", "options_pf": CAP_PF},
            {"key": "c_ilimit", "name": "ILIMIT filter cap", "symbol": "C_ILIMIT",
             "default_pf": 10000, "r_assoc_ohm": round(s8["r_ilimit_sel"], 1), "role": "with R_ILIMIT", "options_pf": CAP_PF},
            {"key": "c_ilimit2", "name": "ILIMIT2 filter cap", "symbol": "C_ILIMIT2",
             "default_pf": 10000, "r_assoc_ohm": round(s8["r_ilimit2_sel"], 1), "role": "with R_ILIMIT2", "options_pf": CAP_PF},
            {"key": "c_vir", "name": "VIR filter cap", "symbol": "C_VIR",
             "default_pf": 10000, "r_assoc_ohm": round(c["r_vir_fr"], 1), "role": "with R_VIR (FR)", "options_pf": CAP_PF},
            {"key": "c_ls", "name": "Current-predict filter cap (across R_LS)", "symbol": "C_LS",
             "default_pf": 470, "r_assoc_ohm": round(s8["r_ls_sel"], 1), "role": "with R_LS", "options_pf": CAP_PF},
        ]
        rls_default = min(RLS_KOHM, key=lambda x: abs(x - s8["r_ls_sel"] / 1e3))  # nearest standard
        r_ls = {"default_kohm": rls_default, "calc_kohm": round(s8["r_ls"] / 1e3, 1),
                "options_kohm": RLS_KOHM, "role": "current-predict; valid 12–87 kΩ"}
        return {"fixed": fixed, "rcs": rcs, "selectable": selectable, "r_ls": r_ls}
    except Exception as e:
        log.exception("control components"); raise HTTPException(500, str(e))

@app.post("/mode-b/control/coefficients", tags=["mode-b"])
def control_coefficients(req: _ComponentsReq):
    """Control Design Screen 3 — Fixed Coefficients / Internal Parameters (review).
    Returns the controller constants & design targets (report Step 2 table)."""
    try:
        from app.mode_b.step16_steps1_8 import compute_steps_1_8
        d = compute_steps_1_8(req.inputs or None)
        return {"coefficients": d["step2"]["rows"]}
    except Exception as e:
        log.exception("control coefficients"); raise HTTPException(500, str(e))

# ── Chapter 7 — Semiconductor loss & thermal ──────────────────────────────────
class _SemiReq(BaseModel):
    design:  Dict[str, Any]                 # operating context (vin_min/max, pout_lo/hi, vout, fsw, fline, nch, r_input, L_phi_uH)
    mosfet:  Dict[str, Any]
    diode:   Dict[str, Any]
    bridge:  Dict[str, Any]
    thermal: Dict[str, Any]
    tj_limit:     Optional[Dict[str, Any]] = None
    selected_vac: Optional[float] = None

@app.get("/mode-b/semiconductor/manifest", tags=["mode-b"])
def semiconductor_manifest():
    """Per-component parameter manifest (drives the confirmation/entry tables)."""
    try:
        from app.mode_b.semiconductor import pfc_component_intake as intake
        return {kind: [p._asdict() for p in plist] for kind, plist in intake.MANIFEST.items()}
    except Exception as e:
        log.exception("semiconductor manifest"); raise HTTPException(500, str(e))

@app.get("/mode-b/semiconductor/library", tags=["mode-b"])
def semiconductor_library():
    """Stored parts the designer can select instead of entering a datasheet by hand
    (provision for the future local component DB). Each entry is a full engine-format block."""
    try:
        from app.mode_b.semiconductor.library import list_components
        return list_components()
    except Exception as e:
        log.exception("semiconductor library"); raise HTTPException(500, str(e))

class _DbRankReq(BaseModel):
    design:   Dict[str, Any]
    criteria: Dict[str, Any] = {}
    top:      int = 10
    mode:     str = "full"          # 'conduction' + mosfet → bottom-bypass MOSFET ranking

@app.get("/mode-b/semiconductor/database/{kind}/options", tags=["mode-b"])
def semiconductor_db_options(kind: str):
    """Distinct manufacturers / mounting / package / technology for the filter dropdowns."""
    try:
        from app.mode_b.semiconductor import database as db
        if kind not in ("mosfet", "diode", "bridge"):
            raise HTTPException(404, "unknown component kind")
        return db.options(kind)
    except HTTPException:
        raise
    except Exception as e:
        log.exception("db options"); raise HTTPException(500, str(e))

@app.post("/mode-b/semiconductor/database/{kind}/rank", tags=["mode-b"])
def semiconductor_db_rank(kind: str, req: _DbRankReq):
    """Filter the local DB by the designer's criteria and return the top-N lowest-loss parts
    (loss computed for this design's operating point). Each result carries its engine block."""
    try:
        from app.mode_b.semiconductor import database as db
        if kind not in ("mosfet", "diode", "bridge"):
            raise HTTPException(404, "unknown component kind")
        return {"results": db.rank_by_loss(kind, req.design, req.criteria or {},
                                           top=int(req.top), mode=req.mode or "full")}
    except HTTPException:
        raise
    except Exception as e:
        log.exception("db rank"); raise HTTPException(500, str(e))

@app.post("/mode-b/semiconductor/database/extract", tags=["mode-b"])
async def semiconductor_datasheet_extract(kind: str = Form(...), file: UploadFile = File(...)):
    """Extract loss-model parameters from an uploaded PDF datasheet (designer confirms after)."""
    try:
        from app.mode_b.semiconductor import datasheet
        if kind not in ("mosfet", "diode", "bridge"):
            raise HTTPException(404, "unknown component kind")
        data = await file.read()
        return datasheet.extract(data, kind)
    except HTTPException:
        raise
    except Exception as e:
        log.exception("datasheet extract"); raise HTTPException(500, str(e))

@app.post("/mode-b/semiconductor/calculate", tags=["mode-b"])
def semiconductor_calculate(req: _SemiReq):
    """Validate the 3 parts, sweep all 9 input voltages, run the design-vs-engine
    consistency gate, and return per-point losses + worst-case summary."""
    try:
        from app.mode_b.semiconductor.adapter import calculate_semiconductor_losses
        res = calculate_semiconductor_losses(req.design, req.mosfet, req.diode, req.bridge,
                                             req.thermal, req.tj_limit)
        res.pop("cfg", None)               # internal/report use only
        return res
    except Exception as e:
        log.exception("semiconductor calculate"); raise HTTPException(500, str(e))

@app.post("/mode-b/semiconductor/figures", tags=["mode-b"])
def semiconductor_figures(req: _SemiReq):
    """Render the four loss/thermal figures (base64 PNG) for a confirmed design."""
    try:
        import tempfile, base64, os
        from app.mode_b.semiconductor.adapter import build_semi_cfg
        from app.mode_b.semiconductor import (pfc_loss_model as engine,
                                              pfc_component_intake as intake,
                                              pfc_visualization as viz)
        cfg, _ref = build_semi_cfg(req.design, req.mosfet, req.diode, req.bridge, req.thermal)
        ok, _ = intake.validate_design(cfg)
        if not ok:
            raise HTTPException(422, "design incomplete — confirm all required component fields first")
        sel = float(req.selected_vac) if req.selected_vac else float(cfg["run"]["vac_list"][0])
        out = {}
        with tempfile.TemporaryDirectory() as td:
            files = viz.build_step4_visuals(cfg, selected_vac=sel, vac_list=cfg["run"]["vac_list"],
                                            output_prefix=os.path.join(td, "semi"),
                                            backend=engine, tj_limits=req.tj_limit)
            for name, path in files.items():
                with open(path, "rb") as f:
                    out[name] = "data:image/png;base64," + base64.b64encode(f.read()).decode()
        return {"figures": out, "selected_vac": sel}
    except HTTPException:
        raise
    except Exception as e:
        log.exception("semiconductor figures"); raise HTTPException(500, str(e))

# ── input protection (MOV surge + NTC inrush) ────────────────────────────────
class _NtcReq(BaseModel):
    design: Dict[str, Any]
    cap:    Dict[str, Any] = {}          # approved capacitor (C_total_uF, V_rating)
    opts:   Dict[str, Any] = {}          # designer knobs (inrush target, margins, parasitics)

class _MovReq(BaseModel):
    design: Dict[str, Any]
    mosfet: Dict[str, Any] = {}          # selected MOSFET (vdss → downstream withstand)
    cap:    Dict[str, Any] = {}          # approved capacitor (V_rating)
    opts:   Dict[str, Any] = {}          # designer knobs (IEC level, criterion, margins)

@app.post("/mode-b/input-protection/ntc/calculate", tags=["mode-b"])
def input_protection_ntc(req: _NtcReq):
    """Size the NTC inrush limiter + bypass relay from the design grid + approved capacitor."""
    try:
        from app.mode_b.inputprotection.adapter import calculate_ntc
        return calculate_ntc(req.design, req.cap or {}, req.opts or {})
    except Exception as e:
        log.exception("ntc calculate"); raise HTTPException(500, str(e))

@app.post("/mode-b/input-protection/mov/calculate", tags=["mode-b"])
def input_protection_mov(req: _MovReq):
    """Size the MOV(s) per IEC 61000-4-5 (test level + performance criterion); compliance basis."""
    try:
        from app.mode_b.inputprotection.adapter import calculate_mov
        return calculate_mov(req.design, req.mosfet or {}, req.cap or {}, req.opts or {})
    except Exception as e:
        log.exception("mov calculate"); raise HTTPException(500, str(e))

class _IpReportReq(BaseModel):
    design:   Dict[str, Any]
    cap:      Dict[str, Any] = {}
    mosfet:   Dict[str, Any] = {}
    ntc_opts: Dict[str, Any] = {}
    mov_opts: Dict[str, Any] = {}

@app.post("/mode-b/input-protection/report", tags=["mode-b"])
def input_protection_report(req: _IpReportReq):
    """Standalone Chapters 8 (NTC inrush) + 9 (MOV surge & compliance) PDF."""
    try:
        from fastapi.responses import Response
        from app.mode_b.report_inputprotection import build_inputprotection_report
        pdf = build_inputprotection_report(req.design, req.cap or {}, req.mosfet or {},
                                           req.ntc_opts or {}, req.mov_opts or {})
        return Response(content=pdf, media_type="application/pdf",
                        headers={"Content-Disposition": 'attachment; filename="PFC_Input_Protection_Ch8_9.pdf"'})
    except Exception as e:
        log.exception("input protection report"); raise HTTPException(500, str(e))

@app.post("/mode-b/step6-magnetic-design", tags=["mode-b"])
def step6(req: ReportReq):
    try:
        _validate_state(req.state)
        from app.mode_b.magnetic_design import design_inductor, design_to_dict
        state = req.state; intake = state.get("intake",{}); ap = intake.get("application",{}); tsi = state.get("topology_specific_inputs",{})
        pout_lo = float(ap.get("output_power_w_low_line",1700)); vin_min = float(ap.get("vin_rms_min",90))
        vout = float(ap.get("output_bus_voltage_v",393)); fsw = float(tsi.get("recommended_frequency_hz") or 70000)
        crest = float(tsi.get("default_crest_ripple_ratio",0.095))
        lpy = _calc_l_py(pout_lo,vin_min,vout,fsw,crest)
        L_sel = round(lpy["L_uH"]/5)*5*1e-6; Iin_pk = lpy["Iin_pk"]; dIL = lpy["dIL"]
        import math as _m
        IL_rms = Iin_pk/2/_m.sqrt(2)*_m.sqrt(_m.pi)*0.98; IL_pk = Iin_pk/2+dIL/2
        tamb = float((intake.get("thermal") or {}).get("ambient_temp_c_max",50))
        tspot= float((intake.get("thermal") or {}).get("hotspot_limit_c",110))
        best, all_r = design_inductor(L=L_sel,IL_pk=IL_pk,IL_rms=IL_rms,dIL=dIL,fsw=fsw,T_budget=tspot-tamb)
        return {"status":"ok","inputs":{"L_calc_uH":lpy["L_uH"],"L_selected_uH":L_sel*1e6,
                "IL_pk_A":round(IL_pk,3),"IL_rms_A":round(IL_rms,3),"dIL_A":round(dIL,4),"fsw_Hz":fsw,"crest_ripple":crest},
                "best":design_to_dict(best) if best else None,"all_candidates":[design_to_dict(r) for r in all_r]}
    except Exception as e:
        log.exception("step6"); raise HTTPException(500, str(e))


# ══════════════════════════════════════════════════════════════════════════════
# MAGNETICS DATABASE AGENT — dedicated guardian for all magnetic material data
# Add new materials: POST /magnetics/add-custom or POST /magnetics/extract-pdf
# Hot reload after data files edited: POST /magnetics/reload
# ══════════════════════════════════════════════════════════════════════════════

from app.magnetics.db import get_db as _mag_db
from app.magnetics.extractor import extract_from_pdf
from pydantic import BaseModel as _BM
from typing import Optional as _Opt

class _AddCustomReq(_BM):
    material_data: dict
    commit: bool = False            # False → pending review, True → live immediately

class _CommitReq(_BM):
    pending_key: str
    corrections: dict = {}          # {field_path: corrected_value}

class _ExtractReq(_BM):
    pdf_base64: str                 # base64-encoded PDF bytes
    material_type: _Opt[str] = None # "ferrite" or "powder" (auto if omitted)
    supplier_hint: str = ""
    grade_hint: str = ""


@app.get("/magnetics/status", tags=["magnetics-db"])
def magnetics_status():
    """
    MagneticsDB status: material counts, core counts, load errors.
    Call after any data update to confirm load was successful.
    """
    return _mag_db().status()


@app.get("/magnetics/list", tags=["magnetics-db"])
def magnetics_list(supplier: str = None, mat_type: str = None,
                    topology: str = None, fsw_kHz: float = None):
    """
    List all materials with optional filters.
    Used by HITL Grade Selection gate to populate dropdown.
    """
    return _mag_db().get_materials(supplier=supplier, mat_type=mat_type,
                                    topology=topology, fsw_kHz=fsw_kHz)


@app.get("/magnetics/rank", tags=["magnetics-db"])
def magnetics_rank(fsw_Hz: float = 70000, Bac_pk_T: float = 0.054,
                    T_C: float = 100.0, topology: str = "boost_pfc"):
    """
    Rank all suitable materials for a given operating point.
    Used by HITL Grade Selection gate to sort candidates best-first.
    """
    return _mag_db().rank_grades(fsw_Hz=fsw_Hz, Bac_pk_T=Bac_pk_T,
                                  T_C=T_C, topology=topology)


@app.post("/magnetics/add-custom", tags=["magnetics-db"])
def magnetics_add_custom(req: _AddCustomReq):
    """
    Add a custom material entered by the designer.

    If commit=False (default): saves to pending/ for review.
      → Returns {status:"pending_review", key, errors, warnings}
      → Designer reviews flagged fields, then calls /magnetics/commit-pending
    
    If commit=True: validates and saves directly to live DB.
      → Returns {status:"committed", key, path}
      → Rejects if validation fails (returns errors list)

    After commit, call /magnetics/reload to pick up any file changes.
    """
    try:
        return _mag_db().add_custom_material(req.material_data, commit=req.commit)
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/magnetics/commit-pending", tags=["magnetics-db"])
def magnetics_commit_pending(req: _CommitReq):
    """
    Commit a pending material after designer review.
    corrections: dict of {field_path: new_value} for flagged/corrected fields.
    Example: {"steinmetz_25C.alpha": 1.25, "Bsat_vs_T.Bsat": [0.50, 0.47, 0.43]}
    """
    try:
        return _mag_db().commit_pending(req.pending_key, req.corrections)
    except Exception as e:
        raise HTTPException(500, str(e))


@app.delete("/magnetics/pending/{pending_key}", tags=["magnetics-db"])
def magnetics_delete_pending(pending_key: str):
    """Discard a pending material (designer rejected it after review)."""
    return _mag_db().delete_pending(f"pending:{pending_key}")


@app.post("/magnetics/extract-pdf", tags=["magnetics-db"])
def magnetics_extract_pdf(req: _ExtractReq):
    """
    Extract magnetic material data from an uploaded PDF datasheet using Claude AI.

    Workflow:
    1. Designer uploads PDF → this endpoint extracts all material data
    2. Each field has a confidence score (0-100%)
    3. Fields with confidence < 90% are flagged for review
    4. Returns a review payload showing all fields + confidence scores
    5. Designer reviews flagged fields via /magnetics/add-custom with corrections
    6. Confirmed material → /magnetics/commit-pending

    Input: PDF as base64 string.
    Output: {fields, flagged_count, high_conf_count, ready_to_commit, parse_errors}
    """
    try:
        import base64
        pdf_bytes = base64.b64decode(req.pdf_base64)
        result = extract_from_pdf(
            pdf_bytes,
            material_type_hint=req.material_type,
            supplier_hint=req.supplier_hint,
            grade_hint=req.grade_hint,
        )
        # Save extracted material to pending for review
        mat_dict = result.to_material_dict()
        pending = _mag_db().add_custom_material(mat_dict, commit=False)
        review  = result.to_review_payload()
        return {**review, "pending_key": pending.get("key"),
                "material_dict": mat_dict}
    except Exception as e:
        log.exception("PDF extraction endpoint error")
        raise HTTPException(500, str(e))


@app.post("/magnetics/reload", tags=["magnetics-db"])
def magnetics_reload():
    """
    Hot reload: scan all data files and reload MagneticsDB without server restart.
    Call this after:
      - Editing a JSON material file directly
      - Adding a new JSON file to data/magnetic_materials/
      - Editing a core catalog CSV
      - Editing the wire catalog
    """
    return _mag_db().reload()


@app.post("/magnetics/validate", tags=["magnetics-db"])
def magnetics_validate():
    """
    Validate all materials in the database.
    Returns list of validation errors (empty list = all pass).
    Run this after any data change to confirm integrity.
    """
    errors = _mag_db().validate_all()
    return {"valid": len(errors) == 0, "error_count": len(errors), "errors": errors}


@app.get("/magnetics/template/{material_type}", tags=["magnetics-db"])
def magnetics_template(material_type: str, supplier: str = "CustomSupplier",
                        grade: str = "MyGrade", mu: int = 60):
    """
    Get a blank JSON template for a new material.
    material_type: "ferrite" or "powder"
    Fill in the template fields and POST to /magnetics/add-custom.
    """
    from app.magnetics.schema import ferrite_template, powder_template
    if material_type == "ferrite":
        return ferrite_template(supplier, grade)
    elif material_type == "powder":
        return powder_template(supplier, grade, mu)
    raise HTTPException(400, f"material_type must be 'ferrite' or 'powder', got '{material_type}'")


# ══════════════════════════════════════════════════════════════════════════════
# MODE B — STEP 7: MAGNETIC DESIGN (Reference Step 13)
# STEP 8: TIME-DOMAIN CORE-LOSS MODELING (Reference Step 14)
#
# HITL flow:
#   Gate 1 → GET  /mode-b/step7/material-comparison   (Ferrite vs Powder)
#   Gate 2 → GET  /mode-b/step7/suppliers              (supplier list)
#   Gate 3 → POST /mode-b/step7/grade-options          (ranked grades)
#   Gate 3.5→ POST /mode-b/step7/wire-options          (wire top 3)
#   Engine → POST /mode-b/step7/run-sizing             (Top 5 core candidates)
#   Gate 4 → selection returned to frontend, designer picks one
#   Step 8 → POST /mode-b/step8/time-domain            (Pcore(t) analysis)
# ══════════════════════════════════════════════════════════════════════════════

import warnings as _w; _w.filterwarnings("ignore")
from app.mode_b.step7_magnetic_calc import (
    design_one_core, rank_candidates, DEFAULT_OPS, DesignResult)
from app.mode_b.calculations import build_design_ops_table
from app.mode_b.step8_time_domain import run_step8_full
from dataclasses import asdict as _asdict
import math as _math, numpy as _np

# ── Request models ────────────────────────────────────────────────────────────
class _GradeOptReq(BaseModel):
    material_type: str              # "ferrite" | "powder"
    supplier: str                   # "Ferroxcube" | "TDK" | "Magnetics Inc."
    fsw_Hz: float = 70000
    Bac_pk_T: float = 0.054
    T_operating_C: float = 100.0
    topology: str = "boost_pfc"

class _WireOptReq(BaseModel):
    wire_type: str                  # "litz" | "solid" | "tiw"
    IL_rms_A: float = 10.07
    IL_HF_rms_A: float = 0.0       # HF ripple RMS = dIL_pp/(2*sqrt(3))
    fsw_Hz: float = 70000
    T_C: float = 100.0
    J_target: float = 5.0
    n_options: int = 3

class _SizingReq(BaseModel):
    state: dict
    material_key: str
    wire_designation: Optional[str] = None   # None = agent sweeps all AWG
    wire_type: str = "magnet"
    max_height_mm: float = 9999
    max_footprint_mm: float = 9999
    max_stacks: int = 3
    J_min: float = 3.0
    J_max: float = 7.0
    J_target: float = 5.0                   # backward compat
    n_top: int = 5
    FFcu_min: float = 0.25
    FFcu_max: float = 0.45
    FFcu_limit: float = 0.45               # backward compat
    coated_only: bool = True
    custom_core: dict = {}
    n_parallel: int = 1
    mounting: str = 'horizontal'           # 'horizontal' | 'vertical'
    optimization_goal: str = 'best_performance'  # 'best_performance' | 'max_ffu'

class _Step8Req(BaseModel):
    state: dict                     # confirmed Mode A state
    approved_design: dict           # one DesignResult from run-sizing
    f_line_Hz: float = 60.0


# ── HITL Gate 1: material comparison ─────────────────────────────────────────
@app.get("/mode-b/step7/material-comparison", tags=["mode-b"])
def step7_material_comparison():
    """
    Returns the quantitative comparison table for Ferrite vs Powder core selection.
    Shown to designer in HITL Gate 1 before they choose material type.
    """
    return {
        "ferrite": {
            "label": "Gapped Ferrite",
            "Bsat_range_T": "0.40–0.45",
            "core_loss_at_70kHz": "Low — best at this frequency",
            "air_gap": "Single discrete gap",
            "fringing_loss": "Yes — modelled by Rogowski correction",
            "dc_bias": "Hard saturation, gap linearises B-H",
            "shapes": "ETD, EE, EC, RM, PQ — bobbin wound",
            "medical_creepage": "Standard ETD bobbin ≥10mm, extended-flange ≥14mm",
            "suppliers": ["Ferroxcube", "TDK"],
            "best_for": "70kHz PFC — ETD59/3C95 validated in Step 6",
        },
        "powder": {
            "label": "Powder Core (distributed gap)",
            "Bsat_range_T": "0.75–1.60",
            "core_loss_at_70kHz": "Moderate to high (material dependent)",
            "air_gap": "Distributed — no fringing loss",
            "fringing_loss": "None",
            "dc_bias": "Soft saturation — graceful rolloff, excellent tolerance",
            "shapes": "Toroid only — hand wound",
            "medical_creepage": "Requires TIW wire or Kapton tape layers",
            "suppliers": ["Magnetics Inc."],
            "best_for": "High current CCM PFC; excellent bias stability at high A·T",
        },
        "medical_advisory": {
            "show_when": "app_class == Medical",
            "message": (
                "Ferrite with ETD extended-flange bobbin simplifies IEC 60601-1 compliance "
                "(≥14mm creepage). Powder toroid requires TIW wire or ≥3 Kapton layers. "
                "Reference design uses Magnetics EDGE 3-stack (Step 13)."
            )
        }
    }


# ── HITL Gate 2: supplier options ────────────────────────────────────────────
@app.get("/mode-b/step7/suppliers", tags=["mode-b"])
def step7_suppliers(material_type: str = "ferrite"):
    """
    Returns available suppliers for the selected material type.
    HITL Gate 2.
    """
    if material_type == "ferrite":
        return {
            "suppliers": [
                {"key": "Ferroxcube", "label": "Ferroxcube",
                 "grades": 10, "note": "Widest grade range (3C90-3C98). 3C97 lowest loss at 70kHz. ★ Recommended."},
                {"key": "TDK", "label": "TDK",
                 "grades": 8,  "note": "N87/N95 widely stocked globally. Good for multi-source."},
            ]
        }
    elif material_type == "powder":
        return {
            "suppliers": [
                {"key": "Magnetics Inc.", "label": "Magnetics Inc.",
                 "grades": 9,  "note": "KoolMu, MPP, EDGE, XFlux, High Flux. ★ Recommended."},
            ]
        }
    raise HTTPException(400, f"material_type must be 'ferrite' or 'powder'")


# ── HITL Gate 3: grade ranking ────────────────────────────────────────────────

class _PowderRankReq(_BM):
    fsw_Hz: float = 70000
    Bac_pk_T: float = 0.054
    T_operating_C: float = 100.0
    Ipk_A: float = 16.73
    dIL_pp_A: float = 5.161
    Le_single_m: float = 0.0655
    L_target_uH: float = 240.0
    mu: int = 60                   # permeability to compare (default 60)

@app.post("/mode-b/step7/powder-ranking", tags=["mode-b"])
def step7_powder_ranking(req: _PowderRankReq):
    """
    Rank all 9 powder material lines at the specified µ for the given design point.
    Returns one entry per material line (best µ=60 representative), ranked 1-9.
    Includes DC bias, core loss, temp stability, cost tier, L variation estimate.
    """
    import math
    db = _mag_db()
    all_ranked = db.rank_grades(
        fsw_Hz=req.fsw_Hz, Bac_pk_T=req.Bac_pk_T,
        T_C=req.T_operating_C, topology="boost_pfc",
        Ipk_A=req.Ipk_A, dIL_pp_A=req.dIL_pp_A,
        Le_single_m=req.Le_single_m, L_target_uH=req.L_target_uH
    )
    # One entry per material line at target µ
    seen = {}
    for r in all_ranked:
        if r["type"] != "powder": continue
        if r["mu"] != req.mu: continue
        line = r["grade"]
        if line in seen: continue
        # Compute L variation
        try:
            m = db.get_material(r["material_key"])
            AL_nom_nH = m.get("basic",{}).get("AL_nom_nH", r["mu"] * 1.25)
            AL_2s = 2 * AL_nom_nH * 1e-9
            N_est = max(1, math.ceil(math.sqrt(req.L_target_uH * 1e-6 / AL_2s)))
            H_fl = N_est * (req.Ipk_A - req.dIL_pp_A/2) / req.Le_single_m / 79.577
            k_fl = db.get_k_bias(r["material_key"], H_fl)
            L_var_pct = round((1 - k_fl) * 100, 1)
            L_no_load_uH = round(N_est**2 * AL_2s * 1e6, 0)
            L_full_load_uH = round(N_est**2 * AL_2s * k_fl * 1e6, 0)
            N_est_val = N_est
        except Exception:
            L_var_pct = 0; L_no_load_uH = req.L_target_uH
            L_full_load_uH = req.L_target_uH; N_est_val = 0
        COST_LABELS = {"MPP":"$$$","High Flux":"$$","XFlux Ultra":"$$",
                       "Kool Mu Ultra":"$$","Kool Mu Max":"$$","Kool Mu HF":"$$",
                       "XFlux":"$","EDGE":"$","Kool Mu":"$"}
        BEST_FOR = {
            "EDGE":         "Best DC bias + 0 ppm/°C — reference PFC design material",
            "High Flux":    "Excellent DC bias + high Bsat 1.5T — cost effective",
            "Kool Mu Ultra":"Lowest core loss — best for high fsw designs",
            "MPP":          "Moderate DC bias + moderate loss — balanced premium",
            "Kool Mu":      "Standard. Wide availability. Lowest cost",
            "XFlux Ultra":  "Good DC bias + lower XFlux loss — high Bsat 1.6T",
            "XFlux":        "Best DC bias in high-Bsat class. High loss at 70kHz",
            "Kool Mu Max":  "Better DC bias than Kool Mu. Similar loss",
            "Kool Mu HF":   "Optimised for high frequency (>200kHz). Similar bias to Kool Mu",
        }
        seen[line] = {**r,
            "L_variation_pct": L_var_pct,
            "L_no_load_uH": int(L_no_load_uH),
            "L_full_load_uH": int(L_full_load_uH),
            "N_est_2stack": N_est_val,
            "cost_label": COST_LABELS.get(line,"$"),
            "best_for": BEST_FOR.get(line,""),
        }
    # Re-rank 1-9
    result = sorted(seen.values(), key=lambda r: r["score"])
    for i, r in enumerate(result): r["rank"] = i + 1
    return {"materials": result, "mu": req.mu, "fsw_kHz": req.fsw_Hz/1000,
            "design_Ipk_A": req.Ipk_A, "L_target_uH": req.L_target_uH}

@app.post("/mode-b/step7/grade-options", tags=["mode-b"])
def step7_grade_options(req: _GradeOptReq):
    """
    Returns ranked grade list for the selected supplier and operating point.
    Agent scores each grade by suitability (loss, Bsat, temp stability, topology fit).
    Best grade shown first. HITL Gate 3.
    """
    try:
        all_ranked = _mag_db().rank_grades(
            fsw_Hz=req.fsw_Hz, Bac_pk_T=req.Bac_pk_T,
            T_C=req.T_operating_C, topology=req.topology,
            Ipk_A=16.73, dIL_pp_A=5.161,
            Le_single_m=0.0655, L_target_uH=240.0
        )
        # Filter to selected supplier
        filtered = [r for r in all_ranked
                    if _mag_db().get_material(r["material_key"]).get("supplier","") == req.supplier
                    and _mag_db().get_material(r["material_key"]).get("type","") == req.material_type]
        # Re-rank within supplier
        for i, r in enumerate(filtered): r["rank"] = i + 1
        return {"grades": filtered, "supplier": req.supplier,
                "material_type": req.material_type, "count": len(filtered)}
    except Exception as e:
        log.exception("step7_grade_options"); raise HTTPException(500, str(e))


# ── HITL Gate 3.5: wire options ───────────────────────────────────────────────
@app.post("/mode-b/step7/wire-options", tags=["mode-b"])
def step7_wire_options(req: _WireOptReq):
    """
    Returns top wire options for the selected type (litz/solid/tiw).
    Designer selects wire type first, agent shows top 3 specs. HITL Gate 3.5.
    """
    try:
        # Type alias ("magnet"->"solid-enamel" etc.) handled inside get_wire_options.
        # IL_rms_A is already per-conductor (frontend divides Irms by nPar before sending).
        # Show all wires (min_cu_fraction=0) so designer can choose from full table.
        opts = _mag_db().get_wire_options(
            req.wire_type, req.IL_rms_A, req.fsw_Hz,
            req.T_C, req.J_target, n_options=50, min_cu_fraction=0.0,
            IL_HF_rms_A=req.IL_HF_rms_A
        )
        rho_T = 1.72e-8 * (1 + 0.00393 * (req.T_C - 20))
        delta = _math.sqrt(rho_T / (_math.pi * req.fsw_Hz * 4*_math.pi*1e-7)) * 1e3

        feasible    = [o for o in opts if o.get("current_ok") and o.get("skin_ok")]
        skin_issues = [o for o in opts if not o.get("skin_ok")]
        wire_reason = ""
        if not opts:
            wire_reason = f"No {req.wire_type} wire found in catalog."
        elif not feasible and skin_issues:
            best_kHz = max(float(o.get("skin_limited_kHz", 0)) for o in skin_issues)
            # PFC context: skin effect applies only to HF ripple (~15% of total current).
            # Net Rac/Rdc penalty ≈ 2% — not a hard barrier.
            # The ⚠skin badge is informational; DC resistance is the real driver.
            wire_reason = (
                f"⚠skin = informational for PFC. Skin effect applies only to HF ripple "
                f"(~15% of current) → Rac/Rdc penalty ≈ 2%%. "
                f"Primary concern: {req.wire_type} has lower Cu area than Litz "
                f"→ higher DCR → more copper loss. Run sizing to compare."
            )
        elif not feasible:
            best_cu = max(float(o.get("Cu_area_mm2", 0)) for o in opts)
            need_cu = req.IL_rms_A / req.J_target if req.J_target > 0 else 0
            wire_reason = (
                f"Largest available gauge has {best_cu:.3f}mm²; "
                f"{req.IL_rms_A:.1f}A at J={req.J_target:.0f}A/mm² needs {need_cu:.3f}mm². "
                f"Lower J target or use a different wire type."
            )

        return {
            "wire_type":     req.wire_type,
            "skin_depth_mm": round(delta, 4),
            "max_strand_dia": round(2*delta, 4),
            "options":       opts,
            "feasible_count": len(feasible),
            "wire_reason":   wire_reason,
            "medical_note":  ("TIW eliminates Kapton tape for IEC 60601-1 creepage on toroids."
                              if req.wire_type == "tiw" else ""),
        }
    except Exception as e:
        log.exception("step7_wire_options"); raise HTTPException(500, str(e))


# ── Core sizing engine → Top 5 ────────────────────────────────────────────────
@app.post("/mode-b/step7/run-sizing", tags=["mode-b"])
def step7_run_sizing(req: _SizingReq):
    """
    Core sizing engine (Reference Step 13).
    Runs design_one_core() for every catalog core matching the selected material
    and size constraints, then returns the Top 5 ranked candidates.

    Input: confirmed Mode A state + designer's HITL selections.
    Output: top_5 list with full Step 13 results per candidate.

    Each candidate in top_5 includes:
      - All Step 13 sub-steps (turns, flux, winding, losses at 9 op-points)
      - Composite score + label (Best overall / Smallest / Lowest loss / Lowest temp / Economical)
      - Pass/fail status and fail reasons
    """
    try:
        _validate_state(req.state)
        state = req.state
        tsi   = state.get("topology_specific_inputs", {})
        intake= state.get("intake", {})

        # Extract design parameters from confirmed state
        L_uH   = float(tsi.get("confirmed_L_uH_sel", tsi.get("recommended_L_uH", 240)))
        fsw_Hz = float(tsi.get("recommended_frequency_hz", 70000))
        Vout   = float(intake.get("application",{}).get("output_bus_voltage_v", 393))
        Pout_lo= float(intake.get("application",{}).get("output_power_w_low_line", 1700))
        Pout_hi= float(intake.get("application",{}).get("output_power_w_high_line", 3600))
        Vin_lo = float(intake.get("application",{}).get("vin_rms_min", 90))
        Vin_hi = float(intake.get("application",{}).get("vin_rms_max", 264))
        N_ph   = int(state.get("selected_channels", 2))
        T_amb  = float(intake.get("thermal",{}).get("ambient_temp_c_max", 50))
        T_spot = float(intake.get("thermal",{}).get("hotspot_limit_c", 110))
        dT_bgt = T_spot - T_amb
        app_cls= intake.get("compliance",{}).get("application_class", "Industrial")
        r_input= float(tsi.get("default_crest_ripple_ratio", 0.095)) or 0.095

        # Build the design-derived 9-point OPS table — [Vin_rms, Pout, eta, PF,
        # Iph_rms] — via the SAME canonical_ops_table -> step2_input_params ->
        # step4_inductance -> step5_phase_rms chain the documentation chapters
        # use for the "accurate" Table 3.2.4a/b. Replaces the stale, hardcoded
        # DEFAULT_OPS (copied from a different reference design) so Table 3.4.1
        # / 3.6.1 always agree with Table 3.2.4 — single source of truth.
        try:
            OPS, _L_phi_doc = build_design_ops_table(
                Vin_lo, Vin_hi, Pout_lo, Pout_hi, Vout, fsw_Hz, r_input)
        except Exception:
            OPS = DEFAULT_OPS

        # Compute per-phase electrical params at worst-case (90 Vac low line)
        eta  = float(OPS[0, 2])
        PF   = float(OPS[0, 3])
        Pin  = Pout_lo / eta
        Vin_pk = Vin_lo * _math.sqrt(2)
        Ipk_line = _math.sqrt(2) * Pin / (Vin_lo * PF)
        Ipk_A    = Ipk_line / N_ph + float(tsi.get("dIL_pp_A", 5.161)) / 2
        Irms_A   = float(tsi.get("Iph_rms_A", float(OPS[0, 4])))
        IL_HF    = Irms_A * 0.114      # approximate HF ripple fraction
        dIL_pp   = float(tsi.get("dIL_pp_A", 5.161))

        # Get the selected material info
        mat_key = req.material_key
        mat_d   = _mag_db().get_material(mat_key)
        supplier= mat_d.get("supplier","")
        mat_type= mat_d.get("type","ferrite")

        # Map supplier to catalog tag
        sup_tag = supplier.lower().replace(" ","_").replace(".","").replace(",","")

        # Resolve wire: alias ("magnet"->"solid-enamel") handled inside get_wire_options.
        # Per-conductor current: bifilar/trifilar split Irms across n_par strands.
        n_par       = getattr(req, 'n_parallel', 1) or 1
        _wtype      = getattr(req, 'wire_type', 'litz').lower() or 'litz'
        Irms_cond   = Irms_A / n_par
        # Use J_max for query to return widest selection, then pick by designation
        _j_query    = req.J_max if req.J_max > 0 else req.J_target
        wire_opts   = _mag_db().get_wire_options(
            _wtype, Irms_cond, fsw_Hz, 100.0, _j_query,
            n_options=50, min_cu_fraction=0.10)
        wire = next((w for w in wire_opts if w.get("designation","") == req.wire_designation), None)
        if wire is None and wire_opts:
            wire = wire_opts[0]   # best available if designation not matched
        if wire is None:
            raise HTTPException(400, f"No {_wtype} wire found for designation {req.wire_designation!r}")
        # Apply n_parallel: multiply Cu area and divide R to get bifilar/trifilar totals
        wire = dict(wire)
        if n_par > 1:
            wire['Cu_area_mm2'] = wire.get('Cu_area_mm2', 1.0) * n_par
            # R_per_m_20C_ohm: calc.py reads this and divides by n_parallel once.
            # Do NOT pre-divide here — that would double-count and give R/4 instead of R/2.
        wire['n_parallel'] = n_par

        # Filter cores — coated_only for Medical
        mat_line = mat_d.get('material_line', None)
        mat_mu   = mat_d.get('mu_initial', None)
        # Sweep ALL permeabilities of the selected material family so
        # the engine finds the globally optimal mu, not just the one
        # the user happened to select in Gate 2.
        catalog_cores = _mag_db().filter_cores(
            supplier=sup_tag,
            max_height_mm=req.max_height_mm,
            max_stacks=req.max_stacks,
            coated_only=getattr(req,'coated_only',True),
            material_line=mat_line,
            mu=None,  # None = all permeabilities of this material family
            mounting=getattr(req, 'mounting', 'horizontal'),
        )
        # Prepend any custom core entered by designer
        custom = getattr(req, 'custom_core', None)
        if custom and isinstance(custom, dict) and custom.get('part_number'):
            catalog_cores = [custom] + list(catalog_cores)
        if not catalog_cores:
            return {"status": "no_cores", "message": f"No cores found for {supplier} within height {req.max_height_mm}mm"}

        FFcu_lim = getattr(req, 'FFcu_limit', 0.40)

        # Run sizing engine for every candidate
        all_results: list[DesignResult] = []
        for core in catalog_cores:
            try:
                # Derive the exact material JSON key for this core's
                # material + permeability (e.g. "edge_40", "mpp_125")
                # Derive DB key from core dict fields (e.g. "edge_60", "mpp_125")
                _ln = str(core.get("material_line","")).lower().replace(" ","_")
                _mu = int(core.get("mu", core.get("mu_initial", core.get("permeability", 60))))
                core_mat_key = f"{_ln}_{_mu}" if _ln else mat_key
                r = design_one_core(
                    core=core, material_key=core_mat_key,
                    L_target_H=L_uH*1e-6, Ipk_A=Ipk_A,
                    Irms_A=Irms_A, IL_HF_rms_A=IL_HF,
                    dIL_pp_A=dIL_pp, fsw_Hz=fsw_Hz,
                    wire=wire, N_phases=N_ph,
                    OPS=OPS, T_amb_C=T_amb,
                    dT_budget_C=dT_bgt, app_class=app_cls,
                    FFcu_limit=FFcu_lim,
                    mounting=getattr(req, 'mounting', 'horizontal'),
                )
                all_results.append(r)
            except Exception:
                pass

        top5 = rank_candidates(all_results, n_top=req.n_top,
                               optimization_goal=getattr(req, 'optimization_goal', 'best_performance'))
        passed = sum(1 for r in all_results if r.passed)

        def _serialize(r: DesignResult) -> dict:
            d = {}
            for f in r.__dataclass_fields__:
                v = getattr(r, f)
                if isinstance(v, _np.ndarray): v = v.tolist()
                d[f] = v
            return d

        return {
            "status":        "ok",
            "step":          7,
            "material_key":  mat_key,
            "wire":          req.wire_designation,
            "cores_evaluated": len(all_results),
            "cores_passed":  passed,
            "top_5": [
                {"label": t["label"], "rank": t.get("rank", i+1), "result": _serialize(t["result"])}
                for i, t in enumerate(top5)
            ],
            "design_params": {
                "L_uH": L_uH, "fsw_Hz": fsw_Hz, "Ipk_A": round(Ipk_A,4),
                "Irms_A": round(Irms_A,4), "T_amb_C": T_amb, "dT_budget_C": dT_bgt,
            }
        }
    except HTTPException: raise
    except Exception as e:
        log.exception("step7_run_sizing"); raise HTTPException(500, str(e))


# ── Simulation-Agent SHADOW endpoint (Phase 1) ───────────────────────────────
#   Additive cross-check only. Builds the sim-agent package from the SELECTED
#   candidate + state, runs the headless engine (fed our DB physics via fields),
#   and compares its numbers to our step7 figures. Does NOT touch run-sizing,
#   Result, or Review. Safe to remove (route + import) with zero side effects.
class _SimReq(BaseModel):
    state: dict                # confirmed Mode A/B state
    approved_design: dict      # one serialized DesignResult (the core sent to Review)
    wire_type: str = 'litz'    # designer's wire-type selection
    line_Hz: float = 60.0


def _sim_crosscheck(result: dict, sim: dict) -> dict:
    """Step-7 vs field-engine comparison via the single shared definition
    (sim_agent.adapter.crosscheck_rows) — apples-to-apples on a common basis."""
    from app.sim_agent import adapter
    rows = adapter.crosscheck_rows(result, sim)
    checkable = [r for r in rows if r["within"] is not None]
    return {"rows": rows,
            "all_within_band": (all(r["within"] for r in checkable) if checkable else None),
            "n_checked": len(checkable)}


@app.post("/mode-b/step7/simulate", tags=["mode-b"])
def step7_simulate(req: _SimReq):
    """Phase-1 shadow: validate+compute the sim-agent package and cross-check vs step7.
    Never throws on bad input (returns ok:false); 500 only on unexpected server error."""
    from app.sim_agent import adapter
    from app.sim_agent import pfc_inductor_engine as _eng
    try:
        result = req.approved_design or {}
        pkg, vr = adapter.build_and_validate(result, req.state,
                                             wire_type=req.wire_type, lineHz=req.line_Hz)
        if not vr.ok:
            return {"status": "invalid_package", "ok": False,
                    "errors": vr.errors, "warnings": vr.warnings}
        sim = _eng.compute(pkg)
        return {
            "status": "ok", "ok": True,
            "verdict": sim["verdict"],
            "tiers": sim["tier"],
            "validation": vr.as_dict(),
            "statics": sim["statics"],
            "worst": sim["worst"],
            "crosscheck": _sim_crosscheck(result, sim),
            "package": pkg,   # SAME object the engine used → viewer parity (Phase 2)
        }
    except _eng.SpecError as e:
        return {"status": "invalid_package", "ok": False, "errors": e.errors}
    except Exception as e:
        log.exception("step7_simulate"); raise HTTPException(500, str(e))


# ── Phase B: step7 view contract (single render payload for all screens) ──────
@app.post("/mode-b/step7/view-contract", tags=["mode-b"])
def step7_view_contract(req: _SimReq):
    """Authoritative render payload from step7: scalars + 90 Vac per-θ waveforms +
    9-point sweep. Result / Review / Simulation all RENDER this (no recompute) so they
    show identical values. Additive/read-only."""
    from app.mode_b.step7_magnetic_calc import build_view_contract
    try:
        return {"status": "ok",
                "contract": build_view_contract(req.approved_design or {}, req.state or {})}
    except Exception as e:
        log.exception("step7_view_contract"); raise HTTPException(500, str(e))


# ── STEP 8: Time-domain core-loss modeling (Reference Step 14) ────────────────
@app.post("/mode-b/step8/time-domain", tags=["mode-b"])
def step8_time_domain(req: _Step8Req):
    """
    Time-domain core-loss analysis (Reference Step 14).
    
    Computes Bac_pk(t) and Pcore(t) across the half line cycle for all 9 Vac.
    Fits power-law model Pcore = k × B^n to crest-point data from Step 7.
    Integrates for accurate Pcore_avg — more accurate than crest-point alone.

    Key result: at 90Vac crest-point overestimates Pcore,avg by ~83%.
                at 230Vac crest-point underestimates Pcore,avg by ~126%.
    """
    try:
        _validate_state(req.state)
        d = req.approved_design
        state = req.state
        intake= state.get("intake",{})

        tsi          = state.get("topology_specific_inputs", {})
        application  = intake.get("application", {})

        material_key = d.get("material_key")
        core_type    = d.get("core_type", "ferrite")
        N            = int(d.get("N", 49))
        n_ph         = int(state.get("selected_channels", 2))
        Ae_mm2       = float(d.get("Ae_total_mm2", 231))
        Ve_cm3       = float(d.get("Ve_total_cm3", 15.977))
        Le_single_m  = float(d.get("Le_single_mm", 0)) * 1e-3
        loss_25C     = d.get("loss_table_25C", [])
        fsw_Hz       = float(tsi.get("recommended_frequency_hz", 70000))
        Vbus         = float(application.get("output_bus_voltage_v", 393))

        # Total zero-bias inductance L0 = AL_nom_total × N² (single-stack AL ×
        # stack count), matching the chain Step 7 uses for _half_cycle_averages.
        L0_nom_H = float(d.get("AL_nom_nH", 0)) * int(d.get("stacks", 1)) * 1e-9 * N**2

        # Rdc/Rac at the converged operating temperature — exact linear
        # interpolation between the stored 25 °C / 100 °C DCR values, since
        # DCR(T) = R_pm_20 × (1 + ALPHA_CU×(T−20)) × Cu_len is linear in T
        # (same chain Step 7 uses to derive Rdc_Tc/Rac_Tc for _half_cycle_averages).
        T_core_C  = float(d.get("T_core_C", 100.0))
        DCR_25_Ω  = float(d.get("DCR_25C_mOhm", 0)) * 1e-3
        DCR_100_Ω = float(d.get("DCR_100C_mOhm", 0)) * 1e-3
        Rdc_Tc    = DCR_25_Ω + (DCR_100_Ω - DCR_25_Ω) * (T_core_C - 25.0) / 75.0
        Rac_Tc    = Rdc_Tc * float(d.get("Rac_Rdc", 1.0))

        # Canonical 9-point operating-matrix inputs — same corner conditions
        # (vin_min/max, pout_lo/hi, r_input) used to build Table 3.2.4/3.4.1's
        # OPS array, so Step 8's per-point Vin_pk/Iin_pk/Iph_rms agree exactly.
        vin_min  = float(application.get("vin_rms_min", 90))
        vin_max  = float(application.get("vin_rms_max", 264))
        pout_lo  = float(application.get("output_power_w_low_line", 1700))
        pout_hi  = float(application.get("output_power_w_high_line", 3600))
        r_input  = float(tsi.get("default_crest_ripple_ratio", 0.095)) or 0.095

        if not material_key:
            raise HTTPException(400, "approved_design must contain material_key")
        if not loss_25C:
            raise HTTPException(400, "approved_design must contain loss_table_25C (from step7/run-sizing)")

        result = run_step8_full(
            material_key=material_key, core_type=core_type, N=N, n_ph=n_ph,
            Ae_total_m2=Ae_mm2 * 1e-6,
            Ve_total_m3=Ve_cm3 * 1e-6,
            Le_single_m=Le_single_m, L0_nom_H=L0_nom_H,
            fsw_Hz=fsw_Hz, Vbus=Vbus,
            Rdc_Tc=Rdc_Tc, Rac_Tc=Rac_Tc, T_core_C=T_core_C,
            loss_table_25C=loss_25C,
            vin_min=vin_min, vin_max=vin_max, pout_lo=pout_lo, pout_hi=pout_hi,
            r_input=r_input,
            f_line=req.f_line_Hz,
        )
        return {"status": "ok", "step": 8, **result}
    except HTTPException: raise
    except Exception as e:
        log.exception("step8_time_domain"); raise HTTPException(500, str(e))


# ── STEP 15: Vout Capacitor Calculation (Hold-up + Ripple) ───────────────────
_STANDARD_CAP_UF = [
    47, 68, 82, 100, 120, 150, 180, 220, 270, 330, 390, 470, 560, 680, 820,
    1000, 1200, 1500, 1800, 2200, 2700, 3300, 3900, 4700, 5600, 6800, 8200, 10000,
]

class _CapCalcReq(BaseModel):
    state:           dict
    t_hold_ms:       float = 20.0    # hold-up time (ms)
    V_min_holdup_V:  float = 300.0   # min bus voltage at end of hold-up
    ripple_pct:      float = 2.0     # peak-to-peak ripple as % of Vout
    V_rating:        int   = 450     # capacitor voltage rating (V)

@app.post("/mode-b/step15/capacitor-calc", tags=["mode-b"])
def step15_capacitor_calc(req: _CapCalcReq):
    """
    Step 15 — Output capacitor sizing for PFC bus.
    Calculates C for ripple (2×f_line) and hold-up time, then proposes
    standard E6/E12 electrolytic options (single and parallel combinations).
    """
    import math as _m
    state  = req.state
    _validate_state(state)
    intake = state.get('intake', {})
    ap     = intake.get('application', {})

    Vout    = float(ap.get('output_bus_voltage_v',       393))
    Pout_lo = float(ap.get('output_power_w_low_line',   1700))
    Pout_hi = float(ap.get('output_power_w_high_line',  3600))
    Pout    = max(Pout_lo, Pout_hi)   # size for worst-case (highest) power
    f_line  = float(ap.get('nominal_line_frequency_hz', 60))

    t_hold = req.t_hold_ms / 1000.0
    V_min  = req.V_min_holdup_V
    if V_min >= Vout:
        raise HTTPException(400, "V_min_holdup_V must be less than Vout")

    I_out     = Pout / Vout
    # RMS capacitor current — dominant 2×f_line component for single-phase PFC
    # I_cap,rms ≈ I_out × √(π²/8 − 1)  (≈ 0.4834 × I_out)
    I_cap_rms = I_out * _m.sqrt(_m.pi**2 / 8.0 - 1.0)

    # Ripple capacitance: C_ripple = P_out / (4π·f_line·V_out·ΔV)
    dV          = (req.ripple_pct / 100.0) * Vout
    C_ripple_uF = Pout / (4 * _m.pi * f_line * Vout * dV) * 1e6

    # Hold-up capacitance: C_holdup = 2·P_out·t_hold / (V_out²−V_min²)
    C_holdup_uF = 2 * Pout * t_hold / (Vout**2 - V_min**2) * 1e6

    C_req  = max(C_ripple_uF, C_holdup_uF)
    factor = 'holdup' if C_holdup_uF >= C_ripple_uF else 'ripple'

    def _dV(C_uF):
        return Pout / (4 * _m.pi * f_line * Vout * max(C_uF * 1e-6, 1e-12))

    def _t_hold(C_uF):
        return (C_uF * 1e-6) * (Vout**2 - V_min**2) / (2 * Pout) * 1000  # ms

    # Build options: for n_par = 1…4, find smallest standard value where total ≥ C_req
    V_rt  = req.V_rating
    opts  = []
    # Add one failing option (closest standard below C_req, single cap)
    for c in reversed(_STANDARD_CAP_UF):
        if c < C_req:
            margin = (c - C_req) / C_req * 100
            opts.append({'n_caps':1,'C_each_uF':c,'C_total_uF':c,'V_rating':V_rt,
                'config':f"1×{c}µF/{V_rt}V",
                'margin_pct':round(margin,1),
                'dV_actual_V':round(_dV(c),2),'dV_actual_pct':round(_dV(c)/Vout*100,2),
                't_holdup_actual_ms':round(_t_hold(c),1),'passes':False})
            break

    for n in range(1, 5):
        for c in _STANDARD_CAP_UF:
            total = n * c
            if total >= C_req:
                margin = (total - C_req) / C_req * 100
                cfg    = f"{n}×{c}µF/{V_rt}V" if n > 1 else f"1×{c}µF/{V_rt}V"
                opts.append({'n_caps':n,'C_each_uF':c,'C_total_uF':total,'V_rating':V_rt,
                    'config':cfg,
                    'margin_pct':round(margin,1),
                    'dV_actual_V':round(_dV(total),2),'dV_actual_pct':round(_dV(total)/Vout*100,2),
                    't_holdup_actual_ms':round(_t_hold(total),1),'passes':True})
                break

    return {
        'status':'ok','step':15,
        'Vout_V':Vout,'Pout_W':Pout,'f_line_Hz':f_line,
        'I_out_A':round(I_out,3),'I_cap_rms_A':round(I_cap_rms,3),
        'C_ripple_uF':round(C_ripple_uF,1),'C_holdup_uF':round(C_holdup_uF,1),
        'C_required_uF':round(C_req,1),'limiting_factor':factor,
        'dV_ripple_spec_V':round(dV,2),'dV_ripple_spec_pct':req.ripple_pct,
        't_hold_ms':req.t_hold_ms,'V_min_holdup_V':V_min,
        'options':opts,
    }


# ── STEP 15 spec endpoints ────────────────────────────────────────────────────

class _CapDesignReq(BaseModel):
    state: dict

class _CapVerifyReq(BaseModel):
    state:          dict
    supplier:       str
    series:         str
    voltage_rating: int
    configuration:  List[Dict[str, Any]]   # [{"value_uF": int, "qty": int}]

@app.post("/mode-b/step15/capacitor-design", tags=["mode-b"])
def step15_capacitor_design(req: _CapDesignReq):
    """Step 15 — full capacitor design calculation (15.1–15.5 + suggested configs)."""
    try:
        _validate_state(req.state)
        from app.mode_b.step15_capacitor import run_capacitor_design
        result = run_capacitor_design(req.state)
        return {"status": "ok", **result}
    except Exception as e:
        log.exception("step15_capacitor_design"); raise HTTPException(500, str(e))

@app.post("/mode-b/step15/verify-configuration", tags=["mode-b"])
def step15_verify_configuration(req: _CapVerifyReq):
    """Step 15 — verify capacitor configuration (15.7 + 15.8) + thermal table (15.9)."""
    try:
        _validate_state(req.state)
        from app.mode_b.step15_capacitor import (
            run_capacitor_design, verify_configuration, calculate_thermal_table)
        base = run_capacitor_design(req.state)
        result = verify_configuration(
            config         = req.configuration,
            supplier       = req.supplier,
            series         = req.series,
            voltage_rating = req.voltage_rating,
            worst          = base["worst_case"],
            low            = base["low_line"],
            Vout           = base["inputs"]["Vout_V"],
            f_line         = base["inputs"]["f_line_Hz"],
            Vdc_min        = base["inputs"]["Vdc_min_V"],
            C_required_uF  = base["C_required_uF"],
        )
        # Enhancement 2 — add thermal table across all 9 operating points
        thermal = calculate_thermal_table(
            config         = req.configuration,
            state          = req.state,
            supplier       = req.supplier,
            series         = req.series,
            voltage_rating = req.voltage_rating,
        )
        result["thermal_table_data"] = thermal
        return {"status": "ok", **result}
    except Exception as e:
        log.exception("step15_verify_configuration"); raise HTTPException(500, str(e))

@app.get("/mode-b/step15/series-options", tags=["mode-b"])
def step15_series_options(supplier: str):
    """Step 15 — return all series for a given supplier."""
    try:
        import json as _j, os as _os
        _db_path = _os.path.join(_os.path.dirname(__file__),
                                  "mode_b", "data", "cap_database.json")
        with open(_db_path, encoding="utf-8") as f:
            db = _j.load(f)
        sup_data = db.get(supplier, {})
        series = []
        for name, meta in sup_data.items():
            series.append({
                "name":            name,
                "series_code":     meta.get("series_code", ""),
                "temp_rating_C":   meta.get("temp_rating_C", 85),
                "life_hours":      meta.get("life_hours", 2000),
                "voltage_ratings": list(meta.get("voltage_ratings", {}).keys()),
            })
        return {"supplier": supplier, "series": series}
    except Exception as e:
        log.exception("step15_series_options"); raise HTTPException(500, str(e))

@app.get("/mode-b/step15/cap-values", tags=["mode-b"])
def step15_cap_values(supplier: str, series: str, voltage_rating: int):
    """Step 15 — return available capacitor values for supplier+series+voltage."""
    try:
        import json as _j, os as _os
        _db_path = _os.path.join(_os.path.dirname(__file__),
                                  "mode_b", "data", "cap_database.json")
        with open(_db_path, encoding="utf-8") as f:
            db = _j.load(f)
        vkey   = str(voltage_rating)
        values = (db.get(supplier, {})
                    .get(series, {})
                    .get("voltage_ratings", {})
                    .get(vkey, []))
        return {"supplier": supplier, "series": series,
                "voltage_rating": voltage_rating, "values_uF": values}
    except Exception as e:
        log.exception("step15_cap_values"); raise HTTPException(500, str(e))


# ── HV Capacitor Database (real parts) ───────────────────────────────────────

class _CapFilterReq(BaseModel):
    voltage_V:        Optional[int]   = None
    op_temp:          Optional[str]   = None
    lifetime:         Optional[str]   = None
    tolerance:        Optional[str]   = None
    lead_spacing_mm:  Optional[float] = None
    height_max_mm:    Optional[float] = None
    diameter_max_mm:  Optional[float] = None

class _CapTableReq(BaseModel):
    state:            dict
    capacitance_uF:   float
    n_parallel:       int   = 1
    voltage_V:        Optional[int]   = None
    op_temp:          Optional[str]   = None
    lifetime:         Optional[str]   = None
    tolerance:        Optional[str]   = None
    lead_spacing_mm:  Optional[float] = None
    height_max_mm:    Optional[float] = None
    diameter_max_mm:  Optional[float] = None

@app.get("/mode-b/step15/hvcap-filter-options", tags=["mode-b"])
def step15_hvcap_filter_options():
    """Step 15 — return distinct filter values from the HV cap database."""
    try:
        from app.mode_b.step15_cap_db import get_filter_options
        return {"status": "ok", **get_filter_options()}
    except Exception as e:
        log.exception("hvcap_filter_options"); raise HTTPException(500, str(e))

@app.post("/mode-b/step15/hvcap-filter-caps", tags=["mode-b"])
def step15_hvcap_filter_caps(req: _CapFilterReq):
    """Step 15 — return capacitance values available after applying filters."""
    try:
        from app.mode_b.step15_cap_db import filter_capacitances
        caps = filter_capacitances(
            voltage_V=req.voltage_V, op_temp=req.op_temp,
            lifetime=req.lifetime, tolerance=req.tolerance,
            lead_spacing_mm=req.lead_spacing_mm,
            height_max_mm=req.height_max_mm,
            diameter_max_mm=req.diameter_max_mm,
        )
        return {"status": "ok", "capacitances_uF": caps, "count": len(caps)}
    except Exception as e:
        log.exception("hvcap_filter_caps"); raise HTTPException(500, str(e))

class _CapLifetimeReq(BaseModel):
    state:          dict
    part_number:    str
    qty:            int   = 1
    Tamb_C:         float = 45.0    # ambient temperature (°C)

@app.post("/mode-b/step15/cap-lifetime", tags=["mode-b"])
def step15_cap_lifetime(req: _CapLifetimeReq):
    """Step 15 — compute 3-method lifetime for a selected capacitor."""
    try:
        _validate_state(req.state)
        from app.mode_b.step15_cap_db import _load, calculate_lifetime
        from app.mode_b.step15_capacitor import run_capacitor_design
        db   = _load()
        cap  = next((r for r in db if r['part_number'] == req.part_number), None)
        if not cap:
            raise HTTPException(404, f"Part {req.part_number!r} not found in database")
        base     = run_capacitor_design(req.state)
        I_LF     = float(base["worst_case"].get("I_LF_A", 0))
        I_HF     = float(base["worst_case"].get("I_HF_A", 0))
        Vout     = float(base["inputs"]["Vout_V"])
        result   = calculate_lifetime(cap, req.qty, I_LF, I_HF, req.Tamb_C, Vout)
        return {"status": "ok", **result}
    except HTTPException: raise
    except Exception as e:
        log.exception("cap_lifetime"); raise HTTPException(500, str(e))

@app.post("/mode-b/step15/hvcap-cap-table", tags=["mode-b"])
def step15_hvcap_cap_table(req: _CapTableReq):
    """Step 15 — return part table for a specific capacitance with ESR + Irms."""
    try:
        _validate_state(req.state)
        from app.mode_b.step15_cap_db import get_cap_table
        from app.mode_b.step15_capacitor import run_capacitor_design
        base     = run_capacitor_design(req.state)
        I_total  = base["worst_case"]["I_total_A"]
        Vout     = base["inputs"]["Vout_V"]
        f_line   = base["inputs"]["f_line_Hz"]
        C_req    = base["C_required_uF"]
        table = get_cap_table(
            capacitance_uF=req.capacitance_uF,
            n_parallel=req.n_parallel,
            I_total_A=I_total, Vout=Vout, f_line=f_line,
            C_required_uF=C_req,
            voltage_V=req.voltage_V, op_temp=req.op_temp,
            lifetime=req.lifetime, tolerance=req.tolerance,
            lead_spacing_mm=req.lead_spacing_mm,
            height_max_mm=req.height_max_mm,
            diameter_max_mm=req.diameter_max_mm,
        )
        return {"status": "ok", "table": table, "count": len(table),
                "I_total_A": I_total, "I_per_cap_A": round(I_total/max(req.n_parallel,1), 3)}
    except Exception as e:
        log.exception("hvcap_cap_table"); raise HTTPException(500, str(e))


# ── Enhancement 1 — Custom capacitor from datasheet ──────────────────────────
from fastapi import UploadFile, File, Form

@app.post("/mode-b/step15/custom-capacitor", tags=["mode-b"])
async def step15_custom_capacitor(
    file:         UploadFile = File(...),
    part_number:  str        = Form(...),
    state:        str        = Form("{}"),
):
    """Upload a capacitor datasheet PDF and extract key parameters."""
    try:
        import json as _j
        from app.mode_b.step15_capacitor import parse_custom_cap_datasheet
        pdf_bytes = await file.read()
        result    = parse_custom_cap_datasheet(pdf_bytes, part_number)
        return {"status": "ok", **result}
    except Exception as e:
        log.exception("step15_custom_capacitor"); raise HTTPException(500, str(e))


# ── Enhancement 4 — Step 15 report generation ─────────────────────────────────
class _Step15ReportReq(BaseModel):
    state:           Dict[str, Any]
    approved_design: Dict[str, Any]
    step15_result:   Dict[str, Any]
    step16_params:   Optional[Dict[str, Any]] = None   # None = skip Step 16

@app.post("/mode-b/step15/generate-report", tags=["mode-b"])
def step15_generate_report(req: _Step15ReportReq):
    """Generate combined PDF covering Steps 1–15.

    If the frontend has included a 'selected_cap' block in step15_result,
    this endpoint calls verify_configuration + calculate_thermal_table
    internally so that Steps 15.4–15.10 are fully rendered in the report.
    Lifetime data (passed as 'lifetime' key) is forwarded unchanged.
    """
    try:
        _validate_state(req.state)
        from app.mode_b.generate_report import generate_full_report as gen_steps1_12
        from app.mode_b.generate_combined_report import generate_combined_report
        from fastapi.responses import Response

        # ── Enrich step15_result with verified + thermal ──────────────────────
        # The frontend passes the raw capacitor sizing dict plus the selected_cap
        # configuration block.  We reconstruct the nested 'verified' and 'thermal'
        # dicts that generate_step15_section requires for Steps 15.4–15.10.
        step15_result = dict(req.step15_result or {})
        sel_cap = step15_result.get("selected_cap") or {}

        if sel_cap and not step15_result.get("verified"):
            try:
                from app.mode_b.step15_capacitor import (
                    run_capacitor_design,
                    verify_configuration,
                    calculate_thermal_table,
                )
                base    = run_capacitor_design(req.state)
                supplier       = str(sel_cap.get("supplier", ""))
                series         = str(sel_cap.get("series",   ""))
                voltage_rating = int(sel_cap.get("voltage_rating_V", 450))
                value_uF       = int(sel_cap.get("value_uF", 470))
                qty            = int(sel_cap.get("qty",      1))
                part_number    = str(sel_cap.get("part_number", ""))

                config_list = [{"value_uF": value_uF, "qty": qty,
                                "part_number": part_number}]

                # Step 15.5–15.8: verification + ripple/hold-up performance
                ver = verify_configuration(
                    config         = config_list,
                    supplier       = supplier,
                    series         = series,
                    voltage_rating = voltage_rating,
                    worst          = base["worst_case"],
                    low            = base["low_line"],
                    Vout           = base["inputs"]["Vout_V"],
                    f_line         = base["inputs"]["f_line_Hz"],
                    Vdc_min        = base["inputs"]["Vdc_min_V"],
                    C_required_uF  = base["C_required_uF"],
                )

                # Enrich cap_specs[0] with rated lifetime + operating temperature
                # so the Selected Capacitor table in Step 15.5 shows them.
                if ver.get("cap_specs"):
                    ver["cap_specs"][0]["lifetime"] = str(sel_cap.get("lifetime",   "—"))
                    ver["cap_specs"][0]["op_temp"]  = str(sel_cap.get("op_temp",    "—"))
                    ver["cap_specs"][0]["ESR_each_mohm"] = (
                        sel_cap.get("ESR_each_mohm") or ver["cap_specs"][0].get("ESR_each_mohm"))
                    ver["cap_specs"][0]["I_rated_A"] = (
                        sel_cap.get("I_rated_A") or ver["cap_specs"][0].get("I_rated_A"))

                # Step 15.9: thermal table across all 9 operating points
                thermal = calculate_thermal_table(
                    config         = config_list,
                    state          = req.state,
                    supplier       = supplier,
                    series         = series,
                    voltage_rating = voltage_rating,
                )

                step15_result["verified"] = ver
                step15_result["thermal"]  = thermal

            except Exception as _e:
                log.warning("step15 verify/thermal rebuild failed: %s", _e)

        # ── Generate PDF ──────────────────────────────────────────────────────
        pdf_1_12    = gen_steps1_12(req.state)
        pdf_combined = generate_combined_report(
            state               = req.state,
            approved_design     = req.approved_design,
            steps1_12_pdf_bytes = pdf_1_12,
            step15_result       = step15_result,
            step16_params       = req.step16_params,
        )
        project_id  = req.state.get("project_id", "design")
        steps_label = "1_16" if req.step16_params else "1_15"
        filename    = f"PFC_Report_{project_id}_Steps{steps_label}.pdf"
        return Response(
            content      = pdf_combined,
            media_type   = "application/pdf",
            headers      = {"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as e:
        log.exception("step15_generate_report"); raise HTTPException(500, str(e))


# ── Full report (Steps 1–14) ──────────────────────────────────────────────────
class _FullReportReq(BaseModel):
    state:           Dict[str, Any]
    approved_design: Dict[str, Any]

@app.post("/mode-b/generate-full-report", tags=["mode-b"])
def generate_full_report_endpoint(req: _FullReportReq):
    """
    Generate combined PDF covering Steps 1–14.

    Flow:
      1. Generate Steps 1-12 PDF via generate_full_report (existing)
      2. Generate Steps 13-14 PDF via generate_steps13_14 (magnetics calculations
         with all equations, tables, and matplotlib charts)
      3. Merge both PDFs with pypdf and return combined binary

    Input:
      state           — confirmed Mode A state
      approved_design — serialised DesignResult from step7/run-sizing

    Returns: PDF binary (application/pdf)
    """
    try:
        _validate_state(req.state)
        from app.mode_b.generate_report import generate_full_report as gen_steps1_12
        from app.mode_b.generate_combined_report import generate_combined_report
        from fastapi.responses import Response

        # Step 1: generate Steps 1-12 PDF
        pdf_1_12 = gen_steps1_12(req.state)

        # Step 2 + 3: generate Steps 13-14 and merge
        pdf_combined = generate_combined_report(
            state=req.state,
            approved_design=req.approved_design,
            steps1_12_pdf_bytes=pdf_1_12,
        )

        project_id = req.state.get("project_id", "design")
        filename = f"PFC_Report_{project_id}_Steps1_14.pdf"
        return Response(
            content=pdf_combined,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as e:
        log.exception("full report generation")
        raise HTTPException(500, str(e))


# ══════════════════════════════════════════════════════════════════════════════
# DOCUMENTATION AGENT — Phase 3
# Typed DesignState access · validates completeness before generating
# POST /mode-b/documentation/report-status  → chapter readiness map
# POST /mode-b/documentation/generate-report → full PDF via agent
# ══════════════════════════════════════════════════════════════════════════════

class _DocStatusReq(BaseModel):
    state:           Dict[str, Any]
    approved_design: Optional[Dict[str, Any]] = None
    step15_result:   Optional[Dict[str, Any]] = None
    step16_params:   Optional[Dict[str, Any]] = None

class _DocReportReq(BaseModel):
    state:           Dict[str, Any]
    approved_design: Optional[Dict[str, Any]] = None
    step15_result:   Optional[Dict[str, Any]] = None
    step16_params:   Optional[Dict[str, Any]] = None
    semiconductor:   Optional[Dict[str, Any]] = None   # {design, mosfet, diode, bridge, thermal, tj_limit} → Chapter 7
    input_protection: Optional[Dict[str, Any]] = None  # {design, cap, mosfet, ntc_opts, mov_opts} → Chapters 8 (NTC) + 9 (MOV)


def _num(v):
    try:
        if v is None or v == "":
            return None
        f = float(v)
        return f if f == f else None  # reject NaN
    except (TypeError, ValueError):
        return None


def _control_inputs_from_step16(sp: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Map the ControlDesign step16_params (power stage) + its embedded
    js_design_state (designer-selected control specs) into the control-report
    calc-engine inputs. Missing values fall back to the engine defaults."""
    sp = sp or {}
    js = sp.get("js_design_state") or {}
    out: Dict[str, Any] = {}
    # power stage
    pairs = {
        "vout": sp.get("Vout_V"), "fsw": sp.get("fsw_Hz"), "lphi_uH": sp.get("L_uH"),
        "cout_uF": sp.get("C_uF"), "nch": sp.get("nch"), "pout_lo": sp.get("Pout_lo_W"),
        "pout_hi": sp.get("Pout_hi_W"), "eta_lo": sp.get("eta_lo"), "eta_hi": sp.get("eta_hi"),
    }
    for k, v in pairs.items():
        n = _num(v)
        if n is not None:
            out[k] = int(n) if k == "nch" else n
    if _num(sp.get("DCR_mOhm")) is not None: out["r_l"] = _num(sp["DCR_mOhm"]) / 1000.0
    if _num(sp.get("ESR_mOhm")) is not None: out["r_c"] = _num(sp["ESR_mOhm"]) / 1000.0
    # designer-selected control specs (exact designState keys)
    jsmap = {
        "fci": js.get("fci_Hz"), "fcv": js.get("fcv_Hz"), "f_z": js.get("cfz_Hz"),
        "f_p": js.get("cfp_Hz"), "fz1": js.get("vfz1_Hz"), "fz2": js.get("vfz2_Hz"),
        "fp1": js.get("vfp1_Hz"), "fp2": js.get("vfp2_Hz"), "gmv": js.get("gmv_S"),
        "r_m": js.get("rf"), "c_m": js.get("cf"), "rfb1_unit": js.get("r1fb"),
    }
    for k, v in jsmap.items():
        n = _num(v)
        if n is not None:
            out[k] = n
    if "rfb1_unit" in out:
        out["rfb1_count"] = 1
    if js.get("vType") in ("type2", "type3"):
        out["comp_type"] = js["vType"]
    # Screen-2 designer selections (R_CS + filter caps) — override engine defaults.
    s2 = sp.get("s2") or {}
    if _num(s2.get("rcs_mohm")) is not None:
        out["rcs"] = _num(s2["rcs_mohm"]) / 1000.0
    if _num(s2.get("c_gc_pf")) is not None:
        out["c_gc"] = _num(s2["c_gc_pf"]) * 1e-12
    if _num(s2.get("c_ls_pf")) is not None:
        out["c_ls"] = _num(s2["c_ls_pf"]) * 1e-12
    return out


def _merge_pdfs(parts: List[bytes]) -> bytes:
    """Concatenate several PDF byte-strings into one."""
    import io as _io
    from pypdf import PdfWriter, PdfReader
    w = PdfWriter()
    for b in parts:
        if not b:
            continue
        for pg in PdfReader(_io.BytesIO(b)).pages:
            w.add_page(pg)
    buf = _io.BytesIO()
    w.write(buf)
    return buf.getvalue()

# painting / image / path-drawing operators — a page with any of these is not blank
_PDF_PAINT = __import__("re").compile(rb'(?:^|[\s>])(?:S|s|f|F|f\*|B|B\*|b|b\*|Do|sh|re|m|l|c|v|y)(?:[\s/\[]|$)')

def _strip_blank_pages(pdf_bytes: bytes) -> bytes:
    """Drop pages that have no text, no images and no vector drawing (truly blank).
    Conservative: any uncertainty keeps the page."""
    import io as _io
    try:
        from pypdf import PdfReader, PdfWriter
        reader = PdfReader(_io.BytesIO(pdf_bytes))
    except Exception:
        return pdf_bytes
    w = PdfWriter()
    removed = 0
    for pg in reader.pages:
        blank = True
        try:
            if (pg.extract_text() or "").strip():
                blank = False
        except Exception:
            blank = False                      # extraction failed → keep
        if blank:
            try:
                if list(pg.images):
                    blank = False
            except Exception:
                blank = False
        if blank:
            try:
                c = pg.get_contents()
                raw = c.get_data() if c is not None else b""
            except Exception:
                raw = b"keep"                   # unknown content → keep
            if _PDF_PAINT.search(raw or b""):
                blank = False
        if blank:
            removed += 1
        else:
            w.add_page(pg)
    if removed == 0:
        return pdf_bytes
    out = _io.BytesIO(); w.write(out)
    return out.getvalue()

@app.post("/mode-b/documentation/report-status", tags=["documentation"])
def doc_report_status(req: _DocStatusReq):
    """
    Documentation Agent — chapter readiness check.
    Returns which chapters are ready to generate, which are pending,
    and exactly what is missing for each pending chapter.

    Call this when the designer wants to know their report coverage
    before downloading — e.g. after Mode A completes or after each
    step approval.
    """
    try:
        _validate_state(req.state)
        from app.mode_b.documentation_agent import DocumentationAgent
        agent = DocumentationAgent(req.state)
        status = agent.report_status(
            approved_design = req.approved_design,
            step15_result   = req.step15_result,
            step16_params   = req.step16_params,
        )
        return {"status": "ok", **status}
    except Exception as e:
        log.exception("doc_report_status"); raise HTTPException(500, str(e))

def _bias_L_curve(approved, L_final_uH, semi_design):
    """Per-operating-point inductance [[Vin_rms, L_uH], ...] for the powder-core bias roll-off.
    Prefers the inductor chapter's L_vs_Vin_table; otherwise builds a linear-in-bias model anchored
    so L = L_final at the highest-bias (low-line) point and recovers toward the no-load inductance
    L0 = A_L,nom·N² as the peak current falls at higher line. Returns None when no inductance data is
    available (the caller then keeps the single constant L, matching Chapter 3's own fallback)."""
    approved = approved or {}
    L0 = None
    try:
        if approved.get("AL_nom_total_nH") and approved.get("N"):
            L0 = float(approved["AL_nom_total_nH"]) * float(approved["N"]) ** 2 / 1e3
    except Exception:
        L0 = None
    # 1) explicit bias table from the magnetic design (authoritative)
    lvt = approved.get("L_vs_Vin_table") or []
    if lvt:
        out = []
        for r in lvt:
            v = r.get("Vin_rms"); luh = r.get("L_full_nom_uH")
            if luh is None and r.get("k_bias") is not None and L0:
                luh = L0 * float(r["k_bias"])
            if v is not None and luh is not None:
                out.append([float(v), float(luh)])
        return out or None
    # 2) linear-in-bias roll-off from the no-load inductance + per-point peak current
    if not (L0 and L_final_uH) or L0 <= float(L_final_uH):
        return None
    try:
        from app.mode_b.semiconductor.adapter import build_design_ops
        _, s2, *_ = build_design_ops({**semi_design, "L_phi_uH": float(L_final_uH)})
        ipk = [float(x) for x in s2["Iin_pk"]]; vac = [float(x) for x in s2["Vin_rms"]]
        ipk_max = max(ipk) or 1.0
        return [[vac[i], L0 - (L0 - float(L_final_uH)) * (ipk[i] / ipk_max)] for i in range(len(vac))]
    except Exception:
        return None


@app.post("/mode-b/documentation/generate-report", tags=["documentation"])
def doc_generate_report(req: _DocReportReq):
    """
    Documentation Agent — generate full PDF report.
    Routes through DocumentationAgent which:
      1. Validates DesignState completeness (clear error if missing fields)
      2. Determines which steps to include based on what has been approved
      3. Calls the existing generators as backends
      4. Returns the combined PDF

    Equivalent to calling the individual generate-report / generate-full-report
    endpoints, but with typed DesignState validation and a single entry point.
    """
    try:
        _validate_state(req.state)
        from app.mode_b.documentation_agent import DocumentationAgent
        from fastapi.responses import Response
        agent = DocumentationAgent(req.state)
        full = bool(req.step16_params and req.approved_design and req.step15_result)
        if full:
            # Single combined PDF: Chapters 1–5 from the documentation agent
            # (Ch6 omitted there) + the full detailed Chapter 6 control report.
            from app.mode_b.report_steps1_8 import build_control_report
            ch1_5 = agent.generate(
                approved_design = req.approved_design,
                step15_result   = req.step15_result,
                step16_params   = None,
                include_ch6     = False,   # Ch6 supplied by build_control_report below
            )
            ch6 = build_control_report(_control_inputs_from_step16(req.step16_params))
            parts = [ch1_5, ch6]
            # ONE inductance everywhere: Chapter 7 must use Chapter 3's finalized Lφ, never its own.
            # Resolve it exactly as the inductor chapter does (confirmed_L_uH_sel → confirmed_L_uH →
            # approved L_target_uH) and force it onto the semiconductor design before rendering.
            _tsi = (req.state or {}).get("topology_specific_inputs", {}) or {}
            _L_final = (_tsi.get("confirmed_L_uH_sel") or _tsi.get("confirmed_L_uH")
                        or (req.approved_design or {}).get("L_target_uH"))
            if req.semiconductor and _L_final:
                req.semiconductor.setdefault("design", {})["L_phi_uH"] = float(_L_final)
            if req.semiconductor:                          # per-operating-point bias inductance
                _curve = _bias_L_curve(req.approved_design, _L_final,
                                       req.semiconductor.get("design", {}))
                if _curve:
                    req.semiconductor["design"]["L_phi_curve"] = _curve
            if req.semiconductor:                          # Chapter 7 — Semiconductor Loss & Thermal
                from app.mode_b.report_semiconductor import build_semiconductor_report
                sc = req.semiconductor
                parts.append(build_semiconductor_report(
                    sc["design"], sc["mosfet"], sc["diode"], sc["bridge"], sc["thermal"],
                    sc.get("tj_limit")))
            if req.input_protection:                        # Chapters 8 (NTC) + 9 (MOV compliance)
                from app.mode_b.report_inputprotection import build_inputprotection_report
                ip = req.input_protection
                parts.append(build_inputprotection_report(
                    ip["design"], ip.get("cap"), ip.get("mosfet"),
                    ip.get("ntc_opts"), ip.get("mov_opts")))
            pdf = _merge_pdfs(parts)
        else:
            pdf = agent.generate(
                approved_design = req.approved_design,
                step15_result   = req.step15_result,
                step16_params   = req.step16_params,
            )
        pdf = _strip_blank_pages(pdf)
        project_id = req.state.get("project_id", "design")
        if req.step16_params and req.approved_design and req.step15_result and req.semiconductor and req.input_protection:
            label = "Steps1_19"
        elif req.step16_params and req.approved_design and req.step15_result and req.semiconductor:
            label = "Steps1_17"
        elif req.step16_params and req.approved_design and req.step15_result:
            label = "Steps1_16"
        elif req.step15_result and req.approved_design:
            label = "Steps1_15"
        elif req.approved_design:
            label = "Steps1_14"
        else:
            label = "Steps1_12"
        filename = f"PFC_Report_{project_id}_{label}.pdf"
        return Response(
            content    = pdf,
            media_type = "application/pdf",
            headers    = {"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except ValueError as e:
        raise HTTPException(422, str(e))
    except Exception as e:
        log.exception("doc_generate_report"); raise HTTPException(500, str(e))
