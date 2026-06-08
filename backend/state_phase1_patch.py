from typing import Any, Dict, List, TypedDict

class ProjectStatePhase1Patch(TypedDict, total=False):
    schema_version: str
    feature_flags: Dict[str, Any]

    guardrail_v2_results: Dict[str, Any]
    supply_chain_results: Dict[str, Any]
    magnetic_design_v2_results: Dict[str, Any]
    simulation_verification_results: Dict[str, Any]

    advisory_blocks: List[Dict[str, Any]]
    rollout_notes: List[str]

    vendor_candidates: Dict[str, Any]
    magnetic_design_data: Dict[str, Any]
    simulation_artifacts: Dict[str, Any]
