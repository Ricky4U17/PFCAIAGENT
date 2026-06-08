PRESET_NAMES = {"lower_overshoot", "faster_response", "larger_phase_margin", "lower_crossover"}

def _copy_loop(loop):
    return {"kp": loop.get("kp", 1.0), "ki": loop.get("ki", 1.0), "compensator_type": loop.get("compensator_type", "Type2"), "kpole_hz": loop.get("kpole_hz")}

def apply_preset_to_loop(loop, preset: str):
    out = _copy_loop(loop)
    kp = float(out.get("kp", 1.0)); ki = float(out.get("ki", 1.0)); kpole_hz = out.get("kpole_hz")
    if preset == "lower_overshoot":
        out["kp"] = kp * 0.90; out["ki"] = ki * 0.75; out["kpole_hz"] = kpole_hz * 0.85 if kpole_hz else kpole_hz
    elif preset == "faster_response":
        out["kp"] = kp * 1.15; out["ki"] = ki * 1.25; out["kpole_hz"] = kpole_hz * 1.10 if kpole_hz else kpole_hz
    elif preset == "larger_phase_margin":
        out["kp"] = kp * 0.88; out["ki"] = ki * 0.70; out["kpole_hz"] = kpole_hz * 0.75 if kpole_hz else kpole_hz
    elif preset == "lower_crossover":
        out["kp"] = kp * 0.80; out["ki"] = ki * 0.60; out["kpole_hz"] = kpole_hz * 0.70 if kpole_hz else kpole_hz
    return out

def apply_preset_to_tuning(tuning, preset: str, target_loop: str = "both"):
    if preset not in PRESET_NAMES:
        raise ValueError(f"Unsupported preset: {preset}")
    result = dict(tuning)
    if target_loop in {"current", "both"}:
        result["current_loop"] = apply_preset_to_loop(result.get("current_loop", {"kp": 1.0, "ki": 1.0, "compensator_type": "Type2"}), preset)
    if target_loop in {"voltage", "both"}:
        result["voltage_loop"] = apply_preset_to_loop(result.get("voltage_loop", {"kp": 1.0, "ki": 1.0, "compensator_type": "Type2"}), preset)
    return result
