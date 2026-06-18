"""
app/mode_b/report_step9.py — full-detail Step 9 (BIBO) report block.

Reproduces the reference document's "Step 12 — BIBO Pin: Brown-In / Brown-Out
Design" word-for-word, line-for-line, table-for-table, step-for-step, renumbered
as our report's Step 9 (subsections 9.1–9.10). Only the font / text / alignment /
formatting follow our agreed report style. All numbers come from the
step16_step9_bibo calc agent (verified to match the document).
"""
from __future__ import annotations
from app.mode_b.doc_report_builder import (
    step_h, sub_h, body, eq_box, data_table, annotation, CW,
)
from app.mode_b.step16_step9_bibo import compute_step9_bibo

CH = 6   # control-design chapter


def _ws(story, label, eq, num=None):
    """One worked sub-step: bold label (HTML) then its equation."""
    body(story, "<b>" + label + "</b>", CH)
    eq_box(story, eq if isinstance(eq, list) else [eq], number=num, ch=CH)


def build_step9(story, data: dict):
    d = data

    step_h(story, "9", "BIBO Pin — Brown-In / Brown-Out Design", CH)
    annotation(story, "THEORY",
        "Brown-in/brown-out sets the line voltages at which the converter starts and stops, with "
        "hysteresis so it cannot chatter near the threshold. The BIBO divider must guarantee "
        "start-up above the lowest valid line and ride-through of standardised line dropouts "
        "(IEC 61000-4-11, SEMI F47) without nuisance shutdown.", CH)
    body(story,
        "The BIBO (Brown-In / Brown-Out) pin monitors the rectified average of the AC input voltage "
        "through an external resistive voltage divider and two-pole low-pass filter. The FAN9672 "
        "uses this signal to disable the PFC stage when the AC input is too low (brownout) and to "
        "re-enable it when the line recovers to a safe level (brown-in). This step sizes all "
        "components for the universal input 90–264 Vac design, sets the brown-in threshold to 87 Vac "
        "to provide a 3 Vac margin below the 90 Vac specification minimum, and verifies full "
        "compliance against the product test specification requirements of EN61000-4-11:2020 and "
        "SEMI F47.", CH)

    # ── 9.1 ───────────────────────────────────────────────────────────────────
    sub_h(story, "9.1", "How the BIBO Pin Works", CH)
    body(story,
        "The BIBO pin senses the average value of the full-wave rectified line voltage. The "
        "averaging filter removes the twice-line-frequency ripple so the FAN9672 comparator sees a "
        "stable DC level proportional to the RMS input voltage. The relationship between line "
        "voltage and V<sub>BIBO</sub> is:", CH)
    eq_box(story, [r"V_{BIBO}=V_{LINE,rms}\times\dfrac{2\sqrt{2}}{\pi}\times"
                   r"\dfrac{R_{B4}}{R_{B1}+R_{B2}+R_{B3}+R_{B4}}"],
           heading="BIBO sense relation", number="9.1", ch=CH)
    body(story,
        "The factor 2√2/π = 0.9003 is the ratio of average to RMS for a full-wave rectified sine. "
        "All thresholds are referred to V<sub>BIBO</sub>, not the AC line directly. The FAN9672-D "
        "internal thresholds are fixed and mode-dependent:", CH)
    data_table(story, "9.1", "FAN9672-D Internal BIBO Thresholds (fixed)",
        "Mode-dependent comparator thresholds — referred to V_BIBO.",
        ["Parameter", "Symbol", "FR Mode (V_VIR < 1.5 V)", "HV Mode (V_VIR > 3.5 V)", "Source"],
        [["Brownout — PFC stops", "V_BIBO,BO", "1.05 V", "1.05 V  (same)", "FAN9672-D elec. spec"],
         ["Brown-in — PFC restarts", "V_BIBO,BI", "1.90 V  (hys = 0.85 V)", "1.75 V  (hys = 0.70 V)", "FAN9672-D elec. spec"],
         ["SAG threshold", "V_SAG", "0.85 V", "0.85 V  (same)", "FAN9672-D elec. spec"],
         ["Brownout debounce time", "t_UVP", "450 ms", "450 ms  (same)", "FAN9672-D elec. spec"]],
        col_widths=[CW*0.24, CW*0.14, CW*0.24, CW*0.20, CW*0.18], ch=CH)
    annotation(story, "NOTE",
        "The brownout and SAG thresholds are identical in both modes. Only the brown-in hysteresis "
        "differs (0.85 V FR vs 0.70 V HV). The brownout AC voltage is therefore the same in both "
        "modes — only the brown-in recovery voltage differs. The internal hysteresis ratio "
        "BI/BO = 1.90/1.05 = 1.8095 in FR mode means that for any chosen brownout level the brown-in "
        "level is always 1.8095× higher. This ratio is fixed and cannot be adjusted externally.", CH)

    # ── 9.2 ───────────────────────────────────────────────────────────────────
    sub_h(story, "9.2", "Design Targets and Constraint Analysis", CH)
    body(story, "Three requirements must be satisfied simultaneously:", CH)
    data_table(story, "9.2", "BIBO Design Requirements",
        "The binding constraints that drive the divider design.",
        ["Requirement", "Target", "Drives Design?"],
        [["PFC starts at or before 87 Vac (3 V margin below 90 Vac spec minimum)",
          "Brown-in FR ≤ 87 Vac  →  Brownout ≤ 48.1 Vac", "YES — determines ratio"],
         ["EN61000-4-11 70V/500ms Criteria A: BO must not fire", "Brownout < 70 Vac",
          "YES — upper limit on BO"],
         ["EN61000-4-11 / SEMI F47 all other Criteria A tests", "See compliance table Section 9.7",
          "Automatically satisfied"]],
        col_widths=[CW*0.46, CW*0.32, CW*0.22], ch=CH)
    body(story,
        "The two binding requirements work in the same direction: the startup requirement forces "
        "brownout below 48.1 Vac, which also satisfies the 70 Vac test limit with 21.9 Vac to spare. "
        "Both can be met with a single resistor network.", CH)
    body(story,
        "The FAN9672-D brownout debounce (t<sub>UVP</sub> = 450 ms) automatically handles all test "
        "dips shorter than 450 ms — these cannot trigger brownout regardless of voltage level:", CH)
    data_table(story, "9.2b", "Standardised Dip Tests vs 450 ms Debounce",
        "Dips shorter than the 450 ms debounce cannot fire brownout at any level.",
        ["Standard", "Test Voltage", "Duration", "Criteria", "Mode", "BO Fires?", "Constraint"],
        [["EN61000-4-11  100V/60Hz", "40 V", "200 ms", "A derate 150W", "FR", "No — 200ms < 450ms", "None (debounce)"],
         ["EN61000-4-11  100V/60Hz", "70 V", "500 ms", "A derate 700W", "FR", "Yes — 500ms > 450ms", "BO must NOT fire at 70 V"],
         ["EN61000-4-11  100V/60Hz", "80 V", "5 s", "A derate 700W", "FR", "Yes — 5s >> 450ms", "BO must NOT fire at 80 V"],
         ["EN61000-4-11  100V/60Hz", "0 V", "5 s", "B", "FR", "Yes — fires", "Criteria B: restart OK"],
         ["EN61000-4-11  240V/50Hz", "96 V", "200 ms", "A derate 650W", "HV", "No — 200ms < 450ms", "None (debounce)"],
         ["EN61000-4-11  240V/50Hz", "168 V", "500 ms", "A derate 1010W", "HV", "Yes — 500ms > 450ms", "BO must NOT fire at 168 V"],
         ["EN61000-4-11  240V/50Hz", "192 V", "5 s", "A", "HV", "Yes — 5s >> 450ms", "BO must NOT fire at 192 V"],
         ["EN61000-4-11  240V/50Hz", "0 V", "5 s", "B", "HV", "Yes — fires", "Criteria B: restart OK"],
         ["SEMI F47  100V/50Hz", "45 V", "200 ms", "B", "FR", "No — 200ms < 450ms", "None (Criteria B anyway)"],
         ["SEMI F47  100V/50Hz", "67 V", "500 ms", "B", "FR", "Yes — fires", "Criteria B: restart OK"],
         ["SEMI F47  100V/50Hz", "78 V", "1 s", "B", "FR", "Yes — fires", "Criteria B: restart OK"],
         ["SEMI F47  200V/50Hz", "90 V", "200 ms", "B", "HV", "No — 200ms < 450ms", "None (Criteria B anyway)"],
         ["SEMI F47  200V/50Hz", "134 V", "500 ms", "B", "HV", "Yes — fires", "Criteria B: restart OK"],
         ["SEMI F47  200V/50Hz", "156 V", "1 s", "A", "HV", "Yes — 1s > 450ms", "BO must NOT fire at 156 V"]],
        col_widths=[CW*0.19, CW*0.10, CW*0.09, CW*0.13, CW*0.07, CW*0.16, CW*0.26], ch=CH)

    # ── 9.3 ───────────────────────────────────────────────────────────────────
    sub_h(story, "9.3", "Voltage Divider Ratio Calculation", CH)
    body(story,
        "The divider ratio is derived from the brown-in startup requirement: V<sub>BIBO</sub> must "
        "reach the internal threshold of 1.90 V when V<sub>LINE</sub> = 87 Vac.", CH)
    eq_box(story, [r"V_{BIBO,BI}=V_{LINE,BI}\times\dfrac{2\sqrt{2}}{\pi}\times"
                   r"\dfrac{R_{B4}}{R_{total}}=1.90\ \mathrm{V}"], number="9.2", ch=CH)
    body(story, "Rearranging for the divider ratio:", CH)
    eq_box(story, [r"\dfrac{R_{B4}}{R_{total}}=\dfrac{V_{BIBO,BI}}{V_{LINE,BI}\times(2\sqrt{2}/\pi)}"], ch=CH)
    _ws(story, "Step 1 — Substitute V<sub>BIBO,BI</sub> = 1.90 V (FR brown-in), "
        "V<sub>LINE,BI</sub> = 87 Vac:",
        r"\dfrac{1.90}{87\times0.9003}=\dfrac{1.90}{78.33}=0.024257")
    _ws(story, "Step 2 — Resulting brownout voltage:",
        r"\dfrac{1.05}{0.9003\times0.024257}=48.08\ \mathrm{Vac}")
    body(story, "&nbsp;&nbsp;&nbsp;&nbsp;48.08 Vac &lt; 70 Vac EN61000-4-11 limit ✓", CH)
    _ws(story, "Step 3 — Resulting HV mode brown-in:",
        r"\dfrac{1.75}{0.9003\times0.024257}=80.13\ \mathrm{Vac}")
    body(story, "&nbsp;&nbsp;&nbsp;&nbsp;80.13 Vac &lt; 180 Vac HV minimum ✓", CH)

    # ── 9.4 ───────────────────────────────────────────────────────────────────
    sub_h(story, "9.4", "Resistor Network Sizing", CH)
    body(story,
        "Four resistors form the divider following the AN4165-D reference circuit. R<sub>B3</sub> is "
        "set to approximately 10% of R<sub>B12</sub> (= R<sub>B1</sub> + R<sub>B2</sub>) to form a "
        "convenient filter tap. R<sub>B1</sub> and R<sub>B2</sub> are equal to share voltage stress. "
        "The exact calculation with R<sub>B4</sub> = 30 kΩ selected as the bottom resistor:", CH)
    eq_box(story, [r"\dfrac{R_{B4}}{R_{B1}+R_{B2}+R_{B3}+R_{B4}}=0.024257"], ch=CH)
    _ws(story, "Step 1 — Select R<sub>B4</sub> = 30 kΩ  (standard E24)", r"R_{B4}=30\ \mathrm{k\Omega}")
    _ws(story, "Step 2 — R<sub>total</sub> = R<sub>B4</sub> / ratio:",
        r"R_{total}=\dfrac{30\,000}{0.024257}=1236.75\ \mathrm{k\Omega}")
    _ws(story, "Step 3 — R<sub>B12</sub> = (R<sub>total</sub> − R<sub>B4</sub>) / 1.1   "
        "(R<sub>B3</sub> = 10% of R<sub>B12</sub>):",
        r"\dfrac{1236.75\mathrm{k}-30\mathrm{k}}{1.1}=1097.05\ \mathrm{k\Omega}")
    _ws(story, "Step 4 — R<sub>B1</sub> = R<sub>B2</sub> = R<sub>B12</sub> / 2:",
        r"\dfrac{1097.05\mathrm{k}}{2}=548.52\ \mathrm{k\Omega}\ \rightarrow\ 560\ \mathrm{k\Omega}\ (E24)")
    _ws(story, "Step 5 — R<sub>B3</sub> = R<sub>B12</sub> / 10:",
        r"\dfrac{1097.05\mathrm{k}}{10}=109.70\ \mathrm{k\Omega}\ \rightarrow\ 82\ \mathrm{k\Omega}\ (E24)")
    body(story, "<b>Standard values selected: R<sub>B1</sub> = R<sub>B2</sub> = 560 kΩ, "
        "R<sub>B3</sub> = 82 kΩ, R<sub>B4</sub> = 30 kΩ.</b>", CH)
    body(story, "<b>Verification with standard values:</b>", CH)
    _ws(story, "Step 6 — Actual ratio:",
        r"\dfrac{30\,000}{560\,000+560\,000+82\,000+30\,000}=\dfrac{30\,000}{1\,232\,000}=0.024351")
    _ws(story, "Step 7 — Brownout voltage:",
        r"\dfrac{1.05}{0.9003\times0.024351}=47.89\ \mathrm{Vac}\quad(<70\ \mathrm{Vac\ limit})")
    _ws(story, "Step 8 — Brown-in FR mode:",
        r"\dfrac{1.90}{0.9003\times0.024351}=86.67\ \mathrm{Vac}\quad(\leq87\ \mathrm{Vac\ target,\ margin}=+0.33\,\mathrm{V})")
    _ws(story, "Step 9 — Brown-in HV mode:",
        r"\dfrac{1.75}{0.9003\times0.024351}=79.82\ \mathrm{Vac}\quad(<180\ \mathrm{Vac\ HV\ minimum})")
    _ws(story, "Step 10 — SAG protection level:",
        r"\dfrac{0.85}{0.9003\times0.024351}=38.77\ \mathrm{Vac}\quad(\mathrm{below\ brownout})")
    body(story, "<b>1% resistor tolerance worst-case check (R<sub>B4</sub> 1% low, all others 1% "
        "high):</b>", CH)
    _ws(story, "Step 11 — Worst-case ratio:",
        r"\dfrac{30\mathrm{k}\times0.99}{560\mathrm{k}\times1.01+560\mathrm{k}\times1.01+82\mathrm{k}\times1.01+30\mathrm{k}\times0.99}=0.023880")
    _ws(story, "Step 12 — Worst-case brown-in FR:",
        r"\dfrac{1.90}{0.9003\times0.023880}=88.37\ \mathrm{Vac}\quad(\leq90\ \mathrm{Vac\ spec\ minimum})")
    eq_box(story, [r"R_{B1}=R_{B2}=560\ \mathrm{k\Omega}\qquad R_{B3}=82\ \mathrm{k\Omega}"
                   r"\qquad R_{B4}=30\ \mathrm{k\Omega}"], ch=CH)
    data_table(story, "9.4", "Threshold Summary — Standard Values",
        "Resulting AC thresholds with the selected E24 resistors.",
        ["Threshold", "V_BIBO", "Nominal AC Voltage", "1% Worst Case", "Requirement"],
        d["thresh_rows"], col_widths=[CW*0.34, CW*0.12, CW*0.20, CW*0.16, CW*0.18], ch=CH)
    annotation(story, "NOTE",
        "The FR brown-in at 86.67 Vac is 0.33 Vac below the 87 Vac design target, giving 3.33 Vac of "
        "margin below the 90 Vac specification minimum. With 1% resistor tolerance the worst-case "
        "brown-in is 88.37 Vac, still below the 90 Vac specification minimum. The HV brown-in at "
        "79.82 Vac is well below the 180 Vac minimum HV operating voltage, so normal power-on "
        "startup is unaffected on the high line.", CH)

    # ── 9.5 ───────────────────────────────────────────────────────────────────
    sub_h(story, "9.5", "Low-Pass Filter Capacitor Sizing", CH)
    body(story,
        "A two-pole RC low-pass filter attenuates the twice-line-frequency (100/120 Hz) ripple on "
        "the rectified AC average. Pole 1 is formed by C<sub>B1</sub> across R<sub>B3</sub>; Pole 2 "
        "is formed by C<sub>B2</sub> across R<sub>B4</sub>. AN4165-D recommends placing the poles "
        "between 10 Hz and 20 Hz.", CH)
    eq_box(story, [r"f_{P1}=\dfrac{1}{2\pi\,C_{B1}\,R_{B3}}",
                   r"f_{P2}=\dfrac{1}{2\pi\,C_{B2}\,R_{B4}}"], number="9.3", ch=CH)
    _ws(story, "Step 1 — C<sub>B1</sub> for f<sub>P1</sub> = 15 Hz (target):",
        r"\dfrac{1}{2\pi\times15\times82\,000}=129\ \mathrm{nF}\ \rightarrow\ \mathrm{select}\ 100\ \mathrm{nF}")
    _ws(story, "Step 2 — C<sub>B2</sub> for f<sub>P2</sub> = 10 Hz (target):",
        r"\dfrac{1}{2\pi\times10\times30\,000}=0.531\ \mathrm{\mu F}\ \rightarrow\ \mathrm{select}\ 560\ \mathrm{nF}")
    _ws(story, "Step 3 — Actual f<sub>P1</sub>  (C<sub>B1</sub>=100nF, R<sub>B3</sub>=82kΩ):",
        r"\dfrac{1}{2\pi\times100\mathrm{n}\times82\,000}=19.4\ \mathrm{Hz}")
    _ws(story, "Step 4 — Actual f<sub>P2</sub>  (C<sub>B2</sub>=560nF, R<sub>B4</sub>=30kΩ):",
        r"\dfrac{1}{2\pi\times560\mathrm{n}\times30\,000}=9.5\ \mathrm{Hz}")
    eq_box(story, [r"C_{B1}=100\ \mathrm{nF}\ (f_{P1}=19.4\ \mathrm{Hz})\qquad"
                   r"C_{B2}=560\ \mathrm{nF}\ (f_{P2}=9.5\ \mathrm{Hz})"], ch=CH)

    # ── interim component summary (doc: "Scorecard and Verdict") ──────────────
    body(story, "<b>Scorecard and Verdict</b>", CH)
    data_table(story, "9.5b", "BIBO Component Summary",
        "Selected divider and filter components.",
        ["Component", "Value", "Function"],
        [["RB1 / RB2", "560 kΩ / 560 kΩ", "HV-rated series sense"],
         ["RB3", "82 kΩ", "filter pole 1 with C_B1"],
         ["RB4", "30 kΩ", "bottom leg, sets ratio"],
         ["CB1 / CB2", "100 nF / 560 nF", "two-pole 120 Hz filter"]],
        col_widths=[CW*0.22, CW*0.30, CW*0.48], ch=CH)
    annotation(story, "DECISION",
        "Single network serves both ranges: brown-in 86.7 Vac (FR), brown-out 47.9 Vac — both inside "
        "their required windows.", CH)

    # ── 9.6 ───────────────────────────────────────────────────────────────────
    sub_h(story, "9.6", "FR Mode and HV Mode Interaction — Single Network Verification", CH)
    body(story,
        "The V<sub>VIR</sub> resistor switches between FR mode (10 kΩ, V<sub>VIR</sub> &lt; 1.5 V, "
        "active for low-line 90–264 Vac range) and HV mode (470 kΩ, V<sub>VIR</sub> &gt; 3.5 V, "
        "active for high-line 180–264 Vac range). This changes the FAN9672 internal comparison "
        "threshold but does NOT change the external divider. V<sub>BIBO</sub> scales identically in "
        "both modes.", CH)
    body(story, "The table below confirms V<sub>BIBO</sub> and PFC status across the full AC range in "
        "each mode:", CH)
    data_table(story, "9.6", "V_BIBO and PFC Status Across the AC Range",
        "Same external divider in both modes; only the brown-in threshold differs.",
        ["V_LINE (Vac)", "V_BIBO (V)", "FR Mode Status  (V_VIR < 1.5 V)", "HV Mode Status  (V_VIR > 3.5 V)"],
        d["vbibo_rows"], col_widths=[CW*0.16, CW*0.16, CW*0.34, CW*0.34], ch=CH)
    annotation(story, "NOTE",
        "The PFC is operating normally at 87 Vac (V<sub>BIBO</sub> = 1.9073 V &gt; 1.9 V brown-in) "
        "and all voltages above it in FR mode. The HV brown-in at 79.8 Vac is well below 180 Vac HV "
        "minimum, confirming normal startup on the high line. The only difference between modes is "
        "the brown-in level (86.7 Vac FR vs 79.8 Vac HV), both comfortably within their respective "
        "operating ranges.", CH)

    # ── 9.7 ───────────────────────────────────────────────────────────────────
    sub_h(story, "9.7", "Test Compliance Verification — EN61000-4-11:2020 and SEMI F47", CH)
    body(story,
        "Pass/fail logic: (1) duration &lt; 450 ms: brownout cannot fire — PASS regardless of "
        "voltage. (2) V<sub>BIBO</sub> &gt; 1.05 V throughout test: brownout does not fire — PASS "
        "for Criteria A. (3) V<sub>BIBO</sub> &lt; 1.05 V for &gt; 450 ms, Criteria B: brownout "
        "fires but restart allowed — PASS. (4) V<sub>BIBO</sub> &lt; 1.05 V for &gt; 450 ms, "
        "Criteria A: brownout fires — FAIL.", CH)
    _cw7 = [CW*0.09, CW*0.10, CW*0.13, CW*0.10, CW*0.11, CW*0.32, CW*0.15]
    _h7 = ["I/P Voltage", "Duration", "Criteria", "V_BIBO", "BO Fires?", "Reason", "Verdict"]

    body(story, "<b>EN61000-4-11:2020 — 100 Vac / 60 Hz  (FR Mode Active)</b>", CH)
    body(story, "FR brownout threshold = 47.89 Vac. V<sub>BIBO</sub> scaling = V<sub>LINE</sub> × "
        "0.021923 V/Vac.", CH)
    data_table(story, "9.7a", "EN61000-4-11 — 100 Vac / 60 Hz (FR)", "",
        _h7,
        [["40 V", "200 ms", "A derate 150W", "0.8769 V", "No  (debounce)", "Duration 200ms < 450ms debounce — BO cannot fire", "PASS ✓"],
         ["70 V", "500 ms", "A derate 700W", "1.5346 V", "In hyst", "V_BIBO=1.5346V in hysteresis zone — stays off if previously tripped", "PASS ✓"],
         ["80 V", "5000 ms", "A derate 700W", "1.7539 V", "In hyst", "V_BIBO=1.7539V in hysteresis zone — stays off if previously tripped", "PASS ✓"],
         ["0 V", "5000 ms", "B", "0.0000 V", "YES", "V_BIBO=0.0000V < 1.05V BO threshold — Criteria B restart OK", "PASS ✓"]],
        col_widths=_cw7, ch=CH)

    body(story, "<b>EN61000-4-11:2020 — 240 Vac / 50 Hz  (HV Mode Active)</b>", CH)
    body(story, "HV brownout = 47.89 Vac. HV brown-in = 79.82 Vac. Normal HV range 180–264 Vac is "
        "entirely above the brown-in threshold.", CH)
    data_table(story, "9.7b", "EN61000-4-11 — 240 Vac / 50 Hz (HV)", "",
        _h7,
        [["96 V", "200 ms", "A derate 650W", "2.1046 V", "No  (debounce)", "Duration 200ms < 450ms debounce — BO cannot fire", "PASS ✓"],
         ["168 V", "500 ms", "A derate 1010W", "3.6831 V", "No", "V_BIBO=3.6831V > BI threshold — PFC operating", "PASS ✓"],
         ["192 V", "5000 ms", "A", "4.2093 V", "No", "V_BIBO=4.2093V > BI threshold — PFC operating", "PASS ✓"],
         ["0 V", "5000 ms", "B", "0.0000 V", "YES", "V_BIBO=0.0000V < 1.05V BO threshold — Criteria B restart OK", "PASS ✓"]],
        col_widths=_cw7, ch=CH)

    body(story, "<b>SEMI F47 — 100 Vac / 50 Hz  (FR Mode Active)</b>", CH)
    data_table(story, "9.7c", "SEMI F47 — 100 Vac / 50 Hz (FR)", "",
        _h7,
        [["45 V", "200 ms", "B", "0.9865 V", "No  (debounce)", "Duration 200ms < 450ms debounce — BO cannot fire", "PASS ✓"],
         ["67 V", "500 ms", "B", "1.4689 V", "In hyst", "V_BIBO=1.4689V in hysteresis zone — stays off if previously tripped", "PASS ✓"],
         ["78 V", "1000 ms", "B", "1.7100 V", "In hyst", "V_BIBO=1.7100V in hysteresis zone — stays off if previously tripped", "PASS ✓"]],
        col_widths=_cw7, ch=CH)

    body(story, "<b>SEMI F47 — 200 Vac / 50 Hz  (HV Mode Active)</b>", CH)
    data_table(story, "9.7d", "SEMI F47 — 200 Vac / 50 Hz (HV)", "",
        _h7,
        [["90 V", "200 ms", "B", "1.9731 V", "No  (debounce)", "Duration 200ms < 450ms debounce — BO cannot fire", "PASS ✓"],
         ["134 V", "500 ms", "B", "2.9377 V", "No", "V_BIBO=2.9377V > BI threshold — PFC operating", "PASS ✓"],
         ["156 V", "1000 ms", "A", "3.4200 V", "No", "V_BIBO=3.4200V > BI threshold — PFC operating", "PASS ✓"]],
        col_widths=_cw7, ch=CH)

    # ── 9.8 ───────────────────────────────────────────────────────────────────
    sub_h(story, "9.8", "Startup Voltage Verification", CH)
    body(story,
        "The primary design requirement is that the PFC enables at or before 87 Vac during "
        "power-on. This is verified by confirming V<sub>BIBO</sub> ≥ 1.90 V (FR brown-in threshold) "
        "at 87 Vac:", CH)
    eq_box(story, [r"V_{BIBO}\ \mathrm{at\ 87\ Vac}=87\times0.9003\times0.024351=1.9073\ \mathrm{V}\quad>1.9\ \mathrm{V}",
                   r"V_{BIBO}\ \mathrm{at\ 90\ Vac}=90\times0.9003\times0.024351=1.9731\ \mathrm{V}\quad>1.9\ \mathrm{V}"], ch=CH)
    data_table(story, "9.8", "Startup Verification",
        "PFC enables at or before 87 Vac across nominal and 1% worst-case tolerance.",
        ["Startup Condition", "V_BIBO", "Threshold", "Margin", "Starts?"],
        d["startup_rows"], col_widths=[CW*0.40, CW*0.13, CW*0.13, CW*0.16, CW*0.18], ch=CH)

    # ── 9.9 ───────────────────────────────────────────────────────────────────
    sub_h(story, "9.9", "Final Scorecard — Component Summary", CH)
    data_table(story, "9.9", "BIBO Verification Scorecard",
        "Every brown-in/brown-out, startup, compliance and filter check.",
        ["Check", "Value / Result", "Criterion", "Verdict"],
        d["scorecard"], col_widths=[CW*0.36, CW*0.28, CW*0.20, CW*0.16], ch=CH)

    # ── 9.10 ──────────────────────────────────────────────────────────────────
    sub_h(story, "9.10", "Verdict", CH)
    annotation(story, "DECISION", "DESIGN PASS  —  ALL CHECKS CONFIRMED  ✓", CH)
    body(story,
        "The resistor network R<sub>B1</sub> = R<sub>B2</sub> = 560 kΩ, R<sub>B3</sub> = 82 kΩ, "
        "R<sub>B4</sub> = 30 kΩ with filter capacitors C<sub>B1</sub> = 100 nF, C<sub>B2</sub> = "
        "560 nF satisfies all three design requirements simultaneously: the PFC enables at 87 Vac "
        "(3 Vac margin below the 90 Vac specification minimum), all EN61000-4-11:2020 Criteria A "
        "test requirements pass for both low-line (FR mode) and high-line (HV mode) operation, and "
        "all SEMI F47 Criteria A tests pass.", CH)
    body(story,
        "The binding EN61000-4-11 constraint — 70 Vac for 500 ms, Criteria A — is met with the "
        "brownout at 47.9 Vac, giving 22.1 Vac margin below the test level. The 450 ms FAN9672 "
        "debounce handles all short-duration dip tests (40 V, 96 V, 45 V, 90 V) automatically "
        "without any contribution from the threshold setting. The 5-second Criteria B tests at 0 V "
        "allow restart, which is inherently satisfied.", CH)
    body(story,
        "With 1% resistor tolerance the worst-case brown-in FR is 88.37 Vac — still below the "
        "90 Vac specification minimum, confirming the design is robust across the full component "
        "tolerance range.", CH)
    annotation(story, "DECISION",
        "R<sub>B1</sub> = R<sub>B2</sub> = 560 kΩ   R<sub>B3</sub> = 82 kΩ   R<sub>B4</sub> = 30 kΩ "
        "  C<sub>B1</sub> = 100 nF   C<sub>B2</sub> = 560 nF.   Brownout = 47.9 Vac  |  Brown-in FR "
        "= 86.67 Vac  |  Brown-in HV = 79.82 Vac  |  PFC starts at 87 Vac.   EN61000-4-11:2020 + "
        "SEMI F47 all Criteria A: PASS.", CH)


def make_pdf(path: str, inp: dict | None = None):
    """Standalone Step 9 review PDF."""
    from reportlab.platypus import SimpleDocTemplate, PageBreak
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from app.mode_b.doc_report_builder import chapter_splash
    data = compute_step9_bibo(inp)
    story = []
    chapter_splash(story, 6, "Control Scheme — Step 9 (BIBO, full detail)",
        "Brown-in / brown-out design for universal 90–264 Vac input — divider, filter, and full "
        "EN61000-4-11:2020 / SEMI F47 compliance verification per FAN9672-D and AN4165-D.",
        ["9.1 pin operation  ·  9.2 requirements & debounce  ·  9.3 divider ratio  ·  9.4 resistor sizing",
         "9.5 filter caps  ·  9.6 FR/HV single-network  ·  9.7 EN61000-4-11 + SEMI F47 compliance",
         "9.8 startup  ·  9.9 scorecard  ·  9.10 verdict"])
    build_step9(story, data)
    while story and isinstance(story[0], PageBreak):
        story.pop(0)
    SimpleDocTemplate(path, pagesize=A4, leftMargin=20*mm, rightMargin=20*mm,
                      topMargin=18*mm, bottomMargin=18*mm,
                      title="Control Scheme — Step 9 (BIBO, full detail)").build(story)
    return path
