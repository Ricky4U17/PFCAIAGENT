"""END-TO-END TESTS THROUGH THE HTTP ENDPOINTS, IN THE ORDER THE GUI CALLS THEM.

WHY THIS FILE EXISTS. Every other test in this suite calls the engine functions directly. That is
how three separate pieces of curve work — C215's diode curves, C224's MOSFET curves and C225's
measured switching energy — could each be built, verified and shipped while being completely
unreachable from the screen: `confirm()` deleted every accepted curve, and no test ran
`confirm_figure` and `confirm` in the order the Curves tab does. The engine was right, the
endpoints were right individually, and the SEQUENCE was broken.

So these tests are deliberately not unit tests. They exercise the real FastAPI app over the real
request models, in the real order, and assert on what the screen would actually receive. When a
future feature works in a unit test but not in the browser, this is the file that should have
caught it.

ISOLATION. The endpoints take no store root — production correctly writes to the one real parts
library — so `DEFAULT_ROOT` is redirected to a temp directory for the duration. Without that these
tests would deposit parts in the shipped library, under the user's OneDrive.
"""
import io
import os
import shutil
import tempfile

import pytest

_MOSFET = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "specs", "Review", "IMZA65R033M2HXKSA1.pdf")

DESIGN = {"vin_min": 90, "vin_max": 264, "vout": 393, "fline": 60, "fsw": 70000,
          "L_phi_uH": 235, "nch": 2, "pout_lo": 1700, "pout_hi": 3600,
          "eta": 0.95, "r_input": 0.2, "pf": 0.99}
# An ASYMMETRIC gate path on purpose: it makes the two K_Rg corrections distinguishable, so a
# single shared factor cannot pass these tests. `sw_method` is deliberately ABSENT — the whole
# point is that confirming the curves is what resolves it, and supplying it here would hide that.
GATE = {"V_GS_drive": 18.0, "R_g_on": 4.7, "R_g_off": 10.0, "R_th_cs": 0.3}


@pytest.fixture(scope="module")
def pdf():
    if not os.path.exists(_MOSFET):
        pytest.skip("IMZA65R033M2HXKSA1 datasheet not available")
    with open(_MOSFET, "rb") as f:
        return f.read()


@pytest.fixture()
def api():
    """The real app, with the parts library pointed at a temp directory."""
    from fastapi.testclient import TestClient
    from app.mode_b.semiconductor import parts_store as PS
    import app.main as main

    root = tempfile.mkdtemp(prefix="api_flow_")
    original = PS.DEFAULT_ROOT
    PS.DEFAULT_ROOT = root
    try:
        with TestClient(main.app) as client:
            yield client
    finally:
        PS.DEFAULT_ROOT = original
        shutil.rmtree(root, ignore_errors=True)


def _upload(api, pdf, part="APITEST-1"):
    r = api.post("/mode-b/semiconductor/datasheet/upload",
                 files={"file": ("ds.pdf", io.BytesIO(pdf), "application/pdf")},
                 data={"kind": "mosfet", "device_class": "sic_mosfet", "part_number": part})
    assert r.status_code == 200, r.text
    return r.json()


def _proposals(api, pdf, part):
    r = api.post("/mode-b/semiconductor/datasheet/figures",
                 files={"file": ("ds.pdf", io.BytesIO(pdf), "application/pdf")},
                 data={"part_number": part})
    assert r.status_code == 200, r.text
    return {p["key"]: p for p in r.json()["proposals"]}


def _accept(api, part, prop, key=None):
    """Exactly the body the Curves tab sends, including the source fields C225 added."""
    ci = (prop.get("cross_check") or {}).get("curve_index", 0)
    c = prop["curves"][ci]
    r = api.post("/mode-b/semiconductor/datasheet/figure-confirm",
                 json={"part_number": part, "key": key or prop["key"],
                       "curve": {"x": c["x"], "y": c["y"], "caption": prop.get("caption"),
                                 "page": prop.get("page"), "frame": prop.get("frame")},
                       "conditions": {}})
    assert r.status_code == 200, r.text
    return r.json()


def _confirm(api, part, edits=None):
    r = api.post("/mode-b/semiconductor/datasheet/confirm",
                 json={"part_number": part, "kind": "mosfet", "device_class": "sic_mosfet",
                       "edits": edits or {}, "design": {**DESIGN, **GATE}})
    assert r.status_code == 200, r.text
    return r.json()


class TestTheCurvesTabSequence:
    """Upload -> read figures -> accept -> confirm, which is what the screen does, and which is
    the exact ordering that hid the C225 defect."""

    def test_accepting_a_curve_then_confirming_keeps_it(self, api, pdf):
        """THE REGRESSION THAT MOTIVATED THIS FILE. The tab re-confirms after every Accept so the
        engine block rebuilds; `confirm` used to rebuild from the extraction and drop the curve.

        E_oss is the right single-curve probe: it reaches the engine on its own. E_on and E_off
        deliberately do not — the switching model needs BOTH before it will replace the analytic
        one — so neither would prove anything about survival by itself."""
        part = _upload(api, pdf)["part_number"]
        props = _proposals(api, pdf, part)
        before = _confirm(api, part)["block"]["_provenance"].get("E_oss_vs_VDS")
        assert before == "derived"                       # the fitted shape, before any curve
        _accept(api, part, props["E_oss_vs_VDS"])
        after = _confirm(api, part)["block"]["_provenance"].get("E_oss_vs_VDS")
        assert after == "digitised", "the accepted curve did not survive confirm"

    def test_accepting_every_target_one_at_a_time_reaches_the_measured_model(self, api, pdf):
        """A real session: accept, confirm, accept, confirm... Each confirm must preserve what the
        previous ones accepted, or only the last curve survives."""
        part = _upload(api, pdf)["part_number"]
        props = _proposals(api, pdf, part)
        keys = ("E_oss_vs_VDS", "C_rss_vs_VDS", "R_DS_on_vs_Tj", "R_DS_on_vs_ID",
                "E_on_vs_ID", "E_off_vs_ID", "E_on_vs_Rg", "E_off_vs_Rg")
        res = None
        for k in keys:
            _accept(api, part, props[k])
            res = _confirm(api, part)                     # what the tab does after each Accept
        blk = res["block"]
        prov = blk.get("_provenance", {})
        # The six keys that carry an engine field must all be marked digitised. The two *_vs_Rg
        # curves deliberately have none — they are consumed as the K_Rg RATIOS, so they show up in
        # `_esw_basis` rather than in the provenance map, and that is asserted separately below.
        for k in ("E_oss_vs_VDS", "C_rss_vs_VDS", "R_DS_on_vs_Tj", "R_DS_on_vs_ID",
                  "E_on_vs_ID", "E_off_vs_ID"):
            assert prov.get(k) == "digitised", f"{k} was lost during the sequence"
        assert blk["_esw_basis"]["k_rg_on"] != 1.0       # the R_g curves did take effect
        assert blk["sw_method"] == "esw"
        # AND THE BLOCK IS NOW FULLY DETERMINED. `sw_method` is the one design input this flow
        # never supplies, so before the curves it shows up as a field the engine would have to
        # default. Confirming them resolves it from evidence, and validation goes clean — which is
        # a stronger statement than "no error": nothing in the block is an engine default any more.
        assert res["validation"]["ok"] is True, res["validation"].get("defaulted")

    def test_the_gate_paths_are_corrected_independently_end_to_end(self, api, pdf):
        """4.7 ohm on and 10 ohm off must produce two DIFFERENT factors all the way out to the
        response the screen receives — a single shared correction would pass a weaker assertion."""
        part = _upload(api, pdf)["part_number"]
        props = _proposals(api, pdf, part)
        for k in ("E_oss_vs_VDS", "E_on_vs_ID", "E_off_vs_ID", "E_on_vs_Rg", "E_off_vs_Rg"):
            _accept(api, part, props[k])
        e = _confirm(api, part)["block"]["_esw_basis"]
        assert e["ok"] is True
        assert e["k_rg_on"] > 1.2 and e["k_rg_off"] > e["k_rg_on"] + 0.5

    def test_the_figures_the_report_shows_are_carried_on_the_block(self, api, pdf):
        """C225 renders the source plot at confirm time; the report reads it off the block. If the
        path does not survive the round trip the evidence panel is silently empty."""
        part = _upload(api, pdf)["part_number"]
        props = _proposals(api, pdf, part)
        for k in ("E_oss_vs_VDS", "E_on_vs_ID"):
            _accept(api, part, props[k])
        imgs = _confirm(api, part)["block"].get("_figure_images") or []
        assert len(imgs) == 2
        for i in imgs:
            assert os.path.exists(i["path"]) and os.path.getsize(i["path"]) > 1000

    def test_a_second_upload_of_the_same_part_does_not_resurrect_old_curves(self, api, pdf):
        """Re-uploading is how a designer corrects a wrong file. The curves belonged to the old
        reading and must not silently carry into the new one."""
        part = _upload(api, pdf)["part_number"]
        props = _proposals(api, pdf, part)
        _accept(api, part, props["E_oss_vs_VDS"])
        assert _confirm(api, part)["block"]["_provenance"].get("E_oss_vs_VDS") == "digitised"
        r = api.post("/mode-b/semiconductor/datasheet/discard", json={"part_number": part})
        assert r.status_code == 200, r.text
        part2 = _upload(api, pdf)["part_number"]
        blk = _confirm(api, part2)["block"]
        assert blk["_provenance"].get("E_oss_vs_VDS") == "derived"   # back to the fitted shape
        assert blk.get("sw_method") != "esw"


class TestTheWholeMosfetFlow:
    """Requirement -> upload -> review -> confirm -> calculate, the whole screen in order."""

    def test_the_requirement_comes_before_any_part(self, api):
        r = api.post("/mode-b/semiconductor/datasheet/requirements",
                     json={"design": DESIGN, "kind": "mosfet"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["V_DSS_min"] > DESIGN["vout"]
        assert "IMZA" not in repr(body).upper()      # the requirement may not name a part

    def test_upload_returns_rows_a_designer_can_review(self, api, pdf):
        up = _upload(api, pdf)
        assert up["ok"] is True and len(up["rows"]) > 10
        assert all(r.get("destination") for r in up["rows"])

    def test_confirm_then_calculate_produces_losses(self, api, pdf):
        """The end of the screen: the block the confirm step returns must be directly usable by
        /calculate, because that is precisely what the Results tab does with it."""
        part = _upload(api, pdf)["part_number"]
        props = _proposals(api, pdf, part)
        for k in ("E_oss_vs_VDS", "E_on_vs_ID", "E_off_vs_ID", "E_on_vs_Rg", "E_off_vs_Rg"):
            _accept(api, part, props[k])
        blk = _confirm(api, part)["block"]

        r = api.post("/mode-b/semiconductor/calculate",
                     json={"design": {**DESIGN, **GATE}, "mosfet": blk,
                           "diode": {"is_sic": True, "vf_curve": [[1, 5, 16], [1.05, 1.35, 1.7]],
                                     "qc": 20e-9, "rth_jc": 0.7, "rth_cs": 0.3},
                           "bridge": {"topology": "diode",
                                      "vf_curve": [[1, 12, 24], [0.75, 0.95, 1.15]],
                                      "n_parallel": 2, "rth_jc": 1.0, "rth_cs": 0.5},
                           "thermal": {"t_ambient": 45.0, "rth_sa": 0.35}})
        assert r.status_code == 200, r.text
        res = r.json()
        assert res["validation"]["ok"] is True, res["validation"]["issues"]
        assert len(res["per_point"]) == 9
        assert res["summary"]["P_FET_max"] > 0
        # the diode columns must reconcile — the hidden-remainder defect Table 7.5 had
        for row in res["per_point"]:
            total = row["P_D_cond"] + row["P_D_sw"] + row.get("P_D_leak", 0.0)
            assert total == pytest.approx(row["P_DIODE_total"], rel=1e-9)

        # AND THE THREE COMPONENT TOTALS MUST SUM TO THE SYSTEM TOTAL. The Results tab shows
        # exactly these four numbers side by side, so any term living outside the three is read as
        # an arithmetic error by whoever adds them up. `P_SEMI_total` counts gate drive while
        # `P_FET_total` does not, so the FET column carries it — the same grouping Chapter 7
        # Table 7.4 uses. This assertion is what keeps the screen and the report on one convention.
        for row in res["per_point"]:
            fet = row["P_FET_total"] + row.get("P_gate_driver", 0.0)
            parts = fet + row["P_DIODE_total"] + row["P_BRIDGE_total"]
            assert parts == pytest.approx(row["P_SEMI_total"], rel=1e-9), (
                f"{row['Vac']:.0f} Vac: FET+Diode+Bridge {parts:.4f} != SEMI "
                f"{row['P_SEMI_total']:.4f}")

    def test_an_unreadable_pdf_is_refused_with_a_reason(self, api):
        """A refusal and an empty extraction look identical to the screen unless it says which."""
        import fitz
        blank = fitz.open(); blank.new_page()
        r = api.post("/mode-b/semiconductor/datasheet/upload",
                     files={"file": ("blank.pdf", io.BytesIO(blank.tobytes()),
                                     "application/pdf")},
                     data={"kind": "mosfet", "device_class": "sic_mosfet"})
        assert r.status_code == 200, r.text
        assert r.json()["ok"] is False and r.json()["reason"]

    def test_an_unknown_component_kind_is_a_404_not_a_500(self, api, pdf):
        r = api.post("/mode-b/semiconductor/datasheet/upload",
                     files={"file": ("ds.pdf", io.BytesIO(pdf), "application/pdf")},
                     data={"kind": "flux_capacitor"})
        assert r.status_code == 404


class TestTheLibraryLifecycle:
    """Provisional until published (C219), and discardable — over HTTP, where the screen sees it."""

    def test_an_uploaded_part_is_not_in_the_library_until_published(self, api, pdf):
        part = _upload(api, pdf)["part_number"]
        lib = api.get("/mode-b/semiconductor/datasheet/library")
        assert lib.status_code == 200, lib.text
        entry = next((p for p in lib.json()["parts"] if p["part_number"] == part), None)
        assert entry is not None and entry.get("published") is False

        r = api.post("/mode-b/semiconductor/datasheet/publish",
                     json={"part_number": part, "published": True})
        assert r.status_code == 200, r.text
        lib = api.get("/mode-b/semiconductor/datasheet/library").json()
        entry = next(p for p in lib["parts"] if p["part_number"] == part)
        assert entry.get("published") is True

    def test_discarding_removes_it(self, api, pdf):
        part = _upload(api, pdf)["part_number"]
        assert api.post("/mode-b/semiconductor/datasheet/discard",
                        json={"part_number": part}).status_code == 200
        lib = api.get("/mode-b/semiconductor/datasheet/library").json()
        assert not any(p["part_number"] == part for p in lib["parts"])


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# B19 — the RASTER path, driven end to end in the order the Curves tab calls it.
#
# THIS CLASS IS THE POINT OF B19'S SECOND HALF. C276 built the tracer and proved it against the
# part's own table, and it was still unreachable from the screen. C215, C224 and C225 EACH shipped
# curve work that passed every unit test and was dead in the GUI, because no test ran the endpoints
# in sequence — and this file exists because of that. So the raster path gets its sequence test in
# the same commit as its wiring, not afterwards.
# ═══════════════════════════════════════════════════════════════════════════════════════════════

_TOSHIBA = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "specs", "Review", "PFC Boost Diode",
    "TRS12E65H_datasheet_en_20230411.pdf")

# What a designer reads off Fig. 9.1 and types in.
_TOSHIBA_AXES = {"x_min": 0.0, "x_max": 2.0, "y_min": 0.0, "y_max": 12.0,
                 "x_title": "Forward voltage V_F (V)", "y_title": "Forward current I_F (A)"}


@pytest.fixture(scope="module")
def toshiba():
    if not os.path.exists(_TOSHIBA):
        pytest.skip("TRS12E65H datasheet not available")
    with open(_TOSHIBA, "rb") as f:
        return f.read()


def _upload_diode(api, pdf, part="APITEST-RASTER"):
    r = api.post("/mode-b/semiconductor/datasheet/upload",
                 files={"file": ("ds.pdf", io.BytesIO(pdf), "application/pdf")},
                 data={"kind": "diode", "device_class": "sic_schottky", "part_number": part})
    assert r.status_code == 200, r.text
    return r.json()


def _raster_candidates(api, pdf):
    r = api.post("/mode-b/semiconductor/datasheet/raster-figures",
                 files={"file": ("ds.pdf", io.BytesIO(pdf), "application/pdf")})
    assert r.status_code == 200, r.text
    return r.json()


def _raster_digitise(api, pdf, cand, part, key="V_F_vs_IF", **over):
    data = {"page": cand["page"], "xref": cand["xref"], "key": key,
            "part_number": part, **_TOSHIBA_AXES}
    data.update(over)
    r = api.post("/mode-b/semiconductor/datasheet/raster-digitise",
                 files={"file": ("ds.pdf", io.BytesIO(pdf), "application/pdf")},
                 data={k: str(v) for k, v in data.items()})
    assert r.status_code == 200, r.text
    return r.json()


class TestTheRasterCurvesTabSequence:
    """Upload -> list bitmaps -> read the axes off the picture -> digitise -> accept -> it is in
    the profile. Every step is the real endpoint, in the order the screen calls them."""

    def test_the_vector_endpoint_still_offers_nothing_for_this_file(self, api, toshiba):
        """The premise. If `/figures` ever starts proposing here, the raster path is redundant and
        this whole flow should be reconsidered rather than left running beside it."""
        part = _upload_diode(api, toshiba)["part_number"]
        assert _proposals(api, toshiba, part) == {}

    def test_the_bitmap_figures_are_listed_with_their_captions(self, api, toshiba):
        """The designer picks from this list, so it has to say which figure each row is. The
        captions are text even on a page whose figures are bitmaps."""
        out = _raster_candidates(api, toshiba)
        assert out["ok"] and len(out["candidates"]) >= 8
        caps = " | ".join(c["caption"] for c in out["candidates"])
        assert "Fig. 9.1" in caps and "IF - VF" in caps

    def test_digitising_returns_a_proposal_in_the_ORDINARY_shape(self, api, toshiba):
        """It must be indistinguishable from a vector proposal to the tab that renders it, or the
        Curves UI would need a second code path — and a second path is where the two drift."""
        part = _upload_diode(api, toshiba)["part_number"]
        cand = next(c for c in _raster_candidates(api, toshiba)["candidates"]
                    if "9.1" in c["caption"])
        out = _raster_digitise(api, toshiba, cand, part)
        assert out["ok"], out.get("reason")
        p = out["proposal"]
        for field in ("key", "page", "frame", "caption", "axes", "x_range", "y_range",
                      "n_curves", "curves", "cross_check", "per_temperature", "swapped"):
            assert field in p, f"a vector proposal carries {field!r} and this one does not"
        assert p["source"] == "raster" and p["calibration_source"] == "designer"
        assert p["n_curves"] >= 4

    def test_the_proposal_carries_the_table_cross_check(self, api, toshiba):
        """The evidence, and the only gate on this path — there is no residual to report because
        the axes were typed in, not fitted."""
        part = _upload_diode(api, toshiba)["part_number"]
        cand = next(c for c in _raster_candidates(api, toshiba)["candidates"]
                    if "9.1" in c["caption"])
        p = _raster_digitise(api, toshiba, cand, part)["proposal"]
        cc = p["cross_check"]
        assert cc["checked"], f"nothing checked it against the table: {cc}"
        assert cc["agrees"], f"the traced curve disagrees with the tabulated V_F: {cc}"

    def test_a_wrong_axis_range_is_refused_by_the_cross_check(self, api, toshiba):
        """The same figure against 0..10 A instead of 0..12 A traces perfectly well and is WRONG.
        Nothing about the picture says so; only the table does."""
        part = _upload_diode(api, toshiba)["part_number"]
        cand = next(c for c in _raster_candidates(api, toshiba)["candidates"]
                    if "9.1" in c["caption"])
        p = _raster_digitise(api, toshiba, cand, part, y_max=10.0)["proposal"]
        assert p["n_curves"] >= 1, "the trace itself should still succeed"
        assert not p["cross_check"]["agrees"], (
            "a figure digitised against a wrong axis range still satisfied the table anchor")

    def test_an_accepted_raster_curve_reaches_the_profile(self, api, toshiba):
        """THE WHOLE SEQUENCE. The curve goes through the SAME figure-confirm the vector path
        uses, lands under the same canonical key, and is stamped `digitised` like any other shape
        read off a picture."""
        part = _upload_diode(api, toshiba)["part_number"]
        cand = next(c for c in _raster_candidates(api, toshiba)["candidates"]
                    if "9.1" in c["caption"])
        p = _raster_digitise(api, toshiba, cand, part)["proposal"]
        res = _accept(api, part, p)
        assert res["ok"] and res["key"] == "V_F_vs_IF" and res["n_points"] > 50

        from app.mode_b.semiconductor import parts_store as PS
        prof = PS.load_profile(part, kind="confirmed")
        entry = next(e for pm in prof["parameters"] if pm["key"] == "V_F_vs_IF"
                     for e in pm["entries"] if e.get("provenance") == "digitised")
        assert entry["source"]["page"] == 4
        assert len(entry["typ"][0]) == res["n_points"]

    def test_the_accepted_curve_is_the_forward_characteristic_the_right_way_round(self, api, toshiba):
        """`V_F_vs_IF` is swapped on the way out, so the stored x is CURRENT and y is VOLTAGE. Get
        this backwards and the engine reads a 12 V forward drop — the C215 transposed-axis bug,
        which was worth -692 W before it was caught."""
        part = _upload_diode(api, toshiba)["part_number"]
        cand = next(c for c in _raster_candidates(api, toshiba)["candidates"]
                    if "9.1" in c["caption"])
        p = _raster_digitise(api, toshiba, cand, part)["proposal"]
        _accept(api, part, p)
        from app.mode_b.semiconductor import parts_store as PS
        prof = PS.load_profile(part, kind="confirmed")
        xs, ys = next(e["typ"] for pm in prof["parameters"] if pm["key"] == "V_F_vs_IF"
                      for e in pm["entries"] if e.get("provenance") == "digitised")
        assert max(xs) > 5.0, "x should be forward CURRENT, running to ~12 A"
        assert 0.2 <= max(ys) <= 8.0, f"y should be a forward VOLTAGE, got up to {max(ys)}"
