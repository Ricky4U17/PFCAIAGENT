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
- **No DCM.** The formula above draws clean CCM everywhere, while this design genuinely runs
  discontinuous near the zero crossings at high line — **22.2 %** of the half cycle at 264 V<sub>AC</sub>
  on the magnetics engine's basis (Chapter 7's loss engine says 29.0 %; they disagree, which is
  PENDING B23, scheduled straight after this work).

  *Correction (C259):* this paragraph previously cited "6 % at 264 Vac". That figure came from a
  measurement taken with the reference parts and **no approved inductor**, so it ran on a flat
  235 µH — the very configuration C255 exists to prevent. With the as-built inductance the same
  engine reports 29 %. The argument was right; the number was from the wrong run.

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

### Phase 0 — Design state export  `IN PROGRESS`
- [x] Inventory every quantity the page needs, per chapter, against canonical names/units
- [x] Define export shape: chapter-scoped, provenance + `approved` per section
- [x] Read-only assembler over approved objects — no recomputation, no silent defaults
- [x] Readiness model feeding the C-12 gate
- [x] Test asserting the export agrees with the **rendered** report for the same design
- [ ] JSON Schema file (deferred — the shape should settle against a real consumer first)
- [ ] Per-scene arrays (waveforms, transient traces) — deliberately **not** Phase 0, see below

**Delivered:** `backend/app/mode_b/design_state.py` (new), `POST /mode-b/design-state`
(20 added lines in `main.py`, **0 deletions**), `backend/tests/test_design_state_export.py`
(11 tests).

**Input is the same shape the report takes** (`_DocReportReq`), deliberately: the GUI already
assembles that payload on the Input Filter page, and it lets export-vs-report be compared from one
fixture.

**Verified:** L across the sweep exports as `133.5 145.5 150.1 154.3 130.3 137.4 142.5 144.9
150.4 µH` and matches the rendered Table 7.1 cell for cell — the anti-C255 property holds by
construction rather than by care.

**Three rules, enforced by tests** — see the module docstring:
1. *No recomputation.* A structural test fails the build if `design_state.py` ever imports an
   engine or a report builder, because the next person would reasonably call one to "just derive"
   a missing value.
2. *No silent defaults.* A missing input yields `approved: false` and an absent section. `{}` is
   not an approval — that is what the GUI sends for a chapter the designer has not reached.
3. *Values keep their source names and units.* Renaming 109 inductor fields into a new vocabulary
   would introduce one transcription bug per field with nothing to catch it. Neutrality here is
   structural — chapter sections, readiness, provenance — not a second naming scheme. The
   canonical mapping belongs in the Ansys/SIMPLIS adapters, where the target tool defines it.

**Why arrays are not in Phase 0.** Including them would mean calling engines, which is rule 1, and
the transient alone is 40 000 points — decimation is a per-scene presentation decision. Each scene
attaches the arrays it needs in its own phase, from the one engine that owns them.

### Phase 1 — Page and scene framework  `DONE at C257`
- [x] New page after Input Filter; gate until prior chapters complete (C-12)
- [x] Live fetch of the export (C-7)
- [x] Scene model with independent time bases
- [x] Operating-point picker across scenes (one at a time, as settled)
- [x] Playback: play/pause, scrub, guided prev/next scene with captions
- [x] Our tokens (C-3); honour `prefers-reduced-motion`
- [ ] Full-screen presentation mode — deferred to Phase 5 with the rest of the polish

**Delivered:** `frontend/src/components/DesignExplorer.tsx` (new), `designState()` in `client.ts`,
`backend/tests/test_design_explorer_is_read_only.py` (6 guards). Existing files: **+65 / −3**, and
all three "deletions" are the same line re-emitted with one item appended.

**A React page, not an iframed asset.** `control_design.html` lives in `public/` and cost two
rounds of "fixed" that never reached the browser because a second copy existed (C244). A React page
on our `ui.tsx` primitives has no duplicate-asset failure mode and satisfies C-3 by construction —
there is no second palette to drift from. C-10 therefore does not apply to this page.

**The gate is a first-class state.** `readiness.gate === 'blocked'` renders a panel naming each
unapproved chapter and says on screen that it will not substitute nominals.

**Six guards, each proven to bite** (`test_design_explorer_is_read_only.py`) — only `designState`
may be called; no duty-from-voltage-ratio, no ripple-from-L-and-fsw, no `Math.sin/cos` synthesising
a waveform; no raw fetch, mutating verb, approve/save callback or assignment into an approved
object; tokens only, no hex, no CDN font; gate consulted before any scene draws; page registered
directly after `inputfilter`. Verified by reintroducing all five violation shapes against a scratch
copy — all caught, page restored byte-identical.

*Note:* the first write-back guard fired on the words "live fetch" in a **comment**. The
behavioural guards now strip comments before scanning; the token/CDN guard still reads raw source
on purpose. A guard that cries wolf gets suppressed — see the stale page-bound in E2.

### Phase 2 — Power stage  `MOSTLY DONE at C258`
- [x] Power-stage schematic with conduction highlighting from engine arrays
- [x] Line-cycle scope from `waveforms_by_vin` — real arrays, not shaped curves
- [x] Switching-period inset built from the engine's `Iavg`, `dIpp` and `D`
- [x] **DCM shading — DONE at C259 via option (a).** The engine now exports the per-angle mask.
- [ ] Input-current ripple and interleaving cancellation
- [ ] Bus ripple at twice line frequency

**Delivered:** `design_state_waveforms.py` + `POST /mode-b/design-state/waveforms` (a *second*
module and endpoint, because `design_state.py` may not import an engine and this one must);
`DesignExplorerScenes.tsx`; `test_design_state_waveforms.py` (7 tests). Footprint on pre-existing
files: `main.py` +16/−0, `client.ts` +20/−0.

**One conversion, server-side.** The engine stores `Ihf = dIpp/(2√3)`; the module returns
`dIpp = 2√3·Ihf`, inverting the engine's own identity on its own per-angle value so `dIpp` inherits
the bias curve for free. Doing it in the browser would put a physics constant in the presentation
layer where nothing tests it.

#### The crest ripple and the worst ripple are different numbers

`points[].dIL_pp_A` is the ripple **at the line crest** — it matches the series at the crest to
0.02 % at all nine points, which is the identity proving arrays and scalars are one engine. But the
ripple peaks where `Vin·D` peaks, which at high line is nowhere near the crest:

| | crest ripple | worst in cycle | |
|---|---|---|---|
| 264 Vac | 1.77 A | **8.38 A at t = 1.55 ms** | 4.7× |
| 90 Vac | 9.21 A | 9.21 A at t = 4.14 ms | identical |

Both correct, different questions. An envelope drawn beside an unlabelled crest figure looks
exactly like a defect. The payload publishes both with their indices, the line scene marks where
the ripple actually peaks, and the test asserts the crest **identity** rather than a false equality.

#### DCM shading — the open decision

The engine detects DCM per angle (`Iavg < dIpp/2`, `step7_magnetic_calc` ~line 496) but only
**counts** it; no per-angle mask reaches the series. Two ways forward:

- **(a) Export the mask** — add `series_dcm` (and optionally `series_dIpp`) to
  `_half_cycle_averages` under the existing `return_series` flag. Additive, but it touches a
  working engine file, which the designer has ruled out for this work so far.
- **(b) Restate the criterion in the waveforms module** — one line, no engine change, but it
  creates a second place where "what counts as DCM" is defined. If the engine's criterion ever
  changed, the animation would silently disagree. This is precisely what the architecture exists
  to prevent.

Until it is decided, **no region is shaded**, `notes.dcm` in the payload says why, and
`test_no_per_angle_dcm_mask_is_published_yet` fails if a DCM key appears — forcing whoever adds it
to come and use it.

### Phase 3 — Magnetics and capacitor (C-4)  `DONE at C260`
- [x] B(t) against `Bsat_at_Tcore` with the saturation limit drawn
- [x] Inner-bore vs mean-path both marked and labelled — **D3 is still an open decision**
- [x] H(Oe) trace; core/copper loss split across the cycle
- [x] Capacitor: ripple current, ESR(T), `T_cap_C` against the part rating
- [ ] Lifetime headroom — Ch5 computes it, but not in `bank_loss_table`; needs its own read

**Delivered:** `MagneticsScene` + `CapacitorScene`; `build_capacitor_view()` calling Chapter 5s own
`bank_loss_table`, returned under `capacitor` on the waveforms endpoint; 6 new tests.

**No per-angle saturation margin is computed in the browser.** `sat_margin_pct` has a specific
engine definition, and the report quotes it on the inner-bore flux while the accept/reject gate
still runs on the mean path (**D3, undecided**). A margin derived per angle in the page would be a
third definition. The scene draws the B_sat line and marks BOTH flux bases; the gap shows the
headroom and the numbers come from the export, labelled.

**Measured live:** B_sat 1.434 T at the core temperature, mean-path 0.410 T, inner-bore 0.560 T —
the D3 gap visible on one plot. Capacitor worst case 61.6 °C against a 105 °C part.

**The capacitor view is gated on `selected_cap`,** and reports its absence rather than returning an
empty table: that gate is what silently dropped seven pages of Chapter 5 from a headless report
until the harness started attaching a part, and an empty panel reads as "no ripple" rather than
"no part chosen".

### Phase 4 — Control (C-5, C-13)
- [x] **FAN9672 application schematic — DONE at C262 (C-13).** Same generator as the report,
      `as_svg=True`, plus `build_fan9672_context()` as a single value builder pinned against
      the report's own copy by test.
- [~] Loop block diagram — the compensation values are exported (`loops.*.comp`: R_IC, C_IC1/2,
      f_z, f_p for the current loop; f_cv, g_mv, H_v, R1, R4, V_ramp for the voltage loop) but not
      yet drawn as a diagram
- [x] **Voltage-loop transient scene** — done at C261, composite built server-side
- [~] **Current-loop scene** — its Bode is in the control scene; a TIME-DOMAIN current-loop scene
      at switching timescale is still open (the engine returns no current-loop step response)

#### Transient scene — settled design

What we have is better than the reference package: `compute_step12_transient` builds the closed-loop
output impedance `Z_cl` from the actual compensator and OTA gain and takes `signal.step()` of it, so
`waves[i].ll/.hl` are genuine ΔV<sub>out</sub>(t) in volts for all six transitions at both line
extremes, with per-row peak / % / `trec`. The reference uses a shaped `(t/τ)·e^(1−t/τ)` heuristic
instead. Use ours.

- [x] All six transitions selectable (settled): 0→100, 0→50, 50→100, 100→0, 50→0, 100→50, LL and HL
- [x] Three stacked, time-aligned panels: **load-current step** / **bus voltage** / **loop signal chain**
- [x] Bus panel draws **three** things:
  1. composite trace `V_bus + ripple(2·f_line) + Δv(t)` — the scope view (the look the designer wants)
  2. **cycle-average overlay** `V_bus + Δv(t)` — free, it is exactly what Step 12 returns
  3. ±band measured **against the average, not the instantaneous trace**
- [x] Loop signal chain: error and compensator output via `lsim` on the *same* `s11["comp"]` TF —
      same transfer functions, same solver, no second model. Duty and inner-loop response are
      deliberately excluded rather than approximated (C-9).
- [x] Caption states the **small-signal basis** — `signal.step` on `Z_cl` is linear; a 0→100 % step
      is not. No slew limit, no error-amp clamp. Say so or the first reviewer question is "where is
      the clamp?"
- [x] Narrative spine: **two-loop time-scale separation** — inner current loop f<sub>ci</sub> ≈ 8 kHz
      settles inside a switching period; outer voltage loop f<sub>cv</sub> ≈ 17 Hz takes ~150 ms
- [x] Make explicit that **f<sub>cv</sub> ≪ 120 Hz is deliberate** — the loop is designed *not* to
      correct bus ripple, because chasing it would modulate the current reference and distort input
      current (Ch6 says this). Ripple sitting uncorrected is intended behaviour, labelled as such.

#### Transient scene — traps

| Trap | Why |
|---|---|
| **Band vs ripple** | `rec_band_pct = 1.0` → ±3.93 V, while bus ripple is 20 V pk-pk = **±10 V**. The reference draws an absolute ±band rectangle (`pfc-explorer.js:805-807`) *and* the composite trace (`:812`), so with its own numbers the bus sits outside tolerance 100 % of the time before any step. Resolved by measuring the band against the cycle-average (above). |
| **Bode marker sliding with time** | A frequency response has no time coordinate. Never animate a dot along the Bode curve during a transient. Show the Bode statically beside it and connect the two by annotation: f<sub>cv</sub> → recovery timescale, PM → ringing or clean settle. |
| **Ripple amplitude constant** | Ripple scales with load, so a 0→100 % step must show it growing — **settled, do it**. See "Ripple during a step" below. |
| **Cross-fading ripple over t_rec** | Would imply the voltage loop regulates ripple. It does not — see below. |
| **Units** | `trec` is milliseconds while everything else is SI seconds. |

#### Ripple during a step — settled 2026-08-23

**The ripple amplitude follows the LOAD, not the loop.** It is set by
`I_load / (2π·2f_line·C)` — a passive consequence of bulk capacitance — so when the load steps at
t = 0 the amplitude changes almost immediately, settling within roughly one line half-cycle
(~8.3 ms). The bus *average* is the slow part, recovering over ~150 ms under the voltage loop.

Two mechanisms on one trace, on deliberately different timescales:

| Quantity | Behaviour at t = 0 |
|---|---|
| ripple envelope | steps with the load, settled in ~1 line half-cycle |
| cycle-average | dips to Δv<sub>pk</sub>, recovers over t_rec |

- [ ] Export supplies `ripple_pp_before` and `ripple_pp_after` per transition per line condition
      (6 × 2 = 12 pairs), each computed by **Ch5's own model** at that load fraction — never a
      browser formula (C-8)
- [ ] Envelope transitions over ~one line half-cycle, **not** over t_rec
- [ ] **Ripple phase stays continuous** across the step — it is locked to the line, only the
      amplitude changes; a phase jump at t = 0 reads as an artefact
- [ ] At 0 % load the ripple is near zero but not exactly zero — take the value Ch5 gives, do not
      special-case it to zero

Rendered correctly this is one of the stronger moments in the scene: the ripple jumps at once while
the average crawls back, which shows *without narration* that the loop is not regulating ripple —
the same point the f<sub>cv</sub> ≪ 120 Hz annotation makes in words.

### Phase 5 — Summary and polish  `PARTLY DONE at C264`
- [x] **Steady-state dashboard** — loss budget and junction temperatures against their limits,
      from the same sweep the Results tab runs (`build_thermal_view`). Gate drive shown separately
      because it belongs in the budget but NOT in the thermal path.
- [x] **Ch1-10 summary blocks** — rendered from the export's own chapter sections; a chapter that
      is not approved says so rather than showing an empty card.
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

- **Ripple grows with load during a step** — engine-supplied endpoints from Ch5, envelope moving on
  the line half-cycle timescale while the average recovers on t_rec. See "Ripple during a step".

## Open questions

*None outstanding. Scope is settled; Phase 0 can be scoped for implementation when the designer is
ready.*
