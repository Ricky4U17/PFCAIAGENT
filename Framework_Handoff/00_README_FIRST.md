# Framework Handoff — PFC AI Design Agent

**What this is.** A package describing an existing, working PFC design tool, prepared so that a
larger framework can be designed around it — extending to DC/DC design, external simulator
integration, and Altium schematic/PCB output.

**Read in this order:**

| # | File | What it gives you |
|---|---|---|
| 1 | `01_workflow_diagram.png` | The whole tool on one page: designer / GUI / engine / data lanes, every human gate, Mode A and Mode B |
| 2 | `02_framework_layers.png` | The software stack — what runs what |
| 3 | `03_Architecture_and_Workflow.pdf` | 6-page narrative: what the tool is, each gate and stage, the framework, how simulation is used, where numbers come from |
| 4 | `04_TECHNICAL_BRIEF.md` | **The important one for design work.** What is built vs stubbed, the conventions, the traps, and the concrete extension points |
| 5 | `05_OPEN_ITEMS.md` | Full open-items register: DATA / CODE / DECISION, with reasoning |
| 6 | `06_CURRENT_STATE.md` | Where the work stands now and what comes next |
| 7 | `07_api_and_engines.json` | **Machine-readable**: 63 endpoints grouped by domain, 18 engine modules with status and public functions, 38 graph nodes, vendor data, extension points, conventions. Generated from the codebase, not hand-written |

If you only read one thing, read **`04_TECHNICAL_BRIEF.md`** — the PDF is the human-facing
explanation, the brief is the engineering handoff.

---

## The three facts that matter most

**1. The physics is deterministic Python; no LLM touches any number.**
Every value in the ~190-page report comes from NumPy/SciPy engines and is reproducible by hand.
An LLM SDK is present for datasheet extraction and reference search only. Any larger framework
should preserve this separation — the outputs have to be defensible to a reviewing engineer.

**2. LangGraph is present but is a blueprint, not the runtime.**
`app/workflow/graph.py` has 38 nodes with genuine human-in-the-loop wait states, and it is
test-exercised — but `build_graph()` is called only from tests. The shipping product is the GUI
calling FastAPI endpoints directly, with the designer as orchestrator. This is worth knowing
before designing a bigger orchestration layer: the graph structure already exists and expresses
the intended flow, so the question is migration, not invention.

**3. The extension points you want already exist as named, empty hooks.**
`simulation_export` (17-line SIMPLIS netlist starter), `altium_export` (2-line stub returning
`"TBD"` components), `pcb_floorplanning_advisory`, `firmware_generation_advisory`, and a
`DCDCResult` placeholder in the EMI filter. They reserve the place in the flow but define no
useful contract. A larger design fills these in rather than adding parallel structures.

---

## What is worth reusing

- **The stage pattern.** Every design block follows *derive the requirement → screen the catalogue
  → the designer selects → re-verify on the actual part*. It keeps the reasoning non-circular and
  it is what makes the report defensible. A DC/DC engine should follow the same shape.
- **The state contract.** One Pydantic `DesignState` carried through every step, so any stage can
  read what earlier stages decided.
- **The report infrastructure.** Shared builders for equation boxes, tables, annotations,
  provenance and verdict rows — a new chapter is composition, not new plumbing.
- **The vendor-data pattern.** Excel workbooks parsed into normalised part records, each carrying
  the datasheet URL and a flag for which parameters had to be estimated.
- **The conventions in section 4 of the technical brief.** They were learned from real defects.

## What to be careful about

Section 5 of the technical brief lists the failure modes this project actually hit — silent
exception swallowing, chapters vanishing without an error, defaults masquerading as designer
input, validation that passes while the output is wrong. They are not hypothetical; each one
shipped at least once. A larger, more automated framework makes every one of them easier to hit
and harder to notice.
