"""Design state export — one neutral view of the approved design, for consumers outside the report.

PHASE 0 of the PFC Design Explorer (see `specs/Improvements/ANIMATION_PLAN.md`). The animation page
is the first consumer; Ansys magnetics and SIMetrix/SIMPLIS exports are planned to sit on the same
export rather than each growing their own aggregation. Writing an animation-shaped payload first
would mean building the aggregation twice.

THIS MODULE IS PURELY ADDITIVE. It imports nothing from the report builders, is imported by nothing
that already worked, and mutates none of its inputs. Removing it would leave the rest of the system
byte-identical.

THREE RULES, and they exist because breaking them is how the defects of the last week happened.

1. NO RECOMPUTATION. Every value is projected from an object the design already approved. This
   module performs no physics, calls no engine, and derives no quantity that an engine owns. The
   standalone Chapter 7 printed a flat inductance for months (C255) because two paths fed the same
   builder different inputs; an export that recomputed anything would be a third path.

2. NO SILENT DEFAULTS. A missing input yields `approved: false` and an absent section — never a
   nominal standing in for a measurement. Table 7.1's caption claimed a Chapter-3 basis while
   running on a flat nominal (C255), and that is exactly how a wrong number reads as a right one.

3. VALUES KEEP THEIR SOURCE NAMES AND UNITS. `L_full_nom_uH` stays microhenries and keeps its name.
   Renaming 109 inductor fields into a new vocabulary would introduce a transcription bug per field
   with nothing to catch it. Neutrality here is STRUCTURAL — chapter-scoped sections, explicit
   readiness, provenance — not a second naming scheme. A canonical mapping layer for the Ansys and
   SIMPLIS exporters can sit on top of this later, where the target tool defines the vocabulary.

INPUT IS THE SAME SHAPE THE REPORT TAKES (`_DocReportReq`), deliberately: the GUI already assembles
that payload on the Input Filter page, and it lets the export be tested for agreement against the
report from one fixture.
"""
from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional

SCHEMA_VERSION = "1.0"

# Chapter → the request field that carries it. Ch1-2 come from `state`; Ch8 and Ch9 share one
# object; Ch10 is the EMI filter, which is the page immediately before the animation.
CHAPTER_SOURCES = {
    "specification":  "state",             # Ch1-2
    "magnetics":      "approved_design",   # Ch3-4
    "capacitor":      "step15_result",     # Ch5
    "control":        "step16_params",     # Ch6
    "semiconductors": "semiconductor",     # Ch7
    "protection":     "input_protection",  # Ch8 (NTC) + Ch9 (MOV/GDT)
    "emi":            "input_filter",      # Ch10
}


def _g(d: Optional[dict], *keys, default=None):
    """First key that is present and not blank. Never raises on a missing dict."""
    if not isinstance(d, dict):
        return default
    for k in keys:
        v = d.get(k)
        if v not in (None, "", []):
            return v
    return default


def _num(v, default=None):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _present(obj) -> bool:
    """An input counts as supplied only if it carries something. `{}` is not an approval."""
    return bool(obj) if not isinstance(obj, dict) else bool(obj)


# ── sections ────────────────────────────────────────────────────────────────────────────────
def _meta(state: dict) -> dict:
    return {
        "project_id":      _g(state, "project_id"),
        "topology":        _g(state, "selected_topology"),
        "mode":            _g(state, "selected_mode"),
        "channels":        _g(state, "selected_channels", default=1),
        "controller_mode": _g(state, "selected_controller_mode"),
    }


def _spec(state: dict) -> dict:
    intake = _g(state, "intake", default={}) or {}
    app_ = intake.get("application") or {}
    th = intake.get("thermal") or {}
    tsi = _g(state, "topology_specific_inputs", default={}) or {}
    return {
        "vin_rms_min_V":        _num(app_.get("vin_rms_min")),
        "vin_rms_max_V":        _num(app_.get("vin_rms_max")),
        "vout_V":               _num(app_.get("output_bus_voltage_v")),
        "pout_low_line_W":      _num(app_.get("output_power_w_low_line")),
        "pout_high_line_W":     _num(app_.get("output_power_w_high_line")),
        "fline_Hz":             _num(app_.get("nominal_line_frequency_hz")),
        "fsw_Hz":               _num(tsi.get("recommended_frequency_hz")),
        "nch":                  _g(state, "selected_channels", default=1),
        "bus_ripple_pp_V":      _num(app_.get("dc_bus_voltage_ripple_pk_pk_v")),
        "hold_up_ms":           _num(app_.get("hold_up_time_ms")),
        "pf_target":            _num(app_.get("power_factor_target")),
        # ONE ambient, the value typed on the first page — the single source every chapter uses.
        "ambient_temp_c_max":   _num(th.get("ambient_temp_c_max")),
        "hotspot_limit_c":      _num(th.get("hotspot_limit_c")),
        "cooling_type":         th.get("cooling_type"),
    }


def _points(approved_design: Optional[dict]) -> List[dict]:
    """Per-operating-point rows, merged on Vin_rms.

    `L_vs_Vin_table` carries the as-built per-point inductance and the ripple that follows it;
    `loss_table_100C` carries the losses and flux at the same nine points. Merging on Vin_rms is
    safe because both tables are produced by the same sizing run over the same sweep.

    The per-point INDUCTANCE is the reason this section exists at all: it is what the standalone
    Chapter 7 was missing (C255), so any consumer reading points[] gets the bias curve, not a flat
    nominal, without having to know the difference.
    """
    if not isinstance(approved_design, dict):
        return []
    lvt = approved_design.get("L_vs_Vin_table") or []
    loss = {round(_num(r.get("Vin_rms"), -1)): r for r in (approved_design.get("loss_table_100C") or [])}
    out: List[dict] = []
    for r in lvt:
        vac = _num(r.get("Vin_rms"))
        if vac is None:
            continue
        lr = loss.get(round(vac), {})
        out.append({
            "vac_V":          vac,
            "vin_pk_V":       _num(lr.get("Vin_pk")),
            "L_full_nom_uH":  _num(r.get("L_full_nom_uH")),
            "L_full_min_uH":  _num(r.get("L_full_min_uH")),
            "L_req_uH":       _num(r.get("L_req_uH")),
            "k_bias":         _num(r.get("k_bias")),
            "meets_req":      r.get("meets_req"),
            "dIL_pp_A":       _num(r.get("dIL_pp_A")),
            "dIin_pp_A":      _num(r.get("dIin_pp_A")),
            "ripple_pct":     _num(r.get("r_act_pct")),
            "Ipk_line_A":     _num(r.get("Ipk_line")),
            "Iavg_crest_A":   _num(r.get("Iavg_crest")),
            "AT":             _num(r.get("AT")),
            "H_Oe":           _num(r.get("H_Oe")),
            # C280: the same bias curve at the LINE CREST. `L_full_nom_uH` above is at HALF the
            # line-peak current, which is the cycle-average basis every chapter uses; this is at
            # the full peak. Both are needed to see how far the inductance moves INSIDE one line
            # cycle - on the reference design it falls 46-60 % between them, so a scene drawn from
            # the cycle-average value alone shows a flat inductor that does not exist.
            "L_crest_nom_uH": _num(r.get("L_crest_nom_uH")),
            "H_Oe_crest":     _num(r.get("H_Oe_crest")),
            "k_bias_crest":   _num(r.get("k_bias_crest")),
            "D_crest":        _num(lr.get("D_crest")),
            "Bac_pk_T":       _num(lr.get("Bac_pk")),
            "Irms_A":         _num(lr.get("Irms")),
            "Ihf_rms_A":      _num(lr.get("Ihf_rms")),
            "Pcore_avg_W":    _num(lr.get("Pcore_avg_W")),
            "Pcu_avg_W":      _num(lr.get("Pcu_avg_W")),
            "Ptotal_avg_W":   _num(lr.get("Ptotal_avg_W")),
        })
    out.sort(key=lambda p: p["vac_V"])
    return out


def _magnetics(ad: Optional[dict]) -> Optional[dict]:
    if not _present(ad):
        return None
    return {
        "core": {
            "name":        _g(ad, "core_name"),
            "type":        _g(ad, "core_type"),
            "part_number": _g(ad, "part_number"),
            "material":    _g(ad, "material_key"),
            "OD_mm":       _num(ad.get("OD_mm")),
            "ID_mm":       _num(ad.get("ID_mm")),
            "HT_mm":       _num(ad.get("HT_mm")),
            "Ae_total_mm2": _num(ad.get("Ae_total_mm2")),
        },
        "winding": {
            "turns":            _num(ad.get("N")),
            "AL_nom_nH":        _num(ad.get("AL_nom_nH")),
            "AL_tol_pct":       _num(ad.get("AL_tol_pct")),
            "DCR_25C_mOhm":     _num(ad.get("DCR_25C_mOhm")),
            "DCR_100C_mOhm":    _num(ad.get("DCR_100C_mOhm")),
            "FFcu":             _num(ad.get("FFcu")),
            "Cu_length_m":      _num(ad.get("Cu_length_m")),
        },
        "flux": {
            # Both saturation bases are carried deliberately. PENDING D3 is still open: the report
            # quotes inner-bore margin while the engine's accept/reject gate runs on mean-path, and
            # a consumer that showed only one would be picking a side of an undecided question.
            "Bsat_at_Tcore_T":     _num(ad.get("Bsat_at_Tcore")),
            "Bmax_FL_T":           _num(ad.get("Bmax_FL_T")),
            "Bmax_inner_FL_T":     _num(ad.get("Bmax_inner_FL_T")),
            "Bdc_T":               _num(ad.get("Bdc_T")),
            "Bac_pk_T":            _num(ad.get("Bac_pk_T")),
            "sat_margin_pct":      _num(ad.get("sat_margin_pct")),
            "sat_margin_inner_pct": _num(ad.get("sat_margin_inner_pct")),
            "H_Oe_design":         _num(ad.get("H_Oe_design")),
            "H_Oe_worst":          _num(ad.get("H_Oe_worst")),
        },
        "thermal": {
            "T_core_C":             _num(ad.get("T_core_C")),
            "dT_rise_C":            _num(ad.get("dT_rise_C")),
            "installed_height_mm":  _num(ad.get("installed_height_mm")),
            "mounting":             _g(ad, "mounting"),
        },
    }


def _capacitor(s15: Optional[dict]) -> Optional[dict]:
    if not _present(s15):
        return None
    sel = s15.get("selected_cap") or {}
    return {
        "C_required_uF":      _num(s15.get("C_required_uF")),
        "V_rating_min_V":     _num(s15.get("V_rating_min_V")),
        "V_rating_selected_V": _num(s15.get("V_rating_selected_V")),
        "governing":          _g(s15, "governing"),
        # selected_cap is the block the report gates Chapter 5's later sections on; its absence is
        # what silently dropped ~7 pages before verify_combined_report started attaching one.
        "selected": {
            "part_number":  _g(sel, "part_number"),
            "supplier":     _g(sel, "supplier"),
            "series":       _g(sel, "series"),
            "value_uF":     _num(sel.get("value_uF")),
            "qty":          _num(sel.get("qty")),
            "voltage_rating_V": _num(sel.get("voltage_rating_V")),
            "temp_rating_C":    _num(sel.get("temp_rating_C")),
        } if sel else None,
        "worst_case": copy.deepcopy(s15.get("worst_case")) if s15.get("worst_case") else None,
    }


def _control(s16: Optional[dict]) -> Optional[dict]:
    if not _present(s16):
        return None
    return {
        "L_uH":       _num(s16.get("L_uH")),
        "DCR_mOhm":   _num(s16.get("DCR_mOhm")),
        "C_uF":       _num(s16.get("C_uF")),
        "ESR_mOhm":   _num(s16.get("ESR_mOhm")),
        "Vout_V":     _num(s16.get("Vout_V")),
        "fsw_Hz":     _num(s16.get("fsw_Hz")),
        "nch":        _num(s16.get("nch")),
        "fci_Hz":     _num(s16.get("fci_Hz")),
        "fcv_Hz":     _num(s16.get("fcv_Hz")),
        "Pout_lo_W":  _num(s16.get("Pout_lo_W")),
        "Pout_hi_W":  _num(s16.get("Pout_hi_W")),
        "eta_lo":     _num(s16.get("eta_lo")),
        "eta_hi":     _num(s16.get("eta_hi")),
    }


def _semiconductors(sc: Optional[dict]) -> Optional[dict]:
    """Part identity and thermal frame only.

    The per-point loss sweep is NOT here: it is an engine result, and running the engine would make
    this a computing path rather than a projection (rule 1). Consumers that need the sweep call
    `/mode-b/semiconductor/calculate`, which is the one place it is produced.
    """
    if not _present(sc):
        return None

    def part(block, *fields):
        b = sc.get(block) or {}
        out = {f: b.get(f) for f in fields if b.get(f) not in (None, "")}
        out["is_datasheet_sourced"] = bool(b.get("irev_curve") or b.get("vf_curve_hot")
                                           or b.get("eon_curve") or b.get("_provenance"))
        return out or None

    return {
        "mosfet": part("mosfet", "part_number", "manufacturer", "technology", "vdss", "rdson_25"),
        "diode":  part("diode", "part_number", "manufacturer", "is_sic", "qc", "vrrm"),
        "bridge": part("bridge", "part_number", "manufacturer", "topology", "n_parallel"),
        "thermal": copy.deepcopy(sc.get("thermal")) if sc.get("thermal") else None,
        "tj_limit": copy.deepcopy(sc.get("tj_limit")) if sc.get("tj_limit") else None,
    }


def _echo(obj: Optional[dict], *keys) -> Optional[dict]:
    """Carry a chapter's own object through unchanged. Used where the downstream shape is still
    settling (protection, EMI) — a projection invented now would have to be rewritten once the
    animation scenes for those chapters are designed."""
    if not _present(obj):
        return None
    return {k: copy.deepcopy(obj[k]) for k in keys if k in obj} or copy.deepcopy(obj)


# ── readiness ───────────────────────────────────────────────────────────────────────────────
def _readiness(supplied: Dict[str, Any]) -> dict:
    """Which chapters are approved, and whether the animation page may open at all.

    C-12: the page is gated until every prior chapter is complete, Ch8-Ch10 included. This reports
    the facts; the caller decides. A consumer must never infer readiness from a section being
    absent — absence and 'designed, but empty' look identical downstream, which is the mistake that
    made a missing `selected_cap` silently drop seven pages of Chapter 5.
    """
    chapters = {}
    for name, field in CHAPTER_SOURCES.items():
        chapters[name] = {"source": field, "approved": _present(supplied.get(field))}
    missing = sorted(n for n, c in chapters.items() if not c["approved"])
    return {
        "chapters": chapters,
        "missing": missing,
        "complete": not missing,
        "gate": "open" if not missing else "blocked",
    }


# ── entry point ─────────────────────────────────────────────────────────────────────────────
def build_design_state(state: Optional[dict] = None,
                       approved_design: Optional[dict] = None,
                       step15_result: Optional[dict] = None,
                       step16_params: Optional[dict] = None,
                       semiconductor: Optional[dict] = None,
                       input_protection: Optional[dict] = None,
                       input_filter: Optional[dict] = None) -> dict:
    """Project the approved design into one neutral, chapter-scoped structure.

    Read-only in the strongest sense: inputs are never mutated, and nothing here computes.
    """
    state = state or {}
    supplied = {
        "state": state, "approved_design": approved_design, "step15_result": step15_result,
        "step16_params": step16_params, "semiconductor": semiconductor,
        "input_protection": input_protection, "input_filter": input_filter,
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "meta": _meta(state),
        "spec": _spec(state),
        "readiness": _readiness(supplied),
        "points": _points(approved_design),
        "chapters": {
            "magnetics":      _magnetics(approved_design),
            "capacitor":      _capacitor(step15_result),
            "control":        _control(step16_params),
            "semiconductors": _semiconductors(semiconductor),
            "protection":     _echo(input_protection, "design", "ntc", "mov", "fuse", "gdt"),
            "emi":            _echo(input_filter, "design", "opts", "protection"),
        },
    }
