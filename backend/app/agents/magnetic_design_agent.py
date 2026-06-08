from app.engines.magnetic_design_engine import design_magnetics

def node_magnetic_design(state):
    inductor = state.get("step_results", {}).get("inductor_sizing", {})
    inp = state.get("step_results", {}).get("input_processing", {})
    overrides = state.get("human_feedback", {}).get("overrides", {})
    payload = {"L_uH": inductor.get("L_required_uH", overrides.get("L", 235e-6) * 1e6), "I_pk": inp.get("Ipk", 20.0) / 2.0, "I_rms": inp.get("Irms", 10.0) / 2.0, "b_max_t": overrides.get("b_max_t", 0.6), "j_a_per_mm2": overrides.get("j_a_per_mm2", 5.0), "ae_m2_guess": overrides.get("ae_m2_guess", 250e-6)}
    return {"magnetic_design_data": design_magnetics(payload)}
