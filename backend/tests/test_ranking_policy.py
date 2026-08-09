"""
M5 (C213) — rank only on quantities the catalogue measures.
===========================================================
The Top-10 loss ranking ordered candidates by a loss built from parameters the parametric export
does not carry. For the MOSFET that is E_oss, E_on/E_off, Q_gd and R_DS(on)-vs-T_j — absent on all
1311 parts, so every figure behind the ordering was estimated from eight columns. For the diode it
is Q_c and Q_rr, both substituted by an estimate that C210 measured 4-6x off on a real part.

An ordering computed from estimates ranks the estimates. What survives is the part of the catalogue
that is real: the bridge's V_f curve, and the bottom bypass FET's R_DS(on).
"""
import pytest

from app.mode_b.semiconductor import database as db

DESIGN = {"vin_min": 90, "vin_max": 264, "vout": 393, "fline": 60, "fsw": 65000,
          "L_phi_uH": 235, "nch": 2, "pout_lo": 1700, "pout_hi": 3600, "eta": 0.95,
          "r_input": 0.2, "pf": 0.99}


class TestWhatTheCatalogueCanStillRank:
    def test_the_bridge_is_ranked_because_its_forward_curve_is_a_real_column(self):
        """Bridge loss is conduction-dominated and `vf`/`vf_if` are measured columns, not
        estimates — so ordering bridges by loss orders the parts."""
        res = db.rank_by_loss("bridge", DESIGN, {}, top=3, max_eval=12)
        assert len(res) == 3
        assert all(r["loss_W"] > 0 for r in res)
        assert res == sorted(res, key=lambda r: r["loss_W"])

    def test_the_bottom_bypass_fet_is_ranked_on_conduction_only(self):
        """It commutates at line frequency, so its loss is I^2*R_DS(on) and `rdson` is real."""
        res = db.rank_by_loss("mosfet", DESIGN, {}, top=3, mode="conduction")
        assert len(res) == 3


class TestWhatItRefusesToRank:
    @pytest.mark.parametrize("kind,missing", [
        ("mosfet", "E_oss"),
        ("diode", "Q_c"),
    ])
    def test_it_refuses_rather_than_ordering_by_an_estimate(self, kind, missing):
        with pytest.raises(db.RankingUnsupported) as e:
            db.rank_by_loss(kind, DESIGN, {}, top=3)
        msg = str(e.value)
        assert missing in msg                      # says WHICH parameter is absent
        assert "datasheet" in msg                  # and what to do instead

    def test_the_refusal_is_a_400_not_a_500(self):
        """A refusal is a statement about the catalogue, not a server fault — and the reason has to
        reach the designer, because it is the argument for uploading a datasheet instead."""
        from fastapi.testclient import TestClient
        from app.main import app
        c = TestClient(app)
        r = c.post("/mode-b/semiconductor/database/mosfet/rank",
                   json={"design": DESIGN, "criteria": {}, "top": 3})
        assert r.status_code == 400
        assert "1311" in r.json()["detail"]

    def test_an_unknown_kind_is_still_a_404(self):
        from fastapi.testclient import TestClient
        from app.main import app
        c = TestClient(app)
        r = c.post("/mode-b/semiconductor/database/thyristor/rank",
                   json={"design": DESIGN, "criteria": {}, "top": 3})
        assert r.status_code == 404

    def test_the_policy_lives_with_the_ranking_not_with_one_caller(self):
        """Called directly, not only through the endpoint — a second caller must not be able to
        route around it."""
        assert db._LOSS_RANKABLE == ("bridge",)
        with pytest.raises(db.RankingUnsupported):
            db.rank_by_loss("diode", DESIGN, {}, top=1, max_eval=1)
