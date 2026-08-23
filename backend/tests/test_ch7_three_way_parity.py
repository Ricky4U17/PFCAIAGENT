"""GUI == ENGINE == REPORT for every per-line Chapter-7 table.

The designer asked, after the inductor-budget defect (C233), whether Chapter 7 carried the same
class of problem: a number shown one way on screen and another way in the document. This walks
EVERY per-line table in the chapter and compares each rendered cell to the engine field it claims
to be.

WHY THE GUI SIDE NEEDS NO SEPARATE FIXTURE. `SemiconductorSelection.tsx` renders the `/calculate`
response verbatim - `p.P_FET_cond`, `p.P_D_cond`, `r.Tj_FET` and so on - with exactly ONE piece of
arithmetic of its own:

    r.P_FET_total + (r.P_gate_driver ?? 0)          // line ~1659

So GUI == engine holds by construction for every other field, and the only edges worth testing are
that one derived value (asserted below against the column the report prints) and engine -> report.
If the GUI ever starts deriving more, this docstring is the thing that has gone stale.

COMPARE AT THE PRECISION THE CELL IS PRINTED AT. Table 7.6 prints whole degrees; the engine carries
70.65. Asserting against the raw float flags all nine rows as mismatches, which is a property of
the format string rather than a defect. The check is `rendered == round(engine, dp)`.

BOUND EACH TABLE. Every per-line table starts its rows with "<Vac> V", so a regex given a fixed
window runs into the NEXT table and silently compares cells from the wrong one - it produced a
200 degC junction temperature during development. `_seg` cuts at the next table caption.
"""
import io
import os
import re
import shutil
import tempfile

import pytest

_SPECS = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "specs")
_PARTS = [("mosfet", "sic_mosfet", os.path.join(_SPECS, "Review", "IMZA65R033M2HXKSA1.pdf")),
          ("diode", "sic_schottky", os.path.join(_SPECS, "Review", "PFC Boost Diode",
                                                 "vs-4c16ep07l-m3.pdf")),
          ("bridge", "bridge_rectifier", os.path.join(_SPECS, "Review",
                                                      "Bridge Rectifier Update", "lve5060e.pdf"))]


@pytest.fixture(scope="module")
def built():
    """All three parts from real datasheets, every offered curve accepted: the configuration a
    designer actually produces, and the only one in which all four tables render."""
    import fitz
    from fastapi.testclient import TestClient
    from app.mode_b.semiconductor import parts_store as PS, adapter as AD
    from app.mode_b.report_semiconductor import build_semiconductor_report
    import app.main as main

    for _, _, path in _PARTS:
        if not os.path.exists(path):
            pytest.skip(f"{os.path.basename(path)} not available")

    design = dict(AD.REFERENCE_DESIGN)
    design.update({"eta": 0.95, "pf": 0.99, "V_GS_drive": 18.0, "R_g_on": 4.7, "R_g_off": 10.0,
                   "R_th_cs": 0.3, "n_parallel": 2, "dies_per_package": 1})
    blocks, root = {}, tempfile.mkdtemp(prefix="ch7parity_")
    orig, PS.DEFAULT_ROOT = PS.DEFAULT_ROOT, root
    try:
        c = TestClient(main.app)
        for kind, cls, path in _PARTS:
            with open(path, "rb") as fh:
                raw = fh.read()
            pn = f"PARITY_{kind}"
            c.post("/mode-b/semiconductor/datasheet/upload",
                   files={"file": ("d.pdf", io.BytesIO(raw), "application/pdf")},
                   data={"kind": kind, "device_class": cls, "part_number": pn})
            pr = c.post("/mode-b/semiconductor/datasheet/figures",
                        files={"file": ("d.pdf", io.BytesIO(raw), "application/pdf")},
                        data={"part_number": pn}).json()["proposals"]
            for q in pr:
                cu = q["curves"][(q.get("cross_check") or {}).get("curve_index", 0)]
                c.post("/mode-b/semiconductor/datasheet/figure-confirm",
                       json={"part_number": pn, "key": q["key"],
                             "curve": {"x": cu["x"], "y": cu["y"], "caption": q.get("caption"),
                                       "page": q.get("page"), "frame": q.get("frame")},
                             "conditions": {}})
            blocks[kind] = c.post("/mode-b/semiconductor/datasheet/confirm",
                                  json={"part_number": pn, "kind": kind, "device_class": cls,
                                        "edits": {}, "design": design}).json()["block"]
        calc = c.post("/mode-b/semiconductor/calculate",
                      json={"design": design, "mosfet": blocks["mosfet"],
                            "diode": blocks["diode"], "bridge": blocks["bridge"],
                            "thermal": AD.REFERENCE_PARTS["thermal"],
                            "tj_limit": {"fet": 150, "diode": 150, "bridge": 130}}).json()
    finally:
        PS.DEFAULT_ROOT = orig
        shutil.rmtree(root, ignore_errors=True)

    pdf = build_semiconductor_report(design, blocks["mosfet"], blocks["diode"], blocks["bridge"],
                                     AD.REFERENCE_PARTS["thermal"])
    with fitz.open(stream=pdf, filetype="pdf") as doc:
        txt = "".join(p.get_text() for p in doc)
    return {"txt": txt, "pp": {round(float(r["Vac"])): r for r in calc["per_point"]},
            "summary": calc["summary"]}


def _seg(txt, tag):
    i = txt.find(tag)
    if i < 0:
        return ""
    j = txt.find("\nTable 7", i + len(tag))
    return txt[i:j if j > 0 else i + 3000]


def _parse(txt, tag, unit, ncol):
    seg = _seg(txt, tag)
    if not seg:
        return {}
    cell = r"([-\d.]+)\s*" + unit + r"\n"
    return {int(m.group(1)): [float(g) for g in m.groups()[1:]]
            for m in re.finditer(r"^(\d+) V\n" + cell * ncol, seg, re.M)}


# table tag, unit regex, ncol, [(column index, label, engine key or callable, decimals)]
TABLES = [
    ("Table 7.3 — Bridge Loss vs Line Voltage", r"[AW]", 2,
     [(0, "Iin_rms", "Iin_rms", 1), (1, "P_BRIDGE_total", "P_BRIDGE_total", 2)]),
    ("Table 7.4 — MOSFET Loss Breakdown vs Line Voltage", r"W?", 6,
     [(0, "P_FET_cond", "P_FET_cond", 2), (1, "P_FET_sw", "P_FET_sw", 2),
      (2, "P_FET_coss", "P_FET_coss", 2), (3, "P_FET_rr", "P_FET_rr", 2),
      (4, "gate+leak", lambda p: (p.get("P_gate_driver") or 0) + (p.get("P_FET_leak") or 0), 2),
      (5, "FET total+gate",
       lambda p: (p.get("P_FET_total") or 0) + (p.get("P_gate_driver") or 0), 2)]),
    ("Table 7.5 — Diode Loss vs Line Voltage", r"W", 4,
     # The report column is headed "Recovery (Qrr)" but the engine field is P_D_sw, NOT P_D_rr -
     # there is no P_D_rr. The GUI reads P_D_sw too, so screen and document agree; only the name
     # differs from the column heading. Do not "correct" this key without checking the engine.
     [(0, "P_D_cond", "P_D_cond", 2), (1, "Recovery (P_D_sw)", "P_D_sw", 2),
      (2, "P_D_leak", "P_D_leak", 3), (3, "P_DIODE_total", "P_DIODE_total", 2)]),
    ("Table 7.6 — Junction Temperatures vs Line Voltage", "°C", 4,
     [(0, "T_sink", "T_sink_main", 0), (1, "Tj_FET", "Tj_FET", 0),
      (2, "Tj_DIODE", "Tj_DIODE", 0), (3, "Tj_BRIDGE", "Tj_BRIDGE_top", 0)]),
]


@pytest.mark.parametrize("tag,unit,ncol,cols", TABLES,
                         ids=[t[0].split("—")[1].strip()[:22] for t in TABLES])
def test_every_rendered_cell_equals_the_engine(built, tag, unit, ncol, cols):
    rows = _parse(built["txt"], tag, unit, ncol)
    assert len(rows) == len(built["pp"]), (
        f"{tag}: parsed {len(rows)} rows, engine has {len(built['pp'])} operating points")
    bad = []
    for vac, cells in rows.items():
        p = built["pp"][vac]
        for idx, label, key, dp in cols:
            want = key(p) if callable(key) else p.get(key)
            assert want is not None, f"{label}: engine field missing at {vac} Vac"
            got = cells[idx]
            if abs(got - round(float(want), dp)) > 10 ** (-dp) / 2 + 1e-9:
                bad.append(f"{vac} Vac {label}: report {got}, engine {float(want):.4f}")
    assert not bad, f"{tag}\n  " + "\n  ".join(bad)


def test_the_one_value_the_gui_derives_matches_the_report(built):
    """`P_FET_total + P_gate_driver` — the GUI's only arithmetic — against the column the report
    prints for it. If these ever diverge, the screen and the document disagree on the FET total."""
    rows = _parse(built["txt"], "Table 7.4 — MOSFET Loss Breakdown vs Line Voltage", r"W?", 6)
    for vac, p in built["pp"].items():
        gui = (p.get("P_FET_total") or 0) + (p.get("P_gate_driver") or 0)
        assert rows[vac][5] == pytest.approx(round(gui, 2), abs=0.006), (
            f"{vac} Vac: GUI shows {gui:.2f} W, report Table 7.4 shows {rows[vac][5]} W")


def test_summary_maxima_are_the_maxima_of_the_per_point_rows(built):
    """The GUI's headline numbers must be the per-point series' own maxima, not a separate solve."""
    pp, su = built["pp"].values(), built["summary"]
    for skey, pkey in (("P_FET_max", "P_FET_total"), ("P_DIODE_max", "P_DIODE_total"),
                       ("P_BRIDGE_max", "P_BRIDGE_total"), ("P_SEMI_max", "P_SEMI_total"),
                       ("Tj_FET_max", "Tj_FET"), ("Tj_DIODE_max", "Tj_DIODE"),
                       ("Tj_BRIDGE_max", "Tj_BRIDGE_top")):
        if su.get(skey) is None:
            continue
        assert su[skey] == pytest.approx(max(float(p[pkey]) for p in pp), rel=1e-9), \
            f"summary {skey} is not max({pkey}) over the operating points"


def test_worst_case_line_voltages_point_at_the_right_rows(built):
    """`worst_loss_Vac` drives which point Figures 7-3/7-4 are drawn at (C232), so it must be the
    argmax of the series it claims, not the first point."""
    pp, su = built["pp"], built["summary"]
    if su.get("worst_loss_Vac") is not None:
        assert round(float(su["worst_loss_Vac"])) == max(pp, key=lambda v: pp[v]["P_SEMI_total"])
    if su.get("worst_TjFET_Vac") is not None:
        assert round(float(su["worst_TjFET_Vac"])) == max(pp, key=lambda v: pp[v]["Tj_FET"])


def test_gate_drive_is_counted_once_and_consistently(built):
    """C250, designer-reported. Gate drive belongs in some totals and not others; both must be
    deliberate, and the two that DO include it must agree.

    The designer reconciled Table 7.4 against the OLD Table 7.8a and found ~0.1 W missing: 7.4's
    MOSFET TOTAL is `P_FET_total + P_gate_driver` while 7.8a's MOSFET row was `P_FET_max`, which
    excludes gate. C249 replaced 7.8a; this pins the two together so they cannot drift apart again.

    The OTHER difference the designer found is NOT a defect, and is asserted here as intended
    behaviour: the heatsink solve uses `Psemi_main = P_fet_total + P_dio_total` - no gate - because
    the gate charge is dissipated in the driver IC and the external R_g, never crossing the
    junction-to-case path. Section 7.6.1 now states that instead of leaving a 0.1 W puzzle.
    """
    dash = "\u2014"
    t74 = _parse(built["txt"], "Table 7.4 " + dash, r"W?", 6)
    t8a = _parse(built["txt"], "Table 7.8a " + dash, r"W?", 4)
    assert t74 and t8a, "Table 7.4 or 7.8a did not render"

    common = sorted(set(t74) & set(t8a))
    assert len(common) >= 9, f"parsed only {len(common)} comparable rows"
    for v in common:
        assert t74[v][5] == pytest.approx(t8a[v][0], abs=0.02), (
            f"{v} Vac: Table 7.4 MOSFET total {t74[v][5]} W but Table 7.8a says {t8a[v][0]} W "
            "- one of them has dropped gate drive")

    # 7.4 must add across: the five mechanism columns ARE the total
    for v, cells in t74.items():
        assert sum(cells[:5]) == pytest.approx(cells[5], abs=0.02), (
            f"{v} Vac: Table 7.4 columns sum to {sum(cells[:5]):.2f} W but its TOTAL says "
            f"{cells[5]:.2f} W")

    # 7.8a must add across too, and its total is what 7.8b carries
    for v, cells in t8a.items():
        assert sum(cells[:3]) == pytest.approx(cells[3], abs=0.02), (
            f"{v} Vac: Table 7.8a components sum to {sum(cells[:3]):.2f} W but its Total says "
            f"{cells[3]:.2f} W")

    # and the thermal path must deliberately EXCLUDE gate drive, in writing
    assert "Gate-drive power is excluded" in " ".join(built["txt"].split()), \
        "Section 7.6.1 no longer explains why its P_sigma is smaller than Table 7.8b's total"
