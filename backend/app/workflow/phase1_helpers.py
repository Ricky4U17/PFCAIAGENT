from __future__ import annotations
from typing import Dict, Any
from app.config.feature_flags import FEATURE_FLAGS


def ensure_phase1_state_defaults(state: Dict[str, Any]) -> Dict[str, Any]:
    state.setdefault("schema_version", "1.3")
    state.setdefault("feature_flags",  FEATURE_FLAGS.model_dump())

    # Mode A new slots (MA-2, MA-8)
    state.setdefault("selected_mode",             None)
    state.setdefault("topology_specific_inputs",  {})
    state.setdefault("mode_a_validation_errors",  [])
    state.setdefault("mode_scores",               [])
    state.setdefault("topology_scores",           [])

    # Phase 1–3 advisory slots
    state.setdefault("guardrail_v2_results",            {})
    state.setdefault("supply_chain_results",            {})
    state.setdefault("magnetic_design_v2_results",      {})
    state.setdefault("simulation_verification_results", {})
    state.setdefault("layout_parasitics_results",   {})
    state.setdefault("firmware_generation_results", {})
    state.setdefault("reliability_mtbf_results",    {})
    state.setdefault("pcb_floorplanning_results",       {})
    state.setdefault("cad_thermal_integration_results", {})
    state.setdefault("magnetic_fea_results",            {})

    state.setdefault("thermal_loopback_count", 0)
    state.setdefault("guardrail_hard_stop",    False)
    state.setdefault("design_defaults", {
        "L": 235e-6, "fsw": 70000.0, "ripple_ratio_target": 0.09493, "Cout": 2200e-6,
    })
    state.setdefault("advisory_blocks", [])
    state.setdefault("rollout_notes",   [])
    state.setdefault("reflection_log",  [])
    state.setdefault("errors",          [])
    return state


def phase1_enabled(state: Dict[str, Any], flag_name: str) -> bool:
    flags = state.get("feature_flags") or FEATURE_FLAGS.model_dump()
    return bool(flags.get(flag_name, False))


def advisory_result(
    name: str, enabled: bool, status: str,
    details: Dict[str, Any] | None = None, blocking: bool = False,
) -> Dict[str, Any]:
    return {"feature": name, "enabled": enabled, "status": status,
            "blocking": blocking, "details": details or {}}
