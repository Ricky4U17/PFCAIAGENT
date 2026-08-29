# PFC AI Design Agent — Technical Brief

**Purpose of this document.** This is a handoff brief for designing a larger framework that
extends the existing work: PFC (built) + DC/DC (not built) + simulation-tool integration
(stubbed) + Altium schematic/PCB (stubbed).

It is written to be read by an AI that has **not** seen the codebase. It states what exists, what
is a placeholder, and what conventions the existing code enforces — so that a bigger design builds
*on* it rather than beside it.

Describes commit `64fcfb4`. Repo root: `pfc_ai_agent_v2/`.

---

## 1. One-paragraph summary

A designer-driven tool that turns a power-supply specification into a complete PFC stage design
(magnetics, DC-bus capacitor, control loops, semiconductors, input protection, EMI filter) plus a
~190-page traceable engineering report. All physics is deterministic Python. No LLM output reaches
any number in the report. The designer approves every stage; nothing advances automatically.

---

## 2. What is genuinely built, and what is a placeholder

This distinction matters more than anything else in this document.

| Area | Status | Evidence |
|---|---|---|
| PFC magnetics (inductor) | **Production** | `step7_magnetic_calc.py` — iGSE, DC-bias-aware turns convergence, two-node thermal, catalogue ranking over 92 materials |
| DC-bus capacitor | **Production** | `step15_capacitor.py` — ripple, vendor-implied ESR(T), lifetime, ±20 % tolerance corners |
| Control loops | **Production** | `step16_step10_iloop.py`, `step16_step11_vloop.py` — 9-point plant, compensators, E-series snapping |
| Semiconductors | **Production** | `pfc_loss_model.py` — per-mechanism loss + thermal network |
| Input protection | **Production** | NTC / MOV / GDT / fuse selectors with vendor DBs |
| EMI filter | **Production** | DM/CM design against limit lines |
| Report generation | **Production** | ~190 pp, 10 chapters, ReportLab |
| **LangGraph orchestration** | **Blueprint only** | `app/workflow/graph.py`, 38 nodes. `build_graph()` is called **from tests only** — the GUI does not run it |
| **SIMPLIS export** | **Stub (17 lines)** | `app/exporters/simplis_exporter.py` — emits a netlist *starter* with a few threaded parameters |
| **Altium export** | **Stub (2 lines)** | `app/exporters/altium_exporter.py` — returns a hardcoded 3-component dict with `"TBD"` values |
| **DC/DC stage** | **Placeholder fields only** | `inputfilter/emi_filter_design.py` has a `DCDCResult` dataclass so the EMI filter can account for a DC/DC noise source; there is no DC/DC design engine |
| PCB floorplanning, firmware gen, closed-loop sim, CAD thermal | **Advisory stubs** | Nodes exist in the graph and return advisory placeholders |

**Implication for the bigger framework:** the extension points you want (DC/DC, simulation,
Altium) already exist as *named hooks with placeholder implementations*. They are not missing —
they are unfilled. A larger design should plan to implement behind those names, and should expect
to define the data contracts they need, because the stubs do not define them meaningfully.

---

## 3. Architecture

### 3.1 The production path

```
React 18 + TypeScript (Vite)
        |  HTTP (~40 endpoints)
FastAPI + Pydantic v2
        |  direct function calls
Deterministic engines (NumPy / SciPy)
        |
JSON material DB + Excel vendor workbooks
        |
ReportLab PDF (+ matplotlib figures, SchemDraw schematics)
```

The designer is the orchestrator. There is no planner deciding the next step; the sequence is the
designer moving through GUI screens, each click an explicit HTTP call.

### 3.2 The LangGraph blueprint

`app/workflow/graph.py` builds a `StateGraph(ProjectState)` with 38 nodes and real
human-in-the-loop wait states (`WAIT_TOPOLOGY`, `WAIT_TOPOLOGY_SPECIFIC`, `WAIT_CONTROLLER`,
`WAIT_MODE_B`) that suspend the graph pending a designer decision. 23 agent modules sit behind the
nodes (`app/agents/`).

It is tested but not on the runtime path. Treat it as the intended orchestration design, already
expressed in code, that the shipping product has not yet been migrated onto.

**Node list** (useful because it shows the intended full scope, including the unbuilt parts):

```
intake_node, topology_selection, topology_hitl, topology_specific_intake,
controller_selection, controller_selection_hitl, WAIT_* (4),
input_processing, duty_and_ripple, inductor_sizing, worst_case_angle,
waveform_reconstruction, magnetic_design, magnetic_design_v2_advisory,
magnetic_fea_advisory, protection_compliance, emi_filter,
layout_parasitics_advisory, control_loops, state_space_analysis,
guardrail_v2_advisory, bidirectional_thermal, cad_thermal_integration_advisory,
vendor_scout, supply_chain_advisory, reliability_mtbf_advisory,
design_graphs, simulation_export, closed_loop_simulation_advisory,
firmware_generation_advisory, pcb_floorplanning_advisory, altium_export,
mode_b_hitl, finalize
```

### 3.3 The state contract

`DesignState` (Pydantic, `app/design_state.py`) is the single object carried between every step.
`model_config = ConfigDict(extra="allow")`, so stages may add keys without a schema migration —
but every *read* should be an explicit declared field, because the failure mode below is real.

---

## 4. Conventions the codebase enforces

These were learned from defects, not chosen abstractly. A larger framework should adopt them.

**4.1 One engine per quantity.** If two chapters print the same number they must call the same
function. Violations produced real, shipped defects: a current density printed 4.17 in one place
and 4.12 in another (two different RMS currents); a capacitor loss that differed several-fold
between chapters (one re-derived it from a nominal ESR instead of the owning engine).

**4.2 No hidden defaults; missing data is printed as DATA MISSING.** An assumed value that looks
like a computed one is worse than a gap. Example: the capacitor voltage class is currently
justified against the regulated bus only, because the OVP threshold and transient maximum are not
design inputs — the report says so rather than assuming them.

**4.3 A gate may block release, never selection.** An unverified or missing datasheet value can
stop a release sign-off and must be listed as a blocker, but must never make every candidate
un-selectable. The designer can always proceed with a documented risk.

**4.4 Requirement → screen → select → verify.** Each design block derives its requirement *before*
naming a part. An earlier version named the part first, making the reasoning circular; Chapters 8
and 9 were restructured specifically to fix this.

**4.5 Provenance is printed.** Material and thermal models carry supplier, catalogue revision and
page, the temperature each curve is valid at, which of two candidate models is the design model,
and which parameters the engine had to estimate and from what.

**4.6 Defaults must not silently substitute for designer input.** This recurred three times:
a hold-up floor read from a key nothing wrote (so Chapter 1 always showed a hardcoded 300 V while
sizing used 290 V); a control grid hardcoded to voltages appearing in no other chapter; a
semiconductor ambient hardcoded to 45 °C while every other chapter used the spec's 50 °C. Each
made a chapter quietly disagree with the specification.

---

## 5. Traps worth inheriting

Practical failure modes discovered while building this. A larger framework will hit them too.

- **A defensive `try/except` around new code hides the typo it was meant to survive.** A wrong
  parameter name raised `NameError`, the handler swallowed it, and three report tables silently
  vanished while the build still reported success.
- **A chapter can disappear without any error.** Chapter builders run under a tolerance path; an
  exception inside one dropped ~90 pages while the endpoint still returned HTTP 200. Only a
  page-count assertion caught it.
- **`dict.get(key, default)` does not fire on an empty string.** A payload carrying `""` produced
  a literally blank field where the default was expected.
- **Report text must be validated by extracting from a built PDF**, not by reading source.
  Multiple defects (a mis-typed format specifier, a stale label, an unrenderable glyph) were
  invisible to both the syntax check and the test suite.
- **ReportLab renders a filled black box for glyphs outside WinAnsi that are not in its symbol
  table.** Two entities (non-breaking hyphen, black circle) shipped as visible black squares.
- **Scripted renumbering can create duplicates that a naive audit cannot see.** Renaming a lone
  `8.1b` to `8.1` collided with an existing `8.1`.

---

## 6. Extension points for the larger framework

### 6.1 DC/DC stage
Nothing exists beyond `DCDCResult` in the EMI filter, which models the DC/DC only as a
common-mode noise *source*. A DC/DC design engine would be a new peer to `step7`/`step15`/`step16`.
The natural shape, following the existing pattern: a requirement calculator, a catalogue screen
against the same vendor workbooks, a designer selection step, and a re-verification on the actual
part — then its own report chapter built with the shared `doc_report_builder` helpers.

### 6.2 Simulation-tool integration
Two distinct things already exist and should not be confused:
- **In-tool simulation agents** — four embedded HTML studios (inductor, DC-bus capacitor, control)
  plus an independent Python cross-check engine (`app/sim_agent/`) whose result is printed in the
  report as a quantity-by-quantity comparison. These are *verification*, not design.
- **External simulator export** — `simplis_exporter.py`, a 17-line netlist starter. This is the
  hook for real SIMPLIS/LTspice/PLECS integration and would need a proper netlist builder plus a
  results-import path if closed-loop verification is wanted.

### 6.3 Altium schematic / PCB
`altium_exporter.py` is a 2-line stub returning fabricated components. Everything is unbuilt:
component-to-library mapping, net generation from the actual selected parts, footprint selection,
and any PCB constraint output. The graph nodes `pcb_floorplanning_advisory` and `altium_export`
reserve the place in the flow.

Note the selected parts *are* fully available — every stage stores a complete selected-part record
(manufacturer, part number, datasheet URL, ratings), which is what a real BOM/netlist export needs.

---

## 7. Repository map

```
backend/
  app/
    main.py                    ~40 FastAPI endpoints
    design_state.py            DesignState / Intake Pydantic models
    workflow/graph.py          LangGraph blueprint (38 nodes, test-only)
    agents/                    23 agent modules
    mode_b/
      step7_magnetic_calc.py   inductor engine
      step15_capacitor.py      DC-bus capacitor engine
      step16_*.py              control loops
      semiconductor/           loss model + device DB
      inputprotection/         NTC / MOV / GDT / fuse
      inputfilter/             EMI (contains the DC/DC placeholder)
      doc_report_builder.py    report Ch1-5 + shared helpers
      report_*.py              Ch6-10
    sim_agent/                 independent cross-check engine
    exporters/                 SIMPLIS + Altium stubs
    magnetics/db.py            92-material database
  data/magnetic_materials/     per-supplier JSON
  tests/                       172 tests
frontend/src/components/       7 design screens + 4 embedded studios
specs/Database/*.xlsx          vendor workbooks (loaded at runtime)
PENDING_ITEMS.md               open items: DATA / CODE / DECISION
IMPLEMENTATION_LOG.md          what was done and why, newest last
SESSION_HANDOFF.md             current state and next steps
```

---

## 8. Known open items a larger design should be aware of

- Capacitor bank meets its requirement at nominal but **fails at −20 % tolerance** on the
  reference design; the report states this and leaves the decision to the designer.
- The saturation acceptance gate runs on mean-path flux while the report quotes the more
  conservative inner-bore figure; both are printed, and unifying them would change part selection.
- `L_target` (designer-confirmed inductance) and `L_req` (derived from the ripple ratio) can
  disagree; only `L_req` sizes anything. This ambiguity should be resolved in a larger design
  rather than inherited.
- Several vendor workbooks lack columns needed to close checks fully (bridge hot V-I curve,
  MOV clamping at rated current, GDT follow-current). These are printed as DATA MISSING.

Full detail in `PENDING_ITEMS.md`.
