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


if __name__ == "__main__":
    img = type2_ota_compensator()
    print("Fig 10A image flowable:", img.drawWidth, "x", img.drawHeight)
    img3 = type3_ota_compensator()
    print("Fig 14A image flowable:", img3.drawWidth, "x", img3.drawHeight)
