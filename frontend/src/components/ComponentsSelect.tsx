/**
 * ComponentsSelect.tsx — Control Design Screen 2 (Chapter 6).
 *
 * Shows the controller-fixed / auto-calculated components (display-only) and lets
 * the designer finalize the selectable items from standard-value dropdowns:
 * R_CS (standard values inside its HL&LL-valid band), the support filter caps
 * (each a dropdown of standard E6 values, with a live pole frequency), and R_LS.
 */
import React, { useEffect, useMemo, useState } from 'react'
import { C, Btn, Card, SecHead } from './ui'
import { controlComponents, type ControlComponents } from '../api/client'
import type { PlantParams } from './PowerPlantReview'

export interface ComponentSelections {
  rcs_mohm: number
  c_gc_pf: number; c_rlpk_pf: number; c_ilimit_pf: number
  c_ilimit2_pf: number; c_vir_pf: number; c_ls_pf: number
  r_ls_kohm: number
}

const cell: React.CSSProperties = { padding: '5px 10px', fontSize: 12, borderBottom: `1px solid ${C.border}`,
  fontFamily: 'IBM Plex Mono,monospace', color: C.text }
const th: React.CSSProperties = { ...cell, color: C.hint, fontWeight: 600, textTransform: 'uppercase',
  letterSpacing: 0.4, fontSize: 10, fontFamily: 'inherit' }
const sel: React.CSSProperties = { background: C.bg3, border: `1px solid ${C.border2}`, borderRadius: 6,
  color: C.text, padding: '5px 8px', fontSize: 12, fontFamily: 'IBM Plex Mono,monospace' }

const capLabel = (pf: number) => pf >= 1e6 ? `${pf / 1e6} µF` : pf >= 1000 ? `${pf / 1000} nF` : `${pf} pF`
const fmtHz = (hz: number) => hz >= 1e6 ? `${(hz / 1e6).toFixed(2)} MHz`
  : hz >= 1e3 ? `${(hz / 1e3).toFixed(2)} kHz` : `${hz.toFixed(1)} Hz`
const poleHz = (rOhm: number, cPf: number) => 1 / (2 * Math.PI * rOhm * cPf * 1e-12)

// field <-> backend key for the six selectable caps
const CAP_FIELDS: [keyof ComponentSelections, string][] = [
  ['c_gc_pf', 'c_gc'], ['c_rlpk_pf', 'c_rlpk'], ['c_ilimit_pf', 'c_ilimit'],
  ['c_ilimit2_pf', 'c_ilimit2'], ['c_vir_pf', 'c_vir'], ['c_ls_pf', 'c_ls'],
]

interface Props {
  params: PlantParams
  initial?: ComponentSelections | null
  onBack: () => void
  onConfirm: (sel: ComponentSelections) => void
}

export const ComponentsSelect: React.FC<Props> = ({ params, initial, onBack, onConfirm }) => {
  const inputs = useMemo(() => ({
    vout: params.vout_V, fsw: params.fsw_kHz * 1000, lphi_uH: params.lphi_uH,
    cout_uF: params.co_uF, nch: params.nch, pout_lo: params.pout_lo_W, pout_hi: params.pout_hi_W,
    r_l: params.rl_mOhm / 1000, r_c: params.rc_mOhm / 1000,
  }), [params])

  const [data, setData] = useState<ControlComponents | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [s, setS] = useState<ComponentSelections | null>(initial ?? null)

  useEffect(() => {
    controlComponents(inputs).then(d => {
      setData(d)
      if (!s) {
        const cap = (k: string) => d.selectable.find(x => x.key === k)?.default_pf ?? 0
        setS({
          rcs_mohm: d.rcs.recommended_mohm,
          c_gc_pf: cap('c_gc'), c_rlpk_pf: cap('c_rlpk'), c_ilimit_pf: cap('c_ilimit'),
          c_ilimit2_pf: cap('c_ilimit2'), c_vir_pf: cap('c_vir'), c_ls_pf: cap('c_ls'),
          r_ls_kohm: d.r_ls.default_kohm,
        })
      }
    }).catch(e => setErr((e as Error).message))
  }, [inputs])  // eslint-disable-line react-hooks/exhaustive-deps

  const upd = (k: keyof ComponentSelections, v: number) => setS(x => x ? { ...x, [k]: v } : x)
  const rcsValid = !!(data && s && s.rcs_mohm >= data.rcs.min_mohm && s.rcs_mohm <= data.rcs.max_mohm)

  // R_LS = Lφ/(1.5e-9·R_CS·ratio) ⇒ R_LS ∝ 1/R_CS. calc_kohm is computed at the
  // recommended R_CS, so rescale it live for any selected R_CS, then snap to standard.
  const rlsCalcK = (rcsMohm: number) =>
    data ? data.r_ls.calc_kohm * (data.rcs.recommended_mohm / rcsMohm) : 0
  const nearestK = (k: number) =>
    data ? data.r_ls.options_kohm.reduce((a, b) => Math.abs(b - k) < Math.abs(a - k) ? b : a,
      data.r_ls.options_kohm[0]) : k
  // selecting a different R_CS retracks R_LS to the rescaled standard value
  const onRcs = (v: number) => setS(x => x ? { ...x, rcs_mohm: v, r_ls_kohm: nearestK(rlsCalcK(v)) } : x)

  return (
    <div style={{ maxWidth: 980, margin: '0 auto', padding: '8px 4px 24px' }}>
      <SecHead icon="🧩" label="Control Design · Screen 2 of 7 — Controller-Fixed Components & Selections"
        sub="Review the auto-fixed parts, then finalize R_CS, the filter caps and R_LS from standard values" />
      {err && <div style={{ color: C.red, fontSize: 12, marginTop: 8 }}>⚠ {err}</div>}
      {!data && !err && <div style={{ color: C.muted, fontSize: 12, marginTop: 10 }}>Loading…</div>}

      {data && s && <>
        <Card style={{ marginTop: 12 }}>
          <div style={{ fontSize: 12, color: C.muted, marginBottom: 8 }}>
            Fixed / auto-calculated by the controller &amp; upstream design (no edit)
          </div>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ borderCollapse: 'collapse', width: '100%' }}>
              <thead><tr>{['Component', 'Symbol', 'Value', 'Role'].map(h => <th key={h} style={th}>{h}</th>)}</tr></thead>
              <tbody>
                {data.fixed.map((f, i) => (
                  <tr key={i}>
                    <td style={cell}>{f.name}</td>
                    <td style={{ ...cell, color: C.teal }}>{f.symbol}</td>
                    <td style={cell}>{f.value}</td>
                    <td style={{ ...cell, color: C.muted }}>{f.role}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>

        <Card style={{ marginTop: 12 }}>
          <div style={{ fontSize: 12, color: C.muted, marginBottom: 8 }}>Current-sense resistor R_CS (standard values, designer)</div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap' }}>
            <label style={{ fontSize: 12, color: C.text }}>R_CS:
              <select value={s.rcs_mohm} style={{ ...sel, marginLeft: 8 }}
                onChange={e => onRcs(Number(e.target.value))}>
                {data.rcs.options_mohm.map(v => (
                  <option key={v} value={v}>{v} mΩ{v === data.rcs.recommended_mohm ? ' (recommended)' : ''}</option>
                ))}
              </select>
            </label>
            <span style={{ fontSize: 11, color: C.hint, fontFamily: 'IBM Plex Mono,monospace' }}>
              valid band {data.rcs.min_mohm}–{data.rcs.max_mohm} mΩ
            </span>
            <span style={{ fontSize: 11, fontWeight: 600, color: rcsValid ? C.green : C.red }}>
              {rcsValid ? '✓ valid for HL & LL' : '✗ outside valid band'}
            </span>
          </div>
          <div style={{ fontSize: 10.5, color: C.muted, marginTop: 6 }}>
            Method-1 (AN4165): LL {data.rcs.m1_ll_mohm} mΩ / HL {data.rcs.m1_hl_mohm} mΩ. {data.rcs.note}
          </div>
        </Card>

        <Card style={{ marginTop: 12 }}>
          <div style={{ fontSize: 12, color: C.muted, marginBottom: 8 }}>Filter capacitors &amp; R_LS — pick standard values; pole updates live</div>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ borderCollapse: 'collapse', width: '100%' }}>
              <thead><tr>{['Component', 'Symbol', 'Value', 'Pole / note'].map(h => <th key={h} style={th}>{h}</th>)}</tr></thead>
              <tbody>
                {CAP_FIELDS.map(([field, key]) => {
                  const meta = data.selectable.find(x => x.key === key)!
                  const cur = s[field]
                  // C_LS sits across R_LS, so its pole tracks the selected R_LS
                  const rOhm = key === 'c_ls' ? s.r_ls_kohm * 1000 : meta.r_assoc_ohm
                  return (
                    <tr key={key}>
                      <td style={cell}>{meta.name}</td>
                      <td style={{ ...cell, color: C.teal }}>{meta.symbol}</td>
                      <td style={cell}>
                        <select value={cur} style={sel} onChange={e => upd(field, Number(e.target.value))}>
                          {meta.options_pf.map(pf => <option key={pf} value={pf}>{capLabel(pf)}</option>)}
                        </select>
                      </td>
                      <td style={{ ...cell, color: C.muted }}>
                        pole {fmtHz(poleHz(rOhm, cur))} ({meta.role})
                      </td>
                    </tr>
                  )
                })}
                <tr>
                  <td style={cell}>Current-predict resistor</td>
                  <td style={{ ...cell, color: C.teal }}>R_LS</td>
                  <td style={cell}>
                    <select value={s.r_ls_kohm} style={sel} onChange={e => upd('r_ls_kohm', Number(e.target.value))}>
                      {data.r_ls.options_kohm.map(v => <option key={v} value={v}>{v} kΩ</option>)}
                    </select>
                  </td>
                  <td style={{ ...cell, color: C.muted }}>calc {rlsCalcK(s.rcs_mohm).toFixed(1)} kΩ (tracks R_CS) · {data.r_ls.role}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </Card>

        <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 18 }}>
          <Btn variant="ghost" onClick={onBack}>← Back</Btn>
          <Btn variant="primary" onClick={() => s && onConfirm(s)} disabled={!rcsValid}>
            Confirm &amp; Continue →
          </Btn>
        </div>
      </>}
    </div>
  )
}
