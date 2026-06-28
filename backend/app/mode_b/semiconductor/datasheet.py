"""
Datasheet extraction — pull the loss-model parameters from an uploaded PDF datasheet.
=====================================================================================
Heuristic, offline extractor: pypdf text → label-anchored regex per parameter. It returns the
values it can find as an engine block (manufacturer/part guessed from the header), plus the list
of fields found vs missing, so the GUI can show a confirmation table the designer edits before
the loss calculation. Curves (Rds(on)-vs-Tj, Eoss-vs-V, Vf-vs-If) are rarely machine-readable, so
those are left to the DB-style estimate / manual entry; scalar parameters are the target here.
"""
from __future__ import annotations
import io, re

_OHM = "[" + chr(0x03A9) + chr(0x2126) + "]"
_MU = chr(0xb5) + chr(0x3bc)


def extract_text(pdf_bytes: bytes, max_pages: int = 8) -> str:
    from pypdf import PdfReader
    r = PdfReader(io.BytesIO(pdf_bytes))
    return "\n".join((p.extract_text() or "") for p in r.pages[:max_pages])


def _num_after(text, label, unit, scale_map=None, prefixed=True):
    """Find 'label … NUMBER [prefix]UNIT' (label and value within ~80 chars)."""
    pre = "[pnu" + _MU + "mkKM]?" if prefixed else ""
    pat = "(?:" + label + r").{0,80}?(-?\d+\.?\d*)\s*(" + pre + r")\s*" + unit
    m = re.search(pat, text, re.I | re.S)
    if not m:
        return None
    val = float(m.group(1))
    if prefixed:
        pref = m.group(2)
        scale = {"p": 1e-12, "n": 1e-9, "u": 1e-6, "µ": 1e-6, "μ": 1e-6, "m": 1e-3,
                 "": 1.0, "k": 1e3, "K": 1e3, "M": 1e6}.get(pref, 1.0)
        val *= scale
    return val


def _rth(text):
    """Rθ(j-c) in K/W or °C/W (junction-to-case)."""
    for pat in (r"R\s*th.{0,8}?[jJ].{0,6}?[cC].{0,40}?(\d+\.?\d*)\s*[" + chr(0xb0) + r"KkC]*\s*/\s*W",
                r"(?:[jJ]unction.{0,12}?[cC]ase|[Tt]hermal [Rr]esistance).{0,40}?(\d+\.?\d*)\s*[" + chr(0xb0) + r"KkC]*\s*/\s*W"):
        m = re.search(pat, text, re.I | re.S)
        if m:
            v = float(m.group(1))
            if 0.05 <= v <= 50:
                return v
    return None


def _header(text):
    """Best-effort manufacturer / part number from the first lines."""
    lines = [l.strip() for l in text.splitlines() if l.strip()][:25]
    part = None
    for l in lines:
        m = re.search(r"\b([A-Z0-9]{2,}[A-Z0-9\-]{3,})\b", l)
        if m and any(c.isdigit() for c in m.group(1)):
            part = m.group(1); break
    mfr = None
    for kw in ["Infineon", "STMicro", "ST ", "Wolfspeed", "Cree", "ROHM", "Rohm", "onsemi",
               "ON Semi", "Vishay", "Nexperia", "Toshiba", "Diodes", "IXYS", "Microchip", "GeneSiC"]:
        if kw.lower() in text[:1500].lower():
            mfr = kw.strip(); break
    return mfr, part


def extract(pdf_bytes: bytes, kind: str) -> dict:
    """Return {block, found, missing, raw_sample}. `block` is a partial engine block (scalars)."""
    text = extract_text(pdf_bytes)
    flat = re.sub(r"[ \t]+", " ", text)
    mfr, part = _header(flat)
    blk = {"manufacturer": mfr, "part_number": part}
    found, missing = [], []

    def take(key, val):
        if val is not None:
            blk[key] = val; found.append(key)
        else:
            missing.append(key)

    if kind == "mosfet":
        sic = bool(re.search(r"silicon\s*carbide|\bSiC\b", flat, re.I))
        blk["tech"] = "sic" if sic else "si"
        take("vdss",     _num_after(flat, r"V\s*\(?DS\)?|Drain[- ]Source Voltage", "V", prefixed=False))
        take("rdson_25", _num_after(flat, r"R\s*DS\s*\(?on\)?|on[- ]resistance", _OHM))
        take("qg",       _num_after(flat, r"Q\s*[gG]\b|Total Gate Charge", "C"))
        take("ciss",     _num_after(flat, r"C\s*iss|Input [Cc]apacitance", "F"))
        take("vth",      _num_after(flat, r"V\s*\(?GS\)?\(?th\)?|[Tt]hreshold", "V", prefixed=False))
        take("qgd",      _num_after(flat, r"Q\s*gd|Gate[- ]Drain Charge", "C"))
        take("eoss_J",   _num_after(flat, r"E\s*oss|Output [Cc]apacitance [Ee]nergy", "J"))
        take("rth_jc",   _rth(flat))
        if "eoss_J" in blk:                            # turn a single Eoss point into the 2-pt curve form
            e = blk.pop("eoss_J"); blk["eoss_at_v"] = [[100, 400], [round(e * 0.25 ** 1.5, 9), round(e, 9)]]
    elif kind == "diode":
        sic = bool(re.search(r"silicon\s*carbide|\bSiC\b|Schottky", flat, re.I))
        blk["is_sic"] = sic
        vf = _num_after(flat, r"V\s*F\b|Forward [Vv]oltage", "V", prefixed=False)
        if vf is not None:
            blk["vf_curve"] = [[1, 10], [max(0.3, vf - 0.3), vf]]; found.append("vf_curve")
        else:
            missing.append("vf_curve")
        if sic:
            take("qc", _num_after(flat, r"Q\s*[cC]\b|[Cc]apacitive [Cc]harge", "C"))
        else:
            take("qrr", _num_after(flat, r"Q\s*rr|[Rr]ecovery [Cc]harge", "C"))
        take("rth_jc", _rth(flat))
    else:  # bridge
        blk["topology"] = "diode"
        vf = _num_after(flat, r"V\s*F\b|Forward [Vv]oltage", "V", prefixed=False)
        if vf is not None:
            blk["vf_curve"] = [[1, 12], [max(0.3, vf - 0.3), vf]]; found.append("vf_curve")
        else:
            missing.append("vf_curve")

    return {"block": blk, "found": found, "missing": missing,
            "raw_sample": flat[:600], "manufacturer": mfr, "part_number": part}
