/**
 * DesignExplorer — the PFC Design Explorer page. Phase 1: shell, gate, scene framework.
 *
 * Plan and every settled constraint: specs/Improvements/ANIMATION_PLAN.md
 *
 * READ-ONLY AND ADDITIVE (C-2, C-11). This page fetches the design-state export and renders it.
 * It never writes back, never re-runs a step, and holds no state that any earlier page reads. The
 * only interaction is *selecting* what to look at.
 *
 * NEVER RECOMPUTE PHYSICS HERE (C-8). Every number on screen comes from the export. The reference
 * package we reviewed recomputes duty and ripple in the browser from a single scalar L, which for
 * our design is the flat-inductance divergence fixed at C255 and contradicts Chapter 7's DCM at
 * high line. If a value is not in the export, the answer is to add it to the export — not to
 * derive it here.
 *
 * NEVER DRAW PHYSICS WE DO NOT MODEL (C-9). The engine deliberately does not track the DCM ringing
 * phase (C253/B16), so no scene may draw a ring.
 *
 * WHY THIS IS A REACT PAGE AND NOT AN IFRAMED HTML ASSET. The one existing embedded tool
 * (control_design.html) is served from public/ and cost two rounds of "fixed" that never reached
 * the browser because a second copy existed (C244). A React page using our own ui.tsx primitives
 * has no duplicate-asset failure mode and satisfies C-3 (our tokens) by construction.
 */
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { C, Btn, Card, SecHead } from './ui'
import { designState, designStateWaveforms,
         type DesignState, type DesignStatePoint, type DesignWaveforms } from '../api/client'
import { LineCycleScene, SwitchingScene, PowerStageSchematic } from './DesignExplorerScenes'

// ── scenes ───────────────────────────────────────────────────────────────────
// Four time bases spanning five orders of magnitude. No single timeline shows them honestly, so
// each scene owns its own clock. `span` is the real-time duration one pass represents.
export interface Scene {
  id: string
  title: string
  eyebrow: string
  /** real seconds represented by one pass of the scene clock */
  span: (d: DesignState) => number
  /** how much slower than real time it plays, so the eye can follow it */
  slowmo: number
  caption: string
  phase: string          // which build phase fills this scene in
}

const FLINE = (d: DesignState) => Number(d.spec.fline_Hz) || 60
const FSW   = (d: DesignState) => Number(d.spec.fsw_Hz) || 70000

export const SCENES: Scene[] = [
  {
    id: 'switching', title: 'Switching detail', eyebrow: 'one switching period',
    span: d => 1 / FSW(d), slowmo: 2e5, phase: 'Phase 2',
    caption: 'One channel over a single switching period: the FET turns on and the inductor '
      + 'charges from the rectified input, the FET turns off and the boost diode carries the '
      + 'current into the bus. The triangle is built from the engine’s own i_on, i_off and duty '
      + 'at the selected line angle — not from a formula evaluated in the browser.',
  },
  {
    id: 'line', title: 'Line cycle', eyebrow: 'one half line cycle',
    span: d => 1 / (2 * FLINE(d)), slowmo: 300, phase: 'Phase 2',
    caption: 'Both channels 180° apart over a half line cycle. Duty sweeps as the input rises and '
      + 'falls, the ripple envelope follows the per-point inductance, the two phases cancel at the '
      + 'input, and DCM appears only where the engine says it does.',
  },
  {
    id: 'transient', title: 'Load step', eyebrow: 'closed-loop response',
    span: () => 0.4, slowmo: 20, phase: 'Phase 4',
    caption: 'A load step and the bus recovering. The trace is the real closed-loop response — the '
      + 'step response of the output impedance built from this design’s compensator — with the '
      + 'cycle-average drawn over it, because the recovery band is measured on the average and not '
      + 'on the instantaneous ripple.',
  },
  {
    id: 'steady', title: 'Steady state', eyebrow: 'summary — not a timeline',
    span: () => 0, slowmo: 1, phase: 'Phase 5',
    caption: 'Losses, temperatures and margins at the selected operating point. This scene does '
      + 'not animate: nothing here varies with time at the scale the other scenes use.',
  },
]

// ── small presentational helpers, all on our tokens (C-3) ────────────────────
const mono: React.CSSProperties = { fontFamily: 'IBM Plex Mono, monospace' }

const Num: React.FC<{ label: string; value: unknown; unit?: string; dp?: number }> =
({ label, value, unit, dp = 2 }) => {
  const v = typeof value === 'number' && isFinite(value)
    ? value.toFixed(dp)
    : (value == null || value === '' ? '—' : String(value))
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, padding: '3px 0' }}>
      <span style={{ fontSize: 12, color: C.muted }}>{label}</span>
      <span style={{ ...mono, fontSize: 12, color: v === '—' ? C.hint : C.text }}>
        {v}{v !== '—' && unit ? <span style={{ color: C.muted }}> {unit}</span> : null}
      </span>
    </div>
  )
}

/** The C-12 gate, rendered. A blocked page says exactly which chapters are missing — an empty
 *  panel would read as "designed, and zero", which is the confusion the whole export avoids. */
const Blocked: React.FC<{ missing: string[]; onBack: () => void }> = ({ missing, onBack }) => (
  <Card>
    <SecHead icon="🎬" label="Design Explorer is not available yet" />
    <div style={{ fontSize: 13, color: C.muted, lineHeight: 1.6, maxWidth: 680 }}>
      The explorer animates the <b>approved</b> design, so every chapter has to be complete before
      it can show anything. It deliberately will not fill the gaps with nominal values — a plausible
      default shown as if it were a result is worse than a page that refuses to open.
    </div>
    <div style={{ marginTop: 14, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
      {missing.map(m => (
        <span key={m} style={{ ...mono, fontSize: 11, padding: '4px 10px', borderRadius: 6,
          background: C.amberL, color: C.amber, border: `1px solid ${C.amber}44` }}>
          {m} — not approved
        </span>
      ))}
    </div>
    <div style={{ marginTop: 18 }}>
      <Btn variant="ghost" onClick={onBack}>← Back to input filter</Btn>
    </div>
  </Card>
)

// ── page ─────────────────────────────────────────────────────────────────────
export interface DesignExplorerProps {
  confirmedState:           Record<string, unknown>
  approvedInductorDesign?:  Record<string, unknown> | null
  approvedCapacitorDesign?: Record<string, unknown> | null
  approvedControlParams?:   Record<string, unknown> | null
  approvedSemiconductor?:   Record<string, unknown> | null
  approvedInputProtection?: Record<string, unknown> | null
  approvedInputFilter?:     Record<string, unknown> | null
  onBack:    () => void
  onRestart: () => void
}

export const DesignExplorer: React.FC<DesignExplorerProps> = ({
  confirmedState, approvedInductorDesign, approvedCapacitorDesign, approvedControlParams,
  approvedSemiconductor, approvedInputProtection, approvedInputFilter, onBack, onRestart,
}) => {
  const [ds, setDs] = useState<DesignState | null>(null)
  const [wf, setWf] = useState<DesignWaveforms | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(true)

  const [sceneIdx, setSceneIdx] = useState(0)
  const [pointIdx, setPointIdx] = useState(0)
  const [playing, setPlaying] = useState(true)
  const [tNorm, setTNorm] = useState(0)          // 0..1 through the current scene's span

  // Honour the OS setting rather than animating regardless (accessibility, C-3 house style).
  const reduced = useMemo(
    () => typeof window !== 'undefined'
      && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches, [])

  // ── live fetch (C-7): always the currently approved state, never a snapshot ──
  const load = useCallback(async () => {
    setBusy(true); setErr(null)
    const req = {
      state: confirmedState,
      approved_design:  approvedInductorDesign ?? null,
      step15_result:    approvedCapacitorDesign ?? null,
      step16_params:    approvedControlParams ?? null,
      semiconductor:    approvedSemiconductor ?? null,
      input_protection: approvedInputProtection ?? null,
      input_filter:     approvedInputFilter ?? null,
    }
    try {
      // both reads in parallel; the waveform arrays are a separate endpoint because that one
      // calls the engine and the projection deliberately cannot (ANIMATION_PLAN, Phase 0 rule 1)
      const [state, waves] = await Promise.all([designState(req), designStateWaveforms(req)])
      setDs(state); setWf(waves)
    } catch (e) { setErr((e as Error).message) } finally { setBusy(false) }
  }, [confirmedState, approvedInductorDesign, approvedCapacitorDesign, approvedControlParams,
      approvedSemiconductor, approvedInputProtection, approvedInputFilter])

  useEffect(() => { void load() }, [load])

  // ── the scene clock ────────────────────────────────────────────────────────
  // setInterval rather than requestAnimationFrame, deliberately: a constant pace is easier to
  // narrate in front of a reviewer than one that tracks frame rate.
  const scene = SCENES[sceneIdx]
  const raf = useRef<number | null>(null)
  useEffect(() => {
    if (!ds || !playing || reduced || !scene || scene.span(ds) <= 0) return
    const stepMs = 33
    const passMs = scene.span(ds) * scene.slowmo * 1000
    const id = window.setInterval(
      () => setTNorm(p => (p + stepMs / Math.max(passMs, 1)) % 1), stepMs)
    raf.current = id
    return () => window.clearInterval(id)
  }, [ds, playing, reduced, scene])

  // reset the clock when the scene or operating point changes, so a pass always starts at 0
  useEffect(() => { setTNorm(0) }, [sceneIdx, pointIdx])

  const point: DesignStatePoint | null = ds?.points?.[pointIdx] ?? null
  // the series for the selected point, if the engine produced one
  const series = point && wf?.available
    ? (wf.series[String(Math.round(point.vac_V))] ?? null) : null
  // where we are inside the switching period at this line angle — the ONLY thing the page
  // derives, and it is a phase position, not physics: the duty itself comes from the engine.
  const idx = series ? Math.min(series.t_ms.length - 1,
    Math.max(0, Math.round(tNorm * (series.t_ms.length - 1)))) : 0
  const qOn = series ? (tNorm * 40) % 1 < series.D[idx] : false
  const tReal = ds && scene ? tNorm * scene.span(ds) : 0

  if (busy) return <Card><div style={{ color: C.muted, fontSize: 13 }}>Loading design state…</div></Card>
  if (err) return (
    <Card>
      <SecHead icon="⚠" label="Could not load the design state" />
      <div style={{ ...mono, fontSize: 12, color: C.red, whiteSpace: 'pre-wrap' }}>{err}</div>
      <div style={{ marginTop: 14, display: 'flex', gap: 8 }}>
        <Btn variant="primary" onClick={() => void load()}>Retry</Btn>
        <Btn variant="ghost" onClick={onBack}>← Back</Btn>
      </div>
    </Card>
  )
  if (!ds) return null
  if (ds.readiness.gate === 'blocked') return <Blocked missing={ds.readiness.missing} onBack={onBack} />

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '230px minmax(560px,1fr) 300px', gap: 16 }}>

      {/* ── left rail: operating point. One at a time (settled) ── */}
      <Card>
        <SecHead icon="⚡" label="Operating point" sub={`${ds.points.length} approved`} />
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6, maxHeight: 520, overflowY: 'auto' }}>
          {ds.points.map((p, i) => {
            const on = i === pointIdx
            return (
              <div key={p.vac_V} role="button" tabIndex={0} aria-selected={on}
                onClick={() => setPointIdx(i)}
                onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setPointIdx(i) } }}
                style={{ cursor: 'pointer', padding: '8px 10px', borderRadius: 7,
                  background: on ? C.accentL : C.bg3, border: `1px solid ${on ? C.accent : C.border}`,
                  borderLeft: `4px solid ${on ? C.accent : C.border2}` }}>
                <div style={{ ...mono, fontSize: 13, color: on ? C.text : C.muted, fontWeight: on ? 600 : 400 }}>
                  {p.vac_V.toFixed(0)} V<span style={{ color: C.hint }}>AC</span>
                </div>
                <div style={{ ...mono, fontSize: 10.5, color: C.hint, marginTop: 2 }}>
                  L {p.L_full_nom_uH?.toFixed(0) ?? '—'} µH · ΔI {p.dIL_pp_A?.toFixed(1) ?? '—'} A
                </div>
              </div>
            )
          })}
        </div>
      </Card>

      {/* ── centre: the scene stage ── */}
      <Card>
        <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 12 }}>
          <div>
            <div style={{ ...mono, fontSize: 10.5, letterSpacing: 1, textTransform: 'uppercase', color: C.teal }}>
              Scene {sceneIdx + 1} of {SCENES.length} · {scene.eyebrow}
            </div>
            <div style={{ fontSize: 16, fontWeight: 600, color: C.text, marginTop: 3 }}>{scene.title}</div>
          </div>
          <span style={{ ...mono, fontSize: 10.5, padding: '3px 8px', borderRadius: 5,
            background: C.bg4, color: C.hint, border: `1px solid ${C.border}` }}>{scene.phase}</span>
        </div>

        {/* stage */}
        {series && (scene.id === 'line' || scene.id === 'switching') ? (
          <div style={{ marginTop: 12, borderRadius: 8, background: C.bg,
            border: `1px solid ${C.border}`, padding: 8 }}>
            {scene.id === 'line'
              ? <LineCycleScene s={series} tNorm={tNorm} nch={Number(ds.spec.nch) || 1} />
              : <SwitchingScene s={series} tNorm={tNorm} fsw={Number(ds.spec.fsw_Hz) || 70000} />}
            <PowerStageSchematic qOn={qOn} nch={Number(ds.spec.nch) || 1}
              vac={point?.vac_V ?? 0} />
          </div>
        ) : (
        <div style={{ marginTop: 12, height: 300, borderRadius: 8, background: C.bg,
          border: `1px solid ${C.border}`, display: 'flex', flexDirection: 'column',
          alignItems: 'center', justifyContent: 'center', gap: 10 }}>
          <div style={{ ...mono, fontSize: 26, color: C.accent }}>
            {scene.span(ds) > 0 ? `t = ${(tReal * 1e3).toFixed(scene.id === 'switching' ? 4 : 2)} ms` : '—'}
          </div>
          <div style={{ ...mono, fontSize: 11, color: C.hint }}>
            {scene.span(ds) > 0
              ? `span ${(scene.span(ds) * 1e3).toFixed(scene.id === 'switching' ? 4 : 2)} ms · ×1/${scene.slowmo} speed`
              : 'static scene'}
          </div>
          {scene.span(ds) > 0 && (
            <div style={{ width: '78%', height: 4, borderRadius: 2, background: C.bg4, overflow: 'hidden' }}>
              <div style={{ width: `${tNorm * 100}%`, height: '100%', background: C.accent }} />
            </div>
          )}
          <div style={{ fontSize: 11, color: C.hint, marginTop: 4 }}>
            {wf && !wf.available && scene.id !== 'steady'
              ? `no series: ${wf.reason}` : `waveforms arrive in ${scene.phase}`}
          </div>
        </div>
        )}

        <div style={{ marginTop: 12, fontSize: 12.5, color: C.muted, lineHeight: 1.65 }}>{scene.caption}</div>

        {/* guided navigation (settled: scene by scene, not free roaming) */}
        <div style={{ marginTop: 14, display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <Btn variant="ghost" onClick={() => setSceneIdx(i => Math.max(0, i - 1))}>← Previous scene</Btn>
          <Btn variant="primary" onClick={() => setSceneIdx(i => Math.min(SCENES.length - 1, i + 1))}>
            Next scene →
          </Btn>
          <Btn variant="ghost" onClick={() => setPlaying(p => !p)}>{playing ? '⏸ Pause' : '▶ Play'}</Btn>
          {reduced && (
            <span style={{ fontSize: 11, color: C.amber }}>
              motion reduced by system setting — scrub manually
            </span>
          )}
          <div style={{ flex: 1 }} />
          <Btn variant="ghost" onClick={() => void load()}>↻ Reload state</Btn>
        </div>
        {scene.span(ds) > 0 && (
          <input type="range" min={0} max={1000} value={Math.round(tNorm * 1000)} aria-label="scene time"
            onChange={e => { setPlaying(false); setTNorm(Number(e.target.value) / 1000) }}
            style={{ width: '100%', marginTop: 10, accentColor: C.accent }} />
        )}
      </Card>

      {/* ── right: the selected point, straight from the export ── */}
      <Card>
        <SecHead icon="📐" label="Point summary" sub="from the approved design" />
        {point ? (
          <>
            <Num label="V_AC"          value={point.vac_V}          unit="V"  dp={0} />
            <Num label="V_in,pk"       value={point.vin_pk_V}       unit="V"  dp={1} />
            <Num label="L_φ (as built)" value={point.L_full_nom_uH} unit="µH" dp={1} />
            <Num label="L required"    value={point.L_req_uH}       unit="µH" dp={1} />
            <Num label="k_bias"        value={point.k_bias}         dp={3} />
            <Num label="ΔI_L,pp"       value={point.dIL_pp_A}       unit="A"  dp={2} />
            <Num label="ΔI_in,pp"      value={point.dIin_pp_A}      unit="A"  dp={2} />
            <Num label="D at crest"    value={point.D_crest}        dp={3} />
            <Num label="I_rms"         value={point.Irms_A}         unit="A"  dp={2} />
            <Num label="H"             value={point.H_Oe}           unit="Oe" dp={1} />
            <Num label="B_ac,pk"       value={point.Bac_pk_T}       unit="T"  dp={4} />
            <div style={{ height: 1, background: C.border, margin: '8px 0' }} />
            <Num label="P_core (avg)"  value={point.Pcore_avg_W}    unit="W" />
            <Num label="P_cu (avg)"    value={point.Pcu_avg_W}      unit="W" />
            <Num label="P_total (avg)" value={point.Ptotal_avg_W}   unit="W" />
          </>
        ) : <div style={{ fontSize: 12, color: C.hint }}>No operating points in the export.</div>}

        <div style={{ marginTop: 14, padding: 10, borderRadius: 7, background: C.bg3,
          border: `1px solid ${C.border}`, fontSize: 11, color: C.hint, lineHeight: 1.55 }}>
          Every value on this page is read from the approved design. Nothing here is recalculated,
          and nothing this page does can change a previous step.
        </div>

        <div style={{ marginTop: 14, display: 'flex', gap: 8 }}>
          <Btn variant="ghost" onClick={onBack}>← Back</Btn>
          <Btn variant="ghost" onClick={onRestart}>Restart</Btn>
        </div>
      </Card>
    </div>
  )
}
