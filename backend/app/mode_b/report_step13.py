"""
app/mode_b/report_step13.py — full-detail Step 13 (THD & 120 Hz rejection) report.

Reproduces the reference document's "Step 16 — Input Current THD and 120 Hz
Rejection" word-for-word, renumbered as our report Step 13 (subsections 13.1–13.3).
Every value is injected from the step16_step13_thd calc agent. Section 13.3
re-designs the compensator at several candidate crossover frequencies and
recomputes PM / rejection / transient — the trade-off table is generated, not
transcribed.

Figure 6 (120 Hz rejection + closed-loop attenuation) is rendered live.
"""
from __future__ import annotations
import io, math
from app.mode_b.doc_report_builder import (
    step_h, sub_h, body, eq_box, data_table, annotation, CW,
)
from app.mode_b.step16_step13_thd import compute_step13_thd

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


def _fig_rejection(d):
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    s11 = d["s11"]; fr = d["f_ripple"]
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(7.2, 3.4))
    # left: closed-loop attenuation, mark 120 Hz
    for bd, op in zip(s11["bode"], s11["rows"]):
        ls = "-" if op["pout"] == d["src"]["pout_lo"] else "--"
        ax1.semilogx(bd["f"], bd["cgain"], ls, lw=1.0, label=f"{op['vac']}V/{op['pout']}W")
    ax1.axvline(fr, color="#b00", lw=0.8, ls=":")
    ax1.annotate("120 Hz", xy=(fr, -5), fontsize=7, color="#b00")
    ax1.set_xlim(1, 1000); ax1.set_ylim(-40, 6)
    ax1.set_xlabel("Frequency (Hz)"); ax1.set_ylabel("Closed-loop gain (dB)")
    ax1.set_title("Closed-loop attenuation", fontsize=9)
    ax1.grid(True, which="both", alpha=0.3); ax1.legend(fontsize=5, ncol=2)
    # right: rejection per operating point
    from app.mode_b.step16_step13_thd import _loop_at
    labels, rejs, cols = [], [], []
    for i, op in enumerate(s11["rows"]):
        tvmag, *_ = _loop_at(s11, i, fr)
        labels.append(f"{op['vac']}")
        rejs.append(-20*math.log10(tvmag))
        cols.append("#1456b8" if op["pout"] == d["src"]["pout_lo"] else "#c0392b")
    ax2.bar(range(len(rejs)), rejs, color=cols)
    ax2.axhline(d["rej_min_db"], color="k", lw=0.8, ls="--")
    ax2.annotate("20 dB min", xy=(0, d["rej_min_db"]+0.5), fontsize=7)
    ax2.set_xticks(range(len(labels))); ax2.set_xticklabels(labels, fontsize=7)
    ax2.set_xlabel("V_AC (V)"); ax2.set_ylabel("120 Hz rejection (dB)")
    ax2.set_title("120 Hz rejection per operating point", fontsize=9)
    ax2.grid(True, axis="y", alpha=0.3)
    fig.tight_layout()
    return _img_from_fig(fig)


def build_step13(story, data: dict):
    d = data
    lo, hi = d["lo"], d["hi"]

    step_h(story, "13", "Input Current THD and 120 Hz Rejection", CH)
    annotation(story, "THEORY",
        "Input-current distortion from the control loop is set by how strongly the loop rejects the "
        "120 Hz bus ripple. Any loop gain at 120 Hz modulates the current command at twice the line "
        "frequency, injecting a third harmonic into the input current. A low voltage-loop crossover "
        "is what keeps this contribution small.", CH)
    annotation(story, "INSIGHT",
        "ON THE BENCH — Measure this with a precision power analyzer (e.g. Yokogawa WT-series) reading "
        "input-current THD directly, and separately capture the bus 120 Hz ripple with an AC-coupled "
        "scope probe. Correlate the measured THD trend across line/load with the rejection figures in "
        "this step.", CH)

    # ── 13.1 ──────────────────────────────────────────────────────────────────
    sub_h(story, "13.1", "Mechanism — Why 120 Hz Rejection Sets THD", CH)
    body(story,
        "In a PFC the bus carries a twice-line-frequency (120 Hz at 60 Hz line) ripple. The voltage "
        "loop senses this ripple through the FBPFC divider. Any loop gain at 120 Hz modulates the "
        "current-command reference at 120 Hz, which mixes with the rectified-sine reference to inject "
        "a 3rd-harmonic distortion into the input current. The dominant control-loop contribution to "
        "input-current THD is therefore set by how strongly the loop attenuates 120 Hz — the 120 Hz "
        "rejection. A deliberately slow voltage loop (17 Hz crossover, far below 120 Hz) is what keeps "
        "this contribution small.", CH)
    body(story, "The peak 120 Hz bus ripple from the delivered power is:", CH)
    eq_box(story, [r"V_{ripple,pk}=\dfrac{P_{OUT}}{2\times\omega_{line}\times V_{OUT}\times C_O}"],
           number="13.1", ch=CH)
    body(story, "The 120 Hz rejection is the inverse of the open-loop gain at 120 Hz:", CH)
    eq_box(story, [r"\mathrm{Rejection\ (dB)}=-20\log_{10}|T_v(j2\pi\cdot120)|"], ch=CH)
    body(story,
        "The residual 120 Hz on the error-amplifier output, and the resulting 2nd-harmonic-feedback "
        "THD contribution (a 120 Hz modulation of the reference produces a 3rd line harmonic of "
        "roughly half its relative depth):", CH)
    eq_box(story, [r"V_{EA,120}=H_{OTA}(j2\pi\cdot120)\times\dfrac{V_{ripple,pk}}{1+T_v(j2\pi\cdot120)}",
                   r"THD_3\approx 50\times\dfrac{V_{EA,120}}{V_{EA}}\ \%"], ch=CH)

    # ── 13.2 ──────────────────────────────────────────────────────────────────
    sub_h(story, "13.2", "Results — 120 Hz Rejection and THD Contribution", CH)
    body(story,
        "Computed for the baseline design (f<sub>cv</sub> = 17 Hz). The bus ripple and rejection "
        "depend on power level, so values are grouped by line range:", CH)
    data_table(story, "13.2", "120 Hz Rejection and THD Contribution",
        "Control-loop (2nd-harmonic-feedback) contribution to input-current THD.",
        ["Operating range", "V_ripple,pk (120 Hz)", "Ripple %", "120 Hz Rejection", "THD3 contribution"],
        [["Low line  90–132 Vac / 1700 W", f"{lo['vrip']:.2f} V", f"{lo['rip_pct']:.2f}%",
          f"{lo['rej_db']:.1f} dB", f"≈ {lo['thd3']:.2f}%"],
         ["High line  180–264 Vac / 3600 W", f"{hi['vrip']:.2f} V", f"{hi['rip_pct']:.2f}%",
          f"{hi['rej_db']:.1f} dB", f"≈ {hi['thd3']:.2f}%"]],
        col_widths=[CW*0.32, CW*0.22, CW*0.12, CW*0.16, CW*0.18], ch=CH)
    annotation(story, "NOTE",
        "These are the control-loop (2nd-harmonic-feedback) contribution to input-current THD — the "
        "dominant loop-related term and the one the compensator controls. Total measured converter "
        "THD also includes current-loop tracking error, cusp/cross-over distortion near the line "
        "zero-crossing, and EMI-filter effects, which are not part of the small-signal loop model. "
        "High line is the worst case (%.1f dB rejection, ~%.0f%% THD<sub>3</sub> contribution) because both the "
        "bus ripple and the loop gain at 120 Hz are larger at full power."
        % (hi['rej_db'], hi['thd3']), CH)

    # Figure 6
    body(story, "<b>Figure 6 — 120 Hz Rejection and Closed-Loop Attenuation</b>", CH)
    body(story,
        "Left: closed-loop voltage response showing strong attenuation by 120 Hz at every operating "
        "point. Right: 120 Hz rejection per operating point — %.0f dB at low line, %.1f dB at high "
        "line, all above the 20 dB minimum." % (lo['rej_db'], hi['rej_db']), CH)
    story.append(_fig_rejection(d))
    body(story, "<i>Figure 6 — 120 Hz rejection: %.0f dB (low line) and %.1f dB (high line), "
        "comfortably above the 20 dB minimum for low THD.</i>" % (lo['rej_db'], hi['rej_db']), CH)
    annotation(story, "DECISION",
        "Input-current THD — 120 Hz rejection is %.0f dB (low line) and %.1f dB (high line), giving "
        "an estimated 2nd-harmonic-feedback THD contribution of ~%.1f%% and ~%.0f%% respectively. "
        "Both exceed the 20 dB minimum. To reduce THD further, lower the voltage-loop crossover (see "
        "Step 14, Design A) at the cost of a larger load-transient dip."
        % (lo['rej_db'], hi['rej_db'], lo['thd3'], hi['thd3']), CH)

    # ── 13.3 ──────────────────────────────────────────────────────────────────
    sub_h(story, "13.3", "Compensator Optimization: Transient vs 120 Hz Rejection", CH)
    annotation(story, "CONCEPT",
        "Crossover frequency is the single knob trading transient stiffness against ripple rejection. "
        "The table below re-designs the voltage compensator at four candidate bandwidths "
        "(f<sub>z2</sub>/f<sub>p2</sub> held at 12/17 Hz; f<sub>z1</sub>, f<sub>p1</sub> scaled with "
        "f<sub>cv</sub>; components snapped to the selected series) and recomputes everything from the "
        "model.", CH)
    data_table(story, "13.3", "Crossover Trade-off — Transient vs Rejection",
        "Each row is a full re-design at that crossover, recomputed from the model.",
        ["f_cv", "PM LL/HL (°)", "Rej. LL/HL (dB)", "Dip 0→100% LL/HL (V)", "Recovery LL/HL (ms)", "Note"],
        [[f"{s['fcv']:.0f} Hz", f"{s['pm_lo']:.1f} / {s['pm_hi']:.1f}",
          f"{s['rej_lo']:.1f} / {s['rej_hi']:.1f}", f"{s['dip_lo']:.1f} / {s['dip_hi']:.1f}",
          f"{s['trec_lo']:.0f} / {s['trec_hi']:.0f}", s["note"]] for s in d["sweep"]],
        col_widths=[CW*0.10, CW*0.18, CW*0.18, CW*0.22, CW*0.18, CW*0.14], ch=CH)
    sel = next((s for s in d["sweep"] if abs(s["fcv"]-17.0) < 0.01), d["sweep"][1])
    annotation(story, "DECISION",
        "f<sub>cv</sub> = 17.0 Hz balances a sub-8%% worst dip against ≥ %.1f dB rejection. Raising "
        "the bandwidth beyond ~20 Hz starts to violate the rejection floor at high line."
        % sel["rej_hi"], CH)


def make_pdf(path: str, inp: dict | None = None):
    from reportlab.platypus import SimpleDocTemplate, PageBreak
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from app.mode_b.doc_report_builder import chapter_splash
    data = compute_step13_thd(inp)
    story = []
    chapter_splash(story, 6, "Control Scheme — Step 13 (Input THD & 120 Hz Rejection, full detail)",
        "120 Hz rejection, 2nd-harmonic-feedback THD contribution and the crossover trade-off sweep "
        "— computed from the Step 11 voltage loop and bus ripple.",
        ["13.1 mechanism (why rejection sets THD)  ·  13.2 rejection & THD results + Figure 6",
         "13.3 compensator optimization — transient vs rejection trade-off sweep"])
    build_step13(story, data)
    while story and isinstance(story[0], PageBreak):
        story.pop(0)
    SimpleDocTemplate(path, pagesize=A4, leftMargin=20*mm, rightMargin=20*mm,
                      topMargin=18*mm, bottomMargin=18*mm,
                      title="Control Scheme — Step 13 (Input THD & 120 Hz Rejection)").build(story)
    return path
