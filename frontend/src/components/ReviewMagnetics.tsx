/**
 * ReviewMagnetics.tsx
 *
 * Embeds "Review Magnetics Data" (PFC Inductor Studio V5.1) as a srcDoc iframe.
 * All four tabs (Overview, Waveform Panes, Voltage Sweep, Design Review Summary)
 * are preserved exactly.
 *
 * Pre-population strategy
 * ────────────────────────
 * The JS studio's cfg, currentMap, and renderAll live inside a self-executing
 * IIFE.  review_magnetics.html now exposes them on window at the end of the
 * IIFE so our inject script can reach them.  All overrides happen AFTER the
 * main script finishes its first render, so the second renderAll() call picks
 * up every corrected value.
 *
 * Fixed vs interactive controls
 * ──────────────────────────────
 * Fixed (hidden from sidebar, pre-populated only):
 *   N, stacks, Icrest (auto-follows Vin), Vout, fsw,
 *   Winding build parameters, Thermal envelope, Live equations sections
 * Interactive (kept visible):
 *   Input voltage (Vin), Temperature, Exploded stack gap, Preset, Loss anchor,
 *   3D view controls, Summary + export
 */
import React, { useMemo, useState } from 'react'
import rawHtml from '../assets/review_magnetics.html?raw'
import { C, Btn } from './ui'
import { step7GenerateReport } from '../api/client'

// OPS table: [Vin_rms, eta, PF] — standard 9-point operating matrix
// Low-line rows use Pout_low; high-line rows use Pout_high
const OPS_ROWS = [
  [ 90, 0.945, 0.9987],
  [110, 0.955, 0.9986],
  [120, 0.965, 0.9985],
  [132, 0.975, 0.9980],
  [180, 0.965, 0.9889],
  [200, 0.975, 0.9884],
  [220, 0.985, 0.9790],
  [230, 0.988, 0.9789],
  [264, 0.990, 0.9520],
] as const

interface Props {
  result:         any
  confirmedState: any
  matType:        string
  selMaterial:    string
  selGrade:       string
  allCandidates:  any[]
  winding:        string
  step8:          any
  onBack:         () => void
  onRestart:      () => void
  onApprove?:     (design: Record<string, unknown>) => void
}

export const ReviewMagnetics: React.FC<Props> = ({
  result, confirmedState, matType, selMaterial, selGrade,
  allCandidates, winding, step8, onBack, onRestart, onApprove,
}) => {
  const [rptLoading, setRptLoad] = useState(false)
  const [rptError,   setRptError] = useState<string | null>(null)

  const iframeHtml = useMemo(() => {
    // ── Extract confirmed design values ────────────────────────────────────
    const tsi      = (confirmedState as any)?.topology_specific_inputs ?? {}
    const app      = (confirmedState as any)?.intake?.application ?? {}
    const n_phases = Number((confirmedState as any)?.selected_channels ?? 2)

    const N          = result.N              ?? 32
    const stacks     = result.stacks         ?? 2
    const Vout       = Number(app.output_bus_voltage_v        ?? 393)
    const fsw        = Number(tsi.recommended_frequency_hz    ?? 70000)
    const fswkHz     = Math.round(fsw / 1000)
    const Pout_low   = Number(app.output_power_w_low_line     ?? 1700)
    const Pout_high  = Number(app.output_power_w_high_line    ?? 3600)

    // Core magnetic constants (single-stack values)
    const AL_single  = result.AL_nom_nH      ?? 122
    const alTotal    = Math.round(AL_single * stacks)
    const Ae_single  = result.Ae_single_mm2  ?? 153
    const Le_mm      = result.Le_single_mm   ?? 94
    const Ve_single  = ((result.Ve_total_cm3 ?? 29.2) / Math.max(stacks, 1)) * 1000  // mm³
    const Wa_single  = result.Wa_single_mm2  ?? 355
    const HT_mm      = result.HT_mm          ?? 17.89
    const OD_mm      = result.OD_mm          ?? 40.9
    const ID_mm      = result.ID_mm          ?? 21.3
    const coreW_mm   = (OD_mm - ID_mm) / 2
    const coreR_mm   = (OD_mm + ID_mm) / 4    // mean radius for 3D model ring
    const Rprime20   = result.R_per_m_20C     ?? 0.006315
    const RacRatio   = result.Rac_Rdc         ?? 1.0
    const satT       = result.Bsat_at_Tcore   ?? 1.0

    // Wire / winding
    const bundleOD   = result.wire_OD_mm          ?? 2.23
    const boreID     = ID_mm
    const woundOD    = result.wound_OD_actual_mm   ?? (OD_mm + 8)
    const htBuild    = Math.max(0.5,
      (result.wound_HT_actual_mm ?? (HT_mm * stacks + bundleOD * 2)) - HT_mm * stacks)
    const passesTotal = N * 2
    const layerCap    = Math.max(1, Math.floor(Math.PI * boreID / bundleOD))
    const layersUsed  = Math.ceil(passesTotal / layerCap)
    const holeID      = Math.max(2, boreID - layersUsed * bundleOD * 2)

    // Display labels
    const partNumber  = result.part_number    ?? '—'
    const wireLabel   = result.wire_designation ?? '—'
    const ffcu        = Math.round((result.FFcu ?? 0) * 100)

    // ── Compute currentMap from actual OPS table ───────────────────────────
    // Icrest_phase = √2 × (Pout/eta) / (Vin × PF) / n_phases
    // Low-line rows (90–132 Vac) use Pout_low; high-line (180–264) use Pout_high
    const currentMapEntries = OPS_ROWS.map(([vin, eta, pf]) => {
      const pout   = vin <= 132 ? Pout_low : Pout_high
      const icrest = Math.sqrt(2) * (pout / eta) / (vin * pf) / n_phases
      return `${vin}:${icrest.toFixed(4)}`
    }).join(',')

    // Initial crest current at 90 Vac
    const [, eta90, pf90] = OPS_ROWS[0]
    const Icrest90 = +(Math.sqrt(2) * (Pout_low / eta90) / (90 * pf90) / n_phases).toFixed(3)

    // ── Mismatch 2: compute material-specific effective Steinmetz 'a' ────────
    // The JS uses hardcoded a=86.7 calibrated for EDGE 75µ. We replace it with
    // a value back-computed from Python's material-specific loss_table_100C:
    //   Pv_mW_cm3 = Pcore_W × 1000 / Ve_cm3
    //   a = Pv_mW_cm3 / (Bac^b × (fsw/1000)^c × F(D))   with b=2.106, c=1.444
    const loss100 = (result.loss_table_100C ?? []) as any[]
    const Ve_cm3  = result.Ve_total_cm3 ?? 29.2
    const b_exp   = 2.106, c_exp = 1.444
    const IGSE_C  = 1.444, IGSE_IC = 3.5435
    const IGSE_K  = Math.pow(2, IGSE_C) / (Math.pow(2 * Math.PI, IGSE_C - 1) * IGSE_IC)
    const FdLocal = (D: number) => {
      D = Math.max(0.02, Math.min(0.98, D))
      return IGSE_K * (Math.pow(D, 1 - IGSE_C) + Math.pow(1 - D, 1 - IGSE_C))
    }
    let a_sum = 0, a_count = 0
    for (const row of loss100) {
      const Pcore = row.Pcore_W ?? 0
      const Bac   = row.Bac_pk  ?? 0
      const D_cr  = row.D_crest ?? 0.5
      if (Pcore > 0 && Bac > 0) {
        const Pv_mW = Pcore * 1000 / Ve_cm3
        const a_row = Pv_mW / (Math.pow(Bac, b_exp) * Math.pow(fsw / 1000, c_exp) * FdLocal(D_cr))
        if (isFinite(a_row) && a_row > 0) { a_sum += a_row; a_count++ }
      }
    }
    const a_effective = a_count > 0 ? +(a_sum / a_count).toFixed(3) : 86.7
    const a_typ       = +(a_effective * 0.85).toFixed(3)   // ~typical = 85% of calibrated max

    // ── Mismatch 1: build k(H) lookup from Python DB (material-specific) ────
    // The JS uses a single empirical formula calibrated to EDGE 75µ, ignoring µ.
    // We replace it with Python's L_vs_Vin_table which has DB k_bias at each H.
    const lvt     = (result.L_vs_Vin_table ?? []) as any[]
    // Anchor: H=0 → k=1.0 (no bias = full inductance)
    const kPairs: [number, number][] = [[0, 1.0]]
    for (const row of lvt) {
      const H_val = row.H_Oe  ?? 0
      const k_val = row.k_bias ?? 1.0
      if (H_val > 0 && k_val > 0 && k_val <= 1.0) kPairs.push([H_val, k_val])
    }
    // Sort ascending by H and deduplicate
    kPairs.sort((a, b) => a[0] - b[0])
    const kTableStr = JSON.stringify(kPairs)

    // ── Inject script ──────────────────────────────────────────────────────
    // Runs after the IIFE finishes. cfg, currentMap, renderAll are now on
    // window (see the patch at the end of review_magnetics.html).
    const inject = `
<script>
(function () {

  /* 1 ── Narrower sidebar so main canvases fill the screen ──────────────── */
  var layout = document.querySelector('.layout');
  if (layout) layout.style.gridTemplateColumns = '240px 1fr';

  /* 2 ── Hide verbose subtitle ─────────────────────────────────────────── */
  var subDiv = document.querySelector('aside .sub');
  if (subDiv) subDiv.style.display = 'none';

  /* 3 ── Compact read-only "Approved Design" summary ───────────────────── */
  var h1el = document.querySelector('aside h1');
  if (h1el) {
    var sd = document.createElement('div');
    sd.style.cssText =
      'background:rgba(56,189,248,.07);border:1px solid rgba(56,189,248,.22);' +
      'border-radius:10px;padding:10px 12px;margin:6px 0 10px;font-size:11px;' +
      'line-height:1.9;color:#cbd5e1;word-break:break-word';
    sd.innerHTML =
      '<div style="color:#38bdf8;font-size:9px;text-transform:uppercase;' +
        'letter-spacing:.06em;font-weight:700;margin-bottom:6px">Approved Design</div>' +
      '<div><span style="color:#9ca3af;display:inline-block;width:82px">Core</span>' +
        '<b>${partNumber}</b> &times;${stacks}</div>' +
      '<div><span style="color:#9ca3af;display:inline-block;width:82px">Turns</span>' +
        'N&nbsp;=&nbsp;<b>${N}</b></div>' +
      '<div><span style="color:#9ca3af;display:inline-block;width:82px">Wire</span>' +
        '${wireLabel}</div>' +
      '<div><span style="color:#9ca3af;display:inline-block;width:82px">AL total</span>' +
        '${alTotal}&nbsp;nH/T&sup2;</div>' +
      '<div><span style="color:#9ca3af;display:inline-block;width:82px">FF<sub>cu</sub></span>' +
        '${ffcu}%</div>' +
      '<div><span style="color:#9ca3af;display:inline-block;width:82px">Vout&nbsp;/&nbsp;fsw</span>' +
        '${Vout}&nbsp;V &middot; ${fswkHz}&nbsp;kHz</div>';
    h1el.insertAdjacentElement('afterend', sd);
  }

  /* 4 ── Helpers ─────────────────────────────────────────────────────────── */
  function hideField(id) {
    var el = document.getElementById(id);
    if (!el) return;
    var g2 = el.closest('.grid2'); if (g2) { g2.style.display = 'none'; return; }
    var g3 = el.closest('.grid3'); if (g3) { g3.style.display = 'none'; return; }
    var f  = el.closest('.field'); if (f)  { f.style.display  = 'none'; return; }
    el.style.display = 'none';
  }
  function hideSection(text) {
    var kids = Array.from(document.querySelector('aside.side').children);
    var hiding = false;
    kids.forEach(function (el) {
      if (el.tagName === 'H2') {
        if (el.textContent.trim().includes(text)) { el.style.display = 'none'; hiding = true; return; }
        if (hiding) hiding = false;
      } else if (hiding) { el.style.display = 'none'; }
    });
  }

  /* 5 ── Hide fixed / derived controls ───────────────────────────────────── */
  hideField('N');
  hideField('stacks');
  Array.from(document.querySelectorAll('aside h2')).forEach(function (el) {
    if (el.textContent.trim() === 'Geometry + winding') el.textContent = 'Exploration controls';
  });
  hideField('Icrest');
  hideField('Vout');      // grid2 hides both Vout and fsw
  hideSection('Winding build parameters');
  hideSection('Thermal envelope');
  hideSection('Live equations');

  /* 6 ── Update footer text ─────────────────────────────────────────────── */
  var footEl = document.querySelector('aside .foot');
  if (footEl) footEl.textContent =
    'Pre-loaded from approved design (${partNumber}, N=${N}\\xd7${stacks} stack). ' +
    'Shaded band = +5\\u202120\\u2009% core-loss uncertainty.';

  /* 7a ── Override retention(H) with Python DB k(H) curve (Mismatch 1) ─────
     The original JS uses a single empirical formula calibrated to EDGE 75µ.
     We replace it with material-specific k(H) from the Python sizing DB
     (linear interpolation over the 9 operating points from L_vs_Vin_table).
     window.retention is now the live function — all compute() calls use it.  */
  var kTable_db = ${kTableStr};
  window.retention = function (H) {
    H = Math.max(0, H);
    if (kTable_db.length === 0) return 1.0;
    if (H <= kTable_db[0][0]) return kTable_db[0][1];
    if (H >= kTable_db[kTable_db.length - 1][0]) return kTable_db[kTable_db.length - 1][1];
    for (var _i = 0; _i < kTable_db.length - 1; _i++) {
      if (H >= kTable_db[_i][0] && H <= kTable_db[_i + 1][0]) {
        var _t = (H - kTable_db[_i][0]) / (kTable_db[_i + 1][0] - kTable_db[_i][0]);
        return kTable_db[_i][1] + _t * (kTable_db[_i + 1][1] - kTable_db[_i][1]);
      }
    }
    return kTable_db[kTable_db.length - 1][1];
  };

  /* 7b ── Override Steinmetz 'a' with material-specific value (Mismatch 2) ─
     The JS uses hardcoded a_max=86.7 calibrated to EDGE 75µ.  We replace
     both lossAnchor options with values back-computed from Python's
     material-specific loss_table_100C so the waveform / sweep plots are
     consistent with what the sizing engine calculated.                       */
  var lossEl = document.getElementById('lossAnchor');
  if (lossEl && lossEl.options.length >= 2) {
    lossEl.options[0].value   = '${a_typ}';
    lossEl.options[0].text    = 'Typical (DB) a = ${a_typ}';
    lossEl.options[1].value   = '${a_effective}';
    lossEl.options[1].text    = 'Max (DB) a = ${a_effective}';
    lossEl.value              = '${a_effective}';   // select the calibrated max
  }
  /* Also update cfg so any code that reads cfg.aTyp / cfg.aMax is consistent */
  cfg.aTyp = ${a_typ};
  cfg.aMax = ${a_effective};

  /* 7 ── Override cfg with selected-design values (now on window) ─────────
     NOTE: cfg is window.cfg thanks to the patch at the end of the IIFE.    */
  cfg.AL_single_nH  = ${AL_single.toFixed(3)};
  cfg.Ae_single_mm2 = ${Ae_single.toFixed(2)};
  cfg.Le_mm         = ${Le_mm.toFixed(2)};
  cfg.Ve_single_mm3 = ${Ve_single.toFixed(1)};
  cfg.Wa_mm2        = ${Wa_single.toFixed(1)};
  cfg.coreHeight_mm = ${HT_mm.toFixed(3)};
  cfg.coreW_mm      = ${coreW_mm.toFixed(3)};
  cfg.coreR_mm      = ${coreR_mm.toFixed(3)};    // mean radius for 3D ring
  cfg.coreOD_mm     = ${OD_mm.toFixed(2)};       // for label text
  cfg.coreID_mm     = ${ID_mm.toFixed(2)};       // for label text
  cfg.coreLabel     = '${partNumber}';           // for stack & label text
  cfg.Rprime20      = ${Rprime20.toFixed(6)};
  cfg.RacRatio      = ${RacRatio.toFixed(4)};
  cfg.Vout          = ${Vout};
  cfg.fsw           = ${fsw};
  cfg.satT          = ${satT.toFixed(3)};

  /* 8 ── Replace currentMap with actual operating-point currents ──────────
     currentMap[Vin] = per-phase Icrest = √2×(Pout/η)/(Vin×PF)/n_phases    */
  var newMap = {${currentMapEntries}};
  Object.keys(newMap).forEach(function (k) { currentMap[+k] = newMap[+k]; });

  /* 9 ── Vin slider: auto-sync Icrest via crestCurrent() ─────────────────
     Clone the element to clear the original listeners, then add one clean
     listener that syncs the display label, the hidden Icrest input, and the
     IcrestVal span before calling renderAll().                              */
  var vinEl = document.getElementById('vin');
  if (vinEl) {
    var newVin = vinEl.cloneNode(true);
    vinEl.parentNode.replaceChild(newVin, vinEl);
    newVin.addEventListener('input', function () {
      var v = +this.value;
      var vd = document.getElementById('vinVal');
      if (vd) vd.textContent = v + ' Vac';
      var ic = crestCurrent(v);
      if (ic !== null) {
        document.getElementById('Icrest').value = ic.toFixed(3);
        var id2 = document.getElementById('IcrestVal');
        if (id2) id2.textContent = ic.toFixed(2) + ' A';
      }
      renderAll();
    });
  }

  /* 10 ── Sync preset dropdown to initial 90 Vac ──────────────────────── */
  var presetEl = document.getElementById('preset');
  if (presetEl) {
    for (var pi = 0; pi < presetEl.options.length; pi++) {
      if (+presetEl.options[pi].value === 90) { presetEl.selectedIndex = pi; break; }
    }
  }

  /* 11 ── Pre-populate all inputs and re-render ───────────────────────── */
  var overrides = {
    N:        ${N},
    stacks:   ${stacks},
    vin:      90,
    Icrest:   ${Icrest90},
    Vout:     ${Vout},
    fsw:      ${fsw},
    tempC:    100,
    boreID:   ${boreID.toFixed(2)},
    bundleOD: ${bundleOD.toFixed(3)},
    woundOD:  ${woundOD.toFixed(1)},
    holeID:   ${holeID.toFixed(1)},
    htBuild:  ${htBuild.toFixed(1)},
  };
  Object.keys(overrides).forEach(function (k) {
    var el = document.getElementById(k);
    if (el) el.value = overrides[k];
  });

  /* 12 ── Re-render with all corrected values ───────────────────────── */
  renderAll();
})();
</script>
`

    let html = rawHtml
    // Rename title and heading
    html = html.replace(
      '<title>PFC Inductor Studio V5.1 — Review Dashboard</title>',
      '<title>Review Magnetics Data</title>'
    )
    html = html.replace(
      '<h1>PFC Inductor Studio V5.1</h1>',
      '<h1>Review Magnetics Data</h1>'
    )
    // Inject script before </body>
    html = html.replace('</body>', inject + '</body>')
    return html
  }, [result, confirmedState])  // eslint-disable-line react-hooks/exhaustive-deps

  // ── Report generation ──────────────────────────────────────────────────
  const handleReport = async () => {
    if (!result || !confirmedState) return
    setRptLoad(true); setRptError(null)
    try {
      const blob = await step7GenerateReport({
        state:           confirmedState as Record<string, unknown>,
        approved_design: {
          ...result,
          material_key:   result.material_key || (matType === 'powder' ? selMaterial : selGrade),
          all_candidates: allCandidates,
        },
      })
      const url = URL.createObjectURL(blob)
      const a   = document.createElement('a')
      a.href = url
      a.download = `PFC_Report_${(confirmedState as any).project_id ?? 'design'}_Steps1_14.pdf`
      document.body.appendChild(a); a.click(); document.body.removeChild(a)
      setTimeout(() => URL.revokeObjectURL(url), 150)
    } catch (e) {
      setRptError((e as Error).message ?? String(e))
      console.error('Report generation failed', e)
    } finally { setRptLoad(false) }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>

      {/* ── iframe: all 4 tabs, full-width ────────────────────────────────── */}
      <iframe
        srcDoc={iframeHtml}
        title="Review Magnetics Data"
        style={{
          width: '100%', height: 'calc(100vh - 175px)', minHeight: 680,
          border: 'none', borderRadius: 10, background: '#08101f', display: 'block',
        }}
        sandbox="allow-scripts allow-same-origin"
      />

      {/* ── Action bar ────────────────────────────────────────────────────── */}
      <div style={{
        display: 'flex', gap: 8, paddingTop: 10, marginTop: 6,
        borderTop: `0.5px solid ${C.border}`,
        justifyContent: 'space-between', alignItems: 'flex-start',
      }}>
        <div style={{ display: 'flex', gap: 8 }}>
          <Btn variant="ghost" onClick={onBack}>← Back to Result</Btn>
          <Btn variant="ghost" onClick={onRestart}>↺ New design</Btn>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 5, alignItems: 'flex-end' }}>
          {rptError && (
            <div style={{ fontSize: 11, color: '#c0392b', background: '#fdf2f2',
              border: '1px solid #e8b4b8', borderRadius: 6, padding: '4px 10px',
              maxWidth: 380, textAlign: 'right' }}>
              ⚠ Report failed: {rptError}
            </div>
          )}
          <div style={{ display: 'flex', gap: 8 }}>
            {step8 && (
              <Btn variant="success" disabled={rptLoading} onClick={handleReport}>
                {rptLoading ? '⏳ Generating report…' : '📄 Generate & Download Report'}
              </Btn>
            )}
            {step8 && onApprove && (
              <Btn variant="primary" onClick={() => onApprove({
                ...result,
                material_key:   result.material_key || (matType === 'powder' ? selMaterial : selGrade),
                all_candidates: allCandidates,
              })}>
                ✓ Approve &amp; Go to Capacitor Sizing
              </Btn>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
