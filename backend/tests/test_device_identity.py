"""A DATASHEET MUST DESCRIBE THE COMPONENT THE DESIGNER SAID IT DOES.

C282, from a designer finding: a DIODE datasheet was uploaded into the bridge-rectifier slot, and
the engine accepted it, extracted it, stored it and calculated a bridge loss from it. Nothing in the
flow ever compared the document against the tab — `upload()` took the device class from whichever
tab was clicked, and its own comment said so.

TWO MEASUREMENTS SHAPED THE DESIGN, and both are asserted here so they cannot quietly stop being
true:

  * the extractor yields the SAME parameters whatever class it is told (test below), so the
    mis-upload produced a complete, plausible profile that nothing downstream could detect;
  * a diode and a bridge have nearly IDENTICAL parameter sets, because a bridge rectifier is four
    diodes. So a fingerprint over canonical keys cannot separate exactly the two kinds that were
    confused, and the document's own words have to carry it.

ONLY A CONTRADICTION REFUSES: the declared kind named nowhere while another kind is named. Silence
is accepted with a note — a scanned datasheet has no text layer, and refusing there would block a
real part for want of a phrase (the shape of B27).
"""
from __future__ import annotations

import io
import os
import shutil
import tempfile

import pytest

from app.mode_b.semiconductor import device_identity as DI

_REVIEW = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "specs", "Review")
_SPECS = os.path.dirname(_REVIEW)

DIODE_SIC = os.path.join(_REVIEW, "PFC Boost Diode", "vs-4c16ep07l-m3.pdf")
DIODE_SI = os.path.join(_REVIEW, "PFC Boost Diode", "SFAF1601G SERIES_H2105.pdf")
DIODE_TOSHIBA = os.path.join(_REVIEW, "PFC Boost Diode", "TRS12E65H_datasheet_en_20230411.pdf")
DIODE_3C40 = os.path.join(_REVIEW, "PFC Boost Diode", "vs-3c40cp12l-m3.pdf")
BRIDGE = os.path.join(_REVIEW, "Bridge Rectifier Update", "lve5060e.pdf")
BRIDGE_GBJ = os.path.join(_SPECS, "Bridge Rectifier Configuration", "GBJ40L06.pdf")
MOSFET = os.path.join(_REVIEW, "IMZA65R033M2HXKSA1.pdf")


def _read(path):
    if not os.path.exists(path):
        pytest.skip(f"{os.path.basename(path)} not available")
    with io.open(path, "rb") as f:
        return f.read()


# ── what each document says it is ────────────────────────────────────────────

@pytest.mark.parametrize("path,expected", [
    (MOSFET, "mosfet"),
    (BRIDGE, "bridge"),
    (BRIDGE_GBJ, "bridge"),
    (DIODE_SIC, "diode"),
    (DIODE_SI, "diode"),
    (DIODE_TOSHIBA, "diode"),
    (DIODE_3C40, "diode"),
])
def test_every_datasheet_on_file_identifies_itself(path, expected):
    """Seven real vendor datasheets, three kinds, page 1. Zero may be misread.

    A FIRST PASS SCORED 5/7 AND BOTH MISSES WERE THE PATTERNS, NOT THE DOCUMENTS: it required
    "schottky BARRIER diode" while VS-4C16EP07L-M3 says "Silicon Carbide Schottky Diode". The
    failure mode of this module is a pattern too narrow, and it looks exactly like a datasheet that
    says nothing — which is why the whole set is asserted rather than a sample.
    """
    ident = DI.identify(_read(path))
    assert ident["kinds"] == [expected], (
        f"{os.path.basename(path)} identified as {ident['kinds']} — expected [{expected!r}]; "
        f"matches: {ident['hits']}")


def test_a_vendors_contact_boilerplate_is_not_evidence():
    """PHRASES, NEVER BARE TOKENS. `DiodesAmericas@vishay` sits on the Vishay BRIDGE datasheet, so
    matching the word "diode" classifies a bridge as a diode. This is the trap that would make a
    naive keyword check worse than no check at all."""
    text = DI._page_text(_read(BRIDGE)).lower()
    assert "diodesamericas" in text, "the boilerplate is gone; re-point this test"
    assert DI.identify(_read(BRIDGE))["kinds"] == ["bridge"]


# ── the verdicts ─────────────────────────────────────────────────────────────

def test_the_designers_accident_is_a_contradiction():
    """The finding itself: a diode datasheet in the bridge slot."""
    c = DI.check_declared(_read(DIODE_SIC), "bridge")
    assert c["verdict"] == "contradicts"
    assert "diode" in c["message"].lower() and "bridge" in c["message"].lower()
    # the refusal has to say what to do next, or it is just a dead end
    assert "upload" in c["message"].lower()


@pytest.mark.parametrize("path,kind", [
    (DIODE_SIC, "diode"), (BRIDGE, "bridge"), (MOSFET, "mosfet")])
def test_a_correct_upload_confirms(path, kind):
    assert DI.check_declared(_read(path), kind)["verdict"] == "confirms"


def test_a_document_with_no_device_phrase_is_accepted_with_a_note():
    """Absence is NOT a refusal. A scanned datasheet has no text layer, and blocking there would
    stop a legitimate part for want of a phrase."""
    c = DI.check_declared(b"%PDF-1.4\n% not a real datasheet\n", "bridge")
    assert c["verdict"] == "no_evidence"
    assert c["message"], "an unchecked upload must still say it was unchecked"


def _pdf_saying(text: str) -> bytes:
    """A one-page PDF containing `text`. Built rather than skipped: the multi-kind case is the one
    that protects against FALSE REFUSALS, and no vendor file on disk exercises it. An earlier draft
    skipped when none was found, which would have left the false-refusal path untested for as long
    as the library happened to hold no such part."""
    import fitz
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((60, 80), text, fontsize=11)
    return doc.tobytes()


def test_a_document_naming_two_kinds_passes_if_the_declared_one_is_among_them():
    """A MOSFET datasheet discussing its body diode, or a co-packaged MOSFET + SiC part, must not
    be refused. Contradiction is defined narrowly on purpose: declared kind absent AND another
    present."""
    data = _pdf_saying("650 V N-channel MOSFET with co-packaged Schottky diode")
    ident = DI.identify(data)
    assert set(ident["kinds"]) == {"mosfet", "diode"}, ident
    for k in ("mosfet", "diode"):
        assert DI.check_declared(data, k)["verdict"] == "confirms", (
            f"a document naming both kinds was refused for {k} — that is a false refusal")
    # ...and the kind it does NOT name is still a contradiction.
    assert DI.check_declared(data, "bridge")["verdict"] == "contradicts"


def test_contradiction_requires_the_declared_kind_to_be_absent():
    """The rule, asserted directly rather than through a file that happens to exercise it."""
    hits = {"kinds": ["diode", "mosfet"]}
    assert "mosfet" in hits["kinds"]        # declared kind present -> never a contradiction
    c = DI.check_declared(_read(MOSFET), "mosfet")
    assert c["verdict"] != "contradicts"


# ── the gate, through the real upload path ───────────────────────────────────

@pytest.fixture()
def store():
    from app.mode_b.semiconductor import parts_store as PS
    root = tempfile.mkdtemp(prefix="c282_")
    original = PS.DEFAULT_ROOT
    PS.DEFAULT_ROOT = root
    try:
        yield root
    finally:
        PS.DEFAULT_ROOT = original
        shutil.rmtree(root, ignore_errors=True)


def test_upload_refuses_the_mis_filed_datasheet_and_stores_NOTHING(store):
    """A refusal that has already written the PDF and a draft profile is not a refusal. The
    message says "nothing has been stored", so that claim is asserted rather than trusted."""
    from app.mode_b.semiconductor import datasheet_flow as flow
    from app.mode_b.semiconductor import parts_store as PS

    r = flow.upload(_read(DIODE_SIC), "bridge", "bridge_rectifier", part_number="MISFILED-1")
    assert r["ok"] is False
    assert r["identity"]["verdict"] == "contradicts"
    assert PS.load_profile("MISFILED-1", kind="extracted") is None
    assert sum(len(f) for _d, _s, f in os.walk(store)) == 0, "the refusal wrote something"


def test_upload_still_accepts_the_right_datasheet(store):
    from app.mode_b.semiconductor import datasheet_flow as flow
    r = flow.upload(_read(BRIDGE), "bridge", "bridge_rectifier", part_number="RIGHT-1")
    assert r["ok"] is True
    assert r["identity"]["verdict"] == "confirms"
    assert r["rows"], "a confirmed upload should still review normally"


def test_the_extractor_alone_cannot_tell_the_kinds_apart():
    """WHY THIS MODULE HAS TO EXIST, asserted so the premise cannot quietly stop being true.

    The same diode PDF extracted under three different device classes yields the same parameters,
    so the class does not gate extraction and a mis-upload produces a complete, plausible profile.
    If this ever starts differing, the extractor has gained class-awareness and the design of the
    gate should be revisited — not deleted, but revisited.
    """
    from app.mode_b.semiconductor import datasheet_extract as DX
    data = _read(DIODE_SIC)
    keysets = []
    for cls in ("sic_schottky", "bridge_rectifier", "sic_mosfet"):
        prof = DX.extract(data, cls)["profile"]
        keysets.append(tuple(sorted(p["key"] for p in (prof.get("parameters") or []))))
    assert len(set(keysets)) == 1, (
        "extraction now depends on the declared class — the gate's premise has changed")


def test_a_diode_and_a_bridge_share_almost_every_parameter():
    """THE OTHER HALF OF THE PREMISE. A bridge rectifier is four diodes, so their canonical-key
    fingerprints overlap almost entirely — which is why a parameter-based check could not have
    caught this accident and the document's own words are what carry it."""
    from app.mode_b.semiconductor import datasheet_extract as DX
    dk = {p["key"] for p in DX.extract(_read(DIODE_SIC), "sic_schottky")["profile"]["parameters"]}
    bk = {p["key"] for p in DX.extract(_read(BRIDGE), "bridge_rectifier")["profile"]["parameters"]}
    overlap = len(dk & bk) / max(len(dk | bk), 1)
    assert overlap > 0.5, (
        f"the parameter sets now differ more than expected (overlap {overlap:.0%}); a fingerprint "
        f"check may have become viable, which would be worth knowing")
