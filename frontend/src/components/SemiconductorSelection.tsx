/**
 * SemiconductorSelection.tsx — Chapter 7: Semiconductor Loss & Thermal.
 *
 * One page, four freely-switchable sub-screens: Bridge / MOSFET / Diode component
 * entry (manufacturer + part number + datasheet params, prefilled with a reference
 * SiC design) and a Results tab. The operating point (η, PF, Pout, Iin, Lφ, …) is
 * carried in from the approved design and shown read-only — the backend sources it
 * from the same single-source-of-truth grid every chapter uses, and a consistency
 * gate guarantees the loss numbers never diverge from the rest of the design.
 */
import React, { useEffect, useMemo, useRef, useState } from 'react'
import { C, Btn, Card, SecHead } from './ui'
import type { CapacitorResult } from './Step15Capacitor'
import { plausibilityCheck, datasheetRequirements, datasheetUpload, datasheetConfirm,
         datasheetFigures, datasheetFigureImage, datasheetFigureConfirm,
         datasheetPublish, datasheetDiscard, semiconductorReport } from '../api/client'
import type { PlausResult, DsRequirement, DsReviewRow, DsUpload, DsConfirm,
              DsFigureProposal, DsCurve } from '../api/client'
import { semiconductorCalculate, semiconductorFigures, docGenerateReport,
         semiconductorDbOptions, semiconductorDbRank, semiconductorExtract,
         type SemiCalcResult, type SemiReqBody, type DbRankResult } from '../api/client'
import { downloadBlob, reportFilename } from '../api/download'

interface Props {
  confirmedState:          Record<string, unknown>
  approvedInductorDesign:  Record<string, unknown>
  approvedCapacitorDesign: CapacitorResult | null
  // Persisted Control-Design step16_params (s2 selections + js_design_state) — forwarded
  // to the report so Ch6/Ch7 document the designer's R_CS etc., not engine defaults.
  approvedControlParams?:  Record<string, unknown> | null
  onBack:    () => void
  // Receives the page's full semiconductor config so App persists it — the
  // Input-Protection page forwards it and its report keeps Chapter 7.
  onNext?:   (semiconductor?: Record<string, unknown>) => void
  onRestart: () => void
}

type Sub = 'bridge' | 'mosfet' | 'diode' | 'results'
// the kinds that use the datasheet-first flow (the bridge is still catalogue/manual)
type DsKind = 'mosfet' | 'diode' | 'bridge'
type Curve = { x: string; y: string }
type Field = { key: string; label: string; kind: 'text' | 'num' | 'curve' | 'bool' | 'select'
               unit?: string; opts?: string[]; hint?: string; show?: (s: Record<string, any>) => boolean }

// ── reference SiC prefill (form values are strings; sci-notation friendly) ──
const MOSFET0: Record<string, any> = {
  manufacturer: '', part_number: '', tech: 'sic',
  rdson_25: '0.060', rdson_tj: { x: '25, 125', y: '1.0, 1.4' },
  ciss: '1500e-12', qgd: '18e-9', vth: '4.0', vpl: '7.0', qg: '60e-9',
  eoss_at_v: { x: '100, 400', y: '1.5e-6, 6e-6' }, rth_jc: '0.6',
  vg: '18.0', rg: '4.0', rth_cs: '0.3',
}
const DIODE0: Record<string, any> = {
  manufacturer: '', part_number: '', is_sic: true,
  vf_curve: { x: '1, 5, 16', y: '1.05, 1.35, 1.7' }, vf_curve_hot: { x: '', y: '' },
  qc: '20e-9', qrr: '120e-9',
  vf_tco: '0.0015', rth_jc: '0.7', rth_cs: '0.3',
}
const BRIDGE0: Record<string, any> = {
  manufacturer: '', part_number: '', topology: 'diode',
  vf_curve: { x: '1, 12, 24', y: '0.75, 0.95, 1.15' }, vf_curve_hot: { x: '', y: '' },
  n_parallel: '2', share_worst: '', ifsm_A: '', i2t_A2s: '',
  rth_jc: '1.0', rth_cs: '0.5',
  rdson_bottom_25: '0.020', rdson_bottom_tj: { x: '25, 125', y: '1.0, 1.5' },
  qg_bottom: '90e-9', n_parallel_bottom: '1', bottom_part: '',
}

const MOSFET_FIELDS: Field[] = [
  { key: 'manufacturer', label: 'Manufacturer', kind: 'text' },
  { key: 'part_number', label: 'Part number', kind: 'text' },
  { key: 'tech', label: 'Technology', kind: 'select', opts: ['si', 'sic'] },
  { key: 'rdson_25', label: 'R_DS(on) @25°C', kind: 'num', unit: 'Ω' },
  { key: 'rdson_tj', label: 'R_DS(on) vs Tj', kind: 'curve', unit: '°C / ×' },
  { key: 'ciss', label: 'C_iss', kind: 'num', unit: 'F' },
  { key: 'qgd', label: 'Q_gd', kind: 'num', unit: 'C' },
  { key: 'vth', label: 'V_th', kind: 'num', unit: 'V' },
  { key: 'vpl', label: 'Miller plateau V_pl', kind: 'num', unit: 'V' },
  { key: 'qg', label: 'Q_g', kind: 'num', unit: 'C' },
  { key: 'eoss_at_v', label: 'E_oss vs V_ds', kind: 'curve', unit: 'V / J' },
  { key: 'rth_jc', label: 'Rθ(j-c)', kind: 'num', unit: '°C/W' },
  { key: 'vg', label: 'Gate drive V_g', kind: 'num', unit: 'V', hint: 'application' },
  { key: 'rg', label: 'Gate resistor R_g', kind: 'num', unit: 'Ω', hint: 'application' },
  { key: 'rth_cs', label: 'Rθ(c-s)', kind: 'num', unit: '°C/W', hint: 'application' },
]
const DIODE_FIELDS: Field[] = [
  { key: 'manufacturer', label: 'Manufacturer', kind: 'text' },
  { key: 'part_number', label: 'Part number', kind: 'text' },
  { key: 'is_sic', label: 'SiC Schottky', kind: 'bool', hint: 'unchecked = Si fast/PN' },
  { key: 'vf_curve', label: 'V_f vs I_f (25°C)', kind: 'curve', unit: 'A / V' },
  { key: 'vf_curve_hot', label: 'V_f vs I_f @125°C (optional)', kind: 'curve', unit: 'A / V',
    hint: 'datasheet hot curve — replaces the scalar tempco with per-current-point interpolation' },
  { key: 'qc', label: 'Q_c (SiC)', kind: 'num', unit: 'C', show: s => !!s.is_sic },
  { key: 'qrr', label: 'Q_rr (Si)', kind: 'num', unit: 'C', show: s => !s.is_sic },
  { key: 'vf_tco', label: 'V_f tempco', kind: 'num', unit: 'V/°C' },
  { key: 'rth_jc', label: 'Rθ(j-c)', kind: 'num', unit: '°C/W' },
  { key: 'rth_cs', label: 'Rθ(c-s)', kind: 'num', unit: '°C/W', hint: 'application' },
]
const BRIDGE_FIELDS: Field[] = [
  { key: 'manufacturer', label: 'Manufacturer', kind: 'text' },
  { key: 'part_number', label: 'Part number', kind: 'text' },
  { key: 'topology', label: 'Topology', kind: 'select', opts: ['diode', 'sync_bottom'],
    hint: 'sync_bottom = bypass MOSFETs on the bottom legs' },
  { key: 'vf_curve', label: 'Diode V_f vs I_f (25°C)', kind: 'curve', unit: 'A / V' },
  { key: 'vf_curve_hot', label: 'Diode V_f vs I_f @125°C (optional)', kind: 'curve', unit: 'A / V',
    hint: 'datasheet hot curve (Fig. "Typical Forward Characteristics") — captures NTC threshold + PTC resistance' },
  { key: 'n_parallel', label: 'Devices in parallel', kind: 'num',
    hint: '2 = split dual-bridge arrangement (AC pins shorted per package)' },
  { key: 'share_worst', label: 'Worst-die share (optional)', kind: 'num',
    hint: 'hottest die’s fraction of the arm current (e.g. 0.6 for 60/40); blank = ideal 1/n' },
  { key: 'ifsm_A', label: 'Surge I_FSM (8.3 ms)', kind: 'num', unit: 'A',
    hint: 'datasheet single half-sine surge rating — verified vs the Ch-8 inrush in the report' },
  { key: 'i2t_A2s', label: 'I²t rating', kind: 'num', unit: 'A²s',
    hint: 'datasheet fusing rating — verified vs the inrush event I²t in the report' },
  { key: 'rth_jc', label: 'Rθ(j-c)', kind: 'num', unit: '°C/W' },
  { key: 'rth_cs', label: 'Rθ(c-s)', kind: 'num', unit: '°C/W', hint: 'application' },
  { key: 'rdson_bottom_25', label: 'Bottom-FET R_DS(on) @25°C', kind: 'num', unit: 'Ω', show: s => s.topology === 'sync_bottom' },
  { key: 'rdson_bottom_tj', label: 'Bottom-FET R_DS(on) vs Tj', kind: 'curve', unit: '°C / ×', show: s => s.topology === 'sync_bottom' },
  { key: 'qg_bottom', label: 'Bottom-FET Q_g', kind: 'num', unit: 'C', show: s => s.topology === 'sync_bottom' },
  { key: 'n_parallel_bottom', label: 'Bottom FETs in parallel', kind: 'num', show: s => s.topology === 'sync_bottom' },
]

// ── form → engine block ──
const pnum = (v: string) => { const n = parseFloat(v); return Number.isFinite(n) ? n : undefined }
const pcurve = (c: Curve) => {
  const xs = (c?.x ?? '').split(',').map(s => parseFloat(s.trim())).filter(Number.isFinite)
  const ys = (c?.y ?? '').split(',').map(s => parseFloat(s.trim())).filter(Number.isFinite)
  return xs.length >= 1 && xs.length === ys.length ? [xs, ys] : undefined
}
function buildBlock(state: Record<string, any>, fields: Field[]): Record<string, unknown> {
  const out: Record<string, unknown> = {}
  for (const f of fields) {
    if (f.show && !f.show(state)) continue
    const v = state[f.key]
    if (f.kind === 'num') { const n = pnum(v); if (n !== undefined) out[f.key] = n }
    else if (f.kind === 'curve') { const c = pcurve(v); if (c) out[f.key] = c }
    else if (f.kind === 'bool') out[f.key] = !!v
    else if (v !== '' && v != null) out[f.key] = v
  }
  return out
}

// ── library part (engine block) → form state (inverse of buildBlock) ──
const numToStr = (v: any) => typeof v === 'number' ? String(v) : (v ?? '')
const curveToForm = (c: any): Curve => Array.isArray(c) && c.length === 2
  ? { x: (c[0] as number[]).join(', '), y: (c[1] as number[]).join(', ') } : { x: '', y: '' }
function blockToForm(block: Record<string, any>, fields: Field[], base: Record<string, any>) {
  const out: Record<string, any> = { ...base }
  for (const f of fields) {
    if (!(f.key in block)) continue
    const v = block[f.key]
    if (f.kind === 'curve') out[f.key] = curveToForm(v)
    else if (f.kind === 'num') out[f.key] = numToStr(v)
    else out[f.key] = v
  }
  return out
}
// One row of the datasheet review screen. Shows the value WITH its conditions and its
// destination, because a bare number is not reviewable — the reviewer has to be able to see what
// it will be used for and under what conditions it was measured.
// A REPORTED-ONLY parameter: read from the datasheet, shown so the designer can see what the
// part carries, and not editable because nothing downstream consumes it. R_g,int is the case — it
// is the device's INTERNAL gate resistance, it is not added to R_g,on / R_g,off (those are the
// external plus driver path), and letting it be typed over would imply it changed a result.
const READ_ONLY_KEYS = new Set(['R_g_int'])

const ReviewRow: React.FC<{ r: DsReviewRow; edit?: string
                            onEdit: (k: string, v: string) => void }> = ({ r, onEdit, edit }) => {
  const bad = !r.supplied
  const readOnly = READ_ONLY_KEYS.has(r.key)
  return (
    <div style={{ borderTop: `1px solid ${C.border}`, padding: '6px 0' }}>
      <div style={{ display: 'grid', gridTemplateColumns: '150px 110px 1fr 130px', gap: 8, alignItems: 'center' }}>
        <div style={{ fontSize: 11.5, color: bad ? C.amber : C.text }}
          dangerouslySetInnerHTML={{ __html: r.label }} />
        <input style={{ ...inStyle, padding: '2px 6px', fontSize: 11.5,
            opacity: readOnly ? 0.65 : 1, cursor: readOnly ? 'not-allowed' : undefined }}
          readOnly={readOnly} disabled={readOnly}
          placeholder={bad ? (r.source_kind === 'design' ? 'you supply' : 'not found') : ''}
          value={edit ?? (r.display ?? '')} onChange={e => onEdit(r.key, e.target.value)} />
        <div style={{ fontSize: 10, color: C.muted }}>
          {readOnly
            ? 'read from the datasheet · reported only, not added to the gate path'
            : Object.entries(r.conditions).length > 0
            ? Object.entries(r.conditions).map(([k, v]) => `${k} = ${v}`).join(', ')
            : (r.source_kind === 'design' ? 'a design choice — no datasheet supplies it' : '—')}
          {r.entries > 1 && <span style={{ color: C.teal }}> · {r.entries} entries</span>}
        </div>
        <div style={{ fontSize: 9.5, color: C.hint, textAlign: 'right' }}>
          → {r.destination}<br />
          <span style={{ color: r.provenance === 'extracted' ? C.green : C.amber }}>{r.provenance}</span>
        </div>
      </div>
      {r.all_entries.length > 1 && (
        <div style={{ marginLeft: 8, marginTop: 2 }}>
          {r.all_entries.map((e, i) => (
            <div key={i} style={{ fontSize: 9.5, color: C.muted, fontFamily: 'IBM Plex Mono,monospace' }}>
              {e.value} · {Object.entries(e.conditions).map(([k, v]) => `${k}=${v}`).join(' ') || 'no conditions stated'}
            </div>))}
        </div>)}
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// MODULE LEVEL ON PURPOSE. A component declared inside another component body
// gets a new function identity on every render, so React treats it as a
// different component type: it unmounts the old subtree and mounts a fresh one.
// That destroys and recreates the <input> on every keystroke, and focus is lost
// after each character. `Knob` in InputProtection.tsx has always been at module
// level, which is exactly why that page never had the problem.
// ─────────────────────────────────────────────────────────────────────────────
const FieldRow: React.FC<{ f: Field; state: Record<string, any>; onSet: (k: string, v: any) => void }>
  = ({ f, state, onSet }) => {
    if (f.show && !f.show(state)) return null
    const v = state[f.key]
    return (
      <div style={{ display: 'grid', gridTemplateColumns: '190px 1fr', gap: 8, alignItems: 'center', marginBottom: 6 }}>
        <label style={{ fontSize: 11.5, color: C.text }}>{f.label}
          {f.unit && <span style={{ color: C.hint }}> ({f.unit})</span>}
          {f.hint && <div style={{ fontSize: 9.5, color: C.muted }}>{f.hint}</div>}
        </label>
        {f.kind === 'bool' ? (
          <input type="checkbox" checked={!!v} onChange={e => onSet(f.key, e.target.checked)} style={{ width: 'auto' }} />
        ) : f.kind === 'select' ? (
          <select value={v} style={inStyle} onChange={e => onSet(f.key, e.target.value)}>
            {f.opts!.map(o => <option key={o} value={o}>{o}</option>)}
          </select>
        ) : f.kind === 'curve' ? (
          <div style={{ display: 'flex', gap: 6 }}>
            <input style={inStyle} value={(v as Curve).x} placeholder="x1, x2, …"
              onChange={e => onSet(f.key, { ...(v as Curve), x: e.target.value })} />
            <input style={inStyle} value={(v as Curve).y} placeholder="y1, y2, …"
              onChange={e => onSet(f.key, { ...(v as Curve), y: e.target.value })} />
          </div>
        ) : (
          <input style={inStyle} value={v ?? ''} onChange={e => onSet(f.key, e.target.value)} />
        )}
      </div>
    )
  }


const Banner: React.FC<{ ok: boolean; okText: string; badText: string; issues?: any[] }>
    = ({ ok, okText, badText, issues }) => (
    <div style={{ background: ok ? 'rgba(45,212,191,.10)' : '#fdf2f2', border: `1px solid ${ok ? C.green : '#e8b4b8'}`,
      borderRadius: 8, padding: '8px 12px', fontSize: 12, color: ok ? C.green : '#c0392b', marginBottom: 8 }}>
      {ok ? `✓ ${okText}` : `✗ ${badText}`}
      {!ok && issues && issues.length > 0 && (
        <ul style={{ margin: '6px 0 0 16px', color: C.text }}>
          {issues.slice(0, 12).map((i, k) => <li key={k} style={{ fontSize: 11 }}>{JSON.stringify(i)}</li>)}
        </ul>
      )}
    </div>
  )


const BASE: Record<Sub, Record<string, any>> = { bridge: BRIDGE0, mosfet: MOSFET0, diode: DIODE0, results: {} }
const FIELDS: Record<Sub, Field[]> = { bridge: BRIDGE_FIELDS, mosfet: MOSFET_FIELDS, diode: DIODE_FIELDS, results: [] }

const inStyle: React.CSSProperties = { background: C.bg3, border: `1px solid ${C.border2}`, borderRadius: 6,
  color: C.text, padding: '5px 8px', fontSize: 12, fontFamily: 'IBM Plex Mono,monospace', width: '100%' }
const fmtW = (n: number) => `${n.toFixed(2)} W`

export const SemiconductorSelection: React.FC<Props> = ({
  confirmedState, approvedInductorDesign, approvedCapacitorDesign, approvedControlParams,
  onBack, onNext, onRestart,
}) => {
  const app = (confirmedState as any)?.intake?.application ?? {}
  const tsi = (confirmedState as any)?.topology_specific_inputs ?? {}

  const design = useMemo(() => ({
    vin_min:  Number(app.vin_rms_min ?? 90),
    vin_max:  Number(app.vin_rms_max ?? 264),
    pout_lo:  Number(app.output_power_w_low_line ?? 1700),
    pout_hi:  Number(app.output_power_w_high_line ?? 3600),
    vout:     Number(app.output_bus_voltage_v ?? 393.7),
    fsw:      Number(tsi.recommended_frequency_hz ?? 70000),
    fline:    Number(app.line_frequency_hz ?? 60),
    nch:      Number((confirmedState as any)?.selected_channels ?? 2),
    r_input:  Number(tsi.default_crest_ripple_ratio ?? 0.20),
    // Lφ is finalized in Chapter 3 — use the SAME resolution (never a Chapter-7 value):
    L_phi_uH: Number(tsi.confirmed_L_uH_sel ?? tsi.confirmed_L_uH ?? (approvedInductorDesign as any)?.L_target_uH ?? 235),
  }), [confirmedState, approvedInductorDesign])  // eslint-disable-line react-hooks/exhaustive-deps

  const [sub, setSub] = useState<Sub>('bridge')
  const [mosfet, setMosfet] = useState({ ...MOSFET0 })
  const [diode, setDiode] = useState({ ...DIODE0 })
  const [bridge, setBridge] = useState({ ...BRIDGE0 })
  // Full engine block of a DB-selected / uploaded part, kept so datasheet fields the FORM doesn't
  // expose (e.g. vf_tco, _estimated) survive into Calculate — otherwise the form round-trip drops them
  // and the Results loss diverges from the Top-10 screen (which uses the full block).
  const [dbBlock, setDbBlock] = useState<Record<string, Record<string, unknown>>>({})
  const _specAmbient = Number(
    (confirmedState as any)?.intake?.thermal?.ambient_temp_c_max ?? 45)
  const [thermal, setThermal] = useState({
    t_ambient: String(_specAmbient), rth_sa: '0.35' })
  // Keep the field in step with the spec until the designer edits it themselves.
  const _ambTouched = useRef(false)
  useEffect(() => {
    if (!_ambTouched.current) setThermal(t => ({ ...t, t_ambient: String(_specAmbient) }))
  }, [_specAmbient])
  const [tjLimit] = useState({ fet: 150, diode: 150, bridge: 130 })

  const [res, setRes] = useState<SemiCalcResult | null>(null)
  const [figs, setFigs] = useState<Record<string, string> | null>(null)
  const [busy, setBusy] = useState(false)
  const [figBusy, setFigBusy] = useState(false)
  const [rptBusy, setRptBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  type SrcMode = 'database' | 'manual' | 'upload'
  const [srcMode, setSrcMode] = useState<Record<string, SrcMode>>({ bridge: 'database', mosfet: 'database', diode: 'database' })
  const [dbOpts, setDbOpts] = useState<Record<string, Record<string, string[]>>>({})
  // Worst-case input RMS current across the two power corners (same η/PF map the Review page
  // uses: 90 V/η0.945/PF0.9987 low line, 180 V/η0.965/PF0.9889 high line). The DB current filters
  // default to ≥ this CALCULATED value — never a hardcoded 15 A — and stay designer-editable.
  const worstIin = useMemo(() => Math.max(
    design.pout_lo / (0.945 * design.vin_min * 0.9987),
    design.pout_hi / (0.965 * 180 * 0.9889),
  ), [design])
  const [dbCrit, setDbCrit] = useState<Record<string, any>>(() => {
    const iw = String(Math.ceil(worstIin))                       // line-current devices
    const iph = String(Math.ceil(worstIin / Math.max(design.nch, 1)))  // per-phase devices
    return {
      bridge: { v_min: '600', i_min: iw }, mosfet: { v_min: '600', i_min: iw },
      diode: { v_min: '600', i_min: iph },
      bottom: { v_min: '550', i_min: iw },
    }
  })
  const [dbRes, setDbRes] = useState<Record<string, DbRankResult[] | null>>({})
  // Design context each ranked list was produced with, so a stale list can be flagged
  // rather than silently disagreeing with the live Results figure.
  const [dbCtx, setDbCtx] = useState<Record<string, { tamb: number; rth: number }>>({})
  const [dbBusy, setDbBusy] = useState<Record<string, boolean>>({})
  const [extBusy, setExtBusy] = useState<Record<string, boolean>>({})
  const [extInfo, setExtInfo] = useState<Record<string, { found: string[]; missing: string[]; part: string } | null>>({})
  useEffect(() => {
    (['bridge', 'mosfet', 'diode'] as Sub[]).forEach(k =>
      semiconductorDbOptions(k).then(o => setDbOpts(s => ({ ...s, [k]: o }))).catch(() => {}))
  }, [])
  const setWhole = (which: Sub, value: Record<string, any>) => {
    (which === 'mosfet' ? setMosfet : which === 'diode' ? setDiode : setBridge)(value as any)
  }
  const setCrit = (which: string, k: string, v: any) => setDbCrit(s => ({ ...s, [which]: { ...s[which], [k]: v } }))
  // key = state slot for crit/results (a Sub, or 'bottom'); kind = DB table; mode = 'full' | 'conduction'
  const runDbSearch = async (key: string, kind: Sub, mode: 'full' | 'conduction' = 'full') => {
    setDbBusy(s => ({ ...s, [key]: true })); setErr(null)
    try {
      const c = dbCrit[key] || {}; const criteria: Record<string, unknown> = {}
      if (pnum(c.v_min) != null) criteria.v_min = pnum(c.v_min)
      if (pnum(c.i_min) != null) criteria.i_min = pnum(c.i_min)
      if (c.mfr) criteria.mfr = c.mfr
      if (c.mounting) criteria.mounting = c.mounting
      if (c.package) criteria.package = c.package
      if (pnum(c.tj_min) != null) criteria.tj_min = pnum(c.tj_min)
      if (c.technology) criteria.technology = c.technology
      // design context so the SCREEN loss equals the Results value for the selected part: companion
      // blocks + thermal + as-built L, and the designer's devices-in-parallel applied to the ranked kind.
      const mBlk = buildBlock(mosfet, MOSFET_FIELDS) as Record<string, unknown>
      const dBlk = buildBlock(diode, DIODE_FIELDS) as Record<string, unknown>
      const bBlk = buildBlock(bridge, BRIDGE_FIELDS) as Record<string, unknown>
      const np = pnum(c.n_parallel)
      if (np != null && kind === 'bridge') bBlk.n_parallel = np
      if (np != null && kind === 'mosfet') mBlk.n_parallel = np
      const r = await semiconductorDbRank(kind, { design, criteria, top: 10, mode,
        mosfet: mBlk, diode: dBlk, bridge: bBlk,
        thermal: { t_ambient: pnum(thermal.t_ambient) ?? _specAmbient, rth_sa: pnum(thermal.rth_sa) ?? 0.35 },
        approved_design: approvedInductorDesign as Record<string, unknown> })
      setDbRes(s => ({ ...s, [key]: r.results }))
      setDbCtx(s => ({ ...s, [key]: { tamb: pnum(thermal.t_ambient) ?? _specAmbient,
                                      rth:  pnum(thermal.rth_sa)   ?? 0.35 } }))
    } catch (e) { setErr((e as Error).message) } finally { setDbBusy(s => ({ ...s, [key]: false })) }
  }
  const pickDbPart = (which: Sub, r: DbRankResult) => {
    setWhole(which, blockToForm(r.block as Record<string, any>, FIELDS[which], BASE[which]))
    setDbBlock(s => ({ ...s, [which]: r.block as Record<string, unknown> }))  // keep full block (vf_tco…)
    setSrcMode(s => ({ ...s, [which]: 'manual' }))   // show the populated fields for review/edit
  }
  // Bottom bypass MOSFET (sync_bottom bridge): conduction-only, merge its fields into the bridge state
  const pickBottomMosfet = (r: DbRankResult) => {
    const b = r.block as any
    setBridge(s => ({ ...s,
      rdson_bottom_25: numToStr(b.rdson_bottom_25),
      rdson_bottom_tj: curveToForm(b.rdson_bottom_tj),
      qg_bottom: numToStr(b.qg_bottom),
      n_parallel_bottom: numToStr(b.n_parallel_bottom),
      bottom_part: `${r.manufacturer ?? ''} ${r.part_number ?? ''}`.trim(),
    }))
  }
  // Advisory sanity-check. Runs after an upload and on demand from the manual form — the two
  // paths where a value reaches the engine without a vendor catalogue behind it. It never blocks:
  // findings are shown, the designer decides.
  const [plaus, setPlaus] = useState<Partial<Record<Sub, PlausResult>>>({})

  // ── datasheet-first flow (M3) ──────────────────────────────────────────────
  // Requirement -> upload -> review/confirm -> results. Confirming stores the engine block, so the
  // existing Calculate runs on datasheet values rather than on catalogue estimates.
  // Keyed by KIND. The MOSFET and the boost diode run the same four-step flow, so they share one
  // panel and one set of handlers — a second copy of 150 lines is how the two drift apart.
  const [dsTab, setDsTab] = useState<Record<DsKind, 'upload' | 'parameters' | 'curves' | 'results'>>(
    { mosfet: 'upload', diode: 'upload', bridge: 'upload' })
  // ── M7: the plotted curves ──────────────────────────────────────────────────────────────
  // Everything a table cannot carry has been standing in as a fitted shape — a constant forward
  // drop, a Q_c moved to the bus by an assumed power law. The shapes are printed on the page. The
  // agent proposes; the designer confirms AGAINST THE PLOT, which is why each row shows the figure.
  const [dsPdf, setDsPdf] = useState<Partial<Record<DsKind, File>>>({})
  const [curveFigs, setCurveFigs] = useState<Partial<Record<DsKind, DsFigureProposal[]>>>({})
  const [figImg, setFigImg] = useState<Record<string, string>>({})
  const [curveBusy, setCurveBusy] = useState(false)
  const [figDone, setFigDone] = useState<Record<string, string>>({})
  // whether the digitiser has actually been RUN for a kind — an empty list before it runs and
  // an empty list after it runs mean different things, and the screen has to say which.
  const [figLoaded, setFigLoaded] = useState<Partial<Record<DsKind, boolean>>>({})
  // Which stored parts the designer has actually vouched for. A part is PROVISIONAL until
  // then, so a datasheet uploaded by mistake never reaches the shared library.
  const [published, setPublished] = useState<Record<string, boolean>>({})
  const [dsReq, setDsReq] = useState<Partial<Record<DsKind, DsRequirement>>>({})
  const [dsUp, setDsUp] = useState<Partial<Record<DsKind, DsUpload>>>({})
  const [dsConf, setDsConf] = useState<Partial<Record<DsKind, DsConfirm>>>({})
  const [dsBusy, setDsBusy] = useState<Partial<Record<DsKind, boolean>>>({})
  const [dsEdits, setDsEdits] = useState<Record<DsKind, Record<string, string>>>(
    { mosfet: {}, diode: {}, bridge: {} })
  // Design-sourced inputs. No upload can supply these, so they are asked for explicitly rather
  // than falling through to an engine default nobody chose. The diode needs far fewer of them:
  // it has no gate.
  const [dsDesign, setDsDesign] = useState<Record<DsKind, Record<string, string>>>({
    // R_g_common is GONE. It was never a third resistor: the engine reads it only as a fallback
    // when the on and off paths are not given separately (`_rg` returns `rg_on or rg`), so a field
    // labelled plainly "R_g" alongside R_g,on and R_g,off read like a third gate resistor. If the
    // two paths are the same, the same number goes in both.
    mosfet: { V_GS_drive: '', R_g_on: '', R_g_off: '', R_th_cs: '0.3',
              sw_method: 'analytic', device_class: 'sic_mosfet' },
    // dies/package: a dual common-cathode boost diode feeding both interleaved channels puts
    // BOTH legs' loss through one case-to-sink interface. The datasheet cannot say whether both
    // legs are actually loaded — only the designer knows which package is fitted.
    diode:  { R_th_cs: '0.3', dies_per_package: '1', device_class: 'sic_schottky' },
    // The bridge blocks the LINE peak and carries the rectified mean, so its configuration is the
    // current PATH: how many packages share it, how badly they share, and whether the bottom two
    // positions are diodes or bypass MOSFETs.
    // Two packages sharing 50/50 is the arrangement this design actually uses, so it is the
    // default rather than a single package. No device class here: a bridge rectifier is the only
    // thing this tab can hold, so a selector with one option is noise.
    bridge: { R_th_cs: '0.5', n_parallel: '2', share_worst: '0.5',
              bridge_topology: 'diode', bottom_mosfet_part: '' },
  })

  // The requirement has to see the SAME design inputs the block is built from. It was called with
  // the top-level design alone, so the bridge's `n_parallel` was always 1 no matter what the
  // Parameters tab said — and the per-package current it states is derived from exactly that. The
  // default of two packages made a pre-existing disconnect visible rather than causing it.
  const dsDesignKey = JSON.stringify(dsDesign)
  useEffect(() => {
    const numeric = (o: Record<string, string>) => Object.fromEntries(
      Object.entries(o ?? {}).filter(([, v]) => v !== '')
        .map(([k, v]) => [k, isNaN(Number(v)) ? v : Number(v)]))
    ;(['mosfet', 'diode', 'bridge'] as DsKind[]).forEach(k =>
      datasheetRequirements({ ...(design as unknown as Record<string, unknown>),
                              ...numeric(dsDesign[k]) }, k)
        .then(r => setDsReq(s2 => ({ ...s2, [k]: r }))).catch(() => {}))
  }, [design, dsDesignKey])

  const doUpload = async (kind: DsKind, file?: File, variant?: string, deviceClass?: string) => {
    if (!file) return
    setDsBusy(s2 => ({ ...s2, [kind]: true })); setErr(null)
    // A NEW UPLOAD RETIRES THE PREVIOUS PART, not just its review screen. `dbBlock` is what the
    // engine reads, so clearing only `dsConf` left the old part still being calculated with while
    // the screen showed the new one — confirm A, upload B, press Calculate, and the numbers are
    // still A's. An unconfirmed upload means NO confirmed part, not silently the one before it.
    setDsConf(s2 => { const n = { ...s2 }; delete n[kind]; return n })
    setDbBlock(s2 => { const n = { ...s2 }; delete n[kind]; return n })
    setFigDone({}); setCurveFigs(s2 => ({ ...s2, [kind]: [] }))
    setFigLoaded(s2 => ({ ...s2, [kind]: false }))
    try {
      const r = await datasheetUpload(kind, file, variant,
                                      deviceClass ?? dsDesign[kind]?.device_class)
      setDsUp(s2 => ({ ...s2, [kind]: r }))
      setDsPdf(s2 => ({ ...s2, [kind]: file }))       // the Curves tab reads the plots from it
      if (r.ok) setDsTab(s2 => ({ ...s2, [kind]: 'curves' }))
      else setErr(r.reason || 'the datasheet could not be read')
    } catch (e) { setErr((e as Error).message) }
    finally { setDsBusy(s2 => ({ ...s2, [kind]: false })) }
  }

  // `goToResults` is false when this runs as part of accepting a CURVE. Every Accept re-confirms
  // the part — that is what rebuilds the block from the profile the curve just landed in — but it
  // was also switching tabs, so accepting seven traces meant seven trips back to the Curves tab.
  const doConfirm = async (kind: DsKind, goToResults = true) => {
    const up = dsUp[kind]
    if (!up?.part_number) return
    setDsBusy(s2 => ({ ...s2, [kind]: true })); setErr(null)
    try {
      const numeric = (o: Record<string, string>) => Object.fromEntries(
        Object.entries(o).filter(([, v]) => v !== '')
          .map(([k, v]) => [k, isNaN(Number(v)) ? v : Number(v)]))
      const r = await datasheetConfirm({ part_number: up.part_number, kind,
        device_class: dsDesign[kind]?.device_class,
        edits: numeric(dsEdits[kind] ?? {}),
        // The diode's V-I curve has to reach the design's peak current, and its Q_c has to be
        // moved to the design's bus voltage — so the whole design goes down, not just the
        // interface resistance.
        design: { ...(design as unknown as Record<string, unknown>),
                  ...numeric(dsDesign[kind] ?? {}) } })
      setDsConf(s2 => ({ ...s2, [kind]: r }))
      // The confirmed block becomes the part the engine uses. Without this the review would be
      // theatre: values approved and then not used.
      setDbBlock(s2 => ({ ...s2, [kind]: r.block }))
      setWhole(kind, blockToForm(r.block as Record<string, any>, FIELDS[kind],
                                 kind === 'mosfet' ? mosfet : kind === 'diode' ? diode : bridge))
      if (goToResults && r.validation.ok) {
        setDsTab(s2 => ({ ...s2, [kind]: 'results' }))
        // CONFIRMING IS THE TRIGGER — no separate "Calculate losses" click. But the three devices
        // SHARE ONE HEATSINK, so the engine solves them together and refuses a partial set: there
        // is no such thing as a bridge loss computed on its own, because its junction temperature
        // depends on what the other two are dissipating. So the run happens once the last
        // component is confirmed; before that the Results tab says what it is still waiting for.
        const ready = (['bridge', 'mosfet', 'diode'] as DsKind[])
          .every(k => k === kind ? true : !!dsConf[k]?.block)
        if (ready) await calc(false)      // fill THIS component's Results tab, do not navigate away
      }
    } catch (e) { setErr((e as Error).message) }
    finally { setDsBusy(s2 => ({ ...s2, [kind]: false })) }
  }
  const loadFigures = async (kind: DsKind) => {
    const file = dsPdf[kind]; const part = dsUp[kind]?.part_number
    if (!file) return
    setCurveBusy(true); setErr(null)
    try {
      const r = await datasheetFigures(file, part || undefined)
      setCurveFigs(s2 => ({ ...s2, [kind]: r.proposals }))
      setFigLoaded(s2 => ({ ...s2, [kind]: true }))
      for (const p of r.proposals) {
        const id = `${p.page}:${p.frame.join(',')}`
        if (figImg[id]) continue
        try {
          const blob = await datasheetFigureImage(file, p.page, p.frame)
          setFigImg(m => ({ ...m, [id]: URL.createObjectURL(blob) }))
        } catch { /* the proposal still stands without its picture */ }
      }
    } catch (e) { setErr((e as Error).message) } finally { setCurveBusy(false) }
  }

  const acceptCurve = async (kind: DsKind, p: DsFigureProposal, ci: number,
                             key: string, tj?: string) => {
    const part = dsUp[kind]?.part_number
    if (!part) return
    setCurveBusy(true); setErr(null)
    try {
      const c = p.curves[ci]
      // caption/page/frame travel WITH the curve: the backend cites them as the curve's source and
      // renders the plot image from the frame, so the report can show the figure the curve came
      // off. Sending only {x,y} left every confirmed curve with a blank source.
      await datasheetFigureConfirm({ part_number: part, key,
        curve: { x: c.x, y: c.y, caption: p.caption, page: p.page, frame: p.frame },
        conditions: tj ? { T_j: Number(tj) } : {} })
      setFigDone(m => ({ ...m, [`${p.key}:${ci}`]: key }))
      // NO re-confirm here any more. It existed to rebuild the engine block from the profile the
      // curve had just landed in, back when Curves came AFTER Parameters. Now that Parameters is
      // the step that follows, confirming here would mark values approved before the designer had
      // looked at them — and it is about to happen anyway, once, with the whole basis in view.
      // The curve is already persisted by the call above; nothing is lost by waiting.
    } catch (e) { setErr((e as Error).message) } finally { setCurveBusy(false) }
  }

  const publishPart = async (kind: DsKind, published: boolean) => {
    const part = dsUp[kind]?.part_number
    if (!part) return
    setCurveBusy(true); setErr(null)
    try {
      await datasheetPublish({ part_number: part, published })
      setPublished(m => ({ ...m, [part]: published }))
    } catch (e) { setErr((e as Error).message) } finally { setCurveBusy(false) }
  }

  const discardPart = async (kind: DsKind) => {
    const part = dsUp[kind]?.part_number
    if (!part) return
    setCurveBusy(true); setErr(null)
    try {
      await datasheetDiscard({ part_number: part })
      setPublished(m => { const n = { ...m }; delete n[part]; return n })
      setDsUp(s2 => { const n = { ...s2 }; delete n[kind]; return n })
      setDsConf(s2 => { const n = { ...s2 }; delete n[kind]; return n })
      setDbBlock(s2 => { const n = { ...s2 }; delete n[kind]; return n })
      setDsTab(s2 => ({ ...s2, [kind]: 'upload' }))
    } catch (e) { setErr((e as Error).message) } finally { setCurveBusy(false) }
  }

  const downloadCh7 = async () => {
    setRptBusy(true); setErr(null)
    try {
      const b = body()
      const blob = await semiconductorReport({ design: b.design, mosfet: b.mosfet, diode: b.diode,
        bridge: b.bridge, thermal: b.thermal, tj_limit: b.tj_limit } as any)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url; a.download = 'PFC_Ch7_Semiconductor_Loss.pdf'; a.click()
      URL.revokeObjectURL(url)
    } catch (e) { setErr((e as Error).message) } finally { setRptBusy(false) }
  }

  const runPlaus = async (which: Sub, block: Record<string, any>) => {
    try {
      const res = await plausibilityCheck(which, block)
      setPlaus(s => ({ ...s, [which]: res }))
    } catch { /* advisory — a failed check must never interrupt the page */ }
  }

  const onExtract = async (which: Sub, file: File | undefined) => {
    if (!file) return
    setExtBusy(s => ({ ...s, [which]: true })); setErr(null)
    try {
      const r = await semiconductorExtract(which, file)
      const cur = which === 'mosfet' ? mosfet : which === 'diode' ? diode : bridge
      setWhole(which, blockToForm(r.block as Record<string, any>, FIELDS[which], cur))
      setExtInfo(s => ({ ...s, [which]: { found: r.found, missing: r.missing,
        part: `${r.manufacturer ?? ''} ${r.part_number ?? ''}`.trim() } }))
      setDbBlock(s => ({ ...s, [which]: r.block as Record<string, unknown> }))  // keep full extracted block
      setSrcMode(s => ({ ...s, [which]: 'manual' }))   // show populated fields for confirmation
      runPlaus(which, r.block as Record<string, any>)   // extracted values get checked too
    } catch (e) { setErr((e as Error).message) } finally { setExtBusy(s => ({ ...s, [which]: false })) }
  }

  // Merge a selected/uploaded part's FULL block under the form edits: the form wins for every field it
  // exposes; the stored block supplies the rest (vf_tco, estimated params) so Calculate uses the exact
  // same block the Top-10 screen did — Results == screen for the selected part.
  // A CONFIRMED DATASHEET BLOCK IS AUTHORITATIVE. Everywhere else the form is the source and the
  // stored block only fills gaps, but once a datasheet has been reviewed and confirmed the form is
  // a view of it — and the seed defaults (DIODE0's qc = 20 nC, qrr = 120 nC, vf_tco) would
  // otherwise win the spread and silently replace a datasheet value with a number nobody chose.
  // Corrections belong on the review screen, which restamps the block.
  const merged = (which: Sub, formBlock: Record<string, unknown>) =>
    dsConf[which as DsKind]
      ? { ...formBlock, ...(dbBlock[which] || {}) }
      : { ...(dbBlock[which] || {}), ...formBlock }
  const body = (): SemiReqBody => ({
    design,
    mosfet: merged('mosfet', buildBlock(mosfet, MOSFET_FIELDS)),
    diode:  merged('diode',  buildBlock(diode, DIODE_FIELDS)),
    bridge: merged('bridge', buildBlock(bridge, BRIDGE_FIELDS)),
    thermal: { t_ambient: pnum(thermal.t_ambient) ?? 45, rth_sa: pnum(thermal.rth_sa) ?? 0.35 },
    tj_limit: tjLimit,
    // pass the approved inductor design so the GUI applies the SAME as-built per-point L the
    // report uses — keeps the on-screen losses identical to the document (no flat-L divergence).
    approved_design: approvedInductorDesign as Record<string, unknown>,
  })

  const calc = async (navigate = true) => {
    setBusy(true); setErr(null); setFigs(null)
    try {
      const b = body()
      const r = await semiconductorCalculate(b)
      setRes(r); if (navigate) setSub('results')
      if (r.validation.ok) {
        setFigBusy(true)
        semiconductorFigures({ ...b, selected_vac: design.vin_min }).then(f => setFigs(f.figures))
          .catch(() => {}).finally(() => setFigBusy(false))
      }
    } catch (e) { setErr((e as Error).message) } finally { setBusy(false) }
  }

  const downloadReport = async () => {
    setRptBusy(true); setErr(null)
    try {
      const b = body()
      const ai = approvedInductorDesign as any
      const step16_params = {
        L_uH: design.L_phi_uH, DCR_mOhm: Number(ai?.DCR_100C_mOhm ?? 28),
        C_uF: approvedCapacitorDesign?.C_total_uF ?? 2350, ESR_mOhm: approvedCapacitorDesign?.ESR_parallel_mohm ?? 5,
        Vout_V: design.vout, fsw_Hz: design.fsw, Pout_lo_W: design.pout_lo, Pout_hi_W: design.pout_hi,
        eta_lo: 0.945, eta_hi: 0.965, nch: design.nch,
        // The approved Control-Design config wins where it overlaps — it carries the
        // designer's s2 selections (R_CS…) and the live loop design (js_design_state);
        // without it the backend documents its engine defaults (e.g. R_CS 15 mΩ).
        ...(approvedControlParams ?? {}),
      }
      const blob = await docGenerateReport({
        state: confirmedState, approved_design: approvedInductorDesign,
        step15_result: approvedCapacitorDesign ? { ...approvedCapacitorDesign } : {},
        step16_params,
        semiconductor: { design: b.design, mosfet: b.mosfet, diode: b.diode, bridge: b.bridge,
          thermal: b.thermal, tj_limit: b.tj_limit },
      })
      downloadBlob(blob, reportFilename(confirmedState, 'Steps1_17'))
    } catch (e) { setErr((e as Error).message) } finally { setRptBusy(false) }
  }

  const setC = (which: Sub) => (k: string, v: any) => {
    const set = which === 'mosfet' ? setMosfet : which === 'diode' ? setDiode : setBridge
    set(s => ({ ...s, [k]: v }))
  }

  const critIn: React.CSSProperties = { ...inStyle, width: 80 }
  const critSel: React.CSSProperties = { ...inStyle, width: 'auto', maxWidth: 160 }
  const rcell: React.CSSProperties = { padding: '3px 7px', fontSize: 11, borderBottom: `1px solid ${C.border}`,
    fontFamily: 'IBM Plex Mono,monospace', color: C.text, whiteSpace: 'nowrap' }

  const dbResultsTable = (results: DbRankResult[], lossLabel: string, onPick: (r: DbRankResult) => void,
    rankedCtx?: { tamb: number; rth: number },
    note = "Worst-case loss over the 9 operating points (the @V is the line voltage where it peaks — e.g. the " +
           "boost diode peaks at HIGH line, the MOSFET usually at LOW line). Computed with the part's REAL " +
           "datasheet Vf/Rds and YOUR actual design context (devices-in-parallel, topology, companions, thermal, " +
           "as-built L). Selecting a part carries that exact configuration into the form, so this figure equals " +
           "the Results-tab value AT THAT SAME LINE VOLTAGE (not the 90 V row unless that is where it peaks) and " +
           "the report. Datasheet curves not in the DB (Eoss, Qrr/Qc, Vf slope) are estimated.") =>
    results.length === 0
      ? <div style={{ fontSize: 11, color: C.muted }}>No parts match — relax the filters.</div>
      : <div style={{ overflowX: 'auto' }}>
          {/* #6/#7 - this table is a SNAPSHOT taken with the design context as it stood when the
              ranking ran; the "worst ... loss" figure in the header is recomputed live. If the
              context has moved since, the two legitimately disagree - say so instead of leaving
              the designer to spot two different numbers for the same quantity. */}
          {(() => {
            const c = rankedCtx
            if (!c) return null
            const tNow = pnum(thermal.t_ambient) ?? _specAmbient
            const rNow = pnum(thermal.rth_sa) ?? 0.35
            if (Math.abs(c.tamb - tNow) < 0.05 && Math.abs(c.rth - rNow) < 0.005) return null
            return (
              <div style={{ fontSize: 10.5, color: C.amber, background: C.amberL,
                border: `1px solid ${C.amber}55`, borderRadius: 6,
                padding: '6px 9px', marginBottom: 8, lineHeight: 1.5 }}>
                ⚠ <b>This list is out of date.</b> It was ranked at T<sub>amb</sub> {c.tamb}°C /
                Rθ<sub>sa</sub> {c.rth} °C/W; the design now uses {tNow}°C / {rNow} °C/W. The losses
                below were computed with the older context, so they will not match the live
                “worst … loss” figure above or the Results tab. Re-run the search to refresh.
              </div>
            )
          })()}
          <table style={{ borderCollapse: 'collapse', width: '100%' }}>
            <thead><tr>{['#', `${lossLabel} loss (worst-case, at ranking)`, 'Tj', 'Rating', 'Mfr', 'Part #', ''].map(h =>
              <th key={h} style={{ ...rcell, color: C.hint, textTransform: 'uppercase', fontSize: 9 }}>{h}</th>)}</tr></thead>
            <tbody>{results.map((r, i) => (
              <tr key={i}>
                <td style={rcell}>{i + 1}</td>
                <td style={{ ...rcell, fontWeight: 700, color: C.teal }}>{r.loss_W.toFixed(2)} W
                  {r.loss_at_Vac != null && <span style={{ color: C.muted, fontWeight: 400 }}> @{r.loss_at_Vac.toFixed(0)} V</span>}</td>
                <td style={rcell}>{r.tj_max_C.toFixed(0)}°C</td>
                <td style={rcell}>{r.v_rating ?? '—'}V / {r.i_rating ?? '—'}A</td>
                <td style={rcell}>{(r.manufacturer ?? '').slice(0, 18)}</td>
                <td style={rcell}>{r.part_number}{r.datasheet_url ? <a href={r.datasheet_url} target="_blank" rel="noreferrer" style={{ color: C.muted, marginLeft: 5 }}>↗</a> : null}</td>
                <td style={rcell}><button onClick={() => onPick(r)} style={{
                  padding: '2px 9px', borderRadius: 5, cursor: 'pointer', fontSize: 10.5, fontWeight: 600,
                  border: `1px solid ${C.teal}`, background: 'rgba(45,212,191,.12)', color: C.teal }}>Select</button></td>
              </tr>))}</tbody>
          </table>
          <div style={{ fontSize: 9.5, color: C.muted, marginTop: 5 }}>{note}</div>
        </div>

  // Bottom bypass MOSFET search (conduction-only) shown inside the bridge manual form when topology = sync_bottom
  const bottomMosfetPanel = () => {
    const crit = dbCrit.bottom || {}; const results = dbRes.bottom
    return (
      <div style={{ marginTop: 12, padding: '10px 12px', border: `1px dashed ${C.teal}`, borderRadius: 8,
        background: 'rgba(45,212,191,.05)' }}>
        <div style={{ fontSize: 12, color: C.teal, fontWeight: 600, marginBottom: 2 }}>
          Bottom bypass MOSFETs — select from database
        </div>
        <div style={{ fontSize: 10, color: C.muted, marginBottom: 8 }}>
          These FETs replace the two bottom bridge diodes and commutate at line frequency, so they have
          <b> conduction loss only</b> (no switching loss). Ranked by I²·R_DS(on) at the worst operating point.
        </div>
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'flex-end', marginBottom: 8 }}>
          <label style={{ fontSize: 10.5, color: C.muted }}>Voltage ≥ (V)<br />
            <input style={critIn} value={crit.v_min ?? ''} onChange={e => setCrit('bottom', 'v_min', e.target.value)} /></label>
          <label style={{ fontSize: 10.5, color: C.muted }}>Current ≥ (A) — worst I<sub>in,rms</sub> ≈ {worstIin.toFixed(1)} A<br />
            <input style={critIn} value={crit.i_min ?? ''} onChange={e => setCrit('bottom', 'i_min', e.target.value)} /></label>
          <label style={{ fontSize: 10.5, color: C.muted }}>Mfr<br />
            <select style={critSel} value={crit.mfr ?? ''} onChange={e => setCrit('bottom', 'mfr', e.target.value)}>
              <option value="">any</option>{(dbOpts.mosfet?.manufacturers ?? []).map(o => <option key={o} value={o}>{o}</option>)}</select></label>
          <label style={{ fontSize: 10.5, color: C.muted }}>Technology<br />
            <select style={critSel} value={crit.technology ?? ''} onChange={e => setCrit('bottom', 'technology', e.target.value)}>
              <option value="">any</option>{(dbOpts.mosfet?.technology ?? []).map(o => <option key={o} value={o}>{o}</option>)}</select></label>
          <Btn variant="primary" disabled={!!dbBusy.bottom} onClick={() => runDbSearch('bottom', 'mosfet', 'conduction')}>
            {dbBusy.bottom ? '⏳ Ranking…' : '🔎 Find top 10 (lowest conduction loss)'}
          </Btn>
        </div>
        {bridge.bottom_part && <div style={{ fontSize: 11, color: C.green, marginBottom: 6 }}>
          ✓ selected bottom FET: <b>{bridge.bottom_part}</b> → R_DS(on)={bridge.rdson_bottom_25} Ω, ×{bridge.n_parallel_bottom}</div>}
        {results && dbResultsTable(results, 'FET conduction', pickBottomMosfet, dbCtx['bottom_mosfet'],
          'Conduction loss only (line-frequency commutation). Selecting a part fills the bottom-FET fields above.')}
      </div>
    )
  }

  // ── MOSFET: the datasheet-first panel (M3) ──────────────────────────────────
  // Three tabs: upload the datasheet, review and confirm what was read, then see the loss
  // breakdown. The old "From database" and "Manual / external" sources are gone for the MOSFET —
  // both fed the engine from parameters the parametric catalogue does not carry, which is what
  // made E_oss 3.4x wrong on the reference part.
  const dsCell: React.CSSProperties = { padding: '4px 8px', fontSize: 11,
    fontFamily: 'IBM Plex Mono,monospace', textAlign: 'right', color: C.text }

  const datasheetPanel = (kind: DsKind) => {
    const up = dsUp[kind]; const conf = dsConf[kind]; const req = dsReq[kind]
    const tab = dsTab[kind]; const busy = !!dsBusy[kind]
    const rows = conf?.rows ?? up?.rows ?? []
    const missing = rows.filter(r => !r.supplied && r.source_kind !== 'design')
    const designGaps = new Set(rows.filter(r => !r.supplied && r.source_kind === 'design')
                                   .map(r => r.key))
    const perPoint = (res?.per_point ?? []) as Record<string, number>[]
    const isFet = kind === 'mosfet'
    const blk = (conf?.block ?? {}) as Record<string, any>
    const tech = blk._technology as Record<string, any> | undefined
    // What the DIODE resolved to, which is what decides whether the charge dumped into the MOSFET
    // is Q_c or Q_rr. Defaults to SiC, matching the loss engine's own default.
    const dSiC = (tech?.is_sic ?? true) as boolean
    const checks = (blk._checks ?? []) as { key: string; severity: string; message: string }[]
    // Design-sourced fields, per kind. The diode has no gate, so asking for R_g would be noise.
    // The C202 gate, run over what was just extracted or confirmed (M6). ADVISORY — it is shown
    // and never enforced: a finding means "this looks wrong", and the designer decides.
    const plaus = conf?.plausibility ?? up?.plausibility
    const plausBlock = (p?: typeof plaus) => (!p || !p.checked) ? null : (
      <div style={{ marginTop: 10, padding: '8px 10px', borderRadius: 8,
        border: `1px solid ${p.ok ? C.border : C.amber}`,
        background: p.ok ? C.bg3 : 'rgba(245,158,11,.08)' }}>
        <div style={{ fontSize: 11.5, color: p.ok ? C.green : C.amber }}>
          {p.ok ? '✓ ' : '⚠ '}
          Plausibility screen: {p.ok
            ? `nothing looked wrong across ${p.checked} checks`
            : `${p.findings.length} finding${p.findings.length > 1 ? 's' : ''} in ${p.checked} checks`}
        </div>
        {p.findings.map((f, i) => (
          <div key={i} style={{ fontSize: 10.5, color: C.text, marginTop: 5, lineHeight: 1.6 }}>
            <b>{f.fields.join(', ')}</b> — {f.message}
          </div>))}
        <div style={{ fontSize: 10, color: C.hint, marginTop: 5, lineHeight: 1.6 }}>
          Advisory only, and it never blocks: these rules compare the extracted values against the
          range every catalogue part occupies, so they catch a misplaced decimal point or a value
          taken from the neighbouring column. Passing means nothing looked wrong, not that the
          extraction is right.
        </div>
      </div>)

    const designFields: [string, string, string][] = isFet
      ? [['V_GS_drive', 'V_GS drive', 'V'], ['R_g_on', 'R_g,on', 'Ω'],
         ['R_g_off', 'R_g,off', 'Ω'], ['R_th_cs', 'R_θcs', '°C/W']]
      : kind === 'bridge'
      ? [['R_th_cs', 'R_θcs', '°C/W'], ['n_parallel', 'Packages in parallel', '1 or 2'],
         ['share_worst', 'Worst-package share', '0.5–1.0']]
      : [['R_th_cs', 'R_θcs', '°C/W'], ['dies_per_package', 'Dies / package', '1 or 2']]
    // The class decides the conduction-loss form and the physics interlocks, so it is a CHOICE for
    // the two kinds that have one and absent for the bridge, which can only ever be a rectifier.
    const classOptions: [string, string][] | null =
      isFet ? [['sic_mosfet', 'Silicon carbide (SiC)'], ['si_mosfet', 'Silicon']]
      : kind === 'diode' ? [['sic_schottky', 'SiC Schottky'], ['si_diode', 'Silicon']]
      : null
    return (
      <Card style={{ marginTop: 12 }}>
        <div style={{ fontSize: 13, color: C.text, fontWeight: 600 }}>
          {isFet ? 'Boost MOSFET' : kind === 'bridge' ? 'Bridge rectifier' : 'Boost diode'} — from its datasheet</div>

        <div style={{ display: 'flex', gap: 8, alignItems: 'center', margin: '10px 0', flexWrap: 'wrap' }}>
          {/* ORDER: upload -> curves -> parameters -> results. The curves are read off the
              datasheet the agent just parsed, so they are part of what the designer is being
              asked to approve — reviewing the scalars BEFORE the plots meant confirming a
              calculation whose largest inputs had not been seen yet. Parameters now comes last
              before the result, and shows the accepted curves alongside the scalars.
              (The JSX blocks below are rendered by `tab === ...`, so their source order is not
              the tab order; each is labelled with its step number.) */}
          {([['upload', '1 · Upload datasheet'], ['curves', '2 · Curves'],
             ['parameters', '3 · Parameters'], ['results', '4 · Results']] as
             ['upload' | 'parameters' | 'curves' | 'results', string][])
            .map(([m, lbl]) => (
              <button key={m} onClick={() => setDsTab(s2 => ({ ...s2, [kind]: m }))} style={{
                padding: '4px 12px', borderRadius: 6, cursor: 'pointer', fontSize: 11, fontWeight: 600,
                border: `1px solid ${tab === m ? C.teal : C.border}`,
                background: tab === m ? 'rgba(45,212,191,.12)' : C.bg3,
                color: tab === m ? C.teal : C.muted }}>{lbl}</button>))}
        </div>

        {/* ── 1 · upload ────────────────────────────────────────────────────── */}
        {tab === 'upload' && (<>
          {req && (
            <div style={{ background: C.bg3, border: `1px solid ${C.border}`, borderRadius: 8,
              padding: '10px 12px', marginBottom: 12 }}>
              <div style={{ fontSize: 10, color: C.hint, textTransform: 'uppercase', marginBottom: 4 }}>
                What the part must clear</div>
              <div style={{ fontSize: 13, color: C.text, fontFamily: 'IBM Plex Mono,monospace' }}>
                {isFet
                  ? <>V<sub>DSS</sub> ≥ {req.V_DSS_min} V &nbsp;·&nbsp; I<sub>D</sub> ≥ {req.I_D_min} A</>
                  : kind === 'bridge'
                  ? <>V<sub>RRM</sub> ≥ {req.V_RRM_min} V &nbsp;·&nbsp; I<sub>F(AV)</sub> ≥ {req.I_F_AV_min} A
                      {(req.I_per_package ?? 0) > 0 && (req.basis?.n_parallel ?? 1) > 1 &&
                        <> &nbsp;·&nbsp; {req.I_per_package} A per package</>}</>
                  : <>V<sub>RRM</sub> ≥ {req.V_RRM_min} V &nbsp;·&nbsp; I<sub>F(AV)</sub> ≥ {req.I_F_AV_min} A
                      &nbsp;·&nbsp; peak {req.I_F_pk} A</>}
              </div>
              <div style={{ fontSize: 10.5, color: C.muted, marginTop: 5, lineHeight: 1.6 }}>
                {req.statement}
              </div>
              <div style={{ fontSize: 10, color: C.hint, marginTop: 5, lineHeight: 1.6 }}>
                {req.note}
              </div>
            </div>)}

          <div style={{ fontSize: 11.5, color: C.muted, marginBottom: 8, lineHeight: 1.7 }}>
            Upload the part's PDF datasheet. Its tables are read into the calculation inputs, which
            you then review before anything is computed. If the PDF has no text layer it is refused
            rather than returning an empty result — a scanned datasheet and a part with no
            parameters would otherwise look identical.
          </div>
          <input type="file" accept=".pdf" disabled={busy} style={{ fontSize: 11 }}
            onChange={e => { doUpload(kind, e.target.files?.[0]); e.currentTarget.value = '' }} />
          {busy && <span style={{ fontSize: 11, color: C.muted, marginLeft: 8 }}>⏳ reading…</span>}

          {up && up.ok && (
            <div style={{ marginTop: 10, fontSize: 11.5, color: C.green }}>
              ✓ {up.part_number} — {rows.filter(r => r.supplied).length} values read from{' '}
              {up.tables_kept} tables ({up.tables_rejected} figure regions rejected)
              {up.stored && !up.stored.changed &&
                <span style={{ color: C.muted }}> · identical to the copy already on file</span>}
            </div>)}
          {up && (up.variants?.length ?? 0) > 1 && (
            <div style={{ marginTop: 12, padding: '10px 12px', borderRadius: 8, background: C.bg3,
              border: `1px solid ${up.variant_required ? C.amber : C.green}` }}>
              <div style={{ fontSize: 11.5, color: C.text, marginBottom: 6 }}>
                {up.variant_required
                  ? <>⚠ This datasheet covers <b>{up.variants!.length} parts</b>. Which one are you
                      using?</>
                  : <>✓ Read as <b>{up.variant}</b>.</>}
              </div>
              <div style={{ fontSize: 10, color: C.hint, marginBottom: 8, lineHeight: 1.6 }}>
                A series document bands the values that differ between its parts — forward voltage
                and capacitance here. Until one is chosen every band is kept, so the review list
                shows the same parameter more than once rather than one being picked for you.
              </div>
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
                <select value={up.variant || ''} disabled={dsBusy[kind]}
                  onChange={e => e.target.value &&
                    doUpload(kind, dsPdf[kind], e.target.value)}
                  style={{ ...inStyle, width: 190, padding: '3px 6px', fontSize: 11.5 }}>
                  <option value="">— choose the part number —</option>
                  {up.variants!.map(v => <option key={v} value={v}>{v}</option>)}
                </select>
                {dsBusy[kind] && <span style={{ fontSize: 10.5, color: C.hint }}>re-reading…</span>}
              </div>
            </div>)}

          {up && up.ok && (up.cross_check?.length ?? 0) > 0 && (
            <div style={{ marginTop: 8, fontSize: 10.5, color: C.amber }}>
              {up.cross_check!.map((c, i) => <div key={i}>⚠ {c.message}</div>)}
            </div>)}
          {up && up.ok && plausBlock(up.plausibility)}
        </>)}

        {/* ── 2 · parameters ────────────────────────────────────────────────── */}
        {tab === 'parameters' && (rows.length === 0
          ? <div style={{ fontSize: 11.5, color: C.hint }}>Upload a datasheet first.</div>
          : (<>
            <div style={{ fontSize: 11.5, color: C.muted, marginBottom: 8, lineHeight: 1.7 }}>
              Only the values this calculation consumes are listed, each with the conditions it was
              measured at and where it is used. Anything not found is at the top. Correct a value
              and it is stored as <i>corrected</i> with the extracted original kept beside it.
            </div>

            {classOptions && (
              <div style={{ marginBottom: 10 }}>
                <div style={{ fontSize: 10.5, color: C.hint, textTransform: 'uppercase',
                  marginBottom: 4 }}>Device class</div>
                <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                  <select value={dsDesign[kind].device_class ?? classOptions[0][0]}
                    disabled={dsBusy[kind]}
                    onChange={e => {
                      const dc = e.target.value
                      setDsDesign(d => ({ ...d, [kind]: { ...d[kind], device_class: dc } }))
                      // RE-READ, not relabel: the class decides which parameters are required and
                      // which conduction form the block is built with, so the datasheet has to go
                      // through extraction again under it.
                      if (dsPdf[kind]) doUpload(kind, dsPdf[kind], dsUp[kind]?.variant || undefined, dc)
                    }}
                    style={{ ...inStyle, width: 210, padding: '3px 6px', fontSize: 11.5 }}>
                    {classOptions.map(([v, lbl]) => <option key={v} value={v}>{lbl}</option>)}
                  </select>
                  {tech?.override && (
                    <span style={{ fontSize: 10.5, color: C.amber }}>
                      ⚠ the datasheet says otherwise — {String(tech.basis ?? '')}
                    </span>)}
                </div>
                <div style={{ fontSize: 10, color: C.hint, marginTop: 5, lineHeight: 1.6 }}>
                  It selects the conduction-loss form and the physics interlocks. Where the
                  datasheet states the technology outright, published evidence wins over this
                  choice and the override is reported above rather than made quietly.
                </div>
              </div>)}

            <div style={{ fontSize: 10.5, color: C.hint, textTransform: 'uppercase', marginBottom: 4 }}>
              Your design decides these — no datasheet supplies them</div>
            <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginBottom: 10 }}>
              {designFields.map(([k, lbl, u]) => (
                <label key={k} style={{ fontSize: 10.5,
                  color: designGaps.has(k) && !(dsDesign[kind][k] ?? '') ? C.amber : C.muted }}>
                  {lbl} ({u}){designGaps.has(k) && !(dsDesign[kind][k] ?? '') ? ' — needed' : ''}<br />
                  <input style={{ ...inStyle, width: 90, padding: '2px 6px', fontSize: 11.5,
                    borderColor: designGaps.has(k) && !(dsDesign[kind][k] ?? '') ? C.amber : undefined }}
                    value={dsDesign[kind][k] ?? ''}
                    onChange={e => setDsDesign(d => ({ ...d,
                      [kind]: { ...d[kind], [k]: e.target.value } }))} /></label>))}
            </div>

            {missing.length > 0 && (
              <div style={{ fontSize: 10.5, color: C.amber, marginBottom: 6 }}>
                {missing.length} value{missing.length > 1 ? 's' : ''} still unsupplied — the engine
                will not run on a default for any of them.
              </div>)}

            {/* Design-sourced parameters are the editable row ABOVE; listing them again here
                asked for the same thing two and three times over (bridge topology appeared in the
                selector, the design row and this list). A review row exists to check a value
                against the datasheet it came from, which a design decision never has. */}
            <div style={{ maxHeight: 420, overflowY: 'auto' }}>
              {rows.filter(r => r.source_kind !== 'design' && r.key !== 'device_class').map(r => (
                <ReviewRow key={r.key} r={r} edit={dsEdits[kind][r.key]}
                  onEdit={(k, v) => setDsEdits(o => ({ ...o,
                    [kind]: { ...o[kind], [k]: v } }))} />))}
            </div>

            {/* THE CURVES ARE PART OF WHAT IS BEING CONFIRMED. This step is the last thing before
                the losses are computed, so it has to show the WHOLE basis — and the curves are the
                largest inputs in it, not a footnote. Listed separately from the scalar rows
                because there is nothing to edit: a curve is accepted against its plot on the
                previous step, or it is not there at all. */}
            {(() => {
              const curved = rows.filter(r => r.has_curve)
              return (
                <div style={{ marginTop: 12, padding: '9px 11px', borderRadius: 8,
                  border: `1px solid ${curved.length ? C.green : C.border}`, background: C.bg3 }}>
                  <div style={{ fontSize: 10.5, color: C.hint, textTransform: 'uppercase' }}>
                    Curves accepted from the datasheet plots</div>
                  {curved.length === 0
                    ? <div style={{ fontSize: 10.5, color: C.muted, marginTop: 5, lineHeight: 1.6 }}>
                        None yet. Every quantity below is a table value or a fitted shape. Step 2
                        offers the plots this calculation can read — accepting them replaces the
                        fits with the vendor's own measured curves.
                      </div>
                    : <div style={{ marginTop: 5 }}>
                        {curved.map(r => (
                          <div key={r.key} style={{ fontSize: 10.5, color: C.text,
                            lineHeight: 1.7 }}>
                            <span style={{ color: C.green }}>✓</span>{' '}
                            <b dangerouslySetInnerHTML={{ __html: r.label }} />{' '}
                            <span style={{ color: C.muted }}>
                              — {r.curve_points} points
                              {r.curve_source?.page ? `, page ${r.curve_source.page}` : ''}
                              {' · '}{r.destination}
                            </span>
                          </div>))}
                      </div>}
                </div>)
            })()}

            <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginTop: 10 }}>
              <Btn variant="primary" disabled={busy} onClick={() => doConfirm(kind)}>
                {busy ? '⏳ confirming…' : '✓ Confirm these values & calculate'}</Btn>
              {conf && (conf.validation.ok
                ? <span style={{ fontSize: 11, color: C.green }}>
                    ✓ every engine input has a source — nothing fell back to a default</span>
                : <span style={{ fontSize: 11, color: C.amber }}>
                    {conf.validation.defaulted.length} input(s) would use an engine default</span>)}
            </div>
            {conf && conf.validation.defaulted.map((d, i) => (
              <div key={i} style={{ fontSize: 10.5, color: C.amber, marginTop: 3 }}>⚠ {d.message}</div>))}
            {plausBlock(plaus)}

            {/* Which recovery model the datasheet put this diode into, and why. `is_sic` defaults
                to true in the engine, so a silicon part read as SiC would be computed by the wrong
                formula with nothing missing to give it away. */}
            {!isFet && tech && (
              <div style={{ marginTop: 10, padding: '8px 10px', borderRadius: 8,
                border: `1px solid ${tech.override ? C.amber : C.border}`,
                background: tech.override ? 'rgba(245,158,11,.08)' : C.bg3 }}>
                <div style={{ fontSize: 11.5, color: tech.override ? C.amber : C.green }}>
                  {tech.override ? '⚠ ' : '✓ '}
                  Calculated as <b>{tech.is_sic ? 'SiC Schottky' : 'silicon'}</b>
                  {tech.override && ' — not the technology this sub-tab assumed'}
                </div>
                <div style={{ fontSize: 10.5, color: C.muted, marginTop: 4, lineHeight: 1.6 }}>
                  {tech.basis}. {tech.is_sic
                    ? 'Its capacitive charge Q_c is swept through the MOSFET at turn-on; the diode itself has no recovery loss.'
                    : 'Its recovery charge Q_rr is split between the MOSFET and the diode — for a CCM boost PFC this is usually the largest single loss term in the chapter.'}
                </div>
              </div>)}
            {kind === 'bridge' && (
              <div style={{ marginTop: 12, padding: '10px 12px', borderRadius: 8,
                border: `1px solid ${C.border}`, background: C.bg3 }}>
                <div style={{ fontSize: 10.5, color: C.hint, textTransform: 'uppercase',
                  marginBottom: 6 }}>Bridge topology</div>
                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
                  {([['diode', 'Four diodes'],
                     ['sync_bottom', 'Sync bottom (bypass MOSFETs)']] as [string, string][])
                    .map(([v, lbl]) => (
                      <button key={v} onClick={() => setDsDesign(d => ({ ...d,
                        bridge: { ...d.bridge, bridge_topology: v } }))} style={{
                        padding: '4px 10px', borderRadius: 6, cursor: 'pointer', fontSize: 11,
                        fontWeight: 600,
                        border: `1px solid ${dsDesign.bridge.bridge_topology === v ? C.teal : C.border}`,
                        background: dsDesign.bridge.bridge_topology === v
                          ? 'rgba(45,212,191,.12)' : C.bg3,
                        color: dsDesign.bridge.bridge_topology === v ? C.teal : C.muted }}>{lbl}</button>))}
                </div>
                {dsDesign.bridge.bridge_topology === 'sync_bottom' && (
                  <div style={{ marginTop: 8 }}>
                    <label style={{ fontSize: 10.5, color: C.muted }}>
                      Bypass MOSFET — part number, as confirmed on the MOSFET tab<br />
                      <input style={{ ...inStyle, width: 260, padding: '2px 6px', fontSize: 11.5 }}
                        value={dsDesign.bridge.bottom_mosfet_part ?? ''}
                        placeholder={dsUp.mosfet?.part_number || 'e.g. IMZA65R033M2H'}
                        onChange={e => setDsDesign(d => ({ ...d,
                          bridge: { ...d.bridge, bottom_mosfet_part: e.target.value } }))} /></label>
                    <div style={{ fontSize: 10, color: C.hint, marginTop: 5, lineHeight: 1.6 }}>
                      In this topology the bottom two positions are MOSFETs, so they are selected the
                      same way every other MOSFET is — requirement, upload, review, confirm — and
                      named here. One upload path used twice, rather than a second extractor.
                    </div>
                  </div>)}
              </div>)}

            {!isFet && checks.filter(c => c.severity === 'check').map((c, i) => (
              <div key={i} style={{ fontSize: 10.5, color: C.amber, marginTop: 4, lineHeight: 1.6 }}>
                ⚠ <b>{c.key}</b> — {c.message}</div>))}
            {!isFet && checks.filter(c => c.severity === 'note').map((c, i) => (
              <div key={i} style={{ fontSize: 10, color: C.hint, marginTop: 3, lineHeight: 1.6 }}>
                {c.message}</div>))}
          </>))}

        {/* ── 3 · curves ────────────────────────────────────────────────────── */}
        {tab === 'curves' && (<>
          <div style={{ fontSize: 11.5, color: C.muted, marginBottom: 8, lineHeight: 1.7 }}>
            Values a table cannot carry have been standing in as fitted shapes — a constant forward
            drop where the datasheet gives V<sub>F</sub> at one current per temperature, a
            Q<sub>c</sub> moved to the bus by an assumed power law. Those shapes are printed on the
            page. Each proposal below is read off the plot and shown <b>beside the figure it came
            from</b>: accept one only if the curve is the one you see.
          </div>
          <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginBottom: 10 }}>
            <Btn variant="primary" disabled={curveBusy || !dsPdf[kind]}
              onClick={() => loadFigures(kind)}>
              {curveBusy ? '⏳ reading the plots…' : '📈 Read the datasheet figures'}</Btn>
            {!dsPdf[kind] && <span style={{ fontSize: 11, color: C.hint }}>
              Upload the datasheet first.</span>}
          </div>

          {(curveFigs[kind] ?? []).map((p, pi) => {
            const id = `${p.page}:${p.frame.join(',')}`
            const cc = p.cross_check
            return (
              <div key={pi} style={{ border: `1px solid ${C.border}`, borderRadius: 8,
                padding: 12, marginBottom: 12, background: C.bg3 }}>
                <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap' }}>
                  {figImg[id] && <img src={figImg[id]} alt={p.caption}
                    style={{ width: 280, maxWidth: '100%', borderRadius: 6, background: '#fff' }} />}
                  <div style={{ flex: 1, minWidth: 260 }}>
                    <div style={{ fontSize: 12, color: C.text, fontWeight: 600 }}>
                      {p.caption || `page ${p.page}`}</div>
                    <div style={{ fontSize: 10.5, color: C.muted, marginTop: 4, lineHeight: 1.6 }}>
                      → <b>{p.key}</b><br />
                      x: {p.axes.x} <i>({p.x_scale}, {p.x_range[0]}…{p.x_range[1]})</i><br />
                      y: {p.axes.y} <i>({p.y_scale}, {p.y_range[0]}…{p.y_range[1]})</i><br />
                      {p.n_curves} curve{p.n_curves > 1 ? 's' : ''} · calibration residual{' '}
                      {(p.residual * 100).toFixed(2)}%
                      {p.swapped && <> · axes transposed to {p.key}'s own order</>}
                    </div>
                    <div style={{ fontSize: 10.5, marginTop: 6, lineHeight: 1.6,
                      color: cc.checked ? (cc.agrees ? C.green : C.amber) : C.hint }}>
                      {cc.checked ? (cc.agrees ? '✓ ' : '⚠ ') : ''}{cc.note}
                    </div>
                    {p.assignment && (
                      <div style={{ fontSize: 10.5, marginTop: 4, lineHeight: 1.6,
                        color: p.assignment.verified ? C.green : C.amber }}>
                        {p.assignment.verified ? '✓ ' : '⚠ '}
                        {p.assignment.verified ? 'Temperatures matched to traces — ' : ''}
                        {p.assignment.reason}
                      </div>)}
                  </div>
                </div>

                <div style={{ marginTop: 10, display: 'flex', flexDirection: 'column', gap: 6 }}>
                  {p.curves.map((c: DsCurve, ci: number) => {
                    const done = figDone[`${p.key}:${ci}`]
                    const rgb = c.color?.length === 3
                      ? `rgb(${c.color.map(v => Math.round(v * 255)).join(',')})` : C.muted
                    return (
                      <div key={ci} style={{ display: 'flex', gap: 8, alignItems: 'center',
                        flexWrap: 'wrap', fontSize: 10.5, color: C.muted }}>
                        <span style={{ width: 22, height: 3, background: rgb, borderRadius: 2 }} />
                        {c.T_j != null && (
                          <span style={{ color: C.text, fontWeight: 600, minWidth: 62 }}>
                            T<sub>J</sub> = {c.T_j}&nbsp;°C</span>)}
                        <span style={{ fontFamily: 'IBM Plex Mono,monospace' }}>
                          {c.n_points} pts · x {c.x_span[0].toPrecision(3)}…{c.x_span[1].toPrecision(3)}
                          {' '}· y {c.y_span[0].toPrecision(3)}…{c.y_span[1].toPrecision(3)}
                        </span>
                        {/* Which trace the datasheet's OWN table lands on. On a plot whose traces
                            are different quantities — C_iss / C_oss / C_rss together — this is the
                            only thing distinguishing them, and accepting the wrong one puts
                            ~1700 pF where 7 pF belongs. */}
                        {cc.checked && cc.agrees && cc.curve_index === ci && (
                          <span style={{ color: C.green, fontWeight: 600 }}>
                            ✓ matches the table
                            {cc.expected != null && cc.got != null &&
                              ` — reads ${cc.got.toPrecision(3)} where it states ` +
                              `${cc.expected.toPrecision(3)}`}
                          </span>)}
                        {cc.checked && cc.agrees && cc.curve_index !== ci && p.n_curves > 1 && (
                          <span style={{ color: C.amber }}>
                            not the trace the table matches</span>)}
                        {done
                          ? <span style={{ color: C.green }}>✓ accepted as {done}</span>
                          : (<>
                            {p.per_temperature && (
                              <input placeholder="T_j °C" id={`tj-${p.key}-${ci}`}
                                defaultValue={c.T_j != null ? String(c.T_j) : ''}
                                style={{ ...inStyle, width: 74, padding: '2px 6px', fontSize: 11 }} />)}
                            <Btn disabled={curveBusy} onClick={() => acceptCurve(kind, p, ci, p.key,
                              (document.getElementById(`tj-${p.key}-${ci}`) as HTMLInputElement)?.value)}>
                              Accept</Btn>
                            {p.key === 'V_F_vs_IF' && (
                              <Btn disabled={curveBusy} onClick={() => acceptCurve(kind, p, ci,
                                'V_F_vs_IF_hot',
                                (document.getElementById(`tj-${p.key}-${ci}`) as HTMLInputElement)?.value)}>
                                Accept as HOT curve</Btn>)}
                          </>)}
                      </div>)
                  })}
                </div>
              </div>)
          })}

          {(curveFigs[kind] ?? []).length > 0 && (
            <div style={{ marginTop: 4, display: 'flex', gap: 8, alignItems: 'center',
              flexWrap: 'wrap' }}>
              <Btn variant="primary" disabled={curveBusy || dsBusy[kind]}
                onClick={() => setDsTab(s2 => ({ ...s2, [kind]: 'parameters' }))}>
                ✓ Done — review the parameters</Btn>
              <span style={{ fontSize: 10.5, color: C.hint }}>
                Accept as many curves as apply first; each one is stored as you go. They appear
                with the scalars on the next step, so you approve the whole basis at once.
              </span>
            </div>)}

          {(curveFigs[kind] ?? []).length === 0 && !curveBusy && figLoaded[kind] && (
            <div style={{ fontSize: 10.5, color: C.hint, lineHeight: 1.6 }}>
              <b>No figure from this datasheet can be used yet.</b> Two separate things have to hold
              and the reason matters, so neither is glossed over:
              <br />· its axes must READ — the tick labels have to fit a consistent linear or
              logarithmic scale. A plot drawn without an axis frame, or with its labels split into
              fragments, is skipped rather than guessed at.
              <br />· the figure must be one this calculation CONSUMES. Curve targets exist for the
              diode (forward drop, capacitive charge and energy, junction capacitance, reverse
              current), for the bridge derating curve, and for the MOSFET (E<sub>oss</sub>(V),
              C<sub>rss</sub>(V), and R<sub>DS(on)</sub> against both junction temperature and
              drain current). A figure outside that set is read but not offered, because nothing
              would consume it.
            </div>)}

          {(curveFigs[kind] ?? []).length === 0 && !curveBusy && !figLoaded[kind] && (
            <div style={{ fontSize: 10.5, color: C.hint, lineHeight: 1.6 }}>
              Nothing read yet. A figure is only offered when its tick labels fit a consistent
              linear or logarithmic scale — a plot whose axes cannot be read is skipped rather than
              guessed at.
            </div>)}
        </>)}

        {/* ── 4 · results ───────────────────────────────────────────────────── */}
        {tab === 'results' && (perPoint.length === 0
          ? <div style={{ fontSize: 11.5, color: C.hint, lineHeight: 1.7 }}>
              {(() => {
                // Name what is missing. "Run Calculate" was unhelpful once confirming became the
                // trigger: the reason this table is empty is almost always another component, not
                // a button the designer failed to press.
                const waiting = (['bridge', 'mosfet', 'diode'] as DsKind[])
                  .filter(k => k !== kind && !dsConf[k]?.block)
                  .map(k => k === 'mosfet' ? 'MOSFET' : k === 'diode' ? 'boost diode' : 'bridge')
                if (!dsConf[kind]?.block)
                  return 'Accept the curves that apply, then confirm the parameters — the losses '
                       + 'are calculated as soon as you do.'
                return waiting.length === 0
                  ? 'Confirm the parameters to calculate.'
                  : `This part is confirmed. The three devices share one heatsink, so their `
                    + `losses and junction temperatures are solved together — waiting on the `
                    + `${waiting.join(' and the ')}.`
              })()}</div>
          : (<>
            <div style={{ fontSize: 11.5, color: C.muted, marginBottom: 8, lineHeight: 1.7 }}>
              {isFet ? 'MOSFET' : 'Boost-diode'} loss by mechanism at every input voltage, for all
              {' '}{design.nch} channels together. These are the engine's own per-point numbers, not
              a second calculation — a presentation layer that recomputes is how a screen comes to
              disagree with the report.
            </div>
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                {/* HEADERS FOLLOW THE RESOLVED TECHNOLOGY, and match Chapter 7's tables word for
                    word. A SiC Schottky has no reverse recovery: what lands in the MOSFET at
                    turn-on is the diode's junction CHARGE Q_c, and calling that column "Recovery"
                    described a mechanism the part does not have. The screen and the report must
                    also not name the same number two different things. */}
                <thead><tr>{(isFet
                  ? ['V_ac', 'P_out', 'Conduction', 'Switching', 'E_oss',
                     dSiC ? 'Diode Q_c → FET' : 'Diode Q_rr → FET', 'Leakage', 'TOTAL', 'T_j']
                  : kind === 'bridge'
                  ? ['V_ac', 'P_out', 'Top (diodes)', 'Bottom (sync FET)', 'TOTAL', 'T_j']
                  : ['V_ac', 'P_out', 'Conduction', dSiC ? 'Recovery (Q_rr = 0)' : 'Recovery Q_rr',
                     'Blocking (leak)', 'TOTAL', 'T_j',
                     dSiC ? 'Q_c → MOSFET' : 'Q_rr → MOSFET']).map(h =>
                       <th key={h} style={th}>{h}</th>)}</tr></thead>
                <tbody>
                  {perPoint.map((p, i) => {
                    const key = isFet ? 'Tj_FET' : kind === 'bridge' ? 'Tj_BRIDGE_top' : 'Tj_DIODE'
                    const hot = p[key] === Math.max(...perPoint.map(x => x[key] ?? 0))
                    return (
                      <tr key={i} style={{ background: hot ? 'rgba(245,158,11,.08)' : 'transparent' }}>
                        <td style={dsCell}>{(p.Vac ?? 0).toFixed(0)} V</td>
                        <td style={dsCell}>{(p.Po ?? 0).toFixed(0)} W</td>
                        {kind === 'bridge' ? (<>
                          <td style={dsCell}>{(p.P_BRIDGE_top ?? 0).toFixed(2)}</td>
                          <td style={dsCell}>{(p.P_BRIDGE_bottom ?? 0).toFixed(2)}</td>
                          <td style={{ ...dsCell, fontWeight: 700, color: C.teal }}>
                            {(p.P_BRIDGE_total ?? 0).toFixed(2)} W</td>
                        </>) : isFet ? (<>
                          <td style={dsCell}>{(p.P_FET_cond ?? 0).toFixed(2)}</td>
                          <td style={dsCell}>{(p.P_FET_sw ?? 0).toFixed(2)}</td>
                          <td style={dsCell}>{(p.P_FET_coss ?? 0).toFixed(2)}</td>
                          <td style={dsCell}>{(p.P_FET_rr ?? 0).toFixed(2)}</td>
                          <td style={dsCell}>{(p.P_FET_leak ?? 0).toFixed(2)}</td>
                          <td style={{ ...dsCell, fontWeight: 700, color: C.teal }}>
                            {(p.P_FET_total ?? 0).toFixed(2)} W</td>
                        </>) : (<>
                          {/* the engine's own key names — P_DIODE_cond/_sw do not exist and
                              would have rendered a silent column of zeros beside a correct total */}
                          <td style={dsCell}>{(p.P_D_cond ?? 0).toFixed(2)}</td>
                          <td style={dsCell}>{(p.P_D_sw ?? 0).toFixed(2)}</td>
                          <td style={dsCell}>{(p.P_D_leak ?? 0).toFixed(3)}</td>
                          <td style={{ ...dsCell, fontWeight: 700, color: C.teal }}>
                            {(p.P_DIODE_total ?? 0).toFixed(2)} W</td>
                        </>)}
                        <td style={{ ...dsCell, color: hot ? C.amber : C.text }}>
                          {(p[key] ?? 0).toFixed(0)} °C</td>
                        {!isFet && <td style={{ ...dsCell, color: C.amber }}>
                          {(p.P_FET_rr ?? 0).toFixed(2)} W</td>}
                      </tr>)
                  })}
                </tbody>
              </table>
            </div>
            {/* MOVED HERE from the summary Results tab along with the columns it explains. A zero
                that is CORRECT looks identical to a zero that is broken, so it is worth saying
                which — and it belongs beside the Recovery column, which now lives only here. */}
            {!isFet && kind === 'diode' && perPoint.every(p => (p.P_D_sw ?? 0) === 0) && (
              <div style={{ fontSize: 10.5, color: C.text, marginTop: 8, padding: '7px 10px',
                borderRadius: 6, background: C.bg3, border: `1px solid ${C.border}`,
                lineHeight: 1.6 }}>
                <b>The recovery column is exactly zero, and that is correct.</b> This part has no
                minority-carrier recovery, so conduction and blocking are its whole loss. Its
                junction charge Q<sub>c</sub> is real, but it is dissipated in the MOSFET channel at
                turn-on rather than in the diode — that is the <i>Q<sub>c</sub> &#8594; MOSFET</i>
                column on the right, and it is counted once, in the MOSFET total. The recovery
                column separates from conduction only for a silicon diode.
              </div>)}
            {dsUp[kind]?.part_number && (
              <div style={{ marginTop: 12, padding: '10px 12px', borderRadius: 8,
                border: `1px solid ${published[dsUp[kind]!.part_number!] ? C.green : C.border}`,
                background: C.bg3 }}>
                <div style={{ fontSize: 11.5, color: C.text, marginBottom: 6 }}>
                  {published[dsUp[kind]!.part_number!]
                    ? <>✓ <b>{dsUp[kind]!.part_number}</b> is in the parts library.</>
                    : <><b>{dsUp[kind]!.part_number}</b> is stored for this design only.</>}
                </div>
                <div style={{ fontSize: 10, color: C.hint, marginBottom: 8, lineHeight: 1.6 }}>
                  Uploading writes the file so it can be reviewed, but that is not the same as
                  adding it to the shared library. Add it once the losses above look right — a
                  datasheet uploaded by mistake should never end up as a part everyone else builds
                  on.
                </div>
                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                  <Btn variant={published[dsUp[kind]!.part_number!] ? undefined : 'primary'}
                    disabled={curveBusy}
                    onClick={() => publishPart(kind, !published[dsUp[kind]!.part_number!])}>
                    {published[dsUp[kind]!.part_number!]
                      ? '↩ Remove from library' : '➕ Add this part to the library'}</Btn>
                  {!published[dsUp[kind]!.part_number!] && (
                    <Btn disabled={curveBusy} onClick={() => discardPart(kind)}>
                      🗑 Wrong datasheet — discard it</Btn>)}
                </div>
              </div>)}

            <div style={{ fontSize: 10.5, color: C.muted, marginTop: 8, lineHeight: 1.6 }}>
              {isFet ? (<>
                Gate-drive loss is <b>{(perPoint[0]?.P_gate_driver ?? 0).toFixed(3)} W</b> and is not
                in the totals above: it is dissipated in the driver and the gate resistors, not in the
                MOSFET junction, so it belongs in the efficiency budget but not in the device
                temperature rise. The highlighted row is the hottest operating point.
              </>) : (<>
                The last column is the charge this diode dumps into the <b>MOSFET</b> at every
                turn-on — it is booked to the MOSFET's junction, not this one, but it is the diode
                that decides it. For a silicon diode it is typically the largest single loss term in
                the whole chapter; a SiC Schottky has no recovery charge and only its much smaller
                junction charge Q_c appears there. The highlighted row is the hottest operating point.
              </>)}
            </div>
          </>))}
      </Card>
    )
  }

  const compForm = (fields: Field[], state: Record<string, any>, which: Sub, title: string, devLoss?: [string, string]) => {
    const mode = srcMode[which]; const opts = dbOpts[which] || {}; const crit = dbCrit[which] || {}; const results = dbRes[which]
    return (
    <Card style={{ marginTop: 12 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
        <div style={{ fontSize: 13, color: C.text, fontWeight: 600 }}>{title}</div>
        {devLoss && (
          <div style={{ fontSize: 11, color: C.teal, fontFamily: 'IBM Plex Mono,monospace' }}>
            worst {devLoss[0]} loss {devLoss[1]}
          </div>
        )}
      </div>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', margin: '10px 0', flexWrap: 'wrap' }}>
        <span style={{ fontSize: 11, color: C.muted }}>Source:</span>
        {([['database', '🔍 From database'], ['manual', '✎ Manual / external'], ['upload', '📄 Upload datasheet']] as [SrcMode, string][])
          .map(([m, lbl]) => (
            <button key={m} onClick={() => {
                setSrcMode(s => ({ ...s, [which]: m }))
                if (m === 'manual') setDbBlock(s => { const n = { ...s }; delete n[which]; return n })  // pure manual → drop stored datasheet block
              }} style={{
              padding: '4px 10px', borderRadius: 6, cursor: 'pointer', fontSize: 11, fontWeight: 600,
              border: `1px solid ${mode === m ? C.teal : C.border}`, background: mode === m ? 'rgba(45,212,191,.12)' : C.bg3,
              color: mode === m ? C.teal : C.muted }}>{lbl}</button>
          ))}
      </div>

      {mode === 'database' && (<>
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'flex-end', marginBottom: 8 }}>
          <label style={{ fontSize: 10.5, color: C.muted }}>Voltage ≥ (V)<br />
            <input style={critIn} value={crit.v_min ?? ''} onChange={e => setCrit(which, 'v_min', e.target.value)} /></label>
          <label style={{ fontSize: 10.5, color: C.muted }}>Current ≥ (A) — worst I<sub>in,rms</sub> ≈ {worstIin.toFixed(1)} A{which === 'diode' ? ` (${design.nch} phases)` : ''}<br />
            <input style={critIn} value={crit.i_min ?? ''} onChange={e => setCrit(which, 'i_min', e.target.value)} /></label>
          <label style={{ fontSize: 10.5, color: C.muted }}>Tj ≥ (°C)<br />
            <input style={critIn} value={crit.tj_min ?? ''} onChange={e => setCrit(which, 'tj_min', e.target.value)} /></label>
          <label style={{ fontSize: 10.5, color: C.muted }}>Manufacturer<br />
            <select style={critSel} value={crit.mfr ?? ''} onChange={e => setCrit(which, 'mfr', e.target.value)}>
              <option value="">any</option>{(opts.manufacturers ?? []).map(o => <option key={o} value={o}>{o}</option>)}</select></label>
          <label style={{ fontSize: 10.5, color: C.muted }}>Mounting<br />
            <select style={critSel} value={crit.mounting ?? ''} onChange={e => setCrit(which, 'mounting', e.target.value)}>
              <option value="">any</option>{(opts.mounting ?? []).map(o => <option key={o} value={o}>{o}</option>)}</select></label>
          <label style={{ fontSize: 10.5, color: C.muted }}>Footprint / package<br />
            <input style={{ ...critIn, width: 120 }} value={crit.package ?? ''} placeholder="e.g. TO247"
              onChange={e => setCrit(which, 'package', e.target.value)} /></label>
          {which === 'mosfet' && (
            <label style={{ fontSize: 10.5, color: C.muted }}>Technology<br />
              <select style={critSel} value={crit.technology ?? ''} onChange={e => setCrit(which, 'technology', e.target.value)}>
                <option value="">any</option>{(opts.technology ?? []).map(o => <option key={o} value={o}>{o}</option>)}</select></label>
          )}
          {(which === 'bridge' || which === 'mosfet') && (
            // Blank does NOT mean 1 — runDbSearch falls back to the part form's own n_parallel
            // (which defaults to 2 for the bridge). Show that effective value so the box can never
            // disagree with what is actually ranked.
            <label style={{ fontSize: 10.5, color: C.muted }}>Devices in parallel<br />
              <input style={{ ...critIn, width: 70 }}
                value={crit.n_parallel ?? ((which === 'bridge' ? bridge.n_parallel : mosfet.n_parallel) ?? '')}
                placeholder="1"
                onChange={e => setCrit(which, 'n_parallel', e.target.value)} /></label>
          )}
          <Btn variant="primary" disabled={!!dbBusy[which]} onClick={() => runDbSearch(which, which)}>
            {dbBusy[which] ? '⏳ Ranking…' : '🔎 Find top 10 (lowest loss)'}
          </Btn>
        </div>
        {results && dbResultsTable(results, which === 'mosfet' ? 'FET' : which, r => pickDbPart(which, r), dbCtx[which])}
      </>)}

      {mode === 'manual' && (
        <div>
          {fields.map(f => <FieldRow key={f.key} f={f} state={state} onSet={setC(which)} />)}
          {/* Advisory only. A flagged value is still usable — the designer confirms or corrects. */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 8 }}>
            <Btn onClick={() => runPlaus(which, merged(which, buildBlock(state, fields)) as Record<string, any>)}>
              ⌕ Sanity-check values</Btn>
            {plaus[which] && plaus[which]!.ok && (
              <span style={{ fontSize: 11, color: C.green }}>
                ✓ nothing looked wrong ({plaus[which]!.checked} checks) — this does not confirm the
                values are right, only that none is impossible
              </span>)}
            {plaus[which] && !plaus[which]!.ok && (
              <span style={{ fontSize: 11, color: C.amber }}>
                {plaus[which]!.findings.length} to look at ({plaus[which]!.checked} checks)
              </span>)}
          </div>
          {plaus[which] && plaus[which]!.findings.length > 0 && (
            <div style={{ background: C.bg3, border: `1px solid ${C.amber}44`, borderRadius: 8,
              padding: '9px 12px', marginTop: 8 }}>
              <div style={{ fontSize: 10, color: C.amber, textTransform: 'uppercase', marginBottom: 4 }}>
                Worth a second look — advisory, nothing is blocked</div>
              {plaus[which]!.findings.map((f, i) => (
                <div key={i} style={{ fontSize: 11, color: C.text, lineHeight: 1.65, marginBottom: 3 }}>
                  <b>{f.fields.join(', ')}</b> — {f.message}
                </div>))}
            </div>)}
          {which === 'bridge' && state.topology === 'sync_bottom' && bottomMosfetPanel()}
        </div>
      )}

      {mode === 'upload' && (
        <div style={{ fontSize: 12, color: C.text }}>
          <div style={{ fontSize: 11, color: C.muted, marginBottom: 6 }}>
            Upload the part's PDF datasheet — the agent extracts the loss-model parameters it can read, then
            opens the Manual form pre-filled for you to confirm/complete the values it could not find.
          </div>
          <input type="file" accept=".pdf" disabled={!!extBusy[which]} style={{ fontSize: 11 }}
            onChange={e => { onExtract(which, e.target.files?.[0]); e.currentTarget.value = '' }} />
          {extBusy[which] && <span style={{ marginLeft: 8, fontSize: 11, color: C.teal }}>⏳ Extracting…</span>}
          {extInfo[which] && (
            <div style={{ marginTop: 8, fontSize: 11, color: C.text, background: C.bg3,
              border: `1px solid ${C.border}`, borderRadius: 6, padding: '7px 10px' }}>
              <div style={{ fontWeight: 600 }}>{extInfo[which]!.part || '(part not detected)'}</div>
              <div style={{ color: C.green, marginTop: 3 }}>✓ extracted: {extInfo[which]!.found.join(', ') || '—'}</div>
              {extInfo[which]!.missing.length > 0 &&
                <div style={{ color: C.hint }}>needs manual entry: {extInfo[which]!.missing.join(', ')}</div>}
              <div style={{ color: C.muted, marginTop: 3 }}>Switched to Manual — review every field, then Calculate.</div>
            </div>
          )}
        </div>
      )}
    </Card>)
  }

  const cell: React.CSSProperties = { padding: '4px 8px', fontSize: 11.5, borderBottom: `1px solid ${C.border}`,
    fontFamily: 'IBM Plex Mono,monospace', color: C.text, textAlign: 'right' }
  const th: React.CSSProperties = { ...cell, color: C.hint, fontWeight: 600, textTransform: 'uppercase', fontSize: 9.5 }
  const worst = (key: string) => res?.summary ? Number((res.summary as any)[key]) : 0

  return (
    <div style={{ maxWidth: 1040, margin: '0 auto', padding: '8px 4px 28px' }}>
      <SecHead icon="🔌" label="Chapter 7 — Semiconductor Loss & Thermal"
        sub="Bridge rectifier · boost MOSFET · boost diode — losses & junction temperatures at every line voltage" />

      <Card style={{ marginTop: 12 }}>
        <div style={{ fontSize: 12, color: C.muted, marginBottom: 8 }}>Operating point (from the approved design — used verbatim, consistency-checked)</div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 8 }}>
          {[['V_OUT', `${design.vout} V`], ['f_sw', `${(design.fsw / 1000).toFixed(0)} kHz`],
            ['f_line', `${design.fline} Hz`], ['N_ch', `${design.nch}`], ['L_φ', `${design.L_phi_uH} µH`],
            ['V_in', `${design.vin_min}–${design.vin_max} V`], ['P_out HL/LL', `${design.pout_hi}/${design.pout_lo} W`],
            ['ripple r', `${design.r_input}`]].map(([k, v]) => (
            <div key={k} style={{ background: C.bg3, border: `1px solid ${C.border}`, borderRadius: 7, padding: '6px 9px' }}>
              <div style={{ fontSize: 9, color: C.hint, textTransform: 'uppercase' }}>{k}</div>
              <div style={{ fontSize: 13, color: C.text, fontWeight: 600, fontFamily: 'IBM Plex Mono,monospace' }}>{v}</div>
            </div>
          ))}
          <div style={{ background: C.bg3, border: `1px solid ${C.border}`, borderRadius: 7, padding: '6px 9px' }}>
            <div style={{ fontSize: 9, color: C.hint, textTransform: 'uppercase' }}>
              T_ambient (°C)
              {Number(thermal.t_ambient) !== _specAmbient && (
                <span style={{ color: C.amber, textTransform: 'none' }}>
                  {' '}· spec is {_specAmbient}°C
                </span>
              )}
            </div>
            <input style={{ ...inStyle, padding: '2px 6px', fontSize: 13 }} value={thermal.t_ambient}
              title={`Seeded from the intake spec (ambient_temp_c_max = ${_specAmbient} °C), the same ambient Chapters 1/3/4/5 use. Override only with a reason — a lower value makes every junction temperature optimistic.`}
              onChange={e => { _ambTouched.current = true
                setThermal(s => ({ ...s, t_ambient: e.target.value })) }} />
          </div>
          <div style={{ background: C.bg3, border: `1px solid ${C.border}`, borderRadius: 7, padding: '6px 9px' }}>
            <div style={{ fontSize: 9, color: C.hint, textTransform: 'uppercase' }}>Rθ(sink-amb) °C/W</div>
            <input style={{ ...inStyle, padding: '2px 6px', fontSize: 13 }} value={thermal.rth_sa}
              onChange={e => setThermal(s => ({ ...s, rth_sa: e.target.value }))} />
          </div>
        </div>
      </Card>

      <div style={{ display: 'flex', gap: 6, marginTop: 12 }}>
        {([['bridge', '⚡ Bridge'], ['mosfet', '🔲 MOSFET'], ['diode', '▷ Diode'], ['results', '📊 Results']] as [Sub, string][])
          .map(([k, lbl]) => {
          const active = sub === k
          return (
            <button key={k} onClick={() => setSub(k)} style={{
              flex: 1, padding: '8px 10px', borderRadius: 8, cursor: 'pointer', fontSize: 12, fontWeight: 600,
              fontFamily: 'IBM Plex Mono,monospace', border: `1px solid ${active ? C.teal : C.border}`,
              background: active ? 'rgba(45,212,191,.12)' : C.bg3, color: active ? C.teal : C.muted }}>{lbl}</button>
          )
        })}
      </div>

      {sub === 'bridge' && datasheetPanel('bridge')}
      {false && compForm(BRIDGE_FIELDS, bridge, 'bridge', 'Bridge rectifier (plain diode bridge, or sync-bottom bypass MOSFETs)',
        res?.summary ? ['bridge', fmtW(worst('P_BRIDGE_max'))] : undefined)}
      {/* The MOSFET no longer has "From database" or "Manual / external" sources. Both fed the
          engine from parameters the parametric catalogue does not carry — E_oss, E_on/E_off, Q_gd
          and R_DS(on) vs T_j are absent for all 1311 of its MOSFETs — which is what made E_oss
          3.4x wrong on the reference part. Diode and bridge keep theirs until M8. */}
      {sub === 'mosfet' && datasheetPanel('mosfet')}
      {sub === 'diode' && datasheetPanel('diode')}

      {sub === 'results' && (
        <Card style={{ marginTop: 12 }}>
          {!res && <div style={{ color: C.muted, fontSize: 12 }}>Run the calculation to see per-voltage losses and junction temperatures.</div>}
          {res && (<>
            <Banner ok={res.validation.ok} okText="All required component fields present"
              badText="Component data incomplete — fill the NOT-AVAILABLE fields" issues={res.validation.issues} />
            {res.consistency && <Banner ok={res.consistency.ok}
              okText="Operating point matches the approved design at every point (no discrepancy)"
              badText="Loss-calc operating point diverges from the design" issues={res.consistency.issues} />}
            {res.summary && (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 8, margin: '10px 0' }}>
                {[['Worst semi loss', fmtW(worst('P_SEMI_max')), `@ ${worst('worst_loss_Vac')} Vac`],
                  ['Tj FET max', `${worst('Tj_FET_max').toFixed(0)} °C`, `limit ${tjLimit.fet}`],
                  ['Tj Diode max', `${worst('Tj_DIODE_max').toFixed(0)} °C`, `limit ${tjLimit.diode}`],
                  ['Tj Bridge max', `${worst('Tj_BRIDGE_max').toFixed(0)} °C`, `limit ${tjLimit.bridge}`]].map(([k, v, u]) => (
                  <div key={k} style={{ background: C.bg3, border: `1px solid ${C.border}`, borderRadius: 8, padding: '8px 10px' }}>
                    <div style={{ fontSize: 9.5, color: C.hint, textTransform: 'uppercase' }}>{k}</div>
                    <div style={{ fontSize: 16, color: C.text, fontWeight: 600, fontFamily: 'IBM Plex Mono,monospace' }}>{v}</div>
                    <div style={{ fontSize: 9.5, color: C.muted }}>{u}</div>
                  </div>
                ))}
              </div>
            )}
            {res.validation.ok && (
              <div style={{ overflowX: 'auto', marginTop: 6 }}>
                <table style={{ borderCollapse: 'collapse', width: '100%' }}>
                  {/* ONE NUMBER PER COMPONENT. The diode used to be the only part whose internals
                      leaked into this summary — the MOSFET has five mechanisms here and shows
                      none, the bridge has top/bottom and shows neither — so "D cond" and
                      "D recovery" were an exception to a rule the table already had. The
                      per-mechanism breakdown lives in each component's own Results sub-tab, which
                      reads the same `res.per_point`, and in Chapter 7 Tables 7.4/7.5.
                      The T_j columns STAY: they are a limit check, not a loss breakdown. */}
                  <thead><tr>{['V_AC', 'P_out', 'η%', 'PF', 'FET', 'Diode', 'Bridge', 'SEMI',
                               'Tj FET', 'Tj D', 'Tj Br']
                    .map((h, i) => <th key={h} style={{ ...th, textAlign: i === 0 ? 'left' : 'right' }}>{h}</th>)}</tr></thead>
                  <tbody>
                    {res.per_point.map((r, i) => (
                      <tr key={i}>
                        <td style={{ ...cell, textAlign: 'left', color: C.teal }}>{r.Vac.toFixed(0)} V</td>
                        <td style={cell}>{r.Po.toFixed(0)}</td>
                        <td style={cell}>{r['eta_in_%'].toFixed(1)}</td>
                        <td style={cell}>{r.PF_in.toFixed(4)}</td>
                        {/* GATE DRIVE IS PART OF THE FET BUCKET, exactly as Chapter 7 Table 7.4
                            has it. `P_SEMI_total` already includes it while `P_FET_total` does
                            not, so showing the latter raw left FET + Diode + Bridge short of SEMI
                            by P_gate_driver on every row. Harmless while seven loss columns sat
                            here; the moment the row became four adjacent totals it reads as an
                            arithmetic error. */}
                        <td style={cell}>
                          {(r.P_FET_total + ((r as any).P_gate_driver ?? 0)).toFixed(2)}</td>
                        <td style={cell}>{r.P_DIODE_total.toFixed(2)}</td>
                        <td style={cell}>{r.P_BRIDGE_total.toFixed(2)}</td>
                        <td style={{ ...cell, fontWeight: 700 }}>{r.P_SEMI_total.toFixed(2)}</td>
                        <td style={cell}>{r.Tj_FET.toFixed(0)}</td>
                        <td style={cell}>{r.Tj_DIODE.toFixed(0)}</td>
                        <td style={cell}>{r.Tj_BRIDGE_top.toFixed(0)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <div style={{ fontSize: 10, color: C.muted, marginTop: 5 }}>
                  One number per component, TOTALLED over all {design.nch} channels. For the
                  per-mechanism breakdown — conduction, switching, E<sub>oss</sub>, recovery,
                  blocking — open that component's own <b>Results</b> tab, or Chapter 7
                  Tables 7.4 and 7.5 in the report.
                </div>
              </div>
            )}
            {figBusy && <div style={{ color: C.muted, fontSize: 11, marginTop: 10 }}>Rendering figures…</div>}
            {figs && (
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginTop: 12 }}>
                {['losses_vs_vac', 'temperatures_vs_vac', 'loss_breakdown', 'waveforms'].map(n => figs[n] && (
                  <img key={n} src={figs[n]} alt={n} style={{ width: '100%', borderRadius: 8, border: `1px solid ${C.border}` }} />
                ))}
              </div>
            )}
          </>)}
        </Card>
      )}

      {err && <div style={{ color: C.red, fontSize: 12, marginTop: 10 }}>⚠ {err}</div>}

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 18 }}>
        <div style={{ display: 'flex', gap: 8 }}>
          <Btn variant="ghost" onClick={onBack}>← Back to Control Design</Btn>
          <Btn variant="ghost" onClick={onRestart}>↺ New design</Btn>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          {/* Chapter 7 alone. The full document is ~190 pages and takes minutes to build;
              checking a loss calculation should need neither. */}
          <Btn disabled={rptBusy || !res?.validation.ok} onClick={downloadCh7}>
            {rptBusy ? '⏳ Generating…' : '📄 Download Chapter 7 only (semiconductor loss)'}</Btn>
          <Btn variant="success" disabled={rptBusy || !res?.validation.ok} onClick={downloadReport}>
            {rptBusy ? '⏳ Generating…' : '📥 Download full report (Ch 1–7)'}
          </Btn>
          {/* `() => calc()`, never bare: React passes the click event as the first argument, which
              since calc gained a `navigate` flag would have been read as that flag. This is the
              C174 trap, and `Btn.onClick` is typed precisely so the compiler catches it. */}
          <Btn variant="primary" disabled={busy} onClick={() => calc()}>
            {busy ? '⏳ Calculating…' : '⚙ Calculate losses (all 9 line voltages)'}
          </Btn>
          {onNext && <Btn variant="success" onClick={() => {
            const b = body()
            onNext({ design: b.design, mosfet: b.mosfet, diode: b.diode, bridge: b.bridge,
                     thermal: b.thermal, tj_limit: b.tj_limit })
          }}>Input protection →</Btn>}
        </div>
      </div>
    </div>
  )
}
