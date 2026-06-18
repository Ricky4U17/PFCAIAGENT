"""
app/mode_b/step16_step13_thd.py — Input-current THD & 120 Hz rejection calc agent.

Reproduces the reference document's "Step 16 — Input Current THD and 120 Hz
Rejection" as our report Step 13. The dominant control-loop contribution to
input-current THD is set by how strongly the voltage loop rejects the 120 Hz bus
ripple; a deliberately slow loop (17 Hz crossover) keeps it small.

Everything is computed from the Step 11 voltage loop and the power-stage spec.
Section 16.3 re-designs the compensator at several candidate crossover
frequencies and recomputes PM / rejection / transient from the model — so the
trade-off table is generated, not transcribed.

compute_step13_thd(inp=None, prior=None) -> full worked result.
"""
from __future__ import annotations
import math, cmath

DEFAULT_INPUTS = {
    "f_line": 60.0,            # mains frequency (Hz) → 120 Hz ripple
    "f_ripple": 120.0,
    "rej_min_db": 20.0,        # minimum acceptable 120 Hz rejection
    "sweep_fcv": [12.0, 17.0, 20.0, 25.0],
}


def _loop_at(s11, idx, f):
    """|T_v|, T_v, |H_OTA|, H_OTA at frequency f for operating point idx."""
    src = s11["src"]; comp = s11["comp"]; kota = s11["kota"]
    op = s11["rows"][idx]
    w = 2*math.pi*f
    s = 1j*w
    # H_OTA shape (actual standard pole/zeros) × kota
    if comp["type"] == "type3":
        wz1, wz2 = 2*math.pi*comp["fz1a"], 2*math.pi*comp["fz2a"]
        wp1, wp2 = 2*math.pi*comp["fp1a"], 2*math.pi*comp["fp2a"]
        hshape = (1 + wz1/s)*(1 + s/wz2) / ((1 + s/wp1)*(1 + s/wp2))
    else:
        wz1, wp1 = 2*math.pi*comp["fz_a"], 2*math.pi*comp["fp_a"]
        hshape = (1 + wz1/s) / (1 + s/wp1)
    hota = kota * hshape
    # T_v,base at f (rebuild with G_i,cl ≈ 1 at 120 Hz the inner loop is unity)
    co = src["co"]; rc = src["r_c"]
    rload = op["rload"]; gmod = op["gmod"]; wrhp = op["wrhp"]
    gvp = (1 + s*co*rc)*(1 - s/wrhp) / (co*s + 2/rload)
    tvbase = gmod * gvp
    tv = tvbase * hota
    return abs(tv), tv, abs(hota), hota


def compute_step13_thd(inp: dict | None = None, prior: dict | None = None) -> dict:
    p = dict(DEFAULT_INPUTS)
    if inp:
        p.update(inp)
    from app.mode_b.step16_step11_vloop import compute_step11_vloop
    if prior is None:
        from app.mode_b.step16_steps1_8 import compute_steps_1_8
        prior = compute_steps_1_8(inp)
    s11 = compute_step11_vloop(inp, prior)
    src = s11["src"]
    vout = src["vout"]; co = src["co"]
    wline = 2*math.pi*p["f_line"]
    fr = p["f_ripple"]
    # EA output operating point per line range — back-calculated V_EA,eff (Step 6)
    vea_lo = prior["step6"]["vee_ll"]
    vea_hi = prior["step6"]["vee_hl"]

    def band(idx, pout, vea):
        vrip = pout / (2*wline*vout*co)              # peak 120 Hz bus ripple
        tvmag, tv, hmag, hota = _loop_at(s11, idx, fr)
        rej_db = -20*math.log10(tvmag)
        vea120 = hmag * vrip / abs(1 + tv)
        thd3 = 50 * vea120 / vea
        return dict(vrip=vrip, rip_pct=vrip/vout*100, rej_db=rej_db,
                    thd3=thd3, tvmag=tvmag, vea=vea)

    lo = band(0, src["pout_lo"], vea_lo)     # low line 1700 W
    hi = band(4, src["pout_hi"], vea_hi)     # high line 3600 W

    # ── 16.3 optimization sweep — redesign at each candidate f_cv ─────────────
    from app.mode_b.step16_step12_transient import compute_step12_transient
    sweep = []
    for fcv in p["sweep_fcv"]:
        # scale Type-III zero1/pole1 with crossover; hold z2/p2 at 12/17 Hz
        sc = fcv / 17.0
        ci = {"comp_type": "type3", "fz1": 3.0*sc, "fz2": 12.0, "fp1": 50.0*sc, "fp2": 17.0,
              "fcv_override": fcv}
        # prior carries fcv into step11 via inputs; pass fcv through
        s11b = compute_step11_vloop({"comp_type": "type3", "fz1": 3.0*sc, "fz2": 12.0,
                                     "fp1": 50.0*sc, "fp2": 17.0}, _prior_with_fcv(prior, fcv))
        pm_lo = s11b["rows"][0]["pm"]; pm_hi = s11b["rows"][4]["pm"]
        rb_lo = _rej(s11b, 0, src["pout_lo"], wline, vout, co, fr)
        rb_hi = _rej(s11b, 4, src["pout_hi"], wline, vout, co, fr)
        tr = compute_step12_transient({"comp_type": "type3", "fz1": 3.0*sc, "fz2": 12.0,
                                       "fp1": 50.0*sc, "fp2": 17.0},
                                      _prior_with_fcv(prior, fcv))
        w = tr["rows"][0]
        cb = s11b["comp"]
        note = "selected" if abs(fcv-17.0) < 0.01 else ("fails 20 dB floor" if rb_hi < p["rej_min_db"] else "—")
        bd_hi = s11b["bode"][4]                     # HL open-loop T_v sweep
        tw0 = tr["waves"][0]                        # 0→100% transition (LL & HL)
        sweep.append(dict(fcv=fcv, pm_lo=pm_lo, pm_hi=pm_hi, rej_lo=rb_lo, rej_hi=rb_hi,
                          dip_lo=w["dv_lo"], dip_hi=w["dv_hi"],
                          trec_lo=w["trec_lo"]*1e3, trec_hi=w["trec_hi"]*1e3, note=note,
                          r2s=cb["r2s"], c1s=cb["c1s"], c3s=cb["c3s"],
                          bode_f=bd_hi["f"], bode_g=bd_hi["ogain"],
                          tr_t=tr["t"], tr_dvhl=tw0["hl"]))

    return {"s11": s11, "src": src, "vout": vout, "lo": lo, "hi": hi,
            "vea_lo": vea_lo, "vea_hi": vea_hi,
            "f_line": p["f_line"], "f_ripple": fr, "rej_min_db": p["rej_min_db"],
            "wline": wline, "sweep": sweep, "p": p}


def _rej(s11, idx, pout, wline, vout, co, fr):
    tvmag, *_ = _loop_at(s11, idx, fr)
    return -20*math.log10(tvmag)


def _prior_with_fcv(prior, fcv):
    """Return a prior steps1-8 result with fcv overridden (for the sweep)."""
    from app.mode_b.step16_steps1_8 import compute_steps_1_8
    if prior is None:
        return compute_steps_1_8({"fcv": fcv})
    # rebuild from same inputs but new fcv
    inp = dict(prior["inputs"]); inp["fcv"] = fcv
    return compute_steps_1_8(inp)


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    d = compute_step13_thd()
    print("doc 16.2: LL Vrip 2.60V 0.66%% rej 30.0dB THD3 1.45%% | HL 5.51V 1.40%% 23.5dB 2.99%%")
    lo, hi = d["lo"], d["hi"]
    print("LL: Vrip %.2f V  %.2f%%  rej %.1f dB  THD3 %.2f%%" % (lo["vrip"], lo["rip_pct"], lo["rej_db"], lo["thd3"]))
    print("HL: Vrip %.2f V  %.2f%%  rej %.1f dB  THD3 %.2f%%" % (hi["vrip"], hi["rip_pct"], hi["rej_db"], hi["thd3"]))
    print("--- 16.3 sweep (doc: 12Hz 83.3/86.9 35.1/28.6 -33.9/-37.8 234/240; 17 79.4/81.9 30.2/23.7 -25.8/-29.1 146/142;")
    print("              20 79.7/81.2 27.4/20.9 -22.5/-25.2 123/119; 25 76.9/76.5 25.0/18.5 -18.6/-21.2 92/86) ---")
    for s in d["sweep"]:
        print("  %4.0fHz PM %.1f/%.1f  Rej %.1f/%.1f  Dip %+.1f/%+.1f  Rec %.0f/%.0f  %s"
              % (s["fcv"], s["pm_lo"], s["pm_hi"], s["rej_lo"], s["rej_hi"],
                 s["dip_lo"], s["dip_hi"], s["trec_lo"], s["trec_hi"], s["note"]))
