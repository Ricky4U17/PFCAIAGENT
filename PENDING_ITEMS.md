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

### A9. Powder material files: `data_source` at the wrong nesting level + 3 with no Bsat-vs-T
Two separate, small data issues found while adding material provenance (item 27):

**(a) Schema mismatch — cosmetic but noisy.** All 67 powder materials log
`[DB] <key>: Missing required field: data_source` at every DB load. The information is NOT
missing: powder files carry it at `basic.data_source`, ferrite files at top level, and the loader
checks top level only. Either move the powder key up or teach the loader to accept both. Until
then the warning is false and trains people to ignore load warnings.

**(b) Real gap — 3 materials have no Bsat temperature data.** `xflux_hdc_26`, `xflux_hdc_40`,
`xflux_hdc_60` carry only `Bsat_25C_T` (no 100 °C/150 °C points, no `Bsat_Tcoeff`), so
`get_Bsat()` falls back to the constant 25 °C value for them and the report's provenance table
says so explicitly ("single value — this material carries no temperature data"). The other 71
powder materials have the full 25/100/150 °C set. Add the missing points from the Magnetics High
DC Bias XFlux Bulletin.

**(c) Contradictory field.** `edge_60.basic.temp_coeff_ppm_per_C = 0` contradicts top-level
`Bsat_Tcoeff = -0.00065`. The explicit 25/100/150 °C points are used in preference to either, so
nothing is currently wrong, but one of the two fields is dead and misleading.

### A10. Reference-file protection — 4 agreed actions (designer 2026-08-02)
Triggered by an accidental deletion of `specs/*.docx|pdf` that went unnoticed for a whole session.
**Key distinction found while investigating:** the deleted files were CITATIONS ONLY (comments and
docstrings) — nothing opens them, nothing broke. The genuinely exposed category is different:

| Category | Files | Deletion impact |
|---|---|---|
| **Runtime-loaded** | `specs/Database/*.xlsx` — `inputprotection/database.py:25` resolves `specs/Database` and opens `ICL_Database.xlsx` | **NTC + fuse selection BREAK** |
| Provenance-only | `PFC_Design_Report_Steps13_15_Styled.docx`, `Output_Capacitor_Calculation.docx`, `PFC_Report_Structure_Agreement.pdf`, `PFC_Inductor_Engine_Equations.pdf`, the 2-channel reference PDF | nothing breaks; the "why" is lost |

**Agreed actions, in priority order:**

1. **Commit `specs/Database/ferroxcube_cores_database (1).xlsx`** — it is currently UNTRACKED, so
   deleting it is PERMANENT. Every other workbook in that folder is tracked and recoverable. This is
   the only unrecoverable exposure; highest value, smallest effort.
2. **Add a startup/test check** asserting the runtime-loaded workbooks exist. A folder cannot give
   this: it turns a silent breakage into an immediate failure, and would have caught the deletion on
   day one instead of it sitting unnoticed. (The accident was a DETECTION failure, not a protection
   failure — git already protected the files.)
3. **Create `specs/Reference/`** for the PROVENANCE documents only. **Leave `specs/Database/` where
   it is** — moving it means editing the hard-coded `_SPEC` path in `inputprotection/database.py`
   and re-testing every selector. Two folders with distinct jobs: `Database/` = the code reads this,
   `Reference/` = humans read this.
4. **Update the citations** to carry the new path so a reader can find them
   (`doc_report_builder.py` header + line ~1912, `step15_cap_db.py` docstring,
   `generate_steps13_14.py` ~1789).

**Also fix while there:** `edge_60.json`'s `validation_anchor.reference_doc` cites
`2_Channel_Inteleaved_magnetics_calculations.pdf`, which does NOT match the restored
`2 Channel Inteleaved TTP CCM PFC Design Document.pdf`, and no file of that name exists. That
citation is PRINTED in the report at Section 3.2.6 as the loss-model validation source, so the
report currently points at a document the repo does not contain.

---

### A11. No real diode datasheet has been through the extractor  `CLOSED 2026-08-11 (C222)`
Closed by the designer supplying both files: `vs-4c16ep07l-m3.pdf` (Vishay, 650 V Gen 4 SiC
Schottky) and `SFAF1601G SERIES_H2105.pdf` (Taiwan Semiconductor, 16 A 50–600 V super-fast), both in
`specs/Review/PFC Boost Diode`. No vendor-specific diode template was needed — the generic one
covers both once the seven defects below were fixed.

**Seven defects, one of which produced silently wrong loss numbers.** Full account in
IMPLEMENTATION_LOG C222; the headline is that a SERIES datasheet bands the values that differ
between its parts, and the part number resolved to the LAST variant while the banded values came
from the FIRST — SFAF1608G reported 0.975 V against a real 1.700 V, 43 % low, straight into
conduction loss. The designer's part number is now the variant; with none given every band is kept
and `variant_required` asks, so nothing is silently chosen.

The others: `Tj_max` read the LOWER bound of "-55 to +175"; `I_FRM` was mapped onto `I_FSM`; `I2t`
was lost to a private-use integral glyph; `C_j` was unread because this vendor prints it as a bare
"C"; the hot forward curve mixed two temperatures into one non-function; and the surge ratings and
junction limit were extracted and then dropped on their way to the block.

Verified by `tests/test_diode_real_datasheets.py` (22 tests), every expectation read off the printed
table rather than off the extractor's own output.

**Still true, and worth keeping:** the M4b precedent — a real file is what exposes a template that
silently falls back to generic. Any further vendor template should be added only against a PDF.

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

### B3. Bridge rectifier tempco is a scalar — `rd = 0` is NOT the defect  `CORRECTED 2026-08-01`

> **PREMISE CORRECTED.** This entry previously said `to_block` should derive `rd` from the Vf–If
> slope. **Do not do that — it double-counts.** `Bridge.vf()` returns the curve value and the model
> then adds `rd·i` on top (`pfc_loss_model.py` line 210), so `rd` is a term ADDITIONAL to the curve.
> `_vf_curve` already synthesises a sloped curve — measured implied slope 10.0 / 5.0 / 13.3 mΩ for
> Vf 1.0 V@20 A, 1.1 V@40 A, 0.95 V@15 A. Populating `rd` from that same slope would count the I²R
> term twice and overstate bridge loss. **`rd = 0.0` is self-consistent and correct.**
>
> Paralleling is also modelled correctly through the curve: each device carries i/n and sits lower
> on its own curve. The designer's original "identical 32.7 W" was the `share_worst = 1.0` case
> (see the note below), not a missing `rd`.

**The actual defect** is the temperature model, and the engine already has the right mechanism for
it. `Bridge.vf()` supports `vf_curve_hot` (a second, hot V–I curve) and interpolates per current
point — its own comment says this "captures the NTC threshold AND the PTC series resistance, which a
single vf_tco scalar cannot (the curves converge/cross at high current)". DB-selected bridges never
get a hot curve, so they fall back to `vf_tco = −0.002 V/°C` applied at EVERY current. A real Si
rectifier's tempco is negative only below its crossover (≈ rated current) and positive above it, so a
constant negative tempco makes a cooler device look worse — which is why paralleling measured as a
LOSS INCREASE on 54 of 70 sampled parts. That is an artifact of the scalar, not physics.

- **Designer decision 2026-08-01: option (a)** — correct the record, warn against the `rd`
  double-count, and document the limitation in the report (done: Section 7.3 "BASIS — HOW THE BRIDGE
  FORWARD DROP IS MODELLED"). No loss numbers changed.
- **Real fix (DATA):** add `vf_hot` / `vf_if_hot` columns to the bridge workbook and pass a hot
  curve through `to_block`. Then the approximation disappears entirely.
- **Rejected:** synthesising a hot curve with an assumed crossover — it is still a guess and would
  silently move every bridge loss figure.

<details><summary>Original entry (superseded — kept for the measurements)</summary>

### B3-orig. Bridge rectifier: DB parts have no dynamic resistance `rd`
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

</details>

### B4. Status vocabulary  `DONE 2026-08-01 (3e)` — one residual item
Canonical set is now **PASS / FAIL / CONDITIONAL / DATA MISSING / OPTIONAL / BLOCKED**, defined in
`doc_report_builder.STATUS_WORDS` with `norm_status()` applied at the RENDER BOUNDARY (inside
`data_table` and `verdict_row`). Only a cell whose whole value is a legacy word is rewritten, so
prose such as "gates 3, 5 OPEN" is never touched. Legend rewritten; "NOT PROVEN" and
"DATA MISSING / OPEN ITEM" retired; GUI `vColor` covers all six and still maps the legacy words.

**Residual — internal enums not renamed (deliberate).** `inputprotection/ntc_bypass_select.py` still
stores `OPEN` / `CHECK` in its `st{}` status dict, and `adapter.py` compares against them
(e.g. `any(v in ("OPEN","CHECK") for v in st.values())`). These render correctly through the
boundary and the GUI maps them, so nothing is user-visible.

Renaming them means moving producer AND consumer together — during 3e exactly that coupling bit:
renaming `gate_summary()`'s per-gate status broke `adapter.py`'s `status == "OPEN"` counter, which
would have left `gates_open` permanently empty. Caught and fixed, but it is the reason this half is
a separate task rather than a tail-end of the same edit.

- **Done when:** the internal dicts use `STATUS_WORDS` values and every comparison is updated in the
  same commit, with a fuse/NTC gate round-trip test asserting `gates_open` is still populated.

<details><summary>Original entry (superseded)</summary>

### B4-orig. Status vocabulary is not consistent across chapters  *(parked by the designer, 2026-07-30)*
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

</details>

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

### B8. Fan credit is never taken on the inductor thermal model  `DECISION-ADJACENT`
The intake spec commonly says cooling = fan cooled, but the toroid temperature rise uses an
empirical NATURAL-CONVECTION surface-area law with no airflow term. This is conservative (forced
air only reduces the rise) and is now stated explicitly in report Table 4.6b + a PITFALL box
(item 28), so the two chapters no longer appear to contradict each other.

**Open if ever revisited:** taking fan credit needs a qualified airflow velocity AT THE INDUCTOR,
which is a system-integration input this design stage does not collect. If that input is ever
added, Table 4.6b, the ΔT budget and the ΔT pass/fail gate must change together.

Related dead path: `step7_magnetic_calc._thermal_Rth()` takes `h_forced = 17.5 W/m²·K` (a
forced-air coefficient) but is only reachable for ETD/ferrite cores — it never runs for toroids.
Anyone reading that default could reasonably assume airflow is modelled for toroids. It is not.

### B9. `L_target` vs `L_req` — designer inputs can disagree (advisory check now live)
Item 29 surfaced that the design carries THREE inductance bases and only one of them sizes
anything:
- `L_target` — the designer's confirmed value. Used ONLY as the initial turns estimate and as a
  legacy `<95%` fallback when no requirement curve exists. It sizes nothing in the modern path.
- `L_req(V)` — per-point requirement from the crest ripple ratio. **This is what the turns loop
  converges against.**
- `L_as-built(V)` — what the built part delivers; drives Sections 3.5/3.6, Ch4, and Ch6/Ch7.

Report Table 3.3.1 now quotes ripple on the REQUIREMENT basis (was: on the `L_target` basis, a
number nothing else used), Section 3.5.2 states it is on the AS-BUILT basis, and an advisory
PITFALL fires when `|L_target - max(L_req)| / max(L_req) > 10%`.

**Open — designer decision, not a code bug:** on the reference state the check fires at **+67%**
(`L_target` 235 µH vs `max(L_req)` 140.4 µH). Either the confirmed inductance or the crest ripple
ratio is not what was intended. Harmless today because sizing follows `L_req`, but the two intake
inputs should be reconciled. NOTE the 235 µH may be a test-fixture artifact — check against a real
designer state before concluding anything about production designs.

The check is REPORTING ONLY by design (convention D0b): it never filters candidates and never
changes a verdict.

#### What to decide
The two intake inputs below independently determine an inductance, and they currently disagree:

| Input | Where the designer sets it | What it produces |
|---|---|---|
| Confirmed inductance `L_target` | Mode A / Step-7 intake (`confirmed_L_uH_sel`) | 235 uH on the reference state |
| Crest ripple ratio `r` | `topology_specific_inputs.default_crest_ripple_ratio` (0.20) | `L_req(V)`, max 140.4 uH at 220 Vac |

**Exactly one of them is redundant.** Three ways to resolve it:

- **(1) Ripple ratio is the master (recommended).** `L_target` becomes a display-only "designer's
  expectation", clearly labelled as not driving anything. Cheapest, matches what the engine already
  does, zero behaviour change. The divergence note then reads as information rather than a warning.
- **(2) `L_target` is the master.** The turns loop would have to size to `max(L_req, L_target)`.
  On the reference state that means N sized for 235 uH instead of 140.4 uH -> more turns, more
  copper, higher fill and DCR, and the design would run at a LOWER ripple ratio than the designer
  selected. **This changes selection** and contradicts the "zero added margin" rule in Section 3.4.3.
- **(3) Make them consistent at intake.** Derive `L_target` FROM the ripple ratio when the designer
  changes `r` (and vice versa), so they can never diverge. Most correct, most GUI work: the two
  fields become coupled and need a "which one do you want to drive?" control.

#### First step before any of this
Confirm whether the +67% is real or a harness artifact. `verify_combined_report._std_state()` hard
-codes `confirmed_L_uH: 235.0`. Load a REAL designer state (or run Mode A end-to-end) and read the
divergence percentage off the Section 3.3.1 PITFALL box. If a real design diverges by only a few
percent, this is documentation-only; if it diverges like the fixture, it is a live design-intent bug.

- **Done when:** one of (1)/(2)/(3) is chosen, the report says which input is authoritative, and the
  advisory box either disappears or is reworded to match the chosen model.
- **Do NOT** silently make the divergence check a gate — it would block designs that are correct.

### B12. Guard against unrenderable entities (black squares)
Item 6.3 traced the designer's "black square" comments to two numeric entities whose codepoints
have NO glyph in Helvetica's WinAnsi encoding AND are absent from ReportLab's symbol-substitution
table, so ReportLab draws a filled box: `&#8209;` (U+2011 non-breaking hyphen) and `&#9679;`
(U+25CF black circle). Both replaced with renderable equivalents (`-` and `&#8226;`).

**Worth automating:** the one-line scan below currently reports NONE and would catch a
regression the moment someone adds another exotic entity. Consider adding it as a test.

```
for every &#NNNN; in app/mode_b/*.py:  cp >= 256, not cp1252-encodable,
and chr(cp) not in reportlab.platypus.paraparser.greeks.values()  ->  will render as a box
```

### B15. Ch5-Ch7 review — items the designer chose NOT to do (C189)
From `PFC_Report_Ch5_to_Ch7_Review_Comments.pdf`. Recorded so they are not re-raised as new:
- **EOL capacitance derating** — DECLINED for now. We model initial ±20% tolerance only. Electrolytics
  also lose capacitance over life (~another −20%); combined worst case ≈ 0.64 × nameplate. Needs an
  EOL-loss figure (not in the DB) and a decision on whether it gates or only reports.
- **Rename "Life Time Period" → "Lifetime estimate"** — DECLINED. "Life Time Period" is a designer
  decision of 2026-07-14: it is the manufacturer's own term for their published model and is
  deliberately distinct from the retired Methods 1/2.
- **50 °C thermal sensitivity study** — moot once #6 landed; Chapter 7 now runs AT the spec ambient.

**Newly opened by #4 (needs designer input):** `intake.protection.ovp_threshold_v` and
`intake.protection.bus_transient_max_v` do not exist anywhere. Report Table 5.2.2 prints them as
DATA MISSING, so the 450 V capacitor class is currently justified against the regulated bus only —
not against the worst voltage the part actually sees. Supplying both closes that table.

### B13. Unrenderable sub/superscript characters beyond the two fixed in B12
The B12 scan was widened (raw characters, not only `&#NNNN;` entities) and found a PRE-EXISTING set
that will render as wrong glyphs or boxes wherever it reaches report prose:

| File | Characters |
|---|---|
| `generate_full_report.py` | `₀` x3 |
| `generate_step16.py` | `₀` x2 |
| `generate_steps13_14.py` | `₀` x1 |
| `report_steps1_8.py` | `⁰ ⁴ ⁵ ⁶ ⁷ ⁸ ⁹ ⁻` |
| `report_semiconductor.py` | `&#8486;` (U+2126 OHM SIGN) x2 |

Confirmed live: a `₀` I introduced in Section 5.4.2 rendered as **"LI"** instead of "L₀".

**FALSE POSITIVE — do not "fix":** the scan flags `●` at `doc_report_builder.py:887`, but
that is a **matplotlib** axis label (DejaVu renders it correctly), not a ReportLab Paragraph. The
scan cannot distinguish the two rendering engines — check the call site before changing anything.
Some hits may be in comments/docstrings and therefore harmless — **each needs checking in a BUILT
PDF, not by grep alone.** Replace rendered ones with `<sub>`/`<sup>` markup (ReportLab handles those
natively) or the entity ReportLab's `paraparser.greeks` knows.

- **Done when:** the widened scan reports NONE for strings that reach a Paragraph, and it is wired
  as a test (see B12) so new prose cannot reintroduce one.

### B14. C6 capacitance tolerance — GUI half  `DONE 2026-08-02 (C188)`
Step-15 gained a ±20% panel (capacitance, margin vs requirement, Life Time Period) and the CapSim
page gained a −20% / nominal / +20% selector that re-runs the simulation at the chosen corner.
DC bus only; the control loop still uses nominal capacitance.

<details><summary>Original entry</summary>

### B14-orig. C6 capacitance tolerance — GUI half not started
The report half is done (Tables 5.3.3 / 5.4.2 / 5.5.2, C187). The designer also asked for:
1. **Step-15 "Vout DC Bus Capacitor Design" page** — the selected-part table should carry the
   +20% / -20% figures alongside nominal.
2. **DC-bus capacitor simulation agent page** — a selector for nominal / +20% / -20% so the agent
   re-runs and shows results at the chosen corner.

Backend is ready: `step15_capacitor.cap_tolerance_from_selection(step15_result, state)` returns all
three corners already computed by the same engine the report uses, so both screens can read it
without duplicating any physics. Scope reminder: DC bus only — the control loop stays nominal.

</details>

### B10. Pre-existing duplicate table numbers (13 remain)
Found while doing the item-26 numbering sweep. Three kinds, none introduced by that sweep:
- **if/else pairs** — 6.11.6, 6.11.7, 6.11.9, 8.6a, 9.6. Two `data_table` calls share a number but
  only one branch ever renders (Type-II vs Type-III, vendor-DB present vs absent). Harmless.
- **cross-module** — 6.2.1, 6.3.1, 6.3.2, 6.4.1, 6.6.1, 6.7.1, 6.9.1. `doc_report_builder`'s Ch6
  PLACEHOLDER reuses numbers that `report_steps1_8` / `report_step9` also use. The placeholder is
  skipped in the combined report (`include_ch6=False`), so only one renders there — but a
  Ch1–5-only build would show both.
- **genuine** — **9.7** ("Selected Part — Recalculated Design Values" and "Selected Part —
  Gate-by-Gate Verdict" in `report_inputprotection.py`). Both render. Should become 9.7a / 9.7b.

### B11. Dangling table cross-references in prose
A scan for `Table X.Y` mentions with no matching `data_table` call found ~17, e.g. 3.2.4, 3.4.1,
5.1, 5.2, 14.1, 14.6, 14.7, 3.2.2b, 3.2.4a. Pre-existing (verified against HEAD — the numbering
sweep created none). Some may point at equations or figures rather than tables; each needs
checking individually before any renumbering work touches them.

---

### B16. SiC Q_c is not gated to CCM, the silicon recovery term is
`pfc_loss_model.loss()` applies the silicon branch as `fsw*avg(rr_fet_frac*E_rec*rr_active)` — the
`rr_active` mask is zero wherever the point is in DCM. The SiC branch is
`P_rr_to_fet = fsw*0.5*Vo*qc*k_qc`, a scalar with no angle dimension and no mask, so the junction
charge is charged at full V_OUT on every cycle including the DCM portion. In DCM the drain has
already resonated below V_OUT before turn-on, so that share is overstated.

Measured on the reference design: DCM appears **only at 264 Vac and only for ~10 % of the
half-cycle**, where the SiC term is ~1.3 W — so the error is under 0.2 W, at an operating point that
is not the thermal worst case (90 Vac is). Found during C210; the report prose was corrected to
describe what the code does rather than claim CCM-gating for both branches.

- **Done when:** the SiC branch carries the same per-angle treatment as the silicon one, with the
  charge taken at the actual pre-turn-on drain voltage in DCM rather than at V_OUT. Needs its own
  verification pass — it moves numbers, so it does not belong in a datasheet-sourcing milestone.

### B17. Diode V_F is evaluated at the mid-current, not across the ripple triangle
`pfc_loss_model.loss()` computes diode conduction as `vf(i_d_repr)*i_d_density + rd*ms_dio`, where
`i_d_repr` is the mid-value of the conducting current. The duty gating and the ripple's contribution
to the mean square are both correct (`ms_dio = (i_ch^2 + di^2/12)*(1-d)`), so what is missed is only
the CURVATURE of V_F(i) across the ripple band — the linear part is already carried by `rd`.

Both external diode reviews (2026-08-07) recommend sampling V_F at N points across the off-time
current ramp instead. That is a genuine refinement, second-order here: V_F is concave, so evaluating
at the mean understates slightly, and the error grows with ripple depth (dI_L reaches ~12 A on a
~16 A peak at low line).

It is deferred rather than done because it only pays once the V-I curve is real. On the parts seen
so far the datasheet publishes V_F at ONE current per temperature, so the "curve" is flat and
sampling it at ten points returns ten identical values. Do this WITH M7, not before.

- **Done when:** the digitised V_F(i, T_j) curve is available and conduction is integrated across
  the ripple triangle; compare against the present mid-current result on the same part to show what
  the refinement was worth.

### B18. The bridge rectifier has no leakage term at all
`Bridge` (pfc_loss_model.py) has no `irev_curve` and no leakage field of any kind, while `Diode` and
`Mosfet` both do. So `I_rev_vs_Tj` is declared for the two diode classes only, and a bridge
datasheet's reverse current has nowhere to go — the `diodes_inc_rectifier` template used to map `IR`
onto that diode-only key, where the value parsed and was then silently dropped (removed at C211).

**Magnitude: ~16 mW** (400 V bus x ~10 uA x 4 diodes), which is why nobody noticed. It is not worth
a model on its own; it becomes worth having if a bridge is ever run hot enough for leakage to matter,
or if the reverse-recovery placeholder in `Bridge.loss()` is ever made real.

- **Done when:** either `Bridge` gains a leakage term and `I_rev_vs_Tj` is declared for
  `bridge_rectifier` (both, or `audit_device_classes()` will flag it), or the decision to leave it
  out is recorded as final and the report says so where bridge loss is reported.

### B19. M7 — a RASTER curve tracer (the last M7 gap)  `CODE`
Of the datasheets on file the digitiser now reads Vishay x2, Diodes Inc and Infineon (C224). The
Toshiba TRS12E65H is the one it cannot: its curves are **1638x1289 bitmaps with no vector paths at
all**, so there is nothing to trace. This is the "assisted pixel digitising" the bring-your-own-part
plan specified — the agent proposes points, the designer confirms them against the plot — and it is
a different capability from everything built so far, not a tuning problem.

Today it reads nothing rather than reading something wrong, which is the correct failure and is
asserted by `test_a_raster_datasheet_is_refused_rather_than_guessed_at`.

- **Done when:** a raster figure yields a proposal whose cross-check against the part's own
  tabulated point agrees, on the Toshiba file, with the same evidence gate the vector path uses.
- **Do not** relax the vector path's calibration gates to make raster figures "sort of" read. C224
  showed why: two axis defects there fit a straight line with residual exactly zero, so the
  residual is not evidence — only the tabulated point is.

## C. GUI  `CODE`

### C1. Control Design page redesign
Agreed 7-screen confirm-gated flow for Chapter 6, plus S7 download/approve → semiconductors.
Plan in `PFC_GUI_Cleanup_Plan.docx`. Discussed and agreed, **not implemented**.

### C2. Report download fails intermittently — PARTIAL FIX APPLIED, needs designer confirmation
**Symptom (designer, 2026-08-01):** happens on *all* report screens, *intermittently* — sometimes the
PDF downloads, sometimes nothing arrives. Spinner completes normally. **No red error banner.**
**Console captured** (`specs/GUI Report downloading error.docx`, 2026-08-01) — and it is
*negative* evidence that supports the diagnosis. Four messages, ALL benign: React DevTools notice;
an iframe sandbox warning plus `[inject] N=40 stacks=2 Pcore=2.132W L0=179.2uH` from the simulation
agent iframe; a CSS `@import` ordering warning; and two accessibility warnings (form fields lacking
id/name/label). **There is NO fetch failure, NO HTTP error and NO exception.** If the request had
failed, the client would have thrown and every screen renders its error state — so the failure is
after the PDF arrives, in the save path. That is exactly where the two mechanisms below sit.

**Ruled out:**
- Not a timeout. `/mode-b/documentation/generate-report` returns in ~111 s (measured), HTTP 200,
  13.0 MB. Earlier 5-9 min figures were whole-script overhead, not the endpoint.
- Not a backend 500. Every screen DOES render its error state, so a non-OK response would have
  shown a banner. Silence points past the fetch, at the save path.
- Not the EMI payload. A 500 on `KeyError: 'pout_lo'` came from a hand-built test payload; the
  InputFilter screen's own `design` object does include `pout_lo`/`pout_hi`.

**Two silent-failure mechanisms found and fixed** (all 7 sites, now via `src/api/download.ts`):
1. `URL.revokeObjectURL(url)` fired **150 ms** after `a.click()`. Revoking a ~13 MB blob URL while
   the browser is still reading it aborts the download and throws nothing. Now held 10 minutes.
2. `document.body.removeChild(a)` ran synchronously after `click()`; Firefox needs the anchor to
   stay in the document until the download starts. Now removed on the same 10-minute timer.

The **intermittency is what makes the revoke race the prime suspect** — a fixed 150 ms budget wins
or loses depending on machine load and PDF size.

Also fixed in passing: 4 of the 7 screens read `(confirmedState as any).project_id` with NO optional
chaining, which throws a TypeError *after* the PDF is fetched — discarding a report that had been
generated, and on ControlDesign also skipping `setReportGen(true)` (the approve-gate flag).

#### ROOT-CAUSE ANALYSIS 2026-08-01 (console reviewed; nothing implemented yet)
Designer clarification: it now fails **every time, on every screen** (was intermittent).

**The discriminator.** There are seven download paths and they split cleanly:

| Path | Shape | User activation when the anchor is clicked |
|---|---|---|
| `DonePanel` (Mode A) | blob already in memory, `downloadBlob` called SYNCHRONOUSLY from `onClick` | **alive** |
| the other six report screens | `await docGenerateReport(...)` -> **~111 s** -> `downloadBlob` | **long expired** |

Chrome's transient user activation lasts ~5 s; the report request takes ~111 s (measured on the
combined report; an EMI-inclusive one is longer). By the time the anchor is clicked the browser no
longer treats it as user-initiated, and Chrome's automatic-download protection applies. **That
protection is surfaced in the ADDRESS BAR, not the console** — which is exactly why the console
shows no error. It is also per-site and sticky once triggered, explaining "sometimes" -> "always".

**Testable prediction (designer to confirm):** the Mode A DonePanel download should still work,
because it is the only synchronous path. Also check the right-hand end of the address bar for a
blocked-download icon; "Always allow" there is an immediate workaround.

**Proposed fixes, NOT applied — designer deferred them 2026-08-01:**
1. **Visible fallback link** — after the PDF arrives, render "Download didn't start? click here"
   beside the button. Clicking it is a FRESH user gesture and can never be blocked. This is the
   robust fix whatever the root cause; `downloadBlob()` already returns the URL for it, it just
   needs UI in the six screens.
2. **`allow-downloads` on two sandboxed iframes** — see C3 below.
3. *(bigger, optional)* split generation from download so the save is always a direct user click.

### C3. Two studio iframes are sandboxed without `allow-downloads`
- `ReviewMagnetics.tsx:1002` — `sandbox="allow-scripts allow-same-origin"`
- `CapacitorSimAgent.tsx:380` — `sandbox="allow-scripts allow-same-origin"`
- `ControlDesign.tsx:263` — `sandbox="allow-scripts allow-downloads allow-forms allow-modals"` (correct)

Any download initiated INSIDE the first two (a studio CSV/PNG export) is silently blocked by the
browser. This is **not** the report button — that lives in the parent document — but it is the same
class of silent failure. Found while analysing C2, 2026-08-01. One-line fix each.

---

### C4. A review-screen correction lands on one entry; the engine may select another
`confirm(edits)` applies a corrected value to whichever entry `_pick_entry` returns for that
canonical key — the one the review row was showing. But `profile_to_block` selects by CONDITION:
`M.select(profile, "R_DS_on", V_GS=<design gate voltage>, T_j=25)`.

On the reference MOSFET those are different rows. R_DS(on) is published at V_GS = 15, 18 and 20 V;
the review row shows the 15 V entry, so a correction lands there, while a design driving 18 V makes
the engine select the 18 V entry. The correction is recorded, screened by the M6 plausibility gate,
and then **not the value the engine uses**. Pinned by
`test_an_edit_lands_on_one_entry_and_the_engine_may_select_another` (C212) so the behaviour cannot
change silently.

Not a gate problem and not a naming problem — the edit model is under-specified. Found while adding
the plausibility screen, which is what made the divergence visible.

- **Done when:** the review screen shows condition-qualified entries separately for a multi-entry
  parameter and an edit targets the one the designer is looking at; or `confirm` applies the edit to
  every entry of that key and says so. Either way the screened value and the used value must be the
  same number.

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

### D3. Saturation-margin GATE basis — mean-path B_max vs inner-bore B_inner
**Settled for reporting (2026-08-01, item 24 "Package 2"); the GATE is deliberately left open.**

The report now uses ONE flux-margin convention everywhere: headroom
`margin = (B_sat - B_used) / B_sat x 100`, with `B_used = B_inner` (inner-bore peak, the worst point
in a toroid). Ratio forms such as `B_sat/B_max = 3.66x` are gone.

**Still open:** the engine's accept/reject gate (`step7_magnetic_calc.py` ~line 1060, threshold
>= 15%) still runs on the MEAN-PATH `sat_margin_pct`, not on `sat_margin_inner_pct`.

#### Current numbers (updated after item 27c made powder Bsat temperature-dependent)
Reference design, T_core 92.8 C, `Bsat = 1.434 T`, crowding 1.365:

| Basis | Margin | Used for |
|---|---|---|
| Mean-path `B_max` = 0.410 T | **71.4%** | the engine's >= 15% accept/reject GATE |
| Inner-bore `B_inner` = 0.560 T | **60.9%** | every figure the REPORT quotes |

Both are stated on the page (Section 4.3 convention note) and both are on the GUI, labelled — so
nothing is hidden. The gap is ~10 points and is structural: `B_inner = B_max x crowd`.

#### What changing it would cost
Moving the gate to `B_inner` is the physically consistent end state (the bore IS the worst point in
a toroid) but it **CHANGES SELECTION**: cores passing today between 15% and ~27% mean-path margin
would newly fail. On the reference design nothing changes — it sits at 60.9%, miles clear — but the
effect on a marginal design is real and is exactly why this is a decision, not a cleanup.

#### If it is picked up, change all of these together
1. `step7_magnetic_calc.py` ~line 1060 — the `< 15.0` fail check -> `sat_margin_inner_pct`.
2. `generate_full_report.py` — 2 gate labels + the `>= 15` check (currently "(mean path)").
3. `generate_steps13_14.py` — 2 labels (currently "(mean path, gate basis)").
4. Report Section 4.3 convention note — it currently EXPLAINS the difference; that paragraph must be
   rewritten or removed once there is no difference.
5. `Step7Wizard.tsx` — the "(mean path, gate basis)" row label.
6. **Re-tune the threshold.** 15% against `B_max` is not the same requirement as 15% against
   `B_inner`. Decide whether the intent is "keep today's strictness" (then the inner threshold is
   roughly 15% - 10% = ~5%, which looks wrong on paper) or "genuinely tighten" (keep 15%, accept
   that some previously-passing cores now fail). **This is the real question, not the plumbing.**

- **Done when:** one flux point drives both the report and the gate, the threshold has been chosen
  deliberately with the above in mind, and a before/after candidate-count comparison is recorded.
- **Verify with:** the baseline-diff method used in item 29 — snapshot candidate count, ordering and
  `passed` flags before and after, and report how many cores changed verdict.

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

### E2. Chapter builders can vanish silently — always check the page count
`doc_report_builder._ch3` / `_ch4` are called under `if approved_design:` in one try-tolerant
path, so an exception inside `_ch4` dropped BOTH chapters (~90 pages) while the endpoint still
returned HTTP 200 and `ast.parse` stayed clean. The build looked fine; the content was gone.

Cause on 2026-08-01: `_ch4` referenced `Bmax_inner` / `sat_m_inner` / `sat_m`, which are `_ch3`
LOCALS, not module-level. `_ch3` and `_ch4` have separate scopes and each must re-derive what it
needs from `d`.

**Habit:** after editing any chapter builder, run `python verify_combined_report.py` (not just
`build_combined()`), because only `main()` asserts the 178-190 page range. A partial-content PDF
is otherwise indistinguishable from a good one.

---

## Recently closed (kept briefly for context)

| Item | Closed by |
|---|---|
| Ch8 NTC flow was circular (part named before requirement) | C162–C164 |
| Fuse screened on only 4 gates | C165 |
| Fuse inrush peak wrongly gated the continuous rating → nothing selectable | C165 |
| Ch8 Table B practical filter was prose, not a table | C166 |
| Current density printed 4.17 in the equation but 4.12 in text/table (two different RMS currents) | item 21 |
| A_L-min vs nominal basis was never stated in the report | item 22 (note only, by designer decision) |
| Table 3.4.4 printed a bare PASS with no margin — binding corner is only +1.5% | item 23 |
| GUI L_full margin rounded before dividing, so it showed +2% where the report showed +1.5% | item 23 |
| Flux margin mixed two conventions AND two flux points (229% vs 59%) | item 24 |
| Saturation margin shown without its calculation | item 25 |
| "Supplier: ." printed blank (dict.get default never fires on an empty string) | item 26 |
| Powder Bsat ignored temperature while the report claimed it did not | item 27c |
| Material provenance absent — supplier/revision/loss+bias source/temperature basis | item 27 (Section 3.2.6) |
| Thermal-model provenance absent; fan-cooled spec vs natural-convection model unreconciled | item 28 (Table 4.6b) |
| Ripple quoted on target-L and as-built-L bases under one symbol, unlabelled | item 29 |
| GUI "sized to that target" note quoted L_target, not the L_req the engine uses | item 29 |
| "Ccm" instead of "CCM" on the cover and Ch1 table (str.title() on a snake_case enum) | 3c/7.1 |
| "(estimated based on available design data)" x3, "dominates magnetics sizing", "(numerical integration, 3000 points)" | 3c/7.3-7.5 |
| Selected controller row listed 3 alternate ICs instead of the one selected | 3c/7.6 |
| Fuse six gates were one dense paragraph | 3c/6.5 |
| Tables 8.6a/8.6b printed 10 PASS candidates | 3c/6.4 (now screen-outcome summaries + selected row in 8.7b/8.7c) |
| Bullet-list and small-note styles were left-aligned, not justified | 3c/6.1 |
| 14 table numbers broke the "letter series starts at a" rule | 3c/6.2 |
| Black squares in the PDF: `&#8209;` (nb-hyphen) and `&#9679;` (black circle) have no WinAnsi glyph and are not in ReportLab's symbol table | 3c/6.3 |
| No project NAME field — cover and Ch1 showed the generated project_id handle | 3c/7.2 |
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
