from __future__ import annotations
from pydantic import BaseModel

class FeatureFlags(BaseModel):
    enable_guardrail_v2: bool = True
    enable_supply_chain_agent: bool = True
    enable_magnetic_design_v2: bool = True
    enable_closed_loop_simulation: bool = True

    enable_layout_parasitics_agent: bool = True
    enable_firmware_generation_agent: bool = True
    enable_reliability_mtbf_agent: bool = True

    enable_pcb_floorplanning_agent: bool = True
    enable_cad_thermal_integration_agent: bool = True
    enable_magnetic_fea_agent: bool = True

    supply_chain_blocking: bool = False
    magnetic_v2_blocking: bool = False
    simulation_blocking: bool = False
    layout_parasitics_blocking: bool = False
    firmware_generation_blocking: bool = False
    reliability_mtbf_blocking: bool = False
    pcb_floorplanning_blocking: bool = False
    cad_thermal_integration_blocking: bool = False
    magnetic_fea_blocking: bool = False

    write_advisory_results_into_report: bool = True
    preserve_legacy_results: bool = True

FEATURE_FLAGS = FeatureFlags()
