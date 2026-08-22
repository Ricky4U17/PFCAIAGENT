"""AN ASSET THAT EXISTS TWICE WILL BE EDITED IN THE COPY NOBODY SERVES.

C244. C242 and C243 fixed the embedded control-design tool - the Screen-2 capacitor wiring, the
C_VIR literal, the Step-5 divider - and none of it reached the designer, because the repository
held TWO copies of the 200 KB file:

    frontend/public/control_design.html      <- served at /control_design.html, what the iframe loads
    frontend/src/assets/control_design.html  <- referenced by nothing at all

Both were tracked in git and byte-identical apart from line endings, so `grep` found the dead one
first and every edit went there. The GUI kept showing the old values through two rounds of "fixed",
and the only signal was the designer running it and saying so again.

`src/assets/control_design.html` is deleted; `public/` is the single copy. This asserts it stays
that way, because the failure is completely silent: the edit applies, the tests pass, the syntax
checks pass, and the browser loads a different file.

WHY A PYTHON TEST FOR A FRONTEND FILE. It is where the suite is, it costs nothing, and the check is
a filesystem property rather than anything JavaScript. `dist/` is a build artefact and gitignored,
so it is excluded - a stale copy there is expected and harmless.
"""
import pathlib

import pytest

_FRONTEND = pathlib.Path(__file__).resolve().parents[2] / "frontend"

# Assets the app loads by URL rather than by import. A second copy of any of these is invisible to
# the bundler, to the type checker and to every test - and to whoever edits the wrong one.
SERVED_ASSETS = ["control_design.html"]


def _copies(name):
    if not _FRONTEND.is_dir():
        pytest.skip("frontend/ not present")
    return sorted(p for p in _FRONTEND.rglob(name)
                  if "node_modules" not in p.parts and "dist" not in p.parts)


@pytest.mark.parametrize("name", SERVED_ASSETS)
def test_exactly_one_copy_of_each_url_loaded_asset(name):
    found = _copies(name)
    rel = [str(p.relative_to(_FRONTEND)) for p in found]
    assert len(found) == 1, (
        f"{name} exists {len(found)} times: {rel}. Only public/ is served, so an edit to any other "
        "copy silently does nothing — this is exactly how C242 and C243 failed to reach the GUI.")
    assert found[0].parent.name == "public", \
        f"{name} should live in frontend/public/ (served at /), found at {rel[0]}"


@pytest.mark.parametrize("name", SERVED_ASSETS)
def test_the_served_copy_carries_the_screen2_wiring(name):
    """A shape check, not a value check: the served file must be the one with the wiring in it.

    Guards the specific way C242/C243 went wrong - the fixes existed, in the wrong file.
    """
    found = _copies(name)
    if not found:
        pytest.skip(f"{name} not found")
    txt = found[0].read_text(encoding="utf-8", errors="replace")
    for probe, why in (("c_ilimit2_pf", "Screen-2 capacitor selections (C242)"),
                       ("aux_CVIR", "C_VIR as a real overridable value, not a literal (C242)"),
                       ("rfb1_Mohm", "Step-5 divider injection (C243)")):
        assert probe in txt, f"served {name} is missing {why}"
    assert "'0.1 µF (typ)'" not in txt, \
        "the hardcoded C_VIR label is back in the served copy"
