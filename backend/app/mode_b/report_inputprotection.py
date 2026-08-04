"""
Chapter 8 — Inrush Limiting (NTC + bypass relay)
Chapter 9 — Surge Protection & Compliance (MOV, IEC/EN 61000-4-5)
================================================================
Built from the SAME adapter the GUI uses (`inputprotection.adapter`), so the documented
numbers are identical to the selection page. Every carried-in quantity (V_ac range, worst-case
I_in,rms, C_out, bus/cap-V rating, device V_ds) is sourced from the upstream design — not
re-entered. MOV sizing is the compliance-certification record and is therefore documented as its
own chapter, separate from the NTC inrush chapter.

Each is a standalone document (like the Chapter-6 / Chapter-7 reports), merged after Chapter 7.
"""
from __future__ import annotations
import io

from app.mode_b.doc_report_builder import (
    chapter_splash, step_h, sub_h, body, eq_box, data_table, annotation, CW,
)
from app.mode_b.inputprotection.adapter import calculate_ntc, calculate_mov, calculate_gdt, calculate_fuse

_MU = "&#181;"; _DEG = "&#176;"; _OHM = "&#937;"


def _f(x, n=2):
    try:
        return f"{float(x):.{n}f}"
    except Exception:
        return "&#8212;"


def _inrush_schematic_flowable():
    """The NTC + relay-bypass schematic (designer's parametric SVG) as a ReportLab flowable,
    scaled to the page width. Returns None if svglib is unavailable so the chapter still builds."""
    try:
        from svglib.svglib import svg2rlg
        from app.mode_b.inputprotection.inrush_schematic import build_svg
        svg = build_svg(show_pin_numbers=True, show_notes=False, show_title_block=False,
                        show_header=True, show_legend=True)
        d = svg2rlg(io.StringIO(svg))
        if d is None or not d.width:
            return None
        sf = CW / d.width
        d.scale(sf, sf)
        d.width *= sf; d.height *= sf
        d.hAlign = "CENTER"
        return d
    except Exception:
        return None


# ══════════════════════════════════════════════════════════════════════════════
#  Chapter 8 — NTC inrush limiter + bypass relay
# ══════════════════════════════════════════════════════════════════════════════
def build_ntc_story(story, design, cap=None, opts=None):
    CH = 8
    opts = dict(opts or {})
    # Fuse selection first — its melting I²t AUTO-FEEDS the Section 8.6 coordination when the designer left the
    # fuse I²t blank (closes the review's OPEN item end-to-end).
    fuse = calculate_fuse(design, cap or {}, opts)
    if not opts.get("fuse_i2t_rating") and fuse.get("selected_i2t"):
        opts["fuse_i2t_rating"] = fuse["selected_i2t"]
    out = calculate_ntc(design, cap or {}, opts)
    s = out["spec"]; r = out["result"]; cat = out["catalog"]
    wc = out.get("worst_case") or {}          # review-upgrade worst-case / coordination proof

    chapter_splash(story, CH, "Inrush Limiting — NTC Thermistor + Bypass Relay",
        "What series element holds the cold-start inrush below target — across R25 tolerance and warm "
        "restart — while the whole startup-current path (NTC, bridge, fuse, relay, bulk cap) survives?",
        ["8.1 Design inputs, limits & selection gates — no part chosen yet",
         "8.2 Maximum allowed inrush target  ·  8.3 Required cold series resistance",
         "8.4 R25 tolerance → required nominal R25  ·  8.5 Pulse-energy requirement",
         "8.6 Candidate database screen  ·  8.7 Final NTC selection  ·  8.8 Selected-part recalculation",
         "8.9 Bypass relay timing & residual make  ·  8.10 Warm / hot restart policy",
         "8.11 Fuse selection & I²t coordination  ·  8.12 Startup-path stress",
         "8.13 AC phase-angle sweep  ·  8.14 Final margin summary & open items"])

    # ── 8.1 inputs, limits & selection gates ──
    # The selected NTC is NOT stated here — the chapter derives the REQUIREMENT first
    # (Section 8.2), then names the selected part and recalculates every figure around it
    # (Section 8.3). Everything that depends on the ACTUAL part — relay
    # timing (Section 8.4), restart policy (Section 8.5), fuse coordination (Section 8.6) — follows selection.
    # Section 8.1 carries only the fixed upstream inputs and the resulting selection gates.
    step_h(story, "8.1", "Design Inputs, Limits & Selection Gates", CH)
    annotation(story, "CONCEPT",
        "The inrush element is sized from values already fixed upstream: the high-line peak sets the "
        "worst-case stress, the approved bulk capacitance (Step 15) sets the charge energy, and the "
        "worst-case input RMS current (from the shared operating grid) sets the continuous self-heat "
        "that forces a bypass. This section states ONLY those inputs and the selection gates they imply — "
        "the NTC part itself is derived and named later (Sections 8.6–8.8), not pre-selected here.", CH)
    data_table(story, "8.1a", "Carried-in Operating Basis", "Each input with its source and status.",
        ["Quantity", "Symbol", "Value", "Source / status"],
        [["High-line RMS", "V<sub>ac,max</sub>", f"{_f(s['vac_max'],0)} V", "design grid"],
         ["High-line peak", "V<sub>in,pk</sub>", f"{_f(r['vin_pk_max'],1)} V", "computed = &#8730;2&#183;V<sub>ac,max</sub>"],
         ["Regulated bus", "V<sub>bus</sub>", f"{_f(s['vout_bus'],1)} V", "design"],
         ["Bulk capacitance", "C<sub>out</sub>", f"{_f(s['cout']*1e6,0)} {_MU}F", "Selected capacitor value"],
         ["Worst-case input RMS", "I<sub>in,rms</sub>", f"{_f(r['i_rms_worst'],2)} A", "operating grid"],
         ["Inrush current target", "I<sub>target</sub>", f"{_f(s['i_inrush_target'],0)} A", "design limit"],
         ["Known parasitic R", "R<sub>par</sub>", f"{_f(r['r_parasitic'],3)} {_OHM}", "line + EMI + ESR + bridge (0 = uncredited)"],
         ["R25 tolerance (screen)", "Tol<sub>R25</sub>", f"{_f((r.get('r25_tol_screen') if isinstance(r,dict) else s.get('r25_tol_default',0.2) or 0.2)*100,0)}%",
          "default — replaced by the selected part's datasheet tolerance"]],
        col_widths=[CW*0.30, CW*0.16, CW*0.24, CW*0.30], ch=CH)
    sub_h(story, "8.2", "Inrush Requirement — Target, Cold Resistance, Tolerance & Pulse Energy", CH)
    body(story,
        f"Every requirement in this chapter descends from ONE number: the maximum cold-start current the "
        f"input stage may draw. It is set by the weakest element in the startup path — bridge "
        f"I<sub>FSM</sub> (Chapter 7, Section 7.3.1), the line fuse, the bypass-relay contacts and the "
        f"bulk-capacitor ripple rating — and by any agency or site limit on turn-on current. For this "
        f"design <b>I<sub>target</sub> = {_f(s['i_inrush_target'],0)} A</b> at the "
        f"{_f(s['vac_max'],0)} Vac high-line corner, where V<sub>in,pk</sub> = "
        f"&#8730;2&#183;{_f(s['vac_max'],0)} = {_f(r['vin_pk_max'],1)} V is largest.", CH)
    body(story,
        "Cold, the whole line peak appears across the series resistance at switch-on, so the minimum total "
        "cold resistance is V<sub>in,pk</sub>/I<sub>target</sub>. Subtracting the loop parasitics leaves what "
        "the NTC alone must provide; the margin then covers the spread between a nominal part and its "
        "tolerance band, and the pulse-energy rating — not the steady current — is the governing "
        "datasheet filter.", CH)
    eq_box(story, [
        r"R_{total,cold}=\dfrac{V_{in,pk}}{I_{target}}\ ,\qquad "
        r"R_{25}=(R_{total,cold}-R_{parasitic})\times k_{margin}",
        r"R_{25,min}=R_{25,nom}\times(1-tol)\ \Rightarrow\ "
        r"R_{25,nom\,required}=\dfrac{R_{25}}{1-tol}",
        r"I_{inrush,max}=\dfrac{V_{in,pk}}{R_{25,min}+R_{parasitic}}",
        r"E_{cap}=\frac{1}{2}\,C_{out}\,V_{in,pk}^{2}\ ,\qquad "
        r"C_{max,equiv}=\dfrac{2E_{pulse}}{V_{ref}^{2}}",
    ], number="8.2", ch=CH)
    body(story,
        f"<b>Worked.</b> R<sub>total,cold</sub> = {_f(r['vin_pk_max'],1)} V / "
        f"{_f(s['i_inrush_target'],0)} A = {_f(r['r_total_min'],3)} {_OHM}. Subtracting the loop parasitic "
        f"({_f(r['r_parasitic'],3)} {_OHM}) leaves R<sub>25</sub> &#8805; {_f(r['r25_required'],3)} {_OHM}; "
        f"the &#215;{_f(s['r25_margin'],2)} margin gives the pick <b>R<sub>25</sub> = "
        f"{_f(r['r25_pick'],3)} {_OHM}</b>, and the tolerance-aware catalog floor is "
        f"<b>R<sub>25,nom</sub> &#8805; {_f(r['r25_nom_required'],2)} {_OHM}</b> so that a part landing on "
        f"the LOW edge of its band still holds the target. The bulk capacitor stores E<sub>cap</sub> = "
        f"&#189;&#183;{_f(s['cout']*1e6,0)} {_MU}F&#183;({_f(r['vin_pk_max'],1)} V)&#178; = "
        f"<b>{_f(r['e_cap'],1)} J</b>; with the &#215;{_f(s['energy_margin'],2)} survival margin the part "
        f"must be rated &#8805; {_f(r['e_pulse_required'],1)} J, equivalently a maximum switchable "
        f"capacitance &#8805; {_f(r['cmax_equiv_required']*1e6,0)} {_MU}F at the "
        f"{_f(s['vref_pulse'],0)} V vendor reference. Accept a part meeting <i>either</i> energy figure.", CH)
    annotation(story, "WHAT Rpar IS",
        "<b>R<sub>par</sub> is the TOTAL non-NTC resistance in the inrush loop</b> — mains and wiring "
        "+ EMI-filter series + bridge + bulk-capacitor ESR, added together and entered as ONE figure "
        "(GUI: <i>Loop R (total)</i>). It is credited against the requirement: the NTC only has to make up "
        "the difference between R<sub>total,cold</sub> and what the loop already provides, so a larger "
        "R<sub>par</sub> means a SMALLER required R<sub>25</sub>. Entering it as a single number is "
        "deliberate — the same resistance counted twice would understate the NTC requirement and can "
        "select an under-sized part. The same figure is credited in the relay make-current and "
        "bypassed-path checks later in this chapter. R<sub>par</sub> = 0 means nothing is credited and the "
        "NTC carries the whole limit, which is the conservative reading.", CH)
    _tol_sw = 0.20
    _sw_rows = []
    for _t, _rr in r["sweep"]:
        _net = max(_rr - r["r_parasitic"], 0.0)
        _sw_rows.append([f"{_f(_t,0)}", f"{_f(_rr,3)}", f"{_f(_net,3)}",
                         f"{_f(_net/(1.0-_tol_sw),3)}"])
    data_table(story, "8.2",
        "Inrush-Target Sweep — Required Resistance, Net of Parasitics, With Tolerance",
        f"How the resistance requirement moves if the inrush target is revised. "
        f"<b>R<sub>min,total</sub></b> = V<sub>in,pk</sub>/I. "
        f"<b>R<sub>min,total</sub> &#8722; R<sub>par</sub></b> credits the "
        f"{_f(r['r_parasitic'],3)} {_OHM} loop parasitic — what the NTC alone must provide. "
        f"<b>20% tolerance</b> is the NOMINAL catalog value needed so the LOW edge of the band still "
        f"holds the target. Design row = {_f(s['i_inrush_target'],0)} A.",
        ["Target I (A)", "R<sub>min,total</sub> (" + _OHM + ")",
         "R<sub>min,total</sub> &#8722; R<sub>par</sub> (" + _OHM + ")",
         "20% tolerance (" + _OHM + ")"],
        _sw_rows, col_widths=[CW*0.20, CW*0.26, CW*0.28, CW*0.26], ch=CH)

    # ── 8.3 selected part — every figure re-derived on the ACTUAL part ──
    # `sel` was previously bound in the old Section 8.7 (removed 2026-08-03 at the designer's
    # request); it is bound here now so this section still owns its own input.
    sel = out.get("selected")
    if sel:
        sub_h(story, "8.3", "Selected-Part Recalculation", CH)
        body(story,
            "All inrush and precharge figures below use the PART's real cold resistance rather than "
            "the generic pick, so the release numbers belong to the part that will be fitted.", CH)
        eq_box(story, [
            rf"I_{{inrush}} = \dfrac{{V_{{in,pk}}}}{{R_{{25}}+R_{{par}}}} = "
            rf"\dfrac{{{r['vin_pk_max']:.1f}}}{{{sel['r_total_cold_ohm']:.2f}}} = {sel['i_inrush_actual_A']:.1f}\ \mathrm{{A}}",
            rf"\tau = R_{{25}}\,C_{{out}} = {sel['tau_ms']:.1f}\ \mathrm{{ms}},\qquad "
            rf"t_{{bypass}} = {s['tau_multiple']:.0f}\,\tau = {sel['t_bypass_ms']:.0f}\ \mathrm{{ms}}",
        ], number="8.3", ch=CH)
        _chk = sel.get("checks") or {}
        data_table(story, "8.3", "Selected Part — Recalculated Design Values",
            "Actual-part figures vs the design targets. Verdict: "
            + ("MEETS the inrush target." if sel.get("meets_target") else "EXCEEDS the inrush target — pick a larger R25."),
            ["Quantity", "Value", "Check"],
            [["Part", f"{sel.get('mfr','')} {sel.get('part_number','')}", "designer-selected"],
             ["R<sub>25</sub>", f"{_f(sel['r25_ohm'],1)} {_OHM}",
              ("&#8805; required " + _f(r['r25_required'],2) + f" {_OHM} " + ("&#10003;" if _chk.get('r25_ok') else "&#10007;"))],
             ["Cold inrush peak (actual)", f"{_f(sel['i_inrush_actual_A'],1)} A",
              f"target &#8804; {_f(s['i_inrush_target'],0)} A " + ("&#10003;" if sel.get('meets_target') else "&#10007;")],
             ["Pulse energy (est. from &#216;)", f"~{_f(sel.get('energy_est_J'),0)} J",
              f"&#8805; {_f(r['e_pulse_required'],0)} J req "
              + ("&#10003;" if _chk.get('energy_ok') else ("&#10007;" if _chk.get('energy_ok') is False else "verify"))
              + f" (margin {_f(sel.get('energy_margin'),2)}&#215; E_cap)"],
             ["Precharge &#964; / bypass delay", f"{_f(sel['tau_ms'],1)} ms / {_f(sel['t_bypass_ms'],0)} ms",
              "close relay after settle"],
             ["Steady I<sub>max</sub>", f"{_f(sel.get('imax_A'),1)} A",
              ("below I<sub>rms</sub> — OK, bypassed after precharge" if _chk.get('imax_note') else "&#8212;")]],
            col_widths=[CW*0.34, CW*0.30, CW*0.36], ch=CH)
        annotation(story, "NOTE",
            "The pulse-energy figure is estimated from the disc diameter; confirm the Joule (or "
            "max-switchable-capacitance) rating and the R25 tolerance on the live datasheet before "
            "release.", CH)

    # ── 8.9 bypass relay timing & residual make — AFTER selection, on the actual part ──
    sub_h(story, "8.4", "Bypass Relay Timing & Residual Make Current", CH)
    body(story,
        "The bypass relay is sized and timed around the part chosen in Section 8.3, not the generic pick: "
        "Section 8.4.1 establishes WHY the NTC must be bypassed at all, Section 8.4.2 sets the precharge delay from the "
        "selected R<sub>25</sub>, and Section 8.4.3 checks what the contacts actually close into.", CH)

    # ── 8.9.1 continuous self-heat — the JUSTIFICATION for the bypass relay ──
    sub_h(story, "8.4.1", "Continuous Self-Heat → Why a Bypass Relay", CH)
    body(story,
        "Left in circuit, the warm NTC dissipates I<sub>in,rms</sub><sup>2</sup>&#183;R<sub>hot</sub> "
        "continuously — tens of watts at kW class, with body temperatures that can approach 250&#176;C. "
        "It is therefore bypassed by a relay after precharge, so it conducts only during the startup "
        "pulse. Consequently its steady-state contribution to the efficiency budget is &#8776; 0 W.", CH)
    data_table(story, "8.4.1", "Continuous Self-Heat if NOT Bypassed",
        f"At the worst-case input RMS current {_f(r['i_rms_worst'],2)} A.",
        ["R<sub>hot</sub> (" + _OHM + ")", "P<sub>loss</sub> = I<sup>2</sup>R (W)"],
        [[f"{_f(rh,2)}", f"{_f(pl,1)}"] for rh, pl in r["loss_rows"]],
        col_widths=[CW*0.5, CW*0.5], ch=CH)

    # ── 8.9.2 precharge timing — on the SELECTED part's R25 ──
    sub_h(story, "8.4.2", "Precharge Timing", CH)
    body(story,
        "<b>Model.</b> After the bulk capacitor has precharged through the NTC, a relay shorts the NTC out so "
        "it carries current only during the startup pulse. The bus settles with the RC time constant "
        "&#964; = R<sub>25</sub>&#183;C<sub>out</sub>; the bypass is closed after a few time constants.", CH)
    eq_box(story, [r"\tau=R_{25}\,C_{out},\qquad t_{bypass}=N_{\tau}\,\tau"], number="8.4.2", ch=CH)
    # Precharge timing must be quoted for the SELECTED part once one exists. Using the generic
    # r25_pick here made the report state an R25 the designer had not chosen (e.g. 5.08 ohm while a
    # 50 ohm NTC was selected), and it disagreed with the selected-part recalculation in Section 8.3.
    _sel_ntc = out.get("selected") or {}
    if _sel_ntc.get("r25_ohm"):
        _r25_t  = float(_sel_ntc["r25_ohm"])
        _tau_ms = float(_sel_ntc.get("tau_ms") or (r['tau'] * 1e3))
        _tb_ms  = float(_sel_ntc.get("t_bypass_ms") or (r['t_bypass'] * 1e3))
        _basis  = (f"the SELECTED NTC ({_sel_ntc.get('mfr','')} "
                   f"{_sel_ntc.get('part_number','')})").replace("  ", " ")
    else:
        _r25_t, _tau_ms, _tb_ms = float(r['r25_pick']), r['tau'] * 1e3, r['t_bypass'] * 1e3
        _basis = "the generic R<sub>25</sub> pick (no part selected yet)"
    body(story,
        f"<b>Worked — on {_basis}.</b> &#964; = R<sub>25</sub>&#183;C<sub>out</sub> = "
        f"{_f(_r25_t,2)} {_OHM} &#215; {_f(s['cout']*1e6,0)} {_MU}F = "
        f"{_f(_tau_ms,1)} ms, so closing the bypass after {_f(s['tau_multiple'],0)}&#183;&#964; = "
        f"<b>{_f(_tb_ms,0)} ms</b> lets the bus settle first. The relay contacts must be rated "
        f"&#8805; {_f(r['relay_contact_v'],0)} V (margin over the {_f(s['vout_bus'],1)} V bus) and carry the "
        f"continuous input current &#8805; {_f(r['relay_contact_a'],1)} A (add AC1/DC headroom).", CH)
    if _sel_ntc.get("r25_ohm") and abs(float(_sel_ntc["r25_ohm"]) - float(r['r25_pick'])) > 0.01:
        body(story,
            f"<i>The sizing calculation of Section 8.2 derived a required R<sub>25</sub> of "
            f"{_f(r['r25_pick'],2)} {_OHM}; the selected part is {_f(_r25_t,2)} {_OHM}. The timing above "
            f"uses the SELECTED value, which is what the built unit will do — the derived figure is the "
            f"minimum the part had to clear, not the value to design the relay delay around.</i>", CH)
    if wc:
        _rr = wc.get("r_required_ohm"); _op = wc.get("relay_operate_ms"); _tolm = wc.get("relay_delay_tol_ms")
        _sel_ms = (out.get("selected") or {}).get("t_bypass_ms")
        _min_ms = (_rr * s['cout'] * s['tau_multiple'] * 1e3) if _rr else None
        _final_ms = (_sel_ms or r['t_bypass'] * 1e3) + (_op or 0) + (_tolm or 0)
        body(story,
            "<b>Release timing (selected-part basis).</b> "
            + (f"Minimum design timing = {_f(_min_ms,0)} ms ({_f(s['tau_multiple'],0)}&#183;&#964; from the "
               f"required resistance {_f(_rr,2)} {_OHM}); " if _min_ms else "")
            + f"selected-part timing = {_f(_sel_ms or r['t_bypass']*1e3,0)} ms (from the actual R<sub>25</sub>). "
            f"The final relay-command delay must be &#8805; the selected-part value plus the relay operate-time "
            + (f"({_f(_op,0)} ms) " if _op else "(TBD) ")
            + "and control-timing tolerance"
            + (f" ({_f(_tolm,0)} ms)" if _tolm else " (TBD)")
            + f" &#8658; <b>&#8805; {_f(_final_ms,0)} ms</b>.", CH)
    annotation(story, "NOTE",
        "Hot-restart caution: a quick OFF/ON leaves the NTC warm (lower R) → higher inrush than the cold "
        "calculation. This is quantified in Section 8.5.", CH)

    # ── 8.9.3 precharge voltage + residual relay make — review points 3 & 4 ──
    if wc:
        sub_h(story, "8.4.3", "Precharge Voltage & Residual Relay-Make Current", CH)
        body(story,
            "The passive NTC path charges the bulk capacitor toward the <b>rectified line peak</b>, not the "
            "regulated PFC bus — the PFC boost stage lifts the bus to V<sub>bus</sub> only after startup. The "
            "capacitor voltage at the bypass instant, and the residual the relay closes into, are:", CH)
        eq_box(story, [r"V_{cap}(t)=V_{in,pk}\,(1-e^{-t/\tau}),\qquad V_{residual}=V_{in,pk}-V_{cap}(N_\tau\tau)",
                       r"I_{relay,make}=\dfrac{V_{residual}}{R_{relay\,path}}"], number="8.4.3", ch=CH)
        _imk = wc.get("i_relay_make_A")
        body(story,
            f"<b>Worked.</b> At {_f(s['tau_multiple'],0)}&#183;&#964; the capacitor reaches "
            f"{_f(wc['vcap_close_V'],1)} V &#8776; <b>{_f(wc['vcap_close_pct'],1)}%</b> of the "
            f"{_f(r['vin_pk_max'],1)} V rectified peak, leaving V<sub>residual</sub> = "
            f"<b>{_f(wc['v_residual_V'],1)} V</b>. The relay therefore makes into a small differential "
            + (f"; with a relay-path impedance of {_f(s['relay_path_ohm'],3)} {_OHM} the make current is "
               f"<b>{_f(_imk,2)} A</b>"
               if _imk is not None else
               ", but the make <i>current</i> = V<sub>residual</sub>/R<sub>path</sub> needs the relay-path "
               "impedance (contact + wiring + bridge + cap ESR + PCB) — an open item until layout is fixed")
            + ".", CH)
        _mk_rating = wc.get("relay_make_rating_A")
        data_table(story, "8.4.3", "Relay-Make Assessment",
            "Residual is computed; make current and rating close on the datasheet/layout.",
            ["Item", "Value / Action", "Status"],
            [["Residual voltage at bypass", f"{_f(wc['v_residual_V'],1)} V", "Calculated"],
             ["Relay-path impedance", (f"{_f(s['relay_path_ohm'],3)} {_OHM}" if s.get('relay_path_ohm') else "TBD (contact + wiring + bridge + ESR + PCB)"),
              "Input" if s.get('relay_path_ohm') else "Open"],
             ["Relay make current", (f"{_f(_imk,2)} A" if _imk is not None else "TBD = V_residual / R_path"),
              "Calculated" if _imk is not None else "Open"],
             ["Contact make rating", (f"{_f(_mk_rating,1)} A" if _mk_rating else "TBD from relay datasheet"),
              (("PASS" if (_imk is not None and _mk_rating and _imk <= _mk_rating) else "CHECK") if _mk_rating else "Required")]],
            col_widths=[CW*0.34, CW*0.42, CW*0.24], ch=CH)

    # ── 8.10 warm / hot restart — review point 5 ──
    if wc:
        sub_h(story, "8.5", "Warm / Hot Restart Policy", CH)
        body(story,
            "After operation the NTC is hot and its resistance is far below R25, so a short-off-time restart "
            "can draw <b>much higher</b> inrush than the cold case. Restart is therefore a REQUIRED design "
            "decision, not just a warning — it gates release, but it does not block NTC part selection.", CH)
        eq_box(story, [r"I_{restart}=\dfrac{V_{in,pk}}{R_{NTC,warm}+R_{source}},\qquad "
                       r"R_{required}=\dfrac{V_{in,pk}}{I_{target}}",
                       r"I_{bypass}=\dfrac{V_{in,pk}}{R_{src}+R_{bridge}+R_{ESR}+R_{wire}+R_{PCB}}"],
               number="8.5", ch=CH)
        _rows = wc.get("restart_rows") or []
        def _rrow(d):
            _tbd = ("TBD, limited by source/path impedance" if "Bypass" in d.get("case", "")
                    else "TBD (R(T) data)")
            return [d["case"], (_f(d["r_ohm"], 3) if d.get("r_ohm") is not None else _tbd),
                    (_f(d["i_A"], 1) if d.get("i_A") is not None else "OPEN"),
                    (_f(d["i_A_real"], 1) if d.get("i_A_real") is not None else "OPEN")]
        data_table(story, "8.5a", "Restart / Bypass Inrush vs Resistance State",
            "Cold, worst-case-tolerance, warm/hot and stuck-relay-bypass cases at the high-line peak. "
            "Conservative = NTC/path alone; realistic = crediting the known parasitic.",
            ["Case", "R (" + _OHM + ")", "Inrush cons. (A)", "Inrush real. (A)"],
            [_rrow(d) for d in _rows],
            col_widths=[CW*0.40, CW*0.22, CW*0.19, CW*0.19], ch=CH)
        body(story,
            f"<b>Restart-permission resistance.</b> Restart is only safe once the NTC has recovered above "
            f"R<sub>required</sub> = V<sub>in,pk</sub>/I<sub>target</sub> = {_f(wc['r_required_ohm'],2)} {_OHM} "
            "(or another active current-limit is enabled). The stuck-relay / NTC-bypassed case is limited only "
            "by the summed startup-path impedance"
            + (f" ({_f(wc['r_path_total_ohm'],3)} {_OHM} &#8658; {_f(wc['i_bypassed_A'],0)} A)"
               if wc.get("r_path_total_ohm") else " — OPEN until R_source/R_bridge/R_ESR/R_wiring/R_PCB are entered")
            + ".", CH)
        if wc.get("i_warm_A"):
            annotation(story, "PITFALL",
                f"Hot restart draws ~{_f(wc['i_warm_A'],0)} A at R<sub>hot</sub> = {_f(wc['r_hot_ohm'],2)} "
                f"{_OHM} — far above the {_f(wc['inrush_target_A'],0)} A target. Enforce a minimum off-time so "
                "the NTC cools, or add active precharge / relay sequencing / a restart interlock.", CH)
        _hrd = wc.get("hot_restart_decision") or {}
        _defined = _hrd.get("defined")
        _ot = _hrd.get("off_time_min_ms"); _rp = _hrd.get("restart_protection")
        data_table(story, "8.5b", "Hot-Restart Decision (required for release)",
            "Status: " + ("<b>DEFINED</b> — a restart policy is stated." if _defined
                          else "<b>DECISION REQUIRED</b> — no restart policy defined yet (release-gating, not selection-gating)."),
            ["Item", "Value / choice"],
            [["Restart status", "PASS — policy defined" if _defined else "CHECK — decision required"],
             ["Minimum off-time", (f"{_f(_ot,0)} ms" if _ot else "not defined")],
             ["Protection method", (f"{_rp}" if _rp else "not declared (hardware / firmware / procedure)")],
             ["Restart-permission R", f"NTC must recover &#8805; {_f(_hrd.get('r_required_ohm'),2)} {_OHM}"],
             ["Acceptable options", "; ".join(_hrd.get("options") or [])[:180]]],
            col_widths=[CW*0.30, CW*0.70], ch=CH)
        body(story,
            "<b>Resolve one</b> of: enforce a minimum off-time so the NTC re-cools above R<sub>required</sub>; "
            "gate restart on a measured R(T)/bus-voltage threshold; use active precharge instead of the NTC on "
            "hot restart; or a firmware lockout with measured proof of recovery. Until one is chosen the NTC "
            "design stays CONDITIONAL for release — but the part selection above is unaffected.", CH)

    # ── 8.11 fuse selection + I²t startup coordination — review point 7 + fuse DB ──
    if wc:
        sub_h(story, "8.6", "Fuse Selection & I²t Startup Coordination", CH)
        # ---- 8.9.0 fuse selection from the vendor DB ----
        _freq = fuse.get("requirements") or {}
        _fsel = fuse.get("selected")
        _fspec = fuse.get("spec") or {}
        _lf = float(_freq.get("load_factor") or 0.75) * 100.0
        # Designer review p212: the six gates were one dense paragraph. One gate per line —
        # this is a checklist the reader ticks off against Table 8.6a, not narrative prose.
        body(story,
            "The line fuse is the upstream protective element for the whole input stage. It is selected from "
            "the vendor database against <b>six gates</b>:", CH)
        for _g in [
            "<b>Gate 1 — AC voltage rating.</b> Rating &#8805; the high line.",
            (f"<b>Gate 2 — continuous RMS current.</b> Rating &#8805; "
             f"{_f(_fspec.get('current_margin',1.5),2)}&#215; the worst-case input RMS "
             f"({_f(fuse.get('i_rms'),1)} A), and the load within {_lf:.0f}% of the rating after "
             f"temperature de-rating (&#8658; &#8805; {_f(_freq.get('i_rated_min'),1)} A)."),
            "<b>Gate 3 — melting I&#178;t.</b> Must EXCEED the NTC-limited startup I&#178;t with "
            "margin, so the fuse does not nuisance-blow at every cold start.",
            "<b>Gate 4 — breaking capacity.</b> &#8805; the available fault current.",
            "<b>Gate 5 — fault coordination.</b> The fuse must safely interrupt a MOV/GDT "
            "fail-short or a stuck bypass relay.",
            "<b>Gate 6 — thermal implementation.</b> The re-rated current at the real maximum "
            "ambient, plus fuseholder / PCB rise, must still carry the load, with the fuse body "
            "inside its temperature limit.",
        ]:
            body(story, "&#8226;&nbsp;&nbsp;" + _g, CH)
        annotation(story, "Why the inrush PEAK does not set the current rating",
            f"The NTC-limited cold-start peak is {_f(fuse.get('inrush_peak_A'),1)} A, well above any sensible "
            "continuous rating. A fuse survives a high peak when the pulse is SHORT and the melting-I&#178;t "
            "margin holds — that is gate 3. Sizing the continuous rating to the inrush peak would force a "
            "grossly oversized fuse that no longer clears a small overload, so the peak is reported for "
            "context and the startup pulse is proven by I&#178;t.", CH)
        if _fsel:
            body(story,
                f"<b>Selected fuse:</b> {_fsel.get('mfr','')} {_fsel.get('part_number','')} — "
                f"{_f(_fsel.get('i_rated_A'),0)} A / {_f(_fsel.get('v_ac_V'),0)} Vac, breaking "
                f"{_f(_fsel.get('breaking_ac_A'),0)} A, melting I&#178;t <b>{_f(_fsel.get('melting_i2t'),0)} "
                f"A&#178;s</b>, {_fsel.get('response_time','')}. Its melting I&#178;t feeds the coordination "
                "check below (and the MOV/GDT fail-short check in Chapter 9).", CH)
        else:
            annotation(story, "OPEN — no catalog fuse fits",
                f"No database fuse meets the requirement (need I<sub>rated</sub> &#8805; "
                f"{_f(_freq.get('i_rated_min'),1)} A at &#8805; {_f(_freq.get('v_min'),0)} Vac with melting "
                "I&#178;t above the startup pulse). The vendor DB tops out at 50 A — use a higher-rated fuse, "
                "relax the current margin, or confirm the site fault current.", CH)
        _fc = fuse.get("candidates") or []
        if _fc:
            def _mk(v):
                return "&#10003;" if v else ("&#8212;" if v is None else "&#10007;")
            data_table(story, "8.6a", "Line-Fuse Candidate Screen (Six Gates)",
                "Vendor fuse database screened against all six gates (columns 1&#8211;6 above). A dash means "
                "the gate is OPEN — a datasheet field (melting I&#178;t, breaking capacity, temperature limit) "
                "or a site input (fault current, ambient) is absent, so the part stays CONDITIONAL and "
                "selectable rather than being silently passed or hidden.",
                ["Part", "I<sub>rated</sub>", "V<sub>ac</sub>", "Breaking", "Melt I²t", "1", "2", "3", "4", "5", "6", "Verdict"],
                [[str(c.get("part_number") or c["label"])[:16], f"{_f(c.get('i_rated_A'),0)}A",
                  f"{_f(c.get('v_ac_V'),0)}", (f"{_f(c.get('breaking_ac_A'),0)}A" if c.get("breaking_ac_A") else "&#8212;"),
                  (f"{_f(c.get('melting_i2t'),0)}" if c.get("melting_i2t") is not None else "MISSING"),
                  _mk(c.get("v_ok")), _mk(c.get("i_ok")), _mk(c.get("i2t_ok")), _mk(c.get("bc_ok")),
                  _mk(c.get("coord_ok")), _mk(c.get("thermal_ok")),
                  c.get("verdict", "PASS" if c["ok"] else "FAIL")] for c in _fc[:8]],
                col_widths=[CW*0.16, CW*0.08, CW*0.07, CW*0.10, CW*0.09, CW*0.045, CW*0.045, CW*0.045,
                            CW*0.045, CW*0.045, CW*0.045, CW*0.155], ch=CH)
        # ---- 8.9b six-gate release table for the SELECTED fuse ----
        _fg = fuse.get("gates") or []
        if _fg:
            _deg = lambda s: str(s or "").replace("degC", "&#176;C").replace(">=", "&#8805;").replace("<=", "&#8804;")
            data_table(story, "8.6b", "Selected Fuse — Six-Gate Release Check",
                "Requirement, measured/datasheet result and status for each gate. OPEN = the input or "
                "datasheet field needed to close the gate is not yet available; CONDITIONAL = the gate passes "
                "on an ESTIMATED value (e.g. a typical re-rating slope) and must be confirmed before release.",
                ["#", "Gate", "Requirement", "Result", "Status"],
                [[str(g["n"]), g["name"], _deg(g["requirement"]), _deg(g["result"]), g["status"]] for g in _fg],
                col_widths=[CW*0.05, CW*0.20, CW*0.33, CW*0.28, CW*0.14], ch=CH)
            _gopen = fuse.get("gates_open") or []
            _gcond = fuse.get("gates_conditional") or []
            if _gopen or _gcond:
                _bits = []
                if _gopen:
                    _bits.append("gate" + ("s " if len(_gopen) > 1 else " ") +
                                 ", ".join(str(n) for n in _gopen) + " OPEN")
                if _gcond:
                    _bits.append("gate" + ("s " if len(_gcond) > 1 else " ") +
                                 ", ".join(str(n) for n in _gcond) + " CONDITIONAL")
                annotation(story, f"Fuse release status: {fuse.get('gate_status','OPEN')}",
                    "The electrical gates are closed by calculation, but " + " and ".join(_bits) + ". "
                    "Supply the available fault current, the MOV/GDT fail-short and stuck-relay fault paths, "
                    "the maximum ambient at the fuse, the datasheet re-rating slope and the measured "
                    "fuseholder / PCB temperature rise to convert these to a computed PASS. Until then the "
                    "fuse is CONDITIONALLY acceptable and must not be signed off for release.", CH)
            else:
                annotation(story, "Fuse release status: PASS",
                    "All six gates close by calculation against datasheet and site data. Confirm on the bench "
                    "with a time-current curve overlay of the cold-start, warm-restart and fault cases.", CH)
        if fuse.get("fast_blow_only"):
            body(story, "<i>Note: the current database contains only fast-blow cartridge fuses; because the "
                 "NTC limits the inrush, a fast-blow fuse whose melting I&#178;t clears the startup pulse is "
                 "acceptable. A time-delay (T) fuse would add margin if available.</i>", CH)
        # ---- 8.11.1 I²t coordination — FOUR DISTINCT CASES, each with its own verdict ----
        # A single "worst case" row hides that the four events have different acceptance criteria: a
        # normal start must NOT blow the fuse (nuisance), whereas a stuck-relay fault SHOULD blow it.
        sub_h(story, "8.6.1", "I²t Coordination — Startup, Restart and Fault Cases", CH)
        body(story,
            "The fuse must survive the startup pulse. For a first-order exponential charge current, the "
            "startup I&#178;t is:", CH)
        eq_box(story, [r"i(t)=\dfrac{V_{in,pk}}{R_{total}}\,e^{-t/\tau},\qquad "
                       r"I^2t_{start}=\dfrac{V_{in,pk}^2\,\tau}{2\,R_{total}^2}"], number="8.6", ch=CH)
        _fr = wc.get("fuse_i2t_rating")
        body(story,
            "These are <b>four different events with four different acceptance criteria</b>, so they are "
            "judged separately rather than collapsed into one worst case. A normal cold start must NOT open "
            "the fuse (that would be a nuisance blow); an abnormal hot restart must still not open it if hot "
            "restart is permitted; and a stuck-relay or MOV/GDT fail-short fault is the case the fuse "
            "<i>is there to clear</i> — there the requirement is the opposite.", CH)

        def _vs(val, *, must_ride):
            """Verdict for one case. must_ride=True → the fuse must NOT open (I2t below pre-arcing).
            must_ride=False → this is a fault the fuse is expected to clear."""
            if val is None:
                return "OPEN — case not quantified"
            if not _fr:
                return "fuse I²t TBD"
            _r = val / _fr
            _pct = "&lt;1%" if _r < 0.01 else f"{_r*100:.0f}%"   # 0.4% must not print as "0%"
            if must_ride:
                return (f"PASS — rides ({_pct} of rating)" if val < _fr
                        else f"NUISANCE BLOW ({_pct} of rating)")
            return (f"clears the fuse ({_pct} of rating)" if val >= _fr
                    else f"below pre-arcing ({_pct}) — fuse will NOT open")

        _i2t_bp = wc.get("i2t_bypass")
        _g5 = next((g for g in (fuse.get("gates") or []) if g.get("n") == 5), None)
        data_table(story, "8.6c", "I²t Coordination by Case",
            f"Each startup / fault case against the selected fuse's pre-arcing I&#178;t"
            + (f" ({_f(_fr,0)} A&#178;s)." if _fr else " (not yet entered)."),
            ["#", "Case", "Requirement", "I²t (A²s)", "Verdict"],
            [["1", "Normal startup — cold nominal", "must NOT open the fuse", _f(wc['i2t_cold'],1),
              _vs(wc.get('i2t_cold'), must_ride=True)],
             ["1b", "Normal startup — minimum R25", "must NOT open the fuse", _f(wc['i2t_min_r25'],1),
              _vs(wc.get('i2t_min_r25'), must_ride=True)],
             ["2", "Abnormal — warm / hot restart", "must NOT open the fuse IF restart is permitted (Section 8.5)",
              (_f(wc['i2t_warm'],1) if wc.get('i2t_warm') else "OPEN"),
              _vs(wc.get('i2t_warm'), must_ride=True)],
             ["3", "Fault — stuck / bypassed relay", "fuse SHOULD clear this fault",
              (_f(_i2t_bp,1) if _i2t_bp else "DATA MISSING (startup-path R)"),
              _vs(_i2t_bp, must_ride=False)],
             ["4", "Fault — MOV/GDT fail-short", "fuse must interrupt safely (Ch 9, gate 5 of Section 8.6)",
              "see breaking capacity",
              (_g5.get("status") if _g5 else "OPEN")]],
            col_widths=[CW*0.05, CW*0.27, CW*0.28, CW*0.14, CW*0.26], ch=CH)
        if wc.get('i2t_warm') and _fr and wc['i2t_warm'] < _fr:
            annotation(story, "READ THIS THE RIGHT WAY",
                f"Case 2 passing means the fuse does NOT protect against a hot restart — the "
                f"{_f(wc['i2t_warm'],0)} A&#178;s restart pulse stays below the {_f(_fr,0)} A&#178;s "
                "pre-arcing I&#178;t, so the fuse will sit there while the bridge, relay and bulk capacitor "
                "take the surge. Hot restart must therefore be handled by the restart policy of Section 8.5, not "
                "by the fuse.", CH)
        if not _fr:
            annotation(story, "NOTE",
                "Enter the selected fuse's pre-arcing I&#178;t (datasheet) to close these checks; the worst "
                "startup case is the warm-restart pulse, not the cold start.", CH)
        if _i2t_bp is None:
            annotation(story, "OPEN — case 3 not quantified",
                "The stuck-relay / NTC-bypassed fault I&#178;t needs the summed startup-path resistance "
                "(source + bridge + cap ESR + wiring + PCB). Until it is entered, whether the fuse clears "
                "a welded-relay fault is unproven.", CH)

    # ── 8.12 startup-path component stress (references Ch7 bridge surge) — review point 8 ──
    if wc:
        sub_h(story, "8.7", "Startup-Path Component Stress", CH)
        body(story,
            "The NTC limits the current, but the whole startup path carries it. This table closes the loop; "
            "the bridge/diode surge is proven against I<sub>FSM</sub> in <b>Chapter 7 (Section 7.3.1)</b> and "
            "is referenced here.", CH)
        body(story,
            "The startup-path stress must be separated into three distinct electrical cases — a normal cold "
            "start, a hot restart (only if allowed), and a stuck/bypassed relay fault — because their currents "
            "differ by orders of magnitude. The bridge/diode surge is proven against I<sub>FSM</sub> in "
            "<b>Chapter 7 (Section 7.3.1)</b>.", CH)
        _sc = wc.get("stress_cases") or []
        def _ifsm_cell(c):
            v = c.get("ifsm_ok")
            return ("&#10003;" if v else ("&#10007;" if v is False else "IFSM TBD"))
        data_table(story, "8.7", "Startup-Path Stress — Cold / Hot-Restart / Bypass",
            f"Peak current and I²t per case; bridge IFSM = "
            + (f"{_f(wc['bridge_ifsm_a'],0)} A" if wc.get("bridge_ifsm_a") else "DATA MISSING (bridge datasheet I<sub>FSM</sub>)") + ".",
            ["Case", "Inrush (A)", "I²t (A²s)", "vs bridge I<sub>FSM</sub>"],
            [[c["case"], (_f(c["i_A"],0) if c.get("i_A") is not None else "OPEN"),
              (_f(c["i2t"],1) if c.get("i2t") is not None else "OPEN"), _ifsm_cell(c)] for c in _sc]
              or [["&#8212;", "", "", ""]],
            col_widths=[CW*0.34, CW*0.22, CW*0.22, CW*0.22], ch=CH)
        annotation(story, "NOTE",
            "Hot restart must be prevented (see the restart policy in Section 8.5) or every path component must "
            "be rated for the hot-restart current. The stuck-relay bypass is a fault case cleared by the "
            "upstream fuse — it is not a ride-through condition.", CH)

    # ── 8.13 AC phase-angle startup sweep — review point 10 (light) ──
    if wc and wc.get("phase_sweep"):
        sub_h(story, "8.8", "AC Phase-Angle Startup Sweep", CH)
        body(story,
            "Turn-on can occur at any line phase; the inrush scales with the instantaneous voltage, worst at "
            "the 90&#176; peak (the case sized above). The sweep gives the expected validation waveform:", CH)
        eq_box(story, [r"V_{in}(\theta)=V_{in,pk}\sin\theta,\qquad "
                       r"I_{inrush}(\theta)=\dfrac{V_{in}(\theta)}{R_{25}+R_{source}}"], number="8.8", ch=CH)
        data_table(story, "8.8", "Inrush vs Turn-On Angle",
            "Nominal R25 and worst-case minimum R25.",
            ["Turn-on angle", "V<sub>in</sub>(&#952;) (V)", "Inrush nominal (A)", "Inrush min-R25 (A)"],
            [[f"{d['deg']}&#176;", _f(d['vin_V'],0), _f(d['i_nom_A'],1), _f(d['i_min_A'],1)]
             for d in wc["phase_sweep"]],
            col_widths=[CW*0.22, CW*0.24, CW*0.27, CW*0.27], ch=CH)

    # ── 8.14 final margin summary + open items — Tables A & B + release taxonomy ──
    if wc:
        sub_h(story, "8.9", "Final NTC Design Margin Summary & Open Items", CH)
        _tgt = wc['inrush_target_A']
        _stat = wc.get("status") or {}
        _overall = wc.get("overall_status", "CONDITIONAL")
        def _mrg(val):
            return f"{100.0*(_tgt-val)/_tgt:+.1f}%" if val else "&#8212;"
        annotation(story, "STATUS LEGEND",
            "One vocabulary is used across Chapters 7&#8211;10. <b>PASS</b> — closed calculation against a "
            "confirmed limit. <b>FAIL</b> — the limit is exceeded. <b>CONDITIONAL</b> — a known risk needing "
            "design judgement, or a value that is estimated rather than datasheet-backed; it gates release "
            "sign-off but never blocks part selection. <b>DATA MISSING</b> — a datasheet, layout or site "
            "value that has not been supplied. <b>OPTIONAL</b> — not required for this design. "
            "<b>BLOCKED</b> — prevents release. "
            f"Overall NTC status: <b>{_overall}</b>.", CH)
        data_table(story, "8.9a", "Table A — Final NTC Design Margin Summary",
            "Each check with its release status (PASS / CHECK / OPEN / BLOCKED).",
            ["Check", "Requirement", "Value", "Status"],
            [["Nominal cold inrush", f"&#8804; {_f(_tgt,0)} A", f"{_f(wc['i_inrush_nom_A'],1)} A ({_mrg(wc['i_inrush_nom_A'])})",
              _stat.get("nominal_cold", "&#8212;")],
             ["Minimum-R25 cold inrush", f"&#8804; {_f(_tgt,0)} A hard", f"{_f(wc['i_inrush_max_A'],1)} A ({_mrg(wc['i_inrush_max_A'])})",
              _stat.get("min_r25_cold", "&#8212;")],
             ["Pulse energy", f"&#8805; {_f(r['e_pulse_required'],0)} J", "estimated (datasheet needed)",
              _stat.get("pulse_energy", "OPEN")],
             ["Precharge timing", f"&#8805; {_f(s['tau_multiple'],0)}&#183;&#964; + relay tol", f"{_f(r['t_bypass']*1e3,0)} ms",
              _stat.get("precharge_timing", "PASS")],
             ["Warm/hot restart", "policy required", (f"{_f(wc['i_warm_A'],0)} A" if wc.get('i_warm_A') else "TBD (R(T))"),
              _stat.get("hot_restart", "CHECK")],
             ["Relay make current", "&#8804; contact rating", (f"{_f(wc['i_relay_make_A'],2)} A" if wc.get('i_relay_make_A') else "TBD"),
              _stat.get("relay_make", "OPEN")],
             ["Fuse I²t", "&#8804; pre-arcing I²t", f"{_f(wc['i2t_worst'],1)} A²s worst",
              _stat.get("fuse_i2t", "OPEN")],
             ["Fuse — six-gate screen", "all 6 gates closed (Section 8.6)",
              (("gates " + ", ".join(str(n) for n in (fuse.get("gates_open") or [])) + " OPEN")
               if fuse.get("gates_open") else
               (("gates " + ", ".join(str(n) for n in (fuse.get("gates_conditional") or [])) + " estimated")
                if fuse.get("gates_conditional") else "all closed")),
              fuse.get("gate_status", "OPEN")],
             ["Bridge surge current", "&#8804; I<sub>FSM</sub>", (f"{_f(wc['bridge_ifsm_a'],0)} A rating" if wc.get('bridge_ifsm_a') else "see Ch 7 Section 7.3.1"),
              _stat.get("bridge_surge", "OPEN")],
             ["Bypass / stuck relay", "cleared by fuse", (f"{_f(wc['i_bypassed_A'],0)} A" if wc.get('i_bypassed_A') else "DATA MISSING (path R)"),
              _stat.get("bypass_stuck", "OPEN")],
             ["Phase-angle sweep", "worst at 90&#176;", "included", _stat.get("phase_angle", "PASS")]],
            col_widths=[CW*0.26, CW*0.24, CW*0.30, CW*0.20], ch=CH)
        data_table(story, "8.9b", "Table B — Open Electrical Items",
            "What must be confirmed for release, and why.",
            ["Open item", "Source needed", "Why"],
            [["R25 tolerance", "NTC datasheet", "worst-case cold inrush"],
             ["R(T) / hot resistance", "NTC datasheet", "warm/hot restart current"],
             ["Pulse energy / max-C", "NTC datasheet", "NTC survival"],
             ["Fuse I²t rating", "fuse datasheet", "no nuisance/unsafe fuse"],
             ["Available fault current", "site / installation", "fuse breaking capacity (gate 4)"],
             ["MOV/GDT fail-short &amp; stuck-relay fault current", "Ch 9 + schematic", "fuse must clear safely (gate 5)"],
             ["Max ambient at the fuse + re-rating slope", "enclosure thermal + fuse datasheet", "current de-rating (gate 6)"],
             ["Fuseholder / PCB temperature rise", "measured on the bench", "fuse body within its limit (gate 6)"],
             ["Bridge I<sub>FSM</sub>", "bridge datasheet (Ch 7)", "rectifier survival"],
             ["Relay make rating", "relay datasheet", "safe bypass timing"],
             ["Relay-path impedance", "schematic / layout", "true make current & inrush"],
             ["Startup-path resistances", "schematic / layout", "bypassed / stuck-relay inrush"]],
            col_widths=[CW*0.30, CW*0.30, CW*0.40], ch=CH)

        # ── 8.14c release classification (Ready / Conditional / Open / Blocked) ──
        def _cls(item, ready, cond):
            v = _stat.get(item, "")
            return {"PASS": ready, "CHECK": cond, "OPEN": "Open",
                    "BLOCKED": "Blocked"}.get(v, "Open")
        data_table(story, "8.9c", "Table C — Release Classification",
            f"Overall NTC release status: <b>{_overall}</b>.",
            ["Item", "Release classification"],
            [["Nominal cold-start NTC sizing", _cls("nominal_cold", "Ready", "Conditional")],
             ["Minimum-R25 cold-start check", _cls("min_r25_cold", "Ready", "Conditional — hard-limit pass, margin to acknowledge")],
             ["Precharge target clarification", "Ready"],
             ["Relay precharge delay", "Conditional — selected-part timing + relay tolerance"],
             ["Relay make-current verification", _cls("relay_make", "Ready", "Conditional")],
             ["Warm / hot restart", _cls("hot_restart", "Ready", "Conditional — define restart policy")],
             ["Fuse I²t coordination", _cls("fuse_i2t", "Ready", "Conditional")],
             ["Fuse selection — six gates", {"PASS": "Ready", "CONDITIONAL": "Conditional — estimated value to confirm",
                                             "OPEN": "Open — site / thermal data needed",
                                             "FAIL": "Blocked"}.get(fuse.get("gate_status", "OPEN"), "Open")],
             ["Bridge / diode surge verification", _cls("bridge_surge", "Ready", "Conditional")],
             ["Pulse-energy confirmation", _cls("pulse_energy", "Ready", "Conditional")],
             ["Phase-angle startup sweep", "Ready"]],
            col_widths=[CW*0.46, CW*0.54], ch=CH)
        annotation(story, "RELEASE STATEMENT",
            "The selected NTC passes the nominal cold-start inrush calculation and the minimum-R25 hard "
            "current limit based on the current assumptions. Final electrical release remains CONDITIONAL "
            "until selected-part pulse-energy data, R25 tolerance, hot-restart policy, fuse I²t rating, relay "
            "make-current rating, relay-path impedance, and bridge I<sub>FSM</sub> margin are confirmed.", CH)

    # ── Figure 8.1 — inrush-limiter topology (NTC + relay bypass) ──
    _fig = _inrush_schematic_flowable()
    if _fig is not None:
        body(story, "<b>Figure 8.1 — Inrush-Limiter Topology (NTC + Relay Bypass)</b>", CH)
        story.append(_fig)
        body(story,
            f"The NTC <b>RT</b> limits the cold-start current into the bulk capacitor <b>C</b> "
            f"(C<sub>out</sub> = {_f(s['cout']*1e6,0)} {_MU}F); once the bus has precharged, the relay "
            f"contact <b>K</b> shorts RT out so it carries current only during the startup pulse. "
            f"Provisional sizing at this stage: R<sub>25</sub> &#8776; {_f(r['r25_pick'],2)} {_OHM} "
            f"(the value derived in Section 8.2, before a part is chosen), giving &#964; &#8776; "
            f"{_f(r['tau']*1e3,1)} ms and a bypass after {_f(r['t_bypass']*1e3,0)} ms. "
            "<b>These are requirement-derived figures, not the built values</b> — Section 8.4.2 "
            "recomputes the precharge timing on the R<sub>25</sub> of the part actually selected, and "
            "that is the number to design the relay delay around. Power path in black, relay-coil "
            "drive in blue; the diode <b>D</b> clamps the coil flyback.", CH)

    # ── 8.2 maximum allowed inrush target — the first real calculation starts HERE ──


# ══════════════════════════════════════════════════════════════════════════════
#  Chapter 9 — MOV surge protection & compliance (IEC/EN 61000-4-5)
# ══════════════════════════════════════════════════════════════════════════════
def build_mov_story(story, design, mosfet=None, cap=None, opts=None):
    CH = 9
    opts = dict(opts or {})
    # Auto-feed the selected line fuse (Ch8) into the MOV/GDT fail-short coordination when the designer
    # left the fuse I²t blank — the same fuse closes the whole protection chain.
    _fuse = calculate_fuse(design, cap or {}, opts)
    if not opts.get("fuse_i2t_rating_A2s") and _fuse.get("selected_i2t"):
        opts["fuse_i2t_rating_A2s"] = _fuse["selected_i2t"]
    out = calculate_mov(design, mosfet or {}, cap or {}, opts)
    s = out["spec"]; st = out["stress"]; mc = out["mcov"]; cr = out["criterion"]
    tg = out["targets"]; cat = out["catalog"]
    cand = out.get("candidates") or []
    en = out.get("energy") or {}; ov = out.get("overshoot") or {}; fz = out.get("fuse_coord") or {}
    mcmp = out.get("mcov_comparison") or []; cmx = out.get("criterion_matrix") or []
    lvl = s.get("level"); crit = cr["name"]
    # Architecture recommendation is needed by Section 9.3 (before parts) AND by Section 9.10;
    # compute once and hand the same packet to both so they can never disagree.
    try:
        _gdt_pre = calculate_gdt(design, opts, environment=opts.get("environment"))
    except Exception:
        _gdt_pre = None

    chapter_splash(story, CH, "Surge Protection & Compliance (MOV, IEC/EN 61000-4-5)",
        "Does the metal-oxide varistor clamp the combination-wave surge below the downstream "
        "withstand while surviving the repetitive pulse current — and is the result traceable to the "
        "declared test level and performance criterion for certification?",
        ["9.1 Design inputs & compliance target  ·  9.2 Surge stress per coupling mode",
         "9.3 Protection architecture decision — MOV-only vs MOV+GDT, before any part",
         "9.4 MOV voltage CLASS selection (9.4.1 class comparison · 9.4.2 class-level clamp)",
         "9.5 Electrical selection gates (9.5.1 energy survival) — declared before screening",
         "9.6 Candidate database screen  ·  9.7 Selected MOV & recalculation (9.7.1 overshoot)",
         "9.8 Criterion A/B/C decision  ·  9.9 Fuse / thermal coordination (fail-short)",
         "9.10 Optional GDT path  ·  9.11 Release-readiness matrix (9.11.1 certification record)"])

    # One-page selection map, so the reader knows which decision each section settles before
    # meeting any numbers (MOV review, "Immediate report improvements").
    annotation(story, "HOW THIS CHAPTER IS ORGANISED — FIVE DECISION LAYERS",
        "A pass in one layer does NOT imply a pass in the next. <b>Layer 1 — compliance target</b> "
        "(Section 9.1-9.2): what surge must be survived, and to which performance criterion. "
        "<b>Layer 2 — architecture</b> (Section 9.3): MOV-only, or MOV plus a GDT for the earth-referred "
        "paths. <b>Layer 3 — MOV voltage class</b> (Section 9.4): which MCOV class can sit on the line "
        "continuously; this is a CLASS decision, not a part. <b>Layer 4 — part selection and electrical "
        "coordination</b> (Sections 9.5-9.8): gates declared, catalog screened, a part chosen, then clamp "
        "and energy recalculated on THAT part and judged against the criterion. <b>Layer 5 — safety "
        "coordination</b> (Section 9.9-9.10): if the MOV fails short or the GDT conducts follow current, "
        "the upstream fuse must clear it. Section 9.11 is the release sign-off.", CH)

    # ── 9.1 ──
    step_h(story, "9.1", "Compliance Basis", CH)
    annotation(story, "CONCEPT",
        "Per IEC/EN 61000-4-5 the surge is a combination wave applied through defined source impedances "
        "(2 &#937; differential; +10 &#937; CDN for line-to-earth). Three orthogonal inputs drive every "
        "number: the TEST LEVEL sizes the stress (open-circuit voltages → short-circuit currents), the "
        "PERFORMANCE CRITERION sizes the acceptance bar (A ride-through, B self-recover, C operator "
        "reset), and the continuous LINE sets the MCOV. The declared level + criterion are the "
        "certification record.", CH)
    data_table(story, "9.1a", "Declared Compliance Inputs", "These choices are the certification basis.",
        ["Input", "Value", "Governs"],
        [["Test level (61000-4-5)", str(lvl), "surge stress (currents/energies)"],
         ["Performance criterion", crit + (" — ride-through" if cr["ride_through"] else " — survive/reset"), "acceptance bar / device gate"],
         ["Continuous line", f"{_f(s['vac_max'],0)} V<sub>ac</sub> max", "MCOV (invariant to level/criterion)"],
         ["Downstream device V<sub>ds</sub>", f"{_f(s['device_vds'],0)} V (from selected MOSFET)", "coordination gate"]],
        col_widths=[CW*0.34, CW*0.40, CW*0.26], ch=CH)
    body(story,
        "<b>Test-level basis.</b> IEC/EN 61000-4-5 defines installation classes by the surge environment. "
        "The declared level must match where the product is installed — a benign, protected supply vs a "
        "long-cable / heavy-industrial / lightning-exposed feed. Typical AC-mains surge sources: "
        "lightning-induced transients, utility and capacitor-bank switching, motor switching, and general "
        "grid disturbances.", CH)
    data_table(story, "9.1b", "IEC/EN 61000-4-5 Installation Levels (AC power port)",
        f"Declared level for this design: <b>{lvl}</b>.",
        ["Level", "L-N (V<sub>oc</sub>)", "L/N-PE (V<sub>oc</sub>)", "Typical environment"],
        [["1", "&#8212;", "500 V", "well-protected / dedicated supply"],
         ["2", "500 V", "1 kV", "partially protected / light commercial"],
         ["3", "1 kV", "2 kV", "typical commercial / industrial mains"],
         ["4", "2 kV", "4 kV", "harsh industrial / long cable / high exposure"]],
        col_widths=[CW*0.10, CW*0.20, CW*0.22, CW*0.48], ch=CH)

    # ── 9.2 stress ──
    sub_h(story, "9.2", "Surge Stress per Coupling Mode", CH)
    body(story,
        "Each protection path is driven by its open-circuit test voltage through its own source "
        "impedance; the MOV-absent short-circuit current is I<sub>sc</sub> = V<sub>oc</sub>/Z. The "
        "line-to-earth current is lower than line-to-line despite the higher voltage — that is the "
        "standard&#8217;s 12 &#937; CDN impedance.", CH)
    eq_box(story, [r"I_{sc}=\dfrac{V_{oc}}{Z}\quad(Z=2\,\Omega\ \mathrm{diff},\ 12\,\Omega\ \mathrm{c.m.})"],
           number="9.2", ch=CH)
    data_table(story, "9.2", "Stress per Path", f"Governing (highest current): {st['governing'] or '&#8212;'}.",
        ["Path", "Mode", "Z (" + _OHM + ")", "V<sub>oc</sub> (V)", "I<sub>sc</sub> (A)"],
        [[p["name"], p["mode"], f"{_f(p['z'],0)}", f"{_f(p['v_oc'],0)}", f"{_f(p['i_sc'],0)}"] for p in st["paths"]]
          or [["&#8212;", "", "", "", ""]],
        col_widths=[CW*0.34, CW*0.20, CW*0.14, CW*0.16, CW*0.16], ch=CH)
    body(story,
        "The combination wave is a 1.2/50 &#181;s open-circuit voltage and an 8/20 &#181;s short-circuit "
        "current; L-N is the governing (highest-current) case in this design. Worked substitution for the "
        "governing path: I<sub>sc</sub> = V<sub>oc</sub>/Z.", CH)

    # ── 9.3 protection architecture decision — BEFORE any part is chosen ──
    sub_h(story, "9.3", "Protection Architecture Decision", CH)
    body(story,
        "Before any part is screened the protection ARCHITECTURE must be fixed, because it decides which "
        "gates apply. The differential L-N path is always clamped by a MOV. The common-mode L-PE / N-PE "
        "paths may be handled by MOVs alone, or by a MOV plus a gas-discharge tube that diverts the large "
        "earth-referred surge current. A GDT adds its own no-fire, dynamic-sparkover, follow-current and "
        "fail-short gates (Section 9.10), so it is only taken when the common-mode stress or the install "
        "environment calls for it.", CH)
    _arch_rec = (_gdt_pre or {}).get("required") or {}
    _arch_chosen = (opts or {}).get("surge_architecture")
    data_table(story, "9.3", "Protection Architecture",
        "The baseline is MOV-only; MOV+GDT is a separate optional branch evaluated in Section 9.10.",
        ["Item", "Value"],
        [["Install environment", str((opts or {}).get("environment", "commercial"))],
         ["Recommended architecture", str(_arch_rec.get("recommend", "MOV-only"))],
         ["GDT status", "REQUIRED" if _arch_rec.get("required") else "OPTIONAL"],
         ["Reason", str(_arch_rec.get("reason", "common-mode stress within MOV capability"))[:150]],
         ["Designer decision", str(_arch_chosen) if _arch_chosen else "follow recommendation"]],
        col_widths=[CW*0.30, CW*0.70], ch=CH)

    # ── 9.4 mcov ──
    sub_h(story, "9.4", "MOV Voltage CLASS Selection (MCOV)", CH)
    body(story,
        "<b>Model.</b> The maximum continuous operating voltage is set ONLY by the continuous worst-case "
        "line, independent of the surge test level and the performance criterion — a varistor that "
        "conducts at the line peak would overheat. It snaps up to the next standard varistor class.", CH)
    body(story,
        f"<b>Worked.</b> With the continuous worst-case line of {_f(s['vac_max'],0)} V<sub>ac</sub> and the "
        f"binding margin, the required MCOV is {_f(mc['required'],0)} V<sub>ac</sub>; this snaps up to the "
        f"standard <b>{_f(mc['class'],0)} V<sub>ac</sub></b> class, whose nominal varistor voltage is "
        f"V<sub>1mA</sub> &#8776; {_f(mc['v1ma'],0)} V. Because it depends on the line alone, changing the "
        f"surge level must not move this number.", CH)

    # ── 9.4.1 MCOV class comparison ──
    sub_h(story, "9.4.1", "MCOV Class Comparison — Leakage/Aging vs Clamp", CH)
    body(story,
        "A higher MCOV class buys more headroom over the line peak (V<sub>pk</sub> = "
        f"{_f(1.41421356*s['vac_max'],0)} V), which lowers standby leakage and slows aging — but it raises "
        "the clamp voltage, eroding downstream margin. Leakage/aging is graded by the varistor-voltage "
        "headroom over the line peak (V<sub>1mA</sub>/V<sub>pk</sub>).", CH)
    data_table(story, "9.4.1", "Candidate MCOV Classes",
        "Higher class → lower leakage/aging, higher clamp. Selected class is the binding minimum.",
        ["MCOV (V<sub>ac</sub>)", "V<sub>1mA</sub> (V)", "Peak headroom", "Leakage/aging", "Clamp trade-off"],
        [[f"{_f(r['mcov'],0)}" + (" &#9733;" if r.get("selected") else ""), f"{_f(r['v1ma'],0)}",
          f"{_f(r['peak_headroom'],2)}&#215;", r["leakage_aging"], r["clamp_tradeoff"]] for r in mcmp]
          or [["&#8212;", "", "", "", ""]],
        col_widths=[CW*0.18, CW*0.16, CW*0.18, CW*0.18, CW*0.30], ch=CH)

    # ── 9.4.2 clamp ──
    sub_h(story, "9.4.2", "Class-Level Clamp (Load-Line Let-Through)", CH)
    body(story,
        "<b>Model.</b> The let-through (clamp) voltage is the operating point where the varistor's highly "
        "non-linear V-I curve V = V<sub>1mA</sub>(I/1mA)<sup>1/&#945;</sup> meets the surge source load "
        "line V = V<sub>drive</sub> &#8722; I&#183;Z. We solve that intersection rather than reading a "
        "fixed datasheet clamp, because the actual clamp depends on the surge current the source can push. "
        "The surge rides on the line peak (phase superposition), so V<sub>drive</sub> includes the line "
        "peak. The clamp must stay under the criterion-set device gate.", CH)
    eq_box(story, [r"V=V_{1mA}\left(\dfrac{I}{1mA}\right)^{1/\alpha}=V_{drive}-I\,Z"], number="9.4.2", ch=CH)
    _gov = next((t for t in tg if t["path"] == st.get("governing")), tg[0] if tg else None)
    if _gov:
        body(story,
            f"<b>Worked (governing path — {_gov['path']}).</b> The drive voltage is V<sub>drive</sub> = "
            f"{_f(_gov['v_drive'],0)} V through Z = {_f(_gov['z'],0)} {_OHM}; the V-I curve meets that load "
            f"line at I<sub>op</sub> = {_f(_gov['i_op'],0)} A, giving a let-through clamp <b>V<sub>c</sub> = "
            f"{_f(_gov['vc'],0)} V</b>. The criterion-{crit} device gate is {_f(_gov['device_gate'],0)} V, so "
            f"the coordination verdict is <b>{_gov['coord']}</b>; the chosen part's 8/20 surge rating must "
            f"also exceed the design target I<sub>max</sub> &#8805; {_f(_gov['imax_required'],0)} A. The full "
            f"per-path picture is below.", CH)
    data_table(story, "9.4.2", "Per-Path Clamp & Coordination", "Let-through vs the device gate at each path.",
        ["Path", "V<sub>drive</sub> (V)", "I<sub>op</sub> (A)", "Clamp V<sub>c</sub> (V)",
         "I<sub>max</sub> req (A)", "Gate (V)", "Verdict"],
        [[t["path"], f"{_f(t['v_drive'],0)}", f"{_f(t['i_op'],0)}", f"{_f(t['vc'],0)}",
          f"{_f(t['imax_required'],0)}", f"{_f(t['device_gate'],0)}", t["coord"]] for t in tg]
          or [["&#8212;", "", "", "", "", "", ""]],
        col_widths=[CW*0.26, CW*0.13, CW*0.11, CW*0.14, CW*0.14, CW*0.11, CW*0.11], ch=CH)

    # ── 9.5 electrical selection gates — declared BEFORE the candidate screen ──
    sub_h(story, "9.5", "MOV Electrical Selection Gates", CH)
    body(story,
        "These are the numbers a catalog MOV must clear, derived from the requirement alone. They are "
        "stated <b>before</b> the candidate screen so that Section 9.6 is a filter against declared gates "
        "rather than a conclusion. Nothing here names a part — the MOV voltage class chosen in Section 9.4 "
        "is a <i>class</i> decision, not a selection.", CH)
    # engine gate strings are ASCII; render them with the same glyphs the rest of the report uses
    _ge = lambda x: str(x).replace(">=", "&#8805;").replace("<=", "&#8804;")
    _gts = out.get("gates") or []
    data_table(story, "9.5", "Electrical Selection Gates",
        "Every gate is derived above; a candidate must clear all of them to be release-qualified.",
        ["#", "Gate", "Requirement", "Basis"],
        [[str(g["n"]), g["name"], _ge(g["requirement"]), g["basis"]] for g in _gts]
          or [["&#8212;", "", "", ""]],
        col_widths=[CW*0.05, CW*0.26, CW*0.21, CW*0.48], ch=CH)

    # ── 9.5.1 energy survival requirement ──
    sub_h(story, "9.5.1", "Energy Survival Requirement", CH)
    body(story,
        "MOV survival is not set by peak current alone — the absorbed pulse energy must stay under the "
        "datasheet single-pulse rating, derated for repetitive pulses and temperature. Exact integration "
        "E = &#8747;v&#183;i dt is approximated conservatively from the clamp voltage, peak current and an "
        "effective pulse width.", CH)
    eq_box(story, [r"E_{MOV}=\int v_{MOV}\,i_{MOV}\,dt \approx 1.4\,V_c\,I_{pk}\,\tau_{8/20}"],
           number="9.2a", ch=CH)
    if en.get("e_rating_J") is not None:
        _eok = "PASS" if en.get("ok") else "OVER"
        body(story,
            f"<b>Worked.</b> Governing-path pulse energy E<sub>surge</sub> &#8776; "
            f"<b>{_f(en['e_surge_J'],1)} J</b> vs allowable {_f(en['e_allow_J'],1)} J "
            f"(datasheet {_f(en['e_rating_J'],0)} J &#215; derate {_f(s.get('mov_energy_derate',0.8),2)} / "
            f"criterion safety {_f(cr['energy_safety'],2)}) &#8658; <b>{_eok}</b>.", CH)
    else:
        annotation(story, "DATA MISSING",
            "Datasheet single-pulse energy not available for the governing candidate — energy survival "
            "cannot be confirmed. Add the J rating to the workbook.", CH)

    # ── 9.6 candidates ──
    sub_h(story, "9.6", "Candidate Datasheet Screen (Governing Path)", CH)
    if cand:
        def _clamp_cell(c):
            return f"{_f(c['clamp_vc'],0)} V" if c.get("clamp_vc") is not None else "DATA MISSING"
        def _cons(c):
            v = c.get("part_num_consistent")
            return "&#10003;" if v else ("&#10007;" if v is False else "&#8212;")
        data_table(story, "9.6", "Vendor MOV Screen (governing path)",
            f"Criterion {crit}, from the live vendor database. Clamp is computed from the datasheet V-I "
            "curve where V<sub>c</sub>@I<sub>n</sub> is present; otherwise flagged DATA MISSING (never a "
            "silent pass).",
            ["Part", "MCOV", "V<sub>1mA</sub>", "I<sub>8/20</sub>", "Energy", "Cap", "Clamp", "P#&#8226;", "Verdict"],
            [[str(c.get("part_number") or c["label"])[:20], f"{_f(c.get('mcov'),0)}",
              f"{_f(c.get('v1ma'),0)}", f"{_f(c.get('imax'),0)}",
              (f"{_f(c.get('energy_2ms_J'),0)}J" if c.get("energy_2ms_J") else "&#8212;"),
              (f"{_f(c.get('capacitance_pf'),0)}p" if c.get("capacitance_pf") else "&#8212;"),
              _clamp_cell(c), _cons(c), c.get("verdict", "PASS" if c["ok"] else "FAIL")] for c in cand[:10]],
            col_widths=[CW*0.20, CW*0.09, CW*0.10, CW*0.11, CW*0.10, CW*0.10, CW*0.13, CW*0.06, CW*0.11], ch=CH)
        body(story, "<i>P#&#8226; = part-number vs MCOV consistency check. Full reason strings and "
             "datasheet URLs are in the selector output.</i>", CH)
    else:
        data_table(story, "9.6", "Catalog Screen (governing path)",
            f"Criterion {crit}. Representative values — verify the V<sub>c</sub>-vs-I curve and the "
            "10-pulse repetitive derating on the live datasheet.",
            ["Verdict", "Candidate part", "Notes"],
            [["PASS" if c["ok"] else "FAIL", c["name"], "; ".join(c["reasons"])[:120]] for c in cat] or [["—", "no catalog", "—"]],
            col_widths=[CW*0.12, CW*0.42, CW*0.46], ch=CH)
    annotation(story, "NOTE",
        "Placement: one differential MOV across L-N at the AC inlet after the fuse; common-mode MOVs "
        "L-PE and N-PE (watch leakage & creepage). Keep leads short/low-inductance (overshoot on the "
        "1.2 &#181;s edge). Pair with an upstream fuse + thermal protection (or a TMOV).", CH)

    # ── 9.7 selected MOV + recalculation — the FIRST place a part is named ──
    _sel = out.get("selected"); _rc = out.get("selected_recalc")
    sub_h(story, "9.7", "Selected MOV & Recalculation", CH)
    if _sel and _rc:
        body(story,
            f"Only now, with the gates declared (Section 9.5) and the catalog screened (Section 9.6), is a "
            f"part named. <b>Selected MOV: {_sel.get('mfr','')} {_sel.get('part_number','')}</b> — "
            f"{_f(_sel.get('mcov'),0)} V<sub>ac</sub> MCOV, V<sub>1mA</sub> = {_f(_rc.get('v1ma'),0)} V. "
            "Every figure below is recomputed from THIS part's datasheet, not from the voltage class: the "
            "class-level clamp in Section 9.4.2 used a snapped class V<sub>1mA</sub>, whereas the load line "
            "below is solved against the part's own varistor voltage.", CH)
        _cls_vc = (_gov or {}).get("vc")
        data_table(story, "9.7", "Selected Part — Recalculated Design Values",
            "Part-specific results. The clamp supersedes the class-level figure of Section 9.4.2.",
            ["Quantity", "Value", "Check"],
            [["Part", f"{_sel.get('mfr','')} {_sel.get('part_number','')}", "designer-selected"],
             ["V<sub>1mA</sub> (datasheet)", f"{_f(_rc.get('v1ma'),0)} V", "drives the load line"],
             ["Varistor exponent &#945;", f"{_f(_rc.get('alpha'),1)}",
              ("ESTIMATED — no datasheet V<sub>c</sub>" if _rc.get("alpha_estimated") else "from datasheet V<sub>c</sub>")],
             ["Operating current I<sub>op</sub>", f"{_f(_rc.get('i_op'),0)} A", "load-line intersection"],
             ["Clamp V<sub>c</sub> (this part)", f"<b>{_f(_rc.get('vc'),0)} V</b>",
              (f"class-level was {_f(_cls_vc,0)} V" if _cls_vc is not None else "&#8212;")],
             ["Device gate", f"{_f(_rc.get('device_gate'),0)} V", f"Criterion {crit}"],
             ["Clamp margin", f"{_f(_rc.get('clamp_margin_V'),0)} V",
              "positive = clamps below the gate"]],
            col_widths=[CW*0.32, CW*0.30, CW*0.38], ch=CH)
        data_table(story, "9.7", "Selected Part — Gate-by-Gate Verdict",
            "Each Section 9.5 gate re-evaluated against this part's datasheet.",
            ["#", "Gate", "Requirement", "Result", "Status"],
            [[str(g["n"]), g["name"], _ge(g["requirement"]), _ge(g["result"]), g["status"]]
             for g in (_rc.get("gates") or [])],
            col_widths=[CW*0.05, CW*0.24, CW*0.28, CW*0.26, CW*0.17], ch=CH)
        if _rc.get("alpha_estimated"):
            annotation(story, "CLAMP IS ESTIMATED — NOT A VERIFIED PASS OR FAIL",
                "This part publishes no clamp voltage at a rated current, so the generic varistor exponent "
                "was used to solve the load line. The clamp gate is therefore reported DATA MISSING: an "
                f"estimate cannot settle Criterion {crit} in either direction. Add the datasheet "
                "V<sub>c</sub>@I<sub>n</sub> to the workbook to close it.", CH)
        _blk = _rc.get("blockers") or []
        if _blk:
            annotation(story, f"RELEASE STATUS: {_rc.get('release_status','DATA MISSING')}",
                "Open before sign-off: " + "; ".join(_blk) + ". These gate the final RELEASE only — "
                "the part above remains selectable and every downstream section is computed from it.", CH)
        body(story, f"<i>Energy survival is judged against the {out.get('energy_basis','selected part')}.</i>", CH)
    else:
        annotation(story, "NO MOV PART SELECTED YET",
            "Section 9.4 fixed the MOV voltage CLASS and Section 9.6 screened the catalog, but no part has "
            "been selected. The clamp, energy and margin figures elsewhere in this chapter are therefore "
            "CLASS-level results, not part results. Select a candidate to recalculate the design around a "
            "real datasheet.", CH)

    # ── 9.7.1 layout overshoot ──
    sub_h(story, "9.7.1", "Layout Parasitic Overshoot", CH)
    body(story,
        "During the fast surge front the parasitic inductance of the MOV loop adds a voltage overshoot "
        "V<sub>over</sub> = L<sub>parasitic</sub>&#183;di/dt on top of the clamp — the effective let-through "
        "the downstream device sees is V<sub>c</sub> + V<sub>over</sub>. This is why the MOV must sit at the "
        "AC inlet on short, wide, low-loop-area copper, right after the fuse.", CH)
    eq_box(story, [r"V_{over}=L_{parasitic}\,\dfrac{di}{dt},\qquad V_{c,eff}=V_c+V_{over}"],
           number="9.7", ch=CH)
    if ov:
        body(story,
            f"<b>Worked.</b> With L<sub>parasitic</sub> = {_f(ov['l_nH'],0)} nH and di/dt = "
            f"{_f(ov['di_dt_A_per_us'],1)} A/&#181;s (8/20 front), V<sub>over</sub> &#8776; "
            f"<b>{_f(ov['v_overshoot'],1)} V</b> &#8658; effective let-through V<sub>c,eff</sub> &#8776; "
            f"<b>{_f(ov['vc_effective'],0)} V</b>. Long leads (100s of nH) multiply this — keep the loop "
            "tight.", CH)

    # ── 9.8 criterion ──
    sub_h(story, "9.8", "Performance Criterion — A/B/C Pass-Fail", CH)
    annotation(story, "THEORY",
        f"Criterion {crit}: ride-through = {cr['ride_through']}; the device gate is "
        + ("the transient abs-max (survival)." if cr["gate_uses_absmax"]
           else f"V<sub>ds</sub> &#8722; {_f(cr['dev_margin_V'],0)} V (protective margin).")
        + " Under A, a clamp above the gate is a FAIL — the bus must keep regulating; under B/C a clamp "
          "above V<sub>ds</sub> but below abs-max is acceptable (the unit may dip/reset). The criterion "
          "changes the gate and verdict wording, not the surge currents or energies.", CH)
    data_table(story, "9.8a", "Criterion A/B/C — Governing Clamp Verdict",
        "Same surge stress; only the acceptance gate and verdict change.",
        ["Criterion", "Meaning", "Device gate (V)", "Verdict"],
        [[r["criterion"] + (" &#9733;" if r["criterion"] == crit else ""),
          "ride-through" if r["ride_through"] else "survive / reset allowed",
          f"{_f(r['gate'],0)}", r["verdict"]] for r in cmx]
          or [["&#8212;", "", "", ""]],
        col_widths=[CW*0.16, CW*0.42, CW*0.20, CW*0.22], ch=CH)
    # DECISION BOX — the review's core ask: a numeric result must never sit alone without the
    # engineering decision that follows from it.
    _dec_vc = (_rc or {}).get("vc", (_gov or {}).get("vc") if _gov else None)
    _dec_gate = (_rc or {}).get("device_gate", (_gov or {}).get("device_gate") if _gov else None)
    _dec_est = bool((_rc or {}).get("alpha_estimated"))
    if _dec_vc is not None and _dec_gate is not None:
        _margin = _dec_gate - _dec_vc
        _basis = ("the SELECTED part" if _rc else "the MOV voltage CLASS (no part selected yet)")
        if _dec_est:
            annotation(story, f"DECISION REQUIRED — Criterion {crit} cannot be settled on estimated data",
                f"Calculated let-through is {_f(_dec_vc,0)} V against a {_f(_dec_gate,0)} V gate "
                f"({_margin:+.0f} V) on {_basis}, but the clamp rests on an ESTIMATED varistor exponent "
                "because no datasheet V<sub>c</sub>@I<sub>n</sub> is available. Status is DATA MISSING, "
                "not PASS and not FAIL. To close it: add the datasheet clamp, or decide on one of the "
                "options below in case the verified clamp also exceeds the gate.", CH)
        elif _margin < 0:
            annotation(story, f"DECISION REQUIRED — Criterion {crit} NOT met (MOV-only)",
                f"Calculated let-through is {_f(_dec_vc,0)} V against a {_f(_dec_gate,0)} V gate on "
                f"{_basis} &#8658; margin {_margin:+.0f} V. This is a formal Criterion-{crit} FAIL for the "
                "MOV-only architecture and gates RELEASE (it does not block part selection).", CH)
        else:
            annotation(story, f"Criterion {crit} met (MOV-only)",
                f"Let-through {_f(_dec_vc,0)} V against a {_f(_dec_gate,0)} V gate on {_basis} &#8658; "
                f"margin {_margin:+.0f} V. Confirm on the bench with the real layout, since parasitic "
                "overshoot (Section 9.7.1) adds to the clamp the device actually sees.", CH)
    if _dec_est or (_dec_vc is not None and _dec_gate is not None and _dec_gate - _dec_vc < 0):
        data_table(story, "9.8b", "Engineering Options if the Verified Clamp Exceeds the Gate",
            "Resolve ONE of these; each is a design decision, not a calculation.",
            ["Option", "What it changes"],
            [["Lower let-through MOV", "larger disc / lower MCOV class — watch leakage and aging (Section 9.4.1)"],
             ["Raise the downstream withstand", "higher-V<sub>ds</sub> device or a clamped snubber — a Chapter-7 change"],
             ["Add a coordinated second stage", "series impedance + follow-on clamp so the MOV is not alone"],
             ["Add series impedance", "raises the source Z the MOV works against, lowering I<sub>op</sub> and V<sub>c</sub>"],
             ["Accept Criterion B or C", "only if the product specification permits dip/reset behaviour"]],
            col_widths=[CW*0.34, CW*0.66], ch=CH)

    # ── 9.9 fuse / thermal coordination ──
    sub_h(story, "9.9", "Fuse / Thermal Coordination (Fail-Short Safety)", CH)
    body(story,
        "After severe or repeated surges a MOV can fail SHORT. The upstream fuse (or a TMOV's integral "
        "thermal disconnect) must make that failure safe — the MOV must be downstream of the fuse, the "
        "available fault current must be within the fuse breaking capacity, and the fuse I&#178;t/clearing "
        "curve must open before the MOV reaches an unsafe thermal condition.", CH)
    if fz.get("ok"):
        annotation(story, "COORDINATION OK", fz.get("note", ""), CH)
    else:
        annotation(story, "DATA MISSING",
            fz.get("note", "Provide the available fault current and the upstream fuse I&#178;t to prove "
                   "the fail-short path is cleared safely."), CH)

    # ── 9.10 GDT (common-mode surge diverter) + 9.9 combined release matrix ──
    # MOV-only coordination verdict handed to the release matrix. Prefer the SELECTED part's clamp
    # (Section 9.7) over the class-level per-path result; an estimated clamp cannot assert PASS.
    if _rc:
        verdict = ("REVIEW" if _rc.get("alpha_estimated")
                   else ("PASS" if (_rc.get("clamp_margin_V") or 0) >= 0 else "FAIL"))
    else:
        verdict = "PASS" if (tg and all(t["coord"] != "FAIL" for t in tg)) else "REVIEW"
    _build_gdt_section(story, design, opts, CH, mov_out=out, mov_verdict=verdict, gdt_pre=_gdt_pre)


def _build_gdt_section(story, design, opts, CH, mov_out=None, mov_verdict="REVIEW", gdt_pre=None):
    """Section "9.10" — GDT common-mode surge diversion: MOV-vs-MOV+GDT recommendation, no-fire gate, surge-current
    class, candidate screen, and the follow-current / fail-short safety checks (with DATA-MISSING gates)."""
    g = gdt_pre or calculate_gdt(design, opts or {}, environment=(opts or {}).get("environment"))
    rec = g.get("required") or {}; sN = g.get("stress") or {}
    fc = g.get("follow_current") or {}; fs = g.get("fail_short") or {}
    gc = g.get("candidates") or []

    step_h(story, "9.10", "Common-Mode Surge Diversion (GDT)", CH)
    body(story,
        "A gas-discharge tube is not a precision clamp — it is a high-current common-mode surge "
        "<b>diverter</b>. The MOV controls the fast/residual voltage; once the GDT fires it carries the "
        "large line/neutral-to-earth surge current. Whether a GDT is needed follows from the common-mode "
        "surge level and the install environment.", CH)
    _rq = "REQUIRED" if rec.get("required") else "OPTIONAL"
    _chosen = (opts or {}).get("surge_architecture")
    _dec = (f" Designer decision: <b>{_chosen}</b>." if _chosen else
            " The designer may accept this or force MOV-only / MOV+GDT.")
    annotation(story, f"RECOMMENDATION — {rec.get('recommend','MOV-only')} ({_rq})",
        rec.get("reason", "") + _dec, CH)

    # 9.8.1 stress + no-fire
    sub_h(story, "9.10.1", "No-Fire & Surge-Current Sizing", CH)
    eq_box(story, [r"V_{spark,min}>V_{line,pk}\cdot K,\qquad I_{GDT}\geq K_{margin}\cdot\dfrac{V_{LE}}{Z_{cm}}"],
           number="9.10", ch=CH)
    body(story,
        f"<b>Worked.</b> Common-mode surge V<sub>LE</sub> = {_f(sN.get('v_le'),0)} V through Z<sub>cm</sub> "
        f"gives I<sub>sc</sub> = {_f(sN.get('i_sc'),0)} A; with the design margin the target is "
        f"I<sub>GDT</sub> &#8805; <b>{_f(sN.get('i_required'),0)} A</b> (prefer a standard "
        f"{_f(sN.get('preferred_class_A'),0)} A class). The GDT must NOT fire on the line: minimum "
        f"sparkover (after tolerance) must exceed <b>{_f(sN.get('no_fire_need_V'),0)} V</b> "
        "(line peak &#215; no-fire margin).", CH)

    # 9.8.2 candidate screen
    sub_h(story, "9.10.2", "Candidate GDT Screen", CH)
    if gc:
        def _v(x, u=""):
            return (f"{_f(x,0)}{u}" if x is not None else "&#8212;")
        data_table(story, "9.10", "Vendor GDT Screen (common-mode)",
            "No-fire (min sparkover vs line peak) and 8/20 surge class from the live database. Dynamic "
            "(impulse) sparkover is DATA MISSING in the export — flagged, never assumed.",
            ["Part", "V<sub>spark</sub> nom/min", "I<sub>8/20</sub>", "Poles", "No-fire", "Surge", "Dyn.spark", "Verdict"],
            [[str(c.get("part_number") or c["label"])[:18],
              f"{_v(c.get('v_spark_nom'))}/{_v(c.get('v_spark_min'))}", _v(c.get("imax_impulse"), "A"),
              _v(c.get("poles")), ("&#10003;" if c.get("no_fire_ok") else ("&#8212;" if c.get("no_fire_ok") is None else "&#10007;")),
              ("&#10003;" if c.get("surge_ok") else "&#10007;"), c.get("dynamic_status", "&#8212;"),
              "PASS" if c["ok"] else "FAIL"] for c in gc[:10]],
            col_widths=[CW*0.19, CW*0.16, CW*0.10, CW*0.08, CW*0.11, CW*0.09, CW*0.16, CW*0.11], ch=CH)
    else:
        body(story, "<i>(no GDT catalog available)</i>", CH)

    # 9.8.3 follow-current + fail-short safety
    sub_h(story, "9.10.3", "Follow-Current & Fail-Short Safety", CH)
    body(story,
        "After the surge the AC source can sustain the arc (follow current), and a GDT can eventually fail "
        "short. On an L/N-to-PE GDT both must be proven safe — self-extinction or fuse clearing — or the "
        "part cannot be signed off.", CH)
    annotation(story, "FOLLOW-CURRENT" + (" — OK" if fc.get("ok") else " — FAIL / DATA MISSING"), fc.get("note", ""), CH)
    annotation(story, "FAIL-SHORT" + (" — OK" if fs.get("ok") else " — FAIL / DATA MISSING"), fs.get("note", ""), CH)
    annotation(story, "MOV + GDT COORDINATION",
        "Staged protection: the MOV limits the initial/residual voltage while the GDT diverts the high "
        "common-mode current once it fires. Verify MOV MCOV vs continuous L-N voltage, GDT minimum "
        "sparkover vs continuous L/N-PE voltage, MOV clamp vs downstream device limits, GDT impulse "
        "sparkover vs insulation withstand, and the follow-current / fail-short fuse clearing above.", CH)

    # ── 9.11 combined MOV-only vs MOV+GDT release-readiness matrix ──
    mo = mov_out or {}
    en = mo.get("energy") or {}; fz = mo.get("fuse_coord") or {}; mc = mo.get("mcov") or {}
    step_h(story, "9.11", "MOV-only vs MOV+GDT — Release-Readiness Matrix", CH)
    body(story,
        "The certification sign-off view. MOV-only is release-ready when clamp, energy, lifetime and fuse "
        "coordination pass; MOV+GDT additionally requires the GDT no-fire tolerance, dynamic sparkover, "
        "follow-current and fail-short fuse clearing to pass. The recommended architecture for this design "
        f"is <b>{rec.get('recommend','MOV-only')}</b>.", CH)

    def _mark(v):   # tri-state cell
        return "PASS" if v is True else ("DATA MISSING" if v is None else "FAIL")
    _clamp_ok = None
    if mo.get("targets"):
        _coords = [t.get("coord") for t in mo["targets"]]
        _clamp_ok = (all(c != "FAIL" for c in _coords)) if all(c not in (None, "") for c in _coords) else None
    _energy_ok = en.get("ok"); _fz_ok = fz.get("ok")
    _gdt_nofire = None
    if gc:
        _gdt_nofire = any(c.get("no_fire_ok") and c.get("surge_ok") for c in gc)
    _dyn = "DATA MISSING"   # impulse sparkover absent in the export for every GDT part
    data_table(story, "9.11", "Release-Readiness Matrix",
        f"Recommended: {rec.get('recommend','MOV-only')}. Final status is PASS only when the required column "
        "clears end-to-end.",
        ["Check", "MOV-only", "MOV + GDT"],
        [["Continuous voltage", f"MCOV {_f(mc.get('class'),0)} Vac", f"MCOV + GDT no-fire {_mark(_gdt_nofire)}"],
         ["Clamp / let-through", _mark(_clamp_ok), f"MOV clamp {_mark(_clamp_ok)} + GDT dyn.spark {_dyn}"],
         ["Energy / current", _mark(_energy_ok), f"{_mark(_energy_ok)} + GDT surge {_mark(_gdt_nofire)}"],
         ["Fail-short safety", _mark(_fz_ok), f"MOV {_mark(_fz_ok)} + GDT follow/fail-short {_mark(fs.get('ok'))}"],
         ["Layout", "low-inductance L-N loop", "low-inductance + safety-spaced PE path"],
         ["Final status", mov_verdict, ("REQUIRED" if rec.get("required") else "OPTIONAL") + " — see checks"]],
        col_widths=[CW*0.26, CW*0.34, CW*0.40], ch=CH)
    annotation(story, "SIGN-OFF",
        "Chapter 9 is RELEASE-READY only when every cell in the required column is PASS. DATA MISSING cells "
        "(e.g. GDT dynamic sparkover, MOV clamp Vc@In) must be filled from the datasheet before "
        "certification — they are not passes.", CH)


    # Certification record — folded in after the release matrix (M3). It now runs inside
    # _build_gdt_section rather than build_mov_story, so re-bind the names it uses from mov_out.
    tg = mo.get("targets") or []
    ov = mo.get("overshoot") or {}
    lvl = (mo.get("spec") or {}).get("level")
    crit = (mo.get("criterion") or {}).get("name", "A")
    _rcd = mo.get("selected_recalc")
    # ── 9.11.1 certification record ──
    sub_h(story, "9.11.1", "Compliance Summary (Certification Record)", CH)
    worst = min(tg, key=lambda t: t["device_gate"] - t["vc"]) if tg else None
    verdict = "PASS" if all(t["coord"] != "FAIL" for t in tg) and tg else "REVIEW"
    _en_cell = ("&#8212;" if en.get("ok") is None else
                (f"PASS ({_f(en['e_surge_J'],1)}/{_f(en['e_allow_J'],0)} J)" if en.get("ok")
                 else f"OVER ({_f(en['e_surge_J'],1)}/{_f(en['e_allow_J'],0)} J)"))
    _fz_cell = ("DATA MISSING" if fz.get("ok") is None else ("cleared by fuse/TMOV" if fz.get("ok") else "NOT PROVEN"))
    data_table(story, "9.11.1", "Surge-Immunity Compliance Record",
        "The traceable record for the technical construction file.",
        ["Item", "Declared / computed"],
        [["Standard", "IEC/EN 61000-4-5 (combination wave)"],
         ["Test level", str(lvl)],
         ["Performance criterion", crit],
         ["MCOV class", f"{_f(mc['class'],0)} V<sub>ac</sub>"],
         ["Worst-case let-through", (f"{_f(worst['vc'],0)} V at {worst['path']}" if worst else "&#8212;")],
         ["+ layout overshoot", (f"{_f(ov['v_overshoot'],1)} V &#8658; V<sub>c,eff</sub> {_f(ov['vc_effective'],0)} V" if ov else "&#8212;")],
         ["Device gate", (f"{_f(worst['device_gate'],0)} V" if worst else "&#8212;")],
         ["Energy survival", _en_cell],
         ["Fuse / fail-short coordination", _fz_cell],
         ["Coordination verdict", verdict]],
        col_widths=[CW*0.42, CW*0.58], ch=CH)



# ══════════════════════════════════════════════════════════════════════════════
def _doc(target):
    from reportlab.platypus import SimpleDocTemplate
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    return SimpleDocTemplate(target, pagesize=A4, leftMargin=20*mm, rightMargin=20*mm,
                             topMargin=18*mm, bottomMargin=18*mm, title="Input Protection")


def build_inputprotection_report(design, cap=None, mosfet=None, ntc_opts=None, mov_opts=None) -> bytes:
    """Standalone Chapters 8 (NTC) + 9 (MOV) PDF, merged after Chapter 7."""
    from reportlab.platypus import PageBreak
    story = []
    build_ntc_story(story, design, cap, ntc_opts)
    build_mov_story(story, design, mosfet, cap, mov_opts)
    while story and isinstance(story[0], PageBreak):
        story.pop(0)
    buf = io.BytesIO()
    _doc(buf).build(story)
    return buf.getvalue()

    # certification record — folded in after the release matrix (M3). Re-bind the names it
    # uses from mov_out, since it now lives in _build_gdt_section rather than build_mov_story.
    tg = mo.get("targets") or []
    ov = mo.get("overshoot") or {}