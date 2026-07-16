"""
generate_step15.py
ReportLab story elements for Step 15 — Vout Capacitor Design.
Covers Steps 15.1–15.8 per spec.
Returns a list of Platypus flowables; caller merges into existing story.
"""
from __future__ import annotations
import math

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.platypus import (
    Paragraph, Spacer, Table, TableStyle, PageBreak, HRFlowable,
)

PAGE_W, _ = A4
LM = RM = 20 * mm
CONTENT_W = PAGE_W - LM - RM

NAVY   = colors.HexColor("#1F3B63")   # H1 band, table headers
BLUE   = colors.HexColor("#2E6CA4")   # subtitle, labels
H2C    = colors.HexColor("#3F7CB5")   # H2 headings
GREEN  = colors.HexColor("#2E7D4F")
AMBER  = colors.HexColor("#D4820A")
LIGHT  = colors.HexColor("#EBF2FA")
RULE   = colors.HexColor("#C8D4E8")   # grid lines
MUTED  = colors.HexColor("#6B7A8D")
STRIPE = colors.HexColor("#F4F8FC")   # alternating rows
CAP_C  = colors.HexColor("#5A5A5A")   # captions
WHITE  = colors.white
BLACK  = colors.black
TEAL   = H2C                          # backward compat


def _S():
    return {
        # H1: 13 pt bold white on navy band (Word doc Heading 1)
        'h1':   ParagraphStyle('h1',  fontName='Helvetica-Bold', fontSize=13,
                    textColor=WHITE, spaceBefore=0, spaceAfter=0, leading=18),
        # H2: 12 pt bold #3F7CB5 — Word doc step sub-headings (Aptos Display 12 pt)
        'h2':   ParagraphStyle('h2',  fontName='Helvetica-Bold', fontSize=12,
                    textColor=H2C, spaceBefore=10, spaceAfter=4, leading=17),
        # H3: 10.5 pt bold #3F7CB5
        'h3':   ParagraphStyle('h3',  fontName='Helvetica-Bold', fontSize=10.5,
                    textColor=H2C, spaceBefore=7,  spaceAfter=2, leading=14),
        # Body: 9.5 pt — Word doc "Aptos Narrow" 9.5 pt
        'body': ParagraphStyle('body', fontName='Helvetica', fontSize=9.5,
                    textColor=BLACK, leading=14, spaceAfter=2),
        'eq':   ParagraphStyle('eq',  fontName='Courier', fontSize=9,
                    textColor=NAVY, leading=13, leftIndent=10),
        # Note/caption: 8 pt italic — Word doc figure caption style
        'note': ParagraphStyle('note', fontName='Helvetica-Oblique', fontSize=8,
                    textColor=CAP_C, leading=11, spaceAfter=4),
        'tbl_hdr':  ParagraphStyle('tbl_hdr',  fontName='Helvetica-Bold', fontSize=8.5,
                    textColor=WHITE, alignment=TA_CENTER, leading=11),
        'tbl_cell': ParagraphStyle('tbl_cell', fontName='Helvetica', fontSize=8.5,
                    textColor=BLACK, alignment=TA_CENTER, leading=11),
        'tbl_cell_l': ParagraphStyle('tbl_cell_l', fontName='Helvetica', fontSize=8.5,
                    textColor=BLACK, leading=11),
    }


def _rule():
    return HRFlowable(width='100%', thickness=0.4, color=RULE,
                      spaceBefore=4, spaceAfter=4)


def _h1_band(text, story, S, cw=None, sb=14, sa=8):
    """Heading 1: white text on navy band."""
    _cw = cw or (PAGE_W - LM - RM)
    band = Table([[Paragraph(text, S['h1'])]], colWidths=[_cw])
    band.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), NAVY),
        ('TOPPADDING',    (0,0), (-1,-1), 7),
        ('BOTTOMPADDING', (0,0), (-1,-1), 7),
        ('LEFTPADDING',   (0,0), (-1,-1), 12),
        ('RIGHTPADDING',  (0,0), (-1,-1), 8),
    ]))
    story.append(Spacer(1, sb))
    story.append(band)
    story.append(Spacer(1, sa))


def _tbl(rows, col_widths, hdr_bg=NAVY):
    t = Table(rows, colWidths=col_widths)
    t.setStyle(TableStyle([
        ('BACKGROUND',     (0,0),  (-1,0),  hdr_bg),
        ('TEXTCOLOR',      (0,0),  (-1,0),  WHITE),
        ('FONTNAME',       (0,0),  (-1,0),  'Helvetica-Bold'),
        ('FONTSIZE',       (0,0),  (-1,0),  8.5),
        ('ALIGN',          (0,0),  (-1,0),  'CENTER'),
        ('FONTNAME',       (0,1),  (-1,-1), 'Helvetica'),
        ('FONTSIZE',       (0,1),  (-1,-1), 8.5),
        ('ROWBACKGROUNDS', (0,1),  (-1,-1), [WHITE, STRIPE]),
        ('ALIGN',          (0,1),  (-1,-1), 'CENTER'),
        ('GRID',           (0,0),  (-1,-1), 0.3, RULE),
        ('VALIGN',         (0,0),  (-1,-1), 'MIDDLE'),
        ('TOPPADDING',     (0,0),  (-1,-1), 3),
        ('BOTTOMPADDING',  (0,0),  (-1,-1), 3),
        ('LEFTPADDING',    (0,0),  (-1,-1), 5),
        ('RIGHTPADDING',   (0,0),  (-1,-1), 5),
    ]))
    return t


def _kv_tbl(rows, S):
    """Simple two-column key/value table."""
    data = [[Paragraph(k, S['body']), Paragraph(v, S['eq'])] for k, v in rows]
    t = Table(data, colWidths=[90*mm, 85*mm])
    t.setStyle(TableStyle([
        ('ROWBACKGROUNDS', (0,0), (-1,-1), [WHITE, STRIPE]),
        ('GRID', (0,0), (-1,-1), 0.3, RULE),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING', (0,0), (-1,-1), 3),
        ('BOTTOMPADDING', (0,0), (-1,-1), 3),
        ('LEFTPADDING', (0,0), (-1,-1), 6),
    ]))
    return t


def generate_step15_section(result: dict) -> list:
    """
    Generate ReportLab story elements for Step 15 (Sections 15.1 – 15.10).
    result: merged dict from run_capacitor_design() + verify_configuration() + thermal.
    """
    S    = _S()
    inp  = result.get("inputs", {})
    wc   = result.get("worst_case", {})
    ll   = result.get("low_line",   {})
    ver  = result.get("verified")   or {}
    th   = result.get("thermal")    or {}
    story = []

    _h1_band('Step 15) V<sub>out</sub> Capacitor Design', story, S)

    # ── 15.1 Inputs ──────────────────────────────────────────────────────────
    story.append(Paragraph('Step 15.1) Design Inputs', S['h2']))
    story.append(_kv_tbl([
        ('V<sub>out</sub>',         f"{inp.get('Vout_V',393.7):.1f} Vdc"),
        ('f<sub>line</sub>',        f"{inp.get('f_line_Hz',60):.0f} Hz"),
        ('V<sub>dc,ripple</sub>',   f"{inp.get('Vdc_ripple_V',20):.0f} V pk-pk"),
        ('V<sub>dc,min</sub> (hold-up floor)', f"{inp.get('Vdc_min_V',290):.0f} V"),
        ('t<sub>hold</sub>',        f"{inp.get('t_hold_ms',20):.0f} ms"),
        ('V<sub>out,max</sub> (transient)', f"{inp.get('Vout_max_V',432):.0f} V"),
    ], S))
    story.append(Spacer(1, 5*mm))

    # ── 15.2 C_holdup — step-by-step for both operating points ──────────────
    Vout     = float(inp.get('Vout_V',     393))
    f_line   = float(inp.get('f_line_Hz',  60))
    Vdc_rip  = float(inp.get('Vdc_ripple_V', 20))
    Vdc_min  = float(inp.get('Vdc_min_V',  290))
    t_hold_s = float(inp.get('t_hold_ms',  20)) / 1000.0
    Vout_max = float(inp.get('Vout_max_V', Vout * 1.10))

    story.append(Paragraph('Step 15.2) Output Capacitance for Hold-up Time', S['h2']))
    story.append(Paragraph(
        'C<sub>holdup</sub> = 2 &middot; P<sub>out</sub> &middot; t<sub>hold</sub> / '
        '(V<sub>out</sub><super>2</super> &minus; V<sub>dc,min</sub><super>2</super>)', S['eq']))
    story.append(Spacer(1, 2*mm))
    for label, op in [('Worst-case (180 Vac)', wc), ('Low-line (90 Vac)', ll)]:
        P   = op.get('Pout',0);  eta = op.get('eta',1)
        C_h = op.get('C_holdup_uF',0)
        story.append(Paragraph(f'<b>{label}:</b>', S['body']))
        story.append(Paragraph(
            f"C<sub>holdup</sub> = 2 &middot; {P} &middot; {t_hold_s:.3f} / "
            f"({Vout:.0f}<super>2</super> &minus; {Vdc_min:.0f}<super>2</super>) = "
            f"<b>{C_h:.1f} &micro;F</b>", S['eq']))
    story.append(Spacer(1, 4*mm))

    # ── 15.3 C_ripple — step-by-step ─────────────────────────────────────────
    story.append(Paragraph('Step 15.3) Output Capacitance for Voltage Ripple', S['h2']))
    story.append(Paragraph(
        'C<sub>ripple</sub> = P<sub>out</sub> / '
        '(2&pi; &middot; f<sub>line</sub> &middot; &eta; &middot; V<sub>out</sub> &middot; V<sub>dc,ripple</sub>)',
        S['eq']))
    story.append(Spacer(1, 2*mm))
    for label, op in [('Worst-case (180 Vac)', wc), ('Low-line (90 Vac)', ll)]:
        P   = op.get('Pout',0);  eta = op.get('eta',1)
        C_r = op.get('C_ripple_uF',0)
        story.append(Paragraph(f'<b>{label}:</b>', S['body']))
        story.append(Paragraph(
            f"C<sub>ripple</sub> = {P} / "
            f"(2&pi; &middot; {f_line:.0f} &middot; {eta} &middot; {Vout:.0f} &middot; {Vdc_rip:.0f}) = "
            f"<b>{C_r:.1f} &micro;F</b>", S['eq']))
    story.append(Spacer(1, 4*mm))

    # ── 15.4 C required + bank decision ──────────────────────────────────────
    story.append(Paragraph('Step 15.4) Required Capacitance and Bank Decision', S['h2']))
    C_req_uF = float(result.get('C_required_uF', 0))
    governing = result.get('governing','—')
    story.append(Paragraph(
        f"C<sub>required</sub> = max(C<sub>holdup,worst</sub>, C<sub>holdup,low</sub>, "
        f"C<sub>ripple,worst</sub>, C<sub>ripple,low</sub>) = "
        f"<b>{C_req_uF:.1f} &micro;F</b> &nbsp;"
        f"(governing: {governing})", S['eq']))
    # Bank decision from verified data
    if ver:
        C_tot = float(ver.get('C_total_uF', 0))
        n_tot = int(ver.get('total_cap_count', 1))
        cap_specs = ver.get('cap_specs', [])
        if cap_specs:
            c_each = float(cap_specs[0].get('value_uF', 0))
            n_min  = math.ceil(C_req_uF / c_each) if c_each > 0 else n_tot
            margin = (C_tot - C_req_uF) / C_req_uF * 100 if C_req_uF > 0 else 0
            story.append(Spacer(1, 2*mm))
            story.append(Paragraph(
                f"Bank: N = ceil({C_req_uF:.1f} / {c_each:.0f}) = {n_min}  "
                f"&rarr; selected N = {n_tot} &times; {c_each:.0f} &micro;F = "
                f"<b>C<sub>bank</sub> = {C_tot:.0f} &micro;F</b>  "
                f"(+{margin:.1f}% margin)", S['eq']))
    story.append(Spacer(1, 4*mm))

    # ── 15.5 Voltage rating ───────────────────────────────────────────────────
    story.append(Paragraph('Step 15.5) Voltage Rating and Selected Capacitor', S['h2']))
    V_min_r = result.get('V_rating_min_V', 0)
    V_sel   = result.get('V_rating_selected_V', 450)
    story.append(Paragraph(
        f"V<sub>min,rating</sub> = max(V<sub>out</sub> &times; 1.12, V<sub>out,max</sub>) = "
        f"max({Vout:.0f} &times; 1.12, {Vout_max:.0f}) = {V_min_r:.1f} V &nbsp;&rarr;&nbsp; "
        f"<b>Selected: {V_sel} V class</b>", S['eq']))
    story.append(Spacer(1, 3*mm))
    # Selected part table
    cap_specs = ver.get('cap_specs', []) if ver else []
    if cap_specs:
        cs = cap_specs[0]
        story.append(Paragraph('Selected part from database:', S['body']))
        rows_sel = [
            ['Manufacturer / Series',  f"{ver.get('supplier','—')} / {ver.get('series','—')}",
             'Rated life',             cs.get('lifetime','—') if isinstance(cs,dict) and 'lifetime' in cs else '—'],
            ['Part number',            cs.get('part_number','—'),
             'Operating temp',         cs.get('op_temp','—') if isinstance(cs,dict) and 'op_temp' in cs else '—'],
            ['Capacitance / voltage',  f"{cs.get('value_uF','—')} &micro;F / {cs.get('voltage_rating_V','—')} V",
             'ESR each',               f"{cs.get('ESR_each_mohm','—')} m&Omega;"],
            ['Quantity in bank',       str(cs.get('qty','—')),
             'I<sub>rated</sub> @120Hz', f"{cs.get('I_rated_A','—')} A"],
            ['Temp rating',            f"{cs.get('temp_rating_C','—')}&deg;C",
             'C<sub>bank</sub> total', f"{ver.get('C_total_uF','—')} &micro;F"],
        ]
        data_sel = []
        for r in rows_sel:
            data_sel.append([
                Paragraph(r[0], S['tbl_cell_l']), Paragraph(str(r[1]), S['eq']),
                Paragraph(r[2], S['tbl_cell_l']), Paragraph(str(r[3]), S['eq']),
            ])
        t_sel = Table(data_sel, colWidths=[40*mm,55*mm,38*mm,42*mm])
        t_sel.setStyle(TableStyle([
            ('ROWBACKGROUNDS',(0,0),(-1,-1),[WHITE,STRIPE]),
            ('GRID',(0,0),(-1,-1),0.3,RULE),('VALIGN',(0,0),(-1,-1),'MIDDLE'),
            ('TOPPADDING',(0,0),(-1,-1),3),('BOTTOMPADDING',(0,0),(-1,-1),3),
            ('LEFTPADDING',(0,0),(-1,-1),5),
        ]))
        story.append(t_sel)
    story.append(Spacer(1, 4*mm))

    # ── 15.6 Full 9-point RMS current table ───────────────────────────────────
    story.append(PageBreak())
    story.append(Paragraph('Step 15.6) Capacitor RMS Current — All 9 Operating Points', S['h2']))
    story.append(Paragraph(
        # SAME decomposition as the DC-bus capacitor simulation page (standard boost-diode RMS
        # identity, √N interleave reduction) — the two pages agree by construction.
        'I<sub>o</sub> = P<sub>out</sub> / V<sub>out</sub> &nbsp;&nbsp;'
        'I<sub>LF</sub> = P<sub>out</sub> / (&radic;2 &middot; V<sub>out</sub>) &nbsp;&nbsp;'
        'I<sub>D,rms</sub><super>2</super> = 8&radic;2 &middot; P<sub>in</sub><super>2</super> / '
        '(3&pi; &middot; V<sub>ac</sub> &middot; PF<super>2</super> &middot; V<sub>out</sub>) &nbsp;&nbsp;'
        'I<sub>HF</sub> = &radic;(I<sub>D,rms</sub><super>2</super> &minus; I<sub>o</sub><super>2</super> '
        '&minus; I<sub>LF</sub><super>2</super>) / &radic;N &nbsp;&nbsp;'
        'I<sub>total</sub> = &radic;(I<sub>LF</sub><super>2</super> + I<sub>HF</sub><super>2</super>)',
        S['body']))
    story.append(Spacer(1, 2*mm))

    th_tbl = th.get("thermal_table", [])
    hdr6 = ['V<sub>in</sub>\n(Vac)', 'P<sub>out</sub>\n(W)', '&eta;',
            'I<sub>o</sub>\n(A)', 'I<sub>LF</sub>\n(A)',
            'I<sub>HF</sub>\n(A)', 'I<sub>total</sub>\n(A)']
    rows6 = [[Paragraph(h, S['tbl_hdr']) for h in hdr6]]
    WC_VIN = 180; LL_VIN = 90
    ts6_extra = []
    for i, row in enumerate(th_tbl):
        ri = i + 1
        is_wc = row.get("Vin_rms") == WC_VIN
        is_ll = row.get("Vin_rms") == LL_VIN
        rows6.append([
            Paragraph(str(row.get("Vin_rms","")),            S['tbl_cell']),
            Paragraph(str(row.get("Pout_W","")),             S['tbl_cell']),
            Paragraph("—",                                   S['tbl_cell']),
            Paragraph(f"{row.get('I_dc_A',0):.3f}",         S['tbl_cell']),
            Paragraph(f"{row.get('I_LF_A',0):.3f}",         S['tbl_cell']),
            Paragraph(f"{row.get('I_HF_A',0):.3f}",         S['tbl_cell']),
            Paragraph(f"<b>{row.get('I_cap_total_A',0):.3f}</b>", S['tbl_cell']),
        ])
        if is_wc:
            ts6_extra += [('BACKGROUND',(0,ri),(-1,ri),colors.HexColor("#1E2E4A")),
                          ('TEXTCOLOR',(0,ri),(-1,ri),colors.HexColor("#93C5FD"))]
        elif is_ll:
            ts6_extra += [('BACKGROUND',(0,ri),(-1,ri),colors.HexColor("#0A2A20")),
                          ('TEXTCOLOR',(0,ri),(-1,ri),colors.HexColor("#6EE7B7"))]
    cw6 = [18*mm,18*mm,12*mm,20*mm,20*mm,20*mm,22*mm]
    t6  = Table(rows6, colWidths=cw6)
    ts6 = TableStyle([
        ('BACKGROUND',(0,0),(-1,0),NAVY),('TEXTCOLOR',(0,0),(-1,0),WHITE),
        ('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),('FONTSIZE',(0,0),(-1,-1),8.5),
        ('ALIGN',(0,0),(-1,-1),'CENTER'),('FONTNAME',(0,1),(-1,-1),'Helvetica'),
        ('ROWBACKGROUNDS',(0,1),(-1,-1),[WHITE,STRIPE]),
        ('GRID',(0,0),(-1,-1),0.3,RULE),('VALIGN',(0,0),(-1,-1),'MIDDLE'),
        ('TOPPADDING',(0,0),(-1,-1),3),('BOTTOMPADDING',(0,0),(-1,-1),3),
        ('LEFTPADDING',(0,0),(-1,-1),5),('RIGHTPADDING',(0,0),(-1,-1),5),
    ] + ts6_extra)
    t6.setStyle(ts6)
    story.append(t6)
    story.append(Paragraph(
        'Blue row = worst-case (180 Vac) &nbsp;|&nbsp; Green row = low-line (90 Vac)', S['note']))
    story.append(Spacer(1, 5*mm))

    # ── 15.6b Ripple voltage verification ────────────────────────────────────
    if ver:
        story.append(Paragraph('Step 15.7) Ripple Voltage with Selected Bank', S['h2']))
        story.append(Paragraph(
            'V<sub>ripple,pp</sub> = P<sub>out</sub> / '
            '(2&pi; &middot; f<sub>line</sub> &middot; C<sub>bank</sub> &middot; &eta; &middot; V<sub>out</sub>)',
            S['eq']))
        story.append(Spacer(1, 2*mm))
        C_bank_F = float(ver.get('C_total_uF',0)) * 1e-6
        wc_v = ver.get('worst_case',{}); ll_v = ver.get('low_line',{})
        for label, v_rip, pout_v, eta_v in [
            ('Worst-case (180 Vac)', wc_v.get('V_ripple_pp_V',0), wc.get('Pout',3600), wc.get('eta',0.965)),
            ('Low-line (90 Vac)',    ll_v.get('V_ripple_pp_V',0), ll.get('Pout',1700), ll.get('eta',0.945)),
        ]:
            spec_v = float(inp.get('Vdc_ripple_V',20))
            ok_v   = v_rip <= spec_v
            story.append(Paragraph(
                f"<b>{label}:</b>  V<sub>ripple,pp</sub> = "
                f"{pout_v:.0f} / (2&pi;&middot;{f_line:.0f}&middot;{C_bank_F*1e6:.0f}e-6&middot;{eta_v}&middot;{Vout:.0f}) = "
                f"<b>{v_rip:.2f} V pk-pk</b>  "
                f"(spec {spec_v:.0f} V &rarr; {'<b>PASS</b>' if ok_v else '<b>FAIL</b>'})",
                S['eq']))
        story.append(Spacer(1, 4*mm))

        # ── 15.8 Sizing summary ───────────────────────────────────────────────
        story.append(Paragraph('Step 15.8) Sizing Summary', S['h2']))
        margin_pct = float(ver.get('margin_pct',0))
        esr_par    = ver.get('ESR_parallel_mohm','—')
        I_rated    = ver.get('I_rated_per_cap_A','—')
        rip_ok_s   = ver.get('ripple_current_pass', True)
        cap_specs  = ver.get('cap_specs',[])
        pn         = cap_specs[0].get('part_number','—') if cap_specs else '—'
        qty_s      = ver.get('total_cap_count',1)
        hdr_sum = ['Parameter', 'Worst-case', 'Low-line']
        rows_sum = [[Paragraph(h, S['tbl_hdr']) for h in hdr_sum]]
        for (k, fw, fl) in [
            ('C<sub>holdup</sub> (&micro;F)',         f"{wc.get('C_holdup_uF','—')}",   f"{ll.get('C_holdup_uF','—')}"),
            ('C<sub>ripple</sub> (&micro;F)',         f"{wc.get('C_ripple_uF','—')}",   f"{ll.get('C_ripple_uF','—')}"),
            ('C<sub>required</sub> = max above (&micro;F)', f"{C_req_uF:.1f}", '—'),
            (f'Selected bank ({qty_s}&times;{pn})',  f"{ver.get('C_total_uF','—')} &micro;F", '—'),
            ('Margin over C<sub>req</sub>',           f"+{margin_pct:.1f}%",             '—'),
            ('ESR<sub>parallel</sub> (m&Omega;)',     f"{esr_par}",                      '—'),
            ('I<sub>rms</sub> per cap (A)',           f"{wc_v.get('I_rms_per_cap_A','—')}", f"{ll_v.get('I_rms_per_cap_A','—')}"),
            ('I<sub>rated</sub> per cap (A)',         f"{I_rated}",                      '—'),
            ('V<sub>ripple,pp</sub> (V)',             f"{wc_v.get('V_ripple_pp_V','—')}", f"{ll_v.get('V_ripple_pp_V','—')}"),
            ('Ripple current',  'PASS' if rip_ok_s else 'FAIL',  '—'),
        ]:
            rows_sum.append([Paragraph(k, S['tbl_cell_l']),
                             Paragraph(fw, S['tbl_cell']),
                             Paragraph(fl, S['tbl_cell'])])
        story.append(_tbl(rows_sum, [80*mm, 45*mm, 45*mm]))
        story.append(Spacer(1, 4*mm))

    # ── 15.7 Selected capacitor specification table ───────────────────────────
    cap_specs = ver.get("cap_specs", [])
    if cap_specs:
        story.append(Paragraph('Step 15.7) Selected Capacitor Specifications', S['h2']))
        hdr7 = ['Part / Value', 'Qty', 'Voltage\n(V)', 'ESR each\n(m&Omega;)',
                'I<sub>rated</sub>\n(A)', 'Temp\n(&deg;C)']
        rows7 = [[Paragraph(h, S['tbl_hdr']) for h in hdr7]]
        for cs in cap_specs:
            pn   = cs.get("part_number","") or f"{cs['value_uF']} µF"
            rows7.append([
                Paragraph(f"{pn}<br/>{cs['value_uF']} &micro;F", S['tbl_cell_l']),
                Paragraph(str(cs['qty']),                         S['tbl_cell']),
                Paragraph(str(cs['voltage_rating_V']),            S['tbl_cell']),
                Paragraph(f"{cs['ESR_each_mohm']}"  if cs.get('ESR_each_mohm')  else '—', S['tbl_cell']),
                Paragraph(f"{cs['I_rated_A']}"      if cs.get('I_rated_A')      else '—', S['tbl_cell']),
                Paragraph(str(cs['temp_rating_C']), S['tbl_cell']),
            ])
        story.append(_tbl(rows7, [48*mm,14*mm,18*mm,24*mm,24*mm,18*mm], hdr_bg=BLUE))
        story.append(Spacer(1, 3*mm))
        # Summary line
        story.append(Paragraph(
            f"Supplier: {ver.get('supplier','')} &nbsp;|&nbsp; Series: {ver.get('series','')} &nbsp;|&nbsp; "
            f"C<sub>total</sub> = {ver.get('C_total_uF','—')} &micro;F &nbsp;|&nbsp; "
            f"ESR<sub>par</sub> = {ver.get('ESR_parallel_mohm','—')} m&Omega; &nbsp;|&nbsp; "
            f"I<sub>rated/cap</sub> = {ver.get('I_rated_per_cap_A','—')} A", S['note']))
        story.append(Spacer(1, 4*mm))

    # ── 15.8 Verified performance: V_ripple + hold-up + ESR spike ────────────
    if ver:
        story.append(Paragraph('Step 15.8) Verified Performance', S['h2']))
        wc_v = ver.get("worst_case", {})
        ll_v = ver.get("low_line",   {})
        rip_ok = ver.get("ripple_current_pass", True)
        hdr8 = ['Metric', 'Worst-case (180 Vac)', 'Low-line (90 Vac)']
        rows8 = [[Paragraph(h, S['tbl_hdr']) for h in hdr8]]
        for (k, fw, fl) in [
            ('C<sub>total</sub> (&micro;F)',           f"{ver.get('C_total_uF','')}",         "—"),
            ('Margin over C<sub>req</sub>',            f"{ver.get('margin_pct','')}%",         "—"),
            ('ESR<sub>parallel</sub> (m&Omega;)',      f"{ver.get('ESR_parallel_mohm','—')}",  "—"),
            ('V<sub>ripple,pp</sub> (V)',              f"{wc_v.get('V_ripple_pp_V','')}",      f"{ll_v.get('V_ripple_pp_V','')}"),
            ('t<sub>holdup</sub> (ms)',                f"{wc_v.get('t_holdup_ms','')}",        f"{ll_v.get('t_holdup_ms','')}"),
            ('I<sub>rms</sub> per cap (A)',            f"{wc_v.get('I_rms_per_cap_A','')}",   f"{ll_v.get('I_rms_per_cap_A','')}"),
            ('I<sub>rated</sub> per cap (A)',          f"{wc_v.get('I_rated_per_cap_A','—')}", f"{ll_v.get('I_rated_per_cap_A','—')}"),
            ('Ripple current check',
             'PASS' if wc_v.get('ripple_current_pass', True) else 'FAIL',
             'PASS' if ll_v.get('ripple_current_pass', True) else 'FAIL'),
            ('V<sub>ESR,pk</sub> (V)',                 str(wc_v.get('V_esr_pk_V','—')),       str(ll_v.get('V_esr_pk_V','—'))),
        ]:
            rows8.append([Paragraph(k, S['tbl_cell_l']),
                          Paragraph(fw, S['tbl_cell']),
                          Paragraph(fl, S['tbl_cell'])])
        rip_color = GREEN if rip_ok else RED
        t8 = Table(rows8, colWidths=[80*mm, 45*mm, 45*mm])
        t8.setStyle(TableStyle([
            ('BACKGROUND',(0,0),(-1,0),NAVY),('TEXTCOLOR',(0,0),(-1,0),WHITE),
            ('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),('FONTSIZE',(0,0),(-1,-1),8.5),
            ('ALIGN',(0,0),(-1,-1),'CENTER'),('FONTNAME',(0,1),(-1,-1),'Helvetica'),
            ('ALIGN',(0,1),(0,-1),'LEFT'),
            ('ROWBACKGROUNDS',(0,1),(-1,-1),[WHITE,STRIPE]),
            ('GRID',(0,0),(-1,-1),0.3,RULE),('VALIGN',(0,0),(-1,-1),'MIDDLE'),
            ('TOPPADDING',(0,0),(-1,-1),3),('BOTTOMPADDING',(0,0),(-1,-1),3),
            ('LEFTPADDING',(0,0),(-1,-1),5),('RIGHTPADDING',(0,0),(-1,-1),5),
            ('TEXTCOLOR',(1,8),(2,8), rip_color),
            ('FONTNAME', (1,8),(2,8),'Helvetica-Bold'),
        ]))
        story.append(t8)
        story.append(Spacer(1, 4*mm))

    # ── 15.9 Power dissipation + temperature rise — all 9 operating points ──
    if th and th.get("thermal_table"):
        story.append(PageBreak())
        story.append(Paragraph('Step 15.9) Power Dissipation & Temperature Rise — All 9 Operating Points',
                               S['h2']))
        temp_rating = th.get("temp_rating_C", 85)
        _tamb9 = th.get("T_amb_C", 50)
        story.append(Paragraph(
            f'Temp rating: {temp_rating}&deg;C &nbsp;|&nbsp; '
            f'R<sub>th,ca</sub> = {th.get("Rth_ca_CW","—")} &deg;C/W &nbsp;|&nbsp; '
            f'T<sub>amb</sub> = {_tamb9}&deg;C &nbsp;|&nbsp; '
            f'I per cap = I<sub>total</sub> / X  (X = number of caps)',
            S['note']))
        # vendor-implied ESR(T) model — the resistance basis of P_diss / ΔT / T_cap below
        _em = th.get("esr_model") or {}
        if _em:
            story.append(Spacer(1, 1.5*mm))
            story.append(Paragraph(
                'ESR model (vendor-implied, temperature-corrected): the datasheet tan-&delta; ESR is a '
                'MAX at 20&deg;C/120 Hz, while the electrolyte resistance is strongly NTC. ESR is '
                'interpolated exponentially in CORE temperature between two anchors from the part\'s own '
                f'datasheet row — <b>{_em.get("esr20_mohm","—")} m&Omega; @20&deg;C</b> (tan-&delta; max) and '
                f'<b>{_em.get("esr_hot_mohm","—")} m&Omega; @{_em.get("T_hot_C","—"):.0f}&deg;C</b> '
                '(= &Delta;T<sub>0</sub>/(I<sub>rated</sub>&sup2;&middot;R<sub>th</sub>), the resistance the '
                'vendor\'s own rated-ripple thermal design implies) — and the core temperature is solved '
                'self-consistently (T<sub>core</sub> = T<sub>amb</sub> + P&middot;R<sub>th</sub>). The '
                'allowed ripple uses the temperature multiplier '
                f'K(T<sub>amb</sub>) = {_em.get("K_temp","—")} ({_em.get("K_source","—")}) &times; the '
                f'{_em.get("I_rated_A","—")} A datasheet rating. HF ESR uses the datasheet frequency '
                f'coefficient k<sub>f</sub> = {_em.get("kf","—")}. Source: {_em.get("source","—")}.',
                S['note']))
        story.append(Spacer(1, 2*mm))

        hdr9 = ['V<sub>in</sub>\n(Vac)', 'P<sub>out</sub>\n(W)',
                'I<sub>total</sub>\n(A)', 'I/cap\n(A)', 'I<sub>allow</sub>\n(A)',
                'ESR<sub>LF</sub>@T\n(m&Omega;)',
                'P<sub>diss</sub>\n(W)', '&Delta;T\n(&deg;C)',
                'T<sub>cap</sub>\n(&deg;C)', 'V<sub>rip,pp</sub>\n(V)', 'Ripple\nPass']
        rows9 = [[Paragraph(h, S['tbl_hdr']) for h in hdr9]]
        ts_extra = []
        for i, row in enumerate(th["thermal_table"]):
            T_cap = row["T_cap_C"]
            t_col = (colors.HexColor("#2E7D4F") if T_cap < temp_rating - 20
                     else colors.HexColor("#D4820A") if T_cap < temp_rating - 5
                     else colors.HexColor("#C0392B"))
            ok    = row["ripple_pass"]
            p_col = colors.HexColor("#2E7D4F") if ok else colors.HexColor("#C0392B")
            ri    = i + 1
            rows9.append([
                Paragraph(str(row["Vin_rms"]),                          S['tbl_cell']),
                Paragraph(str(row["Pout_W"]),                            S['tbl_cell']),
                Paragraph(f"{row['I_cap_total_A']:.3f}",                S['tbl_cell']),
                Paragraph(f"{row['I_cap_per_unit_A']:.3f}",             S['tbl_cell']),
                Paragraph(f"{row.get('I_rated_A',0):.2f}",              S['tbl_cell']),
                Paragraph(f"{row.get('ESR_lf_mohm','—')}",              S['tbl_cell']),
                Paragraph(f"{row['P_dissipated_W']:.3f}",               S['tbl_cell']),
                Paragraph(f"{row['dT_rise_C']:.1f}",                    S['tbl_cell']),
                Paragraph(f"{row['T_cap_C']:.1f}",                      S['tbl_cell']),
                Paragraph(f"{row['V_ripple_pp_V']:.2f}",                S['tbl_cell']),
                Paragraph('PASS' if ok else 'FAIL',                     S['tbl_cell']),
            ])
            ts_extra += [
                ('TEXTCOLOR', (8,ri),(8,ri), t_col),
                ('TEXTCOLOR', (10,ri),(10,ri), p_col),
                ('FONTNAME',  (10,ri),(10,ri), 'Helvetica-Bold'),
            ]

        cw9 = [13*mm,13*mm,15*mm,13*mm,14*mm,15*mm,14*mm,12*mm,14*mm,15*mm,13*mm]
        t9  = Table(rows9, colWidths=cw9)
        t9.setStyle(TableStyle([
            ('BACKGROUND',(0,0),(-1,0),NAVY),('TEXTCOLOR',(0,0),(-1,0),WHITE),
            ('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),('FONTSIZE',(0,0),(-1,-1),7.5),
            ('ALIGN',(0,0),(-1,-1),'CENTER'),('FONTNAME',(0,1),(-1,-1),'Helvetica'),
            ('ROWBACKGROUNDS',(0,1),(-1,-1),[WHITE,STRIPE]),
            ('GRID',(0,0),(-1,-1),0.3,RULE),('VALIGN',(0,0),(-1,-1),'MIDDLE'),
            ('TOPPADDING',(0,0),(-1,-1),2),('BOTTOMPADDING',(0,0),(-1,-1),2),
            ('LEFTPADDING',(0,0),(-1,-1),3),('RIGHTPADDING',(0,0),(-1,-1),3),
        ] + ts_extra))
        story.append(t9)
        story.append(Spacer(1, 3*mm))
        worst_T = th.get("worst_case_T_C","—")
        all_ok  = th.get("all_ripple_pass", False)
        _n_der9 = sum(1 for r in th["thermal_table"] if r.get("ripple_status") == "pass_derated")
        story.append(Paragraph(
            f'Worst-case T<sub>cap</sub> = <b>{worst_T}&deg;C</b> '
            f'(rating {temp_rating}&deg;C) &nbsp;|&nbsp; '
            f'Ripple current: {"PASS" if all_ok else "FAIL — reduce I/cap by adding more capacitors"}'
            + (f' &nbsp;({_n_der9} point(s) PASS-derated: above the nameplate rating but within the '
               f'temperature allowance, core within rating, Life Time Period met)' if _n_der9 else ''),
            S['note']))
        story.append(Spacer(1, 4*mm))

        # ── 15.9b Temperature characterization of the selected capacitor ─────────
        try:
            from app.mode_b.step15_cap_db import _load as _csvload, characterize_temperature_sweep
            _cfg9 = result.get("configuration") or []
            _pn9  = next((str(r.get("part_number") or "") for r in _cfg9 if r.get("part_number")), "")
            _rec9 = next((x for x in _csvload()
                          if str(x.get("part_number", "")).lower() == _pn9.lower()), None) if _pn9 else None
        except Exception:
            _rec9 = None
        if _rec9 is not None:
            _qty9 = sum(int(r.get("qty") or 0) for r in _cfg9) or 1
            _wc9  = result.get("worst_case", {})
            _sw9  = characterize_temperature_sweep(
                _rec9, _qty9, float(_wc9.get("I_LF_A", 0) or 0), float(_wc9.get("I_HF_A", 0) or 0),
                float(result.get("inputs", {}).get("Vout_V", 393) or 393), T_op=_tamb9)
            story.append(Paragraph('Step 15.9b) Temperature Characterization of the Selected Capacitor', S['h2']))
            story.append(Paragraph(
                f'Each figure at its own declared temperature basis; required ripple per capacitor '
                f'= {_sw9["I_req_per_cap_A"]} A (a demand, ambient-independent). Validation: at the '
                f'rated row I<sub>allow</sub> reduces exactly to the nameplate rating; at 20&deg;C the '
                f'no-load ESR reproduces the datasheet tan-&delta; value.', S['body']))
            hdrS = ['T<sub>amb</sub>', 'ESR@T<sub>amb</sub>', 'ESR@T<sub>core</sub>',
                    'T<sub>core</sub>', 'I<sub>allow</sub> (K)', 'Life Time Period']
            rowsS = [[Paragraph(h, S['tbl_hdr']) for h in hdrS]]
            for r in _sw9["rows"]:
                mark = ' (op)' if r['is_operating'] else (' (rated)' if r['is_rated'] else '')
                rowsS.append([
                    Paragraph(f"{r['T_amb_C']:.0f}&deg;C{mark}", S['tbl_cell']),
                    Paragraph(f"{r['esr_at_amb_mohm']:.0f} m&Omega;", S['tbl_cell']),
                    Paragraph(f"{r['esr_at_core_mohm']:.0f} m&Omega;", S['tbl_cell']),
                    Paragraph(f"{r['T_core_C']:.1f}&deg;C", S['tbl_cell']),
                    Paragraph((f"{r['I_allow_A']:.2f} A (K={r['K']}{'*' if r['K_clamped'] else ''})"
                               if r['I_allow_A'] is not None else '—'), S['tbl_cell']),
                    Paragraph(f"{'&gt;200' if r['life_years'] >= 200 else r['life_years']} yr", S['tbl_cell']),
                ])
            tS = Table(rowsS, colWidths=[26*mm, 26*mm, 26*mm, 24*mm, 40*mm, 28*mm])
            tS.setStyle(TableStyle([
                ('BACKGROUND',(0,0),(-1,0),NAVY),('TEXTCOLOR',(0,0),(-1,0),WHITE),
                ('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),('FONTSIZE',(0,0),(-1,-1),8),
                ('ALIGN',(0,0),(-1,-1),'CENTER'),('FONTNAME',(0,1),(-1,-1),'Helvetica'),
                ('ROWBACKGROUNDS',(0,1),(-1,-1),[WHITE,STRIPE]),
                ('GRID',(0,0),(-1,-1),0.3,RULE),('VALIGN',(0,0),(-1,-1),'MIDDLE'),
                ('TOPPADDING',(0,0),(-1,-1),2),('BOTTOMPADDING',(0,0),(-1,-1),2),
            ]))
            story.append(tS)
            story.append(Spacer(1, 2*mm))
            story.append(Paragraph(
                '<b>Why I<sub>allow</sub> is clamped (K* &le; 2.5) at low ambient:</b> the pure thermal '
                'capability keeps growing as the ambient falls (K<sub>raw</sub> &asymp; 4&times; at '
                '0&ndash;25&deg;C), but the credited allowance is clamped because (1) published vendor '
                'temperature-multiplier tables top out at &asymp;2.0&ndash;2.5 &mdash; manufacturers do '
                'not warrant unlimited ripple in a cold enclosure (terminal/tab ampacity, internal '
                'joints and the characterized envelope take over as limits); (2) the un-clamped figure '
                'describes operation with the core AT its temperature limit, where the Life Time Period '
                'would collapse to the bare endurance rating L<sub>0</sub>; (3) a series’ published '
                'multiplier table, when entered in the vendor registry, takes precedence over both the '
                'model and the clamp. Below 20&deg;C the ESR is held at the 20&deg;C datasheet value '
                '(no cold-side anchor).', S['note']))
            story.append(Spacer(1, 4*mm))

    # ── 15.10 Summary ─────────────────────────────────────────────────────────
    if ver:
        story.append(Paragraph('Step 15.10) Summary', S['h2']))
        wc_v = ver.get("worst_case", {})
        ll_v = ver.get("low_line",   {})
        rows10 = [[Paragraph(h, S['tbl_hdr']) for h in
                   ['Parameter','Worst-case (180 Vac)','Low-line (90 Vac)']]]
        for (k, fw, fl) in [
            ('C<sub>required</sub> (&micro;F)',       f"{result.get('C_required_uF','—')}",      "—"),
            ('C<sub>total</sub> selected (&micro;F)', f"{ver.get('C_total_uF','—')}",            "—"),
            ('Margin (%)',                             f"{ver.get('margin_pct','—')}%",            "—"),
            ('Voltage rating (V)',                     f"{result.get('V_rating_selected_V','—')}", "—"),
            ('ESR<sub>parallel</sub> (m&Omega;)',     f"{ver.get('ESR_parallel_mohm','—')}",      "—"),
            ('V<sub>out</sub> ripple pk-pk (V)',      f"{wc_v.get('V_ripple_pp_V','—')}",        f"{ll_v.get('V_ripple_pp_V','—')}"),
            ('Hold-up time (ms)',                      f"{wc_v.get('t_holdup_ms','—')}",          f"{ll_v.get('t_holdup_ms','—')}"),
            ('I<sub>rms,total</sub> (A)',              f"{wc_v.get('I_rms_total_A','—')}",        f"{ll_v.get('I_rms_total_A','—')}"),
            ('I<sub>rms</sub> per cap (A)',            f"{wc_v.get('I_rms_per_cap_A','—')}",     f"{ll_v.get('I_rms_per_cap_A','—')}"),
            ('I<sub>rated</sub> per cap (A)',          f"{ver.get('I_rated_per_cap_A','—')}",     f"{ver.get('I_rated_per_cap_A','—')}"),
            ('Ripple current check',
             'PASS' if wc_v.get('ripple_current_pass',True) else 'FAIL',
             'PASS' if ll_v.get('ripple_current_pass',True) else 'FAIL'),
        ]:
            rows10.append([Paragraph(k, S['tbl_cell_l']),
                           Paragraph(fw, S['tbl_cell']),
                           Paragraph(fl, S['tbl_cell'])])
        story.append(_tbl(rows10, [80*mm, 45*mm, 45*mm]))
        story.append(Spacer(1, 6*mm))

    # ── 15.9–15.11 Life Time Period (manufacturer lifetime model) ─────────────
    # Designer decision 2026-07-14: the manufacturer's own published lifetime model is the SOLE
    # lifetime criterion ("Life Time Period"). The former Methods 1/2 (max-tan-δ ESR Arrhenius
    # screens) remain internal bounds only and are no longer documented.
    lt = result.get("lifetime")
    if lt:
        story.append(PageBreak())
        _h1_band('Step 15.9–15.11) Capacitor Life Time Period', story, S)
        Tamb_rpt = lt.get('Tamb_C', 50)
        Vout_rpt = lt.get('Vout_V', 393)
        m3 = lt.get('method3', {})
        story.append(Paragraph(
            'Aluminium-electrolytic lifetime is governed by electrolyte evaporation — an '
            'Arrhenius process whose rate doubles every 10&deg;C. The <b>Life Time Period</b> is '
            'evaluated with the manufacturer\'s own published lifetime model — the same basis on '
            'which the endurance rating L<sub>o</sub> and the ripple/temperature multipliers are '
            'specified: L = L<sub>o</sub>&middot;f(T)&middot;f(I)&middot;f(V), where f(T) is the '
            'ambient-based 10-K rule, f(I) credits the rated-ripple self-heating &Delta;T<sub>o</sub> '
            'built into L<sub>o</sub>, and f(V) is the (capped) voltage-derating factor. '
            'Pass threshold: &ge; 15 years. Values beyond ~15 years should be read as '
            '"&ge; 15 yr with margin" — seal and electrolyte aging dominate beyond that horizon '
            'and manufacturers do not extrapolate further.',
            S['body']))
        story.append(Spacer(1, 3*mm))

        # Step 15.9 — inputs table
        story.append(Paragraph('Step 15.9) Lifetime Inputs and Operating Conditions', S['h2']))
        cap_s = ver.get('cap_specs',[]) if ver else []
        cs0   = cap_s[0] if cap_s else {}
        life_s = cs0.get('lifetime','—')
        temp_s = cs0.get('temp_rating_C','—')
        qty_lt = lt.get('qty',1)
        I_lf   = lt.get('I_LF_per_cap_A','—')
        I_hf   = lt.get('I_HF_per_cap_A','—')
        story.append(_kv_tbl([
            ('L<sub>o</sub> — datasheet base life',         life_s),
            ('T<sub>max</sub> — max category temperature',  f"{temp_s}&deg;C"),
            ('T<sub>amb</sub> — capacitor ambient',         f"{Tamb_rpt}&deg;C"),
            ('V<sub>out</sub> — operating bus voltage',     f"{Vout_rpt:.1f} Vdc"),
            ('V<sub>rated</sub> — cap voltage rating',      f"{ver.get('voltage_rating','450') if ver else '450'} V"),
            ('N — caps in parallel bank',                   str(qty_lt)),
            ('I<sub>LF,cap</sub> — low-freq ripple per cap', f"{I_lf} A"),
            ('I<sub>HF,cap</sub> — high-freq ripple per cap', f"{I_hf} A"),
            ('I<sub>o</sub> — rated ripple (LF reference)', f"{ver.get('I_rated_per_cap_A','—') if ver else '—'} A"),
        ], S))
        story.append(Spacer(1, 4*mm))

        # Step 15.10 — the worked model
        story.append(Paragraph('Step 15.10) Life Time Period — Manufacturer Model', S['h2']))
        story.append(Paragraph(
            'L = L<sub>o</sub>&middot;f(T)&middot;f(I)&middot;f(V). Ripple is converted to the rated '
            'frequency basis (I<sub>eq</sub>); the self-heating rise &Delta;T<sub>j</sub> is compared '
            'against the datasheet rated-ripple rise &Delta;T<sub>o</sub> inside f(I), so operating at '
            'the rated ripple costs no life relative to the endurance test condition.',
            S['body']))
        story.append(Spacer(1, 2*mm))
        params = [
            ('I<sub>eq</sub> (ripple at rated freq.)', f"{m3.get('I_eq_A','—')} A"),
            ('&Delta;T<sub>j</sub> (core rise)',       f"{m3.get('dTj_C','—')} &deg;C"),
            ('T<sub>core</sub>',                       f"{m3.get('T_core_C','—')} &deg;C"),
            ('f(T) — temperature factor',              f"{m3.get('f_T','—')}&times;"),
            ('f(I) — ripple factor',                   f"{m3.get('f_I','—')}&times;"),
            ('f(V) — voltage factor',                  f"{m3.get('f_V','—')}&times;"),
            ('Life Time Period', f"<b>{m3.get('life_years_uncapped', m3.get('life_years','—'))} yr</b>"),
        ]
        data = [[Paragraph(k, S['body']), Paragraph(str(v), S['eq'])] for k, v in params]
        t = Table(data, colWidths=[85*mm, 85*mm])
        t.setStyle(TableStyle([
            ('ROWBACKGROUNDS', (0,0), (-1,-1), [WHITE, STRIPE]),
            ('GRID', (0,0), (-1,-1), 0.3, RULE),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('TOPPADDING', (0,0), (-1,-1), 3),
            ('BOTTOMPADDING', (0,0), (-1,-1), 3),
            ('LEFTPADDING', (0,0), (-1,-1), 6),
        ]))
        story.append(t)
        story.append(Spacer(1, 3*mm))

        # Step 15.11 — result banner
        min_yr_v = lt.get('min_life_years', 0)
        pass_v   = lt.get('pass_15yr', False)
        story.append(Paragraph(
            f"<b>Life Time Period = {min_yr_v} yr — "
            f"{'PASS' if pass_v else 'FAIL'} &ge; 15-year target.</b> "
            f"T<sub>amb</sub> = {Tamb_rpt}&deg;C, V<sub>out</sub> = {Vout_rpt:.0f} V.",
            S['note']))
        story.append(Spacer(1, 6*mm))

    return story
