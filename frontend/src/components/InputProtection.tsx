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
import { inputProtectionNtc, inputProtectionMov, inputProtectionGdt, docGenerateReport, inrushSchematicUrl,
         type NtcResult, type MovResult, type GdtResult, type CatalogRow, type NtcCandidate } from '../api/client'
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

  const [tab, setTab] = useState<'ntc' | 'mov'>('ntc')
  const [err, setErr] = useState<string | null>(null)

  // ── NTC ──
  const [ntcOpts, setNtcOpts] = useState<Record<string, string>>({
    i_inrush_target: '60', energy_margin: '1.5', r25_margin: '1.10', vref_pulse: '345',
    tau_multiple: '4', ambient_c: '45', r_line: '0', r_emi: '0', r_esr: '0', r_bridge: '0',
    // worst-case / coordination inputs (datasheet / layout; blank = open item in the report)
    fuse_i2t_rating: '', relay_make_rating_a: '', relay_path_ohm: '', off_time_min_ms: '',
    restart_protection: '' })
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
  const calcMov = async () => {
    setMovBusy(true); setErr(null)
    try {
      const opts = movOptsPayload()
      const [m, g] = await Promise.all([
        inputProtectionMov({ design, cap, mosfet: { vdss: Number(movOpts.device_vds) }, opts }),
        inputProtectionGdt({ design, opts }),
      ])
      setMovRes(m); setGdtRes(g)
    } catch (e) { setErr((e as Error).message) } finally { setMovBusy(false) }
  }
  // Effective architecture = recommendation unless the designer overrode it.
  const useGdt = movArch === 'movgdt' || (movArch === 'auto' && !!gdtRes?.required.required)

  useEffect(() => { calcNtc(); calcMov() }, [])  // eslint-disable-line react-hooks/exhaustive-deps

  const [rptBusy, setRptBusy] = useState(false)
  // FULL report: all previous chapters (design basis, magnetics, DC-bus capacitor) + the
  // input-protection chapters — not only Ch 8–9.
  // The input-protection payload for the report (Ch 8 NTC + Ch 9 MOV). Shared by this page's own
  // report button AND handed up via onNext so the EMI page can include Ch 8/9 in its combined report.
  const ipReportPayload = (): Record<string, unknown> => ({
    design, cap, mosfet: { vdss: Number(movOpts.device_vds) },
    ntc_opts: ntcOpts,
    mov_opts: { ...movOptsPayload(), surge_architecture: useGdt ? 'MOV+GDT' : 'MOV-only' },
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
          {([['ntc', '🌡️ NTC inrush limiter'], ['mov', '⚡ Surge (MOV + GDT)']] as [typeof tab, string][])
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
                Catalog screen — R25 ≥ {num(ntcRes.result.r25_pick, 2)} Ω and pulse rating ≥ {num(ntcRes.result.e_pulse_required, 0)} J
                — click Select to base the design on a part
              </div>
              {(ntcRes.candidates?.length ?? 0) > 0 ? (
                <div style={{ overflowX: 'auto' }}>
                  <table style={{ borderCollapse: 'collapse', width: '100%' }}>
                    <thead><tr>{['', '', 'Mfr / Part', 'R25 (Ω)', 'Ø (mm)', 'I_max (A)', 'E est. (J)', 'Notes'].map((h, i) =>
                      <th key={i} style={{ ...cell, color: C.hint, textTransform: 'uppercase', fontSize: 9, textAlign: 'left' }}>{h}</th>)}</tr></thead>
                    <tbody>{(ntcRes.candidates as NtcCandidate[]).map((c, i) => {
                      const isSel = ntcRes.selected?.part_number === c.part_number
                      return (
                        <tr key={i} style={isSel ? { background: 'rgba(45,212,191,.08)' } : undefined}>
                          <td style={cell}>{c.ok ? <Badge color="green">PASS</Badge> : <Badge color="red">FAIL</Badge>}</td>
                          <td style={cell}>
                            <Btn variant={isSel ? 'success' : 'ghost'} onClick={() => selectNtc(c.part_number ?? '')}>
                              {isSel ? '✓ Selected' : 'Select'}
                            </Btn>
                          </td>
                          <td style={{ ...cell, whiteSpace: 'normal', fontWeight: 600, color: c.ok ? C.text : C.muted }}>
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
                    })}</tbody>
                  </table>
                </div>
              ) : (
                <CatalogTable rows={ntcRes.catalog} emptyNote="No catalog parts loaded." />
              )}
              <div style={{ fontSize: 9.5, color: C.muted, marginTop: 6 }}>
                Screened against the vendor ICL database (ICL_Database.xlsx). R25 is the real datasheet value;
                pulse energy is estimated from the disc diameter — confirm energy / max-C on the datasheet before
                ordering. Selecting a part recalculates the inrush/precharge numbers around its actual R25 and
                documents the selection in the report (§8.7).
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
              <div style={{ fontSize: 10.5, color: C.hint, textTransform: 'uppercase', marginBottom: 5 }}>
                Candidate screen — governing path {movRes.stress.governing?.split('(')[0] ?? ''} (criterion {movRes.criterion.name})
              </div>
              <CatalogTable rows={movRes.catalog} emptyNote="No catalog parts loaded." />
              <div style={{ fontSize: 9.5, color: C.muted, marginTop: 6 }}>
                Screened against the vendor MOV database (1140 parts). Clamp reads DATA MISSING where the
                datasheet max-clamping voltage (Vc@In) is absent — never a silent pass. MCOV is invariant to level/criterion.
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
