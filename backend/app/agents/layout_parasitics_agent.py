from __future__ import annotations
from typing import Dict, Any
from app.workflow.phase1_helpers import advisory_result
from app.engines.layout_parasitics.advisory_engine import build_layout_parasitics_advisory

def node_layout_parasitics_advisory(state: Dict[str, Any]) -> Dict[str, Any]:
    advisory = build_layout_parasitics_advisory(state)
    return {"layout_parasitics_results": advisory_result("layout_parasitics_agent", True, advisory.get("status", "advisory_ready"), advisory, False)}
