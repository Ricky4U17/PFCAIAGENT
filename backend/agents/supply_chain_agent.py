from __future__ import annotations
from typing import Dict, Any
from app.workflow.phase1_helpers import advisory_result
from app.engines.supply_chain.advisory_engine import build_supply_chain_advisory

def node_supply_chain_advisory(state: Dict[str, Any]) -> Dict[str, Any]:
    advisory = build_supply_chain_advisory(state)
    return {
        "supply_chain_results": advisory_result(
            name="supply_chain_agent",
            enabled=True,
            status=advisory.get("status", "advisory_ready"),
            details=advisory,
            blocking=False,
        )
    }
