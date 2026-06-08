# Step 15 Enhancements — Implementation Spec

## Rules (follow always)
1. Read every file before editing it
2. Only add to existing files — never remove or rewrite existing code
3. All new backend logic goes in new files or appended to step15_capacitor.py
4. Confirm each change with a summary of what was modified

---

## Enhancement 1 — Custom Capacitor with Datasheet Upload

### Backend

Add to `backend/app/mode_b/step15_capacitor.py`:

```python
def parse_custom_cap_datasheet(pdf_bytes: bytes, part_number: str) -> dict:
    """
    Extract key parameters from uploaded capacitor datasheet PDF.
    Use pdfplumber to extract text, then search for:
      - Capacitance value (uF)
      - Voltage rating (V)
      - ESR at 100Hz and 120Hz (mohm)
      - Ripple current rating (A)
      - Temperature rating (C)
      - Life hours
    Return dict with extracted values and confidence flags.
    If extraction fails for a field, return None for that field
    so UI can prompt designer to enter manually.
    """
```

Add new endpoint to `main.py` (bottom only):

```
POST /mode-b/step15/custom-capacitor
  Input:  multipart/form-data
    - file: PDF datasheet
    - part_number: str
    - state: str (JSON)
  Output: {
    part_number: str,
    extracted: {
      capacitance_uF: float | None,
      voltage_rating_V: int | None,
      ESR_100Hz_mohm: float | None,
      ESR_120Hz_mohm: float | None,
      ripple_current_A: float | None,
      temp_rating_C: int | None,
      life_hours: int | None
    },
    confidence: {field: "extracted"|"manual_required"},
    can_use_in_config: bool
  }
```

### Frontend additions to `Step15Capacitor.tsx`

Add a collapsible section above Section 3 (supplier selection):

```
┌─────────────────────────────────────────────────────┐
│  Custom Capacitor (Optional)                        │
│                                                     │
│  Part number: [________________]                    │
│  Datasheet:   [Upload PDF ▲]  filename.pdf ✓        │
│                                                     │
│  Extracted specs:                                   │
│  Capacitance: 1000 µF   ✓ extracted                 │
│  Voltage:     450 V     ✓ extracted                 │
│  ESR @100Hz:  [185  ] mΩ  ⚠ enter manually         │
│  Ripple Irms: [12.5 ] A   ⚠ enter manually         │
│  Temp rating: 105 °C    ✓ extracted                 │
│  Life:        3000 h    ✓ extracted                 │
│                                                     │
│  [Add to configuration ↓]                          │
└─────────────────────────────────────────────────────┘
```

- Fields marked "enter manually" are editable inputs
- Once added, custom cap appears in configuration table
  same as standard caps with label "Custom: [part_number]"
- ESR used in all downstream calculations

---

## Enhancement 2 — Temperature Rise & Ripple Current Table

### Backend

Add function to `step15_capacitor.py`:

```python
def calculate_thermal_table(
    config: list,           # [{value_uF, qty, ESR_mohm, part_number}]
    state: dict,
    supplier: str,
    series: str,
    voltage_rating: int
) -> dict:
    """
    For each of the 9 operating points (all Vin_rms values):
      1. Calculate I_rms through capacitor bank
      2. Calculate I_rms per capacitor = I_total / sqrt(n_caps)
      3. Calculate power dissipated per cap:
           P_cap = I_rms_per_cap^2 * ESR_parallel / n_caps / 1000
      4. Calculate temperature rise:
           dT = P_cap * Rth_ca
           where Rth_ca = 10 C/W for snap-in, 15 C/W for radial (default)
           Use series type to select Rth_ca
      5. Calculate V_ripple_pp at each operating point
      6. Check ripple current against rated value (pass/fail)
    
    Return table with one row per operating point.
    """
```

Add to verify-configuration endpoint response:

```json
{
  "thermal_table": [
    {
      "Vin_rms": 90,
      "Pout_W": 1700,
      "I_cap_total_A": 6.26,
      "I_cap_per_unit_A": 3.13,
      "P_dissipated_W": 0.48,
      "dT_rise_C": 7.2,
      "T_cap_C": 57.2,
      "V_ripple_pp_V": 5.56,
      "ripple_pass": true
    },
    {
      "Vin_rms": 180,
      "Pout_W": 3600,
      "I_cap_total_A": 12.97,
      "I_cap_per_unit_A": 6.49,
      "P_dissipated_W": 2.06,
      "dT_rise_C": 20.6,
      "T_cap_C": 70.6,
      "V_ripple_pp_V": 11.53,
      "ripple_pass": true
    }
    // ... all 9 operating points
  ],
  "worst_case_dT_C": 20.6,
  "worst_case_T_C": 70.6,
  "all_ripple_pass": true
}
```

### Frontend — add thermal table to Section 5

Below the performance summary, add:

```
Ripple Current & Temperature Rise — All Operating Points

Vin   | Pout  | I_cap total | I per cap | P dissip | ΔT rise | T_cap | Ripple | Pass
(Vac) | (W)   | (A)         | (A)       | (W)      | (°C)    | (°C)  | Vpp    |
 90   | 1700  | 6.26        | 3.13      | 0.48     | 7.2     | 57.2  | 5.56V  | ✓
110   | 1700  | ...
...
180   | 3600  | 12.97       | 6.49      | 2.06     | 20.6    | 70.6  | 11.53V | ✓
...all 9 rows

Worst-case cap temperature: 70.6°C  (limit: 85°C)  ✓
```

Color code T_cap column:
- Green: T_cap < temp_rating - 20°C
- Amber: T_cap < temp_rating - 5°C  
- Red:   T_cap >= temp_rating - 5°C

---

## Enhancement 3 — UI Cleanup

### Remove back-to-Step-7 button

In `Step15Capacitor.tsx`, remove the "← Back to Step 7" button.
Keep only:
- "← Back" (goes to previous step within Step 15 flow if any)
- "📄 Generate Report" button
- "Confirm & Next Step →" button

---

## Enhancement 4 — Report Generation Button

### Add to Step15Capacitor.tsx bottom action bar:

```tsx
<Btn
  variant="secondary"
  disabled={rptLoading}
  onClick={async () => {
    setRptLoad(true)
    try {
      const blob = await step15GenerateReport({
        state: confirmedState,
        approved_design: approvedDesign,   // from Step 7
        step15_result: currentResult,
      })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      const pid = (confirmedState as any).project_id ?? 'design'
      a.href = url
      a.download = `PFC_Report_${pid}_Steps1_15.pdf`
      document.body.appendChild(a)
      a.click()
      a.remove()
      URL.revokeObjectURL(url)
    } catch(e) {
      console.error('Report failed', e)
    } finally {
      setRptLoad(false)
    }
  }}
>
  {rptLoading ? '⏳ Generating…' : '📄 Generate Report (Steps 1–15)'}
</Btn>
```

### New endpoint in `main.py` (add at bottom only):

```
POST /mode-b/step15/generate-report
  Input:  {
    state: dict,
    approved_design: dict,   // Step 7 DesignResult
    step15_result: dict      // full Step 15 result including thermal table
  }
  Output: PDF binary (application/pdf)
  Filename: PFC_Report_{project_id}_Steps1_15.pdf
```

### New file `backend/app/mode_b/generate_step15.py`:

```python
def generate_step15_section(result: dict) -> list:
    """
    Returns ReportLab Platypus story elements for Step 15.
    Sections:
      15.1 — Inputs table (Vout, f_line, Vdc_ripple, Vdc_min, t_hold)
      15.2 — C_holdup formula + two-column results table
      15.3 — C_ripple formula + two-column results table
      15.4 — C_required with governing constraint highlighted
      15.5 — Voltage rating rationale
      15.6 — RMS current table (worst-case + low-line rows)
      15.7 — Selected configuration table
               (value | qty | subtotal | ESR each | ESR parallel)
      15.8 — Performance table (V_ripple, I_rms, t_holdup both op points)
      15.9 — Thermal table (all 9 operating points, colored T_cap column)
      15.10 — Summary table two columns worst-case and low-line
    
    Use same styling as generate_steps13_14.py:
      - Navy header rows
      - Alternating stripe rows
      - Pass/fail badges in green/red
      - Section headers in teal
    """
```

In `generate_combined_report.py`:
- Import `generate_step15_section`
- After Steps 13-14 pages, append Step 15 pages if `step15_result` provided
- Update PDF metadata title to "Steps 1–15"

### Add to `client.ts` (bottom only):

```typescript
export const step15GenerateReport = (req: {
  state: object
  approved_design: object
  step15_result: object
}): Promise<Blob> =>
  fetch(`${BASE}/mode-b/step15/generate-report`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  }).then(async res => {
    if (!res.ok) { const t = await res.text(); throw new Error(`${res.status}: ${t}`) }
    return res.blob()
  })
```

---

## Enhancement 5 — Approve and Go to Next Step Button

### Add to Step15Capacitor.tsx bottom action bar:

```tsx
<Btn
  variant="success"
  disabled={!isConfigValid}
  onClick={() => onConfirm({
    supplier,
    series,
    voltage_rating: voltageRating,
    configuration,
    C_total_uF: verifyResult?.C_total_uF,
    ESR_parallel_mohm: verifyResult?.ESR_parallel_mohm,
    thermal_table: verifyResult?.thermal_table,
    worst_case: verifyResult?.worst_case,
    low_line: verifyResult?.low_line,
  })}
>
  Approve & Continue to Step 16 →
</Btn>
```

### Bottom action bar final layout:

```
[← Back]    [📄 Generate Report (Steps 1–15)]    [Approve & Continue →]
```

Left-aligned back button, center report button, right-aligned approve button.
Approve button disabled until C_total >= C_required AND supplier+series selected.

---

## Props update for Step15Capacitor.tsx

```typescript
interface Props {
  confirmedState: Record<string, unknown>
  approvedDesign: Record<string, unknown>   // ADD THIS — Step 7 result
  onConfirm: (result: CapacitorResult) => void
  onBack: () => void
}

interface CapacitorResult {
  supplier: string
  series: string
  voltage_rating: number
  configuration: { value_uF: number; qty: number; part_number?: string }[]
  C_total_uF: number
  ESR_parallel_mohm: number
  thermal_table: ThermalRow[]
  worst_case: OperatingPointResult
  low_line: OperatingPointResult
}
```

---

## Install required package

```bash
pip install pdfplumber --break-system-packages
```

Add `pdfplumber` to `backend/requirements.txt`
