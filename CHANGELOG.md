## v2.4.0 — 2026-06-04  (GUI sessions 1–33)

### Added — Step 16: PFC Control Loop Design

**Backend:**
- `backend/app/mode_b/step16_control_design.py` (new): Python port of FAN9672 JS
  transfer functions — `_Gid()`, `_Gvp()`, `_Gmi_T2()`, `_Hota_T2()`, `_sweep()`,
  `_margins()`, `design_control_loops()`. Returns Bode sweeps, stability margins,
  9-point scorecard, compensator BOM.
- `backend/app/mode_b/generate_step16.py` (new): PDF sections 16.1–16.5
  (plant frequencies, current-loop Bode, voltage-loop Bode, stability scorecard,
  control BOM). NVGREEN=#76B900 accent.
- `backend/app/mode_b/generate_combined_report.py`: `step16_params` arg added;
  merges Step 16 pages; metadata title updated to "Steps 1–16".
- `backend/app/main.py`: `_Step15ReportReq.step16_params: Optional[Dict]`;
  report filename `Steps1_15.pdf` / `Steps1_16.pdf` based on presence.

**Frontend:**
- `frontend/src/components/ControlDesign.tsx` (new): loads
  `/control_design.html` via `src=` (NOT srcDoc — avoids SyntaxError + sandbox
  escape warning); injects Python plant params via postMessage with 2-second
  init delay; "Generate & Download Report (Steps 1–16)" button.
- `frontend/public/control_design.html` (new): FAN9672 JS tool with all
  hardcoded values parameterised; `window.setPythonValues()` + postMessage bridge.
- `frontend/src/App.tsx`: `step16` added to Step type; `approvedCapacitorDesign`
  state; `handleStep15Approve`; `<ControlDesign>` rendered at step16.
- `frontend/src/components/Stepper.tsx`: `ChipIcon` SVG (NVIDIA-style, green
  #76b900); Step 16 uses chip icon.
- `frontend/src/components/Step15Wizard.tsx`: `onApprove` prop added.
- `frontend/src/components/Step15Capacitor.tsx`: button → "Approve & Go to
  Control Design".
- `frontend/src/api/client.ts`: `step15GenerateReport` accepts optional
  `step16_params?: object | null`.

**Architecture note — srcDoc→public/ migration:**
- 2200-line HTML with em dashes in JS strings caused `SyntaxError` at line 1999
  when embedded as srcDoc attribute. Bundle shrank 508 KB → 342 KB.
- `allow-scripts + allow-same-origin` sandbox combo generates browser security
  warning; fix: removed `allow-same-origin`, added postMessage bridge instead.
- `control_design.html` lives in TWO places: `frontend/src/assets/` (working
  edit copy) and `frontend/public/` (live served). Keep in sync manually.

---

### Added — Review Page (JS Studio Integration)

- `frontend/src/assets/review_magnetics.html`: JS studio embedded in srcDoc
  iframe; `window.cfg/currentMap/renderAll/crestCurrent` exposed at end of IIFE
  so inject script can override them. Ring radius `R=(cfg.coreR_mm||15.55)*SC`.
- `frontend/src/components/ReviewMagnetics.tsx`: 240px sidebar; fixed params
  hidden; overrides `window.retention` with Python DB k(H); overrides Steinmetz
  `a_effective` from `loss_table_100C`; postMessage bridge used.

---

### Added — Steps 13-14 Extended Waveform Sections

- `backend/app/mode_b/generate_steps13_14.py`:
  - `_sec_14_6_extended_waveforms()`: H(t), B(t), Pcu(t), Ptotal(t) plots at 90 Vac.
  - `_sec_14_7_voltage_sweep_uncertainty()`: loss vs Vin ±5–20% uncertainty band.
  - `_sec_14_8_design_review()`: audit checklist GREEN/RED pass/fail cells + narrative.
  - `_resolve_params` extended: `Le_single_mm`, `Rac_Rdc`, `FFcu_design`, `Ku`,
    `sat_margin_pct`, `dT_rise_C`, `dT_budget_C`, `P_unc_lo_W`, `P_unc_hi_W`,
    `passed`, `fail_reasons`, `Pcu_100C_W`, `Ptotal_100C_W`.

---

### Fixed — Window Fill Factor Bug (Critical)

**Root cause:** `FFcu = N × Cu_area / Wa_total_mm2` where `Wa_total = Wa_single ×
stacks`. Stacking toroids does NOT add bore area — each core has its OWN bore.

**Fixes in `step7_magnetic_calc.py`:**
- FFcu denominator: `Wa_total_mm2` → `Wa_single_mm2`.
- Ku (powder): `N × n_parallel × (π/4 × OD²) / Wa_single_mm2` (insulated bundle).
- Pass/fail gate: `FFcu > FFcu_limit` (bare copper) AND `Ku > 0.75` (insulated).

**Impact:** 3-stack designs with small-bore cores that were previously 2–3× too
low in fill now correctly fail. Height default changed 44.45mm → 9999 to avoid
filtering valid large-bore candidates.

---

### Fixed — L_full_load Always Returning L_target

`enrichResult()` in `Step7Wizard.tsx`: replaced `kreq_nom × L0_nom_uH` (always
equals `L_target` by definition) with `L_vs_Vin_table[90].L_full_nom_uH` (actual
DB k_bias × L0). L variation rows now show `L_full@90Vac`, `L_full@180Vac` etc.
in amber (below target) / green (above target).

---

### Fixed — Report Download Race Condition

`DonePanel.tsx`, `Step7Wizard.tsx`, `Step15Capacitor.tsx`: added
`document.body.appendChild(a)` before `a.click()` and `removeChild(a)` after.
`URL.revokeObjectURL` deferred to `setTimeout(..., 150)`. Added `rptError` state
in Step7 and Step15 components for inline failure display.

---

### Fixed — Step 15 Report Missing Sections 15.4–15.10

Root cause: `handleReport` only passed sizing data; `verified` and `thermal` were
never computed. Fix: frontend now includes `selected_cap` block in request; backend
calls `verify_configuration()` and `calculate_thermal_table()` internally.

---

### Fixed — Thermal Model Mismatch (Python Rth vs JS SA Power-Law)

- Old Python: `ΔT = P × Rth` (K/W convection model).
- JS V5.1: `ΔT = (P×1000/SA_cm²)^0.833` (SA power-law).
- Fix in `step7_magnetic_calc.py`: toroids use `_thermal_dT_SA()` with residual
  bore hole geometry. Ferrite ETD still uses Rth.

---

### Fixed — MLT Formula Updated to Match JS V5.1

`_compute_MLT(core, stacks)` in `step7_magnetic_calc.py`:
Old: `π × Dmean`. New: `2 × (coreW + HT × stacks) + 3.8` mm.
Step 13.7.1 report shows updated formula.

---

### Changed — UI / Layout

- `Step7Wizard.tsx`:
  - FFcu slider max 50% → 70%; new zone "Challenging — Special process needed".
  - Candidate list: `AL=XXXnH/T²` added to metric line.
  - Result cards: AL rows (highlighted accent blue); three-temp loss table (25°C,
    80°C, 100°C); L variation per-Vin labels.
  - HEIGHT_PRESETS reordered (No limit first); `maxH` default 44.45 → 9999.
- `IntakeForm.tsx`: defaults changed — Vout 394 V, Pout_hi 3600 W, 47-63 Hz
  universal frequency, SEMI F47 required.
- App-wide: maxWidth 1020 → 1560 px; Step7 result page two-panel layout.

---

### Changed — Report Format (A4 / Helvetica)

`generate_report.py`: page size Letter → A4; DejaVuSerif → Helvetica; body
10.5 pt → 9.5 pt; margins 1" → 20 mm; navy header band added; `mkt()` auto-scales
columns to 170 mm; image widths updated; Step 10→11 explicit PageBreak.

---

## Key File Locations (current)

| Area | File |
|---|---|
| Magnetic sizing engine | `backend/app/mode_b/step7_magnetic_calc.py` |
| Steps 1–12 PDF | `backend/app/mode_b/generate_report.py` |
| Steps 13–14 PDF | `backend/app/mode_b/generate_steps13_14.py` |
| Step 15 PDF | `backend/app/mode_b/generate_step15.py` |
| Step 16 calculation | `backend/app/mode_b/step16_control_design.py` |
| Step 16 PDF | `backend/app/mode_b/generate_step16.py` |
| Report merger | `backend/app/mode_b/generate_combined_report.py` |
| Backend endpoints | `backend/app/main.py` |
| Review page JS studio | `frontend/src/assets/review_magnetics.html` |
| Control design HTML (live) | `frontend/public/control_design.html` |
| Control design HTML (edit copy) | `frontend/src/assets/control_design.html` |
| React routing | `frontend/src/App.tsx` |
| Step 7 Wizard UI | `frontend/src/components/Step7Wizard.tsx` |
| Review page component | `frontend/src/components/ReviewMagnetics.tsx` |
| Control design component | `frontend/src/components/ControlDesign.tsx` |
| Step 15 capacitor UI | `frontend/src/components/Step15Capacitor.tsx` |
| Intake form | `frontend/src/components/IntakeForm.tsx` |
| Stepper nav | `frontend/src/components/Stepper.tsx` |
| API client | `frontend/src/api/client.ts` |

---

## Environment Startup

```powershell
# Backend (from project root)
backend\venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000

# Frontend
cd frontend
npm run dev    # dev server at http://localhost:5173
npm run build  # production build to dist/
```

Required package (not in original requirements.txt):
```powershell
backend\venv\Scripts\pip.exe install python-multipart
```

---

## v2.2.0 — 2025-05-21

### Added — MagneticsDB Agent (Option C)
- `app/magnetics/db.py` (626L): MagneticsDB guardian — single owner of all magnetic data
- `app/magnetics/schema.py` (365L): JSON schema, field validators, blank templates  
- `app/magnetics/extractor.py` (365L): PDF extraction via Claude API with confidence scoring
- `app/magnetics/tools/validate.py` (67L): CLI validator
- `app/magnetics/tests/test_magnetics_db.py` (316L): 39 dedicated DB tests
- 12 new API endpoints: /magnetics/status, /magnetics/list, /magnetics/rank,
  /magnetics/add-custom, /magnetics/commit-pending, /magnetics/extract-pdf,
  /magnetics/reload, /magnetics/validate, /magnetics/template
- Three data update pathways: edit JSON → reload, PDF upload → Claude extract → review → commit,
  manual entry → validate → commit
- Hot reload: POST /magnetics/reload — no server restart needed after data changes

### Added — Step 7 and Step 8 wired
- POST /mode-b/step7/material-comparison: Ferrite vs Powder comparison table
- POST /mode-b/step7/suppliers: supplier options per material type
- POST /mode-b/step7/grade-options: agent-ranked grade list for HITL Gate 3
- POST /mode-b/step7/wire-options: top 3 wire specs (Litz/Solid/TIW) for HITL Gate 3.5
- POST /mode-b/step7/run-sizing: full Step 13 sizing engine → Top 5 candidates
- POST /mode-b/step8/time-domain: full Step 14 Pcore(t) time-domain analysis
- Registry: Steps 7 and 8 updated to DONE with all metadata
- DonePanel.tsx: Steps 7 and 8 marked as implemented
- client.ts: 6 new API call exports

### Fixed — Step 7 sizing engine bugs
- I_phi_avg_crest: was dividing Ipk_A by N_phases again (already per-phase)
- Worst-case DC bias: now uses max(Iavg) across all 9 op-points (180Vac is worst, not 90Vac)
- Ku vs FFcu: powder toroids now use FFcu (reference method, bare copper / window area)
  instead of physical bundle geometry — matches reference Step 13.6.2 exactly
- Toroid thermal model: winding outer surface area used (much larger than bare core geometry)
- Powder toroid creepage: no longer fails Medical check (TIW wire handles IEC 60601-1 instead)

### Tests: 99 passing (37 original + 23 DataLoader/Step8 + 39 MagneticsDB)

# CHANGELOG — PFC AI Agent

All notable changes are documented here.
Format: `## vMAJOR.MINOR.PATCH — YYYY-MM-DD`
Sections: Added · Changed · Fixed · Removed

---

## v2.0.0 — 2025-05-19 (current)

### Added
**Mode A frontend (all 5 HITL gates):**
- Gate 1 `IntakeForm`: 27 fields, 4 sections, real-time validation, Medical leakage auto-lock at 500 µA
- Gate 2 `TopologyHITL`: 6-dimension mode scoring + 6 topology candidates with full score bars + **Medical advisory card** when `app_class=Medical` (TTP leakage risk flagged)
- Gate 3 `ControllerHITL`: Analog/Digital cards with agent reasoning + **Analog IC mismatch advisory** when `isInterleaved=true && ctrlMode=analog` (UC3854 → UCC28070A/NCP1631/FAN9612)
- Gate 4 `ChannelSelect`: Phase count 2/3/4 with **corrected L formula** (L same for all N; Ipk decreases with N) + analog compat flags per phase count
- Gate 5 `MiniIntakeGate`: **5 fsw preset buttons** (50/70/100/140/200 kHz ★) + **4-zone crest ripple guide** (Medical note in low-ripple zone) + live estimates using correct Python formula + CCM variable-freq lockout
- `DonePanel`: 5-gate confirmation trail, Medical strip with IC update note, 25-step Mode B sequence with implementation status

**Mode B backend:**
- Steps 1–12: Complete PDF report (30 pages, 3.7 MB, DejaVu Serif, STIX equations)
- Step 6 `magnetic_design`: Core selection (ETD49/ETD59/E65/KoolMu77907), Steinmetz losses, Litz wire sizing (correct skin depth δ=0.249 mm at 70 kHz), thermal ΔT estimate — selects **ETD59/3C95** (N=39, gap=2.93 mm, Ku=0.46, ΔT=31°C vs 60°C Medical budget)
- API endpoint `/mode-b/step6-magnetic-design`
- Step registry `registry.py`: Single source of truth for all 25 steps
- 37-test regression suite covering every implemented step

**Infrastructure:**
- `run.sh`: One-shot local startup (installs deps + starts both servers)
- `docker-compose.yml`: Docker-based deployment
- `DEVELOPMENT_GUIDE.md`: Step-by-step guide for adding future steps
- `CHANGELOG.md`: This file

### Fixed
- **Critical L formula bug (v1 → v2)**: Channel Select and Mini-intake were using `dIL = crest × IL_ph × 2` (per-phase ratio interpretation) — gave 959 µH instead of 238 µH at r=0.095. Corrected to: `dIin = r × Iin_pk`, `dIL = dIin / K(D)`, `L = Vin_pk × D / (fsw × dIL)`. This matches the Python backend exactly. Protected by `TestCorrectLFormula::test_L_calc_at_90vac_r0095_fsw70k`.
- **L independence of N**: Phase count N does not change the inductance formula. Only per-phase Ipk = Iin_pk/N + dIL/2 changes. Channel Select now shows same L (238 µH) for 2/3/4 phases.
- **Skin depth formula**: Mode B magnetic design had `delta = 66e-3 / sqrt(fsw/1e3)` giving 7.89 mm instead of 0.249 mm. Corrected to `delta = sqrt(rho/(pi*f*mu0))`. Led to 12,878 Litz strands instead of correct 42.
- **ui.tsx Badge/ScoreBar API**: Updated to accept children + named colours (blue/green/amber/red) and `value` prop (0-1 normalised) alongside legacy `label` and `val` props.

### Removed
- Nothing (per policy: steps are never removed, only status changed)

---

## v1.0.0 — 2025-05-15 (initial)

### Added
- Mode A 5-gate HITL frontend (React/TypeScript/Vite)
- Backend FastAPI + LangGraph workflow
- Topology scoring engine (`topology_selector.py`)
- Controller selection agent
- Mode B Steps 1–12 PDF report engine (ReportLab)
- DejaVu Serif fonts bundled
- docker-compose for deployment

---

## How to update this file when adding a step

```markdown
## v2.1.0 — YYYY-MM-DD

### Added
- Mode B Step 7: `magnetic_design_v2_advisory`
  - Paired ETD59 cores in parallel; amorphous material option
  - API: POST /mode-b/step7-magnetic-v2
  - Files: app/mode_b/step7_magnetic_v2.py, app/main.py
  - Regression: TestStep7MagneticV2 (2 new tests, total 39 passing)
- DonePanel: Step 7 marked as implemented
```
