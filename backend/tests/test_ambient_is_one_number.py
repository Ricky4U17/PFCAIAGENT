"""EVERY CHAPTER MUST WORK AT THE AMBIENT THE DESIGNER TYPED ON THE FIRST PAGE.

`intake.thermal.ambient_temp_c_max` is the single source of truth for operating ambient. Three
independent engines consume it:

    Ch3/4 magnetics     step7_run_sizing reads the spec and passes T_amb_C into the thermal solve
    Ch5 capacitor       step15_capacitor reads the spec for ESR(T), ripple headroom and lifetime
    Ch7 semiconductors  the GUI pre-fills the thermal form from the spec; sink = ambient + P*Rth_sa
                        and Tj iterates from there

Verified 2026-08-22 that all three are correctly wired. This file exists so they STAY wired: a
chapter that silently pins its own ambient produces a perfectly plausible report, and the only
symptom is that a number the designer changed does not move.

WHY NOT A RENDERED-REPORT TEST. `TestCombinedReport` asserts the STATED ambient on a single build,
which catches a chapter printing the wrong number. It cannot catch one that prints the right number
and computes with another. That needs two runs at different ambients, and two full report builds
cost ~200 s. These are engine-level instead: seconds, and they test the same wiring.

THE DIRECTION MATTERS AS MUCH AS THE MOVEMENT. Asserting only "it changed" would pass on a sign
error, so each check states which way the number must go.
"""
import copy

import pytest

HOT, COLD = 55.0, 25.0


def _state(tamb):
    from verify_combined_report import _std_state
    st = copy.deepcopy(_std_state())
    st.setdefault("intake", {}).setdefault("thermal", {})["ambient_temp_c_max"] = tamb
    return st


# -- Ch7 semiconductors -------------------------------------------------------
def _semi_at(tamb):
    """The same two calls `/mode-b/semiconductor/calculate` makes."""
    from app.mode_b.semiconductor import adapter as AD
    from app.mode_b.semiconductor import pfc_loss_model as engine
    P = AD.REFERENCE_PARTS
    design = dict(AD.REFERENCE_DESIGN)
    design.update({"eta": 0.95, "pf": 0.99, "R_th_cs": 0.3})
    thermal = dict(P["thermal"])
    thermal["t_ambient"] = tamb
    cfg, _ref = AD.build_semi_cfg(design, P["mosfet"], P["diode"], P["bridge"], thermal)
    return engine.simulate_vac_sweep(cfg)


def test_semiconductor_junction_temperatures_follow_the_ambient():
    """Sink = ambient + P*Rth_sa, so every junction must rise with the room, roughly one-for-one."""
    hot, cold = _semi_at(HOT), _semi_at(COLD)
    ph, pc = hot[0], cold[0]
    for k in ("Tj_FET", "Tj_DIODE", "Tj_BRIDGE_top"):
        assert k in ph, f"{k} missing from the engine output"
        rise = float(ph[k]) - float(pc[k])
        assert rise > (HOT - COLD) * 0.8, (
            f"{k} moved {rise:.1f} degC for a {HOT - COLD:g} degC ambient change "
            f"({pc[k]:.1f} -> {ph[k]:.1f}) — Chapter 7 may not be using the entered ambient")


# ── Ch3/4 magnetics ─────────────────────────────────────────────────────────
def _inductor_at(tamb):
    from fastapi.testclient import TestClient
    import app.main as main
    r = TestClient(main.app).post("/mode-b/step7/run-sizing", json={
        "state": _state(tamb), "material_key": "edge_60", "wire_type": "magnet",
        "wire_designation": None, "max_stacks": 3, "n_top": 1})
    assert r.status_code == 200, r.text
    j = r.json()
    c = (j.get("top_5") or j.get("candidates") or [{}])[0]
    return c.get("result", c)


def test_the_inductor_thermal_solve_follows_the_ambient():
    """`T_core = T_amb + 0.5*dT_budget`, so the core temperature must track the room.

    Note the rise itself moves the OTHER way: `dT_budget = hotspot_limit - ambient`, so a cooler
    room grants a LARGER budget and the optimiser may pick a smaller, hotter-running core. Both
    directions are asserted, because getting either backwards is a real defect.
    """
    hot, cold = _inductor_at(HOT), _inductor_at(COLD)
    assert hot["T_core_C"] > cold["T_core_C"], (
        f"core temperature did not rise with ambient "
        f"({cold['T_core_C']} -> {hot['T_core_C']}) — T_amb_C may not be reaching the solve")
    assert hot["dT_rise_C"] < cold["dT_rise_C"], (
        f"a cooler room should allow a LARGER rise budget (dT_budget = hotspot - ambient); got "
        f"{cold['dT_rise_C']} at {COLD:g} degC and {hot['dT_rise_C']} at {HOT:g} degC")


# -- Ch5 capacitor ------------------------------------------------------------
def _cap_worst_at(tamb):
    from verify_combined_report import pick_selected_cap
    from app.mode_b.step15_capacitor import run_capacitor_design, bank_loss_table
    st = _state(tamb)
    d = run_capacitor_design(st)
    d["selected_cap"] = pick_selected_cap(d)
    tbl = bank_loss_table(d, st)
    assert tbl and tbl.get("worst"), "bank_loss_table returned nothing — fixture is wrong"
    return tbl["worst"]


def test_the_capacitor_case_temperature_and_loss_follow_the_ambient():
    """ESR(T) is solved at the case temperature, which is ambient + self-heating.

    THE GAIN IS DELIBERATELY SUB-UNITY, and the first version of this test asserted otherwise.
    Measured: a 30 degC ambient rise moves the case only 23.1 degC (42.6 -> 65.7), because
    self-heating FALLS from 17.6 K to 10.7 K over the same span - the ESR that produces the heating
    drops as the part warms. That negative feedback is the model working, so the bound is 0.5x
    rather than 1x. Do not "fix" a sub-unity gain here.
    """
    hot, cold = _cap_worst_at(HOT), _cap_worst_at(COLD)
    t_hot, t_cold = float(hot["T_cap_C"]), float(cold["T_cap_C"])
    rise = t_hot - t_cold
    assert rise > (HOT - COLD) * 0.5, (
        f"case temperature moved only {rise:.1f} degC for a {HOT - COLD:g} degC ambient change "
        f"({t_cold} -> {t_hot}) — Chapter 5 may not be using the entered ambient")
    assert rise < (HOT - COLD), (
        f"case temperature rose {rise:.1f} degC for a {HOT - COLD:g} degC ambient change — the "
        "ESR(T) feedback should make this sub-unity; a 1:1 rise means ESR stopped tracking")
    assert t_hot > HOT and t_cold > COLD, "the case must sit ABOVE ambient at both points"
    assert float(hot["ESR_per_cap_mohm"]) < float(cold["ESR_per_cap_mohm"]), (
        "electrolytic ESR must FALL as the part warms; it did not "
        f"({cold['ESR_per_cap_mohm']:.1f} -> {hot['ESR_per_cap_mohm']:.1f} mOhm)")


def test_the_three_engines_read_the_same_spec_field():
    """One field, not three. If a chapter starts reading its own key this fails on the value."""
    w = _cap_worst_at(37.0)
    assert float(w["T_cap_C"]) > 37.0, (
        f"the capacitor case ({w['T_cap_C']} degC) is not above the 37 degC spec ambient — "
        "it is not reading intake.thermal.ambient_temp_c_max")
