"""CHAPTER 6: THE GUI, THE ENGINE AND THE REPORT MUST AGREE, AND NOTHING MAY BE RETYPED.

C238. Asked to give Chapter 6 the treatment Chapter 7 got (C236), after C235 found the schematic
drawing its own component values.

The structural position is good: `/mode-b/control/components` and `/mode-b/control/coefficients`
both call `compute_steps_1_8`, which is the same engine `report_steps1_8` renders from. So GUI ==
engine holds by construction. What does NOT hold by construction is prose and worked equations,
where a value can be RETYPED as a literal - and that is where every Chapter-6 defect was:

    6.4.1  R_RI worked line    hardcoded 70,000 and the 17.143 k intermediate while printing a LIVE
                               answer. The prose immediately above says R_RI is "computed from the
                               target f_SW - not hardcoded".
    6.6.2  denominator         hardcoded K_RLPK 2.465, R_RLPK 12,100 and R_RLPK^2 as 1.4641e8
    6.8.3  soft start          hardcoded I_SS/t_SS/V_SS in the equation, and the SELECTED C_SS as
                               "390 nF" - which lived in a LOCAL variable the report could not read
    6.8.4  C_ILIMIT            asserted 18 nF in prose; the GUI dropdown offered 10 nF; the
                               schematic drew 18 nF. A genuine three-way disagreement.

WHY EQUATIONS NEED THIS SHAPE OF TEST. `eq_box` renders through matplotlib into an IMAGE, so the
equation text never reaches the PDF text layer - no assertion on the built document can read it.
(That is also why C235's wrong resistors survived to a designer's eye.) These tests capture the
STRINGS handed to `eq_box`/`body` during a build instead, which is what actually gets drawn.

A LITERAL THAT IS CORRECT TODAY LOOKS IDENTICAL TO A LIVE VALUE. The only way to tell them apart
is to change the input and see whether the output moves - so the frequency-dependent checks build
TWICE, at 70 kHz and 60 kHz.
"""
import pytest


def _capture(fsw):
    """Strings passed to eq_box / body while Chapter 6 builds at this switching frequency."""
    import matplotlib
    matplotlib.use("Agg")
    import app.mode_b.report_steps1_8 as R

    seen = []
    orig_eq, orig_body = R.eq_box, R.body
    R.eq_box = lambda story, eqs, **kw: seen.append(("eq", list(eqs)))
    R.body = lambda story, txt, *a, **k: seen.append(("body", txt))
    try:
        R.build_control_report({"fsw": fsw})
    except Exception:
        pass          # the PDF build may bail after the story; the captured strings are the point
    finally:
        R.eq_box, R.body = orig_eq, orig_body
    return [s for kind, v in seen for s in (v if kind == "eq" else [v]) if isinstance(s, str)]


@pytest.fixture(scope="module")
def at70():
    return _capture(70000)


@pytest.fixture(scope="module")
def at60():
    return _capture(60000)


def _one(strings, must_contain):
    hits = [s for s in strings if all(m in s for m in must_contain)]
    assert hits, f"no rendered string containing {must_contain}"
    return hits[0]


def test_the_r_ri_worked_equation_tracks_the_switching_frequency(at70, at60):
    """6.4.1. The line under a caption that says "not hardcoded" was hardcoded."""
    e70 = _one(at70, ("3430", "calculated"))
    e60 = _one(at60, ("3430", "calculated"))
    assert r"70\,000" in e70, f"70 kHz build does not show its own frequency: {e70}"
    assert r"60\,000" in e60, f"60 kHz build still shows a stale frequency: {e60}"
    # the intermediate 1.2e9/f_sw must move too - it was frozen at 17.143 k
    assert "17.143" in e70 and "20.000" in e60, (
        f"the 1.2e9/f_sw intermediate is not tracking:\n  70k: {e70}\n  60k: {e60}")


def test_the_gain_modulator_denominator_uses_the_engine_constants(at70):
    """6.6.2. K_RLPK and R_RLPK were retyped here - R_RLPK's FOURTH source of truth after C235."""
    from app.mode_b.step16_steps1_8 import CONST
    eq = _one(at70, ("times", "^2"))
    eqs = [s for s in at70 if "^2" in s and "times" in s and "8" in s]
    assert eqs, "the common-denominator worked line did not render"
    joined = " ".join(eqs)
    assert f"{CONST['k_rlpk']:g}" in joined, f"K_RLPK not taken from the engine: {joined[:160]}"
    assert f"{CONST['r_rlpk']:,.0f}".replace(",", "\\,") in joined, \
        f"R_RLPK not taken from the engine: {joined[:160]}"


def test_soft_start_reports_the_selected_capacitor_from_the_engine(at70):
    """6.8.3. `css_sel` was a LOCAL in the engine; "390 nF" was retyped in two other places."""
    from app.mode_b.step16_steps1_8 import compute_steps_1_8
    s8 = compute_steps_1_8({})["step8"]
    assert "css_sel" in s8, "the engine must EXPORT the selected C_SS, not keep it in a local"
    line = _one(at70, ("C<sub>SS</sub> =", "realized"))
    assert f"{s8['css_sel'] * 1e9:.0f} nF" in line, f"selected C_SS not from the engine: {line}"
    assert f"{s8['c_ss'] * 1e9:.0f} nF" in line, (
        f"the CALCULATED value should be shown beside the selected one: {line}")


def test_every_pin_filter_cap_is_one_value_across_gui_schematic_and_engine():
    """C239. C238 unified C_ILIMIT alone and the designer then found C_VIR and C_RLPK still
    disagreeing - the GUI offered a uniform 10 nF placeholder for four of the five while the
    drawing carried its own literals. Checked as a FAMILY so fixing one cannot leave siblings.

    C_VIR is the reason this is worth a test: it was a hardcoded STRING in the drawing ("0.1 uF
    (typ)"), so it never passed through `g()` and the C235 default-check could not see it at all.
    """
    from fastapi.testclient import TestClient
    from app.mode_b.step16_steps1_8 import compute_steps_1_8
    from app.mode_b.schematics import fan9672_application_schematic
    import app.main as main

    d = compute_steps_1_8({})
    c, s8 = d["const"], d["step8"]
    gui = {r["symbol"]: r for r in TestClient(main.app).post(
        "/mode-b/control/components", json={"inputs": {}}).json().get("selectable", [])}
    assert gui, "the GUI component endpoint offered no selectable caps"

    ctx = {"crest_A": 0.0, "iphi_pk_A": 0.0}
    for skey, ekey in (("c_gc", "c_gc"), ("crlpk", "c_rlpk"), ("cil", "c_ilimit"),
                       ("cil2", "c_ilimit2"), ("cvir", "c_vir"), ("c_ls", "c_ls"),
                       ("clpk", "c_lpk"), ("css", "css_sel")):
        ctx[skey] = s8[ekey]
    resolved = {}
    fan9672_application_schematic(ctx, is_high=False, _resolved=resolved)

    for sym, ekey, skey in (("C_GC", "c_gc", "c_gc"), ("C_RLPK", "c_rlpk", "crlpk"),
                            ("C_ILIMIT", "c_ilimit", "cil"), ("C_ILIMIT2", "c_ilimit2", "cil2"),
                            ("C_VIR", "c_vir", "cvir"), ("C_LS", "c_ls", "c_ls")):
        eng = s8[ekey]
        assert sym in gui, f"{sym} not offered by the GUI endpoint"
        assert gui[sym]["default_pf"] == pytest.approx(eng * 1e12, rel=1e-6), (
            f"{sym}: GUI default {gui[sym]['default_pf']} pF, engine {eng*1e12:.0f} pF")
        assert resolved[skey]["value"] == pytest.approx(eng), (
            f"{sym}: schematic draws {resolved[skey]['value']}, engine {eng}")
        assert resolved[skey]["defaulted"] is False, f"{sym} still using a drawing literal"

    # the drawing must show the SELECTED C_SS, matching Section 6.8.3 - it was handed the
    # CALCULATED 400 nF while the report stated 390 nF
    assert resolved["css"]["value"] == pytest.approx(s8["css_sel"]),         f"schematic C_SS {resolved['css']['value']} != selected {s8['css_sel']}"
    assert s8["css_sel"] != s8["c_ss"], "fixture cannot distinguish selected from calculated"


def test_c_ilimit_is_one_value_across_gui_report_and_schematic(at70):
    """6.8.4. The three-way disagreement: GUI 10 nF, report 18 nF, schematic 18 nF."""
    from app.mode_b.step16_steps1_8 import compute_steps_1_8
    s8 = compute_steps_1_8({})["step8"]
    assert "c_ilimit" in s8, "C_ILIMIT must have exactly one home, in the engine"

    line = _one(at70, ("C<sub>ILIMIT</sub>",))
    assert f"{s8['c_ilimit'] * 1e9:.0f} nF" in line, f"report prose not from the engine: {line}"

    # the schematic must draw the same value rather than its own literal
    from app.mode_b.schematics import fan9672_application_schematic
    resolved = {}
    fan9672_application_schematic({"cil": s8["c_ilimit"], "crest_A": 0.0, "iphi_pk_A": 0.0},
                                  is_high=False, _resolved=resolved)
    assert resolved["cil"]["value"] == pytest.approx(s8["c_ilimit"])
    assert resolved["cil"]["defaulted"] is False, "the drawing is still using its own C_ILIMIT"


def test_gui_component_endpoint_agrees_with_the_engine():
    """`/mode-b/control/components` must report the engine's values, not a parallel computation."""
    from fastapi.testclient import TestClient
    from app.mode_b.step16_steps1_8 import compute_steps_1_8
    import app.main as main

    d = compute_steps_1_8({})
    c, s4, s5 = d["const"], d["step4"], d["step5"]
    r = TestClient(main.app).post("/mode-b/control/components", json={"inputs": {}})
    assert r.status_code == 200, r.text
    rows = {row["symbol"]: row["value"] for row in r.json().get("fixed", [])
            if isinstance(row, dict) and row.get("symbol")}
    assert rows, f"endpoint returned no components: {list(r.json())[:6]}"

    def ohm(x):
        return (f"{x/1e6:.2f} MΩ" if x >= 1e6 else
                (f"{x/1e3:.1f} kΩ" if x >= 1e3 else f"{x:.1f} Ω"))

    for sym, want in (("R_RI", s4["rri_selected"]), ("R_FB2", s5["rfb2"]),
                      ("R_RLPK", c["r_rlpk"])):
        assert sym in rows, f"{sym} missing from the GUI component list"
        assert rows[sym] == ohm(want), \
            f"{sym}: GUI shows {rows[sym]}, engine says {ohm(want)}"
