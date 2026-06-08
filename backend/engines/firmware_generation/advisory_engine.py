from __future__ import annotations
from typing import Dict, Any

def build_firmware_generation_advisory(state: Dict[str, Any]) -> Dict[str, Any]:
    ctrl = state.get("selected_controller", {})
    mode = ctrl.get("type") or state.get("controller_strategy", {}).get("selected_mode") or "analog"
    approved = state.get("approved_tuning", {})
    topology = state.get("selected_topology", "unknown")

    if mode != "digital":
        return {
            "status": "incomplete",
            "blocking": False,
            "target_platform": None,
            "notes": [
                "Firmware generation advisory is most relevant for digital control paths.",
                "Current selected controller mode is not digital.",
            ],
        }

    return {
        "status": "advisory_ready",
        "blocking": False,
        "target_platform": "TI C2000 / DSP starter path",
        "generated_artifacts_preview": {
            "pwm_configuration": {"fsw_hz": 70000, "mode": "up-down" if "totem" in topology.lower() else "up"},
            "adc_trigger_strategy": "PWM synchronized sampling",
            "control_isr_structure": ["read_adc", "run_current_loop", "run_voltage_loop", "update_pwm"],
            "current_loop_coefficients": approved.get("current_loop", {}),
            "voltage_loop_coefficients": approved.get("voltage_loop", {}),
        },
        "notes": [
            "Firmware Generation Agent is advisory-only in Phase 2.",
            "This starter implementation produces a firmware handoff structure, not deployable C code yet.",
            "Promote to real firmware generation after digital control path is hardened.",
        ],
    }
