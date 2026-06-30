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


# ── per-operating-point worked-calculation tables (emitted at 90 V and 180 V) ──────────
def _bridge_worked(story, tr, vac, tid, is_sync):
    i_in_pk = (2 ** 0.5) * tr["Iin_rms"]; ntop = max(tr["n_top"], 1)
    wrows = [
        ["<b>Step 1 — operating currents</b>", "", ""],
        ["RMS line current (Table 7.1)", "carried in from the grid", f"{_f(tr['Iin_rms'],3)} A"],
        ["Peak line current", f"i<sub>in,pk</sub> = &#8730;2 &#183; {_f(tr['Iin_rms'],3)} A", f"{_f(i_in_pk,3)} A"],
        ["Per-device current", f"i<sub>in,pk</sub> / {ntop} device(s)", f"{_f(i_in_pk/ntop,3)} A"],
        ["<b>Step 2 — device parameter at T<sub>j</sub></b>", "", ""],
        [f"V<sub>f</sub> at peak (T<sub>j</sub>={_f(tr['Tj_brT'],0)}{_DEG}C)",
         f"V<sub>f</sub>(i) curve at {_f(i_in_pk/ntop,3)} A", f"{_f(tr['vf_br_pk'],3)} V"],
    ]
    if is_sync:
        wrows += [["Bottom-FET R<sub>ds</sub>(T<sub>j</sub>)", f"R<sub>ds,bot</sub> at {_f(tr['Tj_brB'],0)}{_DEG}C",
                   f"{_f(tr['rds_bot_tj']*1e3,1)} m{_OHM}"],
                  ["<b>Step 3 — loss</b>", "", ""],
                  ["Top diodes (line-avg)", "2 &#183; mean(V<sub>f</sub>(i<sub>in</sub>) &#183; i<sub>in</sub>)", f"{_f(tr['P_bridge_top'])} W"],
                  ["Bottom MOSFETs", "mean(R<sub>ds,bot</sub> &#183; i<sub>in</sub><sup>2</sup>) + gate", f"{_f(tr['P_bridge_bottom'])} W"]]
    else:
        wrows += [["<b>Step 3 — loss</b>", "", ""],
                  ["Conduction (2 devices, line-avg)", "2 &#183; mean(V<sub>f</sub>(i<sub>in</sub>) &#183; i<sub>in</sub>) over the half cycle",
                   f"{_f(tr['P_bridge_top'])} W"]]
    wrows += [["<b>Bridge total</b>", "&#8721; Step 3", f"<b>{_f(tr['P_bridge'])} W</b>"]]
    data_table(story, tid, f"Bridge Loss — Step-by-Step at {vac:.0f} V<sub>AC</sub>",
        "Current &#8594; device parameter &#8594; loss. Two devices carry the full input current at every instant.",
        ["Quantity", "Substitution", "Value"], wrows,
        col_widths=[CW*0.32, CW*0.44, CW*0.24], ch=CH)


def _mosfet_worked(story, tr, vac, tid):
    nch = int(tr["Nch"]); fk = tr["fsw"] / 1e3
    fet_tot = (tr["P_cond_fet_tot"] + tr["P_sw_fet_tot"] + tr["P_oss_tot"]
               + tr["P_rr_fet_tot"] + tr["P_gate_tot"] + tr["P_leak_fet_tot"])
    mech4 = ((f"SiC diode Q<sub>c</sub> at FET turn-on: &#189;&#183;V<sub>OUT</sub>&#183;Q<sub>c</sub>&#183;f<sub>sw</sub> = "
              f"&#189;&#215;{_f(tr['Vo'],0)}V&#215;{_nc(tr['qc'])}&#215;{_f(fk,0)}kHz&#215;{nch}") if tr['is_sic']
             else "Si diode reverse-recovery energy share into the FET")
    data_table(story, tid, f"MOSFET Loss — Step-by-Step at {vac:.0f} V<sub>AC</sub>",
        f"Operating currents &#8594; T<sub>j</sub>-adjusted parameters &#8594; each loss mechanism; last "
        f"column is the all-channel ({nch}-channel) total (reconciles with the sweep table).",
        ["Quantity", "Substitution", f"Value / total ({nch} ch)"],
        [["<b>Step 1 — operating currents</b>", "", ""],
         ["Channel peak current", f"&#8730;2&#183;I<sub>in,rms</sub>/N<sub>ch</sub> = &#8730;2&#183;{_f(tr['Iin_rms'],3)}/{nch}", f"{_f(tr['Ipk_ch'],3)} A"],
         ["Channel RMS (on-state)", "I<sub>FET,rms</sub> = &#8730;mean(i<sup>2</sup>&#183;d) over the line cycle", f"{_f(tr['i_fet_rms_ch'],3)} A"],
         ["Turn-on / turn-off current", "i at the switching instants (peak of line)", f"{_f(tr['i_on_pk'],2)} / {_f(tr['i_off_pk'],2)} A"],
         ["<b>Step 2 — parameters at T<sub>j</sub></b>", "", ""],
         ["R<sub>ds(on)</sub> at T<sub>j</sub>",
          f"{_f(tr['rds_25']*1e3,1)} m{_OHM} &#215; {_f(tr['rds_tj_factor'],3)} (T<sub>j</sub>={_f(tr['Tj_fet'],0)}{_DEG}C)",
          f"{_f(tr['rds_tj']*1e3,1)} m{_OHM}"],
         ["Switching energy / event", f"E<sub>on</sub>+E<sub>off</sub> at peak {_uj(tr['Esw_pk'])}; cycle-avg", f"{_uj(tr['Esw_avg'])}"],
         ["Output-cap energy", f"E<sub>oss</sub>(V<sub>OUT</sub>={_f(tr['Vo'],0)} V)", f"{_uj(tr['eoss_vo'])}"],
         ["<b>Step 3 — per-mechanism loss (&#215; N<sub>ch</sub>)</b>", "", ""],
         ["1 · Conduction",
          f"R<sub>ds</sub>(T<sub>j</sub>)&#183;I<sub>FET,rms</sub><sup>2</sup> = {_f(tr['rds_tj']*1e3,1)}m{_OHM}&#215;({_f(tr['i_fet_rms_ch'],3)})<sup>2</sup>&#215;{nch}",
          f"{_f(tr['P_cond_fet_tot'])} W"],
         ["2 · Switching (E<sub>on</sub>+E<sub>off</sub>)",
          f"f<sub>sw</sub>&#183;E<sub>sw,avg</sub> = {_f(fk,0)}kHz&#215;{_uj(tr['Esw_avg'])}&#215;{nch}",
          f"{_f(tr['P_sw_fet_tot'])} W"],
         ["3 · Output cap (E<sub>oss</sub>)",
          f"f<sub>sw</sub>&#183;E<sub>oss</sub> = {_f(fk,0)}kHz&#215;{_uj(tr['eoss_vo'])}&#215;{nch}",
          f"{_f(tr['P_oss_tot'])} W"],
         ["4 · Diode charge into FET", mech4, f"{_f(tr['P_rr_fet_tot'])} W"],
         ["5 · Gate + leakage",
          f"f<sub>sw</sub>&#183;Q<sub>g</sub>&#183;V<sub>g</sub> = {_f(fk,0)}kHz&#215;{_nc(tr['qg'])}&#215;{_f(tr['vg_drive'],0)}V&#215;{nch}",
          f"{_f(tr['P_gate_tot'] + tr['P_leak_fet_tot'])} W"],
         ["<b>MOSFET total (all channels)</b>", "&#8721; mechanisms 1&#8211;5", f"<b>{_f(fet_tot)} W</b>"]],
        col_widths=[CW*0.26, CW*0.52, CW*0.22], ch=CH)


def _diode_worked(story, tr, vac, tid):
    nch = int(tr["Nch"])
    if tr["is_sic"]:
        sw_sub = "forward-recovery E<sub>fr</sub> only &#8212; Q<sub>c</sub> is booked to the MOSFET turn-on (&#167; 7.4)"
        sw_param = ["Capacitive charge Q<sub>c</sub> &#8594; FET", "SiC: Q<sub>c</sub> dissipates in the MOSFET, not the diode", _nc(tr['qc'])]
    else:
        sw_sub = f"f<sub>sw</sub>&#183;Q<sub>rr</sub>&#183;V<sub>OUT</sub> share (Q<sub>rr</sub>={_nc(tr['qrr_eff'])})"
        sw_param = ["Recovery charge Q<sub>rr</sub>", "Si diode (diode-side share)", _nc(tr['qrr_eff'])]
    data_table(story, tid, f"Boost-Diode Loss — Step-by-Step at {vac:.0f} V<sub>AC</sub>",
        f"Operating current &#8594; T<sub>j</sub>-adjusted parameters &#8594; loss; last column is the "
        f"all-channel ({nch}-channel) total.",
        ["Quantity", "Substitution", f"Value / total ({nch} ch)"],
        [["<b>Step 1 — operating current</b>", "", ""],
         ["Average diode current / ch", "i<sub>D</sub> = i<sub>ch</sub>(1&#8722;d); mean over the line cycle", f"{_f(tr['i_d_avg'],3)} A"],
         ["<b>Step 2 — parameters at T<sub>j</sub></b>", "", ""],
         [f"V<sub>f</sub> at peak I<sub>D</sub> (T<sub>j</sub>={_f(tr['Tj_dio'],0)}{_DEG}C)",
          "from the V<sub>f</sub>(i) curve", f"{_f(tr['vf_d_pk'],3)} V"],
         sw_param,
         ["<b>Step 3 — loss (&#215; N<sub>ch</sub>)</b>", "", ""],
         ["1 · Conduction", "mean(V<sub>f</sub>(i<sub>D</sub>)&#183;i<sub>D</sub>) &#215; N<sub>ch</sub>", f"{_f(tr['P_cond_dio_tot'])} W"],
         ["2 · Switching", sw_sub, f"{_f(tr['P_sw_dio_tot'])} W"],
         ["<b>Diode total (all channels)</b>", "conduction + switching", f"<b>{_f(tr['P_cond_dio_tot'] + tr['P_sw_dio_tot'])} W</b>"]],
        col_widths=[CW*0.28, CW*0.50, CW*0.22], ch=CH)


def _thermal_worked(story, tr, vac, tid, thermal):
    tamb = float(thermal.get("t_ambient", 45)); rsa = float(thermal.get("rth_sa", 0.35))
    data_table(story, tid, f"Junction Temperatures — Step-by-Step at {vac:.0f} V<sub>AC</sub>",
        "Main sink carries the MOSFET + diode (+ bridge) dissipation; each junction sits above the sink "
        "by its own dissipation &#215; (R<sub>&#952;jc</sub>+R<sub>&#952;cs</sub>).",
        ["Quantity", "Substitution", "Value"],
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


def build_semiconductor_story(story, design, mosfet, diode, bridge, thermal, tj_limit=None):
    """Append the full Chapter-7 content to `story`."""
    tj_limit = tj_limit or {"fet": 150, "diode": 150, "bridge": 130}
    res = calculate_semiconductor_losses(design, mosfet, diode, bridge, thermal, tj_limit)
    cfg, ref = build_semi_cfg(design, mosfet, diode, bridge, thermal)
    ops, s2, L_phi, iph = build_design_ops(design)
    rows = res["per_point"]; summ = res["summary"]
    meta = ref["parts"]
    is_sync = cfg["bridge"].get("topology") == "sync_bottom"
    # Converged intermediate quantities at the two requested corners (low-line 90 V and the
    # mid-line 180 V worst case). The worked step-by-step tables are emitted at BOTH points;
    # the 9-point sweep tables follow. Pick the grid points closest to 90 and 180.
    vac_list = [float(v) for v in ops[:, 0]]
    _closest = lambda t: min(vac_list, key=lambda v: abs(v - t))
    worked_vacs = sorted({_closest(90.0), _closest(180.0)})
    traces = []
    for v in worked_vacs:
        try:
            traces.append((v, trace_point(design, mosfet, diode, bridge, thermal, vac=v)))
        except Exception:
            pass

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
            "approved design at all nine points (L&#966; = %s &#181;H everywhere)." % _f(L_phi * 1e6, 0), CH)
    fsw = float(design["fsw"]); vout = float(design["vout"])
    body(story,
        "The total input RMS current follows from the supplied efficiency and power factor; the "
        "per-phase inductor RMS is the Step-5 value (low-frequency + high-frequency ripple components "
        "integrated over the half line cycle); the per-phase peak-to-peak inductor ripple and the "
        "inductance L<sub>&#966;</sub> are the Chapter-3 quantities. All currents below use the SAME "
        "equations as Chapters 2 and 5, to three decimals:", CH)
    eq_box(story, [r"I_{in,rms}=\dfrac{P_{out}}{\eta\,V_{AC}\,PF},\qquad "
                   r"I_{\varphi,rms}=\sqrt{\dfrac{1}{\pi}\int_0^{\pi}\left(i_{\varphi}^2+i_{hf}^2\right)d\theta}",
                   r"d(\theta)=1-\dfrac{\sqrt{2}\,V_{AC}\sin\theta}{V_{OUT}},\qquad "
                   r"\Delta I_{L,pp}=\dfrac{V_{in,pk}\,D_{pk}}{L_{\varphi}\,f_{sw}}"],
           number="7.1", ch=CH)
    data_table(story, "7.1", "Operating Points (identical to Chapters 2, 3 & 5)",
        "Currents from the Step-2 / Step-5 equations (3 decimals). &#916;I<sub>L,pp</sub> and "
        "L<sub>&#966;</sub> use the Chapter-3 formula and inductance, so the low-line &#916;I<sub>L,pp</sub> "
        "equals the Chapter-3 headline value.",
        ["V_AC", "P_out", "&#951; %", "PF", "I_in,rms", "I_&#966;,rms", "&#916;I_L,pp", "L_&#966;"],
        [[f"{s2['Vin_rms'][i]:.0f} V", f"{r['Po']:.0f} W", _f(r['eta_in_%'], 1), _f(r['PF_in'], 4),
          f"{_f(s2['Iin_rms'][i], 3)} A", f"{_f(iph[i], 3)} A",
          f"{_f(s2['Vin_pk'][i] * s2['Dpk'][i] / (L_phi * fsw), 3)} A", f"{_f(L_phi * 1e6, 0)} &#181;H"]
         for i, r in enumerate(rows)],
        col_widths=[CW*0.10, CW*0.12, CW*0.09, CW*0.11, CW*0.15, CW*0.15, CW*0.14, CW*0.13], ch=CH)

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
    body(story,
        "The rectified line current i<sub>in</sub>(&#952;) = &#8730;2&#183;I<sub>in,rms</sub>&#183;sin&#952; flows "
        "through two series devices at every instant. The conduction loss is the forward-voltage drop "
        "V<sub>f</sub>(i) times the current, averaged over the half line cycle and multiplied by the two "
        "conducting devices. The worked calculation below goes current &#8594; device parameter &#8594; loss.", CH)
    eq_box(story, [r"i_{in}(\theta)=\sqrt{2}\,I_{in,rms}\,\sin\theta",
                   r"P_{bridge}=2\,\overline{\,V_f(i_{in})\,i_{in}\,}"
                   + (r"+\,\overline{\,R_{ds,bot}\,i_{in}^2\,}+P_{g,bot}" if is_sync else "")],
           number="7.3", ch=CH)
    for (vac, t), suf in zip(traces, "abcd"):
        _bridge_worked(story, t, vac, f"7.3{suf}", is_sync)
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
        "diode charge dumped into the FET at turn-on (a Si diode's reverse-recovery energy, or a SiC "
        "Schottky's junction-capacitance charge Q<sub>c</sub> &#8212; both are charged through the FET "
        "channel and so heat the MOSFET), and gate-drive + leakage. All are integrated over the line "
        "cycle and multiplied by N<sub>ch</sub>.", CH)
    eq_box(story, [r"I_{ch,pk}=\dfrac{\sqrt{2}\,I_{in,rms}}{N_{ch}},\quad "
                   r"I_{FET,rms}=\sqrt{\overline{\,i^2\,d\,}},\quad R_{ds(on)}(T_j)=R_{ds,25}\,k(T_j)",
                   r"P_{cond}=R_{ds(on)}(T_j)\,I_{FET,rms}^2,\quad "
                   r"P_{sw}=f_{sw}\,\overline{(E_{on}+E_{off})},\quad P_{oss}=f_{sw}\,E_{oss}(V_{OUT})",
                   r"P_{FET}=N_{ch}\,(P_{cond}+P_{sw}+P_{oss}+P_{rr}+P_{gate}+P_{leak})"],
           number="7.4", ch=CH)
    for (vac, t), suf in zip(traces, "abcd"):
        _mosfet_worked(story, t, vac, f"7.4{suf}")
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
        "there is no minority-carrier reverse recovery; its junction-capacitance charge Q<sub>c</sub> is "
        "charged through the MOSFET at turn-on, so that loss is booked to the MOSFET (&#167; 7.4) and the "
        "diode's own switching term is just its forward-recovery energy E<sub>fr</sub> (often "
        "negligible). For a Si diode the switching term is the diode-side share of the Q<sub>rr</sub> "
        "recovery energy (the larger share goes to the FET).", CH)
    eq_box(story, [r"i_D(\theta)=i_{ch}(\theta)\,(1-d(\theta)),\quad "
                   r"P_{cond}=\overline{\,V_f(i_D,T_j)\,i_{D}\,}",
                   r"P_{sw,D}=f_{sw}\,E_{fr}\ \mathrm{(SiC,\ Q_c\ booked\ to\ FET)}\quad \mathrm{or}\quad "
                   r"f_{sw}\,(1-k)\,\overline{Q_{rr}\,V_{OUT}}\ \mathrm{(Si)}"],
           number="7.5", ch=CH)
    for (vac, t), suf in zip(traces, "abcd"):
        _diode_worked(story, t, vac, f"7.5{suf}")
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
    for (vac, t), suf in zip(traces, "abcd"):
        _thermal_worked(story, t, vac, f"7.6{suf}", thermal)
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
