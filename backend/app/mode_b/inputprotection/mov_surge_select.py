#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mov_surge_select.py
====================================================================
MOV (metal-oxide varistor) surge-protection sizing for a
universal-input (90-264 Vac) PFC front end, per IEC/EN 61000-4-5
(combination wave). The designer chooses a TEST LEVEL and a
PERFORMANCE CRITERION; the script makes every output traceable to
those two inputs.

DESIGN PHILOSOPHY (orthogonal inputs)
  - LEVEL sizes the STRESS  : resolves to a (V_LL, V_LE) voltage pair,
        then each coupling mode uses its OWN source impedance:
            line-to-line (differential) : Z = 2  ohm  -> I = V_LL / 2
            line-to-earth (common mode) : Z = 12 ohm  -> I = V_LE / 12
        (IEC 61000-4-5: 2 ohm CWG; CDN adds 10 ohm for line-to-earth.)
  - CRITERION sizes the ACCEPTANCE BAR : A (ride-through), B (self-
        recover), C (operator reset). It changes gates/margins and the
        verdict wording, NOT the currents or energies.
  - MCOV is set ONLY by the continuous worst-case line. It is INVARIANT
        to level and criterion (asserted in the self-test).

CLAMP / COORDINATION
  The let-through voltage is found from the load-line operating point:
        varistor curve : V = V_1mA * (I / 1mA)^(1/alpha)
        source line    : V = V_drive - I * Z
  intersection -> (I_op, Vc). With phase-angle superposition the surge
  rides on the line peak, so V_drive = V_oc + V_line_pk (worst 90/270).

SURVIVAL
  Primary gate is I_max(8/20) with repetitive (10-pulse) derating, not
  the 2 ms joule rating. The 8/20 pulse energy is reported as info.

NOTE on catalog: example parts carry *representative* numbers only and
MUST be confirmed against a live datasheet (esp. the Vc-vs-I curve and
the repetitive-pulse derating curve) before ordering.

Run:  python3 mov_surge_select.py            (report)
      python3 mov_surge_select.py --selftest (prove input steering)
====================================================================
"""

from __future__ import annotations
from dataclasses import dataclass, field
from math import sqrt
import sys


# ============================================================== #
#  STANDARD DATA (auditable lookup tables)                       #
# ============================================================== #

# Test level -> (V_line_earth, V_line_line) open-circuit voltages [V].
# For AC power ports line-to-line is one class below line-to-earth.
# None means the mode is not defined/required at that level.
LEVEL_TABLE = {
    1: (500.0,  None),
    2: (1000.0, 500.0),
    3: (2000.0, 1000.0),
    4: (4000.0, 2000.0),
    "X": (None, None),     # custom -> designer must supply voltages
}

# Coupling source impedances [ohm] (CWG 2 ohm + CDN resistor).
Z_DIFFERENTIAL = 2.0    # line-to-line
Z_COMMON_MODE = 12.0    # line-to-earth (mains)

# standard MOV continuous-voltage classes (Vac RMS), ascending
STD_MCOV_CLASSES = [130, 150, 175, 200, 250, 275, 300, 320, 385, 420, 460, 510, 550]


# Criterion -> acceptance policy.
#   dev_margin_V    : extra V the clamp must stay BELOW the device gate
#   gate_uses_absmax: B/C may use device transient abs-max; A uses Vds
#   allow_reset     : converter may dip/restart
#   allow_disconnect: protective disconnect (fuse/TMOV) counts as pass
#   energy_safety   : safety factor on the survival/energy headroom
@dataclass(frozen=True)
class CritPolicy:
    name: str
    ride_through: bool
    dev_margin_V: float
    gate_uses_absmax: bool
    allow_reset: bool
    allow_disconnect: bool
    energy_safety: float

CRITERION_POLICY = {
    "A": CritPolicy("A", True,  50.0, False, False, False, 1.5),
    "B": CritPolicy("B", False, 0.0,  True,  True,  False, 1.25),
    "C": CritPolicy("C", False, 0.0,  True,  True,  True,  1.25),
}


# ============================================================== #
#  CONFIG  -- edit these to match your design                   #
# ============================================================== #

@dataclass
class Spec:
    # --- line ---
    vac_max: float = 264.0          # Vac, high-line corner (sets MCOV)
    vac_nom: float = 230.0          # Vac, nominal

    # --- DESIGNER CHOICES (the two orthogonal knobs) ---
    level: object = 3               # 1,2,3,4 or "X"
    criterion: str = "A"            # "A","B","C"

    # --- Level X custom voltages (only used if level == "X") ---
    custom_v_ll: float = None       # V, open-circuit line-to-line
    custom_v_le: float = None       # V, open-circuit line-to-earth

    # --- which paths exist on the board ---
    common_mode_protection: bool = True   # L-PE / N-PE MOVs fitted?

    # --- MCOV policy (line-driven, level/criterion independent) ---
    mcov_margin_line: float = 1.0   # MCOV >= margin * Vac_max  (binding)
    mcov_margin_nom: float = 1.25   # advisory (reported, not binding)
    use_advisory_margin: bool = False

    # --- varistor electrical model (override with datasheet) ---
    v1ma_ratio: float = 1.60        # V_1mA / MCOV
    varistor_alpha: float = 30.0    # nonlinearity exponent (I ~ V^alpha)

    # --- downstream withstand to protect ---
    device_vds: float = 650.0       # V, continuous switch rating
    device_absmax: float = 650.0    # V, transient abs-max (>= vds; B/C relief)
    cap_v_rating: float = 450.0     # V, bulk cap rating (DC-side, info)

    # --- surge-current rating policy ---
    imax_margin: float = 3.0        # design target I_max >= margin * I_sc
    pulse_count: int = 10           # 5 pos + 5 neg per mode
    repetitive_derate: float = 0.70 # part I_max * this must still cover I_sc

    # --- phase-angle superposition (surge on line peak) ---
    phase_superposition: bool = True


# ============================================================== #
#  VALIDATION                                                    #
# ============================================================== #

def validate(s: Spec):
    if s.level not in LEVEL_TABLE:
        raise ValueError(f"level must be one of {list(LEVEL_TABLE)} (got {s.level!r})")
    if s.criterion not in CRITERION_POLICY:
        raise ValueError(f"criterion must be one of {list(CRITERION_POLICY)} "
                         f"(got {s.criterion!r})")
    if s.level == "X" and (s.custom_v_ll is None and s.custom_v_le is None):
        raise ValueError("level 'X' requires custom_v_ll and/or custom_v_le")
    if s.device_absmax < s.device_vds:
        raise ValueError("device_absmax must be >= device_vds")


# ============================================================== #
#  STRESS  (driven by LEVEL only)                               #
# ============================================================== #

@dataclass
class Path:
    name: str          # protection path / MOV position
    mode: str          # "differential" | "common-mode"
    z: float           # source impedance
    v_oc: float        # open-circuit test voltage
    i_sc: float        # short-circuit current = v_oc / z (MOV absent)


def resolve_stress(s: Spec):
    """LEVEL -> per-coupling-mode stress vector. No criterion here."""
    if s.level == "X":
        v_le, v_ll = s.custom_v_le, s.custom_v_ll
    else:
        v_le, v_ll = LEVEL_TABLE[s.level]

    paths = []
    if v_ll is not None:
        paths.append(Path("L-N  (differential MOV)", "differential",
                          Z_DIFFERENTIAL, v_ll, v_ll / Z_DIFFERENTIAL))
    if s.common_mode_protection and v_le is not None:
        paths.append(Path("L-PE (common-mode MOV)", "common-mode",
                          Z_COMMON_MODE, v_le, v_le / Z_COMMON_MODE))
        paths.append(Path("N-PE (common-mode MOV)", "common-mode",
                          Z_COMMON_MODE, v_le, v_le / Z_COMMON_MODE))
    return paths, v_le, v_ll


# ============================================================== #
#  MCOV  (driven by LINE only)                                  #
# ============================================================== #

def snap_mcov(req: float) -> int:
    for c in STD_MCOV_CLASSES:
        if c >= req:
            return c
    return STD_MCOV_CLASSES[-1]


def resolve_mcov(s: Spec):
    binding = s.mcov_margin_line * s.vac_max
    advisory = s.mcov_margin_nom * s.vac_nom
    req = max(binding, advisory) if s.use_advisory_margin else binding
    cls = snap_mcov(req)
    return req, advisory, cls


# ============================================================== #
#  CLAMP  (load-line operating point)                           #
# ============================================================== #

def operating_point(v1ma: float, alpha: float, v_drive: float, z: float):
    """Solve varistor curve V = V1mA*(I/1mA)^(1/alpha) against the
       source load line V = v_drive - I*z. Returns (I_op, Vc)."""
    def curve(I):                       # varistor voltage at current I
        return v1ma * (I / 1e-3) ** (1.0 / alpha)
    lo, hi = 1e-6, v_drive / z          # I in (0, short-circuit)
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        # f = curve(I) - loadline(I); root where they cross
        f = curve(mid) - (v_drive - mid * z)
        if f > 0:
            hi = mid
        else:
            lo = mid
    I_op = 0.5 * (lo + hi)
    return I_op, v_drive - I_op * z


def v_line_peak(s: Spec) -> float:
    return sqrt(2.0) * s.vac_max


# ============================================================== #
#  PER-PATH SIZING TARGET  (stress + criterion)                 #
# ============================================================== #

@dataclass
class PathTarget:
    path: Path
    v_drive: float          # drive voltage incl. superposition
    i_op: float             # MOV operating current at the let-through point
    vc: float               # let-through (clamp) voltage
    imax_required: float    # design target I_max(8/20)
    energy_8_20: float      # J, estimated single 8/20 pulse energy (info)
    device_gate: float      # V the clamp must stay under (criterion-set)
    coord_status: str       # OK / TIGHT / FAIL  (vs device)
    cap_status: str         # info vs DC bus cap


def estimate_energy_8_20(vc: float, i_op: float) -> float:
    # Approx single 8/20 pulse energy: rectangular-equivalent ~ 1.4 * Vc * Ipk * 20us.
    return 1.4 * vc * i_op * 20e-6


def size_path(s: Spec, p: Path, v1ma: float, pol: CritPolicy) -> PathTarget:
    v_drive = p.v_oc + (v_line_peak(s) if s.phase_superposition else 0.0)
    i_op, vc = operating_point(v1ma, s.varistor_alpha, v_drive, p.z)

    imax_required = s.imax_margin * p.i_sc
    energy = estimate_energy_8_20(vc, i_op)

    # criterion-set device gate: A protects with margin below Vds;
    # B/C allow up to transient abs-max (survival).
    gate = (s.device_absmax if pol.gate_uses_absmax
            else s.device_vds - pol.dev_margin_V)
    m = gate - vc
    if m >= 50:
        coord = "OK"
    elif m >= 0:
        coord = "TIGHT"
    else:
        coord = "FAIL"

    cap_m = s.cap_v_rating - vc
    cap_status = "OK" if cap_m >= 0 else "OVER (DC-side, info)"

    return PathTarget(p, v_drive, i_op, vc, imax_required, energy,
                      gate, coord, cap_status)


# ============================================================== #
#  CANDIDATE CATALOG (representative -- verify on datasheet!)    #
# ============================================================== #
# name, MCOV[Vac], V_1mA[V], I_max 8/20[A], Vc@I_max[V], energy 2ms[J]
MOV_CATALOG = [
    ("Littelfuse V20E275P / UltraMOV 20mm 275V", 275, 430, 6500, 710, 175),
    ("TDK/EPCOS S20K275 (B72220) 20mm",          275, 430, 8000, 710, 195),
    ("Bourns MOV-20D271K 20mm",                  275, 430, 6500, 715, 170),
    ("Littelfuse TMOV20R275 (thermally prot.)",  275, 430, 6500, 710, 175),
    ("Littelfuse V14E275 14mm 275V",             275, 430, 4500, 750, 110),
    ("TDK/EPCOS S34K275 34mm (low-clamp)",       275, 430, 20000, 685, 530),
]


def effective_alpha(v1ma: float, vc_imax: float, imax: float) -> float:
    """Back out a part's nonlinearity exponent from its own datasheet:
       I = 1mA*(V/V1mA)^alpha  ->  alpha = ln(Imax/1mA)/ln(Vc@Imax/V1mA).
       A larger/flatter disc yields a higher alpha (lower clamp at a
       given current)."""
    from math import log
    return log(imax / 1e-3) / log(vc_imax / v1ma)


def screen_catalog(s: Spec, gov: Path, mcov_req: float, pol: CritPolicy):
    """Screen parts for the GOVERNING (highest-current) path."""
    out = []
    v_drive = gov.v_oc + (v_line_peak(s) if s.phase_superposition else 0.0)
    for name, mcov, v1ma, imax, vc_max, e2ms in MOV_CATALOG:
        reasons, ok = [], True
        if mcov < mcov_req:
            ok = False
            reasons.append(f"MCOV {mcov} < required {mcov_req:.0f} Vac")
        # survival: rated I_max derated for 10 pulses must cover I_sc
        eff_imax = imax * s.repetitive_derate
        if eff_imax < gov.i_sc:
            ok = False
            reasons.append(f"I_max {imax}A x{s.repetitive_derate:.2f} (10-pulse) "
                           f"= {eff_imax:.0f}A < I_sc {gov.i_sc:.0f}A")
        # let-through at THIS part's own curve (per-part alpha), at op point
        a_eff = effective_alpha(v1ma, vc_max, imax)
        i_op, vc = operating_point(v1ma, a_eff, v_drive, gov.z)
        gate = (s.device_absmax if pol.gate_uses_absmax
                else s.device_vds - pol.dev_margin_V)
        reasons.append(f"let-through ~{vc:.0f}V @ {i_op:.0f}A "
                       f"(drive {v_drive:.0f}V); gate {gate:.0f}V [crit {pol.name}]")
        if vc > gate:
            if pol.ride_through:
                ok = False
                reasons.append(f"clamp {vc:.0f}V > gate {gate:.0f}V -> cannot ride "
                               f"through (criterion A)")
            else:
                reasons.append(f"clamp {vc:.0f}V > gate {gate:.0f}V -> FAIL even for "
                               f"survival")
                ok = False
        elif s.device_vds - pol.dev_margin_V < vc <= gate and not pol.ride_through:
            reasons.append("survives but bus disturbed -> unit resets "
                           f"(allowed under criterion {pol.name})")
        out.append((name, ok, reasons))
    return out


# ============================================================== #
#  REPORT                                                       #
# ============================================================== #

def report(s: Spec) -> str:
    validate(s)
    pol = CRITERION_POLICY[s.criterion]
    paths, v_le, v_ll = resolve_stress(s)
    mcov_req, mcov_adv, mcov_cls = resolve_mcov(s)
    v1ma = mcov_cls * s.v1ma_ratio

    # governing path = highest short-circuit current (usually differential)
    gov = max(paths, key=lambda p: p.i_sc) if paths else None

    L = []; p = L.append
    p("=" * 70)
    p(" MOV SURGE PROTECTION (IEC/EN 61000-4-5) -- SIZING REPORT")
    p("=" * 70)

    # ---- design-basis echo (your at-a-glance confirmation) ----
    p("\n[DESIGN BASIS] -- restated from your inputs")
    p(f"    Test level     : {s.level}   (LEVEL sizes the stress)")
    p(f"    Criterion      : {s.criterion} "
      f"({'ride-through' if pol.ride_through else 'survive/reset allowed'})"
      f"   (CRITERION sizes the bar)")
    p(f"    Line (MCOV src): {s.vac_max:.0f} Vac max / {s.vac_nom:.0f} Vac nom")
    p(f"    Resolved V_oc  : L-L = {('n/a' if v_ll is None else f'{v_ll:.0f} V')}, "
      f"L-E = {('n/a' if v_le is None else f'{v_le:.0f} V')}")
    p(f"    Phase superpos.: {'ON (+line peak %.0f V)' % v_line_peak(s) if s.phase_superposition else 'OFF'}")
    p(f"    Pulses/mode    : {s.pulse_count} (5+/5-), repetitive derate "
      f"x{s.repetitive_derate:.2f}")

    p("\n[1] Surge stress per coupling mode  <- LEVEL")
    p("    Mode (MOV position)          Z[ohm]  V_oc[V]   I_sc=V/Z [A]")
    for pt in paths:
        p(f"    {pt.name:<28} {pt.z:>5.0f}  {pt.v_oc:>7.0f}   {pt.i_sc:>8.0f}")
    if gov:
        p(f"    -> governing (highest I): {gov.name}  @ {gov.i_sc:.0f} A")
    p("    NOTE: differential uses 2 ohm; common-mode uses 12 ohm. The")
    p("          line-to-earth current is LOWER than line-to-line despite")
    p("          the higher voltage -- that is the standard's CDN impedance.")

    p("\n[2] Continuous voltage (MCOV)  <- LINE ONLY (level/criterion-independent)")
    p(f"    Rule A (binding) : MCOV >= {s.mcov_margin_line:.2f}*Vac_max "
      f"= {s.mcov_margin_line*s.vac_max:.0f} Vac")
    p(f"    Rule B (advisory): MCOV >= {s.mcov_margin_nom:.2f}*Vac_nom "
      f"= {mcov_adv:.0f} Vac")
    p(f"    Required MCOV    : {mcov_req:.0f} Vac")
    p(f"    -> Standard class: {mcov_cls} Vac  (V_1mA ~ {v1ma:.0f} V)")
    p(f"    (Invariant to level/criterion -- a surge level change must NOT")
    p(f"     move this number; enforced by the self-test.)")

    p("\n[3] Per-path sizing target  <- LEVEL (stress) x CRITERION (gate)")
    for pt in paths:
        t = size_path(s, pt, v1ma, pol)
        p(f"    {pt.name}")
        p(f"        drive V_oc(+line)  : {t.v_drive:.0f} V")
        p(f"        operating point    : {t.i_op:.0f} A @ let-through {t.vc:.0f} V")
        p(f"        I_max(8/20) target : >= {t.imax_required:.0f} A "
          f"({s.imax_margin:.0f}x I_sc)")
        p(f"        est. 8/20 energy   : ~{t.energy_8_20:.1f} J (info; not the 2ms rating)")
        p(f"        device gate        : {t.device_gate:.0f} V [criterion {pol.name}] "
          f"-> {t.coord_status}")
        p(f"        vs cap {s.cap_v_rating:.0f} V    : {t.cap_status}")

    p("\n[4] What the criterion changed (acceptance bar)  <- CRITERION")
    p(f"    Criterion {pol.name}: ride_through={pol.ride_through}, "
      f"reset_allowed={pol.allow_reset}, disconnect_ok={pol.allow_disconnect}")
    p(f"    Device gate = {'abs-max %.0f V' % s.device_absmax if pol.gate_uses_absmax else 'Vds %.0f - margin %.0f = %.0f V' % (s.device_vds, pol.dev_margin_V, s.device_vds-pol.dev_margin_V)}")
    p(f"    Energy/headroom safety factor: x{pol.energy_safety:.2f}")
    if pol.ride_through:
        p("    -> A clamp that exceeds the gate is a FAIL: the bus must keep")
        p("       regulating. If tight, add a 2nd-stage TVS/snubber, a larger")
        p("       low-clamp MOV, or move to higher-voltage devices.")
    else:
        p("    -> A clamp above Vds but below abs-max is acceptable: the unit")
        p("       may dip/reset as long as nothing is damaged.")

    p("\n[5] Placement & coordination")
    p("    - Differential: one MOV across L-N at the AC inlet, AFTER the fuse.")
    p("    - Common mode : L-PE and N-PE MOVs; watch leakage & creepage.")
    p("    - Keep leads SHORT/low-inductance (overshoot on the 1.2us edge).")
    p("    - Pair with upstream fuse + thermal protection (or a TMOV).")

    if gov:
        p(f"\n[6] Candidate screen for governing path: {gov.name}")
        p("    (REPRESENTATIVE values -- verify datasheet Vc-vs-I & 10-pulse derate)")
        for name, ok, reasons in screen_catalog(s, gov, mcov_req, pol):
            p(f"    [{'PASS' if ok else 'FAIL'}] {name}")
            for r in reasons:
                p(f"           - {r}")

    p("\n" + "=" * 70)
    p(" Every number above traces to: LEVEL (stress), CRITERION (bar),")
    p(" or LINE (MCOV). Confirm the Vc-vs-current curve and the 10-pulse")
    p(" repetitive derating against the chosen datasheet.")
    p("=" * 70)
    return "\n".join(L)


# ============================================================== #
#  SELF-TEST  (proves the inputs steer the outputs)             #
# ============================================================== #

def self_test():
    print("Running self-test (proving input -> output steering)...")

    # 1) LEVEL drives the per-mode currents.
    for lvl, exp_diff, exp_cm in [(3, 500.0, 2000/12), (4, 1000.0, 4000/12)]:
        s = Spec(level=lvl)
        paths, _, _ = resolve_stress(s)
        diff = next(p for p in paths if p.mode == "differential").i_sc
        cm = next(p for p in paths if p.mode == "common-mode").i_sc
        assert abs(diff - exp_diff) < 1, f"L{lvl} diff {diff} != {exp_diff}"
        assert abs(cm - exp_cm) < 1, f"L{lvl} cm {cm} != {exp_cm}"
    print("  [ok] Level 3 -> 500A/167A ; Level 4 -> 1000A/333A")

    # 2) MCOV is INVARIANT to level and criterion.
    base = resolve_mcov(Spec(level=3, criterion="A"))[2]
    for lvl in (1, 2, 3, 4):
        for crit in ("A", "B", "C"):
            cls = resolve_mcov(Spec(level=lvl, criterion=crit))[2]
            assert cls == base, f"MCOV moved with inputs: {cls} != {base}"
    assert base == 275, f"MCOV expected 275, got {base}"
    print("  [ok] MCOV = 275 Vac, invariant across all level/criterion combos")

    # 3) CRITERION flips a known-tight part's verdict A(FAIL) -> B(PASS).
    #    Give the device some transient abs-max headroom so survival differs
    #    from ride-through.
    common = dict(level=3, device_vds=650, device_absmax=720,
                  phase_superposition=True)
    sa = Spec(criterion="A", **common)
    sb = Spec(criterion="B", **common)
    gov_a = max(resolve_stress(sa)[0], key=lambda p: p.i_sc)
    gov_b = max(resolve_stress(sb)[0], key=lambda p: p.i_sc)
    mc = resolve_mcov(sa)[0]
    res_a = dict((n, ok) for n, ok, _ in
                 screen_catalog(sa, gov_a, mc, CRITERION_POLICY["A"]))
    res_b = dict((n, ok) for n, ok, _ in
                 screen_catalog(sb, gov_b, mc, CRITERION_POLICY["B"]))
    part = "Littelfuse V20E275P / UltraMOV 20mm 275V"
    assert res_a[part] is False, "expected FAIL under criterion A"
    assert res_b[part] is True, "expected PASS under criterion B"
    print(f"  [ok] '{part.split('/')[0].strip()}': FAIL@A, PASS@B")

    # 4) Validation rejects bad inputs.
    for bad in (dict(level=5), dict(criterion="Z"), dict(level="X")):
        try:
            validate(Spec(**bad)); assert False, f"should have rejected {bad}"
        except ValueError:
            pass
    print("  [ok] invalid level/criterion and bare level-X are rejected")

    print("ALL SELF-TESTS PASSED.")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        self_test()
    else:
        print(report(Spec()))
