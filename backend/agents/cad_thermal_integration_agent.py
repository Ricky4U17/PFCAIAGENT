from __future__ import annotations
from typing import Dict, Any
from app.workflow.phase1_helpers import advisory_result
from app.engines.cad_thermal.advisory_engine import build_cad_thermal_integration_advisory

def node_cad_thermal_integration_advisory(state: Dict[str, Any]) -> Dict[str, Any]:
    advisory = build_cad_thermal_integration_advisory(state)
    return {"cad_thermal_integration_results": advisory_result("cad_thermal_integration_agent", True, advisory.get("status", "advisory_ready"), advisory, False)}
