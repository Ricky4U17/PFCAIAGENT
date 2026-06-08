from __future__ import annotations
from typing import Dict, Any
from app.state import ProjectState


def build_initial_state(project_id: str, intake: Dict[str, Any]) -> ProjectState:
    design_defaults: Dict[str, Any] = {
        "L":                   235e-6,
        "fsw":                 70000.0,
        "ripple_ratio_target": 0.09493,
        "Cout":                2200e-6,
        # eff intentionally absent — derived from efficiency_target_percent at runtime.
    }
    return {
        "project_id":              project_id,
        "mode":                    "mode_a",
        "intake":                  intake,
        "selected_topology":       None,
        "selected_mode":           None,          # MA-8 fix: seeded explicitly
        "controller_strategy":     {},
        "selected_controller":     None,
        "topology_ranking":        [],
        "topology_recommendation": {},
        "mode_scores":             [],
        "topology_scores":         [],
        "topology_specific_inputs":  {},          # MA-8 fix: seeded explicitly
        "mode_a_validation_errors":  [],          # MA-8 fix: seeded explicitly (MA-2)
        "current_step":            None,
        "pending_step":            None,
        "last_completed_step":     None,
        "step_results":            {},
        "state_space_data":        {},
        "approved_tuning":         {},
        "control_loop_results":    {},
        "thermal_results":         {},
        "compliance_results":      {},
        "protection_results":      {},
        "vendor_candidates":       {},
        "emi_filter_data":         {},
        "emi_constraints":         {},
        "magnetic_design_data":    {},
        "thermal_status":          None,
        "thermal_loopback_count":  0,
        "guardrail_hard_stop":     False,
        "graph_artifacts":         {},
        "simulation_artifacts":    {},
        "hardware_artifacts":      {},
        "educator_output":         {},
        "tradeoff_output":         {},
        "report_sections":         {},
        "decision_log":            [],
        "human_feedback":          {},
        "errors":                  [],
        "design_defaults":         design_defaults,
    }


def apply_feedback(state: ProjectState, feedback: Dict[str, Any]) -> ProjectState:
    state["human_feedback"] = feedback or {}
    return state
