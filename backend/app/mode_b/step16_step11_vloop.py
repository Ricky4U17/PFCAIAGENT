"""
app/mode_b/step16_step11_vloop.py — Outer Voltage Loop design calc agent.

Reproduces the reference document's "Step 14 — Outer Voltage Loop Design" as our
report Step 11. Method B (SLVA662): the feedback divider is folded into the OTA
compensator, so the evaluated base loop gain excludes both divider and compensator.

Design rules honoured (per the design engineer's instruction):
  • Crossover (f_cv) and ALL compensator pole/zero frequencies are DESIGNER INPUTS,
    never hard-coded — they arrive through DEFAULT_INPUTS / the GUI.
  • The current-sense filter pole (f_RC) is selected upstream in Step 10 (R_M, C_M)
    and consumed here through the inner-loop transfer function.
  • The CURRENT loop is always Type-2 (Step 10). The VOLTAGE loop compensator is
    selectable: comp_type = 'type3' (default, matches the reference) or 'type2'.

Everything else (V_OUT, L, C_O, K_MAX, V_FBPFC, the divider R1/R4, the inner loop
T_i(s)) is pulled from the prior steps — nothing the engineer already established
is re-entered here.

compute_step11_vloop(inp=None, prior=None) -> full worked result.
"""
from __future__ import annotations
import math, cmath

SQRT2 = math.sqrt(2.0)

DEFAULT_INPUTS = {
    "comp_type": "type3",     # 'type3' (reference) | 'type2'
    "gmv": 100e-6,            # voltage-loop OTA transconductance (S) — designer/datasheet
    "design_corner": "HL",    # size compensator at high-line 3600 W
    # Type-III pole/zero targets (Hz) — DESIGNER SELECTED
    "fz1": 3.0, "fz2": 12.0, "fp1": 50.0, "fp2": 17.0,
    # Type-II pole/zero targets (Hz) — used when comp_type == 'type2'
    "fz": 3.0, "fp": 50.0,
    "vac_ll": [90, 110, 120, 132],
    "vac_hl": [180, 210, 220, 264],
}

_E12 = [1.0, 1.2, 1.5, 1.8, 2.2, 2.7, 3.3, 3.9, 4.7, 5.6, 6.8, 8.2]
_E24 = [1.0, 1.1, 1.2, 1.3, 1.5, 1.6, 1.8, 2.0, 2.2, 2.4, 2.7, 3.0,
        3.3, 3.6, 3.9, 4.3, 4.7, 5.1, 5.6, 6.2, 6.8, 7.5, 8.2, 9.1]
_E96 = [round(10 ** (i / 96), 2) for i in range(96)]


def _snap(x, series):
    if x <= 0:
        return x
    d = math.floor(math.log10(x))
    base = x / 10 ** d
    best = min(series, key=lambda e: abs(e - base))
    return best * 10 ** d


def _e24(x):  # caps
    return _snap(x, _E24)


def _e96(x):  # resistors
    return _snap(x, _E96)


def compute_step11_vloop(inp: dict | None = None, prior: dict | None = None) -> dict:
    p = dict(DEFAULT_INPUTS)
    if inp:
        p.update(inp)
    if prior is None:
        from app.mode_b.step16_steps1_8 import compute_steps_1_8
        prior = compute_steps_1_8()
    from app.mode_b.step16_step10_iloop import compute_step10_iloop
    s10 = compute_step10_iloop(prior=prior)

    pin, pc = prior["inputs"], prior["const"]
    vout = pin["vout"]
    lphi = pin["lphi_uH"] * 1e-6
    co = pin["cout_uF"] * 1e-6
    nch = pin["nch"]
    pout_lo, pout_hi = pin["pout_lo"], pin["pout_hi"]
    kmax = pc["kmax"]                       # Step 6 multiplier selection
    vfbpfc = pc["vref"]                     # FBPFC regulation point (2.5 V)
    vramp = s10["p"]["v_ramp"]
    r_c = s10["p"]["r_c"]
    r1 = prior["step5"]["rfb1"]             # divider top (3.63 MΩ)
    r4 = prior["step5"]["rfb2"]             # divider bottom (23.2 kΩ)
    fcv = pin["fcv"]                        # Step 4 GUI voltage crossover
    gmv = p["gmv"]
    leq = lphi / nch                        # combined two-phase plant inductance
    hv = vfbpfc / vout                      # feedback divider

    # ── inner-loop T_i(s) rebuilt from Step 10 (per-op plant + Type-2 OTA) ─────
    ric = s10["ric"]; rn10 = s10["ramp_norm"]; f_rc = s10["f_rc"]
    gmi = s10["p"]["g_mi"]; wz_c = 2*math.pi*s10["fz_act"]; wp_c = 2*math.pi*s10["fp_act"]

    def Ti(idx, w):
        pl = s10["rows"][idx]["plant"]
        hcs = 1.0 / (1 + 1j*w/(2*math.pi*f_rc))
        ziea = ric * (1 + wz_c/(1j*w)) / (1 + 1j*w/wp_c)
        return pl.gid(w) * rn10 * hcs * gmi * ziea

    ops = [(v, pout_lo) for v in p["vac_ll"]] + [(v, pout_hi) for v in p["vac_hl"]]
    wcv = 2*math.pi*fcv

    def op_base(idx, vac, pout, w):
        rload = vout**2 / pout
        iout = pout / vout
        gmod = kmax * iout / vramp
        Dp = SQRT2 * vac / vout
        wrhp = rload * Dp**2 / leq
        frhp = wrhp / (2*math.pi)
        s = 1j*w
        ti = Ti(idx, w)
        gicl = (ti/nch) / (1 + ti/nch)
        gvp = (1 + s*co*r_c) * (1 - s/wrhp) / (co*s + 2/rload)
        tvbase = gmod * gicl * gvp
        return dict(idx=idx, vac=vac, pout=pout, rload=rload, iout=iout, gmod=gmod,
                    Dp=Dp, wrhp=wrhp, frhp=frhp, ti=ti, gicl=gicl, gvp=gvp, tvbase=tvbase)

    rows = [op_base(i, v, pw, wcv) for i, (v, pw) in enumerate(ops)]
    design_idx = 4 if p["design_corner"] == "HL" else 0
    dr = rows[design_idx]
    tvbase_mag = abs(dr["tvbase"])
    G = 1.0 / tvbase_mag                     # required compensator gain at f_cv

    # ── compensator design ────────────────────────────────────────────────────
    comp = {"type": p["comp_type"]}
    rp = r1 * r4 / (r1 + r4)                  # R1 ∥ R4

    if p["comp_type"] == "type3":
        fz1, fz2, fp1, fp2 = p["fz1"], p["fz2"], p["fp1"], p["fp2"]
        a = math.sqrt(1 + (fcv/fp2)**2)
        b = math.sqrt(1 + (fcv/fp1)**2)
        c = math.sqrt(1 + (fz1/fcv)**2)
        dd = math.sqrt(1 + (fcv/fz2)**2)
        aa = (a*b) / (c*dd)
        bb = G * fp2 * (r1 + r4) / (r4 * gmv * (fp2 - fz1))
        r2 = aa * bb
        rho = fz2 / fp2
        r3 = (rho*r1 - rp) / (1 - rho)
        c2 = 1.0 / (2*math.pi*(r1 + r3)*fz2)
        c1 = 1.0 / (2*math.pi*fz1*r2)
        c3 = c1 / (2*math.pi*r2*c1*fp1 - 1)
        r2s, r3s = _e96(r2), _e96(r3)
        # integrator cap rounds to E12 (large value); precision caps to E24
        c1s, c2s, c3s = _snap(c1, _E12), _e24(c2), _e24(c3)
        # 14.8 pole/zero verification — from CALCULATED components (→ exact targets)
        fz1c = 1.0 / (2*math.pi*r2*c1)
        fz2c = 1.0 / (2*math.pi*(r1 + r3)*c2)
        fp1c = (c1 + c3) / (2*math.pi*r2*c1*c3)
        fp2c = 1.0 / (2*math.pi*(r3 + rp)*c2)
        # actual pole/zero from STANDARD components (used for 14.9 evaluation)
        rp_s = r1*r4/(r1+r4)
        fz1a = 1.0 / (2*math.pi*r2s*c1s)
        fz2a = 1.0 / (2*math.pi*(r1 + r3s)*c2s)
        fp1a = (c1s + c3s) / (2*math.pi*r2s*c1s*c3s)
        fp2a = 1.0 / (2*math.pi*(r3s + rp_s)*c2s)
        comp.update(a=a, b=b, c=c, d=dd, aa=aa, bb=bb,
                    fz1=fz1, fz2=fz2, fp1=fp1, fp2=fp2,
                    r2=r2, r3=r3, c1=c1, c2=c2, c3=c3,
                    r2s=r2s, r3s=r3s, c1s=c1s, c2s=c2s, c3s=c3s,
                    fz1c=fz1c, fz2c=fz2c, fp1c=fp1c, fp2c=fp2c,
                    fz1a=fz1a, fz2a=fz2a, fp1a=fp1a, fp2a=fp2a)
        wz1, wz2 = 2*math.pi*fz1a, 2*math.pi*fz2a
        wp1, wp2 = 2*math.pi*fp1a, 2*math.pi*fp2a

        def hshape(w):
            s = 1j*w
            return (1 + wz1/s) * (1 + s/wz2) / ((1 + s/wp1) * (1 + s/wp2))
    else:  # type2
        fz, fp = p["fz"], p["fp"]
        kappa = math.sqrt(1 + (fz/fcv)**2) / math.sqrt(1 + (fcv/fp)**2)
        r2 = G * (r1 + r4) / (r4 * gmv * kappa)
        c1 = 1.0 / (2*math.pi*fz*r2)
        c3 = 1.0 / (2*math.pi*fp*r2)
        r2s = _e96(r2); c1s, c3s = _e24(c1), _e24(c3)
        fz_a = 1.0 / (2*math.pi*r2s*c1s)
        fp_a = 1.0 / (2*math.pi*r2s*c3s)
        comp.update(fz=fz, fp=fp, kappa=kappa, r2=r2, c1=c1, c3=c3,
                    r2s=r2s, c1s=c1s, c3s=c3s, fz_a=fz_a, fp_a=fp_a)
        wz1, wp1 = 2*math.pi*fz_a, 2*math.pi*fp_a

        def hshape(w):
            s = 1j*w
            return (1 + wz1/s) / (1 + s/wp1)

    # normalise so the design-corner crossover is exactly f_cv (0 dB there)
    kota = 1.0 / abs(dr["tvbase"] * hshape(wcv))

    def tv_full(idx, w):
        return op_base(idx, ops[idx][0], ops[idx][1], w)["tvbase"] * kota * hshape(w)

    def crossover_pm(idx):
        lo, hi = 2*math.pi*0.5, 2*math.pi*100.0
        for _ in range(80):
            mid = math.sqrt(lo*hi)
            if abs(tv_full(idx, mid)) > 1:
                lo = mid
            else:
                hi = mid
        wco = math.sqrt(lo*hi)
        pm = 180 + math.degrees(cmath.phase(tv_full(idx, wco)))
        return wco/(2*math.pi), pm

    for i, op in enumerate(rows):
        fco, pm = crossover_pm(i)
        op["fco"], op["pm"] = fco, pm
        op["loopdb_fcv"] = 20*math.log10(abs(tv_full(i, wcv)))

    # Bode sweep (open + closed) for figures
    fsweep = [10 ** (-0.3 + 3.3*i/240) for i in range(241)]   # 0.5 Hz → 1 kHz
    bode = []
    for i, op in enumerate(rows):
        og, oph, cg, cph = [], [], [], []
        for f in fsweep:
            t = tv_full(i, 2*math.pi*f)
            og.append(20*math.log10(abs(t))); oph.append(math.degrees(cmath.phase(t)))
            cl = t/(1+t)
            cg.append(20*math.log10(abs(cl))); cph.append(math.degrees(cmath.phase(cl)))
        bode.append(dict(vac=op["vac"], pout=op["pout"], f=fsweep,
                         ogain=og, ophase=oph, cgain=cg, cphase=cph))

    return {
        "src": {"vout": vout, "lphi": lphi, "co": co, "nch": nch, "leq": leq,
                "pout_lo": pout_lo, "pout_hi": pout_hi, "kmax": kmax, "vfbpfc": vfbpfc,
                "vramp": vramp, "r_c": r_c, "r1": r1, "r4": r4, "fcv": fcv, "gmv": gmv, "hv": hv},
        "rows": rows, "G": G, "tvbase_mag_design": tvbase_mag, "design_idx": design_idx,
        "comp": comp, "kota": kota, "bode": bode, "p": p,
    }


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    d = compute_step11_vloop()
    s = d["src"]; cm = d["comp"]
    dr = d["rows"][d["design_idx"]]
    print("Hv %.6f (0.006350)  Leq %.1f µH (117.5)" % (s["hv"], s["leq"]*1e6))
    print("=== 180Vac/3600W design point ===")
    print("RLOAD %.4f (43.0555)  IOUT %.4f (9.1440)  GMOD %.4f (2.7249)  D' %.4f (0.6466)  fRHP %.2f kHz (24.38)"
          % (dr["rload"], dr["iout"], dr["gmod"], dr["Dp"], dr["frhp"]/1e3))
    print("Ti(17Hz) %.2f%+.2fj  |Ti|=%.2f (433.65)  ∠=%.2f (-10.81)"
          % (dr["ti"].real, dr["ti"].imag, abs(dr["ti"]), math.degrees(cmath.phase(dr["ti"]))))
    print("Gicl %.6f%+.6fj |%.5f|(0.99549) ∠%.4f(-0.0493)"
          % (dr["gicl"].real, dr["gicl"].imag, abs(dr["gicl"]), math.degrees(cmath.phase(dr["gicl"]))))
    print("Gvp %.5f%+.5fj |%.5f|(4.17471) ∠%.2f(-78.72)"
          % (dr["gvp"].real, dr["gvp"].imag, abs(dr["gvp"]), math.degrees(cmath.phase(dr["gvp"]))))
    print("Tvbase %.4f (11.3244) dB %.2f (21.08)" % (abs(dr["tvbase"]), 20*math.log10(abs(dr["tvbase"]))))
    print("Tv=Tvbase*Hv %.5f (0.07191) dB %.2f (-22.86)" % (abs(dr["tvbase"])*s["hv"], 20*math.log10(abs(dr["tvbase"])*s["hv"])))
    print("G(req) %.6f (0.088305)" % d["G"])
    if cm["type"] == "type3":
        print("a %.4f b %.4f c %.4f d %.4f aa %.4f (0.8483)" % (cm["a"], cm["b"], cm["c"], cm["d"], cm["aa"]))
        print("bb %.2f k (168.85)  R2 %.2f k (143.23)  R3 %.4f M (8.6336)  C1 %.2f n (370.39)  C2 %.4f n (1.0815)  C3 %.2f n (23.64)"
              % (cm["bb"]/1e3, cm["r2"]/1e3, cm["r3"]/1e6, cm["c1"]*1e9, cm["c2"]*1e9, cm["c3"]*1e9))
        print("std: R2 %.0fk R3 %.2fM C1 %.0fn C2 %.1fn C3 %.0fn" %
              (cm["r2s"]/1e3, cm["r3s"]/1e6, cm["c1s"]*1e9, cm["c2s"]*1e9, cm["c3s"]*1e9))
        print("PZ verify (std): fz1 %.3f fz2 %.3f fp1 %.3f fp2 %.3f" % (cm["fz1a"], cm["fz2a"], cm["fp1a"], cm["fp2a"]))
    print("=== 14.9 crossover/PM ===")
    for op in d["rows"]:
        print("  %3d %4d  loop@fcv %.2f dB  fco %.2f Hz  PM %.1f" %
              (op["vac"], op["pout"], op["loopdb_fcv"], op["fco"], op["pm"]))
