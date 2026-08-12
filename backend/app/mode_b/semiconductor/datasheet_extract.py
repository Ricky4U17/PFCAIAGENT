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


_COND = re.compile(r"([A-Za-z][A-Za-z0-9_()θ°]*(?:,[A-Za-z]+)?)\s*=\s*([-+]?[\d.,]+)\s*"
                   r"([pnuμmkKMG]?(?:ohm|V|A|F|C|J|s|H|S|W|degC|Hz)?)", re.U)


_SWING = re.compile(r"([A-Za-z][A-Za-z0-9_()]*)\s*=\s*([-+]?[\d.]+)\s*(?:to|/)\s*"
                    r"([-+]?[\d.]+)\s*([pnu\u03bcmkKMG]?[A-Za-z]*)", re.U)


def parse_swings(text: Any) -> dict[str, float]:
    """Conditions stated as a SWING rather than a level: "V_GS = 0 to 18 V", "V_GS = 0/18 V".

    Gate charge is quoted for a swing, and the swing is the thing that matters: Q_g = 34 nC over
    0-18 V is not 34 nC over 0-15 V. Read as a level the first number wins, which records the swing
    as 0 V and quietly loses the condition the value depends on.
    """
    t = norm_text(text).replace("\u00b0C", "degC").replace("\u2103", "degC")
    out: dict[str, float] = {}
    for sym, lo, hi, unit in _SWING.findall(t):
        try:
            lo_f, hi_f = float(lo), float(hi)
        except ValueError:
            continue
        base, scale = parse_unit(unit)
        key = _CONDITION_ALIASES.get(sym.upper().replace("(", "").replace(")", ""), sym)
        out[f"{key}_swing"] = (hi_f - lo_f) * (scale if base and base != "degC" else 1.0)
        out[f"{key}_high"] = hi_f * (scale if base and base != "degC" else 1.0)
    return out


def parse_conditions(text: Any) -> dict[str, float]:
    """'V_GS = 18 V, T_j = 175 degC' -> {'V_GS': 18.0, 'T_j': 175.0}, values in SI.

    Conditions are what make a value selectable. Without them a multi-valued parameter collapses to
    whichever entry happened to be parsed first — the failure `manifest.select` raises on.
    """
    t = norm_text(text).replace("°C", "degC").replace("℃", "degC")
    out: dict[str, float] = dict(parse_swings(t))
    # A swing is consumed first, so its two numbers are not then read as two separate
    # levels — "V_GS = 0 to 18 V" must not also record V_GS = 0.
    for _m in _SWING.finditer(t):
        t = t.replace(_m.group(0), " ")
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
    "RG": "R_g", "RGEXT": "R_g", "RG,EXT": "R_g", "RGON": "R_g_on", "RGOFF": "R_g_off",
    "F": "f", "IS": "I_S", "T": "T_c",
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


# ── subscript merging (external spec B6) ──────────────────────────────────────────────────────
# Two real datasheets disagree about how subscripts reach the text layer. The Diodes file
# concatenates them ("VRRM"); the Infineon file emits them as SEPARATE smaller spans, and the
# table extractor then appends them at the end of the cell — so "V_GS = 0 V, I_D = 0.57 mA" comes
# out as "V = 0 V, I = 0.57 mA G DS", which parses to the wrong condition keys and silently
# mis-labels the operating point. Merging them back is not cosmetic.
#
# Ratios rather than absolute point sizes, so the rule survives a document set at another size.
# Measured on the Infineon file: body 10.99 pt, subscript 7.01 pt -> ratio 0.638.
_SUB_RATIO = (0.45, 0.85)
_SUB_DY = (0.10, 0.85)      # downward shift, as a fraction of the base size
_SUP_DY = (-0.75, -0.05)    # upward: superscripts are footnote markers, not part of the symbol
_SUB_DX = (-0.60, 1.20)     # NEGATIVE lower bound: italic glyphs overhang leftward, so a
#                             subscript's x0 can precede the base span's x1. Using 0 here drops
#                             every subscript in an italic-symbol document.


def _median_font_size(page) -> float:
    sizes = []
    for b in page.get_text("dict")["blocks"]:
        for l in b.get("lines", []):
            for sp in l["spans"]:
                sizes.append(sp["size"])
    if not sizes:
        return 10.0
    sizes.sort()
    return sizes[len(sizes) // 2]        # MEDIAN, never max: a heading would classify body text
    #                                      as subscript and swallow the whole page.


def cell_lines(page, rect, median_size: float) -> list[str]:
    """The VISUAL LINES inside one table cell, with subscripts re-attached.

    Lines, not one blob, because a single bordered row routinely holds several entries. The
    reference part states four on-resistances in ONE row: typ cell "43 33 30 54", max cell
    "- 41 - -", and four condition sets stacked in the notes cell. Flattened, that is a parameter
    with the nonsensical value "43 33 30 54"; read line by line it is exactly the four
    condition-qualified entries `manifest.select()` needs.

    Superscripts are DROPPED: in these documents they are footnote markers, and leaving them in
    turns "I2t" into a symbol that matches nothing and "R_DS(on)4)" into a parse failure.
    """
    import fitz
    if rect is None:
        return ""
    clip = fitz.Rect(rect)
    spans = []
    for b in page.get_text("dict", clip=clip)["blocks"]:
        for l in b.get("lines", []):
            for sp in l["spans"]:
                t = sp["text"]
                if t.strip():
                    spans.append({"text": t, "size": sp["size"], "bbox": sp["bbox"]})
    if not spans:
        return []

    # Group into VISUAL lines by vertical overlap, not by the PDF's own line objects. A subscript
    # sits on its own line as far as the extractor is concerned, so trusting that structure leaves
    # every subscript stranded at the end of the cell — which is how "V_GS = 18 V" came out as
    # "V = 18 V GS" and parsed to the wrong condition key.
    spans.sort(key=lambda x: x["bbox"][1])
    lines: list[list[dict]] = []
    for sp in spans:
        placed = False
        for ln in lines:
            top = min(x["bbox"][1] for x in ln)
            bot = max(x["bbox"][3] for x in ln)
            overlap = min(bot, sp["bbox"][3]) - max(top, sp["bbox"][1])
            height = min(bot - top, sp["bbox"][3] - sp["bbox"][1])
            if height > 0 and overlap / height > 0.35:
                ln.append(sp)
                placed = True
                break
        if not placed:
            lines.append([sp])

    out_lines: list[str] = []
    for ln in lines:
        ln.sort(key=lambda x: x["bbox"][0])
        parts: list[str] = []
        for i, sp in enumerate(ln):
            ratio = sp["size"] / max(median_size, 1e-6)
            if _SUB_RATIO[0] <= ratio <= _SUB_RATIO[1] and i > 0 and parts:
                prev = ln[i - 1]
                dy = (sp["bbox"][3] - prev["bbox"][3]) / max(prev["size"], 1e-6)
                dx = (sp["bbox"][0] - prev["bbox"][2]) / max(prev["size"], 1e-6)
                if _SUP_DY[0] <= dy <= _SUP_DY[1]:
                    # A superscript is a FOOTNOTE MARKER only when it trails the line and is a
                    # bare number, e.g. "R_DS(on) 4)". Inside a symbol it is part of the name:
                    # dropping it turned I2t into "It", which matches nothing — and I2t is one of
                    # the two ratings the Chapter 8 surge gate has been missing all along.
                    is_marker = (i == len(ln) - 1
                                 and re.fullmatch(r"\d{1,2}\)?", sp["text"].strip()) is not None)
                    if is_marker:
                        continue
                    parts[-1] = parts[-1].rstrip() + sp["text"].strip()
                    continue
                if _SUB_DY[0] <= dy <= _SUB_DY[1] and _SUB_DX[0] <= dx <= _SUB_DX[1]:
                    parts[-1] = parts[-1].rstrip() + sp["text"].strip()   # attach, no space
                    continue
            parts.append(sp["text"])
        out_lines.append(norm_text("".join(parts)))
    return [l for l in out_lines if l]


def cell_text(page, rect, median_size: float) -> str:
    """The whole cell as one string — for headers and names, where lines are only wrapping."""
    return norm_text(" ".join(cell_lines(page, rect, median_size)))


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


def _header_row(rows: list[list], look: int = 3) -> int:
    """Index of the row that carries the column roles.

    Vendors put the section caption INSIDE the table — "MAXIMUM RATINGS (TA = 25 degC...)" spanning
    every column — so `find_tables` returns it as row 0 and the real header, "PARAMETER | SYMBOL |
    <part number> | UNIT", is row 1. Testing row 0 alone rejected every table in the LVE5060E
    datasheet: 12 of 12, with the reason "header has no parameter or symbol column", while the
    table underneath was perfectly ordinary.
    """
    for i, row in enumerate(rows[:look]):
        roles = {_role_of(c) for c in row}
        roles.discard(None)
        if {"symbol", "parameter"} & roles:
            return i
    return 0


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
    h = _header_row(rows)
    roles = {_role_of(c) for c in rows[h]}
    roles.discard(None)
    if not ({"symbol", "parameter"} & roles):
        return False, f"header has no parameter or symbol column (roles seen: {sorted(roles)})"
    return True, ""


def _merge_subheader(header: list[str], rows: list[list[str]]) -> tuple[list[str], list[list[str]]]:
    """Fold a second header row into the first.

    Infineon spans one "Values" header across three columns and puts "Min. | Typ. | Max." on the
    row beneath. Read as data, that row is noise; read as header, it is what tells min from max.
    Without this the parser looks only at the column "Values" sits over, which holds "-" on every
    row whose real number is in the max column — and the parameter disappears.
    """
    if not rows:
        return header, rows
    first = rows[0]
    labels = [_role_of(c) for c in first]
    named = [r for r in labels if r in ("min", "typ", "max")]
    if len(named) >= 2 and not any(parse_numbers(c) for c in first):
        merged = list(header)
        for idx, role in enumerate(labels):
            if role and idx < len(merged):
                merged[idx] = first[idx]
        return merged, rows[1:]
    return header, rows


def find_parameter_tables(pdf_bytes: bytes) -> list[dict]:
    """Every table that looks like a parameter table, with its column roles resolved by header
    text rather than by position — column sets legitimately differ between tables in one file.

    Cell text is rebuilt from span geometry rather than taken from `extract()`, so subscripts stay
    attached to their symbol and to their condition.
    """
    import fitz
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    found = []
    for pno, pg in enumerate(doc, start=1):
        try:
            tables = pg.find_tables().tables
        except Exception:
            continue
        med = _median_font_size(pg)
        for t in tables:
            try:
                raw = t.extract()
            except Exception:
                continue
            ok, why = _is_parameter_table(raw)
            if not ok:
                found.append({"page": pno, "rejected": why, "rows": len(raw)})
                continue
            try:
                lgrid = [[cell_lines(pg, c, med) for c in r.cells] for r in t.rows]
            except Exception:
                lgrid = [[[norm_text(c)] if norm_text(c) else [] for c in r] for r in raw]
            if not lgrid:
                continue
            grid = [[norm_text(" ".join(c)) for c in row] for row in lgrid]
            h = _header_row(grid)
            header, body = _merge_subheader(grid[h], grid[h + 1:])
            lbody = lgrid[len(lgrid) - len(body):]
            roles: dict[str, int] = {}
            for idx, cell in enumerate(header):
                role = _role_of(cell)
                if role and role not in roles:
                    roles[role] = idx
            # A VALUE COLUMN HEADED BY THE PART NUMBER. Vishay heads the single value column of a
            # maximum-ratings table with the device name — "PARAMETER | SYMBOL | LVE5060E | UNIT" —
            # so no value role is recognised and every row parses to nothing. Any unlabelled column
            # between the symbol and the unit is the value: it is the only thing it can be.
            if not ({"value", "typ", "max", "min"} & set(roles)):
                left = max((roles[r] for r in ("symbol", "parameter") if r in roles), default=-1)
                right = roles.get("unit", len(header))
                spare = [i for i in range(left + 1, right) if _role_of(header[i]) is None]
                if len(spare) == 1:
                    roles["value"] = spare[0]
            found.append({"page": pno, "header": header, "roles": roles, "rows": body,
                          "row_lines": lbody, "bbox": [round(v, 1) for v in t.bbox]})
    return found


# ── row parsing ───────────────────────────────────────────────────────────────────────────────
_SYMBOL_TOKEN = re.compile(r"[A-Za-zθ][A-Za-z0-9θ()/_.\-]*")


# A part number in a SERIES datasheet: letters, then digits, optionally a suffix letter. The
# space is optional because vendors set the column header as "SFAF 1601G" and the in-cell band as
# "SFAF1601G".
_VARIANT_TOKEN = re.compile(r"\b([A-Z]{2,6})\s?(\d{2,6}[A-Z]{0,3})\b")


def variant_tokens(text: Any) -> list[str]:
    """Part numbers named in a cell, normalised. Empty for ordinary text."""
    out = []
    for pre, num in _VARIANT_TOKEN.findall(norm_text(text).upper()):
        v = f"{pre}{num}"
        if v not in out:
            out.append(v)
    return out


def find_variants(pdf_bytes: bytes) -> list[str]:
    """The part numbers a SERIES datasheet covers, or [] for a single-part document.

    One document, several parts, and the parameters that differ between them are banded - either as
    a column per variant, or as a list of variants in a cell against each value. Reading such a file
    without knowing WHICH part is being used silently takes one band's numbers: the reference
    silicon file gave a forward voltage of 0.975 V for a part whose actual figure is 1.700 V, a 43 %
    understatement feeding straight into conduction loss.

    Detected by grouping the part-number-shaped tokens by their letter prefix and keeping the
    largest family with more than one member, so an isolated package code or standard number
    ("TO-220AC", "JESD 201") cannot be mistaken for a variant list.
    """
    seen: dict[str, set] = {}
    for t in find_parameter_tables(pdf_bytes):
        if t.get("rejected"):
            continue
        for cellrow in [t.get("header") or []] + list(t.get("rows") or []):
            for c in cellrow:
                for v in variant_tokens(c):
                    m = _VARIANT_TOKEN.match(v)
                    if m:
                        seen.setdefault(m.group(1), set()).add(v)
    if not seen:
        return []
    best = max(seen.values(), key=len)
    return sorted(best) if len(best) > 1 else []


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


def parse_table(table: dict, symbol_map: dict[str, str], name_map: Optional[dict] = None) -> list[dict]:
    """One parsed table -> canonical entries. Anything unmapped is returned as `unresolved` rather
    than dropped, so a reviewer can see what the parser gave up on."""
    roles = table.get("roles") or {}
    entries: list[dict] = []
    prev = None                      # the last row that produced an entry, for continuation rows
    if "symbol" not in roles and "parameter" not in roles:
        return entries

    def cell(row, role):
        i = roles.get(role)
        return row[i] if i is not None and i < len(row) else ""

    lrows = table.get("row_lines") or []
    for ridx, row in enumerate(table.get("rows", [])):
        lrow = lrows[ridx] if ridx < len(lrows) else None
        # A row whose value cells hold several lines is several entries. Expand it before parsing
        # so each entry keeps its own conditions; flattening loses the very thing that makes a
        # multi-valued parameter selectable.
        if lrow:
            n = 0
            for r_ in ("min", "typ", "max", "value"):
                i_ = roles.get(r_)
                if i_ is not None and i_ < len(lrow):
                    n = max(n, len(lrow[i_]))
            if n > 1:
                for k in range(n):
                    sub = list(row)
                    # The symbol column splits too. "RθJC / RθJL / RθJA" stacked over "5 / 9 / 24"
                    # is three parameters on three lines; leaving the symbol cell whole gives three
                    # symbols against one number, which split_packed_row correctly refuses to guess
                    # at — so the row vanished.
                    for r_ in ("symbol", "parameter", "unit",
                               "min", "typ", "max", "value", "conditions"):
                        i_ = roles.get(r_)
                        if i_ is not None and i_ < len(lrow):
                            ls = lrow[i_]
                            sub[i_] = ls[k] if k < len(ls) else (ls[0] if len(ls) == 1 else "")
                    entries.extend(_parse_row(sub, roles, symbol_map, cell, name_map))
                continue
        row = _inherit_continuation(row, roles, prev)
        got = _parse_row(row, roles, symbol_map, cell, name_map)
        if got:
            prev = row
        entries.extend(got)
    return entries


def _inherit_continuation(row, roles, prev):
    """A row with values but no symbol continues the row above it.

    Vendors give a second operating point as a CONTINUATION: the parameter and symbol cells are
    left blank and only the condition that changed is written.

        Instantaneous forward voltage | IF = 25 A | TJ = 25 degC  | VF (1) | 0.89 | 0.93 | V
                                      |           | TJ = 125 degC |        | 0.77 | -    |

    Read row by row, the second line has no symbol and is discarded — which is how the LVE5060E's
    HOT forward voltage went missing, the one value the whole conduction model turns on. Inheriting
    the symbol keeps the pair, and each keeps its own condition, so the two-temperature V-I curve
    comes out of the table instead of needing the plot.
    """
    if prev is None:
        return row
    sym_i, par_i = roles.get("symbol"), roles.get("parameter")
    has_symbol = sym_i is not None and sym_i < len(row) and norm_text(row[sym_i])
    has_param = par_i is not None and par_i < len(row) and norm_text(row[par_i])
    if has_symbol or has_param:
        return row
    has_value = any(roles.get(r) is not None and roles[r] < len(row)
                    and parse_numbers(row[roles[r]]) for r in ("min", "typ", "max", "value"))
    if not has_value:
        return row
    # EVERY EMPTY CELL INHERITS, except the value columns. A continuation states only what
    # CHANGED, so whatever it leaves blank still holds — the symbol, the unit, and the conditions
    # that did not vary. Naming the columns individually kept missing one: first the unit, and the
    # hot reverse current came out as 35 A instead of 35 uA; then the conditions, and the hot
    # forward voltage arrived with no I_F, so it could not pair with the cold point into a curve.
    # The value columns are excluded deliberately: a blank max belongs to this row's condition, not
    # to the row above, and inheriting it would attach the parent's limit to a different operating
    # point.
    values = {roles.get(r) for r in ("min", "typ", "max", "value")}
    out = list(row)
    for i_ in range(min(len(out), len(prev))):
        if i_ in values:
            continue
        if not norm_text(out[i_]) and norm_text(prev[i_]):
            out[i_] = prev[i_]
    return out


def _parse_row(row, roles, symbol_map, cell, name_map=None) -> list[dict]:
    entries: list[dict] = []
    name_cell = cell(row, "parameter") or ""
    # A summary block ("Parameter | Value | Unit") has no symbol column: the symbol IS the
    # parameter cell, e.g. "R DS(on),typ". Falling back to it is what lets the summary take
    # part in the summary-versus-detail cross-check.
    sym_cell = cell(row, "symbol") or name_cell
    # Summary blocks qualify the symbol in the cell itself: "RDS(on),typ", "QG,typ",
    # "Eoss @ 400 V". Split the qualifier off so the symbol still resolves, and keep the
    # inline condition rather than discarding it.
    sym_cell, _inline_field, _inline_cond = _split_qualifier(sym_cell)
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
    # A RANGE IS ONE VALUE, however many symbols share the cell. "TJ(3), TStg" against
    # "-55 to +175" was paired POSITIONALLY into TJ = -55 and TStg = +175, so the operating
    # range's LOWER bound became the maximum junction temperature — the thermal limit the whole
    # design is checked against, off by 230 degrees and in the unsafe direction for T_stg.
    _syms = _SYMBOL_TOKEN.findall(norm_text(sym_cell))
    _rng = parse_range(primary)
    if _rng and _syms:
        pairs = [(sym, _rng[1]) for sym in _syms]
    elif len(_syms) > 1 and symbol_map.get(_symbol_lookup(sym_cell)):
        # "TJ MAX" is ONE parameter whose symbol carries a qualifier word, not two parameters.
        # It tokenises as two symbols against a single value, positional pairing gives up, and
        # the row is dropped — which is how the silicon part lost its 150 degC junction limit.
        _n = parse_numbers(primary)
        pairs = [(norm_text(sym_cell), _n[0])] if _n else []
    else:
        pairs = split_packed_row(sym_cell, primary)
    if not pairs:
        if norm_text(sym_cell) or norm_text(name_cell):
            entries.append({"unresolved": True, "symbol": norm_text(sym_cell),
                            "name": norm_text(name_cell), "row": row})
        return entries

    multi = len(pairs) > 1
    for sym, val in pairs:
        key = symbol_map.get(_symbol_lookup(sym))
        if not key and name_map:
            # BY NAME, only when the symbol did not resolve. A vendor may print the forward
            # capacitance as a bare "C", which is also a package DIMENSION on the mechanical
            # drawing — so matching that letter globally imported a 0.38 mm lead thickness as a
            # junction capacitance. The dimensions table has no parameter-name column at all,
            # which is what makes the name the safe discriminator here.
            key = name_map.get(re.sub(r"\s+", " ", norm_text(name_cell).lower()).strip())
        _conds = parse_conditions(cond_text)
        _conds.update(_inline_cond)
        rec: dict[str, Any] = {
            "symbol": sym, "name": norm_text(name_cell),
            "unit_text": norm_text(unit_cell),
            "conditions": _conds,
            "condition_text": norm_text(cond_text),
        }
        if key:
            rec["key"] = key
        else:
            rec["unresolved"] = True

        if _rng is not None:
            rec["min"], rec["max"] = _rng[0] * scale, _rng[1] * scale
        elif multi:
            rec[_inline_field or "typ"] = val * scale
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
                    if len(nums) == 1 and _inline_field:
                        # "RDS(on),max | 41" is a MAXIMUM. Filing it under typ would put the
                        # worst-case number where the design number belongs — and the
                        # summary-versus-detail cross-check would then compare max against typ
                        # and report a disagreement that does not exist.
                        rec[_inline_field] = nums[0] * scale
                    elif len(nums) > 1:
                        # several values under one symbol = several conditions (the with/without
                        # heatsink case). Keep them all; discarding one loses an operating point.
                        rec["values"] = [n * scale for n in nums]
                        rec["typ"] = nums[0] * scale
                    elif nums:
                        rec["typ"] = nums[0] * scale
        if base_unit:
            rec["si_unit"] = base_unit
        # WHICH VARIANTS THIS ROW IS FOR. A banded row names them in a cell of its own; an ordinary
        # row names none and applies to the whole family. Recorded rather than resolved here: the
        # extractor does not know which part the designer is holding.
        _vars: list[str] = []
        for i, c in enumerate(row):
            if i in roles.values() and i != roles.get("conditions"):
                continue
            for v in variant_tokens(c):
                if v not in _vars:
                    _vars.append(v)
        if _vars:
            rec["variants"] = _vars
        entries.append(rec)
    return entries


_QUALIFIER = re.compile(r"^(?P<sym>.+?)\s*,\s*(?P<field>typ|max|min)\.?$", re.I)
_INLINE_AT = re.compile(r"^(?P<sym>.+?)\s*@\s*(?P<cond>.+)$")


def _split_qualifier(sym_cell: str) -> tuple[str, Optional[str], dict]:
    """"RDS(on),typ" -> ("RDS(on)", "typ", {}); "Eoss @ 400 V" -> ("Eoss", None, {"V_DS": 400}).

    Summary blocks state the qualifier in the symbol cell because they have no min/typ/max
    columns. Dropping it would make the summary unusable for the cross-check, and dropping the
    inline condition would make an E_oss quoted at 400 V look like one quoted at the design bus.
    """
    t = norm_text(sym_cell)
    field = None
    cond: dict = {}
    m = _INLINE_AT.match(t)
    if m:
        t = m.group("sym")
        nums = parse_numbers(m.group("cond"))
        base, scale = parse_unit(re.sub(r"[\d.,\s]", "", m.group("cond")))
        if nums:
            cond["V_DS" if base == "V" else (base or "at")] = nums[0] * scale
    m = _QUALIFIER.match(t)
    if m:
        t, field = m.group("sym"), m.group("field").lower()
    return t, field, cond


def _symbol_lookup(sym: str) -> str:
    """Normalise a datasheet symbol for map lookup: case, spaces, punctuation and the theta glyph
    all vary between vendors and even between tables in one file."""
    t = norm_text(sym).lower()
    # FOOTNOTE MARKERS FIRST, while the brackets are still there to identify them. Vendors tag a
    # symbol with the note that qualifies it — "VF (1)", "RthJA (1)(2)", "IO (1)" — and stripping
    # brackets before the digits turned those into vf1, rthja12 and io1, which match nothing. That
    # is why the LVE5060E's forward voltage and thermal resistance did not extract even once its
    # tables parsed. A DIGIT-ONLY group is a footnote; "(AV)" in IF(AV) is part of the symbol.
    t = re.sub(r"\(\s*\d+\s*\)", "", t)
    # PRIVATE-USE AREA. A symbol-font integral sign arrives as U+F0F2, not as U+222B, so the I2t
    # row of the reference SiC datasheet read as "i2dt" and matched nothing.
    t = "".join(ch for ch in t if not (0xE000 <= ord(ch) <= 0xF8FF))
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
    # Two entries that state DIFFERENT conditions are two operating points, not a disagreement,
    # even when neither condition parsed into a number. "40 A with heatsink / 5 A without" is the
    # case: both have empty condition dicts and wholly different condition text.
    findings = []
    for key, group in by_key.items():
        if len(group) < 2:
            continue
        for field in ("typ", "max", "min"):
            plain = [g for g in group if isinstance(g.get(field), (int, float))
                     and not g.get("conditions")]
            if len({(g.get("condition_text") or "") for g in plain}) > 1:
                continue
            vals = [g[field] for g in plain]
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
def extract(pdf_bytes: bytes, device_class: str, template: Optional[dict] = None,
            variant: Optional[str] = None) -> dict:
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
    name_map = {re.sub(r"\s+", " ", (k or "").lower()).strip(): v
                for k, v in (tmpl.get("name_map") or {}).items()}

    tables = find_parameter_tables(pdf_bytes)
    rejected = [t for t in tables if t.get("rejected")]
    good = [t for t in tables if not t.get("rejected")]

    flat: list[dict] = []
    for t in good:
        for e in parse_table(t, symbol_map, name_map):
            e["source"] = {"page": t["page"], "bbox": t.get("bbox")}
            flat.append(e)

    resolved = [e for e in flat if e.get("key")]
    profile["unresolved"] = [e for e in flat if not e.get("key")]

    # SERIES DATASHEETS. One document, several parts, and the values that differ between them are
    # banded. Without a variant the banded rows are ALL kept — they are then visibly several
    # entries for one key, which the review screen and the cross-check both report, rather than one
    # silently-chosen band. With a variant, only its own band survives.
    variants = find_variants(pdf_bytes)
    # Only a variant this document actually covers filters it. A part number that is not one of
    # them says nothing about the bands, and using it would drop every banded row.
    chosen = variant if (variant and variant in variants) else None
    if chosen:
        resolved = [e for e in resolved
                    if not e.get("variants") or chosen in e["variants"]]
    profile["variants"] = variants
    profile["variant"] = chosen
    if chosen:
        profile["part_number"] = chosen

    # group by canonical key -> one parameter with several condition-qualified entries
    grouped: dict[str, dict] = {}
    for e in resolved:
        p = grouped.setdefault(e["key"], {"key": e["key"], "entries": []})
        entry = {k: v for k, v in e.items()
                 if k in ("min", "typ", "max", "values", "conditions", "condition_text",
                          "symbol", "source", "si_unit", "variants")}
        entry["provenance"] = "extracted"
        p["entries"].append(entry)
    profile["parameters"] = list(grouped.values())

    checks = cross_check(resolved)
    return {"profile": profile, "triage": tri, "tables": good, "rejected": rejected,
            "variants": variants, "variant": profile["variant"],
            "variant_required": bool(variants) and not variant,
            "cross_check": checks, "ok": bool(profile["parameters"]),
            "reason": "" if profile["parameters"] else
                      "no parameters could be mapped to canonical keys — the vendor template may "
                      "not cover this layout"}
