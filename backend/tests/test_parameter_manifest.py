"""
Tests for required-field enforcement, provenance and condition-aware selection (M1).

M0 gave every quantity one name. M1 answers two further questions before a number is trusted:
was it actually supplied, and where did it come from?

The fixture profile below is hand-written from the real IMZA65R033M2H datasheet (Rev 2.0). It
encodes the four distinct R_DS(on) entries the part publishes, which is the case a single
`rdson_25` field cannot represent and the reason `select()` exists.
"""
import pytest

from app.mode_b.semiconductor import manifest as M
from app.mode_b.semiconductor import registry as R
from app.mode_b.semiconductor.pfc_loss_model import Mosfet


# Hand-written from the datasheet's static-characteristics table. Four R_DS(on) entries at three
# gate voltages and two junction temperatures — asking for one without conditions is a guess.
IMZA_PROFILE = {
    "schema_version": "1.0",
    "device_class": "sic_mosfet",
    "part_number": "IMZA65R033M2H",
    "parameters": [
        {"key": "R_DS_on", "entries": [
            {"typ": 0.043, "conditions": {"V_GS": 15, "I_D": 27.9, "T_j": 25}},
            {"typ": 0.033, "max": 0.041, "conditions": {"V_GS": 18, "I_D": 27.9, "T_j": 25}},
            {"typ": 0.030, "conditions": {"V_GS": 20, "I_D": 27.9, "T_j": 25}},
            {"typ": 0.054, "conditions": {"V_GS": 18, "I_D": 27.9, "T_j": 175}},
        ]},
        {"key": "Q_g", "entries": [
            {"typ": 34e-9, "conditions": {"V_GS_swing": 18, "V_DS": 400}},
        ]},
    ],
}


class TestEngineDefaultsAreVisible:
    def test_every_mosfet_field_has_a_default_that_would_fire_silently(self):
        """The premise of M1: omit a field and the engine substitutes without complaint."""
        d = M.engine_defaults("sic_mosfet")
        assert d["rdson_25"] == 0.045 and d["qgd"] == 30e-9 and d["vg_drive"] == 12.0
        assert len(d) == len(Mosfet.__dataclass_fields__)

    def test_defaults_are_resolved_per_device_class(self):
        assert M.engine_defaults("sic_schottky") != M.engine_defaults("sic_mosfet")
        assert M.engine_defaults("igbt") == {}          # no engine dataclass yet


class TestValidateBlock:
    def test_an_empty_block_names_every_missing_required_field(self):
        res = M.validate_block({}, "sic_mosfet")
        assert not res["ok"]
        keys = {d["key"] for d in res["defaulted"]}
        for expected in ("R_DS_on", "Q_g", "V_GS_drive", "E_oss_vs_VDS", "R_th_jc"):
            assert expected in keys

    def test_a_finding_states_the_value_that_would_be_used(self):
        """'A default was used' is not actionable; 'rdson_25 would be 0.045 ohm' is."""
        res = M.validate_block({}, "sic_mosfet")
        f = next(d for d in res["defaulted"] if d["key"] == "V_GS_drive")
        assert f["would_use"] == {"vg": 12.0, "vg_drive": 12.0}
        assert "12.0" in f["message"]

    def test_strict_raises_and_names_every_offender(self):
        with pytest.raises(M.MissingParameterError) as e:
            M.validate_block({}, "sic_mosfet", strict=True)
        assert "R_DS_on" in str(e.value) and "MISSING" in str(e.value)

    def test_strict_is_off_by_default_so_the_engine_stays_testable(self):
        """The gate belongs at approval and release. A hard refusal inside the engine would make
        the suite and the report harness unable to run at all."""
        assert M.validate_block({}, "sic_mosfet")["ok"] is False   # returns, does not raise

    def test_a_complete_block_passes(self):
        blk = {"tech": "sic", "rdson_25": 0.033, "ciss": 1.214e-9, "qg": 34e-9, "qgd": 6.2e-9,
               "vth": 5.6, "vpl": 7.6, "eoss_at_v": [[100, 400], [1.5e-6, 8.7e-6]],
               "rth_jc": 0.77, "rth_cs": 0.3, "rg": 1.8, "rg_on": 1.8, "rg_off": 1.8,
               "sw_method": "analytic",
               **R.expand_to_engine_fields({"V_GS_drive": 18.0})}
        res = M.validate_block(blk, "sic_mosfet")
        assert res["ok"], res["defaulted"]

    def test_provenance_can_be_required_separately(self):
        blk = {"rdson_25": 0.033}
        assert M.validate_block(blk, "sic_mosfet")["untagged"], "an untagged value should be noted"
        tagged = M.stamp(blk, {"R_DS_on": "extracted"})
        assert not M.validate_block(tagged, "sic_mosfet")["untagged"]

    def test_alias_disconnects_are_reported_alongside_missing_fields(self):
        res = M.validate_block({"vg": 15.0}, "sic_mosfet")
        assert any(d["key"] == "V_GS_drive" for d in res["disconnects"])


class TestProvenance:
    def test_stamp_rejects_an_unknown_provenance_value(self):
        with pytest.raises(ValueError):
            M.stamp({}, {"R_DS_on": "guessed"})

    def test_stamp_rejects_an_engine_field_name(self):
        """Provenance is keyed by CANONICAL name — one name per quantity, per the registry."""
        with pytest.raises(R.RegistryError):
            M.stamp({}, {"rdson_25": "extracted"})

    def test_catalogue_blocks_are_tagged_and_say_they_are_not_the_datasheet(self):
        from app.mode_b.semiconductor import database as sdb
        recs = sdb.load("mosfet")
        if not recs:
            pytest.skip("catalogue unavailable")
        blk = sdb.to_block(recs[0], "mosfet")
        prov = blk[M.PROVENANCE_KEY]
        assert prov["R_DS_on"] == "extracted"
        assert prov["Q_gd"] == "derived", "Q_gd is computed as 0.25*Q_g, not read"
        assert "catalogue" in blk[M.SOURCE_KEY] and "not the part datasheet" in blk[M.SOURCE_KEY]

    def test_provenance_and_the_legacy_estimated_list_do_not_contradict(self):
        """Two structures tracking the same fact is the disconnect pattern this project keeps
        hitting. Every field named in `_estimated` must read as 'derived' in the provenance map."""
        from app.mode_b.semiconductor import database as sdb
        recs = sdb.load("mosfet")
        if not recs:
            pytest.skip("catalogue unavailable")
        blk = sdb.to_block(recs[0], "mosfet")
        prov = blk[M.PROVENANCE_KEY]
        for field in blk.get("_estimated", []):
            base = str(field).split("(")[0]
            try:
                key = R.key_for_engine_field(base)
            except R.RegistryError:
                continue
            assert prov.get(key) == "derived", f"{base} is in _estimated but provenance says {prov.get(key)}"

    def test_provenance_rows_put_the_problems_first(self):
        """A review screen that buries unsupplied values under forty confirmed ones is the ceremony
        of verification without the substance."""
        blk = {"rdson_25": 0.033, "qg": 34e-9}
        rows = M.provenance_rows(blk, "sic_mosfet")
        assert rows[0]["supplied"] is False
        assert any(r["supplied"] for r in rows)

    def test_provenance_rows_are_human_scaled(self):
        rows = M.provenance_rows({"rdson_25": 0.033}, "sic_mosfet")
        r = next(x for x in rows if x["key"] == "R_DS_on")
        assert r["display"] == "33 mΩ"


class TestSelect:
    def test_selects_the_entry_matching_the_operating_point(self):
        assert M.select(IMZA_PROFILE, "R_DS_on", V_GS=18, T_j=25)["typ"] == 0.033
        assert M.select(IMZA_PROFILE, "R_DS_on", V_GS=18, T_j=175)["typ"] == 0.054
        assert M.select(IMZA_PROFILE, "R_DS_on", V_GS=15, T_j=25)["typ"] == 0.043
        assert M.select(IMZA_PROFILE, "R_DS_on", V_GS=20, T_j=25)["typ"] == 0.030

    def test_raises_rather_than_returning_the_first_entry(self):
        """Asking for R_DS(on) at 150 degC and silently receiving the 25 degC value is the failure
        this prevents. The engine would run happily and be 60 % wrong."""
        with pytest.raises(M.MissingParameterError) as e:
            M.select(IMZA_PROFILE, "R_DS_on", V_GS=18, T_j=150)
        assert "no entry" in str(e.value) and "V_GS=18" in str(e.value)

    def test_raises_when_conditions_are_omitted_on_a_multi_valued_parameter(self):
        with pytest.raises(M.MissingParameterError) as e:
            M.select(IMZA_PROFILE, "R_DS_on")
        assert "specify conditions" in str(e.value)

    def test_a_single_entry_parameter_needs_no_conditions(self):
        assert M.select(IMZA_PROFILE, "Q_g")["typ"] == 34e-9

    def test_unknown_canonical_key_raises(self):
        with pytest.raises(R.RegistryError):
            M.select(IMZA_PROFILE, "rdson_25")

    def test_missing_parameter_in_profile_raises(self):
        with pytest.raises(M.MissingParameterError):
            M.select(IMZA_PROFILE, "C_iss")

    def test_the_max_entry_is_reachable_for_a_worst_case_run(self):
        e = M.select(IMZA_PROFILE, "R_DS_on", V_GS=18, T_j=25)
        assert e["typ"] == 0.033 and e["max"] == 0.041


class TestDefectOneIsFixed:
    """The defect the whole registry was built after."""

    def test_sic_gate_loss_no_longer_runs_on_the_dataclass_default(self):
        from app.mode_b.semiconductor import database as sdb
        sic = [r for r in sdb.load("mosfet") if "sic" in (r.get("technology") or "").lower()]
        if not sic:
            pytest.skip("no SiC part in the catalogue")
        blk = sdb.to_block(sic[0], "mosfet")
        m = Mosfet(**{k: v for k, v in blk.items() if k in Mosfet.__dataclass_fields__})
        assert m.vg == 15.0 and m.vg_drive == 15.0
        # 12 V was a 20 % understatement of gate loss on every SiC part.
        assert m.vg_drive != Mosfet().vg_drive

    def test_the_audit_carried_by_a_calculation_result_names_what_is_missing(self):
        """A result must always be able to answer 'which of these numbers rest on assumptions?'."""
        from app.mode_b.semiconductor.adapter import parameter_audit
        from app.mode_b.semiconductor import database as sdb
        recs = sdb.load("mosfet")
        if not recs:
            pytest.skip("catalogue unavailable")
        audit = parameter_audit(sdb.to_block(recs[0], "mosfet"), {}, {})
        assert set(audit) >= {"mosfet", "diode", "bridge", "ok"}
        assert audit["mosfet"]["summary"]["by_provenance"]
