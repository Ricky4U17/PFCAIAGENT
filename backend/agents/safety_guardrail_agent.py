"""
safety_guardrail_agent.py — DEPRECATED (I-7). Not wired into graph.build_graph().
Active guardrail is guardrail_v2_agent.node_guardrail_v2_advisory.
Retained only for legacy test compatibility. Remove when all callers migrated.
"""
from __future__ import annotations
import warnings
from typing import Dict, Any
from app.engines.guardrail_engine import evaluate_tuning_guardrails


def node_safety_guardrail(state: Dict[str, Any]) -> Dict[str, Any]:
    warnings.warn(
        "node_safety_guardrail is deprecated; use node_guardrail_v2_advisory instead.",
        DeprecationWarning, stacklevel=2,
    )
    result = evaluate_tuning_guardrails(state.get("state_space_data", {}))
    out = {"guardrail_result": result}
    if not result["allowed"]:
        out["human_feedback"] = {"status": "guardrail_blocked",
                                  "reason": result["explanation"],
                                  "violations": result["violations"]}
    return out
