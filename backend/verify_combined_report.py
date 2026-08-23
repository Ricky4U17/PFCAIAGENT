"""
verify_combined_report.py — headless build of the full combined design report
(Chapters 1-5 documentation agent + Chapter 6 detailed control report) via the
real /mode-b/documentation/generate-report endpoint, for page-count / regression
verification.

WHY THIS EXISTS — selected_cap is mandatory:
    run_capacitor_design(state) alone returns only suggested_configs/suppliers; it
    NEVER returns a selected_cap (that is chosen at GUI Step-15 approve). Chapter 5
    §5.3 (ripple verification), §5.4 (Life Time Period) and §5.5 (bank summary) are
    gated on step15_result["selected_cap"] being present (doc_report_builder rule 8).
    So a headless build WITHOUT a selected_cap silently drops those ~7 pages and reads
    ~205 pp instead of the real ~212 pp. This harness therefore ALWAYS attaches a real
    catalog part as selected_cap so the page count matches the GUI-driven report.

Usage:
    cd backend && PYTHONUTF8=1 venv/Scripts/python.exe verify_combined_report.py
    (optional: pass a voltage-loop crossover, e.g. `... verify_combined_report.py 22`)
"""
from __future__ import annotations
import io, copy, math, sys, os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _std_state():
    """Confirmed Mode-A + mini-intake state (mirrors tests/test_regression.confirmed_state,
    plus the fields the documentation agent's _validate_mode_a() requires)."""
    intake = {
        "application": {"vin_rms_min": 90, "vin_rms_max": 264, "output_bus_voltage_v": 393,
            "output_power_w_high_line": 3600, "output_power_w_low_line": 1700,
            "power_factor_target": 0.99, "efficiency_target_percent": 98.0,
            "dc_bus_voltage_ripple_pk_pk_v": 20, "nominal_line_frequency_hz": 60,
            "hold_up_time_ms": 20, "output_power_w_nom": 3600},
        "thermal": {"cooling_type": "fan_cooled", "ambient_temp_c_max": 50, "hotspot_limit_c": 110},
        "compliance": {"application_class": "Medical", "leakage_current_limit_ua": 500},
        "control": {"control_preference": "Recommend"},
        "business": {"cost_priority": 7, "efficiency_priority": 9, "power_density_priority": 8,
                     "implementation_risk_priority": 6, "preferred_switch_technology": ["Si", "SiC"]},
        "supply": {"preferred_vendors": [], "avoid_vendors": []},
    }
    return {
        "project_id": "verify-combined-001",
        "selected_topology": "interleaved_boost_ccm", "selected_mode": "ccm",
        "selected_channels": 2, "selected_controller_mode": "analog",
        "topology_specific_inputs": {"switching_frequency_style": "fixed",
            "recommended_frequency_hz": 70000.0, "default_crest_ripple_ratio": 0.20,
            "ask_crest_ripple_ratio": True,
            "confirmed_L_uH": 235.0, "confirmed_L_uH_sel": 235.0, "recommended_L_uH": 235.0},
        "intake": intake,
    }


def pick_selected_cap(cap: dict) -> dict:
    """Choose a REAL catalog part as the designer would at Step-15 approve, so §5.3/5.4/5.5
    render. Picks the largest-capacitance DB part at or above the required voltage rating and
    parallels enough of them to meet the required capacitance. Falls back to a known-good part."""
    from app.mode_b.step15_cap_db import _load
    db = _load()
    C_req = float(cap.get("C_required_uF") or cap.get("worst_case", {}).get("C_holdup_uF") or 2000)
    V_min = int(float(cap.get("V_rating_min_V") or 0))
    V_sel = int(float(cap.get("V_rating_selected_V") or V_min or 450))
    # candidates at or above the selected voltage class, largest capacitance first
    cands = sorted((r for r in db if int(r.get("voltage_V", 0)) >= max(V_sel, V_min)),
                   key=lambda r: r.get("capacitance_uF", 0), reverse=True)
    part = next((r for r in cands if r.get("part_number")), None)
    if part is None:
        part = next(r for r in db if r["part_number"] == "383LX122M450B082VS")  # known-good fallback
    value = float(part["capacitance_uF"])
    qty = max(1, math.ceil(C_req / value)) if value else 1
    return {
        "supplier": part.get("manufacturer") or part.get("supplier") or "—",
        "series": part.get("series", "—"),
        "voltage_rating_V": part.get("voltage_V"),
        "value_uF": value, "qty": qty,
        "part_number": part["part_number"],
        "temp_rating_C": part.get("op_temp_max_C", 105),
    }


def build_combined(fcv_Hz: float = 17.0):
    """Run step7 sizing -> cap design (+ real selected_cap) -> step16 params ->
    combined report. Returns (pdf_bytes, page_count, text, meta)."""
    import matplotlib; matplotlib.use("Agg")
    from pypdf import PdfReader
    from fastapi.testclient import TestClient
    from app.main import app
    from app.mode_b.step15_capacitor import run_capacitor_design

    client = TestClient(app)
    state = _std_state()

    # 1) Step-7 magnetic sizing -> approved_design (+ all_candidates)
    r = client.post("/mode-b/step7/run-sizing", json={"state": state, "material_key": "edge_60",
        "wire_type": "magnet", "wire_designation": None, "max_stacks": 3, "n_top": 5})
    r.raise_for_status()
    cands = r.json().get("top_5") or r.json().get("candidates") or []
    approved = copy.deepcopy(cands[0].get("result", cands[0]))
    approved["all_candidates"] = copy.deepcopy([c.get("result", c) for c in cands])

    # 2) Capacitor design + a REAL selected_cap (what Step-15 approve would carry) + worst_case
    cap = run_capacitor_design(state)
    step15 = dict(cap)
    step15["selected_cap"] = pick_selected_cap(cap)
    step15["V_rating_selected_V"] = step15["selected_cap"]["voltage_rating_V"]

    # 3) step16_params (power stage) — L/DCR from the approved inductor, C/ESR from the cap bank
    def _g(d, *ks, default=None):
        for k in ks:
            if isinstance(d, dict) and d.get(k) not in (None, ""):
                return d[k]
        return default
    C_total = step15["selected_cap"]["value_uF"] * step15["selected_cap"]["qty"]
    step16 = {
        "L_uH": float(_g(approved, "L0_nom_uH", "L_phi_uH", "L_uH", default=235)),
        "DCR_mOhm": float(_g(approved, "DCR_mOhm", "dcr_mohm", "R_dc_mOhm", default=95)),
        "C_uF": float(C_total), "ESR_mOhm": float(_g(cap, "ESR_mOhm", "esr_total_mOhm", default=12.7)),
        "Vout_V": 393.0, "fsw_Hz": 70000.0, "Pout_lo_W": 1700.0, "Pout_hi_W": 3600.0,
        "eta_lo": 0.945, "eta_hi": 0.965, "nch": 2, "fci_Hz": 8000.0, "fcv_Hz": float(fcv_Hz),
    }

    # 4) Semiconductor payload — WITHOUT this the whole of Chapter 7 is skipped (`if
    #    req.semiconductor:` in main.py), and for many commits this harness built a document with
    #    no Chapter 7 at all while claiming to be the full report. That is how C233's inductor
    #    budget fix ended up with no coverage on the path that actually ships (B21 / C245).
    #    Catalogue parts, not datasheet uploads: Chapter 7 renders either way and the digitiser
    #    would double the fixture's runtime for nothing this test needs.
    from app.mode_b.semiconductor import adapter as _AD
    _scd = dict(_AD.REFERENCE_DESIGN)
    _scd.update({"eta": 0.95, "pf": 0.99, "V_GS_drive": 18.0, "R_g_on": 4.7, "R_g_off": 10.0,
                 "R_th_cs": 0.3, "nch": int(step16["nch"]), "vout": step16["Vout_V"],
                 "fsw": step16["fsw_Hz"]})
    # THERMAL AMBIENT COMES FROM THE INTAKE SPEC, exactly as the GUI does it
    # (`SemiconductorSelection.tsx`: `_specAmbient = intake.thermal.ambient_temp_c_max`, pre-filled
    # into the thermal form and re-synced until the designer edits it).
    #
    # C245 sent `REFERENCE_PARTS["thermal"]` here, which pins t_ambient = 45. `main.py` only falls
    # back to the spec when the payload's value is ABSENT, so 45 won: the fixture reported "Ambient
    # 45 degC" no matter what the spec said, and could not have detected a chapter that stopped
    # tracking the designer's entered ambient. That is the one thing this fixture most needs to
    # catch, so the harness now mirrors the GUI (C247).
    _spec_amb = float((state.get("intake", {}).get("thermal", {})
                       .get("ambient_temp_c_max") or 45))
    _sc_thermal = dict(_AD.REFERENCE_PARTS["thermal"])
    _sc_thermal["t_ambient"] = _spec_amb
    semiconductor = {
        "design": _scd,
        "mosfet": _AD.REFERENCE_PARTS["mosfet"], "diode": _AD.REFERENCE_PARTS["diode"],
        "bridge": _AD.REFERENCE_PARTS["bridge"], "thermal": _sc_thermal,
        "tj_limit": {"fet": 150, "diode": 150, "bridge": 130},
    }

    # 5) Combined report
    r = client.post("/mode-b/documentation/generate-report", json={"state": state,
        "approved_design": approved, "step15_result": step15, "step16_params": step16,
        "semiconductor": semiconductor})
    r.raise_for_status()
    pdf = r.content
    reader = PdfReader(io.BytesIO(pdf))
    text = "".join((p.extract_text() or "") for p in reader.pages)
    meta = {"selected_cap": step15["selected_cap"], "C_total_uF": C_total}
    return pdf, len(reader.pages), text, meta


def main():
    fcv = float(sys.argv[1]) if len(sys.argv) > 1 else 17.0
    pdf, pages, text, meta = build_combined(fcv)
    sc = meta["selected_cap"]
    print("selected_cap: %s x%d  %s  %.0f uF / %.0f V  (bank %.0f uF)" % (
        sc["part_number"], sc["qty"], sc["supplier"], sc["value_uF"],
        sc["voltage_rating_V"], meta["C_total_uF"]))
    print("COMBINED REPORT: %d pages, %.2f MB  (f_cv = %.0f Hz)" % (pages, len(pdf) / 1e6, fcv))
    checks = {
        "no legacy fallback": "via Mode A HITL" not in text,
        "§5.3 ripple verification": "Ripple Current and Voltage Verification" in text,
        "§5.4 Life Time Period": "Capacitor Life Time Period" in text,
        "§5.5 Bank Summary": "Capacitor Bank Summary" in text,
        "§4.8 cross-check": "Field engine agrees with Step-7" in text,
        "Ch6 Control Scheme": "Control Scheme" in text,
        # A chapter can vanish under HTTP 200 (PENDING E2), so name the ones that have actually
        # done it: Ch3/Ch4 shared a try-tolerant branch, and Ch7 was absent from this harness
        # entirely until C245. The page bound below catches the rest.
        "Ch3 Table 3.6.1": "Table 3.6.1" in text,
        "Ch4 Table 4.2": "Table 4.2" in text,
        "Ch7 Semiconductor Loss": "Semiconductor Loss" in text,
    }
    for name, ok in checks.items():
        print("  [%s] %s" % ("OK" if ok else "!!", name))
    # KEEP THIS IN STEP WITH tests/test_regression.py::test_page_count_is_full_report. It read
    # 178-190 until C251 while the real document was ~212 pp (Ch7 arrived with C245), so running
    # this script on a perfectly good report printed OUT OF RANGE and exited 1 — a stale check
    # that cries wolf is worse than no check, because the next real regression gets waved through.
    ok_pages = 205 <= pages <= 235
    print("PAGE COUNT %s (expected 205-235, got %d)" % ("OK" if ok_pages else "OUT OF RANGE", pages))
    sys.exit(0 if (ok_pages and all(checks.values())) else 1)


if __name__ == "__main__":
    main()
