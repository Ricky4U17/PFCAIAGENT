"""
Tests for the canonical parameter registry (M0).

The registry's whole purpose is to make naming disconnects impossible to introduce silently, so
these tests are the enforcement, not a formality. Three groups:

  TestRegistryIsWellFormed  — the file itself is consistent.
  TestNoDisconnects         — the registry and the engine agree, in BOTH directions.
  TestKnownDisconnects      — a frozen baseline of the disconnects that exist TODAY.

That last group needs explaining. M0 builds the registry; M1 fixes the defects it finds. A test
that simply failed on the known `vg`/`vg_drive` split would leave the suite red for a milestone,
which trains people to ignore it. Instead the baseline pins the exact set of current issues: a NEW
disconnect fails the suite immediately, and when M1 fixes one the baseline must shrink or the test
fails for being out of date. Neither direction can drift unnoticed.
"""
import dataclasses as dc

import pytest

from app.mode_b.semiconductor import registry as R
from app.mode_b.semiconductor.pfc_loss_model import Mosfet, Diode, Bridge


class TestRegistryIsWellFormed:
    def test_loads_and_self_validates(self):
        reg = R.load()
        assert reg["schema_version"]
        assert reg["parameters"] and reg["units"] and reg["device_classes"]

    def test_every_canonical_key_is_unique(self):
        keys = [p["key"] for p in R.load()["parameters"]]
        assert len(keys) == len(set(keys))

    def test_every_engine_field_is_claimed_by_exactly_one_key(self):
        """Two canonical keys claiming one engine field would reintroduce the ambiguity the
        registry removes. `load()` enforces this; asserting it here documents why."""
        owner = {}
        for p in R.load()["parameters"]:
            for ef in p.get("engine_fields", []):
                assert ef not in owner, f"{ef} claimed by {owner.get(ef)} and {p['key']}"
                owner[ef] = p["key"]

    def test_display_units_belong_to_their_si_unit(self):
        units = R.load()["units"]
        for p in R.load()["parameters"]:
            assert units[p["display_unit"]]["si"] == p["si_unit"], p["key"]

    def test_unit_round_trip(self):
        assert R.to_si("R_DS_on", 33, "mohm") == pytest.approx(0.033)
        val, label = R.to_display("R_DS_on", 0.033)
        assert val == pytest.approx(33.0) and label == "mΩ"

    def test_display_unit_is_what_a_reviewer_reads(self):
        """A confirmation screen showing 0.033 instead of 33 mOhm is how a wrong value survives
        review. Every parameter must resolve to a human-scaled number."""
        for key, si in (("R_DS_on", 0.033), ("Q_g", 34e-9), ("E_oss_vs_VDS", 8.7e-6),
                        ("C_iss", 1.214e-9)):
            val, _ = R.to_display(key, si)
            assert 0.1 <= abs(val) < 10000, f"{key} displays as {val}"

    def test_unknown_key_raises_rather_than_returning_none(self):
        with pytest.raises(R.RegistryError):
            R.get("R_DS_ON")            # wrong case is a different name
        with pytest.raises(R.RegistryError):
            R.get("rdson_25")           # engine field, not a canonical key
        with pytest.raises(R.RegistryError):
            R.key_for_engine_field("not_a_field")

    def test_conduction_loss_form_is_a_property_of_device_class(self):
        """I^2*R is right for a MOSFET and wrong for an IGBT. The engine must select the form from
        the class, never assume one globally."""
        assert R.conduction_loss_form("sic_mosfet") == "i2r"
        assert R.conduction_loss_form("si_mosfet") == "i2r"
        assert R.conduction_loss_form("igbt") == "vce0_plus_rce"
        assert R.conduction_loss_form("sic_schottky") == "vf_plus_rd"

    def test_device_class_guards_are_declared(self):
        assert R.device_class("gan_hemt")["qrr_expected"] == "zero"
        assert R.device_class("gan_hemt")["has_body_diode"] is False

    def test_multi_valued_parameters_declare_their_conditions(self):
        """R_DS(on) has four entries on the reference part (V_GS 15/18/20 V at 25 degC, plus 18 V
        at 175 degC). A parameter that can hold several values must say what distinguishes them."""
        for p in R.load()["parameters"]:
            if p.get("multi_valued"):
                assert p.get("condition_qualified"), p["key"]
                assert p.get("conditions"), p["key"]
        assert "R_DS_on" in R.summary()["multi_valued"]

    def test_energy_parameters_require_a_measurement_basis(self):
        """Convention B de-bundles E_oss and recovery charge out of a published E_on. That is only
        possible when the measurement basis is recorded, so the requirement is declared here."""
        for key in ("E_on", "E_off"):
            assert R.get(key).get("requires_measurement_basis") is True

    def test_curves_that_feed_calculations_require_an_anchor(self):
        """An extracted curve must reproduce a tabulated value before it may drive a number."""
        for key in ("E_on_vs_ID", "E_off_vs_ID", "E_oss_vs_VDS", "V_F_vs_IF"):
            assert R.get(key).get("requires_anchor") is True, key

    def test_design_sourced_parameters_are_marked_as_such(self):
        """No datasheet upload can supply a gate resistor or a mounting interface. Marking them
        'design' is what stops them becoming silent defaults again."""
        for key in ("V_GS_drive", "R_g_on", "R_g_off", "R_th_cs", "L_loop"):
            assert R.get(key)["source"] == "design", key

    def test_plausible_ranges_are_ordered_and_contain_real_values(self):
        for key, real in (("R_DS_on", 0.033), ("Q_g", 34e-9), ("E_oss_vs_VDS", 8.7e-6),
                          ("V_DSS", 650.0), ("R_th_jc", 0.77), ("C_iss", 1.214e-9)):
            rng = R.get(key)["plausible"]
            assert rng["min"] <= real <= rng["max"], f"{key}: {real} outside {rng}"


class TestNoDisconnects:
    def test_every_engine_dataclass_field_is_registered(self):
        """The engine grew a parameter and nobody told the registry — the drift this catches."""
        audit = R.audit_engine_dataclasses()
        assert not audit["unregistered"], (
            f"engine fields with no canonical key: {audit['unregistered']}")

    def test_every_registered_engine_field_exists_on_a_dataclass(self):
        """The engine dropped or renamed a field and nobody told the registry."""
        audit = R.audit_engine_dataclasses()
        assert not audit["orphaned"], (
            f"registry names engine fields that do not exist: {audit['orphaned']}")

    def test_coverage_is_complete_across_all_three_dataclasses(self):
        registered = set()
        for p in R.load()["parameters"]:
            registered |= set(p.get("engine_fields", []))
        for cls in (Mosfet, Diode, Bridge):
            fields = {f.name for f in dc.fields(cls)}
            assert fields <= registered, f"{cls.__name__}: {sorted(fields - registered)}"

    def test_expand_to_engine_fields_writes_every_alias(self):
        """The structural fix: a caller supplies one canonical value and cannot write half of it."""
        out = R.expand_to_engine_fields({"V_GS_drive": 18.0})
        assert out == {"vg": 18.0, "vg_drive": 18.0}

    def test_expand_rejects_an_unknown_key(self):
        with pytest.raises(R.RegistryError):
            R.expand_to_engine_fields({"V_gs_drive": 18.0})

    def test_expanded_fields_are_accepted_by_the_engine(self):
        """Naming agreement is worthless if the engine will not take the kwargs."""
        m = Mosfet(**R.expand_to_engine_fields({"V_GS_drive": 18.0, "R_g_on": 1.8}))
        assert m.vg == 18.0 and m.vg_drive == 18.0 and m.rg == 1.8

    def test_audit_block_catches_a_partial_alias_write(self):
        findings = R.audit_block({"vg": 15.0})
        assert len(findings) == 1
        assert findings[0]["issue"] == "partial_write" and findings[0]["key"] == "V_GS_drive"

    def test_audit_block_catches_inconsistent_alias_values(self):
        findings = R.audit_block({"vg": 15.0, "vg_drive": 12.0})
        assert len(findings) == 1 and findings[0]["issue"] == "inconsistent"

    def test_audit_block_is_clean_when_expand_was_used(self):
        assert R.audit_block(R.expand_to_engine_fields({"V_GS_drive": 18.0})) == []


class TestNoKnownDisconnectsRemain:
    """The baseline is now EMPTY, and that is the point.

    M0 recorded one disconnect here: `to_block` wrote `vg` and not `vg_drive`. M1 fixed it at
    source by routing the value through `registry.expand_to_engine_fields`, and the baseline test
    refused to pass until this list was updated — which is exactly the behaviour it was built for.
    A new disconnect now fails immediately against an empty set.
    """

    BASELINE: set = set()

    def _live_mosfet_block(self, sic: bool = False):
        from app.mode_b.semiconductor import database as sdb
        recs = sdb.load("mosfet")
        if sic:
            recs = [r for r in recs if "sic" in (r.get("technology") or "").lower()]
        if not recs:
            pytest.skip("MOSFET catalogue unavailable")
        return sdb.to_block(recs[0], "mosfet")

    @pytest.mark.parametrize("sic", [False, True])
    def test_to_block_has_no_naming_disconnects(self, sic):
        """Runs on both technologies deliberately — see the masking note below."""
        found = {(f["key"], f["issue"]) for f in R.audit_block(self._live_mosfet_block(sic))}
        assert found == self.BASELINE, f"naming disconnect: {sorted(found)}"

    @pytest.mark.parametrize("sic", [False, True])
    def test_both_gate_drive_aliases_are_written_and_agree(self, sic):
        """The defect this whole registry was built after: gate loss ran on the dataclass default
        of 12 V while the switching model used the value `to_block` chose.

        MASKING, and why the structural audit matters more than a value check: on a SILICON part
        `to_block` writes 12 V, which happens to equal the dataclass default, so the two agreed by
        coincidence and the defect was invisible. It only showed on SiC — 15 V written, 12 V used,
        a 20 % error on gate loss. Two thirds of the catalogue would have hidden it from a
        value-based test, which is why `audit_block` checks whether every alias was WRITTEN.
        """
        blk = self._live_mosfet_block(sic)
        assert "vg" in blk and "vg_drive" in blk, "an alias is missing again"
        m = Mosfet(**{k: v for k, v in blk.items() if k in Mosfet.__dataclass_fields__})
        assert m.vg == m.vg_drive

    def test_sic_gate_drive_is_no_longer_the_dataclass_default(self):
        """Pins the fix numerically: SiC must carry 15 V through to gate loss, not fall back to 12."""
        blk = self._live_mosfet_block(sic=True)
        m = Mosfet(**{k: v for k, v in blk.items() if k in Mosfet.__dataclass_fields__})
        assert m.vg_drive == 15.0
        assert m.vg_drive != Mosfet().vg_drive, "gate loss is on the default again"
