from __future__ import annotations
from typing import Any, Dict
from app.engines.guardrails.aggregator import evaluate_guardrail_v2

def node_guardrail_v2_advisory(state: Dict[str, Any]) -> Dict[str, Any]:
    result = evaluate_guardrail_v2(state)

    legacy_errors = list(result["violations"])
    if result["missing_inputs"]:
        legacy_errors.append(
            "Guardrail v2 incomplete due to missing inputs: " + ", ".join(result["missing_inputs"])
        )

    out = {
        "guardrail_v2_results": result,
        "safety_guardrail_data": {
            "passed": result["status"] == "passed",
            "errors": legacy_errors,
            "status": result["status"],
        },
        "hitl_required": bool(result["hard_stop"]),
        "reflection_log": state.get("reflection_log", []) + legacy_errors,
    }

    if result["hard_stop"] and result["blocking_enabled"]:
        out["human_feedback"] = {
            "status": "guardrail_blocked",
            "reason": result["explanation"],
            "violations": result["violations"],
            "missing_inputs": result["missing_inputs"],
        }

    return out
