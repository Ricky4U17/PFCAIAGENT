# Input Data Dictionary — Package Contract v1.0

Every field the adapter must supply, with **unit**, **basis**, **source in your pipeline**,
and **what happens if it's wrong/missing**. This is the anti-mixing document: the three
classic traps are *basis* (single-core vs stack), *units* (kHz/Oe/ohm), and *η vs η·PF*.

Legend — Req: R = required (hard error if missing), O = optional (analytic/neutral fallback),
T3 = real-world measured tier. "Single" basis = value for ONE core; engine multiplies by `stacks`.

## model.design
| Field | Unit | Req | Source | If wrong/missing |
|---|---|---|---|---|
| Vout | V | R | converter spec | error if missing/≤0; wrong → all duty/ripple wrong |
| fsw | **Hz** (not kHz) | R | converter spec | kHz-instead-of-Hz inflates ripple 1000× — instantly visible in B/loss |
| lineHz | Hz | R | converter spec | error if missing |
| nph | – | R | converter spec | per-phase currents wrong by ×nph |
| Prated, specLowLineMaxPct, specHighLineMaxPct | W, %, % | O* | converter spec | *required only if `operating.points` omitted, or for the browser load envelope |

## model.environment
| Field | Unit | Req | Source | If wrong/missing |
|---|---|---|---|---|
| Tamb_C | °C | R | spec worst ambient | error if missing |
| Thot_C | °C | O | spec hotspot limit | default 110 °C used for ΔT allowance |

## model.winding
| Field | Unit | Req | Source | If wrong/missing |
|---|---|---|---|---|
| N | turns | R | designer selection | error if <1 |
| stacks | cores | R | designer selection | error if <1; **this is the multiplier for all Single-basis geometry** |
| build_mm | mm | O | winding design | default 3.8 (MLT estimate only) |

## model.geometry — **BASIS: SINGLE CORE** (engine multiplies by `stacks`)
| Field | Unit | Basis | Req | Source | If wrong/missing |
|---|---|---|---|---|---|
| OD_mm / ID_mm | mm | – | R | core DB | error if missing or ID≥OD |
| HT_mm | mm | **Single** | R | core DB | stack-total here → MLT, SA, thermal all wrong |
| Ae_mm2 | mm² | **Single** | R | core DB | stack-total here → B low by ×stacks → false sat margin |
| Le_mm | mm | – (path length, stack-independent) | R | core DB | H, bias, retention wrong |
| Ve_mm3 (or Ve_cm3) | mm³ (cm³) | **Single** | R | core DB | core loss scales directly with this |
| Wa_mm2 | mm² | per core (window) | R | core DB | window-fit gate wrong |
| AL_nH | nH/T² | **Single, zero-bias** | R | core DB | L0 = AL·stacks·N²; stack-total → L ×stacks too high |
| AL_tol | fraction | – | O | core DB | default 0.08; sets the L-guarantee derate (analytic only) |

## model.material
| Field | Unit | Req | Source | If wrong/missing |
|---|---|---|---|---|
| name | – | O | material DB | label only |
| Bsat | T | R | material DB | sat-margin gate wrong |
| steinmetz.a/b/c | P[mW/cm³]=a·B[**T**]^b·f[**kHz**]^c | R | material DB | **f must be kHz**; Hz here → loss astronomically wrong |
| retention.k0/k1/p | %µ=1/(k0+k1·H[**Oe**]^p) | R | material DB | **H must be Oe** (1 Oe = 79.577 A/m) |
| lossMaxScale | – | O | material DB | default 1.286 (catalog max/typ band) |
| anchors.loss / anchors.bias | [B,f_kHz,P] / [[H_Oe,%µ]] | O (recommended) | datasheet | transcription check; fails verdict if coefficients mistyped |
| **measured.coreLoss** (T3) | `{steinmetz{a,b,c}, maxScale}` or `{points:[[B_T,f_kHz,P_mWcm3]×≥3]}` | O | bench/DB | provenance→measured/T3; >1.5× off catalog → **warning, never silent**; replaces catalog anchor |
| **measured.inductance** (T3) | `{H_Oe:[],L_uH:[]}` or `{I_A:[],L_uH:[]}` | O | bench/DB | provenance→measured/T3; **outranks FEA fields**; L₀ >25 % off analytic → warning |

## model.copper
| Field | Unit | Req | Source | If wrong/missing |
|---|---|---|---|---|
| wire.type | litz/magnet/solid | O | wire DB | unknown type → warning |
| wire.strands | – | R | wire DB | copper area, J, DCR wrong |
| wire.strandDia_mm | mm **bare Cu** | R | wire DB | served/insulated OD here → area overestimated |
| wire.parallel | – | O (1) | designer | total Cu = parallel·strands·A_strand |
| **measured.RdcTotal_20C / RdcPerMeter_20C** (T3) | **Ω** (not mΩ) | O | bench/DB | provenance→measured; >2× off geometry → **warning** (basis/unit suspect) |
| alphaCu / rho20_ohm_m | 1/K, Ω·m | O | constants | defaults 0.00393 / 1.724e-8 |

## model.cooling / model.maps
| Field | Unit | Req | Notes |
|---|---|---|---|
| cooling.mode, airflow_mps | –, m/s | O | natural default; airflow used only when forced |
| maps.etaByVin | **η·PF PRODUCT** per Vin | O* | *browser explorer needs it (or crestByVin). **Trap:** product, not η. `validate()` cross-checks vs points (>5 % → warning). Generate from the same points (see adapter). |

## operating / acceptance / fields
| Block | Req | Notes |
|---|---|---|
| operating.points `[{Vin,Pout,eta,PF}]` | R* | *or derivable from maps+Prated+spec %. η and PF **separate** here. |
| acceptance `{L_target_uH, sat_margin_min|Bmax_T, Binner_max_T, Ku_max, J_max, dT_max_K, FFcu_limit}` | O | **upstream-only**: omitted limit = not checked, reported "no upstream limit"; nothing invented. Bmax basis = mean-path B. |
| fields `{inductance, windingAC, thermal, flux}` | O | solved FEA/CFD ROM (T2). Precedence: **measured > fields > analytic**, per quantity, provenance stamped. |

## Provenance → tier (parity vocabulary, both sides)
`input→T0, analytic/computed→T1, fea→T2, measured→T3`. Quantities tracked: inductance,
windingAC, coreLoss, thermal, flux, copperRdc, window.
