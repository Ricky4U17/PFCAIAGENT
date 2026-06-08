from __future__ import annotations
from typing import Dict, Any, List

def evaluate_tuning_guardrails(state_space_data: Dict[str, Any]) -> Dict[str, Any]:
    payload = state_space_data.get("frontend_payload", {})
    current = payload.get("current_loop", {})
    voltage = payload.get("voltage_loop", {})
    cm = current.get("metrics", {})
    vm = voltage.get("metrics", {})

    violations: List[str] = []
    warnings: List[str] = []

    current_pm = float(cm.get("phase_margin_deg", 999.0))
    current_gm = float(cm.get("gain_margin_db", 999.0))
    voltage_pm = float(vm.get("phase_margin_deg", 999.0))
    voltage_gm = float(vm.get("gain_margin_db", 999.0))
    voltage_fc = float(vm.get("crossover_hz", 0.0))

    if current_pm < 45.0:
        violations.append(f"Current-loop phase margin too low: {current_pm:.2f}° < 45°.")
    if voltage_pm < 45.0:
        violations.append(f"Voltage-loop phase margin too low: {voltage_pm:.2f}° < 45°.")
    if current_gm <= 0.0:
        violations.append(f"Current-loop gain margin not positive: {current_gm:.2f} dB.")
    if voltage_gm <= 0.0:
        violations.append(f"Voltage-loop gain margin not positive: {voltage_gm:.2f} dB.")
    if voltage_fc > 20.0:
        violations.append(f"Voltage-loop crossover too high: {voltage_fc:.2f} Hz > 20 Hz safe ceiling.")

    if float(cm.get("overshoot_percent", 0.0)) > 25.0:
        warnings.append("Current-loop overshoot is high.")
    if float(vm.get("overshoot_percent", 0.0)) > 20.0:
        warnings.append("Voltage-loop overshoot is high.")

    allowed = len(violations) == 0
    return {
        "allowed": allowed,
        "violations": violations,
        "warnings": warnings,
        "explanation": (
            "Retuning request is within guardrail limits."
            if allowed else
            "Retuning request rejected because one or more guardrail limits were violated."
        ),
    }
