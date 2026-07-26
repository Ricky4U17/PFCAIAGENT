"""
inrush_schematic.py
-------------------
Generates the "Inrush Limiter - NTC + Relay Bypass" schematic as a vector SVG
(and optionally a high-resolution PNG).

Pure standard library for SVG output - no dependencies.
PNG output is optional and uses cairosvg if it is installed:

    pip install cairosvg

Use from another script / AI tool:

    from inrush_schematic import build_svg, save_svg, save_png

    svg = build_svg(show_pin_numbers=True, show_notes=True, show_title_block=True)
    save_svg("schematic.svg")
    save_png("schematic.png", scale=3)          # needs cairosvg

Command line:

    python inrush_schematic.py --out schematic --png --scale 3 --no-notes
"""

from __future__ import annotations

import argparse
import datetime as _dt

# --- style constants -------------------------------------------------------
INK = "#1a1a2e"        # power path / body text
CTRL = "#4a6fa5"       # coil-drive / control path
MUTED = "#7f8c8d"      # secondary text
RULE = "#c9ced8"       # frame + hairlines
TINT = "#f7f8fb"       # component body fill
FLAG = "#eef1f6"       # net-label fill
PAPER = "#ffffff"

SANS = "'IBM Plex Sans', 'Segoe UI', Arial, sans-serif"
MONO = "'IBM Plex Mono', 'Consolas', monospace"

W, H = 1240, 960       # drawing sheet, user units


def _t(x, y, s, size=16, weight="600", fill=INK, anchor="start",
       family=SANS, spacing=None):
    """One <text> element."""
    ls = f' letter-spacing="{spacing}"' if spacing else ""
    s = (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
    return (f'<text x="{x}" y="{y}" font-family="{family}" font-size="{size}" '
            f'font-weight="{weight}" fill="{fill}" text-anchor="{anchor}"{ls}>{s}</text>')


def _flag(x, y, w, h, label, size=13):
    """Net-label flag (rounded box + centred mono text)."""
    return (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{FLAG}" '
            f'stroke="{CTRL}" stroke-width="1.5" rx="3"/>'
            + _t(x + w / 2, y + h * 0.68, label, size=size, family=MONO,
                 anchor="middle"))


def _dots(pts, fill=INK, r=4.5):
    return (f'<g fill="{fill}">'
            + "".join(f'<circle cx="{x}" cy="{y}" r="{r}"/>' for x, y in pts)
            + "</g>")


# --- the drawing -----------------------------------------------------------
def build_svg(show_pin_numbers: bool = True,
              show_notes: bool = True,
              show_title_block: bool = True,
              show_legend: bool = True,
              show_header: bool = True,
              title: str = "INRUSH LIMITER - NTC + RELAY BYPASS",
              subtitle: str = "AC INPUT STAGE - PFC FRONT END",
              sheet: str = "1 OF 1",
              rev: str = "A",
              date: str | None = None,
              scale: float = 1.0) -> str:
    """Return the schematic as a standalone SVG document string."""
    date = date or _dt.date.today().isoformat()
    head_h = 46 if show_header else 0
    total_h = H + head_h
    p = []

    p.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {total_h}" '
        f'width="{int(W * scale)}" height="{int(total_h * scale)}">'
        f'<rect width="{W}" height="{total_h}" fill="{PAPER}"/>'
    )

    if show_header:                                     # dark title band
        p.append(f'<rect x="0" y="0" width="{W}" height="{head_h}" fill="{INK}"/>')
        p.append(_t(24, 30, title, size=15, fill="#ffffff", spacing="1"))
        p.append(_t(W - 24, 30, subtitle, size=12, weight="400",
                    fill="#9aa3b5", anchor="end", family=MONO, spacing="0.5"))

    p.append(f'<g transform="translate(0,{head_h})">')
    p.append(f'<rect x="16" y="16" width="{W - 32}" height="{H - 32}" fill="none" '
             f'stroke="{RULE}" stroke-width="1.5"/>')

    # ---- power-path wiring
    power = [
        "M104 330 L170 330", "M104 600 L170 600",
        "M260 330 L260 430 L145 430 L145 330 L170 330",     # BR (top) AC strap
        "M215 285 L215 250",
        "M215 375 L215 460 L340 460 L340 690",
        "M260 600 L260 660 L145 660 L145 600 L170 600",     # BR (bottom) AC strap
        "M215 555 L120 555 L120 250", "M215 645 L215 690",
        "M120 250 L600 250", "M215 690 L470 690",           # +DC rail / -VDC rail
        "M470 250 L470 438", "M470 462 L470 706",           # C to ground
        "M520 250 L520 580", "M900 250 L900 690",           # parallel-branch buses
        "M820 250 L900 250",
        "M520 480 L640 480", "M760 480 L900 480",           # RT branch
        "M520 580 L688 580", "M702 580 L900 580",           # C branch
        "M900 690 L1000 690", "M1090 690 L1168 690",        # output through L
    ]
    p.append(f'<g stroke="{INK}" stroke-width="2" fill="none" stroke-linecap="square">'
             + "".join(f'<path d="{d}"/>' for d in power)
             + f'<path d="M170 330 L215 285 L260 330 L215 375 Z" fill="{PAPER}"/>'
             + f'<path d="M170 600 L215 555 L260 600 L215 645 Z" fill="{PAPER}"/>'
             + "</g>")

    # ---- control / coil-drive wiring
    ctrl = ["M480 150 L600 150", "M540 150 L540 60 L598 60", "M652 60 L880 60",
            "M820 150 L880 150 L880 60", "M918 60 L928 60",
            "M992 60 L1028 60", "M1082 60 L1110 60"]
    p.append(f'<g stroke="{CTRL}" stroke-width="2" fill="none" stroke-linecap="square">'
             + "".join(f'<path d="{d}"/>' for d in ctrl) + "</g>")

    # ---- bridge-rectifier internal diode symbols
    p.append(f'<g fill="{INK}" stroke="{INK}" stroke-width="2" stroke-linecap="round">'
             '<path d="M203 348 L227 348 L215 325 Z"/><path d="M201 322 L229 322"/>'
             '<path d="M203 618 L227 618 L215 595 Z"/><path d="M201 592 L229 592"/></g>')

    # ---- capacitor plates + earth symbol
    p.append(f'<g stroke="{INK}" stroke-width="2.4" stroke-linecap="round">'
             '<path d="M444 438 L496 438"/><path d="M444 462 L496 462"/>'
             '<path d="M688 556 L688 604"/><path d="M702 556 L702 604"/>'
             '<path d="M448 706 L492 706"/><path d="M456 715 L484 715"/>'
             '<path d="M464 724 L476 724"/></g>')

    # ---- NTC thermistor
    p.append(f'<g stroke="{INK}" stroke-width="2">'
             f'<rect x="640" y="466" width="120" height="28" fill="{TINT}" rx="3"/>'
             '<path d="M630 506 L764 452" fill="none"/>'
             f'<path d="M764 452 L748 454 L757 464 Z" fill="{INK}"/></g>')

    # ---- resistor + coil-drive diodes
    p.append(f'<g stroke="{CTRL}" stroke-width="2" fill="none">'
             '<path d="M928 60 L936 46 L949 74 L962 46 L975 74 L984 60 L992 60"/></g>')
    p.append(f'<g stroke="{CTRL}" stroke-width="2" fill="{CTRL}" stroke-linecap="round">'
             '<path d="M598 46 L598 74 L634 60 Z"/><path d="M636 44 L636 76"/>'
             '<path d="M634 60 L652 60"/>'
             '<path d="M1028 46 L1028 74 L1064 60 Z"/><path d="M1066 44 L1066 76"/>'
             '<path d="M1064 60 L1082 60"/></g>')

    # ---- output inductor + arrow
    p.append(f'<g stroke="{INK}" stroke-width="2" fill="none"><path d="M1000 690 '
             'C1006 672, 1018 672, 1024 690 C1030 672, 1042 672, 1048 690 '
             'C1054 672, 1066 672, 1072 690 C1076 678, 1084 678, 1090 690"/></g>'
             f'<path d="M1168 690 L1152 682 L1152 698 Z" fill="{INK}"/>')

    # ---- relay: body, coil (control colour), contact (power colour)
    p.append(
        f'<rect x="600" y="90" width="220" height="210" fill="{TINT}" stroke="{INK}" '
        'stroke-width="2" rx="4"/>'
        f'<line x1="600" y1="196" x2="820" y2="196" stroke="{RULE}" stroke-width="1"/>'
        f'<g stroke="{CTRL}" stroke-width="2" fill="none">'
        '<path d="M600 150 L664 150"/>'
        '<path d="M664 150 C670 132, 682 132, 688 150 C694 132, 706 132, 712 150 '
        'C718 132, 730 132, 736 150 C742 132, 754 132, 760 150"/>'
        '<path d="M760 150 L820 150"/></g>'
        f'<g stroke="{INK}" stroke-width="2" fill="none">'
        '<path d="M600 250 L644 250"/><path d="M776 250 L820 250"/>'
        '<path d="M646 250 L776 218"/></g>'
        f'<circle cx="646" cy="250" r="4" fill="{PAPER}" stroke="{INK}" stroke-width="2"/>'
        f'<circle cx="776" cy="250" r="4" fill="{PAPER}" stroke="{INK}" stroke-width="2"/>'
        f'<path d="M710 166 L710 238" stroke="{CTRL}" stroke-width="1.4" '
        'stroke-dasharray="4 4"/>'
    )

    # ---- junction dots
    p.append(_dots([(170, 330), (145, 330), (170, 600), (145, 600), (215, 250),
                    (120, 250), (470, 250), (520, 250), (470, 690), (340, 690),
                    (520, 480), (520, 580), (900, 480), (900, 580), (900, 250)]))
    p.append(_dots([(540, 150), (880, 60)], fill=CTRL))

    # ---- net labels
    p.append(_flag(40, 316, 64, 28, "N", size=14))
    p.append(_flag(40, 586, 64, 28, "L", size=14))
    p.append(_flag(390, 136, 90, 28, "RELAY"))
    p.append(_flag(1110, 46, 86, 28, "VCC"))

    # ---- reference designators
    for x, y, s in ((286, 306, "BR"), (286, 576, "BR"), (506, 432, "C"),
                    (716, 600, "C"), (614, 116, "K")):
        p.append(_t(x, y, s))
    p.append(_t(700, 444, "RT", anchor="middle"))
    p.append(_t(700, 524, "TH \u00b7 NTC", size=14, weight="500",
                fill=CTRL, anchor="middle"))
    p.append(_t(1045, 656, "L", anchor="middle"))
    for x, y, s in ((954, 38, "R"), (618, 38, "D"), (1048, 38, "D")):
        p.append(_t(x, y, s, fill=CTRL, anchor="middle"))
    p.append(_t(470, 752, "-VDC", size=14, family=MONO, anchor="middle"))
    for y, s in ((278, "+"), (402, "\u2212"), (548, "+"), (672, "\u2212")):
        p.append(_t(238, y, s, size=15, fill=CTRL))

    # ---- legend
    if show_legend:
        p.append(f'<line x1="52" y1="790" x2="88" y2="790" stroke="{INK}" stroke-width="2"/>'
                 + _t(98, 795, "POWER PATH", size=12, weight="500", fill=MUTED)
                 + f'<line x1="212" y1="790" x2="248" y2="790" stroke="{CTRL}" stroke-width="2"/>'
                 + _t(258, 795, "COIL DRIVE / CONTROL", size=12, weight="500", fill=MUTED))

    # ---- pin numbers
    if show_pin_numbers:
        pins = [(160, 322, "2", "end"), (270, 322, "3", "start"),
                (222, 282, "1", "start"), (222, 392, "4", "start"),
                (160, 592, "2", "end"), (270, 592, "3", "start"),
                (222, 552, "1", "start"), (222, 662, "4", "start"),
                (592, 142, "\u2212", "end"), (828, 142, "6", "start"),
                (592, 242, "3", "end"), (828, 242, "8", "start"),
                (594, 52, "2", "end"), (656, 52, "1", "start"),
                (1024, 52, "2", "end"), (1086, 52, "1", "start"),
                (922, 52, "1", "end"), (996, 52, "2", "start")]
        p.append("".join(_t(x, y, s, size=11, weight="400", fill=MUTED,
                            anchor=a, family=MONO) for x, y, s, a in pins))

    # ---- notes
    if show_notes:
        notes = [
            "1. RT (NTC) limits inrush at power-up; the K contact shorts it out "
            "once the bulk capacitance is charged.",
            "2. BR AC pins are strapped, using each bridge as a paired-diode "
            "rectifier across N and L.",
            "3. D clamps the K coil flyback; R and D feed the coil from VCC.",
        ]
        p.append(_t(52, 852, "NOTES", size=12, fill=MUTED, spacing="1"))
        for i, n in enumerate(notes):
            p.append(_t(52, 878 + i * 24, n, size=14, weight="400"))

    # ---- title block
    if show_title_block:
        p.append(
            f'<rect x="784" y="796" width="440" height="148" fill="{PAPER}" '
            f'stroke="{INK}" stroke-width="1.5"/>'
            f'<rect x="784" y="796" width="440" height="34" fill="{INK}"/>'
            + _t(800, 819, title, size=13, fill="#ffffff", spacing="1")
            + f'<line x1="784" y1="884" x2="1224" y2="884" stroke="{RULE}" stroke-width="1"/>'
            + f'<line x1="784" y1="914" x2="1224" y2="914" stroke="{RULE}" stroke-width="1"/>'
            + f'<line x1="1004" y1="884" x2="1004" y2="944" stroke="{RULE}" stroke-width="1"/>'
            + _t(800, 862, "AC Input Stage - PFC Front End", size=15)
        )
        for x, y, s in ((800, 905, "SHEET"), (1020, 905, "REV"),
                        (800, 935, "DATE"), (1020, 935, "SCALE")):
            p.append(_t(x, y, s, size=12, weight="400", fill=MUTED, family=MONO))
        for x, y, s in ((1000, 905, sheet), (1210, 905, rev),
                        (1000, 935, date), (1210, 935, "NTS")):
            p.append(_t(x, y, s, size=12, anchor="end", family=MONO))

    p.append("</g></svg>")
    return "".join(p)


# --- output helpers --------------------------------------------------------
def save_svg(path: str = "inrush_schematic.svg", **kw) -> str:
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(build_svg(**kw))
    return path


def save_png(path: str = "inrush_schematic.png", scale: float = 3.0, **kw) -> str:
    """High-resolution PNG. Requires `pip install cairosvg`."""
    try:
        import cairosvg
    except ImportError as exc:                      # pragma: no cover
        raise SystemExit("PNG export needs cairosvg:  pip install cairosvg") from exc
    cairosvg.svg2png(bytestring=build_svg(**kw).encode("utf-8"),
                     write_to=path, scale=scale, background_color="white")
    return path


def _cli() -> None:
    ap = argparse.ArgumentParser(description="Render the NTC + relay inrush schematic.")
    ap.add_argument("--out", default="inrush_schematic", help="output basename")
    ap.add_argument("--png", action="store_true", help="also write a PNG (needs cairosvg)")
    ap.add_argument("--scale", type=float, default=3.0, help="PNG resolution multiplier")
    ap.add_argument("--no-pins", action="store_true")
    ap.add_argument("--no-notes", action="store_true")
    ap.add_argument("--no-title-block", action="store_true")
    ap.add_argument("--no-header", action="store_true")
    ap.add_argument("--rev", default="A")
    ap.add_argument("--date", default=None)
    a = ap.parse_args()

    opts = dict(show_pin_numbers=not a.no_pins,
                show_notes=not a.no_notes,
                show_title_block=not a.no_title_block,
                show_header=not a.no_header,
                rev=a.rev, date=a.date)

    print("wrote", save_svg(a.out + ".svg", **opts))
    if a.png:
        print("wrote", save_png(a.out + ".png", scale=a.scale, **opts))


if __name__ == "__main__":
    _cli()
