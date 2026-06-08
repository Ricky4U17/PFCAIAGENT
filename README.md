# PFC AI Agent — 2-Phase Interleaved Boost CCM

A full-stack engineering design tool for 2-phase interleaved boost CCM power factor
correction. Combines a FastAPI backend with a React frontend through 5 Mode A HITL
gates and an 8-step Mode B engineering pipeline including full magnetic design.

## Quick start (3 commands)

```bash
git clone <your-repo-url> pfc-ai-agent    # or unzip the archive
cd pfc-ai-agent
./start.sh                                 # installs deps + starts both servers
```

Then open **http://localhost:5173** in your browser.

---

## Prerequisites

| Tool | Minimum version | Check |
|------|-----------------|-------|
| Python | 3.10+ | `python3 --version` |
| Node.js | 18+ | `node --version` |
| npm | 9+ | `npm --version` |

---

## Setup (step by step)

### 1 — API key

The MagneticsDB PDF extraction feature uses Claude. Set your Anthropic API key:

```bash
export ANTHROPIC_API_KEY="sk-ant-..."          # Mac / Linux
set ANTHROPIC_API_KEY=sk-ant-...               # Windows CMD
$env:ANTHROPIC_API_KEY="sk-ant-..."            # Windows PowerShell
```

All other features (Mode A, Steps 1–8, magnetic design) work without an API key.

### 2 — Backend (FastAPI)

```bash
cd backend
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Backend runs at **http://localhost:8000**
API docs: **http://localhost:8000/docs**

### 3 — Frontend (React)

In a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Frontend runs at **http://localhost:5173**

---

## One-shot startup scripts

**Mac / Linux:**
```bash
chmod +x start.sh
./start.sh
```

**Windows:**
```bat
start.bat
```

Both scripts install dependencies and launch both servers. Press `Ctrl+C` to stop.

---

## API endpoints (24 total)

| Tag | Count | Routes |
|-----|-------|--------|
| Mode A HITL | 5 | `/mode-a/start`, `/approve-topology`, `/approve-controller`, `/approve-channels`, `/submit-mini-intake` |
| Mode B pipeline | 8 | `/mode-b/generate-report`, `/step6-magnetic-design`, `/step7/*` (5 routes), `/step8/time-domain` |
| MagneticsDB | 10 | `/magnetics/status`, `/list`, `/rank`, `/add-custom`, `/commit-pending`, `/extract-pdf`, `/reload`, `/validate`, `/template/{type}`, `/pending/{key}` |

Full interactive docs: http://localhost:8000/docs

---

## Data files (all bundled, no download needed)

```
backend/data/
├── magnetic_materials/
│   ├── ferroxcube/     — 10 ferrite grades (3C90–3C98) + 46 cores (ETD/EE/EC/RM/PQ)
│   ├── tdk/            — 8 ferrite grades (N27–PC95) + 25 cores (ETD/EE/RM/PQ)
│   └── magnetics_inc/  — 14 powder materials (KoolMu/MPP/EDGE/XFlux/HiFlux) + 48 toroids
└── wire/
    ├── litz_catalog.csv  — 59 Litz wire entries (TRW + Rupalit + TIW)
    └── awg_table.csv     — 14 solid wire gauges (AWG 4–30)
```

---

## Adding new magnetic materials

**Option 1 — Edit JSON directly:**
```bash
# Add new grade file
cp backend/data/magnetic_materials/ferroxcube/3C97.json \
   backend/data/magnetic_materials/ferroxcube/3C99.json
# Edit 3C99.json with datasheet values, then:
curl -X POST http://localhost:8000/magnetics/reload
```

**Option 2 — Manual entry via API:**
```bash
# Get blank template
curl http://localhost:8000/magnetics/template/ferrite > new_grade.json
# Edit new_grade.json, then POST it:
curl -X POST http://localhost:8000/magnetics/add-custom \
  -H "Content-Type: application/json" \
  -d '{"material_data": <contents of new_grade.json>, "commit": false}'
```

**Option 3 — PDF extraction (requires API key):**
```bash
# Encode your PDF
B64=$(base64 -i ferroxcube_3C99.pdf)
curl -X POST http://localhost:8000/magnetics/extract-pdf \
  -H "Content-Type: application/json" \
  -d "{\"pdf_base64\": \"$B64\", \"supplier_hint\": \"Ferroxcube\", \"grade_hint\": \"3C99\"}"
# Review flagged fields, then commit
curl -X POST http://localhost:8000/magnetics/commit-pending \
  -d '{"pending_key": "pending:ferroxcube_3C99"}'
```

**Validate all materials:**
```bash
curl -X POST http://localhost:8000/magnetics/validate
# returns {"valid": true, "error_count": 0, "errors": []}
```

---

## Running tests

```bash
cd backend
source venv/bin/activate
python -m pytest tests/test_regression.py app/magnetics/tests/ -v
# Expected: 99 passed
```

---

## Project structure

```
pfc-ai-agent/
├── README.md
├── start.sh / start.bat
├── backend/
│   ├── requirements.txt
│   ├── app/
│   │   ├── main.py                       — FastAPI router (696L, 24 endpoints)
│   │   ├── magnetics/
│   │   │   ├── db.py                     — MagneticsDB guardian (626L)
│   │   │   ├── schema.py                 — JSON schema + validators (236L)
│   │   │   ├── extractor.py              — PDF extraction via Claude API (365L)
│   │   │   └── tools/validate.py         — CLI validator
│   │   ├── mode_b/
│   │   │   ├── generate_report.py        — Steps 1–5 PDF engine (749L)
│   │   │   ├── magnetic_design.py        — Step 6 quick sizing (189L)
│   │   │   ├── step7_magnetic_calc.py    — Step 7 full design · Step 13 (610L)
│   │   │   ├── step8_time_domain.py      — Step 8 Pcore(t) · Step 14 (261L)
│   │   │   └── registry.py               — 25-step pipeline registry (376L)
│   │   └── intake/, agents/, workflow/   — Mode A pipeline
│   ├── data/                             — All material JSON + CSV catalogs
│   └── tests/                            — 99 tests (regression + MagneticsDB)
└── frontend/
    ├── package.json
    ├── vite.config.ts                    — Proxy to backend
    └── src/
        ├── App.tsx                       — 9-stage state machine (238L)
        ├── api/client.ts                 — All 25 API call exports (116L)
        └── components/
            ├── IntakeForm.tsx            — Gate 1: 27 fields (307L)
            ├── TopologyHITL.tsx          — Gate 2 (133L)
            ├── ControllerHITL.tsx        — Gate 3 (131L)
            ├── ChannelSelect.tsx         — Gate 4 + L formula (183L)
            ├── MiniIntakeGate.tsx        — Gate 5 + fsw/ripple (208L)
            ├── DonePanel.tsx             — 25-step sequence (185L)
            ├── Step7Wizard.tsx           — Step 7+8 magnetic wizard (800L)
            ├── Stepper.tsx, ui.tsx       — Shared components
```

---

## Reference design parameters

The tool is validated against a reference 2-phase interleaved CCM PFC design:

| Parameter | Value |
|-----------|-------|
| Pout high line | 3600 W |
| Pout low line | 1700 W |
| Vout | 393 Vdc |
| Vin range | 90–264 Vrms |
| fsw | 70 kHz |
| N phases | 2 |
| Ripple ratio r | 0.095 |
| L calculated | 238.21 µH → selected 240 µH |
| Reference core | Magnetics EDGE 60µ, 3-stack × N=50 turns |
| FFcu | 33.5% (ref 32.9%) |
| ΔT | 34.5°C |

---

## Troubleshooting

**Backend won't start:**
```bash
cd backend && pip install -r requirements.txt
# If scipy fails on Apple Silicon:
pip install scipy --pre --extra-index-url https://pypi.anaconda.org/scipy-wheels-nightly/simple
```

**Frontend can't reach backend:**
- Make sure backend is running on port 8000 before starting frontend
- Check `frontend/vite.config.ts` has the correct proxy entries

**PDF extraction fails:**
- Set `ANTHROPIC_API_KEY` environment variable
- All other features work without the key

**Tests fail:**
```bash
cd backend && python -m pytest tests/ -v --tb=short 2>&1 | head -50
```

---

## License
For internal use. Engineering calculations validated against reference Step 13/14 design.
