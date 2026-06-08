from __future__ import annotations
from typing import Dict, Any
from app.engines.state_space.topology_state_space_router import analyze_selected_topology
from app.intake.compat import app_line_frequency_hz, compliance_leakage_limit_ma, compliance_leakage_limit_ua, app_efficiency_fraction

def _build_common_inputs_from_state(state: Dict[str, Any]):
    topology = state.get("selected_topology", "single_boost_ccm")
    app = state["intake"]["application"]
    overrides = state.get("human_feedback", {}).get("overrides", {})
    controller_strategy = state.get("controller_strategy", {})
    selected_controller = state.get("selected_controller", {}) or {}
    controller_mode = selected_controller.get("type") or controller_strategy.get("selected_mode") or controller_strategy.get("recommended_controller_mode") or "analog"
    inputs = {"Vac": app["vin_rms_min"], "Vout": app["output_bus_voltage_v"], "Pout": app.get("output_power_w_low_line", app["output_power_w_nom"]), "eff": overrides.get("eff", 0.945), "pf": app["power_factor_target"], "L": overrides.get("L", 235e-6), "Cout": overrides.get("Cout", 2200e-6), "fsw": overrides.get("fsw", 70000.0), "line_freq": app["line_frequency_hz_nom"]}
    tuning_override = overrides.get("state_space_tuning", {})
    return topology, inputs, controller_mode, tuning_override

def build_state_space_from_state(state: Dict[str, Any]) -> Dict[str, Any]:
    topology, inputs, controller_mode, tuning_override = _build_common_inputs_from_state(state)
    result = analyze_selected_topology(topology=topology, inputs=inputs, controller_mode=controller_mode, tuning_override=tuning_override)
    out = result.model_dump()
    out["approved_tuning"] = state.get("approved_tuning", {})
    return out

def retune_state_space_from_state(state: Dict[str, Any]) -> Dict[str, Any]:
    return build_state_space_from_state(state)

def get_active_tuning_from_state(state: Dict[str, Any]) -> Dict[str, Any]:
    ssd = state.get("state_space_data", {})
    payload = ssd.get("frontend_payload", {})
    if payload:
        return {"current_loop": payload.get("current_loop", {}).get("active_coefficients", {}), "voltage_loop": payload.get("voltage_loop", {}).get("active_coefficients", {})}
    return state.get("human_feedback", {}).get("overrides", {}).get("state_space_tuning", {})