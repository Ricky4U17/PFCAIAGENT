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
  kind: string; V_DSS_min: number; I_D_min: number
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
}
export interface DsUpload {
  ok: boolean; reason?: string; part_number: string | null; device_class?: string
  rows: DsReviewRow[]
  triage?: Record<string, unknown>
  cross_check?: { key: string; field: string; values: number[]; spread_pct: number; message: string }[]
  unresolved?: { symbol?: string; name?: string }[]
  tables_kept?: number; tables_rejected?: number
  stored?: { changed: boolean; sha256: string; note?: string }
  revision_diff?: { key: string; field: string; was: number | null; now: number | null }[]
}
export interface DsConfirm {
  ok: boolean; part_number: string
  rows: DsReviewRow[]
  block: Record<string, unknown>
  validation: { ok: boolean; defaulted: { key: string; message: string }[]
                disconnects: { message: string }[]; summary: Record<string, unknown> }
}
export const datasheetRequirements = (design: Record<string, unknown>, kind = 'mosfet') =>
  post<DsRequirement>('/mode-b/semiconductor/datasheet/requirements', { design, kind })
export const datasheetUpload = (kind: string, file: File, partNumber?: string): Promise<DsUpload> => {
  const fd = new FormData(); fd.append('kind', kind); fd.append('file', file)
  if (partNumber) fd.append('part_number', partNumber)
  return fetch(`${BASE}/mode-b/semiconductor/datasheet/upload`, { method: 'POST', body: fd })
    .then(async r => { if (!r.ok) { const t = await r.text(); throw new Error(`${r.status}: ${t}`) } return r.json() })
}
export const datasheetConfirm = (b: { part_number: string; kind: string
                                      edits?: Record<string, unknown>
                                      design?: Record<string, unknown> }) =>
  post<DsConfirm>('/mode-b/semiconductor/datasheet/confirm', b)
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
