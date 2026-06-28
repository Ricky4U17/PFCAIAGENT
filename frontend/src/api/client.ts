const BASE = import.meta.env.VITE_API_URL ?? ''

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`)
  if (!res.ok) { const t = await res.text(); throw new Error(`${res.status}: ${t}`) }
  return res.json() as Promise<T>
}
async function post<T>(path: string, body: unknown): Promise<T> {
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

  start: (project_id: string, intake: unknown) =>
    post<{status:string;ranking:Candidate[];mode_scores:ModeScore[];
          recommended_topology:string;recommended_mode:string;state:Record<string,unknown>}>
    ('/mode-a/start', { project_id, intake }),

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
  optimization_goal?: 'best_performance' | 'max_ffu'
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
}): Promise<Blob> =>
  fetch(`${BASE}/mode-b/documentation/generate-report`, {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify(req),
  }).then(async res => {
    if (!res.ok) { const t = await res.text(); throw new Error(`${res.status}: ${t}`) }
    return res.blob()
  })

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
         m1_ll_mohm: number; m1_hl_mohm: number; note: string }
  selectable: SelComp[]
  r_ls: { default_kohm: number; calc_kohm: number; options_kohm: number[]; role: string }
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
  tj_limit?:     Record<string, number>
  selected_vac?: number
}
export const semiconductorLibrary = () =>
  get<Record<string, Array<Record<string, unknown>>>>('/mode-b/semiconductor/library')
export interface DbRankResult {
  manufacturer: string; part_number: string; technology: string | null; package: string | null
  mounting: string | null; datasheet_url: string | null; v_rating: number | null; i_rating: number | null
  loss_W: number; tj_max_C: number; block: Record<string, unknown>
}
export const semiconductorDbOptions = (kind: string) =>
  get<Record<string, string[]>>(`/mode-b/semiconductor/database/${kind}/options`)
export const semiconductorDbRank = (kind: string,
  body: { design: Record<string, number>; criteria: Record<string, unknown>; top?: number; mode?: string }) =>
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
export const semiconductorCalculate = (b: SemiReqBody) =>
  post<SemiCalcResult>('/mode-b/semiconductor/calculate', b)
export const semiconductorFigures = (b: SemiReqBody) =>
  post<{ figures: Record<string, string>; selected_vac: number }>('/mode-b/semiconductor/figures', b)
