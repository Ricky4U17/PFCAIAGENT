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
import React, { useEffect, useMemo, useState } from 'react'
import { C, Btn, Card, SecHead } from './ui'
import type { CapacitorResult } from './Step15Capacitor'
import { semiconductorCalculate, semiconductorFigures, docGenerateReport,
         semiconductorDbOptions, semiconductorDbRank, semiconductorExtract,
         type SemiCalcResult, type SemiReqBody, type DbRankResult } from '../api/client'

interface Props {
  confirmedState:          Record<string, unknown>
  approvedInductorDesign:  Record<string, unknown>
  approvedCapacitorDesign: CapacitorResult | null
  onBack:    () => void
  onNext?:   () => void
  onRestart: () => void
}

type Sub = 'bridge' | 'mosfet' | 'diode' | 'results'
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
  vf_curve: { x: '1, 5, 16', y: '1.05, 1.35, 1.7' }, qc: '20e-9', qrr: '120e-9',
  vf_tco: '0.0015', rth_jc: '0.7', rth_cs: '0.3',
}
const BRIDGE0: Record<string, any> = {
  manufacturer: '', part_number: '', topology: 'diode',
  vf_curve: { x: '1, 12, 24', y: '0.75, 0.95, 1.15' }, n_parallel: '2',
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
  { key: 'vf_curve', label: 'V_f vs I_f', kind: 'curve', unit: 'A / V' },
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
  { key: 'vf_curve', label: 'Diode V_f vs I_f', kind: 'curve', unit: 'A / V' },
  { key: 'n_parallel', label: 'Devices in parallel', kind: 'num' },
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
const BASE: Record<Sub, Record<string, any>> = { bridge: BRIDGE0, mosfet: MOSFET0, diode: DIODE0, results: {} }
const FIELDS: Record<Sub, Field[]> = { bridge: BRIDGE_FIELDS, mosfet: MOSFET_FIELDS, diode: DIODE_FIELDS, results: [] }

const inStyle: React.CSSProperties = { background: C.bg3, border: `1px solid ${C.border2}`, borderRadius: 6,
  color: C.text, padding: '5px 8px', fontSize: 12, fontFamily: 'IBM Plex Mono,monospace', width: '100%' }
const fmtW = (n: number) => `${n.toFixed(2)} W`

export const SemiconductorSelection: React.FC<Props> = ({
  confirmedState, approvedInductorDesign, approvedCapacitorDesign, onBack, onNext, onRestart,
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
  const [thermal, setThermal] = useState({ t_ambient: '45', rth_sa: '0.35' })
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
  const [dbCrit, setDbCrit] = useState<Record<string, any>>({
    bridge: { v_min: '600', i_min: '15' }, mosfet: { v_min: '600', i_min: '15' }, diode: { v_min: '600', i_min: '10' },
    bottom: { v_min: '550', i_min: '15' },
  })
  const [dbRes, setDbRes] = useState<Record<string, DbRankResult[] | null>>({})
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
      const r = await semiconductorDbRank(kind, { design, criteria, top: 10, mode })
      setDbRes(s => ({ ...s, [key]: r.results }))
    } catch (e) { setErr((e as Error).message) } finally { setDbBusy(s => ({ ...s, [key]: false })) }
  }
  const pickDbPart = (which: Sub, r: DbRankResult) => {
    setWhole(which, blockToForm(r.block as Record<string, any>, FIELDS[which], BASE[which]))
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
  const onExtract = async (which: Sub, file: File | undefined) => {
    if (!file) return
    setExtBusy(s => ({ ...s, [which]: true })); setErr(null)
    try {
      const r = await semiconductorExtract(which, file)
      const cur = which === 'mosfet' ? mosfet : which === 'diode' ? diode : bridge
      setWhole(which, blockToForm(r.block as Record<string, any>, FIELDS[which], cur))
      setExtInfo(s => ({ ...s, [which]: { found: r.found, missing: r.missing,
        part: `${r.manufacturer ?? ''} ${r.part_number ?? ''}`.trim() } }))
      setSrcMode(s => ({ ...s, [which]: 'manual' }))   // show populated fields for confirmation
    } catch (e) { setErr((e as Error).message) } finally { setExtBusy(s => ({ ...s, [which]: false })) }
  }

  const body = (): SemiReqBody => ({
    design,
    mosfet: buildBlock(mosfet, MOSFET_FIELDS),
    diode:  buildBlock(diode, DIODE_FIELDS),
    bridge: buildBlock(bridge, BRIDGE_FIELDS),
    thermal: { t_ambient: pnum(thermal.t_ambient) ?? 45, rth_sa: pnum(thermal.rth_sa) ?? 0.35 },
    tj_limit: tjLimit,
  })

  const calc = async () => {
    setBusy(true); setErr(null); setFigs(null)
    try {
      const b = body()
      const r = await semiconductorCalculate(b)
      setRes(r); setSub('results')
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
      }
      const blob = await docGenerateReport({
        state: confirmedState, approved_design: approvedInductorDesign,
        step15_result: approvedCapacitorDesign ? { ...approvedCapacitorDesign } : {},
        step16_params,
        semiconductor: { design: b.design, mosfet: b.mosfet, diode: b.diode, bridge: b.bridge,
          thermal: b.thermal, tj_limit: b.tj_limit },
      })
      const url = URL.createObjectURL(blob); const a = document.createElement('a')
      a.href = url; a.download = `PFC_Report_${(confirmedState as any).project_id ?? 'design'}_Steps1_17.pdf`
      document.body.appendChild(a); a.click(); document.body.removeChild(a)
      setTimeout(() => URL.revokeObjectURL(url), 150)
    } catch (e) { setErr((e as Error).message) } finally { setRptBusy(false) }
  }

  const setC = (which: Sub) => (k: string, v: any) => {
    const set = which === 'mosfet' ? setMosfet : which === 'diode' ? setDiode : setBridge
    set(s => ({ ...s, [k]: v }))
  }

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

  const critIn: React.CSSProperties = { ...inStyle, width: 80 }
  const critSel: React.CSSProperties = { ...inStyle, width: 'auto', maxWidth: 160 }
  const rcell: React.CSSProperties = { padding: '3px 7px', fontSize: 11, borderBottom: `1px solid ${C.border}`,
    fontFamily: 'IBM Plex Mono,monospace', color: C.text, whiteSpace: 'nowrap' }

  const dbResultsTable = (results: DbRankResult[], lossLabel: string, onPick: (r: DbRankResult) => void,
    note = "Loss ranked by the calc engine at this design's 9 operating points. Datasheet curves not in the DB " +
           "(Eoss, Rθjc, Qrr/Qc, Vf slope) are estimated — selecting a part fills the form for review/edit.") =>
    results.length === 0
      ? <div style={{ fontSize: 11, color: C.muted }}>No parts match — relax the filters.</div>
      : <div style={{ overflowX: 'auto' }}>
          <table style={{ borderCollapse: 'collapse', width: '100%' }}>
            <thead><tr>{['#', `${lossLabel} loss`, 'Tj', 'Rating', 'Mfr', 'Part #', ''].map(h =>
              <th key={h} style={{ ...rcell, color: C.hint, textTransform: 'uppercase', fontSize: 9 }}>{h}</th>)}</tr></thead>
            <tbody>{results.map((r, i) => (
              <tr key={i}>
                <td style={rcell}>{i + 1}</td>
                <td style={{ ...rcell, fontWeight: 700, color: C.teal }}>{r.loss_W.toFixed(2)} W</td>
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
          <label style={{ fontSize: 10.5, color: C.muted }}>Current ≥ (A)<br />
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
        {results && dbResultsTable(results, 'FET conduction', pickBottomMosfet,
          'Conduction loss only (line-frequency commutation). Selecting a part fills the bottom-FET fields above.')}
      </div>
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
            <button key={m} onClick={() => setSrcMode(s => ({ ...s, [which]: m }))} style={{
              padding: '4px 10px', borderRadius: 6, cursor: 'pointer', fontSize: 11, fontWeight: 600,
              border: `1px solid ${mode === m ? C.teal : C.border}`, background: mode === m ? 'rgba(45,212,191,.12)' : C.bg3,
              color: mode === m ? C.teal : C.muted }}>{lbl}</button>
          ))}
      </div>

      {mode === 'database' && (<>
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'flex-end', marginBottom: 8 }}>
          <label style={{ fontSize: 10.5, color: C.muted }}>Voltage ≥ (V)<br />
            <input style={critIn} value={crit.v_min ?? ''} onChange={e => setCrit(which, 'v_min', e.target.value)} /></label>
          <label style={{ fontSize: 10.5, color: C.muted }}>Current ≥ (A)<br />
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
          <Btn variant="primary" disabled={!!dbBusy[which]} onClick={() => runDbSearch(which, which)}>
            {dbBusy[which] ? '⏳ Ranking…' : '🔎 Find top 10 (lowest loss)'}
          </Btn>
        </div>
        {results && dbResultsTable(results, which === 'mosfet' ? 'FET' : which, r => pickDbPart(which, r))}
      </>)}

      {mode === 'manual' && (
        <div>
          {fields.map(f => <FieldRow key={f.key} f={f} state={state} onSet={setC(which)} />)}
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
            <div style={{ fontSize: 9, color: C.hint, textTransform: 'uppercase' }}>T_ambient (°C)</div>
            <input style={{ ...inStyle, padding: '2px 6px', fontSize: 13 }} value={thermal.t_ambient}
              onChange={e => setThermal(s => ({ ...s, t_ambient: e.target.value }))} />
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

      {sub === 'bridge' && compForm(BRIDGE_FIELDS, bridge, 'bridge', 'Bridge rectifier (plain diode bridge, or sync-bottom bypass MOSFETs)',
        res?.summary ? ['bridge', fmtW(worst('P_BRIDGE_max'))] : undefined)}
      {sub === 'mosfet' && compForm(MOSFET_FIELDS, mosfet, 'mosfet', 'Boost MOSFET (Si super-junction or SiC)',
        res?.summary ? ['FET', fmtW(worst('P_FET_max'))] : undefined)}
      {sub === 'diode' && compForm(DIODE_FIELDS, diode, 'diode', 'Boost diode (SiC Schottky or Si)',
        res?.summary ? ['diode', fmtW(worst('P_DIODE_max'))] : undefined)}

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
                  <thead><tr>{['V_AC', 'P_out', 'η%', 'PF', 'FET', 'Diode', 'Bridge', 'SEMI', 'Tj FET', 'Tj D', 'Tj Br']
                    .map((h, i) => <th key={h} style={{ ...th, textAlign: i === 0 ? 'left' : 'right' }}>{h}</th>)}</tr></thead>
                  <tbody>
                    {res.per_point.map((r, i) => (
                      <tr key={i}>
                        <td style={{ ...cell, textAlign: 'left', color: C.teal }}>{r.Vac.toFixed(0)} V</td>
                        <td style={cell}>{r.Po.toFixed(0)}</td>
                        <td style={cell}>{r['eta_in_%'].toFixed(1)}</td>
                        <td style={cell}>{r.PF_in.toFixed(4)}</td>
                        <td style={cell}>{r.P_FET_total.toFixed(2)}</td>
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
          <Btn variant="success" disabled={rptBusy || !res?.validation.ok} onClick={downloadReport}>
            {rptBusy ? '⏳ Generating…' : '📥 Download full report (Ch 1–7)'}
          </Btn>
          <Btn variant="primary" disabled={busy} onClick={calc}>
            {busy ? '⏳ Calculating…' : '⚙ Calculate losses (all 9 line voltages)'}
          </Btn>
          {onNext && <Btn variant="success" onClick={onNext}>Input protection →</Btn>}
        </div>
      </div>
    </div>
  )
}
