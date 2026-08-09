# PFC AI Design Agent — Session Handoff

**Start here after a restart.** Last updated **2026-08-09**, head = **`a38e49a` C214**, on `master`.

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
- **M7 — HALF DONE at C214.** The digitiser and the proposal layer are in and validated; nothing
  reaches the engine yet. **The remaining half is the confirm screen**: render the figure, overlay
  the proposed points, accept/reject per curve, write it into the profile. Open question for the
  designer: its own sub-tab, or folded into the existing Parameters review screen?
  NOTE the plan's premise was wrong — these datasheets are VECTOR, so no pixel tracing is needed.
  A raster fallback for scanned datasheets is still unbuilt.
- **M8-bridge** — the bridge still has neither a datasheet flow nor a correct requirement (its
  average current is the INPUT current, not the output current; C210 deliberately left it alone
  rather than hand it the diode's formula).
- **PENDING A11** — no real diode datasheet has been through the extractor. Everything downstream of
  extraction is tested; the extraction layer for diodes is not. Ask the designer for a SiC Schottky
  and a silicon fast-recovery PDF.

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
- Backend suite: **431 passed / 2 skipped** (the standing baseline — anything else is a
  regression). 172 → 192 at C202 (`test_plausibility.py`) → 219 at C203
  (`test_parameter_registry.py`) → 244 at C204 (`test_parameter_manifest.py`) → 279 at C205
  and 293 at C206 (`test_datasheet_extract.py`) → 319 at C207, 332 at C208, 343 at C209
  (`test_datasheet_flow.py`) → 378 at C210, 394 at C211 and 409 at C212 (`test_diode_datasheet.py`).
  The suite now takes ~16 min: the datasheet tests re-extract a 17-page PDF per test.
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

Nothing is half-finished. Suggested order:

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
