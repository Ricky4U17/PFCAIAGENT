"""
spice_backend.py — I-8: stable SpiceBackend protocol.
Swap in a real SPICE runner by implementing SpiceBackend.run() and passing it to
build_closed_loop_simulation_advisory(state, backend=YourBackend()).
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Protocol, runtime_checkable


@dataclass
class SpiceResult:
    voltage_overshoot_percent: Optional[float] = None
    current_overshoot_percent: Optional[float] = None
    voltage_settling_time_s:   Optional[float] = None
    current_settling_time_s:   Optional[float] = None
    thd_percent:               Optional[float] = None
    voltage_loop_crossover_hz: Optional[float] = None
    backend_name:   str  = "unknown"
    simulation_ran: bool = False
    netlist_used:   bool = False
    notes:          list = field(default_factory=list)
    raw_output:     Dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class SpiceBackend(Protocol):
    @property
    def name(self) -> str: ...
    def run(self, state: Dict[str, Any]) -> SpiceResult: ...


class ScaffoldBackend:
    name = "scaffold"

    def run(self, state: Dict[str, Any]) -> SpiceResult:
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

        v_os  = _f(vm, "overshoot_percent")
        c_os  = _f(cm, "overshoot_percent")
        sim   = state.get("simulation_artifacts", {})
        netlist_ok = bool(isinstance(sim, dict) and sim.get("simplis_netlist"))

        return SpiceResult(
            voltage_overshoot_percent = round(v_os * 1.08, 3) if v_os is not None else None,
            current_overshoot_percent = round(c_os * 1.05, 3) if c_os is not None else None,
            voltage_settling_time_s   = _f(vm, "settling_time_s"),
            current_settling_time_s   = _f(cm, "settling_time_s"),
            thd_percent               = 1.2 if netlist_ok else None,
            voltage_loop_crossover_hz = _f(vm, "crossover_hz"),
            backend_name   = self.name,
            simulation_ran = False,
            netlist_used   = netlist_ok,
            notes = [
                "Scaffold backend: no real SPICE simulation executed.",
                "Implement SpiceBackend and pass backend= to enable real simulation.",
            ],
        )
