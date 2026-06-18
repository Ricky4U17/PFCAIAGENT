#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate PFC_Inductor_OurEngine_Equations.pdf — step-by-step equations for every quantity
computed by OUR production engine backend/app/mode_b/step7_magnetic_calc.py (Phase-1 v10),
with a complete variable glossary. Equations are transcribed from the CODE, not textbooks.

This is the counterpart to the Simulation-Agent's PFC_Inductor_Engine_Equations.pdf, kept as a
record of our current physics before any merge/refactor. Written 2026-06-10."""
import os
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
                                PageBreak, KeepTogether)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# Register a Unicode TTF so Greek/math glyphs render (Windows Arial, then DejaVu, then Helvetica).
BODY, BOLD, ITAL = 'Helvetica', 'Helvetica-Bold', 'Helvetica-Oblique'
for fam, reg, bd, it in (
    ('UN', r'C:\Windows\Fonts\arial.ttf',  r'C:\Windows\Fonts\arialbd.ttf', r'C:\Windows\Fonts\ariali.ttf'),
    ('UN', '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
           '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
           '/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf'),
):
    try:
        pdfmetrics.registerFont(TTFont('UN', reg))
        pdfmetrics.registerFont(TTFont('UN-B', bd))
        pdfmetrics.registerFont(TTFont('UN-I', it))
        pdfmetrics.registerFontFamily('UN', normal='UN', bold='UN-B', italic='UN-I', boldItalic='UN-B')
        BODY, BOLD, ITAL = 'UN', 'UN-B', 'UN-I'
        break
    except Exception:
        continue

S = getSampleStyleSheet()
st_t   = ParagraphStyle('t',   parent=S['Title'],    fontSize=17, spaceAfter=4, fontName=BOLD)
st_sub = ParagraphStyle('sub', parent=S['Normal'],   fontSize=9,  textColor=colors.grey, alignment=1, fontName=BODY)
st_h1  = ParagraphStyle('h1',  parent=S['Heading1'], fontSize=13, spaceBefore=10, spaceAfter=4,
                        textColor=colors.HexColor('#5c1a3a'), fontName=BOLD)
st_h2  = ParagraphStyle('h2',  parent=S['Heading2'], fontSize=11, spaceBefore=7, spaceAfter=3,
                        textColor=colors.HexColor('#7f2a56'), fontName=BOLD)
st_b   = ParagraphStyle('b',   parent=S['Normal'],   fontSize=9,  leading=12.5, spaceAfter=3, fontName=BODY)
st_eq  = ParagraphStyle('eq',  parent=S['Normal'],   fontSize=9.6, leading=14, leftIndent=22,
                        spaceBefore=2, spaceAfter=2, fontName=BOLD)
st_wh  = ParagraphStyle('wh',  parent=S['Normal'],   fontSize=8.6, leading=11.5, leftIndent=30,
                        spaceAfter=2, textColor=colors.HexColor('#333333'), fontName=BODY)
st_nt  = ParagraphStyle('nt',  parent=S['Normal'],   fontSize=8.4, leading=11, leftIndent=22,
                        textColor=colors.HexColor('#7a5a00'), spaceAfter=4, fontName=BODY)

story = []
_eqn = [0]
def H1(x): story.append(Paragraph(x, st_h1))
def H2(x): story.append(Paragraph(x, st_h2))
def B(x):  story.append(Paragraph(x, st_b))
def EQ(expr, where=None, note=None):
    _eqn[0] += 1
    block = [Paragraph(f"(E{_eqn[0]})&nbsp;&nbsp;{expr}", st_eq)]
    if where:
        for w in where: block.append(Paragraph("&bull; " + w, st_wh))
    if note: block.append(Paragraph("Note: " + note, st_nt))
    story.append(KeepTogether(block))

# ============================ TITLE ============================
story.append(Paragraph("PFC Boost Inductor — Production Engine Equation Reference (v11)", st_t))
story.append(Paragraph(
    "Step-by-step equations for every quantity computed by our production backend "
    "<b>step7_magnetic_calc.py</b> (Phase-1 v10 + Phase-B improvements). Transcribed from the code "
    "as of 2026-06-13. <b>Updates since the v10 reference (2026-06-10):</b> material-specific DB "
    "DC-bias k(H) in the per-&theta; waveform loop (no EDGE fallback); harmonic AC-excess copper "
    "loss (K<sub>harm</sub>); discontinuous-conduction (DCM) detection; instantaneous-peak minimum-L "
    "guarantee; and the single-source view contract feeding Result / Review / Simulation. "
    "Counterpart record to the Simulation-Agent's PFC_Inductor_Engine_Equations.pdf.", st_sub))
story.append(Spacer(1, 8))
B("<b>Conventions.</b> Distributed-gap powder toroid (ferrite path noted where it differs), CCM "
  "boost PFC, n<sub>ph</sub>-phase interleaved. Geometry in mm; flux density in T; bias field H in "
  "A/m internally and oersted (Oe) for retention; Steinmetz frequency in Hz into the DB; resistance "
  "in &Omega;; power in W; temperature in &deg;C. &theta; &isin; (0, &pi;) is the line half-cycle "
  "angle; the engine integrates &theta;-dependent quantities on an <b>M = 360-point</b> midpoint grid. "
  "Subscript &ldquo;single&rdquo; = one core of the stack; stack totals = single &times; n<sub>stk</sub>. "
  "<b>Material data (core loss P<sub>v</sub>(B,f,T) and DC-bias k(H)) comes from the MagneticsDB as "
  "temperature-aware interpolated curves</b>, not closed-form fits &mdash; this is our key accuracy "
  "lever and is shown below as DB(&middot;).")

# ============================ S0 CONSTANTS ============================
H1("S0 &mdash; Physical &amp; model constants")
EQ("&mu;<sub>0</sub> = 4&pi;&times;10<super>&minus;7</super> H/m,&nbsp;&nbsp;"
   "&rho;<sub>Cu,20</sub> = 1.72&times;10<super>&minus;8</super> &Omega;&middot;m,&nbsp;&nbsp;"
   "&alpha;<sub>Cu</sub> = 0.00393 K<super>&minus;1</super>",
   ["copper resistivity at 20 &deg;C and its temperature coefficient",
    "&rho;<sub>Cu</sub>(T) = &rho;<sub>Cu,20</sub>(1 + &alpha;<sub>Cu</sub>(T &minus; 20))"])
EQ("1 Oe = 79.577 A/m",
   ["oersted conversion used wherever the DB bias curve is addressed in Oe"])
EQ("iGSE: c = 1.444,&nbsp; b = 2.106,&nbsp; I<sub>c</sub> = 3.5435,&nbsp; "
   "K<sub>iGSE</sub> = 2<super>c</super> / ((2&pi;)<super>c&minus;1</super>&middot;I<sub>c</sub>)",
   ["fixed improved-Generalised-Steinmetz constants for the triangular-ripple duty correction F(D)"])
EQ("K<sub>harm</sub> = 1.213&nbsp;&nbsp;(triangular-ripple harmonic AC-excess factor)",
   ["amplifies ONLY the AC excess (R<sub>AC</sub>/R<sub>DC</sub> &minus; 1) of the HF copper loss: the "
    "switching ripple's higher harmonics (n = 1,3,5,&hellip;) see a higher effective R<sub>AC</sub>"],
   "NEW (v11): adopted from the simulation-agent engine. K<sub>harm</sub> = 1 recovers the v10 form "
   "I<sub>hf,rms</sub><super>2</super>&middot;R<sub>AC</sub>.")
EQ("Proximity (Dowell-like, v10): k<sub>skin</sub> = 0.50,&nbsp; k<sub>prox</sub> = 0.40,&nbsp; "
   "k<sub>crowd</sub> = 0.25",
   ["calibrated coefficients for the litz/TIW AC-resistance model (E20)"])
EQ("Thermal 2-node split (v10): s<sub>C</sub> = 1.00,&nbsp; s<sub>W</sub> = 0.90,&nbsp; "
   "couple = 0.50,&nbsp; hotspot = 1.12;&nbsp;&nbsp; l<sub>lead</sub> = 150 mm",
   ["core/winding ambient-path split, core&ndash;winding coupling, interior hotspot factor; "
    "default lead length added to copper length"])

# ============================ S1 INDUCTANCE & TURNS ============================
H1("S1 &mdash; Unbiased inductance, required retention, and turns (powder)")
EQ("L<sub>0</sub> = A<sub>L,single</sub> &middot; n<sub>stk</sub> &middot; N<super>2</super> &times; 10<super>&minus;9</super>&nbsp;&nbsp;[H]",
   ["A<sub>L,single</sub> &mdash; inductance factor of ONE core at zero bias [nH/T<super>2</super>]; N &mdash; turns"])
EQ("L<sub>0,min</sub> = L<sub>0</sub>(1 &minus; tol<sub>AL</sub>),&nbsp;&nbsp;L<sub>0,max</sub> = L<sub>0</sub>(1 + tol<sub>AL</sub>)&nbsp;&nbsp;(tol<sub>AL</sub> &asymp; 0.08)")
EQ("k<sub>req</sub> = L<sub>target</sub> / L<sub>0</sub>&nbsp;&nbsp;(required bias retention at the worst DC point)",
   ["turns are chosen as the smallest N whose biased inductance still meets the target:",
    "find N: DB k(H<sub>worst</sub>(N)) &middot; L<sub>0</sub>(N) &ge; L<sub>target</sub>"])
EQ("I<sub>dc,worst</sub> = max<sub>OPS</sub> [ &radic;2&middot;P<sub>out</sub> / (&eta;&middot;V<sub>in</sub>&middot;PF&middot;n<sub>ph</sub>) ]",
   ["worst-case per-phase crest current scanned over all 9 operating points (OPS)"],
   "Ferrite path instead converges turns + gap l<sub>g</sub> to a target peak flux (E14 uses the gapped reluctance).")

# ============================ S2 BIAS ============================
H1("S2 &mdash; DC-bias field and DB permeability retention")
EQ("H<sub>dc</sub> = N &middot; I / l<sub>e,single</sub>&nbsp;&nbsp;[A/m],&nbsp;&nbsp;H<sub>Oe</sub> = H<sub>dc</sub> / 79.577",
   ["uses l<sub>e</sub> of ONE core (NOT n<sub>stk</sub>&middot;l<sub>e</sub>) for stacked toroids"])
EQ("k(H) = DB.get_k_bias(material, H<sub>Oe</sub>)&nbsp;&nbsp;[&ndash;]",
   ["material-specific DC-bias curve interpolated from the MagneticsDB (per material, per H)"],
   "FIXED (v11): the per-&theta; waveform loop now ALSO calls DB.get_k_bias(material, H<sub>Oe</sub>) for the "
   "SELECTED material &mdash; the v10 EDGE-calibrated closed-form fallback "
   "k(H) = min(1, [1/(0.01 + 9.202&times;10<super>&minus;10</super> H<super>3.044</super>)]/100) is no longer "
   "used there. This corrects k(H)/B<sub>max</sub> for non-EDGE materials and makes step7's biased flux match "
   "the field-engine, which reads the same DB curve.")
EQ("L(H) = k(H) &middot; L<sub>0</sub>&nbsp;&nbsp;(biased inductance)")

# ============================ S3 OPERATING POINT ============================
H1("S3 &mdash; Operating-point currents (per OPS corner {V<sub>in</sub>, P<sub>out</sub>, &eta;, PF})")
EQ("P<sub>in</sub> = P<sub>out</sub> / &eta;,&nbsp;&nbsp;V<sub>pk</sub> = &radic;2&middot;V<sub>in</sub>,&nbsp;&nbsp;"
   "D<sub>pk</sub> = 1 &minus; V<sub>pk</sub> / V<sub>out</sub>",
   ["V<sub>out</sub> = 393 V boost rail; D<sub>pk</sub> &mdash; duty at the line crest"])
EQ("I<sub>&phi;,avg,crest</sub> = &radic;2&middot;P<sub>out</sub> / (&eta;&middot;V<sub>in</sub>&middot;PF&middot;n<sub>ph</sub>)",
   ["per-phase switching-average current at the line crest"])

# ============================ S4 LINE-CYCLE WAVEFORMS ============================
H1("S4 &mdash; Line-cycle waveforms over &theta; &isin; (0, &pi;), M = 360 midpoints")
EQ("&theta;<sub>n</sub> = (n + &frac12;)&pi;/M,&nbsp;&nbsp;v<sub>in</sub>(&theta;) = V<sub>pk</sub> sin&theta;,&nbsp;&nbsp;"
   "D(&theta;) = clip(1 &minus; v<sub>in</sub>/V<sub>out</sub>, 0, 0.98)")
EQ("i<sub>avg</sub>(&theta;) = I<sub>&phi;,crest</sub> sin&theta;,&nbsp;&nbsp;"
   "H(&theta;) = 0.4&pi;&middot;N&middot;i<sub>avg</sub>(&theta;) / l<sub>e,cm</sub>,&nbsp;&nbsp;"
   "L(&theta;) = k(H(&theta;))&middot;L<sub>0</sub>",
   ["powder: k(H(&theta;)) = DB.get_k_bias(material, H(&theta;)) per &theta; (v11 &mdash; was an EDGE closed-form in v10)"])
EQ("&Delta;I<sub>pp</sub>(&theta;) = v<sub>in</sub>(&theta;)&middot;D(&theta;) / (L(&theta;)&middot;f<sub>sw</sub>),&nbsp;&nbsp;"
   "I<sub>hf</sub>(&theta;) = &Delta;I<sub>pp</sub>(&theta;) / (2&radic;3)",
   ["triangular switching ripple peak-to-peak and its RMS"])
EQ("DCM at &theta; if&nbsp; i<sub>avg</sub>(&theta;) &lt; &Delta;I<sub>pp</sub>(&theta;)/2;&nbsp;&nbsp;"
   "f<sub>DCM</sub> = (count of such &theta;) / M",
   ["NEW (v11): fraction of the line half-cycle where the inductor current rings to zero "
    "(boundary / discontinuous conduction) &mdash; reported as dcm_fraction"])
EQ("B<sub>ac,pk</sub>(&theta;) = v<sub>in</sub>(&theta;)&middot;D(&theta;) / (2&middot;N&middot;A<sub>e</sub>&middot;f<sub>sw</sub>),&nbsp;&nbsp;"
   "B<sub>dc</sub>(&theta;) = L(&theta;)&middot;i<sub>avg</sub>(&theta;) / (N&middot;A<sub>e</sub>),&nbsp;&nbsp;"
   "B<sub>max</sub>(&theta;) = B<sub>dc</sub> + B<sub>ac,pk</sub>",
   ["A<sub>e</sub> = A<sub>e,single</sub>&middot;n<sub>stk</sub>&times;10<super>&minus;6</super> [m<super>2</super>]"])

# ============================ S5 PEAK FLUX ============================
H1("S5 &mdash; Flux density, radial crowding, saturation margin")
EQ("B<sub>ac,pk</sub> = V<sub>pk,90</sub>&middot;D<sub>pk,90</sub> / (2N&middot;A<sub>e</sub>&middot;f<sub>sw</sub>),&nbsp;&nbsp;"
   "B<sub>dc</sub> = L<sub>target</sub>&middot;I<sub>&phi;,crest</sub> / (N&middot;A<sub>e</sub>)",
   ["headline flux evaluated at the 90 Vac low-line reference corner"])
EQ("B<sub>max,FL</sub> = B<sub>dc</sub> + B<sub>ac,pk</sub>,&nbsp;&nbsp;B<sub>min,FL</sub> = B<sub>dc</sub> &minus; B<sub>ac,pk</sub>")
EQ("crowd<sub>ax</sub> = r<sub>mean</sub> / r<sub>in</sub> = [(ID/2 + OD/2)/2] / (ID/2),&nbsp;&nbsp;"
   "B<sub>inner</sub> = B<sub>max,FL</sub> &middot; crowd<sub>ax</sub>",
   ["toroid 1/r inner-bore flux concentration (v10)"])
EQ("margin<sub>sat</sub> = (B<sub>sat</sub>(T<sub>core</sub>) &minus; B<sub>max</sub>) / B<sub>sat</sub> &times; 100 %",
   ["B<sub>sat</sub>(T<sub>core</sub>) from the DB at the converged core temperature; inner-bore margin checked too"])
EQ("L<sub>full,min@pk</sub> = L<sub>0,min</sub>&middot;DB.k(H<sub>pk</sub>),&nbsp;&nbsp;"
   "H<sub>pk</sub> = N&middot;(I<sub>&phi;,crest</sub> + &Delta;I<sub>pp</sub>/2) / (l<sub>e,single</sub>&middot;79.577)&nbsp;&nbsp;[Oe]",
   ["NEW (v11): minimum guaranteed inductance at the worst INSTANTANEOUS peak bias "
    "(crest-average current + half the ripple), via the selected material's DB curve at min-A<sub>L</sub>"],
   "Informational &mdash; more conservative than the crest-average bias; turns selection and pass/fail are unchanged. Powder only.")
EQ("Ferrite: B<sub>dc</sub> = &mu;<sub>0</sub>N&middot;I / (l<sub>g</sub> + l<sub>e</sub>/&mu;<sub>r</sub>)",
   ["gapped-reluctance bias flux; &mu;<sub>r</sub> = DB.get_mu_r(material, 100&deg;C); l<sub>g</sub> &mdash; air gap"])

# ============================ S6 COPPER GEOMETRY & DCR ============================
H1("S6 &mdash; Copper geometry, MLT, and DC resistance")
EQ("w<sub>core</sub> = (OD &minus; ID)/2,&nbsp;&nbsp;"
   "MLT = 2(w<sub>core</sub> + HT&middot;n<sub>stk</sub>) + 2&middot;OD<sub>bundle</sub>&nbsp;&nbsp;[mm]&nbsp;&nbsp;(v10)",
   ["v10 uses the actual bundle OD as the build allowance (legacy form used a fixed 3.8 mm)"])
EQ("l<sub>Cu</sub> = N&middot;MLT/1000 + l<sub>lead</sub>/1000&nbsp;&nbsp;[m]",
   ["lead wire (entry + exit, 150 mm) added to the wound length"])
EQ("R<sub>DC</sub>(T) = R&prime;<sub>20</sub>&middot;(1 + &alpha;<sub>Cu</sub>(T &minus; 20))&middot;l<sub>Cu</sub>&nbsp;&nbsp;[&Omega;]",
   ["R&prime;<sub>20</sub> &mdash; catalog wire resistance per metre at 20 &deg;C [&Omega;/m]"])
EQ("FF<sub>Cu</sub> = N&middot;A<sub>Cu</sub> / W<sub>a,bore</sub>",
   ["bare-copper bore-window fill; W<sub>a,bore</sub> is the single-core window area (invariant with stacks)"])

# ============================ S7 SKIN / AC RESISTANCE ============================
H1("S7 &mdash; Skin depth and AC resistance (physics-based Dowell-proximity, v10)")
EQ("&delta; = &radic;( &rho;<sub>Cu</sub>(T) / (&pi;&middot;f<sub>sw</sub>&middot;&mu;<sub>0</sub>) ),&nbsp;&nbsp;"
   "x = d<sub>strand</sub> / (2&delta;)",
   ["&delta; &mdash; skin depth at f<sub>sw</sub>; x &mdash; strand-radius / skin-depth ratio"])
EQ("F<sub>skin</sub> = 1 + k<sub>skin</sub>&middot;x<super>2</super>,&nbsp;&nbsp;"
   "F<sub>prox</sub> = 1 + k<sub>prox</sub>&middot;(N<sub>lay</sub>&minus;1)&middot;x<super>2</super>&middot;(1 + k<sub>crowd</sub>(crowd<sub>ax</sub>&minus;1))",
   ["inter-layer proximity grows with layer count and inner-bore crowding"])
EQ("R<sub>AC</sub>/R<sub>DC</sub> = max(1, F<sub>skin</sub>&middot;F<sub>prox</sub>)",
   ["litz/TIW path; solid/enamel uses an exact Bessel skin factor (compute_dowell_factor)"],
   "This physics-based ratio is a strength of our engine vs. a flat 1.15 heuristic.")

# ============================ S8 BORE LAYERS ============================
H1("S8 &mdash; Bore layer count and residual window")
EQ("OD<sub>bundle</sub> &mdash; catalog bundle OD (authoritative) or computed from strands &amp; fill",
   ["feeds both MLT (E15) and the layer/proximity model (E22)"])
EQ("N<sub>lay</sub>, t<sub>pl</sub>, r<sub>bore</sub> = layers(N&middot;n<sub>par</sub>, ID, OD<sub>bundle</sub>);&nbsp;&nbsp;"
   "hole<sub>ID</sub> = max(0.5, 2&middot;r<sub>bore</sub>)",
   ["turns-per-bore-layer and residual bore radius after all layers (negative &rArr; overfull)"])

# ============================ S9 CORE LOSS ============================
H1("S9 &mdash; Core loss (DB Steinmetz, iGSE duty correction, cycle-averaged)")
EQ("P<sub>v</sub>(B, f, T) = DB.get_core_loss(material, f<sub>sw</sub>, B<sub>ac,pk</sub>, T)&nbsp;&nbsp;[W/m<super>3</super>]",
   ["temperature-aware loss density interpolated from the MagneticsDB material curves"])
EQ("F<sub>D</sub>(D) = K<sub>iGSE</sub>&middot;( D<super>1&minus;c</super> + (1&minus;D)<super>1&minus;c</super> ),&nbsp;&nbsp;"
   "D clipped to [0.02, 0.98]",
   ["iGSE duty-ratio correction for the asymmetric triangular flux"])
EQ("p<sub>core</sub>(&theta;) = P<sub>v</sub>(B<sub>ac,pk</sub>(&theta;), f<sub>sw</sub>, T<sub>core</sub>)&middot;F<sub>D</sub>(D(&theta;))&middot;V<sub>e</sub>,&nbsp;&nbsp;"
   "P<sub>core</sub> = (1/M) &Sigma;<sub>n</sub> p<sub>core</sub>(&theta;<sub>n</sub>)",
   ["V<sub>e</sub> = V<sub>e,single</sub>&middot;n<sub>stk</sub> [m<super>3</super>]; this cycle-averaged value is the authoritative P<sub>core</sub>"])
EQ("Uncertainty band: P<sub>unc,lo</sub> = P<sub>Cu,100</sub> + 1.05&middot;P<sub>core</sub>,&nbsp;&nbsp;"
   "P<sub>unc,hi</sub> = P<sub>Cu,100</sub> + 1.20&middot;P<sub>core</sub>",
   ["+5 % to +20 % core-loss uplift band (unanchored until FEA/bench calibration)"])

# ============================ S10 RMS & COPPER LOSS ============================
H1("S10 &mdash; RMS decomposition and copper loss (cycle-averaged)")
EQ("I<sub>&phi;,rms</sub> = &radic;( (1/M)&Sigma; i<sub>avg</sub>(&theta;)<super>2</super> ),&nbsp;&nbsp;"
   "I<sub>hf,rms</sub> = &radic;( (1/M)&Sigma; I<sub>hf</sub>(&theta;)<super>2</super> )")
EQ("P<sub>Cu</sub>(T) = I<sub>&phi;,rms</sub><super>2</super>&middot;R<sub>DC</sub>(T) + "
   "I<sub>hf,rms</sub><super>2</super>&middot;[ R<sub>DC</sub>(T) + (R<sub>AC</sub>(T) &minus; R<sub>DC</sub>(T))&middot;K<sub>harm</sub> ]",
   ["DC-resistance part on the full RMS, plus the AC EXCESS (R<sub>AC</sub> &minus; R<sub>DC</sub>) on the "
    "ripple RMS, amplified by the harmonic factor K<sub>harm</sub> = 1.213",
    "= I<sub>&phi;,rms</sub><super>2</super>R<sub>DC</sub> + I<sub>hf,rms</sub><super>2</super>R<sub>DC</sub>"
    "(1 + (R<sub>AC</sub>/R<sub>DC</sub> &minus; 1)K<sub>harm</sub>); reported at T<sub>core</sub>, 25 &deg;C and 100 &deg;C"],
   "CHANGED (v11): v10 used I<sub>hf,rms</sub><super>2</super>&middot;R<sub>AC</sub>. The harmonic uplift raises HF "
   "copper loss to reflect the triangular ripple's spectrum.")
EQ("J = I<sub>&phi;,rms</sub> / (A<sub>Cu</sub> / n<sub>par</sub>)&nbsp;&nbsp;[A/mm<super>2</super>]",
   ["copper current density per parallel conductor"])

# ============================ S11 THERMAL ============================
H1("S11 &mdash; Thermal (SA single-node convergence + v10 two-node hotspot)")
EQ("SA = [ &pi;&middot;OD<sub>w</sub>&middot;OH + (&pi;/2)(OD<sub>w</sub><super>2</super> &minus; hole<super>2</super>) + &pi;&middot;hole&middot;OH ] / 100&nbsp;&nbsp;[cm<super>2</super>]",
   ["wound-part exposed surface area; OD<sub>w</sub>, OH from the assembled wound envelope"])
EQ("&Delta;T<sub>SA</sub> = ( P<sub>tot</sub>&middot;1000 / SA )<super>0.833</super>&nbsp;&nbsp;[K]",
   ["natural-convection surface-area power law"])
EQ("Convergence: iterate T<sub>core</sub> &larr; T<sub>amb</sub> + &Delta;T<sub>SA</sub>(P<sub>core</sub>(T<sub>core</sub>) + P<sub>Cu</sub>(T<sub>core</sub>) + P<sub>fring</sub>) until |&Delta;| &lt; 0.2 K",
   ["couples temperature-dependent core &amp; copper loss to the surface model (10-iteration loop)"])
EQ("&theta; = &Delta;T<sub>SA</sub>/P<sub>tot</sub>;&nbsp; R<sub>ca</sub> = &theta;(s<sub>C</sub>+s<sub>W</sub>)/s<sub>C</sub>,&nbsp; "
   "R<sub>wa</sub> = &theta;(s<sub>C</sub>+s<sub>W</sub>)/s<sub>W</sub>,&nbsp; R<sub>cw</sub> = &theta;&middot;couple",
   ["two-node resistances derived from the calibrated SA baseline"])
EQ("Solve KCL 2&times;2 for &Delta;T<sub>c</sub>, &Delta;T<sub>w</sub>;&nbsp;&nbsp;"
   "&Delta;T<sub>hotspot</sub> = max(&Delta;T<sub>c</sub>, &Delta;T<sub>w</sub>)&middot;1.12",
   ["core/winding node rises and interior hotspot (1.12 over node average)"])

# ============================ S12 FRINGING (FERRITE) ============================
H1("S12 &mdash; Gap fringing (ferrite only)")
EQ("P<sub>fring</sub> = Rogowski(l<sub>g</sub>, A<sub>e</sub>, W<sub>a</sub>, N, d<sub>bundle</sub>, R<sub>DC,100</sub>)",
   ["gap-fringing eddy loss in winding turns near the gap (compute_rogowski_fringing); powder cores: 0"])

# ============================ S13 PER-Vin SCREENING TABLE ============================
H1("S13 &mdash; Per-V<sub>in</sub> screening table (analytical, single-point)")
B("A faster single-point analytical pass over all 9 OPS corners drives the per-V<sub>in</sub> sweep "
  "table and charts. It is intentionally lighter than the S4/S9/S10 waveform integration:")
EQ("B<sub>ac,pk</sub> = V<sub>pk</sub>D<sub>pk</sub>/(2N&middot;A<sub>e</sub>f<sub>sw</sub>),&nbsp;&nbsp;"
   "P<sub>core</sub> = P<sub>v</sub>(B<sub>ac,pk</sub>,f,T)&middot;F<sub>D</sub>(D<sub>pk</sub>)&middot;V<sub>e</sub>,&nbsp;&nbsp;"
   "P<sub>Cu</sub> = I<sub>rms</sub><super>2</super>R<sub>DC</sub>(T) + I<sub>hf</sub><super>2</super>R<sub>AC</sub>(T)",
   ["single crest-point evaluation per corner (no &theta; integration)"],
   "IMPORTANT: this table is a SCREENING estimate and differs from the authoritative S4/S9/S10 "
   "waveform totals at the same V<sub>in</sub>. The Review page anchors this table to the waveform "
   "result at 90 V / 100 &deg;C so the two presentations agree (P<sub>core</sub>, P<sub>tot</sub> ratios).")

# ============================ S14 WORST-CASE & SCORE ============================
H1("S14 &mdash; Worst-case scan, acceptance, and ranking score")
B("Every OPS corner is evaluated; the design reports worst-case total loss, B<sub>max</sub> (mean path) "
  "and B<sub>inner</sub>, minimum guaranteed L, maximum &Delta;T and J. Pass/fail uses L &ge; L<sub>target</sub>, "
  "B<sub>max</sub> and inner-bore vs B<sub>sat</sub>(T), FF<sub>Cu</sub> &le; limit, &Delta;T &le; budget, J in band.")
EQ("score = w<sub>loss</sub>&middot;P<sub>tot</sub>/P<sub>ref</sub> + w<sub>vol</sub>&middot;V<sub>e</sub>/V<sub>ref</sub> + "
   "w<sub>&Delta;T</sub>&middot;&Delta;T/&Delta;T<sub>ref</sub> + w<sub>cost</sub>&middot;(&hellip;) + w<sub>fill</sub>&middot;(&hellip;)",
   ["composite ranking score (lower is better); candidates returned top-N per stack count"])

# ============================ S15 VIEW CONTRACT ============================
H1("S15 &mdash; Single-source view contract (Result / Review / Simulation)")
B("<b>NEW (v11).</b> build_view_contract(result, state) is the AUTHORITATIVE render payload every screen "
  "draws from. It re-runs the S4/S9/S10 waveform integration on the STORED design so all three screens "
  "render the exact same converged numbers &mdash; they RENDER this, they never recompute. Additive / "
  "read-only.")
EQ("waveform = _half_cycle_averages(&hellip;, V<sub>in,pk</sub> = &radic;2&middot;90, R<sub>dc</sub> = R<sub>DC,100</sub>, M = 360, series)",
   ["the 90 Vac DESIGN-corner per-&theta; arrays (t, v<sub>in</sub>, D, i<sub>avg</sub>, H, B<sub>dc</sub>, "
    "B<sub>ac,pk</sub>, B<sub>max</sub>, I<sub>hf</sub>, p<sub>core</sub>, p<sub>cu</sub>, p<sub>tot</sub>) on the "
    "100 &deg;C copper basis (so &Sigma;p<sub>cu</sub> equals reported P<sub>Cu,100</sub>)"])
EQ("i<sub>crest</sub>(V<sub>in</sub>) = I<sub>&phi;,crest</sub>&middot;( I<sub>crest</sub><super>sweep</super>(V<sub>in</sub>) / I<sub>crest</sub><super>sweep</super>(90) ),&nbsp;&nbsp;M = 180",
   ["per-OPS waveforms for the V<sub>in</sub> explorer, anchored so the design corner equals the readouts"])
EQ("P<sub>core</sub><super>anc</super>(V<sub>in</sub>) = P<sub>core</sub><super>tbl</super>(V<sub>in</sub>)&middot;( P<sub>core</sub><super>design</super> / P<sub>core</sub><super>tbl</super>(90) ),&nbsp;&nbsp;"
   "P<sub>cu</sub><super>anc</super> likewise",
   ["the single-point S13 screening table is rescaled to the authoritative S4/S9/S10 design totals at 90 V, "
    "so the per-V<sub>in</sub> sweep agrees with Result / Review at every corner"])
EQ("acceptance = { B<sub>max</sub> &lt; B<sub>sat</sub>(T), K<sub>u</sub> &le; 60 %, &Delta;T &le; budget, "
   "L<sub>full</sub> &ge; L<sub>target</sub> } &rArr; APPROVE / REJECT",
   ["step7's own verdict + fail reasons exported for the viewer's acceptance panel; limits come from the "
    "design, never invented"])

story.append(PageBreak())
# ============================ GLOSSARY ============================
H1("Appendix &mdash; Variable glossary (code names)")
rows = [["Symbol", "Code name (step7_magnetic_calc.py)", "Unit", "Meaning"]]
G = [
 ["mu0", "MU0", "H/m", "Permeability of free space"],
 ["rhoCu,alphaCu", "RHO_CU_20 / ALPHA_CU", "ohm*m, 1/K", "Copper resistivity / temp coefficient"],
 ["c,b,Ic,K", "IGSE_C / IGSE_B / IGSE_IC / IGSE_K", "-", "iGSE duty-correction constants"],
 ["Kharm", "K_HARM", "-", "Triangular-ripple harmonic AC-excess factor (1.213, v11)"],
 ["kskin,kprox,kcrowd", "_PROX_kSkin/kProx/kCrowd", "-", "Dowell-proximity coefficients (v10)"],
 ["sC,sW,couple,hotspot", "_THERM_sC/sW/couple/hotspot", "-", "Two-node thermal split + hotspot factor"],
 ["N", "N", "turns", "Number of turns (chosen by _turns_powder/_turns_ferrite)"],
 ["nstk", "stacks", "-", "Stacked core count"],
 ["AL,single", "AL_nom_nH", "nH/T2", "Inductance factor of ONE core"],
 ["L0(min/nom/max)", "L0_min/nom/max_uH", "uH", "Unbiased inductance + AL tolerance band"],
 ["kreq", "kreq_nom", "-", "Required retention L_target/L0"],
 ["Ae,single/Ve,single", "Ae_single_mm2 / Ve_total_cm3", "mm2/cm3", "Single-core area / total volume"],
 ["Le,single", "Le_single_mm", "mm", "Magnetic path length of ONE core"],
 ["Wa,bore", "Wa_single_mm2", "mm2", "Single-core bore window area"],
 ["Bsat(T)", "Bsat_at_Tcore", "T", "Saturation flux at core temperature (DB)"],
 ["k(H)", "DB.get_k_bias / _retention_edge", "-", "DC-bias retention (DB curve; EDGE fallback)"],
 ["Pv(B,f,T)", "DB.get_core_loss", "W/m3", "Temperature-aware core-loss density (DB)"],
 ["Hdc/HOe", "H_Oe_design / H_Oe_worst", "A/m, Oe", "DC bias field"],
 ["Iphi,crest", "I_phi_avg_crest", "A", "Per-phase crest average current"],
 ["Dpk", "Dpk90", "-", "Duty at line crest"],
 ["dIpp/Ihf", "dIL_pp_A / IhfRms_A", "A", "Switching ripple pk-pk / RMS"],
 ["Bac,pk/Bdc/Bmax", "Bac_pk_T / Bdc_T / Bmax_FL_T", "T", "AC peak / DC / mean-path peak flux"],
 ["crowd_ax/Binner", "crowd_axial / Bmax_inner_FL_T", "-, T", "Inner-bore crowding / crowded peak flux"],
 ["MLT", "MLT_v10_mm", "mm", "Mean length per turn (2(w+HT*stk)+2*ODb)"],
 ["lCu", "Cu_length_m", "m", "Total conductor length incl. leads"],
 ["RDC(T)", "DCR_25C/100C_mOhm", "mohm", "DC resistance at temperature"],
 ["RAC/RDC", "Rac_Rdc", "-", "AC/DC ratio (Dowell-proximity or Bessel)"],
 ["delta/x", "(internal)", "m, -", "Skin depth / strand-to-skin ratio"],
 ["Nlay,tpl,rbore", "layers_needed / (internal)", "-", "Bore layers, turns/layer, residual radius"],
 ["FFcu/Ku", "FFcu / Ku", "-", "Window fill / bore utilization"],
 ["FD(D)", "_Fd(D)", "-", "iGSE duty correction"],
 ["Pcore", "Pcore_W", "W", "Cycle-averaged core loss (authoritative)"],
 ["Punc lo/hi", "P_unc_lo_W / P_unc_hi_W", "W", "Core-loss uncertainty band"],
 ["fDCM", "dcm_fraction", "-", "Fraction of half-cycle in DCM, i_avg<dIpp/2 (v11)"],
 ["Lfull,min@pk", "Lfull_min_at_peak_uH", "uH", "Min-L at worst instantaneous peak bias, DB k(H) (v11)"],
 ["Iphi,rms/Pcu", "Ihf_rms_A / Pcu_100C_W", "A, W", "RMS current / copper loss"],
 ["J", "J_A_mm2", "A/mm2", "Copper current density"],
 ["SA/dT", "SA (internal) / dT_rise_C", "cm2, K", "Wound surface area / surface rise"],
 ["dTc/dTw/dThot", "dT_core_C/dT_wdg_C/dT_hotspot_C", "K", "Two-node rises + hotspot"],
 ["Rca/Rwa/Rcw", "(returned by _two_node_thermal)", "K/W", "Node thermal resistances"],
 ["Pfring", "P_fringing_W", "W", "Gap fringing loss (ferrite)"],
 ["Ptotal(25/100)", "Ptotal_25C_W / Ptotal_100C_W", "W", "Total loss at temperature"],
 ["score", "score", "-", "Composite ranking score (lower better)"],
]
for g in G: rows.append(g)
tbl = Table(rows, colWidths=[30*mm, 56*mm, 16*mm, 70*mm], repeatRows=1)
tbl.setStyle(TableStyle([
    ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#5c1a3a')),
    ('TEXTCOLOR', (0,0), (-1,0), colors.white),
    ('FONTNAME', (0,0), (-1,0), BOLD),
    ('FONTSIZE', (0,0), (-1,-1), 7.4),
    ('FONTNAME', (0,1), (-1,-1), BODY),
    ('GRID', (0,0), (-1,-1), 0.4, colors.HexColor('#cfb9c4')),
    ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#f7eef3')]),
    ('VALIGN', (0,0), (-1,-1), 'TOP'),
    ('LEFTPADDING', (0,0), (-1,-1), 3), ('RIGHTPADDING', (0,0), (-1,-1), 3),
    ('TOPPADDING', (0,0), (-1,-1), 1.6), ('BOTTOMPADDING', (0,0), (-1,-1), 1.6),
]))
story.append(tbl)
story.append(Spacer(1, 8))
B("<i>Honest status note (v11). Strengths vs. the Simulation-Agent reference engine: temperature-aware "
  "DB core-loss and DC-bias curves, now used per-&theta; in the waveform loop for the SELECTED material "
  "(the v10 EDGE-calibrated k(H) fallback is removed); a physics-based Dowell-proximity R<sub>AC</sub> "
  "with the K<sub>harm</sub> = 1.213 triangular-ripple harmonic uplift on the AC excess; a two-node "
  "hotspot thermal model; ferrite gap fringing; DCM-fraction detection; an instantaneous-peak minimum-L "
  "guarantee; and a single-source view contract (S15) so Result / Review / Simulation render identical "
  "numbers. Open items: the per-V<sub>in</sub> screening table (S13) is single-point and is anchored to "
  "the waveform totals at 90 V; R<sub>AC</sub> (incl. K<sub>harm</sub>), thermal and bias retention are "
  "still first-order until FEA/bench data is attached. All other quantities are exact arithmetic on the "
  "DB + designer-selected geometry/wire.</i>")

out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "PFC_Inductor_OurEngine_Equations_v11.pdf")
doc = SimpleDocTemplate(out_path, pagesize=letter, topMargin=16*mm, bottomMargin=15*mm,
                        leftMargin=16*mm, rightMargin=16*mm,
                        title="PFC Boost Inductor — Production Engine Equation Reference (v11)",
                        author="Magnetics design pipeline")
doc.build(story)
print("PDF built:", out_path, "| equations:", _eqn[0])
