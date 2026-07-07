"""
Local NTC inrush-current-limiter (ICL) database
===============================================
Parse the ICL_Database.xlsx parametric table, normalize each part, screen the catalog against the
NTC sizing result, and rank the survivors — the same "database agent" pattern the semiconductor
selector uses (`app.mode_b.semiconductor.database`).

The Excel (specs/Database/ICL_Database.xlsx) is a Digi-Key-style parametric table. It carries the
REAL selection scalars — R@25°C, tolerance, steady-state max current, hot resistance at rated
current, disc diameter, lead spacing, qualification (AEC-Q200), approval agency — but NOT the
pulse-energy rating (Joules) or the "max switchable capacitance" a vendor quotes for surge
survival. So the hard screen runs on the real R25 (drives the inrush limit); the pulse energy is
ESTIMATED from the disc diameter with a clearly-labelled correlation (marked in every reason and
in `_estimated`) and only ORDERS the survivors — the designer confirms energy / max-C on the
datasheet before ordering, exactly as the module docstring in ntc_bypass_select warns.

A LOCAL copy of the workbook is kept under ./data/ so the selector no longer depends on the
specs/ tree being present at runtime; `build_all()` refreshes both the copy and the JSON cache.
"""
from __future__ import annotations
import os, re, json, shutil

_HERE = os.path.dirname(os.path.abspath(__file__))
_DATA = os.path.join(_HERE, "data")
_SPEC = os.path.normpath(os.path.join(_HERE, "..", "..", "..", "..", "specs", "Database"))
_XLSX = "ICL_Database.xlsx"
_JSON = "icl.json"

# Pulse-energy correlation (ESTIMATE): a high-energy disc's single-pulse capability scales with
# its bulk, ~ disc area. Calibrated against the representative large-disc parts (25 mm ~ 190 J,
# 30 mm ~ 270 J, 34 mm ~ 350 J → k ≈ 0.30 J/mm²). Conservative; always flagged as estimated.
_ENERGY_K = 0.30


# ── value helpers ─────────────────────────────────────────────────────────────
def _num(v):
    """Coerce a cell to float, tolerating '±20%', '5 A', stray text; None on failure."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    m = re.search(r"-?\d+\.?\d*", str(v))
    return float(m.group(0)) if m else None


def _energy_est_J(diameter_mm):
    """Estimated single-pulse energy capability from disc diameter (ESTIMATE, verify datasheet)."""
    d = _num(diameter_mm)
    return round(_ENERGY_K * d * d, 1) if d else None


# ── Excel ingest → normalized records ─────────────────────────────────────────
def _src_path():
    """Prefer the local copy under ./data; fall back to the specs/ workbook."""
    local = os.path.join(_DATA, _XLSX)
    return local if os.path.exists(local) else os.path.join(_SPEC, _XLSX)


def _rows(path):
    import openpyxl
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb[wb.sheetnames[0]]
    it = ws.iter_rows(values_only=True)
    hdr = [str(h).strip() if h is not None else "" for h in next(it)]
    for r in it:
        if any(v not in (None, "") for v in r):
            yield dict(zip(hdr, r))
    wb.close()


def _pick(rec, *subs):
    """First value whose header contains all `subs` (case-insensitive) — robust to °C / unit noise."""
    for k, v in rec.items():
        kl = k.lower()
        if all(s.lower() in kl for s in subs):
            return v
    return None


def ingest():
    out = []
    for r in _rows(_src_path()):
        part = _pick(r, "part")
        if not part:
            continue
        d = _num(_pick(r, "diameter"))
        out.append({
            "mfr":            _pick(r, "mfr") if _pick(r, "mfr") else _pick(r, "manufacturer"),
            "part_number":    part,
            "series":         _pick(r, "series"),
            "description":    _pick(r, "description"),
            "r25":            _num(_pick(r, "r @ 25")) or _num(_pick(r, "25", "ohm")),
            "tolerance":      _pick(r, "tolerance"),
            "imax":           _num(_pick(r, "steady", "max")) or _num(_pick(r, "current", "max")),
            "r_hot_mohm":     _num(_pick(r, "r @ current")) or _num(_pick(r, "mohm")),
            "diameter_mm":    d,
            "lead_spacing_mm": _num(_pick(r, "lead", "spac")),
            "qualification":  _pick(r, "qualif"),
            "approval":       _pick(r, "approv"),
            "datasheet_url":  _pick(r, "datasheet"),
            "url":            _pick(r, "url"),
            "energy_est_J":   _energy_est_J(d),         # ESTIMATE from diameter
        })
    return out


def build_all():
    """Refresh the LOCAL workbook copy (from specs/) + the JSON cache. Returns the part count."""
    os.makedirs(_DATA, exist_ok=True)
    spec_xlsx = os.path.join(_SPEC, _XLSX)
    local_xlsx = os.path.join(_DATA, _XLSX)
    if os.path.exists(spec_xlsx) and os.path.abspath(spec_xlsx) != os.path.abspath(local_xlsx):
        shutil.copyfile(spec_xlsx, local_xlsx)          # keep a local copy of the excel
    recs = ingest()
    with open(os.path.join(_DATA, _JSON), "w", encoding="utf-8") as f:
        json.dump(recs, f)
    return len(recs)


# ── load + filter ─────────────────────────────────────────────────────────────
_CACHE = None
def load():
    global _CACHE
    if _CACHE is None:
        path = os.path.join(_DATA, _JSON)
        if not os.path.exists(path):                    # self-bootstrap on first use
            build_all()
        with open(path, encoding="utf-8") as f:
            _CACHE = json.load(f)
    return _CACHE


def options():
    """Distinct selectable values for GUI dropdowns."""
    recs = load()
    uniq = lambda key: sorted({(r.get(key) or "").strip() for r in recs if r.get(key)})
    return {"manufacturers": uniq("mfr"), "qualification": uniq("qualification"),
            "approval": uniq("approval")}


def filter_parts(crit=None):
    """crit: {r25_min, imax_min, mfr, qualification, diameter_max}."""
    crit = crit or {}
    out = []
    for r in load():
        if crit.get("r25_min") and (r.get("r25") is None or r["r25"] < crit["r25_min"]): continue
        if crit.get("imax_min") and (r.get("imax") is None or r["imax"] < crit["imax_min"]): continue
        if crit.get("diameter_max") and (r.get("diameter_mm") is None or r["diameter_mm"] > crit["diameter_max"]): continue
        if crit.get("mfr") and (r.get("mfr") or "") != crit["mfr"]: continue
        if crit.get("qualification") and (r.get("qualification") or "") != crit["qualification"]: continue
        out.append(r)
    return out


# ── screen the catalog against an NTC sizing result ───────────────────────────
def _label(rec):
    d = rec.get("diameter_mm"); r25 = rec.get("r25")
    bits = []
    if r25 is not None: bits.append(f"{r25:g}Ω")
    if d is not None:   bits.append(f"Ø{d:g}mm")
    tail = f" — {', '.join(bits)}" if bits else ""
    return f"{rec.get('mfr') or ''} {rec.get('part_number') or ''}".strip() + tail


def screen_catalog(s, r, top: int = 12):
    """Screen the vendor ICL catalog against the sizing result `r` (from ntc_bypass_select.compute).

    Returns rows (name, ok, reasons) — the SAME contract as the built-in representative catalog —
    with the qualifying parts ranked first (smallest adequate disc = most economical), then the
    closest near-misses. R25 is the REAL datasheet value; pulse energy is estimated from diameter.
    """
    scored = []
    for rec in load():
        reasons = []; ok = True
        r25 = rec.get("r25")
        if r25 is None:
            ok = False; reasons.append("no R25 on record")
        elif r25 < r.r25_required:
            ok = False; reasons.append(f"R25 {r25:g}Ω < {r.r25_required:.2f}Ω required (inrush too high)")
        e_est = rec.get("energy_est_J")
        if e_est is None:
            ok = False; reasons.append("no disc diameter → energy not estimable")
        elif e_est < r.e_pulse_required:
            ok = False
            reasons.append(f"energy ~{e_est:g} J (est. from Ø) < {r.e_pulse_required:.0f} J required — verify datasheet")
        else:
            reasons.append(f"energy ~{e_est:g} J (est. from Ø; confirm on datasheet)")
        imax = rec.get("imax")
        if ok and imax is not None and imax < r.i_rms_worst:
            reasons.append(f"note: I_max {imax:g}A < I_rms {r.i_rms_worst:.1f}A (OK — bypassed after precharge)")
        # rank key: passing first; then smallest adequate disc; then R25 nearest the pick
        d = rec.get("diameter_mm") or 1e6
        rank = (0 if ok else 1, d, abs((r25 or 1e6) - r.r25_pick))
        scored.append((rank, _label(rec), ok, reasons, rec))
    scored.sort(key=lambda x: x[0])
    return [(name, ok, reasons) for _, name, ok, reasons, _ in scored[:top]]


def rank(s, r, top: int = 12):
    """Rich variant of screen_catalog: full records + verdict, for GUI cards / future use."""
    scored = []
    for rec in load():
        reasons = []; ok = True
        r25 = rec.get("r25"); e_est = rec.get("energy_est_J")
        if r25 is None or r25 < r.r25_required:
            ok = False; reasons.append("R25 below required")
        if e_est is None or e_est < r.e_pulse_required:
            ok = False; reasons.append("estimated energy below required")
        d = rec.get("diameter_mm") or 1e6
        scored.append(((0 if ok else 1, d), {**rec, "ok": ok, "reasons": reasons,
                       "energy_margin": (e_est / r.e_pulse_required) if e_est else None}))
    scored.sort(key=lambda x: x[0])
    return [rec for _, rec in scored[:top]]


if __name__ == "__main__":
    print("ingesting ICL database…", build_all(), "parts;  local copy + cache under", _DATA)
