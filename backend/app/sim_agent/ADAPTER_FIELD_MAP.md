# Adapter Field-Map — our pipeline → Simulation-Agent package

**Purpose.** The ONE place our data is translated into the engine's package contract
(`pfc_inductor_engine.schema()`). Agree this on paper first; `adapter.py` then just
implements it. Authoritative engine for design numbers stays **our** `step7_magnetic_calc.py`
(decision #1); the sim engine runs on **our physics** fed through `fields`/`measured`
(decision #3); Review page stays as-is, Sim Agent is a new downstream page (decision #2).

**Inputs the adapter receives** (already in our app state):
- `result` — the selected candidate `DesignResult` (single core the designer passed to Review).
- `confirmedState` — intake/topology/selection (same object ReviewMagnetics already reads).
- `OPS` — the 9-row operating matrix `[Vin, Pout, eta, PF, Iφ_rms]` (`DEFAULT_OPS` / Mode-A).
- `wire` — the selected wire dict.
- `db = get_db()` — MagneticsDB (material curves).

**The three traps, guarded explicitly below:** ① single-core vs stack BASIS,
② UNITS (Steinmetz f in kHz/B in T/H in Oe; mm/nH/Hz), ③ η vs η·PF.

---

## model.design
| package field | unit | source | conversion / note |
|---|---|---|---|
| `Vout` | V | `confirmedState.intake.application.output_bus_voltage_v` (fallback 393) | engine uses 393 internally too — keep consistent |
| `fsw` | **Hz** | `confirmedState.topology_specific_inputs.recommended_frequency_hz` | already Hz; do **not** ×1000 |
| `lineHz` | Hz | 60 (or `confirmedState…line_hz`) | confirm field name |
| `nph` | – | `confirmedState.selected_channels` (fallback 2) | integer |
| `Prated` | W | `application.output_power_w_high_line` | optional (only for browser map derivation) |
| `specLowLineMaxPct` / `specHighLineMaxPct` | % | from OPS Pout split (low=1700/high=3600 → 47.2 / 100) | optional |

## model.environment
| field | unit | source | note |
|---|---|---|---|
| `Tamb_C` | °C | `design_one_core(T_amb_C=…)` (default 50) | worst-case ambient |
| `Thot_C` | °C | `T_amb_C + dT_budget_C` (e.g. 50+60=110) | allowed hotspot |

## model.winding
| field | unit | source | note |
|---|---|---|---|
| `N` | turns | `result.N` | integer |
| `stacks` | – | `result.stacks` | integer ≥1 |
| `build_mm` | mm | `2 × result.bundle_OD` (our v10 MLT build) OR omit→3.8 | keep MLT parity with our engine |

## model.geometry — ⚠️ ALL PER SINGLE CORE
| field | unit | source (DesignResult) | conversion |
|---|---|---|---|
| `OD_mm` / `ID_mm` / `HT_mm` | mm | `OD_mm` / `ID_mm` / `HT_mm` | single core ✓ |
| `Ae_mm2` | mm² | `Ae_single_mm2` | **single** (NOT Ae_total) |
| `Le_mm` | mm | `Le_single_mm` | single |
| `Ve_mm3` | mm³ | `Ve_total_cm3 / stacks × 1000` | **÷stacks** then cm³→mm³ |
| `Wa_mm2` | mm² | `Wa_single_mm2` | single (bore window) |
| `AL_nH` | nH/T² | `AL_nom_nH` | single-core AL |
| `AL_tol` | frac | `AL_tol_pct / 100` (≈0.08) | |

## model.material — Bsat direct; Steinmetz/retention FITTED from our DB, then OVERRIDDEN
Our DB is a 2-D log-log loss **surface** + a bias **curve**; the engine's base model is a
single Steinmetz triple + `1/(k0+k1·H^p)`. So we **fit** the base (validation requires
numeric a,b,c and k0,k1,p) and then **override with our exact curves** via `fields`.

| field | unit | source | conversion / note |
|---|---|---|---|
| `name` | – | `result.material_key` | |
| `Bsat` | T | `db.get_Bsat(mat, T_core)` | at converged core temp |
| `steinmetz.a,b,c` | – | **fit** to `db.get_core_loss(mat,f,B,T100)` sampled on a (B,f) grid over the design's operating range; least-squares in log-space (reuse engine `_fit_steinmetz`). Engine wants **mW/cm³, B in T, f in kHz** — our `get_core_loss` returns **kW/m³ = mW/cm³** ✓ (sample at f in **kHz**) | fit error only affects the analytic fallback; exact loss comes from `measured.coreLoss.points` |
| `retention.k0,k1,p` | – | **fit** to `db.get_k_bias(mat,H)` sampled over H; or k0=0.01,k1,p fit | base only; exact bias via `fields.inductance` |
| `lossMaxScale` | – | 1.20 (our +20% band upper) | matches our `P_unc_hi` |
| `measured.coreLoss.points` | [[B_T,f_kHz,P_mWcm3]…] | sample `db.get_core_loss` ≥6 points spanning B,f | **T3 exact core loss** (engine refits to our DB) |

## model.copper
| field | unit | source (wire dict) | note |
|---|---|---|---|
| `wire.type` | – | `wire.type` ('litz'/'magnet'/'solid') | |
| `wire.strands` | – | `wire.strands` | per bundle |
| `wire.strandDia_mm` | mm | `wire.strand_dia_mm` | BARE copper dia |
| `wire.parallel` | – | `wire.n_parallel` | ≥1 |
| `wire.fillFactor` | – | `wire.bundle_fill_factor` or omit | |
| `measured.RdcPerMeter_20C` | Ω/m | `wire.R_per_m_20C_ohm` | our catalog R/m → engine cross-checks geometry |
| `RacRdc` | – | `result.Rac_Rdc` | our Dowell value (also overridden by fields.windingAC) |
| `alphaCu`,`rho20_ohm_m` | – | 0.00393 / 1.72e-8 | match our constants |

## operating.points — ⚠️ η and PF SEPARATE
`[{Vin, Pout, eta, PF}]` from each OPS row: `Vin=row[0], Pout=row[1], eta=row[2], PF=row[3]`.
`maps.etaByVin` (browser) = the **product** `round(eta*PF,4)` per Vin. validate() cross-checks.

## acceptance (upstream-only — omit = "no limit", never invent)
| field | source |
|---|---|
| `L_target_uH` | our `L_target_H × 1e6` |
| `sat_margin_min` | our sat-margin policy (e.g. 0.43) — confirm |
| `FFcu_limit` | `design_one_core(FFcu_limit=…)` (0.40) |
| `J_max` | our `J_target` band upper — confirm |
| `Binner_max_T` | optional; pass only if we set an inner-bore limit |

## fields — feed OUR physics exactly (T2), the heart of decision #3
| field | source | makes engine use |
|---|---|---|
| `inductance{H:[Oe], L_uH:[]}` | sample `db.get_k_bias(mat,H)` → `L=k(H)·L0_nom_uH` over H grid (0…H_worst×1.3) | **our exact DC-bias curve** (not the fitted formula) |
| `windingAC{freq_Hz:[fsw], RacOverRdc:[result.Rac_Rdc]}` | our Dowell/Bessel value | **our R_ac** (not the 1.15 stand-in) |
| `thermal{nodes{Rca_KperW,Rwa_KperW,Rcw_KperW}}` | `_two_node_thermal(...)` returns Rca,Rwa,Rcw | **our 2-node hotspot** |
| `flux{radial{r_mm:[ID/2], crowd:[result.crowd_axial]}}` | our crowd factor | our inner-bore crowding |

> Each `fields` block carries `provenance:"computed"` (it's our analytic, not FEA). If/when the
> FEA-gate agent produces real ROMs, it overwrites these with `provenance:"fea"` (T2) — no adapter change.

---

## Resolved source paths (verified against main.py run-sizing + DesignResult)
- `design.fsw` ← `state.topology_specific_inputs.recommended_frequency_hz` (||70000), **Hz**.
- `design.Vout` ← `state.intake.application.output_bus_voltage_v` (||393).
- `design.lineHz` ← not in state → **default 60** (no upstream field; safe constant).
- `design.nph` ← `state.selected_channels` (||2).
- `environment.Tamb_C` ← `state.intake.thermal.ambient_temp_c_max` (||50).
- `environment.Thot_C` ← `state.intake.thermal.hotspot_limit_c` (||110).
- `acceptance.L_target_uH` ← `tsi.confirmed_L_uH_sel` ?? `tsi.recommended_L_uH` ?? 240.
- `operating.points` ← rebuilt EXACTLY as run-sizing: `build_design_ops_table(Vin_lo, Vin_hi,
  Pout_lo, Pout_hi, Vout, fsw, r_input)` from `intake.application.{vin_rms_min/max,
  output_power_w_low_line/high_line}` and `tsi.default_crest_ripple_ratio` (||0.095).
  OPS columns = [Vin, Pout, eta, PF, Iφ_rms].
- `copper.wire`: from DesignResult — `n_strands`, `d_strand_mm`, `wire_OD_mm`, `Cu_area_mm2`,
  `R_per_m_20C`; **`parallel` derived** = round(Cu_area / (n_strands·π/4·d_strand²)); `type`
  passed by caller (designer's wire-type selection, default 'litz').

## Decisions (per "go with recommendations")
1. **Provenance badge** = `"computed"` for all our-DB-fed `fields` (honest: our analytic models,
   not bench/FEA). Core loss is fed via Steinmetz fit + `anchors.loss` (NOT `measured.points`), so
   `coreLoss` reads **T1/computed**, keeping badges truthful.
2. **Validation gate** = proceed + log on warnings (shadow mode); hard errors raise/return `{ok:false}`.
