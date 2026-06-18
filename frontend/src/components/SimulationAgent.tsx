/**
 * SimulationAgent.tsx — Phase 2 post-Review page.
 *
 * Serves the self-contained WebGL field viewer (pfc_sim_agent_v14.html) as an iframe,
 * injecting the SAME package the backend engine used (`window.__MAG_FIELD_PACKAGE__`)
 * via a JSON data-island in <head> — so the viewer and the cross-check show identical
 * numbers (engine ↔ browser parity). Additive: a new sub-view reached from Review.
 */
import React, { useEffect, useMemo, useRef, useState } from 'react'
import rawHtml from '../assets/pfc_sim_agent_v14.html?raw'
import { C, Btn } from './ui'
import { simulateCrossCheck, getViewContract, type SimCrossCheck, type ViewContract } from '../api/client'

interface Props {
  result:         any
  confirmedState: any
  matType:        string
  selMaterial:    string
  selGrade:       string
  onBack:         () => void
}

export const SimulationAgent: React.FC<Props> = ({
  result, confirmedState, matType, selMaterial, selGrade, onBack,
}) => {
  const [loading, setLoading] = useState(true)
  const [error,   setError]   = useState<string | null>(null)
  const [sim,     setSim]     = useState<SimCrossCheck | null>(null)
  const [contract, setContract] = useState<ViewContract | null>(null)
  const iframeRef = useRef<HTMLIFrameElement | null>(null)
  const roRef = useRef<ResizeObserver | null>(null)
  // Post step7's contract into the viewer so its readouts render step7's values (Option B).
  const postContract = () => {
    const cw = iframeRef.current?.contentWindow
    if (cw && contract) cw.postMessage({ __step7_contract: contract }, '*')
  }
  useEffect(() => { postContract() }, [contract])  // eslint-disable-line react-hooks/exhaustive-deps

  // ── Auto-size the iframe to its content (single browser scrollbar) ──────────
  const fitHeight = () => {
    const f = iframeRef.current
    const doc = f?.contentDocument
    if (!f || !doc) return
    const h = Math.max(doc.documentElement?.scrollHeight ?? 0, doc.body?.scrollHeight ?? 0)
    if (h > 0) f.style.height = h + 'px'
  }
  const handleLoad = () => {
    postContract()
    fitHeight()
    const doc = iframeRef.current?.contentDocument
    roRef.current?.disconnect()
    const target = doc?.body ?? doc?.documentElement
    if (target && 'ResizeObserver' in window) {
      const ro = new ResizeObserver(() => fitHeight())
      ro.observe(target)
      roRef.current = ro
    }
  }
  useEffect(() => () => roRef.current?.disconnect(), [])

  // Fetch the package (for the viewer) AND step7's authoritative view-contract (for the
  // headline scalars) once when this page mounts.
  useEffect(() => {
    let alive = true
    setLoading(true); setError(null)
    const design = { ...result,
      material_key: result?.material_key || (matType === 'powder' ? selMaterial : selGrade) }
    const st = confirmedState as Record<string, unknown>
    Promise.allSettled([
      simulateCrossCheck(st, design, 'litz'),
      getViewContract(st, design),
    ]).then(([simRes, vcRes]) => {
      if (!alive) return
      if (simRes.status === 'fulfilled') {
        setSim(simRes.value)
        if (simRes.value.ok === false) setError((simRes.value.errors ?? ['invalid package']).join('; '))
      } else {
        setError((simRes.reason as Error)?.message ?? String(simRes.reason))
      }
      if (vcRes.status === 'fulfilled') setContract(vcRes.value.contract)
    }).finally(() => { if (alive) setLoading(false) })
    return () => { alive = false }
  }, [])  // eslint-disable-line react-hooks/exhaustive-deps

  // Inject the package as a JSON data-island in <head> so the viewer boots with it.
  const iframeHtml = useMemo(() => {
    const pkg = sim?.package
    if (!pkg) return ''
    const island =
      '<script type="application/json" id="__simpkg">' +
      JSON.stringify(pkg).replace(/</g, '\\u003c') +
      '<\/script>'
    const setter =
      '<script>try{window.__MAG_FIELD_PACKAGE__=' +
      'JSON.parse(document.getElementById("__simpkg").textContent);}' +
      'catch(e){console.error("sim package parse failed",e);}<\/script>'
    return rawHtml
      // flow to natural height (no internal 100vh lock) so the iframe auto-sizes
      .replace('min-height:100vh', 'min-height:0')
      .replace('</head>', island + setter + '</head>')
  }, [sim])

  // Authoritative design verdict comes from step7 (result.passed), not the shadow engine's scan.
  const verdict = contract?.acceptance?.verdict ?? (sim?.verdict === 'APPROVE' ? 'APPROVE' : undefined)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 8, flexWrap: 'wrap' }}>
        <span style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: '.06em',
          color: C.accent, fontWeight: 700 }}>Simulation Agent — field viewer</span>
        {verdict && (
          <span style={{ fontFamily: 'IBM Plex Mono,monospace', fontWeight: 700,
            color: verdict === 'APPROVE' ? C.green : C.amber }}>{verdict}</span>
        )}
        <span style={{ marginLeft: 'auto', color: C.hint, fontSize: 10,
          fontFamily: 'IBM Plex Mono,monospace' }}>
          design verdict
        </span>
      </div>

      {/* step7 authoritative scalars — IDENTICAL to Result & Review (single source of truth) */}
      {contract?.scalars && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, marginBottom: 8,
          padding: '8px 10px', borderRadius: 8, border: `1px solid ${C.border}`,
          background: 'rgba(56,189,248,.05)', fontSize: 11, fontFamily: 'IBM Plex Mono,monospace' }}>
          <span style={{ color: C.accent, fontWeight: 700, fontSize: 10, textTransform: 'uppercase',
            letterSpacing: '.06em', alignSelf: 'center' }}>Design values</span>
          {([
            ['L0', contract.scalars.L0_nom_uH, 'µH', 1],
            ['Lfull', contract.scalars.L_full_load_uH, 'µH', 1],
            ['Bmax', contract.scalars.Bmax_FL_T, 'T', 3],
            ['DCR@100', contract.scalars.DCR_100C_mOhm, 'mΩ', 1],
            ['Pcore', contract.scalars.Pcore_W, 'W', 2],
            ['Ptot', contract.scalars.Ptotal_100C_W, 'W', 2],
            ['ΔT', contract.scalars.dT_rise_C, '°C', 1],
            ['J', contract.scalars.J_A_mm2, 'A/mm²', 2],
          ] as Array<[string, number | string | null, string, number]>).map(([lbl, v, u, d]) => (
            <span key={lbl} style={{ color: C.muted }}>
              {lbl} <b style={{ color: C.text }}>{typeof v === 'number' ? v.toFixed(d) : '—'}</b> {u}
            </span>
          ))}
        </div>
      )}

      {loading && (
        <div style={{ padding: 40, textAlign: 'center', color: C.muted }}>⏳ Building simulation package…</div>
      )}
      {error && (
        <div style={{ fontSize: 12, color: '#c0392b', background: '#fdf2f2',
          border: '1px solid #e8b4b8', borderRadius: 8, padding: '10px 12px' }}>
          ⚠ Could not build the simulation package: {error}
        </div>
      )}

      {iframeHtml && (
        <iframe
          ref={iframeRef}
          onLoad={handleLoad}
          srcDoc={iframeHtml}
          title="Simulation Agent — field viewer"
          scrolling="no"
          style={{
            width: '100%', minHeight: 640,
            border: 'none', borderRadius: 10, background: '#0b1020', display: 'block',
          }}
          sandbox="allow-scripts allow-same-origin"
        />
      )}

      {/* action bar */}
      <div style={{ display: 'flex', gap: 8, paddingTop: 10, marginTop: 6,
        borderTop: `0.5px solid ${C.border}` }}>
        <Btn variant="ghost" onClick={onBack}>← Back to Review</Btn>
        {sim?.validation?.warnings && sim.validation.warnings.length > 0 && (
          <span style={{ fontSize: 10, color: C.amber, alignSelf: 'center' }}>
            {sim.validation.warnings.length} validation warning(s) — see console
          </span>
        )}
      </div>
    </div>
  )
}
