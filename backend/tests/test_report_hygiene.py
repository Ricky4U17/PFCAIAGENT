"""Two silent-drift guards found while auditing PENDING_ITEMS at C252.

Both defects share a shape: the build succeeds, the page count is right, nothing logs an error,
and the only symptom is a document or a console that quietly stops meaning what it says.
"""
import collections
import logging
import pathlib
import re

import pytest

_MB = pathlib.Path(__file__).resolve().parents[1] / "app" / "mode_b"


# ─────────────────────────────────────────────────────────────────────────────
# B10 — two tables, one number
# ─────────────────────────────────────────────────────────────────────────────
# Numbers that legitimately appear twice in one module: an if/else pair where only one branch can
# ever render. Every entry must be one of those, and the pairing must be checked before adding.
_KNOWN_IF_ELSE = {
    ("report_inputprotection.py", "9.6"),   # vendor-MOV screen vs catalog screen
    ("report_step11.py", "6.11.6"),         # Type-II vs Type-III compensator
    ("report_step11.py", "6.11.7"),
    ("report_step11.py", "6.11.9"),
}


def _duplicate_table_numbers():
    out = set()
    for path in sorted(_MB.rglob("*.py")):
        nums = re.findall(r"""data_table\(\s*story\s*,\s*["']([0-9][0-9.a-z]*)["']""",
                          path.read_text(encoding="utf-8", errors="replace"))
        for num, count in collections.Counter(nums).items():
            if count > 1:
                out.add((path.name, num))
    return out


def test_no_two_rendered_tables_share_a_number():
    """C252 fixed the one real case: §9.7 was both 'Recalculated Design Values' and 'Gate-by-Gate
    Verdict', and BOTH render, so the report contained two different Table 9.7. They are 9.7a/9.7b
    now. A reader who cites 'Table 9.7' in a review has no way to say which one they meant.

    Note the equation series is separate — `eq_box(..., number="9.7")` in the same section is not a
    clash and is deliberately left alone.
    """
    extra = _duplicate_table_numbers() - _KNOWN_IF_ELSE
    assert not extra, (
        "these table numbers are used twice in one module: "
        + ", ".join(f"{f} -> {n}" for f, n in sorted(extra))
        + ". If both branches can render, suffix them a/b. If it is an if/else pair where only one "
          "can render, add it to _KNOWN_IF_ELSE after checking that is actually true.")


def test_the_known_if_else_pairs_still_exist():
    """Guards the allowlist itself: once a pair is fixed or removed its entry must go, or the list
    silently grows into a place to hide new duplicates."""
    stale = _KNOWN_IF_ELSE - _duplicate_table_numbers()
    assert not stale, (
        f"_KNOWN_IF_ELSE lists pairs that no longer exist: {sorted(stale)} — remove them")


# ─────────────────────────────────────────────────────────────────────────────
# A9a — a load warning that is always wrong
# ─────────────────────────────────────────────────────────────────────────────
def test_the_material_database_validates_clean():
    """Every load logged `Missing required field: data_source` for 66 of 92 materials, and the
    field was present the whole time — powder files carry it at `basic.data_source` while the
    schema named only the top level. 8 powder files DO use the top level, so the schema now accepts
    either (`"data_source|basic.data_source"`) rather than 66 files being migrated.

    The reason this is worth a test rather than a shrug: a warning that is always wrong trains
    everyone to scroll past load warnings, and that is exactly where a real one would appear.
    Measured before the fix: 66 errors. After: 0.
    """
    logging.disable(logging.CRITICAL)
    try:
        from app.magnetics.db import get_db
        db = get_db()
        errors = db.validate_all()
    finally:
        logging.disable(logging.NOTSET)

    assert len(db._materials) > 50, f"only {len(db._materials)} materials loaded — fixture problem"
    assert errors == [], (
        f"{len(errors)} material validation errors, expected none:\n  " + "\n  ".join(errors[:12]))


def test_data_source_is_accepted_at_either_nesting():
    """The alternative-path mechanism itself, so a future schema tidy-up cannot quietly drop it."""
    from app.magnetics.db import get_db
    db = get_db()
    nested = {"type": "powder", "basic": {"data_source": "x"}}
    top = {"type": "powder", "data_source": "x"}
    for d, where in ((nested, "basic.data_source"), (top, "top-level data_source")):
        errs = [e for e in db.validate_material_dict(d) if "data_source" in e]
        assert not errs, f"data_source at {where} was reported missing: {errs}"
