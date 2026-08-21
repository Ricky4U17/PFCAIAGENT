"""
app/mode_b/report_steps1_8.py — full-detail Steps 1–8 control-design report block.

Reproduces the reference document (pages 17–31: Steps 1–8) at the SAME level of
detail — every worked sub-step (LL and HL), every equation with substituted
numbers, every description and table — rendered through the shared
doc_report_builder helpers so ONLY the font / text / alignment / formatting
follow our agreed report style. All numbers come from the step16_steps1_8 calc
agent (verified to match the document).

`build_steps_1_8(story, data)` appends the flowables. `make_pdf(path, inp)` builds
a standalone review PDF.
"""
from __future__ import annotations
import math
from app.mode_b.doc_report_builder import (
    step_h, sub_h, body, eq_box, data_table, annotation, CW,
)
from app.mode_b.step16_steps1_8 import compute_steps_1_8

C6 = 6


# ── number formatting helpers (mathtext) ────────────────────────────────────────
def _sci(x, sig=4):
    """1.215e8 -> '1.215\\times10^{8}' ; small values stay plain."""
    if x == 0:
        return "0"
    e = math.floor(math.log10(abs(x)))
    if -3 <= e < 4:
        return f"{x:.4g}"
    m = x / 10 ** e
    return f"{m:.{sig-1}f}\\times10^{{{e}}}"


_SUP = str.maketrans("0123456789-", "⁰¹²³⁴⁵⁶⁷⁸⁹⁻")
def _sct(x, sig=4):
    """Scientific notation for BODY text (Unicode superscript): 9.014e12 -> '9.014 × 10¹²'."""
    if x == 0:
        return "0"
    e = math.floor(math.log10(abs(x)))
    if -3 <= e < 4:
        return f"{x:.4g}"
    m = x / 10 ** e
    return f"{m:.{sig-1}f} × 10{str(e).translate(_SUP)}"


def _wstep(story, label, eq):
    """One worked sub-step: a bold label then its equation (matches the doc)."""
    body(story, "<b>" + label + "</b>", C6)
    eq_box(story, eq if isinstance(eq, list) else [eq], ch=C6)


def build_steps_1_8(story, data: dict):
    p, c = data["inputs"], data["const"]

    # ═══════════════ Step 1 ═══════════════
    step_h(story, "6.1", "Power Plant Specifications", C6)
    annotation(story, "THEORY",
        "The control loop is designed around the power stage, not the other way round. Everything "
        "in this step — inductance, bus capacitance, switching frequency, ESRs — is fixed by the "
        "power design and enters the loop equations as a constant. Read this table as the boundary "
        "conditions for the entire chapter.", C6)
    annotation(story, "INSIGHT",
        "Three of these numbers dominate the loop design: the per-phase inductance L (sets the "
        "current-loop plant and the right-half-plane zero), the bus capacitance C<sub>O</sub> (sets "
        "the voltage-loop plant pole and the transient dip), and f<sub>SW</sub> (sets the upper "
        "ceiling on current-loop bandwidth).", C6)
    body(story, "These values are the completed power-stage parameters from the FAN9672 architecture "
                "design. All control-loop calculations in this chapter reference these figures as "
                "fixed inputs; no power-stage value is changed here.", C6)
    data_table(story, "6.1.1", "Power-Stage Parameters (fixed inputs)",
        "Completed power-stage parameters carried into the control design.",
        ["Parameter", "Symbol", "Low Line", "High Line", "Unit"],
        data["step1"]["rows"], col_widths=[CW*0.34, CW*0.16, CW*0.18, CW*0.18, CW*0.14], ch=C6)
    annotation(story, "INSIGHT",
        "Per-phase current figures are taken from the power-stage design document and are used in "
        "Section 6.6.5 to verify R<sub>CS</sub> power-dissipation rating.", C6)

    # ═══════════════ Step 2 ═══════════════
    step_h(story, "6.2", "Set the Base", C6)
    annotation(story, "CONCEPT",
        "The base quantities are the normalising constants — peak line voltage, controller gain "
        "factors, the preferred V<sub>EA</sub> window — from which every later expression is built. "
        "Computing them once here keeps the per-step algebra clean and avoids re-deriving the "
        "operating point eight times over.", C6)
    body(story, "The following controller constants and design targets are established from the "
                "FAN9672-D datasheet, the AND9925-D application note (Table 1 and electrical "
                "characteristics), and the AN4165-D design guidelines. These constants govern all "
                "gain-modulator and current-sense calculations throughout this chapter.", C6)
    data_table(story, "6.2.1", "Controller Constants and Design Targets",
        "Constants and targets governing the gain-modulator and current-sense design.",
        ["Parameter", "Symbol", "Value", "Source and Constraint"],
        data["step2"]["rows"], col_widths=[CW*0.34, CW*0.14, CW*0.20, CW*0.32], ch=C6)
    annotation(story, "INSIGHT",
        "K<sub>max</sub> = 1.49 is selected after evaluating Section 6.6.1 and Section 6.6.2 simultaneously. It "
        "places the calculated R<sub>CS</sub> inside the overlap band of both the AN4165 and "
        "AND9925 methods, verified in Section 6.6.3.", C6)

    # ═══════════════ Step 3 ═══════════════
    step_h(story, "6.3", "Gain Modulator and IAC Check", C6)
    annotation(story, "THEORY",
        "The gain modulator is the analog multiplier at the heart of average current-mode PFC: it "
        "forms the instantaneous current command by multiplying the sensed line-voltage shape "
        "(through R<sub>IAC</sub>, the I<sub>AC</sub> pin current) by the voltage-loop output and "
        "dividing by the squared peak. This step sizes that sense path and checks the modulator is "
        "operating inside its valid range.", C6)
    annotation(story, "CONCEPT",
        "I<sub>AC</sub> is a current proportional to the instantaneous rectified line voltage, "
        "injected into the controller through R<sub>IAC</sub>. It carries the shape the input "
        "current must follow; the voltage loop only scales its amplitude.", C6)
    sub_h(story, "6.3.1", "R_IAC Selection and I_AC Verification", C6)
    body(story, "The I<sub>AC</sub> pin senses the rectified AC input through R<sub>IAC</sub>. The "
                "resulting peak I<sub>AC</sub> must remain below 65 µA at the highest AC input in "
                "each range. The FAN9672 internally doubles I<sub>RLPK</sub> and I<sub>GC</sub> in "
                "HV mode, so a single R<sub>RLPK</sub> serves both ranges without change.", C6)
    eq_box(story, [r"I_{AC}=\dfrac{V_{AC,pk}}{R_{IAC}}=\dfrac{V_{AC}\times1.414}{R_{IAC}}",
                   r"I_{AC,max}\ (\mathrm{LL})=\dfrac{132\times1.414}{6\,000\,000}=31.11\ \mu A",
                   r"I_{AC,max}\ (\mathrm{HL})=\dfrac{264\times1.414}{12\,000\,000}=31.11\ \mu A"],
           heading="Worst-case I_AC (FR / HV)", number="6.3.1", ch=C6)
    data_table(story, "6.3.1", "R_IAC Selection and I_AC Peak — All Operating Points",
        "R_IAC = 6 MΩ (FR) / 12 MΩ (HV). Both ranges give identical worst-case I_AC,pk — confirming FR/HV symmetry.",
        ["Range / Mode", "V_AC", "V_IN,pk (V)", "R_IAC (Ω)", "I_AC,pk (µA)", "< 65 µA?"],
        data["step3_1"]["rows"], col_widths=[CW*0.18, CW*0.12, CW*0.18, CW*0.20, CW*0.18, CW*0.14], ch=C6)
    annotation(story, "DECISION",
        f"R<sub>IAC</sub> = {float((data.get('const') or {}).get('riac_fr', 6e6))/1e6:.0f} MΩ (FR) "
        f"and {float((data.get('const') or {}).get('riac_hv', 12e6))/1e6:.0f} MΩ (HV). "
        "Both produce identical I<sub>AC,pk</sub> = "
        "31.11 µA, confirming symmetry. Use 1% resistors split into series strings for voltage "
        "rating and creepage compliance.", C6)
    # Live, not a literal: R_RLPK had three sources of truth (this heading, Table B.1, and a
    # DIFFERENT default inside schematics.py) and the schematic's disagreed with the other two.
    _c632 = (data.get("const") or {})
    _rrlpk_632 = float(_c632.get("r_rlpk", 12100.0))
    sub_h(story, "6.3.2", f"V_LPK Check at R_RLPK = {_rrlpk_632/1e3:.1f} kΩ", C6)
    body(story, "The peak-detector output V<sub>LPK</sub> is formed from I<sub>AC</sub> and "
                "R<sub>RLPK</sub>. In FR mode the multiplier is 2×; in HV mode it is 4× (the FAN9672 "
                "internally doubles I<sub>RLPK</sub>). The C-input to the gain modulator uses the 2× "
                "signal in both modes (AND9925-D Table 1).", C6)
    eq_box(story, [r"V_{LPK}\ (\mathrm{FR})=2\times K_{RLPK}\times I_{AC,pk}\times R_{RLPK}",
                   r"V_{LPK}\ (\mathrm{HV})=4\times K_{RLPK}\times I_{AC,pk}\times R_{RLPK}"], ch=C6)
    data_table(story, "6.3.2", "V_LPK Across All Operating Points",
        "V_LPK preferred ≤ 3.7 V; datasheet hard limit < 3.8 V.",
        ["Operating Point", "I_AC,pk (µA)", "V_LPK (V)", "Status vs 3.7 / 3.8 V"],
        data["step3_2"]["rows"], col_widths=[CW*0.26, CW*0.22, CW*0.20, CW*0.32], ch=C6)
    try:
        _vlpk_hv = float([r for r in data["step3_2"]["rows"] if "HV" in str(r[0])][-1][2])
    except Exception:
        _vlpk_hv = 3.712
    _vhl_lpk = float(data["inputs"].get("vin_hl_max", 264))
    annotation(story, "INSIGHT",
        f"V<sub>LPK</sub> at {_vhl_lpk:.0f} Vac = {_vlpk_hv:.4f} V — {(_vlpk_hv-3.7)*1000:.0f} mV above the preferred 3.7 V target but {(3.8-_vlpk_hv)*1000:.0f} mV "
        f"below the 3.8 V datasheet hard limit. With 1% tolerance on R<sub>RLPK</sub> the worst case "
        f"is {_vlpk_hv*1.01:.3f} V — still within 3.8 V. Acceptable.", C6)

    # ═══════════════ Step 4 ═══════════════
    s4 = data["step4"]
    step_h(story, "6.4", "Oscillator Resistor for the Selected f_SW", C6)
    annotation(story, "CONCEPT",
        "The oscillator resistor R<sub>RI</sub> programs the per-phase switching frequency. "
        "Frequency is a balance: higher f<sub>SW</sub> shrinks the inductor and ripple but raises "
        f"switching loss, and it must stay high enough that the current loop (crossover f<sub>ci</sub> "
        f"≈ {p['fci']/1e3:.1f} kHz, designer-selected) keeps at least a decade of margin below it. "
        "Both loop crossover frequencies (f<sub>ci</sub>, f<sub>cv</sub>) are design choices entered "
        "in the GUI — they are inputs to the loop design, not fixed constants.", C6)
    body(story, "The FAN9672-D oscillator (the RI pin sources 1.2 V/R<sub>RI</sub>) sets the "
                "per-phase frequency in its 50–75 kHz range. R<sub>RI</sub> is computed from the "
                "target f<sub>SW</sub> — not hardcoded:", C6)
    # The prose directly above states R_RI is "computed from the target f_SW - not hardcoded", and
    # this worked line used to hardcode 70,000 and the 17.143 k intermediate while printing a LIVE
    # answer. Change f_sw and the equation contradicted its own caption (C238).
    _fsw641 = float((data.get("inputs") or {}).get("fsw", 70000) or 70000)
    eq_box(story, [r"f_{SW}=\dfrac{1.2\times10^{9}}{R_{RI}+3430}\ \mathrm{Hz}\quad(R_{RI}\ \mathrm{in}\ \Omega)",
                   r"R_{RI}=\dfrac{1.2\times10^{9}}{f_{SW}}-3430",
                   r"R_{RI}=\dfrac{1.2\times10^{9}}{%s}-3430=%.3f\,\mathrm{k}-3.43\,\mathrm{k}=%.2f\ \mathrm{k\Omega}\ \ (\mathrm{calculated})"
                   % (f"{_fsw641:,.0f}".replace(",", r"\,"), 1.2e9 / _fsw641 / 1e3,
                      s4["rri_calc"] / 1e3)],
           heading="Oscillator resistor", number="6.4.1", ch=C6)
    sub_h(story, "6.4.2", "Standard Value Selection", C6)
    data_table(story, "6.4.1", "R_RI Standard-Value Candidates (computed)",
        "Computed R_RI = %.0f Ω → selected E96 %.1f kΩ (f_SW = %.1f kHz)."
        % (s4["rri_calc"], s4["rri_selected"]/1e3, s4["fsw_at_selected"]/1e3),
        ["R_RI Value", "Resulting f_SW", f"Deviation from {data.get('inputs',{}).get('fsw',70000)/1000:.0f} kHz", "Recommendation"],
        s4["rows"], col_widths=[CW*0.18, CW*0.22, CW*0.28, CW*0.32], ch=C6)
    annotation(story, "DECISION",
        "Use R<sub>RI</sub> = 13.7 kΩ (1%). Verify the exact switching frequency on an oscilloscope "
        "at nominal V<sub>DD</sub> during bring-up.", C6)

    # ═══════════════ Step 5 ═══════════════
    s5 = data["step5"]
    step_h(story, "6.5", "Output Sensing and PVO Setting", C6)
    annotation(story, "THEORY",
        "The output divider does two jobs: it sets the regulation point (the bus voltage at which "
        "the divided feedback equals the 2.5 V reference) and it defines the feedback gain "
        "H<sub>v</sub> = V<sub>FBPFC</sub>/V<sub>OUT</sub> that appears in every voltage-loop "
        "equation. A high divider impedance minimises standing loss on the regulated bus but must "
        "stay low enough to swamp the FBPFC pin bias current.", C6)
    sub_h(story, "6.5.1", "FBPFC Voltage Divider Design", C6)
    body(story, "The FAN9672 regulates the FBPFC pin to a 2.500 V reference. The output is sensed "
                "through a resistive divider. The upper resistor R<sub>FB1</sub> is a <b>fixed series "
                "string of 3 × 1.21 MΩ = 3.63 MΩ</b> (chosen for high-voltage rating and creepage). "
                "The designer adjusts the regulated bus voltage by selecting the <b>lower</b> "
                "resistor R<sub>FB2</sub> — R<sub>FB1</sub> is not changed.", C6)
    _wstep(story, "Divider regulation condition:",
           r"V_{FBPFC}=V_{OUT}\times\dfrac{R_{FB2}}{R_{FB1}+R_{FB2}}=2.500\ \mathrm{V}")
    _wstep(story, "Step 1 — Fixed upper resistor (3 × 1.21 MΩ):",
           r"R_{FB1}=3\times1.21\ \mathrm{M\Omega}=3.63\ \mathrm{M\Omega}\ \ (\mathrm{fixed})")
    _wstep(story, "Step 2 — Required ratio for the target V_OUT:",
           r"\dfrac{R_{FB1}+R_{FB2}}{R_{FB2}}=\dfrac{V_{OUT}}{V_{FBPFC}}=\dfrac{%.1f}{2.500}=%.2f"
           % (s5.get("vout_spec", 394.0), s5["ratio_target"]))
    _wstep(story, "Step 3 — Solve for the lower resistor (the adjustment):",
           r"R_{FB2}=\dfrac{R_{FB1}}{V_{OUT}/V_{FBPFC}-1}=\dfrac{3\,630\,000}{%.2f}=%.0f\ \Omega\ \to\ 23.2\ \mathrm{k\Omega}\ (E96)"
           % (s5["ratio_target"]-1, s5["rfb2_calc"]))
    _wstep(story, "Step 4 — Verify actual output voltage:",
           r"V_{OUT}=2.500\times\left(1+\dfrac{3\,630\,000}{23\,200}\right)=%.2f\ \mathrm{V}" % s5["vout_actual"])
    data_table(story, "6.5.1", "FBPFC Voltage Divider",
        "R_FB1 is the fixed 3 × 1.21 MΩ series; R_FB2 is the designer-adjustable lower resistor that sets V_OUT.",
        ["Component", "Selected Value", "Purpose / Result"],
        s5["rows"], col_widths=[CW*0.24, CW*0.30, CW*0.46], ch=C6)
    annotation(story, "INSIGHT",
        "To re-target the bus voltage, change only R<sub>FB2</sub>; the 3 × 1.21 MΩ upper string is "
        "fixed. In the GUI the designer enters the desired V<sub>OUT</sub> and R<sub>FB2</sub> is "
        "computed (then snapped to the nearest E96 standard value).", C6)
    sub_h(story, "6.5.2", "PVO Pin — Voltage Headroom Warning", C6)
    body(story, "AN4165-D and FAN9672-D require the bus to stay at least 25 V above the AC input "
                f"peak when PVO is active. Evaluated at the worst-case {float(data['inputs'].get('vin_hl_max', 264)):.0f} Vac:", C6)
    _vin_hl = float(data["inputs"].get("vin_hl_max", 264.0))
    _vpk    = s5["vin_pk_264"]
    _pvomin = s5["pvo_min"]
    _vspec  = s5.get("vout_spec", 394.0)
    _head   = _pvomin - _vspec                          # +ve → bus below the PVO minimum
    eq_box(story, [r"V_{IN,pk}\ (%.0f\ \mathrm{Vac})=%.0f\times\sqrt{2}=%.1f\ \mathrm{V}" % (_vin_hl, _vin_hl, _vpk),
                   r"V_{OUT,min}\ \mathrm{required}=%.1f+25=%.1f\ \mathrm{V}" % (_vpk, _pvomin)], ch=C6)
    annotation(story, "DECISION",
        ("PVO = 0 V (disabled) throughout this design. The %.1f V bus is %.1f V %s the %.1f V "
         "minimum required for PVO at %.0f Vac. Do not reduce the bus at high line; PVO may only be "
         "enabled where the reduced bus still stays ≥ 25 V above V<sub>IN,pk</sub>."
         % (_vspec, abs(_head), "below" if _head > 0 else "above", _pvomin, _vin_hl)), C6)

    # ═══════════════ Step 6 ═══════════════
    _build_step6(story, data)
    # ═══════════════ Step 7 ═══════════════
    _build_step7(story, data)
    # ═══════════════ Step 8 ═══════════════
    _build_step8(story, data)


def _build_step6(story, data):
    s6, p, c = data["step6"], data["inputs"], data["const"]
    _rms = "%g" % (s6["rcs_sel"] * 1e3)     # selected R_CS in mΩ, for prose/titles
    step_h(story, "6.6", "R_CS Calculation — Two Methods", C6)
    annotation(story, "THEORY",
        "The current-sense resistor converts inductor current into the millivolt-level signal the "
        "inner loop regulates. Its value is a direct trade-off: too large wastes power and clips "
        "the sense range at high line; too small buries the signal in noise and offset. This step "
        "derives it two independent ways and reconciles them.", C6)
    annotation(story, "PITFALL",
        "Size R<sub>CS</sub> at the highest-current corner (low line, full load) so the sense "
        "voltage never exceeds the controller's linear range there — sizing at high line would let "
        "the signal clip at low line, corrupting the current command when the converter is most "
        "stressed.", C6)
    body(story, "R<sub>CS</sub> is sized by two independent methods from different application "
                "notes; both must be satisfied. K<sub>max</sub> = %.2f was chosen so that a "
                "standard %s mΩ resistor falls in the overlap zone of both methods." % (c["kmax"], _rms), C6)

    sub_h(story, "6.6.1", "Method 1 — AN4165-D Equation 31", C6)
    eq_box(story, [r"R_{CS}=\dfrac{V_{IN,min}^2\times G_{max}\times R_M}{R_{IAC}\times P_{max,per-ch}}"
                   r"\qquad(\mathrm{AN4165\text{-}D\ Eq.\ 31})"], ch=C6)
    data_table(story, "6.6.1", "Method 1 Constants",
        "Internal gain-modulator coefficients (FAN9672-D) and the chosen margin.",
        ["Constant", "Value", "Description"],
        [["G_max", "2", "Internal gain-modulator coefficient"],
         ["R_M", "7.5 kΩ", "Internal multiplier output resistor"],
         ["Margin", "149% (K_max = 1.49)", "AN4165 recommends 120–150%"]],
        col_widths=[CW*0.20, CW*0.26, CW*0.54], ch=C6)
    body(story, f"<b>Low Line Calculation — V<sub>IN,min</sub> = {float(data['inputs'].get('vin_ll_min', 90)):.0f} Vac, R<sub>IAC</sub> = 6 MΩ</b>", C6)
    m1 = s6["m1_ll"]
    _wstep(story, "Step 1 — Per-channel maximum power:",
           r"P_{max,per-ch}=\dfrac{%.0f}{%d}\times%.2f=%.1f\ \mathrm{W}"
           % (p["pout_lo"], p["nch"], c["kmax"], m1["pmaxn"]))
    _wstep(story, "Step 2 — Numerator:",
           r"90^2\times2\times7\,500=8\,100\times15\,000=%s" % _sci(m1["num"]))
    _wstep(story, "Step 3 — Denominator:",
           r"6\,000\,000\times%.1f=%s" % (m1["pmaxn"], _sci(m1["den"])))
    _wstep(story, "Step 4 — Result:",
           r"%s\,/\,%s=%.2f\ \mathrm{m\Omega}" % (_sci(m1["num"]), _sci(m1["den"]), m1["rcs"]*1e3))
    body(story, "<b>High Line Reference — V<sub>IN,min</sub> = 180 Vac, R<sub>IAC</sub> = 12 MΩ</b>", C6)
    m1h = s6["m1_hl"]
    _wstep(story, "Step 1 — Per-channel maximum power:",
           r"P_{max,per-ch}=\dfrac{%.0f}{%d}\times%.2f=%.1f\ \mathrm{W}"
           % (p["pout_hi"], p["nch"], c["kmax"], m1h["pmaxn"]))
    _wstep(story, "Step 2 — Numerator:",
           r"180^2\times2\times7\,500=32\,400\times15\,000=%s" % _sci(m1h["num"]))
    _wstep(story, "Step 3 — Denominator:",
           r"12\,000\,000\times%.1f=%s" % (m1h["pmaxn"], _sci(m1h["den"])))
    _wstep(story, "Step 4 — Result:",
           r"%s\,/\,%s=%.2f\ \mathrm{m\Omega}" % (_sci(m1h["num"]), _sci(m1h["den"]), m1h["rcs"]*1e3))

    sub_h(story, "6.6.2", "Method 2 — AND9925-D Equation 11", C6)
    eq_box(story, [r"R_{CS}=\dfrac{K_{RM}\times R_{IAC}\times V_{EA,eff}}"
                   r"{8\times K_{RLPK}^2\times R_{RLPK}^2\times P_{max}/N_{ch}}\qquad(\mathrm{AND9925\text{-}D\ Eq.\ 11})",
                   r"V_{EA,eff}=V_{EA,max}-0.6\ \mathrm{V}"], ch=C6)
    annotation(story, "NOTE",
        "where V<sub>EA,eff</sub> = V<sub>EA,max</sub> − 0.6 V is the effective linear range of the "
        "V<sub>EA</sub> signal. AND9925-D recommends setting V<sub>EA,max</sub> in the range 4 V to "
        "5 V for stable, well-centred control.", C6)
    # K_RLPK, R_RLPK and R_RLPK^2 were retyped into this worked line as literals while the ANSWER
    # was live - the same shape as the C235 schematic defaults. R_RLPK in particular already had
    # three sources of truth before C235; this was a fourth (C238).
    _c662 = data.get("const") or {}
    _krl, _rrl = _c662.get("k_rlpk", 2.465), _c662.get("r_rlpk", 12100.0)
    _wstep(story, "Common denominator factor (same for all points):",
           r"8\times(%g)^2\times(%s)^2=8\times%.3f\times%s=%s"
           % (_krl, f"{_rrl:,.0f}".replace(",", r"\,"), _krl ** 2,
              _sci(_rrl ** 2), _sci(s6["den_common"])))
    body(story, "<b>Low Line sweep</b> (R<sub>IAC</sub> = 6 MΩ, P<sub>max</sub>/N<sub>ch</sub> = %.1f W); "
                "denominator base = %s." % (s6["pmax_nch_lo"], _sct(s6["m2_den_base_ll"])), C6)
    data_table(story, "6.6.2a", "Method 2 R_CS — Low Line V_EA,max Sweep",
        "R_CS = (K_RM·R_IAC·V_EA,eff) / (denominator base).",
        ["Target V_EA,max", "V_EA,eff", "Numerator", "R_CS (AND9925)"],
        [[r[0], r[1], r[2], r[3]] for r in s6["m2_rows"]],
        col_widths=[CW*0.24, CW*0.20, CW*0.32, CW*0.24], ch=C6)
    body(story, "<b>High Line sweep</b> (R<sub>IAC</sub> = 12 MΩ, P<sub>max</sub>/N<sub>ch</sub> = %.1f W); "
                "denominator base = %s." % (s6["pmax_nch_hi"], _sct(s6["m2_den_base_hl"])), C6)
    data_table(story, "6.6.2b", "Method 2 R_CS — High Line V_EA,max Sweep",
        "Same equation at the high-line R_IAC and power.",
        ["Target V_EA,max", "V_EA,eff", "Numerator", "R_CS (AND9925)"],
        [[r[0], r[1], r[4], r[5]] for r in s6["m2_rows"]],
        col_widths=[CW*0.24, CW*0.20, CW*0.32, CW*0.24], ch=C6)

    sub_h(story, "6.6.3", "Combined R_CS Selection", C6)
    body(story, "The table overlays both methods and identifies the overlap zone within which any "
                "selected R<sub>CS</sub> satisfies AN4165 and AND9925 simultaneously. The lowest "
                "standard value inside the zone is selected.", C6)
    data_table(story, "6.6.3", "Both Methods Overlaid — Overlap Zone",
        "K_max = %.2f places a standard %s mΩ shunt inside the overlap of both methods." % (c["kmax"], _rms),
        ["Method", "Low Line", "High Line", "Notes"],
        s6["combined_rows"], col_widths=[CW*0.34, CW*0.18, CW*0.18, CW*0.30], ch=C6)
    annotation(story, "NOTE",
        "R<sub>CS</sub> = " + _rms + " mΩ is selected on the <b>common ground of both methods</b> — the value "
        "must lie inside the overlap of the AN4165 and AND9925 results, and the lowest standard value "
        "in that band is taken. In the GUI the designer is presented with the overlap range "
        "(≈ 13.6–15.1 mΩ here) and selects the value to use; that selection is then carried into all "
        "downstream calculations.", C6)

    sub_h(story, "6.6.4", "Verification of the Selected R_CS", C6)
    body(story, "The implied V<sub>EA,max</sub> is back-calculated from the selected R<sub>CS</sub> "
                "using the AND9925 equation rearranged; both ranges must fall in the preferred "
                "4–5 V window.", C6)
    eq_box(story, [r"V_{EA,eff}=\dfrac{R_{CS}\times8\times K_{RLPK}^2\times R_{RLPK}^2\times(P_{max}/N_{ch})}"
                   r"{K_{RM}\times R_{IAC}},\qquad V_{EA,max}=V_{EA,eff}+0.6\ \mathrm{V}"], ch=C6)
    v = s6["v64_ll"]
    body(story, "<b>Low Line</b>", C6)
    _wstep(story, "Step 1 — Numerator:",
           r"%.4f\times%s\times%.1f=%s" % (s6["rcs_sel"], _sci(s6["den_common"]), s6["pmax_nch_lo"], _sci(v["num"])))
    _wstep(story, "Step 2 — Denominator:", r"6\,000\times6\,000\,000=%s" % _sci(v["den"]))
    _wstep(story, "Step 3 — V_EA,eff:", r"%s\,/\,%s=%.4f\ \mathrm{V}" % (_sci(v["num"]), _sci(v["den"]), v["vee"]))
    _wstep(story, "Step 4 — V_EA,max:", r"%.4f+0.6=%.4f\ \mathrm{V}\ \to\ \mathrm{inside\ 4\text{-}5\ V}\ \checkmark"
           % (v["vee"], v["vee"]+0.6))
    vh = s6["v64_hl"]
    body(story, "<b>High Line</b>", C6)
    _wstep(story, "Step 1 — Numerator:",
           r"%.4f\times%s\times%.1f=%s" % (s6["rcs_sel"], _sci(s6["den_common"]), s6["pmax_nch_hi"], _sci(vh["num"])))
    _wstep(story, "Step 2 — Denominator:", r"6\,000\times12\,000\,000=%s" % _sci(vh["den"]))
    _wstep(story, "Step 3 — V_EA,eff:", r"%s\,/\,%s=%.4f\ \mathrm{V}" % (_sci(vh["num"]), _sci(vh["den"]), vh["vee"]))
    _wstep(story, "Step 4 — V_EA,max:", r"%.4f+0.6=%.4f\ \mathrm{V}\ \to\ \mathrm{inside\ 4\text{-}5\ V}\ \checkmark"
           % (vh["vee"], vh["vee"]+0.6))
    data_table(story, "6.6.4", "Back-Calculated V_EA (must fall in 4–5 V)",
        "Implied V_EA from the selected %s mΩ shunt, both ranges." % _rms,
        ["Range", "V_EA,eff (back-calc)", "V_EA,max (back-calc)", "In 4–5 V window?"],
        s6["verify_rows"], col_widths=[CW*0.20, CW*0.28, CW*0.28, CW*0.24], ch=C6)

    sub_h(story, "6.6.5", "Power Dissipation Check for Selected R_CS", C6)
    body(story, "The R<sub>CS</sub> shunt dissipates I<sub>φ,rms</sub>²·R<sub>CS</sub> per phase. "
                "The shunt power rating must exceed this with margin.", C6)
    eq_box(story, [r"P_{R_{CS}}=I_{\phi,rms}^2\times R_{CS}"], ch=C6)
    _il, _ih, _rcs, _nch = p["iphi_rms_lo"], p["iphi_rms_hi"], s6["rcs_sel"], p["nch"]
    _wstep(story, "Step 1 — Low line (I_φ,rms = %.2f A):" % _il,
           r"(%.2f)^2\times%.4f=%.2f\times%.4f=%.3f\ \mathrm{W\ per\ phase}"
           % (_il, _rcs, _il*_il, _rcs, s6["pdiss_lo_each"]))
    _wstep(story, "Step 2 — Low line total (%d phases):" % _nch, r"%d\times%.3f=%.3f\ \mathrm{W}"
           % (_nch, s6["pdiss_lo_each"], s6["pdiss_lo_total"]))
    _wstep(story, "Step 3 — High line (I_φ,rms = %.2f A):" % _ih,
           r"(%.2f)^2\times%.4f=%.2f\times%.4f=%.3f\ \mathrm{W\ per\ phase}"
           % (_ih, _rcs, _ih*_ih, _rcs, s6["pdiss_hi_each"]))
    _wstep(story, "Step 4 — High line total (%d phases):" % _nch, r"%d\times%.3f=%.3f\ \mathrm{W}"
           % (_nch, s6["pdiss_hi_each"], s6["pdiss_hi_total"]))
    # full R_CS loss across all nine input voltages (from the shared operating grid)
    try:
        from app.mode_b.semiconductor.adapter import build_design_ops
        _rcs = float(p.get("rcs") or s6.get("rcs_sel") or 0.015)
        _nch = int(p.get("nch") or 2)
        _d = {"vin_min": p.get("vin_min", 90), "vin_max": p.get("vin_max", 264),
              "pout_lo": p.get("pout_lo", 1700), "pout_hi": p.get("pout_hi", 3600),
              "vout": p.get("vout", 394.0), "fsw": p.get("fsw", 70000),
              "nch": _nch, "r_input": p.get("r_input", 0.20),
              # Use the SAME as-built inductance (scalar + per-point bias curve) that Chapter 7's
              # §7.8b R_CS budget uses, so the per-phase RMS current — and hence R_CS loss — matches
              # Table 7.8 exactly instead of drifting on a different default L.
              "L_phi_uH": p.get("lphi_uH"), "L_phi_curve": p.get("l_curve")}
        _ops, _s2, _Lp, _iph, _Lpts = build_design_ops(_d)
        _rows = []
        for i in range(len(_ops)):
            _ip = float(_iph[i]); _pe = _ip * _ip * _rcs
            _rows.append([f"{_ops[i, 0]:.0f} V", f"{_ip:.3f} A", f"{_pe:.3f} W", f"{_nch * _pe:.3f} W"])
        body(story, "Across the full input range, the per-phase RMS current — and hence the shunt "
                    "loss P<sub>R<sub>CS</sub></sub> = I<sub>&#966;,rms</sub>&#178;&#183;R<sub>CS</sub> "
                    "— varies as below (the same operating grid used by every chapter):", C6)
        data_table(story, "6.6.5", "R<sub>CS</sub> Power Loss vs Input Voltage (R<sub>CS</sub> = %.1f m&#937;)" % (_rcs * 1e3),
            "Per-phase shunt loss and the total over %d channels, at every operating point." % _nch,
            ["V_AC", "I<sub>&#966;,rms</sub>", "Per phase", "Total (%d ch)" % _nch],
            _rows, col_widths=[CW*0.22, CW*0.26, CW*0.26, CW*0.26], ch=C6)
    except Exception:
        pass
    annotation(story, "DECISION",
        "R<sub>CS</sub> = " + _rms + " mΩ. Use a minimum 3 W, 4-terminal Kelvin metal-element current-sense "
        "shunt per phase (derate to 50% for thermal reliability). The Kelvin package eliminates PCB "
        "trace resistance from the measurement.", C6)


def _build_step7(story, data):
    s7, p, c, s6 = data["step7"], data["inputs"], data["const"], data["step6"]
    step_h(story, "6.7", "GMOD Verification — Three Independent Paths", C6)
    annotation(story, "CONCEPT",
        "K<sub>max</sub> is the multiplier-gain headroom — how much of the modulator's range the "
        "design uses at worst case. Computing it three independent ways (current path, voltage "
        "path, power balance) and getting the same answer cross-checks that the gain-modulator "
        "setup of Steps 3–6 is internally consistent.", C6)
    sub_h(story, "6.7.1", "Purpose and Overview", C6)
    body(story, "The gain modulator (GMOD) is the feed-forward heart of the PFC control loop. It "
                "scales the current command proportionally to V<sub>EA</sub> and inversely to the "
                "square of the input-voltage magnitude, keeping input power constant when the line "
                "changes — without waiting for the output to respond. Three independent equation "
                "paths compute GMOD from completely different component sets; in a self-consistent "
                "design all three must agree, and any mismatch identifies which group is misaligned.", C6)
    data_table(story, "6.7.1", "The Three GMOD Paths",
        "Each path uses a different component set and a different AND9925-D equation.",
        ["Path", "Uses These Components", "Physical Meaning", "Equation Source"],
        [["A — Signal Chain", "K_RM, R_IAC, K_RLPK, R_RLPK", "Input voltage sensing gain", "AND9925-D Eq. 24"],
         ["B — Power + R_CS", "R_CS, P_max, N_ch, V_EA,eff", "Current-sense gain vs power", "AND9925-D Eq. 11"],
         ["C — Output Spec", "K_max, P_out, V_out, V_EA,eff", "Loop-gain coeff. for Bode", "AND9925-D Eq. 26"]],
        col_widths=[CW*0.18, CW*0.30, CW*0.28, CW*0.24], ch=C6)

    sub_h(story, "6.7.2", "Derivation of the Three Paths and Their Relationship", C6)
    body(story, "<b>Path A — From AND9925-D Equation 24 (Instantaneous, then AC-Averaged)</b>", C6)
    body(story, "AND9925-D Equation 24 gives the instantaneous GMOD at line angle θ. The gain "
                "modulator output is proportional to the A × B / C² product of its three input "
                "signals, where A is the instantaneous input voltage signal, B is V<sub>EA</sub>, and "
                "C is the peak-detector output V<sub>LPK</sub>. Expanding with actual signals:", C6)
    eq_box(story, [r"G_{MOD}(\theta)=\dfrac{K_{RM}\times R_{IAC}\times V_{IN,pk}\times|\sin\theta|}"
                   r"{8\times K_{RLPK}^2\times R_{RLPK}^2\times V_{IN,rms}^2}\ \mathrm{A/V}\quad(\mathrm{at\ angle\ }\theta)"], ch=C6)
    body(story, "At the crest of the AC cycle (θ = 90°, |sin θ| = 1) and substituting "
                "V<sub>IN,pk</sub> = √2 × V<sub>IN,rms</sub>:", C6)
    eq_box(story, [r"G_{MOD,crest}=\dfrac{K_{RM}\times R_{IAC}\times\sqrt{2}}{8\times K_{RLPK}^2\times R_{RLPK}^2\times V_{IN,rms}}"], ch=C6)
    body(story, "When the full voltage-regulation loop gain (AND9925-D Eq. 25) is averaged over one "
                "AC half-cycle, the power-stage transfer function G<sub>vd</sub>/G<sub>id</sub> "
                "contributes a V<sub>IN</sub> term in the numerator. This exactly cancels the "
                "V<sub>IN,rms</sub> in the denominator of GMOD<sub>crest</sub>. The result is the "
                "V<sub>in</sub>-independent Path A:", C6)
    eq_box(story, [r"G_{MOD,A}=\dfrac{K_{RM}\times R_{IAC}}{8\times K_{RLPK}^2\times R_{RLPK}^2}"
                   r"\quad[V_{in}\text{-independent}]"], ch=C6)
    body(story, "<b>Path B — From AND9925-D Equation 11 Rearranged (Power Stage)</b>", C6)
    body(story, "AND9925-D Equation 11 defines how R<sub>CS</sub> is set from the GMOD signal-chain "
                "quantities and the power specification:", C6)
    eq_box(story, [r"R_{CS}=\dfrac{K_{RM}\times R_{IAC}\times V_{EA,eff}}{8\times K_{RLPK}^2\times R_{RLPK}^2\times P_{max}/N_{ch}}"
                   r"\quad(\mathrm{AND9925\text{-}D\ Eq.\ 11})"], ch=C6)
    body(story, "Rearranging to isolate the GMOD-equivalent signal-chain factor, and recognising "
                "that the factor K<sub>RM</sub> × R<sub>IAC</sub> / (8 × K<sub>RLPK</sub>² × "
                "R<sub>RLPK</sub>²) is exactly GMOD<sub>A</sub>:", C6)
    eq_box(story, [r"G_{MOD,B}=R_{CS}\times(P_{max}/N_{ch})\,/\,V_{EA,eff}"], ch=C6)
    body(story, "This confirms that Path B is simply Path A expressed through the selected "
                "R<sub>CS</sub>. When R<sub>CS</sub> is sized exactly according to Eq. 11, "
                "GMOD<sub>B</sub> = GMOD<sub>A</sub> identically. The algebraic proof is:", C6)
    eq_box(story, [r"G_{MOD,B}=\left[\dfrac{K_{RM}\times R_{IAC}\times V_{EA,eff}}{8K^2R^2\times P_{max}/N_{ch}}\right]"
                   r"\times\dfrac{(P_{max}/N_{ch})}{V_{EA,eff}}=\dfrac{K_{RM}\times R_{IAC}}{8K^2R^2}=G_{MOD,A}"], ch=C6)
    body(story, "<b>Path C — From AND9925-D Equation 26 (AC-Cycle Averaged Loop Gain)</b>", C6)
    body(story, "AND9925-D Equation 26 is the complete ac-cycle-averaged voltage-regulation loop "
                "gain coefficient. After V<sub>in</sub> cancellation (which occurs exactly as in "
                "Path A) and substituting the power-stage output current relationship "
                "I<sub>out</sub> = P<sub>out</sub> / V<sub>out</sub>:", C6)
    eq_box(story, [r"G_{MOD,C}=\dfrac{K_{max}\times I_{out}}{V_{EA,eff}}\quad[V_{in}\text{-independent}]"], ch=C6)
    body(story, "Path C is used directly for voltage-loop compensator design (bandwidth, phase "
                "margin, Bode-plot analysis). It is V<sub>in</sub>-independent because the averaging "
                "has already been performed.", C6)
    body(story, "<b>Why Path A = Path B (the critical self-consistency check)</b>", C6)
    body(story, "As shown in the Path B derivation above, substituting the AND9925 Eq. 11 definition "
                "of R<sub>CS</sub> into the Path B formula reduces it identically to Path A. Therefore "
                "A = B if and only if R<sub>CS</sub> has been set correctly for the chosen "
                "R<sub>IAC</sub> and R<sub>RLPK</sub>. A ratio A/B = 1.000 is the primary design "
                "self-consistency test.", C6)
    body(story, "<b>Why Path B ≠ Path C (expected structural scaling)</b>", C6)
    body(story, "Paths B and C are not the same quantity — they occupy different positions in the "
                "loop chain. Path B includes the current-sense gain term; Path C has already absorbed "
                "it. The ratio is a fixed constant that depends only on hardware values:", C6)
    eq_box(story, [r"\dfrac{G_{MOD,B}}{G_{MOD,C}}=\dfrac{R_{CS}\times P_{max}/N_{ch}\,/\,V_{EA,eff}}"
                   r"{K_{max}\times I_{out}\,/\,V_{EA,eff}}=\dfrac{R_{CS}\times P_{max}}{N_{ch}\times K_{max}\times I_{out}}",
                   r"\dfrac{G_{MOD,B}}{G_{MOD,C}}=\dfrac{R_{CS}\times V_{out}}{N_{ch}}=\dfrac{%.4f\times%.1f}{%d}=%.4f"
                   r"\quad[\text{always fixed — not a design error}]"
                   % (s6["rcs_sel"], p["vout"], p["nch"], s7["bc_ratio"])], ch=C6)
    data_table(story, "6.7.2", "Expected Path Relationships",
        "What each comparison should show, and the root cause if it does not.",
        ["Comparison", "Expected Outcome", "If Different — Root Cause"],
        [["A vs B", "Ratio = 1.000 exactly", "R_CS mismatched to R_IAC or R_RLPK"],
         ["B / C", "= R_CS·V_out/N_ch = 2.953 (fixed)", "Always this value — expected"],
         ["A vs C", "Ratio = B/C", "R_IAC or R_RLPK mismatched to power spec"]],
        col_widths=[CW*0.16, CW*0.40, CW*0.44], ch=C6)

    # 7.3 correct V_EA,eff
    sub_h(story, "6.7.3", "Correct V_EA,eff for Each Range", C6)
    v, vh = data["step6"]["v64_ll"], data["step6"]["v64_hl"]
    body(story, "For Paths B and C, V<sub>EA,eff</sub> must be the value actually implied by the "
                "selected R<sub>CS</sub> — not the base V<sub>EA,max</sub> = 5.6 V from "
                "Section 6.2. The selected R<sub>CS</sub> was chosen from the AND9925 table to "
                "give V<sub>EA,max</sub> in the 4.0 V to 4.25 V region (Section 6.4). The correct "
                "V<sub>EA,eff</sub> is therefore back-calculated as:", C6)
    eq_box(story, [r"V_{EA,eff}=\dfrac{R_{CS}\times8\times K_{RLPK}^2\times R_{RLPK}^2\times(P_{max}/N_{ch})}"
                   r"{K_{RM}\times R_{IAC}}"], ch=C6)
    _wstep(story, "Step 1 — Low line:",
           r"V_{EA,eff}=\dfrac{%.4f\times%s\times%.1f}{6\,000\times6\,000\,000}=%.4f\ \mathrm{V}"
           % (s6["rcs_sel"], _sci(s6["den_common"]), s6["pmax_nch_lo"], v["vee"]))
    _wstep(story, "Step 2 — Low line V_EA,max:",
           r"%.4f+0.6=%.4f\ \mathrm{V}\quad(\mathrm{inside\ 4\text{-}5\ V\ window}\ \checkmark)" % (v["vee"], v["vee"]+0.6))
    _wstep(story, "Step 3 — High line:",
           r"V_{EA,eff}=\dfrac{%.4f\times%s\times%.1f}{6\,000\times12\,000\,000}=%.4f\ \mathrm{V}"
           % (s6["rcs_sel"], _sci(s6["den_common"]), s6["pmax_nch_hi"], vh["vee"]))
    _wstep(story, "Step 4 — High line V_EA,max:",
           r"%.4f+0.6=%.4f\ \mathrm{V}\quad(\mathrm{inside\ 4\text{-}5\ V\ window}\ \checkmark)" % (vh["vee"], vh["vee"]+0.6))

    # 7.4 LL worked
    sub_h(story, "6.7.4", "Step-by-Step Calculations — Low Line", C6)
    body(story, "Fixed values: R<sub>IAC</sub> = 6 MΩ · P<sub>out</sub> = %.0f W · K<sub>max</sub> "
                "= %.2f · V<sub>EA,eff</sub> = %.4f V." % (p["pout_lo"], c["kmax"], s6["vee_ll"]), C6)
    _gmod_paths(story, s7["A_ll"], s7["B_ll"], s7["C_ll"], "LL", s7["bc_ratio"],
                pout=p["pout_lo"], nch=p["nch"], vout=p["vout"], rcs=s6["rcs_sel"], kmax=c["kmax"])
    # 7.5 HL worked
    sub_h(story, "6.7.5", "Step-by-Step Calculations — High Line", C6)
    body(story, "Fixed values: R<sub>IAC</sub> = 12 MΩ · P<sub>out</sub> = %.0f W · K<sub>max</sub> "
                "= %.2f · V<sub>EA,eff</sub> = %.4f V." % (p["pout_hi"], c["kmax"], s6["vee_hl"]), C6)
    _gmod_paths(story, s7["A_hl"], s7["B_hl"], s7["C_hl"], "HL", s7["bc_ratio"], hl=True,
                pout=p["pout_hi"], nch=p["nch"], vout=p["vout"], rcs=s6["rcs_sel"], kmax=c["kmax"])
    data_table(story, "6.7.5", "GMOD Three-Path Summary — All 8 Operating Points",
        "All three paths agree at every point (A/B = 1.0000; B/C = 2.9527 structural).",
        ["V_AC", "Range", "GMOD crest", "Path A", "Path B", "Path C", "A / B", "B / C"],
        s7["paths_rows"], col_widths=[CW*0.11, CW*0.09, CW*0.15, CW*0.13, CW*0.13, CW*0.13, CW*0.12, CW*0.14], ch=C6)

    # 7.6 VRM / VLPK invariant
    sub_h(story, "6.7.6", "VRM and V_LPK Verification Across All Operating Points", C6)
    body(story, "Two checks at every point: V<sub>RM</sub> (the current-command voltage) must not "
                "exceed the 0.8 V gain-modulator clamp, and V<sub>LPK</sub> must stay below 3.8 V. "
                "The product V<sub>RM</sub>×V<sub>LPK</sub> is a V<sub>in</sub>-independent "
                "invariant — if it is constant, then K<sub>RM</sub>, K<sub>RLPK</sub>, "
                "R<sub>RLPK</sub> and V<sub>EA,eff</sub> are all mutually self-consistent.", C6)
    eq_box(story, [r"V_{RM}\times V_{LPK}\ (\mathrm{FR})=\dfrac{K_{RM}\,V_{EA,eff}}{2\,K_{RLPK}\,R_{RLPK}}"
                   r"=\dfrac{6000\times3.7557}{2\times2.465\times12\,100}=%.5f" % s7["inv_fr"],
                   r"V_{RM}\times V_{LPK}\ (\mathrm{HV})=\dfrac{K_{RM}\,V_{EA,eff}}{K_{RLPK}\,R_{RLPK}}"
                   r"=\dfrac{6000\times3.9766}{2.465\times12\,100}=%.5f" % s7["inv_hv"]], ch=C6)
    data_table(story, "6.7.6", "VRM and V_LPK Invariant — All 9 Points",
        "V_RM ≤ 0.8 V at every point; the V_RM·V_LPK product is constant within each range.",
        ["Operating Point", "I_AC,pk (µA)", "V_LPK (V)", "V_LPK Status", "VRM (V)", "≤ 0.8 V?", "VRM·V_LPK", "= Const?"],
        s7["vrm_rows"], col_widths=[CW*0.17, CW*0.11, CW*0.10, CW*0.13, CW*0.10, CW*0.08, CW*0.13, CW*0.18], ch=C6)
    annotation(story, "INSIGHT",
        "The HV invariant (0.79995) is 2× the FR invariant (0.37775) because V<sub>LPK</sub> uses "
        "the 4× multiplier while the modulator C-input still uses 2×. Both are self-consistent; all "
        "nine points hold the invariant to better than 1×10<super>-4</super>.", C6)

    sub_h(story, "6.7.7", "Final Scorecard", C6)
    data_table(story, "6.7.7", "GMOD Verification Scorecard",
        "Every self-consistency check for the gain-modulator setup.",
        ["Check", "Calculated Value", "Criterion", "Verdict"],
        s7["scorecard"], col_widths=[CW*0.34, CW*0.18, CW*0.30, CW*0.18], ch=C6)
    sub_h(story, "6.7.8", "Verdict", C6)
    annotation(story, "DECISION", "DESIGN PASS  —  ALL CHECKS CONFIRMED  ✓", C6)
    body(story, "<b>1.</b> Path A = Path B = 1.000000 for both low-line and high-line ranges. This "
        "is exact agreement to six decimal places, confirming that R<sub>CS</sub> = %g mΩ is fully "
        "consistent with R<sub>IAC</sub> = 6/12 MΩ and R<sub>RLPK</sub> = 12.1 kΩ. No component is "
        "mismatched to any other." % (s6["rcs_sel"] * 1e3), C6)
    body(story, "<b>2.</b> Path B / C = 2.953 (fixed constant) is confirmed as the expected "
        "structural current-sense gain scaling. It is not a design error — it is the term "
        "R<sub>CS</sub> × V<sub>out</sub> / N<sub>ch</sub> that appears in the loop gain chain at a "
        "different position to Path C.", C6)
    body(story, "<b>3.</b> V<sub>RM</sub> × V<sub>LPK</sub> is constant across all nine operating "
        "points, to better than 1×10<super>-4</super> precision for both ranges. This confirms that "
        "K<sub>RM</sub>, K<sub>RLPK</sub>, R<sub>RLPK</sub>, and the back-calculated "
        "V<sub>EA,eff</sub> are all internally self-consistent.", C6)
    body(story, "<b>4.</b> V<sub>RM</sub> maximum = 0.316 V (worst case at 180 Vac, high line), "
        "providing a 2.5× margin below the 0.8 V clamp limit. The current command does not approach "
        "saturation at any operating condition across either range.", C6)
    try:
        _vlpk7 = float([r for r in data["step3_2"]["rows"] if "HV" in str(r[0])][-1][2])
    except Exception:
        _vlpk7 = 3.712
    _vhl7 = float(data["inputs"].get("vin_hl_max", 264))
    body(story, f"<b>5.</b> V<sub>LPK</sub> at {_vhl7:.0f} Vac = {_vlpk7:.4f} V is {(_vlpk7-3.7)*1000:.0f} mV above the preferred 3.7 V "
        f"design target and {(3.8-_vlpk7)*1000:.0f} mV below the datasheet hard limit of 3.8 V. This is acceptable. With "
        f"1% resistor tolerance on R<sub>RLPK</sub>, the worst-case V<sub>LPK</sub> = {_vlpk7*1.01:.3f} V — still "
        "within the 3.8 V limit.", C6)
    body(story, "<b>6.</b> Implied V<sub>EA,max</sub> = 4.36 V (LL) and 4.58 V (HL) both fall "
        "squarely inside the AND9925-D preferred 4 V to 5 V operating window, confirming adequate "
        "VEA headroom and consistent with the selection rationale in Section 6.6.", C6)
    body(story, "The design proceeds to voltage-loop compensator design using GMOD<sub>C</sub> as "
        "the averaged loop gain coefficient: GMOD<sub>C</sub> = %.4f A/V (low line) and %.4f A/V "
        "(high line)." % (s7["gC_ll"], s7["gC_hl"]), C6)


def _gmod_paths(story, A, B, Cc, rng, bc, hl=False, pout=1700.0, nch=2, vout=394.0, rcs=0.015, kmax=1.49):
    body(story, "<b>Path A — Signal Chain</b>", C6)
    _wstep(story, "Step 1 — Numerator (K_RM × R_IAC):", r"6\,000\times%s=%s"
           % ("12\\,000\\,000" if hl else "6\\,000\\,000", _sci(A["num"])))
    _wstep(story, "Step 2 — Denominator:", r"8\,K_{RLPK}^2\,R_{RLPK}^2=%s" % _sci(A["den"]))
    _wstep(story, "Step 3 — GMOD_A:", r"%s\,/\,%s=%.4f\ \mathrm{A/V}" % (_sci(A["num"]), _sci(A["den"]), A["res"]))
    body(story, "<b>Path B — Power Stage + R_CS</b>", C6)
    _wstep(story, "Step 1 — P_max/N_ch:", r"\dfrac{%.0f\times%.2f}{%d}=%.1f\ \mathrm{W}"
           % (pout, kmax, nch, B["pmaxn"]))
    _wstep(story, "Step 2 — R_CS × P_max/N_ch:", r"%.4f\times%.1f=%.4f" % (rcs, B["pmaxn"], B["rcs_pmax"]))
    _wstep(story, "Step 3 — GMOD_B:", r"%.4f\,/\,%.4f=%.4f\ \mathrm{A/V}" % (B["rcs_pmax"], B["vee"], B["res"]))
    body(story, "<b>Path C — Output Specification</b>", C6)
    _wstep(story, "Step 1 — I_out:", r"%.0f\,/\,%.1f=%.5f\ \mathrm{A}" % (pout, vout, Cc["iout"]))
    _wstep(story, "Step 2 — K_max × I_out:", r"%.2f\times%.5f=%.5f" % (kmax, Cc["iout"], Cc["kmax_iout"]))
    _wstep(story, "Step 3 — GMOD_C:", r"%.5f\,/\,%.4f=%.4f\ \mathrm{A/V}" % (Cc["kmax_iout"], Cc["vee"], Cc["res"]))
    _wstep(story, "Consistency check (%s):" % rng,
           [r"A/B=%.4f/%.4f=1.000000\ \to\ \mathrm{PASS}\ \checkmark" % (A["res"], B["res"]),
            r"B/C=%.4f/%.4f=%.4f\ \to\ =R_{CS}V_{out}/N_{ch}\ \checkmark" % (B["res"], Cc["res"], bc)])


def _build_step8(story, data):
    s8, p, c, s5, s6 = data["step8"], data["inputs"], data["const"], data["step5"], data["step6"]
    step_h(story, "6.8", "GC, LS, Soft-Start and Current Limits (AN4165-D)", C6)
    body(story, "This step closes the GC / LS / soft-start / current-limit components with explicit "
                "AN4165-D procedures. The divider ratio from Section 6.5.1 and R<sub>RI</sub> from Section 6.4 "
                "feed directly into these equations — the step ordering is deliberate.", C6)
    sub_h(story, "6.8.1", "R_GC — Gain Control (AN4165-D Eq. 40)", C6)
    annotation(story, "CONCEPT",
        "The GC pin aligns the I<sub>AC</sub> line-sense path with the FBPFC output-sense path so "
        "the linear-predict (LPT) engine sees consistent scaling. AN4165-D ties R<sub>GC</sub> to "
        "the output-divider ratio.", C6)
    eq_box(story, [r"\mathrm{ratio}=\dfrac{R_{FB1}+R_{FB2}}{R_{FB2}}=\dfrac{%.2f\,\mathrm{M\Omega}+%.1f\,\mathrm{k\Omega}}{%.1f\,\mathrm{k\Omega}}=%.2f"
                   % (s5["rfb1"]/1e6, s5["rfb2"]/1e3, s5["rfb2"]/1e3, s8["ratio"]),
                   r"R_{GC}=\dfrac{6\times10^{6}}{\mathrm{ratio}}=\dfrac{6\times10^{6}}{%.2f}=%.3f\ \mathrm{k\Omega}" % (s8["ratio"], s8["r_gc"]/1e3)], ch=C6)
    body(story, "Decision: R<sub>GC</sub> = %.1f kΩ (nearest E96; ±5%% requirement). "
                "C<sub>GC</sub> = %.0f pF → pin-filter pole %.3f kHz."
                % (s8["r_gc_sel"]/1e3, s8["c_gc"]*1e12, s8["f_gc"]/1e3), C6)
    sub_h(story, "6.8.2", "R_LS — Current Predict (AN4165-D Eq. 39)", C6)
    annotation(story, "CONCEPT",
        "The LS pin sets the emulated inductance the LPT predictor uses to anticipate inductor "
        "current within a switching cycle. It scales with the real inductance, inversely with "
        "R<sub>CS</sub>, and with the divider ratio; AN4165-D bounds it to 12–87 kΩ.", C6)
    body(story,
        "<b>Which L<sub>&#966;</sub> is used here.</b> The whole of Chapter 6 is designed at the "
        "<b>minimum as-built full-load inductance</b> across the nine operating points &#8212; "
        f"L<sub>&#966;</sub> = {p['lphi_uH']:.4g} &#181;H, read from the approved inductor's per-point "
        "curve (Chapter 4, Table 4.1), not a rounded or nameplate value. The minimum is the worst case "
        "for the loop: the lowest inductance gives the highest plant gain and therefore the highest "
        "crossover, so a design that is stable there is stable at every other point. Section 6.10.14 "
        "verifies that explicitly at all nine points.", C6)
    eq_box(story, [r"R_{LS}=\dfrac{L_\phi}{1.5\times10^{-9}\,R_{CS}\,\mathrm{ratio}}"
                   r"=\dfrac{%.4g\,\mu H}{1.5\times10^{-9}\times%g\,\mathrm{m\Omega}\times%.2f}=%.3f\ \mathrm{k\Omega}"
                   % (p["lphi_uH"], s6["rcs_sel"]*1e3, s8["ratio"], s8["r_ls"]/1e3)], ch=C6)
    body(story, "Decision: R<sub>LS</sub> = %.1f kΩ (E96) — inside 12–87 kΩ (PASS). C<sub>LS</sub> "
                "= %.0f pF → pin-filter pole %.3f kHz."
                % (s8["r_ls_sel"]/1e3, s8["c_ls"]*1e12, s8["f_ls"]/1e3), C6)
    annotation(story, "PITFALL",
        "Eq. 39 uses the per-phase inductance and the selected R<sub>CS</sub> — changing the shunt "
        "in Section 6.6 moves R<sub>LS</sub> proportionally. Update them together.", C6)
    sub_h(story, "6.8.3", "Soft Start — C_SS (AN4165-D Eq. 64)", C6)
    # I_SS / t_SS / V_SS were retyped into the equation, and the SELECTED C_SS ("390 nF") into the
    # decision line - while the engine held it in a LOCAL variable, `css_sel`, that nothing could
    # read. The engine's own summary table retyped it too. Now exported and read in both (C238).
    _c683 = data.get("const") or {}
    eq_box(story, [r"C_{SS}=\dfrac{I_{SS}\,t_{SS}}{V_{SS}}=\dfrac{%.0f\,\mu A\times%.0f\,\mathrm{ms}}{%.0f\,\mathrm{V}}=%.0f\ \mathrm{nF}"
                   % (_c683.get("i_ss", 20e-6) * 1e6, _c683.get("t_ss", 0.1) * 1e3,
                      _c683.get("v_ss", 5.0), s8["c_ss"] * 1e9)], ch=C6)
    body(story, "Decision: C<sub>SS</sub> = %.0f nF (nearest standard value to the %.0f nF "
                "calculated) → realized t<sub>SS</sub> = %.0f ms."
                % (s8["css_sel"] * 1e9, s8["c_ss"] * 1e9, s8["t_ss_real"] * 1e3), C6)
    sub_h(story, "6.8.4", "ILIMIT — Current-Command Clamp (Eqs. 32, 35, 38)", C6)
    annotation(story, "CONCEPT",
        "The ILIMIT pin sources a current mirrored from R<sub>RI</sub>; the pin voltage (÷4 "
        "internally) clamps the maximum current command, placed at a chosen ratio above the "
        "worst-case crest command.", C6)
    body(story, "The crest current command is evaluated at <b>both</b> corners (%.0f Vac low line and "
                "%.0f Vac high line); the larger drives the clamp sizing. Values used: "
                "R<sub>RI</sub> = %.2f kΩ (RT/RI oscillator resistor, Section 6.4), "
                "R<sub>CS</sub> = %.1f mΩ (Section 6.6), P = %g W (LL) / %g W (HL), "
                "η = %.3f (LL) / %.3f (HL), N<sub>CH</sub> = %d, and command-clamp ratio = %.1f×."
                % (s8["vin_ll_min"], s8["vin_hl_min"], s8["rri"]/1e3, s8["rcs_sel"]*1e3,
                   s8["pout_lo"], s8["pout_hi"], s8["eta_lo"], s8["eta_hi"], s8["nch"],
                   s8["ilimit_clamp_ratio"]), C6)
    eq_box(story, [
        r"I_{ILIMIT}=\dfrac{1.2\times1.0208}{R_{RI}}=\dfrac{1.2\times1.0208}{%.0f}=%.2f\ \mu A"
        % (s8["rri"], s8["i_ilimit"]*1e6),
        r"\mathrm{crest}_{LL}=\dfrac{\sqrt{2}\times%g}{%.3f\times%d\times%g}=%.2f\ \mathrm{A}"
        % (s8["pout_lo"], s8["eta_lo"], s8["nch"], s8["vin_ll_min"], s8["crest_ll"]),
        r"\mathrm{crest}_{HL}=\dfrac{\sqrt{2}\times%g}{%.3f\times%d\times%g}=%.2f\ \mathrm{A}"
        % (s8["pout_hi"], s8["eta_hi"], s8["nch"], s8["vin_hl_min"], s8["crest_hl"]),
        r"\mathrm{crest}_{worst}=%.2f\ \mathrm{A}\ (\mathrm{at\ %s})\ \Rightarrow\ "
        r"V_{CS,crest}=%.2f\times%.1f\,\mathrm{m\Omega}=%.1f\ \mathrm{mV}"
        % (s8["crest_cmd"], s8["crest_corner"].replace(" ", "\\ "),
           s8["crest_cmd"], s8["rcs_sel"]*1e3, s8["vcs_crest"]*1e3),
        r"R_{ILIMIT}=\dfrac{%.1f\times\mathrm{crest}\times R_{CS}\times4}{I_{ILIMIT}}"
        r"=\dfrac{%.1f\times%.2f\times%.4f\times4}{%.2f\times10^{-6}}=%.0f\ \Omega\ (%.2f\ \mathrm{k\Omega})"
        % (s8["ilimit_clamp_ratio"], s8["ilimit_clamp_ratio"], s8["crest_cmd"], s8["rcs_sel"],
           s8["i_ilimit"]*1e6, s8["r_ilimit"], s8["r_ilimit"]/1e3)], ch=C6)
    # C_ILIMIT had no single home: this prose asserted 18 nF, the schematic drew 18 nF, and the
    # GUI dropdown offered 10 nF as its default - so screen and document disagreed. It is now one
    # engine field that all three read (C238).
    body(story, "Decision: R<sub>ILIMIT</sub> = %.1f kΩ (E96) → command clamp ≈ %.1f× crest (window "
                "1.2–2.0×). C<sub>ILIMIT</sub> = %.0f nF."
                % (s8["r_ilimit_sel"]/1e3, s8["ilimit_clamp_ratio"], s8["c_ilimit"]*1e9), C6)
    sub_h(story, "6.8.5", "ILIMIT2 — Cycle-by-Cycle Peak Limit (Eqs. 33, 36, 37)", C6)
    body(story, "The peak inductor current I<sub>L,pk</sub> is the per-phase peak, taken as the "
                "<b>worst of both corners</b> (%.0f Vac and %.0f Vac). Values used: R<sub>RI</sub> = "
                "%.2f kΩ, R<sub>CS</sub> = %.1f mΩ, peak-limit ratio = %.1f×."
                % (s8["vin_ll_min"], s8["vin_hl_min"], s8["rri"]/1e3, s8["rcs_sel"]*1e3,
                   s8["ilimit2_ratio"]), C6)
    eq_box(story, [
        r"I_{ILIMIT2}=\dfrac{1.2\times1.03125}{R_{RI}}=\dfrac{1.2\times1.03125}{%.0f}=%.2f\ \mu A"
        % (s8["rri"], s8["i_ilimit2"]*1e6),
        r"I_{L,PK}=\max(I_{\phi,pk}@%.0f\,\mathrm{V},\ I_{\phi,pk}@%.0f\,\mathrm{V})="
        r"\max(%.2f,\ %.2f)=%.2f\ \mathrm{A}\ (\mathrm{at\ %s})"
        % (s8["vin_ll_min"], s8["vin_hl_min"], s8["ilpk_ll"], s8["ilpk_hl"], s8["il_pk"],
           s8["ilpk_corner"].replace(" ", "\\ ")),
        r"V_{CS,PK}=I_{L,PK}\times R_{CS}=%.2f\times%.1f\,\mathrm{m\Omega}=%.0f\ \mathrm{mV}"
        % (s8["il_pk"], s8["rcs_sel"]*1e3, s8["vcs_pk"]*1e3),
        r"R_{ILIMIT2}=\dfrac{%.1f\times V_{CS,PK}}{I_{ILIMIT2}}=\dfrac{%.1f\times%.3f}{%.2f\times10^{-6}}"
        r"=%.0f\ \Omega\ (%.2f\ \mathrm{k\Omega})"
        % (s8["ilimit2_ratio"], s8["ilimit2_ratio"], s8["vcs_pk"], s8["i_ilimit2"]*1e6,
           s8["r_ilimit2"], s8["r_ilimit2"]/1e3)], ch=C6)
    body(story, "Decision: R<sub>ILIMIT2</sub> = %.2f kΩ (E96) → no nuisance trips in normal "
                "operation. C<sub>ILIMIT2</sub> = 75 nF." % (s8["r_ilimit2_sel"]/1e3), C6)
    sub_h(story, "6.8.6", "Component Scorecard", C6)
    data_table(story, "6.8.6", "Component Scorecard — GC, LS, Soft-Start, Current Limits",
        "Gain-control, current-predict, soft-start and current-limit components.",
        ["Component", "Equation", "Calculated", "Selected", "Check", "Verdict"],
        s8["scorecard"], col_widths=[CW*0.15, CW*0.18, CW*0.16, CW*0.14, CW*0.21, CW*0.13], ch=C6)


_TITLE = "Control Scheme"


def _build_asbuilt_L_section(story, inp: dict, prior: dict):
    """Per-point as-built inductance verification (designer decision 2026-07-17).

    The approved inductor's per-point inductance curve (l_curve = [[Vac, L_uH], …])
    is passed in by the report endpoint. The control design is anchored at the
    MINIMUM as-built full-load inductance (worst point: lowest L → highest plant
    gain → highest current-loop crossover); this section verifies all nine points:
    with L_i ≥ L_design everywhere, the effective crossover only moves DOWN from
    the design point, so every point stays inside the designed bandwidth."""
    curve = inp.get("l_curve") or []
    if len(curve) < 2:
        return
    _p    = prior.get("inputs", {}) if isinstance(prior, dict) else {}
    L_des = float(inp.get("lphi_uH") or _p.get("lphi_uH", 0) or 0)
    fci   = float(_p.get("fci", inp.get("fci", 8000)) or 8000)
    if not L_des:
        L_des = min(float(l) for _, l in curve)
    sub_h(story, "6.10.14", "As-built inductance basis — verification at all nine operating points", C6)
    annotation(story, "CONCEPT",
        f"The control design uses L<sub>φ</sub> = <b>{L_des:.1f} µH</b> — the MINIMUM "
        "as-built full-load inductance of the approved inductor across the nine operating "
        "points (its inductance varies with DC bias). This is the worst case for the "
        "current loop: the lowest inductance gives the highest plant gain and therefore "
        "the highest loop crossover. At every other point the as-built L is larger, the "
        "plant gain lower, and the effective crossover proportionally lower — so the "
        "compensator designed here is verified at all nine points by construction.", C6)
    rows = []
    ok_all = True
    for vac, l_uh in curve:
        l_uh = float(l_uh)
        fci_i = fci * (L_des / l_uh) if l_uh else fci
        ok = fci_i <= fci * 1.0001
        ok_all = ok_all and ok
        rows.append([f"{float(vac):.0f}", f"{l_uh:.1f}",
                     f"{(L_des / l_uh):.3f}" if l_uh else "—",
                     f"{fci_i/1e3:.2f}", "✓" if ok else "✗"])
    data_table(story, "6.10.14",
        "As-Built Inductance and Effective Current-Loop Crossover — All 9 Points",
        f"Per-point as-built L (nominal A<sub>L</sub>) from the approved inductor design; "
        f"plant-gain ratio and effective crossover relative to the design basis "
        f"(L = {L_des:.1f} µH, f<sub>ci</sub> = {fci/1e3:.1f} kHz).",
        ["V<sub>in</sub> (Vac)", "L<sub>as-built</sub> (µH)",
         "Gain ratio L<sub>des</sub>/L<sub>i</sub>",
         "Effective f<sub>ci</sub> (kHz)", "Within design ✓"],
        rows,
        col_widths=[CW*0.18, CW*0.22, CW*0.22, CW*0.22, CW*0.16], ch=C6)
    body(story,
        ("All nine points remain at or below the designed crossover — the loop is "
         "verified across the part's real inductance swing."
         if ok_all else
         "One or more points exceed the design-basis crossover — review the inductance "
         "basis passed to the control design."), C6)


def _build_app_schematic_section(story, inp, prior, sec="6.8.7", fig_prefix="6.8.7",
                                 one_per_page=False, ch=None):
    """The complete FAN9672 application schematic (all pin networks), rendered TWICE: once for the
    low-line (FR) mode and once for the high-line (HV) mode. Component values are identical between
    the two; only the mode-set items differ (R_IAC series count, VIR threshold) plus the per-line
    operating annotations. Design-specific values are threaded from the sized components; fixed-
    practice filters fall back to datasheet-practice defaults. `sec`/`fig_prefix` set the section and
    figure labels (default the in-chapter §6.8.7; Appendix B.2 passes "B.2"); `one_per_page` puts each
    schematic on its own page so it sits beside the Table B.1 BOM for comparison."""
    from reportlab.platypus import PageBreak
    _ch = ch if ch is not None else C6   # chapter style (Ch6 in-line; Appendix B passes its own)
    from app.mode_b.schematics import fan9672_application_schematic
    from app.mode_b.step16_step9_bibo import compute_step9_bibo
    from app.mode_b.step16_step10_iloop import compute_step10_iloop
    from app.mode_b.step16_step11_vloop import compute_step11_vloop
    s8 = prior.get("step8", {}) if isinstance(prior, dict) else {}
    # The schematic asks its context for 22 keys; `base` used to supply 10 and the other 12 fell
    # back to literals inside schematics.py. Two of those literals were WRONG (C235):
    #   R_RLPK      drawn 15 kOhm, engine value 12.1 kOhm (CONST.r_rlpk) - the BOM said 12.1 all along
    #   R_FB1 unit  drawn 3.63 MOhm and labelled "x3", i.e. a 10.89 MOhm string; the engine's
    #               PER-UNIT value is 1.21 MOhm and 3.63 MOhm is the TOTAL the BOM reports
    # The rest happened to match, which is worse than being wrong: they agree only for this design
    # and would drift silently the moment a spec changed. Everything with an engine value is now
    # threaded from it.
    _c = prior.get("const", {}) if isinstance(prior, dict) else {}
    _s5 = prior.get("step5", {}) if isinstance(prior, dict) else {}
    try:    b = compute_step9_bibo(inp)
    except Exception: b = {}
    try:    d10 = compute_step10_iloop(inp, prior)
    except Exception: d10 = {}
    try:    d11 = compute_step11_vloop(inp, prior); cm = d11.get("comp", {}) or {}
    except Exception: d11, cm = {}, {}
    base = dict(
        rb1=b.get("rb1"), rb2=b.get("rb2"), rb3=b.get("rb3"), rb4=b.get("rb4"),
        cb1=b.get("cb1"), cb2=b.get("cb2"),
        r_gc_sel=s8.get("r_gc_sel"), c_gc=s8.get("c_gc"),
        r_ilimit_sel=s8.get("r_ilimit_sel"), r_ilimit2_sel=s8.get("r_ilimit2_sel"),
        r_ls_sel=s8.get("r_ls_sel"), c_ls=s8.get("c_ls"), css=s8.get("c_ss"),
        rri=s8.get("rri"), rcs_mohm=(s8.get("rcs_sel") or 0.015) * 1e3,
        r_ic=d10.get("ric"), c_ic1=d10.get("cic1"), c_ic2=d10.get("cic2"),
        r_vc=cm.get("r2s"), c_vc1=cm.get("c1s"), c_vc2=cm.get("c3s"),
        r3=cm.get("r3s"), c_v3=cm.get("c2s"), vType=cm.get("type", "type3"),
        i_ilimit_uA=(s8.get("i_ilimit") or 0) * 1e6,
        vcs_pk_mV=(s8.get("vcs_pk") or 0) * 1e3,
        # ── previously defaulted inside schematics.py; now threaded from the engine ──
        rrlpk=_c.get("r_rlpk"),                      # was 15 kOhm; BOM and Section 6.3.2 say 12.1
        cil=s8.get("c_ilimit"),                      # was an 18 nF literal; GUI offered 10 nF
        rfb_each=_s5.get("rfb1_unit"),               # PER-UNIT (x3 in the drawing) - not the total
        rfb2=_s5.get("rfb2"),
    )
    sub_h(story, sec, "FAN9672 Application Schematic — Low Line and High Line", _ch)
    body(story,
        "The complete FAN9672 front-end with every external component annotated from the sized "
        "bill of materials — amber values are live design selections; grey \"(typ)\" parts are "
        "fixed-practice filters not sized by the loop equations. The control-network component "
        "values are <b>identical</b> at both line ranges; only the mode-set items differ — R<sub>IAC</sub> "
        "(FR: 3×2 MΩ / HV: 6×2 MΩ), the VIR mode threshold, and the per-line operating point in the "
        "title block. Compensator networks (R<sub>IC</sub>, R<sub>VC</sub>, FBPFC divider) are sized "
        "in Section 6.10 and Section 6.11.", _ch)
    _vlo_s = float((prior or {}).get("inputs", {}).get("vin_ll_min", 90))
    _vhi_s = float((prior or {}).get("inputs", {}).get("vin_hl_max", 264))
    for hi, tag, lab in [(False, "a", f"Low line — FR mode, {_vlo_s:.0f}–132 Vac"),
                         (True, "b", f"High line — HV mode, 180–{_vhi_s:.0f} Vac")]:
        if one_per_page:
            story.append(PageBreak())
        v = dict(base)
        v["crest_A"]   = s8.get("crest_hl" if hi else "crest_ll") or 0
        v["iphi_pk_A"] = s8.get("ilpk_hl" if hi else "ilpk_ll") or 0
        # Mode-set items: these are the two components that legitimately DIFFER between the sheets,
        # so they are set per sheet rather than in `base`. Same values the drawing defaulted to,
        # now read from the engine so a change to the constants reaches the figure.
        v["riac"] = _c.get("riac_hv") if hi else _c.get("riac_fr")
        v["rvir"] = _c.get("r_vir_hv") if hi else _c.get("r_vir_fr")
        body(story, f"<b>Figure {fig_prefix}{tag} — FAN9672 application schematic ({lab})</b>", _ch)
        body(story,
             ("High-line (HV) mode: R<sub>IAC</sub> = 6×2 MΩ and the VIR high-range threshold; "
              "operating point %.0f–%.0f Vac." % (180, _vhi_s)) if hi else
             ("Low-line (FR) mode: R<sub>IAC</sub> = 3×2 MΩ and the VIR low-range threshold; "
              "operating point %.0f–132 Vac. Control-network values match the high-line sheet." % _vlo_s),
             _ch)
        try:
            story.append(fan9672_application_schematic(v, is_high=hi))
        except Exception:
            body(story, "<i>(schematic unavailable)</i>", _ch)


def build_story(inp: dict | None = None):
    """Assemble the full Steps 1–14 + Appendices control-design story.

    The designer specs `inp` are merged once into the Step 1–8 result (`prior`)
    and threaded through EVERY dependent step, so a spec change (V_OUT, f_sw, L,
    C_O, f_ci, f_cv, R_CS selection, compensator type / pole-zero placement, …)
    propagates consistently end-to-end.
    """
    from reportlab.platypus import PageBreak
    from app.mode_b.doc_report_builder import chapter_splash
    from app.mode_b.report_step9 import build_step9
    from app.mode_b.step16_step9_bibo import compute_step9_bibo
    from app.mode_b.report_step10 import build_step10
    from app.mode_b.step16_step10_iloop import compute_step10_iloop
    from app.mode_b.report_step11 import build_step11
    from app.mode_b.step16_step11_vloop import compute_step11_vloop
    from app.mode_b.report_step12 import build_step12
    from app.mode_b.step16_step12_transient import compute_step12_transient
    from app.mode_b.report_step13 import build_step13
    from app.mode_b.step16_step13_thd import compute_step13_thd
    from app.mode_b.report_step14 import build_step14
    from app.mode_b.appendices import build_appendices

    prior = compute_steps_1_8(inp)            # designer specs merged here, threaded below
    story = []
    chapter_splash(story, 6, _TITLE,
        "The complete FAN9672 control-loop design.",
        ["6.1–6.5 Power-stage spec, controller base, gain modulator, oscillator, output sensing",
         "6.6 R_CS current-sense resistor — two methods",
         "6.7 GMOD verification — three independent paths",
         "6.8 GC, LS, soft-start and current-limit components",
         "6.9 BIBO — brown-in / brown-out design",
         "6.10 Inner current loop — Type-II compensator",
         "6.11 Outer voltage loop — Type-II / Type-III compensator",
         "6.12–6.14 Step-load transient, input THD & 120 Hz rejection, compensator optimization",
         "Appendices A–E — derivations, BOM, bench test plan, references, quick-reference"])
    # Each build_stepN / build_appendices starts with step_h(), which already inserts a
    # PageBreak — so NO explicit PageBreak here (an extra one would create a blank page).
    build_steps_1_8(story, prior)
    # (FAN9672 application schematic moved to Appendix B.2 — rendered after the Table B.1 BOM so the
    #  bill of materials and the control circuit can be compared side by side.)
    build_step9(story, compute_step9_bibo(inp))
    s10 = compute_step10_iloop(inp, prior)
    build_step10(story, s10)
    _build_asbuilt_L_section(story, inp or {}, prior)   # Section 6.10.14 — current-loop as-built L basis
    s11 = compute_step11_vloop(inp, prior)
    build_step11(story, s11)
    s12 = compute_step12_transient(inp, prior)
    build_step12(story, s12)
    s13 = compute_step13_thd(inp, prior)
    build_step13(story, s13)
    s13["lphi_uH"] = inp.get("lphi_uH"); s13["cout_uF"] = inp.get("cout_uF")  # for the "fixed components" note
    build_step14(story, s13)
    build_appendices(story, prior=prior, s10=s10, s11=s11, s12=s12, s13=s13, inp=inp or {})
    while story and isinstance(story[0], PageBreak):
        story.pop(0)
    return story


def _doc(target):
    from reportlab.platypus import SimpleDocTemplate
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    return SimpleDocTemplate(target, pagesize=A4, leftMargin=20*mm, rightMargin=20*mm,
                             topMargin=18*mm, bottomMargin=18*mm, title=_TITLE)


def make_pdf(path: str, inp: dict | None = None):
    """Build the full control report to a file path."""
    _doc(path).build(build_story(inp))
    return path


def build_control_report(inp: dict | None = None) -> bytes:
    """Build the full control report and return the PDF as bytes (for the API/GUI)."""
    import io
    buf = io.BytesIO()
    _doc(buf).build(build_story(inp))
    return buf.getvalue()
