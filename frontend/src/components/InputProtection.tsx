/**
 * InputProtection.tsx — Input-protection selection (MOV surge + NTC inrush).
 *
 * Two tabs:
 *   • NTC inrush — sizes the inrush limiter + bypass relay from the design grid
 *     (V_ac, worst-case I_in,rms) and the approved capacitor (C_out, bus voltage).
 *   • MOV surge — sizes the varistor(s) per IEC 61000-4-5 from a chosen TEST LEVEL +
 *     PERFORMANCE CRITERION; this is the COMPLIANCE-CERTIFICATION basis and is
 *     documented as its own report chapter. Downstream withstand V_ds is carried in
 *     from the selected MOSFET; the bulk-cap V rating from the approved capacitor.
 *
 * Every carried-in quantity is shown read-only; only the designer knobs (inrush
 * target, IEC level/criterion, margins) are editable. NTC part selection runs against the
 * vendor ICL database (ICL_Database.xlsx); the MOV catalog is still the engine's built-in.
 */
import React, { useEffect, useMemo, useState } from 'react'
import { C, Btn, Card, SecHead, Badge } from './ui'
import { inputProtectionNtc, inputProtectionMov, inputProtectionGdt, inputProtectionFuse, docGenerateReport, inrushSchematicUrl,
         type NtcResult, type MovResult, type GdtResult, type FuseResult, type CatalogRow, type NtcCandidate } from '../api/client'
import type { CapacitorResult } from './Step15Capacitor'

interface Props {
  confirmedState:          Record<string, unknown>
  approvedInductorDesign:  Record<string, unknown>
  approvedCapacitorDesign?: CapacitorResult | null
  // Persisted upstream approvals — forwarded to the full report so it keeps
  // Ch 6 (control, designer R_CS) and Ch 7 (semiconductors) instead of dropping them.
  approvedControlParams?:  Record<string, unknown> | null
  approvedSemiconductor?:  Record<string, unknown> | null
  selectedMosfet?:         Record<string, unknown> | null
  onBack:    () => void
  onNext?:   (ip: Record<string, unknown>) => void
  onRestart: () => void
}

const inStyle: React.CSSProperties = { background: C.bg3, border: `1px solid ${C.border2}`, borderRadius: 6,
  color: C.text, padding: '5px 8px', fontSize: 12, fontFamily: 'IBM Plex Mono,monospace', width: 90 }
const selStyle: React.CSSProperties = { ...inStyle, width: 'auto', minWidth: 70, cursor: 'pointer' }
const cell: React.CSSProperties = { padding: '4px 9px', fontSize: 11.5, borderBottom: `1px solid ${C.border}`,
  fontFamily: 'IBM Plex Mono,monospace', color: C.text, whiteSpace: 'nowrap' }
const num = (v: unknown, d = 2) => (typeof v === 'number' && isFinite(v) ? v.toFixed(d) : '—')

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

const CatalogTable: React.FC<{ rows: CatalogRow[]; emptyNote: string }> = ({ rows, emptyNote }) => (
  rows.length === 0 ? <div style={{ fontSize: 11, color: C.muted }}>{emptyNote}</div>
  : <div style={{ overflowX: 'auto' }}>
      <table style={{ borderCollapse: 'collapse', width: '100%' }}>
        <thead><tr>{['', 'Candidate part', 'Notes (verify on datasheet)'].map(h =>
          <th key={h} style={{ ...cell, color: C.hint, textTransform: 'uppercase', fontSize: 9, textAlign: 'left' }}>{h}</th>)}</tr></thead>
        <tbody>{rows.map((r, i) => (
          <tr key={i}>
            <td style={cell}>{r.ok
              ? <Badge color="green">PASS</Badge>
              : <Badge color="red">FAIL</Badge>}</td>
            <td style={{ ...cell, color: r.ok ? C.text : C.muted, fontWeight: 600, whiteSpace: 'normal' }}>{r.name}</td>
            <td style={{ ...cell, whiteSpace: 'normal', color: C.muted, fontSize: 10.5 }}>
              {r.reasons.map((x, k) => <div key={k}>– {x}</div>)}</td>
          </tr>))}</tbody>
      </table>
    </div>
)

export const InputProtection: React.FC<Props> = ({
  confirmedState, approvedInductorDesign, approvedCapacitorDesign,
  approvedControlParams, approvedSemiconductor, selectedMosfet, onBack, onNext, onRestart,
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
    L_phi_uH: Number(tsi.confirmed_L_uH_sel ?? tsi.confirmed_L_uH ?? (approvedInductorDesign as any)?.L_target_uH ?? 235),
  }), [confirmedState, approvedInductorDesign])  // eslint-disable-line react-hooks/exhaustive-deps

  const cap = useMemo(() => {
    const c = approvedCapacitorDesign as any
    return { C_total_uF: Number(c?.C_total_uF ?? 2350),
             V_rating: Number(c?.V_rating ?? c?.v_rating_V ?? c?.Vdc_rating ?? 450) }
  }, [approvedCapacitorDesign])
  const mosfetVds = Number((selectedMosfet as any)?.vdss ?? 650)

  const [tab, setTab] = useState<'ntc' | 'mov' | 'fuse'>('ntc')
  const [err, setErr] = useState<string | null>(null)

  // ── NTC ──
  const [ntcOpts, setNtcOpts] = useState<Record<string, string>>({
    i_inrush_target: '60', energy_margin: '1.5', r25_margin: '1.10', vref_pulse: '345',
    tau_multiple: '4', ambient_c: '45', r_line: '0', r_emi: '0', r_esr: '0', r_bridge: '0',
    // worst-case / coordination inputs (datasheet / layout; blank = open item in the report)
    fuse_i2t_rating: '', relay_make_rating_a: '', relay_path_ohm: '', off_time_min_ms: '',
    restart_protection: '',
    // round-2 review: startup-path resistances (bypassed/stuck-relay inrush), bridge IFSM, relay timing
    r_wiring_ohm: '', r_pcb_ohm: '', bridge_ifsm_a: '', relay_operate_ms: '', relay_delay_tol_ms: '' })
  const [ntcRes, setNtcRes] = useState<NtcResult | null>(null)
  const [ntcBusy, setNtcBusy] = useState(false)
  const setN = (k: string, v: string) => setNtcOpts(s => ({ ...s, [k]: v }))
  const calcNtc = async (optsOverride?: Record<string, string>) => {
    const opts = optsOverride ?? ntcOpts
    setNtcBusy(true); setErr(null)
    try { setNtcRes(await inputProtectionNtc({ design, cap, opts })) }
    catch (e) { setErr((e as Error).message) } finally { setNtcBusy(false) }
  }
  // designer picks a specific NTC from the ICL catalog → recalc the design around that part
  const selectNtc = (pn: string) => {
    const opts = { ...ntcOpts, selected_part: pn }
    setNtcOpts(opts); calcNtc(opts)
  }

  // ── MOV + GDT (surge) ──
  const [movOpts, setMovOpts] = useState<Record<string, string>>({
    level: '3', criterion: 'A', vac_nom: '230', device_vds: String(mosfetVds), device_absmax: String(mosfetVds),
    imax_margin: '3', repetitive_derate: '0.70', varistor_alpha: '30', v1ma_ratio: '1.60',
    // Phase-2/3/4 coordination + GDT inputs (blank → engine named defaults / DATA-MISSING gate)
    environment: 'commercial', mains_fault_current_A: '', fuse_i2t_rating_A2s: '', lead_inductance_nH: '20',
    follow_current_extinguish_A: '', insulation_withstand_V: '' })
  const [movCM, setMovCM] = useState(true)
  const [movRes, setMovRes] = useState<MovResult | null>(null)
  const [movBusy, setMovBusy] = useState(false)
  // Architecture choice: 'auto' follows the recommendation; else force MOV-only / MOV+GDT.
  const [movArch, setMovArch] = useState<'auto' | 'mov' | 'movgdt'>('auto')
  const [gdtRes, setGdtRes] = useState<GdtResult | null>(null)
  const setM = (k: string, v: string) => setMovOpts(s => ({ ...s, [k]: v }))
  const movOptsPayload = (): Record<string, unknown> => {
    const o: Record<string, unknown> = { common_mode_protection: movCM }
    Object.entries(movOpts).forEach(([k, v]) => { if (v !== '' && v != null) o[k] = v })
    return o
  }
  const calcMov = async (override?: Record<string, string>) => {
    setMovBusy(true); setErr(null)
    try {
      const eff = override ?? movOpts
      const o: Record<string, unknown> = { common_mode_protection: movCM }
      Object.entries(eff).forEach(([k, v]) => { if (v !== '' && v != null) o[k] = v })
      const [m, g] = await Promise.all([
        inputProtectionMov({ design, cap, mosfet: { vdss: Number(eff.device_vds) }, opts: o }),
        inputProtectionGdt({ design, opts: o }),
      ])
      setMovRes(m); setGdtRes(g)
    } catch (e) { setErr((e as Error).message) } finally { setMovBusy(false) }
  }
  const selectMov = (pn: string) => { const o = { ...movOpts, selected_part: pn }; setMovOpts(o); calcMov(o) }
  // verdict → badge colour (PASS green / CONDITIONAL amber / FAIL red)
  // OPEN/CHECK are "not yet proven", not failures — they must not read as red (see the fuse six-gate table)
  const vColor = (v?: string) => v === 'PASS' ? 'green' : v === 'CONDITIONAL' ? 'amber'
    : (v === 'OPEN' || v === 'CHECK') ? 'gray' : 'red'
  // Effective architecture = recommendation unless the designer overrode it.
  const useGdt = movArch === 'movgdt' || (movArch === 'auto' && !!gdtRes?.required.required)

  // ── Line fuse ── (reuses mains_fault_current_A + margins; feeds startup I²t via the design/NTC grid)
  const [fuseOpts, setFuseOpts] = useState<Record<string, string>>({
    fuse_current_margin: '1.5', fuse_i2t_margin: '2.0', fuse_ambient_derate: '1.0', fuse_load_factor: '0.75',
    // gate 6 (thermal implementation) + gate 5 (fault coordination) — blank leaves the gate OPEN
    fuse_ambient_C: '', fuseholder_rise_C: '', fuse_derate_per_C: '',
    mov_fail_short_current_A: '', relay_stuck_fault_current_A: '' })
  const [fuseRes, setFuseRes] = useState<FuseResult | null>(null)
  const [fuseBusy, setFuseBusy] = useState(false)
  const setF = (k: string, v: string) => setFuseOpts(s => ({ ...s, [k]: v }))
  const calcFuse = async (override?: Record<string, string>) => {
    setFuseBusy(true); setErr(null)
    try {
      // fuse selection shares the fault current + startup basis (incl. selected NTC) with NTC/MOV
      const fo = override ?? fuseOpts
      const opts: Record<string, unknown> = { ...ntcOpts, ...fo,
        mains_fault_current_A: ntcOpts.mains_fault_current_A || movOpts.mains_fault_current_A }
      setFuseRes(await inputProtectionFuse({ design, cap, opts }))
    } catch (e) { setErr((e as Error).message) } finally { setFuseBusy(false) }
  }
  const selectFuse = (pn: string) => { const o = { ...fuseOpts, fuse_selected_part: pn }; setFuseOpts(o); calcFuse(o) }
  // The selected fuse's melting I²t auto-feeds the NTC/MOV coordination in the report.
  const selFuseI2t = fuseRes?.selected_i2t ?? null

  useEffect(() => { calcNtc(); calcMov(); calcFuse() }, [])  // eslint-disable-line react-hooks/exhaustive-deps

  const [rptBusy, setRptBusy] = useState(false)
  // FULL report: all previous chapters (design basis, magnetics, DC-bus capacitor) + the
  // input-protection chapters — not only Ch 8–9.
  // The input-protection payload for the report (Ch 8 NTC + Ch 9 MOV). Shared by this page's own
  // report button AND handed up via onNext so the EMI page can include Ch 8/9 in its combined report.
  const ipReportPayload = (): Record<string, unknown> => ({
    design, cap, mosfet: { vdss: Number(movOpts.device_vds) },
    // fold the fuse selection margins in, and auto-feed the selected fuse I²t into the NTC/MOV coordination
    ntc_opts: { ...ntcOpts, ...fuseOpts,
      ...(selFuseI2t && !ntcOpts.fuse_i2t_rating ? { fuse_i2t_rating: String(selFuseI2t) } : {}) },
    mov_opts: { ...movOptsPayload(), surge_architecture: useGdt ? 'MOV+GDT' : 'MOV-only',
      ...fuseOpts,
      ...(selFuseI2t && !movOpts.fuse_i2t_rating_A2s ? { fuse_i2t_rating_A2s: String(selFuseI2t) } : {}) },
  })

  const downloadReport = async () => {
    setRptBusy(true); setErr(null)
    try {
      const blob = await docGenerateReport({
        state:           confirmedState as Record<string, unknown>,
        approved_design: approvedInductorDesign as Record<string, unknown>,
        step15_result:   approvedCapacitorDesign ? ({ ...approvedCapacitorDesign } as Record<string, unknown>) : {},
        // Forward the persisted upstream approvals so the full report keeps Ch 6
        // (designer's control config, R_CS) and Ch 7 (semiconductor selection).
        ...(approvedControlParams ? { step16_params: approvedControlParams } : {}),
        ...(approvedSemiconductor ? { semiconductor: approvedSemiconductor } : {}),
        input_protection: ipReportPayload(),
      })
      const url = URL.createObjectURL(blob); const a = document.createElement('a')
      a.href = url; a.download = `PFC_Report_${(confirmedState as any)?.project_id ?? 'design'}_incl_InputProtection.pdf`
      document.body.appendChild(a); a.click(); document.body.removeChild(a)
      setTimeout(() => URL.revokeObjectURL(url), 150)
    } catch (e) { setErr((e as Error).message) } finally { setRptBusy(false) }
  }

  const verdictColor = (v: string) => v === 'OK' ? 'green' : v === 'TIGHT' ? 'amber' : 'red'

  return (
    <div style={{ maxWidth: 1080, margin: '0 auto' }}>
      <Card>
        <SecHead icon="🛡️" label="Input Protection — MOV surge + NTC inrush"
          sub={`${design.vin_min}–${design.vin_max} Vac · bus ${num(design.vout, 0)} V`} />
        <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
          {([['ntc', '🌡️ NTC inrush limiter'], ['mov', '⚡ Surge (MOV + GDT)'], ['fuse', '🔌 Line fuse']] as [typeof tab, string][])
            .map(([t, lbl]) => (
              <button key={t} onClick={() => setTab(t)} style={{
                padding: '7px 16px', borderRadius: 8, cursor: 'pointer', fontSize: 13, fontWeight: 600,
                border: `1px solid ${tab === t ? C.accent : C.border}`, background: tab === t ? C.accentL : C.bg3,
                color: tab === t ? C.accent : C.muted }}>{lbl}</button>
            ))}
        </div>
        {err && <div style={{ background: C.redL, border: `1px solid ${C.red}55`, borderRadius: 8,
          padding: '9px 12px', marginBottom: 12, fontSize: 12, color: '#fca5a5' }}>⚠ {err}</div>}

        {/* ─────────────── NTC ─────────────── */}
        {tab === 'ntc' && (
          <div>
            <div style={{ fontSize: 11.5, color: C.muted, marginBottom: 10 }}>
              Carried in from the design grid and the approved capacitor — read-only:
            </div>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 14 }}>
              <Chip k="V_ac range" v={`${design.vin_min}–${design.vin_max} V`} />
              <Chip k="C_out (Step 15)" v={`${num(cap.C_total_uF, 0)} µF`} />
              <Chip k="Bus voltage" v={`${num(design.vout, 0)} V`} />
              {ntcRes && <Chip k="I_rms worst (grid)" v={`${num(ntcRes.result.i_rms_worst, 1)} A`} />}
            </div>
            <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'flex-end', marginBottom: 14 }}>
              <Knob label="Inrush target" unit="A" value={ntcOpts.i_inrush_target} onChange={v => setN('i_inrush_target', v)} />
              <Knob label="Energy margin" unit="×" value={ntcOpts.energy_margin} onChange={v => setN('energy_margin', v)} />
              <Knob label="R25 margin" unit="×" value={ntcOpts.r25_margin} onChange={v => setN('r25_margin', v)} />
              <Knob label="Pulse V_ref" unit="V" value={ntcOpts.vref_pulse} onChange={v => setN('vref_pulse', v)} />
              <Knob label="Bypass delay" unit="×τ" value={ntcOpts.tau_multiple} onChange={v => setN('tau_multiple', v)} />
              <Knob label="Loop R (line+EMI+ESR)" unit="Ω" value={ntcOpts.r_emi} onChange={v => setN('r_emi', v)} />
              <Btn variant="primary" disabled={ntcBusy} onClick={calcNtc}>{ntcBusy ? '⏳ Sizing…' : '↻ Re-size NTC'}</Btn>
            </div>
            {/* Worst-case / coordination inputs (datasheet + layout). Blank ⇒ shown as an open item. */}
            <div style={{ fontSize: 10.5, color: C.hint, textTransform: 'uppercase', marginBottom: 5 }}>
              Worst-case & coordination <span style={{ color: C.muted, textTransform: 'none' }}>— datasheet / layout; blank = open item in the report</span></div>
            <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'flex-end', marginBottom: 14 }}>
              <Knob label="Fuse I²t rating" unit="A²s" value={ntcOpts.fuse_i2t_rating} onChange={v => setN('fuse_i2t_rating', v)} />
              <Knob label="Relay make rating" unit="A" value={ntcOpts.relay_make_rating_a} onChange={v => setN('relay_make_rating_a', v)} />
              <Knob label="Relay-path R" unit="Ω" value={ntcOpts.relay_path_ohm} onChange={v => setN('relay_path_ohm', v)} />
              <Knob label="Min off-time" unit="ms" value={ntcOpts.off_time_min_ms} onChange={v => setN('off_time_min_ms', v)} />
              <label style={{ fontSize: 10.5, color: C.muted, minWidth: 150 }}>Restart protection<br />
                <select style={{ background: C.bg3, border: `1px solid ${C.border2}`, borderRadius: 6, color: C.text, padding: '5px 8px', fontSize: 12, width: '100%' }}
                  value={ntcOpts.restart_protection} onChange={e => setN('restart_protection', e.target.value)}>
                  <option value="">— unstated —</option><option value="hardware">hardware</option>
                  <option value="firmware">firmware</option><option value="procedure">procedure</option></select></label>
            </div>
            {/* Startup-path resistances → bypassed/stuck-relay inrush + 3-column stress (review round 2). */}
            <div style={{ fontSize: 10.5, color: C.hint, textTransform: 'uppercase', marginBottom: 5 }}>
              Startup path & stress <span style={{ color: C.muted, textTransform: 'none' }}>— for bypassed/stuck-relay inrush &amp; bridge IFSM; blank = OPEN</span></div>
            <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'flex-end', marginBottom: 14 }}>
              <Knob label="R_bridge" unit="Ω" value={ntcOpts.r_bridge} onChange={v => setN('r_bridge', v)} />
              <Knob label="R_ESR" unit="Ω" value={ntcOpts.r_esr} onChange={v => setN('r_esr', v)} />
              <Knob label="R_wiring" unit="Ω" value={ntcOpts.r_wiring_ohm} onChange={v => setN('r_wiring_ohm', v)} />
              <Knob label="R_PCB" unit="Ω" value={ntcOpts.r_pcb_ohm} onChange={v => setN('r_pcb_ohm', v)} />
              <Knob label="Bridge IFSM" unit="A" value={ntcOpts.bridge_ifsm_a} onChange={v => setN('bridge_ifsm_a', v)} />
              <Knob label="Relay operate" unit="ms" value={ntcOpts.relay_operate_ms} onChange={v => setN('relay_operate_ms', v)} />
              <Knob label="Delay tolerance" unit="ms" value={ntcOpts.relay_delay_tol_ms} onChange={v => setN('relay_delay_tol_ms', v)} />
            </div>
            {/* Inrush-limiter topology schematic (same drawing embedded in the Ch 8 report). */}
            <details style={{ marginBottom: 14 }}>
              <summary style={{ cursor: 'pointer', fontSize: 11.5, color: C.teal, fontWeight: 600 }}>
                🔧 Inrush-limiter schematic (NTC + relay bypass)</summary>
              <div style={{ background: '#fff', border: `1px solid ${C.border}`, borderRadius: 8, padding: 8, marginTop: 8 }}>
                <img src={inrushSchematicUrl()} alt="NTC + relay-bypass inrush-limiter schematic"
                  style={{ width: '100%', height: 'auto', display: 'block' }} />
              </div>
            </details>

            {ntcRes && (<>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(150px,1fr))', gap: 8, marginBottom: 14 }}>
                <Chip k="NTC R25 (pick)" v={`${num(ntcRes.result.r25_pick, 2)} Ω`} />
                <Chip k="Charge energy E_cap" v={`${num(ntcRes.result.e_cap, 0)} J`} />
                <Chip k="Pulse rating req." v={`≥ ${num(ntcRes.result.e_pulse_required, 0)} J`} />
                <Chip k="Equiv. max-C @ V_ref" v={`${num(ntcRes.result.cmax_equiv_required * 1e6, 0)} µF`} />
                <Chip k="Precharge τ" v={`${num(ntcRes.result.tau * 1e3, 1)} ms`} />
                <Chip k="Bypass close delay" v={`${num(ntcRes.result.t_bypass * 1e3, 0)} ms`} />
                <Chip k="Relay contact V" v={`≥ ${num(ntcRes.result.relay_contact_v, 0)} V`} />
                <Chip k="Relay contact A" v={`≥ ${num(ntcRes.result.relay_contact_a, 1)} A`} />
              </div>
              <div style={{ display: 'flex', gap: 18, flexWrap: 'wrap', marginBottom: 14 }}>
                <div>
                  <div style={{ fontSize: 10, color: C.hint, textTransform: 'uppercase', marginBottom: 4 }}>Inrush target sweep</div>
                  <table style={{ borderCollapse: 'collapse' }}><thead><tr>
                    {['Target I (A)', 'R_min total (Ω)'].map(h => <th key={h} style={{ ...cell, color: C.hint, fontSize: 9 }}>{h}</th>)}
                  </tr></thead><tbody>{ntcRes.result.sweep.map(([t, r], i) => (
                    <tr key={i}><td style={cell}>{t}</td><td style={cell}>{num(r, 3)}</td></tr>))}</tbody></table>
                </div>
                <div>
                  <div style={{ fontSize: 10, color: C.hint, textTransform: 'uppercase', marginBottom: 4 }}>Continuous self-heat (why bypass)</div>
                  <table style={{ borderCollapse: 'collapse' }}><thead><tr>
                    {['R_hot (Ω)', 'P_loss = I²R (W)'].map(h => <th key={h} style={{ ...cell, color: C.hint, fontSize: 9 }}>{h}</th>)}
                  </tr></thead><tbody>{ntcRes.result.loss_rows.map(([rh, pl], i) => (
                    <tr key={i}><td style={cell}>{num(rh, 2)}</td><td style={cell}>{num(pl, 1)}</td></tr>))}</tbody></table>
                </div>
              </div>
              {ntcRes.selected && (
                <div style={{ background: C.tealL, border: `1px solid ${C.teal}66`, borderRadius: 8,
                  padding: '10px 12px', marginBottom: 12 }}>
                  <div style={{ fontSize: 10, color: C.teal, textTransform: 'uppercase', fontWeight: 700,
                    letterSpacing: '.05em', marginBottom: 6 }}>
                    Selected NTC — design recalculated for the actual part
                  </div>
                  <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                    <Chip k="Part" v={`${ntcRes.selected.mfr ?? ''} ${ntcRes.selected.part_number ?? ''}`} />
                    <Chip k="R25 (actual)" v={`${num(ntcRes.selected.r25_ohm, 1)} Ω`} />
                    <Chip k="Cold inrush (actual)" v={`${num(ntcRes.selected.i_inrush_actual_A, 1)} A ${ntcRes.selected.meets_target ? '✓' : '✗ > target'}`} />
                    <Chip k="τ / bypass delay" v={`${num(ntcRes.selected.tau_ms, 1)} / ${num(ntcRes.selected.t_bypass_ms, 0)} ms`} />
                    <Chip k="Energy margin (est.)" v={ntcRes.selected.energy_margin != null ? `${num(ntcRes.selected.energy_margin, 2)}× E_cap` : '—'} />
                  </div>
                </div>
              )}
              <div style={{ fontSize: 10.5, color: C.hint, textTransform: 'uppercase', marginBottom: 5 }}>
                Candidate screen — nominal R25 ≥ {num(ntcRes.result.r25_nom_required, 2)} Ω
                (tolerance-aware: {num((ntcRes.result.r25_tol_screen ?? 0) * 100, 0)}% below still holds the inrush)
                and pulse rating ≥ {num(ntcRes.result.e_pulse_required, 0)} J — click Select to base the design on a part
              </div>
              {(() => {
                const cands = (ntcRes.candidates ?? []) as NtcCandidate[]
                if (!cands.length) return <CatalogTable rows={ntcRes.catalog} emptyNote="No catalog parts loaded." />
                const vd = (c: NtcCandidate) => c.verdict ?? (c.ok ? 'PASS' : 'FAIL')
                const pass = cands.filter(c => vd(c) === 'PASS')
                const cond = cands.filter(c => vd(c) === 'CONDITIONAL')
                const qualifying = [...pass, ...cond]
                const fallback = qualifying.length === 0        // never-empty: show closest if nothing qualifies
                const shown = fallback ? cands : qualifying
                const ntcRow = (c: NtcCandidate, key: string) => {
                  const isSel = ntcRes.selected?.part_number === c.part_number
                  const v = vd(c)
                  return (
                    <tr key={key} style={isSel ? { background: 'rgba(45,212,191,.08)' } : undefined}>
                      <td style={cell}><Badge color={vColor(v)}>{v}</Badge></td>
                      <td style={cell}>
                        <Btn variant={isSel ? 'success' : 'ghost'} onClick={() => selectNtc(c.part_number ?? '')}>
                          {isSel ? '✓ Selected' : 'Select'}
                        </Btn>
                      </td>
                      <td style={{ ...cell, whiteSpace: 'normal', fontWeight: 600, color: v === 'FAIL' ? C.muted : C.text }}>
                        {c.mfr} {c.datasheet_url
                          ? <a href={(c.datasheet_url.startsWith('//') ? 'https:' : '') + c.datasheet_url} target="_blank"
                               rel="noreferrer" style={{ color: C.accent }}>{c.part_number}</a>
                          : c.part_number}
                      </td>
                      <td style={cell}>{num(c.r25, 1)}</td>
                      <td style={cell}>{num(c.diameter_mm, 0)}</td>
                      <td style={cell}>{num(c.imax, 1)}</td>
                      <td style={cell}>{num(c.energy_est_J, 0)}</td>
                      <td style={{ ...cell, whiteSpace: 'normal', color: C.muted, fontSize: 10 }}>
                        {(c.reasons ?? []).slice(0, 2).map((x, k) => <div key={k}>– {x}</div>)}</td>
                    </tr>
                  )
                }
                const divider = (label: string) => (
                  <tr><td colSpan={8} style={{ ...cell, background: C.bg3, color: C.hint, fontSize: 9,
                    textTransform: 'uppercase', letterSpacing: '.05em', fontWeight: 700 }}>{label}</td></tr>
                )
                return (
                  <div style={{ overflowX: 'auto' }}>
                    {fallback && (
                      <div style={{ fontSize: 10, color: C.amber, marginBottom: 6 }}>
                        No catalog part clears the R25 inrush gate — showing the closest parts. Relax the inrush
                        target, credit more parasitic resistance, or use active precharge.
                      </div>
                    )}
                    <table style={{ borderCollapse: 'collapse', width: '100%' }}>
                      <thead><tr>{['Verdict', '', 'Mfr / Part', 'R25 (Ω)', 'Ø (mm)', 'I_max (A)', 'E est. (J)', 'Notes'].map((h, i) =>
                        <th key={i} style={{ ...cell, color: C.hint, textTransform: 'uppercase', fontSize: 9, textAlign: 'left' }}>{h}</th>)}</tr></thead>
                      <tbody>
                        {fallback
                          ? shown.map((c, i) => ntcRow(c, `f${i}`))
                          : <>
                              {pass.map((c, i) => ntcRow(c, `p${i}`))}
                              {cond.length > 0 && divider('Conditional — clears the inrush gate; confirm pulse energy on the datasheet')}
                              {cond.map((c, i) => ntcRow(c, `c${i}`))}
                            </>}
                      </tbody>
                    </table>
                  </div>
                )
              })()}
              <div style={{ fontSize: 9.5, color: C.muted, marginTop: 6 }}>
                Screened against the vendor ICL database (ICL_Database.xlsx). <b>PASS</b> = nominal R25 clears the
                tolerance-aware inrush gate and the (estimated) pulse energy meets the requirement;
                <b> CONDITIONAL</b> = clears the inrush gate but pulse energy (estimated from disc Ø) needs datasheet
                confirmation; parts that cannot hold the inrush are hidden. R25 is the real datasheet value.
                Selecting a part documents the choice in the report (§8.7) and recalculates the inrush/precharge
                numbers around its actual R25 (§8.8).
              </div>
            </>)}
          </div>
        )}

        {/* ─────────────── MOV ─────────────── */}
        {tab === 'mov' && (
          <div>
            <div style={{ background: C.tealL, border: `1px solid ${C.teal}55`, borderRadius: 8,
              padding: '8px 12px', marginBottom: 12, fontSize: 11.5, color: C.text }}>
              <b style={{ color: C.teal }}>Compliance basis.</b> MOV sizing follows IEC/EN 61000-4-5 (combination wave).
              The <b>test level</b> sets the surge stress, the <b>performance criterion</b> sets the acceptance bar, and
              the continuous line sets the MCOV. These choices are the certification record — documented in their own chapter.
            </div>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 14 }}>
              <Chip k="V_ac max / nom" v={`${design.vin_max} / ${movOpts.vac_nom} V`} />
              <Chip k="Device V_ds (MOSFET)" v={`${num(Number(movOpts.device_vds), 0)} V`} />
              <Chip k="Bulk-cap V rating" v={`${num(cap.V_rating, 0)} V`} />
            </div>
            <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'flex-end', marginBottom: 14 }}>
              <label style={{ fontSize: 10.5, color: C.muted }}>IEC test level<br />
                <select style={selStyle} value={movOpts.level} onChange={e => setM('level', e.target.value)}>
                  {['1', '2', '3', '4', 'X'].map(o => <option key={o} value={o}>{o === 'X' ? 'X (custom)' : `Level ${o}`}</option>)}</select></label>
              <label style={{ fontSize: 10.5, color: C.muted }}>Performance criterion<br />
                <select style={selStyle} value={movOpts.criterion} onChange={e => setM('criterion', e.target.value)}>
                  {[['A', 'A — ride-through'], ['B', 'B — self-recover'], ['C', 'C — operator reset']].map(([v, l]) =>
                    <option key={v} value={v}>{l}</option>)}</select></label>
              <label style={{ fontSize: 10.5, color: C.muted }}>Common-mode MOVs<br />
                <select style={selStyle} value={movCM ? 'yes' : 'no'} onChange={e => setMovCM(e.target.value === 'yes')}>
                  <option value="yes">L-PE + N-PE</option><option value="no">L-N only</option></select></label>
              <label style={{ fontSize: 10.5, color: C.muted }}>Install environment<br />
                <select style={selStyle} value={movOpts.environment} onChange={e => setM('environment', e.target.value)}>
                  {[['residential', 'residential'], ['commercial', 'commercial'], ['industrial', 'industrial'],
                    ['lightning', 'lightning-exposed'], ['telecom', 'telecom']].map(([v, l]) =>
                    <option key={v} value={v}>{l}</option>)}</select></label>
              <Knob label="Device V_ds" unit="V" value={movOpts.device_vds} onChange={v => setM('device_vds', v)} />
              <Knob label="Device abs-max" unit="V" value={movOpts.device_absmax} onChange={v => setM('device_absmax', v)} />
              <Knob label="I_max margin" unit="×" value={movOpts.imax_margin} onChange={v => setM('imax_margin', v)} />
              <Btn variant="primary" disabled={movBusy} onClick={calcMov}>{movBusy ? '⏳ Sizing…' : '↻ Re-size surge'}</Btn>
            </div>
            <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'flex-end', marginBottom: 14 }}>
              <Knob label="Lead inductance" unit="nH" value={movOpts.lead_inductance_nH} onChange={v => setM('lead_inductance_nH', v)} />
              <Knob label="Mains fault I" unit="A" value={movOpts.mains_fault_current_A} onChange={v => setM('mains_fault_current_A', v)} />
              <Knob label="Fuse I²t" unit="A²s" value={movOpts.fuse_i2t_rating_A2s} onChange={v => setM('fuse_i2t_rating_A2s', v)} />
              <Knob label="GDT follow-I extinguish" unit="A" value={movOpts.follow_current_extinguish_A} onChange={v => setM('follow_current_extinguish_A', v)} />
              <Knob label="Insulation withstand" unit="V" value={movOpts.insulation_withstand_V} onChange={v => setM('insulation_withstand_V', v)} />
            </div>

            {movRes && (<>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(150px,1fr))', gap: 8, marginBottom: 14 }}>
                <Chip k="MCOV class" v={`${movRes.mcov.class} Vac`} />
                <Chip k="V_1mA (≈)" v={`${num(movRes.mcov.v1ma, 0)} V`} />
                <Chip k="Governing path" v={movRes.stress.governing?.split('(')[0] ?? '—'} />
                <Chip k="Criterion gate" v={movRes.criterion.gate_uses_absmax ? 'abs-max' : `V_ds − ${num(movRes.criterion.dev_margin_V, 0)}`} />
              </div>
              <div style={{ fontSize: 10.5, color: C.hint, textTransform: 'uppercase', marginBottom: 5 }}>
                Surge stress per coupling mode (LEVEL {movOpts.level}) → per-path clamp & coordination
              </div>
              <div style={{ overflowX: 'auto', marginBottom: 14 }}>
                <table style={{ borderCollapse: 'collapse', width: '100%' }}>
                  <thead><tr>{['Path', 'Z (Ω)', 'V_oc (V)', 'I_sc (A)', 'Clamp Vc (V)', 'I_max req (A)', '8/20 E (J)', 'vs device'].map(h =>
                    <th key={h} style={{ ...cell, color: C.hint, fontSize: 9, textAlign: 'left' }}>{h}</th>)}</tr></thead>
                  <tbody>{movRes.targets.map((t, i) => (
                    <tr key={i}>
                      <td style={cell}>{t.path}</td>
                      <td style={cell}>{num(t.z, 0)}</td>
                      <td style={cell}>{num(t.v_oc, 0)}</td>
                      <td style={cell}>{num(t.i_sc, 0)}</td>
                      <td style={{ ...cell, fontWeight: 700, color: C.text }}>{num(t.vc, 0)}</td>
                      <td style={cell}>{num(t.imax_required, 0)}</td>
                      <td style={cell}>{num(t.energy_8_20, 1)}</td>
                      <td style={cell}><Badge color={verdictColor(t.coord)}>{t.coord}</Badge></td>
                    </tr>))}</tbody>
                </table>
              </div>
              {/* Selection gates, stated BEFORE the candidate list so the screen filters against
                  declared numbers instead of reading as a conclusion (MOV review, layer 3). */}
              {(movRes.gates ?? []).length > 0 && (<>
                <div style={{ fontSize: 10.5, color: C.hint, textTransform: 'uppercase', marginBottom: 5 }}>
                  Selection gates — what a catalog MOV must clear (derived before screening)
                </div>
                <div style={{ overflowX: 'auto', marginBottom: 14 }}>
                  <table style={{ borderCollapse: 'collapse', width: '100%' }}>
                    <thead><tr>{['#', 'Gate', 'Requirement', 'Basis'].map(h =>
                      <th key={h} style={{ ...cell, color: C.hint, fontSize: 9, textAlign: 'left' }}>{h}</th>)}</tr></thead>
                    <tbody>{(movRes.gates ?? []).map(g => (
                      <tr key={g.n}>
                        <td style={cell}>{g.n}</td>
                        <td style={cell}>{g.name}</td>
                        <td style={{ ...cell, fontWeight: 600 }}>{g.requirement}</td>
                        <td style={{ ...cell, fontSize: 9.5, color: C.muted }}>{g.basis}</td>
                      </tr>))}</tbody>
                  </table>
                </div>
              </>)}

              <div style={{ fontSize: 10.5, color: C.hint, textTransform: 'uppercase', marginBottom: 5 }}>
                Candidate MOVs — governing path {movRes.stress.governing?.split('(')[0] ?? ''} (criterion {movRes.criterion.name}) · select one
              </div>
              <div style={{ fontSize: 9.5, color: C.muted, marginBottom: 6 }}>
                The <b>{movRes.mcov.class} Vac MCOV class</b> above is a <i>voltage-class</i> decision, not a part
                selection. Clamp, energy, surge current and safety are only proven once a part is chosen below.
              </div>
              {movRes.selected && (
                <div style={{ background: C.tealL, border: `1px solid ${C.teal}55`, borderRadius: 8,
                  padding: '8px 12px', marginBottom: 8, fontSize: 11.5, color: C.text }}>
                  <b style={{ color: C.teal }}>Selected:</b> {movRes.selected.mfr} {movRes.selected.part_number} —{' '}
                  {num(movRes.selected.mcov, 0)} Vac, V₁ₘₐ {num(movRes.selected.v1ma, 0)} V, I_max {num(movRes.selected.imax, 0)} A.{' '}
                  {movRes.selected.verdict === 'CONDITIONAL' ? 'CONDITIONAL — clamp unverified (add Vc@In to confirm ride-through).' : ''}
                </div>
              )}

              {/* Recalculation on the ACTUAL part — the clamp above is the voltage-CLASS figure. */}
              {movRes.selected_recalc && (() => {
                const R = movRes.selected_recalc!
                const classVc = movRes.targets.find(t => t.path === movRes.stress.governing)?.vc
                return (
                <div style={{ border: `1px solid ${C.teal}55`, borderRadius: 8, padding: '10px 12px', marginBottom: 12 }}>
                  <div style={{ fontSize: 10.5, color: C.hint, textTransform: 'uppercase', marginBottom: 6 }}>
                    Selected part — recalculated{' '}
                    <Badge color={vColor(R.release_status)}>{R.release_status}</Badge>
                  </div>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(140px,1fr))', gap: 8, marginBottom: 10 }}>
                    <Chip k="V₁ₘₐ (datasheet)" v={`${num(R.v1ma, 0)} V`} />
                    <Chip k="Clamp Vc (this part)" v={`${num(R.vc, 0)} V${R.alpha_estimated ? ' est.' : ''}`} />
                    <Chip k="Clamp Vc (class)" v={classVc != null ? `${num(classVc, 0)} V` : '—'} />
                    <Chip k="Margin vs gate" v={`${R.clamp_margin_V >= 0 ? '+' : ''}${num(R.clamp_margin_V, 0)} V`} />
                    <Chip k="With layout overshoot" v={`${num(R.overshoot.vc_effective, 0)} V`} />
                  </div>
                  <div style={{ overflowX: 'auto' }}>
                    <table style={{ borderCollapse: 'collapse', width: '100%' }}>
                      <thead><tr>{['#', 'Gate', 'Requirement', 'Result', 'Status'].map(h =>
                        <th key={h} style={{ ...cell, color: C.hint, fontSize: 9, textAlign: 'left' }}>{h}</th>)}</tr></thead>
                      <tbody>{R.gates.map(g => (
                        <tr key={g.n}>
                          <td style={cell}>{g.n}</td>
                          <td style={cell}>{g.name}</td>
                          <td style={{ ...cell, fontSize: 9.5, color: C.muted }}>{g.requirement}</td>
                          <td style={{ ...cell, fontSize: 9.5 }}>{g.result}</td>
                          <td style={cell}><Badge color={vColor(g.status)}>{g.status}</Badge></td>
                        </tr>))}</tbody>
                    </table>
                  </div>
                  {R.alpha_estimated && (
                    <div style={{ fontSize: 9.5, color: C.amber, marginTop: 8 }}>
                      The clamp is <b>ESTIMATED</b>: this part publishes no Vc at a rated current, so the generic
                      varistor exponent was used. It is reported DATA MISSING rather than PASS or FAIL — an estimate
                      cannot settle Criterion {movRes.criterion.name} either way.
                    </div>
                  )}
                  {R.blockers.length > 0 && (
                    <div style={{ fontSize: 9.5, color: C.muted, marginTop: 6 }}>
                      <b>Release blockers:</b> {R.blockers.join(' · ')}. These stop final sign-off only —
                      part selection is never blocked.
                    </div>
                  )}
                  {movRes.energy_basis && (
                    <div style={{ fontSize: 9.5, color: C.muted, marginTop: 4 }}>
                      Energy survival judged against the <b>{movRes.energy_basis}</b>.
                    </div>
                  )}
                </div>)
              })()}
              <div style={{ overflowX: 'auto', marginBottom: 6 }}>
                <table style={{ borderCollapse: 'collapse', width: '100%' }}>
                  <thead><tr>{['', 'Part', 'MCOV', 'V₁ₘₐ', 'I_max', 'Energy', 'Clamp', 'Verdict'].map(h =>
                    <th key={h} style={{ ...cell, color: C.hint, fontSize: 9, textAlign: 'left' }}>{h}</th>)}</tr></thead>
                  <tbody>{(movRes.candidates ?? []).slice(0, 12).map((c, i) => {
                    const isSel = movOpts.selected_part === c.part_number
                    return (
                    <tr key={i} style={isSel ? { background: C.tealL } : undefined}>
                      <td style={cell}><Btn variant={isSel ? 'success' : 'ghost'} onClick={() => selectMov(c.part_number ?? '')}>
                        {isSel ? '✓' : 'Select'}</Btn></td>
                      <td style={cell}>{c.part_number}</td>
                      <td style={cell}>{num(c.mcov, 0)}</td>
                      <td style={cell}>{num(c.v1ma, 0)}</td>
                      <td style={cell}>{num(c.imax, 0)}A</td>
                      <td style={cell}>{c.energy_2ms_J != null ? `${num(c.energy_2ms_J, 0)}J` : '—'}</td>
                      <td style={cell}>{c.clamp_vc != null ? `${num(c.clamp_vc, 0)}V` : 'DATA MISSING'}</td>
                      <td style={cell}><Badge color={vColor(c.verdict)}>{c.verdict}</Badge></td>
                    </tr>)})}</tbody>
                </table>
              </div>
              <div style={{ fontSize: 9.5, color: C.muted, marginTop: 6 }}>
                Screened against the vendor MOV database (1140 parts). <b>CONDITIONAL</b> = selectable but the
                clamp is unverified (datasheet Vc@In absent) — never a silent pass. MCOV is invariant to level/criterion.
              </div>

              {/* ── GDT recommendation + common-mode diversion ── */}
              {gdtRes && (<div style={{ marginTop: 18, borderTop: `1px solid ${C.border}`, paddingTop: 14 }}>
                <div style={{ background: gdtRes.required.required ? C.redL : C.tealL,
                  border: `1px solid ${(gdtRes.required.required ? C.red : C.teal)}55`, borderRadius: 8,
                  padding: '9px 12px', marginBottom: 12, fontSize: 11.5, color: C.text }}>
                  <b style={{ color: gdtRes.required.required ? C.red : C.teal }}>
                    Recommendation — {gdtRes.required.recommend} ({gdtRes.required.required ? 'REQUIRED' : 'OPTIONAL'}).</b>{' '}
                  {gdtRes.required.reason}
                </div>
                <label style={{ fontSize: 10.5, color: C.muted, marginBottom: 10, display: 'inline-block' }}>
                  Surge architecture&nbsp;
                  <select style={selStyle} value={movArch} onChange={e => setMovArch(e.target.value as typeof movArch)}>
                    <option value="auto">Follow recommendation ({gdtRes.required.required ? 'MOV+GDT' : 'MOV-only'})</option>
                    <option value="mov">MOV-only</option><option value="movgdt">MOV + GDT</option>
                  </select>
                  <span style={{ marginLeft: 8, color: useGdt ? C.teal : C.muted, fontWeight: 600 }}>
                    → {useGdt ? 'MOV + GDT' : 'MOV-only'}</span>
                </label>

                {useGdt && (<>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(150px,1fr))', gap: 8, marginBottom: 10 }}>
                    <Chip k="CM surge V_LE" v={`${num(gdtRes.stress.v_le, 0)} V`} />
                    <Chip k="I_GDT required" v={`${num(gdtRes.stress.i_required, 0)} A`} />
                    <Chip k="Prefer class" v={`${num(gdtRes.stress.preferred_class_A, 0)} A`} />
                    <Chip k="No-fire need" v={`${num(gdtRes.stress.no_fire_need_V, 0)} V`} />
                  </div>
                  <div style={{ fontSize: 10.5, color: C.hint, textTransform: 'uppercase', marginBottom: 5 }}>
                    GDT candidate screen — common-mode (L/N-PE)
                  </div>
                  <div style={{ overflowX: 'auto', marginBottom: 8 }}>
                    <table style={{ borderCollapse: 'collapse', width: '100%' }}>
                      <thead><tr>{['Part', 'V_spark nom/min', 'I_8/20', 'Poles', 'No-fire', 'Surge', 'Dyn.spark', 'Verdict'].map(h =>
                        <th key={h} style={{ ...cell, color: C.hint, fontSize: 9, textAlign: 'left' }}>{h}</th>)}</tr></thead>
                      <tbody>{gdtRes.candidates.slice(0, 8).map((c, i) => (
                        <tr key={i}>
                          <td style={cell}>{c.part_number ?? c.label}</td>
                          <td style={cell}>{num(c.v_spark_nom, 0)}/{num(c.v_spark_min, 0)}</td>
                          <td style={cell}>{num(c.imax_impulse, 0)}</td>
                          <td style={cell}>{num(c.poles, 0)}</td>
                          <td style={cell}><Badge color={c.no_fire_ok ? 'green' : 'red'}>{c.no_fire_ok ? 'ok' : 'no'}</Badge></td>
                          <td style={cell}><Badge color={c.surge_ok ? 'green' : 'red'}>{c.surge_ok ? 'ok' : 'no'}</Badge></td>
                          <td style={{ ...cell, fontSize: 9, color: C.amber }}>{c.dynamic_status}</td>
                          <td style={cell}><Badge color={c.ok ? 'green' : 'red'}>{c.ok ? 'PASS' : 'FAIL'}</Badge></td>
                        </tr>))}</tbody>
                    </table>
                  </div>
                  <div style={{ fontSize: 10, color: C.text, marginBottom: 4 }}>
                    <Badge color={gdtRes.follow_current.ok ? 'green' : 'red'}>follow-current</Badge>{' '}
                    {gdtRes.follow_current.note}
                  </div>
                  <div style={{ fontSize: 10, color: C.text }}>
                    <Badge color={gdtRes.fail_short.ok ? 'green' : 'red'}>fail-short</Badge>{' '}
                    {gdtRes.fail_short.note}
                  </div>
                  <div style={{ fontSize: 9.5, color: C.muted, marginTop: 6 }}>
                    GDT screened against the vendor database (172 parts). Dynamic (impulse) sparkover is DATA
                    MISSING in the export — flagged, never assumed. Follow-current / fail-short require the
                    fault-current + fuse-I²t inputs to pass.
                  </div>
                </>)}
              </div>)}
            </>)}
          </div>
        )}

        {/* ─────────────── Fuse ─────────────── */}
        {tab === 'fuse' && (
          <div>
            <div style={{ background: C.tealL, border: `1px solid ${C.teal}55`, borderRadius: 8,
              padding: '8px 12px', marginBottom: 12, fontSize: 11.5, color: C.text }}>
              <b style={{ color: C.teal }}>Line fuse — six gates.</b> The upstream protective element for the
              whole input stage: <b>1</b> voltage rating ≥ high line · <b>2</b> continuous RMS current with
              margin and within the load factor after temperature de-rating · <b>3</b> melting I²t &gt; the
              NTC-limited startup I²t (this is what rides the inrush — the inrush <i>peak</i> does not set the
              current rating) · <b>4</b> breaking capacity ≥ available fault current · <b>5</b> fault
              coordination: clears a MOV/GDT fail-short or stuck bypass relay (Ch 9) · <b>6</b> thermal
              implementation: re-rated current at the real ambient + fuseholder rise. The selected fuse's I²t
              auto-feeds the NTC &amp; MOV/GDT coordination.
            </div>
            <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'flex-end', marginBottom: 8 }}>
              <Knob label="Current margin" unit="×I_rms" value={fuseOpts.fuse_current_margin} onChange={v => setF('fuse_current_margin', v)} />
              <Knob label="Load factor" unit="× rating" value={fuseOpts.fuse_load_factor} onChange={v => setF('fuse_load_factor', v)} />
              <Knob label="I²t margin" unit="×startup" value={fuseOpts.fuse_i2t_margin} onChange={v => setF('fuse_i2t_margin', v)} />
              <Knob label="Ambient derate" unit="×" value={fuseOpts.fuse_ambient_derate} onChange={v => setF('fuse_ambient_derate', v)} />
              <Btn variant="primary" disabled={fuseBusy} onClick={calcFuse}>{fuseBusy ? '⏳ Selecting…' : '↻ Re-select fuse'}</Btn>
            </div>
            <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'flex-end', marginBottom: 14 }}>
              <Knob label="Max ambient at fuse" unit="°C" value={fuseOpts.fuse_ambient_C} onChange={v => setF('fuse_ambient_C', v)} />
              <Knob label="Fuseholder/PCB rise" unit="°C" value={fuseOpts.fuseholder_rise_C} onChange={v => setF('fuseholder_rise_C', v)} />
              <Knob label="Re-rating slope" unit="%/°C" value={fuseOpts.fuse_derate_per_C} onChange={v => setF('fuse_derate_per_C', v)} />
              <Knob label="MOV/GDT fail-short" unit="A" value={fuseOpts.mov_fail_short_current_A} onChange={v => setF('mov_fail_short_current_A', v)} />
              <Knob label="Stuck-relay fault" unit="A" value={fuseOpts.relay_stuck_fault_current_A} onChange={v => setF('relay_stuck_fault_current_A', v)} />
              <span style={{ fontSize: 9.5, color: C.muted, maxWidth: 230 }}>
                Gates 5 &amp; 6. Blank = gate stays OPEN (never a silent pass). Fault current + startup basis
                shared with the NTC/MOV tabs.
              </span>
            </div>

            {fuseRes && (<>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(140px,1fr))', gap: 8, marginBottom: 12 }}>
                <Chip k="Worst I_rms" v={`${num(fuseRes.i_rms, 1)} A`} />
                <Chip k="I_rated req" v={`≥ ${num(fuseRes.requirements.i_rated_min, 1)} A`} />
                <Chip k="75%-rule / margin" v={`${num(fuseRes.requirements.i_load_min, 1)} / ${num(fuseRes.requirements.i_cont_min, 1)} A`} />
                <Chip k="Thermal de-rate k" v={fuseRes.requirements.thermal.known
                  ? `${num(fuseRes.requirements.k_thermal, 2)}×${fuseRes.requirements.thermal.estimated ? ' (est.)' : ''}` : 'OPEN'} />
                <Chip k="Startup I²t" v={fuseRes.startup_i2t != null ? `${num(fuseRes.startup_i2t, 1)} A²s` : '—'} />
                <Chip k="Melt I²t req" v={fuseRes.requirements.i2t_min != null ? `> ${num(fuseRes.requirements.i2t_min, 1)} A²s` : '—'} />
                <Chip k="Inrush peak (ridden by I²t)" v={fuseRes.inrush_peak_A != null ? `${num(fuseRes.inrush_peak_A, 1)} A` : '—'} />
                <Chip k="Fault coordination" v={fuseRes.requirements.coord.known
                  ? `≥ ${num(fuseRes.requirements.coord.i_A, 0)} A` : 'OPEN'} />
              </div>
              {fuseRes.selected ? (
                <div style={{ background: C.tealL, border: `1px solid ${C.teal}55`, borderRadius: 8,
                  padding: '9px 12px', marginBottom: 12, fontSize: 11.5, color: C.text }}>
                  <b style={{ color: C.teal }}>Selected:</b> {fuseRes.selected.mfr} {fuseRes.selected.part_number} —{' '}
                  {num(fuseRes.selected.i_rated_A, 0)} A / {num(fuseRes.selected.v_ac_V, 0)} Vac, breaking{' '}
                  {num(fuseRes.selected.breaking_ac_A, 0)} A, melting I²t <b>{num(fuseRes.selected.melting_i2t, 0)} A²s</b>
                  {fuseRes.selected.response_time ? ` (${fuseRes.selected.response_time})` : ''}.
                  {fuseRes.selected.i_usable_A != null
                    ? ` Usable ${num(fuseRes.selected.i_usable_A, 1)} A after de-rating — load is ${num(fuseRes.selected.load_pct_of_usable, 0)}% of it.` : ''}
                  {selFuseI2t ? ' → auto-feeds the NTC/MOV coordination.' : ''}
                </div>
              ) : (
                <div style={{ background: C.redL, border: `1px solid ${C.red}55`, borderRadius: 8,
                  padding: '9px 12px', marginBottom: 12, fontSize: 11.5, color: '#fca5a5' }}>
                  <b>No catalog fuse meets the requirement</b> — need I_rated ≥ {num(fuseRes.requirements.i_rated_min, 1)} A
                  (continuous margin {num(fuseRes.requirements.i_cont_min, 1)} A / load-factor rule {num(fuseRes.requirements.i_load_min, 1)} A
                  {fuseRes.requirements.thermal.known ? `, de-rated ×${num(fuseRes.requirements.k_thermal, 2)}` : ''})
                  at ≥ {num(fuseRes.requirements.v_min, 0)} Vac. The DB tops out at 50 A; use a higher-rated fuse, lower the
                  ambient/fuseholder rise, or relax the current margin.
                </div>
              )}

              {/* six-gate release check for the selected fuse */}
              <div style={{ fontSize: 10.5, color: C.hint, textTransform: 'uppercase', marginBottom: 5 }}>
                Six-gate release check{' '}
                <Badge color={vColor(fuseRes.gate_status)}>{fuseRes.gate_status}</Badge>
              </div>
              <div style={{ overflowX: 'auto', marginBottom: 14 }}>
                <table style={{ borderCollapse: 'collapse', width: '100%' }}>
                  <thead><tr>{['#', 'Gate', 'Requirement', 'Result', 'Status'].map(h =>
                    <th key={h} style={{ ...cell, color: C.hint, fontSize: 9, textAlign: 'left' }}>{h}</th>)}</tr></thead>
                  <tbody>{fuseRes.gates.map(g => (
                    <tr key={g.n}>
                      <td style={cell}>{g.n}</td>
                      <td style={cell}>{g.name}</td>
                      <td style={{ ...cell, fontSize: 9.5, color: C.muted }}>{g.requirement}</td>
                      <td style={{ ...cell, fontSize: 9.5 }}>{g.result}</td>
                      <td style={cell}><Badge color={vColor(g.status)}>{g.status}</Badge></td>
                    </tr>))}</tbody>
                </table>
              </div>

              <div style={{ fontSize: 10.5, color: C.hint, textTransform: 'uppercase', marginBottom: 5 }}>
                Candidate fuses — screened on all six gates · select one
              </div>
              <div style={{ overflowX: 'auto', marginBottom: 8 }}>
                <table style={{ borderCollapse: 'collapse', width: '100%' }}>
                  <thead><tr>{['', 'Part', 'I_rated', 'V_ac', 'Breaking', 'Melt I²t', 'Response',
                               '1', '2', '3', '4', '5', '6', 'Verdict'].map((h, hi) =>
                    <th key={hi} style={{ ...cell, color: C.hint, fontSize: 9, textAlign: 'left' }}>{h}</th>)}</tr></thead>
                  <tbody>{fuseRes.candidates.filter(c => c.verdict !== 'FAIL').slice(0, 12).map((c, i) => {
                    const isSel = fuseOpts.fuse_selected_part === c.part_number
                    const mk = (v: boolean | null) => v == null
                      ? <span style={{ color: C.muted }}>—</span>
                      : <span style={{ color: v ? C.teal : C.red }}>{v ? '✓' : '✗'}</span>
                    return (
                    <tr key={i} style={isSel ? { background: C.tealL } : undefined}>
                      <td style={cell}><Btn variant={isSel ? 'success' : 'ghost'} onClick={() => selectFuse(c.part_number ?? '')}>
                        {isSel ? '✓' : 'Select'}</Btn></td>
                      <td style={cell}>{c.part_number ?? c.label}</td>
                      <td style={cell}>{num(c.i_rated_A, 0)}A</td>
                      <td style={cell}>{num(c.v_ac_V, 0)}</td>
                      <td style={cell}>{c.breaking_ac_A != null ? `${num(c.breaking_ac_A, 0)}A` : '—'}</td>
                      <td style={cell}>{c.melting_i2t != null ? num(c.melting_i2t, 0) : 'MISSING'}</td>
                      <td style={cell}>{c.response_time ?? '—'}</td>
                      <td style={cell}>{mk(c.v_ok)}</td>
                      <td style={cell}>{mk(c.i_ok)}</td>
                      <td style={cell}>{mk(c.i2t_ok)}</td>
                      <td style={cell}>{mk(c.bc_ok)}</td>
                      <td style={cell}>{mk(c.coord_ok)}</td>
                      <td style={cell}>{mk(c.thermal_ok)}</td>
                      <td style={cell}><Badge color={vColor(c.verdict)}>{c.verdict}</Badge></td>
                    </tr>)})}</tbody>
                </table>
              </div>
              <div style={{ fontSize: 9.5, color: C.muted, marginTop: 6 }}>
                Gate columns 1–6 as above; <b>—</b> means that gate is OPEN (a datasheet field or a site input is
                missing), so the part stays <b>CONDITIONAL</b> and selectable rather than being silently passed or
                hidden. Fuses that violate a real limit are hidden.
                {fuseRes.fast_blow_only ? ' DB is fast-blow only; OK because the NTC limits inrush.' : ''}
              </div>
            </>)}
          </div>
        )}
      </Card>

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '4px 2px 24px' }}>
        <Btn variant="ghost" onClick={onBack}>← Back to semiconductors</Btn>
        <div style={{ display: 'flex', gap: 8 }}>
          <Btn variant="success" disabled={rptBusy} onClick={downloadReport}>
            {rptBusy ? '⏳ Generating…' : '📥 Download full report (incl. previous steps)'}
          </Btn>
          {onNext && <Btn variant="primary" onClick={() => onNext(ipReportPayload())}>Input filter →</Btn>}
          <Btn variant="ghost" onClick={onRestart}>Restart</Btn>
        </div>
      </div>
    </div>
  )
}
