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
        Chapter 8 bridge-surge gate reports OPEN. They are in the datasheet table."""
        assert _entries(extracted["profile"], "I_FSM")[0]["typ"] == 420.0
        assert _entries(extracted["profile"], "I2t")[0]["typ"] == 732.0

    def test_forward_voltage_arrives_with_its_conditions(self, extracted):
        """A V_F of 0.87 V is not a fact. 0.87 V at I_F = 20 A, T_j = 25 degC is."""
        e = _entries(extracted["profile"], "V_F_vs_IF")[0]
        assert e["typ"] == pytest.approx(0.87) and e["max"] == pytest.approx(0.90)
        assert e["conditions"] == {"I_F": 20.0, "T_j": 25.0}

    def test_a_value_in_the_max_column_is_not_lost_to_a_dash_in_typ(self, extracted):
        """`IR | — | — | 10 | µA`. A dash is truthy, so choosing the first NON-EMPTY value column
        silently dropped the parameter; the column must be chosen by whether it holds a number."""
        e = _entries(extracted["profile"], "I_rev_vs_Tj")[0]
        assert e["max"] == pytest.approx(1e-5)      # 10 µA, scaled to SI

    def test_a_temperature_range_yields_both_bounds(self, extracted):
        e = _entries(extracted["profile"], "Tj_max")[0]
        assert e["min"] == -40.0 and e["max"] == 150.0

    def test_units_are_converted_to_si(self, extracted):
        assert _entries(extracted["profile"], "C_iss")[0]["min"] == pytest.approx(400e-12)

    def test_several_parameters_packed_into_one_row_are_unpacked(self):
        """`RthJC RthJL RthJA | 5 9 24` is three parameters, not one named
        'RthJC RthJL RthJA' with the value '5 9 24'."""
        assert DX.split_packed_row("RθJC RθJL RθJA", "5 9 24") == [
            ("RθJC", 5.0), ("RθJL", 9.0), ("RθJA", 24.0)]

    def test_packed_rows_refuse_to_guess_when_counts_disagree(self):
        """Three symbols against two numbers has no safe alignment. Reporting nothing beats
        pairing them wrongly."""
        assert DX.split_packed_row("A B C", "1 2") == []

    def test_several_conditions_under_one_symbol_are_all_kept(self, extracted):
        """`IF(AV) | 40 5 | A` is the rating with and WITHOUT a heatsink. Taking the first number
        discards an operating point the designer may be relying on."""
        e = _entries(extracted["profile"], "I_F_AV")[0]
        assert e["values"] == [40.0, 5.0] and e["typ"] == 40.0

    def test_unmapped_symbols_are_reported_not_dropped(self, extracted):
        """R_thetaJL and R_thetaJA are real datasheet parameters our engine does not model. They
        belong in `unresolved` so a reviewer can see what the parser gave up on."""
        syms = {u["symbol"] for u in extracted["profile"]["unresolved"]}
        assert "RθJL" in syms and "RθJA" in syms

    def test_nothing_maps_to_a_name_outside_the_registry(self, extracted):
        for p in extracted["profile"]["parameters"]:
            R.get(p["key"])                          # raises if the key was invented


class TestCrossCheck:
    def test_a_repeated_parameter_with_different_values_is_flagged(self, extracted):
        """The fixture publishes two thermal tables for two mounting variants, so R_th(j-c) comes
        out as both 5 and 2 degC/W. That ambiguity must reach the reviewer, not be resolved by
        whichever table happened to parse first."""
        flagged = {c["key"] for c in extracted["cross_check"]}
        assert "R_th_jc" in flagged

    def test_the_summary_and_detail_blocks_agree_on_the_voltage_rating(self, extracted):
        """V_RRM in the product summary and V_B in the electrical table are both 600 V. Agreement
        between an independently-parsed summary and detail is free validation."""
        vals = {e.get("typ") or e.get("min") for e in _entries(extracted["profile"], "V_DSS")}
        assert vals == {600.0}


class TestTemplates:
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
