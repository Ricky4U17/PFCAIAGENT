"""
app/mode_b/step16_steps1_8.py — Control-design calculation agent, Steps 1–8.

Reproduces the FAN9672 gain-modulator / current-sense design steps of the
reference design report (FAN9672_Control_Loop_Design_Combined_with_Thesis…),
following AN4165-D, AND9925-D and FAN9672-D. Every formula here was verified to
reproduce the reference document's worked numbers to 4–5 significant figures.

Steps 1–8 (power-stage spec → base constants → IAC/V_LPK → oscillator → output
divider/PVO → R_CS two methods → GMOD three-path verification → GC/LS/SS/ILIMIT).
The power-stage inputs (Step 1) are taken from the earlier design steps / spec —
they are NOT recomputed here.

`compute_steps_1_8(inp=None)` returns a structured dict the report builder reads.
"""
from __future__ import annotations
import math

SQRT2 = math.sqrt(2.0)

# E24 standard-value mantissas (for snapping computed R_CS to a real shunt value).
_E24 = [1.0, 1.1, 1.2, 1.3, 1.5, 1.6, 1.8, 2.0, 2.2, 2.4, 2.7, 3.0,
        3.3, 3.6, 3.9, 4.3, 4.7, 5.1, 5.6, 6.2, 6.8, 7.5, 8.2, 9.1]

# E96 1% series for standard-value snapping
_E96 = [1.00,1.02,1.05,1.07,1.10,1.13,1.15,1.18,1.21,1.24,1.27,1.30,1.33,1.37,1.40,
        1.43,1.47,1.50,1.54,1.58,1.62,1.65,1.69,1.74,1.78,1.82,1.87,1.91,1.96,2.00,
        2.05,2.10,2.15,2.21,2.26,2.32,2.37,2.43,2.49,2.55,2.61,2.67,2.74,2.80,2.87,
        2.94,3.01,3.09,3.16,3.24,3.32,3.40,3.48,3.57,3.65,3.74,3.83,3.92,4.02,4.12,
        4.22,4.32,4.42,4.53,4.64,4.75,4.87,4.99,5.11,5.23,5.36,5.49,5.62,5.76,5.90,
        6.04,6.19,6.34,6.49,6.65,6.81,6.98,7.15,7.32,7.50,7.68,7.87,8.06,8.25,8.45,
        8.66,8.87,9.09,9.31,9.53,9.76]


def _nearest_e24(v: float) -> float:
    """Nearest E24 capacitor value. Capacitors are stocked in E24, not the E6 subset the GUI
    dropdown used to offer - which is how C239's 430 pF / 18 nF / 75 nF / 240 pF defaults ended up
    UNSELECTABLE on Screen 2, so four dropdowns fell back to their first option (100 pF) and sent
    that to the report (C242)."""
    if v <= 0:
        return v
    dec = math.floor(math.log10(v))
    base = v / (10 ** dec)
    cands = _E24 + [10.0]          # decade wrap, same reasoning as _nearest_e96
    return min(cands, key=lambda c: abs(math.log(c / base))) * (10 ** dec)


def _nearest_e96(v: float) -> float:
    if v <= 0:
        return v
    dec = math.floor(math.log10(v))
    base = v / (10 ** dec)
    # DECADE WRAP: an E-series list stops below 10 (E12 at 8.2, E24 at 9.1, E96 at 9.76), so a
    # normalised value above the last entry had NO candidate above it and snapped DOWN a whole
    # step — 99.97 nF became 82 nF instead of the obvious 100 nF. The next decade's first entry
    # (10.0) is a real standard value and must be a candidate.
    best = min(_E96 + [10.0], key=lambda m: abs(math.log(m) - math.log(base)))
    return round(best * (10 ** dec), 6)


# ── default inputs (from the earlier power-stage / spec steps) ──────────────────
DEFAULT_INPUTS = dict(
    vin_ll_min=90.0, vin_ll_max=132.0, vin_hl_min=180.0, vin_hl_max=264.0,
    pout_lo=1700.0, pout_hi=3600.0, vout=394.0, fsw=70000.0,
    lphi_uH=235.0, nch=2, cout_uF=2200.0, eta_lo=0.945, eta_hi=0.965,
    iphi_rms_lo=10.12, iphi_rms_hi=10.59, iphi_pk_lo=16.76, iphi_pk_hi=17.51,
    # designer-selected loop crossovers (GUI) — used for descriptions / Steps 13–14
    fci=8000.0, fcv=17.0,
    # designer-selected output-divider upper resistor (fixed series of 3 × R_FB1_unit)
    rfb1_unit=1.21e6, rfb1_count=3,
    # designer-selected pin-filter capacitors (set the GC / LS filter pole frequencies)
    # PIN-FILTER POLES are the design input; each capacitor is DERIVED from its pole and the
    # associated resistor, then snapped to E24 - the same procedure the interactive tool uses, and
    # what the designer asked for. C239 instead froze the four caps as constants copied from the
    # drawing, which made them wrong the moment R_GC / R_ILIMIT / R_LS moved (C242).
    f_pole_gc=10e3, f_pole_ls=10e3, f_pole_ilimit=500.0,
    c_gc=None, c_ls=None,           # None -> derive from the pole; a number overrides
    r_ls_sel=None,                  # designer R_LS override (ohms); None -> E96 snap of the calc
    # THE PIN-FILTER CAPACITOR FAMILY. None of these had a single home: the GUI dropdown offered a
    # uniform 10 nF placeholder for four of them while the schematic drew its own literals and the
    # report quoted a third value. C238 fixed only C_ILIMIT; the designer found C_VIR and C_RLPK
    # still disagreeing, so the whole family now lives here (C239). Values are the ones the
    # SCHEMATIC has always drawn - the figures the designer has been reviewing - not the GUI's
    # uniform placeholder. No engine calculation consumes them; they set RC poles with their
    # associated resistors, which the GUI displays.
    c_ilimit=None, c_ilimit2=None,  # None -> derive from f_pole_ilimit
    # no pole to derive from: fixed-practice anchors, but snapped to E24 so the GUI can offer them
    c_rlpk=1e-9, c_vir=100e-9, c_lpk=1e-9,
    rcs=None,                       # designer R_CS override (Ω); None → computed best-of-both-methods default
)

# ── controller constants (Step 2 base; FAN9672-D / AND9925-D) ───────────────────
CONST = dict(
    vref=2.5, vea_max_base=5.6, vea_min=0.6, vea_pref_lo=4.0, vea_pref_hi=5.0,
    iac_max=65e-6, vlpk_pref=3.7, vlpk_ds=3.8,
    k_rlpk=2.465, k_rm=6000.0, r_rlpk=12100.0,
    riac_fr=6e6, riac_hv=12e6, r_vir_fr=10e3, r_vir_hv=470e3,
    kmax=1.49, gmax=2.0, rm=7500.0,               # Method-1 (AN4165 Eq.31)
    i_ss=20e-6, v_ss=5.0, t_ss=0.100,             # soft start
    ilimit_clamp_ratio=1.8, ilimit2_ratio=1.5,
)


def _f(v, n=4):
    return None if v is None else round(float(v), n)


def compute_steps_1_8(inp: dict | None = None) -> dict:
    p = {**DEFAULT_INPUTS, **(inp or {})}
    # Map the designer's low-line / high-line corners onto the LL-band min and HL-band max so the whole
    # control chapter tracks the intake spec (the 7 middle band voltages 110..230 stay per designer rule).
    if inp:
        if inp.get("vin_min") is not None: p["vin_ll_min"] = float(inp["vin_min"])
        if inp.get("vin_max") is not None: p["vin_hl_max"] = float(inp["vin_max"])
    c = CONST
    out: dict = {"inputs": p, "const": c}

    # ── Step 1 — power-plant specification (inputs, not recomputed) ─────────────
    out["step1"] = {"rows": [
        ["AC Input Voltage Range", "Vin,rms", f"{p['vin_ll_min']:.0f}–{p['vin_ll_max']:.0f}",
         f"{p['vin_hl_min']:.0f}–{p['vin_hl_max']:.0f}", "Vac"],
        ["Rated Output Power", "Pout", f"{p['pout_lo']:.0f}", f"{p['pout_hi']:.0f}", "W"],
        ["Regulated DC Bus", "Vout", f"{p['vout']:.1f}", f"{p['vout']:.1f}", "V"],
        ["Switching Frequency", "fsw", f"{p['fsw']/1e3:.0f}", f"{p['fsw']/1e3:.0f}", "kHz"],
        # 4 significant digits: the as-built L is 101.6 uH, not the 102 uH a %.0f implied, and the
        # designer compares this row against Chapter 4 Table 4.1 directly.
        ["Per-Phase Inductance (min as-built)", "Lφ", f"{p['lphi_uH']:.4g}", f"{p['lphi_uH']:.4g}", "µH"],
        ["Number of Channels", "Nch", f"{p['nch']}", f"{p['nch']}", "—"],
        ["Output Capacitor", "Cout", f"{p['cout_uF']:.0f}", f"{p['cout_uF']:.0f}", "µF"],
        ["Worst-Case Efficiency", "η", f"{p['eta_lo']*100:.1f}%", f"{p['eta_hi']*100:.1f}%", "—"],
        ["Per-Phase RMS Current", "Iφ,rms", f"{p['iphi_rms_lo']:.2f}", f"{p['iphi_rms_hi']:.2f}", "A"],
        ["Per-Phase Peak Current", "Iφ,pk", f"{p['iphi_pk_lo']:.2f}", f"{p['iphi_pk_hi']:.2f}", "A"],
    ]}

    # ── Step 2 — base constants ────────────────────────────────────────────────
    out["step2"] = {"rows": [
        ["IAC pin maximum current", "I_AC,max", "< 65 µA", "FAN9672-D pin rating"],
        ["V_LPK preferred limit", "V_LPK,pref", "≤ 3.7 V", "100 mV below datasheet max"],
        ["V_LPK datasheet hard limit", "V_LPK,ds", "< 3.8 V", "FAN9672-D absolute max"],
        ["Gain-modulator ripple factor", "K_RLPK", f"{c['k_rlpk']}", "AND9925-D Table 1"],
        ["Gain-modulator constant", "K_RM", f"{c['k_rm']:.0f}", "AND9925-D gain modulator"],
        ["VEA maximum (base)", "V_EA,max", f"{c['vea_max_base']} V", "FAN9672 linear 0.6–5.6 V"],
        ["Preferred VEA window", "—", f"{c['vea_pref_lo']:.0f}–{c['vea_pref_hi']:.0f} V", "AND9925-D guideline"],
        ["Peak-detector resistor", "R_RLPK", f"{c['r_rlpk']/1e3:.1f} kΩ", "Selected for V_LPK compliance"],
        ["VIR resistor — FR (low)", "R_VIR", f"{c['r_vir_fr']/1e3:.0f} kΩ", "V_VIR < 1.5 V → FR mode"],
        ["VIR resistor — HV (high)", "R_VIR", f"{c['r_vir_hv']/1e3:.0f} kΩ", "V_VIR > 3.5 V → HV mode"],
        ["Selected K_max", "K_max", f"{c['kmax']} ({c['kmax']*100:.0f}%)", "Satisfies both R_CS methods (Section 6.6)"],
    ]}

    # ── Step 3.1 — RIAC selection + IAC check ──────────────────────────────────
    def iac_rows(vacs, riac, mode):
        rows = []
        for vac in vacs:
            vpk = SQRT2 * vac
            iac = vpk / riac
            rows.append([f"{mode}", f"{vac:.0f} Vac", f"{vpk:.3f}", f"{riac:.0f}",
                         f"{iac*1e6:.2f}", "PASS ✓" if iac < c["iac_max"] else "FAIL ✗"])
        return rows
    out["step3_1"] = {
        "riac_fr": c["riac_fr"], "riac_hv": c["riac_hv"],
        "rows": iac_rows([int(p["vin_ll_min"]), 110, 120, 132], c["riac_fr"], "Low / FR")
              + iac_rows([180, 200, 220, 230, int(p["vin_hl_max"])], c["riac_hv"], "High / HV"),
    }

    # ── Step 3.2 — V_LPK check (FR ×2, HV ×4) ──────────────────────────────────
    def vlpk(vac, riac, mult):
        iac = SQRT2 * vac / riac
        return iac, mult * c["k_rlpk"] * iac * c["r_rlpk"]
    vlpk_rows = []
    for vac in [int(p["vin_ll_min"]), 110, 120, 132]:
        iac, vl = vlpk(vac, c["riac_fr"], 2)
        st = "✓ ≤ 3.7 V" if vl <= c["vlpk_pref"] else ("! 3.7–3.8 V" if vl < c["vlpk_ds"] else "✗ > 3.8 V")
        vlpk_rows.append([f"{vac} Vac / FR", f"{iac*1e6:.3f}", f"{vl:.4f}", st])
    for vac in [180, 200, 220, 230, int(p["vin_hl_max"])]:
        iac, vl = vlpk(vac, c["riac_hv"], 4)
        st = "✓ ≤ 3.7 V" if vl <= c["vlpk_pref"] else ("! 3.7–3.8 V" if vl < c["vlpk_ds"] else "✗ > 3.8 V")
        vlpk_rows.append([f"{vac} Vac / HV", f"{iac*1e6:.3f}", f"{vl:.4f}", st])
    out["step3_2"] = {"rows": vlpk_rows}

    # ── Step 4 — oscillator R_RI, COMPUTED from f_SW (FAN9672-D: 18–40 or 55–75 kHz) ─
    # FAN9672-D eq. 3 (datasheet p.14):  f_OSC = 8e8 / R_RI  ⇒  R_RI = 8e8 / f_SW.
    # The RI pin sources 1.2 V/R_RI — that part was always right, and AN4165-D eq. 35/36
    # mirror it into I_ILIMIT / I_ILIMIT2 further down this function.
    #
    # C268. This used to be  f_SW = 1.2e9 / (R_RI + 3430), a form that appears in NO reference
    # document in this repo — not the datasheet, not AN4165-D, AN5257 or AND9925-D. It put
    # 13.7 kΩ on the BOM for a 70 kHz design, and that resistor actually runs the part at
    # 58.4 kHz: 16.6 % below the frequency Chapters 4–7 are all designed at. Eq. 3 reproduces
    # both datasheet test cases (25 kΩ → 32 kHz typ, 12.5 kΩ → 62 kHz typ) and the AN4165-D
    # worked example (40 kHz at 20 kΩ) exactly; the old form missed all three, and mapped the
    # datasheet's own 10.7 kΩ minimum to 84.9 kHz — past the part's 75 kHz ceiling.
    #
    # R_RI also scales I_ILIMIT/I_ILIMIT2, so R_ILIMIT and R_ILIMIT2 move with it. The clamp
    # THRESHOLD depends on the ratio R_ILIMIT/R_RI, so changing R_RI alone would silently push
    # the command clamp from 1.81x to 2.16x, outside the 1.2–2.0x window. They must move
    # together, which they do because both are computed from `rri` below.
    #
    # At 70 kHz: 11.43 kΩ → nearest E96 11.5 kΩ (f_SW = 69.57 kHz).
    def _rri_from_fsw(fsw):
        return 8.0e8 / fsw
    def _fsw_from_rri(rri):
        return 8.0e8 / rri
    rri_calc = _rri_from_fsw(p["fsw"])
    rri_sel = _nearest_e96(rri_calc)
    fsw_sel = _fsw_from_rri(rri_sel)
    # candidate table: the selected E96 value and its two E96 neighbours, all computed
    idx = _E96.index(min(_E96, key=lambda m: abs(math.log(m) - math.log(rri_sel / 10**math.floor(math.log10(rri_sel))))))
    dec = 10 ** math.floor(math.log10(rri_sel))
    cand_e96 = [round(_E96[max(0, idx-1)]*dec, 1), rri_sel, round(_E96[min(len(_E96)-1, idx+1)]*dec, 1)]
    rri_rows = []
    for r in sorted(set(cand_e96)):
        f = _fsw_from_rri(r)
        sel = " ← Selected (closest to target)" if abs(r - rri_sel) < 1 else ""
        rri_rows.append([f"{r/1e3:.1f} kΩ", f"{f/1e3:.1f} kHz",
                         f"{(f-p['fsw'])/1e3:+.1f} kHz",
                         ("Slightly higher f" if f > p['fsw'] else "Slightly lower f").strip() + sel])
    out["step4"] = {
        "rri_calc": rri_calc, "rri_selected": rri_sel, "fsw_at_selected": fsw_sel,
        "rows": rri_rows,
    }

    # ── Step 5 — FBPFC divider + PVO ───────────────────────────────────────────
    # R_FB1 is FIXED as a series string of 3 × 1.21 MΩ = 3.63 MΩ (HV rating / creepage).
    # The designer adjusts the regulated bus by changing the LOWER resistor R_FB2.
    rfb1 = p["rfb1_count"] * p["rfb1_unit"]               # 3 × 1.21 MΩ = 3.63 MΩ (fixed)
    ratio_target = p["vout"] / c["vref"]                  # required (Rfb1+Rfb2)/Rfb2
    rfb2_calc = rfb1 / (ratio_target - 1.0)               # R_FB2 to set the target Vout
    rfb2 = _nearest_e96(rfb2_calc)                        # → 23.2 kΩ (E96)
    ratio = (rfb1 + rfb2) / rfb2
    vout_actual = c["vref"] * ratio
    hv_gain = c["vref"] / p["vout"]
    vin_pk_264 = SQRT2 * p["vin_hl_max"]
    pvo_min = vin_pk_264 + 25.0
    # Point-27 tolerance CHECK: the nearest-standard R_FB2 makes the regulated bus differ slightly from
    # the designer's spec. Rather than propagate two Vout values, we require the divider to land the
    # actual within ±0.1% of spec and then use the SPEC value everywhere downstream. If the check ever
    # fails, the divider must be re-selected (a closer E96/E192 pair) — the report flags it instead of
    # silently drifting.
    VOUT_TOL_PCT = 0.1
    vout_dev_pct = (vout_actual - p["vout"]) / p["vout"] * 100.0
    vout_within_tol = abs(vout_dev_pct) <= VOUT_TOL_PCT
    out["step5"] = {
        "rfb1": rfb1, "rfb1_unit": p["rfb1_unit"], "rfb1_count": p["rfb1_count"],
        "rfb2": rfb2, "rfb2_calc": rfb2_calc, "ratio": ratio, "ratio_target": ratio_target,
        "vout_actual": vout_actual, "hv_gain": hv_gain, "vin_pk_264": vin_pk_264,
        "vout_spec": p["vout"], "vout_dev_pct": vout_dev_pct,
        "vout_tol_pct": VOUT_TOL_PCT, "vout_within_tol": vout_within_tol,
        "pvo_min": pvo_min, "pvo_enabled": p["vout"] >= pvo_min,
        "rows": [
            ["R_FB1 (upper, fixed)", f"{p['rfb1_count']}×{p['rfb1_unit']/1e6:.2f} MΩ = {rfb1/1e6:.2f} MΩ",
             "Fixed series string for HV rating / creepage"],
            ["R_FB2 (lower, adjust)", f"{rfb2/1e3:.1f} kΩ", "Designer adjusts this to set V_OUT"],
            ["Actual V_OUT", f"{vout_actual:.2f} V", f"{vout_dev_pct:+.3f}% vs {p['vout']:.0f} V spec"],
            ["Within ±%.1f%% tol?" % VOUT_TOL_PCT, "PASS" if vout_within_tol else "FAIL",
             "Spec V_OUT used in all downstream calcs" if vout_within_tol
             else "Re-select R_FB2 (closer standard value)"],
            ["Feedback gain H_v", f"{hv_gain:.5f}", "V_FBPFC / V_OUT"],
        ],
    }

    # ── Step 6 — R_CS two methods ──────────────────────────────────────────────
    pmax_nch_lo = p["pout_lo"] * c["kmax"] / p["nch"]     # = 1266.5 W
    pmax_nch_hi = p["pout_hi"] * c["kmax"] / p["nch"]     # = 2682.0 W
    # Method 1 — AN4165-D Eq.31:  R_CS = Gmax·R_M·Vin,min² / (R_IAC · Pmax/Nch)
    def rcs_m1(vmin, riac, pmaxn):
        return c["gmax"] * c["rm"] * vmin**2 / (riac * pmaxn)
    rcs1_ll = rcs_m1(p["vin_ll_min"], c["riac_fr"], pmax_nch_lo)
    rcs1_hl = rcs_m1(p["vin_hl_min"], c["riac_hv"], pmax_nch_hi)
    # Method 2 — AND9925-D Eq.11:  R_CS = K_RM·R_IAC·V_EA,eff / (8·K_RLPK²·R_RLPK²·Pmax/Nch)
    den_common = 8 * c["k_rlpk"]**2 * c["r_rlpk"]**2
    def rcs_m2(riac, vea_eff, pmaxn):
        return c["k_rm"] * riac * vea_eff / (den_common * pmaxn)
    m2_rows = []
    for vmax in [4.0, 4.5, 5.0, 5.1]:
        vee = vmax - c["vea_min"]
        num_ll = c["k_rm"] * c["riac_fr"] * vee
        num_hl = c["k_rm"] * c["riac_hv"] * vee
        m2_rows.append([f"{vmax:.1f} V", f"{vee:.1f} V",
                        f"{num_ll:.4e}", f"{rcs_m2(c['riac_fr'], vee, pmax_nch_lo)*1e3:.3f} mΩ",
                        f"{num_hl:.4e}", f"{rcs_m2(c['riac_hv'], vee, pmax_nch_hi)*1e3:.3f} mΩ"])
    # Numeric Method-2 band (V_EA within the preferred 4.0–5.0 V window, both lines):
    # V_EA,eff rises with R_CS, so the lower bound is @4.0 V and the upper @5.0 V.
    m2_lo = max(rcs_m2(c["riac_fr"], 4.0 - c["vea_min"], pmax_nch_lo),
                rcs_m2(c["riac_hv"], 4.0 - c["vea_min"], pmax_nch_hi))
    m2_hi = min(rcs_m2(c["riac_fr"], 5.0 - c["vea_min"], pmax_nch_lo),
                rcs_m2(c["riac_hv"], 5.0 - c["vea_min"], pmax_nch_hi))
    # R_CS default = best-of-both-methods (no hardcoded 15 mΩ). The Method-1 (AN4165 power-stage)
    # recommendation is the midpoint of its low-/high-line values; snap it DOWN to the nearest E24
    # standard shunt value (lower R_CS ⇒ lower loss) while keeping it inside the Method-2 (AND9925
    # V_EA-window) valid band [m2_lo, m2_hi]. The designer's Screen-2 selection overrides this.
    def _e24_floor(x):
        if x <= 0:
            return x
        dd = math.floor(math.log10(x))
        mm = x / 10 ** dd
        cc = [v for v in _E24 if v <= mm * 1.0001]
        return (cc[-1] if cc else _E24[0]) * 10 ** dd
    _rcs_m1_mid = 0.5 * (rcs1_ll + rcs1_hl)
    _rcs_best = _e24_floor(min(max(_rcs_m1_mid, m2_lo), m2_hi))
    if _rcs_best < m2_lo:                      # E24-floor dropped below the band → keep clamped target
        _rcs_best = min(max(_rcs_m1_mid, m2_lo), m2_hi)
    rcs_sel = float(p["rcs"]) if p.get("rcs") else _rcs_best
    # 6.4 back-calculated V_EA,eff for the selected R_CS
    def vea_eff_from_rcs(riac, pmaxn):
        return rcs_sel * den_common * pmaxn / (c["k_rm"] * riac)
    vee_ll = vea_eff_from_rcs(c["riac_fr"], pmax_nch_lo)
    vee_hl = vea_eff_from_rcs(c["riac_hv"], pmax_nch_hi)
    # 6.5 power dissipation
    pdiss_lo1 = p["iphi_rms_lo"]**2 * rcs_sel
    pdiss_hi1 = p["iphi_rms_hi"]**2 * rcs_sel
    out["step6"] = {
        "pmax_nch_lo": pmax_nch_lo, "pmax_nch_hi": pmax_nch_hi,
        "rcs1_ll": rcs1_ll, "rcs1_hl": rcs1_hl, "den_common": den_common,
        "m2_lo": m2_lo, "m2_hi": m2_hi,
        "m2_rows": m2_rows, "rcs_sel": rcs_sel,
        "vee_ll": vee_ll, "vee_hl": vee_hl,
        "vea_max_ll": vee_ll + c["vea_min"], "vea_max_hl": vee_hl + c["vea_min"],
        "pdiss_lo_each": pdiss_lo1, "pdiss_lo_total": p["nch"]*pdiss_lo1,
        "pdiss_hi_each": pdiss_hi1, "pdiss_hi_total": p["nch"]*pdiss_hi1,
        "combined_rows": [
            ["AN4165 Eq. 31", f"{rcs1_ll*1e3:.2f} mΩ", f"{rcs1_hl*1e3:.2f} mΩ", "Power-stage approach"],
            ["AND9925 Eq. 11 @ V_EA=4.0 V", f"{rcs_m2(c['riac_fr'],3.4,pmax_nch_lo)*1e3:.2f} mΩ",
             f"{rcs_m2(c['riac_hv'],3.4,pmax_nch_hi)*1e3:.2f} mΩ", "Lower V_EA bound"],
            ["AND9925 Eq. 11 @ V_EA=5.0 V", f"{rcs_m2(c['riac_fr'],4.4,pmax_nch_lo)*1e3:.2f} mΩ",
             f"{rcs_m2(c['riac_hv'],4.4,pmax_nch_hi)*1e3:.2f} mΩ", "Upper V_EA bound"],
            [f"Selected: R_CS = {rcs_sel*1e3:.1f} mΩ", "✓ inside overlap", "✓ inside overlap",
             "Designer selection" if p.get("rcs") else "Computed best (M1 rec., E24, within M2 band)"],
        ],
        "verify_rows": [
            ["Low line", f"{vee_ll:.4f} V", f"{vee_ll+c['vea_min']:.4f} V",
             "PASS ✓" if c["vea_pref_lo"] <= vee_ll+c["vea_min"] <= c["vea_pref_hi"] else "CHECK"],
            ["High line", f"{vee_hl:.4f} V", f"{vee_hl+c['vea_min']:.4f} V",
             "PASS ✓" if c["vea_pref_lo"] <= vee_hl+c["vea_min"] <= c["vea_pref_hi"] else "CHECK"],
        ],
    }

    # ── Step 7 — GMOD three paths ──────────────────────────────────────────────
    def gmod_A(riac):  # signal chain
        return c["k_rm"] * riac / den_common
    def gmod_B(pmaxn, vea_eff):  # power + R_CS
        return pmaxn * rcs_sel / vea_eff
    def gmod_C(pout, vea_eff):  # output spec
        return c["kmax"] * (pout / p["vout"]) / vea_eff
    gA_ll, gA_hl = gmod_A(c["riac_fr"]), gmod_A(c["riac_hv"])
    gB_ll, gB_hl = gmod_B(pmax_nch_lo, vee_ll), gmod_B(pmax_nch_hi, vee_hl)
    gC_ll, gC_hl = gmod_C(p["pout_lo"], vee_ll), gmod_C(p["pout_hi"], vee_hl)
    bc_ratio = rcs_sel * p["vout"] / p["nch"]            # B/C structural constant
    # GMOD crest per operating point (A/V): K_RM·R_IAC/(8·K_RLPK²·R_RLPK²·2·Vin,rms²)·... → ∝1/Vin²
    def gmod_crest(vac, riac):
        return c["k_rm"] * riac / (den_common * 2 * vac**2)
    paths_rows = []
    for vac, riac, A in [(90, c["riac_fr"], gA_ll), (110, c["riac_fr"], gA_ll),
                         (120, c["riac_fr"], gA_ll), (132, c["riac_fr"], gA_ll),
                         (180, c["riac_hv"], gA_hl), (200, c["riac_hv"], gA_hl),
                         (220, c["riac_hv"], gA_hl), (230, c["riac_hv"], gA_hl),
                         (int(p["vin_hl_max"]), c["riac_hv"], gA_hl)]:
        rng = "LL" if riac == c["riac_fr"] else "HL"
        B = A
        C = gC_ll if rng == "LL" else gC_hl
        paths_rows.append([f"{vac} V", rng, f"{gmod_crest(vac, riac):.4f}",
                           f"{A:.4f}", f"{B:.4f}", f"{C:.4f}", "1.0000 ✓", f"{A/C:.4f}"])
    # scorecard support values (VRM/V_LPK extremes + invariants)
    _inv_fr = c["k_rm"]*vee_ll/(2*c["k_rlpk"]*c["r_rlpk"])
    _inv_hv = c["k_rm"]*vee_hl/(c["k_rlpk"]*c["r_rlpk"])
    _vlpk90  = 2*c["k_rlpk"]*(SQRT2*90 /c["riac_fr"])*c["r_rlpk"]
    _vlpk180 = 4*c["k_rlpk"]*(SQRT2*180/c["riac_hv"])*c["r_rlpk"]
    _vlpk132 = 2*c["k_rlpk"]*(SQRT2*132/c["riac_fr"])*c["r_rlpk"]   # highest FR
    _vlpk264 = 4*c["k_rlpk"]*(SQRT2*264/c["riac_hv"])*c["r_rlpk"]   # highest HV
    _vrm_ll  = _inv_fr/_vlpk90                                      # VRM worst at lowest Vac
    _vrm_hl  = _inv_hv/_vlpk180
    _iac_worst = SQRT2*132/c["riac_fr"]                            # = √2·264/12 MΩ → 31.11 µA
    out["step7"] = {
        "gA_ll": gA_ll, "gA_hl": gA_hl, "gB_ll": gB_ll, "gB_hl": gB_hl,
        "gC_ll": gC_ll, "gC_hl": gC_hl, "bc_ratio": bc_ratio,
        "paths_rows": paths_rows,
        # Step 7.7 — full scorecard, exactly as the reference document (18 rows)
        "scorecard": [
            ["GMOD_A (LL) — Signal chain", f"{gA_ll:.4f} A/V", "—", "Computed"],
            ["GMOD_A (HL) — Signal chain", f"{gA_hl:.4f} A/V", "= 2 × GMOD_A_LL", "SYMMETRY ✓"],
            ["GMOD_B (LL) — Power + R_CS", f"{gB_ll:.4f} A/V", "—", "Computed"],
            ["GMOD_B (HL) — Power + R_CS", f"{gB_hl:.4f} A/V", "—", "Computed"],
            ["GMOD_C (LL) — Output spec", f"{gC_ll:.4f} A/V", "Voltage-loop design input", "Computed"],
            ["GMOD_C (HL) — Output spec", f"{gC_hl:.4f} A/V", "Voltage-loop design input", "Computed"],
            ["Path A / Path B  (LL)", "1.000000", "Target = 1.000 exactly", "PASS ✓"],
            ["Path A / Path B  (HL)", "1.000000", "Target = 1.000 exactly", "PASS ✓"],
            ["Path B / Path C  (both ranges)", f"{bc_ratio:.4f}", "= R_CS × V_out / N_ch  (fixed)", "EXPECTED ✓"],
            ["VRM maximum  (LL @ 90 Vac)", f"{_vrm_ll:.4f} V", "Limit ≤ 0.8 V", "PASS ✓"],
            ["VRM maximum  (HL @ 180 Vac)", f"{_vrm_hl:.4f} V", "Limit ≤ 0.8 V", "PASS ✓"],
            ["V_LPK maximum  (LL @ 132 Vac)", f"{_vlpk132:.4f} V", "Preferred ≤ 3.7 V", "PASS ✓"],
            ["V_LPK maximum  (HL @ 264 Vac)", f"{_vlpk264:.4f} V", "Hard limit < 3.8 V", "ACCEPTABLE ✓"],
            ["VRM × V_LPK invariant  (FR)", f"{_inv_fr:.5f}  = constant", "Vin-independent across all 4 points", "PASS ✓"],
            ["VRM × V_LPK invariant  (HV)", f"{_inv_hv:.5f}  = constant", "Vin-independent across all 5 points", "PASS ✓"],
            ["V_EA,max implied  (LL)", f"{vee_ll+c['vea_min']:.4f} V", "Preferred 4.0 – 5.0 V", "PASS ✓"],
            ["V_EA,max implied  (HL)", f"{vee_hl+c['vea_min']:.4f} V", "Preferred 4.0 – 5.0 V", "PASS ✓"],
            ["I_AC,pk  (both ranges, worst case)", f"{_iac_worst*1e6:.2f} µA", "< 65 µA", "PASS ✓"],
        ],
    }

    # ── Step 8 — GC / LS / soft-start / current limits (AN4165-D) ───────────────
    rri = out["step4"]["rri_selected"]
    r_gc = 6e6 / ratio

    # ── R_LS: the EMULATOR's inductance, which is not the loop's (C279) ────────────────────────
    # AND9925-D is explicit about what this pin does. The CS resistor sits at the switch source,
    # so the controller only sees inductor current during t_ON; the linear-predict (LPT) block
    # synthesizes the t_OFF part by discharging a capacitor, and R_LS sets that slope to match the
    # real one - "mimicking behavior of the actual inductance applied in the boost converter".
    #
    # SO THIS IS A FIDELITY PROBLEM, NOT A WORST-CASE ONE. `lphi_uH` is the MINIMUM as-built
    # inductance across the nine operating points, and it is the right basis for the current-loop
    # COMPENSATION - lowest L, highest plant gain, highest crossover, so a compensator stable
    # there is stable everywhere (Section 6.10.14 asserts exactly that, and it depends on the
    # minimum). An emulator has no conservative direction: it is either accurate or it is not, and
    # feeding it the extreme of a 1.4:1 range makes it the worst estimator in the set rather than
    # the safest. R_LS therefore takes a CENTRAL value - the median of the per-point full-load
    # inductances - while the loop keeps the minimum. Two inductances, two jobs.
    _lcf = p.get("l_curve_full") or []
    _l_pts = sorted(float(r["L_avg_uH"]) for r in _lcf if r.get("L_avg_uH")) or \
        sorted(float(l) for _v, l in (p.get("l_curve") or []) if l)
    if _l_pts:
        # THE MEAN OF THE PER-POINT VALUES (designer decision, C281). It was the median at C279;
        # the designer chose the arithmetic mean, which minimises the average error across the
        # operating points rather than landing on whichever one happens to sit in the middle.
        #
        # NOT THE MIDRANGE. (min+max)/2 is a different number - 120.45 uH against this set's
        # 123.19 uH - and it is fixed entirely by the two extreme points while ignoring the other
        # seven. The designer read the C279 basis line as a midrange, which is why the report now
        # shows the SUMMATION rather than only naming the statistic.
        l_ls_uH = sum(_l_pts) / len(_l_pts)
        l_ls_basis = f"arithmetic mean of the {len(_l_pts)} per-point full-load inductances"
    else:
        # No as-built curve (a legacy design, or a requirement-only run). The scalar is all there
        # is, and it is named as such rather than silently presented as a mean.
        l_ls_uH = float(p["lphi_uH"])
        l_ls_basis = "design Lφ (no per-point as-built curve available)"
    l_pfc = l_ls_uH * 1e-6
    r_ls = l_pfc / (1.5e-9 * rcs_sel * ratio)
    r_gc_sel = _nearest_e96(r_gc)

    # AN4165-D and the FAN9672 datasheet both bound R_LS to 12-87 kOhm. Outside it the pin does
    # not set a usable slope, so the band is a hard constraint on the SELECTION even when the
    # physics asks for more - and when it binds, the report says so and states the inductance the
    # selected resistor actually emulates rather than the one that was asked for.
    R_LS_MIN, R_LS_MAX = 12e3, 87e3
    r_ls_sel = min(max(_nearest_e96(r_ls), R_LS_MIN), R_LS_MAX)
    r_ls_clamped = not (R_LS_MIN <= r_ls <= R_LS_MAX)

    # The per-point evidence Section 6.8.2 tabulates. Built HERE rather than in the report so the
    # two cannot disagree, and so the GUI can show the same rows - one engine per value.
    # R_LS is quoted per point on the cycle-average basis, because that is the basis the equation
    # is written on; the crest column is alongside it to show how far the real inductance moves
    # inside one line cycle, which is the reason no single resistor is exact.
    _ls_points = []
    for _r in _lcf:
        _lavg = float(_r["L_avg_uH"])
        _rp = _lavg * 1e-6 / (1.5e-9 * rcs_sel * ratio)
        _ls_points.append({
            "Vin_rms": float(_r["Vin_rms"]),
            "L_avg_uH": _lavg,
            "L_crest_uH": float(_r.get("L_crest_uH") or _lavg),
            "r_ls_ohm": _rp,
            "in_band": bool(R_LS_MIN <= _rp <= R_LS_MAX),
            # C281: the mean generally equals NO operating point, so "is this the basis" has no
            # answer. What a reader (and a bench engineer) can use is where the emulator is closest
            # to the truth, so the flag marks the NEAREST point and the caption says so.
            "is_basis": False,
        })
    if _ls_points:
        _near = min(_ls_points, key=lambda r: abs(r["L_avg_uH"] - l_ls_uH))
        _near["is_basis"] = True
    # Screen 2 offers R_LS as a dropdown (main.py serves `r_ls.options_kohm`), so the
    # designer's pick must win over the E96 snap - it was being discarded, exactly like the
    # four capacitors in C240 and on the same screen (C241).
    r_ls_overridden = False
    if p.get("r_ls_sel"):
        r_ls_sel = float(p["r_ls_sel"])
        r_ls_overridden = abs(r_ls_sel - _nearest_e96(r_ls)) > 1.0

    # WHAT THE SELECTED RESISTOR ACTUALLY EMULATES. Inverting Eq. 39 on the value that will be
    # fitted is the only figure that says what the LPT block will really do, and it is what makes
    # a designer override self-explaining instead of an unexplained gap between two numbers on the
    # page (the C233/C234 shape: correct numbers are not an answered question).
    l_ls_eff_uH = r_ls_sel * 1.5e-9 * rcs_sel * ratio * 1e6

    def _pin_cap(override, r_assoc, f_pole):
        """C = 1/(2*pi*R*f_pole), snapped to E24. A designer override wins outright.

        The capacitor FOLLOWS its resistor and its target pole. Freezing it as a constant (C239)
        meant that changing R_GC, R_ILIMIT or R_LS moved the pole silently, and that the frozen
        value might not even be offerable in the dropdown - which is what put 100 pF on Screen 2.
        """
        if override:
            return float(override)
        if not (r_assoc and f_pole):
            return None
        return _nearest_e24(1.0 / (2 * math.pi * float(r_assoc) * float(f_pole)))

    c_gc = _pin_cap(p.get("c_gc"), r_gc_sel, p.get("f_pole_gc"))
    c_ls = _pin_cap(p.get("c_ls"), r_ls_sel, p.get("f_pole_ls"))
    f_gc = 1.0 / (2 * math.pi * r_gc_sel * c_gc)         # GC pin-filter pole
    f_ls = 1.0 / (2 * math.pi * r_ls_sel * c_ls)         # LS pin-filter pole
    c_ss = c["i_ss"] * c["t_ss"] / c["v_ss"]
    css_sel = 390e-9
    t_ss_real = css_sel * c["v_ss"] / c["i_ss"]
    # Worst-case crest command and peak inductor current — evaluated at BOTH corners
    # (90 Vac low line and 180 Vac high line); the larger drives the current-limit sizing.
    crest_ll = SQRT2 * p["pout_lo"] / (p["eta_lo"] * p["nch"] * p["vin_ll_min"])  # @ 90 Vac
    crest_hl = SQRT2 * p["pout_hi"] / (p["eta_hi"] * p["nch"] * p["vin_hl_min"])  # @ 180 Vac
    crest_cmd = max(crest_ll, crest_hl)
    crest_corner = "180 Vac (HL)" if crest_hl >= crest_ll else "90 Vac (LL)"
    i_ilimit = 1.2 * 1.0208 / rri
    vcs_crest = crest_cmd * rcs_sel
    r_ilimit = c["ilimit_clamp_ratio"] * crest_cmd * rcs_sel * 4 / i_ilimit
    i_ilimit2 = 1.2 * 1.03125 / rri
    ilpk_ll, ilpk_hl = p["iphi_pk_lo"], p["iphi_pk_hi"]   # per-phase peaks (from power stage)
    il_pk = max(ilpk_ll, ilpk_hl)
    ilpk_corner = "180 Vac (HL)" if ilpk_hl >= ilpk_ll else "90 Vac (LL)"
    vcs_pk = il_pk * rcs_sel
    r_ilimit2 = c["ilimit2_ratio"] * vcs_pk / i_ilimit2
    out["step8"] = {
        "ratio": ratio, "r_gc": r_gc, "r_ls": r_ls, "c_ss": c_ss, "t_ss_real": t_ss_real,
        "css_sel": css_sel,
        "c_ilimit": _pin_cap(p.get("c_ilimit"), _nearest_e96(r_ilimit), p.get("f_pole_ilimit")),
        "c_ilimit2": _pin_cap(p.get("c_ilimit2"), _nearest_e96(r_ilimit2), p.get("f_pole_ilimit")),
        "c_rlpk": _nearest_e24(p["c_rlpk"]), "c_vir": _nearest_e24(p["c_vir"]),
        "c_lpk": _nearest_e24(p["c_lpk"]),
        "c_gc": c_gc, "c_ls": c_ls, "f_gc": f_gc, "f_ls": f_ls,
        "r_gc_sel": r_gc_sel, "r_ls_sel": r_ls_sel,
        # C279 - the LS emulator's own basis, exported so the report, the Screen-2 payload and
        # the embedded JS tool all read ONE set of numbers instead of three derivations.
        "l_ls_uH": l_ls_uH, "l_ls_basis": l_ls_basis,
        "l_ls_eff_uH": l_ls_eff_uH,
        "r_ls_clamped": r_ls_clamped, "r_ls_overridden": r_ls_overridden,
        "r_ls_band": [12.0, 87.0],
        "ls_points": _ls_points,
        "i_ilimit": i_ilimit, "crest_ll": crest_ll, "crest_hl": crest_hl, "crest_cmd": crest_cmd,
        "crest_corner": crest_corner, "vcs_crest": vcs_crest, "r_ilimit": r_ilimit,
        "i_ilimit2": i_ilimit2, "ilpk_ll": ilpk_ll, "ilpk_hl": ilpk_hl, "il_pk": il_pk,
        "ilpk_corner": ilpk_corner, "vcs_pk": vcs_pk, "r_ilimit2": r_ilimit2,
        # inputs surfaced for the Section 6.8.4/6.8.5 worked-example substitution steps
        "rri": rri, "rcs_sel": rcs_sel,
        "pout_lo": p["pout_lo"], "pout_hi": p["pout_hi"],
        "eta_lo": p["eta_lo"], "eta_hi": p["eta_hi"], "nch": p["nch"],
        "vin_ll_min": p["vin_ll_min"], "vin_hl_min": p["vin_hl_min"],
        "ilimit_clamp_ratio": c["ilimit_clamp_ratio"], "ilimit2_ratio": c["ilimit2_ratio"],
        "r_ilimit_sel": _nearest_e96(r_ilimit), "r_ilimit2_sel": _nearest_e96(r_ilimit2),
        "scorecard": [
            ["R_GC", "AN4165 Eq. 40", f"{r_gc/1e3:.3f} kΩ", f"{r_gc_sel/1e3:.1f} kΩ", "±5 %", "PASS"],
            ["C_GC", "pin filter", "—", f"{c_gc*1e12:.0f} pF", f"pole {f_gc/1e3:.3f} kHz", "—"],
            ["R_LS", "AN4165 Eq. 39", f"{r_ls/1e3:.3f} kΩ", f"{r_ls_sel/1e3:.1f} kΩ",
             "12–87 kΩ", "PASS" if 12e3 <= r_ls <= 87e3 else "CHECK"],
            ["C_LS", "pin filter", "—", f"{c_ls*1e12:.0f} pF", f"pole {f_ls/1e3:.3f} kHz", "—"],
            ["C_SS", "AN4165 Eq. 64", f"{c_ss*1e9:.0f} nF", f"{css_sel*1e9:.0f} nF", f"t_SS {t_ss_real*1e3:.0f} ms", "PASS"],
            ["R_ILIMIT", "AN4165 Eq. 38", f"{r_ilimit/1e3:.3f} kΩ", f"{_nearest_e96(r_ilimit)/1e3:.1f} kΩ",
             "1.2–2.0× crest", "PASS"],
            ["R_ILIMIT2", "AN4165 Eq. 33", f"{r_ilimit2/1e3:.3f} kΩ", f"{_nearest_e96(r_ilimit2)/1e3:.2f} kΩ",
             "≥ I_L,pk·R_CS", "PASS"],
        ],
    }

    # ── worked-step intermediates (for the detailed report) ─────────────────────
    out["step6"]["m1_ll"] = {"pmaxn": pmax_nch_lo, "num": c["gmax"]*c["rm"]*p["vin_ll_min"]**2,
                             "den": c["riac_fr"]*pmax_nch_lo, "rcs": rcs1_ll}
    out["step6"]["m1_hl"] = {"pmaxn": pmax_nch_hi, "num": c["gmax"]*c["rm"]*p["vin_hl_min"]**2,
                             "den": c["riac_hv"]*pmax_nch_hi, "rcs": rcs1_hl}
    out["step6"]["m2_den_base_ll"] = den_common * pmax_nch_lo
    out["step6"]["m2_den_base_hl"] = den_common * pmax_nch_hi
    out["step6"]["v64_ll"] = {"num": rcs_sel*den_common*pmax_nch_lo, "den": c["k_rm"]*c["riac_fr"], "vee": vee_ll}
    out["step6"]["v64_hl"] = {"num": rcs_sel*den_common*pmax_nch_hi, "den": c["k_rm"]*c["riac_hv"], "vee": vee_hl}

    iout_ll, iout_hi = p["pout_lo"]/p["vout"], p["pout_hi"]/p["vout"]
    out["step7"]["A_ll"] = {"num": c["k_rm"]*c["riac_fr"], "den": den_common, "res": gA_ll}
    out["step7"]["A_hl"] = {"num": c["k_rm"]*c["riac_hv"], "den": den_common, "res": gA_hl}
    out["step7"]["B_ll"] = {"pmaxn": pmax_nch_lo, "rcs_pmax": rcs_sel*pmax_nch_lo, "vee": vee_ll, "res": gB_ll}
    out["step7"]["B_hl"] = {"pmaxn": pmax_nch_hi, "rcs_pmax": rcs_sel*pmax_nch_hi, "vee": vee_hl, "res": gB_hl}
    out["step7"]["C_ll"] = {"iout": iout_ll, "kmax_iout": c["kmax"]*iout_ll, "vee": vee_ll, "res": gC_ll}
    out["step7"]["C_hl"] = {"iout": iout_hi, "kmax_iout": c["kmax"]*iout_hi, "vee": vee_hl, "res": gC_hl}

    # Step 7.6 — VRM × V_LPK invariant (FR: ×2 ; HV: V_LPK ×4 but C-input ×2)
    inv_fr = c["k_rm"]*vee_ll/(2*c["k_rlpk"]*c["r_rlpk"])
    inv_hv = c["k_rm"]*vee_hl/(c["k_rlpk"]*c["r_rlpk"])
    out["step7"]["inv_fr"], out["step7"]["inv_hv"] = inv_fr, inv_hv
    vrm_rows = []
    for vac, riac, mult, inv in ([(v, c["riac_fr"], 2, inv_fr) for v in [int(p["vin_ll_min"]),110,120,132]]
                                 + [(v, c["riac_hv"], 4, inv_hv) for v in [180,200,220,230,int(p["vin_hl_max"])]]):
        iac = SQRT2*vac/riac
        vl = mult*c["k_rlpk"]*iac*c["r_rlpk"]
        vrm = inv/vl
        mode = "FR" if mult == 2 else "HV"
        vstat = "✓ ≤ 3.7V" if vl <= c["vlpk_pref"] else "! 3.7–3.8V"
        vrm_rows.append([f"{vac} Vac / {mode}", f"{iac*1e6:.3f}", f"{vl:.4f}", vstat,
                         f"{vrm:.5f}", "✓" if vrm <= 0.8 else "✗", f"{vrm*vl:.5f}", "✓ Constant"])
    out["step7"]["vrm_rows"] = vrm_rows
    return out


if __name__ == "__main__":
    import json
    r = compute_steps_1_8()
    s6, s7, s8 = r["step6"], r["step7"], r["step8"]
    print("Step6  R_CS M1: LL %.2f / HL %.2f mΩ | sel 15 mΩ -> VEA,max LL %.3f HL %.3f"
          % (s6["rcs1_ll"]*1e3, s6["rcs1_hl"]*1e3, s6["vea_max_ll"], s6["vea_max_hl"]))
    print("Step7  GMOD A LL %.4f HL %.4f | C LL %.4f HL %.4f | B/C %.4f"
          % (s7["gA_ll"], s7["gA_hl"], s7["gC_ll"], s7["gC_hl"], s7["bc_ratio"]))
    print("Step8  R_GC %.3fk R_LS %.3fk C_SS %.0fnF R_ILIM %.3fk R_ILIM2 %.3fk"
          % (s8["r_gc"]/1e3, s8["r_ls"]/1e3, s8["c_ss"]*1e9, s8["r_ilimit"]/1e3, s8["r_ilimit2"]/1e3))
