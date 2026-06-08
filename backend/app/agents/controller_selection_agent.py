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
        n_phases = state.get("selected_channels", 2) or 2
        topo = (topology or '').lower()
        is_interleaved = 'interleaved' in topo
        is_crcm = 'crcm' in topo or 'crm' in topo
        is_dcm  = 'dcm' in topo
        n_phases = state.get('selected_channels', 2) or 2

        if is_crcm:
            controllers = [
                {"name": "L6563 (ST)", "type": "analog",
                 "reason": "Dedicated CrCM/TM PFC controller. Fixed off-time control."},
                {"name": "NCP1607 (ON Semi)", "type": "analog",
                 "reason": "Transition-mode PFC controller. Good for 200-600W."},
                {"name": "FAN6961 (ON Semi)", "type": "analog",
                 "reason": "CrCM PFC controller with green-mode standby."},
                {"name": "TI C2000", "type": "digital",
                 "reason": "Digital option for variable frequency CrCM control."},
            ]
        elif is_dcm:
            controllers = [
                {"name": "NCP1606 (ON Semi)", "type": "analog",
                 "reason": "DCM PFC controller. Best for low power under 150W."},
                {"name": "L6561 (ST)", "type": "analog",
                 "reason": "DCM/TM PFC controller. Simple and low cost."},
                {"name": "TI C2000", "type": "digital",
                 "reason": "Digital option for DCM control."},
            ]
        elif is_interleaved and n_phases == 3:
            controllers = [
                {"name": "FAN9613 (ON Semi)", "type": "analog",
                 "reason": "Dedicated 3-phase interleaved CCM PFC. Built-in 120 deg phase shift."},
                {"name": "UCC28070A x3 + sync (TI)", "type": "analog",
                 "reason": "Three UCC28070A with external 120 deg RC phase-shift network."},
                {"name": "TI C2000", "type": "digital",
                 "reason": "Digital option for 3-phase interleaved PFC."},
            ]
        elif is_interleaved and n_phases == 2:
            controllers = [
                {"name": "UCC28070A (TI)", "type": "analog",
                 "reason": "Dedicated 2-phase interleaved CCM PFC. 180 deg phase shift hardwired."},
                {"name": "NCP1631 (ON Semi)", "type": "analog",
                 "reason": "2-phase interleaved CCM PFC with dead-time and OVP/OCP."},
                {"name": "FAN9612 (ON Semi)", "type": "analog",
                 "reason": "Master-slave 2-phase interleaved CCM PFC."},
                {"name": "TI C2000", "type": "digital",
                 "reason": "Digital option for 2-phase interleaved PFC."},
            ]
        else:
            controllers = [
                {"name": "TI UC3854", "type": "analog",
                 "reason": "Classic single-phase CCM boost PFC analog controller."},
                {"name": "Infineon ICE3PCS01G", "type": "analog",
                 "reason": "Dedicated CCM PFC controller with integrated gate drive."},
                {"name": "ON NCP1654", "type": "analog",
                 "reason": "Fixed-frequency CCM PFC controller with burst mode."},
                {"name": "TI C2000", "type": "digital",
                 "reason": "Flexible DSP for adaptive tuning and digital PFC."},
                {"name": "STM32G4 + X-CUBE-MCSDK", "type": "digital",
                 "reason": "Cost-effective digital option with PFC support libraries."},
            ]
        
