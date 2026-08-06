"""
manifest.py — required-field enforcement and provenance (M1).
=============================================================
The registry (M0) says what every quantity is CALLED. This module says whether the values a
calculation is about to use were actually supplied, and where each one came from.

WHY IT EXISTS. Every field of `Mosfet`, `Diode` and `Bridge` has a default. Omit one and the engine
does not complain — it substitutes. `rdson_25` defaults to 45 mOhm, `qgd` to 30 nC, `vg_drive` to
12 V. That is how a gate-drive voltage nobody chose reached a released report, and it is why
"no hardcoded parameters" cannot be a policy: it has to be a check that fails loudly and by name.

THREE CHECKS, in order of severity:

  DEFAULTED   a required quantity was not written at all, so the engine's built-in default fires.
              Reported with the field name AND the value that would be used, because "a default was
              used" is not actionable and "rdson_25 will be 0.045 ohm" is.
  DISCONNECT  a quantity written to some of its engine field aliases but not the others, or written
              inconsistently. Delegated to registry.audit_block.
  PROVENANCE  a value present with no record of where it came from. Not an error today (the vendor
              catalogue path predates this), but it is what the report's provenance table reads, so
              an untagged value is one the report cannot describe honestly.

ENFORCEMENT LEVEL IS THE CALLER'S. `validate_block` always returns findings; `strict=True` raises.
The gate belongs at GUI approval and report release, not inside the engine — the test suite and the
report harness legitimately compute without a datasheet, and a hard refusal in the engine would
make the tool untestable rather than more correct.
"""
from __future__ import annotations

import dataclasses as dc
from typing import Any, Optional

from app.mode_b.semiconductor import registry as R

PROVENANCE_KEY = "_provenance"          # canonical-key -> provenance value, carried on a block
SOURCE_KEY = "_source"                  # free text: which document the block came from


class MissingParameterError(ValueError):
    """A required parameter was absent when the caller demanded strictness. Names every offender —
    a failure that does not say which field is barely better than the silent default it replaced."""


# ── engine defaults ───────────────────────────────────────────────────────────────────────────
def _engine_dataclass(device_class: str):
    """The dataclass this device class maps onto. The mapping lives in the registry, not here."""
    name = R.device_class(device_class).get("engine_dataclass")
    if not name:
        return None
    from app.mode_b.semiconductor import pfc_loss_model as engine
    return getattr(engine, name)


def engine_defaults(device_class: str) -> dict[str, Any]:
    """Field -> the value the engine would silently use if the field is not supplied."""
    cls = _engine_dataclass(device_class)
    if cls is None:
        return {}
    out = {}
    for f in dc.fields(cls):
        if f.default is not dc.MISSING:
            out[f.name] = f.default
        elif f.default_factory is not dc.MISSING:      # type: ignore[attr-defined]
            out[f.name] = f.default_factory()          # type: ignore[attr-defined]
    return out


# ── the check ─────────────────────────────────────────────────────────────────────────────────
def validate_block(block: dict, device_class: str, consumer: str = "loss_engine",
                   strict: bool = False, require_provenance: bool = False) -> dict:
    """Check one engine block before it is used.

    Returns {"ok", "device_class", "defaulted", "disconnects", "untagged", "provenance", "summary"}.
    `ok` means nothing required is missing and no alias is half-written — it does NOT mean the
    values are right; that is the plausibility gate's question and the designer's.
    """
    block = dict(block or {})
    prov = dict(block.get(PROVENANCE_KEY) or {})
    defaults = engine_defaults(device_class)

    defaulted, untagged = [], []
    for key in R.required_keys(device_class, consumer):
        p = R.get(key)
        fields = p.get("engine_fields", [])
        if not fields:
            continue                                   # consumed elsewhere (requirement/thermal)
        written = [f for f in fields if block.get(f) not in (None, "", [])]
        if not written:
            defaulted.append({
                "key": key, "engine_fields": fields,
                "report_label": p.get("report_label", key),
                "source": p["source"],
                "would_use": {f: defaults.get(f) for f in fields},
                "message": (f"{key} was not supplied; the engine default would be used for "
                            f"{', '.join(f'{f}={defaults.get(f)!r}' for f in fields)}."),
            })
        elif key not in prov:
            untagged.append({"key": key, "engine_fields": fields,
                             "message": f"{key} has a value but no provenance record."})

    disconnects = R.audit_block(block)

    ok = not defaulted and not disconnects and (not require_provenance or not untagged)
    result = {
        "ok": ok, "device_class": device_class, "consumer": consumer,
        "defaulted": defaulted, "disconnects": disconnects, "untagged": untagged,
        "provenance": prov, "source": block.get(SOURCE_KEY),
        "summary": _summarise(prov, defaulted, disconnects, untagged),
    }
    if strict and not ok:
        raise MissingParameterError(_strict_message(result))
    return result


def _summarise(prov, defaulted, disconnects, untagged) -> dict:
    counts: dict[str, int] = {}
    for v in prov.values():
        counts[v] = counts.get(v, 0) + 1
    return {"by_provenance": counts, "defaulted": len(defaulted),
            "disconnects": len(disconnects), "untagged": len(untagged)}


def _strict_message(res: dict) -> str:
    lines = [f"{res['device_class']}: cannot calculate from this block."]
    for d in res["defaulted"]:
        lines.append(f"  MISSING   {d['message']}")
    for d in res["disconnects"]:
        lines.append(f"  DISCONNECT {d['message']}")
    for u in res["untagged"]:
        lines.append(f"  UNTAGGED  {u['message']}")
    return "\n".join(lines)


# ── provenance stamping ───────────────────────────────────────────────────────────────────────
def stamp(block: dict, provenance: dict[str, str], source: Optional[str] = None) -> dict:
    """Attach or extend a block's provenance record. Keys are CANONICAL, never engine field names —
    one name per quantity, per the registry's contract."""
    out = dict(block or {})
    allowed = set(R.load()["provenance_values"])
    cur = dict(out.get(PROVENANCE_KEY) or {})
    for key, val in provenance.items():
        if val not in allowed:
            raise ValueError(f"provenance {val!r} for {key!r} is not one of {sorted(allowed)}")
        R.get(key)                                     # unknown canonical key raises
        cur[key] = val
    out[PROVENANCE_KEY] = cur
    if source:
        out[SOURCE_KEY] = source
    return out


def provenance_rows(block: dict, device_class: str) -> list[dict]:
    """One row per canonical quantity the engine will consume, for the confirmation screen and the
    report: label, value in display units, provenance, and where it is used.

    The external spec's review-gate rule applies here — a bare number is not reviewable, a number
    with its conditions and its destination is.
    """
    prov = dict(block.get(PROVENANCE_KEY) or {})
    defaults = engine_defaults(device_class)
    rows = []
    for p in R.parameters(device_class):
        fields = p.get("engine_fields", [])
        if not fields or "loss_engine" not in p.get("consumed_by", []):
            continue
        raw = next((block[f] for f in fields if block.get(f) not in (None, "", [])), None)
        supplied = raw is not None
        val = raw if supplied else defaults.get(fields[0])
        display = None
        if isinstance(val, (int, float)) and p["si_unit"] not in ("text", "1"):
            n, unit = R.to_display(p["key"], float(val))
            display = f"{n:g} {unit}".strip()
        rows.append({
            "key": p["key"], "label": p.get("report_label", p["key"]),
            "value": val, "display": display,
            "supplied": supplied,
            "provenance": prov.get(p["key"], "extracted" if supplied else "default"),
            "source_kind": p["source"],
            "conditions": p.get("conditions", []),
            "required": bool(p.get("required")),
        })
    # Anything unsupplied or defaulted sorts to the top: a review screen that buries the problems
    # under forty confirmed values is the ceremony of verification without the substance.
    rows.sort(key=lambda r: (r["supplied"], not r["required"], r["key"]))
    return rows


# ── condition-aware value selection (external spec A8) ────────────────────────────────────────
def select(profile: dict, key: str, **conditions) -> dict:
    """Pick the entry of a multi-valued parameter that matches the caller's operating point.

        select(profile, "R_DS_on", V_GS=18, T_j=175)  -> {"typ": 0.054, ...}

    Scores by exact condition matches and breaks ties by fewest unmatched conditions. **Raises when
    nothing matches** rather than returning the first entry — asking for R_DS(on) at 175 degC and
    silently receiving the 25 degC value is the failure this prevents.
    """
    R.get(key)                                          # unknown canonical key raises
    entries = []
    for p in profile.get("parameters", []):
        if p.get("key") == key:
            entries = p.get("entries", [])
            break
    if not entries:
        raise MissingParameterError(
            f"profile {profile.get('part_number', '?')!r} has no entries for {key!r}")

    if not conditions:
        if len(entries) > 1:
            raise MissingParameterError(
                f"{key!r} has {len(entries)} entries; specify conditions "
                f"({', '.join(sorted({c for e in entries for c in (e.get('conditions') or {})}))}) "
                f"— returning an arbitrary one would be a guess")
        return entries[0]

    best, best_score = None, None
    for e in entries:
        ec = e.get("conditions") or {}
        matched = sum(1 for k, v in conditions.items()
                      if k in ec and _close(ec[k], v))
        conflicting = sum(1 for k, v in conditions.items()
                          if k in ec and not _close(ec[k], v))
        if conflicting:
            continue
        unmatched = len(conditions) - matched
        score = (matched, -unmatched)
        if best_score is None or score > best_score:
            best, best_score = e, score

    if best is None or best_score[0] == 0:
        want = ", ".join(f"{k}={v}" for k, v in sorted(conditions.items()))
        have = " | ".join(str(e.get("conditions")) for e in entries)
        raise MissingParameterError(
            f"no entry of {key!r} matches {want}. Available: {have}. "
            f"Falling back to another condition would silently change the operating point.")
    return best


def _close(a, b, rel: float = 1e-6) -> bool:
    try:
        a, b = float(a), float(b)
    except (TypeError, ValueError):
        return a == b
    return abs(a - b) <= rel * max(1.0, abs(a), abs(b))
