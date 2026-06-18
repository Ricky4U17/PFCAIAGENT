"""
app/mode_b/appendices.py — Appendices A–E of the control-loop design report.

Reproduces the reference document's appendices word-for-word:
  A — Derivations of Key Transfer Functions (incl. the thesis-level A.3–A.7)
  B — Bill of Materials (Control Components)
  C — Bench Verification and Test Plan
  D — References and Further Reading
  E — Equation Quick-Reference Card

These are reference / derivation sections: prose is reproduced verbatim and every
equation is rendered as proper mathtext. Stated example constants are reproduced as
the document gives them (the live design values are computed in Steps 1–14).
"""
from __future__ import annotations
from app.mode_b.doc_report_builder import (
    step_h, sub_h, body, eq_box, data_table, annotation, CW,
)

CH = 6


def build_appendices(story):
    _appendix_a(story)
    _appendix_b(story)
    _appendix_c(story)
    _appendix_d(story)
    _appendix_e(story)


# ════════════════════════════ Appendix A ════════════════════════════════════
def _appendix_a(story):
    step_h(story, "Appendix A", "Derivations of Key Transfer Functions", CH)
    body(story,
        "This appendix derives, from the averaged converter model, the two transfer functions the "
        "main report quotes: the boost small-signal plant (with its right-half-plane zero) and the "
        "OTA Type-III compensator. The aim is that a reader can reconstruct every plant and "
        "compensator expression used in Steps 10 and 11 without consulting the source application "
        "notes.", CH)

    sub_h(story, "A.1", "Boost Power Stage — Plant and the RHP Zero", CH)
    body(story,
        "Averaging the boost converter over a switching period and perturbing about the operating "
        "point (duty D, complement D′ = 1−D = V<sub>IN,pk</sub>/V<sub>OUT</sub>) gives the standard "
        "CCM control-to-output relationship. The duty-to-output voltage transfer function carries one "
        "right-half-plane zero, one left-half-plane (ESR) zero and a complex pole pair:", CH)
    eq_box(story, [r"G_{vd}(s)=\dfrac{V_{OUT}}{D'^2}\times"
                   r"\dfrac{(1+s/\omega_{zESR})(1-s/\omega_{RHP})}{1+s/(\omega_0 Q)+s^2/\omega_0^2}"], ch=CH)
    body(story, "The right-half-plane zero, the resonance and the quality factor evaluate to:", CH)
    eq_box(story, [r"\omega_{RHP}=\dfrac{R_{LOAD}\,D'^2}{L_{eq}}\,,\quad"
                   r"\omega_0=\dfrac{D'}{\sqrt{L_{eq}C_O}}\,,\quad"
                   r"Q=D'\,R_{LOAD}\sqrt{\dfrac{C_O}{L_{eq}}}"], ch=CH)
    annotation(story, "THEORY",
        "The minus sign in (1 − s/ω<sub>RHP</sub>) is the right-half-plane zero. Physically it is the "
        "boost converter's inability to source extra output current without first storing more "
        "inductor energy: raising the duty briefly steals charge from the output. It adds "
        "+20 dB/decade of gain but −90° of phase, so it can only be lived with, never compensated — "
        "hence the bandwidth ceiling.", CH)
    annotation(story, "INSIGHT",
        "For the two interleaved phases the effective inductance is L<sub>eq</sub> = L/2, so "
        "ω<sub>RHP</sub> is twice what a single phase would give. This is the quantitative reason the "
        "voltage loop in Step 11 can be placed where it is: interleaving pushes the RHP-zero ceiling "
        "higher.", CH)
    body(story,
        "For the inner current loop the relevant plant is the duty-to-inductor-current transfer "
        "function G<sub>id</sub>(s); including the winding resistance r<sub>L</sub> damps the "
        "resonance to the finite Q used in Step 10 (the lossless model would give Q → ∞). Its "
        "denominator is the same complex pair; its numerator places a low-frequency zero from the "
        "output network.", CH)

    sub_h(story, "A.2", "OTA Type-III Compensator", CH)
    body(story,
        "The voltage compensator is built around the FAN9672 transconductance amplifier (output "
        "current g<sub>m</sub>·v<sub>in</sub> driving an impedance network). With the network of "
        "Figure 14A — R2 in series with C1, C3 in parallel, and the R3–C2 branch — the "
        "voltage-error-to-output transfer function has an integrator (pole at the origin), two zeros "
        "and two further poles:", CH)
    eq_box(story, [r"H_{OTA}(s)=\dfrac{g_m}{C_1+C_3}\times"
                   r"\dfrac{(1+sR_2C_1)(1+s(R_1+R_3)C_2)}"
                   r"{s\,(1+sR_2\,C_1C_3/(C_1+C_3))(1+sR_3C_2)}"], ch=CH)
    body(story, "Matching this to the canonical Type-III form gives the pole/zero placement used in "
        "the design:", CH)
    data_table(story, "A.2", "Type-III Pole/Zero Placement",
        "Canonical Type-III singularities and their design values.",
        ["Singularity", "Expression", "Design value"],
        [["Integrator pole", "at origin", "—"],
         ["Zero f_z1", "1 / (2π R2 C1)", "3 Hz"],
         ["Zero f_z2", "1 / (2π (R1+R3) C2)", "12 Hz"],
         ["Pole f_p1", "(C1+C3) / (2π R2 C1 C3)", "50 Hz"],
         ["Pole f_p2", "1 / (2π R3 C2)", "17 Hz"]],
        col_widths=[CW*0.26, CW*0.44, CW*0.30], ch=CH)
    annotation(story, "CONCEPT",
        "A Type-III compensator places its two zeros below crossover to add up to +90° of phase boost "
        "right where the loop crosses 0 dB, then uses its two poles to restore the roll-off "
        "afterwards. That phase boost is what lets a 17 Hz loop still achieve >80° phase margin "
        "despite the integrator's −90° and the plant's lag.", CH)

    sub_h(story, "A.3", "Thesis-Level Derivation — Scope and Method", CH)
    body(story,
        "Sections A.3 through A.6 reproduce, in full, the thesis-level derivation of the inner current "
        "loop and outer voltage loop on which Steps 10 and 11 and the summary derivations of A.1–A.2 "
        "are based. They are included so that the report is self-contained: every plant, compensator "
        "and loop-gain expression used in the main body can be reconstructed here from the averaged "
        "converter model, with no model terms discarded.", CH)
    body(story,
        "The guiding principle is that a transfer function cannot be obtained without a modelling "
        "basis. The phrase “no assumption and no approximation” is therefore interpreted as follows: "
        "after selecting the CCM averaged boost model and applying first-order small-signal "
        "linearization, no model terms are dropped. The derivations retain the inductor DCR "
        "r<sub>L</sub>, the capacitor ESR r<sub>C</sub>, the finite load resistance R<sub>LOAD</sub>, "
        "the duty-dependent terms, the current-sense filtering, the closed-current-loop tracking term, "
        "the right-half-plane (RHP) zero and the ESR zero. Numerical results are rounded only for "
        "presentation.", CH)
    body(story, "The two final loop gains derived below are", CH)
    eq_box(story, [r"T_i(s)=G_{id}(s)\,\dfrac{R_{CS}}{V_{RAMP}}\,H_{CS}(s)\,G_{mi}(s)",
                   r"T_v(s)=K_{MAX}\dfrac{I_{OUT}}{5}\dfrac{V_{FBPFC}}{V_{OUT}}"
                   r"\dfrac{T_i(s)/N_{CH}}{1+T_i(s)/N_{CH}}"
                   r"\dfrac{(1+sC_O r_C)(1-s/\omega_{RHP})}{C_O s+2/R_{LOAD}}\,G_{MV}Z_{comp}(s)"], ch=CH)

    sub_h(story, "A.4", "Average-Current-Mode PFC Control Architecture", CH)
    body(story, "<b>A.4.1  Nested-loop structure</b>", CH)
    body(story,
        "Average-current-mode PFC is a nested two-loop system. The inner current loop is fast and "
        "forces the boost inductor current to track a current command proportional to the rectified "
        "input voltage. The outer voltage loop is slow and adjusts only the current-command amplitude "
        "to regulate the DC bus.", CH)
    body(story, "For each phase, the current path is", CH)
    eq_box(story, [r"\hat d(s)\rightarrow\hat i_L(s)\rightarrow\hat v_{CS}(s)\rightarrow"
                   r"\hat v_{IEA}(s)\rightarrow\hat d(s)"], ch=CH)
    body(story, "For the voltage loop, the path is", CH)
    eq_box(story, [r"\hat v_o(s)\rightarrow\hat v_{FB}(s)\rightarrow\hat v_{VEA}(s)\rightarrow"
                   r"\hat i_{cmd}(s)\rightarrow\hat p_{in}(s)\rightarrow\hat v_o(s)"], ch=CH)
    body(story, "The loop separation is intentional:", CH)
    eq_box(story, [r"f_{cv}\ll 2f_{line}\ll f_{ci}\ll f_{sw}"], ch=CH)
    body(story, "For this design,", CH)
    eq_box(story, [r"17\ \mathrm{Hz}\ll 120\ \mathrm{Hz}\ll 8\ \mathrm{kHz}\ll 70\ \mathrm{kHz}"], ch=CH)
    body(story, "<b>A.4.2  Why the current loop is closed first</b>", CH)
    body(story,
        "The current loop must be designed first because the voltage loop commands current. In the "
        "voltage-loop equation, the inner loop appears as the tracking term", CH)
    eq_box(story, [r"G_{i,cl}(s)=\dfrac{T_i(s)/N_{CH}}{1+T_i(s)/N_{CH}}"], ch=CH)
    body(story,
        "At frequencies much lower than the current-loop crossover, this term is close to unity. It "
        "is nevertheless retained in the final equation because the intent is to keep the full loop "
        "structure and avoid replacing a dynamic block by a constant.", CH)

    sub_h(story, "A.5", "Mathematical Basis: Averaging, Perturbation, and Laplace Transform", CH)
    body(story, "<b>A.5.1  Averaged large-signal modelling</b>", CH)
    body(story,
        "For a CCM boost phase, the switch ON and OFF intervals are duty-cycle averaged over one "
        "switching period. The averaged equations are continuous-time equations in the slow variables "
        "i<sub>L</sub>, v<sub>C</sub> and v<sub>o</sub>. The selected model retains the inductor DCR "
        "r<sub>L</sub>, the output-capacitor ESR r<sub>C</sub>, the finite load resistance "
        "R = R<sub>LOAD</sub>, the duty D and its complement D′ = 1−D, the output-capacitor dynamics, "
        "and the boost output-current coupling through D′i<sub>L</sub>.", CH)
    body(story, "<b>A.5.2  Small-signal perturbation</b>", CH)
    body(story, "Each large-signal variable is written as a steady-state value plus a small "
        "perturbation:", CH)
    eq_box(story, [r"i_L=I_L+\hat i_L,\quad v_C=V_C+\hat v_C,\quad v_o=V_O+\hat v_o,\quad"
                   r"d=D+\hat d,\quad D'=1-D-\hat d"], ch=CH)
    body(story, "The product D′i<sub>L</sub> becomes", CH)
    eq_box(story, [r"D'i_L=(1-D-\hat d)(I_L+\hat i_L)"
                   r"=(1-D)I_L+(1-D)\hat i_L-I_L\hat d-\hat d\,\hat i_L"], ch=CH)
    body(story, "The first-order perturbation is therefore", CH)
    eq_box(story, [r"\widehat{D'i_L}=D'\hat i_L-I_L\hat d"], ch=CH)
    body(story,
        "The term d<super>^</super> i<super>^</super><sub>L</sub> is a second-order perturbation. Removing "
        "second-order perturbation products is not an optional engineering approximation; it is the "
        "definition of a first-order small-signal transfer function.", CH)
    body(story, "<b>A.5.3  Laplace transform convention</b>", CH)
    body(story, "All perturbation variables are transformed using zero initial conditions. Therefore", CH)
    eq_box(story, [r"\mathcal{L}\left\{\dfrac{d\hat x}{dt}\right\}=s\,\hat x(s)"], ch=CH)
    body(story, "For readability, hats are kept on small-signal variables but the argument s is "
        "sometimes omitted inside longer derivations.", CH)

    sub_h(story, "A.6", "Inner Current-Loop Theory Derivation", CH)
    body(story, "<b>A.6.1  Definition of the current-loop plant</b>", CH)
    body(story, "The per-phase duty-to-inductor-current plant is", CH)
    eq_box(story, [r"G_{id}(s)=\dfrac{\hat i_L(s)}{\hat d(s)}"], ch=CH)
    body(story, "The current loop also contains current sensing, a current-sense filter, current OTA "
        "compensation and PWM ramp gain. The final current-loop gain is", CH)
    eq_box(story, [r"T_i(s)=G_{id}(s)\,R_{CS}\,H_{CS}(s)\,G_{mi}(s)\,F_m,\qquad F_m=\dfrac{1}{V_{RAMP}}"], ch=CH)
    body(story, "Rearranging,", CH)
    eq_box(story, [r"T_i(s)=G_{id}(s)\,\dfrac{R_{CS}}{V_{RAMP}}\,H_{CS}(s)\,G_{mi}(s)"], ch=CH)
    body(story, "<b>A.6.2  Large-signal averaged boost equations</b>", CH)
    body(story, "For one boost phase,", CH)
    eq_box(story, [r"L\dfrac{di_L}{dt}=v_{in}-r_L i_L-D'v_o"], ch=CH)
    body(story, "The output current delivered by the boost diode path is", CH)
    eq_box(story, [r"i_d=D'i_L"], ch=CH)
    body(story, "Including capacitor ESR, the capacitor state equation can be written as", CH)
    eq_box(story, [r"C(R+r_C)\dfrac{dv_C}{dt}=R\,D'i_L-v_C"], ch=CH)
    body(story, "The terminal output voltage is", CH)
    eq_box(story, [r"v_o=\dfrac{R}{R+r_C}v_C+\dfrac{R\,r_C}{R+r_C}D'i_L"], ch=CH)
    body(story, "These four equations define the full averaged model used for the inner-loop plant "
        "derivation.", CH)
    body(story, "<b>A.6.3  Small-signal capacitor equation</b>", CH)
    body(story, "Applying the first-order perturbation to the capacitor state equation,", CH)
    eq_box(story, [r"C(R+r_C)\dfrac{d\hat v_C}{dt}=R(D'\hat i_L-I_L\hat d)-\hat v_C"], ch=CH)
    body(story, "Taking the Laplace transform,", CH)
    eq_box(story, [r"C(R+r_C)s\,\hat v_C=R\,D'\hat i_L-R\,I_L\hat d-\hat v_C"], ch=CH)
    body(story, "Collecting v<super>^</super><sub>C</sub> terms,", CH)
    eq_box(story, [r"(1+sC(R+r_C))\hat v_C=R(D'\hat i_L-I_L\hat d)"], ch=CH)
    body(story, "Therefore", CH)
    eq_box(story, [r"\hat v_C(s)=\dfrac{R(D'\hat i_L-I_L\hat d)}{1+sC(R+r_C)}"], ch=CH)
    body(story, "<b>A.6.4  Small-signal output-voltage equation</b>", CH)
    body(story, "From the terminal-voltage relation,", CH)
    eq_box(story, [r"\hat v_o=\dfrac{R}{R+r_C}\hat v_C+\dfrac{R\,r_C}{R+r_C}(D'\hat i_L-I_L\hat d)"], ch=CH)
    body(story, "Substituting the capacitor result,", CH)
    eq_box(story, [r"\hat v_o=\dfrac{R}{R+r_C}\left(\dfrac{R}{1+sC(R+r_C)}+r_C\right)(D'\hat i_L-I_L\hat d)"], ch=CH)
    body(story, "Putting the bracket over a common denominator,", CH)
    eq_box(story, [r"\dfrac{R}{1+sC(R+r_C)}+r_C=\dfrac{R+r_C+sC r_C(R+r_C)}{1+sC(R+r_C)}"], ch=CH)
    body(story, "Since", CH)
    eq_box(story, [r"R+r_C+sC r_C(R+r_C)=(R+r_C)(1+sC r_C)"], ch=CH)
    body(story, "then", CH)
    eq_box(story, [r"\hat v_o=R\,\dfrac{1+sC r_C}{1+sC(R+r_C)}(D'\hat i_L-I_L\hat d)"], ch=CH)
    body(story, "<b>A.6.5  Small-signal inductor equation and control-to-current plant</b>", CH)
    body(story, "For the control-to-current transfer function, set the input-voltage perturbation to "
        "zero, v<super>^</super><sub>in</sub> = 0. From the inductor equation,", CH)
    eq_box(story, [r"L\dfrac{d\hat i_L}{dt}=-r_L\hat i_L-D'\hat v_o+V_O\hat d"], ch=CH)
    body(story, "The Laplace transform gives", CH)
    eq_box(story, [r"(Ls+r_L)\hat i_L+D'\hat v_o=V_O\hat d"], ch=CH)
    body(story, "Substituting the output-voltage result,", CH)
    eq_box(story, [r"(Ls+r_L)\hat i_L+D'R\,\dfrac{1+sC r_C}{1+sC(R+r_C)}(D'\hat i_L-I_L\hat d)=V_O\hat d"], ch=CH)
    body(story, "Multiplying through by 1+sC(R+r<sub>C</sub>),", CH)
    eq_box(story, [r"[(Ls+r_L)(1+sC(R+r_C))+D'^2 R(1+sC r_C)]\hat i_L"
                   r"=[V_O(1+sC(R+r_C))+D'R I_L(1+sC r_C)]\hat d"], ch=CH)
    body(story, "Thus the exact small-signal duty-to-current plant before steady-state substitution "
        "is", CH)
    eq_box(story, [r"G_{id}(s)=\dfrac{V_O(1+sC(R+r_C))+D'R I_L(1+sC r_C)}"
                   r"{(Ls+r_L)(1+sC(R+r_C))+D'^2 R(1+sC r_C)}"], ch=CH)
    body(story, "<b>A.6.6  Steady-state substitutions and numerator zero</b>", CH)
    body(story, "At the operating point,", CH)
    eq_box(story, [r"I_O=\dfrac{V_O}{R},\quad D'I_L=I_O=\dfrac{V_O}{R}"], ch=CH)
    body(story, "Therefore", CH)
    eq_box(story, [r"D'R I_L=V_O"], ch=CH)
    body(story, "Substituting into the numerator,", CH)
    eq_box(story, [r"N(s)=V_O(1+sC(R+r_C))+V_O(1+sC r_C)=V_O(2+sC(R+2r_C))"], ch=CH)
    body(story, "Now write", CH)
    eq_box(story, [r"2+sC(R+2r_C)=C(R+2r_C)\left(s+\dfrac{2}{C(R+2r_C)}\right)"], ch=CH)
    body(story, "Since", CH)
    eq_box(story, [r"\dfrac{2}{C(R+2r_C)}=\dfrac{1}{C(R/2+r_C)}"], ch=CH)
    body(story, "the numerator zero is", CH)
    eq_box(story, [r"\omega_z=\dfrac{1}{C(R/2+r_C)}"], ch=CH)
    body(story, "This zero is not the capacitor ESR zero 1/(C r<sub>C</sub>), because it contains "
        "R/2 + r<sub>C</sub>.", CH)
    body(story, "<b>A.6.7  Denominator expansion</b>", CH)
    body(story, "The denominator is", CH)
    eq_box(story, [r"D_{den}(s)=(Ls+r_L)(1+sC(R+r_C))+D'^2 R(1+sC r_C)"], ch=CH)
    body(story, "Expanding,", CH)
    eq_box(story, [r"D_{den}(s)=Ls+r_L+s^2 LC(R+r_C)+s r_L C(R+r_C)+D'^2 R+s D'^2 R C r_C"], ch=CH)
    body(story, "Collecting powers of s,", CH)
    eq_box(story, [r"D_{den}(s)=s^2 LC(R+r_C)+s[L+r_L C(R+r_C)+D'^2 R C r_C]+(r_L+D'^2 R)"], ch=CH)
    body(story, "Dividing by LC(R+r<sub>C</sub>) gives", CH)
    eq_box(story, [r"D_{norm}(s)=s^2+a_1 s+a_0"], ch=CH)
    body(story, "where", CH)
    eq_box(story, [r"a_1=\dfrac{C(r_L(R+r_C)+R r_C(1-D)^2)+L}{LC(R+r_C)}",
                   r"a_0=\dfrac{(1-D)^2 R+r_L}{LC(R+r_C)}"], ch=CH)
    body(story, "<b>A.6.8  Final full duty-to-current plant</b>", CH)
    body(story, "Combining the normalized numerator and denominator,", CH)
    eq_box(story, [r"G_{id}(s)=\dfrac{V_{OUT}}{L}\,\dfrac{R_{LOAD}+2r_C}{R_{LOAD}+r_C}\,"
                   r"\dfrac{s+\omega_z}{s^2+a_1 s+a_0}"], ch=CH)
    body(story, "with", CH)
    eq_box(story, [r"\omega_z=\dfrac{1}{C_O(R_{LOAD}/2+r_C)}"], ch=CH)
    body(story, "The natural frequency and quality factor of the second-order denominator are", CH)
    eq_box(story, [r"\omega_0=\sqrt{a_0},\quad f_0=\dfrac{\sqrt{a_0}}{2\pi},\quad Q=\dfrac{\sqrt{a_0}}{a_1}"], ch=CH)
    body(story, "<b>A.6.9  Current-sense filter and PWM ramp gain</b>", CH)
    body(story, "The current-sense filter is", CH)
    eq_box(story, [r"H_{CS}(s)=\dfrac{1}{1+s/\omega_{RC}},\quad\omega_{RC}=\dfrac{1}{R_f C_f}"], ch=CH)
    body(story, "For R<sub>f</sub> = 2 kΩ and C<sub>f</sub> = 470 pF,", CH)
    eq_box(story, [r"f_{RC}=\dfrac{1}{2\pi R_f C_f}=169.3\ \mathrm{kHz}"], ch=CH)
    body(story, "The PWM ramp gain is", CH)
    eq_box(story, [r"F_m=\dfrac{1}{V_{RAMP}}"], ch=CH)
    body(story, "and the current-sense / ramp normalization is", CH)
    eq_box(story, [r"\dfrac{R_{CS}}{V_{RAMP}}=\dfrac{0.015}{5}=0.003"], ch=CH)
    body(story, "<b>A.6.10  Type-II current OTA compensator</b>", CH)
    body(story, "The FAN9672 current amplifier is an OTA. The transconductance amplifier converts "
        "error voltage into output current, and the external impedance Z<sub>IEA</sub>(s) converts "
        "that current into the compensation voltage:", CH)
    eq_box(story, [r"G_{mi}(s)=G_{MI}\,Z_{IEA}(s)"], ch=CH)
    body(story, "For a Type-II compensation shape,", CH)
    eq_box(story, [r"Z_{IEA}(s)=R_{IC}\,\dfrac{1+\omega_{zi}/s}{1+s/\omega_{pi}}"], ch=CH)
    body(story, "This form provides high low-frequency gain, a zero for phase boost near crossover, "
        "and a high-frequency pole for noise-gain control.", CH)
    body(story, "<b>A.6.11  Final current-loop gain</b>", CH)
    body(story, "Substituting the plant, the current-sense filter and the Type-II compensator,", CH)
    eq_box(story, [r"T_i(s)=\dfrac{V_{OUT}}{L}\dfrac{R_{LOAD}+2r_C}{R_{LOAD}+r_C}"
                   r"\dfrac{s+\omega_z}{s^2+a_1 s+a_0}\dfrac{R_{CS}}{V_{RAMP}}"
                   r"G_{MI}R_{IC}\dfrac{1+\omega_{zi}/s}{1+s/\omega_{pi}}\dfrac{1}{1+s/\omega_{RC}}"], ch=CH)

    sub_h(story, "A.7", "Outer Voltage-Loop Theory Derivation", CH)
    body(story, "<b>A.7.1  What the outer loop controls</b>", CH)
    body(story,
        "The voltage loop regulates the DC bus. In a PFC converter it does not directly command duty. "
        "Instead, it commands the amplitude of the sinusoidal current reference. The inner current "
        "loop then makes the inductor current track that reference. The final voltage-loop gain is a "
        "product of five blocks:", CH)
    eq_box(story, [r"T_v(s)=G_{MOD}\,G_{i,cl}(s)\,G_{vp}(s)\,H_v\,G_{mv}(s)"], ch=CH)
    body(story, "Each block has a separate physical origin, summarized below.", CH)
    data_table(story, "A-1", "Outer voltage-loop blocks and their physical origin",
        "The five cascaded blocks of the voltage-loop gain.",
        ["Block", "Expression", "Physical meaning"],
        [["Multiplier / gain modulator", "G_MOD", "VEA command to current-command amplitude"],
         ["Closed current-loop tracking", "G_i,cl(s)", "Accuracy of current-reference tracking"],
         ["Output plant", "G_vp(s)", "Output power / current to bus voltage"],
         ["Feedback divider", "H_v", "Output voltage to FBPFC voltage"],
         ["Voltage compensator", "G_mv(s)", "Voltage OTA and compensation network"]],
        col_widths=[CW*0.30, CW*0.20, CW*0.50], ch=CH)
    body(story, "<b>A.7.2  Energy-balance output plant</b>", CH)
    body(story, "The output capacitor stores energy", CH)
    eq_box(story, [r"E_C=\frac{1}{2}C_O V_o^2"], ch=CH)
    body(story, "The rate of change of stored energy equals input power minus load power:", CH)
    eq_box(story, [r"C_O V_o\dfrac{dV_o}{dt}=p_{in}-\dfrac{V_o^2}{R_{LOAD}}"], ch=CH)
    body(story, "Let", CH)
    eq_box(story, [r"V_o=V_{OUT}+\hat v_o,\quad p_{in}=P_{IN}+\hat p_{in}"], ch=CH)
    body(story, "At steady state,", CH)
    eq_box(story, [r"P_{IN}=\dfrac{V_{OUT}^2}{R_{LOAD}}"], ch=CH)
    body(story, "The load-power perturbation is", CH)
    eq_box(story, [r"\dfrac{V_o^2}{R_{LOAD}}=\dfrac{(V_{OUT}+\hat v_o)^2}{R_{LOAD}}"
                   r"=\dfrac{V_{OUT}^2}{R_{LOAD}}+\dfrac{2V_{OUT}}{R_{LOAD}}\hat v_o+\dfrac{\hat v_o^2}{R_{LOAD}}"], ch=CH)
    body(story, "The first-order perturbation is", CH)
    eq_box(story, [r"\hat p_{load}=\dfrac{2V_{OUT}}{R_{LOAD}}\hat v_o"], ch=CH)
    body(story, "The left-hand side becomes C<sub>O</sub>(V<sub>OUT</sub>+v<super>^</super><sub>o</sub>) "
        "dv<super>^</super><sub>o</sub>/dt, whose first-order term is", CH)
    eq_box(story, [r"C_O V_{OUT}\dfrac{d\hat v_o}{dt}"], ch=CH)
    body(story, "Therefore,", CH)
    eq_box(story, [r"C_O V_{OUT}\dfrac{d\hat v_o}{dt}=\hat p_{in}-\dfrac{2V_{OUT}}{R_{LOAD}}\hat v_o"], ch=CH)
    body(story, "Dividing by V<sub>OUT</sub>,", CH)
    eq_box(story, [r"C_O\dfrac{d\hat v_o}{dt}+\dfrac{2}{R_{LOAD}}\hat v_o=\dfrac{\hat p_{in}}{V_{OUT}}"], ch=CH)
    body(story, "The Laplace transform gives", CH)
    eq_box(story, [r"\left(C_O s+\dfrac{2}{R_{LOAD}}\right)\hat v_o(s)=\dfrac{\hat p_{in}(s)}{V_{OUT}}"], ch=CH)
    body(story, "Thus", CH)
    eq_box(story, [r"\dfrac{\hat v_o(s)}{\hat p_{in}(s)}=\dfrac{1}{V_{OUT}}\dfrac{1}{C_O s+2/R_{LOAD}}"], ch=CH)
    body(story, "If the command variable is an equivalent output-current perturbation "
        "i<super>^</super><sub>out,eq</sub> = p<super>^</super><sub>in</sub>/V<sub>OUT</sub>, then", CH)
    eq_box(story, [r"\dfrac{\hat v_o(s)}{\hat i_{out,eq}(s)}=\dfrac{1}{C_O s+2/R_{LOAD}}"], ch=CH)
    body(story, "This is why the voltage-loop denominator is C<sub>O</sub>s + 2/R<sub>LOAD</sub>, the "
        "factor of two arising from the derivative of load power with respect to voltage.", CH)
    body(story, "<b>A.7.3  Output capacitor ESR zero</b>", CH)
    body(story, "The terminal output voltage is", CH)
    eq_box(story, [r"\hat v_o=\hat v_C+r_C\hat i_C"], ch=CH)
    body(story, "With", CH)
    eq_box(story, [r"\hat i_C=C_O\dfrac{d\hat v_C}{dt}"], ch=CH)
    body(story, "the Laplace transform gives", CH)
    eq_box(story, [r"\hat v_o(s)=\hat v_C(s)+r_C C_O s\,\hat v_C(s)=\hat v_C(s)(1+sC_O r_C)"], ch=CH)
    body(story, "Therefore the output plant contains the ESR-zero factor", CH)
    eq_box(story, [r"G_{ESR}(s)=1+sC_O r_C,\quad\omega_{ESR}=\dfrac{1}{C_O r_C}"], ch=CH)
    body(story, "<b>A.7.4  Boost right-half-plane zero</b>", CH)
    body(story,
        "A CCM boost converter has non-minimum-phase output dynamics. Increasing duty reduces the "
        "instantaneous off-time D′ = 1−D and initially reduces energy delivery to the output before "
        "the inductor current rises. This creates a right-half-plane zero in the output-voltage path. "
        "For the interleaved output plant written with the effective inductance appropriate to total "
        "output energy transfer,", CH)
    eq_box(story, [r"\omega_{RHP}=\dfrac{R_{LOAD}(1-D)^2}{L_{eq}},\quad L_{eq}=\dfrac{L_\phi}{N_{CH}}"], ch=CH)
    body(story, "The RHP zero appears as", CH)
    eq_box(story, [r"1-\dfrac{s}{\omega_{RHP}}"], ch=CH)
    body(story, "The minus sign is essential: it contributes phase lag rather than phase lead.", CH)
    body(story, "<b>A.7.5  Full voltage power-stage plant</b>", CH)
    body(story, "Combining the energy-balance denominator, the ESR zero and the RHP zero,", CH)
    eq_box(story, [r"G_{vp}(s)=\dfrac{(1+sC_O r_C)(1-s/\omega_{RHP})}{C_O s+2/R_{LOAD}}"], ch=CH)
    body(story, "<b>A.7.6  Closed inner current-loop tracking</b>", CH)
    body(story, "The voltage loop commands current, but the current does not track perfectly. The "
        "closed current-loop tracking term is retained as", CH)
    eq_box(story, [r"G_{i,cl}(s)=\dfrac{T_i(s)/N_{CH}}{1+T_i(s)/N_{CH}}"], ch=CH)
    body(story, "If T<sub>i</sub>(s)/N<sub>CH</sub> &gt;&gt; 1, this term approaches one. The full "
        "expression is kept because this derivation does not replace dynamic blocks by constants in "
        "the final loop equation.", CH)
    body(story, "<b>A.7.7  Feedback divider gain</b>", CH)
    body(story, "The feedback divider gives", CH)
    eq_box(story, [r"H_v=\dfrac{R_{BOT}}{R_{TOP}+R_{BOT}}"], ch=CH)
    body(story, "At regulation,", CH)
    eq_box(story, [r"H_v=\dfrac{V_{FBPFC}}{V_{OUT}}"], ch=CH)
    body(story, "Using V<sub>FBPFC</sub> = 2.5 V and V<sub>OUT</sub> = 393.7 V,", CH)
    eq_box(story, [r"H_v=\dfrac{2.5}{393.7}=0.006350"], ch=CH)
    body(story, "<b>A.7.8  Gain modulator block</b>", CH)
    body(story, "For voltage-loop stability analysis, the system-level averaged command gain is", CH)
    eq_box(story, [r"G_{MOD}=\dfrac{K_{MAX}I_{OUT}}{5}=\dfrac{K_{MAX}P_{OUT}}{5V_{OUT}}"], ch=CH)
    body(story,
        "This is the line-cycle averaged loop-analysis form. The FAN9672 / AND9925 hardware equations "
        "for IAC, RLPK, LPK, VIR and the gain-modulator internals are used to design support-pin "
        "scaling and power-command limits; they should not be inserted directly into the loop product "
        "as though they were the averaged closed outer-loop gain at every line angle. For the two "
        "power levels,", CH)
    eq_box(story, [r"G_{MOD,1700}=\dfrac{1.4\cdot1700/393.7}{5}=1.209\ \mathrm{A/V},\quad"
                   r"G_{MOD,3600}=\dfrac{1.4\cdot3600/393.7}{5}=2.561\ \mathrm{A/V}"], ch=CH)
    body(story, "<b>A.7.9  Voltage OTA compensator</b>", CH)
    body(story, "The voltage OTA produces output current", CH)
    eq_box(story, [r"i_{OTA}=G_{MV}\hat v_{err}"], ch=CH)
    body(story, "The compensation impedance converts this current to a voltage-loop command:", CH)
    eq_box(story, [r"\hat v_c=i_{OTA}Z_{comp}(s)"], ch=CH)
    body(story, "Therefore,", CH)
    eq_box(story, [r"G_{mv}(s)=G_{MV}Z_{comp}(s)"], ch=CH)
    body(story, "For a Type-III target shape,", CH)
    eq_box(story, [r"Z_{comp}(s)=K_v\,\dfrac{(1+s/\omega_{z1})(1+s/\omega_{z2})}"
                   r"{s(1+s/\omega_{p1})(1+s/\omega_{p2})}"], ch=CH)
    body(story, "The selected target locations are f<sub>z1</sub> = 3 Hz, f<sub>z2</sub> = 12 Hz, "
        "f<sub>p1</sub> = 17 Hz and f<sub>p2</sub> = 50 Hz.", CH)
    body(story, "<b>A.7.10  Final voltage-loop gain</b>", CH)
    body(story, "Substituting the gain modulator, the closed current-loop tracking term, the "
        "power-stage plant, the divider gain and the voltage compensator,", CH)
    eq_box(story, [r"T_v(s)=K_{MAX}\dfrac{I_{OUT}}{5}\dfrac{V_{FBPFC}}{V_{OUT}}"
                   r"\dfrac{T_i(s)/N_{CH}}{1+T_i(s)/N_{CH}}"
                   r"\dfrac{(1+sC_O r_C)(1-s/\omega_{RHP})}{C_O s+2/R_{LOAD}}G_{MV}Z_{comp}(s)"], ch=CH)


# ════════════════════════════ Appendix B ════════════════════════════════════
def _appendix_b(story):
    step_h(story, "Appendix B", "Bill of Materials (Control Components)", CH)
    body(story,
        "External components that set the control behaviour, with the step that derives each. "
        "Power-train components (switches, inductors, bulk capacitor) are specified in the power-stage "
        "design and are listed here only where they enter the loop equations.", CH)
    data_table(story, "B.1", "Control Bill of Materials",
        "External components that set the control behaviour.",
        ["Designator", "Value", "Type / Rating", "Tol.", "Function (step)"],
        [["R_RI", "11.5 kΩ", "Thin film, 1/16 W", "1%", "Oscillator — 70 kHz (Step 4)"],
         ["R_FB1", "3.63 MΩ", "HV divider, ≥ 200 V", "1%", "Output sense top (Step 5)"],
         ["R_FB2", "23.2 kΩ", "Thin film", "1%", "Output sense bottom (Step 5)"],
         ["R_CS", "15 mΩ", "Kelvin shunt, 3 W", "1%", "Current sense (Step 6)"],
         ["R_IAC", "6 / 12 MΩ", "HV, ≥ 400 V", "1%", "IAC line sense, FR/HV (Step 3)"],
         ["R_RLPK", "12.1 kΩ", "Thin film", "1%", "Peak detector (Step 3)"],
         ["R_IC", "120 kΩ", "Thin film", "1%", "Current comp gain (Step 10)"],
         ["C_IC1", "1.3 nF", "C0G/NP0", "5%", "Current comp zero (Step 10)"],
         ["C_IC2", "51 pF", "C0G/NP0", "5%", "Current comp pole (Step 10)"],
         ["R2", "143 kΩ", "Thin film", "1%", "Voltage comp R2 (Step 11)"],
         ["R3", "8.66 MΩ", "Thin film", "1%", "Voltage comp R3 (Step 11)"],
         ["C1", "390 nF", "Film", "5%", "Voltage comp C1 (Step 11)"],
         ["C2", "1.1 nF", "C0G/NP0", "5%", "Voltage comp C2 (Step 11)"],
         ["C3", "24 nF", "Film/C0G", "5%", "Voltage comp C3 (Step 11)"]],
        col_widths=[CW*0.14, CW*0.13, CW*0.26, CW*0.09, CW*0.38], ch=CH)
    annotation(story, "PITFALL",
        "Use C0G/NP0 or film dielectrics for every compensator capacitor. Class-II ceramics (X7R and "
        "worse) lose 20–80% of their capacitance with DC bias and temperature, which would shift the "
        "carefully placed pole/zero frequencies and erode phase margin in the field.", CH)


# ════════════════════════════ Appendix C ════════════════════════════════════
def _appendix_c(story):
    step_h(story, "Appendix C", "Bench Verification and Test Plan", CH)
    body(story,
        "Each headline result in this report has a corresponding bench measurement. Performing these "
        "closes the loop between calculation and hardware and is the basis for design sign-off.", CH)
    sub_h(story, "C.1", "Loop gain — phase and gain margin", CH)
    annotation(story, "INSIGHT",
        "ON THE BENCH — Inject a small disturbance across a 10–50 Ω resistor placed in the feedback "
        "path and measure the loop gain with a frequency-response analyzer (Bode 100, or equivalent). "
        "Measure the current loop (expect crossover ≈ 8.1 kHz, PM ≈ 63°) and the voltage loop (expect "
        "17 Hz / 82° at high line, 7.8 Hz / 81° at low line). Sweep both line and load corners and "
        "confirm the trends in Steps 10–11.", CH)
    sub_h(story, "C.2", "Load-step transient", CH)
    annotation(story, "INSIGHT",
        "ON THE BENCH — Apply 0→100% and 100→0% electronic-load steps at low and high line. Capture "
        "bus deviation and recovery time with an AC-coupled probe. Expect a worst-case dip near 7.3% "
        "(28.9 V) recovering within ~150 ms (Step 12); confirm the response is monotonic, with no "
        "ringing, consistent with the >80° phase margin.", CH)
    sub_h(story, "C.3", "Input-current THD and 120 Hz rejection", CH)
    annotation(story, "INSIGHT",
        "ON THE BENCH — Measure input-current THD with a precision power analyzer across line and "
        "load. Expect the loop contribution to track the 120 Hz rejection of Step 13 (30 dB low line, "
        "23.5 dB high line). Separately verify the bus 120 Hz ripple amplitude against the Step 13 "
        "prediction (2.6 V low line, 5.5 V high line).", CH)
    sub_h(story, "C.4", "Brown-in / brown-out and start-up", CH)
    annotation(story, "INSIGHT",
        "ON THE BENCH — Ramp the AC line up and down slowly and record the start and stop thresholds "
        "(expect brown-in ≈ 86.7 Vac, brown-out ≈ 47.9 Vac, Step 9). Apply IEC 61000-4-11 and "
        "SEMI F47 voltage dips and confirm ride-through without nuisance shutdown.", CH)
    annotation(story, "NOTE",
        "Record all measurements against the predicted values in a sign-off table. A deviation beyond "
        "component tolerance usually points to a modelling assumption (ESR, sense filtering, or layout "
        "parasitics) worth revisiting rather than a calculation error.", CH)


# ════════════════════════════ Appendix D ════════════════════════════════════
def _appendix_d(story):
    step_h(story, "Appendix D", "References and Further Reading", CH)
    body(story, "Primary sources for the equations and methods used in this report:", CH)
    data_table(story, "D.1", "References",
        "Primary sources for the equations and methods.",
        ["Ref", "Source"],
        [["[1]", "ON Semiconductor, FAN9672 / FAN9673 Interleaved Dual-Channel PFC Controller — Datasheet."],
         ["[2]", "ON Semiconductor, AN4165-D — Design Guidelines for the FAN9672 Interleaved PFC Controller."],
         ["[3]", "ON Semiconductor, AND9925-D — Average Current-Mode Control and Small-Signal Modelling of the PFC Boost Stage."],
         ["[4]", "Texas Instruments, SLVA662 — Type-III Compensator Design with a Transconductance (OTA) Error Amplifier."],
         ["[5]", "R. W. Erickson and D. Maksimovic, Fundamentals of Power Electronics, 3rd ed. — boost small-signal model, RHP zero, feedback design."],
         ["[6]", "L. H. Dixon, Average Current-Mode Control of Switching Power Supplies — Unitrode/TI application note."],
         ["[7]", "IEC 61000-3-2 (input-current harmonics) and IEC 61000-4-11 / SEMI F47 (voltage-dip immunity)."]],
        col_widths=[CW*0.10, CW*0.90], ch=CH)
    annotation(story, "INSIGHT",
        "For the reader new to the field, [5] (Erickson & Maksimovic) is the canonical text for the "
        "plant derivations in Appendix A, and [6] (Dixon) is the original and most readable treatment "
        "of the average current-mode current loop in Step 10.", CH)


# ════════════════════════════ Appendix E ════════════════════════════════════
def _appendix_e(story):
    step_h(story, "Appendix E", "Equation Quick-Reference Card", CH)
    body(story,
        "The working equations of the report on a single card, with the result each produces. Symbols "
        "are defined in the Nomenclature.", CH)
    body(story, "<b>Current loop (Step 10)</b>", CH)
    data_table(story, "E.1", "Current Loop — Quick Reference", "",
        ["Quantity", "Expression / result"],
        [["RHP zero (per phase)", "f_RHP = R_LOAD · D'² / (2π L)"],
         ["Plant resonance / Q", "f_o = D'/(2π√(L_eq C_O)),  Q set by r_L"],
         ["Compensator zero / pole", "f_z = 1/(2π R_IC C_IC1) = 1.02 kHz,  f_p = 1/(2π R_IC C_IC2) = 26 kHz"],
         ["Crossover / margin", "f_ci = 8.12 kHz,  PM = 62.8°"]],
        col_widths=[CW*0.32, CW*0.68], ch=CH)
    body(story, "<b>Voltage loop (Step 11)</b>", CH)
    data_table(story, "E.2", "Voltage Loop — Quick Reference", "",
        ["Quantity", "Expression / result"],
        [["Loop gain", "T_v = (K_max·I_OUT/V_RAMP) · G_i,cl · G_vp · H_OTA"],
         ["Feedback divider", "H_v = V_FBPFC / V_OUT = 0.006350"],
         ["Comp zeros / poles", "f_z1=3, f_z2=12 Hz;  f_p (origin), f_p1=50, f_p2=17 Hz"],
         ["Crossover / margin", "f_cv = 17 Hz (HL) / 7.8 Hz (LL),  PM ≈ 82°"]],
        col_widths=[CW*0.32, CW*0.68], ch=CH)
    body(story, "<b>Performance (Steps 12–13)</b>", CH)
    data_table(story, "E.3", "Performance — Quick Reference", "",
        ["Quantity", "Expression / result"],
        [["Load-step dip", "ΔV_OUT(s) = −ΔI · Z_open(s)/(1+T_v(s));  worst case 28.9 V (7.3%)"],
         ["Bus 120 Hz ripple", "V_ripple,pk = P_OUT/(2 ω_line V_OUT C_O) = 2.6 / 5.5 V"],
         ["120 Hz rejection", "−20 log10|T_v(j2π·120)| = 30 / 23.5 dB"],
         ["THD3 (loop contribution)", "≈ 50 · V_EA,120 / V_EA ≈ 1.5 / 3.0 %"]],
        col_widths=[CW*0.30, CW*0.70], ch=CH)
    annotation(story, "DECISION",
        "End of report.  Seventeen steps, both compensators derived and verified, transient and "
        "distortion characterised, and the design-space trade-offs quantified — a complete, "
        "reproducible control-loop design for the FAN9672 interleaved CCM PFC.", CH)
