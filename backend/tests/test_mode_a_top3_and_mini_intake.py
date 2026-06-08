from app.intake.topology_selector import select_topology
from app.workflow.api_helpers import build_initial_state
from app.workflow.graph import build_graph

def _intake():
    return {
        "application": {
            "vin_rms_min": 90.0, "vin_rms_max": 264.0, "nominal_line_frequency_hz": 60.0,
            "input_frequency_range_hz_min": 47.0, "input_frequency_range_hz_max": 63.0,
            "output_bus_voltage_v": 390.0, "dc_bus_voltage_ripple_pk_pk_v": 20.0,
            "output_power_w_nom": 3600.0, "output_power_w_low_line": 1700.0, "output_power_w_high_line": 3600.0,
            "power_factor_target": 0.99, "efficiency_target_percent": 98.0, "hold_up_time_ms": 20.0,
        },
        "thermal": {"cooling_type": "fan_cooled", "ambient_temp_c_max": 50.0, "max_temp_rise_c": 45.0, "hotspot_limit_c": 110.0, "max_enclosure_rth_c_per_w": 0.5},
        "mechanical": {"height_limit_mm": 40.0, "power_density_priority": 8},
        "compliance": {"conducted_emi_class": "FCC Class B", "radiated_emi_class": "FCC Class B", "harmonics_class": "EN61000-3-2", "surge_requirement": "1 KV Line to Line / 2KV Line to Ground Class A", "leakage_current_limit_ua": 3500.0, "application_class": "Industrial", "semi_f47_required": False},
        "control": {"control_preference": "Recommend"},
        "business": {"cost_priority": 7, "efficiency_priority": 9, "power_density_priority": 8, "implementation_risk_priority": 8, "preferred_switch_technology": ["Si", "SiC", "GaN"]},
        "supply": {"preferred_vendors": [], "avoid_vendors": []},
    }

def test_selector_returns_top3():
    result = select_topology(_intake())
    assert len(result["top_3"]) == 3
    assert result["recommended_mode"] in {"ccm", "crcm", "dcm"}

def test_graph_runs_topology_specific_intake():
    graph = build_graph()
    state = build_initial_state("modea", _intake())
    state = graph.invoke(state)
    state["human_feedback"] = {"approved": True}
    state = graph.invoke(state)
    assert state["current_step"] in {"topology_specific_intake", "awaiting_topology_specific_inputs"}
