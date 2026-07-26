"""
verify_emi_newspecs.py — differential-spec harness for the Chapter-10 EMI filter.
==================================================================================
Runs the EMI synthesis + report with a NON-reference spec set and checks that:

  1. NO reference value leaks into the design or the rendered report (hardcode canaries) —
     the same methodology that caught the C127-C133 hardcodes,
  2. the NEW spec values actually appear (the design tracks the specs), and
  3. spec-tracking INVARIANTS hold (Vbus -> CM source, f_sw -> first harmonic, safety
     standard -> C_Y ceiling, DC-DC toggle -> CM, higher Vbus -> higher CM source).

Edit the SPEC / CAP / OPTS block below and run from the backend/ directory:

    PYTHONUTF8=1 python verify_emi_newspecs.py

Exit code 0 = all checks pass; 1 = a canary leaked or an invariant failed.
"""
from __future__ import annotations
import io
import re
import sys

from app.mode_b.inputfilter.adapter import calculate_emi
from app.mode_b.report_inputfilter import build_inputfilter_report

# ── NON-reference spec block (edit freely; stays within the hard [85,264] Vac clamp) ──
SPEC = dict(vin_min=100, vin_max=250, pout_lo=1200, pout_hi=2500, vout=450.0,
            fsw=85000, fline=50, nch=2, r_input=0.20, L_phi_uH=300)
CAP = {"value_uF": 500, "qty": 2, "ESR_parallel_mohm": 4}
OPTS = dict(safety_standard="IEC_60601_1", compliance_profile=3, margin_db=6,  # medical + Class A
            c_node_pfc_pf=60, dvdt_pfc_vns=12,
            dcdc={"present": True, "f_sw_dc_hz": 300000, "v_node_v": 450,
                  "c_node_psfb_pf": 40, "c_ps_pf": 20, "dvdt_psfb_vns": 18})

# Reference values that MUST NOT appear in a non-reference design/report (hardcode canaries):
# the doc worked-example specs + its specific synthesized component values.
REF_CANARIES = [
    ("f_sw 70 kHz", "70 kHz"), ("vin_min 90 Vac", "90 V"), ("vin_max 264", "264"),
    ("Vout 394", "394"), ("Vbus 400 V", "400 V"),
    ("L_CM 6.8 mH", "6.8 mH"), ("L_CM 1.5 mH", "1.5 mH"), ("L_DM 27 µH", "27 µH"),
    ("C_Y 23.2 nF", "23.2 nF"), ("bleeder 82 k", "82 k"),
]
# New-spec values that SHOULD appear (proves the design tracks the specs).
NEW_PRESENT = [
    ("vin_max 250", "250"), ("f_sw 85 kHz", "85 kHz"), ("first harmonic 170 kHz", "170 kHz"),
    ("Vbus 450", "450"),
]

_G = "\033[92m"; _R = "\033[91m"; _Y = "\033[93m"; _0 = "\033[0m"


def _pdf_text(pdf: bytes) -> str:
    from pypdf import PdfReader
    return "".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(pdf)).pages)


def _count(txt: str, needle: str) -> int:
    """Count occurrences with digit boundaries so a numeric needle never matches inside a larger
    number (e.g. '70 kHz' must not match '170 kHz', '264' must not match '1264')."""
    pat = r"(?<!\d)" + re.escape(needle) + (r"(?!\d)" if needle[-1].isdigit() else "")
    return len(re.findall(pat, txt))


def main() -> int:
    fails = 0

    # ── build the design + report with the non-reference specs ──
    out = calculate_emi(SPEC, CAP, {}, {}, OPTS)
    r, b = out["result"], out["basis"]
    pdf = build_inputfilter_report(SPEC, CAP, {}, {}, OPTS)
    txt = _pdf_text(pdf)
    _lcm = "inf" if r["l_cm"] == float("inf") else f"{r['l_cm']*1e3:.2f} mH"
    print(f"Report: {len(pdf)} bytes | noise_source={r['noise_source']} | "
          f"DM {r['dm_stages']}-stg {r['l_dm']*1e6:.1f} uH / {r['c_x']*1e6:.2f} uF  |  "
          f"CM {r['cm_stages']}-stg {_lcm} / {r['c_y_emi_total']*1e9:.2f} nF")

    # ── 1. hardcode canaries (must be ABSENT) ──
    print("\n--- reference-value canaries (must be ABSENT) ---")
    for label, needle in REF_CANARIES:
        n = _count(txt, needle)
        ok = (n == 0)
        fails += 0 if ok else 1
        print(f"  [{(_G+'ok'+_0) if ok else (_R+'LEAK'+_0)}] {label:<18} '{needle}' x{n}")

    # ── 2. new-spec values (should be PRESENT) ──
    print("\n--- new-spec values (should be PRESENT) ---")
    for label, needle in NEW_PRESENT:
        n = _count(txt, needle)
        ok = (n > 0)
        if not ok:
            print(f"  [{_Y}warn{_0}] {label:<22} '{needle}' not found")
        else:
            print(f"  [{_G}ok{_0}] {label:<22} '{needle}' x{n}")

    # ── 3. spec-tracking invariants ──
    print("\n--- spec-tracking invariants ---")

    def check(name, cond, detail=""):
        nonlocal fails
        fails += 0 if cond else 1
        print(f"  [{(_G+'ok'+_0) if cond else (_R+'FAIL'+_0)}] {name}  {detail}")

    check("first harmonic = N_ch x f_sw",
          abs(r["first_harmonic_hz"] - SPEC["nch"] * SPEC["fsw"]) < 1,
          f"({r['first_harmonic_hz']/1e3:.0f} kHz)")
    check("noise source is computed (not estimate)", r["noise_source"] == "computed")
    check("components finite & positive",
          r["c_x"] > 0 and r["l_dm"] > 0 and r["c_y_emi_total"] > 0)
    check("9-point sweep present", len(r["per_point"]) == 9)
    check("spectra render arrays present",
          bool(r["spectra"].get("f")) and len(r["spectra"]["f"]) > 10)

    # tighter safety standard -> smaller Y-cap ceiling
    o_classI = dict(OPTS); o_classI["safety_standard"] = "IEC_62368_1"   # 3.5 mA
    r_classI = calculate_emi(SPEC, CAP, {}, {}, o_classI)["result"]
    check("medical leakage -> smaller C_Y than Class I",
          r["c_y_emi_total"] < r_classI["c_y_emi_total"],
          f"(med {r['c_y_emi_total']*1e9:.2f} < I {r_classI['c_y_emi_total']*1e9:.2f} nF)")

    # DC-DC present -> higher CM requirement than PFC-only
    o_pfc = dict(OPTS); o_pfc["dcdc"] = {"present": False}
    r_pfc = calculate_emi(SPEC, CAP, {}, {}, o_pfc)["result"]
    check("DC-DC present -> higher CM required att than PFC-only",
          r["cm_req_att_db"] > r_pfc["cm_req_att_db"] + 1,
          f"(with {r['cm_req_att_db']:.0f} > PFC-only {r_pfc['cm_req_att_db']:.0f} dB)")

    # higher Vbus -> higher CM source
    s_hi = dict(SPEC); s_hi["vout"] = 500.0
    o_hi = dict(OPTS); o_hi = dict(OPTS); o_hi["dcdc"] = dict(OPTS["dcdc"]); o_hi["dcdc"]["v_node_v"] = 500
    r_hi = calculate_emi(s_hi, CAP, {}, {}, o_hi)["result"]
    check("higher Vbus -> higher CM source",
          r_hi["spectra"]["cm_src"][0] > r["spectra"]["cm_src"][0],
          f"({r_hi['spectra']['cm_src'][0]:.1f} > {r['spectra']['cm_src'][0]:.1f} dBuV @150k)")

    # different f_sw -> different first harmonic / DM corner
    s_fs = dict(SPEC); s_fs["fsw"] = 120000
    r_fs = calculate_emi(s_fs, CAP, {}, {}, o_pfc)["result"]
    check("f_sw change -> first harmonic tracks",
          abs(r_fs["first_harmonic_hz"] - 2 * 120000) < 1,
          f"({r_fs['first_harmonic_hz']/1e3:.0f} kHz)")

    print("\n" + ("=" * 60))
    if fails == 0:
        print(f"{_G}ALL EMI DIFFERENTIAL-SPEC CHECKS PASSED — no reference value leaked.{_0}")
    else:
        print(f"{_R}{fails} CHECK(S) FAILED — investigate the leak/invariant above.{_0}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
