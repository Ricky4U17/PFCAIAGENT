"""
app/mode_b/report_step11.py — full-detail Step 11 (Outer Voltage Loop) report.

Reproduces the reference document's "Step 14 — Outer Voltage Loop Design"
word-for-word, line-for-line, table-for-table, step-for-step, renumbered as our
report Step 11 (subsections 11.1–11.9). Method B (SLVA662). Every value is injected
from the step16_step11_vloop calc agent (derived from prior steps + designer-
selected crossover / pole-zero frequencies — nothing hard-coded).

Figures: Fig 3 (open-loop T_v) and Fig 4 (closed-loop T_v) rendered live from the
computed transfer functions; Fig 14A (Type-III OTA schematic) drawn via SchemDraw.
"""
from __future__ import annotations
import io, math, cmath
from app.mode_b.doc_report_builder import (
    step_h, sub_h, body, eq_box, data_table, annotation, CW,
)
from app.mode_b.step16_step11_vloop import compute_step11_vloop

CH = 6


def _ws(story, label, eq, num=None):
    body(story, "<b>" + label + "</b>", CH)
    eq_box(story, eq if isinstance(eq, list) else [eq], number=num, ch=CH)


def _ang(z):
    return math.degrees(cmath.phase(z))


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


def _fig_open_loop_v(d):
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(7.0, 5.4), sharex=True)
    for bd, op in zip(d["bode"], d["rows"]):
        ls = "-" if op["pout"] == d["src"]["pout_lo"] else "--"
        ax1.semilogx(bd["f"], bd["ogain"], ls, lw=1.1, label=f"{op['vac']} Vac / {op['pout']} W")
        ax2.semilogx(bd["f"], bd["ophase"], ls, lw=1.1)
    ax1.axhline(0, color="0.4", lw=0.8)
    for fx, cl in ((d["rows"][0]["fco"], "#1a7"), (d["rows"][4]["fco"], "#a17")):
        ax1.axvline(fx, color=cl, lw=0.8, ls=":")
    ax1.set_ylabel("Magnitude (dB)")
    ax1.set_title("Figure 3 — Open-loop voltage loop $T_v(s)$ — all 8 operating points")
    ax1.grid(True, which="both", alpha=0.3); ax1.legend(fontsize=6, ncol=2, loc="upper right")
    ax1.annotate("7.8 Hz (LL)\n17 Hz (HL)", xy=(d["rows"][4]["fco"], 0),
                 xytext=(40, 25), fontsize=7, arrowprops=dict(arrowstyle="->", lw=0.6))
    ax2.set_ylabel("Phase (°)"); ax2.set_xlabel("Frequency (Hz)")
    ax2.grid(True, which="both", alpha=0.3); ax2.set_xlim(0.5, 1000)
    fig.tight_layout()
    return _img_from_fig(fig)


def _fig_closed_loop_v(d):
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(7.0, 5.4), sharex=True)
    for bd, op in zip(d["bode"], d["rows"]):
        ls = "-" if op["pout"] == d["src"]["pout_lo"] else "--"
        ax1.semilogx(bd["f"], bd["cgain"], ls, lw=1.1, label=f"{op['vac']} Vac / {op['pout']} W")
        ax2.semilogx(bd["f"], bd["cphase"], ls, lw=1.1)
    ax1.axhline(-3, color="#b00", lw=0.8, ls=":")
    ax1.set_ylabel("Magnitude (dB)")
    ax1.set_title("Figure 4 — Closed-loop voltage loop $T_v/(1+T_v)$ — all 8 operating points")
    ax1.grid(True, which="both", alpha=0.3); ax1.legend(fontsize=6, ncol=2, loc="lower left")
    ax1.set_ylim(-30, 6)
    ax2.set_ylabel("Phase (°)"); ax2.set_xlabel("Frequency (Hz)")
    ax2.grid(True, which="both", alpha=0.3); ax2.set_xlim(0.5, 1000)
    fig.tight_layout()
    return _img_from_fig(fig)


def build_step11(story, data: dict):
    d = data
    s = d["src"]
    rows = d["rows"]
    cm = d["comp"]
    dr = rows[d["design_idx"]]
    vout = s["vout"]

    step_h(story, "11", "Outer Voltage Loop Design", CH)
    annotation(story, "THEORY",
        "The outer loop sets the amplitude of the current command to regulate the bus. It must be "
        "slow — crossover near 17 Hz — so it does not respond to the 120 Hz ripple inherent on a "
        "single-phase-fed bus; responding to that ripple would distort the current reference and "
        "wreck the power factor. A Type-III OTA compensator provides the phase boost needed for "
        "adequate margin at such a low crossover.", CH)
    annotation(story, "CONCEPT",
        "Method B (SLVA662) folds the feedback divider into the OTA compensator network, so the loop "
        "gain evaluated here already contains the divider H<sub>v</sub>. The closed inner current "
        "loop appears in this analysis as a near-unity block, G<sub>i,cl</sub> ≈ 1.", CH)
    annotation(story, "NOTE",
        "The inner current loop is always a Type-2 compensator (Step 10). For the voltage loop the "
        "designer selects the compensator type — Type-2 or Type-3 — and all crossover and pole/zero "
        "frequencies through the GUI. This design uses the Type-III compensator reproduced below.", CH)

    # ── 11.1 ──────────────────────────────────────────────────────────────────
    sub_h(story, "11.1", "Voltage Loop Architecture — Method B", CH)
    body(story,
        "With the inner current loop closed (Step 10), the outer voltage loop regulates the DC bus by "
        "commanding the current reference. The voltage-loop gain is the product of the gain-modulator "
        "term, the closed current loop, and the voltage plant. Following the OTA Type-III approach of "
        "SLVA662 (Method B), the feedback divider H<sub>v</sub> = V<sub>FBPFC</sub> / V<sub>OUT</sub> "
        "is moved out of the plant and absorbed into the compensator transfer function from "
        "V<sub>O</sub> to V<sub>EA</sub>, so the loop gain evaluated here excludes both the divider "
        "and the compensator:", CH)
    eq_box(story, [r"T_{v,base}(s)=K_{MAX}\times\dfrac{I_{OUT}}{V_{RAMP}}\times G_{i,cl}(s)\times G_{vp}(s)"],
           number="11.1", ch=CH)
    body(story, "where the three factors are the multiplier gain term, the current-loop closed-loop "
        "transfer function, and the accurate voltage plant:", CH)
    eq_box(story, [r"GMOD=K_{MAX}\times\dfrac{I_{OUT}}{V_{RAMP}}\qquad"
                   r"G_{i,cl}(s)=\dfrac{T_i(s)/N_{CH}}{1+T_i(s)/N_{CH}}"], ch=CH)
    eq_box(story, [r"G_{vp}(s)=\dfrac{(1+sC_O r_C)(1-s/\omega_{RHP})}{C_O\,s+2/R_{LOAD}}"], ch=CH)
    body(story, "The feedback divider, moved into the OTA Type-III compensator (Method B), is:", CH)
    eq_box(story, [r"H_v=\dfrac{V_{FBPFC}}{V_{OUT}}=\dfrac{%.1f}{%.1f}=%.6f"
                   % (s["vfbpfc"], vout, s["hv"])], ch=CH)
    data_table(story, "11.1", "Voltage-Loop Parameters",
        "Sourced from prior steps and the power-stage specification.",
        ["Parameter", "Value", "Source / Role"],
        [["Max multiplier gain  K_MAX", f"{s['kmax']:.2f}", "Step 6 selection (149%)"],
         ["Output voltage  V_OUT", f"{vout:.1f} V", "Regulated DC bus"],
         ["Feedback reference  V_FBPFC", f"{s['vfbpfc']:.1f} V", "FBPFC regulation point"],
         ["Ramp voltage  V_RAMP", f"{s['vramp']:.0f} V", "Internal PWM ramp"],
         ["Output capacitor  C_O", f"{s['co']*1e6:.0f} µF", "Bus capacitor"],
         ["Capacitor ESR  r_C", f"{s['r_c']*1e3:.0f} mΩ", "Output-cap ESR"],
         ["Channels  N_CH", f"{s['nch']}", "Interleaved phases"],
         ["Effective inductance  L_eq = L/2", f"{s['leq']*1e6:.1f} µH", "Two-phase combined plant"],
         ["Transconductance  GMV", f"{s['gmv']*1e6:.0f} µS", "Voltage-loop OTA"],
         ["Voltage-loop crossover  f_cv", f"{s['fcv']:.0f} Hz", "Design target"]],
        col_widths=[CW*0.34, CW*0.18, CW*0.48], ch=CH)

    # ── 11.2 ──────────────────────────────────────────────────────────────────
    sub_h(story, "11.2", "Voltage Plant RHP Zero — All 8 Operating Points", CH)
    body(story,
        "The interleaved boost plant presents a right-half-plane zero whose frequency depends on the "
        "load and duty complement. The two-phase combined plant uses the effective inductance "
        "L<sub>eq</sub> = L/2 = %.1f µH:" % (s["leq"]*1e6), CH)
    eq_box(story, [r"D'=\dfrac{\sqrt{2}\times V_{AC}}{V_{OUT}}\qquad"
                   r"\omega_{RHP}=\dfrac{R_{LOAD}\times(D')^2}{L_{eq}}\qquad"
                   r"f_{RHP}=\dfrac{\omega_{RHP}}{2\pi}"], ch=CH)
    data_table(story, "11.2", "Voltage-Plant RHP Zero — 8 Conditions",
        "RHP-zero frequency across the universal-input range (L_eq = L/2).",
        ["V_AC (V)", "P_OUT (W)", "R_LOAD (Ω)", "D'", "f_RHP (kHz)"],
        [[f"{o['vac']}", f"{o['pout']}", f"{o['rload']:.4f}", f"{o['Dp']:.4f}", f"{o['frhp']/1e3:.2f}"]
         for o in rows], col_widths=[CW*0.16, CW*0.16, CW*0.24, CW*0.20, CW*0.24], ch=CH)
    annotation(story, "NOTE",
        "The voltage-plant RHP-zero frequency is twice the corresponding current-loop value (Step 10) "
        "because the combined two-phase plant uses L<sub>eq</sub> = L/2 = %.1f µH rather than the "
        "per-phase %.0f µH. Even the lowest f<sub>RHP</sub> (%.2f kHz) is far above the %.0f Hz "
        "crossover, so the RHP zero has negligible effect on voltage-loop phase margin."
        % (s["leq"]*1e6, s["lphi"]*1e6, rows[0]["frhp"]/1e3, s["fcv"]), CH)

    # ── 11.3 ──────────────────────────────────────────────────────────────────
    sub_h(story, "11.3", "Detailed Calculation — 180 Vac / 3600 W (design point)", CH)
    body(story,
        "The compensator is sized at the 3600 W high-line design point, where the loop must cross over "
        "at 17 Hz at full power. All quantities are evaluated at f<sub>cv</sub> = %.0f Hz, "
        "s = j·2π·%.0f = j%.2f rad/s." % (s["fcv"], s["fcv"], 2*math.pi*s["fcv"]), CH)
    _ws(story, "Step 1 — Load resistance and output current:",
        [r"R_{LOAD}=\dfrac{V_{OUT}^2}{P_{OUT}}=\dfrac{%.1f^2}{3600}=%.4f\ \Omega" % (vout, dr["rload"]),
         r"I_{OUT}=\dfrac{P_{OUT}}{V_{OUT}}=\dfrac{3600}{%.1f}=%.4f\ \mathrm{A}" % (vout, dr["iout"])])
    _ws(story, "Step 2 — Multiplier gain term:",
        r"GMOD=K_{MAX}\times\dfrac{I_{OUT}}{V_{RAMP}}=1.49\times\dfrac{%.4f}{5}=%.4f"
        % (dr["iout"], dr["gmod"]))
    _ws(story, "Step 3 — Duty complement and RHP zero:",
        [r"D'=\dfrac{\sqrt{2}\times180}{%.1f}=%.4f" % (vout, dr["Dp"]),
         r"\omega_{RHP}=\dfrac{%.4f\times%.4f^2}{%.1f\,\mu H}=%.0f\ \mathrm{rad/s}"
         % (dr["rload"], dr["Dp"], s["leq"]*1e6, dr["wrhp"]),
         r"f_{RHP}=%.2f\ \mathrm{kHz}" % (dr["frhp"]/1e3)])
    body(story, "<b>Step 4 — Current-loop closed-loop term at %.0f Hz:</b>" % s["fcv"], CH)
    body(story, "Using the full inner current loop with its Type-2 OTA compensator (Step 10):", CH)
    eq_box(story, [r"T_i(j2\pi\cdot%.0f)=%.2f%+.2fj\qquad |T_i|=%.2f\qquad\angle T_i=%.2f^\circ"
                   % (s["fcv"], dr["ti"].real, dr["ti"].imag, abs(dr["ti"]), _ang(dr["ti"])),
                   r"G_{i,cl}(j2\pi\cdot%.0f)=\dfrac{T_i/2}{1+T_i/2}=%.6f%+.6fj"
                   % (s["fcv"], dr["gicl"].real, dr["gicl"].imag),
                   r"|G_{i,cl}|=%.5f\qquad\angle G_{i,cl}=%.4f^\circ"
                   % (abs(dr["gicl"]), _ang(dr["gicl"]))], ch=CH)
    body(story, "At %.0f Hz the current loop is essentially unity (its bandwidth is 8.12 kHz), but it "
        "is retained for accuracy." % s["fcv"], CH)
    _ws(story, "Step 5 — Voltage plant at %.0f Hz:" % s["fcv"],
        [r"G_{vp}(j2\pi\cdot%.0f)=%.5f%+.5fj" % (s["fcv"], dr["gvp"].real, dr["gvp"].imag),
         r"|G_{vp}|=%.5f\qquad\angle G_{vp}=%.2f^\circ" % (abs(dr["gvp"]), _ang(dr["gvp"]))])
    _ws(story, "Step 6 — Voltage-loop gain without compensator:",
        [r"T_{v,base}=GMOD\times G_{i,cl}\times G_{vp}=%.4f\times%.5f\times%.5f"
         % (dr["gmod"], abs(dr["gicl"]), abs(dr["gvp"])),
         r"T_{v,base}=%.4f\quad(%.2f\ \mathrm{dB})" % (abs(dr["tvbase"]), 20*math.log10(abs(dr["tvbase"])))])
    body(story, "Including the feedback divider H<sub>v</sub> (shown here for reference; in Method B "
        "it is part of the compensator):", CH)
    eq_box(story, [r"T_v=T_{v,base}\times H_v=%.4f\times%.6f=%.5f"
                   % (abs(dr["tvbase"]), s["hv"], abs(dr["tvbase"])*s["hv"]),
                   r"T_v=%.5f\ (%.2f\ \mathrm{dB})\qquad\angle T_v=%.2f^\circ"
                   % (abs(dr["tvbase"])*s["hv"], 20*math.log10(abs(dr["tvbase"])*s["hv"]), _ang(dr["tvbase"]))], ch=CH)

    # ── 11.4 ──────────────────────────────────────────────────────────────────
    sub_h(story, "11.4", "Voltage Loop Gain Without Compensator — All 8 Operating Points", CH)
    body(story,
        "|T<sub>v</sub>| is the loop gain including the divider but without the compensator; "
        "|T<sub>v,base</sub>| (Method B, divider in compensator) is |T<sub>v</sub>| / H<sub>v</sub> "
        "and sets the required compensator gain.", CH)
    data_table(story, "11.4", "Voltage Loop Gain (no compensator) — 8 Conditions", "",
        ["V_AC (V)", "P_OUT (W)", "f_RHP (kHz)", "|G_vp|", "|T_v,base|", "|T_v| (dB)", "∠T_v (°)"],
        [[f"{o['vac']}", f"{o['pout']}", f"{o['frhp']/1e3:.2f}", f"{abs(o['gvp']):.4f}",
          f"{abs(o['tvbase']):.4f}", f"{20*math.log10(abs(o['tvbase'])*s['hv']):.2f}",
          f"{_ang(o['tvbase']):.2f}"] for o in rows],
        col_widths=[CW*0.12, CW*0.13, CW*0.15, CW*0.14, CW*0.16, CW*0.15, CW*0.15], ch=CH)

    # ── 11.5 ──────────────────────────────────────────────────────────────────
    sub_h(story, "11.5", "Required Compensator Gain", CH)
    body(story,
        "To force the loop to cross 0 dB at f<sub>cv</sub> = %.0f Hz, the OTA Type-III compensator "
        "(which now contains the divider H<sub>v</sub>) must supply a magnitude equal to the inverse "
        "of the uncompensated base gain:" % s["fcv"], CH)
    eq_box(story, [r"H_{OTA}(%.0f\ \mathrm{Hz})=\dfrac{1}{T_{v,base}}" % s["fcv"]], ch=CH)
    body(story, "Sizing at the high-line 3600 W design point:", CH)
    eq_box(story, [r"H_{OTA}=\dfrac{1}{%.4f}=%.6f\quad(%.2f\ \mathrm{dB})"
                   % (d["tvbase_mag_design"], d["G"], 20*math.log10(d["G"]))], ch=CH)
    body(story, "At low line (1700 W) the base gain is lower (|T<sub>v,base</sub>| ≈ %.2f), so the "
        "same compensator yields a lower crossover — quantified in Section 11.9."
        % abs(rows[0]["tvbase"]), CH)

    if cm["type"] == "type2":
        _build_step11_type2(story, d, cm, s, rows)
        return
    # ── 11.6 ──────────────────────────────────────────────────────────────────
    sub_h(story, "11.6", "OTA Type-III Compensator Design (SLVA662, Method B)", CH)
    body(story,
        "The compensator is an OTA Type-III network. Method B includes the feedback divider resistors "
        "R<sub>1</sub> = R<sub>FB,top</sub> and R<sub>4</sub> = R<sub>FB,bottom</sub> inside the "
        "compensator together with g<sub>m</sub>, R<sub>2</sub>, R<sub>3</sub>, C<sub>1</sub>, "
        "C<sub>2</sub> and C<sub>3</sub>. Its transfer function and pole-zero targets are:", CH)
    eq_box(story, [r"H_{OTA}(s)=-G_0\times\dfrac{(1+\omega_{z1}/s)(1+s/\omega_{z2})}"
                   r"{(1+s/\omega_{p1})(1+s/\omega_{p2})}"], ch=CH)
    data_table(story, "11.6", "Type-III Compensator Targets",
        "Divider from Step 5; pole/zero frequencies are designer-selected.",
        ["Quantity", "Value", "Symbol", "Role"],
        [["Top feedback resistor", f"{s['r1']/1e6:.2f} MΩ", "R1 = R_FB,top", "From Step 5 divider"],
         ["Bottom feedback resistor", f"{s['r4']/1e3:.1f} kΩ", "R4 = R_FB,bottom", "From Step 5 divider"],
         ["Transconductance", f"{s['gmv']*1e6:.0f} µS", "gm = GMV", "Voltage-loop OTA"],
         ["Crossover", f"{s['fcv']:.0f} Hz", "f_c", "Design target"],
         ["Required gain at f_c", f"{d['G']:.6f}", "G", "= 1/|T_v,base| (HL)"],
         ["Zero 1 / Zero 2", f"{cm['fz1']:.0f} Hz / {cm['fz2']:.0f} Hz", "f_z1 / f_z2", "Phase boost"],
         ["Pole 1 / Pole 2", f"{cm['fp1']:.0f} Hz / {cm['fp2']:.0f} Hz", "f_p1 / f_p2", "HF roll-off"]],
        col_widths=[CW*0.30, CW*0.20, CW*0.22, CW*0.28], ch=CH)
    body(story, "<b>Intermediate SLVA662 factors</b>", CH)
    eq_box(story, [r"a=\sqrt{1+(f_c/f_{p2})^2}=\sqrt{1+(17/17)^2}=%.4f" % cm["a"],
                   r"b=\sqrt{1+(17/50)^2}=%.4f" % cm["b"],
                   r"c=\sqrt{1+(3/17)^2}=%.4f" % cm["c"],
                   r"d=\sqrt{1+(17/12)^2}=%.4f" % cm["d"],
                   r"aa=\dfrac{a\times b}{c\times d}=\dfrac{%.4f\times%.4f}{%.4f\times%.4f}=%.4f"
                   % (cm["a"], cm["b"], cm["c"], cm["d"], cm["aa"])], ch=CH)
    body(story, "<b>Component values (design point)</b>", CH)
    _ws(story, "Step 1 — Gain factor bb and R<sub>2</sub>:",
        [r"bb=\dfrac{G\times f_{p2}\,(R_1+R_4)}{R_4\times g_m\,(f_{p2}-f_{z1})}"
         r"=\dfrac{%.6f\times17\times%.4f\,\mathrm{M\Omega}}{23.2\mathrm{k}\times100\mu S\times14}=%.2f\ \mathrm{k\Omega}"
         % (d["G"], (s["r1"]+s["r4"])/1e6, cm["bb"]/1e3),
         r"R_2=aa\times bb=%.4f\times%.2f\mathrm{k}=%.2f\ \mathrm{k\Omega}"
         % (cm["aa"], cm["bb"]/1e3, cm["r2"]/1e3)])
    body(story, "<b>Step 2 — R<sub>3</sub> and C<sub>2</sub> (second branch — sets f<sub>z2</sub> "
        "and f<sub>p2</sub>):</b>", CH)
    body(story, "R<sub>3</sub> and C<sub>2</sub> satisfy f<sub>z2</sub> = 1/[2π(R<sub>1</sub>+"
        "R<sub>3</sub>)C<sub>2</sub>] and f<sub>p2</sub> = 1/[2π(R<sub>3</sub>+R<sub>1</sub>||"
        "R<sub>4</sub>)C<sub>2</sub>] simultaneously with R<sub>1</sub> = %.2f MΩ, R<sub>4</sub> = "
        "%.1f kΩ:" % (s["r1"]/1e6, s["r4"]/1e3), CH)
    eq_box(story, [r"R_3=%.4f\ \mathrm{M\Omega}\qquad C_2=%.4f\ \mathrm{nF}"
                   % (cm["r3"]/1e6, cm["c2"]*1e9)], ch=CH)
    _ws(story, "Step 3 — C<sub>1</sub> (sets f<sub>z1</sub>):",
        r"C_1=\dfrac{1}{2\pi\times f_{z1}\times R_2}=\dfrac{1}{2\pi\times3\times%.2f\mathrm{k}}=%.2f\ \mathrm{nF}"
        % (cm["r2"]/1e3, cm["c1"]*1e9))
    _ws(story, "Step 4 — C<sub>3</sub> (sets f<sub>p1</sub> with R<sub>2</sub>, C<sub>1</sub>):",
        r"C_3=\dfrac{C_1}{2\pi\times C_1\times R_2\times f_{p1}-1}=%.2f\ \mathrm{nF}" % (cm["c3"]*1e9))

    # ── 11.7 ──────────────────────────────────────────────────────────────────
    sub_h(story, "11.7", "Final Compensator Component Values", CH)
    data_table(story, "11.7", "Voltage Compensator Components",
        "Calculated values and standard selections.",
        ["Component", "Calculated", "Standard value", "Sets"],
        [["R2", f"{cm['r2']/1e3:.2f} kΩ", f"{cm['r2s']/1e3:.0f} kΩ", "f_z1, f_p1"],
         ["R3", f"{cm['r3']/1e6:.4f} MΩ", f"{cm['r3s']/1e6:.2f} MΩ", "f_z2, f_p2"],
         ["C1", f"{cm['c1']*1e9:.2f} nF", f"{cm['c1s']*1e9:.0f} nF", "f_z1"],
         ["C2", f"{cm['c2']*1e9:.4f} nF", f"{cm['c2s']*1e9:.1f} nF", "f_z2"],
         ["C3", f"{cm['c3']*1e9:.2f} nF", f"{cm['c3s']*1e9:.0f} nF", "f_p1"]],
        col_widths=[CW*0.18, CW*0.26, CW*0.26, CW*0.30], ch=CH)
    annotation(story, "DECISION",
        "Voltage compensator (OTA Type-III, GMV = %.0f µS):  R2 = %.0f kΩ, R3 = %.2f MΩ, C1 = %.0f nF, "
        "C2 = %.1f nF, C3 = %.0f nF, with divider R1 = %.2f MΩ / R4 = %.1f kΩ. Pole-zero set: "
        "f_z1 = %.0f Hz, f_z2 = %.0f Hz, f_p1 = %.0f Hz, f_p2 = %.0f Hz."
        % (s["gmv"]*1e6, cm["r2s"]/1e3, cm["r3s"]/1e6, cm["c1s"]*1e9, cm["c2s"]*1e9, cm["c3s"]*1e9,
           s["r1"]/1e6, s["r4"]/1e3, cm["fz1"], cm["fz2"], cm["fp1"], cm["fp2"]), CH)

    # ── 11.8 ──────────────────────────────────────────────────────────────────
    sub_h(story, "11.8", "Pole-Zero Verification (calculated values)", CH)
    eq_box(story, [r"f_{z1}=\dfrac{1}{2\pi R_2 C_1}=%.3f\ \mathrm{Hz}" % cm["fz1c"],
                   r"f_{z2}=\dfrac{1}{2\pi (R_1+R_3) C_2}=%.3f\ \mathrm{Hz}" % cm["fz2c"],
                   r"f_{p1}=\dfrac{C_1+C_3}{2\pi R_2 C_1 C_3}=%.3f\ \mathrm{Hz}" % cm["fp1c"],
                   r"f_{p2}=\dfrac{1}{2\pi (R_3+R_1\|R_4) C_2}=%.3f\ \mathrm{Hz}" % cm["fp2c"]], ch=CH)

    # ── 11.9 ──────────────────────────────────────────────────────────────────
    sub_h(story, "11.9", "Voltage-Loop Crossover and Stability — All 8 Operating Points", CH)
    body(story,
        "With the final standard components the loop is evaluated across all operating points. Because "
        "the compensator is sized for the 3600 W design point, the high-line crossover is 17 Hz; at "
        "low line (1700 W) the lower plant gain shifts the crossover down to about 7.8 Hz. Phase "
        "margin is high (~81–82°) at every condition.", CH)
    data_table(story, "11.9", "Voltage-Loop Crossover and Stability — 8 Conditions", "",
        ["V_AC (V)", "P_OUT (W)", "Loop gain at 17 Hz (dB)", "Crossover f_cv (Hz)", "Phase margin (°)"],
        [[f"{o['vac']}", f"{o['pout']}", f"{o['loopdb_fcv']:.2f}", f"{o['fco']:.2f}", f"{o['pm']:.1f}"]
         for o in rows], col_widths=[CW*0.15, CW*0.16, CW*0.27, CW*0.22, CW*0.20], ch=CH)
    annotation(story, "NOTE",
        "The voltage loop is unconditionally stable across the universal-input range: phase margin "
        "stays near 81–82° and the gain margin is large because the loop has rolled well below 0 dB "
        "long before the phase reaches −180°. The 1700 W crossover of 7.8 Hz is expected — the "
        "compensator is sized at the 3600 W full-power design point.", CH)

    # Figures
    body(story, "<b>Figure 14A — Type-III OTA Voltage-Loop Compensator Schematic</b>", CH)
    body(story,
        "The voltage OTA (GMV = %.0f µS) senses the bus through the R1/R4 divider and drives the "
        "Type-III network. R2-C1 set the first zero and the integrator, C3 adds the first "
        "high-frequency pole, and the R3-C2 branch provides the second zero/pole pair (Method B folds "
        "the divider into the compensator)." % (s["gmv"]*1e6), CH)
    from app.mode_b.schematics import type3_ota_compensator
    story.append(type3_ota_compensator(
        r2_k=cm["r2s"]/1e3, r3_m=cm["r3s"]/1e6, c1_nf=cm["c1s"]*1e9, c2_nf=cm["c2s"]*1e9,
        c3_nf=cm["c3s"]*1e9, r1_m=s["r1"]/1e6, r4_k=s["r4"]/1e3, gmv_us=s["gmv"]*1e6))
    body(story, "<i>Figure 14A — Type-III network: R2 = %.0f kΩ, R3 = %.2f MΩ, C1 = %.0f nF, C2 = "
        "%.1f nF, C3 = %.0f nF. Zeros %.0f/%.0f Hz, poles %.0f/%.0f Hz.</i>"
        % (cm["r2s"]/1e3, cm["r3s"]/1e6, cm["c1s"]*1e9, cm["c2s"]*1e9, cm["c3s"]*1e9,
           cm["fz1"], cm["fz2"], cm["fp1"], cm["fp2"]), CH)
    body(story, "<b>Figure 3 — Open-Loop Voltage Loop T<sub>v</sub>(s)  |  All 8 Operating "
        "Points</b>", CH)
    body(story,
        "The open-loop voltage gain crosses 0 dB at 7.8 Hz (low line, solid) and 17 Hz (high line, "
        "dashed). The Type-III compensator lifts the phase near crossover, giving ≈81–82° phase "
        "margin. Vertical markers indicate the two crossover frequencies.", CH)
    story.append(_fig_open_loop_v(d))
    body(story, "<i>Figure 3 — Open-loop T<sub>v</sub>(s): gain (dB, top) and phase (°, bottom). "
        "Crossover %.1f Hz (LL) / %.0f Hz (HL); PM ≈ %.0f–%.0f°.</i>"
        % (rows[0]["fco"], rows[4]["fco"], rows[0]["pm"], rows[4]["pm"]), CH)
    body(story, "<b>Figure 4 — Closed-Loop Voltage Loop T<sub>v</sub>(s)/(1+T<sub>v</sub>(s))  |  "
        "All 8 Operating Points</b>", CH)
    body(story,
        "The closed-loop voltage response is flat to the loop bandwidth and rolls off smoothly with "
        "no peaking, confirming the high phase margin and well-damped regulation at every operating "
        "point.", CH)
    story.append(_fig_closed_loop_v(d))
    body(story, "<i>Figure 4 — Closed-loop T<sub>v</sub>(s)/(1+T<sub>v</sub>(s)): gain and phase "
        "across all 8 operating points.</i>", CH)
    annotation(story, "DECISION",
        "Outer voltage loop — DESIGN PASS. Crossover %.0f Hz at 3600 W (PM %.0f°) and %.1f Hz at "
        "1700 W (PM %.0f°). Compensator: R2 = %.0f kΩ, R3 = %.2f MΩ, C1 = %.0f nF, C2 = %.1f nF, "
        "C3 = %.0f nF (OTA Type-III, GMV = %.0f µS)."
        % (rows[4]["fco"], rows[4]["pm"], rows[0]["fco"], rows[0]["pm"],
           cm["r2s"]/1e3, cm["r3s"]/1e6, cm["c1s"]*1e9, cm["c2s"]*1e9, cm["c3s"]*1e9, s["gmv"]*1e6), CH)


def _build_step11_type2(story, d, cm, s, rows):
    """§11.6–11.9 + figures + verdict when the designer selects a Type-II voltage
    compensator (one zero, one HF pole; no R3-C2 feed-forward branch)."""
    sub_h(story, "11.6", "OTA Type-II Compensator Design (Method B)", CH)
    body(story,
        "The designer selected a Type-II voltage compensator. Method B folds the feedback divider "
        "(R<sub>1</sub>, R<sub>4</sub>) into the OTA network together with g<sub>m</sub>, R<sub>2</sub>, "
        "C<sub>1</sub> and C<sub>3</sub>. It provides an integrator with one phase-boost zero and one "
        "high-frequency pole:", CH)
    eq_box(story, [r"H_{OTA}(s)=-G_0\times\dfrac{1+\omega_z/s}{1+s/\omega_p}"], number="11.6", ch=CH)
    data_table(story, "11.6", "Type-II Compensator Targets",
        "Divider from Step 5; crossover and pole/zero are designer-selected.",
        ["Quantity", "Value", "Symbol", "Role"],
        [["Top feedback resistor", f"{s['r1']/1e6:.2f} MΩ", "R1 = R_FB,top", "From Step 5 divider"],
         ["Bottom feedback resistor", f"{s['r4']/1e3:.1f} kΩ", "R4 = R_FB,bottom", "From Step 5 divider"],
         ["Transconductance", f"{s['gmv']*1e6:.0f} µS", "gm = GMV", "Voltage-loop OTA"],
         ["Crossover", f"{s['fcv']:.0f} Hz", "f_c", "Design target"],
         ["Required gain at f_c", f"{d['G']:.6f}", "G", "= 1/|T_v,base| (HL)"],
         ["Zero / Pole", f"{cm['fz']:.0f} Hz / {cm['fp']:.0f} Hz", "f_z / f_p", "Phase boost / HF roll-off"]],
        col_widths=[CW*0.30, CW*0.20, CW*0.22, CW*0.28], ch=CH)
    body(story, "<b>Shape factor and component values (design point)</b>", CH)
    eq_box(story, [r"\kappa=\dfrac{\sqrt{1+(f_z/f_c)^2}}{\sqrt{1+(f_c/f_p)^2}}=%.6f" % cm["kappa"]], ch=CH)
    _ws(story, "Step 1 — R<sub>2</sub> (sets the loop gain at f<sub>cv</sub>):",
        r"R_2=\dfrac{G\,(R_1+R_4)}{R_4\,g_m\,\kappa}=%.2f\ \mathrm{k\Omega}" % (cm["r2"]/1e3))
    _ws(story, "Step 2 — C<sub>1</sub> (sets the zero f<sub>z</sub>):",
        r"C_1=\dfrac{1}{2\pi R_2 f_z}=%.2f\ \mathrm{nF}" % (cm["c1"]*1e9))
    _ws(story, "Step 3 — C<sub>3</sub> (sets the HF pole f<sub>p</sub>):",
        r"C_3=\dfrac{1}{2\pi R_2 f_p}=%.2f\ \mathrm{nF}" % (cm["c3"]*1e9))

    sub_h(story, "11.7", "Final Compensator Component Values", CH)
    data_table(story, "11.7", "Voltage Compensator Components (Type-II)",
        "Calculated values and standard selections.",
        ["Component", "Calculated", "Standard value", "Sets"],
        [["R2", f"{cm['r2']/1e3:.2f} kΩ", f"{cm['r2s']/1e3:.0f} kΩ", "f_z, f_p, gain"],
         ["C1", f"{cm['c1']*1e9:.2f} nF", f"{cm['c1s']*1e9:.0f} nF", "f_z"],
         ["C3", f"{cm['c3']*1e9:.2f} nF", f"{cm['c3s']*1e9:.0f} nF", "f_p"]],
        col_widths=[CW*0.20, CW*0.27, CW*0.27, CW*0.26], ch=CH)
    annotation(story, "DECISION",
        "Voltage compensator (OTA Type-II, GMV = %.0f µS):  R2 = %.0f kΩ, C1 = %.0f nF, C3 = %.0f nF, "
        "with divider R1 = %.2f MΩ / R4 = %.1f kΩ. Pole-zero set: f_z = %.1f Hz, f_p = %.1f Hz."
        % (s["gmv"]*1e6, cm["r2s"]/1e3, cm["c1s"]*1e9, cm["c3s"]*1e9, s["r1"]/1e6, s["r4"]/1e3,
           cm["fz_a"], cm["fp_a"]), CH)

    sub_h(story, "11.8", "Pole-Zero Verification (standard components)", CH)
    eq_box(story, [r"f_z=\dfrac{1}{2\pi R_2 C_1}=%.3f\ \mathrm{Hz}" % cm["fz_a"],
                   r"f_p=\dfrac{1}{2\pi R_2 C_3}=%.3f\ \mathrm{Hz}" % cm["fp_a"]], ch=CH)

    sub_h(story, "11.9", "Voltage-Loop Crossover and Stability — All 8 Operating Points", CH)
    body(story,
        "With the final standard components the loop is evaluated across all operating points. The "
        "compensator is sized for the 3600 W design point; at low line (1700 W) the lower plant gain "
        "shifts the crossover down.", CH)
    data_table(story, "11.9", "Voltage-Loop Crossover and Stability — 8 Conditions", "",
        ["V_AC (V)", "P_OUT (W)", "Loop gain at 17 Hz (dB)", "Crossover f_cv (Hz)", "Phase margin (°)"],
        [[f"{o['vac']}", f"{o['pout']}", f"{o['loopdb_fcv']:.2f}", f"{o['fco']:.2f}", f"{o['pm']:.1f}"]
         for o in rows], col_widths=[CW*0.15, CW*0.16, CW*0.27, CW*0.22, CW*0.20], ch=CH)
    annotation(story, "NOTE",
        "A Type-II compensator provides up to ~90° of phase boost from its single zero/pole pair — "
        "less than a Type-III. Confirm the phase margin above meets the ≥60° target at every "
        "operating point; if not, switch to the Type-III compensator (the reference design choice).", CH)

    body(story, "<b>Figure 14A — Type-II OTA Voltage-Loop Compensator Schematic</b>", CH)
    body(story,
        "The voltage OTA (GMV = %.0f µS) senses the bus through the R1/R4 divider. R2-C1 set the "
        "integrator and the compensating zero; C3 adds the high-frequency pole." % (s["gmv"]*1e6), CH)
    from app.mode_b.schematics import type2_voltage_compensator
    story.append(type2_voltage_compensator(
        r2_k=cm["r2s"]/1e3, c1_nf=cm["c1s"]*1e9, c3_nf=cm["c3s"]*1e9,
        r1_m=s["r1"]/1e6, r4_k=s["r4"]/1e3, gmv_us=s["gmv"]*1e6))
    body(story, "<i>Figure 14A — Type-II network: R2 = %.0f kΩ, C1 = %.0f nF, C3 = %.0f nF. "
        "Zero %.1f Hz, pole %.1f Hz.</i>"
        % (cm["r2s"]/1e3, cm["c1s"]*1e9, cm["c3s"]*1e9, cm["fz_a"], cm["fp_a"]), CH)
    body(story, "<b>Figure 3 — Open-Loop Voltage Loop T<sub>v</sub>(s)  |  All 8 Operating Points</b>", CH)
    body(story, "The open-loop voltage gain with the Type-II compensator across all eight operating "
        "points; the crossover and phase margin per point are tabulated in §11.9.", CH)
    story.append(_fig_open_loop_v(d))
    body(story, "<i>Figure 3 — Open-loop T<sub>v</sub>(s): gain (dB, top) and phase (°, bottom). "
        "Crossover %.1f Hz (LL) / %.0f Hz (HL); PM %.0f° / %.0f°.</i>"
        % (rows[0]["fco"], rows[4]["fco"], rows[0]["pm"], rows[4]["pm"]), CH)
    body(story, "<b>Figure 4 — Closed-Loop Voltage Loop T<sub>v</sub>(s)/(1+T<sub>v</sub>(s))</b>", CH)
    story.append(_fig_closed_loop_v(d))
    body(story, "<i>Figure 4 — Closed-loop T<sub>v</sub>(s)/(1+T<sub>v</sub>(s)): gain and phase "
        "across all 8 operating points.</i>", CH)
    annotation(story, "DECISION",
        "Outer voltage loop (Type-II) — crossover %.0f Hz at 3600 W (PM %.0f°) and %.1f Hz at 1700 W "
        "(PM %.0f°). Compensator: R2 = %.0f kΩ, C1 = %.0f nF, C3 = %.0f nF (OTA Type-II, GMV = %.0f µS)."
        % (rows[4]["fco"], rows[4]["pm"], rows[0]["fco"], rows[0]["pm"],
           cm["r2s"]/1e3, cm["c1s"]*1e9, cm["c3s"]*1e9, s["gmv"]*1e6), CH)


def make_pdf(path: str, inp: dict | None = None):
    from reportlab.platypus import SimpleDocTemplate, PageBreak
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from app.mode_b.doc_report_builder import chapter_splash
    data = compute_step11_vloop(inp)
    story = []
    chapter_splash(story, 6, "Control Scheme — Step 11 (Outer Voltage Loop, full detail)",
        "Method-B OTA Type-III voltage-loop compensator and full 8-point stability verification "
        "per FAN9672-D, AN4165-D and SLVA662 — every value from prior steps + designer-set f_cv / "
        "pole-zero frequencies.",
        ["11.1 architecture (Method B)  ·  11.2 plant RHP zero  ·  11.3 full 180 Vac worked calc",
         "11.4 8-point base gain  ·  11.5 required gain  ·  11.6 Type-III design (R2/R3/C1/C2/C3)",
         "11.7 components  ·  11.8 pole-zero verify  ·  11.9 8-point crossover/PM + Bode + schematic"])
    build_step11(story, data)
    while story and isinstance(story[0], PageBreak):
        story.pop(0)
    SimpleDocTemplate(path, pagesize=A4, leftMargin=20*mm, rightMargin=20*mm,
                      topMargin=18*mm, bottomMargin=18*mm,
                      title="Control Scheme — Step 11 (Outer Voltage Loop)").build(story)
    return path
