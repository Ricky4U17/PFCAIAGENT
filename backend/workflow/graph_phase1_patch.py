from __future__ import annotations
from typing import Dict, Any
from app.workflow.phase1_helpers import ensure_phase1_state_defaults, phase1_enabled
from app.agents.guardrail_v2_agent import node_guardrail_v2_advisory
from app.agents.supply_chain_agent import node_supply_chain_advisory
from app.agents.magnetic_design_v2_agent import node_magnetic_design_v2_advisory
from app.agents.simulation_verification_agent import node_closed_loop_simulation_advisory

def phase1_bootstrap_node(state: Dict[str, Any]) -> Dict[str, Any]:
    return ensure_phase1_state_defaults(state)

def magnetic_design_v2_advisory_node(state: Dict[str, Any]) -> Dict[str, Any]:
    if not phase1_enabled(state, "enable_magnetic_design_v2"):
        return {"magnetic_design_v2_results": {"feature": "magnetic_design_v2", "enabled": False, "status": "disabled", "blocking": False, "details": {}}}
    return node_magnetic_design_v2_advisory(state)

def guardrail_v2_advisory_node(state: Dict[str, Any]) -> Dict[str, Any]:
    if not phase1_enabled(state, "enable_guardrail_v2"):
        return {"guardrail_v2_results": {"feature": "guardrail_v2", "enabled": False, "status": "disabled", "blocking": False, "details": {}}}
    return node_guardrail_v2_advisory(state)

def supply_chain_advisory_node(state: Dict[str, Any]) -> Dict[str, Any]:
    if not phase1_enabled(state, "enable_supply_chain_agent"):
        return {"supply_chain_results": {"feature": "supply_chain_agent", "enabled": False, "status": "disabled", "blocking": False, "details": {}}}
    return node_supply_chain_advisory(state)

def closed_loop_simulation_advisory_node(state: Dict[str, Any]) -> Dict[str, Any]:
    if not phase1_enabled(state, "enable_closed_loop_simulation"):
        return {"simulation_verification_results": {"feature": "closed_loop_simulation", "enabled": False, "status": "disabled", "blocking": False, "details": {}}}
    return node_closed_loop_simulation_advisory(state)
