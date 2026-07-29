"""
emi_schematic.py
----------------
Generates the conducted-EMI-filter schematic as a vector SVG. Two views:

  view="asbuilt" — the designer's as-built topology (from specs/Improvements/EMI/
                   EMI Schematic.pdf): fuses, X-caps, MOV/GDT surge cluster,
                   bleeders, three CM chokes (L1/L2/L3) interleaved with X-caps,
                   Y-caps and ferrite beads. Uses the designer's ref-designators.
  view="synth"   — the synthesized functional ladder the engine actually solves,
                   annotated with the COMPUTED values (C_X / L_DM / R_d+L_d /
                   L_CM / C_Y / R_bleed). Pass `vals` from the EMIResult; if it
                   is None the ladder falls back to symbolic labels.

Pure standard library for SVG output — no dependencies (mirrors the NTC
inrush_schematic.py pattern so it embeds via svglib and serves inline in the GUI).

    from emi_schematic import build_svg
    svg = build_svg(view="synth", vals={"c_x_uf": 4.7, ...})
"""

from __future__ import annotations

import argparse
import datetime as _dt

# --- style constants (shared look with inrush_schematic.py) -----------------
INK = "#1a1a2e"        # power path / body text
CTRL = "#4a6fa5"       # earth / Y-cap path
ACC = "#b5473a"        # protection (fuse / MOV / GDT / bleeder)
MUTED = "#7f8c8d"      # secondary text
RULE = "#c9ced8"       # frame + hairlines
TINT = "#f7f8fb"       # component body fill
FLAG = "#eef1f6"       # net-label fill
PAPER = "#ffffff"

SANS = "'IBM Plex Sans', 'Segoe UI', Arial, sans-serif"
MONO = "'IBM Plex Mono', 'Consolas', monospace"

W, H = 1240, 560       # drawing sheet, user units


# --- primitives ------------------------------------------------------------
def _t(x, y, s, size=15, weight="600", fill=INK, anchor="start",
       family=SANS, spacing=None):
    ls = f' letter-spacing="{spacing}"' if spacing else ""
    s = str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return (f'<text x="{x}" y="{y}" font-family="{family}" font-size="{size}" '
            f'font-weight="{weight}" fill="{fill}" text-anchor="{anchor}"{ls}>{s}</text>')


def _flag(x, y, w, h, label, size=14):
    return (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{FLAG}" '
            f'stroke="{CTRL}" stroke-width="1.5" rx="3"/>'
            + _t(x + w / 2, y + h * 0.68, label, size=size, family=MONO, anchor="middle"))


def _dots(pts, fill=INK, r=4.0):
    return (f'<g fill="{fill}">'
            + "".join(f'<circle cx="{x}" cy="{y}" r="{r}"/>' for x, y in pts) + "</g>")


def _coil(x0, y, n=4, w=52, up=13, color=INK):
    """Horizontal coil of n half-circle bumps along a rail at height y."""
    step = w / n
    d = [f"M{x0} {y}"]
    for i in range(n):
        cx1 = x0 + i * step + step * 0.15
        cx2 = x0 + i * step + step * 0.85
        xe = x0 + (i + 1) * step
        d.append(f"C{cx1} {y-up*2}, {cx2} {y-up*2}, {xe} {y}")
    return (f'<path d="{" ".join(d)}" fill="none" stroke="{color}" '
            f'stroke-width="2.2" stroke-linecap="round"/>')


def _vcoil(x, y0, n=4, h=52, side=13, color=INK):
    """Vertical coil (for a CM-choke winding drawn on a vertical stub)."""
    step = h / n
    d = [f"M{x} {y0}"]
    for i in range(n):
        cy1 = y0 + i * step + step * 0.15
        cy2 = y0 + i * step + step * 0.85
        ye = y0 + (i + 1) * step
        d.append(f"C{x+side*2} {cy1}, {x+side*2} {cy2}, {x} {ye}")
    return (f'<path d="{" ".join(d)}" fill="none" stroke="{color}" '
            f'stroke-width="2.2" stroke-linecap="round"/>')


def _fuse(x, y, color=ACC):
    """Fuse: rounded rect straddling a horizontal rail."""
    return (f'<rect x="{x-20}" y="{y-9}" width="40" height="18" rx="9" '
            f'fill="{TINT}" stroke="{color}" stroke-width="2"/>'
            f'<line x1="{x-14}" y1="{y}" x2="{x+14}" y2="{y}" stroke="{color}" stroke-width="1.6"/>')


def _bead(x, y):
    """Ferrite bead: small filled oval on a horizontal rail."""
    return (f'<rect x="{x-14}" y="{y-8}" width="28" height="16" rx="8" '
            f'fill="{INK}" opacity="0.82"/>')


def _xcap(x, yA, yB, color=INK):
    """Vertical film-cap (X-cap) between two horizontal rails at column x."""
    ym = (yA + yB) / 2
    return (f'<g stroke="{color}" stroke-width="2" stroke-linecap="round">'
            f'<line x1="{x}" y1="{yA}" x2="{x}" y2="{ym-9}"/>'
            f'<line x1="{x-15}" y1="{ym-9}" x2="{x+15}" y2="{ym-9}"/>'
            f'<line x1="{x-15}" y1="{ym+9}" x2="{x+15}" y2="{ym+9}"/>'
            f'<line x1="{x}" y1="{ym+9}" x2="{x}" y2="{yB}"/></g>')


def _ycap(x, y_rail, y_pe, color=CTRL):
    """Y-cap from a rail to the PE rail (drawn in the earth colour)."""
    ym = (y_rail + y_pe) / 2
    return (f'<g stroke="{color}" stroke-width="2" stroke-linecap="round">'
            f'<line x1="{x}" y1="{y_rail}" x2="{x}" y2="{ym-8}"/>'
            f'<line x1="{x-13}" y1="{ym-8}" x2="{x+13}" y2="{ym-8}"/>'
            f'<line x1="{x-13}" y1="{ym+8}" x2="{x+13}" y2="{ym+8}"/>'
            f'<line x1="{x}" y1="{ym+8}" x2="{x}" y2="{y_pe}"/></g>')


def _res_v(x, yA, yB, color=ACC):
    """Vertical resistor (bleeder) between two rails."""
    ym = (yA + yB) / 2
    zig = (f'M{x} {ym-24} L{x-8} {ym-19} L{x+8} {ym-11} L{x-8} {ym-3} '
           f'L{x+8} {ym+5} L{x-8} {ym+13} L{x} {ym+20}')
    return (f'<g stroke="{color}" stroke-width="2" fill="none" stroke-linecap="round">'
            f'<line x1="{x}" y1="{yA}" x2="{x}" y2="{ym-24}"/>'
            f'<path d="{zig}"/>'
            f'<line x1="{x}" y1="{ym+20}" x2="{x}" y2="{yB}"/></g>')


def _mov(x, yA, yB, color=ACC):
    """MOV / varistor between two rails (diagonal-slash box)."""
    ym = (yA + yB) / 2
    return (f'<g stroke="{color}" stroke-width="2" fill="{TINT}" stroke-linecap="round">'
            f'<line x1="{x}" y1="{yA}" x2="{x}" y2="{ym-16}"/>'
            f'<rect x="{x-13}" y="{ym-16}" width="26" height="32" rx="2"/>'
            f'<line x1="{x-9}" y1="{ym+11}" x2="{x+9}" y2="{ym-11}" stroke="{color}"/>'
            f'<line x1="{x}" y1="{ym+16}" x2="{x}" y2="{yB}"/></g>')


def _gdt(x, yA, yB, color=ACC):
    """Gas-discharge tube between two rails (two electrodes in a circle)."""
    ym = (yA + yB) / 2
    return (f'<g stroke="{color}" stroke-width="2" fill="none" stroke-linecap="round">'
            f'<line x1="{x}" y1="{yA}" x2="{x}" y2="{ym-13}"/>'
            f'<circle cx="{x}" cy="{ym}" r="13" fill="{TINT}"/>'
            f'<line x1="{x-7}" y1="{ym-5}" x2="{x+7}" y2="{ym-5}"/>'
            f'<line x1="{x-7}" y1="{ym+5}" x2="{x+7}" y2="{ym+5}"/>'
            f'<line x1="{x}" y1="{ym+13}" x2="{x}" y2="{yB}"/></g>')


def _earth(x, y, color=CTRL):
    """Protective-earth symbol hanging below y."""
    return (f'<g stroke="{color}" stroke-width="2" stroke-linecap="round">'
            f'<line x1="{x}" y1="{y}" x2="{x}" y2="{y+14}"/>'
            f'<line x1="{x-16}" y1="{y+14}" x2="{x+16}" y2="{y+14}"/>'
            f'<line x1="{x-10}" y1="{y+20}" x2="{x+10}" y2="{y+20}"/>'
            f'<line x1="{x-4}" y1="{y+26}" x2="{x+4}" y2="{y+26}"/></g>')


def _cmchoke(x, yL, yN, label, color=INK):
    """Common-mode choke: coupled coils on the L and N rails with a shared core."""
    w = 56
    s = [_coil(x, yL, n=4, w=w, up=12, color=color),
         _coil(x, yN, n=4, w=w, up=-12, color=color)]      # N winding bumps downward
    cx = x + w / 2
    ymid = (yL + yN) / 2
    s.append(f'<line x1="{cx-24}" y1="{ymid-3}" x2="{cx+24}" y2="{ymid-3}" '
             f'stroke="{MUTED}" stroke-width="1.2"/>')
    s.append(f'<line x1="{cx-24}" y1="{ymid+3}" x2="{cx+24}" y2="{ymid+3}" '
             f'stroke="{MUTED}" stroke-width="1.2"/>')           # core hairlines
    s.append(_dots([(x + 3, yL - 15), (x + 3, yN + 15)], fill=color, r=3.0))  # phasing dots
    return "".join(s), x + w


def _header(title, subtitle, head_h):
    return (f'<rect x="0" y="0" width="{W}" height="{head_h}" fill="{INK}"/>'
            + _t(24, 30, title, size=15, fill="#ffffff", spacing="1")
            + _t(W - 24, 30, subtitle, size=12, weight="400",
                 fill="#9aa3b5", anchor="end", family=MONO, spacing="0.5"))


def _legend(y):
    return (f'<line x1="52" y1="{y}" x2="88" y2="{y}" stroke="{INK}" stroke-width="2.4"/>'
            + _t(98, y + 5, "LINE / NEUTRAL (power)", size=12, weight="500", fill=MUTED)
            + f'<line x1="300" y1="{y}" x2="336" y2="{y}" stroke="{CTRL}" stroke-width="2.4"/>'
            + _t(346, y + 5, "PROTECTIVE EARTH / Y-cap", size=12, weight="500", fill=MUTED)
            + f'<line x1="560" y1="{y}" x2="596" y2="{y}" stroke="{ACC}" stroke-width="2.4"/>'
            + _t(606, y + 5, "PROTECTION (fuse / MOV / GDT / bleeder)", size=12,
                 weight="500", fill=MUTED))


# --- as-built topology (designer's schematic) ------------------------------
def _asbuilt_body():
    yL, yPE, yN = 150, 300, 450
    x0, x1 = 150, 1180
    p = []
    # three rails
    p.append(f'<g stroke="{INK}" stroke-width="2" stroke-linecap="round">'
             f'<line x1="{x0}" y1="{yL}" x2="{x1}" y2="{yL}"/>'
             f'<line x1="{x0}" y1="{yN}" x2="{x1}" y2="{yN}"/></g>')
    p.append(f'<line x1="{x0}" y1="{yPE}" x2="{x1}" y2="{yPE}" stroke="{CTRL}" '
             f'stroke-width="2" stroke-linecap="round"/>')

    # input terminal block TB1 (L / PE / N)
    p.append(f'<rect x="60" y="128" width="70" height="344" rx="4" fill="{TINT}" '
             f'stroke="{INK}" stroke-width="1.6"/>')
    p.append(_t(95, 120, "TB1", size=13, fill=MUTED, anchor="middle"))
    for yy, lab, pin in ((yL, "L", "1"), (yPE, "PE", "2"), (yN, "N", "3")):
        p.append(f'<line x1="130" y1="{yy}" x2="{x0}" y2="{yy}" stroke="{INK if lab!="PE" else CTRL}" stroke-width="2"/>')
        p.append(_t(78, yy + 5, lab, size=13, family=MONO, anchor="middle"))
        p.append(_t(118, yy - 8, pin, size=10, family=MONO, fill=MUTED, anchor="middle"))

    def label(x, y, s, fill=INK, dy=0):
        p.append(_t(x, y + dy, s, size=12, family=MONO, fill=fill, anchor="middle"))

    # ---- input X-caps C1/C2 across L-N
    p.append(_xcap(185, yL, yN)); label(185, 118, "C1")
    p.append(_xcap(215, yL, yN)); label(215, 482, "C2", dy=6)
    # ---- fuses F1 (line), F2 (neutral)
    p.append(_fuse(255, yL)); label(255, 128, "F1", fill=ACC)
    p.append(_fuse(255, yN)); label(255, 476, "F2", fill=ACC)
    # ---- differential MOV1 (L-N)
    p.append(_mov(300, yL, yN)); label(322, 300, "MOV1", fill=ACC)
    # ---- CM surge to earth: MOV2+GDT2 (L-PE), MOV3+GDT3 (N-PE)
    p.append(_mov(350, yL, yPE)); label(350, 210, "MOV2", fill=ACC)
    p.append(_gdt(390, yL, yPE)); label(390, 210, "GDT2", fill=ACC)
    p.append(_mov(350, yN, yPE)); label(350, 392, "MOV3", fill=ACC)
    p.append(_gdt(390, yN, yPE)); label(390, 392, "GDT3", fill=ACC)
    # ---- bleeders R1/R2 + GDT1 (L-N)
    p.append(_res_v(435, yL, yN)); label(462, 232, "R1", fill=ACC)
    p.append(_res_v(465, yL, yN)); label(462, 372, "R2", fill=ACC)
    p.append(_gdt(500, yL, yN)); label(522, 300, "GDT1", fill=ACC)
    # ---- X-cap C3
    p.append(_xcap(540, yL, yN)); label(540, 118, "C3")

    # ---- CM choke L1
    g, xe = _cmchoke(590, yL, yN, "L1"); p.append(g); label(618, 128, "L1")
    # ---- X-cap C5 + Y-caps C6/C7 to PE
    p.append(_xcap(680, yL, yN)); label(680, 118, "C5")
    p.append(_ycap(715, yL, yPE)); label(715, 218, "C6", fill=CTRL)
    p.append(_ycap(715, yN, yPE)); label(715, 384, "C7", fill=CTRL)
    # ---- ferrite beads FB1/FB2
    p.append(_bead(755, yL)); label(755, 128, "FB1")
    p.append(_bead(755, yN)); label(755, 476, "FB2")

    # ---- CM choke L2
    g, xe = _cmchoke(790, yL, yN, "L2"); p.append(g); label(818, 128, "L2")
    # ---- Y-caps C8/C9 + beads FB3/FB4 + X-cap C10
    p.append(_ycap(880, yL, yPE)); label(880, 218, "C8", fill=CTRL)
    p.append(_ycap(880, yN, yPE)); label(880, 384, "C9", fill=CTRL)
    p.append(_bead(920, yL)); label(920, 128, "FB3")
    p.append(_bead(920, yN)); label(920, 476, "FB4")
    p.append(_xcap(955, yL, yN)); label(955, 118, "C10")

    # ---- CM choke L3
    g, xe = _cmchoke(985, yL, yN, "L3"); p.append(g); label(1013, 128, "L3")
    # ---- output X-caps C11/C12, Y-caps C13/C14, beads FB5/FB6
    p.append(_xcap(1075, yL, yN)); label(1075, 118, "C11/C12")
    p.append(_ycap(1110, yL, yPE)); label(1110, 218, "C13", fill=CTRL)
    p.append(_ycap(1110, yN, yPE)); label(1110, 384, "C14", fill=CTRL)
    p.append(_bead(1150, yL)); label(1150, 128, "FB5")
    p.append(_bead(1150, yN)); label(1150, 476, "FB6")

    # PE to chassis (CHAS2)
    p.append(_earth(x0 - 8, yPE + 0));
    p.append(_t(x0 - 8, yPE + 48, "CHAS2", size=11, family=MONO, fill=CTRL, anchor="middle"))

    # output flags → converter
    p.append(_t(x1 + 4, yL - 8, "to", size=11, fill=MUTED, anchor="end"))
    p.append(_flag(x1 - 10, yL - 14, 54, 26, "L′"))
    p.append(_flag(x1 - 10, yN - 14, 54, 26, "N′"))
    p.append(_t(x1 + 46, yPE + 5, "PFC / converter", size=12, fill=MUTED))
    return "".join(p)


# --- synthesized functional ladder (engine values) -------------------------
def _synth_body(vals):
    v = vals or {}
    yL, yPE, yN = 150, 300, 450
    x0, x1 = 130, 1170
    dm_stages = int(v.get("dm_stages", 1) or 1)
    cm_stages = int(v.get("cm_stages", 1) or 1)
    p = []
    p.append(f'<g stroke="{INK}" stroke-width="2" stroke-linecap="round">'
             f'<line x1="{x0}" y1="{yL}" x2="{x1}" y2="{yL}"/>'
             f'<line x1="{x0}" y1="{yN}" x2="{x1}" y2="{yN}"/></g>')
    p.append(f'<line x1="{x0}" y1="{yPE}" x2="{x1}" y2="{yPE}" stroke="{CTRL}" '
             f'stroke-width="2" stroke-linecap="round"/>')

    def label(x, y, s, fill=INK, size=12, anchor="middle"):
        p.append(_t(x, y, s, size=size, family=MONO, fill=fill, anchor=anchor))

    # mains flags
    p.append(_flag(70, yL - 14, 52, 26, "L"))
    p.append(_flag(70, yN - 14, 52, 26, "N"))
    p.append(_earth(x0 - 2, yPE)); label(x0 - 2, yPE + 48, "PE", CTRL, 11)

    # fuse + input X-cap
    p.append(_fuse(180, yL)); label(180, 128, "F", ACC)
    cx = f"C_X {v['c_x_uf']:.2f} µF" if v.get("c_x_uf") is not None else "C_X"
    p.append(_xcap(240, yL, yN)); label(240, 118, cx)

    # DM stage(s): L_DM on the line rail + series-R-L damping across it
    ldm = f"L_DM {v['l_dm_uh']:.1f} µH" if v.get("l_dm_uh") is not None else "L_DM"
    xdm = 320
    for st in range(max(dm_stages, 1)):
        g_off = xdm + st * 150
        p.append(_coil(g_off, yL, n=4, w=52, up=13)); label(g_off + 26, 118,
                 ldm + (f" ×{dm_stages}" if dm_stages > 1 and st == 0 else "") if st == 0 else "")
        # damping branch R_d + L_d drawn under the DM choke (informative)
    # damping annotation
    rd = v.get("damp_r"); ld = v.get("damp_l_uh")
    if rd is not None:
        dtxt = f"R_d {rd:.2f} Ω" + (f" + L_d {ld:.1f} µH" if ld is not None else "")
        p.append(f'<rect x="{xdm-6}" y="{yL+18}" width="150" height="26" rx="4" '
                 f'fill="{TINT}" stroke="{ACC}" stroke-width="1.4"/>')
        label(xdm + 69, yL + 35, dtxt, ACC, 11)

    # CM choke(s)
    xcm = 620
    lcm = f"L_CM {v['l_cm_mh']:.2f} mH" if v.get("l_cm_mh") is not None else "L_CM"
    for st in range(max(cm_stages, 1)):
        g, xe = _cmchoke(xcm + st * 150, yL, yN, "L_CM")
        p.append(g)
        if st == 0:
            label(xcm + 28, 118, lcm + (f" ×{cm_stages}" if cm_stages > 1 else ""))

    # Y-caps to PE
    xcy = 620 + max(cm_stages, 1) * 150 + 30
    cy = f"C_Y {v['cy_nf_each']:.2f} nF" if v.get("cy_nf_each") is not None else "C_Y"
    p.append(_ycap(xcy, yL, yPE)); label(xcy + 44, (yL + yPE) / 2, cy + " (L-PE)", CTRL, 11, "start")
    p.append(_ycap(xcy, yN, yPE)); label(xcy + 44, (yN + yPE) / 2, cy + " (N-PE)", CTRL, 11, "start")

    # bleeder across the X-cap (report its value)
    rb = v.get("r_bleed_k")
    if rb is not None:
        p.append(_res_v(270, yL, yN)); label(298, 232, f"R_b {rb:.0f} kΩ", ACC, 11, "start")

    # output flags
    p.append(_flag(x1 - 6, yL - 14, 58, 26, "L′"))
    p.append(_flag(x1 - 6, yN - 14, 58, 26, "N′"))
    p.append(_t(x1 + 56, yPE + 5, "to PFC / converter", size=12, fill=MUTED))
    return "".join(p)


# --- public builder --------------------------------------------------------
def build_svg(view: str = "synth",
              vals: dict | None = None,
              show_header: bool = True,
              show_legend: bool = True,
              title: str | None = None,
              subtitle: str | None = None,
              date: str | None = None,
              scale: float = 1.0,
              responsive: bool = False) -> str:
    """Return the EMI-filter schematic as a standalone SVG document string. `responsive=True` emits a
    width:100% SVG (height scales from the viewBox) for inline GUI embedding; the report path keeps the
    fixed pixel size that svglib needs to scale to the page."""
    date = date or _dt.date.today().isoformat()
    if view == "asbuilt":
        title = title or "EMI INPUT FILTER — AS-BUILT TOPOLOGY"
        subtitle = subtitle or "DESIGNER SCHEMATIC (ref-designators)"
        body = _asbuilt_body()
    else:
        title = title or "EMI INPUT FILTER — SYNTHESIZED LADDER"
        subtitle = subtitle or "COMPUTED VALUES (DM + CM stages)"
        body = _synth_body(vals)

    head_h = 46 if show_header else 0
    total_h = H + head_h
    # responsive: width 100%, height auto from the viewBox aspect ratio (no fixed px → no GUI overflow).
    _size = ('width="100%" style="height:auto;display:block;max-width:100%"' if responsive
             else f'width="{int(W*scale)}" height="{int(total_h*scale)}"')
    p = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {total_h}" '
         f'preserveAspectRatio="xMidYMid meet" {_size}>'
         f'<rect width="{W}" height="{total_h}" fill="{PAPER}"/>']
    if show_header:
        p.append(_header(title, subtitle, head_h))
    p.append(f'<g transform="translate(0,{head_h})">')
    p.append(f'<rect x="16" y="16" width="{W-32}" height="{H-32}" fill="none" '
             f'stroke="{RULE}" stroke-width="1.5"/>')
    p.append(body)
    if show_legend:
        p.append(_legend(H - 40))
    p.append("</g></svg>")
    return "".join(p)


def vals_from_result(r: dict) -> dict:
    """Extract synth-ladder annotation values from an EMIResult dict (adapter _native)."""
    linf = (r.get("l_cm") in (None, float("inf"))) or (isinstance(r.get("l_cm"), float)
                                                        and r["l_cm"] != r["l_cm"])
    return {
        "c_x_uf": (r.get("c_x") or 0) * 1e6,
        "l_dm_uh": (r.get("l_dm") or 0) * 1e6,
        "damp_r": r.get("damp_r"),
        "damp_l_uh": (r.get("damp_l") or 0) * 1e6 if r.get("damp_l") else None,
        "l_cm_mh": None if linf else (r.get("l_cm") or 0) * 1e3,
        "cy_nf_each": (r.get("c_y_emi_total") or 0) * 1e9 / 2,
        "r_bleed_k": (r.get("r_bleed_ohm") or 0) / 1e3 if r.get("r_bleed_ohm") else None,
        "dm_stages": r.get("dm_stages", 1),
        "cm_stages": r.get("cm_stages", 1),
    }


# --- output helpers --------------------------------------------------------
def save_svg(path: str = "emi_schematic.svg", **kw) -> str:
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(build_svg(**kw))
    return path


def _cli() -> None:
    ap = argparse.ArgumentParser(description="Render the EMI-filter schematic (both views).")
    ap.add_argument("--out", default="emi_schematic", help="output basename")
    ap.add_argument("--view", default="synth", choices=["synth", "asbuilt"])
    a = ap.parse_args()
    print("wrote", save_svg(f"{a.out}_{a.view}.svg", view=a.view))


if __name__ == "__main__":
    _cli()
