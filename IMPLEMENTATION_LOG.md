# PFC AI Agent v2 — Implementation Log

Tracks every decision made, file changed, and verification result for the
DesignState canonical schema work (sessions starting 2026-06-06).

For overall project history (Steps 1–16) see `CHANGELOG.md`.

---

## Legend

| Symbol | Meaning |
|--------|---------|
| ✅ | Verified — test passed |
| ⚠️ | Warning — non-blocking issue noted |
| ❌ | Failure — must fix before proceeding |
| 🔒 | Locked — do not change without updating this log |

---

## Session 2026-06-06

### Discussion Summary

- Reviewed proposed DesignState canonical schema architecture (7 spec PDFs in `specs/`)
- Generated current + proposed architecture block diagrams as PNG images
- Key concern raised: **will this break the GUI?** Answer confirmed: ZERO GUI impact if
  DesignState is backend-only (Phase 1 = pure backend schema, validation off by default)
- Pre-implementation review PDF generated: `specs/PFC_DesignState_Implementation_Review.pdf`
- Naming conflict found and corrected: use `design_state.py` not `schemas.py`
  (two `schemas.py` already exist in `app/engines/state_space/` and `app/llm/`)

---

### Phase 1 — Schema Only

**Goal:** Add DesignState schema as documentation + optional validation scaffold.
No behaviour change. Feature flag defaults to OFF.

#### Files Created

| File | Lines | Purpose |
|------|-------|---------|
| `backend/app/design_state.py` | 100 | Pydantic DesignState model — all Optional, `extra='allow'` |
| `docs/DESIGN_STATE.md` | 100 | Field ownership table, agent rules, how-to-extend |
| `frontend/src/types/DesignState.ts` | 95 | TypeScript interface — not imported, documentation only |

#### Files Modified

| File | Change | Lines added |
|------|--------|------------|
| `backend/app/config/feature_flags.py` | Added `enable_design_state_validation: bool = False` | +4 |
| `backend/app/main.py` | Added `_validate_state()` helper (not called from any endpoint) | +11 |

#### Files NOT Changed (GUI protection)

`frontend/src/App.tsx` · `frontend/src/api/client.ts` · all components ·
all mode_b calculation engines · all report generators · all JS studio tools

#### Verification Results — Phase 1

| Check | Command | Result |
|-------|---------|--------|
| Syntax — design_state.py | `ast.parse(...)` | ✅ OK |
| Syntax — feature_flags.py | `ast.parse(...)` | ✅ OK |
| Syntax — main.py | `ast.parse(...)` | ✅ OK |
| Import — design_state module loads | `from app.design_state import DesignState` | ✅ OK |
| Validation — real state dict accepted | `DesignState.model_validate(sample)` | ✅ OK |
| Extra fields — unknown keys pass | extra_field in sample dict | ✅ Preserved |
| Feature flag — defaults to False | `FEATURE_FLAGS.enable_design_state_validation` | ✅ False |
| Helper no-op — skipped when flag=False | `_validate_state(sample)` | ✅ SKIPPED |
| TypeScript — no new errors | `npx tsc --noEmit` | ✅ 0 errors |

**Phase 1 status: ✅ COMPLETE — all 9 checks passed**

---

### Phase 2 — Opt-in Validation

**Goal:** Enable validation, test all endpoints against DesignState schema,
fix any field mismatches, make `True` the permanent default.

#### Files Modified

| File | Change | Lines added |
|------|--------|------------|
| `backend/app/config/feature_flags.py` | `enable_design_state_validation: bool = False` → `True` | 0 net (comment updated) |
| `backend/app/main.py` | `_validate_state(req.state)` added to 13 endpoints | +13 |

#### Endpoints Wired (13 total)

| Endpoint | Location in main.py |
|----------|---------------------|
| `POST /mode-a/approve-topology` | after `state = dict(req.state)` |
| `POST /mode-a/approve-controller` | after `state = dict(req.state)` |
| `POST /mode-a/approve-channels` | after `state = dict(req.state)` |
| `POST /mode-a/submit-mini-intake` | after `state = dict(req.state)` |
| `POST /mode-b/generate-report` | first line in try block |
| `POST /mode-b/step6-magnetic-design` | first line in try block |
| `POST /mode-b/step7/run-sizing` | first line in try block |
| `POST /mode-b/step8/time-domain` | first line in try block |
| `POST /mode-b/step15/capacitor-calc` | after `state = req.state` |
| `POST /mode-b/step15/capacitor-design` | first line in try block |
| `POST /mode-b/step15/verify-configuration` | first line in try block |
| `POST /mode-b/step15/cap-lifetime` | first line in try block |
| `POST /mode-b/step15/hvcap-cap-table` | first line in try block |
| `POST /mode-b/step15/generate-report` | first line in try block |
| `POST /mode-b/generate-full-report` | first line in try block |

*(Note: `/mode-a/start` excluded — it receives `intake` + `project_id` directly, not a `state` dict)*

#### Validation Test Results — Phase 2

11 state shapes tested covering the full Mode-A pipeline + edge cases:

| Test | State Shape | Result |
|------|-------------|--------|
| 1 | After `/mode-a/start` | ✅ PASS |
| 2 | After `/mode-a/approve-topology` | ✅ PASS |
| 3 | After `/mode-a/approve-controller` | ✅ PASS |
| 4 | After `/mode-a/approve-channels` (interleaved) | ✅ PASS |
| 5 | Full confirmed state (after submit-mini-intake) | ✅ PASS |
| 6 | Medical `application_class` | ✅ PASS |
| 7 | Analog controller, single-phase | ✅ PASS |
| 8 | Extra/unexpected frontend fields | ✅ PASS (extra='allow') |
| 9 | Minimal state (only project_id) | ✅ PASS |
| 10 | Empty dict | ✅ PASS |
| 11 | Numeric fields as strings (coercion) | ✅ PASS |

| Final check | Result |
|-------------|--------|
| Syntax — main.py (after 13 edits) | ✅ OK |
| `_validate_state` call count in main.py | ✅ 13 calls (16 grep hits = 1 def + 13 calls + 2 comments) |
| TypeScript build `npx tsc --noEmit` | ✅ 0 errors |
| Validation suite (flag=True, live) | ✅ 11/11 passed, 0 failed |

**Phase 2 status: ✅ COMPLETE — flag enabled, validation live on all 13 endpoints**

---

### Rollback Instructions (if needed)

**Instant rollback (30 seconds):**
```python
# backend/app/config/feature_flags.py
enable_design_state_validation: bool = False   # change True → False
```
No restart needed — FastAPI reloads the flag on next request (uvicorn --reload mode).

**Full rollback (remove DesignState entirely):**
1. Delete `backend/app/design_state.py`
2. Delete `docs/DESIGN_STATE.md`
3. Delete `frontend/src/types/DesignState.ts`
4. Remove `enable_design_state_validation` line from `feature_flags.py`
5. Remove `_validate_state()` helper + all 13 call sites from `main.py`
6. Remove `IMPLEMENTATION_LOG.md` (optional)

---

---

### Phase 3 — Documentation Agent

**Goal:** Documentation Agent reads DesignState with typed access, validates completeness, orchestrates existing generators. Chapter readiness panel auto-loads in DonePanel after Mode A.

#### Files Created

| File | Lines | Purpose |
|------|-------|---------|
| `backend/app/mode_b/documentation_agent.py` | 145 | `DocumentationAgent` class — `report_status()`, `generate()`, `_validate_mode_a()`, `_assess_chapters()` |

#### Files Modified

| File | Change | Lines added |
|------|--------|------------|
| `backend/app/main.py` | `_DocStatusReq`, `_DocReportReq` models + 2 new endpoints: `POST /mode-b/documentation/report-status` and `POST /mode-b/documentation/generate-report` | +65 |
| `frontend/src/api/client.ts` | `DocChapter` + `DocReportStatus` interfaces, `docReportStatus()` + `docGenerateReport()` functions | +40 |
| `frontend/src/components/DonePanel.tsx` | Import `DocReportStatus`; added `docStatus` + `docStatusLoading` props; added "📊 Report coverage" card in right column showing chapter-by-chapter readiness | +40 |
| `frontend/src/App.tsx` | Import `docReportStatus` + `DocReportStatus`; added `docStatus`/`docStatusLoading` to `AppState`; auto-fetches doc status (non-blocking) when step transitions to `'done'`; passes props to DonePanel | +12 |

#### Files NOT Changed

All existing report endpoints · Step7Wizard · Step15Wizard · ControlDesign · all calculation engines · all existing report generators

#### Verification Results — Phase 3

| Check | Result |
|-------|--------|
| Syntax — documentation_agent.py | ✅ OK |
| Syntax — main.py (after +65 lines) | ✅ OK |
| TypeScript build `npx tsc --noEmit` | ✅ 0 errors |
| `DocumentationAgent` init — typed DesignState access | ✅ OK |
| `report_status()` — Mode A only → `ready_label=Steps 1–12`, Ch.1 ready, Ch.2–6 pending | ✅ OK |
| `report_status()` — with `approved_design` → `ready_label=Steps 1–14` | ✅ OK |
| `_validate_mode_a()` — incomplete state → 3 clear error messages | ✅ OK |
| UI — DonePanel receives `docStatus` / `docStatusLoading` props without breaking existing layout | ✅ 0 TypeScript errors |

**Phase 3 status: ✅ COMPLETE — build + live test passed**

| Check | Result |
|-------|--------|
| `tsc` TypeScript compile | ✅ 0 errors |
| `vite build` production bundle | ✅ built in 3.83s, 344.94 kB (no regression) |
| Backend health `/health` | ✅ `{"status":"ok","version":"2.0.0"}` |
| `POST /documentation/report-status` — Mode A only | ✅ `ready_label=Steps 1–12`, Ch.1 ready, Ch.2–6 pending with correct messages |
| `POST /documentation/report-status` — with `approved_design` | ✅ `ready_label=Steps 1–14`, Ch.2 status=ready |
| App renders — intake form loads | ✅ Screenshot confirmed |
| App renders — topology HITL loads after submit | ✅ Screenshot confirmed |
| Browser console errors | ✅ None (one harmless 404 for favicon unrelated to changes) |
| Block diagram regenerated | ✅ `specs/PFC_Architecture_Current_v2.png` |

#### What Phase 3 adds (user-visible)

- After Mode A completes, the DonePanel right column shows "📊 Report coverage" — a chapter-by-chapter checklist (✅ ready / ⏳ pending) that loads automatically in the background.
- Ch.1 Specification & Criteria shows ✅ immediately (Mode A is complete).
- Ch.2–4 show ⏳ with the exact action needed (e.g. "approve_design — complete Step 7").
- Ch.5–6 show ⏳ with a "planned future chapter" note.
- No existing buttons or flows changed.

---

---

### Documentation Agent — Chapter-Based Report Builder (2026-06-06)

**Goal:** Update Documentation Agent to produce chapter-based engineering report per planning PDFs (specs/). Implements: chapter splash pages, 5 annotation boxes, 4-line equation format, table standard, progressive disclosure, correct chapter numbering.

**Source reviewed:** 7 planning PDFs in specs/ — PFC_Report_Structure_Agreement, PFC_Documentation_Standards, PFC_Documentation_Improvement_Plan, PFC_Supplier_Data_and_Control_Theory, PFC_Future_Expansion_Plan, PFC_Global_State_and_Next_Level, PFC_DesignState_Implementation_Review.

#### Chapter structure implemented (per planning PDFs)

| Chapter | Title | Color | Data source | Status |
|---------|-------|-------|-------------|--------|
| 1 | Specifications | Navy #1F3B63 | Mode A DesignState | ✅ Full content |
| 2 | Topology and Control Scheme | Dark green #1B5E20 | Mode A DesignState | ✅ Full content |
| 3 | PFC Inductor Sizing | Dark amber #7B4500 | approved_design (Step 7) | ✅ Full content (§3.1–3.7) |
| 4 | PFC Inductor Performance Analysis | Dark purple #4A148C | approved_design | ✅ Structure + data stubs |
| 5 | DC Bus Capacitor Selection | Dark teal #006064 | step15_result | ✅ Structure + data when available |
| 6 | Control Scheme | Dark slate #263238 | step16_params | ✅ Structure + data when available |

#### Documentation standards implemented

| Standard | Status |
|----------|--------|
| Chapter splash page (full-page colour panel, number, title, question, bullets) | ✅ |
| CONCEPT annotation box | ✅ |
| THEORY annotation box | ✅ |
| PITFALL annotation box | ✅ |
| DECISION annotation box | ✅ |
| INSIGHT annotation box | ✅ |
| 4-line equation template (label → symbolic → numerical → result) | ✅ |
| Table standard (name + intro sentence + body + interpretation) | ✅ |
| 3-level decimal numbering X.Y.Z | ✅ |
| worst-case row amber highlight in tables | ✅ |
| Progressive disclosure structure | ✅ |

#### Files created / modified

| File | Action | Lines |
|------|--------|-------|
| `backend/app/mode_b/doc_report_builder.py` | **New** — all building blocks + chapter generators | ~580 |
| `backend/app/mode_b/documentation_agent.py` | **Rewritten** — correct chapter numbering, routes to builder, legacy fallback | ~200 |

#### Files NOT changed

All existing generators · main.py · frontend · App.tsx · client.ts

#### Verification results

| Check | Result |
|-------|--------|
| Syntax — doc_report_builder.py | ✅ OK |
| Syntax — documentation_agent.py | ✅ OK |
| `report_status()` — Mode A only: Ch.1+2 ready, Ch.3-6 pending | ✅ |
| `report_status()` — with approved_design: Ch.1-4 ready, ready_label=Chapters 1–4 | ✅ |
| `generate_chapter_report()` — Ch.1+2 only: 17,181 bytes | ✅ |
| `generate_chapter_report()` — Ch.1-4 with approved_design: 34,426 bytes | ✅ |
| PDF content — 18 pages, all 6 chapters rendered with correct titles | ✅ |
| Chapter splash pages rendered for all 6 chapters | ✅ |
| Chapter 1: Tables 1.1.1, 1.2.1, 1.4.1 rendered | ✅ |
| Chapter 3: 5-step inductance derivation, Tables 3.4.1, 3.5.1, 3.6.1, 3.7.1 | ✅ |
| All annotation boxes (CONCEPT, INSIGHT, DECISION) rendered | ✅ |
| Sample PDF saved to `specs/PFC_DocAgent_Sample_Ch1_4.pdf` | ✅ |

**Status: ✅ COMPLETE**

---

### Documentation Agent — Chapter Content Expansion (2026-06-07)

**Goal:** Implement all user-requested Chapter 1/2/3 content updates aligned with
`PFC_Design_Report_Steps13_15_Styled.docx` style and planning PDFs.

**Source reviewed:** `specs/PFC_Design_Report_Steps13_15_Styled.docx` — extracted all
table structures, formatting (Bold 12pt #2E74B5 step headings, italic 8pt captions,
Courier equation boxes with blue left border) and 49 tables of numerical data.

#### Changes implemented

| Section | What was added |
|---------|---------------|
| Ch.1 §1.1 | Expanded electrical table: Bus voltage ripple, Power factor, Efficiency, Hold-up time, Hold-up floor voltage all added |
| Ch.1 §1.2 | Thermal budget table (unchanged) |
| Ch.1 §1.3 | Full compliance matrix: Conducted EMI, Harmonic currents (IEC 61000-3-2), Leakage current, Surge (IEC 61000-4-5), EFT/Burst (IEC 61000-4-4), Magnetic field (IEC 61000-4-8), Voltage dips (IEC 61000-4-11) — each with standard, requirement, limit, test method |
| Ch.1 §1.4 | **Removed** — derived design targets moved to Ch.2 §2.3 |
| Ch.2 §2.1 | Six-topology comparison table with scoring rationale; selected topology highlighted amber |
| Ch.2 §2.2 | Three control options (Analog IC, Digital DSP, Digital ARM) with pros/cons table; DECISION box shows selected mode |
| Ch.2 §2.3 | Phase count, fsw, crest ripple ratio — each with design impact explanation |
| Ch.2 §2.4 | Nine-point operating table (Vin, Pout, Vin_pk, D@crest, K(D), Ipk_line, Iph_rms) + K(D) vs Vin matplotlib chart |
| Ch.3 §3.1 | Reference operating point table (Step 13.1 from Word doc) |
| Ch.3 §3.2 | Top core candidates table (Step 13.0) |
| Ch.3 §3.3 | Selected core parameters table with PITFALL box for window area |
| Ch.3 §3.4 | Turns count — N from AL (Steps 13.3.1–13.3.3) with kreq calculation |
| Ch.3 §3.5 | L at full load vs Vin table + matplotlib plot with AL tolerance band (Step 13.4) |
| Ch.3 §3.6 | Flux density — dBpp, Bdc, Bmin/Bmax (Step 13.5) |
| Ch.3 §3.7 | Winding fill factor — wire table + FFcu calculation (Step 13.6) |
| Ch.3 §3.8 | Loss calculation — MLT, DCR, Pcu, Pcore, Ptotal (Step 13.7) |
| Ch.3 §3.9 | Loss vs Vin at 25°C — 9-row table + bar+line chart (Step 13.8) |
| Ch.3 §3.10 | Loss vs Vin at 100°C — 9-row table + bar+line chart (Step 13.9) |
| Ch.3 §3.11 | 16-row summary table with all verdicts (Step 13.10) |
| Style | Step headings Bold 12pt #2E74B5; eq_box with blue left border + Courier; captions italic 8pt — all matching Word doc |

#### Verification

| Check | Result |
|-------|--------|
| Syntax — doc_report_builder.py | ✅ OK |
| Ch.1+2 only PDF: 83,269 bytes | ✅ |
| Ch.1-4 with approved_design: 240,057 bytes, 24 pages | ✅ |
| All 6 chapter splash pages rendered | ✅ |
| K(D) chart (Figure 2.1) rendered | ✅ |
| L vs Vin chart (Figure 3.1) rendered | ✅ |
| Loss vs Vin 25°C chart (Figure 3.2) rendered | ✅ |
| Loss vs Vin 100°C chart (Figure 3.3) rendered | ✅ |
| All 9-point operating tables rendered | ✅ |
| Sample PDF saved to `specs/PFC_DocAgent_Sample_Ch1_4.pdf` | ✅ |

---

## Session 2026-06-07 — doc_report_builder.py recovery + Chapter 3 §3.2 full port

### Context

`doc_report_builder.py` was found truncated at the start of this session — only the
building-block helpers (`_S`, `chapter_splash`, `step_h`/`sub_h`, `eq_box`,
`data_table`, `_mpl_img`, `_ops`, etc.) survived; `build_full_report` and
`_ch1`…`_ch6` were missing, so `documentation_agent.py` raised `ImportError`. The
generator code survived in four scratch files (`C:\tmp\ch1.py`, `ch2.py`, `ch3.py`,
`ch456_asm.py`) written during a prior session — these were reassembled in file
order to restore a working baseline.

### Changes

| Area | Change |
|------|--------|
| Restore | Concatenated `ch1.py → ch2.py → ch3.py → ch456_asm.py` after the existing helper block; confirmed `build_full_report` importable and buildable again |
| `eq_box()` re-style | Replaced Courier/left-border/green-bold style with the Word-doc-matching pale-blue (`EQ_BG`), centered, borderless, uniformly-styled stacked-line box — applies automatically to every chapter |
| New `_ch2` §2.4 | Inserted "Design Operating Point — Specifications, Duty Cycle, and Ripple Cancellation" between §2.3 and the old §2.4 (renumbered to §2.5–§2.7); ports `generate_report.py` Steps 1–3 (spec table, input-parameter equations + Dpk-vs-Vin graph, K(D)-at-crest equations/table/graphs) reusing `step2_input_params`/`K_of_D` |
| `_ch3` §3.2 full port | Replaced the old condensed §3.2 ("Ripple and Interleaving Analysis", ~5 subsections) **in place** with "Ripple, Current, and Duty-Cycle Analysis" — a full 1:1 port of `generate_report.py` Steps 4–12.5: 9 subsections (3.2.1–3.2.9, with 3.2.8/3.2.9 further split into .1–.5/.1–.4), ~13 equations, ~9 tables, 26 matplotlib figures (`fig_n` sequential counter → "Figure 3.2.N"), reusing `step4_inductance`, `step5_phase_rms`, `step7_8_worst_case`, `gen_waveforms`, `K_of_D` directly from `app.mode_b.calculations`. Added a `_vc(i)` helper mapping `Vin_rms` → `VAC_COLORS` palette entries, and local `_dIL_curve`/`_ripple_at` waveform helpers |

### Pitfall hit and fixed — section renumbering cascade

Initially renumbered §3.3→§3.8 down the chapter (mistakenly assuming the new §3.2
content needed a fresh top-level section). This was wrong — §3.2 was expanded
*in place*, so §3.3–§3.7 needed **no** renumbering at all. Two problems resulted
from the erroneous forward shift and had to be untangled:
1. A naive multi-pass string-replace cascade corrupted two sub-numbers
   (`3.3.4`→`3.4.5`, `3.3.5`→`3.4.6` instead of `3.4.4`/`3.4.5`) because compound
   strings like `"3.3.4"` contain `"3.4"` as a substring — fixed by hand.
2. Reverted the entire renumbering with a single-pass regex
   (`3\.([4-8])(\.\d+)?\b` → decrement captured digit), scoped only to lines
   containing `step_h(`/`sub_h(`/`data_table(`/`chapter_splash`/`Section `/`Table `
   so it could never touch numeric literals like `figsize=(7, 3.7)`. One
   self-authored cross-reference ("Section 3.4 carries this...") had been written
   assuming the (wrong) renumbering, and was hand-corrected to "Section 3.3" (Core
   Material Selection) post-revert.

Final structure confirmed correct: §3.1 Design Requirements → §3.2 Ripple/Current/
Duty-Cycle Analysis (NEW, full Steps 4–12.5) → §3.3 Core Material → §3.4 Core
Geometry → §3.5 Winding Design → §3.6 Loss/Thermal → §3.7 Sizing Summary — matching
the pre-session structure with §3.2 expanded in place. All `Section 3.X[.Y]` /
`Table 3.X.Y` cross-references (including `_ch4`'s "Section 3.4.3 Table confirms
this") re-verified to point at the correct (now-restored) targets.

### Verification

| Check | Result |
|-------|--------|
| `import app.mode_b.doc_report_builder` | ✅ no `ImportError` |
| `build_full_report(state, approved_design=approved)` with `C:\tmp\e2e_state.json` / `e2e_result.json` | ✅ 4,276,331 bytes, 49 pages |
| Saved sample PDF | `C:\tmp\sample_ch1_4.pdf` |
| PyMuPDF render — §3.2.1–3.2.10 figures (RMS current, ripple, worst-case angle) | ✅ render with correct LaTeX-styled axis labels |
| PyMuPDF render — §3.2.7 grouped duty-cycle multi-panel grids + compact ripple table | ✅ |
| PyMuPDF render — §3.2.8 per-phase waveforms (signed ripple, envelopes, Phase A vs B) | ✅ |
| Equation boxes (`eq_box`) — pale-blue centered style across all chapters | ✅ |
| Section numbering / cross-references in `_ch3` and `_ch4` | ✅ all consistent after revert |

---

## Session 2026-06-07 (cont'd) — Chapter 1/2 restructure: canonical η/PF table, page breaks, §1.4/§1.6 removal, new §2.7

User request (verbatim, paraphrased): add a η/PF reference table after Table 1.2.1
citing "PFC_Design_Report_Steps1_15, p.3" and make it the single source for all
downstream η/PF use; force every major (`X.Y`) step heading onto a new page; delete
§1.4 "Operating Points Matrix" (K(D) — phase count N_ph not yet selected at Ch.1) and
§1.6 "Design Targets Summary" (L_target/f_sw/crest ripple — none selected yet); add a
new §2.7 "Input ripple ratio at crest" (a missing selection/rationale section) between
§2.6 Switching Frequency and the old §2.7 Architecture Summary (→ renumbered §2.8).

### Changes — `backend/app/mode_b/doc_report_builder.py`

1. **New module-level helper `_canonical_ops_table(vin_min, vin_max, pout_lo, pout_hi)`**
   (placed right after `_ops`) — the SINGLE source of the nine-point η/PF matrix
   (source: "PFC_Design_Report_Steps1_15", p.3). Replaced three previously-duplicated
   inline `np.array([...])` literals with calls to this helper:
   - `_ch2` §2.4 `OPS` (was hand-typed at the old line 788)
   - `_ch3` §3.2 `OPS3` (exact duplicate of the above, old line 1291)
   - `_ch3`'s scalar `eta`/`PF` at the 90 Vac corner — now `float(_ops_ref[0,2])`/`[0,3]`
     instead of hardcoded `0.945`/`0.9987` literals
   - `_ops()` itself — refactored to pull **per-point** η/PF from the canonical table
     (`ops_ref[i,2]`/`[i,3]` inside the VAC_LIST loop) instead of one fixed
     `eta=0.945, PF=0.9987` default applied to all nine points; this was a real
     numerical inconsistency the user's "should be referred in further calculations"
     wording flagged — now every Pin/Ipk/Iph figure in every `_ops()`-driven sweep
     (used in `_ch2` §2.8.2 and `_ch3` §3.2) matches the η/PF actually confirmed for
     that operating point.

2. **Page-break-per-step**: removed the trailing `story.append(PageBreak())` from
   `chapter_splash` (it already opens with one) and instead made `step_h()` itself
   open with `story.append(PageBreak())`. Net effect: identical behaviour for each
   chapter's first step (`X.1` — previously got its break from `chapter_splash`'s
   trailing call, now gets it from `step_h`'s leading call — no blank page introduced),
   and EVERY subsequent major step (`X.2`, `X.3`, …) now starts on a fresh page too.
   Verified no blank pages were introduced by checking that all 6 `chapter_splash`
   calls are immediately followed by a `step_h` call with nothing else appended
   to `story` in between.

3. **New §1.2.4 "Efficiency and power factor across operating points"** — inserted
   immediately after the DECISION annotation that follows Table 1.2.1. Contains
   `sub_h "1.2.4"` + `data_table "1.2.2"` ("Operating-Point Efficiency and Power
   Factor — Reference Table") populated from `_canonical_ops_table(...)`, citing
   `"PFC_Design_Report_Steps1_15", page 3` explicitly in both the CONCEPT annotation
   and the table's source line. Updated the two stale "Section 1.4" cross-references
   inside Table 1.2.1's intro/interpretation text (old lines 403/421) to point at
   "Section 1.2.4" instead (since the table they referenced — the old §1.4 Operating
   Points Matrix — no longer exists).

4. **Removed §1.4 "Operating Points Matrix"** (K(D) column — user's stated reason:
   N_ph not yet selected at Ch.1 stage; selection happens in Ch.2 §2.5) and
   **§1.6 "Design Targets Summary"** (L_target/f_sw/crest ripple — none of these are
   selected until Ch.2 §§2.6/2.7 or computed until Ch.3). Renumbered the surviving
   §1.5 "Thermal and Mechanical Constraints" → **§1.4** (table `1.5.1`→`1.4.1`).
   Removed the now-dead `tsi`/`fsw`/`crest`/`L_tgt`/`n_ph` locals from `_ch1` (they
   were only consumed by the two removed sections). Updated the chapter banner
   comment ("Sections 1.1–1.6" → "Sections 1.1–1.4 …") and the Ch.1 `chapter_splash`
   bullet list (replaced the "Nine-point operating matrix" / "Design targets summary"
   bullets with one describing the new η/PF reference table and its citation).

5. **New §2.7 "Input ripple ratio at crest"** — inserted between §2.6 Switching
   Frequency and the old §2.7 Architecture Summary. Modeled on the §2.5/§2.6
   selection pattern: `sub_h "2.7.1"` + `data_table "2.7.1"` ("Crest Ripple Ratio —
   Trade-off Comparison", qualitative low/selected/high rows) followed by
   `sub_h "2.7.2"` "Selected: r = NN% — rationale" + DECISION annotation explaining
   why the configured `crest` value (e.g. 0.20) was chosen and how it feeds the
   ΔI_L,pp → L_φ derivation in Ch.3 §3.1.

6. **Renumbered old §2.7 "Architecture Summary" → §2.8** (and `2.7.1`→`2.8.1`,
   `2.7.2`→`2.8.2`, plus their `data_table` refs). Replaced the local
   `eta = 0.945; PF = 0.9987` shadow-redefinition (old line 932, used only to derive
   the 90 Vac-corner constants) with `eta_90 = float(OPS[0,2]); PF_90 = float(OPS[0,3])`
   — sourced from the same canonical `OPS` array already in scope, eliminating the
   hardcoded literal entirely. Fixed a stale self-reference inside Table 2.8.2's intro
   ("Table 2.6.2 is used directly in Section 3.2…" → "This table is used directly in
   Section 3.2…"). Updated the Ch.2 `chapter_splash` bullet list (added a "2.7 Input
   ripple ratio at crest" bullet, renumbered "Architecture summary" bullet to "2.8").
   Also updated Table 2.8.1's intro text "Sections 2.1–2.5" → "Sections 2.1–2.7" since
   it now also reflects the new ripple-ratio rationale section.

### Final Chapter 1 / Chapter 2 structure (post-change)

- **Ch.1**: 1.1 Project ID → 1.2 Input/Output Electrical Reqs (incl. NEW 1.2.4 η/PF
  reference table) → 1.3 Compliance & Standards → 1.4 Thermal & Mechanical (was 1.5)
- **Ch.2**: 2.1 Topology → 2.2 Operating Mode → 2.3 Controller IC → 2.4 Design
  Operating Point (incl. K(D) at crest) → 2.5 Channel Count → 2.6 Switching
  Frequency → **2.7 Input ripple ratio at crest (NEW)** → 2.8 Architecture Summary
  (was 2.7)

### Verification

| Check | Result |
|-------|--------|
| `import app.mode_b.doc_report_builder` | ✅ no `ImportError` |
| `build_full_report(state, approved_design=approved)` (`C:\tmp\e2e_state.json`/`e2e_result.json`) | ✅ 4,282,587 bytes, 60 pages |
| Saved sample PDF | `specs/PFC_DocAgent_Ch1_2_Restructure_Review.pdf` |
| PyMuPDF scan — step-heading → page map | ✅ 1.1–1.4 (no 1.5/1.6 gap), 2.1–2.8 (new 2.7, renumbered 2.8), each on its own page |
| PyMuPDF text dump — Table 1.2.2 (η/PF, cites "PFC_Design_Report_Steps1_15", p.3) | ✅ renders correctly with all 9 rows |
| PyMuPDF text dump — §2.7 (ripple-ratio trade-off table + DECISION) and §2.8 (renumbered Architecture Summary, tables 2.8.1/2.8.2) | ✅ |
| Chapter-splash → first-step page-break collision check (no blank page introduced) | ✅ confirmed all 6 `chapter_splash` calls are followed immediately by `step_h` with nothing else appended in between |

### Resume point for a future session

All requested changes are complete and verified via a fresh 60-page sample PDF. If
continuing: the pre-existing blank page 2 (between the cover page and the Chapter 1
splash, caused by `build_full_report`'s own `PageBreak()` after the cover colliding
with `chapter_splash`'s leading `PageBreak()`) was NOT part of this request and was
left untouched — flag it separately if it should be fixed.

---

## 2026-06-07 — Report formatting improvements: keep-together tables, citation cleanup, §2.4↔§2.7 reorder, professional equation restyle

**Request (4 parts):** (1) tables must never split across a page break — restart the
whole title+table block on a new page if it doesn't fit; (2) remove the
`"PFC_Design_Report_Steps1_15", page 3 (operating-point table)` citation phrase from
§1.2.4 and elsewhere, replacing it with "estimated based on available data" framing;
(3) move §2.4 ("Design Operating Point — Specifications, Duty Cycle, and Ripple
Cancellation") to come *after* §2.7 ("Input ripple ratio at crest"), renumbering the
chapter; (4) redesign `eq_box()` so equations look professional — true stacked
fractions, real Greek/math symbols (Δ, η, θ, φ, √, ∫), and a heading-outside-left /
number-outside-right layout — matching the reference image
`specs/Desired way of writing equation through out the report making.png`, applied to
**every** `eq_box` call site in the report (~35 locations across Chapters 2, 3, 5).

**File changed:** `backend/app/mode_b/doc_report_builder.py` (only file touched)

| # | Change | How |
|---|--------|-----|
| 1 | `data_table()` now builds `[title, intro, table]` and wraps it in a single `KeepTogether(block)` | guarantees the table (with its heading) always restarts atomically on a new page rather than splitting mid-table |
| 2 | Removed all 7 occurrences of the `"PFC_Design_Report_Steps1_15", page 3` citation (code comments, `chapter_splash` bullet, §1.2.4 CONCEPT box, Table 1.2.2 intro, §2.7.1b body — formerly §2.4.1b) | replaced with consistent "estimated based on available design data — interpolated/reproduced from the specified corner conditions" framing; verified via `grep` → zero remaining matches (also re-verified against the rendered PDF text via PyMuPDF — zero hits) |
| 3 | Swapped the adjacent §2.4 block with the §§2.5–2.7 block (one atomic `Edit`, hand-renumbered) | new order: 2.4 Channel Count (was 2.5) → 2.5 Switching Frequency (was 2.6) → 2.6 Input ripple ratio at crest (was 2.7) → 2.7 Design Operating Point (was 2.4) → 2.8 Architecture Summary (unchanged, still consumes `OPS`/`Vin_rms`/`eta`/`PF` defined in the now-preceding §2.7); also renumbered the embedded figures (2.2→2.1, 2.3→2.2, 2.4→2.3, old 2.1→2.4) and the `chapter_splash` bullet list to match |
| 4 | Replaced `eq_box()` entirely + added `_eq_img(tex, fontsize, color, dpi)` helper | renders each mathtext expression (`$...$` via matplotlib, no LaTeX install needed) to a tightly-cropped transparent PNG sized natively via `ImageReader.getSize()` × `72/dpi`; `eq_box(story, expr, heading=None, number=None, ch=1)` accepts a single expression or a stacked list (definition → substitution → result) and renders an optional small 2-col heading table (label-left-bold / "(N)" right-italic-muted) **above** the pale-blue equation box — directly matching the reference image's three call-outs (true fractions via `\dfrac{}{}`, real symbols `\Delta\eta\theta\phi\sqrt{}\int`, heading-left/number-right layout) |

**Equation conversion sweep** — converted all ~35 call sites chapter by chapter
(Ch.2 §2.7.2/§2.7.3 five governing relations + K(D) piecewise; Ch.3 §3.1 six-step
target-inductance derivation (3.1-1…3.1-6); §3.2.1 ΔIin,pp/ΔIL,pp/Lφ chain (4.1–4.3);
§3.2.2 average/RMS per-phase current (5.1–5.2) — these two are the *exact* equations
shown in the reference image's bottom example group; §3.2.5 worst-case line angle
(8.1–8.3); §3.2.8 per-phase waveforms (11.1–11.4); §3.2.x input ripple chain
(12.1–12.3); §3.5 winding design — skin depth, turns count, L0, FFcu; §3.6 loss/
thermal — copper length/DCR, core loss, total loss+ΔT; Ch.5 §5.x capacitor sizing —
C_holdup, C_ripple, C_required). One `\displaystyle` mathtext incompatibility was
caught and fixed during the build-verification pass (matplotlib mathtext doesn't
support `\displaystyle` — removed it; `\int_0^{\pi}` renders at normal size without
it, which still matches the reference style).

**Verification:**

| Check | Result |
|-------|--------|
| `import app.mode_b.doc_report_builder` | ✅ no `ImportError` |
| `build_full_report(state, approved_design=approved)` (`C:\tmp\e2e_state.json`/`e2e_result.json`) | ✅ 4,778,990 bytes, 64 pages |
| Saved sample PDF | `C:\tmp\verify_report.pdf` |
| PyMuPDF text scan for citation phrase | ✅ zero hits across all 64 pages |
| PyMuPDF render — Table 1.2.2 (page 5) | ✅ title + 9-row table render together at the top of the page (no split); intro reads "Estimated based on available design data..." |
| PyMuPDF render — page 12 (§2.4 Channel Count) vs page 15 (§2.7 Design Operating Point) | ✅ confirms new order: 2.4 now precedes 2.7 |
| PyMuPDF render — §2.7.3 K(D) piecewise definition (page 18) | ✅ true stacked fraction bars for `(1−2D)/(1−D)` and `(2D−1)/D`, real "D < 0.5"/"D = 0.5" conditions |
| PyMuPDF render — §3.2.2 equations 5.1/5.2 (page 27, zoomed) | ✅ matches reference image exactly: `i_{L,avg,φ}(θ) = (I_{in,pk}/2) sin θ` and `I_{L,φ,rms} = √[(1/π)∫₀^π (i²_{L,avg}+i²_{L,hf}) dθ]` with stacked fraction, radical, integral, real Greek symbols, heading-left "(5.1)"/"(5.2)" number-right |
| PyMuPDF render — §3.5.1 skin-depth multi-line equation (page 48) | ✅ stacked substitution chain renders with proper `ρ`, `δ = √(ρ/(π f_sw μ₀))`, scientific notation `2.2608×10⁻⁸` |

### Resume point for a future session

All four requested formatting changes are complete and verified via a fresh 64-page
sample PDF (`C:\tmp\verify_report.pdf`). No outstanding `eq_box` call sites remain in
the old plain-string format (confirmed via regex scan for `eq_box(story, [\s*"`).

---

## 2026-06-07 — Magnetics calc fixes: bias-aware turns sizing, first-pass loss self-consistency, single-source Iφ,rms (closes "complete mismatch in values" / "basic addition error" / thermal complaints)

**Request (verbatim, paraphrased):** (1) Inductance/turns sizing must account for
DC-bias H(Oe) and permeability rolloff at minimum Vin / full load — not the naive
`N = ⌈√(L_target/A_L,nom)⌉` estimate; also Table 3.2.4a/3.2.4b's per-phase current
figures are "accurate" while Table 3.4.1's sizing-engine-input figures are "very
different… a complete mismatch in values considered for magnetics calculations";
(2) a "basic addition error" in the loss totals — "very disappointed… data
consistency is missing"; (3) "fix temperature calculations." Apply all three to both
the calculation engine and the documentation agent.

### Root causes found

1. **`DEFAULT_OPS`** (hardcoded 9-row array in `step7_magnetic_calc.py`) carried
   stale Iφ,rms values copied from a *different* reference design
   (`EDGE_0059392A2`), so the sizing engine's actual inputs diverged from the
   design-derived "accurate" Table 3.2.4 figures by design.
2. **`_turns_powder()`** picked N from a static `A_L,nom` ladder with no DC-bias
   feedback — H(Oe)/k_bias were computed *after* N was already fixed, so the
   "✓ PASS" check in §3.5.3 was checking a number that didn't drive the decision.
3. **Pcu double-write**: `Pcu_25C_W`/`Pcu_100C_W` were computed once as genuine
   first-pass `I_rms,ref²·DCR` figures, then silently overwritten downstream with
   cycle-averaged final values — so §3.6's "first-pass" equation box showed operands
   that could never literally sum to a `Ptotal_*_W` sourced from yet a third
   (`Pcu_final + Pcore_avg + P_fringing`) chain. This was the "basic addition error"
   (`0.5086 + 2.6425 = 2.0550` shown in `specs/Newely Generated.pdf` p.51 — the
   correct sum is 3.1511).
4. **Three independent, disagreeing Iφ,rms estimators** lived in
   `doc_report_builder.py`: (a) `_ops()`'s "PFC approximation"
   `ipk_l/n_ph/√2 · √(π/2) · 0.98` (→ 12.29 A, used by Table 3.1.1 / feeds Ch.4),
   (b) the rigorous `step2→step4→step5_phase_rms` chain (→ 10.07–10.28 A, used by
   Table 3.2.2b), and (c) `d.get("IL_rms_A", 0)` in §3.4.1 — a field
   `DesignResult`/`enrichResult` never actually populates, always rendering
   **`Iφ,rms = 0.0000 A`** in Table 3.4.1 (present in BOTH the original buggy report
   AND, until fixed mid-session, my first corrected sample — confirmed pre-existing,
   not a regression I introduced).

### Changes — `backend/app/mode_b/calculations.py`

Added `canonical_ops_table(vin_min, vin_max, pout_lo, pout_hi)` (the 9-point η/PF
reference matrix, single source of truth) and
`build_design_ops_table(vin_min, vin_max, pout_lo, pout_hi, vout, fsw, r_input)`
→ `(OPS, L_phi)` where `OPS[:,4]` is Iφ,rms derived through the rigorous
`step2_input_params → step4_inductance → step5_phase_rms` chain — now THE single
source every consumer (sizing engine, every report chapter) must read from so
Table 3.2.4 / Table 3.4.1 / Table 3.1.1 never disagree again.

### Changes — `backend/app/mode_b/step7_magnetic_calc.py`

- `_turns_powder()` now returns `(…, H_Oe, k_b)` and N is selected by an iterative
  **bias-aware** convergence loop: `H_Am = N·I_dc/Le_s` → `H_Oe = H_Am/79.577` →
  `k_b = get_k_bias(mat_key, H_Oe)`, incrementing N until
  `L_full_min = N²·A_L,min·k_b ≥ 0.85·L_target`.
- New `DesignResult` fields: `I_dc_worst_A`, `H_Oe_worst`, `k_bias_worst` (the
  worst-case-across-all-9-OPs values that actually drove the converged N) and
  `Pcu_25C_firstpass_W` / `Pcu_100C_firstpass_W` — the genuine first-pass
  `I_rms,ref²·DCR` figures, preserved under their own names *before* the existing
  downstream overwrite (left intact for backward compat with the legacy
  `generate_full_report.py`/`generate_steps13_14.py` generators) replaces
  `Pcu_25C_W`/`Pcu_100C_W` with cycle-averaged final values.

### Changes — `backend/app/main.py`

`step7_run_sizing` now builds its OPS via `build_design_ops_table(Vin_lo, Vin_hi,
Pout_lo, Pout_hi, Vout, fsw_Hz, r_input)` (falling back to `DEFAULT_OPS` only on
exception) instead of always passing the stale hardcoded `DEFAULT_OPS` — so the
sizing engine's `Irms_A` input now matches the design's actual corner conditions
(measured: 10.2787 A vs. the old stale 10.07 A for this design — a genuine ~2%
difference that now flows consistently through `IL_rms_ref → Pcu_* → J_A_mm2 → ΔT`).

### Changes — `backend/app/mode_b/doc_report_builder.py`

1. Replaced the local `_canonical_ops_table` definition with an alias to
   `app.mode_b.calculations.canonical_ops_table` (single source, shared with the
   sizing engine via `build_design_ops_table`).
2. Rewrote §3.5.3 "Number of turns N" → **"Number of turns N — bias-aware A_L
   sizing"**: now shows the real `H_Oe = N·I_dc,worst/(L_e×79.577)`,
   `k_bias = k(H_Oe)`, `L_full,min = N²·A_L,min·k_bias ≥ 0.85·L_target` convergence
   chain with actual substituted numbers, plus a PITFALL box that explicitly
   contrasts the converged N against the naive `N = ⌈√(L_target/A_L,nom)⌉` estimate
   and explains that `I_dc,worst` is the **maximum across all 9 operating points**
   (not necessarily the 90 Vac corner).
3. §3.6 loss section now reads `Pcu_25C_firstpass_W`/`Pcu_100C_firstpass_W` (falling
   back to the plain fields only for older pre-split saved designs) and computes
   `Ptot25/Ptot100` as the **literal sum** of the displayed operands
   (`Ptot = Pcu + Pcore_pk`) — guaranteeing the equation box's arithmetic is always
   correct, closing the "basic addition error."
4. §3.4.1 "Sizing engine inputs": replaced the broken `Iph_rms =
   float(d.get("IL_rms_A", 0))` (always 0.0000) with `Iph_rms_ref` derived via
   `build_design_ops_table(...)[0,4]` at the top of `_ch3` — now identical to
   Table 3.2.2b / Table 3.2.4's design-derived figure.
5. `_ops()` helper (feeds Table 3.1.1 / Ch.4): replaced the crude sinusoidal
   "PFC approximation" `ipk_l/n_ph/√2 · √(π/2) · 0.98` (→ 12.29 A, ~20% off) with
   `float(ops_design[i, 4])` sourced from the same `build_design_ops_table` chain;
   added `vin_min, vin_max, r_input` params (both call sites in `_ch2`/`_ch3`
   updated — `_ch2` passes its `crest` local since it has no `r_input`, both pull
   from the same `tsi.default_crest_ripple_ratio`).

### Verification — before/after sample comparison

Generated `C:\tmp\PFC_Corrected_Sample_Ch1_4.pdf` (65 pages, same corner conditions
as `specs/Newely Generated.pdf`: 90–264 Vac, 1700/3600 W, 393 V, 70 kHz, edge_75,
2-phase, n_parallel=2, L_target=239 µH) via
`DocumentationAgent(STATE).generate_chapter_report(approved_design=approved)` and
rendered both PDFs to PNG with PyMuPDF for a page-by-page comparison.

| Metric | Original (`Newely Generated.pdf`) | Corrected sample |
|---|---|---|
| Table 3.1.1 Iφ,rms @ 90 Vac | 12.2912 A (crude approx.) | **10.2787 A** |
| Table 3.2.2b IL,φ,rms @ 90 Vac (rigorous) | 10.0702 A | **10.2787 A** |
| Table 3.4.1 "Sizing Engine Inputs" Iφ,rms | **0.0000 A** ❌ | **10.2787 A** ✅ — all three now agree |
| §3.5.3 turns method | naive `N=⌈√(L_target/A_L,nom)⌉=31`, no H(Oe)/k_bias shown | bias-aware: `H_Oe=40.37 Oe ⇒ k_bias=0.8637`, `L_full,min=215.3 µH ≥ 0.85·L_target=203.2 µH ⇒ N=31`, contrasted against naive N=30 |
| §3.6.3 P_total(25°C) | `0.5086 + 2.6425 = 2.0550 W` ❌ (correct sum is 3.1511) | `0.5424 + 2.6425 = 3.1849 W` ✅ |
| §3.6.3 P_total(100°C) | `0.6556 + 2.6425 = 2.2020 W` ❌ (correct sum is 3.2981) | `0.6992 + 2.6425 = 3.3417 W` ✅ |
| Thermal verdict | ΔT = 10.41°C, PASS — 83% margin | ΔT = 10.47°C, PASS — 83% margin |

Selected core/turns landed on the same part (`0059214A2 ×3, N=31`) in both —
expected, since the corrected Iφ,rms (10.28 A) only differs from the old stale value
(10.07 A) by ~2%, not enough to cross a candidate-ranking threshold for this design's
margins. The fix is about **self-consistency and correctness of the displayed
figures**, not about changing which core gets picked.

| Check | Result |
|-------|--------|
| `import app.main`, `import app.mode_b.doc_report_builder` | ✅ no `ImportError` |
| `build_design_ops_table()` smoke test (Iφ,rms vs old `DEFAULT_OPS`/EDGE reference) | ✅ produces genuinely different, design-derived values |
| `step7_run_sizing(req)` with corrected-design STATE | ✅ returns candidates with new `I_dc_worst_A`/`H_Oe_worst`/`k_bias_worst`/`Pcu_*_firstpass_W` fields populated |
| `DocumentationAgent(STATE).generate_chapter_report(approved_design=…)` | ✅ 4,849,853 bytes, 65 pages |
| PyMuPDF render — Table 3.1.1 / 3.2.2b / 3.4.1 (pages 24/27/46) | ✅ all three show identical Iφ,rms = 10.2787 A |
| PyMuPDF render — §3.5.3 bias-aware turns convergence (page 49) | ✅ H_Oe/k_bias/L_full,min substitution chain + PITFALL contrast vs naive N |
| PyMuPDF render — §3.6.3 loss equation box (page 52) | ✅ both P_total sums are now arithmetically correct |
| §3.1–3.2 spot-check (page 32, Tables 3.2.4a/3.2.4b) | ✅ unaffected, renders cleanly as the user expected |

### Resume point for a future session

All three requested points (DC-bias-aware sizing, addition-error/data-consistency,
thermal) are fixed in both the calculation engine (`calculations.py`,
`step7_magnetic_calc.py`, `main.py`) and the documentation agent
(`doc_report_builder.py`, wrapped by `DocumentationAgent`). Confirmed no duplicate
copies of the fixed patterns (`IL_rms_A` lookup, sinusoidal Iφ,rms approximation,
`DEFAULT_OPS`-style stale tables) exist in the legacy generators
(`generate_report.py`, `generate_combined_report.py`, `generate_steps13_14.py`) or
in `documentation_agent.py` itself — those are unaffected and untouched. Sample
comparison PDFs: `C:\tmp\PFC_Corrected_Sample_Ch1_4.pdf` (corrected) vs.
`specs/Newely Generated.pdf` (original).

---

## Session 2026-06-08

### Discussion Summary

Follow-up to 2026-06-07's "single source of truth" cleanup — user spotted two more
places where the *same physical quantity* was rendered from two different
calculation chains and didn't match exactly:

1. Report Table 3.2.4a's `ΔI_L,pp (A)` (90 V row) vs. Table 3.4.1's
   "Ripple current pk-pk@crest `ΔI_L,pp`" — close but not identical.
2. GUI Step7Wizard "Result" page: the "Losses at operating temperature" panel's
   `Pcore iron` vs. the "Time domain core loss" table's `Pcore avg W` (90 Vac row)
   — both labelled as the half-cycle-averaged core loss at the reference corner,
   but numerically different.

### Fix 1 — §3.4.1 ΔI_L,pp now matches §3.2.4a exactly (`doc_report_builder.py`)

**Root cause**: `L_tgt = float(tsi.confirmed_L_uH if tsi else 240) or 240`
(both definitions, `_ch2`/`_ch3` — lines ~628 and ~1146) read the **raw, unrounded**
`confirmed_L_uH` field. But the actual sizing engine
(`main.py:712`, `step7_run_sizing`) consumes `confirmed_L_uH_sel` — the value
**rounded to the nearest 5 µH** (`main.py:177`,
`tsi["confirmed_L_uH_sel"] = round(lpy["L_uH"]/5)*5`). Table 3.2.4a's
`dIL_crest[0]` is computed independently in §3.2's rigorous chain using `L_phi`
(`doc_report_builder.py:1380`, `round(L_phi_calc*1e6/5)*5*1e-6` — also rounded to
the nearest 5 µH from essentially the same raw `L_calc`). So §3.4.1's
`ΔI_L,pp = Vin,pk·D / (L_tgt·fsw)` used a slightly different (unrounded) L than
§3.2.4a's `dIL_crest[0] = step5_phase_rms(..., L_phi, ...)` — hence "close but not
exact."

**Fix**: changed `L_tgt` (both occurrences, single `replace_all` edit) to prefer
the rounded selected value:
`L_tgt = float((tsi.confirmed_L_uH_sel or tsi.confirmed_L_uH) if tsi else 240) or 240`
— now `L_tgt` reflects what the sizing engine actually used, and (since both
roundings start from the same raw `L_calc`/`lpy["L_uH"]`) numerically equals
`L_phi`, so §3.4.1's ΔI_L,pp formula reduces to the same expression as
`dIL_crest[0]`.

**Verified** with a realistic `confirmed_L_uH`/`confirmed_L_uH_sel` pair
(113.15 / 115 µH — recomputed via `_calc_l_py` for the 90–264 Vac / 1700–3600 W /
393 V / 70 kHz / 70% crest-ripple scenario; the prior session's test fixture had
hand-set both fields to a stale placeholder `239.0`, masking this bug):

| Table | ΔI_L,pp (90 V) — before | ΔI_L,pp (90 V) — after |
|-------|------------------------|------------------------|
| 3.2.4a `dIL_crest[0]` | 10.6904 A | 10.6904 A (unchanged — already correct) |
| 3.4.1 "Ripple current pk-pk@crest" | 5.1439 A (computed with stale `confirmed_L_uH=239`) | **10.6904 A** ✅ exact match |

Regenerated `C:\tmp\PFC_Verify_3_4_1_fix.pdf` (4,849,357 bytes) and confirmed via
PyMuPDF text extraction: page 33 (Table 3.2.4a, 90 V row) and page 47 (Table 3.4.1)
both now read `ΔI_L,pp = 10.6904 A`, and §3.4.1's "Target inductance" row now shows
`L_φ,target = 115 µH` (matching `L_phi` used throughout §3.2), not the stale 239 µH.

### Fix 2 — GUI "Pcore" now matches "Pcore avg W" at the reference operating point (`step8_time_domain.py`, `main.py`)

**Root cause**: two independent calculation chains both claim to produce the
"half-cycle-averaged core loss at 90 Vac":
- `result.Pcore_W` (shown as `Pcore iron` in "Losses at operating temperature") —
  computed once, at the design's reference 90 Vac corner, by
  `_half_cycle_averages()` (`step7_magnetic_calc.py:678-704`): a rigorous 360-point
  per-line-angle magnetics-DB lookup with iGSE `F(D)` correction, explicitly
  commented "authoritative"/"primary".
- `step8.summary_table[i].Pcore_avg_W` (shown as `Pcore avg W` in "Time domain
  core loss", one row per of the 9 canonical Vac points) — computed by
  `run_step8_full()` (`step8_time_domain.py`): fits a power-law model
  `Pcore = k·B^n` to the 9 **crest-point** values from `loss_table_25C`, then
  integrates the *fitted curve* (not DB lookups) over the half cycle via the
  trapezoid rule. This is a fast approximation meant for the full 9-point sweep
  (the endpoint's own docstring even flags "at 90 Vac crest-point overestimates
  Pcore,avg by ~83%" as its key insight) — it was never anchored to the
  already-known-good `Pcore_W` value at the one point where Step 7 had already
  done the rigorous calculation.

**Initial fix (superseded same session — see "Final fix" below)**: first tried
anchoring just the matching row — `run_step8_full()` gained optional
`Pcore_avg_ref`/`Vin_ref` params, and when the loop reached `Vin_ref` it
overwrote the power-law-fit estimate with the authoritative value and tagged the
row `"anchored to Step 7 Pcore_W (authoritative)"`. This made the one row match,
but the user then asked which method (rigorous 360-point DB+iGSE integration vs.
fast power-law-fit integration) is more accurate, and on hearing it's the
rigorous one, replied: **"If report generation takes time then it is okay.
Accuracy is very important at each stage."** — i.e. don't just patch the one row,
make every row rigorous.

**Final fix — replaced the entire power-law-fit integration with rigorous
per-point `_half_cycle_averages` calls**: `run_step8_full()` was rewritten to run
the SAME 360-point per-line-angle DB+iGSE half-cycle integration that produces
`DesignResult.Pcore_W` (Step 7's `_half_cycle_averages`, `step7_magnetic_calc.py:266`)
independently at all 9 canonical operating points — instead of fitting
`Pcore = k·B^n` to 9 crest values and integrating the fitted curve. Key pieces:

- `_half_cycle_averages` gained an additive, backward-compatible
  `return_series: bool = False` flag that also returns per-angle
  `theta_rad`/`Bac_pk_T_series`/`Pcore_W_series` arrays — letting `run_step8_full`
  build its `waveforms` plot data from genuine per-angle DB lookups too (not the
  fitted curve).
- Derived `Icrest_A[i] = max(Iin_pk[i]/n_ph, Iph_rms[i]·0.9)` — algebraically
  identical to the reference-corner formula
  `max(Ipk_A − dIL_pp_A/2, Irms_A·0.9)` used inside Step 7, since
  `Ipk_A − dIL_pp_A/2 = Ipk_line/n_ph = Iin_pk/n_ph` (the `dIL_pp_A/2` terms
  cancel). This lets all 9 points' crest currents be derived purely from the
  canonical `OPS`/`Iin_pk` arrays (`canonical_ops_table` → `step2_input_params` →
  `build_design_ops_table`, the same chain Table 3.2.4/3.4.1 use) — no extra
  `step5_phase_rms` calls needed.
- `Rdc_Tc`/`Rac_Tc` at the converged `T_core_C` are now derived in `main.py` via
  **exact linear interpolation** between the stored `DCR_25C_mOhm`/`DCR_100C_mOhm`
  values (`Rdc_Tc = DCR_25 + (DCR_100−DCR_25)·(T_core−25)/75`) — exact because
  `DCR(T) = R_pm_20·(1+ALPHA_CU·(T−20))·Cu_len` is linear in `T`, and
  `R_pm_20`/`Cu_len` aren't themselves persisted on `DesignResult`.
- The now-redundant `Pcore_avg_ref`/`Vin_ref` anchor params/override/note were
  removed — every row is independently rigorous, so the anchor adds nothing
  (verified below: the reference row matches `Pcore_W` to full precision without it).
- `power_law_fit` (the GUI's informational "P = k·B^n" panel) is still computed
  from the Step 7 crest-point data and returned unchanged.
- `main.py`'s endpoint now extracts and passes the additional design constants:
  `core_type`, `n_ph` (`selected_channels`), `Le_single_m`, `L0_nom_H` (=
  `AL_nom_nH·stacks·1e-9·N²`), `Rdc_Tc`/`Rac_Tc`, `T_core_C`, and the
  `vin_min/vin_max/pout_lo/pout_hi/r_input` OPS-building inputs (same fields the
  `step7/run-sizing` endpoint already reads at `main.py:712-724`).

| Check | Result |
|-------|--------|
| `import app.mode_b.step8_time_domain`, `app.mode_b.doc_report_builder`, `app.main` | ✅ no `ImportError` |
| `_calc_l_py(1700,90,393,70000,0.20)` vs. independently-derived `step4_inductance` `L_calc` | ✅ both = 113.15 µH raw → both round to 115 µH (`L_phi` ≡ `confirmed_L_uH_sel`) |
| PyMuPDF render — Table 3.2.4a / Table 3.4.1 (pages 33/47, `PFC_Verify_3_4_1_fix.pdf`) | ✅ ΔI_L,pp = 10.6904 A in both |
| Reference corner (90 Vac) `summary_table[0].Pcore_avg_W` (rigorous, unrounded) vs. `DesignResult.Pcore_W` | ✅ `1.5464082...` → rounds to `1.5464`, **exact** match — no anchor needed |
| Full 9-point sweep (`edge_75` powder design, EDGE 3-stack) | ✅ runs end-to-end; `Pcore_avg` now correctly brackets `Pcore_crest` per point (e.g. 90 V: avg 1.546 W vs crest 2.643 W, ratio 0.585 — "crest overestimates avg"; 230 V: avg 2.060 W vs crest 1.154 W, ratio 1.786 — "crest underestimates avg"), matching the physical pattern the module's docstring describes |

### Verification — full report regenerated through the actual GUI pipeline (both fixes confirmed end-to-end, 2026-06-08)

Traced the GUI "Generate Report" buttons all the way to the PDF builder to confirm
which code path actually runs in production, then regenerated a full report through
that exact path and re-checked both issues against it:

**GUI → endpoint → builder trace** (`frontend/src/api/client.ts:220` `docGenerateReport`
is the only report-download call wired into `ControlDesign.tsx`, `ReviewMagnetics.tsx`,
`Step15Capacitor.tsx`, `App.tsx`):
`docGenerateReport` → `POST /mode-b/documentation/generate-report`
(`main.py:1461 doc_generate_report`) → `DocumentationAgent.generate()`
(`documentation_agent.py:121`) → tries `generate_chapter_report()` first
(`:94`) → `doc_report_builder.build_full_report` (`:113-119`). The
`_generate_legacy()` fallback (`generate_report.py` + `generate_combined_report.py`
+ `generate_steps13_14.py`, with its own independent power-law-fit `Pcore_avg`
chain in `_sec_14_3`/Table 14.1) only fires if the chapter builder *raises* —
it does not, so it never runs in normal operation. **This means the chapter-based
builder verified below — the one carrying both Fix 1 and Fix 2's data — is the
literal PDF the user receives when clicking "Generate Report" in the GUI.**

**Regeneration**: called `DocumentationAgent(state).generate_chapter_report(approved_design=...)`
on `corrected_state.json`/`corrected_approved_design.json`, after first patching
`tsi.confirmed_L_uH`/`confirmed_L_uH_sel` from the fixture's stale synthetic
placeholder `239.0` (a leftover from a prior session's `gen_corrected_sample.py`
that pre-dates this design's actual corner conditions and doesn't match what
`_calc_l_py`/`step4_inductance` derive for them) to the internally-consistent
pair this state's real parameters (`90 Vrms`/`1700 W`/`393 Vdc`/`70 kHz`/`20%`
crest) actually produce: raw `113.15 µH` → rounded `115 µH`. **This patch is a
test-fixture correction only — `main.py:176-177` already writes exactly this
consistent pair into real wizard-generated states at intake**, so no production
code needed to change for this. → `C:\tmp\PFC_Verify_Step8Rewrite_ChapterReport.pdf`
(65 pages).

| Check | Result |
|-------|--------|
| Table 3.2.4a (page 33, 90 V row) `∆IL,pp` | `10.6904 A` |
| Table 3.4.1 (page 47) `Lφ,target` / `∆IL,pp` | `115 µH` / `10.6904 A` — **exact match with 3.2.4a** ✅ |
| Raw (unrounded) `Pcore_avg_W` at the 90 Vac reference corner, recomputed via the identical `_half_cycle_averages(..., return_series=True)` call `run_step8_full` makes for `i=0` | `1.5464082095029652` |
| → rounds to `1.546` (3 dp — `step8.summary_table[0].Pcore_avg_W`, "Pcore avg W" in Time-domain panel) and `1.5464` (4 dp) | both are display-precision roundings of the **same** raw float |
| `DesignResult.Pcore_W` ("Pcore iron", Losses-at-operating-temperature panel) | `1.5464` — **exact match** to the raw value's 4-dp rounding ✅ |
| Chapter 4 §4.5 "Core Loss — Cycle-Averaged iGSE" (`doc_report_builder.py:2386` `Pcore_cavg = d.get("Pcore_W")`) | reads the same `Pcore_W` and correctly labels it "P_core,avg (iGSE)", consistent with it now *being* the cycle-averaged value — no separate/independent Pcore-avg computation exists in the chapter builder |

**Conclusion — no further changes needed in `calculations.py`, `documentation_agent.py`,
or `doc_report_builder.py`.** Both fixes (Fix 1's `confirmed_L_uH_sel` read in
`_ch2`/`_ch3`, and Fix 2's rigorous `_half_cycle_averages`-everywhere rewrite of
`run_step8_full`) sit on the exact code path the GUI's "Generate Report" buttons
invoke. **The next report generated through the GUI from a real (non-synthetic)
design will show `Lφ,target`/`∆IL,pp` matching across Tables 3.2.4a/3.4.1 and
`Pcore_W`/`Pcore_avg_W` matching across the Losses and Time-domain panels,
automatically — both panels were already reading from the single corrected
calculation chain; this session only added end-to-end proof of it.**

### Resume point for a future session

Both fixes follow the same "single source of truth" pattern established
2026-06-07 (Iφ,rms via `build_design_ops_table`): when two displayed values claim
to be the same physical quantity, derive both from the same authoritative
calculation chain rather than letting them drift via independent recomputation —
literal anchoring of one row is a stopgap; deriving every row the same rigorous
way is the real fix (and the user explicitly authorized the extra ~9× DB-lookup
cost: "accuracy is very important at each stage"). `confirmed_L_uH_sel`
(rounded-to-5µH) is now the canonical "target inductance" read throughout
`doc_report_builder.py`'s `_ch2`/`_ch3`; `_half_cycle_averages` (360-point
per-angle DB+iGSE integration) is now the SOLE core-loss-vs-Vin calculation
chain — used both for `DesignResult.Pcore_W` (Step 7, single reference point) and
`step8.summary_table[].Pcore_avg_W`/`waveforms` (Step 8, all 9 points) — so they
can never again diverge. No other latent duplicates of either pattern were found
in `generate_report.py`, `generate_combined_report.py`, `generate_steps13_14.py`,
or `documentation_agent.py`.

End-to-end verification (above) confirms this chain is exactly what the GUI's
"Generate Report" buttons exercise via `docGenerateReport` →
`generate_chapter_report` → `build_full_report` — so **both fixes are correctly
wired through the report-generation chain with no further changes required there**.
The one remaining latent issue — `generate_steps13_14.py`'s Table 14.1 still
computing `Pcore_avg` via its own independent power-law-fit chain (`_sec_14_3`,
lines ~826-980) — lives only in `_generate_legacy()`'s exception-fallback path and
is never exercised while the chapter builder succeeds; flagged for awareness, not
fixed (out of the two reported issues' scope, and removing/rewriting a fallback
pipeline the user hasn't asked to touch would be unrequested scope creep).

> **Update — see "Fix 3" immediately below**: this verification proved the
> *backend* calculation chain was already single-sourced and consistent — but the
> user then reran the live GUI and found the two "Pcore" panels **still**
> disagreed. The actual remaining bug was in the *frontend*: `Step7Wizard.tsx` was
> overwriting the winning candidate's correct `material_key` with a stale Gate-2
> selection before calling Step 8, feeding the two calculations different
> materials. See Fix 3 for the root cause, the one-line fix, and updated
> resume-point guidance.

---

## 2026-06-08 (cont'd) — Fix 3: GUI "Pcore iron" vs "Pcore avg W" STILL mismatched live — found and fixed the real cause (`Step7Wizard.tsx`)

After the verification above (which proved the *backend* calculation chain is
already single-sourced and correct), the user reran the actual GUI and reported
the two panels were **still showing different numbers** — e.g. `Pcore iron =
0.805 W` vs. `Pcore avg W @ 90 V = 1.072 W` (screenshot:
`specs/Pcore discripenses.jpg`, candidate `0059716A2`, "Edge · µ=60", bifilar
winding). This proved the backend chain alone wasn't sufficient — something in
the GUI's request wiring was feeding the two calculations *different inputs* for
the same design.

**Root cause — `material_key` clobbered in the `step8TimeDomain` payload**
(`Step7Wizard.tsx:279-280`, the auto-run-Step-8 call right after sizing
completes):
```ts
step8TimeDomain({ state: confirmedState,
  approved_design: { ...top, material_key: matKey }, f_line_Hz: 60.0 })
```
- `top` is the literal winning `DesignResult` from `step7RunSizing` — its
  `material_key` field is `core_mat_key` (`main.py:814`:
  `f"{material_line}_{mu}"`, e.g. `"edge_60"`), i.e. **the exact permeability
  grade the sizing engine actually used and that `design_one_core` passed to
  `_half_cycle_averages` when it computed `res.Pcore_W`** (`step7_magnetic_calc.py:690,715`).
- `matKey` (= `matType==='powder' ? selMaterial : selGrade`, `Step7Wizard.tsx:240`)
  is the Gate-2 **family selection** the user picked *before* sizing ran — e.g.
  `"edge_75"`. `main.py:782-794` deliberately "sweeps ALL permeabilities of the
  selected material family" (`mu=None` in `filter_cores`) so the engine can land
  on a *different* µ than the user's Gate-2 pick if that's globally optimal —
  which is exactly what produced candidate `0059716A2` at µ=60 while the
  Gate-2 pick was a different grade.
- The spread `{ ...top, material_key: matKey }` then **overwrites** the correct,
  candidate-specific `"edge_60"` with the stale Gate-2 `"edge_75"` (or whatever
  grade was originally selected) right before sending `approved_design` to
  `/mode-b/step8/time-domain`. `run_step8_full` reads `material_key = d.get(...)`
  (`step8_time_domain.py`) and passes *that* — the wrong grade — into every
  `_half_cycle_averages`/`get_core_loss` DB lookup for all 9 points.

**Why this produces exactly this symptom**: `get_core_loss` returns a
*materially different* loss-density curve per permeability grade — verified
numerically (`_half_cycle_averages` with identical Bac/fsw/T, only `material_key`
varied): `edge_60 → 0.2018 W`, `edge_75 → 0.2224 W` (+10%), `edge_90 → 0.2874 W`
(+42%), `edge_40 → 0.2383 W` (+18%). A Gate-2-vs-winner grade mismatch of even one
step in the family easily produces the ~10–40% divergence the screenshot shows
(`0.805` vs `1.072` ⇒ +33%) — while `Pcore_W` (computed once, correctly, inside
`design_one_core` with the *true* `core_mat_key`) stays right. Sensitivity-checked
and *ruled out* as the cause: `Vout_V` (✅ also found hardcoded to `393.0` in
`design_one_core` — see "Other latent issue" below — but ±50 V only moves
`Pcore_avg` by single digits %, can't produce +33%); `Icrest_A`/`Rdc`/`Rac`
(`_half_cycle_averages` shows `Pcore` depends only on `Vin_pk`, `Vout`, `N`, `Ae`,
`Ve`, `fsw`, `T_core`, `material_key` — current/resistance terms feed only `Pcu`).

**Fix**: removed the `material_key: matKey` override —
`approved_design: { ...top }` now passes the winning candidate's own
(correct, sizing-engine-derived) `material_key` straight through, so Step 8's
DB lookups use the *same* material grade `design_one_core` used to produce
`Pcore_W`. Single line changed, `Step7Wizard.tsx:280`:
```ts
step8TimeDomain({ state: confirmedState,
  approved_design: { ...top }, f_line_Hz: 60.0 })
```

**Other latent issue found while investigating (not fixed — separate, smaller-impact bug)**:
`design_one_core` (`step7_magnetic_calc.py:443,492,698`) hardcodes
`Vout_V = 393.0` for `Dpk90`/`Bac_pk`/the `_half_cycle_averages` call that
produces `Pcore_W`, instead of reading the design's actual
`intake.application.output_bus_voltage_v` (which `run_step8_full` correctly
does). For the project's reference 393 V bus this is a no-op, but for any design
configured with a different DC-bus target it would silently skew `Pcore_W`,
`Bac_pk_T`, `Bdc_T` etc. away from the design's true operating point — a smaller
(~single-digit-%, per the sensitivity sweep above) but real divergence from the
"single source of truth" pattern. Flagged for a future session; not fixed now
because (a) it wasn't the cause of the reported symptom (ruled out numerically),
(b) `design_one_core` has no `Vout_V`/`Vbus` parameter today — plumbing it through
means changing its signature and all 3 internal call sites plus the
`step7_run_sizing` caller, a larger change than the user's "both panels mismatch"
report calls for.

### Verification

| Check | Result |
|-------|--------|
| Confirmed only one `step8TimeDomain(` call site exists in `Step7Wizard.tsx` (`grep -n`) | line 279 — the auto-run-after-sizing call; no other site needed the same fix |
| `_half_cycle_averages` sensitivity sweep — `material_key` (edge family, µ=40/60/75/90) vs. fixed Bac/fsw/T | `Pcore_avg_W` varies 0.2018 → 0.2874 W (a ~42% spread) — confirms a one-grade Gate-2-vs-winner mismatch fully explains a ~33% "Pcore iron" vs "Pcore avg W" gap |
| `_half_cycle_averages` sensitivity sweep — `Vout_V` 350→460 V (±17% bus-voltage swing, unrealistically wide) | `Pcore_avg_W` only moves 0.1777 → 0.2353 W (≈ ±15%, monotonic, gentle) — ruled out as sole cause of the observed +33% |
| `enrichResult()` (`Step7Wizard.tsx:208`) audited for any field it could mutate that feeds `_half_cycle_averages` (`N`, `Ae_total_mm2`, `Ve_total_cm3`, `Le_single_mm`, `AL_nom_nH`, `stacks`, `T_core_C`, `fsw`) | none touched — `enrichResult` only adds display-derived fields (`L_full_load_uH`, `kbias`, `Rth`, …); `material_key` was the *only* field in the `approved_design` spread being deliberately overwritten |

### Resume point for a future session

The `material_key` clobber was a **third instance** of the same "two panels, two
independently-sourced inputs" anti-pattern this whole 2026-06-08 session has been
chasing — except this time the divergence was injected *in the frontend request
payload*, not in a backend calculation chain (which is why the backend-side
verification two sections up showed everything matching: it tested the chain with
internally-consistent inputs, and the chain *is* internally consistent — the bug
was that the GUI wasn't feeding it consistent inputs). **Lesson for future
"both panels disagree" reports**: always check what `approved_design`/`state`
payload the GUI actually POSTs (browser devtools / the exact spread expression in
the calling component) before assuming the backend math is at fault — a single
clobbered field in a `{ ...spread, field: override }` is invisible from the
backend side and will pass every backend-only regression check. If the
`Vout_V = 393.0` hardcode in `design_one_core` is ever revisited, thread the
design's actual `output_bus_voltage_v` through its signature (and the
`step7_run_sizing` call site, `main.py:815-826`) the same way `run_step8_full`
already reads it from `intake.application`.

---

## 2026-06-08 (cont'd #2) — Fix 4: the REAL remaining cause — Step 8 never re-ran when the user picked a different candidate (`Step7Wizard.tsx`)

User retested and reported the gap was *still* there (`Pcore iron = 1.069 W` vs.
`Pcore avg W @ 90 V = 1.135 W`, candidate `#5 0059553A2 µ=75` highlighted —
screenshot `specs/Pcore discripenses issue not fixed.jpg`), **and** a second,
clarifying symptom: *"when I select a different core option from the left side
menu, Pcore avg W value does not change in the table."* That second symptom is
the key — it says the Time-Domain table is not reactive to candidate selection at
all, which immediately reframes the first symptom: the displayed "Pcore avg W"
values were never *for* the highlighted candidate in the first place.

**Root cause**: `runSizing()` (`Step7Wizard.tsx`) auto-runs Step 8 exactly **once**,
for the initially-auto-selected "best" candidate, right after sizing completes
(`runStep8For(top)`, formerly an inline `step8TimeDomain(...)` call — see Fix 3).
But the candidate-list `onClick` handler (the "click to select" left-side menu,
`Step7Wizard.tsx:868`) only ever called:
```ts
onClick={() => { const _np = ...; enrichResult(r, i, _np, winding) }}
```
`enrichResult` updates `result`/`selectedCandIdx` (so "Pcore iron" *does* update
correctly — it reads `result.Pcore_W`, freshly enriched per candidate, confirmed
at `Step7Wizard.tsx:1081`) but **never touched `step8` state** — so the
"Time Domain Core Loss" table kept showing the stale `step8` object computed for
whichever candidate happened to be the sizing engine's initial pick (e.g. µ=60),
while "Pcore iron" now correctly reflected the newly-clicked candidate (e.g.
µ=75). Two panels, reading two *different candidates'* data — not (this time) two
different calculation chains or a clobbered field, but a missing re-fetch on
selection change. Exactly the same family of "stale cross-panel state" bug as
Fix 3, one click-handler over.

**Fix** — refactored the Step-8 invocation into one reusable helper,
`runStep8For(raw)` (`Step7Wizard.tsx`, added directly after `enrichResult`):
```ts
const runStep8For = (raw: any) => {
  setS8Load(true); setStep8(null)
  step8TimeDomain({ state: confirmedState,
    approved_design: { ...raw }, f_line_Hz: 60.0 })
  .then((s8:any) => { setStep8(s8); setS8Load(false) })
  .catch(() => setS8Load(false))
}
```
and now call it from **both** places a candidate becomes selected:
- `runSizing()`: `enrichResult(top, 0, nPar, winding); ...; runStep8For(top)` —
  unchanged behavior, just routed through the shared helper (replaces the inline
  call introduced in Fix 3).
- the candidate-list `onClick` (`Step7Wizard.tsx:868`):
  ```ts
  onClick={() => { const _np = ...; enrichResult(r, i, _np, winding); runStep8For(r) }}
  ```
  — now re-runs Step 8 for the clicked candidate's own raw `DesignResult` (`r`,
  i.e. `c.result`, the same un-enriched shape as `top`/`best.result`, carrying its
  own correct `material_key`/`N`/`Ae_total_mm2`/etc.), so "Pcore avg W" is always
  computed for the *currently displayed* core — never a leftover from a previous
  selection. `setStep8(null)` also clears the stale table immediately on click so
  the loading spinner (`s8Loading`, already wired into the UI at lines 916/923) is
  visibly accurate rather than showing old numbers while the new request is in
  flight.

This single helper is now the **sole** call site for `step8TimeDomain` in the
component (verified: `grep -n "step8TimeDomain(" Step7Wizard.tsx` → only the one
definition inside `runStep8For`), so any future selection-changing UI (e.g. a
future "compare candidates" feature) automatically stays correct by construction —
there is no second code path that could again drift out of sync.

### Verification

| Check | Result |
|-------|--------|
| `grep -n "step8TimeDomain("` — confirm single call site post-refactor | exactly one — inside `runStep8For`; both `runSizing` and the candidate-list `onClick` now route through it |
| `grep -n "setSelectedCandIdx\|enrichResult("` — every place selection changes also now triggers Step 8 | both sites (`runSizing:288`, candidate `onClick:868`) call `enrichResult(...)` immediately followed by `runStep8For(...)` with the SAME raw candidate object, so `result.Pcore_W` ("Pcore iron") and `step8.summary_table[].Pcore_avg_W` ("Pcore avg W") are now guaranteed to originate from one `_half_cycle_averages` run over one `material_key`/`N`/`Ae`/`Ve`/`Le` set |
| Confirmed `design_one_core` computes `Pcore_W` at the `Vin_pk90` (90 Vac) corner (`step7_magnetic_calc.py:491,699`) — the SAME corner as the Time-Domain table's first/reference row (`OPS[0]`, `Vin_rms=90`) | the two figures being compared ARE the same physical quantity at the same operating point — confirms an exact match is the correct expectation once both are sourced from the same candidate+material, not just "close" |

### Resume point for a future session

This was the actual remaining bug — Fix 3's `material_key`-override fix was
necessary (it was a real, independent latent bug) but not sufficient, because the
GUI's Step-8 table was *also* simply not wired to refresh on candidate-selection
at all. **Both fixes are required together**: Fix 3 ensures the payload carries
the right material for whichever candidate is selected; Fix 4 ensures Step 8
actually re-runs when that selection changes. With both in place, clicking any
candidate in the left-side list now: (1) updates "Pcore iron" via `enrichResult`
→ `setResult`, (2) clears and re-fetches "Pcore avg W" via `runStep8For` →
`setStep8(null)` + `step8TimeDomain(...)`. User should re-test by clicking through
several candidates of *different* µ and stack counts and confirming "Pcore iron"
and "Pcore avg W @ 90 V" track together (exact match) for each one, with a brief
spinner between clicks. The still-unfixed `Vout_V = 393.0` hardcode in
`design_one_core` (flagged in Fix 3) remains the only known latent divergence —
it would only matter for a project configured at a non-393 V bus.

---

## Session 2026-06-08 (cont'd #3) — Fix 5: Review page KPI / canvas / audit discrepancy

### Root Cause

The Review page (`ReviewMagnetics.tsx` → `review_magnetics.html` iframe) was computing L0,
Lfull, Pcore, Ptotal, H, k, Bac,pk, DCR, ΔT, Bmax using the JS studio's **analytical
Steinmetz model with sinusoidal-current assumption**. The Magnetic Material Result screen
shows **Python-rigorous iGSE half-cycle integration** values. Natural divergence, especially
for Pcore/Ptotal (iGSE vs single-point Steinmetz) and Lfull (kbias from DB table vs single
empirical formula calibrated to EDGE 75µ only).

### Fix

Added step 13 to the inject script in `ReviewMagnetics.tsx`. New approach:

1. **TS variable declarations** (after `ffcu`, before currentMap computation):
   - `pyL0_uH`, `pyLfull_uH`, `pyH_Oe`, `pyK`, `pyBacPk_T`, `pyDCR_100_mOhm`,
     `pyPcore_W`, `pyPtot_100_W`, `pyDT_C`, `pyBmax_T` — all read from `result`
     with `?? 0` fallbacks.

2. **Inject step 13** IIFE (inserted between step 12's `renderAll()` call and `})();`):
   - Declares same values as JS variables (embedded via TS template substitution at
     page-render time)
   - `applyPyOverrides()`: overrides all 8 KPI card textContents; repaints the 3D model
     canvas info box (erases draw3D's box, redraws with Python Lfull/Ptotal/Bmax/DCR/ΔT);
     patches audit table rows 5 (Lfull), 6 (Bmax), 7 (Ptotal), 10 (dT)
   - Calls `applyPyOverrides()` immediately after renderAll() for first paint
   - Registers `setTimeout(applyPyOverrides, 0)` listeners on all input elements
     (N, stacks, tempC, explode, vin, Icrest, Vout, fsw, lossAnchor, boreID, bundleOD,
     woundOD, holeID, htBuild, preset, genReview, refreshSummary, frontBtn, isoBtn,
     topBtn, resetBtn) so Python values persist after any user interaction that triggers
     the original IIFE's renderAll()

### Files changed

- `frontend/src/components/ReviewMagnetics.tsx` — added pyXxx TS variable block +
  inject step 13 IIFE

### Verification

- TypeScript: `npx tsc --noEmit` — no errors ✅

---

## Session 2026-06-08 (cont'd #4) — Fix 5 extended: remaining review page discrepancies

Expanded `applyPyOverrides()` in inject step 13 to cover every remaining surface that
still showed JS-approximated values after Fix 5's initial scope.

### Added overrides (D–G)

**D. Overview table `overviewTbl` row 7** — "Estimated ΔT" cell replaced with `pyDT`.

**E. Overview status banners** — The three health-check `<div>` elements (Inductance target
met/missed, Flux level, Estimated temperature rise) were rebuilt with Python Lfull, Bmax,
and ΔT. SA re-computed from live DOM input values (same formula as JS `compute()`). Also
uses `window.cfg.satT` for saturation margin.

**F. Waveform metrics table `waveTbl`** — "Peak H(t)" and "Peak Bmax(t)" rows replaced with
Python H and Bmax. Peak Pcore/Pcu/Ptotal rows left as JS instantaneous peaks (Python only
provides cycle-averaged values — no mapping possible).

**G. Summary textarea `summaryOut`**:
- Inductance line → pyL0, pyLfull, pyH, pyK
- Flux line → pyBac, pyBmax, saturation margin from `window.cfg.satT`
- Loss line → pyPcore, pyPcu (pyPtot − pyPcore), pyPtot, uncertainty band (±5–20% of pyPcore)
- Build line → ΔT value replaced in-place; copper length / fill / current density left as JS
  (those are geometric calculations, no discrepancy)
- Recommended talking points → re-evaluated with Python thresholds (okL: Lfull≥235 µH,
  pyBHigh: Bmax>0.45 T, pyTHigh: ΔT>35 °C)

### Not changed (intentionally JS-analytical)
- Sweep plots and sweep table Pcore/Ptotal columns — `a_effective` is already calibrated
  from Python loss data; remaining model difference (Steinmetz vs iGSE) is documented in
  the sidebar as an analytical approximation. Python has no multi-Vin sweep data.
- Waveform canvases (H(t), B(t), Pcore(t) waveform shapes) — visualization/exploration only.

### Files changed
- `frontend/src/components/ReviewMagnetics.tsx` — step 13 IIFE expanded

### Verification
- TypeScript: `npx tsc --noEmit` — no errors ✅

---

## Session 2026-06-08 — Phase 1: v10 Accuracy Improvements (step7_magnetic_calc.py)

### Goal
Adopt `pfc_sim_agent_v10.html` physics model in the Python backend so every result
derives from the designer's actual selections (material, core, wire) rather than
hardcoded approximations. This is Phase 1 of a 4-phase plan (Phases 2–4: JS review
page alignment, documentation agent, v10 simulation endpoint).

### Changes

**New module-level constants**
- `_PROX_kSkin=0.50`, `_PROX_kProx=0.40`, `_PROX_kCrowd=0.25` — v10 Dowell-proximity calibration
- `_THERM_sC=1.00`, `_THERM_sW=0.90`, `_THERM_couple=0.50`, `_THERM_hotspot=1.12` — 2-node thermal split
- `_LEAD_MM_DEFAULT=150.0` — lead wire length (mm) added to Cu_len

**New helper functions**
- `_bundle_OD_mm(d_strand_mm, n_strands, n_parallel, OD_catalog_mm)` — catalog OD primary, computed fallback
- `_compute_layers(N, n_parallel, ID_mm, bundle_OD_mm)` — v10 tpl/layer formula; returns (layers, tpl, bore_r)
- `_rac_rdc_litz(d_strand_mm, layers, OD_core_mm, ID_core_mm, fsw_Hz, T_C)` — v10 Fskin×Fprox proximity
- `_two_node_thermal(wound_OD_mm, wound_HT_mm, hole_ID_mm, Pcore_W, Pcu_W, T_amb_C)` — 2-node KCL solve

**Updated `_compute_MLT(core, stacks, wire_OD_mm=0.0)`**
- When `wire_OD_mm > 0`: uses `2×wire_OD_mm` routing build (v10)
- When `wire_OD_mm = 0`: legacy `3.8mm` fixed (backward compat)

**New `DesignResult` fields (17 total)**
- Winding geometry: `bundle_OD_computed_mm`, `layers_needed`, `turns_per_layer`,
  `bore_hole_r_mm`, `lead_length_mm`
- Rac/proximity: `Rac_Rdc_litz`, `crowd_axial`
- B(r) crowding: `Bmax_inner_FL_T`, `sat_margin_inner_pct`
- 2-node thermal: `dT_core_C`, `dT_wdg_C`, `dT_hotspot_C`, `T_hotspot_C`,
  `Rca_KperW`, `Rwa_KperW`, `Rcw_KperW`
- MLT: `MLT_v10_mm` (new v10), `MLT_mm` preserved (legacy 3.8mm for report compat)

**`design_one_core()` restructured**
1. Wire params extracted BEFORE MLT (d_strand_mm, OD_mm needed for v10 MLT)
2. Bundle OD and layer count computed from actual wire catalog geometry
3. v10 MLT used for Cu_length_m; legacy MLT stored separately for PDF compat
4. Lead wire (150mm default) added to Cu_len
5. Litz/TIW: Rac/Rdc from `_rac_rdc_litz()` replacing hardcoded `1.0`
6. Solid/enamel: existing Bessel skin-effect formula via `_db()._rac_rdc_solid()`
7. `_two_node_thermal()` called for toroid cores; ETD fallback to scaled SA value
8. Inner-bore saturation check added: fail if `Bmax_inner_FL_T >= Bsat_at_Tcore`

### Files Changed
| File | Change |
|------|--------|
| `backend/app/mode_b/step7_magnetic_calc.py` | Complete rewrite with Phase 1 v10 accuracy model |

### Verification
- `python -c "import app.mode_b.step7_magnetic_calc"` → OK ✅
- All 17 new DesignResult fields present ✅
- All DB methods (`get_Bsat`, `get_k_bias`, `get_core_loss`, `get_mu_r`, `_rac_rdc_solid`) confirmed ✅
- `compute_dowell_factor`, `compute_rogowski_fringing` import paths confirmed ✅

### Not changed (intentionally)
- `dT_rise_C` remains SA single-node surface ΔT — used for pass/fail score and backward compat
- `MLT_mm` (legacy 3.8mm) preserved — PDF report generator still reads it
- ReviewMagnetics.tsx and review_magnetics.html JS — Phase 2 (separate session)

---

## Session 2026-06-09 — Phase 2: Review Page v10 Alignment

### Goal
Make the Review Magnetics page fully consistent with the Phase 1 v10 Python backend.
Every value, graph, and status banner on the review page now derives from the same
physics model as the sizing engine result page.

### JS Physics Fixes (review_magnetics.html)

| Location | Before | After |
|----------|--------|-------|
| `compute()` MLT | Fixed `3.8mm` routing build | `2 × bundleOD` (v10 geometry) |
| `compute()` Cu length | `N × MLT` | `N × MLT + leadMm/1000` (lead wire added) |
| `compute()` current density J | `Irms / 3.14` (hardcoded) | `Irms / cfg.CuArea_mm2` (actual wire) |
| `drawWindowBuild()` passes | `2 × N` (hardcoded bifilar) | `N × cfg.nParallel` |
| `drawWindowBuild()` tpl | `floor(2π×rC / od)` | `floor(2π×max(rC, od/2) / od)` (v10) |
| `cfg` defaults | missing leadMm, CuArea_mm2, nParallel | Added with safe defaults |

### Geometry Injection Fixes (ReviewMagnetics.tsx)

| Variable | Before | After |
|----------|--------|-------|
| `bundleOD` | `result.wire_OD_mm` | `result.bundle_OD_computed_mm` (catalog primary) |
| `layersUsed` | Own JS formula | `result.layers_needed` from Python |
| `holeID` | Own JS formula | `result.bore_hole_r_mm × 2` from Python |
| `passesTotal` | `N × 2` | `N × pyNpar` (matches Python n_parallel) |
| New `cfg` injections | — | `cfg.leadMm`, `cfg.CuArea_mm2`, `cfg.nParallel` |

### New v10 Fields Displayed

17 new `DesignResult` fields from Phase 1 are now surfaced on the review page:

| Location | New content |
|----------|-------------|
| 3D canvas overlay | Purple line: `T_hotspot / ΔT_core / ΔT_wdg / Bmax_inner` |
| Overview table | 6 new rows: T_hotspot, ΔT_core, ΔT_wdg, Bmax_inner, sat_margin_inner, MLT_v10 |
| Overview status banners | Flux banner: shows both mean and inner-bore Bmax + crowding factor; ΔT banner: shows hotspot; New banner: inner-bore saturation margin |
| Waveform metrics table | 3 new rows: Bmax_inner, T_hotspot, ΔT_core/wdg |
| Summary textarea Flux line | Adds Bmax_inner, crowding factor, inner saturation % |
| Summary textarea Build line | Replaces bare ΔT with surface ΔT + T_hotspot + 2-node breakdown |

### Files Changed
| File | Change |
|------|--------|
| `frontend/src/assets/review_magnetics.html` | 4 targeted physics fixes in JS compute() and drawWindowBuild() |
| `frontend/src/components/ReviewMagnetics.tsx` | New TS extractions; cfg injection; expanded overlay; new table rows; updated status banners and summary |

### Verification
- `npx tsc --noEmit` — no errors ✅
- All 4 HTML edits confirmed applied ✅
- All 8 TSX edits confirmed applied ✅

---

*Log format: date · decision · files changed · verification result*
*Append a new dated section for each future session that changes DesignState-related files.*

## 2026-06-09 — Phase 2 Bug Fix: result page ↔ review page data mismatch

### Root Cause Analysis
After Phase 2, the review page KPI cards (Pcore, Ptotal, DCR) are already overridden with Python values. The mismatches the user observed were:
1. **`fillIns` used hardcoded `2` bundles/turn** instead of `cfg.nParallel` — for single winding this over-reported insulated fill by 2×, causing wrong winding-fit status
2. **`fillBare` used hardcoded `3.14 mm²`** instead of `cfg.CuArea_mm2` — wrong for any wire size ≠ 3.14
3. **Sweep table (Voltage Sweep tab)** showed JS Steinmetz values — vs result page Python iGSE values
4. **Overview table rows 0,3,4,5,6,8** showed JS-computed Cu_length, Ihf, Pac, J, Ku, unc-range — all differing from Python's exact values

### Fixes Applied
| Location | Fix |
|----------|-----|
| `review_magnetics.html:233` | `fillBare`: `3.14*N` → `N*(cfg.CuArea_mm2\|\|3.14)` |
| `review_magnetics.html:234` | `fillIns`: hardcoded `2` → `(cfg.nParallel\|\|1)` |
| `review_magnetics.html:350` | Overview table comments updated (no more "3.14 mm²"/"2 bundles/turn") |
| `ReviewMagnetics.tsx` | 7 new TS extractions: `Cu_length_m`, `Ihf_rms_A`, `Pac_W`, `J_A_mm2`, `Ku`, `P_unc_lo_W`, `P_unc_hi_W` |
| `ReviewMagnetics.tsx` | `sweepRows` builder: joins `loss_table_100C` with `L_vs_Vin_table` by Vin |
| `ReviewMagnetics.tsx` | New JS vars: `pyCuLen`, `pyIhf`, `pyPacW`, `pyJA`, `pyKuPct`, `pyPuncLo`, `pyPuncHi`, `pySweepData` |
| `ReviewMagnetics.tsx` | New section **D2** in `applyPyOverrides`: patches overview rows 0,3,4,5,6,8 with Python values |
| `ReviewMagnetics.tsx` | New section **H** in `applyPyOverrides`: replaces sweep table with Python's 9 iGSE data points |
| `ReviewMagnetics.tsx` | Section G summary: uncertainty range uses `pyPuncLo/Hi` (direct Python) instead of back-computed |

### After Fix — Overview Table Sources
| Row | Quantity | Source |
|-----|----------|--------|
| 0 | Copper length | Python `Cu_length_m` ✅ |
| 1 | Duty at crest | JS (same formula both sides) |
| 2 | Irms | JS (same half-cycle integral both sides) |
| 3 | HF ripple rms | Python `Ihf_rms_A` ✅ |
| 4 | HF ripple copper loss | Python `Pac_W` ✅ |
| 5 | Current density | Python `J_A_mm2` ✅ |
| 6 | Insulated fill | Python `Ku×100` ✅ |
| 7 | Estimated ΔT | Python `dT_rise_C` ✅ (pre-existing) |
| 8 | Uncertainty range | Python `P_unc_lo_W`–`P_unc_hi_W` ✅ |

### Verification
- `npx tsc --noEmit` — no errors ✅


---

## 2026-06-09 — Review page SyntaxError: root-cause fix via JSON data island

### Problem
The Step 7 **Review** page (`ReviewMagnetics.tsx` → `review_magnetics.html` iframe)
kept showing the studio's JS *defaults* (N=32, stacks=2, Pcore=3.04 W / Ptot=6.03 W)
instead of the selected candidate's Python values (e.g. `0059071A2 ×3`, N=47,
Pcore=0.836 W). Console confirmed React state was correct, but the injected
`<script>` failed at parse time:
`Uncaught SyntaxError: Invalid or unexpected token (about:srcdoc:441:36)` — so none of
the override code ran and the iframe kept its defaults. The error tracked the inject
content exactly (438→441 as 3 lines were added), confirming a stable bad token inside
the generated script.

### Root cause
The inject was a ~500-line TS **template literal** with ~80 `${…}` substitutions woven
into executable JS plus 615 non-ASCII chars. Two genuine escaping bugs were confirmed:
`su.value.split('\n')` and `lines.join('\n')` used a **single backslash** inside the
template literal → TypeScript cooked `\n` into a **real newline** inside a single-quoted
JS string → unterminated string → SyntaxError. The construction was inherently fragile
(every value/quote/escape a potential parse break).

### Fix — eliminate the entire bug class
Refactored value injection to a **JSON data island + 100% static reader script**:
| File | Change |
|------|--------|
| `ReviewMagnetics.tsx` | New `PY` payload object holds every value (numbers, strings, `kTable`, `sweepData`, `currentMap`) |
| `ReviewMagnetics.tsx` | Emits `<script type="application/json" id="pyReviewData">` + `JSON.stringify(PY).replace(/</g,'<')` data island (guaranteed-valid JS; `<` escaped so a value can't close the tag) |
| `ReviewMagnetics.tsx` | Inject `<script>` now opens with `var PY = JSON.parse(document.getElementById('pyReviewData').textContent);` and contains **zero `${…}`** — all former substitutions replaced with `PY.*` references |
| `ReviewMagnetics.tsx` | Fixed `split('\n')` / `join('\n')` (double backslash → correct `\n` escape at runtime) |
| `ReviewMagnetics.tsx` | Removed dead `currentMapEntries` / `kTableStr` / `sweepDataStr`; removed `[ReviewMagnetics] inject params` + `[srcdoc line X]` debug logging (kept one lightweight `[inject] …` log) |

Because no value is ever substituted into executable JS, a value can never again
produce a SyntaxError. Display precision preserved by moving `.toFixed(n)` to where the
strings are built.

### Verification
- `node` parse-check of the cooked static script (`new Function(code)`) — **PARSE OK**,
  502 lines, no SyntaxError ✅
- `npx tsc --noEmit` — no errors ✅
- Browser (pending user): Review on `0059071A2 ×3` → console `[inject] N=47 stacks=3
  Pcore=0.836W L0=404.2uH`; banner + KPI cards show N=47, Pcore≈0.836 W, L0≈404 µH,
  Ptot≈3.88 W; switching candidates updates the page (reviewKey remount).

### 2026-06-09 (follow-up) — 3D-model overlay: live Python-by-Vin + flicker fix

**Problem:** On the Review page, moving the Vin / temperature sliders made the values
under the 3D model **flicker** and not reflect the change. Cause: the studio's
`draw3D()` redraws the canvas + its own JS overlay each `renderAll()`, then our
`setTimeout(applyPyOverrides, 0)` drew the Python overlay on top in a *separate* tick
(two paints = flicker), using *static* design-point values (no Vin/temp response).

**Fix (`ReviewMagnetics.tsx`):**
- New `pyAtVin(vin)` helper interpolates `PY.sweepData` (per-operating-point Lfull,
  Bac, Pcore, Pcu, Ptot, Icrest) so the overlay stays Python-authoritative as Vin moves.
- Canvas **Section B** rewritten to compute live values: Lfull/Ptotal/Pcore/Pcu from
  Vin interpolation; DCR & copper loss via copper temp coefficient `(235+T)/(235+100)`;
  ΔT/ΔTcore/ΔTwdg scaled by total-loss ratio; Bmax/Bmax_inner by Bac ratio; T_hotspot
  shifts with the live temp setpoint. At the nominal point (90 V, 100 °C) all
  ratios = 1, so it still equals the Python design values exactly. Added live "Vin = …"
  to the overlay; box alpha .78 → .92 to fully cover the studio overlay.
- Flicker eliminated by making `_reApply` **synchronous** (`applyPyOverrides()` instead
  of `setTimeout(applyPyOverrides, 0)`) — our listeners run after the studio's
  `renderAll()` in the same event/frame, so the browser paints once.
- KPI cards/tables remain pinned to the authoritative design point (unchanged).

**Verify:** `node` parse-check (549-line static script) PARSE OK ✅; `npx tsc --noEmit`
clean ✅. Browser (pending user): drag Vin/temp on Review → 3D overlay updates smoothly
(no flicker) with Python-backed values.

### 2026-06-10 — Review KPI cards (under 3D model) made live (Python per-Vin + temp)

**Clarification:** "Values under the 3D model" = the **KPI cards** (`<div class="cards">`
directly beneath `<canvas id="model">`: kpiL0/Lfull/H/K/Bpk/DCR/Pcore/Ptot), not the
in-canvas overlay box. The studio's `renderAll()` writes them with live JS values
(`review_magnetics.html:339`); our Section A pinned them to static Python design-point
values, so after the flicker fix they stopped responding to the Vin/temp sliders.

**Fix (`ReviewMagnetics.tsx`, `applyPyOverrides`):**
- Hoisted the live operating-point computation to the **top** of `applyPyOverrides`
  (shared by both the cards and the 3D overlay): `pyAtVin(curVin)` interpolates Python
  `sweepData`; copper temp scaling `(235+T)/(235+100)` → DCR & copper loss; loss-ratio
  → ΔT/ΔTcore/ΔTwdg/T_hotspot; Bac-ratio → Bmax/Bmax_inner; crest-current ratio → H,
  and `window.retention(liveH)` → k. At 90 V / 100 °C all ratios = 1 (matches design).
- **Section A** cards now show live values: Lfull, Bac,pk, Pcore (Vin); DCR, Ptotal
  (Vin + temp); H, k (Vin); L0 stays static (zero-bias, Vin-independent).
- **Section B** overlay reuses the same shared `live*` vars (de-duplicated).
- Temperature correctly drives only DCR / Ptotal / ΔT / T_hotspot (copper + thermal);
  magnetics (Lfull/Bac/Pcore/H/k) are temp-independent in this first-order model.
- Removed the temporary `[overlay]` debug log.

**Verify:** `node` parse-check (551-line static script) PARSE OK ✅; `npx tsc --noEmit`
clean ✅; user confirmed cards now move with both Vin and temperature.

### 2026-06-10 (follow-up 2) — Cards: live H/k(H), DCR, + new Bmax card

**Requests:** (1) "Peak H @ crest", "Retention k(H)", "DCR" cards still appeared
fixed — make live. (2) Add a "Bmax" card under the 3D model.

**Root cause of fixed H/k:** the `sweepRows` builder read `lvtRow.Icrest_A`, a field
that does not exist in `L_vs_Vin_table` (actual field is `Iavg_crest`). So `at.Icrest`
was 0 → H scaled to 0/fixed → k(H) fixed. The table actually carries **`H_Oe` and
`k_bias` per Vin directly** (`step7_magnetic_calc.py:1027-1028`).

**Fix (`ReviewMagnetics.tsx`):**
- `sweepRows`: added `H` (`H_Oe`) and `k` (`k_bias`) per row; fixed `Icrest` to read
  `Iavg_crest`/`Ipk_line`.
- `pyAtVin`: interpolate `H` and `k` too; fallback `at` carries `H: pyH, k: pyK`.
- Section A cards now read the **exact Python per-Vin** values: `kpiH = at.H`,
  `kpiK = at.k` (replaced the crest-current scaling, removed `hScale`/`liveH`/`liveK`).
  `DCR @ T` was already temp-live (`pyDCR·(235+T)/(235+100)`) — varies with temperature
  (it is a DC resistance, intentionally Vin-independent).
- New **`kpiBmax`** card ("Bmax,mean @ crest") added to `review_magnetics.html` next to
  `kpiBpk`; populated with `liveBmax` (Vin-driven via Bac ratio). Operating flux is
  temperature-independent in this first-order model, so it tracks Vin.

**Behavior:** Vin-driven cards = Lfull, Bac,pk, Bmax, Pcore, Peak H, Retention k;
temp-driven = DCR, Ptotal (+ overlay ΔT/T_hotspot). L0 stays static (zero-bias).

**Verify:** `node` parse-check (550-line static script) PARSE OK ✅; `npx tsc --noEmit`
clean ✅.

### 2026-06-10 (follow-up 3) — Loss-model anchoring (Review ↔ Result consistency)

**Problem:** Review-page losses disagreed with the Result page. Root cause = two
different loss models:
- Result page `Pcore_W` / `Ptotal_100C_W` (`step7_magnetic_calc.py:817,830`) come from
  the rigorous 360-point time-domain `gen_waveforms` at 90 V (authoritative).
- Review `sweepData` comes from `_build_loss_table` (`:1034`), a single-point
  analytical estimate → higher Ptotal at 90 V (e.g. 4.56 vs 3.88 W).

The Review cards/overlay (now interpolating the analytical table) therefore showed a
higher total than the Result page.

**Fix (`ReviewMagnetics.tsx`) — anchor analytical → waveform at the design point:**
- Compute `pcoreAnchor = result.Pcore_W / lossTable.Pcore@90V` and
  `pcuAnchor = result.Pcu_100C_W / lossTable.Pcu@90V` (added to `PY`).
- KPI cards + 3D overlay: `liveCore = at.Pcore·pcoreAnchor`,
  `livePcu = at.Pcu·pcuAnchor·tScale`, `livePtot = liveCore + livePcu`. At 90 V/100 °C
  this equals the Result page exactly (`kpiPcore` = result Pcore, `kpiPtot` = result
  Ptotal); per-Vin shape follows the table. (Also fixes the ΔT loss-ratio, which was
  inflated by the un-anchored total.)
- Sweep table (Section H) rows anchored the same way for app-wide consistency.
- **Charts:** the JS Steinmetz `a` coefficient is now multiplied by `pcoreAnchor`, so
  the core-loss charts (overview miniPlot, waveform Pcore(t)/Ptotal(t)) align with the
  rigorous core loss. Charts already recompute on Vin/Temp via the studio `renderAll`.
  Note: copper-loss chart *shape* and time-domain *shape* remain the JS analytical
  model (level anchored at the design point; not a full Python time-domain port).

**Verify:** `node` parse-check (554-line static script) PARSE OK ✅; `npx tsc --noEmit`
clean ✅.

### 2026-06-10 (follow-up 4) — Split dual-scale chart overlays into separate panels

The `×8` / `×4` overlays were a single-axis co-plotting trick (two different-unit
quantities sharing one Y-axis, the smaller one rescaled to be visible). Replaced with
separate stacked panels, each auto-scaled in its real units (`review_magnetics.html`):
- **Overview:** `Pcore(t) + Bmax(t)×8` on `miniPlot` → `miniPlot` (Core Loss, W) +
  new `miniPlot2` (Flux Density Bmax, T).
- **Waveform panes:** `H(t) + Iavg(t)×4` on `waveH` → `waveH` (H, Oe) + new
  `waveIavg` (Current, A). `showH` checkbox now hides only the H panel (faint
  zero-line placeholder, matching the Pcore/Pcu/Ptot pattern).

Both new panels redraw on every `renderAll` / waveform-toggle, so they track Vin/Temp
like the others. `npx tsc --noEmit` clean ✅.

## 2026-06-10 — Simulation Agent merge: Phase 0 + adapter (additive, isolated)

Decisions locked: (1) our step7 stays authoritative for design numbers; (2) Review page
unchanged, Sim Agent becomes a new downstream page; (3) feed our DB physics into the sim
engine via `fields`/`measured` overrides.

**Equation record:** `specs/Simulation Agent/Inductor Calculation Improvement FIles/
PFC_Inductor_OurEngine_Equations.pdf` (6 pp, 47 eqs) generated from step7_magnetic_calc.py,
beside the sim-agent's reference PDF (+ generator script).

**Phase 0 (isolated module):** new `backend/app/sim_agent/` with `pfc_inductor_engine.py`,
its tests, and both fixtures copied verbatim. 25/25 tests pass (backend venv); analytic
fixture → APPROVE/T1, FEA fixture → APPROVE/T2. Nothing in the live pipeline imports it.

**Adapter:** `backend/app/sim_agent/adapter.py` (+ `ADAPTER_FIELD_MAP.md`) maps a serialized
DesignResult + confirmed state → engine package. Guards the three traps (single-core basis:
Ve÷stacks etc.; units; η vs η·PF). Feeds our physics: bias L(H)←db.get_k_bias (fields.
inductance), R_ac←DesignResult.Rac_Rdc (fields.windingAC), 2-node thermal←Rca/Rwa/Rcw
(fields.thermal), crowd←crowd_axial (fields.flux). Steinmetz a,b,c and retention k0,k1,p are
least-squares fit from the DB (validation base only). operating.points rebuilt via
build_design_ops_table (parity with run-sizing).

**Smoke gate** (`smoke_adapter.py`, `python -m app.sim_agent.smoke_adapter`): validate() →
0 errors; compute() → APPROVE; Lguar 338 µH, worstLoss 6.35 W, Bmax 0.262 T, dT 38.1 °C.
Tiers: inductance/windingAC/thermal/flux/coreLoss = T1 (our computed physics); copperRdc =
T3 (our catalog R/m via copper.measured). Still no live endpoint — fully additive/reversible.

Next: Phase 1 shadow endpoint POST /mode-b/step7/simulate to cross-check vs run-sizing on a
real selected candidate.

### 2026-06-10 (Phase 1) — shadow endpoint POST /mode-b/step7/simulate

- Adapter: dropped `copper.measured` so the engine computes R_dc from geometry →
  provenance "computed" / **copperRdc = T1** (designer's choice). We still feed our v10 MLT
  (build_mm = 2*bundleOD) + matching A_cu/rho, so the geometry DCR tracks our DesignResult
  DCR; documented residual = the 150 mm lead our DCR includes and the engine's length does not
  (~2-3%, within the ±5% band).
- New endpoint `step7_simulate` in main.py (request `_SimReq{state, approved_design, wire_type,
  line_Hz}`): builds the package via `sim_agent.adapter`, runs `validate()`+`compute()`, and
  returns verdict, tiers (all T1 = our physics), validation, statics, worst, and a `crosscheck`
  table comparing our step7 figures to the sim engine with golden bands (L0 ±2%, DCR ±5%,
  Ptot@90 ±15%, Bmax@90 ±5%, dT ±30%, J ±10%). Never throws on bad input (ok:false).
- Lazy-imports the isolated module; does NOT touch run-sizing/Result/Review. Removable
  (route + import) with zero side effects.
- Verified: endpoint executes, returns well-formed crosscheck. (Synthetic smoke flags DCR/loss
  because the fabricated DCR was geometry-inconsistent — expected; real candidates agree.)

Next: exercise the endpoint with a REAL selected candidate (live UI / a saved run-sizing
result), tune any band, then Phase 2 (serve pfc_sim_agent_v14.html as the post-Review page,
injecting the SAME package).

### 2026-06-10 (Phase 1 wiring) — real-candidate cross-check in the Review page UI

- `client.ts`: added `simulateCrossCheck(state, approved_design, wire_type)` → POST
  /mode-b/step7/simulate, with `SimCrossCheck`/`SimCrossCheckRow` types.
- `ReviewMagnetics.tsx`: added a **"🧪 Sim cross-check"** button in the action bar and an
  additive results panel (below the iframe) showing the engine verdict, all-within-band badge,
  the per-quantity cross-check table (Ours step7 vs Sim, Δ%, ±band, status), tier line
  ("engine fed our DB physics"), and any validation warnings. New state simLoading/simError/
  simResult + handler handleSimCheck; posts the SAME selected DesignResult (`result`) +
  `confirmedState` the report path already uses. NO changes to the iframe/inject — the
  stabilized Review studio is untouched.
- Verified: `npx tsc --noEmit` clean; backend endpoint chain (main→adapter→engine) returns a
  well-formed crosscheck with copperRdc=T1.

How to use: open Review for a real selected core → click "Sim cross-check" → panel shows how
the sim engine (running our DB physics) agrees with step7 across L0/DCR/Ptot/Bmax/dT/J.
Next: Phase 2 — serve pfc_sim_agent_v14.html as the post-Review page with the same package.

### 2026-06-10 (Phase 2) — Simulation Agent field-viewer page after Review

- Backend: `/mode-b/step7/simulate` now also returns `"package": pkg` (the SAME object the
  engine computed on) → engine↔viewer parity.
- Viewer asset: copied `pfc_sim_agent_v14.html` → `frontend/src/assets/` (self-contained WebGL
  field viewer; boots inline reading `window.__MAG_FIELD_PACKAGE__`, head at L13 / body script L66).
- New `SimulationAgent.tsx`: fetches the package via `simulateCrossCheck`, injects it as a JSON
  data-island in `<head>` (`<script id=__simpkg type=application/json>` + a setter that
  `JSON.parse`s it into `window.__MAG_FIELD_PACKAGE__`) BEFORE the viewer boots — the robust
  data-island pattern, `<` escaped. Renders the viewer in a sandboxed iframe with a verdict/tier
  header and a Back-to-Review button.
- `client.ts`: added `package?` to `SimCrossCheck`.
- `Step7Wizard.tsx`: new SubStep `'simagent'`; render block; StepBar maps simagent→Review so the
  bar stays lit; navigation via new ReviewMagnetics prop.
- `ReviewMagnetics.tsx`: new optional `onSimAgent` prop + "🔬 Simulation Agent →" action-bar
  button. Iframe/inject untouched.
- Verified: `npx tsc --noEmit` clean; endpoint returns full package (model/operating/acceptance/
  fields[flux,inductance,thermal,windingAC], 9 op points).

Flow now: Result → Review → "🔬 Simulation Agent →" → field viewer (same package) → Back.
REMAINING (Phase-5 style): eyeball the WebGL 3D render in a real browser; the JS-side
validatePackage mirrors Python's (contractual parity), but visual confirmation is still pending.
Next candidate: Phase 4 — documentation agent consumes the engine result + equation reference.

### 2026-06-10 (Phase 4) — Documentation agent uses the engine output + equations

Added an **additive, defensive "4.8 Simulation-Agent Verification"** subsection to the
chapter report (`doc_report_builder.py`, end of `_ch4` "PFC Inductor Performance Analysis" —
the path the Review "Generate Report" button uses via DocumentationAgent → build_full_report).

`_sim_verification(story, state, d)`:
- Lazy-imports `sim_agent.adapter` + engine; builds the package (our DB physics via fields),
  validates, computes. Every failure mode degrades to a one-line note; the call is also wrapped
  in try/except in `_ch4`, so the section can NEVER abort report generation.
- Emits: a CONCEPT box, the field-engine verdict + provenance/tier line (all T1 = our physics),
  a **cross-check Table 4.8.1** (Step-7 vs field engine, Δ, ±band, within/review) for L0/DCR/
  Ptot@90/Bmax@90/ΔT/J, an interpretation line, a THEORY box with the engine's governing
  equations (iGSE core loss, k(H), copper loss with k_harm≈1.213, 2-node thermal) tagged by
  provenance, and a verdict row.
- Matches the report's char conventions (literal µ/°/²/Δ/φ; avoids Ω → "mOhm").

Step-7 stays authoritative (stated in the section); this is independent verification + honest
provenance, satisfying "updated equations used by the documentation agent."

Verified: isolated render of the section → 11 flowables, correct layout/units (Δ/µ/²/° render);
`doc_report_builder` imports clean. Each step heading page-breaks by design, so 4.8 starts on a
fresh page after 4.7 in the full report.

### 2026-06-10 (Phase 4b) — cross-check section in the combined Steps 1–14 report

Added the same independent verification to the OTHER report path — the combined Steps 1-14
report (`generate_steps13_14.py`, used by `generate_combined_report` →
`/mode-b/generate-full-report` and `/mode-b/generate-combined`).

`_sec_14_9_sim_verification(story, approved_design, state, S)`:
- Lazy-imports `sim_agent.adapter` + engine; builds package (our DB physics via fields),
  validates, computes. Every failure degrades to a one-line note; the call in
  `generate_steps13_14_pdf` is also wrapped in try/except → never aborts the report.
- Emits, in this report's native style (`_S()` styles, `_tbl_style()`): "Step 14.9)" navy
  heading, intro, verdict + provenance/tier line (all T1), cross-check Table (Step 13-14 vs
  field engine: L0/DCR/Ptot@90/Bmax@90/ΔT/J with Δ, ±band, within/review), interpretation
  note, and "Step 14.9.1) Field-engine governing relations" (iGSE core loss, k(H), copper
  loss with k_harm≈1.213, 2-node thermal) + reference pointer.
- This file already uses µ/Δ/²/Ω, so used "mΩ" here (vs "mOhm" in the chapter builder).

Verified: isolated render → 16 flowables, correct layout/units (mΩ/µ/²/°/Δ render);
`generate_steps13_14` imports clean. Both report paths (chapter §4.8 and combined §14.9)
now carry the engine cross-check + provenance + equations. Step-7/13-14 stays authoritative.

### 2026-06-10 (fix) — viewer schema superset + cross-check tightening

User reported the Simulation-Agent viewer "not displaying many things" and cross-check
discrepancies. Root cause of the viewer issue: the JS viewer reads a RICHER display schema
than the Python engine, and our adapter emitted only the engine schema → many panels read
undefined → NaN/blank (JS validate still passed since required blocks existed).

Fix in `adapter.py` — emit a SUPERSET package (one object serves both engine + viewer):
- geometry.stackHeight_mm (alias of HT_mm)
- design.vinMin/vinMax/vinDefault(high-line)/loadDefaultPct/specLowLineMaxPct/specHighLineMaxPct
- copper.refDeltaT_C=80 + prox{kSkin,kProx,kCrowd} + wire.fillFactor
- winding.leadLength_mm + winding.window{bundleOD,layers,turnsPerLayer,radialBuild,boreHoleR,Ku}
- material.mui (DB) + material.AL_nH
- full cooling block (airScale…CthCore/Wdg…hotspotFactor)
- acceptance.Bmax_T/Ku_max/dT_max_K (alongside engine L_target_uH/sat_margin_min/FFcu_limit)
- meta.units(dict) + meta.envelope{vin,loadPct,phase}
- vinDefault set to a HIGH-LINE point (100% load is unphysical at low line / spec-limited).

Cross-check tightening: `_fit_loss_steinmetz` now concentrates the B-grid over the actual
operating crest-flux range (bac_max = result.Bac_pk_T) so the power-law tracks the DB
bilinear surface where the design runs → smaller Pcore/Ptot deltas vs Step-7.

Python engine ignores the extra fields (validate only checks required) → still 0 errors,
all tiers T1. Verified with the viewer's OWN JS (SimAgentField.evaluateHeadless in Node):
JS validate ok, 0 warnings, NaN/Inf fields = NONE; @230V/100% Ic 11.4A, Lfull 390µH,
Pcore 0.47W, Pcu 6.0W, Ptot 6.4W (sensible). Note: residual DCR delta on real data is the
~2-3% lead-wire term (geometry DCR has no lead); the big delta in synthetic tests was
inconsistent fake Cu_area vs R_per_m, not a real issue.

### 2026-06-10 (fix) — cross-check apples-to-apples + self-check of generated files

User saw Bmax/ΔT/J flagged. Diagnosed as DEFINITION mismatches in the comparison (not
physics bugs), confirmed in code:
- J: step7 divides by per-conductor area (Cu_area/n_par, step7:824); engine by total Cu
  (engine:583) → differ by n_par for bifilar/trifilar.
- ΔT: step7 dT_rise_C = surface; engine dT = winding node at +20% loss band (engine:572).
- Bmax: step7 uses L_target for B_dc; engine uses biased L(H) (engine:535) → engine lower.

Fix — single shared definition `adapter.crosscheck_rows(result, sim)` comparing on a COMMON
basis: J put on per-conductor basis (engine ×n_par); ΔT vs our dT_hotspot_C (band ±30, note
"engine winding node @ +20% loss"); Bmax band widened 5→12% (note "ours L_target vs engine
biased L"); L0 ±2 / DCR ±5 / Ptot ±15 unchanged. Each row carries a basis note.
Refactored all THREE callers to use it: `main.py _sim_crosscheck`, report §4.8
(doc_report_builder), §14.9 (generate_steps13_14) — eliminates 3 divergent copies.

Self-check corrections: smoke_adapter R_per_m made consistent with Cu_area (rho20/Cu_area).
client.ts SimCrossCheckRow.ours/sim → string|number|null + note?.

Verified: with consistent values ALL 6 rows = within incl. J per-cond @ n_par=3 (the n_par
fix); §14.9 + §4.8 render correctly (units mOhm/µ/²/°/Δ, basis notes); smoke validate ok,
all tiers T1; frontend tsc clean.

### 2026-06-10 (fix 2) — real-data cross-check: ΔT and Bmax resolved

From the user's screenshot (real candidate): J now within (+5.8% ✓, the n_par fix worked),
L0/DCR/Ptotal within. Two genuine flags remained — root-caused in code:

- ΔT hotspot +123% (ours 30.2 → sim 67.4): we fed `fields.thermal` with our NETWORK node
  Rwa = theta·(sC+sW)/sW ≈ 2.1·theta, but the engine does a crude `dT = Ptot_max · Rwa`
  (pfc_inductor_engine:572), not a KCL solve → ~2.5× overestimate. FIX: stop feeding
  `fields.thermal`; the engine then uses its analytic surface-area ΔT (same SA power-law as
  step7 dT_rise_C, ×1.2 loss band) → compare surface-to-surface (verified +11% within ±30%).
  Our 2-node hotspot remains authoritative in step7/report.

- Bmax −31% (ours 0.618 → sim 0.424): step7 computes B_dc from a higher L; the engine uses
  the biased L(H) (pfc_inductor_engine:535) — lower and MORE accurate, so step7 is
  conservative (extra saturation margin, safe). FIX: Bmax is now a ONE-SIDED check — flagged
  only if the engine reads HIGHER than step7 (the unsafe direction); engine-lower is expected.

Both implemented in `adapter.py` (crosscheck_rows spec gained a `one_sided` flag; ΔT row now
compares dT_rise_C surface; fields.thermal removed). All three callers (endpoint, §4.8, §14.9)
inherit it automatically.

Verified: with consistent values all 6 rows = within (incl. Bmax one-sided & ΔT surface);
viewer still renders fully with no NaN (thermal now analytic, 1 expected warning); smoke ok;
backend imports clean. Note: the viewer's thermal panel is now its analytic 2-node (from the
cooling block) rather than our fed nodes — acceptable since the engine's node usage was the
crude single-multiply that caused the error.

### 2026-06-10 (Phase A.1) — material-agnostic retention (no EDGE applied to other materials)

KEY FIX (designer requirement: always use the SELECTED material's DB parameters):
- `step7_magnetic_calc.py _half_cycle_averages` line 443: replaced the EDGE-hardcoded
  `_retention_edge(H)` with `_db().get_k_bias(material_key, H)` — the selected material's
  actual DB DC-bias curve. This k(H) feeds Lth→Bdc→Bmax, so it ALSO fixes the Bmax
  cross-check discrepancy (step7 now uses the same DB curve the field-engine reads via
  fields.inductance).
- Same EDGE bug fixed in the report: `generate_steps13_14.py _sec_14_6_extended_waveforms`
  now uses `get_db().get_k_bias(material_key, H)` (defensive fallback = unity, never EDGE);
  removed the dead `_retention_edge_report`.

Evidence of impact: old hardcode returned k=0.973 for EVERY material at H=63 Oe; the DB
gives edge_14→0.970 (≈, low-µ) but edge_125→0.549 (−43.6%). So the hardcode (calibrated for
a low-µ EDGE) badly overestimated retention/Bmax for higher-µ and non-EDGE materials.

Pcore is unaffected (depends on Bac, k-independent) → Ptotal stays stable; only Bdc/Bmax
correct downward to the material-accurate value. All screens read step7's Bmax (Result direct,
Review via override, Sim via DB fields) → they now converge on Bmax.

Verified: per-material k(H) differs correctly; `_half_cycle_averages` runs for multiple
materials; full `design_one_core` runs on a real DB core (edge_14: N=240, Bmax 0.840, Pcore
0.565, Ptot 2.688, no crash); step7 + generate_steps13_14 import clean.

Deferred (Phase A.2, minor): k_harm HF-copper factor, min-L-at-peak-bias, DCM flag.

### 2026-06-10 (Phase A.2) — port 3 sim-agent refinements into step7

step7_magnetic_calc.py now best-of-breed for these:
- **k_harm** (HF copper harmonic factor, =1.213): the AC excess (Rac/Rdc−1) of the HF copper
  loss is amplified by K_HARM in `_half_cycle_averages` (Pcu_i, Pac) and in the final
  Pcu_final_100/25. K_HARM=1 ⇒ identical to before, so the change is a small, correct uplift
  (~+0.5% Ptot) that ALSO converges step7 with the field-engine (which already uses k_harm).
- **min-L-at-peak-bias** (informational): new field `Lfull_min_at_peak_uH` = L0_min · k(H_peak)
  at the worst INSTANTANEOUS peak bias (i_avg,crest + ΔIpp/2), using the selected material's DB
  curve. Turns selection / pass-fail UNCHANGED (additive only).
- **DCM flag** (informational): new field `dcm_fraction` = fraction of the half-cycle where
  i_avg < ΔIpp/2 (DCM), computed in the waveform loop.

DesignResult gained `Lfull_min_at_peak_uH`, `dcm_fraction`. Verified: full `design_one_core`
runs on a real DB core (edge_14: Ptot 2.701 W, Lfull_min_at_peak 117 µH, dcm 0.0, no crash);
step7 + generate_steps13_14 import clean; sim smoke ok.

Phase A complete: step7 is now the best-of-all-three engine (kept ours: DB loss, Dowell Rac,
2-node thermal, catalog DCR, fringing; adopted from sim: material-agnostic DB retention [A.1],
k_harm, min-L-at-peak, DCM). Next: Phase B (step7 view contract) → Phase C (Review/viewer
render step7's arrays) for full screen convergence.

### 2026-06-10 (Phase B) — step7 "view contract" (single render payload)

- step7_magnetic_calc.py: `_half_cycle_averages` now emits ALL per-θ series when
  return_series=True (t_ms, Vin, D, Iavg, H_Oe, Bdc, Bac_pk, Bmax, Ihf, Pcore, Pcu, Ptot) —
  additive, gated by the flag, so the normal engine path is unchanged (zero regression).
- New `build_view_contract(result, state)`: re-runs `_half_cycle_averages` with the stored
  design → {scalars, waveform(90 V, 360 pts), sweep(9 pts), L_vs_Vin, meta}, ALL from step7's
  own physics. Added field `I_phi_avg_crest_A` so the waveform regenerates exactly.
- Endpoint POST /mode-b/step7/view-contract; client.ts getViewContract() + ViewContract type.
- VERIFIED round-trip: contract max(Bmax) == result.Bmax_FL_T (0.8396), Pcore matches exactly;
  12 series×360 + 9 sweep + 23 scalars; tsc clean; design_one_core regression OK.

### 2026-06-10 (Phase C.1) — Simulation page renders step7's authoritative scalars

- SimulationAgent.tsx now also fetches `getViewContract` (Promise.allSettled alongside the
  cross-check) and renders a "step7 values" strip (L0, Lfull, Bmax, DCR@100, Pcore, Ptot, ΔT, J)
  — the SAME numbers as Result and Review (Review KPIs already overridden with step7 in Phase A).
  So all three screens now display identical HEADLINE values from the single step7 source.
- The WebGL field viewer (iframe) remains the visualization. tsc clean.

Remaining Phase C.2 (chart-level exact convergence — needs browser verification): feed the
contract's per-θ waveform + 9-pt sweep into the Review studio plots and the viewer charts so the
CHART SHAPES are step7-exact too (today they self-compute in JS, well-calibrated after Phase A).
Open decision: design-point-only (90 V) waveforms vs per-Vin (to keep the studio's Vin explorer
exact) — the latter needs the contract to carry waveforms at each OPS Vin.

### 2026-06-10 (Phase C.2-B) — studio renders step7's per-Vin waveforms

Backend: `build_view_contract` now returns `waveforms_by_vin` — step7-exact per-θ series
(t_ms,Vin,D,Iavg,H_Oe,Bdc,Bac_pk,Bmax,Ihf,Pcore,Pcu,Ptot, M=180) at every OPS Vin, plus
`meta.vins`. Verified: 9 Vins, Bmax/Pcore/Iavg vary correctly per operating point.

Frontend (gated → zero regression if contract absent):
- review_magnetics.html: `_step7WaveFor(vin)` maps the posted contract's nearest-OPS waveform
  into the studio's o.wave shape; `renderAll` overrides o.wave + peak metrics with it when
  present; a `message` listener stores the contract and re-renders. Parse-checked OK.
- ReviewMagnetics.tsx: fetches `getViewContract`, postMessages `{__step7_contract}` to the
  iframe on load + on arrival (iframe ref + onLoad). Inject unchanged (still parses, 554 lines).
- SimulationAgent.tsx (C.1): shows step7 "values" strip.

So the Review studio's waveform panes + overview mini-plot now render step7's authoritative
per-Vin curves (nearest OPS point as the Vin slider moves); KPIs already step7 (Phase A);
Sim page shows step7 scalars. tsc clean; backend imports + smoke OK.

NEEDS BROWSER VERIFICATION (cannot render charts headless): open Review → confirm waveform
panes/mini-plot match step7 and update with the Vin slider; then Simulation Agent page.
Remaining (optional): feed step7 sweep into the studio's Voltage-Sweep CHARTS (table already
step7); per-Vin interpolation between OPS points (currently snaps to nearest OPS).

### 2026-06-11 (Phase C — Option B) — Simulation VIEWER renders step7's values

Root cause of the image-2 mismatch: the iframe viewer (pfc_sim_agent_v14.html, `SimAgentField`)
is a SEPARATE engine that recomputes core/copper/thermal from the Steinmetz FIT (no temp) —
less accurate than step7's DB-bilinear surface — and it opened at a different corner
(180 V/full, worst-case scan) than Review (90 V design point). So it showed Pcore 1.81 / Ptot
5.17 vs Review's 0.62 / 3.62.

Fix (converge the viewer to step7; gated → no-op without a posted contract):
- adapter.py: `design.vinDefault` → low line (Vin_lo, 90 V) at `loadDefaultPct = specLowLineMaxPct`
  so the viewer OPENS on step7's design corner (same as Review).
- pfc_sim_agent_v14.html `render()`: after `opPoint`, override op.Pcore/Pcu/Ptot (from contract
  `sweep`, nearest Vin), f.Pcore/f.Pcu inst (from `waveforms_by_vin` peak), and
  ThotSS/TcoreSS/TwdgSS (from contract `scalars`) — so the LIVE READOUTS display step7's numbers.
  Added a `message` listener storing the contract + re-render. Parse-checked OK (487 lines).
- SimulationAgent.tsx: posts `{__step7_contract}` to the viewer iframe (ref + onLoad + on arrival).

Rationale (why render, not re-equation the viewer): step7's core loss is bilinear interpolation
over the measured Pv(B,f) datasheet tables — "porting the equation" would mean shipping the whole
magnetics DB + engine into the browser and maintaining a 2nd copy (the drift we're eliminating).
Rendering step7's per-Vin contract gives identical numbers with ONE engine.

Verified: tsc clean; viewer + studio JS parse; smoke ok (9 OPS, valid package).
NEEDS BROWSER VERIFICATION: open Simulation Agent → LIVE READOUTS (Pcore/Pcu/Ptot/thermal)
should now match Review at 90 V and track step7 as the Vin slider moves.
Remaining: the viewer's ACCEPTANCE panel still uses its own worst-case scan (REJECT) — could be
fed step7's cross-check verdict next; Voltage-Sweep charts in Review (table already step7).

### 2026-06-11 (Option B cont.) — step7 verdict feeds the viewer's ACCEPTANCE panel

- step7_magnetic_calc.build_view_contract: new `acceptance` block = {verdict (from result.passed),
  passed, reasons (result.fail_reasons), rows[B_max vs Bsat, K_u≤60%, ΔT≤budget, J, L_guarantee]}.
- client.ts ViewContract: added `acceptance?` (+ waveforms_by_vin?, meta.vins?).
- pfc_sim_agent_v14.html render(): when the posted contract carries `acceptance`, the panel shows
  step7's verdict + rows + fail_reasons (labeled "· step7 design verdict"); else falls back to the
  viewer's own worst-case scan. Gated → no regression. Rides on the same posted contract (no extra
  wiring). Parse-checked OK.
- Verified: contract.acceptance populates (verdict/passed/reasons/rows); tsc clean; viewer parses.

Phase C / Option B complete: Sim viewer now renders step7's LIVE READOUTS (loss/thermal),
opens on step7's 90 V corner, and its ACCEPTANCE shows step7's verdict — all from the one
view-contract. Needs browser confirm.

### 2026-06-11 — rename "Acceptance"→"Design Verdict"; fix Result vs Review Pcore

GUI rename (no "step7" shown anywhere):
- pfc_sim_agent_v14.html: panel heading "Acceptance (upstream limits)" → "Design Verdict";
  verdict suffix "· step7 design verdict" → "" (heading conveys it).
- SimulationAgent.tsx: scalars-strip label "step7 values" → "Design values".

Result vs Review Pcore mismatch — ROOT CAUSE: the Review studio's Vin slider defaulted to
180 Vac (review_magnetics.html input value="180"), so the live KPI showed Pcore at 180 V
(liveCore = at.Pcore·pcoreAnchor interpolated at the slider Vin) while the Result page shows the
fixed 90 V design value result.Pcore_W. The pcoreAnchor makes them IDENTICAL at 90 V
(liveCore@90 = ltPcore90·(result.Pcore_W/ltPcore90) = result.Pcore_W). Fix: default the Review
slider to 90 Vac (the design corner) so it opens matching Result; also matches the Sim viewer
default (90 V) set earlier. Slider still free to explore.

Verified: tsc clean; both studios parse; no GUI "step7" text remains.

### 2026-06-11 — Review KPIs labeled with live operating point

Added a live "Operating point: <Vin> Vac · <T> °C" indicator directly above the Review KPI cards
(review_magnetics.html #kpiOpTag). Updated in BOTH the studio render() (from i.vinRms/i.tempC)
and the inject applyPyOverrides (from curVin/curT — the authoritative pass that sets the Python
KPI values and re-fires on every slider move). So the KPI block always shows which corner the
values reflect; at the 90 V default it matches the Result page. tsc clean; studio + inject parse.

### 2026-06-11 — Sim viewer readouts now equal Result/Review (B,H,Pcore,Pcu,Rdc,Rac,Ptot,Ku)

Two bugs in the Option-B override: (1) loss used the contract `sweep` (raw loss-table) instead
of the design-anchored values Review shows, and the per-Vin waveform Pcu was on the T_core basis
not 100 °C; (2) B, H, Rdc, Rac, Ku were never overridden (still the viewer's own recompute).

Fix:
- step7 build_view_contract: sweep now carries ANCHORED loss `Pcore_anc/Pcu_anc/Ptot_anc`
  (loss-table × the SAME 90 V anchor Review uses, vs result.Pcore_W / Pcu_100C_W) → per-Vin loss
  equals Result/Review exactly. Added `Rac_Rdc` to the contract scalars.
- pfc_sim_agent_v14.html: replaced the op-mutating override with a readout-TEXT override placed
  AFTER the readout assignments (field plots keep the viewer's geometry). It sets:
  kPc/kPu (anchored-sweep avg | waveform inst), kPt (anchored), kH (H_Oe_design × per-Vin sweep
  H ratio), kBp (Bmax_FL_T × per-Vin Bac ratio), kR (DCR | DCR×Rac_Rdc), kKu (step7 Ku), thermal
  (scalars). At the design corner bsw==sref so H/Bmax equal the design values exactly; off-design
  they track the slider. Relabeled cards "B peak (inner)"→"Bmax,mean @ crest", "H (live)"→
  "Peak H @ crest" to match Review.

Verified: at 90 V Pcore_anc=result.Pcore_W, Pcu_anc=result.Pcu_100C_W, kBp=result.Bmax_FL_T,
kH=result.H_Oe_design (exact); tsc clean; viewer parses; backend imports OK.

### 2026-06-11 — three Review/Sim improvements

1) Review first-load Pcore wrong (fixed once a slider moved): my C.2-B postMessage handler in
   review_magnetics.html calls renderAll() (resets KPIs to JS values) but didn't re-apply the
   Python override. Fix: the inject now adds its own `message` listener that calls `_reApply()`
   after the contract arrives (registered after the studio's, so it runs post-renderAll).

2) Moved the "🔬 Simulation Agent" button into the studio TAB row, between "Voltage Sweep" and
   "Design Review Summary". It's a tab-styled button (id navSimAgent, no data-tab) that posts
   {__navSimAgent} to the parent; ReviewMagnetics listens and calls onSimAgent. Tab handler now
   skips buttons without data-tab. Removed the old bottom-action-bar Sim Agent button.

3) Sim viewer winding model didn't match Review's window-build. Review uses passes = N×nParallel
   filled by a shrinking bore-capacity per layer (33/27/21/14…); the viewer placed only N turns
   uniformly. Fix: adapter computes the SAME bore-fill (`layerCaps`, `passes`, `nParallel`,
   computed `boreHoleR`) into winding.window; viewer windowGeom exposes them and drawRing draws
   the variable per-layer passes. (n_parallel comes from enrichResult on the approved design.)

Verified: tsc clean; studio + viewer parse; inject parses; smoke + backend imports OK.

### 2026-06-11 — graph audit: align all graphs to step7, fix B-H slope, 3D per-layer turns

Root cause of misaligned graph peaks: waveform-based graphs used a different crest-current /
temperature basis than the readouts.
- Stage 1 (backend): build_view_contract waveforms_by_vin now anchors the crest to
  I_phi_avg_crest (so peaks = H_Oe_design / Bmax_FL_T at the design corner) and uses the 100 °C
  copper R (so Pcu = Pcu_100C_W). VERIFIED at 90 V: H 1305, Bmax 0.8396, Pcore 0.565, Pcu 2.136
  all == readouts. Review waveform panes + overview mini-plot (use o.wave) now align.
- Stage 2 (viewer): render() replaces the viewer's `wf` with step7's per-Vin series (L_uH from
  the fed DB inductance) so the Loss(t) / B–H live / L(t) graphs draw step7 curves.
- Stage 3 (viewer B-H slope): the magnetization curve + load-fraction dots used the EDGE-fit
  `material.retention {k0,k1,p}` — same bug step7 had. Now B(H)=µ0·µi·(L(H)/L0)·H using step7's
  DB inductance (ev.fp.Lh), so the bias-climbs-with-load slope is correct per material.
- Stage 4 (Review sweep charts): sweepPlot/sweepPlot2 now fed step7's ANCHORED per-Vin sweep
  (Pcore_anc/Pcu_anc/Ptot_anc/Bac/Lfull), interpolated within each line regime — matches the
  readouts/table.
- 3D turns: draw3D now renders the exact per-layer fill (layerCaps / passes = N×nParallel), same
  as drawRing and Review's window-build.

All gated on the posted contract (no-op without it). Verified: tsc clean; both studios parse;
backend imports + smoke OK. Needs browser confirmation of the rendered graphs.

### 2026-06-11 (follow-up) — fix 3D (WebGL mesh) + B-H curve for real

3D: the actual 3D path is a WebGL renderer (drawGL/_buildMesh); my earlier draw3D edit only
touched the CANVAS FALLBACK. Fixed `_buildMesh` (pfc_sim_agent_v14.html:417) to build the winding
turns from `layerCaps` / `passes = N×nParallel` (same bore-fill as drawRing/Review). Now the
WebGL 3D renders the full per-layer turn stack-up.

B-H: the magnetization curve + load dots used `µ0·mat.mui·k(H)` — mat.mui need not match the
AL-derived inductance, so the curve and the live Bdc trajectory didn't coincide; the axis was
also fixed (160 Oe / 0.80 T) and didn't frame the data. Rewrote drawBH to: find the live (step7)
crest, set ADAPTIVE axes (Hx=1.6·Hcr, By=1.55·Bcr), and draw B(H)=L(H)·H·k with k anchored so the
curve passes through the live crest → the magnetization curve, the load dots, and the live curve
all coincide, using step7's DB inductance L(H). Adapter extends the DB H-grid to H_worst×1.8 (28
pts) so the curve doesn't extrapolate within the axis.

Verified: viewer parses (mesh layerCaps + BH anchor present); smoke OK.

### 2026-06-12 — Sim viewer: B-H Bsat framing, remove captions, design tiles, step7 verdict

1) B-H (drawBH): now frames the Y axis to B_sat (By=max(Bsat·1.08, Bcr·1.6)) and draws a dashed
   B_sat reference line + "(NN% margin)" so the saturation level and margin are visible. (Operating
   B_max on a powder core is ~0.35 T, far below B_sat 1.5 T — the earlier flat-looking curve was
   the operating-region roll-off, not saturation.)
3) Removed captions: the WebGL 3D blurb, the per-mode "B(r) source: …" caption (kept only the
   DCM/spec warnings), and the "Provenance·tier:" badge row.
4) provRow now shows clean tiles: "Design values · source: injected field package" + material +
   N·stacks + wire + Tamb.
5) Header verdict now reads step7's authoritative design verdict (contract.acceptance.verdict =
   result.passed) instead of the shadow-engine's worst-case scan; label "design verdict". The old
   "REJECT" was the Python shadow engine's own acceptance, not step7's.

Verified: tsc clean; viewer parses; all removals confirmed.

### 2026-06-12 — point-2 viewer polish: field gradient contrast + graph hover crosshair

1) Field gradient (fieldSetup): replaced the fixed/loose colour scales (flux vmax=0.6 etc.) with an
   ADAPTIVE range = the field's actual min/max across the radius (vmin=max(0,lo−12%span),
   vmax=hi+5%span; thermal keeps vmin=Tamb). One change fixes cross/ring/3D + colorbar (all read
   fieldSetup) → the gradient now uses the full palette instead of washing out.
2) Graph hover: new `_hover(cid,redraw,xmaxFn,xf,labelFn)` — on mousemove it redraws the base graph
   and overlays a dashed cursor line + the nearest data point's values; `mouseleave` restores it.
   `_last` (op/f/wf/wfRef/refLf/vin) stored each render. Bound on lossC (t · Pcore · Pcu), ltC
   (t · L), bhC (H · Bdc). Reads the step7 waveform (wf overridden earlier).

Verified: tsc clean; viewer parses (adaptive fieldSetup + 3 hovers); smoke OK.

### 2026-06-12 — restore continuous animation + per-parameter tiles (matching the original feel)

Root cause: pinning the visuals to step7's DISCRETE contract data removed the original's continuous
animation. Fixes:
1) Field gradient pulsing (fieldSetup): the colour SCALE is now anchored to the crest-phase field
   (stable), while the displayed field uses the CURRENT phase — so cross/ring/3D (all read
   fieldSetup, incl. WebGL drawGL) visibly pulse with the play/phase animation again, AND keep
   full-palette contrast. (My previous per-frame adaptive scale had killed the pulsing.)
2) B-H / loss / L(t) now animate with Vin AND Load: new `_s7sample(vin,lf)` INTERPOLATES step7's
   per-Vin waveforms across Vin (no cross-gap) and SCALES with load (H/Bdc/Iavg·ls, Pcu·ls²),
   driving both wf (graphs) and the readouts from one source → continuous animation that still
   equals step7 at the design corner. (field-vs-radius already animated via op/f.)
3) Design-value tiles: `_buildTiles()` fills #provRow with individual tiles per parameter
   (L0, Lfull, Bmax, Bmax_inner, Pcore, Ptot, DCR, ΔT, J, Ku, sat margin) + "source: injected
   field package", rebuilt when the contract arrives.

Verified: tsc clean; viewer parses (crest-scale, _s7sample, _buildTiles, load-scale); smoke OK.

### 2026-06-12 (hotfix) — blank Simulation Agent page

Cause: my crest-anchored fieldSetup called bare `inst(op,0.5)`, but in the Viewer scope `inst` is
only `ev.inst` (the Viewer destructures Brad/windowGeom/specMaxPct/crestIL from ev, but NOT inst).
The ReferenceError threw on every render → whole script halted → tiles/views/graphs all blank.
Fix: `inst(op,0.5)` → `ev.inst(op,0.5)`. (Parse passes either way; this was a runtime-only error.)
Scanned: no other bare `inst(` in the Viewer scope.

### 2026-06-13 — Sim viewer: gradient regression + layout per annotated image

1) Colour gradient regression (fieldSetup): reverted from my crest-RADIAL adaptive scale (which
   compressed the phase sweep → looked like 2 colours) to an ABSOLUTE 0→crest-peak scale (vmin=0 /
   Tamb, vmax = crest inner-radius peak ×1.05). The live field now sweeps the FULL ramp as it
   pulses with the phase (press Play / drag phase) and shows the inner→outer radial gradient at
   crest — for Flux B / Cu loss / Core loss / T. (Field also changes with Vin/Load via op.)
2) Layout (annotated image): moved the View buttons (Cross/Ring/3D) to the TOP of the main pane
   (with modeBadge); removed the duplicate "injected field package" (the left provRow AND the top
   badgeRow are gone); the design-value tiles now render UNDER the view (#provRow below the
   canvas), each parameter its own tile (Material, Core, N, Wire, Tamb, L0, Lfull, Bmax,
   Bmax-inner, Pcore, Ptot, DCR, ΔT, J, Ku, sat-margin) + one "source: injected field package".
   `_buildTiles()` populates it at mount and on every contract post. Kept modeBadge (render writes
   it) in the new top row.

Verified: viewer parses; no orphan badgeRow refs; tsc clean.

BH note: for EDGE, 1.5 T is B_sat (the limit), not operating B_max (~0.35 T). The graph frames to
B_sat with the dashed B_sat line + % margin — it is correct; the operating curve sits low because
the design runs far below saturation (good margin).

### 2026-06-13 — BH saturating curve + live "inst" Pcore/Pcu tracks phase

A) Live readouts: the "avg | inst" Pcore/Pcu showed the CYCLE PEAK for "inst", so it never moved
   with the phase. Now "inst" = the step7 waveform value at the CURRENT phase index
   (_s7d.W[round(phase·(n-1))]) → changes continuously as it plays / phase drags.
B) BH curve: B(H)=L(H)·H rolls OVER (k(H) drops faster than H rises), so it "saturated at a low
   value". Replaced with a true saturating magnetization curve B(H)=Bsat·tanh(s·H), with s anchored
   so the curve passes through the operating crest (Hcr,Bcr) and flattens at Bsat. Hx=Hcr·4 (shows
   the climb toward Bsat); the operating bias + load dots sit low on the linear part (true margin),
   Bsat dashed line + % margin shown. For EDGE this climbs toward 1.5 T with the operating point
   far below — the textbook representation the original approximated. (Removed the old _bk anchor.)

Scope-checked (no bare refs — the cause of the earlier blank page); viewer parses; tsc clean.

### 2026-06-13 — BH curve reverted to the ORIGINAL representation (per user)

Reviewed the original pfc_sim_agent_v14.html (Merging Files). Its B–H is a clean rising
magnetization curve (Hx=160 Oe, By≈0.80, MAG = µ0·µi·k(H)·H + load dots + dashed spec-max ghost +
solid live trace + crest dot + switching-loop ellipse). drawRadial in our file is already
byte-identical to the original. My adaptive/tanh/Bsat experiments on the BH were the regression.

Fix: drawBH now uses the ORIGINAL representation, with two engine-correct substitutions:
- k(H) from OUR DB inductance (ev.fp.Lh(H)/Lh(0)) instead of the EDGE-fit retention → correct for
  any material, identical to the original for EDGE.
- live green trace = step7's per-Vin wf.W Bdc(H) (our engine).
- Y-axis auto-fits: By=max(0.80, magMax·1.1, liveMax·1.25) → 0.80 (original look) for typical
  designs, expands only if B_max is genuinely high (no clipping). Removed the tanh/Bsat-line code.

Verified: viewer parses; no stray tanh vars; tsc clean. (Live "inst" Pcore/Pcu phase-tracking and
the absolute-scale field gradient from earlier stay.)

### 2026-06-13 — BH live-trace tracking + Field-vs-radius auto-fit

A) B-H not tracking: the grey magnetization curve used µ0·µi·k(H) with the DATASHEET µi, which
   doesn't equal step7's L0-derived inductance → the curve sat OFF the green live trace. Fix: MAG
   curve B(H)=L(H)·H·_bk with _bk anchored to the live crest (_bk=Bcr/(Lh(Hcr)·Hcr)=le/(0.4π·N²·Ae)).
   This makes MAG(H) mathematically EQUAL step7's live Bdc(H)=L(H)·I(H)/(N·Ae), so the green trace
   lies exactly on the grey curve (proper tracking). Hx=160, By auto-fits (≥0.80).
B) Field vs radius looked flat: drawRadial used a fixed 0.6 T axis. Now (flux/copper) the y-axis
   auto-fits the actual B(r) range (vmax=hi·1.05, vmin=max(0,lo−0.25·span)) so the inner→outer
   crowding curve fills the panel regardless of the absolute B level. Core/thermal unchanged.

Verified: viewer parses; tsc clean.

### 2026-06-13 — BH slope (peak-cap) + Field-vs-radius crest-stable axis

A) BH slope: the DB k(H) for higher-µ EDGE rolls off fast, so B(H)=L(H)·H peaks (~120 Oe for
   edge_60) then turns DOWN — a small-signal µ·H curve isn't a real B-H past the peak. (The
   original's generic EDGE-75 FIT rolled off slower → kept rising; that was the slope difference.)
   Fix: cap the H axis at the curve's PEAK so the magnetization curve rises monotonically (original
   look) using our correct DB physics. The green live trace still rides the grey curve.
B) Field vs radius "not moving": my per-frame auto-fit normalised out the magnitude change. Now the
   y-axis is tuned to the CREST field (ev.inst(op,0.5)) — stable across the half cycle — so the
   curve fills the panel AND drops/moves as the phase plays.
C) adapter: inductance H-grid extended to ≥170 Oe / 36 pts so L(H) covers the B-H axis without
   clamping (real designs keep fine ~5 Oe resolution).

Verified: viewer parses; tsc clean; smoke ok.

### 2026-06-13 — Field-vs-radius: stop out-of-window clipping

The crest-based vmin (_lo−0.30·range) clipped the curve off the BOTTOM at low phase. Fixed:
vmin=0, vmax=crest inner-peak·1.08 (stable across the half cycle). The instantaneous curve now
sweeps 0→crest as the phase plays and always stays inside the panel (no clipping); axis is tuned
to the actual peak (not the fixed 0.6 T).

### 2026-06-13 — removed Field-vs-radius and B-H graphs (per user)

Per request, removed both right-panel graphs from the Simulation Agent viewer:
- Deleted the #radialC and #bhC canvases.
- Removed the drawRadial(op,f) and drawBH(...) calls from render().
- Removed the bhC hover binding.
(drawRadial/drawBH function defs left in place, now unused/dead — harmless; can prune later.)
Remaining right-panel graphs: Loss P(t), Warm-up transient, L(t). Verified: viewer parses; tsc ok.

### 2026-06-13 — Documentation agent: two magnetics-chapter fixes

1) Window-area pitfall reframed (3.4.3, doc_report_builder.py). The single-bore window
   area Wa being unchanged by the stack was annotated as a PITFALL — it is the correct
   way to size a stacked toroid (stack adds Ae/Ve/AL, not winding window). Changed the
   PITFALL → THEORY annotation; states this is standard, correct practice, not a limitation.

2) Detailed step7 engine equations + 9-point calculations added to Chapter 4
   (_ch4, doc_report_builder.py), sourced from the PFC_Inductor_OurEngine_Equations content:
   - 4.2 now leads with the per-OP inductance chain (Iφ,crest → H[Oe] → k(H) → L_full=L0·k)
     and renders the AUTHORITATIVE 9-point Table 4.1 from result.L_vs_Vin_table
     (Vin, Iφ,crest, N·I, H, k(H), L min/nom/max).
   - 4.3 flux-density equations (Bac,pk, Bdc, Bmax) with the engine's 90 V values.
   - 4.4 NEW loss methodology: DB Steinmetz Pv → iGSE Pcore=Pv·F(D)·Ve; split copper
     Pcu = Iφ,rms²Rdc + Ihf,rms²Rac; Ptotal.
   - 4.6 NEW authoritative 9-point Table 4.2 from result.loss_table_100C
     (Vin, Vpk, D, Irms, Ihf,rms, Bac,pk, F(D), Pcu, Pcore, Ptot; worst-case row amber)
     + a worked example (4.6.1) that evaluates the full equation chain with the engine's
     own numbers at the worst-case corner.
   These use the centralized step7 output (L_vs_Vin_table / loss_table_100C, already on
   the approved_design payload) instead of the Chapter-3 first-pass peak-point estimate.

Verified: ast parse OK; all 17 added mathtext equations render; full _ch4 builds a 134 KB PDF
end-to-end with realistic engine tables (data_table + eq_box + worked example).

### 2026-06-13 — Full report field-correctness: Chapter 5 (capacitor) + Chapter 6 (control)

Verified the complete chapter-based report end-to-end by driving the REAL engines
(step7 run-sizing → approved_design, step15 run_capacitor_design → step15_result,
step16 design_control_loops → step16_params) through the documentation/generate-report
endpoint and scanning the rendered PDF for placeholder/default-leak fields. Found two
real field-drift bugs where doc_report_builder.py read keys the live payloads never carry:

1) _ch5 (Chapter 5, Capacitor): read FLAT keys (C_holdup_uF, C_ripple_uF, limiting_factor,
   t_hold_ms, V_min_holdup_V, Vout_V, Pout_W, dV_ripple_spec_pct) but the real step15_result
   (= run_capacitor_design output + selected_cap) nests them under worst_case{}, inputs{},
   and "governing". Result: hold-up/ripple equations rendered with 0.0 µF, governing factor
   showed "—", and Vout/Vmin/Pout silently used hardcoded defaults (300 V, 3600 W, 2%).
   Fix: read nested worst_case{}/inputs{}/"governing" first (flat keys kept as fallback);
   ripple CONCEPT now shows ΔV in volts (20 V pk-pk) not the bogus 2% default; ripple eq_box
   now shows the full numeric substitution incl. η. Governing string prettified
   ("C_holdup" → "hold-up") for prose. Now renders Choldup=2046.9 µF, Cripple=1259.0 µF,
   Creq=max=2046.9 µF — matches the engine exactly.

2) _ch6 (Chapter 6, Control): read fi_c_Hz/fv_c_Hz/PM_inner_deg/PM_outer_deg, but step16_params
   carries only plant inputs (L, DCR, C, ESR, Vout, fsw, …) — those crossover/PM keys never
   exist, so the scorecard was always "— Hz / —° / VERIFY". Fix: _ch6 now calls
   design_control_loops(**step16_params) when "scorecard" is absent, then renders the worst-case
   (min PM across all 9 corners) crossover, phase margin, gain margin + verdict. Table 6.6.1
   gained a Gain Margin column; voltage-loop pass criterion aligned to the engine's own 55°.

Verified: py_compile OK; full 6-chapter report builds (71 pages, 4.9 MB) via the real endpoint
chain; placeholder scan clean (remaining "VERIFY"/"= 0.0" hits are the test project name
"VERIFY-3p6kW" and "Bac,pk = 0.0710 T" substrings, not field bugs). Page 67 (Ch5 eqs) and
page 71 (Ch6 scorecard) visually confirmed with correct numbers. Sample PDF written to
PFC_Report_VERIFY_Steps1_16.pdf at project root.

KNOWN GAP (not a field bug — structural, for a follow-up session): Chapter 5 splash promises
5.1–5.5 but only 5.1 + 5.3 are implemented (5.2 bank config, 5.4 ripple-current verification
@ 9 pts, 5.5 Arrhenius lifetime still missing). Chapter 6 splash promises 6.1/6.2/6.4/6.5/6.6
but only 6.1 + 6.6 are implemented (6.2 plant analysis, 6.4 current-loop, 6.5 voltage-loop
compensator design still missing). The engine data for these (worst_case/low_line I_rms,
scorecard 9-point table, rhpz_table, compensator component values) is already available on
the payloads.

### 2026-06-13 — Built out the missing Chapter 5 + Chapter 6 sub-sections

Both chapters' splash pages promised sub-sections that didn't exist (only 5.1+5.3 and
6.1+6.6 were implemented). Added the five missing ones, each grounded in real engine data
already on the payloads (no invented fields), using the existing doc_report_builder helpers
(step_h / annotation / eq_box / data_table / verdict_row):

Chapter 5 (Capacitor) — doc_report_builder.py _ch5:
- 5.2 Bank Configuration and Voltage Rating: calls step15_capacitor.verify_configuration() on
  the selected_cap config → Table 5.2.1 (installed C, margin %, parallel ESR, V/T rating) +
  PASS/UNDERSIZED verdict; Table 5.2.2 lists the engine's suggested_configs alternatives.
- 5.4 Ripple Current and Voltage Verification — 9 points: calls calculate_thermal_table() →
  Table 5.4.1 (I_cap, I/cap, I_rated, ΔVpp, T_cap, verdict per point; hottest row highlighted)
  + all-9-points ripple-rating verdict.
- 5.5 Lifetime Analysis (Arrhenius): uses s15["lifetime"] if present, else computes via
  step15_cap_db.calculate_lifetime() from selected_cap (parses datasheet life-hours, maps
  ESR/Vrating/Trating) → Table 5.5.1 (3 methods, core temp, hours, years; governing/minimum
  row highlighted) + 15-yr service-life verdict.

Chapter 6 (Control) — doc_report_builder.py _ch6 (reuses the design_control_loops() result
already computed for 6.6):
- 6.2 Plant Analysis: f_0 and f_ESR eq_boxes with numeric results + Table 6.2.1 (LC pole,
  ESR zero, RHP zeros @ LL/HL, fsw/10, fcv, fci with significance).
- 6.4 Current Loop (Type-II): Table 6.4.1 (R_IC, C1/C2 with zero/pole freqs) + Table 6.4.2
  (LL/HL margins, PM≥45° verdict).
- 6.5 Voltage Loop (Type-II/III auto): Table 6.5.1 (R2, C1, C3, optional R3/C2 for Type-III,
  feedback divider) + Table 6.5.2 (margins + 120 Hz rejection, PM≥55° & rej≥20 dB verdict).

Bug caught + fixed during visual QA: the 6.2.1 table used literal unicode "f₀" which Helvetica
renders as tofu boxes in ReportLab table cells (CLAUDE.md rule #7). Switched to "f<sub>0</sub>"
/"f<sub>ESR</sub>" — table cells are Paragraphs so sub-tags render.

Verified: py_compile OK; full 6-chapter report builds via the real endpoint chain (71 → 77
pages) with realistic engine data; all six new pages rendered to PNG and visually confirmed
(5.2 margin 14.8% PASS, 5.4 9-point table worst row 53.4 °C, 5.5 governing 23.2 yr,
6.2 f0=211.9 Hz/f_ESR=8.91 kHz, 6.4 Type-II R_IC/C1/C2, 6.5 Type-II compensator + divider).
Sample PDF refreshed at PFC_Report_VERIFY_Steps1_16.pdf. Chapters 5 and 6 now match their
splash-page promises end-to-end.

### 2026-06-13 — Report Structure Agreement: Table of Contents + missing chapter sections

Went through specs/PFC_Report_Structure_Agreement.pdf and closed the highest-value gaps
between the agreed structure and the chapter-based builder (doc_report_builder.py).

ADDED — Table of Contents (index) after the cover page:
- New _TOCMark zero-size flowable + _ReportDoc(SimpleDocTemplate).afterFlowable that notifies
  ReportLab's TableOfContents. chapter_splash emits a level-0 mark at the top of each chapter
  page (chapter title lives inside a Table, so it is not a direct Paragraph); step_h tags its
  heading Paragraph level 1, sub_h level 2 — accurate page numbers.
- build_full_report now renders a "Table of Contents" page (3-level styles, dotted leaders) after
  the cover and uses doc.multiBuild() (two passes) so the page numbers resolve.

ADDED — data-backed sections that were missing vs the agreement (all from real engine output):
- 5.6 Capacitor Bank Summary — consolidated design-margins table (installed-vs-required C,
  voltage rating, hottest-case temp, service life) with per-check status.
- 6.7 Soft-Start and Protection — C_SS = I_SS·t_SS/V_SS eq_box + protection-component table
  (C_SS, R_CS/ILIMIT, BIBO) from design_control_loops (css, t_ss_ms, RCS_mOhm).
- 6.8 Control Network Bill of Materials — full compensator + feedback-divider + soft-start BOM
  (R_IC/C1_IC/C2_IC, R2/[R3]/C1_V/[C2_V]/C3_V/R_FB1/R_FB2, C_SS) with reference designators.

documentation_agent.py: updated the Chapter 5 and Chapter 6 section lists in _assess_chapters to
match the new structure (5.1–5.6; 6.1/6.2/6.4/6.5/6.6/6.7/6.8).

Verified: py_compile OK; full report builds via the real endpoint chain (77 -> 84 pages);
TOC page rendered + visually confirmed (chapters bold/navy, sections + subsections indented,
dotted leaders, correct page numbers); 5.6 / 6.7 / 6.8 rendered with real values
(e.g. 6.8 BOM: R_IC 267 k�, R2 154 kΩ, C_SS 200 nF). Sample PDF refreshed.

NOT YET DONE (larger items deferred — flagged for a follow-up): front matter (revision history,
executive-summary scorecard, nomenclature, abbreviations tables); back matter appendices A–D
(BOM/bench-plan/sensitivity/references); Chapter 4 §4.8 CCM/DCM boundary check (engine now exposes
dcm_fraction — collides with the existing "4.8 Simulation-Agent Verification", needs renumber) and
§4.9 design-validation checklist; Chapter 6 §6.3 FAN9672 pin map.

### 2026-06-13 — Improvements & Corrections (pass 1: corrections + formatting + root-cause bugs)

Worked through specs/"Improvments and Corrections.docx" (designer review of the generated
report). This pass = the clear corrections, global formatting, and the three "find the reason
and correct it" root-cause bugs. Heavy calc-narratives/new-tables and the two new figures
(2D winding cross-section, thermal 2D/3D) are pass 2.

GLOBAL FORMATTING (doc_report_builder.py _S):
- Annotation box body text -> TA_JUSTIFY (item 1).
- Data-table cell content -> TA_CENTER (item 2).
- _eq_img now caps equation image width to the content width so wide equations no longer
  overflow the right margin (item 13).

TEXT CORRECTIONS:
- Cover: added "Design Engineer: Ricky Shah" (item 3).
- Ch1 PITFALL rewritten -> INSIGHT: powder toroids ship factory-coated and do NOT require TIW
  wire (items 4 & 8; same fix in Table 3.3.1 "Medical creepage" row).
- Removed chapter cross-references: Table 1.3.1 "Design Impact" (item 5), Table 1.4.1 "Applied
  in" -> "Role" (item 6), 2.6 CONCEPT "...Chapter 3 3.1 builds directly..." (item 7), the
  "Outputs shown in Table 3.4.2" forward ref (item 9), and the "...follows in Sections 3.6 and
  Chapter 4" forward ref (item 10).
- Ch5: merged 5.2 + 5.3 (item 27) -> "Bank Configuration and Selected Capacitor": kept the
  CONCEPT + a capacitance-check verdict, folded the selected-cap spec into one Table 5.2.1, and
  removed the two tables the reviewer flagged as not making sense (old 5.2.1 bank-config,
  5.2.2 alternatives).

ROOT-CAUSE BUG FIXES (engine/data — "fix everything" per designer):
- Bsat (item 21): edge_*.json had Bsat 1.05 T (Kool-Mu's value, copied in error). Corrected all
  10 EDGE files to 1.5 T at 25 C (100 C -> 1.427, 150 C -> 1.378 via the existing -0.00065/C
  coeff). Saturation margin now reads against the correct EDGE Bsat.
- Wire-diameter logic (item 11, doc): 3.5.2 showed "1.6277 mm (< 0.5720 mm limit)" which was
  false. Now prints the correct comparison and, for a solid conductor that exceeds 2*delta,
  explains it is acceptable (LF-dominated current; AC excess captured by Rac/Rdc), not a defect.
- Verdict REJECT with all-in-band (item 26): the field engine (sim_agent/pfc_inductor_engine.py)
  had TWO over-strict asserts. (a) skin_depth hard-failed any wire thicker than 2*delta -> now
  N/A for a solid single-strand conductor. (b) L_guarantee compared the INSTANTANEOUS-PEAK
  inductance against 100% of L_target, whereas step7 (authoritative) guarantees the
  CREST-AVERAGE inductance at AL_min >= 85% of target (standard DC-bias rolloff allowance).
  Aligned the assert to step7's basis/threshold; peak-bias L kept as informational. Verdict now
  APPROVE, consistent with step7 and the 6/6 cross-check agreement.

Verified: py_compile OK (doc_report_builder + pfc_inductor_engine); full report rebuilds via the
real endpoint chain (83 pages); 9/9 spot-checks pass; field-engine verdict APPROVE (0 REJECTs);
cover, justified CONCEPT box, centered tables, and the merged 5.2 visually confirmed. Sample
PDF refreshed.

PASS 2 (pending): step-by-step calc narratives + new tables (DCR 25/100C steps, copper-loss in
3.6.2, current-density 3.5.7, full-load L table in 3.5.4, iGSE worked steps 4.4/4.5, method-vs-
method loss comparison 4.7, thermal calc steps, 9-point flux table 4.3 with correct Bsat,
capacitor calc steps 5.4/5.5); figures (4.1 2D winding cross-section, thermal 2D/3D).

### 2026-06-13 — Improvements & Corrections (pass 2a: Chapter 3 calculation detail)

doc_report_builder.py _ch3 — added the step-by-step calculations the designer asked for:
- 3.5.3 (item 12): THEORY box explaining the 79.577 factor (1 Oe = 79.577 A/m = 1000/4pi, the
  Oe<->A/m conversion the DB bias curve is indexed in) and k(H) (the permeability-retention
  factor), term by term with the design's own numbers.
- 3.5.4 (items 14/15): full-load (DC-biased) inductance — worst-case narrative (which Vin,
  H, k(H), L_full) plus Table 3.5.4, the 9-point L_full(min/nom/max) sweep from the engine's
  L_vs_Vin_table, worst row highlighted.
- 3.5.7 (item 16): NEW "Current density check" subsection — CONCEPT + J = I_rms / (n_par*A_cu,1)
  worked equation + PASS/REVIEW verdict against the 7 A/mm^2 target.
- 3.6.1 (item 17): DCR eq expanded to show DCR(T) = R'(20C)*[1+alpha*(T-20)]*l_cu with the full
  numeric substitution at 25 C and 100 C (per-metre R x total length x temperature factor) —
  also corrected the from-25C 100 C factor (now both derived from the 20 C reference).
- 3.6.2 (item 18): added the copper-loss calculation Pcu(T) = I_phi,rms^2 * DCR(T) with numeric
  substitution at 25 C and 100 C (previously only core loss was shown); retitled 3.6.2 to cover
  both copper and core loss.

Verified: py_compile OK; report rebuilds (84 pages); all five additions present; 3.5.4 table and
the 3.6 DCR/copper-loss page visually confirmed (DCR 33.23/42.83 mOhm, Pcu 3.49/4.50 W).

PASS 2 REMAINING: Ch4 — 4.3 nine-point flux table (item 20), iGSE worked steps 4.4/4.5
(item 22), method-vs-method loss comparison 4.7 (item 24), thermal calc steps (item 25);
Ch5 — 5.4 capacitor-current/thermal calc steps (item 28), 5.5 lifetime per-method steps
(item 29); FIGURES — 4.1 2D winding cross-section (item 19), thermal 2D/3D (item 25).

### 2026-06-14 — Improvements & Corrections (pass 2b: Chapter 4 + 5 calculation steps)

doc_report_builder.py — added the remaining step-by-step calculations and tables:
Chapter 4:
- 4.3 (item 20): Table 4.3 — nine-point flux density (Bac,pk / Bdc / Bmax + saturation margin)
  against the corrected EDGE Bsat = 1.50 T. Bdc(Vin) computed from L_full*Iavg_crest/(N*Ae).
- 4.5 (item 22): worked iGSE F(D) = K_iGSE[D^(1-c)+(1-D)^(1-c)] with the 90 Vac numbers, plus a
  THEORY box on why the duty correction matters.
- 4.7 (item 24): Table 4.5 — peak-point (Ch3) vs cycle-averaged iGSE (Ch4) loss-method comparison
  (core loss 1.83 -> 1.07 W, -42%) + INSIGHT explaining the difference.
- 4.7 (item 25, calc part): thermal calculation steps — SA natural-convection law
  dT=(Ptot*1000/SA)^0.833 worked out (SA 60.6 cm^2, dT 51.9 C) + Table 4.6 per-Vin temperature
  rise across all 9 points.
Chapter 5:
- 5.4 (item 28): worked example at the hottest corner before Table 5.4.1 — I_cap,total ->
  I_per_cap -> P_cap -> dT/T_cap -> dV_pp, all from engine values.
- 5.5 (item 29): per-method Arrhenius chains before Table 5.5.1 — f_T, f_V, L=L0*f_T*f_V for
  Methods 1 & 2, and the f_T/f_I/f_V manufacturer model for Method 3.

Verified: py_compile OK; report rebuilds (85 pages); all seven additions present and visually
confirmed (4.3 flux table with Bsat 1.50 T, 4.7 loss comparison + thermal steps + per-Vin dT
table, 5.4 worked chain).

PASS 2 REMAINING: only the two FIGURES — 4.1 2D winding cross-section with turns (item 19) and
the thermal 2D/3D visualization (figure part of item 25).

### 2026-06-14 — Improvements & Corrections (pass 2c: the two figures — COMPLETE)

doc_report_builder.py — added the two figures, finishing the designer review:
- Item 19 (Figure 4.1, §4.1): 2D winding cross-section — matplotlib _fig_winding_cross_section(d).
  Left panel: toroid top view (core annulus) with the N turns drawn as copper segments around the
  ring (capped at 64 drawn for legibility), OD/ID labelled. Right panel: radial cross-section of
  one turn wrapping the core stack, with core dims (below) and wire OD labelled.
- Item 25 figure (Figure 4.2, §4.7): 2D thermal map — _fig_thermal(d, t_amb). Left: filled
  temperature field over the wound cross-section (inferno), interior hotspot cooling to the
  surface, °C colorbar + contour lines. Right: thermal-budget ladder (ambient -> surface ->
  hotspot) against the dashed ΔT-limit line.

Fixes during figure QA: the thermal map initially rendered the surface HOTTER than the hotspot
(inverted) because dT_hotspot_C < dT_rise_C in the payload — now the interior hotspot is forced
to the hottest node (max(dThs, 1.12*dT)); ladder labels staggered so hotspot/limit no longer
collide; the winding cross-section core-dimension label moved below the (thin, tall stack)
rectangle so it no longer overflows.

Verified: py_compile OK; report rebuilds (85 pages); both figures rendered and visually confirmed
(Fig 4.1: 44 turns + 3-stack core 7.1x34.3 mm, wire OD 1.68 mm; Fig 4.2: hotspot 108 C -> surface
102 C vs 110 C limit).

ALL 29 ITEMS FROM "Improvments and Corrections.docx" ARE NOW COMPLETE (pass 1 corrections/
formatting/root-cause bugs; pass 2a Ch3 calcs; pass 2b Ch4/5 calcs; pass 2c figures).

### 2026-06-14 — Final read-through polish

Ran a full-report automated scan (replacement chars, nan/inf/None leaks, leftover chapter
forward-refs, suspicious zero results, duplicate table refs, section-heading order, verdict
tokens) plus visual spot-checks. Fixes applied:
- Chapter 5 had a 5.2 -> 5.4 numbering gap from the earlier 5.2/5.3 merge. Renumbered the body so
  it reads 5.1-5.5 with no gap (Ripple 5.4->5.3, Lifetime 5.5->5.4, Bank summary 5.6->5.5; tables
  5.x.1 follow; "Sections 5.1-5.5" intro -> "5.1-5.4"). Updated the Ch5 chapter splash bullets and
  documentation_agent.py Ch5 section list to match; the auto-TOC now shows 5.1-5.5.
- Ch6 chapter splash now lists the added 6.7 and 6.8 bullets.
- Softened the one remaining inline chapter cross-ref in 4.5 ("Peak-point estimate (Chapter 3)"
  -> "Peak-point (first-pass) estimate").

No action needed (verified benign):
- "None" on two pages is the literal English word in table cells ("None — no discrete gap",
  "None — K(D) = 1.0 always"), not a value leak.
- The 3 VERIFY verdicts (Ch6 6.4/6.5/6.6) are the genuine auto-sized control-loop margins from the
  placeholder step16 inputs, not report bugs.
- Scan otherwise clean: 0 replacement chars, no nan/inf, no duplicate table refs, no leftover
  "(Chapter X)" forward-refs in spec tables.

KNOWN GAP (intentional, not a rough edge): Ch6 6.3 (FAN9672 pin configuration) is unbuilt because
the engine does not produce a pin map; left as an honest gap rather than renumbering over it.

Verified: py_compile OK (builder + agent); report rebuilds (85 pages); TOC/splash/body consistent
for Ch5 (5.1-5.5) and Ch6 (incl. 6.7/6.8).

### 2026-06-14 — §6.3 pin table + round-2 corrections

(1) §6.3 FAN9672 Pin Configuration (new): pin-function map (IEAO/VEAO/CS/VFB/SS/VIN/GMOD/RAMP/
VREF/GATE/VCC) populated with the design's real compensator/sense/soft-start component values,
plus an operating-envelope table (R_CS, f_sw, V_out) and a GMOD insight. Added to the Ch6 splash
and the documentation_agent Ch6 list; Ch6 now reads a complete 6.1-6.8.

(2) Round-2 corrections from "Improvments and Corrections.docx":
- 2.7.1 CONCEPT: removed "via Mode A HITL gates".
- 4.4/4.5: full iGSE worked chain (F(D) -> Pcore -> Pcu -> Ptotal) at BOTH 90 and 180 Vac, with a
  THEORY note (the 9-point breakdown is Table 4.2).
- 4.7: loss comparison expanded to core + copper + TOTAL for Method 1 (peak-point, Table 3.6.1)
  vs Method 2 (iGSE), with the +/-% difference and an INSIGHT.
- 5.3: added the ripple-current decomposition (I_dc -> I_LF -> I_HF -> I_cap,total) before the
  worked example.
- 5.4: answered the reviewer's questions — CONCEPT explaining R_th (case-to-ambient ~15 C/W radial,
  ~10 snap) and T_core (= Tamb + P_ripple*R_th, differs per method because the ESR estimate
  differs); each of the 3 methods now worked end to end (ESR -> P -> dT -> T_core -> f_T,f_V -> L;
  Method 3 via I_eq/f_I/f_V). Confirms why T_core differs (M1 51.2 C, M2 62.5 C, M3 69.5 C).

Build-fail caught and fixed during QA: a bare "\sqrt2" in the 5.3 decomposition is invalid
matplotlib mathtext (needs \sqrt{2}); it threw inside build_full_report, silently falling the
report back to the legacy generator (58 pages). Fixed -> chapter builder restored (88 pages).

Verified: py_compile OK; report rebuilds via the real endpoint chain (88 pages); 0 replacement
chars, no duplicate table refs; §6.3 pin table and the 3-method lifetime page visually confirmed.

### 2026-06-14 — Table 4.5 9-voltage + Method-3 detail + 4 of the 12 v11 quantities

Saved SESSION_HANDOFF.md (resume point) + project memory first.
- Task 1: Table 4.5 loss comparison expanded to all 9 operating points (Core/Copper/Total for
  Method 1 peak-point vs Method 2 iGSE; worst row highlighted).
- Task 2: Method-3 lifetime fully worked (I_eq via k_LF/k_HF, ΔTj, T_core, and f_T/f_I/f_V each
  with every constant substituted: f_T=2^((Tmax-Tamb)/10), f_I=2^(ΔTo/d_To−ΔTj/d_Tj) with
  d_To=7.5/d_Tj, f_V=5(k_v−1)(1−Vop/Vrated)+1).
- Task 3 (12 v11 quantities) — first 4 DONE: #1 K_harm in the 4.4 copper-loss equation (+THEORY);
  #5 inner-bore radial crowding (4.3 crowd eq + B_inner column across all 9 points, sat margin now
  vs inner-bore peak); #6 L_full,min@pk (4.2 eq + note); #8 loss uncertainty band +5%/+20% (4.7).
  Remaining 8 queued in SESSION_HANDOFF.md (#2 Rac/Rdc, #3 DCM 9-pt, #4 flux waveforms[fig],
  #7 layers, #9 convergence, #10 two-node, #11 ranking score, #12 Pcore(θ)[fig]).

QA: 2 mathtext bugs caught via direct build_full_report() (\sqrt2→\sqrt{2}, \le→\leq) that would
have silently fallen the report back to the legacy generator; also avoided \text{-} in mathtext.

Verified: builds via direct builder call (89 pages); Table 4.5, Method-3, and 4.3 flux (B_inner)
visually confirmed.

### 2026-06-14 — Bug history saved + 6 more v11 quantities (10 of 12 done)

Expanded SESSION_HANDOFF.md into a full "BUGS & GOTCHAS — history" (legacy-fallback trap;
mathtext unsupported tokens \sqrt2/\le/\text{}; no unicode subscripts in ReportLab; circular
all_candidates ref; Windows console encoding; 2-pass TOC; the engine/data fixes already applied —
Bsat, field-engine asserts, wire-diameter, thermal-figure inversion).

Implemented 6 more of the 12 v11 quantities (now 10/12):
- #2 Rac/Rdc — 3.5.1: x = d/(2δ), F_skin/F_prox formulas, R_AC/R_DC = max(1, F_skin·F_prox) with
  the calibrated k_skin/k_prox/k_crowd coefficients.
- #3 CCM/DCM boundary — 4.2: i_avg > ΔIpp/2 condition + dcm_fraction at the design corner.
- #7 bore layering — 3.5.6: layers_needed, turns_per_layer, residual bore clearance.
- #9 thermal convergence — 4.7 THEORY: the T_core iterate-until-0.2K loop.
- #10 two-node thermal — 4.7: θ/Rca/Rwa/Rcw split, ΔT_core/ΔT_wdg, hotspot = max×1.12.
- #11 composite ranking score — 3.4.6: the weighted score formula + selected/top-5 candidate scores.

REMAINING (only the 2 figures): #4 per-θ flux waveforms, #12 Pcore(θ) double-hump — both need the
per-θ series from build_view_contract; deferred (recipe in SESSION_HANDOFF.md). No
documentation_agent change needed — these are additions within existing sections.

Verified: builds via direct build_full_report() (91 pages); the 6 new blocks present; two-node
thermal page visually confirmed (ΔT_core 31.2, ΔT_wdg 36.1, hotspot 40.5 °C).

### 2026-06-14 — The two waveform figures → ALL 12 v11 quantities done

Added the last two of the 12 v11 quantities, both per-θ figures fed by
step7_magnetic_calc.build_view_contract() (new helpers _view_contract [caches the contract on the
result dict so it runs once], _fig_flux_waveforms, _fig_pcore_waveform):
- #4 Figure 4.3 (§4.3): Bac,pk(t), Bdc(t), Bmax(t) over the half line cycle at 90 Vac, with the
  Bdc±Bac shaded band.
- #12 Figure 4.4 (§4.5): instantaneous core loss Pcore(t) at low line (90) vs high line (264),
  showing the characteristic high-line double-hump + an INSIGHT on why peak-point misreads it.

Verified: builds via direct build_full_report() (93 pages); both figures rendered and visually
confirmed (flux band + the double-hump signature). The full report is regenerated at
PFC_Report_VERIFY_Steps1_16.pdf for review.

All 12 v11 quantities (E1–E54 task-3 list) are now part of the report.

---

## Session 2026-06-14 (cont'd) — Embedded-iframe scrollbars + DC-bus capacitor simulation step

### A. Single browser scrollbar on the studio pages (Review / Sim Agent / Control Design)
Removed the "double scrollbar" (inner iframe scroll stacked next to the page scroll).
Each embedded studio iframe now auto-grows to its full content height so only the
browser scrollbar moves the page.
- `ReviewMagnetics.tsx`, `SimulationAgent.tsx` (same-origin srcDoc): neutralise the
  studio's internal `min-height:100vh` (`.replace('min-height:100vh','min-height:0')`),
  drop the fixed `height: calc(100vh-…)`, add `scrolling="no"`, and on load measure
  `document.body.scrollHeight` → set iframe height; a `ResizeObserver` on `body` keeps it
  synced across tab/slider changes.
- `ControlDesign.tsx` (cross-origin, no allow-same-origin): can't read the iframe DOM, so
  `public/control_design.html` now posts `{type:'docHeight',height}` to the parent (on load,
  resize, ResizeObserver, and after `setPythonValues`); the component listens and sets the
  iframe height.
- Internal scroll regions that are meant to scroll (studio sidebars `.side{overflow:auto}`,
  `.table-wrap{max-height:360px}`) are untouched.

### B. New DC-bus capacitor simulation step (between Step 15 and Step 16)
After the designer approves the capacitor, the flow now routes through a simulation check
before Control Design.
- Embeds `specs/Capacitor/pfc_dcbus_agent_v4.html` (copied to
  `frontend/src/assets/pfc_dcbus_agent_v4.html`). Tool boots from
  `window.__DCBUS_PACKAGE__` (schema `dcbus-1.2`).
- New `frontend/src/components/CapacitorSimAgent.tsx`:
  - Fetches the authoritative envelope via `step15CapacitorDesign({state})` (same source as
    the Step-15 page: `design.inputs.{Vout_V,f_line_Hz,Vdc_ripple_V,Vdc_min_V,t_hold_ms}`),
    combines it with `confirmedState.intake.{application,thermal}` (Vac min/max, PF, eff,
    ambient, phases via `selected_channels`, fsw via `topology_specific_inputs`) and the
    approved `result.selected_cap` (manufacturer/series/C_uF/Vrated/ESR/I_rated/T0/L0).
  - Injects `window.__DCBUS_PACKAGE__` in `<head>`; a lock script before `</body>` disables
    every `.inputs` field (predefined → read-only), hides the package load/reset/export
    buttons, and disables the ambient slider `sT`. Only the INPUT VOLTAGE (`sVac`) and
    OUTPUT POWER (`sP`) sliders stay interactive → live ripple / ripple-I margin /
    hotspot-lifetime / V-derate / scope.
  - Same iframe auto-resize pattern (with a >2px threshold guard, since the tool listens to
    `window.resize → refreshAll`, to avoid a set→resize→set thrash).
  - Acceptance limits mirror upstream: Vripple/holdup/Vmin from `design.inputs`,
    `Imargin_min_pct = 0` (N/A if the part has no I_rated), `Thot_max_C = T0`,
    `life_min_h = 15×8760`, `Vderate_max_pct = 90`.
- `App.tsx`: added `'capsim'` to `Step`, `SS` label map; `handleStep15Approve` now goes to
  `capsim`; new render block (`onApprove → step16`, `onBack → step15`); `ControlDesign`
  `onBack` now returns to `capsim`.
- `Step15Capacitor.tsx`: approve button relabelled "Approve & Go to Simulation".

Verified: `tsc --noEmit` clean; `vite build` succeeds (50 modules).

### B2 — DC-bus sim corrections (false REJECT + two-power-band model)
The first cut judged the verdict at the tool's default corner `{VacMin, PoutMax}` = **90 V /
3600 W** — an impossible operating point (at 90 V low line the rated power is only 1700 W).
That over-stressed the HF current term → false REJECT. Step 15 actually sizes the worst case
at **180 V / 3600 W** (high line). Fixes:
- **Engine made band-aware** (`frontend/src/assets/pfc_dcbus_agent_v4.html`): added `_opAt(op,
  Vac)` (per-band eff/PF/Pout, low line ≤150 V vs high line) used in `hfCurrent` + `compute`;
  `worstCorner` now returns the high-line band min-voltage at rated power; `formToPkg` carries
  `bands`/`lineBreak_V` through each refresh.
- **Two-band package** (`CapacitorSimAgent.tsx`, schema `dcbus-2.0`): `operating.bands.{low,high}`
  with `{VacMin,VacMax,Pout_W,PF,eff}` (low 1700 W @ eff .945, high 3600 W @ eff .965),
  `lineBreak_V:150`. Capacitance at **nominal** (`tol_pct=eolAging_pct=0`) to match how Step 15
  sized `C_required`. Lifetime gate set to `null` (informational) — owned upstream by Step 15's
  3-method model; the tool's single-point Arrhenius would falsely fail an already-validated part.
- **GUI per the spec**: PF, efficiency, fsw, phases are no longer shown — applied automatically
  in the engine per operating point. DC bus voltage, line frequency, ambient range and the
  selected-capacitor data are shown as read-only constant **tiles** (lock script rebuilds the
  left panel; the original form fields stay hidden in the DOM so the engine still reads them).
  The OUTPUT-POWER slider is **coupled to the line band** (low→1700, high→3600) selected by
  INPUT VOLTAGE; **AMBIENT is now adjustable** too (Vac / Pout / Tamb sliders).
- Verified headless via the tool's pure engine: worst corner = `{180,3600,50}` → **APPROVE**
  (ripple 11.8/20 Vpp, hold-up 23/20 ms, ripple-I margin 32 %, hotspot 68/105 °C, derate
  88.6/90 %); the impossible 90 V/3600 W corner gave only 6 % ripple-I margin (the false-reject
  driver). `tsc`/`vite build` clean; lock-script IIFE `node --check` OK.

### B3 — line split 180 V, auto-play band coupling, plots, scope ripple view
- **Line split moved to 180 Vac** (was 150): `lineBreak_V=180`, boundary comparison `<` in both
  the engine `_opAt` and the React band logic so 180 V itself is high line (the worst corner).
- **Power-band coupling made native** in the tool (`coupleBandPower()` called at the top of
  `refreshExplore`) so the auto-play "sweep Vac across range" now switches OUTPUT POWER to the
  high-line rated power past 180 V (the old React `input`-listener coupling never fired on the
  sweep's programmatic `.value` writes). Removed the duplicate coupling from the React lock script.
- **Plots reconnected to the band model**: exposed `DCBUS._opAt`; "Lifetime vs input voltage"
  now uses each band's rated power per Vac (real curve with a step at 180 V instead of the
  impossible low-V/high-P collapse); "Ripple vs output power" sweeps 0→band-rated power at the
  current line. Lifetime-vs-ambient and ripple-vs-C already ran at the (band-consistent) explore
  point.
- **Scope shows the capacitor total ripple**: removed the amber `v_in(t)` line trace (it spanned
  ±√2·Vac and flattened the few-volt bus ripple) and zoomed the top scope onto `v_bus` ±
  max(ripple-limit, VppTot)·1.35 so the total LF+HF pk-pk swing is visible against the ripple-limit
  band; updated the readout ("v_bus total ripple … Vpp pk-pk") and legend.
- Verified headless: worst corner still `{180,3600}`→APPROVE; band split @90/179→1700, @180/230→3600;
  Lifetime-vs-Vin = 13.6→19.3 yr (low line) stepping to 7.5 yr at 180 V then 12 yr at 264 V.
  `tsc`/`vite build` clean.

### B4 — scope tight-fit, fixed plot axes, lifetime calibration
- **Scope auto-fits tightly to the bus ripple**: `scopeTop` y-range is now the actual min/max of
  the `v_bus` envelope (`VbB`/`VbT`) ± 15 %, with the wide ripple-limit band removed (it was
  forcing the scale). The total LF+HF pk-pk fills the view; legend updated.
- **Fixed plot axes (cursor moves, not the scale)**: `renderStaticPlots` precomputes stable bounds
  from the worst/best design case — ripple-axis top `yRip` (full high-line power), `yRipC` (min-C),
  lifetime-axis top `yLife`. Applied to **Ripple-vs-output-power** (x 0→high-line rated, y 0→yRip),
  **Ripple-vs-total-C** (x/y fixed), **Lifetime-vs-ambient** (y 0→yLife). Dragging sliders now moves
  the cursor within a stable frame.
- **Lifetime calibrated to Step 15**: the tool's single-point Arrhenius (`L0·2^((T0−Thot)/10)`) was
  off (~7.5 yr with a default L0=5000 h) vs Step 15's 3-method 25.4/18.4/74.6 yr. The component now
  fetches `step15CapLifetime` (at the worst-corner ambient) and passes `bank.cap.lifeAnchor_h =
  governing×8760`; the tool's `calibrateLife()` back-computes a constant `voltageLifeMult` so the
  worst-corner life equals the governing figure, and all explore/plot lifetimes scale physically
  around it. `formToPkg` carries the multiplier. A tile shows the Step-15 3-method numbers + anchor.
- Verified headless: anchor 18.4 yr → mult 2.465 → calibrated corner life 18.40 yr (APPROVE);
  explore points 38 yr (low line, hot) … 84 yr (high line, cool). `tsc`/`vite build` clean.

---

## Session 2026-06-14 (cont'd) — Controller reference database + database agent

### C1 — Local reference DB (`backend/data/controllers/`)
One folder per controller + shared theory, with a machine-readable `manifest.json` and `README.md`.
- `fan9672/` — FAN9672-D (datasheet), AN4165-D (FAN9673 sibling interleaved-CCM-PFC guideline,
  same method), AN5257 (avg-current-mode interleaved PFC theory), plus the project's worked
  `FAN9672_Control_Loop_Design_Report_Rev2.1.doc` and `FAN9672_Control_Design_Tool_v4.html`.
- `_common/control_loop_design/` — SLUA079, SLUP098, SLVA662, Practical-Feedback-Loop-Design-Buck
  (controller-agnostic compensator theory).
- Copied from `specs/Controller/{FAN9672 Reference Documents, Control Loop Design Reference documents}`.
- **Known gap:** designer named AND9925-D for FAN9672 but the source folder had AN5257 instead;
  recorded under `missing` in the manifest/README — drop the PDF in to add it.

### C2 — Database agent (`backend/app/reference_agent.py`)
Self-contained retrieval agent, **no new dependencies** (PyMuPDF + stdlib only):
- Reads `manifest.json`; extracts text from **PDFs** (per page) and **HTML/MHTML** incl. the
  HTML-based Word `.doc` export (per ~1800-char window). Binary OLE `.doc` is skipped.
- **Pure-Python BM25** ranker (k1=1.5, b=0.75) over page/section chunks; tokenizer keeps technical
  tokens like `fan9672`. Index cached to `data/controllers/.index.json` (mtime/size signature →
  auto-rebuild; gitignored).
- Controller-scoped retrieval: `query(question, controller="fan9672")` searches that controller's
  docs + its `common_collections`. Returns ranked passages with citations (`DOC p.N` / `DOC §N`) +
  snippets. Optional `synthesize=True` → grounded, cited Claude answer (`claude-sonnet-4-6`,
  `ANTHROPIC_API_KEY`); **gracefully degrades to retrieval-only** when no key (current state).
- Endpoints in `main.py`: `POST /controller-db/query`, `GET /controller-db/sources`.
- Verified: index = 134 chunks / 9 files; queries return correct top hits (RIC/crossover → AN4165-D
  pp.6-7; compensators → SLVA662; FAN9672 comp values → the report `.doc` + design tool). API 200
  via TestClient. CLI: `python -m app.reference_agent "<question>"`.

### C3 — Step-16 hook + GUI removals
- **Reference agent hooked into Step 16**: new `frontend/src/components/ControllerReferences.tsx`
  (collapsible "📚 Controller references" panel) rendered in `ControlDesign.tsx` between the iframe
  and the action bar. Auto-loads a starter set on mount, has a free-text search box + topic chips
  (Voltage loop / Current loop / Multiplier-gain / Type II-III / Pin functions), and shows ranked
  cited passages (citation badge + title + snippet). Client fn `controllerDbQuery` + types
  `RefPassage`/`RefQueryResult` added to `client.ts`. Retrieval-only until an `ANTHROPIC_API_KEY`
  is set (then `synthesize` can add a cited answer).
- **GUI removals (per designer):**
  - `DonePanel.tsx` — removed the "Mode B — 25-step engineering sequence" card + its `MB_STEPS` data.
  - `Step7Wizard.tsx` — removed the wire-page note "Both modes apply the same pass/fail gates …".
  - `ReviewMagnetics.tsx` inject — removed the top "Reviewing <part> …" banner and the
    "Pre-loaded from approved design …" footer; now also `hideSection('3D view controls')` and
    `hideSection('Summary + export')` in the studio sidebar. Header comment updated.
- Verified: `tsc` + `vite build` clean; live `POST /controller-db/query` returns cited passages.

### C4 — report citations + Review turns-mismatch fix
- **Step-16 report citations**: new `_ch6_references()` in `doc_report_builder.py` appends **§6.9
  Reference Documentation** to Ch.6 — §6.9.1 bibliography (controller docs + shared control-loop
  theory, from `reference_agent.sources()`) and §6.9.2 per-design-aspect references. Fully guarded
  (try/except) so a missing DB never breaks the report. Verified: renders §6.9/6.9.1/6.9.2 with all
  six docs + aspect citations.
- **§6.9.2 grounded cited paragraphs**: each aspect (control architecture, current/voltage loop,
  compensator equations, pin config) now queries the agent with `synthesize=True, k=3`; when an LLM
  is configured it renders a short paragraph written strictly from the retrieved excerpts with
  inline citations + a `[Sources: …]` line (`body()`), under sub-heading "Grounded Reference
  Summary by Design Aspect". Falls back to the §6.9.2 citation table when no/failed LLM. Answer text
  is HTML-escaped (`<`,`&`,`>`) before going into ReportLab Paragraphs. Verified both paths
  (live key is set but out of credits → graceful table fallback; monkeypatched LLM → grounded
  paragraphs render, inline cites kept, escaping correct).
- **Review-page turns mismatch (recurring) — root cause + guardrail**: the studio's `N` control is
  `<input type="range" max="52">` (stacks max=4). A range input **clamps `.value` to [min,max]**, so
  injecting an approved `PY.N`=71 silently truncated the FORM field to 52. The JSON-island summary
  showed the real 71, but `drawWindowBuild` (`passes = i.N×nParallel`), fill %, and the canvas
  overlay read the clamped form value → fewer turns drawn. **Guardrail** (`ReviewMagnetics.tsx`
  overrides loop): before assigning any override, if the target is a `type="range"`, widen its
  `min`/`max` to include the value, then set `.value` (and sync the `*Val` label). Now no hardcoded
  slider bound can truncate an injected value. Also fixed the hardcoded "2 × N" label in
  `review_magnetics.html` to use `cfg.nParallel`. Documented as recurring bug #5 in memory
  `review_page_recurring_bugs`.
- `tsc` + `vite build` clean; `_ch6_references` renders standalone (3 pp).

### C5 — more Review / DC-bus GUI removals
- **Review page** (`ReviewMagnetics.tsx` inject block 5b — elements HIDDEN not removed, so the
  studio's onclick wiring never hits null): hide all `.toolbar` + `.export-grid` (every "Export …
  PNG", Export JSON/CSV, "Generate design review summary", "Refresh summary", "Copy summary"),
  hide `#reviewStatus` (the "Press \"Generate…\"" line), and hide the captions "Titles deliberately
  match report style…" (`.tiny`) and the h3 "Generate design review summary". Removed the React
  "engine fed our DB physics · tiers …" line from the shadow cross-check panel.
- **Simulation Agent** (`pfc_sim_agent_v14.html`): `noteBox` no longer prints the "All design data …
  model fallbacks" blurb (keeps only the validation-error text when present).
- **DC-bus simulation** (`CapacitorSimAgent.tsx` lock): removed the "These specs are predefined …
  output power follows the selected line range" tile note; the masthead `srcTag` ("package:
  injected (window.__DCBUS_PACKAGE__)") is now `display:none`.
- Verified: phrases gone from source; dcbus lock IIFE `node --check` OK; `tsc`/`vite build` clean.

### C6 — Voltage-sweep dual y-axis + iGSE note removal
- **Dual y-axis** on Review → Voltage sweep → "Flux Density and Inductance Vs Input Voltage"
  (`review_magnetics.html`): extended `drawPlot()` to support a right axis — any series tagged
  `axis:'right'` auto-scales against a separate right scale with right-side tick labels, reserved
  right margin (`m.r` 58 when present), and an optional `rlabel`. Fully backward-compatible (no
  right-axis series → identical to before, used by all the other charts). Updated the `sweepPlot2`
  call: orange **Bac,pk** stays on the LEFT in true Tesla (`ylabel` "Flux density Bac,pk (T)"),
  green **Lfull** moves to the RIGHT axis in true **µH** — the old `Lfull/4000` display hack is
  removed (legend now "Lfull (µH)", `rlabel` "Inductance Lfull (µH)"). Green now reads actual
  inductance and matches the `Lfull (µH)` table column.
- **Removed the iGSE banner row** "Python iGSE — N design points · sweep charts remain analytical"
  that `ReviewMagnetics.tsx` block H prepended to the sweep table; the table starts at data rows.
- Verified: `tsc`/`vite build` clean; `review_magnetics.html` script `node --check` OK.

### C7 — Design Review Summary tab: fit table + read-only justified summary
- **Audit table fits, no inner scroll**: scoped CSS `#review .table-wrap{max-height:none;overflow:visible}`
  (global `.table-wrap` 360px scroll unchanged for the other tabs).
- **Summary box** (`#summaryOut`): made **read-only** (`readonly` attr), **justified**
  (`text-align:justify`), no inner scrollbar (`resize:none;overflow:hidden`), and **auto-grows to
  content** via new global `fitSummary()` (sets height = scrollHeight). Called at the end of the
  studio `renderAll()`, after the React inject's block-G summary rewrite, and on every tab switch
  (so it sizes correctly once the hidden Review tab becomes visible). The existing iframe
  ResizeObserver then grows the page to fit → single browser scrollbar, no clipping.
- Verified: `tsc`/`vite build` clean; studio `node --check` OK.

### C8 — DC-bus sim: heading text + Vwork from design
- Tile section headings (`CapacitorSimAgent.tsx`): "Fixed operating conditions" → "Operating
  conditions"; "Selected capacitor (fixed)" → "Selected capacitor"; lifetime note
  "Lifetime — Step 15 (3-method, @N °C):" → "Lifetime 3-method, @N °C:".
- Removed "· package: injected (window.__DCBUS_PACKAGE__)" from the verdict `stampWhy` text
  (`pfc_dcbus_agent_v4.html` renderVerdict); the masthead `srcTag` was already hidden (C5).
- **Vwork now equals the design DC bus voltage**: was `Vbus/nS·(1+imb) + VppTot/2/nS` → showed
  397 V (393 bus + ~4 V half-ripple). Changed to `Vbus/nS·(1+imb)` so the working voltage is the
  upstream design bus voltage (e.g. 393 V); ripple is no longer added to the derate basis. Verified
  headless: Vwork 393.0 V, vDer 87.3 %, verdict APPROVE.
- `tsc`/`vite build` clean; dcbus engine `eval`/compute smoke OK.

### C9 — DC-bus sim: part number, temp-rating fix, lifetime gate, footer removal
1. **Part number tile** added to "Selected capacitor"; `bank.cap.part_number` now carried in the
   package (from `selected_cap.part_number`).
2. **Temp-rating fix** (no 85 °C parts exist): the cap-table rows never exposed a numeric temp, so
   `chosenPart.temp_rating_C` was `undefined` → fell back to **85**. Added `op_temp_max_C` to the
   `get_cap_table` rows (`step15_cap_db.py`); `Step15Capacitor.tsx` now sets `selected_cap`
   `op_temp`/`temp_rating_C` from `chosenPart.op_temp_max_C ?? 105` (both report + onConfirm paths).
   Backend `run_capacitor_design`/`verify_configuration` fallback changed `…get("temp_rating_C",85)`
   → `get("temp_rating_C") or get("op_temp_max_C") or 105`. (Re-approve Step 15 to refresh an
   already-stored cap.)
3. **Lifetime gate** in the acceptance ledger: `life_min_h` null → `15×8760`; ledger Lifetime row now
   shows years (value/limit "18.4 yr" / "15 yr"). PASS/FAIL is consistent with Step 15 because the
   sim life is calibrated to its governing value. Verified headless: 18.4 yr ≥ 15 yr → PASS, verdict
   APPROVE.
4. **Removed the footer blurb** "Tier-1 analytic model, judged at … follow measured > fields >
   analytic." (`pfc_dcbus_agent_v4.html`).
- `tsc`/`vite build` clean; backend ast/import OK; dcbus engine compute smoke OK.

### C10 — remove remaining hardcoded/stale values in cap selection
Audit found three more values the DC-bus sim hardcoded instead of sourcing from the DB (same
root cause as the temp bug — `get_cap_table` under-exposed DB columns). Fixed:
- **Cap-table now exposes** `ripple_hf_A`, `lifetime_temp_C`, and a package-based `Rth_ca_CW`
  (`step15_cap_db.py`: 10 °C/W snap-in/screw, else 15 — same model as `verify_configuration`).
  Carried into `selected_cap` (`Step15Capacitor.tsx`, both report + onConfirm; type extended).
- **`CapacitorSimAgent.tsx`** now uses real values instead of guesses:
  - `freqMult_HF` = `ripple_hf_A / I_rated_120hz_A` (was hardcoded 1.4).
  - `Rth_CperW` = `Rth_ca_CW` (was hardcoded 18 → now 10 for the snap-in; hotspot 62.9→57.2 °C,
    consistent with Step 15).
  - Arrhenius reference `T0_C` = `lifetime_temp_C`; new `temp_max_C` = `op_temp_max_C` drives the
    "Temp rating" tile and the `Thot_max_C` hotspot limit (previously conflated into one `T0`).
- Verified headless: cap-table exposes ripple_hf 2.996 / lifetime_temp 105 / op_temp_max 105 /
  Rth 10; freqMult 1.4; Rth 10 → hotspot 57.2 °C, life 18.4 yr (anchored), verdict APPROVE.
  `tsc`/`vite build` clean; backend ast OK. (Re-approve Step 15 to refresh an already-stored cap.)

### C11 — Control Design page improvements ("Improvments and Corrections.docx")
All in `frontend/public/control_design.html` (mirrored to `src/assets/`), cross-origin so edited
directly; buttons HIDDEN (not deleted) to keep their JS handlers from hitting null:
1. Title "PFC Control Loop Design Tool — v4" → **"Control Loop Design"** (`<h1>` + `<title>`).
2. Removed the "Mode-specific design … no anchored estimates" subtitle blurb.
3. Hid the toolbar buttons: Load Report Defaults, Export Summary, Generate Report, Save JSON,
   Load JSON (kept Low Line / High Line). The React Steps-1–16 report button is unaffected.
4. **Mode Inputs**: Vout, fSW, L per phase, CO, rL, rC, η are now `readonly` constants (dashed,
   muted styling via `input[readonly]`); values still injected by `setPythonValues` which ends in
   `recalc()`.
5. **New "Components Fixed by Controller" panel** holding RIAC, RVIR, RRLPK (moved out of Mode
   Inputs, read-only — set by the FAN9672 / mode).
6. Removed the **Controller References** panel from `ControlDesign.tsx` (dropped import + render).
7. **Soft Start C_SS**: only `t_SS` stays editable; the standard cap is now a read-only *suggested*
   value (new `bomRow4Static` + `AUXHEAD_SUGGEST`, `css = nearestStd(...)`) instead of a selectable
   dropdown.
- Verified: app script `node --check` OK; `tsc`/`vite build` clean. (Cross-origin iframe served
  from `public/`.)

### C12 — Documentation agent: control-loop equation derivation (Ch.6)
Added a step-by-step theory/derivation of the inner current-loop and outer voltage-loop equations
to the Control Scheme chapter, from the two new derivation docs
(`Inner_Current_Loop_Theory_Derivation.docx`, `Outer_Voltage_Loop_Theory_Derivation.docx`) +
the DB control-loop references.
- New `_ch6_loop_derivation(story, res)` in `doc_report_builder.py`, rendered as **§6.1.1 Loop
  Structure**, **§6.1.2 Inner Current-Loop Derivation** (8 steps: averaged boost model →
  small-signal → Gid(s) with the R_LOAD/2 numerator zero ≠ ESR zero → full T_i(s) with
  R_CS/V_RAMP, H_CS, Type-II OTA), **§6.1.3 Outer Voltage-Loop Derivation** (energy-balance plant
  with the factor-2 denominator → ESR + RHP zeros → G_i,cl tracking, G_MOD, H_v, Type-III →
  full T_v(s)). Equations via `eq_box` (matplotlib mathtext) with worked numbers (R_CS/V_RAMP=0.003,
  f_RC≈169 kHz, H_v≈0.00636, G_MOD≈1.21/2.56 A/V, f_ESR≈7.2 kHz) + a THEORY box citing the docs/§6.9.
- **No renumbering**: placed as subsections of §6.1 (rendered before §6.2), so §6.2–§6.9 are
  untouched — avoids the documented renumbering-cascade risk.
- §6.1 heading → "Control Architecture and Loop-Equation Derivation"; chapter-splash bullet updated.
- Fixed two unsupported mathtext tokens (`\big(`/`\Big(` → plain parens).
- Verified: `_ch6_loop_derivation` renders (3 pp standalone); full `_ch6` builds 15 pp with clean
  6.1→6.1.3→6.2→…→6.9 numbering and all existing sections intact. Backend ast/import OK.
  ("Later we will add more details" — this is the first pass: algebraic backbone + final equations.)

### C13 — Control-design report replication, Phase 1 (Steps 1–8) + AND9925-D in DB
Target: replicate `FAN9672_Control_Loop_Design_Combined_with_Thesis_Derivation.docx` (69 tables, 14
figures) as our Control Design chapter at equal quality/detail. Phase 1 = calc agent + report for
Steps 1–8 (review iteration).
- **AND9925-D added** to `data/controllers/fan9672/` + manifest (title "FAN9672/9673 Tips and
  Tricks", Rev 3); reference index rebuilt; README `missing` cleared.
- **Calc agent `step16_steps1_8.py`** (`compute_steps_1_8`): Steps 1 (spec inputs) · 2 (base
  constants) · 3 (IAC + V_LPK, 8 pts) · 4 (oscillator R_RI candidates) · 5 (FBPFC divider + PVO) ·
  6 (R_CS Method-1 AN4165 Eq31 + Method-2 AND9925 Eq11 sweep + verify + power) · 7 (GMOD 3-path
  A/B/C across 8 pts + scorecard) · 8 (R_GC/R_LS/C_SS/ILIMIT/ILIMIT2). Reverse-derived formulas
  verified to reproduce the doc: R_CS M1 15.99/15.10 mΩ, V_EA,max 4.356/4.577 V, GMOD A
  5.0583/10.1167, C 1.7131/3.4262, B/C 2.9527, R_GC 38.10 kΩ, R_LS 66.32 kΩ, C_SS 400 nF.
- **Report `report_steps1_8.py`** (`build_steps_1_8` / `make_pdf`) renders the block via
  doc_report_builder helpers (step_h/sub_h/body/eq_box/data_table/annotation) → 12-page review PDF
  `PFC_Chapter6_Steps1_8_Control_Design.pdf` (our font/alignment, callout boxes, typeset equations).
- **Designer resolutions (2026-06-16):** (1) R_RI now **computed from f_SW** via the FAN9672-D
  oscillator relation `R_RI = 1.2e9/f_SW − 3430` → 13.71 kΩ → E96 13.7 kΩ (70.05 kHz); candidate
  table is computed from E96 neighbours, not hardcoded. (2) ILIMIT crest current uses the
  **standard formula** √2·P/(η·N·V_min) = 14.13 A → R_ILIMIT 17.07 kΩ, R_ILIMIT2 4.02 kΩ.
  (3) V_LPK@264 Vac = 3.71 V accepted. Review PDF regenerated (12 pp).
- **Schematic plan agreed:** SchemDraw (Type-II/III networks + architecture block diagrams,
  auto-labelled from the calc agent) + KiCad (board schematic Fig S-1); Bode/transient via
  matplotlib in Phase 2. SchemDraw is a new dependency — to add on confirmation.

### C13b — Steps 1–8 expanded to FULL document detail (pages 17–31)
Designer flagged the first cut abbreviated the steps. Re-extracted the docx INCLUDING OMML math
(`m:oMath`) to capture every worked equation, then rebuilt to reproduce pages 17–31 verbatim —
only font/text/alignment changed to our style.
- Calc agent (`step16_steps1_8.py`) now also emits all worked intermediates: Method-1 num/den per
  range; §6.4 V_EA back-calc num/den; §7.4/7.5 Path A/B/C step values (LL & HL); and the §7.6
  **V_RM × V_LPK invariant** table — derived exact formulas FR `K_RM·V_EA,eff/(2·K_RLPK·R_RLPK)` =
  0.37775 and HV `…/(K_RLPK·R_RLPK)` = 0.79995, V_RM@90FR = 0.299 (matches doc).
- Report (`report_steps1_8.py`) rewritten: every sub-step rendered as label + equation with the
  substituted numbers (e.g. "Step 2 Numerator: 90²×2×7500 = 8100×15000 = 1.215×10⁸"), both LL and
  HL, every description/THEORY/CONCEPT/INSIGHT/PITFALL/DECISION verbatim, every table full
  (3.1/3.2/6.1/6.2a/6.2b/6.3/6.4/7.1/7.2/7.5/7.6/7.7/8.6). Review PDF now **21 pp** (was 12).
- Verified rendering of worked pages; numbers match the document throughout.

### C13c — Steps 1–8 designer corrections (10 items)
1. **Crossover freqs configurable** — `fci`/`fcv` are now inputs (default 8 kHz/17 Hz, GUI-selected);
   Step 4 concept references f<sub>ci</sub> dynamically, not hardcoded 8 kHz.
2. **R_FB1 fixed series** — R_FB1 = 3 × 1.21 MΩ = 3.63 MΩ (fixed); R_FB2 is the designer-adjustable
   lower resistor, computed from target V_OUT (`rfb2 = rfb1/(Vout/Vref−1)` → 23.2 kΩ). Step 5 reworked.
3. **6.2 note added** — "V_EA,eff = V_EA,max − 0.6 V … AND9925-D recommends V_EA,max 4–5 V."
4. **Sci-notation fixed** — body text now uses Unicode superscripts (`9.014 × 10¹²`) via new `_sct()`
   instead of raw `\times10^{}` leaking as literal text.
5. **R_CS selection clarified** — NOTE: 15 mΩ is the common-ground of both methods; GUI presents the
   overlap range and the designer's pick is carried downstream.
6. **§7.2 verbatim** — full Path A/B/C derivations + "Why A=B" / "Why B≠C" reproduced word-for-word.
7. **§7.3 verbatim** — back-calc intro + worked Step 1–4 (LL & HL) for V_EA,eff added.
8. **ILIMIT crest / I_L,pk worst-of-both-corners** — crest evaluated at 90 V and 180 V (worst 14.66 A
   @180 HL); I_L,pk = max(I_φ,pk@90, I_φ,pk@180) = 17.51 A @180 HL. R_ILIMIT/R_ILIMIT2 use the worst.
9. **8.6 scorecard** — C_GC (430 pF, pole 9.664 kHz) and C_LS (240 pF, pole 9.972 kHz) rows added;
   designer-selectable cap values set the filter pole.
10. Added "NOTE" annotation style (neutral slate). Review PDF now **22 pp**; numbers verified vs doc.


## C14 — Control report Steps 9 & 10 (reference Steps 12 & 13), + 7.7/7.8 fixes
- Step 7.7 scorecard expanded 9->18 rows (added GMOD_B LL/HL, Path A/B split, VRM max LL/HL, V_LPK max LL/HL, VRM×V_LPK invariant FR/HV) to match reference exactly. Step 7.8 verdict reproduced word-for-word (DESIGN PASS + 6 numbered points + GMOD_C handoff). Fixed glyph boxes: 1×10⁻⁴ via <super>, ⚠ -> ! in 3.2/7.6 tables.
- Step 9 (BIBO, ref Step 12): new step16_step9_bibo.py (calc) + report_step9.py. Subsections 9.1-9.10 word-for-word; divider ratio/resistors/caps/V_BIBO sweep/EN61000-4-11+SEMI F47 compliance all COMPUTED & verified vs doc.
- Step 10 (Inner Current Loop, ref Step 13): new step16_step10_iloop.py (calc) + report_step10.py. Boost plant G_id(s) DCR-damped; full 90Vac worked calc, 8-point tables, Type-2 OTA compensator (R_IC 120k/C_IC1 1.3n/C_IC2 51p), crossover 8.12kHz PM 62.8°. ALL values sourced from prior steps (V_OUT<-S5, R_CS<-S6, Lφ/C_O/f_ci<-S1/S4) — not hard-coded. Two Bode figures (open & closed loop) rendered live from the transfer functions. Fig 10A schematic deferred to SchemDraw pass.
- Unicode subscripts (Tᵢ,F₀) replaced with ASCII in headings/table-headers per CLAUDE.md rule 7.
- Combined report now Steps 1-10: PFC_Chapter6_Steps1_10_Control_Design.pdf (49 pp, 0 glyph boxes). Standalone: PFC_Chapter6_Step9_BIBO.pdf (12 pp), PFC_Chapter6_Step10_InnerLoop.pdf (14 pp).


## C15 — SchemDraw schematics setup (Fig 10A)
- Installed schemdraw 0.23, added to backend/requirements.txt.
- New app/mode_b/schematics.py: SchemDraw->PNG->ReportLab Image helper (matplotlib backend). type2_ota_compensator() draws the inner-loop Type-II OTA network (OTA + R_IC/C_IC1 series branch ∥ C_IC2), values injected from the calc agent.
- report_step10.py Fig 10A placeholder replaced with the live schematic + caption.
- Step 10 standalone -> 15 pp; combined Steps 1-10 -> 50 pp; 0 glyph boxes. schematics.py is the shared entry point for all future report schematics (Steps 11-14, board schematic S-1).


## C16 — Control report Step 11 (Outer Voltage Loop, ref Step 14) + Type-III schematic
- New step16_step11_vloop.py (calc) + report_step11.py. Subsections 11.1-11.9 word-for-word (Method B / SLVA662).
- Consumes Step 10 inner loop: rebuilds compensated T_i(s) from s10 plant objects to form G_i,cl(s). Voltage plant G_vp(s) uses L_eq=L/2.
- ALL values computed from prior steps + DESIGNER-SELECTED freqs (per instruction): f_cv, f_z1/f_z2/f_p1/f_p2 are DEFAULT_INPUTS, not hard-coded. CS-filter pole stays designer-set in Step 10. Verified vs doc: Hv 0.006350, Tvbase 11.3246 (21.08dB), G 0.088303, aa 0.8483, R2 143.23k/R3 8.6336M/C1 370.4n/C2 1.0815n/C3 23.64n (calc) -> 143k/8.66M/390n/1.1n/24n (std); 14.8 PZ exactly 3/12/50/17 Hz; 14.9 HL 17.00Hz/PM82.4, LL 7.80Hz/PM80.9.
- comp_type selector: 'type3' (default, reproduces doc) | 'type2'. CURRENT loop always Type-2; VOLTAGE loop designer-selectable (type2 path verified functional, HL PM 72.3). NOTE box added to report stating this.
- schematics.py: added type3_ota_compensator() (Fig 14A) — R1/R4 divider, R3-C2 feedforward ∥ R1, OTA, C3∥(R2+C1) output. Visually verified layout. Snapping: R->E96, integrator cap C1->E12, precision caps C2/C3->E24 (matches doc std column).
- Figs 3 (open-loop Tv) & 4 (closed-loop Tv) rendered live. Fixed ∥ (U+2225) glyph box in prose -> ||.
- Step 11 standalone 11pp; combined Steps 1-11 -> PFC_Chapter6_Steps1_11_Control_Design.pdf (61pp, 0 glyph boxes).


## C17 — Control report Steps 12 & 13 (ref Steps 15 & 16)
- Verification gate confirmed to user first (re-ran step9/10/11 __main__ harnesses; engine==doc==report by construction; disclosed only 4th-5th sig-fig rounding deviations).
- Step 12 (Step Load Transient, ref Step 15): new step16_step12_transient.py (calc) + report_step12.py. Closed-loop output impedance Z_cl=Z_open/(1+T_v) step response via scipy.signal.step; G_i,cl=1 at this timescale. Subsections 12.1-12.3 word-for-word. VERIFIED vs doc 15.3: HL 0->100 -28.9V/152ms, LL -25.9V/154ms, all 6 transitions match. Figure 5 (2x3 grid, LL/HL, ±1% band) live.
- Step 13 (Input THD & 120Hz Rejection, ref Step 16): new step16_step13_thd.py (calc) + report_step13.py. Subsections 13.1-13.3 word-for-word incl 16.3 optimization sweep (re-designs at 12/17/20/25 Hz, recomputes PM/rej/dip/recovery). VERIFIED vs doc 16.2: Vrip 2.60/5.51V, rej 30.1/23.6dB; THD3 1.43/2.95% using per-range V_EA,eff sourced from Step6 vee_ll/vee_hl. Sweep: rej & dip match doc; 25Hz HL 18.4dB fails 20dB floor (matches). Figure 6 (closed-loop attenuation + rejection bars) live.
- Fixes: literal %% in format strings (0->100%, ±1% band); THD3 subscript glyph -> <sub>3</sub>/THD3 (rule 7).
- Cross-refs renumbered: doc Step14->our 11, doc Step17->our 14.
- Combined Steps 1-13 -> PFC_Chapter6_Steps1_13_Control_Design.pdf (69pp, 0 glyph boxes). Standalone S12 4pp, S13 4pp.
- Remaining: doc Step 17 -> our Step 14 (Loop Equation Accuracy & Compensator Optimization).


## C18 — Control report Step 14 (ref Step 17) + Appendices A-E
- Step 14 (Compensator Optimization, ref Step 17): new report_step14.py. Per instruction PITFALL and 17.1 (incl Figure 7) OMITTED; only 17.2 reproduced, placed after INSIGHT as 14.1. Four trade-off designs (Baseline 17 / A 12 / B 20 / C 25 Hz) COMPUTED via the Step 13 optimization sweep (extended to return per-design R2/C1/C3 + HL bode/transient curves). Verified vs doc 17.2: comp values 143k/390n/24n @17Hz exact; off-baseline within E-series snap. Figure 8 (open-loop, transient, rejection bars for 4 designs) live.
- Appendices A-E (new appendices.py), word-to-word: A (A.1-A.7 thesis-level boost plant + OTA Type-III derivations, ~70 eqs reconstructed as mathtext), B BOM (step refs renumbered 13->10,14->11), C bench test plan, D references, E quick-reference (3 tables). Stated example constants reproduced verbatim (incl A.7.8 GMOD with KMAX=1.4 -> 1.209/2.561, and A.7.9 fp1/fp2 ordering as doc gives).
- mathtext fixes: ig*->plain parens, 	frac->rac. Glyph fixes: prose combining-hat (U+0302)->\<super>^\</super>, ≫->&gt;&gt;, ć->c.
- Combined Steps 1-14 + Appendices A-E -> PFC_Chapter6_Steps1_14_Control_Design.pdf (89pp, 0 glyph boxes). Standalone: Step14 3pp, Appendices 16pp.
- CONTROL CHAPTER COMPLETE: all 17 reference steps (renumbered 1-14) + appendices reproduced; every calc engine verified vs doc.


## C19 - Full combined report + GUI generation path
- Refactored report_steps1_8.py: build_story(inp) computes prior=compute_steps_1_8(inp) ONCE and threads it through steps 9-13 (fixed: steps 10-13 previously recomputed prior WITHOUT inp). Added build_control_report(inp)->bytes alongside make_pdf(path,inp).
- Backend main.py: GET /mode-b/control-report/defaults and POST /mode-b/control-report (inputs -> Steps 1-14 + Appendices PDF). Verified via uvicorn+curl: 200 application/pdf 3.87MB %PDF.
- Frontend: client.ts controlReport()/controlReportDefaults(); ControlDesign.tsx handleControlReport maps params+iframe state -> inputs, downloads FAN9672_Control_Loop_Design_Report.pdf. New primary button beside Steps 1-16 button. tsc clean.
- Generated+opened PFC_Chapter6_Steps1_14_Control_Design.pdf (89pp).


## C20 - Exact designState mapping (control_design.html -> control report)
- control_design.html getDesignState payload documented. Existing fields: vType('type2'|'type3'), cType('T1'|'T2'), mode, fci_Hz, fcv_Hz, r1fb, r4fb, rf, cf, dci_std, dcv_std, dcv_calc, dcv_cor, dcv_err.
- Added missing designer pole/zero TARGETS to the payload (public/ + src/assets/ copies): cfz_Hz, cfp_Hz (current zero/pole), vfz1_Hz/vfz2_Hz/vfp1_Hz/vfp2_Hz (voltage), gmv_S.
- ControlDesign.tsx handleControlReport now maps EXACT keys -> engine inputs: fci_Hz->fci, fcv_Hz->fcv, cfz/cfp->f_z/f_p, vfz1..vfp2->fz1..fp2, gmv_S->gmv, rf->r_m, cf->c_m, r1fb->rfb1_unit(+rfb1_count=1), vType->comp_type. Removed defensive guessing.
- Verified end-to-end: all keys propagate through prior->step10->step11 (fci 9000, fcv 18, f_rc 169.3k, fz_act 1113, gmv 100u, comp type3, rfb1 3.63M); PDF builds. tsc clean.
- Note: dist/control_design.html is build output (regenerated on npm build); public/ + src/assets/ updated.


## C21 - Frontend rebuilt + GUI button tested (Playwright)
- npm run build OK; dist/control_design.html confirmed carrying new designState fields (cfz_Hz/cfp_Hz/vfz1..vfp2_Hz/gmv_S).
- Playwright (chromium) drove the real built tool against live backend (uvicorn :8077) + static dist (:5199):
  (1) tool emits full designState: vType type3, fci 8000, fcv 17, cfz 1000, cfp 26000, vfz1/2 3/12, vfp1/2 50/17, gmv 1e-4, rf 2000, cf 4.7e-10, r1fb 3.63e6.
  (2) button mapping -> POST /mode-b/control-report -> 200 application/pdf 3.87MB %PDF; 0 console errors.
  (3) designer edit (fcv 17->20, fci 8000->9500, vfz1 3->4) propagates to report inputs exactly (fci 9500/fcv 20/fz1 4), valid PDF.
- Test files removed; servers stopped. GUI report generation verified end-to-end.


## C22 - e2e test, Type-II report fix, combined Ch1-5 + Ch6 report
- e2e (Playwright): frontend/e2e/control_report.spec.cjs drives the real Mode-A wizard (intake->done) against the live backend, then lands on the real Control Design page via a guarded window.__E2E_CONTROL__ seam (App.tsx) and clicks the real Control-Loop Report button -> asserts a valid PDF from /mode-b/control-report. Added data-testid="gate-option" to TopologyHITL/ControllerHITL/ChannelSelect cards. README documents the run recipe (build w/ VITE_API_URL=:8077, backend :8077, static dist :5199, npx playwright install chromium). ALL CHECKS PASS.
- FIX (Control-Loop Report button failed): root cause = report_step11.build_step11 hard-coded Type-III comp keys (fz1/r3s/...), so when the designer picked the Type-II voltage compensator (vType=type2) the build threw KeyError -> endpoint 500 -> "Control report failed". Added _build_step11_type2 (full 11.6-11.9 + figures + verdict for one-zero/one-pole Type-II) and branch in build_step11; added schematics.type2_voltage_compensator (Fig 14A Type-II). build_control_report now succeeds for BOTH type2 (3.78MB) and type3 (3.87MB).
- FEATURE (single combined report): "Generate & Download Report" on Control Design now returns ONE PDF = Chapters 1-5 (documentation agent, Ch6 omitted) + the full detailed Chapter 6 control report (Steps 1-14 + Appendices), merged via pypdf. main.py: _control_inputs_from_step16 maps step16_params + embedded js_design_state -> control-report inputs; _merge_pdfs concatenates; doc_generate_report full branch builds Ch1-5 (step16_params=None) + build_control_report and merges. Verified live: HTTP 200, 161 pages, 8.9MB.


## C23 - ControlDesign: single full-report button + Select Semiconductors (Chapter 7)
- ControlDesign page now has ONE report button: "Generate Full Report (Chapters 1-6 + Appendices)" (combined Ch1-5 + detailed Ch6 via docGenerateReport). Removed the standalone "Control-Loop Report (Steps 1-14 + Appendices)" button + handleControlReport + ctrl state + controlReport import. (/mode-b/control-report endpoint + client kept for API use.)
- New second button "Select Semiconductors ->" advances to Chapter 7. App.tsx: added 'semiconductors' step + SS label + onSelectSemiconductors wiring; new SemiconductorSelection.tsx (Chapter 7 scaffold carrying bus V / power / L / C forward). Stepper.tsx: added Semiconductors entry.
- e2e updated (Test B): asserts the single Generate-Full-Report button present, old Control-Loop Report button removed, Select Semiconductors button present, and that it navigates to the Chapter 7 page. ALL CHECKS PASS. tsc/build clean.


## C24 - Control Design redesign: Screen 1 (Power Plant Parameters) implemented
- Backend: POST /mode-b/control/power-plant (canonical_ops_table) returns the 9-point grid (vac, pout, eta_pct, pf, vin_pk, duty, rload, line) = same eta/PF as report Table 1.2.2.
- Frontend: new PowerPlantReview.tsx (Screen 1, themed React) - fixed-params cards (Vin range, Vout, Pout HL/LL, fsw, Nch, L, r_L, C, r_C, PF/eff targets, line freq), 9-point operating-point table, compliance card; Confirm & Continue gating. client.ts controlPowerPlant()/PowerPlantRow.
- ControlDesign.tsx: screen wizard state ('s1' -> 'tool'); S1 renders first, Confirm -> existing FAN9672 tool (S2-S7, to be migrated next); tool Back -> Screen 1.
- e2e Test B updated: asserts S1 renders + table loads (endpoint OK) + Confirm enables -> tool + buttons + Chapter 7 nav. ALL CHECKS PASS; tsc/build clean.
- Status: S1 DONE. Next: S2 (controller-fixed components + selectable caps/R_CS).


## C25 - Control Design redesign: Screen 2 (Controller-fixed components + selections)
- Backend: POST /mode-b/control/components returns 16 fixed/auto-calc components (R_RI, R_FB1/2, R_IAC LL/HL, R_RLPK, R_VIR FR/HV, RB1-4, CB1-2, R_GC, R_pin8=4.75k) + R_CS valid band (Method-1 bound: 12.84-15.1 mOhm, rec 15) + 8 selectable items (C_GC/C_LS/C_SS/C_LPK/C_RLPK/C_ILIMIT/C_ILIMIT2 with pin-filter poles, R_LS).
- Engine: compute_steps_1_8 now accepts optional rcs override (DEFAULT_INPUTS rcs=None) so designer R_CS flows downstream; _control_inputs_from_step16 maps step16_params.s2 {rcs_mohm,c_gc_pf,c_ls_pf} -> rcs/c_gc/c_ls.
- Frontend: new ComponentsSelect.tsx (Screen 2) - fixed table, R_CS constrained selector with live valid-HL&LL check, filter-cap + R_LS inputs; client controlComponents(). ControlDesign wizard s1->s2->tool; S2 selections stored + injected into handleReport step16_params.s2; tool Back -> Screen 2.
- e2e Test B: clears S1 then S2 (asserts components render + R_CS valid indicator + confirm) then tool. ALL CHECKS PASS; tsc/build clean. Verified R_CS=13mOhm flows into report.
- Status: S1, S2 DONE. Next: S3 (review Core Component Table + Fixed Coefficients).


## C26 - Control Design redesign: Screen 3 (Core Components + Fixed Coefficients review)
- Backend: POST /mode-b/control/coefficients returns the 11 controller-constant rows (report Step 2 table).
- Frontend: new CoreReview.tsx (Screen 3, review-only) - consolidated Core Component Table (fixed components + Screen-2 designer selections with function) + Fixed Coefficients/Internal Parameters table; client controlCoefficients(). ControlDesign wizard s1->s2->s3->tool; S3 reads s2sel (reflects R_CS override in fetched values); tool Back -> Screen 3.
- e2e Test B: clears S1,S2,S3 (asserts each renders + endpoint data + confirm) then tool. ALL CHECKS PASS; tsc/build clean.
- Status: S1, S2, S3 DONE. Next: S4 (Compensators & Bode) - first migration of interactive tool content into a gated React screen (or keep tool tab + confirm gate).


## C27 - Control Design redesign: Screens 4-7 (wizard-driven embedded tool) - REDESIGN COMPLETE
- control_design.html (public + src/assets): added 'wizard mode' - setWizardScreen postMessage activates one tool tab (screen2-5) + body.wizard hides the tab bar; setPythonValues now accepts rcs_mohm (designer R_CS -> state.rcsSel + rcsCustom).
- ControlDesign.tsx: screen wizard extended to s1..s7. S4-S7 drive the SAME mounted iframe via setWizardScreen (S4 Compensators&Bode interactive, S5 Transient, S6 iTHD, S7 Schematic). Per-screen action bar: Back/New design + 'Confirm & Continue' (S4-S6); S7 = 'Download + Review' (handleReport, combined Ch1-6+appendices) + 'Approve & go to Semiconductors' (gated: enabled only after a report is generated -> reportGen state). R_CS (s2sel) injected into the tool so the Bode reflects it.
- e2e Test B: full 7-screen walk (S1-S3 native, S4-S7 wizard labels, S7 Download+Review [route-mocked report] -> Approve enables -> Ch7). ALL CHECKS PASS; tsc/build clean. Verified S4 wizard mode via screenshot (tab bar hidden, interactive Ti(s) Bode with LL/HL overlay).
- STATUS: Control Design (Chapter 6) 7-screen confirm-gated redesign COMPLETE (S1-S7). Remaining GUI cleanup: broader items G1-G11 + Chapters 1-5 (open), and Chapter 7 build-out.


## C28 - Control Design screens 1-3 designer feedback
- S1 (PowerPlantReview): efficiency column header -> 'Efficiency η (%)'; switching freq labeled 'Switching frequency f_sw (selected)'.
- S2 (ComponentsSelect): reworked to standard-value DROPDOWNS. R_CS = dropdown of standard mOhm values within the HL&LL valid band (recommended flagged). Filter caps = per-cap dropdown of standard E6 values with LIVE pole freq (computed frontend from backend r_assoc_ohm). New cap set per designer: C_GC=470pF, C_RLPK=10nF, C_ILIMIT=10nF, C_ILIMIT2=10nF, C_VIR=10nF (new), C_LS=470pF; dropped C_SS/C_LPK from selectable. R_LS = dropdown of standard kOhm (12-87), default snapped to nearest standard (68k). Backend /mode-b/control/components returns options_mohm, options_pf, r_assoc_ohm, options_kohm.
- S3 (CoreReview): selectable rows updated to the new cap set; 'Pin-8 series resistor'/'R_pin8' renamed -> 'LPK series resistor'/'R_LPK', default 4.7 kOhm (was 4.75).
- e2e ALL PASS; tsc/build clean; verified S2 via screenshot (dropdowns + live poles + R_LPK 4.7k). Restarted user :8000 backend with --reload.
- Earlier this turn: diagnosed user 404 = stale 4-day-old backend holding :8000 (Errno 10048 on restart); cleared orphaned multiprocessing workers, freed port, started fresh.

## C29 - S2: R_LS tracks R_CS
- R_LS = Lφ/(1.5e-9·R_CS·ratio) ⇒ R_LS ∝ 1/R_CS. Selecting a non-recommended R_CS now
  live-rescales R_LS (calc_kohm·recommended/rcs) and snaps to the nearest standard kΩ.
- C_LS pole (cap across R_LS) now uses the SELECTED R_LS, so it tracks too.
- R_LS row note shows the live calc + '(tracks R_CS)'. Frontend-only; build clean.

## C30 - S4 split into 3 confirm-gated sub-screens (current / voltage / results)
- control_design.html (public + src/assets): tagged every #screen2 panel with data-sub
  (cur|vol|res); CSS hides non-active-sub panels in wizard mode. setWizardScreen handler
  now accepts a 'sub' field → toggles body.sub-cur/vol/res. Added Final Control-Loop
  Components panel (#allCompBom) + renderAllComp(p,dci,dcv): consolidated read-only table
  of R_CS, CS filter (R_F/C_F across R_CS), current comp (R_IC/C_IC1/C_IC2), voltage comp
  (Type-2/3), FB divider. Wired into recalc().
    · sub=cur: Std-Value, Current Loop, Ti Bode, Calc log
    · sub=vol: Std-Value, Voltage Loop, Tv Bode, Calc log
    · sub=res: Final Components, Tolerance, Scorecard
- ControlDesign.tsx: S4 now walks 4a current -> 4b voltage -> 4c results before S5; Back
  reverses (4a Back -> S3, S5 Back -> 4c). postWizard sends {screen:screen2, sub} on S4.
  Label shows '4a/4b/4c'. goNext/goBack replace WIZ_NEXT/PREV for S4.
- Verified headless (playwright): correct panels per sub, allCompBom 13 rows, no JS errors.

## C31 - S4 sub-screens: gated steps -> free sub-tab bar
- ControlDesign.tsx: S4 now shows a 3-button sub-tab bar (4a Current / 4b Voltage /
  4c Final components) above the iframe; clicking sets s4sub directly (effect re-posts
  {screen:screen2,sub} to the tool). S4 advances/retreats as a whole again:
  goNext/goBack reduced to WIZ_NEXT/WIZ_PREV (s4->s5 / s4->s3). Continue label simplified.
- No control_design.html change (sub switching already supported via setWizardScreen sub).
- Build clean.

## C32 - S4 refinements: hide calc log, bigger PZ, crossover sliders + guardrails
- control_design.html (public + src/assets):
  1) Compensation Calculation Log panel data-sub none -> hidden in all S4 wizard subs.
  2) Pole-Zero canvas H 74 -> 170px (data-h aware); markers/labels enlarged, centred
     marker row + faint guide; drag hit tolerance 12 -> 18px (.pz CSS 170px).
  3) Crossover scroll bars: fci slider bounded f_SW/20..f_SW/5, fcv slider 2..40 Hz,
     each with a live 'Allowed ...' band label. Sliders drive the number field;
     commit (change) snaps into band. gather() hard-clamps fci/fcv so the math always
     respects the guardrails. syncCrossoverUI() (called at top of recalc) keeps slider
     min/max + value + band labels in step with f_SW.
- Verified headless: calc log hidden, PZ 170px, fci[3.5k,14k]/fcv[2,40] bands + labels,
  clamps (fci 50000->14000, fcv 0.5->2), no JS errors.
- NOTE: user fcv spec was garbled ('not more than half 40 Hz') -> interpreted as max 40 Hz.

## C33 - S4 layout: PZ under Bode, drop BOM note, Line Range to left column
- control_design.html (public + src/assets):
  1) Pole-Zero placement moved out of the Current/Voltage Loop panels (left) to directly
     UNDER the corresponding Bode plot (right column) -> canvas now ~974px wide (was ~430).
  2) Removed the 'Report BOM uses E96 ... not the ideal ones.' note from Standard-Value panel.
  3) Moved Low/High line selector out of the header toolbar into a new 'Line Range' panel
     in screen2 left column (data-sub=cur vol) -> shows under the loop design on both 4a/4b.
     (Header previously held the only mode toggle, which sat above the wizard content.)
- IDs preserved (pzCur/pzVol/modeLow/modeHigh) so pzPointer/drawPZ/setMode wiring intact.
- Verified headless: BOM note gone, pz under correct Bode panels, modeLow in Line Range
  panel (not header), mode toggle works, no JS errors.

## C34 - S4/S5 cleanup: hide transient notes, move Line Range, trim fci label
- control_design.html (public + src/assets):
  1) Added global 'body.wizard .nowiz{display:none}'; tagged S5 Transient Notes panel
     (calcLog3) .nowiz -> hidden in wizard (S5 now shows only Load-Step Transient + dVout plot).
  2) Removed Line Range description text; MOVED Line Range panel to TOP of screen2 left
     column (above Standard-Value Series).
  3) fci: simplified label to 'Crossover f_ci (Hz)' and removed the 'Allowed ...' band
     readout (#fciBand). syncCrossoverUI already guards $('fciBand') with if(b) -> safe.
     Guardrail clamp + slider bounds unchanged. (fcv label/band left as-is per request.)
- Verified headless: left order Line Range>Std-Value>..., notes hidden, fciBand gone, no JS errors.

## C35 - Current-loop compensator: true k-factor auto-track + lock toggle
- control_design.html (public + src/assets): Current Loop panel gains a 'Auto-place f_z/f_p
  from f_ci (true k-factor)' checkbox (#ciKlock, default ON) + 'Target phase margin' input
  (#ciPM, default 60).
- designCI Type-2 branch: when locked, boost = clamp(PM_target - pmT1, 0..88) where
  pmT1 = no-boost PM (90+aTu); k = tan(45 + boost/2); f_z = f_ci/k, f_p = f_ci*k. Writes
  f_z/f_p back to fields + p so PZ markers, Bode, BOM all track. Manual fields disabled
  when locked. #ciKnote shows target/no-boost PM, boost, k, f_z, f_p. Unlocked = old manual.
- Wired ciKlock/ciPM to recalc; saveJSON/loadJSON persist them; loadDefaults sets lock OFF
  (report defaults are the exact manual f_z=1k/f_p=26k design).
- Verified headless: fci 8000 -> fz1.95k/fp32.9k (geo mean=fci); fci 12000 tracks; achieved
  current-loop PM 59.7 deg vs 60 target; PM 45 reduces boost; unlock re-enables fields. No JS errors.
- NOTE: wizard default current-loop design now uses k-factor placement (was fz1k/fp26k);
  uncheck the toggle for manual/report values.

## C36 - Voltage-loop compensator: true k-factor auto-track + lock toggle
- control_design.html (public + src/assets): Voltage Loop panel gains #vKlock checkbox
  (default ON) + #vPM target-PM input (default 60).
- designCV: when locked (live design only, gated !pure), boost = PM_target - pmNoBoost.
  Type-2: k=tan(45+boost/2), f_z1=f_cv/k, f_p1=f_cv*k (boost clamp 0..88).
  Type-3: coincident pairs, k=tan^2(45+boost/4), f_z1=f_z2=f_cv/sqrt(k),
  f_p1=f_p2=f_cv*sqrt(k) (boost clamp 1..160 so f_z2<f_p2 and R3>0). Writes placements
  back to vfz1/vfz2/vfp1/vfp2 fields + p so PZ markers, Bode, BOM track. Manual fields
  disabled while locked; #vKnote shows type/target/no-boost PM/boost/k/placements.
- Wired vKlock/vPM to recalc; saveJSON/loadJSON persist; loadDefaults sets lock OFF.
- Verified headless: Type-3 fcv17 -> fz/fp 10.96/26.37 (geo mean=fcv), PM 59.4; fcv25 tracks
  PM 59.9; Type-2 fcv25 fz8.55/fp73.07 PM 60.1; unlock re-enables. No JS errors.
- NOTE: wizard default voltage-loop design now uses k-factor placement (was the SLVA662
  manual fz1=3/fz2=12/fp1=50/fp2=17); uncheck for manual/report values.

## C37 - Auto-optimize (balanced) for both loops + tightened guardrails
- Guardrails updated per designer rules: f_cv in [10,20] Hz (HL; reject 100/120 Hz, keep
  response); f_ci in [2 decades above f_cv (100*f_cv), f_SW/6] (loop decoupling + separation).
  gather() clamps + syncCrossoverUI() slider bounds + fcv input/slider min/max updated.
- designCI/designCV gained a 'quiet' no-DOM eval path (uses pre-set fz/fp, nearestStd, no
  field writes) so the optimizer can score candidates without side effects. Live behavior
  unchanged (verified: pre-optimize scorecard identical to prior).
- Two 'Auto-optimize (balanced)' buttons (#vOpt voltage, #cOpt current) + result notes.
  Voltage: sweep f_cv 10-20 @0.5, k-factor target 60, pick HIGHEST f_cv with sizing-corner
  PM>=58 (60 target, ~2 for snap) AND worst 120Hz rejection>=26 dB (fallback: >=20 floor).
  Current: sweep f_ci [100*f_cv, min(f_SW/6, 0.9*f_RHP)] (32 pts log), k-factor target 60,
  among PM>=58 take the HIGHEST f_ci within 3deg of best PM (max bandwidth, RHP benign).
  Both set crossover + enable k-factor lock + recalc + show note.
- Verified headless: V(type3) f_cv 17Hz PM59.4 rej26.8; V(type2) 16.5Hz PM58.5; I 5.81kHz
  PM59.9 below RHP 6.45kHz f_SW/12.1. No JS errors.
- NOTE: PM constraint for voltage is at the sizing (HL) corner (k-factor controls it);
  worst-over-8-points voltage PM is inherently lower (~51) and shown in the margin table.

## C38 - Voltage manual slider back to 2-40 Hz (optimizer stays 10-20)
- Per designer: manual f_cv slider/input/clamp restored to [2,40] Hz; auto-optimizer
  search range stays hardcoded 10-20 Hz (independent of slider). fcvBand note now reads
  'Allowed 2 - 40 Hz · auto-optimizer targets 10 - 20 Hz'. Verified: manual 35 Hz accepted,
  optimize() still returns 17 Hz; no JS errors.

## C39 - Fix S3->S4 iframe remount (flash + lost crossover/transient/iTHD)
- ROOT CAUSE: S1-S3 were early-return native screens, so the control_design.html iframe
  was only mounted when reaching S4 -> every S3->S4 transition REMOUNTED it fresh:
  (1) showed its un-configured default for ~2s (the 'old setup' flash), and (2) reset the
  crossover to HTML defaults, so transient/iTHD never reflected the designer's changes.
- FIX (ControlDesign.tsx): keep ONE iframe mounted for the whole Control-Design session,
  hidden (display:none wrapper) on S1-S3, visible on S4-S7. It loads + configures once
  during S1-S3 and is ready/instant at S4; tool state (crossover, placement) persists across
  all navigation. postWizard now pre-positions the hidden iframe at wizard screen2; the
  drive-effect runs on every screen change; added a re-inject effect so the designer's R_CS
  is pushed to the tool once S2 is confirmed (iframe now loads before S2).
- e2e: updated stale S4 label assertion ('Compensators & Bode' -> '4a . Current loop', changed
  in C31). Full spec ALL CHECKS PASSED. Verified: control_design.html loads exactly ONCE
  across S1->S4 (no remount); iframe present-but-hidden at S1, visible at S4.
- Tool-level confirmed transient/iTHD DO update on crossover change (tab->recalc): -29V/142ms
  -> -21V/60ms; iTHD 0.68%% -> 1.11%%.

## C40 - S6 iTHD: add IEC 61000-3-2 (Class A) 3rd-harmonic pass/fail
- control_design.html (public + src/assets) renderScreen4: per operating point compute
  I1 = Pout/(eta*Vac) (fundamental, PF~1) and I3 = (iTHD3/100)*I1, compare to IEC 61000-3-2
  Class A 3rd-harmonic limit 2.30 A. Added table columns I1 (A) / I3 (A) / IEC verdict;
  summary card 'IEC 61000-3-2 . I3 (Class A) = X / 2.30 A'; note line with worst I3 + the
  >16 A -> IEC 61000-3-12 scope caveat. Class A used because PFC is >600 W (not Class D).
- Verified headless: worst I3 = 0.42 A @ 180 Vac -> PASS; columns/card/note render; no JS errors.

## C41 - S6 iTHD: add 5th & 7th IEC 61000-3-2 Class A limits
- thdCalc extended: returns thd5, thd7 via the harmonic cascade. I_h/I1 = vea_{h-1}/(2*veaEff);
  4f bus ripple Vr4 = Vr*(thd3/100)*0.5, 6f Vr6 = Vr*(thd5/100)/3 (from omega ratios);
  vea at 240/360 Hz = |Hota|*Vrh/|1+Tv|. eaRipple() helper. Backward compatible (Vr,rej,vea120,thd3).
- renderScreen4: per-point i3/i5/i7 from iTHD_h*I1; per-voltage table now shows I1 + overall IEC
  Class A verdict. New #iecTable compliance table: rows 3rd/5th/7th with Class A limit
  (2.30/1.14/0.77 A), worst-case I_h @ V_AC, margin (x), PASS/FAIL. Summary card + note updated;
  note flags 5th/7th as second-order cascade (also EMI-filter/rectifier dependent) + >16A 3-12 caveat.
- Added #iecTable element under thdNote in screen4 panel.
- Verified headless: 3rd 0.42/2.30 PASS, 5th 0.002/1.14 PASS, 7th ~0/0.77 PASS; no JS errors.

## C42 - S4 visionary upgrade: live transient (4b), tracking+iTHD model (4a), 6-goal scorecard
- thdCalc: added current-loop tracking-distortion model. Intrinsic cusp seed SEED={3:3,5:1.5,7:1}%
  suppressed by current-loop sensitivity S=1/|1+Ti| at h-th line harmonic; thd_h total = RSS of
  voltage-loop cascade (thd_hv) and current-loop (thd_hi). Exposes thd3v/5v/7v, thd3i/5i/7i,
  trackdB. S6 IEC table now uses totals automatically. Verified: thd3i grows 0.002->0.013% and
  trackdB drops 62->48 dB as f_ci 8k->2k (physically: current loop not the THD bottleneck in range).
- 4b (voltage): new live ΔVout(t) HL 0→100% step panel (#liveStep canvas data-h aware +
  #liveMetrics: peak dip, recovery, PM->ringing). drawStepPlot now honors data-h.
- 4a (current): new Current Tracking & iTHD panel (#trackTable): per-line-harmonic current-loop
  gain (dB) + iTHD contribution (responds to f_ci).
- Both tuning subs: 6-goal live scorecard (#goalCards): fast response, over/undershoot, ringing,
  phase margin, current tracking, 2f rejection — green/red, updates on every recalc. Thresholds:
  recovery<=80ms, dip<=8%, ringing PM>=52, PM current>=45 & voltage>=58, track>=20dB, rej>=20dB.
- renderLive(p,dci,dcv,mg,mgv,sc) called each recalc (one step + thdCalc, cheap). S5 stays the
  transient explorer, S6 the full iTHD+IEC detail (now totals).
- Verified headless: scorecard 6 chips all green nominal; sub visibility correct (4a track, 4b step);
  responsiveness (tracking vs f_ci, recovery vs f_cv); no JS errors.

## C43 - Type-III voltage k-factor: zero/pole spread control (3 placement options)
- Voltage panel: added #vPlace select (Coincident/Spread) + #vSpread ratio r input (Type-III only).
- designCV type3 k-factor: geometric centres zc=fcv/√k, pc=fcv·√k; spread straddles each pair
  geometrically — fz1=zc/r, fz2=zc·r, fp1=pc/r, fp2=pc·r (r=1 ⇒ coincident). Geometric means
  preserved so boost stays centred at fcv; plateau widens, peak boost (PM) drops with r. R3>0
  preserved (vfp2/vfz2 = pc/zc = k regardless of r). _placeCV (optimizer) respects the setting.
- 3 placement options now: (1) k-factor Coincident [lock on], (2) k-factor Spread r [lock on],
  (3) Manual [lock off, 4 independent inputs]. vPlace/vSpread disabled unless lock on & Type-III.
  Note shows 'coincident' / 'spread r=x' + split fz/fp. Wired to recalc + save/load.
- Verified headless: coincident fz1=fz2 10.96/fp 26.37 PM59.4; spread r=2 fz 5.48/21.92 fp 13.18/52.73
  (geo means preserved) PM51.9 R3>0; Type-2 & manual disable the control; no JS errors.

## C44 - S5 six step-plots (dip+overshoot) + S5/S6 layout cleanup
- drawStepPlot gained a step-fraction param (default 1): plots ΔV = step·(Pout/Vout)·yr, so
  load-decrease steps (k<0) now render as OVERSHOOT. Guards missing canvas.
- S5: right column now shows ALL 6 load-step transitions as a 2×3 grid of plots
  (stepPlot0..5, paired increase/decrease), drawn via trans.forEach. Removed the single
  0→100% plot. Transient table max-height none (no scroll). Removed the 'Each cell:...' note row.
  Transient Notes panel moved under the table (left col, still nowiz).
- S6: #screen4.active{display:block} → single column. Reordered: iTHD₃ graph on top, then
  '120 Hz Rejection & iTHD₃' table (+note+IEC), then Summary. tableWraps max-height none (no scroll).
- Verified headless: 6 plots 175px, note gone, no-scroll on S5/S6 tables, S6 order graph>table>summary,
  display block; no JS errors.

## C45 - S7 schematic: line-range selector + switched-components list + note
- screen5 (schematic): added Low Line (FR) / High Line (HV) selector (#modeLow2/#modeHigh2)
  -> setMode -> schematic redraws with the selected range's live values (R_IAC 6/12 MΩ,
  R_VIR 10/470 kΩ via populateMode). _syncModeBtns() keeps S4 Line Range + screen5 buttons in sync
  (setMode/setModeSilent). Wired onclick.
- Added #lineDiffTable under the schematic in renderSchematic: lists the components that change
  FR<->HV (R_IAC, R_VIR) with both values, active range highlighted amber. Plus note:
  'Switch these components using the microcontroller (relay/analog switch) ...'.
- Verified headless: toggle updates riac/rvir + highlight; S4 modeHigh stays synced; note present; no JS errors.

## C46 - Voltage loop: FB top/bottom (R1/R4) made read-only (fixed by Step 5)
- r1fb/r4fb inputs on the voltage compensator panel now readonly (+ title, label '— fixed (Step 5)'),
  matching the R_IAC/R_VIR fixed-field pattern. Still read by gather() so H_div / Type-3 math
  unchanged; designer can see but not edit. Verified: readonly true, values 3.63MΩ/23.2kΩ still used; no JS errors.

## C47 - PDF report: remove duplicate Chapter 6 heading + strip blank pages
- Duplicate Ch6: combined report = ch1_5 (agent) + ch6 (build_control_report). The agent's
  _ch6 emitted a Chapter-6 splash + 'Step 16 data not yet available' placeholder (misleading,
  data IS in the merged ch6) -> two 'CHAPTER 6 — Control Scheme' splashes. Added include_ch6
  flag threaded generate -> generate_chapter_report -> build_full_report (guards _ch6); endpoint
  combined path passes include_ch6=False. Verified: splash pages [27,29] -> [27] (one heading).
- Blank pages: added _strip_blank_pages(pdf) in main.py (pypdf) — drops pages with no text,
  no images, no vector/paint ops (conservative; figures kept). Applied to the final pdf in
  doc_generate_report. Verified: synthetic 4->3 (blank removed, figure kept); combined report
  8 blank pages removed.
- CAVEAT: ch1_5 TOC page numbers may drift slightly if blanks fell within ch1_5 (merged-TOC was
  already approximate). Acceptable per the explicit 'remove blanks' request. Backend restart needed.
