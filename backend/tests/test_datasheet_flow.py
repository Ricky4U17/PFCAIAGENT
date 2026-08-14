"""
Tests for the datasheet-first selection flow (M3).

The flow is: state the requirement, upload the datasheet, review and confirm what was read, then
calculate. These tests run it end to end against the real Infineon datasheet, because the point of
the whole milestone is that the numbers the engine uses come from that file rather than from an
estimate.
"""
import os
import shutil
import tempfile

import pytest

from app.mode_b.semiconductor import datasheet_flow as DF
from app.mode_b.semiconductor import manifest as M
from app.mode_b.semiconductor import parts_store as PS
from app.mode_b.semiconductor import registry as R

_MOSFET = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "specs", "Review", "IMZA65R033M2HXKSA1.pdf")

DESIGN = {"vin_min": 90, "vin_max": 264, "vout": 393, "fline": 60, "fsw": 65000,
          "L_phi_uH": 235, "nch": 2, "pout_lo": 1700, "pout_hi": 3600,
          "eta": 0.95, "r_input": 0.2, "pf": 0.99}

# The design decisions no datasheet can supply.
DESIGN_INPUTS = {"V_GS_drive": 18.0, "R_g_on": 1.8, "R_g_off": 1.8,
                 "R_th_cs": 0.3, "sw_method": "analytic"}


@pytest.fixture
def store_root():
    d = tempfile.mkdtemp(prefix="ds_flow_test_")
    try:
        yield d
    finally:
        shutil.rmtree(d, ignore_errors=True)


@pytest.fixture(scope="module")
def pdf_bytes():
    if not os.path.exists(_MOSFET):
        pytest.skip("IMZA65R033M2HXKSA1 datasheet not available")
    with open(_MOSFET, "rb") as f:
        return f.read()


class TestRequirementComesFirst:
    def test_the_requirement_is_derived_from_the_design_alone(self):
        req = DF.requirements(DESIGN)
        assert req["V_DSS_min"] == pytest.approx(393 * 1.20, rel=1e-3)
        assert req["I_D_min"] > 0
        assert req["basis"]["V_bus"] == 393 and req["basis"]["n_channels"] == 2

    def test_no_part_number_is_offered(self):
        """The Top-10 ranking is gone because it ordered candidates by a loss computed from the
        nine parameters the catalogue does not carry. Nothing here may name a part."""
        req = DF.requirements(DESIGN)
        blob = repr(req).upper()
        for token in ("IMZA", "IPW", "IPD", "IMW", "PART_NUMBER"):
            assert token not in blob

    def test_the_statement_says_where_the_numbers_came_from(self):
        s = DF.requirements(DESIGN)["statement"]
        assert "bus" in s and "margin" in s and "upload" in s


class TestUpload:
    def test_a_readable_datasheet_yields_review_rows(self, pdf_bytes, store_root):
        up = DF.upload(pdf_bytes, "mosfet", "sic_mosfet", root=store_root)
        assert up["ok"] and up["part_number"] == "IMZA65R033M2H"
        assert len(up["rows"]) > 10

    def test_an_unreadable_pdf_is_refused_with_a_reason(self, store_root):
        """An empty profile and a refusal look identical to a caller unless the flow says which."""
        import fitz
        blank = fitz.open()
        blank.new_page()
        up = DF.upload(blank.tobytes(), "mosfet", "sic_mosfet", root=store_root)
        assert up["ok"] is False and "text layer" in up["reason"]
        assert up["rows"] == []

    def test_the_part_number_is_not_a_word_from_the_cover(self, pdf_bytes, store_root):
        """The first heuristic returned "MOSFET" from the cover page, which would have created a
        library folder of that name. A part number contains digits."""
        up = DF.upload(pdf_bytes, "mosfet", "sic_mosfet", root=store_root)
        assert up["part_number"] not in ("MOSFET", "DATASHEET", "UNKNOWN")
        assert any(c.isdigit() for c in up["part_number"])

    def test_re_uploading_the_same_file_is_a_no_op(self, pdf_bytes, store_root):
        DF.upload(pdf_bytes, "mosfet", "sic_mosfet", root=store_root)
        again = DF.upload(pdf_bytes, "mosfet", "sic_mosfet", root=store_root)
        assert again["stored"]["changed"] is False


class TestReviewScreen:
    def test_it_shows_only_what_the_calculation_consumes(self, pdf_bytes, store_root):
        """Sixty rows produces click-through. The registry has 80+ parameters; the screen shows the
        ones this calculation uses."""
        rows = DF.upload(pdf_bytes, "mosfet", "sic_mosfet", root=store_root)["rows"]
        assert 10 <= len(rows) <= 30
        assert not any(r["key"].startswith("k_") for r in rows), "tolerance knobs are noise here"

    def test_every_row_states_its_destination(self, pdf_bytes, store_root):
        """A bare number is not reviewable; a number with its conditions and its use is."""
        rows = DF.upload(pdf_bytes, "mosfet", "sic_mosfet", root=store_root)["rows"]
        for r in rows:
            assert r["destination"]
        rds = next(r for r in rows if r["key"] == "R_DS_on")
        assert rds["destination"] == "conduction loss"

    def test_problems_sort_to_the_top(self, pdf_bytes, store_root):
        rows = DF.upload(pdf_bytes, "mosfet", "sic_mosfet", root=store_root)["rows"]
        first_supplied = next(i for i, r in enumerate(rows) if r["supplied"])
        assert all(not r["supplied"] for r in rows[:first_supplied])

    def test_a_multi_valued_parameter_lists_every_entry(self, pdf_bytes, store_root):
        """Showing one of four on-resistances, chosen arbitrarily, tells a reviewer nothing about
        which one will actually be used."""
        rows = DF.upload(pdf_bytes, "mosfet", "sic_mosfet", root=store_root)["rows"]
        rds = next(r for r in rows if r["key"] == "R_DS_on")
        assert rds["entries"] >= 4
        conds = [tuple(sorted(e["conditions"].items())) for e in rds["all_entries"]]
        assert len(set(conds)) >= 4, "entries must be distinguishable"

    def test_design_sourced_rows_are_marked_and_unsupplied(self, pdf_bytes, store_root):
        """No upload can supply a gate resistor. They must appear as the designer's to fill in, not
        silently take an engine default."""
        rows = DF.upload(pdf_bytes, "mosfet", "sic_mosfet", root=store_root)["rows"]
        for key in ("V_GS_drive", "R_g_on", "R_g_off", "R_th_cs"):
            r = next(x for x in rows if x["key"] == key)
            assert r["source_kind"] == "design" and not r["supplied"]

    def test_the_headline_values_are_the_datasheet_ones(self, pdf_bytes, store_root):
        rows = {r["key"]: r for r in DF.upload(pdf_bytes, "mosfet", "sic_mosfet",
                                               root=store_root)["rows"]}
        assert rows["E_oss_vs_VDS"]["value"] == pytest.approx(8.7e-6)
        assert rows["Q_gd"]["value"] == pytest.approx(6.2e-9)
        assert rows["R_th_jc"]["value"] == pytest.approx(0.77)
        assert rows["E_oss_vs_VDS"]["display"] == "8.7 µJ"


class TestConfirmAndBlock:
    def _confirmed(self, pdf_bytes, root, edits=None):
        up = DF.upload(pdf_bytes, "mosfet", "sic_mosfet", root=root)
        DF.confirm(up["part_number"], edits or {}, "sic_mosfet", root=root)
        return up["part_number"], PS.load_profile(up["part_number"], kind="confirmed", root=root)

    def test_confirming_marks_the_part_ready(self, pdf_bytes, store_root):
        mpn, _ = self._confirmed(pdf_bytes, store_root)
        lib = {p["part_number"]: p for p in PS.library(root=store_root)}
        assert lib[mpn]["ready"] is True

    def test_a_correction_keeps_the_extracted_original(self, pdf_bytes, store_root):
        """The library must always be able to answer "the machine read X, you confirmed Y"."""
        mpn, prof = self._confirmed(pdf_bytes, store_root, edits={"R_th_jc": 0.80})
        e = next(p for p in prof["parameters"] if p["key"] == "R_th_jc")["entries"][0]
        assert e["typ"] == 0.80 and e["provenance"] == "corrected"
        assert e["extracted_original"]["max"] == pytest.approx(0.77)

    def test_the_block_uses_the_entry_at_the_designs_own_gate_voltage(self, pdf_bytes, store_root):
        """Four on-resistances are published. Handing the engine whichever parsed first would put a
        15 V or a 175 degC number into a design driven at 18 V and 25 degC."""
        _, prof = self._confirmed(pdf_bytes, store_root)
        blk = DF.profile_to_block(prof, "sic_mosfet", DESIGN_INPUTS)
        assert blk["rdson_25"] == pytest.approx(0.033)

    def test_the_temperature_curve_comes_from_the_datasheet_not_a_generic_assumption(
            self, pdf_bytes, store_root):
        """The catalogue path assumed 'SiC rises 1.4x by 125 degC'. The datasheet states 33 mOhm at
        25 degC and 54 at 175, so the real ratio is 1.64 at 175 — a different curve entirely."""
        _, prof = self._confirmed(pdf_bytes, store_root)
        blk = DF.profile_to_block(prof, "sic_mosfet", DESIGN_INPUTS)
        temps, ratios = blk["rdson_tj"]
        assert temps == [25.0, 175.0]
        assert ratios[1] == pytest.approx(54.0 / 33.0, rel=1e-3)

    def test_eoss_is_anchored_on_the_published_value(self, pdf_bytes, store_root):
        """Still a fitted shape — a V^1.5 curve — but anchored on 8.7 uJ rather than invented from
        die area, which gave 30.0 uJ. Stamped `derived`, and M7 replaces it with the real curve."""
        _, prof = self._confirmed(pdf_bytes, store_root)
        blk = DF.profile_to_block(prof, "sic_mosfet", DESIGN_INPUTS)
        vs, es = blk["eoss_at_v"]
        assert vs[1] == 400.0 and es[1] == pytest.approx(8.7e-6)
        assert blk[M.PROVENANCE_KEY]["E_oss_vs_VDS"] == "derived"

    def test_the_gate_drive_alias_is_written_to_both_engine_fields(self, pdf_bytes, store_root):
        """The M1 fix, exercised through the real flow."""
        _, prof = self._confirmed(pdf_bytes, store_root)
        blk = DF.profile_to_block(prof, "sic_mosfet", DESIGN_INPUTS)
        assert blk["vg"] == 18.0 and blk["vg_drive"] == 18.0
        assert R.audit_block(blk) == []

    def test_every_engine_input_has_a_provenance_and_none_defaults(self, pdf_bytes, store_root):
        """The point of the whole milestone: nothing the engine consumes is a number nobody chose."""
        _, prof = self._confirmed(pdf_bytes, store_root)
        blk = DF.profile_to_block(prof, "sic_mosfet", DESIGN_INPUTS)
        v = M.validate_block(blk, "sic_mosfet")
        assert v["ok"], v["defaulted"]
        assert not v["untagged"]

    def test_omitting_a_design_input_is_reported_not_defaulted(self, pdf_bytes, store_root):
        _, prof = self._confirmed(pdf_bytes, store_root)
        blk = DF.profile_to_block(prof, "sic_mosfet",
                                  {k: v for k, v in DESIGN_INPUTS.items() if k != "V_GS_drive"})
        v = M.validate_block(blk, "sic_mosfet")
        assert not v["ok"]
        assert any(d["key"] == "V_GS_drive" for d in v["defaulted"])


class TestLossTable:
    def test_it_reports_the_engines_own_numbers(self, pdf_bytes, store_root):
        """Recomputing in the presentation layer is how the Top-10 screen came to disagree with the
        Results page (C157-C160). The table must be a view, not a second calculation."""
        from app.mode_b.semiconductor.adapter import calculate_semiconductor_losses
        from app.mode_b.semiconductor import database as sdb
        up = DF.upload(pdf_bytes, "mosfet", "sic_mosfet", root=store_root)
        DF.confirm(up["part_number"], {}, "sic_mosfet", root=store_root)
        prof = PS.load_profile(up["part_number"], kind="confirmed", root=store_root)
        mos = DF.profile_to_block(prof, "sic_mosfet", DESIGN_INPUTS)
        res = calculate_semiconductor_losses(
            DESIGN, mos, sdb.to_block(sdb.load("diode")[0], "diode"),
            sdb.to_block(sdb.load("bridge")[0], "bridge"),
            {"t_ambient": 50, "rth_sa": 0.5}, None)
        tbl = DF.loss_table(res["per_point"])
        assert len(tbl["rows"]) == len(res["per_point"])
        for row, src in zip(tbl["rows"], res["per_point"]):
            assert row["P_FET_total"] == src["P_FET_total"]
            assert row["P_FET_cond"] == src["P_FET_cond"]

    def test_the_components_sum_to_the_total(self, pdf_bytes, store_root):
        from app.mode_b.semiconductor.adapter import calculate_semiconductor_losses
        from app.mode_b.semiconductor import database as sdb
        up = DF.upload(pdf_bytes, "mosfet", "sic_mosfet", root=store_root)
        DF.confirm(up["part_number"], {}, "sic_mosfet", root=store_root)
        prof = PS.load_profile(up["part_number"], kind="confirmed", root=store_root)
        res = calculate_semiconductor_losses(
            DESIGN, DF.profile_to_block(prof, "sic_mosfet", DESIGN_INPUTS),
            sdb.to_block(sdb.load("diode")[0], "diode"),
            sdb.to_block(sdb.load("bridge")[0], "bridge"),
            {"t_ambient": 50, "rth_sa": 0.5}, None)
        tbl = DF.loss_table(res["per_point"])
        for r in tbl["rows"]:
            parts = sum(r[k] or 0.0 for k in
                        ("P_FET_cond", "P_FET_sw", "P_FET_coss", "P_FET_rr", "P_FET_leak"))
            assert parts == pytest.approx(r["P_FET_total"], rel=1e-6)

    def test_gate_loss_is_reported_but_excluded_from_the_device_total(self, pdf_bytes, store_root):
        """It is dissipated in the driver and the gate resistors, not the junction — so it belongs
        in the efficiency budget but not in the device temperature rise."""
        from app.mode_b.semiconductor.adapter import calculate_semiconductor_losses
        from app.mode_b.semiconductor import database as sdb
        up = DF.upload(pdf_bytes, "mosfet", "sic_mosfet", root=store_root)
        DF.confirm(up["part_number"], {}, "sic_mosfet", root=store_root)
        prof = PS.load_profile(up["part_number"], kind="confirmed", root=store_root)
        res = calculate_semiconductor_losses(
            DESIGN, DF.profile_to_block(prof, "sic_mosfet", DESIGN_INPUTS),
            sdb.to_block(sdb.load("diode")[0], "diode"),
            sdb.to_block(sdb.load("bridge")[0], "bridge"),
            {"t_ambient": 50, "rth_sa": 0.5}, None)
        tbl = DF.loss_table(res["per_point"])
        assert tbl["rows"][0]["P_gate_driver"] is not None
        assert "not in the MOSFET junction" in tbl["note"]

    def test_it_names_the_worst_and_hottest_points(self, pdf_bytes, store_root):
        rows = [{"Vac": 90, "P_FET_total": 20.0, "Tj_FET": 100.0},
                {"Vac": 264, "P_FET_total": 5.0, "Tj_FET": 130.0}]
        tbl = DF.loss_table(rows)
        assert tbl["worst_loss"]["Vac"] == 90 and tbl["hottest"]["Vac"] == 264


class TestDatasheetBeatsTheCatalogue:
    def test_the_datasheet_block_differs_from_the_catalogue_estimate_where_it_should(
            self, pdf_bytes, store_root):
        """Side by side, on the same part: this is the whole reason for the milestone."""
        from app.mode_b.semiconductor import database as sdb
        up = DF.upload(pdf_bytes, "mosfet", "sic_mosfet", root=store_root)
        DF.confirm(up["part_number"], {}, "sic_mosfet", root=store_root)
        prof = PS.load_profile(up["part_number"], kind="confirmed", root=store_root)
        ds = DF.profile_to_block(prof, "sic_mosfet", DESIGN_INPUTS)

        cat_rec = next((r for r in sdb.load("mosfet")
                        if "IMZA65R033" in (r.get("part_number") or "")), None)
        if cat_rec is None:
            pytest.skip("part not in the catalogue for comparison")
        cat = sdb.to_block(cat_rec, "mosfet")

        # E_oss: estimated from die area vs published. 30.0 uJ against 8.7 uJ.
        assert cat["eoss_at_v"][1][1] > 3 * ds["eoss_at_v"][1][1]
        # Q_gd: 0.25*Q_g vs published.
        assert cat["qgd"] > ds["qgd"]
        # R_DS(on): the catalogue value carries no gate-voltage condition at all.
        assert cat["rdson_25"] != ds["rdson_25"]


# ══════════════════════════════════════════════════════════════════════════════════════════════
#  M4a — the direct-substitution loss terms, once the values are real.
#  Conduction R_DS(T_j), E_oss at the actual bus, gate on the real V_GS, leakage, thermal.
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _blocks(pdf_bytes, root, design_inputs=None):
    """(catalogue block, datasheet block) for the SAME part — the comparison M4a exists to make."""
    from app.mode_b.semiconductor import database as sdb
    up = DF.upload(pdf_bytes, "mosfet", "sic_mosfet", root=root)
    DF.confirm(up["part_number"], {}, "sic_mosfet", root=root)
    prof = PS.load_profile(up["part_number"], kind="confirmed", root=root)
    ds = DF.profile_to_block(prof, "sic_mosfet", design_inputs or DESIGN_INPUTS)
    rec = next((r for r in sdb.load("mosfet")
                if "IMZA65R033" in (r.get("part_number") or "")), None)
    return (sdb.to_block(rec, "mosfet") if rec else None), ds


def _losses(block):
    from app.mode_b.semiconductor.adapter import calculate_semiconductor_losses
    from app.mode_b.semiconductor import database as sdb
    d = dict(DESIGN, fsw=70000)
    return calculate_semiconductor_losses(
        d, block, sdb.to_block(sdb.load("diode")[0], "diode"),
        sdb.to_block(sdb.load("bridge")[0], "bridge"),
        {"t_ambient": 50, "rth_sa": 0.5}, None)["per_point"]


class TestM4aSubstitution:
    def test_eoss_loss_falls_to_the_published_figure(self, pdf_bytes, store_root):
        """The headline of the whole plan. The die-area estimate gave 30.0 uJ against a published
        8.7, so E_oss loss was roughly 3.4x too high at every operating point."""
        cat, ds = _blocks(pdf_bytes, store_root)
        if cat is None:
            pytest.skip("part not in the catalogue")
        c, d = _losses(cat)[0], _losses(ds)[0]
        assert c["P_FET_coss"] > 3.5 and d["P_FET_coss"] < 1.5
        assert d["P_FET_coss"] == pytest.approx(1.19, abs=0.15)

    def test_gate_loss_uses_the_real_drive_voltage(self, pdf_bytes, store_root):
        """f_sw * Q_g * V_g, on 18 V and 34 nC from the datasheet rather than a generic pairing."""
        _, ds = _blocks(pdf_bytes, store_root)
        d = _losses(ds)[0]
        assert d["P_gate_driver"] == pytest.approx(2 * 70e3 * 34e-9 * 18.0, rel=0.02)

    def test_conduction_rises_because_the_real_part_is_worse_than_the_estimate(
            self, pdf_bytes, store_root):
        """Not every correction is favourable, and that is the point of using real values:
        R_DS(on) is 33 mOhm not 30, and the real hot curve is 1.64x at 175 degC, not 1.4x."""
        cat, ds = _blocks(pdf_bytes, store_root)
        if cat is None:
            pytest.skip("part not in the catalogue")
        assert _losses(ds)[0]["P_FET_cond"] > _losses(cat)[0]["P_FET_cond"]

    def test_the_temperature_curve_is_the_datasheets_own(self, pdf_bytes, store_root):
        _, ds = _blocks(pdf_bytes, store_root)
        temps, ratios = ds["rdson_tj"]
        assert temps[-1] == 175.0 and ratios[-1] == pytest.approx(54.0 / 33.0, rel=1e-3)

    def test_leakage_is_now_a_measurement_rather_than_a_placeholder(self, pdf_bytes, store_root):
        """The blocking-loss term stood at exactly zero because nothing populated the I_DSS curve.
        Two published points make it small but real — and honestly small, not assumed away."""
        _, ds = _blocks(pdf_bytes, store_root)
        assert ds["idss_curve"][0] == [25.0, 175.0]
        assert _losses(ds)[0]["P_FET_leak"] > 0.0

    def test_thermal_resistance_is_the_published_one(self, pdf_bytes, store_root):
        _, ds = _blocks(pdf_bytes, store_root)
        assert ds["rth_jc"] == pytest.approx(0.77)

    def test_total_loss_and_junction_temperature_both_fall(self, pdf_bytes, store_root):
        cat, ds = _blocks(pdf_bytes, store_root)
        if cat is None:
            pytest.skip("part not in the catalogue")
        c, d = _losses(cat)[0], _losses(ds)[0]
        assert d["P_FET_total"] < c["P_FET_total"]
        assert d["Tj_FET"] < c["Tj_FET"]


class TestM4aChecks:
    def test_a_gate_swing_mismatch_is_reported(self, pdf_bytes, store_root):
        """Q_g is published for a 0-18 V swing. Driving 15 V moves less charge, so using 34 nC
        overstates gate loss — reported rather than silently corrected, because scaling it without
        the gate-charge curve would be a guess."""
        _, ds = _blocks(pdf_bytes, store_root, dict(DESIGN_INPUTS, V_GS_drive=15.0))
        msgs = [c["message"] for c in ds["_checks"] if c["key"] == "Q_g"]
        assert msgs and "18 V gate swing" in msgs[0] and "drives 15 V" in msgs[0]

    def test_no_mismatch_is_reported_when_the_swing_matches(self, pdf_bytes, store_root):
        _, ds = _blocks(pdf_bytes, store_root)
        assert not [c for c in ds["_checks"] if c["key"] == "Q_g"]

    def test_a_missing_transconductance_is_stated_not_assumed(self, pdf_bytes, store_root):
        """This datasheet does not publish g_fs in its tables, so the plan's assumption that it is
        a phase-1 value does not hold here. Without it the plateau is constant and switching energy
        is strictly proportional to current — a real limitation, and it is said out loud."""
        _, ds = _blocks(pdf_bytes, store_root)
        note = next(c for c in ds["_checks"] if c["key"] == "g_fs")
        assert note["severity"] == "note" and "superlinearity" in note["message"]

    def test_an_unpublished_gate_voltage_is_flagged(self, pdf_bytes, store_root):
        """The datasheet publishes 15, 18 and 20 V. A design at 12 V gets the nearest, and is told."""
        _, ds = _blocks(pdf_bytes, store_root, dict(DESIGN_INPUTS, V_GS_drive=12.0))
        assert any(c["key"] == "R_DS_on" for c in ds["_checks"])

    def test_crss_is_deliberately_not_fitted_from_one_point(self, pdf_bytes, store_root):
        """C_rss swings by orders of magnitude across the blocking range; a two-point fit through
        the single published value would be a shape nobody measured. Without it the engine uses the
        Miller integral, and Q_gd is now the real 6.2 nC."""
        _, ds = _blocks(pdf_bytes, store_root)
        assert "crss_curve" not in ds
        assert ds["qgd"] == pytest.approx(6.2e-9)


class TestMetadataNeverReachesTheEngine:
    def test_any_underscore_key_is_metadata(self):
        """Twice a new underscore-prefixed field reached the Mosfet dataclass and raised, because
        the allow-list had to be updated in a second place. The convention now holds for every
        such key, so it cannot be forgotten again."""
        from app.mode_b.semiconductor.adapter import _clean_block
        params, meta = _clean_block({"rdson_25": 0.033, "_anything_new": "x", "_checks": []})
        assert params == {"rdson_25": 0.033}
        assert "_anything_new" in meta and "_checks" in meta


# ══════════════════════════════════════════════════════════════════════════════════════════════
#  M4b — switching-energy anchoring under CONVENTION B (settled 2026-08-05).
#
#  A published E_on bundles the device's own C_oss discharge and the freewheeling element's charge,
#  both of which this engine counts separately. Anchoring on the raw figure would double-count them.
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestSwitchingAnchor:
    def _anchor(self, pdf_bytes, root, design_inputs=None):
        _, ds = _blocks(pdf_bytes, root, design_inputs)
        return ds, ds["_switching_anchor"]

    def test_the_anchor_reproduces_the_datasheet_test_point(self, pdf_bytes, store_root):
        """The acceptance criterion. Overlap + own E_oss + fixture charge must reconstruct the
        published E_on, and the anchored E_off must equal the published E_off."""
        import numpy as np
        from app.mode_b.semiconductor.pfc_loss_model import Mosfet
        ds, a = self._anchor(pdf_bytes, store_root)
        assert a["ok"]
        b, band = a["basis"], a["band"]
        m = Mosfet(**{k: v for k, v in ds.items() if k in Mosfet.__dataclass_fields__})
        one, zero = np.array([b["I_test"]]), np.array([0.0])
        e_on = float(m.e_switch(one, zero, b["V_test"], b["T_j_test"])[0])
        e_off = float(m.e_switch(zero, one, b["V_test"], b["T_j_test"])[0])
        reconstructed = e_on + m.eoss(b["V_test"]) + band["q_fw_used_C"] * b["V_test"]
        assert reconstructed == pytest.approx(b["E_on_ds"], rel=0.02)
        assert e_off == pytest.approx(b["E_off_ds"], rel=0.02)

    def test_de_bundling_is_what_brings_the_two_factors_together(self, pdf_bytes, store_root):
        """The empirical case for convention B. Anchored on the RAW published E_on the factors are
        about 4.3 and 1.9 — 2.3x apart. Remove the parts the engine counts separately and they
        become ~1.7 and ~1.6. A magnitude error would have scaled both alike; the divergence was
        a definition mismatch, and de-bundling removes it."""
        _, a = self._anchor(pdf_bytes, store_root)
        b = a["basis"]
        raw_k_on = b["E_on_ds"] / b["E_on_analytic"]
        assert raw_k_on / a["k_off"] > 2.0, "the raw factors should be far apart"
        ratio = max(a["k_on"], a["k_off"]) / min(a["k_on"], a["k_off"])
        assert ratio < 1.5, f"after de-bundling they should converge, got {ratio:.2f}"

    def test_an_independent_anchor_agrees_about_the_unknown_charge(self, pdf_bytes, store_root):
        """E_off carries no bundled charge, so it can be anchored without any assumption. Asking
        what the fixture must then have contributed is a route to the unknown that knows nothing
        about the assumed range — agreement is real validation, not arithmetic that was arranged."""
        _, a = self._anchor(pdf_bytes, store_root)
        q = a["implied_q_fw_C"]
        lo, hi = a["band"]["q_fw_low_C"], a["band"]["q_fw_high_C"]
        assert lo <= q <= hi, f"implied {q*1e9:.0f} nC outside the assumed {lo*1e9:.0f}-{hi*1e9:.0f}"

    def test_the_uncertainty_band_is_reported_not_hidden(self, pdf_bytes, store_root):
        """This datasheet shows its test fixture only as a circuit diagram, so the freewheeling
        charge is not extractable. The anchor uses a midpoint AND says what the ends would give."""
        _, a = self._anchor(pdf_bytes, store_root)
        assert a["band"]["stated"] is False
        assert a["band"]["k_on_low"] < a["k_on"] < a["band"]["k_on_high"]
        assert any("does not state" in n for n in a["notes"])

    def test_the_engine_factors_deliver_the_two_anchors(self, pdf_bytes, store_root):
        """The engine scales both energies by k_esw and turn-off again by k_turnoff, so the ratio
        is what makes e_off land on k_off. Easy to get backwards; asserted rather than assumed."""
        ds, a = self._anchor(pdf_bytes, store_root)
        assert ds["k_esw"] == pytest.approx(a["k_on"], rel=1e-4)
        assert ds["k_esw"] * ds["k_turnoff"] == pytest.approx(a["k_off"], rel=1e-4)

    def test_the_anchor_is_bounded_and_refuses_absurd_values(self, pdf_bytes, store_root):
        """A negative or wild factor means the de-bundling subtracted too much, or the model does
        not describe the device. Either way it must not be applied silently."""
        ds, a = self._anchor(pdf_bytes, store_root)
        assert 0.5 <= a["k_on"] <= 5.0 and 0.5 <= a["k_off"] <= 5.0

    def test_a_part_with_no_published_energies_is_not_anchored(self, pdf_bytes, store_root):
        """Most catalogue parts publish nothing to anchor on. That must leave the model unscaled
        rather than inventing a factor."""
        prof = {"parameters": [{"key": "R_DS_on", "entries": [{"typ": 0.033, "conditions": {}}]}]}
        a = DF.switching_anchor(prof, {"rdson_25": 0.033}, DESIGN_INPUTS)
        assert a["ok"] is False and "no E_on/E_off" in a["reason"]

    def test_anchoring_raises_switching_loss_towards_the_measured_truth(self, pdf_bytes, store_root):
        """The un-anchored analytic model was measured 2.9x low at the datasheet's own test point.
        Anchoring should therefore INCREASE the switching term, not decrease it."""
        ds, _ = self._anchor(pdf_bytes, store_root)
        un = dict(ds, k_esw=1.0, k_turnoff=1.0)
        assert _losses(ds)[0]["P_FET_sw"] > _losses(un)[0]["P_FET_sw"]

    def test_the_separate_gate_resistors_reach_the_engine(self, pdf_bytes, store_root):
        """Convention B couples R_g,on to E_on and R_g,off to E_off. Both must arrive, and the
        anchor must be taken at the FIXTURE's resistor, not the design's."""
        ds, a = self._anchor(pdf_bytes, store_root,
                             dict(DESIGN_INPUTS, R_g_on=2.2, R_g_off=1.0))
        assert ds["rg_on"] == 2.2 and ds["rg_off"] == 1.0
        assert a["basis"]["R_g_test"] == pytest.approx(1.8)

    def test_the_provenance_records_the_factors_as_derived(self, pdf_bytes, store_root):
        ds, _ = self._anchor(pdf_bytes, store_root)
        assert ds[M.PROVENANCE_KEY]["k_esw"] == "derived"
        assert ds[M.PROVENANCE_KEY]["k_turnoff"] == "derived"

    def test_the_bundling_state_permits_a_separate_eoss_term(self, pdf_bytes, store_root):
        """The registry's third state. `raw` and `unknown` must block a separate E_oss term;
        `de_bundled` allows it precisely because the overlap was taken net of it."""
        _, a = self._anchor(pdf_bytes, store_root)
        assert a["bundling"] == "de_bundled"


class TestPlausibilityOnTheRealMosfet:
    """M6 (C212). The gate now runs on the datasheet path — the one place a number arrives with no
    vendor catalogue behind it, and therefore the one place it was never applied."""

    def test_the_real_datasheet_screens_clean_with_rules_armed(self, pdf_bytes, store_root):
        up = DF.upload(pdf_bytes, "mosfet", "sic_mosfet", root=store_root)
        p = up["plausibility"]
        assert p["ok"], p["findings"]
        assert p["checked"] >= 5, p          # `ok` is worthless if nothing ran
        assert p["record"]["vdss"] == 650.0

    def test_a_designers_own_correction_is_screened_too(self, pdf_bytes, store_root):
        """Confirmation is where a hand-typed value enters, and it is the confirmed profile the
        engine runs on. A 10x slip on R_DS(on) passes the band on its own — 0.33 ohm is a real
        resistance for some part — and is caught only by the CROSS-FIELD rule against I_D."""
        up = DF.upload(pdf_bytes, "mosfet", "sic_mosfet", root=store_root)
        assert up["plausibility"]["ok"]
        bad = DF.confirm(up["part_number"], {"R_DS_on": 0.33}, "sic_mosfet", root=store_root)
        assert not bad["plausibility"]["ok"]
        assert "mosfet.id_x_rdson" in {f["rule"] for f in bad["plausibility"]["findings"]}

    def test_it_never_blocks_the_confirmation(self, pdf_bytes, store_root):
        """Advisory means advisory: flagged, and the confirmation still succeeds and still builds
        a valid block. The gate reports; it does not decide."""
        up = DF.upload(pdf_bytes, "mosfet", "sic_mosfet", root=store_root)
        res = DF.confirm(up["part_number"], {"R_DS_on": 0.33}, "sic_mosfet", root=store_root)
        assert res["ok"] is True
        assert not res["plausibility"]["ok"]                 # flagged...
        prof = PS.load_profile(up["part_number"], kind="confirmed", root=store_root)
        blk = DF.profile_to_block(prof, "sic_mosfet", DESIGN_INPUTS)
        assert M.validate_block(blk, "sic_mosfet")["ok"]     # ...and the flow carries on regardless

    def test_an_edit_lands_on_one_entry_and_the_engine_may_select_another(self, pdf_bytes,
                                                                          store_root):
        """Documents a real wrinkle in the edit model, found while testing M6 (PENDING C4).

        `confirm(edits)` applies a correction to whichever entry `_pick_entry` returns — here the
        V_GS = 15 V row — while `profile_to_block` selects by the DESIGN's gate voltage, 18 V. So a
        correction can be recorded, screened, and then not be the value the engine uses. Asserted
        rather than fixed: the fix is to let the review screen target a specific condition, which is
        a change to the screen, not to the gate."""
        up = DF.upload(pdf_bytes, "mosfet", "sic_mosfet", root=store_root)
        res = DF.confirm(up["part_number"], {"R_DS_on": 0.33}, "sic_mosfet", root=store_root)
        assert res["plausibility"]["record"]["rdson"] == pytest.approx(0.33)   # screened
        prof = PS.load_profile(up["part_number"], kind="confirmed", root=store_root)
        blk = DF.profile_to_block(prof, "sic_mosfet", DESIGN_INPUTS)
        assert blk["rdson_25"] == pytest.approx(0.033)                        # but not used


# ── M7 for the MOSFET (C224) ──────────────────────────────────────────────────────────────────
# Extracting and digitising a 17-page PDF is the slowest thing in this suite, so the whole M7 flow
# is run ONCE at module scope — upload, digitise, accept all four curves — and the tests below read
# different keys off that one result. Per-test isolation buys nothing here: the four curves land on
# four independent canonical keys, and accepting all four is also the realistic end state.
@pytest.fixture(scope="module")
def m7(pdf_bytes):
    root = tempfile.mkdtemp(prefix="ds_m7_")
    try:
        up = DF.upload(pdf_bytes, "mosfet", "sic_mosfet", root=root)
        mpn = up["part_number"]
        prof = PS.load_profile(mpn, kind="extracted", root=root)
        props = {q["key"]: q for q in DF.figure_proposals(pdf_bytes, prof)["proposals"]}
        for key in ("E_oss_vs_VDS", "C_rss_vs_VDS", "R_DS_on_vs_Tj", "R_DS_on_vs_ID",
                    "E_on_vs_ID", "E_off_vs_ID", "E_on_vs_Rg", "E_off_vs_Rg"):
            if key not in props:
                continue
            q = props[key]
            ci = (q["cross_check"] or {}).get("curve_index", 0)   # the trace the table anchors
            c = dict(q["curves"][ci])
            c["caption"], c["page"] = q["caption"], q["page"]
            DF.confirm_figure(mpn, key, c, root=root)
        confirmed = PS.load_profile(mpn, kind="confirmed", root=root)
        # NO `sw_method` here, deliberately. DESIGN_INPUTS pins it to "analytic" for the older
        # tests, and passing that would tell the block to ignore the very curves this fixture
        # exists to confirm — the evidence is supposed to choose the method when the designer has
        # not. The designer-override path is tested separately, where it is the actual subject.
        d = {k: v for k, v in DESIGN_INPUTS.items() if k != "sw_method"}
        yield {"props": props, "profile": confirmed, "part_number": mpn, "root": root,
               "design": d,
               "block": DF.profile_to_block(confirmed, "sic_mosfet", d, root=root)}
    finally:
        shutil.rmtree(root, ignore_errors=True)


class TestTheMosfetFiguresAreOffered:
    """Until C224 `_FIGURE_TARGETS` held only the five diode keys and the bridge derating curve, so
    a MOSFET datasheet yielded no proposals even where its plots read cleanly."""

    def test_the_four_mosfet_targets_are_all_found(self, m7):
        assert set(m7["props"]) >= {"E_oss_vs_VDS", "C_rss_vs_VDS",
                                    "R_DS_on_vs_Tj", "R_DS_on_vs_ID"}

    def test_each_one_is_checked_against_the_part_s_own_table(self, m7):
        """The acceptance test for the whole reading. The plot and the table are independent
        renderings of one measurement, so agreement is what says the frame, the axes and the scale
        were all read right — and it is what catches a log axis read as linear."""
        for key in ("E_oss_vs_VDS", "C_rss_vs_VDS", "R_DS_on_vs_Tj", "R_DS_on_vs_ID"):
            cc = m7["props"][key]["cross_check"]
            assert cc["checked"] is True, f"{key} was not checked"
            assert cc["agrees"] is True, f"{key}: {cc.get('note')}"

    def test_the_capacitance_figure_carries_three_traces_and_the_table_picks_one(self, m7):
        """C_iss, C_oss and C_rss share one plot, so its traces are three DIFFERENT quantities
        rather than one quantity at three conditions. Accepting the wrong one would put ~1700 pF
        where 7 pF belongs. The datasheet's own tabulated C_rss identifies which is which."""
        p = m7["props"]["C_rss_vs_VDS"]
        assert p["n_curves"] == 3
        ci = p["cross_check"]["curve_index"]
        assert max(p["curves"][ci]["y"]) < min(max(c["y"]) for i, c in enumerate(p["curves"])
                                               if i != ci)      # C_rss is the lowest of the three


class TestAConfirmedMosfetCurveReachesTheEngine:
    """Proposals no engine reads change no number. This is the C215 step for the MOSFET: before it,
    all four were accepted and stored and the block still showed the two-point fits."""

    def test_eoss_replaces_the_fitted_shape_and_lands_in_joules(self, m7):
        """The published point was already the anchor (C208), so the curve corrects the SHAPE
        between anchors rather than the level — and the unit is the thing worth asserting, because
        a curve read in nJ instead of uJ is smooth, monotonic and wrong by 1000x."""
        blk = m7["block"]
        assert blk[M.PROVENANCE_KEY]["E_oss_vs_VDS"] == "digitised"
        assert len(blk["eoss_at_v"][0]) > 20
        assert blk["_eoss_basis"]["checked"] is True
        assert blk["_eoss_basis"]["error_pct"] < 12.0
        xs, ys = blk["eoss_at_v"]
        at400 = max(y for x, y in zip(xs, ys) if x <= 400.0)
        assert 5e-6 < at400 < 2e-5, f"E_oss(400 V) = {at400} is not in joules"

    def test_crss_is_mapped_once_there_is_a_measured_shape(self, m7):
        """It was deliberately unmapped while the datasheet gave ONE point, because crss_curve
        wants C_rss(V) across the blocking range. A digitised curve is that shape."""
        blk = m7["block"]
        assert blk[M.PROVENANCE_KEY]["C_rss_vs_VDS"] == "digitised"
        assert 1e-12 < min(blk["crss_curve"][1]) < 5e-11        # farads, not picofarads

    def test_the_temperature_curve_beats_the_two_point_interpolation(self, m7):
        """The registry says why in one line: the curve is convex, so a straight line between two
        tabulated endpoints overshoots in the middle."""
        blk = m7["block"]
        assert blk[M.PROVENANCE_KEY]["R_DS_on_vs_Tj"] == "digitised"
        xs, ys = blk["rdson_tj"]
        assert len(xs) > 20
        assert DF._curve_at({"x": xs, "y": ys}, 25.0) == pytest.approx(1.0, abs=0.1)

    def test_rdson_vs_current_is_normalised_not_taken_in_ohms(self, m7):
        """The engine MULTIPLIES by this curve (`r *= curve(Id)`) and the plot is in ohms. Landing
        it raw would scale on-resistance by ~0.04 instead of by ~1."""
        blk = m7["block"]
        assert blk[M.PROVENANCE_KEY]["R_DS_on_vs_ID"] == "digitised"
        xs, ys = blk["rdson_id_curve"]
        assert 0.5 < min(ys) < 1.5 and 1.0 <= max(ys) < 4.0, (min(ys), max(ys))
        # By INTERPOLATION, not by looking for a nearby sample: the curve is normalised at the
        # current the table states, which need not be one of the digitised points.
        at_ref = DF._curve_at({"x": xs, "y": ys}, blk["_rdson_id_basis"]["normalised_at_A"])
        assert at_ref == pytest.approx(1.0, abs=1e-6)

    def test_a_curve_that_contradicts_the_table_is_refused(self, m7, pdf_bytes, store_root):
        """A unit slip is the one error every other check survives, so the tabulated point is the
        gate. A curve scaled 1000x must be rejected and the fitted shape kept, not used."""
        up = DF.upload(pdf_bytes, "mosfet", "sic_mosfet", root=store_root)
        p = m7["props"]["E_oss_vs_VDS"]
        bad = dict(p["curves"][(p["cross_check"] or {}).get("curve_index", 0)])
        bad["y"] = [v * 1000.0 for v in bad["y"]]
        DF.confirm_figure(up["part_number"], "E_oss_vs_VDS", bad, root=store_root)
        blk = DF.profile_to_block(
            PS.load_profile(up["part_number"], kind="confirmed", root=store_root),
            "sic_mosfet", DESIGN_INPUTS)
        assert blk[M.PROVENANCE_KEY]["E_oss_vs_VDS"] == "derived"      # fell back
        assert blk["_eoss_basis"]["from_curve"] is False
        assert blk["_eoss_basis"]["error_pct"] > 100.0


class TestTheUnitBackstopWhenThereIsNoTabulatedPoint:
    """With a tabulated point the unit is checked against it. WITHOUT one, the registry's declared
    plausibility band is all that is left, and these tests pin down HOW WEAK that is — E_oss is
    declared 1e-8 to 1e-2 J, so a 1000x slip from 8.7 uJ lands at 8.7 mJ and sails through.

    That is the reason an unanchored curve is returned `checked: False` and reported as unverified
    instead of being treated as confirmed. Asserting the limit rather than a comfortable-looking
    pass is the point: someone will otherwise read the backstop as a unit check, which it is not.
    Built from a hand-made profile so it costs no PDF work."""

    @staticmethod
    def _profile(curve_y):
        """A minimal MOSFET profile carrying ONLY a digitised E_oss curve — no tabulated point."""
        return {"part_number": "SYNTHETIC", "parameters": [
            {"key": "device_class", "entries": [{"typ": "sic_mosfet", "conditions": {}}]},
            {"key": "R_DS_on", "entries": [{"typ": 0.033, "conditions": {"V_GS": 18.0,
                                                                         "T_j": 25.0}}]},
            {"key": "E_oss_vs_VDS", "entries": [
                {"typ": [[100.0, 200.0, 300.0, 400.0], curve_y], "provenance": "digitised",
                 "conditions": {}, "n_points": 4}]},
        ]}

    def test_a_plausible_curve_is_used_and_marked_unchecked(self):
        blk = DF.profile_to_block(self._profile([1.0, 3.0, 6.0, 8.7]),   # uJ -> 8.7e-6 J, sane
                                  "sic_mosfet", DESIGN_INPUTS)
        assert blk[M.PROVENANCE_KEY]["E_oss_vs_VDS"] == "digitised"
        basis = blk["_eoss_basis"]
        assert basis["from_curve"] is True and basis["checked"] is False
        assert "tabulates no value" in basis["note"]

    def test_a_grossly_wrong_curve_is_refused(self):
        """8.7 J of output-capacitance energy is not a reading of anything."""
        blk = DF.profile_to_block(self._profile([1e6, 3e6, 6e6, 8.7e6]),   # uJ -> 8.7 J
                                  "sic_mosfet", DESIGN_INPUTS)
        assert blk[M.PROVENANCE_KEY].get("E_oss_vs_VDS") != "digitised"
        assert blk["_eoss_basis"]["from_curve"] is False
        assert "outside the plausible" in blk["_eoss_basis"]["note"]

    def test_the_band_does_NOT_catch_a_1000x_slip_and_says_so(self):
        """The limit of the backstop, asserted so it is not mistaken for a unit check. 8.7 mJ is
        1000x wrong and inside the declared band, so it is USED — and marked unverified, which is
        the whole reason that flag exists."""
        blk = DF.profile_to_block(self._profile([1e3, 3e3, 6e3, 8.7e3]),   # uJ -> 8.7 mJ
                                  "sic_mosfet", DESIGN_INPUTS)
        assert blk[M.PROVENANCE_KEY]["E_oss_vs_VDS"] == "digitised"        # not caught...
        assert blk["_eoss_basis"]["checked"] is False                      # ...but never "checked"
        assert "could not be checked" in blk["_eoss_basis"]["note"]


# ── the MEASURED switching-energy curves (C225, from the external MOSFET review) ───────────────
class TestSwitchingEnergyComesOffTheMeasuredCurves:
    """The external review's main MOSFET recommendation: stop inferring the SHAPE of E_on/E_off
    from an analytic gate model anchored at one point, and read the vendor's own E(I_D) plots.

    The trap it also warned about is the reason this is not a two-line change — a published E_on
    bundles C_oss discharge and fixture freewheeling charge, both of which this chapter already
    books separately, so the raw curve would double-count them."""

    def test_both_energies_are_offered_from_the_one_figure(self, m7):
        """E_on and E_off share a plot, so `figure_proposals` must not stop at the first match."""
        for key in ("E_on_vs_ID", "E_off_vs_ID", "E_on_vs_Rg", "E_off_vs_Rg"):
            assert key in m7["props"], f"{key} was not offered"
        a, b = m7["props"]["E_on_vs_ID"], m7["props"]["E_off_vs_ID"]
        assert a["frame"] == b["frame"] and a["page"] == b["page"]   # the SAME figure

    def test_each_key_finds_its_own_trace(self, m7):
        """Three unlabelled traces: E_on, E_off and their sum. The datasheet states E_on = 35 uJ
        and E_off = 22 uJ at one test point, and that is what tells them apart."""
        on, off = m7["props"]["E_on_vs_ID"], m7["props"]["E_off_vs_ID"]
        assert on["cross_check"]["agrees"] and off["cross_check"]["agrees"]
        assert on["cross_check"]["curve_index"] != off["cross_check"]["curve_index"]
        assert on["cross_check"]["got"] > off["cross_check"]["got"]     # E_on > E_off

    def test_the_curves_reach_the_engine_in_joules(self, m7):
        blk = m7["block"]
        assert blk["sw_method"] == "esw"
        assert blk[M.PROVENANCE_KEY]["E_on_vs_ID"] == "digitised"
        assert blk[M.PROVENANCE_KEY]["E_off_vs_ID"] == "digitised"
        assert len(blk["eon_curve"][0]) > 20 and len(blk["eoff_curve"][0]) > 20
        assert blk["vref_sw"] == pytest.approx(400.0)
        # microjoules, in joules: 1e-6..1e-4. A curve left in uJ would read 10..100.
        assert 1e-7 < max(blk["eoff_curve"][1]) < 1e-3

    def test_turn_on_is_de_bundled_and_the_residual_proves_the_size(self, m7):
        """THE physical check. Overlap energy is proportional to current, so after removing the
        parts that are set by VOLTAGE (C_oss and the fixture's freewheeling charge) what is left
        must fall to about zero at the lowest plotted current. If the subtraction were the wrong
        size this would come out strongly negative or still large."""
        e = m7["block"]["_esw_basis"]
        assert e["ok"], e.get("reason")
        assert e["debundled_J"] > 0
        resid = e["residual_at_min_current_J"]
        assert -1e-6 < resid < 3e-6, f"residual {resid*1e6:.2f} uJ is not near zero"
        # and the de-bundled turn-on curve must sit BELOW the published one at the test point
        blk = m7["block"]
        at = DF._curve_at({"x": blk["eon_curve"][0], "y": blk["eon_curve"][1]}, e["i_test"])
        assert at < 35e-6, "de-bundled turn-on must be below the published 35 uJ"
        assert at == pytest.approx(35e-6 - e["debundled_J"], rel=0.05)

    def test_turn_off_is_not_de_bundled(self, m7):
        """No C_oss discharge and no recovery charge flow through the device at turn-off, so E_off
        is used as published. At the test current it must still read the tabulated 22 uJ."""
        blk = m7["block"]
        at = DF._curve_at({"x": blk["eoff_curve"][0], "y": blk["eoff_curve"][1]},
                          blk["_esw_basis"]["i_test"])
        assert at == pytest.approx(22e-6, rel=0.05)

    def test_the_analytic_anchor_stays_independent(self, m7):
        """Regression guard. The anchor's whole value is that it shares no input with the plot;
        once the block carries `sw_method='esw'` it would otherwise compare the curve with itself
        and report a nonsense factor (0.36 was the observed value before this was fixed)."""
        a = m7["block"]["_switching_anchor"]
        assert a["ok"], a.get("reason")
        assert 0.5 <= a["k_on"] <= 5.0


class TestGateResistanceIsCorrectedPerPath:
    """The published energies are valid only at the fixture's gate resistor, and the `esw` path
    applies no correction of its own. Turn-on and turn-off are corrected SEPARATELY because the
    two gate paths are independent — using one figure for both hides an asymmetric gate drive."""

    @staticmethod
    def _blk(pdf_bytes, root, rg_on, rg_off):
        up = DF.upload(pdf_bytes, "mosfet", "sic_mosfet", root=root)
        mpn = up["part_number"]
        prof0 = PS.load_profile(mpn, kind="extracted", root=root)
        props = {q["key"]: q for q in DF.figure_proposals(pdf_bytes, prof0)["proposals"]}
        for key in ("E_oss_vs_VDS", "E_on_vs_ID", "E_off_vs_ID", "E_on_vs_Rg", "E_off_vs_Rg"):
            q = props[key]
            ci = (q["cross_check"] or {}).get("curve_index", 0)
            c = dict(q["curves"][ci]); c["caption"], c["page"] = q["caption"], q["page"]
            DF.confirm_figure(mpn, key, c, root=root)
        d = dict(DESIGN_INPUTS); d["R_g_on"], d["R_g_off"] = rg_on, rg_off
        return DF.profile_to_block(PS.load_profile(mpn, kind="confirmed", root=root),
                                   "sic_mosfet", d)

    def test_the_fixture_resistor_is_a_no_op(self, pdf_bytes, store_root):
        """1.8 ohm IS the test condition, so the correction must be exactly 1.0 — not 'about' 1.0.
        Anything else means the ratio is being read off the wrong place on the curve."""
        e = self._blk(pdf_bytes, store_root, 1.8, 1.8)["_esw_basis"]
        assert e["k_rg_on"] == pytest.approx(1.0, abs=1e-3)
        assert e["k_rg_off"] == pytest.approx(1.0, abs=1e-3)

    def test_an_asymmetric_gate_path_gives_two_different_factors(self, pdf_bytes, store_root):
        e = self._blk(pdf_bytes, store_root, 4.7, 10.0)["_esw_basis"]
        assert e["k_rg_on"] > 1.2 and e["k_rg_off"] > 1.2      # both slower than the fixture
        assert e["k_rg_off"] > e["k_rg_on"]                    # 10 ohm costs more than 4.7 ohm
        assert abs(e["k_rg_off"] - e["k_rg_on"]) > 0.5         # and they are NOT the same number


class TestTheDesignerCanStillChooseTheAnalyticModel:
    def test_an_explicit_sw_method_wins_over_the_curves(self, pdf_bytes, store_root):
        """Evidence wins by DEFAULT, not unconditionally. Choosing the analytic model stays a
        decision on the record: the curves are still read, checked and reported, just not used."""
        up = DF.upload(pdf_bytes, "mosfet", "sic_mosfet", root=store_root)
        mpn = up["part_number"]
        prof0 = PS.load_profile(mpn, kind="extracted", root=store_root)
        props = {q["key"]: q for q in DF.figure_proposals(pdf_bytes, prof0)["proposals"]}
        for key in ("E_oss_vs_VDS", "E_on_vs_ID", "E_off_vs_ID"):
            q = props[key]
            ci = (q["cross_check"] or {}).get("curve_index", 0)
            c = dict(q["curves"][ci]); c["caption"], c["page"] = q["caption"], q["page"]
            DF.confirm_figure(mpn, key, c, root=store_root)
        d = dict(DESIGN_INPUTS); d["sw_method"] = "analytic"
        blk = DF.profile_to_block(PS.load_profile(mpn, kind="confirmed", root=store_root),
                                  "sic_mosfet", d)
        assert blk["sw_method"] == "analytic"          # the designer's choice stands...
        assert blk["_esw_basis"]["ok"] is True         # ...and the curves are still reported


class TestTheAnchorFactorsNeverScaleAMeasuredCurve:
    """REGRESSION GUARD for a bug that was masked by a second one.

    `Mosfet.e_switch` applies `k_esw` and `k_turnoff` in BOTH its branches. Those factors exist to
    calibrate the ANALYTIC model against the published energies (k_esw came out at 2.71 on this
    part), so writing them while the measured E(I_D) curves are in use multiplies a digitised plot
    by 2.71 — P_FET read 41 % high. It only looked correct at first because the anchor was itself
    broken and failing its own band check, so nothing was written. Fixing the anchor exposed it.

    The curve IS the measurement; there is nothing left to calibrate on that path.
    """

    def test_no_anchor_factor_is_written_when_the_curves_are_in_use(self, m7):
        blk = m7["block"]
        assert blk["sw_method"] == "esw"
        assert blk.get("k_esw", 1.0) == 1.0
        assert blk.get("k_turnoff", 1.0) == 1.0
        anchor = blk["_switching_anchor"]
        assert anchor["ok"] is True                    # still computed...
        assert anchor.get("applied") is False          # ...and explicitly not applied
        assert anchor.get("not_applied_reason")

    def test_the_factors_are_still_applied_to_the_analytic_model(self, pdf_bytes, store_root):
        """The other half: switching the designer back to the analytic model must restore them,
        or the anchor stops doing the job it was built for (C209)."""
        up = DF.upload(pdf_bytes, "mosfet", "sic_mosfet", root=store_root)
        d = dict(DESIGN_INPUTS); d["sw_method"] = "analytic"
        blk = DF.profile_to_block(PS.load_profile(up["part_number"], kind="extracted",
                                                  root=store_root), "sic_mosfet", d)
        assert blk["_switching_anchor"]["ok"] is True
        assert blk["k_esw"] != 1.0
        assert blk[M.PROVENANCE_KEY]["k_esw"] == "derived"

    def test_switching_energy_is_exactly_the_curve_arithmetic(self, m7):
        """Hand-check, so the number is not merely self-consistent: at the datasheet's own test
        current the engine must return (E_on,debundled + E_off) scaled by V_OUT/V_test, with no
        other factor sneaking in."""
        import numpy as np
        from app.mode_b.semiconductor.pfc_loss_model import Mosfet, curve
        blk = m7["block"]
        e = blk["_esw_basis"]
        fields = {k: v for k, v in blk.items() if k in Mosfet.__dataclass_fields__}
        m = Mosfet(**fields)
        i = np.array([e["i_test"]])
        vo = 394.0
        eon = curve(i, *blk["eon_curve"])[0]
        eoff = curve(i, *blk["eoff_curve"])[0]
        got = m.e_switch(i, i, vo, 110.0)[0]
        assert got == pytest.approx((eon + eoff) * (vo / blk["vref_sw"]), rel=1e-9)
        # and the de-bundling really did come off the turn-on side
        assert eon == pytest.approx(35e-6 - e["debundled_J"], abs=1.5e-6)


class TestConfirmDoesNotDestroyAcceptedCurves:
    """REGRESSION GUARD for the defect that made every curve feature dead in the real GUI.

    `confirm()` rebuilds from the EXTRACTED profile by design — that is what lets the library say
    "the machine read X, you confirmed Y". But it wrote that over the confirmed profile, and the
    only thing living there that the extraction does not contain is a digitised curve.

    The Curves tab re-confirms after every Accept (deliberately, so the engine block rebuilds), so
    in the running application each curve was written by `confirm_figure` and deleted by the
    `confirm` that followed it milliseconds later. C215, C224 and C225 all shipped curve features
    that never once reached the engine through the screen.

    EVERY EXISTING TEST MISSED IT by calling `profile_to_block` directly and never running the two
    calls in the order the GUI does. These tests run them in that order.
    """

    @staticmethod
    def _n_digitised(mpn, root):
        p = PS.load_profile(mpn, kind="confirmed", root=root) or {}
        return sum(1 for prm in p.get("parameters", [])
                   for e in prm.get("entries", []) if e.get("provenance") == "digitised")

    def _accept_one(self, pdf_bytes, root, key="E_on_vs_ID"):
        up = DF.upload(pdf_bytes, "mosfet", "sic_mosfet", root=root)
        mpn = up["part_number"]
        prof0 = PS.load_profile(mpn, kind="extracted", root=root)
        p = next(q for q in DF.figure_proposals(pdf_bytes, prof0)["proposals"] if q["key"] == key)
        ci = (p["cross_check"] or {}).get("curve_index", 0)
        c = dict(p["curves"][ci])
        c["caption"], c["page"], c["frame"] = p["caption"], p["page"], p["frame"]
        DF.confirm_figure(mpn, key, c, root=root)
        return mpn

    def test_a_curve_survives_the_confirm_that_follows_it(self, pdf_bytes, store_root):
        mpn = self._accept_one(pdf_bytes, store_root)
        assert self._n_digitised(mpn, store_root) == 1
        DF.confirm(mpn, {}, "sic_mosfet", root=store_root)
        assert self._n_digitised(mpn, store_root) == 1, "confirm() destroyed the accepted curve"

    def test_it_survives_an_edit_too(self, pdf_bytes, store_root):
        """The edit path is the one that rebuilds from the extraction, so it is the one that used
        to drop the curve. Both must end up in the profile: the correction AND the evidence."""
        mpn = self._accept_one(pdf_bytes, store_root)
        DF.confirm(mpn, {"R_th_jc": 0.80}, "sic_mosfet", root=store_root)
        prof = PS.load_profile(mpn, kind="confirmed", root=store_root)
        assert self._n_digitised(mpn, store_root) == 1
        rth = next(p for p in prof["parameters"] if p["key"] == "R_th_jc")
        assert any(e.get("provenance") == "corrected" for e in rth["entries"])

    def test_re_confirming_repeatedly_does_not_duplicate_it(self, pdf_bytes, store_root):
        """The GUI confirms after every Accept, so this runs many times in one session."""
        mpn = self._accept_one(pdf_bytes, store_root)
        for _ in range(3):
            DF.confirm(mpn, {}, "sic_mosfet", root=store_root)
        assert self._n_digitised(mpn, store_root) == 1

    def test_the_engine_block_still_uses_the_curve_after_confirming(self, pdf_bytes, store_root):
        """The end of the chain, and the thing the designer actually sees: accept a curve, confirm,
        and the switching model must be the measured one."""
        up_keys = ("E_oss_vs_VDS", "E_on_vs_ID", "E_off_vs_ID")
        up = DF.upload(pdf_bytes, "mosfet", "sic_mosfet", root=store_root)
        mpn = up["part_number"]
        prof0 = PS.load_profile(mpn, kind="extracted", root=store_root)
        props = {q["key"]: q for q in DF.figure_proposals(pdf_bytes, prof0)["proposals"]}
        for key in up_keys:
            q = props[key]
            ci = (q["cross_check"] or {}).get("curve_index", 0)
            c = dict(q["curves"][ci])
            c["caption"], c["page"], c["frame"] = q["caption"], q["page"], q["frame"]
            DF.confirm_figure(mpn, key, c, root=store_root)
            DF.confirm(mpn, {}, "sic_mosfet", root=store_root)      # exactly what the tab does
        d = {k: v for k, v in DESIGN_INPUTS.items() if k != "sw_method"}
        blk = DF.profile_to_block(PS.load_profile(mpn, kind="confirmed", root=store_root),
                                  "sic_mosfet", d, root=store_root)
        assert blk["sw_method"] == "esw"
        assert blk["_esw_basis"]["ok"] is True
        assert len(blk["_figure_images"]) == len(up_keys)
