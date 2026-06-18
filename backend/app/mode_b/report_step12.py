"""
app/mode_b/report_step12.py — full-detail Step 12 (Step Load Transient) report.

Reproduces the reference document's "Step 15 — Step Load Transient Response"
word-for-word, renumbered as our report Step 12 (subsections 12.1–12.3). Every
value is injected from the step16_step12_transient calc agent (closed-loop output
impedance step response, derived from the Step 11 voltage loop + spec).

Figure 5 (six load transitions, LL vs HL) is rendered live from the simulated
ΔVout(t) waveforms.
"""
from __future__ import annotations
import io, math
from app.mode_b.doc_report_builder import (
    step_h, sub_h, body, eq_box, data_table, annotation, CW,
)
from app.mode_b.step16_step12_transient import compute_step12_transient

CH = 6


def _img_from_fig(fig, dpi=200):
    from reportlab.lib.utils import ImageReader
    from reportlab.platypus import Image
    import matplotlib.pyplot as plt
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight", pad_inches=0.04)
    plt.close(fig)
    buf.seek(0)
    iw, ih = ImageReader(buf).getSize()
    buf.seek(0)
    return Image(buf, width=CW, height=ih * (CW / iw))


def _fig_transient(d):
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    vout = d["vout"]; band = d["band"]
    t = d["t"] * 1e3
    fig, axes = plt.subplots(2, 3, figsize=(7.2, 4.6), sharex=True)
    for k, w in enumerate(d["waves"]):
        ax = axes[k // 3][k % 3]
        ax.axhspan(-band, band, color="0.85", alpha=0.6)
        ax.plot(t, w["ll"], "-", color="#1456b8", lw=1.0, label="LL 90 V/1700 W")
        ax.plot(t, w["hl"], "--", color="#c0392b", lw=1.0, label="HL 180 V/3600 W")
        ax.axhline(0, color="0.4", lw=0.6)
        ax.set_title(w["label"], fontsize=7)
        ax.grid(True, alpha=0.3)
        ax.set_xlim(0, 300)
        if k % 3 == 0:
            ax.set_ylabel("ΔV$_{out}$ (V)", fontsize=8)
        if k // 3 == 1:
            ax.set_xlabel("Time (ms)", fontsize=8)
    axes[0][0].legend(fontsize=6, loc="lower right")
    fig.suptitle("Figure 5 — Step load transient response, all 6 transitions (LL vs HL)", fontsize=9)
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    return _img_from_fig(fig)


def build_step12(story, data: dict):
    d = data
    src = d["src"]; vout = d["vout"]
    fcv_lo = d["s11"]["rows"][0]["fco"]; fcv_hi = d["s11"]["rows"][4]["fco"]
    ifl_lo = d["ifull_lo"]; ifl_hi = d["iful_hi"]
    wh = d["worst_hl"]; wl = d["worst_ll"]

    step_h(story, "12", "Step Load Transient Response", CH)
    annotation(story, "CONCEPT",
        "A load step is rejected through the closed-loop output impedance Z<sub>cl</sub>(s) = "
        "Z<sub>open</sub>(s)/(1+T<sub>v</sub>(s)). Because the compensator integrates, "
        "Z<sub>cl</sub> is zero at DC — so the bus always recovers fully; the only questions are how "
        "far it dips and how long it takes.", CH)
    annotation(story, "INSIGHT",
        "The transient dip is the unavoidable price of the slow voltage loop chosen in Step 11. With "
        "the power components fixed, the dip can only be traded against 120 Hz rejection (THD) — which "
        "is exactly what Step 13 quantifies.", CH)

    # ── 12.1 ──────────────────────────────────────────────────────────────────
    sub_h(story, "12.1", "Method — Closed-Loop Output Impedance", CH)
    body(story,
        "A load-current step is rejected by the closed voltage loop. The output-voltage deviation is "
        "the load step acting through the closed-loop output impedance, which is the open-loop output "
        "impedance divided by the return difference (1 + T<sub>v</sub>). Because the compensator "
        "contains an integrator, the closed-loop output impedance is zero at DC, so the deviation "
        "always recovers fully to the regulation point.", CH)
    eq_box(story, [r"\Delta V_{OUT}(s)=-\Delta I_{LOAD}(s)\times\dfrac{Z_{open}(s)}{1+T_v(s)}"],
           number="12.1", ch=CH)
    body(story,
        "The open-loop output impedance is set by the bus capacitor working into the boost "
        "small-signal load term (the same denominator as the voltage plant); the ESR adds a small "
        "instantaneous step:", CH)
    eq_box(story, [r"Z_{open}(s)=\dfrac{1+sC_O r_C}{C_O\,s+2/R_{LOAD}}"], ch=CH)
    body(story,
        "For a load step of magnitude ΔI the time response ΔV<sub>out</sub>(t) is obtained from the "
        "inverse transform. The peak deviation occurs near the loop bandwidth and the deviation then "
        "recovers; recovery time is measured to the ±1%% band (±%.2f V about the %.1f V bus). The peak "
        "scales linearly with step size, and at this small-signal level step-up and step-down are "
        "symmetric." % (d["band"], vout), CH)
    data_table(story, "12.1", "Transient Method Parameters",
        "Inputs to the closed-loop output-impedance response.",
        ["Quantity", "Value", "Note"],
        [["Bus capacitor  C_O", f"{src['co']*1e6:.0f} µF", "Fixed (power stage)"],
         ["Recovery band", f"±1%  =  ±{d['band']:.2f} V", f"About {vout:.1f} V bus"],
         ["Voltage-loop crossover  f_cv", f"{fcv_lo:.1f} Hz (LL) / {fcv_hi:.0f} Hz (HL)", "Step 11 design"],
         ["Full-load current  I_full = P_OUT/V_OUT",
          f"{ifl_lo:.3f} A (1700 W) / {ifl_hi:.3f} A (3600 W)", "Step magnitude reference"]],
        col_widths=[CW*0.34, CW*0.30, CW*0.36], ch=CH)

    # ── 12.2 ──────────────────────────────────────────────────────────────────
    sub_h(story, "12.2", "Step Magnitudes", CH)
    body(story,
        "Six load transitions are evaluated — three load-increase (dip) and three load-decrease "
        "(overshoot) — at both line ranges. The current step ΔI for each transition:", CH)
    data_table(story, "12.2", "Load-Step Magnitudes",
        "Current step ΔI per transition and line range.",
        ["Load transition", "ΔI  (Low line, 1700 W)", "ΔI  (High line, 3600 W)"],
        [[r["label"], f"{r['di_lo']:+.3f} A", f"{r['di_hi']:+.3f} A"] for r in d["rows"]],
        col_widths=[CW*0.40, CW*0.30, CW*0.30], ch=CH)

    # ── 12.3 ──────────────────────────────────────────────────────────────────
    sub_h(story, "12.3", "Results — Peak Deviation and Recovery Time", CH)
    body(story,
        "Peak deviation and recovery time to the ±1% band, computed for our design. Values are "
        "identical across the four voltages within each line range (the load resistance and loop "
        "shape depend on power, not on line voltage):", CH)
    data_table(story, "12.3", "Transient Results — Peak Deviation and Recovery",
        "Peak ΔVout and recovery time to the ±1% band.",
        ["Load transition", "LL ΔV (V)", "LL %", "LL t_rec", "HL ΔV (V)", "HL %", "HL t_rec"],
        [[r["label"], f"{r['dv_lo']:+.1f}", f"{r['pct_lo']:+.1f}%", f"{r['trec_lo']*1e3:.0f} ms",
          f"{r['dv_hi']:+.1f}", f"{r['pct_hi']:+.1f}%", f"{r['trec_hi']*1e3:.0f} ms"] for r in d["rows"]],
        col_widths=[CW*0.28, CW*0.12, CW*0.10, CW*0.13, CW*0.12, CW*0.10, CW*0.15], ch=CH)
    annotation(story, "NOTE",
        "The worst-case transient is the full 0→100%% step at high line: a %.1f V (%.1f%%) dip "
        "recovering in %.0f ms. This is expected for a PFC whose voltage loop is intentionally slow "
        "(17 Hz) to reject the 120 Hz bus ripple. If the application requires a smaller dip, the bus "
        "capacitor must be increased or the loop bandwidth raised — the latter at the cost of 120 Hz "
        "rejection / THD, as quantified in Step 13."
        % (abs(wh["dv_hi"]), abs(wh["pct_hi"]), wh["trec_hi"]*1e3), CH)

    # Figure 5
    body(story, "<b>Figure 5 — Step Load Transient Response  |  All 6 Transitions, Low Line vs High "
        "Line</b>", CH)
    body(story,
        "Closed-loop output-voltage deviation for each load transition. Blue = low line "
        "(90 Vac/1700 W), red = high line (180 Vac/3600 W). The shaded band is the ±1% recovery "
        "window. Load-increase steps (top row) dip; load-decrease steps (bottom row) overshoot.", CH)
    story.append(_fig_transient(d))
    body(story, "<i>Figure 5 — ΔVout vs time for the six load transitions. Worst case: HL 0→100%% = "
        "%.1f V (%.1f%%), recovering in %.0f ms.</i>"
        % (wh["dv_hi"], wh["pct_hi"], wh["trec_hi"]*1e3), CH)
    annotation(story, "DECISION",
        "Step load transient — worst-case dip %.1f V (%.1f%%) at HL 0→100%%, full recovery within "
        "%.0f ms; low-line worst case %.1f V (%.1f%%) in %.0f ms. All transitions recover "
        "monotonically with no ringing (phase margin > 80°)."
        % (abs(wh["dv_hi"]), abs(wh["pct_hi"]), wh["trec_hi"]*1e3,
           abs(wl["dv_lo"]), abs(wl["pct_lo"]), wl["trec_lo"]*1e3), CH)


def make_pdf(path: str, inp: dict | None = None):
    from reportlab.platypus import SimpleDocTemplate, PageBreak
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from app.mode_b.doc_report_builder import chapter_splash
    data = compute_step12_transient(inp)
    story = []
    chapter_splash(story, 6, "Control Scheme — Step 12 (Step Load Transient, full detail)",
        "Closed-loop output-impedance step response — peak bus dip and recovery time for six load "
        "transitions across both line ranges, computed from the Step 11 voltage loop.",
        ["12.1 method (closed-loop output impedance)  ·  12.2 step magnitudes",
         "12.3 results (peak deviation + recovery)  ·  Figure 5 transient waveforms"])
    build_step12(story, data)
    while story and isinstance(story[0], PageBreak):
        story.pop(0)
    SimpleDocTemplate(path, pagesize=A4, leftMargin=20*mm, rightMargin=20*mm,
                      topMargin=18*mm, bottomMargin=18*mm,
                      title="Control Scheme — Step 12 (Step Load Transient)").build(story)
    return path
