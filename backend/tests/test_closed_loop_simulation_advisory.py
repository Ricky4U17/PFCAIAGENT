from app.agents.simulation_verification_agent import node_closed_loop_simulation_advisory

def test_simulation_advisory_returns_structured_result_with_state_space():
    state = {
        "simulation_artifacts": {
            "simplis_netlist": "* demo netlist"
        },
        "state_space_data": {
            "frontend_payload": {
                "current_loop": {
                    "metrics": {
                        "overshoot_percent": 10.0,
                        "settling_time_s": 0.002
                    }
                },
                "voltage_loop": {
                    "metrics": {
                        "overshoot_percent": 5.0,
                        "settling_time_s": 0.15,
                        "crossover_hz": 12.0
                    }
                }
            }
        }
    }
    out = node_closed_loop_simulation_advisory(state)
    result = out["simulation_verification_results"]
    assert result["status"] == "advisory_ready"
    assert result["blocking"] is False
    details = result["details"]
    assert details["simulation_export_available"] is True
    assert details["netlist_available"] is True
    assert "correlation_summary" in details

def test_simulation_advisory_handles_missing_artifacts():
    out = node_closed_loop_simulation_advisory({})
    result = out["simulation_verification_results"]
    assert result["status"] == "incomplete"
    assert result["blocking"] is False
