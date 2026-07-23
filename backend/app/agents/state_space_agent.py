from __future__ import annotations
from typing import Dict, Any
from app.engines.state_space.topology_state_space_router import analyze_selected_topology
from app.intake.compat import app_line_frequency_hz, compliance_leakage_limit_ma, compliance_leakage_limit_ua, app_efficiency_fraction

def _wire_dcr_ohm_from_state(state: Dict[str, Any]):
    """Per-phase inductor DCR (Ω) from the SELECTED wire, evaluated at the copper operating
    temperature (ambient + winding ΔT-rise), when an approved inductor is present in state — the
    point-29 rule (no hardcoded DCR for control-loop calcs). DCR is linear in temperature, so we
    interpolate between step7's two wire-computed points (DCR@25 °C, DCR@100 °C). Returns None when
    no inductor has been selected yet (the first-pass workflow magnetic model picks no wire), so the
    caller keeps a representative default rather than fabricating a value."""
    ALPHA_CU = 0.00393
    d = (state.get("approved_design") or state.get("selected_inductor")
         or state.get("step_results", {}).get("magnetic_design", {}) or {})
    if not isinstance(d, dict):
        return None
    dcr25  = float(d.get("DCR_25C_mOhm", 0) or 0)
    dcr100 = float(d.get("DCR_100C_mOhm", 0) or 0)
    if dcr25 <= 0:
        return None
    if dcr100 <= 0:
        dcr100 = dcr25 * (1 + ALPHA_CU * 80) / (1 + ALPHA_CU * 5)
    try:
        ambient = float(state.get("intake", {}).get("thermal", {}).get("ambient_temp_c_max", 50) or 50)
    except Exception:
        ambient = 50.0
    dT_wdg = float(d.get("dT_wdg_C", 0) or 0)
    T_cu   = ambient + dT_wdg
    return (dcr25 + (dcr100 - dcr25) * (T_cu - 25.0) / 75.0) * 1e-3   # mΩ → Ω

def _build_common_inputs_from_state(state: Dict[str, Any]):
    topology = state.get("selected_topology", "single_boost_ccm")
    app = state["intake"]["application"]
    overrides = state.get("human_feedback", {}).get("overrides", {})
    controller_strategy = state.get("controller_strategy", {})
    selected_controller = state.get("selected_controller", {}) or {}
    controller_mode = selected_controller.get("type") or controller_strategy.get("selected_mode") or controller_strategy.get("recommended_controller_mode") or "analog"
    # DCR precedence: explicit override → wire-derived from the selected inductor → representative
    # default (no wire chosen yet in the first-pass workflow path). ~20 mΩ matches this design's
    # actual inductor, so the default is realistic rather than arbitrary.
    r_L = overrides.get("r_L")
    if r_L is None:
        r_L = _wire_dcr_ohm_from_state(state)
    if r_L is None:
        r_L = 0.02
    inputs = {"Vac": app["vin_rms_min"], "Vout": app["output_bus_voltage_v"], "Pout": app.get("output_power_w_low_line", app["output_power_w_nom"]), "eff": overrides.get("eff", 0.945), "pf": app["power_factor_target"], "L": overrides.get("L", 235e-6), "Cout": overrides.get("Cout", 2200e-6), "fsw": overrides.get("fsw", 70000.0), "line_freq": app["line_frequency_hz_nom"], "r_L": float(r_L)}
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