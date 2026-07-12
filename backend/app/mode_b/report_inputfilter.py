"""
Chapter 10 — Input EMI Filter (Conducted Emissions)
===================================================
Built from the SAME engine + adapter the GUI uses (`inputfilter.adapter`), so the documented filter
is identical to the selection page. The conducted-emission filter (differential-mode choke + X-cap,
common-mode choke + Y-caps, plus a damping leg) is synthesized to meet a chosen compliance profile
(CISPR 11/32, FCC §15.107) within a chosen safety earth-leakage limit, with a user margin.

Standalone document (like the Chapter-7/8/9 reports), merged after Chapter 9.
"""
from __future__ import annotations
import io

from app.mode_b.doc_report_builder import (
    chapter_splash, step_h, body, eq_box, data_table, annotation, CW,
)
from app.mode_b.inputfilter.adapter import calculate_emi
from app.mode_b.inputfilter import emi_filter_design as emi

_MU = "&#181;"; _DEG = "&#176;"; _OHM = "&#937;"
CH = 10


def _f(x, n=2):
    try:
        return f"{float(x):.{n}f}"
    except Exception:
        return "&#8212;"


def build_inputfilter_story(story, design, cap=None, protection=None, ntc=None, opts=None):
    out = calculate_emi(design, cap or {}, protection or {}, ntc or {}, opts or {})
    r = out["result"]; b = out["basis"]
    klass = r["conducted_class"]; det = r["detector"]; margin = r["margin_db"]
    prof_label = emi.COMPLIANCE_PROFILE.get(int((opts or {}).get("compliance_profile", 5)), (None, None, None, "—"))[3]

    chapter_splash(story, CH, "Input EMI Filter — Conducted Emissions",
        "What differential- and common-mode filter lets the PFC front end meet the conducted-emission "
        "limits over 150 kHz–30 MHz, while staying within the safety earth-leakage ceiling?",
        ["10.1 Basis — two orthogonal inputs (safety leakage vs compliance limit) + the method",
         "10.2 Noise at the LISN — differential and common-mode estimates",
         "10.3 Required attenuation — noise vs the limit line over the band",
         "10.4 Differential-mode stage  ·  10.5 Common-mode stage",
         "10.6 Damping & input-impedance (Middlebrook) stability",
         "10.7 Component summary, safety & feasibility"])

    # ── 10.1 basis ──
    step_h(story, "10.1", "Compliance Basis & Method", CH)
    annotation(story, "CONCEPT",
        "Two <b>orthogonal</b> designer inputs drive the filter. The SAFETY standard sets the earth-leakage "
        "ceiling — a hard cap on total Y-capacitance. The COMPLIANCE profile sets the conducted-emission "
        "envelope (CISPR 11/EN 55011, CISPR 32/EN 55032, FCC &#167;15.107; Class A/B). They pull in "
        "opposite directions: compliance wants more Y-cap for common-mode attenuation, safety caps it. The "
        "synthesis finds the smallest filter that meets the limit WITHIN the leakage ceiling, or reports "
        "infeasibility back to the design rather than silently violating either.", CH)
    body(story,
        "The method is the standard required-attenuation flow: estimate the bare-EUT noise at the LISN, "
        "subtract the (limit &#8722; margin) line to get the required attenuation over 150 kHz&#8211;30 MHz, "
        "convert the worst point into an LC corner frequency (40 dB/decade per stage), then split that "
        "corner into L and C under the safety and saturation constraints.", CH)
    data_table(story, "10.1", "Declared Inputs & Carried-in Basis", "The safety/compliance choices + the PFC context.",
        ["Input", "Value", "Role"],
        [["Compliance profile", str(prof_label), f"Class {klass} / {det} detector"],
         ["Design margin", f"{_f(margin,0)} dB", "subtracted from the limit line"],
         ["Safety leakage limit", f"{_f(r['leakage_limit_A']*1e3,2)} mA", "hard Y-cap ceiling"],
         ["Bus voltage V<sub>bus</sub>", f"{_f(b['v_bus'],1)} V", "CM charge-per-edge"],
         ["Switching freq f<sub>sw</sub> &#215; N<sub>ch</sub>", f"{_f(b['f_sw']/1e3,0)} kHz &#215; {int(b['n_phases'])}", "interleaving"],
         ["First in-band harmonic", f"{_f(r['first_harmonic_hz']/1e3,0)} kHz", "= N<sub>ch</sub>&#183;f<sub>sw</sub>"],
         ["Inductor ripple I<sub>pp</sub>", f"{_f(b['i_ripple_pp_A'],2)} A", "DM noise source"],
         ["Bulk-cap ESR", (f"{_f(b['esr_bulk_mohm'],1)} m{_OHM}" if b.get('esr_bulk_mohm') else "default"), "DM noise across ESR"]],
        col_widths=[CW*0.34, CW*0.34, CW*0.32], ch=CH)
    if r["noise_source"] == "estimate":
        annotation(story, "NOTE",
            "Noise is a first-order <b>estimate</b> (DM from the input-ripple harmonics across the bulk-cap "
            "ESR; CM from C<sub>parasitic</sub>&#183;dv/dt). It is a pre-compliance starting point &#8212; "
            "replace with a measured bare-EUT spectrum for certification sign-off.", CH)

    # ── 10.2 noise ──
    step_h(story, "10.2", "Noise at the LISN", CH)
    body(story,
        "<b>Model.</b> The differential-mode noise comes from the input-current ripple harmonics developing "
        "a voltage across the bulk-capacitor ESR (the HF-dominant shunt the LISN sees). The common-mode "
        "noise comes from the switch-node dv/dt driving displacement current through the node-to-earth "
        "parasitic capacitance; its envelope is flat to a knee at 1/(&#960;&#183;t<sub>r</sub>), then rolls "
        "off. With N-channel interleaving the first DM harmonic is shifted up to N&#183;f<sub>sw</sub>, so "
        "peaks below 150 kHz fall outside the measured band.", CH)
    eq_box(story, [r"V_{DM}(f)=I_{h}(f)\,ESR,\qquad I_{h}\propto \dfrac{1}{n^2}\ \mathrm{at}\ n\,(N f_{sw})",
                   r"I_{CM}(f)\approx 2\,(C_{p}V_{bus})\,f_{sw}\ \ \mathrm{up\ to}\ \ f_{knee}=\dfrac{1}{\pi t_r}"],
           number="10.2", ch=CH)

    # ── 10.3 required attenuation ──
    step_h(story, "10.3", "Required Attenuation", CH)
    body(story,
        "At each frequency the required attenuation is the noise minus the (limit &#8722; margin) line; the "
        "worst point over the band sets the filter corner. A single LC stage gives 40 dB/decade; if that "
        "needs an impractically low corner the synthesis escalates to two stages (80 dB/decade).", CH)
    eq_box(story, [r"A_{req}(f)=V_{noise}(f)-\left(L_{limit}(f)-\mathrm{margin}\right)",
                   r"f_{c}=\dfrac{f_{noise}}{10^{\,A_{req}/(20\,m)}}\quad(m=\mathrm{poles})"],
           number="10.3", ch=CH)
    _W = lambda txt: body(story, txt, CH)
    _W(f"<b>Differential mode:</b> the worst required attenuation is <b>{_f(r['dm_req_att_db'],0)} dB</b> at "
       f"{_f(r['dm_req_att_f']/1e3,0)} kHz &#8658; {r['dm_stages']} LC stage(s), corner "
       f"<b>f<sub>c,DM</sub> = {_f(r['dm_corner_hz']/1e3,1)} kHz</b>.")
    _W(f"<b>Common mode:</b> the worst required attenuation is <b>{_f(r['cm_req_att_db'],0)} dB</b> at "
       f"{_f(r['cm_req_att_f']/1e3,0)} kHz &#8658; {r['cm_stages']} LC stage(s), corner "
       f"<b>f<sub>c,CM</sub> = {_f(r['cm_corner_hz']/1e3,1)} kHz</b>.")

    # ── 10.4 DM stage ──
    step_h(story, "10.4", "Differential-Mode Stage", CH)
    body(story,
        "<b>Model.</b> The DM filter is the X-capacitor (line-to-line) with a DM inductor (often the "
        "leakage inductance of the common-mode choke). The X-cap is grown first (it is cheap and lossless) "
        "and the DM inductance solved from the corner; if that inductance exceeds the saturation-practical "
        "limit, the synthesis flags adding an X-cap bank or a second stage.", CH)
    eq_box(story, [r"f_{c,DM}=\dfrac{1}{2\pi\sqrt{L_{DM}\,C_X}}\;\Rightarrow\;L_{DM}=\dfrac{1}{(2\pi f_{c,DM})^2\,C_X}"],
           number="10.4", ch=CH)
    _W(f"<b>Worked.</b> With C<sub>X</sub> = {_f(r['c_x']*1e6,3)} {_MU}F at the DM corner "
       f"{_f(r['dm_corner_hz']/1e3,1)} kHz, the DM inductance is <b>L<sub>DM</sub> = {_f(r['l_dm']*1e6,1)} "
       f"{_MU}H</b>.")

    # ── 10.5 CM stage ──
    step_h(story, "10.5", "Common-Mode Stage", CH)
    body(story,
        "<b>Model.</b> The CM filter is the common-mode choke with the Y-capacitors (line/neutral to PE). "
        "Y-capacitance is fixed FIRST by the safety leakage ceiling &#8212; the total Y-cap is whatever the "
        "leakage budget allows after subtracting any Y-cap already committed upstream &#8212; then the CM "
        "inductance is solved from the corner. This ordering guarantees the earth-leakage limit can never "
        "be violated.", CH)
    eq_box(story, [r"C_{Y,max}=\dfrac{k\,I_{leak,lim}}{2\pi f_{line}\,V_{ac,max}},\qquad "
                   r"L_{CM}=\dfrac{1}{(2\pi f_{c,CM})^2\,2C_Y}"], number="10.5", ch=CH)
    _W(f"<b>Worked.</b> The leakage ceiling allows C<sub>Y</sub> = {_f(r['c_y_emi_total']*1e9,2)} nF total "
       f"({_f(r['c_y_emi_total']*1e9/2,2)} nF each L-PE / N-PE); solving the {_f(r['cm_corner_hz']/1e3,1)} kHz "
       f"corner gives <b>L<sub>CM</sub> = "
       + ("&#8734; (infeasible)" if not (r['l_cm'] < float('inf')) else f"{_f(r['l_cm']*1e3,2)} mH") + "</b>.")

    # ── 10.6 damping & stability ──
    step_h(story, "10.6", "Damping & Input-Impedance Stability", CH)
    body(story,
        "<b>Model.</b> An undamped LC input filter peaks at its corner and can destabilize the converter, "
        "whose input looks like a negative resistance (constant-power load). A parallel R&#8211;C damping "
        "leg flattens the peak, and the Middlebrook criterion requires the filter's characteristic "
        "impedance Z<sub>0</sub> = &#8730;(L<sub>DM</sub>/C<sub>X</sub>) to stay well below the magnitude of "
        "the converter's input resistance |R<sub>in</sub>| = V<sub>ac,min</sub>&#178;/P<sub>in</sub>.", CH)
    eq_box(story, [r"Z_0=\sqrt{L_{DM}/C_X},\qquad |R_{in}|=\dfrac{V_{ac,min}^2}{P_{out}/\eta},\qquad Z_0\ll|R_{in}|"],
           number="10.6", ch=CH)
    _W(f"<b>Worked.</b> Z<sub>0</sub> = {_f(r['stability_z0_dm'],1)} {_OHM} vs |R<sub>in</sub>| = "
       f"{_f(r['stability_rin_conv'],0)} {_OHM} &#8658; <b>{'stable' if r['stability_ok'] else 'CHECK — increase damping / C_X'}</b>. "
       f"Damping leg: R<sub>d</sub> &#8776; {_f(r['damp_r'],0)} {_OHM} with C<sub>d</sub> = {_f(r['damp_c']*1e6,2)} {_MU}F.")

    # ── 10.7 summary ──
    step_h(story, "10.7", "Component Summary, Safety & Feasibility", CH)
    data_table(story, "10.7", "Synthesized Filter & Checks",
        f"Conducted Class {klass} / {det}, {_f(margin,0)} dB margin. Verdict: "
        + ("FEASIBLE." if r["feasible"] else "INFEASIBLE — see feedback."),
        ["Quantity", "Value", "Check"],
        [["DM choke L<sub>DM</sub>", f"{_f(r['l_dm']*1e6,1)} {_MU}H", "&#8212;"],
         ["X-cap C<sub>X</sub>", f"{_f(r['c_x']*1e6,3)} {_MU}F", "&#8212;"],
         ["CM choke L<sub>CM</sub>", ("&#8734;" if not (r['l_cm'] < float('inf')) else f"{_f(r['l_cm']*1e3,2)} mH"), "&#8212;"],
         ["Y-cap C<sub>Y</sub> (total)", f"{_f(r['c_y_emi_total']*1e9,2)} nF", "leakage-bounded"],
         ["Damping R<sub>d</sub> / C<sub>d</sub>", f"{_f(r['damp_r'],0)} {_OHM} / {_f(r['damp_c']*1e6,2)} {_MU}F", "&#8212;"],
         ["Earth leakage", f"{_f(r['leakage_actual_A']*1e3,2)} mA",
          ("PASS" if r['leakage_actual_A'] <= r['leakage_limit_A'] else "OVER") + f" (limit {_f(r['leakage_limit_A']*1e3,2)})"],
         ["Middlebrook stability", f"Z<sub>0</sub> {_f(r['stability_z0_dm'],0)} {_OHM}",
          "PASS" if r['stability_ok'] else "CHECK"],
         ["X-cap discharge", (f"{_f(r['xcap_discharge_s'],2)} s" if r.get('xcap_discharge_s') is not None else "set bleeder"), "safety rule"]],
        col_widths=[CW*0.34, CW*0.30, CW*0.36], ch=CH)
    if r.get("feedback"):
        annotation(story, "PIPELINE FEEDBACK",
            " ".join(r["feedback"])[:600] + " — revisit the protection-stage Y-caps or the safety/compliance choice.", CH)
    if r.get("warnings"):
        annotation(story, "NOTE", " ".join(r["warnings"])[:600], CH)
    annotation(story, "NOTE",
        "Confirm the chosen common-mode-choke core for saturation and its leakage inductance (which doubles "
        "as the DM inductor), and re-run against a measured bare-EUT spectrum before certification.", CH)


def _doc(target):
    from reportlab.platypus import SimpleDocTemplate
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    return SimpleDocTemplate(target, pagesize=A4, leftMargin=20*mm, rightMargin=20*mm,
                             topMargin=18*mm, bottomMargin=18*mm, title="Chapter 10 — Input EMI Filter")


def build_inputfilter_report(design, cap=None, protection=None, ntc=None, opts=None) -> bytes:
    """Standalone Chapter-10 PDF (merged after Chapter 9)."""
    from reportlab.platypus import PageBreak
    story = []
    build_inputfilter_story(story, design, cap, protection, ntc, opts)
    while story and isinstance(story[0], PageBreak):
        story.pop(0)
    buf = io.BytesIO()
    _doc(buf).build(story)
    return buf.getvalue()
