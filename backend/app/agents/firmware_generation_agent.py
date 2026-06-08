from __future__ import annotations
from typing import Dict, Any
from app.workflow.phase1_helpers import advisory_result
from app.engines.firmware_generation.advisory_engine import build_firmware_generation_advisory

def node_firmware_generation_advisory(state: Dict[str, Any]) -> Dict[str, Any]:
    advisory = build_firmware_generation_advisory(state)
    return {"firmware_generation_results": advisory_result("firmware_generation_agent", True, advisory.get("status", "advisory_ready"), advisory, False)}
