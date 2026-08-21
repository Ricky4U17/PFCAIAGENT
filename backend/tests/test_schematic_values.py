"""THE VALUES ON THE FAN9672 SCHEMATIC MUST BE THE ENGINE'S, NOT THE DRAWING'S OWN DEFAULTS.

C235. The designer reported that Figures B.2a/B.2b showed wrong component values. Two were wrong:

    R_RLPK      drawn 15 kOhm, engine value 12.1 kOhm - Table B.1 and Section 6.3.2 both said 12.1
    R_FB1 unit  drawn "3.63 MOhm x3" = a 10.89 MOhm string; 3.63 MOhm is the TOTAL and the
                per-unit value is 1.21 MOhm, so the feedback divider top was drawn 3x too large

Cause: the drawing asks its context for 22 keys and the report supplied 10. The other twelve fell
back to literals inside `schematics.py`. TEN OF THOSE LITERALS HAPPENED TO BE CORRECT for this
design, which is worse than being wrong - they agree only by coincidence and drift silently the
moment a spec changes. Both real defects were in the other two.

WHY THIS TEST EXISTS IN THIS FORM. The values are drawn into a raster image, so no text assertion
on the built PDF can reach them - the defect survived every existing check and was found by eye.
Rather than leave it eyeball-only, `fan9672_application_schematic` now takes a `_resolved` dict
recording what each key resolved to and whether it was defaulted. That is what is asserted here.

VERIFIED AGAINST THE BUG: reverting either value in the report's context dict fails this file.
"""
import pytest

# Keys with no engine value: genuinely fixed-practice parts, drawn grey and labelled "(typ)" in the
# figure. They are ALLOWED to default. Everything else must come from the engine.
FIXED_PRACTICE = {"rf", "cf", "rpin8"}
# The whole pin-filter family left this set. C238 moved `cil` alone; the designer then found C_VIR
# and C_RLPK still disagreeing with the GUI, so C239 moved `cil2`, `crlpk`, `cvir` and `clpk` too,
# and `css` now carries the SELECTED value rather than the calculated one. Only the CS-sense filter
# (rf/cf) and the pin-8 pull-up genuinely have no engine value left.


@pytest.fixture(scope="module")
def ctx():
    """The context the report builds, assembled exactly as `_build_app_schematic_section` does."""
    from app.mode_b.step16_steps1_8 import compute_steps_1_8
    from app.mode_b.step16_step9_bibo import compute_step9_bibo
    from app.mode_b.step16_step10_iloop import compute_step10_iloop
    from app.mode_b.step16_step11_vloop import compute_step11_vloop

    prior = compute_steps_1_8({})
    inp = prior.get("inputs", {})
    c, s5, s8 = prior["const"], prior["step5"], prior["step8"]
    b = compute_step9_bibo(inp)
    d10 = compute_step10_iloop(inp, prior)
    cm = (compute_step11_vloop(inp, prior) or {}).get("comp", {}) or {}
    base = dict(
        rb1=b.get("rb1"), rb2=b.get("rb2"), rb3=b.get("rb3"), rb4=b.get("rb4"),
        cb1=b.get("cb1"), cb2=b.get("cb2"),
        r_gc_sel=s8.get("r_gc_sel"), c_gc=s8.get("c_gc"),
        r_ilimit_sel=s8.get("r_ilimit_sel"), r_ilimit2_sel=s8.get("r_ilimit2_sel"),
        r_ls_sel=s8.get("r_ls_sel"), c_ls=s8.get("c_ls"), css=s8.get("css_sel"),
        rri=s8.get("rri"), rcs_mohm=(s8.get("rcs_sel") or 0.015) * 1e3,
        r_ic=d10.get("ric"), c_ic1=d10.get("cic1"), c_ic2=d10.get("cic2"),
        r_vc=cm.get("r2s"), c_vc1=cm.get("c1s"), c_vc2=cm.get("c3s"),
        r3=cm.get("r3s"), c_v3=cm.get("c2s"), vType=cm.get("type", "type3"),
        i_ilimit_uA=(s8.get("i_ilimit") or 0) * 1e6,
        vcs_pk_mV=(s8.get("vcs_pk") or 0) * 1e3,
        rrlpk=c.get("r_rlpk"), rfb_each=s5.get("rfb1_unit"), rfb2=s5.get("rfb2"),
        cil=s8.get("c_ilimit"), cil2=s8.get("c_ilimit2"), crlpk=s8.get("c_rlpk"),
        cvir=s8.get("c_vir"), clpk=s8.get("c_lpk"),
    )
    return {"base": base, "const": c, "step5": s5, "prior": prior}


def _draw(ctx, hi):
    from app.mode_b.schematics import fan9672_application_schematic
    c = ctx["const"]
    v = dict(ctx["base"])
    v["crest_A"] = 0.0
    v["iphi_pk_A"] = 0.0
    v["riac"] = c.get("riac_hv") if hi else c.get("riac_fr")
    v["rvir"] = c.get("r_vir_hv") if hi else c.get("r_vir_fr")
    resolved = {}
    fan9672_application_schematic(v, is_high=hi, _resolved=resolved)
    return resolved


@pytest.mark.parametrize("hi", [False, True], ids=["FR-low-line", "HV-high-line"])
def test_no_sized_component_falls_back_to_a_drawing_default(ctx, hi):
    """Every key with an engine value must be supplied. This is the CLASS the defect belonged to.

    Stated as "nothing defaulted" rather than "these values are right", because ten of the twelve
    defaults were right by coincidence and would have passed a value check while remaining a
    latent trap.
    """
    resolved = _draw(ctx, hi)
    defaulted = sorted(k for k, r in resolved.items()
                       if r["defaulted"] and k not in FIXED_PRACTICE)
    assert not defaulted, (
        f"sized components fell back to schematics.py literals: {defaulted} — "
        "thread them from the engine instead")


@pytest.mark.parametrize("hi", [False, True], ids=["FR-low-line", "HV-high-line"])
def test_drawn_values_equal_the_engine(ctx, hi):
    """The two that were actually wrong, plus the rest that share their source."""
    c, s5 = ctx["const"], ctx["step5"]
    resolved = _draw(ctx, hi)
    want = {
        "rrlpk": c["r_rlpk"],                                   # was drawn 15 kOhm
        "rfb_each": s5["rfb1_unit"],                            # was drawn 3.63 MOhm (the TOTAL)
        "rfb2": s5["rfb2"],
        "riac": c["riac_hv"] if hi else c["riac_fr"],
        "rvir": c["r_vir_hv"] if hi else c["r_vir_fr"],
    }
    for k, expect in want.items():
        got = resolved[k]["value"]
        assert got == pytest.approx(float(expect), rel=1e-9), \
            f"{k}: drawn {got}, engine says {expect}"


def test_r_fb1_string_totals_what_the_bom_reports(ctx):
    """The per-unit value times the string count must be the BOM's R_FB1.

    This is the defect that mattered electrically: the drawing multiplies its `rfb_each` by the
    string count in the label, so supplying the TOTAL there draws a divider 3x too large.
    """
    s5 = ctx["step5"]
    resolved = _draw(ctx, True)
    per_unit = resolved["rfb_each"]["value"]
    assert per_unit * s5["rfb1_count"] == pytest.approx(s5["rfb1"], rel=1e-9), (
        f"drawn {per_unit} x {s5['rfb1_count']} = {per_unit * s5['rfb1_count']}, "
        f"but the BOM reports R_FB1 = {s5['rfb1']}")


def test_a_none_in_the_context_does_not_reach_the_drawing(ctx):
    """A key threaded from an engine that did not compute it must fall back, not render "None".

    Threading values through created this hazard: `v.get(k, d)` returns None for a present-but-None
    key, so a missing engine result would have been formatted onto a schematic a designer might
    build from.
    """
    from app.mode_b.schematics import fan9672_application_schematic
    v = dict(ctx["base"])
    v["rrlpk"] = None
    v["crest_A"] = v["iphi_pk_A"] = 0.0
    resolved = {}
    fan9672_application_schematic(v, is_high=False, _resolved=resolved)
    assert resolved["rrlpk"]["value"] is not None, "None reached the drawing"
    assert resolved["rrlpk"]["defaulted"] is True
