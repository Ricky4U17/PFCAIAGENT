from app.engines.thermal_loopback_engine import evaluate_bidirectional_thermal

def node_bidirectional_thermal(state):
    app = state["intake"]["application"]; thermal = state["intake"].get("thermal", {}); overrides = state.get("human_feedback", {}).get("overrides", {})
    payload = {"Pout": app.get("output_power_w_nom", 1700.0), "eff": overrides.get("eff", 0.95), "max_rise_c": thermal.get("max_temp_rise_c", 40.0), "max_enclosure_rth_c_per_w": thermal.get("max_enclosure_rth_c_per_w", 0.5), "fsw": overrides.get("fsw", 70000.0)}
    result = evaluate_bidirectional_thermal(payload)
    out = {"thermal_data": result.get("thermal_data", {}), "thermal_status": result["status"]}
    if result["status"] == "failed" and result.get("loopback"):
        out["human_feedback"] = {"status": "recalculate_hardware", "reason": result["loopback"]["reason"], "overrides": result["loopback"]["suggested_overrides"]}
    return out
