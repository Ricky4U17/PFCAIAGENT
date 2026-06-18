/**
 * CapacitorSimAgent.tsx — DC Bus Capacitor simulation step.
 *
 * Inserted between Step 15 (capacitor approval) and Step 16 (control design).
 * Embeds the self-contained "PFC DC Bus Capacitor — Sim Agent v4" tool
 * (pfc_dcbus_agent_v4.html) as a srcDoc iframe and injects the approved design
 * as window.__DCBUS_PACKAGE__ (schema dcbus-1.2).
 *
 * The left panel shows the PRE-DEFINED specs as read-only constant tiles (DC bus
 * voltage, line frequency, ambient range, selected-capacitor data). Power factor,
 * efficiency, switching frequency and phase count are NOT shown — they are applied
 * automatically by the engine per operating point. The designer explores via the
 * INPUT VOLTAGE, OUTPUT POWER and AMBIENT sliders.
 *
 * Two-band model: the spec is not a free rectangle. Low line (Vac < 180) runs at
 * the low-line power (e.g. 1700 W); high line (≥ 180) at the high-line power
 * (e.g. 3600 W). The OUTPUT-POWER slider follows the band selected by INPUT
 * VOLTAGE, and PF/efficiency follow the band too. The rating verdict is judged at
 * the realistic worst corner (high-line min voltage at rated power, max ambient) —
 * the same corner Step 15 sizes against — not the impossible {VacMin, PoutMax}.
 *
 * Operating values + acceptance limits come from the same backend
 * run_capacitor_design() the Step-15 page uses (design.inputs); capacitor part
 * values come from the approved result.selected_cap. Capacitance is taken at
 * nominal (tol/aging = 0) to stay consistent with how Step 15 sized C_required.
 */
import React, { useEffect, useMemo, useRef, useState } from 'react'
import rawHtml from '../assets/pfc_dcbus_agent_v4.html?raw'
import { C, Btn } from './ui'
import { step15CapacitorDesign, step15CapLifetime } from '../api/client'
import type { CapacitorResult } from './Step15Capacitor'

interface Props {
  result:         CapacitorResult
  confirmedState: Record<string, unknown>
  onBack:         () => void
  onApprove:      () => void
  onRestart:      () => void
}

// Parse a datasheet lifetime string ("5000 h", "8,000 hrs @ 105°C") → hours.
const parseLifeHours = (s?: string): number | null => {
  if (!s) return null
  const m = String(s).match(/([\d,]+)\s*(?:h|hr|hrs|hour)/i)
  if (!m) return null
  const n = parseFloat(m[1].replace(/,/g, ''))
  return Number.isFinite(n) && n > 0 ? n : null
}

export const CapacitorSimAgent: React.FC<Props> = ({
  result, confirmedState, onBack, onApprove, onRestart,
}) => {
  const iframeRef = useRef<HTMLIFrameElement | null>(null)
  const roRef     = useRef<ResizeObserver | null>(null)
  const [design,  setDesign]  = useState<any>(null)
  const [life,    setLife]    = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [error,   setError]   = useState<string | null>(null)

  // Fetch the authoritative operating envelope + acceptance from the backend
  // (same source as the Step-15 page) so the locked specs match upstream.
  useEffect(() => {
    let alive = true
    setLoading(true); setError(null)
    step15CapacitorDesign({ state: confirmedState })
      .then((d: any) => { if (alive) { setDesign(d); setLoading(false) } })
      .catch((e: any) => { if (alive) { setError(String(e)); setLoading(false) } })
    return () => { alive = false }
  }, [confirmedState])

  // Fetch the authoritative Step-15 3-method lifetime (at the worst-corner ambient) so the
  // sim's crude single-point Arrhenius can be calibrated to it — keeping the headline life
  // consistent with the previous page instead of off by an order of magnitude.
  useEffect(() => {
    const cap = result.selected_cap
    if (!cap?.part_number) return
    let alive = true
    step15CapLifetime({
      state: confirmedState,
      part_number: cap.part_number,
      qty: Number(cap.qty ?? 1),
      Tamb_C: Number((confirmedState as any)?.intake?.thermal?.ambient_temp_c_max ?? 50),
    }).then((d: any) => { if (alive) setLife(d) }).catch(() => {})
    return () => { alive = false }
  }, [result, confirmedState])

  // ── Build the dcbus package from upstream design + approved part ────────────
  const pkg = useMemo(() => {
    if (!design) return null
    const app     = (confirmedState as any)?.intake?.application ?? {}
    const thermal = (confirmedState as any)?.intake?.thermal      ?? {}
    const tsi     = (confirmedState as any)?.topology_specific_inputs ?? {}
    const inp     = design.inputs ?? {}
    const cap     = result.selected_cap
    const cfg0    = result.configuration?.[0] ?? {}

    const Vbus    = Number(inp.Vout_V        ?? app.output_bus_voltage_v ?? 393)
    const phases  = Number((confirmedState as any)?.selected_channels ?? 2)
    const PF      = Number(app.power_factor_target ?? 0.99)

    // Two operating ranges (the spec is NOT a free rectangle): low line runs at the
    // low-line power, high line at the high-line power. PF/efficiency follow the band
    // (low-line PFC efficiency is lower than high-line) and are handled in the engine —
    // they are never shown on the GUI.
    const VacMin   = Number(app.vin_rms_min ?? 90)
    const VacMax   = Number(app.vin_rms_max ?? 264)
    const Pout_low = Number(app.output_power_w_low_line  ?? 1700)
    const Pout_hi  = Number(app.output_power_w_high_line ?? 3600)
    const lineBreak = 180                       // Vac < 180 = low line, ≥ 180 = high line
    const highVacMin = VacMax >= 180 ? 180 : Math.max(VacMin, lineBreak)

    // Capacitor part values (from the approved selection)
    const C_uF    = Number(cap?.value_uF         ?? cfg0.value_uF ?? 0)
    const nPar    = Number(cap?.qty              ?? cfg0.qty      ?? 1)
    const Vrated  = Number(cap?.voltage_rating_V ?? result.voltage_rating ?? 450)
    const esr120  = Number(cap?.ESR_each_mohm    ?? 0) / 1000     // mΩ → Ω
    const iRated  = cap?.I_rated_A ?? null
    const tempMaxC  = Number(cap?.temp_rating_C ?? 105)            // rated category max (hotspot limit)
    const lifeTempC = Number(cap?.lifetime_temp_C ?? tempMaxC)    // temp L0 is rated at (Arrhenius ref)
    const Rth       = Number(cap?.Rth_ca_CW ?? 18)               // °C/W from package type (10 snap / 15 radial)
    const rippleHf  = Number(cap?.ripple_hf_A ?? 0)               // rated HF ripple → frequency multiplier
    const freqMult  = (rippleHf > 0 && iRated) ? +(rippleHf / Number(iRated)).toFixed(3) : 1.4
    const L0      = parseLifeHours(cap?.lifetime) ?? 5000

    // Step-15 governing lifetime → calibration anchor for the sim's Arrhenius model.
    const govYears = Number(life?.min_life_years)
    const lifeAnchor_h = govYears > 0 ? govYears * 8760 : null
    const lf = (m: any) => (m && m.life_years != null ? `${Number(m.life_years).toFixed(0)}` : '—')
    const lifeNote = life
      ? `m1 ${lf(life.method1)} · m2 ${lf(life.method2)} · m3 ${lf(life.method3)} yr → governing ${govYears > 0 ? govYears.toFixed(1) : '—'} yr`
      : null

    return {
      schema: 'dcbus-2.0',
      design: { name: `${(confirmedState as any)?.project_id ?? 'PFC'} — approved DC-bus bank`,
                lifeNote, lifeTamb_C: Number(thermal.ambient_temp_c_max ?? 50) },
      operating: {
        // legacy rectangle (kept for the form / plots / slider ranges)
        VacMin_V: VacMin, VacMax_V: VacMax,
        PF, eff: 0.965,                          // fallback only — bands override per point
        fLine_Hz: Number(inp.f_line_Hz ?? app.nominal_line_frequency_hz ?? 60) || 60,
        PoutMin_W: Math.round(Pout_low * 0.2), PoutMax_W: Pout_hi,
        TambMin_C: 25,
        TambMax_C: Number(thermal.ambient_temp_c_max ?? 50),
        Vbus_V:    Vbus,
        phases,
        fsw_Hz:    Number(tsi.recommended_frequency_hz ?? 70000),
        Ihf_A:     null,
        // two-band model (engine reads these; UI never shows PF/eff/fsw/phases)
        lineBreak_V: lineBreak,
        bands: {
          low:  { VacMin_V: VacMin,     VacMax_V: lineBreak, Pout_W: Pout_low, PF, eff: 0.945 },
          high: { VacMin_V: highVacMin, VacMax_V: VacMax,    Pout_W: Pout_hi,  PF, eff: 0.965 },
        },
      },
      bank: {
        nPar, nSer: 1, balanceR_kohm: null, seriesImbalance_pct: 0,
        cap: {
          manufacturer: cap?.supplier ?? result.supplier ?? '—',
          series:       cap?.series   ?? result.series   ?? '',
          part_number:  cap?.part_number ?? cfg0.part_number ?? '—',
          C_uF, Vrated_V: Vrated,
          ESR_120_ohm:  esr120 > 0 ? esr120 : null,
          tanDelta:     null,
          ESR_HF_ohm:   null,            // tool falls back to ESR@120 (conservative)
          rippleRating_A: iRated ?? 0,
          freqMult_HF:  freqMult,        // ripple_hf_A / ripple_120hz_A from the datasheet (DB)
          tempMult:     1.0,
          Rth_CperW:    Rth,             // case-to-ambient from package type (DB), not a fixed guess
          // nominal capacitance basis — consistent with how Step 15 sized C_required
          tol_pct:      0,
          eolAging_pct: 0,
          // T0_C = the temperature L0 is rated at (Arrhenius reference); temp_max_C = category max
          L0_h: L0, T0_C: lifeTempC, temp_max_C: tempMaxC, voltageLifeMult: 1,
          // calibrate the sim's Arrhenius life to the Step-15 governing value (if available)
          ...(lifeAnchor_h ? { lifeAnchor_h } : {}),
        },
      },
      acceptance: {
        Vripple_max_Vpp: Number(inp.Vdc_ripple_V ?? app.dc_bus_voltage_ripple_pk_pk_v ?? 20),
        holdUp_min_ms:   Number(inp.t_hold_ms ?? app.holdup_time_ms ?? app.hold_up_time_ms ?? 20),
        holdUpVmin_V:    Number(inp.Vdc_min_V ?? app.holdup_vmin_v ?? 290),
        // mirrors upstream check (I_per_cap ≤ I_rated); N/A if the part has no rating
        Imargin_min_pct: iRated ? 0 : null,
        Thot_max_C:      tempMaxC,       // cap must stay within its rated category max temp
        // 15-year lifetime gate. The sim's life is calibrated to Step 15's governing 3-method
        // value (via lifeAnchor_h), so this PASS/FAIL is consistent with the upstream verdict.
        life_min_h:      15 * 8760,
        Vderate_max_pct: 90,             // consistent with the 1.12× voltage-derate rule
      },
    }
  }, [design, life, confirmedState, result])

  // ── Assemble the iframe HTML: inject package + lock the inputs ──────────────
  const iframeHtml = useMemo(() => {
    if (!pkg) return ''
    const island =
      '<script type="application/json" id="__dcbuspkg">' +
      JSON.stringify(pkg).replace(/</g, '\\u003c') +
      '<\/script>'
    const setter =
      '<script>try{window.__DCBUS_PACKAGE__=' +
      'JSON.parse(document.getElementById("__dcbuspkg").textContent);}' +
      'catch(e){console.error("dcbus package parse failed",e);}<\/script>'

    // Runs after the tool's own script. Replaces the editable left panel with
    // read-only constant tiles, hides the auto-adjusted parameters (PF / efficiency
    // / fsw / phases), couples the OUTPUT-POWER slider to the line band, and leaves
    // INPUT VOLTAGE, OUTPUT POWER and AMBIENT adjustable.
    const lock = `
<script>
(function () {
  var P = window.__DCBUS_PACKAGE__ || {};
  var op = P.operating || {}, cap = (P.bank && P.bank.cap) || {};
  function num(x, d) { return (x == null || isNaN(x)) ? '—' : (d != null ? Number(x).toFixed(d) : x); }

  function buildTiles() {
    var inputs = document.querySelector('.inputs');
    if (!inputs) return;
    // hide every editable group but KEEP the fields in the DOM — the engine still
    // reads their (injected) values via formToPkg(). PF / efficiency / fsw / phases
    // live inside these hidden groups and are therefore never shown.
    inputs.querySelectorAll('.sec, .grid2, .btns, .hint').forEach(function (el) { el.style.display = 'none'; });
    if (document.getElementById('dcbusTiles')) return;     // build once

    var amb = num(op.TambMin_C) + '–' + num(op.TambMax_C) + ' °C';
    var sec = function (t) { return '<div style="font:600 11px var(--mono);letter-spacing:1.2px;text-transform:uppercase;color:var(--muted);margin:14px 0 8px">' + t + '</div>'; };
    var tile = function (l, v) {
      return '<div style="background:var(--panel2);border:1px solid var(--line);border-radius:9px;padding:8px 10px">' +
        '<div style="font:11px var(--mono);color:var(--muted)">' + l + '</div>' +
        '<div style="font:600 14px var(--mono);color:var(--text);margin-top:3px">' + v + '</div></div>';
    };
    var grid = function (cells) { return '<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px">' + cells.join('') + '</div>'; };

    var html = '<div id="dcbusTiles">';
    html += sec('Operating conditions');
    html += grid([
      tile('DC bus voltage', num(op.Vbus_V, 0) + ' V'),
      tile('Line frequency', num(op.fLine_Hz, 0) + ' Hz'),
      tile('Ambient range', amb),
      tile('Low / high line', num((op.bands && op.bands.low && op.bands.low.Pout_W), 0) + ' / ' + num((op.bands && op.bands.high && op.bands.high.Pout_W), 0) + ' W'),
    ]);
    html += sec('Selected capacitor');
    html += grid([
      tile('Manufacturer', cap.manufacturer || '—'),
      tile('Part number', cap.part_number || '—'),
      tile('Series', cap.series || '—'),
      tile('Value × qty', num(cap.C_uF, 0) + ' µF × ' + num((P.bank && P.bank.nPar), 0)),
      tile('Rated voltage', num(cap.Vrated_V, 0) + ' V'),
      tile('ESR @120 Hz', cap.ESR_120_ohm != null ? num(cap.ESR_120_ohm * 1000, 0) + ' mΩ' : '—'),
      tile('Ripple rating', cap.rippleRating_A ? num(cap.rippleRating_A, 2) + ' A' : '—'),
      tile('Temp rating', num(cap.temp_max_C ?? cap.T0_C, 0) + ' °C'),
      tile('Rated life', num(cap.L0_h, 0) + ' h'),
    ]);
    if (P.design && P.design.lifeNote) {
      html += '<div style="font:11px var(--mono);color:var(--muted);margin-top:12px;line-height:1.6;' +
        'background:var(--panel2);border:1px solid var(--line);border-radius:9px;padding:8px 10px">' +
        '<b style="color:var(--text)">Lifetime 3-method, @' + num(P.design.lifeTamb_C, 0) + ' °C:</b><br>' +
        P.design.lifeNote + '.<br>The simulation life is calibrated to the governing value, then varies ' +
        'with the operating point you select.</div>';
    }
    html += '</div>';

    var wrap = document.createElement('div');
    wrap.innerHTML = html;
    inputs.insertBefore(wrap.firstChild, inputs.firstChild);
  }

  // Power-band coupling (OUTPUT POWER follows INPUT VOLTAGE) is handled natively in
  // the tool's refreshExplore() so it also tracks the auto-play sweep — nothing to do here.
  function start() {
    buildTiles();
    var src = document.getElementById('srcTag');
    if (src) src.style.display = 'none';   // hide the "package: …" source tag entirely
  }
  start();
  setTimeout(start, 200);
})();
<\/script>`

    return rawHtml
      .replace('</head>', island + setter + '</head>')
      .replace('</body>', lock + '</body>')
  }, [pkg])

  // ── Auto-size the iframe to its content (single browser scrollbar) ──────────
  const fitHeight = () => {
    const f = iframeRef.current
    const doc = f?.contentDocument
    if (!f || !doc) return
    const h = Math.max(doc.documentElement?.scrollHeight ?? 0, doc.body?.scrollHeight ?? 0)
    // threshold guard: the tool listens to window.resize → re-render, so avoid a
    // set→resize→set thrash by only updating on a real change.
    if (h > 0 && Math.abs((parseFloat(f.style.height) || 0) - h) > 2) f.style.height = h + 'px'
  }
  const handleLoad = () => {
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

  const cap = result.selected_cap
  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 8, flexWrap: 'wrap' }}>
        <span style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: '.06em',
          color: C.accent, fontWeight: 700 }}>DC Bus Capacitor — Simulation</span>
        {cap && (
          <span style={{ fontSize: 11, fontFamily: 'IBM Plex Mono,monospace', color: C.muted }}>
            {cap.supplier} {cap.series} · {cap.value_uF} µF × {cap.qty} · {cap.voltage_rating_V} V
          </span>
        )}
        <span style={{ marginLeft: 'auto', color: C.hint, fontSize: 10,
          fontFamily: 'IBM Plex Mono,monospace' }}>
          adjust input voltage · output power · ambient
        </span>
      </div>

      {loading && (
        <div style={{ padding: 40, textAlign: 'center', color: C.muted }}>⏳ Loading design specs…</div>
      )}
      {error && (
        <div style={{ fontSize: 12, color: '#c0392b', background: '#fdf2f2',
          border: '1px solid #e8b4b8', borderRadius: 8, padding: '10px 12px' }}>
          ⚠ Could not load capacitor design: {error}
        </div>
      )}

      {iframeHtml && (
        <iframe
          ref={iframeRef}
          onLoad={handleLoad}
          srcDoc={iframeHtml}
          title="PFC DC Bus Capacitor — Sim Agent"
          scrolling="no"
          style={{
            width: '100%', minHeight: 680,
            border: 'none', borderRadius: 10, background: '#0a0f1e', display: 'block',
          }}
          sandbox="allow-scripts allow-same-origin"
        />
      )}

      {/* action bar */}
      <div style={{ display: 'flex', gap: 8, paddingTop: 10, marginTop: 6,
        borderTop: `0.5px solid ${C.border}`, justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ display: 'flex', gap: 8 }}>
          <Btn variant="ghost" onClick={onBack}>← Back to Capacitor</Btn>
          <Btn variant="ghost" onClick={onRestart}>↺ New design</Btn>
        </div>
        <Btn variant="primary" onClick={onApprove}>
          ✓ Approve &amp; Go to Control Design
        </Btn>
      </div>
    </div>
  )
}
