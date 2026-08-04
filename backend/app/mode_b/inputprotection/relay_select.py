"""
relay_select.py — bypass-relay selection for the NTC inrush limiter.

The relay shorts the NTC out once the bus has precharged, so it is not a general-purpose contactor
choice: the duty is one make per start into a partly-charged bus, then continuous conduction of the
line current with the NTC out of circuit.

Five gates, in the order they constrain the choice:

  1. Contact current    — the contact must carry the worst-case continuous input RMS with margin.
  2. Switching voltage  — rating >= the highest voltage across the open contact (the line peak).
  3. Make current       — the residual precharge current at the instant of closure. This is the
                          gate that actually distinguishes relays here: the contact closes onto
                          (V_in,pk - V_bus)/(R_path), and welding is the failure mode.
  4. Coil supply        — the coil voltage must be a rail the board actually has.
  5. Timing             — operate time must fit inside the precharge delay, so the contact does not
                          close before the bus has charged.

Convention (project rule D0b): a gate whose input is missing reports DATA MISSING and the part
stays SELECTABLE. Only a gate that is genuinely violated reports FAIL. A missing datasheet value
must never make the whole catalogue un-selectable.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


GATES = [
    (1, "Contact current rating"),
    (2, "Switching voltage rating"),
    (3, "Make current at closure"),
    (4, "Coil supply available"),
    (5, "Operate timing vs precharge delay"),
]


@dataclass
class RelaySpec:
    """Everything the relay duty depends on — all carried in from the NTC sizing, not re-derived."""
    i_rms_worst: float = 0.0          # A, worst-case continuous input RMS
    vin_pk_max: float = 0.0           # V, line peak (max voltage across the open contact)
    v_bus_precharged: float = 0.0     # V, bus voltage at the moment of closure
    r_path_ohm: float = 0.0           # ohm, resistance in the make path (loop parasitic + NTC)
    t_bypass_ms: float = 0.0          # ms, precharge delay the relay must close within
    coil_supply_v: Optional[float] = None    # V, the rail available on the board (None = unknown)
    ambient_c: float = 45.0           # degC
    current_margin: float = 1.5       # x, contact rating over worst-case RMS
    voltage_margin: float = 1.1       # x, switching rating over the line peak
    contact_form: Optional[str] = None       # designer filter, e.g. "SPST-NO (1 Form A)"
    mounting: Optional[str] = None           # designer filter


@dataclass
class RelayRequirement:
    i_contact_min_A: float
    v_switch_min_V: float
    i_make_A: Optional[float]
    t_operate_max_ms: Optional[float]
    coil_supply_v: Optional[float]
    notes: list = field(default_factory=list)


def requirements(spec: RelaySpec) -> RelayRequirement:
    """Turn the duty into the numbers a catalogue part must clear. Derived BEFORE any part is named."""
    i_contact_min = spec.i_rms_worst * spec.current_margin
    v_switch_min = spec.vin_pk_max * spec.voltage_margin

    # Residual make current: the contact closes across whatever is still dropped over the NTC and
    # the loop resistance. Once the bus has precharged to near the peak this is small - that is the
    # whole point of waiting - but it is NOT zero, and it is what welds contacts when the delay is
    # too short.
    i_make = None
    if spec.r_path_ohm > 0:
        dv = max(spec.vin_pk_max - spec.v_bus_precharged, 0.0)
        i_make = dv / spec.r_path_ohm

    # The relay must be closed by the time the precharge window ends.
    t_op_max = spec.t_bypass_ms if spec.t_bypass_ms > 0 else None

    notes = []
    if spec.r_path_ohm <= 0:
        notes.append("Make-path resistance not supplied — make current cannot be evaluated.")
    if spec.coil_supply_v is None:
        notes.append("Coil supply rail not declared — coil-voltage gate is informational.")
    return RelayRequirement(round(i_contact_min, 3), round(v_switch_min, 1),
                            (round(i_make, 2) if i_make is not None else None),
                            t_op_max, spec.coil_supply_v, notes)


def _st(ok: Optional[bool], conditional: bool = False) -> str:
    """Canonical status vocabulary (see doc_report_builder.STATUS_WORDS)."""
    if ok is None:
        return "DATA MISSING"
    if not ok:
        return "FAIL"
    return "CONDITIONAL" if conditional else "PASS"


def gate_rows(part: dict | None, req: RelayRequirement, spec: RelaySpec) -> list[dict]:
    """Per-gate verdict for one part, or the bare requirement when `part` is None."""
    p = part or {}
    rows = []

    ci = p.get("contact_i_A")
    rows.append({"n": 1, "name": GATES[0][1],
                 "requirement": f">= {req.i_contact_min_A:g} A",
                 "result": (f"{ci:g} A" if ci is not None else "—"),
                 "status": _st(None if (ci is None or not part) else ci >= req.i_contact_min_A)})

    sv = p.get("switch_v_V")
    rows.append({"n": 2, "name": GATES[1][1],
                 "requirement": f">= {req.v_switch_min_V:g} V",
                 "result": (f"{sv:g} V" if sv is not None else "—"),
                 "status": _st(None if (sv is None or not part) else sv >= req.v_switch_min_V)})

    # Gate 3 compares against the CONTACT rating: a datasheet make/inrush rating is rarely given in
    # this table, so passing on the continuous rating is CONDITIONAL, not a clean pass.
    if req.i_make_A is None:
        rows.append({"n": 3, "name": GATES[2][1], "requirement": "make current must be evaluated",
                     "result": "path R not supplied", "status": "DATA MISSING"})
    else:
        ok = None if (ci is None or not part) else ci >= req.i_make_A
        rows.append({"n": 3, "name": GATES[2][1],
                     "requirement": f">= {req.i_make_A:g} A at closure",
                     "result": (f"{ci:g} A continuous rating" if ci is not None else "—"),
                     "status": _st(ok, conditional=bool(ok))})

    cv = p.get("coil_v_V")
    if req.coil_supply_v is None:
        rows.append({"n": 4, "name": GATES[3][1], "requirement": "coil rail must be declared",
                     "result": (f"{cv:g} V coil" if cv is not None else "—"),
                     "status": "DATA MISSING"})
    else:
        ok = None if (cv is None or not part) else abs(cv - req.coil_supply_v) < 0.51
        rows.append({"n": 4, "name": GATES[3][1],
                     "requirement": f"coil = {req.coil_supply_v:g} V rail",
                     "result": (f"{cv:g} V" if cv is not None else "—"), "status": _st(ok)})

    to = p.get("t_operate_ms")
    if req.t_operate_max_ms is None:
        rows.append({"n": 5, "name": GATES[4][1], "requirement": "precharge delay must be known",
                     "result": (f"{to:g} ms" if to is not None else "—"), "status": "DATA MISSING"})
    else:
        ok = None if (to is None or not part) else to <= req.t_operate_max_ms
        rows.append({"n": 5, "name": GATES[4][1],
                     "requirement": f"operate <= {req.t_operate_max_ms:g} ms precharge delay",
                     "result": (f"{to:g} ms" if to is not None else "—"), "status": _st(ok)})
    return rows


def screen(parts: list[dict], spec: RelaySpec, req: RelayRequirement, top: int = 25) -> list[dict]:
    """Rank the catalogue: never-empty, pass-first, then conditional, then data-missing."""
    order = {"PASS": 0, "CONDITIONAL": 1, "DATA MISSING": 2, "FAIL": 3}
    scored = []
    for p in parts:
        if spec.contact_form and (p.get("contact_form") or "") != spec.contact_form:
            continue
        if spec.mounting and (p.get("mounting") or "") != spec.mounting:
            continue
        rows = gate_rows(p, req, spec)
        worst = max(order.get(r["status"], 2) for r in rows)
        verdict = {0: "PASS", 1: "CONDITIONAL", 2: "DATA MISSING", 3: "FAIL"}[worst]
        scored.append({**p, "gates": rows, "verdict": verdict,
                       "_rank": (worst,
                                 # prefer the smallest contact that still clears the requirement:
                                 # an oversized relay costs board area and coil power for nothing
                                 p.get("contact_i_A") or 9e9,
                                 p.get("coil_i_mA") or 9e9)})
    scored.sort(key=lambda x: x["_rank"])
    for x in scored:
        x.pop("_rank", None)
    return scored[:top]


def overall_status(rows: list[dict]) -> str:
    if any(r["status"] == "FAIL" for r in rows):
        return "FAIL"
    if any(r["status"] == "DATA MISSING" for r in rows):
        return "DATA MISSING"
    if any(r["status"] == "CONDITIONAL" for r in rows):
        return "CONDITIONAL"
    return "PASS"
