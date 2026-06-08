from __future__ import annotations
from typing import Dict, Any

def _safe_float(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return default

def build_layout_parasitics_advisory(state: Dict[str, Any]) -> Dict[str, Any]:
    fsw = _safe_float(state.get("human_feedback", {}).get("overrides", {}).get("fsw"), 70000.0)
    topology = state.get("selected_topology", "unknown")
    vendor = state.get("vendor_candidates", {})
    semis = vendor.get("semiconductors", {}).get("candidates", []) if isinstance(vendor, dict) else []
    selected_pkg = semis[0].get("package", "unknown") if semis else "unknown"

    return {
        "status": "advisory_ready",
        "blocking": False,
        "estimated_parasitics": {
            "hf_power_loop_stray_inductance_nH": 10.0,
            "gate_loop_stray_inductance_nH": 4.0,
            "switch_node_parasitic_capacitance_pF": 35.0 if semis else 60.0,
            "selected_package_context": selected_pkg,
        },
        "impact_assessment": {
            "ringing_risk": "moderate" if fsw >= 65000 else "low",
            "dvdt_sensitivity": "high" if "totem" in topology.lower() or fsw >= 70000 else "moderate",
            "emi_penalty_estimate": "moderate",
            "switching_loss_penalty_estimate_percent": 6.5 if fsw >= 70000 else 3.0,
        },
        "notes": [
            "Layout Parasitics Agent is advisory-only in Phase 2.",
            "Parasitics are heuristic estimates until real PCB floorplanning is integrated.",
            "Use this result to inform EMI, thermal, and semiconductor tradeoff review.",
        ],
    }
