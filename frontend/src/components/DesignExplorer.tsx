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
import { designState, designStateWaveforms, designStateSchematic,
         type DesignState, type DesignStatePoint, type DesignWaveforms,
         type DesignSchematic } from '../api/client'
import { LineCycleScene, SwitchingScene, PowerStageSchematic,
         MagneticsScene, CapacitorScene, BodeScene, TransientScene,
         SteadyStateScene } from './DesignExplorerScenes'

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
    id: 'magnetics', title: 'Magnetics', eyebrow: 'flux, field and loss over the cycle',
    span: d => 1 / (2 * FLINE(d)), slowmo: 300, phase: 'Phase 3',
    caption: 'Flux density against the saturation limit AT THE CORE TEMPERATURE — not the 25 °C '
      + 'datasheet value, because powder saturation falls as the core warms and the cold figure '
      + 'would flatter the margin. Both flux bases are marked: the report quotes the inner-bore '
      + 'peak, while the engine’s accept/reject gate still runs on the mean path. Below, the '
      + 'magnetising field and the core/copper split over the same cycle.',
  },
  {
    id: 'capacitor', title: 'DC bus capacitor', eyebrow: 'ripple, ESR and case temperature',
    span: () => 0, slowmo: 1, phase: 'Phase 3',
    caption: 'Bank ripple current, case temperature and ESR at every operating point, from '
      + 'Chapter 5’s own bank model. ESR falls as the part warms, so the self-heating that sets '
      + 'the temperature is self-limiting — a case rise below one-for-one with ambient is the '
      + 'model working, not a defect.',
  },
  {
    id: 'control', title: 'Control loops', eyebrow: 'open-loop gain and phase — static',
    span: () => 0, slowmo: 1, phase: 'Phase 4',
    caption: 'Both loops, at the selected operating point, with crossover and phase margin marked. '
      + 'This plot is deliberately static: a frequency response has no time coordinate, so nothing '
      + 'slides along it while a transient plays. The link to the next scene is by annotation — '
      + 'crossover sets the recovery timescale and phase margin decides whether it rings. Note the '
      + 'separation: the current loop closes near 8 kHz and settles inside a switching period, '
      + 'while the voltage loop is deliberately far below 120 Hz so it does NOT chase bus ripple '
      + 'and distort the input current.',
  },
  {
    id: 'schematic', title: 'Controller schematic', eyebrow: 'FAN9672 application circuit',
    span: () => 0, slowmo: 1, phase: 'Phase 4',
    caption: 'The complete FAN9672 front end with every external component annotated from the '
      + 'sized bill of materials. This is the SAME drawing and the SAME value context the report '
      + 'prints — rendered as SVG here rather than as a raster, so the page can scale it and the '
      + 'two can never show different components. Amber values are live design selections; any '
      + 'component that fell back to fixed practice is counted below the sheet rather than passing '
      + 'as a designed value.',
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


/** Ch1-10 at a glance, from the export's own chapter sections (C264).
 *
 *  Every row is a value the design already approved — this panel formats, it does not compute.
 *  A chapter that is not approved says so rather than rendering an empty card, because an empty
 *  card reads as "designed, and zero". */
const ChapterSummary: React.FC<{ ds: DesignState }> = ({ ds }) => {
  const rows: Array<[string, string, Array<[string, unknown]>]> = []
  const ch = ds.chapters as Record<string, any>
  const f = (v: unknown, dp = 2, unit = '') =>
    typeof v === 'number' && isFinite(v) ? `${v.toFixed(dp)}${unit ? ' ' + unit : ''}`
      : (v == null || v === '' ? '—' : String(v))

  if (ch.magnetics) rows.push(['Ch 3-4', 'Inductor', [
    ['Core', `${ch.magnetics.core?.name ?? '—'} (${ch.magnetics.core?.material ?? '—'})`],
    ['Turns', f(ch.magnetics.winding?.turns, 0)],
    ['DCR @100 °C', f(ch.magnetics.winding?.DCR_100C_mOhm, 1, 'mΩ')],
    ['B_sat @T_core', f(ch.magnetics.flux?.Bsat_at_Tcore_T, 3, 'T')],
    ['T_core / ΔT', `${f(ch.magnetics.thermal?.T_core_C, 1)} / ${f(ch.magnetics.thermal?.dT_rise_C, 1)} °C`],
  ]])
  if (ch.capacitor) rows.push(['Ch 5', 'DC bus capacitor', [
    ['Part', ch.capacitor.selected?.part_number ?? '—'],
    ['Bank', `${f(ch.capacitor.selected?.value_uF, 0)} µF × ${f(ch.capacitor.selected?.qty, 0)}`],
    ['Rating', f(ch.capacitor.selected?.voltage_rating_V, 0, 'V')],
    ['C required', f(ch.capacitor.C_required_uF, 0, 'µF')],
  ]])
  if (ch.control) rows.push(['Ch 6', 'Control', [
    ['f_ci / f_cv', `${f(ch.control.fci_Hz, 0, 'Hz')} / ${f(ch.control.fcv_Hz, 1, 'Hz')}`],
    ['L / C', `${f(ch.control.L_uH, 1, 'µH')} / ${f(ch.control.C_uF, 0, 'µF')}`],
    ['ESR', f(ch.control.ESR_mOhm, 1, 'mΩ')],
  ]])
  if (ch.semiconductors) rows.push(['Ch 7', 'Semiconductors', [
    ['MOSFET', ch.semiconductors.mosfet?.part_number ?? '—'],
    ['Diode', ch.semiconductors.diode?.part_number ?? '—'],
    ['Bridge', ch.semiconductors.bridge?.part_number ?? '—'],
  ]])
  if (ch.protection) rows.push(['Ch 8-9', 'Input protection', [['Approved', 'yes']]])
  if (ch.emi) rows.push(['Ch 10', 'EMI filter', [['Approved', 'yes']]])

  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(200px,1fr))', gap: 10 }}>
      {rows.map(([tag, title, items]) => (
        <div key={tag} style={{ background: C.bg3, border: `1px solid ${C.border}`,
          borderRadius: 7, padding: '10px 12px' }}>
          <div style={{ ...mono, fontSize: 10, color: C.teal, letterSpacing: 1 }}>{tag}</div>
          <div style={{ fontSize: 12.5, fontWeight: 600, color: C.text, margin: '2px 0 6px' }}>{title}</div>
          {items.map(([k, v]) => (
            <div key={k} style={{ display: 'flex', justifyContent: 'space-between', gap: 8, padding: '2px 0' }}>
              <span style={{ fontSize: 11, color: C.muted }}>{k}</span>
              <span style={{ ...mono, fontSize: 11, color: C.text, textAlign: 'right' }}>{String(v)}</span>
            </div>
          ))}
        </div>
      ))}
    </div>
  )
}

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
  const [sch, setSch] = useState<DesignSchematic | null>(null)
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
      const [state, waves, schem] = await Promise.all([
        designState(req), designStateWaveforms(req), designStateSchematic(req)])
      setDs(state); setWf(waves); setSch(schem)
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
  const flux = (ds?.chapters?.magnetics as Record<string, any> | null)?.flux ?? null
  const capView = wf?.capacitor ?? null
  const thermal = wf?.thermal ?? null
  const ctrl = wf?.control ?? null
  const tr = ctrl?.transient
  const [loopKey, setLoopKey] = useState<'voltage' | 'current'>('voltage')
  const [transIdx, setTransIdx] = useState(0)
  const [sheetKey, setSheetKey] = useState<'low' | 'high'>('low')
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
                  L {p.L_full_nom_uH?.toFixed(0) ?? '—'}
                  {p.L_crest_nom_uH ? `→${p.L_crest_nom_uH.toFixed(0)}` : ''} µH
                  {' '}· ΔI {p.dIL_pp_A?.toFixed(1) ?? '—'} A
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
        {series && (scene.id === 'line' || scene.id === 'switching' || scene.id === 'magnetics') ? (
          <div style={{ marginTop: 12, borderRadius: 8, background: C.bg,
            border: `1px solid ${C.border}`, padding: 8 }}>
            {scene.id === 'line' ? (
              <>
                <LineCycleScene s={series} tNorm={tNorm} nch={Number(ds.spec.nch) || 1} />
                <PowerStageSchematic qOn={qOn} nch={Number(ds.spec.nch) || 1}
                  vac={point?.vac_V ?? 0} />
              </>
            ) : scene.id === 'switching' ? (
              <>
                <SwitchingScene s={series} tNorm={tNorm} fsw={Number(ds.spec.fsw_Hz) || 70000} />
                <PowerStageSchematic qOn={qOn} nch={Number(ds.spec.nch) || 1}
                  vac={point?.vac_V ?? 0} />
              </>
            ) : (
              <MagneticsScene s={series} tNorm={tNorm}
                bsat={flux ? (flux.Bsat_at_Tcore_T as number ?? null) : null}
                bmaxFL={flux ? (flux.Bmax_FL_T as number ?? null) : null}
                bInnerFL={flux ? (flux.Bmax_inner_FL_T as number ?? null) : null} />
            )}
          </div>
        ) : scene.id === 'control' && ctrl?.available && ctrl.loops[loopKey] ? (
          <div style={{ marginTop: 12, borderRadius: 8, background: C.bg,
            border: `1px solid ${C.border}`, padding: 8 }}>
            <div style={{ display: 'flex', gap: 8, marginBottom: 6 }}>
              {(['voltage', 'current'] as const).map(k => (
                <Btn key={k} variant={loopKey === k ? 'primary' : 'ghost'}
                  onClick={() => setLoopKey(k)}>{ctrl.loops[k]?.name ?? k}</Btn>
              ))}
            </div>
            <BodeScene loop={ctrl.loops[loopKey] as any} selectedVac={point?.vac_V ?? 0} />
          </div>
        ) : scene.id === 'transient' && tr?.available && tr.transitions?.length ? (
          <div style={{ marginTop: 12, borderRadius: 8, background: C.bg,
            border: `1px solid ${C.border}`, padding: 8 }}>
            <div style={{ display: 'flex', gap: 6, marginBottom: 6, flexWrap: 'wrap' }}>
              {tr.transitions.map((w, k) => (
                <Btn key={w.label} variant={transIdx === k ? 'primary' : 'ghost'}
                  onClick={() => setTransIdx(k)}>{w.label}</Btn>
              ))}
            </div>
            <TransientScene t={tr.t ?? []}
              trace={(point && point.vac_V >= 180 ? tr.transitions[transIdx].hl
                                                  : tr.transitions[transIdx].ll) ?? []}
              composite={((point && point.vac_V >= 180
                ? (tr.transitions[transIdx] as any).hl_composite
                : (tr.transitions[transIdx] as any).ll_composite) ?? []) as number[]}
              vout={tr.vout ?? 0} band={tr.band ?? 0}
              tNorm={tNorm} label={tr.transitions[transIdx].label}
              dv={(tr.rows?.[transIdx] as any)?.[point && point.vac_V >= 180 ? 'dv_hi' : 'dv_lo'] ?? null}
              trec={(tr.rows?.[transIdx] as any)?.[point && point.vac_V >= 180 ? 'trec_hi' : 'trec_lo'] ?? null} />
          </div>
        ) : scene.id === 'steady' && thermal?.available ? (
          <div style={{ marginTop: 12, borderRadius: 8, background: C.bg,
            border: `1px solid ${C.border}`, padding: 8 }}>
            <SteadyStateScene rows={thermal.rows} limits={thermal.limits}
              selectedVac={point?.vac_V ?? 0} />
            <div style={{ marginTop: 10 }}><ChapterSummary ds={ds} /></div>
          </div>
        ) : scene.id === 'schematic' && sch?.available && sch.sheets[sheetKey] ? (
          <div style={{ marginTop: 12, borderRadius: 8, background: C.bg2,
            border: `1px solid ${C.border}`, padding: 8 }}>
            <div style={{ display: 'flex', gap: 8, marginBottom: 8, alignItems: 'center' }}>
              {(['low', 'high'] as const).map(k => (
                <Btn key={k} variant={sheetKey === k ? 'primary' : 'ghost'}
                  onClick={() => setSheetKey(k)}>{sch.sheets[k]?.label ?? k}</Btn>
              ))}
              <div style={{ flex: 1 }} />
              <span style={{ ...mono, fontSize: 10.5, color: C.hint }}>
                {sch.sheets[sheetKey].n_values - sch.sheets[sheetKey].defaulted.length} of{' '}
                {sch.sheets[sheetKey].n_values} values from the engine
                {sch.sheets[sheetKey].defaulted.length > 0
                  ? ` · fixed practice: ${sch.sheets[sheetKey].defaulted.join(', ')}` : ''}
              </span>
            </div>
            <div style={{ background: C.paper, borderRadius: 6, padding: 4, overflowX: 'auto' }}
              dangerouslySetInnerHTML={{ __html: sch.sheets[sheetKey].svg }} />
          </div>
        ) : scene.id === 'capacitor' && capView?.available ? (
          <div style={{ marginTop: 12, borderRadius: 8, background: C.bg,
            border: `1px solid ${C.border}`, padding: 8 }}>
            <CapacitorScene rows={capView.rows} selectedVac={point?.vac_V ?? 0}
              tLimit={Number((ds.chapters.capacitor as any)?.selected?.temp_rating_C) || null} />
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
            {/* C280: BOTH bias points, because one of them alone shows an inductor that does
                not exist. `L_full_nom_uH` is at HALF the line-peak current (the cycle-average
                basis every chapter uses); at the crest the bias is twice as deep and the
                inductance is 46-60 % lower on this design. The swing is the reason the FAN9672
                LS pin cannot be exact everywhere (Section 6.8.2). */}
            <Num label="L_φ (cycle-avg)" value={point.L_full_nom_uH} unit="µH" dp={1} />
            <Num label="L_φ (at crest)"  value={point.L_crest_nom_uH} unit="µH" dp={1} />
            {point.L_full_nom_uH && point.L_crest_nom_uH ? (
              <Num label="crest roll-off"
                   value={100 * (1 - point.L_crest_nom_uH / point.L_full_nom_uH)}
                   unit="%" dp={0} />
            ) : null}
            <Num label="L required"    value={point.L_req_uH}       unit="µH" dp={1} />
            <Num label="k_bias (avg)"  value={point.k_bias}         dp={3} />
            <Num label="k_bias (crest)" value={point.k_bias_crest}  dp={3} />
            <Num label="ΔI_L,pp"       value={point.dIL_pp_A}       unit="A"  dp={2} />
            <Num label="ΔI_in,pp"      value={point.dIin_pp_A}      unit="A"  dp={2} />
            <Num label="D at crest"    value={point.D_crest}        dp={3} />
            <Num label="I_rms"         value={point.Irms_A}         unit="A"  dp={2} />
            <Num label="H (avg)"       value={point.H_Oe}           unit="Oe" dp={1} />
            <Num label="H (at crest)"  value={point.H_Oe_crest}     unit="Oe" dp={1} />
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
