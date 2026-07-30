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

    # --- worst-case / coordination inputs (review upgrade; named defaults, override per datasheet) ---
    r25_tol_default: float = 0.20  # R25 tolerance fraction used if the part's own value is blank
    rsource_min: float = 0.0       # ohm, min documented source R (conservative 0 -> highest inrush)
    fuse_i2t_rating: float = 0.0   # A^2s, fuse pre-arcing I2t (0 -> open item, compare skipped)
    relay_make_rating_a: float = 0.0   # A, relay contact make-current rating (0 -> open item)
    relay_path_ohm: float = 0.0    # ohm, relay-path impedance for make-current (0 -> open item)
    off_time_min_ms: float = 0.0   # ms, minimum enforced off-time before restart (0 -> not guaranteed)
    restart_protection: str = ""   # "hardware" | "firmware" | "procedure" | "" (unstated)
    # --- round-2 review: startup-path resistances for the bypassed/stuck-relay inrush (0 -> OPEN) ---
    r_wiring_ohm: float = 0.0      # ohm, mains + internal wiring
    r_pcb_ohm: float = 0.0        # ohm, PCB copper in the startup path
    bridge_ifsm_a: float = 0.0    # A, rectifier single-cycle surge (IFSM) rating (0 -> OPEN)
    relay_operate_ms: float = 0.0 # ms, relay operate/settle time added to the precharge delay
    relay_delay_tol_ms: float = 0.0  # ms, control-timing tolerance added to the precharge delay


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
    r25_nom_required: float       # required *nominal* catalog R25 after -tolerance (screen floor)
    r25_tol_screen: float         # tolerance fraction used for the screen floor
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
    # Tolerance-aware NOMINAL catalog floor for the candidate screen: a part is quoted at its
    # nominal R25 but can be as low as R25·(1−tol) after tolerance, and that MINIMUM must still
    # deliver the margin'd requirement. So the required *nominal* catalog value is the margin'd
    # requirement grossed up by 1/(1−tol):  R25_nom_req = r25_pick / (1 − tol).
    # (The screen uses the default tolerance since a specific part's own tol is only known once
    # a candidate is chosen; per-part evaluation in worst_case_startup uses that part's own tol.)
    _tol_scr = s.r25_tol_default if 0.0 <= s.r25_tol_default < 1.0 else 0.0
    r25_nom_required = r25_pick / (1.0 - _tol_scr) if _tol_scr < 1.0 else r25_pick

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
        r25_nom_required=r25_nom_required,
        r25_tol_screen=_tol_scr,
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


def _parse_tol(raw, default: float) -> float:
    """Tolerance fraction from a datasheet cell ('±20%', '20%', '0.2', 20) -> 0.20; else default."""
    if raw is None:
        return default
    try:
        import re
        m = re.search(r"[-+]?\d*\.?\d+", str(raw))
        if not m:
            return default
        v = float(m.group())
        if v > 1.0:              # a percentage like 20 or 20%
            v /= 100.0
        return v if 0.0 < v < 1.0 else default
    except Exception:
        return default


def worst_case_startup(s: Spec, r: NtcResult, rec: dict) -> dict:
    """Review-upgrade worst-case + coordination proof for the SELECTED NTC part `rec`
    (keys: r25, tolerance, r_hot_mohm, imax, energy_est_J, ...). Every value derives from the
    design (Vin_pk / Cout / tau) or the part's datasheet fields; datasheet/layout-dependent items
    that have no input are returned as None (open items), never guessed.

    Returns a JSON-safe dict covering: R25 tolerance -> worst-case cold inrush (pt1), precharge
    voltage / residual relay make (pt3, pt4), warm/hot restart (pt5), fuse I2t (pt7) and the AC
    phase-angle sweep (pt10)."""
    from math import exp, sin, pi
    r25 = rec.get("r25")
    if r25 is None:
        return {}
    r25 = float(r25); rsrc = s.rsource_min
    vpk = r.vin_pk_max
    r_para = r.r_parasitic                  # known loop parasitics (line+EMI+ESR+bridge)

    def _inrush(res, para=0.0):            # cold peak into a series resistance (+optional parasitic)
        return vpk / max(res + rsrc + para, 1e-9)

    # ---- pt1: R25 tolerance -> minimum R25 -> worst-case cold inrush ----
    # Two consistent columns everywhere: CONSERVATIVE (NTC alone, no credited parasitic) and
    # REALISTIC (NTC + known loop parasitic). This removes the old §8.2.1-vs-§8.7 mismatch where
    # the tolerance worst-case ignored the parasitic while the selected-part recalc credited it.
    tol = _parse_tol(rec.get("tolerance"), s.r25_tol_default)
    tol_from_part = rec.get("tolerance") is not None and _parse_tol(rec.get("tolerance"), -1) >= 0
    r25_min = r25 * (1.0 - tol)
    i_nom = _inrush(r25); i_min = _inrush(r25_min)
    i_nom_real = _inrush(r25, r_para); i_min_real = _inrush(r25_min, r_para)

    # ---- pt3/pt4: precharge voltage at bypass close + residual relay make ----
    n_tau = s.tau_multiple
    tau = r25 * s.cout
    vcap_close = vpk * (1.0 - exp(-n_tau))         # Vcap at N*tau (fraction of rectified peak)
    v_residual = vpk - vcap_close
    i_relay_make = (v_residual / s.relay_path_ohm) if s.relay_path_ohm > 0 else None

    # ---- pt5: warm / hot restart (DB r_hot if present; else off-time requirement) ----
    r_hot = (float(rec["r_hot_mohm"]) / 1000.0) if rec.get("r_hot_mohm") else None
    i_warm = _inrush(r_hot) if r_hot else None
    # restart-permission resistance: the NTC must recover above this before restart is allowed.
    r_required = vpk / max(s.i_inrush_target, 1e-9)
    # relay stuck-closed / NTC-bypassed inrush from the SUMMED startup path (review §3.2); None -> OPEN.
    r_path_total = s.rsource_min + s.r_bridge + s.r_esr + s.r_wiring_ohm + s.r_pcb_ohm
    i_bypassed = (vpk / r_path_total) if r_path_total > 0 else None
    restart_rows = [
        {"case": "Cold 25C nominal", "r_ohm": round(r25, 3),
         "i_A": round(i_nom, 1), "i_A_real": round(i_nom_real, 1)},
        {"case": "Cold 25C minimum R25", "r_ohm": round(r25_min, 3),
         "i_A": round(i_min, 1), "i_A_real": round(i_min_real, 1)},
        {"case": "Warm/hot restart",
         "r_ohm": (round(r_hot, 3) if r_hot else None), "i_A": (round(i_warm, 1) if i_warm else None),
         "i_A_real": (round(_inrush(r_hot, r_para), 1) if r_hot else None)},
        {"case": "Bypass / stuck relay",
         "r_ohm": (round(r_path_total, 3) if r_path_total > 0 else None),
         "i_A": (round(i_bypassed, 1) if i_bypassed else None),
         "i_A_real": (round(i_bypassed, 1) if i_bypassed else None)},  # bypass path already sums all R
    ]

    # ---- pt7: startup I2t (first-order exp) at cold / min-R25 / warm ----
    def _i2t(res):                          # integral of (Vpk/R e^-t/tau)^2 = Vpk^2 tau / (2 R^2)
        rt = res + rsrc
        return (vpk ** 2 * (rt * s.cout)) / (2.0 * rt ** 2) if rt > 0 else None
    i2t_cold = _i2t(r25); i2t_min = _i2t(r25_min); i2t_warm = _i2t(r_hot) if r_hot else None
    i2t_bypass = ((vpk ** 2 * (r_path_total * s.cout)) / (2.0 * r_path_total ** 2)) if r_path_total > 0 else None
    i2t_worst = max(v for v in (i2t_cold, i2t_min, i2t_warm) if v is not None)
    fuse_ok = (s.fuse_i2t_rating > i2t_worst) if s.fuse_i2t_rating > 0 else None

    # ---- review §5: startup-path stress separated into the three electrical cases ----
    def _ifsm_ok(i):
        return (s.bridge_ifsm_a > i) if (s.bridge_ifsm_a > 0 and i is not None) else None
    stress_cases = [
        {"case": "Normal cold-start", "i_A": round(i_min, 1), "i2t": round(i2t_min, 2),
         "ifsm_ok": _ifsm_ok(i_min)},
        {"case": "Hot restart (if allowed)", "i_A": (round(i_warm, 1) if i_warm else None),
         "i2t": (round(i2t_warm, 2) if i2t_warm else None), "ifsm_ok": _ifsm_ok(i_warm)},
        {"case": "Bypass / stuck relay", "i_A": (round(i_bypassed, 1) if i_bypassed else None),
         "i2t": (round(i2t_bypass, 2) if i2t_bypass else None), "ifsm_ok": _ifsm_ok(i_bypassed)},
    ]

    # ---- review §8/§3.4: release-status taxonomy (PASS / OPEN / CHECK / BLOCKED) + rollup ----
    hard_ok = i_min <= s.i_inrush_target
    design_margin_ok = r25_min >= r_required * s.r25_margin
    st = {}
    st["nominal_cold"] = "PASS" if i_nom <= s.i_inrush_target else "BLOCKED"
    st["min_r25_cold"] = ("BLOCKED" if not hard_ok else ("PASS" if design_margin_ok else "CHECK"))
    st["pulse_energy"] = "OPEN"                 # DB energy is an estimate → datasheet confirmation required
    st["precharge_timing"] = "PASS"
    st["relay_make"] = ("OPEN" if (s.relay_path_ohm <= 0 or s.relay_make_rating_a <= 0)
                        else ("PASS" if (i_relay_make is not None and i_relay_make <= s.relay_make_rating_a) else "CHECK"))
    # Hot restart is a REQUIRED DESIGN DECISION, not a part-selection blocker: if a restart policy
    # is defined (enforced min off-time OR a stated protection method) it PASSES; otherwise it stays
    # a release-gating decision (CHECK → CONDITIONAL rollup), but it NEVER becomes BLOCKED and never
    # stops the designer from selecting an NTC.
    hot_restart_defined = (s.off_time_min_ms > 0) or bool(s.restart_protection)
    st["hot_restart"] = "PASS" if hot_restart_defined else "CHECK"
    st["fuse_i2t"] = ("OPEN" if s.fuse_i2t_rating <= 0 else ("PASS" if fuse_ok else "CHECK"))
    # bridge IFSM vs the NORMAL cases (cold-start, and hot restart if allowed); the stuck-relay fault
    # IFSM is carried by the bypass_stuck item (it is cleared by the fuse, not ridden through).
    _bridge_normal = [stress_cases[0]["ifsm_ok"], stress_cases[1]["ifsm_ok"]]
    st["bridge_surge"] = ("OPEN" if s.bridge_ifsm_a <= 0
                          else ("PASS" if all(v for v in _bridge_normal if v is not None) else "CHECK"))
    st["bypass_stuck"] = ("OPEN" if r_path_total <= 0 else "CHECK")
    st["phase_angle"] = "PASS"
    if any(v == "BLOCKED" for v in st.values()):
        overall = "BLOCKED"
    elif any(v in ("OPEN", "CHECK") for v in st.values()):
        overall = "CONDITIONAL"
    else:
        overall = "READY"

    # ---- pt10: AC phase-angle startup sweep (nominal + min-R25) ----
    phase = []
    for deg in (0, 30, 45, 60, 90):
        vth = vpk * sin(deg * pi / 180.0)
        phase.append({"deg": deg, "vin_V": round(vth, 1),
                      "i_nom_A": round(vth / max(r25 + rsrc, 1e-9), 1),
                      "i_min_A": round(vth / max(r25_min + rsrc, 1e-9), 1)})

    # Hot-restart decision packet — surfaced in the GUI/report so the designer resolves it before
    # release (it does not gate part selection).
    hot_restart_decision = {
        "defined": bool(hot_restart_defined),
        "off_time_min_ms": (s.off_time_min_ms or None),
        "restart_protection": (s.restart_protection or None),
        "i_warm_A": (round(i_warm, 1) if i_warm else None),
        "r_required_ohm": round(r_required, 3),
        "options": [
            "Enforce a minimum off-time so the NTC re-cools above R_required before restart",
            "Gate restart on a measured R(T) / bus-voltage recovery threshold",
            "Use active precharge (relay + resistor) instead of the NTC on hot restart",
            "Firmware lockout with measured proof of NTC recovery",
        ],
    }

    return {
        "r25_ohm": r25, "r25_tol": tol, "tol_from_datasheet": bool(tol_from_part),
        "r25_min_ohm": round(r25_min, 3),
        "r_parasitic_ohm": round(r_para, 3),
        "i_inrush_nom_A": round(i_nom, 1), "i_inrush_max_A": round(i_min, 1),
        "i_inrush_nom_real_A": round(i_nom_real, 1), "i_inrush_max_real_A": round(i_min_real, 1),
        "inrush_target_A": s.i_inrush_target,
        "hot_restart_decision": hot_restart_decision,
        "vcap_close_V": round(vcap_close, 1), "vcap_close_pct": round(100.0 * vcap_close / vpk, 1),
        "v_residual_V": round(v_residual, 1),
        "i_relay_make_A": (round(i_relay_make, 2) if i_relay_make is not None else None),
        "relay_make_rating_A": (s.relay_make_rating_a or None),
        "r_hot_ohm": (round(r_hot, 3) if r_hot else None),
        "i_warm_A": (round(i_warm, 1) if i_warm else None),
        "i_bypassed_A": (round(i_bypassed, 1) if i_bypassed else None),
        "r_path_total_ohm": (round(r_path_total, 3) if r_path_total > 0 else None),
        "r_required_ohm": round(r_required, 3),
        "hard_limit_ok": bool(hard_ok), "design_margin_ok": bool(design_margin_ok),
        "r25_design_margin_ohm": round(r_required * s.r25_margin, 3),
        "restart_rows": restart_rows, "stress_cases": stress_cases,
        "off_time_min_ms": (s.off_time_min_ms or None), "restart_protection": (s.restart_protection or None),
        "relay_operate_ms": (s.relay_operate_ms or None), "relay_delay_tol_ms": (s.relay_delay_tol_ms or None),
        "bridge_ifsm_a": (s.bridge_ifsm_a or None),
        "i2t_cold": round(i2t_cold, 2), "i2t_min_r25": round(i2t_min, 2),
        "i2t_warm": (round(i2t_warm, 2) if i2t_warm else None),
        "i2t_bypass": (round(i2t_bypass, 2) if i2t_bypass else None), "i2t_worst": round(i2t_worst, 2),
        "fuse_i2t_rating": (s.fuse_i2t_rating or None), "fuse_ok": fuse_ok,
        "phase_sweep": phase,
        "status": st, "overall_status": overall,
    }


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
    """Return rows: (name, pass/fail, reasons).

    Prefer the real vendor ICL database (ICL_Database.xlsx via `database.screen_catalog`); fall
    back to the built-in representative catalog below only if that database is unavailable.
    """
    try:
        from . import database as db
        rows = db.screen_catalog(s, r)
        if rows:
            return rows
    except Exception:
        pass
    out = []
    for name, r25, imax, ejoule, cmax in NTC_CATALOG:
        reasons = []
        ok = True
        # R25 must be at least the required *nominal* value so its −tolerance minimum still
        # meets the margin'd inrush requirement (tolerance-aware hard gate).
        if r25 < r.r25_nom_required:
            ok = False
            reasons.append(f"R25 {r25} < {r.r25_nom_required:.2f} ohm nominal (−tol min misses inrush target)")
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
