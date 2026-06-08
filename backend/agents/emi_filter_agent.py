from app.engines.emi_filter_engine import design_emi_filter
from app.intake.compat import app_line_frequency_hz, compliance_leakage_limit_ma, compliance_leakage_limit_ua, app_efficiency_fraction

def node_emi_filter(state):
    app = state["intake"]["application"]; comp = state["intake"].get("compliance", {}); overrides = state.get("human_feedback", {}).get("overrides", {})
    payload = {"fsw": overrides.get("fsw", 70000.0), "Vac_max": app.get("vin_rms_max", 264.0), "line_freq_hz": app_line_frequency_hz(app), "leakage_limit_ma": compliance_leakage_limit_ma(comp), "dm_atten_db": overrides.get("dm_atten_db", 40.0)}
    result = design_emi_filter(payload)
    return {"emi_filter_data": result, "emi_constraints": {"cy_max_nf": result["results"]["cy_max_nf"]}}