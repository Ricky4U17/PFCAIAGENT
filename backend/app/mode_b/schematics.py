"""
app/mode_b/schematics.py — SchemDraw-rendered circuit schematics for the report.

Each builder returns a ReportLab Image flowable (PNG rendered through SchemDraw's
matplotlib backend) sized to the document content width, so schematics drop into
the report story exactly like the matplotlib Bode figures.

Figures provided:
  • type2_ota_compensator(...)  — Fig 10A, the inner-loop Type-II OTA network.
"""
from __future__ import annotations
import io

import matplotlib
matplotlib.use("Agg")
import schemdraw
import schemdraw.elements as elm

from app.mode_b.doc_report_builder import CW

schemdraw.use("matplotlib")


def _drawing_to_image(d, max_frac=0.74):
    """Render a SchemDraw drawing to a ReportLab Image, capped to a fraction of CW."""
    from reportlab.lib.utils import ImageReader
    from reportlab.platypus import Image
    png = d.get_imagedata("png")
    buf = io.BytesIO(png)
    iw, ih = ImageReader(buf).getSize()
    buf.seek(0)
    w = CW * max_frac
    h = ih * (w / iw)
    return Image(buf, width=w, height=h)


def type2_ota_compensator(ric_k=120.0, cic1_nf=1.3, cic2_pf=51.0,
                          fz_hz=1020.0, fp_khz=26.0, gmi_us=88.0):
    """Fig 10A — Type-II OTA current-loop compensator.

    OTA (transconductance G_MI) output drives a network to ground: R_IC in series
    with C_IC1 (integrator + compensating zero) in parallel with C_IC2 (HF pole).
    All component values are passed in from the calc agent.
    """
    d = schemdraw.Drawing(show=False)
    d.config(unit=2.4, fontsize=11)

    op = elm.Opamp(leads=True)
    d += op
    d += elm.Label().at(op.center).label("OTA\nG$_{MI}$ = %g µS" % gmi_us, ofst=(-0.1, 0))

    # inputs
    d += elm.Line().left().at(op.in2).length(0.5)
    d += elm.Dot(open=True).label("V$_{REF}$", loc="left")
    d += elm.Line().left().at(op.in1).length(0.5)
    d += elm.Dot(open=True).label("FB", loc="left")

    # output node (IEAO)
    d += elm.Line().right().at(op.out).length(1.1)
    node = d.here
    d += elm.Dot().label("IEAO", loc="top", ofst=(0, 0.15))

    # branch B — C_IC2 (the HF pole), label to the LEFT to clear branch A
    d += elm.Capacitor().down().at(node).label("C$_{IC2}$\n%g pF" % cic2_pf, loc="left")
    d += elm.Line().down().length(d.unit)        # drop to the shared bottom rail
    bot_b = d.here

    # branch A — R_IC + C_IC1 (integrator + zero), parallel to C_IC2
    d += elm.Line().right().at(node).length(1.7)
    d += elm.Resistor().down().label("R$_{IC}$\n%g kΩ" % ric_k)
    d += elm.Capacitor().down().label("C$_{IC1}$\n%g nF" % cic1_nf)
    bot_a = d.here

    # shared bottom rail + single ground
    d += elm.Line().left().at(bot_a).to(bot_b)
    d += elm.Ground().at(bot_b)

    return _drawing_to_image(d)


def type3_ota_compensator(r2_k=143.0, r3_m=8.66, c1_nf=390.0, c2_nf=1.1, c3_nf=24.0,
                          r1_m=3.63, r4_k=23.2, gmv_us=100.0):
    """Fig 14A — Type-III OTA voltage-loop compensator (SLVA662, Method B).

    Voltage OTA (G_MV) senses the bus through the R1/R4 divider. R2-C1 set the first
    zero + integrator, C3 adds the first HF pole, and the R3-C2 branch (across R1)
    provides the second zero/pole pair. All values passed in from the calc agent.
    """
    d = schemdraw.Drawing(show=False)
    d.config(unit=2.2, fontsize=10.5)

    # ── divider column R1 (V_O → FB), drawn 2 units tall so the parallel ──────
    # ── R3-C2 feed-forward column (also 2 units) lines up top and bottom ──────
    d += elm.Dot(open=True).label("V$_O$", loc="right")
    vo = d.here
    d += elm.Resistor().down().at(vo).label("R1\n%g MΩ" % r1_m)
    d += elm.Line().down().length(d.unit)
    fb = d.here
    d += elm.Dot().label("FB", loc="right", ofst=(0.05, 0))
    d += elm.Resistor().down().at(fb).label("R4\n%g kΩ" % r4_k, loc="right")
    d += elm.Ground()

    # R3-C2 feed-forward across R1 (Method B): equal-height column to the left
    d += elm.Line().left().at(vo).length(1.5)
    top_b = d.here
    d += elm.Resistor().down().at(top_b).label("R3\n%g MΩ" % r3_m)
    d += elm.Capacitor().down().label("C2\n%g nF" % c2_nf)
    d += elm.Line().right().to(fb)          # bottoms align with FB → clean tie

    # ── OTA to the right; FB → inverting input, V_REF → non-inverting ─────────
    op = elm.Opamp(leads=True).right().anchor("in1").at((fb[0] + 2.0, fb[1]))
    d += op
    d += elm.Line().at(fb).to(op.in1)
    d += elm.Line().left().at(op.in2).length(0.5)
    d += elm.Dot(open=True).label("V$_{REF}$", loc="left")
    d += elm.Label().at(op.center).label("OTA\nG$_{MV}$ = %g µS" % gmv_us, ofst=(-0.1, 0))

    # ── output compensation network: C3 ∥ (R2 + C1) to ground ────────────────
    d += elm.Line().right().at(op.out).length(1.0)
    comp = d.here
    d += elm.Dot().label("COMP", loc="top", ofst=(0, 0.15))
    d += elm.Capacitor().down().at(comp).label("C3\n%g nF" % c3_nf, loc="left")
    d += elm.Line().down().length(d.unit)
    bot_b = d.here
    d += elm.Line().right().at(comp).length(1.6)
    d += elm.Resistor().down().label("R2\n%g kΩ" % r2_k)
    d += elm.Capacitor().down().label("C1\n%g nF" % c1_nf)
    d += elm.Line().left().at(d.here).to(bot_b)
    d += elm.Ground().at(bot_b)

    return _drawing_to_image(d, max_frac=0.95)


def type2_voltage_compensator(r2_k=143.0, c1_nf=390.0, c3_nf=24.0,
                              r1_m=3.63, r4_k=23.2, gmv_us=100.0):
    """Fig 14A (Type-II variant) — OTA Type-II voltage-loop compensator.

    Same as the Type-III network but without the R3-C2 feed-forward branch:
    OTA (G_MV) senses the bus through R1/R4; R2-C1 set the integrator + zero and
    C3 adds the high-frequency pole. Used when the designer selects a Type-II
    voltage compensator in the GUI.
    """
    d = schemdraw.Drawing(show=False)
    d.config(unit=2.2, fontsize=10.5)

    d += elm.Dot(open=True).label("V$_O$", loc="right")
    vo = d.here
    d += elm.Resistor().down().at(vo).label("R1\n%g MΩ" % r1_m)
    fb = d.here
    d += elm.Dot().label("FB", loc="right", ofst=(0.05, 0))
    d += elm.Resistor().down().at(fb).label("R4\n%g kΩ" % r4_k, loc="right")
    d += elm.Ground()

    op = elm.Opamp(leads=True).right().anchor("in1").at((fb[0] + 2.0, fb[1]))
    d += op
    d += elm.Line().at(fb).to(op.in1)
    d += elm.Line().left().at(op.in2).length(0.5)
    d += elm.Dot(open=True).label("V$_{REF}$", loc="left")
    d += elm.Label().at(op.center).label("OTA\nG$_{MV}$ = %g µS" % gmv_us, ofst=(-0.1, 0))

    d += elm.Line().right().at(op.out).length(1.0)
    comp = d.here
    d += elm.Dot().label("COMP", loc="top", ofst=(0, 0.15))
    d += elm.Capacitor().down().at(comp).label("C3\n%g nF" % c3_nf, loc="left")
    d += elm.Line().down().length(d.unit)
    bot_b = d.here
    d += elm.Line().right().at(comp).length(1.6)
    d += elm.Resistor().down().label("R2\n%g kΩ" % r2_k)
    d += elm.Capacitor().down().label("C1\n%g nF" % c1_nf)
    d += elm.Line().left().at(d.here).to(bot_b)
    d += elm.Ground().at(bot_b)
    return _drawing_to_image(d, max_frac=0.82)


def _fmt_ohm(x):
    try:
        x = float(x)
    except Exception:
        return "—"
    if x >= 1e6:  return f"{x/1e6:g} MΩ"
    if x >= 1e3:  return f"{x/1e3:g} kΩ"
    return f"{x:g} Ω"


def _fmt_cap(x):
    try:
        x = float(x)
    except Exception:
        return "—"
    if x >= 1e-6:  return f"{x*1e6:g} µF"
    if x >= 1e-9:  return f"{x*1e9:g} nF"
    return f"{x*1e12:g} pF"


def fan9672_application_schematic(v, is_high=False, max_frac=1.0, _resolved=None):
    """Full FAN9672 (LQFP-32) application schematic — IC body + every external pin network —
    rendered with matplotlib for the report (white-page theme). Component values are identical at
    both line ranges; only the mode-dependent items differ with `is_high`: the R_IAC series count
    (FR 3×2 MΩ / HV 6×2 MΩ), the VIR mode threshold, and the title/mode labels. `v` is a dict of
    component values + this line's operating annotations; missing keys fall back to fixed-practice
    defaults so the figure always renders. Returns a ReportLab Image sized to the content width.

    `_resolved`, if given a dict, records what each key ACTUALLY resolved to and whether it came
    from `v` or from a fixed-practice default. The values are drawn into a raster image, so nothing
    downstream can read them back — which is how R_RLPK sat at a defaulted 15 kOhm while the BOM
    and Section 6.3.2 both said 12.1 (C235). This makes the drawn values assertable without OCR;
    `tests/test_schematic_values.py` is the consumer."""
    import matplotlib.pyplot as plt
    from reportlab.lib.utils import ImageReader
    from reportlab.platypus import Image

    def g(k, d=None):
        # A key present-but-None must fall back to the default, not propagate None into the
        # formatters: threading a value through from an engine that did not compute it would
        # otherwise render "None" on a schematic a designer might build from.
        val = v.get(k) if isinstance(v, dict) else None
        defaulted = val is None
        if defaulted:
            val = d
        if _resolved is not None:
            _resolved[k] = {"value": val, "defaulted": defaulted, "default": d}
        return val
    fo, fc = _fmt_ohm, _fmt_cap
    mode_lo = not is_high
    # ── colours (light theme for the printed page) ───────────────────────────
    WIRE, ICF, ICE = "#54648a", "#eef2fa", "#2c5aa0"
    PINc, VALc, NODEc, MINc, NDc = "#1a3a6b", "#b45309", "#54648a", "#6b7a8d", "#0f7a4f"
    fig, ax = plt.subplots(figsize=(11.0, 7.3))
    ax.set_xlim(30, 1500); ax.set_ylim(990, 20)     # SVG coords (y-down)
    ax.axis("off")

    def W(x1, y1, x2, y2):
        ax.plot([x1, x2], [y1, y2], color=WIRE, lw=1.0, solid_capstyle="round", zorder=1)
    def T(x, y, t, cls="v", a="center"):
        col = {"v": VALc, "p": PINc, "n": NDc, "t": MINc}.get(cls, PINc)
        fs = {"p": 8.0, "num": 6.6, "t": 7.2, "n": 8.0}.get(cls, 8.4)
        fw = "bold" if cls in ("v", "p") else "normal"
        ha = {"start": "left", "end": "right", "middle": "center"}.get(a, a)
        ax.text(x, y, str(t), color=col, fontsize=fs, fontweight=fw, ha=ha, va="center", zorder=4)
    def NODE(x, y):
        ax.plot(x, y, "o", ms=2.6, color=NODEc, zorder=3)
    def _rect(x, y, w, h):
        ax.add_patch(plt.Rectangle((x, y), w, h, fill=False, edgecolor="#3f6bb0", lw=1.2, zorder=2))
    def RH(cx, cy, lab, name, below=False):        # horizontal resistor
        W(cx-34, cy, cx-22, cy); _rect(cx-22, cy-6, 44, 12); W(cx+22, cy, cx+34, cy)
        if name: T(cx, cy+(18 if below else -20), name, "t")
        if lab:  T(cx, cy+(30 if below else -9), lab, "v")
    def RV(cx, cy, lab, name, side=1):             # vertical resistor
        W(cx, cy-30, cx, cy-18); _rect(cx-6, cy-18, 12, 36); W(cx, cy+18, cx, cy+30)
        if name: T(cx+11*side, cy-3, name, "t", "start" if side > 0 else "end")
        if lab:  T(cx+11*side, cy+9, lab, "v", "start" if side > 0 else "end")
    def CV(cx, cy, lab, name, side=1):             # vertical capacitor
        W(cx, cy-22, cx, cy-4); W(cx-9, cy-4, cx+9, cy-4); W(cx-9, cy+4, cx+9, cy+4); W(cx, cy+4, cx, cy+22)
        if name: T(cx+12*side, cy-2, name, "t", "start" if side > 0 else "end")
        if lab:  T(cx+12*side, cy+10, lab, "v", "start" if side > 0 else "end")
    def CHB(cx, cy, lab, name):                    # horizontal capacitor (label below)
        W(cx-26, cy, cx-4, cy); W(cx-4, cy-9, cx-4, cy+9); W(cx+4, cy-9, cx+4, cy+9); W(cx+4, cy, cx+26, cy)
        if name: T(cx, cy+20, name, "t")
        if lab:  T(cx, cy+32, lab, "v")
    def GND(x, y, up=False):
        s = -1 if up else 1
        W(x-9, y, x+9, y); W(x-5.5, y+4*s, x+5.5, y+4*s); W(x-2, y+8*s, x+2, y+8*s)

    icL, icR, icT, icB = 560, 1000, 300, 700
    ax.add_patch(plt.Rectangle((icL, icT), icR-icL, icB-icT, fill=True, facecolor=ICF,
                               edgecolor=ICE, lw=1.6, zorder=2, joinstyle="round"))
    T(780, 470, "FAN9672Q", "p"); T(780, 490, "2-Ch Interleaved CCM PFC — LQFP-32", "t")
    T(780, 512, ("FR mode (90–132 Vac)" if mode_lo else "HV mode (180–264 Vac)"), "n")
    rowY = lambda i: 340 + i*46
    for i, n in enumerate(["BIBO", "PVO", "ILIMIT", "GC", "RI", "RLPK", "ILIMIT2", "LPK"]):
        y = rowY(i); W(505, y, icL, y); T(icL+8, y, str(i+1), "num", "start"); T(icL+24, y, n, "p", "start")
    for i, pn in enumerate([("24", "GND"), ("23", "CS1+"), ("22", "CS1-"), ("21", "CS2+"),
                            ("20", "CS2-"), ("19", "NC"), ("18", "NC"), ("17", "LS")]):
        y = rowY(i); W(icR, y, 1055, y); T(icR-8, y, pn[0], "num", "end"); T(icR-24, y, pn[1], "p", "end")
    for pn in [("32", "IAC", 600), ("31", "SS", 648), ("30", "VEA", 700), ("29", "FBPFC", 800),
               ("28", "VDD", 880), ("27", "OPFC1", 925), ("26", "OPFC2", 962)]:
        W(pn[2], icT-30, pn[2], icT); T(pn[2], icT+14, pn[0], "num"); T(pn[2], icT+28, pn[1], "p")
    for pn in [("9", "RDY", 602), ("10", "IEA1", 668), ("11", "IEA2", 800), ("13", "CM1", 884),
               ("14", "CM2", 916), ("16", "VIR", 974)]:
        W(pn[2], icB, pn[2], icB+30); T(pn[2], icB-8, pn[0], "num"); T(pn[2], icB-22, pn[1], "p")

    # ── TOP networks ──
    W(630, 88, 1010, 88); T(1022, 88, "GND", "n", "start")
    T(600, 108, "VIN (rect)", "n"); NODE(600, 118); W(600, 118, 600, 162)
    RV(600, 192, fo(g("riac", 12e6 if is_high else 6e6)),
       f"R_IAC ({'6' if is_high else '3'} × 2 MΩ ser.)", 1); W(600, 222, 600, icT-30)
    W(648, icT-30, 648, 152); CV(648, 130, fc(g("css", 390e-9)), "C_SS", -1); W(648, 108, 648, 88)
    W(700, icT-30, 700, 254); NODE(700, 254); W(684, 254, 724, 254)
    W(684, 254, 684, 244); RV(684, 214, fo(g("r_vc", 143e3)), "R_VC", -1)
    W(684, 184, 684, 176); CV(684, 156, fc(g("c_vc1", 390e-9)), "C_VC1", -1); W(684, 134, 684, 88)
    W(724, 254, 724, 242); CV(724, 220, fc(g("c_vc2", 24e-9)), "C_VC2", 1); W(724, 198, 724, 88)
    T(800, 48, "+VDC", "n"); NODE(800, 58); W(800, 58, 800, 80)
    RV(800, 104, "", "", 1); RV(800, 150, "", "", 1); RV(800, 196, fo(g("rfb_each", 3.63e6))+" ×3", "R_FB1 string", 1)
    W(800, 226, 800, icT-30); NODE(800, 262); W(800, 262, 816, 262)
    RH(838, 262, fo(g("rfb2", 23.2e3)), "R_FB2", below=True); W(872, 262, 872, 266); GND(872, 268)
    if g("vType", "type3") == "type3":
        W(800, 58, 756, 58); W(756, 58, 756, 84); RV(756, 108, fo(g("r3", 8.66e6)), "R_V3", -1)
        W(756, 138, 756, 148); CV(756, 168, fc(g("c_v3", 1.1e-9)), "C_V3", -1); W(756, 190, 756, 262); W(756, 262, 800, 262)
    W(880, icT-30, 880, 250); CV(880, 228, "0.1µ+10µ", "C_VDD", -1); W(880, 206, 880, 88)
    for i, (x, lab) in enumerate([(925, "→ Q1 gate"), (962, "→ Q2 gate")]):
        W(x, icT-30, x, icT-52); ax.plot([x-5, x, x+5], [icT-52, icT-64, icT-52], color="#8a6fd0", lw=1.2)
        T(x+6, icT-80 - (0 if i else 16), lab, "t", "start")

    # ── LEFT networks ──
    def rcGndH(x, y, Rlab, Rname, Clab, Cname):
        NODE(x, y); W(x, y-13, x, y+13)
        W(x, y-13, x-16, y-13); RH(x-50, y-13, Rlab, Rname); W(x-84, y-13, x-100, y-13); GND(x-100, y-13)
        W(x, y+13, x-16, y+13); CHB(x-50, y+13, Clab, Cname); W(x-76, y+13, x-100, y+13); GND(x-100, y+13)
    y = rowY(0)     # BIBO ladder
    T(74, 300, "VIN (rect)", "n"); NODE(74, 310); W(74, 310, 74, y); W(74, y, 110, y)
    RH(144, y, fo(g("rb1")), "R_B1"); RH(232, y, fo(g("rb2")), "R_B2"); NODE(278, y)
    RH(318, y, fo(g("rb3")), "R_B3"); NODE(366, y); W(352, y, 505, y)
    W(278, y, 278, y-22); CV(278, y-44, fc(g("cb1")), "C_B1", -1); W(278, y-66, 278, y-72); GND(278, y-74, up=True)
    NODE(392, y); W(392, y, 392, y-16); RV(392, y-46, fo(g("rb4")), "R_B4", 1); W(392, y-76, 392, y-78); GND(392, y-80, up=True)
    NODE(448, y); W(448, y, 448, y-22); CV(448, y-44, fc(g("cb2")), "C_B2", 1); W(448, y-66, 448, y-72); GND(448, y-74, up=True)
    y = rowY(1); W(505, y, 468, y); W(468, y, 468, y+8); GND(468, y+10); T(452, y-4, "0 V — disabled", "t", "end")
    y = rowY(2); rcGndH(462, y, fo(g("r_ilimit_sel")), "R_ILIMIT", fc(g("cil", 18e-9)), "C_ILIMIT"); W(462, y, 505, y)
    y = rowY(3); rcGndH(312, y, fo(g("r_gc_sel")), "R_GC", fc(g("c_gc")), "C_GC"); W(312, y, 505, y)
    y = rowY(4); NODE(468, y); W(468, y, 505, y); RH(430, y, fo(g("rri", 13700.0)), "R_RI"); W(396, y, 382, y); GND(382, y+2)
    y = rowY(5); rcGndH(462, y, fo(g("rrlpk", 15e3)), "R_RLPK", fc(g("crlpk", 1e-9)), "C_RLPK"); W(462, y, 505, y)
    y = rowY(6); rcGndH(312, y, fo(g("r_ilimit2_sel")), "R_ILIMIT2", fc(g("cil2", 75e-9)), "C_ILIMIT2"); W(312, y, 505, y)
    y = rowY(7); W(476, y, 505, y); RH(442, y, fo(g("rpin8", 1e3)), "R_pin8"); NODE(404, y)
    W(404, y, 404, y+14); CV(404, y+36, fc(g("clpk", 1e-9)), "C_LPK", -1); W(404, y+58, 404, y+64); GND(404, y+66)

    # ── BOTTOM networks ──
    W(602, icB+30, 602, icB+44); T(602, icB+62, "PFC ready", "t"); T(602, icB+75, "(pull-up typ)", "t")
    def iea(x, mirror, lab):
        d = -1 if mirror else 1; xr = x-20*d; xc = x+22*d
        W(x, icB+30, x, icB+50); NODE(x, icB+50); W(min(xr, xc), icB+50, max(xr, xc), icB+50)
        W(xr, icB+50, xr, icB+62); RV(xr, icB+86, fo(g("r_ic", 30.1e3)) if lab else "", "R_IC" if lab else "", -d)
        W(xr, icB+116, xr, icB+124); CV(xr, icB+144, fc(g("c_ic1", 5.6e-9)) if lab else "", "C_IC1" if lab else "", -d)
        W(xr, icB+166, xr, icB+174); GND(xr, icB+176)
        W(xc, icB+50, xc, icB+66); CV(xc, icB+86, fc(g("c_ic2", 200e-12)) if lab else "", "C_IC2" if lab else "", d)
        W(xc, icB+108, xc, icB+174); GND(xc, icB+176)
    iea(668, False, True); iea(800, True, False); T(800, icB+196, "(network identical to IEA1)", "t")
    W(884, icB+30, 884, icB+50); W(916, icB+30, 916, icB+50); W(884, icB+50, 916, icB+50); W(900, icB+50, 900, icB+58); GND(900, icB+60)
    T(900, icB+104, "both channels enabled", "t")
    x = 974; W(x, icB+30, x, icB+50); NODE(x, icB+50); W(x-18, icB+50, x+22, icB+50)
    W(x-18, icB+50, x-18, icB+62); RV(x-18, icB+86, fo(g("rvir", 10e3 if mode_lo else 470e3)), "R_VIR", -1)
    W(x-18, icB+116, x-18, icB+124); GND(x-18, icB+126)
    W(x+22, icB+50, x+22, icB+66); CV(x+22, icB+86, fc(g("cvir", 100e-9)), "C_VIR", 1); W(x+22, icB+108, x+22, icB+124); GND(x+22, icB+126)
    T(x, icB+150, ("V_VIR < 1.5 V → FR" if mode_lo else "V_VIR > 3.5 V → HV"), "n")

    # ── RIGHT networks ──
    y = rowY(0); W(1055, y, 1070, y); GND(1070, y+2); T(1088, y, "signal GND", "t", "start")
    def csCh(rp, rm, sw, nm):
        yp, ym = rowY(rp), rowY(rm)
        W(1055, yp, 1130, yp); NODE(1130, yp); W(1130, yp, 1156, yp); RH(1190, yp, fo(g("rf", 2e3)), "R_F"); W(1224, yp, 1300, yp); NODE(1300, yp)
        W(1055, ym, 1130, ym); NODE(1130, ym); W(1130, ym, 1156, ym); RH(1190, ym, "", ""); W(1224, ym, 1300, ym); NODE(1300, ym)
        CV(1130, (yp+ym)/2, fc(g("cf", 470e-12)), "C_F", -1)
        ax.add_patch(plt.Rectangle((1293, yp+8), 14, ym-yp-16, fill=False, edgecolor=VALc, lw=1.6, zorder=2))
        W(1300, yp, 1300, yp+8); W(1300, ym-8, 1300, ym)
        T(1322, (yp+ym)/2-2, f"{g('rcs_mohm', 15.0):g} mΩ", "v", "start"); T(1322, (yp+ym)/2+12, "R_CS "+nm+" (Kelvin)", "t", "start")
        T(1300, yp-8, sw, "n"); W(1300, ym, 1300, ym+4); GND(1300, ym+6); T(1334, ym+14, "PGND", "t", "start")
    csCh(1, 2, "SW1 source", "CS1"); csCh(3, 4, "SW2 source", "CS2")
    y19, y18 = rowY(5), rowY(6); W(1055, y19, 1072, y19); W(1055, y18, 1072, y18); W(1072, y19, 1072, y18); NODE(1072, y18); W(1072, y18, 1072, y18+8); GND(1072, y18+10)
    y = rowY(7); NODE(1090, y); W(1055, y, 1090, y); W(1090, y-13, 1090, y+13)
    W(1090, y-13, 1106, y-13); RH(1140, y-13, fo(g("r_ls_sel")), "R_LS"); W(1174, y-13, 1190, y-13); GND(1190, y-13)
    W(1090, y+13, 1106, y+13); CHB(1140, y+13, fc(g("c_ls")), "C_LS"); W(1166, y+13, 1190, y+13); GND(1190, y+13)

    # ── title block ──
    def Tt(x, y, t, a="start"):
        ax.text(x, y, t, color="#334", fontsize=6.4, ha="left", va="center", zorder=5)
    ax.add_patch(plt.Rectangle((1092, 892), 402, 88, fill=True, facecolor="#f4f7fc", edgecolor="#c2cee0", lw=1.0, zorder=2))
    ax.text(1102, 909, "FAN9672 FRONT END — LIVE DESIGN VALUES", color=PINc, fontsize=6.8,
            fontweight="bold", ha="left", va="center", zorder=5)
    Tt(1102, 927, f"Line: {'High / HV' if is_high else 'Low / FR'}   ·   crest cmd {g('crest_A', 0):.2f} A   ·   R_CS {g('rcs_mohm', 15.0):g} mΩ")
    Tt(1102, 943, f"I_phi,pk {g('iphi_pk_A', 0):.2f} A   ·   V_CS,pk {g('vcs_pk_mV', 0):.0f} mV   ·   I_ILIMIT {g('i_ilimit_uA', 0):.1f} µA")
    Tt(1102, 959, f"V-comp {'Type 3 OTA' if g('vType','type3')=='type3' else 'Type 2 OTA'}   ·   I-comp Type 2 OTA")

    fig.tight_layout(pad=0.2)
    buf = io.BytesIO(); fig.savefig(buf, format="png", dpi=210, bbox_inches="tight", pad_inches=0.05)
    plt.close(fig); buf.seek(0)
    iw, ih = ImageReader(buf).getSize(); buf.seek(0)
    w = CW * max_frac; h = ih * (w / iw)
    return Image(buf, width=w, height=h)


if __name__ == "__main__":
    img = type2_ota_compensator()
    print("Fig 10A image flowable:", img.drawWidth, "x", img.drawHeight)
    img3 = type3_ota_compensator()
    print("Fig 14A image flowable:", img3.drawWidth, "x", img3.drawHeight)
    img2v = type2_voltage_compensator()
    print("Fig 14A (type2) image flowable:", img2v.drawWidth, "x", img2v.drawHeight)
