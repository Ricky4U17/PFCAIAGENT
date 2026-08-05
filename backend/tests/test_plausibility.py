"""
Tests for the plausibility gate (app/plausibility.py).

Two properties matter more than any individual rule, and both are asserted against the real
catalogues rather than fixtures:

  1. NO FALSE FLAGS. Every part already in a vendor catalogue must pass its own rules. A gate that
     flags real parts is one a designer stops reading, at which point it protects nothing.
  2. IT CATCHES THE FAILURE IT EXISTS FOR. A misplaced decimal point is a factor of ten, so a x10
     slip injected into a real part should be caught most of the time.

The detection floors below are deliberately a little under the measured rates (mosfet 79, diode 79,
bridge 86, ntc 54, relay 76, fuse 67, core 100, mov 100 at the time of writing), so ordinary
catalogue growth does not turn a green suite red. A LARGE drop means a rule stopped firing and is
worth investigating; that is what these guard.
"""
import random

import pytest

from app import plausibility as pl


def _catalogues():
    """(kind, records, numeric fields worth perturbing) for every catalogue that loads."""
    out = []
    try:
        from app.mode_b.semiconductor import database as sdb
        out += [("mosfet", sdb.load("mosfet"), ["rdson", "qg", "vdss", "vth", "id_25"]),
                ("diode", sdb.load("diode"), ["vf", "vr", "io"]),
                ("bridge", sdb.load("bridge"), ["vf", "vr", "io"])]
    except Exception:
        pass
    try:
        from app.mode_b.inputprotection import database as ipdb
        out += [("ntc", ipdb.load(), ["r25", "imax", "r_hot_mohm", "diameter_mm"]),
                ("relay", ipdb.load_relay(), ["contact_i_A", "switch_v_V", "coil_i_mA", "t_operate_ms"]),
                ("fuse", ipdb.load_fuse(), ["i_rated_A", "v_ac_V", "melting_i2t"])]
        try:
            out.append(("mov", ipdb.load_mov(), ["mcov", "v1ma"]))
        except Exception:
            pass
    except Exception:
        pass
    try:
        from app.magnetics.db import get_db
        out.append(("core", get_db()._cores_mag,
                    ["Ae_mm2", "Le_mm", "Ve_cm3", "OD_mm", "AL_nom_nH"]))
    except Exception:
        pass
    return [(k, r, f) for k, r, f in out if r]


CATALOGUES = _catalogues()
MIN_DETECTION = {"mosfet": 0.65, "diode": 0.65, "bridge": 0.70, "ntc": 0.40,
                 "relay": 0.60, "fuse": 0.50, "core": 0.90, "mov": 0.90}


@pytest.mark.skipif(not CATALOGUES, reason="no vendor catalogue available")
class TestNoFalseFlags:
    def test_every_catalogue_part_passes_its_own_rules(self):
        """The single most important property: a real part is never flagged."""
        offenders = []
        for kind, recs, _ in CATALOGUES:
            for rec in recs:
                res = pl.check(kind, rec)
                if not res["ok"]:
                    offenders.append((kind, rec.get("part_number"),
                                      res["findings"][0]["rule"], res["findings"][0]["message"]))
        assert not offenders, (
            f"{len(offenders)} catalogue parts flagged; first few: {offenders[:5]}")

    def test_rules_actually_ran(self):
        """Guards against the opposite failure — a green result because nothing was evaluated."""
        for kind, recs, _ in CATALOGUES:
            evaluated = [pl.check(kind, r)["checked"] for r in recs[:200]]
            assert max(evaluated) >= 2, f"{kind}: no part had 2+ rules evaluated"


@pytest.mark.skipif(not CATALOGUES, reason="no vendor catalogue available")
class TestCatchesDecimalSlips:
    @pytest.mark.parametrize("kind", [c[0] for c in CATALOGUES])
    def test_x10_slip_is_caught(self, kind):
        recs, fields = next((r, f) for k, r, f in CATALOGUES if k == kind)
        rng = random.Random(20260804)
        caught = trials = 0
        for _ in range(800):
            rec = dict(rng.choice(recs))
            fld = rng.choice(fields)
            if not isinstance(rec.get(fld), (int, float)) or not rec.get(fld):
                continue
            rec[fld] = rec[fld] * rng.choice([10.0, 0.1])
            trials += 1
            if not pl.check(kind, rec)["ok"]:
                caught += 1
        assert trials >= 50, f"{kind}: too few usable trials ({trials})"
        rate = caught / trials
        assert rate >= MIN_DETECTION[kind], (
            f"{kind}: x10 slips caught {rate:.0%}, floor {MIN_DETECTION[kind]:.0%}")


class TestKnownDefects:
    """The specific mistakes this gate was built after."""

    def test_C115_geometric_volume_mistaken_for_Ve(self):
        """C115 spent an investigation on a Ve of 15.98 cm3 where the datasheet says 4.15.
        Ve = Ae x le settles it in one line."""
        r = pl.check("core", {"Ae_mm2": 65.4, "Le_mm": 63.5, "Ve_cm3": 15.98})
        assert not r["ok"]
        assert any(f["rule"] == "core.Ve_identity" for f in r["findings"])

    def test_the_same_core_with_the_right_Ve_passes(self):
        r = pl.check("core", {"Ae_mm2": 65.4, "Le_mm": 63.5, "Ve_cm3": 4.15})
        assert r["ok"] and r["checked"] >= 1

    def test_swapped_OD_and_ID(self):
        r = pl.check("core", {"OD_mm": 14.7, "ID_mm": 27.7})
        assert not r["ok"] and any(f["rule"] == "core.OD_gt_ID" for f in r["findings"])

    def test_NTC_hot_and_cold_resistance_swapped(self):
        """R25 10 ohm with R_hot 0.05 ohm is an ordinary NTC. Enter them the other way round and
        the part would have to RISE with temperature, which an NTC does not."""
        r = pl.check("ntc", {"r25": 0.05, "r_hot_mohm": 10000.0})
        assert not r["ok"] and any(f["rule"] == "ntc.rhot_lt_r25" for f in r["findings"])

    def test_NTC_hot_resistance_entered_in_the_wrong_unit(self):
        """R_hot is 0.05 ohm; typing 0.05 into a field that wants milliohms is 1000x low. The
        hot/cold ratio catches it even though neither value on its own looks impossible."""
        r = pl.check("ntc", {"r25": 10.0, "r_hot_mohm": 0.05})
        assert not r["ok"] and any(f["rule"] == "ntc.rhot_over_r25" for f in r["findings"])

    def test_MOSFET_vth_and_vdss_swapped(self):
        r = pl.check("mosfet", {"vth": 650.0, "vdss": 4.5})
        assert not r["ok"] and any(f["rule"] == "mosfet.vth_lt_vdss" for f in r["findings"])


class TestContract:
    def test_never_rejects_and_never_raises(self):
        """Advisory only: no input may produce an exception or a blocking verdict."""
        for kind in list(pl.KINDS) + ["nonsense", "", None]:
            for rec in ({}, {"part_number": "X"}, {"vf": "not a number"}, {"vf": None}):
                res = pl.check(kind, rec)
                assert isinstance(res["findings"], list)
                assert "blocked" not in res and "reject" not in res

    def test_unknown_kind_is_reported_not_raised(self):
        res = pl.check("flux_capacitor", {"x": 1})
        assert res["ok"] and res["checked"] == 0 and "no rules" in res["note"]

    def test_bands_are_measured_from_real_parts(self):
        bands = pl.band_report()
        if not bands:
            pytest.skip("no catalogue available")
        for key, b in bands.items():
            assert b["lo"] <= b["hi"], key
            assert b["parts"] and b["parts"] >= 20, f"{key} built from too few parts"

    def test_no_rule_checks_a_derived_field_against_its_own_derivation(self):
        """`energy_est_J` is computed from the disc diameter at ingest, so a rule comparing the two
        could never fire. Guards the docstring's warning against a future well-meaning addition."""
        assert "ntc.energy" not in pl.band_report()
