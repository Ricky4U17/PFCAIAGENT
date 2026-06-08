from app.exporters.report_generator import generate_final_report_markdown

def test_report_includes_phase1_advisories():
    state = {
        "project_id": "demo",
        "selected_topology": "interleaved_boost_ccm",
        "guardrail_v2_results": {"status": "passed", "blocking": False, "details": {"rules_checked": 6}},
        "supply_chain_results": {"status": "advisory_ready", "blocking": False, "details": {"recommended_choice": {"mpn": "IMW65R072M1H"}}},
        "magnetic_design_v2_results": {"status": "advisory_ready", "blocking": False, "details": {"recommended_core_family": "Kool Mµ / ferrite shortlist"}},
        "simulation_verification_results": {"status": "advisory_ready", "blocking": False, "details": {"simulation_export_available": True}},
    }
    md = generate_final_report_markdown(state)
    assert "Guardrail v2 Advisory" in md
    assert "Supply Chain Advisory" in md
    assert "Magnetic Design v2 Advisory" in md
    assert "Closed-loop Simulation Verification Advisory" in md
