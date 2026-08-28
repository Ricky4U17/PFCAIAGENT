"""SCREEN 2 SHOWS WHAT THE DESIGNER IS SPECIFYING, AND ITS DEFAULTS MUST BE SELECTABLE.

C269, from two designer findings on the Control Design screens.

FINDING 1 - C_ILIMIT2 offered 100 pF where the engine says 91 nF. 100 pF is the FIRST entry in
`options_pf`, and that is the tell: a browser renders a `<select>` whose `value` matches no
`<option>` by displaying the first one, while React state still holds the unmatched value. So the
screen and the state disagreed, which is why picking 100 nF by hand "fixed" the pole - the designer
was not correcting a bad calculation, they were giving the select a value it could match.

Two ways in, both closed here:
  * the ENGINE default itself is not on the offered grid  -> asserted below
  * a REHYDRATED selection (`step16_params.s2`) is stale, zero or absent -> `ComponentsSelect` now
    reconciles it against the offered options instead of applying defaults only when there was no
    stored selection at all

C268 made this urgent: R_ILIMIT2 moved 4.87k -> 3.65k, so every selection persisted before it is
attached to a different resistor and its pole has moved. This is C242's failure through a new door,
which is why the invariant is asserted rather than the one value that was wrong.

FINDING 2 - R_ILIMIT and R_ILIMIT2 appeared nowhere on the Control Design screens. They were
computed, handed over as `r_assoc_ohm` for the two filter caps, drawn on the schematic and printed
in the report - but never listed, so the designer could not see two of the resistors they were
specifying. Both scale with R_RI, so both moved at C268 and no screen said so.
"""
from __future__ import annotations

import pytest

from app.main import _ComponentsReq, control_components

INPUTS = {"vout": 394.0, "fsw": 70000.0, "lphi_uH": 101.6, "nch": 2}


@pytest.fixture(scope="module")
def screen2():
    return control_components(_ComponentsReq(inputs=INPUTS))


def test_every_offered_default_is_one_of_the_offered_options(screen2):
    """If a default is off-grid the select cannot match it and silently shows its first entry."""
    first = screen2["selectable"][0]["options_pf"][0]
    offenders = []
    for x in screen2["selectable"]:
        if x["default_pf"] not in x["options_pf"]:
            offenders.append(f"{x['key']}: default {x['default_pf']} pF is not in options_pf")
    assert not offenders, (
        "these selects have no matching option, so the GUI will display "
        f"{first} pF while state holds something else:\n  " + "\n  ".join(offenders))


def test_the_defaults_are_not_all_the_first_option(screen2):
    """A negative control. If everything collapsed to the first option this file would pass
    vacuously while the screen was completely wrong."""
    first = screen2["selectable"][0]["options_pf"][0]
    defaults = [x["default_pf"] for x in screen2["selectable"]]
    assert any(d != first for d in defaults), \
        f"every default equals the first option ({first} pF) - the engine is not being read"


def test_c_ilimit2_default_matches_its_own_pin_pole(screen2):
    """The value the designer reported. C_ILIMIT2 sits across R_ILIMIT2; its pole must be the
    ILIMIT pin-filter pole, not a placeholder that happens to be offerable."""
    import math
    c2 = next(x for x in screen2["selectable"] if x["key"] == "c_ilimit2")
    c1 = next(x for x in screen2["selectable"] if x["key"] == "c_ilimit")
    pole2 = 1.0 / (2 * math.pi * c2["r_assoc_ohm"] * c2["default_pf"] * 1e-12)
    pole1 = 1.0 / (2 * math.pi * c1["r_assoc_ohm"] * c1["default_pf"] * 1e-12)
    assert c2["default_pf"] > 1000, (
        f"C_ILIMIT2 default is {c2['default_pf']} pF — a sub-nF value here is the 100 pF "
        "first-option fallback, not a computed capacitor")
    assert pole2 == pytest.approx(pole1, rel=0.15), (
        f"C_ILIMIT2 pole {pole2:.0f} Hz and C_ILIMIT pole {pole1:.0f} Hz come from the same pin "
        "filter setting and should agree to within E24 snapping")


@pytest.mark.parametrize("symbol", ["R_RI", "R_ILIMIT", "R_ILIMIT2", "R_GC", "R_RLPK"])
def test_the_screens_show_the_resistors_the_designer_is_specifying(screen2, symbol):
    """R_ILIMIT/R_ILIMIT2 were missing entirely (C269). Screen 3 renders `fixed` + the Screen-2
    selections, so listing them here covers both screens."""
    syms = [f["symbol"] for f in screen2["fixed"]]
    assert symbol in syms, f"{symbol} is not shown on Screen 2/3; present: {syms}"


def test_a_sub_10k_resistor_keeps_its_e96_third_digit(screen2):
    """C269: one decimal printed the E96 3.65 kOhm R_ILIMIT2 as "3.6 kOhm" - a different, real,
    orderable part. Build from that display and you fit the wrong resistor."""
    row = next(f for f in screen2["fixed"] if f["symbol"] == "R_ILIMIT2")
    assert row["value"].startswith("3.65"), \
        f"R_ILIMIT2 displays as {row['value']!r}, losing the third significant figure"
