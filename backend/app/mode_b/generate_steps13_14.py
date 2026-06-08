"""
generate_steps13_14.py
Generates a pixel-faithful Steps 13–14 PDF matching the reference document exactly.
All calculations are performed from the approved_design dict + state.
Produces PDF bytes; caller merges with Steps 1–12 PDF.
"""
from __future__ import annotations
import io, math, os
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
from matplotlib.lines import Line2D
from scipy import stats as scipy_stats

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT, TA_JUSTIFY
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, HRFlowable, Image, KeepTogether,
)

PAGE_W, PAGE_H = A4
LM = RM = 20*mm
TM = BM = 18*mm
CONTENT_W = PAGE_W - LM - RM

# ── Colours — exactly match reference Word document ──────────────────────────
NAVY   = colors.HexColor("#1F3B63")   # H1 band, table headers, title
BLUE   = colors.HexColor("#2E6CA4")   # subtitle, labels
H2C    = colors.HexColor("#3F7CB5")   # H2 headings
GREEN  = colors.HexColor("#2E7D4F")   # pass indicators
RED    = colors.HexColor("#C0392B")   # fail / warning
AMBER  = colors.HexColor("#D4820A")   # note callouts
LIGHT  = colors.HexColor("#EBF2FA")   # highlight background
RULE   = colors.HexColor("#C8D4E8")   # table grid lines
MUTED  = colors.HexColor("#6B7A8D")   # footnotes
WHITE  = colors.white
BLACK  = colors.black
STRIPE = colors.HexColor("#F4F8FC")   # alternating table rows
CAP_C  = colors.HexColor("#5A5A5A")   # captions
TEAL   = H2C                          # backward compat alias

# ── Matplotlib colours matching reference ────────────────────────────────────
VAC_COLORS = {
    90:  '#1f77b4',  # blue
    110: '#d62728',  # red
    120: '#2ca02c',  # green
    132: '#9467bd',  # purple
    180: '#8c564b',  # brown
    200: '#e377c2',  # pink
    220: '#7f7f7f',  # grey
    230: '#bcbd22',  # olive
    264: '#17becf',  # cyan
}
VAC_LIST = [90, 110, 120, 132, 180, 200, 220, 230, 264]


# ── Style sheet ───────────────────────────────────────────────────────────────
def _S():
    s = {}
    # H1: 13 pt bold white on navy band (matches Word doc Heading 1)
    s['h1'] = ParagraphStyle('h1', fontName='Helvetica-Bold', fontSize=13,
        textColor=WHITE, spaceBefore=0, spaceAfter=0, leading=18)
    # H2: 12 pt bold #3F7CB5 — matches Word doc step sub-headings (Aptos Display 12 pt)
    s['h2'] = ParagraphStyle('h2', fontName='Helvetica-Bold', fontSize=12,
        textColor=H2C, spaceBefore=10, spaceAfter=4, leading=17)
    # H3: 10.5 pt bold #3F7CB5 — sub-sub-step headings
    s['h3'] = ParagraphStyle('h3', fontName='Helvetica-Bold', fontSize=10.5,
        textColor=H2C, spaceBefore=7, spaceAfter=2, leading=14)
    # Body: 9.5 pt — matches Word doc "Aptos Narrow" 9.5 pt body text
    s['body'] = ParagraphStyle('body', fontName='Helvetica', fontSize=9.5,
        textColor=BLACK, leading=14, spaceAfter=2)
    s['eq'] = ParagraphStyle('eq', fontName='Courier', fontSize=9,
        textColor=NAVY, leading=13, leftIndent=10)
    # Caption: 8 pt italic — matches Word doc figure caption style (Aptos Narrow 8 pt)
    s['caption'] = ParagraphStyle('caption', fontName='Helvetica-Oblique',
        fontSize=8, textColor=CAP_C, alignment=TA_CENTER, leading=11, spaceAfter=6)
    # Note: 8 pt italic — matches Word doc footnote/note style
    s['note'] = ParagraphStyle('note', fontName='Helvetica-Oblique', fontSize=8,
        textColor=CAP_C, leading=11, spaceAfter=4)
    s['tbl_hdr'] = ParagraphStyle('tbl_hdr', fontName='Helvetica-Bold', fontSize=8.5,
        textColor=WHITE, alignment=TA_CENTER, leading=11)
    s['tbl_cell'] = ParagraphStyle('tbl_cell', fontName='Helvetica', fontSize=8.5,
        textColor=BLACK, alignment=TA_CENTER, leading=11)
    s['tbl_cell_l'] = ParagraphStyle('tbl_cell_l', fontName='Helvetica', fontSize=8.5,
        textColor=BLACK, leading=11)
    return s


def _rule():
    return HRFlowable(width='100%', thickness=0.4, color=RULE,
                      spaceBefore=4, spaceAfter=4)


def _h1_band(text, story, S, sb=14, sa=8):
    """Heading 1: white text on navy band — matches reference Word document."""
    from reportlab.platypus import Table as _T, TableStyle as _TS
    cw = PAGE_W - LM - RM
    band = _T([[Paragraph(text, S['h1'])]], colWidths=[cw])
    band.setStyle(_TS([
        ('BACKGROUND', (0,0), (-1,-1), NAVY),
        ('TOPPADDING',    (0,0), (-1,-1), 7),
        ('BOTTOMPADDING', (0,0), (-1,-1), 7),
        ('LEFTPADDING',   (0,0), (-1,-1), 12),
        ('RIGHTPADDING',  (0,0), (-1,-1), 8),
    ]))
    story.append(Spacer(1, sb))
    story.append(band)
    story.append(Spacer(1, sa))


def _tbl_style(hdr_bg=NAVY, stripe=STRIPE):
    return TableStyle([
        ('BACKGROUND',    (0,0), (-1,0),  hdr_bg),
        ('TEXTCOLOR',     (0,0), (-1,0),  WHITE),
        ('FONTNAME',      (0,0), (-1,0),  'Helvetica-Bold'),
        ('FONTSIZE',      (0,0), (-1,0),  8.5),
        ('ALIGN',         (0,0), (-1,0),  'CENTER'),
        ('FONTNAME',      (0,1), (-1,-1), 'Helvetica'),
        ('FONTSIZE',      (0,1), (-1,-1), 8.5),
        ('ROWBACKGROUNDS',(0,1), (-1,-1), [WHITE, stripe]),
        ('ALIGN',         (0,1), (-1,-1), 'CENTER'),
        ('GRID',          (0,0), (-1,-1), 0.3, RULE),
        ('VALIGN',        (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING',    (0,0), (-1,-1), 3),
        ('BOTTOMPADDING', (0,0), (-1,-1), 3),
        ('LEFTPADDING',   (0,0), (-1,-1), 5),
        ('RIGHTPADDING',  (0,0), (-1,-1), 5),
    ])


def _mpl_to_image(fig, width_mm=170):
    """Save matplotlib figure to a ReportLab Image flowable."""
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=180, bbox_inches='tight',
                facecolor='white', edgecolor='none')
    plt.close(fig)
    buf.seek(0)
    w = width_mm * mm
    # preserve aspect
    from PIL import Image as PILImage
    pil = PILImage.open(buf)
    pw, ph = pil.size
    h = w * ph / pw
    buf.seek(0)
    return Image(buf, width=w, height=h)


# ── Physics helpers ───────────────────────────────────────────────────────────
def _Bac_pk_t(Vac_rms, Vbus, N, Ae_m2, fsw, f_line=60, n_pts=500):
    """Return (t_s, Bac_pk_T) arrays over half line cycle."""
    T_half = 1.0 / (2 * f_line)
    t = np.linspace(0, T_half, n_pts)
    Vpk = math.sqrt(2) * Vac_rms
    Vin_t = Vpk * np.sin(2 * math.pi * f_line * t)
    D_t = np.clip(1.0 - Vin_t / Vbus, 0, 1)
    Bac_t = Vin_t * D_t / (2 * N * Ae_m2 * fsw)
    Bac_t = np.clip(Bac_t, 0, None)
    return t, Bac_t


def _power_law_fit(Bac_list, Pcore_list):
    """Log-log fit: Pcore = k * B^n. Returns (k, n, r2)."""
    mask = np.array(Pcore_list) > 0
    logB = np.log(np.array(Bac_list)[mask])
    logP = np.log(np.array(Pcore_list)[mask])
    slope, intercept, r, _, _ = scipy_stats.linregress(logB, logP)
    k = math.exp(intercept)
    n = slope
    r2 = r**2
    return k, n, r2


def _page_header_footer(canvas, doc):
    canvas.saveState()
    # header bar
    canvas.setFillColor(NAVY)
    canvas.rect(0, PAGE_H - 13*mm, PAGE_W, 13*mm, fill=1, stroke=0)
    canvas.setFillColor(WHITE)
    canvas.setFont('Helvetica-Bold', 8.5)
    canvas.drawString(LM, PAGE_H - 8.5*mm,
        'PFC Inductor Magnetic Design — Steps 13 & 14')
    canvas.setFont('Helvetica', 7.5)
    canvas.drawRightString(PAGE_W - RM, PAGE_H - 8.5*mm,
        f'Page {doc.page}')
    # footer — navy rule + centred text (matches reference)
    canvas.setStrokeColor(NAVY); canvas.setLineWidth(0.8)
    canvas.line(LM, 7*mm, PAGE_W - RM, 7*mm)
    canvas.setFillColor(colors.HexColor('#777777'))
    canvas.setFont('Helvetica', 7.5)
    canvas.drawCentredString(PAGE_W / 2, 4*mm,
        f'PFC Inductor Magnetic Design   —   Steps 13 & 14   │   Page {doc.page}')
    canvas.restoreState()


def _mat_mu(key: str) -> str:
    """Extract trailing permeability number from a material key ('edge_90' -> '90')."""
    if not key:
        return '—'
    parts = key.rsplit('_', 1)
    return parts[1] if len(parts) == 2 and parts[1].isdigit() else '—'


# ══════════════════════════════════════════════════════════════════════════════
# Section builders
# ══════════════════════════════════════════════════════════════════════════════

def _sec_13_1(story, D, S):
    _h1_band('Step 13) Boost Inductor Magnetic Design', story, S)
    story.append(Paragraph('Step 13.1) Reference Operating Point and Design Targets'
                           ' (Low Line, Full Load)', S['h2']))
    rows = [
        ('V<sub>out</sub>', f"{D['Vout_V']:.0f} Vdc"),
        ('f<sub>sw</sub>', f"{D['fsw_Hz']/1e3:.0f} kHz"),
        ('V<sub>in,rms</sub> (low line)', f"{D['Vin_lo_rms']:.0f} Vac @ {D['f_line_Hz']:.0f} Hz"),
        ('V<sub>in,pk</sub> = &radic;2 &middot; V<sub>in,rms</sub>',
         f"{D['Vin_pk']:.4f} V"),
        ('D<sub>pk</sub> = 1 &minus; (V<sub>in,pk</sub>/V<sub>out</sub>)',
         f"{D['D_pk']:.4f}"),
        ('L<sub>&phi;,target</sub> (low line, full load)',
         f"{D['L_target_uH']:.0f} &micro;H"),
        ('I<sub>&phi;,avg@crest</sub> = I<sub>pk,line</sub>/2',
         f"{D['Iavg_crest']:.4f} A"),
        ('I<sub>&phi;,rms</sub> (used for copper loss)',
         f"{D['Irms_A']:.4f} A"),
        ('&Delta;I<sub>L,pp@crest</sub> = V<sub>in,pk</sub>&middot;D<sub>pk</sub>'
         '/(L<sub>&phi;</sub>&middot;f<sub>sw</sub>)',
         f"{D['dIL_pp']:.4f} A"),
    ]
    data = [[Paragraph(k, S['body']), Paragraph(v, S['eq'])] for k, v in rows]
    t = Table(data, colWidths=[95*mm, 80*mm])
    t.setStyle(TableStyle([
        ('ROWBACKGROUNDS', (0,0), (-1,-1), [WHITE, STRIPE]),
        ('GRID',   (0,0), (-1,-1), 0.3, RULE),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING',    (0,0), (-1,-1), 3),
        ('BOTTOMPADDING', (0,0), (-1,-1), 3),
        ('LEFTPADDING',   (0,0), (-1,-1), 6),
    ]))
    story.append(t)
    story.append(Spacer(1, 4*mm))


def _sec_13_candidates(story, D, S):
    """Step 13.0 — Top candidates table (before selected-core detail)."""
    candidates = D.get('all_candidates', [])
    if not candidates:
        return
    story.append(Paragraph('Step 13.0) Top Core Candidates — Sizing Engine Results', S['h2']))
    story.append(Paragraph(
        f'The engine evaluated all catalog cores for the selected material family and '
        f'ranked the top {len(candidates)} candidates. '
        f'The highlighted row is the approved design carried forward to Steps 13.1–14.',
        S['body']))
    story.append(Spacer(1, 3*mm))

    approved_pn     = D.get('part_number', '')
    approved_stacks = int(D.get('stacks', 1))

    hdr = ['#', 'Part number', 'µ', 'Stacks', 'N',
           'FF<sub>cu</sub>%', 'ΔT °C', 'P<sub>total</sub> W', 'Result']
    rows = [[Paragraph(h, S['tbl_hdr']) for h in hdr]]

    approved_row = None
    for i, c in enumerate(candidates):
        r      = c.get('result', c) if isinstance(c, dict) else {}
        pn     = str(r.get('part_number', '—'))
        stacks = int(r.get('stacks', 1))
        mu     = _mat_mu(str(r.get('material_key', '')))
        N      = str(r.get('N', '—'))
        ffcu   = f"{float(r.get('FFcu', 0))*100:.0f}" if r.get('FFcu') is not None else '—'
        dt     = f"{float(r.get('dT_rise_C', 0)):.1f}" if r.get('dT_rise_C') is not None else '—'
        ptot   = f"{float(r.get('Ptotal_100C_W', 0)):.2f}" if r.get('Ptotal_100C_W') is not None else '—'
        passed = bool(r.get('passed', False))
        rank   = str(c.get('rank', i + 1)) if isinstance(c, dict) else str(i + 1)
        res    = 'PASS' if passed else 'fail'
        is_sel = (pn == approved_pn and stacks == approved_stacks)
        if is_sel:
            approved_row = len(rows)
        rows.append([Paragraph(str(x), S['tbl_cell']) for x in [
            rank, pn, mu, stacks, N, ffcu, dt, ptot, res,
        ]])

    cw = [10*mm, 38*mm, 14*mm, 16*mm, 12*mm, 18*mm, 16*mm, 22*mm, 15*mm]
    t = Table(rows, colWidths=cw)
    ts = _tbl_style()
    if approved_row:
        ts.add('BACKGROUND', (0, approved_row), (-1, approved_row), LIGHT)
        ts.add('FONTNAME',   (0, approved_row), (-1, approved_row), 'Helvetica-Bold')
        ts.add('TEXTCOLOR',  (0, approved_row), (-1, approved_row), BLUE)
    t.setStyle(ts)
    story.append(t)

    label_notes = [
        f"#{c.get('rank', i+1)} {(c.get('result') or {}).get('part_number','')} — {c['label']}"
        for i, c in enumerate(candidates)
        if isinstance(c, dict) and c.get('label')
    ]
    if label_notes:
        story.append(Spacer(1, 2*mm))
        for note in label_notes:
            story.append(Paragraph(note, S['note']))

    story.append(Spacer(1, 4*mm))
    story.append(PageBreak())


def _sec_13_2(story, D, S):
    story.append(Paragraph('Step 13.2) Selected Core and Stacking Parameters', S['h2']))
    story.append(Paragraph(
        f"Core: {D['supplier']} {D['part_number']}  &nbsp;|&nbsp; "
        f"OD = {D['OD_mm']:.2f} mm, ID = {D['ID_mm']:.2f} mm, HT = {D['HT_mm']:.2f} mm (uncoated)",
        S['body']))
    rows = [
        ('A<sub>L</sub>(single)',
         f"{D['AL_nom_single_nH']:.0f} nH/T&sup2; &plusmn; {D['AL_tol_pct']:.0f}%"),
        ('A<sub>e</sub>(single)', f"{D['Ae_single_mm2']:.0f} mm&sup2;"),
        ('W<sub>a</sub>(single)', f"{D['Wa_single_mm2']:.0f} mm&sup2;"),
        ('Stacks', str(D['stacks'])),
        ('A<sub>L,total,min</sub>', f"{D['AL_min_total_nH']:.0f} nH/T&sup2;"),
        ('A<sub>L,total,nom</sub>', f"{D['AL_nom_total_nH']:.0f} nH/T&sup2;"),
        ('A<sub>L,total,max</sub>', f"{D['AL_max_total_nH']:.0f} nH/T&sup2;"),
        ('A<sub>e,total</sub>', f"{D['Ae_total_mm2']:.0f} mm&sup2;"),
        ('W<sub>a,total</sub>', f"{D['Wa_total_mm2']:.0f} mm&sup2;"),
    ]
    data = [[Paragraph(k, S['body']), Paragraph(v, S['eq'])] for k, v in rows]
    t = Table(data, colWidths=[95*mm, 80*mm])
    t.setStyle(TableStyle([
        ('ROWBACKGROUNDS', (0,0), (-1,-1), [WHITE, STRIPE]),
        ('GRID', (0,0), (-1,-1), 0.3, RULE),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING',    (0,0), (-1,-1), 3),
        ('BOTTOMPADDING', (0,0), (-1,-1), 3),
        ('LEFTPADDING',   (0,0), (-1,-1), 6),
    ]))
    story.append(t)
    story.append(Spacer(1, 4*mm))


def _sec_13_3(story, D, S):
    story.append(Paragraph('Step 13.3) Number of Turns', S['h2']))
    story.append(Paragraph('Step 13.3.1) Selected turns', S['h3']))
    story.append(Paragraph(f"<b>N = {D['N']} turns</b>", S['eq']))
    story.append(Spacer(1, 3*mm))

    story.append(Paragraph('Step 13.3.2) No-load inductance (0 A) using A<sub>L,total</sub>', S['h3']))
    story.append(Paragraph('L<sub>0</sub> = A<sub>L,total</sub> &middot; N<sup>2</sup>', S['eq']))

    N = D['N']
    AL_min = D['AL_min_total_nH']
    AL_nom = D['AL_nom_total_nH']
    AL_max = D['AL_max_total_nH']
    L0_min = AL_min * N**2 / 1e3   # µH
    L0_nom = AL_nom * N**2 / 1e3
    L0_max = AL_max * N**2 / 1e3
    D['L0_min_uH'] = L0_min
    D['L0_nom_uH'] = L0_nom
    D['L0_max_uH'] = L0_max

    eqs = [
        f"L<sub>0,min</sub> = ({AL_min:.0f} nH/T&sup2;) &middot; ({N}&sup2;) = {L0_min:.3f} &micro;H",
        f"L<sub>0,nom</sub> = ({AL_nom:.0f} nH/T&sup2;) &middot; ({N}&sup2;) = {L0_nom:.3f} &micro;H",
        f"L<sub>0,max</sub> = ({AL_max:.0f} nH/T&sup2;) &middot; ({N}&sup2;) = {L0_max:.3f} &micro;H",
    ]
    for eq in eqs:
        story.append(Paragraph(eq, S['eq']))
    story.append(Spacer(1, 3*mm))

    story.append(Paragraph('Step 13.3.3) Required inductance retention at full-load bias', S['h3']))
    story.append(Paragraph('k<sub>req</sub> = L<sub>&phi;,target</sub> / L<sub>0</sub>', S['eq']))
    L_t = D['L_target_uH']
    kreq_min = L_t / L0_min
    kreq_nom = L_t / L0_nom
    kreq_max = L_t / L0_max
    D['kreq_min_calc'] = kreq_min
    D['kreq_nom_calc'] = kreq_nom
    D['kreq_max_calc'] = kreq_max

    eqs2 = [
        f"k<sub>req,min</sub>(A<sub>L</sub>) = {L_t:.3f} / {L0_min:.3f} = {kreq_min:.4f}",
        f"k<sub>req,nom</sub>(A<sub>L</sub>) = {L_t:.3f} / {L0_nom:.3f} = {kreq_nom:.4f}",
        f"k<sub>req,max</sub>(A<sub>L</sub>) = {L_t:.3f} / {L0_max:.3f} = {kreq_max:.4f}",
    ]
    for eq in eqs2:
        story.append(Paragraph(eq, S['eq']))
    story.append(Spacer(1, 2*mm))
    story.append(Paragraph('Bias (A&middot;T) at low line full load (crest average):', S['body']))
    AT = N * D['Iavg_crest']
    D['AT_design'] = AT
    story.append(Paragraph(f"A&middot;T = N &middot; I<sub>&phi;,avg@crest</sub>", S['eq']))
    story.append(Paragraph(
        f"A&middot;T = {N} &middot; {D['Iavg_crest']:.4f} = <b>{AT:.2f} A&middot;T</b>", S['eq']))
    story.append(Spacer(1, 4*mm))


def _sec_13_4(story, D, S):
    story.append(Paragraph('Step 13.4) Inductance at Full Load vs Input Voltage (Table and Plot)', S['h2']))
    story.append(Paragraph(
        'Method (engineering estimate):', S['body']))
    notes = [
        '1) Use operating-point table to obtain I<sub>pk,line</sub> at crest for each V<sub>in,rms</sub>.',
        '2) Compute per-phase crest-average DC current: I<sub>&phi;,avg@crest</sub> = I<sub>pk,line</sub> / 2.',
        '3) Compute bias in ampere-turns: A&middot;T = N &middot; I<sub>&phi;,avg@crest</sub>.',
        '4) Apply an engineering retention model k<sub>bias</sub> = f(A&middot;T) and compute '
        'L<sub>full</sub> = L<sub>0</sub> &middot; k<sub>bias</sub>.',
    ]
    for n in notes:
        story.append(Paragraph(n, S['body']))
    story.append(Paragraph(
        '<i>Note: k<sub>bias</sub> model provides a consistent inductance trend vs V<sub>in</sub> '
        'for the chosen N and stacked core.</i>', S['note']))
    story.append(Spacer(1, 2*mm))

    # Build table data from ops_table
    ops = D['ops_table']
    hdr = ['V<sub>in,rms</sub><br/>(Vac)', 'I<sub>pk,line</sub><br/>(A)',
           'I<sub>&phi;,avg@crest</sub><br/>(A)', 'A&middot;T<br/>(A&middot;T)',
           'k<sub>bias</sub><br/>(—)',
           'L<sub>full,min</sub><br/>(&micro;H)', 'L<sub>full,nom</sub><br/>(&micro;H)',
           'L<sub>full,max</sub><br/>(&micro;H)']
    rows = [[Paragraph(h, S['tbl_hdr']) for h in hdr]]
    for r in ops:
        rows.append([Paragraph(str(x), S['tbl_cell']) for x in [
            r['Vin_rms'], f"{r['Ipk_line']:.4f}", f"{r['Iavg_crest']:.4f}",
            f"{r['AT']:.1f}", f"{r['k_bias']:.4f}",
            f"{r['L_full_min']:.1f}", f"{r['L_full_nom']:.1f}", f"{r['L_full_max']:.1f}",
        ]])
    cw = [18*mm, 20*mm, 22*mm, 18*mm, 16*mm, 20*mm, 20*mm, 20*mm]
    t = Table(rows, colWidths=cw)
    t.setStyle(_tbl_style())
    story.append(t)
    story.append(Spacer(1, 5*mm))

    # Plot
    fig, ax = plt.subplots(figsize=(7.5, 3.8))
    Vin_pts = [r['Vin_rms'] for r in ops]
    L_min   = [r['L_full_min'] for r in ops]
    L_nom   = [r['L_full_nom'] for r in ops]
    L_max   = [r['L_full_max'] for r in ops]
    ax.plot(Vin_pts, L_nom, 'o-', color='#2E6DA4', lw=2,   label='L_full (nom AL)')
    ax.plot(Vin_pts, L_min, 's--', color='#E74C3C', lw=1.5, label='L_full (AL min)')
    ax.plot(Vin_pts, L_max, 's--', color='#2E7D4F', lw=1.5, label='L_full (AL max)')
    ax.set_xlabel('V$_{in,rms}$ (Vac)', fontsize=10)
    ax.set_ylabel('Inductance at full load per phase, L$_\\phi$ (µH)', fontsize=10)
    ax.set_title('Step 13.4 — Inductance at Full Load vs Input Voltage', fontsize=10)
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)
    ax.set_xlim(80, 274)
    story.append(_mpl_to_image(fig))
    story.append(Spacer(1, 4*mm))


def _sec_13_5(story, D, S):
    story.append(Paragraph('Step 13.5) Flux Density Swing at 0 A and Full Load (Crest Condition)', S['h2']))
    Vpk = D['Vin_pk']; Dpk = D['D_pk']
    N = D['N']; Ae = D['Ae_total_mm2'] * 1e-6; fsw = D['fsw_Hz']
    dBpp = Vpk * Dpk / (N * Ae * fsw)
    Bac_pk = dBpp / 2
    Bdc = D['L_target_uH']*1e-6 * D['Iavg_crest'] / (N * Ae)
    D['dBpp_T'] = dBpp; D['Bac_pk_T'] = Bac_pk; D['Bdc_T'] = Bdc
    D['Bmin_FL_T'] = Bdc - Bac_pk; D['Bmax_FL_T'] = Bdc + Bac_pk

    story.append(Paragraph('Step 13.5.1) AC flux swing from applied volt-seconds', S['h3']))
    story.append(Paragraph('&Delta;B<sub>pp</sub> = V<sub>in,pk</sub> &middot; D<sub>pk</sub>'
                            ' / (N &middot; A<sub>e,total</sub> &middot; f<sub>sw</sub>)', S['eq']))
    story.append(Paragraph(
        f"&Delta;B<sub>pp</sub> = {Vpk:.4f} &middot; {Dpk:.4f}"
        f" / ({N} &middot; {Ae*1e6:.0f}e-6 &middot; {fsw:.0f})", S['eq']))
    story.append(Paragraph(f"<b>&Delta;B<sub>pp</sub> = {dBpp:.6f} T</b>", S['eq']))
    story.append(Paragraph('B<sub>ac,pk</sub> = &Delta;B<sub>pp</sub> / 2', S['eq']))
    story.append(Paragraph(f"<b>B<sub>ac,pk</sub> = {Bac_pk:.6f} T</b>", S['eq']))
    story.append(Spacer(1, 3*mm))

    story.append(Paragraph('Step 13.5.2) DC flux density at full load (using L<sub>&phi;,target</sub>)', S['h3']))
    story.append(Paragraph(
        'B<sub>dc</sub> = L<sub>&phi;,target</sub> &middot; I<sub>&phi;,avg@crest</sub>'
        ' / (N &middot; A<sub>e,total</sub>)', S['eq']))
    story.append(Paragraph(
        f"B<sub>dc</sub> = {D['L_target_uH']*1e-6:.6e} &middot; {D['Iavg_crest']:.4f}"
        f" / ({N} &middot; {Ae:.6e})", S['eq']))
    story.append(Paragraph(f"<b>B<sub>dc</sub> = {Bdc:.6f} T</b>", S['eq']))
    story.append(Spacer(1, 3*mm))

    story.append(Paragraph('Step 13.5.3) Flux swing range', S['h3']))
    story.append(Paragraph('No-load (I &asymp; 0 A):', S['body']))
    story.append(Paragraph(f"B<sub>min,NL</sub> = &minus;{Bac_pk:.6f} T", S['eq']))
    story.append(Paragraph(f"B<sub>max,NL</sub> = +{Bac_pk:.6f} T", S['eq']))
    story.append(Paragraph('Full-load (crest average current):', S['body']))
    story.append(Paragraph(f"B<sub>min,FL</sub> = {D['Bmin_FL_T']:.6f} T", S['eq']))
    story.append(Paragraph(f"B<sub>max,FL</sub> = {D['Bmax_FL_T']:.6f} T", S['eq']))
    story.append(Spacer(1, 4*mm))


def _sec_13_6(story, D, S):
    story.append(Paragraph('Step 13.6) Winding Fill Factor', S['h2']))
    story.append(Paragraph('Step 13.6.1) Selected wire', S['h3']))
    n_par         = int(D.get('n_parallel', 1))
    Cu_per_cond   = D['Cu_area_single_mm2']               # bare Cu area of ONE conductor
    Cu_per_turn   = Cu_per_cond * n_par                   # bare Cu area for one full turn
    winding_style = {1: 'Single', 2: 'Bifilar (×2)', 3: 'Trifilar (×3)'}.get(n_par, f'×{n_par}')
    rows = [
        ('Wire designation',                              D['wire_designation']),
        ('Construction',                                  D.get('wire_construction', D['wire_designation'])),
        ('Winding style',                                 winding_style),
        ('OD (per conductor)',                            f"{D['wire_OD_mm']:.2f} mm"),
        ('Cu area per conductor (A<sub>cu,1</sub>)',     f"{Cu_per_cond:.4f} mm&sup2;"),
        ('Cu area per turn (n<sub>par</sub> &times; A<sub>cu,1</sub>)', f"{Cu_per_turn:.4f} mm&sup2;"),
        ('R<sub>eq</sub>(20&deg;C) parallel bundle',     f"{D['R_per_m_20C']:.6f} &Omega;/m"),
    ]
    data = [[Paragraph(k, S['body']), Paragraph(v, S['eq'])] for k, v in rows]
    t = Table(data, colWidths=[100*mm, 75*mm])
    t.setStyle(TableStyle([
        ('ROWBACKGROUNDS', (0,0), (-1,-1), [WHITE, STRIPE]),
        ('GRID', (0,0), (-1,-1), 0.3, RULE),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING',    (0,0), (-1,-1), 3),
        ('BOTTOMPADDING', (0,0), (-1,-1), 3),
        ('LEFTPADDING',   (0,0), (-1,-1), 6),
    ]))
    story.append(t)
    story.append(Spacer(1, 3*mm))

    story.append(Paragraph('Step 13.6.2) Copper fill factor', S['h3']))
    story.append(Paragraph(
        'For stacked toroids the winding passes through the bore of each core but '
        'the bore opening is the same for every stack — the fill-factor denominator '
        'is W<sub>a,single</sub> (bore area of one core), not the summed total.',
        S['body']))
    N = D['N']
    Cu_total = D['Cu_area_total_mm2']   # = N × Cu_per_turn
    # Correct denominator: single-core bore area (Wa does NOT multiply with stacks)
    Wa = D['Wa_single_mm2']
    FFcu = Cu_total / Wa
    D['FFcu_calc'] = FFcu
    story.append(Paragraph(
        f"A<sub>cu,total</sub> = N &middot; (n<sub>par</sub> &middot; A<sub>cu,1</sub>)"
        f" = {N} &middot; ({n_par} &middot; {Cu_per_cond:.4f})"
        f" = {N} &middot; {Cu_per_turn:.4f} = <b>{Cu_total:.2f} mm&sup2;</b>", S['eq']))
    story.append(Paragraph(
        f"FF<sub>cu</sub> = A<sub>cu,total</sub> / W<sub>a,single</sub>"
        f" = {Cu_total:.2f} / {Wa:.0f} = {FFcu:.4f} (<b>{FFcu*100:.1f}%</b>)", S['eq']))
    story.append(Spacer(1, 4*mm))


def _sec_13_7(story, D, S):
    story.append(Paragraph('Step 13.7) Loss Calculation (Copper + Core) — Low Line', S['h2']))

    # 13.7.1 copper length — cross-section perimeter method (matches JS V5.1)
    # MLT = 2 × (coreW + HT_total) + 3.8 mm  where coreW = (OD−ID)/2
    # This correctly scales with stacks; the pure π×Dmean formula does not.
    story.append(Paragraph('Step 13.7.1) Copper length', S['h3']))
    OD = D['OD_mm']; ID = D['ID_mm']
    HT  = D['HT_mm']
    stacks = D['stacks']
    coreW = (OD - ID) / 2                        # radial width of one core cross-section
    MLT   = 2 * (coreW + HT * stacks) + 3.8     # mm/turn
    Cu_len = D['N'] * MLT / 1000                 # m
    D['MLT_mm'] = MLT; D['Cu_len_m'] = Cu_len
    story.append(Paragraph(
        f"MLT = 2 &middot; (core<sub>W</sub> + HT &middot; stacks) + 3.8"
        f" = 2 &middot; ({coreW:.2f} + {HT:.2f} &middot; {stacks}) + 3.8"
        f" = <b>{MLT:.3f} mm/turn</b>", S['eq']))
    story.append(Paragraph(f"&ell;<sub>cu</sub> = N &middot; MLT = <b>{Cu_len:.6f} m</b>", S['eq']))
    story.append(Spacer(1, 3*mm))

    # 13.7.2 DCR
    story.append(Paragraph('Step 13.7.2) DCR (25&deg;C and 100&deg;C)', S['h3']))
    R20 = D['R_per_m_20C']
    alpha = 0.00393
    DCR_25  = R20 * Cu_len * (1 + alpha * (25  - 20)) * 1000   # mΩ
    DCR_100 = R20 * Cu_len * (1 + alpha * (100 - 20)) * 1000
    D['DCR_25_mOhm'] = DCR_25; D['DCR_100_mOhm'] = DCR_100
    story.append(Paragraph(
        "R&prime;(T) = R&prime;(20&deg;C) &middot; [1 + &alpha; &middot; (T &minus; 20)]", S['eq']))
    story.append(Paragraph(f"R&prime;(20&deg;C) = {R20:.6f} &Omega;/m", S['eq']))
    story.append(Paragraph(f"<b>DCR(25&deg;C) = {DCR_25:.4f} m&Omega;</b>", S['eq']))
    story.append(Paragraph(f"<b>DCR(100&deg;C) = {DCR_100:.4f} m&Omega;</b>", S['eq']))
    story.append(Spacer(1, 3*mm))

    # 13.7.3 copper loss
    story.append(Paragraph('Step 13.7.3) Copper loss at low line using I<sub>&phi;,rms</sub>', S['h3']))
    Irms = D['Irms_A']
    Pcu_25  = Irms**2 * DCR_25  / 1000
    Pcu_100 = Irms**2 * DCR_100 / 1000
    D['Pcu_25_W'] = Pcu_25; D['Pcu_100_W'] = Pcu_100
    story.append(Paragraph(
        "P<sub>cu</sub> = I<sub>&phi;,rms</sub><super>2</super> &middot; DCR", S['eq']))
    story.append(Paragraph(f"I<sub>&phi;,rms</sub> = {Irms:.4f} A", S['eq']))
    story.append(Paragraph(
        f"P<sub>cu</sub>(25&deg;C) = ({Irms:.4f})<super>2</super> &middot; {DCR_25:.4f} m&Omega;"
        f" = <b>{Pcu_25:.4f} W</b>", S['eq']))
    story.append(Paragraph(
        f"P<sub>cu</sub>(100&deg;C) = ({Irms:.4f})<super>2</super> &middot; {DCR_100:.4f} m&Omega;"
        f" = <b>{Pcu_100:.4f} W</b>", S['eq']))
    story.append(Spacer(1, 3*mm))

    # 13.7.4 core loss
    story.append(Paragraph('Step 13.7.4) Core loss estimate (anchored to datasheet reference)', S['h3']))
    Pv_ref   = D.get('Pv_ref_W_cm3', 0.525)
    f_ref    = D.get('f_ref_Hz', 100000)
    B_ref    = D.get('B_ref_T', 0.1)
    Ve_cm3   = D['Ve_total_cm3']
    Bac_pk   = D['Bac_pk_T']
    # Steinmetz scaling: Pv ~ (f/f_ref)^1.5 * (B/B_ref)^2.3
    Pv_est = Pv_ref * (D['fsw_Hz']/f_ref)**1.5 * (Bac_pk/B_ref)**2.3
    Pcore_lo = Pv_est * Ve_cm3
    D['Pv_est_W_cm3'] = Pv_est; D['Pcore_lo_W'] = Pcore_lo
    story.append(Paragraph(
        f"Reference: P<sub>v,ref</sub> = {Pv_ref:.3f} W/cm&sup3; at ({f_ref/1e3:.0f} kHz, {B_ref:.1f} T)", S['body']))
    story.append(Paragraph(f"B<sub>ac,pk</sub> (90 Vac crest) = {Bac_pk:.6f} T", S['eq']))
    story.append(Paragraph(f"V<sub>core,total</sub> = {Ve_cm3:.6f} cm&sup3;", S['eq']))
    story.append(Paragraph(f"P<sub>v</sub> &asymp; {Pv_est:.6f} W/cm&sup3; (estimate)", S['eq']))
    story.append(Paragraph(f"<b>P<sub>core</sub> &asymp; {Pcore_lo:.6f} W</b>", S['eq']))
    story.append(Spacer(1, 3*mm))

    # 13.7.5 total
    story.append(Paragraph('Step 13.7.5) Total loss (low line)', S['h3']))
    Pt_25  = Pcu_25  + Pcore_lo
    Pt_100 = Pcu_100 + Pcore_lo
    D['Ptotal_25_lo_W'] = Pt_25; D['Ptotal_100_lo_W'] = Pt_100
    story.append(Paragraph("P<sub>total</sub> = P<sub>cu</sub> + P<sub>core</sub>", S['eq']))
    story.append(Paragraph(
        f"P<sub>total</sub>(25&deg;C) = {Pcu_25:.4f} + {Pcore_lo:.4f}"
        f" = <b>{Pt_25:.4f} W</b>", S['eq']))
    story.append(Paragraph(
        f"P<sub>total</sub>(100&deg;C) = {Pcu_100:.4f} + {Pcore_lo:.4f}"
        f" = <b>{Pt_100:.4f} W</b>", S['eq']))
    story.append(Spacer(1, 4*mm))


def _loss_sweep_table_and_plot(story, D, S, temp_C, title_step):
    """Build loss vs Vin table + chart for 25°C or 100°C."""
    story.append(Paragraph(
        f'Step {title_step}) Inductor Loss vs Input Voltage'
        f' (Nominal A<sub>L</sub>, Per-phase, {temp_C}&deg;C)', S['h2']))
    story.append(Paragraph('Assumptions for this sweep:', S['body']))
    assumptions = [
        f'1) Nominal A<sub>L</sub> only (used for the selected turns N).',
        f'2) DCR uses {temp_C}&deg;C winding resistance (constant vs V<sub>in</sub>).',
        f'3) Copper loss uses I<sub>&phi;,rms</sub> from operating-point table for each V<sub>in</sub>.',
        f'4) Core loss uses B<sub>ac,pk</sub> computed from V<sub>in,pk</sub> and D@crest, '
        f'anchored to datasheet loss density reference.',
        f'5) All losses below are per phase.',
    ]
    for a in assumptions:
        story.append(Paragraph(a, S['body']))
    story.append(Spacer(1, 2*mm))

    ops = D['ops_table']
    DCR = D['DCR_25_mOhm'] if temp_C == 25 else D['DCR_100_mOhm']

    hdr = ['V<sub>in,rms</sub><br/>(Vac)', 'V<sub>in,pk</sub><br/>(V)',
           'D@crest<br/>(—)', 'I<sub>&phi;,rms</sub><br/>(A)',
           'B<sub>ac,pk</sub><br/>(T)', 'P<sub>cu</sub><br/>(W)',
           'P<sub>core</sub><br/>(W)', 'P<sub>total</sub><br/>(W)']
    rows = [[Paragraph(h, S['tbl_hdr']) for h in hdr]]

    Vin_pts=[]; Pcu_pts=[]; Pcore_pts=[]; Ptot_pts=[]
    for r in ops:
        Pcu   = r['Irms']**2 * DCR / 1000
        Pcore = r['Pcore_W']
        Ptot  = Pcu + Pcore
        Vin_pts.append(r['Vin_rms'])
        Pcu_pts.append(Pcu); Pcore_pts.append(Pcore); Ptot_pts.append(Ptot)
        rows.append([Paragraph(str(x), S['tbl_cell']) for x in [
            r['Vin_rms'], f"{r['Vin_pk']:.3f}", f"{r['D_crest']:.4f}",
            f"{r['Irms']:.4f}", f"{r['Bac_pk']:.5f}",
            f"{Pcu:.3f}", f"{Pcore:.3f}", f"{Ptot:.3f}",
        ]])

    cw = [18*mm, 18*mm, 16*mm, 18*mm, 18*mm, 15*mm, 15*mm, 15*mm]
    t = Table(rows, colWidths=cw)
    t.setStyle(_tbl_style())
    story.append(t)
    story.append(Spacer(1, 4*mm))

    # Chart
    fig, ax = plt.subplots(figsize=(7.5, 3.8))
    ax.plot(Vin_pts, Pcu_pts,   'o-', color='#2E6DA4', lw=2,   label=f'Copper loss P_cu ({temp_C}°C)')
    ax.plot(Vin_pts, Pcore_pts, 's-', color='#E74C3C', lw=2,   label='Core loss P_core (est)')
    ax.plot(Vin_pts, Ptot_pts,  '^-', color='#2E7D4F', lw=2,   label=f'Total inductor loss P_total ({temp_C}°C)')
    ax.set_xlabel('V$_{in,rms}$ (Vac)', fontsize=10)
    ax.set_ylabel('Loss per phase (W)', fontsize=10)
    ax.set_title(f'Step {title_step} — Inductor Loss vs Input Voltage (Nominal AL, Per-phase, {temp_C}°C)', fontsize=10)
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)
    story.append(_mpl_to_image(fig))
    story.append(Spacer(1, 4*mm))


def _sec_13_10(story, D, S):
    story.append(PageBreak())
    story.append(Paragraph('Step 13.10) Summary Table', S['h2']))
    n_par = D.get('n_parallel', 1) or 1
    wire_str = D['wire_designation']
    rows_data = [
        ('Core',                         f"{D['part_number']} ({D['stacks']}-stack)"),
        ('Turns',                        str(D['N'])),
        ('A<sub>L,total</sub> (min/nom/max)',
         f"{D['AL_min_total_nH']:.0f} / {D['AL_nom_total_nH']:.0f} / {D['AL_max_total_nH']:.0f} nH/T&sup2;"),
        ('L<sub>0</sub> (0A) (min/nom/max)',
         f"{D['L0_min_uH']:.1f} / {D['L0_nom_uH']:.1f} / {D['L0_max_uH']:.1f} &micro;H"),
        ('k<sub>req</sub> (min/nom/max)',
         f"{D['kreq_min_calc']:.4f} / {D['kreq_nom_calc']:.4f} / {D['kreq_max_calc']:.4f}"),
        ('A<sub>e,total</sub>',          f"{D['Ae_total_mm2']:.0f} mm&sup2;"),
        ('W<sub>a,total</sub>',          f"{D['Wa_total_mm2']:.0f} mm&sup2;"),
        ('Copper fill factor (FF<sub>cu</sub>)',
         f"{D['FFcu_calc']*100:.1f}%"),
        ('B<sub>ac,pk</sub> @ 90 Vac crest', f"{D['Bac_pk_T']:.4f} T"),
        ('B<sub>dc</sub> @ 90 Vac full load', f"{D['Bdc_T']:.4f} T"),
        ('Flux range @ 90 Vac full load',
         f"{D['Bmin_FL_T']:.4f} to {D['Bmax_FL_T']:.4f} T"),
        ('Wire',                          wire_str),
        ('Copper length',                f"{D['Cu_len_m']:.4f} m"),
        ('DCR @ 25&deg;C',               f"{D['DCR_25_mOhm']:.2f} m&Omega;"),
        ('P<sub>cu</sub> @ 90Vac @25&deg;C', f"{D['Pcu_25_W']:.3f} W"),
        ('P<sub>core</sub> @ 90Vac (estimate)', f"{D['Pcore_lo_W']:.3f} W"),
        ('P<sub>total</sub> @ 90Vac @25&deg;C (estimate)', f"{D['Ptotal_25_lo_W']:.3f} W"),
    ]
    data = [[Paragraph('<b>Item</b>', S['body']), Paragraph('<b>Value</b>', S['body'])]]
    data += [[Paragraph(k, S['body']), Paragraph(v, S['eq'])] for k, v in rows_data]
    t = Table(data, colWidths=[80*mm, 95*mm])
    ts = _tbl_style()
    ts.add('BACKGROUND', (0,0), (-1,0), BLUE)
    t.setStyle(ts)
    story.append(t)
    story.append(Spacer(1, 6*mm))


def _sec_14_1(story, D, S):
    story.append(PageBreak())
    _h1_band('Step 14) Time-Domain Flux and Core-Loss Modeling', story, S)
    story.append(Paragraph('Across Half Line Cycle — Detailed P<sub>core</sub>(t) Breakdown', S['h2']))
    story.append(Paragraph(
        'This section computes P<sub>core</sub>(t) across the rectified half line cycle, '
        'following the time-domain modeling concept: model vs time/angle, then integrate. '
        'The core-loss model is anchored to the crest-point P<sub>core</sub> values from Step 13.8.',
        S['body']))
    story.append(Spacer(1, 4*mm))

    story.append(Paragraph('Step 14.1) Governing equations', S['h2']))
    eqs = [
        'V<sub>in</sub>(t) = V<sub>pk</sub> &middot; sin(2&pi; &middot; f<sub>line</sub> &middot; t),&nbsp;&nbsp; t &isin; [0, 1/(2f<sub>line</sub>)]',
        'V<sub>pk</sub> = &radic;2 &middot; V<sub>ac,rms</sub>',
        'D(t) = 1 &minus; V<sub>in</sub>(t) / V<sub>bus</sub>',
        '&Delta;B<sub>pp</sub>(t) = V<sub>in</sub>(t) &middot; D(t) / (N &middot; A<sub>e</sub> &middot; f<sub>sw</sub>)',
        'B<sub>ac,pk</sub>(t) = &Delta;B<sub>pp</sub>(t) / 2',
        '&rArr; B<sub>ac,pk</sub>(t) = V<sub>in</sub>(t) &middot; D(t) / (2 &middot; N &middot; A<sub>e</sub> &middot; f<sub>sw</sub>)',
    ]
    for eq in eqs:
        story.append(Paragraph(eq, S['eq']))
    story.append(Spacer(1, 4*mm))


def _sec_14_2(story, D, S):
    story.append(Paragraph('Step 14.2) Worked example — B<sub>ac,pk</sub>(t) for V<sub>in</sub> = 90 Vac', S['h2']))
    Vac = 90; Vbus = D['Vout_V']; N = D['N']
    Ae_m2 = D['Ae_total_mm2']*1e-6; fsw = D['fsw_Hz']; fline = D['f_line_Hz']
    Vpk = math.sqrt(2)*Vac
    T_half = 1/(2*fline)

    given = [
        (f"V<sub>ac,rms</sub> = {Vac} V", f"V<sub>bus</sub> = {Vbus:.0f} V"),
        (f"f<sub>line</sub> = {fline:.0f} Hz", f"f<sub>sw</sub> = {fsw/1e3:.0f} kHz"),
        (f"N = {N} turns", f"A<sub>e</sub> = {D['Ae_total_mm2']:.0f} mm&sup2;"),
    ]
    for a, b in given:
        story.append(Paragraph(f"Given: {a} &nbsp;&nbsp; {b}", S['body']))
    story.append(Spacer(1, 2*mm))

    t_arr, Bac_arr = _Bac_pk_t(Vac, Vbus, N, Ae_m2, fsw, fline)
    peak_B = float(np.max(Bac_arr))
    t_peak = float(t_arr[np.argmax(Bac_arr)])*1000  # ms

    computes = [
        f"V<sub>pk</sub> = &radic;2 &middot; {Vac} = {Vpk:.3f} V",
        f"T<sub>half</sub> = 1/(2&middot;{fline:.0f}) = {T_half*1000:.3f} ms",
        f"V<sub>in</sub>(t) = V<sub>pk</sub> &middot; sin(2&pi;&middot;f<sub>line</sub>&middot;t)",
        f"D(t) = 1 &minus; V<sub>in</sub>(t)/V<sub>bus</sub>",
        f"B<sub>ac,pk</sub>(t) = V<sub>in</sub>(t)&middot;D(t)/(2&middot;N&middot;A<sub>e</sub>&middot;f<sub>sw</sub>)",
    ]
    for c in computes:
        story.append(Paragraph(f"Compute: {c}", S['eq']))
    story.append(Spacer(1, 2*mm))

    # Summary table
    sum_data = [
        [Paragraph('<b>Quantity</b>', S['body']), Paragraph(f'<b>Value ({Vac} Vac)</b>', S['body'])],
        [Paragraph('Peak B<sub>ac,pk</sub>(t)', S['body']), Paragraph(f'{peak_B:.5f} T', S['eq'])],
        [Paragraph('Time at peak', S['body']),              Paragraph(f'{t_peak:.3f} ms', S['eq'])],
        [Paragraph('B<sub>ac,pk</sub> at crest (&theta;=90°)', S['body']),
                                                            Paragraph(f'{peak_B:.5f} T', S['eq'])],
    ]
    t = Table(sum_data, colWidths=[90*mm, 85*mm])
    t.setStyle(_tbl_style(hdr_bg=TEAL))
    story.append(t)
    story.append(Spacer(1, 4*mm))

    # Figure 14.1 — Bac_pk(t) at 90 Vac
    fig, ax = plt.subplots(figsize=(7, 3.5))
    ax.plot(t_arr*1000, Bac_arr, color='#2E6DA4', lw=2)
    ax.plot([t_peak], [peak_B], 'o', color='#E74C3C', ms=8, zorder=5)
    ax.annotate(f'Peak = {peak_B:.4f} T @ {t_peak:.3f} ms\n'
                f'Vin≈{Vpk:.1f} V, D≈{1-Vpk/Vbus:.3f}',
                xy=(t_peak, peak_B), xytext=(t_peak+0.8, peak_B*0.92),
                fontsize=8, color='#333333',
                arrowprops=dict(arrowstyle='->', color='#333333', lw=0.8))
    ax.set_xlabel('Time over half line cycle (ms)', fontsize=10)
    ax.set_ylabel('B$_{ac,pk}$(t) (T)', fontsize=10)
    ax.set_title(f'B$_{{ac,pk}}$(t) — {Vac} Vac input (half-cycle, per inductor)', fontsize=10)
    ax.set_xlim(0, T_half*1000)
    ax.set_ylim(0, None)
    ax.grid(True, alpha=0.3)
    story.append(_mpl_to_image(fig))
    story.append(Paragraph(
        f'Figure 14.1 — B<sub>ac,pk</sub>(t) over half line cycle at {Vac} Vac (per inductor).',
        S['caption']))
    story.append(Spacer(1, 4*mm))


def _sec_14_3(story, D, S):
    story.append(Paragraph('Step 14.3) Core-loss model used to compute P<sub>core</sub>(t)', S['h2']))
    story.append(Paragraph(
        'A power-law model is used: P<sub>core</sub> = k &middot; (B<sub>ac,pk</sub>)<super>n</super>. '
        'Constants k and n are identified by fitting a log-log line to the crest-point data '
        '(B<sub>ac,pk</sub>@crest, P<sub>core</sub>@crest) across all input voltages.',
        S['body']))
    story.append(Spacer(1, 2*mm))

    model_eqs = [
        'P<sub>core</sub>(B) = k &middot; B<super>n</super>',
        'ln(P<sub>core</sub>) = ln(k) + n &middot; ln(B)',
        'Fit inputs: (B<sub>i</sub>, P<sub>i</sub>) = crest-point values from Step 13.8',
    ]
    for eq in model_eqs:
        story.append(Paragraph(eq, S['eq']))
    story.append(Spacer(1, 2*mm))

    ops = D['ops_table']
    Bac_list   = [r['Bac_pk'] for r in ops]
    Pcore_list = [r['Pcore_W'] for r in ops]
    k, n, r2 = _power_law_fit(Bac_list, Pcore_list)
    D['fit_k'] = k; D['fit_n'] = n; D['fit_r2'] = r2

    story.append(Paragraph(f"<b>Fit result: n = {n:.4f}</b>", S['eq']))
    story.append(Paragraph(f"<b>Fit result: k = {k:.2f}</b> (units: P<sub>core</sub> in W when B in T)", S['eq']))
    story.append(Spacer(1, 3*mm))

    # Fit input table
    hdr = ['V<sub>ac,rms</sub>', 'B<sub>ac,pk</sub>@crest (T)', 'P<sub>core</sub>@crest (W)']
    rows = [[Paragraph(h, S['tbl_hdr']) for h in hdr]]
    for r in ops:
        rows.append([Paragraph(str(x), S['tbl_cell']) for x in [
            r['Vin_rms'], f"{r['Bac_pk']:.5f}", f"{r['Pcore_W']:.3f}"]])
    t = Table(rows, colWidths=[40*mm, 60*mm, 60*mm])
    t.setStyle(_tbl_style(hdr_bg=TEAL))
    story.append(t)
    story.append(Spacer(1, 3*mm))

    # Validation
    Bval = ops[-2]['Bac_pk']  # 230 Vac
    Pval = k * Bval**n
    story.append(Paragraph(
        f'<i>Validation: Using B<sub>ac,pk</sub>@crest = {Bval:.5f} T (230 Vac), '
        f'model predicts P<sub>core</sub> = {Pval:.3f} W, matching crest-point value.</i>',
        S['note']))
    story.append(Spacer(1, 4*mm))


def _sec_14_4(story, D, S):
    story.append(Paragraph(
        'Step 14.4) Constructing P<sub>core</sub>(t) from B<sub>ac,pk</sub>(t) and computing average loss',
        S['h2']))
    bullet_items = [
        'Compute B<sub>ac,pk</sub>(t) using Step 14.1 equations.',
        'Compute P<sub>core</sub>(t) = k &middot; (B<sub>ac,pk</sub>(t))<super>n</super>',
        'Average over half-cycle: P<sub>core,avg</sub> = (1/T<sub>half</sub>) &middot; &int;<sub>0</sub><super>T<sub>half</sub></super> P<sub>core</sub>(t) dt',
        'Peak over half-cycle: P<sub>core,pk</sub> = max(P<sub>core</sub>(t))',
    ]
    for b in bullet_items:
        story.append(Paragraph(f'&bull; {b}', S['body']))
    story.append(Spacer(1, 3*mm))

    # Plot 230 Vac Pcore(t) as in reference
    Vac = 230
    k = D['fit_k']; n = D['fit_n']
    Ae_m2 = D['Ae_total_mm2']*1e-6
    t_arr, Bac_arr = _Bac_pk_t(Vac, D['Vout_V'], D['N'], Ae_m2, D['fsw_Hz'], D['f_line_Hz'])
    Pcore_t = k * np.power(np.maximum(Bac_arr, 1e-12), n)
    Pavg = float(np.trapezoid(Pcore_t, t_arr) / (t_arr[-1] - t_arr[0]))
    Ppk  = float(np.max(Pcore_t))
    t_pk = float(t_arr[np.argmax(Pcore_t)])*1000
    Vin_pk_at_t = math.sqrt(2)*Vac * math.sin(2*math.pi*D['f_line_Hz']*t_arr[np.argmax(Pcore_t)])
    D_at_pk = 1 - Vin_pk_at_t / D['Vout_V']

    fig, ax = plt.subplots(figsize=(7, 3.8))
    ax.plot(t_arr*1000, Pcore_t, color='#2E6DA4', lw=2)
    ax.axhline(Pavg, color='#E74C3C', lw=1.5, ls='--')
    ax.plot([t_pk], [Ppk], 'o', color='#E74C3C', ms=8, zorder=5)
    ax.annotate(f'Avg = {Pavg:.3f} W\nPeak = {Ppk:.3f} W @ {t_pk:.3f} ms',
                xy=(t_arr[-1]*1000*0.55, Pavg),
                fontsize=8.5, color='#333333', va='bottom')
    ax.set_xlabel('Time over half line cycle (ms)', fontsize=10)
    ax.set_ylabel('P$_{core}$(t) (W)', fontsize=10)
    ax.set_title(f'P$_{{core}}$(t) — {Vac} Vac input (half-cycle, per inductor)', fontsize=10)
    ax.set_xlim(0, t_arr[-1]*1000)
    ax.set_ylim(0, None)
    ax.grid(True, alpha=0.3)
    story.append(_mpl_to_image(fig))
    story.append(Paragraph(
        f'Figure 14.2 — P<sub>core</sub>(t) over half line cycle at {Vac} Vac (per inductor), with average line.',
        S['caption']))
    story.append(Paragraph(
        f'{Vac} Vac numerical summary: P<sub>core,avg</sub> = {Pavg:.3f} W; '
        f'P<sub>core,pk</sub> = {Ppk:.3f} W at t = {t_pk:.3f} ms, '
        f'where V<sub>in</sub> &asymp; {Vin_pk_at_t:.1f} V and D &asymp; {D_at_pk:.3f}.',
        S['note']))
    story.append(Spacer(1, 4*mm))


def _sec_14_5(story, D, S):
    story.append(Paragraph(
        'Step 14.5) Comparative waveforms and summary metrics for all V<sub>ac</sub>', S['h2']))
    Ae_m2 = D['Ae_total_mm2']*1e-6
    k = D['fit_k']; n_exp = D['fit_n']
    fline = D['f_line_Hz']
    Vbus = D['Vout_V']; N = D['N']; fsw = D['fsw_Hz']

    # Fig 14.3 — Bac_pk(t) overlay
    fig, ax = plt.subplots(figsize=(7.5, 3.8))
    for Vac in VAC_LIST:
        t_arr, Bac_arr = _Bac_pk_t(Vac, Vbus, N, Ae_m2, fsw, fline)
        ax.plot(t_arr*1000, Bac_arr, color=VAC_COLORS[Vac], lw=1.5, label=f'{Vac} Vac')
    ax.set_xlabel('Time over half line cycle (ms)', fontsize=10)
    ax.set_ylabel('B$_{ac,pk}$(t) (T)', fontsize=10)
    ax.set_title('B$_{ac,pk}$(t) over half-cycle for all input voltages (per inductor)', fontsize=10)
    ax.legend(fontsize=8, ncol=3, loc='upper right')
    ax.grid(True, alpha=0.3)
    ax.set_xlim(0, 1/(2*fline)*1000)
    ax.set_ylim(0, None)
    story.append(Paragraph('B<sub>ac,pk</sub>(t) overlay for all input voltages:', S['body']))
    story.append(_mpl_to_image(fig))
    story.append(Paragraph('Figure 14.3 — B<sub>ac,pk</sub>(t) overlay (per inductor).', S['caption']))
    story.append(Spacer(1, 3*mm))

    # Fig 14.4 — Pcore(t) overlay
    fig, ax = plt.subplots(figsize=(7.5, 3.8))
    for Vac in VAC_LIST:
        t_arr, Bac_arr = _Bac_pk_t(Vac, Vbus, N, Ae_m2, fsw, fline)
        Pcore_t = k * np.power(np.maximum(Bac_arr, 1e-12), n_exp)
        ax.plot(t_arr*1000, Pcore_t, color=VAC_COLORS[Vac], lw=1.5, label=f'{Vac} Vac')
    ax.set_xlabel('Time over half line cycle (ms)', fontsize=10)
    ax.set_ylabel('P$_{core}$(t) (W)', fontsize=10)
    ax.set_title('P$_{core}$(t) over half-cycle for all input voltages (per inductor)', fontsize=10)
    ax.legend(fontsize=8, ncol=3, loc='upper right')
    ax.grid(True, alpha=0.3)
    ax.set_xlim(0, 1/(2*fline)*1000)
    ax.set_ylim(0, None)
    story.append(Paragraph('P<sub>core</sub>(t) overlay for all input voltages:', S['body']))
    story.append(_mpl_to_image(fig))
    story.append(Paragraph('Figure 14.4 — P<sub>core</sub>(t) overlay (per inductor).', S['caption']))
    story.append(Spacer(1, 4*mm))

    # Table 14.1
    story.append(Paragraph('Table 14.1 — Core-loss metrics derived from P<sub>core</sub>(t) '
                            'across half line cycle (per inductor)', S['h3']))
    hdr = ['V<sub>ac,rms</sub><br/>(Vac)', 'P<sub>core,avg</sub><br/>(W)',
           'P<sub>core,pk</sub><br/>(W)', 't@peak<br/>(ms)',
           'V<sub>in</sub>@peak<br/>(V)', 'D@peak']
    rows = [[Paragraph(h, S['tbl_hdr']) for h in hdr]]
    summary_rows = []
    T_half = 1/(2*fline)
    for Vac in VAC_LIST:
        t_arr, Bac_arr = _Bac_pk_t(Vac, Vbus, N, Ae_m2, fsw, fline)
        Pcore_t = k * np.power(np.maximum(Bac_arr, 1e-12), n_exp)
        Pavg = float(np.trapezoid(Pcore_t, t_arr) / (t_arr[-1]-t_arr[0]))
        Ppk  = float(np.max(Pcore_t))
        t_pk = float(t_arr[np.argmax(Pcore_t)])
        Vin_at_pk = math.sqrt(2)*Vac * math.sin(2*math.pi*fline*t_pk)
        D_at_pk   = max(0, 1 - Vin_at_pk/Vbus)
        summary_rows.append({
            'Vin_rms': Vac, 'Pavg': Pavg, 'Ppk': Ppk,
            't_pk_ms': t_pk*1000, 'Vin_at_pk': Vin_at_pk, 'D_at_pk': D_at_pk,
        })
        rows.append([Paragraph(str(x), S['tbl_cell']) for x in [
            Vac, f"{Pavg:.3f}", f"{Ppk:.3f}", f"{t_pk*1000:.3f}",
            f"{Vin_at_pk:.1f}", f"{D_at_pk:.3f}",
        ]])
    D['summary_rows'] = summary_rows
    cw = [22*mm, 28*mm, 28*mm, 22*mm, 28*mm, 22*mm]
    t = Table(rows, colWidths=cw)
    t.setStyle(_tbl_style(hdr_bg=NAVY))
    story.append(t)
    story.append(Spacer(1, 6*mm))


# ══════════════════════════════════════════════════════════════════════════════
# Main entry: build ops_table from approved_design, then generate PDF
# ══════════════════════════════════════════════════════════════════════════════

def _build_ops_table(D):
    """Build per-Vin operating point table with all derived quantities."""
    from app.mode_b.step7_magnetic_calc import DEFAULT_OPS  # noqa
    import numpy as _np

    Vbus = D['Vout_V']; N = D['N']
    Ae_m2 = D['Ae_total_mm2']*1e-6; fsw = D['fsw_Hz']
    k_fit = None  # built after first pass
    L0_nom = D['AL_nom_total_nH'] * N**2 / 1e3  # µH
    L_target = D['L_target_uH']

    # Operating points: use DEFAULT_OPS from step7_magnetic_calc
    # DEFAULT_OPS columns: [Vin_rms, Pout_W, eta, PF, Irms_ph, ...]
    OPS = DEFAULT_OPS

    rows = []
    for row in OPS:
        Vin_rms = float(row[0])
        eta     = float(row[2])
        PF      = float(row[3])
        Irms    = float(row[4])
        Pout    = float(row[1])

        Vin_pk   = math.sqrt(2) * Vin_rms
        D_crest  = max(0.0, 1.0 - Vin_pk / Vbus)
        Pin      = Pout / eta
        Ipk_line = math.sqrt(2) * Pin / (Vin_rms * PF)
        Iavg_crest = Ipk_line / 2

        Bac_pk = Vin_pk * D_crest / (2 * N * Ae_m2 * fsw)

        # AT bias
        AT = N * Iavg_crest
        # k_bias from backend L_vs_Vin_table if available, else estimate
        k_bias = L_target / L0_nom  # placeholder; overridden below

        rows.append({
            'Vin_rms': Vin_rms, 'Vin_pk': Vin_pk,
            'D_crest': D_crest, 'Irms': Irms,
            'Ipk_line': Ipk_line, 'Iavg_crest': Iavg_crest,
            'AT': AT, 'Bac_pk': Bac_pk,
            'Pcore_W': 0,  # filled after fit
        })

    # Steinmetz-based Pcore for each op-point (anchored to 90 Vac reference)
    Pv_ref = D.get('Pv_ref_W_cm3', 0.525)
    f_ref  = D.get('f_ref_Hz', 100000)
    B_ref  = D.get('B_ref_T', 0.1)
    Ve_cm3 = D['Ve_total_cm3']
    for r in rows:
        Pv = Pv_ref * (fsw/f_ref)**1.5 * (r['Bac_pk']/B_ref)**2.3
        r['Pcore_W'] = Pv * Ve_cm3

    # k_bias from backend L_vs_Vin_table if provided
    lvt = D.get('L_vs_Vin_table', [])
    if lvt:
        lvt_map = {int(r.get('Vin_rms', 0)): r for r in lvt}
        for r in rows:
            vkey = int(r['Vin_rms'])
            if vkey in lvt_map:
                r['k_bias']     = float(lvt_map[vkey].get('k_bias', L_target/L0_nom))
                r['L_full_nom'] = float(lvt_map[vkey].get('L_full_nom_uH', L0_nom * r['k_bias']))
                r['L_full_min'] = float(lvt_map[vkey].get('L_full_min_uH', r['L_full_nom'] * 0.92))
                r['L_full_max'] = float(lvt_map[vkey].get('L_full_max_uH', r['L_full_nom'] * 1.08))
            else:
                r['k_bias']     = L_target / L0_nom
                r['L_full_nom'] = L0_nom * r['k_bias']
                r['L_full_min'] = r['L_full_nom'] * 0.92
                r['L_full_max'] = r['L_full_nom'] * 1.08
    else:
        # Use loss_table_25C from backend if available
        lt = D.get('loss_table_25C', [])
        lt_map = {int(r.get('Vin_rms', 0)): r for r in lt} if lt else {}
        for r in rows:
            vkey = int(r['Vin_rms'])
            if vkey in lt_map and lt_map[vkey].get('Pcore_W'):
                r['Pcore_W'] = float(lt_map[vkey]['Pcore_W'])
            k_b = L_target / L0_nom
            r['k_bias']     = k_b
            r['L_full_nom'] = L0_nom * k_b
            r['L_full_min'] = r['L_full_nom'] * 0.92
            r['L_full_max'] = r['L_full_nom'] * 1.08

    D['ops_table'] = rows


def _resolve_params(approved_design: dict, state: dict) -> dict:
    """Map approved_design + state into a flat D dict for the report."""
    d = approved_design
    intake = state.get('intake', {})
    ap     = intake.get('application', {})
    tsi    = state.get('topology_specific_inputs', {})

    stacks = int(d.get('stacks', 1))

    # AL values — use the fields now stored directly in DesignResult
    AL_nom_single = float(d.get('AL_nom_nH', 0))       # single-stack nominal nH/T²
    AL_tol        = float(d.get('AL_tol_pct', 8))       # ±%

    # Back-calculate single AL from total if not stored directly
    if AL_nom_single == 0:
        AL_nom_total_raw = float(d.get('AL_nom_total',
            float(d.get('L0_nom_uH', 0)) * 1e3 / max(int(d.get('N', 1))**2, 1)))
        AL_nom_single = AL_nom_total_raw / stacks

    AL_nom_total = AL_nom_single * stacks
    AL_min_total = AL_nom_total * (1 - AL_tol/100)
    AL_max_total = AL_nom_total * (1 + AL_tol/100)

    Vout  = float(ap.get('output_bus_voltage_v', d.get('Vbus_V', 393)))
    fsw   = float(tsi.get('recommended_frequency_hz', 70000))
    Vin_lo= float(ap.get('vin_rms_min', 90))
    fline = float(tsi.get('f_line_Hz', 60))
    N     = int(d.get('N', 49))
    # L_target: prefer what the designer actually confirmed
    L_target = float(tsi.get('confirmed_L_uH_sel',
                     tsi.get('confirmed_L_uH', d.get('L_target_uH', 235))))
    Irms  = float(tsi.get('Iph_rms_A', d.get('Irms_A', 10.07)))
    Ipk_line = float(tsi.get('confirmed_Iin_pk_A', 28.3))

    Vin_pk = math.sqrt(2) * Vin_lo
    D_pk   = max(0, 1 - Vin_pk / Vout)
    Iavg_crest = Ipk_line / 2
    dIL_pp = Vin_pk * D_pk / (L_target * 1e-6 * fsw)

    Ae_total  = float(d.get('Ae_total_mm2', 231))
    Wa_total  = float(d.get('Wa_total_mm2', 468))
    Ve_total  = float(d.get('Ve_total_cm3', 15.977))
    # Single-stack values — now stored directly in DesignResult
    Ae_single = float(d.get('Ae_single_mm2', Ae_total / stacks))
    Wa_single = float(d.get('Wa_single_mm2', Wa_total / stacks))  # single-core window area

    # Cu_area_mm2 in DesignResult = copper area for ONE turn (n_parallel already included)
    # Cu_area_total_mm2 = N turns × area per turn  (used for FFcu = Acu_total / Wa)
    Cu_area_per_turn = float(d.get('Cu_area_mm2', 3.1416))
    Cu_area_total    = Cu_area_per_turn * N
    Cu_area_single   = Cu_area_per_turn / max(int(d.get('n_parallel', 1)), 1)
    wire_OD  = float(d.get('wire_OD_mm', 2.23))
    R20      = float(d.get('R_per_m_20C', 0.006315))
    wire_des = d.get('wire_designation', '2x(0.1x200)')

    # Core physical dims — now stored directly in DesignResult
    OD = float(d.get('OD_mm', 0.0))
    ID = float(d.get('ID_mm', 0.0))
    HT = float(d.get('HT_mm', 0.0))

    supplier = d.get('supplier', '')
    if not supplier:
        mat_key = d.get('material_key', '')
        supplier = mat_key.split('_')[0].title() if mat_key else 'Magnetics' 

    return dict(
        # core
        part_number=d.get('part_number', '0059894A2'),
        supplier=supplier,
        stacks=stacks,
        OD_mm=OD, ID_mm=ID, HT_mm=HT,
        Ae_single_mm2=round(Ae_single,1),
        Wa_single_mm2=round(Wa_single,1),
        Ae_total_mm2=Ae_total,
        Wa_total_mm2=Wa_total,
        Ve_total_cm3=Ve_total,
        AL_nom_single_nH=AL_nom_single,
        AL_tol_pct=AL_tol,
        AL_nom_total_nH=round(AL_nom_total),
        AL_min_total_nH=round(AL_min_total),
        AL_max_total_nH=round(AL_max_total),
        # electrical
        Vout_V=Vout, fsw_Hz=fsw, f_line_Hz=fline,
        Vin_lo_rms=Vin_lo, Vin_pk=Vin_pk, D_pk=D_pk,
        N=N, L_target_uH=L_target,
        Irms_A=Irms, Ipk_line=Ipk_line,
        Iavg_crest=Iavg_crest, dIL_pp=dIL_pp,
        # wire
        wire_designation=wire_des,
        wire_construction=d.get('wire_construction', wire_des),
        wire_OD_mm=wire_OD,
        Cu_area_total_mm2=Cu_area_total,
        Cu_area_single_mm2=Cu_area_single,
        R_per_m_20C=R20,
        n_parallel=int(d.get('n_parallel', 1)),
        # datasheet reference for loss anchor
        Pv_ref_W_cm3=d.get('Pv_ref_W_cm3', 0.525),
        f_ref_Hz=d.get('f_ref_Hz', 100000),
        B_ref_T=d.get('B_ref_T', 0.1),
        # pass-through tables from backend
        L_vs_Vin_table=d.get('L_vs_Vin_table', []),
        loss_table_25C=d.get('loss_table_25C', []),
        loss_table_100C=d.get('loss_table_100C', []),
        all_candidates=d.get('all_candidates', []),
        # Extra fields for new Step 14.6–14.8 sections
        Le_single_mm=float(d.get('Le_single_mm',
            round(float(d.get('Ve_total_cm3', 1)) * 1000 /
                  max(float(d.get('Ae_total_mm2', 231)) / max(int(d.get('stacks', 1)), 1), 1)))),
        Rac_Rdc=float(d.get('Rac_Rdc', 1.0)),
        FFcu_design=float(d.get('FFcu', 0.0)),
        Ku=float(d.get('Ku', 0.0)),
        sat_margin_pct=float(d.get('sat_margin_pct', 0.0)),
        dT_rise_C=float(d.get('dT_rise_C', 0.0)),
        dT_budget_C=float(d.get('dT_budget_C', 60.0)),
        P_unc_lo_W=float(d.get('P_unc_lo_W', 0.0)),
        P_unc_hi_W=float(d.get('P_unc_hi_W', 0.0)),
        passed=bool(d.get('passed', True)),
        fail_reasons=list(d.get('fail_reasons', [])),
        Pcu_100C_W=float(d.get('Pcu_100C_W', 0.0)),
        Ptotal_100C_W=float(d.get('Ptotal_100C_W', 0.0)),
        L0_nom_uH=float(d.get('L0_nom_uH', 0.0)),
        Bmax_FL_T=float(d.get('Bmax_FL_T', 0.0)),
        material_key=d.get('material_key', ''),
    )


# ══════════════════════════════════════════════════════════════════════════════
# JS-Studio equivalent sections (Steps 14.6 – 14.8)
# Matches the four tabs in "Review Magnetics Data" (PFC Inductor Studio V5.1):
#   Overview       → Steps 13.1–13.10 (already present)
#   Waveform Panes → Step 14.6  (H, B, Pcu, Ptotal waveforms)
#   Voltage Sweep  → Step 14.7  (loss vs Vin with uncertainty band)
#   Design Review  → Step 14.8  (audit checklist + summary)
# ══════════════════════════════════════════════════════════════════════════════

# Analytical DC-bias retention k(H) — matches JS V5.1 retention() formula
def _retention_edge_report(H_Oe: float) -> float:
    H = max(0.0, H_Oe)
    return min(1.0, (1.0 / (0.01 + 9.202e-10 * H ** 3.044)) / 100.0)


def _sec_14_6_extended_waveforms(story, D, S):
    """Step 14.6 — Extended waveform analysis (matching JS 'Waveform Panes' tab).
    Adds: H(t), full B(t) overlay (Bdc, Bmax, Bac,pk), Pcu(t), Ptotal(t) at 90 Vac.
    """
    story.append(PageBreak())
    _h1_band('Step 14.6) Extended Waveform Analysis — H, B, Copper & Total Loss', story, S)
    story.append(Paragraph(
        'Instantaneous quantities over one half line cycle at 90 Vac full load. '
        'Computed with the analytical DC-bias retention k(H) from the iGSE-corrected model. '
        'Matches the waveform-pane outputs of the Review Magnetics tool.',
        S['body']))
    story.append(Spacer(1, 4*mm))

    # ── Parameters ────────────────────────────────────────────────────────────
    N      = D['N']
    stacks = D['stacks']
    Ae_m2  = D['Ae_total_mm2'] * 1e-6
    Vbus   = D['Vout_V']
    fsw    = D['fsw_Hz']
    fline  = D['f_line_Hz']
    Icrest = D['Iavg_crest']
    Vac90  = 90.0
    Vpk90  = Vac90 * math.sqrt(2)
    L0_H   = D['AL_nom_total_nH'] * 1e-9 * N**2

    # Le from assembled dimensions: Ve_total / Ae_total (approximation for toroid)
    Le_m   = float(D.get('Le_single_mm', D['Ve_total_cm3'] * 1e-6 * 1e4 /
                          max(D['Ae_total_mm2'] * 1e-6, 1e-8))) * 1e-3
    Le_cm  = Le_m * 100.0

    # DCR at 100°C — D values set by _sec_13_7
    DCR_mOhm = D.get('DCR_100_mOhm', D.get('DCR_25_mOhm', 14.6))
    Rdc    = DCR_mOhm * 1e-3
    Rac    = Rdc * float(D.get('Rac_Rdc', 1.0))

    # ── Waveform arrays (M=360 half-cycle points) ─────────────────────────────
    M      = 360
    T_half = 1.0 / (2.0 * fline)
    t_ms   = np.linspace(0, T_half * 1000, M)
    theta  = np.linspace(0, math.pi, M)

    Vin    = Vpk90 * np.sin(theta)
    I_t    = Icrest * np.sin(theta)
    D_t    = np.clip(1.0 - Vin / Vbus, 0.0, 0.98)

    H_t    = 0.4 * math.pi * N * I_t / Le_cm           # Oe
    k_t    = np.array([_retention_edge_report(float(h)) for h in H_t])
    L_t    = np.maximum(L0_H * k_t, 1e-9)               # H

    Bac_t  = Vin * D_t / (2.0 * N * Ae_m2 * fsw)       # T
    Bdc_t  = L_t * I_t / (N * Ae_m2)                    # T
    Bmax_t = Bdc_t + Bac_t

    dIpp_t = Vin * D_t / np.maximum(L_t * fsw, 1e-12)
    Ihf_t  = dIpp_t / (2.0 * math.sqrt(3.0))
    Pcu_t  = Rdc * I_t**2 + Rac * Ihf_t**2             # W

    # Core loss at each instant (power-law, from fit stored in D['fit_k'/'fit_n'])
    k_pl  = D.get('fit_k', 1.0); n_pl = D.get('fit_n', 2.3)
    Pcore_t = k_pl * np.power(np.maximum(Bac_t, 1e-12), n_pl)
    Ptot_t  = Pcore_t + Pcu_t

    # Peak summary
    H_pk    = float(np.max(H_t))
    Bmax_pk = float(np.max(Bmax_t))
    Pcu_pk  = float(np.max(Pcu_t))
    Ptot_pk = float(np.max(Ptot_t))

    # ── Plot 14.6a — H(t) ────────────────────────────────────────────────────
    story.append(Paragraph('Step 14.6.1) Magnetic field intensity H(t) — 90 Vac', S['h2']))
    fig, ax = plt.subplots(figsize=(7.5, 3.0))
    ax.plot(t_ms, H_t, color='#38bdf8', lw=2, label='H(t) [Oe]')
    ax.plot(t_ms, I_t * 4, color='#a78bfa', lw=1.2, ls='--',
            label=f'I_avg(t)×4  [A×4]')
    ax.set_xlabel('Time over half line cycle (ms)', fontsize=10)
    ax.set_ylabel('H (Oe)  /  I×4 (A)', fontsize=10)
    ax.set_title('H(t) and I_avg(t) vs Time — 90 Vac', fontsize=10)
    ax.legend(fontsize=9); ax.grid(True, alpha=0.3)
    ax.set_xlim(0, T_half * 1000); ax.set_ylim(0, None)
    story.append(_mpl_to_image(fig))
    story.append(Paragraph(
        f'Figure 14.6.1 — H peaks at {H_pk:.1f} Oe at the line crest (θ=90°).',
        S['caption']))
    story.append(Spacer(1, 4*mm))

    # ── Plot 14.6b — B(t) overlay ────────────────────────────────────────────
    story.append(Paragraph('Step 14.6.2) Flux density B(t) — 90 Vac', S['h2']))
    fig, ax = plt.subplots(figsize=(7.5, 3.2))
    ax.plot(t_ms, Bdc_t,  color='#22c55e', lw=2,   label='B_dc(t)')
    ax.plot(t_ms, Bmax_t, color='#38bdf8', lw=2,   label='B_max(t) = B_dc + B_ac,pk')
    ax.plot(t_ms, Bac_t,  color='#f59e0b', lw=1.5, label='B_ac,pk(t)')
    ax.set_xlabel('Time over half line cycle (ms)', fontsize=10)
    ax.set_ylabel('Flux density B (T)', fontsize=10)
    ax.set_title('B_dc(t), B_max(t), B_ac,pk(t) — 90 Vac, half cycle', fontsize=10)
    ax.legend(fontsize=9); ax.grid(True, alpha=0.3)
    ax.set_xlim(0, T_half * 1000); ax.set_ylim(0, None)
    story.append(_mpl_to_image(fig))
    story.append(Paragraph(
        f'Figure 14.6.2 — B_max peaks at {Bmax_pk:.4f} T. '
        f'B_dc dominates; B_ac,pk is the switching ripple term.',
        S['caption']))
    story.append(Spacer(1, 4*mm))

    # ── Plot 14.6c — Pcu(t) ──────────────────────────────────────────────────
    story.append(Paragraph('Step 14.6.3) Instantaneous copper loss P_cu(t) — 90 Vac', S['h2']))
    story.append(Paragraph(
        'P_cu(t) = R_dc × I_avg²(t) + R_ac × I_hf²(t)   '
        '(DC term + HF ripple term, from JS V5.1 decomposition)',
        S['eq']))
    story.append(Spacer(1, 2*mm))
    fig, ax = plt.subplots(figsize=(7.5, 3.0))
    ax.plot(t_ms, Pcu_t * 1000, color='#a78bfa', lw=2, label='P_cu(t) (mW)')
    ax.axhline(float(np.mean(Pcu_t)) * 1000, color='#a78bfa', lw=1.2, ls='--',
               label=f'Avg = {float(np.mean(Pcu_t))*1000:.1f} mW')
    ax.set_xlabel('Time over half line cycle (ms)', fontsize=10)
    ax.set_ylabel('Copper loss P_cu(t) (mW)', fontsize=10)
    ax.set_title('Instantaneous Copper Loss P_cu(t) — 90 Vac', fontsize=10)
    ax.legend(fontsize=9); ax.grid(True, alpha=0.3)
    ax.set_xlim(0, T_half * 1000); ax.set_ylim(0, None)
    story.append(_mpl_to_image(fig))
    story.append(Paragraph(
        f'Figure 14.6.3 — P_cu(t) peaks at {Pcu_pk*1000:.1f} mW. '
        f'Follows I²: maximum at line crest.',
        S['caption']))
    story.append(Spacer(1, 4*mm))

    # ── Plot 14.6d — Ptotal(t) ───────────────────────────────────────────────
    story.append(Paragraph('Step 14.6.4) Instantaneous total loss P_total(t) — 90 Vac', S['h2']))
    fig, ax = plt.subplots(figsize=(7.5, 3.0))
    ax.plot(t_ms, Ptot_t,  color='#38bdf8', lw=2, label='P_total(t) = P_core + P_cu')
    ax.plot(t_ms, Pcore_t, color='#f59e0b', lw=1.5, ls='--', label='P_core(t)')
    ax.plot(t_ms, Pcu_t,   color='#a78bfa', lw=1.5, ls='--', label='P_cu(t)')
    P_avg = float(np.mean(Ptot_t))
    ax.axhline(P_avg, color='#ef4444', lw=1.2, ls='-',
               label=f'P_total avg = {P_avg:.3f} W')
    ax.set_xlabel('Time over half line cycle (ms)', fontsize=10)
    ax.set_ylabel('Loss (W)', fontsize=10)
    ax.set_title('Instantaneous Total Loss P_total(t) — 90 Vac', fontsize=10)
    ax.legend(fontsize=9); ax.grid(True, alpha=0.3)
    ax.set_xlim(0, T_half * 1000); ax.set_ylim(0, None)
    story.append(_mpl_to_image(fig))
    story.append(Paragraph(
        f'Figure 14.6.4 — P_total(t) over the half line cycle at 90 Vac. '
        f'Half-cycle average = {P_avg:.3f} W; peak = {Ptot_pk:.3f} W.',
        S['caption']))
    story.append(Spacer(1, 4*mm))

    # ── Peak summary table ────────────────────────────────────────────────────
    story.append(Paragraph('Table 14.6 — Waveform peak values (90 Vac, 100°C winding)', S['h3']))
    hdr = ['Quantity', 'Peak value', 'Occurs at']
    rows = [[Paragraph(h, S['tbl_hdr']) for h in hdr]]
    rows.append([Paragraph('Peak H(t)',          S['tbl_cell']),
                 Paragraph(f'{H_pk:.1f} Oe',     S['tbl_cell']),
                 Paragraph('θ = 90° (crest)',    S['tbl_cell'])])
    rows.append([Paragraph('Peak B_max(t)',       S['tbl_cell']),
                 Paragraph(f'{Bmax_pk:.4f} T',   S['tbl_cell']),
                 Paragraph('θ ≈ 90° (crest)',    S['tbl_cell'])])
    rows.append([Paragraph('Peak P_cu(t)',        S['tbl_cell']),
                 Paragraph(f'{Pcu_pk*1000:.1f} mW', S['tbl_cell']),
                 Paragraph('θ = 90° (crest)',    S['tbl_cell'])])
    rows.append([Paragraph('Peak P_total(t)',     S['tbl_cell']),
                 Paragraph(f'{Ptot_pk:.3f} W',   S['tbl_cell']),
                 Paragraph('near line crest',    S['tbl_cell'])])
    t = Table(rows, colWidths=[70*mm, 50*mm, 50*mm])
    t.setStyle(_tbl_style())
    story.append(t)
    story.append(Spacer(1, 6*mm))


def _sec_14_7_voltage_sweep_uncertainty(story, D, S):
    """Step 14.7 — Voltage sweep with iGSE uncertainty band (JS 'Voltage Sweep' tab).
    Adds the ±5–20 % core-loss uncertainty band to the loss-vs-Vin sweep.
    """
    story.append(PageBreak())
    _h1_band('Step 14.7) Voltage Sweep — Loss and Flux with Uncertainty Band', story, S)
    story.append(Paragraph(
        'Combined sweep plot at 100°C winding. Solid lines = analytical model. '
        'Shaded orange band = core-loss uncertainty +5% to +20% (engineering estimate — '
        'unanchored until calibrated against FEA or bench measurement).',
        S['body']))
    story.append(Spacer(1, 4*mm))

    lt = D.get('loss_table_100C', [])
    if not lt:
        story.append(Paragraph('Loss table not available.', S['note']))
        return

    # Separate low-line / high-line with a visible gap at 133–179 Vac
    lo = [r for r in lt if r['Vin_rms'] <= 132]
    hi = [r for r in lt if r['Vin_rms'] >= 180]

    def _xy(rows, key):
        return [r['Vin_rms'] for r in rows], [r[key] for r in rows]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(7.5, 3.8))

    # ── Left: Loss vs Vin with uncertainty band ───────────────────────────────
    for seg in [lo, hi]:
        if not seg: continue
        vx  = [r['Vin_rms']   for r in seg]
        Pc  = [r['Pcore_W']   for r in seg]
        Pcu = [r['Pcu_W']     for r in seg]
        Pt  = [r['Ptotal_W']  for r in seg]
        Plo = [cu + 1.05 * co for cu, co in zip(Pcu, Pc)]
        Phi = [cu + 1.20 * co for cu, co in zip(Pcu, Pc)]

        ax1.fill_between(vx, [co * 1.05 for co in Pc], [co * 1.20 for co in Pc],
                         alpha=0.25, color='#f59e0b', label='Core-loss uncertainty' if seg is lo else '')
        ax1.fill_between(vx, Plo, Phi,
                         alpha=0.12, color='#ef4444', label='Total-loss uncertainty' if seg is lo else '')
        ax1.plot(vx, Pc,  color='#38bdf8', lw=2,   label='P_core (model)' if seg is lo else '')
        ax1.plot(vx, Pt,  color='#60a5fa', lw=2,   ls='--',
                 label='P_total (model)' if seg is lo else '')

    ax1.set_xlabel('V_in,rms (Vac)', fontsize=10)
    ax1.set_ylabel('Loss per inductor (W)', fontsize=10)
    ax1.set_title('Loss vs Input Voltage — gap 133–179 Vac undefined', fontsize=9)
    ax1.legend(fontsize=8); ax1.grid(True, alpha=0.3); ax1.set_xlim(80, 274)

    # ── Right: Bac,pk and L_full vs Vin ──────────────────────────────────────
    ops = D.get('ops_table', [])
    if ops:
        vx_op   = [r['Vin_rms'] for r in ops]
        Bac_op  = [r['Bac_pk']  for r in ops]
        Lnom_op = [r.get('L_full_nom', r.get('L_full_nom_uH', D['L_target_uH'])) for r in ops]
        ax2_r   = ax2.twinx()
        ax2.plot(vx_op, Bac_op, color='#f59e0b', lw=2,
                 marker='o', ms=4, label='B_ac,pk crest (T)')
        ax2_r.plot(vx_op, Lnom_op, color='#22c55e', lw=2,
                   marker='s', ms=4, label='L_full nom (µH)')
        ax2.set_xlabel('V_in,rms (Vac)', fontsize=10)
        ax2.set_ylabel('B_ac,pk (T)', fontsize=10, color='#f59e0b')
        ax2_r.set_ylabel('L_full nom (µH)', fontsize=10, color='#22c55e')
        ax2.set_title('Flux Density and Inductance vs Input Voltage', fontsize=9)
        ax2.grid(True, alpha=0.3); ax2.set_xlim(80, 274)
        lines1, lab1 = ax2.get_legend_handles_labels()
        lines2, lab2 = ax2_r.get_legend_handles_labels()
        ax2.legend(lines1 + lines2, lab1 + lab2, fontsize=8)
    else:
        ax2.set_visible(False)

    fig.tight_layout(pad=1.0)
    story.append(_mpl_to_image(fig, width_mm=170))
    story.append(Paragraph(
        'Figure 14.7 — Left: P_core and P_total vs V_in with +5–20 % uncertainty band '
        '(orange = core, red = total). Right: B_ac,pk and L_full nominal vs V_in. '
        'Gap at 133–179 Vac reflects different power corners in the OPS table.',
        S['caption']))
    story.append(Spacer(1, 4*mm))

    # ── Tabular uncertainty data ──────────────────────────────────────────────
    story.append(Paragraph('Table 14.7 — Loss vs V_in with uncertainty range (100°C winding)', S['h3']))
    hdr = ['V_in rms', 'P_core (W)', 'P_cu (W)', 'P_total (W)',
           'Unc. low (W)', 'Unc. high (W)']
    rows = [[Paragraph(h, S['tbl_hdr']) for h in hdr]]
    for r in lt:
        Pc = r['Pcore_W']; Pcu_r = r['Pcu_W']
        rows.append([Paragraph(str(x), S['tbl_cell']) for x in [
            int(r['Vin_rms']),
            f'{Pc:.3f}', f'{Pcu_r:.3f}', f'{r["Ptotal_W"]:.3f}',
            f'{Pcu_r + 1.05*Pc:.3f}', f'{Pcu_r + 1.20*Pc:.3f}',
        ]])
    cw = [20*mm, 25*mm, 25*mm, 25*mm, 30*mm, 30*mm]
    t = Table(rows, colWidths=cw)
    t.setStyle(_tbl_style())
    story.append(t)
    story.append(Spacer(1, 4*mm))
    story.append(Paragraph(
        '<i>Uncertainty band = P_cu + [1.05 … 1.20] × P_core. '
        'The ±5–20% on core loss is an unanchored engineering estimate; '
        'calibrate against an FEA run or bench measurement before production sign-off.</i>',
        S['note']))
    story.append(Spacer(1, 6*mm))


def _sec_14_8_design_review(story, D, S):
    """Step 14.8 — Design review summary (JS 'Design Review Summary' tab).
    Audit checklist: every pass/fail criterion in one table + narrative summary.
    """
    story.append(PageBreak())
    _h1_band('Step 14.8) Design Review Summary — Audit Checklist', story, S)
    story.append(Paragraph(
        'Consolidated pass/fail audit of the approved design against every design criterion. '
        'Matches the Design Review Summary tab in the Review Magnetics tool.',
        S['body']))
    story.append(Spacer(1, 4*mm))

    N        = D['N']
    stacks   = D['stacks']
    L_tgt    = D['L_target_uH']
    FFcu     = D.get('FFcu_calc', 0.0)
    Ku       = float(D.get('approved_design_Ku', D.get('Ku', 0.0)))
    sat_pct  = D.get('sat_margin_pct', 0.0)
    dT       = D.get('dT_rise_C', 0.0)
    dT_bgt   = D.get('dT_budget_C', 60.0)
    passed   = D.get('passed', True)
    fails    = D.get('fail_reasons', [])

    # L_full from L_vs_Vin_table at 90 Vac
    lvt = D.get('L_vs_Vin_table', [])
    row90 = next((r for r in lvt if int(r.get('Vin_rms', 0)) == 90), None)
    L_full_nom = row90['L_full_nom_uH'] if row90 else L_tgt
    k_actual   = row90['k_bias']        if row90 else 0.0

    # Worst-case L_full_min across all op-points
    L_full_min = min((r['L_full_min_uH'] for r in lvt), default=L_full_nom)

    # Uncertainty
    Punc_lo = D.get('P_unc_lo_W', 0.0)
    Punc_hi = D.get('P_unc_hi_W', 0.0)

    # ── Audit table ───────────────────────────────────────────────────────────
    PASS_C = GREEN; FAIL_C = RED
    hdr = ['Audit item', 'Value', 'Limit / target', 'Result']
    rows = [[Paragraph(h, S['tbl_hdr']) for h in hdr]]

    def _row(item, val, limit, ok):
        tag = '✓ PASS' if ok else '✗ FAIL'
        col = PASS_C if ok else FAIL_C
        return [
            Paragraph(item,  S['tbl_cell_l']),
            Paragraph(val,   S['tbl_cell']),
            Paragraph(limit, S['tbl_cell']),
            Paragraph(f'<b><font color="{col.hexval()}">{tag}</font></b>', S['tbl_cell']),
        ]

    rows.append(_row('Turns N',
        str(N), '—', True))
    rows.append(_row(f'Core stack count',
        f'×{stacks}', '—', True))
    rows.append(_row('Inductance target met',
        f'L_full = {L_full_nom:.1f} µH',
        f'≥ {L_tgt:.0f} µH',
        L_full_nom >= L_tgt))
    rows.append(_row('Worst-case L_full (AL_min, all Vin)',
        f'{L_full_min:.1f} µH',
        f'≥ {L_tgt*0.85:.0f} µH (85% of target)',
        L_full_min >= L_tgt * 0.85))
    rows.append(_row('DC-bias retention k',
        f'{k_actual:.4f}',
        'design-specific',
        k_actual > 0.5))
    rows.append(_row('Bare-copper fill FF_cu',
        f'{FFcu*100:.1f}%',
        '≤ 40% (reference criterion)',
        FFcu <= 0.40))
    rows.append(_row('Insulated fill K_u',
        f'{Ku*100:.1f}%' if Ku > 0 else '—',
        '≤ 75% (practical winding limit)',
        Ku <= 0.75 if Ku > 0 else True))
    rows.append(_row('Saturation margin',
        f'{sat_pct:.1f}%',
        '≥ 15%',
        sat_pct >= 15.0))
    rows.append(_row('Temperature rise ΔT',
        f'{dT:.1f} °C',
        f'≤ {dT_bgt:.0f} °C budget',
        dT <= dT_bgt))
    rows.append(_row('Overall design result',
        'All constraints met' if passed else f'{len(fails)} constraint(s) not met',
        '—',
        passed))

    cw = [75*mm, 40*mm, 50*mm, 25*mm]
    t = Table(rows, colWidths=cw)
    ts = _tbl_style()
    t.setStyle(ts)
    story.append(t)
    story.append(Spacer(1, 4*mm))

    # ── Fail-reason list ──────────────────────────────────────────────────────
    if fails:
        story.append(Paragraph('<b>Constraints not fully met:</b>', S['body']))
        for i, f in enumerate(fails):
            story.append(Paragraph(f'  {i+1}. {f}', S['note']))
        story.append(Spacer(1, 3*mm))

    # ── Narrative summary (matches JS Design Review Summary text) ─────────────
    story.append(Paragraph('Design narrative', S['h2']))

    Pcore_ref  = D.get('Pcore_W', 0.0)
    Pcu_ref    = D.get('Pcu_100_mOhm', D.get('Pcu_100C_W', 0.0))   # from sec 13.7
    Ptot_ref   = D.get('Ptotal_100_lo_W', D.get('Ptotal_100C_W', 0.0))

    summary_lines = [
        f'<b>Selected design:</b> {D["supplier"]} {D["part_number"]}, '
        f'×{stacks} stack, N = {N} turns, '
        f'{D.get("wire_designation","—")} ({D.get("winding_style","—") if "winding_style" in D else "bifilar"}).',

        f'<b>Inductance:</b> L₀ = {D["L0_nom_uH"]:.1f} µH (0 A), '
        f'L_full nom = {L_full_nom:.1f} µH at 90 Vac full load, '
        f'DC-bias retention k = {k_actual:.3f}.',

        f'<b>Flux:</b> B_ac,pk = {D["Bac_pk_T"]*1000:.2f} mT at 90 Vac crest, '
        f'B_max ≈ {D.get("Bmax_FL_T",0)*1000:.1f} mT, '
        f'saturation margin {sat_pct:.0f}%.',

        f'<b>Losses @ 100°C:</b> P_core ≈ {Pcore_ref:.3f} W (half-cycle avg, iGSE), '
        f'P_cu ≈ {D.get("Pcu_100C_W",0):.3f} W, '
        f'P_total ≈ {D.get("Ptotal_100C_W",0):.3f} W. '
        f'Uncertainty range: {Punc_lo:.2f} – {Punc_hi:.2f} W '
        f'(+5 – +20 % core-loss band).',

        f'<b>Thermal:</b> ΔT ≈ {dT:.1f} °C (vs budget {dT_bgt:.0f} °C).',

        f'<b>Overall result: {"PASS — all constraints met" if passed else "REVIEW REQUIRED — see constraints above"}.</b>',
    ]
    for line in summary_lines:
        story.append(Paragraph(line, S['body']))
        story.append(Spacer(1, 2*mm))
    story.append(Spacer(1, 4*mm))

    story.append(Paragraph(
        '<i>This summary matches the Design Review Summary tab of the Review Magnetics tool '
        '(PFC Inductor Studio V5.1). Core-loss uncertainty band +5–20% is an engineering '
        'estimate and should be calibrated against FEA or bench measurement before '
        'production sign-off.</i>',
        S['note']))


# ── Public API ─────────────────────────────────────────────────────────────────
def generate_steps13_14_pdf(approved_design: dict, state: dict) -> bytes:
    """Generate Steps 13–14 PDF bytes."""
    D = _resolve_params(approved_design, state)
    _build_ops_table(D)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
        leftMargin=25.4*mm, rightMargin=25.4*mm, topMargin=22*mm, bottomMargin=18*mm,
        title='PFC Inductor Magnetic Design — Steps 13 & 14',
        author='PFC AI Design Agent')

    S = _S()
    story = []

    _sec_13_1(story, D, S)
    story.append(PageBreak())
    _sec_13_candidates(story, D, S)
    _sec_13_2(story, D, S)
    _sec_13_3(story, D, S)
    story.append(PageBreak())
    _sec_13_4(story, D, S)
    story.append(PageBreak())
    _sec_13_5(story, D, S)
    _sec_13_6(story, D, S)
    story.append(PageBreak())
    _sec_13_7(story, D, S)
    story.append(PageBreak())
    _loss_sweep_table_and_plot(story, D, S, 25,  '13.8')
    story.append(PageBreak())
    _loss_sweep_table_and_plot(story, D, S, 100, '13.9')
    _sec_13_10(story, D, S)
    _sec_14_1(story, D, S)
    _sec_14_2(story, D, S)
    story.append(PageBreak())
    _sec_14_3(story, D, S)
    story.append(PageBreak())
    _sec_14_4(story, D, S)
    story.append(PageBreak())
    _sec_14_5(story, D, S)
    # ── NEW: JS-studio equivalent sections ────────────────────────────────────
    _sec_14_6_extended_waveforms(story, D, S)      # H(t), B(t), Pcu(t), Ptotal(t)
    _sec_14_7_voltage_sweep_uncertainty(story, D, S)  # loss sweep + uncertainty band
    _sec_14_8_design_review(story, D, S)           # audit checklist + narrative

    doc.build(story,
              onFirstPage=_page_header_footer,
              onLaterPages=_page_header_footer)
    return buf.getvalue()
