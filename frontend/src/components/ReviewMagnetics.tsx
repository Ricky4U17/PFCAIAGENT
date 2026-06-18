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
 *   Winding build parameters, Thermal envelope, Live equations,
 *   3D view controls, Summary + export sections
 * Interactive (kept visible):
 *   Input voltage (Vin), Temperature, Preset, Loss anchor
 */
import React, { useEffect, useMemo, useRef, useState } from 'react'
import rawHtml from '../assets/review_magnetics.html?raw'
import { C, Btn } from './ui'
import { docGenerateReport, simulateCrossCheck, getViewContract,
         type SimCrossCheck, type ViewContract } from '../api/client'

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
  onSimAgent?:    () => void
  onApprove?:     (design: Record<string, unknown>) => void
}

export const ReviewMagnetics: React.FC<Props> = ({
  result, confirmedState, matType, selMaterial, selGrade,
  allCandidates, winding, step8, onBack, onRestart, onSimAgent, onApprove,
}) => {
  const [rptLoading, setRptLoad] = useState(false)
  const [rptError,   setRptError] = useState<string | null>(null)
  const [simLoading, setSimLoad] = useState(false)
  const [simError,   setSimError] = useState<string | null>(null)
  const [simResult,  setSimResult] = useState<SimCrossCheck | null>(null)
  // Phase C: step7 per-Vin waveform contract, posted into the studio so its charts render
  // step7's authoritative arrays (gated in the studio → no effect if this never arrives).
  const iframeRef = useRef<HTMLIFrameElement | null>(null)
  const roRef = useRef<ResizeObserver | null>(null)
  const [contract, setContract] = useState<ViewContract | null>(null)

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
    const bundleOD   = Number(result.bundle_OD_computed_mm ?? result.wire_OD_mm ?? 2.23)
    const boreID     = ID_mm
    const woundOD    = result.wound_OD_actual_mm   ?? (OD_mm + 8)
    const htBuild    = Math.max(0.5,
      (result.wound_HT_actual_mm ?? (HT_mm * stacks + bundleOD * 2)) - HT_mm * stacks)
    // v10 layer count from Python (bore_hole_r_mm is residual radius after all layers)
    const pyNpar      = winding === 'bifilar' ? 2 : winding === 'trifilar' ? 3 : 1
    const passesTotal = N * pyNpar
    const layerCap    = Math.max(1, Math.floor(2 * Math.PI * Math.max(boreID / 2 - bundleOD / 2, bundleOD / 2) / bundleOD))
    const layersUsed  = result.layers_needed ?? Math.ceil(passesTotal / layerCap)
    const holeID      = result.bore_hole_r_mm > 0
      ? Math.max(1, result.bore_hole_r_mm * 2)
      : Math.max(2, boreID - layersUsed * bundleOD * 2)

    // Display labels
    const partNumber  = result.part_number    ?? '—'
    const wireLabel   = result.wire_designation ?? '—'
    const ffcu        = Math.round((result.FFcu ?? 0) * 100)

    // ── Python-authoritative values for KPI / canvas / audit overrides ─────
    // The JS studio computes L, Pcore, Ptotal, dT with analytical approximations
    // (single-point Steinmetz, sinusoidal I). These are the rigorous values from
    // the Python sizing engine — always shown instead of JS-computed numbers.
    const pyL0_uH       = result.L0_nom_uH         ?? 0
    const pyLfull_uH    = result.L_full_load_uH     ?? 0   // enrichResult: L_vs_Vin @ 90V
    const pyH_Oe        = result.H_Oe_design        ?? 0
    const pyK           = result.kbias ?? (result.kreq_nom ?? 1.0)
    const pyBacPk_T     = result.Bac_pk_T           ?? 0
    const pyDCR_100_mOhm = result.DCR_100C_mOhm     ?? 0
    const pyPcore_W     = result.Pcore_W             ?? 0
    const pyPtot_100_W  = result.Ptotal_100C_W       ?? 0
    const pyDT_C        = result.dT_rise_C           ?? 0
    const pyBmax_T      = result.Bmax_FL_T           ?? 0

    // ── v10 Phase 1 new fields ─────────────────────────────────────────────
    const pyDT_core_C    = Number(result.dT_core_C              ?? 0)
    const pyDT_wdg_C     = Number(result.dT_wdg_C               ?? 0)
    const pyDT_hotspot_C = Number(result.dT_hotspot_C            ?? 0)
    const pyT_hotspot_C  = Number(result.T_hotspot_C             ?? 0)
    const pyBmax_inner   = Number(result.Bmax_inner_FL_T         ?? 0)
    const pySatInner_pct = Number(result.sat_margin_inner_pct    ?? 0)
    const pyMLT_v10_mm   = Number(result.MLT_v10_mm              ?? 0)
    const pyLeadMm       = Number(result.lead_length_mm          ?? 150)
    const pyCuArea_mm2   = Number(result.Cu_area_mm2             ?? 3.14)
    // ── Additional Python-authoritative values for overview table overrides ──
    const pyCuLen_m      = Number(result.Cu_length_m             ?? 0)
    const pyIhf_rms_A    = Number(result.Ihf_rms_A               ?? 0)
    const pyPac_W        = Number(result.Pac_W                   ?? 0)
    const pyJ_A_mm2      = Number(result.J_A_mm2                 ?? 0)
    const pyKu           = Number(result.Ku                      ?? 0)
    const pyPuncLo_W     = Number(result.P_unc_lo_W              ?? 0)
    const pyPuncHi_W     = Number(result.P_unc_hi_W              ?? 0)


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
    // ── Anchor the analytical loss model to the rigorous waveform result ─────
    // _build_loss_table (sweepData) and the JS Steinmetz model are single-point
    // analytical estimates; the Result page Pcore_W / Pcu_100C_W come from the
    // 360-point time-domain waveform model (the authoritative numbers). Anchor
    // both the KPI/overlay/sweep losses AND the JS chart 'a' coefficient so the
    // design point (90 V / 100 °C) equals the Result page exactly, with the
    // per-Vin shape following the analytical table.
    const lossAt90    = loss100.find((r: any) => Math.abs(Number(r.Vin_rms) - 90) < 1) ?? loss100[0]
    const ltPcore90   = lossAt90 ? Number(lossAt90.Pcore_W) : 0
    const ltPcu90     = lossAt90 ? Number(lossAt90.Pcu_W)   : 0
    const pcoreAnchor = (ltPcore90 > 0 && result.Pcore_W)    ? (result.Pcore_W    / ltPcore90) : 1
    const pcuAnchor   = (ltPcu90   > 0 && result.Pcu_100C_W) ? (result.Pcu_100C_W / ltPcu90)   : 1

    const a_effective = a_count > 0 ? +((a_sum / a_count) * pcoreAnchor).toFixed(3) : 86.7
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

    // ── Build Python iGSE sweep data for sweep-table override ────────────────
    // Joins loss_table_100C with L_vs_Vin_table (by Vin_rms) to produce one
    // authoritative row per operating point — replaces JS Steinmetz sweep table.
    const sweepRows = loss100.map((row: any) => {
      const vin = Number(row.Vin_rms ?? 0)
      const lvtRow = lvt.find((r: any) => Math.abs(Number(r.Vin_rms) - vin) < 0.5)
      return {
        Vin:    vin,
        Icrest: Number(lvtRow?.Iavg_crest ?? lvtRow?.Ipk_line ?? 0),
        Lfull:  Number(lvtRow?.L_full_nom_uH ?? 0),
        H:      Number(lvtRow?.H_Oe   ?? 0),     // per-Vin magnetizing force (Python)
        k:      Number(lvtRow?.k_bias ?? 1),     // per-Vin retention k(H)  (Python)
        Bac:    Number(row.Bac_pk   ?? 0),
        Pcore:  Number(row.Pcore_W  ?? 0),
        Pcu:    Number(row.Pcu_W    ?? 0),
        Ptot:   Number(row.Ptotal_W ?? 0),
      }
    })

    // ── Per-Vin current map as a plain object (for the data island) ──────────
    const currentMapObj: Record<string, number> = {}
    OPS_ROWS.forEach(([vin, eta, pf]) => {
      const pout = vin <= 132 ? Pout_low : Pout_high
      currentMapObj[String(vin)] = +(Math.sqrt(2) * (pout / eta) / (vin * pf) / n_phases).toFixed(4)
    })

    // ── Single Python-authoritative payload ─────────────────────────────────
    // Every value the inject needs crosses the TS→iframe boundary through ONE
    // JSON.stringify (guaranteed-valid JS). The inject script reads PY.* only;
    // NO value is ever substituted into executable JS, so a value can never
    // produce a SyntaxError. (Root-cause fix for the recurring about:srcdoc
    // "Invalid or unexpected token" error.)
    const PY = {
      N, stacks, Vout, fsw, fswkHz, Icrest90, alTotal, ffcu,
      partNumber, wireLabel,
      AL_single, Ae_single, Le_mm, Ve_single, Wa_single, HT_mm, coreW_mm,
      coreR_mm, OD_mm, ID_mm, Rprime20, RacRatio, satT, pyLeadMm, pyCuArea_mm2,
      pyNpar, boreID, bundleOD, woundOD, holeID, htBuild,
      a_typ, a_effective, pcoreAnchor, pcuAnchor,
      pyL0_uH, pyLfull_uH, pyH_Oe, pyK, pyBacPk_T, pyDCR_100_mOhm, pyPcore_W,
      pyPtot_100_W, pyDT_C, pyBmax_T, pyT_hotspot_C, pyDT_core_C, pyDT_wdg_C,
      pyBmax_inner, pySatInner_pct, pyMLT_v10_mm, pyCuLen_m, pyIhf_rms_A,
      pyPac_W, pyJ_A_mm2, pyKu, pyPuncLo_W, pyPuncHi_W,
      kTable: kPairs, sweepData: sweepRows, currentMap: currentMapObj,
    }

    // Data island: guaranteed-valid JSON; '<' escaped so a string value can
    // never close the <script> early.
    const dataIsland =
      '<script type="application/json" id="pyReviewData">' +
      JSON.stringify(PY).replace(/</g, '\\u003c') +
      '<\/script>'

    // ── Inject script ──────────────────────────────────────────────────────
    // Runs after the IIFE finishes. cfg, currentMap, renderAll are now on
    // window (see the patch at the end of review_magnetics.html).
    const inject = `
${dataIsland}
<script>
var PY = JSON.parse(document.getElementById('pyReviewData').textContent);
console.log("[inject] N=" + PY.N + " stacks=" + PY.stacks + " Pcore=" + PY.pyPcore_W.toFixed(3) + "W L0=" + PY.pyL0_uH.toFixed(1) + "uH");
(function () {
  /* Safe string variables — JSON.stringify escapes quotes, newlines, backslashes */
  var _pn = PY.partNumber;
  var _wl = PY.wireLabel;


  /* 1 ── Narrower sidebar so main canvases fill the screen ──────────────── */
  var layout = document.querySelector('.layout');
  if (layout) layout.style.gridTemplateColumns = '240px 1fr';

  /* 2 ── Hide verbose subtitle ─────────────────────────────────────────── */
  var subDiv = document.querySelector('aside .sub');
  if (subDiv) subDiv.style.display = 'none';

  /* 3b ── Compact read-only "Approved Design" summary ───────────────────── */
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
        '<b>' + _pn + '</b> &times;' + PY.stacks + '</div>' +
      '<div><span style="color:#9ca3af;display:inline-block;width:82px">Turns</span>' +
        'N&nbsp;=&nbsp;<b>' + PY.N + '</b></div>' +
      '<div><span style="color:#9ca3af;display:inline-block;width:82px">Wire</span>' +
        _wl + '</div>' +
      '<div><span style="color:#9ca3af;display:inline-block;width:82px">AL total</span>' +
        PY.alTotal + '&nbsp;nH/T&sup2;</div>' +
      '<div><span style="color:#9ca3af;display:inline-block;width:82px">FF<sub>cu</sub></span>' +
        PY.ffcu + '%</div>' +
      '<div><span style="color:#9ca3af;display:inline-block;width:82px">Vout&nbsp;/&nbsp;fsw</span>' +
        PY.Vout + '&nbsp;V &middot; ' + PY.fswkHz + '&nbsp;kHz</div>';
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
  hideSection('3D view controls');
  hideSection('Summary + export');

  /* 5b ── Remove export/summary toolbars, captions and the status line (designer) ──
     Elements are HIDDEN (not removed) so the studio's onclick wiring never hits a null. */
  ['.toolbar', '.export-grid'].forEach(function (sel) {
    Array.prototype.forEach.call(document.querySelectorAll(sel), function (el) { el.style.display = 'none'; });
  });
  var _rs = document.getElementById('reviewStatus'); if (_rs) _rs.style.display = 'none';
  Array.prototype.forEach.call(document.querySelectorAll('.tiny, h3'), function (el) {
    var t = (el.textContent || '');
    if (t.indexOf('Titles deliberately match') >= 0 || t.trim() === 'Generate design review summary')
      el.style.display = 'none';
  });

  /* 6 ── Remove the footer note ─────────────────────────────────────────── */
  var footEl = document.querySelector('aside .foot');
  if (footEl) footEl.style.display = 'none';

  /* 7a ── Override retention(H) with Python DB k(H) curve (Mismatch 1) ─────
     The original JS uses a single empirical formula calibrated to EDGE 75µ.
     We replace it with material-specific k(H) from the Python sizing DB
     (linear interpolation over the 9 operating points from L_vs_Vin_table).
     window.retention is now the live function — all compute() calls use it.  */
  var kTable_db = PY.kTable;
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
    lossEl.options[0].value   = String(PY.a_typ);
    lossEl.options[0].text    = 'Typical (DB) a = ' + PY.a_typ;
    lossEl.options[1].value   = String(PY.a_effective);
    lossEl.options[1].text    = 'Max (DB) a = ' + PY.a_effective;
    lossEl.value              = String(PY.a_effective);   // select the calibrated max
  }
  /* Also update cfg so any code that reads cfg.aTyp / cfg.aMax is consistent */
  cfg.aTyp = PY.a_typ;
  cfg.aMax = PY.a_effective;

  /* 7 ── Override cfg with selected-design values (now on window) ─────────
     NOTE: cfg is window.cfg thanks to the patch at the end of the IIFE.    */
  cfg.AL_single_nH  = PY.AL_single;
  cfg.Ae_single_mm2 = PY.Ae_single;
  cfg.Le_mm         = PY.Le_mm;
  cfg.Ve_single_mm3 = PY.Ve_single;
  cfg.Wa_mm2        = PY.Wa_single;
  cfg.coreHeight_mm = PY.HT_mm;
  cfg.coreW_mm      = PY.coreW_mm;
  cfg.coreR_mm      = PY.coreR_mm;    // mean radius for 3D ring
  cfg.coreOD_mm     = PY.OD_mm;       // for label text
  cfg.coreID_mm     = PY.ID_mm;       // for label text
  cfg.coreLabel     = _pn;            // for stack & label text
  cfg.Rprime20      = PY.Rprime20;
  cfg.RacRatio      = PY.RacRatio;
  cfg.Vout          = PY.Vout;
  cfg.fsw           = PY.fsw;
  cfg.satT          = PY.satT;
  cfg.leadMm        = PY.pyLeadMm;
  cfg.CuArea_mm2    = PY.pyCuArea_mm2;
  cfg.nParallel     = PY.pyNpar;

  /* 8 ── Replace currentMap with actual operating-point currents ──────────
     currentMap[Vin] = per-phase Icrest = √2×(Pout/η)/(Vin×PF)/n_phases    */
  var newMap = PY.currentMap;
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
    N:        PY.N,
    stacks:   PY.stacks,
    vin:      90,
    Icrest:   PY.Icrest90,
    Vout:     PY.Vout,
    fsw:      PY.fsw,
    tempC:    100,
    boreID:   PY.boreID,
    bundleOD: PY.bundleOD,
    woundOD:  PY.woundOD,
    holeID:   PY.holeID,
    htBuild:  PY.htBuild,
  };
  Object.keys(overrides).forEach(function (k) {
    var el = document.getElementById(k);
    if (!el) return;
    var v = overrides[k];
    /* GUARDRAIL ── a <input type="range"> CLAMPS .value to [min,max]. The studio's
       N slider is max=52 / stacks max=4, but approved designs can exceed those
       (e.g. N=71), so the clamp silently truncated the value and any code reading
       the FORM field (drawWindowBuild passes = N×nParallel, fill %) drew the wrong
       turn count while the JSON-island summary showed the real N — a recurring
       mismatch. Widen the slider's own min/max to include v BEFORE assigning, so
       the form value always equals PY.* regardless of the hardcoded bounds.        */
    if (el.tagName === 'INPUT' && el.type === 'range' && isFinite(+v)) {
      if (+v < +el.min) el.min = String(v);
      if (+v > +el.max) el.max = String(v);
    }
    el.value = v;
    /* keep the slider's printed label (id+'Val') in sync with the widened value */
    var lbl = document.getElementById(k + 'Val');
    if (lbl) lbl.textContent = v;
  });

  /* 12 ── Re-render with all corrected values ───────────────────────── */
  renderAll();

  /* 13 ── Override ALL JS-computed values with Python-authoritative ones ──
     Covers: KPI cards, canvas overlay, audit table, overview table ΔT,
     overview status health-check banners, waveform-metrics table H/Bmax,
     and the review-summary textarea (Inductance/Flux/Loss/Build lines +
     recommended talking points re-evaluated with Python thresholds).      */
  (function () {
    var pyL0    = PY.pyL0_uH;
    var pyLfull = PY.pyLfull_uH;
    var pyH     = PY.pyH_Oe;
    var pyK     = PY.pyK;
    var pyBac   = PY.pyBacPk_T;
    var pyDCR   = PY.pyDCR_100_mOhm;
    var pyPcore = PY.pyPcore_W;
    var pyPtot  = PY.pyPtot_100_W;
    var pyDT    = PY.pyDT_C;
    var pyBmax  = PY.pyBmax_T;
    // v10 new fields
    var pyThotspot  = PY.pyT_hotspot_C;
    var pyDTcore    = PY.pyDT_core_C;
    var pyDTwdg     = PY.pyDT_wdg_C;
    var pyBinner    = PY.pyBmax_inner;
    var pySatInner  = PY.pySatInner_pct;
    var pyMLTv10    = PY.pyMLT_v10_mm;
    // overview + sweep overrides
    var pyCuLen     = PY.pyCuLen_m;
    var pyIhf       = PY.pyIhf_rms_A;
    var pyPacW      = PY.pyPac_W;
    var pyJA        = PY.pyJ_A_mm2;
    var pyKuPct     = (PY.pyKu * 100).toFixed(2);
    var pyPuncLo    = PY.pyPuncLo_W;
    var pyPuncHi    = PY.pyPuncHi_W;
    var pySweepData = PY.sweepData;

    // Interpolate Python per-operating-point data (sweepData) at an arbitrary
    // Vin — keeps the live 3D-model overlay Python-authoritative as Vin moves.
    var _swSorted = (pySweepData || []).slice().sort(function (a, b) { return a.Vin - b.Vin; });
    function pyAtVin(vin) {
      var sd = _swSorted;
      if (!sd.length) return null;
      if (vin <= sd[0].Vin) return sd[0];
      if (vin >= sd[sd.length - 1].Vin) return sd[sd.length - 1];
      for (var i = 0; i < sd.length - 1; i++) {
        var a = sd[i], b = sd[i + 1];
        if (vin >= a.Vin && vin <= b.Vin) {
          var t = (b.Vin - a.Vin) > 0 ? (vin - a.Vin) / (b.Vin - a.Vin) : 0;
          var lerp = function (key) { return a[key] + t * (b[key] - a[key]); };
          return { Vin: vin, Lfull: lerp('Lfull'), Bac: lerp('Bac'),
                   Pcore: lerp('Pcore'), Pcu: lerp('Pcu'), Ptot: lerp('Ptot'),
                   Icrest: lerp('Icrest'), H: lerp('H'), k: lerp('k') };
        }
      }
      return sd[sd.length - 1];
    }

    function applyPyOverrides() {
      var d = document;
      function setEl(id, txt) { var e = d.getElementById(id); if (e) e.textContent = txt; }

      /* Live operating point — Python per-Vin data (sweepData) + temp scaling.
         Drives BOTH the KPI cards (Section A) and the 3D-model overlay (B). At
         the design point (90 V, 100 °C) every ratio is 1, so the values equal
         the Python design numbers exactly. */
      var curVin = +(d.getElementById('vin')   || {value: 90}).value;
      var curT   = +(d.getElementById('tempC') || {value: 100}).value;
      var _opTag = d.getElementById('kpiOpTag');
      if (_opTag) _opTag.innerHTML = 'Operating point: <span style="color:#38bdf8">' +
        curVin + ' Vac</span> &middot; ' + curT + ' &deg;C';
      var at = pyAtVin(curVin) ||
        { Lfull: pyLfull, Bac: pyBac, Pcore: pyPcore, Pcu: (pyPtot - pyPcore), Ptot: pyPtot,
          Icrest: PY.Icrest90, H: pyH, k: pyK };
      var tScale     = (235 + curT) / (235 + 100);          // copper R(T)=R100*(235+T)/(235+100)
      var liveDCR    = pyDCR  * tScale;
      var liveCore   = at.Pcore * PY.pcoreAnchor;           // core loss, anchored to waveform model
      var livePcu    = at.Pcu * PY.pcuAnchor * tScale;      // copper loss, anchored, tracks R(T)
      var livePtot   = liveCore + livePcu;                  // total = core(≈T-indep) + copper(T)
      var bScale     = pyBac > 0 ? at.Bac / pyBac : 1;      // flux ~ AC excitation
      var liveBmax   = pyBmax   * bScale;
      var liveBinner = pyBinner * bScale;
      var lScale     = pyPtot > 0 ? livePtot / pyPtot : 1;  // thermal rise ~ total loss
      var liveDT     = pyDT     * lScale;
      var liveDTcore = pyDTcore * lScale;
      var liveDTwdg  = pyDTwdg  * lScale;
      var liveThs    = pyThotspot + (curT - 100) +
                       Math.max(liveDTcore - pyDTcore, liveDTwdg - pyDTwdg);

      /* A ── KPI cards (live: Python per-Vin + temp scaling) ─────────────── */
      setEl('kpiL0',    pyL0.toFixed(1)     + ' µH');   // zero-bias L — Vin-independent
      setEl('kpiLfull', at.Lfull.toFixed(1) + ' µH');
      setEl('kpiH',     at.H.toFixed(1)     + ' Oe');   // per-Vin H_Oe (Python)
      setEl('kpiK',     at.k.toFixed(3));               // per-Vin k(H)  (Python)
      setEl('kpiBmax',  liveBmax.toFixed(3) + ' T');    // mean operating flux (Vin)
      setEl('kpiBpk',   at.Bac.toFixed(3)   + ' T');
      setEl('kpiDCR',   liveDCR.toFixed(1)  + ' mΩ');
      setEl('kpiPcore', liveCore.toFixed(2) + ' W');
      setEl('kpiPtot',  livePtot.toFixed(2) + ' W');

      /* B ── Canvas info overlay — LIVE: Python per-Vin data + temp scaling ── */
      var cvs = d.getElementById('model');
      if (cvs) {
        var ctx = cvs.getContext('2d');
        var curN   = +(d.getElementById('N')      || {value: PY.N}).value;
        var curStk = +(d.getElementById('stacks') || {value: PY.stacks}).value;

        ctx.fillStyle = 'rgba(15,23,42,.92)';
        ctx.fillRect(14, 14, 392, 160);
        ctx.strokeStyle = 'rgba(148,163,184,.18)';
        ctx.strokeRect(14, 14, 392, 160);
        ctx.fillStyle = '#e5e7eb'; ctx.font = '14px Segoe UI';
        ctx.fillText('N = ' + curN + '   stacks = ' + curStk + '   Vin = ' + curVin + ' Vac   temp = ' + curT + '°C', 26, 38);
        ctx.fillText('Lfull = ' + at.Lfull.toFixed(1) + ' µH   Ptotal = ' + livePtot.toFixed(2) + ' W', 26, 62);
        ctx.fillText('Bmax,mean = ' + liveBmax.toFixed(3) + ' T   DCR = ' + liveDCR.toFixed(1) + ' mΩ   ΔT = ' + liveDT.toFixed(1) + '°C', 26, 86);
        ctx.fillStyle = '#a78bfa'; ctx.font = '13px Segoe UI';
        ctx.fillText('T_hotspot = ' + liveThs.toFixed(1) + '°C  (core +' + liveDTcore.toFixed(1) + ' / wdg +' + liveDTwdg.toFixed(1) + ' K)   Bmax,inner = ' + liveBinner.toFixed(3) + ' T', 26, 110);
        ctx.fillStyle = '#9ca3af'; ctx.font = '12px Segoe UI';
        var cg = window.cfg || {};
        var cOD = (cg.coreOD_mm || 40.9).toFixed(1), cID = (cg.coreID_mm || 21.3).toFixed(1);
        var cH  = (curStk * (cg.coreHeight_mm || 0)).toFixed(1), cLbl = cg.coreLabel || '';
        ctx.fillText('OD ' + cOD + ' · ID ' + cID + ' · stack height ' + cH + ' mm' +
          (cLbl ? ' · ' + cLbl : '') + ' · winding fades when exploded', 26, 136);
      }

      /* C ── Audit table (Design Review Summary tab) ────────────────────── */
      var auTbl = d.getElementById('auditTbl');
      if (auTbl) {
        var auRows = auTbl.querySelectorAll('tr');
        var auPatch = {5: pyLfull.toFixed(1) + ' µH', 6: pyBmax.toFixed(3) + ' T',
                       7: pyPtot.toFixed(2)  + ' W', 10: pyDT.toFixed(1)   + ' °C'};
        Object.keys(auPatch).forEach(function (idx) {
          var r = auRows[+idx]; if (!r) return;
          var tds = r.querySelectorAll('td'); if (tds[1]) tds[1].textContent = auPatch[idx];
        });
      }

      /* D ── Overview table — patch ΔT row + append v10 thermal / flux rows ─ */
      var ovTbl = d.getElementById('overviewTbl');
      if (ovTbl) {
        var ovR = ovTbl.querySelectorAll('tr')[7];
        if (ovR) { var tds7 = ovR.querySelectorAll('td'); if (tds7[1]) tds7[1].textContent = pyDT.toFixed(1) + ' °C (SA surface)'; }
        // Append v10 rows only once (guard by checking first new label)
        var alreadyAdded = Array.from(ovTbl.querySelectorAll('td')).some(function(td){ return td.textContent === 'T_hotspot (v10)'; });
        if (!alreadyAdded) {
          var ovBody = ovTbl.querySelector('tbody') || ovTbl;
          [['T_hotspot (v10)',     pyThotspot.toFixed(1) + ' °C',   'max(ΔT_core, ΔT_wdg) × 1.12 hotspot factor (2-node)'],
           ['ΔT core node',        pyDTcore.toFixed(1)   + ' °C',   'Core node temperature rise above ambient'],
           ['ΔT winding node',     pyDTwdg.toFixed(1)    + ' °C',   'Winding node temperature rise above ambient'],
           ['Bmax inner bore',     pyBinner.toFixed(3)   + ' T',    'Bmax × (r_mean/r_in) radial crowding — inner bore peak'],
           ['Sat. margin inner',   pySatInner.toFixed(1) + ' %',    'Inner-bore headroom vs Bsat at T_core'],
           ['MLT (v10)',           pyMLTv10.toFixed(2)   + ' mm',   '2(coreW + HT×stacks) + 2×bundleOD']
          ].forEach(function(row) {
            var tr = document.createElement('tr');
            row.forEach(function(txt) { var td = document.createElement('td'); td.textContent = txt; tr.appendChild(td); });
            ovBody.appendChild(tr);
          });
        }
      }

      /* D2 ── Override remaining overview rows with Python-authoritative values */
      if (ovTbl) {
        var ovR2 = ovTbl.querySelectorAll('tr');
        var ovPatch2 = {
          0: pyCuLen.toFixed(2) + ' m',
          3: pyIhf.toFixed(2) + ' A',
          4: (pyPacW * 1000).toFixed(1) + ' mW',
          5: pyJA.toFixed(2) + ' A/mm²',
          6: pyKuPct + ' %',
          8: pyPuncLo.toFixed(2) + '–' + pyPuncHi.toFixed(2) + ' W',
        };
        Object.keys(ovPatch2).forEach(function(idx) {
          var r = ovR2[+idx]; if (!r) return;
          var tds = r.querySelectorAll('td'); if (tds[1]) tds[1].textContent = ovPatch2[idx];
        });
      }

      /* H ── Sweep table — replace JS Steinmetz rows with Python iGSE data ── */
      var swTbl = d.getElementById('sweepTbl');
      if (swTbl && pySweepData.length > 0) {
        swTbl.innerHTML = pySweepData.map(function(r) {
          var pc = r.Pcore * PY.pcoreAnchor;   // anchored to waveform core loss
          var pu = r.Pcu   * PY.pcuAnchor;     // anchored to waveform copper loss
          var pt = pc + pu;
          var unc = (pu + 1.05*pc).toFixed(2) + '–' + (pu + 1.20*pc).toFixed(2);
          var hl = r.Vin > 150;
          return '<tr' + (hl ? ' style="opacity:.75"' : '') + '>' +
            '<td>' + r.Vin.toFixed(0) + (hl ? ' HL' : ' LL') + '</td>' +
            '<td>' + r.Icrest.toFixed(2) + '</td>' +
            '<td>' + r.Lfull.toFixed(1) + '</td>' +
            '<td>' + r.Bac.toFixed(3) + '</td>' +
            '<td>' + pc.toFixed(2) + '</td>' +
            '<td>' + pu.toFixed(2) + '</td>' +
            '<td>' + pt.toFixed(2) + '</td>' +
            '<td>' + unc + '</td></tr>';
        }).join('');
      }

      /* E ── Overview status — Lfull / Bmax / ΔT / hotspot health-check ──── */
      var osi = d.getElementById('overviewStatus');
      if (osi) {
        var cg2 = window.cfg || {};
        var satT2 = cg2.satT || 1.0;
        var okL2 = pyLfull >= 235, okB2 = pyBmax < 0.5, okT2 = pyDT < 40;
        var okBi2 = pyBinner < satT2 * 0.85;      // inner-bore: healthy when <85% of Bsat
        var okThs2 = pyThotspot < 110;             // hotspot: healthy when <110°C absolute
        var sm2   = (satT2 / Math.max(pyBmax,   1e-9)).toFixed(2);
        var smI2  = (satT2 / Math.max(pyBinner, 1e-9)).toFixed(2);
        var cStk2 = +(d.getElementById('stacks') || {value: PY.stacks}).value;
        var htBEl = d.getElementById('htBuild'), wODEl = d.getElementById('woundOD'), hlEl = d.getElementById('holeID');
        var htB2  = +(htBEl ? htBEl.value  : PY.htBuild);
        var odW2  = +(wODEl ? wODEl.value  : PY.woundOD);
        var hlID2 = +(hlEl  ? hlEl.value   : PY.holeID);
        var oh2   = cStk2 * (cg2.coreHeight_mm || 17.89) + htB2;
        var sa2   = (Math.PI*odW2*oh2 + 2*(Math.PI/4)*(odW2*odW2 - hlID2*hlID2) + Math.PI*hlID2*oh2) / 100;
        osi.querySelectorAll('div').forEach(function (dv) {
          var t = dv.textContent;
          if (t.indexOf('Inductance target') >= 0) {
            dv.innerHTML = '<span class="' + (okL2?'ok':'warn') + '">' +
              (okL2?'Inductance target met':'Inductance target missed') +
              '</span> — Lfull = ' + pyLfull.toFixed(1) + ' µH versus 235 µH target.';
          } else if (t.indexOf('Flux level') >= 0) {
            dv.innerHTML = '<span class="' + (okB2?'ok':'warn') + '">' +
              (okB2?'Flux level looks comfortable':'Flux level is getting high') +
              '</span> — Bmax,mean = ' + pyBmax.toFixed(3) + ' T (≈' + sm2 + '× to ' + satT2.toFixed(2) + ' T);  inner-bore peak = ' + pyBinner.toFixed(3) + ' T (≈' + smI2 + '× B(r) crowded).';
          } else if (t.indexOf('temperature rise') >= 0) {
            dv.innerHTML = '<span class="' + (okT2?'ok':'warn') + '">' +
              (okT2?'Estimated temperature rise looks manageable':'Estimated temperature rise is getting high') +
              '</span> — ΔT_surface ≈ ' + pyDT.toFixed(1) + ' °C (SA ' + sa2.toFixed(0) + ' cm²); T_hotspot = ' + pyThotspot.toFixed(1) + ' °C (core +' + pyDTcore.toFixed(1) + ' / wdg +' + pyDTwdg.toFixed(1) + ' K, 2-node v10).';
          }
        });
        // Append inner-bore saturation banner only once
        var hasBiDiv2 = Array.from(osi.querySelectorAll('div')).some(function(dv){ return dv.textContent.indexOf('Inner-bore saturation') >= 0; });
        if (!hasBiDiv2) {
          var biDiv2 = document.createElement('div');
          biDiv2.innerHTML = '<span class="' + (okBi2?'ok':'warn') + '">' +
            (okBi2?'Inner-bore saturation margin OK':'Inner-bore saturation margin tight') +
            '</span> — Bmax,inner = ' + pyBinner.toFixed(3) + ' T (' + pySatInner.toFixed(1) + '% margin). B(r) crowding factor from radial geometry (v10).';
          osi.appendChild(biDiv2);
        }
      }

      /* F ── Waveform metrics table — patch H/Bmax + append v10 thermal rows ─ */
      var wvTbl = d.getElementById('waveTbl');
      if (wvTbl) {
        wvTbl.querySelectorAll('tr').forEach(function (r) {
          var tds = r.querySelectorAll('td'); if (!tds[0]) return;
          var lbl = tds[0].textContent.trim();
          if (lbl === 'Peak H(t)'    && tds[1]) tds[1].textContent = pyH.toFixed(1)    + ' Oe';
          if (lbl === 'Peak Bmax(t)' && tds[1]) tds[1].textContent = pyBmax.toFixed(3) + ' T (mean)';
        });
        // Append v10 rows only once
        var hasWvRow = Array.from(wvTbl.querySelectorAll('td')).some(function(td){ return td.textContent === 'T_hotspot (v10)'; });
        if (!hasWvRow) {
          var wvBody = wvTbl.querySelector('tbody') || wvTbl;
          [['Bmax inner bore',      pyBinner.toFixed(3) + ' T'],
           ['T_hotspot (v10)',      pyThotspot.toFixed(1) + ' °C'],
           ['ΔT core / winding',   pyDTcore.toFixed(1) + ' / ' + pyDTwdg.toFixed(1) + ' °C']
          ].forEach(function(row) {
            var tr = document.createElement('tr');
            row.forEach(function(t) { var td = document.createElement('td'); td.textContent = t; tr.appendChild(td); });
            wvBody.appendChild(tr);
          });
        }
      }

      /* G ── Summary textarea — replace Python-authoritative lines ──────── */
      var su = d.getElementById('summaryOut');
      if (su && su.value) {
        var pyPcu2  = pyPtot - pyPcore;
        var pyUncLo = pyPuncLo > 0 ? pyPuncLo.toFixed(2) : (pyPcu2 + 1.05*pyPcore).toFixed(2);
        var pyUncHi = pyPuncHi > 0 ? pyPuncHi.toFixed(2) : (pyPcu2 + 1.20*pyPcore).toFixed(2);
        var satT3   = (window.cfg && window.cfg.satT) ? window.cfg.satT : 1.0;
        var sm3     = (satT3 / Math.max(pyBmax, 1e-9)).toFixed(2);
        var okL3 = pyLfull >= 235, pyBHigh = pyBmax > 0.45, pyTHigh = pyDT > 35;
        var lines = su.value.split('\\n'), recIdx = -1;
        for (var si = 0; si < lines.length; si++) {
          var ln = lines[si];
          if (ln.indexOf('Inductance:') >= 0) {
            lines[si] = 'Inductance: L0 = ' + pyL0.toFixed(1) + ' µH, Lfull = ' + pyLfull.toFixed(1) +
              ' µH, Hcrest = ' + pyH.toFixed(1) + ' Oe, retention = ' + pyK.toFixed(3) + '.';
          } else if (ln.indexOf('Flux:') >= 0) {
            var crowdFactor3 = pyBmax > 0 ? (pyBinner / pyBmax).toFixed(2) : '—';
            lines[si] = 'Flux: Bac,pk@crest = ' + pyBac.toFixed(3) + ' T, Bmax,mean = ' + pyBmax.toFixed(3) +
              ' T, Bmax,inner = ' + pyBinner.toFixed(3) + ' T (×' + crowdFactor3 + ' B(r) crowding), sat. margin inner = ' + pySatInner.toFixed(1) + '% vs Bsat ' + satT3.toFixed(2) + ' T.';
          } else if (ln.indexOf('Loss:') >= 0) {
            lines[si] = 'Loss: Pcore = ' + pyPcore.toFixed(2) + ' W, Pcu ≈ ' + pyPcu2.toFixed(2) +
              ' W, Ptotal = ' + pyPtot.toFixed(2) + ' W, total-loss uncertainty range = ' +
              pyUncLo + ' to ' + pyUncHi + ' W (analytical uncertainty, not simulation-backed).';
          } else if (ln.indexOf('Build:') >= 0) {
            // Replace ΔT value and append v10 hotspot (2-node thermal); keep copper length / fill / J
            var dtTag = 'estimated ΔT = ';
            var di = ln.indexOf(dtTag);
            if (di >= 0) {
              var di2 = ln.indexOf('°C', di + dtTag.length);
              if (di2 >= 0) {
                lines[si] = ln.substring(0, di) + dtTag + pyDT.toFixed(1) + ' °C (surface), T_hotspot = ' +
                  pyThotspot.toFixed(1) + ' °C (core +' + pyDTcore.toFixed(1) + ' / wdg +' + pyDTwdg.toFixed(1) + ' K, 2-node v10).';
              }
            }
          } else if (ln.trim() === 'Recommended talking points:') {
            recIdx = si;
          }
        }
        // Re-evaluate recommended talking points with Python thresholds
        if (recIdx >= 0) {
          var recs = [];
          if (!okL3)   recs.push('Increase turns or stack count to recover inductance margin.');
          if (pyBHigh) recs.push('Review flux margin; consider more turns or more core area.');
          if (pyTHigh) recs.push('Review copper loss or airflow; DCR dominates temperature rise.');
          if (recs.length === 0) recs.push('Current point looks healthy within the analytical model.');
          lines = lines.slice(0, recIdx + 1).concat(
            recs.map(function (t, ix) { return '  ' + (ix + 1) + '. ' + t; })
          );
        }
        su.value = lines.join('\\n');
      }
      /* grow the read-only summary box to fit its final (Python-corrected) text — no inner scroll */
      if (typeof fitSummary === 'function') fitSummary();
    }

    applyPyOverrides();

    // Re-apply after any input change. Our listeners are registered AFTER the
    // studio's, so the studio's renderAll() (which redraws the canvas + its own
    // overlay) has already run by the time this fires. Running SYNCHRONOUSLY —
    // not via setTimeout — keeps both draws in the same frame so the browser
    // paints only once: no flicker, and our Python overlay always wins.
    var _reApply = function () { applyPyOverrides(); };
    ['N','stacks','tempC','explode','vin','Icrest','Vout','fsw',
     'lossAnchor','boreID','bundleOD','woundOD','holeID','htBuild'].forEach(function (id) {
      var el = document.getElementById(id); if (el) el.addEventListener('input', _reApply);
    });
    var presetEl2 = document.getElementById('preset');
    if (presetEl2) presetEl2.addEventListener('change', _reApply);
    ['genReview','refreshSummary','frontBtn','isoBtn','topBtn','resetBtn'].forEach(function (id) {
      var el = document.getElementById(id); if (el) el.addEventListener('click', _reApply);
    });
    // When the parent posts the step7 contract, the studio's own handler runs renderAll() (which
    // resets the KPI cards to JS values). Our listener is registered AFTER it, so re-applying the
    // Python overrides here restores the correct numbers on FIRST load (no slider move needed).
    window.addEventListener('message', function (ev) {
      if (ev && ev.data && ev.data.__step7_contract) _reApply();
    });
  })();
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
    // Let the content flow to its natural height (no internal 100vh lock) so the
    // iframe can be auto-sized to it and the page uses a single browser scrollbar.
    html = html.replace('min-height:100vh', 'min-height:0')
    // Inject data island + script before </body>
    html = html.replace('</body>', inject + '</body>')
    return html
  }, [result, confirmedState])  // eslint-disable-line react-hooks/exhaustive-deps

  // ── Report generation ──────────────────────────────────────────────────
  const handleReport = async () => {
    if (!result || !confirmedState) return
    setRptLoad(true); setRptError(null)
    try {
      const blob = await docGenerateReport({
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

  // ── Simulation-Agent shadow cross-check (Phase 1) ──────────────────────────
  const handleSimCheck = async () => {
    if (!result || !confirmedState) return
    setSimLoad(true); setSimError(null)
    try {
      const out = await simulateCrossCheck(
        confirmedState as Record<string, unknown>,
        { ...result,
          material_key: result.material_key || (matType === 'powder' ? selMaterial : selGrade) },
        'litz',
      )
      setSimResult(out)
      if (out.ok === false) setSimError((out.errors ?? ['invalid package']).join('; '))
    } catch (e) {
      setSimError((e as Error).message ?? String(e))
    } finally { setSimLoad(false) }
  }

  // Fetch step7's view-contract (per-Vin waveforms) and post it into the studio iframe so its
  // charts render step7's authoritative arrays. Gated in the studio → harmless if it never arrives.
  useEffect(() => {
    if (!result || !confirmedState) return
    let alive = true
    getViewContract(
      confirmedState as Record<string, unknown>,
      { ...result, material_key: result.material_key || (matType === 'powder' ? selMaterial : selGrade) },
    ).then(out => { if (alive) setContract(out.contract) }).catch(() => {})
    return () => { alive = false }
  }, [result, confirmedState])  // eslint-disable-line react-hooks/exhaustive-deps

  const postContract = () => {
    const cw = iframeRef.current?.contentWindow
    if (cw && contract) cw.postMessage({ __step7_contract: contract }, '*')
  }
  useEffect(() => { postContract() }, [contract])  // eslint-disable-line react-hooks/exhaustive-deps

  // ── Auto-size the iframe to its content (kills the inner scrollbar) ─────────
  // The studio is same-origin (allow-same-origin), so we can read its document
  // height and grow the iframe to fit. With no internal scroll, only the browser
  // scrollbar moves the page up/down.
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

  // The "Simulation Agent" tab inside the studio posts this to navigate to the Sim Agent page.
  useEffect(() => {
    const onMsg = (ev: MessageEvent) => {
      if (ev?.data?.__navSimAgent && onSimAgent) onSimAgent()
    }
    window.addEventListener('message', onMsg)
    return () => window.removeEventListener('message', onMsg)
  }, [onSimAgent])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>

      {/* ── iframe: all 4 tabs, full-width ────────────────────────────────── */}
      <iframe
        ref={iframeRef}
        onLoad={handleLoad}
        srcDoc={iframeHtml}
        title="Review Magnetics Data"
        scrolling="no"
        style={{
          width: '100%', minHeight: 680,
          border: 'none', borderRadius: 10, background: '#08101f', display: 'block',
        }}
        sandbox="allow-scripts allow-same-origin"
      />

      {/* ── Simulation-Agent cross-check (Phase 1 shadow; additive) ────────── */}
      {(simResult || simError) && (
        <div style={{
          marginTop: 8, padding: '10px 12px', borderRadius: 8,
          border: `1px solid ${C.border}`, background: 'rgba(56,189,248,.05)', fontSize: 12,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6, flexWrap: 'wrap' }}>
            <span style={{ fontSize: 10, textTransform: 'uppercase', letterSpacing: '.06em',
              color: C.accent, fontWeight: 700 }}>Simulation cross-check (shadow)</span>
            {simResult?.verdict && (
              <span style={{ fontFamily: 'IBM Plex Mono,monospace', fontWeight: 700,
                color: simResult.verdict === 'APPROVE' ? C.green : C.amber }}>{simResult.verdict}</span>
            )}
            {simResult?.crosscheck && (
              <span style={{ fontFamily: 'IBM Plex Mono,monospace',
                color: simResult.crosscheck.all_within_band ? C.green : C.amber }}>
                {simResult.crosscheck.all_within_band === null ? '—'
                  : simResult.crosscheck.all_within_band ? '✓ all within band'
                  : '⚠ deviations outside band'}
              </span>
            )}
          </div>
          {simError && <div style={{ color: '#c0392b', marginBottom: 6 }}>⚠ {simError}</div>}
          {simResult?.crosscheck?.rows && (
            <table style={{ width: '100%', borderCollapse: 'collapse',
              fontFamily: 'IBM Plex Mono,monospace', fontSize: 11 }}>
              <thead>
                <tr style={{ color: C.muted, textAlign: 'right' }}>
                  <th style={{ textAlign: 'left', padding: '2px 6px' }}>Quantity</th>
                  <th style={{ padding: '2px 6px' }}>Ours (step7)</th>
                  <th style={{ padding: '2px 6px' }}>Sim engine</th>
                  <th style={{ padding: '2px 6px' }}>Δ%</th>
                  <th style={{ padding: '2px 6px' }}>Band</th>
                  <th style={{ padding: '2px 6px' }}>Status</th>
                </tr>
              </thead>
              <tbody>
                {simResult.crosscheck.rows.map((r) => (
                  <tr key={r.quantity} style={{ borderTop: `0.5px solid ${C.border}`, textAlign: 'right' }}>
                    <td style={{ textAlign: 'left', padding: '3px 6px', color: C.text }}>{r.quantity}</td>
                    <td style={{ padding: '3px 6px', color: C.muted }}>{r.ours ?? '—'}</td>
                    <td style={{ padding: '3px 6px', color: C.muted }}>{r.sim ?? '—'}</td>
                    <td style={{ padding: '3px 6px', color: r.within === false ? C.amber : C.text }}>
                      {r.delta_pct === null ? '—' : `${r.delta_pct > 0 ? '+' : ''}${r.delta_pct}%`}
                    </td>
                    <td style={{ padding: '3px 6px', color: C.hint }}>±{r.band_pct}%</td>
                    <td style={{ padding: '3px 6px',
                      color: r.within === null ? C.hint : r.within ? C.green : C.amber }}>
                      {r.within === null ? '—' : r.within ? '✓' : '⚠'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {simResult?.validation?.warnings && simResult.validation.warnings.length > 0 && (
            <div style={{ marginTop: 6, color: C.amber, fontSize: 10 }}>
              {simResult.validation.warnings.map((w, i) => <div key={i}>• {w}</div>)}
            </div>
          )}
        </div>
      )}

      {/* ── Action bar ────────────────────────────────────────────────────── */}
      <div style={{
        display: 'flex', gap: 8, paddingTop: 10, marginTop: 6,
        borderTop: `0.5px solid ${C.border}`,
        justifyContent: 'space-between', alignItems: 'flex-start',
      }}>
        <div style={{ display: 'flex', gap: 8 }}>
          <Btn variant="ghost" onClick={onBack}>← Back to Result</Btn>
          <Btn variant="ghost" onClick={onRestart}>↺ New design</Btn>
          <Btn variant="ghost" disabled={simLoading} onClick={handleSimCheck}>
            {simLoading ? '⏳ Simulating…' : '🧪 Sim cross-check'}
          </Btn>
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
