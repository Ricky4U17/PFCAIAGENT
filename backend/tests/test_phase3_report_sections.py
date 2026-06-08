from app.exporters.report_generator import generate_final_report_markdown

def test_report_includes_phase3_advisories():
    state = {
        "project_id": "demo",
        "selected_topology": "interleaved_boost_ccm",
        "pcb_floorplanning_results": {"status": "advisory_ready", "blocking": False, "details": {"floorplan_recommendations": {"critical_commutation_loop_priority": "highest"}}},
        "cad_thermal_integration_results": {"status": "advisory_ready", "blocking": False, "details": {"mechanical_summary": {"required_thermal_resistance_c_per_w": 0.55}}},
        "magnetic_fea_results": {"status": "advisory_ready", "blocking": False, "details": {"fea_screening_summary": {"estimated_local_flux_crowding_risk": "moderate"}}},
    }
    md = generate_final_report_markdown(state)
    assert "PCB Floorplanning Advisory" in md
    assert "CAD Thermal Integration Advisory" in md
    assert "Magnetic FEA Advisory" in md
