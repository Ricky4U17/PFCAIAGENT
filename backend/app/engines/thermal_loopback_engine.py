from typing import Dict, Any

def evaluate_bidirectional_thermal(inputs: Dict[str, Any]) -> Dict[str, Any]:
    pout = float(inputs.get("Pout", 1700.0)); eff = float(inputs.get("eff", 0.95)); max_rise_c = float(inputs.get("max_rise_c", 40.0)); max_enclosure_rth = float(inputs.get("max_enclosure_rth_c_per_w", 0.5)); fsw = float(inputs.get("fsw", 70000.0))
    total_loss = pout * (1.0 - eff); required_rth = max_rise_c / max(total_loss, 1e-12)
    if required_rth < max_enclosure_rth:
        return {"status": "failed", "thermal_data": {"total_loss_w": total_loss, "rth_required_c_per_w": required_rth}, "loopback": {"action": "recalculate_hardware", "reason": "Lower fsw to reduce switching losses or increase magnetic/device size.", "suggested_overrides": {"fsw": max(fsw * 0.8, 20000.0)}}}
    return {"status": "passed", "thermal_data": {"total_loss_w": total_loss, "rth_required_c_per_w": required_rth}, "loopback": None}
