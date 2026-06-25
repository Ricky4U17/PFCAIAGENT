"""
Component intake / confirmation layer for the PFC loss model
============================================================
Supports the workflow:
    1. designer uploads a datasheet
    2. agent extracts the parameters it can find
    3. agent shows a CONFIRMATION TABLE - every expected field with its value,
       or "NOT AVAILABLE" if the agent could not find it
    4. designer confirms / fills the gaps
    5. validate_design() guards the run so the engine NEVER silently falls back
       to a built-in default for a required parameter

This module holds NO loss physics. It only knows which parameters each component
needs, where they come from (datasheet vs designer/application), and whether they
are required. Field names match the dataclasses in pfc_loss_model_step3_local.py.

Sources:
    datasheet   -> agent should extract from the uploaded datasheet
    application -> NOT on the datasheet; designer/board context must supply
    choice      -> a modelling/design selection
Levels:
    required           -> must be present or the run is blocked
    if_analytic/if_esw -> required depending on mosfet sw_method
    if_sic/if_si       -> required depending on diode type
    if_sync_bottom     -> required only for a synchronous-bottom bridge
    recommended        -> strongly advised (e.g. tempco, margins); warns if absent
    optional           -> safe to leave to the model default
"""
from __future__ import annotations
from collections import namedtuple

try:
    import pandas as pd
except Exception:               # pandas optional; fall back to list-of-dicts
    pd = None

Param = namedtuple("Param", "name source group level units note")

# --------------------------------------------------------------------------- #
#  Parameter manifests (datasheet extraction targets)                         #
# --------------------------------------------------------------------------- #
MOSFET = [
    Param("tech",        "choice",      "identity",   "required", "si|sic",     "Silicon super-junction or SiC"),
    Param("rdson_25",    "datasheet",   "conduction", "required", "ohm",        "R_DS(on) typ @25C at the actual gate-drive Vgs"),
    Param("rdson_tj",    "datasheet",   "conduction", "required", "(T[],mult[])","R_DS(on) normalized vs Tj, >=2 pts e.g. [[25,125],[1.0,1.6]]"),
    Param("ciss",        "datasheet",   "switching",  "if_analytic","F",        "Input capacitance C_iss"),
    Param("qgd",         "datasheet",   "switching",  "if_analytic","C",        "Gate-drain charge Q_gd (or provide crss_curve)"),
    Param("vth",         "datasheet",   "switching",  "if_analytic","V",        "Gate threshold V_GS(th)"),
    Param("vpl",         "datasheet",   "switching",  "if_analytic","V",        "Miller plateau voltage"),
    Param("eon_curve",   "datasheet",   "switching",  "if_esw",   "(I[],J[])",  "E_on vs current (only if sw_method='esw')"),
    Param("eoff_curve",  "datasheet",   "switching",  "if_esw",   "(I[],J[])",  "E_off vs current (only if sw_method='esw')"),
    Param("qg",          "datasheet",   "gate",       "required", "C",          "Total gate charge Q_g at the drive voltage"),
    Param("eoss_at_v",   "datasheet",   "switching",  "required", "(V[],J[])",  "E_oss (Coss stored energy) vs Vds, >=2 pts"),
    Param("rth_jc",      "datasheet",   "thermal",    "required", "C/W",        "Junction-to-case R_th(j-c)"),
    Param("vg",          "application", "gate",       "required", "V",          "Gate-drive turn-on voltage"),
    Param("rg",          "application", "switching",  "required", "ohm",        "Total series gate resistance (or rg_on/rg_off)"),
    Param("rth_cs",      "application", "thermal",    "required", "C/W",        "Case-to-sink R_th (thermal interface material)"),
    Param("sw_method",   "choice",      "switching",  "optional", "analytic|esw","Switching-loss method (default 'analytic')"),
    Param("crss_curve",  "datasheet",   "switching",  "recommended","(V[],C[])","Crss vs Vds - better than a single Q_gd"),
    Param("vsd",         "datasheet",   "body-diode", "recommended","V",        "Body-diode forward drop (if body diode conducts)"),
    Param("qrr_body",    "datasheet",   "body-diode", "optional", "C",          "Body-diode reverse-recovery charge"),
    Param("zth_foster",  "datasheet",   "thermal",    "recommended","(R[],tau[])","Foster Z_th network for transient Tj"),
    Param("k_rdson",     "application", "margin",     "recommended","x",        "Worst-case R_DS(on) multiplier for signoff"),
    Param("k_esw",       "application", "margin",     "optional", "x",          "Worst-case switching-energy multiplier"),
]

DIODE = [
    Param("is_sic",        "choice",      "identity",  "required", "bool",       "SiC Schottky (True) or Si PN/fast (False)"),
    Param("vf_curve",      "datasheet",   "conduction","required", "(I[],V[])",  "Forward drop Vf vs If, >=2 pts"),
    Param("qc",            "datasheet",   "switching", "if_sic",   "C",          "Capacitive charge Q_c (SiC; no real Qrr)"),
    Param("qrr",           "datasheet",   "switching", "if_si",    "C",          "Reverse-recovery charge Q_rr (Si)"),
    Param("rth_jc",        "datasheet",   "thermal",   "required", "C/W",        "Junction-to-case R_th(j-c)"),
    Param("rth_cs",        "application", "thermal",   "required", "C/W",        "Case-to-sink R_th (thermal interface material)"),
    Param("vf_tco",        "datasheet",   "conduction","recommended","V/C",      "Vf temperature coefficient"),
    Param("qrr_if_curve",  "datasheet",   "switching", "optional", "(I[],C[])",  "Qrr vs If (Si, refines recovery)"),
    Param("qrr_didt_curve","datasheet",   "switching", "optional", "(A/us[],C[])","Qrr vs di/dt (Si)"),
    Param("e_fr",          "datasheet",   "switching", "optional", "J",          "Forward-recovery energy"),
    Param("zth_foster",    "datasheet",   "thermal",   "recommended","(R[],tau[])","Foster Z_th network for transient Tj"),
    Param("k_vf",          "application", "margin",    "recommended","x",        "Worst-case Vf multiplier for signoff"),
]

BRIDGE = [
    Param("topology",         "choice",     "identity",  "required",      "diode|sync_bottom","Plain diode bridge or synchronous-bottom"),
    Param("vf_curve",         "datasheet",  "conduction","required",      "(I[],V[])","Single bridge-diode Vf vs If, >=2 pts"),
    Param("n_parallel",       "application","conduction","required",      "int",      "Bridge devices in parallel"),
    Param("rth_jc",           "datasheet",  "thermal",   "required",      "C/W",      "Junction-to-case R_th(j-c) per device"),
    Param("rth_cs",           "application","thermal",   "required",      "C/W",      "Case-to-sink R_th"),
    Param("vf_tco",           "datasheet",  "conduction","recommended",   "V/C",      "Vf temperature coefficient"),
    Param("rdson_bottom_25",  "datasheet",  "conduction","if_sync_bottom","ohm",      "Bottom-FET R_DS(on) @25C (sync bridge)"),
    Param("rdson_bottom_tj",  "datasheet",  "conduction","if_sync_bottom","(T[],mult[])","Bottom-FET R_DS(on) vs Tj (sync bridge)"),
    Param("qg_bottom",        "datasheet",  "gate",      "if_sync_bottom","C",        "Bottom-FET gate charge (sync bridge)"),
    Param("n_parallel_bottom","application","conduction","if_sync_bottom","int",      "Bottom FETs in parallel (sync bridge)"),
    Param("k_vf",             "application","margin",    "recommended",   "x",        "Worst-case Vf multiplier for signoff"),
]

SYSTEM = [   # the 'spec' + 'thermal' blocks - design/operating context, not a datasheet
    Param("vo",         "application","operating","required","V",      "Boost output (bus) voltage"),
    Param("fsw",        "application","operating","required","Hz",     "Switching frequency"),
    Param("fline",      "application","operating","required","Hz",     "AC line frequency"),
    Param("nch",        "application","operating","required","int",    "Interleaved channel count (1, 2 or 3)"),
    Param("L",          "application","operating","required","H",      "PER-CHANNEL boost inductance (or supply ripple instead)"),
    Param("eta",        "provided",   "operating","required","frac",   "Efficiency (supplied by upstream tool)"),
    Param("pf",         "provided",   "operating","required","frac",   "Power factor (supplied by upstream tool)"),
    Param("po|pin|iin_rms","provided","operating","required","W|W|A",  "One of: output power, input power, or input RMS current"),
    Param("pct_ripple|di_pp_peak","application","operating","optional","frac|A","Ripple spec; overrides L if given"),
    Param("t_ambient|t_sink_fixed","application","thermal","required","C","Ambient temp, or a regulated sink temperature"),
    Param("rth_sa",     "application","thermal",  "recommended","C/W","Sink-to-ambient R_th (needed if t_sink_fixed not given)"),
]

MANIFEST = {"mosfet": MOSFET, "diode": DIODE, "bridge": BRIDGE, "system": SYSTEM}

_CONTEXT_TAGS = {"if_analytic", "if_esw", "if_sic", "if_si", "if_sync_bottom"}

# A required parameter is also satisfied by an equivalent alternative set the engine accepts.
_ALIASES = {
    "mosfet": {"rg": [["rg"], ["rg_on", "rg_off"]],
               "vg": [["vg"], ["vg_drive"]]},
    "diode":  {},
    "bridge": {},
    "system": {"eta": [["eta"], ["eta_curve"]],
               "pf":  [["pf"], ["pf_curve"]]},
}


# --------------------------------------------------------------------------- #
#  Helpers                                                                     #
# --------------------------------------------------------------------------- #
def _present(d, name):
    """True if a parameter (or any of its 'a|b|c' alternatives) is supplied & non-empty."""
    for key in name.split("|"):
        v = d.get(key, None)
        if v is not None and v != "" and v != []:
            return True
    return False


def _fmt_value(v):
    """Readable display string (avoids pandas rounding small floats to 0.0 in object columns)."""
    if v is None:
        return ""
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, float):
        return f"{v:.4g}"
    if isinstance(v, (list, tuple)):
        return str(v)
    return str(v)


def _satisfied(d, name, kind):
    """True if `name` is present directly, via a 'a|b' alternative, or via an engine-accepted alias set."""
    if _present(d, name):
        return True
    for altset in _ALIASES.get(kind, {}).get(name, []):
        if all(_present(d, a) for a in altset):
            return True
    return False


def _effective_value(d, name, kind):
    for key in name.split("|"):
        if d.get(key) not in (None, "", []):
            return d[key]
    for altset in _ALIASES.get(kind, {}).get(name, []):
        if all(_present(d, a) for a in altset):
            return "(via " + "+".join(altset) + ")"
    return None


def _effective_required(p, ctx):
    """Resolve a conditional level to a concrete required/recommended/optional/n_a."""
    if p.level == "if_analytic":  return "required" if ctx.get("sw_method", "analytic") == "analytic" else "n/a"
    if p.level == "if_esw":       return "required" if ctx.get("sw_method", "analytic") == "esw" else "n/a"
    if p.level == "if_sic":       return "required" if ctx.get("is_sic", True) else "n/a"
    if p.level == "if_si":        return "required" if not ctx.get("is_sic", True) else "n/a"
    if p.level == "if_sync_bottom":return "required" if ctx.get("topology", "diode") == "sync_bottom" else "n/a"
    return p.level


def _context_for(kind, extracted):
    if kind == "mosfet": return {"sw_method": extracted.get("sw_method", "analytic")}
    if kind == "diode":  return {"is_sic": extracted.get("is_sic", True)}
    if kind == "bridge": return {"topology": extracted.get("topology", "diode")}
    return {}


def confirmation_table(extracted, kind, as_dataframe=True):
    """Build the table the agent shows the designer for one component.

    extracted : dict of whatever the agent pulled from the datasheet
    kind      : 'mosfet' | 'diode' | 'bridge' | 'system'
    Returns a DataFrame (or list of dicts) with a STATUS per parameter; required
    parameters the agent could not find are flagged 'NOT AVAILABLE'.
    """
    if kind not in MANIFEST:
        raise ValueError(f"unknown component kind '{kind}' (use {list(MANIFEST)})")
    ctx = _context_for(kind, extracted)
    rows = []
    for p in MANIFEST[kind]:
        req = _effective_required(p, ctx)
        if req == "n/a":
            continue
        present = _satisfied(extracted, p.name, kind)
        value = _effective_value(extracted, p.name, kind)
        if present:
            status = "provided"
        elif req == "required":
            status = "NOT AVAILABLE"
        elif req == "recommended":
            status = "missing (recommended)"
        else:
            status = "optional (model default)"
        rows.append({"parameter": p.name, "status": status, "value": _fmt_value(value),
                     "source": p.source, "group": p.group, "units": p.units, "note": p.note})
    if as_dataframe and pd is not None:
        return pd.DataFrame(rows, columns=["parameter", "status", "value", "source", "group", "units", "note"])
    return rows


def missing_required(extracted, kind):
    """List of required parameter names the agent could not supply for this component."""
    ctx = _context_for(kind, extracted)
    out = []
    for p in MANIFEST[kind]:
        if _effective_required(p, ctx) == "required" and not _satisfied(extracted, p.name, kind):
            out.append(p.name)
    return out


def validate_design(cfg, strict=True):
    """Guard before calculation. Checks the assembled cfg dict (mosfet/diode/bridge/
    spec/thermal) for every required parameter, resolving conditional requirements.

    Returns (ok: bool, issues: DataFrame|list). When ok is False the design must NOT
    be run - a required value would otherwise be silently taken from a default.
    """
    issues = []
    comp_keys = {"mosfet": cfg.get("mosfet", {}), "diode": cfg.get("diode", {}),
                 "bridge": cfg.get("bridge", {})}
    for kind, d in comp_keys.items():
        for name in missing_required(d, kind):
            issues.append({"component": kind, "parameter": name, "issue": "NOT AVAILABLE (required)"})

    # system block lives in cfg['spec'] (+ cfg['thermal'])
    spec = cfg.get("spec", {}); thermal = cfg.get("thermal", {})
    for name in ("vo", "fsw", "fline", "nch"):
        if not _present(spec, name):
            issues.append({"component": "system", "parameter": name, "issue": "NOT AVAILABLE (required)"})
    for name in ("eta", "pf"):
        if not _satisfied(spec, name, "system"):
            issues.append({"component": "system", "parameter": name, "issue": "NOT AVAILABLE (required)"})
    if not (_present(spec, "po") or _present(spec, "pin") or _present(spec, "iin_rms")
            or _present(spec, "po_curve") or _present(spec, "pin_curve") or _present(spec, "iin_rms_curve")):
        issues.append({"component": "system", "parameter": "po|pin|iin_rms", "issue": "NOT AVAILABLE (need one)"})
    if not (_present(spec, "L") or _present(spec, "pct_ripple") or _present(spec, "di_pp_peak")
            or _present(spec, "di_pp_peak_curve")):
        issues.append({"component": "system", "parameter": "L|pct_ripple|di_pp_peak",
                       "issue": "NOT AVAILABLE (need inductance or a ripple spec)"})
    if not (_present(thermal, "t_sink_fixed") or (_present(thermal, "t_ambient") and _present(thermal, "rth_sa"))):
        issues.append({"component": "system", "parameter": "t_ambient+rth_sa | t_sink_fixed",
                       "issue": "NOT AVAILABLE (need a thermal boundary condition)"})
    nch = spec.get("nch")
    if nch is not None and nch not in (1, 2, 3):
        issues.append({"component": "system", "parameter": "nch",
                       "issue": f"unsupported channel count {nch} (use 1, 2 or 3)"})

    ok = len(issues) == 0
    if pd is not None:
        issues = pd.DataFrame(issues, columns=["component", "parameter", "issue"])
    if strict and not ok:
        pass   # caller decides; we just report
    return ok, issues


if __name__ == "__main__":
    # demo: an agent that found most of a SiC MOSFET datasheet but missed Q_g and R_th(j-c)
    extracted = dict(tech="sic", rdson_25=0.040, rdson_tj=[[25, 125], [1.0, 1.4]],
                     ciss=1100e-12, qgd=22e-9, vth=4.5, vpl=9.0,
                     eoss_at_v=[[100, 400], [2e-6, 9e-6]])   # missing qg, rth_jc, vg, rg, rth_cs
    tbl = confirmation_table(extracted, "mosfet")
    print("CONFIRMATION TABLE (mosfet):")
    print(tbl.to_string(index=False) if pd is not None else tbl)
    print("\nmissing required:", missing_required(extracted, "mosfet"))
