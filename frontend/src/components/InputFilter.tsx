/**
 * InputFilter.tsx — Input EMI filter design (differential-mode + common-mode).
 *
 * Synthesizes the conducted-EMI filter that lets the PFC front end meet a chosen compliance
 * profile (CISPR 32 / EN 55032 / FCC 15.107, Class A/B) within a chosen safety earth-leakage
 * limit. The PFC operating context (V_ac, V_bus, P_out, f_sw, interleaving, inductor ripple,
 * bulk-cap ESR) is carried in; the designer picks the standards + margin and the backend
 * (vendored physics engine) returns the required attenuation and the DM/CM component values.
 */
import React, { useEffect, useMemo, useState } from 'react'
import { C, Btn, Card, SecHead, Badge } from './ui'
import type { CapacitorResult } from './Step15Capacitor'
import { inputFilterOptions, inputFilterDesign, type EmiDesign } from '../api/client'

interface Props {
  confirmedState:          Record<string, unknown>
  approvedInductorDesign:  Record<string, unknown>
  approvedCapacitorDesign?: CapacitorResult | null
  onBack:    () => void
  onRestart: () => void
}

const inStyle: React.CSSProperties = { background: C.bg3, border: `1px solid ${C.border2}`, borderRadius: 6,
  color: C.text, padding: '5px 8px', fontSize: 12, fontFamily: 'IBM Plex Mono,monospace', width: '100%' }
const selStyle: React.CSSProperties = { ...inStyle, cursor: 'pointer' }
const num = (v: unknown, d = 1) => (typeof v === 'number' && isFinite(v) ? v.toFixed(d) : '—')

const Chip: React.FC<{ k: string; v: string }> = ({ k, v }) => (
  <div style={{ background: C.bg3, border: `1px solid ${C.border}`, borderRadius: 7, padding: '5px 10px' }}>
    <div style={{ fontSize: 9.5, color: C.hint, textTransform: 'uppercase', letterSpacing: '.05em' }}>{k}</div>
    <div style={{ fontSize: 12.5, color: C.text, fontFamily: 'IBM Plex Mono,monospace', fontWeight: 600 }}>{v}</div>
  </div>
)
const Stat: React.FC<{ k: string; v: string; ok?: boolean }> = ({ k, v, ok }) => (
  <div style={{ background: C.bg3, border: `1px solid ${ok === false ? C.red : C.border}`, borderRadius: 7, padding: '6px 11px' }}>
    <div style={{ fontSize: 9.5, color: C.hint, textTransform: 'uppercase' }}>{k}</div>
    <div style={{ fontSize: 13, color: ok === false ? C.red : C.text, fontFamily: 'IBM Plex Mono,monospace', fontWeight: 700 }}>{v}</div>
  </div>
)

export const InputFilter: React.FC<Props> = ({
  confirmedState, approvedInductorDesign, approvedCapacitorDesign, onBack, onRestart,
}) => {
  const app = (confirmedState as any)?.intake?.application ?? {}
  const tsi = (confirmedState as any)?.topology_specific_inputs ?? {}
  const design = useMemo(() => ({
    vin_min: Number(app.vin_rms_min ?? 90), vin_max: Number(app.vin_rms_max ?? 264),
    pout_lo: Number(app.output_power_w_low_line ?? 1700), pout_hi: Number(app.output_power_w_high_line ?? 3600),
    vout: Number(app.output_bus_voltage_v ?? 393.7), fsw: Number(tsi.recommended_frequency_hz ?? 70000),
    fline: Number(app.line_frequency_hz ?? 60), nch: Number((confirmedState as any)?.selected_channels ?? 2),
    r_input: Number(tsi.default_crest_ripple_ratio ?? 0.20),
    L_phi_uH: Number(tsi.confirmed_L_uH_sel ?? tsi.confirmed_L_uH ?? (approvedInductorDesign as any)?.L_target_uH ?? 240),
  }), [confirmedState, approvedInductorDesign])  // eslint-disable-line react-hooks/exhaustive-deps
  const cap = useMemo(() => ({ ESR_parallel_mohm: Number((approvedCapacitorDesign as any)?.ESR_parallel_mohm ?? 5) }),
    [approvedCapacitorDesign])

  const [opts, setOpts] = useState<Record<string, string>>({
    safety_standard: 'IEC_62368_1', compliance_profile: '5', margin_db: '6', detector: '',
    c_para_earth_pf: '100', sw_rise_time_ns: '20', committed_y_cap_nf: '0', bleeder_r_ohm: '1000000',
  })
  const [opt, setOpt] = useState<{ safety_standards: string[]; leakage_mA: Record<string, number>
    compliance_profiles: Record<string, string> } | null>(null)
  const [res, setRes] = useState<EmiDesign | null>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const setO = (k: string, v: string) => setOpts(s => ({ ...s, [k]: v }))

  useEffect(() => { inputFilterOptions().then(setOpt).catch(() => {}) }, [])

  const run = async () => {
    setBusy(true); setErr(null)
    try {
      const o: Record<string, unknown> = {
        safety_standard: opts.safety_standard, compliance_profile: Number(opts.compliance_profile),
        margin_db: Number(opts.margin_db), c_para_earth_pf: Number(opts.c_para_earth_pf),
        sw_rise_time_ns: Number(opts.sw_rise_time_ns), bleeder_r_ohm: Number(opts.bleeder_r_ohm),
      }
      if (opts.detector) o.detector = opts.detector
      setRes(await inputFilterDesign({ design, cap,
        protection: { committed_y_cap_nf: Number(opts.committed_y_cap_nf) }, opts: o }))
    } catch (e) { setErr((e as Error).message) } finally { setBusy(false) }
  }
  useEffect(() => { run() }, [])  // eslint-disable-line react-hooks/exhaustive-deps

  const r = res?.result
  return (
    <div style={{ maxWidth: 1080, margin: '0 auto' }}>
      <Card>
        <SecHead icon="🎚️" label="Input EMI Filter — Differential & Common Mode"
          sub={`${design.vin_min}–${design.vin_max} Vac · f_sw ${num(design.fsw / 1e3, 0)} kHz`} />
        <div style={{ background: C.tealL, border: `1px solid ${C.teal}55`, borderRadius: 8,
          padding: '8px 12px', marginBottom: 12, fontSize: 11.5, color: C.text }}>
          <b style={{ color: C.teal }}>Synthesis.</b> The PFC draws a switching-frequency ripple current; this
          DM (X-cap + DM choke) and CM (CM choke + Y-caps) filter attenuates it to meet the chosen
          conducted-emission profile over 150 kHz–30 MHz, within the safety earth-leakage limit. With
          2-channel interleaving the first in-band harmonic sits at 2·f_sw. Noise is a first-order
          <i> estimate</i> here — replace with a measured bare-EUT spectrum for sign-off.
        </div>

        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 14 }}>
          <Chip k="V_bus" v={`${num(design.vout, 0)} V`} />
          <Chip k="P_out" v={`${num(design.pout_hi, 0)} W`} />
          <Chip k="f_sw / N_ch" v={`${num(design.fsw / 1e3, 0)} kHz · ${design.nch}`} />
          {res && <Chip k="Inductor ripple I_pp" v={`${num(res.basis.i_ripple_pp_A as number, 2)} A`} />}
          {res && <Chip k="Bulk ESR" v={`${num(res.basis.esr_bulk_mohm as number, 1)} mΩ`} />}
          {r && <Chip k="First harmonic" v={`${num(r.first_harmonic_hz / 1e3, 0)} kHz`} />}
        </div>

        {/* designer choices */}
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'flex-end', marginBottom: 14 }}>
          <label style={{ fontSize: 10.5, color: C.muted, minWidth: 180 }}>Safety standard (leakage limit)<br />
            <select style={selStyle} value={opts.safety_standard} onChange={e => setO('safety_standard', e.target.value)}>
              {(opt?.safety_standards ?? ['IEC_62368_1']).map(s =>
                <option key={s} value={s}>{s}{opt ? ` — ${opt.leakage_mA[s]?.toFixed(2)} mA` : ''}</option>)}</select></label>
          <label style={{ fontSize: 10.5, color: C.muted, minWidth: 260 }}>Compliance profile (emission limit)<br />
            <select style={selStyle} value={opts.compliance_profile} onChange={e => setO('compliance_profile', e.target.value)}>
              {Object.entries(opt?.compliance_profiles ?? { '5': 'Class B' }).map(([k, v]) =>
                <option key={k} value={k}>{k} — {v}</option>)}</select></label>
          <label style={{ fontSize: 10.5, color: C.muted, width: 90 }}>Margin (dB)<br />
            <input style={inStyle} value={opts.margin_db} onChange={e => setO('margin_db', e.target.value)} /></label>
          <label style={{ fontSize: 10.5, color: C.muted, width: 90 }}>Detector<br />
            <select style={selStyle} value={opts.detector} onChange={e => setO('detector', e.target.value)}>
              <option value="">profile</option><option value="AV">AV</option><option value="QP">QP</option></select></label>
          <label style={{ fontSize: 10.5, color: C.muted, width: 110 }}>C_para earth (pF)<br />
            <input style={inStyle} value={opts.c_para_earth_pf} onChange={e => setO('c_para_earth_pf', e.target.value)} /></label>
          <label style={{ fontSize: 10.5, color: C.muted, width: 110 }}>Upstream C_Y (nF)<br />
            <input style={inStyle} value={opts.committed_y_cap_nf} onChange={e => setO('committed_y_cap_nf', e.target.value)} /></label>
          <Btn variant="primary" disabled={busy} onClick={run}>{busy ? '⏳ Synthesizing…' : '🔧 Synthesize filter'}</Btn>
        </div>

        {err && <div style={{ background: C.redL, border: `1px solid ${C.red}55`, borderRadius: 8,
          padding: '9px 12px', marginBottom: 12, fontSize: 12, color: '#fca5a5' }}>⚠ {err}</div>}

        {r && (<>
          <div style={{ marginBottom: 12 }}>
            {r.feasible
              ? <Badge color="green">FEASIBLE — Class {r.conducted_class} / {r.detector}, {num(r.margin_db, 0)} dB margin</Badge>
              : <Badge color="red">INFEASIBLE — see feedback below</Badge>}
          </div>

          <div style={{ fontSize: 10.5, color: C.hint, textTransform: 'uppercase', marginBottom: 5 }}>Required attenuation</div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 14 }}>
            <Stat k="DM" v={`${num(r.dm_req_att_db, 0)} dB @ ${num(r.dm_req_att_f / 1e3, 0)} kHz`} />
            <Stat k="DM corner" v={`${num(r.dm_corner_hz / 1e3, 1)} kHz · ${r.dm_stages} stage`} />
            <Stat k="CM" v={`${num(r.cm_req_att_db, 0)} dB @ ${num(r.cm_req_att_f / 1e3, 0)} kHz`} />
            <Stat k="CM corner" v={`${num(r.cm_corner_hz / 1e3, 1)} kHz · ${r.cm_stages} stage`} />
          </div>

          <div style={{ fontSize: 10.5, color: C.hint, textTransform: 'uppercase', marginBottom: 5 }}>Synthesized components</div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(150px,1fr))', gap: 8, marginBottom: 14 }}>
            <Stat k="DM choke L_DM" v={`${num(r.l_dm * 1e6, 1)} µH`} />
            <Stat k="X-cap C_X" v={`${num(r.c_x * 1e6, 3)} µF`} />
            <Stat k="CM choke L_CM" v={isFinite(r.l_cm) ? `${num(r.l_cm * 1e3, 2)} mH` : '∞'} />
            <Stat k="Y-cap C_Y (total)" v={`${num(r.c_y_emi_total * 1e9, 2)} nF`} />
            <Stat k="Y-cap each (L/N-PE)" v={`${num(r.c_y_emi_total * 1e9 / 2, 2)} nF`} />
            <Stat k="Damping R_d / C_d" v={`${num(r.damp_r, 0)} Ω · ${num(r.damp_c * 1e6, 2)} µF`} />
          </div>

          <div style={{ fontSize: 10.5, color: C.hint, textTransform: 'uppercase', marginBottom: 5 }}>Safety & stability checks</div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 12 }}>
            <Stat k="Earth leakage" v={`${num(r.leakage_actual_A * 1e3, 2)} / ${num(r.leakage_limit_A * 1e3, 2)} mA`}
              ok={r.leakage_actual_A <= r.leakage_limit_A} />
            <Stat k="Middlebrook (Z₀ vs |R_in|)" v={`${num(r.stability_z0_dm, 0)} / ${num(r.stability_rin_conv, 0)} Ω`}
              ok={r.stability_ok} />
            {r.xcap_discharge_s != null && <Stat k="X-cap discharge" v={`${num(r.xcap_discharge_s, 2)} s`} />}
          </div>

          {r.feedback.length > 0 && <div style={{ background: C.redL, border: `1px solid ${C.red}55`, borderRadius: 8,
            padding: '9px 12px', marginBottom: 8, fontSize: 11.5, color: '#fca5a5' }}>
            <b>Pipeline feedback — revisit an earlier stage:</b>
            {r.feedback.map((f, i) => <div key={i} style={{ marginTop: 3 }}>!! {f}</div>)}</div>}
          {r.warnings.length > 0 && <div style={{ fontSize: 10.5, color: C.muted, marginTop: 4 }}>
            {r.warnings.map((w, i) => <div key={i}>⚠ {w}</div>)}</div>}
        </>)}
      </Card>

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '4px 2px 24px' }}>
        <Btn variant="ghost" onClick={onBack}>← Back to input protection</Btn>
        <Btn variant="ghost" onClick={onRestart}>Restart</Btn>
      </div>
    </div>
  )
}
