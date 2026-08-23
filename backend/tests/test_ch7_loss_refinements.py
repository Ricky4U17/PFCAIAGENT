"""Three Chapter-7 loss-model refinements: PENDING B16, B17, B18 (C253).

All three were logged as known approximations rather than bugs, and all three are small on the
reference design — the point of testing them is that each has an EXACT degenerate case which must
reproduce the old number bit for bit. A refinement that quietly moves a figure it was not supposed
to touch is worse than the approximation it replaced, so every test below pins both ends: the
degenerate case is unchanged, and the non-degenerate case moves in the stated direction.
"""
import numpy as np
import pytest


@pytest.fixture(scope="module")
def sweep():
    from app.mode_b.semiconductor import adapter as AD
    from app.mode_b.semiconductor import pfc_loss_model as E
    P = AD.REFERENCE_PARTS
    design = dict(AD.REFERENCE_DESIGN)
    design.update({"eta": 0.95, "pf": 0.99, "R_th_cs": 0.3})
    thermal = dict(P["thermal"]); thermal["t_ambient"] = 50.0
    cfg, _ = AD.build_semi_cfg(design, P["mosfet"], P["diode"], P["bridge"], thermal)
    return {int(round(r["Vac"])): r for r in E.simulate_vac_sweep(cfg)}, cfg


# ── B16 — the SiC junction charge is taken at the voltage the drain is ACTUALLY at ──────────
def test_the_sic_charge_term_is_unchanged_wherever_there_is_no_dcm(sweep):
    """In CCM the drain is at V_OUT when the FET turns on, so the refinement must be a no-op.

    The scalar it has to reproduce is the whole of the old model:
        P = fsw * V_OUT * Q_c * k_qc / (2 - m)
    """
    rows, cfg = sweep
    from app.mode_b.semiconductor import pfc_loss_model as E
    dio = E.Diode(**cfg["diode"]) if isinstance(cfg["diode"], dict) else cfg["diode"]
    if not dio.is_sic:
        pytest.skip("reference diode is not SiC")
    spec = cfg["spec"] if isinstance(cfg["spec"], dict) else cfg["spec"].__dict__
    fsw, vout = float(spec["fsw"]), float(spec["vo"])
    # P_FET_rr is the SYSTEM total; the engine expression is per channel. Getting this backwards
    # is the standing per-phase-vs-system trap in this codebase, so nch is explicit here.
    nch = int(spec.get("nch", 1) or 1)
    scalar = nch*fsw*vout*dio.qc*dio.k_qc/(2.0 - min(dio.cj_grading, 0.95))

    ccm_only = [v for v, r in rows.items() if float(r["DCM_%"]) == 0.0]
    assert ccm_only, "no fully-CCM operating point in the sweep — fixture problem"
    for v in ccm_only:
        got = float(rows[v]["P_FET_rr"])
        assert abs(got - scalar) < 1e-9, (
            f"{v} Vac is fully CCM but the Q_c term is {got:.6f} W, not the full-V_OUT scalar "
            f"{scalar:.6f} W — the per-angle refinement changed a point it must not touch")


def test_the_sic_charge_term_falls_where_the_converter_enters_dcm(sweep):
    """Past the zero crossings at high line the node has already resonated below V_OUT, so
    charging C_j at full V_OUT overstated the term. It must fall, and by no more than the DCM
    fraction — the DCM portion can contribute nothing, it cannot contribute negatively.
    """
    rows, cfg = sweep
    dcm_pts = [v for v, r in rows.items() if float(r["DCM_%"]) > 0.0]
    if not dcm_pts:
        pytest.skip("reference design never enters DCM")
    ccm = next(v for v, r in rows.items() if float(r["DCM_%"]) == 0.0)
    scalar = float(rows[ccm]["P_FET_rr"])
    for v in dcm_pts:
        got, frac = float(rows[v]["P_FET_rr"]), float(rows[v]["DCM_%"])/100.0
        assert got < scalar, (
            f"{v} Vac is {100*frac:.0f} % DCM but its Q_c term ({got:.4f} W) did not fall below "
            f"the full-V_OUT scalar ({scalar:.4f} W)")
        assert got >= scalar*(1.0 - frac) - 1e-9, (
            f"{v} Vac lost more than its DCM fraction: {got:.4f} W vs a floor of "
            f"{scalar*(1-frac):.4f} W. DCM sits near the zero crossings where v is small, so its "
            "contribution tends to zero — it must not go negative")


# ── B17 — v_F(i)*i integrated across the ripple triangle ────────────────────────────────────
def test_a_single_point_forward_curve_reproduces_the_mid_current_result_exactly():
    """THE PROPERTY THAT MAKES THE CHANGE SAFE. The mean of a linear ramp is its mid-value, so a
    device whose datasheet publishes one forward voltage must give the identical number. Most
    catalogue parts are exactly that, and none of their reports may move.
    """
    from app.mode_b.semiconductor import pfc_loss_model as E
    flat = E.Diode(vf_curve=((1.0, 50.0), (1.4, 1.4)), vf_tco=0.0)
    i_lo = np.array([2.0, 5.0, 0.0]); i_hi = np.array([14.0, 5.0, 20.0])
    ramp = E.vf_i_ramp(flat, i_lo, i_hi, 100.0)
    mid = (i_lo + i_hi)/2.0
    expect = flat.vf(mid, 100.0)*mid
    assert np.allclose(ramp, expect, rtol=0, atol=1e-12), (
        f"flat curve must be a no-op: ramp={ramp}, mid-point={expect}")


def test_the_ripple_integration_is_converged_at_nine_points():
    """9 samples is a choice; this pins that it is enough. If someone lowers _N_RIPPLE to save
    time, the number moves and this says so.
    """
    from app.mode_b.semiconductor import pfc_loss_model as E
    dio = E.Diode(vf_curve=((1.0, 5.0, 16.0), (1.05, 1.35, 1.70)), vf_tco=0.0)
    i_lo = np.array([2.0]); i_hi = np.array([14.0])
    nine = float(E.vf_i_ramp(dio, i_lo, i_hi, 100.0)[0])

    fine_w = np.linspace(0.0, 1.0, 129)
    grid = i_lo[None, :] + (i_hi - i_lo)[None, :]*fine_w[:, None]
    fine = float(np.mean(dio.vf(grid, 100.0)*grid, axis=0)[0])
    assert abs(nine - fine)/fine < 2e-3, (
        f"9-point ramp {nine:.6f} W vs 129-point {fine:.6f} W — not converged")


def test_a_curved_forward_characteristic_actually_moves_the_diode_figure(sweep):
    """The refinement has to be worth something on a real part, or it is complexity for nothing.

    Measured on the reference SiC diode (a genuine 3-point curve, 1.05/1.35/1.70 V at 1/5/16 A):
    conduction rises by 0.02-0.08 W across the sweep. It RISES — v_F(i) is concave, but the
    integrand is v_F(i)*i, whose curvature runs the other way, so the mid-point sample was
    understating. Small, and in the conservative direction.
    """
    rows, cfg = sweep
    dio_cfg = cfg["diode"] if isinstance(cfg["diode"], dict) else cfg["diode"].__dict__
    pts = (dio_cfg.get("vf_curve") or [[]])[0]
    if len(pts) < 3:
        pytest.skip("reference diode has no multi-point forward curve")
    # sanity: the curve is genuinely non-linear, otherwise the test proves nothing
    from app.mode_b.semiconductor import pfc_loss_model as E
    dio = E.Diode(**dio_cfg) if isinstance(cfg["diode"], dict) else cfg["diode"]
    lo, hi = np.array([2.0]), np.array([14.0])
    mid = (lo + hi)/2.0
    ramp = float(E.vf_i_ramp(dio, lo, hi, 100.0)[0])
    point = float((dio.vf(mid, 100.0)*mid)[0])
    assert ramp > point, (
        f"integrating across the ripple gave {ramp:.5f} W, the mid-point sample {point:.5f} W — "
        "expected the integral to be the larger for this curve shape")
    assert abs(ramp - point)/point < 0.05, (
        "a >5 % swing from ripple curvature alone is not credible on this curve — check the ramp "
        "bounds before believing it")


# ── B18 — the bridge finally has a leakage term ─────────────────────────────────────────────
def _bridge_loss(**kw):
    from app.mode_b.semiconductor import pfc_loss_model as E
    i = np.abs(np.sin(np.linspace(0.0, np.pi, 400)))*10.0
    return E.Bridge(**kw).loss(i, kw.pop("_tj", 125.0), 125.0, 60.0, 373.0)["total"]


def test_a_bridge_without_a_leakage_curve_is_completely_unaffected():
    """Every catalogue bridge is in this state — the workbook has no leakage column — so the
    default path must be bit-identical to before the field existed."""
    from app.mode_b.semiconductor import pfc_loss_model as E
    i = np.abs(np.sin(np.linspace(0.0, np.pi, 400)))*10.0
    plain = E.Bridge().loss(i, 125.0, 125.0, 60.0, 373.0)["total"]
    explicit_none = E.Bridge(irev_curve=None).loss(i, 125.0, 125.0, 60.0, 373.0)["total"]
    assert plain == explicit_none


def test_bridge_leakage_matches_two_legs_at_the_mean_line_voltage():
    """Two of the four legs block at any instant, and they stand off the LINE voltage, not the
    bus — mean |v_line| = 2*Vpk/pi. The entry's own estimate used the 400 V bus and four diodes,
    which is roughly 4x too high; at 373 Vpk and 10 uA the real figure is 4.75 mW.
    """
    from app.mode_b.semiconductor import pfc_loss_model as E
    i = np.abs(np.sin(np.linspace(0.0, np.pi, 400)))*10.0
    Vpk, irev = 373.0, 10e-6
    base = E.Bridge().loss(i, 125.0, 125.0, 60.0, Vpk)["total"]
    leaky = E.Bridge(irev_curve=((25.0, 125.0), (1e-6, irev))).loss(i, 125.0, 125.0, 60.0, Vpk)["total"]
    expect = 2.0*(2.0*Vpk/np.pi)*irev
    assert abs((leaky - base) - expect) < 1e-9, (
        f"leakage came out {1000*(leaky-base):.4f} mW, expected {1000*expect:.4f} mW")


def test_bridge_leakage_rises_with_junction_temperature():
    """It is a curve, not a constant — leakage roughly decades with temperature, and a model that
    ignored that would make the term pointless at the only temperature where it matters."""
    from app.mode_b.semiconductor import pfc_loss_model as E
    i = np.abs(np.sin(np.linspace(0.0, np.pi, 400)))*10.0
    br = E.Bridge(irev_curve=((25.0, 125.0), (1e-6, 10e-6)))
    cold = br.loss(i, 25.0, 25.0, 60.0, 373.0)["total"]
    hot = br.loss(i, 125.0, 125.0, 60.0, 373.0)["total"]
    assert hot > cold, f"leakage did not rise with Tj ({cold:.6f} -> {hot:.6f} W)"


def test_a_bridge_datasheets_leakage_reaches_the_engine():
    """THE HALF THAT IS EASY TO MISS. Declaring the key and adding the dataclass field both pass
    their own checks while the value still goes nowhere, because `_bridge_block` also has to carry
    it — that is precisely the C211 defect (parsed cleanly, landed on a name the part's class does
    not have, dropped downstream). Caught here by following the value instead of the declarations.

    Two points are required: leakage roughly decades with temperature, so a single published I_R
    is a number and not a curve, and interpolating from it would invent the slope.
    """
    from app.mode_b.semiconductor.datasheet_flow import profile_to_block

    def profile(entries):
        return {"parameters": [
            {"key": "I_rev_vs_Tj", "entries": entries},
            {"key": "V_F_vs_IF", "entries": [
                {"typ": 0.9, "conditions": {"I_F": 10.0, "T_j": 25.0}, "confirmed": True}]}]}

    pts = [{"typ": 5e-6, "conditions": {"T_j": 25.0, "V_R": 400.0}, "confirmed": True},
           {"typ": 50e-6, "conditions": {"T_j": 125.0, "V_R": 400.0}, "confirmed": True}]
    design = {"vout": 393.0, "fsw": 70e3}

    blk = profile_to_block(profile(pts), "bridge_rectifier", design)
    assert blk.get("irev_curve") == [[25.0, 125.0], [5e-6, 50e-6]], (
        f"a bridge profile's I_rev_vs_Tj did not reach the block: {blk.get('irev_curve')!r}")
    assert blk.get("_irev_at_VR") == [400.0], "the reverse voltage the leakage was quoted at was lost"

    one = profile_to_block(profile(pts[:1]), "bridge_rectifier", design)
    assert one.get("irev_curve") is None, (
        "a single leakage point must NOT become a curve — the slope would be invented")


@pytest.mark.parametrize("with_curve", [False, True])
def test_the_report_states_the_bridge_blocking_loss_either_way(with_curve):
    """C253b. The leakage was real and inside the bridge total, and the report never mentioned it —
    so a reader could not tell whether it was modelled, omitted, or already counted. Section 7.3
    now says which, WITH the number when there is one.

    Both branches are asserted because the silent state is the dangerous one: "we did not model it"
    and "we modelled it and it is 10 mW" are different claims, and a page that says neither reads
    identically to a page where the term was forgotten.
    """
    import io
    import matplotlib
    matplotlib.use("Agg")
    from pypdf import PdfReader
    from app.mode_b.semiconductor import adapter as AD
    from app.mode_b.report_semiconductor import build_semiconductor_report

    P = AD.REFERENCE_PARTS
    design = dict(AD.REFERENCE_DESIGN)
    design.update({"eta": 0.95, "pf": 0.99, "V_GS_drive": 18.0, "R_g_on": 4.7,
                   "R_g_off": 10.0, "R_th_cs": 0.3, "nch": 2})
    thermal = dict(P["thermal"]); thermal["t_ambient"] = 50.0
    bridge = dict(P["bridge"])
    if with_curve:
        bridge["irev_curve"] = [[25.0, 125.0], [1e-6, 35e-6]]

    pdf = build_semiconductor_report(design, P["mosfet"], P["diode"], bridge, thermal,
                                     {"fet": 150, "diode": 150, "bridge": 130})
    text = "".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(pdf)).pages)

    assert "Blocking (leakage) loss" in text, "Section 7.3 says nothing about blocking loss"
    if with_curve:
        assert "is included in the totals above" in text, (
            "a bridge WITH a leakage curve must say the term is counted, and give the number")
        assert "mW at worst" in text, "the milliwatt figure is missing from the note"
    else:
        assert "is not modelled for this part" in text, (
            "a bridge with no leakage curve must say so — silence reads as 'already counted'")


def test_the_registry_agrees_that_a_bridge_can_carry_a_leakage_curve():
    """`I_rev_vs_Tj` was declared for the two diode classes only, so a bridge datasheet's I_R had
    nowhere to go. Declaration and dataclass field must land together or `audit_device_classes`
    flags it — which is the disconnect the registry exists to prevent."""
    import dataclasses as dc
    from app.mode_b.semiconductor.pfc_loss_model import Bridge
    from app.mode_b.semiconductor.registry import audit_device_classes, load

    assert "irev_curve" in {f.name for f in dc.fields(Bridge)}, "Bridge lost its irev_curve field"
    param = next(p for p in load()["parameters"] if p["key"] == "I_rev_vs_Tj")
    assert "bridge_rectifier" in param["device_classes"], (
        "I_rev_vs_Tj is not declared for bridge_rectifier, so an extracted bridge leakage curve "
        "would be parsed and then dropped — exactly the C211 failure")
    assert audit_device_classes() == [], "registry audit is no longer clean"
