"""
plausibility.py — sanity-check a part record against physics and against the catalogue.
=======================================================================================
When a designer types a part in by hand, or the PDF extractor reads one out of a datasheet, a
single wrong digit produces a number that is not obviously wrong. It flows into the loss model, the
thermal check and the report, and nothing in a 190-page document says "this cannot be right".

There is no authority to check a manufacturer part NUMBER against, so this module does not try. It
checks the VALUES, two ways:

  IDENTITY rules  — an exact physical relation the record must satisfy on its own terms, e.g. a
                    toroid's Ve = Ae * le, or OD > ID. Tolerances here are not guessed: they are
                    the residuals measured across the 1923-core catalogue (Ve vs Ae*le is within
                    7% for every core in it), so a real part passes and a decimal slip does not.

  BAND rules      — the value, or a cross-field combination of values, must land inside the range
                    the existing catalogue occupies, widened. Bands are computed from the live
                    catalogues at first use, so they track the data rather than a frozen constant.

CROSS-FIELD BANDS ARE THE USEFUL ONES. A single-field band is weak: MOSFET R_DS(on) spans
0.018-0.19 ohm across 1257 parts, so a 10x slip on a mid-range part lands inside the band and
passes. The product R_DS(on)*Q_g spans only 990-24480 mOhm*nC, so a 10x slip in EITHER field moves
it clear outside. Where a cross-field relation exists, it is worth more than both fields checked
separately, and this module leans on them.

WHAT THIS IS NOT. It cannot tell a right value from a plausible wrong one — a V_f of 1.1 V typed
where the datasheet says 1.4 V is inside every band and always will be. It catches slips of
magnitude, transposed fields and impossible geometry. Confirming a value against the datasheet
remains the designer's job; this only removes the errors a machine can see.

NEVER BLOCKS. Findings are advisory (project convention: selection is never blocked by a check).
The caller shows them and records the designer's acknowledgement; nothing here rejects a part.

A NOTE ON DERIVED FIELDS. A rule that checks a value against the formula that produced it proves
nothing. `energy_est_J` in the ICL catalogue is computed from the disc diameter at ingest, so
"energy vs diameter" holds to 0.3% across all 994 parts and would be a rule that can never fire.
Rules below are only written where both sides come from the vendor independently.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, asdict
from typing import Callable, Optional


def _va(text) -> Optional[float]:
    """Volt-amps out of a relay's 'Load - Max Switching' string ('15400VA', '2.5 kVA')."""
    m = re.search(r"([\d.]+)\s*(k?)VA", str(text or ""), re.I)
    return float(m.group(1)) * (1000.0 if m.group(2) else 1.0) if m else None

# How far outside the catalogue's own range a value may sit before it is flagged. Tuned to the
# failure mode: a misplaced decimal point is a factor of 10, so the widening has to stay well
# inside that. Cross-field relations are physical and tight, hence the smaller factor.
WIDEN_SINGLE = 3.0
WIDEN_CROSS = 2.0

# Band edges. The full min/max of the catalogue is used, not a trimmed percentile: trimming to
# p1/p99 flagged four legitimate parts sitting in the tail (a 0.5 V I_D x R_DS(on) part against a
# p1 of 1.32), and a false flag on a real part is the one thing that would make a designer stop
# reading these. The widening below then sets the actual line.
_P_LO, _P_HI = 0.0, 1.0


@dataclass
class Finding:
    """One thing that does not look right. `severity` is advisory throughout."""
    rule: str                       # short stable id, e.g. "core.Ve_identity"
    fields: list                    # the record fields the rule looked at
    message: str                    # what to tell the designer
    observed: Optional[float] = None
    expected: str = ""              # human description of what was expected
    severity: str = "FLAG"          # FLAG = looks wrong · NOTE = worth an eye

    def as_dict(self) -> dict:
        return asdict(self)


# ── reference bands, measured from the live catalogues ───────────────────────────────────────
_BANDS: dict[str, tuple[float, float]] = {}
_BAND_SRC: dict[str, int] = {}


def _percentile_band(values, lo=_P_LO, hi=_P_HI) -> Optional[tuple[float, float]]:
    v = sorted(x for x in values if x is not None and isinstance(x, (int, float))
               and x == x and math.isfinite(x))
    if len(v) < 20:                       # too few to say anything about the population
        return None
    n = len(v)
    return v[min(n - 1, int(n * lo))], v[min(n - 1, int(n * hi))]


def _load_bands() -> None:
    """Build every band once, from whatever catalogues are present. A catalogue that will not load
    simply leaves its rules unarmed — a missing reference must never become a false flag."""
    if _BANDS:
        return

    def add(key, values):
        b = _percentile_band(values)
        if b:
            _BANDS[key] = b
            _BAND_SRC[key] = len([x for x in values if x is not None])

    try:
        from app.mode_b.semiconductor import database as sdb
        m = sdb.load("mosfet")
        add("mosfet.vdss", [r.get("vdss") for r in m])
        add("mosfet.rdson", [r.get("rdson") for r in m])
        add("mosfet.vth", [r.get("vth") for r in m])
        add("mosfet.qg", [r.get("qg") for r in m])
        # cross-field: figure of merit, and the drop at rated current
        add("mosfet.fom", [r["rdson"] * 1e3 * r["qg"] * 1e9
                           for r in m if r.get("rdson") and r.get("qg")])
        add("mosfet.id_x_rdson", [r["id_25"] * r["rdson"]
                                  for r in m if r.get("id_25") and r.get("rdson")])
        for k in ("diode", "bridge"):
            d = sdb.load(k)
            add(f"{k}.vf", [r.get("vf") for r in d])
            add(f"{k}.vr", [r.get("vr") for r in d])
            add(f"{k}.io", [r.get("io") for r in d])
    except Exception:
        pass

    try:
        from app.mode_b.inputprotection import database as ipdb
        f = ipdb.load_fuse()
        add("fuse.i_rated_A", [r.get("i_rated_A") for r in f])
        add("fuse.v_ac_V", [r.get("v_ac_V") for r in f])
        add("fuse.i2t_over_i2", [r["melting_i2t"] / r["i_rated_A"] ** 2
                                 for r in f if r.get("melting_i2t") and r.get("i_rated_A")])
        rl = ipdb.load_relay()
        add("relay.contact_i_A", [r.get("contact_i_A") for r in rl])
        add("relay.switch_v_V", [r.get("switch_v_V") for r in rl])
        add("relay.t_operate_ms", [r.get("t_operate_ms") for r in rl])
        add("relay.coil_mW", [r["coil_v_V"] * r["coil_i_mA"]
                              for r in rl if r.get("coil_v_V") and r.get("coil_i_mA")])
        add("relay.release_over_operate", [r["t_release_ms"] / r["t_operate_ms"]
                                           for r in rl if r.get("t_release_ms") and r.get("t_operate_ms")])
        # The tightest relay rule by some way: the published VA rating against contact current x
        # switching voltage spans only 0.33-2.0 across 1078 of the 1082 parts, so a slip in either
        # factor moves it clear out.
        add("relay.va_over_iv", [_va(r.get("load_max")) / (r["contact_i_A"] * r["switch_v_V"])
                                 for r in rl if r.get("contact_i_A") and r.get("switch_v_V")
                                 and _va(r.get("load_max"))])
        n = ipdb.load()
        add("ntc.r25", [r.get("r25") for r in n])
        add("ntc.imax", [r.get("imax") for r in n])
        add("ntc.rhot_over_r25", [(r["r_hot_mohm"] / 1000.0) / r["r25"]
                                  for r in n if r.get("r_hot_mohm") and r.get("r25")])
        # Current rating against disc area. Both come from the vendor independently (unlike
        # energy_est_J, which is DERIVED from the diameter and so cannot be checked against it).
        add("ntc.imax_over_area", [r["imax"] / r["diameter_mm"] ** 2
                                   for r in n if r.get("imax") and r.get("diameter_mm")])
        try:
            mv = ipdb.load_mov()
            add("mov.v1ma_over_mcov", [r["v1ma"] / r["mcov"]
                                       for r in mv if r.get("v1ma") and r.get("mcov")])
            add("mov.mcov", [r.get("mcov") for r in mv])
        except Exception:
            pass
    except Exception:
        pass


def band_report() -> dict:
    """The bands in force, for the report's provenance section and for debugging."""
    _load_bands()
    return {k: {"lo": v[0], "hi": v[1], "parts": _BAND_SRC.get(k)} for k, v in sorted(_BANDS.items())}


class _Ctx(list):
    """Findings, plus a count of the rules that actually RAN.

    A rule whose inputs are absent is skipped, not passed. Reporting "nothing looked wrong" without
    saying how many rules could be evaluated would let a record with two fields look as well checked
    as one with ten.
    """
    evaluated = 0

    def ran(self):
        self.evaluated += 1


def _hard(out: "_Ctx", inputs_present: bool, violated: bool, finding: Finding) -> None:
    """A rule with a definite right answer — geometry that cannot be, units that cannot be."""
    if not inputs_present:
        return
    out.ran()
    if violated:
        out.append(finding)


# ── rule helpers ─────────────────────────────────────────────────────────────────────────────
def _num(rec, key):
    v = rec.get(key)
    try:
        if v is None or v == "":
            return None
        f = float(v)
        return f if math.isfinite(f) else None
    except (TypeError, ValueError):
        return None


def _check_band(out, key, value, fields, label, widen, unit=""):
    """Flag a value that sits outside the catalogue's own range, widened."""
    _load_bands()
    b = _BANDS.get(key)
    if b is None or value is None:
        return
    out.ran()
    lo, hi = b[0] / widen, b[1] * widen
    if not (lo <= value <= hi):
        out.append(Finding(
            rule=key, fields=list(fields), observed=round(value, 6),
            expected=f"{lo:.4g} to {hi:.4g} {unit}".strip(),
            message=(f"{label} is {value:.4g} {unit}".strip()
                     + f", outside the range every one of the {_BAND_SRC.get(key, 0)} catalogue "
                       f"parts occupies ({b[0]:.4g} to {b[1]:.4g}{(' ' + unit) if unit else ''}, "
                       f"widened {widen:g}x). Check for a misplaced decimal point or a swapped field.")))


def _check_identity(out, rule, lhs, rhs, tol_pct, fields, label, note):
    """Flag a physical identity the record fails on its own terms."""
    if lhs is None or rhs is None or rhs == 0:
        return
    out.ran()
    err = abs(lhs - rhs) / abs(rhs) * 100.0
    if err > tol_pct:
        out.append(Finding(
            rule=rule, fields=list(fields), observed=round(err, 2),
            expected=f"within {tol_pct:g}%",
            message=f"{label}: {err:.1f}% apart ({lhs:.4g} vs {rhs:.4g}). {note}"))


# ── per-kind rules ───────────────────────────────────────────────────────────────────────────
def _core(rec, out):
    Ae = _num(rec, "Ae_mm2"); Le = _num(rec, "Le_mm") or _num(rec, "le_mm")
    Ve = _num(rec, "Ve_cm3"); OD = _num(rec, "OD_mm"); ID = _num(rec, "ID_mm")
    AL = _num(rec, "AL_nom_nH"); mu = _num(rec, "mu")

    # Exact identity. Residual across all 1923 catalogue cores is under 7%, so 12% passes every
    # real part while a decimal slip (900%) or a swapped Ae/Le cannot hide.
    if Ae and Le and Ve:
        _check_identity(out, "core.Ve_identity", Ve * 1000.0, Ae * Le, 12.0,
                        ["Ve_cm3", "Ae_mm2", "Le_mm"], "Ve should equal Ae x le",
                        "Every core in the catalogue satisfies this within 7%.")
    # Toroid mean magnetic path. Catalogue residual reaches 8.6%, so 20% is the flag line.
    if Le and OD and ID:
        _check_identity(out, "core.le_geometry", Le, math.pi * (OD + ID) / 2.0, 20.0,
                        ["Le_mm", "OD_mm", "ID_mm"], "le vs the mean toroid path pi(OD+ID)/2",
                        "Check the dimensions, or whether this is really a toroid.")
    # A_L from the geometry and permeability. Powder cores have a distributed gap and mu is
    # nominal, so the catalogue spread is wider (to 13%); 30% is the flag line.
    if AL and mu and Ae and Le:
        _check_identity(out, "core.AL_identity", AL,
                        4e-7 * math.pi * mu * (Ae * 1e-6) / (Le * 1e-3) * 1e9, 30.0,
                        ["AL_nom_nH", "mu", "Ae_mm2", "Le_mm"],
                        "A_L vs mu0 x mu x Ae / le", "Check A_L, mu, Ae and le against the datasheet.")
    _hard(out, OD is not None and ID is not None, bool(OD and ID and OD <= ID),
          Finding(rule="core.OD_gt_ID", fields=["OD_mm", "ID_mm"], expected="OD > ID",
                  message=f"Outer diameter {OD} mm is not greater than the inner {ID} mm — "
                          f"the two are probably swapped."))
    for k in ("Ae_mm2", "Le_mm", "Ve_cm3", "OD_mm", "ID_mm", "HT_mm", "AL_nom_nH"):
        v = _num(rec, k)
        _hard(out, v is not None, bool(v is not None and v <= 0),
              Finding(rule="core.positive", fields=[k], observed=v, expected="> 0",
                      message=f"{k} is {v}; it must be positive."))


def _mosfet(rec, out):
    rds = _num(rec, "rdson") or _num(rec, "rdson_25")
    qg = _num(rec, "qg"); vdss = _num(rec, "vdss"); vth = _num(rec, "vth")
    idc = _num(rec, "id_25") or _num(rec, "id")
    _check_band(out, "mosfet.vdss", vdss, ["vdss"], "V_DSS", WIDEN_SINGLE, "V")
    _check_band(out, "mosfet.rdson", rds, ["rdson"], "R_DS(on)", WIDEN_SINGLE, "ohm")
    _check_band(out, "mosfet.vth", vth, ["vth"], "V_GS(th)", WIDEN_SINGLE, "V")
    _check_band(out, "mosfet.qg", qg, ["qg"], "Q_g", WIDEN_SINGLE, "C")
    # The strong ones: a slip in EITHER field moves the combination clear of the band.
    if rds and qg:
        _check_band(out, "mosfet.fom", rds * 1e3 * qg * 1e9, ["rdson", "qg"],
                    "the figure of merit R_DS(on) x Q_g", WIDEN_CROSS, "mOhm*nC")
    if rds and idc:
        _check_band(out, "mosfet.id_x_rdson", idc * rds, ["id_25", "rdson"],
                    "the drop at rated current I_D x R_DS(on)", WIDEN_CROSS, "V")
    _hard(out, bool(vth and vdss), bool(vth and vdss and vth >= vdss),
          Finding(rule="mosfet.vth_lt_vdss", fields=["vth", "vdss"], expected="V_GS(th) << V_DSS",
                  message=f"Gate threshold {vth} V is not below V_DSS {vdss} V — "
                          f"the two look swapped."))


def _diode_like(kind, rec, out):
    vf = _num(rec, "vf"); vr = _num(rec, "vr"); io = _num(rec, "io")
    _check_band(out, f"{kind}.vf", vf, ["vf"], "forward drop V_f", WIDEN_SINGLE, "V")
    _check_band(out, f"{kind}.vr", vr, ["vr"], "reverse rating V_R", WIDEN_SINGLE, "V")
    _check_band(out, f"{kind}.io", io, ["io"], "rated current I_o", WIDEN_SINGLE, "A")
    _hard(out, bool(vf and vr), bool(vf and vr and vf >= vr),
          Finding(rule=f"{kind}.vf_lt_vr", fields=["vf", "vr"], expected="V_f << V_R",
                  message=f"Forward drop {vf} V is not below the reverse rating {vr} V — "
                          f"the two look swapped."))
    ifsm = _num(rec, "ifsm_A"); i2t = _num(rec, "i2t_A2s")
    # I2t is the half-sine integral of IFSM: I2t = IFSM^2 * 8.3ms / 2. Vendors round and quote at
    # different pulse widths, so this is a wide check that only catches a wrong order of magnitude.
    if ifsm and i2t:
        _check_identity(out, f"{kind}.ifsm_i2t", i2t, ifsm ** 2 * 8.3e-3 / 2.0, 150.0,
                        ["i2t_A2s", "ifsm_A"], "I2t vs IFSM^2 x 8.3 ms / 2",
                        "Both are datasheet surge figures; they should agree to an order of magnitude.")


def _ntc(rec, out):
    r25 = _num(rec, "r25"); imax = _num(rec, "imax"); rhot = _num(rec, "r_hot_mohm")
    _check_band(out, "ntc.r25", r25, ["r25"], "R25", WIDEN_SINGLE, "ohm")
    _check_band(out, "ntc.imax", imax, ["imax"], "steady I_max", WIDEN_SINGLE, "A")
    dia = _num(rec, "diameter_mm")
    if imax and dia:
        _check_band(out, "ntc.imax_over_area", imax / dia ** 2, ["imax", "diameter_mm"],
                    "the current rating relative to disc area I_max/D^2", WIDEN_CROSS, "A/mm2")
    if r25 and rhot:
        _check_band(out, "ntc.rhot_over_r25", (rhot / 1000.0) / r25, ["r_hot_mohm", "r25"],
                    "the hot/cold resistance ratio R_hot/R25", WIDEN_CROSS)
        _hard(out, True, rhot / 1000.0 >= r25,
              Finding(rule="ntc.rhot_lt_r25", fields=["r_hot_mohm", "r25"], expected="R_hot < R25",
                      message=f"Hot resistance {rhot/1000.0:g} ohm is not below R25 {r25:g} ohm. "
                              f"An NTC falls with temperature; check the units (mOhm vs ohm)."))


def _relay(rec, out):
    ci = _num(rec, "contact_i_A"); sv = _num(rec, "switch_v_V")
    cv = _num(rec, "coil_v_V"); cmA = _num(rec, "coil_i_mA")
    top = _num(rec, "t_operate_ms"); trl = _num(rec, "t_release_ms")
    _check_band(out, "relay.contact_i_A", ci, ["contact_i_A"], "contact rating", WIDEN_SINGLE, "A")
    _check_band(out, "relay.switch_v_V", sv, ["switch_v_V"], "switching voltage", WIDEN_SINGLE, "V")
    _check_band(out, "relay.t_operate_ms", top, ["t_operate_ms"], "operate time", WIDEN_SINGLE, "ms")
    if cv and cmA:
        _check_band(out, "relay.coil_mW", cv * cmA, ["coil_v_V", "coil_i_mA"],
                    "coil power V x I", WIDEN_CROSS, "mW")
    if top and trl:
        _check_band(out, "relay.release_over_operate", trl / top, ["t_release_ms", "t_operate_ms"],
                    "the release/operate time ratio", WIDEN_CROSS)
    va = _va(rec.get("load_max"))
    if va and ci and sv:
        _check_band(out, "relay.va_over_iv", va / (ci * sv), ["load_max", "contact_i_A", "switch_v_V"],
                    "the VA rating against contact current x switching voltage", WIDEN_CROSS)


def _fuse(rec, out):
    ir = _num(rec, "i_rated_A"); vac = _num(rec, "v_ac_V")
    i2t = _num(rec, "melting_i2t"); bc = _num(rec, "breaking_ac_A")
    _check_band(out, "fuse.i_rated_A", ir, ["i_rated_A"], "rated current", WIDEN_SINGLE, "A")
    _check_band(out, "fuse.v_ac_V", vac, ["v_ac_V"], "AC voltage rating", WIDEN_SINGLE, "V")
    if ir and i2t:
        # Weak by nature: melting I2t is dominated by the fuse's speed class, so the catalogue
        # ratio spans three decades (0.002 to 2.2). It catches a wrong order of magnitude, no more.
        _check_band(out, "fuse.i2t_over_i2", i2t / ir ** 2, ["melting_i2t", "i_rated_A"],
                    "melting I2t relative to I_rated^2", WIDEN_CROSS, "s")
    _hard(out, bool(ir and bc), bool(ir and bc and bc < ir),
          Finding(rule="fuse.breaking_gt_rated", fields=["breaking_ac_A", "i_rated_A"],
                  expected="breaking capacity >> rated current",
                  message=f"Breaking capacity {bc} A is below the rated current {ir} A, which cannot "
                          f"be right — check the units (kA vs A)."))


def _mov(rec, out):
    mcov = _num(rec, "mcov"); v1ma = _num(rec, "v1ma")
    _check_band(out, "mov.mcov", mcov, ["mcov"], "MCOV", WIDEN_SINGLE, "V")
    if mcov and v1ma:
        _check_band(out, "mov.v1ma_over_mcov", v1ma / mcov, ["v1ma", "mcov"],
                    "the varistor-voltage ratio V_1mA/MCOV", WIDEN_CROSS)
        _hard(out, True, v1ma <= mcov,
              Finding(rule="mov.v1ma_gt_mcov", fields=["v1ma", "mcov"], expected="V_1mA > MCOV",
                      message=f"V_1mA {v1ma:g} V is not above the MCOV {mcov:g} V — the two "
                              f"look swapped."))


_RULES: dict[str, Callable[[dict, list], None]] = {
    "core": _core,
    "mosfet": _mosfet,
    "diode": lambda r, o: _diode_like("diode", r, o),
    "bridge": lambda r, o: _diode_like("bridge", r, o),
    "ntc": _ntc,
    "relay": _relay,
    "fuse": _fuse,
    "mov": _mov,
}

KINDS = tuple(sorted(_RULES))


def check(kind: str, rec: dict) -> dict:
    """Sanity-check one part record. Returns findings — never a pass/fail, never a rejection.

    {"kind", "findings": [...], "checked": n_rules_armed, "ok": bool}
    `ok` means "nothing looked wrong", not "this part is correct".
    """
    kind = (kind or "").strip().lower()
    fn = _RULES.get(kind)
    if fn is None:
        return {"kind": kind, "findings": [], "checked": 0, "ok": True,
                "note": f"no rules for '{kind}' — known kinds: {', '.join(KINDS)}"}
    out = _Ctx()
    try:
        fn(rec or {}, out)
    except Exception as e:                       # a broken rule must not break the page
        return {"kind": kind, "findings": [], "checked": 0, "ok": True,
                "note": f"plausibility check unavailable: {e}"}
    return {"kind": kind, "findings": [f.as_dict() for f in out],
            "checked": out.evaluated, "ok": not out,
            "note": ("" if out.evaluated else
                     "no rule could be evaluated — the record has none of the fields these rules "
                     "compare, so this is not a clean result")}
