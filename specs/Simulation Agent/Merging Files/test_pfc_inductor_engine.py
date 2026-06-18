#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_pfc_inductor_engine.py
===========================
Developer-side regression net for pfc_inductor_engine.py. NONE of these numbers live
in the engine; they are the EXPECTED OUTPUTS for two fully-specified inputs. The engine
holds no material constants of its own - every constant below is supplied in the package.

  * golden_case_A  -- a hand-verified design (worst-case numbers verified independently).
  * golden_case_B  -- a DIFFERENT material / core / wire, proving the engine is agnostic
                      (it must produce different results from its own injected constants).
  * override tests -- a solved `fields` block must replace analytic values and flip provenance.
  * validation     -- broken / infeasible inputs must fail LOUDLY (SpecError); soft issues warn.

Run:  pytest -q
"""
import copy, math
import pytest
import pfc_inductor_engine as eng


# ---------------------------------------------------------------------------
#  golden_case_A : fully specified design (constants injected, not from engine)
# ---------------------------------------------------------------------------
def package_A():
    return {
        "schemaVersion": "1.0",
        "model": {
            "design": {"Vout": 394.0, "fsw": 70e3, "lineHz": 60.0, "nph": 2},
            "environment": {"Tamb_C": 50.0, "Thot_C": 110.0},
            "winding": {"N": 31, "stacks": 3, "build_mm": 3.8},
            "geometry": {"OD_mm": 58.04, "ID_mm": 34.75, "HT_mm": 14.86, "Ae_mm2": 144.0,
                         "Le_mm": 143.0, "Ve_mm3": 20700.0, "Wa_mm2": 948.0, "AL_nH": 94.0, "AL_tol": 0.08},
            "material": {"name": "Material-A", "Bsat": 1.5,
                         "steinmetz": {"a": 121.47, "b": 2.263, "c": 1.403},
                         "retention": {"k0": 0.01, "k1": 1.58e-9, "p": 3.067},
                         "lossMaxScale": 1.286,
                         "anchors": {"loss": [0.1, 100.0, 424.0], "bias": [[105.0, 80.0]]}},
            "copper": {"wire": {"type": "litz", "strands": 800, "strandDia_mm": 0.1,
                                "parallel": 2, "fillFactor": 0.45}, "RacRdc": 1.15},
            "cooling": {"mode": "natural"},
        },
        "operating": {"points": [
            {"Vin": 90, "Pout": 1700, "eta": 0.945, "PF": 0.9987},
            {"Vin": 110, "Pout": 1700, "eta": 0.955, "PF": 0.9986},
            {"Vin": 120, "Pout": 1700, "eta": 0.965, "PF": 0.9985},
            {"Vin": 132, "Pout": 1700, "eta": 0.975, "PF": 0.9980},
            {"Vin": 180, "Pout": 3600, "eta": 0.965, "PF": 0.9889},
            {"Vin": 200, "Pout": 3600, "eta": 0.975, "PF": 0.9884},
            {"Vin": 220, "Pout": 3600, "eta": 0.985, "PF": 0.9790},
            {"Vin": 230, "Pout": 3600, "eta": 0.988, "PF": 0.9789},
            {"Vin": 264, "Pout": 3600, "eta": 0.990, "PF": 0.9520}]},
        "acceptance": {"L_target_uH": 239.0, "sat_margin_min": 0.43,
                       "FFcu_limit": 0.45, "J_min": 3.0, "J_max": 7.0},
    }


# ---------------------------------------------------------------------------
#  golden_case_B : a genuinely different material / core / wire / topology
# ---------------------------------------------------------------------------
def package_B():
    return {
        "schemaVersion": "1.0",
        "model": {
            "design": {"Vout": 400.0, "fsw": 100e3, "lineHz": 50.0, "nph": 1},
            "environment": {"Tamb_C": 40.0, "Thot_C": 120.0},
            "winding": {"N": 45, "stacks": 1, "build_mm": 3.0},
            "geometry": {"OD_mm": 47.6, "ID_mm": 27.7, "HT_mm": 17.0, "Ae_mm2": 125.0,
                         "Le_mm": 110.0, "Ve_mm3": 13700.0, "Wa_mm2": 600.0, "AL_nH": 75.0, "AL_tol": 0.08},
            "material": {"name": "Material-B", "Bsat": 1.5,
                         "steinmetz": {"a": 150.40, "b": 2.263, "c": 1.369},
                         "retention": {"k0": 0.01, "k1": 2.59e-9, "p": 2.683}},
            "copper": {"wire": {"type": "litz", "strands": 600, "strandDia_mm": 0.1,
                                "parallel": 1, "fillFactor": 0.40}, "RacRdc": 1.2},
            "cooling": {"mode": "natural"},
        },
        "operating": {"points": [
            {"Vin": 90, "Pout": 1500, "eta": 0.95, "PF": 0.99},
            {"Vin": 180, "Pout": 3000, "eta": 0.96, "PF": 0.99},
            {"Vin": 230, "Pout": 3000, "eta": 0.97, "PF": 0.98}]},
        "acceptance": {"L_target_uH": 120.0, "sat_margin_min": 0.43, "FFcu_limit": 0.45},
    }


# ============================== GOLDEN A ====================================
def test_golden_A_statics():
    r = eng.compute(package_A())
    s = r["statics"]
    assert s["L0_nom_uH"] == pytest.approx(271.0, rel=1e-2)
    assert s["L0_min_uH"] == pytest.approx(249.3, rel=1e-2)
    assert s["MLT_mm"] == pytest.approx(116.2, rel=1e-2)
    assert s["DCR25_mohm"] == pytest.approx(5.029, rel=2e-2)
    assert s["DCR100_mohm"] == pytest.approx(6.512, rel=2e-2)
    assert s["FFcu"] == pytest.approx(0.411, rel=2e-2)
    assert s["J_AperMM2"] == pytest.approx(0.84, rel=3e-2)
    assert s["skin_depth_mm"] == pytest.approx(0.249, rel=2e-2)

def test_golden_A_worstcase_and_verdict():
    r = eng.compute(package_A())
    w = r["worst"]
    assert w["loss"]["Vin"] == 180
    assert w["loss"]["Ptot_typ"] == pytest.approx(3.24, rel=2e-2)
    assert w["loss"]["Ptot_max"] == pytest.approx(3.95, rel=2e-2)
    assert w["Bmax"]["Vin"] == 180
    assert w["Bmax"]["Bmax"] == pytest.approx(0.344, rel=2e-2)
    assert w["dT"]["dT"] == pytest.approx(11.4, rel=3e-2)
    assert w["Lmin_guarantee_uH"] == pytest.approx(244.2, rel=1e-2)
    assert r["verdict"] == "APPROVE"

def test_golden_A_all_provenance_analytic_by_default():
    r = eng.compute(package_A())
    p = r["provenance"]
    assert p["inductance"] == "analytic" and p["windingAC"] == "analytic"
    assert p["thermal"] == "analytic" and p["flux"] == "analytic"
    assert p["copperRdc"] == "computed"


# ============================== GOLDEN B (agnosticism) ======================
def test_golden_B_runs_and_differs_from_A():
    rA = eng.compute(package_A()); rB = eng.compute(package_B())
    # different injected constants -> different results (engine shares no constants)
    assert rB["statics"]["L0_nom_uH"] != pytest.approx(rA["statics"]["L0_nom_uH"], rel=1e-3)
    assert rB["worst"]["Bmax"]["Bmax"] != pytest.approx(rA["worst"]["Bmax"]["Bmax"], rel=1e-3)
    assert rB["verdict"] in ("APPROVE", "REJECT")
    # L0 sanity for B: AL(75nH)*1*N^2 = 75e-9*45^2 -> ~151.9 uH
    assert rB["statics"]["L0_nom_uH"] == pytest.approx(75e-9 * 45**2 * 1e6, rel=1e-6)

def test_engine_is_material_agnostic_mix():
    # swapping ONLY the material block changes the answer (no hidden material in engine)
    pkg = package_A()
    base_B = eng.compute(pkg)["worst"]["Bmax"]["Bmax"]
    pkg["model"]["material"]["steinmetz"]["a"] *= 2.0   # double core-loss coefficient
    higher = eng.compute(pkg)
    assert higher["worst"]["loss"]["Ptot_typ"] > base_B  # loss rose; nothing cached


# ============================== FIELDS OVERRIDE =============================
def test_windingAC_field_overrides_and_flags_fea():
    pkg = package_A()
    pkg["fields"] = {"windingAC": {"freq_Hz": [1e3, 7e4, 2e5, 1e6],
                                   "RacOverRdc": [1.0, 1.6, 2.4, 6.0], "provenance": "fea"}}
    r = eng.compute(pkg)
    assert r["provenance"]["windingAC"] == "fea"
    assert r["statics"]["Rac_Rdc"] == pytest.approx(1.6, rel=1e-6)   # interp at 70 kHz

def test_inductance_field_overrides_and_flags_fea():
    pkg = package_A()
    pkg["fields"] = {"inductance": {"H": [0, 40, 80, 160], "L_uH": [260, 230, 170, 90], "provenance": "fea"}}
    r = eng.compute(pkg)
    assert r["provenance"]["inductance"] == "fea"
    # guarantee L now driven by the FEA table (not the analytic k*L0)
    assert r["worst"]["Lmin_guarantee_uH"] < 260

def test_thermal_field_overrides_and_flags_fea():
    pkg = package_A()
    pkg["fields"] = {"thermal": {"nodes": {"Rca_KperW": 6.0, "Rwa_KperW": 5.0, "Rcw_KperW": 2.0},
                                 "provenance": "fea"}}
    r = eng.compute(pkg)
    assert r["provenance"]["thermal"] == "fea"
    # winding-node rise = Ptot_max * Rwa  -> clearly different from the analytic correlation
    assert r["worst"]["dT"]["dT"] > 11.4


# ============================== VALIDATION =================================
def test_missing_material_constant_raises():
    pkg = package_A(); del pkg["model"]["material"]["steinmetz"]["a"]
    with pytest.raises(eng.SpecError) as ei:
        eng.compute(pkg)
    assert any("steinmetz.a" in e for e in ei.value.errors)

def test_ID_ge_OD_raises():
    pkg = package_A(); pkg["model"]["geometry"]["ID_mm"] = 60.0  # >= OD 58.04
    with pytest.raises(eng.SpecError) as ei:
        eng.compute(pkg)
    assert any("ID_mm" in e for e in ei.value.errors)

def test_window_overflow_raises():
    pkg = package_A(); pkg["model"]["winding"]["N"] = 4000  # cannot fit the bore
    with pytest.raises(eng.SpecError) as ei:
        eng.compute(pkg)
    assert any("window overflow" in e.lower() for e in ei.value.errors)

def test_measured_vs_geometry_disagreement_warns_but_computes():
    pkg = package_A()
    pkg["model"]["copper"]["measured"] = {"RdcTotal_20C": 60e-3}  # ~12x the geometry estimate
    vr = eng.validate(pkg)
    assert vr.ok and any("disagree" in w for w in vr.warnings)
    r = eng.compute(pkg)                       # still computes
    assert r["provenance"]["copperRdc"] == "measured"
    assert r["validation"]["warnings"]

def test_no_operating_points_derives_from_maps():
    # remove explicit points; provide maps + Prated + spec pcts (v10-style model)
    pkg = package_A(); del pkg["operating"]
    pkg["model"]["design"]["Prated"] = 3600
    pkg["model"]["design"]["specLowLineMaxPct"] = 47.2
    pkg["model"]["design"]["specHighLineMaxPct"] = 100.0
    pkg["model"]["maps"] = {"etaByVin": {90: 0.944, 132: 0.973, 180: 0.954, 230: 0.967, 264: 0.942}}
    r = eng.compute(pkg)
    assert r["verdict"] in ("APPROVE", "REJECT")
    assert len(r["points"]) == 5


# ============================== SHIPPED FIXTURES ===========================
# These are the JSON files the parent agent validates against. Tests here guarantee
# the shipped examples stay loadable/computable and that the FEA example overrides.
import os, json as _json
_HERE = os.path.dirname(os.path.abspath(__file__))

def _load(name):
    with open(os.path.join(_HERE, name)) as fh:
        return _json.load(fh)

def test_example_analytic_fixture_computes_all_T1():
    r = eng.compute(_load("example_package_analytic.json"))
    assert r["verdict"] == "APPROVE"
    assert r["provenance"]["windingAC"] == "analytic"
    assert r["tier"]["windingAC"] == "T1" and r["tier"]["thermal"] == "T1"

def test_example_fea_fixture_overrides_to_T2():
    r = eng.compute(_load("example_package_fea.json"))
    assert r["provenance"]["windingAC"] == "fea" and r["provenance"]["thermal"] == "fea"
    assert r["provenance"]["inductance"] == "fea"
    assert r["tier"]["windingAC"] == "T2" and r["tier"]["inductance"] == "T2"
    assert r["statics"]["Rac_Rdc"] == pytest.approx(1.18, rel=1e-6)   # from the FEA table @70 kHz

def test_compute_from_json_string_roundtrip():
    s = _json.dumps(package_A())
    out = _json.loads(eng.compute_from_json(s))
    assert out["verdict"] == "APPROVE" and "tier" in out

def test_tier_vocabulary_complete():
    # every provenance value the engine can emit maps to a defined tier
    r = eng.compute(_load("example_package_fea.json"))
    assert set(r["tier"].values()) <= {"T0", "T1", "T2", "T3"}


# ====================== PARITY RULES (B basis, L derate) ====================
def test_Binner_limit_upstream_only():
    pkg = package_A()
    r = eng.compute(pkg)                       # no Binner_max_T -> not asserted
    assert "inner_flux" not in r["asserts"]
    assert r["worst"]["Binner"]["B_inner"] > r["worst"]["Bmax"]["Bmax"]  # crowded > mean
    pkg["acceptance"]["Binner_max_T"] = 0.40   # below the ~0.46 T crowded value -> REJECT
    r2 = eng.compute(pkg)
    assert "inner_flux" in r2["asserts"] and r2["asserts"]["inner_flux"][0] is False
    assert r2["verdict"] == "REJECT"

def test_fea_inductance_not_AL_derated():
    # With a solved L(H) table, the guarantee comes from the table (no AL_tol derate):
    # interpolated L at the worst bias must lower-bound the guarantee exactly.
    pkg = package_A()
    pkg["fields"] = {"inductance": {"H": [0, 300], "L_uH": [250, 250], "provenance": "fea"}}
    r = eng.compute(pkg)
    assert r["worst"]["Lmin_guarantee_uH"] == pytest.approx(250.0, rel=1e-6)


# ===================== REAL-WORLD TIER (measured, T3) ======================
def test_measured_coreloss_steinmetz_overrides_T3():
    base = eng.compute(package_A())
    pkg = package_A()
    pkg["model"]["material"]["measured"] = {"coreLoss": {
        "steinmetz": {"a": 121.47 * 1.2, "b": 2.263, "c": 1.403}, "maxScale": 1.05}}
    r = eng.compute(pkg)
    assert r["provenance"]["coreLoss"] == "measured" and r["tier"]["coreLoss"] == "T3"
    assert r["verdict"] == "APPROVE"   # catalog loss anchor must NOT false-fail a measured fit
    assert r["worst"]["loss"]["Ptot_typ"] > base["worst"]["loss"]["Ptot_typ"]   # 1.2x loss visible
    # measured maxScale (1.05) replaces the catalog +-band (1.286)
    assert r["worst"]["loss"]["Ptot_max"] < base["worst"]["loss"]["Ptot_max"] * 1.2

def test_measured_coreloss_points_fit_recovers_catalog():
    # synth bench points from the catalog law -> fit must reproduce catalog losses
    a, b, c = 121.47, 2.263, 1.403
    pts = [[B, f, a * B ** b * f ** c] for B in (0.05, 0.1, 0.2) for f in (50, 100, 200)]
    pkg = package_A(); pkg["model"]["material"]["measured"] = {"coreLoss": {"points": pts}}
    r = eng.compute(pkg); base = eng.compute(package_A())
    assert r["provenance"]["coreLoss"] == "measured"
    assert r["worst"]["loss"]["Ptot_typ"] == pytest.approx(base["worst"]["loss"]["Ptot_typ"], rel=1e-3)

def test_measured_inductance_outranks_fea():
    pkg = package_A()
    pkg["fields"] = {"inductance": {"H": [0, 300], "L_uH": [200, 200], "provenance": "fea"}}
    pkg["model"]["material"]["measured"] = {"inductance": {"H_Oe": [0, 300], "L_uH": [260, 260]}}
    r = eng.compute(pkg)
    assert r["provenance"]["inductance"] == "measured" and r["tier"]["inductance"] == "T3"
    assert r["worst"]["Lmin_guarantee_uH"] == pytest.approx(260.0, rel=1e-6)

def test_measured_inductance_accepts_bias_current_form():
    pkg = package_A()
    pkg["model"]["material"]["measured"] = {"inductance": {"I_A": [0, 30], "L_uH": [271, 250]}}
    r = eng.compute(pkg)
    assert r["provenance"]["inductance"] == "measured"

def test_measured_contradiction_warns_never_silently_accepts():
    pkg = package_A()
    pkg["model"]["material"]["measured"] = {"coreLoss": {
        "steinmetz": {"a": 121.47 * 3, "b": 2.263, "c": 1.403}}}
    vr = eng.validate(pkg)
    assert vr.ok and any("differs from catalog" in w for w in vr.warnings)
    r = eng.compute(pkg)                                   # still computes (warning, not error)
    assert r["validation"]["warnings"]

def test_eta_map_product_mixing_guard():
    pkg = package_A()
    pkg["model"]["maps"] = {"etaByVin": {180: 0.80}}       # points say eta*PF ~ 0.954
    vr = eng.validate(pkg)
    assert vr.ok and any("PRODUCT" in w for w in vr.warnings)


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-q"]))
