"""READING A CURVE OFF A BITMAP, AND PROVING IT WITH THE PART'S OWN TABLE.

C276, closing PENDING B19 — the last M7 gap. The Toshiba TRS12E65H publishes its characteristic
curves as 1638x1289 images with no vector paths, so `curve_extract.py` reads nothing from it. That
refusal is correct and `test_a_raster_datasheet_is_refused_rather_than_guessed_at` still asserts it;
this module is the separate, opt-in capability B19 asked for.

WHY THE ANCHORS ARE THE WHOLE TEST. B19 says it plainly: "Do not relax the vector path's
calibration gates" and "the residual is not evidence — only the tabulated point is". On a raster
figure there is not even a tick-label fit to take a residual of, so the ONLY thing that can say the
axes were read correctly is a number the datasheet states independently, in its table, in text.

TRS12E65H section 6, Electrical Characteristics, V_F (pulse measurement):

    I_F =  6 A            typ 1.0  V     (Ta = 25 degC)
    I_F = 12 A            typ 1.2  V,  max 1.35 V
    I_F = 12 A, Ta = 150  typ 1.36 V

Two of those sit on DIFFERENT curves of Fig. 9.1, which is what makes this non-circular: a wrong
axis scale cannot put curve A on 1.2 V and curve B on 1.36 V at the same time. If the assignment
were confirmed with the same anchor that selected it, this file would be checking its own homework.
"""
from __future__ import annotations

import io
import os

import pytest

from app.mode_b.semiconductor import curve_extract as CX
from app.mode_b.semiconductor import raster_curve as RC

_PDF = os.path.join(os.path.dirname(__file__), "..", "..", "specs", "Review", "PFC Boost Diode",
                    "TRS12E65H_datasheet_en_20230411.pdf")
# Fig. 9.1 (I_F - V_F) is the fourth page, and the first plot bitmap on it.
_PAGE = 3
_XREF = 12
# Read off the plot by the designer, which is the point: the tick labels are pixels.
_AXES = {"x": {"min": 0.0, "max": 2.0, "title": "Forward voltage V_F (V)"},
         "y": {"min": 0.0, "max": 12.0, "title": "Forward current I_F (A)"}}


def _bytes():
    if not os.path.exists(_PDF):
        pytest.skip("TRS12E65H datasheet not available")
    with io.open(_PDF, "rb") as f:
        return f.read()


@pytest.fixture(scope="module")
def pdf():
    return _bytes()


@pytest.fixture(scope="module")
def proposal(pdf):
    return RC.digitise_raster(pdf, _PAGE, _XREF, axes=_AXES)


# ── the refusal is still the default ─────────────────────────────────────────

def test_without_axes_it_still_refuses(pdf):
    """The pre-B19 behaviour is what happens unless a designer opts in. `curve_extract` reading
    nothing from this file is CORRECT, and this module must not quietly change that."""
    out = RC.digitise_raster(pdf, _PAGE, _XREF, axes=None)
    assert out["ok"] is False
    assert out["calibration"]["ok"] is False
    assert out["curves"] == []
    assert "bitmap" in out["reason"]


def test_the_vector_path_still_reads_nothing_from_this_file(pdf):
    """Guards the boundary between the two capabilities. If this ever starts returning figures,
    the raster path is being reached by something that should not reach it."""
    figs = CX.digitise(pdf)
    assert not [f for f in figs["figures"] if f["calibration"]["ok"]]


# ── the geometry ─────────────────────────────────────────────────────────────

def test_the_plot_frame_is_found(pdf):
    """Everything downstream is measured from this box, so an error here scales every value."""
    img = next(i for i in RC.figure_images(pdf, _PAGE) if i["xref"] == _XREF)
    frame = RC.find_frame(img["gray"])
    assert frame is not None
    # 1638x1289 image; the plot occupies most of it.
    assert frame["width_px"] > 900 and frame["height_px"] > 800
    assert frame["x_left"] < frame["x_right"] and frame["y_top"] < frame["y_bottom"]


def test_several_curves_are_separated(proposal):
    """Fig. 9.1 draws five temperatures. They cross, and near the origin they collapse into one
    blob, so five is not guaranteed — but one merged track would mean the tracing does nothing."""
    assert proposal["ok"] is True
    assert len(proposal["curves"]) >= 4, (
        f"only {len(proposal['curves'])} curve(s) separated; the family should fan out at high "
        f"current")


# ── the gate ─────────────────────────────────────────────────────────────────

def test_a_traced_curve_agrees_with_the_tabulated_25C_point(proposal):
    """V_F = 1.2 V at I_F = 12 A, Ta = 25 degC, from the part's own table."""
    hits = [c for c in proposal["curves"]
            if (v := RC.value_at(c["points"], 11.9)) is not None and abs(v - 1.2) / 1.2 <= 0.05]
    assert hits, ("no traced curve reaches the tabulated 25 degC point (1.2 V at 12 A) within 5%; "
                  "got " + repr([RC.value_at(c["points"], 11.9) for c in proposal["curves"]]))


def test_a_different_curve_agrees_with_the_tabulated_150C_point(proposal):
    """V_F = 1.36 V at I_F = 12 A, Ta = 150 degC — a SECOND anchor on a DIFFERENT curve.

    This is the assertion that makes the result evidence rather than coincidence. One anchor can be
    hit by a wrong scale that happens to land; two anchors at different values on different curves
    of the same plot cannot both be hit by one wrong scale.
    """
    at12 = {c["index"]: RC.value_at(c["points"], 11.9) for c in proposal["curves"]}
    c25 = [i for i, v in at12.items() if v is not None and abs(v - 1.2) / 1.2 <= 0.05]
    c150 = [i for i, v in at12.items() if v is not None and abs(v - 1.36) / 1.36 <= 0.05]
    assert c150, f"no curve reaches the 150 degC anchor (1.36 V at 12 A); got {at12}"
    assert set(c25) != set(c150), (
        f"the same curve was matched to both the 25 degC and 150 degC anchors ({at12}) — the two "
        f"tabulated points are 13% apart, so one curve satisfying both means the tolerance is "
        f"doing the work, not the tracing")


def test_cross_check_reports_the_anchors_it_was_given(pdf):
    """The proposal must carry its own evidence, like every other M7 proposal."""
    anchors = [{"x": 1.2, "y": 11.9, "label": "V_F at 12 A, 25 degC", "tol_pct": 5.0}]
    out = RC.digitise_raster(pdf, _PAGE, _XREF, axes=_AXES, anchors=anchors)
    agreeing = [c for c in out["curves"] if c["cross_check"]["agrees"]]
    assert agreeing, "no curve agreed with its anchor"
    ev = agreeing[0]["cross_check"]["anchors"][0]
    assert ev["error_pct"] is not None and ev["error_pct"] <= 5.0
    assert ev["label"] == "V_F at 12 A, 25 degC"


def test_a_curve_is_not_extrapolated_past_where_it_was_traced():
    """`value_at` returns None off the end rather than inventing a point. A track that stopped at
    a merge does not know where it went next, and answering anyway is how a digitiser reports a
    number nobody drew."""
    curve = [[1.0, 2.0], [1.1, 6.0], [1.2, 10.0]]
    assert RC.value_at(curve, 6.0) == pytest.approx(1.1, abs=0.02)
    assert RC.value_at(curve, 11.0) is None
    assert RC.value_at(curve, 0.5) is None


def test_a_wrong_axis_range_is_caught_by_the_anchor(pdf):
    """THE POINT OF THE WHOLE GATE. Digitising the same figure against a plausible-but-wrong
    y-axis (0..10 A instead of 0..12 A) produces curves that look perfectly reasonable — smooth,
    monotonic, well separated — and the anchor is what refuses them.
    """
    bad = {"x": _AXES["x"], "y": {"min": 0.0, "max": 10.0}}
    anchors = [{"x": 1.2, "y": 11.9, "label": "V_F at 12 A, 25 degC", "tol_pct": 5.0}]
    out = RC.digitise_raster(pdf, _PAGE, _XREF, axes=bad, anchors=anchors)
    assert out["ok"] is True and out["curves"], "the tracing itself should still succeed"
    assert not [c for c in out["curves"] if c["cross_check"]["agrees"]], (
        "a curve digitised against a wrong axis range still satisfied the tabulated anchor — the "
        "gate is not discriminating")
