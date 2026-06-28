"""
Chapter 7 — Semiconductor Loss & Thermal (report)
=================================================
Builds the Chapter-7 PDF from the SAME engine + adapter the GUI uses, so the documented
numbers are identical to the page. Losses are reported at EVERY input voltage (all 9
operating points), then rolled up to the worst-case total and reconciled against the
system loss implied by the design efficiency.

Standalone document (like the Chapter-6 control report) — merged after Chapters 1–6.
"""
from __future__ import annotations
import io, os, tempfile

from app.mode_b.doc_report_builder import (
    chapter_splash, step_h, sub_h, body, eq_box, data_table, annotation, CW,
)
from app.mode_b.semiconductor.adapter import (
    calculate_semiconductor_losses, build_semi_cfg, build_design_ops, trace_point,
)

_OHM = "&#937;"; _MU = "&#181;"; _DEG = "&#176;"

CH = 7
_TITLE = "Semiconductor Loss & Thermal Design"


def _img_path(path, width=CW):
    # read the PNG into memory NOW (the temp dir is removed before the doc is built)
    from reportlab.lib.utils import ImageReader
    from reportlab.platypus import Image
    with open(path, "rb") as f:
        data = f.read()
    iw, ih = ImageReader(io.BytesIO(data)).getSize()
    return Image(io.BytesIO(data), width=width, height=ih * (width / iw))


def _f(x, n=2):
    return f"{float(x):.{n}f}"


def _uj(x):
    return f"{float(x) * 1e6:.2f} {_MU}J"


def _nc(x):
    return f"{float(x) * 1e9:.0f} nC"


def build_semiconductor_story(story, design, mosfet, diode, bridge, thermal, tj_limit=None):
    """Append the full Chapter-7 content to `story`."""
    tj_limit = tj_limit or {"fet": 150, "diode": 150, "bridge": 130}
    res = calculate_semiconductor_losses(design, mosfet, diode, bridge, thermal, tj_limit)
    cfg, ref = build_semi_cfg(design, mosfet, diode, bridge, thermal)
    ops, s2, L_phi, iph = build_design_ops(design)
    rows = res["per_point"]; summ = res["summary"]
    meta = ref["parts"]
    is_sync = cfg["bridge"].get("topology") == "sync_bottom"
    # converged intermediate quantities at the worst-case loss point — drives the worked examples
    worst_vac = max(rows, key=lambda r: r["P_SEMI_total"])["Vac"]
    try:
        tr = trace_point(design, mosfet, diode, bridge, thermal, vac=worst_vac)
    except Exception:
        tr = None
    WC = f"worked at the worst-case point, {worst_vac:.0f} V<sub>AC</sub>"

    chapter_splash(story, CH, _TITLE,
        "How much do the power semiconductors dissipate, and do they stay within their "
        "junction-temperature limits across the whole line range?",
        ["7.1 Operating-point basis — the same 9-point grid used by every chapter",
         "7.2 Selected components — bridge, MOSFET, diode (datasheet + application)",
         "7.3 Bridge rectifier loss  ·  7.4 MOSFET loss (every mechanism)  ·  7.5 Boost-diode loss",
         "      each with a step-by-step worked substitution at the worst-case point + the full 9-point sweep",
         "7.6 Thermal network and junction temperatures",
         "7.7 Loss & temperature vs line voltage  ·  7.8 Summary and efficiency cross-check"])

    # ── 7.1 Operating-point basis ────────────────────────────────────────────
    step_h(story, "7.1", "Operating-Point Basis", CH)
    annotation(story, "CONCEPT",
        "Every loss in this chapter is evaluated at the design's nine operating points using the "
        "efficiency, power factor, output power, total input RMS current and per-phase inductance "
        "carried in from the upstream chapters — not re-derived here. A consistency gate checks the "
        "engine's echoed operating point against those upstream values at every point, so the "
        "semiconductor numbers can never diverge from the rest of the design.", CH)
    if res["consistency"] and res["consistency"]["ok"]:
        annotation(story, "NOTE",
            "Consistency gate: PASS — Vac, P_out, P_in, &#951;, PF, I_in,rms, I_pk and L&#966; match the "
            "approved design at all nine points (L_eff = %s &#181;H everywhere)." % _f(L_phi * 1e6, 0), CH)
    body(story,
        "The line current follows from the supplied efficiency and power factor, "
        "I<sub>in,rms</sub> = P<sub>out</sub> / (&#951;&#183;V<sub>AC</sub>&#183;PF); the per-phase "
        "inductor RMS is the value sized in Chapter 3. The duty law is the structural boost relation:", CH)
    eq_box(story, [r"d(\theta)=1-\dfrac{V_{AC}\sqrt{2}\,\sin\theta}{V_{OUT}}",
                   r"I_{in,rms}=\dfrac{P_{out}}{\eta\,V_{AC}\,PF},\quad I_{pk,ch}=\dfrac{\sqrt{2}\,I_{in,rms}}{N_{ch}}"],
           number="7.1", ch=CH)
    data_table(story, "7.1", "Operating Points (carried in from the approved design)",
        "The nine-point grid every chapter shares; the loss engine consumes these verbatim.",
        ["V_AC", "P_out", "&#951; %", "PF", "I_in,rms", "I_ph,rms", "ripple %", "L_eff"],
        [[f"{r['Vac']:.0f} V", f"{r['Po']:.0f} W", _f(r['eta_in_%'], 1), _f(r['PF_in'], 4),
          f"{_f(r['Iin_rms'], 1)} A", f"{_f(iph[i], 2)} A", _f(r['ripple_pk_%'], 1),
          f"{_f(r['L_eff_uH'], 0)} &#181;H"] for i, r in enumerate(rows)],
        col_widths=[CW*0.10, CW*0.12, CW*0.10, CW*0.12, CW*0.14, CW*0.14, CW*0.12, CW*0.16], ch=CH)

    # ── 7.2 Selected components ──────────────────────────────────────────────
    step_h(story, "7.2", "Selected Components", CH)
    def _part(kind, label):
        m = meta.get(kind, {}); p = cfg[kind]
        return [label, m.get("manufacturer", "—") or "—", m.get("part_number", "—") or "—",
                p.get("tech") or p.get("topology") or ("SiC" if p.get("is_sic") else "Si")]
    data_table(story, "7.2", "Confirmed Power Semiconductors",
        "Manufacturer / part number and the technology selected for each block.",
        ["Block", "Manufacturer", "Part number", "Type"],
        [_part("bridge", "Bridge rectifier"), _part("mosfet", "Boost MOSFET"), _part("diode", "Boost diode")],
        col_widths=[CW*0.24, CW*0.26, CW*0.30, CW*0.20], ch=CH)
    annotation(story, "NOTE",
        "Datasheet parameters (R<sub>DS(on)</sub>, V<sub>f</sub> curves, Q<sub>g</sub>, E<sub>oss</sub>, "
        "R<sub>&#952;jc</sub> …) and the application inputs (gate drive, R<sub>g</sub>, R<sub>&#952;cs</sub>, "
        "T<sub>ambient</sub>, R<sub>&#952;sa</sub>) confirmed on the selection screen are used as-is; the "
        "validation gate blocks the calculation until every required field is present.", CH)

    # ── 7.3 Bridge rectifier ─────────────────────────────────────────────────
    step_h(story, "7.3", "Bridge Rectifier Loss", CH)
    body(story,
        ("Synchronous-bottom bridge: the top legs are diodes and the bottom legs are bypass MOSFETs; "
         "two devices conduct the full input current at any instant."
         if is_sync else
         "Plain diode bridge: two diodes conduct the full input current at any instant. The loss is the "
         "forward-conduction loss of the conducting pair, integrated over the line cycle."), CH)
    eq_box(story, [r"P_{bridge}=2\,\overline{\,V_f(i_{in})\,i_{in}\,}"
                   + (r"+\,\overline{\,R_{ds,bot}\,i_{in}^2\,}+P_{g,bot}" if is_sync else "")],
           number="7.3", ch=CH)
    if tr:
        i_in_pk = (2 ** 0.5) * tr["Iin_rms"]
        wrows = [
            ["Peak input current", f"&#8730;2 &#183; I<sub>in,rms</sub> = &#8730;2 &#183; {_f(tr['Iin_rms'],1)} A", f"{_f(i_in_pk,1)} A"],
            [f"V<sub>f</sub> at peak (T<sub>j</sub>={_f(tr['Tj_brT'],0)}{_DEG}C)",
             f"from the V<sub>f</sub>(i) curve at {_f(i_in_pk / max(tr['n_top'],1),1)} A", f"{_f(tr['vf_br_pk'],3)} V"],
        ]
        if is_sync:
            wrows += [["Bottom-FET R<sub>ds</sub>(T<sub>j</sub>)", f"R<sub>ds,bot</sub> at {_f(tr['Tj_brB'],0)}{_DEG}C",
                       f"{_f(tr['rds_bot_tj']*1e3,1)} m{_OHM}"],
                      ["Top diodes (line-avg)", "2 &#183; mean(V<sub>f</sub> &#183; i<sub>in</sub>)", f"{_f(tr['P_bridge_top'])} W"],
                      ["Bottom MOSFETs", "mean(R<sub>ds,bot</sub> &#183; i<sub>in</sub><sup>2</sup>) + gate", f"{_f(tr['P_bridge_bottom'])} W"]]
        else:
            wrows += [["Conduction loss (line-avg)", "2 &#183; mean(V<sub>f</sub> &#183; i<sub>in</sub>) over the cycle",
                       f"{_f(tr['P_bridge_top'])} W"]]
        wrows += [["Bridge total", "&#8721; above", f"{_f(tr['P_bridge'])} W"]]
        data_table(story, "7.3a", "Bridge Loss — Worked Calculation",
            f"Step-by-step substitution ({WC}). Two devices carry the full input current at every instant.",
            ["Quantity", "Substitution", "Value"], wrows,
            col_widths=[CW*0.30, CW*0.46, CW*0.24], ch=CH)
    data_table(story, "7.3", "Bridge Loss vs Line Voltage",
        "Conducting-pair loss at each operating point" + (" (top diodes + bottom MOSFETs)." if is_sync else "."),
        ["V_AC", "I_in,rms", "P_bridge (top)", "P_bridge (bottom)", "P_bridge total"],
        [[f"{r['Vac']:.0f} V", f"{_f(r['Iin_rms'],1)} A", f"{_f(r['P_BRIDGE_top'])} W",
          f"{_f(r['P_BRIDGE_bottom'])} W", f"{_f(r['P_BRIDGE_total'])} W"] for r in rows],
        col_widths=[CW*0.14, CW*0.18, CW*0.22, CW*0.24, CW*0.22], ch=CH)

    # ── 7.4 MOSFET ───────────────────────────────────────────────────────────
    step_h(story, "7.4", "Boost MOSFET Loss", CH)
    annotation(story, "THEORY",
        "The MOSFET loss is the sum of five mechanisms: ohmic conduction, hard-switching crossover "
        "(turn-on + turn-off), output-capacitance (E<sub>oss</sub>) dissipation at hard turn-on, the "
        "share of diode reverse-recovery energy dumped into the FET, and gate-drive + leakage. All are "
        "integrated over the line cycle and multiplied by N<sub>ch</sub>.", CH)
    eq_box(story, [r"P_{cond}=\overline{R_{ds(on)}(T_j,i)\,i^2\,d}",
                   r"P_{sw}=f_{sw}\,\overline{(E_{on}+E_{off})},\quad P_{oss}=f_{sw}\,E_{oss}(V_{OUT})",
                   r"P_{FET}=P_{cond}+P_{sw}+P_{oss}+P_{rr}+P_{gate}+P_{leak}"],
           number="7.4", ch=CH)
    if tr:
        nch = int(tr["Nch"]); fk = tr["fsw"] / 1e3
        fet_tot = (tr["P_cond_fet_tot"] + tr["P_sw_fet_tot"] + tr["P_oss_tot"]
                   + tr["P_rr_fet_tot"] + tr["P_gate_tot"] + tr["P_leak_fet_tot"])
        data_table(story, "7.4a", "MOSFET Loss — Worked Calculation (per mechanism)",
            f"Step-by-step substitution ({WC}); the last column is the all-channel ({nch}-channel) total. "
            f"Intermediate values (R<sub>ds</sub> at T<sub>j</sub>, channel RMS current, switching energy) are the "
            f"engine's own converged numbers, so each line reconciles exactly with the sweep table below.",
            ["Mechanism", "Substitution at the worst-case point", f"Total ({nch} ch)"],
            [["R<sub>ds(on)</sub> at T<sub>j</sub>",
              f"{_f(tr['rds_25']*1e3,1)} m{_OHM} &#215; {_f(tr['rds_tj_factor'],2)} (T<sub>j</sub>={_f(tr['Tj_fet'],0)}{_DEG}C)",
              f"{_f(tr['rds_tj']*1e3,1)} m{_OHM}"],
             ["Channel RMS current", "&#8730;mean(i<sup>2</sup>&#183;d) over the line cycle", f"{_f(tr['i_fet_rms_ch'],2)} A"],
             ["1 · Conduction",
              f"R<sub>ds</sub>(T<sub>j</sub>) &#183; I<sub>rms</sub><sup>2</sup> = {_f(tr['rds_tj']*1e3,1)}m{_OHM} &#215; ({_f(tr['i_fet_rms_ch'],2)}A)<sup>2</sup> &#215; {nch}",
              f"{_f(tr['P_cond_fet_tot'])} W"],
             ["2 · Switching (E<sub>on</sub>+E<sub>off</sub>)",
              f"f<sub>sw</sub> &#183; E<sub>sw,avg</sub> = {_f(fk,0)}kHz &#215; {_uj(tr['Esw_avg'])} &#215; {nch}",
              f"{_f(tr['P_sw_fet_tot'])} W"],
             ["3 · Output cap (E<sub>oss</sub>)",
              f"f<sub>sw</sub> &#183; E<sub>oss</sub>(V<sub>OUT</sub>) = {_f(fk,0)}kHz &#215; {_uj(tr['eoss_vo'])} &#215; {nch}",
              f"{_f(tr['P_oss_tot'])} W"],
             ["4 · Reverse-recovery share",
              "diode recovery energy into the FET (0 for a SiC diode)", f"{_f(tr['P_rr_fet_tot'])} W"],
             ["5 · Gate + leakage",
              f"f<sub>sw</sub> &#183; Q<sub>g</sub> &#183; V<sub>g</sub> = {_f(fk,0)}kHz &#215; {_nc(tr['qg'])} &#215; {_f(tr['vg_drive'],0)}V &#215; {nch}",
              f"{_f(tr['P_gate_tot'] + tr['P_leak_fet_tot'])} W"],
             ["MOSFET total (all channels)", "&#8721; mechanisms 1&#8211;5", f"{_f(fet_tot)} W"]],
            col_widths=[CW*0.24, CW*0.56, CW*0.20], ch=CH)
    data_table(story, "7.4", "MOSFET Loss Breakdown vs Line Voltage",
        "Per-mechanism MOSFET loss (all channels), at every input voltage.",
        ["V_AC", "Cond", "Switch", "Coss", "RR", "Gate+leak", "FET total"],
        [[f"{r['Vac']:.0f} V", _f(r['P_FET_cond']), _f(r['P_FET_sw']), _f(r['P_FET_coss']),
          _f(r['P_FET_rr']), _f(r['P_gate_driver'] + r['P_FET_leak']), f"{_f(r['P_FET_total'])} W"] for r in rows],
        col_widths=[CW*0.13, CW*0.13, CW*0.14, CW*0.13, CW*0.12, CW*0.17, CW*0.18], ch=CH)

    # ── 7.5 Boost diode ──────────────────────────────────────────────────────
    step_h(story, "7.5", "Boost Diode Loss", CH)
    body(story,
        "The boost diode dissipates forward-conduction loss plus a switching term. For a SiC Schottky "
        "the switching term is the capacitive-charge loss &#189;&#183;V<sub>OUT</sub>&#183;Q<sub>c</sub>&#183;f<sub>sw</sub> "
        "(no real reverse recovery); for a Si diode it is the diode's share of the Q<sub>rr</sub> recovery energy.", CH)
    eq_box(story, [r"P_{diode}=\overline{\,V_f(i)\,i_{D}\,}+P_{sw,D}"], number="7.5", ch=CH)
    if tr:
        nch = int(tr["Nch"])
        if tr["is_sic"]:
            sw_sub = (f"&#189; &#183; V<sub>OUT</sub> &#183; Q<sub>c</sub> &#183; f<sub>sw</sub> = "
                      f"&#189; &#215; {_f(tr['Vo'],0)}V &#215; {_nc(tr['qc'])} &#215; {_f(tr['fsw']/1e3,0)}kHz &#215; {nch}")
        else:
            sw_sub = (f"Q<sub>rr</sub> recovery energy share (Q<sub>rr</sub>={_nc(tr['qrr_eff'])}) "
                      f"&#215; V<sub>OUT</sub> &#215; f<sub>sw</sub>")
        data_table(story, "7.5a", "Boost-Diode Loss — Worked Calculation",
            f"Step-by-step substitution ({WC}); last column is the all-channel ({nch}-channel) total.",
            ["Quantity", "Substitution at the worst-case point", f"Total ({nch} ch)"],
            [[f"V<sub>f</sub> at peak I<sub>D</sub> (T<sub>j</sub>={_f(tr['Tj_dio'],0)}{_DEG}C)",
              "from the V<sub>f</sub>(i) curve", f"{_f(tr['vf_d_pk'],3)} V"],
             ["Average diode current / ch", "mean(i<sub>D</sub>) over the line cycle", f"{_f(tr['i_d_avg'],2)} A"],
             ["1 · Conduction", "mean(V<sub>f</sub>(i) &#183; i<sub>D</sub>) &#215; N<sub>ch</sub>", f"{_f(tr['P_cond_dio_tot'])} W"],
             ["2 · Switching", sw_sub, f"{_f(tr['P_sw_dio_tot'])} W"],
             ["Diode total (all channels)", "conduction + switching", f"{_f(tr['P_cond_dio_tot'] + tr['P_sw_dio_tot'])} W"]],
            col_widths=[CW*0.28, CW*0.50, CW*0.22], ch=CH)
    data_table(story, "7.5", "Diode Loss vs Line Voltage",
        "Conduction + switching loss of the boost diode(s), at every input voltage.",
        ["V_AC", "Conduction", "Switching", "Diode total"],
        [[f"{r['Vac']:.0f} V", f"{_f(r['P_D_cond'])} W", f"{_f(r['P_D_sw'])} W", f"{_f(r['P_DIODE_total'])} W"]
         for r in rows],
        col_widths=[CW*0.18, CW*0.27, CW*0.27, CW*0.28], ch=CH)

    # ── 7.6 Thermal ──────────────────────────────────────────────────────────
    step_h(story, "7.6", "Thermal Network and Junction Temperatures", CH)
    body(story,
        "Each device sees a junction&#8594;case&#8594;sink&#8594;ambient path. With the per-device "
        "dissipation and the R<sub>&#952;</sub> chain, the junction temperature is:", CH)
    eq_box(story, [r"T_{sink}=T_{amb}+P_{\Sigma}\,R_{\theta,sa}",
                   r"T_j=T_{sink}+P_{dev}\,(R_{\theta,jc}+R_{\theta,cs})"], number="7.6", ch=CH)
    if tr:
        tamb = float(thermal.get("t_ambient", 45)); rsa = float(thermal.get("rth_sa", 0.35))
        data_table(story, "7.6a", "Junction Temperatures — Worked Calculation",
            f"Step-by-step substitution ({WC}). The main sink carries the MOSFET + diode (+ bridge) dissipation; "
            f"each junction then sits above the sink by its own dissipation times R<sub>&#952;jc</sub>+R<sub>&#952;cs</sub>.",
            ["Quantity", "Substitution at the worst-case point", "Value"],
            [["Main-sink temperature",
              f"{_f(tamb,0)}{_DEG}C + {_f(tr['Psemi_main'] + tr['P_bridge'],1)}W &#215; {_f(rsa,2)} {_DEG}C/W",
              f"{_f(tr['sink_main'],1)} {_DEG}C"],
             ["FET junction T<sub>j</sub>",
              f"{_f(tr['sink_main'],1)} + {_f(tr['P_fet_each'],2)}W &#215; ({_f(tr['rth_jc_fet'],2)}+{_f(tr['rth_cs_fet'],2)})",
              f"{_f(tr['Tj_fet'],1)} {_DEG}C"],
             ["Diode junction T<sub>j</sub>",
              f"{_f(tr['sink_main'],1)} + {_f(tr['P_dio_each'],2)}W &#215; ({_f(tr['rth_jc_dio'],2)}+{_f(tr['rth_cs_dio'],2)})",
              f"{_f(tr['Tj_dio'],1)} {_DEG}C"],
             ["Bridge (top) junction T<sub>j</sub>",
              "T<sub>sink</sub> + P<sub>dev</sub> &#183; (R<sub>&#952;jc</sub>+R<sub>&#952;cs</sub>)",
              f"{_f(tr['Tj_brT'],1)} {_DEG}C"]],
            col_widths=[CW*0.28, CW*0.50, CW*0.22], ch=CH)
    data_table(story, "7.6", "Junction Temperatures vs Line Voltage",
        f"Ambient {_f(thermal.get('t_ambient', 45), 0)} &#176;C, sink R&#952; "
        f"{_f(thermal.get('rth_sa', 0.35), 2)} &#176;C/W. Limits: FET {tj_limit['fet']}, "
        f"diode {tj_limit['diode']}, bridge {tj_limit['bridge']} &#176;C.",
        ["V_AC", "T_sink", "Tj FET", "Tj Diode", "Tj Bridge", "Verdict"],
        [[f"{r['Vac']:.0f} V", f"{_f(r['T_sink_main'],0)} &#176;C", f"{_f(r['Tj_FET'],0)} &#176;C",
          f"{_f(r['Tj_DIODE'],0)} &#176;C", f"{_f(r['Tj_BRIDGE_top'],0)} &#176;C",
          ("PASS" if (r['Tj_FET'] <= tj_limit['fet'] and r['Tj_DIODE'] <= tj_limit['diode']
                      and r['Tj_BRIDGE_top'] <= tj_limit['bridge']) else "CHECK")] for r in rows],
        col_widths=[CW*0.14, CW*0.16, CW*0.16, CW*0.18, CW*0.18, CW*0.18], ch=CH)

    # ── 7.7 Figures ──────────────────────────────────────────────────────────
    step_h(story, "7.7", "Loss and Temperature vs Line Voltage", CH)
    try:
        from app.mode_b.semiconductor import pfc_loss_model as engine, pfc_visualization as viz
        sel = float(cfg["run"]["vac_list"][0])
        with tempfile.TemporaryDirectory() as td:
            files = viz.build_step4_visuals(cfg, selected_vac=sel, vac_list=cfg["run"]["vac_list"],
                                            output_prefix=os.path.join(td, "ch7"), backend=engine,
                                            tj_limits=tj_limit)
            for name, cap in [("losses_vs_vac", "Figure 7-1 — Semiconductor losses vs input voltage."),
                              ("temperatures_vs_vac", "Figure 7-2 — Junction temperatures vs input voltage."),
                              ("loss_breakdown", f"Figure 7-3 — Per-mechanism loss breakdown at {sel:.0f} Vac."),
                              ("waveforms", f"Figure 7-4 — Operating-point waveforms at {sel:.0f} Vac.")]:
                if name in files:
                    story.append(_img_path(files[name]))
                    body(story, cap, CH)
    except Exception:
        annotation(story, "NOTE", "Figures unavailable in this build.", CH)

    # ── 7.8 Summary + cross-check ────────────────────────────────────────────
    step_h(story, "7.8", "Summary and Efficiency Cross-Check", CH)
    wr = max(rows, key=lambda r: r["P_SEMI_total"])   # worst-case operating point
    data_table(story, "7.8", "Worst-Case Semiconductor Loss and Margin",
        f"Worst semiconductor dissipation occurs at {wr['Vac']:.0f} Vac.",
        ["Quantity", "Worst-case value", "Limit / margin"],
        [["MOSFET loss (all ch)", f"{_f(summ['P_FET_max'])} W", "—"],
         ["Diode loss (all ch)", f"{_f(summ['P_DIODE_max'])} W", "—"],
         ["Bridge loss", f"{_f(summ['P_BRIDGE_max'])} W", "—"],
         ["Total semiconductor loss", f"{_f(summ['P_SEMI_max'])} W", f"@ {summ['worst_loss_Vac']:.0f} Vac"],
         ["Tj FET (max)", f"{_f(summ['Tj_FET_max'],0)} &#176;C", f"limit {tj_limit['fet']} &#176;C"],
         ["Tj Diode (max)", f"{_f(summ['Tj_DIODE_max'],0)} &#176;C", f"limit {tj_limit['diode']} &#176;C"],
         ["Tj Bridge (max)", f"{_f(summ['Tj_BRIDGE_max'],0)} &#176;C", f"limit {tj_limit['bridge']} &#176;C"]],
        col_widths=[CW*0.40, CW*0.30, CW*0.30], ch=CH)
    body(story,
        "Because the design efficiency is an input, the total system loss is known "
        "(P<sub>system</sub> = P<sub>out</sub>&#183;(1&#8722;&#951;)/&#951;). The semiconductor share computed "
        "here, subtracted from that, gives the implied non-semiconductor remainder (inductor + capacitor "
        "+ control) — a cross-check against the Chapter 3/4/5 budgets:", CH)
    eq_box(story, [r"P_{other}=P_{system}-P_{semi}=\dfrac{P_{out}(1-\eta)}{\eta}-P_{semi}"],
           number="7.8", ch=CH)
    data_table(story, "7.8b", "Loss Budget Cross-Check vs Line Voltage",
        "System loss from the supplied efficiency, the semiconductor share, and the implied remainder.",
        ["V_AC", "System loss", "Semiconductor", "Implied other"],
        [[f"{r['Vac']:.0f} V", f"{_f(r['P_SYSTEM_total'],1)} W", f"{_f(r['P_SEMI_total'],1)} W",
          f"{_f(r['P_OTHER_implied'],1)} W"] for r in rows],
        col_widths=[CW*0.18, CW*0.27, CW*0.27, CW*0.28], ch=CH)


def _doc(target):
    from reportlab.platypus import SimpleDocTemplate
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    return SimpleDocTemplate(target, pagesize=A4, leftMargin=20*mm, rightMargin=20*mm,
                             topMargin=18*mm, bottomMargin=18*mm, title="Chapter 7 — " + _TITLE)


def build_semiconductor_report(design, mosfet, diode, bridge, thermal, tj_limit=None) -> bytes:
    """Standalone Chapter-7 PDF (merged after Chapters 1–6)."""
    from reportlab.platypus import PageBreak
    story = []
    build_semiconductor_story(story, design, mosfet, diode, bridge, thermal, tj_limit)
    while story and isinstance(story[0], PageBreak):   # chapter_splash leads with a PageBreak
        story.pop(0)
    buf = io.BytesIO()
    _doc(buf).build(story)
    return buf.getvalue()
