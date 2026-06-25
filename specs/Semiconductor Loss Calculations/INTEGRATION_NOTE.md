# PFC Semiconductor Loss & Thermal Model — Integration Note

*For the bigger script / its agent. This explains what the module does, its purpose, the data
contract, and exactly how to call it. Read sections 4, 6 and 8 before writing any integration code.*

---

## 1. Purpose

This is a **semiconductor loss and thermal estimator for a single-phase CCM boost PFC stage**.
Given an operating point and the datasheet parameters of the three power-semiconductor blocks, it
returns the **conduction, switching, Coss/recovery and gate losses**, the **junction temperatures**,
and **comparison + visualization** outputs. It is the back end that turns "this MOSFET / this diode /
this bridge at this operating point" into loss and temperature numbers the bigger tool can act on.

It is analytic (closed-form over the line cycle and a Vac sweep) — fast, deterministic, no SPICE,
no iteration. The bigger script supplies the operating point; this module never guesses it.

## 2. Scope and limits (read before relying on it)

**Handles**
- Single-phase **CCM boost PFC**, **1, 2, or 3-channel interleaved** (set `spec.nch`).
- MOSFET (Si super-junction or SiC), boost diode (SiC Schottky or Si), bridge rectifier
  (plain diode bridge or synchronous-bottom).
- Per-mechanism semiconductor losses, junction temps via a junction→case→sink→ambient network
  (optional Foster Zth for transient Tj ripple), design-vs-design comparison, four standard plots.

**Does NOT handle** (the bigger script must cover these elsewhere)
- **Non-boost topologies** (no totem-pole, bridgeless dual-boost, buck, LLC). The duty law
  `d = 1 − Vin/Vo` is structural.
- **Inductor and output-capacitor losses** — semiconductors only. The non-semiconductor remainder
  appears as `P_OTHER_implied` (computed from the supplied efficiency) but is not itself modeled.
- **Efficiency / power-factor prediction** — `eta` and `PF` are **inputs**, not outputs.

## 3. File stack (keep all four in one folder)

| File | Layer | Role |
|---|---|---|
| `pfc_loss_model_step3_local.py` | 1 — calculation | the physics + the operating-point engine |
| `pfc_component_intake.py` | intake/validation | parameter manifest, confirmation table, **validation gate** |
| `pfc_visualization_step4.py` | 3 — visualization | the four figures (no physics; calls the backend) |
| `pfc_semiconductor_advanced_review_notebook.ipynb` | 2 — orchestration | human review demo (not needed for headless integration) |

For programmatic integration you call only the first three modules.

## 4. The data contract — the `cfg` dictionary

Everything flows through one plain dict with **five required blocks**. A missing block raises
`KeyError`, and a missing *field inside* a block silently falls back to a built-in default — which is
why section 8's validation gate is mandatory.

```python
cfg = {
    "spec":    { ... operating point + topology ... },
    "mosfet":  { ... MOSFET datasheet + gate-drive ... },
    "diode":   { ... boost-diode datasheet ... },
    "bridge":  { ... rectifier datasheet ... },
    "thermal": { ... ambient / heatsink boundary ... },
}
```

### 4.1 Mapping the upstream operating point into `cfg`

The quantities the bigger script already computes map as follows. **Input voltage `Vac` is a call
argument, not a field** (so the same `cfg` can be swept across line voltages).

| Upstream quantity | Where it goes | Notes |
|---|---|---|
| Input voltage `Vac` | `simulate_point(vac, ...)` argument / `vac_list` | per evaluation point |
| Input power `Pin` | `spec.pin` (or `spec.pin_curve`) | sets `Po = eta·Pin` |
| Input current `Iin` (RMS) | `spec.iin_rms` (or `spec.iin_rms_curve`) | highest-priority current source |
| Inductance `L` | `spec.L` | **per channel**, in henries |
| Inductor ripple | `spec.pct_ripple` (fraction) or `spec.di_pp_peak` (A) | overrides `L` if given |
| Power factor `PF` | `spec.pf` (or `spec.pf_curve`) | |
| Efficiency `eta` | `spec.eta` (or `spec.eta_curve`) | fraction (0–1) |
| Output voltage `Vo` | `spec.vo` | |
| Channel count | `spec.nch` | must be 1, 2 or 3 |

**Line-current precedence** (the engine picks the first available):
`iin_rms` → `pin/(Vac·PF)` → `Po/(eta·Vac·PF)`.
Provide the scalar forms and drop the `*_curve` forms to avoid ambiguity.

### 4.2 Component parameters — datasheet vs application

The single source of truth for required fields is `pfc_component_intake.MANIFEST`; query it at runtime
rather than hard-coding a list. The split that matters for the agent:

- **`datasheet`** — the agent extracts these from the uploaded datasheet (typical values for nominal
  runs): MOSFET `rdson_25`, `rdson_tj`, `ciss`, `qgd`, `vth`, `vpl`, `qg`, `eoss_at_v`, `rth_jc`;
  diode/bridge `vf_curve`, SiC `qc` or Si `qrr`, `rth_jc`.
- **`application`** — NOT on the datasheet; the designer/board context must supply: gate-drive `vg`,
  gate resistor `rg` (or `rg_on`/`rg_off`), case-to-sink `rth_cs`, `n_parallel`, and the thermal
  boundary (`thermal.t_ambient`+`rth_sa`, or a regulated `thermal.t_sink_fixed`).
- **margins** — leave `k_rdson`, `k_esw`, `k_vf`, … at 1.0 for nominal; raise them for worst-case
  signoff.

Curves are `(x_points, y_points)` tuples/lists, e.g. `rdson_tj=[[25,125],[1.0,1.6]]`,
`eoss_at_v=[[100,400],[3e-6,11.7e-6]]`, `vf_curve=[[1,5,20],[0.9,1.1,1.5]]`.

## 5. Public API

**`pfc_loss_model_step3_local.py`**
- `design_from_dict(cfg) -> (sp, mos, dio, br, th)` — build engine objects from the dict.
- `simulate_point(vac, sp, mos, dio, br, th, return_waveforms=False) -> dict` — one operating point.
- `simulate_vac_sweep(cfg, vac_list=None, return_waveforms=False) -> list[dict]` — convenience sweep.
- `flatten_result(result) -> dict` — strip array payloads so a result is DataFrame/JSON-safe.

**`pfc_component_intake.py`**
- `confirmation_table(extracted, kind) -> DataFrame` — review table; missing required → `NOT AVAILABLE`.
- `missing_required(extracted, kind) -> list[str]` — required fields the agent still owes.
- `validate_design(cfg) -> (ok: bool, issues)` — **the gate**; `ok=False` means do not run.
- `MANIFEST` — the parameter dictionary (`kind` ∈ `mosfet`, `diode`, `bridge`, `system`).

**`pfc_visualization_step4.py`**
- `build_step4_visuals(cfg, selected_vac=90, vac_list=None, output_prefix="step4", show=False) -> {name: path}`
  — writes `waveforms`, `loss_breakdown`, `losses_vs_vac`, `temperatures_vs_vac` PNGs.

## 6. End-to-end integration (copy-paste)

```python
import importlib.util, sys

def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec); sys.modules[name] = mod
    spec.loader.exec_module(mod); return mod

backend = _load("pfc_backend", "pfc_loss_model_step3_local.py")
intake  = _load("pfc_intake",  "pfc_component_intake.py")
viz     = _load("pfc_viz",     "pfc_visualization_step4.py")

# --- 1. agent extracts from the datasheet; show the designer, get confirmation ---
extracted_mosfet = { "tech":"sic", "rdson_25":0.040, "rdson_tj":[[25,125],[1.0,1.4]],
                     "ciss":1100e-12, "qgd":22e-9, "vth":4.5, "vpl":9.0,
                     "qg":60e-9, "eoss_at_v":[[100,400],[2e-6,9e-6]], "rth_jc":0.5 }
print(intake.confirmation_table(extracted_mosfet, "mosfet"))   # NOT AVAILABLE flags gaps

# --- 2. assemble the confirmed design (datasheet values + application context + operating point) ---
cfg = {
    "spec": { "vo":400, "fsw":65e3, "fline":60, "nch":2, "L":250e-6,
              "eta":0.97, "pf":0.99, "pin":2200.0 },          # upstream operating point
    "mosfet": { **extracted_mosfet, "vg":15.0, "rg":4.7, "rth_cs":0.3 },   # + application inputs
    "diode":  { "is_sic":True, "vf_curve":[[1,5,20],[0.9,1.1,1.5]], "qc":18e-9,
                "rth_jc":1.0, "rth_cs":0.3 },
    "bridge": { "topology":"diode", "vf_curve":[[1,10,25],[0.8,1.0,1.2]],
                "n_parallel":1, "rth_jc":1.2, "rth_cs":0.3 },
    "thermal":{ "t_ambient":45.0, "rth_sa":0.3 },
}

# --- 3. GATE: never calculate on an incomplete design ---
ok, issues = intake.validate_design(cfg)
if not ok:
    raise ValueError(f"Design incomplete — refusing to run:\n{issues}")

# --- 4. calculate (single point or a sweep) ---
result = backend.simulate_point(230.0, *backend.design_from_dict(cfg))
rows   = [backend.flatten_result(r)
          for r in backend.simulate_vac_sweep(cfg, vac_list=[90,115,180,230,265])]

# --- 5. visuals (optional) ---
files = viz.build_step4_visuals(cfg, selected_vac=90,
                                vac_list=[90,115,180,230,265], output_prefix="run1")
```

## 7. Reading the result dict

Per-point keys (all scalars; safe after `flatten_result`):

- **Losses [W]:** `P_FET_total` (`P_FET_cond`, `P_FET_sw`, `P_FET_coss`, `P_FET_rr`, `P_FET_leak`),
  `P_DIODE_total` (`P_D_cond`, `P_D_sw`), `P_BRIDGE_total` (`P_BRIDGE_top`, `P_BRIDGE_bottom`),
  `P_gate_driver`, `P_SEMI_total`.
- **System cross-check [W]:** `P_SYSTEM_total` = `Po·(1−eta)/eta`; `P_OTHER_implied` =
  system − semi = the inductor + cap + control remainder (the bigger script's other budgets land here).
- **Temperatures [°C]:** `Tj_FET`, `Tj_DIODE`, `Tj_BRIDGE_top`, `Tj_BRIDGE_bottom`,
  `T_sink_main`, `T_sink_bridge`. With a Foster `zth_foster` you also get `Tj_*_peak` / `Tj_*_ripple`.
- **Operating-point echo:** `Vac`, `Po`, `Pin`, `Iin_rms`, `Ipk_ch`, `eta_in_%`, `PF_in`,
  `DCM_%`, `L_eff_uH`, `ripple_pk_%`, `Vo_ripple_pp`.

With `return_waveforms=True` the result also carries a `"waveforms"` dict of per-line-angle arrays
(`vin`, `duty`, `i_ch`, `i_in`, `i_on`, `i_off`, `di_pp`, `dcm_mask`, and total instantaneous device
powers). `flatten_result` removes it.

## 8. Hard rules (the integration will be wrong if you skip these)

1. **Always call `validate_design(cfg)` and stop on `ok=False`.** Unset required fields do not error —
   they inherit built-in defaults and produce plausible-but-wrong numbers. The gate is the only thing
   preventing that. Treat `ok=False` as a hard failure, not a warning.
2. **`L` is per-channel inductance.** For interleaved designs, pass the single-channel value.
3. **`Vac` is a call argument, not a `spec` field.** Sweep it by passing different `vac`/`vac_list`.
4. **Supply scalars, drop curves, for a single operating point.** Mixing `pin` and `po_curve`, etc.,
   is resolved by the precedence rules but is best avoided — hand in exactly one consistent set.
5. **`nch` ∈ {1, 2, 3}.** Other values are rejected by the gate.
6. **`eta`/`PF` are inputs.** Do not expect this module to report a predicted efficiency; it reports the
   semiconductor share of the loss you implied by the efficiency you supplied.
7. **Typical values for nominal, `k_*` multipliers for worst case.** Don't mix max-rated datasheet
   numbers into a nominal run.

## 9. One-line summary for the agent

> Build a five-block `cfg` dict (operating point in `spec`, three confirmed component blocks, a
> `thermal` boundary), call `intake.validate_design(cfg)` and abort if it fails, then
> `backend.simulate_point(vac, *backend.design_from_dict(cfg))` for losses + temperatures, and
> optionally `viz.build_step4_visuals(cfg, ...)` for figures. It models boost-PFC semiconductors only;
> inductor/cap and efficiency come from your side.
