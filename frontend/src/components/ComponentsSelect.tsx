/**
 * ComponentsSelect.tsx — Control Design Screen 2 (Chapter 6).
 *
 * Shows the components that are fixed / auto-calculated by the controller + the
 * upstream design (display-only), and lets the designer finalize the few
 * selectable items: R_CS over its valid band (satisfying HL & LL), the support
 * filter caps, and R_LS. Confirm advances to Screen 3.
 */
import React, { useEffect, useMemo, useState } from 'react'
import { C, Btn, Card, SecHead } from './ui'
import { controlComponents, type ControlComponents } from '../api/client'
import type { PlantParams } from './PowerPlantReview'

export interface ComponentSelections {
  rcs_mohm: number
  c_gc_pf: number; c_ls_pf: number; c_ss_pf: number; c_lpk_pf: number
  c_rlpk_pf: number; c_ilimit_pf: number; c_ilimit2_pf: number; r_ls_kohm: number
}

interface Props {
  params: PlantParams
  initial?: ComponentSelections | null
  onBack: () => void
  onConfirm: (sel: ComponentSelections) => void
}

const cell: React.CSSProperties = { padding: '5px 10px', fontSize: 12, borderBottom: `1px solid ${C.border}`,
  fontFamily: 'IBM Plex Mono,monospace', color: C.text }
const th: React.CSSProperties = { ...cell, color: C.hint, fontWeight: 600, textTransform: 'uppercase',
  letterSpacing: 0.4, fontSize: 10, fontFamily: 'inherit' }
const numInp: React.CSSProperties = { width: 110, background: C.bg3, border: `1px solid ${C.border2}`,
  borderRadius: 6, color: C.text, padding: '5px 8px', fontSize: 12, fontFamily: 'IBM Plex Mono,monospace' }

export const ComponentsSelect: React.FC<Props> = ({ params, initial, onBack, onConfirm }) => {
  const inputs = useMemo(() => ({
    vout: params.vout_V, fsw: params.fsw_kHz * 1000, lphi_uH: params.lphi_uH,
    cout_uF: params.co_uF, nch: params.nch, pout_lo: params.pout_lo_W, pout_hi: params.pout_hi_W,
    r_l: params.rl_mOhm / 1000, r_c: params.rc_mOhm / 1000,
  }), [params])

  const [data, setData] = useState<ControlComponents | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [sel, setSel] = useState<ComponentSelections | null>(initial ?? null)

  useEffect(() => {
    controlComponents(inputs).then(d => {
      setData(d)
      if (!sel) {
        const cap = (k: string) => d.selectable.find(s => s.key === k)?.default_pf ?? 0
        setSel({
          rcs_mohm: d.rcs.recommended_mohm,
          c_gc_pf: cap('c_gc'), c_ls_pf: cap('c_ls'), c_ss_pf: cap('c_ss'),
          c_lpk_pf: cap('c_lpk'), c_rlpk_pf: cap('c_rlpk'),
          c_ilimit_pf: cap('c_ilimit'), c_ilimit2_pf: cap('c_ilimit2'),
          r_ls_kohm: d.selectable.find(s => s.key === 'r_ls')?.default_kohm ?? 66.5,
        })
      }
    }).catch(e => setErr((e as Error).message))
  }, [inputs])  // eslint-disable-line react-hooks/exhaustive-deps

  const upd = (k: keyof ComponentSelections, v: number) => setSel(s => s ? { ...s, [k]: v } : s)
  const rcsValid = !!(data && sel && sel.rcs_mohm >= data.rcs.min_mohm && sel.rcs_mohm <= data.rcs.max_mohm)
  const capRows: [keyof ComponentSelections, string][] = [
    ['c_gc_pf', 'c_gc'], ['c_ls_pf', 'c_ls'], ['c_ss_pf', 'c_ss'], ['c_lpk_pf', 'c_lpk'],
    ['c_rlpk_pf', 'c_rlpk'], ['c_ilimit_pf', 'c_ilimit'], ['c_ilimit2_pf', 'c_ilimit2'],
  ]

  return (
    <div style={{ maxWidth: 980, margin: '0 auto', padding: '8px 4px 24px' }}>
      <SecHead icon="🧩" label="Control Design · Screen 2 of 7 — Controller-Fixed Components & Selections"
        sub="Review the auto-fixed parts, then finalize R_CS, the filter caps and R_LS" />
      {err && <div style={{ color: C.red, fontSize: 12, marginTop: 8 }}>⚠ {err}</div>}
      {!data && !err && <div style={{ color: C.muted, fontSize: 12, marginTop: 10 }}>Loading…</div>}

      {data && sel && <>
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
          <div style={{ fontSize: 12, color: C.muted, marginBottom: 8 }}>Current-sense resistor R_CS (designer)</div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap' }}>
            <label style={{ fontSize: 12, color: C.text }}>R_CS (mΩ):
              <input type="number" step={0.1} value={sel.rcs_mohm} style={{ ...numInp, marginLeft: 8 }}
                onChange={e => upd('rcs_mohm', Number(e.target.value))} />
            </label>
            <span style={{ fontSize: 11, color: C.hint, fontFamily: 'IBM Plex Mono,monospace' }}>
              valid {data.rcs.min_mohm}–{data.rcs.max_mohm} mΩ · recommended {data.rcs.recommended_mohm} mΩ
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
          <div style={{ fontSize: 12, color: C.muted, marginBottom: 8 }}>Filter capacitors &amp; R_LS (designer)</div>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ borderCollapse: 'collapse', width: '100%' }}>
              <thead><tr>{['Component', 'Symbol', 'Value (pF)', 'Role / pole'].map(h => <th key={h} style={th}>{h}</th>)}</tr></thead>
              <tbody>
                {capRows.map(([field, key]) => {
                  const meta = data.selectable.find(s => s.key === key)!
                  return (
                    <tr key={key}>
                      <td style={cell}>{meta.name}</td>
                      <td style={{ ...cell, color: C.teal }}>{meta.symbol}</td>
                      <td style={cell}>
                        <input type="number" value={sel[field]} style={numInp}
                          onChange={e => upd(field, Number(e.target.value))} />
                      </td>
                      <td style={{ ...cell, color: C.muted }}>{meta.role}</td>
                    </tr>
                  )
                })}
                <tr>
                  <td style={cell}>Current-predict resistor</td>
                  <td style={{ ...cell, color: C.teal }}>R_LS</td>
                  <td style={cell}>
                    <input type="number" step={0.1} value={sel.r_ls_kohm} style={numInp}
                      onChange={e => upd('r_ls_kohm', Number(e.target.value))} />
                    <span style={{ marginLeft: 6, color: C.hint }}>kΩ</span>
                  </td>
                  <td style={{ ...cell, color: C.muted }}>
                    {data.selectable.find(s => s.key === 'r_ls')?.role}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </Card>

        <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 18 }}>
          <Btn variant="ghost" onClick={onBack}>← Back</Btn>
          <Btn variant="primary" onClick={() => sel && onConfirm(sel)} disabled={!rcsValid}>
            Confirm &amp; Continue →
          </Btn>
        </div>
      </>}
    </div>
  )
}
