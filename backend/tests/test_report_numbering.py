"""NO TWO RENDERED TABLES MAY SHARE A NUMBER — checked on built PDFs, which is the only place it shows.

WHY A BUILT PDF. C230 found "Measured Switching Energy" and "Switching-Energy Anchor" both
numbered 7.4.2b: C225 added the first without noticing C209 already held that number, and both
render once the measured curves are confirmed. It was invisible to `ast.parse`, to the registry
audits and to all 610 tests, because nothing rendered the document and looked. That is the trap
already recorded in SESSION_HANDOFF, and this is the check it asks for.

WHY NOT A SOURCE SCAN. Grepping `data_table(` for repeated numbers produces false positives by
design: `PENDING_ITEMS` B10 lists 13 source-level collisions, and most are if/else pairs — 6.11.6,
8.6a, 9.6 — where two calls share a number and only one branch can ever render. A source scan
would demand they be renumbered for no reason. Only a rendered scan distinguishes "two calls" from
"two tables on the page", which is the thing that actually confuses a reviewer.

THE CONFIGURATION MATTERS. The 7.4.2b clash appeared only with the datasheet-first curves in use,
because the measured-energy table renders solely on that path. A chapter is therefore built BOTH
ways: with catalogue parts (analytic switching) and with a confirmed datasheet part (measured
switching). Testing one would have missed the defect that motivated the file.

NOT COVERED: B10's one genuinely-rendered duplicate, 9.7 in Chapter 9, needs a selected MOV part
to appear; the bare design built here does not reach it. That remains a B10 item.
"""
import collections
import io
import os
import re
import shutil
import tempfile

import pytest

_SPECS = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "specs")
_MOSFET_PDF = os.path.join(_SPECS, "Review", "IMZA65R033M2HXKSA1.pdf")
# All three from REAL vendor PDFs. Catalogue stubs publish no surge ratings and no curves, so
# whole blocks of the chapter never render with them — Section 7.3.1's surge table among them,
# which is how a second duplicate (the bridge worked derivation also numbered 7.3.1) survived the
# first version of this file. A fixture that cannot reach a section cannot police its numbering.
_PARTS = [("mosfet", "sic_mosfet", os.path.join(_SPECS, "Review", "IMZA65R033M2HXKSA1.pdf")),
          ("diode", "sic_schottky", os.path.join(_SPECS, "Review", "PFC Boost Diode",
                                                 "vs-4c16ep07l-m3.pdf")),
          ("bridge", "bridge_rectifier", os.path.join(_SPECS, "Review",
                                                      "Bridge Rectifier Update", "lve5060e.pdf"))]

# TABLES ONLY, and deliberately. A table caption is unambiguous in extracted text because it is
# prefixed by the literal word "Table". A section heading is not: it renders as "8.7 — Title", and
# prose that wraps onto a cross-reference produces the same shape at the start of a line. Both of
# these are ORDINARY PROSE in Chapters 8/9 and a heading regex flags them:
#     "8.7 — with the NTC shorted out, this loop resistance is ..."
#     "9.1-9.2): what surge must be survived, and to which criterion ..."
# A check that cries wolf on running text is a check somebody switches off, so section numbering
# is left to a future style-aware pass over the PDF spans rather than guessed at from plain text.
_TABLE = re.compile(r"^Table\s+([0-9]+[0-9.a-z]*)\s", re.M)


def _text(pdf: bytes) -> str:
    import fitz
    with fitz.open(stream=pdf, filetype="pdf") as doc:
        return "".join(p.get_text() for p in doc)


def _dups(numbers):
    return sorted(n for n, c in collections.Counter(numbers).items() if c > 1)


def _design():
    from app.mode_b.semiconductor import adapter as AD
    d = dict(AD.REFERENCE_DESIGN)
    d.update({"eta": 0.95, "pf": 0.99, "V_GS_drive": 18.0, "R_g_on": 4.7,
              "R_g_off": 10.0, "R_th_cs": 0.3})
    return d


@pytest.fixture(scope="module")
def ch7_catalogue():
    """Chapter 7 with catalogue parts: the analytic switching model."""
    from app.mode_b.semiconductor import adapter as AD
    from app.mode_b.report_semiconductor import build_semiconductor_report
    P = AD.REFERENCE_PARTS
    return _text(build_semiconductor_report(_design(), P["mosfet"], P["diode"],
                                            P["bridge"], P["thermal"]))


@pytest.fixture(scope="module")
def ch7_datasheet():
    """Chapter 7 with all three devices confirmed from their own datasheets and every offered
    curve accepted — the document a designer actually produces, and the only configuration in
    which the surge, derating and per-mechanism evidence blocks all render."""
    from fastapi.testclient import TestClient
    from app.mode_b.semiconductor import adapter as AD, parts_store as PS
    from app.mode_b.report_semiconductor import build_semiconductor_report
    import app.main as main

    for _, _, path in _PARTS:
        if not os.path.exists(path):
            pytest.skip(f"{os.path.basename(path)} not available")

    design = dict(_design())
    design.update({"n_parallel": 2, "dies_per_package": 1})
    blocks = {}
    root = tempfile.mkdtemp(prefix="numbering_")
    orig, PS.DEFAULT_ROOT = PS.DEFAULT_ROOT, root
    try:
        c = TestClient(main.app)
        for kind, cls, path in _PARTS:
            with open(path, "rb") as f:
                raw = f.read()
            pn = f"NUM{kind[:3].upper()}"
            c.post("/mode-b/semiconductor/datasheet/upload",
                   files={"file": ("d.pdf", io.BytesIO(raw), "application/pdf")},
                   data={"kind": kind, "device_class": cls, "part_number": pn})
            for q in c.post("/mode-b/semiconductor/datasheet/figures",
                            files={"file": ("d.pdf", io.BytesIO(raw), "application/pdf")},
                            data={"part_number": pn}).json()["proposals"]:
                cu = q["curves"][(q.get("cross_check") or {}).get("curve_index", 0)]
                c.post("/mode-b/semiconductor/datasheet/figure-confirm",
                       json={"part_number": pn, "key": q["key"],
                             "curve": {"x": cu["x"], "y": cu["y"], "caption": q.get("caption"),
                                       "page": q.get("page"), "frame": q.get("frame")},
                             "conditions": {}})
            blocks[kind] = c.post(
                "/mode-b/semiconductor/datasheet/confirm",
                json={"part_number": pn, "kind": kind, "device_class": cls,
                      "edits": {}, "design": design}).json()["block"]
        assert blocks["mosfet"].get("sw_method") == "esw", "must exercise the measured-curve path"
        assert blocks["bridge"].get("ifsm_A") or blocks["bridge"].get("i2t_A2s"),             "the bridge must publish surge ratings, or Section 7.3.1 never renders"
        return _text(build_semiconductor_report(design, blocks["mosfet"], blocks["diode"],
                                                blocks["bridge"],
                                                AD.REFERENCE_PARTS["thermal"]))
    finally:
        PS.DEFAULT_ROOT = orig
        shutil.rmtree(root, ignore_errors=True)


@pytest.fixture(scope="module")
def ch89():
    from app.mode_b.report_inputprotection import build_inputprotection_report
    return _text(build_inputprotection_report(_design()))


def _check(text, label):
    tables = _TABLE.findall(text)
    # guard on the guard: a "no duplicates" assertion passes trivially over an empty list
    assert len(tables) >= 8, f"{label}: only {len(tables)} tables found — did the build fail?"
    assert not _dups(tables), f"{label}: two tables share a number: {_dups(tables)}"


def test_chapter_7_with_catalogue_parts(ch7_catalogue):
    _check(ch7_catalogue, "Ch7 (analytic)")


def test_chapter_7_with_a_confirmed_datasheet_part(ch7_datasheet):
    """The configuration the C230 duplicate lived in."""
    _check(ch7_datasheet, "Ch7 (measured curves)")


def test_chapters_8_and_9(ch89):
    _check(ch89, "Ch8/9")


def test_the_measured_path_really_renders_both_switching_tables(ch7_datasheet):
    """The two tables that collided must BOTH still appear — renumbering must not have been
    achieved by dropping one of them."""
    tables = _TABLE.findall(ch7_datasheet)
    assert "7.4.2b" in tables, "the measured-energy table is missing"
    assert "7.4.2c" in tables, "the analytic cross-check table is missing"


def test_the_two_configurations_really_differ(ch7_catalogue, ch7_datasheet):
    """If both fixtures produced the same document, the datasheet one is not exercising the
    measured path and this file would be testing one configuration twice."""
    assert "de-bundled" in ch7_datasheet
    assert "7.4.2b" not in _TABLE.findall(ch7_catalogue)
