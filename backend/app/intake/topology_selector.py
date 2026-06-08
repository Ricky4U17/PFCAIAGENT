from __future__ import annotations
from typing import Dict, Any, List
from app.intake.schema import FullIntake

MODE_MATRIX = {
    "ccm": {"high_power_fit": 5, "emi_predictability": 5, "thermal_current_stress": 4, "fixed_frequency_fit": 5, "implementation_risk": 4, "power_density_fit": 4},
    "crcm": {"high_power_fit": 3, "emi_predictability": 2, "thermal_current_stress": 3, "fixed_frequency_fit": 1, "implementation_risk": 3, "power_density_fit": 3},
    "dcm": {"high_power_fit": 1, "emi_predictability": 2, "thermal_current_stress": 1, "fixed_frequency_fit": 3, "implementation_risk": 4, "power_density_fit": 2},
}
TOPOLOGY_MATRIX = {
    "single_boost": {"efficiency_fit": 3, "thermal_fit": 3, "mechanical_fit": 3, "control_fit": 5, "cost_fit": 5, "supply_fit": 5, "implementation_fit": 5},
    "interleaved_boost": {"efficiency_fit": 4, "thermal_fit": 5, "mechanical_fit": 4, "control_fit": 4, "cost_fit": 3, "supply_fit": 4, "implementation_fit": 4},
    "ttp": {"efficiency_fit": 5, "thermal_fit": 4, "mechanical_fit": 5, "control_fit": 2, "cost_fit": 2, "supply_fit": 3, "implementation_fit": 2},
    "ttp_interleaved": {"efficiency_fit": 5, "thermal_fit": 5, "mechanical_fit": 5, "control_fit": 1, "cost_fit": 1, "supply_fit": 2, "implementation_fit": 1},
}
VALID_COMBINATIONS = [
    ("ccm", "single_boost", "single_boost_ccm"),
    ("ccm", "interleaved_boost", "interleaved_boost_ccm"),
    ("crcm", "single_boost", "boost_crcm"),
    ("dcm", "single_boost", "boost_dcm"),
    ("ccm", "ttp", "totem_pole_ccm"),
    ("ccm", "ttp_interleaved", "totem_pole_interleaved_ccm"),
]

def _normalize(weights: Dict[str, float]) -> Dict[str, float]:
    total = max(sum(weights.values()), 1e-9)
    return {k: v / total for k, v in weights.items()}

def build_mode_weights(intake: FullIntake) -> Dict[str, float]:
    base = {k: 1.0 for k in next(iter(MODE_MATRIX.values())).keys()}
    a, t, b, c = intake.application, intake.thermal, intake.business, intake.control
    p_hi = max(a.output_power_w_high_line, a.output_power_w_nom)
    if p_hi >= 1500:
        base["high_power_fit"] += 3.0
        base["thermal_current_stress"] += 1.5
    if p_hi >= 2500:
        base["high_power_fit"] += 1.5
        base["emi_predictability"] += 1.0
    base["emi_predictability"] += 1.5
    base["power_density_fit"] += b.power_density_priority / 5.0
    base["implementation_risk"] += b.implementation_risk_priority / 4.0
    if c.control_preference == "Analog":
        base["fixed_frequency_fit"] += 1.0
    if t.cooling_type in {"natural_convection", "conduction_cooled"}:
        base["thermal_current_stress"] += 1.3
    return _normalize(base)

def build_topology_weights(intake: FullIntake) -> Dict[str, float]:
    base = {k: 1.0 for k in next(iter(TOPOLOGY_MATRIX.values())).keys()}
    b, t, m, c = intake.business, intake.thermal, intake.mechanical, intake.control
    base["efficiency_fit"] += b.efficiency_priority / 4.0
    base["cost_fit"] += b.cost_priority / 5.0
    base["mechanical_fit"] += m.power_density_priority / 5.0
    base["implementation_fit"] += b.implementation_risk_priority / 4.0
    if t.cooling_type in {"natural_convection", "conduction_cooled"}:
        base["thermal_fit"] += 1.5
    if c.control_preference == "Analog":
        base["control_fit"] += 1.7
    return _normalize(base)

def _mode_penalty(intake: FullIntake, mode: str) -> List[str]:
    notes = []
    p_hi = max(intake.application.output_power_w_high_line, intake.application.output_power_w_nom)
    if p_hi >= 1500 and mode == "dcm":
        notes.append("DCM penalized at higher power because of peak/RMS current stress.")
    if p_hi >= 2500 and mode == "crcm":
        notes.append("CrCM penalized at high power because variable-frequency EMI becomes harder.")
    if intake.control.control_preference == "Analog" and mode == "crcm":
        notes.append("CrCM penalized because variable-frequency control is a weaker analog fit.")
    return notes

def _topology_penalty(intake: FullIntake, topo: str) -> List[str]:
    notes = []
    tech = intake.business.preferred_switch_technology
    ctrl = intake.control.control_preference
    p_hi = max(intake.application.output_power_w_high_line, intake.application.output_power_w_nom)
    if topo in {"ttp", "ttp_interleaved"} and not any(x in tech for x in ["SiC", "GaN"]):
        notes.append("Totem-pole penalized because wide-bandgap devices are not preferred.")
    if topo in {"ttp", "ttp_interleaved"} and ctrl == "Analog":
        notes.append("Totem-pole penalized because analog-only control is a weak fit.")
    if topo == "ttp_interleaved" and intake.business.implementation_risk_priority >= 8:
        notes.append("Interleaved TTP penalized for implementation complexity.")
    if topo == "single_boost" and p_hi >= 1500:
        notes.append("Single-boost penalized because kW-class power benefits strongly from interleaving.")
    if topo == "single_boost" and p_hi >= 2500:
        notes.append("Single-boost further penalized at very high power due to current and thermal concentration.")
    return notes

def _score_row(row: Dict[str, float], weights: Dict[str, float]) -> float:
    return sum(row[k] * weights[k] for k in weights)

def _mini_intake_defaults(mode: str, topology_key: str) -> Dict[str, Any]:
    if mode == "ccm":
        return {"switching_frequency_style": "fixed", "recommended_frequency_hz": 70000.0, "recommended_frequency_range_hz": None, "ask_crest_ripple_ratio": True, "default_crest_ripple_ratio": 0.20, "crest_ripple_ratio_guidance": "Typical CCM crest ripple ratio is about 0.1 to 0.4."}
    if mode == "crcm":
        return {"switching_frequency_style": "variable", "recommended_frequency_hz": None, "recommended_frequency_range_hz": [45000.0, 180000.0], "ask_crest_ripple_ratio": False, "default_crest_ripple_ratio": 2.0, "crest_ripple_ratio_guidance": "CrCM crest ripple ratio is 2.0 by default."}
    return {"switching_frequency_style": "recommend", "recommended_frequency_hz": None, "recommended_frequency_range_hz": [60000.0, 160000.0], "ask_crest_ripple_ratio": False, "default_crest_ripple_ratio": 2.5, "crest_ripple_ratio_guidance": "DCM crest ripple ratio is greater than 2.0 by default."}

def select_topology(intake_dict: Dict[str, Any]) -> Dict[str, Any]:
    intake = FullIntake(**intake_dict)
    mode_weights = build_mode_weights(intake)
    topo_weights = build_topology_weights(intake)

    mode_scores = []
    for mode, row in MODE_MATRIX.items():
        base = _score_row(row, mode_weights)
        penalties = _mode_penalty(intake, mode)
        penalty = 0.9 * len(penalties)
        mode_scores.append({"mode": mode, "base_score": round(base, 4), "penalty": round(penalty, 4), "final_score": round(base - penalty, 4), "penalty_details": penalties, "raw_scores": row})
    mode_scores.sort(key=lambda x: x["final_score"], reverse=True)

    topology_scores = []
    for topo, row in TOPOLOGY_MATRIX.items():
        base = _score_row(row, topo_weights)
        penalties = _topology_penalty(intake, topo)
        penalty = 0.95 * len(penalties)
        topology_scores.append({"topology_family": topo, "base_score": round(base, 4), "penalty": round(penalty, 4), "final_score": round(base - penalty, 4), "penalty_details": penalties, "raw_scores": row})
    topology_scores.sort(key=lambda x: x["final_score"], reverse=True)

    family_lookup = {x["topology_family"]: x for x in topology_scores}
    mode_lookup = {x["mode"]: x for x in mode_scores}
    p_hi = max(intake.application.output_power_w_high_line, intake.application.output_power_w_nom)
    ctrl = intake.control.control_preference
    tech = intake.business.preferred_switch_technology

    ranking = []
    for mode, family, candidate in VALID_COMBINATIONS:
        ms = mode_lookup[mode]
        ts = family_lookup[family]
        final = 0.48 * ms["final_score"] + 0.52 * ts["final_score"]
        bonus = 0.0
        reasons = []
        if candidate == "interleaved_boost_ccm" and p_hi >= 1500:
            bonus += 1.6
            reasons.append("Interleaved CCM boost favored for kW-class power because it spreads current and thermal stress.")
        if candidate == "single_boost_ccm" and p_hi >= 1500:
            bonus -= 1.8
            reasons.append("Single-boost CCM de-prioritized because power level benefits strongly from interleaving.")
        if candidate == "totem_pole_ccm" and ctrl in {"Digital", "Recommend"} and any(x in tech for x in ["SiC", "GaN"]):
            bonus += 0.8
            reasons.append("Totem-pole CCM favored because digital control and wide-bandgap devices are acceptable.")
        if candidate == "totem_pole_interleaved_ccm" and ctrl in {"Digital", "Recommend"} and any(x in tech for x in ["SiC", "GaN"]) and p_hi >= 2500:
            bonus += 0.6
            reasons.append("Interleaved TTP gains credit at high power when digital/WBG complexity is acceptable.")
        if candidate == "boost_crcm" and p_hi >= 2500:
            bonus -= 1.0
            reasons.append("CrCM boost de-prioritized because high-power variable-frequency EMI is harder.")
        if candidate == "boost_dcm" and p_hi >= 1000:
            bonus -= 2.0
            reasons.append("DCM de-prioritized because high peak current is a weak fit for this power class.")
        reasons.extend(ms["penalty_details"])
        reasons.extend(ts["penalty_details"])
        prefix = {
            "interleaved_boost_ccm": "Strong practical candidate with predictable EMI and lower per-phase current.",
            "totem_pole_ccm": "High-efficiency candidate with bridge-loss elimination potential.",
            "totem_pole_interleaved_ccm": "Premium high-density candidate with strong thermal sharing.",
            "single_boost_ccm": "Lower-complexity fixed-frequency candidate with strong analog-controller compatibility.",
            "boost_crcm": "Variable-frequency candidate with lower inductance than CCM.",
            "boost_dcm": "Simple low-power candidate, but usually stressed at higher power.",
        }[candidate]
        reasons = [prefix] + reasons
        ranking.append({
            "topology": candidate, "mode": mode, "family": family,
            "base_score": round(final, 4), "bonus": round(bonus, 4), "penalty": 0.0,
            "final_score": round(final + bonus, 4), "penalty_details": reasons[:6],
            "mini_intake_defaults": _mini_intake_defaults(mode, candidate),
        })
    ranking.sort(key=lambda x: x["final_score"], reverse=True)
    top_3 = ranking[:3]
    rec = top_3[0]
    run = top_3[1] if len(top_3) > 1 else None
    return {
        "mode_weights": mode_weights, "topology_weights": topo_weights,
        "mode_scores": mode_scores, "topology_scores": topology_scores,
        "ranking": ranking, "top_3": top_3,
        "recommended_topology": rec["topology"], "recommended_mode": rec["mode"],
        "runner_up_topology": run["topology"] if run else None,
        "why_selected": rec["penalty_details"][:3],
        "why_runner_up_lost": run["penalty_details"][:2] if run else [],
    }
