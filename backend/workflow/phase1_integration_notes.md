# Phase 1 Integration Notes

## Safe rollout rules
- Guardrail v2 enabled
- Supply-chain advisory enabled, non-blocking
- Magnetic Design v2 advisory enabled, non-blocking
- Closed-loop Simulation Verification advisory enabled, non-blocking
- no overwrite of legacy outputs
- feature flags control all new nodes
- existing stable path remains valid

## Suggested graph wiring points

### Early bootstrap
Call:
```python
state = ensure_phase1_state_defaults(state)
```

### After `magnetic_design`
Insert:
```python
if phase1_enabled(state, "enable_magnetic_design_v2"):
    next_step = "magnetic_design_v2_advisory"
else:
    next_step = "protection_compliance"
```

### After `state_space_analysis`
Insert:
```python
if phase1_enabled(state, "enable_guardrail_v2"):
    next_step = "guardrail_v2_advisory"
else:
    next_step = "bidirectional_thermal"
```

### After `vendor_scout`
Insert:
```python
if phase1_enabled(state, "enable_supply_chain_agent"):
    next_step = "supply_chain_advisory"
else:
    next_step = "design_graphs"
```

### After `simulation_export`
Insert:
```python
if phase1_enabled(state, "enable_closed_loop_simulation"):
    next_step = "closed_loop_simulation_advisory"
else:
    next_step = "altium_export"
```
