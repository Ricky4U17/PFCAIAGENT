"""
Chapter 10 — Input EMI Filter (Conducted Emissions)
===================================================
Thesis-level chapter built from the SAME engine + adapter the GUI uses (`inputfilter.adapter`), so the
documented filter is identical to the selection page. Follows the EMI_Input_Filter_Design_Guide (Rev J)
methodology — computed noise source, required attenuation, DM/CM synthesis with real-parasitic ABCD
insertion loss, series-R-L damping + frequency-domain Middlebrook stability, protection/surge/inrush,
leakage (normal + single-fault), component schedule, loss budget, per-operating-point verification,
governing equations and a worked-calculation appendix — all rendered in our document format so the
combined PDF reads consistently. Every number traces to a designer input or a named, reported default
(App-B discipline); nothing is a hardcoded reference value.

Standalone document (like the Chapter-7/8/9 reports), merged after Chapter 9.
"""
from __future__ import annotations
import io

from app.mode_b.doc_report_builder import (
    chapter_splash, step_h, sub_h, body, eq_box, data_table, annotation, CW,
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


# ────────────────────────────── figures ──────────────────────────────
def _img_from_fig(fig, dpi=180):
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


def _fig_source_vs_limit(r):
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    s = r["spectra"]; fk = [x / 1e3 for x in s["f"]]
    fig, ax = plt.subplots(figsize=(7.2, 3.0))
    ax.semilogx(fk, s["cm_src"], color="#c0392b", lw=1.3, label="CM source (unfiltered)")
    ax.semilogx(fk, s["dm_src"], color="#1456b8", lw=1.3, label="DM source (unfiltered)")
    ax.semilogx(fk, s["limit"], color="#111", lw=1.1, ls="--", label="Class limit")
    ax.set_xlabel("Frequency (kHz)", fontsize=8); ax.set_ylabel("dBµV", fontsize=8)
    ax.set_title("Figure 10.1 — Computed unfiltered emissions vs the conducted limit", fontsize=8.5)
    ax.grid(True, which="both", alpha=0.3); ax.tick_params(labelsize=7); ax.legend(fontsize=7, loc="upper right")
    fig.tight_layout()
    return _img_from_fig(fig)


def _fig_required_and_delivered(r):
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    s = r["spectra"]; m = r["margin_db"]; fk = [x / 1e3 for x in s["f"]]
    dm_req = [max(sc - (li - m), 0.0) for sc, li in zip(s["dm_src"], s["limit"])]
    cm_req = [max(sc - (li - m), 0.0) for sc, li in zip(s["cm_src"], s["limit"])]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(7.4, 3.0))
    a1.semilogx(fk, s["dm_il"], color="#1456b8", lw=1.4, label="delivered IL (ABCD)")
    a1.semilogx(fk, dm_req, color="#c0392b", lw=1.1, ls="--", label="required (+margin)")
    a1.set_title("DM insertion loss vs requirement", fontsize=8); a1.set_ylabel("dB", fontsize=8)
    a2.semilogx(fk, s["cm_il"], color="#1456b8", lw=1.4, label="delivered IL (ABCD)")
    a2.semilogx(fk, cm_req, color="#c0392b", lw=1.1, ls="--", label="required (+margin)")
    a2.set_title("CM insertion loss vs requirement", fontsize=8)
    for a in (a1, a2):
        a.set_xlabel("Frequency (kHz)", fontsize=8); a.grid(True, which="both", alpha=0.3)
        a.tick_params(labelsize=7); a.legend(fontsize=6.5, loc="lower right")
    fig.suptitle("Figure 10.2 — Delivered insertion loss (real-parasitic ABCD model) vs required", fontsize=8.5)
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    return _img_from_fig(fig)


def _fig_middlebrook(r):
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    s = r["spectra"]; fk = [x / 1e3 for x in s["mbk_f"]]
    fig, ax = plt.subplots(figsize=(7.2, 3.0))
    ax.loglog(fk, s["mbk_zin"], color="#159", lw=1.3, label="converter |Z_in|")
    ax.loglog(fk, s["mbk_zout"], color="#c0392b", lw=1.3, label="filter |Z_out| (damped)")
    ax.set_xlabel("Frequency (kHz)", fontsize=8); ax.set_ylabel("|Z| (Ω)", fontsize=8)
    ax.set_title("Figure 10.3 — Middlebrook: filter |Z_out| vs converter |Z_in|", fontsize=8.5)
    ax.grid(True, which="both", alpha=0.3); ax.tick_params(labelsize=7); ax.legend(fontsize=7)
    fig.tight_layout()
    return _img_from_fig(fig)


def _fig_loss_sweep(r):
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    pp = r["per_point"]
    if not pp:
        return None
    v = [d["vac"] for d in pp]; cu = [d["cu_loss_w"] for d in pp]; lk = [d["i_leak_a"] * 1e3 for d in pp]
    fig, ax = plt.subplots(figsize=(7.2, 2.9))
    colors = ["#c0392b" if vv < 180 else "#1456b8" for vv in v]
    ax.bar([str(int(vv)) for vv in v], cu, color=colors, alpha=0.85)
    ax.set_xlabel("Input voltage (Vac)", fontsize=8); ax.set_ylabel("Choke copper loss (W)", fontsize=8)
    ax.set_title("Figure 10.4 — Filter copper loss per operating point (red = low band, blue = high band)", fontsize=8.3)
    ax.grid(True, axis="y", alpha=0.3); ax.tick_params(labelsize=7)
    ax2 = ax.twinx(); ax2.plot([str(int(vv)) for vv in v], lk, "o-", color="#0a0", lw=1.0, ms=3, label="Y-cap leakage (mA)")
    ax2.set_ylabel("Earth leakage (mA)", fontsize=8, color="#0a0"); ax2.tick_params(labelsize=7, colors="#0a0")
    fig.tight_layout()
    return _img_from_fig(fig)


# ────────────────────────────── report body ──────────────────────────────
def build_inputfilter_story(story, design, cap=None, protection=None, ntc=None, opts=None):
    out = calculate_emi(design, cap or {}, protection or {}, ntc or {}, opts or {})
    r = out["result"]; b = out["basis"]
    klass = r["conducted_class"]; det = r["detector"]; margin = r["margin_db"]
    prof_label = emi.COMPLIANCE_PROFILE.get(int((opts or {}).get("compliance_profile", 5)),
                                            (None, None, None, "—"))[3]
    dcdc_on = bool(b.get("dcdc_present"))
    _W = lambda t: body(story, t, CH)
    _linf = (r["l_cm"] == float("inf")) or (isinstance(r["l_cm"], float) and r["l_cm"] != r["l_cm"])

    chapter_splash(story, CH, "Input EMI Filter — Conducted Emissions",
        "What differential- and common-mode filter lets the front end meet the conducted-emission limits "
        "over 150 kHz–30 MHz — with margin, without destabilising the converter, and within the safety "
        "earth-leakage ceiling — and how is every value derived from the converter specification?",
        ["10.1 Basis & method — two orthogonal inputs (safety leakage vs compliance limit)",
         "10.2 Noise mechanisms & the computed DM/CM source  ·  10.3 Required attenuation",
         "10.4 Topology & staging  ·  10.5 DM stage  ·  10.6 CM stage (+ source reduction)",
         "10.7 Damping & Middlebrook stability  ·  10.8 Protection, surge, inrush",
         "10.9 Leakage (normal + single-fault)  ·  10.10 Component schedule",
         "10.11 Loss budget  ·  10.12 Per-operating-point verification",
         "10.13 Governing equations  ·  10.14 Verification checklist  ·  10.A Worked calculations"])

    # ── 10.1 basis & method ──
    step_h(story, "10.1", "Compliance Basis & Method", CH)
    annotation(story, "CONCEPT",
        "Two <b>orthogonal</b> designer inputs drive the filter. The SAFETY standard sets the earth-leakage "
        "ceiling — a hard cap on total Y-capacitance. The COMPLIANCE profile sets the conducted-emission "
        "envelope (CISPR 11/EN 55011, CISPR 32/EN 55032, FCC &#167;15.107; Class A/B). They pull in opposite "
        "directions: compliance wants more Y-cap for common-mode attenuation, safety caps it. The synthesis "
        "finds the smallest filter that meets the limit WITHIN the leakage ceiling, or reports infeasibility "
        "back to the design rather than silently violating either.", CH)
    body(story,
        "The method is a loop. First the bare-EUT noise is <b>computed</b> from the converter switching "
        "waveforms and parasitics (Section 10.2). The required attenuation is that noise minus the "
        "(limit &#8722; margin) line over 150 kHz&#8211;30 MHz (Section 10.3). A staged DM+CM network is "
        "synthesised to the binding corner and then verified against a real-parasitic ABCD insertion-loss "
        "model (Sections 10.4&#8211;10.7); where a band cannot be met with practical parts the tool returns "
        "a source-reduction target rather than an impossible filter. This is a <b>calculated baseline</b> to "
        "be confirmed by a LISN sweep, after which the same equations are re-run on the measured source.", CH)
    data_table(story, "10.1", "Declared Inputs & Carried-in Basis", "Safety/compliance choices + the PFC (and optional DC-DC) context.",
        ["Input", "Value", "Role"],
        [["Compliance profile", str(prof_label), f"Class {klass} / {det} detector"],
         ["Design margin", f"{_f(margin,0)} dB", "subtracted from the limit line"],
         ["Safety leakage limit", f"{_f(r['leakage_limit_A']*1e3,2)} mA", "hard Y-cap ceiling"],
         ["Bus voltage V<sub>bus</sub>", f"{_f(b['v_bus'],1)} V", "CM charge-per-edge"],
         ["Switching freq f<sub>sw</sub> &#215; N<sub>ch</sub>", f"{_f(b['f_sw']/1e3,0)} kHz &#215; {int(b['n_phases'])}", "interleaving"],
         ["First in-band harmonic", f"{_f(r['first_harmonic_hz']/1e3,0)} kHz", "= N<sub>ch</sub>&#183;f<sub>sw</sub>"],
         ["Boost inductor / phase", f"{_f(b.get('l_boost_uH'),0)} {_MU}H" if b.get('l_boost_uH') else "&#8212;", "DM ripple &#916;I, Middlebrook Z<sub>in</sub>"],
         ["Bulk cap / ESR", (f"{_f(b.get('bulk_c_uF'),0)} {_MU}F / {_f(b['esr_bulk_mohm'],1)} m{_OHM}" if b.get('bulk_c_uF') else "default"), "DM shunt path"],
         ["DC-DC stage", ("present — CM source included" if dcdc_on else "not present (PFC-only)"), "transformer/switch-node CM"],
         ["Noise source", str(r["noise_source"]), "computed / measured / estimate"]],
        col_widths=[CW*0.34, CW*0.34, CW*0.32], ch=CH)

    # ── 10.2 noise mechanisms + computed source ──
    step_h(story, "10.2", "Noise Mechanisms & Computed Source", CH)
    annotation(story, "CONCEPT",
        "Two independent noise circuits share the wires. <b>Differential-mode</b> (DM) flows line&#8596;"
        "neutral, driven by the pulsating PFC input-ripple current and scaling with that current. "
        "<b>Common-mode</b> (CM) flows line+neutral&#8594;earth, driven by dv/dt coupling through parasitic "
        "capacitance to chassis and scaling with voltage. They are filtered by different elements, computed "
        "and verified separately, then recombined for the line-to-earth check.", CH)
    body(story,
        "<b>DM source.</b> The input-ripple current per phase is &#916;I = &#8730;2&#183;V<sub>in</sub>"
        "&#183;D/(L<sub>boost</sub>&#183;f<sub>sw</sub>), reduced by interleaving. A trapezoidal-pulse "
        "envelope (flat, then &#8722;20, then &#8722;40 dB/dec at f<sub>1</sub>=1/(&#960;DT), f<sub>2</sub>="
        "1/(&#960;t<sub>r</sub>)) is current-divided by the bulk capacitor (ESR + j&#969;ESL + 1/j&#969;C) "
        "against the LISN DM impedance — the bulk cap shunts most of the ripple, so DM is usually modest. "
        "<b>CM source.</b> Each coupling node injects a displacement current I = C&#183;dv/dt "
        "(charge/edge Q = C&#183;&#916;V, envelope 2&#183;Q&#183;f<sub>rep</sub> flat to 1/(&#960;t<sub>r</sub>)"
        + (", summed over the PFC switch-node, the DC-DC switch-node and the transformer inter-winding "
           "capacitance C<sub>ps</sub>" if dcdc_on else " from the PFC switch-node") +
        ") into the LISN CM impedance. CM is essentially line-independent because V<sub>bus</sub> is regulated.", CH)
    eq_box(story, [r"\Delta I=\dfrac{\sqrt{2}\,V_{in}\,D}{L_{boost}\,f_{sw}},\qquad "
                   r"f_1=\dfrac{1}{\pi D T},\quad f_2=\dfrac{1}{\pi t_r}",
                   r"I_{CM}=\sum_i 2\,(C_i\,\Delta V_i)\,f_{rep,i},\qquad V_{CM}=I_{CM}\,Z_{LISN,CM}"],
           number="10.2", ch=CH)
    try:
        story.append(_fig_source_vs_limit(r))
    except Exception:
        body(story, "<i>(source figure unavailable)</i>", CH)
    _W(f"<b>Computed result.</b> At 150 kHz the DM source is &#8776; {_f(r['spectra']['dm_src'][0],0)} dBµV "
       f"and the CM source &#8776; {_f(r['spectra']['cm_src'][0],0)} dBµV; CM is the binding mode.")

    # ── 10.3 required attenuation ──
    step_h(story, "10.3", "Required Attenuation", CH)
    body(story,
        "At each frequency the required attenuation is the noise minus the (limit &#8722; margin) line. The "
        "filter is sized to the <b>binding corner</b> — the minimum LC corner over the whole band, not the "
        "single worst point — because the computed source can peak in the mid/high band (bulk-cap ESL), not "
        "only at 150 kHz. A single LC stage gives 40 dB/decade; the synthesis escalates to two stages "
        "(80 dB/decade) when the real-parasitic delivered margin is short.", CH)
    eq_box(story, [r"A_{req}(f)=V_{noise}(f)-\left(L_{limit}(f)-\mathrm{margin}\right)",
                   r"f_{c}=\min_f \dfrac{f}{10^{\,A_{req}(f)/(20\,m)}}\quad(m=\mathrm{poles})"],
           number="10.3", ch=CH)
    _W(f"<b>Differential mode:</b> worst required attenuation <b>{_f(r['dm_req_att_db'],0)} dB</b> at "
       f"{_f(r['dm_req_att_f']/1e3,0)} kHz &#8658; {r['dm_stages']} LC stage(s), binding corner "
       f"<b>{_f(r['dm_corner_hz']/1e3,1)} kHz</b>.")
    _W(f"<b>Common mode:</b> worst required attenuation <b>{_f(r['cm_req_att_db'],0)} dB</b> at "
       f"{_f(r['cm_req_att_f']/1e3,0)} kHz &#8658; {r['cm_stages']} LC stage(s), binding corner "
       f"<b>{_f(r['cm_corner_hz']/1e3,1)} kHz</b>.")

    # ── 10.4 topology & staging ──
    step_h(story, "10.4", "Filter Topology & Staging", CH)
    body(story,
        "An LC section attenuates by <b>impedance mismatch</b>: a shunt capacitor works facing a high "
        "impedance, a series inductor facing a low impedance. The mains side through the LISN is 50 &#937; "
        "per line; the converter side is low-impedance at switching frequencies. Hence the inductor faces "
        "the converter and the capacitor faces the mains (CL orientation). Same-mode stages are stacked to "
        "steepen roll-off rather than growing one component. The CM choke provides large CM inductance while "
        "its leakage doubles as DM inductance; X-caps (line-line) filter DM; Y-caps (line-earth) filter CM "
        "and are capped by the leakage-current safety limit (Section 10.9).", CH)

    # ── 10.5 DM stage ──
    step_h(story, "10.5", "Differential-Mode Stage", CH)
    body(story,
        "<b>Model.</b> The DM filter is the X-capacitor(s) with a DM inductor (often the leakage inductance "
        "of the common-mode choke plus a discrete DM choke). The X-cap is set at the practical maximum first "
        "(it is cheap and lossless) and the DM inductance solved from the binding corner; the design is then "
        "verified against the real-parasitic ABCD model and escalated to a second stage if short.", CH)
    eq_box(story, [r"f_{c,DM}=\dfrac{1}{2\pi\sqrt{L_{DM}\,C_X}}\;\Rightarrow\;"
                   r"L_{DM}=\dfrac{n^2}{(2\pi f_{c,DM})^2\,C_X}\quad(n=\mathrm{stages})"],
           number="10.5", ch=CH)
    _W(f"<b>Worked.</b> With C<sub>X</sub> = {_f(r['c_x']*1e6,3)} {_MU}F at the {_f(r['dm_corner_hz']/1e3,1)} kHz "
       f"binding corner ({r['dm_stages']} stage), the total DM inductance is <b>L<sub>DM</sub> = "
       f"{_f(r['l_dm']*1e6,1)} {_MU}H</b>. The delivered ABCD insertion loss is {_f(r['dm_il_db'],0)} dB with "
       f"a worst-case margin of <b>{_f(r['dm_margin_db'],1)} dB</b> at {_f(r['dm_margin_f']/1e3,0)} kHz.")

    # ── 10.6 CM stage ──
    step_h(story, "10.6", "Common-Mode Stage", CH)
    body(story,
        "<b>Model.</b> The CM filter is the common-mode choke(s) with the Y-capacitors (line/neutral to PE). "
        "Y-capacitance is fixed FIRST by the safety leakage ceiling — the total Y-cap is whatever the leakage "
        "budget allows after subtracting any Y-cap committed upstream — then the CM inductance is solved from "
        "the binding corner. This ordering guarantees the earth-leakage limit can never be violated.", CH)
    eq_box(story, [r"C_{Y,max}=\dfrac{k\,I_{leak,lim}}{2\pi f_{line}\,V_{ac,max}},\qquad "
                   r"L_{CM}=\dfrac{n^2}{(2\pi f_{c,CM})^2\,2C_Y}"], number="10.6", ch=CH)
    _W(f"<b>Worked.</b> The leakage ceiling allows C<sub>Y</sub> = {_f(r['c_y_emi_total']*1e9,2)} nF total "
       f"({_f(r['c_y_emi_total']*1e9/2,2)} nF each L-PE / N-PE); solving the {_f(r['cm_corner_hz']/1e3,1)} kHz "
       f"binding corner ({r['cm_stages']} stage) gives <b>L<sub>CM</sub> = "
       + ("&#8734; (infeasible)" if _linf else f"{_f(r['l_cm']*1e3,2)} mH") +
       f"</b>, delivering {_f(r['cm_il_db'],0)} dB with margin <b>{_f(r['cm_margin_db'],1)} dB</b>.")
    try:
        story.append(_fig_required_and_delivered(r))
    except Exception:
        body(story, "<i>(insertion-loss figure unavailable)</i>", CH)
    if r["cm_margin_db"] < 0:
        annotation(story, "SOURCE REDUCTION",
            "The strengthened CM stage has nearly spent the Y-cap leakage budget, and HF CM is floored by "
            "choke self-resonance/layout. The next lever is not more Y-capacitance — it is reducing the CM "
            "SOURCE: a transformer Faraday shield (lower C<sub>ps</sub>), a low-capacitance thermal interface "
            "at the switch nodes, and moderated dV/dt. Halving the dominant coupling capacitance buys ~6 dB "
            "of CM margin at the source, without the leakage/loss penalty of larger Y-caps.", CH)

    # ── 10.7 damping & stability ──
    step_h(story, "10.7", "Damping & Input-Impedance (Middlebrook) Stability", CH)
    body(story,
        "<b>Model.</b> An undamped LC input filter peaks at its resonance and can destabilise the converter, "
        "whose closed-loop input looks like a negative resistance (constant-power load). A <b>series R&#8211;L</b> "
        "branch across the DM choke (L<sub>d</sub> &#8776; L<sub>DM</sub>) damps the peak without the large "
        "blocking capacitor and reactive current of the parallel-R&#8211;C method. R<sub>d</sub> is grid-"
        "searched to minimise the computed filter output-impedance peak. Middlebrook then requires the filter "
        "output impedance to stay 6 dB below the converter input impedance at the resonance.", CH)
    eq_box(story, [r"20\log_{10}\left(\dfrac{|Z_{in,conv}(f)|}{|Z_{out,filter}(f)|}\right)\geq 6\ \mathrm{dB}",
                   r"|R_{in}|=\dfrac{V_{ac,min}^2}{P_{in}}\ \ (\mathrm{LF}),\qquad "
                   r"|Z_{in}|\approx 2\pi f\,\dfrac{L_{boost}}{N_{ch}}\ \ (f_{res})"],
           number="10.7", ch=CH)
    _W(f"<b>Worked.</b> Series-R&#8211;L damping R<sub>d</sub> = {_f(r['damp_r'],2)} {_OHM}, L<sub>d</sub> = "
       f"{_f(r['damp_l']*1e6,1)} {_MU}H across L<sub>DM</sub>. At the DM resonance {_f(r['dm_res_hz']/1e3,1)} "
       f"kHz the Middlebrook margin is <b>{_f(r['stability_margin_db'],1)} dB</b> &#8658; "
       f"<b>{'stable' if r['stability_ok'] else 'CHECK — lower R_d / raise C_X'}</b>.")
    try:
        story.append(_fig_middlebrook(r))
    except Exception:
        body(story, "<i>(Middlebrook figure unavailable)</i>", CH)

    # ── 10.8 protection ──
    step_h(story, "10.8", "Protection, Surge & Inrush", CH)
    body(story,
        "Requirements-driven parts (finalised with the surge standard, mains category, insulation/creepage "
        "and safety approvals — not the filter transfer function): a line <b>fuse</b> upstream of all filter "
        "components; a <b>MOV</b> (e.g. 275 Vac MCOV class) line-to-line for differential surge — note the "
        "MCOV is not the clamp voltage, which is read from the datasheet at the specified surge current; an "
        "<b>NTC</b> inrush limiter in series, relay-bypassed at steady state on high-power designs; and an "
        "optional <b>GDT</b> line/neutral-to-earth for high-energy CM surges (rating set by the mains "
        "line-to-earth voltage — never a low-voltage GDT on a node that sees mains potential to earth).", CH)
    sub_h(story, "10.8.1", "X-capacitor discharge (bleeder)", CH)
    eq_box(story, [r"R_{bleed}\leq \dfrac{-t}{C_{X,total}\,\ln(V_{safe}/V_{peak})}"], number="10.8", ch=CH)
    _W("<b>Worked.</b> X-cap discharge "
       + (f"time constant is {_f(r['xcap_discharge_s'],2)} s with the chosen bleeder."
          if r.get("xcap_discharge_s") is not None else
          "must be verified — provide a bleeder resistor so the X-caps drain below the safe voltage within "
          "the standard's time limit."))

    # ── 10.9 leakage ──
    step_h(story, "10.9", "Leakage (Touch) Current — Normal + Single Fault", CH)
    body(story,
        "Y-capacitors conduct a small line-frequency current from line to protective earth; the safety "
        "standard caps this touch current for the equipment's protection class, checked under both normal "
        "and single-fault (open-neutral) conditions.", CH)
    eq_box(story, [r"I_{leak}=2\pi f_{line}\,V\,C_{Y,total}\leq I_{lim}"], number="10.9", ch=CH)
    _leak_ok = max(r["leakage_actual_A"], r["leak_fault_A"]) <= r["leakage_limit_A"]
    data_table(story, "10.9", "Earth-Leakage Check", "Evaluated at the worst line corner and frequency.",
        ["Condition", "Current", "Limit", "Verdict"],
        [["Normal", f"{_f(r['leakage_actual_A']*1e3,2)} mA", f"{_f(r['leakage_limit_A']*1e3,2)} mA",
          "PASS" if r['leakage_actual_A'] <= r['leakage_limit_A'] else "OVER"],
         ["Single fault (open neutral)", f"{_f(r['leak_fault_A']*1e3,2)} mA", f"{_f(r['leakage_limit_A']*1e3,2)} mA",
          "PASS" if r['leak_fault_A'] <= r['leakage_limit_A'] else "OVER"]],
        col_widths=[CW*0.40, CW*0.22, CW*0.20, CW*0.18], ch=CH)
    if not _leak_ok:
        annotation(story, "PITFALL", "Leakage exceeds the class limit — reduce Y-capacitance and recover CM "
                   "margin by source reduction (Section 10.6), or re-select a lower protection class.", CH)

    # ── 10.10 component schedule ──
    step_h(story, "10.10", "Component Schedule (Netlist, Mains → Converter)", CH)
    _cy_each = r["c_y_emi_total"] * 1e9 / 2
    data_table(story, "10.10", "Synthesized Filter Components",
        "Safety-rated capacitors (X2 line-to-line, Y2 line-to-earth). Magnetics are calculated targets — "
        "confirm saturation, DCR and self-resonance against vendor data before sign-off.",
        ["Ref", "Value", "Function"],
        [["F1 / MOV / NTC / GDT", "requirements-driven", "fuse / surge / inrush / CM surge (Section 10.8)"],
         ["C_X (X2)", f"{_f(r['c_x']*1e6,3)} {_MU}F ({r['dm_stages']} stage)", "DM, line-to-line"],
         ["L_DM", f"{_f(r['l_dm']*1e6,1)} {_MU}H ({r['dm_stages']} stage)", "DM choke"],
         ["R_d + L_d", f"{_f(r['damp_r'],2)} {_OHM} + {_f(r['damp_l']*1e6,1)} {_MU}H", "series-R-L damping across L_DM"],
         ["L_CM", ("&#8734;" if _linf else f"{_f(r['l_cm']*1e3,2)} mH ({r['cm_stages']} stage)"), "CM choke"],
         ["C_Y (Y2)", f"{_f(r['c_y_emi_total']*1e9,2)} nF total ({_f(_cy_each,2)} nF each)", "CM, line/neutral-to-PE"],
         ["R_bleed", (f"{_f(r['xcap_discharge_s'],2)} s discharge" if r.get('xcap_discharge_s') is not None else "set per §10.8"), "X-cap bleeder"]],
        col_widths=[CW*0.24, CW*0.36, CW*0.40], ch=CH)

    # ── 10.11 loss ──
    step_h(story, "10.11", "Loss Budget", CH)
    body(story,
        "Losses are computed component-by-component. Copper (I&#178;&#183;DCR) dominates and is worst at the "
        "highest-current line corner; core loss is from HF ripple flux (CM-choke line-frequency core loss "
        "&#8776; 0, net flux cancels); cap ESR and bleeder (V&#178;/R) are minor. Core and X-cap-ESR losses "
        "are shown as estimates until vendor data replaces them.", CH)
    if r.get("loss_rows"):
        data_table(story, "10.11", f"Loss Breakdown — worst case @ {_f(r['loss_worst_vac'],0)} Vac",
            "Copper from I&#178;&#183;DCR; core/ESR estimated as a fraction of copper (overridable).",
            ["Component", "Loss (W)"],
            [[lbl, _f(w, 2)] for lbl, w in r["loss_rows"]] + [["<b>Total</b>", f"<b>{_f(r['loss_total_w'],2)}</b>"]],
            col_widths=[CW*0.6, CW*0.4], ch=CH)
    try:
        fig = _fig_loss_sweep(r)
        if fig is not None:
            story.append(fig)
    except Exception:
        body(story, "<i>(loss figure unavailable)</i>", CH)

    # ── 10.12 per-operating-point verification ──
    step_h(story, "10.12", "Per-Operating-Point Verification", CH)
    body(story,
        "Derived at every point of the shared operating grid: input current, choke copper loss, X-cap "
        "reactive current, Y-cap earth leakage, and the mode expected to dominate emissions (DM at low line, "
        "CM at high line). Reactive and leakage currents are evaluated at the line frequency.", CH)
    if r.get("per_point"):
        data_table(story, "10.12", "Operating-Point Sweep",
            "One row per grid point; the dominant mode flips from DM to CM across the 132&#8211;180 V band.",
            ["V_ac", "I_in (A)", "Cu loss (W)", "I_Cx (mA)", "I_leak (µA)", "Mode"],
            [[_f(d["vac"], 0), _f(d["i_in"], 2), _f(d["cu_loss_w"], 2),
              _f(d["i_cx_a"] * 1e3, 0), _f(d["i_leak_a"] * 1e6, 0), d["worst_mode"]] for d in r["per_point"]],
            col_widths=[CW*0.13, CW*0.17, CW*0.20, CW*0.18, CW*0.20, CW*0.12], ch=CH)
    # Per-line IL verification (§19): worst-case delivered margin at each line condition. The DM source
    # scales with the per-line ripple; the CM source is line-independent (V_bus regulated), so its margin
    # is common. Post-filter emission below the limit ⇔ margin ≥ 0.
    if r.get("per_line"):
        body(story,
            "<b>Per-line verification.</b> The final check layers each line's emission against the delivered "
            "insertion loss: the worst-case margin over the band (delivered IL &#8722; required attenuation "
            "from that line's source). DM is worst at low line (highest ripple); CM is common across lines "
            "because the bus is regulated. A margin &#8805; 0 dB means the post-filter emission clears the "
            "limit at that line condition.", CH)
        _all_ok = all(d["ok"] for d in r["per_line"])
        data_table(story, "10.12b", "Per-Line IL Verification (post-filter vs limit)",
            ("All line conditions clear the limit." if _all_ok else
             "Some lines are short of the design margin — see the CM source-reduction note (Section 10.6)."),
            ["V_ac", "Dominant", "DM margin (dB)", "CM margin (dB)", "Verdict"],
            [[_f(d["vac"], 0), d["mode"], _f(d["dm_margin_db"], 1), _f(d["cm_margin_db"], 1),
              ("PASS" if d["ok"] else "SHORT")] for d in r["per_line"]],
            col_widths=[CW*0.15, CW*0.18, CW*0.24, CW*0.24, CW*0.19], ch=CH)

    # ── 10.13 governing equations ──
    step_h(story, "10.13", "Governing Equations", CH)
    eq_box(story, [r"I_{in}=\dfrac{P_{out}}{V_{in}\,\eta\,PF}",
                   r"A_{req}=A_{noise}-L_{limit}+m",
                   r"f_c=\dfrac{1}{2\pi\sqrt{LC}},\quad C_X=\dfrac{1}{(2\pi f_c)^2 L_{DM}},\quad "
                   r"L_{CM}=\dfrac{1}{(2\pi f_c)^2\,2C_Y}",
                   r"\zeta=\dfrac{R}{2}\sqrt{C/L}\geq 0.707,\qquad R_n=\dfrac{V_{in}^2}{P_{in}}",
                   r"R_{bleed}\leq\dfrac{-t}{C_X\ln(V_{safe}/V_{peak})},\qquad I_{leak}=2\pi f V C_{Y,total}"],
           number="10.13", ch=CH)

    # ── 10.14 checklist ──
    step_h(story, "10.14", "Compliance & Verification Checklist", CH)
    body(story,
        "&#8226; Baseline LISN sweep (QP + AVG) with DM/CM separation; replace the computed source with "
        "measured data and recompute the required attenuation. &#8226; Confirm &#8805; margin in every band. "
        "&#8226; Measure filter |Z<sub>out</sub>| (DM); confirm &#8805; 6 dB below converter |Z<sub>in</sub>| "
        "through resonance. &#8226; Verify at the worst-current and worst-CM corners; thermal soak at the two "
        "worst-current points. &#8226; Confirm leakage under normal and open-neutral fault; X-cap discharge "
        "time; MOV/fuse coordination. &#8226; Radiated pre-scan (30 MHz&#8211;1 GHz) with cable/enclosure "
        "mitigations as needed.", CH)

    # ── verdict + provenance ──
    data_table(story, "10.15", "Filter Verdict & Design Grade",
        f"Conducted Class {klass} / {det}, {_f(margin,0)} dB target margin. Noise source: {r['noise_source']}.",
        ["Quantity", "Value", "Check"],
        [["DM delivered margin", f"{_f(r['dm_margin_db'],1)} dB", "PASS" if r['dm_margin_db'] >= 0 else "SHORT"],
         ["CM delivered margin", f"{_f(r['cm_margin_db'],1)} dB", "PASS" if r['cm_margin_db'] >= 0 else "SHORT — reduce source"],
         ["Middlebrook margin", f"{_f(r['stability_margin_db'],1)} dB", "PASS" if r['stability_ok'] else "CHECK"],
         ["Earth leakage (norm/fault)", f"{_f(r['leakage_actual_A']*1e3,2)} / {_f(r['leak_fault_A']*1e3,2)} mA",
          "PASS" if _leak_ok else "OVER"],
         ["Total filter loss", f"{_f(r['loss_total_w'],1)} W @ {_f(r['loss_worst_vac'],0)} V", "&#8212;"],
         ["Feasibility", ("FEASIBLE" if r["feasible"] else "INFEASIBLE"), "leakage-budget gate"]],
        col_widths=[CW*0.34, CW*0.34, CW*0.32], ch=CH)
    if r.get("feedback"):
        annotation(story, "PIPELINE FEEDBACK",
            " ".join(r["feedback"])[:600] + " — revisit the protection-stage Y-caps or the safety/compliance choice.", CH)
    if r.get("warnings"):
        annotation(story, "NOTE", " ".join(r["warnings"])[:900], CH)

    # ── 10.A worked calculations ──
    step_h(story, "10.A", "Appendix — Worked Calculations", CH)
    _pp0 = (r["per_point"][0] if r.get("per_point") else {"vac": b.get("vac_max"), "i_in": 0})
    _cu_w = sum(w for l, w in r.get("loss_rows", []) if "copper" in l)
    _W(f"<b>A.1 Input current</b> (worst corner {_f(_pp0['vac'],0)} Vac): "
       f"I<sub>in</sub> = P<sub>out</sub>/(V&#183;&#951;&#183;PF) = <b>{_f(_pp0['i_in'],2)} A</b> — sets the choke current rating.")
    _W(f"<b>A.2 DM stage:</b> binding corner f<sub>c,DM</sub> = {_f(r['dm_corner_hz']/1e3,1)} kHz with "
       f"C<sub>X</sub> = {_f(r['c_x']*1e6,2)} {_MU}F &#8658; L<sub>DM</sub> = <b>{_f(r['l_dm']*1e6,1)} {_MU}H</b> "
       f"({r['dm_stages']} stage); delivered {_f(r['dm_il_db'],0)} dB, margin {_f(r['dm_margin_db'],1)} dB.")
    _W(f"<b>A.3 CM stage:</b> C<sub>Y,total</sub> = {_f(r['c_y_emi_total']*1e9,2)} nF (leakage-bounded) &#8658; "
       f"L<sub>CM</sub> = <b>" + ("&#8734;" if _linf else f"{_f(r['l_cm']*1e3,2)} mH") +
       f"</b> ({r['cm_stages']} stage); delivered {_f(r['cm_il_db'],0)} dB, margin {_f(r['cm_margin_db'],1)} dB.")
    _W(f"<b>A.4 Damping / stability:</b> series-R&#8211;L R<sub>d</sub> = {_f(r['damp_r'],2)} {_OHM}, "
       f"L<sub>d</sub> = {_f(r['damp_l']*1e6,1)} {_MU}H &#8658; Middlebrook margin "
       f"<b>{_f(r['stability_margin_db'],1)} dB</b> at {_f(r['dm_res_hz']/1e3,1)} kHz.")
    _W(f"<b>A.5 Leakage:</b> I<sub>leak</sub> = 2&#960;fVC<sub>Y</sub> = <b>{_f(r['leakage_actual_A']*1e3,2)} mA</b> "
       f"normal / {_f(r['leak_fault_A']*1e3,2)} mA single-fault (limit {_f(r['leakage_limit_A']*1e3,2)} mA).")
    _W(f"<b>A.6 Losses (worst case @ {_f(r['loss_worst_vac'],0)} V):</b> copper = {_f(_cu_w,2)} W, "
       f"total = <b>{_f(r['loss_total_w'],2)} W</b>.")
    annotation(story, "NOTE",
        "Every value above is a calculated baseline from the converter specification and named parasitic "
        "defaults (each reported in the provenance). Confirm the common-mode-choke core (saturation + leakage "
        "inductance, which doubles as DM inductance) and re-run against a measured bare-EUT spectrum before "
        "certification.", CH)


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
