"""The Design Explorer page must stay a viewer.

`specs/Improvements/ANIMATION_PLAN.md` constraints C-2, C-8 and C-11: the page is additive and
one-way, it recomputes no physics, and it cannot alter any previously calculated value. Those are
easy to hold on day one and easy to lose later — the natural way to add a feature to an animation
is to derive one more quantity in the browser, and the natural way to make it interactive is to let
it write something back.

Both failures would be invisible: the page would still render, the numbers would still look right,
and it would quietly become a second source of truth sitting beside the report. That is C255 — the
standalone Chapter 7 running on a flat inductance because a second path fed the engine different
inputs — and the whole reason the design-state export exists.

WHY A PYTHON TEST FOR A REACT PAGE. Same as `test_no_duplicate_frontend_assets` and
`test_downloads_go_through_helper`: it is where the suite is, it costs milliseconds, and the
property is textual.
"""
import pathlib
import re

import pytest

_FE = pathlib.Path(__file__).resolve().parents[2] / "frontend" / "src"
# EVERY explorer file, not just the page. The scene renderers are where a stray Math.sin or a
# ripple rebuilt from a scalar L would actually land — guarding only the shell while the drawing
# code sits in another file would protect nothing.
_FILES = ("DesignExplorer.tsx", "DesignExplorerScenes.tsx")


def _paths():
    found = [_FE / "components" / f for f in _FILES if (_FE / "components" / f).is_file()]
    if not found:
        pytest.skip("no DesignExplorer files present")
    return found


def _src():
    return chr(10).join(p.read_text(encoding="utf-8") for p in _paths())


def _code():
    """Source with comments stripped.

    The prose in this file legitimately discusses `fetch`, `Math.sin` and the other patterns these
    guards look for — the first version flagged the phrase "live fetch (C-7)" in a comment. A
    scanner that cannot tell code from commentary produces false positives, and a guard that cries
    wolf gets suppressed, which is how the stale page-count check nearly cost a real regression.
    """
    src = _src()
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)          # block comments, incl. the header
    src = re.sub(r"(?m)^\s*//.*$", "", src)                   # whole-line comments
    src = re.sub(r"\s//(?!\S).*$", "", src, flags=re.M)       # trailing comments
    return src


def test_the_page_reads_the_export_and_calls_nothing_else():
    """C-8. One endpoint, and it is the read-only projection.

    Any other backend call means the page is either recomputing something or triggering work, and
    both put a second source of truth next to the report.
    """
    src = _code()
    called = set(re.findall(r"\b(?:await\s+)?([a-zA-Z_][\w]*)\s*\(\s*\{", src))
    api_imports = set()
    for m in re.finditer(r"import\s*\{([^}]*)\}\s*from\s*'\.\./api/client'", src):
        api_imports |= {s.strip().replace("type ", "") for s in m.group(1).split(",") if s.strip()}
    # only the names that are actually API functions, not the types
    fns = {n for n in api_imports if n and n[0].islower()}
    # The allowlist is the READ-ONLY design-state family, and it is short on purpose. Adding to it
    # must be a deliberate edit here with a reason — which is how `designStateWaveforms` arrived at
    # C258: a second endpoint, but still a pure read, and separate only because it calls the engine
    # while the projection may not. Anything that triggers work, selects a part, or persists
    # something does not belong on this page at all.
    allowed = {"designState", "designStateWaveforms"}
    assert fns <= allowed, (
        f"DesignExplorer imports API functions outside the read-only family: {sorted(fns - allowed)}. "
        "The page may only read design state (C-8, C-11).")
    assert "designState" in called or "designState(" in src, "the page never fetches the export"
    assert fns >= {"designState"}, "the page must fetch the design-state export"


def test_the_page_does_not_recompute_physics():
    """C-8, the specific shapes that would reintroduce C255.

    The reference package we reviewed recomputes duty as `1 - vin/vbus` and ripple as
    `vin*d/(L*fsw)` from a single scalar L. On our design that is a flat inductance where the
    report has a 134-154 uH bias curve, and it has no DCM concept while Chapter 7 reports 6 % DCM
    at high line. If a value is missing, it belongs in the export, not in the browser.
    """
    src = _code()
    offenders = []
    # duty derived from a voltage ratio
    if re.search(r"1\s*-\s*\w*[Vv]in\w*\s*/\s*\w*(?:[Vv]bus|[Vv]out)", src):
        offenders.append("duty derived as 1 - vin/vbus")
    # ripple derived from L and fsw
    if re.search(r"/\s*\(\s*\w*L\w*\s*\*\s*\w*fsw", src, re.I):
        offenders.append("ripple derived as v*d/(L*fsw)")
    # trig used to synthesise a waveform rather than plot supplied samples
    if re.search(r"Math\.(sin|cos)\s*\(", src):
        offenders.append("Math.sin/cos — waveforms must come from engine arrays, not be synthesised")
    assert not offenders, (
        "DesignExplorer recomputes physics in the browser: " + "; ".join(offenders)
        + ". Add the quantity to the design-state export instead (ANIMATION_PLAN C-8).")


def test_the_page_cannot_write_anything_back():
    """C-2 and C-11: additive and one-way.

    The page receives approved objects as props. If it ever mutated one, the pages behind it would
    change underneath the designer with nothing to show for it.
    """
    src = _code()
    bad = []
    for pat, why in (
        (r"\bfetch\s*\(", "raw fetch — go through the api client"),
        (r"method:\s*['\"](?:PUT|PATCH|DELETE)['\"]", "a mutating HTTP method"),
        (r"\bon(?:Approve|Confirm|Save|Commit|Apply)\b", "an approve/save callback"),
        (r"\bapproved[A-Za-z]*\s*\.\w+\s*=", "assignment into an approved object"),
        (r"\bapproved[A-Za-z]*\[[^\]]+\]\s*=(?!=)", "index assignment into an approved object"),
    ):
        if re.search(pat, src):
            bad.append(why)
    assert not bad, (
        "DesignExplorer can write back or mutate approved state: " + "; ".join(bad)
        + ". The page is read-only in both directions (C-2, C-11).")


def test_the_page_uses_our_tokens_not_a_second_palette():
    """C-3: uniformity with the rest of the GUI.

    The reference package ships its own orange-accent palette and IBM Plex from a CDN. Hard-coded
    hex here would mean the explorer slowly drifts into looking like a different product, and a CDN
    font silently degrades offline.
    """
    src = _src()
    assert re.search(r"import\s*\{[^}]*\bC\b[^}]*\}\s*from\s*'\./ui'", src), \
        "the page does not import the shared token set from ui.tsx"
    # a stray hex colour is the tell; the tokens live in ui.tsx
    hexes = [h for h in re.findall(r"#[0-9a-fA-F]{3,8}\b", src)]
    assert not hexes, f"hard-coded colours in DesignExplorer: {sorted(set(hexes))} — use C.* from ui.tsx"
    assert "fonts.googleapis" not in src and "cdn" not in src.lower(), \
        "no external font/CDN reference — the GUI must work offline"


def test_the_gate_is_honoured_before_anything_is_drawn():
    """C-12. The export reports readiness; the page must act on it.

    Showing a partial animation would be worse than showing nothing: an absent chapter renders as
    an empty panel, and an empty panel reads as 'designed, and zero'.
    """
    src = _code()
    assert "readiness" in src and "blocked" in src, \
        "the page does not consult readiness.gate"
    assert re.search(r"gate\s*===\s*'blocked'", src), \
        "the page does not branch on readiness.gate === 'blocked' before rendering scenes"


def test_the_page_is_registered_after_the_input_filter():
    """The designer's placement: the explorer is the page after Input Filter, and it appears in the
    stepper so it is reachable rather than a hidden route."""
    stepper = (_FE / "components" / "Stepper.tsx").read_text(encoding="utf-8")
    ids = re.findall(r"\{id:'([\w]+)'", stepper)
    assert "explorer" in ids, "the Design Explorer is missing from the stepper"
    assert ids.index("explorer") == ids.index("inputfilter") + 1, (
        f"explorer must follow inputfilter in the stepper; order is {ids}")
