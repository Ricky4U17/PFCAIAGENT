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
import React, { useMemo, useState } from 'react'
import { C, Btn, Card, SecHead } from './ui'
import type { CapacitorResult } from './Step15Capacitor'
import { semiconductorCalculate, semiconductorFigures,
         type SemiCalcResult, type SemiReqBody } from '../api/client'

interface Props {
  confirmedState:          Record<string, unknown>
  approvedInductorDesign:  Record<string, unknown>
  approvedCapacitorDesign: CapacitorResult | null
  onBack:    () => void
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
  qg_bottom: '90e-9', n_parallel_bottom: '1',
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

const inStyle: React.CSSProperties = { background: C.bg3, border: `1px solid ${C.border2}`, borderRadius: 6,
  color: C.text, padding: '5px 8px', fontSize: 12, fontFamily: 'IBM Plex Mono,monospace', width: '100%' }
const fmtW = (n: number) => `${n.toFixed(2)} W`

export const SemiconductorSelection: React.FC<Props> = ({
  confirmedState, approvedInductorDesign, onBack, onRestart,
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
    L_phi_uH: Number((approvedInductorDesign as any)?.L_target_uH ?? 235),
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
  const [err, setErr] = useState<string | null>(null)

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

  const compForm = (fields: Field[], state: Record<string, any>, which: Sub, title: string, devLoss?: [string, string]) => (
    <Card style={{ marginTop: 12 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
        <div style={{ fontSize: 13, color: C.text, fontWeight: 600 }}>{title}</div>
        {devLoss && (
          <div style={{ fontSize: 11, color: C.teal, fontFamily: 'IBM Plex Mono,monospace' }}>
            worst {devLoss[0]} loss {devLoss[1]}
          </div>
        )}
      </div>
      <div style={{ marginTop: 10 }}>
        {fields.map(f => <FieldRow key={f.key} f={f} state={state} onSet={setC(which)} />)}
      </div>
    </Card>
  )

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
        <Btn variant="primary" disabled={busy} onClick={calc}>
          {busy ? '⏳ Calculating…' : '⚙ Calculate losses (all 9 line voltages)'}
        </Btn>
      </div>
    </div>
  )
}
