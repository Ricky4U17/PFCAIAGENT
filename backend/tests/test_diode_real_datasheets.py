"""
C222 — the diode extractor meets real vendor PDFs (closes PENDING A11).
=======================================================================
Everything downstream of extraction was covered by `test_diode_datasheet.py`, against CONSTRUCTED
profiles. The extraction layer itself had never read a diode datasheet. Two real files — a SiC
Schottky and a silicon super-fast rectifier — found seven defects, one of which produced silently
wrong loss numbers.

Every expected value below is READ OFF THE PRINTED TABLE, not off the extractor's own output.
"""
import io
import os

import pytest

from app.mode_b.semiconductor import datasheet_extract as DX

_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "specs", "Review", "PFC Boost Diode")
_SIC = os.path.join(_DIR, "vs-4c16ep07l-m3.pdf")
_SI = os.path.join(_DIR, "SFAF1601G SERIES_H2105.pdf")


def _read(p):
    if not os.path.exists(p):
        pytest.skip(f"{os.path.basename(p)} not available")
    with io.open(p, "rb") as f:
        return f.read()


@pytest.fixture(scope="module")
def sic_pdf():
    return _read(_SIC)


@pytest.fixture(scope="module")
def si_pdf():
    return _read(_SI)


def _entries(profile, key):
    return [e for p in profile.get("parameters", []) if p["key"] == key for e in p["entries"]]


def _vals(profile, key, field="typ"):
    out = []
    for e in _entries(profile, key):
        v = e.get(field)
        if v is None:
            v = e.get("max")
        out.append(v)
    return out


@pytest.fixture(scope="module")
def sic(sic_pdf):
    return DX.extract(sic_pdf, "sic_schottky")["profile"]


@pytest.fixture(scope="module")
def si(si_pdf):
    return DX.extract(si_pdf, "si_diode")["profile"]


class TestSiCSchottkyAgainstItsPrintedTables:
    """VS-4C16EP07L-M3, Vishay, 650 V Gen 4 SiC Schottky."""

    def test_capacitive_charge(self, sic):
        e = _entries(sic, "Q_c")[0]
        assert e["typ"] == pytest.approx(44e-9)
        assert e["conditions"]["V_R"] == 400.0

    def test_blocking_voltage(self, sic):
        assert _vals(sic, "V_RRM")[0] == 650.0

    def test_junction_limit_is_the_TOP_of_the_range(self, sic):
        """"Operating junction and storage temperatures | TJ(3), TStg | -55 to +175" was paired
        POSITIONALLY into TJ = -55 and TStg = +175, so the maximum junction temperature came out as
        the range's LOWER bound — the limit the whole thermal design is checked against."""
        e = _entries(sic, "Tj_max")[0]
        assert e["max"] == 175.0 and e["min"] == -55.0
        assert _entries(sic, "T_stg")[0]["max"] == 175.0

    def test_surge_current_is_not_the_repetitive_rating(self, sic):
        """I_FRM (75 A, repetitive) was mapped onto I_FSM (non-repetitive surge). Different
        ratings, and Chapter 8's inrush check compares against the surge one."""
        got = sorted(_vals(sic, "I_FSM"))
        assert got == [90.0, 101.0]
        assert 75.0 not in got

    def test_fusing_i2t(self, sic):
        """Its symbol is a symbol-font integral sign, which arrives as U+F0F2 and made the whole
        token unmatchable."""
        assert sorted(_vals(sic, "I2t")) == [40.5, 51.0]

    def test_both_capacitance_points(self, sic):
        """Two points, and BOTH are needed: one alone cannot fit the junction grading coefficient
        that C211's dissipated-charge split turns on."""
        got = sorted(_vals(sic, "C_j"))
        assert got[0] == pytest.approx(63e-12)
        assert got[1] == pytest.approx(737e-12)

    def test_a_package_dimension_is_not_a_capacitance(self, sic):
        """The mechanical drawing calls a lead thickness "c" (0.38–0.89 mm). Mapping the bare
        letter globally imported it as a junction capacitance."""
        for v in _vals(sic, "C_j"):
            assert v < 1e-8                      # farads, not millimetres

    def test_forward_voltage_at_three_temperatures(self, sic):
        by_t = {(e["conditions"].get("T_j"), e["typ"]) for e in _entries(sic, "V_F_vs_IF")}
        assert (None, 1.3) in by_t and (150.0, 1.45) in by_t and (175.0, 1.55) in by_t

    def test_thermal_resistance(self, sic):
        e = _entries(sic, "R_th_jc")[0]
        assert e["typ"] == 1.0 and e["max"] == 1.3

    def test_a_single_part_document_reports_no_variants(self, sic_pdf):
        assert DX.find_variants(sic_pdf) == []


class TestSiliconSuperFastAgainstItsPrintedTables:
    """SFAF1601G–SFAF1608G, Taiwan Semiconductor, 16 A 50–600 V super-fast rectifier."""

    def test_junction_limit(self, si):
        assert 150.0 in _vals(si, "Tj_max")

    def test_surge_current(self, si):
        assert 200.0 in _vals(si, "I_FSM")

    def test_reverse_recovery_time(self, si):
        """The parameter the whole silicon path turns on: C210 reconstructs Q_rr from t_rr."""
        e = _entries(si, "t_rr")[0]
        assert (e.get("max") or e.get("typ")) == pytest.approx(35e-9)


class TestSeriesVariants:
    def test_every_variant_is_found(self, si_pdf):
        assert DX.find_variants(si_pdf) == [f"SFAF160{n}G" for n in range(1, 9)]

    def test_without_a_choice_the_bands_are_all_kept(self, si_pdf):
        """Visible rather than silently resolved: three forward voltages for one key is something
        the review screen and the cross-check both report."""
        res = DX.extract(si_pdf, "si_diode")
        assert res["variant_required"] is True
        assert sorted(_vals(res["profile"], "V_F_vs_IF")) == [0.975, 1.3, 1.7]

    @pytest.mark.parametrize("variant,v_f,c_j", [
        ("SFAF1601G", 0.975, 130e-12),
        ("SFAF1604G", 0.975, 130e-12),
        ("SFAF1606G", 1.300, 100e-12),
        ("SFAF1608G", 1.700, 100e-12),
    ])
    def test_the_chosen_part_gets_its_own_band(self, si_pdf, variant, v_f, c_j):
        """THE DEFECT THIS CLOSES: the part number resolved to the LAST variant while the banded
        values came from the FIRST, so SFAF1608G reported 0.975 V against a real 1.700 V — a 43 %
        understatement feeding straight into conduction loss."""
        prof = DX.extract(si_pdf, "si_diode", variant=variant)["profile"]
        assert prof["part_number"] == variant
        assert _vals(prof, "V_F_vs_IF") == [pytest.approx(v_f)]
        assert _vals(prof, "C_j") == [pytest.approx(c_j)]

    def test_an_unknown_part_number_does_not_filter_anything_away(self, si_pdf):
        """A part number this document does not cover says nothing about the bands. Filtering on it
        would drop every banded row and leave a profile that looks like a part with no forward
        voltage at all."""
        res = DX.extract(si_pdf, "si_diode", variant="NOT-IN-THIS-SERIES")
        assert res["variant"] is None
        assert len(_vals(res["profile"], "V_F_vs_IF")) == 3


class TestWhatReachesTheEngine:
    def test_the_hot_forward_curve_is_one_temperature(self, sic_pdf):
        """The part publishes V_F at 150 degC AND at 175 degC, both at 16 A. Returning both built a
        curve whose x was [16, 16] — two points at one current, which is not a function."""
        import tempfile, shutil, sys
        sys.path.insert(0, os.path.dirname(__file__))
        from test_bridge_datasheet import DESIGN
        from app.mode_b.semiconductor import datasheet_flow as DF
        from app.mode_b.semiconductor import parts_store as PS
        d = tempfile.mkdtemp(prefix="realdiode_")
        try:
            mpn = DF.upload(sic_pdf, "diode", "sic_schottky", root=d)["part_number"]
            blk = DF.profile_to_block(PS.load_profile(mpn, kind="extracted", root=d),
                                      "sic_schottky", DESIGN)
            xs = blk["vf_curve_hot"][0]
            assert len(xs) == len(set(xs))
            assert blk["vf_thot"] == 175.0
            # the surge ratings and the junction limit must REACH the block, not merely extract
            assert blk["ifsm_A"] == 101.0 and blk["i2t_A2s"] == 51.0 and blk["_tj_max_C"] == 175.0
            # UNDERSCORE-PREFIXED so `_clean_block` routes it to metadata by convention.
            # Named without one it stayed in params and Diode(**params) refused it — the
            # same C218 trap, walked into again one commit after documenting it.
            from app.mode_b.semiconductor.adapter import _clean_block
            from app.mode_b.semiconductor.pfc_loss_model import Diode
            params, meta = _clean_block(blk)
            assert "_tj_max_C" in meta and "_tj_max_C" not in params
            Diode(**params)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_the_grading_coefficient_is_fitted_from_the_parts_own_points(self, sic_pdf):
        """With one capacitance point m falls back to 0 and C211's dissipated share is 0.500. With
        the pair it is fitted, and this part's own value moves it to 0.629."""
        import tempfile, shutil, sys
        sys.path.insert(0, os.path.dirname(__file__))
        from test_bridge_datasheet import DESIGN
        from app.mode_b.semiconductor import datasheet_flow as DF
        from app.mode_b.semiconductor import parts_store as PS
        d = tempfile.mkdtemp(prefix="realdiode_")
        try:
            mpn = DF.upload(sic_pdf, "diode", "sic_schottky", root=d)["part_number"]
            blk = DF.profile_to_block(PS.load_profile(mpn, kind="extracted", root=d),
                                      "sic_schottky", DESIGN)
            note = next((n for n in (blk.get("_checks") or [])
                         if n["key"] == "C_j_grading"), None)
            assert note is not None and "0.4" in note["message"]
        finally:
            shutil.rmtree(d, ignore_errors=True)
