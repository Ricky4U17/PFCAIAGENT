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
}): Promise<Blob> =>
  fetch(`${BASE}/mode-b/documentation/generate-report`, {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify(req),
  }).then(async res => {
    if (!res.ok) { const t = await res.text(); throw new Error(`${res.status}: ${t}`) }
    return res.blob()
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
