# DesignState — Field Ownership Reference

Single source of truth for every field that flows through the `state` dict
between the React frontend and the FastAPI backend.

Schema file: `backend/app/design_state.py`  
TypeScript mirror: `frontend/src/types/DesignState.ts`  
Feature flag: `backend/app/config/feature_flags.py` → `enable_design_state_validation`

---

## Ownership Rules

| Rule | Description |
|------|-------------|
| **One owner** | Each top-level field is set by exactly one agent/endpoint. |
| **Read freely** | Any agent may read any field. |
| **Doc Agent is read-only** | Documentation Agent reads DesignState but never writes design fields. |
| **JS tools own `js_state`** | JS studio tools (review_magnetics.html, control_design.html) write only to `js_state`. Python agents never write `js_state`. |
| **Extra fields allowed** | All Pydantic models use `extra='allow'`. Forward-compat: new fields from the frontend never cause 422 errors. |

---

## Field Table

### Root level

| Field | Type | Set by endpoint | Read by |
|-------|------|-----------------|---------|
| `project_id` | `str` | `/mode-a/start` | All report generators |
| `intake` | `Intake` | `/mode-a/start` | All Mode-B engines |
| `topology_recommendation` | `TopologyRecommendation` | `/mode-a/approve-topology` | Frontend display |
| `selected_topology` | `str` | `/mode-a/approve-topology` | Controller strategy, report |
| `selected_mode` | `str` | `/mode-a/approve-topology` | fsw defaults, L calc |
| `controller_strategy` | `ControllerStrategy` | `/mode-a/approve-topology` | Frontend display, report |
| `selected_controller_mode` | `str` | `/mode-a/approve-controller` | Mini-intake, report |
| `selected_channels` | `int` | `/mode-a/approve-channels` | Step-7 engine (N_phases) |
| `topology_specific_inputs` | `TopologySpecificInputs` | `/mode-a/submit-mini-intake` | All Step-7/8/15/16 engines |
| `js_state` | `JsState` | JS studio tools only | JS tools only |

---

### `intake.application`

| Field | Type | Used by |
|-------|------|---------|
| `vin_rms_min` | `float` | Step-7 L calc, thermal, report |
| `output_power_w_low_line` | `float` | Step-7 Ipk calc, report |
| `output_power_w_high_line` | `float` | Step-15 C sizing (worst-case) |
| `output_bus_voltage_v` | `float` | Step-7 D calc, Step-8, Step-15, Step-16 |
| `nominal_line_frequency_hz` | `float` | Step-15 ripple calc, Step-8 |

### `intake.thermal`

| Field | Type | Used by |
|-------|------|---------|
| `ambient_temp_c_max` | `float` | Step-7 thermal model (T_amb) |
| `hotspot_limit_c` | `float` | Step-7 ΔT budget |

### `intake.compliance`

| Field | Type | Used by |
|-------|------|---------|
| `application_class` | `str` | Step-7 coated_only flag, report Medical advisory |
| `leakage_current_limit_ua` | `float` | Report sections |

### `intake.control`

| Field | Type | Used by |
|-------|------|---------|
| `control_preference` | `str` | `/mode-a/approve-topology` controller strategy |

### `intake.business`

| Field | Type | Used by |
|-------|------|---------|
| `preferred_switch_technology` | `list[str]` | Controller strategy (WBG detection) |

---

### `topology_specific_inputs`

| Field | Type | Set when | Used by |
|-------|------|----------|---------|
| `switching_frequency_style` | `str` | mini-intake submit | Frontend display |
| `recommended_frequency_hz` | `float` | mini-intake submit | Step-7/8 fsw |
| `recommended_frequency_range_hz` | `[float,float]` | CrCM/DCM only | Frontend display |
| `default_crest_ripple_ratio` | `float` | mini-intake submit | Step-7 dIL calc |
| `confirmed_L_uH` | `float` | mini-intake submit (exact) | Step-7 L_target |
| `confirmed_L_uH_sel` | `float` | mini-intake submit (rounded) | Step-7 L_target_H |
| `confirmed_Iin_pk_A` | `float` | mini-intake submit | Display |
| `confirmed_dIL_A` | `float` | mini-intake submit | Display |
| `dIL_pp_A` | `float` | mini-intake submit | Step-7 dIL_pp |
| `Iph_rms_A` | `float` | mini-intake submit | Step-7 Irms |

---

## Adding a New Field

1. Add the field to `design_state.py` under the correct sub-model.
2. Add a row to this table (field, type, set-by, read-by).
3. Add the field to `DesignState.ts` in the same position.
4. Declare read/write intent in the new agent's docstring.

## Adding a New Agent

1. Define which DesignState fields the agent **reads** (list them).
2. Define which DesignState fields the agent **writes** (list them — should be a new sub-section it owns).
3. Update this table.
4. Never write fields owned by another agent.

---

*Last updated: 2026-06-06*  
*Schema version: 1.0 — Phase 1 (validation off by default)*
