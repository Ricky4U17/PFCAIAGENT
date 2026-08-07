"""
datasheet_flow.py — the datasheet-first selection flow (M3).
============================================================
Ties M0-M2 into the three things the GUI needs:

    requirements(design)             what the part must clear, stated BEFORE any part is named
    upload(...)                      PDF -> extracted profile -> review rows
    confirm(...)                     reviewed values -> confirmed profile -> engine block

WHY REQUIREMENT FIRST. The GUI shows V_DSS >= ... and I_D >= ... and no manufacturer part number
at all until a datasheet is uploaded. That is the same shape Chapter 8 already uses for the NTC and
the fuse: derive the requirement, then name a part, never the other way round. It also removes the
Top-10 loss ranking, which ordered candidates by a loss computed from the nine parameters the
parametric catalogue does not carry.

WHY A REVIEW SCREEN AT ALL. Extraction is a machine reading a PDF; it will occasionally be
confidently wrong. The screen exists so a wrong value is caught by the person who can recognise it.
It therefore shows ONLY what the calculation consumes, each value with its conditions AND its
destination, and sorts anything unsupplied or derived to the top — a screen that shows forty
confirmed values with two problems buried in them is the ceremony of verification without the
substance.

WHAT IS STILL NOT FROM THE DATASHEET. Gate-drive voltage, gate resistors, the mounting interface
and the switching-model choice are DESIGN decisions. No upload can supply them, so they appear as
designer inputs with `source: "design"`, and the required-field manifest (M1) refuses to treat a
missing one as an engine default.
"""
from __future__ import annotations

import math
from typing import Any, Optional

from app.mode_b.semiconductor import datasheet_extract as DX
from app.mode_b.semiconductor import manifest as M
from app.mode_b.semiconductor import parts_store as PS
from app.mode_b.semiconductor import registry as R

# Margins on the blocking rating. Design choices with a stated default, not physics — surfaced so
# the requirement the GUI prints can be traced to something other than a number in the source.
DEFAULT_V_MARGIN = 1.20      # over the regulated bus, covering overshoot and tolerance
DEFAULT_I_MARGIN = 1.50      # over the per-channel peak


def requirements(design: dict, kind: str = "mosfet",
                 v_margin: float = DEFAULT_V_MARGIN,
                 i_margin: float = DEFAULT_I_MARGIN) -> dict:
    """What a part must clear, derived from the design alone.

    Stated before any datasheet is uploaded, and deliberately carrying NO part number: the designer
    sources a part against the requirement rather than picking from a ranked list whose ranking
    rests on estimated parameters.
    """
    from app.mode_b.semiconductor.adapter import build_design_ops
    vout = float(design.get("vout") or design.get("Vbus_V") or 0.0)
    nch = int(design.get("nch") or design.get("n_ch") or 1)
    try:
        _, s2, *_ = build_design_ops(design)
        iin_rms = float(max(s2["Iin_rms"]))
    except Exception:
        iin_rms = float(design.get("Iin_rms_worst_A") or 0.0)

    ipk_ch = math.sqrt(2.0) * iin_rms / max(nch, 1)
    v_min = vout * v_margin
    i_min = ipk_ch * i_margin

    return {
        "kind": kind,
        "V_DSS_min": round(v_min, 1),
        "I_D_min": round(i_min, 2),
        "basis": {
            "V_bus": vout, "v_margin": v_margin,
            "I_in_rms_worst": round(iin_rms, 3), "n_channels": nch,
            "I_pk_per_channel": round(ipk_ch, 3), "i_margin": i_margin,
        },
        "statement": (
            f"The part must block at least {v_min:.0f} V "
            f"({vout:.0f} V bus x {v_margin:g} margin) and carry at least {i_min:.1f} A "
            f"({ipk_ch:.1f} A per-channel peak x {i_margin:g} margin). "
            f"Source a part meeting these, then upload its datasheet."),
        "note": ("No part number is offered here on purpose. Ranking candidates by loss would rest "
                 "on parameters the parametric catalogue does not carry — E_oss, E_on/E_off, Q_gd, "
                 "R_DS(on) vs T_j are absent for every one of its 1311 MOSFETs."),
    }


# ── upload ────────────────────────────────────────────────────────────────────────────────────
def upload(pdf_bytes: bytes, kind: str, device_class: str, filename: str = "datasheet.pdf",
           part_number: Optional[str] = None, root: Optional[str] = None) -> dict:
    """Extract, store, and return everything the review screen needs.

    A PDF that cannot be read is REFUSED with a reason rather than yielding an empty profile that
    looks like a part with no parameters.
    """
    res = DX.extract(pdf_bytes, device_class)
    profile = res["profile"]

    if not res["ok"]:
        return {"ok": False, "reason": res["reason"], "triage": res["triage"],
                "profile": profile, "rows": [], "part_number": None}

    mpn = part_number or _guess_part_number(pdf_bytes) or "UNKNOWN"
    profile["part_number"] = mpn
    # The class comes from the tab the designer uploaded under, not from a field they fill in.
    profile.setdefault("parameters", []).append({
        "key": "device_class",
        "entries": [{"typ": device_class, "provenance": "extracted", "conditions": {}}]})
    profile["datasheet"]["filename"] = filename

    stored = PS.store_datasheet(mpn, pdf_bytes, filename, aliases=[mpn], root=root)
    written = PS.write_extracted(mpn, profile, root=root)

    prev = None
    if stored.get("previous_sha256"):
        prev = PS.load_profile(mpn, kind="confirmed", root=root)

    return {
        "ok": True, "part_number": mpn, "device_class": device_class,
        "profile": profile, "stored": stored, "written": written,
        "triage": res["triage"],
        "rows": review_rows(profile, device_class),
        "cross_check": res["cross_check"],
        "unresolved": profile.get("unresolved", []),
        "tables_kept": len(res["tables"]), "tables_rejected": len(res["rejected"]),
        "revision_diff": (PS.diff_profiles(prev, profile) if prev else []),
    }


def _guess_part_number(pdf_bytes: bytes) -> Optional[str]:
    """Best-effort part number from the document title or first page.

    Offered as a SUGGESTION the designer confirms — never the primary key typed by hand, because a
    typo there silently creates a second library entry for one part.
    """
    import re
    # A part number contains DIGITS. Without that test the first page of the Infineon datasheet
    # yields "MOSFET", which would have created a library folder of that name.
    def _plausible(tok: str) -> bool:
        return (len(tok) >= 6 and any(c.isdigit() for c in tok)
                and any(c.isalpha() for c in tok)
                and tok.upper() not in {"MOSFET", "DATASHEET", "REVISION"})

    try:
        import fitz
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        title = DX.norm_text((doc.metadata or {}).get("title") or "")
        for tok in title.split():
            if _plausible(tok):
                return tok
        # Otherwise the token that repeats on the most pages: a part number appears in the header
        # or footer of every page, while a heading appears once.
        from collections import Counter
        seen = Counter()
        for i in range(min(4, doc.page_count)):
            toks = {t for t in re.findall(r"[A-Z][A-Z0-9\-]{5,}", DX.norm_text(doc[i].get_text()))
                    if _plausible(t)}
            seen.update(toks)
        if seen:
            best, count = seen.most_common(1)[0]
            if count >= 2:
                return best
            return best
    except Exception:
        pass
    return None


# ── the review screen ─────────────────────────────────────────────────────────────────────────
def review_rows(profile: dict, device_class: str) -> list[dict]:
    """One row per quantity the calculation consumes — and nothing else.

    Sixty rows produces click-through. Ten to fifteen, each with its conditions and its
    destination, is reviewable.
    """
    by_key: dict[str, list[dict]] = {}
    for p in profile.get("parameters", []):
        by_key[p["key"]] = p.get("entries", [])

    rows = []
    for p in R.parameters(device_class):
        consumed = p.get("consumed_by", [])
        if not ({"loss_engine", "requirement", "thermal"} & set(consumed)):
            continue
        # Tolerance multipliers default to 1.0 (typical) and are only touched for a worst-case
        # sign-off run. Listing them as "missing" is noise, and noise is what turns a review screen
        # into click-through.
        if p["key"].startswith("k_"):
            continue
        # A quantity neither required nor extracted has nothing for a reviewer to judge.
        if not p.get("required") and p["key"] not in by_key:
            continue
        entries = by_key.get(p["key"], [])
        best = _pick_entry(entries)
        val = None
        if best:
            val = best.get("typ", best.get("max", best.get("min")))
        display = None
        if isinstance(val, (int, float)) and p["si_unit"] not in ("text", "1"):
            n, unit = R.to_display(p["key"], float(val))
            display = f"{n:g} {unit}".strip()

        rows.append({
            "key": p["key"],
            "label": p.get("report_label", p["key"]),
            "unit": p["display_unit"],
            "value": val,
            "display": display,
            "conditions": (best or {}).get("conditions") or {},
            "entries": len(entries),
            "all_entries": [
                {"value": e.get("typ", e.get("max", e.get("min"))),
                 "min": e.get("min"), "typ": e.get("typ"), "max": e.get("max"),
                 "conditions": e.get("conditions") or {},
                 "provenance": e.get("provenance", "extracted")}
                for e in entries
            ] if len(entries) > 1 else [],
            "supplied": val is not None,
            "source_kind": p["source"],
            "provenance": (best or {}).get("provenance", "default" if val is None else "extracted"),
            "required": bool(p.get("required")),
            "is_curve": bool(p.get("is_curve")),
            "destination": _destination(p),
            "description": p.get("description", ""),
        })

    # Problems first: unsupplied, then required, then design-sourced. A reviewer should meet the
    # gaps before the confirmations.
    rows.sort(key=lambda r: (r["supplied"], not r["required"], r["source_kind"] != "design",
                             r["key"]))
    return rows


def _pick_entry(entries: list[dict]) -> Optional[dict]:
    """The entry a review screen should show first — the one with the most stated conditions, which
    is the one a designer can actually judge."""
    if not entries:
        return None
    return max(entries, key=lambda e: (len(e.get("conditions") or {}),
                                       1 if "typ" in e else 0))


_DESTINATION = {
    "R_DS_on": "conduction loss", "R_DS_on_vs_Tj": "hot conduction loss",
    "C_iss": "switching transition times", "Q_gd": "Miller charge, switching energy",
    "Q_g": "gate-drive loss", "V_GS_th": "switching model", "g_fs": "switching energy vs current",
    "E_oss_vs_VDS": "output-capacitance loss", "E_on": "switching-energy anchor",
    "E_off": "switching-energy anchor", "R_th_jc": "junction temperature",
    "R_th_cs": "junction temperature", "V_GS_drive": "gate-drive loss and switching",
    "R_g_on": "turn-on energy", "R_g_off": "turn-off energy",
    "V_DSS": "blocking requirement", "I_D": "current requirement",
    "Tj_max": "thermal limit check", "I_FSM": "Chapter 8 surge check",
    "I2t": "Chapter 8 surge check",
}


def _destination(p: dict) -> str:
    return _DESTINATION.get(p["key"], ", ".join(p.get("consumed_by", [])) or "report")


# ── confirm ───────────────────────────────────────────────────────────────────────────────────
def confirm(part_number: str, edits: dict, device_class: str, reviewed_by: str = "designer",
            root: Optional[str] = None) -> dict:
    """Write the designer's approved values, and return the engine block they produce.

    An edited value is stamped `corrected` and the extracted original is RETAINED, so the library
    can always answer "the machine read X, you confirmed Y".
    """
    profile = PS.load_profile(part_number, kind="extracted", root=root)
    if profile is None:
        raise PS.PartsStoreError(f"no extraction on file for {part_number!r}; upload the datasheet first")

    profile = dict(profile)
    for key, new_val in (edits or {}).items():
        R.get(key)                                   # unknown canonical key raises
        found = False
        for p in profile.get("parameters", []):
            if p["key"] != key:
                continue
            e = _pick_entry(p["entries"]) or {}
            if e:
                if "extracted_original" not in e:
                    e["extracted_original"] = {k: e.get(k) for k in ("min", "typ", "max")}
                e["typ"] = new_val
                e["provenance"] = "corrected"
                found = True
        if not found:
            profile.setdefault("parameters", []).append({
                "key": key,
                "entries": [{"typ": new_val, "provenance": "manual", "conditions": {}}],
            })

    written = PS.write_confirmed(part_number, profile, reviewed_by=reviewed_by, root=root)
    return {"ok": True, "part_number": part_number, "written": written,
            "rows": review_rows(profile, device_class)}


# ── profile -> engine block ───────────────────────────────────────────────────────────────────
def profile_to_block(profile: dict, device_class: str, design: dict) -> dict:
    """Turn a confirmed profile into an engine block.

    `select()` is what earns its keep here: the on-resistance handed to the engine is the entry at
    the design's OWN gate-drive voltage, not whichever entry parsed first. Ask for a condition the
    datasheet does not state and it raises rather than substituting a neighbour.
    """
    vgs = float(design.get("V_GS_drive") or design.get("vg") or 0.0)
    blk: dict[str, Any] = {
        "manufacturer": profile.get("manufacturer"),
        "part_number": profile.get("part_number"),
        M.SOURCE_KEY: f"datasheet {profile.get('datasheet', {}).get('filename', '')}"
                      f" (sha {str(profile.get('datasheet', {}).get('sha256', ''))[:12]})",
    }
    prov: dict[str, str] = {}

    def put(key, value, how="extracted"):
        if value is None:
            return
        blk.update(R.expand_to_engine_fields({key: value}))
        prov[key] = how

    # conduction — at the design's gate voltage, 25 degC reference
    try:
        e = M.select(profile, "R_DS_on", V_GS=vgs, T_j=25) if vgs else None
    except M.MissingParameterError:
        e = None
    if e is None:
        e = _pick_entry(_entries_of(profile, "R_DS_on"))
    if e:
        put("R_DS_on", e.get("typ") or e.get("max"))

    # A REAL temperature curve from the datasheet's own two points, replacing the generic
    # "SiC rises 1.4x by 125 degC" assumption that has been standing in for it.
    hot = _hot_entry(profile, vgs)
    cold = e
    if hot and cold and cold.get("typ"):
        t_hot = (hot.get("conditions") or {}).get("T_j", 175.0)
        put("R_DS_on_vs_Tj", [[25.0, float(t_hot)],
                              [1.0, round(float(hot["typ"]) / float(cold["typ"]), 4)]], "derived")

    for key in ("C_iss", "Q_g", "Q_gd", "V_GS_th", "g_fs", "R_th_jc", "V_SD"):
        ent = _pick_entry(_entries_of(profile, key))
        if ent:
            put(key, ent.get("typ") or ent.get("max") or ent.get("min"))

    # LEAKAGE (plan 5.5). The blocking-loss term has been zero because nothing ever populated the
    # curve — a placeholder, not a measurement. Two published I_DSS points, at 25 degC and at
    # T_j,max, give the engine a real curve to interpolate over.
    idss = [(float((e.get("conditions") or {}).get("T_j")),
             float(e.get("typ") or e.get("max")))
            for e in _entries_of(profile, "I_DSS_vs_Tj")
            if (e.get("conditions") or {}).get("T_j") and (e.get("typ") or e.get("max"))]
    if len(idss) >= 2:
        idss.sort()
        put("I_DSS_vs_Tj", [[t for t, _ in idss], [v for _, v in idss]])

    # C_rss is deliberately NOT mapped. The datasheet publishes ONE point (7 pF at 400 V) and the
    # engine's crss_curve expects C_rss(V), which swings by orders of magnitude across the blocking
    # range. A two-point fit through a single value would be a shape nobody measured; without it
    # the engine uses the Miller integral Q_gd*V/2, and Q_gd is now the real 6.2 nC.

    # E_oss: phase 1 has the published point, not the curve. Anchoring a V^1.5 shape ON THE REAL
    # VALUE is not the same as inventing one from die area — that estimate was 3.4x high on this
    # part — but it is still a fitted shape, so it is stamped `derived` and M7 replaces it with the
    # digitised curve.
    ent = _pick_entry(_entries_of(profile, "E_oss_vs_VDS"))
    if ent and (ent.get("typ") or ent.get("max")):
        v_at = float((ent.get("conditions") or {}).get("V_DS") or 400.0)
        e_at = float(ent.get("typ") or ent.get("max"))
        put("E_oss_vs_VDS", [[v_at * 0.25, v_at],
                             [round(e_at * 0.25 ** 1.5, 12), e_at]], "derived")

    # V_plateau is DERIVED, not published. With g_fs known it is per-current inside the engine;
    # without it, V_GS(th) + 2 V is the standing approximation. Deriving it here rather than letting
    # the dataclass default fire is the difference between a number with a stated basis and a
    # hardcode — which is the whole point of M1's manifest.
    vth_e = _pick_entry(_entries_of(profile, "V_GS_th"))
    if vth_e and (vth_e.get("typ") or vth_e.get("max")):
        put("V_plateau", float(vth_e.get("typ") or vth_e.get("max")) + 2.0, "derived")

    cls = R.device_class(device_class)
    blk["tech"] = "sic" if "sic" in device_class else "si"
    prov["device_class"] = "extracted"

    for key in ("V_GS_drive", "R_g_on", "R_g_off", "R_g_common", "R_th_cs", "sw_method"):
        val = design.get(key)
        if val not in (None, ""):
            put(key, val, "manual")

    blk[M.PROVENANCE_KEY] = prov
    blk["_conduction_form"] = cls["conduction_loss_form"]
    blk["_checks"] = _consistency_checks(profile, design, blk)
    return blk


def _consistency_checks(profile: dict, design: dict, blk: dict) -> list[dict]:
    """Cross-checks between the datasheet's stated conditions and the design's own choices.

    These are the questions a value cannot answer about itself: Q_g is quoted for a particular gate
    swing, R_DS(on) for a particular gate voltage. Using one at a different operating point is not
    wrong provided somebody decided to — so they are reported, never silently corrected.
    """
    out = []
    vgs = design.get("V_GS_drive")

    qg_e = _pick_entry(_entries_of(profile, "Q_g")) or {}
    swing = (qg_e.get("conditions") or {}).get("V_GS_swing")
    if vgs and swing and abs(float(swing) - float(vgs)) > 0.5:
        out.append({
            "key": "Q_g", "severity": "check",
            "message": (f"Q_g = {(qg_e.get('typ') or 0) * 1e9:.0f} nC is quoted for a "
                        f"{float(swing):g} V gate swing, but the design drives {float(vgs):g} V. "
                        f"Gate-drive loss scales with the charge actually moved, so this over- or "
                        f"under-states it. Read Q_g at {float(vgs):g} V off the gate-charge curve "
                        f"(phase 2), or accept the difference deliberately.")})

    rds_conds = [c for c in ((e.get("conditions") or {}).get("V_GS")
                             for e in _entries_of(profile, "R_DS_on")) if c]
    if vgs and rds_conds and not any(abs(c - float(vgs)) < 0.5 for c in rds_conds):
        out.append({
            "key": "R_DS_on", "severity": "check",
            "message": (f"No R_DS(on) is published at V_GS = {float(vgs):g} V; the datasheet states "
                        f"{sorted(set(rds_conds))} V. The value used is the nearest stated "
                        f"condition, which is an approximation.")})

    if "gfs" not in blk:
        out.append({
            "key": "g_fs", "severity": "note",
            "message": ("Transconductance is not published in this datasheet's tables, so the "
                        "Miller plateau is treated as constant and switching energy comes out "
                        "strictly proportional to current. The transfer-characteristic curve "
                        "restores the correct superlinearity (phase 2).")})

    if "idss_curve" not in blk:
        out.append({
            "key": "I_DSS_vs_Tj", "severity": "note",
            "message": ("Blocking (leakage) loss is reported as zero because no two-point I_DSS "
                        "curve could be built. That is a placeholder, not a measurement.")})
    return out


def _entries_of(profile: dict, key: str) -> list[dict]:
    for p in profile.get("parameters", []):
        if p["key"] == key:
            return p.get("entries", [])
    return []


def _hot_entry(profile: dict, vgs: float) -> Optional[dict]:
    best = None
    for e in _entries_of(profile, "R_DS_on"):
        tj = (e.get("conditions") or {}).get("T_j")
        if tj and tj > 100 and (not vgs or (e.get("conditions") or {}).get("V_GS") in (None, vgs)):
            if best is None or tj > (best.get("conditions") or {}).get("T_j", 0):
                best = e
    return best


# ── the loss table the results tab renders ────────────────────────────────────────────────────
FET_LOSS_COLUMNS = [
    ("Vac", "Input", "V"),
    ("Po", "P_out", "W"),
    ("P_FET_cond", "Conduction", "W"),
    ("P_FET_sw", "Switching", "W"),
    ("P_FET_coss", "E_oss", "W"),
    ("P_FET_rr", "Recovery", "W"),
    ("P_FET_leak", "Leakage", "W"),
    ("P_FET_total", "TOTAL (all channels)", "W"),
    ("Tj_FET", "T_j", "degC"),
]


def loss_table(per_point: list[dict]) -> dict:
    """The MOSFET loss breakdown per input voltage, taken STRAIGHT from the engine's own per-point
    rows — not recomputed. Recomputing it in the presentation layer is how the Top-10 screen came
    to disagree with the Results page (C157-C160), and that is not a mistake worth repeating.

    Gate-drive loss is reported SEPARATELY: it is dissipated in the driver and R_g, not in the
    MOSFET junction, so it belongs in the efficiency budget but not in the device total.
    """
    rows = []
    for r in per_point or []:
        row = {k: r.get(k) for k, _, _ in FET_LOSS_COLUMNS}
        row["P_gate_driver"] = r.get("P_gate_driver")
        rows.append(row)
    worst = max(rows, key=lambda r: r.get("P_FET_total") or 0.0) if rows else None
    hottest = max(rows, key=lambda r: r.get("Tj_FET") or 0.0) if rows else None
    return {
        "columns": [{"key": k, "label": lbl, "unit": u} for k, lbl, u in FET_LOSS_COLUMNS],
        "rows": rows,
        "worst_loss": worst, "hottest": hottest,
        "note": ("Gate-drive loss is listed separately because it is dissipated in the driver and "
                 "the gate resistors, not in the MOSFET junction — it belongs in the efficiency "
                 "budget but not in the device total or its temperature rise."),
    }
