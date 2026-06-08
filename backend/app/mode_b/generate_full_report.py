"""
app/mode_b/generate_full_report.py
PFC Inductor Design Report — Steps 1–14.

Generates a professional PDF via ReportLab Platypus.
Called from the /mode-b/generate-full-report endpoint.

Input:
    state          — confirmed Mode A state dict
    approved_design — serialised DesignResult dict (from step7/run-sizing)
    step8_result   — result dict from step8/time-domain

Output: PDF bytes
"""
from __future__ import annotations
import io
import math
from datetime import datetime
from typing import Any

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.platypus import (
    NextPageTemplate,
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, HRFlowable, KeepTogether,
)
from reportlab.platypus import BaseDocTemplate, Frame, PageTemplate


# ── Colour palette ────────────────────────────────────────────────────────────
C_NAVY   = colors.HexColor("#0F2B5B")
C_TEAL   = colors.HexColor("#1A7B8C")
C_GREEN  = colors.HexColor("#1E8C4E")
C_AMBER  = colors.HexColor("#C97A10")
C_RED    = colors.HexColor("#C94040")
C_LIGHT  = colors.HexColor("#EEF2F7")
C_RULE   = colors.HexColor("#C5D0DE")
C_WHITE  = colors.white
C_BLACK  = colors.black
C_MUTED  = colors.HexColor("#6B7A8D")
C_PASS   = colors.HexColor("#D4EFDF")
C_FAIL   = colors.HexColor("#FADBD8")

PAGE_W, PAGE_H = A4
MARGIN = 20 * mm


# ── Style sheet ───────────────────────────────────────────────────────────────
def _styles():
    base = getSampleStyleSheet()
    s = {}

    s["cover_title"] = ParagraphStyle("cover_title",
        fontName="Helvetica-Bold", fontSize=26,
        textColor=C_WHITE, alignment=TA_CENTER, leading=32)

    s["cover_sub"] = ParagraphStyle("cover_sub",
        fontName="Helvetica", fontSize=13,
        textColor=colors.HexColor("#C5D0DE"), alignment=TA_CENTER, leading=18)

    s["cover_meta"] = ParagraphStyle("cover_meta",
        fontName="Helvetica", fontSize=10,
        textColor=colors.HexColor("#8A9CB0"), alignment=TA_CENTER, leading=14)

    s["h1"] = ParagraphStyle("h1",
        fontName="Helvetica-Bold", fontSize=15,
        textColor=C_NAVY, spaceBefore=14, spaceAfter=4, leading=20)

    s["h2"] = ParagraphStyle("h2",
        fontName="Helvetica-Bold", fontSize=11,
        textColor=C_TEAL, spaceBefore=10, spaceAfter=3, leading=14)

    s["h3"] = ParagraphStyle("h3",
        fontName="Helvetica-Bold", fontSize=9,
        textColor=C_NAVY, spaceBefore=7, spaceAfter=2, leading=12)

    s["body"] = ParagraphStyle("body",
        fontName="Helvetica", fontSize=9,
        textColor=C_BLACK, leading=13, spaceAfter=3)

    s["mono"] = ParagraphStyle("mono",
        fontName="Courier", fontSize=8.5,
        textColor=C_NAVY, leading=12)

    s["caption"] = ParagraphStyle("caption",
        fontName="Helvetica-Oblique", fontSize=8,
        textColor=C_MUTED, leading=11, spaceAfter=6)

    s["pass_badge"] = ParagraphStyle("pass_badge",
        fontName="Helvetica-Bold", fontSize=9,
        textColor=C_GREEN, alignment=TA_CENTER)

    s["fail_badge"] = ParagraphStyle("fail_badge",
        fontName="Helvetica-Bold", fontSize=9,
        textColor=C_RED, alignment=TA_CENTER)

    s["toc_entry"] = ParagraphStyle("toc_entry",
        fontName="Helvetica", fontSize=9,
        textColor=C_NAVY, leading=14)

    return s


# ── Table helpers ─────────────────────────────────────────────────────────────
def _tbl_style(header_bg=C_NAVY, stripe=C_LIGHT):
    return TableStyle([
        ("BACKGROUND",   (0, 0), (-1, 0),  header_bg),
        ("TEXTCOLOR",    (0, 0), (-1, 0),  C_WHITE),
        ("FONTNAME",     (0, 0), (-1, 0),  "Helvetica-Bold"),
        ("FONTSIZE",     (0, 0), (-1, 0),  8),
        ("FONTNAME",     (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE",     (0, 1), (-1, -1), 8),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [C_WHITE, stripe]),
        ("GRID",         (0, 0), (-1, -1), 0.3, C_RULE),
        ("VALIGN",       (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",   (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 4),
        ("LEFTPADDING",  (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ])


def _kv_table(rows: list[tuple], col_w=None, s=None):
    """Two-column key-value table."""
    col_w = col_w or [70*mm, 90*mm]
    data = [[Paragraph(f"<b>{k}</b>", s["body"]),
             Paragraph(str(v), s["mono"])] for k, v in rows]
    t = Table(data, colWidths=col_w)
    t.setStyle(TableStyle([
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [C_WHITE, C_LIGHT]),
        ("GRID",          (0, 0), (-1, -1), 0.3, C_RULE),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
    ]))
    return t


def _section_rule(s):
    return HRFlowable(width="100%", thickness=0.5, color=C_RULE,
                      spaceBefore=4, spaceAfter=4)


def _badge(text: str, passed: bool, s):
    style = s["pass_badge"] if passed else s["fail_badge"]
    prefix = "✓ " if passed else "✗ "
    return Paragraph(prefix + text, style)


def _fmt(v, decimals=3, unit=""):
    if v is None:
        return "—"
    try:
        return f"{float(v):.{decimals}f}{(' ' + unit) if unit else ''}"
    except Exception:
        return str(v)


# ── Cover page ────────────────────────────────────────────────────────────────
def _cover(story, state, d, s):
    """Navy cover page with project metadata."""
    intake = state.get("intake", {})
    ap = intake.get("application", {})
    project_id = state.get("project_id", "—")
    app_class = intake.get("compliance", {}).get("application_class", "Industrial")
    now = datetime.now().strftime("%d %B %Y  %H:%M UTC")

    # Draw navy rectangle as table background trick
    cover_bg = Table(
        [[Paragraph("PFC Inductor Design Report", s["cover_title"])],
         [Paragraph("Full Calculation Record — Steps 1 through 14", s["cover_sub"])],
         [Spacer(1, 8*mm)],
         [Paragraph(f"Project: {project_id}", s["cover_meta"])],
         [Paragraph(f"Application class: {app_class}", s["cover_meta"])],
         [Paragraph(f"Generated: {now}", s["cover_meta"])],
         ],
        colWidths=[PAGE_W - 2*MARGIN],
    )
    cover_bg.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), C_NAVY),
        ("TOPPADDING",    (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LEFTPADDING",   (0, 0), (-1, -1), 18),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 18),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(Spacer(1, 30*mm))
    story.append(cover_bg)
    story.append(Spacer(1, 12*mm))

    # Summary bar
    pn  = d.get("part_number", "—")
    stk = d.get("stacks", 1)
    N   = d.get("N", "—")
    ffcu= d.get("FFcu", 0)
    status = "APPROVED" if d.get("passed") else "REVIEW REQUIRED"
    s_color = C_GREEN if d.get("passed") else C_AMBER

    summary = Table([
        [Paragraph("<b>Core</b>", s["body"]),
         Paragraph("<b>Turns</b>", s["body"]),
         Paragraph("<b>Wire</b>", s["body"]),
         Paragraph("<b>FFcu</b>", s["body"]),
         Paragraph("<b>Status</b>", s["body"])],
        [Paragraph(f"{pn}" + (f" ×{stk}" if stk > 1 else ""), s["mono"]),
         Paragraph(str(N), s["mono"]),
         Paragraph(str(d.get("wire_designation", "—")), s["mono"]),
         Paragraph(f"{ffcu*100:.1f}%", s["mono"]),
         Paragraph(f"<b>{status}</b>", ParagraphStyle("st", fontName="Helvetica-Bold",
             fontSize=9, textColor=s_color))],
    ], colWidths=[50*mm, 25*mm, 55*mm, 25*mm, 40*mm])
    summary.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0), C_LIGHT),
        ("GRID",          (0, 0), (-1, -1), 0.4, C_RULE),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
    ]))
    story.append(summary)
    story.append(Spacer(1, 8*mm))

    # Design spec quick-ref
    spec_rows = [
        ("Output power (low-line)",    f"{ap.get('output_power_w_low_line', '—')} W"),
        ("Output power (high-line)",   f"{ap.get('output_power_w_high_line', '—')} W"),
        ("Vin range",                  f"{ap.get('vin_rms_min', '—')} – {ap.get('vin_rms_max', '—')} Vac"),
        ("Output bus voltage",         f"{ap.get('output_bus_voltage_v', '—')} Vdc"),
        ("Topology",                   state.get("selected_topology", "—").replace("_", " ").title()),
        ("Phases",                     str(state.get("selected_channels", 1))),
        ("Switching frequency",        f"{float(state.get('topology_specific_inputs',{}).get('recommended_frequency_hz', 70000))/1e3:.0f} kHz"),
    ]
    story.append(_kv_table(spec_rows, col_w=[80*mm, 80*mm], s=s))
    story.append(PageBreak())


# ── Table of contents ─────────────────────────────────────────────────────────
def _toc(story, s):
    story.append(Paragraph("Table of Contents", s["h1"]))
    story.append(_section_rule(s))
    sections = [
        ("Steps 1–3",  "Specification, Compliance & Topology Selection"),
        ("Step 4",     "Controller Strategy"),
        ("Step 5",     "Interleaving & Channel Count"),
        ("Step 6",     "Switching Frequency & Mode"),
        ("Step 7",     "Inductance Calculation"),
        ("Step 8",     "Peak & RMS Current"),
        ("Step 9",     "Core Material & Geometry Selection"),
        ("Step 10",    "Wire & Winding Selection"),
        ("Step 11",    "Window Utilisation & Fill Factor"),
        ("Step 12",    "Thermal Pre-Screen"),
        ("Step 13",    "Magnetic Design — Full Calculation"),
        ("  13.1",     "Turns Calculation"),
        ("  13.2",     "AL & Inductance vs Bias"),
        ("  13.3",     "Flux Density"),
        ("  13.4",     "Winding Fill & Copper Area"),
        ("  13.5",     "Loss Calculation (9 op-points)"),
        ("  13.6",     "Thermal Convergence"),
        ("  13.7",     "Pass/Fail Checks"),
        ("Step 14",    "Time-Domain Core-Loss Analysis"),
        ("  14.1",     "Bac(t) half-cycle integration"),
        ("  14.2",     "Pcore average vs crest-point comparison"),
    ]
    for num, title in sections:
        indent = 10*mm if num.startswith("  ") else 0
        story.append(Paragraph(
            f'<para leftIndent="{indent}"><b>{num}</b> — {title}</para>',
            s["toc_entry"]))
    story.append(PageBreak())


# ── Steps 1–3: Specification ──────────────────────────────────────────────────
def _steps1_3(story, state, s):
    intake = state.get("intake", {})
    ap = intake.get("application", {})
    comp = intake.get("compliance", {})
    therm = intake.get("thermal", {})

    story.append(Paragraph("Steps 1–3 — Specification, Compliance & Input Data", s["h1"]))
    story.append(_section_rule(s))

    story.append(Paragraph("3.1  Application Requirements", s["h2"]))
    rows = [
        ("Application class",         comp.get("application_class", "Industrial")),
        ("Output power — low line",   f"{ap.get('output_power_w_low_line', '—')} W"),
        ("Output power — high line",  f"{ap.get('output_power_w_high_line', '—')} W"),
        ("Vin min (rms)",             f"{ap.get('vin_rms_min', '—')} Vac"),
        ("Vin max (rms)",             f"{ap.get('vin_rms_max', '—')} Vac"),
        ("Output bus voltage",        f"{ap.get('output_bus_voltage_v', '—')} Vdc"),
        ("Power factor target",       f"≥ {ap.get('power_factor_min', 0.99):.3f}"),
        ("THD target",                f"≤ {ap.get('thd_max_pct', 5):.1f}%"),
        ("Efficiency target",         f"≥ {ap.get('efficiency_min_pct', 93):.1f}%"),
        ("Grid standard",             comp.get("grid_standard", "IEC 61000-3-2 Class A")),
        ("Safety standard",           comp.get("safety_standard", "IEC 62368-1")),
    ]
    story.append(_kv_table(rows, s=s))

    story.append(Paragraph("3.2  Thermal Budget", s["h2"]))
    t_amb = float(therm.get("ambient_temp_c_max", 50))
    t_hot = float(therm.get("hotspot_limit_c", 110))
    rows2 = [
        ("Max ambient temperature",   f"{t_amb:.0f} °C"),
        ("Hotspot temperature limit", f"{t_hot:.0f} °C"),
        ("Thermal budget ΔT",         f"{t_hot - t_amb:.0f} °C"),
        ("Cooling method",            therm.get("cooling_method", "Forced air")),
    ]
    story.append(_kv_table(rows2, s=s))
    story.append(Spacer(1, 4*mm))


# ── Step 4: Controller ────────────────────────────────────────────────────────
def _step4(story, state, s):
    story.append(Paragraph("Step 4 — Controller Strategy", s["h1"]))
    story.append(_section_rule(s))
    ctrl = state.get("controller_strategy", {})
    rows = [
        ("Selected controller mode",   state.get("selected_controller_mode", "—")),
        ("Recommended controller",     ctrl.get("recommended_controller_mode", "—")),
        ("Control law",                ctrl.get("control_law", "—")),
        ("Zero-crossing detection",    str(ctrl.get("zero_crossing_detect", "—"))),
        ("Interleaved phase shift",    ctrl.get("phase_shift_strategy", "—")),
    ]
    story.append(_kv_table(rows, s=s))
    story.append(Spacer(1, 4*mm))


# ── Steps 5–6: Topology & Frequency ──────────────────────────────────────────
def _steps5_6(story, state, s):
    story.append(Paragraph("Steps 5–6 — Interleaving, Channels & Switching Frequency", s["h1"]))
    story.append(_section_rule(s))
    tsi = state.get("topology_specific_inputs", {})
    n_ch = state.get("selected_channels", 1)
    fsw = float(tsi.get("recommended_frequency_hz", 70000))
    topo = state.get("selected_topology", "—").replace("_", " ").title()
    mode = state.get("selected_mode", "ccm").upper()
    fsw_style = tsi.get("switching_frequency_style", "fixed").title()

    rows = [
        ("Topology",               topo),
        ("Conduction mode",        mode),
        ("Number of phases",       str(n_ch)),
        ("Phase shift",            f"{360/n_ch:.0f}° between phases" if n_ch > 1 else "N/A (single phase)"),
        ("Switching frequency",    f"{fsw/1e3:.0f} kHz ({fsw_style})"),
        ("Ripple cancellation",    f"Input ripple reduced by factor {n_ch} with {n_ch}-phase interleaving" if n_ch > 1 else "N/A"),
    ]
    story.append(_kv_table(rows, s=s))
    story.append(Spacer(1, 4*mm))


# ── Steps 7–8: Inductance & Current ──────────────────────────────────────────
def _steps7_8(story, state, s):
    story.append(Paragraph("Steps 7–8 — Inductance & Current Calculations", s["h1"]))
    story.append(_section_rule(s))
    tsi = state.get("topology_specific_inputs", {})
    intake = state.get("intake", {})
    ap = intake.get("application", {})

    Pout = float(ap.get("output_power_w_low_line", 1700))
    Vin  = float(ap.get("vin_rms_min", 90))
    Vout = float(ap.get("output_bus_voltage_v", 393))
    fsw  = float(tsi.get("recommended_frequency_hz", 70000))
    crest= float(tsi.get("default_crest_ripple_ratio", 0.20))
    eta  = 0.945
    PF   = 0.9987
    n_ph = int(state.get("selected_channels", 2))

    Vin_pk  = Vin * math.sqrt(2)
    D_crest = 1 - Vin_pk / Vout
    Pin     = Pout / eta
    Ipk_line= math.sqrt(2) * Pin / (Vin * PF)
    dIL_pp  = float(tsi.get("confirmed_dIL_A", tsi.get("dIL_pp_A", 5.161)))
    L_sel   = float(tsi.get("confirmed_L_uH_sel", tsi.get("confirmed_L_uH", 240)))
    Ipk_ph  = Ipk_line / n_ph + dIL_pp / 2
    Irms_ph = float(tsi.get("Iph_rms_A", float(DEFAULT_OPS_ROW0_RMS if False else 10.07)))

    story.append(Paragraph("Step 7 — Inductance", s["h2"]))
    story.append(Paragraph(
        f"Target inductance is derived from the volt-second balance at the crest of the "
        f"lowest-line voltage ({Vin} Vac), at duty cycle D = 1 − Vin,pk / Vout.", s["body"]))
    rows7 = [
        ("Vin,min (rms)",           f"{Vin} Vac"),
        ("Vin,pk at low line",      f"{Vin_pk:.2f} Vpk"),
        ("Vout (bus)",              f"{Vout} Vdc"),
        ("Duty cycle D at crest",   f"{D_crest:.4f}"),
        ("Switching frequency",     f"{fsw/1e3:.0f} kHz"),
        ("Crest ripple ratio r",    f"{crest:.3f}  (dIL/Ipk = {crest*100:.1f}%)"),
        ("Peak line current",       f"{Ipk_line:.3f} A (total, {n_ph}-phase)"),
        ("Peak phase current Ipk",  f"{Ipk_ph:.3f} A/phase"),
        ("Peak-to-peak ripple dIL", f"{dIL_pp:.3f} A"),
        ("Indicative L",            f"{float(tsi.get('confirmed_L_uH', L_sel)):.1f} µH"),
        ("Selected L (rounded)",    f"{L_sel:.0f} µH"),
    ]
    story.append(_kv_table(rows7, s=s))

    story.append(Paragraph("Step 8 — RMS & Peak Currents", s["h2"]))
    story.append(Paragraph(
        f"Per-phase RMS current computed from the 9-operating-point matrix "
        f"(90–264 Vac, 1700–3600 W). Worst case is at Vin=90 Vac.", s["body"]))
    rows8 = [
        ("Per-phase RMS Irms",      f"{Irms_ph:.3f} A"),
        ("Per-phase peak Ipk",      f"{Ipk_ph:.3f} A"),
        ("HF ripple Irms,HF",       f"{dIL_pp / (2*math.sqrt(3)):.3f} A"),
    ]
    story.append(_kv_table(rows8, s=s))
    story.append(Spacer(1, 4*mm))


# ── Steps 9–12: Pre-design selections ────────────────────────────────────────
def _steps9_12(story, state, d, s):
    story.append(Paragraph("Steps 9–12 — Core, Wire & Pre-Screen", s["h1"]))
    story.append(_section_rule(s))

    story.append(Paragraph("Step 9 — Core Material & Geometry", s["h2"]))
    rows9 = [
        ("Core part number",    d.get("part_number", "—")),
        ("Material",            d.get("material_key", "—")),
        ("Core type",           d.get("core_type", "—").title()),
        ("Stacks",              str(d.get("stacks", 1))),
        ("Ae total",            f"{d.get('Ae_total_mm2', 0):.2f} mm²"),
        ("Wa (window area)",    f"{d.get('Wa_total_mm2', 0):.2f} mm²"),
        ("Ve total",            f"{d.get('Ve_total_cm3', 0):.3f} cm³"),
        ("Le (single core)",    f"{d.get('Le_single_mm', 0):.2f} mm"),
        ("h effective",         f"{d.get('h_effective_mm', 0):.2f} mm"),
    ]
    if d.get("lg_mm", 0) > 0:
        rows9.append(("Air gap lg", f"{d.get('lg_mm', 0):.3f} mm (ferrite)"))
    story.append(_kv_table(rows9, s=s))

    story.append(Paragraph("Step 10 — Wire & Winding", s["h2"]))
    n_par = d.get("n_parallel", 1) or 1
    winding_style = {1: "Single strand", 2: "Bifilar (×2 parallel)", 3: "Trifilar (×3 parallel)"}.get(n_par, f"×{n_par} parallel")
    rows10 = [
        ("Wire designation",    d.get("wire_designation", "—")),
        ("Strand diameter",     f"{d.get('d_strand_mm', 0):.3f} mm"),
        ("Strands per bundle",  str(d.get("n_strands", 0))),
        ("Winding style",       winding_style),
        ("Cu area (total)",     f"{d.get('Cu_area_mm2', 0):.4f} mm²"),
        ("Wire OD",             f"{d.get('wire_OD_mm', 0):.3f} mm"),
        ("R per metre @20°C",   f"{d.get('R_per_m_20C', 0)*1000:.4f} mΩ/m"),
    ]
    story.append(_kv_table(rows10, s=s))

    story.append(Paragraph("Step 11 — Window Utilisation", s["h2"]))
    ffcu = float(d.get("FFcu", 0))
    ku   = float(d.get("Ku", ffcu))
    rows11 = [
        ("N turns",             str(d.get("N", "—"))),
        ("FFcu = N×Acu / Wa",   f"{ffcu*100:.2f}%"),
        ("Ku (physical fill)",  f"{ku*100:.2f}%"),
        ("FFcu limit",          "40% (designer setting)"),
        ("Fill status",         "✓ Within limit" if ffcu <= 0.40 else "⚠ Exceeds limit"),
    ]
    story.append(_kv_table(rows11, s=s))

    story.append(Paragraph("Step 12 — Thermal Pre-Screen", s["h2"]))
    intake = state.get("intake", {})
    therm = intake.get("thermal", {})
    t_amb = float(therm.get("ambient_temp_c_max", 50))
    t_hot = float(therm.get("hotspot_limit_c", 110))
    dT_bgt = t_hot - t_amb
    dT_act = float(d.get("dT_rise_C", 0))
    rows12 = [
        ("Thermal budget ΔT",   f"{dT_bgt:.0f} °C"),
        ("Computed ΔT rise",    f"{dT_act:.1f} °C"),
        ("T_core (converged)",  f"{d.get('T_core_C', 0):.1f} °C"),
        ("Thermal status",      "✓ Within budget" if dT_act <= dT_bgt else "⚠ Exceeds budget"),
    ]
    story.append(_kv_table(rows12, s=s))
    story.append(Spacer(1, 4*mm))


# ── Step 13: Full magnetics ───────────────────────────────────────────────────
def _step13(story, d, s):
    story.append(Paragraph("Step 13 — Magnetic Design: Full Calculation", s["h1"]))
    story.append(_section_rule(s))
    story.append(Paragraph(
        "This section reproduces the full Step 13 calculation sequence from the design reference. "
        "All values are computed by the sizing engine and cross-checked against the 9-operating-point matrix.",
        s["body"]))
    story.append(Spacer(1, 3*mm))

    # 13.1 Turns
    story.append(Paragraph("13.1  Turns Calculation", s["h2"]))
    n_par = d.get("n_parallel", 1) or 1
    rows = [
        ("Method",           "Iterative N convergence with DC-bias rolloff (powder) / B-field convergence (ferrite)"),
        ("N (turns)",        str(d.get("N", "—"))),
        ("AT design",        f"{d.get('AT_design', 0):.2f}  A·turns"),
        ("H at design pt",   f"{d.get('H_Oe_design', 0):.2f}  Oe"),
        ("Air gap lg",       f"{d.get('lg_mm', 0):.3f} mm" if d.get("lg_mm", 0) > 0 else "N/A (powder core)"),
    ]
    story.append(_kv_table(rows, s=s))

    # 13.2 Inductance
    story.append(Paragraph("13.2  AL and Inductance vs DC Bias", s["h2"]))
    rows = [
        ("L₀ min  (AL,min × N²)",  f"{d.get('L0_min_uH', 0):.1f} µH"),
        ("L₀ nom  (AL,nom × N²)",  f"{d.get('L0_nom_uH', 0):.1f} µH"),
        ("L₀ max  (AL,max × N²)",  f"{d.get('L0_max_uH', 0):.1f} µH"),
        ("k,req min",               f"{d.get('kreq_min', 0):.4f}"),
        ("k,req nom",               f"{d.get('kreq_nom', 0):.4f}"),
        ("k,req max",               f"{d.get('kreq_max', 0):.4f}"),
        ("L full-load (nom × k)",   f"{round(d.get('L0_nom_uH',0)*d.get('kreq_nom',1)):.0f} µH"),
        ("L variation",             f"{round((1-d.get('kreq_nom',1))*100):.0f}% DC-bias rolloff"),
    ]
    story.append(_kv_table(rows, s=s))

    # L vs Vin table
    lvt = d.get("L_vs_Vin_table", [])
    if lvt:
        story.append(Paragraph("L full-load min/nom/max across all 9 operating points:", s["h3"]))
        hdr = ["Vin rms", "Ipk line A", "Iavg A", "AT", "H Oe", "k_bias", "L_min µH", "L_nom µH", "L_max µH"]
        rows_t = [hdr] + [
            [str(r.get("Vin_rms","")), _fmt(r.get("Ipk_line"), 2), _fmt(r.get("Iavg_crest"), 2),
             _fmt(r.get("AT"), 1), _fmt(r.get("H_Oe"), 1), _fmt(r.get("k_bias"), 4),
             _fmt(r.get("L_full_min_uH"), 1), _fmt(r.get("L_full_nom_uH"), 1), _fmt(r.get("L_full_max_uH"), 1)]
            for r in lvt
        ]
        col_w = [18*mm, 20*mm, 18*mm, 16*mm, 15*mm, 16*mm, 18*mm, 18*mm, 18*mm]
        t = Table(rows_t, colWidths=col_w)
        t.setStyle(_tbl_style(header_bg=C_TEAL))
        story.append(t)
        story.append(Spacer(1, 3*mm))

    # 13.3 Flux density
    story.append(Paragraph("13.3  Flux Density (at 90 Vac crest)", s["h2"]))
    rows = [
        ("ΔBpp (AC swing)",     f"{d.get('dBpp_T', 0)*1000:.3f} mT"),
        ("Bac,pk = ΔB/2",       f"{d.get('Bac_pk_T', 0)*1000:.3f} mT"),
        ("Bdc (DC bias)",       f"{d.get('Bdc_T', 0)*1000:.2f} mT"),
        ("Bmin @ full-load",    f"{d.get('Bmin_FL_T', 0)*1000:.2f} mT"),
        ("Bmax @ full-load",    f"{d.get('Bmax_FL_T', 0)*1000:.2f} mT"),
        ("Bsat @ T_core",       f"{d.get('Bsat_at_Tcore', 0)*1000:.0f} mT"),
        ("Saturation margin",   f"{d.get('sat_margin_pct', 0):.1f}%  {'✓' if d.get('sat_margin_pct',0)>=15 else '⚠'}"),
    ]
    story.append(_kv_table(rows, s=s))

    # 13.4 Winding fill
    story.append(Paragraph("13.4  Winding Fill Factor", s["h2"]))
    ffcu = float(d.get("FFcu", 0))
    ku   = float(d.get("Ku", ffcu))
    rows = [
        ("MLT (mean length/turn)", f"{d.get('MLT_mm', 0):.2f} mm"),
        ("Winding length",         f"{d.get('Cu_length_m', 0):.4f} m"),
        ("Cu area per conductor",  f"{d.get('Cu_area_mm2', 0):.4f} mm²"),
        ("Acu total = N × Acu",    f"{d.get('N',0) * d.get('Cu_area_mm2',0):.3f} mm²"),
        ("Wa total",               f"{d.get('Wa_total_mm2', 0):.2f} mm²"),
        ("FFcu = Acu,tot / Wa",    f"{ffcu*100:.2f}%  {'✓ ≤40%' if ffcu<=0.40 else '⚠ >40%'}"),
        ("Ku (physical bundle)",   f"{ku*100:.2f}%"),
        ("Rac/Rdc (Dowell)",       f"{d.get('Rac_Rdc', 1.0):.4f}×"),
    ]
    story.append(_kv_table(rows, s=s))

    # 13.5 Losses
    story.append(Paragraph("13.5  Loss Calculation", s["h2"]))
    rows = [
        ("DCR @ 25°C",          f"{d.get('DCR_25C_mOhm', 0):.3f} mΩ"),
        ("DCR @ 100°C",         f"{d.get('DCR_100C_mOhm', 0):.3f} mΩ"),
        ("Pcu @ 25°C",          f"{d.get('Pcu_25C_W', 0):.4f} W"),
        ("Pcu @ 100°C",         f"{d.get('Pcu_100C_W', 0):.4f} W"),
        ("Pcore",               f"{d.get('Pcore_W', 0):.4f} W"),
        ("P_fringing",          f"{d.get('P_fringing_W', 0):.4f} W"),
        ("Ptotal @ 25°C",       f"{d.get('Ptotal_25C_W', 0):.4f} W"),
        ("Ptotal @ 100°C",      f"{d.get('Ptotal_100C_W', 0):.4f} W"),
        ("Efficiency loss",     f"{d.get('Ptotal_100C_W',0)/3600*100:.3f}%"),
    ]
    story.append(_kv_table(rows, s=s))

    # Loss vs Vin tables
    for label, key in [("Loss vs Vin @ 25°C", "loss_table_25C"), ("Loss vs Vin @ 100°C", "loss_table_100C")]:
        lt = d.get(key, [])
        if lt:
            story.append(Paragraph(label, s["h3"]))
            hdr = ["Vin rms", "Vin pk V", "D crest", "Irms A", "Bac pk mT", "Pcu W", "Pcore W", "Ptotal W"]
            rows_t = [hdr] + [
                [str(r.get("Vin_rms","")), _fmt(r.get("Vin_pk"),1), _fmt(r.get("D_crest"),4),
                 _fmt(r.get("Irms"),3), f"{r.get('Bac_pk',0)*1000:.2f}",
                 _fmt(r.get("Pcu_W"),4), _fmt(r.get("Pcore_W"),4), _fmt(r.get("Ptotal_W"),4)]
                for r in lt
            ]
            col_w = [18*mm, 18*mm, 17*mm, 17*mm, 20*mm, 18*mm, 18*mm, 18*mm]
            t = Table(rows_t, colWidths=col_w)
            t.setStyle(_tbl_style(header_bg=C_TEAL))
            story.append(t)
            story.append(Spacer(1, 3*mm))

    # 13.6 Thermal
    story.append(Paragraph("13.6  Thermal Convergence", s["h2"]))
    t_amb = 50.0
    rows = [
        ("T_ambient",               f"{t_amb:.0f} °C"),
        ("T_core (converged)",      f"{d.get('T_core_C', 0):.2f} °C"),
        ("ΔT rise",                 f"{d.get('dT_rise_C', 0):.2f} °C"),
        ("ΔT budget",               f"{d.get('dT_budget_C', 60):.0f} °C"),
        ("Thermal status",          "✓ Pass" if d.get('dT_rise_C',0) <= d.get('dT_budget_C',60) else "⚠ Exceeds budget"),
    ]
    story.append(_kv_table(rows, s=s))

    # 13.7 Pass/Fail
    story.append(Paragraph("13.7  Pass / Fail Summary", s["h2"]))
    passed = d.get("passed", False)
    fail_reasons = d.get("fail_reasons", [])

    status_data = [
        [Paragraph("Overall design result", s["body"]),
         _badge("PASS — all constraints met" if passed else "FAIL — see reasons below", passed, s)],
    ]
    if fail_reasons:
        for fr in fail_reasons:
            status_data.append([
                Paragraph("  ⚠ Constraint violation", s["body"]),
                Paragraph(fr, ParagraphStyle("fr", fontName="Helvetica", fontSize=8,
                    textColor=C_RED, leading=11)),
            ])

    checks = [
        ("FFcu ≤ 40%",          d.get("FFcu",0) <= 0.40),
        ("Saturation margin ≥ 15%", d.get("sat_margin_pct",0) >= 15.0),
        ("ΔT ≤ budget",         d.get("dT_rise_C",0) <= d.get("dT_budget_C",60)),
    ]
    check_data = [["Check", "Result", "Actual"]]
    check_labels = {
        "FFcu ≤ 40%":           f"{d.get('FFcu',0)*100:.2f}%",
        "Saturation margin ≥ 15%": f"{d.get('sat_margin_pct',0):.1f}%",
        "ΔT ≤ budget":          f"{d.get('dT_rise_C',0):.1f}°C vs {d.get('dT_budget_C',60):.0f}°C",
    }
    for label, ok in checks:
        check_data.append([
            Paragraph(label, s["body"]),
            Paragraph("✓ PASS" if ok else "✗ FAIL",
                ParagraphStyle("ck", fontName="Helvetica-Bold", fontSize=8,
                    textColor=C_GREEN if ok else C_RED)),
            Paragraph(check_labels.get(label, ""), s["mono"]),
        ])
    t = Table(check_data, colWidths=[75*mm, 30*mm, 60*mm])
    t.setStyle(_tbl_style(header_bg=C_NAVY))
    # Highlight fail rows
    for i, (_, ok) in enumerate(checks, 1):
        if not ok:
            t.setStyle(TableStyle([("BACKGROUND", (0,i), (-1,i), C_FAIL)]))
    story.append(t)
    story.append(Spacer(1, 4*mm))
    story.append(PageBreak())


# ── Step 14: Time-domain ──────────────────────────────────────────────────────
def _step14(story, step8, s):
    story.append(Paragraph("Step 14 — Time-Domain Core-Loss Analysis", s["h1"]))
    story.append(_section_rule(s))
    story.append(Paragraph(
        "Integrates Pcore(t) over the half line cycle at each of the 9 operating points. "
        "This corrects for the well-known error of using only the crest-point — which overestimates "
        "at 90 Vac but underestimates at 230–264 Vac.",
        s["body"]))
    story.append(Spacer(1, 3*mm))

    if not step8:
        story.append(Paragraph("⚠  Step 14 data not available — time-domain analysis was not run.", s["body"]))
        return

    # Power-law fit
    fit = step8.get("power_law_fit", {})
    story.append(Paragraph("14.1  Power-Law Fit to Crest-Point Data", s["h2"]))
    rows = [
        ("Fit equation",    f"Pcore = {fit.get('k',0):.2f} × Bac^{fit.get('n',0):.4f}"),
        ("Coefficient k",   f"{fit.get('k', 0):.4f}"),
        ("Exponent n",      f"{fit.get('n', 0):.4f}"),
        ("R² fit quality",  f"{fit.get('r_squared', 0):.6f}"),
    ]
    story.append(_kv_table(rows, s=s))

    # Summary table
    story.append(Paragraph("14.2  Pcore Average vs Crest-Point per Operating Point", s["h2"]))
    st = step8.get("summary_table", [])
    if st:
        hdr = ["Vin rms", "Bac pk mT", "Pcore avg W", "Pcore crest W", "Avg/Crest %", "Assessment"]
        rows_t = [hdr]
        for r in st:
            ratio = r.get("Pcore_avg_W", 0) / max(r.get("Pcore_pk_W", 0.001), 0.001)
            pct = ratio * 100
            assess = "Crest ~OK" if 80 <= pct <= 120 else ("Crest over-est." if pct < 80 else "Crest under-est.")
            rows_t.append([
                str(r.get("Vin_rms", "")),
                f"{r.get('Bac_pk',0)*1000:.3f}",
                f"{r.get('Pcore_avg_W',0):.4f}",
                f"{r.get('Pcore_pk_W',0):.4f}",
                f"{pct:.0f}%",
                assess,
            ])
        col_w = [18*mm, 20*mm, 24*mm, 24*mm, 22*mm, 35*mm]
        t = Table(rows_t, colWidths=col_w)
        t.setStyle(_tbl_style(header_bg=C_TEAL))
        # Highlight 90Vac row (first data row)
        t.setStyle(TableStyle([("BACKGROUND", (0,1), (-1,1), colors.HexColor("#D6EAF8"))]))
        story.append(t)
        story.append(Spacer(1, 3*mm))

    story.append(Paragraph(
        "Key finding: At 90 Vac the crest-point method overestimates average Pcore "
        "(duty cycle is high and Bac(t) is low away from the crest). "
        "At 230–264 Vac the crest-point underestimates. "
        "The time-domain average should be used as the thermal-budget figure of merit.",
        s["body"]))


# ── Header / footer callbacks ─────────────────────────────────────────────────
_PAGE_NUM = [0]


def _on_page(canvas, doc):
    canvas.saveState()
    w, h = A4
    # Header bar
    canvas.setFillColor(C_NAVY)
    canvas.rect(0, h - 12*mm, w, 12*mm, fill=1, stroke=0)
    canvas.setFillColor(C_WHITE)
    canvas.setFont("Helvetica-Bold", 8)
    canvas.drawString(MARGIN, h - 8*mm, "PFC Inductor Design Report")
    canvas.setFont("Helvetica", 7)
    canvas.drawRightString(w - MARGIN, h - 8*mm, f"CONFIDENTIAL — {datetime.now().strftime('%Y-%m-%d')}")
    # Footer
    canvas.setFillColor(C_MUTED)
    canvas.setFont("Helvetica", 7)
    canvas.drawString(MARGIN, 8*mm, "Generated by PFC AI Design Agent v2")
    canvas.drawRightString(w - MARGIN, 8*mm, f"Page {doc.page}")
    canvas.restoreState()


def _on_cover(canvas, doc):
    # No header/footer on cover
    pass


# ── Main entry point ──────────────────────────────────────────────────────────
def generate_full_report(state: dict, approved_design: dict, step8_result: dict | None = None) -> bytes:
    """
    Build complete Steps 1–14 PDF and return raw bytes.

    Parameters
    ----------
    state           : confirmed Mode A state (intake, topology_specific_inputs, …)
    approved_design : serialised DesignResult from step7/run-sizing
    step8_result    : result dict from step8/time-domain (may be None)
    """
    buf = io.BytesIO()
    s = _styles()
    d = approved_design

    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=16*mm, bottomMargin=16*mm,
        title="PFC Inductor Design Report — Steps 1–14",
        author="PFC AI Design Agent v2",
        subject="Full magnetic design calculation record",
    )

    story = []

    # Page 1 = cover (handled by onFirstPage callback = no header/footer)
    # Pages 2+ = body (header + footer via onLaterPages callback)
    _cover(story, state, d, s)

    # All content pages
    _toc(story, s)
    _steps1_3(story, state, s)
    _step4(story, state, s)
    _steps5_6(story, state, s)
    _steps7_8(story, state, s)
    _steps9_12(story, state, d, s)
    story.append(PageBreak())
    _step13(story, d, s)
    _step14(story, step8_result, s)

    doc.build(
        story,
        onFirstPage=_on_cover,
        onLaterPages=_on_page,
    )

    return buf.getvalue()
