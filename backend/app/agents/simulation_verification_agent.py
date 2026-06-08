from __future__ import annotations
from typing import Dict, Any
from app.workflow.phase1_helpers import advisory_result
from app.engines.simulation.advisory_engine import build_closed_loop_simulation_advisory

def node_closed_loop_simulation_advisory(state: Dict[str, Any]) -> Dict[str, Any]:
    advisory = build_closed_loop_simulation_advisory(state)
    return {
        "simulation_verification_results": advisory_result(
            name="closed_loop_simulation",
            enabled=True,
            status=advisory.get("status", "advisory_ready"),
            details=advisory,
            blocking=False,
        )
    }
