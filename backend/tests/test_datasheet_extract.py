"""
Tests for datasheet extraction and the per-part store (M2).

The acceptance fixture is a REAL vendor datasheet on disk — Diodes Incorporated GBJ40L06,
DS44960 Rev 4-2. Every expectation below was read off that document by hand first. A test written
against an imagined layout proves nothing; the traps that cost time are all things real files do
and invented ones do not.

The MOSFET acceptance case (IMZA65R033M2H) cannot run yet: the file in specs/Review is the loss
REPORT, not the datasheet. When the datasheet PDF is supplied, add it as a second fixture.
"""
import os
import shutil
import tempfile

import pytest

from app.mode_b.semiconductor import datasheet_extract as DX
from app.mode_b.semiconductor import parts_store as PS
from app.mode_b.semiconductor import registry as R
from app.mode_b.semiconductor import vendor_templates as VT

_FIXTURE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "specs", "Bridge Rectifier Configuration", "GBJ40L06.pdf")


@pytest.fixture(scope="module")
def pdf_bytes():
    if not os.path.exists(_FIXTURE):
        pytest.skip("GBJ40L06 datasheet not available")
    with open(_FIXTURE, "rb") as f:
        return f.read()


@pytest.fixture(scope="module")
def extracted(pdf_bytes):
    return DX.extract(pdf_bytes, "bridge_rectifier")


@pytest.fixture
def store_root():
    """A private temp directory. pytest's own `tmp_path` cannot be used on this machine — the
    shared pytest temp root raises WinError 5 when scanned."""
    d = tempfile.mkdtemp(prefix="parts_store_test_")
    try:
        yield d
    finally:
        shutil.rmtree(d, ignore_errors=True)


def _entries(profile, key):
    for p in profile["parameters"]:
        if p["key"] == key:
            return p["entries"]
    return []


class TestTextNormalisation:
    def test_lookalike_codepoints_fold_together(self):
        """U+2103 renders as degC and U+2126 as omega; both compare unequal to the typed forms.
        The fixture file uses U+2103, so without NFKC every temperature unit misses."""
        assert DX.norm_text("℃") == "°C"
        assert DX.parse_unit("℃")[0] == "degC"
        assert DX.parse_unit("Ω")[0] == DX.parse_unit("Ω")[0] == "ohm"
        assert DX.parse_unit("µA")[1] == DX.parse_unit("μA")[1] == pytest.approx(1e-6)

    def test_a_lone_dash_is_not_specified_not_zero(self):
        """'min = —' means no minimum is stated. Reading it as 0 would turn an unspecified bound
        into a specified one, and every min/typ/max datasheet is full of them."""
        for dash in ("-", "—", "–", "--"):
            assert DX.parse_numbers(dash) == []

    def test_si_prefixes_scale(self):
        assert DX.parse_unit("mohm") == ("ohm", pytest.approx(1e-3))
        assert DX.parse_unit("nC")[1] == pytest.approx(1e-9)
        assert DX.parse_unit("pF") == ("F", pytest.approx(1e-12))

    def test_conditions_parse_into_a_dict_in_si(self):
        c = DX.parse_conditions("IF = 20A, TJ = +25°C")
        assert c["I_F"] == 20.0 and c["T_j"] == 25.0

    def test_a_range_is_not_a_single_value(self):
        assert DX.parse_range("-40 to +150") == (-40.0, 150.0)


class TestTriage:
    def test_reports_what_kind_of_document_this_is(self, pdf_bytes):
        t = DX.triage(pdf_bytes)
        assert t["pages"] == 5 and t["has_text_layer"] and t["readable"]
        assert t["method"] == "template"
        assert t["vector_figure_pages"], "the curve pages are vector, which phase 2 needs"

    def test_an_unreadable_document_fails_loudly_rather_than_returning_nothing(self):
        """A scanned PDF parsed as if it had text yields zero parameters and looks exactly like a
        part with no data. It has to say which it is."""
        import fitz
        blank = fitz.open()
        blank.new_page()
        res = DX.extract(blank.tobytes(), "bridge_rectifier")
        assert res["ok"] is False
        assert "text layer" in res["reason"] and "supply a text PDF" in res["reason"]


class TestJunkTableRejection:
    def test_figure_pages_do_not_become_phantom_parameters(self, extracted):
        """Graph axes are drawn as rules, so the table finder returns large grids of empty cells.
        The fixture yields 12 such phantoms against 3 real tables; without the structural filter
        the parser reports parameters that do not exist."""
        assert len(extracted["rejected"]) >= 10
        assert len(extracted["tables"]) == 3
        assert any("figure, not a table" in r["rejected"] for r in extracted["rejected"])

    def test_every_kept_table_has_a_symbol_or_parameter_column(self, extracted):
        for t in extracted["tables"]:
            assert {"symbol", "parameter"} & set(t["roles"])


class TestRealDatasheetValues:
    """Read off the PDF by hand; these are the acceptance numbers."""

    def test_the_vendor_template_matched_on_document_metadata(self, pdf_bytes):
        """The visible header carries only a website — the vendor name is in the document
        properties. Matching on page text alone silently fell back to the generic template."""
        assert VT.match(pdf_bytes)["template_id"] == "diodes_inc_rectifier"

    def test_surge_ratings_that_the_catalogue_does_not_have(self, extracted):
        """I_FSM and I2t are absent from the parametric export on EVERY bridge, which is why the
        Chapter 8 bridge-surge gate reports OPEN. They are in the datasheet table.

        I2t also guards a specific regression: the superscript rule that strips footnote markers
        once turned "I²t" into "It", which matches nothing. A superscript is only a marker when it
        trails the line and is a bare number."""
        assert _entries(extracted["profile"], "I_FSM")[0]["typ"] == 420.0
        assert _entries(extracted["profile"], "I2t")[0]["typ"] == 732.0

    def test_forward_voltage_arrives_with_its_conditions(self, extracted):
        """A V_F of 0.87 V is not a fact. 0.87 V at I_F = 20 A, T_j = 25 degC is."""
        e = _entries(extracted["profile"], "V_F_vs_IF")[0]
        assert e["typ"] == pytest.approx(0.87) and e["max"] == pytest.approx(0.90)
        assert e["conditions"] == {"I_F": 20.0, "T_j": 25.0}

    def test_a_value_in_the_max_column_is_not_lost_to_a_dash_in_typ(self):
        """`IR | — | — | 10 | µA`. A dash is truthy, so choosing the first NON-EMPTY value column
        silently dropped the parameter; the column must be chosen by whether it holds a number.

        Driven by a CONSTRUCTED row rather than off a particular datasheet. It used to read the
        bridge's reverse-current entry, which stopped existing at C211 when that mapping was removed
        (a bridge's leakage has no valid key — see PENDING B18). The subject of the test was always
        the dash, not the leakage, and a synthetic row states that directly and cannot be broken by
        a template change."""
        roles = {"symbol": 0, "min": 1, "typ": 2, "max": 3, "unit": 4}
        row = ["IR", "—", "—", "10", "µA"]
        cell = lambda r, role: r[roles[role]] if role in roles else ""
        got = DX._parse_row(row, roles, {"ir": "I_rev_vs_Tj"}, cell)
        assert len(got) == 1, got
        e = got[0]
        assert e["max"] == pytest.approx(1e-5)      # 10 µA, scaled to SI
        assert e.get("typ") is None and e.get("min") is None

    def test_a_temperature_range_yields_both_bounds(self, extracted):
        e = _entries(extracted["profile"], "Tj_max")[0]
        assert e["min"] == -40.0 and e["max"] == 150.0

    def test_units_are_converted_to_si(self, extracted):
        """400 pF -> 4e-10 F.

        This read `C_iss` until C211. That was the same disconnect the V_DSS assertion above had:
        the part is a BRIDGE RECTIFIER and C_iss is a MOSFET input capacitance, declared for the
        MOSFET classes only — so its total capacitance landed on a key its class does not carry and
        was dropped. `C_j` is the diode/bridge counterpart, and it is what the two-point fit for the
        junction grading coefficient reads."""
        assert _entries(extracted["profile"], "C_j")[0]["min"] == pytest.approx(400e-12)
        assert not _entries(extracted["profile"], "C_iss"), (
            "a rectifier's junction capacitance must not be filed under the MOSFET's C_iss")

    def test_several_parameters_packed_into_one_row_are_unpacked(self):
        """`RthJC RthJL RthJA | 5 9 24` is three parameters, not one named
        'RthJC RthJL RthJA' with the value '5 9 24'."""
        assert DX.split_packed_row("RθJC RθJL RθJA", "5 9 24") == [
            ("RθJC", 5.0), ("RθJL", 9.0), ("RθJA", 24.0)]

    def test_packed_rows_refuse_to_guess_when_counts_disagree(self):
        """Three symbols against two numbers has no safe alignment. Reporting nothing beats
        pairing them wrongly."""
        assert DX.split_packed_row("A B C", "1 2") == []

    def test_several_conditions_under_one_symbol_become_separate_entries(self, extracted):
        """`IF(AV) | 40 5 | A` is the rating with and WITHOUT a heatsink. Taking the first number
        discards an operating point the designer may be relying on; keeping them as separate
        condition-qualified entries is what lets `select()` reach either."""
        vals = sorted(e["typ"] for e in _entries(extracted["profile"], "I_F_AV"))
        assert vals == [5.0, 40.0]

    def test_unmapped_symbols_are_reported_not_dropped(self, extracted):
        """R_thetaJL and R_thetaJA are real datasheet parameters our engine does not model. They
        belong in `unresolved` so a reviewer can see what the parser gave up on, rather than being
        silently discarded — the difference between "we did not use this" and "we did not see it"."""
        syms = {u["symbol"] for u in extracted["profile"]["unresolved"]}
        assert "RθJL" in syms and "RθJA" in syms
        assert "RθJC" not in syms, "the junction-to-case value IS modelled and must resolve"

    def test_nothing_maps_to_a_name_outside_the_registry(self, extracted):
        for p in extracted["profile"]["parameters"]:
            R.get(p["key"])                          # raises if the key was invented


class TestCrossCheck:
    def test_a_repeated_parameter_with_different_values_is_flagged(self, extracted):
        """The fixture publishes two thermal tables for two mounting variants, so R_th(j-c) comes
        out as both 5 and 2 degC/W. That ambiguity must reach the reviewer, not be resolved by
        whichever table happened to parse first.

        The check is deliberately advisory and errs towards flagging: I_F_AV also appears here,
        because its two ratings share one line of qualifying text ("With Heatsink Without
        Heatsink") and so cannot be told apart automatically. A reviewer dismisses that in a
        second; tuning it away would risk suppressing a real disagreement."""
        flagged = {c["key"] for c in extracted["cross_check"]}
        assert "R_th_jc" in flagged
        assert all(c["values"] and c["spread_pct"] > 1.0 for c in extracted["cross_check"])

    def test_the_summary_and_detail_blocks_agree_on_the_voltage_rating(self, extracted):
        """V_RRM in the product summary and V_B in the electrical table are both 600 V. Agreement
        between an independently-parsed summary and detail is free validation.

        This asserted `V_DSS` until C210. That was the disconnect, not the fixture: the part is a
        BRIDGE RECTIFIER, and `V_DSS` is declared for the MOSFET classes only — so its blocking
        rating landed on a key its own class does not carry and was dropped from every review row
        and requirement check downstream. `V_RRM` is the diode/bridge counterpart."""
        vals = {e.get("typ") or e.get("min") for e in _entries(extracted["profile"], "V_RRM")}
        assert vals == {600.0}
        assert not _entries(extracted["profile"], "V_DSS"), (
            "a rectifier's reverse rating must not be filed under the MOSFET's V_DSS")


class TestTemplates:
    def test_a_scoped_template_may_only_map_keys_valid_for_its_own_classes(self):
        """Existence was never the problem; APPLICABILITY was.

        Four defects slipped past the old "is this key in the registry" check: VRRM and VR mapped
        onto the MOSFET-only V_DSS, CT onto the MOSFET-only C_iss, and IR onto a diode-only leakage
        key from the BRIDGE template. Each parsed cleanly, landed on a name the part's own class
        does not carry, and was dropped downstream — and two green tests were asserting the wrong
        key. A template that declares its device classes must map only to keys valid for them.
        """
        import copy
        from app.mode_b.semiconductor import vendor_templates as VT
        from app.mode_b.semiconductor import registry as R

        classes_of = {p["key"]: set(p.get("device_classes") or [])
                      for p in R.load()["parameters"]}
        for t in VT.templates():
            scope = set(t.get("device_classes") or [])
            if not scope:
                continue                      # generic applies to everything
            for sym, key in (t.get("symbol_map") or {}).items():
                assert scope & classes_of[key], (t["template_id"], sym, key)

        # and the rule must actually bite, not just pass because nothing violates it today
        bad = copy.deepcopy(VT.load())
        tmpl = next(t for t in bad["templates"] if t["template_id"] == "diodes_inc_rectifier")
        tmpl["symbol_map"]["IR"] = "I_rev_vs_Tj"        # diode-only key on a bridge template
        with pytest.raises(ValueError, match="declared only for"):
            VT._validate(bad)

    def test_no_template_may_map_a_symbol_to_an_unregistered_name(self):
        """Inventing a name in a vendor adapter is exactly what the registry exists to prevent, so
        loading the templates validates every mapping against it."""
        VT.load()

    def test_a_fallback_template_always_exists(self):
        assert any(t.get("match", {}).get("always") for t in VT.templates())

    def test_templates_declare_vocabulary_not_coordinates(self):
        """If a template carried page numbers or bounding boxes, the layering has failed: those are
        derived at runtime from the document."""
        for t in VT.templates():
            assert "page" not in t and "bbox" not in t


class TestPartsStore:
    def test_identical_bytes_are_a_no_op(self, pdf_bytes, store_root):
        root = store_root
        a = PS.store_datasheet("GBJ40L06", pdf_bytes, root=root)
        b = PS.store_datasheet("GBJ40L06", pdf_bytes, root=root)
        assert a["changed"] is True and b["changed"] is False

    def test_changed_bytes_are_a_new_revision_requiring_re_approval(self, pdf_bytes, store_root):
        root = store_root
        PS.store_datasheet("GBJ40L06", pdf_bytes, root=root)
        c = PS.store_datasheet("GBJ40L06", pdf_bytes + b"\n", root=root)
        assert c["changed"] and "re-approved" in c["note"]
        assert c["previous_sha256"] and c["previous_sha256"] != c["sha256"]

    def test_extractions_are_versioned_and_never_overwritten(self, pdf_bytes, store_root):
        root = store_root
        prof = DX.extract(pdf_bytes, "bridge_rectifier")["profile"]
        v1 = PS.write_extracted("GBJ40L06", prof, root=root)
        v2 = PS.write_extracted("GBJ40L06", prof, root=root)
        assert v1["version"] == 1 and v2["version"] == 2
        assert os.path.exists(v1["path"]) and os.path.exists(v2["path"])

    def test_aliases_resolve_however_the_designer_types_it(self, pdf_bytes, store_root):
        """We have already been bitten: the catalogue says IMZA65R033M2HXKSA1 and the review report
        says IMZA65R033M2H."""
        root = store_root
        PS.store_datasheet("GBJ40L06", pdf_bytes, aliases=["GBJ40L06-F"], root=root)
        for typed in ("gbj40l06", "GBJ-40L06", "gbj 40l06", "GBJ40L06-F"):
            assert PS.resolve(typed, root=root) == "GBJ40L06"
        assert PS.resolve("NOT-A-PART", root=root) is None

    def test_only_a_confirmed_profile_marks_a_part_ready(self, pdf_bytes, store_root):
        root = store_root
        prof = DX.extract(pdf_bytes, "bridge_rectifier")["profile"]
        PS.store_datasheet("GBJ40L06", pdf_bytes, root=root)
        PS.write_extracted("GBJ40L06", prof, root=root)
        assert PS.library(root=root)[0]["ready"] is False
        PS.write_confirmed("GBJ40L06", prof, reviewed_by="designer", root=root)
        assert PS.library(root=root)[0]["ready"] is True

    def test_an_extracted_profile_is_not_reviewed(self, pdf_bytes, store_root):
        root = store_root
        prof = DX.extract(pdf_bytes, "bridge_rectifier")["profile"]
        PS.write_extracted("GBJ40L06", prof, root=root)
        stored = PS.load_profile("GBJ40L06", kind="extracted", root=root)
        assert stored["reviewed"] is False and stored["reviewed_by"] is None

    def test_a_revision_diff_lists_only_what_changed(self):
        old = {"parameters": [{"key": "V_F_vs_IF", "entries": [{"typ": 0.87, "max": 0.90}]}]}
        new = {"parameters": [{"key": "V_F_vs_IF", "entries": [{"typ": 0.85, "max": 0.90}]}]}
        d = PS.diff_profiles(old, new)
        assert len(d) == 1 and d[0]["field"] == "typ" and d[0]["was"] == 0.87 and d[0]["now"] == 0.85


class TestProfileShape:
    def test_the_profile_carries_its_own_identity_and_method(self, extracted):
        p = extracted["profile"]
        assert p["schema_version"] and p["device_class"] == "bridge_rectifier"
        assert len(p["datasheet"]["sha256"]) == 64
        assert p["extraction"]["phase"] == "tables_only"
        assert p["extraction"]["vendor_template"] == "diodes_inc_rectifier"

    def test_every_entry_records_where_it_came_from(self, extracted):
        for param in extracted["profile"]["parameters"]:
            for e in param["entries"]:
                assert e["provenance"] == "extracted"
                assert e["source"]["page"] >= 1

    def test_no_curves_are_invented_in_phase_1(self, extracted):
        """The old regex extractor fabricated a V-I curve from a single scalar. Phase 1 reads
        tables; a missing curve stays missing until M7 digitises it."""
        assert extracted["profile"]["curves"] == []


# ══════════════════════════════════════════════════════════════════════════════════════════════
#  MOSFET acceptance — the plan's M2 criterion, against the real Infineon datasheet.
#  IMZA65R033M2HXKSA1, CoolSiC 650 V G2, Rev 2.0, 2024-09-24.
#
#  This is the part whose numbers started the whole datasheet-first plan: our estimate had E_oss
#  3.4x high and Q_gd 37% high, because the Digi-Key catalogue carries neither.
# ══════════════════════════════════════════════════════════════════════════════════════════════
_MOSFET_FIXTURE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "specs", "Review", "IMZA65R033M2HXKSA1.pdf")


@pytest.fixture(scope="module")
def mosfet_profile():
    if not os.path.exists(_MOSFET_FIXTURE):
        pytest.skip("IMZA65R033M2HXKSA1 datasheet not available")
    with open(_MOSFET_FIXTURE, "rb") as f:
        return DX.extract(f.read(), "sic_mosfet")["profile"]


class TestMosfetAcceptance:
    def test_the_vendor_template_matched(self, mosfet_profile):
        assert mosfet_profile["extraction"]["vendor_template"] == "infineon_coolsic_g2"

    def test_all_four_on_resistance_entries_are_separate_and_condition_qualified(self, mosfet_profile):
        """THE acceptance criterion. The part publishes four R_DS(on) values in ONE bordered row —
        typ cell '43 33 30 54', max cell '- 41 - -', four condition sets stacked in the notes.
        Flattened they are a parameter with the value '43 33 30 54'; read per visual line they are
        the four entries `select()` needs."""
        from app.mode_b.semiconductor import manifest as M
        assert M.select(mosfet_profile, "R_DS_on", V_GS=15, T_j=25)["typ"] == pytest.approx(0.043)
        assert M.select(mosfet_profile, "R_DS_on", V_GS=18, T_j=25)["typ"] == pytest.approx(0.033)
        assert M.select(mosfet_profile, "R_DS_on", V_GS=20, T_j=25)["typ"] == pytest.approx(0.030)
        assert M.select(mosfet_profile, "R_DS_on", V_GS=18, T_j=175)["typ"] == pytest.approx(0.054)

    def test_the_design_entry_carries_its_maximum_too(self, mosfet_profile):
        from app.mode_b.semiconductor import manifest as M
        e = M.select(mosfet_profile, "R_DS_on", V_GS=18, T_j=25)
        assert e["typ"] == pytest.approx(0.033) and e["max"] == pytest.approx(0.041)

    def test_eoss_the_parameter_that_was_3_4x_wrong(self, mosfet_profile):
        """Our die-area estimate gave 30.0 uJ against a published 8.7 uJ, because that scaling is
        calibrated on silicon superjunction and this is a SiC trench device. 4.20 W vs 1.22 W at
        2 channels and 70 kHz, constant at every operating point."""
        e = _entries(mosfet_profile, "E_oss_vs_VDS")[0]
        assert e["typ"] == pytest.approx(8.7e-6)
        assert e["conditions"]["V_DS"] == 400.0

    def test_qgd_the_parameter_that_was_37_percent_wrong(self, mosfet_profile):
        """Estimated as 0.25*Q_g = 8.5 nC; the datasheet says 6.2 nC. Q_GS(pl) is deliberately NOT
        mapped to Q_gd — they are different charges, and mapping both put two contradictory values
        under one canonical key."""
        entries = _entries(mosfet_profile, "Q_gd")
        assert len(entries) == 1
        assert entries[0]["typ"] == pytest.approx(6.2e-9)

    def test_switching_energies_arrive_with_their_full_test_condition(self, mosfet_profile):
        """Convention B anchors on these, so the conditions are not decoration: the anchor is only
        valid at the bus, current and gate resistance they were measured at."""
        from app.mode_b.semiconductor import manifest as M
        on = M.select(mosfet_profile, "E_on", I_D=27.9, V_DS=400)
        off = M.select(mosfet_profile, "E_off", I_D=27.9, V_DS=400)
        assert on["typ"] == pytest.approx(35e-6) and off["typ"] == pytest.approx(22e-6)
        assert on["conditions"]["R_g"] == pytest.approx(1.8)
        assert on["conditions"]["V_DS"] == 400.0 and on["conditions"]["I_D"] == pytest.approx(27.9)

    def test_etot_reconstructs_from_eon_plus_eoff(self, mosfet_profile):
        """Free cross-validation: the vendor publishes the total as well as the parts."""
        on = _entries(mosfet_profile, "E_on")[0]["typ"]
        off = _entries(mosfet_profile, "E_off")[0]["typ"]
        tot = _entries(mosfet_profile, "E_tot")[0]["typ"]
        assert on + off == pytest.approx(tot, rel=1e-6)

    def test_the_remaining_headline_parameters(self, mosfet_profile):
        assert _entries(mosfet_profile, "Q_g")[-1]["typ"] == pytest.approx(34e-9)
        assert _entries(mosfet_profile, "R_th_jc")[0]["max"] == pytest.approx(0.77)
        assert _entries(mosfet_profile, "C_iss")[0]["typ"] == pytest.approx(1214e-12)
        assert _entries(mosfet_profile, "V_DSS")[0]["min"] == 650.0

    def test_gate_threshold_carries_min_typ_and_max(self, mosfet_profile):
        e = _entries(mosfet_profile, "V_GS_th")[0]
        assert (e["min"], e["typ"], e["max"]) == (3.5, 4.5, 5.6)

    def test_leakage_is_separated_by_junction_temperature(self, mosfet_profile):
        """Two rows in one bordered row again — 25 degC and 175 degC. Conflated, a hot-leakage
        question would silently receive the cold answer."""
        from app.mode_b.semiconductor import manifest as M
        assert M.select(mosfet_profile, "I_DSS_vs_Tj", T_j=25)["typ"] == pytest.approx(1e-6)
        assert M.select(mosfet_profile, "I_DSS_vs_Tj", T_j=175)["typ"] == pytest.approx(3e-6)

    def test_subscripts_survive_into_the_condition_keys(self, mosfet_profile):
        """This file emits subscripts as separate smaller spans, and the table extractor appends
        them at the END of the cell — so 'V_GS = 0 V, I_D = 0.57 mA' arrives as
        'V = 0 V, I = 0.57 mA G DS' and parses to the wrong condition names. Geometric merging is
        what makes the conditions mean anything."""
        e = _entries(mosfet_profile, "V_DSS")[0]
        assert set(e["conditions"]) == {"V_GS", "I_D"}
        assert e["conditions"]["V_GS"] == 0.0

    def test_a_summary_qualifier_files_the_value_under_the_right_field(self, mosfet_profile):
        """The page-1 summary states 'R_DS(on),max | 41 | mOhm' with no min/typ/max columns. Filing
        that under typ would put the worst-case number where the design number belongs."""
        vals = [(e.get("typ"), e.get("max")) for e in _entries(mosfet_profile, "R_DS_on")
                if not e["conditions"]]
        assert (None, 0.041) in vals, f"summary max not filed as a max: {vals}"

    def test_every_extracted_key_is_in_the_registry(self, mosfet_profile):
        for p in mosfet_profile["parameters"]:
            R.get(p["key"])

    def test_no_curve_is_invented_from_a_scalar(self, mosfet_profile):
        """The datasheet has 14 pages of vector figures. Phase 1 reads none of them, and says so,
        rather than fitting a shape through one point as the old extractor did."""
        assert mosfet_profile["curves"] == []
        assert mosfet_profile["extraction"]["phase"] == "tables_only"


_LVE = os.path.join(os.path.dirname(__file__), "..", "..", "specs", "Review",
                    "Bridge Rectifier Update", "lve5060e.pdf")


@pytest.fixture(scope="module")
def lve():
    """The bridge the designer actually uses. It extracted ZERO parameters until C217 — four
    separate layout habits, none of them exotic, each of which silently produced nothing."""
    if not os.path.exists(_LVE):
        pytest.skip("LVE5060E datasheet not available")
    with open(_LVE, "rb") as f:
        return DX.extract(f.read(), "bridge_rectifier")["profile"]


def _e(profile, key):
    return _entries(profile, key)


class TestLayoutHabitsThatProducedNothing:
    def test_the_header_is_found_below_a_spanning_title_row(self, lve):
        """Vendors put the section caption INSIDE the table, so `find_tables` returns
        "MAXIMUM RATINGS (TA = 25 degC...)" as row 0 and the real header as row 1. Testing row 0
        alone rejected 12 of 12 tables in this file."""
        assert _e(lve, "V_RRM")[0]["typ"] == 600.0

    def test_a_value_column_headed_by_the_part_number_is_recognised(self, lve):
        """"PARAMETER | SYMBOL | LVE5060E | UNIT" — the value column carries the device name, so no
        value role matched and every row parsed to nothing. An unlabelled column between the symbol
        and the unit can only be the value."""
        assert _e(lve, "R_th_jc")[0]["typ"] == pytest.approx(1.2)

    def test_a_footnote_marker_does_not_destroy_the_symbol(self, lve):
        """"VF (1)" normalised to `vf1`, which is in no symbol map, because brackets were stripped
        before the digits. A DIGIT-ONLY group is a footnote; "(AV)" in IF(AV) is part of the name."""
        assert DX._symbol_lookup("VF (1)") == DX._symbol_lookup("VF")
        assert DX._symbol_lookup("RθJA (1)(2)") == DX._symbol_lookup("RthJA")
        assert DX._symbol_lookup("IF(AV) (1)") == "ifav"        # the (AV) survives
        assert _e(lve, "V_F_vs_IF")[0]["typ"] == pytest.approx(0.89)

    def test_a_continuation_row_inherits_everything_it_left_blank(self, lve):
        """A second operating point states only what CHANGED:

            Instantaneous forward voltage | IF = 25 A | TJ = 25 C  | VF (1) | 0.89 | 0.93 | V
                                          |           | TJ = 125 C |        | 0.77 | -    |

        Read alone the second line has no symbol, no unit and no current — and it is the HOT
        forward voltage, the one value the conduction model turns on."""
        vf = {e["conditions"].get("T_j"): e for e in _e(lve, "V_F_vs_IF")}
        assert vf[125.0]["typ"] == pytest.approx(0.77)
        assert vf[125.0]["conditions"]["I_F"] == 25.0          # inherited from the row above
        ir = {e["conditions"].get("T_j"): e for e in _e(lve, "I_rev_vs_Tj")}
        assert ir[125.0]["typ"] == pytest.approx(35e-6)        # the UNIT was inherited too
        assert ir[125.0]["conditions"]["V_R"] == 600.0

    def test_a_continuation_row_does_not_inherit_a_value(self, lve):
        """The one thing it must NOT take. A blank max belongs to this row's condition, not to the
        row above; inheriting it would attach the cold limit to the hot point."""
        vf = {e["conditions"].get("T_j"): e for e in _e(lve, "V_F_vs_IF")}
        assert vf[25.0]["max"] == pytest.approx(0.93)
        assert vf[125.0].get("max") is None

    def test_the_datasheets_that_already_worked_still_do(self, lve):
        """Every fix above is additive. These counts are equalities, not floors.

        Two rose at C222, both because a row that had been DROPPED now reads. The MOSFET gained
        `R_g_int` (3.1 ohm at 1 MHz): its symbol "RG,int" tokenises as two symbols against one
        value, so positional pairing gave up on it. The SiC diode gained `I2t`: its symbol is a
        symbol-font integral sign arriving as U+F0F2, which made the token unmatchable. Both were
        checked against the printed rows before these numbers were moved.
        """
        spec = os.path.join(os.path.dirname(__file__), "..", "..", "specs")
        for path, cls, n in (
                (os.path.join(spec, "Review", "IMZA65R033M2HXKSA1.pdf"), "sic_mosfet", 21),
                (os.path.join(spec, "Bridge Rectifier Configuration", "GBJ40L06.pdf"),
                 "bridge_rectifier", 9),
                (os.path.join(spec, "Review", "PFC Boost Diode", "vs-3c40cp12l-m3.pdf"),
                 "sic_schottky", 9)):
            if not os.path.exists(path):
                continue
            with open(path, "rb") as f:
                got = DX.extract(f.read(), cls)["profile"]["parameters"]
            assert len(got) == n, (path, len(got))
