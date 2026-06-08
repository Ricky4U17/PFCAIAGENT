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
            "implementation_risk_priority": 8, "preferred_switch_technology": ["Si","SiC","GaN"],
        },
    }

def test_smoke_workflow_pauses_and_advances():
    graph = build_graph()
    state = build_initial_state("smoke_project", _sample_intake())

    state = graph.invoke(state)
    assert state["current_step"] == "awaiting_topology_approval"

    state["human_feedback"] = {"approved": True}
    state = graph.invoke(state)
    assert state["current_step"] == "awaiting_controller_approval"

    state["human_feedback"] = {"approved": True, "controller_mode": "analog", "controller_name": "TI UC3854"}
    state = graph.invoke(state)
    assert state["current_step"] == "awaiting_mode_b_approval"
    assert "input_processing" in state["step_results"]
