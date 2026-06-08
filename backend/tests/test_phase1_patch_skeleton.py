from app.workflow.phase1_helpers import ensure_phase1_state_defaults
from app.agents.guardrail_v2_agent import node_guardrail_v2_advisory
from app.agents.supply_chain_agent import node_supply_chain_advisory
from app.agents.magnetic_design_v2_agent import node_magnetic_design_v2_advisory
from app.agents.simulation_verification_agent import node_closed_loop_simulation_advisory

def test_phase1_defaults_are_added():
    state = {}
    state = ensure_phase1_state_defaults(state)
    assert state["schema_version"] == "1.1"
    assert "feature_flags" in state
    assert "guardrail_v2_results" in state
    assert "supply_chain_results" in state
    assert "magnetic_design_v2_results" in state
    assert "simulation_verification_results" in state

def test_placeholder_nodes_return_structured_outputs():
    state = ensure_phase1_state_defaults({})
    assert node_guardrail_v2_advisory(state)["guardrail_v2_results"]["status"] == "placeholder_advisory"
    assert node_supply_chain_advisory(state)["supply_chain_results"]["status"] == "placeholder_advisory"
    assert node_magnetic_design_v2_advisory(state)["magnetic_design_v2_results"]["status"] == "placeholder_advisory"
    assert node_closed_loop_simulation_advisory(state)["simulation_verification_results"]["status"] == "placeholder_advisory"
