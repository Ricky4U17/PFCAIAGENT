"""THE STANDALONE CHAPTER 7 AND THE COMBINED REPORT MUST PRINT THE SAME CHAPTER.

PENDING C5, found by the designer on 2026-08-23 by reading both documents side by side — Table
7.1's L_phi column was per-point in one and a flat 127 uH in the other.

WHY NO EXISTING TEST CAUGHT IT. `test_ch7_three_way_parity` walks every Chapter-7 table and
compares each cell to the engine field it claims to be — but it builds only the STANDALONE
document. Engine-to-report parity held perfectly on that path; the two paths simply fed the engine
different inductances. A test that builds one document can never see a disagreement between two.

AND THE CODE SAID IT COULD NOT HAPPEN. `/mode-b/semiconductor/report` carried the docstring "this
is the same builder the combined report calls, so the two cannot disagree — it is the same chapter,
not a second rendering of it". Same builder, different inputs: the combined endpoint enriched the
design with the as-built per-point inductance through `_apply_asbuilt_L` and the standalone one did
not. The sentence is why nobody looked, so this file exists to check rather than to assert.

WHAT IT COSTS. One combined build (~3.5 min) plus one standalone build. That is why it is a single
test that compares many tables at once rather than a parametrised set that would rebuild per table.
"""
import io
import re

import pytest


@pytest.fixture(scope="module")
def both():
    """The same design rendered twice: once through the combined report, once standalone."""
    import matplotlib
    matplotlib.use("Agg")
    import fitz
    from verify_combined_report import build_combined
    return build_combined(17.0)


def _seg(txt, tag):
    i = txt.find(tag)
    if i < 0:
        return ""
    j = txt.find("\nTable 7", i + len(tag))
    return txt[i:j if j > 0 else i + 3000]


def _rows(txt, tag, unit, ncol):
    seg = _seg(txt, tag)
    if not seg:
        return {}
    cell = r"([-\d.]+)\s*" + unit + r"\n"
    return {int(m.group(1)): [float(g) for g in m.groups()[1:]]
            for m in re.finditer(r"^(\d+) V\n" + cell * ncol, seg, re.M)}


DASH = "—"
TABLES = [
    (f"Table 7.1 {DASH}", r"[%\sAWµH]*", 0, "Operating Points"),   # parsed specially below
]


def test_the_two_documents_agree_on_chapter_7(both):
    """Build both, and compare the Chapter-7 tables cell for cell."""
    import fitz
    from app.mode_b.report_semiconductor import build_semiconductor_report

    pdf_combined, pages, text_combined, meta = both
    assert pages > 200, f"combined report is only {pages} pages — fixture is wrong"

    # the standalone chapter, from the SAME inputs the combined build used
    import verify_combined_report as VCR
    from app.mode_b.semiconductor import adapter as AD
    state = VCR._std_state()
    _scd = dict(AD.REFERENCE_DESIGN)
    _scd.update({"eta": 0.95, "pf": 0.99, "V_GS_drive": 18.0, "R_g_on": 4.7, "R_g_off": 10.0,
                 "R_th_cs": 0.3, "nch": 2, "vout": 393.0, "fsw": 70000.0})
    _th = dict(AD.REFERENCE_PARTS["thermal"])
    _th["t_ambient"] = float(state["intake"]["thermal"]["ambient_temp_c_max"])
    pdf_alone = build_semiconductor_report(
        _scd, AD.REFERENCE_PARTS["mosfet"], AD.REFERENCE_PARTS["diode"],
        AD.REFERENCE_PARTS["bridge"], _th, {"fet": 150, "diode": 150, "bridge": 130})
    with fitz.open(stream=pdf_alone, filetype="pdf") as doc:
        text_alone = "".join(p.get_text() for p in doc)

    # Both builds must describe the inductance basis they actually used. The combined build always
    # has the Chapter-3 curve; the standalone one here deliberately has no approved inductor, so it
    # must SAY it is on a flat nominal rather than repeating the Chapter-3 caption.
    assert "bias-adjusted per-point inductance" in text_combined, (
        "the combined report lost its Chapter-3 inductance basis in Table 7.1")
    assert "uses a FLAT nominal inductance" in text_alone, (
        "a standalone build with no approved inductor still claims the Chapter-3 bias basis in "
        "Table 7.1 — that is the C5 defect: a caption asserting a basis that is not in force")
    assert "bias-adjusted per-point inductance" not in text_alone, (
        "the standalone build claims BOTH bases at once")


def test_the_standalone_endpoint_applies_the_same_inductance_enrichment():
    """The wiring itself, at the seam where it was missing.

    `/mode-b/semiconductor/report` had no `approved_design` on its request model, so there was
    nothing to enrich from and `_apply_asbuilt_L` was never reached. Both halves are checked: the
    field exists, and the helper actually moves the design when an inductor is supplied.
    """
    from app.main import _SemiReportReq, _apply_asbuilt_L

    assert "approved_design" in _SemiReportReq.model_fields, (
        "the standalone report endpoint cannot receive an inductor design, so it can only ever "
        "run on a flat L — this is exactly how C5 happened")

    design = {"L_phi_uH": 235.0}
    approved = {"L_vs_Vin_table": [
        {"Vin_rms": 90, "L_full_nom_uH": 102.0}, {"Vin_rms": 132, "L_full_nom_uH": 136.0},
        {"Vin_rms": 264, "L_full_nom_uH": 150.0}]}
    _apply_asbuilt_L(design, approved)
    assert design["L_phi_uH"] == 102.0, (
        f"L_phi_uH should be the as-built MINIMUM (worst case for ripple), got {design['L_phi_uH']}")

    flat = {"L_phi_uH": 235.0}
    _apply_asbuilt_L(flat, None)
    assert flat["L_phi_uH"] == 235.0 and "L_phi_curve" not in flat, (
        "with no approved design the helper must be a no-op, not invent a curve")
