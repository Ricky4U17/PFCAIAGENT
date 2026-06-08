from app.intake.topology_selector import select_topology
from app.workflow.mode_a_validation import validate_topology_specific_inputs

def high_power_intake(control="Recommend", tech=None):
    if tech is None:
        tech = ["Si", "SiC", "GaN"]
    return {
        "application": {
            "vin_rms_min": 90.0, "vin_rms_max": 264.0, "nominal_line_frequency_hz": 60.0,
            "input_frequency_range_hz_min": 47.0, "input_frequency_range_hz_max": 63.0,
            "output_bus_voltage_v": 390.0, "dc_bus_voltage_ripple_pk_pk_v": 20.0,
            "output_power_w_nom": 3600.0, "output_power_w_low_line": 1700.0, "output_power_w_high_line": 3600.0,
            "power_factor_target": 0.99, "efficiency_target_percent": 98.0, "hold_up_time_ms": 20.0,
        },
        "thermal": {"cooling_type": "fan_cooled", "ambient_temp_c_max": 50.0, "max_temp_rise_c": 45.0, "hotspot_limit_c": 110.0, "max_enclosure_rth_c_per_w": 0.5},
        "mechanical": {"height_limit_mm": 40.0, "power_density_priority": 8},
        "compliance": {"conducted_emi_class": "FCC Class B", "radiated_emi_class": "FCC Class B", "harmonics_class": "EN61000-3-2", "surge_requirement": "1 KV Line to Line / 2KV Line to Ground Class A", "leakage_current_limit_ua": 3500.0, "application_class": "Industrial", "semi_f47_required": False},
        "control": {"control_preference": control},
        "business": {"cost_priority": 7, "efficiency_priority": 9, "power_density_priority": 8, "implementation_risk_priority": 8, "preferred_switch_technology": tech},
        "supply": {"preferred_vendors": [], "avoid_vendors": []},
    }

def test_high_power_biases_interleaved_over_single_boost():
    result = select_topology(high_power_intake())
    assert result["ranking"][0]["topology"] != "single_boost_ccm"

def test_ttp_digital_wbg_case_scores_ttp_family_in_top3():
    result = select_topology(high_power_intake(control="Digital", tech=["SiC", "GaN"]))
    top3 = [x["topology"] for x in result["top_3"]]
    assert any(t in top3 for t in ["totem_pole_ccm", "totem_pole_interleaved_ccm"])

def test_ccm_mini_intake_validation():
    ok, errors = validate_topology_specific_inputs("ccm", {"switching_frequency_style": "fixed", "recommended_frequency_hz": 70000.0, "default_crest_ripple_ratio": 0.2})
    assert ok and not errors

def test_crcm_requires_variable_range():
    ok, errors = validate_topology_specific_inputs("crcm", {"switching_frequency_style": "variable", "default_crest_ripple_ratio": 2.0})
    assert not ok and errors

def test_dcm_requires_crest_ratio_above_two():
    ok, errors = validate_topology_specific_inputs("dcm", {"switching_frequency_style": "fixed", "recommended_frequency_hz": 80000.0, "default_crest_ripple_ratio": 1.8})
    assert not ok and errors
