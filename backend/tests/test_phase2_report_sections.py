from app.exporters.report_generator import generate_final_report_markdown

def test_report_includes_phase2_advisories():
    state = {
        "project_id": "demo",
        "selected_topology": "interleaved_boost_ccm",
        "layout_parasitics_results": {"status": "advisory_ready", "blocking": False, "details": {"impact_assessment": {"ringing_risk": "moderate"}}},
        "firmware_generation_results": {"status": "incomplete", "blocking": False, "details": {"notes": ["analog mode selected"]}},
        "reliability_mtbf_results": {"status": "advisory_ready", "blocking": False, "details": {"reliability_summary": {"estimated_mtbf_hours": 1000000}}},
    }
    md = generate_final_report_markdown(state)
    assert "Layout Parasitics Advisory" in md
    assert "Firmware Generation Advisory" in md
    assert "Reliability / MTBF Advisory" in md
