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
 * target, IEC level/criterion, margins) are editable. Part selection runs against the
 * engines' built-in catalogs for now (the vendor NTC/MOV database attaches here later).
 */
import React, { useEffect, useMemo, useState } from 'react'
import { C, Btn, Card, SecHead, Badge } from './ui'
import { inputProtectionNtc, inputProtectionMov,
         type NtcResult, type MovResult, type CatalogRow } from '../api/client'
import type { CapacitorResult } from './Step15Capacitor'

interface Props {
  confirmedState:          Record<string, unknown>
  approvedInductorDesign:  Record<string, unknown>
  approvedCapacitorDesign?: CapacitorResult | null
  selectedMosfet?:         Record<string, unknown> | null
  onBack:    () => void
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
  confirmedState, approvedInductorDesign, approvedCapacitorDesign, selectedMosfet, onBack, onRestart,
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
    tau_multiple: '4', ambient_c: '45', r_line: '0', r_emi: '0', r_esr: '0', r_bridge: '0' })
  const [ntcRes, setNtcRes] = useState<NtcResult | null>(null)
  const [ntcBusy, setNtcBusy] = useState(false)
  const setN = (k: string, v: string) => setNtcOpts(s => ({ ...s, [k]: v }))
  const calcNtc = async () => {
    setNtcBusy(true); setErr(null)
    try { setNtcRes(await inputProtectionNtc({ design, cap, opts: ntcOpts })) }
    catch (e) { setErr((e as Error).message) } finally { setNtcBusy(false) }
  }

  // ── MOV ──
  const [movOpts, setMovOpts] = useState<Record<string, string>>({
    level: '3', criterion: 'A', vac_nom: '230', device_vds: String(mosfetVds), device_absmax: String(mosfetVds),
    imax_margin: '3', repetitive_derate: '0.70', varistor_alpha: '30', v1ma_ratio: '1.60' })
  const [movCM, setMovCM] = useState(true)
  const [movRes, setMovRes] = useState<MovResult | null>(null)
  const [movBusy, setMovBusy] = useState(false)
  const setM = (k: string, v: string) => setMovOpts(s => ({ ...s, [k]: v }))
  const calcMov = async () => {
    setMovBusy(true); setErr(null)
    try {
      const opts: Record<string, unknown> = { ...movOpts, common_mode_protection: movCM }
      setMovRes(await inputProtectionMov({ design, cap, mosfet: { vdss: Number(movOpts.device_vds) }, opts }))
    } catch (e) { setErr((e as Error).message) } finally { setMovBusy(false) }
  }

  useEffect(() => { calcNtc(); calcMov() }, [])  // eslint-disable-line react-hooks/exhaustive-deps

  const verdictColor = (v: string) => v === 'OK' ? 'green' : v === 'TIGHT' ? 'amber' : 'red'

  return (
    <div style={{ maxWidth: 1080, margin: '0 auto' }}>
      <Card>
        <SecHead icon="🛡️" label="Input Protection — MOV surge + NTC inrush"
          sub={`${design.vin_min}–${design.vin_max} Vac · bus ${num(design.vout, 0)} V`} />
        <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
          {([['ntc', '🌡️ NTC inrush limiter'], ['mov', '⚡ MOV surge (compliance)']] as [typeof tab, string][])
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
              <div style={{ fontSize: 10.5, color: C.hint, textTransform: 'uppercase', marginBottom: 5 }}>
                Catalog screen — R25 ≥ {num(ntcRes.result.r25_pick, 2)} Ω and pulse rating ≥ {num(ntcRes.result.e_pulse_required, 0)} J
              </div>
              <CatalogTable rows={ntcRes.catalog} emptyNote="No catalog parts loaded." />
              <div style={{ fontSize: 9.5, color: C.muted, marginTop: 6 }}>
                Built-in representative catalog — your vendor NTC database attaches here later. The NTC steady-state
                loss is folded into the efficiency cross-check; the sizing is documented step-by-step in its chapter.
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
              <Knob label="Device V_ds" unit="V" value={movOpts.device_vds} onChange={v => setM('device_vds', v)} />
              <Knob label="Device abs-max" unit="V" value={movOpts.device_absmax} onChange={v => setM('device_absmax', v)} />
              <Knob label="I_max margin" unit="×" value={movOpts.imax_margin} onChange={v => setM('imax_margin', v)} />
              <Btn variant="primary" disabled={movBusy} onClick={calcMov}>{movBusy ? '⏳ Sizing…' : '↻ Re-size MOV'}</Btn>
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
                Representative catalog (verify the Vc-vs-I curve and the 10-pulse repetitive derating on the live
                datasheet). Your vendor MOV database attaches here later. The MCOV is invariant to level/criterion.
              </div>
            </>)}
          </div>
        )}
      </Card>

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '4px 2px 24px' }}>
        <Btn variant="ghost" onClick={onBack}>← Back to semiconductors</Btn>
        <Btn variant="ghost" onClick={onRestart}>Restart</Btn>
      </div>
    </div>
  )
}
