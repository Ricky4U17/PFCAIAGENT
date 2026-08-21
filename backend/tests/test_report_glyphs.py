"""NO CHARACTER MAY REACH THE PAGE THAT THE FONT CANNOT DRAW.

C237. The designer reported "black square syntax" through the Parameter column of Table 7.2e. The
cause was one line:

    _k.replace("_", "&#8203;_")        # zero-width space, to let the narrow column wrap

ReportLab's Helvetica has no U+200B glyph, so it drew a notdef BOX for every underscore. The wrap
it was buying was never needed either: the widest key, `dies_per_package`, is 65 pt against a
135 pt column.

WHY THE EXISTING GLYPH CHECK COULD NOT SEE IT. Every build in this session ran a check that counted
U+FFFD and U+25A0 in the extracted text and reported "zero unrenderable glyphs" while the squares
were on the page. **A notdef box does not extract as a box** - the text layer carries the ORIGINAL
codepoint, so U+200B extracts as U+200B (and, depending on the extractor, as "I"). Counting
replacement characters in extracted text can never detect this class.

"Not encodable in cp1252" is not the test either: the chapter legitimately carries Greek and maths
(Omega, phi, theta, pi, <=, sqrt, integral) which ReportLab renders correctly by substituting the
Symbol font. Flagging those produces noise and teaches people to ignore the check.

SCANNING FOR INVISIBLE CHARACTERS DOES NOT WORK EITHER, and this was measured rather than assumed.
Rendering "R&#8203;_th&#8203;_cs" and extracting it back gives:

    'RI_thI_cs'   ->   U+0052 U+0049 U+005F ...

The notdef glyph maps to the LETTER I. So the zero-width space is not in the extracted text in any
form a scanner could recognise - it has become an ordinary capital I. A Cf/zero-width scan runs
clean on the exact document that shows the black squares. (That scan is kept below as a cheap net
for invisible characters that DO survive extraction, but it cannot catch this defect and is not
what guards it.)

WHAT ACTUALLY WORKS is a ROUND-TRIP: the Parameter column must extract back to exactly the engine's
key strings. Anything inserted for layout - a zero-width space, a soft hyphen, a stray break -
changes the string and fails, whatever it degrades into. Verified by reintroducing the defect: the
round-trip fails naming eight keys; the invisible-character scan passes.
"""
import io
import os
import shutil
import tempfile
import unicodedata

import pytest

_SPECS = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "specs")
_PARTS = [("mosfet", "sic_mosfet", os.path.join(_SPECS, "Review", "IMZA65R033M2HXKSA1.pdf")),
          ("diode", "sic_schottky", os.path.join(_SPECS, "Review", "PFC Boost Diode",
                                                 "vs-4c16ep07l-m3.pdf")),
          ("bridge", "bridge_rectifier", os.path.join(_SPECS, "Review",
                                                      "Bridge Rectifier Update", "lve5060e.pdf"))]

# No visible glyph in a text font. U+200B is the one that shipped; the rest are the same mistake
# wearing different hats, and all of them render as a notdef box in ReportLab's base-14 fonts.
INVISIBLE = {"​", "‌", "‍", "﻿", "­", "⁠", "᠎"}


@pytest.fixture(scope="module")
def built():
    """Chapter 7 with all three parts real. Curves are NOT confirmed here: Table 7.2e renders from
    `_provenance` either way, and skipping the digitiser keeps this file fast."""
    import fitz
    from fastapi.testclient import TestClient
    from app.mode_b.semiconductor import parts_store as PS, adapter as AD
    from app.mode_b.report_semiconductor import build_semiconductor_report
    import app.main as main

    for _, _, path in _PARTS:
        if not os.path.exists(path):
            pytest.skip(f"{os.path.basename(path)} not available")

    design = dict(AD.REFERENCE_DESIGN)
    design.update({"eta": 0.95, "pf": 0.99, "V_GS_drive": 18.0, "R_g_on": 4.7, "R_g_off": 10.0,
                   "R_th_cs": 0.3, "n_parallel": 2, "dies_per_package": 1})
    blocks, root = {}, tempfile.mkdtemp(prefix="glyphs_")
    orig, PS.DEFAULT_ROOT = PS.DEFAULT_ROOT, root
    try:
        c = TestClient(main.app)
        for kind, cls, path in _PARTS:
            with open(path, "rb") as fh:
                raw = fh.read()
            pn = f"GLYPH_{kind}"
            c.post("/mode-b/semiconductor/datasheet/upload",
                   files={"file": ("d.pdf", io.BytesIO(raw), "application/pdf")},
                   data={"kind": kind, "device_class": cls, "part_number": pn})
            blocks[kind] = c.post("/mode-b/semiconductor/datasheet/confirm",
                                  json={"part_number": pn, "kind": kind, "device_class": cls,
                                        "edits": {}, "design": design}).json()["block"]
    finally:
        PS.DEFAULT_ROOT = orig
        shutil.rmtree(root, ignore_errors=True)

    pdf = build_semiconductor_report(design, blocks["mosfet"], blocks["diode"], blocks["bridge"],
                                     AD.REFERENCE_PARTS["thermal"])
    with fitz.open(stream=pdf, filetype="pdf") as doc:
        txt = "".join(p.get_text() for p in doc)
    return {"txt": txt, "blocks": blocks}


def test_no_invisible_characters_reach_the_page(built):
    """The class the black squares belonged to, across the WHOLE chapter."""
    found = {}
    for ch in built["txt"]:
        if ch in INVISIBLE or (unicodedata.category(ch) == "Cf" and ch not in "\r\n"):
            found[f"U+{ord(ch):04X}"] = found.get(f"U+{ord(ch):04X}", 0) + 1
    assert not found, (
        f"invisible/format characters rendered as notdef boxes: {found} — "
        "ReportLab's base-14 fonts have no glyph for these")


def test_table_7_2e_parameter_column_reads_the_canonical_keys(built):
    """Every Parameter cell must be EXACTLY the engine key, character for character.

    A round-trip, so anything inserted for layout - a zero-width space, a soft hyphen, a stray
    break - fails here even if it happened to be invisible in the extracted text.
    """
    txt = built["txt"]
    i = txt.find("Table 7.2e")
    assert i > 0, "Table 7.2e did not render"
    seg = txt[i:i + 6000]

    from app.mode_b.report_semiconductor import _PROV_KEY
    keys = set()
    for blk in built["blocks"].values():
        keys.update((blk or {}).get(_PROV_KEY) or {})
    assert keys, "no provenance keys on any block — fixture is wrong"

    missing = [k for k in sorted(keys) if f"\n{k}\n" not in seg]
    assert not missing, (
        f"Parameter cells do not match their canonical keys: {missing[:8]} — "
        "something is being inserted into the key for layout")


def test_a_notdef_glyph_extracts_as_a_letter_not_as_itself():
    """The measurement the file's reasoning rests on, pinned so it cannot rot.

    If a future ReportLab or PyMuPDF starts round-tripping U+200B faithfully, this fails and the
    docstring above needs revisiting - at which point the invisible-character scan WOULD become
    able to catch the defect. Until then, only the round-trip guards it.
    """
    import fitz
    from reportlab.platypus import SimpleDocTemplate, Paragraph
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.pagesizes import A4

    buf = io.BytesIO()
    SimpleDocTemplate(buf, pagesize=A4).build(
        [Paragraph("R&#8203;_th&#8203;_cs", getSampleStyleSheet()["BodyText"])])
    with fitz.open(stream=buf.getvalue(), filetype="pdf") as d:
        got = "".join(p.get_text() for p in d).strip()

    assert got != "R_th_cs", "the zero-width space rendered harmlessly — premise changed"
    assert not any(c in INVISIBLE for c in got), (
        f"U+200B now survives extraction as itself ({got!r}) — the invisible-character scan can "
        "now catch this class, and this file's reasoning should be updated")
    assert "I" in got, f"expected the notdef to extract as a letter, got {got!r}"
