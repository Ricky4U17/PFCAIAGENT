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


# ── narrative worked calculations (model → equation → worked at 90 V and 180 V) ─────────
# These follow the style of the earlier chapters: each loss has a short explanation of the
# model and why it is used, the governing equation, then the substituted numbers at each corner.
def _W(story, txt):
    body(story, txt, CH)


def _bridge_section(story, traces, is_sync):
    _W(story,
       "<b>Model.</b> The bridge rectifies the AC line; at every instant two devices in series carry "
       "the full rectified current i<sub>in</sub>(&#952;) = &#8730;2&#183;I<sub>in,rms</sub>&#183;sin&#952;. "
       "Each drops a <i>current-dependent</i> forward voltage V<sub>f</sub>(i) read from its datasheet "
       "V-I curve — at tens of amps the drop is well above the textbook 0.7 V, so a constant-V<sub>f</sub> "
       "model would understate the loss. We integrate the V<sub>f</sub>(i)&#183;i product over the half "
       "line cycle (both factors vary along the sinusoid) and double it for the conducting pair." +
       (" For the sync-bottom variant the bottom legs are MOSFETs, adding an ohmic R<sub>ds</sub>&#183;i&#178; "
        "term and a small line-frequency gate loss." if is_sync else ""))
    eq_box(story, [r"i_{in}(\theta)=\sqrt{2}\,I_{in,rms}\,\sin\theta",
                   r"P_{bridge}=2\,\overline{\,V_f(i_{in})\,i_{in}\,}"
                   + (r"+\,\overline{\,R_{ds,bot}\,i_{in}^2\,}+P_{g,bot}" if is_sync else "")],
           number="7.3", ch=CH)
    for vac, tr in traces:
        i_in_pk = (2 ** 0.5) * tr["Iin_rms"]; ntop = max(tr["n_top"], 1)
        extra = (f" (top diodes {_f(tr['P_bridge_top'])} W + bottom MOSFETs {_f(tr['P_bridge_bottom'])} W)"
                 if is_sync else "")
        _W(story,
           f"<b>At {vac:.0f} V<sub>AC</sub>:</b> I<sub>in,rms</sub> = {_f(tr['Iin_rms'],3)} A &#8658; "
           f"peak i<sub>in,pk</sub> = &#8730;2&#183;{_f(tr['Iin_rms'],3)} = {_f(i_in_pk,3)} A "
           f"({_f(i_in_pk/ntop,3)} A per device). At that current V<sub>f</sub> &#8776; "
           f"{_f(tr['vf_br_pk'],3)} V (T<sub>j</sub> = {_f(tr['Tj_brT'],0)}{_DEG}C); the cycle-averaged "
           f"conduction loss of the pair is <b>P<sub>bridge</sub> = {_f(tr['P_bridge'])} W</b>{extra}.")


def _mosfet_section(story, traces):
    nch = int(traces[0][1]["Nch"]) if traces else 1

    sub_h(story, "7.4.1", "Conduction loss", CH)
    _W(story,
       "<b>Model.</b> While the MOSFET is on it is a resistor R<sub>ds(on)</sub>, so the loss is the "
       "on-state RMS current squared times that resistance. The on-state RMS current is the "
       "<i>duty-weighted</i> integral of the channel current over the line cycle (the FET conducts only "
       "during the on-time d). R<sub>ds(on)</sub> has a strong positive temperature coefficient "
       "(&#8776; +0.4&#8211;0.5 %/&#176;C for SiC), so we evaluate it at the converged hot junction "
       "temperature — a 25&#176;C value would under-state the loss by 20&#8211;40 %.")
    eq_box(story, [r"I_{FET,rms}=\sqrt{\overline{\,i^2\,d\,}},\qquad R_{ds(on)}(T_j)=R_{ds,25}\,k(T_j)",
                   r"P_{cond}=N_{ch}\,R_{ds(on)}(T_j)\,I_{FET,rms}^2"], number="7.4.1", ch=CH)
    for vac, tr in traces:
        _W(story,
           f"<b>{vac:.0f} V<sub>AC</sub>:</b> R<sub>ds(on)</sub>(T<sub>j</sub>={_f(tr['Tj_fet'],0)}{_DEG}C) = "
           f"{_f(tr['rds_25']*1e3,1)}&#215;{_f(tr['rds_tj_factor'],3)} = {_f(tr['rds_tj']*1e3,1)} m{_OHM}; "
           f"I<sub>FET,rms</sub> = {_f(tr['i_fet_rms_ch'],3)} A &#8658; P<sub>cond</sub> = "
           f"{_f(tr['rds_tj']*1e3,1)}m{_OHM}&#215;({_f(tr['i_fet_rms_ch'],3)})&#178;&#215;{nch} = "
           f"<b>{_f(tr['P_cond_fet_tot'])} W</b>.")

    sub_h(story, "7.4.2", "Switching loss (turn-on + turn-off)", CH)
    _W(story,
       "<b>Model.</b> At hard switching the drain voltage and current overlap during the transition, "
       "dissipating a crossover energy each cycle. Rather than a single datasheet E<sub>sw</sub> figure "
       "(quoted at one R<sub>g</sub>/V<sub>DS</sub>/I that rarely matches the design), we compute "
       "E<sub>on</sub> and E<sub>off</sub> <i>analytically</i> from the actual gate drive: the "
       "current rise/fall times from C<sub>iss</sub>&#183;R<sub>g</sub>&#183;ln(&#183;) and the "
       "Miller-plateau charge J = Q<sub>gd</sub>&#183;V<sub>OUT</sub>/2 (or the C<sub>rss</sub>(V) "
       "integral). This makes E<sub>sw</sub> scale correctly with this design's R<sub>g</sub>, V<sub>g</sub>, "
       "operating current and T<sub>j</sub>. The loss is f<sub>sw</sub> times the cycle-averaged energy.")
    eq_box(story, [r"E_{sw}(i,V_{OUT},T_j)=E_{on}+E_{off},\qquad "
                   r"P_{sw}=N_{ch}\,f_{sw}\,\overline{E_{sw}}"], number="7.4.2", ch=CH)
    for vac, tr in traces:
        _W(story,
           f"<b>{vac:.0f} V<sub>AC</sub>:</b> switching currents (peak of line) i<sub>on</sub>/i<sub>off</sub> = "
           f"{_f(tr['i_on_pk'],2)}/{_f(tr['i_off_pk'],2)} A; per-event E<sub>sw</sub> peaks at "
           f"{_uj(tr['Esw_pk'])} and averages {_uj(tr['Esw_avg'])} over the cycle &#8658; P<sub>sw</sub> = "
           f"{_f(tr['fsw']/1e3,0)}kHz&#215;{_uj(tr['Esw_avg'])}&#215;{nch} = <b>{_f(tr['P_sw_fet_tot'])} W</b>.")

    sub_h(story, "7.4.3", "Output-capacitance loss (E<sub>oss</sub>)", CH)
    _W(story,
       "<b>Model.</b> While off, the MOSFET output capacitance C<sub>oss</sub> charges to V<sub>OUT</sub>; "
       "at the next hard turn-on that stored charge is dumped through the channel and dissipated. We use "
       "the datasheet stored energy E<sub>oss</sub>(V<sub>OUT</sub>) — the &#189;&#8747;V dQ integral of "
       "the strongly non-linear C<sub>oss</sub>, not &#189;C&#183;V&#178; with a fixed C. It depends only "
       "on V<sub>OUT</sub> and f<sub>sw</sub>, so it is essentially line-independent.")
    eq_box(story, [r"P_{oss}=N_{ch}\,f_{sw}\,E_{oss}(V_{OUT})"], number="7.4.3", ch=CH)
    for vac, tr in traces:
        _W(story,
           f"<b>{vac:.0f} V<sub>AC</sub>:</b> E<sub>oss</sub>(V<sub>OUT</sub>={_f(tr['Vo'],0)} V) = "
           f"{_uj(tr['eoss_vo'])} &#8658; P<sub>oss</sub> = {_f(tr['fsw']/1e3,0)}kHz&#215;{_uj(tr['eoss_vo'])}"
           f"&#215;{nch} = <b>{_f(tr['P_oss_tot'])} W</b>.")

    sub_h(story, "7.4.4", "Diode charge dumped into the FET", CH)
    _W(story,
       "<b>Model.</b> At MOSFET turn-on the boost diode is commutated off and its charge is removed "
       "<i>through the FET channel</i>, so this energy heats the MOSFET. For a Si diode it is the "
       "reverse-recovery charge Q<sub>rr</sub> swept out under V<sub>OUT</sub> (&#8776; 85 % of "
       "Q<sub>rr</sub>&#183;V<sub>OUT</sub> to the FET, the rest to the diode). For a SiC Schottky there "
       "is no minority-carrier recovery, but its junction-capacitance charge Q<sub>c</sub> is charged "
       "through the channel, dissipating &#189;&#183;V<sub>OUT</sub>&#183;Q<sub>c</sub>. It is counted "
       "only in CCM (in DCM the diode current is already zero at turn-on).")
    eq_box(story, [r"P_{rr\to FET}=N_{ch}\,f_{sw}\,\frac{1}{2} V_{OUT}\,Q_c\ \mathrm{(SiC)}\quad "
                   r"\mathrm{or}\quad N_{ch}\,f_{sw}\,k\,\overline{Q_{rr}V_{OUT}}\ \mathrm{(Si)}"],
           number="7.4.4", ch=CH)
    for vac, tr in traces:
        if tr["is_sic"]:
            sub = f"&#189;&#215;{_f(tr['Vo'],0)}V&#215;{_nc(tr['qc'])}&#215;{_f(tr['fsw']/1e3,0)}kHz&#215;{nch}"
        else:
            sub = f"&#8776;0.85&#215;{_nc(tr['qrr_eff'])}&#215;{_f(tr['Vo'],0)}V&#215;{_f(tr['fsw']/1e3,0)}kHz&#215;{nch}"
        _W(story,
           f"<b>{vac:.0f} V<sub>AC</sub>:</b> charge into FET = {sub} = <b>{_f(tr['P_rr_fet_tot'])} W</b>.")

    sub_h(story, "7.4.5", "Gate drive + leakage", CH)
    _W(story,
       "<b>Model.</b> Every switching cycle the gate driver moves the total gate charge Q<sub>g</sub> "
       "through the gate-drive voltage V<sub>g</sub>; that Q<sub>g</sub>&#183;V<sub>g</sub> energy is "
       "dissipated in the gate-loop resistance each period. Off-state leakage "
       "(V<sub>OUT</sub>&#183;I<sub>DSS</sub>) is added when a leakage curve is supplied; it is usually "
       "negligible at these temperatures.")
    eq_box(story, [r"P_{gate}=N_{ch}\,f_{sw}\,Q_g\,V_g"], number="7.4.5", ch=CH)
    for vac, tr in traces:
        _W(story,
           f"<b>{vac:.0f} V<sub>AC</sub>:</b> P<sub>gate</sub>+leak = {_f(tr['fsw']/1e3,0)}kHz&#215;"
           f"{_nc(tr['qg'])}&#215;{_f(tr['vg_drive'],0)}V&#215;{nch} = "
           f"<b>{_f(tr['P_gate_tot'] + tr['P_leak_fet_tot'])} W</b>.")

    tot_txt = "; ".join(
        f"{vac:.0f} V &#8594; {_f(tr['P_cond_fet_tot'] + tr['P_sw_fet_tot'] + tr['P_oss_tot'] + tr['P_rr_fet_tot'] + tr['P_gate_tot'] + tr['P_leak_fet_tot'])} W"
        for vac, tr in traces)
    _W(story, f"<b>MOSFET total (all {nch} channels):</b> {tot_txt}. The full 9-point breakdown is Table 7.4.")


def _diode_section(story, traces):
    nch = int(traces[0][1]["Nch"]) if traces else 1
    _W(story,
       "<b>Model.</b> The boost diode conducts the inductor current during the MOSFET off-time, "
       "i<sub>D</sub> = i<sub>ch</sub>&#183;(1&#8722;d). Its conduction loss is the cycle-average of the "
       "current-dependent forward drop V<sub>f</sub>(i,T<sub>j</sub>) times i<sub>D</sub>. For a SiC "
       "Schottky there is no reverse-recovery loss in the diode (its Q<sub>c</sub> is booked to the "
       "MOSFET, &#167; 7.4.4); the only diode switching term is its forward-recovery energy E<sub>fr</sub> "
       "(usually negligible). For a Si diode the diode keeps the smaller (&#8776; 15 %) share of the "
       "Q<sub>rr</sub> recovery energy.")
    eq_box(story, [r"i_D(\theta)=i_{ch}(\theta)\,(1-d(\theta)),\qquad P_{cond}=N_{ch}\,\overline{\,V_f(i_D,T_j)\,i_D\,}",
                   r"P_{sw,D}=N_{ch}\,f_{sw}\,E_{fr}\ \mathrm{(SiC)}\quad\mathrm{or}\quad "
                   r"N_{ch}\,f_{sw}\,(1-k)\,\overline{Q_{rr}V_{OUT}}\ \mathrm{(Si)}"],
           number="7.5", ch=CH)
    for vac, tr in traces:
        sw = (f"forward-recovery only, {_f(tr['P_sw_dio_tot'])} W (Q<sub>c</sub> booked to the FET)"
              if tr["is_sic"] else f"{_f(tr['P_sw_dio_tot'])} W (Q<sub>rr</sub> diode share)")
        _W(story,
           f"<b>{vac:.0f} V<sub>AC</sub>:</b> average diode current {_f(tr['i_d_avg'],3)} A, V<sub>f</sub> "
           f"&#8776; {_f(tr['vf_d_pk'],3)} V (T<sub>j</sub> = {_f(tr['Tj_dio'],0)}{_DEG}C) &#8658; conduction "
           f"{_f(tr['P_cond_dio_tot'])} W, switching {sw}; <b>diode total "
           f"{_f(tr['P_cond_dio_tot'] + tr['P_sw_dio_tot'])} W</b>.")


def _thermal_section(story, traces, thermal):
    tamb = float(thermal.get("t_ambient", 45)); rsa = float(thermal.get("rth_sa", 0.35))
    _W(story,
       "<b>Model.</b> Each device sits on a steady-state thermal-resistance ladder junction &#8594; case "
       "&#8594; heatsink &#8594; ambient. The shared sink rises above ambient by the <i>total</i> "
       "dissipation times R<sub>&#952;,sink-amb</sub>; each junction then rises above the sink by its "
       "<i>own</i> dissipation times (R<sub>&#952;jc</sub>+R<sub>&#952;cs</sub>). The solve is iterated "
       "because R<sub>ds(on)</sub>, V<sub>f</sub> and E<sub>sw</sub> themselves depend on T<sub>j</sub> "
       "— the numbers below are the converged values.")
    eq_box(story, [r"T_{sink}=T_{amb}+P_{\Sigma}\,R_{\theta,sa}",
                   r"T_j=T_{sink}+P_{dev}\,(R_{\theta,jc}+R_{\theta,cs})"], number="7.6", ch=CH)
    for vac, tr in traces:
        _W(story,
           f"<b>{vac:.0f} V<sub>AC</sub>:</b> sink = {_f(tamb,0)}{_DEG}C + "
           f"{_f(tr['Psemi_main'] + tr['P_bridge'],1)}W&#215;{_f(rsa,2)} = {_f(tr['sink_main'],1)}{_DEG}C; "
           f"then T<sub>j,FET</sub> = {_f(tr['Tj_fet'],1)}{_DEG}C, T<sub>j,diode</sub> = "
           f"{_f(tr['Tj_dio'],1)}{_DEG}C, T<sub>j,bridge</sub> = {_f(tr['Tj_brT'],1)}{_DEG}C.")


def build_semiconductor_story(story, design, mosfet, diode, bridge, thermal, tj_limit=None):
    """Append the full Chapter-7 content to `story`."""
    tj_limit = tj_limit or {"fet": 150, "diode": 150, "bridge": 130}
    res = calculate_semiconductor_losses(design, mosfet, diode, bridge, thermal, tj_limit)
    cfg, ref = build_semi_cfg(design, mosfet, diode, bridge, thermal)
    ops, s2, L_phi, iph, L_pts = build_design_ops(design)
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
    L_varies = len({round(float(x) * 1e6, 1) for x in L_pts}) > 1
    if res["consistency"] and res["consistency"]["ok"]:
        annotation(story, "NOTE",
            "Consistency gate: PASS — Vac, P_out, P_in, &#951;, PF, I_in,rms, I_pk and L&#966; match the "
            "approved design at all nine points." + (
                " L&#966; is bias-adjusted per operating point (see the L<sub>&#966;</sub> column)."
                if L_varies else " (L&#966; = %s &#181;H everywhere.)" % _f(L_phi * 1e6, 0)), CH)
    fsw = float(design["fsw"]); vout = float(design["vout"])
    body(story,
        "The total input RMS current follows from the supplied efficiency and power factor; the "
        "per-phase inductor RMS is the Step-5 value (low-frequency + high-frequency ripple components "
        "integrated over the half line cycle). The per-phase peak-to-peak inductor ripple uses the "
        "<b>per-operating-point</b> inductance L<sub>&#966;</sub>(V<sub>AC</sub>): a powder core's "
        "permeability rolls off with DC bias (current), so the inductance is lowest at the "
        "highest-current operating point and recovers toward the no-load value where the bias is "
        "smaller. These are the Chapter-3 bias-adjusted inductances. All currents below use the SAME "
        "equations as Chapters 2 and 5, to three decimals:", CH)
    eq_box(story, [r"I_{in,rms}=\dfrac{P_{out}}{\eta\,V_{AC}\,PF},\qquad "
                   r"I_{\varphi,rms}=\sqrt{\dfrac{1}{\pi}\int_0^{\pi}\left(i_{\varphi}^2+i_{hf}^2\right)d\theta}",
                   r"d(\theta)=1-\dfrac{\sqrt{2}\,V_{AC}\sin\theta}{V_{OUT}},\qquad "
                   r"\Delta I_{L,pp}=\dfrac{V_{in,pk}\,D_{pk}}{L_{\varphi}(V_{AC})\,f_{sw}}"],
           number="7.1", ch=CH)
    data_table(story, "7.1", "Operating Points (identical to Chapters 2, 3 & 5)",
        "Currents from the Step-2 / Step-5 equations (3 decimals). &#916;I<sub>L,pp</sub> uses the "
        "bias-adjusted per-point inductance L<sub>&#966;</sub>(V<sub>AC</sub>) from Chapter 3 — "
        "L<sub>&#966;</sub> is lowest where the peak current (DC bias) is highest and recovers as the "
        "current falls.",
        ["V_AC", "P_out", "&#951; %", "PF", "I_in,rms", "I_&#966;,rms", "&#916;I_L,pp", "L_&#966;"],
        [[f"{s2['Vin_rms'][i]:.0f} V", f"{r['Po']:.0f} W", _f(r['eta_in_%'], 1), _f(r['PF_in'], 4),
          f"{_f(s2['Iin_rms'][i], 3)} A", f"{_f(iph[i], 3)} A",
          f"{_f(s2['Vin_pk'][i] * s2['Dpk'][i] / (L_pts[i] * fsw), 3)} A", f"{_f(L_pts[i] * 1e6, 0)} &#181;H"]
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
    _bridge_section(story, traces, is_sync)
    data_table(story, "7.3", "Bridge Loss vs Line Voltage",
        "Conducting-pair loss at each operating point" + (" (top diodes + bottom MOSFETs)." if is_sync else "."),
        ["V_AC", "I_in,rms", "P_bridge (top)", "P_bridge (bottom)", "P_bridge total"],
        [[f"{r['Vac']:.0f} V", f"{_f(r['Iin_rms'],1)} A", f"{_f(r['P_BRIDGE_top'])} W",
          f"{_f(r['P_BRIDGE_bottom'])} W", f"{_f(r['P_BRIDGE_total'])} W"] for r in rows],
        col_widths=[CW*0.14, CW*0.18, CW*0.22, CW*0.24, CW*0.22], ch=CH)

    # ── 7.4 MOSFET ───────────────────────────────────────────────────────────
    step_h(story, "7.4", "Boost MOSFET Loss", CH)
    annotation(story, "THEORY",
        "The MOSFET loss is the sum of five mechanisms — ohmic conduction, hard-switching crossover, "
        "output-capacitance (E<sub>oss</sub>) dissipation, the diode charge dumped into the FET, and "
        "gate-drive + leakage. Each is modelled below in its own sub-section: the equation we use, why "
        "that model is appropriate, and the worked numbers at the 90 V and 180 V corners.", CH)
    _mosfet_section(story, traces)
    data_table(story, "7.4", "MOSFET Loss Breakdown vs Line Voltage",
        "Per-mechanism MOSFET loss (all channels), at every input voltage.",
        ["V_AC", "Cond", "Switch", "Coss", "RR", "Gate+leak", "FET total"],
        [[f"{r['Vac']:.0f} V", _f(r['P_FET_cond']), _f(r['P_FET_sw']), _f(r['P_FET_coss']),
          _f(r['P_FET_rr']), _f(r['P_gate_driver'] + r['P_FET_leak']), f"{_f(r['P_FET_total'])} W"] for r in rows],
        col_widths=[CW*0.13, CW*0.13, CW*0.14, CW*0.13, CW*0.12, CW*0.17, CW*0.18], ch=CH)

    # ── 7.5 Boost diode ──────────────────────────────────────────────────────
    step_h(story, "7.5", "Boost Diode Loss", CH)
    _diode_section(story, traces)
    data_table(story, "7.5", "Diode Loss vs Line Voltage",
        "Conduction + switching loss of the boost diode(s), at every input voltage.",
        ["V_AC", "Conduction", "Switching", "Diode total"],
        [[f"{r['Vac']:.0f} V", f"{_f(r['P_D_cond'])} W", f"{_f(r['P_D_sw'])} W", f"{_f(r['P_DIODE_total'])} W"]
         for r in rows],
        col_widths=[CW*0.18, CW*0.27, CW*0.27, CW*0.28], ch=CH)

    # ── 7.6 Thermal ──────────────────────────────────────────────────────────
    step_h(story, "7.6", "Thermal Network and Junction Temperatures", CH)
    _thermal_section(story, traces, thermal)
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
