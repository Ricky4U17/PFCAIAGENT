/**
 * CoreReview.tsx — Control Design Screen 3 (Chapter 6).
 *
 * Review-only: the consolidated Core Component Table (everything fixed/selected
 * through Screens 1–2, with each part's function) and the Fixed Coefficients /
 * Internal Parameters (FAN9672 constants & design targets). Confirm advances to
 * Screen 4 (compensator design).
 */
import React, { useEffect, useMemo, useState } from 'react'
import { C, Btn, Card, SecHead } from './ui'
import { controlComponents, controlCoefficients, type ControlComponents } from '../api/client'
import type { PlantParams } from './PowerPlantReview'
import type { ComponentSelections } from './ComponentsSelect'

interface Props {
  params: PlantParams
  s2sel: ComponentSelections | null
  onBack: () => void
  onConfirm: () => void
}

const cell: React.CSSProperties = { padding: '5px 10px', fontSize: 12, borderBottom: `1px solid ${C.border}`,
  fontFamily: 'IBM Plex Mono,monospace', color: C.text }
const th: React.CSSProperties = { ...cell, color: C.hint, fontWeight: 600, textTransform: 'uppercase',
  letterSpacing: 0.4, fontSize: 10, fontFamily: 'inherit' }

const fmtCap = (pf: number) => pf >= 1e6 ? `${(pf / 1e6).toFixed(2)} µF`
  : pf >= 1000 ? `${(pf / 1000).toFixed(pf % 1000 ? 1 : 0)} nF` : `${pf} pF`

export const CoreReview: React.FC<Props> = ({ params, s2sel, onBack, onConfirm }) => {
  const inputs = useMemo(() => ({
    vout: params.vout_V, fsw: params.fsw_kHz * 1000, lphi_uH: params.lphi_uH,
    cout_uF: params.co_uF, nch: params.nch, pout_lo: params.pout_lo_W, pout_hi: params.pout_hi_W,
    r_l: params.rl_mOhm / 1000, r_c: params.rc_mOhm / 1000,
    ...(s2sel ? { rcs: s2sel.rcs_mohm / 1000 } : {}),
  }), [params, s2sel])

  const [comp, setComp] = useState<ControlComponents | null>(null)
  const [coef, setCoef] = useState<string[][] | null>(null)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    Promise.all([controlComponents(inputs), controlCoefficients(inputs)])
      .then(([c, k]) => { setComp(c); setCoef(k.coefficients) })
      .catch(e => setErr((e as Error).message))
  }, [inputs])

  // selected rows (designer choices from Screen 2) with role text from metadata
  const role = (key: string) => comp?.selectable.find(s => s.key === key)?.role ?? ''
  const sym = (key: string) => comp?.selectable.find(s => s.key === key)?.symbol ?? key
  const selRows: { name: string; symbol: string; value: string; role: string }[] = s2sel ? [
    { name: 'Current-sense resistor', symbol: 'R_CS', value: `${s2sel.rcs_mohm} mΩ`, role: 'designer-selected' },
    { name: 'Gain-control filter cap', symbol: sym('c_gc'), value: fmtCap(s2sel.c_gc_pf), role: role('c_gc') },
    { name: 'RLPK filter cap', symbol: sym('c_rlpk'), value: fmtCap(s2sel.c_rlpk_pf), role: role('c_rlpk') },
    { name: 'ILIMIT filter cap', symbol: sym('c_ilimit'), value: fmtCap(s2sel.c_ilimit_pf), role: role('c_ilimit') },
    { name: 'ILIMIT2 filter cap', symbol: sym('c_ilimit2'), value: fmtCap(s2sel.c_ilimit2_pf), role: role('c_ilimit2') },
    { name: 'VIR filter cap', symbol: sym('c_vir'), value: fmtCap(s2sel.c_vir_pf), role: role('c_vir') },
    { name: 'Current-predict filter cap', symbol: sym('c_ls'), value: fmtCap(s2sel.c_ls_pf), role: role('c_ls') },
    { name: 'Current-predict resistor', symbol: 'R_LS', value: `${s2sel.r_ls_kohm} kΩ`, role: 'designer-selected' },
  ] : []

  const tableA = comp ? [...comp.fixed, ...selRows] : []

  return (
    <div style={{ maxWidth: 980, margin: '0 auto', padding: '8px 4px 24px' }}>
      <SecHead icon="📑" label="Control Design · Screen 3 of 7 — Core Components & Fixed Coefficients"
        sub="Review the consolidated component table and the controller internal parameters, then continue" />
      {err && <div style={{ color: C.red, fontSize: 12, marginTop: 8 }}>⚠ {err}</div>}
      {!comp && !err && <div style={{ color: C.muted, fontSize: 12, marginTop: 10 }}>Loading…</div>}

      {comp && coef && <>
        <Card style={{ marginTop: 12 }}>
          <div style={{ fontSize: 12, color: C.muted, marginBottom: 8 }}>Core Component Table — calculated &amp; selected, with function</div>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ borderCollapse: 'collapse', width: '100%' }}>
              <thead><tr>{['Component', 'Symbol', 'Value', 'Function'].map(h => <th key={h} style={th}>{h}</th>)}</tr></thead>
              <tbody>
                {tableA.map((r, i) => (
                  <tr key={i}>
                    <td style={cell}>{r.name}</td>
                    <td style={{ ...cell, color: C.teal }}>{r.symbol}</td>
                    <td style={cell}>{r.value}</td>
                    <td style={{ ...cell, color: C.muted }}>{r.role}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>

        <Card style={{ marginTop: 12 }}>
          <div style={{ fontSize: 12, color: C.muted, marginBottom: 8 }}>Fixed Coefficients / Internal Parameters</div>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ borderCollapse: 'collapse', width: '100%' }}>
              <thead><tr>{['Parameter', 'Symbol', 'Value', 'Source / constraint'].map(h => <th key={h} style={th}>{h}</th>)}</tr></thead>
              <tbody>
                {coef.map((r, i) => (
                  <tr key={i}>
                    <td style={cell}>{r[0]}</td>
                    <td style={{ ...cell, color: C.teal }}>{r[1]}</td>
                    <td style={cell}>{r[2]}</td>
                    <td style={{ ...cell, color: C.muted }}>{r[3]}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>

        <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 18 }}>
          <Btn variant="ghost" onClick={onBack}>← Back</Btn>
          <Btn variant="primary" onClick={onConfirm}>Confirm &amp; Continue →</Btn>
        </div>
      </>}
    </div>
  )
}
