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

// ── magnetics scene: flux against saturation, field, and the loss split ──────
/**
 * B(t) is drawn against the engine's B_sat AT THE CORE TEMPERATURE — not the 25 °C datasheet
 * value, because powder saturation falls with temperature and the 25 °C figure would flatter the
 * margin.
 *
 * NO PER-ANGLE MARGIN NUMBER IS COMPUTED HERE. `sat_margin_pct` has a specific definition in the
 * engine, and the report quotes it on the inner-bore flux while the accept/reject gate still runs
 * on the mean path — PENDING D3, undecided. Deriving a margin per angle in the browser would be
 * inventing a third definition. The gap between the trace and the B_sat line shows the headroom;
 * the numbers come from the export, labelled with their basis.
 */
export const MagneticsScene: React.FC<{
  s: WaveSeries; tNorm: number
  bsat: number | null; bmaxFL: number | null; bInnerFL: number | null
}> = ({ s, tNorm, bsat, bmaxFL, bInnerFL }) => {
  const n = s.t_ms.length
  const i = Math.min(n - 1, Math.max(0, Math.round(tNorm * (n - 1))))
  const W = 700, H = 300
  const bB: Box = { x: 52, y: 8,   w: W - 66, h: 128 }
  const bH: Box = { x: 52, y: 150, w: W - 66, h: 60 }
  const bP: Box = { x: 52, y: 222, w: W - 66, h: 62 }

  const bHi = Math.max(bsat ?? 0, ...(s.Bmax || [0])) * 1.06 || 1
  const pAll = [...(s.Pcore || []), ...(s.Pcu || [])]
  const pHi = Math.max(...pAll, 0.001) * 1.08
  const hHi = Math.max(...(s.H_Oe || [0])) * 1.08 || 1
  const Yb = (v: number) => bB.y + bB.h - (v / bHi) * bB.h
  const cx = (b: Box) => b.x + (i / Math.max(n - 1, 1)) * b.w

  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" height={H} role="img"
      aria-label="Flux density against saturation, magnetising field, and the core/copper loss split over one half line cycle">
      <Axis box={bB} label="B(t) vs B_sat" lo={0} hi={bHi} unit="T" />
      {bsat != null && (
        <>
          <rect x={bB.x} y={bB.y} width={bB.w} height={Math.max(0, Yb(bsat) - bB.y)}
            fill={`${C.red}12`} />
          <line x1={bB.x} y1={Yb(bsat)} x2={bB.x + bB.w} y2={Yb(bsat)}
            stroke={C.red} strokeWidth={1.4} strokeDasharray="5 3" />
          <text x={bB.x + bB.w - 4} y={Yb(bsat) - 5} fill={C.red} fontSize={9.5}
            fontFamily={mono} textAnchor="end">B_sat {bsat.toFixed(3)} T (at T_core)</text>
        </>
      )}
      {bInnerFL != null && (
        <>
          <line x1={bB.x} y1={Yb(bInnerFL)} x2={bB.x + bB.w} y2={Yb(bInnerFL)}
            stroke={C.amber} strokeWidth={1} strokeDasharray="2 4" opacity={0.9} />
          <text x={bB.x + 4} y={Yb(bInnerFL) - 4} fill={C.amber} fontSize={9} fontFamily={mono}>
            B inner-bore {bInnerFL.toFixed(3)} T
          </text>
        </>
      )}
      {bmaxFL != null && (
        <text x={bB.x + 4} y={Yb(bmaxFL) - 4} fill={C.muted} fontSize={9} fontFamily={mono}>
          B mean-path {bmaxFL.toFixed(3)} T
        </text>
      )}
      <path d={path(s.Bmax, bB, 0, bHi, n)} fill="none" stroke={C.teal} strokeWidth={1.6} />

      <Axis box={bH} label="H(t)" lo={0} hi={hHi} unit="Oe" />
      <path d={path(s.H_Oe, bH, 0, hHi, n)} fill="none" stroke={C.accent} strokeWidth={1.3} />

      <Axis box={bP} label="core vs copper loss" lo={0} hi={pHi} unit="W" />
      <path d={path(s.Pcore, bP, 0, pHi, n)} fill="none" stroke={C.amber} strokeWidth={1.3} />
      <path d={path(s.Pcu, bP, 0, pHi, n)} fill="none" stroke={C.green} strokeWidth={1.3} />
      <text x={bP.x + bP.w - 4} y={bP.y + bP.h - 5} fill={C.hint} fontSize={9} fontFamily={mono}
        textAnchor="end">
        <tspan fill={C.amber}>core</tspan> · <tspan fill={C.green}>copper</tspan>
      </text>

      {[bB, bH, bP].map((b, k) => (
        <line key={k} x1={cx(b)} y1={b.y} x2={cx(b)} y2={b.y + b.h}
          stroke={C.text} strokeWidth={1} opacity={0.5} />
      ))}
    </svg>
  )
}

// ── capacitor scene: ripple loading, ESR(T) and case temperature per line point ──
/**
 * Not a timeline — one bar per operating point, from Chapter 5's own bank model.
 *
 * The ESR trace is worth reading beside the temperature: ESR FALLS as the part warms, so the
 * self-heating that drives the temperature is self-limiting. A case rise below 1:1 with ambient is
 * the model working; it has been mistaken for a defect before.
 */
export const CapacitorScene: React.FC<{
  rows: Array<Record<string, number>>; selectedVac: number; tLimit: number | null
}> = ({ rows, selectedVac, tLimit }) => {
  const W = 700, H = 300
  const b: Box = { x: 52, y: 20, w: W - 76, h: 190 }
  const tHi = Math.max(...rows.map(r => r.T_cap_C), tLimit ?? 0) * 1.1 || 1
  const iHi = Math.max(...rows.map(r => r.I_cap_total_A)) * 1.25 || 1
  const bw = b.w / Math.max(rows.length, 1)
  const Yt = (v: number) => b.y + b.h - (v / tHi) * b.h

  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" height={H} role="img"
      aria-label="Capacitor ripple current, case temperature and ESR at each operating point">
      <rect x={b.x} y={b.y} width={b.w} height={b.h} fill="none" stroke={C.border} />
      <text x={b.x + 4} y={b.y - 6} fill={C.muted} fontSize={9.5} fontFamily={mono}>
        bank ripple current (bars) · case temperature (line) · ESR (dashed)
      </text>
      {tLimit != null && (
        <>
          <line x1={b.x} y1={Yt(tLimit)} x2={b.x + b.w} y2={Yt(tLimit)}
            stroke={C.red} strokeWidth={1.3} strokeDasharray="5 3" />
          <text x={b.x + b.w - 4} y={Yt(tLimit) - 5} fill={C.red} fontSize={9.5}
            fontFamily={mono} textAnchor="end">rated {tLimit.toFixed(0)} °C</text>
        </>
      )}
      {rows.map((r, k) => {
        const sel = Math.round(r.Vin_rms) === Math.round(selectedVac)
        const h = (r.I_cap_total_A / iHi) * b.h
        return (
          <g key={k}>
            <rect x={b.x + k * bw + bw * 0.22} y={b.y + b.h - h}
              width={bw * 0.56} height={h}
              fill={sel ? C.accent : `${C.accent}44`} />
            <text x={b.x + k * bw + bw / 2} y={b.y + b.h + 13} fill={sel ? C.text : C.hint}
              fontSize={9} fontFamily={mono} textAnchor="middle">{r.Vin_rms.toFixed(0)}</text>
            <text x={b.x + k * bw + bw / 2} y={b.y + b.h - h - 4} fill={sel ? C.accent : C.hint}
              fontSize={8.5} fontFamily={mono} textAnchor="middle">{r.I_cap_total_A.toFixed(1)}</text>
          </g>
        )
      })}
      <path d={rows.map((r, k) =>
        `${k ? 'L' : 'M'}${(b.x + k * bw + bw / 2).toFixed(1)},${Yt(r.T_cap_C).toFixed(1)}`).join('')}
        fill="none" stroke={C.amber} strokeWidth={1.8} />
      {rows.map((r, k) => (
        <circle key={k} cx={b.x + k * bw + bw / 2} cy={Yt(r.T_cap_C)} r={2.6} fill={C.amber} />
      ))}
      <path d={rows.map((r, k) => {
        const y = b.y + b.h - (r.ESR_per_cap_mohm / (Math.max(...rows.map(q => q.ESR_per_cap_mohm)) * 1.6)) * b.h
        return `${k ? 'L' : 'M'}${(b.x + k * bw + bw / 2).toFixed(1)},${y.toFixed(1)}`
      }).join('')} fill="none" stroke={C.teal} strokeWidth={1.2} strokeDasharray="4 3" />
      <text x={b.x} y={b.y + b.h + 30} fill={C.hint} fontSize={9.5} fontFamily={mono}>
        V_AC · ESR falls as the part warms, so the self-heating that sets the temperature is
        self-limiting — a sub-unity case rise is the model working
      </text>
    </svg>
  )
}

// ── Bode scene: both loops, STATIC (C-5) ────────────────────────────────────
/**
 * NO MARKER SLIDES ALONG THIS PLOT WHILE ANYTHING PLAYS. A frequency response has no time
 * coordinate; animating a dot along it would be meaningless and the first control engineer in the
 * room would say so. The link to the transient is made by annotation — crossover sets the recovery
 * timescale, phase margin decides whether it rings — not by fake motion.
 */
export const BodeScene: React.FC<{
  loop: { name: string; bode: Array<{ vac: number; f: number[]; ogain: number[]; ophase: number[] }>
          points: Array<{ vac: number; fco: number | null; pm: number | null }>
          comp?: Record<string, number> }
  selectedVac: number
}> = ({ loop, selectedVac }) => {
  const W = 700, H = 300
  const b = loop.bode.find(x => Math.round(x.vac) === Math.round(selectedVac)) ?? loop.bode[0]
  const pt = loop.points.find(x => Math.round(x.vac) === Math.round(selectedVac)) ?? loop.points[0]
  if (!b || !b.f.length) return <svg viewBox={`0 0 ${W} ${H}`} width="100%" height={H} />
  const bG: Box = { x: 54, y: 14, w: W - 70, h: 130 }
  const bP: Box = { x: 54, y: 166, w: W - 70, h: 110 }
  const lf = b.f.map(v => Math.log10(Math.max(v, 1e-3)))
  const f0 = lf[0], f1 = lf[lf.length - 1]
  const X = (k: number) => bG.x + ((lf[k] - f0) / (f1 - f0 || 1)) * bG.w
  const gLo = Math.min(...b.ogain), gHi = Math.max(...b.ogain)
  const pLo = Math.min(...b.ophase), pHi = Math.max(...b.ophase)
  const Yg = (v: number) => bG.y + bG.h - ((v - gLo) / (gHi - gLo || 1)) * bG.h
  const Yp = (v: number) => bP.y + bP.h - ((v - pLo) / (pHi - pLo || 1)) * bP.h
  const line = (vals: number[], Y: (v: number) => number) =>
    vals.map((v, k) => `${k ? 'L' : 'M'}${X(k).toFixed(1)},${Y(v).toFixed(1)}`).join('')
  const xco = pt?.fco ? bG.x + ((Math.log10(pt.fco) - f0) / (f1 - f0 || 1)) * bG.w : null

  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" height={H} role="img"
      aria-label={`${loop.name} open-loop gain and phase at ${selectedVac} volts AC`}>
      <rect x={bG.x} y={bG.y} width={bG.w} height={bG.h} fill="none" stroke={C.border} />
      <rect x={bP.x} y={bP.y} width={bP.w} height={bP.h} fill="none" stroke={C.border} />
      <text x={bG.x + 4} y={bG.y + 12} fill={C.muted} fontSize={9.5} fontFamily={mono}>
        {loop.name} — open-loop gain (dB)
      </text>
      <text x={bP.x + 4} y={bP.y + 12} fill={C.muted} fontSize={9.5} fontFamily={mono}>phase (°)</text>
      {gLo < 0 && gHi > 0 && (
        <line x1={bG.x} y1={Yg(0)} x2={bG.x + bG.w} y2={Yg(0)} stroke={C.border2} strokeDasharray="3 3" />
      )}
      {pLo < -180 && pHi > -180 && (
        <line x1={bP.x} y1={Yp(-180)} x2={bP.x + bP.w} y2={Yp(-180)} stroke={C.red}
          strokeWidth={1} strokeDasharray="3 3" opacity={0.7} />
      )}
      <path d={line(b.ogain, Yg)} fill="none" stroke={C.accent} strokeWidth={1.6} />
      <path d={line(b.ophase, Yp)} fill="none" stroke={C.teal} strokeWidth={1.4} />
      {xco != null && (
        <>
          <line x1={xco} y1={bG.y} x2={xco} y2={bP.y + bP.h} stroke={C.green}
            strokeWidth={1.2} strokeDasharray="4 3" />
          <text x={xco + 5} y={bG.y + 26} fill={C.green} fontSize={9.5} fontFamily={mono}>
            f_co {pt!.fco!.toFixed(pt!.fco! < 100 ? 1 : 0)} Hz
          </text>
          {pt?.pm != null && (
            <text x={xco + 5} y={bP.y + 26} fill={C.green} fontSize={9.5} fontFamily={mono}>
              PM {pt.pm.toFixed(1)}°
            </text>
          )}
        </>
      )}
      <text x={bG.x} y={H - 3} fill={C.hint} fontSize={9} fontFamily={mono}>
        {b.f[0].toFixed(b.f[0] < 10 ? 1 : 0)} Hz
      </text>
      <text x={bG.x + bG.w} y={H - 3} fill={C.hint} fontSize={9} fontFamily={mono} textAnchor="end">
        {(b.f[b.f.length - 1] / 1000).toFixed(1)} kHz
      </text>
    </svg>
  )
}

// ── transient scene: the settled three-layer bus panel ───────────────────────
/**
 * THE BAND IS MEASURED ON THE CYCLE-AVERAGE, NOT THE INSTANTANEOUS TRACE. Steady-state 2·f_line
 * ripple (±10 V here) is larger than the ±1 % recovery band (±3.93 V), so drawing an absolute band
 * against the composite trace would show the design permanently out of regulation before any step
 * fires — which is exactly what the reference package does with its own numbers.
 *
 * Three layers: the composite scope view, the cycle-average over it, and the band about the
 * average. t_rec is read on the average, which is also how it is read on a bench.
 */
export const TransientScene: React.FC<{
  t: number[]; trace: number[]; composite: number[]; vout: number; band: number
  tNorm: number; label: string; dv: number | null; trec: number | null
}> = ({ t, trace, composite, vout, band, tNorm, label, dv, trec }) => {
  const W = 700, H = 300
  const b: Box = { x: 58, y: 26, w: W - 76, h: 200 }
  const n = t.length
  if (!n) return <svg viewBox={`0 0 ${W} ${H}`} width="100%" height={H} />
  // the composite comes from the export; the browser never synthesises a waveform (C-8)
  const pad = composite.length
    ? Math.max(0, Math.max(...composite) - Math.min(...composite)) * 0.12
    : Math.abs(Math.max(...trace) - Math.min(...trace)) * 0.2
  const lo = Math.min(vout + Math.min(...trace), ...(composite.length ? composite : [vout])) - pad
  const hi = Math.max(vout + Math.max(...trace), ...(composite.length ? composite : [vout])) + pad
  const Y = (v: number) => b.y + b.h - ((v - lo) / (hi - lo || 1)) * b.h
  const X = (k: number) => b.x + (k / Math.max(n - 1, 1)) * b.w
  const cur = Math.min(n - 1, Math.round(tNorm * (n - 1)))
  const comp = composite

  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" height={H} role="img"
      aria-label={`Bus voltage during a ${label} load step`}>
      <rect x={b.x} y={b.y} width={b.w} height={b.h} fill="none" stroke={C.border} />
      <rect x={b.x} y={Y(vout + band)} width={b.w} height={Math.max(1, Y(vout - band) - Y(vout + band))}
        fill={`${C.green}18`} />
      <line x1={b.x} y1={Y(vout)} x2={b.x + b.w} y2={Y(vout)} stroke={C.border2} strokeDasharray="2 4" />
      <path d={comp.map((v, k) => `${k ? 'L' : 'M'}${X(k).toFixed(1)},${Y(v).toFixed(1)}`).join('')}
        fill="none" stroke={`${C.teal}88`} strokeWidth={1} />
      <path d={trace.map((v, k) => `${k ? 'L' : 'M'}${X(k).toFixed(1)},${Y(vout + v).toFixed(1)}`).join('')}
        fill="none" stroke={C.amber} strokeWidth={2} />
      {trec != null && trec > 0 && (
        <line x1={X(Math.round((trec / (t[n - 1] || 1)) * (n - 1)))} y1={b.y}
          x2={X(Math.round((trec / (t[n - 1] || 1)) * (n - 1)))} y2={b.y + b.h}
          stroke={C.green} strokeWidth={1.2} strokeDasharray="4 3" />
      )}
      <line x1={X(cur)} y1={b.y} x2={X(cur)} y2={b.y + b.h} stroke={C.text} strokeWidth={1} opacity={0.5} />
      <text x={b.x + 4} y={b.y - 8} fill={C.amber} fontSize={10} fontFamily={mono}>
        {label} · Δv {dv != null ? dv.toFixed(1) : '—'} V · t_rec {trec != null ? (trec * 1e3).toFixed(0) : '—'} ms
      </text>
      <text x={b.x + b.w} y={b.y - 8} fill={C.hint} fontSize={9} fontFamily={mono} textAnchor="end">
        band ±{band.toFixed(2)} V on the cycle-average
      </text>
      <text x={b.x} y={b.y + b.h + 14} fill={C.hint} fontSize={9} fontFamily={mono}>
        <tspan fill={C.amber}>cycle-average</tspan> · <tspan fill={C.teal}>composite (avg + 2·f_line ripple)</tspan>
        {' '}· ripple drawn at the full-load spec amplitude — it does not yet scale with the step
      </text>
      <text x={b.x} y={b.y + b.h + 28} fill={C.hint} fontSize={9} fontFamily={mono}>
        small-signal model: no slew limit, no error-amp clamp
      </text>
    </svg>
  )
}

// ── steady state: loss budget and junction temperatures against their limits ──
/**
 * Not a timeline. Two panels per operating point: where the semiconductor watts go, and how much
 * thermal headroom each device has.
 *
 * GATE DRIVE IS SHOWN SEPARATELY AND ON PURPOSE. It belongs in the loss budget but NOT in the
 * thermal path — the gate charge is dissipated in the driver and the gate resistors, not in the
 * channel. Folding it into the FET bar would overstate the junction's heat, and separating it
 * without saying so has caused a 0.1 W reconciliation hunt before.
 */
export const SteadyStateScene: React.FC<{
  rows: Array<Record<string, number>>
  limits: { fet: number | null; diode: number | null; bridge: number | null }
  selectedVac: number
}> = ({ rows, limits, selectedVac }) => {
  const W = 700, H = 300
  const r = rows.find(x => Math.round(x.Vac) === Math.round(selectedVac)) ?? rows[0]
  if (!r) return <svg viewBox={`0 0 ${W} ${H}`} width="100%" height={H} />

  const bL: Box = { x: 52, y: 26, w: 300, h: 120 }
  const parts: Array<[string, number, string]> = [
    ['MOSFET', r.P_FET_total ?? 0, C.accent],
    ['Diode', r.P_DIODE_total ?? 0, C.green],
    ['Bridge', r.P_BRIDGE_total ?? 0, C.amber],
    ['Gate drive', r.P_gate_driver ?? 0, C.teal],
  ]
  const tot = parts.reduce((a, [, v]) => a + v, 0) || 1
  let acc = 0

  const devs: Array<[string, number, number | null]> = [
    ['Tj FET', r.Tj_FET ?? 0, limits.fet],
    ['Tj diode', r.Tj_DIODE ?? 0, limits.diode],
    ['Tj bridge', r.Tj_BRIDGE_top ?? 0, limits.bridge],
    ['T sink', r.T_sink_main ?? 0, null],
  ]
  const tMax = Math.max(...devs.map(([, v, l]) => Math.max(v, l ?? 0))) * 1.08 || 1
  const bT: Box = { x: 400, y: 26, w: 270, h: 120 }

  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" height={H} role="img"
      aria-label={`Loss budget and junction temperatures at ${selectedVac} volts AC`}>
      <text x={bL.x} y={bL.y - 8} fill={C.muted} fontSize={10} fontFamily={mono}>
        semiconductor loss — {tot.toFixed(2)} W total
      </text>
      {parts.map(([lab, v, col], k) => {
        const w = (v / tot) * bL.w
        const x = bL.x + acc
        acc += w
        return (
          <g key={lab}>
            <rect x={x} y={bL.y} width={Math.max(0, w - 1)} height={34} fill={col} />
            <text x={bL.x} y={bL.y + 56 + k * 15} fill={C.muted} fontSize={10} fontFamily={mono}>
              <tspan fill={col}>■</tspan> {lab}
            </text>
            <text x={bL.x + bL.w} y={bL.y + 56 + k * 15} fill={C.text} fontSize={10}
              fontFamily={mono} textAnchor="end">
              {v.toFixed(2)} W · {((v / tot) * 100).toFixed(0)} %
            </text>
          </g>
        )
      })}

      <text x={bT.x} y={bT.y - 8} fill={C.muted} fontSize={10} fontFamily={mono}>
        junction temperature vs limit
      </text>
      {devs.map(([lab, v, lim], k) => {
        const y = bT.y + k * 30
        const wv = (v / tMax) * bT.w
        const over = lim != null && v > lim
        return (
          <g key={lab}>
            <rect x={bT.x} y={y} width={bT.w} height={16} fill={C.bg3} />
            <rect x={bT.x} y={y} width={wv} height={16} fill={over ? C.red : C.green} />
            {lim != null && (
              <line x1={bT.x + (lim / tMax) * bT.w} y1={y - 2}
                x2={bT.x + (lim / tMax) * bT.w} y2={y + 18} stroke={C.red} strokeWidth={1.4} />
            )}
            <text x={bT.x - 6} y={y + 12} fill={C.muted} fontSize={9.5} fontFamily={mono}
              textAnchor="end">{lab}</text>
            <text x={bT.x + bT.w + 4} y={y + 12} fill={over ? C.red : C.text} fontSize={9.5}
              fontFamily={mono}>
              {v.toFixed(0)}{lim != null ? ` / ${lim.toFixed(0)} °C` : ' °C'}
            </text>
          </g>
        )
      })}

      <text x={bL.x} y={H - 26} fill={C.hint} fontSize={9.5} fontFamily={mono}>
        Gate drive is in the budget but NOT in the thermal path — that charge is dissipated in the
      </text>
      <text x={bL.x} y={H - 13} fill={C.hint} fontSize={9.5} fontFamily={mono}>
        driver and the gate resistors, not in the channel. DCM here: {(r['DCM_%'] ?? 0).toFixed(1)} %
      </text>
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
