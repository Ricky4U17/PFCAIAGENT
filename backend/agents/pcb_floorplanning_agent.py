from __future__ import annotations
from typing import Dict, Any
from app.workflow.phase1_helpers import advisory_result
from app.engines.pcb_floorplanning.advisory_engine import build_pcb_floorplanning_advisory

def node_pcb_floorplanning_advisory(state: Dict[str, Any]) -> Dict[str, Any]:
    advisory = build_pcb_floorplanning_advisory(state)
    return {"pcb_floorplanning_results": advisory_result("pcb_floorplanning_agent", True, advisory.get("status", "advisory_ready"), advisory, False)}
