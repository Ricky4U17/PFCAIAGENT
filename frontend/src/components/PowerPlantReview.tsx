/**
 * PowerPlantReview.tsx — Control Design Screen 1 (Chapter 6).
 *
 * Review-only screen: shows the power-plant parameters that are already fixed by
 * the time we reach Control Design — carried-in scalars (V_OUT, f_sw, N_ch, L, C,
 * compliance) plus the canonical operating-point grid (efficiency, power factor,
 * V_in,pk, duty, R_LOAD at all points — the same data as report Table 1.2.2).
 * The designer reviews and confirms to advance to Screen 2.
 */
import React, { useEffect, useState } from 'react'
import { C, Btn, Card, SecHead } from './ui'
import { controlPowerPlant, type PowerPlantRow } from '../api/client'

export interface PlantParams {
  vout_V: number; fsw_kHz: number; nch: number
  lphi_uH: number; rl_mOhm: number; co_uF: number; rc_mOhm: number
  pout_lo_W: number; pout_hi_W: number; eta_lo: number; eta_hi: number
}

interface Props {
  confirmedState: Record<string, unknown>
  params: PlantParams
  onBack: () => void
  onConfirm: () => void
}

const cell: React.CSSProperties = { padding: '6px 10px', fontSize: 12, borderBottom: `1px solid ${C.border}`,
  fontFamily: 'IBM Plex Mono,monospace', color: C.text }
const th: React.CSSProperties = { ...cell, color: C.hint, fontWeight: 600, textTransform: 'uppercase',
  letterSpacing: 0.4, fontSize: 10, fontFamily: 'inherit' }

const KV: React.FC<{ k: string; v: string }> = ({ k, v }) => (
  <div style={{ background: C.bg3, border: `1px solid ${C.border}`, borderRadius: 8, padding: '8px 11px' }}>
    <div style={{ fontSize: 10, color: C.hint, textTransform: 'uppercase', letterSpacing: 0.5 }}>{k}</div>
    <div style={{ fontSize: 15, color: C.text, fontWeight: 600, fontFamily: 'IBM Plex Mono,monospace' }}>{v}</div>
  </div>
)

export const PowerPlantReview: React.FC<Props> = ({ confirmedState, params, onBack, onConfirm }) => {
  const app = (confirmedState as any)?.intake?.application ?? {}
  const comp = (confirmedState as any)?.intake?.compliance ?? {}
  const vinMin = Number(app.vin_rms_min ?? 90)
  const vinMax = Number(app.vin_rms_max ?? 264)

  const [rows, setRows] = useState<PowerPlantRow[] | null>(null)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    controlPowerPlant({
      vin_min: vinMin, vin_max: vinMax,
      pout_lo: params.pout_lo_W, pout_hi: params.pout_hi_W, vout: params.vout_V,
    }).then(r => setRows(r.rows)).catch(e => setErr((e as Error).message))
  }, [vinMin, vinMax, params.pout_lo_W, params.pout_hi_W, params.vout_V])

  const fixed: [string, string][] = [
    ['Input voltage range', `${vinMin}–${vinMax} Vrms`],
    ['Output voltage  V_OUT', `${params.vout_V.toFixed(1)} V`],
    ['Output power (HL / LL)', `${params.pout_hi_W.toFixed(0)} / ${params.pout_lo_W.toFixed(0)} W`],
    ['Switching freq  f_sw', `${params.fsw_kHz.toFixed(0)} kHz`],
    ['Channels  N_ch', `${params.nch}`],
    ['Per-phase inductance  Lφ', `${params.lphi_uH.toFixed(0)} µH`],
    ['Inductor DCR  r_L', `${params.rl_mOhm.toFixed(0)} mΩ`],
    ['Bus capacitance  C_O', `${params.co_uF.toFixed(0)} µF`],
    ['Capacitor ESR  r_C', `${params.rc_mOhm.toFixed(0)} mΩ`],
    ['PF target', `${Number(app.power_factor_target ?? 0.99).toFixed(3)}`],
    ['Efficiency target', `${Number(app.efficiency_target_percent ?? 95).toFixed(1)} %`],
    ['Line frequency', `${Number(app.line_frequency_hz ?? 60).toFixed(0)} Hz`],
  ]
  const compliance: [string, string][] = [
    ['Application class', String(comp.application_class ?? '—')],
    ['SEMI F47', comp.semi_f47 === true ? 'Required' : comp.semi_f47 === false ? 'Not required' : '—'],
    ['Leakage limit', comp.leakage_current_limit_ua != null ? `${comp.leakage_current_limit_ua} µA` : '—'],
    ['Hold-up time', app.hold_up_time_ms != null ? `${app.hold_up_time_ms} ms` : '—'],
  ]

  return (
    <div style={{ maxWidth: 980, margin: '0 auto', padding: '8px 4px 24px' }}>
      <SecHead icon="📋" label="Control Design · Screen 1 of 7 — Power Plant Parameters"
        sub="Review the parameters fixed by the upstream design, then confirm to continue" />

      <Card style={{ marginTop: 12 }}>
        <div style={{ fontSize: 12, color: C.muted, marginBottom: 10 }}>Fixed design parameters (carried in)</div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 9 }}>
          {fixed.map(([k, v]) => <KV key={k} k={k} v={v} />)}
        </div>
      </Card>

      <Card style={{ marginTop: 12 }}>
        <div style={{ fontSize: 12, color: C.muted, marginBottom: 8 }}>
          Operating points — efficiency, power factor, duty &amp; load (Table 1.2.2)
        </div>
        {err && <div style={{ color: C.red, fontSize: 12 }}>⚠ {err}</div>}
        {!rows && !err && <div style={{ color: C.muted, fontSize: 12 }}>Loading…</div>}
        {rows && (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ borderCollapse: 'collapse', width: '100%' }}>
              <thead><tr>
                {['V_in (Vrms)', 'Line', 'P_out (W)', 'η (%)', 'PF', 'V_in,pk (V)', 'Duty D', 'R_LOAD (Ω)']
                  .map(h => <th key={h} style={th}>{h}</th>)}
              </tr></thead>
              <tbody>
                {rows.map((r, i) => (
                  <tr key={i}>
                    <td style={cell}>{r.vac}</td>
                    <td style={{ ...cell, color: r.line === 'High' ? C.amber : C.teal }}>{r.line}</td>
                    <td style={cell}>{r.pout}</td>
                    <td style={cell}>{r.eta_pct.toFixed(1)}</td>
                    <td style={cell}>{r.pf.toFixed(4)}</td>
                    <td style={cell}>{r.vin_pk.toFixed(1)}</td>
                    <td style={cell}>{r.duty.toFixed(4)}</td>
                    <td style={cell}>{r.rload.toFixed(2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Card style={{ marginTop: 12 }}>
        <div style={{ fontSize: 12, color: C.muted, marginBottom: 10 }}>Compliance requirements</div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 9 }}>
          {compliance.map(([k, v]) => <KV key={k} k={k} v={v} />)}
        </div>
      </Card>

      <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 18 }}>
        <Btn variant="ghost" onClick={onBack}>← Back</Btn>
        <Btn variant="primary" onClick={onConfirm} disabled={!rows}>Confirm &amp; Continue →</Btn>
      </div>
    </div>
  )
}
