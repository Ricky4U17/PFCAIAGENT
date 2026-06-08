"""
graph.py — Phase 3 hardened.  All 12 issues corrected:
I-1  Terminal routing: pending_step="finalize" (not None) at last step.
I-2  Thermal loopback: capped at THERMAL_LOOPBACK_LIMIT; stale steps cleared.
I-3  Guardrail blocked: guardrail_hard_stop written to state; mode_b_hitl checks first.
I-4  Disabled advisory auto-advance: ADVISORY_FLAG_MAP + mode_b_hitl fast-path.
I-5  Design defaults: eff from intake.efficiency_target_percent; others from design_defaults.
I-6  Report sections: structured dicts, serialised at export only.
I-7  Deprecated safety_guardrail_agent: not imported or referenced here.
I-8  SpiceBackend protocol: simulation advisory uses stable swap interface.
I-9  CAD thermal keys: reads thermal_data nested dict correctly.
I-10 Magnetic FEA fallback: uses magnetic_design_data when v2 disabled.
I-11 ProjectState TypedDict: all fields declared in state.py.
I-12 latest_workflow.md: updated to 25-step Phase 3 sequence.
"""
from __future__ import annotations
import os
from langgraph.graph import StateGraph, END

from app.state import ProjectState
from app.intake.topology_selector import select_topology
from app.engines.interleaved_ccm import run_interleaved_ccm_step
from app.engines.control_loops import design_control_loops
from app.engines.pdf_pwm_ripple import reconstruct_piecewise_pwm_ripple
from app.agents.controller_selection_agent import build_controller_strategy
from app.agents.state_space_agent import build_state_space_from_state
from app.agents.protection_compliance_agent import node_protection_compliance
from app.agents.magnetic_design_agent import node_magnetic_design
from app.agents.emi_filter_agent import node_emi_filter
from app.agents.bidirectional_thermal_agent import node_bidirectional_thermal
from app.agents.vendor_scout_agent import scout_vendors
from app.agents.graph_agent import generate_design_graphs
from app.agents.educator_agent import build_educator_response
from app.agents.tradeoff_agent import build_tradeoff_summary
from app.agents.guardrail_v2_agent import node_guardrail_v2_advisory
from app.agents.supply_chain_agent import node_supply_chain_advisory
from app.agents.magnetic_design_v2_agent import node_magnetic_design_v2_advisory
from app.agents.simulation_verification_agent import node_closed_loop_simulation_advisory
from app.agents.layout_parasitics_agent import node_layout_parasitics_advisory
from app.agents.firmware_generation_agent import node_firmware_generation_advisory
from app.agents.reliability_mtbf_agent import node_reliability_mtbf_advisory
from app.agents.pcb_floorplanning_agent import node_pcb_floorplanning_advisory
from app.agents.cad_thermal_integration_agent import node_cad_thermal_integration_advisory
from app.agents.magnetic_fea_agent import node_magnetic_fea_advisory
from app.workflow.phase1_helpers import ensure_phase1_state_defaults, phase1_enabled
from app.workflow.mode_a_validation import validate_topology_specific_inputs
from app.intake.compat import app_line_frequency_hz, app_efficiency_fraction
from app.exporters.simplis_exporter import generate_simplis_netlist
from app.exporters.altium_exporter import generate_altium_design_stub
from app.services.report_helpers import build_topology_section, build_step_section

GENERATED_DIR = "generated_artifacts"

MODE_B_SEQUENCE = [
    "input_processing", "duty_and_ripple", "inductor_sizing", "worst_case_angle",
    "waveform_reconstruction", "magnetic_design", "magnetic_design_v2_advisory",
    "magnetic_fea_advisory", "protection_compliance", "emi_filter",
    "layout_parasitics_advisory", "control_loops", "state_space_analysis",
    "guardrail_v2_advisory", "bidirectional_thermal", "cad_thermal_integration_advisory",
    "vendor_scout", "supply_chain_advisory", "reliability_mtbf_advisory",
    "design_graphs", "simulation_export", "closed_loop_simulation_advisory",
    "firmware_generation_advisory", "pcb_floorplanning_advisory", "altium_export",
]

# I-4: advisory → feature-flag map; disabled advisories auto-advance without HITL cost.
ADVISORY_FLAG_MAP: dict = {
    "magnetic_design_v2_advisory":       "enable_magnetic_design_v2",
    "magnetic_fea_advisory":             "enable_magnetic_fea_agent",
    "layout_parasitics_advisory":        "enable_layout_parasitics_agent",
    "guardrail_v2_advisory":             "enable_guardrail_v2",
    "cad_thermal_integration_advisory":  "enable_cad_thermal_integration_agent",
    "supply_chain_advisory":             "enable_supply_chain_agent",
    "reliability_mtbf_advisory":         "enable_reliability_mtbf_agent",
    "closed_loop_simulation_advisory":   "enable_closed_loop_simulation",
    "firmware_generation_advisory":      "enable_firmware_generation_agent",
    "pcb_floorplanning_advisory":        "enable_pcb_floorplanning_agent",
}

# I-2: max thermal loopback retries before hard-pause.
THERMAL_LOOPBACK_LIMIT = 3

# I-2: steps that must be invalidated when thermal loopback restarts inductor_sizing.
# Includes all Phase 3 steps that sit downstream of inductor_sizing.
THERMAL_LOOPBACK_STALE_STEPS = [
    "worst_case_angle", "waveform_reconstruction", "magnetic_design",
    "magnetic_design_v2_advisory", "magnetic_fea_advisory",
    "protection_compliance", "emi_filter", "layout_parasitics_advisory",
]

WAIT_TOPOLOGY   = "awaiting_topology_approval"
WAIT_CONTROLLER = "awaiting_controller_approval"
WAIT_MODE_B     = "awaiting_mode_b_approval"
WAIT_TOPOLOGY_SPECIFIC = "awaiting_topology_specific_inputs"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_step_tradeoff_and_educator(state, step_name, results,
                                       verification=None, citations=None, options=None):
    verification = verification or {}
    citations    = citations    or []
    options      = options      or []
    tradeoff = build_tradeoff_summary(
        {"mode": "mode_b", "topology": state.get("selected_topology"),
         "current_step": step_name},
        options, citations,
    )
    state["tradeoff_output"] = tradeoff.model_dump()
    educator = build_educator_response(step_name, results, verification,
                                        state["tradeoff_output"], citations)
    state["educator_output"] = educator.model_dump()
    state.setdefault("step_results", {}).setdefault(step_name, {})
    if isinstance(results, dict):
        for k, v in results.items():
            state["step_results"][step_name][k] = v
    state["step_results"][step_name]["educator_output"] = state["educator_output"]
    state["step_results"][step_name]["tradeoff_output"] = state["tradeoff_output"]
    return state


# I-5: eff from intake.efficiency_target_percent; other defaults from design_defaults.
def _design_inputs(state):
    app     = state["intake"]["application"]
    thermal = state["intake"]["thermal"]
    overrides = state.get("human_feedback", {}).get("overrides", {})
    defaults  = state.get("design_defaults", {})
    topo_inputs = state.get("topology_specific_inputs", {})
    # MA-3 fix: use compat helpers instead of ad-hoc key checks.
    eff_default  = app_efficiency_fraction(app, default=float(defaults.get("eff", 0.945)))
    line_freq    = app_line_frequency_hz(app)
    fsw_default  = topo_inputs.get("recommended_frequency_hz", float(defaults.get("fsw", 70000.0)))
    ripple_default = topo_inputs.get("default_crest_ripple_ratio", float(defaults.get("ripple_ratio_target", 0.09493)))
    return {
        "Vac":  app["vin_rms_min"],
        "Vout": app["output_bus_voltage_v"],
        "Pout": app.get("output_power_w_low_line", app["output_power_w_nom"]),
        "eff":  overrides.get("eff",  eff_default),
        "pf":   app["power_factor_target"],
        "L":    overrides.get("L",    float(defaults.get("L",    235e-6))),
        "fsw":  overrides.get("fsw",  float(fsw_default)),
        "line_freq":           line_freq,
        "ripple_ratio_target": overrides.get("ripple_ratio_target", float(ripple_default)),
        "Cout": overrides.get("Cout", float(defaults.get("Cout", 2200e-6))),
        "cooling_type": thermal["cooling_type"],
    }


def _safe_node(fn, step_name, state):
    """Wrap any node body; catches exceptions and appends to state['errors']."""
    try:
        return fn(state)
    except Exception as exc:
        state.setdefault("errors", []).append(f"{step_name}: {exc}")
        return state


# ---------------------------------------------------------------------------
# Mode A nodes
# ---------------------------------------------------------------------------

def intake_node(state):
    state = ensure_phase1_state_defaults(state)
    state["mode"] = "mode_a"
    return state



def topology_selection_node(state):
    selection = select_topology(state["intake"])
    state["topology_recommendation"] = selection
    state["topology_ranking"]        = selection["ranking"]
    state["mode_scores"]             = selection.get("mode_scores", [])
    state["topology_scores"]         = selection.get("topology_scores", [])
    state["report_sections"]["topology_selection"] = build_topology_section(selection)
    state["current_step"] = "topology_selection"
    return state


def topology_hitl_node(state):
    # Auto-advance if topology was previously approved AND feedback is not targeting this gate.
    if state.get("selected_topology") and state.get("waiting_at") != WAIT_TOPOLOGY:
        state["pending_step"] = "topology_specific_intake"
        return state
    feedback = state.get("human_feedback", {})
    if feedback.get("approved", False):
        chosen_topology = feedback.get("selected_topology") or state["topology_recommendation"]["recommended_topology"]
        ranking = state["topology_recommendation"].get("ranking", [])
        chosen = next((r for r in ranking if r.get("topology") == chosen_topology), None)
        if chosen is None:
            chosen = state["topology_recommendation"].get("top_3", [{}])[0]
            chosen_topology = chosen.get("topology", chosen_topology)
        state["selected_topology"] = chosen_topology
        state["selected_mode"] = feedback.get("selected_mode") or chosen.get("mode") or state["topology_recommendation"].get("recommended_mode")
        state["topology_specific_inputs"] = chosen.get("mini_intake_defaults", {})
        state["pending_step"]        = "topology_specific_intake"
        state["last_completed_step"] = "topology_selection"
        state["human_feedback"]      = {}   # consumed; clear so downstream gates don't see it
        state.setdefault("decision_log", []).append({
            "stage": "mode_a_topology_selection",
            "selected_topology": state["selected_topology"],
            "selected_mode": state["selected_mode"],
            "source": "recommended_top_3" if not feedback.get("selected_topology") else "designer_override",
        })
    else:
        state["pending_step"] = WAIT_TOPOLOGY
    return state


def route_after_topology_hitl(state):
    return state.get("pending_step", WAIT_TOPOLOGY)



def topology_specific_intake_node(state):
    state["current_step"] = "topology_specific_intake"
    # Auto-advance if mini-intake was previously completed AND feedback is not targeting this gate.
    if state.get("last_completed_step") == "topology_specific_intake" and state.get("waiting_at") != WAIT_TOPOLOGY_SPECIFIC:
        state["pending_step"] = "controller_selection"
        return state
    defaults = dict(state.get("topology_specific_inputs", {}))
    feedback = state.get("human_feedback", {})
    if feedback.get("approved", False):
        merged = dict(defaults)
        if "switching_frequency_style" in feedback:
            merged["switching_frequency_style"] = feedback["switching_frequency_style"]
            # MA-6 / validation: if style is being explicitly set to "fixed" but the user
            # did NOT supply a frequency value, clear the inherited default so validation
            # correctly requires the user to provide one.
            if feedback["switching_frequency_style"] == "fixed" and "switching_frequency_hz" not in feedback:
                merged.pop("recommended_frequency_hz", None)
        if "switching_frequency_hz" in feedback:
            merged["recommended_frequency_hz"] = feedback["switching_frequency_hz"]
        if "switching_frequency_range_hz" in feedback:
            merged["recommended_frequency_range_hz"] = feedback["switching_frequency_range_hz"]
        # MA-4 fix: apply crest_ripple_ratio for ALL modes, not just CCM.
        # CCM: user-editable (0.05–0.6). CrCM: locked to 2.0. DCM: must be >2.0.
        # Validation enforces the per-mode constraints; we always pass the value through.
        if "crest_ripple_ratio" in feedback:
            merged["default_crest_ripple_ratio"] = feedback["crest_ripple_ratio"]
        ok, errors = validate_topology_specific_inputs(state.get("selected_mode"), merged)
        state["topology_specific_inputs"] = merged
        if ok:
            state["pending_step"] = "controller_selection"
            state["last_completed_step"] = "topology_specific_intake"
            state["human_feedback"] = {}    # consumed; clear so downstream gates don't see it
            # MA-6 fix: clear stale validation errors on successful submission.
            state["mode_a_validation_errors"] = []
            state.setdefault("decision_log", []).append({"stage": "mode_a_post_selection_mini_intake", "topology_specific_inputs": merged})
        else:
            state["pending_step"] = WAIT_TOPOLOGY_SPECIFIC
            state["mode_a_validation_errors"] = errors
    else:
        state["pending_step"] = WAIT_TOPOLOGY_SPECIFIC
    return state

def route_after_topology_specific_intake(state):

    return state.get("pending_step", WAIT_TOPOLOGY_SPECIFIC)


def controller_selection_node(state):
    state["controller_strategy"] = build_controller_strategy(state)
    state["current_step"] = "controller_selection"
    return state


def controller_selection_hitl_node(state):
    # Auto-advance if controller was already approved AND feedback is not targeting this gate.
    if state.get("mode") == "mode_b" and state.get("waiting_at") != WAIT_CONTROLLER:
        state["pending_step"] = MODE_B_SEQUENCE[0]
        return state
    feedback = state.get("human_feedback", {})
    if feedback.get("approved", False):
        chosen_mode = (feedback.get("controller_mode")
                       or state["controller_strategy"]["recommended_controller_mode"])
        chosen_name = feedback.get("controller_name") or "Recommended Controller"
        state["controller_strategy"]["selected_mode"] = chosen_mode
        state["selected_controller"] = {"name": chosen_name, "type": chosen_mode,
                                         "reason": "Selected by designer."}
        state["mode"]                = "mode_b"
        state["pending_step"]        = MODE_B_SEQUENCE[0]
        state["last_completed_step"] = "controller_selection"
        state["human_feedback"]      = {}   # consumed; clear so mode_b_hitl doesn't auto-advance
    else:
        state["pending_step"] = WAIT_CONTROLLER
    return state


def route_after_controller_selection_hitl(state):
    return state.get("pending_step", WAIT_CONTROLLER)


def wait_topology_node(state):   state["current_step"] = WAIT_TOPOLOGY;   state["waiting_at"] = WAIT_TOPOLOGY;   return state
def wait_topology_specific_node(state): state["current_step"] = WAIT_TOPOLOGY_SPECIFIC; state["waiting_at"] = WAIT_TOPOLOGY_SPECIFIC; return state
def wait_controller_node(state): state["current_step"] = WAIT_CONTROLLER; state["waiting_at"] = WAIT_CONTROLLER; return state
def wait_mode_b_node(state):     state["current_step"] = WAIT_MODE_B;     state["waiting_at"] = WAIT_MODE_B;     return state


# ---------------------------------------------------------------------------
# Mode B core step nodes
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------

def _step_node_from_interleaved(name):
    def fn(state):
        try:
            result = run_interleaved_ccm_step(name, _design_inputs(state))
        except Exception as exc:
            state.setdefault("errors", []).append(f"{name}: {exc}")
            result = {"error": str(exc)}
        state["step_results"][name]    = result
        state["report_sections"][name] = build_step_section(name, result)
        state["current_step"] = name
        return _build_step_tradeoff_and_educator(state, name, result)
    return fn


input_processing_node = _step_node_from_interleaved("input_processing")
duty_and_ripple_node  = _step_node_from_interleaved("duty_and_ripple")
inductor_sizing_node  = _step_node_from_interleaved("inductor_sizing")
worst_case_angle_node = _step_node_from_interleaved("worst_case_angle")


def waveform_reconstruction_node(state):
    i = _design_inputs(state)
    try:
        result = reconstruct_piecewise_pwm_ripple(
            i["Vac"], i["Vout"], i["Pout"], i["eff"], i["pf"],
            i["L"], i["fsw"], i["line_freq"]
        )
    except Exception as exc:
        state.setdefault("errors", []).append(f"waveform_reconstruction: {exc}")
        result = {"crest": {}, "error": str(exc)}
    state["step_results"]["waveform_reconstruction"] = result
    state["report_sections"]["waveform_reconstruction"] = build_step_section(
        "Waveform Reconstruction", {"crest": result.get("crest", {})}
    )
    state["current_step"] = "waveform_reconstruction"
    return _build_step_tradeoff_and_educator(state, "waveform_reconstruction",
                                              {"crest": result.get("crest", {})})


def magnetic_design_node(state):
    try:
        result = node_magnetic_design(state)
    except Exception as exc:
        state.setdefault("errors", []).append(f"magnetic_design: {exc}")
        result = {"error": str(exc)}
    state["magnetic_design_data"]            = result.get("magnetic_design_data", {})
    state["step_results"]["magnetic_design"] = result
    state["current_step"] = "magnetic_design"
    return _build_step_tradeoff_and_educator(state, "magnetic_design", result)


def protection_node(state):
    try:
        result = node_protection_compliance(state)
    except Exception as exc:
        state.setdefault("errors", []).append(f"protection_compliance: {exc}")
        result = {"error": str(exc)}
    state["protection_results"]                    = result.get("protection_results", {})
    state["step_results"]["protection_compliance"] = result
    state["current_step"] = "protection_compliance"
    return _build_step_tradeoff_and_educator(state, "protection_compliance", result)


def emi_filter_node(state):
    try:
        result = node_emi_filter(state)
    except Exception as exc:
        state.setdefault("errors", []).append(f"emi_filter: {exc}")
        result = {"error": str(exc)}
    state["emi_filter_data"]             = result.get("emi_filter_data", {})
    state["emi_constraints"]             = result.get("emi_constraints", {})
    state["step_results"]["emi_filter"]  = result
    state["current_step"] = "emi_filter"
    return _build_step_tradeoff_and_educator(state, "emi_filter", result)


def control_loops_node(state):
    out_dir = os.path.join(GENERATED_DIR, state.get("project_id", "project"), "control_loops")
    try:
        result = design_control_loops(_design_inputs(state), out_dir)
    except Exception as exc:
        state.setdefault("errors", []).append(f"control_loops: {exc}")
        result = {"current_loop": {"bode_plot": ""}, "voltage_loop": {"bode_plot": ""}, "error": str(exc)}
    state["control_loop_results"] = result
    state.setdefault("graph_artifacts", {})
    state["graph_artifacts"]["current_loop_bode"] = result.get("current_loop", {}).get("bode_plot", "")
    state["graph_artifacts"]["voltage_loop_bode"] = result.get("voltage_loop", {}).get("bode_plot", "")
    state["step_results"]["control_loops"] = result
    state["current_step"] = "control_loops"
    return _build_step_tradeoff_and_educator(state, "control_loops", result)


def state_space_analysis_node(state):
    try:
        result = build_state_space_from_state(state)
    except Exception as exc:
        state.setdefault("errors", []).append(f"state_space_analysis: {exc}")
        result = {"operating_point": {}, "current_loop": {"suggestion": {}},
                  "voltage_loop": {"suggestion": {}}}
    state["state_space_data"]                     = result
    state["step_results"]["state_space_analysis"] = result
    state["current_step"] = "state_space_analysis"
    return _build_step_tradeoff_and_educator(state, "state_space_analysis", {
        "controller_strategy":     state.get("controller_strategy", {}),
        "selected_controller":     state.get("selected_controller", {}),
        "operating_point":         result.get("operating_point", {}),
        "current_loop_suggestion": result.get("current_loop", {}).get("suggestion", {}),
        "voltage_loop_suggestion": result.get("voltage_loop", {}).get("suggestion", {}),
    })


def bidirectional_thermal_node(state):
    try:
        result = node_bidirectional_thermal(state)
    except Exception as exc:
        state.setdefault("errors", []).append(f"bidirectional_thermal: {exc}")
        result = {"thermal_status": "error", "error": str(exc)}
    state["thermal_results"]                        = result
    state["thermal_status"]                         = result.get("thermal_status")
    state["step_results"]["bidirectional_thermal"]  = result
    state["current_step"] = "bidirectional_thermal"
    return _build_step_tradeoff_and_educator(state, "bidirectional_thermal", result)


def vendor_scout_node(state):
    try:
        result = scout_vendors(state)
    except Exception as exc:
        state.setdefault("errors", []).append(f"vendor_scout: {exc}")
        result = {"error": str(exc)}
    state["vendor_candidates"]            = result
    state["step_results"]["vendor_scout"] = result
    state["current_step"] = "vendor_scout"
    return _build_step_tradeoff_and_educator(state, "vendor_scout", result)


def design_graphs_node(state):
    try:
        result = generate_design_graphs(state)
    except Exception as exc:
        state.setdefault("errors", []).append(f"design_graphs: {exc}")
        result = {"error": str(exc)}
    state.setdefault("graph_artifacts", {}).update(result)
    state["step_results"]["design_graphs"] = result
    state["current_step"] = "design_graphs"
    return _build_step_tradeoff_and_educator(state, "design_graphs", result)


def simulation_export_node(state):
    try:
        result = {"simplis_netlist": generate_simplis_netlist(state)}
    except Exception as exc:
        state.setdefault("errors", []).append(f"simulation_export: {exc}")
        result = {"simplis_netlist": None, "error": str(exc)}
    state["simulation_artifacts"]              = result
    state["step_results"]["simulation_export"] = result
    state["current_step"] = "simulation_export"
    return _build_step_tradeoff_and_educator(state, "simulation_export", result)


def altium_export_node(state):
    try:
        result = generate_altium_design_stub(state)
    except Exception as exc:
        state.setdefault("errors", []).append(f"altium_export: {exc}")
        result = {"error": str(exc)}
    state["hardware_artifacts"]            = result
    state["step_results"]["altium_export"] = result
    state["current_step"] = "altium_export"
    return _build_step_tradeoff_and_educator(state, "altium_export", result)


# ---------------------------------------------------------------------------
# Advisory nodes (all: I-4 auto-advance when flag off; try/except; I-8 sim)
# ---------------------------------------------------------------------------

def _advisory_node(step_name, flag_name, run_fn, result_key, state_key):
    """Factory: creates a standard advisory node with all guards applied."""
    def fn(state):
        result = {"feature": step_name, "enabled": False, "status": "disabled",
                  "blocking": False, "details": {}}
        if phase1_enabled(state, flag_name):
            try:
                result = run_fn(state).get(result_key, result)
            except Exception as exc:
                state.setdefault("errors", []).append(f"{step_name}: {exc}")
                result = {"feature": step_name, "enabled": True, "status": "error",
                          "blocking": False, "details": {"error": str(exc)}}
        state[state_key]                    = result
        state["step_results"][step_name]    = result
        state["current_step"]               = step_name
        return _build_step_tradeoff_and_educator(state, step_name, result)
    fn.__name__ = f"{step_name}_node"
    return fn


magnetic_design_v2_advisory_node = _advisory_node(
    "magnetic_design_v2_advisory", "enable_magnetic_design_v2",
    node_magnetic_design_v2_advisory, "magnetic_design_v2_results",
    "magnetic_design_v2_results",
)
magnetic_fea_advisory_node = _advisory_node(
    "magnetic_fea_advisory", "enable_magnetic_fea_agent",
    node_magnetic_fea_advisory, "magnetic_fea_results",
    "magnetic_fea_results",
)
layout_parasitics_advisory_node = _advisory_node(
    "layout_parasitics_advisory", "enable_layout_parasitics_agent",
    node_layout_parasitics_advisory, "layout_parasitics_results",
    "layout_parasitics_results",
)
supply_chain_advisory_node = _advisory_node(
    "supply_chain_advisory", "enable_supply_chain_agent",
    node_supply_chain_advisory, "supply_chain_results",
    "supply_chain_results",
)
reliability_mtbf_advisory_node = _advisory_node(
    "reliability_mtbf_advisory", "enable_reliability_mtbf_agent",
    node_reliability_mtbf_advisory, "reliability_mtbf_results",
    "reliability_mtbf_results",
)
cad_thermal_integration_advisory_node = _advisory_node(
    "cad_thermal_integration_advisory", "enable_cad_thermal_integration_agent",
    node_cad_thermal_integration_advisory, "cad_thermal_integration_results",
    "cad_thermal_integration_results",
)
pcb_floorplanning_advisory_node = _advisory_node(
    "pcb_floorplanning_advisory", "enable_pcb_floorplanning_agent",
    node_pcb_floorplanning_advisory, "pcb_floorplanning_results",
    "pcb_floorplanning_results",
)
firmware_generation_advisory_node = _advisory_node(
    "firmware_generation_advisory", "enable_firmware_generation_agent",
    node_firmware_generation_advisory, "firmware_generation_results",
    "firmware_generation_results",
)


def closed_loop_simulation_advisory_node(state):
    """I-8: uses SpiceBackend protocol. Auto-advances when flag off (I-4)."""
    result = {"feature": "closed_loop_simulation", "enabled": False,
              "status": "disabled", "blocking": False, "details": {}}
    if phase1_enabled(state, "enable_closed_loop_simulation"):
        try:
            result = node_closed_loop_simulation_advisory(state).get(
                "simulation_verification_results", result
            )
        except Exception as exc:
            state.setdefault("errors", []).append(f"closed_loop_simulation_advisory: {exc}")
            result = {"feature": "closed_loop_simulation", "enabled": True,
                      "status": "error", "blocking": False, "details": {"error": str(exc)}}
    state["simulation_verification_results"]                  = result
    state["step_results"]["closed_loop_simulation_advisory"]  = result
    state["current_step"] = "closed_loop_simulation_advisory"
    return _build_step_tradeoff_and_educator(state, "closed_loop_simulation_advisory", result)


def guardrail_v2_advisory_node(state):
    """I-3: writes guardrail_hard_stop and injects guardrail_blocked into human_feedback."""
    result = {"feature": "guardrail_v2", "enabled": False, "status": "disabled",
              "blocking": False, "details": {}}
    state["guardrail_hard_stop"] = False
    if phase1_enabled(state, "enable_guardrail_v2"):
        try:
            node_result = node_guardrail_v2_advisory(state)
            result      = node_result.get("guardrail_v2_results", result)
            state["safety_guardrail_data"] = node_result.get("safety_guardrail_data", {})
            state["reflection_log"]        = node_result.get(
                "reflection_log", state.get("reflection_log", [])
            )
            state["guardrail_hard_stop"] = bool(result.get("hard_stop", False))
            if state["guardrail_hard_stop"] and result.get("blocking_enabled", False):
                state["human_feedback"] = {
                    "status":       "guardrail_blocked",
                    "reason":       result.get("explanation", "Guardrail violation."),
                    "violations":   result.get("violations", []),
                    "missing_inputs": result.get("missing_inputs", []),
                }
        except Exception as exc:
            state.setdefault("errors", []).append(f"guardrail_v2_advisory: {exc}")
            result = {"feature": "guardrail_v2", "enabled": True, "status": "error",
                      "blocking": False, "details": {"error": str(exc)}}
    state["guardrail_v2_results"]                  = result
    state["step_results"]["guardrail_v2_advisory"] = result
    state["current_step"] = "guardrail_v2_advisory"
    return _build_step_tradeoff_and_educator(state, "guardrail_v2_advisory", result)


# ---------------------------------------------------------------------------
# HITL router — all 4 primary fixes converge here
# ---------------------------------------------------------------------------

def mode_b_hitl_node(state):
    """
    I-1  Returns 'finalize' at terminal step (not None).
    I-2  Caps thermal loopback; clears stale steps on retry.
    I-3  Checks guardrail_blocked before approved branch.
    I-4  Auto-advances disabled advisories without a human round-trip.
    """
    feedback = state.get("human_feedback", {})
    current  = state.get("current_step")
    state["last_completed_step"] = current

    # I-3: guardrail hard-stop takes priority.
    if feedback.get("status") == "guardrail_blocked":
        state["pending_step"] = WAIT_MODE_B
        return state

    # I-4: disabled advisory — skip HITL entirely.
    flag_name = ADVISORY_FLAG_MAP.get(current)
    if flag_name and not phase1_enabled(state, flag_name):
        idx = MODE_B_SEQUENCE.index(current)
        state["pending_step"] = "finalize" if idx >= len(MODE_B_SEQUENCE) - 1 \
                                 else MODE_B_SEQUENCE[idx + 1]
        return state

    if feedback.get("approved", False):
        # I-2: thermal loopback guard.
        if current == "bidirectional_thermal" and state.get("thermal_status") == "failed":
            count = state.get("thermal_loopback_count", 0) + 1
            state["thermal_loopback_count"] = count
            if count >= THERMAL_LOOPBACK_LIMIT:
                state.setdefault("errors", []).append(
                    f"Thermal loopback limit ({THERMAL_LOOPBACK_LIMIT}) reached — "
                    "manual intervention required."
                )
                state["pending_step"] = WAIT_MODE_B
            else:
                # Clear stale steps so they recompute from new L / fsw.
                for stale in THERMAL_LOOPBACK_STALE_STEPS:
                    state["step_results"].pop(stale, None)
                    state["report_sections"].pop(stale, None)
                state["pending_step"] = "inductor_sizing"
        else:
            idx = MODE_B_SEQUENCE.index(current)
            # I-1: 'finalize' at terminal step instead of None.
            state["pending_step"] = "finalize" if idx >= len(MODE_B_SEQUENCE) - 1 \
                                     else MODE_B_SEQUENCE[idx + 1]
            state["human_feedback"] = {}    # consumed; clear so next mode_b_hitl waits
    elif feedback.get("repeat_step", False):
        state["pending_step"] = current
    else:
        state["pending_step"] = WAIT_MODE_B

    return state


def route_after_mode_b_hitl(state):
    return state.get("pending_step", WAIT_MODE_B)


def finalize_node(state):
    state["mode"]         = "final"
    state["current_step"] = "final"
    state["pending_step"] = None
    return state


# ---------------------------------------------------------------------------
# Graph assembly
# ---------------------------------------------------------------------------

def build_graph():
    g = StateGraph(ProjectState)
    nodes = [
        ("intake_node",                     intake_node),
        ("topology_selection",              topology_selection_node),
        ("topology_hitl",                   topology_hitl_node),
        ("topology_specific_intake",        topology_specific_intake_node),
        ("controller_selection",            controller_selection_node),
        ("controller_selection_hitl",       controller_selection_hitl_node),
        (WAIT_TOPOLOGY,                     wait_topology_node),
        (WAIT_TOPOLOGY_SPECIFIC,            wait_topology_specific_node),
        (WAIT_CONTROLLER,                   wait_controller_node),
        (WAIT_MODE_B,                       wait_mode_b_node),
        ("input_processing",                input_processing_node),
        ("duty_and_ripple",                 duty_and_ripple_node),
        ("inductor_sizing",                 inductor_sizing_node),
        ("worst_case_angle",                worst_case_angle_node),
        ("waveform_reconstruction",         waveform_reconstruction_node),
        ("magnetic_design",                 magnetic_design_node),
        ("magnetic_design_v2_advisory",     magnetic_design_v2_advisory_node),
        ("magnetic_fea_advisory",           magnetic_fea_advisory_node),
        ("protection_compliance",           protection_node),
        ("emi_filter",                      emi_filter_node),
        ("layout_parasitics_advisory",      layout_parasitics_advisory_node),
        ("control_loops",                   control_loops_node),
        ("state_space_analysis",            state_space_analysis_node),
        ("guardrail_v2_advisory",           guardrail_v2_advisory_node),
        ("bidirectional_thermal",           bidirectional_thermal_node),
        ("cad_thermal_integration_advisory",cad_thermal_integration_advisory_node),
        ("vendor_scout",                    vendor_scout_node),
        ("supply_chain_advisory",           supply_chain_advisory_node),
        ("reliability_mtbf_advisory",       reliability_mtbf_advisory_node),
        ("design_graphs",                   design_graphs_node),
        ("simulation_export",               simulation_export_node),
        ("closed_loop_simulation_advisory", closed_loop_simulation_advisory_node),
        ("firmware_generation_advisory",    firmware_generation_advisory_node),
        ("pcb_floorplanning_advisory",      pcb_floorplanning_advisory_node),
        ("altium_export",                   altium_export_node),
        ("mode_b_hitl",                     mode_b_hitl_node),
        ("finalize",                        finalize_node),
    ]
    for name, node in nodes:
        g.add_node(name, node)

    g.set_entry_point("intake_node")
    g.add_edge("intake_node", "topology_selection")
    g.add_edge("topology_selection", "topology_hitl")
    # MA-1 fix: include "topology_specific_intake" — topology_hitl routes here when
    # approved. Previously only "controller_selection" was in the map, causing a
    # LangGraph KeyError on every topology approval since pending_step is set to
    # "topology_specific_intake", not "controller_selection".
    g.add_conditional_edges(
        "topology_hitl", route_after_topology_hitl,
        {
            "topology_specific_intake": "topology_specific_intake",
            WAIT_TOPOLOGY: WAIT_TOPOLOGY,
        },
    )
    g.add_conditional_edges("topology_specific_intake", route_after_topology_specific_intake, {"controller_selection":"controller_selection", WAIT_TOPOLOGY_SPECIFIC:WAIT_TOPOLOGY_SPECIFIC})
    g.add_edge("controller_selection", "controller_selection_hitl")
    g.add_conditional_edges(
        "controller_selection_hitl", route_after_controller_selection_hitl,
        {"input_processing": "input_processing", WAIT_CONTROLLER: WAIT_CONTROLLER},
    )
    for name in MODE_B_SEQUENCE:
        g.add_edge(name, "mode_b_hitl")

    # I-1: route_map includes "finalize" — previously pending_step=None was returned
    # at altium_export and had no matching key, causing LangGraph to error.
    route_map = {name: name for name in MODE_B_SEQUENCE}
    route_map[WAIT_MODE_B] = WAIT_MODE_B
    route_map["finalize"]  = "finalize"
    g.add_conditional_edges("mode_b_hitl", route_after_mode_b_hitl, route_map)
    g.add_edge(WAIT_TOPOLOGY, END)
    g.add_edge(WAIT_TOPOLOGY_SPECIFIC, END)
    g.add_edge(WAIT_CONTROLLER, END)
    g.add_edge(WAIT_MODE_B, END)
    g.add_edge("finalize", END)
    return g.compile()
