# Datasheet-first semiconductor parameters — agreed plan

Status: **AGREED, NOT STARTED.** Written 2026-08-05 from the designer review of
`specs/Review/IMZA65R033M2H_MOSFET_Loss_Report_With_Datasheet_Evidence.pdf` and the discussion that
followed. No code has been written. Revision 2 adds Section 5, the loss-model merge.

---

## 1. Why

The MOSFET catalogue is a Digi-Key parametric export. Measured coverage of the fields the loss
engine actually consumes:

| Field the loss model needs | Present in the 1311-part MOSFET DB |
|---|---|
| E_oss, E_on, E_off, Q_gd, R_DS(T_j), Q_oss, R_g, V_GS, C_rss | **0 / 1311 — all nine** |

Everything the engine uses is therefore ESTIMATED from eight columns. On the designer's part
(IMZA65R033M2HXKSA1), measured against the datasheet:

| Parameter | Our block | Datasheet | Error |
|---|---|---|---|
| **E_oss @ 400 V** | **30.0 µJ** (estimated `0.9e-6 / R_ds`) | **8.7 µJ** | **+245 % (3.4×)** |
| Q_gd | 8.5 nC (= 0.25 · Q_g) | 6.2 nC | +37 % |
| R_DS(on) @25 °C | 0.030 Ω | 0.033 Ω typ @ V_GS = 18 V | −9 % |
| Hot R_DS curve | generic SiC 1.4× @125 °C | 33 → 54 mΩ @175 °C | −1 % at 80 °C |
| V_GS drive | 15 V generic (gate loss used 12 V) | 18 V | −17 % |
| R_g | 4.0 Ω placeholder | 1.8 Ω (datasheet test) | no provenance |

The E_oss estimate assumes larger die → lower R_DS(on) → more C_oss, calibrated on silicon
superjunction. This is a **SiC trench** device, whose whole point is far lower output charge for a
given R_DS(on). 4.20 W instead of 1.22 W at 2 channels × 70 kHz — a constant offset at every
operating point, and 28 % of total MOSFET loss at 264 Vac.

### Three code defects found while checking

1. **`vg_drive` is never set from the database.** `to_block` writes `vg` (switching) but not
   `vg_drive` (gate loss), so the dataclass default of 12 V is used. Two field names for one
   physical quantity, one silently defaulted — same defect class as `vdc_min_holdup_v` (C187).
2. **The analytic switching model is unvalidated.** At the datasheet's own test point it gives
   20 µJ against a published 57 µJ. **See Section 5.2 — most of that gap is a definition mismatch,
   not a model error**, which changes what we do about it.
3. **R_g = 4.0 Ω is a placeholder.** Switching energy scales roughly linearly with it, so a ~2×
   lever is set by a guess. `rg_on` / `rg_off` exist in the dataclass; nothing sets them.

### Feasibility — tested, not assumed

Against `specs/Bridge Rectifier Configuration/GBJ40L06.pdf` with PyMuPDF 1.27:

- `find_tables()` recovered the parameter table with symbol / value / unit columns intact.
- **Datasheet curves are VECTOR polylines, not raster images** — 44 candidate paths on the graph
  page, all line primitives. Digitising recovers plotted coordinates, not a pixel estimate.
- Concrete win: extraction found **I_FSM = 420 A and I²t = 732 A²s**. Both are `None` in our bridge
  database today, and they are exactly what leaves the Chapter 8 bridge-surge gate OPEN.

---

## 2. Agreed design

| # | Decision |
|---|---|
| 1 | Excel DB **stays**, but its only remaining job is the plausibility bands + reference distribution. It is no longer a selection tool. |
| 2 | **Top-10 loss ranking screen is removed.** It ranked by a loss computed from the nine parameters the DB does not have. |
| 3 | MOSFET tab → **two sub-tabs**: `Upload datasheet` (first), `Parameters` (review + confirm). |
| 4 | `From database` and `Manual / external` sub-tabs **removed for the MOSFET**. |
| 5 | Before upload the GUI shows only the computed requirement: V_DSS ≥ …, I_D ≥ …. **No MPN shown anywhere before upload.** No R_DS(on) ceiling (designer decision, 2026-08-05). |
| 6 | **No datasheet → no movement.** Gate at GUI approval / report release, NOT inside the engine — so the 192-test suite and `verify_combined_report.py` keep working. |
| 7 | Unreadable or insufficient PDF → GUI asks for a better PDF, no further movement. |
| 8 | Order: **MOSFET → PFC diode → bridge rectifier** → other components later. |
| 9 | **Phase 1 = tables + text. Phase 2 = curves.** Vector digitiser where paths exist; **assisted pixel digitising** for scanned/raster datasheets (designer decision). |
| 10 | **Folder per part** (below). |
| 11 | Existing designs are **re-confirmed against a datasheet**, not grandfathered. |
| 12 | A field the datasheet genuinely lacks → **designer entry WITH provenance** ("designer entered, from Diagram N"), never a silent default. |
| 13 | Switching energy: see Section 5.2. |
| 14 | **Design-sourced parameters are explicit designer inputs**, not defaults: R_g,on / R_g,off, V_GS drive, R_th(c-s), R_th(s-a), T_ambient. No datasheet can supply these. |

### Folder per part

```
parts/<MPN>/
  datasheet.pdf         + sha256, vendor revision, retrieved date
  extracted.json        what the machine read — NEVER overwritten
  confirmed.json        what the designer agreed — this is what the engine uses
  curves/               phase 2, with the axis calibration stored alongside each curve
```

A part number is **not** a unique key to a set of values — vendors revise datasheets silently, so
the hash and revision are part of the identity.

---

## 3. Standing constraints (designer, 2026-08-05)

### C1 — No hardcoded parameters
Every calculation uses parameters from the uploaded datasheet. **The real danger is dataclass
defaults, which fire silently:** `Mosfet` supplies a default for every field (`rdson_25=0.045`,
`qgd=30e-9`, `vpl=5.4`, `vg=12.0`, `rg=1.8`, `vg_drive=12.0`, …). Omit a field and the engine
substitutes rather than complaining. That is precisely how the `vg_drive` = 12 V defect happened.

**Enforcement:** a required-field manifest plus a provenance tag on every engine input, asserted
before calculation. If any consumed field fell through to a default, fail loudly and name it.

### C2 — One name per quantity, end to end
Today one quantity carries three names across four layers (`rdson` → `rdson_25` → `rdson_25`+
`rdson_tj` → "R_DS(on)"), and `vg` / `vg_drive` are two names for one physical quantity — which IS
the defect, not a symptom.

**Enforcement:** a parameter registry — canonical name, unit, source (datasheet | design |
derived), report label, required-for-engine flag — read by extraction, the confirmation screen, the
engine and the report. A mismatch becomes a startup error, not a silent divergence.

### C3 — No repetition of the recent mistakes
Specifically: the same quantity computed in two places (C195/C196/C199), a table on a different
basis from the section around it (C199), and silent defaults (C187, C201).

---

## 4. What we keep vs what we adopt

### Keep — our engine is better than the review report here
- **DCM handling.** The review assumes CCM throughout; near the zero crossing the converter is
  discontinuous and both the RMS and the switching currents change form.
- **Per-angle R_DS(on)** evaluated at the local current, not just the peak.
- **Loop-inductance term** ½·L_s·I_off².
- **Thermal iteration** (80 passes) rather than an asserted T_j per operating point.
- **Correct duty per angle.** The review tabulates D_max = 1.000 at every point including 264 Vac,
  where the crest duty is ~0.05 — a clamp artefact.
- **Per-operating-point L** (`L_curve`), capturing powder-core DC-bias roll-off. The review uses one
  L per line voltage but does not tie it to bias.
- **Gate loss excluded from the FET junction.** `P_gate` is in the efficiency budget but NOT in
  `P_fet_each`, because it is dissipated in the driver and R_g. Already correct; keep it that way.
- **Q_rr modelled from the ACTUALLY SELECTED boost diode**, not from the datasheet's test fixture.

### Adopt — from the review report
- Separate **R_g,on → E_on** and **R_g,off → E_off**, with K_Rg correction factors.
- Current-dependent E_on / E_off anchored on the datasheet test point.
- E_oss kept explicitly separate from E_on / E_off, with the double-count question **resolved**
  rather than merely flagged (Section 5.2).
- Graph/table → equation traceability stated in the report.

### Cross-validation worth recording
The review's conduction RMS, `(I_valley² + I_valley·I_peak + I_peak²)/3`, is **algebraically
identical** to our `i_ch² + Δi²/12`. Two independently written derivations agree — so the conduction
path is not where the error was.

---

## 5. The loss-model merge, term by term

This is the substance: which formulation survives for each loss term, and what the datasheet
changes about it.

### 5.1 Conduction

| | |
|---|---|
| **Ours** | `P = mean over θ of R_DS(T_j, I_local) · [i_ch² + Δi²/12] · D(θ)`, with CCM/DCM split, T_j converged |
| **Review** | Same RMS algebra, but one R_DS from a linear 25→175 °C interpolation at an asserted T_j |
| **Merged** | **Keep ours entirely.** Replace only the *source* of R_DS(T_j): phase 1 the datasheet's two table points (33 mΩ @25 °C, 54 mΩ @175 °C, both at V_GS = 18 V), phase 2 the digitised R_DS(T_j) curve — which is convex, so the linear interpolation both models use today is itself an approximation |

Also extract **V_GS at which R_DS(on) is specified**. A 33 mΩ figure at 18 V is not the same part at
15 V, and today nothing records which condition the number came from.

### 5.2 Switching — the term that needs a decision

Measured, at the datasheet's own test point (400 V, 27.9 A, R_g 1.8 Ω, datasheet parameters):

| | Analytic (ours) | Datasheet | Ratio |
|---|---|---|---|
| E_on | 8.1 µJ | 35 µJ | **k_on = 4.30** |
| E_off | 11.9 µJ | 22 µJ | **k_off = 1.85** |

**The two factors differ by 2.3×, and that is the clue.** A pure magnitude error would scale both
alike. Decomposing what a published E_on actually contains in a double-pulse test:

```
FET V-I overlap   8.1 µJ   (what our analytic model computes)
+ own E_oss       8.7 µJ   (we already count this as P_oss_fet)
+ freewheel charge  7–20 µJ (we already count this as P_rr_to_fet)
                 ────────
                  24–37 µJ  vs published 35 µJ
```

**So k_on = 4.30 is mostly a DEFINITION mismatch, not a model error.** The published E_on bundles
charge terms our engine already accounts for separately. Anchoring on the raw number while keeping
our separate E_oss and Q_rr terms would **double-count**. The review report warns about this in one
line and does not resolve it; we have to.

Two consistent conventions:

| | Convention | Consequence |
|---|---|---|
| **A** | **Datasheet-inclusive.** Use published E_on/E_off as the whole switching energy; drop our separate `P_oss_fet` and `P_rr_to_fet` at turn-on | Simple, directly traceable. But it **freezes** the C_oss and recovery contribution at the test fixture's conditions — wrong bus voltage, and wrong when the designer's boost diode differs from the DPT's freewheeling device |
| **B** | **Component-wise — SETTLED 2026-08-05.** Anchor only the *overlap* term: `E_overlap,anchor = E_on,ds − E_oss(V_test) − Q_c,fw·V_test`, then keep E_oss at the ACTUAL bus and Q_rr from the ACTUALLY SELECTED diode | Preserves the two things our engine does better. Needs the DPT's freewheeling device, which datasheets state in the test-condition footnote — so it becomes an extracted field |

Under **B**, the merged model is:

```
k_on  = [E_on,ds  − E_oss(V_test) − Q_c,fw·V_test] / E_overlap,analytic(test conditions)
k_off =  E_off,ds / E_off,analytic(test conditions)

E_on(θ)  = k_on  · E_overlap,analytic(I_valley(θ), V_bus, R_g,on)
E_off(θ) = k_off · E_off,analytic(I_peak(θ),  V_bus, R_g,off)
P_sw     = N_ch · f_sw · mean_θ[E_on + E_off]      (+ P_oss and P_rr as today)
```

Both `k` factors are **reported**, and their divergence is diagnostic: if they stay far apart after
the definition correction, the model shape is suspect and the report should say so rather than
present the number as derived.

### Why B — settled 2026-08-05

1. **The boost diode must couple to MOSFET turn-on loss.** Under A the charge dumped into the FET
   is frozen at whatever freewheeling device the vendor used in their fixture, so changing the boost
   diode would not move MOSFET switching loss at all. That is physically wrong, and it discards a
   cross-component interaction our engine already models via `P_rr_to_fet`.
2. **B reproduces the low-current intercept; A with linear scaling does not.** Validated against
   independently digitised curve data (external build spec, Layer D4):

   | I_D | measured E_on | B model (overlap + E_oss + Q_fw*V) | linear scaling |
   |---|---|---|---|
   | 2 A | 25.6 uJ | 21.5 uJ (-16 %) | 2.5 uJ (**-90 %**) |
   | 5 A | 26.6 uJ | 23.1 uJ (-13 %) | 6.3 uJ (-76 %) |
   | 12 A | 29.4 uJ | 26.7 uJ (-9 %) | 15.1 uJ (-49 %) |
   | 27.9 A | 37.1 uJ | 34.8 uJ (-6 %) | 35.0 uJ (-6 %) |

   B was **not fitted to these points** — it lands within 6-16 % across the sweep because the
   current-INDEPENDENT part of switching energy is carried by the separate E_oss and Q_rr terms.
   In a sinusoidal-input converter most of the line cycle is spent at low current, which is exactly
   where linear scaling collapses.
3. The loss breakdown keeps its E_oss line item, and the reviewer's own report requires E_oss to
   stay separate.

**B's cost, measured and accepted.** The anchor subtraction is sensitive to the fixture's
freewheeling device: a 3x spread in `k_on` (0.78 to 2.36 for Q_c,fw of 50 down to 18 nC) when the
datasheet does not state it. At total-loss level that is **+/-5 %**, against the 20 % error being
fixed. Three mitigations, all required:

- Extract the double-pulse fixture into the `measurement` block. When stated, the spread vanishes.
- When not stated, anchor on the mid case and **print the +/-5 % band**, never a bare number.
- Bound the anchor: a negative result, or an implied `k_on` outside roughly 0.5 to 5, is a flag.

**Why the analytic shape is worth keeping in phase 1.** Because it is physical, R_g dependence comes
free — `t_rise ∝ C_iss·R_g` and `I_gate ∝ 1/R_g` — so evaluating at the designer's actual R_g needs
no Diagram 18. The review's method cannot do this without digitising that curve. That is a real
advantage of the merge over either source alone.

**One shape correction that is phase 1, not phase 2.** With `gfs = None` (our default) the plateau
voltage is constant and E_sw comes out *strictly* proportional to current:

| I | E_sw, `gfs` unset | E_sw, `gfs` = 20 S |
|---|---|---|
| 2 A | 1.44 µJ (0.719 µJ/A) | 1.17 µJ (0.584 µJ/A) |
| 27.9 A | 20.05 µJ (0.719 µJ/A) | 18.73 µJ (0.671 µJ/A) |

Transconductance **g_fs is a table value** in most dynamic-characteristics tables, so extracting it
restores the correct superlinearity in phase 1. Note this also corrects an earlier review comment of
mine: our model is linear in current too, exactly like the review's — the current-*independent* part
of switching loss is E_oss, which is precisely why both keep it separate.

### 5.3 E_oss

| | |
|---|---|
| **Ours** | `P = f_sw · E_oss(V_bus)` from a 2-point curve, fully dissipated at hard turn-on. Structure correct; the curve is the 3.4×-wrong estimate |
| **Review** | Same formula, datasheet 8.7 µJ, but evaluated at 400 V rather than the actual 394 V bus |
| **Merged** | Our structure, datasheet value, **at the actual bus**. Phase 1 the table point (noting it is quoted at 400 V); phase 2 the digitised E_oss(V_DS) so the bus voltage is honoured exactly |

### 5.4 Gate drive

| | |
|---|---|
| **Ours** | `P = f_sw · Q_g · V_drive` — correct formula, but `V_drive` silently 12 V, and `Q_g` is the DB value without its gate-swing condition |
| **Review** | Same formula, 34 nC at 18 V |
| **Merged** | Same formula. Extract Q_g **with the V_GS swing it was measured over**; if the designer drives a different swing, phase 2 reads Q_g at that swing off the gate-charge curve. Keep gate loss OUT of the FET junction temperature (we already do; the review does not say either way) |

### 5.5 Leakage

Ours supports an `I_DSS(T_j)` curve and defaults to zero; the review sets 0 as a placeholder.
**Merged:** extract I_DSS where published (usually a table value at 25 °C and sometimes at T_j,max),
build the 2-point curve, and let the existing `p_leak` path work. Small, but it closes a placeholder
with a real number.

### 5.6 Thermal

| | |
|---|---|
| **Ours** | 80-pass iteration to a converged T_j; R_th(j-c) + R_th(c-s) + R_th(s-a); optional Foster network |
| **Review** | T_j asserted per operating point; notes R_th(j-c) 0.77 and Diagram 4 |
| **Merged** | **Keep ours.** Use the datasheet R_th(j-c) = 0.77 — worth noting our estimate from P_d gave 0.773, so the estimator is sound *here* even though E_oss was badly wrong. Phase 2 optionally fits Z_th(t) from Diagram 4 |

### 5.7 What the merged model must reproduce, and where it must differ

Reproduce the datasheet exactly: E_oss 8.7 µJ, Q_gd 6.2 nC, R_DS 33 mΩ @18 V, gate loss on 18 V,
switching anchored to the published 35/22 µJ under the chosen convention.

Differ **deliberately and explainably**: DCM near the zero crossing, converged T_j, per-angle
R_DS(on), correct duty at 264 Vac, Q_rr from the real diode, E_oss at the real bus. Matching the
review report everywhere would mean we had adopted its weaknesses too.

---

## 6. Build order

**Sequencing note:** the old selection paths are removed at M5, AFTER the new one works. Removing
them first would leave no way to choose a MOSFET at all.

| M | Milestone | Delivers | Verify |
|---|---|---|---|
| **M0** | **Parameter registry** | Canonical name / unit / source / report label / required flag for every MOSFET quantity. Test asserts engine dataclass field names match the registry. | Catches `vg` vs `vg_drive` on day one. Suite green. |
| **M1** | **Required-field manifest + provenance enforcement** | `validate_block()` refuses to compute unless every required field carries a provenance tag. Defect 1 fixed by construction. | A block missing `vg_drive` errors instead of defaulting to 12 V. |
| **M2** | **PDF extraction, phase 1** | `find_tables()` + label matching → `extracted.json`; per-part folder with hash + revision. Extracts g_fs, the V_GS conditions, and the DPT freewheeling device. | On the IMZA datasheet: E_oss, Q_gd, R_DS@18 V, E_on/E_off + test conditions, g_fs, R_th(j-c) all recovered. |
| **M3** | **Parameters confirmation screen** | Two sub-tabs; requirement-first display; per-field datasheet source; designer entry with provenance for gaps; Confirm → `confirmed.json`. | Nothing pre-filled from an estimate. Unconfirmed field = DATA MISSING. |
| **M4a** | **Direct-substitution loss terms** | Conduction R_DS(T_j) from the datasheet, E_oss at the actual bus, gate on the real V_GS, leakage, thermal R_th(j-c). Sections 5.1, 5.3–5.6. | E_oss 4.20 W → 1.22 W; gate 0.057 W → 0.086 W. |
| **M4b** | **Switching-energy anchoring** | Section 5.2 under the chosen convention; separate R_g,on/R_g,off; g_fs restoring superlinearity; `k_on`/`k_off` computed, reported, and their divergence flagged. | Reproduces 35/22 µJ at the test point with no double count. |
| **M5** | **Remove Top-10 and the two sub-tabs** | Selection is datasheet-first only. | No GUI path computes from estimates. |
| **M6** | **Plausibility gate on extraction** | C202's gate runs on `extracted.json` and again on `confirmed.json`. | Already built — wiring only. |
| **M7** | **Phase 2 — curve digitiser** | R_DS(T_j), E_oss(V), E vs R_g, E vs I_D, gate charge. Vector paths where present; assisted pixel digitising for scanned datasheets. Axis calibration confirmed and stored. | Curve overlaid on the datasheet image for confirmation. |
| **M8** | **PFC diode, then bridge** | Same registry, same pipeline. | Bridge recovers I_FSM / I²t, closing the Chapter 8 gate. |

### Verification discipline, every milestone
- Backend suite green (**192 passed / 2 skipped** is the baseline).
- Report changes verified render → extract; equations by page **image**, since `eq_box` draws
  through matplotlib and never appears in extracted text.
- `verify_combined_report.py`, plus the standalone endpoints for Ch 7–10 which it does not cover.
- Frontend `tsc` and a production `vite build`.

---

## 7. Adopted from the external build spec (`specs/Review/files.zip`)

An independently written extraction specification was reviewed 2026-08-05. It is a general
multi-vendor library design. We are **not** adopting its scope — 12 phases, a vision-model fallback,
a multi-vendor template pack. We ARE adopting the parts that make M0-M8 harder to get wrong.

### Adopted — folded into the milestones

| From | What | Into |
|---|---|---|
| A5 | **`measurement` block on every energy and charge value**: circuit, external_diode, includes_coss, includes_reverse_recovery, reference_device, confidence (`stated` / `inferred` / `unknown`). `unknown` blocks any calculation that depends on the distinction. | M2 — precisely the field convention B needs |
| A6 | **Anchor validation.** Every extracted curve must reproduce a tabulated value at that entry's stated conditions, default 8 % tolerance. No anchor available ⇒ **advisory only**, may not feed a calculation. Record measured, expected, error %, pass/fail — a reviewer needs the margin, not a green tick. | M7 |
| B8 | **Identify curve traces by anchor match, never bounding-box order.** They had two switching-energy curves assigned backwards; only the table anchor exposed it. | M7 |
| A8 | **`select(profile, key, **conditions)` raises when nothing matches** — never falls back to the first entry. | M1 |
| A3 | **Multi-valued parameters with conditions.** R_DS(on) on the reference part has FOUR entries (V_GS 15 / 18 / 20 V at 25 degC, plus 18 V at 175 degC). A single `rdson_25` field cannot represent that. | M0 — schema change |
| A9 | **Alias table.** One PDF yields a base type, ordering codes and a package marking. We have already hit this: our DB says `IMZA65R033M2HXKSA1`, the review PDF says `IMZA65R033M2H`. Never let the designer type the primary key. | M2 |
| A9.5 | **A family datasheet emits multiple profiles** from one PDF sharing one source hash. | M2 |
| A11 | **Profiles immutable and versioned.** A new datasheet revision writes a new version and requires re-approval of changed items only, shown as a diff. Every calculation records the `profile_version` it consumed. | M2 / M3 |
| A10 | **Review-gate design.** Show only what this calculation consumes (10-15 values), each **with its conditions AND its destination** (`R_DS(on) = 54 mOhm at V_GS 18 V, T_j 175 degC -> hot conduction loss`); sort defaulted / low-confidence / warned to the top; **render each curve with its anchor overlaid**; show which model is active and the delta. | M3 |
| B9 | **Summary-versus-detail cross-check.** Datasheets repeat headline figures in a summary block and again in the detail tables — compare them. Free validation. | M2 |
| B3 | **Table continuation across pages** — merge fragments sharing a caption index before parsing. Verified necessary on the reference file. | M2 |
| B6 | **Subscript merge by font-size RATIO with a NEGATIVE dx lower bound.** Italic glyphs overhang leftward, so a subscript's x0 can precede the base word's x1; using zero silently drops every subscript in the document. Use the MEDIAN body font size, never the maximum. | M2 |
| B7 | **NFKC-normalise units.** U+2126 (ohm sign) and U+03A9 (Greek omega) render identically and compare unequal — the source file uses U+2126. Treat a lone dash as "not specified", not zero. | M2 |
| A1 | **Device classes select the conduction-loss form.** `I^2 R` is a property of `sic_mosfet`, not a global assumption: an IGBT needs `V_ce0*I_avg + r_ce*I_rms^2`, GaN has no body diode. | M0 — vocabulary, even though only MOSFET is built now |

### Adopted with a correction

**A7.1 as written would block convention B.** It says: if a switching-energy entry has
`includes_coss == true` AND a separate `P_Eoss` term is enabled, refuse to run. But B deliberately
*de-bundles* — it subtracts E_oss from the anchor precisely so the separate term is not a double
count. The interlock needs a third state:

```
raw          + separate E_oss -> REFUSE (double count)
unknown      + separate E_oss -> REFUSE (cannot tell)
de-bundled   + separate E_oss -> ALLOW, and print the de-bundling arithmetic in the report
```

### Not adopted, and why

- **Vision-model fallback (C3).** Introduces a model dependency and non-determinism into a tool
  whose value is traceability. The designer has already agreed that an unreadable PDF asks for a
  better PDF — a better failure mode than a plausible machine guess.
- **The 12-phase build order and multi-vendor template pack.** Right for a general library, larger
  than this project needs. Our order stays M0-M8, hardened by the table above.
- **"Excel is export-only".** Agreed as a *profile storage* rule. But the plausibility bands (C202)
  are measured FROM the Excel catalogues as a reference distribution, which is not profile storage.
  No conflict — stated here so it is not "cleaned up" later.

### Where we are already ahead

- **Plausibility gate.** Their B9 asks for "values inside a plausible range declared per key". Ours
  (C202) is measured from 8948 catalogue parts with cross-field relations, zero false positives and
  80 % detection of decimal slips. Our gate IS their B9, stronger.
- **Thermal iteration (A7.4).** They specify it as a requirement; we already converge.
- **Line-cycle integration and DCM.** Outside their scope entirely — the extraction spec stops at
  the device. Our per-theta integration with a CCM/DCM split remains the calculation layer.
- **Non-zero intercept (A7.2).** We identified it independently; they measured it. Their D4 table is
  now the acceptance fixture for convention B.

### Their calibration of effort, worth repeating

Linear R_DS(T_j) interpolation gives 40.7 mOhm at 80 degC where the digitised curve gives 38.4 —
**5.7 % on conduction loss**, an order of magnitude less important than the switching-energy error.
Prioritise M4b over the R_DS(T_j) curve.

---

## 8. Open

Nothing blocking. The plan is finalised; M0 can start.
