/**
 * Scene renderers for the Design Explorer. Phase 2 — the power stage.
 *
 * EVERY CURVE HERE IS AN ENGINE ARRAY PLOTTED POINT FOR POINT (ANIMATION_PLAN C-8). Nothing on
 * this canvas is synthesised: no sin(), no duty rebuilt from a voltage ratio, no ripple rebuilt
 * from a scalar inductance. The reference package we reviewed does all three, which on our design
 * means a flat 127 µH where the report has a 134-154 µH bias curve, and clean CCM where this design
 * genuinely runs discontinuous near the high-line zero crossings. If a quantity is missing, it
 * belongs in the export.
 *
 * NOTHING UNMODELLED IS DRAWN (C-9). The engine does not track the DCM ringing phase, and it does
 * not publish a per-angle DCM mask at all — so no region is shaded as DCM here. When the mask
 * exists, `test_design_state_waveforms.py::test_no_per_angle_dcm_mask_is_published_yet` has to be
 * deleted deliberately, which is the prompt to come and use it.
 */
import React, { useMemo } from 'react'
import { C } from './ui'
import type { WaveSeries } from '../api/client'

const mono = 'IBM Plex Mono, monospace'

// ── tiny plotting helpers ────────────────────────────────────────────────────
interface Box { x: number; y: number; w: number; h: number }

function path(pts: number[], box: Box, lo: number, hi: number, n: number): string {
  const span = hi - lo || 1
  return pts.map((v, i) => {
    const x = box.x + (i / Math.max(n - 1, 1)) * box.w
    const y = box.y + box.h - ((v - lo) / span) * box.h
    return `${i ? 'L' : 'M'}${x.toFixed(1)},${y.toFixed(1)}`
  }).join('')
}

function band(mid: number[], half: number[], box: Box, lo: number, hi: number, n: number): string {
  const span = hi - lo || 1
  const Y = (v: number) => box.y + box.h - ((v - lo) / span) * box.h
  const X = (i: number) => box.x + (i / Math.max(n - 1, 1)) * box.w
  const up = mid.map((v, i) => `${i ? 'L' : 'M'}${X(i).toFixed(1)},${Y(v + half[i] / 2).toFixed(1)}`)
  const dn = mid.map((v, i) => `L${X(n - 1 - i).toFixed(1)},${Y(mid[n - 1 - i] - half[n - 1 - i] / 2).toFixed(1)}`)
  return up.join('') + dn.slice(1).join('') + 'Z'
}

const Axis: React.FC<{ box: Box; label: string; lo: number; hi: number; unit: string }> =
({ box, label, lo, hi, unit }) => (
  <>
    <rect x={box.x} y={box.y} width={box.w} height={box.h} fill="none" stroke={C.border} />
    <text x={box.x + 4} y={box.y + 12} fill={C.muted} fontSize={9.5} fontFamily={mono}>{label}</text>
    <text x={box.x + box.w - 4} y={box.y + 12} fill={C.hint} fontSize={9} fontFamily={mono}
      textAnchor="end">{hi.toFixed(hi < 10 ? 2 : 0)} {unit}</text>
    <text x={box.x + box.w - 4} y={box.y + box.h - 4} fill={C.hint} fontSize={9} fontFamily={mono}
      textAnchor="end">{lo.toFixed(lo < 10 ? 2 : 0)}</text>
  </>
)

// ── line-cycle scene ─────────────────────────────────────────────────────────
export const LineCycleScene: React.FC<{ s: WaveSeries; tNorm: number; nch: number }> =
({ s, tNorm, nch }) => {
  const n = s.t_ms.length
  const i = Math.min(n - 1, Math.max(0, Math.round(tNorm * (n - 1))))
  const W = 700, H = 300

  const ranges = useMemo(() => {
    const pad = (a: number[], f = 0.08) => {
      const lo = Math.min(...a), hi = Math.max(...a), d = (hi - lo) * f || 1
      return [lo - d, hi + d] as [number, number]
    }
    const iHi = Math.max(...s.Iavg.map((v, k) => v + s.dIpp[k] / 2))
    const iLo = Math.min(...s.Iavg.map((v, k) => v - s.dIpp[k] / 2))
    return { v: pad(s.Vin), i: [Math.min(iLo, 0), iHi * 1.08] as [number, number], d: pad(s.D) }
  }, [s])

  // contiguous runs of the engine's DCM flag, so each becomes one shaded band
  const { dcmSpans, dcmCount } = useMemo(() => {
    const m = s.dcm || []
    const spans: [number, number][] = []
    let start = -1
    m.forEach((f, k) => {
      if (f && start < 0) start = k
      if (!f && start >= 0) { spans.push([start, k - 1]); start = -1 }
    })
    if (start >= 0) spans.push([start, m.length - 1])
    return { dcmSpans: spans, dcmCount: m.filter(Boolean).length }
  }, [s])

  const bV: Box = { x: 46, y: 8,   w: W - 60, h: 84 }
  const bI: Box = { x: 46, y: 104, w: W - 60, h: 104 }
  const bD: Box = { x: 46, y: 220, w: W - 60, h: 64 }
  const cx = (b: Box) => b.x + (i / Math.max(n - 1, 1)) * b.w

  // second phase: the same series shifted half a switching period is NOT drawn — interleaving
  // cancellation is an input-side effect and belongs with the input-ripple work, not a fake
  // second trace here.
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" height={H} role="img"
      aria-label="Input voltage, per-phase inductor current with ripple envelope, and duty cycle over one half line cycle">
      <Axis box={bV} label="v_in(t)" lo={ranges.v[0]} hi={ranges.v[1]} unit="V" />
      <path d={path(s.Vin, bV, ranges.v[0], ranges.v[1], n)} fill="none" stroke={C.teal} strokeWidth={1.4} />

      <Axis box={bI} label={`i_φ(t) — per phase, ×${nch} phases`} lo={ranges.i[0]} hi={ranges.i[1]} unit="A" />
      {/* DCM: exactly the angles the MAGNETICS engine flagged (C259). Shaded, never inferred —
          and the basis is labelled, because Chapter 7's loss engine reports a different DCM
          fraction for the same design and the two must not be presented as one number. */}
      {dcmSpans.map(([a, b], k) => (
        <rect key={k} x={bI.x + (a / (n - 1)) * bI.w} y={bI.y}
          width={Math.max(1.5, ((b - a + 1) / (n - 1)) * bI.w)} height={bI.h}
          fill={`${C.amber}22`} stroke="none" />
      ))}
      <path d={band(s.Iavg, s.dIpp, bI, ranges.i[0], ranges.i[1], n)} fill={`${C.accent}33`} stroke="none" />
      <path d={path(s.Iavg, bI, ranges.i[0], ranges.i[1], n)} fill="none" stroke={C.accent} strokeWidth={1.5} />
      {dcmSpans.length > 0 && (
        <text x={bI.x + 4} y={bI.y + bI.h - 5} fill={C.amber} fontSize={9} fontFamily={mono}>
          DCM {((dcmCount / n) * 100).toFixed(1)} % of the half cycle — magnetics-engine basis
        </text>
      )}

      <Axis box={bD} label="D(t)" lo={ranges.d[0]} hi={ranges.d[1]} unit="" />
      <path d={path(s.D, bD, ranges.d[0], ranges.d[1], n)} fill="none" stroke={C.green} strokeWidth={1.4} />

      {/* where the ripple actually peaks — not the crest, and worth marking */}
      {[bI].map((b, k) => (
        <line key={k} x1={b.x + (s.summary.i_dIpp_max / (n - 1)) * b.w} y1={b.y}
          x2={b.x + (s.summary.i_dIpp_max / (n - 1)) * b.w} y2={b.y + b.h}
          stroke={C.amber} strokeWidth={1} strokeDasharray="3 3" opacity={0.8} />
      ))}
      <text x={bI.x + (s.summary.i_dIpp_max / (n - 1)) * bI.w + 4} y={bI.y + 24}
        fill={C.amber} fontSize={9} fontFamily={mono}>ΔI max</text>

      {[bV, bI, bD].map((b, k) => (
        <line key={k} x1={cx(b)} y1={b.y} x2={cx(b)} y2={b.y + b.h} stroke={C.text} strokeWidth={1} opacity={0.55} />
      ))}
    </svg>
  )
}

// ── switching-period inset ───────────────────────────────────────────────────
/** The triangle at the selected line angle, built from the engine's own i_avg, ΔI_pp and D.
 *  Straight ramps only: the model is piecewise-linear and drawing curvature would be inventing it. */
export const SwitchingScene: React.FC<{ s: WaveSeries; tNorm: number; fsw: number }> =
({ s, tNorm, fsw }) => {
  const n = s.t_ms.length
  const i = Math.min(n - 1, Math.max(0, Math.round(tNorm * (n - 1))))
  const d = s.D[i], iavg = s.Iavg[i], dipp = s.dIpp[i]
  const W = 700, H = 300
  const b: Box = { x: 52, y: 30, w: W - 70, h: 200 }
  const lo = Math.max(0, iavg - dipp), hi = iavg + dipp * 0.9 || 1
  const Y = (v: number) => b.y + b.h - ((v - lo) / (hi - lo || 1)) * b.h
  const xOn = b.x + d * b.w
  const iOn = iavg - dipp / 2, iOff = iavg + dipp / 2

  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" height={H} role="img"
      aria-label="Inductor current over one switching period at the selected line angle">
      <rect x={b.x} y={b.y} width={b.w} height={b.h} fill="none" stroke={C.border} />
      <rect x={b.x} y={b.y} width={d * b.w} height={b.h} fill={`${C.accent}18`} />
      <text x={b.x + 6} y={b.y - 8} fill={C.accent} fontSize={10} fontFamily={mono}>
        Q on — inductor charging (D = {d.toFixed(3)})
      </text>
      <text x={xOn + 6} y={b.y - 8} fill={C.green} fontSize={10} fontFamily={mono}>
        Q off — diode conducting
      </text>
      <line x1={xOn} y1={b.y} x2={xOn} y2={b.y + b.h} stroke={C.border2} strokeDasharray="3 3" />
      <path d={`M${b.x},${Y(iOn)} L${xOn},${Y(iOff)} L${b.x + b.w},${Y(iOn)}`}
        fill="none" stroke={C.accent} strokeWidth={2} />
      <line x1={b.x} y1={Y(iavg)} x2={b.x + b.w} y2={Y(iavg)} stroke={C.muted}
        strokeWidth={1} strokeDasharray="2 4" />
      <text x={b.x - 6} y={Y(iavg) + 3} fill={C.muted} fontSize={9} fontFamily={mono} textAnchor="end">
        {iavg.toFixed(2)} A
      </text>
      <text x={b.x - 6} y={Y(iOff) + 3} fill={C.hint} fontSize={9} fontFamily={mono} textAnchor="end">
        {iOff.toFixed(2)}
      </text>
      <text x={b.x - 6} y={Y(iOn) + 3} fill={C.hint} fontSize={9} fontFamily={mono} textAnchor="end">
        {iOn.toFixed(2)}
      </text>
      <text x={b.x} y={b.y + b.h + 16} fill={C.hint} fontSize={9.5} fontFamily={mono}>
        one period = {(1e6 / fsw).toFixed(2)} µs · ΔI_pp {dipp.toFixed(2)} A · at t = {s.t_ms[i].toFixed(2)} ms
      </text>
      {iOn <= 0 && (
        <text x={b.x + b.w} y={b.y + b.h + 16} fill={C.amber} fontSize={9.5} fontFamily={mono} textAnchor="end">
          valley at/below zero — engine publishes no DCM mask, so none is drawn
        </text>
      )}
    </svg>
  )
}

// ── power-stage schematic with conduction highlighting ───────────────────────
/** Which device carries the current depends only on where we are inside the switching period,
 *  which the caller derives from the engine's duty at this line angle. */
export const PowerStageSchematic: React.FC<{ qOn: boolean; nch: number; vac: number }> =
({ qOn, nch, vac }) => {
  const on = C.accent, off = C.border2
  const W = 700, H = 190
  const wire = (d: string, live: boolean, k?: string) => (
    <path key={k} d={d} fill="none" stroke={live ? on : C.border2} strokeWidth={live ? 2.2 : 1.3} />
  )
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" height={H} role="img"
      aria-label={`Power stage, ${qOn ? 'switch conducting' : 'diode conducting'}`}>
      <text x={8} y={14} fill={C.muted} fontSize={10} fontFamily={mono}>{vac.toFixed(0)} V AC</text>
      {/* bridge */}
      <rect x={40} y={40} width={70} height={70} fill={C.bg3} stroke={C.border} rx={4} />
      <text x={75} y={80} fill={C.muted} fontSize={10} fontFamily={mono} textAnchor="middle">BR</text>
      {wire('M8,60 L40,60', true)}{wire('M8,90 L40,90', true)}
      {/* phases */}
      {Array.from({ length: Math.max(1, nch) }).map((_, p) => {
        const y = 55 + p * 46
        return (
          <g key={p}>
            {wire(`M110,${y} L170,${y}`, true)}
            <rect x={170} y={y - 9} width={44} height={18} fill={C.bg4} stroke={C.border} rx={3} />
            <text x={192} y={y + 4} fill={C.text} fontSize={9.5} fontFamily={mono} textAnchor="middle">L{p + 1}</text>
            {wire(`M214,${y} L300,${y}`, true)}
            {/* diode leg — conducts when the switch is off */}
            {wire(`M300,${y} L380,${y}`, !qOn)}
            <polygon points={`320,${y - 7} 336,${y} 320,${y + 7}`} fill={!qOn ? C.green : off} />
            <line x1={336} y1={y - 7} x2={336} y2={y + 7} stroke={!qOn ? C.green : off} strokeWidth={2} />
            <text x={328} y={y - 12} fill={!qOn ? C.green : C.hint} fontSize={9} fontFamily={mono}
              textAnchor="middle">D{p + 1}</text>
            {/* switch leg — conducts when on */}
            {wire(`M300,${y} L300,${y + 24}`, qOn)}
            <rect x={288} y={y + 24} width={24} height={16} fill={qOn ? `${C.accent}33` : C.bg3}
              stroke={qOn ? on : off} rx={2} />
            <text x={300} y={y + 36} fill={qOn ? on : C.hint} fontSize={9} fontFamily={mono}
              textAnchor="middle">Q{p + 1}</text>
            {wire(`M300,${y + 40} L300,${152}`, qOn)}
          </g>
        )
      })}
      {/* bus */}
      {wire('M380,55 L380,152', true)}{wire('M380,55 L470,55', true)}
      <line x1={455} y1={70} x2={495} y2={70} stroke={C.amber} strokeWidth={2.5} />
      <line x1={455} y1={80} x2={495} y2={80} stroke={C.amber} strokeWidth={2.5} />
      {wire('M475,55 L475,70', true)}{wire('M475,80 L475,152', true)}
      <text x={505} y={78} fill={C.amber} fontSize={10} fontFamily={mono}>C_bus</text>
      {wire('M475,55 L600,55', true)}
      <rect x={600} y={45} width={62} height={44} fill={C.bg3} stroke={C.border} strokeDasharray="4 3" rx={4} />
      <text x={631} y={64} fill={C.hint} fontSize={9} fontFamily={mono} textAnchor="middle">LOAD</text>
      <text x={631} y={78} fill={C.hint} fontSize={8} fontFamily={mono} textAnchor="middle">(later)</text>
      {wire('M662,67 L676,67 L676,152 L40,152 L40,110', true)}
      <text x={8} y={175} fill={qOn ? on : C.green} fontSize={10} fontFamily={mono}>
        {qOn ? '● switch conducting — inductor charging from the line'
             : '● diode conducting — inductor discharging into the bus'}
      </text>
    </svg>
  )
}
