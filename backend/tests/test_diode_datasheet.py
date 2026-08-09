"""
M8 — the boost diode, from its datasheet.
=========================================
Why this milestone exists: through M0-M4 the MOSFET's own parameters were sharpened until they all
came from its datasheet, and the total moved by 4.3 W. Meanwhile the single largest term in the
chapter — the charge the boost DIODE dumps into the MOSFET at turn-on — never moved at all, because
it is not a MOSFET number. It sat on a catalogue `qrr` that the loader itself marks as estimated,
and it is 48 % of the MOSFET's loss.

The tests below are organised around the one failure that would be worst: `Diode.is_sic` defaults to
True, and the two recovery branches are different physics. A silicon part evaluated as SiC has its
biggest loss term computed by the wrong formula, with no missing value to give it away.
"""
import math

import pytest

from app.mode_b.semiconductor import datasheet_flow as DF
from app.mode_b.semiconductor import manifest as M
from app.mode_b.semiconductor import registry as R
from app.mode_b.semiconductor.adapter import _clean_block
from app.mode_b.semiconductor.pfc_loss_model import Diode

DESIGN = {"vin_min": 90, "vin_max": 264, "vout": 393, "fline": 60, "fsw": 65000,
          "L_phi_uH": 235, "nch": 2, "pout_lo": 1700, "pout_hi": 3600, "eta": 0.95,
          "r_input": 0.2, "pf": 0.99, "R_th_cs": 0.3}


def _e(typ, **cond):
    return {"typ": typ, "conditions": cond, "provenance": "extracted"}


def _prof(name, params):
    return {"part_number": name, "manufacturer": "TestCo",
            "datasheet": {"filename": name + ".pdf", "sha256": "0" * 64},
            "parameters": [{"key": k, "entries": v} for k, v in params.items()]}


SIC = _prof("SIC-TEST", {
    "V_RRM":       [_e(650.0)],
    "I_F_AV":      [_e(20.0, T_c=155)],
    "V_F_vs_IF":   [_e(1.50, I_F=20, T_j=25), _e(1.28, I_F=10, T_j=25),
                    _e(1.95, I_F=20, T_j=175), _e(1.55, I_F=10, T_j=175)],
    "Q_c":         [_e(52e-9, V_R=400)],
    "R_th_jc":     [_e(0.55)],
    "I_rev_vs_Tj": [_e(20e-6, T_j=25), _e(90e-6, T_j=175)],
})

SI = _prof("SI-TEST", {
    "V_RRM":     [_e(600.0)],
    "I_F_AV":    [_e(30.0, T_c=125)],
    "V_F_vs_IF": [_e(1.50, I_F=30, T_j=25), _e(1.30, I_F=30, T_j=125)],
    "r_d":       [_e(0.012)],
    "t_rr":      [_e(45e-9, I_F=30, diF_dt=200, T_j=25)],
    "I_RRM":     [_e(8.0, I_F=30, diF_dt=200, T_j=25)],
    "R_th_jc":   [_e(0.60)],
})


class TestTechnologyIsReadOffTheDatasheet:
    """The sub-tab is a UI default; the datasheet is evidence. Evidence wins, and says so."""

    def test_capacitive_charge_and_no_recovery_charge_means_sic(self):
        t = DF.resolve_technology(SIC, "sic_schottky")
        assert t["is_sic"] is True and t["provenance"] == "derived"
        assert not t["ambiguous"]

    def test_recovery_charge_and_no_capacitive_charge_means_silicon(self):
        t = DF.resolve_technology(SI, "si_diode")
        assert t["is_sic"] is False and t["provenance"] == "derived"

    def test_a_silicon_datasheet_uploaded_under_the_sic_tab_is_still_silicon(self):
        """The default device class for every diode upload is `sic_schottky`. If the tab decided,
        a silicon part would be evaluated by the SiC branch and read a Q_c it never published."""
        blk = DF.profile_to_block(SI, "sic_schottky", DESIGN)
        assert blk["is_sic"] is False
        assert blk["_device_class"] == "si_diode"
        assert blk["_declared_class"] == "sic_schottky"
        assert blk["_technology"]["override"] is True
        msg = next(c["message"] for c in blk["_checks"] if c["key"] == "is_sic")
        assert "uploaded as a SiC Schottky" in msg and "followed the DATASHEET" in msg

    def test_a_sic_datasheet_uploaded_under_the_silicon_tab_is_still_sic(self):
        blk = DF.profile_to_block(SIC, "si_diode", DESIGN)
        assert blk["is_sic"] is True
        assert blk["_device_class"] == "sic_schottky"
        assert any(c["key"] == "is_sic" for c in blk["_checks"])

    def test_no_evidence_falls_back_to_the_tab_and_says_it_is_unverified(self):
        bare = _prof("BARE", {"V_F_vs_IF": [_e(1.5, I_F=10, T_j=25)], "R_th_jc": [_e(0.6)]})
        blk = DF.profile_to_block(bare, "sic_schottky", DESIGN)
        assert blk["_technology"]["ambiguous"] is True
        assert any("could not be confirmed" in c["message"] for c in blk["_checks"])

    def test_the_wrong_branch_cannot_read_a_stale_field(self):
        """A SiC block carries no Q_rr and a silicon block no Q_c. If both were populated, flipping
        `is_sic` would silently pick up a number belonging to the other technology."""
        sic = DF.profile_to_block(SIC, "sic_schottky", DESIGN)
        si = DF.profile_to_block(SI, "si_diode", DESIGN)
        assert "qc" in sic and "qrr" not in sic
        assert "qrr" in si and "qc" not in si


class TestCapacitiveChargeReachesTheBusVoltage:
    """The engine spends 0.5*V_bus*Q_c. Q_c is published at whatever V_R the vendor chose."""

    def test_a_value_published_at_the_bus_voltage_is_not_scaled(self):
        blk = DF.profile_to_block(SIC, "sic_schottky", DESIGN)          # 400 V vs a 393 V bus
        assert blk["qc"] == pytest.approx(52e-9)
        assert blk["_qc_basis"]["scaled"] is False

    def test_a_value_published_elsewhere_is_moved_to_the_bus(self):
        p = _prof("QC600", {**{k: v for k, v in
                               ((q["key"], q["entries"]) for q in SIC["parameters"])},
                            "Q_c": [_e(78e-9, V_R=600)]})
        blk = DF.profile_to_block(p, "sic_schottky", DESIGN)
        basis = blk["_qc_basis"]
        assert basis["scaled"] is True and basis["fitted"] is False
        assert basis["exponent"] == DF.SCHOTTKY_QC_EXPONENT
        # Q ~ V^0.5 for an abrupt junction: 78 nC * sqrt(393/600)
        assert blk["qc"] == pytest.approx(78e-9 * (393 / 600) ** 0.5, rel=1e-6)
        assert blk["qc"] < 78e-9                    # a 600 V figure OVERSTATES a 393 V bus

    def test_two_published_points_replace_the_assumed_exponent_with_the_parts_own(self):
        p = _prof("QC2", {**{k: v for k, v in
                             ((q["key"], q["entries"]) for q in SIC["parameters"])},
                          "Q_c": [_e(40e-9, V_R=200), _e(80e-9, V_R=800)]})
        blk = DF.profile_to_block(p, "sic_schottky", DESIGN)
        basis = blk["_qc_basis"]
        assert basis["fitted"] is True
        # Q doubles as V quadruples -> exponent 0.5 recovered from the part's own numbers
        assert basis["exponent"] == pytest.approx(0.5, abs=1e-6)

    def test_a_missing_capacitive_charge_is_reported_not_defaulted(self):
        p = _prof("NOQC", {"V_RRM": [_e(650.0)], "is_sic": [_e(True)],
                           "V_F_vs_IF": [_e(1.5, I_F=10, T_j=25)], "R_th_jc": [_e(0.6)]})
        blk = DF.profile_to_block(p, "sic_schottky", DESIGN)
        assert "qc" not in blk
        assert any(c["key"] == "Q_c" and c["severity"] == "check" for c in blk["_checks"])


class TestRecoveryChargeForSilicon:
    def test_it_is_reconstructed_from_trr_and_irrm_with_the_assumption_stated(self):
        blk = DF.profile_to_block(SI, "si_diode", DESIGN)
        assert blk["qrr"] == pytest.approx(0.5 * 45e-9 * 8.0)
        basis = blk["_qrr_basis"]
        assert basis["provenance"] == "derived"
        assert "TRIANGULAR" in basis["note"] and "floor" in basis["note"]

    def test_a_published_charge_is_preferred_over_the_reconstruction(self):
        p = _prof("QRR", {**{k: v for k, v in
                             ((q["key"], q["entries"]) for q in SI["parameters"])},
                          "Q_rr": [_e(260e-9, I_F=30, diF_dt=200, T_j=25)]})
        blk = DF.profile_to_block(p, "si_diode", DESIGN)
        assert blk["qrr"] == pytest.approx(260e-9)
        assert blk["_qrr_basis"]["provenance"] == "extracted"

    def test_the_partition_into_the_mosfet_is_declared_as_an_assumption(self):
        """rr_fet_frac scales the largest single term in the chapter and is not a datasheet
        quantity. Silence here is what made it look like a measurement."""
        blk = DF.profile_to_block(SI, "si_diode", DESIGN)
        assert any(c["key"] == "rr_fet_frac" for c in blk["_checks"])
        assert not any(c["key"] == "rr_fet_frac"
                       for c in DF.profile_to_block(SIC, "sic_schottky", DESIGN)["_checks"])

    def test_the_charge_is_not_rescaled_to_the_designs_didt(self):
        """Scaling one published point by an invented shape would look like a correction while
        being a guess — the same call made for the MOSFET's C_rss at M4a."""
        blk = DF.profile_to_block(SI, "si_diode", DESIGN)
        assert blk["qrr"] == pytest.approx(0.5 * 45e-9 * 8.0)
        assert any("di/dt" in c["message"] for c in blk["_checks"] if c["key"] == "Q_rr")

    def test_a_temperature_pair_gives_a_real_tempco(self):
        p = _prof("QRRT", {**{k: v for k, v in
                              ((q["key"], q["entries"]) for q in SI["parameters"])},
                           "Q_rr": [_e(200e-9, T_j=25), _e(300e-9, T_j=125)]})
        blk = DF.profile_to_block(p, "si_diode", DESIGN)
        assert blk["qrr_tco"] == pytest.approx((300 / 200 - 1) / 100, rel=1e-6)


class TestForwardCurve:
    def test_two_points_build_the_curve_directly(self):
        blk = DF.profile_to_block(SIC, "sic_schottky", DESIGN)
        assert blk["vf_curve"] == [[10.0, 20.0], [1.28, 1.50]]
        assert blk["vf_curve_hot"] == [[10.0, 20.0], [1.55, 1.95]]
        assert blk["vf_thot"] == 175.0

    def test_one_point_plus_the_published_slope_is_the_datasheets_own_linear_model(self):
        blk = DF.profile_to_block(SI, "si_diode", DESIGN)
        xs, ys = blk["vf_curve"]
        v0 = 1.50 - 0.012 * 30                       # threshold implied by the datasheet
        assert ys[0] == pytest.approx(v0)
        # exact at the published point, because the model IS the datasheet's
        import numpy as np
        assert float(np.interp(30.0, xs, ys)) == pytest.approx(1.50, rel=1e-9)

    def test_the_series_resistance_is_not_counted_twice(self):
        """The engine's forward model is v(i) = vf_curve(i) + rd*i. Every curve this builder makes
        already carries the slope — from two published points, or from one point plus r_d itself —
        so writing `rd` as well counted the resistive term twice. It cost 12.8 % on the diode's
        conduction loss and nothing looked wrong: both numbers came off the datasheet."""
        blk = DF.profile_to_block(SI, "si_diode", DESIGN)
        xs, ys = blk["vf_curve"]
        slope = (ys[1] - ys[0]) / (xs[1] - xs[0])
        assert slope == pytest.approx(0.012, rel=1e-6)      # the curve carries r_d
        assert "rd" not in blk                              # ...so the engine must not add it again
        assert blk["_r_d_published"] == pytest.approx(0.012)  # but it is still recorded

    def test_r_d_still_reaches_the_engine_when_no_curve_could_be_built(self):
        """The only case where the engine's separate rd term is the right home for it."""
        p = _prof("RDONLY", {"V_RRM": [_e(650.0)], "Q_c": [_e(50e-9, V_R=400)],
                             "r_d": [_e(0.02)], "R_th_jc": [_e(0.6)]})
        blk = DF.profile_to_block(p, "sic_schottky", DESIGN)
        assert "vf_curve" not in blk
        assert blk["rd"] == pytest.approx(0.02)

    def test_one_point_with_no_slope_is_flagged_because_it_understates_the_peak(self):
        p = _prof("FLAT", {"V_RRM": [_e(650.0)], "Q_c": [_e(50e-9, V_R=400)],
                           "V_F_vs_IF": [_e(1.5, I_F=10, T_j=25)], "R_th_jc": [_e(0.6)]})
        blk = DF.profile_to_block(p, "sic_schottky", DESIGN)
        row = next(c for c in blk["_checks"] if c["key"] == "V_F_vs_IF")
        assert row["severity"] == "check"
        assert "CONSTANT" in row["message"]

    def test_two_leakage_points_build_a_real_reverse_current_curve(self):
        blk = DF.profile_to_block(SIC, "sic_schottky", DESIGN)
        assert blk["irev_curve"] == [[25.0, 175.0], [20e-6, 90e-6]]
        assert not any(c["key"] == "I_rev_vs_Tj" for c in blk["_checks"])


class TestRequirement:
    def test_a_diode_is_rated_on_average_current_not_the_input_peak(self):
        """I_F(AV) is an AVERAGE rating and the boost diode carries the OUTPUT current. Comparing
        it against the MOSFET's input peak would demand a part several times larger than needed."""
        req = DF.requirements(DESIGN, "diode")
        iout_ch = 3600 / 393 / 2
        assert req["I_F_AV_min"] == pytest.approx(iout_ch * 1.5, abs=0.05)
        assert req["V_RRM_min"] == pytest.approx(393 * 1.2, abs=0.1)
        # the peak is reported separately rather than folded into an average rating
        assert req["I_F_pk"] > req["I_F_AV_min"]
        assert "V_DSS_min" not in req

    @pytest.mark.parametrize("kind", ["mosfet", "bridge"])
    def test_no_other_kind_is_given_the_diode_requirement(self, kind):
        """A bridge also carries an average current, but it is the INPUT current — this branch
        would hand it a confidently wrong number. It keeps its own until M8-bridge."""
        req = DF.requirements(DESIGN, kind)
        assert "V_DSS_min" in req and "I_F_AV_min" not in req

    def test_a_part_below_the_blocking_margin_is_reported(self):
        p = _prof("LOWV", {"V_RRM": [_e(400.0)], "Q_c": [_e(50e-9, V_R=400)],
                           "V_F_vs_IF": [_e(1.5, I_F=10, T_j=25), _e(1.7, I_F=20, T_j=25)],
                           "R_th_jc": [_e(0.6)]})
        blk = DF.profile_to_block(p, "sic_schottky", DESIGN)
        assert any(c["key"] == "V_RRM" for c in blk["_checks"])


class TestNoNamingDisconnects:
    def test_every_class_declares_only_engine_fields_its_own_dataclass_has(self):
        """The pooled audit unions Mosfet+Diode+Bridge, so a field on ANY of them looks present on
        ALL of them. That hid eleven declarations — n_parallel and share_worst on the diode
        classes, the Q_rr curves on the bridge, `tech` on both — each a TypeError waiting for the
        first builder to write it."""
        assert R.audit_device_classes() == []

    def test_the_pooled_audit_is_still_clean(self):
        assert R.audit_engine_dataclasses() == {"unregistered": [], "orphaned": []}

    @pytest.mark.parametrize("profile,cls", [(SIC, "sic_schottky"), (SI, "si_diode")])
    def test_the_block_constructs_the_engine_dataclass(self, profile, cls):
        params, _meta = _clean_block(DF.profile_to_block(profile, cls, DESIGN))
        d = Diode(**params)                          # raises if any key is not a Diode field
        assert isinstance(d, Diode)

    @pytest.mark.parametrize("profile", [SIC, SI], ids=["sic", "si"])
    def test_validation_uses_the_resolved_class_not_the_tab(self, profile):
        """Both uploaded under the SiC tab; the silicon one must not be audited for a Q_c it
        correctly does not have."""
        blk = DF.profile_to_block(profile, "sic_schottky", DESIGN)
        v = M.validate_block(blk, blk["_device_class"])
        assert v["ok"], v["defaulted"]

    def test_no_underscore_metadata_reaches_the_dataclass(self):
        params, meta = _clean_block(DF.profile_to_block(SIC, "sic_schottky", DESIGN))
        assert not [k for k in params if k.startswith("_")]
        for k in ("_technology", "_qc_basis", "_checks", "_device_class"):
            assert k in meta


class TestItChangesTheAnswer:
    def test_sic_removes_most_of_the_charge_the_diode_dumps_into_the_mosfet(self):
        """The point of the milestone. Same MOSFET, same design, same engine — only the diode's
        technology and its datasheet numbers change."""
        from app.mode_b.semiconductor import database as sdb
        from app.mode_b.semiconductor.adapter import calculate_semiconductor_losses
        mos = sdb.to_block(sdb.load("mosfet")[0], "mosfet")
        brg = sdb.to_block(sdb.load("bridge")[0], "bridge")
        th = {"t_ambient": 50, "rth_sa": 0.5}

        sic = calculate_semiconductor_losses(
            DESIGN, mos, DF.profile_to_block(SIC, "sic_schottky", DESIGN), brg, th, None)
        si = calculate_semiconductor_losses(
            DESIGN, mos, DF.profile_to_block(SI, "si_diode", DESIGN), brg, th, None)

        rr_sic = sic["per_point"][0]["P_FET_rr"]
        rr_si = si["per_point"][0]["P_FET_rr"]
        assert rr_sic > 0 and rr_si > rr_sic * 3      # not a rounding difference
        assert sic["summary"]["Tj_FET_max"] < si["summary"]["Tj_FET_max"]

    def test_the_diode_loss_columns_sum_to_its_total(self):
        """The Results tab shows conduction / switching / leakage beside a total. Until M8 the
        engine exposed no diode leakage key at all, so the columns fell short of the total by
        however much it was — invisible while it was always zero, which it stopped being the moment
        a datasheet supplied a real I_R(T_j) curve."""
        from app.mode_b.semiconductor import database as sdb
        from app.mode_b.semiconductor.adapter import calculate_semiconductor_losses
        res = calculate_semiconductor_losses(
            DESIGN, sdb.to_block(sdb.load("mosfet")[0], "mosfet"),
            DF.profile_to_block(SIC, "sic_schottky", DESIGN),
            sdb.to_block(sdb.load("bridge")[0], "bridge"),
            {"t_ambient": 50, "rth_sa": 0.5}, None)
        for p in res["per_point"]:
            assert (p["P_D_cond"] + p["P_D_sw"] + p["P_D_leak"]
                    == pytest.approx(p["P_DIODE_total"], rel=1e-9))
        assert any(p["P_D_leak"] > 0 for p in res["per_point"])   # a real curve, not a placeholder

    def test_the_engine_trace_carries_the_designs_own_didt(self):
        """So the report can hold the design's commutation rate against the di/dt the datasheet's
        Q_rr was measured at, instead of leaving the reader to assume they match."""
        from app.mode_b.semiconductor import database as sdb
        from app.mode_b.semiconductor.adapter import trace_point
        tr = trace_point(DESIGN, sdb.to_block(sdb.load("mosfet")[0], "mosfet"),
                         DF.profile_to_block(SI, "si_diode", DESIGN),
                         sdb.to_block(sdb.load("bridge")[0], "bridge"),
                         {"t_ambient": 50, "rth_sa": 0.5}, 90.0)
        assert tr["didt_pk"] > 0
        assert tr["rr_fet_frac"] == pytest.approx(0.85)


# ─────────────────────────────────────────────────────────────────────────────────────────────
# C211 — the four corrections that came out of the designer's two external diode reviews.
#
# Both reviewers independently recommended replacing 0.5*V*Q_c with the datasheet's capacitive
# ENERGY curve E_c(V). That is backwards: E_c is the energy STORED in the junction capacitance,
# and it is returned at the next turn-off when the inductor charges the switch node. What the
# MOSFET dissipates is the difference between what the bus supplied and what stayed stored.
# ─────────────────────────────────────────────────────────────────────────────────────────────

# VS-3C40CP12L-M3, transcribed from the datasheet the designer supplied. Dual common-cathode SiC
# MPS, TO-247AD 3L, 2 x 20 A, 1200 V. Every electrical value is quoted PER LEG.
VS3C40 = _prof("VS-3C40CP12L-M3", {
    "V_RRM":       [_e(1200.0)],
    "I_F_AV":      [_e(20.0, T_c=153)],
    "V_F_vs_IF":   [_e(1.35, I_F=20, T_j=25),
                    _e(1.73, I_F=20, T_j=150), _e(1.85, I_F=20, T_j=175)],
    "Q_c":         [_e(107e-9, V_R=800)],
    "C_j":         [_e(1200e-12, V_R=1, f=1e6), _e(73e-12, V_R=800, f=1e6)],
    "R_th_jc":     [_e(0.8), _e(0.4)],                    # per leg / per device, both max
    "I_rev_vs_Tj": [_e(1.5e-6, V_R=1200, T_j=25), _e(12e-6, V_R=1200, T_j=175)],
})


class TestCapacitiveChargeIsSplitStoredVersusDissipated:
    def test_the_grading_coefficient_is_fitted_from_the_two_published_capacitance_points(self):
        """No curve digitising: vendors state C_j at ~1 V and at the rated V_R, which pins m."""
        blk = DF.profile_to_block(VS3C40, "sic_schottky", DESIGN)
        # 1200 pF at 1 V -> 73 pF at 800 V
        expected = -math.log(73e-12 / 1200e-12) / math.log(800.0 / 1.0)
        assert blk["cj_grading"] == pytest.approx(expected, abs=1e-3)
        assert 0.33 < blk["cj_grading"] < 0.5          # a physical junction, not a fit artefact

    def test_the_fitted_law_reproduces_the_published_charge(self):
        """The check that says the two-point fit is describing this part and not just a line."""
        blk = DF.profile_to_block(VS3C40, "sic_schottky", DESIGN)
        m = blk["cj_grading"]
        c0 = 73e-12 * 800.0 ** m
        q_modelled = c0 * 800.0 ** (1 - m) / (1 - m)
        assert q_modelled == pytest.approx(107e-9, rel=0.10)

    def test_the_charge_is_moved_to_the_bus_with_that_same_exponent(self):
        blk = DF.profile_to_block(VS3C40, "sic_schottky", DESIGN)
        m = blk["cj_grading"]
        assert blk["qc"] == pytest.approx(107e-9 * (393 / 800) ** (1 - m), rel=1e-6)
        assert blk["_qc_basis"]["fitted"] is True
        assert blk["qc"] < 107e-9                       # an 800 V figure overstates a 393 V bus

    @pytest.mark.parametrize("m", [0.0, 0.33, 0.419, 0.472, 0.5])
    def test_the_dissipated_share_is_one_over_two_minus_m(self, m):
        """E_diss = V*Q_c - E_stored, and for C(v) = C0*v^-m that is exactly V*Q_c/(2-m).

        Checked against direct integration rather than trusting the algebra. The grid is
        LOG-spaced: C ~ v^-m is singular at the origin, and a linear grid misestimates the charge
        by half a percent at m = 0.5 — enough to hide the very effect being tested."""
        import numpy as np
        V = 394.0
        v = np.geomspace(1e-9, V, 200_001)
        C = 1.2e-9 * v ** -m
        q = float(np.trapezoid(C, v)); e_stored = float(np.trapezoid(v * C, v))
        assert (V * q - e_stored) / (V * q) == pytest.approx(1.0 / (2.0 - m), rel=1e-3)

    def test_m_zero_is_the_linear_capacitor_and_reproduces_the_old_number_exactly(self):
        """The default. An unknown m must not silently change every existing result."""
        from app.mode_b.semiconductor import database as sdb
        from app.mode_b.semiconductor.adapter import calculate_semiconductor_losses
        import copy
        mos = sdb.to_block(sdb.load("mosfet")[0], "mosfet")
        brg = sdb.to_block(sdb.load("bridge")[0], "bridge")
        blk = DF.profile_to_block(VS3C40, "sic_schottky", DESIGN)
        old = copy.deepcopy(blk); old["cj_grading"] = 0.0
        run = lambda b: calculate_semiconductor_losses(
            DESIGN, mos, b, brg, {"t_ambient": 50, "rth_sa": 0.5}, None)["per_point"][0]
        p_old, p_new = run(old), run(blk)
        fsw, vo, nch = DESIGN["fsw"], DESIGN["vout"], DESIGN["nch"]
        assert p_old["P_FET_rr"] == pytest.approx(nch * fsw * 0.5 * vo * blk["qc"], rel=1e-6)
        assert p_new["P_FET_rr"] > p_old["P_FET_rr"] * 1.2      # the correction is not cosmetic

    def test_a_part_with_no_capacitance_points_says_the_term_is_understated(self):
        blk = DF.profile_to_block(SIC, "sic_schottky", DESIGN)      # SIC fixture has no C_j
        assert "cj_grading" not in blk
        msg = next(c["message"] for c in blk["_checks"] if c["key"] == "C_j_grading")
        assert "linear" in msg.lower() and "understated" in msg


class TestSharedPackageThermal:
    def test_the_per_leg_thermal_resistance_is_used_not_the_per_device_one(self):
        """A dual package publishes both; the junction sees the per-leg (larger) figure. Picking
        the per-device number would halve the predicted rise."""
        blk = DF.profile_to_block(VS3C40, "sic_schottky", DESIGN)
        assert blk["rth_jc"] == pytest.approx(0.8)
        assert blk["_rth_jc_published"] == [0.4, 0.8]

    def test_two_thermal_resistances_flag_a_multi_die_package(self):
        blk = DF.profile_to_block(VS3C40, "sic_schottky", DESIGN)
        c = next(c for c in blk["_checks"] if c["key"] == "dies_per_package")
        assert c["severity"] == "check" and "MULTI-DIE" in c["message"]

    def test_a_shared_case_carries_every_loaded_dies_loss(self):
        from app.mode_b.semiconductor import database as sdb
        from app.mode_b.semiconductor.adapter import calculate_semiconductor_losses
        mos = sdb.to_block(sdb.load("mosfet")[0], "mosfet")
        brg = sdb.to_block(sdb.load("bridge")[0], "bridge")
        run = lambda d: calculate_semiconductor_losses(
            DESIGN, mos, DF.profile_to_block(VS3C40, "sic_schottky", d), brg,
            {"t_ambient": 50, "rth_sa": 0.5}, None)["per_point"][0]
        one = run(DESIGN)
        two = run({**DESIGN, "dies_per_package": 2})
        assert two["Tj_DIODE"] > one["Tj_DIODE"]
        assert two["Tj_DIODE"] - one["Tj_DIODE"] == pytest.approx(1.1, abs=0.4)

    def test_declaring_the_dual_replaces_the_warning_with_a_statement(self):
        blk = DF.profile_to_block(VS3C40, "sic_schottky", {**DESIGN, "dies_per_package": 2})
        assert blk["dies_per_package"] == 2
        c = next(c for c in blk["_checks"] if c["key"] == "dies_per_package")
        assert c["severity"] == "note"


class TestLeakageIsQuotedAtARatedVoltage:
    def test_the_reverse_voltage_is_recorded_and_reported_as_an_upper_bound(self):
        """I_R is published at the rated V_R (1200 V here), not the 393 V bus. It is used as
        published and declared a bound, because fitting the barrier-lowering law needs two voltage
        points and this datasheet gives one."""
        blk = DF.profile_to_block(VS3C40, "sic_schottky", DESIGN)
        assert blk["_irev_at_VR"] == [1200.0]
        msg = next(c["message"] for c in blk["_checks"] if c["key"] == "I_rev_vs_Tj")
        assert "UPPER BOUND" in msg and "1200" in msg
        assert blk["irev_curve"] == [[25.0, 175.0], [1.5e-6, 12e-6]]


# ─────────────────────────────────────────────────────────────────────────────────────────────
# M6 (C212) — the C202 plausibility gate, wired onto extracted and confirmed profiles.
#
# The gate was built against the vendor catalogues and then reachable only through its own
# endpoint, so the one path where a number arrives with NO vendor behind it — a machine reading a
# PDF — was the one path it never saw.
# ─────────────────────────────────────────────────────────────────────────────────────────────
import copy


def _mutate(profile, key, entries):
    p = copy.deepcopy(profile)
    for q in p["parameters"]:
        if q["key"] == key:
            q["entries"] = entries
    return p


class TestPlausibilityScreensTheDatasheetPath:
    def test_the_record_is_built_from_registry_names_not_a_local_table(self):
        """The rules read catalogue-shaped records; the profile speaks canonical keys. The bridge
        between them is `db_field`/`meta_field` in the registry, so the two cannot drift apart the
        way V_DSS and V_RRM did."""
        from app.mode_b.semiconductor import registry as R
        rec = DF.plausibility_record(VS3C40, "sic_schottky")
        assert rec["vr"] == 1200.0 and rec["vf"] == 1.35 and rec["io"] == 20.0
        owners = R.record_field_owners()
        assert owners["vr"] == "V_RRM" and owners["vf"] == "V_F_vs_IF"

    def test_every_field_the_semiconductor_rules_read_is_reachable_from_a_canonical_key(self):
        """If a rule gains an input the registry cannot supply, that rule silently stops arming on
        the datasheet path — it would still return ok, having checked nothing."""
        from app.mode_b.semiconductor import registry as R
        owners = R.record_field_owners()
        for field in ("rdson", "qg", "vdss", "vth", "id_25",     # mosfet
                      "vf", "vr", "io", "ifsm_A", "i2t_A2s"):    # diode / bridge
            assert field in owners, field

    def test_a_real_part_screens_clean_with_rules_actually_armed(self):
        """`ok` is worthless if nothing ran: `checked` must be non-zero."""
        res = DF.screen(VS3C40, "sic_schottky")
        assert res["ok"] and res["checked"] >= 3, res

    @pytest.mark.parametrize("label,key,entries,rule", [
        ("V_F decimal slip",  "V_F_vs_IF", [_e(13.5, I_F=20, T_j=25)], "diode.vf"),
        ("columns swapped",   "V_RRM",     [_e(1.35)],                 "diode.vf_lt_vr"),
        ("unit read as mA",   "I_F_AV",    [_e(0.020, T_c=153)],       "diode.io"),
        ("a factor of ten",   "V_RRM",     [_e(12000.0)],              "diode.vr"),
    ])
    def test_it_catches_the_mistakes_extraction_actually_makes(self, label, key, entries, rule):
        res = DF.screen(_mutate(VS3C40, key, entries), "sic_schottky")
        assert not res["ok"], label
        assert rule in {f["rule"] for f in res["findings"]}, (label, res["findings"])

    def test_the_screen_rides_on_both_upload_and_confirm(self):
        """Confirmation is where a DESIGNER's own correction can introduce a slip, and it is the
        confirmed profile the engine runs on."""
        import inspect
        src = inspect.getsource(DF.upload) + inspect.getsource(DF.confirm)
        assert src.count("screen(") == 2

    def test_it_is_advisory_and_cannot_break_the_flow(self):
        """A screen that can raise is worse than no screen: it would take the upload down with it."""
        res = DF.screen({"parameters": "not a list at all"}, "sic_schottky")
        assert res["ok"] is True and res["findings"] == []
        assert "unavailable" in res.get("note", "") or res["checked"] == 0

    def test_an_unscreenable_class_says_so_rather_than_claiming_a_pass(self):
        res = DF.screen(VS3C40, "igbt")           # no engine dataclass, so no rules
        assert res["ok"] is True and res["checked"] == 0 and "no plausibility rules" in res["note"]

    def test_the_record_choice_is_deterministic(self):
        """A SiC part publishes R_DS(on) at three gate voltages. Which one lands in the record must
        not depend on dictionary ordering, or a screen result changes between runs."""
        first = DF.plausibility_record(VS3C40, "sic_schottky")
        for _ in range(5):
            assert DF.plausibility_record(VS3C40, "sic_schottky") == first
