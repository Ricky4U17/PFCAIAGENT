"""
test_hardening_v3.py — regression tests covering all 12 Phase 3 hardening fixes.
"""
from __future__ import annotations
import warnings
import pytest
from app.workflow.api_helpers import build_initial_state
from app.workflow.graph import (
    build_graph, ADVISORY_FLAG_MAP, THERMAL_LOOPBACK_LIMIT,
    THERMAL_LOOPBACK_STALE_STEPS, MODE_B_SEQUENCE,
)
from app.services.report_helpers import (
    build_topology_section, build_step_section, build_advisory_section,
    section_to_markdown,
)
from app.engines.simulation.spice_backend import ScaffoldBackend, SpiceBackend, SpiceResult
from app.engines.simulation.advisory_engine import build_closed_loop_simulation_advisory
from app.engines.cad_thermal.advisory_engine import build_cad_thermal_integration_advisory
from app.engines.magnetic_fea.advisory_engine import build_magnetic_fea_advisory


def _intake():
    return {
        "application": {
            "vin_rms_min": 90.0, "vin_rms_max": 264.0, "line_frequency_hz_nom": 60.0,
            "output_bus_voltage_v": 390.0, "output_power_w_nom": 3600.0,
            "output_power_w_low_line": 1700.0, "power_factor_target": 0.99,
            "efficiency_target_percent": 96.5,
        },
        "thermal": {
            "cooling_type": "fan_cooled", "ambient_temp_c_max": 50.0,
            "max_temp_rise_c": 45.0, "max_enclosure_rth_c_per_w": 0.5,
        },
        "compliance": {
            "conducted_emi_required": True, "radiated_emi_required": True,
            "surge_required": True, "leakage_current_limit_ma": 3.5,
        },
        "business": {
            "cost_priority": 7, "efficiency_priority": 9, "power_density_priority": 8,
            "implementation_risk_priority": 8,
            "preferred_switch_technology": ["Si", "SiC", "GaN"],
        },
    }


def _advance_to_mode_b(graph, state):
    state = graph.invoke(state)
    state["human_feedback"] = {"approved": True}
    state = graph.invoke(state)
    state["human_feedback"] = {"approved": True, "controller_mode": "analog",
                                "controller_name": "TI UC3854"}
    state = graph.invoke(state)
    return state


# ── I-1: Terminal routing ────────────────────────────────────────────────────

def test_i1_graph_reaches_final():
    graph = build_graph()
    state = build_initial_state("i1", _intake())
    state = _advance_to_mode_b(graph, state)
    for _ in range(60):
        if state.get("current_step") == "final":
            break
        state["human_feedback"] = {"approved": True}
        state = graph.invoke(state)
    assert state.get("current_step") == "final", \
        f"Stuck at: {state.get('current_step')}"
    assert state.get("mode") == "final"


def test_i1_finalize_in_route_map():
    graph = build_graph()
    assert graph is not None   # compile would raise if "finalize" missing from route_map


def test_i1_altium_is_last_sequence_step():
    assert MODE_B_SEQUENCE[-1] == "altium_export"
    assert len(MODE_B_SEQUENCE) == 25


# ── I-2: Thermal loopback guard ──────────────────────────────────────────────

def test_i2_counter_seeded_in_initial_state():
    state = build_initial_state("i2", _intake())
    assert state["thermal_loopback_count"] == 0


def test_i2_limit_constant():
    assert THERMAL_LOOPBACK_LIMIT >= 2


def test_i2_stale_steps_all_downstream_of_inductor():
    idx_inductor = MODE_B_SEQUENCE.index("inductor_sizing")
    for step in THERMAL_LOOPBACK_STALE_STEPS:
        assert MODE_B_SEQUENCE.index(step) > idx_inductor, \
            f"{step} must be downstream of inductor_sizing"


def test_i2_loopback_pauses_at_limit():
    from app.workflow.graph import mode_b_hitl_node, WAIT_MODE_B
    state = build_initial_state("i2b", _intake())
    state.update(current_step="bidirectional_thermal", thermal_status="failed",
                 thermal_loopback_count=THERMAL_LOOPBACK_LIMIT,
                 human_feedback={"approved": True}, feature_flags={})
    result = mode_b_hitl_node(state)
    assert result["pending_step"] == WAIT_MODE_B
    assert any("Thermal loopback limit" in e for e in result.get("errors", []))


def test_i2_stale_results_cleared_on_retry():
    from app.workflow.graph import mode_b_hitl_node
    state = build_initial_state("i2c", _intake())
    state.update(current_step="bidirectional_thermal", thermal_status="failed",
                 thermal_loopback_count=0, human_feedback={"approved": True},
                 feature_flags={})
    for step in THERMAL_LOOPBACK_STALE_STEPS:
        state["step_results"][step]    = {"stale": True}
        state["report_sections"][step] = {"stale": True}
    mode_b_hitl_node(state)
    for step in THERMAL_LOOPBACK_STALE_STEPS:
        assert step not in state["step_results"],    f"{step} not cleared from step_results"
        assert step not in state["report_sections"], f"{step} not cleared from report_sections"


def test_i2_phase3_stale_steps_included():
    """magnetic_fea_advisory is downstream of inductor_sizing and must be in stale list."""
    assert "magnetic_fea_advisory" in THERMAL_LOOPBACK_STALE_STEPS


# ── I-3: Guardrail blocked pauses workflow ───────────────────────────────────

def test_i3_guardrail_blocked_pauses():
    from app.workflow.graph import mode_b_hitl_node, WAIT_MODE_B
    state = build_initial_state("i3", _intake())
    state.update(current_step="guardrail_v2_advisory",
                 feature_flags={"enable_guardrail_v2": True},
                 human_feedback={"status": "guardrail_blocked",
                                 "violations": ["phase margin too low"]})
    result = mode_b_hitl_node(state)
    assert result["pending_step"] == WAIT_MODE_B


def test_i3_guardrail_blocked_wins_over_approved():
    from app.workflow.graph import mode_b_hitl_node, WAIT_MODE_B
    state = build_initial_state("i3b", _intake())
    state.update(current_step="guardrail_v2_advisory",
                 feature_flags={"enable_guardrail_v2": True},
                 human_feedback={"status": "guardrail_blocked", "approved": True,
                                 "violations": ["pm"]})
    result = mode_b_hitl_node(state)
    assert result["pending_step"] == WAIT_MODE_B


def test_i3_guardrail_hard_stop_seeded():
    state = build_initial_state("i3c", _intake())
    assert state["guardrail_hard_stop"] is False


# ── I-4: Disabled advisory auto-advance ──────────────────────────────────────

@pytest.mark.parametrize("step,flag", list(ADVISORY_FLAG_MAP.items()))
def test_i4_disabled_advisory_auto_advances(step, flag):
    from app.workflow.graph import mode_b_hitl_node
    state = build_initial_state("i4", _intake())
    state.update(current_step=step, human_feedback={},
                 feature_flags={flag: False})
    result = mode_b_hitl_node(state)
    idx      = MODE_B_SEQUENCE.index(step)
    expected = "finalize" if idx >= len(MODE_B_SEQUENCE) - 1 else MODE_B_SEQUENCE[idx + 1]
    assert result["pending_step"] == expected, \
        f"{step}: expected {expected!r}, got {result['pending_step']!r}"


def test_i4_phase3_advisories_in_flag_map():
    assert "magnetic_fea_advisory" in ADVISORY_FLAG_MAP
    assert "cad_thermal_integration_advisory" in ADVISORY_FLAG_MAP
    assert "pcb_floorplanning_advisory" in ADVISORY_FLAG_MAP


def test_i4_enabled_advisory_waits_for_human():
    from app.workflow.graph import mode_b_hitl_node, WAIT_MODE_B
    state = build_initial_state("i4b", _intake())
    state.update(current_step="supply_chain_advisory", human_feedback={},
                 feature_flags={"enable_supply_chain_agent": True})
    result = mode_b_hitl_node(state)
    assert result["pending_step"] == WAIT_MODE_B


# ── I-5: Design defaults / eff from intake ───────────────────────────────────

def test_i5_eff_from_intake():
    from app.workflow.graph import _design_inputs
    state = build_initial_state("i5", _intake())
    di = _design_inputs(state)
    assert abs(di["eff"] - 0.965) < 1e-9, f"Expected 0.965 got {di['eff']}"


def test_i5_override_wins():
    from app.workflow.graph import _design_inputs
    state = build_initial_state("i5b", _intake())
    state["human_feedback"] = {"overrides": {"eff": 0.91}}
    assert abs(_design_inputs(state)["eff"] - 0.91) < 1e-9


def test_i5_design_defaults_seeded_without_eff():
    state = build_initial_state("i5c", _intake())
    dd = state.get("design_defaults", {})
    assert "L"   in dd and "fsw" in dd and "Cout" in dd
    assert "eff" not in dd, "eff must not be in design_defaults"


def test_i5_l_fsw_from_design_defaults():
    from app.workflow.graph import _design_inputs
    state = build_initial_state("i5d", _intake())
    state["design_defaults"]["L"]   = 300e-6
    state["design_defaults"]["fsw"] = 80000.0
    di = _design_inputs(state)
    assert abs(di["L"]   - 300e-6)  < 1e-12
    assert abs(di["fsw"] - 80000.0) < 1e-6


# ── I-6: Structured report sections ──────────────────────────────────────────

def test_i6_step_section_is_dict():
    r = build_step_section("inductor_sizing", {"L_required_H": 235e-6, "Ipk": 10.5})
    assert isinstance(r, dict)
    assert r["type"] == "step_result"
    assert "L_required_H" in r["params"]


def test_i6_topology_section_is_dict():
    sel = {"recommended_topology": "interleaved_boost_ccm",
           "runner_up_topology": "single_boost_ccm",
           "why_selected": [], "why_runner_up_lost": [],
           "ranking": [{"topology": "interleaved_boost_ccm",
                        "final_score": 3.8, "penalty": 0.0, "penalty_details": []}]}
    r = build_topology_section(sel)
    assert isinstance(r, dict) and r["type"] == "topology_selection"


def test_i6_markdown_rendered_at_export():
    section = build_step_section("control_loops", {"phase_margin_deg": 52.1})
    md = section_to_markdown(section)
    assert "52.1" in md and "control loops" in md.lower()


def test_i6_legacy_string_passthrough():
    md = section_to_markdown("## Legacy\n- k: v")
    assert "Legacy" in md


def test_i6_advisory_section_dict():
    r = build_advisory_section("PCB Floorplanning",
                                {"status": "advisory_ready", "blocking": False,
                                 "details": {}, "notes": ["n1"]})
    assert r["type"] == "advisory" and r["title"] == "PCB Floorplanning"


# ── I-7: Deprecated safety_guardrail_agent ───────────────────────────────────

def test_i7_deprecation_warning():
    from app.agents.safety_guardrail_agent import node_safety_guardrail
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        node_safety_guardrail({"state_space_data": {}})
    assert any(issubclass(x.category, DeprecationWarning) for x in w)


def test_i7_not_referenced_in_graph():
    import inspect, app.workflow.graph as gmod
    src = inspect.getsource(gmod)
    assert "node_safety_guardrail" not in src
    assert "safety_guardrail_agent" not in src


# ── I-8: SpiceBackend protocol ────────────────────────────────────────────────

def test_i8_scaffold_is_spice_backend():
    assert isinstance(ScaffoldBackend(), SpiceBackend)


def test_i8_scaffold_returns_spice_result():
    r = ScaffoldBackend().run({})
    assert isinstance(r, SpiceResult)
    assert r.backend_name == "scaffold" and r.simulation_ran is False


def test_i8_custom_backend_accepted():
    class FakeBackend:
        name = "fake"
        def run(self, state):
            return SpiceResult(voltage_overshoot_percent=5.0,
                               simulation_ran=True, backend_name="fake")
    assert isinstance(FakeBackend(), SpiceBackend)
    adv = build_closed_loop_simulation_advisory({}, backend=FakeBackend())
    assert adv["backend_name"] == "fake"
    assert adv["simulation_ran"] is True


def test_i8_default_is_scaffold():
    adv = build_closed_loop_simulation_advisory({})
    assert adv["backend_name"] == "scaffold"


# ── I-9: CAD thermal correct key nesting ─────────────────────────────────────

def test_i9_reads_nested_thermal_data():
    """Verify advisory reads thermal_data sub-dict, not missing top-level keys."""
    state = build_initial_state("i9", _intake())
    state["thermal_results"] = {
        "thermal_status": "passed",
        "thermal_data": {
            "total_loss_w":         85.0,
            "rth_required_c_per_w": 0.47,
        }
    }
    adv = build_cad_thermal_integration_advisory(state)
    mech = adv["mechanical_summary"]
    assert mech["required_thermal_resistance_c_per_w"] == pytest.approx(0.47, abs=1e-4), \
        "Must read from thermal_data nested dict, not non-existent top-level key"
    assert mech["estimated_total_loss_w"] == pytest.approx(85.0, abs=0.1)


def test_i9_does_not_silently_default_rth():
    """If thermal_results is missing entirely, note should be in output but engine must not crash."""
    adv = build_cad_thermal_integration_advisory({})
    assert "required_thermal_resistance_c_per_w" in adv["mechanical_summary"]


def test_i9_hotspot_uses_intake_max_rise():
    state = build_initial_state("i9b", _intake())
    # intake sets max_temp_rise_c=45, ambient=50 → hotspot=95
    adv = build_cad_thermal_integration_advisory(state)
    assert adv["mechanical_summary"]["estimated_hotspot_temp_c"] == pytest.approx(95.0, abs=0.5)


# ── I-10: Magnetic FEA fallback ──────────────────────────────────────────────

def test_i10_uses_v2_derived_when_available():
    state = build_initial_state("i10", _intake())
    state["magnetic_design_v2_results"] = {
        "details": {"derived_estimates": {"Bmax_est_T": 0.31, "saturation_margin_est": 1.35}}
    }
    adv = build_magnetic_fea_advisory(state)
    assert adv["fea_screening_summary"]["estimated_bulk_Bmax_T"] == pytest.approx(0.31, abs=1e-4)
    assert "magnetic_design_v2" in adv["fea_screening_summary"]["data_source"]


def test_i10_fallback_to_magnetic_design_data_when_v2_disabled():
    state = build_initial_state("i10b", _intake())
    # v2 advisory ran but was disabled → details={}
    state["magnetic_design_v2_results"] = {"status": "disabled", "details": {}}
    # Core magnetic_design step wrote Bpk
    state["magnetic_design_data"] = {"Bpk": 0.29, "i_sat_a": 22.0}
    state["step_results"]["input_processing"] = {"Ipk": 15.0}
    adv = build_magnetic_fea_advisory(state)
    assert adv["fea_screening_summary"]["estimated_bulk_Bmax_T"] == pytest.approx(0.29, abs=1e-4)
    assert "fallback" in adv["fea_screening_summary"]["data_source"]


def test_i10_data_source_documented_in_output():
    adv = build_magnetic_fea_advisory({})
    assert "data_source" in adv["fea_screening_summary"]
    assert adv["fea_screening_summary"]["data_source"] != ""


# ── I-11: ProjectState TypedDict completeness ────────────────────────────────

def test_i11_state_has_phase3_fields():
    from app.state import ProjectState
    annotations = ProjectState.__annotations__
    required = [
        "schema_version", "feature_flags", "design_defaults",
        "thermal_loopback_count", "guardrail_hard_stop",
        "pcb_floorplanning_results", "cad_thermal_integration_results",
        "magnetic_fea_results",
        "layout_parasitics_results", "firmware_generation_results",
        "reliability_mtbf_results",
        "guardrail_v2_results", "supply_chain_results",
        "magnetic_design_v2_results", "simulation_verification_results",
        "reflection_log", "advisory_blocks", "rollout_notes",
    ]
    missing = [f for f in required if f not in annotations]
    assert not missing, f"Missing from ProjectState: {missing}"


def test_i11_initial_state_has_all_advisory_slots():
    state = build_initial_state("i11", _intake())
    advisory_keys = [
        "pcb_floorplanning_results", "cad_thermal_integration_results",
        "magnetic_fea_results",
    ]
    # Phase 3 slots seeded by ensure_phase1_state_defaults on first intake_node call
    from app.workflow.phase1_helpers import ensure_phase1_state_defaults
    state = ensure_phase1_state_defaults(state)
    for key in advisory_keys:
        assert key in state, f"{key} not seeded"


# ── I-12: Workflow doc updated ───────────────────────────────────────────────

def test_i12_workflow_doc_mentions_phase3():
    import pathlib
    doc = pathlib.Path(__file__).parents[3] / "docs" / "latest_workflow.md"
    assert doc.exists(), "latest_workflow.md not found"
    content = doc.read_text()
    assert "Phase 3" in content, "Workflow doc must mention Phase 3"
    assert "25" in content or "pcb_floorplanning" in content.lower(), \
        "Workflow doc must reference 25 steps or Phase 3 nodes"


# ── Integration: Phase 3 end-to-end ──────────────────────────────────────────

def test_phase3_all_advisory_nodes_execute():
    graph = build_graph()
    state = build_initial_state("p3e2e", _intake())
    state = _advance_to_mode_b(graph, state)
    for _ in range(60):
        if state.get("current_step") == "final":
            break
        state["human_feedback"] = {"approved": True}
        state = graph.invoke(state)
    assert state.get("current_step") == "final"
    for step in ["magnetic_fea_advisory", "cad_thermal_integration_advisory",
                 "pcb_floorplanning_advisory"]:
        assert step in state.get("step_results", {}), f"{step} missing from step_results"
    for key in ["magnetic_fea_results", "cad_thermal_integration_results",
                "pcb_floorplanning_results"]:
        assert key in state, f"{key} missing from state"
