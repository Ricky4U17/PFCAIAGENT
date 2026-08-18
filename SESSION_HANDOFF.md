# PFC AI Design Agent — Session Handoff

**Start here after a restart.** Last updated **2026-08-17**, head = **`3953636` C231**, on `master`.

> This file was stale for a long time (it sat at 2026-06-14 / ~C50 while work ran to C173). It is now
> the live resume point. **Keep it current at every commit wrap-up**, alongside `IMPLEMENTATION_LOG.md`.

## The three files that matter

| File | What it holds |
|---|---|
| **`PENDING_ITEMS.md`** | Everything still open, tagged `DATA` / `CODE` / `DECISION`, each with "done when". **Read before starting new work.** |
| **`IMPLEMENTATION_LOG.md`** | What was actually done, newest C-entry at the bottom. Full detail + verification numbers. |
| **this file** | Where we are right now and what comes next. |

---

---

## The datasheet-first arc (C202-C210) — where it actually stands

**Why it started.** The Digi-Key MOSFET catalogue carries **0 of 1311 parts with ANY of the nine
fields the loss engine consumes**. Everything was estimated from eight columns; on IMZA65R033M2H the
estimated E_oss was 3.4x the published value. The fix is not a bigger database — it is that a number
entering the design must carry provenance.

| C | What | Verified against |
|---|---|---|
| C202 | plausibility gate (advisory, cross-field bands from live catalogues) | 8948 parts, 0 false positives |
| C203 | canonical parameter registry — one name / one unit / one meaning | two-way dataclass audit |
| C204 | required-field manifest; `select()` raises rather than guessing a condition | — |
| C205 | PDF table extractor + per-part immutable profile store + vendor templates | a real Infineon PDF |
| C206 | extractor hardening (subscripts, packed rows, dash-vs-number columns) | same PDF |
| C207 | the GUI flow: requirement -> upload -> review -> confirm | — |
| C208 | **M4a** direct-substitution terms on real values | 21.35 W -> 17.08 W |
| C209 | **M4b** switching-energy anchoring, convention B | k_on/k_off 2.3x apart -> 1.10x |
| C210 | **M8-diode** the boost diode from its datasheet | 8.14 W -> 1.33 W on a SiC part |
| C211 | capacitive-charge split V*Q_c/(2-m); leakage bound; shared-package thermal | 1.81 W -> 2.29 W on VS-3C40 |
| C212 | **M6** plausibility gate wired onto extracted/confirmed profiles | catches a decimal slip, a swapped column, a wrong unit |
| C213 | **M5** loss ranking restricted to what the catalogue measures | bridge + bottom-FET kept; MOSFET/diode refuse with the reason |
| C214 | **M7 part 1** vector curve digitiser + proposals | Fig.1 2.8%, Fig.9 0.36% against the part's own table |
| C215 | **M7 part 2** Curves sub-tab; a confirmed curve reaches the engine | P_D_cond 7.19 -> 5.86 W; caught a transposed-axis -692 W bug |
| C216 | digitiser measured on 4 vendors + fragmented-label fallback | reads 3 of 5 files; Toshiba is RASTER, Infineon frameless |
| C217 | **M8-bridge** steps 0-2 + 5; LVE5060E extraction; consensus axis fitting | 0 -> 11 params; Fig. 4 matches BOTH table anchors |
| C218 | **M8-bridge** steps 3, 4, 6, 7 — requirement, sync-bottom, GUI, §7.3 | bridge leaves the catalogue; I_F(AV) 22.2 -> 28.3 A |
| C219 | 3 GUI defects; parts are **provisional until published**; Ch7-only PDF | re-upload no longer calculates the OLD part |
| C220 | per-temperature traces NAMED (order + table anchor); 1-based `page`; leader filter | sharing sweep no longer degenerate; 29.27 -> 25.71 W |
| C221 | bridge **derating gate** computed (Table 7.3.3), PASS/FAIL/DATA MISSING | 30.0 A allowed vs 9.4 A drawn at 102 °C case |
| C222 | **real diode datasheets through the extractor** — 7 defects, series-variant selection | SFAF1608G V_F 0.975 → 1.700 V; **A11 CLOSED** |
| C223 | 6 designer findings on the semiconductor page (GUI only) | requirement ignored `n_parallel` — per-package 18.87 → 9.43 A |
| C224 | **M7-MOSFET** — grid-based plot finding, decade/lost-minus axes, 4 targets, curves reach the engine | 0 → 17 of 26 calibrate; 4 targets all agree with the part's own table; P_FET 9.10 → 8.78 W |
| C225 | external review: **measured E_on/E_off curves** + de-bundled + per-path K_Rg; labels, leakage column, datasheet figures in the report | traces self-identify to ≤0.8 %; **found k_esw scaling a measured curve by 2.71** (P_FET 41 % high) |
| C226 | R_g_common retired; gate drive into the FET total; **a hidden `sw_method:'analytic'` was disabling C225 entirely** | swept R_g_common 1.8→9999 Ω, loss identical; curves read+stored+shown then NOT used |
| C227 | report 500 on a digitised curve (`_vf` printed all 244 points); I_F(AV) unnamed (`IF (1)` is a DIE INDEX); `is_sic` asked for while displayed | report would not build at all; both dies now kept with their case temperatures |
| C228 | **a minimum is a value** — V_DSS extracted at 650 V and dropped 3 layers later by `_scalar_entry` | diagnosed wrong 3× before the baseline caught the inert "fix" |
| C229 | "1 value still unsupplied" — two false alarms; `_scalar_entry` inverted to *not a curve* | device_class dropped on 7/7 datasheets; banner now agrees with `validate_block` |
| C230 | Ch7 states the method it ran (7.2c followed `sw_method`); duplicate 7.4.2b split; **new Table 7.2e** | 22 engine inputs with their source; GUI↔report 9/9, 0 mismatch |
| C231 | **every loss term shows the plot its value came off, or says there is no plot** | 7 mechanisms; 4 table-sourced values stated without a figure; found a 2nd duplicate (7.3.1) |

**Settled convention B** (2026-08-05): a published E_on bundles the device overlap, its own E_oss,
and the fixture's freewheeling charge. This engine counts the last two separately, so they are
subtracted BEFORE anchoring. Confirmed empirically at C209 — raw anchoring puts k_on and k_off 2.3x
apart, de-bundling brings them to 1.10x, and a magnitude error would have scaled both alike.

**Settled at C210:** the datasheet outranks the sub-tab. Every diode upload defaults to the
`sic_schottky` class, so if the tab decided the technology a silicon part would be evaluated by the
SiC branch — different physics on the largest term in the chapter, with no missing value to give it
away. Evidence wins, the override is reported everywhere, and the block is validated against the
class it RESOLVED to rather than the one it arrived under.

### Two traps this arc added to the list
4. **A pooled audit cannot see a per-class disconnect.** `audit_engine_dataclasses` unions Mosfet +
   Diode + Bridge, so a field on ANY of them looks present on ALL of them — it reported clean while
   eleven classes claimed engine fields their own dataclass lacks. Use `audit_device_classes()`
   (C210); it checks each class against its own dataclass.
5. **A symbol map written before a device class existed will aim at the nearest wrong key.**
   Four defects of one shape: `VRRM`/`VR` onto the MOSFET-only `V_DSS`, `CT` onto the MOSFET-only
   `C_iss`, `IR` onto a diode-only leakage key from the BRIDGE template — each parsed cleanly,
   landed on a name the part's class does not carry, and was dropped, and two GREEN TESTS were
   asserting the wrong key. The old validator only asked whether the key existed. Templates now
   declare `device_classes` and the validator enforces applicability (C211). Run
   `audit_device_classes()` and the template-scope test after touching either file.
6. **Never re-dump the JSON registries through `json.dump`.** `canonical_parameters.json` and
   `vendor_templates.json` are hand-aligned for reading. Re-dumping turned a 15-line change into a
   2242-line diff (caught and reverted at C210). Edit them as TEXT and parse only to validate.

### What is left of the plan
- ~~**M5**~~ — DONE at C213. Not deleted: the bridge and the bottom-FET conduction search
  still use it legitimately, so the ranking is bounded to what the catalogue measures.
- ~~**M6**~~ — DONE at C212. The gate runs on upload and on confirm, advisory in both.
- **M7 — DONE for the diode at C214/C215 and for the MOSFET at C224.** Digitiser, proposals,
  Curves sub-tab, and the confirmed curve reaching the engine, for both device kinds.
  - ~~**(b) Infineon frameless + fragmented labels**~~ and ~~**(c) no MOSFET targets**~~ — BOTH
    CLOSED at C224. The blocker was never calibration quality: this vendor draws no rectangle and
    every gridline is its own stroke, so nothing could FIND the plots. `find_plots_by_grid` recovers
    the box from the geometry (see its docstring). 14 → 26 regions, 0 → 17 calibrated, and four
    MOSFET targets that each agree with the part's own tabulated value.
  - **(a) Toshiba still needs a RASTER tracer.** Its curves are 1638x1289 bitmaps, no vector paths
    at all — a different capability, the "assisted pixel digitising" the plan specified. Unbuilt,
    and the one remaining M7 gap. It reads nothing rather than reading something wrong, which is
    the behaviour a test asserts.
  - **The lesson C224 added:** two axis defects are INVISIBLE to the residual gate, and only the
    cross-check against the datasheet's own table catches them. Decade labels read as integers
    (100/101/102/103) are equally spaced, so they fit a linear axis with residual exactly zero —
    that put a C_oss curve on a linear 100..104 axis instead of 1 pF..10 nF. And an exponent minus
    drawn as a graphic leaves the text layer reading 10^5..10^0 for an axis running 10^-5..10^0.
    **Never accept a curve on residual alone where the datasheet tabulates a point on those axes.**
- ~~**M8-bridge**~~ — DONE at C217/C218. The bridge is selected the way the MOSFET and the diode
  are, and **nothing in Chapter 7 now comes from the parametric catalogue.** Its requirement is its
  own (blocks the LINE peak, carries the RECTIFIED MEAN against an average rating), sync-bottom
  names an ordinary confirmed MOSFET as the bypass FET, and §7.3 runs a real sharing sweep.
  TWO FOLLOW-UPS, both small:
  - ~~the sharing sensitivity is degenerate~~ — CLOSED at C220. Fig. 4 is confirmable now that
    its traces are named, and with the real V-I curve the cases separate: 25.71 / 26.40 / 27.04 W
    at 50/50, 60/40, 70/30 (all were 29.27). The headline falls 29.27 -> 25.71 W.
  - ~~the derating gate (Fig. 1)~~ — CLOSED at C221. Canonical key `I_F_AV_vs_Tc`, matched on
    "case temperature" EXACTLY (the free-air curve on the same page is rated 6 A against this
    one's 50 A), carried as `_i_f_av_vs_tc` metadata, computed as Table 7.3.3 with PASS / FAIL /
    DATA MISSING. A part with no curve on file reports DATA MISSING and never reads as approved.

  **BOTH C218 follow-ups are now closed.** Chapter 7 takes nothing from the parametric catalogue,
  and the bridge is selected, verified, loss-modelled and derating-checked from its own datasheet.
- ~~**PENDING A11**~~ — CLOSED at C222. Both files are on disk in `specs/Review/PFC Boost Diode`
  and the generic template covers them. **The datasheet-first arc M0–M8 is now complete and
  signed off on real vendor PDFs for all three device kinds.**

  The lasting lesson is the SERIES DATASHEET: one document, several parts, and the values that
  differ are BANDED — either a column per variant or a variant list in a cell. The designer's part
  number is the variant. With none given every band is kept and `variant_required` asks; a band is
  never silently chosen. Any new vendor file should be checked for this first.

---

## Where we are before that (2026-08-04)

**Just finished:** a long Chapter 8 / input-protection arc (C195–C201), driven by the designer
item-by-item and by a redlined review PDF. Chapter 8 is now the most worked-over chapter in the
report; treat its conventions as settled.

### What changed, and the three rules that came out of it

| C | Commit | What |
|---|---|---|
| C195 | `3a2a1c8` | NTC page: 4 controls to the Relay tab; **R_wiring/R_PCB removed — they were a second sum of the same loop** that omitted the designer's Loop R; bridge I_FSM auto-fed from Ch 7 |
| C196 | `76769e4` | **Relay make current: one formula, at the right instant.** Three copies spanned 1 A / 7 A / 138 A. The contact shorts the NTC out as it closes, so the NTC is NOT in the make path |
| C197 | `cfb1751` | Ch 8 legibility: substituted equations, **k_margin restored to Table 8.2** (it disagreed with its own equation by exactly 1.10), why N·τ = 4, what steady I_max is, splash page rebuilt |
| C198 | `474c399` | Under-rated relays hidden (1038/1082); safe values derived for the inputs nobody publishes |
| C199 | `395ad2e` | **Relay selects on 3 gates, fuse on 2** — the only ones the vendor tables carry for every part; plus 52 redlines from the review PDF |
| C200 | `5874f6a` | Annotation-label wraps, all four |
| C201 | `4e4c004` | **Input focus loss fixed** (component declared inside a component); PDF-fitted curves now labelled in Table 7.2d |

**Three rules worth carrying forward:**

1. **A gate is only worth screening on if the vendor table carries the field for every part.**
   Melting I²t is 90/115, the fuse re-rating slope is **0/115**, and no relay publishes a make
   rating — screening on those excluded parts for want of a datasheet column, not for any electrical
   reason. They are now computed, reported, and confirmed by the designer.
2. **Annotation labels wrap PER WORD, not per label.** The cell is ~20 mm and breaks on spaces only,
   so any unbroken token over **7 characters** splits mid-word — "ANCHORED" at 8 letters already
   does (C209), as do "DE-RATIN G", "CATALOG UE" and "STATEME NT". A hyphen is not a break point. "MAKE RATING" is fine.
3. **Never declare a React component inside another component.** New identity every render →
   unmount/remount → the `<input>` is recreated on every keystroke and loses focus. `Knob` in
   `InputProtection.tsx` has always been at module level, which is why that page never had it.
   There are now no inline `React.FC` declarations left anywhere; keep it that way.

### Where the designer landed on Chapter 8's shape
- **Candidate lists do not belong in the report.** The GUI is where parts are seen and chosen; the
  report records the part picked and why. The fuse and relay candidate tables are to come out of the
  report too, "when we come to that point" — not yet done.
- **Selection is never blocked by missing data**, and an un-screenable check becomes a stated
  designer confirmation rather than a permanently-OPEN gate.
- **The NTC restart off-time and the relay dwell time are different quantities** and must not be
  conflated: 2 × t_operate is contact settling (~80 ms), thermal recovery is seconds to minutes.

### The earlier 5-item batch (C193–C194) — ALL FIVE ARE IN

| # | Item | Where |
|---|---|---|
| 4 | `Loop R` default 1 Ω, and ONE loop-resistance input | C193 `d593963` |
| 5 | Chapter 8 restructured to the designer's flow, 8.1-8.14 → **8.1-8.9** | C193 `d593963` |
| 1 | Separate **Relay** tab (GUI is now NTC / Relay / Surge / Line fuse) | C194 `cac1cdd` |
| 2 | Relay vendor database — `Power_Relays_Database.xlsx`, **1082 parts** | C194 `cac1cdd` |
| 3 | Relay + fuse parameters moved to their own tabs; new relay inputs, reported in Sections 8.4.4 / 8.4.5 | C194 `cac1cdd` |

Two things worth knowing before touching this area again:

- **`Loop R` was labelled "line + EMI + ESR" but bound to `r_emi` alone**, and `r_line` had no knob
  at all. It is now ONE figure (`r_loop_ohm`), deliberately — the same resistance counted twice
  understates the NTC requirement and can select an under-sized part. The annotation "WHAT Rpar IS"
  in Section 8.2 says so in the report.
- **The relay and fuse knob VALUES still travel in `ntcOpts`.** Only the editing location moved.
  The NTC engine reads them for its own relay make-current and I²t checks, so do not "tidy" them
  into a separate payload without following those reads.

Preceding that: the designer's two-PDF review (32 in-PDF annotations + a Copilot Ch1-4 review) —
Group 1, 3a, Group 4 (items 21-29), 3c, 3d, 3e — C175 to C186; then the Copilot Ch1-Ch6 review
(C187/C188), the Ch5-Ch7 review (C189) and two GUI review rounds (C190-C192).

Also new and NOT committed: **`Framework_Handoff/`** — the package prepared for claude.ai to design
the larger framework (architecture PDF, two block diagrams, technical brief, open items, current
state, and `07_api_and_engines.json` = 63 endpoints / 18 engines / 38 graph nodes).

### Next up, in order
0. **The "bring your own part" architecture** — reviewed 2026-08-04. **Step (a) the plausibility
   gate is DONE (C202)**; steps (b)–(e) not started. The real problem is not database size but that a number entering the design has no
   provenance and no validation. Agreed order: (a) plausibility gate using the existing catalogues
   as the reference distribution — `Ve = Ae·le` alone would have resolved C115 in seconds;
   (b) provenance-tagged `contributed/` store separate from `verified/`; (c) batch MPN compare +
   Excel export, running through the SAME engine the report uses; (d) supplier PDFs as the source of
   record for the curves the Excel spine cannot carry, with an ASSISTED DIGITISER (agent proposes
   points, designer confirms against the plot) — never a silent extractor; (e) a chatbot scoped to
   explaining the design from ENGINE OUTPUTS first, part discovery second. Three questions still
   open: does a contributed part read differently in the report; is a flagged value blocking or
   advisory (recommendation: advisory + recorded acknowledgement); chatbot scope on day one.
1. **Designer decision from C187:** Table 5.5.2 shows the reference bank FAILS the capacitance
   requirement at -20% (1920 uF vs 2047 uF, -6.2%). Add capacitance, accept reduced worst-case
   hold-up, or source a tighter part.
3. **C2** — report download. Two silent failure mechanisms were fixed (premature
   `revokeObjectURL`, synchronous `removeChild`); **the designer must retest**. If it still fails,
   capture the screen + whether a red banner now appears + the console, then wire the visible
   fallback link (`downloadBlob()` already returns the URL for it).
2. Then: **D3**
   (saturation gate on B_inner — changes selection, decide on its own merits), **B9**
   (L_target vs L_req: the reference state diverges +67%, a designer decision), **A9** (3 xflux_hdc
   materials with no Bsat-vs-T; `data_source` at the wrong nesting level in 67 powder files).

### Traps this stretch re-taught
- **The same quantity computed in two places will diverge, and the report will not say so.** C196
  found three formulas for the relay make current; C195 found two sums of one loop resistance; C199
  found a table on the generic R25 pick inside a section that otherwise uses the selected part.
  When adding a table or a worked example, check which basis the rest of the section uses.
- **`eq_box` renders through matplotlib, so equations never appear in extracted text.** Verifying
  them needs a page image, not a text extract. Same for anything drawn rather than typeset.
- **A scripted renumbering can create DUPLICATES that a "does the series start at 'a'" audit cannot
  see.** Always list the RENDERED table captions from a built PDF and check for repeats.
- **`ast.parse` + the suite are not enough.** Three defects this stretch (the `_ch4` NameError that
  silently dropped ~90 pages, the `%`-format `TypeError`, the leftover "Ccm") were only visible in a
  BUILT PDF. Run `verify_combined_report.py` (its 178-190 page assertion is the guard), and for
  Ch7-10 build the standalone endpoints — the combined verify does NOT cover them.
- **`dict.get(k, default)` does not fire on an empty string.** That was the blank "Supplier: .".
- **Report and GUI drift when they compute the same thing twice.** Diff engine output against a
  pre-change baseline before/after any presentation-layer edit.

---

## Where we were (2026-07-30)

Four designer review areas are complete and committed: **EMI**, **MOV+GDT**, **NTC**, **Fuse**.
The last stretch of work reorganised Chapters 8 and 9 around a *requirement → screen → select → verify*
flow and fixed several real calculation defects found along the way.

### Recent arc — C162 → C177

| C | Commit | What |
|---|---|---|
| C162–C164 | `e0f6619` `8f792ad` `da4cab0` | Ch8 NTC: tolerance-aware R25 gate, two-tier GUI list, de-circularised report |
| C165 | `3e6d0f5` | Fuse 4 → 6 gates. **Fixed:** the inrush *peak* was gating the continuous rating, so nothing was selectable |
| C166 | `5f82376` | Ch8 resequenced 8.1 → 8.14, real Table B, fuse I²t split into 4 cases |
| C167 | `fcb0755` | One section-reference convention report-wide: **"Section"** (no `§`, no "Sec.") |
| C168 | `fcb0755` | MOV backend: selection gates + selected-**part** recalculation. **Fixed:** energy judged against the wrong candidate |
| C169–C170 | `df2254e` | MOV GUI panel + Chapter 9 restructured to **9.1 – 9.11** |
| C171 | `d3cd507` | **Capacitor loss: one engine, per line.** Ch7 Table 7.8b was re-deriving from the control-loop ESR → 46 % low. Now == Ch5 Table 5.3.1 row for row |
| C172 | `b103437` | `verify_configuration` resolves ESR from the **part record**, not the curated series table |
| C173 | `94c5ee8` | Top-10 "Devices in parallel" box showed a misleading placeholder — blank meant 2, not 1 |
| C174 | `7e89c39` | Re-run buttons passed React's click event as their options — knob values never reached the backend |
| C175–C177 | `1ba399e` `b73d9c6` `3cbc633` | Inductor loss on TWO bases: **crest → saturation, cycle-average → thermal + efficiency**. Naming collision (`Pcore_W` meant average at top level, crest per row) resolved; per-point averages for core AND copper; Tables 4.2 / 4.5a / 4.5b / 4.6 / 7.8b and the Review page all on one basis |

### State of the build (verified at C201)
- Backend suite: **525 passed / 2 skipped** (the standing baseline — anything else is a
  regression). 172 → 192 at C202 (`test_plausibility.py`) → 219 at C203
  (`test_parameter_registry.py`) → 244 at C204 (`test_parameter_manifest.py`) → 279 at C205
  and 293 at C206 (`test_datasheet_extract.py`) → 319 at C207, 332 at C208, 343 at C209
  (`test_datasheet_flow.py`) → 378 at C210, 394 at C211 and 409 at C212 (`test_diode_datasheet.py`)
  → 442 at C214 (`test_curve_extract.py`), 455 at C217, 467 at C218 (`test_bridge_datasheet.py`)
  and 478 at C219 (`test_parts_library.py`), 491 at C220 (`test_figure_temperatures.py`),
  503 at C221 (`test_derating_gate.py`), 525 at C222 (`test_diode_real_datasheets.py`),
  **536 at C224** (4 in `test_curve_extract.py`, 8 in `test_datasheet_flow.py`),
  **551 at C225**, **571 at C228** (API-flow, curve-survival and min-only guards).
  The datasheet tests re-extract and re-digitise a 17-page PDF, so they dominate the runtime.
  C224/C225 tests run the whole M7 flow ONCE at module scope for that reason — if you add more,
  do the same rather than uploading per test.
  **The suite takes ~10.5 min** (647 s / 615 tests, measured 2026-08-17 on a quiet machine).
  It is past the 10-minute foreground limit, so ALWAYS run it backgrounded. The trend is one-way:
  the two newest guards each build real datasheets, which is what makes them worth having. It was
  51 min until `tests/conftest.py` began memoising the two pure expensive reads — `extract` (~40 s,
  called ~34 times on the same few PDFs) and `digitise` — session-wide, keyed on the SHA-256 of the
  PDF bytes. **Every cache hit returns a DEEP COPY and that is load-bearing**: `upload` writes
  `part_number` into the profile it is handed and `figure_proposals` writes `T_j` onto curve dicts,
  so sharing the cached object would leak one test's mutations into the next test's "fresh"
  extract. The slowest tests are now the report builders (~100 s), not the datasheet reads.
  **Two earlier readings were WRONG and are recorded here so they are not trusted again**: 3 h 50 m
  (heavy probe scripts running concurrently) and 1 h 25 m (a single test showed 1902 s — 32 min for
  work that takes 43 s standalone). The 1902 s did NOT reproduce: the same test at the same position
  with no plugins to reorder it came back under 42 s on a repeat run, and the totals agree
  (85 min − 32 min ≈ 51 min). Code, memory, ordering and Defender were each eliminated by
  measurement, so it was external. **When a suite time looks wrong, re-run before believing it.**
- Frontend `tsc`: clean.
- Combined report: **190 pp** without the semiconductor block. With it, expect ~205 pp.
  Remember `verify_combined_report.py` does NOT include the semiconductor block, so **Chapter 7 is
  not in the harness report** — to check anything in Ch7, POST `/documentation/generate-report`
  with `semiconductor` present.
- Chapters 8+9 standalone: **27 pp** with an NTC selected (25 pp bare), sections in order
  8.1, 8.2, 8.3, 8.4, 8.4.1-8.4.6, 8.5, 8.6, 8.6.1, 8.7, 8.8, 8.9. Zero unrenderable glyphs and
  zero mid-word label wraps — both are swept for, not assumed.
- Frontend production `vite build`: clean (worth running after any component-structure change).

---

## What to pick up next

Nothing is half-finished. The Chapter-7 documentation arc (C230-C231) is complete and the designer
has run it; the agreed NEXT topic is **more graphs and supporting detail in the report**, discussed
but not started. Two things were flagged during C231 and should shape it:

- **Decide inline vs appendix before adding figures.** Chapter 7 is 21 pages with all three parts
  real. C231 relocated the eight existing plots at net-zero cost; anything genuinely NEW grows the
  chapter. Worth agreeing a structure first rather than discovering it at 30 pages.
- **Run `tests/test_report_numbering.py` before and after** — it is now the gate on exactly the
  activity that is next, and it has already caught two duplicates that nothing else could see.

Then, in order:

0. **`PENDING_ITEMS.md` B19** — the raster curve tracer, the last M7 gap. Optional: it is the only
   datasheet on file that cannot be read, and it fails safely today. Take it when a designer
   actually needs a Toshiba part, not before.
1. **`PENDING_ITEMS.md` B5** — delete the dead `_extra["esr_mohm"]` in `main.py`. Small, and it still
   carries the `or`-chain pattern that caused C171.
   *(Group 2 of the designer review — report shows the ranking default instead of the selected part —
   is the other natural next step; see the review findings list.)*
2. **Chapter 9 M4 (data)** — `PENDING_ITEMS.md` A2/A3. MOV `Vc @ In` is missing on 1140/1140 parts and
   GDT impulse-sparkover + follow-current on 172/172. **Criterion A cannot reach PASS until this lands** —
   M1–M3 made that blocker legible rather than hidden. This is the designer's "improve the database" batch.
3. **`PENDING_ITEMS.md` B3** — bridge rectifier `rd`. DB-selected bridges run with `rd = 0`, so paralleling
   understates its benefit (~1 W shown vs ~4–5 W real).
4. **`PENDING_ITEMS.md` B4** — status-vocabulary unification. Parked by the designer; Ch8 and Ch9 use
   different word sets. Do it as one project-wide pass, not per chapter.

---

## Settled conventions — do not re-litigate

- **Section references spell out "Section".** No `§`, no "Sec.". Whole report. (`PENDING_ITEMS.md` D0a)
- **BLOCKED gates RELEASE only, never part selection.** A missing datasheet field or failed gate stops
  sign-off and is listed as a blocker, but the designer can always still pick a part. (D0b)
- **One engine per value.** If two chapters print the same quantity they must call the same function —
  never re-derive. C161 (inductor copper) and C171 (capacitor loss) both exist because this was violated.

---

## Traps that have bitten more than once

- **A FIXTURE THAT CANNOT RENDER A SECTION CANNOT POLICE IT.** C231: the numbering test shipped
  that morning used a real MOSFET but STUB diode and bridge, so Section 7.3.1 (surge ratings, which
  render only when the bridge publishes I_FSM/I²t) never appeared — and a duplicate 7.3.1 sat there
  undetected. Report fixtures must build the configuration a designer actually produces: all three
  parts from real vendor PDFs. `tests/test_report_numbering.py` now does, and asserts the bridge
  really carries surge ratings so the section is guaranteed to render.
- **`tests/test_report_numbering.py`** — no two RENDERED tables share a number, on built PDFs.
  Run it before and after adding any section, table or figure to a report chapter.
- **`tests/test_review_completeness.py` IS THE GUARD ON THIS WHOLE CLASS.** It walks every
  parameter of every vendor datasheet on file and asserts that nothing the profile holds is
  reported unsupplied — deliberately not written against a key list, which would go stale exactly
  when it mattered. It was verified to FAIL against both historical broken states of
  `_scalar_entry` before being trusted. If a designer ever again reports being asked for a value
  the datasheet prints, this file should have caught it: check why it did not.
- **ASK WHERE THE VALUE STOPS, NOT HOW IT IS READ.** C228: V_DSS looked like an extraction
  failure, was diagnosed as one three times over, and had been extracted correctly all along —
  a filter three layers downstream (`_scalar_entry`, testing `typ`/`max` and not `min`) dropped
  it. `unresolved` records and the raw text layer both make anything missing look like a parsing
  problem. Walk the value from table row → entry → review row and find where it disappears
  BEFORE theorising about the reader.
- **BASELINE THE EXTRACTOR BEFORE TOUCHING IT.** `scratchpad/extract_baseline.py` snapshots every
  parameter every datasheet on file yields — 79 keys across 7 vendor files, with values and
  conditions. The only acceptable diff is a NEW key. That is what proved a C228 candidate fix
  inert (0 added, 0 changed) instead of shipping it into the shared path every upload uses.
  Rebuild it before any change to `datasheet_extract.py` or `vendor_templates.json`.
- **A HELPER ADDED TO EXCLUDE ONE SHAPE WILL EXCLUDE MORE THAN INTENDED.** `_scalar_entry` was
  written to keep a digitised curve out of a scalar slot and silently removed every min-only
  parameter with it. When narrowing a selection, enumerate what legitimately passes — here the
  caller reads min, typ AND max.

- **A FEATURE CAN PASS EVERY TEST AND STILL BE DEAD IN THE GUI.** C215, C224 and C225 each shipped
  curve work that never reached the engine through the screen: `confirm()` deleted every accepted
  curve, and no test ran `confirm_figure` and `confirm` in the order the Curves tab calls them.
  The engine was right and each endpoint was right — the SEQUENCE was broken, and nothing tested a
  sequence. `tests/test_api_flows.py` now drives the real endpoints in GUI order; **add to it when
  you add a screen flow**, because a unit test on the engine cannot see this class of defect.


- **The verify harness does not cover Chapter 7.** `verify_combined_report.py` passes no `semiconductor`
  block, so Ch7 is absent from its 184-page report — that is why the C171 capacitor-loss error survived.
  To check anything in Ch7–Ch10, `POST /mode-b/documentation/generate-report` with `semiconductor`
  (and `input_protection` / `input_filter`) present.
- **After moving a block of report code, BUILD the PDF — `ast.parse` is not enough.** In C170 a relocated
  block landed after a `return` (valid Python, dead code) and a variable it defined went missing. Both
  parsed cleanly; only building caught them.
- **ReportLab text must stay within Windows-1252.** Non-cp1252 glyphs render as `.notdef` boxes. Verify
  with render → PyMuPDF text extract and count `■`. Safe: `√ · ² ³ → ← ↔ η φ θ π Δ μ Ω ° ± ⊗ ● ′ ∝ Φ`.
  Not safe: `⌈⌉ ⌊⌋ ⊙ ○` and combining diacritics.
- **`or` fallback chains silently substitute different physical quantities.** That is the C171 bug in one
  line. A missing value should read DATA MISSING.
- **Never pass a handler bare to `onClick` if it takes parameters** — React supplies the click event as
  the first argument. `onClick={() => fn()}`. `Btn.onClick` is now typed to catch this, and the `post`
  helper rejects an event in a request body. (C174; PENDING_ITEMS B6.)

---

## Running things

```bash
# backend  (venv)
cd backend && uvicorn app.main:app --port 8000
# frontend
cd frontend && npm run dev

# full suite  (~5 min, expect 172 passed / 2 skipped)
cd backend && PYTHONUTF8=1 venv/Scripts/python.exe -m pytest tests/ -q

# combined-report harness  (Ch1–6 only — see the trap above)
cd backend && PYTHONUTF8=1 venv/Scripts/python.exe verify_combined_report.py [fcv_Hz]
```

Run Python with `PYTHONUTF8=1` on Windows or prints of `★ µ Ω °` throw `UnicodeEncodeError` (cp1252).
