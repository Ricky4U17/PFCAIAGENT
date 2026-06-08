import numpy as np
from app.engines.state_space.operating_point import build_operating_point
from app.engines.state_space.plant_models import topology_state_space_model
from app.engines.state_space.loop_compensators import build_current_loop_compensator, build_voltage_loop_compensator
from app.engines.state_space.analysis import ss_to_siso_tf, build_loop_analysis
from app.engines.state_space.schemas import StateSpaceAnalysisResult, LoopTuningSuggestion, LoopAnalysisResult

def _find_fc_from_bode(freq_hz, mag_db) -> float:
    idx = min(range(len(mag_db)), key=lambda i: abs(mag_db[i]))
    return float(freq_hz[idx])

def analyze_selected_topology(topology: str, inputs: dict, controller_mode: str = "analog", tuning_override: dict | None = None) -> StateSpaceAnalysisResult:
    tuning_override = tuning_override or {}
    current_override = tuning_override.get("current_loop", {})
    voltage_override = tuning_override.get("voltage_loop", {})
    op = build_operating_point(topology, inputs)
    matrices, raw = topology_state_space_model(topology, op, inputs)
    A, B, C, D = np.array(raw["A"]), np.array(raw["B"]), np.array(raw["C"]), np.array(raw["D"])
    i_num, i_den = ss_to_siso_tf(A,B,C,D,0,0)
    ctype_i, cnum_i, cden_i, cmeta_i = build_current_loop_compensator(topology, op.fsw_hz, controller_mode, current_override if current_override else None)
    bode_i, step_i, margins_i = build_loop_analysis(i_num, i_den, cnum_i, cden_i, 1.0, max(10*op.fsw_hz,1e4), 2e-3)
    sugg_i = LoopTuningSuggestion(loop_name="current_loop", compensator_type=ctype_i, kp=float(cmeta_i["kp"]), ki=float(cmeta_i["ki"]), kz_hz=float(cmeta_i.get("kz_hz")) if cmeta_i.get("kz_hz") is not None else None, kpole_hz=float(cmeta_i.get("kpole_hz")) if cmeta_i.get("kpole_hz") is not None else None, target_fc_hz=float(cmeta_i["target_fc_hz"]) if cmeta_i.get("target_fc_hz") is not None else 0.0, achieved_fc_hz=_find_fc_from_bode(bode_i.frequency_hz,bode_i.loop_mag_db), phase_margin_deg=float(margins_i["phase_margin_deg"]), gain_margin_db=float(margins_i["gain_margin_db"]), notes=[f"Controller mode: {controller_mode}", "User overrides applied." if current_override else "Suggested coefficients used."])
    current_loop = LoopAnalysisResult(plant_tf_num=i_num.tolist(), plant_tf_den=i_den.tolist(), compensator_tf_num=cnum_i.tolist(), compensator_tf_den=cden_i.tolist(), suggestion=sugg_i, bode=bode_i, step=step_i)

    v_num, v_den = ss_to_siso_tf(A,B,C,D,1,0)
    ctype_v, cnum_v, cden_v, cmeta_v = build_voltage_loop_compensator(topology, op.line_freq_hz, controller_mode, voltage_override if voltage_override else None)
    bode_v, step_v, margins_v = build_loop_analysis(v_num, v_den, cnum_v, cden_v, 0.01, 1e4, 0.5)
    sugg_v = LoopTuningSuggestion(loop_name="voltage_loop", compensator_type=ctype_v, kp=float(cmeta_v["kp"]), ki=float(cmeta_v["ki"]), kz_hz=float(cmeta_v.get("kz_hz")) if cmeta_v.get("kz_hz") is not None else None, kpole_hz=float(cmeta_v.get("kpole_hz")) if cmeta_v.get("kpole_hz") is not None else None, target_fc_hz=float(cmeta_v["target_fc_hz"]) if cmeta_v.get("target_fc_hz") is not None else 0.0, achieved_fc_hz=_find_fc_from_bode(bode_v.frequency_hz,bode_v.loop_mag_db), phase_margin_deg=float(margins_v["phase_margin_deg"]), gain_margin_db=float(margins_v["gain_margin_db"]), notes=[f"Controller mode: {controller_mode}", "User overrides applied." if voltage_override else "Suggested coefficients used."])
    voltage_loop = LoopAnalysisResult(plant_tf_num=v_num.tolist(), plant_tf_den=v_den.tolist(), compensator_tf_num=cnum_v.tolist(), compensator_tf_den=cden_v.tolist(), suggestion=sugg_v, bode=bode_v, step=step_v)

    frontend_payload = {
        "topology": topology,
        "controller_mode": controller_mode,
        "current_loop": {"active_coefficients": {"kp": sugg_i.kp, "ki": sugg_i.ki, "compensator_type": sugg_i.compensator_type, "kpole_hz": sugg_i.kpole_hz}, "suggestion": sugg_i.model_dump(), "bode": bode_i.model_dump(), "step": step_i.model_dump(), "metrics": {"phase_margin_deg": sugg_i.phase_margin_deg, "gain_margin_db": sugg_i.gain_margin_db, "crossover_hz": sugg_i.achieved_fc_hz, "overshoot_percent": step_i.overshoot_percent, "settling_time_s": step_i.settling_time_s, "rise_time_s": step_i.rise_time_s}},
        "voltage_loop": {"active_coefficients": {"kp": sugg_v.kp, "ki": sugg_v.ki, "compensator_type": sugg_v.compensator_type, "kpole_hz": sugg_v.kpole_hz}, "suggestion": sugg_v.model_dump(), "bode": bode_v.model_dump(), "step": step_v.model_dump(), "metrics": {"phase_margin_deg": sugg_v.phase_margin_deg, "gain_margin_db": sugg_v.gain_margin_db, "crossover_hz": sugg_v.achieved_fc_hz, "overshoot_percent": step_v.overshoot_percent, "settling_time_s": step_v.settling_time_s, "rise_time_s": step_v.rise_time_s}},
        "dashboard_controls": {"editable_fields": ["current_loop.kp","current_loop.ki","current_loop.compensator_type","current_loop.kpole_hz","voltage_loop.kp","voltage_loop.ki","voltage_loop.compensator_type","voltage_loop.kpole_hz"], "compare_domains": True},
    }
    return StateSpaceAnalysisResult(operating_point=op, matrices=matrices, current_loop=current_loop, voltage_loop=voltage_loop, frontend_payload=frontend_payload, notes=["CCM boost/interleaved CCM are the strongest first-pass models."])
