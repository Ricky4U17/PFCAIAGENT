const BASE = import.meta.env.VITE_API_URL ?? ''

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`)
  if (!res.ok) { const t = await res.text(); throw new Error(`${res.status}: ${t}`) }
  return res.json() as Promise<T>
}
// A DOM node or React SyntheticEvent that leaks into a request body serialises to
// "Converting circular structure to JSON …" — a stack trace that says nothing about which control
// sent it. This happened for real: three buttons passed a handler bare to onClick, so React's click
// event arrived as the handler's optional `opts` argument and went straight into the payload.
// Fail early and name the offender instead.
function assertSerialisable(path: string, body: unknown): void {
  const bad = (v: unknown): string | null => {
    if (v === null || typeof v !== 'object') return null
    if (typeof Element !== 'undefined' && v instanceof Element) return 'a DOM element'
    if (typeof Event !== 'undefined' && v instanceof Event) return 'a DOM event'
    const o = v as Record<string, unknown>
    // React SyntheticEvent: not an Event instance, but always carries these two
    if ('nativeEvent' in o && '_reactName' in o) return 'a React synthetic event'
    return null
  }
  const seen = (body ?? {}) as Record<string, unknown>
  for (const [k, v] of Object.entries(seen)) {
    const why = bad(v)
    if (why) throw new Error(`${path}: field "${k}" is ${why}, not data. This usually means a click ` +
      `handler was passed bare to onClick (use onClick={() => fn()}), so React's event became its argument.`)
    if (v && typeof v === 'object') {
      for (const [k2, v2] of Object.entries(v as Record<string, unknown>)) {
        const why2 = bad(v2)
        if (why2) throw new Error(`${path}: field "${k}.${k2}" is ${why2}, not data. This usually means ` +
          `a click handler was passed bare to onClick (use onClick={() => fn()}).`)
      }
    }
  }
}

async function post<T>(path: string, body: unknown): Promise<T> {
  assertSerialisable(path, body)
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) { const t = await res.text(); throw new Error(`${res.status}: ${t}`) }
  return res.json() as Promise<T>
}

export interface Candidate {
  topology: string; mode: string; family: string
  base_score: number; bonus: number; penalty: number; final_score: number
  penalty_details: string[]
  mini_intake_defaults: MiniDefaults
}
export interface ModeScore {
  mode: string; base_score: number; penalty: number; final_score: number
  penalty_details: string[]; raw_scores: Record<string, number>
}
export interface MiniDefaults {
  switching_frequency_style: string
  recommended_frequency_hz: number | null
  recommended_frequency_range_hz: [number,number] | null
  ask_crest_ripple_ratio: boolean
  default_crest_ripple_ratio: number
  crest_ripple_ratio_guidance: string
}
export interface ControllerStrategy {
  recommended_controller_mode: string
  reasoning: string[]
  stated_control_preference?: string
}
export interface FullIntake {
  application?: Record<string,unknown>
  thermal?: Record<string,unknown>
  control?: Record<string,unknown>
  business?: Record<string,unknown>
  compliance?: Record<string,unknown>
  supply?: Record<string,unknown>
  [key: string]: unknown
}

export const api = {
  health: () => fetch(`${BASE}/health`).then(r => r.json()),

  start: (project_id: string, intake: unknown, project_name?: string) =>
    post<{status:string;ranking:Candidate[];mode_scores:ModeScore[];
          recommended_topology:string;recommended_mode:string;state:Record<string,unknown>}>
    // project_name is omitted entirely when blank, so the backend keeps its default.
    ('/mode-a/start', { project_id, intake, ...(project_name ? { project_name } : {}) }),

  approveTopology: (state: unknown, feedback: unknown) =>
    post<{status:string;selected_topology:string;selected_mode:string;
          controller_strategy:ControllerStrategy;state:Record<string,unknown>}>
    ('/mode-a/approve-topology', { state, feedback }),

  approveController: (state: unknown, feedback: unknown) =>
    post<{status:string;selected_controller_mode:string;is_interleaved?:boolean;
          selected_channels?:number;mini_intake_defaults?:MiniDefaults;
          validation_errors?:string[];state:Record<string,unknown>}>
    ('/mode-a/approve-controller', { state, feedback }),

  approveChannels: (state: unknown, feedback: unknown) =>
    post<{status:string;selected_channels:number;mini_intake_defaults:MiniDefaults;
          validation_errors:string[];state:Record<string,unknown>}>
    ('/mode-a/approve-channels', { state, feedback }),

  submitMiniIntake: (state: unknown, feedback: unknown) =>
    post<{status:string;validation_errors?:string[];mini_intake_defaults?:MiniDefaults;
          selected_topology?:string;selected_mode?:string;selected_channels?:number;
          selected_controller_mode?:string;topology_specific_inputs?:MiniDefaults;
          state:Record<string,unknown>}>
    ('/mode-a/submit-mini-intake', { state, feedback }),

  generateReport: (state: unknown): Promise<ArrayBuffer> =>
    fetch(`${BASE}/mode-b/generate-report`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ state }),
    }).then(async res => {
      if (!res.ok) { const t = await res.text(); throw new Error(`${res.status}: ${t}`) }
      return res.arrayBuffer()
    }),

  step6MagneticDesign: (state: unknown) =>
    post<{status:string;inputs:Record<string,unknown>;best:Record<string,unknown>|null;all_candidates:Record<string,unknown>[]}>
    ('/mode-b/step6-magnetic-design', { state }),
}

// ── Step 7: Magnetic Design HITL ─────────────────────────────────────────────
export const step7MaterialComparison = () =>
  get('/mode-b/step7/material-comparison')

export const step7Suppliers = (material_type: string) =>
  get(`/mode-b/step7/suppliers?material_type=${material_type}`)

export const step7PowderRanking = (req: {
  fsw_Hz: number; Bac_pk_T: number; T_operating_C: number
  Ipk_A: number; dIL_pp_A: number; Le_single_m: number; L_target_uH: number; mu?: number
}) => post('/mode-b/step7/powder-ranking', req)

export const step7GradeOptions = (req: {
  material_type: string; supplier: string
  fsw_Hz: number; Bac_pk_T: number; T_operating_C: number; topology: string
}) => post('/mode-b/step7/grade-options', req)

export const step7WireOptions = (req: {
  wire_type: string; IL_rms_A: number; IL_HF_rms_A?: number
  fsw_Hz: number; T_C: number; J_target: number; n_options: number
}) => post('/mode-b/step7/wire-options', req)

export const step7RunSizing = (req: {
  state: object; material_key: string; wire_designation: string
  max_height_mm: number; max_stacks: number; J_target: number; n_top: number
  FFcu_limit?: number; coated_only?: boolean; custom_core?: object | null
  mounting?: string; wire_type?: string; n_parallel?: number
  optimization_goal?: 'best_performance' | 'max_ffu' | 'min_height'
}) => post('/mode-b/step7/run-sizing', req)

// ── Step 8: Time-domain core-loss modeling ───────────────────────────────────
export const step8TimeDomain = (req: {
  state: object; approved_design: object; f_line_Hz: number
}) => post('/mode-b/step8/time-domain', req)

// ── Step 15: Vout Capacitor Calculation ──────────────────────────────────────
export const step15CapCalc = (req: {
  state: object
  t_hold_ms?: number
  V_min_holdup_V?: number
  ripple_pct?: number
  V_rating?: number
}) => post('/mode-b/step15/capacitor-calc', req)

// ── Step 15: Vout Capacitor Design (spec endpoints) ──────────────────────────
export const step15CapacitorDesign = (req: { state: object }) =>
  post('/mode-b/step15/capacitor-design', req)

export const step15VerifyConfig = (req: {
  state: object
  supplier: string
  series: string
  voltage_rating: number
  configuration: { value_uF: number; qty: number }[]
}) => post('/mode-b/step15/verify-configuration', req)

export const step15SeriesOptions = (supplier: string) =>
  get(`/mode-b/step15/series-options?supplier=${encodeURIComponent(supplier)}`)

export const step15CapValues = (supplier: string, series: string, voltage: number) =>
  get(`/mode-b/step15/cap-values?supplier=${encodeURIComponent(supplier)}&series=${encodeURIComponent(series)}&voltage_rating=${voltage}`)

// ── Step 15: HV Capacitor Database (real parts) ──────────────────────────────
export const step15HvcapFilterOptions = () =>
  get('/mode-b/step15/hvcap-filter-options')

export const step15HvcapFilterCaps = (req: {
  voltage_V?: number; op_temp?: string; lifetime?: string; tolerance?: string
  lead_spacing_mm?: number; height_max_mm?: number; diameter_max_mm?: number
}) => post('/mode-b/step15/hvcap-filter-caps', req)

export const step15CapLifetime = (req: {
  state: object; part_number: string; qty: number; Tamb_C?: number
}) => post('/mode-b/step15/cap-lifetime', req)
// temperature characterization of the selected cap (ESR / I_allow / Life Time Period / T_core
// at 0/20/25/T_op/85/T_rated °C)
export const step15CapTempSweep = (req: {
  state: object; part_number: string; qty: number; Tamb_C?: number
}) => post('/mode-b/step15/cap-temp-sweep', req)

// ── Controller reference database agent ──────────────────────────────────────
export interface RefPassage {
  rank: number; score: number
  controller: string | null; collection: string | null
  file: string; doc_no: string | null; title: string | null
  loc: string; citation: string; snippet: string
}
export interface RefQueryResult {
  question: string; controller: string | null; scope_pages: number
  passages: RefPassage[]; answer: string | null; used_llm: boolean
}
export const controllerDbQuery = (req: {
  question: string; controller?: string; k?: number; synthesize?: boolean
}) => post('/controller-db/query', req) as Promise<RefQueryResult>

export const step15HvcapCapTable = (req: {
  state: object; capacitance_uF: number; n_parallel?: number
  voltage_V?: number; op_temp?: string; lifetime?: string; tolerance?: string
  lead_spacing_mm?: number; height_max_mm?: number; diameter_max_mm?: number
  Tamb_C?: number   // operating ambient → vendor-implied ESR(T) + K(T) in the returned rows
}) => post('/mode-b/step15/hvcap-cap-table', req)

export const step15GenerateReport = (req: {
  state: object
  approved_design: object
  step15_result: object
  step16_params?: object | null
}): Promise<Blob> =>
  fetch(`${BASE}/mode-b/step15/generate-report`, {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify(req),
  }).then(async res => {
    if (!res.ok) { const t = await res.text(); throw new Error(`${res.status}: ${t}`) }
    return res.blob()
  })

// ── Documentation Agent (Phase 3) ────────────────────────────────────────────
export interface DocChapter {
  chapter:  number
  title:    string
  status:   'ready' | 'pending' | 'partial'
  sections: string[]
  missing:  string[]
  note:     string
}
export interface DocReportStatus {
  project_id?:       string
  topology?:         string
  mode?:             string
  channels?:         number
  ready_label:       string
  can_generate:      boolean
  chapters:          DocChapter[]
  ready_count:       number
  pending_count:     number
  missing_for_full:  string[]
}

export const docReportStatus = (req: {
  state:            Record<string, unknown>
  approved_design?: Record<string, unknown> | null
  step15_result?:   Record<string, unknown> | null
  step16_params?:   Record<string, unknown> | null
}): Promise<DocReportStatus & { status: string }> =>
  post('/mode-b/documentation/report-status', req)

export const docGenerateReport = (req: {
  state:            Record<string, unknown>
  approved_design?: Record<string, unknown> | null
  step15_result?:   Record<string, unknown> | null
  step16_params?:   Record<string, unknown> | null
  semiconductor?:   Record<string, unknown> | null
  input_protection?: Record<string, unknown> | null
  input_filter?:     Record<string, unknown> | null
}): Promise<Blob> =>
  fetch(`${BASE}/mode-b/documentation/generate-report`, {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify(req),
  }).then(async res => {
    if (!res.ok) { const t = await res.text(); throw new Error(`${res.status}: ${t}`) }
    return res.blob()
  })

// ── Design state export (PFC Design Explorer, Phase 0) ───────────────────────
/** Chapter-scoped projection of the approved design. Read-only: the endpoint computes nothing and
 *  the page must never write back — see specs/Improvements/ANIMATION_PLAN.md (C-2, C-11).
 *  Takes the SAME request shape as the combined report, so the Input Filter page's payload works
 *  unchanged and the export cannot drift from the document. */
export interface DesignStateReq {
  state:             Record<string, unknown>
  approved_design?:  Record<string, unknown> | null
  step15_result?:    Record<string, unknown> | null
  step16_params?:    Record<string, unknown> | null
  semiconductor?:    Record<string, unknown> | null
  input_protection?: Record<string, unknown> | null
  input_filter?:     Record<string, unknown> | null
}
export interface DesignStatePoint {
  vac_V: number; vin_pk_V: number | null
  L_full_nom_uH: number | null; L_req_uH: number | null; k_bias: number | null
  dIL_pp_A: number | null; dIin_pp_A: number | null; ripple_pct: number | null
  Ipk_line_A: number | null; Iavg_crest_A: number | null
  AT: number | null; H_Oe: number | null; D_crest: number | null; Bac_pk_T: number | null
  Irms_A: number | null; Ihf_rms_A: number | null
  Pcore_avg_W: number | null; Pcu_avg_W: number | null; Ptotal_avg_W: number | null
  [k: string]: unknown
}
export interface DesignState {
  schema_version: string
  meta:  Record<string, unknown>
  spec:  Record<string, number | string | null>
  readiness: {
    chapters: Record<string, { source: string; approved: boolean }>
    missing: string[]; complete: boolean; gate: 'open' | 'blocked'
  }
  points: DesignStatePoint[]
  chapters: Record<string, Record<string, unknown> | null>
}
export const designState = (req: DesignStateReq) =>
  post<DesignState>('/mode-b/design-state', req)

/** Per-Vin half-line-cycle series — the arrays the explorer draws. Same engine entry point the
 *  report's Section 4.6.2 uses, so the page and the document plot identical curves. */
export interface WaveSeries {
  t_ms: number[]; Vin: number[]; D: number[]; Iavg: number[]; Ihf: number[]; dIpp: number[]
  H_Oe: number[]; Bdc: number[]; Bac_pk: number[]; Bmax: number[]
  /** per-angle DCM flag from the MAGNETICS engine (C259). Not Chapter 7's DCM_% — the two
   *  engines disagree (22.2 % vs 29.0 % at 264 Vac); label the basis wherever this is drawn. */
  dcm: boolean[]
  Pcore: number[]; Pcu: number[]; Ptot: number[]
  summary: {
    i_crest: number; i_dIpp_max: number
    dIpp_at_crest_A: number; dIpp_cycle_max_A: number
    t_ms_at_dIpp_max: number | null; t_ms_at_crest: number | null
  }
}
export interface CapacitorView {
  available: boolean; reason: string | null
  n_caps?: number
  rows: Array<Record<string, number>>
  worst?: Record<string, number> | null
  notes?: Record<string, string>
}
export interface LoopView {
  name: string
  bode: Array<{ vac: number; pout: number; f: number[]; ogain: number[]; ophase: number[] }>
  points: Array<{ vac: number; pout: number; fco: number | null; pm: number | null }>
  comp?: Record<string, number>
}
export interface ControlView {
  available: boolean; reason?: string | null
  loops: Record<string, LoopView>
  transient?: {
    available: boolean; reason?: string
    vout?: number; band?: number; t?: number[]
    transitions?: Array<{ label: string; ll: number[]; hl: number[] }>
    rows?: Array<Record<string, unknown>>
    worst_ll?: Record<string, number> | null
    worst_hl?: Record<string, number> | null
    notes?: Record<string, string>
  }
}
export interface ThermalView {
  available: boolean; reason?: string | null
  rows: Array<Record<string, number>>
  worst?: Record<string, number> | null
  limits: { fet: number | null; diode: number | null; bridge: number | null }
  notes?: Record<string, string>
}
export interface DesignWaveforms {
  available: boolean; reason: string | null
  vins: string[]; series: Record<string, WaveSeries>
  n_points: number; notes?: Record<string, string>
  /** Chapter 5's own bank model, per operating point (C260). */
  capacitor?: CapacitorView
  /** Chapter 6's loops and step-load transient (C261). */
  control?: ControlView
  /** Chapter 7's sweep for the steady-state dashboard (C264). */
  thermal?: ThermalView
}
export interface SchematicSheet {
  label: string; svg: string; defaulted: string[]; n_values: number
}
export interface DesignSchematic {
  available: boolean; reason: string | null
  sheets: Record<string, SchematicSheet>
}
/** FAN9672 application schematic, both line ranges, from the SAME generator and value context the
 *  report uses — SVG rather than raster so the page can scale it (C-13). */
export const designStateSchematic = (req: DesignStateReq) =>
  post<DesignSchematic>('/mode-b/design-state/schematic', req)

export const designStateWaveforms = (req: DesignStateReq) =>
  post<DesignWaveforms>('/mode-b/design-state/waveforms', req)

// ── Control-loop design report (Steps 1–14 + Appendices A–E) ─────────────────
// Generates the full FAN9672 control-loop design report from designer specs.
// Any omitted input falls back to the verified calc-engine defaults.
export const controlReportDefaults = (): Promise<Record<string, Record<string, unknown>>> =>
  fetch(`${BASE}/mode-b/control-report/defaults`).then(r => r.json())

export const controlReport = (inputs: Record<string, unknown>): Promise<Blob> =>
  fetch(`${BASE}/mode-b/control-report`, {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify({ inputs }),
  }).then(async res => {
    if (!res.ok) { const t = await res.text(); throw new Error(`${res.status}: ${t}`) }
    return res.blob()
  })

export interface PowerPlantRow {
  vac: number; pout: number; eta_pct: number; pf: number
  vin_pk: number; duty: number; rload: number; line: string
}
// Control Design Screen 1 — canonical operating-point grid (eta/PF/Vin_pk/duty/R_LOAD).
export const controlPowerPlant = (p: {
  vin_min: number; vin_max: number; pout_lo: number; pout_hi: number; vout: number
}): Promise<{ rows: PowerPlantRow[] }> =>
  fetch(`${BASE}/mode-b/control/power-plant`, {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify(p),
  }).then(async res => {
    if (!res.ok) { const t = await res.text(); throw new Error(`${res.status}: ${t}`) }
    return res.json()
  })

// Control Design Screen 2 — controller-fixed components + designer selections.
export interface FixedComp { name: string; symbol: string; value: string; role: string }
export interface SelComp { key: string; name: string; symbol: string; role: string
  default_pf: number; r_assoc_ohm: number; options_pf: number[] }
export interface ControlComponents {
  fixed: FixedComp[]
  rcs: { min_mohm: number; max_mohm: number; recommended_mohm: number; options_mohm: number[]
         m1_ll_mohm: number; m1_hl_mohm: number; m2_lo_mohm?: number; m2_hi_mohm?: number; note: string }
  selectable: SelComp[]
  r_ls: { default_kohm: number; calc_kohm: number; options_kohm: number[]; role: string }
  // numeric Step-5 divider, for the embedded tool's readonly r1fb / r4fb fields
  divider?: { rfb1_ohm: number; rfb2_ohm: number; rfb1_unit_ohm: number; rfb1_count: number }
}
export const controlComponents = (inputs: Record<string, unknown>): Promise<ControlComponents> =>
  fetch(`${BASE}/mode-b/control/components`, {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify({ inputs }),
  }).then(async res => {
    if (!res.ok) { const t = await res.text(); throw new Error(`${res.status}: ${t}`) }
    return res.json()
  })

// Control Design Screen 3 — Fixed Coefficients / Internal Parameters (review).
export const controlCoefficients = (inputs: Record<string, unknown>): Promise<{ coefficients: string[][] }> =>
  fetch(`${BASE}/mode-b/control/coefficients`, {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify({ inputs }),
  }).then(async res => {
    if (!res.ok) { const t = await res.text(); throw new Error(`${res.status}: ${t}`) }
    return res.json()
  })

// ── Step 7: Generate combined report (Steps 1–14) ────────────────────────────
export const step7GenerateReport = (payload: {
  state:           Record<string, unknown>
  approved_design: Record<string, unknown>
}): Promise<Blob> =>
  fetch(`${BASE}/mode-b/generate-full-report`, {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify(payload),
  }).then(async res => {
    if (!res.ok) { const t = await res.text(); throw new Error(`${res.status}: ${t}`) }
    return res.blob()
  })

// ── Step 7: Simulation-Agent shadow cross-check (Phase 1) ─────────────────────
export interface SimCrossCheckRow {
  quantity: string; ours: string | number | null; sim: string | number | null
  delta_pct: number | null; band_pct: number; within: boolean | null
  note?: string
}
export interface SimCrossCheck {
  status: string; ok?: boolean; verdict?: string
  tiers?: Record<string, string>
  validation?: { ok: boolean; errors: string[]; warnings: string[] }
  statics?: Record<string, number>
  worst?: Record<string, unknown>
  crosscheck?: { rows: SimCrossCheckRow[]; all_within_band: boolean | null; n_checked: number }
  package?: Record<string, unknown>   // the exact package the engine used (Phase 2 viewer)
  errors?: string[]; warnings?: string[]
}
export const simulateCrossCheck = (
  state: Record<string, unknown>,
  approved_design: Record<string, unknown>,
  wire_type = 'litz',
): Promise<SimCrossCheck> =>
  post<SimCrossCheck>('/mode-b/step7/simulate', { state, approved_design, wire_type })

// ── Phase B: step7 view contract (single render payload for all screens) ──────
export interface ViewContract {
  scalars: Record<string, number | string | null>
  waveform: Record<string, number[]>   // t_ms, Vin, D, Iavg, H_Oe, Bdc, Bac_pk, Bmax, Ihf, Pcore, Pcu, Ptot
  waveforms_by_vin?: Record<string, Record<string, number[]>>  // per-Vin explorer waveforms
  sweep: Array<Record<string, number>>  // per-Vin: Vin, Icrest, Lfull, H_Oe, k_bias, Bac, Pcore, Pcu, Ptot
  L_vs_Vin: Array<Record<string, number>>
  acceptance?: {
    verdict: string; passed: boolean; reasons: string[]
    rows: Array<{ name: string; val: string; ok: boolean | null; limTxt: string }>
  }
  meta: { Vout_V: number; fsw_Hz: number; vin_design: number; source: string; vins?: number[] }
}
export const getViewContract = (
  state: Record<string, unknown>,
  approved_design: Record<string, unknown>,
): Promise<{ status: string; contract: ViewContract }> =>
  post<{ status: string; contract: ViewContract }>('/mode-b/step7/view-contract',
    { state, approved_design })

// ── Chapter 7 — Semiconductor loss & thermal ──────────────────────────────────
export interface SemiCalcResult {
  validation:  { ok: boolean; issues: Array<Record<string, unknown>> }
  consistency: { ok: boolean; issues: Array<Record<string, unknown>> } | null
  per_point:   Array<Record<string, number>>
  summary:     Record<string, number | boolean | Record<string, boolean>> | null
}
export interface SemiReqBody {
  design:  Record<string, number>
  mosfet:  Record<string, unknown>
  diode:   Record<string, unknown>
  bridge:  Record<string, unknown>
  thermal: Record<string, unknown>
  tj_limit?:       Record<string, number>
  selected_vac?:   number
  approved_design?: Record<string, unknown> | null   // inductor design → as-built L (match report)
}
export const semiconductorLibrary = () =>
  get<Record<string, Array<Record<string, unknown>>>>('/mode-b/semiconductor/library')
export interface DbRankResult {
  manufacturer: string; part_number: string; technology: string | null; package: string | null
  mounting: string | null; datasheet_url: string | null; v_rating: number | null; i_rating: number | null
  loss_W: number; loss_at_Vac?: number; tj_max_C: number; block: Record<string, unknown>
}
export const semiconductorDbOptions = (kind: string) =>
  get<Record<string, string[]>>(`/mode-b/semiconductor/database/${kind}/options`)
export const semiconductorDbRank = (kind: string,
  body: { design: Record<string, number>; criteria: Record<string, unknown>; top?: number; mode?: string
    // design context → screen loss equals the Results value for the selected part
    mosfet?: Record<string, unknown>; diode?: Record<string, unknown>; bridge?: Record<string, unknown>
    thermal?: Record<string, unknown>; approved_design?: Record<string, unknown> | null }) =>
  post<{ results: DbRankResult[] }>(`/mode-b/semiconductor/database/${kind}/rank`, body)
export interface DsExtract {
  block: Record<string, unknown>; found: string[]; missing: string[]
  manufacturer: string | null; part_number: string | null; raw_sample: string
}
export const semiconductorExtract = (kind: string, file: File): Promise<DsExtract> => {
  const fd = new FormData(); fd.append('kind', kind); fd.append('file', file)
  return fetch(`${BASE}/mode-b/semiconductor/database/extract`, { method: 'POST', body: fd })
    .then(async r => { if (!r.ok) { const t = await r.text(); throw new Error(`${r.status}: ${t}`) } return r.json() })
}
// ── datasheet-first part selection (M3) ──────────────────────────────────────
// Requirement first, then the designer supplies the datasheet, then the extracted values are
// reviewed and confirmed. No manufacturer part number is offered before an upload.
export interface DsRequirement {
  kind: string
  V_DSS_min?: number; I_D_min?: number            // MOSFET: blocking + peak drain current
  V_RRM_min?: number; I_F_AV_min?: number         // diode/bridge: blocking + AVERAGE forward current
  I_F_pk?: number                                 // diode: repetitive peak, not covered by I_F(AV)
  I_rect_avg?: number; I_per_package?: number     // bridge: rectified mean, and its share per package
  basis: Record<string, number>; statement: string; note: string
}
export interface DsReviewRow {
  key: string; label: string; unit: string
  value: number | string | null; display: string | null
  conditions: Record<string, number>
  entries: number
  all_entries: { value: number | null; min?: number | null; typ?: number | null; max?: number | null
                 conditions: Record<string, number>; provenance: string }[]
  supplied: boolean; source_kind: string; provenance: string
  required: boolean; is_curve: boolean; destination: string; description: string
  /** A curve the designer ACCEPTED off a plot, so the review step can show the whole basis of the
   *  calculation and not only its scalars. `is_curve` says the parameter is curve-SHAPED;
   *  `has_curve` says one has actually been confirmed for this part. */
  has_curve?: boolean
  curve_points?: number
  curve_source?: { figure?: string; page?: number; image?: string }
}
/** The C202 plausibility gate, run over an extracted or confirmed profile (M6). ADVISORY:
 *  `ok: true` means nothing looked wrong, not that the extraction is right. It never blocks. */
export interface DsPlausibility {
  ok: boolean; checked: number; advisory?: boolean; note?: string
  findings: PlausFinding[]
  record: Record<string, number>
}
export interface DsUpload {
  ok: boolean; reason?: string; part_number: string | null; device_class?: string
  plausibility?: DsPlausibility
  rows: DsReviewRow[]
  triage?: Record<string, unknown>
  cross_check?: { key: string; field: string; values: number[]; spread_pct: number; message: string }[]
  unresolved?: { symbol?: string; name?: string }[]
  tables_kept?: number; tables_rejected?: number
  stored?: { changed: boolean; sha256: string; note?: string }
  revision_diff?: { key: string; field: string; was: number | null; now: number | null }[]
  /** A SERIES datasheet covers several parts and bands the values that differ between them.
   *  `variant_required` means the document names more than one and none was chosen, so the banded
   *  rows are all still present — visible rather than silently resolved to one band. */
  variants?: string[]
  variant?: string | null
  variant_required?: boolean
}
export interface DsConfirm {
  ok: boolean; part_number: string
  device_class?: string          // what the block RESOLVED to — for a diode, read off the datasheet
  plausibility?: DsPlausibility
  rows: DsReviewRow[]
  block: Record<string, unknown>
  validation: { ok: boolean; defaulted: { key: string; message: string }[]
                disconnects: { message: string }[]; summary: Record<string, unknown> }
}
export const datasheetRequirements = (design: Record<string, unknown>, kind = 'mosfet') =>
  post<DsRequirement>('/mode-b/semiconductor/datasheet/requirements', { design, kind })
export const datasheetUpload = (kind: string, file: File, partNumber?: string,
                                deviceClass?: string): Promise<DsUpload> => {
  const fd = new FormData(); fd.append('kind', kind); fd.append('file', file)
  if (partNumber) fd.append('part_number', partNumber)
  // The class the part is EXTRACTED under: it selects the conduction-loss form and which
  // parameters are required, so changing it re-reads the datasheet rather than relabelling it.
  if (deviceClass) fd.append('device_class', deviceClass)
  return fetch(`${BASE}/mode-b/semiconductor/datasheet/upload`, { method: 'POST', body: fd })
    .then(async r => { if (!r.ok) { const t = await r.text(); throw new Error(`${r.status}: ${t}`) } return r.json() })
}
export const datasheetConfirm = (b: { part_number: string; kind: string
                                      device_class?: string
                                      edits?: Record<string, unknown>
                                      design?: Record<string, unknown> }) =>
  post<DsConfirm>('/mode-b/semiconductor/datasheet/confirm', b)
// ── M7: the plotted curves ───────────────────────────────────────────────────────────────────
// A proposal is only ever a proposal. It carries the axis titles the digitiser read, the
// calibration residual, and where the datasheet tabulates a point on those axes a cross-check
// against it — the table and the plot being independent renderings of one measurement.
export interface DsCurve {
  x: number[]; y: number[]
  color: number[]; n_points: number
  drawn_as?: string
  x_span: number[]; y_span: number[]
  /** Which temperature this trace is, once the order has been checked against the table. Null
   *  means the traces are in temperature order but which end is the hot one is not established. */
  T_j?: number | null
}
export interface DsAssignment {
  ok: boolean; verified: boolean
  by?: Record<string, number>
  order?: number[]
  rises_with_temperature?: boolean
  worst_anchor_error_pct?: number | null
  reason: string
}
export interface DsFigureProposal {
  key: string; page: number; frame: number[]
  caption: string
  axes: { x: string; y: string }
  x_scale: string; y_scale: string
  x_range: number[]; y_range: number[]
  residual: number
  per_temperature: boolean; swapped: boolean
  n_curves: number
  curves: DsCurve[]
  /** 'raster' when the figure was a bitmap traced against designer-supplied axes (B19). Absent on
   *  the vector path. `residual` is 0 for these — the axes were typed in, not fitted, so there is
   *  nothing to take a residual of and the cross-check is the only evidence. */
  source?: string
  calibration_source?: string
  /** `curve_index` is WHICH trace matched the tabulated point. On a figure whose traces are
   *  different quantities rather than one quantity at several conditions — C_iss / C_oss / C_rss
   *  share a plot — that index is the only thing on the page that says which trace is the one the
   *  key names, so it is shown against the trace rather than left in the note. */
  cross_check: { checked: boolean; agrees: boolean; error_pct?: number
                 curve_index?: number
                 expected?: number; got?: number; note: string }
  temperatures?: { T_j: number; label: string; anchor: number[] }[]
  assignment?: DsAssignment
}
export const datasheetFigures = (file: File, partNumber?: string) => {
  const fd = new FormData(); fd.append('file', file)
  if (partNumber) fd.append('part_number', partNumber)
  return fetch(`${BASE}/mode-b/semiconductor/datasheet/figures`, { method: 'POST', body: fd })
    .then(async r => { if (!r.ok) throw new Error(`${r.status}: ${await r.text()}`)
                       return r.json() as Promise<{ ok: boolean; proposals: DsFigureProposal[]
                                                    figures_seen: number; reason?: string }> })
}
/** A bitmap figure the vector digitiser cannot read (B19). Some vendors publish their curves as
 *  images with no vector paths, and on such a page even the tick labels are pixels — so the axis
 *  ranges are typed in by the designer, and the evidence is the cross-check against the part's own
 *  table, never a calibration residual (there is nothing to fit). */
export interface DsRasterCandidate {
  page: number; page_index: number; xref: number
  width: number; height: number
  rect: number[]
  frame_area_pct: number
  caption: string
}
export const datasheetRasterFigures = (file: File) => {
  const fd = new FormData(); fd.append('file', file)
  return fetch(`${BASE}/mode-b/semiconductor/datasheet/raster-figures`,
               { method: 'POST', body: fd })
    .then(async r => { if (!r.ok) throw new Error(`${r.status}: ${await r.text()}`)
                       return r.json() as Promise<{ ok: boolean; reason?: string
                                                    candidates: DsRasterCandidate[] }> })
}
/** Trace one bitmap figure against ranges the designer read off the printed plot. Returns an
 *  ORDINARY DsFigureProposal, so the Curves tab renders it and `acceptCurve` confirms it by the
 *  same road a vector curve takes. */
export const datasheetRasterDigitise = (
  file: File, b: { page: number; xref: number; key: string; part_number?: string
                   x_min: number; x_max: number; y_min: number; y_max: number
                   x_log?: boolean; y_log?: boolean; x_title?: string; y_title?: string }) => {
  const fd = new FormData(); fd.append('file', file)
  Object.entries(b).forEach(([k, v]) => { if (v !== undefined && v !== '') fd.append(k, String(v)) })
  return fetch(`${BASE}/mode-b/semiconductor/datasheet/raster-digitise`,
               { method: 'POST', body: fd })
    .then(async r => { if (!r.ok) throw new Error(`${r.status}: ${await r.text()}`)
                       return r.json() as Promise<{ ok: boolean; reason?: string
                                                    proposal: DsFigureProposal | null }> })
}
export const datasheetFigureImage = (file: File, page: number, frame: number[]) => {
  const fd = new FormData(); fd.append('file', file); fd.append('page', String(page))
  fd.append('x0', String(frame[0])); fd.append('y0', String(frame[1]))
  fd.append('x1', String(frame[2])); fd.append('y1', String(frame[3]))
  return fetch(`${BASE}/mode-b/semiconductor/datasheet/figure-image`, { method: 'POST', body: fd })
    .then(async r => { if (!r.ok) throw new Error(`${r.status}`); return r.blob() })
}
/** `caption`/`page`/`frame` are the curve's SOURCE, not decoration: the backend cites them and
 *  renders the plot image from the frame so Chapter 7 can show the figure the curve was read off. */
export const datasheetFigureConfirm = (b: { part_number: string; key: string
                                            curve: { x: number[]; y: number[]
                                                     caption?: string; page?: number
                                                     frame?: number[] }
                                            conditions?: Record<string, unknown> }) =>
  post<{ ok: boolean; key: string; n_points: number }>(
    '/mode-b/semiconductor/datasheet/figure-confirm', b)

export const datasheetPublish = (b: { part_number: string; published?: boolean }) =>
  post<{ part_number: string; published: boolean }>(
    '/mode-b/semiconductor/datasheet/publish', b)
export const datasheetDiscard = (b: { part_number: string }) =>
  post<{ part_number: string; discarded: boolean }>(
    '/mode-b/semiconductor/datasheet/discard', b)
/** Chapter 7 alone. The same builder the combined report calls, so the two cannot disagree. */
export const semiconductorReport = (b: SemiReqBody) =>
  fetch(`${BASE}/mode-b/semiconductor/report`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(b),
  }).then(async r => { if (!r.ok) throw new Error(`${r.status}: ${await r.text()}`); return r.blob() })

export const datasheetLibrary = () =>
  get<{ parts: { part_number: string; ready: boolean; sha256?: string
                 extracted_versions: number[]; confirmed_versions: number[] }[] }>(
    '/mode-b/semiconductor/datasheet/library')

// ── plausibility gate ────────────────────────────────────────────────────────
// Advisory sanity-check of a hand-entered or extracted part against physics and the vendor
// catalogues. It returns findings, never a rejection: `ok` means nothing looked wrong, NOT that
// the part is right — it cannot tell a correct value from a plausible wrong one.
export interface PlausFinding {
  rule: string; fields: string[]; message: string
  observed?: number | null; expected: string; severity: string
}
export interface PlausResult {
  kind: string; findings: PlausFinding[]; checked: number; ok: boolean; note?: string
}
export const plausibilityCheck = (kind: string, record: Record<string, unknown>) =>
  post<PlausResult>('/mode-b/plausibility/check', { kind, record })

export const semiconductorCalculate = (b: SemiReqBody) =>
  post<SemiCalcResult>('/mode-b/semiconductor/calculate', b)
export const semiconductorFigures = (b: SemiReqBody) =>
  post<{ figures: Record<string, string>; selected_vac: number }>('/mode-b/semiconductor/figures', b)

// ── input protection (MOV surge + NTC inrush) ────────────────────────────────
export interface CatalogRow { name: string; ok: boolean; reasons: string[] }
export interface NtcCandidate {
  mfr?: string; part_number?: string; r25?: number; imax?: number; diameter_mm?: number
  energy_est_J?: number; datasheet_url?: string; ok: boolean; reasons: string[]
  energy_margin?: number | null
  verdict?: string; tier1_ok?: boolean; tier2_ok?: boolean; energy_estimated?: boolean
}
export interface NtcSelected {
  part_number?: string; mfr?: string; r25_ohm: number; imax_A?: number; diameter_mm?: number
  energy_est_J?: number; datasheet_url?: string
  i_inrush_actual_A: number; r_total_cold_ohm: number; tau_ms: number; t_bypass_ms: number
  energy_margin?: number | null
  checks?: { r25_ok?: boolean; energy_ok?: boolean | null; imax_note?: boolean }
  meets_target?: boolean
}
export interface NtcResult {
  spec: Record<string, number>
  result: {
    vin_pk_max: number; r_total_min: number; r_parasitic: number; r25_required: number; r25_pick: number
    r25_nom_required: number; r25_tol_screen: number
    e_cap: number; e_pulse_required: number; cmax_equiv_required: number; i_rms_worst: number
    tau: number; t_bypass: number; relay_contact_v: number; relay_contact_a: number
    sweep: [number, number][]; loss_rows: [number, number][]
  }
  catalog: CatalogRow[]
  candidates?: NtcCandidate[]
  selected?: NtcSelected | null
  sources: Record<string, number>
}
export interface MovResult {
  spec: Record<string, number>
  stress: { v_le: number | null; v_ll: number | null; governing: string | null
            paths: { name: string; mode: string; z: number; v_oc: number; i_sc: number }[] }
  mcov: { required: number; advisory: number; class: number; v1ma: number }
  criterion: { name: string; ride_through: boolean; gate_uses_absmax: boolean; dev_margin_V: number; energy_safety: number }
  targets: { path: string; mode: string; z: number; v_oc: number; i_sc: number; v_drive: number
             i_op: number; vc: number; imax_required: number; energy_8_20: number
             device_gate: number; coord: string; cap_status: string }[]
  catalog: CatalogRow[]
  candidates?: MovCandidate[]
  selected?: MovCandidate | null
  sources: Record<string, number>
  // M1: gates stated BEFORE the candidate screen, and the recalculation on the SELECTED part
  // (the clamp in `targets` is a voltage-CLASS result; `selected_recalc.vc` is the part result).
  gates?: MovGate[]
  selected_recalc?: MovSelectedRecalc | null
  energy_basis?: string
}
export interface MovGate {
  n: number; name: string; requirement: string; value: number | null; unit: string; basis: string
}
export interface MovSelectedGate { n: number; name: string; requirement: string; result: string; status: string }
export interface MovSelectedRecalc {
  part_number: string | null; mfr: string | null; mcov: number | null
  v1ma: number; alpha: number; alpha_estimated: boolean
  i_op: number; vc: number; device_gate: number; clamp_margin_V: number; imax_required: number
  energy: { e_surge_J: number; e_rating_J: number | null; e_allow_J: number | null; ok: boolean | null; note: string }
  overshoot: { di_dt_A_per_us: number; l_nH: number; v_overshoot: number; vc_effective: number }
  gates: MovSelectedGate[]; blockers: string[]
  release_status: string; selection_blocked: boolean
}
export interface MovCandidate {
  label: string; part_number: string | null; mfr: string | null
  mcov: number | null; v1ma: number | null; imax: number | null; energy_2ms_J: number | null
  clamp_vc: number | null; clamp_status: string; part_num_consistent: boolean | null
  verdict: string; ok: boolean; reasons: string[]
}
export const inputProtectionNtc = (body: { design: Record<string, number>; cap?: Record<string, unknown>; opts?: Record<string, unknown> }) =>
  post<NtcResult>('/mode-b/input-protection/ntc/calculate', body)
// Inline SVG of the NTC + relay-bypass inrush schematic (served by the backend generator).
export const inrushSchematicUrl = (): string => `${BASE}/mode-b/input-protection/inrush-schematic`
export const inputProtectionMov = (body: { design: Record<string, number>; mosfet?: Record<string, unknown>; cap?: Record<string, unknown>; opts?: Record<string, unknown> }) =>
  post<MovResult>('/mode-b/input-protection/mov/calculate', body)

export interface GdtCandidate {
  label: string; part_number: string | null; mfr: string | null
  v_spark_nom: number | null; v_spark_min: number | null; v_spark_max: number | null
  imax_impulse: number | null; poles: number | null; fail_short: string | null
  no_fire_ok: boolean | null; surge_ok: boolean | null; dynamic_status: string; ok: boolean; reasons: string[]
}
export interface GdtResult {
  required: { required: boolean; recommend: string; reason: string }
  stress: { v_le: number | null; i_sc: number | null; i_required: number | null
            preferred_class_A: number | null; no_fire_need_V: number | null }
  follow_current: { ok: boolean | null; note: string }
  fail_short: { ok: boolean | null; note: string }
  candidates: GdtCandidate[]
}
export const inputProtectionGdt = (body: { design: Record<string, number>; opts?: Record<string, unknown> }) =>
  post<GdtResult>('/mode-b/input-protection/gdt/calculate', body)

export interface FuseCandidate {
  label: string; part_number: string | null; mfr: string | null
  i_rated_A: number | null; v_ac_V: number | null; breaking_ac_A: number | null; melting_i2t: number | null
  response_time: string | null; fuse_type: string | null
  // six-gate screen: 1 voltage · 2 continuous current · 3 startup I²t · 4 breaking capacity
  //                  5 fault coordination (MOV/GDT fail-short, stuck relay) · 6 thermal implementation
  v_ok: boolean | null; i_ok: boolean | null; bc_ok: boolean | null; i2t_ok: boolean | null
  coord_ok: boolean | null; thermal_ok: boolean | null
  op_temp: string | null; t_body_max_C: number | null
  i_usable_A: number | null; load_pct_of_usable: number | null
  verdict: string; ok: boolean; reasons: string[]
}
export interface FuseGate { n: number; name: string; requirement: string; result: string; status: string }
export interface FuseResult {
  i_rms: number; startup_i2t: number | null; inrush_peak_A: number | null
  requirements: {
    v_min: number; i_cont_min: number; i_load_min: number; inrush_peak: number | null
    i_rated_min: number; i_rated_max: number | null; bc_min: number | null; i2t_min: number | null
    load_factor: number; k_thermal: number; coord_min: number | null
    thermal: { known: boolean; estimated: boolean; rise_known: boolean; k_thermal: number; t_body_C: number | null; note: string }
    coord: { known: boolean; i_A: number | null; source: string | null; note: string }
  }
  candidates: FuseCandidate[]
  selected: FuseCandidate | null; selected_i2t: number | null; fast_blow_only: boolean | null
  gates: FuseGate[]; gate_status: string; gates_open: number[]; gates_conditional: number[]
}
export const inputProtectionFuse = (body: { design: Record<string, number>; cap?: Record<string, unknown>; opts?: Record<string, unknown> }) =>
  post<FuseResult>('/mode-b/input-protection/fuse/calculate', body)

// ── NTC bypass relay ─────────────────────────────────────────────────────────
// The duty (worst-case RMS, line peak, precharge delay, loop parasitic) is carried in from the
// NTC calculation server-side, so the relay is sized on the same numbers the inrush design used.
export interface RelayGate { n: number; name: string; requirement: string; result: string; status: string }
export interface RelayCandidate {
  mfr?: string; part_number: string; description?: string; datasheet_url?: string
  mounting?: string; contact_form?: string; coil_type?: string; contact_material?: string
  op_temp?: string; coil_v_V?: number | null; coil_i_mA?: number | null
  contact_i_A?: number | null; switch_v_V?: number | null; load_max?: string
  t_operate_ms?: number | null; t_release_ms?: number | null
  gates?: RelayGate[]; verdict?: string
}
// What the designer confirms about the chosen relay, with the figure to confirm it against.
// Not gates: two of these cannot be screened (no relay in the catalogue publishes a make rating)
// and one is system timing rather than a property of the part.
export interface RelayConfirmation { item: string; figure: string; confirm: string }
export interface RelayResult {
  spec: Record<string, number | null>
  requirements: { i_contact_min_A: number; v_switch_min_V: number; i_make_A: number | null
                  t_operate_max_ms: number | null; coil_supply_v: number | null; notes: string[] }
  candidates: RelayCandidate[]; selected: RelayCandidate | null
  // parts rated below the computed contact requirement are hidden; `fallback` means nothing in the
  // catalogue cleared it, so the closest parts are shown instead (the list is never empty)
  screen?: { hidden: number; fallback: boolean; i_contact_min_A: number; considered: number }
  confirmation?: RelayConfirmation[]
  gates: RelayGate[]; gate_status: string; catalog_size: number
}
export const inputProtectionRelay = (body: { design: Record<string, number>; cap?: Record<string, unknown>; opts?: Record<string, unknown> }) =>
  post<RelayResult>('/mode-b/input-protection/relay/calculate', body)
// ── input EMI filter (DM + CM conducted-emissions synthesis) ─────────────────
export interface EmiResult {
  feasible: boolean; conducted_class: string; detector: string; margin_db: number
  leakage_limit_A: number; first_harmonic_hz: number; noise_source: string
  dm_req_att_db: number; dm_req_att_f: number; cm_req_att_db: number; cm_req_att_f: number
  dm_stages: number; cm_stages: number; dm_corner_hz: number; cm_corner_hz: number
  c_x: number; l_dm: number; c_y_emi_total: number; c_y_system_total: number; l_cm: number
  damp_r: number; damp_c: number; leakage_actual_A: number; xcap_discharge_s: number | null
  stability_z0_dm: number; stability_rin_conv: number; stability_ok: boolean
  damp_l: number; stability_margin_db: number; dm_res_hz: number
  dm_il_db: number; dm_margin_db: number; dm_margin_f: number
  cm_il_db: number; cm_margin_db: number; cm_margin_f: number
  warnings: string[]; feedback: string[]; provenance: Record<string, string>
}
export interface EmiDesign { result: EmiResult; basis: Record<string, number | null> }
export const inputFilterOptions = (): Promise<{ safety_standards: string[]
    leakage_mA: Record<string, number>; compliance_profiles: Record<string, string> }> =>
  fetch(`${BASE}/mode-b/input-filter/options`).then(r => r.json())
export const inputFilterDesign = (body: { design: Record<string, number>; cap?: Record<string, unknown>
    protection?: Record<string, unknown>; ntc?: Record<string, unknown>; opts?: Record<string, unknown> }) =>
  post<EmiDesign>('/mode-b/input-filter/design', body)
export const inputFilterReport = (body: { design: Record<string, number>; cap?: Record<string, unknown>
    protection?: Record<string, unknown>; ntc?: Record<string, unknown>; opts?: Record<string, unknown> }): Promise<Blob> =>
  fetch(`${BASE}/mode-b/input-filter/report`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  }).then(async r => { if (!r.ok) { const t = await r.text(); throw new Error(`${r.status}: ${t}`) } return r.blob() })

export const inputFilterSchematic = (view: 'asbuilt' | 'synth',
    body: { design: Record<string, number>; cap?: Record<string, unknown>
    protection?: Record<string, unknown>; ntc?: Record<string, unknown>; opts?: Record<string, unknown> }): Promise<string> =>
  fetch(`${BASE}/mode-b/input-filter/schematic?view=${view}`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  }).then(async r => { if (!r.ok) { const t = await r.text(); throw new Error(`${r.status}: ${t}`) } return r.text() })

export const inputProtectionReport = (body: { design: Record<string, number>; cap?: Record<string, unknown>
    mosfet?: Record<string, unknown>; ntc_opts?: Record<string, unknown>; mov_opts?: Record<string, unknown> }): Promise<Blob> =>
  fetch(`${BASE}/mode-b/input-protection/report`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  }).then(async r => { if (!r.ok) { const t = await r.text(); throw new Error(`${r.status}: ${t}`) } return r.blob() })
