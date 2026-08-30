"""
device_identity.py — does this datasheet describe the component the designer said it does?
==========================================================================================
The designer uploaded a DIODE datasheet into the bridge-rectifier slot and the engine accepted it,
extracted it, and calculated a bridge loss from it. Nothing in the flow ever compared the document
against the tab: `upload()` takes the device class from whichever tab was clicked, and its own
comment says so — "the class comes from the tab the designer uploaded under, not from a field they
fill in".

Measured while designing this, and both facts shaped it:

  * THE EXTRACTOR DOES NOT CARE. The same diode PDF extracted under `sic_schottky`,
    `bridge_rectifier` and `sic_mosfet` yields a BYTE-IDENTICAL set of 12 parameters. So the
    mis-upload did not merely go unchecked — it produced a complete, plausible profile that nothing
    downstream could tell from a real one.
  * THE PARAMETERS CANNOT SEPARATE A DIODE FROM A BRIDGE. Both publish C_j, I2t, I_FSM, I_F_AV,
    I_rev_vs_Tj, R_th_jc, T_stg. That is physically correct — a bridge rectifier IS four diodes —
    so a fingerprint over canonical keys is strong for MOSFET-vs-rest and near-useless for exactly
    the confusion that happened. The document's own words are what carry it.

PHRASES, NEVER BARE TOKENS. `DiodesAmericas@vishay` appears on the Vishay BRIDGE datasheet, in its
contact boilerplate — so matching the word "diode" classifies a bridge as a diode. Every pattern
here is a device phrase ("schottky diode", "bridge rectifier"), which is why the boilerplate cannot
reach them.

A FIRST PASS AT THIS SCORED 5/7 AND THE TWO MISSES WERE MINE, not the datasheets'. The pattern
required "schottky BARRIER diode" while VS-4C16EP07L-M3 says "650 V Gen 4 Power Silicon Carbide
Schottky Diode, 16 A" — the evidence was on page 1 all along. The designer pointed at both files.
Written down because the failure mode of this module is a pattern that is too narrow, and it looks
exactly like a datasheet that says nothing.

CONTRADICTION IS DEFINED NARROWLY, and deliberately: the declared kind has ZERO evidence AND some
other kind has evidence. A document naming two kinds — a MOSFET datasheet discussing its body
diode, a co-packaged MOSFET+SiC part — still passes as long as the declared kind is among them.
Absence alone is never a refusal: a scanned datasheet has no text layer, and refusing there would
block a legitimate part for want of a phrase, which is the shape of PENDING B27.
"""
from __future__ import annotations

import re
from typing import Optional

# Pages searched. The product descriptor sits at the top of page 1 on every vendor on file
# ("Low VF Single-Phase Single In-Line Bridge Rectifiers"), directly under the document number.
# Two pages are read anyway so a cover sheet or a title page cannot hide it.
_PAGES = 2

# Device phrases, by the `kind` the upload endpoint uses. Ordered longest-first within a kind only
# for readability; every pattern is counted, so overlap is harmless.
_PATTERNS: dict[str, list[str]] = {
    "bridge": [
        r"bridge\s+rectifier",          # covers the plural
        r"single[-\s]phase.{0,30}bridge",
        r"three[-\s]phase.{0,30}bridge",
        r"bridge\s+diode",
        r"glass\s+passivated\s+bridge",
    ],
    "diode": [
        r"schottky\s+(barrier\s+)?diode",
        r"silicon\s+carbide\s+schottky",
        r"\bsic\s+diode\b",
        r"rectifier\s+diode",
        r"(super\s?fast|fast\s+recovery|ultra\s?fast|standard)\s+rectifier",
        r"barrier\s+rectifier",
        r"avalanche\s+diode",
        r"\bpin\s+diode\b",
    ],
    "mosfet": [
        r"\bmosfet\b",
        r"n[-\s]channel",
        r"p[-\s]channel",
        r"\bigbt\b",
        r"power\s+transistor",
    ],
}

# How the kinds are named to a person. The endpoint's vocabulary is mosfet / diode / bridge.
_LABEL = {"bridge": "bridge rectifier", "diode": "diode", "mosfet": "MOSFET"}


def _page_text(pdf_bytes: bytes, pages: int = _PAGES) -> str:
    try:
        import fitz
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        n = min(pages, doc.page_count)
        return " ".join(" ".join(doc[i].get_text().split()) for i in range(n))
    except Exception:
        return ""


def identify(pdf_bytes: bytes) -> dict:
    """What the document calls itself, with the phrase that says so.

    Returns every kind that matched, not just a winner: a caller deciding whether to REFUSE needs
    to know that the declared kind was among the matches, which a single verdict cannot express.
    """
    text = _page_text(pdf_bytes)
    low = text.lower()
    hits: dict[str, list[str]] = {}
    for kind, pats in _PATTERNS.items():
        found = []
        for p in pats:
            for m in re.finditer(p, low):
                # The matched phrase in the document's own casing, for the message.
                found.append(text[m.start():m.end()])
        if found:
            hits[kind] = found
    return {
        "kinds": sorted(hits),
        "hits": {k: v[:4] for k, v in hits.items()},
        "counts": {k: len(v) for k, v in hits.items()},
        "has_text": bool(low.strip()),
    }


def check_declared(pdf_bytes: bytes, declared_kind: str) -> dict:
    """Compare the document against the slot it was uploaded into.

    Three verdicts, because two would force a refusal on silence:

      * ``confirms``    — the declared kind is named in the document.
      * ``no_evidence`` — nothing decisive found (a scanned datasheet, or an unusual wording).
                          Proceed; say so on the review screen.
      * ``contradicts`` — the declared kind is named NOWHERE and another kind is named. This is
                          the mis-upload, and it is the only verdict that refuses.
    """
    ident = identify(pdf_bytes)
    kinds = ident["kinds"]
    declared = (declared_kind or "").strip().lower()

    if declared in kinds:
        return {**ident, "verdict": "confirms", "declared": declared, "message": ""}

    if not kinds:
        return {**ident, "verdict": "no_evidence", "declared": declared,
                "message": ("This datasheet does not name its device type in the first "
                            f"{_PAGES} pages, so it could not be checked against the "
                            f"{_LABEL.get(declared, declared)} slot. It was accepted as uploaded — "
                            "confirm it is the right part before relying on the result.")}

    # Contradiction. Name what the document says, what was expected, and what to do about it -
    # a refusal that does not say how to proceed just moves the dead end.
    said = ", ".join(_LABEL.get(k, k) for k in kinds)
    quoted = "; ".join(f'"{p}"' for p in (ident["hits"].get(kinds[0]) or [])[:2])
    return {
        **ident, "verdict": "contradicts", "declared": declared,
        "message": (
            f"This datasheet describes a {said}, but it was uploaded under "
            f"{_LABEL.get(declared, declared)}. The document says {quoted}. "
            f"Nothing has been stored. **Upload the {_LABEL.get(declared, declared)} datasheet "
            f"for this part**, or use the {said} tab if this is the file you meant.")}


def is_refused(check: Optional[dict]) -> bool:
    return bool(check) and check.get("verdict") == "contradicts"
