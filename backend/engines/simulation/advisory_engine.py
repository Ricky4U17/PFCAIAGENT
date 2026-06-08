"""advisory_engine.py — I-8: uses SpiceBackend protocol."""
from __future__ import annotations
from typing import Any, Dict, Optional
from app.engines.simulation.spice_backend import ScaffoldBackend, SpiceBackend, SpiceResult


def build_closed_loop_simulation_advisory(
    state: Dict[str, Any],
    backend: Optional[SpiceBackend] = None,
) -> Dict[str, Any]:
    if backend is None:
        backend = ScaffoldBackend()
    result: SpiceResult = backend.run(state)

    ssd     = state.get("state_space_data", {})
    payload = ssd.get("frontend_payload", {})
    vm = payload.get("voltage_loop", {}).get("metrics", {})
    cm = payload.get("current_loop", {}).get("metrics", {})

    def _f(d: dict, k: str) -> Optional[float]:
        try:
            v = d.get(k)
            return float(v) if v is not None else None
        except (TypeError, ValueError):
            return None

    def _delta(a: Optional[float], b: Optional[float]) -> Optional[float]:
        return round(a - b, 3) if a is not None and b is not None else None

    v_os_m = _f(vm, "overshoot_percent")
    c_os_m = _f(cm, "overshoot_percent")

    correlation = {
        "voltage_overshoot_math_percent":  v_os_m,
        "voltage_overshoot_sim_percent":   result.voltage_overshoot_percent,
        "voltage_overshoot_delta_percent": _delta(result.voltage_overshoot_percent, v_os_m),
        "current_overshoot_math_percent":  c_os_m,
        "current_overshoot_sim_percent":   result.current_overshoot_percent,
        "current_overshoot_delta_percent": _delta(result.current_overshoot_percent, c_os_m),
        "voltage_settling_math_s":         _f(vm, "settling_time_s"),
        "voltage_settling_sim_s":          result.voltage_settling_time_s,
        "current_settling_math_s":         _f(cm, "settling_time_s"),
        "current_settling_sim_s":          result.current_settling_time_s,
        "voltage_loop_crossover_math_hz":  _f(vm, "crossover_hz"),
        "voltage_loop_crossover_sim_hz":   result.voltage_loop_crossover_hz,
        "thd_estimate_percent":            result.thd_percent,
    }

    return {
        "status":            "advisory_ready" if (result.simulation_ran or payload) else "incomplete",
        "blocking":          False,
        "backend_name":      result.backend_name,
        "simulation_ran":    result.simulation_ran,
        "netlist_used":      result.netlist_used,
        "correlation_summary": correlation,
        "notes":             result.notes,
        "recommended_next_upgrades": [
            "Implement NgspiceBackend or PySpiceBackend conforming to SpiceBackend protocol.",
            "Pass it to build_closed_loop_simulation_advisory(state, backend=...).",
        ],
    }
