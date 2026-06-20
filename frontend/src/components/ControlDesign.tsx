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
import React, { useRef, useCallback, useState, useEffect } from 'react'
import { C, Btn } from './ui'
import type { CapacitorResult } from './Step15Capacitor'
import { docGenerateReport } from '../api/client'
import { PowerPlantReview } from './PowerPlantReview'
import { ComponentsSelect, type ComponentSelections } from './ComponentsSelect'
import { CoreReview } from './CoreReview'

interface Props {
  confirmedState:          Record<string, unknown>
  approvedInductorDesign:  Record<string, unknown>
  approvedCapacitorDesign: CapacitorResult | null
  onBack:    () => void
  onRestart: () => void
  onSelectSemiconductors: () => void
}

export const ControlDesign: React.FC<Props> = ({
  confirmedState, approvedInductorDesign, approvedCapacitorDesign,
  onBack, onRestart, onSelectSemiconductors,
}) => {
  const iframeRef              = useRef<HTMLIFrameElement>(null)
  const [rptLoading, setRptLoad] = useState(false)
  const [rptError,   setRptError] = useState<string|null>(null)
  // Control-Design screen wizard. S1–S3 are native React screens; S4–S7 drive the
  // embedded FAN9672 tool's tabs (S4 Compensators&Bode interactive, S5 Transient,
  // S6 iTHD, S7 Schematic + report/approve) one at a time in "wizard mode".
  type Scr = 's1'|'s2'|'s3'|'s4'|'s5'|'s6'|'s7'
  type Sub = 'cur'|'vol'|'res'
  const [screen, setScreen] = useState<Scr>('s1')
  const [s4sub, setS4sub] = useState<Sub>('cur')   // S4 sub-screen: current → voltage → results
  const [s2sel, setS2Sel] = useState<ComponentSelections|null>(null)
  const [reportGen, setReportGen] = useState(false)
  const injectedRef = useRef(false)
  const TOOL_TAB: Record<string, string> = { s4: 'screen2', s5: 'screen3', s6: 'screen4', s7: 'screen5' }
  const WIZ_NEXT: Record<string, Scr> = { s4: 's5', s5: 's6', s6: 's7' }
  const WIZ_PREV: Record<string, Scr> = { s4: 's3', s5: 's4', s6: 's5', s7: 's6' }
  const WIZ_LABEL: Record<string, string> = {
    s5: 'Screen 5/7 · Transient', s6: 'Screen 6/7 · iTHD', s7: 'Screen 7/7 · Schematic & Report',
  }
  // S4 sub-screens — freely switchable via a sub-tab bar (not gated)
  const SUB_ORDER: Sub[] = ['cur', 'vol', 'res']
  const SUB_TAB: Record<Sub, string> = {
    cur: '4a · Current loop', vol: '4b · Voltage loop', res: '4c · Final components',
  }
  const SUB_LABEL: Record<Sub, string> = {
    cur: '4a · Current loop — HL & LL (incl. CS filter across R_CS)',
    vol: '4b · Voltage loop — HL & LL',
    res: '4c · Final control-loop components',
  }
  const screenRef = useRef<Scr>(screen); screenRef.current = screen
  const s4subRef = useRef<Sub>(s4sub); s4subRef.current = s4sub
  const postWizard = () => {
    const s = screenRef.current
    const win = iframeRef.current?.contentWindow
    if (!win) return
    if (s === 's4') {
      win.postMessage({ type: 'setWizardScreen', screen: 'screen2', sub: s4subRef.current }, '*')
    } else if (TOOL_TAB[s]) {
      win.postMessage({ type: 'setWizardScreen', screen: TOOL_TAB[s] }, '*')
    } else {
      // S1–S3: iframe is mounted but hidden — pre-position it on the first tool screen
      // in wizard mode so revealing it at S4 is instant (no un-configured flash).
      win.postMessage({ type: 'setWizardScreen', screen: 'screen2', sub: 'cur' }, '*')
    }
  }
  // drive the tool tab / S4 sub-screen on every screen change (iframe stays mounted always)
  useEffect(() => {
    const id = setTimeout(postWizard, 60); return () => clearTimeout(id)
  }, [screen, s4sub])  // eslint-disable-line react-hooks/exhaustive-deps

  // wizard nav — S4 advances/retreats as a whole; its 3 sub-screens switch freely (tabs)
  const goNext = () => setScreen(WIZ_NEXT[screen])
  const goBack = () => setScreen(WIZ_PREV[screen])

  // ── Auto-size the iframe to its content (single browser scrollbar) ──────────
  // control_design.html is cross-origin (no allow-same-origin), so it posts its
  // own document height; we grow the iframe to fit → no inner scrollbar.
  useEffect(() => {
    const onMsg = (e: MessageEvent) => {
      if (e.data?.type === 'docHeight' && typeof e.data.height === 'number' && e.data.height > 0) {
        const f = iframeRef.current
        if (f) f.style.height = e.data.height + 'px'
      }
    }
    window.addEventListener('message', onMsg)
    return () => window.removeEventListener('message', onMsg)
  }, [])

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
      { type: 'setPythonValues', params: { ...params, rcs_mohm: s2sel?.rcs_mohm } },
      '*'
    )
  }, [params, s2sel])  // eslint-disable-line react-hooks/exhaustive-deps

  // The iframe now loads before S2 is confirmed, so re-inject the designer's R_CS
  // into the tool once S2 is locked in (rcs drives the compensator sizing / Bode).
  useEffect(() => {
    if (s2sel) sendValues()
  }, [s2sel])  // eslint-disable-line react-hooks/exhaustive-deps

  const handleLoad = useCallback(() => {
    injectedRef.current = false
    // Give the JS tool 2 s to initialise before posting values.
    // The postMessage listener in the HTML calls setPythonValues when received.
    const tryInject = (attempt: number) => {
      setTimeout(() => {
        sendValues()
        postWizard()   // put the tool into wizard mode on the current screen's tab
        // Retry once more after another second in case the first arrived early
        if (attempt < 2) tryInject(attempt + 1)
      }, attempt === 0 ? 2000 : 1500)
    }
    tryInject(0)
  }, [sendValues])  // eslint-disable-line react-hooks/exhaustive-deps

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
        step16_params: { ...step16_params, js_design_state: jsState, s2: s2sel ?? undefined },
      })
      const url = URL.createObjectURL(blob)
      const a   = document.createElement('a')
      a.href     = url
      a.download = `PFC_Report_${(confirmedState as any).project_id ?? 'design'}_Steps1_16.pdf`
      document.body.appendChild(a); a.click(); document.body.removeChild(a)
      setTimeout(() => URL.revokeObjectURL(url), 150)
      setReportGen(true)   // enable "Approve & go to Semiconductors"
    } catch(e) {
      setRptError((e as Error).message ?? String(e))
    } finally { setRptLoad(false) }
  }


  const onS123 = screen === 's1' || screen === 's2' || screen === 's3'

  return (
    <>
      {/* ── Native review/select screens S1–S3 ── */}
      {screen === 's1' && (
        <PowerPlantReview confirmedState={confirmedState} params={params}
          onBack={onBack} onConfirm={() => setScreen('s2')} />
      )}
      {screen === 's2' && (
        <ComponentsSelect params={params} initial={s2sel}
          onBack={() => setScreen('s1')} onConfirm={(sel) => { setS2Sel(sel); setScreen('s3') }} />
      )}
      {screen === 's3' && (
        <CoreReview params={params} s2sel={s2sel}
          onBack={() => setScreen('s2')} onConfirm={() => { setS4sub('cur'); setScreen('s4') }} />
      )}

      {/* ── S4–S7 share ONE iframe mounted for the whole Control-Design session
            (hidden on S1–S3). It loads + configures once, so it never reloads,
            never flashes its un-configured default, and keeps the designer's tool
            state (crossover, placement) across navigation. ── */}
      <div style={{ display: onS123 ? 'none' : 'flex', flexDirection: 'column', height: '100%' }}>

        {/* S4 sub-tab bar: freely switch current / voltage / results */}
        {screen === 's4' && (
          <div style={{ display: 'flex', gap: 6, marginBottom: 10 }}>
            {SUB_ORDER.map(sb => {
              const active = sb === s4sub
              return (
                <button key={sb} onClick={() => setS4sub(sb)} style={{
                  flex: 1, padding: '8px 10px', borderRadius: 8, cursor: 'pointer',
                  fontSize: 12, fontWeight: 600, fontFamily: 'IBM Plex Mono,monospace',
                  border: `1px solid ${active ? C.teal : C.border}`,
                  background: active ? 'rgba(45,212,191,.12)' : C.bg3,
                  color: active ? C.teal : C.muted,
                }}>{SUB_TAB[sb]}</button>
              )
            })}
          </div>
        )}

        <iframe
          ref={iframeRef}
          src="/control_design.html"
          title="PFC Control Loop Design Tool"
          onLoad={handleLoad}
          scrolling="no"
          style={{ width: '100%', minHeight: 680, border: 'none', borderRadius: 10,
            background: '#0b1220', display: 'block' }}
          sandbox="allow-scripts allow-downloads allow-forms allow-modals"
        />

        {!onS123 && (
          <div style={{ display: 'flex', gap: 8, paddingTop: 10, marginTop: 6,
            borderTop: `0.5px solid ${C.border}`, justifyContent: 'space-between', alignItems: 'center' }}>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <Btn variant="ghost" onClick={goBack}>← Back</Btn>
              <Btn variant="ghost" onClick={onRestart}>↺ New design</Btn>
              <span style={{ fontSize: 11, color: C.hint, fontFamily: 'IBM Plex Mono,monospace' }}>
                {screen === 's4' ? `Screen 4/7 · ${SUB_LABEL[s4sub]}` : WIZ_LABEL[screen]}
              </span>
            </div>

            {screen !== 's7' ? (
              <Btn variant="primary" onClick={goNext}>Confirm &amp; Continue →</Btn>
            ) : (
              <div style={{ display:'flex', flexDirection:'column', gap:5, alignItems:'flex-end' }}>
                {rptError && (
                  <div style={{ fontSize:11, color:'#c0392b', background:'#fdf2f2',
                    border:'1px solid #e8b4b8', borderRadius:6, padding:'4px 10px' }}>
                    ⚠ Report failed: {rptError}
                  </div>
                )}
                <div style={{ display:'flex', gap:8, alignItems:'center' }}>
                  <Btn variant="success" disabled={rptLoading} onClick={handleReport}>
                    {rptLoading ? '⏳ Generating…' : '📥 Download + Review (Chapters 1–6 + Appendices)'}
                  </Btn>
                  <Btn variant="primary" disabled={!reportGen} onClick={onSelectSemiconductors}>
                    ✓ Approve &amp; go to Semiconductors →
                  </Btn>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </>
  )
}
