from app.engines.protection_engine import design_protection
from app.intake.compat import app_line_frequency_hz, compliance_leakage_limit_ma, compliance_leakage_limit_ua, app_efficiency_fraction

def node_protection_compliance(state):
    app = state["intake"]["application"]; comp = state["intake"].get("compliance", {}); inp = state.get("step_results", {}).get("input_processing", {})
    payload = {"i_pk": inp.get("Ipk", 20.0), "v_bus": app.get("output_bus_voltage_v", 390.0), "line_freq_hz": app_line_frequency_hz(app), "vac_max_rms": app.get("vin_rms_max", 264.0), "leakage_limit_ma": compliance_leakage_limit_ma(comp)}
    return {"protection_results": design_protection(payload)}