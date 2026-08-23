"""EVERY REPORT DOWNLOAD MUST GO THROUGH src/api/download.ts.

PENDING C2. Report downloads failed *intermittently*, on every screen, with no error banner and
no console exception. The cause was not in the fetch — it was after the PDF had already arrived,
in the save path, where two mistakes both fail completely silently:

    URL.revokeObjectURL(url)  fired 150 ms after a.click()   -> aborts the read of a large blob
    document.body.removeChild(a)  ran synchronously          -> Firefox needs the anchor to stay

Both were fixed by moving all seven screens onto `downloadBlob`, which holds the URL and the
anchor for ten minutes. The fix held. What did not hold was its EXCLUSIVITY: `downloadCh7` in
SemiconductorSelection.tsx was written later, open-coded the anchor dance again, and revoked the
URL on the very next statement — a worse version of the original bug, on the largest single-chapter
PDF the GUI produces. It sat there unnoticed because C2 was logged as "fixed, awaiting designer
confirmation" and nobody re-counted the call sites (C251).

That is the failure mode this file exists for. The helper being correct proves nothing if the next
download button does not call it, and a new button is exactly the moment the knowledge is missing.
The symptom is unreportable — the designer sees a spinner finish and no file — so it must be caught
here rather than in use.

WHY A PYTHON TEST FOR TYPESCRIPT. Same reason as test_no_duplicate_frontend_assets: it is where
the suite is, it costs milliseconds, and the property is textual.
"""
import pathlib
import re

import pytest

_COMPONENTS = pathlib.Path(__file__).resolve().parents[2] / "frontend" / "src" / "components"

# `createObjectURL` is legitimate for showing a blob on the page (an <img src>, an iframe). It is
# NOT legitimate for saving one, and these are the tells that a save is what is happening.
_SAVE_TELLS = (".download", "click()")

# Line-level opt-out for a genuine non-download use that trips the heuristic. Must state why.
_ALLOW = "download-ok:"


def _sources():
    if not _COMPONENTS.is_dir():
        pytest.skip("frontend/src/components not present")
    return sorted(_COMPONENTS.rglob("*.tsx"))


def _windows(text):
    """(line_no, snippet) around each createObjectURL call — the anchor dance is a few lines."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if "createObjectURL" in line:
            yield i + 1, "\n".join(lines[i:i + 6])


def test_no_screen_open_codes_a_download():
    offenders = []
    for path in _sources():
        text = path.read_text(encoding="utf-8", errors="replace")
        for line_no, window in _windows(text):
            if _ALLOW in window:
                continue
            if any(tell in window for tell in _SAVE_TELLS):
                offenders.append(f"{path.name}:{line_no}")
    assert not offenders, (
        "these save a blob without downloadBlob(), which is how reports vanished silently "
        f"(PENDING C2): {', '.join(offenders)}. Call downloadBlob(blob, name) from "
        "'../api/download' instead of building an <a> — it holds the object URL and the anchor "
        "for ten minutes, and returns the URL for a manual fallback link.")


def test_every_studio_iframe_allows_downloads():
    """PENDING C3, same silent class. A sandboxed iframe without `allow-downloads` has its exports
    blocked by the browser with no console error and no visible failure — the studio's CSV/PNG
    button simply does nothing.

    The entry named two offenders; there were three. `SimulationAgent.tsx` was written after C3 was
    logged and nobody re-counted — the identical mistake as C2's 8th download site, which is why
    this is a test and not a fixed list.
    """
    offenders = []
    for path in _sources():
        for m in re.finditer(r'sandbox="([^"]*)"', path.read_text(encoding="utf-8", errors="replace")):
            if "allow-downloads" not in m.group(1):
                offenders.append(f"{path.name}: sandbox={m.group(1)!r}")
    assert not offenders, (
        "these sandboxed iframes cannot download anything, silently: " + "; ".join(offenders)
        + ". Add allow-downloads unless the frame genuinely must never save a file.")


def test_the_helper_still_holds_the_url_and_the_anchor():
    """The guard above is only worth anything while downloadBlob itself is correct."""
    helper = _COMPONENTS.parent / "api" / "download.ts"
    if not helper.is_file():
        pytest.skip("download.ts not present")
    src = helper.read_text(encoding="utf-8", errors="replace")

    m = re.search(r"REVOKE_AFTER_MS\s*=\s*([^\n]+)", src)
    assert m, "REVOKE_AFTER_MS is gone from download.ts"
    ms = eval(m.group(1).split("//")[0].strip(), {"__builtins__": {}})  # e.g. `10 * 60 * 1000`
    assert ms >= 60_000, (
        f"the blob URL is revoked after {ms} ms; a 13 MB report can still be reading. The whole "
        "point of C2 was to make this generous — do not tighten it.")

    # revoke and remove must BOTH be deferred, not called straight after click()
    after_click = src.split("a.click()", 1)
    assert len(after_click) == 2, "download.ts no longer clicks an anchor — re-read this test"
    tail = after_click[1]
    assert "setTimeout" in tail.split("revokeObjectURL")[0], \
        "revokeObjectURL is no longer inside the deferred callback — this reintroduces C2"
    assert "a.remove()" in tail and tail.index("setTimeout") < tail.index("a.remove()"), \
        "the anchor is removed outside the deferred callback — Firefox needs it to stay"
