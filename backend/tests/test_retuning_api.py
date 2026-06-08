from fastapi.testclient import TestClient
from app.main import app
from app.workflow.api_helpers import build_initial_state

client = TestClient(app)

def _sample_state():
    intake = {
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
    state = build_initial_state("retune_project", intake)
    state["selected_topology"] = "interleaved_boost_ccm"
    state["controller_strategy"] = {"selected_mode": "analog"}
    state["selected_controller"] = {"name": "TI UC3854", "type": "analog"}
    return state

def test_retune_both_loops_endpoint():
    state = _sample_state()
    response = client.post(
        "/retune/both-loops",
        json={
            "state": state,
            "current_loop": {"kp": 1.2, "ki": 8000, "compensator_type": "Type2"},
            "voltage_loop": {"kp": 0.8, "ki": 120, "compensator_type": "Type2"},
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "frontend_payload" in data
    assert "current_loop" in data["frontend_payload"]
    assert "voltage_loop" in data["frontend_payload"]

def test_reset_default_values_endpoint():
    state = _sample_state()
    response = client.post("/retune/reset-default-values", json={"state": state})
    assert response.status_code == 200
    assert response.json()["message"] == "Reset to default suggested tuning values."
