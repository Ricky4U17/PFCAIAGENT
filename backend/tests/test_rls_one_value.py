"""R_LS IS ONE VALUE, WHEREVER IT IS SHOWN.

C279. R_LS was derived in THREE places: the Python engine, the React Screen-2 component, and
`control_design.html`, which is a separate JS engine reached through an iframe (the C243 finding).
Three derivations of one quantity is the "same quantity computed in two places will diverge" trap
this repo keeps recording — and it had already produced the symptom the designer reported: a report
page showing R_LS = 35.846 kΩ calculated beside 47 kΩ selected, with nothing reconciling them.

WHAT IS ASSERTED HERE. The engine is the single source: the Screen-2 payload and the report both
read its fields rather than recomputing, and the JS tool is fed the same basis instead of deriving
one from the loop's inductance. The React screen legitimately RESCALES for a live R_CS choice
(R_LS ∝ 1/R_CS), and that rescale is checked to be exactly the engine's own relationship — a
rescale that drifts is the same defect wearing a different hat.

THE SECOND THING IT ASSERTS is that R_LS and the current loop use DIFFERENT inductances on purpose.
That is the whole design decision (C279): the loop is compensated at the MINIMUM as-built L because
lowest L is the highest plant gain, and Section 6.10.14's verification depends on it; the LS pin
emulates the inductor, so it takes a CENTRAL value. If someone "fixes" the inconsistency by making
them equal, this file says which one is which and why.
"""
from __future__ import annotations

import math

import pytest

from app.mode_b.step16_steps1_8 import compute_steps_1_8

# The reference design's nine-point as-built curve, both bases.
CURVE = [(90, 264.1, 109.0), (110, 315.8, 149.0), (120, 338.1, 170.1), (132, 360.7, 194.5),
         (180, 252.4, 101.2), (200, 280.0, 120.1), (220, 302.0, 137.5), (230, 312.9, 146.4),
         (264, 339.4, 171.4)]


def _inp(**over):
    d = {"l_curve_full": [{"Vin_rms": v, "L_avg_uH": a, "L_crest_uH": c} for v, a, c in CURVE],
         "l_curve": [[v, a] for v, a, _c in CURVE],
         "lphi_uH": min(a for _v, a, _c in CURVE)}
    d.update(over)
    return d


@pytest.fixture(scope="module")
def res():
    return compute_steps_1_8(_inp())


# ── the basis ────────────────────────────────────────────────────────────────

def test_the_emulator_and_the_loop_use_different_inductances_on_purpose(res):
    """The design decision itself. Making these equal is the change this test exists to catch."""
    s8 = res["step8"]
    l_loop = res["inputs"]["lphi_uH"]
    assert l_loop == min(a for _v, a, _c in CURVE), "the loop must stay on the MINIMUM as-built L"
    assert s8["l_ls_uH"] > l_loop, (
        "R_LS is sized at the minimum inductance again. That is the loop's basis (Section 6.10.14 "
        "depends on it); an emulator wants a central value — see C279.")
    vals = [a for _v, a, _c in CURVE]
    assert s8["l_ls_uH"] == pytest.approx(sum(vals) / len(vals), rel=1e-12)


def test_the_basis_is_named_in_words(res):
    """The number is useless on the page without the rule that produced it — that is how a 35.8 kΩ
    calculation and a 47 kΩ selection came to sit side by side unexplained."""
    basis = res["step8"]["l_ls_basis"]
    assert basis and "mean" in basis.lower()


def test_the_basis_is_the_mean_and_not_the_midrange(res):
    """C281, AND THIS IS WHY THE REPORT PRINTS THE SUMMATION.

    The C279 basis line named a statistic and printed the range beside it — "median of 9 per-point
    full-load inductances (101.6–139.3 µH)" — and the designer read it as the MIDRANGE,
    (101.6+139.3)/2 = 120.45. That is a different number reached from the same words, and neither
    party was careless: a named statistic next to a printed range genuinely reads both ways.

    The two differ whenever the points are not symmetric about the range, which is always here: the
    low-line and high-line full-load points sit at the bottom and the rest cluster above them.
    """
    s8 = res["step8"]
    vals = [a for _v, a, _c in CURVE]
    midrange = (min(vals) + max(vals)) / 2.0
    assert s8["l_ls_uH"] != pytest.approx(midrange, rel=1e-6), (
        "the basis has become the midrange — it is meant to be the arithmetic mean, and the two "
        "are only equal on a symmetric set")
    assert s8["l_ls_uH"] == pytest.approx(sum(vals) / len(vals), rel=1e-12)


def test_without_an_as_built_curve_it_falls_back_and_says_so():
    """A legacy design has only the scalar. It must not be presented as a median of nothing."""
    s8 = compute_steps_1_8({"lphi_uH": 235.0})["step8"]
    assert s8["l_ls_uH"] == 235.0
    assert "no per-point" in s8["l_ls_basis"]


# ── one value, three renderers ───────────────────────────────────────────────

def test_equation_39_is_the_engine_s_own_relationship(res):
    """R_LS = L / (1.5n · R_CS · ratio), on the basis the engine chose."""
    s8, s6 = res["step8"], res["step6"]
    expect = s8["l_ls_uH"] * 1e-6 / (1.5e-9 * s6["rcs_sel"] * s8["ratio"])
    assert s8["r_ls"] == pytest.approx(expect, rel=1e-9)


def test_the_effective_inductance_is_equation_39_inverted(res):
    """What the SELECTED resistor emulates. This is the number that makes a clamp or a designer
    override self-explaining instead of an unexplained second figure on the page."""
    s8, s6 = res["step8"], res["step6"]
    back = s8["r_ls_sel"] * 1.5e-9 * s6["rcs_sel"] * s8["ratio"] * 1e6
    assert s8["l_ls_eff_uH"] == pytest.approx(back, rel=1e-9)


def test_the_screen2_payload_reports_the_engine_s_numbers(res):
    """Screen 2 must not recompute. Every R_LS field it serves comes from the engine."""
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    # The route the Screen-2 component actually calls. An earlier draft guessed the path, got a
    # 404 and SKIPPED - a parity test that silently covers nothing, which is the failure this
    # repo keeps recording. It asserts now, so a renamed route fails here instead of going quiet.
    r = client.post("/mode-b/control/components", json={"inputs": _inp()})
    assert r.status_code == 200, r.text
    d = r.json()["r_ls"]
    s8 = res["step8"]
    assert d["calc_kohm"] == pytest.approx(s8["r_ls"] / 1e3, abs=0.05)
    assert d["l_ls_uH"] == pytest.approx(s8["l_ls_uH"], abs=0.05)
    assert d["l_ls_eff_uH"] == pytest.approx(s8["l_ls_eff_uH"], abs=0.05)
    assert d["l_ls_basis"] == s8["l_ls_basis"]
    assert d["clamped"] == bool(s8["r_ls_clamped"])


def test_the_screens_rescale_for_R_CS_is_the_engine_s_own_law(res):
    """The React screen shows `calc_kohm × (rcs_recommended / rcs_selected)` so the figure tracks a
    live R_CS choice. R_LS ∝ 1/R_CS exactly, so that rescale must reproduce the engine run at the
    other shunt — a rescale that drifts is the three-derivations defect wearing a different hat."""
    s6, s8 = res["step6"], res["step8"]
    rcs_a = s6["rcs_sel"]
    rcs_b = rcs_a * 1.25
    other = compute_steps_1_8(_inp(rcs=rcs_b))
    screen = s8["r_ls"] * (rcs_a / rcs_b)
    assert other["step8"]["r_ls"] == pytest.approx(screen, rel=1e-9), (
        "the screen's R_CS rescale no longer matches the engine")


# ── the band ─────────────────────────────────────────────────────────────────

def test_the_selection_is_held_inside_the_datasheet_band(res):
    """AN4165-D and FAN9672-D both bound R_LS to 12-87 kΩ. Outside it the pin sets no usable
    slope, so the limit governs the SELECTION even when the physics asks for more."""
    s8 = res["step8"]
    lo, hi = 12e3, 87e3
    assert lo <= s8["r_ls_sel"] <= hi
    if not (lo <= s8["r_ls"] <= hi):
        assert s8["r_ls_clamped"] is True
        assert s8["r_ls_sel"] in (lo, hi)


def test_every_operating_point_is_tabulated_with_its_own_R_LS(res):
    """The evidence Section 6.8.2 prints. Built in the engine so the report cannot disagree."""
    pts = res["step8"]["ls_points"]
    assert len(pts) == len(CURVE)
    s6, s8 = res["step6"], res["step8"]
    for row, (v, a, c) in zip(pts, CURVE):
        assert row["Vin_rms"] == v
        assert row["L_avg_uH"] == a and row["L_crest_uH"] == c
        assert row["r_ls_ohm"] == pytest.approx(
            a * 1e-6 / (1.5e-9 * s6["rcs_sel"] * s8["ratio"]), rel=1e-9)
        assert row["in_band"] == (12e3 <= row["r_ls_ohm"] <= 87e3)
    # C281: the basis is a MEAN, so it equals no point in general. The flag marks the nearest one
    # — which is what the table's arrow claims and what a bench engineer can act on.
    flagged = [r for r in pts if r["is_basis"]]
    assert len(flagged) == 1, "exactly one point should be flagged as nearest the design basis"
    near = min(pts, key=lambda r: abs(r["L_avg_uH"] - res["step8"]["l_ls_uH"]))
    assert flagged[0]["Vin_rms"] == near["Vin_rms"], "the flag is not on the nearest point"


def test_the_crest_column_is_below_the_cycle_average_everywhere(res):
    """A sanity check on the two bases, and on which is which. Deeper bias means less inductance,
    so if this ever inverts the two columns have been swapped — which would put the SMALLER number
    in the column the equation reads."""
    for r in res["step8"]["ls_points"]:
        assert r["L_crest_uH"] < r["L_avg_uH"], f"crest L is not below cycle-average at {r['Vin_rms']} V"


# ── C_LS follows its resistor ────────────────────────────────────────────────

def test_C_LS_follows_R_LS(res):
    """The designer asked for this explicitly: move R_LS and C_LS moves with it. The capacitor is
    derived from its own resistor and the LS pin-filter pole, so the pole is what stays fixed."""
    s8 = res["step8"]
    f_pole = res["inputs"]["f_pole_ls"]
    assert s8["f_ls"] == pytest.approx(1.0 / (2 * math.pi * s8["r_ls_sel"] * s8["c_ls"]), rel=1e-9)
    # ... and it really does move: halving the emulated inductance halves R_LS and doubles C_LS.
    half = compute_steps_1_8(_inp(l_curve_full=[
        {"Vin_rms": v, "L_avg_uH": a / 2.0, "L_crest_uH": c / 2.0} for v, a, c in CURVE]))["step8"]
    assert half["r_ls"] == pytest.approx(s8["r_ls"] / 2.0, rel=1e-9)
    if not (half["r_ls_clamped"] or s8["r_ls_clamped"]):
        assert half["c_ls"] > s8["c_ls"], "C_LS did not follow R_LS down"
        assert half["f_ls"] == pytest.approx(f_pole, rel=0.35), "the LS pole should stay put"
