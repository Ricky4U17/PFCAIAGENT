"""
generate_step16.py
Step 16 — PFC Control Loop Design PDF section.

Generates ReportLab flowables from the dict produced by
step16_control_design.design_control_loops().

Sections:
  16.1  Plant key frequencies (LC pole, ESR zero, RHP zeros)
  16.2  Current loop — Bode plot + compensator component values
  16.3  Voltage loop — Bode plot + compensator component values
  16.4  Stability scorecard — all 9 operating points table
  16.5  Control network BOM summary
"""
from __future__ import annotations
import io, math
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.platypus import (
    Paragraph, Spacer, Table, TableStyle, PageBreak, HRFlowable, Image,
)
from PIL import Image as PILImage

PAGE_W, PAGE_H = A4
LM = RM = 20 * mm
CONTENT_W = PAGE_W - LM - RM

# ── Colours ──────────────────────────────────────────────────────────────────
NAVY   = colors.HexColor("#1F3B63")
BLUE   = colors.HexColor("#2E6CA4")
H2C    = colors.HexColor("#3F7CB5")
GREEN  = colors.HexColor("#2E7D4F")
AMBER  = colors.HexColor("#D4820A")
RED    = colors.HexColor("#C0392B")
NVGREEN= colors.HexColor("#76B900")   # NVIDIA / control-design accent
RULE   = colors.HexColor("#C8D4E8")
STRIPE = colors.HexColor("#F4F8FC")
CAP_C  = colors.HexColor("#5A5A5A")
WHITE  = colors.white
BLACK  = colors.black


def _S():
    return {
        'h1':  ParagraphStyle('h1',  fontName='Helvetica-Bold', fontSize=13,
                   textColor=WHITE, spaceBefore=0, spaceAfter=0, leading=18),
        'h2':  ParagraphStyle('h2',  fontName='Helvetica-Bold', fontSize=12,
                   textColor=H2C, spaceBefore=10, spaceAfter=4, leading=17),
        'h3':  ParagraphStyle('h3',  fontName='Helvetica-Bold', fontSize=10.5,
                   textColor=H2C, spaceBefore=7, spaceAfter=2, leading=14),
        'body': ParagraphStyle('body', fontName='Helvetica', fontSize=9.5,
                   textColor=BLACK, leading=14, spaceAfter=2),
        'eq':   ParagraphStyle('eq',   fontName='Courier', fontSize=9,
                   textColor=NAVY, leading=13, leftIndent=10),
        'note': ParagraphStyle('note', fontName='Helvetica-Oblique', fontSize=8,
                   textColor=CAP_C, leading=11, spaceAfter=4),
        'cap':  ParagraphStyle('cap',  fontName='Helvetica-Oblique', fontSize=8,
                   textColor=CAP_C, alignment=TA_CENTER, leading=11, spaceAfter=6),
        'tbl_hdr': ParagraphStyle('tbl_hdr', fontName='Helvetica-Bold', fontSize=8.5,
                   textColor=WHITE, alignment=TA_CENTER, leading=11),
        'tbl_cell': ParagraphStyle('tbl_cell', fontName='Helvetica', fontSize=8.5,
                   textColor=BLACK, alignment=TA_CENTER, leading=11),
        'tbl_cell_l': ParagraphStyle('tbl_cell_l', fontName='Helvetica', fontSize=8.5,
                   textColor=BLACK, leading=11),
    }


def _h1_band(text: str, story: list, S: dict):
    band = Table([[Paragraph(text, S['h1'])]], colWidths=[CONTENT_W])
    band.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), NAVY),
        ('TOPPADDING',    (0,0), (-1,-1), 7),
        ('BOTTOMPADDING', (0,0), (-1,-1), 7),
        ('LEFTPADDING',   (0,0), (-1,-1), 12),
        ('RIGHTPADDING',  (0,0), (-1,-1), 8),
    ]))
    story.append(Spacer(1, 14*mm))
    story.append(band)
    story.append(Spacer(1, 8*mm))


def _tbl_style(hdr_bg=NAVY):
    return TableStyle([
        ('BACKGROUND',    (0,0), (-1,0),  hdr_bg),
        ('TEXTCOLOR',     (0,0), (-1,0),  WHITE),
        ('FONTNAME',      (0,0), (-1,0),  'Helvetica-Bold'),
        ('FONTSIZE',      (0,0), (-1,0),  8.5),
        ('ALIGN',         (0,0), (-1,0),  'CENTER'),
        ('FONTNAME',      (0,1), (-1,-1), 'Helvetica'),
        ('FONTSIZE',      (0,1), (-1,-1), 8.5),
        ('ROWBACKGROUNDS',(0,1), (-1,-1), [WHITE, STRIPE]),
        ('ALIGN',         (0,1), (-1,-1), 'CENTER'),
        ('GRID',          (0,0), (-1,-1), 0.3, RULE),
        ('VALIGN',        (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING',    (0,0), (-1,-1), 3),
        ('BOTTOMPADDING', (0,0), (-1,-1), 3),
        ('LEFTPADDING',   (0,0), (-1,-1), 5),
        ('RIGHTPADDING',  (0,0), (-1,-1), 5),
    ])


def _mpl_to_image(fig, width_mm: float = 170):
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=180, bbox_inches='tight',
                facecolor='white', edgecolor='none')
    plt.close(fig)
    buf.seek(0)
    w = width_mm * mm
    pil = PILImage.open(buf); pw, ph = pil.size
    h   = w * ph / pw
    buf.seek(0)
    return Image(buf, width=w, height=h)


def _fmt_hz(f: float) -> str:
    if not math.isfinite(f):
        return '—'
    if f >= 1e6: return f'{f/1e6:.2f} MHz'
    if f >= 1e3: return f'{f/1e3:.2f} kHz'
    return f'{f:.1f} Hz'


def _fmt_r(v: float) -> str:
    if not math.isfinite(v): return '—'
    if v >= 1e6: return f'{v/1e6:.3f} MΩ'
    if v >= 1e3: return f'{v/1e3:.2f} kΩ'
    return f'{v:.1f} Ω'


def _fmt_c(v: float) -> str:
    if not math.isfinite(v): return '—'
    if v >= 1e-6: return f'{v*1e6:.2f} µF'
    if v >= 1e-9: return f'{v*1e9:.1f} nF'
    return f'{v*1e12:.1f} pF'


def _pass_pill(ok: bool) -> str:
    col = GREEN.hexval() if ok else RED.hexval()
    txt = 'PASS' if ok else 'FAIL'
    return f'<font color="{col}"><b>{txt}</b></font>'


# ── Section builders ──────────────────────────────────────────────────────────

def _sec_16_1(story, D, S):
    story.append(Paragraph('Step 16.1) Plant Key Frequencies', S['h2']))
    story.append(Paragraph(
        'Small-signal plant critical frequencies computed from the approved '
        'inductor (L, DCR) and capacitor (C, ESR) parameters.',
        S['body']))
    story.append(Spacer(1, 3*mm))

    rows = [
        ['Parameter', 'Value', 'Significance'],
        [Paragraph('f₀ — LC double pole', S['tbl_cell_l']),
         Paragraph(_fmt_hz(D['f_lc_Hz']), S['tbl_cell']),
         Paragraph('Natural resonance of output filter; sets open-loop roll-off slope', S['tbl_cell_l'])],
        [Paragraph('f_esr — capacitor ESR zero', S['tbl_cell_l']),
         Paragraph(_fmt_hz(D['f_esr_Hz']), S['tbl_cell']),
         Paragraph('Adds +20 dB/dec above this; improves phase near f₀', S['tbl_cell_l'])],
        [Paragraph('f_RHPz — RHP zero @ 90 Vac (LL)', S['tbl_cell_l']),
         Paragraph(_fmt_hz(D['f_rhpz_ll_Hz']), S['tbl_cell']),
         Paragraph('Hard ceiling on voltage-loop bandwidth — must stay below f_RHPz / 5', S['tbl_cell_l'])],
        [Paragraph('f_RHPz — RHP zero @ 180 Vac (HL)', S['tbl_cell_l']),
         Paragraph(_fmt_hz(D['f_rhpz_hl_Hz']), S['tbl_cell']),
         Paragraph('Less restrictive than LL due to lower line current at HL', S['tbl_cell_l'])],
        [Paragraph('f_sw / 10 — digital BW ceiling', S['tbl_cell_l']),
         Paragraph(_fmt_hz(D['fsw_Hz'] / 10), S['tbl_cell']),
         Paragraph('Practical digital control limit (Nyquist / 5)', S['tbl_cell_l'])],
        [Paragraph('Recommended V-loop BW', S['tbl_cell_l']),
         Paragraph(_fmt_hz(D['fcv_Hz']), S['tbl_cell']),
         Paragraph('min(fsw/10, f_RHPz/5) — conservative margin', S['tbl_cell_l'])],
        [Paragraph('Recommended I-loop BW', S['tbl_cell_l']),
         Paragraph(_fmt_hz(D['fci_Hz']), S['tbl_cell']),
         Paragraph('fsw / 8 — fast enough for line-cycle tracking', S['tbl_cell_l'])],
    ]
    t = Table(rows[0:1] + rows[1:], colWidths=[58*mm, 30*mm, 82*mm])
    t.setStyle(_tbl_style(NVGREEN))
    story.append(t)
    story.append(Spacer(1, 6*mm))


def _sec_16_2(story, D, S):
    story.append(Paragraph('Step 16.2) Current Loop — Type-II Compensator on I_EA', S['h2']))
    story.append(Paragraph(
        'Average-current-mode inner loop. Crossover target: '
        f'{_fmt_hz(D["fci_Hz"])} (f_sw / 8). '
        'Type-II OTA: one integrator + one zero/pole pair (R_IC, C1, C2).',
        S['body']))
    story.append(Spacer(1, 3*mm))

    # Component table
    mg_ll = D['mg_i_ll']; mg_hl = D['mg_i_hl']
    comp_rows = [
        ['Component', 'Calculated', 'Standard (E96/E24)', 'Function'],
        [Paragraph('R_IC', S['tbl_cell_l']),
         Paragraph(_fmt_r(1/(abs(D['mg_i_ll'].get('fc',1) or 1) * D.get('RIC', 1e3))), S['tbl_cell']),
         Paragraph(_fmt_r(D['RIC']), S['tbl_cell']),
         Paragraph('Sets compensator gain at f_ci', S['tbl_cell_l'])],
        [Paragraph('C1 (zero cap)', S['tbl_cell_l']),
         Paragraph('—', S['tbl_cell']),
         Paragraph(_fmt_c(D['C1_cur']), S['tbl_cell']),
         Paragraph(f'Zero f_z = {_fmt_hz(1/(2*math.pi*D["RIC"]*D["C1_cur"]))}', S['tbl_cell_l'])],
        [Paragraph('C2 (pole cap)', S['tbl_cell_l']),
         Paragraph('—', S['tbl_cell']),
         Paragraph(_fmt_c(D['C2_cur']), S['tbl_cell']),
         Paragraph(f'Pole f_p = {_fmt_hz(1/(2*math.pi*D["RIC"]*D["C2_cur"]))}', S['tbl_cell_l'])],
    ]
    t = Table(comp_rows, colWidths=[35*mm, 32*mm, 32*mm, 71*mm])
    t.setStyle(_tbl_style())
    story.append(t)
    story.append(Spacer(1, 4*mm))

    # Stability margins
    margin_rows = [
        ['Operating point', 'f_c (Hz)', 'Phase margin', 'Gain margin', 'Result'],
        [Paragraph('LL 90 Vac / '+str(int(D['Pout_lo_W']))+' W', S['tbl_cell_l']),
         Paragraph(_fmt_hz(mg_ll['fc']), S['tbl_cell']),
         Paragraph(f"{mg_ll['pm']:.1f}°", S['tbl_cell']),
         Paragraph(f"{mg_ll['gm']:.1f} dB" if math.isfinite(mg_ll['gm']) else '—', S['tbl_cell']),
         Paragraph(_pass_pill(mg_ll['pm'] >= 45), S['tbl_cell'])],
        [Paragraph('HL 180 Vac / '+str(int(D['Pout_hi_W']))+' W', S['tbl_cell_l']),
         Paragraph(_fmt_hz(mg_hl['fc']), S['tbl_cell']),
         Paragraph(f"{mg_hl['pm']:.1f}°", S['tbl_cell']),
         Paragraph(f"{mg_hl['gm']:.1f} dB" if math.isfinite(mg_hl['gm']) else '—', S['tbl_cell']),
         Paragraph(_pass_pill(mg_hl['pm'] >= 45), S['tbl_cell'])],
    ]
    t = Table(margin_rows, colWidths=[50*mm, 28*mm, 28*mm, 28*mm, 36*mm])
    t.setStyle(_tbl_style())
    story.append(t)
    story.append(Spacer(1, 4*mm))

    # Bode plot — current loop
    f_ll, m_ll, p_ll = D['sw_i_ll']
    f_hl, m_hl, p_hl = D['sw_i_hl']

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(7.5, 5.0), sharex=True)
    ax1.semilogx(f_ll, m_ll, color='#2E6DA4', lw=2, label='LL 90 V')
    ax1.semilogx(f_hl, m_hl, color='#f59e0b', lw=1.5, ls='--', label='HL 180 V')
    ax1.axhline(0, color='#555', lw=0.8, ls=':')
    ax1.set_ylabel('Magnitude (dB)', fontsize=9)
    ax1.set_title('Current Loop T_i(s) — magnitude & phase', fontsize=10)
    ax1.legend(fontsize=8); ax1.grid(True, alpha=0.3)

    ax2.semilogx(f_ll, p_ll, color='#2E6DA4', lw=2)
    ax2.semilogx(f_hl, p_hl, color='#f59e0b', lw=1.5, ls='--')
    ax2.axhline(-180, color='#555', lw=0.8, ls=':')
    ax2.set_xlabel('Frequency (Hz)', fontsize=9)
    ax2.set_ylabel('Phase (°)', fontsize=9)
    ax2.grid(True, alpha=0.3)
    fig.tight_layout()
    story.append(_mpl_to_image(fig))
    story.append(Paragraph(
        'Figure 16.2 — Current loop Bode plot: LL 90 V (blue solid) and HL 180 V (amber dashed). '
        'Target PM ≥ 45°.', S['cap']))
    story.append(Spacer(1, 6*mm))


def _sec_16_3(story, D, S):
    is_t3  = D.get('v_type', 'type2') == 'type3'
    tname  = 'Type-III' if is_t3 else 'Type-II'
    tdesc  = ('two integrators + 2 zeros + 2 poles (R2, R3, C1, C2, C3) — SLVA662 Method B'
              if is_t3 else
              'one integrator + one zero/pole pair (R2, C1, C3)')
    story.append(Paragraph(f'Step 16.3) Voltage Loop — {tname} OTA Compensator on V_EA', S['h2']))
    story.append(Paragraph(
        f'Outer voltage loop. Crossover target: '
        f'{_fmt_hz(D["fcv_Hz"])} = min(f_sw/10, f_RHPz/5). '
        f'{tname} OTA: {tdesc}.',
        S['body']))
    story.append(Spacer(1, 3*mm))

    mg_ll = D['mg_v_ll']; mg_hl = D['mg_v_hl']
    R2 = D['R2']; C1v = D['C1_vol']; C3v = D['C3_vol']
    if is_t3:
        R3 = D.get('R3', 0); C2v = D.get('C2_vol', 0)
        R1fb = D['R1fb']
        fz1 = 1/(2*math.pi*R2*C1v)      if (R2 and C1v) else float('nan')
        fz2 = 1/(2*math.pi*(R1fb+R3)*C2v) if (R1fb and R3 and C2v) else float('nan')
        P   = R1fb * D['R4fb'] / (R1fb + D['R4fb'])
        fp1 = (C1v+C3v)/(2*math.pi*R2*C1v*C3v) if (R2 and C1v and C3v) else float('nan')
        fp2 = 1/(2*math.pi*(R3+P)*C2v) if (R3 and P and C2v) else float('nan')
        comp_rows = [
            ['Component', 'Standard value', 'Function'],
            [Paragraph('R2', S['tbl_cell_l']),
             Paragraph(_fmt_r(R2), S['tbl_cell']),
             Paragraph(f'Primary gain resistor  (f_cv = {_fmt_hz(D["fcv_Hz"])})', S['tbl_cell_l'])],
            [Paragraph('R3 (branch)', S['tbl_cell_l']),
             Paragraph(_fmt_r(R3), S['tbl_cell']),
             Paragraph(f'Second-branch resistor  (f_z2 = {_fmt_hz(fz2)})', S['tbl_cell_l'])],
            [Paragraph('C1 (zero-1 cap)', S['tbl_cell_l']),
             Paragraph(_fmt_c(C1v), S['tbl_cell']),
             Paragraph(f'Zero-1  f_z1 = {_fmt_hz(fz1)}', S['tbl_cell_l'])],
            [Paragraph('C2 (branch cap)', S['tbl_cell_l']),
             Paragraph(_fmt_c(C2v), S['tbl_cell']),
             Paragraph(f'Branch zero/pole pair  f_p2 = {_fmt_hz(fp2)}', S['tbl_cell_l'])],
            [Paragraph('C3 (pole-1 cap)', S['tbl_cell_l']),
             Paragraph(_fmt_c(C3v), S['tbl_cell']),
             Paragraph(f'Pole-1  f_p1 = {_fmt_hz(fp1)}', S['tbl_cell_l'])],
            [Paragraph('R_FB1 (string)', S['tbl_cell_l']),
             Paragraph(_fmt_r(D['R1fb']), S['tbl_cell']),
             Paragraph('Upper feedback divider (3 × 402 kΩ typ)', S['tbl_cell_l'])],
            [Paragraph('R_FB2', S['tbl_cell_l']),
             Paragraph(_fmt_r(D['R4fb']), S['tbl_cell']),
             Paragraph(f'Lower divider → V_out = {D["Vout_V"]:.1f} V', S['tbl_cell_l'])],
        ]
    else:
        fz1 = 1/(2*math.pi*R2*C1v) if (R2 and C1v) else float('nan')
        comp_rows = [
            ['Component', 'Standard value', 'Function'],
            [Paragraph('R2', S['tbl_cell_l']),
             Paragraph(_fmt_r(R2), S['tbl_cell']),
             Paragraph(f'Sets voltage-loop gain at f_cv = {_fmt_hz(D["fcv_Hz"])}', S['tbl_cell_l'])],
            [Paragraph('C1 (zero cap)', S['tbl_cell_l']),
             Paragraph(_fmt_c(C1v), S['tbl_cell']),
             Paragraph(f'Zero  f_z1 = {_fmt_hz(fz1)}', S['tbl_cell_l'])],
            [Paragraph('C3 (pole cap)', S['tbl_cell_l']),
             Paragraph(_fmt_c(C3v), S['tbl_cell']),
             Paragraph(f'Pole f_p1 ≈ f_ESR = {_fmt_hz(D["f_esr_Hz"])}', S['tbl_cell_l'])],
            [Paragraph('R_FB1 (string)', S['tbl_cell_l']),
             Paragraph(_fmt_r(D['R1fb']), S['tbl_cell']),
             Paragraph('Upper feedback divider (3 × 402 kΩ typ)', S['tbl_cell_l'])],
            [Paragraph('R_FB2', S['tbl_cell_l']),
             Paragraph(_fmt_r(D['R4fb']), S['tbl_cell']),
             Paragraph(f'Lower divider → V_out = {D["Vout_V"]:.1f} V', S['tbl_cell_l'])],
        ]
    t = Table(comp_rows, colWidths=[30*mm, 32*mm, 108*mm])
    t.setStyle(_tbl_style())
    story.append(t)
    story.append(Spacer(1, 4*mm))

    margin_rows = [
        ['Operating point', 'f_c (Hz)', 'Phase margin', 'Gain margin', '120 Hz rej.', 'Result'],
    ]
    for row in D['scorecard'][:2]:
        mg  = {'fc': row['fc_v'], 'pm': row['pm_v'], 'gm': row['gm_v']}
        rej = row['rej_120']
        ok  = row['pm_v'] >= 55 and rej >= 20
        margin_rows.append([
            Paragraph(f'{"LL" if row["Vin_rms"]<=132 else "HL"} {row["Vin_rms"]} Vac', S['tbl_cell_l']),
            Paragraph(_fmt_hz(row['fc_v']), S['tbl_cell']),
            Paragraph(f"{row['pm_v']:.1f}°", S['tbl_cell']),
            Paragraph(f"{row['gm_v']:.1f} dB" if math.isfinite(row['gm_v']) else '—', S['tbl_cell']),
            Paragraph(f"{rej:.1f} dB", S['tbl_cell']),
            Paragraph(_pass_pill(ok), S['tbl_cell']),
        ])
    t = Table(margin_rows, colWidths=[38*mm, 25*mm, 25*mm, 25*mm, 25*mm, 32*mm])
    t.setStyle(_tbl_style())
    story.append(t)
    story.append(Spacer(1, 4*mm))

    # Bode plot — voltage loop
    f_ll, m_ll, p_ll = D['sw_v_ll']
    f_hl, m_hl, p_hl = D['sw_v_hl']

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(7.5, 5.0), sharex=True)
    ax1.semilogx(f_ll, m_ll, color='#2E6DA4', lw=2, label='LL 90 V')
    ax1.semilogx(f_hl, m_hl, color='#f59e0b', lw=1.5, ls='--', label='HL 180 V')
    ax1.axhline(0, color='#555', lw=0.8, ls=':')
    ax1.set_ylabel('Magnitude (dB)', fontsize=9)
    ax1.set_title('Voltage Loop T_v(s) — magnitude & phase', fontsize=10)
    ax1.legend(fontsize=8); ax1.grid(True, alpha=0.3)

    ax2.semilogx(f_ll, p_ll, color='#2E6DA4', lw=2)
    ax2.semilogx(f_hl, p_hl, color='#f59e0b', lw=1.5, ls='--')
    ax2.axhline(-180, color='#555', lw=0.8, ls=':')
    ax2.set_xlabel('Frequency (Hz)', fontsize=9)
    ax2.set_ylabel('Phase (°)', fontsize=9)
    ax2.grid(True, alpha=0.3)
    fig.tight_layout()
    story.append(_mpl_to_image(fig))
    story.append(Paragraph(
        'Figure 16.3 — Voltage loop Bode plot: LL 90 V (blue solid) and HL 180 V (amber dashed). '
        'Target PM ≥ 55°, 120 Hz rejection ≥ 20 dB.', S['cap']))
    story.append(Spacer(1, 6*mm))


def _sec_16_4(story, D, S):
    story.append(PageBreak())
    story.append(Paragraph('Step 16.4) Stability Scorecard — All 9 Operating Points', S['h2']))
    story.append(Paragraph(
        'Loop margins evaluated at each of the 9 standard operating points '
        '(4 low-line × Pout_lo, 5 high-line × Pout_hi). '
        'Pass criteria: I-loop PM ≥ 45°, V-loop PM ≥ 55°, 120 Hz rejection ≥ 20 dB.',
        S['body']))
    story.append(Spacer(1, 3*mm))

    hdr = ['Vin rms', 'P_out', 'I-loop fc', 'I PM', 'I GM',
           'V-loop fc', 'V PM', 'V GM', '120 Hz rej.', 'Result']
    rows = [[Paragraph(h, S['tbl_hdr']) for h in hdr]]
    for r in D['scorecard']:
        ok = r['pass']
        row_bg = colors.HexColor('#e8f5e9') if ok else colors.HexColor('#fde8e8')
        rows.append([
            Paragraph(f"{r['Vin_rms']} Vac ({r['line']})", S['tbl_cell_l']),
            Paragraph(f"{int(r['Pout'])} W", S['tbl_cell']),
            Paragraph(_fmt_hz(r['fc_i']), S['tbl_cell']),
            Paragraph(f"{r['pm_i']:.0f}°", S['tbl_cell']),
            Paragraph(f"{r['gm_i']:.0f} dB" if math.isfinite(r['gm_i']) else '—', S['tbl_cell']),
            Paragraph(_fmt_hz(r['fc_v']), S['tbl_cell']),
            Paragraph(f"{r['pm_v']:.0f}°", S['tbl_cell']),
            Paragraph(f"{r['gm_v']:.0f} dB" if math.isfinite(r['gm_v']) else '—', S['tbl_cell']),
            Paragraph(f"{r['rej_120']:.0f} dB", S['tbl_cell']),
            Paragraph(_pass_pill(ok), S['tbl_cell']),
        ])

    cw = [25*mm, 18*mm, 18*mm, 14*mm, 14*mm, 18*mm, 14*mm, 14*mm, 18*mm, 17*mm]
    t = Table(rows, colWidths=cw)
    ts = _tbl_style()
    for i, r in enumerate(D['scorecard'], 1):
        if r['pass']:
            ts.add('BACKGROUND', (0, i), (-1, i), colors.HexColor('#e8f5e9'))
        else:
            ts.add('BACKGROUND', (0, i), (-1, i), colors.HexColor('#fde8e8'))
    t.setStyle(ts)
    story.append(t)
    story.append(Spacer(1, 4*mm))
    n_pass = sum(1 for r in D['scorecard'] if r['pass'])
    story.append(Paragraph(
        f'<b>{n_pass}/{len(D["scorecard"])} operating points pass all criteria.</b>  '
        'Green rows = PASS; red rows = one or more criteria not met.',
        S['note']))
    story.append(Spacer(1, 6*mm))


def _sec_16_5(story, D, S):
    is_t3  = D.get('v_type', 'type2') == 'type3'
    tname  = 'Type-III' if is_t3 else 'Type-II'
    story.append(Paragraph('Step 16.5) Control Network BOM Summary', S['h2']))
    story.append(Paragraph(
        f'Standard-value control components for the FAN9672. '
        f'Current loop: Type-II OTA on I_EA.  '
        f'Voltage loop: {tname} OTA on V_EA.',
        S['body']))
    story.append(Spacer(1, 3*mm))

    css_str  = _fmt_c(D['css'])
    t_ss_str = f"{D['t_ss_ms']:.0f} ms"
    fci_zero = _fmt_hz(1/(2*math.pi*D['RIC']*D['C1_cur']))
    fci_pole = _fmt_hz(1/(2*math.pi*D['RIC']*D['C2_cur']))
    R2 = D['R2']; C1v = D['C1_vol']; C3v = D['C3_vol']
    fcv_z1   = _fmt_hz(1/(2*math.pi*R2*C1v)) if (R2 and C1v) else '—'

    bom_rows = [
        ['Ref.', 'Value', 'Function'],
        [Paragraph('R_IC  (I-loop gain)', S['tbl_cell_l']),
         Paragraph(_fmt_r(D['RIC']), S['tbl_cell']),
         Paragraph(f'Current-loop gain resistor  (f_ci = {_fmt_hz(D["fci_Hz"])})', S['tbl_cell_l'])],
        [Paragraph('C1_IC  (zero cap)', S['tbl_cell_l']),
         Paragraph(_fmt_c(D['C1_cur']), S['tbl_cell']),
         Paragraph(f'Current-loop zero  f_z = {fci_zero}', S['tbl_cell_l'])],
        [Paragraph('C2_IC  (pole cap)', S['tbl_cell_l']),
         Paragraph(_fmt_c(D['C2_cur']), S['tbl_cell']),
         Paragraph(f'Current-loop pole  f_p = {fci_pole}', S['tbl_cell_l'])],
        [Paragraph('R2_VC  (V-loop gain)', S['tbl_cell_l']),
         Paragraph(_fmt_r(R2), S['tbl_cell']),
         Paragraph(f'Voltage-loop gain resistor  (f_cv = {_fmt_hz(D["fcv_Hz"])})', S['tbl_cell_l'])],
    ]
    if is_t3:
        R3 = D.get('R3', 0); C2v = D.get('C2_vol', 0)
        bom_rows += [
            [Paragraph('R3_VC  (branch)', S['tbl_cell_l']),
             Paragraph(_fmt_r(R3), S['tbl_cell']),
             Paragraph('Type-III second-branch resistor (fz2/fp2 pair)', S['tbl_cell_l'])],
            [Paragraph('C1_VC  (zero-1 cap)', S['tbl_cell_l']),
             Paragraph(_fmt_c(C1v), S['tbl_cell']),
             Paragraph(f'Voltage-loop zero-1  f_z1 = {fcv_z1}', S['tbl_cell_l'])],
            [Paragraph('C2_VC  (branch cap)', S['tbl_cell_l']),
             Paragraph(_fmt_c(C2v), S['tbl_cell']),
             Paragraph('Type-III branch capacitor (fz2/fp2 pair)', S['tbl_cell_l'])],
            [Paragraph('C3_VC  (pole-1 cap)', S['tbl_cell_l']),
             Paragraph(_fmt_c(C3v), S['tbl_cell']),
             Paragraph(f'Voltage-loop pole-1 ≈ f_ESR = {_fmt_hz(D["f_esr_Hz"])}', S['tbl_cell_l'])],
        ]
    else:
        bom_rows += [
            [Paragraph('C1_VC  (zero cap)', S['tbl_cell_l']),
             Paragraph(_fmt_c(C1v), S['tbl_cell']),
             Paragraph(f'Voltage-loop zero  f_z = {fcv_z1}', S['tbl_cell_l'])],
            [Paragraph('C3_VC  (pole cap)', S['tbl_cell_l']),
             Paragraph(_fmt_c(C3v), S['tbl_cell']),
             Paragraph(f'Voltage-loop pole ≈ f_ESR = {_fmt_hz(D["f_esr_Hz"])}', S['tbl_cell_l'])],
        ]
    bom_rows += [
        [Paragraph('C_SS  (soft-start)', S['tbl_cell_l']),
         Paragraph(css_str, S['tbl_cell']),
         Paragraph(f'Soft-start time ≈ {t_ss_str} (I_SS = 20 µA, V_SS = 5 V)', S['tbl_cell_l'])],
        [Paragraph('R_FB1  (upper divider)', S['tbl_cell_l']),
         Paragraph(_fmt_r(D['R1fb']), S['tbl_cell']),
         Paragraph(f'V_out feedback — sets {D["Vout_V"]:.1f} V with R_FB2', S['tbl_cell_l'])],
        [Paragraph('R_FB2  (lower divider)', S['tbl_cell_l']),
         Paragraph(_fmt_r(D['R4fb']), S['tbl_cell']),
         Paragraph(f'V_ref = 2.50 V → R_FB1/R_FB2 = {D["R1fb"]/D["R4fb"]:.1f}', S['tbl_cell_l'])],
    ]
    t = Table(bom_rows, colWidths=[50*mm, 28*mm, 92*mm])
    t.setStyle(_tbl_style())
    story.append(t)
    story.append(Spacer(1, 4*mm))
    story.append(Paragraph(
        f'<i>Component values taken from the JS Control Design Tool (Screen 2) — '
        f'{tname} voltage OTA. R_IC and R2 from E96; capacitors from E24. '
        f'Bode plots above are computed with these exact standard values.</i>',
        S['note']))


# ── Public API ────────────────────────────────────────────────────────────────

def generate_step16_section(ctrl: dict) -> list:
    """
    Generate ReportLab flowables for Step 16 — Control Loop Design.
    ctrl: dict from step16_control_design.design_control_loops()
    """
    S     = _S()
    story = []

    _h1_band('Step 16) PFC Control Loop Design — FAN9672', story, S)
    story.append(Paragraph(
        'This step designs the average-current-mode (ACM) control loops for the '
        'two-phase interleaved boost PFC using the FAN9672 controller IC. '
        'Transfer functions match the PFC Control Loop Design Tool v4 equations. '
        'Plant parameters are taken directly from the approved inductor (Step 7) '
        'and output capacitor (Step 15).',
        S['body']))
    story.append(Spacer(1, 4*mm))

    _sec_16_1(story, ctrl, S)
    _sec_16_2(story, ctrl, S)
    story.append(PageBreak())
    _sec_16_3(story, ctrl, S)
    _sec_16_4(story, ctrl, S)
    _sec_16_5(story, ctrl, S)

    return story
