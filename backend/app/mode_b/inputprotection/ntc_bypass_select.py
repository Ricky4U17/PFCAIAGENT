#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ntc_bypass_select.py
====================================================================
Inrush-Limiting NTC Thermistor + Bypass-Relay sizing for a
universal-input (90-264 Vac) totem-pole PFC front end.

Implements the design flow of "Step 20" of the reference report and
extends it with the datasheet conversions vendors actually publish
(energy in Joules  <->  "maximum switchable capacitance" at a test
voltage), precharge timing, and a candidate-matching pass.

Method / references (selection logic, not reproduced text):
  - Capacitor charge energy absorbed by the series element:
        E = 1/2 * C * Vpk^2          (classic SMPS bulk-cap charge)
  - Peak inrush set by total cold series resistance:
        I_pk ~= Vpk / R_total_cold
  - Vendors rate pulse strength either in Joules OR as a max
    capacitance switched from a reference voltage Vref (TDK/EPCOS,
    AMWEI, Vishay/Ametherm app notes). The two are linked by
        E_test = 1/2 * C_max * Vref^2
    so an application can be screened in either currency.
  - Continuous self-heat forces a bypass at kW class (TDK note:
    body can reach ~250 C); hence relay after precharge.

NOTE on catalog: the few example parts at the bottom carry
*representative* numbers only and MUST be confirmed against a live
datasheet before ordering. The math above is the deliverable; the
catalog is a convenience filter.

Run:  python3 ntc_bypass_select.py
====================================================================
"""

from __future__ import annotations
from dataclasses import dataclass, field
from math import sqrt, log


# ============================================================== #
#  CONFIG  -- edit these to match your design                    #
# ============================================================== #

@dataclass
class Spec:
    # --- line / bus ---
    vac_min: float = 90.0          # Vac, brownout corner
    vac_max: float = 264.0         # Vac, high-line corner
    vac_nom: float = 230.0         # Vac, nominal (for reference only)
    f_line: float = 60.0           # Hz
    vout_bus: float = 390.0        # Vdc, regulated bus

    # --- bulk capacitance being charged ---
    cout: float = 2200e-6          # F, bulk/output capacitance

    # --- inrush target ---
    i_inrush_target: float = 60.0  # A, peak inrush allowed cold @ vac_max

    # --- continuous operation (drives the relay / loss check) ---
    p_out: float = 1900.0          # W, rated output (set 0 to derive from i_rms_worst)
    eff: float = 0.95              # converter efficiency at brownout
    i_rms_worst: float = 20.958    # A, override; used if p_out==0

    # --- parasitics already in the loop (be conservative: assume 0
    #     for a bridgeless totem-pole unless you can guarantee them) ---
    r_line: float = 0.0            # ohm, mains + wiring
    r_emi: float = 0.0             # ohm, EMI filter series
    r_esr: float = 0.0             # ohm, bulk cap ESR
    r_bridge: float = 0.0          # ohm, rectifier (0 for bridgeless TP)

    # --- engineering margins ---
    energy_margin: float = 1.5     # require pulse rating >= margin * E_cap
    r25_margin: float = 1.10       # pick R25 >= margin * R_min (NTC alone)
    vref_pulse: float = 345.0      # V, vendor pulse-test reference (EPCOS/AMWEI ~ (230+dV)*sqrt2)

    # --- relay / precharge ---
    tau_multiple: float = 4.0      # close bypass after N*tau (cap settle)
    relay_v_margin: float = 1.25   # contact voltage rating margin over Vbus
    ambient_c: float = 45.0        # deg C, worst-case ambient


# ============================================================== #
#  CORE CALCULATIONS                                             #
# ============================================================== #

@dataclass
class NtcResult:
    vin_pk_max: float
    r_total_min: float            # min total cold R for the inrush target
    r_parasitic: float            # sum of known parasitics
    r25_required: float           # required NTC-alone cold resistance
    r25_pick: float               # recommended R25 with margin
    e_cap: float                  # J, stored/charge energy to absorb
    e_pulse_required: float       # J, with margin
    cmax_equiv_required: float    # F, equivalent "max switchable C" at vref
    i_rms_worst: float            # A, continuous worst-case
    tau: float                    # s, RC time constant at picked R25
    t_bypass: float               # s, recommended bypass-close delay
    relay_contact_v: float        # V, min contact voltage rating
    relay_contact_a: float        # A, min contact current rating
    sweep: list                   # inrush sweep rows
    loss_rows: list               # continuous-loss rows


def compute(s: Spec) -> NtcResult:
    # peak of the highest line
    vin_pk_max = sqrt(2.0) * s.vac_max

    # minimum total cold series resistance to hold the inrush target
    r_total_min = vin_pk_max / s.i_inrush_target

    # known parasitics (default 0 -> NTC carries the whole limit)
    r_parasitic = s.r_line + s.r_emi + s.r_esr + s.r_bridge
    r25_required = max(r_total_min - r_parasitic, 0.0)
    r25_pick = r25_required * s.r25_margin

    # energy the series element must absorb when charging the bulk cap
    e_cap = 0.5 * s.cout * vin_pk_max ** 2
    e_pulse_required = s.energy_margin * e_cap

    # express that energy as the "max switchable capacitance" a vendor
    # would quote at its pulse-test reference voltage:
    #     E = 1/2 * C * Vref^2  ->  C = 2E / Vref^2
    cmax_equiv_required = 2.0 * e_pulse_required / (s.vref_pulse ** 2)

    # worst-case continuous RMS input current (brownout corner)
    if s.p_out > 0:
        i_rms_worst = s.p_out / (s.eff * s.vac_min)
    else:
        i_rms_worst = s.i_rms_worst

    # precharge timing at the picked R25 (RC charge of the bulk cap)
    tau = max(r25_pick, 1e-9) * s.cout
    t_bypass = s.tau_multiple * tau

    # relay contact ratings (it bypasses the NTC and carries Irms after)
    relay_contact_v = s.vout_bus * s.relay_v_margin
    relay_contact_a = i_rms_worst  # continuous; choose AC/DC-rated headroom on top

    # inrush target sweep (parallels the report table)
    targets = [30, 40, 50, 60, 75]
    sweep = [(t, vin_pk_max / t) for t in targets]

    # continuous-loss check at assorted hot resistances
    loss_rows = [(rh, i_rms_worst ** 2 * rh) for rh in (0.05, 0.10, 0.20)]

    return NtcResult(
        vin_pk_max=vin_pk_max,
        r_total_min=r_total_min,
        r_parasitic=r_parasitic,
        r25_required=r25_required,
        r25_pick=r25_pick,
        e_cap=e_cap,
        e_pulse_required=e_pulse_required,
        cmax_equiv_required=cmax_equiv_required,
        i_rms_worst=i_rms_worst,
        tau=tau,
        t_bypass=t_bypass,
        relay_contact_v=relay_contact_v,
        relay_contact_a=relay_contact_a,
        sweep=sweep,
        loss_rows=loss_rows,
    )


# ============================================================== #
#  CANDIDATE CATALOG (representative -- verify on datasheet!)    #
# ============================================================== #
# Fields: name, R25 [ohm], I_max steady [A], energy [J], cmax@vref [F or None]
NTC_CATALOG = [
    # name              R25   Imax   E_J    Cmax(F)@~350V
    ("Ametherm SL22 series (large disc)", 5.0, 25.0, 260.0, None),
    ("Ametherm bigAMP (UL)",              5.0, 36.0, 260.0, None),
    ("TDK/EPCOS B57 high-energy disc",    8.0, 22.0, 200.0, 3300e-6),
    ("Cantherm MF72 large disc",          5.0, 20.0, 190.0, None),
    ("Ametherm MegaSurge (480Vac)",       6.0, 30.0, 400.0, None),
    ("Ametherm MS35 7R 7ohm high-energy",  7.0, 25.0, 300.0, None),
]


def screen_catalog(s: Spec, r: NtcResult):
    """Return rows: (name, pass/fail, reasons)."""
    out = []
    for name, r25, imax, ejoule, cmax in NTC_CATALOG:
        reasons = []
        ok = True
        # R25 must be at least the required NTC-alone resistance
        if r25 < r.r25_required:
            ok = False
            reasons.append(f"R25 {r25} < {r.r25_required:.2f} ohm (inrush too high)")
        # energy: either Joules or equivalent max-C must cover the event
        e_ok = ejoule >= r.e_pulse_required
        c_ok = (cmax is not None) and (cmax >= r.cmax_equiv_required)
        if not (e_ok or c_ok):
            ok = False
            reasons.append(
                f"energy {ejoule} J < {r.e_pulse_required:.0f} J req "
                f"(and Cmax {('n/a' if cmax is None else f'{cmax*1e6:.0f}uF')} "
                f"< {r.cmax_equiv_required*1e6:.0f}uF)")
        # steady current only matters if NOT bypassed; we bypass, so this
        # is informational -- flag if very small relative to precharge duty
        if imax < r.i_rms_worst and ok:
            reasons.append(f"note: Imax {imax}A < Irms {r.i_rms_worst:.1f}A "
                           f"(OK because bypassed; sized for precharge only)")
        out.append((name, ok, reasons))
    return out


# ============================================================== #
#  REPORT                                                       #
# ============================================================== #

def report(s: Spec, r: NtcResult):
    L = []
    p = L.append
    p("=" * 68)
    p(" NTC INRUSH LIMITER + BYPASS RELAY -- SIZING REPORT")
    p("=" * 68)

    p("\n[1] Operating point")
    p(f"    Line range          : {s.vac_min:.0f} - {s.vac_max:.0f} Vac @ {s.f_line:.0f} Hz")
    p(f"    Bus voltage         : {s.vout_bus:.0f} Vdc")
    p(f"    Bulk capacitance    : {s.cout*1e6:.0f} uF")
    p(f"    Peak of high line   : Vin_pk,max = sqrt(2)*{s.vac_max:.0f} = {r.vin_pk_max:.2f} V")

    p("\n[2] Cold series resistance for inrush target")
    p(f"    Target peak inrush  : {s.i_inrush_target:.0f} A (cold, @ {s.vac_max:.0f} Vac)")
    p(f"    R_total,cold (min)  : {r.vin_pk_max:.2f}/{s.i_inrush_target:.0f} = "
      f"{r.r_total_min:.3f} ohm")
    p(f"    Known parasitics    : {r.r_parasitic:.3f} ohm "
      f"(line+EMI+ESR+bridge; 0 = conservative for bridgeless TP)")
    p(f"    -> NTC R25 required : {r.r25_required:.3f} ohm")
    p(f"    -> NTC R25 PICK     : {r.r25_pick:.3f} ohm "
      f"(x{s.r25_margin:.2f} margin) ... choose nearest standard >= this")

    p("\n    Inrush target sweep (Required total cold R_min):")
    p("      I_target [A]   R_min,total [ohm]")
    for t, rr in r.sweep:
        mark = "  <- selected" if abs(t - s.i_inrush_target) < 1e-6 else ""
        p(f"        {t:>5}          {rr:>7.3f}{mark}")

    p("\n[3] Pulse-energy survival (the real datasheet filter)")
    p(f"    Charge energy E_cap = 0.5*C*Vpk^2 = "
      f"0.5*{s.cout*1e6:.0f}uF*({r.vin_pk_max:.1f})^2 = {r.e_cap:.1f} J")
    p(f"    Required pulse rating (x{s.energy_margin:.1f}) : >= {r.e_pulse_required:.1f} J")
    p(f"    Equivalent 'max switchable C' @ {s.vref_pulse:.0f} V test ref:")
    p(f"        C = 2E/Vref^2 = {r.cmax_equiv_required*1e6:.0f} uF")
    p(f"    -> On a datasheet, accept the part if EITHER")
    p(f"         energy >= {r.e_pulse_required:.0f} J   OR")
    p(f"         max-capacitance @ ~{s.vref_pulse:.0f}V >= {r.cmax_equiv_required*1e6:.0f} uF")

    p("\n[4] Continuous self-heat -> why a bypass is mandatory")
    p(f"    Worst-case input RMS current : {r.i_rms_worst:.3f} A")
    if s.p_out > 0:
        p(f"      (from P_out {s.p_out:.0f} W / eff {s.eff:.2f} / Vac_min {s.vac_min:.0f})")
    p("      R_hot [ohm]   P_loss = Irms^2*R_hot [W]")
    for rh, pl in r.loss_rows:
        p(f"        {rh:>5.2f}          {pl:>7.1f}")
    p("    -> Tens of watts in the thermistor is unacceptable: CLOSE A")
    p("       BYPASS RELAY after precharge so the NTC sees current only")
    p("       during the startup pulse.")

    p("\n[5] Bypass relay + precharge timing")
    p(f"    RC time constant at R25_pick : tau = R*C = "
      f"{r.r25_pick:.2f}*{s.cout*1e6:.0f}uF = {r.tau*1e3:.1f} ms")
    p(f"    Recommended bypass delay     : {s.tau_multiple:.0f}*tau = "
      f"{r.t_bypass*1e3:.0f} ms (let bus settle, then close)")
    p(f"    Relay contact voltage rating : >= {r.relay_contact_v:.0f} V "
      f"(x{s.relay_v_margin:.2f} over {s.vout_bus:.0f} V bus)")
    p(f"    Relay contact current rating : >= {r.relay_contact_a:.1f} A continuous "
      f"(add headroom; use AC1/DC rating)")
    p( "    Control logic: drive coil from a delay (uC timer or RC) after")
    p( "    AC-detect; ensure relay is OPEN at every fresh power-up.")

    p("\n[6] Hot-restart caution")
    p( "    A quick OFF/ON leaves the NTC warm -> lower R -> HIGHER inrush")
    p( "    than the cold calc. Mitigate with a minimum re-enable delay")
    p( "    (let it cool) OR verify warm-NTC inrush against fuse & cap I^2t.")

    p("\n[7] Datasheet filter (final)")
    p(f"    R25                  : >= {r.r25_pick:.2f} ohm")
    p(f"    Pulse energy         : >= {r.e_pulse_required:.0f} J "
      f"(or max-C >= {r.cmax_equiv_required*1e6:.0f} uF @ ~{s.vref_pulse:.0f} V)")
    p( "    Body                 : large disc (high-energy class)")
    p( "    Topology             : NTC in AC line + bypass relay after precharge")
    p(f"    Bypass delay         : ~{r.t_bypass*1e3:.0f} ms")
    p( "    Hot-restart          : add re-enable cool-down delay")

    p("\n[8] Candidate screen (REPRESENTATIVE values -- verify datasheet)")
    for name, ok, reasons in screen_catalog(s, r):
        tag = "PASS" if ok else "FAIL"
        p(f"    [{tag}] {name}")
        for rs in reasons:
            p(f"           - {rs}")

    p("\n" + "=" * 68)
    p(" NOTE: numbers are design TARGETS. Confirm R25 tolerance, energy/")
    p(" max-C, and steady current against the chosen vendor datasheet.")
    p("=" * 68)
    return "\n".join(L)


if __name__ == "__main__":
    spec = Spec()
    res = compute(spec)
    print(report(spec, res))
