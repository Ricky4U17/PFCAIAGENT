"""THE INDUCTOR LOSS BUDGET MUST AGREE WITH THE CHAPTER THAT OWNS IT.

C233. Chapter 7's Table 7.8b counted inductor COPPER for every interleaved channel but inductor
CORE only once:

    p_lcu = nch * iphi * iphi * dcr
    p_ind = p_lcu + _core_at(vac)          # <- nch missing

On a 2-phase design that dropped an entire inductor's core loss (2.1-3.4 W per point, ~25% of the
inductor column) out of the budget. Nothing looked wrong: the Balance column is a REMAINDER, so it
silently absorbed the missing watts and every row still summed to P_system. The designer found it
by hand, comparing the report against Chapter 3.

WHY NO TEST CAUGHT IT. There was none - the whole 7.8b path had zero coverage. And a remainder
column means internal arithmetic is self-consistent by construction, so checking that the row adds
up proves nothing. The only assertion with teeth is against the OTHER chapter's numbers.

WHY THIS PARSES A BUILT PDF rather than calling a helper. The first draft of this file
re-implemented the budget arithmetic and asserted against that, which would have passed happily
while the shipped report stayed broken - it tests the test. The numbers a reviewer disputes are the
ones ON THE PAGE, so the page is what gets read. Same reasoning as tests/test_report_numbering.py.

VERIFIED AGAINST THE BUG: reintroducing `p_ind = p_lcu + _core_at(vac)` fails
test_78b_inductor_column_is_nch_times_chapter4 at all nine line points.
"""
import io
import os
import re
import shutil
import tempfile

import pytest

_SPECS = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "specs")
_PARTS = [("mosfet", "sic_mosfet", os.path.join(_SPECS, "Review", "IMZA65R033M2HXKSA1.pdf")),
          ("diode", "sic_schottky", os.path.join(_SPECS, "Review", "PFC Boost Diode",
                                                 "vs-4c16ep07l-m3.pdf")),
          ("bridge", "bridge_rectifier", os.path.join(_SPECS, "Review", "Bridge Rectifier Update",
                                                      "lve5060e.pdf"))]

# Chapter 4 Table 4.2, PER PHASE, as the engine produced it for the designer's 2026-08-19 build.
# Literal on purpose: this file's job is to pin Chapter 7 to Chapter 4's published numbers, so a
# change in either engine that moves them should surface here and be explained rather than absorbed.
CH4_PER_PHASE = {          # Vac: (Pcu_avg_W, Pcore_avg_W, Ptot_W)
    90:  (3.377, 2.132, 5.509),   110: (2.247, 2.667, 4.914),   120: (1.866, 2.892, 4.758),
    132: (1.530, 3.116, 4.646),   180: (2.785, 3.437, 6.222),   200: (2.238, 3.298, 5.536),
    220: (1.871, 3.031, 4.902),   230: (1.704, 2.862, 4.566),   264: (1.344, 2.234, 3.578),
}
NCH = 2


def _cu():
    return {v: t[0] for v, t in CH4_PER_PHASE.items()}


def _core():
    return {v: t[1] for v, t in CH4_PER_PHASE.items()}


def _build(nch=NCH, cu=None, core=None):
    """Build Chapter 7 with all three parts real and a known Chapter-4 handoff in `extra`."""
    import fitz
    from fastapi.testclient import TestClient
    from app.mode_b.semiconductor import parts_store as PS, adapter as AD
    from app.mode_b.report_semiconductor import build_semiconductor_report
    import app.main as main

    design = dict(AD.REFERENCE_DESIGN)
    design.update({"eta": 0.95, "pf": 0.99, "V_GS_drive": 18.0, "R_g_on": 4.7, "R_g_off": 10.0,
                   "R_th_cs": 0.3, "nch": nch, "n_parallel": 2, "dies_per_package": 1})
    extra = {"dcr_mohm": 19.5, "rcs_mohm": 12.0,
             "cu_loss_by_vac": cu if cu is not None else _cu(),
             "core_loss_by_vac": core if core is not None else _core(),
             "core_loss_w": (core or _core())[180]}

    blocks, root = {}, tempfile.mkdtemp()
    orig, PS.DEFAULT_ROOT = PS.DEFAULT_ROOT, root
    try:
        c = TestClient(main.app)
        for kind, cls, path in _PARTS:
            with open(path, "rb") as fh:
                raw = fh.read()
            pn = f"BUDGET_{kind}"
            c.post("/mode-b/semiconductor/datasheet/upload",
                   files={"file": ("d.pdf", io.BytesIO(raw), "application/pdf")},
                   data={"kind": kind, "device_class": cls, "part_number": pn})
            r = c.post("/mode-b/semiconductor/datasheet/confirm",
                       json={"part_number": pn, "kind": kind, "device_class": cls,
                             "edits": {}, "design": design})
            blocks[kind] = r.json()["block"]
        pdf = build_semiconductor_report(design, blocks["mosfet"], blocks["diode"],
                                         blocks["bridge"], AD.REFERENCE_PARTS["thermal"],
                                         extra=extra)
    finally:
        PS.DEFAULT_ROOT = orig
        shutil.rmtree(root, ignore_errors=True)

    doc = fitz.open(stream=pdf, filetype="pdf")
    return "".join(p.get_text() for p in doc)


def _inductor_column(txt):
    """Pull {Vac: inductor_W} out of the rendered Table 7.8b.

    Row shape: '90 V' then Semicond., Inductor, Capacitor, R_CS, Balance, 'NNN.N W'.
    """
    out = {}
    for m in re.finditer(r"^(\d+) V\n([-\d.]+)\n([-\d.]+)\n([-\d.]+)\n([-\d.]+)\n([-\d.]+)\n"
                         r"([\d.]+) W$", txt, re.M):
        out[int(m.group(1))] = float(m.group(3))
    return out


@pytest.fixture(scope="module")
def rendered():
    return _build()


def test_table_78b_actually_rendered(rendered):
    """Guard on the guard: 7.8b is gated on dcr/rcs being present, and a test that silently
    asserts over an empty dict passes forever while checking nothing (the C232 trap)."""
    cols = _inductor_column(rendered)
    assert "System Loss Budget" in rendered, "Table 7.8b did not render - the fixture is wrong"
    assert len(cols) == len(CH4_PER_PHASE), f"parsed {len(cols)} rows, expected {len(CH4_PER_PHASE)}"


def test_78b_inductor_column_is_nch_times_chapter4(rendered):
    """The property the C233 defect broke, asserted against Chapter 4's own totals."""
    cols = _inductor_column(rendered)
    cu, core = _cu(), _core()
    for vac, (_, _, ptot) in CH4_PER_PHASE.items():
        want = NCH * ptot
        assert cols[vac] == pytest.approx(want, abs=0.06), (
            f"{vac} Vac: 7.8b shows {cols[vac]} W, expected {NCH} x Table 4.2 Ptot = {want:.2f} W")
        # and it must equal nch x (cu + core) from the same rows, not a re-derived I^2*DCR
        assert cols[vac] == pytest.approx(NCH * (cu[vac] + core[vac]), abs=0.06)


def test_the_historical_bug_would_be_caught(rendered):
    """The shipped-before arithmetic must be distinguishable from the fix at every point.

    Stated as a contrast because the defect was a wrong SHAPE, not a wrong constant, and a shape is
    what a later edit is most likely to get wrong again.
    """
    cols = _inductor_column(rendered)
    cu, core = _cu(), _core()
    for vac in CH4_PER_PHASE:
        buggy = NCH * cu[vac] + core[vac]        # copper x nch, core x 1
        assert cols[vac] != pytest.approx(buggy, abs=0.05), (
            f"{vac} Vac: rendered value matches the historical bug")


def test_core_scales_with_channel_count():
    """Doubling the channel count doubles the inductor column - both terms, not just copper.

    Each build is compared against its OWN exact expectation rather than against the other: the
    table prints one decimal, so 4.758 renders as '4.8' and twice that is 9.6 while the true
    doubled value renders as '9.5'. Chaining two rounded numbers manufactures a failure that says
    nothing about the code.
    """
    per_phase = {v: CH4_PER_PHASE[v][2] for v in CH4_PER_PHASE}
    for nch in (1, 2):
        cols = _inductor_column(_build(nch=nch))
        for vac, ptot in per_phase.items():
            assert cols[vac] == pytest.approx(nch * ptot, abs=0.06), (
                f"{vac} Vac, N_ch={nch}: got {cols[vac]} W, expected {nch * ptot:.2f} W")
