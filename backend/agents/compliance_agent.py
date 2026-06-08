from app.intake.compat import app_line_frequency_hz, compliance_leakage_limit_ma, compliance_leakage_limit_ua, app_efficiency_fraction
def evaluate_compliance(state):
    comp = state["intake"]["compliance"]
    standards = []
    if comp.get("conducted_emi_required") or comp.get("radiated_emi_required"): standards.append("EMC product-standard family must be identified")
    if comp.get("surge_required"): standards.append("IEC 61000-4-5")
    return {"likely_standards": standards, "risk_flags": ["Tight leakage-current limit may constrain EMI filter design."] if comp.get("leakage_current_limit_ma", 99) < 1.0 else [], "notes": ["Design-oriented compliance screen only."]}