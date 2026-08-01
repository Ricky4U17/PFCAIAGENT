# PFC AI Design Agent — Pending Items

Running log of open work. Anything the design agent cannot close **by calculation** — because a vendor
datasheet field, a site input, or a design decision is missing — lands here instead of being silently
passed.

**Conventions**
- `DATA` = a vendor workbook / datasheet column is missing. Fixing the data closes it; no code change.
- `CODE` = needs implementation.
- `DECISION` = waiting on a designer call, not on work.
- Each item names the file(s) involved and what "done" looks like, so it can be picked up cold.

**How this interacts with the reports:** an open item here shows up in the generated report as
`OPEN`, `CONDITIONAL` or `DATA MISSING` — never as a silent PASS, and never as something that blocks
the designer from selecting a part.

Last updated 2026-08-01 (after C178).

---

## A. Vendor database gaps  `DATA`

Counts measured on the shipped workbooks under `backend/app/mode_b/inputprotection/data/`.

### A1. NTC — no datasheet pulse-energy rating  ⭐ highest value
`ICL_Database.xlsx` (997 parts) has **no Joule / max-switchable-capacitance column at all**. Pulse energy
is currently *computed from disc diameter* (`database._energy_est_J`, line 48), which is why every NTC
candidate can only ever reach `CONDITIONAL` — Tier-2 of the selection gate is an estimate, so it is a
soft gate that never rejects a part.

- **Done when:** the workbook carries a real `Pulse energy (J)` and/or `Max switchable C (µF) @ V_ref`
  column; `ingest()` reads it; `energy_estimated` becomes `False` for those parts and they can reach a
  true `PASS`.
- **Raised by:** `specs/NTC/NTC Improvement.docx` review point 4 ("keep estimated energy only as
  preliminary; final database should require actual datasheet Joule rating").
- Also partial in the same file: `R_hot` missing on **112/997** (blocks the warm/hot-restart current for
  those parts), R25 tolerance missing on 6/997, disc diameter on 3/997.

### A2. MOV — clamping voltage at rated current
`MOV_Combined_Database.xlsx` (1140 parts): **`Vc @ I_max` missing on 1140/1140** — the column does not
exist. This is the field Criterion A in Chapter 9 needs, so the clamp check prints `DATA MISSING` and
fails Criterion A rather than passing silently.

- **Done when:** a `Vc @ In (V)` column exists; §9.3/§9.5 Criterion A computes instead of reporting
  DATA MISSING.
- Minor in the same file: energy-2ms missing 9/1140, capacitance 26/1140, V1mA 2/1140.

### A3. GDT — impulse sparkover and follow current
`GDT_Combined_Database.xlsx` (172 parts): **both missing on 172/172** —
- `impulse sparkover @ dV/dt` → §9.8.1 dynamic-sparkover check cannot run.
- `follow current` → §9.8.3 follow-current / fail-short coordination cannot close.

### A4. Fuse — melting I²t holes
`Fuse_Database.xlsx` (115 parts): melting I²t missing on **25/115**; breaking capacity on 1/115. Those
25 parts stay `CONDITIONAL` (selectable, but the no-nuisance-blow check cannot be proven).

### A5. Fuse catalogue coverage
The DB is **fast-blow only** and tops out at **50 A**. A high-power low-line design can legitimately run
out of candidates. Adding time-delay (T) parts and ratings above 50 A would widen the usable envelope —
a time-delay fuse also gives more startup margin than fast-blow.

### A6. Capacitor — cold-side ESR anchor
If the capacitor DB gains a `Z(−25 °C) / Z(+20 °C)` ratio column, `cap_esr_model` could anchor ESR below
20 °C instead of extrapolating.

### A7. Capacitor — vendor temperature multipliers
`VENDOR_TEMP_MULTIPLIERS` registry is **empty**. Populate per-series from verified datasheets only.

### A8. Unresolved: HXK ripple-current variant
Designer's HXK datasheet says **1.69 A** ripple; the DB says **2.09 A**. Which variant is correct is
still unknown — resolve before trusting either for a release calculation.

---

## B. Report & calculation  `CODE`

### B1. Chapter 6 appendix BOM values are hardcoded
`appendices.py` — `build_appendices(story)` takes **no design data**, so the appendix component values
(R_CS 15 mΩ, R_RI 11.5 kΩ, R_FB1 3.63 MΩ, the `0.015/5` equation in Appendix A) do not track the design.
Needs the design threaded into `build_appendices`. Everything in the Ch6 body itself was de-hardcoded in
C99/C100 — this is the leftover.

### B2. Per-Vin time-domain waveform families
`waveforms_by_vin` exists inside `build_view_contract` but is **not** in the `approved_design` payload,
so the report cannot draw B(t)/L(t)/P(t) families over the cycle for all 9 input voltages without
re-deriving them (which would break the one-engine rule). Needs the engine to export the per-Vin time
series into the approved payload.

### B3. Bridge rectifier: DB parts have no dynamic resistance `rd`  ⭐ affects paralleling
`database.to_block(rec, "bridge")` sets `topology / vf_curve / vf_tco / n_parallel / rth_jc / rth_cs`
but **never `rd`**, so every DB-selected bridge runs with the engine default `rd = 0.0`
(`pfc_loss_model.Bridge.rd`).

Why it matters: bridge loss is `2·mean(vf(i·a)·i + rd·a·i²)` where `a = 1/n_parallel`. The `rd·a·i²`
term is exactly the one that halves when devices are paralleled. With `rd = 0` the only benefit of
paralleling is the shape of the Vf curve, and that is partly or wholly cancelled by the negative
`vf_tco = −0.002 V/°C`: two packages run cooler, and a cooler Si diode has a HIGHER Vf.

Measured on the 9-point sweep (2-ch, 90–264 Vac, 1700/3600 W), worst-case-over-line:

| Configuration | n=1 | n=2 | Δ |
|---|---|---|---|
| GBJ40L06 as the DB gives it (rd=0, tco=−0.002) | 26.99 W | 25.82 W | −1.16 W |
| same, tco forced to 0 | 33.21 W | 30.41 W | −2.80 W |
| same, rd = 5 mΩ | 30.80 W | 27.83 W | −2.97 W |
| same, rd = 5 mΩ and tco = 0 | 37.59 W | 32.60 W | −4.99 W |

Across a random 70-part sample, paralleling **increased** worst-case loss for 54 parts and decreased it
for 16 — the sign is dominated by the temperature effect rather than by current sharing.

- **Done when:** `to_block` derives `rd` from the datasheet (slope of the Vf–If curve above the knee, or
  a dedicated `rd` column), so the I²R term is present and paralleling behaves physically.
- **Related `DATA` need:** the bridge workbook has a single `Vf @ If` point; `_vf_curve` synthesises a
  3-point curve around it (shape is an ESTIMATE, already flagged). A real datasheet Vf–If curve would fix
  both `rd` and the curve shape.
- **Note (not a bug):** setting `share_worst = 1.0` on the bridge form makes `n_parallel` have literally
  zero effect (`a` clamps to 1.0). That is correct — it declares that one die carries the whole arm —
  but it does mean the loss will not move at all when paralleling is changed.
- Raised 2026-07-30 by a designer report that 1 vs 2 bridges gave identical loss.

### B4. Status vocabulary is not consistent across chapters  *(parked by the designer, 2026-07-30)*
The MOV review asks for exactly six status words: **PASS / FAIL / DATA MISSING / REVIEW / OPTIONAL /
BLOCKED**. Today two different sets are in use:

| Chapter | Words currently emitted |
|---|---|
| Ch8 (NTC / fuse) | PASS · OPEN · CHECK · BLOCKED · CONDITIONAL |
| Ch9 (MOV / GDT) | PASS · FAIL · DATA MISSING · REVIEW · OPTIONAL · CONDITIONAL, plus strays "NOT PROVEN" and "DATA MISSING / OPEN ITEM" |

This is deliberately **not** a Ch9-local fix — doing it per-chapter would entrench the split. It needs one
project-wide pass over Ch7–Ch10 plus the GUI badge colours (`vColor` in `InputProtection.tsx`, which
already special-cases OPEN/CHECK).

**Recommendation when it is picked up:** keep **CONDITIONAL** — it is load-bearing, it is the mechanism
that implements rule D0b (a gate may stop release without blocking selection) — and fold **REVIEW** into
it rather than carrying both. Map OPEN → DATA MISSING, CHECK → CONDITIONAL, retire "NOT PROVEN".

- **Done when:** one vocabulary is defined in a single module-level constant set, every chapter emits
  only those words, and the GUI badge mapping covers all of them.
- Deliberately deferred by the designer while M1–M3 land, so the reorg is not blocked behind it.

### B5. Audit remaining bare `onClick={fn}` handlers when adding new ones  *(FIXED for today's sites — C174)*
Not an open defect: all current sites are clean. This entry exists because the **failure mode is easy to
reintroduce and expensive to diagnose**, so the rule should be visible.

**What happened (C174):** `onClick={calcNtc}` passes the handler bare, so React calls it with the click
event. Where the handler's first parameter is an *optional override* — `calcNtc(override?: Opts)` — the
SyntheticEvent silently became that override and went into the request body, producing
`Converting circular structure to JSON … HTMLButtonElement … FiberNode … stateNode`. Three buttons were
affected (Re-size NTC, Re-size surge, Re-select fuse) and the designer's knob values were never reaching
the backend on any of them.

**Why `tsc` never saw it:** `Btn` declared `onClick?: () => void`, and TypeScript accepts a function whose
only parameter is optional as a zero-arg function. The type asserted "no arguments" while React passed one.

**The rule:** any handler that takes parameters must be wrapped — `onClick={() => fn()}` — never passed
bare. `Btn.onClick` is now typed `(e: React.MouseEvent<HTMLButtonElement>) => void`, so `strictFunctionTypes`
rejects the bare form at compile time (verified: reverting one site reproduces TS2322). Zero-argument
handlers (`onBack`, `onRestart`, …) still assign fine and need no wrapper.

- All ~25 other bare `onClick={fn}` sites in the frontend were swept at C174 and take no parameters.
- `client.ts::assertSerialisable` now rejects a DOM element / DOM event / React synthetic event in a
  request body with a message naming the field and the likely cause, instead of a circular-structure trace.

### B6. EMI Phase D
Monte-Carlo tolerance analysis and radiated-emissions screening. Deferred by the designer after EMI
review round 2 (C147/C148). Also outstanding from that review: E-series component snapping, and
treating CM leakage as differential-mode L.

### B7. EMI filter — Rev J methodology
`specs/EMI_Input_Filter_Design_Guide.docx` (Rev J) was reviewed but **not implemented**. Scope agreed as
configurable PFC + DC-DC, with DC-DC as placeholders. Hard no-hardcode mandate applies.

---

## C. GUI  `CODE`

### C1. Control Design page redesign
Agreed 7-screen confirm-gated flow for Chapter 6, plus S7 download/approve → semiconductors.
Plan in `PFC_GUI_Cleanup_Plan.docx`. Discussed and agreed, **not implemented**.

---

## D. Decisions  `DECISION`

### D0. SETTLED 2026-07-30 — two project-wide conventions
Both decided by the designer; apply everywhere, do not re-litigate per chapter.

**(a) Section references spell out "Section".** No `§`, no "Sec.". Applies to the WHOLE report.
Currently three conventions are live — `§` (23 rendered hits in Ch8/9, introduced by C164/C166),
"Section" (Ch1–6, set by C105), "Sec." (Ch7/Ch10, set by C145). See B4 for the sweep.

**(b) BLOCKED gates RELEASE ONLY, never part selection.** A BLOCKED or DATA-MISSING gate stops the
release sign-off and must be listed as a blocker, but the designer can always still select a part.
This is now the general rule behind [[feedback-selection-never-blocked]] — D1 below is one instance of
it, and it is the answer to the MOV review's request for BLOCKED on a negative clamp margin.

### D1. Hot restart — DECISION-REQUIRED, not BLOCKED  *(instance of D0b)*
`specs/NTC/NTC Improvement.docx` asks for hot restart to be marked **BLOCKED** until a restart policy
exists. We implement it as **DECISION-REQUIRED**: it gates the final release sign-off but never blocks
NTC part selection.

Report §8.10 + Table 8.10b. Settled — consistent with D0b.

### D2. Max-stacks 3-stack sighting
A designer once saw a 3-stack candidate when max_stacks should have excluded it. The chain was verified
to honour the setting and a defensive client-side filter was added (C87), but the original sighting was
never reproduced. If it recurs, capture the exact supplier / material / mounting flow.

---

## E. Engine / test debt  `CODE`

### E1. Mode-A workflow control design is genuinely unstable
The LangGraph `control_loops` / `state_space` nodes produce an unstable design (voltage-loop crossover
399 Hz against a 20 Hz limit, current PM 14°, negative voltage margins), so `guardrail_v2` correctly
hard-stops the pipeline. Because `blocking_enabled` is tied to `enable_guardrail_v2` with no
advisory-only split, ~6 phase-advisory tests can never reach `final`.

**Not a production issue** — the production Step-16 path is stable at ~17 Hz. This is the LangGraph
workflow path only. Found during C117.

---

## Recently closed (kept briefly for context)

| Item | Closed by |
|---|---|
| Ch8 NTC flow was circular (part named before requirement) | C162–C164 |
| Fuse screened on only 4 gates | C165 |
| Fuse inrush peak wrongly gated the continuous rating → nothing selectable | C165 |
| Ch8 Table B practical filter was prose, not a table | C166 |
| Fuse I²t collapsed 4 different events into one worst case | C166 |
| Ch8 section order / full 8.1→8.14 renumber | C166 |
| Three section-reference conventions (`§` / "Sec." / "Section") | C167 |
| Ch9 never named a selected MOV part; clamp/energy judged on the class | C168–C170 |
| Ch9 clamp result had no engineering decision beside it | C170 |
| Ch5 vs Ch7 capacitor loss disagreed (different ESR, re-derived not carried) | C171 |
| Inductor copper: design scalar vs loss table disagreed 8.3% at the same corner | C177 |
| Dead `_extra["esr_mohm"]` carrying the C171 `or`-chain pattern | C178 |
| Ch3 candidate table starred rank #1 instead of the approved design | C178 |
| Ch8 §8.9.2 precharge timing used the generic R25, not the selected NTC | C178 |
| `verify_configuration` returned no ESR when the curated series table lacked the series | C172 |
| Re-size/Re-select buttons sent React's click event as their options (circular-JSON error) | C174 |
| Backend test suite red (33 failures) | C107–C120, now 172 passed / 2 skipped |
| Printed TOC covered only Ch1–5 | `_rebuild_printed_toc` |
| MOV vendor workbook not wired | C149 |
