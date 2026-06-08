# Step 15 — Vout Capacitor Design — Implementation Spec

## Rules (read first, follow always)
1. Read every file before editing it
2. Only modify `backend/app/main.py` and `frontend/src/api/client.ts` — add to bottom only
3. All other code goes in NEW files only
4. Do not break any existing functionality
5. Confirm each file created with a summary

---

## Files to Create

### 1. `backend/app/mode_b/data/cap_database.json`

```json
{
  "Nichicon": {
    "LGU — General Purpose 85°C": {
      "series_code": "LGU",
      "temp_rating_C": 85,
      "life_hours": 2000,
      "voltage_ratings": {
        "400": [100,150,180,220,270,330,390,470,560,680,820,1000,1200,1500,1800,2200,2700,3300,3900,4700],
        "420": [100,150,220,330,470,680,1000,1500,2200,3300,4700],
        "450": [100,150,220,330,470,680,1000,1500,2200,3300]
      },
      "ESR_mohm": {
        "100":  {"400":1800,"420":1800,"450":2000},
        "220":  {"400":900,"420":900,"450":1000},
        "470":  {"400":450,"420":450,"450":500},
        "1000": {"400":220,"420":220,"450":250},
        "2200": {"400":120,"420":120,"450":140},
        "4700": {"400":70,"420":70,"450":80}
      },
      "ripple_current_factor": 1.0
    },
    "LGN — Long Life 85°C": {
      "series_code": "LGN",
      "temp_rating_C": 85,
      "life_hours": 5000,
      "voltage_ratings": {
        "400": [100,220,470,1000,2200,4700],
        "450": [100,220,470,1000,2200]
      },
      "ESR_mohm": {
        "1000": {"400":200,"450":230},
        "2200": {"400":110,"450":130}
      },
      "ripple_current_factor": 1.2
    }
  },
  "Panasonic": {
    "EEUFM — Standard 105°C": {
      "series_code": "EEUFM",
      "temp_rating_C": 105,
      "life_hours": 2000,
      "voltage_ratings": {
        "400": [100,150,220,330,470,680,1000,1500,2200,3300,4700],
        "420": [100,220,470,1000,2200,4700],
        "450": [100,220,470,1000,2200]
      },
      "ESR_mohm": {
        "470":  {"400":420,"420":450,"450":480},
        "1000": {"400":200,"420":220,"450":240},
        "2200": {"400":105,"420":115,"450":125},
        "4700": {"400":60,"420":65,"450":70}
      },
      "ripple_current_factor": 1.0
    },
    "EEUFC — Long Life 105°C": {
      "series_code": "EEUFC",
      "temp_rating_C": 105,
      "life_hours": 5000,
      "voltage_ratings": {
        "400": [220,470,1000,2200,4700],
        "450": [220,470,1000,2200]
      },
      "ESR_mohm": {
        "1000": {"400":180,"450":200},
        "2200": {"400":95,"450":110}
      },
      "ripple_current_factor": 1.25
    }
  },
  "Rubycon": {
    "YXG — High Ripple 105°C": {
      "series_code": "YXG",
      "temp_rating_C": 105,
      "life_hours": 3000,
      "voltage_ratings": {
        "400": [100,220,470,1000,1500,2200,3300,4700],
        "450": [100,220,470,1000,1500,2200]
      },
      "ESR_mohm": {
        "470":  {"400":400,"450":450},
        "1000": {"400":190,"450":210},
        "2200": {"400":100,"450":115}
      },
      "ripple_current_factor": 1.15
    }
  },
  "Cornell Dubilier": {
    "380LX — Screw Terminal 85°C": {
      "series_code": "380LX",
      "temp_rating_C": 85,
      "life_hours": 2000,
      "voltage_ratings": {
        "400": [1000,1500,2200,3300,4700,6800,10000],
        "450": [1000,1500,2200,3300,4700,6800]
      },
      "ESR_mohm": {
        "1000": {"400":150,"450":170},
        "2200": {"400":80,"450":90},
        "4700": {"400":45,"450":52}
      },
      "ripple_current_factor": 1.0
    }
  },
  "Vishay": {
    "MAL2 — General Purpose 85°C": {
      "series_code": "MAL2",
      "temp_rating_C": 85,
      "life_hours": 2000,
      "voltage_ratings": {
        "400": [100,220,470,1000,2200,4700],
        "450": [100,220,470,1000,2200]
      },
      "ESR_mohm": {
        "1000": {"400":210,"450":240},
        "2200": {"400":115,"450":130}
      },
      "ripple_current_factor": 1.0
    }
  },
  "TDK": {
    "B43310 — Snap-in 105°C": {
      "series_code": "B43310",
      "temp_rating_C": 105,
      "life_hours": 3000,
      "voltage_ratings": {
        "400": [220,470,1000,2200,3300,4700],
        "450": [220,470,1000,2200,3300]
      },
      "ESR_mohm": {
        "1000": {"400":195,"450":220},
        "2200": {"400":100,"450":115}
      },
      "ripple_current_factor": 1.1
    }
  }
}
```

For ESR values not in database, interpolate: `ESR ≈ K / C_uF`
where K is fit from available points in same series+voltage.

---

### 2. `backend/app/mode_b/step15_capacitor.py`

Load `cap_database.json` from `data/` folder relative to this file.

#### Inputs from state (Step 15.1)
```python
Vout        = state["intake"]["application"]["output_bus_voltage_v"]
Pout_high   = state["intake"]["application"]["output_power_w_high_line"]
Pout_low    = state["intake"]["application"]["output_power_w_low_line"]
f_line      = 60.0
Vdc_ripple  = state["topology_specific_inputs"].get("dc_bus_ripple_vpp", 20.0)
Vdc_min     = state["intake"]["application"].get("holdup_vmin_v", 290.0)
t_hold_s    = state["intake"]["application"].get("holdup_time_ms", 20.0) / 1000.0
Vout_max    = state["topology_specific_inputs"].get("Vout_max_V", Vout * 1.10)

# Two operating points
worst = {"Vin_rms": 180, "Pout": Pout_high, "eta": 0.965}
low   = {"Vin_rms": 90,  "Pout": Pout_low,  "eta": 0.945}
# Override from state ops table if available
```

#### Step 15.2 — C from hold-up (per operating point)
```python
C_holdup = (2 * Pout * t_hold_s) / (Vout**2 - Vdc_min**2)
```

#### Step 15.3 — C from ripple (per operating point)
```python
C_ripple = Pout / (2 * pi * f_line * eta * Vout * Vdc_ripple)
```

#### Step 15.4 — C required
```python
C_required = max(C_holdup_worst, C_holdup_low, C_ripple_worst, C_ripple_low)
# Record governing constraint label
```

#### Step 15.5 — Voltage rating
```python
V_min = max(Vout * 1.12, Vout_max)
V_selected = next v in [400, 420, 450, 500] where v >= V_min
```

#### Step 15.6 — RMS currents (per operating point)
```python
Vin_pk   = sqrt(2) * Vin_rms
I_dc     = Pout / (eta * Vout)
I_LF     = I_dc / sqrt(2)
I_HF     = sqrt(max(0, I_dc**2 * (16*Vout)/(6*Vin_pk*2*pi) - I_LF**2))
I_total  = sqrt(I_LF**2 + I_HF**2)
```

#### Step 15.7 — Verify configuration
```python
C_total      = sum(qty * value_uF for each row) * 1e-6  # convert to F
V_ripple_pp  = Pout / (2*pi * f_line * C_total * eta * Vout)
t_holdup_ms  = C_total * (Vout**2 - Vdc_min**2) / (2 * Pout) * 1000
I_rms_per_cap = I_total / sqrt(total_cap_count)
```

#### Step 15.8 — Effective ESR
```python
# For each cap unit in configuration:
#   Look up ESR from database by value_uF and voltage_rating
#   Interpolate if exact value not in database: ESR = K / C_uF
# Parallel combination:
ESR_parallel = 1 / sum(qty / ESR_i for each row)
V_esr_pk     = I_total * ESR_parallel / 1000  # mohm to ohm
```

#### Suggested configurations (auto-generate 3)
```
1. Fewest caps:  single cap >= C_required, else 2× next lower value
2. Balanced:     2 or 3 equal caps summing to >= C_required
3. Mixed:        largest available cap + smaller caps for remainder
For each: compute all Step 15.7 and 15.8 metrics
```

---

### 3. New endpoints in `main.py` (add at bottom only)

#### `POST /mode-b/step15/capacitor-design`
```
Input:  { state: dict }
Output: {
  inputs: { Vout, f_line, Vdc_ripple, Vdc_min, t_hold_ms, Vout_max },
  worst_case: { Vin_rms, Pout, eta, C_holdup_uF, C_ripple_uF,
                I_LF_A, I_HF_A, I_total_A },
  low_line:   { same fields },
  C_required_uF: float,
  governing: str,
  V_rating_min_V: float,
  V_rating_selected_V: int,
  suppliers: [list of supplier names],
  suggested_configs: [3 options with all metrics]
}
```

#### `POST /mode-b/step15/verify-configuration`
```
Input:  {
  state: dict,
  supplier: str,
  series: str,
  voltage_rating: int,
  configuration: [{ value_uF: int, qty: int }]
}
Output: {
  C_total_uF: float,
  valid: bool,
  margin_pct: float,
  ESR_parallel_mohm: float,
  V_esr_pk_worst_V: float,
  V_esr_pk_low_V: float,
  worst_case: { V_ripple_pp_V, t_holdup_ms, I_rms_per_cap_A, I_rms_total_A },
  low_line:   { same fields }
}
```

#### `GET /mode-b/step15/series-options`
```
Input:  ?supplier=Nichicon
Output: { series: [{ name, series_code, temp_rating_C, life_hours,
                     voltage_ratings: [400,420,450] }] }
```

#### `GET /mode-b/step15/cap-values`
```
Input:  ?supplier=Nichicon&series=LGU&voltage_rating=450
Output: { values_uF: [100,150,220,...] }
```

---

### 4. `frontend/src/components/Step15Capacitor.tsx`

Single scrollable page. Use Card, Btn, SecHead, Spinner from `./ui`.
Match Step7Wizard styling.

#### Section 1 — Calculation Results (read-only)
Two-column table: Worst-case | Low-line
- C from hold-up (µF)
- C from ripple (µF)
- C required — governing value highlighted amber
- Governing constraint label
- I_LF (A), I_HF (A), I_total (A)

#### Section 2 — Voltage Rating
- Show: Vout × 1.12 = xxx V
- Show: Vout_max transient = xxx V
- Show: Required rating ≥ xxx V
- Show: Selected rating = xxx V (green)

#### Section 3 — Supplier, Series, Voltage (all in one row)
```
[Nichicon] [Panasonic] [Rubycon] [Cornell Dubilier] [Vishay] [TDK]
     ↓ selecting supplier shows series dropdown
[LGU — General 85°C ▼]   →   [400V] [420V] [●450V]
```
- Supplier = clickable badge buttons
- Series = dropdown filtered by supplier
- Voltage = radio buttons, auto-select minimum valid, can go higher

#### Section 4 — Value Selection + Configuration Table
```
Top: grid of value buttons from selected series+voltage
  [100µF] [150µF] [220µF] [330µF] [470µF] [680µF]
  [1000µF] [1500µF] [2200µF] [3300µF] [4700µF]
  Click → adds row to table below

Configuration table columns:
  Value (µF) | Qty (1–10 dropdown) | Subtotal (µF) | ESR (mΩ) | Remove ✕
  TOTAL row:   —                   | xxx µF        | xxx mΩ   |
  Total color: green if >= C_required, red if below

Suggested configs (quick-load buttons):
  💡 1 × 2200µF
  💡 2 × 1000µF + 1 × 220µF
  💡 3 × 680µF + 1 × 100µF
```

#### Section 5 — Performance Summary (live, debounced 500ms)
Calls `/verify-configuration` on every configuration change.
Two-column table: Worst-case | Low-line
- V_ripple pk-pk (V)
- I_rms per cap (A)
- I_rms total (A)
- Hold-up time (ms)
- ESR parallel (mΩ)
- ESR voltage spike pk (V)

#### Confirm Button
- Disabled until: C_total >= C_required AND supplier + series selected
- Label: "Confirm Capacitor Selection →"
- onClick: call onConfirm(result)

#### Props
```typescript
interface Props {
  confirmedState: Record<string, unknown>
  onConfirm: (result: CapacitorResult) => void
  onBack: () => void
}
```

---

### 5. `client.ts` additions (add at bottom only)

```typescript
export const step15CapacitorDesign = (req: { state: object }) =>
  post('/mode-b/step15/capacitor-design', req)

export const step15VerifyConfig = (req: {
  state: object
  supplier: string
  series: string
  voltage_rating: number
  configuration: { value_uF: number; qty: number }[]
}) => post('/mode-b/step15/verify-configuration', req)

export const step15SeriesOptions = (supplier: string) =>
  get(`/mode-b/step15/series-options?supplier=${encodeURIComponent(supplier)}`)

export const step15CapValues = (supplier: string, series: string, voltage: number) =>
  get(`/mode-b/step15/cap-values?supplier=${encodeURIComponent(supplier)}&series=${encodeURIComponent(series)}&voltage_rating=${voltage}`)
```

---

### 6. Report integration

Create `backend/app/mode_b/generate_step15.py` with function:
```python
def generate_step15_section(result: dict) -> list:
    """Returns ReportLab story elements for Step 15."""
```

Sections to include:
- Step 15.1 inputs table
- Step 15.2 C_holdup formula + two-column results
- Step 15.3 C_ripple formula + two-column results
- Step 15.4 C_required selection with governing label
- Step 15.5 Voltage rating rationale
- Step 15.6 RMS current table (worst-case + low-line)
- Step 15.7 Verified performance table
- Step 15.8 Summary table (2 columns)
- ESR calculation and voltage spike

In `generate_combined_report.py`, call this function when
`step15_result` is present in the approved design dict.
