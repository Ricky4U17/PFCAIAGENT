from app.engines.thermal_models import evaluate_cooling

def evaluate_thermal(state):
    inp = state.get("step_results", {}).get("input_processing", {})
    thermal = state["intake"]["thermal"]
    irms = inp.get("Irms", 10.0)
    total_loss = (irms / 2.0)**2 * 0.057 + 10.0
    return {"total_loss_w": total_loss, "cooling_assessment": evaluate_cooling(total_loss, thermal["cooling_type"])}
