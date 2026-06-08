from __future__ import annotations
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field

class LoopOverride(BaseModel):
    kp: Optional[float] = None
    ki: Optional[float] = None
    compensator_type: Optional[str] = None
    kpole_hz: Optional[float] = None

class RetuneRequest(BaseModel):
    state: Dict[str, Any]
    current_loop: Optional[LoopOverride] = None
    voltage_loop: Optional[LoopOverride] = None

class ControllerModeUpdateRequest(BaseModel):
    state: Dict[str, Any]
    controller_mode: str = Field(..., description="analog or digital")
    controller_name: Optional[str] = None

class ApproveTuningRequest(BaseModel):
    state: Dict[str, Any]

class PresetRetuneRequest(BaseModel):
    state: Dict[str, Any]
    preset: str
    target_loop: str = "both"

def merge_retuning_overrides(state: Dict[str, Any], current_loop: Optional[LoopOverride] = None, voltage_loop: Optional[LoopOverride] = None) -> Dict[str, Any]:
    feedback = state.setdefault("human_feedback", {})
    overrides = feedback.setdefault("overrides", {})
    tuning = overrides.setdefault("state_space_tuning", {})
    if current_loop:
        tuning["current_loop"] = {k:v for k,v in current_loop.model_dump().items() if v is not None}
    if voltage_loop:
        tuning["voltage_loop"] = {k:v for k,v in voltage_loop.model_dump().items() if v is not None}
    return state

def merge_raw_tuning_override(state: Dict[str, Any], tuning_dict: Dict[str, Any]) -> Dict[str, Any]:
    feedback = state.setdefault("human_feedback", {})
    overrides = feedback.setdefault("overrides", {})
    overrides["state_space_tuning"] = tuning_dict
    return state

def reset_retuning_overrides(state: Dict[str, Any], reset_current: bool = True, reset_voltage: bool = True) -> Dict[str, Any]:
    feedback = state.setdefault("human_feedback", {})
    overrides = feedback.setdefault("overrides", {})
    tuning = overrides.setdefault("state_space_tuning", {})
    if reset_current and "current_loop" in tuning: del tuning["current_loop"]
    if reset_voltage and "voltage_loop" in tuning: del tuning["voltage_loop"]
    return state

def merge_controller_mode_update(state: Dict[str, Any], controller_mode: str, controller_name: Optional[str] = None) -> Dict[str, Any]:
    strategy = state.setdefault("controller_strategy", {})
    strategy["selected_mode"] = controller_mode
    selected = state.setdefault("selected_controller", {})
    selected["type"] = controller_mode
    if controller_name:
        selected["name"] = controller_name
    return state

def store_approved_tuning(state: Dict[str, Any]) -> Dict[str, Any]:
    ssd = state.get("state_space_data", {})
    payload = ssd.get("frontend_payload", {})
    approved = state.setdefault("approved_tuning", {})
    approved["current_loop"] = payload.get("current_loop", {}).get("active_coefficients", {})
    approved["voltage_loop"] = payload.get("voltage_loop", {}).get("active_coefficients", {})
    approved["controller_mode"] = payload.get("controller_mode")
    approved["topology"] = payload.get("topology")
    state.setdefault("decision_log", []).append({"step": "approve_retuning", "approved_tuning": approved})
    return state
