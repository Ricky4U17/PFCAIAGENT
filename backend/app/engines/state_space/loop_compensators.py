import math
import numpy as np

def pi_compensator(kp: float, ki: float):
    return np.array([kp, ki], dtype=float), np.array([1.0, 0.0], dtype=float)

def type2_compensator(k: float, fz_hz: float, fp_hz: float):
    wz, wp = 2*math.pi*fz_hz, 2*math.pi*fp_hz
    return np.array([k/wz, k], dtype=float), np.array([1.0/wp, 1.0, 0.0], dtype=float)

def recommend_current_loop_compensator(topology: str, fsw_hz: float, controller_mode: str = "analog"):
    if topology == "totem_pole_ccm": return "Type2", fsw_hz/10.0
    if topology in {"single_boost_ccm","interleaved_boost_ccm"}: return "Type2", fsw_hz/10.0 if controller_mode=="digital" else fsw_hz/12.0
    return "PI", fsw_hz/20.0

def recommend_voltage_loop_compensator(topology: str, line_freq_hz: float, controller_mode: str = "analog"):
    return "Type2", max(5.0, line_freq_hz/10.0)

def _apply_override_to_pi(override: dict):
    kp = float(override.get("kp",1.0)); ki = float(override.get("ki",1.0)); num, den = pi_compensator(kp, ki); return "PI", num, den, {"kp": kp, "ki": ki, "target_fc_hz": None}

def _apply_override_to_type2(override: dict, default_target_fc: float):
    kp = float(override.get("kp",1.0)); ki = float(override.get("ki",1.0))
    wz = ki / max(kp, 1e-12); fz = wz / (2*math.pi); fp = float(override.get("kpole_hz", default_target_fc*5.0))
    num, den = type2_compensator(kp, fz, fp)
    return "Type2", num, den, {"kp": kp, "ki": ki, "kz_hz": fz, "kpole_hz": fp, "target_fc_hz": default_target_fc}

def build_current_loop_compensator(topology: str, fsw_hz: float, controller_mode: str = "analog", override: dict | None = None):
    ctype, target_fc = recommend_current_loop_compensator(topology, fsw_hz, controller_mode)
    if override:
        forced = override.get("compensator_type", ctype)
        if forced in {"PI","Type1"}: return _apply_override_to_pi(override)
        return _apply_override_to_type2(override, target_fc)
    if ctype == "PI":
        kp, ki = 1.0, 2*math.pi*target_fc; num, den = pi_compensator(kp, ki); return ctype, num, den, {"kp": kp, "ki": ki, "target_fc_hz": target_fc}
    fz, fp, k = target_fc/5.0, target_fc*5.0, 1.0; num, den = type2_compensator(k, fz, fp); return ctype, num, den, {"kp": k, "ki": 2*math.pi*fz*k, "kz_hz": fz, "kpole_hz": fp, "target_fc_hz": target_fc}

def build_voltage_loop_compensator(topology: str, line_freq_hz: float, controller_mode: str = "analog", override: dict | None = None):
    ctype, target_fc = recommend_voltage_loop_compensator(topology, line_freq_hz, controller_mode)
    if override:
        forced = override.get("compensator_type", ctype)
        if forced in {"PI","Type1"}: return _apply_override_to_pi(override)
        return _apply_override_to_type2(override, target_fc)
    fz, fp, k = target_fc/3.0, target_fc*10.0, 1.0; num, den = type2_compensator(k, fz, fp); return ctype, num, den, {"kp": k, "ki": 2*math.pi*fz*k, "kz_hz": fz, "kpole_hz": fp, "target_fc_hz": target_fc}
