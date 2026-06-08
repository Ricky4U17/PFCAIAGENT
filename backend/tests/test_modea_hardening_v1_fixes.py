"""
test_modea_hardening_v1_fixes.py — regression tests for all 8 Mode A hardening fixes.
"""
from __future__ import annotations
import pytest
from app.workflow.api_helpers import build_initial_state
from app.workflow.graph import build_graph, WAIT_TOPOLOGY, WAIT_TOPOLOGY_SPECIFIC
from app.workflow.mode_a_validation import validate_topology_specific_inputs
from app.intake.schema import FullIntake, ApplicationRequirements
from app.intake.compat import app_line_frequency_hz, app_efficiency_fraction, compliance_leakage_limit_ua, compliance_leakage_limit_ma
from app.intake.topology_selector import select_topology
from app.agents.controller_selection_agent import build_controller_strategy


def _intake(control="Recommend", tech=None, line_freq=60.0):
    if tech is None:
        tech = ["Si", "SiC", "GaN"]
    return {
        "application": {
            "vin_rms_min": 90.0, "vin_rms_max": 264.0,
            "nominal_line_frequency_hz": line_freq,
            "input_frequency_range_hz_min": 47.0, "input_frequency_range_hz_max": 63.0,
            "output_bus_voltage_v": 390.0, "dc_bus_voltage_ripple_pk_pk_v": 20.0,
            "output_power_w_nom": 3600.0, "output_power_w_low_line": 1700.0,
            "output_power_w_high_line": 3600.0,
            "power_factor_target": 0.99, "efficiency_target_percent": 96.5,
            "hold_up_time_ms": 20.0,
        },
        "thermal": {"cooling_type": "fan_cooled", "ambient_temp_c_max": 50.0,
                    "max_temp_rise_c": 45.0, "hotspot_limit_c": 110.0,
                    "max_enclosure_rth_c_per_w": 0.5},
        "mechanical": {"height_limit_mm": 40.0, "power_density_priority": 8},
        "compliance": {"conducted_emi_class": "FCC Class B", "radiated_emi_class": "FCC Class B",
                       "harmonics_class": "EN61000-3-2",
                       "surge_requirement": "1 KV Line to Line / 2KV Line to Ground Class A",
                       "leakage_current_limit_ua": 3500.0, "application_class": "Industrial",
                       "semi_f47_required": False},
        "control": {"control_preference": control},
        "business": {"cost_priority": 7, "efficiency_priority": 9, "power_density_priority": 8,
                     "implementation_risk_priority": 8, "preferred_switch_technology": tech},
        "supply": {"preferred_vendors": [], "avoid_vendors": []},
    }


def _advance_mode_a(graph, state):
    """Advance through topology → mini-intake → controller HITL gates."""
    state = graph.invoke(state)  # topology_selection → topology_hitl pause
    assert state["current_step"] == WAIT_TOPOLOGY

    state["human_feedback"] = {"approved": True}
    state = graph.invoke(state)  # topology_hitl → mini-intake pause
    assert state["current_step"] == WAIT_TOPOLOGY_SPECIFIC

    state["human_feedback"] = {
        "approved": True,
        "switching_frequency_style": "fixed",
        "switching_frequency_hz": 70000.0,
        "crest_ripple_ratio": 0.20,
    }
    state = graph.invoke(state)  # mini-intake → controller pause
    assert state["current_step"] == "awaiting_controller_approval"

    state["human_feedback"] = {"approved": True, "controller_mode": "analog",
                                "controller_name": "TI UC3854"}
    state = graph.invoke(state)  # controller → first Mode B step
    return state


# ── MA-1: topology_hitl route map ────────────────────────────────────────────

def test_ma1_graph_advances_past_topology_hitl():
    """topology_hitl must route to topology_specific_intake, not raise KeyError."""
    graph = build_graph()
    state = build_initial_state("ma1", _intake())
    state = graph.invoke(state)
    assert state["current_step"] == WAIT_TOPOLOGY, \
        f"Expected WAIT_TOPOLOGY, got {state['current_step']}"
    state["human_feedback"] = {"approved": True}
    state = graph.invoke(state)
    # Must reach mini-intake, not crash
    assert state["current_step"] == WAIT_TOPOLOGY_SPECIFIC, \
        f"MA-1: Expected WAIT_TOPOLOGY_SPECIFIC, got {state['current_step']}"


def test_ma1_designer_override_topology_also_routes():
    graph = build_graph()
    state = build_initial_state("ma1b", _intake())
    state = graph.invoke(state)
    state["human_feedback"] = {"approved": True, "selected_topology": "single_boost_ccm"}
    state = graph.invoke(state)
    assert state["current_step"] == WAIT_TOPOLOGY_SPECIFIC
    assert state["selected_topology"] == "single_boost_ccm"


def test_ma1_full_mode_a_to_mode_b():
    """Complete end-to-end Mode A → first Mode B step without errors."""
    graph = build_graph()
    state = build_initial_state("ma1c", _intake())
    state = _advance_mode_a(graph, state)
    assert state["mode"] == "mode_b"
    assert state["current_step"] not in (WAIT_TOPOLOGY, WAIT_TOPOLOGY_SPECIFIC,
                                          "awaiting_controller_approval")
    assert not state.get("errors"), f"Errors during Mode A: {state.get('errors')}"


# ── MA-2: mode_a_validation_errors in TypedDict ──────────────────────────────

def test_ma2_validation_errors_in_state_type():
    from app.state import ProjectState
    assert "mode_a_validation_errors" in ProjectState.__annotations__


def test_ma2_validation_errors_seeded_in_initial_state():
    state = build_initial_state("ma2", _intake())
    assert "mode_a_validation_errors" in state
    assert state["mode_a_validation_errors"] == []


# ── MA-3: compat helpers wired into _design_inputs ───────────────────────────

def test_ma3_compat_app_line_frequency_hz_new_key():
    app = {"nominal_line_frequency_hz": 50.0}
    assert app_line_frequency_hz(app) == 50.0


def test_ma3_compat_app_line_frequency_hz_old_key():
    app = {"line_frequency_hz_nom": 60.0}
    assert app_line_frequency_hz(app) == 60.0


def test_ma3_compat_app_efficiency_fraction_percent():
    app = {"efficiency_target_percent": 96.5}
    assert abs(app_efficiency_fraction(app) - 0.965) < 1e-9


def test_ma3_compat_leakage_ua():
    comp = {"leakage_current_limit_ua": 3500.0}
    assert compliance_leakage_limit_ua(comp) == 3500.0


def test_ma3_compat_leakage_ma_bridge():
    comp = {"leakage_current_limit_ma": 3.5}
    assert abs(compliance_leakage_limit_ua(comp) - 3500.0) < 1e-6
    assert abs(compliance_leakage_limit_ma(comp) - 3.5) < 1e-9


def test_ma3_design_inputs_uses_compat_line_freq():
    """_design_inputs must route through compat for line_freq."""
    from app.workflow.graph import _design_inputs
    state = build_initial_state("ma3d", _intake(line_freq=50.0))
    di = _design_inputs(state)
    assert di["line_freq"] == 50.0


def test_ma3_design_inputs_uses_compat_efficiency():
    from app.workflow.graph import _design_inputs
    state = build_initial_state("ma3e", _intake())
    di = _design_inputs(state)
    assert abs(di["eff"] - 0.965) < 1e-9, f"Expected 0.965, got {di['eff']}"


# ── MA-4: crest_ripple_ratio applied for all modes ───────────────────────────

def test_ma4_ccm_crest_ripple_applied():
    graph = build_graph()
    state = build_initial_state("ma4a", _intake())
    state = graph.invoke(state)
    state["human_feedback"] = {"approved": True}
    state = graph.invoke(state)
    state["human_feedback"] = {
        "approved": True, "switching_frequency_style": "fixed",
        "switching_frequency_hz": 70000.0, "crest_ripple_ratio": 0.15,
    }
    state = graph.invoke(state)
    assert state["topology_specific_inputs"]["default_crest_ripple_ratio"] == 0.15


def test_ma4_crcm_crest_ripple_applied_and_validated():
    """CrCM: user can only submit 2.0; any other value fails validation."""
    # Valid CrCM submission
    ok, errs = validate_topology_specific_inputs("crcm", {
        "switching_frequency_style": "variable",
        "recommended_frequency_range_hz": [45000.0, 180000.0],
        "default_crest_ripple_ratio": 2.0,
    })
    assert ok, f"Valid CrCM rejected: {errs}"

    # Invalid CrCM ripple (user tried to set 1.5)
    ok, errs = validate_topology_specific_inputs("crcm", {
        "switching_frequency_style": "variable",
        "recommended_frequency_range_hz": [45000.0, 180000.0],
        "default_crest_ripple_ratio": 1.5,
    })
    assert not ok, "CrCM ripple=1.5 should be rejected"


def test_ma4_dcm_crest_ripple_must_exceed_two():
    ok, errs = validate_topology_specific_inputs("dcm", {
        "switching_frequency_style": "fixed",
        "recommended_frequency_hz": 80000.0,
        "default_crest_ripple_ratio": 2.5,
    })
    assert ok, f"Valid DCM ripple=2.5 rejected: {errs}"

    ok, errs = validate_topology_specific_inputs("dcm", {
        "switching_frequency_style": "fixed",
        "recommended_frequency_hz": 80000.0,
        "default_crest_ripple_ratio": 1.8,
    })
    assert not ok, "DCM ripple=1.8 should be rejected"


# ── MA-5: 400 Hz line frequency accepted ─────────────────────────────────────

def test_ma5_400hz_accepted_by_schema():
    """Pydantic must not reject 400.0 as line frequency."""
    app = ApplicationRequirements(nominal_line_frequency_hz=400.0)
    assert app.nominal_line_frequency_hz == 400.0


def test_ma5_400hz_flows_into_design_inputs():
    from app.workflow.graph import _design_inputs
    state = build_initial_state("ma5", _intake(line_freq=400.0))
    di = _design_inputs(state)
    assert di["line_freq"] == 400.0


def test_ma5_full_intake_with_400hz_parses():
    raw = _intake(line_freq=400.0)
    intake = FullIntake(**raw)
    assert intake.application.nominal_line_frequency_hz == 400.0


# ── MA-6: stale validation errors cleared on success ─────────────────────────

def test_ma6_stale_errors_cleared_after_success():
    graph = build_graph()
    state = build_initial_state("ma6", _intake())
    state = graph.invoke(state)
    state["human_feedback"] = {"approved": True}
    state = graph.invoke(state)

    # First mini-intake: invalid (DCM crest ratio 1.5 — but mode is CCM here, so
    # test by submitting without required frequency value)
    state["human_feedback"] = {"approved": True, "switching_frequency_style": "fixed"}
    state = graph.invoke(state)
    # May or may not have validation errors depending on mode; seed manually to test clearing
    state["mode_a_validation_errors"] = ["some old error"]

    # Now submit valid data
    state["human_feedback"] = {
        "approved": True, "switching_frequency_style": "fixed",
        "switching_frequency_hz": 70000.0, "crest_ripple_ratio": 0.20,
    }
    state = graph.invoke(state)
    assert state.get("mode_a_validation_errors") == [], \
        f"Stale errors not cleared: {state.get('mode_a_validation_errors')}"


# ── MA-7: control_preference respected in controller selection ────────────────

def test_ma7_analog_preference_respected_for_conventional_boost():
    state = build_initial_state("ma7a", _intake(control="Analog"))
    state["selected_topology"] = "interleaved_boost_ccm"
    strategy = build_controller_strategy(state)
    assert strategy["recommended_controller_mode"] == "analog"
    assert strategy["stated_control_preference"] == "Analog"


def test_ma7_digital_preference_respected_for_conventional_boost():
    state = build_initial_state("ma7b", _intake(control="Digital"))
    state["selected_topology"] = "interleaved_boost_ccm"
    strategy = build_controller_strategy(state)
    assert strategy["recommended_controller_mode"] == "digital"


def test_ma7_analog_preference_honoured_for_ttp_with_warning():
    state = build_initial_state("ma7c", _intake(control="Analog", tech=["SiC"]))
    state["selected_topology"] = "totem_pole_ccm"
    strategy = build_controller_strategy(state)
    # Preference honoured even for TTP
    assert strategy["recommended_controller_mode"] == "analog"
    # Warning included in reasoning
    assert any("Analog preference" in r for r in strategy["reasoning"]), \
        "Expected warning about Analog preference for TTP"


def test_ma7_recommend_defaults_digital_for_wbg():
    state = build_initial_state("ma7d", _intake(control="Recommend", tech=["SiC", "GaN"]))
    state["selected_topology"] = "interleaved_boost_ccm"
    strategy = build_controller_strategy(state)
    assert strategy["recommended_controller_mode"] == "digital"


def test_ma7_recommend_defaults_analog_for_si_only():
    state = build_initial_state("ma7e", _intake(control="Recommend", tech=["Si"]))
    state["selected_topology"] = "interleaved_boost_ccm"
    strategy = build_controller_strategy(state)
    assert strategy["recommended_controller_mode"] == "analog"


# ── MA-8: initial state completeness ─────────────────────────────────────────

def test_ma8_selected_mode_seeded():
    state = build_initial_state("ma8a", _intake())
    assert "selected_mode" in state
    assert state["selected_mode"] is None


def test_ma8_topology_specific_inputs_seeded():
    state = build_initial_state("ma8b", _intake())
    assert "topology_specific_inputs" in state
    assert state["topology_specific_inputs"] == {}


def test_ma8_mode_a_validation_errors_seeded():
    state = build_initial_state("ma8c", _intake())
    assert "mode_a_validation_errors" in state
    assert state["mode_a_validation_errors"] == []


def test_ma8_ensure_phase1_defaults_seeds_mode_a_fields():
    from app.workflow.phase1_helpers import ensure_phase1_state_defaults
    state: dict = {}
    ensure_phase1_state_defaults(state)
    assert state.get("selected_mode") is None
    assert state.get("topology_specific_inputs") == {}
    assert state.get("mode_a_validation_errors") == []


# ── Integration: full Mode A round-trip ──────────────────────────────────────

def test_integration_mode_a_top3_produced():
    result = select_topology(_intake())
    assert "top_3" in result
    assert len(result["top_3"]) == 3
    assert "mode_scores" in result
    assert "topology_scores" in result


def test_integration_mini_intake_fsw_flows_to_design_inputs():
    from app.workflow.graph import _design_inputs
    state = build_initial_state("intg", _intake())
    state["topology_specific_inputs"] = {
        "recommended_frequency_hz": 85000.0,
        "default_crest_ripple_ratio": 0.12,
    }
    di = _design_inputs(state)
    assert di["fsw"] == 85000.0
    assert di["ripple_ratio_target"] == 0.12


def test_integration_full_mode_a_no_errors():
    graph = build_graph()
    state = build_initial_state("intg2", _intake())
    state = _advance_mode_a(graph, state)
    assert state["mode"] == "mode_b"
    assert state.get("errors", []) == []
    assert state.get("mode_a_validation_errors", []) == []
    assert state["selected_topology"] is not None
    assert state["selected_mode"] is not None
    assert state["topology_specific_inputs"] != {}
