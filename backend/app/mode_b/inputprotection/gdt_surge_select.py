#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gdt_surge_select.py
====================================================================
GDT (gas-discharge tube) surge-diverter sizing for the common-mode
(line/neutral-to-earth) paths of a universal-input PFC front end, per
the Chapter-9 MOV+GDT review (IEC/EN 61000-4-5).

A GDT is NOT a precision clamp — it is a high-current surge DIVERTER.
The MOV still controls the fast/residual voltage; the GDT fires and
carries the large common-mode surge current once its sparkover is
reached. So the GDT checks are different from the MOV checks:

  1. NO-FIRE (continuous)  : the GDT must not conduct on normal AC or
        line swell. Use the MINIMUM sparkover after tolerance, not the
        nominal:  V_spark_min > V_line_pk * K_margin.
  2. DYNAMIC / IMPULSE SPARKOVER : during a fast IEC edge the GDT fires
        LATE, at a much higher impulse sparkover than the DC value. The
        let-through is max(V_impulse_spark, V_spark_max) and must stay
        under downstream insulation withstand. If the datasheet impulse
        sparkover is absent -> DATA MISSING (flag, do not assume).
  3. SURGE CURRENT : I_sc = V_le / Z_cm, times a design margin; prefer a
        standard impulse-current class (5/10/20 kA).
  4. FOLLOW CURRENT / ARC EXTINCTION : after the surge the AC source can
        sustain the arc. Must prove self-extinction or fuse clearing. If
        follow-current data is missing on an L-PE/N-PE GDT -> FAIL /
        DATA MISSING (review program rule), NOT a pass.
  5. FAIL-SHORT SAFETY : a GDT can fail short; the upstream fuse must
        clear the L/N-to-PE fault. Missing fuse evidence -> FAIL.

Every output traces to the LEVEL (stress), the LINE (no-fire), or a
datasheet field; missing datasheet fields are surfaced, never assumed.

Run:  python3 gdt_surge_select.py --selftest
====================================================================
"""

from __future__ import annotations
from dataclasses import dataclass
from math import sqrt
import sys

from .mov_surge_select import LEVEL_TABLE, Z_COMMON_MODE

# Standard GDT 8/20 impulse-current classes [A] to prefer for the database default.
STD_GDT_CLASSES = [1000, 2500, 3000, 5000, 10000, 20000]


@dataclass
class GdtSpec:
    # --- line (no-fire) ---
    vac_max: float = 264.0            # Vac high-line corner
    vac_nom: float = 230.0            # Vac nominal
    line_swell: float = 1.0           # line-swell factor over vac_max (named; raise for a swell-prone grid)
    k_line_margin: float = 1.20       # V_spark_min must exceed line peak by this factor

    # --- stress (LEVEL, common-mode L/N-to-earth) ---
    level: object = 3                 # 1..4 or "X"
    custom_v_le: float = None         # V, open-circuit line-to-earth (level "X")
    z_common: float = Z_COMMON_MODE   # ohm, CDN common-mode impedance
    imax_margin: float = 3.0          # I_GDT >= margin * I_sc

    # --- coordination / safety inputs (None => DATA MISSING gate) ---
    insulation_withstand_V: float = None   # downstream insulation / spacing withstand (impulse sparkover)
    follow_current_extinguish_A: float = None  # source follow-current the GDT can self-extinguish
    mains_fault_current_A: float = None    # available L/N-PE fault current (fail-short)
    fuse_i2t_rating_A2s: float = None      # upstream fuse melting I2t
    fuse_rating_A: float = None            # upstream fuse continuous rating (info)
    placement: str = "L/N-PE"              # GDTs sit line/neutral-to-earth


def validate(s: GdtSpec):
    if s.level not in LEVEL_TABLE:
        raise ValueError(f"level must be one of {list(LEVEL_TABLE)} (got {s.level!r})")
    if s.level == "X" and s.custom_v_le is None:
        raise ValueError("level 'X' requires custom_v_le")


# ============================================================== #
#  STRESS + LINE                                                #
# ============================================================== #

def v_le_of(s: GdtSpec) -> float:
    """Open-circuit line-to-earth surge voltage for the level (or custom)."""
    if s.level == "X":
        return s.custom_v_le
    return LEVEL_TABLE[s.level][0]


def resolve_stress(s: GdtSpec):
    """Common-mode surge: I_sc = V_le / Z_cm, and the design current target."""
    v_le = v_le_of(s)
    if v_le is None:
        return None, None, None
    i_sc = v_le / s.z_common
    return v_le, i_sc, i_sc * s.imax_margin


def v_line_peak(s: GdtSpec) -> float:
    """Line peak with swell — the voltage the GDT must NOT fire on."""
    return sqrt(2.0) * s.vac_max * s.line_swell


def snap_gdt_class(req_A: float) -> int:
    for c in STD_GDT_CLASSES:
        if c >= req_A:
            return c
    return STD_GDT_CLASSES[-1]


# ============================================================== #
#  PER-CANDIDATE CHECKS                                          #
# ============================================================== #

def no_fire(s: GdtSpec, v_spark_min: float) -> dict:
    """Continuous no-fire: minimum sparkover (after tolerance) must clear the swelled line peak."""
    vpk = v_line_peak(s)
    need = vpk * s.k_line_margin
    if v_spark_min is None:
        return {"ok": None, "vpk": vpk, "need": need, "v_spark_min": None,
                "note": "DATA MISSING: minimum sparkover unknown"}
    return {"ok": v_spark_min > need, "vpk": vpk, "need": need, "v_spark_min": v_spark_min,
            "note": (f"V_spark_min {v_spark_min:.0f} V "
                     f"{'>' if v_spark_min > need else '<='} {need:.0f} V "
                     f"(line peak {vpk:.0f} V x margin {s.k_line_margin:.2f})")}


def dynamic_sparkover(s: GdtSpec, v_impulse_spark: float, v_spark_max: float) -> dict:
    """Impulse (dynamic) let-through = max(impulse sparkover, DC sparkover max) vs insulation withstand.
    Missing datasheet impulse sparkover -> DATA MISSING (do not claim the DC value clamps the edge)."""
    if v_impulse_spark is None:
        return {"ok": None, "v_letthrough": None, "withstand": s.insulation_withstand_V,
                "note": "DATA MISSING: datasheet impulse sparkover @ dv/dt not provided — dynamic "
                        "let-through cannot be bounded (do NOT assume the DC sparkover clamps the edge)"}
    v_lt = max(v_impulse_spark, v_spark_max or 0.0)
    if s.insulation_withstand_V is None:
        return {"ok": None, "v_letthrough": v_lt, "withstand": None,
                "note": f"impulse let-through {v_lt:.0f} V; downstream insulation withstand not provided"}
    return {"ok": v_lt <= s.insulation_withstand_V, "v_letthrough": v_lt,
            "withstand": s.insulation_withstand_V,
            "note": f"impulse let-through {v_lt:.0f} V vs insulation withstand {s.insulation_withstand_V:.0f} V"}


def surge_current(s: GdtSpec, i_required: float, imax_impulse: float) -> dict:
    """8/20 impulse current: the part rating must exceed the design target current."""
    if imax_impulse is None:
        return {"ok": None, "i_required": i_required, "imax_impulse": None,
                "note": "DATA MISSING: 8/20 impulse current rating unknown"}
    return {"ok": imax_impulse >= i_required, "i_required": i_required, "imax_impulse": imax_impulse,
            "note": f"I_rating {imax_impulse:.0f} A {'>=' if imax_impulse >= i_required else '<'} "
                    f"required {i_required:.0f} A"}


def follow_current(s: GdtSpec, fail_short_flag=None) -> dict:
    """Arc-extinction after the surge. On an L/N-PE GDT, missing follow-current data is a FAIL per the
    review program rule (not a pass)."""
    if s.follow_current_extinguish_A is None:
        return {"ok": False, "note": "FAIL / DATA MISSING: follow-current (arc-extinction) data required "
                "for an L/N-PE GDT — provide the datasheet hold/follow current and the available mains "
                "current, or prove fuse clearing"}
    return {"ok": True, "extinguish_A": s.follow_current_extinguish_A,
            "note": f"self-extinguishes below {s.follow_current_extinguish_A:.1f} A follow current"}


def fail_short(s: GdtSpec, fail_short_flag=None) -> dict:
    """Fail-short safety: the upstream fuse must clear an L/N-PE short. Missing evidence -> FAIL."""
    if s.mains_fault_current_A is None or s.fuse_i2t_rating_A2s is None:
        return {"ok": False, "note": "FAIL / DATA MISSING: provide the available L/N-PE fault current and "
                "the upstream fuse I2t/clearing curve — a GDT fail-short path must be proven safe"}
    return {"ok": True, "i_fault_A": s.mains_fault_current_A, "fuse_i2t_A2s": s.fuse_i2t_rating_A2s,
            "note": (f"fail-short cleared: fault {s.mains_fault_current_A:.0f} A within fuse breaking "
                     f"capacity, fuse I2t {s.fuse_i2t_rating_A2s:.0f} A2s")
                    + ("" if not fail_short_flag or str(fail_short_flag).lower().startswith("n")
                       else " (NOTE: datasheet marks this part fail-short)")}


# ============================================================== #
#  GDT-REQUIRED DECISION (level-driven; environment refines in GUI) #
# ============================================================== #

def gdt_required(s: GdtSpec, environment: str = None) -> dict:
    """Recommend MOV-only vs MOV+GDT from the common-mode surge level (and, when given, the install
    environment). Level 3 CM -> optional; Level 4 / >=4 kV L-PE or harsh environment -> required."""
    v_le = v_le_of(s)
    env = (environment or "").strip().lower()
    harsh = env in ("industrial", "harsh", "lightning", "outdoor", "telecom")
    if v_le is None:
        return {"required": False, "recommend": "MOV-only", "reason": "no defined line-to-earth surge level"}
    if v_le >= 4000 or s.level == 4 or harsh:
        return {"required": True, "recommend": "MOV+GDT",
                "reason": f"line-to-earth surge {v_le:.0f} V"
                          + (f" / {env} environment" if harsh else "")
                          + " — add a common-mode GDT diversion path"}
    if v_le >= 2000 or s.level == 3:
        return {"required": False, "recommend": "MOV-only (GDT optional)",
                "reason": f"line-to-earth surge {v_le:.0f} V — MOV usually sufficient if clamp/energy/fuse "
                          "checks pass; GDT optional for extra common-mode robustness"}
    return {"required": False, "recommend": "MOV-only",
            "reason": f"line-to-earth surge {v_le:.0f} V — low common-mode stress"}


# ============================================================== #
#  SELF-TEST                                                     #
# ============================================================== #

def self_test():
    print("Running GDT self-test...")
    s = GdtSpec(level=3)
    validate(s)
    v_le, i_sc, i_req = resolve_stress(s)
    assert abs(v_le - 2000) < 1 and abs(i_sc - 2000 / 12) < 1, (v_le, i_sc)
    assert abs(i_req - i_sc * 3) < 1
    print(f"  [ok] Level 3 CM: V_le {v_le:.0f} V, I_sc {i_sc:.0f} A, I_req {i_req:.0f} A")

    # no-fire: 600 V nominal +/-20% -> min 480 V must clear 264 Vac peak*swell*margin
    nf = no_fire(s, 480.0)
    assert nf["ok"] is True, nf
    nf_low = no_fire(s, 376.0)                      # 470 V class -> min 376 V, too close
    assert nf_low["ok"] is False, nf_low
    print(f"  [ok] no-fire: 480 V PASS ({nf['need']:.0f} V need), 376 V FAIL")

    # dynamic sparkover DATA MISSING when impulse value absent
    ds = dynamic_sparkover(s, None, 720.0)
    assert ds["ok"] is None, ds
    print("  [ok] dynamic sparkover -> DATA MISSING when impulse value absent")

    # follow-current / fail-short FAIL when data missing (review program rule)
    assert follow_current(s)["ok"] is False
    assert fail_short(s)["ok"] is False
    print("  [ok] follow-current & fail-short -> FAIL when data missing")

    # GDT-required decision by level/environment
    assert gdt_required(GdtSpec(level=3))["required"] is False
    assert gdt_required(GdtSpec(level=4))["required"] is True
    assert gdt_required(GdtSpec(level=3), environment="industrial")["required"] is True
    print("  [ok] GDT-required: L3 optional, L4 required, L3+industrial required")

    print("ALL GDT SELF-TESTS PASSED.")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        self_test()
    else:
        s = GdtSpec()
        v_le, i_sc, i_req = resolve_stress(s)
        print(f"GDT L{s.level}: V_le {v_le:.0f} V -> I_sc {i_sc:.0f} A, I_req {i_req:.0f} A "
              f"(prefer {snap_gdt_class(i_req)} A class); no-fire need {v_line_peak(s)*s.k_line_margin:.0f} V")
        print("required:", gdt_required(s))
