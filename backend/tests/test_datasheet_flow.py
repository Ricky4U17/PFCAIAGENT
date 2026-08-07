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
DESIGN_INPUTS = {"V_GS_drive": 18.0, "R_g_on": 1.8, "R_g_off": 1.8, "R_g_common": 1.8,
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
