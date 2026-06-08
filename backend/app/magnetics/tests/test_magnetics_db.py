"""
app/magnetics/tests/test_magnetics_db.py
Dedicated test suite for MagneticsDB guardian.

Run: cd backend && python3 -m pytest app/magnetics/tests/ -v
These tests are independent — they test the DB layer only, not Step 7/8 calculations.
"""
import sys, math
sys.path.insert(0, ".")
import pytest, numpy as np


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def db():
    from app.magnetics.db import MagneticsDB
    return MagneticsDB()


# ── Singleton ─────────────────────────────────────────────────────────────────

class TestSingleton:

    def test_get_db_returns_same_instance(self):
        from app.magnetics.db import get_db
        a = get_db(); b = get_db()
        assert a is b, "get_db() must return the same singleton"

    def test_reload_returns_summary(self, db):
        result = db.reload()
        assert "loaded"  in result
        assert "errors"  in result
        assert result["loaded"] >= 10, "Expected at least 10 materials"


# ── Status ────────────────────────────────────────────────────────────────────

class TestStatus:

    def test_status_has_all_keys(self, db):
        s = db.status()
        for key in ["total_materials","ferrite_grades","powder_grades",
                    "ferroxcube_cores","tdk_cores","magnetics_toroids","wire_entries"]:
            assert key in s, f"Missing status key: {key}"

    def test_material_counts_reasonable(self, db):
        s = db.status()
        assert s["ferrite_grades"]    >= 10
        assert s["powder_grades"]     >= 8
        assert s["ferroxcube_cores"]  >= 30
        assert s["tdk_cores"]         >= 15
        assert s["magnetics_toroids"] >= 20
        assert s["wire_entries"]      >= 30

    def test_load_errors_empty_for_valid_db(self, db):
        assert len(db.status()["load_errors"]) == 0, \
            f"DB loaded with errors: {db.status()['load_errors']}"


# ── Material query ─────────────────────────────────────────────────────────────

class TestMaterialQuery:

    def test_get_known_ferrite(self, db):
        d = db.get_material("3C95")
        assert d["type"]     == "ferrite"
        assert d["supplier"] == "Ferroxcube"

    def test_get_known_powder(self, db):
        d = db.get_material("edge_60")
        assert d["type"]        == "powder"
        assert d["mu_initial"]  == 60

    def test_get_missing_raises(self, db):
        with pytest.raises(KeyError):
            db.get_material("nonexistent_grade_xyz")

    def test_get_materials_by_supplier(self, db):
        fc = db.get_materials(supplier="Ferroxcube")
        assert all(m["supplier"] == "Ferroxcube" for m in fc)
        assert len(fc) >= 10

    def test_get_materials_by_type(self, db):
        ferrites = db.get_materials(mat_type="ferrite")
        powders  = db.get_materials(mat_type="powder")
        assert all(m["type"] == "ferrite" for m in ferrites)
        assert all(m["type"] == "powder"  for m in powders)

    def test_get_materials_by_fsw(self, db):
        # 3C98 is optimised for 200kHz+ — should appear for 500kHz
        high_f = db.get_materials(fsw_kHz=500)
        keys = [m["_key"] for m in high_f]
        assert "3C98" in keys, "3C98 should be valid at 500kHz"

    def test_rank_grades_returns_sorted(self, db):
        ranked = db.rank_grades(fsw_Hz=70e3, Bac_pk_T=0.054, T_C=100.0)
        assert len(ranked) >= 5
        scores = [r["score"] for r in ranked]
        assert scores == sorted(scores), "Ranked list must be sorted ascending by score"


# ── Core loss calculations ────────────────────────────────────────────────────

class TestCoreLoss:

    def test_EDGE60_at_reference_point(self, db):
        """EDGE-60 at 70kHz/54mT — corrected 2026-05 from Magnetics graph (Pv_ref=400)."""
        Pv = db.get_core_loss("edge_60", 70e3, 0.054103, 25.0)
        assert abs(Pv - 53.783) / 53.783 < 0.02, \
            f"Pv={Pv:.3f} deviates >2% from Magnetics-graph reference 53.783 kW/m³"

    def test_high_B_gives_higher_loss(self, db):
        Pv_low  = db.get_core_loss("3C95", 70e3, 0.05,  100.0)
        Pv_high = db.get_core_loss("3C95", 70e3, 0.15,  100.0)
        assert Pv_high > Pv_low

    def test_high_freq_gives_higher_loss(self, db):
        Pv_70k  = db.get_core_loss("3C95", 70e3,  0.10, 100.0)
        Pv_200k = db.get_core_loss("3C95", 200e3, 0.10, 100.0)
        assert Pv_200k > Pv_70k

    def test_100C_higher_than_25C_for_ferrite(self, db):
        Pv_25  = db.get_core_loss("3C95", 100e3, 0.10, 25.0)
        Pv_100 = db.get_core_loss("3C95", 100e3, 0.10, 100.0)
        assert Pv_100 > Pv_25

    def test_mpp_lower_loss_than_koolmu(self, db):
        Pv_mpp    = db.get_core_loss("mpp_60",    70e3, 0.054, 25.0)
        Pv_koolmu = db.get_core_loss("kool_mu_60",70e3, 0.054, 25.0)
        assert Pv_mpp < Pv_koolmu, \
            f"MPP ({Pv_mpp:.1f}) should have lower loss than KoolMu ({Pv_koolmu:.1f})"

    def test_low_B_high_Vin_no_clamp_error(self, db):
        """264Vac case: Bac≈0.010T — must not be clamped to grid min. Corrected Pv_ref=400."""
        Pv = db.get_core_loss("edge_60", 70e3, 0.01006, 25.0)
        assert Pv < 3.0, f"Pv={Pv:.4f} too high — B=0.01T should give < 3.0 kW/m³"
        assert Pv > 0.01, f"Pv={Pv:.4f} suspiciously low — interpolation may be clamped"


# ── Bsat and µr ──────────────────────────────────────────────────────────────

class TestMaterialProperties:

    def test_Bsat_3C95_at_100C(self, db):
        assert abs(db.get_Bsat("3C95", 100.0) - 0.430) < 0.005

    def test_Bsat_decreases_with_temperature_ferrite(self, db):
        b25 = db.get_Bsat("3C95", 25.0)
        b100= db.get_Bsat("3C95", 100.0)
        assert b25 > b100

    def test_Bsat_powder_constant(self, db):
        b25  = db.get_Bsat("kool_mu_60", 25.0)
        b100 = db.get_Bsat("kool_mu_60", 100.0)
        assert b25 == b100, "Powder Bsat should be temperature-independent"


# ── DC bias rolloff ───────────────────────────────────────────────────────────

class TestDCBias:

    def test_k_bias_at_zero_H_is_one(self, db):
        k = db.get_k_bias("edge_60", 0.0)
        assert abs(k - 1.0) < 0.01

    def test_k_bias_decreases_with_H(self, db):
        k50  = db.get_k_bias("edge_60", 50.0)
        k200 = db.get_k_bias("edge_60", 200.0)
        assert k50 > k200

    def test_k_bias_reference_design_point(self, db):
        """At H=133 Oe: EDGE 60µ must give k_bias ≈ 0.440 (reference Step 13.4, N=49).
        Anchored to hardware-validated data for 0059894A2 3-stack design."""
        Le_s = 65.5e-3; N = 49; I_dc = 14.1522
        H_Oe = (N * I_dc / Le_s) / 79.577
        k = db.get_k_bias("edge_60", H_Oe)
        assert abs(k - 0.4398) / 0.4398 < 0.02, \
            f"k_bias={k:.4f} deviates >2% from reference 0.4398"

    def test_mpp_better_bias_than_koolmu(self, db):
        """MPP 60µ must retain more inductance than KoolMu 60µ at same H."""
        k_mpp    = db.get_k_bias("mpp_60",     133.0)
        k_koolmu = db.get_k_bias("kool_mu_60", 133.0)
        assert k_mpp > k_koolmu, \
            f"MPP k={k_mpp:.3f} should be better than KoolMu k={k_koolmu:.3f} at H=133 Oe"

    def test_ferrite_raises_on_k_bias(self, db):
        with pytest.raises(TypeError):
            db.get_k_bias("3C95", 100.0)


# ── Core catalog filtering ────────────────────────────────────────────────────

class TestCoreCatalog:

    def test_edge_3stack_fits_1U(self, db):
        cores = db.filter_cores("magnetics_inc", max_height_mm=44.45, min_Ae_mm2=150, max_stacks=3)
        edge3 = [c for c in cores if "0059894A2" in str(c.get("part_number","")) and c["stacks"]==3]
        assert len(edge3) == 1, "EDGE 0059894A2 3-stack must fit in 1U"
        assert abs(edge3[0]["Ve_total_cm3"] - 15.977) < 0.05

    def test_height_filter_works(self, db):
        all_cores = db.filter_cores("magnetics_inc", max_stacks=3)
        restricted = db.filter_cores("magnetics_inc", max_height_mm=30.0, max_stacks=3)
        assert len(restricted) <= len(all_cores)
        assert all(c["h_effective_mm"] <= 30.0 for c in restricted)

    def test_ferroxcube_etd_filtered(self, db):
        etd = db.filter_cores("ferroxcube", shape="ETD")
        assert len(etd) >= 10
        assert all(c.get("shape","").upper() == "ETD" for c in etd)

    def test_extended_flange_in_ferroxcube(self, db):
        extended = [c for c in db.filter_cores("ferroxcube") if c.get("bobbin_type")=="extended"]
        assert len(extended) >= 8, "Must have at least 8 extended-flange bobbin variants"
        for c in extended:
            assert float(c.get("bobbin_creepage_mm",0)) >= 12, \
                f"Extended bobbin {c['part_number']} has <12mm creepage"


# ── Wire catalog ──────────────────────────────────────────────────────────────

class TestWireCatalog:

    def test_reference_wire_in_catalog(self, db):
        opts = db.get_wire_options("litz", 10.07, 70e3, T_C=25.0, J_target=5.0, n_options=5)
        designations = [r.get("designation","") for r in opts]
        assert any("0.1" in d for d in designations), \
            "0.1mm strand Litz must be an option for this design"

    def test_tiw_in_catalog(self, db):
        """TIW: solid conductors used in parallel. DB suggests n_parallel needed."""
        tiw = db.get_wire_options("tiw", 10.07, 70e3, T_C=100.0, J_target=5.0, n_options=3)
        assert len(tiw) >= 1, "TIW wire must be available for Medical toroid winding"
        # Each result must suggest n_parallel conductors
        assert all("n_parallel" in r for r in tiw)
        assert all(r["n_parallel"] >= 1 for r in tiw)
        # Total Cu area must meet J target
        for r in tiw:
            assert float(r["Cu_total_mm2"]) * 5.0 >= 10.07 * 0.9

    def test_skin_depth_filter_removes_thick_strands(self, db):
        opts = db.get_wire_options("litz", 10.07, 70e3, T_C=100.0)
        # At 70kHz (100°C), max strand = 2×0.276mm = 0.552mm → 0.25mm strands pass, 0.3mm strands fail
        for opt in opts:
            d_s = float(opt.get("strand_dia_mm", 0))
            if d_s > 0:
                assert d_s <= 0.56, f"Strand dia {d_s}mm too large for 70kHz skin depth"


# ── Validation ────────────────────────────────────────────────────────────────

class TestValidation:

    def test_all_materials_pass_validation(self, db):
        errors = db.validate_all()
        assert len(errors) == 0, f"Validation errors: {errors}"

    def test_template_fails_validation(self, db):
        from app.magnetics.schema import ferrite_template
        template = ferrite_template("Test", "TestGrade")
        errors = db.validate_material_dict(template)
        assert len(errors) > 0, "Empty template must fail validation"

    def test_valid_ferrite_passes(self, db):
        good = db.get_material("3C95")
        errors = db.validate_material_dict(good)
        assert len(errors) == 0

    def test_bsat_range_rule(self, db):
        """Bsat out of range must fail business rule check."""
        d = dict(db.get_material("3C95"))
        d["Bsat_vs_T"] = {"T_C": [25,100], "Bsat": [2.0, 1.8]}  # unrealistically high
        errors = db.validate_material_dict(d)
        assert any("Bsat" in e or "bsat" in e.lower() for e in errors)


# ── Custom data entry ─────────────────────────────────────────────────────────

class TestCustomEntry:

    def test_add_invalid_material_to_pending(self, db):
        """Invalid material goes to pending, not live DB."""
        result = db.add_custom_material({
            "supplier": "TestCo", "grade": "TX001", "type": "ferrite",
            "data_source": "test", "data_quality": "custom_entered",
            # Missing most required fields
        }, commit=False)
        assert result["status"] == "pending_review"
        assert len(result["errors"]) > 0
        # Cleanup
        db.delete_pending(result["key"])

    def test_add_complete_material_to_pending(self, db):
        """A complete valid material can be added to pending for review."""
        import numpy as np
        def lt(f, B, Pv_ref=80.0, alpha=1.25, beta=2.50):
            return [[round(Pv_ref*(ff/100)**alpha*(bb/0.1)**beta,3) for ff in f] for bb in B]
        F=[25,50,70,100,200,300,500,1000]; B=[0.005,0.01,0.02,0.05,0.08,0.1,0.15,0.2,0.3,0.4]

        complete = {
            "supplier": "TestCo", "grade": "TX002", "type": "ferrite",
            "data_source": "test suite", "data_quality": "custom_entered",
            "basic": {"mu_initial": 3000, "mu_initial_tolerance_pct": 25,
                      "curie_temp_C": 220, "resistivity_ohm_m": 5.0},
            "Bsat_vs_T": {"T_C":[25,60,80,100,120], "Bsat":[0.50,0.47,0.45,0.42,0.38]},
            "mu_r_vs_T": {"T_C":[25,60,80,100,120], "mu_r":[3000,3100,3200,3000,2600]},
            "steinmetz_25C":  {"Pv_ref_kW_m3":70.0,"f_ref_kHz":100,"B_ref_T":0.10,"alpha":1.25,"beta":2.50},
            "steinmetz_100C": {"Pv_ref_kW_m3":90.0,"f_ref_kHz":100,"B_ref_T":0.10,"alpha":1.25,"beta":2.50},
            "core_loss_surface_25C":  {"T_C":25,"f_kHz":F,"B_pk_T":B,"Pv_kW_m3":lt(F,B,70.0)},
            "core_loss_surface_100C": {"T_C":100,"f_kHz":F,"B_pk_T":B,"Pv_kW_m3":lt(F,B,90.0)},
        }
        result = db.add_custom_material(complete, commit=False)
        assert result["status"] == "pending_review"
        assert len(result["errors"]) == 0, f"Valid material has errors: {result['errors']}"
        # Cleanup
        db.delete_pending(result["key"])
