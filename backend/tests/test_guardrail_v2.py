from app.agents.guardrail_v2_agent import node_guardrail_v2_advisory

def _base_state():
    return {
        "feature_flags": {"enable_guardrail_v2": True},
        "calculations": {"i_peak": 20.0, "i_sat_selected": 30.0},
        "state_space_data": {
            "frontend_payload": {
                "current_loop": {"metrics": {"phase_margin_deg": 55.0, "gain_margin_db": 10.0}},
                "voltage_loop": {"metrics": {"phase_margin_deg": 60.0, "gain_margin_db": 8.0, "crossover_hz": 10.0}},
            }
        },
        "reflection_log": [],
    }

def test_guardrail_v2_passes_safe_case():
    state = _base_state()
    out = node_guardrail_v2_advisory(state)
    assert out["guardrail_v2_results"]["status"] == "passed"
    assert out["safety_guardrail_data"]["passed"] is True
    assert out["hitl_required"] is False

def test_guardrail_v2_fails_on_saturation_margin():
    state = _base_state()
    state["calculations"]["i_sat_selected"] = 22.0
    out = node_guardrail_v2_advisory(state)
    assert out["guardrail_v2_results"]["status"] == "failed"
    assert out["hitl_required"] is True
    assert any("saturation margin" in v.lower() for v in out["guardrail_v2_results"]["violations"])

def test_guardrail_v2_fails_on_voltage_loop_bandwidth():
    state = _base_state()
    state["state_space_data"]["frontend_payload"]["voltage_loop"]["metrics"]["crossover_hz"] = 25.0
    out = node_guardrail_v2_advisory(state)
    assert out["guardrail_v2_results"]["status"] == "failed"
    assert any("crossover" in v.lower() for v in out["guardrail_v2_results"]["violations"])

def test_guardrail_v2_marks_incomplete_when_inputs_missing():
    state = {"feature_flags": {"enable_guardrail_v2": True}, "reflection_log": []}
    out = node_guardrail_v2_advisory(state)
    assert out["guardrail_v2_results"]["status"] == "incomplete"
    assert out["safety_guardrail_data"]["passed"] is False
    assert len(out["guardrail_v2_results"]["missing_inputs"]) > 0
