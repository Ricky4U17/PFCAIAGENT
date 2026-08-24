# PFC Design Explorer — animation page

**Status: agreed in principle, NOT started.** Discussion 2026-08-23. No script changes made.
This file is the running to-do list; keep it current as scope is settled.

---

## What it is

A GUI-only page that animates the approved design so the designer can walk a reviewer through the
whole converter — topology, current flow, switching, duty, ripple, bus regulation, step-load
response, magnetics, thermals, control loops — using **our own calculated values**, live from the
currently approved state.

**It is not part of the report.** It is a presentation and review instrument.

## What it is not

- **Not a simulator.** Every drawn quantity is an engine value played back, never recomputed.
- **Not editable.** One-way, read-only. The only interaction is *selecting* what to view
  (operating point, scene, block). It cannot change, re-run, or write back any prior step.
- **Not reachable early.** Gated: all preceding pages/chapters must be complete first.
- **Not an import of the reference package.** See "Reference material" below.

---

## Constraints (settled with the designer)

| # | Constraint |
|---|---|
| C-1 | The `pfc-explorer` handoff package is **reference only**. Our own component, our attribute names, our data, our flow. Nothing imported verbatim. |
| C-2 | **Purely additive.** New page after the Input Filter page. Reads approved state; writes nothing, alters nothing. |
| C-3 | **Our design tokens only** — the `ui.tsx` palette and type scale, for uniformity with the rest of the GUI. |
| C-4 | Inductor and capacitor detail (B<sub>sat</sub>, ΔT, H(Oe), the graphs) are first-class content. |
| C-5 | Interactive Bode + loop block diagram included — **view-only**. |
| C-6 | The aggregation layer must be tool-neutral, because Ansys and SIMetrix/SIMPLIS export come later. |
| C-7 | **Live**: always animates the currently approved state. No snapshots. |
| C-8 | **Never recompute physics in the browser.** Render engine arrays. |
| C-9 | **Never draw unmodelled physics.** |
| C-10 | One asset copy, `public/` only. |
| C-11 | Read-only in both directions: the page cannot alter any previously calculated value. |
| C-12 | Page is **gated** until every prior chapter/page is complete. |
| C-13 | The FAN9672 controller application schematic is part of the animation. |

### Why C-8 and C-9 are hard rules

The reference component recomputes in the browser (`pfc-explorer.js:653-655`, `765-766`):

```js
var dd  = Math.min(.995, Math.max(.005, 1 - vin / vb));   // ideal CCM duty, no DCM concept
var dil = vin * dd / (p.L * 1e-6 * d.spec.fsw);           // ONE scalar L per operating point
```

Against our design that produces two visible contradictions with our own report:

- **Scalar `L`.** Our Table 7.1 L<sub>φ</sub> runs **134 → 154 µH across the line cycle**. A single
  L is precisely the flat-inductance divergence eliminated at C255 — reappearing inside the tool
  built to persuade a reviewer.
- **No DCM.** Chapter 7 reports **DCM_% = 6 % at 264 V<sub>AC</sub>**. The formula above draws
  clean CCM everywhere.

C-9 exists because an animation invites drawing what looks right. C253/B16 established that the
engine deliberately does **not** track the DCM ringing phase (it takes the settled node voltage as
the conservative choice). Drawing a ring we do not compute would put physics on screen that the
loss numbers do not contain.

---

## Architecture — one export, several consumers

Ansys, SIMPLIS and the animation all need the *same design state*, viewed differently. Build the
export once:

```
approved state (Ch1-10)  →  DESIGN STATE EXPORT  →  animation payload   (this page)
                                                 →  Ansys magnetics     (future page)
                                                 →  SIMetrix/SIMPLIS    (future page)
```

Design-state-shaped, not animation-shaped: chapter-scoped, canonical names, SI units, provenance
and an `approved` flag per section. Follow the discipline already established by
`canonical_parameters.json` + `registry.py` (one name, one unit, one meaning) rather than inventing
a second vocabulary.

**Future verification loop (designer's intent, not this page):** the agent generates importable
files, sets up the run in the real software, executes it, and compares the result against our
calculations. That makes the export a *verification contract*, not just a convenience — another
reason it must be neutral and provenance-carrying from the start.

---

## Scenes — three time scales plus a dashboard

Five orders of magnitude separate these; no single timeline shows them honestly.

| Scene | Time base | Shows |
|---|---|---|
| Switching detail | ~14 µs | one channel: FET on, inductor charging, FET off, diode conducting, the triangle |
| Line cycle | 8.33 ms | both channels 180° apart, duty sweep, ripple envelope, interleaving cancellation, DCM where it occurs, bus ripple at 2·f<sub>line</sub> |
| Load step | ~150 ms | V<sub>out</sub> sag and recovery from the real Step-12 transient |
| Steady state | — | thermal, loss budget, margins; a dashboard, not a timeline |

Operating-point picker applies across all scenes.

---

## Data — everything needed already exists

| Content | Source | New physics? |
|---|---|---|
| Conduction / switching / duty | `pfc_loss_model` per-angle: `duty`, `i_ch`, `i_on`, `i_off`, `di_pp`, `dcm_mask` | no |
| Line-cycle envelope | `waveforms_by_vin`: `t_ms, Vin, D, Iavg, H_Oe, Bdc, Bac_pk, Bmax, Ihf, Pcore, Pcu, Ptot` | no |
| Input ripple + interleaving | Ch2 §2.7, `emi_filter_design` (`i0 = 2·di·d/n_phases`) | no |
| Bus ripple | Ch5 step-15 + CapSim two-band model | no |
| Step-load response | `compute_step12_transient()` — returns real `t` and `waves` | no |
| Magnetics | `Bsat_at_Tcore`, `Bmax_T`, `Bmax_inner_FL_T`, `sat_margin_pct`, `H_Oe`, `T_core_C`, `dT_rise_C`, `DCR_25C/100C` | no |
| Semiconductor thermal | `Tj_FET`, `Tj_DIODE`, `Tj_BRIDGE_top`, `T_sink_main` | no |
| Control loops | Ch6 — current/voltage loop gain, crossover, PM | no |
| FAN9672 app schematic | `schematics.py::fan9672_application_schematic(v, is_high, _resolved)` | no |

**Nothing on the list requires new computation.** This is aggregation and rendering.

### Schematic reuse note

`fan9672_application_schematic` already renders from resolved design values, and feeds the report.
Prefer emitting **SVG with addressable element IDs** from that same generator so pins and nets can
highlight, rather than drawing a second schematic for the animation. One definition, two outputs —
a second drawing would drift from the report the way every duplicated source has.

---

## To-do

### Phase 0 — Design state export
- [ ] Inventory every quantity the page needs, per chapter, against canonical names/units
- [ ] Define export shape: chapter-scoped, SI, provenance + `approved` per section
- [ ] Read-only assembler over approved objects — no recomputation, no silent defaults
- [ ] Readiness model feeding the C-12 gate
- [ ] Schema + a test asserting the export agrees with the report for the same design

### Phase 1 — Page and scene framework
- [ ] New page after Input Filter; gate until prior chapters complete (C-12)
- [ ] Live fetch of the export (C-7)
- [ ] Scene model with independent time bases
- [ ] Operating-point picker across scenes
- [ ] Playback + presentation mode (full-screen, play/pause, step, captions)
- [ ] Our tokens (C-3); honour `prefers-reduced-motion`

### Phase 2 — Power stage
- [ ] Power-stage schematic with conduction highlighting from engine arrays
- [ ] Line-cycle scope from `waveforms_by_vin` — real arrays, not shaped curves
- [ ] Switching-period inset reconstructed from `i_on`/`i_off`/`duty`
- [ ] DCM shown only where the engine says it occurs; labelled; no invented ringing (C-9)
- [ ] Input-current ripple and interleaving cancellation
- [ ] Bus ripple at twice line frequency

### Phase 3 — Magnetics and capacitor (C-4)
- [ ] B(t) against `Bsat_at_Tcore`, live saturation margin
- [ ] Inner-bore vs mean-path both shown and labelled — **D3 is still an open decision**
- [ ] H(Oe) trace; core/copper loss split across the cycle
- [ ] Thermal: `T_core_C`, `dT_rise_C` against budget
- [ ] Capacitor: ripple current, ESR(T), `T_cap_C`, lifetime headroom

### Phase 4 — Control (C-5, C-13)
- [ ] FAN9672 application schematic, SVG with addressable IDs, live values
- [ ] Interactive Bode, current and voltage loop, crossover/PM markers — **view-only, static plot**
- [ ] Loop block diagram with live compensation values
- [ ] **Voltage-loop transient scene** — see "Transient scene" below
- [ ] **Current-loop scene, separate**, at switching timescale (settled)

#### Transient scene — settled design

What we have is better than the reference package: `compute_step12_transient` builds the closed-loop
output impedance `Z_cl` from the actual compensator and OTA gain and takes `signal.step()` of it, so
`waves[i].ll/.hl` are genuine ΔV<sub>out</sub>(t) in volts for all six transitions at both line
extremes, with per-row peak / % / `trec`. The reference uses a shaped `(t/τ)·e^(1−t/τ)` heuristic
instead. Use ours.

- [ ] All six transitions selectable (settled): 0→100, 0→50, 50→100, 100→0, 50→0, 100→50, LL and HL
- [ ] Three stacked, time-aligned panels: **load-current step** / **bus voltage** / **loop signal chain**
- [ ] Bus panel draws **three** things:
  1. composite trace `V_bus + ripple(2·f_line) + Δv(t)` — the scope view (the look the designer wants)
  2. **cycle-average overlay** `V_bus + Δv(t)` — free, it is exactly what Step 12 returns
  3. ±band measured **against the average, not the instantaneous trace**
- [ ] Loop signal chain: error and compensator output via `lsim` on the *same* `s11["comp"]` TF —
      same transfer functions, same solver, no second model. Duty and inner-loop response are
      deliberately excluded rather than approximated (C-9).
- [ ] Caption states the **small-signal basis** — `signal.step` on `Z_cl` is linear; a 0→100 % step
      is not. No slew limit, no error-amp clamp. Say so or the first reviewer question is "where is
      the clamp?"
- [ ] Narrative spine: **two-loop time-scale separation** — inner current loop f<sub>ci</sub> ≈ 8 kHz
      settles inside a switching period; outer voltage loop f<sub>cv</sub> ≈ 17 Hz takes ~150 ms
- [ ] Make explicit that **f<sub>cv</sub> ≪ 120 Hz is deliberate** — the loop is designed *not* to
      correct bus ripple, because chasing it would modulate the current reference and distort input
      current (Ch6 says this). Ripple sitting uncorrected is intended behaviour, labelled as such.

#### Transient scene — traps

| Trap | Why |
|---|---|
| **Band vs ripple** | `rec_band_pct = 1.0` → ±3.93 V, while bus ripple is 20 V pk-pk = **±10 V**. The reference draws an absolute ±band rectangle (`pfc-explorer.js:805-807`) *and* the composite trace (`:812`), so with its own numbers the bus sits outside tolerance 100 % of the time before any step. Resolved by measuring the band against the cycle-average (above). |
| **Bode marker sliding with time** | A frequency response has no time coordinate. Never animate a dot along the Bode curve during a transient. Show the Bode statically beside it and connect the two by annotation: f<sub>cv</sub> → recovery timescale, PM → ringing or clean settle. |
| **Ripple amplitude constant** | Ripple scales with load, so a 0→100 % step should show it growing. Supply `ripplePP_before` / `ripplePP_after` per transition from Ch5 so the change comes from the engine, not a browser formula. **OPEN — designer to confirm worth doing.** |
| **Units** | `trec` is milliseconds while everything else is SI seconds. |

### Phase 5 — Summary and polish
- [ ] Chapter block panels: fuse, MOV/GDT, NTC, EMI, bridge, L, Q, D, R_CS, C, controller
- [ ] DC-DC / load block as a labelled **placeholder** (settled: placeholder for now)
- [ ] Vendor IBM Plex woff2 locally — offline safety
- [ ] Accessibility: every animated value also present as text

### Future — separate page(s), not this one
- [ ] Ansys magnetics export + agent-driven run and comparison
- [ ] SIMetrix/SIMPLIS netlist export + agent-driven run and comparison
- [ ] FAN9673 vendor Excel as an **independent cross-check** of Ch6 compensation

---

## Reference material

`specs/Review/Animation/`

| File | Use |
|---|---|
| `Converter Physics Animation Guide (1).zip` | A Claude-generated handoff: `pfc-explorer.js` custom element, payload builder, JSON schema, example payload. **Reference only (C-1).** Good for scene structure, interaction model and accessibility approach. Its palette and its browser-side physics are both rejected. |
| `FAN967X BOOST PFC DESIGN TOOL (1).XLSX` | onsemi's vendor calculator for **our own controller family** — the codebase references FAN9672 78× and AND9925 37×. Sheet carries VRAMP, CVC1/CVC2, CIC1/CIC2, RLOAD, CBULK and evaluated loop transfer functions. Valuable as an **independent oracle for Chapter 6**, unrelated to the animation. Never a source of product values. |

---

## Settled 2026-08-23 (second round)

- **One operating point at a time** — no side-by-side comparison.
- **Gate requires Ch8–Ch10 complete too** (NTC / MOV / GDT), not just the power-stage chain.
- **Guided, scene-by-scene** presentation with captions — not free navigation.
- **All six load transitions selectable**, LL and HL.
- **Current loop gets its own scene** at switching timescale.
- **Bus panel superimposes 2·f_line ripple with the transient**, as in the reference — with the
  cycle-average overlay and band correction described under the transient scene.

## Open questions

- [ ] Ripple amplitude vs load during a step — supply `ripplePP_before` / `ripplePP_after` per
      transition from Ch5 so the amplitude change comes from the engine, or keep constant
      amplitude for simplicity? (Ripple scales with load: a 0→100 % step should show it growing
      from ~0 to the full ±10 V, which also makes the point that the ripple spec is a full-load
      spec. The reference package draws it at constant amplitude.)
