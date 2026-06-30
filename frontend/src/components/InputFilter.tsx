/**
 * InputFilter.tsx — Input EMI filter design (differential-mode + common-mode).
 *
 * Starting page for the conducted-emissions input filter that sits between the AC inlet and the
 * PFC stage. The PFC draws a switching-frequency ripple current (at f_sw, partly cancelled by
 * interleaving) that must be attenuated to meet CISPR 32 / EN 55032 conducted limits
 * (150 kHz – 30 MHz). All operating context is carried in from the upstream design.
 */
import React, { useMemo, useState } from 'react'
import { C, Btn, Card, SecHead } from './ui'
import type { CapacitorResult } from './Step15Capacitor'

interface Props {
  confirmedState:          Record<string, unknown>
  approvedInductorDesign:  Record<string, unknown>
  approvedCapacitorDesign?: CapacitorResult | null
  onBack:    () => void
  onRestart: () => void
}

const inStyle: React.CSSProperties = { background: C.bg3, border: `1px solid ${C.border2}`, borderRadius: 6,
  color: C.text, padding: '5px 8px', fontSize: 12, fontFamily: 'IBM Plex Mono,monospace', width: 90 }
const num = (v: unknown, d = 1) => (typeof v === 'number' && isFinite(v) ? v.toFixed(d) : '—')

const Chip: React.FC<{ k: string; v: string }> = ({ k, v }) => (
  <div style={{ background: C.bg3, border: `1px solid ${C.border}`, borderRadius: 7, padding: '5px 10px' }}>
    <div style={{ fontSize: 9.5, color: C.hint, textTransform: 'uppercase', letterSpacing: '.05em' }}>{k}</div>
    <div style={{ fontSize: 12.5, color: C.text, fontFamily: 'IBM Plex Mono,monospace', fontWeight: 600 }}>{v}</div>
  </div>
)

const Knob: React.FC<{ label: string; unit?: string; value: string; onChange: (v: string) => void; w?: number }>
  = ({ label, unit, value, onChange, w }) => (
  <label style={{ fontSize: 10.5, color: C.muted }}>{label}{unit ? ` (${unit})` : ''}<br />
    <input style={{ ...inStyle, width: w ?? 90 }} value={value} onChange={e => onChange(e.target.value)} /></label>
)

export const InputFilter: React.FC<Props> = ({
  confirmedState, approvedInductorDesign, onBack, onRestart,
}) => {
  const app = (confirmedState as any)?.intake?.application ?? {}
  const tsi = (confirmedState as any)?.topology_specific_inputs ?? {}
  const d = useMemo(() => ({
    vin_min: Number(app.vin_rms_min ?? 90),
    vin_max: Number(app.vin_rms_max ?? 264),
    pout:    Number(app.output_power_w_high_line ?? 3600),
    fsw:     Number(tsi.recommended_frequency_hz ?? 70000),
    nch:     Number((confirmedState as any)?.selected_channels ?? 2),
    fline:   Number(app.line_frequency_hz ?? 60),
  }), [confirmedState])  // eslint-disable-line react-hooks/exhaustive-deps

  // worst-case input RMS current at low line (≈ Pout/(η·Vac))
  const iin = d.pout / (0.945 * d.vin_min)
  // effective ripple frequency the filter must attenuate (2× fsw for a 2-channel interleaved stage)
  const frip = d.fsw * (d.nch >= 2 ? 2 : 1)

  // designer knobs
  const [cx, setCx] = useState('0.47')      // X-capacitor µF
  const [ldm, setLdm] = useState('2.2')     // DM inductance mH (extra, beyond the boost L)
  const [cy, setCy] = useState('2.2')       // Y-capacitor nF each
  const [lcm, setLcm] = useState('10')      // CM choke mH

  const cxF = Number(cx) * 1e-6, ldmH = Number(ldm) * 1e-3
  const lcmH = Number(lcm) * 1e-3, cyF = Number(cy) * 1e-9
  // DM corner: f0 = 1/(2π√(L·2Cx)) (two X-caps see ½ each → 2Cx in the loop); CM corner with 2 Y-caps
  const fdm = 1 / (2 * Math.PI * Math.sqrt(ldmH * 2 * cxF))
  const fcm = 1 / (2 * Math.PI * Math.sqrt(lcmH * (2 * cyF)))
  // 2nd-order roll-off attenuation at the ripple frequency (dB) ≈ 40·log10(frip/f0)
  const attDm = 40 * Math.log10(Math.max(frip / fdm, 1.0001))
  // Y-cap leakage current at high line (per IEC 60950/62368: < 3.5 mA): I = 2πf·V·2Cy
  const iLeak = 2 * Math.PI * d.fline * (d.vin_max * Math.SQRT2) * (2 * cyF) * 1000  // mA (rough)

  return (
    <div style={{ maxWidth: 1080, margin: '0 auto' }}>
      <Card>
        <SecHead icon="🎚️" label="Input EMI Filter — Differential & Common Mode"
          sub={`${d.vin_min}–${d.vin_max} Vac · f_sw ${num(d.fsw / 1e3, 0)} kHz`} />
        <div style={{ background: C.tealL, border: `1px solid ${C.teal}55`, borderRadius: 8,
          padding: '8px 12px', marginBottom: 12, fontSize: 11.5, color: C.text }}>
          <b style={{ color: C.teal }}>Purpose.</b> The PFC draws a switching-frequency ripple current that
          would otherwise inject conducted noise back onto the mains. This filter — differential-mode
          (X-caps + DM inductance) and common-mode (CM choke + Y-caps) — attenuates it to meet
          CISPR&nbsp;32 / EN&nbsp;55032 conducted-emission limits over 150&nbsp;kHz–30&nbsp;MHz.
        </div>

        <div style={{ fontSize: 11.5, color: C.muted, marginBottom: 8 }}>Carried in from the design — read-only:</div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 16 }}>
          <Chip k="V_ac range" v={`${d.vin_min}–${d.vin_max} V`} />
          <Chip k="P_out" v={`${num(d.pout, 0)} W`} />
          <Chip k="f_sw" v={`${num(d.fsw / 1e3, 0)} kHz`} />
          <Chip k="Channels" v={`${d.nch}`} />
          <Chip k="Ripple freq (filter)" v={`${num(frip / 1e3, 0)} kHz`} />
          <Chip k="I_in,rms (low line)" v={`${num(iin, 1)} A`} />
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
          <div>
            <div style={{ fontSize: 12, color: C.text, fontWeight: 600, marginBottom: 8 }}>Differential-mode stage</div>
            <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 10 }}>
              <Knob label="X-cap C_X" unit="µF" value={cx} onChange={setCx} />
              <Knob label="DM inductor L_DM" unit="mH" value={ldm} onChange={setLdm} />
            </div>
            <div style={{ fontSize: 11.5, color: C.muted }}>
              DM corner f<sub>0,DM</sub> = <b style={{ color: C.text }}>{num(fdm / 1e3, 1)} kHz</b><br />
              Est. attenuation at {num(frip / 1e3, 0)} kHz ≈ <b style={{ color: C.green }}>{num(attDm, 0)} dB</b> (2nd-order)
            </div>
          </div>
          <div>
            <div style={{ fontSize: 12, color: C.text, fontWeight: 600, marginBottom: 8 }}>Common-mode stage</div>
            <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 10 }}>
              <Knob label="CM choke L_CM" unit="mH" value={lcm} onChange={setLcm} />
              <Knob label="Y-cap C_Y (each)" unit="nF" value={cy} onChange={setCy} />
            </div>
            <div style={{ fontSize: 11.5, color: C.muted }}>
              CM corner f<sub>0,CM</sub> = <b style={{ color: C.text }}>{num(fcm / 1e3, 1)} kHz</b><br />
              Y-cap leakage @ high line ≈ <b style={{ color: iLeak > 3.5 ? C.red : C.green }}>{num(iLeak, 2)} mA</b>
              {iLeak > 3.5 && <span style={{ color: C.red }}> (&gt; 3.5 mA limit — reduce C_Y)</span>}
            </div>
          </div>
        </div>

        <div style={{ fontSize: 9.5, color: C.muted, marginTop: 14, borderTop: `1px solid ${C.border}`, paddingTop: 10 }}>
          Starting estimates use 2nd-order LC corner frequencies and a 40 dB/decade roll-off; the full design
          (insertion-loss vs the measured/standard limit line, choke saturation & leakage-inductance DM
          contribution, damping, and a CISPR quasi-peak margin) attaches here next.
        </div>
      </Card>

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '4px 2px 24px' }}>
        <Btn variant="ghost" onClick={onBack}>← Back to input protection</Btn>
        <Btn variant="ghost" onClick={onRestart}>Restart</Btn>
      </div>
    </div>
  )
}
