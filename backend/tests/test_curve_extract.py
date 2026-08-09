"""
M7 (C214) — reading the PLOTTED curves off a datasheet.
=======================================================
Everything a table cannot carry has been standing in as a fitted shape: a CONSTANT forward drop
where the datasheet gives V_F at one current per temperature (C210), a Q_c moved to the bus by an
assumed power law (C211), a V^1.5 E_oss through one published point (C208). All of it is printed on
the page.

The plan called this "assisted pixel digitising". These datasheets are VECTOR, so the curve is not
traced but READ — the only real error is in the axes. Which is why every test here is about the
CALIBRATION, and why the strongest ones hold the digitised curve against a number the same datasheet
tabulates: the table and the plot are independent renderings of one measurement.
"""
import io
import os

import pytest

from app.mode_b.semiconductor import curve_extract as CX
from app.mode_b.semiconductor import datasheet_flow as DF

_DIODE = os.path.join(os.path.dirname(__file__), "..", "..", "specs", "Review",
                      "PFC Boost Diode", "vs-3c40cp12l-m3.pdf")


@pytest.fixture(scope="module")
def pdf():
    if not os.path.exists(_DIODE):
        pytest.skip("VS-3C40CP12L-M3 datasheet not available")
    with open(_DIODE, "rb") as f:
        return f.read()


@pytest.fixture(scope="module")
def figures(pdf):
    return CX.digitise(pdf)


def _fig(figures, n):
    return next(f for f in figures["figures"] if f["caption"].startswith(f"Fig. {n} "))


class TestCalibration:
    def test_every_plot_on_the_datasheet_is_found(self, figures):
        """Nine figures are captioned Fig. 1..9. A frame drawn as four LINES counts too — Figs 8
        and 9, the capacitive charge and energy curves, are drawn that way and a rectangle-only
        search could not see them."""
        captioned = [f for f in figures["figures"] if f["caption"].startswith("Fig. ")]
        assert len(captioned) == 9

    def test_the_axis_scales_are_read_not_assumed(self, figures):
        """A log axis read as linear is the single most damaging way to get this wrong, and it is
        decided by the SPACING of the tick labels, not by a guess."""
        assert _fig(figures, 1)["calibration"]["x"]["scale"] == "linear"
        assert _fig(figures, 2)["calibration"]["y"]["scale"] == "log"
        assert _fig(figures, 5)["calibration"]["x"]["scale"] == "log"

    def test_the_calibration_residual_is_the_evidence(self, figures):
        """The fit through the tick labels is the only self-contained evidence that they were
        associated with the right axis. A plot with a second axis on the far side, or a legend full
        of numbers, must produce a bad fit rather than a confident wrong answer."""
        for f in figures["figures"]:
            cal = f["calibration"]
            if cal["ok"]:
                assert cal["x"]["residual"] <= 0.02 and cal["y"]["residual"] <= 0.02

    def test_a_frame_whose_ticks_do_not_fit_is_refused(self, figures):
        """One frame on page 4 is a layout box, not a plot. It must decline rather than invent."""
        bad = [f for f in figures["figures"] if not f["calibration"]["ok"]]
        assert bad and "do not fit" in bad[0]["calibration"]["reason"]

    def test_the_axis_titles_are_recovered(self, figures):
        cal = _fig(figures, 1)["calibration"]
        assert "Forward Voltage" in cal["titles"]["x"]
        assert "Forward Current" in cal["titles"]["y"]


class TestTheCurvesAgreeWithTheTable:
    """The acceptance test for the whole milestone. If the axes were misread — wrong label set,
    linear taken for log, the frame off by a tick — the digitised curve misses the tabulated point.
    """

    def test_the_forward_curve_passes_through_the_tabulated_point(self, figures):
        """The table states V_F = 1.35 V at I_F = 20 A, 25 degC."""
        cc = CX.cross_check(_fig(figures, 1)["curves"], 1.35, 20.0)
        assert cc["checked"] and cc["agrees"]
        assert cc["error_pct"] < 5.0

    def test_the_capacitive_charge_curve_reproduces_the_tabulated_charge(self, figures):
        """Q_c = 107 nC at V_R = 800 V — a different figure, drawn as a FILLED ribbon rather than a
        stroke, on a different pair of axes. Agreement there is independent of the first check."""
        cc = CX.cross_check(_fig(figures, 9)["curves"], 800.0, 107.0)
        assert cc["checked"] and cc["agrees"]
        assert cc["error_pct"] < 3.0

    def test_the_five_forward_curves_order_by_temperature(self, figures):
        """The legend runs -55, 25, 125, 150, 175 degC. This diode has a POSITIVE V_F tempco, so at
        a fixed drop the hotter curve must carry less current — an ordering the extractor never
        sees, and therefore a real check on it."""
        got = [CX.value_at(c, 1.35) for c in _fig(figures, 1)["curves"]]
        got = [g for g in got if g is not None][:5]
        assert got == sorted(got, reverse=True)

    def test_a_disagreeing_curve_is_reported_not_used(self, figures):
        cc = CX.cross_check(_fig(figures, 1)["curves"], 1.35, 60.0)   # nothing carries 60 A there
        assert cc["checked"] and not cc["agrees"]
        assert "disagree" in cc["note"] or "misread" in cc["note"]


class TestItSettlesTheC211Question:
    def test_the_dissipated_share_measured_off_the_page_matches_the_closed_form(self, figures):
        """C211 argued E_dissipated = V*Q_c - E_c = V*Q_c/(2-m), against two external reviews that
        both said to use E_c itself. Q_c AND E_c are separately plotted on this datasheet, so the
        share can now be MEASURED rather than modelled — and the reviewers' version tested."""
        qc = _fig(figures, 9)["curves"][0]
        ec = _fig(figures, 8)["curves"][0]
        v = 393.0                                    # the design's bus
        q = CX.value_at(qc, v) * 1e-9
        e = CX.value_at(ec, v) * 1e-6
        measured = (v * q - e) / (v * q)
        closed_form = 1.0 / (2.0 - 0.4188)           # m fitted from the two capacitance points
        assert measured == pytest.approx(closed_form, rel=0.05)
        # and using E_c directly, as both reviews recommended, is far off in the other direction
        assert (e / (v * q)) < measured * 0.7


class TestProposals:
    def test_figures_are_matched_by_their_axes_not_by_figure_number(self, pdf):
        """"Fig. 1" is a forward-voltage plot on one vendor's datasheet and a surge curve on
        another's. An axis titled "Forward Voltage Drop" is the same plot everywhere."""
        from tests.test_diode_datasheet import VS3C40
        res = DF.figure_proposals(pdf, VS3C40)
        keys = {p["key"] for p in res["proposals"]}
        assert {"V_F_vs_IF", "Q_c_vs_VR", "E_c_vs_VR", "C_j_vs_VR"} <= keys

    def test_each_proposal_carries_its_own_evidence(self, pdf):
        from tests.test_diode_datasheet import VS3C40
        res = DF.figure_proposals(pdf, VS3C40)
        vf = next(p for p in res["proposals"] if p["key"] == "V_F_vs_IF")
        assert vf["cross_check"]["agrees"] and vf["residual"] <= 0.02
        assert "Forward Voltage" in vf["axes"]["x"]

    def test_an_uncheckable_figure_says_so_rather_than_implying_a_pass(self, pdf):
        from tests.test_diode_datasheet import VS3C40
        res = DF.figure_proposals(pdf, VS3C40)
        ec = next(p for p in res["proposals"] if p["key"] == "E_c_vs_VR")
        assert not ec["cross_check"]["checked"]
        assert not ec["cross_check"]["agrees"]        # unchecked is never "agrees"

    def test_a_document_with_no_readable_figures_returns_empty_not_an_error(self):
        res = DF.figure_proposals(b"not a pdf at all")
        assert res["proposals"] == []

    def test_the_figure_renders_for_the_designer_to_confirm_against(self, pdf, figures):
        """The proposal is only ever a proposal: the designer confirms it against what is printed,
        so the image is part of the contract."""
        import fitz
        doc = fitz.open(stream=pdf, filetype="pdf")
        f = _fig(figures, 1)
        png = CX.render(doc[f["page"]], tuple(f["frame"]))
        assert png[:8] == b"\x89PNG\r\n\x1a\n" and len(png) > 5000


class TestConfirmingACurveReachesTheEngine:
    """M7 part 2. A proposal is nothing until the designer accepts it against the plot; once
    accepted it must actually replace the fitted shape it was proposed for."""

    @pytest.fixture
    def store(self):
        import shutil, tempfile
        from app.mode_b.semiconductor import parts_store as PS
        from tests.test_diode_datasheet import VS3C40
        d = tempfile.mkdtemp(prefix="m7_")
        PS.write_extracted("VS-3C40CP12L-M3", VS3C40, root=d)
        try:
            yield d
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def _accept(self, pdf, store, which=("V_F_vs_IF", "Q_c_vs_VR", "C_j_vs_VR")):
        """Fig. 1 plots five temperatures; the designer assigns the 25 degC curve to the cold slot
        and the 150 degC curve to the hot one. BOTH, because the engine interpolates between them."""
        from tests.test_diode_datasheet import VS3C40
        props = {p["key"]: p for p in DF.figure_proposals(pdf, VS3C40)["proposals"]}
        if "V_F_vs_IF" in which:
            DF.confirm_figure("VS-3C40CP12L-M3", "V_F_vs_IF",
                              props["V_F_vs_IF"]["curves"][1], {"T_j": 25}, root=store)
            DF.confirm_figure("VS-3C40CP12L-M3", "V_F_vs_IF_hot",
                              props["V_F_vs_IF"]["curves"][3], {"T_j": 150}, root=store)
        for k in ("Q_c_vs_VR", "C_j_vs_VR"):
            if k in which:
                DF.confirm_figure("VS-3C40CP12L-M3", k, props[k]["curves"][0], {}, root=store)
        from app.mode_b.semiconductor import parts_store as PS
        return PS.load_profile("VS-3C40CP12L-M3", kind="confirmed", root=store)

    def test_the_proposal_is_emitted_in_the_canonical_orientation(self, pdf):
        """`V_F_vs_IF` is V_F as a function of I_F, so its x is CURRENT — but every vendor plots
        that figure with voltage on the x axis. Emitting the figure's own order put voltage where
        the engine reads current and produced -692 W of conduction loss at -645 degC."""
        from tests.test_diode_datasheet import VS3C40
        props = {p["key"]: p for p in DF.figure_proposals(pdf, VS3C40)["proposals"]}
        vf = props["V_F_vs_IF"]
        assert vf["swapped"] is True
        c = vf["curves"][1]
        assert max(c["x"]) > 20                      # x is current, tens of amps
        assert 0.5 < max(c["y"]) < 5                 # y is the forward drop, volts
        # ...and a figure already in canonical order is NOT swapped
        assert props["Q_c_vs_VR"]["swapped"] is False

    def test_a_transposed_curve_is_refused_rather_than_used(self, store, pdf):
        """The interlock behind the orientation fix: a forward drop of tens of volts is not a
        forward drop, whatever the calibration says."""
        from app.mode_b.semiconductor import parts_store as PS
        from tests.test_diode_datasheet import VS3C40, DESIGN
        props = {p["key"]: p for p in DF.figure_proposals(pdf, VS3C40)["proposals"]}
        bad = DF._swap_axes(props["V_F_vs_IF"]["curves"][1])      # put it back the wrong way
        DF.confirm_figure("VS-3C40CP12L-M3", "V_F_vs_IF", bad, {"T_j": 25}, root=store)
        prof = PS.load_profile("VS-3C40CP12L-M3", kind="confirmed", root=store)
        blk = DF.profile_to_block(prof, "sic_schottky", DESIGN)
        msg = next(c["message"] for c in blk["_checks"] if c["key"] == "V_F_vs_IF")
        assert "TRANSPOSED" in msg
        assert len(blk["vf_curve"][0]) == 1                       # fell back to the table

    def test_digitising_only_one_of_the_temperature_pair_is_flagged(self, store, pdf):
        """Found by this test suite: digitising the cold curve alone recovers 4 % of the conduction
        error, where digitising both recovers 18 %. The engine interpolates between them, so a
        300-point shape paired with a flat tabulated point is neither."""
        from app.mode_b.semiconductor import parts_store as PS
        from tests.test_diode_datasheet import VS3C40, DESIGN
        props = {p["key"]: p for p in DF.figure_proposals(pdf, VS3C40)["proposals"]}
        DF.confirm_figure("VS-3C40CP12L-M3", "V_F_vs_IF",
                          props["V_F_vs_IF"]["curves"][1], {"T_j": 25}, root=store)
        prof = PS.load_profile("VS-3C40CP12L-M3", kind="confirmed", root=store)
        blk = DF.profile_to_block(prof, "sic_schottky", DESIGN)
        msg = next(c["message"] for c in blk["_checks"] if c["key"] == "V_F_vs_IF_hot")
        assert "Only the cold" in msg

    def test_a_confirmed_forward_curve_replaces_the_constant_drop(self, store, pdf):
        """C210 could only give this part a CONSTANT forward drop, because it publishes V_F at one
        current per temperature. The plot gives the shape."""
        from tests.test_diode_datasheet import DESIGN
        prof = self._accept(pdf, store)
        blk = DF.profile_to_block(prof, "sic_schottky", DESIGN)
        xs, ys = blk["vf_curve"]
        assert len(xs) > 100
        assert 0.5 < min(ys) < 1.2 and 2.0 < max(ys) < 3.0
        assert blk["_provenance"]["V_F_vs_IF"] == "digitised"

    def test_the_constant_drop_was_OVERstating_conduction_not_understating_it(self, store, pdf):
        """A correction to what C210 recorded. The constant is the drop at the part's RATED
        current, which a boost diode reaches only at the crest — so holding it across the whole
        line cycle overstates conduction, and only the peak is understated."""
        from app.mode_b.semiconductor import database as sdb
        from app.mode_b.semiconductor.adapter import calculate_semiconductor_losses
        from tests.test_diode_datasheet import VS3C40, DESIGN
        mos = sdb.to_block(sdb.load("mosfet")[0], "mosfet")
        brg = sdb.to_block(sdb.load("bridge")[0], "bridge")
        th = {"t_ambient": 50, "rth_sa": 0.5}
        run = lambda p: calculate_semiconductor_losses(
            DESIGN, mos, DF.profile_to_block(p, "sic_schottky", DESIGN), brg, th, None)["per_point"][0]
        flat = run(VS3C40)
        curved = run(self._accept(pdf, store))
        assert curved["P_D_cond"] < flat["P_D_cond"]
        assert 0.10 < (flat["P_D_cond"] - curved["P_D_cond"]) / flat["P_D_cond"] < 0.30
        assert curved["P_D_cond"] > 0 and curved["Tj_DIODE"] > 0      # the -692 W guard

    def test_q_c_is_read_at_the_bus_instead_of_scaled(self, store, pdf):
        """C211 moved the tabulated Q_c to the bus with a power law. The plot has the value."""
        from tests.test_diode_datasheet import DESIGN
        prof = self._accept(pdf, store, which=("Q_c_vs_VR",))
        blk = DF.profile_to_block(prof, "sic_schottky", DESIGN)
        assert blk["_qc_basis"]["from_curve"] is True
        assert blk["_qc_basis"]["scaled"] is False
        assert blk["qc"] == pytest.approx(73.4e-9, rel=0.05)
        assert blk["_provenance"]["Q_c"] == "digitised"

    def test_the_grading_coefficient_is_fitted_across_the_whole_curve(self, store, pdf):
        """Two tabulated capacitance points give an interpolation between two dots; the plotted
        curve gives a fit."""
        from tests.test_diode_datasheet import DESIGN
        prof = self._accept(pdf, store, which=("C_j_vs_VR",))
        blk = DF.profile_to_block(prof, "sic_schottky", DESIGN)
        assert blk["_cj_basis"]["from_curve"] is True
        assert 0.25 < blk["cj_grading"] < 0.55

    def test_confirming_an_unknown_key_raises(self, store, pdf):
        from tests.test_diode_datasheet import VS3C40
        props = {p["key"]: p for p in DF.figure_proposals(pdf, VS3C40)["proposals"]}
        from app.mode_b.semiconductor.registry import RegistryError
        with pytest.raises(RegistryError):
            DF.confirm_figure("VS-3C40CP12L-M3", "V_F_vs_Invented",
                              props["V_F_vs_IF"]["curves"][0], root=store)
