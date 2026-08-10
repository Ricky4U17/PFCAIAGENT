"""
M8-bridge (C218) — the bridge from its datasheet.
=================================================
The last component still selected from the parametric catalogue. Its conduction model needed no new
physics: the engine already integrates the current-dependent forward drop over the line cycle,
doubles it for the two diodes in series at any instant, and derates for imperfect sharing. What it
lacked was datasheet numbers, a requirement of its own, and a way in.
"""
import io
import os

import pytest

from app.mode_b.semiconductor import datasheet_extract as DX
from app.mode_b.semiconductor import datasheet_flow as DF
from app.mode_b.semiconductor.adapter import _clean_block
from app.mode_b.semiconductor.pfc_loss_model import Bridge

DESIGN = {"vin_min": 90, "vin_max": 264, "vout": 393, "fline": 60, "fsw": 65000,
          "L_phi_uH": 235, "nch": 2, "pout_lo": 1700, "pout_hi": 3600, "eta": 0.95,
          "r_input": 0.2, "pf": 0.99, "R_th_cs": 0.5}

_LVE = os.path.join(os.path.dirname(__file__), "..", "..", "specs", "Review",
                    "Bridge Rectifier Update", "lve5060e.pdf")

_THERMAL = {"t_ambient": 50, "rth_sa": 0.5}


@pytest.fixture(scope="module")
def profile():
    if not os.path.exists(_LVE):
        pytest.skip("LVE5060E datasheet not available")
    with io.open(_LVE, "rb") as f:
        p = DX.extract(f.read(), "bridge_rectifier")["profile"]
    p["part_number"] = "LVE5060E-M3/P"
    p["manufacturer"] = "Vishay"
    return p


def _companions():
    from app.mode_b.semiconductor import database as sdb
    return (sdb.to_block(sdb.load("mosfet")[0], "mosfet"),
            sdb.to_block(sdb.load("diode")[0], "diode"))


class TestTheRequirementIsTheBridgesOwn:
    def test_it_blocks_the_line_peak_not_the_bus(self):
        """A bridge sits BEFORE the inductor. Deriving its blocking requirement from the boost bus
        was conservative here only by accident — on a design whose bus is not near the line peak it
        would be wrong, and in either direction."""
        req = DF.requirements(DESIGN, "bridge")
        assert req["V_RRM_min"] == pytest.approx(2 ** 0.5 * 264 * 1.2, rel=1e-3)
        assert "V_DSS_min" not in req

    def test_it_carries_the_rectified_mean_against_an_average_rating(self):
        """Vendors quote I_F(AV) as the bridge's total DC output current, so the rectified mean is
        what it must be compared against. It had been handed the per-channel input PEAK, 22.2 A,
        where the correct figure is 28.3 A — understating by 27 %, the direction that passes an
        under-rated part."""
        from app.mode_b.semiconductor.adapter import build_design_ops
        req = DF.requirements(DESIGN, "bridge")
        _, s2, *_ = build_design_ops(DESIGN)
        iin = float(max(s2["Iin_rms"]))
        assert req["I_rect_avg"] == pytest.approx(0.9003 * iin, rel=1e-3)
        assert req["I_F_AV_min"] == pytest.approx(0.9003 * iin * 1.5, rel=1e-3)
        assert req["I_F_AV_min"] > DF.requirements(DESIGN, "mosfet")["I_D_min"]

    def test_it_states_the_per_package_share(self):
        req = DF.requirements({**DESIGN, "n_parallel": 2}, "bridge")
        assert req["I_per_package"] == pytest.approx(req["I_rect_avg"] / 2, abs=0.01)  # both rounded
        assert "per package" in req["statement"]


class TestTheBlock:
    def test_it_is_built_by_the_bridge_builder_not_the_mosfet_one(self, profile):
        """`profile_to_block` routed Diode to the diode builder and EVERYTHING ELSE to the MOSFET
        one, so a bridge profile was searched for R_DS(on) and gate charge. Nothing had hit it only
        because the bridge had no upload path."""
        blk = DF.profile_to_block(profile, "bridge_rectifier", DESIGN)
        assert blk["_device_class"] == "bridge_rectifier"
        assert "rdson_25" not in blk and "qg" not in blk

    def test_the_engine_dataclass_accepts_it(self, profile):
        """The guard for the failure this milestone actually produced: V_RRM was written under its
        CATALOGUE name `vr`, which is not a Bridge field, and Bridge(**params) refused it. There
        are two external names for a quantity and they are not interchangeable."""
        params, _meta = _clean_block(DF.profile_to_block(profile, "bridge_rectifier", DESIGN))
        assert isinstance(Bridge(**params), Bridge)

    def test_the_datasheet_values_reach_it(self, profile):
        blk = DF.profile_to_block(profile, "bridge_rectifier", DESIGN)
        assert blk["rth_jc"] == pytest.approx(1.2)          # the report had been assuming 1.0
        assert blk["vf_curve"][1][0] == pytest.approx(0.89)
        assert blk["vf_curve_hot"][1][0] == pytest.approx(0.77)
        assert blk["vf_thot"] == pytest.approx(125.0)

    def test_the_surge_figures_travel_as_metadata(self, profile):
        """I_FSM and I2t are Chapter 8's inrush and fuse inputs, not loss parameters. They were
        being extracted and then dropped, because nothing carried them onto the block."""
        blk = DF.profile_to_block(profile, "bridge_rectifier", DESIGN)
        assert blk["ifsm_A"] == pytest.approx(600.0)
        assert blk["i2t_A2s"] == pytest.approx(1490.0)

    def test_an_unnamed_bypass_fet_is_reported_not_defaulted(self, profile):
        blk = DF.profile_to_block(profile, "bridge_rectifier",
                                  {**DESIGN, "bridge_topology": "sync_bottom"})
        msg = next(c["message"] for c in blk["_checks"] if c["key"] == "R_DS_on_bottom")
        assert "no bypass MOSFET has been named" in msg

    def test_parallel_packages_without_a_derate_are_flagged(self, profile):
        blk = DF.profile_to_block(profile, "bridge_rectifier", {**DESIGN, "n_parallel": 2})
        assert any(c["key"] == "share_worst" for c in blk["_checks"])


class TestSharingSensitivity:
    def test_the_sweep_is_a_real_run_of_each_case(self, profile):
        from app.mode_b.report_semiconductor import _sharing_sweep
        mos, dio = _companions()
        blk = DF.profile_to_block(profile, "bridge_rectifier", {**DESIGN, "n_parallel": 2})
        out = _sharing_sweep(DESIGN, mos, dio, blk, _THERMAL)
        assert out and len(out) == 4
        assert all(c["P"] > 0 and c["Tj"] > 0 for c in out)
        single = next(c for c in out if "single" in c["case"])
        assert single["Tj"] > out[0]["Tj"]      # one package carries everything and runs hotter

    def test_a_flat_forward_drop_makes_the_sharing_cases_identical(self, profile):
        """Not a bug, and the report says so. With a single tabulated V_F point the curve is FLAT,
        so V_F(i) is the same whatever the split and the derate cancels — the sensitivity is a
        statement about the DATA until the forward curve is digitised."""
        from app.mode_b.report_semiconductor import _sharing_sweep
        mos, dio = _companions()
        blk = DF.profile_to_block(profile, "bridge_rectifier", {**DESIGN, "n_parallel": 2})
        assert len(blk["vf_curve"][0]) == 1                  # one point: a flat curve
        out = _sharing_sweep(DESIGN, mos, dio, blk, _THERMAL)
        shared = [c["P"] for c in out if "single" not in c["case"]]
        assert max(shared) - min(shared) < 0.05

    def test_a_single_package_has_nothing_to_sweep(self, profile):
        from app.mode_b.report_semiconductor import _sharing_sweep
        mos, dio = _companions()
        blk = DF.profile_to_block(profile, "bridge_rectifier", DESIGN)
        assert _sharing_sweep(DESIGN, mos, dio, blk, _THERMAL) is None
