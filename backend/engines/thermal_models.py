def evaluate_cooling(total_loss_w: float, cooling_type: str):
    thermal_map = {"natural_convection": 6.0, "fan_cooled": 2.5, "conduction_cooled": 3.5}
    rth = thermal_map.get(cooling_type, 4.0)
    rise = total_loss_w * rth
    risk = "low" if rise < 30 else "medium" if rise < 60 else "high"
    return {"cooling_type": cooling_type, "thermal_resistance_c_per_w": rth, "temperature_rise_c": rise, "risk_level": risk}
