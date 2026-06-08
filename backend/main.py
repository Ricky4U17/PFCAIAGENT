"""PFC AI Agent — Mode A Hardened v1  |  FastAPI entry point."""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Any, Dict, Optional
import logging

from app.workflow.graph import build_graph
from app.workflow.api_helpers import build_initial_state, apply_feedback
from app.agents.controller_selection_agent import build_controller_strategy
from app.exporters.report_generator import generate_final_report_bundle
from app.api.retuning import (
    RetuneRequest, ControllerModeUpdateRequest, ApproveTuningRequest,
    PresetRetuneRequest, merge_retuning_overrides, merge_raw_tuning_override,
    reset_retuning_overrides, merge_controller_mode_update, store_approved_tuning,
)
from app.agents.state_space_agent import retune_state_space_from_state, get_active_tuning_from_state
from app.engines.state_space.retuning_presets import apply_preset_to_tuning

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

app = FastAPI(
    title="PFC AI Agent",
    description="Mode A Hardened v1 — full 25-step PFC design workflow",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

graph = build_graph()
log.info("LangGraph compiled successfully")

# ── Pydantic request models ───────────────────────────────────────────────────

class CreateProjectRequest(BaseModel):
    project_id: str
    intake: Dict[str, Any]

class RunProjectRequest(BaseModel):
    state: Dict[str, Any]

class FeedbackRequest(BaseModel):
    state: Dict[str, Any]
    feedback: Dict[str, Any]

class ModeAStartRequest(BaseModel):
    project_id: str
    intake: Dict[str, Any]

class ModeAFeedbackRequest(BaseModel):
    state: Dict[str, Any]
    feedback: Dict[str, Any]

# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/", tags=["health"])
def root():
    return {"status": "ok", "service": "PFC AI Agent", "version": "1.0.0"}

@app.get("/health", tags=["health"])
def health():
    return {"status": "healthy"}

# ── Mode A step-by-step endpoints ─────────────────────────────────────────────

@app.post("/mode-a/start", tags=["mode-a"])
def mode_a_start(req: ModeAStartRequest):
    """
    Step 1 — Run intake + topology selection.
    Returns state paused at WAIT_TOPOLOGY with full ranking.
    """
    try:
        state = build_initial_state(req.project_id, req.intake)
        state = graph.invoke(state)
        rec = state.get("topology_recommendation", {})
        return {
            "status": "wait_topology",
            "current_step": state.get("current_step"),
            "ranking": state.get("topology_ranking", []),
            "mode_scores": state.get("mode_scores", []),
            "topology_scores": state.get("topology_scores", []),
            "recommended_topology": rec.get("recommended_topology"),
            "recommended_mode": rec.get("recommended_mode"),
            "state": state,
        }
    except Exception as e:
        log.exception("mode_a_start failed")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/mode-a/approve-topology", tags=["mode-a"])
def mode_a_approve_topology(req: ModeAFeedbackRequest):
    """
    Step 2 — Submit topology HITL approval (or override).
    feedback: { "approved": true, "selected_topology": "interleaved_boost_ccm" }
    Returns state paused at WAIT_TOPOLOGY_SPECIFIC with mini_intake_defaults.
    """
    try:
        state = req.state
        state["human_feedback"] = req.feedback
        state = graph.invoke(state)
        errors = state.get("mode_a_validation_errors", [])
        return {
            "status": "wait_mini_intake",
            "current_step": state.get("current_step"),
            "selected_topology": state.get("selected_topology"),
            "selected_mode": state.get("selected_mode"),
            "mini_intake_defaults": state.get("topology_specific_inputs", {}),
            "validation_errors": errors,
            "state": state,
        }
    except Exception as e:
        log.exception("mode_a_approve_topology failed")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/mode-a/submit-mini-intake", tags=["mode-a"])
def mode_a_submit_mini_intake(req: ModeAFeedbackRequest):
    """
    Step 3 — Submit mini-intake gate (fsw style/value, crest ripple).
    feedback: { "approved": true, "switching_frequency_style": "fixed",
                "switching_frequency_hz": 70000, "crest_ripple_ratio": 0.20 }
    Returns state paused at WAIT_CONTROLLER with controller_strategy,
    or back at WAIT_TOPOLOGY_SPECIFIC if validation fails.
    """
    try:
        state = req.state
        state["human_feedback"] = req.feedback
        state = graph.invoke(state)
        errors = state.get("mode_a_validation_errors", [])
        if errors:
            return {
                "status": "wait_mini_intake",
                "current_step": state.get("current_step"),
                "validation_errors": errors,
                "mini_intake_defaults": state.get("topology_specific_inputs", {}),
                "state": state,
            }
        strategy = build_controller_strategy(state)
        state["controller_strategy"] = strategy
        return {
            "status": "wait_controller",
            "current_step": state.get("current_step"),
            "controller_strategy": strategy,
            "validation_errors": [],
            "state": state,
        }
    except Exception as e:
        log.exception("mode_a_submit_mini_intake failed")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/mode-a/approve-controller", tags=["mode-a"])
def mode_a_approve_controller(req: ModeAFeedbackRequest):
    """
    Step 4 — Submit controller HITL approval.
    feedback: { "approved": true, "controller_mode": "analog", "controller_name": "TI UC3854" }
    Returns state with mode=mode_b, paused at WAIT_MODE_B (first Mode B step).
    """
    try:
        state = req.state
        state["human_feedback"] = req.feedback
        state = graph.invoke(state)
        return {
            "status": "mode_b_ready",
            "current_step": state.get("current_step"),
            "mode": state.get("mode"),
            "selected_controller": state.get("selected_controller"),
            "state": state,
        }
    except Exception as e:
        log.exception("mode_a_approve_controller failed")
        raise HTTPException(status_code=500, detail=str(e))

# ── Generic workflow endpoints ────────────────────────────────────────────────

@app.post("/projects/create", tags=["workflow"])
def create_project(req: CreateProjectRequest):
    return build_initial_state(req.project_id, req.intake)

@app.post("/workflow/run", tags=["workflow"])
def run_workflow(req: RunProjectRequest):
    try:
        return graph.invoke(req.state)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/workflow/feedback", tags=["workflow"])
def run_with_feedback(req: FeedbackRequest):
    try:
        state = apply_feedback(req.state, req.feedback)
        return graph.invoke(state)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/report/generate", tags=["report"])
def generate_report(req: RunProjectRequest):
    out_dir = f"generated_artifacts/{req.state.get('project_id','project')}/reports"
    return generate_final_report_bundle(req.state, out_dir)

# ── Retuning endpoints ────────────────────────────────────────────────────────

@app.post("/retune/current-loop", tags=["retuning"])
def retune_current_loop(req: RetuneRequest):
    state = merge_retuning_overrides(req.state, current_loop=req.current_loop, voltage_loop=None)
    result = retune_state_space_from_state(state)
    return {"state": state, "state_space_data": result, "frontend_payload": result["frontend_payload"]}

@app.post("/retune/voltage-loop", tags=["retuning"])
def retune_voltage_loop(req: RetuneRequest):
    state = merge_retuning_overrides(req.state, current_loop=None, voltage_loop=req.voltage_loop)
    result = retune_state_space_from_state(state)
    return {"state": state, "state_space_data": result, "frontend_payload": result["frontend_payload"]}

@app.post("/retune/both-loops", tags=["retuning"])
def retune_both_loops(req: RetuneRequest):
    state = merge_retuning_overrides(req.state, current_loop=req.current_loop, voltage_loop=req.voltage_loop)
    result = retune_state_space_from_state(state)
    return {"state": state, "state_space_data": result, "frontend_payload": result["frontend_payload"]}

@app.post("/retune/controller-mode", tags=["retuning"])
def update_controller_mode(req: ControllerModeUpdateRequest):
    state = merge_controller_mode_update(req.state, req.controller_mode, req.controller_name)
    result = retune_state_space_from_state(state)
    return {"state": state, "state_space_data": result, "frontend_payload": result["frontend_payload"]}

@app.post("/retune/reset-default-values", tags=["retuning"])
def reset_default_values(req: RunProjectRequest):
    state = reset_retuning_overrides(req.state, reset_current=True, reset_voltage=True)
    result = retune_state_space_from_state(state)
    return {"state": state, "state_space_data": result, "frontend_payload": result["frontend_payload"]}

@app.post("/retune/approve", tags=["retuning"])
def approve_retuning(req: ApproveTuningRequest):
    state = store_approved_tuning(req.state)
    result = retune_state_space_from_state(state)
    state["state_space_data"] = result
    return {"state": state, "approved_tuning": state.get("approved_tuning", {}),
            "state_space_data": result, "frontend_payload": result["frontend_payload"]}

@app.post("/retune/preset", tags=["retuning"])
def preset_retune(req: PresetRetuneRequest):
    active_tuning = get_active_tuning_from_state(req.state)
    preset_tuning = apply_preset_to_tuning(active_tuning, req.preset, req.target_loop)
    state = merge_raw_tuning_override(req.state, preset_tuning)
    state.setdefault("human_feedback", {}).setdefault("overrides", {})["last_retuning_preset"] = {
        "preset": req.preset, "target_loop": req.target_loop
    }
    result = retune_state_space_from_state(state)
    return {"state": state, "preset_applied": req.preset, "target_loop": req.target_loop,
            "state_space_data": result, "frontend_payload": result["frontend_payload"]}
