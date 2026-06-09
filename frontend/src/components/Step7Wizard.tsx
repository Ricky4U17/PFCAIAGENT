import React, { useState, useEffect } from 'react'
import { Card, SecHead, Btn, Badge, ErrBanner, ActionBar, Spinner, C } from './ui'
import {
  step7PowderRanking, step7MaterialComparison, step7Suppliers,
  step7GradeOptions, step7WireOptions, step7RunSizing, step8TimeDomain,
} from '../api/client'
import { ReviewMagnetics } from './ReviewMagnetics'

interface Props {
  confirmedState: Record<string, unknown>
  onBack: () => void
  onRestart: () => void
  onApprove?: (approvedDesign: Record<string, unknown>) => void
}

// ── Helpers ───────────────────────────────────────────────────────────────────
type SubStep = 'material' | 'powder_rank' | 'ferrite_grade' | 'wire' | 'result' | 'review'

const WINDING_OPTS = [
  { key: 'single',    label: 'Single strand',  desc: 'Standard — one conductor wound.' },
  { key: 'bifilar',   label: 'Bifilar',         desc: '2 conductors wound together. Reduces AC resistance, halves Pcu. Standard for Medical TIW.' },
  { key: 'trifilar',  label: 'Trifilar',        desc: '3 conductors wound together. For 3-phase or ultra-low DCR requirement.' },
]
const HEIGHT_PRESETS = [
  { label: 'No limit',      value: 9999  },
  { label: '1U (44.45 mm)', value: 44.45 },
  { label: '2U (88.9 mm)',  value: 88.9  },
  { label: '3U (133.3 mm)', value: 133.3 },
]
const SCORE_COLOR = (s: number) => s <= 3 ? C.green : s <= 8 ? C.teal : s <= 12 ? C.amber : C.red
const K_COLOR     = (k: number) => k >= 0.75 ? C.green : k >= 0.50 ? C.teal : k >= 0.35 ? C.amber : C.red
const DT_COLOR    = (dt: number) => dt < 40 ? C.green : dt < 60 ? C.amber : C.red
// Normalise wire designation — Litz uses 'designation', TIW may use 'wire_code'/'size'
const wireKey = (w: any): string =>
  w.designation ?? w.wire_code ?? w.size ??
  `${(w.strand_dia_mm ?? w.diameter_mm ?? w.dia_mm ?? 0).toFixed(3)}mm`

// Format material key: "edge_90" → "Edge · µ=90", ferrite keys like "3c95" pass through unchanged
const fmtMat = (key: string) => {
  const m = key.match(/^(.+?)_(\d+)$/)
  return m
    ? `${m[1].replace(/_/g,' ').replace(/\b\w/g,c=>c.toUpperCase())} · µ=${m[2]}`
    : key.replace(/_/g,' ').replace(/\b\w/g,c=>c.toUpperCase())
}
// Extract trailing permeability number from a material key ("edge_90" → "90")
const matMu = (key: string) => { const m = (key||'').match(/(\d+)$/); return m ? m[1] : '' }

// ── Steps bar ────────────────────────────────────────────────────────────────
const StepBar = ({ sub, isPowder }: { sub: SubStep; isPowder: boolean }) => {
  const steps = isPowder
    ? [['material','Type'],['powder_rank','Rank'],['wire','Wire'],['result','Result'],['review','Review']]
    : [['material','Type'],['ferrite_grade','Grade'],['wire','Wire'],['result','Result'],['review','Review']]
  const idx = steps.findIndex(([k]) => k === sub)
  return (
    <div style={{ display:'grid', gridTemplateColumns:`repeat(${steps.length},1fr)`, gap:4, marginBottom:18 }}>
      {steps.map(([k,lbl],i) => {
        const done=i<idx, act=i===idx
        return (
          <div key={k}>
            <div style={{height:3,borderRadius:2,marginBottom:3,
              background:done?C.green:act?C.accent:C.border,transition:'background .3s'}}/>
            <div style={{fontSize:9,color:done?C.green:act?C.accent:C.hint,
              textTransform:'uppercase',letterSpacing:'.05em',fontWeight:500}}>
              {done?'✓ ':''}{lbl}
            </div>
          </div>
        )
      })}
    </div>
  )
}

// ── Main Wizard ───────────────────────────────────────────────────────────────
export const Step7Wizard: React.FC<Props> = ({ confirmedState, onBack, onRestart, onApprove }) => {
  const intake   = (confirmedState.intake as any) ?? {}
  const tsi      = (confirmedState.topology_specific_inputs as any) ?? {}
  const isMedical = ((intake.compliance as any)?.application_class ?? '') === 'Medical'
  const fsw_Hz   = Number(tsi.recommended_frequency_hz ?? 70000)
  const L_uH     = Number(tsi.confirmed_L_uH_sel ?? tsi.recommended_L_uH ?? 240)
  const Irms     = Number(tsi.Iph_rms_A ?? 10.07)
  const Ipk      = Number(tsi.Ipk_ph_A ?? 16.73)
  const dIL      = Number(tsi.dIL_pp_A ?? 5.161)

  const [sub,   setSub]   = useState<SubStep>('material')
  const [loading,setLoad] = useState(false)
  const [err,   setErr]   = useState<string[]>([])

  // Gate 1 — material type
  const [matType, setMatType] = useState<'powder'|'ferrite'>('powder')
  const [matComp, setMatComp] = useState<any>(null)

  // Gate 2a — powder ranking
  const [powderRanked, setPowderRanked] = useState<any[]>([])
  const [selMaterial,  setSelMaterial]  = useState('')

  // Gate 2b — ferrite grade
  const [suppliers, setSuppliers] = useState<any[]>([])
  const [supplier,  setSupplier]  = useState('')
  const [grades,    setGrades]    = useState<any[]>([])
  const [selGrade,  setSelGrade]  = useState('')

  // Gate 3 — wire + size
  const [wireType,    setWireType]    = useState<'litz'|'magnet'|'tiw'>('magnet')
  const [winding,     setWinding]     = useState('bifilar')
  const [wireOptions, setWireOptions] = useState<any[]>([])
  const [wireReason,  setWireReason]  = useState('')
  const [selWire,     setSelWire]     = useState('')
  const [maxH,        setMaxH]        = useState(9999)
  const [maxStacks,   setMaxStacks]   = useState(3)
  const [mountDir,    setMountDir]    = useState<'horizontal'|'vertical'>('horizontal')
  const [jTarget,     setJTarget]     = useState(5.0)
  const [FFcuLimit,   setFFcuLimit]   = useState(0.35)    // designer-selectable fill factor
  const [optGoal,     setOptGoal]     = useState<'best_performance'|'max_ffu'>('best_performance')
  const [coatedOnly,  setCoatedOnly]  = useState(true)    // Medical default
  const [showCustom,  setShowCustom]  = useState(false)   // custom core entry panel
  const [customCore,  setCustomCore]  = useState({        // custom core fields
    part_number:'', OD_mm:'', ID_mm:'', HT_mm:'',
    AL_nom_nH:'', AL_min_nH:'', Wa_mm2:'', Ve_cm3:'', Le_mm:''
  })

  // Gate 4 — result
  const [result,   setResult]   = useState<any>(null)
  const [allCandidates, setAllCandidates] = useState<any[]>([])
  const [selectedCandIdx, setSelectedCandIdx] = useState<number>(0)
  const [step8,    setStep8]    = useState<any>(null)
  const [s8Loading,setS8Load]   = useState(false)
  const [rptLoading,setRptLoad] = useState(false)
  const [rptError,  setRptError] = useState<string|null>(null)

  // Load material comparison once
  useEffect(() => {
    step7MaterialComparison().then(setMatComp).catch(() => {})
  }, [])

  // Load powder ranking when entering powder_rank gate
  useEffect(() => {
    if (sub !== 'powder_rank') return
    setLoad(true); setErr([])
    step7PowderRanking({
      fsw_Hz, Bac_pk_T: 0.054, T_operating_C: 100.0,
      Ipk_A: Ipk, dIL_pp_A: dIL, Le_single_m: 0.0655, L_target_uH: L_uH, mu: 60
    }).then((d:any) => {
      setPowderRanked(d.materials ?? [])
      if (d.materials?.length) setSelMaterial(d.materials[0].material_key)
      setLoad(false)
    }).catch(() => { setErr(['Failed to load material ranking']); setLoad(false) })
  }, [sub])

  // Load suppliers for ferrite path
  useEffect(() => {
    if (sub !== 'ferrite_grade') return
    step7Suppliers('ferrite').then((d:any) => {
      setSuppliers(d.suppliers ?? [])
      if (d.suppliers?.length) setSupplier(d.suppliers[0].key)
    }).catch(() => setErr(['Failed to load suppliers']))
  }, [sub])

  // Load grades when supplier changes
  useEffect(() => {
    if (sub !== 'ferrite_grade' || !supplier) return
    setLoad(true)
    step7GradeOptions({ material_type:'ferrite', supplier,
      fsw_Hz, Bac_pk_T:0.054, T_operating_C:100.0, topology:'boost_pfc' })
    .then((d:any) => { setGrades(d.grades??[]); if(d.grades?.length) setSelGrade(d.grades[0].material_key); setLoad(false) })
    .catch(() => { setErr(['Failed to load grades']); setLoad(false) })
  }, [sub, supplier])

  // Clear wire selection when wire type changes so stale Litz key can't block TIW
  useEffect(() => { setSelWire(''); setWireReason('') }, [wireType])

  // TIW wire is triple-insulated — core coating not required for Medical compliance
  useEffect(() => {
    if (wireType === 'tiw') setCoatedOnly(false)
    else if (isMedical)     setCoatedOnly(true)
  }, [wireType])

  // TIW is triple-insulated — disable coated filter automatically
  useEffect(() => {
    if (wireType === 'tiw') setCoatedOnly(false)
    else if (isMedical)     setCoatedOnly(true)
  }, [wireType])

  // Load wire options when entering wire gate
  useEffect(() => {
    if (sub !== 'wire') return
    setLoad(true)
    const nPar = winding==='bifilar'?2:winding==='trifilar'?3:1
    // Crest ripple: r = dIL_pp / Ipk at line crest. IL_HF_rms = dIL_pp/(2√3)
    const dIL_pp  = parseFloat((sub as any)?.topology_specific_inputs?.dIL_pp_A
                    ?? (sub as any)?.dIL_pp_A ?? 5.161)
    const IL_HF_rms = dIL_pp / (2 * Math.sqrt(3))
    step7WireOptions({ wire_type: wireType, IL_rms_A: Irms/nPar,
      IL_HF_rms_A: IL_HF_rms,
      fsw_Hz, T_C:100.0, J_target: jTarget, n_options:50 })
    .then((d:any) => {
        setWireOptions(d.options??[])
        setWireReason(d.wire_reason??'')
        // Auto-select first feasible wire; fall back to first available
        const feasible = (d.options??[]).filter((w:any)=>w.current_ok!==false&&w.skin_ok!==false)
        const best = feasible[0] ?? (d.options??[])[0]
        if(best) setSelWire(wireKey(best)); else setSelWire('')
        setLoad(false)
    })
    .catch(() => { setErr(['Failed to load wire options']); setLoad(false) })
  }, [sub, wireType, winding, jTarget])

  // Shared enrichment: adds all computed display fields to a raw backend result.
  // nPar and winding are passed explicitly to avoid stale-closure bugs.
  const enrichResult = (raw: any, idx: number, np: number, wd: string) => {
    const t = { ...raw }
    t.H_dc_Oe         = t.H_Oe_design ?? 0
    t.dT_rise_C       = t.dT_rise_C ?? 0
    t.Rth             = t.dT_rise_C / Math.max((t.Pcu_100C_W ?? 0) + (t.Pcore_W ?? 0), 0.001)
    t.Bsat_T          = t.Bsat_at_Tcore ?? 0
    t.Pcu_100C_W      = t.Pcu_100C_W ?? 0
    t.FFcu            = t.FFcu ?? 0
    t.Bmax_FL_T       = t.Bmax_FL_T ?? 0
    t.L_no_load_uH    = Math.round(t.L0_nom_uH ?? 0)

    // Use the actual DB-computed L_full and k from L_vs_Vin_table at 90 Vac.
    // kreq_nom = L_target/L0 (required k) and is NOT the actual retention —
    // using it here always returned L_target rather than the real full-load L.
    const lvt    = (t.L_vs_Vin_table ?? []) as any[]
    const row90  = lvt.find(r => Number(r.Vin_rms) === 90)
    const kActual = row90?.k_bias        ?? (t.kreq_nom ?? 0.8)
    const Lfull   = row90?.L_full_nom_uH ?? Math.round((t.L0_nom_uH ?? 0) * kActual)
    t.kbias           = kActual
    t.L_full_load_uH  = Math.round(Lfull)
    t.L_variation_pct = Math.round((1 - kActual) * 100)

    t.n_parallel      = np
    t.winding         = wd
    setSelectedCandIdx(idx)
    setResult(t)
    return t
  }

  // Single source of truth for Step 8 (time-domain core loss): re-run it for
  // whichever candidate is currently selected, so "Pcore avg W" always reflects
  // the same core/material the "Pcore iron" figure was computed for. Pass the
  // RAW candidate result (its own material_key/N/Ae/etc.) — never the enriched
  // display object or a Gate-2 selection — so both panels agree exactly.
  const runStep8For = (raw: any) => {
    setS8Load(true); setStep8(null)
    step8TimeDomain({ state: confirmedState,
      approved_design: { ...raw }, f_line_Hz: 60.0 })
    .then((s8:any) => { setStep8(s8); setS8Load(false) })
    .catch(() => setS8Load(false))
  }

  const runSizing = async () => {
    setLoad(true); setErr([])
    const nPar = winding==='bifilar'?2:winding==='trifilar'?3:1
    const matKey = matType==='powder' ? selMaterial : selGrade
    try {
      // Build custom core payload if designer filled it in
      const cc = showCustom && customCore.part_number ? {
        ...customCore,
        OD_mm: +customCore.OD_mm, ID_mm: +customCore.ID_mm, HT_mm: +customCore.HT_mm,
        AL_nom_nH: +customCore.AL_nom_nH, AL_min_nH: +customCore.AL_min_nH,
        Wa_mm2: +customCore.Wa_mm2, Ve_cm3: +customCore.Ve_cm3, Le_mm: +customCore.Le_mm,
        // computed fields needed by design_one_core
        stacks: 1, h_effective_mm: +customCore.HT_mm,
        Ae_total_mm2: Math.round((+customCore.OD_mm - +customCore.ID_mm)/2 * +customCore.HT_mm),
        Wa_total_mm2: +customCore.Wa_mm2,
        Ve_total_cm3: +customCore.Ve_cm3,
        Le_single_mm: +customCore.Le_mm,
        AL_nom_total: +customCore.AL_nom_nH,
        AL_min_total: +customCore.AL_min_nH || Math.round(+customCore.AL_nom_nH * 0.92),
        AL_max_total: Math.round(+customCore.AL_nom_nH * 1.08),
        AL_tolerance_pct: 8,
        coated: 'true', material_line: 'Custom',
      } : null

      const d = await step7RunSizing({
        state: confirmedState, material_key: matKey,
        wire_designation: selWire, wire_type: wireType, n_parallel: nPar,
        max_height_mm: maxH, max_stacks: maxStacks, J_target: jTarget, n_top:5,
        FFcu_limit: FFcuLimit, coated_only: coatedOnly,
        custom_core: cc ?? {}, mounting: mountDir, optimization_goal: optGoal,
      }) as any
      const candidates = d.top_5 ?? []
      const passing = candidates.filter((c:any) => c.result?.passed)
      const best = passing.length ? passing[0] : candidates[0]
      const top = best?.result ?? null
      if (top) { top.label = best?.label ?? ''; top.rank = best?.rank ?? 1 }
      if (!top) { setErr(['No suitable core found — try larger height or different material']); setLoad(false); return }
      setAllCandidates(candidates)
      enrichResult(top, 0, nPar, winding)   // enrich best candidate
      setSub('result'); setLoad(false)
      runStep8For(top)   // auto-run Step 8 for the initially-selected candidate
    } catch(e) { setErr([String(e)||'Sizing failed']); setLoad(false) }
  }

  const isPowder = matType === 'powder'

  return (
    <div style={{ width:'100%', padding:'0 0 40px' }}>
      <StepBar sub={sub} isPowder={isPowder} />
      <ErrBanner errors={err} />

      {/* ══ GATE 1: MATERIAL TYPE ══════════════════════════════════════════ */}
      {sub === 'material' && (
        <Card>
          <SecHead icon="🧲" label="Select Material Type"
            sub={`fsw=${(fsw_Hz/1000).toFixed(0)}kHz  L=${L_uH}µH`} />
          {isMedical && (
            <div style={{background:C.tealL,border:`1px solid ${C.teal}44`,borderRadius:8,
              padding:'9px 14px',marginBottom:14,fontSize:12,color:C.teal}}>
              Medical — both ferrite (extended-flange bobbin) and powder toroid (Coated) qualify for IEC 60601-1 creepage.
            </div>
          )}
          <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:12,marginBottom:14}}>
            {(['powder','ferrite'] as const).map(mt => {
              const info = matComp ? (matComp as any)[mt] : null
              const act = matType===mt
              return (
                <div key={mt} onClick={()=>setMatType(mt)} style={{
                  border:`2px solid ${act?C.accent:C.border}`,borderRadius:10,
                  padding:'14px 16px',cursor:'pointer',
                  background:act?C.accentL:C.bg3,transition:'all .15s',
                }}>
                  <div style={{fontWeight:600,color:act?C.accent:C.text,marginBottom:8,fontSize:14}}>
                    {act?'● ':'○ '}{info?.label ?? mt}
                  </div>
                  {info && (
                    <div style={{fontSize:11,color:C.muted,lineHeight:1.8}}>
                      <div><span style={{color:C.hint}}>Shapes: </span>{info.shapes}</div>
                      <div><span style={{color:C.hint}}>DC bias: </span>{info.dc_bias}</div>
                      <div><span style={{color:C.hint}}>Loss: </span>{info.core_loss_at_70kHz}</div>
                    </div>
                  )}
                </div>
              )
            })}
          </div>
          <div className="ab">
            <div />
            <div style={{display:'flex',gap:8}}>
              <Btn variant="ghost" onClick={onBack}>← Back</Btn>
              <Btn variant="primary" onClick={()=>setSub(matType==='powder'?'powder_rank':'ferrite_grade')}>
                Continue →
              </Btn>
            </div>
          </div>
        </Card>
      )}

      {/* ══ GATE 2A: POWDER MATERIAL RANKING (9 materials) ════════════════ */}
      {sub === 'powder_rank' && (
        <Card>
          <SecHead icon="📊" label="Select Core Material" />

          {loading ? (
            <div style={{display:'flex',alignItems:'center',gap:10,color:C.muted,padding:'20px 0'}}>
              <Spinner />&nbsp;Ranking materials at fsw={fsw_Hz/1000}kHz, Bac=54mT, Ipk={Ipk.toFixed(2)}A…
            </div>
          ) : (
            <>
              {/* Column headers */}
              <div style={{display:'grid',
                gridTemplateColumns:'24px 1fr 90px 90px 70px 70px 60px 60px',
                gap:6,padding:'6px 10px',fontSize:10,color:C.hint,
                fontFamily:'IBM Plex Mono,monospace',textTransform:'uppercase',letterSpacing:'.05em',
                borderBottom:`0.5px solid ${C.border}`,marginBottom:4}}>
                <div>#</div><div>Material</div><div>DC bias</div>
                <div>Core loss</div><div>Temp coeff</div>
                <div>L change</div><div>Cost</div><div>Score</div>
              </div>

              {powderRanked.map((m,i) => {
                const sel = selMaterial === m.material_key
                return (
                  <div key={m.material_key} onClick={()=>setSelMaterial(m.material_key)}
                    style={{display:'grid',
                      gridTemplateColumns:'24px 1fr 90px 90px 70px 70px 60px 60px',
                      gap:6,padding:'10px 10px',cursor:'pointer',borderRadius:8,
                      marginBottom:3,
                      border:`1.5px solid ${sel?C.accent:'transparent'}`,
                      background:sel?C.accentL:i%2===0?C.bg2:C.bg3,
                      transition:'all .12s',
                    }}>
                    {/* Rank */}
                    <div style={{fontFamily:'IBM Plex Mono,monospace',fontSize:11,
                      color:i<3?C.green:C.hint,fontWeight:i<3?600:400}}>
                      {i<3?'★':' '}{i+1}
                    </div>
                    {/* Material name + best-for */}
                    <div>
                      <div style={{fontWeight:sel?600:500,fontSize:13,
                        color:sel?C.accent:C.text,marginBottom:2}}>
                        {m.grade}
                        {sel && <span style={{fontSize:10,color:C.accent,marginLeft:6}}>✓ selected</span>}
                      </div>
                      <div style={{fontSize:10,color:C.muted,lineHeight:1.4}}>{m.best_for}</div>
                    </div>
                    {/* DC bias */}
                    <div>
                      <div style={{fontSize:12,fontFamily:'IBM Plex Mono,monospace',
                        color:K_COLOR(m.k_bias_est),fontWeight:600}}>
                        {(m.k_bias_est*100).toFixed(0)}%
                      </div>
                      <div style={{height:3,borderRadius:2,background:C.border,overflow:'hidden',marginTop:3}}>
                        <div style={{width:`${m.k_bias_est*100}%`,height:'100%',
                          background:K_COLOR(m.k_bias_est),borderRadius:2}}/>
                      </div>
                    </div>
                    {/* Core loss */}
                    <div style={{fontFamily:'IBM Plex Mono,monospace',fontSize:11,
                      color:m.Pv_kW_m3<60?C.green:m.Pv_kW_m3<120?C.teal:m.Pv_kW_m3<200?C.amber:C.red}}>
                      {m.Pv_kW_m3.toFixed(0)} kW/m³
                    </div>
                    {/* Temp coeff */}
                    <div style={{fontFamily:'IBM Plex Mono,monospace',fontSize:11,
                      color:m.temp_coeff_ppm_C===0?C.green:m.temp_coeff_ppm_C<50?C.teal:m.temp_coeff_ppm_C<100?C.amber:C.red}}>
                      {m.temp_coeff_ppm_C===0?'0 ★':`${m.temp_coeff_ppm_C}`} ppm
                    </div>
                    {/* L variation */}
                    <div style={{fontFamily:'IBM Plex Mono,monospace',fontSize:11,
                      color:m.L_variation_pct<20?C.green:m.L_variation_pct<40?C.amber:C.red}}>
                      −{m.L_variation_pct}%
                    </div>
                    {/* Cost */}
                    <div style={{fontSize:12,color:m.cost_label==='$$$'?C.red:m.cost_label==='$$'?C.amber:C.green,
                      fontWeight:500}}>
                      {m.cost_label}
                    </div>
                    {/* Score */}
                    <div style={{fontFamily:'IBM Plex Mono,monospace',fontSize:12,
                      fontWeight:600,color:SCORE_COLOR(m.score)}}>
                      {m.score.toFixed(1)}
                    </div>
                  </div>
                )
              })}

              {/* Legend */}
              <div style={{marginTop:12,padding:'10px 12px',background:C.bg3,
                borderRadius:8,fontSize:11,color:C.muted,lineHeight:1.8}}>
                <strong style={{color:C.text}}>How to read:</strong>&nbsp;
                DC bias = inductance retention at full-load H field (higher = better) ·
                L change = how much inductance drops from no-load to full-load ·
                Score = composite (bias 35% + loss 25% + temp 15% + cost 15% + Bsat 10%) — lower is better
              </div>
            </>
          )}

          <div className="ab" style={{marginTop:12}}>
            <div style={{fontSize:12,fontFamily:'IBM Plex Mono,monospace',color:C.green}}>
              {selMaterial && powderRanked.find(m=>m.material_key===selMaterial)?.grade}
              {selMaterial && ` selected — L drops ~${powderRanked.find(m=>m.material_key===selMaterial)?.L_variation_pct ?? 0}% at full load`}
            </div>
            <div style={{display:'flex',gap:8}}>
              <Btn variant="ghost" onClick={()=>setSub('material')}>← Back</Btn>
              <Btn variant="primary" onClick={()=>setSub('wire')} disabled={!selMaterial||loading}>
                Wire + constraints →
              </Btn>
            </div>
          </div>
        </Card>
      )}

      {/* ══ GATE 2B: FERRITE GRADE ══════════════════════════════════════════ */}
      {sub === 'ferrite_grade' && (
        <Card>
          <SecHead icon="📊" label="Gate 2 — Ferrite grade selection" sub="agent-ranked by loss · Bsat · topology fit" />
          <div style={{display:'flex',gap:8,marginBottom:14,flexWrap:'wrap'}}>
            {suppliers.map(s => (
              <div key={s.key} onClick={()=>setSupplier(s.key)}
                style={{padding:'5px 12px',borderRadius:8,cursor:'pointer',fontSize:12,
                  fontFamily:'IBM Plex Mono,monospace',
                  border:`1px solid ${supplier===s.key?C.accent:C.border}`,
                  background:supplier===s.key?C.accentL:C.bg3,
                  color:supplier===s.key?C.accent:C.muted}}>
                {s.label}
              </div>
            ))}
          </div>
          {loading ? <div style={{display:'flex',gap:10,color:C.muted,padding:'16px 0'}}><Spinner/>&nbsp;Loading grades…</div> : (
            <table style={{width:'100%',borderCollapse:'collapse',fontSize:12,marginBottom:12}}>
              <thead>
                <tr style={{background:C.bg3,borderBottom:`0.5px solid ${C.border}`}}>
                  {['#','Grade','Pv@op kW/m³','Bsat T','PFC fit','Quality',''].map(h=>(
                    <th key={h} style={{padding:'7px 8px',textAlign:'left',color:C.hint,
                      fontFamily:'IBM Plex Mono,monospace',fontWeight:400,fontSize:10}}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {grades.map((g,i) => {
                  const act = selGrade===g.material_key
                  return (
                    <tr key={g.material_key} onClick={()=>setSelGrade(g.material_key)}
                      style={{cursor:'pointer',background:act?C.accentL:i%2===0?C.bg2:C.bg3,
                        borderBottom:`0.5px solid ${C.border}`}}>
                      <td style={{padding:'8px 8px',color:C.hint,fontFamily:'IBM Plex Mono,monospace'}}>{g.rank}</td>
                      <td style={{padding:'8px 8px',fontWeight:act?600:400,
                        color:act?C.accent:C.text,fontFamily:'IBM Plex Mono,monospace'}}>{g.grade}</td>
                      <td style={{padding:'8px 8px',fontFamily:'IBM Plex Mono,monospace'}}>{g.Pv_kW_m3?.toFixed(1)}</td>
                      <td style={{padding:'8px 8px',fontFamily:'IBM Plex Mono,monospace'}}>{g.Bsat_T?.toFixed(3)}</td>
                      <td style={{padding:'8px 8px'}}><span style={{
                        color:({best:C.green,good:C.teal,ok:C.amber,poor:C.red} as any)[g.topology_fit]??C.muted,
                        fontSize:11,fontFamily:'IBM Plex Mono,monospace'}}>{g.topology_fit}</span></td>
                      <td style={{padding:'8px 8px',fontSize:10,color:C.hint}}>{g.data_quality?.split('_').join(' ')}</td>
                      <td style={{padding:'8px 8px'}}>{act&&<span style={{color:C.accent}}>✓</span>}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          )}
          <div className="ab">
            <div style={{fontSize:11,fontFamily:'IBM Plex Mono,monospace',color:C.green}}>{selGrade}</div>
            <div style={{display:'flex',gap:8}}>
              <Btn variant="ghost" onClick={()=>setSub('material')}>← Back</Btn>
              <Btn variant="primary" onClick={()=>setSub('wire')} disabled={!selGrade||loading}>
                Wire + constraints →
              </Btn>
            </div>
          </div>
        </Card>
      )}

      {/* ══ GATE 3: WIRE + SIZE + WINDING ═════════════════════════════════ */}
      {sub === 'wire' && (
        <Card>
          <SecHead icon="🔌" label="Wire, winding style and size constraints" />

          <div style={{display:'grid',gridTemplateColumns:'1fr 1fr 1fr',gap:16,marginBottom:16}}>
            {/* Wire type */}
            <div>
              <div style={{fontSize:10,color:C.hint,fontFamily:'IBM Plex Mono,monospace',
                textTransform:'uppercase',letterSpacing:'.06em',marginBottom:8}}>Wire type</div>
              {[{k:'magnet',l:'Magnet wire', d:'Rubadue single-build enamel. Standard for PFC inductors.'},
                {k:'litz',  l:'Litz wire',    d:'Stranded — lower AC resistance >20 kHz. Higher cost.'},
                {k:'tiw',   l:'TIW wire',      d:isMedical?'★ Medical: triple-insulated, no Kapton.':'Triple-insulated for isolation.'}
              ].map(wt => (
                <div key={wt.k} onClick={()=>setWireType(wt.k as any)}
                  style={{border:`1.5px solid ${wireType===wt.k?C.accent:C.border}`,
                    borderRadius:8,padding:'9px 12px',cursor:'pointer',marginBottom:8,
                    background:wireType===wt.k?C.accentL:C.bg3}}>
                  <div style={{fontWeight:500,color:wireType===wt.k?C.accent:C.text,fontSize:12}}>
                    {wireType===wt.k?'● ':'○ '}{wt.l}
                  </div>
                  <div style={{fontSize:11,color:C.muted,marginTop:2}}>{wt.d}</div>
                </div>
              ))}
            </div>

            {/* Winding style */}
            <div>
              <div style={{fontSize:10,color:C.hint,fontFamily:'IBM Plex Mono,monospace',
                textTransform:'uppercase',letterSpacing:'.06em',marginBottom:8}}>Winding style</div>
              {WINDING_OPTS.map(w => (
                <div key={w.key} onClick={()=>setWinding(w.key)}
                  style={{border:`1.5px solid ${winding===w.key?C.teal:C.border}`,
                    borderRadius:8,padding:'9px 12px',cursor:'pointer',marginBottom:8,
                    background:winding===w.key?C.tealL:C.bg3}}>
                  <div style={{fontWeight:500,color:winding===w.key?C.teal:C.text,fontSize:12}}>
                    {winding===w.key?'● ':'○ '}{w.label}
                    {w.key==='bifilar'&&isMedical&&<span style={{fontSize:10,color:C.green,marginLeft:6}}>★ Medical</span>}
                  </div>
                  <div style={{fontSize:10,color:C.muted,marginTop:2}}>{w.desc}</div>
                </div>
              ))}
            </div>

            {/* Size + J */}
            <div>
              <div style={{fontSize:10,color:C.hint,fontFamily:'IBM Plex Mono,monospace',
                textTransform:'uppercase',letterSpacing:'.06em',marginBottom:4}}>Max core height</div>
              <div style={{fontSize:9,color:C.hint,marginBottom:6,lineHeight:1.4}}>
                3-stack designs need ≥60 mm. Use 2U or No limit to see them.
              </div>
              {HEIGHT_PRESETS.map(p => (
                <div key={p.label} onClick={()=>setMaxH(p.value)}
                  style={{display:'flex',alignItems:'center',gap:6,cursor:'pointer',
                    padding:'6px 10px',borderRadius:7,marginBottom:5,fontSize:12,
                    border:`1px solid ${maxH===p.value?C.accent:C.border}`,
                    background:maxH===p.value?C.accentL:C.bg3,
                    color:maxH===p.value?C.accent:C.muted}}>
                  {maxH===p.value?'●':'○'} {p.label}
                </div>
              ))}
              <div style={{marginTop:10,fontSize:10,color:C.hint,
                fontFamily:'IBM Plex Mono,monospace',textTransform:'uppercase',
                letterSpacing:'.06em',marginBottom:4}}>Max stacks</div>
              <div style={{display:'flex',gap:5}}>
                {[1,2,3,4].map(n=>(
                  <div key={n} onClick={()=>setMaxStacks(n)}
                    style={{padding:'5px 10px',borderRadius:7,cursor:'pointer',fontSize:12,
                      fontFamily:'IBM Plex Mono,monospace',
                      border:`1px solid ${maxStacks===n?C.accent:C.border}`,
                      background:maxStacks===n?C.accentL:C.bg3,
                      color:maxStacks===n?C.accent:C.muted,fontWeight:maxStacks===n?600:400}}>
                    {n}
                  </div>
                ))}
              </div>
              <div style={{marginTop:10,fontSize:10,color:C.hint,
                fontFamily:'IBM Plex Mono,monospace',textTransform:'uppercase',
                letterSpacing:'.06em',marginBottom:6}}>Mounting orientation</div>
              {([
                {k:'horizontal',l:'Horizontal',d:'Cores flat, stacked on top of each other. Height = wound HT × stacks.'},
                {k:'vertical',  l:'Vertical',  d:'Cores upright, side by side. Height = wound OD of one core (no stack multiply).'},
              ] as const).map(m=>(
                <div key={m.k} onClick={()=>setMountDir(m.k)}
                  style={{border:`1px solid ${mountDir===m.k?C.accent:C.border}`,
                    borderRadius:7,padding:'7px 10px',cursor:'pointer',marginBottom:5,
                    background:mountDir===m.k?C.accentL:C.bg3}}>
                  <div style={{fontSize:11,fontWeight:500,color:mountDir===m.k?C.accent:C.text}}>
                    {mountDir===m.k?'● ':'○ '}{m.l}
                  </div>
                  <div style={{fontSize:10,color:C.muted,marginTop:2,lineHeight:1.4}}>{m.d}</div>
                </div>
              ))}
              <div style={{marginTop:10,fontSize:10,color:C.hint,
                fontFamily:'IBM Plex Mono,monospace',textTransform:'uppercase',
                letterSpacing:'.06em',marginBottom:4}}>J limit — colour guide only</div>
              <input type="range" min={3} max={10} step={0.5} value={jTarget}
                onChange={e=>setJTarget(+e.target.value)} style={{width:'100%',accentColor:C.accent}}/>
              <div style={{fontSize:10,color:C.muted,marginTop:2,lineHeight:1.4}}>
                J = {jTarget} A/mm² — colours the table only.
                Select any wire; engine uses your choice.
              </div>
            </div>
          </div>

          {/* Wire options table */}
          <div style={{fontSize:10,color:C.hint,fontFamily:'IBM Plex Mono,monospace',
            textTransform:'uppercase',letterSpacing:'.06em',marginBottom:6}}>
            Wire options — {winding==='bifilar'?'2 conductors wound together':'single conductor'}
          </div>
          {wireReason&&(
            <div style={{padding:'8px 12px',marginBottom:8,borderRadius:7,fontSize:11,
              background:'rgba(255,140,0,0.1)',border:'0.5px solid rgba(255,140,0,0.3)',
              color:'#ffaa44',lineHeight:1.5}}>
              ⚠ {wireReason}
            </div>
          )}
          {loading ? (
            <div style={{display:'flex',gap:10,color:C.muted,padding:'12px 0'}}><Spinner/>&nbsp;Loading wire options…</div>
          ) : (
            <div style={{border:`0.5px solid ${C.border}`,borderRadius:8,overflow:'hidden',marginBottom:10}}>
              <table style={{width:'100%',borderCollapse:'collapse',fontSize:11}}>
                <thead>
                  <tr style={{background:C.bg3,borderBottom:`0.5px solid ${C.border}`}}>
                    {['Designation','d (mm)','Cu (mm²)','J A/mm²','Rac/Rdc','R/m @100°C',''].map(h=>(
                      <th key={h} style={{padding:'6px 8px',textAlign:'left',color:C.hint,
                        fontFamily:'IBM Plex Mono,monospace',fontWeight:400,fontSize:10}}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {wireOptions.map((w,i) => {
                    const wk = wireKey(w)
                    const act = selWire===wk
                    const nPar = winding==='bifilar'?2:winding==='trifilar'?3:1
                    return (
                      <tr key={wk} onClick={()=>setSelWire(wk)}
                        style={{cursor:'pointer',background:act?C.accentL:i%2===0?C.bg2:C.bg3,
                          borderBottom:`0.5px solid ${C.border}`}}>
                        <td style={{padding:'7px 8px',color:act?C.accent:C.text,
                          fontFamily:'IBM Plex Mono,monospace',fontWeight:act?600:400}}>
                          {wk}
                          {nPar>1&&<span style={{fontSize:9,color:C.teal,marginLeft:4}}>×{nPar}</span>}

                          {w.current_ok===false&&<span style={{fontSize:9,color:C.red,marginLeft:4}}>⚠curr</span>}
                        </td>
                        <td style={{padding:'7px 8px',fontFamily:'IBM Plex Mono,monospace'}}>{(w.strand_dia_mm ?? w.diameter_mm ?? w.dia_mm ?? '—') + (w.strand_dia_mm||w.diameter_mm||w.dia_mm ? 'mm' : '')}</td>
                        <td style={{padding:'7px 8px',fontFamily:'IBM Plex Mono,monospace'}}>
                          {(w.Cu_area_mm2*nPar).toFixed(4)} mm²
                        </td>
                        <td style={{padding:'7px 8px',fontFamily:'IBM Plex Mono,monospace',
                          color:w.J_at_Irms>jTarget*1.4?C.red:w.J_at_Irms>jTarget?C.amber:C.green}}>
                          {w.J_at_Irms.toFixed(1)} A/mm²
                        </td>
                        <td style={{padding:'7px 8px',fontFamily:'IBM Plex Mono,monospace',
                          color:(w.Rac_Rdc_eff??1)>1.10?C.red:(w.Rac_Rdc_eff??1)>1.03?C.amber:C.green,
                          cursor:'default'}}
                          title={`F_skin=${(w.F_skin??1).toFixed(3)}× (wire intrinsic at ${Math.round(fsw_Hz/1e3)}kHz)\nRac/Rdc_eff = 1+(IL_HF/IL_rms)²×(F_skin-1)\nApplies only to HF ripple fraction of current`}>
                          {(w.Rac_Rdc_eff??1).toFixed(3)}×
                        </td>
                        <td style={{padding:'7px 8px',fontFamily:'IBM Plex Mono,monospace',color:C.muted}}>
                          {((w.R_per_m_at_T/nPar)*1000).toFixed(2)} mΩ/m
                        </td>
                        <td style={{padding:'7px 8px'}}>{act&&<span style={{color:C.accent}}>✓</span>}</td>
                      </tr>
                    )
                  })}
                  {!wireOptions.length&&!loading&&(
                    <tr><td colSpan={7} style={{padding:'14px 10px',color:C.hint,
                      textAlign:'center',lineHeight:1.6}}>
                      {wireReason||'No wires found for this type'}
                    </td></tr>
                  )}
                </tbody>
              </table>
            </div>
          )}


          {/* ── FFcu% designer control ── */}
          <div style={{background:C.bg3,border:`0.5px solid ${C.border}`,borderRadius:10,padding:'14px 16px',marginBottom:12}}>
            <div style={{display:'flex',alignItems:'center',justifyContent:'space-between',marginBottom:8}}>
              <div style={{fontSize:13,fontWeight:500}}>
                Window fill factor FFcu = <span style={{
                  color:FFcuLimit<0.30?C.amber:FFcuLimit<=0.40?C.green:FFcuLimit<=0.50?C.amber:C.red,
                  fontFamily:'IBM Plex Mono,monospace',fontWeight:700
                }}>{(FFcuLimit*100).toFixed(0)}%</span>
              </div>
              <span style={{
                padding:'2px 10px',borderRadius:12,fontSize:10,fontWeight:500,
                background:FFcuLimit<0.30?C.amberL:FFcuLimit<=0.40?C.greenL:FFcuLimit<=0.50?C.amberL:'rgba(226,75,74,.1)',
                color:FFcuLimit<0.30?C.amber:FFcuLimit<=0.40?C.green:FFcuLimit<=0.50?C.amber:C.red,
                border:`0.5px solid ${FFcuLimit<0.30?C.amber:FFcuLimit<=0.40?C.green:FFcuLimit<=0.50?C.amber:C.red}44`,
              }}>
                {FFcuLimit<0.30?'Underutilised':FFcuLimit<=0.40?'✓ Recommended':FFcuLimit<=0.50?'Tight':'⚠ Challenging — Special process needed'}
              </span>
            </div>
            <input type="range" min={0.20} max={0.70} step={0.01} value={FFcuLimit}
              onChange={e=>setFFcuLimit(+e.target.value)}
              style={{width:'100%',accentColor:FFcuLimit<=0.40?C.green:FFcuLimit<=0.50?C.amber:C.red,marginBottom:4}}/>
            <div style={{display:'flex',justifyContent:'space-between',fontSize:9,color:C.hint,marginBottom:8}}>
              <span>20%</span>
              <span style={{color:C.green,fontWeight:600}}>40% optimal</span>
              <span style={{color:C.amber,fontWeight:600}}>50% tight</span>
              <span style={{color:C.red,fontWeight:600}}>70% max</span>
            </div>
            <div style={{display:'grid',gridTemplateColumns:'repeat(4,1fr)',gap:4,marginBottom:8}}>
              {[{r:'20–29%',c:C.amber,t:'Underutilised — core oversized'},
                {r:'30–40%',c:C.green,t:'★ Recommended — ideal balance'},
                {r:'41–50%',c:C.amber,t:'Tight — careful winding needed'},
                {r:'51–70%',c:C.red,  t:'Challenging — Special winding process needed'},
              ].map(({r,c,t})=>(
                <div key={r} style={{padding:'5px 8px',borderRadius:6,background:c+'14',
                  border:`0.5px solid ${c}44`,fontSize:9,color:c,textAlign:'center',lineHeight:1.4}}>
                  <div style={{fontWeight:600,fontFamily:'IBM Plex Mono,monospace'}}>{r}</div>
                  <div style={{color:C.muted,fontSize:8,marginTop:1}}>{t}</div>
                </div>
              ))}
            </div>
            <div style={{fontSize:11,color:C.muted,lineHeight:1.6}}>
              <strong style={{color:C.text}}>What is FFcu?</strong> — the fraction of the winding window
              occupied by bare copper. FFcu = N × wire_Cu_area / Wa<sub>single</sub>.
              Recommended ≤40% for standard powder toroids; 41–50% requires careful winding;
              51–70% is achievable but needs a specialist winding house with dedicated tooling.
              Bifilar doubles the wire area per turn, so fewer turns fit.
            </div>
          </div>

          {/* ── Shortlist priority (optimisation goal) ── */}
          <div style={{background:C.bg3,border:`0.5px solid ${C.border}`,borderRadius:10,
            padding:'14px 16px',marginBottom:12}}>
            <div style={{fontSize:10,color:C.hint,fontFamily:'IBM Plex Mono,monospace',
              textTransform:'uppercase',letterSpacing:'.06em',marginBottom:10}}>Shortlist priority</div>
            <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:8}}>
              {([
                {k:'best_performance', l:'Best Performance',
                  d:'Lowest total loss + best DC bias headroom. Highest efficiency design.'},
                {k:'max_ffu',          l:'Max FFcu — Smallest Core',
                  d:'Highest window utilisation first. Shows most compact option for the chosen wire.'},
              ] as {k:'best_performance'|'max_ffu', l:string, d:string}[]).map(o=>(
                <div key={o.k} onClick={()=>setOptGoal(o.k)}
                  style={{border:`1.5px solid ${optGoal===o.k?C.accent:C.border}`,borderRadius:8,
                    padding:'10px 12px',cursor:'pointer',
                    background:optGoal===o.k?C.accentL:C.bg2}}>
                  <div style={{fontWeight:600,color:optGoal===o.k?C.accent:C.text,fontSize:12,marginBottom:3}}>
                    {optGoal===o.k?'● ':'○ '}{o.l}
                  </div>
                  <div style={{fontSize:10,color:C.muted,lineHeight:1.45}}>{o.d}</div>
                </div>
              ))}
            </div>
            <div style={{fontSize:10,color:C.hint,marginTop:8,lineHeight:1.5}}>
              Both modes apply the same pass/fail gates (FFcu limit, saturation, ΔT). Only the
              ordering within each stack tier changes. Run sizing once per mode to compare.
            </div>
          </div>

          {/* ── Coated core toggle ── */}
          {wireType==='tiw'&&(
            <div style={{background:C.tealL,border:`0.5px solid ${C.teal}44`,
              borderRadius:8,padding:'8px 12px',marginBottom:8,fontSize:11,color:C.teal}}>
              🔒 TIW wire is triple-insulated — Medical creepage is met by the wire itself.
              Core coating filter disabled automatically.
            </div>
          )}
          <div style={{display:'flex',alignItems:'center',gap:12,padding:'10px 14px',
            background:coatedOnly?C.greenL:C.amberL,
            border:`0.5px solid ${coatedOnly?C.green+'44':C.amber+'44'}`,
            borderRadius:8,marginBottom:12,cursor:'pointer'}}
            onClick={()=>setCoatedOnly(!coatedOnly)}>
            <div style={{fontSize:18}}>{coatedOnly?'✓':'○'}</div>
            <div>
              <div style={{fontSize:12,fontWeight:500,color:coatedOnly?C.green:C.amber}}>
                Coated toroids only {coatedOnly?'(enabled)':'(disabled)'}
              </div>
              <div style={{fontSize:11,color:C.muted}}>
                {coatedOnly
                  ? 'Only phenolic/epoxy coated cores shown. Recommended for Medical — moisture and abrasion protection.'
                  : 'Bare cores included. Note: bare cores require additional protection for Medical IEC 60601-1.'}
              </div>
            </div>
          </div>

          {/* ── Custom core entry ── */}
          <div style={{border:`0.5px solid ${C.border}`,borderRadius:10,marginBottom:12,overflow:'hidden'}}>
            <div style={{display:'flex',alignItems:'center',justifyContent:'space-between',
              padding:'10px 14px',background:C.bg3,cursor:'pointer'}}
              onClick={()=>setShowCustom(!showCustom)}>
              <div style={{fontSize:12,fontWeight:500}}>
                {showCustom?'▾':'▸'} Enter custom core dimensions (optional)
              </div>
              <div />
            </div>
            {showCustom&&(
              <div style={{padding:'14px 16px'}}>
                <div style={{fontSize:11,color:C.amber,marginBottom:10,lineHeight:1.5}}>
                  Enter your toroid dimensions. AL values from manufacturer datasheet.
                  If custom core is filled, it will be evaluated first and shown in results.
                </div>
                <div style={{display:'grid',gridTemplateColumns:'repeat(3,1fr)',gap:10}}>
                  {[
                    {l:'Part number',  k:'part_number',  ph:'e.g. 0059894A2'},
                    {l:'OD (mm)',      k:'OD_mm',        ph:'e.g. 27.69'},
                    {l:'ID (mm)',      k:'ID_mm',        ph:'e.g. 14.10'},
                    {l:'Height (mm)',  k:'HT_mm',        ph:'e.g. 11.94'},
                    {l:'AL nom (nH)',  k:'AL_nom_nH',    ph:'e.g. 75'},
                    {l:'AL min (nH)', k:'AL_min_nH',    ph:'leave blank = AL_nom×0.92'},
                    {l:'Wa (mm²)',     k:'Wa_mm2',       ph:'window area e.g. 156'},
                    {l:'Ve (cm³)',     k:'Ve_cm3',       ph:'core volume e.g. 5.33'},
                    {l:'Le (mm)',      k:'Le_mm',        ph:'mean path length e.g. 65.5'},
                  ].map(({l,k,ph})=>(
                    <div key={k}>
                      <div style={{fontSize:10,color:C.hint,fontFamily:'IBM Plex Mono,monospace',
                        textTransform:'uppercase',letterSpacing:'.05em',marginBottom:4}}>{l}</div>
                      <input type={k==='part_number'?'text':'number'} placeholder={ph}
                        value={(customCore as any)[k]}
                        onChange={e=>setCustomCore(cc=>({...cc,[k]:e.target.value}))}
                        style={{width:'100%'}}/>
                    </div>
                  ))}
                </div>
                {customCore.part_number&&(
                  <div style={{marginTop:10,fontSize:11,color:C.green,fontFamily:'IBM Plex Mono,monospace'}}>
                    ✓ Custom core will be evaluated: {customCore.part_number}
                    {customCore.AL_nom_nH&&` · AL=${customCore.AL_nom_nH}nH`}
                    {customCore.HT_mm&&` · H=${customCore.HT_mm}mm`}
                  </div>
                )}
                <div style={{marginTop:10,padding:'8px 12px',background:C.bg3,borderRadius:8,
                  fontSize:10,color:C.muted,lineHeight:1.7}}>
                  <strong style={{color:C.text}}>How agent selects AL:</strong> N = ceil(√(L_target / AL_nom)).
                  Then iterates: H_Oe = N × I_dc / Le / 79.577 → k_bias = DC bias rolloff at H_Oe →
                  check N² × AL_min × k_bias ≥ 0.85 × L_target. If not, N++ and repeat.
                  AL_min (worst tolerance) ensures the design holds under production spread.
                </div>
              </div>
            )}
          </div>

          <div className="ab">
            <div style={{fontSize:11,fontFamily:'IBM Plex Mono,monospace',color:C.green}}>
              {selWire&&`${selWire} · ${winding} · ≤${maxH===9999?'∞':maxH}mm · ${maxStacks}-stack max`}
            </div>
            <div style={{display:'flex',gap:8}}>
              <Btn variant="ghost" onClick={()=>setSub(isPowder?'powder_rank':'ferrite_grade')}>← Back</Btn>
              <Btn variant="primary" onClick={runSizing} disabled={!selWire||loading}>
                {loading?'Sizing…':'Finalize Selection →'}
              </Btn>
            </div>
          </div>
          {loading&&<div style={{display:'flex',gap:10,color:C.muted,padding:'10px 0',fontSize:13}}>
            <Spinner/>&nbsp;Running Step 13 sizing engine across catalog…
          </div>}
        </Card>
      )}

      {/* ══ GATE 4: RESULT — two-panel layout (left: selection + actions, right: detail cards) ══ */}
      {sub === 'result' && result && (
        <div style={{display:'grid',gridTemplateColumns:'360px 1fr',gap:16,alignItems:'start'}}>

          {/* ── LEFT PANEL: candidates list + result badge + action bar ── */}
          <div style={{display:'flex',flexDirection:'column',gap:10,position:'sticky',top:16}}>

            {/* Candidates list */}
            {allCandidates.length > 1 && (
              <div>
                <div style={{fontSize:10,color:C.hint,fontFamily:'IBM Plex Mono,monospace',
                  textTransform:'uppercase',letterSpacing:'.06em',marginBottom:6}}>
                  Top {allCandidates.length} candidates — click to select
                </div>
                {allCandidates.map((c:any, i:number) => {
                  const r = c.result ?? {}
                  const isSelected = selectedCandIdx === i
                  return (
                    <div key={i} onClick={() => { const _np = winding==='bifilar'?2:winding==='trifilar'?3:1; enrichResult(r, i, _np, winding); runStep8For(r) }} style={{
                      display:'flex',alignItems:'flex-start',gap:8,padding:'8px 12px',
                      borderRadius:8,marginBottom:4,cursor:'pointer',
                      border:`1.5px solid ${isSelected?C.accent:r.passed?C.green+'44':C.border}`,
                      background:isSelected?C.accentL:C.bg2,
                    }}>
                      <span style={{fontSize:10,color:C.hint,minWidth:18,paddingTop:2}}>#{i+1}</span>
                      <div style={{flex:1,minWidth:0}}>
                        <div style={{display:'flex',alignItems:'center',gap:5,flexWrap:'wrap',marginBottom:2}}>
                          <span style={{fontFamily:'IBM Plex Mono,monospace',fontWeight:500,fontSize:12,
                            color:isSelected?C.accent:C.text}}>
                            {r.part_number}
                            {r.stacks>1&&<span style={{fontSize:10,color:C.teal,marginLeft:5}}>×{r.stacks}</span>}
                            {matMu(r.material_key)&&<span style={{fontSize:9,color:C.hint,marginLeft:5}}>µ={matMu(r.material_key)}</span>}
                          </span>
                          {c.label&&(()=>{
                            const lbl:string=c.label
                            const isOverall=lbl.includes('Best overall'),isBest=lbl.startsWith('★')
                            const isSmall=lbl.includes('Smallest'),isEcon=lbl.includes('economical')
                            const bg=isOverall?C.greenL:isBest?C.accentL:isSmall?C.tealL:isEcon?C.amberL:C.bg3
                            const fg=isOverall?C.green:isBest?C.accent:isSmall?C.teal:isEcon?C.amber:C.hint
                            const bd=isOverall?C.green:isBest?C.accent:isSmall?C.teal:isEcon?C.amber:C.border
                            return <span style={{fontSize:8,padding:'1px 6px',borderRadius:8,fontWeight:600,
                              background:bg,color:fg,border:`0.5px solid ${bd}44`,whiteSpace:'nowrap'}}>{lbl}</span>
                          })()}
                        </div>
                        <div style={{fontSize:9,fontFamily:'IBM Plex Mono,monospace',color:C.muted}}>
                          N={r.N} · AL={Math.round((r.AL_nom_nH??0)*(r.stacks??1))}nH · L={Math.round(r.L0_nom_uH??0)}µH · FFcu={(r.FFcu*100).toFixed(0)}%
                          {' '}· ΔT={r.dT_rise_C?.toFixed(0)}°C · P={r.Ptotal_100C_W?.toFixed(2)}W
                        </div>
                      </div>
                      <span style={{fontSize:9,paddingTop:2,flexShrink:0,color:r.passed?C.green:C.amber}}>{r.passed?'✓':'⚠'}</span>
                    </div>
                  )
                })}
              </div>
            )}

            {/* Result badge */}
            <div style={{background:result.passed?C.greenL:C.amberL,
              border:`1px solid ${result.passed?C.green+'44':C.amber+'44'}`,borderRadius:10,padding:'12px 14px'}}>
              <div style={{display:'flex',alignItems:'center',gap:10}}>
                <div style={{fontSize:22}}>{result.passed?'✓':'⚠'}</div>
                <div style={{flex:1,minWidth:0}}>
                  <div style={{fontWeight:600,fontSize:15,color:result.passed?C.green:C.amber,
                    fontFamily:'IBM Plex Mono,monospace',overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}>
                    {result.part_number}
                    {result.stacks>1&&<span style={{fontSize:12,marginLeft:6}}>× {result.stacks} stack</span>}
                  </div>
                  <div style={{fontSize:11,color:C.muted,marginTop:2,lineHeight:1.4}}>
                    {fmtMat(result.material_key||selMaterial||selGrade)}<br/>
                    {winding} · {selWire}
                    {result.stacks>1&&` · N=${result.N} turns`}
                  </div>
                </div>
              </div>
              {s8Loading&&<div style={{display:'flex',alignItems:'center',gap:6,fontSize:11,color:C.muted,marginTop:8}}>
                <Spinner/>Running Step 8…</div>}
              {step8&&!s8Loading&&<div style={{marginTop:8}}>
                <span className="badge badge-g">Step 8 complete ✓</span></div>}
            </div>

            {/* Status messages */}
            {!step8&&s8Loading&&(
              <div style={{display:'flex',gap:8,color:C.muted,fontSize:12}}>
                <Spinner/>&nbsp;Step 8 time-domain analysis…
              </div>
            )}
            {result.fail_reasons?.length>0&&(
              <div style={{background:C.amberL,border:`0.5px solid ${C.amber}44`,
                borderRadius:8,padding:'8px 12px',fontSize:11,color:C.amber}}>
                ⚠ {result.fail_reasons.join(' · ')}
              </div>
            )}

            {/* Action bar */}
            <div style={{display:'flex',gap:8,paddingTop:8,borderTop:`0.5px solid ${C.border}`,justifyContent:'space-between',alignItems:'center'}}>
              <Btn variant="ghost" onClick={()=>setSub('wire')}>← Back</Btn>
              {step8 && (
                <Btn variant="primary" onClick={()=>setSub('review')} style={{padding:'9px 20px',fontSize:13}}>
                  🔍 Review
                </Btn>
              )}
              {!step8 && <div style={{fontSize:11,color:C.muted}}>Awaiting Step 8…</div>}
            </div>
          </div>

          {/* ── RIGHT PANEL: 4 detail cards (2×2) + Step 8 table ── */}
          <div>
            <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:12,marginBottom:14}}>

              {/* Winding */}
              <Card style={{margin:0}}>
                <div style={{fontSize:10,color:C.accent,fontFamily:'IBM Plex Mono,monospace',
                  textTransform:'uppercase',letterSpacing:'.06em',marginBottom:10}}>Winding design</div>
                {[
                  ['N turns',                String(result.N)],
                  ['Winding style',          winding + (result.n_parallel>1?` (×${result.n_parallel} parallel)`:'')],
                  ['Wire',                   selWire],
                  ['Wire OD',                result.wire_OD_mm?.toFixed(2)+' mm'],
                  ['Window fill FFcu',       (result.FFcu*100).toFixed(1)+'%'],
                  ['Installed height ('+( result.mounting??mountDir)+')', result.installed_height_mm?.toFixed(1)+' mm'],
                  ['Wound HT (horizontal)',  result.wound_HT_actual_mm?.toFixed(1)+' mm'],
                  ['Wound OD (vertical)',    result.wound_OD_actual_mm?.toFixed(1)+' mm'],
                  ['Bmax T',                 result.Bmax_FL_T?.toFixed(4)],
                  ['Bsat margin',            result.sat_margin_pct?.toFixed(0)+'%'],
                ].map(([k,v])=>(
                  <div key={k} className="kv">
                    <span style={{color:C.muted}}>{k}</span>
                    <span className="mono" style={{fontWeight:500}}>{v}</span>
                  </div>
                ))}
              </Card>

              {/* Inductance */}
              <Card style={{margin:0}}>
                <div style={{fontSize:10,color:C.accent,fontFamily:'IBM Plex Mono,monospace',
                  textTransform:'uppercase',letterSpacing:'.06em',marginBottom:10}}>Inductance vs DC bias</div>
                {[
                  ['Target L ≥',         `${L_uH} µH`],
                  ['AL nom (single core)',`${result.AL_nom_nH?.toFixed(0) ?? '—'} nH/T²`],
                  ['AL nom (total ×'+String(result.stacks??1)+')',`${Math.round((result.AL_nom_nH??0)*(result.stacks??1))} nH/T²`],
                  ['AL tolerance',       `±${result.AL_tol_pct?.toFixed(0) ?? '8'}%`],
                  ['L no-load (H=0)',    `${result.L_no_load_uH ?? L_uH} µH`],
                  // Per-operating-point L_full_nom and L_margin from L_vs_Vin_table
                  ...((result.L_vs_Vin_table ?? []) as any[]).map((r:any) => {
                    const Lnom = Math.round(r.L_full_nom_uH ?? 0)
                    const diff = Lnom - L_uH
                    const pct  = Lnom > 0 ? ((Lnom / L_uH - 1) * 100).toFixed(0) : '—'
                    const col  = diff >= 0 ? 'L_full@'+r.Vin_rms+'Vac ✓' : 'L_full@'+r.Vin_rms+'Vac'
                    const val  = `${Lnom} µH  (${diff >= 0 ? '+' : ''}${diff}µH / ${diff >= 0 ? '+' : ''}${pct}%)`
                    return [col, val] as [string, string]
                  }),
                  ['L variation (no-load→full-load)', `−${result.L_variation_pct ?? '—'}%`],
                  ['k_bias actual (DB)',              result.kbias?.toFixed(3) ?? result.kreq_nom?.toFixed(3) ?? '—'],
                  ['H_dc at full-load',               result.H_Oe_design != null ? result.H_Oe_design.toFixed(1)+' Oe' : '—'],
                ].map(([k,v])=>{
                  const isLfull   = k.startsWith('L_full@')
                  const isBelow   = isLfull && v.includes('-')
                  const isAbove   = isLfull && !isBelow
                  const valColor  = k==='Target L ≥'?C.hint
                                  : k.startsWith('AL')?C.accent
                                  : isAbove?C.green
                                  : isBelow?C.amber
                                  : k.startsWith('L variation')?
                                      (result.L_variation_pct<20?C.green:result.L_variation_pct<40?C.amber:C.red)
                                  : C.text
                  return (
                    <div key={k} className="kv">
                      <span style={{color: isLfull?(isBelow?C.amber:C.green):C.muted}}>{k}</span>
                      <span className="mono" style={{fontWeight:500, color:valColor}}>{v as string}</span>
                    </div>
                  )
                })}
                {(()=>{
                  const kActual = result.kbias ?? result.kreq_nom ?? 0.8
                  return (
                    <div style={{marginTop:12}}>
                      <div style={{fontSize:10,color:C.hint,marginBottom:4}}>L range: no-load → full-load</div>
                      <div style={{height:8,borderRadius:4,background:C.bg3,overflow:'hidden',position:'relative'}}>
                        <div style={{width:'100%',height:'100%',background:C.border,position:'absolute'}}/>
                        <div style={{width:`${kActual*100}%`,height:'100%',background:K_COLOR(kActual),position:'absolute',borderRadius:4}}/>
                        <div style={{position:'absolute',left:`${kActual*100}%`,top:0,width:2,height:'100%',background:C.text}}/>
                      </div>
                      <div style={{display:'flex',justifyContent:'space-between',fontSize:9,color:C.hint,marginTop:2}}>
                        <span>Full load ({result.L_full_load_uH ?? 0}µH)</span>
                        <span>No load ({result.L0_nom_uH ?? result.L_no_load_uH ?? L_uH}µH)</span>
                      </div>
                    </div>
                  )
                })()}
              </Card>

              {/* Losses — three temperatures */}
              {(()=>{
                // 80°C values by linear interpolation: (80-25)/(100-25) = 55/75
                const f80 = 55/75
                const Pcu80  = result.Pcu_25C_W  != null && result.Pcu_100C_W  != null
                  ? result.Pcu_25C_W  + f80 * (result.Pcu_100C_W  - result.Pcu_25C_W)  : null
                const DCR80  = result.DCR_25C_mOhm != null && result.DCR_100C_mOhm != null
                  ? result.DCR_25C_mOhm + f80 * (result.DCR_100C_mOhm - result.DCR_25C_mOhm) : null
                const Ptot80 = Pcu80 != null && result.Pcore_W != null
                  ? Pcu80 + result.Pcore_W + (result.P_fringing_W ?? 0) : null
                // Pout from state for efficiency calc
                const Pout = Number((confirmedState as any)?.intake?.application
                  ?.output_power_w_high_line ?? 3600)
                const eff = (P: number|null) => P != null
                  ? (P/Pout*100).toFixed(3)+'%' : '—'
                const fmt = (v: number|null, d=2) => v != null ? v.toFixed(d)+' W' : '—'
                const fmtR = (v: number|null) => v != null ? v.toFixed(2)+' mΩ' : '—'
                const col = (v: number|null, ref: number|null) =>
                  v == null ? C.text : (v > (ref ?? v)*1.15 ? C.red : v > (ref ?? v)*1.05 ? C.amber : C.text)

                return (
                  <Card style={{margin:0}}>
                    <div style={{fontSize:10,color:C.accent,fontFamily:'IBM Plex Mono,monospace',
                      textTransform:'uppercase',letterSpacing:'.06em',marginBottom:10}}>
                      Losses at operating temperature
                    </div>

                    {/* Column headers */}
                    <div style={{display:'grid',gridTemplateColumns:'1fr 1fr 1fr 1fr',
                      gap:4,marginBottom:6}}>
                      <div style={{fontSize:9,color:C.hint}}>Parameter</div>
                      {['25 °C','80 °C','100 °C'].map(t=>(
                        <div key={t} style={{fontSize:9,fontFamily:'IBM Plex Mono,monospace',
                          color:C.accent,textAlign:'right',fontWeight:600}}>{t}</div>
                      ))}
                    </div>

                    {/* Pcu row */}
                    {[
                      { lbl:'Pcu copper', v25:result.Pcu_25C_W, v80:Pcu80, v100:result.Pcu_100C_W, d:2 },
                      { lbl:'Pcore iron',  v25:result.Pcore_W,    v80:result.Pcore_W, v100:result.Pcore_W, d:3 },
                      { lbl:'Ptotal',      v25:result.Ptotal_25C_W, v80:Ptot80, v100:result.Ptotal_100C_W, d:3 },
                    ].map(({lbl, v25, v80, v100, d})=>(
                      <div key={lbl} style={{display:'grid',gridTemplateColumns:'1fr 1fr 1fr 1fr',
                        gap:4,padding:'4px 0',borderBottom:`0.5px solid ${C.border}`}}>
                        <span style={{fontSize:11,color:C.muted}}>{lbl}</span>
                        <span style={{fontSize:11,fontFamily:'IBM Plex Mono,monospace',
                          textAlign:'right',color:C.text}}>{fmt(v25 as any,d)}</span>
                        <span style={{fontSize:11,fontFamily:'IBM Plex Mono,monospace',
                          textAlign:'right',color:col(v80 as any, v25 as any)}}>{fmt(v80 as any,d)}</span>
                        <span style={{fontSize:11,fontFamily:'IBM Plex Mono,monospace',
                          textAlign:'right',color:lbl==='Ptotal'?C.amber:col(v100 as any, v25 as any)}}>
                          {fmt(v100 as any,d)}
                        </span>
                      </div>
                    ))}

                    {/* Efficiency hit row */}
                    <div style={{display:'grid',gridTemplateColumns:'1fr 1fr 1fr 1fr',
                      gap:4,padding:'4px 0',borderBottom:`0.5px solid ${C.border}`}}>
                      <span style={{fontSize:11,color:C.muted}}>Efficiency hit</span>
                      {[result.Ptotal_25C_W, Ptot80, result.Ptotal_100C_W].map((p,i)=>(
                        <span key={i} style={{fontSize:11,fontFamily:'IBM Plex Mono,monospace',
                          textAlign:'right',color:C.text}}>{eff(p as any)}</span>
                      ))}
                    </div>

                    {/* DCR rows */}
                    <div style={{marginTop:8}}>
                      {[
                        ['R_L cold (25°C)',  fmtR(result.DCR_25C_mOhm)],
                        ['R_L warm (80°C)',  fmtR(DCR80)],
                        ['R_L hot (100°C)',  fmtR(result.DCR_100C_mOhm)],
                      ].map(([k,v])=>(
                        <div key={k} className="kv">
                          <span style={{color:C.muted}}>{k}</span>
                          <span className="mono" style={{fontWeight:500}}>{v}</span>
                        </div>
                      ))}
                    </div>

                    {/* Uncertainty */}
                    <div className="kv" style={{marginTop:4}}>
                      <span style={{color:C.muted}}>Uncertainty range</span>
                      <span className="mono" style={{fontWeight:500,color:C.hint}}>
                        {result.P_unc_lo_W?.toFixed(2) ?? '—'} – {result.P_unc_hi_W?.toFixed(2) ?? '—'} W
                      </span>
                    </div>

                    <div style={{fontSize:9,color:C.hint,marginTop:6,lineHeight:1.4}}>
                      Pcore is the half-cycle averaged value (temperature-independent in this model).
                      80°C values interpolated linearly between 25°C and 100°C.
                    </div>
                  </Card>
                )
              })()}

              {/* Thermal */}
              <Card style={{margin:0}}>
                <div style={{fontSize:10,color:C.accent,fontFamily:'IBM Plex Mono,monospace',
                  textTransform:'uppercase',letterSpacing:'.06em',marginBottom:10}}>Thermal</div>
                {[
                  ['ΔT temperature rise', result.dT_rise_C?.toFixed(1)+'°C'],
                  ['Max operating temp',  `${(50+(result.dT_rise_C??0)).toFixed(0)}°C at Ta=50°C`],
                  ['Thermal resistance',  result.Rth?.toFixed(1)+'°C/W'],
                  ['Status',             result.dT_rise_C<result.dT_budget_C?'✓ within budget':'⚠ exceeds budget'],
                ].map(([k,v])=>(
                  <div key={k} className="kv">
                    <span style={{color:C.muted}}>{k}</span>
                    <span className="mono" style={{fontWeight:500,
                      color:k==='ΔT temperature rise'?DT_COLOR(result.dT_rise_C):
                            k==='Status'?(result.dT_rise_C<result.dT_budget_C?C.green:C.red):C.text}}>{v}</span>
                  </div>
                ))}
              </Card>
            </div>

            {/* Step 8 results */}
            {step8 && (
              <Card style={{border:`0.5px solid ${C.green}44`,marginBottom:12}}>
                <SecHead icon="📈" label="Time domain core loss" />
                <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:10,marginBottom:12}}>
                  <div style={{background:C.bg3,borderRadius:8,padding:'10px 14px'}}>
                    <div style={{fontSize:10,color:C.hint,fontFamily:'IBM Plex Mono,monospace',
                      textTransform:'uppercase',letterSpacing:'.05em',marginBottom:4}}>Power-law fit</div>
                    <div style={{fontFamily:'IBM Plex Mono,monospace',fontSize:14,color:C.accent,fontWeight:500}}>
                      P = {(step8.power_law_fit?.k??0).toFixed(1)} × B^{(step8.power_law_fit?.n??0).toFixed(4)}
                    </div>
                  </div>
                  <div style={{background:C.bg3,borderRadius:8,padding:'10px 14px'}}>
                    <div style={{fontSize:10,color:C.hint,fontFamily:'IBM Plex Mono,monospace',
                      textTransform:'uppercase',letterSpacing:'.05em',marginBottom:4}}>Key finding</div>
                    <div style={{fontSize:11,color:C.amber,lineHeight:1.5}}>
                      Crest-point overestimates at 90V · underestimates at 230V<br/>
                      Time-domain avg is the correct value for thermal budget
                    </div>
                  </div>
                </div>
                <div style={{border:`0.5px solid ${C.border}`,borderRadius:8,overflow:'hidden'}}>
                  <table style={{width:'100%',borderCollapse:'collapse',fontSize:11}}>
                    <thead>
                      <tr style={{background:C.bg3,borderBottom:`0.5px solid ${C.border}`}}>
                        {['Vin rms','Bac pk T','Pcore avg W','Pcore crest W','Avg/Crest'].map(h=>(
                          <th key={h} style={{padding:'6px 8px',textAlign:'left',color:C.hint,
                            fontFamily:'IBM Plex Mono,monospace',fontWeight:400,fontSize:10}}>{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {(step8.summary_table??[]).map((row:any,i:number)=>{
                        const ratio=row.Pcore_pk_W>0?row.Pcore_avg_W/row.Pcore_pk_W:1
                        return (
                          <tr key={i} style={{background:row.Vin_rms===90?C.accentL:i%2===0?C.bg2:C.bg3,
                            borderBottom:`0.5px solid ${C.border}`}}>
                            <td style={{padding:'6px 8px',fontFamily:'IBM Plex Mono,monospace',
                              color:row.Vin_rms===90?C.accent:C.text,fontWeight:row.Vin_rms===90?600:400}}>{row.Vin_rms}V</td>
                            <td style={{padding:'6px 8px',fontFamily:'IBM Plex Mono,monospace'}}>{row.Bac_pk?.toFixed(5)}</td>
                            <td style={{padding:'6px 8px',fontFamily:'IBM Plex Mono,monospace',color:C.green,fontWeight:600}}>{row.Pcore_avg_W?.toFixed(3)}</td>
                            <td style={{padding:'6px 8px',fontFamily:'IBM Plex Mono,monospace',color:C.muted}}>{row.Pcore_pk_W?.toFixed(3)}</td>
                            <td style={{padding:'6px 8px',fontFamily:'IBM Plex Mono,monospace',
                              color:ratio>1.5?C.red:ratio<0.7?C.amber:C.green}}>{(ratio*100).toFixed(0)}%</td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
              </Card>
            )}
          </div>
        </div>
      )}

      {/* ══ REVIEW: full JS studio (iGSE waveforms, sweep, 3D view) ══════════ */}
      {sub === 'review' && result && (
        <ReviewMagnetics
          result={result}
          confirmedState={confirmedState}
          matType={matType}
          selMaterial={selMaterial}
          selGrade={selGrade}
          allCandidates={allCandidates}
          winding={winding}
          step8={step8}
          onBack={()=>setSub('result')}
          onRestart={onRestart}
          onApprove={onApprove ? (design) => onApprove(design) : undefined}
        />
      )}
    </div>
  )
}
