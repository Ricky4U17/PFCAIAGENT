"""
C220 — which trace is which temperature, and the page a citation prints.
=======================================================================
A per-temperature figure is useless until its traces are named. Fig. 4 of the LVE5060E carries seven
forward-voltage curves and the engine wants exactly two of them — a cold anchor and a hot one — so
"curve 3 of 7, 339 points" is not something a designer can act on.

Proximity does not name them: the labels sit off to one side with a hairline leader, and five of the
seven are nearest to the SAME curve. Order does, and the datasheet's own table settles which end of
the order is the hot one.
"""
import io
import os
import sys
import tempfile
import shutil

import pytest

sys.path.insert(0, os.path.dirname(__file__))

from app.mode_b.semiconductor import curve_extract as CX
from app.mode_b.semiconductor import datasheet_flow as DF
from app.mode_b.semiconductor import parts_store as PS

_LVE = os.path.join(os.path.dirname(__file__), "..", "..", "specs", "Review",
                    "Bridge Rectifier Update", "lve5060e.pdf")


@pytest.fixture(scope="module")
def pdf():
    if not os.path.exists(_LVE):
        pytest.skip("LVE5060E datasheet not available")
    with io.open(_LVE, "rb") as f:
        return f.read()


@pytest.fixture(scope="module")
def figs(pdf):
    return CX.digitise(pdf)["figures"]


@pytest.fixture(scope="module")
def fig4(figs):
    return next(f for f in figs if "Fig. 4" in (f["caption"] or ""))


@pytest.fixture(scope="module")
def profile(pdf):
    d = tempfile.mkdtemp(prefix="figtemp_")
    try:
        mpn = DF.upload(pdf, "bridge", "bridge_rectifier", root=d)["part_number"]
        yield PS.load_profile(mpn, kind="extracted", root=d)
    finally:
        shutil.rmtree(d, ignore_errors=True)


class TestThePagePrintedIsThePageItIsOn:
    def test_page_is_one_based(self, fig4):
        """It carried the loop INDEX under a 1-based name, so every "Fig. 4, page 2" written into a
        confirmed profile pointed one page short of the figure. Fig. 4 is on page 3 of five."""
        assert fig4["page"] == 3
        assert fig4["page_index"] == 2

    def test_the_index_still_indexes(self, pdf, fig4):
        import fitz
        doc = fitz.open(stream=pdf, filetype="pdf")
        page = doc[fig4["page_index"]]
        assert "Fig. 4" in page.get_text()
        assert "Fig. 4" not in doc[fig4["page"] - 2].get_text()      # the page it used to name


class TestAnAnnotationLeaderIsNotACurve:
    def test_fig4_offers_seven_traces_not_nine(self, fig4):
        """Seven temperatures are plotted. The other two "curves" were the hairline leaders drawn
        from a label to the trace it names."""
        assert len(fig4["curves"]) == 7

    def test_what_was_dropped_was_two_point_and_black(self, pdf, fig4):
        for c in fig4["curves"]:
            assert c["n_points"] > 2 or (c["color"] and any(v >= 0.15 for v in c["color"]))

    def test_a_single_segment_coloured_trace_is_kept(self, figs):
        """Fig. 3's power-loss lines are genuinely one straight segment each — the filter must key
        on hairline BLACK, not on straightness, or it throws real data away."""
        f3 = next(f for f in figs if "Fig. 3" in (f["caption"] or ""))
        assert len(f3["curves"]) >= 5


class TestTheTemperaturesAreRead:
    def test_all_seven_labels(self, fig4):
        assert [d["T_j"] for d in fig4["temperatures"]] == [-40, 25, 75, 100, 125, 150, 175]

    def test_a_single_condition_note_is_not_a_legend(self, figs):
        """Fig. 6 states "T_J = 25 °C" as a measurement CONDITION, not as a trace label. Reading it
        is right; what must not happen is a one-entry legend being matched to a family."""
        f6 = next(f for f in figs if "Fig. 6" in (f["caption"] or ""))
        assert [d["T_j"] for d in f6["temperatures"]] == [25.0]


class TestNamingTheTraces:
    def test_verified_against_the_datasheets_own_table(self, pdf, profile):
        """The table gives V_F at 25 A for 25 °C and 125 °C. Those two points decide both the
        direction and whether the whole assignment is believable."""
        p = next(q for q in DF.figure_proposals(pdf, profile)["proposals"]
                 if q["key"] == "V_F_vs_IF")
        a = p["assignment"]
        assert a["ok"] and a["verified"]
        assert a["rises_with_temperature"] is False          # a forward drop FALLS as Tj rises
        assert a["worst_anchor_error_pct"] < 2.0
        assert sorted(c["T_j"] for c in p["curves"]) == [-40, 25, 75, 100, 125, 150, 175]

    def test_the_named_traces_reproduce_the_table(self, pdf, profile):
        p = next(q for q in DF.figure_proposals(pdf, profile)["proposals"]
                 if q["key"] == "V_F_vs_IF")
        for tj, expect in ((25.0, 0.89), (125.0, 0.77)):
            c = next(c for c in p["curves"] if c["T_j"] == tj)
            assert abs(CX.value_at(c, 25.0) - expect) / expect < 0.02

    def test_without_a_table_anchor_it_refuses_to_pick_an_end(self, pdf):
        """The ORDER is known and the DIRECTION is not. Returning a mapping anyway is a coin flip
        dressed as a reading, and getting it backwards mislabels the family by its whole span."""
        p = next(q for q in DF.figure_proposals(pdf, None)["proposals"]
                 if q["key"] == "V_F_vs_IF")
        a = p["assignment"]
        assert a["ok"] and not a["verified"]
        assert a["by"] == {} and a["order"]
        assert all(c["T_j"] is None for c in p["curves"])

    def test_reverse_current_has_no_anchor_so_it_refuses_too(self, pdf, profile):
        """Fig. 5's x axis is PERCENT of rated reverse voltage while the table states a condition of
        600 V, so the tabulated point cannot be placed on the plot. Refusing is the right answer."""
        ps = [q for q in DF.figure_proposals(pdf, profile)["proposals"] if q["key"] == "I_rev_vs_VR"]
        if ps:
            assert not ps[0]["assignment"]["verified"]


class TestWhatItBuys:
    def test_a_confirmed_fig4_makes_the_sharing_sweep_real(self, pdf):
        """C218 reported 29.27 W at every split: one tabulated V_F is a FLAT curve, and against a
        flat curve the sharing derate cancels exactly. That was a statement about the DATA. With the
        real V-I curve the cases separate and rise monotonically with imbalance."""
        from test_bridge_datasheet import DESIGN, _THERMAL, _companions
        from app.mode_b.report_semiconductor import _sharing_sweep
        mos, dio = _companions()
        d = tempfile.mkdtemp(prefix="figtemp_")
        try:
            mpn = DF.upload(pdf, "bridge", "bridge_rectifier", root=d)["part_number"]
            prof = PS.load_profile(mpn, kind="extracted", root=d)
            p = next(q for q in DF.figure_proposals(pdf, prof)["proposals"]
                     if q["key"] == "V_F_vs_IF")
            for tj, key in ((25.0, "V_F_vs_IF"), (125.0, "V_F_vs_IF_hot")):
                c = next(c for c in p["curves"] if c["T_j"] == tj)
                DF.confirm_figure(mpn, key, {"x": c["x"], "y": c["y"],
                                             "caption": p["caption"], "page": p["page"]},
                                  {"T_j": tj}, root=d)
            prof2 = PS.load_profile(mpn, kind="confirmed", root=d)
            blk = DF.profile_to_block(prof2, "bridge_rectifier", {**DESIGN, "n_parallel": 2})
            assert len(blk["vf_curve"][0]) > 100 and len(blk["vf_curve_hot"][0]) > 10

            out = _sharing_sweep(DESIGN, mos, dio, blk, _THERMAL)
            shared = [c["P"] for c in out if "single" not in c["case"]]
            assert len(set(round(v, 3) for v in shared)) == len(shared)   # no longer degenerate
            assert shared == sorted(shared)          # worse sharing costs more
            assert (max(shared) - min(shared)) / min(shared) > 0.02
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_the_page_recorded_with_the_curve_is_the_printed_one(self, pdf):
        d = tempfile.mkdtemp(prefix="figtemp_")
        try:
            mpn = DF.upload(pdf, "bridge", "bridge_rectifier", root=d)["part_number"]
            prof = PS.load_profile(mpn, kind="extracted", root=d)
            p = next(q for q in DF.figure_proposals(pdf, prof)["proposals"]
                     if q["key"] == "V_F_vs_IF")
            c = next(c for c in p["curves"] if c["T_j"] == 25.0)
            DF.confirm_figure(mpn, "V_F_vs_IF", {"x": c["x"], "y": c["y"],
                                                 "caption": p["caption"], "page": p["page"]},
                              {"T_j": 25.0}, root=d)
            prof2 = PS.load_profile(mpn, kind="confirmed", root=d)
            e = next(e for pp in prof2["parameters"] if pp["key"] == "V_F_vs_IF"
                     for e in pp["entries"] if e.get("provenance") == "digitised")
            assert e["source"]["page"] == 3
            assert "Fig. 4" in e["source"]["figure"]
        finally:
            shutil.rmtree(d, ignore_errors=True)
