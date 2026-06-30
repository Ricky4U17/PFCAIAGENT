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
    chapter_splash, step_h, body, eq_box, data_table, annotation, CW,
)
from app.mode_b.inputprotection.adapter import calculate_ntc, calculate_mov

_MU = "&#181;"; _DEG = "&#176;"; _OHM = "&#937;"


def _f(x, n=2):
    try:
        return f"{float(x):.{n}f}"
    except Exception:
        return "&#8212;"


# ══════════════════════════════════════════════════════════════════════════════
#  Chapter 8 — NTC inrush limiter + bypass relay
# ══════════════════════════════════════════════════════════════════════════════
def build_ntc_story(story, design, cap=None, opts=None):
    CH = 8
    out = calculate_ntc(design, cap or {}, opts or {})
    s = out["spec"]; r = out["result"]; cat = out["catalog"]

    chapter_splash(story, CH, "Inrush Limiting — NTC Thermistor + Bypass Relay",
        "What series element holds the cold-start inrush below target while surviving the "
        "bulk-capacitor charge energy, and why must it be bypassed for continuous operation?",
        ["8.1 Basis — line range, bus voltage, bulk capacitance and worst-case input current",
         "8.2 Cold series resistance for the inrush target",
         "8.3 Pulse-energy survival — the real datasheet filter",
         "8.4 Continuous self-heat → why a bypass relay is mandatory",
         "8.5 Bypass relay + precharge timing",
         "8.6 Candidate screen and selection"])

    # ── 8.1 basis ──
    step_h(story, "8.1", "Design Basis (carried in)", CH)
    annotation(story, "CONCEPT",
        "The inrush element is sized from values already fixed upstream: the high-line peak sets the "
        "worst-case stress, the approved bulk capacitance (Step 15) sets the charge energy, and the "
        "worst-case input RMS current (from the shared operating grid) sets the continuous self-heat "
        "that forces a bypass. Nothing here is re-entered.", CH)
    data_table(story, "8.1", "Carried-in Operating Basis", "Sourced from the design grid and the approved capacitor.",
        ["Quantity", "Symbol", "Value"],
        [["High-line RMS", "V<sub>ac,max</sub>", f"{_f(s['vac_max'],0)} V"],
         ["High-line peak", "V<sub>in,pk</sub> = &#8730;2&#183;V<sub>ac,max</sub>", f"{_f(r['vin_pk_max'],1)} V"],
         ["Regulated bus", "V<sub>bus</sub>", f"{_f(s['vout_bus'],0)} V"],
         ["Bulk capacitance (Step 15)", "C<sub>out</sub>", f"{_f(s['cout']*1e6,0)} {_MU}F"],
         ["Worst-case input RMS (grid)", "I<sub>in,rms</sub>", f"{_f(r['i_rms_worst'],2)} A"]],
        col_widths=[CW*0.46, CW*0.30, CW*0.24], ch=CH)

    # ── 8.2 cold resistance ──
    step_h(story, "8.2", "Cold Series Resistance for the Inrush Target", CH)
    body(story,
        "Cold, the whole line peak appears across the series resistance at switch-on, so the minimum "
        "total cold resistance to hold the peak inrush below target is V<sub>in,pk</sub>/I<sub>target</sub>. "
        "Subtracting the known loop parasitics leaves the resistance the NTC alone must provide:", CH)
    eq_box(story, [r"R_{total,cold}=\dfrac{V_{in,pk}}{I_{target}}",
                   r"R_{25}=(R_{total,cold}-R_{parasitic})\times k_{margin}"],
           number="8.2", ch=CH)
    body(story,
        f"<b>Worked.</b> The high-line peak is V<sub>in,pk</sub> = &#8730;2&#183;{_f(s['vac_max'],0)} = "
        f"{_f(r['vin_pk_max'],1)} V. To hold the cold inrush at the {_f(s['i_inrush_target'],0)} A target the "
        f"total cold resistance must be at least {_f(r['vin_pk_max'],1)} V / {_f(s['i_inrush_target'],0)} A = "
        f"{_f(r['r_total_min'],3)} {_OHM}. Subtracting the known loop parasitics ({_f(r['r_parasitic'],3)} "
        f"{_OHM}: line + EMI + ESR + bridge) leaves the NTC-alone requirement R<sub>25</sub> &#8805; "
        f"{_f(r['r25_required'],3)} {_OHM}; applying the &#215;{_f(s['r25_margin'],2)} margin gives the pick "
        f"<b>R<sub>25</sub> = {_f(r['r25_pick'],3)} {_OHM}</b> (choose the nearest standard value &#8805; this).", CH)
    data_table(story, "8.2b", "Inrush-Target Sweep", "Minimum total cold resistance for a range of inrush targets.",
        ["Target I (A)", "R<sub>min,total</sub> (" + _OHM + ")"],
        [[f"{_f(t,0)}", f"{_f(rr,3)}"] for t, rr in r["sweep"]],
        col_widths=[CW*0.5, CW*0.5], ch=CH)

    # ── 8.3 pulse energy ──
    step_h(story, "8.3", "Pulse-Energy Survival", CH)
    body(story,
        "On every cold start the series element absorbs the bulk-capacitor charge energy. This pulse "
        "rating — not the steady current — is the governing datasheet filter. Vendors quote it either in "
        "joules or as a &#8220;maximum switchable capacitance&#8221; at a reference voltage; the two are "
        "interchangeable through E = &#189;CV&#178;.", CH)
    eq_box(story, [r"E_{cap}=\frac{1}{2}\,C_{out}\,V_{in,pk}^{2}",
                   r"C_{max,equiv}=\dfrac{2\,E_{pulse}}{V_{ref}^{2}}"], number="8.3", ch=CH)
    body(story,
        f"<b>Worked.</b> The bulk capacitor stores E<sub>cap</sub> = &#189;&#183;{_f(s['cout']*1e6,0)} {_MU}F&#183;"
        f"({_f(r['vin_pk_max'],1)} V)&#178; = <b>{_f(r['e_cap'],1)} J</b> at the high-line peak. With the "
        f"&#215;{_f(s['energy_margin'],2)} survival margin the part must be rated &#8805; "
        f"{_f(r['e_pulse_required'],1)} J — or, equivalently, a maximum switchable capacitance "
        f"&#8805; 2&#183;{_f(r['e_pulse_required'],1)} J / ({_f(s['vref_pulse'],0)} V)&#178; = "
        f"{_f(r['cmax_equiv_required']*1e6,0)} {_MU}F at the {_f(s['vref_pulse'],0)} V vendor reference. "
        f"Accept a part that meets <i>either</i> figure.", CH)

    # ── 8.4 self-heat / bypass ──
    step_h(story, "8.4", "Continuous Self-Heat → Why a Bypass Relay", CH)
    body(story,
        "Left in circuit, the warm NTC dissipates I<sub>in,rms</sub><sup>2</sup>&#183;R<sub>hot</sub> "
        "continuously — tens of watts at kW class, with body temperatures that can approach 250&#176;C. "
        "It is therefore bypassed by a relay after precharge, so it conducts only during the startup "
        "pulse. Consequently its steady-state contribution to the efficiency budget is &#8776; 0 W.", CH)
    data_table(story, "8.4", "Continuous Self-Heat if NOT Bypassed",
        f"At the worst-case input RMS current {_f(r['i_rms_worst'],2)} A.",
        ["R<sub>hot</sub> (" + _OHM + ")", "P<sub>loss</sub> = I<sup>2</sup>R (W)"],
        [[f"{_f(rh,2)}", f"{_f(pl,1)}"] for rh, pl in r["loss_rows"]],
        col_widths=[CW*0.5, CW*0.5], ch=CH)

    # ── 8.5 relay/timing ──
    step_h(story, "8.5", "Bypass Relay + Precharge Timing", CH)
    body(story,
        "<b>Model.</b> After the bulk capacitor has precharged through the NTC, a relay shorts the NTC out so "
        "it carries current only during the startup pulse. The bus settles with the RC time constant "
        "&#964; = R<sub>25</sub>&#183;C<sub>out</sub>; the bypass is closed after a few time constants.", CH)
    eq_box(story, [r"\tau=R_{25}\,C_{out},\qquad t_{bypass}=N_{\tau}\,\tau"], number="8.5", ch=CH)
    body(story,
        f"<b>Worked.</b> &#964; = {_f(r['r25_pick'],2)} {_OHM} &#215; {_f(s['cout']*1e6,0)} {_MU}F = "
        f"{_f(r['tau']*1e3,1)} ms, so closing the bypass after {_f(s['tau_multiple'],0)}&#183;&#964; = "
        f"<b>{_f(r['t_bypass']*1e3,0)} ms</b> lets the bus settle first. The relay contacts must be rated "
        f"&#8805; {_f(r['relay_contact_v'],0)} V (margin over the {_f(s['vout_bus'],0)} V bus) and carry the "
        f"continuous input current &#8805; {_f(r['relay_contact_a'],1)} A (add AC1/DC headroom).", CH)
    annotation(story, "NOTE",
        "Hot-restart caution: a quick OFF/ON leaves the NTC warm (lower R) → higher inrush than the cold "
        "calculation. Add a minimum re-enable cool-down, or verify warm-NTC inrush against the fuse and "
        "capacitor I&#178;t.", CH)

    # ── 8.6 candidates ──
    step_h(story, "8.6", "Candidate Screen", CH)
    data_table(story, "8.6", "Catalog Screen",
        f"Accept if R25 &#8805; {_f(r['r25_pick'],2)} {_OHM} and pulse rating &#8805; {_f(r['e_pulse_required'],0)} J "
        "(or the equivalent max-C). Representative values — confirm on the live datasheet.",
        ["Verdict", "Candidate part", "Notes"],
        [["PASS" if c["ok"] else "FAIL", c["name"], "; ".join(c["reasons"])[:120]] for c in cat] or [["—", "no catalog", "—"]],
        col_widths=[CW*0.12, CW*0.40, CW*0.48], ch=CH)


# ══════════════════════════════════════════════════════════════════════════════
#  Chapter 9 — MOV surge protection & compliance (IEC/EN 61000-4-5)
# ══════════════════════════════════════════════════════════════════════════════
def build_mov_story(story, design, mosfet=None, cap=None, opts=None):
    CH = 9
    out = calculate_mov(design, mosfet or {}, cap or {}, opts or {})
    s = out["spec"]; st = out["stress"]; mc = out["mcov"]; cr = out["criterion"]
    tg = out["targets"]; cat = out["catalog"]
    lvl = s.get("level"); crit = cr["name"]

    chapter_splash(story, CH, "Surge Protection & Compliance (MOV, IEC/EN 61000-4-5)",
        "Does the metal-oxide varistor clamp the combination-wave surge below the downstream "
        "withstand while surviving the repetitive pulse current — and is the result traceable to the "
        "declared test level and performance criterion for certification?",
        ["9.1 Compliance basis — LEVEL (stress), CRITERION (acceptance), LINE (MCOV) are orthogonal",
         "9.2 Surge stress per coupling mode",
         "9.3 Continuous voltage (MCOV) — line-driven, level/criterion-independent",
         "9.4 Clamp / coordination — load-line let-through vs the device gate",
         "9.5 Performance criterion — what it changes",
         "9.6 Candidate screen, placement & coordination",
         "9.7 Compliance summary (certification record)"])

    # ── 9.1 ──
    step_h(story, "9.1", "Compliance Basis", CH)
    annotation(story, "CONCEPT",
        "Per IEC/EN 61000-4-5 the surge is a combination wave applied through defined source impedances "
        "(2 &#937; differential; +10 &#937; CDN for line-to-earth). Three orthogonal inputs drive every "
        "number: the TEST LEVEL sizes the stress (open-circuit voltages → short-circuit currents), the "
        "PERFORMANCE CRITERION sizes the acceptance bar (A ride-through, B self-recover, C operator "
        "reset), and the continuous LINE sets the MCOV. The declared level + criterion are the "
        "certification record.", CH)
    data_table(story, "9.1", "Declared Compliance Inputs", "These choices are the certification basis.",
        ["Input", "Value", "Governs"],
        [["Test level (61000-4-5)", str(lvl), "surge stress (currents/energies)"],
         ["Performance criterion", crit + (" — ride-through" if cr["ride_through"] else " — survive/reset"), "acceptance bar / device gate"],
         ["Continuous line", f"{_f(s['vac_max'],0)} V<sub>ac</sub> max", "MCOV (invariant to level/criterion)"],
         ["Downstream device V<sub>ds</sub>", f"{_f(s['device_vds'],0)} V (from selected MOSFET)", "coordination gate"]],
        col_widths=[CW*0.34, CW*0.40, CW*0.26], ch=CH)

    # ── 9.2 stress ──
    step_h(story, "9.2", "Surge Stress per Coupling Mode", CH)
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

    # ── 9.3 mcov ──
    step_h(story, "9.3", "Continuous Voltage (MCOV)", CH)
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

    # ── 9.4 clamp ──
    step_h(story, "9.4", "Clamp / Coordination (Load-Line Let-Through)", CH)
    body(story,
        "<b>Model.</b> The let-through (clamp) voltage is the operating point where the varistor's highly "
        "non-linear V-I curve V = V<sub>1mA</sub>(I/1mA)<sup>1/&#945;</sup> meets the surge source load "
        "line V = V<sub>drive</sub> &#8722; I&#183;Z. We solve that intersection rather than reading a "
        "fixed datasheet clamp, because the actual clamp depends on the surge current the source can push. "
        "The surge rides on the line peak (phase superposition), so V<sub>drive</sub> includes the line "
        "peak. The clamp must stay under the criterion-set device gate.", CH)
    eq_box(story, [r"V=V_{1mA}\left(\dfrac{I}{1mA}\right)^{1/\alpha}=V_{drive}-I\,Z"], number="9.4", ch=CH)
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
    data_table(story, "9.4", "Per-Path Clamp & Coordination", "Let-through vs the device gate at each path.",
        ["Path", "V<sub>drive</sub> (V)", "I<sub>op</sub> (A)", "Clamp V<sub>c</sub> (V)",
         "I<sub>max</sub> req (A)", "Gate (V)", "Verdict"],
        [[t["path"], f"{_f(t['v_drive'],0)}", f"{_f(t['i_op'],0)}", f"{_f(t['vc'],0)}",
          f"{_f(t['imax_required'],0)}", f"{_f(t['device_gate'],0)}", t["coord"]] for t in tg]
          or [["&#8212;", "", "", "", "", "", ""]],
        col_widths=[CW*0.26, CW*0.13, CW*0.11, CW*0.14, CW*0.14, CW*0.11, CW*0.11], ch=CH)

    # ── 9.5 criterion ──
    step_h(story, "9.5", "Performance Criterion — What It Changes", CH)
    annotation(story, "THEORY",
        f"Criterion {crit}: ride-through = {cr['ride_through']}; the device gate is "
        + ("the transient abs-max (survival)." if cr["gate_uses_absmax"]
           else f"V<sub>ds</sub> &#8722; {_f(cr['dev_margin_V'],0)} V (protective margin).")
        + " Under A, a clamp above the gate is a FAIL — the bus must keep regulating; under B/C a clamp "
          "above V<sub>ds</sub> but below abs-max is acceptable (the unit may dip/reset). The criterion "
          "changes the gate and verdict wording, not the surge currents or energies.", CH)

    # ── 9.6 candidates ──
    step_h(story, "9.6", "Candidate Screen, Placement & Coordination", CH)
    data_table(story, "9.6", "Catalog Screen (governing path)",
        f"Criterion {crit}. Representative values — verify the V<sub>c</sub>-vs-I curve and the 10-pulse "
        "repetitive derating on the live datasheet.",
        ["Verdict", "Candidate part", "Notes"],
        [["PASS" if c["ok"] else "FAIL", c["name"], "; ".join(c["reasons"])[:120]] for c in cat] or [["—", "no catalog", "—"]],
        col_widths=[CW*0.12, CW*0.42, CW*0.46], ch=CH)
    annotation(story, "NOTE",
        "Placement: one differential MOV across L-N at the AC inlet after the fuse; common-mode MOVs "
        "L-PE and N-PE (watch leakage & creepage). Keep leads short/low-inductance (overshoot on the "
        "1.2 &#181;s edge). Pair with an upstream fuse + thermal protection (or a TMOV).", CH)

    # ── 9.7 compliance summary ──
    step_h(story, "9.7", "Compliance Summary (Certification Record)", CH)
    worst = min(tg, key=lambda t: t["device_gate"] - t["vc"]) if tg else None
    verdict = "PASS" if all(t["coord"] != "FAIL" for t in tg) and tg else "REVIEW"
    data_table(story, "9.7", "Surge-Immunity Compliance Record",
        "The traceable record for the technical construction file.",
        ["Item", "Declared / computed"],
        [["Standard", "IEC/EN 61000-4-5 (combination wave)"],
         ["Test level", str(lvl)],
         ["Performance criterion", crit],
         ["MCOV class", f"{_f(mc['class'],0)} V<sub>ac</sub>"],
         ["Worst-case let-through", (f"{_f(worst['vc'],0)} V at {worst['path']}" if worst else "&#8212;")],
         ["Device gate", (f"{_f(worst['device_gate'],0)} V" if worst else "&#8212;")],
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
