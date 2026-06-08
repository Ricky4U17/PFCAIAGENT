from __future__ import annotations
from typing import Any, Dict, List, Tuple

def _get_nested(data: Dict[str, Any], path: List[str]):
    cur = data
    for key in path:
        if not isinstance(cur, dict) or key not in cur:
            return None
        cur = cur[key]
    return cur

def _first_available_float(state: Dict[str, Any], candidates: List[Tuple[str, List[str]]]):
    missing_labels = []
    for label, path in candidates:
        value = _get_nested(state, path)
        if value is None:
            missing_labels.append(label)
            continue
        try:
            return float(value), []
        except (TypeError, ValueError):
            missing_labels.append(label)
    return None, missing_labels

def evaluate_guardrail_v2(state: Dict[str, Any]) -> Dict[str, Any]:
    flags = state.get("feature_flags", {})
    blocking_enabled = bool(flags.get("enable_guardrail_v2", True))

    guardrail_cfg = {
        "min_sat_margin": 1.2,
        "max_v_loop_bw_hz": 20.0,
        "min_phase_margin_deg": 45.0,
        "min_gain_margin_db": 0.0,
    }

    missing_inputs: List[str] = []
    warnings: List[str] = []
    violations: List[str] = []

    i_pk, miss = _first_available_float(
        state,
        [
            ("calculations.i_peak", ["calculations", "i_peak"]),
            ("step_results.input_processing.Ipk", ["step_results", "input_processing", "Ipk"]),
        ],
    )
    missing_inputs.extend(miss)

    i_sat, miss = _first_available_float(
        state,
        [
            ("calculations.i_sat_selected", ["calculations", "i_sat_selected"]),
            ("hardware_artifacts.inductor.i_sat_a", ["hardware_artifacts", "inductor", "i_sat_a"]),
            ("magnetic_design_v2_results.details.i_sat_selected", ["magnetic_design_v2_results", "details", "i_sat_selected"]),
        ],
    )
    missing_inputs.extend(miss)

    v_bw, miss = _first_available_float(
        state,
        [
            ("state_space_data.v_loop_bw", ["state_space_data", "v_loop_bw"]),
            ("frontend_payload.voltage_loop.metrics.crossover_hz", ["state_space_data", "frontend_payload", "voltage_loop", "metrics", "crossover_hz"]),
            ("step_results.state_space_analysis.frontend_payload.voltage_loop.metrics.crossover_hz", ["step_results", "state_space_analysis", "frontend_payload", "voltage_loop", "metrics", "crossover_hz"]),
        ],
    )
    missing_inputs.extend(miss)

    c_pm, miss = _first_available_float(
        state,
        [("frontend_payload.current_loop.metrics.phase_margin_deg", ["state_space_data", "frontend_payload", "current_loop", "metrics", "phase_margin_deg"])],
    )
    missing_inputs.extend(miss)

    v_pm, miss = _first_available_float(
        state,
        [("frontend_payload.voltage_loop.metrics.phase_margin_deg", ["state_space_data", "frontend_payload", "voltage_loop", "metrics", "phase_margin_deg"])],
    )
    missing_inputs.extend(miss)

    c_gm, miss = _first_available_float(
        state,
        [("frontend_payload.current_loop.metrics.gain_margin_db", ["state_space_data", "frontend_payload", "current_loop", "metrics", "gain_margin_db"])],
    )
    missing_inputs.extend(miss)

    v_gm, miss = _first_available_float(
        state,
        [("frontend_payload.voltage_loop.metrics.gain_margin_db", ["state_space_data", "frontend_payload", "voltage_loop", "metrics", "gain_margin_db"])],
    )
    missing_inputs.extend(miss)

    seen = set()
    missing_inputs = [x for x in missing_inputs if not (x in seen or seen.add(x))]

    sat_margin = None
    if i_pk is not None and i_sat is not None:
        sat_margin = i_sat / max(i_pk, 1e-12)
        if sat_margin < guardrail_cfg["min_sat_margin"]:
            violations.append(
                f"Inductor saturation margin too low: {sat_margin:.3f} < {guardrail_cfg['min_sat_margin']:.3f}."
            )

    if v_bw is not None and v_bw > guardrail_cfg["max_v_loop_bw_hz"]:
        violations.append(
            f"Voltage-loop crossover too high: {v_bw:.3f} Hz > {guardrail_cfg['max_v_loop_bw_hz']:.3f} Hz."
        )

    if c_pm is not None and c_pm < guardrail_cfg["min_phase_margin_deg"]:
        violations.append(
            f"Current-loop phase margin too low: {c_pm:.3f}° < {guardrail_cfg['min_phase_margin_deg']:.3f}°."
        )

    if v_pm is not None and v_pm < guardrail_cfg["min_phase_margin_deg"]:
        violations.append(
            f"Voltage-loop phase margin too low: {v_pm:.3f}° < {guardrail_cfg['min_phase_margin_deg']:.3f}°."
        )

    if c_gm is not None and c_gm <= guardrail_cfg["min_gain_margin_db"]:
        violations.append(
            f"Current-loop gain margin not positive: {c_gm:.3f} dB <= {guardrail_cfg['min_gain_margin_db']:.3f} dB."
        )

    if v_gm is not None and v_gm <= guardrail_cfg["min_gain_margin_db"]:
        violations.append(
            f"Voltage-loop gain margin not positive: {v_gm:.3f} dB <= {guardrail_cfg['min_gain_margin_db']:.3f} dB."
        )

    if sat_margin is not None and sat_margin < (guardrail_cfg["min_sat_margin"] + 0.1):
        warnings.append("Inductor saturation margin is close to the minimum threshold.")
    if v_bw is not None and v_bw > (0.8 * guardrail_cfg["max_v_loop_bw_hz"]):
        warnings.append("Voltage-loop crossover is approaching the 20 Hz ceiling.")

    hard_stop = len(violations) > 0
    status = "failed" if hard_stop else ("incomplete" if missing_inputs else "passed")

    explanation = {
        "passed": "Guardrail v2 passed with no hard-stop violations.",
        "failed": "Guardrail v2 found one or more hard-stop violations.",
        "incomplete": "Guardrail v2 could not fully evaluate all checks because some inputs are missing.",
    }[status]

    return {
        "status": status,
        "hard_stop": hard_stop,
        "blocking_enabled": blocking_enabled,
        "violations": violations,
        "warnings": warnings,
        "missing_inputs": missing_inputs,
        "metrics": {
            "i_peak_a": i_pk,
            "i_sat_a": i_sat,
            "sat_margin": sat_margin,
            "v_loop_bw_hz": v_bw,
            "current_loop_phase_margin_deg": c_pm,
            "voltage_loop_phase_margin_deg": v_pm,
            "current_loop_gain_margin_db": c_gm,
            "voltage_loop_gain_margin_db": v_gm,
        },
        "rules": guardrail_cfg,
        "explanation": explanation,
    }
