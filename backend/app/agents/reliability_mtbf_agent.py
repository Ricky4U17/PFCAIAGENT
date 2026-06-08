from __future__ import annotations
from typing import Dict, Any
from app.workflow.phase1_helpers import advisory_result
from app.engines.reliability.advisory_engine import build_reliability_mtbf_advisory

def node_reliability_mtbf_advisory(state: Dict[str, Any]) -> Dict[str, Any]:
    advisory = build_reliability_mtbf_advisory(state)
    return {"reliability_mtbf_results": advisory_result("reliability_mtbf_agent", True, advisory.get("status", "advisory_ready"), advisory, False)}
