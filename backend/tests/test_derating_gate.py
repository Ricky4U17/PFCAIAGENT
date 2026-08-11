"""
C221 — the bridge derating gate: is the part ALLOWED to carry this current here?
================================================================================
Section 7.3 has described this check since C218 without computing it. It is not a loss question and
not a junction-temperature question: a bridge can sit comfortably inside its dissipation budget and
its Tj limit while being operated outside the current its vendor permits at that case temperature.

The failure mode this guards against is a silent pass — a part with no derating curve on file
reading as an approved one.
"""
import io
import os
import sys
import shutil
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(__file__))

from test_bridge_datasheet import DESIGN, _THERMAL, _companions

from app.mode_b.semiconductor import database as sdb
from app.mode_b.semiconductor import datasheet_flow as DF
from app.mode_b.semiconductor import parts_store as PS
from app.mode_b.semiconductor.adapter import calculate_semiconductor_losses
from app.mode_b.report_semiconductor import _derating_check

_LVE = os.path.join(os.path.dirname(__file__), "..", "..", "specs", "Review",
                    "Bridge Rectifier Update", "lve5060e.pdf")


@pytest.fixture(scope="module")
def pdf():
    if not os.path.exists(_LVE):
        pytest.skip("LVE5060E datasheet not available")
    with io.open(_LVE, "rb") as f:
        return f.read()


def _worst(block):
    mos, dio = _companions()
    res = calculate_semiconductor_losses(DESIGN, mos, dio, block, _THERMAL, None)
    return max(res["per_point"], key=lambda r: r["P_BRIDGE_total"])


@pytest.fixture(scope="module")
def derated(pdf):
    """The LVE5060E block with its Fig. 1 derating curve confirmed."""
    d = tempfile.mkdtemp(prefix="derate_")
    try:
        mpn = DF.upload(pdf, "bridge", "bridge_rectifier", root=d)["part_number"]
        prof = PS.load_profile(mpn, kind="extracted", root=d)
        p = next(q for q in DF.figure_proposals(pdf, prof)["proposals"]
                 if q["key"] == "I_F_AV_vs_Tc")
        c = p["curves"][0]
        DF.confirm_figure(mpn, "I_F_AV_vs_Tc",
                          {"x": c["x"], "y": c["y"], "caption": p["caption"], "page": p["page"]},
                          {}, root=d)
        blk = DF.profile_to_block(PS.load_profile(mpn, kind="confirmed", root=d),
                                  "bridge_rectifier", {**DESIGN, "n_parallel": 2})
        blk["n_parallel"] = 2
        yield blk
    finally:
        shutil.rmtree(d, ignore_errors=True)


class TestTheRightCurveIsPicked:
    def test_case_temperature_not_ambient(self, pdf):
        """Vendors publish both, side by side, and they differ by nearly an order of magnitude —
        the LVE5060E is rated 50 A against case and 6 A in free air. Matching "temperature" loosely
        would silently take the wrong one."""
        props = DF.figure_proposals(pdf)["proposals"]
        got = [q for q in props if q["key"] == "I_F_AV_vs_Tc"]
        assert len(got) == 1
        assert "case temperature" in got[0]["axes"]["x"].lower()
        assert max(got[0]["curves"][0]["y"]) > 40           # the 50 A curve, not the 6 A one

    def test_the_curve_reaches_the_block(self, derated):
        assert derated["_i_f_av_vs_tc"][0]

    def test_it_travels_as_metadata_not_an_engine_field(self, derated):
        """Underscore-prefixed on purpose: the adapter treats any such key as metadata by
        convention, so it cannot reach Bridge(**params) and raise the way V_RRM did at C218."""
        from app.mode_b.semiconductor.adapter import _clean_block
        from app.mode_b.semiconductor.pfc_loss_model import Bridge
        params, meta = _clean_block(derated)
        assert "_i_f_av_vs_tc" in meta and "_i_f_av_vs_tc" not in params
        Bridge(**params)                                     # must not raise


class TestTheGate:
    def test_no_curve_is_data_missing_not_a_pass(self):
        """The catalogue part has no derating curve. An ungated part must never read as an approved
        one — that is the whole failure this check exists to prevent."""
        br = sdb.to_block(sdb.load("bridge")[0], "bridge")
        br["n_parallel"] = 2
        g = _derating_check(DESIGN, br, _worst(br), _THERMAL)
        assert g["verdict"] == "DATA MISSING"
        assert g["I_allowed_A"] is None
        assert g["I_actual_A"] > 0 and g["T_case_C"] is not None

    def test_a_confirmed_curve_gives_a_verdict(self, derated):
        g = _derating_check(DESIGN, derated, _worst(derated), _THERMAL)
        assert g["verdict"] == "PASS"
        assert g["I_allowed_A"] > g["I_actual_A"]
        assert g["headroom_pct"] > 0

    def test_the_current_is_the_requirements_own_figure(self, derated):
        """Not a second derivation of the same quantity — two expressions for one number is how
        they come to disagree."""
        g = _derating_check(DESIGN, derated, _worst(derated), _THERMAL)
        req = DF.requirements({**DESIGN, "n_parallel": 2}, "bridge")
        assert g["I_actual_A"] == pytest.approx(req["I_per_package"], rel=1e-6)

    def test_case_temperature_is_below_the_junction(self, derated):
        w = _worst(derated)
        g = _derating_check(DESIGN, derated, w, _THERMAL)
        assert g["T_case_C"] < w["Tj_BRIDGE_top"]
        drop = w["Tj_BRIDGE_top"] - g["T_case_C"]
        # P_per_package_W is published rounded, so this checks the PATH, not the last digit
        assert drop == pytest.approx(g["P_per_package_W"] * derated["rth_jc"], rel=1e-2)

    def test_too_hot_for_the_rating_fails(self, derated):
        """On the curve, but past the point where what it allows drops below what the design
        draws."""
        w = dict(_worst(derated))
        w["Tj_BRIDGE_top"] = 175.0                 # ~160 degC case, where the part allows ~6 A
        g = _derating_check(DESIGN, derated, w, _THERMAL)
        assert g["verdict"] == "FAIL"
        assert g["I_allowed_A"] < g["I_actual_A"]

    def test_off_the_end_of_the_curve_fails_rather_than_reporting_no_data(self, derated):
        """Beyond its last published point the part carries no rating at all. That is a FAIL, not a
        missing number — reporting DATA MISSING there would read as "not yet checked"."""
        w = dict(_worst(derated))
        w["Tj_BRIDGE_top"] = 260.0
        g = _derating_check(DESIGN, derated, w, _THERMAL)
        assert g["verdict"] == "FAIL"
        assert g["T_curve_max_C"] == pytest.approx(175.0, abs=1.0)

    def test_no_bridge_is_not_a_verdict(self):
        assert _derating_check(DESIGN, None, None, _THERMAL) is None


class TestItReachesTheReport:
    def test_section_733_renders_and_the_promise_is_retired(self):
        """C218 left an annotation saying the comparison "is stated there once the curve has been
        confirmed". Table 7.3.3 now states it, so that forward reference must be gone or the
        chapter contradicts itself."""
        import fitz
        from app.mode_b.report_semiconductor import build_semiconductor_report
        mos, dio = _companions()
        br = sdb.to_block(sdb.load("bridge")[0], "bridge")
        br["n_parallel"] = 2
        pdf = build_semiconductor_report(DESIGN, mos, dio, br, _THERMAL)
        doc = fitz.open(stream=pdf, filetype="pdf")
        txt = "".join(p.get_text() for p in doc)
        assert "Bridge Derating Check" in txt and "7.3.3" in txt
        assert "is stated there once the curve" not in txt
        assert txt.count(chr(0xfffd)) == 0
        assert "degC" not in txt

    def test_no_part_specific_value_is_written_into_the_prose(self):
        """The description must not carry this part's own numbers — every design gets this chapter.
        The values belong in the table, read from whichever curve was confirmed."""
        src = io.open(os.path.join(os.path.dirname(__file__), "..", "app", "mode_b",
                                   "report_semiconductor.py"), encoding="utf-8").read()
        i = src.find("Bridge Derating Check")
        block = src[i:i + 1400]
        assert "50 A at 50" not in block
