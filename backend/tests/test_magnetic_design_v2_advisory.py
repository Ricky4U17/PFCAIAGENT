from app.agents.magnetic_design_v2_agent import node_magnetic_design_v2_advisory

def test_magnetic_design_v2_returns_structured_result():
    state = {
        "magnetic_design_data": {
            "inputs": {
                "L_uH": 235.0,
                "I_pk": 14.0,
                "I_rms": 10.0
            },
            "results": {
                "Ap_required_cm4": 1.8,
                "Turns_est": 12.4,
                "Wire_Area_mm2": 2.6
            }
        }
    }
    out = node_magnetic_design_v2_advisory(state)
    result = out["magnetic_design_v2_results"]
    assert result["status"] == "advisory_ready"
    assert result["blocking"] is False
    details = result["details"]
    assert details["recommended_core_family"] is not None
    assert details["derived_estimates"]["turns_integerized"] >= 1

def test_magnetic_design_v2_handles_missing_legacy_data():
    out = node_magnetic_design_v2_advisory({})
    result = out["magnetic_design_v2_results"]
    assert result["status"] == "advisory_ready"
    assert result["blocking"] is False
