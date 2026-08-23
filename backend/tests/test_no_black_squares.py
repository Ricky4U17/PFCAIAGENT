"""THE DESIGNER'S "BLACK SQUARES" ARE ZAPFDINGBATS 'n'.

PENDING B12/B13. The reports use the base-14 Type 1 fonts — no TTF is ever registered — so any
character outside WinAnsi has to be substituted. ReportLab does that well for a handful (Omega,
less-equal, check mark, ballot X, black star all reach a real Symbol/ZapfDingbats glyph) and
falls through to **ZapfDingbats 'n', a filled black square**, for everything else. That fallback
is the defect the designer kept reporting, and it is silent: the build succeeds, the page count is
right, and only a human looking at the page sees it.

WHY THE ORIGINAL SCAN COULD NOT WORK. B12 proposed flagging any `&#NNNN;` whose codepoint is
>= 256, not cp1252-encodable, and absent from `paraparser.greeks`. Measured against reality that
predicate is wrong in both directions:

    &#8486;  OHM SIGN         not in greeks  -> the proposed scan FLAGS it   -> actually renders
    U+0394   DELTA            maps to 'Delta' -> Adobe glyph list says U+2206, so a naive
                                                 codepoint comparison flags it -> actually renders
    U+2502   BOX DRAWINGS |   would not have been looked at at all           -> BLACK SQUARE on
                                                                                every page footer

So the predicate here is not a table lookup. It RENDERS the character and reads the result back:
if the extracted text contains U+25A0, that is the ZapfDingbats fallback and the character is
unusable. No glyph lists, no encoding rules, no maintenance as ReportLab changes.

TWO LAYERS, because neither alone is enough:
  * `test_the_built_report_has_no_black_squares` (in test_regression.TestCombinedReport) covers the
    document that actually ships, with zero false positives — but only the branches this design
    takes. It read ZERO the whole time the footers below were broken.
  * this file scans the SOURCE of every report builder, which reaches the conditional branches a
    single build never exercises. Three of the four defects found at C252 were exactly that:
    "Review winding approach" (fires only when Ku > 0.65), "Negative clearance" (only when the
    bore overfills), and `_sct()`'s exponents (only outside 1e-3..1e4).
"""
import io
import pathlib
import re

import pytest

_MB = pathlib.Path(__file__).resolve().parents[1] / "app" / "mode_b"

# Modules that build a PDF. A character in any other module is a parsing constant or a log line.
_BUILDERS = {
    "doc_report_builder.py", "report_steps1_8.py", "report_semiconductor.py",
    "report_inputprotection.py", "report_step9.py", "appendices.py", "schematics.py",
    "generate_full_report.py", "generate_report.py", "generate_step16.py",
    "generate_steps13_14.py", "generate_step15.py", "generate_combined_report.py",
}

# (file, codepoint) pairs that are NOT report prose. Keep this list short and give every entry a
# reason — an allowlist is how a real defect gets waved through.
_ALLOW: set = set()

_cache: dict = {}


def _is_black_square(ch):
    """Render the character and read it back. The rendered page is the only evidence."""
    if ch in _cache:
        return _cache[ch]
    from pypdf import PdfReader
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate
    buf = io.BytesIO()
    SimpleDocTemplate(buf).build([Paragraph("X" + ch + "X", getSampleStyleSheet()["BodyText"])])
    text = PdfReader(io.BytesIO(buf.getvalue())).pages[0].extract_text() or ""
    _cache[ch] = ("■" in text) and ch != "■"
    return _cache[ch]


def test_the_detector_agrees_with_the_known_cases():
    """If this drifts, every other assertion here is worthless."""
    for cp, why in ((0x2011, "non-breaking hyphen — one of the two the designer originally saw"),
                    (0x25A0, "the black square itself"),
                    (0x2502, "box-drawing bar — was in two page footers until C252"),
                    (0x2080, "subscript zero — 'L0' printed as a box"),
                    (0x2074, "superscript four")):
        if cp == 0x25A0:
            continue
        assert _is_black_square(chr(cp)), f"U+{cp:04X} should be detected as a black square ({why})"
    for cp, why in ((0x03A9, "omega"), (0x2126, "ohm sign"), (0x2264, "less-equal"),
                    (0x00B5, "micro"), (0x0394, "delta"), (0x2713, "check mark"),
                    (0x2717, "ballot X"), (0x2605, "black star")):
        assert not _is_black_square(chr(cp)), (
            f"U+{cp:04X} ({why}) renders correctly — flagging it would send someone off to 'fix' "
            "working text, which is what the original B12 predicate did")


def _offenders():
    out = []
    for path in sorted(_MB.rglob("*.py")):
        if path.name not in _BUILDERS:
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            if line.lstrip().startswith("#"):
                continue
            code = line.split("  #")[0]          # strip trailing comments, keep '#' inside strings
            chars = {chr(int(m.group(1))) for m in re.finditer(r"&#(\d+);", code)
                     if int(m.group(1)) >= 256}
            chars |= {c for c in code if ord(c) >= 256}
            for ch in chars:
                if (path.name, ord(ch)) in _ALLOW:
                    continue
                if _is_black_square(ch):
                    out.append(f"{path.name}:{lineno} U+{ord(ch):04X} in {code.strip()[:70]!r}")
    return out


def test_no_report_builder_emits_a_character_that_renders_as_a_black_square():
    bad = _offenders()
    assert not bad, (
        "these characters have no glyph in the base-14 fonts and print as a filled black square:\n  "
        + "\n  ".join(bad)
        + "\n\nUse <sub>/<sup> markup for subscripts and superscripts, an ASCII equivalent for "
          "box-drawing and dashes, or one of the characters the self-check above proves renders. "
          "If a hit is genuinely not report prose, add (file, codepoint) to _ALLOW with a reason.")
