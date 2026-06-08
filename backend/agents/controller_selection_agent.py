from __future__ import annotations
from typing import Dict, Any, List


def build_controller_strategy(state: Dict[str, Any]) -> Dict[str, Any]:
    topology   = state.get("selected_topology") or \
                 state.get("topology_recommendation", {}).get("recommended_topology")
    intake     = state.get("intake", {})
    preferred  = intake.get("business", {}).get("preferred_switch_technology", ["Si", "SiC", "GaN"])

    # MA-7 fix: respect intake.control.control_preference.
    stated_pref = intake.get("control", {}).get("control_preference", "Recommend")

    is_ttp = topology in {"totem_pole_ccm", "totem_pole_interleaved_ccm"}

    # Recommendation logic:
    # • TTP → digital is strongly preferred for hard-switching control
    # • Conventional boost → prefer analog unless designer said Digital or SiC/GaN is in use
    if is_ttp:
        if stated_pref == "Analog":
            recommended_mode = "analog"  # honour designer's stated preference
        else:
            recommended_mode = "digital"
    else:
        if stated_pref == "Digital":
            recommended_mode = "digital"
        elif stated_pref == "Analog":
            recommended_mode = "analog"
        else:
            # "Recommend": prefer analog for conventional boost unless WBG is present
            recommended_mode = "digital" if ("SiC" in preferred or "GaN" in preferred) else "analog"

    # Build controller list filtered to allowed hardware.
    if is_ttp:
        controllers: List[Dict[str, Any]] = [
            {"name": "TI C2000", "type": "digital",
             "reason": "Strong fit for totem-pole gate-drive and dead-time control."},
            {"name": "STM32G4 + custom firmware", "type": "digital",
             "reason": "Cost-effective digital option for TTP with fast ADC."},
            {"name": "Designer supplied controller", "type": "digital",
             "reason": "Use if your platform is predefined."},
        ]
    else:
        controllers = [
            {"name": "TI UC3854", "type": "analog",
             "reason": "Classic CCM boost PFC analog controller, widely supported."},
            {"name": "Infineon ICE3PCS01G", "type": "analog",
             "reason": "Dedicated CCM PFC controller with integrated gate drive."},
            {"name": "ON NCP1654", "type": "analog",
             "reason": "Fixed-frequency CCM PFC controller with burst mode."},
            {"name": "TI C2000", "type": "digital",
             "reason": "Flexible DSP option for adaptive tuning and digital PFC."},
            {"name": "STM32G4 + X-CUBE-MCSDK", "type": "digital",
             "reason": "Cost-effective digital option with PFC support libraries."},
            {"name": "Designer supplied controller", "type": "analog_or_digital",
             "reason": "Use your existing platform."},
        ]

    reasons: List[str] = []
    if is_ttp:
        reasons.append("Totem-pole PFC generally favors digital control for dead-time management.")
        if stated_pref == "Analog":
            reasons.append("Designer stated Analog preference — honoured, but digital is strongly recommended.")
    else:
        reasons.append("Conventional boost families support analog or digital control.")
    if "SiC" in preferred or "GaN" in preferred:
        reasons.append("Wide-bandgap preference increases attractiveness of digital control.")
    if stated_pref in {"Analog", "Digital"}:
        reasons.append(f"Designer intake specifies '{stated_pref}' as control preference.")

    return {
        "topology":                    topology,
        "stated_control_preference":   stated_pref,
        "allowed_strategies":          ["analog", "digital"],
        "recommended_controller_mode": recommended_mode,
        "recommended_controllers":     controllers,
        "reasoning":                   reasons,
        "designer_action":             "Select recommended controller mode/controller or provide a custom controller.",
        "selected_mode":               None,
        "selected_controller":         None,
    }
