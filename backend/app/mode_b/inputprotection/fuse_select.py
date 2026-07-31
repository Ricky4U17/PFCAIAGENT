#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fuse_select.py
====================================================================
Line-fuse selection + coordination for the PFC front end. The fuse is
the upstream protective element for the whole input stage, screened
against SIX gates (specs/NTC/NTC Improvement.docx, designer review):

  1. Voltage rating        — V_ac rating >= high-line V_in,max.
  2. Continuous RMS current— rating carries the worst-case input RMS
     with margin AND after temperature de-rating (the "75 % loading"
     rule: a cartridge fuse is de-rated ~25 % at its reference ambient
     to avoid nuisance opening).
  3. Startup / inrush I2t  — melting (pre-arcing) I2t must EXCEED the
     NTC-limited startup I2t with margin.  NOTE: the fuse does NOT
     need a current rating above the inrush PEAK — a fuse survives a
     high peak if the pulse is short and the I2t margin holds.  The
     peak is reported for context only (see `inrush_gates_rating`).
  4. Breaking capacity     — >= available short-circuit current at the
     installation.
  5. Fault coordination    — must safely interrupt what a FAILED
     protection device presents: MOV / GDT fail-short, and a stuck
     bypass relay.  Ch9 fail-short safety closes here.
  6. Thermal implementation— the re-rated current at the real maximum
     ambient PLUS fuseholder / PCB / enclosure rise must still cover
     the load, and the fuse body must stay inside its temperature
     limit.

Every threshold derives from the design (line, I_rms) or a named,
overridable margin; a missing datasheet field (e.g. melting I2t) or a
missing site input (fault current, ambient, fuseholder rise) is
surfaced as DATA MISSING / OPEN, never silently passed.  The
per-candidate screen lives in database.screen_table_fuse against the
vendor Fuse_Database.xlsx.

Run:  python3 fuse_select.py --selftest
====================================================================
"""

from __future__ import annotations
from dataclasses import dataclass
import sys


# ── named, overridable defaults (no magic numbers inline) ─────────────────────
DEFAULT_LOAD_FACTOR = 0.75        # continuous load <= 75 % of rating at the reference ambient
DEFAULT_DERATE_PER_C = 0.5        # %/degC re-rating slope used only when the datasheet curve is absent
DEFAULT_T_RATING_REF_C = 25.0     # ambient the catalog current rating is stated at

# Gate registry — the report / GUI render these labels so the six gates stay one definition.
GATES = (
    (1, "Voltage rating",         "V_ac rating >= high-line V_in,max"),
    (2, "Continuous RMS current", "I_rated >= margin x I_rms, and I_rms <= load_factor x I_rated after de-rating"),
    (3, "Startup / inrush I2t",   "melting I2t > i2t_margin x worst-case startup I2t"),
    (4, "Breaking capacity",      "breaking capacity >= available fault current at the installation"),
    (5, "Fault coordination",     "breaking capacity >= MOV/GDT fail-short and stuck-relay/bypass fault current"),
    (6, "Thermal implementation", "re-rated current at max ambient + fuseholder rise covers the load, body within limit"),
)


@dataclass
class FuseSpec:
    # ── design / line ────────────────────────────────────────────────────────
    vac_max: float = 264.0             # Vac high-line corner (AC voltage rating gate)
    i_rms: float = 0.0                 # A, worst-case continuous input RMS (from the grid)
    inrush_peak_A: float = None        # A, worst-case cold-inrush peak (NTC-limited) — reported, see gate 3
    available_fault_current_A: float = None  # A, site fault current (breaking-cap gate); None -> OPEN
    # ── margins (gates 2 + 3) ────────────────────────────────────────────────
    current_margin: float = 1.5        # I_rated >= margin * I_rms / k_thermal
    i2t_margin: float = 2.0            # melting I2t must exceed margin * startup I2t (no nuisance blow)
    load_factor: float = DEFAULT_LOAD_FACTOR   # gate 2b: I_rms <= load_factor * I_rated * k_thermal
    ambient_derate: float = 1.0        # explicit de-rating override, used when t_ambient_C is not given
    oversize_factor: float = 4.0       # reject fuses rated > this * the minimum (won't clear a small overload)
    # ── gate 6: thermal implementation ───────────────────────────────────────
    t_ambient_C: float = None          # max ambient AT THE FUSE; None -> thermal gate OPEN
    t_rating_ref_C: float = DEFAULT_T_RATING_REF_C   # ambient the catalog rating is stated at
    derate_per_C: float = None         # %/degC from the datasheet re-rating curve; None -> ESTIMATED
    fuseholder_rise_C: float = None    # fuseholder / PCB copper / enclosure rise; None -> rise OPEN
    t_body_max_C: float = None         # part temperature limit; normally read from the DB record's op_temp
    # ── gate 5: fault coordination ───────────────────────────────────────────
    mov_fail_short_current_A: float = None    # prospective current when a MOV fails SHORT
    gdt_follow_current_A: float = None        # GDT follow-on current after sparkover
    relay_stuck_fault_current_A: float = None # stuck / welded bypass-relay fault path
    mov_gdt_present: bool = None       # True + available fault current -> fail-short is a bolted line fault
    # ── legacy switch ────────────────────────────────────────────────────────
    inrush_gates_rating: bool = False  # True restores the old (over-strict) I_rated >= inrush-peak rule


def thermal_derating(fs: FuseSpec) -> dict:
    """Gate-6 physics. The catalog current rating is stated at `t_rating_ref_C`; above that the fuse must be
    re-rated along the datasheet re-rating curve (linear approximation, slope `derate_per_C` in %/degC). The
    temperature the FUSE actually sees is the ambient PLUS the fuseholder / PCB / enclosure rise, so both are
    inputs. Returns the de-rating factor k_thermal plus what is known vs estimated vs open."""
    t_amb = fs.t_ambient_C
    rise_known = fs.fuseholder_rise_C is not None
    if t_amb is None:
        return {
            "known": False, "estimated": False, "rise_known": rise_known,
            "k_thermal": max(fs.ambient_derate, 1e-3),
            "t_ambient_C": None, "rise_C": fs.fuseholder_rise_C, "t_body_C": None, "dT_C": None,
            "slope_pct_per_C": None,
            "note": ("maximum ambient at the fuse not given — thermal de-rating OPEN"
                     + ("" if fs.ambient_derate == 1.0 else f"; explicit de-rate {fs.ambient_derate:g} applied")),
        }
    slope = fs.derate_per_C
    estimated = slope is None
    if estimated:
        slope = DEFAULT_DERATE_PER_C
    t_body = t_amb + (fs.fuseholder_rise_C or 0.0)
    dT = max(0.0, t_body - fs.t_rating_ref_C)
    k = max(0.10, 1.0 - slope / 100.0 * dT)
    if estimated:
        note = (f"re-rating slope not given — ESTIMATED at {slope:g} %/degC (typical cartridge curve); "
                "enter the datasheet slope to close this gate")
    else:
        note = f"datasheet re-rating slope {slope:g} %/degC"
    if not rise_known:
        note += "; fuseholder / PCB rise not given — body temperature assumes ambient only"
    return {
        "known": True, "estimated": estimated, "rise_known": rise_known,
        "k_thermal": k, "t_ambient_C": t_amb, "rise_C": fs.fuseholder_rise_C,
        "t_body_C": t_body, "dT_C": dT, "slope_pct_per_C": slope, "note": note,
    }


def fault_coordination(fs: FuseSpec) -> dict:
    """Gate-5 threshold. The fuse must safely interrupt the fault a FAILED protection device presents: a MOV
    that has failed short, a GDT conducting follow-on current, or a stuck / welded bypass relay. When the
    designer only states that a MOV/GDT is fitted, its fail-short is a bolted line fault, so the prospective
    current is the site's available fault current. No data -> OPEN (never a silent pass)."""
    srcs = []
    if fs.mov_fail_short_current_A:
        srcs.append(("MOV fail-short", float(fs.mov_fail_short_current_A)))
    if fs.gdt_follow_current_A:
        srcs.append(("GDT follow current", float(fs.gdt_follow_current_A)))
    if fs.relay_stuck_fault_current_A:
        srcs.append(("stuck bypass relay", float(fs.relay_stuck_fault_current_A)))
    if not srcs and fs.mov_gdt_present and fs.available_fault_current_A:
        srcs.append(("MOV/GDT fail-short (bolted line fault)", float(fs.available_fault_current_A)))
    if not srcs:
        return {"known": False, "i_A": None, "source": None,
                "note": "no MOV/GDT fail-short or stuck-relay fault current given — fault coordination OPEN"}
    source, i_a = max(srcs, key=lambda s: s[1])
    return {"known": True, "i_A": i_a, "source": source,
            "note": f"governing fault path: {source} at {i_a:g} A"}


def requirements(fs: FuseSpec, startup_i2t: float = None) -> dict:
    """The thresholds a candidate fuse must meet, one entry per gate.

    Gate 2 has TWO components and the binding requirement is the larger:
      (a) the continuous-margin rule   I_rated >= current_margin * I_rms / k_thermal
      (b) the load-factor rule         I_rated >= I_rms / (load_factor * k_thermal)
    Gate 3 (melting I2t) is what carries the startup pulse — the inrush PEAK does NOT set the current
    rating unless `inrush_gates_rating` is set (legacy behaviour)."""
    th = thermal_derating(fs)
    fc = fault_coordination(fs)
    k = max(th["k_thermal"], 1e-3)
    i_cont = fs.current_margin * fs.i_rms / k if fs.i_rms else 0.0
    i_load = fs.i_rms / max(fs.load_factor * k, 1e-3) if fs.i_rms else 0.0
    i_rated_min = max(i_cont, i_load)
    if fs.inrush_gates_rating:
        i_rated_min = max(i_rated_min, fs.inrush_peak_A or 0.0)
    return {
        # gate 1
        "v_min": fs.vac_max,
        # gate 2
        "i_cont_min": i_cont,                            # continuous-margin component
        "i_load_min": i_load,                            # load-factor (75 %) component
        "i_rated_min": i_rated_min,                      # binding = max of the two (+ inrush if legacy)
        "i_rated_max": i_rated_min * fs.oversize_factor if i_rated_min else None,
        "load_factor": fs.load_factor,
        "k_thermal": k,
        # gate 3
        "i2t_min": (fs.i2t_margin * startup_i2t) if startup_i2t else None,  # None -> ride-inrush OPEN
        "startup_i2t": startup_i2t,
        "inrush_peak": fs.inrush_peak_A,                 # context only (see docstring)
        "inrush_gates_rating": bool(fs.inrush_gates_rating),
        # gate 4
        "bc_min": fs.available_fault_current_A,          # None -> breaking-cap check OPEN
        # gate 5
        "coord": fc,
        "coord_min": fc["i_A"],
        # gate 6
        "thermal": th,
        # labels
        "gates": [{"n": n, "name": nm, "requirement": rq} for n, nm, rq in GATES],
    }


def _fmt(v, unit="", nd=1):
    return "—" if v is None else (f"{v:.{nd}f} {unit}".strip() if isinstance(v, float) else f"{v} {unit}".strip())


def gate_summary(fs: FuseSpec, req: dict, part: dict = None) -> list:
    """Release table for the SELECTED fuse — one row per gate with requirement, result and status.
    Status is PASS / FAIL / OPEN (input or datasheet field missing) / CONDITIONAL (result rests on an
    estimated value). `part` is a screen row from database.screen_table_fuse; None -> every gate OPEN."""
    p = part or {}
    th, co = req["thermal"], req["coord"]
    lf_pct = req["load_factor"] * 100.0

    def st(ok, cond=False):
        return "OPEN" if ok is None else ("CONDITIONAL" if (ok and cond) else ("PASS" if ok else "FAIL"))

    rows = []
    # 1 voltage
    rows.append({"n": 1, "name": GATES[0][1], "requirement": f">= {_fmt(req['v_min'],'Vac',0)}",
                 "result": _fmt(p.get("v_ac_V"), "Vac", 0), "status": st(p.get("v_ok") if part else None)})
    # 2 continuous RMS current
    _r2 = _fmt(p.get("i_rated_A"), "A", 0)
    if p.get("i_usable_A") is not None:
        _r2 += (f" ({_fmt(p['i_usable_A'],'A')} usable at {lf_pct:.0f}% x k={req['k_thermal']:.2f}"
                + (f", load {fs.i_rms:.1f} A" if fs.i_rms else "") + ")")
    rows.append({"n": 2, "name": GATES[1][1],
                 "requirement": (f">= {_fmt(req['i_rated_min'],'A')} "
                                 f"(margin {_fmt(req['i_cont_min'],'A')}, {lf_pct:.0f}% rule {_fmt(req['i_load_min'],'A')})"),
                 "result": _r2, "status": st(p.get("i_ok") if part else None)})
    # 3 startup / inrush I2t
    _req3 = (f"> {_fmt(req['i2t_min'],'A2s')} ({fs.i2t_margin:g} x startup {_fmt(req['startup_i2t'],'A2s')})"
             if req["i2t_min"] else "startup I2t not given")
    _res3 = _fmt(p.get("melting_i2t"), "A2s") + (f"; inrush peak {_fmt(req['inrush_peak'],'A')} ridden by I2t"
                                                 if req.get("inrush_peak") else "")
    rows.append({"n": 3, "name": GATES[2][1], "requirement": _req3, "result": _res3,
                 "status": st(p.get("i2t_ok") if part else None)})
    # 4 breaking capacity
    rows.append({"n": 4, "name": GATES[3][1],
                 "requirement": (f">= {_fmt(req['bc_min'],'A',0)} available fault current" if req["bc_min"]
                                 else "available fault current not given"),
                 "result": _fmt(p.get("breaking_ac_A"), "A", 0), "status": st(p.get("bc_ok") if part else None)})
    # 5 fault coordination
    rows.append({"n": 5, "name": GATES[4][1],
                 "requirement": (f">= {_fmt(co['i_A'],'A',0)} ({co['source']})" if co["known"] else co["note"]),
                 "result": (_fmt(p.get("breaking_ac_A"), "A", 0) + " breaking" if p.get("breaking_ac_A") else "—"),
                 "status": st(p.get("coord_ok") if part else None)})
    # 6 thermal implementation
    if th["known"]:
        _req6 = (f"body <= part limit at {_fmt(th['t_ambient_C'],'degC',0)} ambient"
                 + (f" + {_fmt(th['rise_C'],'degC',0)} holder rise" if th["rise_known"] else " (holder rise not given)"))
        _res6 = (f"body {_fmt(th['t_body_C'],'degC',0)} vs limit {_fmt(p.get('t_body_max_C'),'degC',0)}; "
                 f"k={th['k_thermal']:.2f}")
    else:
        _req6, _res6 = th["note"], "—"
    rows.append({"n": 6, "name": GATES[5][1], "requirement": _req6, "result": _res6,
                 "status": st(p.get("thermal_ok") if part else None,
                              cond=bool(th.get("estimated") or not th.get("rise_known")))})
    return rows


def self_test():
    print("Running fuse self-test...")
    fs = FuseSpec(vac_max=264, i_rms=20.0, available_fault_current_A=1500, current_margin=1.5)
    req = requirements(fs, startup_i2t=16.4)
    assert abs(req["i_cont_min"] - 30.0) < 1e-6, req               # 1.5 * 20
    assert abs(req["i_load_min"] - 20.0 / 0.75) < 1e-6, req        # 75 % loading -> 26.67 A
    assert abs(req["i_rated_min"] - 30.0) < 1e-6, req              # binding = the 1.5x rule here
    assert req["v_min"] == 264
    assert req["bc_min"] == 1500
    assert abs(req["i2t_min"] - 32.8) < 1e-6, req                  # 2.0 * 16.4
    print(f"  [ok] gates 1-4: I_rated>={req['i_rated_min']:.1f}A (cont {req['i_cont_min']:.1f} / "
          f"75% {req['i_load_min']:.1f}), V>={req['v_min']:.0f}V, BC>={req['bc_min']:.0f}A, "
          f"melt-I2t>={req['i2t_min']:.1f}A2s")

    # gate 3: the inrush PEAK must NOT raise the current rating (review correction)
    f2 = FuseSpec(vac_max=264, i_rms=25.90, inrush_peak_A=54.5)
    r2 = requirements(f2, startup_i2t=16.4)
    assert abs(r2["i_rated_min"] - 1.5 * 25.90) < 1e-6, r2         # 38.85 A, NOT 54.5 A
    assert r2["inrush_peak"] == 54.5 and r2["inrush_gates_rating"] is False
    f2b = FuseSpec(vac_max=264, i_rms=25.90, inrush_peak_A=54.5, inrush_gates_rating=True)
    assert abs(requirements(f2b, 16.4)["i_rated_min"] - 54.5) < 1e-6   # legacy switch still available
    print("  [ok] gate 3: inrush peak 54.5 A does NOT gate the rating (38.85 A binding); legacy switch works")

    # doc worked example: 40 A fuse, 25.9 A load -> 75 % usable = 30 A
    assert abs(0.75 * 40 - 30.0) < 1e-9
    assert 25.90 <= 0.75 * 40, "75 % loading check"
    print("  [ok] gate 2: 25.90 A <= 0.75 x 40 A = 30 A usable at the reference ambient")

    # gate 6: thermal de-rating
    t_open = thermal_derating(FuseSpec(i_rms=20.0))
    assert t_open["known"] is False and t_open["k_thermal"] == 1.0
    t_est = thermal_derating(FuseSpec(i_rms=20.0, t_ambient_C=55.0))
    assert t_est["known"] and t_est["estimated"]
    assert abs(t_est["k_thermal"] - (1.0 - 0.5 / 100 * 30.0)) < 1e-9, t_est   # 0.85 at 55 degC
    t_ds = thermal_derating(FuseSpec(i_rms=20.0, t_ambient_C=55.0, derate_per_C=0.4, fuseholder_rise_C=15.0,
                                     t_body_max_C=125.0))
    assert t_ds["estimated"] is False and t_ds["rise_known"] and t_ds["t_body_C"] == 70.0
    assert abs(t_ds["k_thermal"] - (1.0 - 0.4 / 100 * 45.0)) < 1e-9, t_ds     # 0.82 at 70 degC body
    r3 = requirements(FuseSpec(i_rms=25.90, t_ambient_C=55.0), startup_i2t=16.4)
    assert abs(r3["i_rated_min"] - 1.5 * 25.90 / 0.85) < 1e-6, r3             # 45.7 A once de-rated
    print(f"  [ok] gate 6: 55 degC ambient -> k={t_est['k_thermal']:.2f} (ESTIMATED), "
          f"I_rated>= {r3['i_rated_min']:.1f}A; datasheet slope + holder rise -> k={t_ds['k_thermal']:.2f}")

    # gate 5: fault coordination
    c_open = fault_coordination(FuseSpec(i_rms=20.0))
    assert c_open["known"] is False and c_open["i_A"] is None
    c_bolt = fault_coordination(FuseSpec(i_rms=20.0, available_fault_current_A=1500, mov_gdt_present=True))
    assert c_bolt["known"] and c_bolt["i_A"] == 1500
    c_max = fault_coordination(FuseSpec(i_rms=20.0, mov_fail_short_current_A=800,
                                        relay_stuck_fault_current_A=2200, gdt_follow_current_A=120))
    assert c_max["i_A"] == 2200 and "relay" in c_max["source"], c_max
    print(f"  [ok] gate 5: no data -> OPEN; MOV/GDT fitted -> bolted {c_bolt['i_A']:.0f} A; "
          f"governing path '{c_max['source']}' {c_max['i_A']:.0f} A")

    # missing inputs -> OPEN
    r4 = requirements(FuseSpec(vac_max=264, i_rms=20.0), startup_i2t=None)
    assert r4["bc_min"] is None and r4["i2t_min"] is None and r4["coord_min"] is None
    assert r4["thermal"]["known"] is False
    assert len(r4["gates"]) == 6
    print("  [ok] missing fault current / startup I2t / ambient -> OPEN thresholds; 6 gates registered")
    print("ALL FUSE SELF-TESTS PASSED.")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        self_test()
    else:
        fs = FuseSpec(i_rms=20.0, available_fault_current_A=1500)
        print("fuse requirements:", requirements(fs, startup_i2t=16.4))
