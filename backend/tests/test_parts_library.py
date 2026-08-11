"""
C219 — a stored part is provisional until the designer publishes it, and Chapter 7 on its own.
==============================================================================================
Uploading a datasheet has to write it somewhere: the review screen, the confirm step and the figure
digitiser all read the stored profile. But writing is not the same as ADDING TO THE LIBRARY. A
datasheet uploaded by mistake was reaching the shared parts store before anyone had looked at it,
and a store whose entire value is its provenance cannot afford to fill up with wrong parts.
"""
import io
import os
import shutil
import tempfile

import pytest

from app.mode_b.semiconductor import datasheet_flow as DF
from app.mode_b.semiconductor import parts_store as PS

_MOSFET = os.path.join(os.path.dirname(__file__), "..", "..", "specs", "Review",
                       "IMZA65R033M2HXKSA1.pdf")

DESIGN = {"vin_min": 90, "vin_max": 264, "vout": 393, "fline": 60, "fsw": 65000,
          "L_phi_uH": 235, "nch": 2, "pout_lo": 1700, "pout_hi": 3600, "eta": 0.95,
          "r_input": 0.2, "pf": 0.99}


@pytest.fixture
def store():
    d = tempfile.mkdtemp(prefix="parts_lib_")
    try:
        yield d
    finally:
        shutil.rmtree(d, ignore_errors=True)


@pytest.fixture(scope="module")
def pdf():
    if not os.path.exists(_MOSFET):
        pytest.skip("IMZA65R033M2HXKSA1 datasheet not available")
    with io.open(_MOSFET, "rb") as f:
        return f.read()


def _upload(pdf, store):
    return DF.upload(pdf, "mosfet", "sic_mosfet", root=store)["part_number"]


class TestAPartIsProvisionalUntilPublished:
    def test_uploading_does_not_add_it_to_the_library(self, pdf, store):
        mpn = _upload(pdf, store)
        rec = next(r for r in PS.library(store) if r["part_number"] == mpn)
        assert rec["published"] is False

    def test_publishing_is_what_adds_it(self, pdf, store):
        mpn = _upload(pdf, store)
        PS.publish(mpn, root=store)
        rec = next(r for r in PS.library(store) if r["part_number"] == mpn)
        assert rec["published"] is True and rec["published_utc"]

    def test_it_can_be_taken_back_out(self, pdf, store):
        mpn = _upload(pdf, store)
        PS.publish(mpn, root=store)
        PS.publish(mpn, False, root=store)
        rec = next(r for r in PS.library(store) if r["part_number"] == mpn)
        assert rec["published"] is False

    def test_a_new_revision_is_not_vouched_for_by_its_predecessor(self, pdf, store):
        """Re-uploading a CORRECTED file for the same part number resets it to provisional. The
        previous revision having been approved says nothing about this one."""
        mpn = _upload(pdf, store)
        PS.publish(mpn, root=store)
        PS.store_datasheet(mpn, pdf + b"%corrected", root=store)     # different bytes, same part
        rec = next(r for r in PS.library(store) if r["part_number"] == mpn)
        assert rec["published"] is False

    def test_re_uploading_the_identical_file_changes_nothing(self, pdf, store):
        mpn = _upload(pdf, store)
        PS.publish(mpn, root=store)
        out = PS.store_datasheet(mpn, pdf, root=store)
        assert out["changed"] is False
        rec = next(r for r in PS.library(store) if r["part_number"] == mpn)
        assert rec["published"] is True          # a no-op must not retire an approved part


class TestDiscard:
    def test_a_provisional_part_can_be_discarded(self, pdf, store):
        """The point of the whole mechanism: a datasheet uploaded by mistake leaves no trace."""
        mpn = _upload(pdf, store)
        PS.discard(mpn, root=store)
        assert not [r for r in PS.library(store) if r["part_number"] == mpn]

    def test_a_published_part_refuses_to_be_deleted(self, pdf, store):
        """The stored profile is what lets the report answer "the machine read X, you confirmed Y".
        Deleting a published part breaks the trail the store exists to keep — so un-publishing is
        offered and deletion is not."""
        mpn = _upload(pdf, store)
        PS.publish(mpn, root=store)
        with pytest.raises(PS.PartsStoreError, match="published"):
            PS.discard(mpn, root=store)
        assert [r for r in PS.library(store) if r["part_number"] == mpn]

    def test_discarding_something_that_was_never_stored_says_so(self, store):
        with pytest.raises(PS.PartsStoreError, match="no datasheet on file"):
            PS.discard("NOT-A-PART", root=store)


class TestChapterSevenOnItsOwn:
    def test_it_is_the_same_builder_the_full_report_uses(self):
        """Not a second rendering of the chapter — the same one. A separate implementation would
        be free to disagree with the document it is meant to preview."""
        import inspect
        from app import main
        src = inspect.getsource(main.semiconductor_report)
        assert "build_semiconductor_report" in src

    def test_it_returns_a_pdf_of_the_chapter(self):
        from fastapi.testclient import TestClient
        from app.main import app
        from app.mode_b.semiconductor import database as sdb
        c = TestClient(app)
        r = c.post("/mode-b/semiconductor/report", json={
            "design": DESIGN,
            "mosfet": sdb.to_block(sdb.load("mosfet")[0], "mosfet"),
            "diode": sdb.to_block(sdb.load("diode")[0], "diode"),
            "bridge": sdb.to_block(sdb.load("bridge")[0], "bridge"),
            "thermal": {"t_ambient": 50, "rth_sa": 0.5}})
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/pdf"
        assert r.content[:5] == b"%PDF-"
        import fitz
        assert 8 <= fitz.open(stream=r.content, filetype="pdf").page_count <= 40

    def test_the_publish_endpoint_reports_a_bad_part_rather_than_failing_silently(self):
        from fastapi.testclient import TestClient
        from app.main import app
        c = TestClient(app)
        r = c.post("/mode-b/semiconductor/datasheet/publish",
                   json={"part_number": "NOT-A-PART", "published": True})
        assert r.status_code == 400 and "no datasheet on file" in r.json()["detail"]
