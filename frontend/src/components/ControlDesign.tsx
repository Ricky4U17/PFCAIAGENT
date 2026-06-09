/**
 * ControlDesign.tsx — Step 16: PFC Control Loop Design Tool
 *
 * Loads the FAN9672 Control Design Tool from /control_design.html (served
 * as a static public asset — avoids the srcdoc encoding/sandbox issues).
 *
 * Python plant parameters are injected via postMessage once the iframe loads:
 *   { type: 'setPythonValues', params: { lphi_uH, rl_mOhm, co_uF, ... } }
 *
 * Sandbox: allow-scripts allow-downloads allow-forms allow-modals
 *   (no allow-same-origin — prevents sandbox escape security warning)
 *
 * The iframe receives the message through the listener added at the end of
 * control_design.html, which calls window.setPythonValues(params).
 */
import React, { useRef, useCallback, useState } from 'react'
import { C, Btn } from './ui'
import type { CapacitorResult } from './Step15Capacitor'
import { docGenerateReport } from '../api/client'

interface Props {
  confirmedState:          Record<string, unknown>
  approvedInductorDesign:  Record<string, unknown>
  approvedCapacitorDesign: CapacitorResult | null
  onBack:    () => void
  onRestart: () => void
}

export const ControlDesign: React.FC<Props> = ({
  confirmedState, approvedInductorDesign, approvedCapacitorDesign,
  onBack, onRestart,
}) => {
  const iframeRef              = useRef<HTMLIFrameElement>(null)
  const [rptLoading, setRptLoad] = useState(false)
  const [rptError,   setRptError] = useState<string|null>(null)
  const injectedRef = useRef(false)

  // ── Build Python plant parameters ─────────────────────────────────────────
  const tsi  = (confirmedState as any)?.topology_specific_inputs ?? {}
  const app  = (confirmedState as any)?.intake?.application ?? {}

  const params = {
    lphi_uH:   Number((approvedInductorDesign as any)?.L_target_uH   ?? 235),
    rl_mOhm:   Number((approvedInductorDesign as any)?.DCR_100C_mOhm ?? 28),
    co_uF:     approvedCapacitorDesign?.C_total_uF         ?? 2350,
    rc_mOhm:   approvedCapacitorDesign?.ESR_parallel_mohm  ?? 5,
    vout_V:    Number(app.output_bus_voltage_v              ?? 394),
    fsw_kHz:   Number(tsi.recommended_frequency_hz         ?? 70000) / 1000,
    pout_lo_W: Number(app.output_power_w_low_line           ?? 1700),
    pout_hi_W: Number(app.output_power_w_high_line          ?? 3600),
    eta_lo:    0.945,
    eta_hi:    0.965,
    nch:       Number((confirmedState as any)?.selected_channels ?? 2),
  }

  // ── Inject via postMessage once iframe loads and setPythonValues is ready ──
  const sendValues = useCallback(() => {
    if (!iframeRef.current?.contentWindow) return
    iframeRef.current.contentWindow.postMessage(
      { type: 'setPythonValues', params },
      '*'
    )
  }, [params])  // eslint-disable-line react-hooks/exhaustive-deps

  const handleLoad = useCallback(() => {
    injectedRef.current = false
    // Give the JS tool 2 s to initialise before posting values.
    // The postMessage listener in the HTML calls setPythonValues when received.
    const tryInject = (attempt: number) => {
      setTimeout(() => {
        sendValues()
        // Retry once more after another second in case the first arrived early
        if (attempt < 2) tryInject(attempt + 1)
      }, attempt === 0 ? 2000 : 1500)
    }
    tryInject(0)
  }, [sendValues])

  // ── Step16 params for Python report ───────────────────────────────────────
  const step16_params = {
    L_uH:       params.lphi_uH,
    DCR_mOhm:   params.rl_mOhm,
    C_uF:       params.co_uF,
    ESR_mOhm:   params.rc_mOhm,
    Vout_V:     params.vout_V,
    fsw_Hz:     params.fsw_kHz * 1000,
    Pout_lo_W:  params.pout_lo_W,
    Pout_hi_W:  params.pout_hi_W,
    eta_lo:     params.eta_lo,
    eta_hi:     params.eta_hi,
    nch:        params.nch,
  }

  // Ask the iframe for its current computed design state (component values, type).
  // Times out after 2 s and returns null — Python falls back to its own calculation.
  const getJsDesignState = (): Promise<Record<string, unknown> | null> =>
    new Promise(resolve => {
      const timer = setTimeout(() => { window.removeEventListener('message', handler); resolve(null) }, 2000)
      const handler = (e: MessageEvent) => {
        if (e.data?.type === 'designState') {
          clearTimeout(timer); window.removeEventListener('message', handler)
          resolve(e.data.data ?? null)
        }
      }
      window.addEventListener('message', handler)
      iframeRef.current?.contentWindow?.postMessage({ type: 'getDesignState' }, '*')
    })

  const handleReport = async () => {
    if (!confirmedState) return
    setRptLoad(true); setRptError(null)
    try {
      const jsState = await getJsDesignState()
      const blob = await docGenerateReport({
        state:           confirmedState as Record<string, unknown>,
        approved_design: approvedInductorDesign as Record<string, unknown>,
        step15_result:   approvedCapacitorDesign
                           ? ({ ...approvedCapacitorDesign } as Record<string, unknown>)
                           : {},
        step16_params: { ...step16_params, js_design_state: jsState },
      })
      const url = URL.createObjectURL(blob)
      const a   = document.createElement('a')
      a.href     = url
      a.download = `PFC_Report_${(confirmedState as any).project_id ?? 'design'}_Steps1_16.pdf`
      document.body.appendChild(a); a.click(); document.body.removeChild(a)
      setTimeout(() => URL.revokeObjectURL(url), 150)
    } catch(e) {
      setRptError((e as Error).message ?? String(e))
    } finally { setRptLoad(false) }
  }

  return (
    <div style={{ display:'flex', flexDirection:'column', height:'100%' }}>

      {/* ── iframe: served from public/ — no srcdoc, no allow-same-origin ── */}
      <iframe
        ref={iframeRef}
        src="/control_design.html"
        title="PFC Control Loop Design Tool"
        onLoad={handleLoad}
        style={{
          width: '100%',
          height: 'calc(100vh - 175px)',
          minHeight: 680,
          border: 'none',
          borderRadius: 10,
          background: '#0b1220',
          display: 'block',
        }}
        sandbox="allow-scripts allow-downloads allow-forms allow-modals"
      />

      {/* ── Action bar ─────────────────────────────────────────────────── */}
      <div style={{
        display: 'flex', gap: 8, paddingTop: 10, marginTop: 6,
        borderTop: `0.5px solid ${C.border}`,
        justifyContent: 'space-between', alignItems: 'flex-start',
      }}>
        <div style={{ display: 'flex', gap: 8 }}>
          <Btn variant="ghost" onClick={onBack}>← Back</Btn>
          <Btn variant="ghost" onClick={onRestart}>↺ New design</Btn>
        </div>

        <div style={{ display:'flex', flexDirection:'column', gap:5, alignItems:'flex-end' }}>
          {rptError && (
            <div style={{ fontSize:11, color:'#c0392b', background:'#fdf2f2',
              border:'1px solid #e8b4b8', borderRadius:6, padding:'4px 10px' }}>
              ⚠ Report failed: {rptError}
            </div>
          )}
          <div style={{ display:'flex', gap:8, alignItems:'center' }}>
            <span style={{ fontSize:10, color:C.hint, fontFamily:'IBM Plex Mono,monospace' }}>
              Word doc ↓ &amp; JSON save inside the tool
            </span>
            <Btn variant="success" disabled={rptLoading} onClick={handleReport}>
              {rptLoading ? '⏳ Generating…' : '📄 Generate & Download Report (Steps 1–16)'}
            </Btn>
          </div>
        </div>
      </div>
    </div>
  )
}
