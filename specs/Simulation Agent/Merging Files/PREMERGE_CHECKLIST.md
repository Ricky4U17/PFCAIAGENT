# Pre-Merge Verification Protocol

Run this **in the merge environment, at pre-merge time** — not before. Phases 0/1/4 are
automated by `premerge_check.py`; Phases 2/3/5 need your real DB record, designer numbers,
and the designer present. Do the phases in order; each has a hard pass criterion. Any FAIL
stops the merge until explained.

> One-command start: `python premerge_check.py`  (add `--package your_pkg.json` for Phase 2)

---

## Phase 0 — Environment (automated)
**Goal:** the merge environment can run the engine at all.
- Python ≥ 3.9; `import numpy` works; `import pfc_inductor_engine` works; `eng.schema()` returns.
- Note whether `pytest` exists (if not, the checker uses its built-in fallback runner).
- Note whether `node` exists (needed only for Phase 4 browser parity; SKIP is acceptable, record it).
**Pass:** engine imports and schema prints. **Fail:** fix environment before anything else.

## Phase 1 — Component self-test (automated)
**Goal:** the component is intact after copying into the merge tree.
- Full test suite green (25 tests).
- Both shipped fixtures compute: `example_package_analytic.json` → APPROVE, all-T1;
  `example_package_fea.json` → APPROVE, windingAC/inductance/thermal = fea/T2.
- Legacy guard: `import powder_core_inductor` must raise ImportError (retired stub),
  or the file is already deleted.
**Pass:** all green. **Fail:** files corrupted in transfer — re-copy, do not patch by hand.

## Phase 2 — Adapter validation (your real record required)
**Goal:** one *real* DB record + designer selection maps to a contract-clean package.
1. Fill in `adapter_template.py` lookups (units/basis per `DATA_DICTIONARY.md`).
2. Produce the package for the designer's actual finalized design.
3. `python premerge_check.py --package real_pkg.json`
**Pass:** zero validation errors; **every warning read aloud and explained** (warnings are
the mixing-trap detectors: measured-vs-geometry DCR, η·PF product, measured-vs-catalog).
**Fail:** fix the adapter (almost always units or single-vs-stack basis), never the engine.

## Phase 3 — Golden cross-check (designer's numbers required)
**Goal:** engine output matches the designer's independent hand numbers for that real design.
Compare, with agreed tolerance bands (suggested):
| Quantity | Band | Note |
|---|---|---|
| L0 nominal / L guarantee | ±2 % | exact math from AL·stacks·N² |
| DCR 25 °C | ±5 % (geometry) / ±2 % (measured) | basis check |
| Worst-case total loss | ±15 % | Tier-1 model band |
| B mean-path worst | ±5 % | |
| ΔT | ±30 % or FEA/CFD | weakest stand-in — expect T2 data here eventually |
**Pass:** within bands, or every deviation explained by model tier (record it).
**Fail:** stop; diagnose with the designer before merging.

## Phase 4 — Engine ↔ browser parity (automated if node present)
**Goal:** same package → same verdict on both sides.
- Both fixtures AND (if provided) the real package run through engine and
  `SimAgentField.evaluateHeadless`; verdicts must match; provenance must match.
**Pass:** verdict parity on every package tried. **Fail:** do not merge — a designer could
see APPROVE in the browser while the pipeline REJECTs.

## Phase 5 — Demo run (designer present)
**Goal:** end-to-end dry run of the actual workflow.
1. Bigger script builds the real package and calls `eng.compute_from_json(...)`.
2. Same package injected into the viewer: `window.__MAG_FIELD_PACKAGE__ = pkg` before boot.
3. Designer reviews: KPIs, acceptance panel (limits all from upstream), provenance/tier
   badges, cross-section/ring/3D views, L(t), DCM region, operating plane.
4. If bench data exists in the DB, include it (`material.measured`, `copper.measured`) and
   confirm badges flip to measured/T3.
**Pass:** designer signs off that numbers and display are usable and honest (stand-in
quantities visibly labeled T1). **Fail:** capture objections as issues; decide merge/hold.

## Phase 6 — Sign-off & rollback
- Record: date, environment, commit/copy hashes, Phase 2 warnings + explanations,
  Phase 3 deviation table, Phase 5 sign-off name.
- Commit: engine, tests, fixtures, adapter (filled), viewer v12, docs.
- Delete: `powder_core_inductor.py` stub, superseded viewer versions (≤ v11).
- Rollback: the component is self-contained — removing the files and the adapter call
  restores the prior state; no shared state, no DB writes.

---
### Known honest caveats to re-state at sign-off
- R_ac, thermal, analytic L(H) are Tier-1 stand-ins until `fields`/measured data arrives.
- Browser 3D view is geometric/to-scale (painter depth), validated no-throw, **visually
  confirm once in a real browser** during Phase 5.
- Residual engine↔browser reporting deltas ~1 % (documented in INTEGRATION.md §6).
