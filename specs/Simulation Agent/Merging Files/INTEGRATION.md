# PFC Inductor Magnetics — Integration Guide

Merge-readiness notes for folding the magnetics component into the main pipeline.
The component is **two halves that share one package contract**: a headless Python
compute engine and a browser display module. Feeding both the *same* package object
is what guarantees they never disagree.

---

## 1. File manifest

**Ship / merge**
| File | Role | Merges into |
|---|---|---|
| `pfc_inductor_engine.py` | Headless compute backend (`validate` / `compute` / `compute_from_json`). Material-agnostic; holds only physics/unit constants. | Python pipeline (analytic-screen + FEA-gate agents) |
| `test_pfc_inductor_engine.py` | Regression net (17 tests). Dev/CI only, not runtime. | CI |
| `example_package_analytic.json` | All-analytic package (Tier-1 stand-ins). Validation fixture + browser preview. | Fixtures |
| `example_package_fea.json` | Same design + solved FEA `fields` (Tier-2). Shows override path. | Fixtures |
| `pfc_sim_agent_v14.html` | Browser Studio / Simulation-Agent display (`window.SimAgentField`): measured tier, P_core badge, **WebGL 3D (lit, depth-buffered, ¼-cutaway field view) with automatic canvas-2D fallback**. Self-contained, zero dependencies. | Frontend asset (served, not imported into Python) |
| `adapter_template.py` | Skeleton: DB record + designer selection → package (the ONLY schema-mapping point). | Bigger script (fill in lookups) |
| `DATA_DICTIONARY.md` | Every field: unit, basis (single-core vs stack), source, failure mode. | Docs for whoever fills the adapter |
| `PREMERGE_CHECKLIST.md` | Phased verification protocol, run at pre-merge time in the merge environment. | Merge process |
| `premerge_check.py` | Portable checker automating Phases 0/1/4 (+`--package` for Phase 2). | Merge process |

**Do NOT ship**
- `powder_core_inductor.py` — **retired**; raises `ImportError` on import. It carried an
  embedded material library (violates no-hard-coded-data). Delete once nothing references it.
- `pfc_sim_agent_v13.html` / `v12.html` — kept only as known-good ROLLBACKs for v14; `v11` and older, plus `pfc_live_sim_demo_*` — superseded, delete.

---

## 2. The contract (one package, both sides)

`eng.schema()` returns the authoritative shape. Top level:

```
{ schemaVersion, meta?, model{...}, operating{points:[...]}?, acceptance{...}?, fields{...}? }
```

- **`model`** — the finalized design from upstream: `design, environment, winding, geometry,
  material, copper, cooling, maps?`. Every material/geometry/wire constant lives here.
- **`operating.points`** `[{Vin,Pout,eta,PF}]` — the spec corners. If omitted, derived from
  `model.maps.etaByVin + design.Prated + spec*Pct`.
- **`acceptance`** — pass/fail limits (`L_target_uH, sat_margin_min|Bmax_T, Ku_max, J_max,
  dT_max_K`). **Upstream-only**: any limit you omit is reported as "no upstream limit", never
  invented. Omit the block entirely → verdict `NO LIMITS`.
- **`fields`** — *optional* solved ROM (`inductance, windingAC, thermal, flux`). When present it
  **overrides** the analytic model for that quantity and stamps provenance. Absent → analytic.

The engine adds **zero** design data. If a required field is missing it errors; it never
substitutes a default for material/geometry/wire.

---

## 3. Python integration

```python
import pfc_inductor_engine as eng

# safe agent-to-agent entry: returns JSON, never throws on bad input
out = eng.compute_from_json(package_json_str)        # -> '{"ok":false,"errors":[...]}' if invalid

# or, with exceptions:
vr = eng.validate(package)                           # ValidationResult(ok, errors, warnings)
if not vr.ok:
    handle(vr.errors)                                # hard stop
log(vr.warnings)                                     # proceed, but record
result = eng.compute(package)                        # raises eng.SpecError on hard errors
```

`result` includes: `meta, statics, points, worst, asserts, verdict, provenance, tier, validation`.

**Error vs warning is a real distinction, honor it:**
- **errors** → no result is possible (missing constant, `ID ≥ OD`, window overflow, non-physical).
- **warnings** → result is valid but flagged (measured-R disagrees with geometry >2×, `fsw`
  outside a supplied `windingAC` table). Log them; don't drop them.

CLI: `python pfc_inductor_engine.py package.json` (or pipe JSON on stdin).

---

## 4. Browser integration

`SimAgentField` is a frontend asset, not a Python import. It boots **only** if a `#fieldC`
canvas exists, so headless import is side-effect-free.

Inject the package before the page boots (precedence high→low):
```js
window.__MAG_FIELD_PACKAGE__ = pkg;   // full package (preferred)
window.__MAG_INPUT__ = model;         // model-only (analytic)
// else falls back to EXAMPLE_PACKAGE (preview; strip in production)
```
Headless JS eval (no rendering): `SimAgentField.evaluateHeadless(pkg, {vin, loadPct, phase, warmMin})`
→ `{result, provenance, validation, windowGeom, worstCase, acceptance}`.

Both sides emit the same provenance/tier vocabulary, so a quantity shown `fea · T2` in the
browser is `fea`/`T2` in the engine result.

---

## 5. Provenance & tiers (and what's still a stand-in)

`provenance ∈ {input, computed, analytic, fea, measured}` → `tier ∈ {T0, T1, T2, T3}`
(`input`=T0, `analytic`/`computed`=T1, `fea`=T2, `measured`=T3).

**Honest status of the physics:** three quantities are **Tier-1 analytic stand-ins** until real
data is supplied through `fields`:
- **R_ac** — `1.15` skin/proximity heuristic (Zhao porosity model parked, not adopted).
- **thermal ΔT** — natural-convection correlation.
- **biased L(H)** — catalog DC-bias curve.

These are first-order, not validated. Retire each by attaching solved data:
`fields.windingAC` (FEA eddy-current → R_ac, T2), `fields.thermal` (CFD nodes → ΔT, T2),
`fields.inductance` (FEA magnetostatic → L(H), T2), and — once the **real-world tier** lands —
`material.measured.coreLoss` (refit Steinmetz or ≥3 raw P(B,f) bench points — fitted in-engine) and
`material.measured.inductance` (L vs H_Oe or vs bias current I_A) — **now implemented on both sides**
(bench → T3, retires the ±29 % core-loss band). Precedence per quantity: **measured > fea > analytic**.
Measured data contradicting the catalog by a suspicious margin raises a **warning, never a silent
accept**; the catalog transcription anchor is dropped only when a measured fit replaces it.
`example_package_fea.json` shows the T2 override; compare it to the analytic one.

---

## 6. Parity rules (engine ↔ browser quantity definitions)

The two halves were cross-validated on the shipped fixtures; these definitions are now
contractual. If you change one side, change the other and re-run the parity check.

- **Saturation basis = mean-path B.** `acceptance.Bmax_T` / `sat_margin_min` are checked
  against the mean-path peak B (the basis of the hand verification). The crowded
  inner-radius value is reported by both sides (`worst.Binner` / `B_inner(crowded)` row)
  and is checked **only** if upstream supplies `acceptance.Binner_max_T`. Same package →
  same verdict on both sides (REJECT cross-check included in validation).
- **L-guarantee derating is provenance-aware.** Analytic L(H) is derated by `AL_tol`
  (catalog tolerance). A solved `fields.inductance` table is the *actual* L(H) and is
  **not** derated on either side.
- **Operating data is dual-representation.** The canonical package carries BOTH
  `operating.points` (engine: discrete spec corners) and `maps.etaByVin + design.Prated +
  spec*Pct` (browser: continuous Vin explorer), generated from the same source so they
  cannot disagree. A package missing the browser's current source yields verdict
  `INSUFFICIENT DATA` (never a spurious REJECT).
- **Residual known deltas (accepted, ~1 %):** L-guarantee differs slightly (engine
  evaluates at peak instantaneous bias on the worst corner; browser at crest bias of the
  envelope scan: e.g. 244 vs 246 µH), and J differs in the rounding of RMS basis
  (0.84 vs 0.83 A/mm²). Both are reporting differences, not model differences, and both
  sides remain conservative for the verdicts they gate.

## 7. CI gate & merge steps

- **Gate:** `pytest test_pfc_inductor_engine.py` green (25 tests, ~0.8 s, numpy only).
- Add one test that runs a *real production package* through `compute()` once you have one.

Merge checklist:
1. Agree the schema source-of-truth (adopt `eng.schema()`, or write a thin adapter to main's).
2. Build the package upstream (DB + designer selection). Engine adds no design data.
3. Call via `compute_from_json` (or `compute` + `try/except SpecError`); handle the error path.
4. Treat `validate()` as a gate; surface errors and warnings distinctly.
5. Wire FEA/measured results into `fields` with correct `provenance` (the override channel).
6. Feed the browser the **same** package object (`window.__MAG_FIELD_PACKAGE__`).
7. Namespace the module to your convention (import-safe: no side effects, numpy-only).
8. Delete the retired `powder_core_inductor.py` from the tree.

**Still open after this (not code-merge blockers, but flagged):** the real-world/measured tier
(core-loss & L(H) measured overrides + template + protocol doc), and visual confirmation of the
3D render (verified no-throw in all modes, but not eyeballed by an automated harness).
