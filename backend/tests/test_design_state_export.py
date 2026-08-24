"""The design state export — Phase 0 of the PFC Design Explorer.

The export exists so the animation page, and later the Ansys and SIMetrix/SIMPLIS exporters, all
read ONE projection of the approved design instead of each growing their own aggregation. Its whole
value is that it cannot disagree with the report, so most of this file is about that.

The defect this phase is built to prevent already happened once: the standalone Chapter 7 ran on a
flat inductance while the combined report ran on the as-built bias curve (C255), because two paths
fed the same builder different inputs. An export is a third path. If it recomputed anything, or
substituted a nominal for a missing input, it would be C255 again with a wider blast radius —
this time behind an animation that is specifically built to persuade a reviewer.
"""
import copy

import pytest

from app.mode_b.design_state import build_design_state, CHAPTER_SOURCES


@pytest.fixture(scope="module")
def std_inputs():
    """A real sized inductor and capacitor for the reference state.

    Deliberately PARTIAL — Ch6-Ch10 are absent — because that is the state the gate has to reject,
    and the tests that need a complete design add the remaining chapters themselves. Built from the
    same helpers `verify_combined_report` uses, so export-vs-report comparisons start from
    identical inputs.
    """
    import matplotlib
    matplotlib.use("Agg")
    import copy as _copy
    import logging
    from fastapi.testclient import TestClient
    import app.main as main
    import verify_combined_report as VCR
    from app.mode_b.step15_capacitor import run_capacitor_design

    logging.disable(logging.WARNING)
    try:
        client = TestClient(main.app)
        state = VCR._std_state()
        r = client.post("/mode-b/step7/run-sizing", json={
            "state": state, "material_key": "edge_60", "wire_type": "magnet",
            "wire_designation": None, "max_stacks": 3, "n_top": 5})
        assert r.status_code == 200, r.text
        approved = _copy.deepcopy(r.json()["top_5"][0]["result"])
        cap = run_capacitor_design(state)
        cap["selected_cap"] = VCR.pick_selected_cap(cap)
    finally:
        logging.disable(logging.NOTSET)
    return {"state": state, "approved_design": approved, "step15_result": cap}


# ── rule 1: it is a projection, not a computation ───────────────────────────────────────────
def test_the_module_does_not_import_any_engine_or_report_builder():
    """Structural guard on rule 1. If this module ever imports a builder or an engine, the next
    person will reasonably call it to 'just derive' one missing value, and the export stops being
    a projection. Keeping the import surface empty makes that a visible decision, not a drift."""
    import pathlib
    import re
    src = (pathlib.Path(__file__).resolve().parents[1]
           / "app" / "mode_b" / "design_state.py").read_text(encoding="utf-8")
    imports = re.findall(r"^\s*(?:from|import)\s+([\w.]+)", src, re.M)
    forbidden = [m for m in imports
                 if any(t in m for t in ("report_", "doc_report_builder", "generate_",
                                         "pfc_loss_model", "step7_magnetic_calc", "step15_",
                                         "step16_", "appendices", "schematics"))]
    assert not forbidden, (
        f"design_state imports engine/report modules: {forbidden}. It must project approved "
        "objects, never compute — see the three rules in its docstring.")


def test_it_never_mutates_its_inputs(std_inputs):
    """C-2 and C-11: the page is additive and one-way. If the export mutated an approved object,
    the GUI holding that same object would silently change underneath the pages behind it."""
    before = copy.deepcopy(std_inputs)
    build_design_state(**std_inputs)
    assert std_inputs == before, "build_design_state mutated one of its inputs"


# ── rule 2: no silent defaults ──────────────────────────────────────────────────────────────
def test_a_missing_chapter_is_absent_and_reported_not_defaulted(std_inputs):
    """An unapproved chapter must yield `None` plus `approved: false` — never a plausible nominal.

    A nominal standing in for a measurement is exactly how Table 7.1 printed a flat inductance
    under a caption claiming the Chapter-3 bias basis (C255).
    """
    only_state = build_design_state(state=std_inputs["state"])
    for name in ("magnetics", "capacitor", "control", "semiconductors", "protection", "emi"):
        assert only_state["chapters"][name] is None, f"{name} invented content from nothing"
        assert only_state["readiness"]["chapters"][name]["approved"] is False
    assert only_state["points"] == [], "points[] fabricated rows with no inductor design"


def test_an_empty_dict_is_not_an_approval(std_inputs):
    """`{}` is what the GUI sends for a chapter the designer has not reached. It must not read as
    approved — the difference between 'designed, and empty' and 'not designed' is the whole gate."""
    d = build_design_state(state=std_inputs["state"], step15_result={})
    assert d["readiness"]["chapters"]["capacitor"]["approved"] is False
    assert d["chapters"]["capacitor"] is None


# ── the C-12 gate ───────────────────────────────────────────────────────────────────────────
def test_the_gate_opens_only_when_every_chapter_is_approved(std_inputs):
    """C-12, settled with the designer: the animation page is unreachable until Ch1-Ch10 are all
    complete, Ch8-Ch10 included."""
    partial = build_design_state(**std_inputs)
    assert partial["readiness"]["gate"] == "blocked"
    assert partial["readiness"]["complete"] is False
    assert set(partial["readiness"]["missing"]) <= set(CHAPTER_SOURCES)

    full = dict(std_inputs)
    full.update({"step16_params": {"L_uH": 235.0}, "semiconductor": {"design": {}},
                 "input_protection": {"design": {}}, "input_filter": {"design": {}}})
    opened = build_design_state(**full)
    assert opened["readiness"]["missing"] == [], opened["readiness"]["missing"]
    assert opened["readiness"]["gate"] == "open" and opened["readiness"]["complete"] is True


def test_every_chapter_names_the_request_field_it_came_from(std_inputs):
    """Provenance: a consumer must be able to say WHERE a section came from without guessing."""
    d = build_design_state(**std_inputs)
    for name, field in CHAPTER_SOURCES.items():
        assert d["readiness"]["chapters"][name]["source"] == field


# ── the anti-C255 property ──────────────────────────────────────────────────────────────────
def test_points_carry_the_per_point_bias_inductance_not_a_flat_nominal(std_inputs):
    """THE REASON points[] EXISTS.

    Any consumer reading points[] must get the as-built inductance per operating point, so it
    cannot accidentally animate a flat L the way the standalone Chapter 7 printed one. Measured on
    the reference design: L runs roughly 130-155 uH across the sweep, against a 235 uH target.
    """
    d = build_design_state(**std_inputs)
    ls = [p["L_full_nom_uH"] for p in d["points"]]
    assert len(ls) >= 9, f"expected the full sweep, got {len(ls)} points"
    assert all(v is not None for v in ls), "a point is missing its inductance"
    assert max(ls) - min(ls) > 1.0, (
        f"L is effectively constant across the sweep ({min(ls)}-{max(ls)} uH) — the export is "
        "carrying a flat nominal, which is the C255 defect")
    # and the ripple must move with it, or the consumer will draw a constant envelope
    dis = [p["dIL_pp_A"] for p in d["points"]]
    assert max(dis) - min(dis) > 0.1, f"dIL_pp is flat across the sweep: {dis}"


def test_points_are_sorted_and_keyed_consistently(std_inputs):
    d = build_design_state(**std_inputs)
    vacs = [p["vac_V"] for p in d["points"]]
    assert vacs == sorted(vacs), f"points[] is not in line-voltage order: {vacs}"
    assert len(set(vacs)) == len(vacs), f"duplicate operating points: {vacs}"


def test_the_single_ambient_reaches_the_export(std_inputs):
    """`intake.thermal.ambient_temp_c_max` is the one ambient every chapter uses (C247). If the
    export dropped it, every thermal number the animation shows would be unattributable."""
    d = build_design_state(**std_inputs)
    spec_amb = std_inputs["state"]["intake"]["thermal"]["ambient_temp_c_max"]
    assert d["spec"]["ambient_temp_c_max"] == float(spec_amb)


def test_both_saturation_bases_are_carried(std_inputs):
    """PENDING D3 is undecided: the report quotes inner-bore margin while the engine's gate runs on
    mean-path. Carrying only one would have the export silently pick a side."""
    flux = build_design_state(**std_inputs)["chapters"]["magnetics"]["flux"]
    assert flux["Bmax_FL_T"] is not None and flux["Bmax_inner_FL_T"] is not None
    assert flux["Bsat_at_Tcore_T"] is not None


# ── agreement with the document ─────────────────────────────────────────────────────────────
def test_the_export_agrees_with_the_rendered_report_on_the_inductance_curve(std_inputs):
    """THE POINT OF THE WHOLE PHASE: export and report must not be able to disagree.

    Renders Chapter 7 and compares Table 7.1's L column, cell for cell, against points[]. This is
    the check that did not exist while the standalone chapter and the combined report disagreed.

    WHY THE STANDALONE CHAPTER AND NOT THE FULL REPORT. Table 7.1 is the same table in both, and
    since C255 they are identical for the same design (asserted by
    `test_ch7_standalone_matches_combined.py`). Rendering one chapter costs ~20 s against ~3.5 min
    for the whole document, and a guard this central must run on every suite rather than be
    deselected behind a marker — a skipped guard protects nothing.
    """
    import re
    import matplotlib
    matplotlib.use("Agg")
    import fitz
    from fastapi.testclient import TestClient
    import app.main as main

    client = TestClient(main.app)
    from app.mode_b.semiconductor import adapter as AD
    design = dict(AD.REFERENCE_DESIGN)
    design.update({"eta": 0.95, "pf": 0.99, "V_GS_drive": 18.0, "R_g_on": 4.7, "R_g_off": 10.0,
                   "R_th_cs": 0.3, "nch": 2, "vout": 393.0, "fsw": 70000.0})
    thermal = dict(AD.REFERENCE_PARTS["thermal"])
    thermal["t_ambient"] = float(std_inputs["state"]["intake"]["thermal"]["ambient_temp_c_max"])

    r = client.post("/mode-b/semiconductor/report", json={
        "design": design, "mosfet": AD.REFERENCE_PARTS["mosfet"],
        "diode": AD.REFERENCE_PARTS["diode"], "bridge": AD.REFERENCE_PARTS["bridge"],
        "thermal": thermal, "tj_limit": {"fet": 150, "diode": 150, "bridge": 130},
        # the same approved inductor the export projects — without this the chapter runs on a flat
        # nominal and the comparison would be meaningless (C255)
        "approved_design": std_inputs["approved_design"]})
    assert r.status_code == 200, r.text
    with fitz.open(stream=r.content, filetype="pdf") as doc:
        txt = "".join(p.get_text() for p in doc)

    seg = txt[txt.find("Table 7.1"):]
    cut = seg.find("\nTable 7", 10)
    seg = seg[:cut] if cut > 0 else seg[:4000]
    printed = [int(x) for x in re.findall(r"(\d+)\s*µH", seg)[:9]]
    assert len(printed) == 9, f"could not read Table 7.1's L column, got {printed}"

    exported = [round(p["L_full_nom_uH"]) for p in build_design_state(**std_inputs)["points"]]
    assert printed == exported, (
        f"rendered Table 7.1 L = {printed} but the export says {exported} — the animation would "
        "show a different inductance from the document it sits beside")
