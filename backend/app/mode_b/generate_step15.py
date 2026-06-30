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
        'I<sub>dc</sub> = P<sub>out</sub> / (&eta; &middot; V<sub>out</sub>) &nbsp;&nbsp;'
        'I<sub>LF</sub> = I<sub>dc</sub> / &radic;2 &nbsp;&nbsp;'
        'I<sub>HF</sub> = &radic;(I<sub>dc</sub><super>2</super> &middot; 16V<sub>out</sub> / '
        '(6V<sub>in,pk</sub> &middot; 2&pi;) &minus; I<sub>LF</sub><super>2</super>) &nbsp;&nbsp;'
        'I<sub>total</sub> = &radic;(I<sub>LF</sub><super>2</super> + I<sub>HF</sub><super>2</super>)',
        S['body']))
    story.append(Spacer(1, 2*mm))

    th_tbl = th.get("thermal_table", [])
    hdr6 = ['V<sub>in</sub>\n(Vac)', 'P<sub>out</sub>\n(W)', '&eta;',
            'I<sub>dc</sub>\n(A)', 'I<sub>LF</sub>\n(A)',
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
        story.append(Paragraph(
            f'Temp rating: {temp_rating}&deg;C &nbsp;|&nbsp; '
            f'R<sub>th,ca</sub> = {th.get("Rth_ca_CW","—")} &deg;C/W &nbsp;|&nbsp; '
            f'T<sub>amb</sub> = 50&deg;C &nbsp;|&nbsp; '
            f'I per cap = I<sub>total</sub> / X  (X = number of caps)',
            S['note']))
        story.append(Spacer(1, 2*mm))

        hdr9 = ['V<sub>in</sub>\n(Vac)', 'P<sub>out</sub>\n(W)',
                'I<sub>total</sub>\n(A)', 'I/cap\n(A)', 'I<sub>rated</sub>\n(A)',
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
                Paragraph(f"{row['P_dissipated_W']:.3f}",               S['tbl_cell']),
                Paragraph(f"{row['dT_rise_C']:.1f}",                    S['tbl_cell']),
                Paragraph(f"{row['T_cap_C']:.1f}",                      S['tbl_cell']),
                Paragraph(f"{row['V_ripple_pp_V']:.2f}",                S['tbl_cell']),
                Paragraph('PASS' if ok else 'FAIL',                     S['tbl_cell']),
            ])
            ts_extra += [
                ('TEXTCOLOR', (7,ri),(7,ri), t_col),
                ('TEXTCOLOR', (9,ri),(9,ri), p_col),
                ('FONTNAME',  (9,ri),(9,ri), 'Helvetica-Bold'),
            ]

        cw9 = [14*mm,14*mm,16*mm,14*mm,16*mm,16*mm,13*mm,15*mm,16*mm,14*mm]
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
        story.append(Paragraph(
            f'Worst-case T<sub>cap</sub> = <b>{worst_T}&deg;C</b> '
            f'(rating {temp_rating}&deg;C) &nbsp;|&nbsp; '
            f'Ripple current: {"PASS" if all_ok else "FAIL — reduce I/cap by adding more capacitors"}',
            S['note']))
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

    # ── 15.11–15.16 Lifetime calculation (three methods) ─────────────────────
    lt = result.get("lifetime")
    if lt:
        story.append(PageBreak())
        _h1_band('Step 15.9–15.16) Capacitor Lifetime Analysis', story, S)
        Tamb_rpt = lt.get('Tamb_C', 45)
        Vout_rpt = lt.get('Vout_V', 393)
        story.append(Paragraph(
            'Aluminium-electrolytic lifetime is governed by electrolyte evaporation — an '
            'Arrhenius process whose rate doubles every 10&deg;C (Arrhenius rule). '
            'Three independent methods are evaluated; the <b>minimum</b> result is the governing '
            'conservative estimate. Pass threshold: &ge; 15 years.',
            S['body']))
        story.append(Spacer(1, 3*mm))

        # Step 15.9 — inputs table
        story.append(Paragraph('Step 15.9) Lifetime Inputs and Operating Conditions', S['h2']))
        m1 = lt.get('method1',{}); m3 = lt.get('method3',{})
        cap_s = ver.get('cap_specs',[]) if ver else []
        Lo_h  = result.get('inputs',{})
        # Get Lo and Tmax from first cap spec
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
            ('ESR<sub>LF</sub> from datasheet',             f"{m1.get('esr_lf_ohm','—')} &Omega;"),
            ('ESR<sub>HF</sub> from datasheet (0.595&times;ESR<sub>LF</sub>)', f"{m1.get('esr_hf_ohm','—')} &Omega;"),
            ('R<sub>th</sub> — thermal resistance cap-to-air', '10 &deg;C/W (snap-in)'),
            ('I<sub>o</sub> — rated ripple (LF reference)', f"{ver.get('I_rated_per_cap_A','—') if ver else '—'} A"),
        ], S))
        story.append(Spacer(1, 5*mm))
        story.append(Spacer(1, 4*mm))

        # Per-method detail
        for m_key, step_label, desc in [
            ('method1', 'Step 15.12 — Method 1: Arrhenius from Datasheet ESR',
             'Self-heating computed from the manufacturer-published 100 Hz ESR and HF impedance. '
             'Core temperature T<sub>core</sub> = T<sub>amb</sub> + I<sup>2</sup>&middot;ESR&middot;R<sub>th</sub>. '
             'Voltage derating (V<sub>o</sub>/V)<sup>3</sup> applied.'),
            ('method2', 'Step 15.13 — Method 2: Arrhenius from tan-δ ESR (conservative)',
             'ESR derived from dissipation factor: ESR<sub>LF</sub> = tan-&delta; / (2&pi;&middot;120&middot;C). '
             'Uses worst-case tan-&delta; — conservative bound for parts without a published ESR.'),
            ('method3', 'Step 15.14–15.15 — Method 3: Manufacturer Model',
             'Full model: L = L<sub>o</sub>&middot;f(T)&middot;f(I)&middot;f(V). '
             'Ripple converted to rated frequency; self-heating anchored to datasheet &Delta;T<sub>o</sub>.'),
        ]:
            m = lt.get(m_key, {})
            if not m: continue
            story.append(Paragraph(step_label, S['h2']))
            story.append(Paragraph(desc, S['body']))
            story.append(Spacer(1, 2*mm))

            if m_key == 'method3':
                params = [
                    ('I<sub>eq</sub> (ripple at rated freq.)', f"{m.get('I_eq_A','—')} A"),
                    ('&Delta;T<sub>j</sub> (core rise)',       f"{m.get('dTj_C','—')} &deg;C"),
                    ('T<sub>core</sub>',                       f"{m.get('T_core_C','—')} &deg;C"),
                    ('f(T) — temperature factor',              f"{m.get('f_T','—')}&times;"),
                    ('f(I) — ripple factor',                   f"{m.get('f_I','—')}&times;"),
                    ('f(V) — voltage factor',                  f"{m.get('f_V','—')}&times;"),
                ]
            else:
                params = [
                    ('ESR<sub>LF</sub> used',       f"{m.get('esr_lf_ohm','—')} &Omega;"),
                    ('ESR<sub>HF</sub> used',       f"{m.get('esr_hf_ohm','—')} &Omega;"),
                    ('P self-heating per cap',      f"{m.get('P_W','—')} W"),
                    ('&Delta;T<sub>core</sub>',     f"{m.get('dT_C','—')} &deg;C"),
                    ('T<sub>core</sub>',            f"{m.get('T_core_C','—')} &deg;C"),
                    ('Temperature factor',          f"{m.get('temp_factor','—')}&times;"),
                    ('Voltage factor (V<sub>o</sub>/V)<sup>3</sup>', f"{m.get('volt_factor','—')}&times;"),
                ]

            life_yr = m.get('life_years_uncapped', m.get('life_years','—'))
            params.append(('Calculated life', f"<b>{life_yr} yr</b>"))
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
            story.append(Spacer(1, 4*mm))

        # Three-method comparison table (matches document Table 7)
        story.append(Paragraph('Step 15.16) Three-Method Lifetime Comparison', S['h2']))
        story.append(Paragraph(
            f'One capacitor of the bank, worst-case, T<sub>amb</sub> = {Tamb_rpt}&deg;C, '
            f'V<sub>out</sub> = {Vout_rpt:.0f} V. '
            f'All three methods must exceed the 15-year design target.',
            S['body']))
        story.append(Spacer(1, 2*mm))

        hdr_lt = ['Method', 'ESR basis / heating', 'T<sub>core</sub>', 'Life (temp+V)', 'Pass?']
        rows_lt = [[Paragraph(h, S['tbl_hdr']) for h in hdr_lt]]
        m_min = lt.get('min_life_years', 0)
        for m_key, m_short, m_basis in [
            ('method1', 'Method 1 — Datasheet ESR',
             f"ESR {lt.get('method1',{}).get('esr_lf_ohm','—')} &Omega; &rarr; &Delta;T {lt.get('method1',{}).get('dT_C','—')}&deg;C"),
            ('method2', 'Method 2 — tan-&delta; ESR (worst case)',
             f"ESR {lt.get('method2',{}).get('esr_lf_ohm','—')} &Omega; &rarr; &Delta;T {lt.get('method2',{}).get('dT_C','—')}&deg;C"),
            ('method3', 'Method 3 — Manufacturer model',
             f"f(T)={lt.get('method3',{}).get('f_T','—')}&times; f(I)={lt.get('method3',{}).get('f_I','—')}&times; f(V)={lt.get('method3',{}).get('f_V','—')}&times;"),
        ]:
            m   = lt.get(m_key, {})
            yr  = m.get('life_years_uncapped', m.get('life_years','—'))
            tc  = m.get('T_core_C','—')
            ok  = float(str(yr).replace('>','')) >= 15 if str(yr).replace('>','').replace('.','').isdigit() else False
            is_gov = (m_key == lt.get('governing_method','').lower().replace(' ','').replace('-','')[0:7])
            rows_lt.append([
                Paragraph(f"{'★ ' if is_gov else ''}{m_short}", S['tbl_cell_l']),
                Paragraph(m_basis, S['tbl_cell_l']),
                Paragraph(f"{tc}&deg;C", S['tbl_cell']),
                Paragraph(f"<b>{yr} yr</b>", S['tbl_cell']),
                Paragraph('PASS' if ok else 'FAIL', S['tbl_cell']),
            ])
        cw_lt  = [44*mm, 58*mm, 22*mm, 28*mm, 18*mm]
        t_lt   = Table(rows_lt, colWidths=cw_lt)
        ts_lt  = TableStyle([
            ('BACKGROUND',(0,0),(-1,0),NAVY),('TEXTCOLOR',(0,0),(-1,0),WHITE),
            ('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),('FONTSIZE',(0,0),(-1,-1),8.5),
            ('ALIGN',(0,0),(-1,-1),'CENTER'),('ALIGN',(0,1),(1,-1),'LEFT'),
            ('FONTNAME',(0,1),(-1,-1),'Helvetica'),
            ('ROWBACKGROUNDS',(0,1),(-1,-1),[WHITE,STRIPE]),
            ('GRID',(0,0),(-1,-1),0.3,RULE),('VALIGN',(0,0),(-1,-1),'MIDDLE'),
            ('TOPPADDING',(0,0),(-1,-1),3),('BOTTOMPADDING',(0,0),(-1,-1),3),
            ('LEFTPADDING',(0,0),(-1,-1),5),('RIGHTPADDING',(0,0),(-1,-1),5),
        ])
        # Highlight governing row
        gov_idx = {'method1':1,'method2':2,'method3':3}.get(
            'method'+lt.get('governing_method','Method 1')[-1], 1)
        ts_lt.add('BACKGROUND', (0, gov_idx), (-1, gov_idx), LIGHT)
        ts_lt.add('TEXTCOLOR',  (0, gov_idx), (-1, gov_idx), NAVY)
        ts_lt.add('FONTNAME',   (0, gov_idx), (-1, gov_idx), 'Helvetica-Bold')
        t_lt.setStyle(ts_lt)
        story.append(t_lt)
        story.append(Spacer(1, 3*mm))

        # Governing result banner
        min_yr_v = lt.get('min_life_years', 0)
        pass_v   = lt.get('pass_15yr', False)
        story.append(Paragraph(
            f"<b>Governing (minimum) life = {min_yr_v} yr ({lt.get('governing_method','—')}) — "
            f"{'PASS' if pass_v else 'FAIL'} &ge; 15-year target.</b> "
            f"T<sub>amb</sub> = {Tamb_rpt}&deg;C.",
            S['note']))
        story.append(Spacer(1, 6*mm))

    return story
