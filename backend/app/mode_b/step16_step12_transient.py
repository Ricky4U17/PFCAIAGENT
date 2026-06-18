"""
app/mode_b/step16_step12_transient.py — Step Load Transient Response calc agent.

Reproduces the reference document's "Step 15 — Step Load Transient Response" as our
report Step 12. A load-current step is rejected through the closed-loop output
impedance Z_cl(s) = Z_open(s)/(1+T_v(s)); the bus deviation is the step acting
through Z_cl. Because the voltage compensator integrates, Z_cl is zero at DC, so
the bus always recovers fully — only the peak dip and recovery time are in question.

Everything is computed from the Step 11 voltage loop (compensator, plant, operating
points) and the power-stage spec — nothing hard-coded. The inner current loop is
≈unity at the voltage-loop timescale, so G_i,cl = 1 is used for the transient (as
the document states).

compute_step12_transient(inp=None, prior=None) -> full worked result.
"""
from __future__ import annotations
import math
import numpy as np
from scipy import signal

DEFAULT_INPUTS = {
    "rec_band_pct": 1.0,       # ±1% recovery band
    "t_end": 0.8,             # simulation horizon (s)
    "n_pts": 40000,
}

# six load transitions: (label, fraction-of-full step), sign +=load increase (dip)
TRANSITIONS = [
    ("0 → 100%  (full step up)", +1.0),
    ("0 → 50%", +0.5),
    ("50 → 100%", +0.5),
    ("100 → 0%  (full step down)", -1.0),
    ("50 → 0%", -0.5),
    ("100 → 50%", -0.5),
]


def _zcl_tf(op, s11, kota, comp):
    """Closed-loop output impedance Z_cl(s)=Z_open/(1+T_v), as (num,den) poly coeffs.

    T_v(s) = GMOD · G_vp(s) · H_OTA(s)   (G_i,cl ≈ 1 at this timescale).
    """
    co = s11["co"]; rc = s11["r_c"]
    rload = op["rload"]; gmod = op["gmod"]; wrhp = op["wrhp"]
    # pole/zero (actual standard components) from Step 11
    if comp["type"] == "type3":
        wz1, wz2 = 2*math.pi*comp["fz1a"], 2*math.pi*comp["fz2a"]
        wp1, wp2 = 2*math.pi*comp["fp1a"], 2*math.pi*comp["fp2a"]
        # H_OTA = kota·(1+wz1/s)(1+s/wz2)/[(1+s/wp1)(1+s/wp2)]
        gain = kota * (wp1 * wp2) / wz2
        num_h = gain * np.poly1d([1, wz1]) * np.poly1d([1, wz2])
        den_h = np.poly1d([1, 0]) * np.poly1d([1, wp1]) * np.poly1d([1, wp2])
    else:
        wz1 = 2*math.pi*comp["fz_a"]; wp1 = 2*math.pi*comp["fp_a"]
        gain = kota * wp1 / 1.0
        num_h = gain * np.poly1d([1, wz1])
        den_h = np.poly1d([1, 0]) * np.poly1d([1, wp1])

    num_gvp = np.poly1d([co*rc, 1]) * np.poly1d([-1/wrhp, 1])
    den_gvp = np.poly1d([co, 2/rload])
    num_tv = gmod * num_gvp * num_h
    den_tv = den_gvp * den_h

    num_zo = np.poly1d([co*rc, 1])
    den_zo = np.poly1d([co, 2/rload])

    # Z_cl = num_zo·den_tv / [den_zo·(den_tv + num_tv)]
    ret_diff = den_tv + num_tv
    num_zcl = (num_zo * den_tv).coeffs
    den_zcl = (den_zo * ret_diff).coeffs
    return num_zcl, den_zcl


def compute_step12_transient(inp: dict | None = None, prior: dict | None = None) -> dict:
    p = dict(DEFAULT_INPUTS)
    if inp:
        p.update(inp)
    from app.mode_b.step16_step11_vloop import compute_step11_vloop
    s11 = compute_step11_vloop(inp, prior)
    src = s11["src"]
    vout = src["vout"]
    band = p["rec_band_pct"]/100.0 * vout
    ifull_lo = src["pout_lo"]/vout
    iful_hi = src["pout_hi"]/vout

    # representative op per line range (transient depends on power, not line voltage)
    op_lo = s11["rows"][0]      # 90 Vac / 1700 W
    op_hi = s11["rows"][4]      # 180 Vac / 3600 W

    t = np.linspace(0, p["t_end"], p["n_pts"])

    def response(op):
        num, den = _zcl_tf(op, src, s11["kota"], s11["comp"])
        _, y = signal.step((num, den), T=t)         # step response of Z_cl (unit ΔI)
        return y

    y_lo = response(op_lo)       # volts per amp of step
    y_hi = response(op_hi)

    def metrics(y, di):
        dv = -di * y                                 # ΔVout(t)
        peak = dv[np.argmax(np.abs(dv))]
        over = np.where(np.abs(dv) > band)[0]
        trec = t[over[-1]] if len(over) else 0.0
        return peak, trec

    rows = []
    for label, frac in TRANSITIONS:
        di_lo = frac * ifull_lo
        di_hi = frac * iful_hi
        plo, tlo = metrics(y_lo, di_lo)
        phi, thi = metrics(y_hi, di_hi)
        rows.append(dict(label=label, di_lo=di_lo, di_hi=di_hi,
                         dv_lo=plo, pct_lo=plo/vout*100, trec_lo=tlo,
                         dv_hi=phi, pct_hi=phi/vout*100, trec_hi=thi))

    # waveform traces for Figure 5 (per transition, LL & HL)
    waves = []
    for label, frac in TRANSITIONS:
        waves.append(dict(label=label,
                          t=t, ll=-frac*ifull_lo*y_lo, hl=-frac*iful_hi*y_hi))

    worst_hl = max(rows, key=lambda r: abs(r["dv_hi"]))
    worst_ll = max(rows, key=lambda r: abs(r["dv_lo"]))
    return {
        "s11": s11, "src": src, "vout": vout, "band": band,
        "ifull_lo": ifull_lo, "iful_hi": iful_hi, "rows": rows, "waves": waves, "t": t,
        "worst_hl": worst_hl, "worst_ll": worst_ll, "p": p,
    }


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    d = compute_step12_transient()
    print("band ±%.2f V  I_full %.3f/%.3f A (4.318/9.144)"
          % (d["band"], d["src"]["pout_lo"]/d["vout"], d["iful_hi"]))
    print("doc 15.3: 0→100 LL -25.9V/154ms HL -28.9V/152ms ; 0→50 LL -13.0/122 HL -14.5/112")
    for r in d["rows"]:
        print("  %-26s LL %+6.1fV %+5.1f%% %4.0fms | HL %+6.1fV %+5.1f%% %4.0fms"
              % (r["label"], r["dv_lo"], r["pct_lo"], r["trec_lo"]*1e3,
                 r["dv_hi"], r["pct_hi"], r["trec_hi"]*1e3))
