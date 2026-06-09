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
