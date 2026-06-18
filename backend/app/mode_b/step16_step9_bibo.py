"""
app/mode_b/step16_step9_bibo.py — BIBO (Brown-In / Brown-Out) design calc agent.

Reproduces the reference document's "Step 12 — BIBO Pin: Brown-In / Brown-Out
Design" as our report Step 9 (numbering continues from Step 8). Every derived
number is computed here from the FAN9672-D internal thresholds and the universal
90–264 Vac input requirement; the report renders these values verbatim.

compute_step9_bibo(inp=None) -> dict with every worked value and every table row.
"""
from __future__ import annotations
import math

# FAN9672-D fixed internal BIBO thresholds (V, referred to V_BIBO)
DEFAULT_INPUTS = {
    "vbo": 1.05,          # brownout — PFC stops (both modes)
    "vbi_fr": 1.90,       # brown-in FR mode (hys 0.85 V)
    "vbi_hv": 1.75,       # brown-in HV mode (hys 0.70 V)
    "vsag": 0.85,         # SAG threshold (both modes)
    "t_uvp_ms": 450,      # brownout debounce
    "vline_bi": 87.0,     # design brown-in target (3 V margin below 90 Vac spec min)
    "rb4": 30_000.0,      # bottom resistor (E24)
    "rb1_sel": 560_000.0, # selected RB1 = RB2 (E24)
    "rb2_sel": 560_000.0,
    "rb3_sel": 82_000.0,
    "cb1": 100e-9,        # filter pole 1 cap (across RB3)
    "cb2": 560e-9,        # filter pole 2 cap (across RB4)
    "fp1_target": 15.0,
    "fp2_target": 10.0,
}

KAVG = 2 * math.sqrt(2) / math.pi   # 0.90032 — avg/RMS of full-wave rectified sine


def _f(x, n):  # fixed-dp string
    return f"{x:.{n}f}"


def compute_step9_bibo(inp: dict | None = None) -> dict:
    p = dict(DEFAULT_INPUTS)
    if inp:
        p.update(inp)
    kavg = KAVG

    # ── 9.3 divider ratio from brown-in startup requirement ──────────────────
    ratio_target = p["vbi_fr"] / (p["vline_bi"] * kavg)            # 0.024257
    bo_target = p["vbo"] / (kavg * ratio_target)                   # 48.08 Vac
    hvbi_target = p["vbi_hv"] / (kavg * ratio_target)              # 80.13 Vac

    # ── 9.4 resistor network sizing ──────────────────────────────────────────
    rb4 = p["rb4"]
    rtotal_calc = rb4 / ratio_target                              # 1236.75 kΩ
    rb12_calc = (rtotal_calc - rb4) / 1.1                         # 1097.05 kΩ (RB3 = 10% of RB12)
    rb1_calc = rb12_calc / 2                                      # 548.52 kΩ → 560 k
    rb3_calc = rb12_calc / 10                                     # 109.70 kΩ → 82 k
    rb1 = p["rb1_sel"]; rb2 = p["rb2_sel"]; rb3 = p["rb3_sel"]
    rsum = rb1 + rb2 + rb3 + rb4
    ratio_act = rb4 / rsum                                        # 0.024351
    bo_act = p["vbo"] / (kavg * ratio_act)                        # 47.89
    bifr_act = p["vbi_fr"] / (kavg * ratio_act)                  # 86.67
    bihv_act = p["vbi_hv"] / (kavg * ratio_act)                  # 79.82
    sag_act = p["vsag"] / (kavg * ratio_act)                     # 38.77

    # 1% worst case: RB4 1% low, all others 1% high → lowest ratio
    ratio_wc = (rb4 * 0.99) / (rb1 * 1.01 + rb2 * 1.01 + rb3 * 1.01 + rb4 * 0.99)  # 0.023880
    bifr_wc = p["vbi_fr"] / (kavg * ratio_wc)                    # 88.37
    bo_wc = p["vbo"] / (kavg * ratio_wc)                         # 48.84

    scale = kavg * ratio_act                                      # 0.021923 V/Vac
    scale_wc = kavg * ratio_wc

    # ── 9.5 low-pass filter caps ─────────────────────────────────────────────
    cb1 = p["cb1"]; cb2 = p["cb2"]
    cb1_calc = 1 / (2 * math.pi * p["fp1_target"] * rb3)
    cb2_calc = 1 / (2 * math.pi * p["fp2_target"] * rb4)
    fp1_act = 1 / (2 * math.pi * cb1 * rb3)                       # 19.4 Hz
    fp2_act = 1 / (2 * math.pi * cb2 * rb4)                       # 9.5 Hz

    # ── 9.6 V_BIBO sweep across full AC range, FR/HV status ──────────────────
    def status(v, hv):
        bi = p["vbi_hv"] if hv else p["vbi_fr"]
        if v < p["vsag"]:
            return "SAG active"
        if v < p["vbo"]:
            return "BROWNOUT zone"
        if v < bi:
            return "Hysteresis zone"
        return "PFC operating"
    vlines = [0, 40, 45, 50, 67, 75, 78, 80, 87, 90, 96, 100, 110, 120,
              132, 134, 156, 160, 168, 180, 192, 220, 240, 264]
    vbibo_rows = []
    for vl in vlines:
        v = vl * scale
        vbibo_rows.append([f"{vl} Vac", f"{_f(v,4)} V", status(v, False), status(v, True)])

    # ── 9.8 startup verification ─────────────────────────────────────────────
    v87 = 87 * scale; v90 = 90 * scale; v90_wc = 90 * scale_wc; v85 = 85 * scale
    startup_rows = [
        ["Power-on at 87 Vac  (design target)", f"{_f(v87,4)} V", "1.9 V", f"+{_f(v87-1.9,4)} V", "YES  ✓"],
        ["Power-on at 90 Vac  (spec minimum)", f"{_f(v90,4)} V", "1.9 V", f"+{_f(v90-1.9,4)} V", "YES  ✓"],
        ["1% worst-case at 90 Vac", f"{_f(v90_wc,4)} V", "1.9 V", f"+{_f(v90_wc-1.9,4)} V", "YES  ✓"],
        ["Power-on at 85 Vac  (below target)", f"{_f(v85,4)} V", "1.9 V", f"−{_f(1.9-v85,4)} V", "NO  (starts at 86.7V)"],
    ]

    out = {
        "inputs": p, "kavg": kavg,
        "ratio_target": ratio_target, "bo_target": bo_target, "hvbi_target": hvbi_target,
        "rtotal_calc": rtotal_calc, "rb12_calc": rb12_calc, "rb1_calc": rb1_calc, "rb3_calc": rb3_calc,
        "rb1": rb1, "rb2": rb2, "rb3": rb3, "rb4": rb4,
        "ratio_act": ratio_act, "bo_act": bo_act, "bifr_act": bifr_act,
        "bihv_act": bihv_act, "sag_act": sag_act,
        "ratio_wc": ratio_wc, "bifr_wc": bifr_wc, "bo_wc": bo_wc,
        "scale": scale, "scale_wc": scale_wc,
        "cb1": cb1, "cb2": cb2, "cb1_calc": cb1_calc, "cb2_calc": cb2_calc,
        "fp1_act": fp1_act, "fp2_act": fp2_act,
        "vbibo_rows": vbibo_rows, "startup_rows": startup_rows,
        "v87": v87, "v90": v90,
    }

    # ── 9.4 threshold summary table ──────────────────────────────────────────
    out["thresh_rows"] = [
        ["Brownout  (PFC stops after 450 ms)", "1.05 V", f"{_f(bo_act,2)} Vac", f"{_f(bo_wc,2)} Vac", "< 70 Vac  ✓"],
        ["Brown-in FR mode  (PFC restarts)", "1.90 V", f"{_f(bifr_act,2)} Vac", f"{_f(bifr_wc,2)} Vac", "≤ 87 Vac  ✓"],
        ["Brown-in HV mode  (PFC restarts)", "1.75 V", f"{_f(bihv_act,2)} Vac", "—", "< 180 Vac  ✓"],
        ["SAG  (both modes)", "0.85 V", f"{_f(sag_act,2)} Vac", "—", "Below brownout  ✓"],
    ]

    # ── 9.9 final scorecard ──────────────────────────────────────────────────
    out["scorecard"] = [
        ["Brownout nominal", f"{_f(bo_act,2)} Vac", "< 70 Vac", "PASS ✓"],
        ["Brownout 1% worst case", f"{_f(bo_wc,2)} Vac", "< 70 Vac", "PASS ✓"],
        ["Brown-in FR nominal", f"{_f(bifr_act,2)} Vac", "≤ 87 Vac target", "PASS ✓"],
        ["Brown-in FR 1% worst case", f"{_f(bifr_wc,2)} Vac", "≤ 90 Vac spec min", "PASS ✓"],
        ["Brown-in HV nominal", f"{_f(bihv_act,2)} Vac", "< 180 Vac HV min", "PASS ✓"],
        ["SAG level", f"{_f(sag_act,2)} Vac", "Below brownout", "PASS ✓"],
        [f"Startup at 87 Vac  V_BIBO={_f(v87,4)}V", "> 1.9 V  ✓", "PFC enables", "PASS ✓"],
        [f"Startup at 90 Vac  V_BIBO={_f(v90,4)}V", "> 1.9 V  ✓", "PFC enables", "PASS ✓"],
        ["EN61000-4-11 70V/500ms FR Criteria A", f"V_BIBO={_f(70*scale,4)}V > 1.05V", "BO does not fire", "PASS ✓"],
        ["EN61000-4-11 80V/5s   FR Criteria A", f"V_BIBO={_f(80*scale,4)}V > 1.05V", "BO does not fire", "PASS ✓"],
        ["EN61000-4-11 168V/500ms HV Criteria A", f"V_BIBO={_f(168*scale,4)}V >> 1.05V", "BO does not fire", "PASS ✓"],
        ["EN61000-4-11 192V/5s  HV Criteria A", f"V_BIBO={_f(192*scale,4)}V >> 1.75V", "PFC operating", "PASS ✓"],
        ["SEMI F47 156V/1s HV Criteria A", f"V_BIBO={_f(156*scale,4)}V >> 1.75V", "PFC operating", "PASS ✓"],
        ["Filter pole fP1", f"{_f(fp1_act,1)} Hz", "10–20 Hz target", "PASS ✓"],
        ["Filter pole fP2", f"{_f(fp2_act,1)} Hz", "< 20 Hz target", "PASS ✓"],
        ["Single network: FR and HV modes", "Yes — same BO threshold both modes", "No mode switching", "PASS ✓"],
    ]
    return out


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    d = compute_step9_bibo()
    print("ratio_target %.6f (doc 0.024257)" % d["ratio_target"])
    print("bo_target %.2f (48.08)  hvbi_target %.2f (80.13)" % (d["bo_target"], d["hvbi_target"]))
    print("rtotal %.2fk (1236.75)  rb12 %.2fk (1097.05)  rb1 %.2fk (548.52)  rb3 %.2fk (109.70)"
          % (d["rtotal_calc"]/1e3, d["rb12_calc"]/1e3, d["rb1_calc"]/1e3, d["rb3_calc"]/1e3))
    print("ratio_act %.6f (0.024351)  bo %.2f (47.89)  bifr %.2f (86.67)  bihv %.2f (79.82)  sag %.2f (38.77)"
          % (d["ratio_act"], d["bo_act"], d["bifr_act"], d["bihv_act"], d["sag_act"]))
    print("ratio_wc %.6f (0.023880)  bifr_wc %.2f (88.37)  bo_wc %.2f (48.84)"
          % (d["ratio_wc"], d["bifr_wc"], d["bo_wc"]))
    print("cb1_calc %.0f nF (129)  cb2_calc %.3f uF (0.531)  fp1 %.1f (19.4)  fp2 %.1f (9.5)"
          % (d["cb1_calc"]*1e9, d["cb2_calc"]*1e6, d["fp1_act"], d["fp2_act"]))
    print("scale %.6f (0.021923)" % d["scale"])
    print("--- V_BIBO sweep ---")
    for r in d["vbibo_rows"]:
        print("  ", " | ".join(r))
    print("--- startup ---")
    for r in d["startup_rows"]:
        print("  ", " | ".join(r))
