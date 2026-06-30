"""
app/mode_b/report_step14.py — Step 14 (Compensator Optimization) report.

Reproduces the reference document's "Step 17 — Loop Equation Accuracy and
Compensator Optimization", renumbered as our report Step 14. Per the design
engineer's instruction the PITFALL and §17.1 (and its Figure 7) are omitted; only
§17.2 is reproduced, placed after the INSIGHT as §14.1.

The four trade-off designs are computed by re-designing the compensator at each
candidate crossover (the Step 13 optimization sweep) — not transcribed. Figure 8
is rendered live.
"""
from __future__ import annotations
import io, math
from app.mode_b.doc_report_builder import (
    step_h, sub_h, body, eq_box, data_table, annotation, CW,
)
from app.mode_b.step16_step13_thd import compute_step13_thd

CH = 6

# design labels mapped to crossover (matches the reference §17.2)
_DESIGNS = [
    (17.0, "Baseline", "17 Hz", "Reference — balanced"),
    (12.0, "A — THD / rejection focus", "12 Hz", "Best THD, worst transient"),
    (20.0, "B — Balanced", "20 Hz", "Faster transient, rejection OK"),
    (25.0, "C — Transient focus", "25 Hz", "Fastest transient, THD risk"),
]


def _by_fcv(sweep, fcv):
    return next(s for s in sweep if abs(s["fcv"] - fcv) < 0.01)


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


def _fig_optimization(d):
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    sweep = d["sweep"]
    fig, (a1, a2, a3) = plt.subplots(1, 3, figsize=(7.4, 3.2))
    cols = {17.0: "#111", 12.0: "#1456b8", 20.0: "#1a9850", 25.0: "#c0392b"}
    for fcv, label, ftxt, _ in _DESIGNS:
        s = _by_fcv(sweep, fcv)
        c = cols[fcv]
        a1.semilogx(s["bode_f"], s["bode_g"], lw=1.0, color=c, label=f"{ftxt}")
        a2.plot([t*1e3 for t in s["tr_t"]], s["tr_dvhl"], lw=1.0, color=c)
    a1.axhline(0, color="0.5", lw=0.7); a1.set_xlim(1, 1000)
    a1.set_title("Open-loop $T_v$ (HL)", fontsize=8.5)
    a1.set_xlabel("Hz", fontsize=8); a1.set_ylabel("dB", fontsize=8)
    a1.grid(True, which="both", alpha=0.3); a1.legend(fontsize=5.5)
    a2.axhline(0, color="0.5", lw=0.6); a2.set_xlim(0, 350)
    a2.set_title("0→100% transient (HL)", fontsize=8.5)
    a2.set_xlabel("ms", fontsize=8); a2.set_ylabel("ΔV (V)", fontsize=8)
    a2.grid(True, alpha=0.3)
    x = range(len(_DESIGNS))
    a3.bar([i-0.2 for i in x], [_by_fcv(sweep, f)["rej_lo"] for f, *_ in _DESIGNS],
           width=0.4, color="#1456b8", label="LL")
    a3.bar([i+0.2 for i in x], [_by_fcv(sweep, f)["rej_hi"] for f, *_ in _DESIGNS],
           width=0.4, color="#c0392b", label="HL")
    a3.axhline(d["rej_min_db"], color="k", ls="--", lw=0.8)
    a3.annotate("20 dB", xy=(0, d["rej_min_db"]+0.4), fontsize=7)
    a3.set_xticks(list(x)); a3.set_xticklabels([t for _, _, t, _ in _DESIGNS], fontsize=7)
    a3.set_title("120 Hz rejection", fontsize=8.5); a3.set_ylabel("dB", fontsize=8)
    a3.legend(fontsize=6); a3.grid(True, axis="y", alpha=0.3)
    fig.suptitle("Figure 8 — Compensator optimization trade-off (power components fixed)", fontsize=9)
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    return _img_from_fig(fig)


def build_step14(story, data: dict):
    d = data
    sweep = d["sweep"]

    step_h(story, "14", "Loop Equation Accuracy and Compensator Optimization", CH)
    annotation(story, "INSIGHT",
        "With the power stage frozen, the only remaining design freedom is the compensator pole/zero "
        "placement. Every performance axis — transient dip, 120 Hz rejection / THD, phase margin — "
        "trades against the others through a single knob: the voltage-loop crossover. This step makes "
        "that trade-off explicit and quantifies four operating points along it.", CH)

    # ── 14.1 (was 17.2) ───────────────────────────────────────────────────────
    sub_h(story, "14.1", "Compensator Optimization — Transient vs 120 Hz Rejection / THD", CH)
    _co = d.get("cout_uF"); _l = d.get("lphi_uH")
    _co_s = f"{float(_co):.0f} µF" if _co else "2200 µF"
    _l_s = f"{float(_l):.0f} µH" if _l else "235 µH"
    body(story,
        f"The power components (C<sub>O</sub> = {_co_s}, L = {_l_s}) are fixed and cannot be changed; "
        "only the compensator pole/zero placement is free. Lowering the voltage-loop crossover "
        "improves 120 Hz rejection (lower THD) but enlarges and slows the load-transient response; "
        "raising it does the opposite. Four designs spanning this trade-off were evaluated by scaling "
        "the Type-III pole/zero pattern to different crossover frequencies and re-sizing the gain:", CH)
    rows1 = []
    for fcv, label, ftxt, _ in _DESIGNS:
        s = _by_fcv(sweep, fcv)
        rows1.append([label, ftxt, f"{s['pm_lo']:.0f}° / {s['pm_hi']:.0f}°",
                      f"{s['rej_lo']:.1f} / {s['rej_hi']:.1f} dB",
                      f"{s['dip_lo']:.1f} / {s['dip_hi']:.1f} V",
                      f"{s['trec_lo']:.0f} / {s['trec_hi']:.0f} ms"])
    data_table(story, "14.1", "Crossover Trade-off — Four Designs",
        "Each design is a full re-design at that crossover, recomputed from the model.",
        ["Design", "f_cv (HL)", "PM_v (LL / HL)", "120 Hz Rej (LL / HL)", "0→100% dip (LL / HL)",
         "Recovery (LL/HL)"],
        rows1, col_widths=[CW*0.22, CW*0.10, CW*0.16, CW*0.18, CW*0.18, CW*0.16], ch=CH)
    body(story,
        "The corresponding compensator values (R<sub>3</sub> ≈ 8.66 MΩ and C<sub>2</sub> ≈ 1.1 nF "
        "stay essentially fixed; only R<sub>2</sub>, C<sub>1</sub> and C<sub>3</sub> scale with "
        "crossover):", CH)
    rows2 = []
    for fcv, label, ftxt, effect in _DESIGNS:
        s = _by_fcv(sweep, fcv)
        tag = "Baseline (17 Hz)" if fcv == 17.0 else f"{label.split(' ')[0]} ({ftxt})"
        rows2.append([tag, f"{s['r2s']/1e3:.0f} kΩ", f"{s['c1s']*1e9:.0f} nF",
                      f"{s['c3s']*1e9:.0f} nF", effect])
    data_table(story, "14.2", "Compensator Values per Design",
        "Only R2, C1 and C3 change between designs.",
        ["Design", "R2", "C1", "C3", "Effect"],
        rows2, col_widths=[CW*0.20, CW*0.13, CW*0.13, CW*0.13, CW*0.41], ch=CH)

    # Figure 8
    body(story, "<b>Figure 8 — Compensator Optimization Trade-off (power components fixed)</b>", CH)
    body(story,
        "Open-loop gain, load-step transient (dip and overshoot) and 120 Hz rejection for the four "
        "designs at high line. Design A (12 Hz) maximises 120 Hz rejection but gives the largest, "
        "slowest transient; Design C (25 Hz) gives the fastest, smallest transient but its high-line "
        "rejection falls below the 20 dB minimum. Design B (20 Hz) and the Baseline (17 Hz) sit "
        "between.", CH)
    story.append(_fig_optimization(d))
    body(story, "<i>Figure 8 — Lowering f<sub>cv</sub> improves THD/120 Hz rejection but worsens the "
        "transient; raising it does the reverse. Design C drops below 20 dB rejection at high "
        "line.</i>", CH)
    sA = _by_fcv(sweep, 12.0); sB = _by_fcv(sweep, 20.0); sC = _by_fcv(sweep, 25.0)
    sBase = _by_fcv(sweep, 17.0)
    annotation(story, "NOTE",
        "Recommendation: the Baseline (17 Hz) is already well balanced — %.0f/%.1f dB rejection with "
        "a %.0f V worst-case dip. If THD is the priority, Design A (12 Hz) adds ~6 dB of 120 Hz "
        "rejection at the cost of a larger, slower transient. If transient response is the priority, "
        "Design B (20 Hz) cuts the dip and recovery by ~25%% while keeping rejection ≥ %.0f dB. "
        "Design C (25 Hz) is not recommended: its high-line 120 Hz rejection (%.1f dB) falls below "
        "the 20 dB minimum and would degrade THD. The current loop is left unchanged (crossover "
        "8.12 kHz, PM 62.8°); its phase margin can be raised slightly by increasing the compensator "
        "pole f<sub>p</sub> above 26 kHz if more current-loop margin is desired."
        % (sBase["rej_lo"], sBase["rej_hi"], abs(sBase["dip_hi"]), sB["rej_hi"], sC["rej_hi"]), CH)
    annotation(story, "DECISION",
        "Optimization — the baseline 17 Hz voltage loop is retained as the balanced choice. Design A "
        "(12 Hz) is the THD-optimal option and Design B (20 Hz) the transient-optimal option within "
        "the ≥20 dB rejection constraint; only the voltage compensator R2/C1/C3 change between them. "
        "Power components remain fixed.", CH)


def make_pdf(path: str, inp: dict | None = None):
    from reportlab.platypus import SimpleDocTemplate, PageBreak
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from app.mode_b.doc_report_builder import chapter_splash
    data = compute_step13_thd(inp)
    story = []
    chapter_splash(story, 6, "Control Scheme — Step 14 (Compensator Optimization, full detail)",
        "The voltage-loop crossover as the single trade-off knob — four candidate designs spanning "
        "transient stiffness vs 120 Hz rejection / THD, each re-designed and recomputed from the model.",
        ["14.1 compensator optimization — transient vs 120 Hz rejection / THD",
         "four designs (12 / 17 / 20 / 25 Hz)  ·  Figure 8 trade-off  ·  recommendation"])
    build_step14(story, data)
    while story and isinstance(story[0], PageBreak):
        story.pop(0)
    SimpleDocTemplate(path, pagesize=A4, leftMargin=20*mm, rightMargin=20*mm,
                      topMargin=18*mm, bottomMargin=18*mm,
                      title="Control Scheme — Step 14 (Compensator Optimization)").build(story)
    return path
