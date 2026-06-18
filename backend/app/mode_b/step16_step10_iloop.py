"""
app/mode_b/step16_step10_iloop.py — Inner Current Loop design calc agent.

Reproduces the reference document's "Step 13 — Inner Current Loop Design" as our
report Step 10. Every value is COMPUTED from previously-calculated steps and the
design specification — nothing the engineer already established upstream is
hard-coded here:

    V_OUT   ← Step 5  (feedback divider)        R_CS  ← Step 6  (Kelvin shunt)
    Lϕ, C_O ← Step 1  (power-stage spec)         f_ci  ← Step 4  (GUI crossover)
    P_OUT, V_AC ranges, N_ch ← design spec       r_L, r_C, V_RAMP, G_MI, R_M, C_M, f_z, f_p

`compute_step10_iloop(inp=None, prior=None)` returns the full worked result.
The boost duty-to-current plant G_id(s) is modelled WITH the inductor DCR (r_L)
so the resonance damps to a finite, realistic Q (per the document's pitfall).
"""
from __future__ import annotations
import math, cmath

SQRT2 = math.sqrt(2.0)

# Component values that originate HERE (anti-alias filter, datasheet, compensator
# targets) — everything else is pulled from prior steps in compute_step10_iloop.
DEFAULT_INPUTS = {
    "r_l": 0.010,        # inductor DCR per phase (Ω) — spec
    "r_c": 0.010,        # output-cap ESR per cap (Ω) — spec
    "v_ramp": 5.0,       # internal PWM ramp (V) — FAN9672-D
    "g_mi": 88e-6,       # OTA transconductance (S) — FAN9672-D
    "r_m": 2000.0,       # CS anti-alias filter R (Ω)
    "c_m": 470e-12,      # CS anti-alias filter C (F)
    "f_z": 1000.0,       # compensator zero target (Hz) — ~decade below f_ci (GUI)
    "f_p": 26000.0,      # compensator HF pole target (Hz) — ~3× f_ci (GUI)
    "pm_min": 45.0,      # phase-margin requirement (°)
    # operating points (V_AC, P_OUT) — LL range @ pout_lo, HL range @ pout_hi
    "vac_ll": [90, 110, 120, 132],
    "vac_hl": [180, 210, 220, 264],
}

_E24 = [1.0, 1.1, 1.2, 1.3, 1.5, 1.6, 1.8, 2.0, 2.2, 2.4, 2.7, 3.0,
        3.3, 3.6, 3.9, 4.3, 4.7, 5.1, 5.6, 6.2, 6.8, 7.5, 8.2, 9.1]


def _nearest_e24(x):
    if x <= 0:
        return x
    d = math.floor(math.log10(x))
    base = x / 10 ** d
    best = min(_E24, key=lambda e: abs(e - base))
    return best * 10 ** d


class _Plant:
    """Boost duty-to-inductor-current small-signal plant G_id(s), DCR-damped."""
    def __init__(self, vout, lphi, co, r_l, r_c, rload, D):
        self.kfront = (vout / lphi) * (rload + 2 * r_c) / (rload + r_c)
        self.wz = 1.0 / (co * (rload / 2 + r_c))
        Dp = 1 - D
        self.esr_ratio = (rload + 2 * r_c) / (rload + r_c)
        self.vout_over_l = vout / lphi
        n_a1 = co * (r_l * (rload + r_c) + rload * r_c * Dp ** 2) + lphi
        d_a1 = lphi * co * (rload + r_c)
        self.na1, self.da1 = n_a1, d_a1
        self.a1 = n_a1 / d_a1
        n_a0 = Dp ** 2 * rload + r_l
        self.na0 = n_a0
        self.a0 = n_a0 / d_a1
        self.f0 = math.sqrt(self.a0) / (2 * math.pi)
        self.q = math.sqrt(self.a0) / self.a1

    def gid(self, w):
        s = 1j * w
        return self.kfront * (s + self.wz) / (s * s + self.a1 * s + self.a0)


def compute_step10_iloop(inp: dict | None = None, prior: dict | None = None) -> dict:
    p = dict(DEFAULT_INPUTS)
    if inp:
        p.update(inp)
    if prior is None:
        from app.mode_b.step16_steps1_8 import compute_steps_1_8
        prior = compute_steps_1_8()

    # ── inputs sourced from prior steps / spec (NOT hard-coded) ───────────────
    pin = prior["inputs"]
    vout = pin["vout"]                       # Step 5 feedback divider target
    lphi = pin["lphi_uH"] * 1e-6             # Step 1 per-phase inductance
    co = pin["cout_uF"] * 1e-6               # Step 1 total output capacitance
    rcs = prior["step6"]["rcs_sel"]          # Step 6 selected Kelvin shunt
    fci = pin["fci"]                         # Step 4 GUI current crossover
    nch = pin["nch"]
    pout_lo, pout_hi = pin["pout_lo"], pin["pout_hi"]
    r_l, r_c, vramp, gmi = p["r_l"], p["r_c"], p["v_ramp"], p["g_mi"]
    rm, cm, fz, fp = p["r_m"], p["c_m"], p["f_z"], p["f_p"]

    f_rc = 1.0 / (2 * math.pi * rm * cm)     # CS filter HF pole
    ramp_norm = rcs / vramp                  # R_CS / V_RAMP
    wci = 2 * math.pi * fci

    def hcs(w):                              # first-order CS filter
        return 1.0 / (1 + 1j * (w / (2 * math.pi * f_rc)))

    ops = [(v, pout_lo) for v in p["vac_ll"]] + [(v, pout_hi) for v in p["vac_hl"]]

    def op_calc(vac, pout):
        rload = vout ** 2 / pout
        vinpk = SQRT2 * vac
        D = 1 - vinpk / vout
        Dp = 1 - D
        pl = _Plant(vout, lphi, co, r_l, r_c, rload, D)
        frhp = rload * Dp ** 2 / (2 * math.pi * lphi)
        gid_ci = pl.gid(wci)
        h = hcs(wci)
        ti_unc = gid_ci * ramp_norm * h
        return dict(vac=vac, pout=pout, rload=rload, vinpk=vinpk, D=D, Dp=Dp,
                    plant=pl, frhp=frhp, gid_ci=gid_ci, h=h, ti_unc=ti_unc,
                    f0=pl.f0, q=pl.q)

    rows = [op_calc(v, pw) for v, pw in ops]

    # ── compensator design (Type-2 OTA), sized at 90 Vac worst case ───────────
    base = rows[0]
    ti_unc_mag = abs(base["ti_unc"])
    kappa = math.sqrt(1 + (fz / fci) ** 2) / math.sqrt(1 + (fci / fp) ** 2)
    ric_calc = 1.0 / (ti_unc_mag * gmi * kappa)
    ric = _nearest_e24(ric_calc)
    cic1_calc = 1.0 / (2 * math.pi * ric_calc * fz)
    cic1 = _nearest_e24(cic1_calc)
    cic2_calc = 1.0 / (2 * math.pi * ric_calc * fp)
    cic2 = _nearest_e24(cic2_calc)
    fz_act = 1.0 / (2 * math.pi * ric * cic1)
    fp_act = 1.0 / (2 * math.pi * ric * cic2)

    wz_c, wp_c = 2 * math.pi * fz_act, 2 * math.pi * fp_act

    def ziea(w):
        return ric * (1 + wz_c / (1j * w)) / (1 + 1j * w / wp_c)

    def gmi_tf(w):
        return gmi * ziea(w)

    def ti_comp(op, w):
        return op["plant"].gid(w) * ramp_norm * hcs(w) * gmi_tf(w)

    def crossover_pm(op):
        # |Ti| is monotonically falling through unity near f_ci → bisect
        lo, hi = 2 * math.pi * 1e3, 2 * math.pi * 1e5
        for _ in range(80):
            mid = math.sqrt(lo * hi)
            if abs(ti_comp(op, mid)) > 1:
                lo = mid
            else:
                hi = mid
        wco = math.sqrt(lo * hi)
        ph = math.degrees(cmath.phase(ti_comp(op, wco)))
        return wco / (2 * math.pi), 180 + ph

    for op in rows:
        fco, pm = crossover_pm(op)
        op["fco"], op["pm"] = fco, pm

    # ── Bode sweep arrays (open & closed loop) for the figures ────────────────
    fsweep = [10 ** (1 + 4.0 * i / 240) for i in range(241)]   # 10 Hz → 100 kHz
    bode = []
    for op in rows:
        og, oph, cg, cph = [], [], [], []
        for f in fsweep:
            t = ti_comp(op, 2 * math.pi * f)
            og.append(20 * math.log10(abs(t)))
            oph.append(math.degrees(cmath.phase(t)))
            cl = t / (1 + t)
            cg.append(20 * math.log10(abs(cl)))
            cph.append(math.degrees(cmath.phase(cl)))
        bode.append(dict(vac=op["vac"], pout=op["pout"], f=fsweep,
                         ogain=og, ophase=oph, cgain=cg, cphase=cph))

    out = {
        "src": {"vout": vout, "lphi": lphi, "co": co, "rcs": rcs, "fci": fci,
                "nch": nch, "pout_lo": pout_lo, "pout_hi": pout_hi},
        "p": p, "f_rc": f_rc, "ramp_norm": ramp_norm,
        "rows": rows, "kappa": kappa,
        "ric_calc": ric_calc, "ric": ric, "cic1_calc": cic1_calc, "cic1": cic1,
        "cic2_calc": cic2_calc, "cic2": cic2, "fz": fz, "fp": fp,
        "fz_act": fz_act, "fp_act": fp_act, "rm": rm, "cm": cm,
        "ti_unc_mag": ti_unc_mag, "bode": bode,
        "fco_nom": rows[0]["fco"], "pm_nom": rows[0]["pm"],
    }
    return out


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    d = compute_step10_iloop()
    b = d["rows"][0]
    pl = b["plant"]
    print("=== 90 Vac / 1700 W detailed ===")
    print("RLOAD %.4f (91.1763)  Vinpk %.4f (127.2792)  D %.6f (0.676710)  Dp %.6f (0.323290)"
          % (b["rload"], b["vinpk"], b["D"], b["Dp"]))
    print("Kfront %.4e (1.6755e6)  wz %.4f (9.9685)  a1 %.4f (51.9850)  a0 %.4e (2.0235e5)"
          % (pl.kfront, pl.wz, pl.a1, pl.a0))
    print("F0 %.4f (71.5931)  Q %.4f (8.6531)  fRHP %.4f kHz (6.4538)"
          % (pl.f0, pl.q, b["frhp"]/1e3))
    print("|Gid| %.4f (33.3357)  ∠Gid %.4f (-89.9521)" % (abs(b["gid_ci"]), math.degrees(cmath.phase(b["gid_ci"]))))
    print("Hcs %.6f (0.998886)  ∠Hcs %.4f (-2.7052)" % (abs(b["h"]), math.degrees(cmath.phase(b["h"]))))
    print("Ti_unc %.6f (0.099896)  dB %.4f (-20.0091)  ∠ %.4f (-92.6573)"
          % (abs(b["ti_unc"]), 20*math.log10(abs(b["ti_unc"])), math.degrees(cmath.phase(b["ti_unc"]))))
    print("=== compensator ===")
    print("kappa %.6f (0.963217)  Ric %.1f k (118.1)->%.0f k  Cic1 %.4f n->%.1f n  Cic2 %.2f p->%.0f p"
          % (d["kappa"], d["ric_calc"]/1e3, d["ric"]/1e3, d["cic1_calc"]*1e9, d["cic1"]*1e9,
             d["cic2_calc"]*1e12, d["cic2"]*1e12))
    print("fz_act %.1f Hz (1020.2)  fp_act %.3f kHz (26.006)" % (d["fz_act"], d["fp_act"]/1e3))
    print("=== 8-point summary (D, F0, Q, fRHP, Ti_unc dB, ∠, fco, PM) ===")
    for op in d["rows"]:
        print("  %3d %4d  D=%.5f F0=%.2f Q=%.3f fRHP=%.3f  Tidb=%.3f ang=%.2f  fco=%.3fk PM=%.1f"
              % (op["vac"], op["pout"], op["D"], op["f0"], op["q"], op["frhp"]/1e3,
                 20*math.log10(abs(op["ti_unc"])), math.degrees(cmath.phase(op["ti_unc"])),
                 op["fco"]/1e3, op["pm"]))
