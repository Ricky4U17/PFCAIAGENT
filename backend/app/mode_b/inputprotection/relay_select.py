"""
relay_select.py — bypass-relay selection for the NTC inrush limiter.

The relay shorts the NTC out once the bus has precharged, so it is not a general-purpose contactor
choice: the duty is one make per start into a partly-charged bus, then continuous conduction of the
line current with the NTC out of circuit.

THREE gates select the part, and only three. Each is decided by a value the vendor table carries
for every part, so the screen is never guessing:

  1. Contact current    — the contact must carry the worst-case continuous input RMS with margin.
  2. Switching voltage  — rating >= the highest voltage across the open contact (the line peak).
  3. Coil supply        — the coil voltage must be a rail the board actually has.

Everything else about the relay is CONFIRMED BY THE DESIGNER against figures this module computes,
not screened here (see `confirmation_rows`):

  * Make current at closure — the current the CONTACT carries the instant it closes. Closing the
    contact is what shorts the NTC out, so the NTC is NOT in this path:
    I_make = (V_in,pk - V_bus)/(R_par + R_relay). No relay in this catalogue publishes a make or
    inrush rating, so there is nothing to screen against; the duty is stated and the designer
    confirms it with the vendor or on the bench.
  * Operate timing — the contact closes at t_bypass + t_operate. Whether that lands after the bus
    has reached its final value is system timing the designer owns, not a property of the part.
  * Minimum on / off time — taken as 2x the operate time (a settling allowance covering bounce),
    which is why neither is asked for as an input.

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
    (3, "Coil supply available"),
]
# Multiple of the operate time taken as the relay's minimum on- and off-time. A contact needs time
# to settle after bounce before the coil state is changed again; twice the operate time is the
# conventional allowance and removes two inputs the designer would otherwise have to supply.
MIN_DWELL_MULTIPLE = 2.0


@dataclass
class RelaySpec:
    """Everything the relay duty depends on — all carried in from the NTC sizing, not re-derived."""
    i_rms_worst: float = 0.0          # A, worst-case continuous input RMS
    vin_pk_max: float = 0.0           # V, line peak (max voltage across the open contact)
    v_bus_precharged: float = 0.0     # V, bus voltage at the moment of closure
    r_path_ohm: float = 0.0           # ohm, make path = loop parasitic + the relay's own contact and
                                      # wiring resistance. NOT the NTC — the contact shorts it out.
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

    # Residual make current: the contact closes across whatever is still dropped across the NTC, and
    # in doing so shorts the NTC out - so the current that flows through the CONTACT is limited by
    # the loop, not by the NTC. Once the bus has precharged to near the peak this is small - that is
    # the whole point of waiting - but it is NOT zero, and it is what welds contacts when the delay
    # is too short.
    i_make = None
    if spec.r_path_ohm > 0:
        dv = max(spec.vin_pk_max - spec.v_bus_precharged, 0.0)
        i_make = dv / spec.r_path_ohm

    # The relay must be closed by the time the precharge window ends.
    t_op_max = spec.t_bypass_ms if spec.t_bypass_ms > 0 else None

    notes = []
    if spec.r_path_ohm <= 0:
        notes.append("No loop resistance supplied (Section 8.2 Loop R) — make current cannot be "
                     "evaluated.")
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

    cv = p.get("coil_v_V")
    if req.coil_supply_v is None:
        rows.append({"n": 3, "name": GATES[2][1], "requirement": "coil rail must be declared",
                     "result": (f"{cv:g} V coil" if cv is not None else "—"),
                     "status": "DATA MISSING"})
    else:
        ok = None if (cv is None or not part) else abs(cv - req.coil_supply_v) < 0.51
        rows.append({"n": 3, "name": GATES[2][1],
                     "requirement": f"coil = {req.coil_supply_v:g} V rail",
                     "result": (f"{cv:g} V" if cv is not None else "—"), "status": _st(ok)})
    return rows


def confirmation_rows(part: dict | None, req: RelayRequirement, spec: RelaySpec) -> list[dict]:
    """What the DESIGNER confirms about the chosen relay, with the figure to confirm it against.

    These are not gates and carry no verdict. Two of them cannot be screened because the data does
    not exist (no relay in this catalogue publishes a make rating), and one is system timing rather
    than a property of the part. Stating the number is the useful thing; deciding is the designer's.
    """
    p = part or {}
    to = p.get("t_operate_ms")
    dwell = (to * MIN_DWELL_MULTIPLE) if to else None
    rows = [
        {"item": "Contact make current",
         "figure": (f"{req.i_make_A:g} A at closure" if req.i_make_A is not None
                    else "needs the loop resistance"),
         "confirm": "that the contact can make this current once per start — no part in this "
                    "catalogue publishes a make/inrush rating, so confirm with the vendor or "
                    "measure at closure"},
        {"item": "Closure vs bus charged",
         "figure": (f"contact closes at t_bypass + t_operate = {spec.t_bypass_ms:g} + {to:g} = "
                    f"{spec.t_bypass_ms + to:g} ms" if (to and spec.t_bypass_ms)
                    else "needs the operate time"),
         "confirm": "that the bus has reached its final value by then — this is system timing, "
                    "not a property of the relay"},
        {"item": "Minimum on / off time",
         "figure": (f"{dwell:g} ms each ({MIN_DWELL_MULTIPLE:g} x the {to:g} ms operate time)"
                    if dwell else "needs the operate time"),
         "confirm": "that the control never commands the coil to change state inside this window"},
    ]
    return rows


def _rank_all(parts: list[dict], spec: RelaySpec, req: RelayRequirement,
              drop_under_rated: bool) -> list[dict]:
    order = {"PASS": 0, "CONDITIONAL": 1, "DATA MISSING": 2, "FAIL": 3}
    scored = []
    for p in parts:
        if spec.contact_form and (p.get("contact_form") or "") != spec.contact_form:
            continue
        if spec.mounting and (p.get("mounting") or "") != spec.mounting:
            continue
        # A part whose PUBLISHED contact rating is below the computed requirement cannot be used at
        # any margin, so it is dropped from the list rather than ranked last — the designer should
        # not have to read past parts that are already excluded. A part that does not publish a
        # rating is NOT dropped: that is DATA MISSING, not a violation, and the standing convention
        # is that missing data never removes a part from selection.
        ci = p.get("contact_i_A")
        if drop_under_rated and ci is not None and req.i_contact_min_A > 0 \
                and ci < req.i_contact_min_A:
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
    return scored


def screen(parts: list[dict], spec: RelaySpec, req: RelayRequirement,
           top: int = 25) -> tuple[list[dict], dict]:
    """Rank the catalogue: pass-first, then conditional, then data-missing.

    Parts rated below the computed contact-current requirement are hidden. NEVER-EMPTY is still
    guaranteed: if nothing in the catalogue clears the requirement the filter is lifted and the
    closest parts are returned with `fallback` set, so the designer always has something to select
    and can see how far short the catalogue falls.

    Returns (rows, meta) where meta carries `hidden`, `fallback` and the requirement used.
    """
    kept = _rank_all(parts, spec, req, drop_under_rated=True)
    fallback = not kept
    if fallback:
        kept = _rank_all(parts, spec, req, drop_under_rated=False)
    considered = len(_rank_all(parts, spec, req, drop_under_rated=False)) if not fallback else len(kept)
    return kept[:top], {"hidden": max(considered - len(kept), 0),
                        "fallback": bool(fallback),
                        "i_contact_min_A": req.i_contact_min_A,
                        "considered": considered}


def overall_status(rows: list[dict]) -> str:
    if any(r["status"] == "FAIL" for r in rows):
        return "FAIL"
    if any(r["status"] == "DATA MISSING" for r in rows):
        return "DATA MISSING"
    if any(r["status"] == "CONDITIONAL" for r in rows):
        return "CONDITIONAL"
    return "PASS"
