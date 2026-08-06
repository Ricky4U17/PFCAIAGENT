"""
datasheet_extract.py — read a component datasheet PDF into canonical parameter entries (M2).
============================================================================================
Phase 1: TEXT AND TABLES ONLY. Curves are phase 2 (M7) and this module does not guess at them.

The old `datasheet.py` regex extractor is still in place for the legacy upload path; this replaces
it for the datasheet-first flow, and differs in three ways that matter:

  * It reads TABLES, not a flattened text blob, so a value arrives with its conditions attached.
    `R_DS(on) = 33 mOhm` is not a fact; `R_DS(on) = 33 mOhm at V_GS 18 V, T_j 25 degC` is.
  * It writes CANONICAL keys from the registry, so no name is invented on the way in.
  * It never fabricates a curve from a scalar. A missing curve stays missing.

WHAT THE REAL FILE TAUGHT US. Every rule below was written against an actual vendor datasheet
(Comchip GBJ40L06), not imagined:

  1. FIGURE PAGES PRODUCE JUNK TABLES. Graph axes are drawn as rules, so `find_tables()` happily
     returns 20x21 grids of empty cells. Rejecting them structurally is not optional — without it
     the parser reports dozens of phantom parameters.
  2. ONE ROW CAN HOLD SEVERAL PARAMETERS. "RthJC RthJL RthJA | 5 9 24 | degC/W" is three
     parameters. Parsed naively it is one parameter called "RthJC RthJL RthJA" with the value
     "5 9 24".
  3. ONE ROW CAN HOLD SEVERAL CONDITIONS. "IF(AV) | 40 5 | A" is the rating with and without a
     heatsink. Taking the first number silently discards the other operating point.
  4. COLUMN SETS DIFFER BETWEEN TABLES IN ONE DOCUMENT. Page 2 has
     Characteristic|Symbol|Value|Unit; the next table has
     Characteristic|Test Conditions|Symbol|Min|Typ|Max|Unit. Roles must be matched by header text,
     never by position.
  5. LOOK-ALIKE CODEPOINTS. The file carries U+2103 (single-glyph degC) where the eye sees "degC",
     and the micro sign U+00B5 where a typed mu would be U+03BC. They render identically and
     compare unequal. NFKC normalisation first, always.
"""
from __future__ import annotations

import hashlib
import io
import re
import unicodedata
from typing import Any, Optional

from app.mode_b.semiconductor import registry as R

# ── text normalisation ────────────────────────────────────────────────────────────────────────
_DASHES = "‐‑‒–—―−"      # hyphen variants through minus sign


def norm_text(s: Any) -> str:
    """NFKC, unify dashes, collapse whitespace. Run before ANY comparison.

    NFKC is what folds U+2103 into 'degC' and the micro sign into a Greek mu, so a unit read off
    the page compares equal to a unit typed into a template.
    """
    if s is None:
        return ""
    t = unicodedata.normalize("NFKC", str(s))
    t = t.replace(" ", " ")
    for d in _DASHES:
        t = t.replace(d, "-")
    return re.sub(r"\s+", " ", t).strip()


_NUM = re.compile(r"[-+]?\d+(?:[.,]\d+)?(?:[eE][-+]?\d+)?")


def parse_numbers(s: Any) -> list[float]:
    """Every number in a cell, in order. A lone dash means NOT SPECIFIED and yields nothing —
    reading it as zero would turn 'no minimum stated' into 'minimum is zero'."""
    t = norm_text(s)
    if not t or t in {"-", "--", "N/A", "n/a"}:
        return []
    out = []
    for m in _NUM.finditer(t):
        try:
            out.append(float(m.group(0).replace(",", ".")))
        except ValueError:
            pass
    return out


_SI_PREFIX = {"p": 1e-12, "n": 1e-9, "u": 1e-6, "μ": 1e-6, "m": 1e-3,
              "": 1.0, "k": 1e3, "K": 1e3, "M": 1e6, "G": 1e9}


def parse_unit(s: Any) -> tuple[Optional[str], float]:
    """A unit cell -> (base unit, SI scale). 'mOhm' -> ('ohm', 1e-3); 'A2s' -> ('A2s', 1.0)."""
    t = norm_text(s).replace("Ω", "ohm").replace("Ω", "ohm")
    t = t.replace("°C", "degC").replace("℃", "degC")
    if not t:
        return None, 1.0
    m = re.match(r"^([pnuμmkKMG]?)(ohm|V|A|F|C|J|s|H|S|W|degC|A2s|pF|nF)\b", t)
    if not m:
        return t, 1.0
    prefix, base = m.group(1), m.group(2)
    if base in ("pF", "nF"):                     # already-prefixed unit written as one token
        return "F", (1e-12 if base == "pF" else 1e-9)
    return base, _SI_PREFIX.get(prefix, 1.0)


_COND = re.compile(r"([A-Za-z][A-Za-z0-9_()θ°]*)\s*=\s*([-+]?[\d.,]+)\s*"
                   r"([pnuμmkKMG]?(?:ohm|V|A|F|C|J|s|H|S|W|degC|Hz)?)", re.U)


def parse_conditions(text: Any) -> dict[str, float]:
    """'V_GS = 18 V, T_j = 175 degC' -> {'V_GS': 18.0, 'T_j': 175.0}, values in SI.

    Conditions are what make a value selectable. Without them a multi-valued parameter collapses to
    whichever entry happened to be parsed first — the failure `manifest.select` raises on.
    """
    t = norm_text(text).replace("°C", "degC").replace("℃", "degC")
    out: dict[str, float] = {}
    for sym, num, unit in _COND.findall(t):
        try:
            val = float(num.replace(",", "."))
        except ValueError:
            continue
        base, scale = parse_unit(unit)
        key = _CONDITION_ALIASES.get(sym.upper().replace("(", "").replace(")", ""), sym)
        out[key] = val * (scale if base and base != "degC" else 1.0)
    return out


_CONDITION_ALIASES = {
    "VGS": "V_GS", "VDS": "V_DS", "VDD": "V_DS", "VR": "V_R", "VCC": "V_DS",
    "ID": "I_D", "IF": "I_F", "IR": "I_R", "IC": "I_C",
    "TJ": "T_j", "TC": "T_c", "TA": "T_amb", "TSTG": "T_stg",
    "RG": "R_g", "RGEXT": "R_g", "F": "f",
}


# ── triage (external spec B1) ─────────────────────────────────────────────────────────────────
def triage(pdf_bytes: bytes) -> dict:
    """Decide how this document must be read, and RECORD the decision. Never fall back silently —
    a scanned datasheet parsed as if it had a text layer yields nothing and looks like a part with
    no parameters."""
    import fitz
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    text_chars = 0
    vector_pages, raster_pages = [], []
    for i, pg in enumerate(doc):
        text_chars += len(pg.get_text().strip())
        if len(pg.get_drawings()) > 40:
            vector_pages.append(i + 1)
        if pg.get_images():
            raster_pages.append(i + 1)
    has_text = text_chars > 200 * doc.page_count / max(doc.page_count, 1)
    return {
        "pages": doc.page_count,
        "has_text_layer": bool(text_chars > 500),
        "text_chars": text_chars,
        "vector_figure_pages": vector_pages,
        "raster_figure_pages": raster_pages,
        "method": "template" if text_chars > 500 else "ocr_required",
        "readable": bool(text_chars > 500),
        "note": ("" if text_chars > 500 else
                 "No usable text layer — this is a scanned or image-only PDF. Phase 1 cannot read "
                 "it; supply a text PDF from the vendor."),
    }


# ── table discovery, with the junk filter the real file forced ────────────────────────────────
_ROLE_SYNONYMS = {
    "parameter":  ["characteristic", "characteristics", "parameter", "parameters", "description",
                   "symbol and description", "item"],
    "symbol":     ["symbol", "sym", "symbols"],
    "conditions": ["test condition", "test conditions", "conditions", "condition",
                   "note/ test condition", "note / test condition", "remarks"],
    "min":        ["min", "min.", "minimum"],
    "typ":        ["typ", "typ.", "typical"],
    "max":        ["max", "max.", "maximum"],
    "value":      ["value", "values", "rating", "ratings"],
    "unit":       ["unit", "units"],
}


def _role_of(header_cell: str) -> Optional[str]:
    h = norm_text(header_cell).lower().rstrip(".")
    if not h:
        return None
    for role, names in _ROLE_SYNONYMS.items():
        if h in names or any(h.startswith(n) for n in names):
            return role
    return None


def _is_parameter_table(rows: list[list]) -> tuple[bool, str]:
    """Reject the phantom tables that figure axes produce.

    A graph page yields grids like 20x21 with almost every cell empty and no header words. Without
    this filter the parser invents dozens of parameters out of chart gridlines.
    """
    if len(rows) < 2:
        return False, "fewer than two rows"
    cells = [c for r in rows for c in r]
    filled = sum(1 for c in cells if norm_text(c))
    if not cells or filled / len(cells) < 0.35:
        return False, f"only {filled}/{len(cells)} cells carry text — this is a figure, not a table"
    roles = {_role_of(c) for c in rows[0]}
    roles.discard(None)
    if not ({"symbol", "parameter"} & roles):
        return False, f"header has no parameter or symbol column (roles seen: {sorted(roles)})"
    return True, ""


def find_parameter_tables(pdf_bytes: bytes) -> list[dict]:
    """Every table that looks like a parameter table, with its column roles resolved by header
    text rather than by position — column sets legitimately differ between tables in one file."""
    import fitz
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    found = []
    for pno, pg in enumerate(doc, start=1):
        try:
            tables = pg.find_tables().tables
        except Exception:
            continue
        for t in tables:
            try:
                rows = t.extract()
            except Exception:
                continue
            ok, why = _is_parameter_table(rows)
            if not ok:
                found.append({"page": pno, "rejected": why, "rows": len(rows)})
                continue
            header = [norm_text(c) for c in rows[0]]
            roles = {}
            for idx, cell in enumerate(header):
                role = _role_of(cell)
                if role and role not in roles:
                    roles[role] = idx
            found.append({"page": pno, "header": header, "roles": roles,
                          "rows": [[norm_text(c) for c in r] for r in rows[1:]],
                          "bbox": [round(v, 1) for v in t.bbox]})
    return found


# ── row parsing ───────────────────────────────────────────────────────────────────────────────
_SYMBOL_TOKEN = re.compile(r"[A-Za-zθ][A-Za-z0-9θ()/_.\-]*")


def split_packed_row(symbol_cell: str, value_cell: str) -> list[tuple[str, float]]:
    """Unpack a row that carries several parameters at once.

    "RthJC RthJL RthJA" / "5 9 24" is three parameters, not one called
    "RthJC RthJL RthJA" with the value "5 9 24". Pairs them positionally, and only when the counts
    match — guessing an alignment would be worse than reporting nothing.
    """
    syms = _SYMBOL_TOKEN.findall(norm_text(symbol_cell))
    vals = parse_numbers(value_cell)
    if len(syms) > 1 and len(syms) == len(vals):
        return list(zip(syms, vals))
    if len(syms) == 1 and vals:
        return [(syms[0], vals[0])]
    return []


def parse_range(text: str) -> Optional[tuple[float, float]]:
    """'-40 to +150' -> (-40, 150). Operating ranges are stated this way, and taking the first
    number would report the minimum as the maximum."""
    t = norm_text(text)
    m = re.match(r"^\s*([-+]?[\d.]+)\s*(?:to|\.\.\.|~|-)\s*([-+]?[\d.]+)\s*$", t)
    if m:
        return float(m.group(1)), float(m.group(2))
    return None


def parse_table(table: dict, symbol_map: dict[str, str]) -> list[dict]:
    """One parsed table -> canonical entries. Anything unmapped is returned as `unresolved` rather
    than dropped, so a reviewer can see what the parser gave up on."""
    roles = table.get("roles") or {}
    entries: list[dict] = []
    if "symbol" not in roles and "parameter" not in roles:
        return entries

    def cell(row, role):
        i = roles.get(role)
        return row[i] if i is not None and i < len(row) else ""

    for row in table.get("rows", []):
        sym_cell = cell(row, "symbol") or ""
        name_cell = cell(row, "parameter") or ""
        unit_cell = cell(row, "unit") or ""
        cond_text = " ".join(norm_text(row[i]) for i in range(len(row))
                             if i not in roles.values() or roles.get("conditions") == i)
        base_unit, scale = parse_unit(unit_cell)

        # Value columns in preference order — a typ is the design number, a max is the sign-off
        # one. Pick the first column that actually CONTAINS A NUMBER, not the first that is
        # non-empty: a "—" in the typ column is truthy, and choosing it over a max column holding
        # the real value silently drops the parameter. Every "min/typ/max" datasheet has rows like
        # `VB | 600 | — | — | V`, so this is the common case, not an edge one.
        vcols = {r: cell(row, r) for r in ("min", "typ", "max", "value") if r in roles}
        primary = ""
        for r in ("value", "typ", "max", "min"):
            if parse_numbers(vcols.get(r, "")):
                primary = vcols[r]
                break
        pairs = split_packed_row(sym_cell, primary)
        if not pairs:
            if norm_text(sym_cell) or norm_text(name_cell):
                entries.append({"unresolved": True, "symbol": norm_text(sym_cell),
                                "name": norm_text(name_cell), "row": row})
            continue

        multi = len(pairs) > 1
        for sym, val in pairs:
            key = symbol_map.get(_symbol_lookup(sym))
            rec: dict[str, Any] = {
                "symbol": sym, "name": norm_text(name_cell),
                "unit_text": norm_text(unit_cell),
                "conditions": parse_conditions(cond_text),
                "condition_text": norm_text(cell(row, "conditions")),
            }
            if key:
                rec["key"] = key
            else:
                rec["unresolved"] = True

            if multi:
                rec["typ"] = val * scale
            else:
                for r in ("min", "typ", "max"):
                    nums = parse_numbers(vcols.get(r, ""))
                    if nums:
                        rec[r] = nums[0] * scale
                if "value" in vcols and not any(k in rec for k in ("min", "typ", "max")):
                    rng = parse_range(vcols["value"])
                    if rng:
                        rec["min"], rec["max"] = rng
                    else:
                        nums = parse_numbers(vcols["value"])
                        if len(nums) > 1:
                            # several values under one symbol = several conditions (the with/without
                            # heatsink case). Keep them all; discarding one loses an operating point.
                            rec["values"] = [n * scale for n in nums]
                            rec["typ"] = nums[0] * scale
                        elif nums:
                            rec["typ"] = nums[0] * scale
            if base_unit:
                rec["si_unit"] = base_unit
            entries.append(rec)
    return entries


def _symbol_lookup(sym: str) -> str:
    """Normalise a datasheet symbol for map lookup: case, spaces, punctuation and the theta glyph
    all vary between vendors and even between tables in one file."""
    t = norm_text(sym).lower()
    t = t.replace("θ", "th").replace("(", "").replace(")", "")
    return re.sub(r"[\s._\-/]", "", t)


# ── cross-check (external spec B9) ────────────────────────────────────────────────────────────
def cross_check(entries: list[dict]) -> list[dict]:
    """Most datasheets repeat headline figures in a summary block AND in the detail tables. Where
    both exist, compare them: disagreement means one extraction is wrong. Free validation."""
    by_key: dict[str, list[dict]] = {}
    for e in entries:
        if e.get("key") and not e.get("unresolved"):
            by_key.setdefault(e["key"], []).append(e)
    findings = []
    for key, group in by_key.items():
        if len(group) < 2:
            continue
        for field in ("typ", "max", "min"):
            vals = [g[field] for g in group if isinstance(g.get(field), (int, float))
                    and not g.get("conditions")]
            if len(vals) > 1 and max(vals) - min(vals) > 1e-9 * max(1.0, abs(max(vals))):
                spread = (max(vals) - min(vals)) / max(abs(max(vals)), 1e-12) * 100
                if spread > 1.0:
                    findings.append({
                        "key": key, "field": field, "values": vals,
                        "spread_pct": round(spread, 1),
                        "message": f"{key} {field} appears more than once with different values "
                                   f"{vals}; one of the extractions is wrong."})
    return findings


# ── the entry point ───────────────────────────────────────────────────────────────────────────
def extract(pdf_bytes: bytes, device_class: str, template: Optional[dict] = None) -> dict:
    """Read a datasheet into a draft profile. Returns the profile plus everything a reviewer needs
    to judge it: the triage decision, what was rejected, what could not be mapped, and the
    cross-check result.

    NOTHING here is trusted. The output is a proposal for the confirmation screen (M3).
    """
    from app.mode_b.semiconductor import vendor_templates as VT

    tri = triage(pdf_bytes)
    profile = {
        "schema_version": R.load()["schema_version"],
        "device_class": device_class,
        "datasheet": {"sha256": hashlib.sha256(pdf_bytes).hexdigest(),
                      "bytes": len(pdf_bytes)},
        "extraction": {"method": tri["method"], "phase": "tables_only",
                       "vendor_template": None},
        "parameters": [], "curves": [], "unresolved": [],
    }
    if not tri["readable"]:
        profile["extraction"]["failed"] = tri["note"]
        return {"profile": profile, "triage": tri, "tables": [], "rejected": [],
                "cross_check": [], "ok": False, "reason": tri["note"]}

    tmpl = template or VT.match(pdf_bytes)
    profile["extraction"]["vendor_template"] = tmpl.get("template_id")
    symbol_map = {_symbol_lookup(k): v for k, v in (tmpl.get("symbol_map") or {}).items()}

    tables = find_parameter_tables(pdf_bytes)
    rejected = [t for t in tables if t.get("rejected")]
    good = [t for t in tables if not t.get("rejected")]

    flat: list[dict] = []
    for t in good:
        for e in parse_table(t, symbol_map):
            e["source"] = {"page": t["page"], "bbox": t.get("bbox")}
            flat.append(e)

    resolved = [e for e in flat if e.get("key")]
    profile["unresolved"] = [e for e in flat if not e.get("key")]

    # group by canonical key -> one parameter with several condition-qualified entries
    grouped: dict[str, dict] = {}
    for e in resolved:
        p = grouped.setdefault(e["key"], {"key": e["key"], "entries": []})
        entry = {k: v for k, v in e.items()
                 if k in ("min", "typ", "max", "values", "conditions", "condition_text",
                          "symbol", "source", "si_unit")}
        entry["provenance"] = "extracted"
        p["entries"].append(entry)
    profile["parameters"] = list(grouped.values())

    checks = cross_check(resolved)
    return {"profile": profile, "triage": tri, "tables": good, "rejected": rejected,
            "cross_check": checks, "ok": bool(profile["parameters"]),
            "reason": "" if profile["parameters"] else
                      "no parameters could be mapped to canonical keys — the vendor template may "
                      "not cover this layout"}
