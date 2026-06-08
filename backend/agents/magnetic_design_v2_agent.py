from __future__ import annotations
from typing import Dict, Any
from app.workflow.phase1_helpers import advisory_result
from app.engines.magnetics_v2.advisory_engine import build_magnetic_design_v2_advisory

def node_magnetic_design_v2_advisory(state: Dict[str, Any]) -> Dict[str, Any]:
    advisory = build_magnetic_design_v2_advisory(state)
    return {
        "magnetic_design_v2_results": advisory_result(
            name="magnetic_design_v2",
            enabled=True,
            status=advisory.get("status", "advisory_ready"),
            details=advisory,
            blocking=False,
        )
    }
