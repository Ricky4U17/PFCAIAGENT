# Controller Reference Database

Local store of reference documents for analog PFC controllers, for a database/RAG agent to
consult during control-loop design (Step 16).

## Layout

```
backend/data/controllers/
├── manifest.json                     # machine-readable index (titles, types, what each doc is for)
├── README.md                         # this file
├── fan9672/                          # one folder per controller
│   ├── FAN9672-D.PDF                 # datasheet (primary)
│   ├── AN4165-D.PDF                  # interleaved CCM PFC design guideline (FAN9673 sibling, same method)
│   ├── AN5257.pdf                    # average-current-mode interleaved PFC control theory
│   ├── AND9925-D.PDF                 # FAN9672/9673 Tips and Tricks (R_CS Method-2, GMOD checks)
│   ├── FAN9672_Control_Loop_Design_Report_Rev2.1.doc   # worked design report (internal)
│   └── FAN9672_Control_Design_Tool_v4.html             # interactive design calculator (internal)
└── _common/                          # controller-agnostic theory, shared by all controllers
    └── control_loop_design/
        ├── slua079.pdf               # Average Current Mode Control (TI/Unitrode, Lloyd Dixon)
        ├── slup098.pdf               # Control Loop Design (TI Seminar 800, Topic 7)
        ├── slva662.pdf               # Type II/III Compensators (TI, op-amp & OTA)
        └── Practical-Feedback-Loop-Design-Buck.pdf   # Fairchild Power Seminar (Hangseok Choi)
```

## Conventions
- **One folder per controller**, named by lowercase part id (e.g. `fan9672`).
- Each controller folder may reference one or more shared collections under `_common/`
  (declared per controller in `manifest.json` as `common_collections`).
- `manifest.json` is the source of truth: doc number, type, title, publisher, page count,
  and a `use_for` hint per document. Add new docs there when dropping files in.

## To add another controller
1. `mkdir backend/data/controllers/<part_id>/` and copy its PDFs in.
2. Add a `controllers.<part_id>` entry to `manifest.json` with its `documents` list.

## Known gaps
- None outstanding (AND9925-D added 2026-06-16).

Source of the copied files: `specs/Controller/FAN9672 Reference Documents` and
`specs/Controller/Control Loop Design Reference documents`.
