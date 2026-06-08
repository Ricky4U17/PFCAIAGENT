from typing import Any, Dict, List, Optional, TypedDict


class ProjectState(TypedDict, total=False):
    # --- identity & versioning ---
    project_id:     str
    schema_version: str
    feature_flags:  Dict[str, Any]

    # --- mode ---
    mode: str

    # --- intake ---
    intake:            Dict[str, Any]
    selected_topology: Optional[str]
    selected_mode:     Optional[str]      # "ccm" | "crcm" | "dcm"

    # --- design defaults ---
    design_defaults: Dict[str, Any]

    # --- Mode A topology selection ---
    topology_ranking:        List[Dict[str, Any]]
    topology_recommendation: Dict[str, Any]
    mode_scores:             List[Dict[str, Any]]
    topology_scores:         List[Dict[str, Any]]

    # --- Mode A mini-intake (post-selection) ---
    topology_specific_inputs: Dict[str, Any]
    # MA-2 fix: declared so TypedDict and LangGraph validation are consistent.
    mode_a_validation_errors: List[str]

    # --- controller ---
    controller_strategy: Dict[str, Any]
    selected_controller: Optional[Dict[str, Any]]
    selected_controller_mode: Optional[str]    # "analog" | "digital"
    selected_channels:    Optional[int]         # 1 for single-phase, 2–4 for interleaved

    # --- step tracking ---
    current_step:        Optional[str]
    pending_step:        Optional[str]
    last_completed_step: Optional[str]
    waiting_at:          Optional[str]   # set by wait nodes; survives re-invoke to route feedback to the right gate
    step_results:        Dict[str, Any]

    # --- core engineering results ---
    state_space_data:     Dict[str, Any]
    approved_tuning:      Dict[str, Any]
    control_loop_results: Dict[str, Any]
    thermal_results:      Dict[str, Any]
    compliance_results:   Dict[str, Any]
    protection_results:   Dict[str, Any]
    vendor_candidates:    Dict[str, Any]
    emi_filter_data:      Dict[str, Any]
    emi_constraints:      Dict[str, Any]
    magnetic_design_data: Dict[str, Any]
    thermal_status:       Optional[str]

    # --- loopback guard ---
    thermal_loopback_count: int

    # --- guardrail hard-stop ---
    guardrail_hard_stop: bool

    # --- artifacts ---
    graph_artifacts:      Dict[str, str]
    simulation_artifacts: Dict[str, Any]
    hardware_artifacts:   Dict[str, Any]

    # --- LLM outputs ---
    educator_output: Dict[str, Any]
    tradeoff_output: Dict[str, Any]

    # --- report sections (structured dicts) ---
    report_sections: Dict[str, Any]

    # --- audit ---
    decision_log:   List[Dict[str, Any]]
    human_feedback: Dict[str, Any]
    errors:         List[str]

    # --- Phase 1 advisory results ---
    guardrail_v2_results:            Dict[str, Any]
    safety_guardrail_data:           Dict[str, Any]
    supply_chain_results:            Dict[str, Any]
    magnetic_design_v2_results:      Dict[str, Any]
    simulation_verification_results: Dict[str, Any]
    reflection_log:                  List[str]

    # --- Phase 2 advisory results ---
    layout_parasitics_results:   Dict[str, Any]
    firmware_generation_results: Dict[str, Any]
    reliability_mtbf_results:    Dict[str, Any]

    # --- Phase 3 advisory results ---
    pcb_floorplanning_results:       Dict[str, Any]
    cad_thermal_integration_results: Dict[str, Any]
    magnetic_fea_results:            Dict[str, Any]

    # --- rollout helpers ---
    advisory_blocks: List[Dict[str, Any]]
    rollout_notes:   List[str]
