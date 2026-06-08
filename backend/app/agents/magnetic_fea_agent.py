from __future__ import annotations
from typing import Dict, Any
from app.workflow.phase1_helpers import advisory_result
from app.engines.magnetic_fea.advisory_engine import build_magnetic_fea_advisory

def node_magnetic_fea_advisory(state: Dict[str, Any]) -> Dict[str, Any]:
    advisory = build_magnetic_fea_advisory(state)
    return {"magnetic_fea_results": advisory_result("magnetic_fea_agent", True, advisory.get("status", "advisory_ready"), advisory, False)}
