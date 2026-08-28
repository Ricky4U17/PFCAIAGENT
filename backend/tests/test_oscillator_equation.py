"""THE OSCILLATOR EQUATION IS ANCHORED IN THE DATASHEET, NOT IN OUR OWN OUTPUT.

C268. Chapter 6 printed `f_SW = 1.2e9 / (R_RI + 3430)` for the FAN9672 and specified 13.7 kOhm for
a 70 kHz design. That resistor runs the part at 58.4 kHz. The form appears in NONE of the four
reference PDFs in `specs/Controller/FAN9672 Reference Documents` — it is not a mis-transcription of
anything we hold. A designer caught it by reading the datasheet.

WHY THE EXISTING GUARD DID NOT. `test_ch6_no_stale_values` built Chapter 6 twice, at 70 and 60 kHz,
and checked that R_RI moved — which it did. But it anchored on `"3430"` and the `17.143 k`
intermediate, artefacts OF THE WRONG FORMULA. It asked whether the number was live, never whether
it was right, so it passed for as long as the wrong equation stayed wrong in a consistent way.
Nothing internal could have caught it either: `fsw_at_selected` is display-only, every downstream
chapter uses the TARGET f_SW, so the design was self-consistent at 70 kHz and only the BOM was
wrong.

So this file does the one thing that would have caught it: it checks our equation against the
VENDOR's own published numbers. When a value comes from a vendor document, the test anchor belongs
in that document.

    FAN9672-D p.6, electrical table   R_RI = 25 kOhm    -> f_OSC 30-34 kHz (typ 32)
    FAN9672-D p.6, electrical table   R_RI = 12.5 kOhm  -> f_OSC 58-66 kHz (typ 62)
    FAN9672-D p.10, note 4            RI range 53.3 k - 10.7 kOhm
    FAN9672-D p.14, eq. 3             f_OSC = 8e8 / R_RI
    AN4165-D p.6, worked example      f_SW = 40 kHz at R_RI = 20 kOhm

The old form gives 42.2 / 75.3 / 51.2 kHz against those three measured points, and maps the 10.7 k
minimum to 84.9 kHz — past the part's own 75 kHz ceiling.
"""
from __future__ import annotations

import pathlib
import re

import pytest

from app.mode_b.step16_steps1_8 import compute_steps_1_8

_GUI = pathlib.Path(__file__).resolve().parents[2] / "frontend" / "public" / "control_design.html"

# (R_RI ohms, f_min Hz, f_max Hz, what published it)
VENDOR_ANCHORS = [
    (25000.0, 30_000.0, 34_000.0, "FAN9672-D p.6 electrical table, test case 1 (typ 32 kHz)"),
    (12500.0, 58_000.0, 66_000.0, "FAN9672-D p.6 electrical table, test case 2 (typ 62 kHz)"),
    (20000.0, 39_500.0, 40_500.0, "AN4165-D p.6 design example, f_SW = 40 kHz"),
]


def _rri_for(fsw):
    """R_RI the engine computes for a target f_SW, through the public entry point."""
    return compute_steps_1_8({"fsw": fsw})["step4"]["rri_calc"]


@pytest.mark.parametrize("rri,f_lo,f_hi,source", VENDOR_ANCHORS,
                         ids=[a[3].split(",")[0] for a in VENDOR_ANCHORS])
def test_the_engine_reproduces_the_vendor_measured_points(rri, f_lo, f_hi, source):
    """Invert the engine at the band edges: the R_RI it wants must bracket the published one."""
    r_at_lo, r_at_hi = _rri_for(f_lo), _rri_for(f_hi)
    lo, hi = min(r_at_lo, r_at_hi), max(r_at_lo, r_at_hi)
    assert lo <= rri <= hi, (
        f"{source}: the vendor measured {rri:.0f} ohm over {f_lo/1e3:.1f}-{f_hi/1e3:.1f} kHz, but "
        f"this engine wants {lo:.0f}-{hi:.0f} ohm across that band. The equation disagrees with "
        "the part.")


def test_the_constant_is_the_datasheet_constant():
    """f_OSC * R_RI is the constant 8e8 (FAN9672-D eq. 3) at every frequency, not just one."""
    for fsw in (18e3, 40e3, 55e3, 70e3, 75e3):
        product = _rri_for(fsw) * fsw
        assert abs(product - 8.0e8) < 1.0, (
            f"at {fsw/1e3:.0f} kHz the equation implies f*R = {product:.4g}, not the datasheet's "
            "8e8 — the oscillator relationship has been changed")


def test_the_discredited_form_is_gone_everywhere():
    """`3430` was in the engine, the report and NINE GUI call sites."""
    root = pathlib.Path(__file__).resolve().parents[2]
    offenders = []
    for rel in ("backend/app/mode_b/step16_steps1_8.py",
                "backend/app/mode_b/report_steps1_8.py",
                "backend/app/mode_b/schematics.py",
                "frontend/public/control_design.html"):
        p = root / rel
        if not p.exists():
            continue
        for n, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            stripped = line.strip()
            # a historical note in a comment is fine; a live expression is not
            if stripped.startswith(("#", "*", "//", "/*")):
                continue
            if "3430" in line or "1.2e9" in line:
                offenders.append(f"{rel}:{n}: {stripped[:90]}")
    assert not offenders, "the pre-C268 oscillator equation is back:\n  " + "\n  ".join(offenders)


def test_the_gui_and_the_engine_use_one_equation():
    """The GUI carried the formula at nine sites; it now has one definition. Keep it that way."""
    if not _GUI.exists():
        pytest.skip("control_design.html not present")
    txt = _GUI.read_text(encoding="utf-8", errors="replace")
    assert "const rriFromFsw=fsw=>8e8/fsw" in txt, \
        "the GUI R_RI helper is missing or no longer uses the datasheet constant"
    assert "fswFromRri=rri=>8e8/rri" in txt, \
        "the GUI f_SW helper is missing or no longer uses the datasheet constant"
    # Every remaining mention of the oscillator maths must go through the helpers. Comments are
    # stripped first: the helper's own comment explains the equation as "f_OSC = 8e8/R_RI", and a
    # scan that cannot tell prose from code flags the documentation it is standing next to.
    code = re.sub(r"/\*.*?\*/", "", txt, flags=re.S)
    code = re.sub(r"(?m)^\s*//.*$", "", code)
    inline = [m for m in re.findall(r"8e8\s*/\s*(\w+)", code) if m not in ("fsw", "rri")]
    assert not inline, (
        f"{len(inline)} inline copies of the oscillator constant are back in the GUI ({inline}) — "
        "they must call rriFromFsw/fswFromRri so there is one definition to correct")
