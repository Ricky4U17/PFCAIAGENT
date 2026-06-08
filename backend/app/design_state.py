"""
backend/app/design_state.py
Canonical DesignState schema for PFC AI Agent v2.

Every field the frontend sends as 'state' is declared here.
Field ownership rules:
  - Mode-A endpoints    own: project_id, intake, topology_recommendation,
                             selected_topology, selected_mode,
                             controller_strategy, selected_controller_mode,
                             selected_channels, topology_specific_inputs
  - Step-7 engine       reads all Mode-A fields (read-only)
  - Step-15 engine      reads all Mode-A fields (read-only)
  - Step-16 engine      reads all Mode-A fields (read-only)
  - Documentation Agent reads all fields (never writes design data)
  - JS tools            write only to js_state sub-section

Validation is opt-in — controlled by feature_flags.enable_design_state_validation.
Extra fields are always allowed (extra='allow') for forward compatibility.
"""
from __future__ import annotations
from typing import Optional, List, Any
from pydantic import BaseModel, ConfigDict


class IntakeApplication(BaseModel):
    model_config = ConfigDict(extra="allow")
    vin_rms_min:              Optional[float] = None
    output_power_w_low_line:  Optional[float] = None
    output_power_w_high_line: Optional[float] = None
    output_bus_voltage_v:     Optional[float] = None
    nominal_line_frequency_hz:Optional[float] = None


class IntakeThermal(BaseModel):
    model_config = ConfigDict(extra="allow")
    ambient_temp_c_max: Optional[float] = None
    hotspot_limit_c:    Optional[float] = None


class IntakeControl(BaseModel):
    model_config = ConfigDict(extra="allow")
    control_preference: Optional[str] = None   # "Analog" | "Digital" | "Digital ARM" | "Recommend"


class IntakeBusiness(BaseModel):
    model_config = ConfigDict(extra="allow")
    preferred_switch_technology: Optional[List[str]] = None   # ["Si"] | ["SiC"] | ["GaN"]


class IntakeCompliance(BaseModel):
    model_config = ConfigDict(extra="allow")
    application_class:         Optional[str]   = None   # "Industrial" | "Medical"
    leakage_current_limit_ua:  Optional[float] = None


class IntakeSupply(BaseModel):
    model_config = ConfigDict(extra="allow")


class Intake(BaseModel):
    model_config = ConfigDict(extra="allow")
    application: Optional[IntakeApplication] = None
    thermal:     Optional[IntakeThermal]     = None
    control:     Optional[IntakeControl]     = None
    business:    Optional[IntakeBusiness]    = None
    compliance:  Optional[IntakeCompliance]  = None
    supply:      Optional[IntakeSupply]      = None


class TopologyRecommendation(BaseModel):
    model_config = ConfigDict(extra="allow")
    recommended_topology: Optional[str] = None
    recommended_mode:     Optional[str] = None   # "ccm" | "crcm" | "dcm"


class ControllerStrategy(BaseModel):
    model_config = ConfigDict(extra="allow")
    recommended_controller_mode: Optional[str]       = None   # "analog" | "digital" | "digital_arm"
    reasoning:                   Optional[List[str]]  = None
    stated_control_preference:   Optional[str]        = None


class TopologySpecificInputs(BaseModel):
    """Populated by Mode-A mini-intake gate. Confirmed values used by all downstream steps."""
    model_config = ConfigDict(extra="allow")
    switching_frequency_style:      Optional[str]              = None
    recommended_frequency_hz:       Optional[float]            = None
    recommended_frequency_range_hz: Optional[Any]              = None
    ask_crest_ripple_ratio:         Optional[bool]             = None
    default_crest_ripple_ratio:     Optional[float]            = None
    crest_ripple_ratio_guidance:    Optional[str]              = None
    indicative_L_uH:                Optional[float]            = None
    indicative_Iin_pk_A:            Optional[float]            = None
    # Confirmed after mini-intake submission
    confirmed_L_uH:                 Optional[float]            = None
    confirmed_L_uH_sel:             Optional[float]            = None
    confirmed_Iin_pk_A:             Optional[float]            = None
    confirmed_dIL_A:                Optional[float]            = None
    dIL_pp_A:                       Optional[float]            = None
    Iph_rms_A:                      Optional[float]            = None


class JsState(BaseModel):
    """Owned exclusively by JS studio tools. Design agents never write here."""
    model_config = ConfigDict(extra="allow")


class DesignState(BaseModel):
    """
    Canonical state dict passed between frontend and every backend endpoint.
    Owner: Mode-A pipeline populates this; all other agents read it.

    Usage:
        from app.design_state import DesignState
        ds = DesignState.model_validate(raw_state_dict)
    """
    model_config = ConfigDict(extra="allow")

    # ── Set by /mode-a/start ────────────────────────────────────────────────
    project_id: Optional[str]    = None
    intake:     Optional[Intake] = None

    # ── Set by /mode-a/approve-topology ─────────────────────────────────────
    topology_recommendation:  Optional[TopologyRecommendation] = None
    selected_topology:        Optional[str] = None
    selected_mode:            Optional[str] = None   # "ccm" | "crcm" | "dcm"
    controller_strategy:      Optional[ControllerStrategy] = None

    # ── Set by /mode-a/approve-controller ───────────────────────────────────
    selected_controller_mode: Optional[str] = None   # "analog" | "digital" | "digital_arm"

    # ── Set by /mode-a/approve-channels ─────────────────────────────────────
    selected_channels:        Optional[int] = None   # 1 | 2 | 3 …

    # ── Set by /mode-a/submit-mini-intake ───────────────────────────────────
    topology_specific_inputs: Optional[TopologySpecificInputs] = None

    # ── Reserved for JS studio tools (never written by Python agents) ───────
    js_state: Optional[JsState] = None
