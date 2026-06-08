# Graph Patch Notes — Guardrail v2

This patch assumes the Phase 1 skeleton has already been merged.

## Keep bootstrap early
Call:
```python
from app.workflow.phase1_helpers import ensure_phase1_state_defaults
state = ensure_phase1_state_defaults(state)
```

## Replace placeholder import with real one
The skeleton already uses:
```python
from app.agents.guardrail_v2_agent import node_guardrail_v2_advisory
```

## Safe routing recommendation
Insert Guardrail v2 after `state_space_analysis` and before `bidirectional_thermal`.

Pseudo-routing:
```python
if phase1_enabled(state, "enable_guardrail_v2"):
    next_step = "guardrail_v2_advisory"
else:
    next_step = "bidirectional_thermal"
```

## Legacy compatibility preserved
This implementation still returns:
- `safety_guardrail_data`
- `hitl_required`
- `reflection_log`
