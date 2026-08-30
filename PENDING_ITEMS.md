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

Last updated 2026-08-23 (after C252).

**AUDITED 2026-08-23 (C252).** Every mechanically-checkable claim below was re-run against the
code, because this list had been wrong five times running — B5 and Group 2 read open while closed
since C178, E2 read open while guarded, C2 read "fixed" while hiding a live defect, and C3
undercounted its own sites. Results:

- **The `DATA` section is exact.** A1 (997 parts, no energy column, R_hot 112/997, tolerance 6/997,
  diameter 3/997), A2 (V<sub>c</sub>@I absent, V1mA 2/1140, energy 9/1140, capacitance 26/1140),
  A3 (no impulse sparkover, no follow current, 172/172), A4 (melting I²t 25/115, breaking capacity
  1/115), A5 (max rating 50.0 A, 115/115 Fast Blow), A7 (registry holds only a commented example).
  Every count still matches to the digit. These are genuinely blocked on vendor data.
- **Four entries were stale and are now closed or rescoped:** B1 (the appendix builder DOES take
  design data), B2 (Section 4.6.2 renders the per-V<sub>in</sub> families), A9a and B10 and C3
  (fixed at C252), B12/B13 (the proposed scan predicate was wrong in both directions — see B12).
- **Entries labelled done but never moved:** A11, B4, B5, B14, E2. Moved to Recently closed.
- **Where an entry's prose was stale but its claim held**, the claim is kept and the prose
  corrected: B16's quoted formula was out of date, the missing DCM mask is real; B17's variable had
  been renamed, the mid-current evaluation is real (`pfc_loss_model.py:359`).

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

### A9. Powder material files: 3 with no Bsat-vs-T  *(part (a) FIXED at C252)*
Two separate, small data issues found while adding material provenance (item 27):

**(a) Schema mismatch — FIXED at C252.** The count was **66**, not 67, and the split is real: of
92 material files, 66 powder files carry `data_source` under `basic` and **8 powder files carry it
at top level** (all 18 ferrites are top-level). So migrating the 66 would not have made the schema
correct either. `POWDER_REQUIRED_FIELDS` now names both locations
(`"data_source|basic.data_source"`) and `validate_material_dict` takes the first that resolves.
Measured 66 errors before, 0 after; proven by reinstating the original single path, which
reproduces all 66. Guarded by `tests/test_report_hygiene.py`.

*Why it was worth fixing a "cosmetic" warning:* it fired on every single load and was always
wrong, which is how people learn to scroll past load warnings — and that is exactly where a real
one appears.

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

1. ~~**Commit the untracked workbooks**~~ **DONE at C253.** There were TWO, not one: `ferroxcube_cores_database (1).xlsx` AND `Power_Relays_Database.xlsx` (loaded by `inputprotection/database.py`). Both are now tracked, so every workbook in that folder is recoverable. Original text: it is currently UNTRACKED, so
   deleting it is PERMANENT. Every other workbook in that folder is tracked and recoverable. This is
   the only unrecoverable exposure; highest value, smallest effort.
2. ~~**Add a startup/test check** asserting the runtime-loaded workbooks exist.~~ **DONE at C267**
   — `backend/tests/test_runtime_data_files.py`, 25 checks. Original text: A folder cannot give
   this: it turns a silent breakage into an immediate failure, and would have caught the deletion on
   day one instead of it sitting unnoticed. (The accident was a DETECTION failure, not a protection
   failure — git already protected the files.)

   Built to check THREE properties per family, because each fails on its own: **resolves** (a source
   exists), **loads** (it yields a real header and a data row — a zero-byte file passes
   `os.path.exists` and still breaks the page), **tracked** (git can recover a deletion). Families
   are discovered from the module's own `*_src_path` resolvers and `_SRC` dict, so a sixth workbook
   is covered without editing the test; `test_the_enumeration_found_something` fails if a rename
   ever empties the scan. MOV and GDT are classified OPTIONAL — `load_mov`/`load_gdt` return `[]`
   and fall back to the built-in catalog — so they must load and be tracked *if present* but are
   not required to exist.

   **Two things found while building it.** (a) The first draft reimplemented the path lookup and was
   wrong within minutes — the fuse family searches `specs/Improvements/FUSE`, which the
   reimplementation did not know about, and the fuse sheet has TITLE rows above its header so the
   generic `_rows` read the title as a one-column header. It now calls `*_src_path()` and the
   family's own reader; a check that reimplements what it checks verifies something else.
   (b) `MOV_Combined_Database.xlsx` and `GDT_Combined_Database.xlsx` under `specs/Improvements/MOV/`
   are UNTRACKED — but **not an exposure**: the resolver prefers the `inputprotection/data/` copies
   and those are tracked. Left alone deliberately; tracking a second copy of a tracked file is the
   C244 duplicate-asset trap.

   All four failure modes were verified to fire (deleted / zero-byte / misplaced header / untracked,
   the last against a real untracked workbook) with a healthy family as the negative control.
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

### B1. Chapter 6 appendix BOM values are hardcoded  `MOSTLY CLOSED — verify what is left`
**Corrected 2026-08-23.** The premise is out of date. `build_appendices` now takes the design:
`build_appendices(story, prior=None, s10=None, s11=None, s12=None, s13=None, inp=None)`, and
Table B.1 reads live values (`ctx['rri']`, `ctx['r1']`, `ctx['rcs']`) — done by C238/C239, which
also put the six pole-derived capacitors in the table.

**What is actually left:** the literals now only survive as `.get(..., default)` FALLBACKS
(e.g. `float(p5.get("rfb1", 3.63e6))`). A fallback is not automatically wrong, but a silent one is:
if the design data does not arrive, the appendix prints the reference design's numbers with nothing
saying so.

- **Done when:** each fallback either cannot be reached (the caller always supplies the value) or
  prints a visible marker when it fires, so a stale appendix cannot look like a computed one.

### B2. Per-Vin time-domain waveform families  `CLOSED — verified 2026-08-23`
The report draws them. **Section 4.6.2 "Per-Cycle Waveform Families — All 9 Operating Points"**
(`doc_report_builder.py:4524`) plots six quantities — H(t), i<sub>avg</sub>(t), B<sub>max</sub>(t)
and the instantaneous core / copper / total losses — as low-line and high-line families.

The entry's worry about the one-engine rule was answered a different way than it assumed: rather
than exporting the series through `approved_design`, the builder calls
`build_view_contract(d, state)` directly and reads `waveforms_by_vin` from it. That is the engine
itself, not a re-derivation, so the report and the GUI Review panes plot identical series by
construction.

### B3. Bridge temperature model — measured hot data vs an assumed scalar  `RESCOPED 2026-08-22`

> **TWO PREMISES HAVE NOW BEEN CORRECTED. Read this before picking the entry up.**
>
> **(1) `rd = 0.0` is correct** (2026-08-01). `Bridge.vf()` returns the curve value and the model
> adds `rd·i` on top, so deriving `rd` from the same curve slope double-counts. The original
> "paralleling understates by ~4 W" measurements below belong to that retracted premise.
>
> **(2) The datasheet path already replaces the assumed tempco** (2026-08-22). This entry was
> written before the datasheet-first bridge work (C217/C218/C222) and reads as though nothing
> exists. It does.

**Measured 2026-08-22, both paths, same 100 °C rise at 20 A:**

| path | hot data | ΔV(125 − 25 °C) | basis |
|---|---|---|---|
| catalogue (Digi-Key parametric) | none | −0.200 V | **assumed** `vf_tco = −0.002 V/°C` |
| LVE5060E via datasheet upload | hot V_F from the table | −0.120 V | **measured**, the part's own |

So uploading the datasheet does not merely add a curve — it replaces an assumed temperature
correction with a measured one, a **40 % difference in the whole correction** on this part.

**What is still not captured, and why it is not a code defect.** Both of LVE5060E's "curves" are
SINGLE points (`vf_curve [[25],[0.89]]`, `vf_curve_hot [[25],[0.77]]`), so the drop is constant in
current and the cold/hot pair never converges. Capturing the crossover needs a hot **V–I figure**,
and this vendor prints only a cold one. `datasheet_flow` already raises a `check` note when one of
the pair is digitised and the other is not.

**Why the catalogue path cannot be fixed from the catalogue.** The bridge workbook
(`bridge_rectifiers_combined_sorted.xlsx`) has exactly one forward-voltage column —
`Voltage - Forward (Vf) (Max) @ If` — and no temperature columns beyond "Operating Temperature".
The `vf_hot` / `vf_if_hot` columns the old entry asked for **cannot be imported because the data is
not in the source**. This is the MOSFET story again: the catalogue lacks the fields the engine needs,
which is why datasheet-first exists.

- **Done (option a, 2026-08-01):** the limitation is stated in Section 7.3, conditional on the part
  actually lacking a hot curve, so it fires for catalogue parts and stays silent for datasheet ones.
- **Done (2026-08-22):** `tests/test_bridge_temperature_model.py` guards both states — a datasheet
  bridge must carry a measured hot curve, a catalogue bridge must not and must keep its tempco, the
  measured and assumed tempcos must differ, and the scalar fallback must be a flat shift at every
  current (which is the artifact the note describes).
- **Remaining, and it is DATA not code:** a bridge datasheet that publishes a hot V–I figure, so the
  pair can be digitised and the crossover captured. Nothing to build until such a part is chosen.
- **Rejected:** synthesising a hot curve with an assumed crossover — still a guess, and it would
  silently move every bridge loss figure.

<details><summary>Original entry (superseded — kept for the measurements)</summary>

### B3-orig. Bridge rectifier: DB parts have no dynamic resistance `rd`
`database.to_block(rec, "bridge")` sets `topology / vf_curve / vf_tco / n_parallel / rth_jc / rth_cs`
but **never `rd`**, so every DB-selected bridge runs with the engine default `rd = 0.0`
(`pfc_loss_model.Bridge.rd`).

Measured on the 9-point sweep (2-ch, 90–264 Vac, 1700/3600 W), worst-case-over-line:

| Configuration | n=1 | n=2 | Δ |
|---|---|---|---|
| GBJ40L06 as the DB gives it (rd=0, tco=−0.002) | 26.99 W | 25.82 W | −1.16 W |
| same, tco forced to 0 | 33.21 W | 30.41 W | −2.80 W |
| same, rd = 5 mΩ | 30.80 W | 27.83 W | −2.97 W |
| same, rd = 5 mΩ and tco = 0 | 37.59 W | 32.60 W | −4.99 W |

Across a random 70-part sample, paralleling **increased** worst-case loss for 54 parts and decreased
it for 16 — the sign is dominated by the temperature effect rather than by current sharing.

- **Note (not a bug):** setting `share_worst = 1.0` on the bridge form makes `n_parallel` have
  literally zero effect (`a` clamps to 1.0). That is correct — it declares that one die carries the
  whole arm — but the loss will not move when paralleling changes.
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

### B12. Guard against unrenderable entities (black squares)  `DONE at C252`
Item 6.3 traced the designer's "black square" comments to two numeric entities whose codepoints
have NO glyph in Helvetica's WinAnsi encoding AND are absent from ReportLab's symbol-substitution
table, so ReportLab draws a filled box: `&#8209;` (U+2011 non-breaking hyphen) and `&#9679;`
(U+25CF black circle). Both replaced with renderable equivalents (`-` and `&#8226;`).

**DONE at C252 — but the proposed predicate was wrong, and the scan did NOT report NONE.**

The scan this entry specified — `cp >= 256`, not cp1252-encodable, absent from
`paraparser.greeks.values()` — is wrong in *both* directions, so it could not have been wired as
a test as written:

| character | proposed scan | reality |
|---|---|---|
| `&#8486;` OHM SIGN | flags it | renders correctly (Symbol `Omega`) |
| U+0394 DELTA | flags it (Adobe glyph list maps Symbol's `Delta` to U+2206) | renders correctly |
| U+2713 ✓, U+2717 ✗, U+2605 ★ | flags them | render correctly (ZapfDingbats) |
| **U+2502 │** box-drawing | never looked at — not an entity | **black square on every page footer of two reports** |

**What the mechanism actually is.** No TTF is ever registered, so everything outside WinAnsi is
substituted. ReportLab reaches a real glyph for a handful (Ω, ≤, ✓, ✗, ★, µ, Δ) and falls through
to **ZapfDingbats `n` — a filled black square — for everything else.** That is the designer's
"black square", and `pypdf` extracts exactly that fallback as U+25A0. So the predicate needs no
glyph tables at all: render the character, read it back, and look for `■`.

**Four defects found and fixed at C252,** none of which the shipping report showed, because each
sits on a branch the reference design does not take:

1. `│` in the page footer of `generate_report.py` and `generate_steps13_14.py` — a square on
   **every page** of both standalone reports. Drawn with `canvas.drawCentredString`, not a
   Paragraph, which is why no Paragraph-based check would have found it.
2. `_sct()` in `report_steps1_8.py` built exponents from a Unicode-superscript translation table —
   so "denominator base = 9.014 × 10¹²" printed as `10■■`. Fires only outside 1e-3…1e4. Now
   `<sup>` markup; the dead table is deleted.
3. `⚠` in `doc_report_builder.py` ×2 (fires only when K<sub>u</sub> > 0.65, or when the bore
   overfills) and ×7 in `generate_full_report.py`. Replaced with `✗`, the ballot X those files
   already use as the negative counterpart of `✓`.
4. `≪` in the Ch6 prose. Replaced with `&lt;&lt;`.

**Two guards, because neither is sufficient alone:**
- `test_regression.py::test_the_built_report_has_no_black_squares` — asks the shipping document.
  Zero false positives, but it read **zero for months while the two footers were broken**, because
  it only sees the branches one design takes.
- `tests/test_no_black_squares.py` — scans the source of every report builder, which reaches the
  conditional branches. It self-validates the detector against both the known-bad and the
  known-good characters first, so it cannot rot into flagging working text.

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

### B13. Unrenderable sub/superscript characters beyond the two fixed in B12  `CLOSED at C252`
Folded into B12 — same subject, same fix, same two guards. Every character on the list below was
re-tested by rendering at C252: the `₀` and the `⁰⁴⁵⁶⁷⁸⁹⁻` set are real black squares and are
gone; `&#8486;` (OHM SIGN) is **not** — it renders correctly and was a false positive of the old
predicate. The `●` matplotlib false positive this entry warned about is correctly ignored by the
new detector, which tests the character rather than guessing from its codepoint.

<details><summary>Original list (kept — every entry was verified, not assumed)</summary>

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

</details>

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

### B10. Duplicate table numbers  `THE GENUINE ONE FIXED at C252`
The one case where both tables actually render is fixed: §9.7 was **both** "Selected Part —
Recalculated Design Values" and "Selected Part — Gate-by-Gate Verdict", so the report contained two
different Table 9.7 and a review comment citing "Table 9.7" was ambiguous. They are **9.7a / 9.7b**
now. No prose referenced "Table 9.7", so nothing else had to move. The `eq_box(..., number="9.7")`
in the same section is the EQUATION series — a separate sequence, deliberately left alone.

`tests/test_report_hygiene.py` now fails on any new in-module duplicate, with the surviving if/else
pairs listed explicitly — and a second test fails if one of those listed pairs stops existing, so
the allowlist cannot quietly become a place to hide new duplicates.

<details><summary>Original survey (the remaining kinds, all harmless)</summary>

Found while doing the item-26 numbering sweep. Three kinds, none introduced by that sweep:
- **if/else pairs** — 6.11.6, 6.11.7, 6.11.9, 8.6a, 9.6. Two `data_table` calls share a number but
  only one branch ever renders (Type-II vs Type-III, vendor-DB present vs absent). Harmless.
- **cross-module** — 6.2.1, 6.3.1, 6.3.2, 6.4.1, 6.6.1, 6.7.1, 6.9.1. `doc_report_builder`'s Ch6
  PLACEHOLDER reuses numbers that `report_steps1_8` / `report_step9` also use. The placeholder is
  skipped in the combined report (`include_ch6=False`), so only one renders there — but a
  Ch1–5-only build would show both.
- **genuine** — **9.7** ("Selected Part — Recalculated Design Values" and "Selected Part —
  Gate-by-Gate Verdict" in `report_inputprotection.py`). Both render. Should become 9.7a / 9.7b.

</details>

### B11. Dangling table cross-references in prose
A scan for `Table X.Y` mentions with no matching `data_table` call found ~17, e.g. 3.2.4, 3.4.1,
5.1, 5.2, 14.1, 14.6, 14.7, 3.2.2b, 3.2.4a. Pre-existing (verified against HEAD — the numbering
sweep created none). Some may point at equations or figures rather than tables; each needs
checking individually before any renumbering work touches them.

---

### B16. SiC Q_c is not gated to CCM, the silicon recovery term is  `DONE at C253`
`pfc_loss_model.loss()` applies the silicon branch as `fsw*avg(rr_fet_frac*E_rec*rr_active)` — the
`rr_active` mask is zero wherever the point is in DCM. The SiC branch is (re-read 2026-08-23; the
formula this entry used to quote predates the C-j grading term)

    P_rr_to_fet = fsw*Vo*dio.qc*dio.k_qc / (2.0 - min(dio.cj_grading, 0.95))

— still a scalar with no angle dimension and **no mask**, so the junction charge is charged at full
V_OUT on every cycle including the DCM portion. The claim holds; only the constant changed. In DCM the drain has
already resonated below V_OUT before turn-on, so that share is overstated.

Measured on the reference design: DCM appears **only at 264 Vac and only for ~10 % of the
half-cycle**, where the SiC term is ~1.3 W — so the error is under 0.2 W, at an operating point that
is not the thermal worst case (90 Vac is). Found during C210; the report prose was corrected to
describe what the code does rather than claim CCM-gating for both branches.

**DONE at C253.** The branch is now per-angle. For `C_j(v) = C0·v^-m` the stored charge scales as
`(v/Vo)^(1-m)`, so the dissipated energy `v·Q_c(v)/(2-m)` scales as `(v/Vo)^(2-m)`; in CCM
`v_pre = V_OUT` and the expression is *identical* to the old scalar, in DCM it takes the settled
switch-node voltage.

Settling to `v` is deliberately the conservative choice — an undamped node reaches `2v - V_OUT` at
the first valley, lower still and often clamped at zero — so the correction is understated rather
than resting on a ringing phase the model does not track.

**Measured:** −0.033 W, at 264 Vac only, which independently confirms the entry's claim that DCM
appears nowhere else (`DCM_% = 0` at all eight other points, 6 % at 264 Vac). The drop is almost
exactly the DCM fraction, because DCM occurs near the zero crossings where `v` is small and there
is barely any charge to dump. Guarded both ways by `tests/test_ch7_loss_refinements.py`: a fully
CCM point must equal the full-V_OUT scalar to 1e-9, and a DCM point must fall, but by no more than
its DCM fraction.

### B17. Diode V_F is evaluated at the mid-current, not across the ripple triangle  `DONE at C253`
`pfc_loss_model.loss()` computes diode conduction as `vf(i_d_repr)*i_d_density + rd*ms_dio`, where
`i_d_repr` is the mid-value of the conducting current. **Re-verified 2026-08-23** at
`pfc_loss_model.py:359` — `P_cond_dio = avg(dio.vf(i_d_repr, Tj_dio)*i_d_density + dio.rd*ms_dio)`
with `i_d_repr[ccm] = i_ch[ccm]`. Accurate as written. The duty gating and the ripple's contribution
to the mean square are both correct (`ms_dio = (i_ch^2 + di^2/12)*(1-d)`), so what is missed is only
the CURVATURE of V_F(i) across the ripple band — the linear part is already carried by `rd`.

Both external diode reviews (2026-08-07) recommend sampling V_F at N points across the off-time
current ramp instead. That is a genuine refinement, second-order here: V_F is concave, so evaluating
at the mean understates slightly, and the error grows with ripple depth (dI_L reaches ~12 A on a
~16 A peak at low line).

**DONE at C253 — and the reason it was deferred had expired.** The entry said the parts seen so far
publish V_F at one current per temperature, so the curve is flat and sampling it returns identical
values. That stopped being true: the reference SiC diode carries a genuine 3-point curve
(1.05 / 1.35 / 1.70 V at 1 / 5 / 16 A), and C222 brought real diode datasheets through the
extractor.

Conduction is now integrated across the ramp — `i_off → i_on` in CCM, `Ip → 0` in DCM — by
`vf_i_ramp()`. `r_d·ms_dio` already carried the linear part, so only the curve term moved.

**Two things worth recording.**

*The safety property.* The mean of a linear ramp is its mid-value, so a single-point forward curve
reproduces the old number exactly. Every catalogue part is in that state, and none of their reports
move. Asserted directly.

*The sign is the opposite of what the entry predicted.* It reasoned "V_F is concave, so evaluating
at the mean understates slightly" — but the integrand is `V_F(i)·i`, whose curvature runs the other
way. Measured: diode conduction **rises** 0.020–0.066 W across the sweep. Conservative direction,
but not the predicted one.

*A quadrature bug found on the way.* The first implementation averaged `linspace(0, 1, N)`, which
weights both endpoints fully and is not a quadrature rule — 0.7 % biased. Midpoint sampling fixed
it and preserves the flat-curve identity. N = 17 against a 4097-point reference: N=9 is 0.043 %
out (~5 mW, a tenth of the effect being modelled), N=17 is 0.012 %, N=33 is 0.003 % and agrees with
N=17 to 0.1 mW. N=17 costs 1 ms on the full sweep.

Net on the system: worst-case P_SEMI 65.5616 → 65.6022 W (+0.06 %), max ΔTj 0.056 °C. No verdict
changes.

### B18. The bridge rectifier has no leakage term at all  `DONE at C253`
`Bridge` (pfc_loss_model.py) has no `irev_curve` and no leakage field of any kind, while `Diode` and
`Mosfet` both do. So `I_rev_vs_Tj` is declared for the two diode classes only, and a bridge
datasheet's reverse current has nowhere to go — the `diodes_inc_rectifier` template used to map `IR`
onto that diode-only key, where the value parsed and was then silently dropped (removed at C211).

**Magnitude: ~16 mW** (400 V bus x ~10 uA x 4 diodes), which is why nobody noticed. It is not worth
a model on its own; it becomes worth having if a bridge is ever run hot enough for leakage to matter,
or if the reverse-recovery placeholder in `Bridge.loss()` is ever made real.

**DONE at C253 — and it was THREE halves, not the two the entry asked for.** `Bridge` has an
`irev_curve` field, `I_rev_vs_Tj` is declared for `bridge_rectifier`, and `audit_device_classes()`
is clean — but with only those two in place every check still passed while the value went nowhere,
because `_bridge_block` never read the key. That is the C211 defect verbatim, inside the entry
written to fix it.

It surfaced because the negative control in
`test_a_scoped_template_may_only_map_keys_valid_for_its_own_classes` used `IR → I_rev_vs_Tj` as its
example of an *invalid* mapping. B18 made that mapping legitimate, so the control stopped biting
and the test failed — which is how the missing builder half was found. The control now uses
`C_iss`. **A negative control can be invalidated by the very change it polices**, and "declared" is
not "wired".

Verified end to end: a two-point profile yields `irev_curve = [[25, 125], [5e-6, 50e-6]]` and the
engine returns 23.75 mW at 125 °C / 50 µA — the hand figure. A single published point yields
`None` plus a note, because leakage decades with temperature and one point would invent the slope.

**The entry's own magnitude estimate was ~4× high.** It used "400 V bus × ~10 µA × 4 diodes ≈
16 mW", but a bridge's legs block the **line** voltage, not the bus, and only two block at a time.
The correct figure is `2 · mean(|v_line|) · I_R = 2 · (2·Vpk/π) · I_R` — **4.75 mW** at 373 Vpk and
10 µA, matched to 1e-9 by the test against a hand calculation.

Still zero for every catalogue part, because the workbook has no leakage column — the default path
is bit-identical to before the field existed, which is asserted.

**Reported on the page at C254.** C253 left the term counted but invisible, and the entry's own
"done when" had asked for the report to say something where bridge loss is reported. Found by
diffing the designer's two built reports: their bridge datasheet *does* supply an I<sub>R</sub>(T<sub>j</sub>)
table, so the term was live at 17 mW and mentioned nowhere. Section 7.3 now states both states —
the figure and its basis when a curve exists, and an explicit "not modelled for this part, and one
published point cannot become a curve" when it does not. Both branches asserted, because a page
that says neither is indistinguishable from one where the term was forgotten.

### B22. Table 7.2e states no temperature conditions  `CODE` — *designer review comment 3*
The last of the designer's four report-review comments (2026-08-19). Table 7.2e lists every engine
input and where it came from, but **states no conditions at all**, so a reviewer cannot tell whether
R_DS(on) came from a 25 °C table entry or from the Tj curve.

**The data already exists** — profiles carry per-entry `conditions` (`{"T_c": 25.0}`,
`{"V_DS": 400.0}`, `{"V_GS_swing": 18.0}`). Measured across the three real parts: 31 of 58
parameters carry some condition, 14 carry a temperature. So this is surfacing a column, not new
extraction, and it will be honestly patchy.

On the substance: the engine already corrects the two terms that dominate (R_DS(on) via the vs-Tj
curve, V_f integrated at the converged Tj). The charge terms (Q_g, Q_gd, C_iss) are used at their
25 °C values, which is defensible — they are weakly temperature-dependent — but the report never
says so, and that is the real gap.

- **BLOCKED on a designer decision** (asked 2026-08-19, not yet answered): state each value's own
  datasheet condition, normalise everything to one ambient, or both? The design runs at
  Ta = 45–50 °C while the comment mentioned 25/50 °C. C247 settled that the operating ambient is one
  number from the first page, which removes the ambiguity about what "the" ambient means, but not
  the question of what the column should show.
- **Done when:** every row of 7.2e states the condition its value was taken at, or says DATA MISSING,
  and the four table-sourced values keep the "no plot exists" line C231 added.

### B23. Two engines reported different DCM fractions  `FIXED at C263`
**FIXED at C263**, and the cause was not the one recorded below — see the correction.

| V_AC | before | after | magnetics | gap |
|---|---|---|---|---|
| 200 | 8.7 % | **0.0 %** | 0.0 % | exact |
| 220 | 18.3 % | **4.0 %** | 3.3 % | +0.7 |
| 230 | 22.0 % | **11.3 %** | 10.0 % | +1.3 |
| 264 | 29.0 % | **24.3 %** | 22.2 % | +2.1 |

Gaps of up to 15 percentage points are now at most 2.1, and every CCM point agrees exactly. The
residual is sampling resolution — the loss engine interpolates L from ten points while the
magnetics engine evaluates `k_bias(H)` continuously — not a modelling disagreement.

**THE RECORDED CAUSE WAS WRONG.** This entry blamed the loss model's `L_eff` back-out and a
per-channel-instantaneous versus per-phase-average current. Measured at C263: no ripple target is
supplied in this configuration, so `L_eff == L_op` and the back-out never fires; and the two
currents agree to within rounding. Both stated causes were inert.

**The real cause: WHICH inductance, not which current.** `step7_magnetic_calc` has always used a
PER-ANGLE inductance — `Lth = L0_nom · k_bias(H)` at every angle, so as the current falls through
the line cycle the core's permeability recovers and L rises. The loss engine used ONE value per
operating point: the full-load, worst-bias figure, everywhere in the cycle. That overstates the
ripple exactly where the current is small, which is exactly where DCM is decided.

**The fix.** `Spec.L_bias_curve` — inductance against instantaneous channel current — read off the
approved design's own `L_vs_Vin_table` (each row is the as-built L at that point's crest current),
so it is a hand-off rather than a second bias model. When absent the engine keeps its previous
single-L behaviour exactly, and a stated ripple target still wins (re-biasing an L that was itself
backed out of the requested ripple would be circular; asserted).

**The zero-bias anchor is not cosmetic.** `np.interp` clamps below the lowest sampled current, and
DCM happens near the zero crossings where the current is smallest — so the clamped region is
precisely the one that decides the answer. Anchoring at `L0_nom_uH` (k_bias → 1 at zero bias) took
220 Vac from 13.0 % to 4.0 %. Without it the fix was less than half of one.

**Chapter 7's numbers moved**, as the old entry warned they would: worst-case semiconductor loss
66.320 → 66.114 W (−0.21 W, −0.3 %), every point falling, because the model had been overstating
ripple where the current is low. Bounded by a test so the size and sign are recorded rather than
rediscovered.

`tests/test_dcm_cross_engine.py` holds the acceptance test: the two engines must stay within
3 percentage points, and no point may disagree about *whether* it runs discontinuous.

<details><summary>Original entry (superseded — kept for the misdiagnosis)</summary>


**Found at C259** while exporting a per-angle DCM mask for the Design Explorer. The magnetics
engine and the Chapter-7 loss engine both compute how much of the half cycle runs discontinuous,
and they disagree — measured on the reference design with the as-built inductance applied:

| V_AC | magnetics (`step7_magnetic_calc`) | Chapter 7 (`pfc_loss_model`) |
|---|---|---|
| 220 | 3.3 % | 18.3 % |
| 230 | 10.0 % | 22.0 % |
| 264 | 22.2 % | 29.0 % |

Same ordering, same physical story — DCM near the zero crossings at high line, growing with line
voltage — but the numbers are far apart, and at 220 Vac they differ by more than 5x.

**Why, as far as it is currently understood.** The two apply the same *criterion* (`i < Δi/2`) to
different *quantities*:

- magnetics uses the per-phase **average** current and the as-built per-angle inductance;
- the loss model uses a per-channel **instantaneous** current and an `L_eff` **backed out of the
  requested peak ripple** (`L_eff = Vpk*d_pk/(di_peak_req*fsw)`), not the bias curve directly.

Each is self-consistent, so neither is obviously wrong, and no report figure is currently known to
be affected — DCM enters the loss model only through `rr_active` (silicon recovery, masked in DCM)
and, since C253, the SiC Q_c term.

**Why it matters now.** The Design Explorer shades the angles the *magnetics* engine flags. If a
later scene quotes Chapter 7's `DCM_%` beside that shading, the page would present two engines as
one number — the exact class of defect C255 was. The waveform payload therefore declares its basis
in `notes.dcm_basis`, and a test asserts that declaration exists.

- **Done when:** either the two are reconciled onto one definition of the operating current and
  inductance, or the difference is explained and both figures are labelled with their basis
  wherever they appear.
- **Do NOT** simply make one call the other. The loss model's `L_eff` back-out exists so a designer
  can specify a ripple target; removing it to share the magnetics inductance would change Chapter 7
  loss numbers, which needs its own verification pass.

</details>


### B24. No guard on the FAN9672 legal switching-frequency bands  `CODE`
Found while fixing the oscillator equation at C268; **flagged, not fixed** — the designer asked for
the thirteen equation sites and the hardcoded DECISION line, and this is a separate behaviour.

The part programs f_OSC in **two** bands, 18–40 kHz and 55–75 kHz, and the datasheet (p.14) states
plainly that "setting frequency between 40 kHz and 55 kHz is not allowed in FAN9672". Note 4 (p.10)
bounds the RI resistor at 53.3 k–10.7 kΩ. Nothing in the engine, the GUI or the report rejects a
target f_SW in the forbidden gap or outside 18–75 kHz: the arithmetic is happy to return an R_RI
for 47 kHz, and every downstream chapter would then be designed at a frequency the controller
cannot produce. Section 6.4's prose now names both bands (C268), but prose is not a gate.

Worth pairing with a check that the SELECTED E96 value keeps the achieved frequency inside the
band — snapping to the nearest standard value can walk a legal target across a boundary, which is
most likely near 40 and 55 kHz where the design would look fine and the part would not run.

### B25. Protection resistors snap nearest-in-log, not conservatively  `DECISION` — *designer accepted 4.12 kΩ*
**Designer verified the report on 2026-08-27 and accepted the values as they stand:** R_ILIMIT
14.7 kΩ, R_ILIMIT2 4.12 kΩ, C_ILIMIT 22 nF, C_ILIMIT2 75 nF. So nearest-in-log rounding is accepted
in practice and this is no longer blocking anything. Kept open only as a policy question — if
protection resistors should ever snap DOWN as a rule, this is the entry to act on. Close it if the
designer confirms they do not want the change.
Raised at C270. R_ILIMIT2's raw value is 4076.8 Ω; `_nearest_e96` picks **4.12 kΩ** (log-nearest),
the designer computed **4.02 kΩ** — adjacent E96 steps, 1.4 % apart, either side of the raw value.

For an ordinary component nearest-in-log is right. For a **protection threshold** the two directions
are not equivalent: R_ILIMIT/R_ILIMIT2 scale the trip level, so rounding **down** trips slightly
earlier (more margin against the part) and rounding **up** allows a slightly higher peak before the
limit acts. A designer may reasonably want protection resistors to snap down as policy.

**Not changed unilaterally** — it would move every protection resistor in Chapter 6, and it is a
design-policy call rather than a defect. Needs the designer's decision.

### B26. Current-loop components changed at the same crossover — CAUSE STILL UNKNOWN  `CODE`
**The R_CS hypothesis below is WRONG and is kept only as a record of a ruled-out cause.** The
designer confirmed R_CS was **12 mΩ in both runs**, so a silent reconcile did not move it and the
loop plant did not change that way. Two hypotheses have now failed on this symptom (R_RI, then
R_CS); do not offer a third without measuring.

**What is established.** R_RI is not in the current loop: `TiUnc = plantI(L, Vout, Co, r_L, r_C) ×
Hcs(rf, cf) × R_CS/V_ramp`, `V_ramp` is a constant, `rf`/`cf` are designer DOM fields, the optimizer
searches against the TARGET f_SW, and the achieved f_SW is display-only. R_CS is unchanged. So the
remaining candidates are the other plant terms — **Lφ, C_out, r_L, r_C** — or `rf`/`cf`, or the
optimizer's own search bounds.

**Lφ is the one to check first.** `ControlDesign` builds `params.lphi_uH` from
`tsi.confirmed_L_uH_sel ?? tsi.confirmed_L_uH ?? L_target_uH ?? 235`, whereas the REPORT designs
Chapter 6 at the **minimum as-built** Lφ from `L_vs_Vin_table`. Those are different quantities, and
`R_IC ∝ 1/|T_u|` scales with Lφ. This was not touched by C268–C270, so it does not explain a change
*between two runs* on its own — but it does mean the GUI and report can design different loops, and
it should be resolved before chasing anything subtler.

**What to ask for:** the before/after R_IC, C1, C2 and f_ci, plus Lφ shown on Screen 1. Without
those this is guesswork, and guesswork has already been wrong twice here.

*Original (ruled out):* C269 made Screen 2 reconcile a rehydrated
selection against the currently-offered options, which is right when the stored value is invalid —
but it happens **silently**, and one of those values is R_CS.

R_CS is not cosmetic: `R_IC ∝ 1/R_CS` in the current loop, so C1/C2 move inversely. For this design
the valid band is 11.54–12.36 mΩ, i.e. **12 mΩ is the only option** — a stored 15 mΩ is reset to 12,
giving a 25 % larger R_IC and 20 % smaller caps *at the same crossover*. The designer reported
exactly that symptom ("same f_ci, different current-loop components") and asked whether the R_RI fix
caused it. It did not — R_RI appears nowhere in the loop (verified: `TiUnc = plantI(L, Vout, Co,
r_L, r_C) × Hcs(rf, cf) × R_CS/V_ramp`; the achieved f_SW is display-only).

**Action once confirmed:** a reconcile that changes R_CS (or R_LS) must announce itself — the caps
already show an amber `calc` note, and a reset that alters the loop deserves at least as much. Do
not implement before the designer confirms R_CS actually changed between their two runs; the cause
is a hypothesis, and it is the kind that has been wrong before (see B23).

### B27. `run-sizing` substitutes a different wire when a designation does not match  `CLOSED at C272`
**Closed on the designer's instruction — "make it raise instead of substituting."** A named wire is
now either used or refused, never quietly swapped. Three behaviours, verified against the real
endpoint:

| request | behaviour |
|---|---|
| `None` / empty | auto-pick the best available (**unchanged** — this is the documented "agent sweeps all AWG" path, and it ran through the same fallback) |
| a name the sweep filtered out | **honoured** — re-resolved against the unfiltered catalog |
| a name in no catalog | **400**, naming what is available |

**The middle row is why this was not a one-line change.** The picker lists the catalog with
`min_cu_fraction=0` ("show all wires so designer can choose from full table") while the sweep
filters at 0.10 and queries at `J_max`. At 20 A per conductor four wires are visible and clickable
yet absent from the sweep list (`0.05x100`, `0.05x200`, `0.071x100`, `0.1x50`). A blunt raise would
have 400'd on a legitimate pick — a different way of not doing what the designer asked. An explicit
choice is not the sweep's to veto; the under-sizing still shows through `current_ok=False`.

Guard: `tests/test_wire_designation_is_honoured.py`, including a test that the picker/sweep
divergence still exists — if the two lists ever agree, the unfiltered re-resolve becomes dead code
and the test says so rather than silently guarding nothing.

*Original entry:* Found at C271 while collapsing the vendor-equivalent litz rows. `/mode-b/step7/run-sizing` resolves
the selected wire by designation and, on no match, does **not** raise — it takes `wire_opts[0]`, the
largest wire in the list:

```python
wire = next((w for w in wire_opts if w["designation"] == req.wire_designation), None)
if wire is None and wire_opts:
    wire = wire_opts[0]        # no error, no warning
```

So any request naming a wire the catalog no longer offers is silently rewound onto a different one.
C271 made the vendor codes resolvable so the collapse could not trigger this, and added a test for
the substitution — but the fallback itself is untouched and still live for every other cause of a
miss (a renamed entry, a filtered-out wire, a typo from an older saved design).

**Options:** raise a 400 like the `wire is None` branch two lines below already does; or keep the
fallback but return a flag the GUI can surface ("requested X, using Y"). The second is safer for
existing designs. Either way the designer should never learn about it from a build.

Not fixed at C271 because it predates that work, changes behaviour for every wire type, and is a
decision about how strict the endpoint should be.

### B28. `run-sizing` returns 200 with an empty candidate list and no reason  `CLOSED at C273`
Found at C272 by the endpoint test added for B27, not by the change itself. Closed at C273.

An explicit wire pick that no core can wind came back **`status: "ok"`, `cores_passed: 0`,
`top_5: []`** — measured with `0.05x100` (0.196 mm² of copper) on the standard 3.6 kW design:
424 cores evaluated, 0 passed. Nothing in the response distinguished it from a successful run.

**Correction to this entry as first written:** it claimed the GUI "renders an empty table with
nothing saying why". It does not — `Step7Wizard.runSizing` shows a hardcoded *"No suitable core
found — try larger height or different material"*. That is worse than silence here, because the
advice is wrong: the binding gate was the WIRE, and no height and no material would have helped.
The entry was written from the API response without opening the component.

**The fix.** `DesignResult` now carries `fail_gates` alongside `fail_reasons` — one stable gate
name per reason, appended through a single `res.fail(gate, reason)` method so the two cannot
drift (nine call sites; one that forgot its gate would under-count exactly the gate nobody
thought about). run-sizing aggregates them over the whole sweep, counting each gate **once per
core**, and returns `status: "no_passing_cores"` with `no_pass_reason` and `fail_gate_counts`.
The GUI prefers that reason over its hardcoded string.

Measured on the `0.05x100` case:

> All 424 cores evaluated, none passed. Most common gate: thermal (424 of 424) — the temperature
> rise exceeds budget — try a larger core or a larger wire. Also blocking: inductance (189),
> fill (28), winding_fit (23).

**The gate is THERMAL, and that is worth recording.** The test drafted for this asserted a
*winding* gate — "a 0.196 mm² wire must fail on fill" — and the engine said thermal. The engine
was right: a wire that thin fits any window trivially and then runs at J = 51 A/mm², so it cooks.
424 of 424 is unanimous, which is what makes the diagnosis worth printing at all.

Also closed here: the response's `"wire"` field echoes `req.wire_designation` back verbatim, so
on the auto-pick path it read `null` while a real wire was chosen. `wire_used` now reports what
was actually wound. `"wire"` keeps its meaning ("what was asked for") because saved designs and
the GUI already read it.

Guard: `tests/test_no_passing_cores_is_reported.py`, verified to FAIL against the pre-C273
`status: "ok"` by injecting it.

### B19. M7 — a RASTER curve tracer (the last M7 gap)  `CLOSED at C277`
**The last M7 gap is closed.** The tracer (C276) is now reachable from the Curves tab and a
confirmed raster curve reaches the engine by the same road a vector one does.

**C276 — the tracer.** `raster_curve.py`. On Fig. 9.1 of the Toshiba TRS12E65H it separates four
curves and agrees with the part's own table to **0.25 %** (1.203 V against a tabulated 1.2 V at
12 A, 25 °C) and **0.5 %** (1.353 V against 1.36 V at 150 °C). Two anchors on two DIFFERENT
curves, which no single scale error can satisfy at once; a test asserts they are not the same
curve, so a loose tolerance cannot pass by matching one curve to both.

The axis ranges come from the designer because on these pages the tick labels are pixels — OCR
would be a system dependency failing exactly as C224 warned, and gridline counting cannot tell
0..2 from 0..20. **Without axes it refuses**, so `curve_extract` reading nothing from this file
remains the default and the original refusal test keeps its meaning.

**C277 — the wiring.** Two endpoints (`/datasheet/raster-figures` lists the bitmaps with their
captions, `/datasheet/raster-digitise` traces one against typed-in axes), the Curves-tab panel that
appears only when a datasheet has such figures, and a proposal returned in the **ordinary
`DsFigureProposal` shape** — so the existing accept UI renders it and the existing
`figure-confirm` stores it. A parallel confirm path was avoided deliberately: a second place to
accept a curve is where the two drift apart.

Guarded by `TestTheRasterCurvesTabSequence` in `tests/test_api_flows.py`, which drives the real
endpoints in the order the screen calls them — upload → list → digitise → accept → read it back
out of the profile. **That sequence test is the point.** C215, C224 and C225 each shipped curve
work that passed every unit test and was dead in the GUI, which is why that file exists; the raster
path got its sequence test in the same commit as its wiring.

**Two real defects surfaced by writing that flow**, neither introduced by it:
  * **the curves came out x-DESCENDING.** `CX.value_at` tests `x < xs[0] or x > xs[-1]` and so
    returns None for a descending curve — the figure reported "no digitised curve covers x = 1.2"
    while holding a curve passing exactly through it. Curve dicts in that module are implicitly
    x-ascending; raster curves now arrive that way.
  * **a temperature stated as `Ta` was read as 25 °C** — see **B29**, which is the part of this
    that is NOT fixed.

### B29. A measurement's temperature may be stated as T_j, T_c or T_amb  `CLOSED at C278`
Found at C277 by the B19 end-to-end flow — the Toshiba TRS12E65H is the first datasheet on file to
state a hot condition as **Ta = 150**. It extracts and stores correctly as
`{"I_F": 12.0, "T_amb": 150.0}`, and every consumer asked for `conditions["T_j"]`, got nothing, and
filed a 150 °C measurement as a 25 °C one. C277 fixed the two V_F sites; C278 did the family.

**Converted to `measurement_temperature()` — vendor-stated conditions, where the vendor chooses
how to say it:**

| site | what it feeds |
|---|---|
| `idss` (`I_DSS_vs_Tj`) | MOSFET leakage vs temperature — **fewer than two points leaves the curve unbuilt and the blocking-loss term back at zero**, so dropping a point for want of a key is not neutral |
| `_hot_entry` | the hot R_DS(on) entry |
| `irev`, `irev_br` | diode and bridge reverse leakage vs temperature |
| `_qrr_tempco` | Q_rr's temperature coefficient |
| `tj_test` | the switching-energy test point the analytic model is re-run at |

**Left reading `T_j`, deliberately — 4 sites**, the digitised-curve conditions on the diode and
bridge paths (`dig_vf`, `dig_hot`, twice each). Those conditions are **ours, not the vendor's**:
`confirm_figure` writes them from the Curves tab, which offers a single T_j field, so no other key
can be there. Each carries a `T_j DELIBERATELY` comment, and a test asserts all four still do —
a bare `get("T_j")` is indistinguishable from the defect it survived.

**A third case needed its own treatment.** The Q_rr note *prints* the condition, and rendering an
ambient as "T_j" is a false statement about the measurement that reads exactly like a true one. It
goes through `measurement_temperature_named()`, which returns the value **and the key**, so the
note says `T_amb = 150 degC` when that is what the datasheet said.

Guard: `tests/test_measurement_temperature.py` (14 tests), including the real-part regression —
the Toshiba's cold set must hold 1.0 and 1.2 V and **not** 1.36 V. Verified to FAIL against the
injected pre-C277 behaviour (5 tests fail, the real-part one among them), then restored.

**Two things worth keeping from how this was built:**
* **The count is the guard, not a list.** `grep -c 'get("T_j")' datasheet_flow.py` is **5** at C278
  — the 4 deliberate reads plus `measurement_temperature`'s own preferred read. If it rises, a new
  site has joined the family. C2 and C3 each grew a site nobody re-counted; a list goes stale
  exactly when it matters.
* **The first draft of the regression test skipped.** It called `datasheet_extract.extract()`
  directly, which returns no parameters for this file because the vendor templates are applied by
  the *upload* path — so it would have shipped permanently green and covering nothing. It drives
  the real upload endpoint instead.

**Still untested: the `T_c` middle branch against a real file.** No datasheet on file states a
condition that way, so it is covered only by unit tests. Not a gap worth holding the entry open
for — but if a part ever arrives stating `Tc`, that is the one to check.

### B30. R_LS cannot emulate the design's own inductance at the reference R_CS  `DECISION` — *half answered at C281*
Raised by C279, which rebuilt Section 6.8.2 after the designer asked why the report calculated
35.846 kΩ and selected 47 kΩ. The basis is fixed — R_LS is an emulator coefficient and now takes
the **median** per-point full-load inductance rather than the loop's minimum — but two things it
exposed are decisions, not calculations.

**1. The band binds on the reference design.** The median implies R_LS = 88.3 kΩ against a
12–87 kΩ limit, so the selection clamps to 87 kΩ and emulates 308.2 µH instead of the 312.9 µH
asked for. That is a 1.5 % miss and harmless — but it is the *shunt* that decides it:
R_LS ∝ L/(R_CS·ratio), so a smaller R_CS buys headroom. **Five of the nine operating points imply
an R_LS outside the band entirely** at the reference shunt. Worth deciding whether R_CS selection
(Section 6.6) should carry an R_LS-headroom check, or whether clamping with the value stated is
enough. Today it clamps and says so.

**2. ~~The central estimator~~ — ANSWERED at C281: the designer chose the ARITHMETIC MEAN.**
123.19 µH on the reference design. The report now prints the summation term by term rather than
naming a statistic, because naming one ("median of 9 … (101.6–139.3 µH)") was read as a midrange,
(101.6+139.3)/2 = 120.45 — a different number reached from the same words. Original reasoning: AN4165-D assumes a
constant inductance ("inductance of 100 µH is selected") because it is written for a linear
inductor; a powder core swings ~5:1 inside one line cycle, so *something* has to stand in for it
and the app note does not say what. The median of the per-point full-load values is defensible and
deterministic, and the residual error falls where it does least harm — but a current-weighted mean,
or the inductance at the mains the unit will actually run on, are equally arguable. **Confirm the
rule or name a different one.**

- **Done when:** ~~the designer confirms the estimator~~ (done at C281 — arithmetic mean) and
  says whether R_CS selection should be made aware of the R_LS band. **Only the R_CS-headroom
  half is still open.**
- **Do not** re-point R_LS at `lphi_uH`. That is the loop's minimum-inductance basis and
  Section 6.10.14's verification depends on it; `tests/test_rls_one_value.py` asserts the two stay
  different on purpose.

### B31. Parts uploaded before the device-identity gate were never checked  `CODE`
C282 added a gate that refuses a datasheet describing a different component from the tab it was
uploaded under — the designer had filed a diode datasheet under Bridge rectifier and the engine
extracted, stored and costed it. **The gate protects new uploads only.** Everything already in the
parts store predates it, including the mis-filed part that produced the finding.

`device_identity.check_declared()` takes the stored PDF and the profile's `device_class`, so the
audit is a loop over `parts_store`, not new analysis. What needs deciding is what to DO with a hit:
a stored profile may already be referenced by a confirmed design, so silently deleting it would
change a design under the designer. Reporting the mismatch and letting them re-upload matches how
C282's refusal behaves.

- **Done when:** a one-shot audit reports every stored part whose datasheet contradicts its
  recorded kind, and the GUI marks such a part as needing re-upload rather than quietly using it.
- **Note** the audit inherits the gate's limits: `no_evidence` is not a mismatch (a scanned
  datasheet has no text to search), so only true contradictions should be reported or the report
  will be mostly noise.

### C1. Control Design page redesign
Agreed 7-screen confirm-gated flow for Chapter 6, plus S7 download/approve → semiconductors.
Plan in `PFC_GUI_Cleanup_Plan.docx`. Discussed and agreed, **not implemented**.

### C2. Report download fails intermittently — CLOSED PENDING RECURRENCE (designer, 2026-08-23)
**Closed by the designer on evidence, not by a code argument.** Three downloads succeeded on
2026-08-23 with no failures reported, on the paths that used to fail:

| File | Time | Which path |
|---|---|---|
| `PFC_Report_pfc-FUll report Latest.pdf` (15.9 MB) | 14:13 | full combined report — the ~111 s generate, the case where user-activation expiry would bite |
| `PFC_Ch7_Semiconductor_Loss (1).pdf` (1.3 MB) | 16:04 | **the standalone Chapter 7 — the 8th site, genuinely broken until C251** |
| `PFC_Report_pfc-1787525546065_Steps1_17.pdf` (14.7 MB) | 16:10 | full combined report again |

The Chapter-7 one is the meaningful result: until C251 that path revoked the object URL on the
statement after `click()` with the anchor never in the document, on the largest single-chapter PDF
the GUI emits. It now saves.

**Why "pending recurrence" and not simply closed.** The original symptom was *intermittent*, and
three successes cannot prove absence of an intermittent fault. The second mechanism in this entry —
transient user activation expiring across the long generate — was never disproved, only
un-observed, and its fix (**the visible fallback link, proposal 1**) remains unbuilt and deferred.

- **If it recurs:** do not re-diagnose from scratch. Build the fallback link. It is robust whatever
  the root cause, `downloadBlob` already returns the object URL for it, and it needs UI on the six
  report screens plus the Chapter-7 button.
- Guarded against regression by `tests/test_downloads_go_through_helper.py`, which counts the
  download sites from the tree rather than checking a list — a list is what went stale and let the
  8th site through.

<details><summary>Full diagnosis (retained — the symptom leaves no trace to re-derive)</summary>

**Status 2026-08-22.** Re-audited on the designer's question "is this still open?", and it was —
not because the fix had regressed, but because the fix was never exclusive. The seven screens
migrated to `src/api/download.ts` are all still correct (10-minute hold on both the object URL and
the anchor; no unguarded `project_id`). But `downloadCh7` in `SemiconductorSelection.tsx`, written
*after* that migration, open-coded the anchor dance again and revoked the URL on the statement
straight after `click()` — a worse version of the original 150 ms race, with the anchor never
placed in the document, on the largest single-chapter PDF the GUI emits. Now routed through
`downloadBlob` like the rest.

**The lesson is about the log, not the code.** C2 read "fixed, awaiting designer confirmation" for
three weeks, so nobody re-counted the call sites, and a new download button was exactly where the
knowledge was missing. `tests/test_downloads_go_through_helper.py` now fails on any `.tsx` that
pairs `createObjectURL` with `.download`/`click()` outside the helper, and separately asserts the
helper still defers both the revoke and the anchor removal. Verified by reintroducing the exact
pattern (it fails) and removing it (it passes).

**This does NOT close C2, and the header should not be read as saying so.** The revoke race is one
of two mechanisms in this entry. The second — transient user activation expiring during the ~111 s
generate, in the ROOT-CAUSE ANALYSIS section below — is untouched by any of this, and the fix for
it (**proposal 1, the visible fallback link**) was deferred by the designer on 2026-08-01 and has
still not been built. If the failure is activation expiry, C251 changes nothing about it.

**So the order is:** (a) designer re-runs the reports, especially the standalone Chapter 7 download,
and reports whether any still finish with no file; (b) if they do, build the fallback link — it is
robust whatever the root cause, `downloadBlob` already returns the URL for it, and it needs UI in
the six screens plus the Ch7 button. The diagnosis below is retained in full because the symptom
leaves no trace to re-derive.


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

**Two silent-failure mechanisms found and fixed** (7 sites then, the 8th at C251 — all now via
`src/api/download.ts`):
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

</details>

### C3. Studio iframes sandboxed without `allow-downloads`  `FIXED at C252`
**There were three, not two.** The entry named `ReviewMagnetics` and `CapacitorSimAgent`;
`SimulationAgent.tsx` was written after C3 was logged and nobody re-counted the sites — the
identical failure to C2's 8th download path, on the same day, found by the same kind of scan.

All three now carry `allow-downloads`. `ControlDesign.tsx` already did.

Guarded by `tests/test_downloads_go_through_helper.py::test_every_studio_iframe_allows_downloads`,
which counts the sites rather than trusting a list — because a written-down list of offenders is
precisely what went stale here. Any download initiated inside a sandboxed frame without that flag
is blocked by the browser with no console error and no visible failure: the export button simply
does nothing.

---

### C5. The standalone Chapter 7 and the combined report disagreed — flat L vs the bias curve  `FIXED at C255`
**Found by the designer, 2026-08-23,** comparing Table 7.1 between the two documents they had just
downloaded. The L<sub>φ</sub> column reads per-point in one and a constant in the other:

| | 90 V | 110 V | 120 V | 132 V | 180 V |
|---|---|---|---|---|---|
| combined report | 102 | 120 | 128 | 136 | 111 µH |
| standalone Ch 7 | **127** | **127** | **127** | **127** | **127 µH** |

**It is not cosmetic — it moves the loss numbers.** ΔI<sub>L,pp</sub> at 90 V is 12.115 A vs
9.689 A, which changes the RMS currents and therefore conduction and switching loss. Worst-case
semiconductor dissipation is **54.82 W (combined) vs 54.64 W (standalone)**; MOSFET conduction at
90 V differs by 0.15 W. Small, but it is the same chapter reporting two different answers, which is
the class of defect C233/C251/C252 were all about.

**Root cause, exact.** Both endpoints call the same builder, but they do not pass the same inputs:

- `/mode-b/documentation/generate-report` (`main.py:2866`) computes
  `_bias_L_curve(approved_design, L_final, design)` and injects `design["L_phi_curve"]`.
- `/mode-b/semiconductor/report` (`main.py:795`) passes `req.design` straight through. Its request
  model carries no `approved_design`, so there is no curve to inject and the engine falls back to
  the flat `L_phi_uH`.

**The endpoint's own docstring asserts the property this disproves:** *"This is the same builder the
combined report calls, so the two cannot disagree — it is the same chapter, not a second
rendering of it."* Same builder, different inputs. That sentence is why nobody looked.

**Table 7.1's caption also states a basis the standalone build cannot honour** — "ΔI<sub>L,pp</sub>
uses the bias-adjusted per-point inductance L<sub>φ</sub>(V<sub>AC</sub>) from Chapter 3" — when
in that build there is no Chapter 3 and L is flat.

**Fix (scoped, not started).** The GUI already has the data: `SemiconductorSelection.tsx` holds
`approvedInductorDesign` and already sends it on three other calls (lines 367, 648, 681).
1. Frontend: include `approved_design` in the `semiconductorReport` request.
2. Backend: `/mode-b/semiconductor/report` injects `L_phi_curve` exactly as the combined endpoint
   does, from the same `_bias_L_curve` helper — one code path, not a copy.
3. When no approved inductor is available (the part-screening case, before Step 7 is approved), the
   report must SAY the inductance is a flat nominal rather than printing the Chapter-3 caption.
4. Delete or correct the docstring's "cannot disagree" claim.

**FIXED at C255.** `_apply_asbuilt_L` already existed and was already called from three
endpoints — including `/semiconductor/calculate`, so the GUI and the combined report had agreed all
along. The standalone report endpoint was the one path that never called it, because its request
model had no `approved_design` to call it with; and on the frontend `downloadCh7` copied six fields
by name out of `body()` and so dropped the seventh, which `body()` carries with a comment saying it
exists to prevent exactly this. **Two stale lists, one at each end of the same request.**

Verified: Table 7.1's L<sub>φ</sub> column is now identical in both documents at all nine points —
`134 146 150 154 130 137 142 145 150 µH`. With no approved inductor the standalone build prints a
flat nominal *and says so in bold*, instead of repeating the Chapter-3 caption over a basis that is
not in force.

- **Superseded done-when:** Table 7.1 and every loss table match row for row between the two documents for the
  same design, asserted by a test that builds both and diffs them — the check that would have
  caught this, and which no existing test performs (`test_ch7_three_way_parity` builds only the
  standalone one).

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

### D1. Hot restart — DECISION-REQUIRED, not BLOCKED  `SETTLED` *(instance of D0b)*
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

### D4. Inductor copper: SA single-node vs two-node winding temperature  `DECISION`
Raised by C248 and deliberately not taken. Copper loss is priced at the **SA single-node**
temperature (92.8 °C at a 50 °C ambient) — the same temperature the convergence loop and the
`dT_rise` pass/fail criterion use. The finer **two-node** model puts the winding at **84.0 °C** at
the same ambient, and the copper is physically in the winding.

Pricing copper at the winding node would be ~3 % lower again, and arguably more correct. It would
also mean the loss, the thermal convergence loop and the pass/fail criterion **no longer share a
temperature** — three numbers in one chapter on two different thermal models.

- **The decision:** keep one self-consistent model (today), or use the finer node for loss and
  accept the split. Not a defect either way; C248 fixed the real one, which was core and copper
  being on *different* temperatures within the same row.
- **Done when:** the designer picks, and whichever is chosen is stated in Chapter 4 so a reviewer
  knows which node the copper figure belongs to.

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

### E2. Chapter builders can vanish silently — CLOSED at C251, now guarded automatically
`doc_report_builder._ch3` / `_ch4` are called under `if approved_design:` in one try-tolerant
path, so an exception inside `_ch4` dropped BOTH chapters (~90 pages) while the endpoint still
returned HTTP 200 and `ast.parse` stayed clean. The build looked fine; the content was gone.

Cause on 2026-08-01: `_ch4` referenced `Bmax_inner` / `sat_m_inner` / `sat_m`, which are `_ch3`
LOCALS, not module-level. `_ch3` and `_ch4` have separate scopes and each must re-derive what it
needs from `d`.

**CLOSED at C251 — the habit is now three automatic guards.** This entry used to end "run
`python verify_combined_report.py`, because only `main()` asserts the 178-190 page range". Both
halves had gone stale: the bound moved into the suite, and the document grew to ~212 pp when C245
added Chapter 7, so the script this entry recommended printed OUT OF RANGE on a *correct* report.
Fixed at C251 (script bound raised to 205-235, matching the suite). A chapter vanishing under
HTTP 200 is now caught without anyone remembering to look:

| Guard | Catches |
|---|---|
| `test_regression.py::test_page_count_is_full_report` | `205 <= pages <= 235` — the lower bound is sized so one missing chapter fails it |
| `test_chapter3_and_chapter4_agree_on_core_loss` | parses **Table 3.6.1** *and* **Table 4.2** from the built PDF — either chapter going missing fails it, which is precisely the `_ch3`/`_ch4` case below |
| `test_chapter7_is_present` (C245) | Ch7 by name, after it was absent from the harness for many commits |

`verify_combined_report.py` also names Ch3/Ch4/Ch7 in its own checklist now. The scoping trap
itself — `_ch3` and `_ch4` have separate scopes, each must re-derive from `d` — is kept in
SESSION_HANDOFF under the built-PDF trap, where it belongs as standing advice rather than an open
item.

---

## Recently closed (kept briefly for context)

**Closed at C252 (the audit).** Fixes: **A9a** loader accepts `data_source` at either nesting
(66 false load warnings → 0); **B10** §9.7 split into 9.7a/9.7b; **B12/B13** four black-square
defects, including one on every page footer of two reports; **C3** `allow-downloads` on all three
studio iframes. Verified closed by measurement, no code needed: **B2** (Section 4.6.2 renders the
per-V<sub>in</sub> families from `build_view_contract`).

**Entries that were already done and had simply never been moved** — the reason the open count read
37 when it was nearer 30:

| Item | Closed by | Evidence re-checked 2026-08-23 |
|---|---|---|
| A11 — no real diode datasheet through the extractor | C222 | 22 tests in `test_diode_real_datasheets.py`; both vendor PDFs on file |
| B4 — status vocabulary | C178 (3e) | `STATUS_WORDS` + `norm_status()` at the render boundary; only the deliberate internal-enum residual remains |
| B5 — bare `onClick={fn}` handlers | C174 | `Btn.onClick` typed with its event parameter, so `strictFunctionTypes` rejects the bare form at compile time |
| B14 — C6 capacitance tolerance, GUI half | C188 | Step-15 ±20 % panel + CapSim corner selector |
| E2 — chapter builders can vanish silently | C251 | page floor 205-235, Ch3-vs-Ch4 parity test, `test_chapter7_is_present` |

- **B21 — the combined-report fixture built no Chapter 7** (C245). `build_combined` sent no
  `semiconductor` payload and `main.py` gates the chapter on it, so every `TestCombinedReport`
  assertion described a 191-page document the designer never receives, and C233's inductor fix had
  no coverage on the shipping path. Fixed with catalogue parts (212 pp); three guards, including
  Table 7.8b == N_ch x Table 4.2 P_tot asserted end to end.
- **B20 — Chapter 3 and Chapter 4 disagreed on peak core loss** (C245). Chapter 3 was not computing
  it: `Pcore_pk * (bac/Bac_val)**2.1`, a power law off one anchor with a fixed exponent instead of
  the material's Steinmetz beta — exact at 90 Vac, −24% at 264 Vac. It now reads the engine's
  per-point value; agreement exact at all nine points.

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
