# PFC AI Design Agent — Latest Workflow

This document describes the current end-to-end design workflow executed by the
LangGraph state machine in `backend/app/workflow/graph.py`.

## Execution model

The graph uses a **re-run-from-START** model: every `graph.invoke()` re-enters at
`intake_node`. A human-in-the-loop (HITL) pause is implemented by routing to a
`WAIT_*` node that ends the invocation; the next invoke resumes from the step in
progress. Progress is tracked with `mode`, `last_completed_step`, and `pending_step`.

## Gates before Mode B

1. **Topology approval** (`awaiting_topology_approval`) — approve the selected topology.
2. **Topology-specific mini-intake** (`awaiting_topology_specific_inputs`) — switching
   frequency style/value and crest ripple ratio.
3. **Controller approval** (`awaiting_controller_approval`) — controller mode
   (analog/digital) and part.

After the controller gate the graph enters **Mode B** and steps through
`MODE_B_SEQUENCE` one step per approved invoke, pausing at
`awaiting_mode_b_approval` between steps, until `finalize` sets `current_step = "final"`.

## Mode B sequence (25 steps)

The pipeline is `MODE_B_SEQUENCE` (length **25**, terminal step `altium_export`):

| # | Step | Notes |
|---|------|-------|
| 1 | `input_processing` | |
| 2 | `duty_and_ripple` | |
| 3 | `inductor_sizing` | thermal loopback re-entry point |
| 4 | `worst_case_angle` | |
| 5 | `waveform_reconstruction` | |
| 6 | `magnetic_design` | |
| 7 | `magnetic_design_v2_advisory` | Phase 1 advisory |
| 8 | `magnetic_fea_advisory` | Phase 3 advisory |
| 9 | `protection_compliance` | |
| 10 | `emi_filter` | |
| 11 | `layout_parasitics_advisory` | Phase 2 advisory |
| 12 | `control_loops` | analytic loop design |
| 13 | `state_space_analysis` | state-space current/voltage loop design + margins |
| 14 | `guardrail_v2_advisory` | Phase 1 advisory / design validation |
| 15 | `bidirectional_thermal` | thermal check; loops back to `inductor_sizing` on failure |
| 16 | `cad_thermal_integration_advisory` | Phase 3 advisory |
| 17 | `vendor_scout` | |
| 18 | `supply_chain_advisory` | Phase 1 advisory |
| 19 | `reliability_mtbf_advisory` | Phase 2 advisory |
| 20 | `design_graphs` | |
| 21 | `simulation_export` | |
| 22 | `closed_loop_simulation_advisory` | correlates math vs. SPICE (scaffold backend) |
| 23 | `firmware_generation_advisory` | Phase 2 advisory |
| 24 | `pcb_floorplanning_advisory` | Phase 3 advisory |
| 25 | `altium_export` | terminal step → `finalize` |

## Phase 3 advisory nodes

The **Phase 3** advisories are non-blocking and run inside the main flow:
`magnetic_fea_advisory`, `cad_thermal_integration_advisory`, and
`pcb_floorplanning_advisory`. Each is gated by a feature flag in `ADVISORY_FLAG_MAP`;
a disabled advisory auto-advances without a human round-trip.

## Control-loop design (state-space)

`state_space_analysis` builds the small-signal plant (`plant_models.py`), auto-designs
current and voltage compensators (`loop_compensators.py`), and calibrates each
compensator gain so the open-loop crossover lands at the design target
(`topology_state_space_router._calibrate_loop_gain`). The boost plant includes
inductor DCR (`r_L`) so the CCM LC resonance is realistically damped; the voltage
loop uses an integrator-dominant compensator that rolls off cleanly through the
resonance. Both loops are checked for crossover, phase margin, and gain margin.

## Thermal loopback guard

`bidirectional_thermal` can request a hardware recalculation (loop back to
`inductor_sizing`, clearing downstream stale steps). Loopbacks are capped at
`THERMAL_LOOPBACK_LIMIT` (3); on reaching the limit the workflow logs an error and
pauses at `awaiting_mode_b_approval` for manual intervention (change inputs / cooling).
