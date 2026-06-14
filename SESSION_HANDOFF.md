# PFC AI Design Agent — Documentation-Agent Work · Session Handoff

**Resume point for the report / documentation-agent improvement work.** Last updated 2026-06-14.
Detailed blow-by-blow is in `IMPLEMENTATION_LOG.md`; this file is the concise "start here".

## Where things stand
- Branch `master`. Latest relevant commits (newest first):
  - `4ef5660` §6.3 FAN9672 pin table + round-2 calc-detail corrections
  - `e9f2069` final read-through polish (Ch5 renumber, splashes)
  - `09b0c73` winding + thermal figures
  - `52948d7` Ch4+5 calc steps · `7f6a482` Ch3 calc steps
  - `3954c97` pass-1 corrections/formatting/root-cause bugs
  - `7fb8e3e` Table of Contents + missing Ch5/Ch6 sections
- The chapter-based report builds to **88 pages**; sample at project root
  `PFC_Report_VERIFY_Steps1_16.pdf` (gitignored pattern `PFC_Report_VERIFY_*.pdf`; the committed
  copy was force-added once).

## Key files (documentation agent)
- `backend/app/mode_b/doc_report_builder.py` — the chapter-based PDF builder (Ch1–6, TOC, figures).
  THIS is where almost all report edits happen.
- `backend/app/mode_b/documentation_agent.py` — orchestrator + `_assess_chapters` section lists.
- Data sources the report reads: `step7_magnetic_calc.py` (inductor), `step15_capacitor.py` +
  `step15_cap_db.py` (capacitor), `step16_control_design.py` (control), `sim_agent/
  pfc_inductor_engine.py` (Ch4.8 cross-check).
- Engine equation reference: `specs/Simulation Agent/Inductor Calculation Improvement FIles/
  PFC_Inductor_OurEngine_Equations_v11.pdf` (E1–E54, what the engine computes).

## How to regenerate + verify (headless)
Use a throwaway script in `backend/` driving the real endpoints via FastAPI TestClient:
1. POST `/mode-b/step7/run-sizing` (material_key `edge_60`, wire `magnet`) → top_5[0].result = approved_design (+ all_candidates).
2. `run_capacitor_design(state)` + a `selected_cap` dict → step15_result; `verify_configuration(...)` for C_total/ESR.
3. step16_params from approved_design L0_nom/DCR + cap C_total/ESR.
4. POST `/mode-b/documentation/generate-report` → PDF; render pages with PyMuPDF (`fitz`) at matrix(2,2).
Run with `PYTHONIOENCODING=utf-8 PYTHONUTF8=1 venv/Scripts/python.exe`.

## BUGS & GOTCHAS — history (read before editing the builder)
- **Silent legacy fallback (the big one):** `DocumentationAgent.generate()` wraps the chapter
  builder in try/except and falls back to the OLD generator on ANY exception. Symptom: report
  drops to ~58 pages, Ch6 headings vanish, and stale legacy text reappears (e.g. "via Mode A HITL
  gates"). ALWAYS verify the page count (~88–89) after edits. To surface the real traceback, call
  `build_full_report(state, approved_design=…, step15_result=…, step16_params=…)` DIRECTLY (not
  through the agent) in the verify harness — the agent hides the error.
- **matplotlib mathtext (equations are rendered images) — unsupported / tricky tokens that throw:**
  - `\sqrt2` → must be `\sqrt{2}` (brace the argument).
  - `\le` / `\ge` → unsupported; use `\leq` / `\geq`.
  - `\text{...}` is unreliable; avoid (e.g. don't write `core\text{-}loss` — use `core\ loss`).
  - `\left`/`\right`, `\dfrac`, `\mathrm`, `\Rightarrow`, `\Delta`, `\phi`, `\mu`, `\times`,
    `\sqrt{}`, `^{}`, `_{}` all WORK. When unsure, test via a direct builder call.
- **No unicode subscripts/Greek in ReportLab table cells or body Paragraphs** — use `<sub>`/`<sup>`
  HTML tags (CLAUDE.md rule #7). Unicode `f₀`-style chars render as tofu boxes in Helvetica.
  (Equation images via `_eq_img` are fine — those are matplotlib, not ReportLab.)
- `_eq_img` caps equation image width to CW so wide equations don't overflow the right margin.
- Global style (in `_S`): table cell text is centre-aligned; annotation body text is justified.
- **Windows console encoding:** run the harness with `PYTHONIOENCODING=utf-8 PYTHONUTF8=1` or
  prints of ★/µ/Ω/° throw `UnicodeEncodeError` (cp1252). Render PDFs with PyMuPDF (`fitz`).
- **Circular reference when building approved_design:** `top_5[0].result` IS the same object you
  then store under `approved_design["all_candidates"][0]` → JSON `Circular reference`. Use
  `copy.deepcopy` for both.
- **2-pass TOC:** the report uses `doc.multiBuild()` + `_ReportDoc.afterFlowable` + `_TOCMark`;
  section/sub headings are tagged on the Paragraph (accurate page #), chapters via a 0-size mark.

## ENGINE/DATA FIXES already applied (don't re-introduce)
- EDGE `Bsat` corrected 1.05→1.5 T across `data/magnetic_materials/magnetics_inc/edge_*.json`
  (1.05 was Kool-Mu's value). This also cleared a false saturation REJECT.
- Field engine `sim_agent/pfc_inductor_engine.py`: `skin_depth` assert no longer hard-fails a
  solid single-strand wire; `L_guarantee` aligned to step7's crest-average AL_min ≥ 85%·target
  (was instantaneous-peak ≥ 100%). These fixed the "6/6 in band but REJECT" verdict.
- Wire-diameter check (3.5.2) printed an inverted "< limit"; corrected + solid-wire explanation.
- Thermal figure (`_fig_thermal`) once rendered the surface HOTTER than the hotspot when
  `dT_hotspot_C < dT_rise_C` in the payload — now forces the interior to the hottest node.

## DONE (designer review "Improvments and Corrections.docx" — both rounds)
All 29 round-1 items + round-2 items (2.7.1, 4.4/4.5 iGSE 90+180, 4.7 core+copper+total, 5.3
ripple decomposition, 5.4 Rth/Tcore + 3-method lifetime) + §6.3 FAN9672 pin table. Root-cause
fixes: EDGE Bsat, field-engine REJECT-with-all-in-band (skin_depth + L_guarantee asserts), wire
diameter logic.

## PENDING (next session — requested 2026-06-14)
1. **Page 69 / Table 4.5:** expand the loss-method comparison to ALL 9 input voltages (currently
   90 Vac only). Method 1 peak-point core per Vin ≈ Pcore_peak·(Bac(Vin)/Bac(90))^2.1; Method 2
   iGSE + copper from `loss_table_100C`.
2. **Page 77 / Method 3 lifetime:** more detail for f_T, f_I, f_V — no shortcuts/approximations
   (show the full manufacturer-model derivation: I_eq with k_LF/k_HF, ΔTj, the f_T/f_I/f_V
   formulas with every constant substituted). Source: `step15_cap_db.calculate_lifetime` method3.
3. **Apply all 12 v11 quantities** (from the task-3 table). STATUS as of 2026-06-14: **10 of 12 DONE**.
   - DONE: #1 K_harm (4.4 copper eq+THEORY) · #2 Rac/Rdc Dowell-proximity (3.5.1 eq+note) ·
     #3 CCM/DCM boundary at design corner (4.2 note, dcm_fraction) · #5 inner-bore crowding B_inner
     9-pt (4.3 crowd eq + column) · #6 L_full,min@pk (4.2 eq+note) · #7 bore layers / turns-per-layer
     / residual clearance (3.5.6 note) · #8 loss uncertainty band +5–20% (4.7 eq+note) · #9 thermal
     convergence loop (4.7 THEORY) · #10 two-node core/winding split + hotspot (4.7 eq+THEORY) ·
     #11 composite ranking score (3.4.6 eq + candidate scores).
   - TODO (only the 2 figures left): **#4 per-θ flux waveforms** Bac,pk(θ)/Bdc(θ)/Bmax(θ) over the
     half cycle (E20) and **#12 Pcore(θ) waveform + double-hump at high line** (E38). Both need the
     per-θ series from `step7_magnetic_calc.build_view_contract(result, state)` (returns
     `waveform`/`waveforms_by_vin` arrays: t_ms, Bdc, Bac_pk, Bmax, Pcore, …). Build two matplotlib
     figures via the `_fig_img` helper and drop into §4.3 (flux) and §4.5 (core loss).
   - #3/#5/#6/#8 currently report at the design corner / via the 9-pt flux table; a per-Vin 9-row
     table for #3 DCM and #8 uncertainty could be added later if wanted.
