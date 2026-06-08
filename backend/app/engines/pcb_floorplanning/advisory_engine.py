from __future__ import annotations
from typing import Dict, Any

def build_pcb_floorplanning_advisory(state: Dict[str, Any]) -> Dict[str, Any]:
    topology = state.get("selected_topology", "unknown")
    package = "TO-247"
    semis = state.get("vendor_candidates", {}).get("semiconductors", {}).get("candidates", [])
    if semis:
        package = semis[0].get("package", package)
    return {
        "status": "advisory_ready",
        "blocking": False,
        "floorplan_recommendations": {
            "critical_commutation_loop_priority": "highest",
            "recommended_relative_placement": [
                "place high-frequency switch pair adjacent",
                "place decoupling capacitor directly across switching loop",
                "place boost inductor close to power stage but outside hottest commutation pocket",
            ],
            "estimated_loop_area_reduction_target_percent": 35.0,
            "package_context": package,
            "topology_context": topology,
        },
        "notes": [
            "PCB Floorplanning Agent is advisory-only in Phase 3.",
            "This starter implementation provides layout intent and placement guidance, not real Altium coordinates yet.",
        ],
    }
