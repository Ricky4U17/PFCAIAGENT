# PFC AI Design Agent — Session Handoff

**Start here after a restart.** Last updated **2026-08-01**, head = C188, on `master`.

> This file was stale for a long time (it sat at 2026-06-14 / ~C50 while work ran to C173). It is now
> the live resume point. **Keep it current at every commit wrap-up**, alongside `IMPLEMENTATION_LOG.md`.

## The three files that matter

| File | What it holds |
|---|---|
| **`PENDING_ITEMS.md`** | Everything still open, tagged `DATA` / `CODE` / `DECISION`, each with "done when". **Read before starting new work.** |
| **`IMPLEMENTATION_LOG.md`** | What was actually done, newest C-entry at the bottom. Full detail + verification numbers. |
| **this file** | Where we are right now and what comes next. |

---

## Where we are (2026-08-01)

**Just finished:** the designer's two-PDF review (32 in-PDF annotations + a Copilot Ch1-4 review).
**ALL batches are complete** — Group 1, 3a, Group 4 (items 21-29), 3c, 3d, 3e — C175 to C186,
merged to `master` on 2026-08-01.

### Next up, in order
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

### State of the build
- Backend suite: **172 passed / 2 skipped** (the standing baseline — anything else is a regression).
- Frontend `tsc`: clean.
- Combined report: **184 pp** without the semiconductor block, **199 pp** with it.

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
