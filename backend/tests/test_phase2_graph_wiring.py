from app.workflow.api_helpers import build_initial_state
from app.workflow.graph import build_graph

def _sample_intake():
    return {
        "application": {
            "vin_rms_min": 90.0, "vin_rms_max": 264.0, "line_frequency_hz_nom": 60.0,
            "output_bus_voltage_v": 390.0, "output_power_w_nom": 3600.0,
            "output_power_w_low_line": 1700.0, "power_factor_target": 0.99,
        },
        "thermal": {
            "cooling_type": "fan_cooled", "ambient_temp_c_max": 50.0,
            "max_temp_rise_c": 45.0, "max_enclosure_rth_c_per_w": 0.5,
        },
        "compliance": {
            "conducted_emi_required": True, "radiated_emi_required": True,
            "surge_required": True, "leakage_current_limit_ma": 3.5,
        },
        "business": {
            "cost_priority": 7, "efficiency_priority": 9, "power_density_priority": 8,
            "implementation_risk_priority": 8, "preferred_switch_technology": ["Si", "SiC", "GaN"],
        },
    }

def test_phase2_advisory_nodes_execute_in_main_flow():
    graph = build_graph()
    state = build_initial_state("phase2_flow", _sample_intake())
    state = graph.invoke(state)
    state["human_feedback"] = {"approved": True}
    state = graph.invoke(state)
    state["human_feedback"] = {"approved": True, "controller_mode": "analog", "controller_name": "TI UC3854"}
    state = graph.invoke(state)

    for _ in range(30):
        state["human_feedback"] = {"approved": True}
        state = graph.invoke(state)
        if state.get("current_step") == "final":
            break

    assert "layout_parasitics_advisory" in state.get("step_results", {})
    assert "firmware_generation_advisory" in state.get("step_results", {})
    assert "reliability_mtbf_advisory" in state.get("step_results", {})
    assert "layout_parasitics_results" in state
    assert "firmware_generation_results" in state
    assert "reliability_mtbf_results" in state
