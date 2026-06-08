# PFC AI Agent — Development Guide

## Principle: nothing gets lost

Every step is registered in `backend/app/mode_b/registry.py`.
Every step that was implemented has a regression test in `backend/tests/test_regression.py`.
Before any commit, run the test suite and confirm `37/37 passed` (plus your new tests).

```bash
cd backend && python -m pytest tests/test_regression.py -v
```

---

## Repository anatomy

```
pfc_ai_complete/
├── README.md                          ← user-facing run instructions
├── DEVELOPMENT_GUIDE.md               ← this file
├── CHANGELOG.md                       ← version history
├── run.sh                             ← one-shot local startup
├── docker-compose.yml
│
├── frontend/src/
│   ├── App.tsx                        ← 6-gate state machine
│   ├── api/client.ts                  ← all API calls
│   └── components/
│       ├── ui.tsx                     ← design system (Badge, Btn, Card, etc.)
│       ├── Stepper.tsx
│       ├── IntakeForm.tsx             ← Gate 1 (27 fields)
│       ├── TopologyHITL.tsx           ← Gate 2 + Medical advisory
│       ├── ControllerHITL.tsx         ← Gate 3 + analog IC advisory
│       ├── ChannelSelect.tsx          ← Gate 4 + corrected L formula
│       ├── MiniIntakeGate.tsx         ← Gate 5 + fsw presets + ripple zones
│       └── DonePanel.tsx             ← Done + 25-step sequence list
│
└── backend/
    ├── requirements.txt
    ├── app/
    │   ├── main.py                    ← ALL FastAPI endpoints
    │   ├── state.py                   ← ProjectState TypedDict
    │   ├── intake/
    │   │   └── topology_selector.py   ← Mode A scoring engine
    │   ├── agents/
    │   │   └── controller_selection_agent.py
    │   └── mode_b/
    │       ├── registry.py            ← SINGLE SOURCE OF TRUTH — 25 steps
    │       ├── calculations.py        ← K(D), step2–8 math, waveforms
    │       ├── generate_report.py     ← Steps 1–12 PDF (749 lines)
    │       └── magnetic_design.py     ← Step 6: core, wire, losses
    └── tests/
        └── test_regression.py         ← 37 tests covering every DONE step
```

---

## How to add a new Mode B step (example: Step 7)

### Checklist — complete in order, never skip

- [ ] 1. Update `registry.py` — change status to IN_PROGRESS
- [ ] 2. Write the calculation / advisory code
- [ ] 3. Add the API endpoint to `main.py`
- [ ] 4. Update `registry.py` again — change status to DONE, fill in all fields
- [ ] 5. Add regression tests to `test_regression.py`
- [ ] 6. Run full test suite — must be `N+new passed, 0 failed`
- [ ] 7. Update `CHANGELOG.md`
- [ ] 8. Update `DonePanel.tsx` step status badges

---

### Step 1 — Update registry.py (mark IN_PROGRESS)

```python
# In backend/app/mode_b/registry.py
7: dict(
    key              = "magnetic_design_v2_advisory",
    status           = "IN_PROGRESS",     # ← change from QUEUED
    ...
)
```

### Step 2 — Write the calculation code

Option A — add to `calculations.py` (pure numerical):
```python
# backend/app/mode_b/calculations.py

def step7_core_pairs(L_phi: float, IL_pk: float, ...) -> dict:
    """
    Step 7: Evaluate paired-core option (2× ETD59 in parallel).
    Returns: dict with N_cores, L_per_core, gap, combined losses.
    """
    ...
    return dict(n_cores=2, L_per_core=..., gap_mm=..., P_total=...)
```

Option B — new module for complex steps:
```python
# backend/app/mode_b/step7_magnetic_v2.py
"""Step 7: Advanced magnetic design advisory."""
def evaluate_paired_cores(...) -> dict: ...
def evaluate_amorphous_option(...) -> dict: ...
```

### Step 3 — Add API endpoint to main.py

```python
# backend/app/main.py — add after the /mode-b/step6-magnetic-design endpoint

@app.post("/mode-b/step7-magnetic-v2", tags=["mode-b"])
def step7_magnetic_v2(req: ReportReq):
    """Step 7: Advanced magnetic design options."""
    try:
        from app.mode_b.step7_magnetic_v2 import evaluate_paired_cores
        state = req.state
        # extract confirmed L, IL_pk, etc. from state
        tsi = state.get("topology_specific_inputs", {})
        result = evaluate_paired_cores(
            L_uH=tsi.get("confirmed_L_uH_sel", 240),
            ...
        )
        return {"status": "ok", "step": 7, "result": result}
    except Exception as e:
        log.exception("step7"); raise HTTPException(500, str(e))
```

### Step 4 — Complete the registry entry

```python
7: dict(
    key              = "magnetic_design_v2_advisory",
    status           = "DONE",                         # ← DONE
    outputs          = ["api_json:paired_core_option", "advisory_report"],
    api_route        = "/mode-b/step7-magnetic-v2",    # ← fill in
    pdf_pages        = None,
    implemented_in   = ["app/mode_b/step7_magnetic_v2.py",   # ← fill in
                        "app/main.py:step7_magnetic_v2"],
    next_inputs      = ["n_cores", "L_per_core_uH"],
    description      = "Evaluates paired ETD59 cores in parallel; amorphous material option.",
),
```

### Step 5 — Add regression tests

```python
# backend/tests/test_regression.py — add a new class

class TestStep7MagneticV2:

    def test_paired_cores_lower_loss_than_single(self):
        from app.mode_b.step7_magnetic_v2 import evaluate_paired_cores
        from app.mode_b.magnetic_design import design_inductor
        # Single core baseline
        best, _ = design_inductor(240e-6, 16.73, 10.07, 5.161, 70e3, 60.0)
        # Paired option
        result = evaluate_paired_cores(L_uH=240, IL_pk=16.73, IL_rms=10.07)
        assert result["P_total"] < best.P_total, \
            "Paired cores should reduce total loss vs single core"

    def test_paired_result_has_required_keys(self):
        from app.mode_b.step7_magnetic_v2 import evaluate_paired_cores
        r = evaluate_paired_cores(L_uH=240, IL_pk=16.73, IL_rms=10.07)
        required = {"n_cores", "L_per_core_uH", "N_turns", "P_total", "dT_rise"}
        assert required.issubset(r.keys()), f"Missing keys: {required - r.keys()}"
```

### Step 6 — Run and confirm

```bash
cd backend
python -m pytest tests/test_regression.py -v
# Must show: 37 + N_new passed, 0 failed
```

### Step 7 — Update CHANGELOG.md

```markdown
## v2.1.0 — 2025-XX-XX
### Added
- Mode B Step 7: magnetic_design_v2_advisory (paired core, amorphous option)
  - API: POST /mode-b/step7-magnetic-v2
  - Files: app/mode_b/step7_magnetic_v2.py, app/main.py
- Regression tests: TestStep7MagneticV2 (2 tests)
```

### Step 8 — Update DonePanel.tsx

```typescript
// frontend/src/components/DonePanel.tsx
// Change step 7 status pill from queued to done:
const MB_STEPS = [
  ...
  ['magnetic_design_v2_advisory', 'Step 7 API ✓'],  // ← was 'Queued'
  ...
]
```

---

## Critical rules — never break these

### 1. The L formula
```python
# Always: L = Vin_pk × D / (fsw × dIL)
# where:  dIin = r × Iin_pk
#         dIL  = dIin / K(D)
#         K(D) = (2D-1)/D for D≥0.5, (1-2D)/(1-D) for D<0.5
# NEVER use: dIL = crest × IL_ph × 2  ← this was the v1 bug
```
Protected by: `TestCorrectLFormula::test_L_calc_at_90vac_r0095_fsw70k`

### 2. L is independent of N (phase count)
The phase count N only changes per-phase current (Iin_pk/N), NOT the inductance.
Protected by: `TestCorrectLFormula::test_L_is_independent_of_N`

### 3. Medical advisory gates
- Gate 2: TTP topologies flagged "Medical ⚠ verify leakage" (TTP body diodes at zero-crossing)
- Gate 3: When analog + interleaved: show UC3854→UCC28070A/NCP1631/FAN9612 update
- Gate 5: Low ripple zone (r<0.15) preferred for Medical THD compliance
These are in the frontend only — no backend regression test; verify visually.

### 4. 25-step completeness
`TestStepRegistry::test_registry_has_25_steps` ensures no step is ever removed.
`TestStepRegistry::test_step_numbers_are_1_to_25` ensures no gaps.

---

## File edit cheatsheet

| What you want to change | File(s) to edit |
|------------------------|-----------------|
| Add/change Mode B calculation | `app/mode_b/calculations.py` or new `app/mode_b/step_N_*.py` |
| Add API endpoint | `app/main.py` |
| Add PDF section | `app/mode_b/generate_report.py` |
| Add magnetic core to library | `app/mode_b/magnetic_design.py:CORE_LIBRARY` |
| Add regression test | `tests/test_regression.py` |
| Update step status | `app/mode_b/registry.py` |
| Change Gate 2 topology advisory | `frontend/src/components/TopologyHITL.tsx` |
| Change Gate 3 controller advisory | `frontend/src/components/ControllerHITL.tsx` |
| Change Gate 4 L formula display | `frontend/src/components/ChannelSelect.tsx` |
| Change Gate 5 live estimates | `frontend/src/components/MiniIntakeGate.tsx` |
| Add step to Done panel list | `frontend/src/components/DonePanel.tsx:MB_STEPS` |
| Change API client | `frontend/src/api/client.ts` |
| Change design system (colours, Badge, Btn) | `frontend/src/components/ui.tsx` |

---

## Design constants — never change without regression tests

| Constant | Value | Where used | Protected by test |
|----------|-------|-----------|-----------------|
| Vin_min sizing point | 90 Vac | L formula, PDF report | `test_L_calc_at_90vac_r0095_fsw70k` |
| Default eta at low-line | 0.945 | `_calc_l_py`, `calculate.*` | `test_L_calc_at_90vac_r0095_fsw70k` |
| Default PF at low-line | 0.9987 | same | same |
| fsw presets | [50,70,100,140,200] kHz | `MiniIntakeGate.tsx` | visual |
| K(0.5) = 0 | perfect cancellation | `calculations.py` | `test_K_of_D_at_half` |
| L_selected rounding | nearest 5 µH | `main.py`, `generate_report.py` | `test_L_selected_rounds_to_240` |
| Medical leakage limit | 500 µA | `IntakeForm.tsx`, advisories | visual |
| Interleaved IC update | UCC28070A/NCP1631/FAN9612 | `ControllerHITL.tsx` | visual |
