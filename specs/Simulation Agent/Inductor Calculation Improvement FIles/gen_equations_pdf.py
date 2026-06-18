#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate PFC_Inductor_Engine_Equations.pdf — step-by-step equations for every quantity
computed by pfc_inductor_engine.py (v1.0.0) and the SimAgentField viewer (v14), with a
complete variable glossary. Equations are transcribed from the CODE, not from textbooks."""
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
                                PageBreak, KeepTogether)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
try:
    pdfmetrics.registerFont(TTFont('DVS', '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'))
    pdfmetrics.registerFont(TTFont('DVS-B', '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'))
    pdfmetrics.registerFont(TTFont('DVS-I', '/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf'))
    pdfmetrics.registerFontFamily('DVS', normal='DVS', bold='DVS-B', italic='DVS-I', boldItalic='DVS-B')
    BODY, BOLD = 'DVS', 'DVS-B'
except Exception:
    BODY, BOLD = 'Helvetica', 'Helvetica-Bold'   # fallback: Greek via Symbol, math symbols degraded

S = getSampleStyleSheet()
st_t   = ParagraphStyle('t',   parent=S['Title'],    fontSize=17, spaceAfter=4, fontName=BOLD)
st_sub = ParagraphStyle('sub', parent=S['Normal'],   fontSize=9,  textColor=colors.grey, alignment=1, fontName=BODY)
st_h1  = ParagraphStyle('h1',  parent=S['Heading1'], fontSize=13, spaceBefore=10, spaceAfter=4,
                        textColor=colors.HexColor('#1a3a5c'), fontName=BOLD)
st_h2  = ParagraphStyle('h2',  parent=S['Heading2'], fontSize=11, spaceBefore=7, spaceAfter=3,
                        textColor=colors.HexColor('#2a567f'), fontName=BOLD)
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
story.append(Paragraph("PFC Boost Inductor Engine — Equation Reference", st_t))
story.append(Paragraph(
    "Step-by-step equations for every quantity computed by <b>pfc_inductor_engine.py</b> (v1.0.0, "
    "schema 1.0) and the <b>SimAgentField</b> browser viewer (v14). Transcribed from the code; "
    "companion to DATA_DICTIONARY.md and PowderCore_Magnetic_Calc_Standard_v1.", st_sub))
story.append(Spacer(1, 8))
B("<b>Conventions.</b> Distributed-gap powder toroid, CCM boost PFC, n<sub>ph</sub>-phase interleaved. "
  "Geometry in mm; flux density in T; bias field H in oersted (Oe); Steinmetz frequency in kHz; "
  "resistance in &Omega;; power in W; temperature in &deg;C. &theta; &isin; (0, &pi;) is the line "
  "half-cycle angle; the engine evaluates all &theta;-dependent quantities on a 40 001-point grid and "
  "integrates by the trapezoidal rule. Subscript &ldquo;single&rdquo; = one core of the stack. "
  "Each quantity carries a provenance/tier: analytic-T1, FEA-T2, measured-T3; solved or measured "
  "data, when present in the package, replaces the analytic expression for that quantity only "
  "(precedence: measured &gt; FEA &gt; analytic).")

# ============================ S0 CONSTANTS ============================
H1("S0 — Physical constants (the only numbers owned by the engine)")
EQ("&mu;<sub>0</sub> = 4&pi;&times;10<super>&minus;7</super> H/m",
   ["&mu;<sub>0</sub> — permeability of free space"])
EQ("1 Oe = 79.577 A/m",
   ["oersted-to-SI conversion for the bias field H"])
EQ("&rho;<sub>20</sub> = 1.724&times;10<super>&minus;8</super> &Omega;&middot;m,&nbsp;&nbsp;&alpha;<sub>Cu</sub> = 0.00393 K<super>&minus;1</super>",
   ["&rho;<sub>20</sub> — copper resistivity at 20 &deg;C (package-overridable)",
    "&alpha;<sub>Cu</sub> — copper temperature coefficient (package-overridable)"],
   "Every material, geometry, wire and operating value is injected by the package; none is built in.")

# ============================ S1 INDUCTANCE ============================
H1("S1 — Unbiased inductance and tolerance band")
EQ("L<sub>0</sub> = A<sub>L,single</sub> &middot; n<sub>stk</sub> &middot; N<super>2</super> &times; 10<super>&minus;9</super>&nbsp;&nbsp;[H]",
   ["A<sub>L,single</sub> — inductance factor of ONE core at zero bias [nH/turn<super>2</super>]",
    "n<sub>stk</sub> — number of stacked cores; N — turns"])
EQ("L<sub>0,min</sub> = L<sub>0</sub>(1 &minus; tol<sub>AL</sub>),&nbsp;&nbsp;L<sub>0,max</sub> = L<sub>0</sub>(1 + tol<sub>AL</sub>)",
   ["tol<sub>AL</sub> — catalog A<sub>L</sub> tolerance fraction (e.g. 0.08 for &plusmn;8 %)"],
   "The tolerance derate applies ONLY when L(H) is analytic. A solved FEA table or measured L(I) "
   "is the actual inductance and is used un-derated (parity rule, both engine and viewer).")

# ============================ S2 BIAS ============================
H1("S2 — DC-bias field and permeability retention")
EQ("H = 0.4&pi; &middot; N &middot; I / l<sub>e,cm</sub>&nbsp;&nbsp;[Oe]",
   ["I — instantaneous inductor current [A]; l<sub>e,cm</sub> = L<sub>e,mm</sub>/10 — magnetic path length [cm]"])
EQ("k(H) = 1 / (k<sub>0</sub> + k<sub>1</sub>&middot;H<super>p</super>) / 100&nbsp;&nbsp;[–]",
   ["k(H) — per-unit permeability retention (catalog DC-bias fit; k<sub>0</sub>&asymp;0.01 gives 100 % at H=0)",
    "k<sub>0</sub>, k<sub>1</sub>, p — material retention coefficients from the package"])
EQ("L(H) = k(H) &middot; L<sub>0</sub>&nbsp;&nbsp;(analytic T1)&nbsp;&nbsp;|&nbsp;&nbsp;L(H) = interp(H; table)&nbsp;&nbsp;(FEA T2 / measured T3)",
   ["table — fields.inductance{H[Oe], L[&mu;H]} or material.measured.inductance"],
   "Measured L given versus bias current is converted point-by-point with E6: "
   "H<sub>i</sub> = 0.4&pi;&middot;N&middot;I<sub>i</sub>/l<sub>e,cm</sub>.")

# ============================ S3 OPERATING POINT ============================
H1("S3 — Operating-point currents (per spec corner {V<sub>in</sub>, P<sub>out</sub>, &eta;, PF})")
EQ("P<sub>in</sub> = P<sub>out</sub> / &eta;",
   ["&eta; — converter efficiency at this corner (per unit)"])
EQ("V<sub>pk</sub> = &radic;2 &middot; V<sub>in</sub>",
   ["V<sub>in</sub> — line RMS voltage [V]"])
EQ("I<sub>in,rms</sub> = P<sub>in</sub> / (V<sub>in</sub> &middot; PF),&nbsp;&nbsp;I<sub>in,pk</sub> = &radic;2 &middot; I<sub>in,rms</sub>",
   ["PF — power factor at this corner (per unit)"])
EQ("I<sub>c</sub> = I<sub>in,pk</sub> / n<sub>ph</sub>",
   ["I<sub>c</sub> — per-phase crest (low-frequency peak) current; n<sub>ph</sub> — interleaved phases"],
   "Browser map form: when only maps.etaByVin is given, &eta;&middot;PF is taken as the map value "
   "(the PRODUCT) with P<sub>out</sub> = load&middot;P<sub>rated</sub>; validate() cross-checks the two forms.")

# ============================ S4 LINE-CYCLE WAVEFORMS ============================
H1("S4 — Line-cycle waveforms over &theta; &isin; (0, &pi;)")
EQ("v<sub>in</sub>(&theta;) = V<sub>pk</sub> sin&theta;,&nbsp;&nbsp;D(&theta;) = clip(1 &minus; v<sub>in</sub>(&theta;)/V<sub>out</sub>, 0, 1)",
   ["D(&theta;) — boost duty ratio (CCM); V<sub>out</sub> — DC output voltage",
    "D<sub>pk</sub> = 1 &minus; V<sub>pk</sub>/V<sub>out</sub> — duty at the line crest"])
EQ("i<sub>avg</sub>(&theta;) = I<sub>c</sub> sin&theta;",
   ["i<sub>avg</sub> — switching-period-average inductor current (sinusoidal PFC reference)"])
EQ("&Delta;I<sub>pp</sub>(&theta;) = v<sub>in</sub>(&theta;)&middot;D(&theta;) / (L(H(&theta;))&middot;f<sub>sw</sub>)",
   ["&Delta;I<sub>pp</sub> — peak-to-peak switching ripple; L evaluated at the local bias "
    "H(&theta;) = 0.4&pi;&middot;N&middot;i<sub>avg</sub>(&theta;)/l<sub>e,cm</sub> (E6)",
    "f<sub>sw</sub> — switching frequency [Hz]"])
EQ("i<sub>pk</sub>(&theta;) = i<sub>avg</sub>(&theta;) + &Delta;I<sub>pp</sub>(&theta;)/2",
   ["i<sub>pk</sub> — instantaneous switching-peak current"])
EQ("B<sub>ac,pk</sub>(&theta;) = v<sub>in</sub>(&theta;)&middot;D(&theta;) / (2&middot;N&middot;A<sub>e</sub>&middot;f<sub>sw</sub>)",
   ["B<sub>ac,pk</sub> — half of the peak-to-peak AC flux swing [T]",
    "A<sub>e</sub> = A<sub>e,single</sub>&middot;n<sub>stk</sub>&times;10<super>&minus;6</super> — total effective area [m<super>2</super>]"])
EQ("B<sub>dc</sub>(&theta;) = L&middot;i<sub>avg</sub>(&theta;) / (N&middot;A<sub>e</sub>),&nbsp;&nbsp;B<sub>mean</sub>(&theta;) = B<sub>dc</sub>(&theta;) + B<sub>ac,pk</sub>(&theta;)",
   ["B<sub>dc</sub> — bias flux density at the mean magnetic path; B<sub>mean</sub> — instantaneous peak at the mean path"])

# ============================ S5 PEAK FLUX ============================
H1("S5 — Peak flux density and saturation margin")
EQ("B<sub>max</sub> = max<sub>&theta;</sub> [ L(H(&theta;)) &middot; i<sub>pk</sub>(&theta;) / (N&middot;A<sub>e</sub>) ]&nbsp;&nbsp;[T, mean path]",
   ["the worst instantaneous mean-path peak over the half line cycle"],
   "Acceptance basis (parity rule): B<sub>max</sub> is checked against the upstream limit "
   "B<sub>max,T</sub> or (1 &minus; sat_margin_min)&middot;B<sub>sat</sub>; the verification "
   "golden numbers use this mean-path basis.")
EQ("crowd = r<sub>mean</sub> / r<sub>in</sub>&nbsp;&nbsp;(analytic 1/r)&nbsp;&nbsp;|&nbsp;&nbsp;crowd = interp(r<sub>in</sub>; fields.flux.radial)",
   ["r<sub>in</sub> = ID/2, r<sub>mean</sub> = (ID/2 + OD/2)/2 — inner and mean radii [mm]"])
EQ("B<sub>inner</sub> = B<sub>max</sub> &middot; crowd",
   ["B<sub>inner</sub> — crowded inner-radius peak flux (toroid 1/r concentration)"],
   "Checked only if upstream supplies acceptance.Binner_max_T.")
EQ("margin<sub>sat</sub> = (B<sub>sat</sub> &minus; B<sub>max</sub>) / B<sub>max</sub> &times; 100 %",
   ["B<sub>sat</sub> — material saturation flux density [T]"])

# ============================ S6 COPPER GEOMETRY & DCR ============================
H1("S6 — Copper geometry and DC resistance")
EQ("A<sub>str</sub> = (&pi;/4)&middot;d<sub>str</sub><super>2</super>,&nbsp;&nbsp;A<sub>Cu</sub> = n<sub>par</sub>&middot;n<sub>str</sub>&middot;A<sub>str</sub>&nbsp;&nbsp;[mm<super>2</super>]",
   ["d<sub>str</sub> — BARE strand diameter [mm]; n<sub>str</sub> — strands per bundle; "
    "n<sub>par</sub> — parallel bundles"])
EQ("w<sub>core</sub> = (OD &minus; ID)/2,&nbsp;&nbsp;h<sub>stk</sub> = HT<sub>single</sub>&middot;n<sub>stk</sub>",
   ["w<sub>core</sub> — radial wall width; h<sub>stk</sub> — stacked core height [mm]"])
EQ("MLT = 2(w<sub>core</sub> + h<sub>stk</sub>) + b<sub>w</sub>&nbsp;&nbsp;[mm]&nbsp;&nbsp;(engine)",
   ["b<sub>w</sub> — winding build allowance [mm] (default 3.8)",
    "Viewer form: MLT = 2(w<sub>core</sub>+h<sub>stk</sub>) + 2&middot;OD<sub>b</sub>, leads added once: "
    "l = N&middot;MLT + l<sub>lead</sub>"])
EQ("l<sub>Cu</sub> = N &middot; MLT / 1000&nbsp;&nbsp;[m]",
   ["l<sub>Cu</sub> — total conductor length"])
EQ("R<sub>DC,25</sub> = &rho;<sub>20</sub>(1 + 5&alpha;<sub>Cu</sub>) &middot; l<sub>Cu</sub> / (A<sub>Cu</sub>&times;10<super>&minus;6</super>)&nbsp;&nbsp;[&Omega;]",
   ["geometry estimate at 25 &deg;C; provenance &lsquo;computed&rsquo;"],
   "Measured override (T3): R<sub>DC,25</sub> = R<sub>meas,20</sub>(1+5&alpha;<sub>Cu</sub>) or "
   "R&prime;<sub>meas,20</sub>&middot;l<sub>Cu</sub>(1+5&alpha;<sub>Cu</sub>); a &gt;2&times; disagreement "
   "with the geometry estimate raises a validation warning.")
EQ("R<sub>DC</sub>(T) = R<sub>DC,25</sub> &middot; (1 + &alpha;<sub>Cu</sub>(T &minus; 25))",
   ["T — copper temperature [&deg;C]; losses evaluated at T<sub>wind</sub> = 100 &deg;C (worst) and 25 &deg;C"])
EQ("FF<sub>Cu</sub> = N&middot;A<sub>Cu</sub> / W<sub>a</sub>",
   ["FF<sub>Cu</sub> — bare-copper window fill; W<sub>a</sub> — core window area [mm<super>2</super>]; "
    "FF<sub>Cu</sub> &gt; 1 is a hard validation error (physically impossible)"])

# ============================ S7 SKIN / AC RESISTANCE ============================
H1("S7 — Skin depth and AC resistance")
EQ("&delta; = &radic;( &rho;<sub>20</sub> / (&pi;&middot;f<sub>sw</sub>&middot;&mu;<sub>0</sub>) )&nbsp;&nbsp;[m]",
   ["&delta; — copper skin depth at f<sub>sw</sub>; strand check: d<sub>str</sub> &lt; 2&delta;"])
EQ("F<sub>R</sub> = R<sub>AC</sub>/R<sub>DC</sub> = 1.15&nbsp;&nbsp;(engine default, package-overridable)",
   ["F<sub>R</sub> — AC-to-DC resistance ratio at f<sub>sw</sub> (Tier-1 stand-in heuristic)"])
EQ("Viewer analytic: x = d<sub>str</sub>/(2&delta;);&nbsp; F<sub>skin</sub> = 1 + k<sub>skin</sub>x<super>2</super>;&nbsp; "
   "F<sub>prox</sub> = 1 + k<sub>prox</sub>(N<sub>lay</sub>&minus;1)x<super>2</super>(1 + k<sub>crowd</sub>(crowd<sub>ax</sub>&minus;1));&nbsp; F<sub>R</sub> = F<sub>skin</sub>&middot;F<sub>prox</sub>",
   ["k<sub>skin</sub>, k<sub>prox</sub>, k<sub>crowd</sub> — stand-in hyperparameters (defaults 0.5/0.40/0.25)",
    "N<sub>lay</sub> — bore winding layers (E55); crowd<sub>ax</sub> = r<sub>mean</sub>/r<sub>in</sub>"],
   "Both forms are Tier-1 placeholders. A solved table fields.windingAC{f, R<sub>AC</sub>/R<sub>DC</sub>} "
   "(eddy-current FEA or core-less-bobbin measurement) replaces them by interpolation at f<sub>sw</sub> (T2/T3).")
EQ("k<sub>harm</sub> = &Sigma;<sub>n odd</sub>(1/n<super>2</super>)<super>2</super>n<super>2</super> / &Sigma;<sub>n odd</sub>(1/n<super>2</super>)<super>2</super> &asymp; 1.213",
   ["k<sub>harm</sub> — excess factor for the triangular-ripple harmonic spectrum (n = 1,3,5,&hellip;199)"])

# ============================ S8 RMS & COPPER LOSS ============================
H1("S8 — RMS decomposition and copper loss")
EQ("I<sub>rms,LF</sub> = I<sub>c</sub>/&radic;2",
   ["low-frequency (line) RMS of the per-phase current"])
EQ("I<sub>rms,HF</sub> = &radic;[ (1/&pi;)&int;<sub>0</sub><super>&pi;</super> (&Delta;I<sub>pp</sub>(&theta;)/(2&radic;3))<super>2</super> d&theta; ]",
   ["RMS of the triangular switching ripple, cycle-averaged"])
EQ("I<sub>&phi;,rms</sub> = &radic;( I<sub>rms,LF</sub><super>2</super> + I<sub>rms,HF</sub><super>2</super> )",
   ["total per-phase RMS current"])
EQ("P<sub>Cu</sub>(T) = I<sub>&phi;,rms</sub><super>2</super>&middot;R<sub>DC</sub>(T) + I<sub>rms,HF</sub><super>2</super>&middot;(F<sub>R</sub>&minus;1)&middot;k<sub>harm</sub>&middot;R<sub>DC</sub>(T)",
   ["first term — all current at DC resistance; second — HF ripple AC excess only",
    "reported at T = 100 &deg;C (P<sub>Cu,100</sub>, worst) and 25 &deg;C (P<sub>Cu,25</sub>)"])
EQ("J = max<sub>corners</sub>(I<sub>&phi;,rms</sub>) / A<sub>Cu</sub>&nbsp;&nbsp;[A/mm<super>2</super>]",
   ["J — copper current density, checked against acceptance.J_max if supplied"])

# ============================ S9 CORE LOSS ============================
H1("S9 — Core loss (Steinmetz with duty correction, cycle-averaged)")
EQ("P<sub>v</sub>(B, f) = a &middot; B<super>b</super> &middot; f<sub>kHz</sub><super>c</super>&nbsp;&nbsp;[mW/cm<super>3</super>]",
   ["a, b, c — material Steinmetz coefficients (catalog or measured refit); B in T, f in kHz"])
EQ("I<sub>c,int</sub> = &int;<sub>0</sub><super>2&pi;</super> |cos&theta;|<super>c</super> d&theta;&nbsp;&nbsp;(&asymp; 3.54 for c&asymp;1.4)",
   ["iGSE-style normalization integral, computed numerically per material"])
EQ("F<sub>D</sub>(D) = 2<super>c</super>&middot;(D<super>1&minus;c</super> + (1&minus;D)<super>1&minus;c</super>) / ((2&pi;)<super>c&minus;1</super> &middot; I<sub>c,int</sub>)",
   ["F<sub>D</sub> — duty-ratio (non-sinusoidal) correction for the asymmetric triangular flux; "
    "D clipped to [10<super>&minus;4</super>, 1&minus;10<super>&minus;4</super>]"])
EQ("p<sub>core</sub>(&theta;) = P<sub>v</sub>(B<sub>ac,pk</sub>(&theta;), f<sub>sw,kHz</sub>) &middot; F<sub>D</sub>(D(&theta;)) &middot; V<sub>e,cm3</sub> / 1000&nbsp;&nbsp;[W]",
   ["V<sub>e,cm3</sub> = V<sub>e,single</sub>&middot;n<sub>stk</sub> — total core volume [cm<super>3</super>]"])
EQ("P<sub>core</sub> = (1/&pi;) &int;<sub>0</sub><super>&pi;</super> p<sub>core</sub>(&theta;) d&theta;&nbsp;&nbsp;(method &lsquo;cycle_avg_igse&rsquo;)",
   ["alternative &lsquo;peak_point&rsquo;: P<sub>core</sub> = P<sub>v</sub>(B<sub>ac,crest</sub>, f<sub>kHz</sub>)&middot;V<sub>e,cm3</sub>/1000"])
EQ("P<sub>core,max</sub> = P<sub>core</sub> &middot; s<sub>max</sub>",
   ["s<sub>max</sub> — material max/typical loss band (catalog default 1.286 &asymp; &plusmn;29 %); "
    "a measured refit may supply its own bench-uncertainty s<sub>max</sub>"],
   "Measured core loss (T3): either a refit {a,b,c} used directly in E39, or &ge;3 raw bench points "
   "fitted by least squares (E59); the catalog transcription anchor is then dropped, and "
   "measured-vs-catalog disagreement &gt;1.5&times; raises a validation warning.")
EQ("P<sub>tot,typ</sub> = P<sub>core</sub> + P<sub>Cu,100</sub>,&nbsp;&nbsp;P<sub>tot,max</sub> = P<sub>core,max</sub> + P<sub>Cu,100</sub>",
   ["per-corner totals; the worst corner over all operating points is reported"])

# ============================ S10 THERMAL ============================
H1("S10 — Thermal (engine correlation; viewer 2-node network; FEA/CFD override)")
H2("Engine (single-node correlation, T1)")
EQ("OD<sub>w</sub> = OD + 2&radic;A<sub>bund</sub>,&nbsp;&nbsp;OH = h<sub>stk</sub> + 2&radic;A<sub>bund</sub> + 6.6,&nbsp;&nbsp;hole = max(ID &minus; 2&radic;A<sub>bund</sub>, 1)&nbsp;&nbsp;[mm]",
   ["A<sub>bund</sub> = n<sub>str</sub>&middot;A<sub>str</sub> — one bundle&rsquo;s copper area [mm<super>2</super>]; "
    "wound-part envelope dimensions"])
EQ("SA = [&pi;&middot;OD<sub>w</sub>&middot;OH + (&pi;/2)(OD<sub>w</sub><super>2</super> &minus; hole<super>2</super>) + &pi;&middot;hole&middot;OH] / 100&nbsp;&nbsp;[cm<super>2</super>]",
   ["SA — exposed surface area of the wound part"])
EQ("&Delta;T<sub>nat</sub> = (P<sub>tot,max</sub>&middot;1000 / SA)<super>0.833</super>&nbsp;&nbsp;[K]",
   ["natural-convection correlation (P in W &rarr; mW in the ratio)"])
EQ("Forced: Re = v&middot;L<sub>c</sub>/&nu;,&nbsp; Nu = 0.466&middot;Re<super>0.5</super>&middot;Pr<super>1/3</super>,&nbsp; "
   "h = Nu&middot;k<sub>air</sub>/L<sub>c</sub>,&nbsp; h<sub>rad</sub> = 0.9&middot;&sigma;&middot;4&middot;T<sub>m</sub><super>3</super>,&nbsp; "
   "&Delta;T = P/(SA<sub>m2</sub>(h+h<sub>rad</sub>))",
   ["v — airflow [m/s]; L<sub>c</sub> = OD<sub>w</sub>/1000 [m]; &nu; = 1.57&times;10<super>&minus;5</super> m<super>2</super>/s; "
    "Pr = 0.71; k<sub>air</sub> = 0.0263 W/m&middot;K; &sigma; = 5.67&times;10<super>&minus;8</super>; "
    "T<sub>m</sub> — mean film temperature [K]"])
H2("Viewer (two-node core/winding network, T1; calibrated to E42)")
EQ("&theta;<sub>sa</sub> = &Delta;T<sub>nat</sub>&middot;c<sub>mult</sub> / P<sub>tot</sub>;&nbsp;&nbsp;"
   "R<sub>ca</sub> = &theta;<sub>sa</sub>(s<sub>C</sub>+s<sub>W</sub>)/s<sub>C</sub>,&nbsp;&nbsp;"
   "R<sub>wa</sub> = &theta;<sub>sa</sub>(s<sub>C</sub>+s<sub>W</sub>)/s<sub>W</sub>,&nbsp;&nbsp;"
   "R<sub>cw</sub> = &theta;<sub>sa</sub>&middot;c<sub>cw</sub>",
   ["s<sub>C</sub>, s<sub>W</sub> — core/winding split of the ambient path (1/R<sub>ca</sub>+1/R<sub>wa</sub>=1/&theta;<sub>sa</sub>); "
    "c<sub>mult</sub>, c<sub>cw</sub> — cooling-model factors from the package"])
EQ("Steady state: [P<sub>core</sub>; P<sub>Cu</sub>] = "
   "[1/R<sub>ca</sub>+1/R<sub>cw</sub>, &minus;1/R<sub>cw</sub>; &minus;1/R<sub>cw</sub>, 1/R<sub>wa</sub>+1/R<sub>cw</sub>] &middot; [&Delta;T<sub>c</sub>; &Delta;T<sub>w</sub>]",
   ["2&times;2 linear solve for core and winding rises; T<sub>hot</sub> = T<sub>amb</sub> + max(&Delta;T<sub>c</sub>,&Delta;T<sub>w</sub>)&middot;k<sub>hot</sub>"])
EQ("Warm-up: C<sub>th,c</sub>dT<sub>c</sub>/dt = P<sub>core</sub> &minus; (T<sub>c</sub>&minus;T<sub>a</sub>)/R<sub>ca</sub> &minus; (T<sub>c</sub>&minus;T<sub>w</sub>)/R<sub>cw</sub>&nbsp; "
   "(and symmetrically for the winding), Euler dt = 0.5 s",
   ["C<sub>th,c</sub>, C<sub>th,w</sub> — node thermal capacitances [J/K] from the package"])
EQ("FEA/CFD override (T2): {R<sub>ca</sub>, R<sub>wa</sub>, R<sub>cw</sub>} from fields.thermal.nodes; "
   "engine winding rise &Delta;T = P<sub>tot,max</sub>&middot;R<sub>wa</sub>; "
   "&theta;<sub>SA</sub>-only form expands as R<sub>ca</sub>=R<sub>wa</sub>=2&theta;<sub>SA</sub>, R<sub>cw</sub>=&theta;<sub>SA</sub>/2",
   None)

# ============================ S11 WINDOW / L GUARANTEE / DCM ============================
H1("S11 — Window utilization, inductance guarantee, DCM boundary")
EQ("OD<sub>b</sub> = 2&radic;( A<sub>Cu</sub> / FF<sub>b</sub> / &pi; )&nbsp;&nbsp;[mm]&nbsp;&nbsp;(single strand: 1.08&middot;d<sub>str</sub>)",
   ["OD<sub>b</sub> — effective bundle diameter; FF<sub>b</sub> — bundle packing factor (default 0.55)"])
EQ("t<sub>pl</sub> = &lfloor;2&pi;&middot;max(r<sub>in</sub>&minus;OD<sub>b</sub>/2, OD<sub>b</sub>)/OD<sub>b</sub>&rfloor;,&nbsp;&nbsp;"
   "N<sub>lay</sub> = &lceil;N/t<sub>pl</sub>&rceil;,&nbsp;&nbsp;r<sub>bore</sub> = r<sub>in</sub> &minus; N<sub>lay</sub>&middot;OD<sub>b</sub>",
   ["t<sub>pl</sub> — turns per bore layer; N<sub>lay</sub> — layers needed; r<sub>bore</sub> — residual bore radius "
    "(negative &rArr; overfull)"])
EQ("K<sub>u</sub> = N&middot;A<sub>Cu</sub> / (&pi;&middot;r<sub>in</sub><super>2</super>)",
   ["K<sub>u</sub> — bore-window utilization, checked against acceptance.Ku_max if supplied"])
EQ("L<sub>guar</sub> = min<sub>corners</sub> L<sub>min</sub>(H<sub>pk</sub>);&nbsp;&nbsp;analytic: L<sub>min</sub>(H) = k(H)&middot;L<sub>0,min</sub>;&nbsp;&nbsp;table: un-derated interp",
   ["H<sub>pk</sub> = 0.4&pi;&middot;N&middot;I<sub>pk,inst</sub>/l<sub>e,cm</sub> — bias at the worst instantaneous peak",
    "checked against acceptance.L_target_uH if supplied"])
EQ("DCM boundary: load where I<sub>c</sub> = &Delta;I<sub>pp</sub>(crest)/2; "
   "waveform flag dcm(&theta;) when i<sub>avg</sub>(&theta;) &lt; &Delta;I<sub>pp</sub>(&theta;)/2",
   ["below the boundary the CCM equations are invalid; the viewer shades the region and warns when "
    "the DCM fraction of the half-cycle exceeds 0.5"])

# ============================ S12 WORST CASE & ACCEPTANCE ============================
H1("S12 — Worst-case scan and acceptance verdict")
B("All operating corners (engine) / all envelope V<sub>in</sub> at spec-max load (viewer) are evaluated; "
  "the scan reports: worst P<sub>tot,max</sub> and its V<sub>in</sub>; worst B<sub>max</sub> (mean path) and "
  "B<sub>inner</sub>; minimum L<sub>guar</sub>; maximum &Delta;T; maximum J; K<sub>u</sub>. Acceptance checks "
  "ONLY limits present in the package (upstream-only — omitted limit &rArr; &lsquo;no upstream limit&rsquo;, "
  "no value invented):")
B("&bull; material anchors reproduce catalog points (skipped for measured fits) &bull; "
  "L<sub>guar</sub> &ge; L_target &bull; B<sub>max</sub> &le; B<sub>max,T</sub> or "
  "(1&minus;sat_margin_min)&middot;B<sub>sat</sub> &bull; B<sub>inner</sub> &le; Binner_max_T (optional) &bull; "
  "FF<sub>Cu</sub> &le; FFcu_limit &bull; d<sub>str</sub> &lt; 2&delta; &bull; &Delta;T &le; T<sub>hot</sub>&minus;T<sub>amb</sub> "
  "(or dT_max_K) &bull; J &le; J_max. Verdict = APPROVE iff every checked assert passes; REJECT otherwise; "
  "NO LIMITS / INSUFFICIENT DATA when nothing checkable.")

# ============================ S13 MEASURED-DATA EQUATIONS ============================
H1("S13 — Measured-data (Tier-3) equations")
EQ("Steinmetz refit: ln P<sub>i</sub> = ln a + b&middot;ln B<sub>i</sub> + c&middot;ln f<sub>i</sub> &nbsp;&rarr;&nbsp; "
   "least-squares solve for (ln a, b, c) over &ge;3 bench points",
   ["points [B<sub>i</sub> (T), f<sub>i</sub> (kHz), P<sub>i</sub> (mW/cm<super>3</super>)] must span B and f"])
EQ("Bias-current conversion: H<sub>i</sub> = 0.4&pi;&middot;N&middot;I<sub>i</sub> / l<sub>e,cm</sub>; "
   "points sorted ascending before interpolation",
   ["lets the lab supply L vs I directly; engine/viewer convert with the design&rsquo;s own N and l<sub>e</sub>"])
EQ("Self-consistency guards (warn, never silently accept): measured Steinmetz vs catalog ratio at "
   "(0.1 T, 100 kHz) outside [0.67, 1.5]; median bench-point ratio outside [0.67, 1.5]; measured "
   "L<sub>0</sub> vs analytic L<sub>0</sub> off by &gt;25 %; measured R<sub>DC</sub> vs geometry off by &gt;2&times;",
   None)

story.append(PageBreak())
# ============================ GLOSSARY ============================
H1("Appendix — Variable glossary")
rows = [["Symbol", "Package / code name", "Unit", "Meaning"]]
G = [
 ["mu0", "MU0", "H/m", "Permeability of free space (4*pi*1e-7)"],
 ["rho20", "copper.rho20_ohm_m", "ohm*m", "Copper resistivity at 20 C"],
 ["alphaCu", "copper.alphaCu", "1/K", "Copper temperature coefficient"],
 ["Vout", "design.Vout", "V", "Boost DC output voltage"],
 ["fsw", "design.fsw", "Hz", "Switching frequency"],
 ["fline", "design.lineHz", "Hz", "AC line frequency"],
 ["nph", "design.nph", "-", "Interleaved phase count"],
 ["Prated", "design.Prated", "W", "Rated output power (map-derived points)"],
 ["Vin, Pout, eta, PF", "operating.points[i]", "V, W, -, -", "Spec-corner line voltage, output power, efficiency, PF"],
 ["Tamb", "environment.Tamb_C", "C", "Worst-case ambient temperature"],
 ["Thot", "environment.Thot_C", "C", "Allowed hotspot temperature"],
 ["N", "winding.N", "turns", "Number of turns"],
 ["nstk", "winding.stacks", "-", "Stacked core count"],
 ["bw", "winding.build_mm", "mm", "Winding build allowance for MLT"],
 ["OD, ID, HT", "geometry.OD/ID/HT_mm", "mm", "Core outer/inner diameter, SINGLE-core height"],
 ["Ae,single", "geometry.Ae_mm2", "mm2", "Effective area of ONE core"],
 ["Le", "geometry.Le_mm", "mm", "Magnetic path length (le_cm = Le/10)"],
 ["Ve,single", "geometry.Ve_mm3", "mm3", "Volume of ONE core"],
 ["Wa", "geometry.Wa_mm2", "mm2", "Window area"],
 ["AL,single", "geometry.AL_nH", "nH/T2", "Inductance factor of ONE core, zero bias"],
 ["tolAL", "geometry.AL_tol", "-", "AL tolerance fraction (analytic derate only)"],
 ["Bsat", "material.Bsat", "T", "Saturation flux density"],
 ["a, b, c", "material.steinmetz", "-", "Core-loss fit P=a*B^b*f_kHz^c (mW/cm3)"],
 ["k0, k1, p", "material.retention", "-", "DC-bias fit %mu = 1/(k0+k1*H_Oe^p)"],
 ["smax", "material.lossMaxScale", "-", "Max/typ core-loss band (default 1.286)"],
 ["dstr", "copper.wire.strandDia_mm", "mm", "Bare strand diameter"],
 ["nstr, npar", "wire.strands / parallel", "-", "Strands per bundle / parallel bundles"],
 ["FFb", "wire.fillFactor", "-", "Bundle packing factor (bundle OD)"],
 ["kskin,kprox,kcrowd", "copper.prox", "-", "Viewer analytic R_AC stand-in hyperparameters"],
 ["FR", "copper.RacRdc / fields.windingAC", "-", "AC/DC resistance ratio at fsw"],
 ["Rmeas20", "copper.measured.RdcTotal_20C", "ohm", "Measured total DCR at 20 C (T3)"],
 ["theta", "(internal)", "rad", "Line half-cycle angle, grid over (0, pi)"],
 ["D", "(internal)", "-", "Boost duty ratio 1 - vin/Vout"],
 ["Ic", "(internal Iphi_crest)", "A", "Per-phase crest current"],
 ["dIpp", "(internal)", "A", "Peak-to-peak switching ripple"],
 ["H", "(internal)", "Oe", "Bias field 0.4*pi*N*I/le_cm"],
 ["k(H)", "(internal)", "-", "Permeability retention at bias H"],
 ["L0 / L(H)", "statics.L0_*_uH / points.L_nom_uH", "H, uH", "Unbiased / bias-corrected inductance"],
 ["Bac,pk", "points.Bac_crest", "T", "Half of pk-pk AC flux swing"],
 ["Bmax", "worst.Bmax.Bmax", "T", "Worst mean-path instantaneous peak flux"],
 ["Binner", "worst.Binner.B_inner", "T", "Crowded inner-radius peak flux"],
 ["crowd", "statics.crowd_peak", "-", "Inner-radius crowding ratio rmean/rin (or FEA)"],
 ["MLT", "statics.MLT_mm", "mm", "Mean length per turn"],
 ["lCu", "statics.ell_cu_m", "m", "Total conductor length"],
 ["ACu", "(internal A_cu_mm2)", "mm2", "Total copper cross-section"],
 ["RDC(T)", "statics.DCR25/100_mohm", "mohm", "DC resistance at temperature T"],
 ["delta", "statics.skin_depth_mm", "mm", "Skin depth at fsw"],
 ["kharm", "(internal ~1.213)", "-", "Harmonic excess factor, triangular ripple"],
 ["Irms,LF/HF", "points.Iphi_rms / Irms_HF", "A", "Line / ripple RMS components"],
 ["PCu", "points.Pcu25/Pcu100", "W", "Copper loss at 25/100 C"],
 ["Fd(D)", "(internal F_D)", "-", "Duty correction for core loss"],
 ["Pcore(,max)", "points.Pcore / Pcore_max", "W", "Cycle-avg core loss, typ / max band"],
 ["Ptot", "points.Ptot_typ/_max", "W", "Total loss per corner"],
 ["SA", "statics.SA_cm2", "cm2", "Wound-part surface area"],
 ["dT", "points.dT / worst.dT", "K", "Temperature rise (correlation, nodes, or CFD)"],
 ["Rca,Rwa,Rcw", "fields.thermal.nodes", "K/W", "Core-amb / winding-amb / core-winding resistances"],
 ["ODb", "windowGeom.bundleOD", "mm", "Effective bundle diameter"],
 ["Nlay, tpl", "windowGeom.layersNeeded/turnsPerLayer", "-", "Bore layers / turns per layer"],
 ["Ku", "windowGeom.Ku", "-", "Bore utilization N*ACu/(pi*rin^2)"],
 ["J", "statics.J_AperMM2", "A/mm2", "Copper current density"],
 ["Lguar", "worst.Lmin_guarantee_uH", "uH", "Guaranteed minimum inductance at worst bias"],
 ["FFCu", "statics.FFcu", "-", "Bare-copper window fill N*ACu/Wa"],
 ["provenance/tier", "result.provenance / tier", "-", "Per-quantity source: input-T0, analytic-T1, fea-T2, measured-T3"],
]
for g in G: rows.append(g)
tbl = Table(rows, colWidths=[30*mm, 52*mm, 18*mm, 72*mm], repeatRows=1)
tbl.setStyle(TableStyle([
    ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#1a3a5c')),
    ('TEXTCOLOR', (0,0), (-1,0), colors.white),
    ('FONTNAME', (0,0), (-1,0), BOLD),
    ('FONTSIZE', (0,0), (-1,-1), 7.4),
    ('FONTNAME', (0,1), (-1,-1), BODY),
    ('GRID', (0,0), (-1,-1), 0.4, colors.HexColor('#b9c4cf')),
    ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#eef3f7')]),
    ('VALIGN', (0,0), (-1,-1), 'TOP'),
    ('LEFTPADDING', (0,0), (-1,-1), 3), ('RIGHTPADDING', (0,0), (-1,-1), 3),
    ('TOPPADDING', (0,0), (-1,-1), 1.6), ('BOTTOMPADDING', (0,0), (-1,-1), 1.6),
]))
story.append(tbl)
story.append(Spacer(1, 8))
B("<i>Honest status note: F<sub>R</sub> (E31/E32), the thermal correlations (E46&ndash;E52), and the "
  "analytic L(H) (E7&ndash;E8) are Tier-1 stand-ins. They are replaced — per quantity, with provenance — when "
  "solved FEA/CFD data arrives in <b>fields</b> or measured bench data arrives in "
  "<b>material.measured / copper.measured</b>. Everything else above is exact arithmetic on the "
  "injected package values.</i>")

doc = SimpleDocTemplate("/mnt/user-data/outputs/PFC_Inductor_Engine_Equations.pdf",
                        pagesize=letter, topMargin=16*mm, bottomMargin=15*mm,
                        leftMargin=16*mm, rightMargin=16*mm,
                        title="PFC Boost Inductor Engine — Equation Reference",
                        author="Magnetics design pipeline")
doc.build(story)
print("PDF built, equations:", _eqn[0])
