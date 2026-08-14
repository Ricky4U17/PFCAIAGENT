"""Session-wide memoisation of the two expensive reads in the datasheet suite.

WHY THIS EXISTS. `datasheet_extract.extract` re-reads a 17-page PDF and costs ~40 s. The suite
calls it about 34 times, nearly always on the SAME handful of files, which was roughly 23 of the
51 minutes the whole suite took. `curve_extract.digitise` is the same shape at ~2.5 s a call.
Neither is what those tests are checking — they are the fixed cost of getting to the thing under
test — so the result is computed once per distinct input and reused.

WHY IT IS SAFE, AND THE ONE RULE THAT MAKES IT SO. Both functions are pure: same bytes in, same
result out, no I/O beyond reading the bytes they were handed and no dependence on the parts store.
Nothing in the suite monkeypatches either of them, so no test can be served a result computed
before a patch it was relying on.

**EVERY HIT RETURNS A DEEP COPY, AND THAT IS NOT OPTIONAL.** Both results are mutated downstream by
ordinary production code: `flow.upload` writes `part_number` into the profile it was handed and
appends a `device_class` parameter to it, and `flow.figure_proposals` writes `T_j` onto the curve
dicts of the figure it was given. Handing out the cached object itself would let one test's
mutations arrive inside the next test's "freshly extracted" profile — a cross-test leak that would
look like a real defect in whichever test happened to run second. The copy costs milliseconds
against a 40-second call.

A template argument bypasses the cache entirely rather than being folded into the key: it is a
dict, it is rare in the suite, and hashing it reliably is more work than the call it would save.

If a test ever needs a genuinely cold read, call the originals stashed on this fixture rather than
disabling it globally.
"""
import copy
import hashlib

import pytest


@pytest.fixture(scope="session", autouse=True)
def cache_expensive_datasheet_reads():
    from app.mode_b.semiconductor import curve_extract as CX
    from app.mode_b.semiconductor import datasheet_extract as DX

    real_extract, real_digitise = DX.extract, CX.digitise
    store: dict = {}
    stats = {"extract_hit": 0, "extract_miss": 0, "digitise_hit": 0, "digitise_miss": 0}

    def _digest(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    def extract(pdf_bytes, device_class, template=None, variant=None):
        if template is not None:
            return real_extract(pdf_bytes, device_class, template, variant)
        key = ("extract", _digest(pdf_bytes), device_class, variant)
        if key in store:
            stats["extract_hit"] += 1
        else:
            stats["extract_miss"] += 1
            store[key] = real_extract(pdf_bytes, device_class, None, variant)
        return copy.deepcopy(store[key])

    def digitise(pdf_bytes, page_no=None):
        key = ("digitise", _digest(pdf_bytes), page_no)
        if key in store:
            stats["digitise_hit"] += 1
        else:
            stats["digitise_miss"] += 1
            store[key] = real_digitise(pdf_bytes, page_no)
        return copy.deepcopy(store[key])

    DX.extract, CX.digitise = extract, digitise
    try:
        yield {"real_extract": real_extract, "real_digitise": real_digitise, "stats": stats}
    finally:
        DX.extract, CX.digitise = real_extract, real_digitise
