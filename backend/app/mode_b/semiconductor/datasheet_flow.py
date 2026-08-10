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
    pout = 0.0
    try:
        ops, s2, *_ = build_design_ops(design)
        iin_rms = float(max(s2["Iin_rms"]))
        pout = float(max(ops[:, 1]))
    except Exception:
        iin_rms = float(design.get("Iin_rms_worst_A") or 0.0)
        pout = float(design.get("pout_hi") or 0.0)

    ipk_ch = math.sqrt(2.0) * iin_rms / max(nch, 1)
    v_min = vout * v_margin
    i_min = ipk_ch * i_margin

    # A BOOST DIODE IS NOT RATED THE WAY A MOSFET IS. Its catalogue rating is I_F(AV), an AVERAGE,
    # and the average current it carries is the OUTPUT current -- not the input current the MOSFET
    # sees. Comparing an average rating against an input peak is the mistake this branch exists to
    # avoid: at 393 V / 3600 W it is the difference between requiring ~7 A and requiring ~39 A.
    # A BRIDGE BLOCKS THE LINE PEAK AND CARRIES THE RECTIFIED MEAN. Neither is what it was being
    # told. It had been handed the MOSFET's requirement, which asks it to block the BUS (472 V here
    # against the 448 V it actually needs — conservative by accident, and wrong on any design whose
    # bus is not near the line peak) and to carry the per-channel input PEAK, 22.2 A, where the
    # rating it is compared against is an AVERAGE and the correct figure is 28.3 A. That second
    # error understates by 27 %, which is the direction that passes an under-rated part.
    if kind == "bridge":
        v_pk = math.sqrt(2.0) * float(design.get("vin_max") or 0.0)
        # 2*sqrt(2)/pi. Vendors rate a bridge by its total DC output current, not per diode, so
        # this is the quantity the datasheet's I_F(AV) is to be compared against.
        i_rect = 0.9003 * iin_rms
        n_par = max(int(design.get("n_parallel") or 1), 1)
        v_min_br = v_pk * v_margin
        i_min_br = i_rect * i_margin
        return {
            "kind": kind,
            "V_RRM_min": round(v_min_br, 1),
            "I_F_AV_min": round(i_min_br, 2),
            "I_rect_avg": round(i_rect, 2),
            "I_per_package": round(i_rect / n_par, 2),
            "basis": {
                "V_line_pk": round(v_pk, 1), "v_margin": v_margin,
                "I_in_rms_worst": round(iin_rms, 3), "i_margin": i_margin,
                "form_factor": 0.9003, "n_parallel": n_par, "V_bus": vout,
            },
            "statement": (
                f"The bridge must block at least {v_min_br:.0f} V "
                f"({v_pk:.0f} V line peak at {design.get('vin_max')} Vac x {v_margin:g} margin) and "
                f"carry at least {i_min_br:.1f} A average "
                f"({i_rect:.1f} A rectified mean x {i_margin:g} margin)"
                + (f", or {i_rect / n_par:.1f} A per package across {n_par} packages"
                   if n_par > 1 else "")
                + ". Source a part meeting these, then upload its datasheet."),
            "note": ("The bridge blocks the LINE peak, not the boost bus — it sits before the "
                     "inductor. And its rating is an AVERAGE: vendors quote I_F(AV) as the total "
                     "DC output current of the bridge, which is why the rectified mean is the "
                     "quantity compared against it rather than any peak or per-diode figure."),
        }

    # DIODE ONLY below. A bridge rectifier also carries an average current, but it is the INPUT
    # current, not the output current, which is why it has its own branch above.
    if kind == "diode":
        iout_ch = (pout / vout / max(nch, 1)) if vout else 0.0
        return {
            "kind": kind,
            "V_RRM_min": round(v_min, 1),
            "I_F_AV_min": round(iout_ch * i_margin, 2),
            "I_F_pk": round(ipk_ch, 2),
            "basis": {
                "V_bus": vout, "v_margin": v_margin, "P_out_worst": round(pout, 1),
                "I_out_per_channel": round(iout_ch, 3), "n_channels": nch,
                "I_pk_per_channel": round(ipk_ch, 3), "i_margin": i_margin,
            },
            "statement": (
                f"The diode must block at least {v_min:.0f} V "
                f"({vout:.0f} V bus x {v_margin:g} margin) and carry at least "
                f"{iout_ch * i_margin:.1f} A average ({iout_ch:.1f} A per-channel output current "
                f"x {i_margin:g} margin). Its repetitive peak is {ipk_ch:.1f} A, which an I_F(AV) "
                f"rating does not by itself cover - check the datasheet's peak and surge ratings "
                f"separately. Source a part meeting these, then upload its datasheet."),
            "note": ("For a CCM boost PFC a SiC Schottky is the usual choice: it has no "
                     "minority-carrier reverse recovery, which is otherwise the largest single "
                     "loss term in the MOSFET. Either technology is calculated correctly - the "
                     "recovery model follows the technology read off the datasheet, not the tab "
                     "the file happened to be uploaded under."),
        }

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
        "plausibility": screen(profile, device_class),
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


# ── the plotted curves (M7) ───────────────────────────────────────────────────────────────────
# Everything a table cannot carry has been standing in as a fitted shape: a constant forward drop
# where the datasheet gives V_F at one current per temperature (C210), a Q_c moved to the bus by an
# assumed power law (C211), a V^1.5 E_oss through a single point (C208). All of it is printed on
# the page, in the figures.
#
# A proposal is matched to a canonical key by what the AXES say, not by figure number: "Fig. 1" is a
# forward-voltage plot on one vendor's datasheet and a surge curve on another's, while an axis
# titled "VF - Forward Voltage Drop (V)" against "IF - Instantaneous Forward Current (A)" is the
# same plot everywhere.

# THE CANONICAL KEY NAMES ITS OWN ORIENTATION, AND THE PLOT NEED NOT AGREE. `V_F_vs_IF` is V_F as
# a function of I_F, so its x is CURRENT — but every vendor plots that figure the other way up, with
# voltage on the x axis. Emitting the figure's own order put voltage where the engine reads current
# and produced -692 W of conduction loss and a junction at -645 degC. `swap` is the fix, and it is
# declared per target rather than inferred, because a silent transpose is exactly the kind of thing
# that reads as plausible until something is negative.
_FIGURE_TARGETS = [
    # canonical key,   x axis matches,        y axis matches,            per-temp, swap
    ("V_F_vs_IF",      ("forward voltage",),  ("forward current",),      True,     True),
    ("Q_c_vs_VR",      ("reverse voltage",),  ("capacitive charge",),    False,    False),
    ("E_c_vs_VR",      ("reverse voltage",),  ("capacitive energy",),    False,    False),
    ("C_j_vs_VR",      ("reverse voltage",),  ("junction capacitance",), False,    False),
    ("I_rev_vs_VR",    ("reverse voltage",),  ("reverse current",),      True,     False),
]


def _axis_matches(title: str, wants: tuple) -> bool:
    t = (title or "").lower()
    return any(w in t for w in wants)


def figure_proposals(pdf_bytes: bytes, profile: Optional[dict] = None) -> dict:
    """Digitise every plot and offer the ones this calculation can actually use.

    Each proposal carries its own evidence: the axis titles it read, the calibration residual, and
    where possible a CROSS-CHECK against a value the same datasheet tabulates. The table and the
    plot are independent renderings of one measurement, so their agreement is what says the axes
    were read correctly — and a proposal that fails it is returned marked, never quietly used.
    """
    from app.mode_b.semiconductor import curve_extract as CX

    try:
        res = CX.digitise(pdf_bytes)
    except Exception as e:
        return {"ok": False, "reason": f"the figures could not be read: {e}", "proposals": []}

    out = []
    for fig in res["figures"]:
        cal = fig["calibration"]
        if not cal["ok"] or not fig["curves"]:
            continue
        tx, ty = cal["titles"]["x"], cal["titles"]["y"]
        for key, wx, wy, per_temp, swap in _FIGURE_TARGETS:
            if not (_axis_matches(tx, wx) and _axis_matches(ty, wy)):
                continue
            curves = fig["curves"]
            if swap:
                curves = [_swap_axes(c) for c in curves]
            p = {
                "key": key, "page": fig["page"], "frame": fig["frame"],
                "caption": fig["caption"], "axes": cal["titles"],
                "x_scale": cal["x"]["scale"], "y_scale": cal["y"]["scale"],
                "x_range": cal["x"]["range"], "y_range": cal["y"]["range"],
                "residual": max(cal["x"]["residual"], cal["y"]["residual"]),
                "per_temperature": per_temp,
                "swapped": swap,
                "n_curves": len(curves),
                "curves": curves,
            }
            # the cross-check runs on the FIGURE's own orientation, which is how the table states it
            p["cross_check"] = _figure_cross_check(key, fig["curves"], profile)
            out.append(p)
            break
    return {"ok": True, "proposals": out, "figures_seen": len(res["figures"])}


def _swap_axes(curve: dict) -> dict:
    """Return the curve with x and y exchanged, re-sorted on the new x."""
    pts = sorted(zip(curve["y"], curve["x"]))
    out = dict(curve)
    out["x"] = [round(a, 6) for a, _ in pts]
    out["y"] = [round(b, 6) for _, b in pts]
    out["x_span"] = [min(out["x"]), max(out["x"])]
    out["y_span"] = [min(out["y"]), max(out["y"])]
    return out


def _figure_cross_check(key: str, curves: list, profile: Optional[dict]) -> dict:
    """Hold the digitised curves against a point the datasheet's own TABLE states."""
    from app.mode_b.semiconductor import curve_extract as CX

    if not profile:
        return {"checked": False, "agrees": False,
                "note": "no confirmed table values to check the figure against"}
    if key == "V_F_vs_IF":
        pts = _vf_points(profile, hot=False)
        if pts:
            i_f, v_f, _t = pts[-1]
            return CX.cross_check(curves, v_f, i_f)
    if key == "Q_c_vs_VR":
        e = _pick_entry(_entries_of(profile, "Q_c"))
        vr = ((e or {}).get("conditions") or {}).get("V_R")
        q = (e or {}).get("typ") or (e or {}).get("max")
        if vr and q:
            return CX.cross_check(curves, float(vr), float(q) * 1e9)   # the plot is in nC
    if key == "C_j_vs_VR":
        for e in _entries_of(profile, "C_j"):
            vr = (e.get("conditions") or {}).get("V_R")
            c = e.get("typ") or e.get("max")
            if vr and c and float(vr) > 1:
                return CX.cross_check(curves, float(vr), float(c) * 1e12)   # pF
    return {"checked": False, "agrees": False,
            "note": "this datasheet tabulates no value on this figure's axes, so the digitised "
                    "curve cannot be checked against the part's own numbers"}


def confirm_figure(part_number: str, key: str, curve: dict, conditions: Optional[dict] = None,
                   reviewed_by: str = "designer", root: Optional[str] = None) -> dict:
    """Write a curve the designer accepted, against the plot, into the confirmed profile.

    Stamped `digitised`, which is its own provenance: a shape read off a picture is neither a table
    value nor a fit, and the report has to be able to say so. Everything else about it is ordinary —
    it lands in the same profile, under a canonical key, and the engine picks it up from there.
    """
    R.get(key)                                       # unknown canonical key raises, by design
    profile = (PS.load_profile(part_number, kind="confirmed", root=root)
               or PS.load_profile(part_number, kind="extracted", root=root))
    if profile is None:
        raise PS.PartsStoreError(f"no profile on file for {part_number!r}; upload the datasheet first")
    profile = dict(profile)

    entry = {"typ": [list(curve["x"]), list(curve["y"])],
             "provenance": "digitised",
             "conditions": dict(conditions or {}),
             "source": {"figure": curve.get("caption"), "page": curve.get("page")},
             "n_points": len(curve["x"])}
    for p in profile.setdefault("parameters", []):
        if p["key"] == key:
            p["entries"] = [e for e in p["entries"] if e.get("provenance") != "digitised"]
            p["entries"].append(entry)
            break
    else:
        profile["parameters"].append({"key": key, "entries": [entry]})

    written = PS.write_confirmed(part_number, profile, reviewed_by=reviewed_by, root=root)
    return {"ok": True, "part_number": part_number, "key": key, "written": written,
            "n_points": entry["n_points"]}


# A forward drop outside this band is not a forward drop. Silicon sits near 0.7 V, SiC near 1.5,
# and nothing conducts usefully above a few volts — so a curve that leaves it has been misread,
# and the commonest way is to have x and y the wrong way round.
_VF_PLAUSIBLE_V = (0.2, 8.0)


def _plausible_vf_curve(curve: dict) -> bool:
    ys = curve.get("y") or []
    xs = curve.get("x") or []
    if not ys or not xs:
        return False
    lo, hi = _VF_PLAUSIBLE_V
    return lo <= min(ys) and max(ys) <= hi and min(xs) >= 0.0


def _digitised(profile: dict, key: str) -> Optional[dict]:
    """The confirmed digitised curve for a key, as {'x': [...], 'y': [...]}, or None."""
    for e in _entries_of(profile, key):
        if e.get("provenance") == "digitised" and isinstance(e.get("typ"), (list, tuple)):
            xy = e["typ"]
            if len(xy) == 2 and xy[0] and xy[1]:
                return {"x": list(xy[0]), "y": list(xy[1]), "conditions": e.get("conditions") or {}}
    return None


def _curve_at(curve: dict, x: float) -> Optional[float]:
    xs, ys = curve["x"], curve["y"]
    if not xs or x < xs[0] or x > xs[-1]:
        return None
    for (xa, ya), (xb, yb) in zip(zip(xs, ys), zip(xs[1:], ys[1:])):
        if xa <= x <= xb:
            return ya if xb == xa else ya + (yb - ya) * (x - xa) / (xb - xa)
    return ys[-1]


# ── the plausibility screen (M6) ──────────────────────────────────────────────────────────────
# The C202 gate was built against the vendor catalogues and then reachable only through its own
# endpoint, so the one path where a number arrives with NO vendor behind it - a machine reading a
# PDF - was the one path it never saw. Extraction fails in exactly the shapes these rules catch: a
# decimal point off, a value taken from the neighbouring column, a unit read as milli instead of
# nano.
#
# ADVISORY, ALWAYS. It returns findings and never a rejection, and it cannot block an upload or a
# confirmation. `ok: true` means nothing looked wrong, not that the extraction is right.

_PLAUSIBILITY_KIND = {"Mosfet": "mosfet", "Diode": "diode", "Bridge": "bridge"}


def plausibility_record(profile: dict, device_class: str) -> dict:
    """Build a part RECORD, in the shape the C202 rules read, from a canonical profile.

    The field names come from the registry (`db_field` / `meta_field`), never from a table written
    here — that is the whole reason the rules can be shared with the catalogue path at all.
    """
    rec: dict[str, Any] = {}
    for p in R.parameters(device_class):
        key = p["key"]
        if not (p.get("db_field") or p.get("meta_field")):
            continue
        entries = _entries_of(profile, key)
        if not entries:
            continue
        # The record must sit in the same population as a catalogue row, or the bands do not apply.
        # Both of these are quoted at 25 degC in every parametric export while a datasheet also
        # publishes them hot, and `_pick_entry` prefers whichever entry carries the most conditions
        # — usually the hot one. So prefer a cold entry, and pick DETERMINISTICALLY among several.
        #
        # This is an order-of-magnitude screen, not an operating point: a SiC part publishes
        # R_DS(on) at three gate voltages (30, 33, 43 mOhm here) and any of them screens the same.
        # What matters is that the choice cannot change with dictionary ordering.
        # A CORRECTED value outranks everything. The screen exists to catch a hand-entered slip,
        # and a part publishing R_DS(on) at three gate voltages would otherwise hide one: taking
        # the smallest of 30, 33, 43 mOhm still returns 30 after the designer typed 330.
        edited = [e for e in entries
                  if (e.get("provenance") or "extracted") in ("corrected", "manual")]
        entries = edited or entries
        cold = [e for e in entries if ((e.get("conditions") or {}).get("T_j") or 25) < 100]
        if key == "V_F_vs_IF":
            # a forward-drop CURVE has no single value; the catalogue's `vf` is the drop at the
            # rated current, so take the coldest, highest-current published point
            pick = max(cold or entries,
                       key=lambda e: (e.get("conditions") or {}).get("I_F") or 0)
        elif key == "R_DS_on" and cold:
            pick = min(cold, key=lambda e: e.get("typ") or e.get("max") or float("inf"))
        else:
            pick = _pick_entry(entries)
        val = (pick or {}).get("typ")
        if val is None:
            val = (pick or {}).get("max")
        if val is None:
            val = (pick or {}).get("min")
        if isinstance(val, (int, float)):
            rec.update(R.to_record_fields({key: float(val)}))
    return rec


def screen(profile: dict, device_class: str) -> dict:
    """Run the plausibility gate over an extracted or confirmed profile. Never raises."""
    from app import plausibility

    try:
        cls = R.device_class(device_class)
        kind = _PLAUSIBILITY_KIND.get(cls.get("engine_dataclass") or "")
        if not kind:
            return {"ok": True, "findings": [], "checked": 0, "record": {},
                    "note": f"no plausibility rules for {device_class!r}"}
        rec = plausibility_record(profile, device_class)
        res = plausibility.check(kind, rec)
        res["record"] = rec
        res["advisory"] = True
        return res
    except Exception as e:                       # a screen must never break an upload
        return {"ok": True, "findings": [], "checked": 0, "record": {},
                "note": f"plausibility screen unavailable: {e}"}


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
    # diode
    "V_RRM": "blocking requirement", "I_F_AV": "current requirement",
    "V_F_vs_IF": "conduction loss", "V_F_vs_IF_hot": "hot conduction loss",
    "r_d": "conduction loss slope", "is_sic": "which recovery model applies",
    "Q_c": "charge dumped into the MOSFET at turn-on",
    "Q_rr": "recovery loss, split between MOSFET and diode",
    "t_rr": "reverse-recovery charge when Q_rr is not published",
    "I_RRM": "reverse-recovery charge when Q_rr is not published",
    "Q_rr_vs_didt": "recovery charge at the design's di/dt",
    "Q_rr_vs_IF": "recovery charge at the design's forward current",
    "rr_fet_frac": "how the recovery energy splits", "E_fr": "forward-recovery loss",
    "I_rev_vs_Tj": "blocking (leakage) loss",
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
    # Screened AGAIN after confirmation, not only on upload: a designer correcting a value is
    # exactly when a new decimal slip can enter, and it is the confirmed profile the engine runs on.
    return {"ok": True, "part_number": part_number, "written": written,
            "plausibility": screen(profile, device_class),
            "rows": review_rows(profile, device_class)}


# ── profile -> engine block ───────────────────────────────────────────────────────────────────
def profile_to_block(profile: dict, device_class: str, design: dict) -> dict:
    """Turn a confirmed profile into an engine block, routed by the class's engine dataclass.

    The route comes from the REGISTRY (`engine_dataclass`), not from a string test on the class
    name, so adding a class cannot silently fall through to the MOSFET builder.
    """
    cls = R.device_class(device_class)
    engine = cls.get("engine_dataclass")
    # EXPLICIT, and no default. The docstring above used to promise that adding a class could not
    # fall through to the MOSFET builder while the code did exactly that for anything that was not
    # a Diode — so a bridge profile went to `_mosfet_block` and was searched for R_DS(on) and gate
    # charge. Nothing had hit it only because the bridge had no upload path.
    builder = {"Mosfet": _mosfet_block, "Diode": _diode_block, "Bridge": _bridge_block}.get(engine)
    if builder is None:
        raise R.RegistryError(
            f"device class {device_class!r} has engine_dataclass {engine!r}, which has no block "
            f"builder. Add one rather than letting it default: the builders read different "
            f"parameters, so the wrong one produces a block that is confidently empty.")
    return builder(profile, device_class, design, cls)


def _mosfet_block(profile: dict, device_class: str, design: dict, cls: dict) -> dict:
    """`select()` is what earns its keep here: the on-resistance handed to the engine is the entry
    at the design's OWN gate-drive voltage, not whichever entry parsed first. Ask for a condition
    the datasheet does not state and it raises rather than substituting a neighbour.
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

    blk["tech"] = "sic" if "sic" in device_class else "si"
    prov["device_class"] = "extracted"

    for key in ("V_GS_drive", "R_g_on", "R_g_off", "R_g_common", "R_th_cs", "sw_method"):
        val = design.get(key)
        if val not in (None, ""):
            put(key, val, "manual")

    blk[M.PROVENANCE_KEY] = prov
    blk["_conduction_form"] = cls["conduction_loss_form"]

    # M4b: anchor the switching model on the published energies. Done LAST, because it needs the
    # rest of the block (E_oss, Q_gd, C_iss) already in place to evaluate the analytic baseline.
    anchor = switching_anchor(profile, blk, design)
    blk["_switching_anchor"] = anchor
    if anchor.get("ok"):
        blk["k_esw"] = anchor["k_esw"]
        blk["k_turnoff"] = anchor["k_turnoff"]
        prov["k_esw"] = "derived"
        prov["k_turnoff"] = "derived"

    blk["_checks"] = _mosfet_checks(profile, design, blk)
    return blk


def _mosfet_checks(profile: dict, design: dict, blk: dict) -> list[dict]:
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




# ── diode: technology, and why it must never be defaulted ─────────────────────────────────────
# Q_c(V) = integral of C_j dV. For an abrupt Schottky junction C_j falls as V^-0.5, so the charge
# rises as V^0.5. Used only when the datasheet states Q_c at ONE reverse voltage; with two or more
# the exponent is fitted from the part's own numbers instead.
SCHOTTKY_QC_EXPONENT = 0.5


def resolve_technology(profile: dict, device_class: str) -> dict:
    """SiC Schottky or silicon? The one diode decision that must not fall back to a default.

    `Diode.is_sic` defaults to True, and the two branches are completely different physics: SiC
    dumps a fixed capacitive charge Q_c into the MOSFET, silicon dumps a current- and di/dt-
    dependent recovery charge Q_rr that is several times larger. Get it wrong and the largest single
    term in the whole chapter is computed by the wrong formula, silently.

    THE DATASHEET OUTRANKS THE TAB. The device class arrives from whichever sub-tab the file was
    uploaded under, and that defaults to `sic_schottky` for every diode — it is a UI default, not an
    assertion by the designer. So published evidence wins when it is unambiguous, and the override
    is reported rather than made quietly.
    """
    def has(key):
        return any((e.get("typ") is not None or e.get("max") is not None)
                   for e in _entries_of(profile, key))

    declared = "sic" in device_class or "schottky" in device_class
    stated = _pick_entry(_entries_of(profile, "is_sic"))
    qc, qrr = has("Q_c"), (has("Q_rr") or has("t_rr") or has("I_RRM"))

    if stated is not None and stated.get("typ") is not None:
        is_sic = bool(stated.get("typ"))
        basis, prov = "stated on the datasheet", "extracted"
    elif qc and not qrr:
        is_sic, basis, prov = True, "the datasheet publishes a capacitive charge Q_c and no reverse-recovery charge", "derived"
    elif qrr and not qc:
        is_sic, basis, prov = False, "the datasheet publishes a reverse-recovery charge (Q_rr, t_rr or I_RRM) and no Q_c", "derived"
    elif qc and qrr:
        is_sic, basis, prov = declared, "the datasheet publishes BOTH Q_c and a recovery charge, so the uploaded class decides", "manual"
    else:
        is_sic, basis, prov = declared, "the datasheet publishes neither Q_c nor a recovery charge, so the uploaded class decides", "manual"

    return {
        "is_sic": bool(is_sic),
        "provenance": prov,
        "basis": basis,
        "declared": declared,
        "override": bool(is_sic) != bool(declared),
        "ambiguous": prov == "manual",
        "evidence": {"has_Q_c": qc, "has_recovery_charge": qrr,
                     "stated_is_sic": (stated or {}).get("typ")},
    }


def _cj_grading(profile: dict) -> Optional[dict]:
    """Fit m in C_j(v) = C0*v^-m from the two capacitance points vendors publish.

    This one number does two jobs that were both being assumed:
      - Q_c scales between the published reverse voltage and the bus as V^(1-m), where the flow
        had been assuming an abrupt-junction 0.5.
      - the share of the capacitive charge DISSIPATED in the MOSFET rather than stored is
        1/(2-m); the engine had been using 0.5, which is the LINEAR-capacitor value (m = 0).

    No curve digitising is needed: Vishay and Toshiba both state C_j at 1 V and at the rated V_R,
    and those two points pin m. Checked against the published Q_c on three real parts, the fitted
    power law reproduces it to within 3-6 %.
    """
    pts = []
    for e in _entries_of(profile, "C_j"):
        c = e.get("typ") or e.get("max")
        vr = (e.get("conditions") or {}).get("V_R")
        if c and vr:
            pts.append((float(vr), float(c)))
    pts = sorted(set(pts))
    if len(pts) < 2:
        return None
    (v1, c1), (v2, c2) = pts[0], pts[-1]
    if v1 <= 0 or v2 <= v1 or c1 <= 0 or c2 <= 0:
        return None
    m = -math.log(c2 / c1) / math.log(v2 / v1)
    if not (0.0 <= m <= 0.95):                    # outside this a junction model does not apply
        return {"m": None, "rejected": round(m, 4), "from": [(v1, c1), (v2, c2)]}
    return {"m": round(m, 4), "from": [(v1, c1), (v2, c2)],
            "qc_factor": round(1.0 / (2.0 - m), 4),
            "note": (f"The junction grading coefficient m = {m:.3f} is fitted from this part's own "
                     f"two published capacitance points ({c1*1e12:.0f} pF at {v1:g} V and "
                     f"{c2*1e12:.0f} pF at {v2:g} V). It sets the Q_c voltage scaling as "
                     f"V^{1-m:.3f} and the dissipated share of the capacitive charge as "
                     f"1/(2-m) = {1/(2-m):.3f}, against the 0.500 a linear capacitor would give.")}


def _qc_at_bus(profile: dict, v_bus: float, m: Optional[float] = None) -> Optional[dict]:
    """Move the published capacitive charge to the voltage the engine actually uses it at.

    The engine spends 0.5*V_bus*Q_c at every MOSFET turn-on, so Q_c has to be the charge at V_bus.
    Vendors publish it at whatever reverse voltage they chose - commonly 400 V or 600 V - and using
    a 600 V figure on a 393 V bus overstates the term by about 25 %.
    """
    pts = []
    for e in _entries_of(profile, "Q_c"):
        q = e.get("typ") or e.get("max")
        vr = (e.get("conditions") or {}).get("V_R")
        if q:
            pts.append((float(vr) if vr else None, float(q)))
    if not pts:
        return None

    known = sorted({(v, q) for v, q in pts if v})
    if not known:                                   # published, but at no stated voltage
        return {"qc": pts[0][1], "provenance": "extracted", "scaled": False,
                "note": ("The datasheet states Q_c without a reverse voltage, so it is used as "
                         "published. If it was measured at a voltage well away from the bus, the "
                         "turn-on term carries that error.")}

    if len(known) >= 2:                             # the part's OWN exponent, not an assumed one
        (v1, q1), (v2, q2) = known[0], known[-1]
        m = math.log(q2 / q1) / math.log(v2 / v1)
        q_bus = q1 * (v_bus / v1) ** m
        return {"qc": q_bus, "provenance": "derived", "scaled": True, "exponent": round(m, 4),
                "fitted": True, "from": {"V_R": v1, "Q_c": q1}, "V_bus": v_bus,
                "note": (f"Q_c scaled from {q1*1e9:.1f} nC at {v1:.0f} V to {q_bus*1e9:.1f} nC at "
                         f"the {v_bus:.0f} V bus, using the exponent {m:.2f} fitted from this "
                         f"part's own two published points.")}

    v1, q1 = known[0]
    if m is not None:                               # the part's OWN exponent, from its C-V points
        exp = 1.0 - m
        q_bus = q1 * (v_bus / v1) ** exp
        if abs(v_bus - v1) / v1 < 0.02:
            return {"qc": q1, "provenance": "extracted", "scaled": False,
                    "from": {"V_R": v1, "Q_c": q1}, "exponent": round(exp, 4), "fitted": True,
                    "note": (f"Q_c is published at {v1:.0f} V and the bus is {v_bus:.0f} V - within "
                             f"2 %, so it is used as stated.")}
        return {"qc": q_bus, "provenance": "derived", "scaled": True, "exponent": round(exp, 4),
                "fitted": True, "from": {"V_R": v1, "Q_c": q1}, "V_bus": v_bus,
                "note": (f"Q_c scaled from {q1*1e9:.1f} nC at {v1:.0f} V to {q_bus*1e9:.1f} nC at "
                         f"the {v_bus:.0f} V bus as V^{exp:.3f}, the exponent implied by this "
                         f"part's own capacitance points rather than an assumed 0.5.")}
    if abs(v_bus - v1) / v1 < 0.02:                 # within rounding of the bus; scaling is noise
        return {"qc": q1, "provenance": "extracted", "scaled": False, "from": {"V_R": v1, "Q_c": q1},
                "note": (f"Q_c is published at {v1:.0f} V and the bus is {v_bus:.0f} V - within 2 %, "
                         f"so it is used as stated. Scaling across that gap would move the charge "
                         f"by under 1 %, which is smaller than the value's own tolerance.")}
    q_bus = q1 * (v_bus / v1) ** SCHOTTKY_QC_EXPONENT
    return {"qc": q_bus, "provenance": "derived", "scaled": True,
            "exponent": SCHOTTKY_QC_EXPONENT, "fitted": False,
            "from": {"V_R": v1, "Q_c": q1}, "V_bus": v_bus,
            "note": (f"Q_c is published at {v1:.0f} V but the engine spends it at the "
                     f"{v_bus:.0f} V bus, so it is scaled to {q_bus*1e9:.1f} nC (from "
                     f"{q1*1e9:.1f} nC) as V^{SCHOTTKY_QC_EXPONENT:g} - the abrupt-junction "
                     f"result, not a fit to this part. A second published point would replace "
                     f"the exponent with this part's own.")}


def _vf_points(profile: dict, hot: bool) -> list[tuple]:
    """(I_F, V_F) pairs at 25 degC, or at the hot measurement temperature."""
    pts = []
    for e in _entries_of(profile, "V_F_vs_IF"):
        c = e.get("conditions") or {}
        i, v = c.get("I_F"), (e.get("typ") or e.get("max"))
        if i is None or v is None:
            continue
        tj = c.get("T_j")
        if (tj is not None and float(tj) >= 100.0) == hot:
            pts.append((float(i), float(v), float(tj) if tj is not None else None))
    return sorted(pts)


def _vf_curve_from(pts: list[tuple], rd: Optional[float], i_max: float):
    """Build the engine's V-I curve, and say how much of it was measured.

    A single published point is a real limitation, not a curve: a boost diode swings from zero to
    tens of amps, and a flat V_F understates conduction loss at the peak. With r_d the two together
    ARE the datasheet's own linear model, so that case is exact rather than assumed.
    """
    if len(pts) >= 2:
        return ([p[0] for p in pts], [p[1] for p in pts]), "extracted", None
    if len(pts) == 1 and rd:
        i1, v1 = pts[0][0], pts[0][1]
        v0 = v1 - rd * i1                                  # the datasheet's own threshold
        hi = max(i1 * 1.5, i_max * 1.5, i1 + 1.0)
        return ([0.0, hi], [max(v0, 0.0), v0 + rd * hi]), "derived", (
            "note",
            f"V_F is published at a single current ({i1:g} A). Combined with the published slope "
            f"r_d = {rd*1e3:.1f} mOhm it gives the datasheet's own linear model "
            f"V_F(i) = {v0:.3f} + {rd*1e3:.1f}m*i, which is used over 0-{hi:.0f} A.")
    if len(pts) == 1:
        i1, v1 = pts[0][0], pts[0][1]
        return ([i1], [v1]), "extracted", (
            "check",
            f"V_F is published at a single current ({i1:g} A) with no slope r_d, so the forward "
            f"drop is treated as CONSTANT at {v1:g} V — the value quoted at the part's RATED "
            f"current. A boost diode's current swings from zero to tens of amps and spends most of "
            f"the line cycle well below its rating, so a constant rated-current drop OVERSTATES "
            f"conduction over most of the cycle and understates it only at the peak. Measured on "
            f"this part the net effect is an 18 % overstatement. Supply r_d, a second V_F point, or "
            f"digitise the V-I curve (M7).")
    return None, None, None


def _diode_block(profile: dict, device_class: str, design: dict, cls: dict) -> dict:
    """Turn a confirmed diode profile into a `Diode` engine block.

    Both technologies are built here and neither is privileged: the technology is resolved from the
    datasheet, and only the fields that technology actually uses are populated. A SiC block carries
    no Q_rr and a silicon block carries no Q_c, so a wrong branch cannot quietly read a stale field.
    """
    v_bus = float(design.get("vout") or design.get("Vbus_V") or 0.0)
    blk: dict[str, Any] = {
        "manufacturer": profile.get("manufacturer"),
        "part_number": profile.get("part_number"),
        M.SOURCE_KEY: f"datasheet {profile.get('datasheet', {}).get('filename', '')}"
                      f" (sha {str(profile.get('datasheet', {}).get('sha256', ''))[:12]})",
    }
    prov: dict[str, str] = {}
    notes: list[dict] = []

    def put(key, value, how="extracted"):
        if value is None:
            return
        blk.update(R.expand_to_engine_fields({key: value}))
        prov[key] = how

    # 1. technology FIRST — every branch below depends on it
    tech = resolve_technology(profile, device_class)
    put("is_sic", tech["is_sic"], tech["provenance"])
    blk["_technology"] = tech

    # 2. conduction. The peak current sets how far the V-I curve has to reach.
    i_max = 0.0
    try:
        from app.mode_b.semiconductor.adapter import build_design_ops
        _, s2, *_ = build_design_ops(design)
        i_max = float(max(s2["Iin_pk"])) / max(int(design.get("nch") or 1), 1)
    except Exception:
        pass

    rd_e = _pick_entry(_entries_of(profile, "r_d"))
    rd = float(rd_e.get("typ") or rd_e.get("max")) if rd_e and (rd_e.get("typ") or rd_e.get("max")) else None

    # A DIGITISED forward curve outranks everything the table can give. On this part the table
    # publishes V_F at ONE current per temperature, so without the plot the drop is a constant
    # (C210) and conduction is understated at the current peak.
    dig_vf = _digitised(profile, "V_F_vs_IF")
    if dig_vf and not _plausible_vf_curve(dig_vf):
        notes.append({"key": "V_F_vs_IF", "severity": "check", "message": (
            f"The digitised forward curve is not being used: its drop spans "
            f"{min(dig_vf['y']):.2g} to {max(dig_vf['y']):.2g} V, which is not a diode forward "
            f"characteristic. The usual cause is a TRANSPOSED curve — the canonical key is V_F as a "
            f"function of I_F, so its x is current, while every vendor plots that figure with "
            f"voltage on the x axis. The tabulated values are used instead.")})
        dig_vf = None
    if dig_vf:
        put("V_F_vs_IF", [list(dig_vf["x"]), list(dig_vf["y"])], "digitised")
        tj = (dig_vf.get("conditions") or {}).get("T_j")
        if tj:
            put("V_F_tref", float(tj))
        notes.append({"key": "V_F_vs_IF", "severity": "note", "message": (
            f"The forward drop is the curve read off the datasheet's own plot and confirmed by the "
            f"designer ({len(dig_vf['x'])} points), not a line through the tabulated point. That "
            f"approximation held the drop at the value quoted for the RATED current, which the "
            f"diode exceeds only at the crest — so it overstated conduction over most of the line "
            f"cycle, by 18 % on this part.")})

    cold = _vf_points(profile, hot=False)
    hot = _vf_points(profile, hot=True)
    cv, how, note = _vf_curve_from(cold, rd, i_max)
    if cv and not dig_vf:
        put("V_F_vs_IF", [list(cv[0]), list(cv[1])], how)
        if cold and cold[0][2]:
            put("V_F_tref", cold[0][2])
    if note and not dig_vf:
        notes.append({"key": "V_F_vs_IF", "severity": note[0], "message": note[1]})

    # r_d REACHES THE ENGINE ONLY WHEN NO V-I CURVE DID. The engine's forward model is
    #     v(i) = vf_curve(i) + rd*i
    # and every curve built above already carries the slope — from two published points directly, or
    # from one point plus this same r_d. Writing both counted the resistive term TWICE: measured at
    # 12.8 % on the diode's conduction loss (5.86 W against 5.20 W). The published value is still
    # kept, as metadata, because it is what built the curve and the report has to be able to say so.
    if rd is not None:
        if cv is None:
            put("r_d", rd)
        else:
            blk["_r_d_published"] = rd

    dig_hot = _digitised(profile, "V_F_vs_IF_hot")
    # The engine interpolates the forward drop BETWEEN the cold and hot curves, so the two have to
    # be the same kind of object. Digitising one and leaving the other as a single tabulated point
    # interpolates a 300-point shape against a flat line, and the result is neither: measured on the
    # reference part, digitising the cold curve alone recovers 4 % of the conduction error where
    # digitising both recovers 18 %.
    if bool(dig_vf) != bool(dig_hot):
        notes.append({"key": "V_F_vs_IF_hot", "severity": "check", "message": (
            f"Only the {'cold' if dig_vf else 'hot'} forward curve has been digitised. The engine "
            f"interpolates the drop between the two temperatures, so pairing a digitised shape with "
            f"a single tabulated point at the other temperature interpolates a curve against a flat "
            f"line. Digitise both curves from the same figure — most V-I plots draw every "
            f"temperature — or neither.")})
    if dig_hot:
        put("V_F_vs_IF_hot", [list(dig_hot["x"]), list(dig_hot["y"])], "digitised")
        tj = (dig_hot.get("conditions") or {}).get("T_j")
        put("V_F_thot", float(tj) if tj else 125.0)
    else:
        hv, hhow, _hnote = _vf_curve_from(hot, rd, i_max)
        if hv and len(hot) >= 1:
            put("V_F_vs_IF_hot", [list(hv[0]), list(hv[1])], hhow)
            put("V_F_thot", hot[0][2] or 125.0)

    # 3. recovery — the branch that is half the MOSFET's loss
    grading = _cj_grading(profile)
    m = (grading or {}).get("m")
    # A digitised C_j curve fits the grading coefficient over the WHOLE plotted range, instead of
    # interpolating between the two tabulated dots.
    dig_cj = _digitised(profile, "C_j_vs_VR")
    if dig_cj and len(dig_cj["x"]) >= 4:
        xs, ys = dig_cj["x"], dig_cj["y"]
        lo, hi = 0, len(xs) - 1
        if xs[lo] > 0 and xs[hi] > xs[lo] and ys[lo] > 0 and ys[hi] > 0:
            m_fit = -math.log(ys[hi] / ys[lo]) / math.log(xs[hi] / xs[lo])
            if 0.0 <= m_fit <= 0.95:
                m = round(m_fit, 4)
                grading = {"m": m, "qc_factor": round(1.0 / (2.0 - m), 4), "from_curve": True,
                           "note": (f"The grading coefficient m = {m:.3f} is fitted across the "
                                    f"digitised C_j(V_R) curve ({len(xs)} points), not between the "
                                    f"two tabulated capacitance values.")}
    if m is not None:
        put("C_j_grading", m, "derived")
        blk["_cj_basis"] = grading
    if tech["is_sic"]:
        dig_qc = _digitised(profile, "Q_c_vs_VR")
        read = _curve_at(dig_qc, v_bus) if dig_qc else None
        if read is not None:
            # Read AT THE BUS off the plot: no power law, no assumed exponent, no scaling at all.
            qc = {"qc": read * 1e-9, "provenance": "digitised", "scaled": False, "from_curve": True,
                  "note": (f"Q_c = {read:.1f} nC is read directly off the datasheet's Q_c(V_R) plot "
                           f"at the {v_bus:.0f} V bus, so the published value is not scaled at all "
                           f"— neither by an assumed exponent nor by one fitted from two points.")}
        else:
            qc = _qc_at_bus(profile, v_bus, m)
        if qc:
            put("Q_c", qc["qc"], qc["provenance"])
            blk["_qc_basis"] = qc
            if qc.get("scaled"):
                notes.append({"key": "Q_c", "severity": "note", "message": qc["note"]})
        else:
            notes.append({"key": "Q_c", "severity": "check", "message": (
                "No capacitive charge Q_c could be read from this datasheet. It is the entire "
                "turn-on penalty a SiC diode imposes on the MOSFET, so without it that term falls "
                "back to the engine default and is not this part's number. Enter it from the "
                "datasheet's dynamic-characteristics table.")})
    else:
        qrr = _qrr_for_design(profile)
        if qrr:
            put("Q_rr", qrr["qrr"], qrr["provenance"])
            blk["_qrr_basis"] = qrr
            if qrr.get("note"):
                notes.append({"key": "Q_rr", "severity": "note", "message": qrr["note"]})
        else:
            notes.append({"key": "Q_rr", "severity": "check", "message": (
                "No reverse-recovery charge could be read from this datasheet - neither Q_rr, nor "
                "t_rr with I_RRM. For a silicon boost diode this is the single largest loss term "
                "in the chapter; without it the engine uses its default and the number is not this "
                "part's.")})

        tco = _qrr_tempco(profile)
        if tco is not None:
            put("Q_rr_tempco", tco, "derived")

    # 4. thermal and leakage
    # A multi-die package publishes R_th_jc TWICE - per leg and per device. The junction sees the
    # PER-LEG figure (the larger one); the per-device number describes the whole package and would
    # halve the predicted rise if it were picked by accident.
    rth_vals = sorted({float(e.get("max") or e.get("typ"))
                       for e in _entries_of(profile, "R_th_jc")
                       if (e.get("max") or e.get("typ"))})
    if rth_vals:
        put("R_th_jc", rth_vals[-1])
        blk["_rth_jc_published"] = rth_vals
    ent = _pick_entry(_entries_of(profile, "E_fr"))
    if ent:
        put("E_fr", ent.get("typ") or ent.get("max"))

    irev = [(float((e.get("conditions") or {}).get("T_j")), float(e.get("typ") or e.get("max")),
             (e.get("conditions") or {}).get("V_R"))
            for e in _entries_of(profile, "I_rev_vs_Tj")
            if (e.get("conditions") or {}).get("T_j") and (e.get("typ") or e.get("max"))]
    if len(irev) >= 2:
        irev.sort()
        put("I_rev_vs_Tj", [[t for t, _, _ in irev], [v for _, v, _ in irev]])
        vrs = {float(v) for _, _, v in irev if v}
        if vrs:
            blk["_irev_at_VR"] = sorted(vrs)

    # dies sharing one package: a DESIGN fact, not a datasheet field
    n_die = design.get("dies_per_package")
    if n_die not in (None, ""):
        put("dies_per_package", int(n_die), "manual")

    # 5. design-sourced, never from any datasheet
    for key in ("R_th_cs", "k_vf", "k_qc", "k_qrr"):
        val = design.get(key)
        if val not in (None, ""):
            put(key, val, "manual")

    resolved = "sic_schottky" if tech["is_sic"] else "si_diode"
    blk[M.PROVENANCE_KEY] = prov
    blk["_conduction_form"] = cls["conduction_loss_form"]
    # The class the block IS, which is not always the sub-tab it arrived under. Everything
    # downstream — required-field validation, the report's provenance table — must use this one,
    # or a silicon part gets audited for a Q_c it should not have.
    blk["_device_class"] = resolved
    blk["_declared_class"] = device_class
    blk["_checks"] = notes + _diode_checks(profile, design, blk, tech)
    return blk


def _bridge_block(profile: dict, device_class: str, design: dict, cls: dict) -> dict:
    """Turn a confirmed bridge profile into a `Bridge` engine block.

    The bridge's conduction model needs no new physics: the engine already integrates the
    current-dependent forward drop over the line cycle, doubles it for the two diodes in series at
    any instant, and derates for imperfect sharing between paralleled packages. What it has been
    missing is DATASHEET NUMBERS - the catalogue supplies a V_f anchor and estimates the curve shape
    and the thermal resistance around it.

    SYNC-BOTTOM IS A SECOND PART. In that topology the bottom two positions are MOSFETs, with their
    own R_DS(on), gate charge and thermal path. Rather than invent a second extractor, the bypass
    FET is an ordinary confirmed MOSFET profile named by the design, and its values are mapped onto
    the bridge's `_bottom` parameters here. One upload path, used twice.
    """
    v_pk = math.sqrt(2.0) * float(design.get("vin_max") or 0.0)
    blk: dict[str, Any] = {
        "manufacturer": profile.get("manufacturer"),
        "part_number": profile.get("part_number"),
        M.SOURCE_KEY: f"datasheet {profile.get('datasheet', {}).get('filename', '')}"
                      f" (sha {str(profile.get('datasheet', {}).get('sha256', ''))[:12]})",
    }
    prov: dict[str, str] = {}
    notes: list[dict] = []

    def put(key, value, how="extracted"):
        if value is None:
            return
        blk.update(R.expand_to_engine_fields({key: value}))
        prov[key] = how

    # 1. conduction — the same curve machinery the diode uses, digitised curve preferred
    i_max = 0.0
    try:
        from app.mode_b.semiconductor.adapter import build_design_ops
        _, s2, *_ = build_design_ops(design)
        i_max = float(max(s2["Iin_pk"]))
    except Exception:
        pass

    rd_e = _pick_entry(_entries_of(profile, "r_d"))
    rd = float(rd_e.get("typ") or rd_e.get("max")) if rd_e and (rd_e.get("typ") or rd_e.get("max")) else None

    dig_vf = _digitised(profile, "V_F_vs_IF")
    if dig_vf and not _plausible_vf_curve(dig_vf):
        notes.append({"key": "V_F_vs_IF", "severity": "check", "message": (
            "The digitised forward curve is not being used: its drop is not a diode forward "
            "characteristic. The usual cause is a transposed curve — the canonical key is V_F as a "
            "function of I_F, so its x is current, while vendors plot it with voltage on x.")})
        dig_vf = None

    if dig_vf:
        put("V_F_vs_IF", [list(dig_vf["x"]), list(dig_vf["y"])], "digitised")
        tj = (dig_vf.get("conditions") or {}).get("T_j")
        if tj:
            put("V_F_tref", float(tj))
    else:
        cold = _vf_points(profile, hot=False)
        cv, how, note = _vf_curve_from(cold, rd, i_max)
        if cv:
            put("V_F_vs_IF", [list(cv[0]), list(cv[1])], how)
            if cold and cold[0][2]:
                put("V_F_tref", cold[0][2])
        if note:
            notes.append({"key": "V_F_vs_IF", "severity": note[0], "message": note[1]})

    dig_hot = _digitised(profile, "V_F_vs_IF_hot")
    if dig_hot:
        put("V_F_vs_IF_hot", [list(dig_hot["x"]), list(dig_hot["y"])], "digitised")
        tj = (dig_hot.get("conditions") or {}).get("T_j")
        put("V_F_thot", float(tj) if tj else 125.0)
    else:
        hot = _vf_points(profile, hot=True)
        hv, hhow, _n = _vf_curve_from(hot, rd, i_max)
        if hv and hot:
            put("V_F_vs_IF_hot", [list(hv[0]), list(hv[1])], hhow)
            put("V_F_thot", hot[0][2] or 125.0)
    if bool(dig_vf) != bool(dig_hot):
        notes.append({"key": "V_F_vs_IF_hot", "severity": "check", "message": (
            f"Only the {'cold' if dig_vf else 'hot'} forward curve has been digitised. The engine "
            f"interpolates the drop between the two temperatures, so pairing a digitised shape with "
            f"a single tabulated point at the other interpolates a curve against a flat line.")})

    # r_d reaches the engine only when no V-I curve did — the curve already carries the slope
    if rd is not None:
        if "vf_curve" not in blk:
            put("r_d", rd)
        else:
            blk["_r_d_published"] = rd

    # 2. thermal — the per-package figure, and the largest published value where several are given
    rth_vals = sorted({float(e.get("max") or e.get("typ"))
                       for e in _entries_of(profile, "R_th_jc")
                       if (e.get("max") or e.get("typ"))})
    if rth_vals:
        put("R_th_jc", rth_vals[-1])
        blk["_rth_jc_published"] = rth_vals

    # 3. recovery — optional for a bridge, and reported as such rather than as a gap
    qrr = _qrr_for_design(profile)
    if qrr:
        put("Q_rr", qrr["qrr"], qrr["provenance"])
        blk["_qrr_basis"] = qrr
    else:
        notes.append({"key": "Q_rr", "severity": "note", "message": (
            "No reverse-recovery charge is published, which is normal for a mains bridge: it "
            "commutates at LINE frequency, so the term is negligible beside conduction and the "
            "engine treats it as a placeholder rather than a model. It is not counted as a gap.")})

    # 3b. the surge figures. Not loss parameters — they are the Chapter 8 inrush and fuse-
    # coordination inputs, and they were being extracted and then dropped because nothing carried
    # them onto the block. `meta_field` is how a non-engine quantity travels.
    # `meta_field` ONLY, not `db_field`. The two are different external names for different
    # audiences: `meta_field` is what the block carries, `db_field` is the vendor catalogue's
    # column. `to_record_fields` returns either, so using it here wrote V_RRM as `vr` — a
    # catalogue name that is not a Bridge field, and Bridge(**params) refused it outright.
    for key in ("I_FSM", "I2t"):
        field = R.get(key).get("meta_field")
        ent = _pick_entry(_entries_of(profile, key))
        val = (ent or {}).get("typ")
        if val is None:
            val = (ent or {}).get("max")
        if field and isinstance(val, (int, float)):
            blk[field] = float(val)
            prov[key] = "extracted"

    # 4. the design's own configuration — none of this is on any datasheet
    topo = design.get("bridge_topology") or design.get("topology") or "diode"
    put("bridge_topology", topo, "manual")
    for key in ("n_parallel", "n_parallel_top", "n_parallel_bottom", "share_worst",
                "R_th_cs", "k_vf", "k_rdson"):
        val = design.get(key)
        if val not in (None, ""):
            put(key, val, "manual")

    # 5. sync-bottom: the bypass FET is an ordinary confirmed MOSFET profile
    if topo == "sync_bottom":
        blk.update(_bottom_fet(design, notes, put))

    resolved = device_class
    blk[M.PROVENANCE_KEY] = prov
    blk["_conduction_form"] = cls["conduction_loss_form"]
    blk["_device_class"] = resolved
    blk["_checks"] = notes + _bridge_checks(profile, design, blk, v_pk)
    return blk


def _bottom_fet(design: dict, notes: list, put) -> dict:
    """Map a confirmed bypass-MOSFET profile onto the bridge's `_bottom` parameters.

    The bottom devices of a sync-bottom bridge are MOSFETs, so they are selected the same way every
    other MOSFET is — requirement, upload, review, confirm — and named here by part number. Reusing
    that path is the difference between one selection flow and two.
    """
    part = design.get("bottom_mosfet_part")
    if not part:
        notes.append({"key": "R_DS_on_bottom", "severity": "check", "message": (
            "The topology is sync_bottom, so the two bottom positions are MOSFETs — but no bypass "
            "MOSFET has been named. Their conduction loss will fall back to the engine's default "
            "R_DS(on), which is not this design's part. Select and confirm the bypass FET on the "
            "MOSFET tab, then name it here.")})
        return {}
    prof = PS.load_profile(part, kind="confirmed") or PS.load_profile(part, kind="extracted")
    if prof is None:
        notes.append({"key": "R_DS_on_bottom", "severity": "check", "message": (
            f"No confirmed profile is on file for the bypass MOSFET {part!r}. Upload and confirm "
            f"its datasheet on the MOSFET tab first.")})
        return {}

    vgs = float(design.get("V_GS_drive_bottom") or design.get("V_GS_drive") or 0.0)
    e = None
    try:
        e = M.select(prof, "R_DS_on", V_GS=vgs, T_j=25) if vgs else None
    except M.MissingParameterError:
        e = None
    e = e or _pick_entry(_entries_of(prof, "R_DS_on"))
    if e:
        put("R_DS_on_bottom", e.get("typ") or e.get("max"), "extracted")
    hot = _hot_entry(prof, vgs)
    if hot and e and e.get("typ"):
        t_hot = (hot.get("conditions") or {}).get("T_j", 175.0)
        put("R_DS_on_bottom_vs_Tj", [[25.0, float(t_hot)],
                                     [1.0, round(float(hot["typ"]) / float(e["typ"]), 4)]], "derived")
    qg = _pick_entry(_entries_of(prof, "Q_g"))
    if qg:
        put("Q_g_bottom", qg.get("typ") or qg.get("max"), "extracted")
    rth = _pick_entry(_entries_of(prof, "R_th_jc"))
    if rth:
        put("R_th_jc_bottom", rth.get("typ") or rth.get("max"), "extracted")
    if vgs:
        put("V_GS_drive_bottom", vgs, "manual")
    if design.get("R_th_cs_bottom") not in (None, ""):
        put("R_th_cs_bottom", design["R_th_cs_bottom"], "manual")
    return {"_bottom_part": part}


def _bridge_checks(profile: dict, design: dict, blk: dict, v_pk: float) -> list[dict]:
    """What the bridge's own numbers cannot say about themselves."""
    out = []
    vr = _pick_entry(_entries_of(profile, "V_RRM"))
    v_rated = float(vr.get("typ") or vr.get("max")) if vr and (vr.get("typ") or vr.get("max")) else None
    if v_rated and v_pk and v_rated < v_pk * DEFAULT_V_MARGIN:
        out.append({"key": "V_RRM", "severity": "check", "message": (
            f"V_RRM = {v_rated:.0f} V is below the {v_pk * DEFAULT_V_MARGIN:.0f} V this design asks "
            f"for ({v_pk:.0f} V line peak at high line x {DEFAULT_V_MARGIN:g}). Note the bridge "
            f"blocks the LINE peak, not the boost bus.")})

    n_par = int(blk.get("n_parallel") or 1)
    if n_par > 1 and blk.get("share_worst") in (None, ""):
        out.append({"key": "share_worst", "severity": "check", "message": (
            f"{n_par} bridge packages are declared in parallel but no sharing derate is given, so "
            f"the calculation assumes they split the current EQUALLY. Paralleled rectifiers do not "
            f"share equally — the hotter one takes more, and its own loss makes it hotter. Chapter "
            f"7.3 reports 50/50, 60/40 and 70/30 alongside the nominal for exactly this reason; "
            f"set the derate to make the assumption explicit rather than implicit.")})

    for key, label in (("I_FSM", "I_FSM"), ("I2t", "I2t")):
        if _entries_of(profile, key):
            out.append({"key": key, "severity": "note", "message": (
                f"{label} is read from the datasheet and used ONLY for the inrush and fuse-"
                f"coordination checks in Chapter 8. It has no part in steady-state conduction "
                f"loss, and is listed here so its absence from the loss table is not mistaken for "
                f"an oversight.")})
    return out


def _qrr_for_design(profile: dict) -> Optional[dict]:
    """The silicon diode's recovery charge, published or reconstructed — with which, recorded."""
    e = _pick_entry(_entries_of(profile, "Q_rr"))
    if e and (e.get("typ") or e.get("max")):
        c = e.get("conditions") or {}
        return {"qrr": float(e.get("typ") or e.get("max")), "provenance": "extracted",
                "conditions": c,
                "note": None if c else (
                    "Q_rr is published without its test conditions. Recovery charge depends "
                    "strongly on forward current, di/dt and junction temperature, so a value "
                    "without them cannot be checked against this design's operating point.")}

    trr = _pick_entry(_entries_of(profile, "t_rr"))
    irm = _pick_entry(_entries_of(profile, "I_RRM"))
    t = float(trr.get("typ") or trr.get("max")) if trr and (trr.get("typ") or trr.get("max")) else None
    i = float(irm.get("typ") or irm.get("max")) if irm and (irm.get("typ") or irm.get("max")) else None
    if t and i:
        return {"qrr": 0.5 * t * i, "provenance": "derived",
                "conditions": (trr.get("conditions") or {}),
                "note": (f"Q_rr is not published. It is reconstructed as 0.5 * t_rr * I_RRM = "
                         f"0.5 * {t*1e9:.0f} ns * {i:.1f} A = {0.5*t*i*1e9:.0f} nC, which assumes "
                         f"a TRIANGULAR recovery waveform. A soft-recovery diode carries more "
                         f"charge than that triangle, so this is a floor rather than a best "
                         f"estimate.")}
    return None


def _qrr_tempco(profile: dict) -> Optional[float]:
    """Fit Q_rr's temperature coefficient when the datasheet states it at two temperatures."""
    pts = []
    for e in _entries_of(profile, "Q_rr"):
        tj = (e.get("conditions") or {}).get("T_j")
        q = e.get("typ") or e.get("max")
        if tj and q:
            pts.append((float(tj), float(q)))
    pts = sorted(set(pts))
    if len(pts) < 2 or pts[0][1] <= 0 or pts[-1][0] == pts[0][0]:
        return None
    (t1, q1), (t2, q2) = pts[0], pts[-1]
    return round((q2 / q1 - 1.0) / (t2 - t1), 6)


def _diode_checks(profile: dict, design: dict, blk: dict, tech: dict) -> list[dict]:
    """What the diode's own numbers cannot say about themselves."""
    out = []
    v_bus = float(design.get("vout") or design.get("Vbus_V") or 0.0)

    if tech["override"]:
        out.append({"key": "is_sic", "severity": "check", "message": (
            f"This file was uploaded as a "
            f"{'SiC Schottky' if tech['declared'] else 'silicon'} diode, but "
            f"{tech['basis']}. The calculation has followed the DATASHEET and treated it as "
            f"{'SiC Schottky' if tech['is_sic'] else 'silicon'}, because the sub-tab carries a "
            f"default and the datasheet carries evidence. The two recovery models differ by "
            f"several times on the largest term in this chapter - confirm which part this is.")})
    elif tech["ambiguous"]:
        out.append({"key": "is_sic", "severity": "check", "message": (
            f"The technology could not be confirmed from the datasheet: {tech['basis']}. It is "
            f"being treated as {'SiC Schottky' if tech['is_sic'] else 'silicon'} on the strength "
            f"of the sub-tab alone, which is a UI default rather than a measurement.")})

    if not tech["is_sic"] and "rr_fet_frac" not in blk:
        out.append({"key": "rr_fet_frac", "severity": "note", "message": (
            "How the recovery energy divides between the MOSFET and the diode is an ASSUMED "
            "partition (85 % to the MOSFET), not a datasheet quantity. It scales the largest "
            "single term in the chapter directly, so it is stated here rather than left silent.")})

    if not tech["is_sic"]:
        basis = blk.get("_qrr_basis") or {}
        c = basis.get("conditions") or {}
        if c.get("diF_dt") or c.get("I_F"):
            bits = []
            if c.get("I_F"):
                bits.append(f"I_F = {float(c['I_F']):g} A")
            if c.get("diF_dt"):
                bits.append(f"di/dt = {float(c['diF_dt']):g} A/us")
            if c.get("T_j"):
                bits.append(f"T_j = {float(c['T_j']):g} degC")
            how = ("is published at" if basis.get("provenance") == "extracted"
                   else "is referenced to")
            out.append({"key": "Q_rr", "severity": "note", "message": (
                f"The recovery charge {how} {', '.join(bits)} and is used at that value. It "
                f"rises with both forward current and di/dt, and this design does not necessarily "
                f"switch at the datasheet's test point - Chapter 7 prints the di/dt actually "
                f"achieved next to this figure. Digitising the Q_rr curves (phase 2) is what "
                f"removes the assumption; scaling a single point by an invented shape would not.")})

    if "irev_curve" not in blk:
        out.append({"key": "I_rev_vs_Tj", "severity": "note", "message": (
            "Diode blocking (leakage) loss is reported as zero because no two-point reverse-current "
            "curve could be built. That is a placeholder, not a measurement. It matters more for "
            "SiC than for silicon: Schottky leakage rises steeply with temperature and reverse "
            "voltage.")})

    if "vf_curve_hot" not in blk:
        out.append({"key": "V_F_vs_IF_hot", "severity": "note", "message": (
            "Only one V-I temperature was found, so the forward drop is corrected by a scalar "
            "tempco. A published hot curve captures the crossover a single coefficient cannot - "
            "the drop falls with temperature at low current and rises at high current.")})

    # ── the capacitive-charge model ───────────────────────────────────────────────────────────
    if tech["is_sic"]:
        if "cj_grading" not in blk:
            out.append({"key": "C_j_grading", "severity": "check", "message": (
                "This datasheet does not give two junction-capacitance points, so the grading "
                "coefficient m could not be fitted and the model falls back to m = 0 - a LINEAR "
                "capacitor, for which the dissipated share of Q_c is exactly the textbook 0.5. Real "
                "junctions run m = 0.33 to 0.5, where the share is 0.60 to 0.67, so the charge "
                "dumped into the MOSFET is understated by roughly a quarter. Two C_j values (one "
                "near 1 V and one at the rated V_R) are enough to remove the assumption entirely - "
                "no curve digitising is needed.")})
        else:
            b = blk.get("_cj_basis") or {}
            out.append({"key": "C_j_grading", "severity": "note", "message": b.get("note", "")})

    # ── leakage is quoted at a reverse voltage that is not the bus ─────────────────────────────
    vrs = blk.get("_irev_at_VR") or []
    if vrs and v_bus:
        far = [v for v in vrs if abs(v - v_bus) / max(v, 1.0) > 0.10]
        if far:
            out.append({"key": "I_rev_vs_Tj", "severity": "note", "message": (
                f"Reverse current is published at V_R = {', '.join(f'{v:.0f}' for v in far)} V, "
                f"not at the {v_bus:.0f} V bus, and it is used as published. Schottky leakage rises "
                f"steeply with reverse voltage, so this is a CONSERVATIVE UPPER BOUND on the "
                f"blocking term rather than its value here. It is not scaled, because the "
                f"barrier-lowering law needs two voltage points to fit and this datasheet gives "
                f"one - and an invented law would look like a correction while being a guess. The "
                f"term is small, so the cost of the bound is small.")})

    # ── a package whose dies share one interface ──────────────────────────────────────────────
    rths = blk.get("_rth_jc_published") or []
    n_die = int(blk.get("dies_per_package") or 1)
    if len(rths) >= 2 and n_die == 1:
        ratio = rths[-1] / rths[0] if rths[0] else 0
        out.append({"key": "dies_per_package", "severity": "check", "message": (
            f"This datasheet publishes R_th_jc twice - {', '.join(f'{r:g}' for r in rths)} K/W, a "
            f"ratio of {ratio:.1f} - which is the signature of a MULTI-DIE package quoting both "
            f"per-leg and per-device figures. The per-leg value ({rths[-1]:g} K/W) is used for the "
            f"junction, which is correct, but the thermal model is still assuming ONE die per "
            f"package, so only one leg's loss passes through the case-to-sink interface. If both "
            f"legs are loaded - one per interleaved channel - set dies/package to {ratio:.0f} and "
            f"the shared interface will carry both.")})
    elif n_die > 1:
        out.append({"key": "dies_per_package", "severity": "note", "message": (
            f"{n_die} dies share one package, so the case-to-sink interface carries every loaded "
            f"die's loss while each junction sees only its own leg through R_th_jc. Junction "
            f"temperature is T_sink + P_leg*R_th_jc + {n_die}*P_leg*R_th_cs.")})

    vr = _pick_entry(_entries_of(profile, "V_RRM"))
    v_rated = float(vr.get("typ") or vr.get("max")) if vr and (vr.get("typ") or vr.get("max")) else None
    if v_rated and v_bus and v_rated < v_bus * DEFAULT_V_MARGIN:
        out.append({"key": "V_RRM", "severity": "check", "message": (
            f"V_RRM = {v_rated:.0f} V is below the {v_bus * DEFAULT_V_MARGIN:.0f} V the requirement "
            f"asks for ({v_bus:.0f} V bus x {DEFAULT_V_MARGIN:g}). The part will still be "
            f"calculated, but it does not meet the blocking margin this design stated.")})
    return out


# ── switching-energy anchoring, convention B (M4b) ────────────────────────────────────────────
# Plausible freewheeling-device charge in a double-pulse fixture, when the datasheet does not say
# which device it used. The low end is a bare capacitive Schottky, the high end a larger one; the
# midpoint is what the anchor uses and the ends give the band that is printed alongside it.
QFW_RANGE_C = (18e-9, 50e-9)


def switching_anchor(profile: dict, block: dict, design: dict) -> dict:
    """Anchor the analytic switching model on the datasheet's published E_on and E_off.

    CONVENTION B, settled 2026-08-05. A published E_on is measured in a double-pulse fixture and
    bundles three things: the device's own V-I overlap, the discharge of its own C_oss, and the
    charge of the freewheeling element. This engine already counts the last two SEPARATELY, as
    `P_oss_fet` and `P_rr_to_fet`. Anchoring on the raw number while keeping those terms would
    double-count them, so the bundled parts are subtracted before the anchor is taken:

        k_on  = [E_on,ds - E_oss(V_test) - Q_fw*V_test] / E_overlap,analytic(test conditions)
        k_off =  E_off,ds                               / E_off,analytic(test conditions)

    E_off needs no de-bundling: turn-off energy is the device's own overlap plus the loop-inductance
    term, with no C_oss discharge and no recovery charge flowing through it. That makes it the CLEAN
    anchor, and the difference between the two factors is diagnostic rather than cosmetic — if they
    stay far apart after de-bundling, the model's SHAPE is wrong, not its magnitude.

    Why the anchor is worth having at all: measured against this part, the un-anchored analytic
    model gives 20 uJ where the datasheet publishes 57 uJ at its own test point.
    """
    from app.mode_b.semiconductor.pfc_loss_model import Mosfet
    import numpy as np

    on_e = _pick_entry(_entries_of(profile, "E_on"))
    off_e = _pick_entry(_entries_of(profile, "E_off"))
    if not on_e or not off_e:
        return {"ok": False, "reason": "the datasheet publishes no E_on/E_off to anchor on"}

    e_on_ds = float(on_e.get("typ") or on_e.get("max") or 0.0)
    e_off_ds = float(off_e.get("typ") or off_e.get("max") or 0.0)
    cond = dict(on_e.get("conditions") or {})
    v_test = float(cond.get("V_DS") or 400.0)
    i_test = float(cond.get("I_D") or 0.0)
    rg_test = float(cond.get("R_g") or 0.0)
    tj_test = float(cond.get("T_j") or 25.0)
    if not (e_on_ds and e_off_ds and i_test):
        return {"ok": False, "reason": "the published switching energies carry no usable test point"}

    # The analytic model AT THE DATASHEET'S OWN CONDITIONS, unscaled. Same part parameters, the
    # fixture's gate resistor and gate voltage — not the design's.
    fields = Mosfet.__dataclass_fields__
    base = {k: v for k, v in block.items() if k in fields}
    base.update({"k_esw": 1.0, "k_turnoff": 1.0, "ls_loop": 0.0})
    if rg_test:
        base.update({"rg": rg_test, "rg_on": rg_test, "rg_off": rg_test})
    vgs_test = cond.get("V_GS_high") or cond.get("V_GS_swing")
    if vgs_test:
        base["vg"] = float(vgs_test)
    m = Mosfet(**base)
    zero, one = np.array([0.0]), np.array([i_test])
    e_on_an = float(m.e_switch(one, zero, v_test, tj_test)[0])
    e_off_an = float(m.e_switch(zero, one, v_test, tj_test)[0])
    if e_on_an <= 0 or e_off_an <= 0:
        return {"ok": False, "reason": "the analytic model returns no switching energy to anchor"}

    # E_oss of THIS device at the test voltage — the part of E_on the engine counts separately.
    e_oss_test = float(m.eoss(v_test))

    # The fixture's freewheeling device. Datasheets rarely state it in extractable text; this one
    # shows it only as a circuit diagram. Unknown means a BAND, not a silent assumption.
    fw = (profile.get("measurement") or {}).get("freewheel_charge_C")
    stated = fw is not None
    q_lo, q_hi = QFW_RANGE_C
    q_mid = fw if stated else 0.5 * (q_lo + q_hi)

    def _k_on(q_fw):
        return (e_on_ds - e_oss_test - q_fw * v_test) / e_on_an

    k_on = _k_on(q_mid)
    k_off = e_off_ds / e_off_an
    band = (_k_on(q_hi), _k_on(q_lo))          # more charge subtracted -> smaller k

    # An independent read on the same unknown: E_off needs no de-bundling, so if its factor also
    # applied to turn-on, the charge the fixture must have contributed is whatever is left over.
    # Agreement with the assumed range is a real cross-check; disagreement says the shape is wrong.
    implied_q_fw = (e_on_ds - e_oss_test - k_off * e_on_an) / v_test

    notes, ok = [], True
    if not stated:
        notes.append(
            f"The datasheet does not state the freewheeling device of its switching-energy test "
            f"fixture, so the charge it contributed is unknown. The anchor uses the midpoint of a "
            f"{q_lo*1e9:.0f}-{q_hi*1e9:.0f} nC range; across that range k_on spans "
            f"{band[0]:.2f} to {band[1]:.2f}, which is about +/-5% on total MOSFET loss.")
    if not (0.5 <= k_on <= 5.0):
        ok = False
        notes.append(
            f"k_on = {k_on:.2f} is outside the plausible 0.5-5.0 band. Either the de-bundling "
            f"subtracted too much (check E_oss and the assumed fixture charge) or the analytic "
            f"model does not describe this device. Not applied.")
    if not (0.5 <= k_off <= 5.0):
        ok = False
        notes.append(f"k_off = {k_off:.2f} is outside the plausible 0.5-5.0 band. Not applied.")
    if ok and max(k_on, k_off) / max(min(k_on, k_off), 1e-9) > 2.5:
        notes.append(
            f"k_on ({k_on:.2f}) and k_off ({k_off:.2f}) differ by more than 2.5x AFTER "
            f"de-bundling. A magnitude error would scale both alike, so this points at the model's "
            f"SHAPE rather than its size. Treat the switching term as provisional until the "
            f"E(I_D) curve is digitised.")
    if implied_q_fw < 0 or implied_q_fw > 2 * q_hi:
        notes.append(
            f"Cross-check: anchoring on E_off alone implies the fixture contributed "
            f"{implied_q_fw*1e9:.0f} nC, outside the assumed {q_lo*1e9:.0f}-{q_hi*1e9:.0f} nC "
            f"range. The two anchors disagree about what the published E_on contains.")

    return {
        "ok": ok,
        "k_on": round(k_on, 4), "k_off": round(k_off, 4),
        "k_esw": round(k_on, 6),
        # The engine scales BOTH energies by k_esw and turn-off again by k_turnoff, so the ratio is
        # what makes e_off land on k_off. Recorded here because the arithmetic is not obvious.
        "k_turnoff": round(k_off / k_on, 6) if k_on else 1.0,
        "bundling": "de_bundled",
        "band": {"k_on_low": round(band[0], 4), "k_on_high": round(band[1], 4),
                 "q_fw_low_C": q_lo, "q_fw_high_C": q_hi, "q_fw_used_C": q_mid,
                 "stated": bool(stated)},
        "basis": {
            "E_on_ds": e_on_ds, "E_off_ds": e_off_ds,
            "E_on_analytic": round(e_on_an, 12), "E_off_analytic": round(e_off_an, 12),
            "E_oss_at_test": round(e_oss_test, 12),
            "V_test": v_test, "I_test": i_test, "R_g_test": rg_test, "T_j_test": tj_test,
        },
        "implied_q_fw_C": implied_q_fw,
        "notes": notes,
        "statement": (
            f"E_on {e_on_ds*1e6:.0f} uJ published at {v_test:.0f} V, {i_test:.1f} A, "
            f"R_g {rg_test:g} ohm. Removing this device's own E_oss ({e_oss_test*1e6:.1f} uJ) and "
            f"the fixture's freewheeling charge ({q_mid*1e9:.0f} nC x {v_test:.0f} V = "
            f"{q_mid*v_test*1e6:.1f} uJ) leaves {(e_on_ds - e_oss_test - q_mid*v_test)*1e6:.1f} uJ "
            f"of device overlap, against {e_on_an*1e6:.1f} uJ from the model -> k_on = {k_on:.2f}. "
            f"E_off needs no de-bundling: {e_off_ds*1e6:.0f} uJ against {e_off_an*1e6:.1f} uJ "
            f"-> k_off = {k_off:.2f}."),
    }


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
