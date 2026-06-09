import React, { useState, useEffect, useRef, useCallback } from 'react'
import { Card, SecHead, Btn, ErrBanner, Spinner, C } from './ui'
import {
  step15CapacitorDesign,
  docGenerateReport,
  step15HvcapFilterOptions, step15HvcapFilterCaps, step15HvcapCapTable,
  step15CapLifetime,
} from '../api/client'

// ── Interfaces ────────────────────────────────────────────────────────────────
export interface ThermalRow {
  Vin_rms: number; Pout_W: number
  I_dc_A: number; I_LF_A: number; I_HF_A: number
  I_cap_total_A: number; I_cap_per_unit_A: number
  I_rated_A: number; P_dissipated_W: number
  dT_rise_C: number; T_cap_C: number
  V_ripple_pp_V: number; ripple_pass: boolean
}
export interface OperatingPointResult {
  V_ripple_pp_V: number; t_holdup_ms: number
  I_rms_per_cap_A: number; I_rms_total_A: number
  I_rated_per_cap_A: number | null; ripple_current_pass: boolean
  V_esr_pk_V: number | null
}
export interface CapacitorResult {
  supplier: string; series: string; voltage_rating: number
  configuration: { value_uF: number; qty: number; part_number?: string }[]
  C_total_uF: number; ESR_parallel_mohm: number
  thermal_table: ThermalRow[]
  worst_case: OperatingPointResult; low_line: OperatingPointResult
  // Carries full part detail through to ControlDesign so the backend can
  // reconstruct verified + thermal for Step 15 sections 15.7+.
  selected_cap?: {
    supplier: string; series: string; voltage_rating_V: number
    value_uF: number; qty: number; part_number: string
    lifetime: string; op_temp: string
    ESR_each_mohm: number; I_rated_A: number | null; temp_rating_C: number
  }
}

interface Props {
  confirmedState: Record<string, unknown>
  approvedDesign: Record<string, unknown>
  onConfirm: (result: CapacitorResult) => void
  onBack: () => void
}

// ── Helpers ───────────────────────────────────────────────────────────────────
const KV = ({ k, v, hi, red }: { k: string; v: string; hi?: boolean; red?: boolean }) => (
  <div style={{ display:'flex',justifyContent:'space-between',padding:'5px 0',
    borderBottom:`0.5px solid ${C.border}` }}>
    <span style={{fontSize:11,color:C.muted}}>{k}</span>
    <span style={{fontSize:11,fontFamily:'IBM Plex Mono,monospace',fontWeight:500,
      color:red?C.red:hi?C.amber:C.text}}>{v}</span>
  </div>
)
const LABEL = (txt: string) => (
  <div style={{fontSize:10,color:C.hint,fontFamily:'IBM Plex Mono,monospace',
    textTransform:'uppercase',letterSpacing:'.05em',marginBottom:4}}>{txt}</div>
)
const Chip = ({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) => (
  <div onClick={onClick} style={{padding:'4px 10px',borderRadius:6,cursor:'pointer',fontSize:11,
    fontFamily:'IBM Plex Mono,monospace',userSelect:'none',transition:'all .12s',
    border:`1px solid ${active?C.accent:C.border}`,
    background:active?C.accentL:C.bg3,
    color:active?C.accent:C.muted,fontWeight:active?600:400}}>{label}</div>
)

// ── Component ─────────────────────────────────────────────────────────────────
export const Step15Capacitor: React.FC<Props> = ({
  confirmedState, approvedDesign, onConfirm, onBack,
}) => {
  // Design requirements
  const [loadingDesign, setLoadingDesign] = useState(true)
  const [design,        setDesign]        = useState<any>(null)
  const [err,           setErr]           = useState<string[]>([])

  // Filter options
  const [filterOpts, setFilterOpts] = useState<any>(null)

  // Filter state — Environment
  const [fVoltage,    setFVoltage]   = useState<number|null>(null)
  const [fOpTemp,     setFOpTemp]    = useState<string|null>(null)
  const [fTolerance,  setFTolerance] = useState<string|null>(null)
  const [fLifetime,   setFLifetime]  = useState<string|null>(null)
  const [fAmbientC,   setFAmbientC]  = useState<number>(45)   // ambient temperature for lifetime

  // Filter state — Dimensions
  const [fLeadSpacing, setFLeadSpacing] = useState<number|null>(null)
  const [fHeightMax,   setFHeightMax]   = useState<number|null>(null)
  const [fDiaMax,      setFDiaMax]      = useState<number|null>(null)

  // Available caps after filtering
  const [availCaps,   setAvailCaps]  = useState<number[]>([])
  const [loadingCaps, setLoadingCaps] = useState(false)

  // Selected capacitance value + qty
  const [selectedCapUF,  setSelectedCapUF]  = useState<number|null>(null)
  const [selectedQty,    setSelectedQty]    = useState(1)

  // Part table from real DB
  const [capTable,      setCapTable]     = useState<any[]>([])
  const [loadingTable,  setLoadingTable] = useState(false)

  // Designer's chosen part from the table
  const [chosenPart, setChosenPart] = useState<any>(null)

  // Lifetime calculation results
  const [lifetime,       setLifetime]       = useState<any>(null)
  const [loadingLifetime,setLoadingLifetime] = useState(false)

  // Report
  const [rptLoading, setRptLoad] = useState(false)
  const [rptError,   setRptError] = useState<string|null>(null)

  // ── Load design requirements ───────────────────────────────────────────────
  useEffect(() => {
    step15CapacitorDesign({ state: confirmedState })
      .then((d: any) => { setDesign(d); setLoadingDesign(false) })
      .catch((e: any) => { setErr([String(e)]); setLoadingDesign(false) })

    step15HvcapFilterOptions().then((d: any) => {
      setFilterOpts(d)
      if (d.voltages?.includes(450)) setFVoltage(450)
      else if (d.voltages?.length) setFVoltage(d.voltages[0])
    }).catch(() => {})
  }, [])

  // ── Reload filtered caps when filters change ──────────────────────────────
  useEffect(() => {
    setLoadingCaps(true)
    step15HvcapFilterCaps({
      voltage_V: fVoltage??undefined, op_temp: fOpTemp??undefined,
      lifetime: fLifetime??undefined, tolerance: fTolerance??undefined,
      lead_spacing_mm: fLeadSpacing??undefined,
      height_max_mm: fHeightMax??undefined, diameter_max_mm: fDiaMax??undefined,
    }).then((d: any) => {
      setAvailCaps(d.capacitances_uF ?? [])
      setLoadingCaps(false)
    }).catch(() => setLoadingCaps(false))
    // Reset selection when filters change
    setSelectedCapUF(null); setCapTable([]); setChosenPart(null)
  }, [fVoltage, fOpTemp, fLifetime, fTolerance, fLeadSpacing, fHeightMax, fDiaMax])

  // ── When cap value is selected, compute min qty and load table ────────────
  const C_req     = design?.C_required_uF ?? 0
  const I_worst   = design?.worst_case?.I_total_A ?? 0

  const computeMinQty = (cap_uF: number) =>
    cap_uF > 0 ? Math.ceil(C_req / cap_uF) : 1

  const loadTable = useCallback((cap_uF: number, qty: number) => {
    setLoadingTable(true)
    setCapTable([])
    step15HvcapCapTable({
      state: confirmedState, capacitance_uF: cap_uF, n_parallel: qty,
      voltage_V: fVoltage??undefined, op_temp: fOpTemp??undefined,
      lifetime: fLifetime??undefined, tolerance: fTolerance??undefined,
      lead_spacing_mm: fLeadSpacing??undefined,
      height_max_mm: fHeightMax??undefined, diameter_max_mm: fDiaMax??undefined,
    }).then((d: any) => {
      setCapTable(d.table ?? [])
      setLoadingTable(false)
    }).catch(() => setLoadingTable(false))
  }, [confirmedState, fVoltage, fOpTemp, fLifetime, fTolerance, fLeadSpacing, fHeightMax, fDiaMax])

  const handlePickCap = (cap_uF: number) => {
    const minQ = computeMinQty(cap_uF)
    setSelectedCapUF(cap_uF)
    setSelectedQty(minQ)
    setChosenPart(null)
    loadTable(cap_uF, minQ)
  }

  // Reload table whenever qty changes (debounced 400ms)
  const qtyDebounce = useRef<ReturnType<typeof setTimeout>|null>(null)
  const handleQtyChange = (newQty: number) => {
    const q = Math.max(1, Math.min(20, newQty))
    setSelectedQty(q)
    setChosenPart(null)
    if (selectedCapUF) {
      if (qtyDebounce.current) clearTimeout(qtyDebounce.current)
      qtyDebounce.current = setTimeout(() => loadTable(selectedCapUF, q), 400)
    }
  }

  // ── Fetch lifetime whenever part or ambient temp changes ─────────────────
  useEffect(() => {
    if (!chosenPart || !chosenPart.part_number) { setLifetime(null); return }
    setLoadingLifetime(true)
    step15CapLifetime({
      state: confirmedState,
      part_number: chosenPart.part_number,
      qty: selectedQty,
      Tamb_C: fAmbientC,
    }).then((d: any) => { setLifetime(d); setLoadingLifetime(false) })
      .catch(() => setLoadingLifetime(false))
  }, [chosenPart, selectedQty, fAmbientC])

  // ── Computed effective parameters ─────────────────────────────────────────
  const C_total     = (selectedCapUF ?? 0) * selectedQty
  const pctOfReq    = C_req > 0 ? Math.min((C_total / C_req) * 100, 100) : 0
  const meetsC      = C_total >= C_req
  const minQtyNeeded = selectedCapUF ? computeMinQty(selectedCapUF) : 1

  // Effective parameters based on chosen part + qty
  const esr_each_mohm  = (chosenPart?.esr_each_ohm ?? 0) * 1000
  const esr_eff_mohm   = selectedQty > 0 ? esr_each_mohm / selectedQty : 0
  const I_per_cap      = selectedQty > 0 ? I_worst / selectedQty : 0
  const I_rated        = chosenPart?.I_rated_120hz_A ?? null
  const ripple_pass    = I_rated !== null ? I_per_cap <= I_rated : null

  const lifetimeOk = lifetime ? lifetime.pass_15yr : true   // allow approve if not yet calculated
  const canApprove = meetsC && !!chosenPart

  // ── Report ─────────────────────────────────────────────────────────────────
  const handleReport = async () => {
    setRptLoad(true)
    setRptError(null)
    try {
      // Build a complete step15_result so the backend can render all 10 sub-steps.
      // The backend will use selected_cap to call verify_configuration + calculate_thermal_table
      // internally and nest the results as "verified" and "thermal" before rendering.
      const selectedCapConfig = chosenPart ? {
        supplier:         chosenPart.manufacturer ?? '',
        series:           chosenPart.series       ?? '',
        voltage_rating_V: chosenPart.voltage_V    ?? 450,
        value_uF:         chosenPart.capacitance_uF ?? selectedCapUF ?? 470,
        qty:              selectedQty,
        part_number:      chosenPart.part_number  ?? '',
        lifetime:         chosenPart.lifetime     ?? '—',
        op_temp:          chosenPart.temp_rating_C != null
                            ? `${chosenPart.temp_rating_C}°C` : '—',
        ESR_each_mohm:    (chosenPart.esr_each_ohm ?? 0) * 1000,
        I_rated_A:        chosenPart.I_rated_120hz_A ?? null,
        temp_rating_C:    chosenPart.temp_rating_C  ?? 85,
      } : null

      const blob = await docGenerateReport({
        state: confirmedState, approved_design: approvedDesign,
        step15_result: {
          ...design,
          // Selected capacitor configuration — backend uses this to build verified + thermal
          ...(selectedCapConfig ? { selected_cap: selectedCapConfig } : {}),
          // Lifetime analysis already computed in the UI
          ...(lifetime         ? { lifetime }                         : {}),
        },
      })
      const url = URL.createObjectURL(blob)
      const a   = document.createElement('a')
      a.href = url
      a.download = `PFC_Report_${(confirmedState as any).project_id ?? 'design'}_Steps1_15.pdf`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      setTimeout(() => URL.revokeObjectURL(url), 150)
    } catch(e) {
      const msg = (e as Error).message ?? String(e)
      console.error('Report generation failed', e)
      setRptError(msg)
    }
    setRptLoad(false)
  }

  if (loadingDesign) return (
    <div style={{display:'flex',gap:10,color:C.muted,padding:'40px 0',justifyContent:'center'}}>
      <Spinner />&nbsp;Calculating capacitor requirements…
    </div>
  )

  const wc = design?.worst_case ?? {}
  const ll = design?.low_line   ?? {}

  return (
    <div style={{width:'100%',padding:'0 0 60px'}}>
      <ErrBanner errors={err} />

      {/* ── 1. Requirements ─────────────────────────────────────────────────── */}
      <Card>
        <SecHead icon="🔋" label="Vout DC Bus Capacitor Design" />
        <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:12,marginBottom:12}}>
          {[['Worst-case',wc],['Low-line',ll]].map(([lbl,op]:any) => (
            <div key={lbl} style={{background:C.bg3,borderRadius:8,padding:'12px 14px'}}>
              <div style={{fontSize:10,color:C.hint,fontFamily:'IBM Plex Mono,monospace',
                textTransform:'uppercase',letterSpacing:'.05em',marginBottom:8}}>
                {lbl} · {op.Vin_rms}Vac · {op.Pout}W
              </div>
              <KV k="C_holdup" v={`${op.C_holdup_uF} µF`} />
              <KV k="C_ripple" v={`${op.C_ripple_uF} µF`} />
              <KV k="I_total"  v={`${op.I_total_A} A`} hi />
            </div>
          ))}
        </div>
        <div style={{background:C.amberL,border:`0.5px solid ${C.amber}44`,borderRadius:8,
          padding:'10px 14px',fontSize:12,marginBottom:8}}>
          <span style={{color:C.hint}}>C required = </span>
          <span style={{fontFamily:'IBM Plex Mono,monospace',fontWeight:700,color:C.amber,fontSize:15}}>
            {design?.C_required_uF} µF
          </span>
          <span style={{color:C.hint,marginLeft:10}}>governing: </span>
          <span style={{color:C.amber}}>{design?.governing}</span>
        </div>
        {/* Worst-case Itotal breakdown */}
        <div style={{background:C.bg3,border:`0.5px solid ${C.border}`,borderRadius:8,padding:'10px 14px'}}>
          <div style={{fontSize:10,color:C.hint,fontFamily:'IBM Plex Mono,monospace',
            textTransform:'uppercase',letterSpacing:'.05em',marginBottom:8}}>
            Worst-case Bank Currents (180 Vac, {wc.Pout}W) — drives cap sizing & lifetime
          </div>
          <div style={{display:'grid',gridTemplateColumns:'repeat(4,1fr)',gap:8}}>
            {[
              ['I_LF (2×fline)', `${wc.I_LF_A ?? '—'} A`],
              ['I_HF (switching)', `${wc.I_HF_A ?? '—'} A`],
              ['I_total bank', `${wc.I_total_A ?? '—'} A`],
              ['I req. = I_total/qty', selectedQty > 0 && I_worst > 0
                ? `${(I_worst/selectedQty).toFixed(3)} A (÷${selectedQty})`
                : '— select qty'],
            ].map(([k,v]) => (
              <div key={k} style={{background:C.bg4,borderRadius:6,padding:'7px 10px'}}>
                <div style={{fontSize:9,color:C.hint,marginBottom:3}}>{k}</div>
                <div style={{fontFamily:'IBM Plex Mono,monospace',fontSize:12,fontWeight:600,
                  color:k.includes('total')?C.amber:C.text}}>{v}</div>
              </div>
            ))}
          </div>
        </div>
      </Card>

      {/* ── 2. Voltage Rating ───────────────────────────────────────────────── */}
      <Card>
        <SecHead icon="⚡" label="Capacitor Voltage Rating" />
        <KV k="Vout × 1.12"      v={`${(design?.inputs?.Vout_V * 1.12).toFixed(1)} V`} />
        <KV k="Required rating ≥" v={`${design?.V_rating_min_V} V`} />
        <div style={{marginTop:6}}><KV k="Selected rating" v={`${design?.V_rating_selected_V} V`} hi /></div>
      </Card>

      {/* ── 3. Filters: Operating Environment + Dimensions ──────────────────── */}
      <Card>
        <SecHead icon="🌡️" label="Cap Operating Environment and Dimensions"
          sub="Filter the parts database by your application requirements" />

        {!filterOpts ? (
          <div style={{color:C.muted,fontSize:12}}><Spinner/>&nbsp;Loading filter options…</div>
        ) : (<>
          <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:16,marginBottom:16}}>
            <div>
              {LABEL('Voltage Rating')}
              <div style={{display:'flex',gap:5,flexWrap:'wrap'}}>
                {(filterOpts.voltages ?? []).map((v:number) => (
                  <Chip key={v} label={`${v}V`} active={fVoltage===v} onClick={()=>setFVoltage(v===fVoltage?null:v)} />
                ))}
              </div>
            </div>
            <div>
              {LABEL('Operating Temperature')}
              <div style={{display:'flex',gap:5,flexWrap:'wrap'}}>
                {(filterOpts.op_temps ?? []).map((t:string) => (
                  <Chip key={t} label={t} active={fOpTemp===t} onClick={()=>setFOpTemp(t===fOpTemp?null:t)} />
                ))}
              </div>
            </div>
            <div>
              {LABEL('Tolerance')}
              <div style={{display:'flex',gap:5,flexWrap:'wrap'}}>
                {(filterOpts.tolerances ?? []).map((t:string) => (
                  <Chip key={t} label={t} active={fTolerance===t} onClick={()=>setFTolerance(t===fTolerance?null:t)} />
                ))}
              </div>
            </div>
            <div>
              {LABEL('Lifetime @ Temp')}
              <select value={fLifetime ?? ''} onChange={e=>setFLifetime(e.target.value||null)}
                style={{width:'100%',padding:'6px 10px',borderRadius:6,border:`1px solid ${C.border}`,
                  background:C.bg3,color:C.text,fontSize:12,fontFamily:'inherit'}}>
                <option value=''>All lifetimes</option>
                {(filterOpts.lifetimes ?? []).map((l:string) => (
                  <option key={l} value={l}>{l}</option>
                ))}
              </select>
            </div>
          </div>

          <div style={{borderTop:`0.5px solid ${C.border}`,paddingTop:14}}>
            <div style={{fontSize:11,fontWeight:600,color:C.text,marginBottom:10}}>Dimensions</div>
            <div style={{display:'grid',gridTemplateColumns:'1fr 1fr 1fr',gap:14}}>
              <div>
                {LABEL('Lead Spacing (mm)')}
                <div style={{display:'flex',gap:5,flexWrap:'wrap'}}>
                  <Chip label="Any" active={fLeadSpacing===null} onClick={()=>setFLeadSpacing(null)} />
                  {(filterOpts.lead_spacings ?? []).map((s:number) => (
                    <Chip key={s} label={`${s}mm`} active={fLeadSpacing===s} onClick={()=>setFLeadSpacing(s===fLeadSpacing?null:s)} />
                  ))}
                </div>
              </div>
              <div>
                {LABEL('Max Height (mm)')}
                <select value={fHeightMax ?? ''} onChange={e=>setFHeightMax(e.target.value?+e.target.value:null)}
                  style={{width:'100%',padding:'6px 10px',borderRadius:6,border:`1px solid ${C.border}`,
                    background:C.bg3,color:C.text,fontSize:12,fontFamily:'inherit'}}>
                  <option value=''>No limit</option>
                  {[30,40,50,60,70,80,100,120,150].map(h=>(
                    <option key={h} value={h}>≤ {h} mm</option>
                  ))}
                </select>
              </div>
              <div>
                {LABEL('Max Diameter (mm)')}
                <select value={fDiaMax ?? ''} onChange={e=>setFDiaMax(e.target.value?+e.target.value:null)}
                  style={{width:'100%',padding:'6px 10px',borderRadius:6,border:`1px solid ${C.border}`,
                    background:C.bg3,color:C.text,fontSize:12,fontFamily:'inherit'}}>
                  <option value=''>No limit</option>
                  {[20,25,30,35,40,50,60,70].map(d=>(
                    <option key={d} value={d}>≤ {d} mm</option>
                  ))}
                </select>
              </div>
            </div>
          </div>

          {/* Ambient temperature — used for lifetime calculations */}
          <div style={{borderTop:`0.5px solid ${C.border}`,paddingTop:14,marginTop:4}}>
            <div style={{display:'flex',alignItems:'center',justifyContent:'space-between',marginBottom:6}}>
              {LABEL('Ambient Temperature (for lifetime calculation)')}
              <span style={{fontFamily:'IBM Plex Mono,monospace',fontSize:13,fontWeight:700,
                color:C.accent}}>{fAmbientC}°C</span>
            </div>
            <input type="range" min={0} max={50} step={5} value={fAmbientC}
              onChange={e=>setFAmbientC(+e.target.value)}
              style={{width:'100%',accentColor:C.accent,marginBottom:4}} />
            <div style={{display:'flex',justifyContent:'space-between',fontSize:9,color:C.hint}}>
              <span>0°C (cold)</span>
              <span>25°C (standard)</span>
              <span>50°C (hot)</span>
            </div>
            <div style={{fontSize:10,color:C.muted,marginTop:4}}>
              Capacitor ambient — air temperature 2–5 cm from can. Used in all three lifetime methods.
              Higher ambient = shorter life.
            </div>
          </div>

          <div style={{marginTop:10,fontSize:11,color:C.hint}}>
            {loadingCaps
              ? <><Spinner/>&nbsp;Updating…</>
              : `${availCaps.length} capacitance value(s) available with current filters`}
          </div>
        </>)}
      </Card>

      {/* ── 4. Capacitor Value Selection ────────────────────────────────────── */}
      <Card>
        <SecHead icon="🔌" label="Capacitor Value Selection"
          sub={selectedCapUF
            ? `Selected: ${selectedCapUF}µF  ·  min qty needed: ${minQtyNeeded}`
            : `${C_req.toFixed(0)} µF required — click a value to begin`} />

        <div style={{display:'flex',gap:5,flexWrap:'wrap',marginBottom:14}}>
          {availCaps.map(val => {
            const isSel = selectedCapUF === val
            const minQ  = computeMinQty(val)
            return (
              <div key={val}
                style={{padding:'6px 12px',borderRadius:7,cursor:'pointer',fontSize:11,
                  fontFamily:'IBM Plex Mono,monospace',transition:'all .12s',
                  border:`1.5px solid ${isSel?C.accent:C.border}`,
                  background:isSel?C.accentL:C.bg3,
                  color:isSel?C.accent:C.muted,fontWeight:isSel?600:400}}
                onClick={()=>handlePickCap(val)}>
                <div style={{fontWeight:600}}>{val}µF</div>
                <div style={{fontSize:9,color:isSel?C.accent:C.hint,marginTop:2}}>min {minQ}×</div>
              </div>
            )
          })}
          {availCaps.length===0 && !loadingCaps && (
            <div style={{fontSize:11,color:C.hint}}>No capacitors match — relax the filters</div>
          )}
        </div>

        {/* ── Capacitor Configuration Builder ─────────────────────────── */}
        {selectedCapUF && (
          <div style={{background:C.bg3,border:`1px solid ${C.border}`,borderRadius:10,padding:'16px 18px'}}>
            <div style={{fontSize:12,fontWeight:600,color:C.text,marginBottom:14}}>
              Capacitor Configuration
            </div>

            {/* Qty adjuster */}
            <div style={{display:'flex',alignItems:'center',gap:14,marginBottom:16,flexWrap:'wrap'}}>
              <div>
                {LABEL('Total Capacitors')}
                <div style={{display:'flex',alignItems:'center',gap:8}}>
                  <button onClick={()=>handleQtyChange(selectedQty-1)}
                    style={{width:32,height:32,borderRadius:6,border:`1px solid ${C.border}`,
                      background:C.bg2,color:C.text,fontSize:16,cursor:'pointer',fontFamily:'inherit'}}>
                    −
                  </button>
                  <span style={{fontFamily:'IBM Plex Mono,monospace',fontSize:22,fontWeight:700,
                    color:C.accent,minWidth:40,textAlign:'center'}}>
                    {selectedQty}
                  </span>
                  <button onClick={()=>handleQtyChange(selectedQty+1)}
                    style={{width:32,height:32,borderRadius:6,border:`1px solid ${C.border}`,
                      background:C.bg2,color:C.text,fontSize:16,cursor:'pointer',fontFamily:'inherit'}}>
                    +
                  </button>
                </div>
                <div style={{fontSize:10,color:C.hint,marginTop:4}}>
                  min needed: {minQtyNeeded} · each {selectedCapUF}µF
                </div>
              </div>

              {/* Progress to C_required */}
              <div style={{flex:1,minWidth:200}}>
                {LABEL('Total Capacitance vs Required')}
                <div style={{display:'flex',alignItems:'center',gap:8,marginBottom:4}}>
                  <span style={{fontFamily:'IBM Plex Mono,monospace',fontSize:14,fontWeight:700,
                    color:meetsC?C.green:C.red}}>
                    {C_total} µF
                  </span>
                  <span style={{fontSize:11,color:C.hint}}>of {C_req.toFixed(0)} µF required</span>
                  <span style={{fontSize:11,fontWeight:600,color:meetsC?C.green:C.red}}>
                    {meetsC?'✓ OK':'✗ Short'}
                  </span>
                </div>
                {/* Progress bar */}
                <div style={{height:8,borderRadius:4,background:C.border,overflow:'hidden'}}>
                  <div style={{height:'100%',borderRadius:4,transition:'width .3s',
                    width:`${pctOfReq}%`,
                    background:meetsC?C.green:pctOfReq>80?C.amber:C.red}} />
                </div>
                <div style={{display:'flex',justifyContent:'space-between',fontSize:9,
                  color:C.hint,marginTop:2}}>
                  <span>0</span>
                  <span>{C_req.toFixed(0)} µF</span>
                </div>
              </div>
            </div>

            {/* Effective parameters based on qty + chosen part */}
            <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:12}}>
              <div>
                <div style={{fontSize:10,color:C.hint,fontFamily:'IBM Plex Mono,monospace',
                  textTransform:'uppercase',letterSpacing:'.05em',marginBottom:8}}>
                  Calculated — {selectedQty} caps in parallel
                </div>
                <KV k="Total capacitance"      v={`${C_total} µF`} hi={!meetsC} red={!meetsC} />
                <KV k="C per unit"             v={`${selectedCapUF} µF`} />
                <KV k="ESR effective (par.)"   v={chosenPart ? `${esr_eff_mohm.toFixed(1)} mΩ` : '—'} />
                <KV k="ESR each cap"           v={chosenPart ? `${esr_each_mohm.toFixed(0)} mΩ` : '—'} />
                <KV k="I_rms per cap (worst)"  v={`${I_per_cap.toFixed(3)} A`} />
                <KV k="I_rated per cap"        v={I_rated ? `${I_rated.toFixed(3)} A` : '—'} />
                <div style={{marginTop:8,padding:'6px 10px',borderRadius:6,
                  background:ripple_pass===null?C.bg4:ripple_pass?C.greenL:C.redL,
                  border:`0.5px solid ${ripple_pass===null?C.border:ripple_pass?C.green:C.red}44`,
                  fontSize:11,fontWeight:600,
                  color:ripple_pass===null?C.hint:ripple_pass?C.green:C.red}}>
                  {ripple_pass===null
                    ? 'Select a part to check ripple current'
                    : ripple_pass
                    ? `✓ Ripple PASS — I/cap ${I_per_cap.toFixed(3)}A ≤ ${I_rated!.toFixed(3)}A rated`
                    : `⚠ Ripple FAIL — I/cap ${I_per_cap.toFixed(3)}A > ${I_rated!.toFixed(3)}A — increase qty`}
                </div>
              </div>
              <div>
                <div style={{fontSize:10,color:C.hint,fontFamily:'IBM Plex Mono,monospace',
                  textTransform:'uppercase',letterSpacing:'.05em',marginBottom:8}}>
                  Selected Part
                </div>
                {chosenPart ? (
                  <div style={{background:C.bg4,borderRadius:8,padding:'10px 12px'}}>
                    <div style={{fontSize:12,fontWeight:600,color:C.accent,marginBottom:4}}>
                      {chosenPart.manufacturer}
                    </div>
                    <div style={{fontSize:11,fontFamily:'IBM Plex Mono,monospace',color:C.text,marginBottom:8}}>
                      {chosenPart.part_number}
                    </div>
                    <KV k="Capacitance"     v={`${chosenPart.capacitance_uF} µF`} />
                    <KV k="Voltage"         v={`${chosenPart.voltage_V} V`} />
                    <KV k="ESR (each)"      v={`${esr_each_mohm.toFixed(0)} mΩ`} />
                    <KV k="I_rated @120Hz"  v={`${chosenPart.I_rated_120hz_A?.toFixed(3) ?? '—'} A`} />
                    <KV k="Lifetime (rated)" v={chosenPart.lifetime} />
                    <KV k="Dimensions"      v={`⌀${chosenPart.diameter_mm} × ${chosenPart.height_mm}mm`} />
                    <KV k="Lead spacing"    v={`${chosenPart.lead_spacing_mm}mm`} />
                    {chosenPart.rohs && (
                      <div style={{marginTop:4,fontSize:10,color:C.green}}>✓ RoHS compliant</div>
                    )}
                  </div>
                ) : (
                  <div style={{background:C.bg4,borderRadius:8,padding:'10px 12px',
                    fontSize:11,color:C.hint,textAlign:'center'}}>
                    Select a part from the table below
                  </div>
                )}

            {/* ── Lifetime panel ──────────────────────────────────────── */}
            {(loadingLifetime || lifetime) && (
              <div style={{marginTop:12}}>
                <div style={{fontSize:11,fontWeight:600,color:C.text,marginBottom:8,display:'flex',
                  alignItems:'center',gap:8}}>
                  Calculated Lifespan @ T_amb={fAmbientC}°C
                  {loadingLifetime && <Spinner/>}
                </div>
                {lifetime && !loadingLifetime && (
                  <>
                    {/* Three-method table */}
                    <div style={{border:`0.5px solid ${C.border}`,borderRadius:7,overflow:'hidden',marginBottom:8}}>
                      <table style={{width:'100%',borderCollapse:'collapse',fontSize:10}}>
                        <thead>
                          <tr style={{background:C.bg4,borderBottom:`0.5px solid ${C.border}`}}>
                            <th style={{padding:'5px 8px',textAlign:'left',color:C.hint,fontWeight:400}}>Method</th>
                            <th style={{padding:'5px 8px',textAlign:'right',color:C.hint,fontWeight:400}}>T_core</th>
                            <th style={{padding:'5px 8px',textAlign:'right',color:C.hint,fontWeight:400}}>Life (yr)</th>
                            <th style={{padding:'5px 8px',textAlign:'center',color:C.hint,fontWeight:400}}>≥15yr</th>
                          </tr>
                        </thead>
                        <tbody>
                          {[
                            {key:'method1', m:lifetime.method1},
                            {key:'method2', m:lifetime.method2},
                            {key:'method3', m:lifetime.method3},
                          ].map(({key, m}) => {
                            const isMin = m.life_years === lifetime.min_life_years
                            const pass  = m.life_years >= 15
                            return (
                              <tr key={key} style={{borderBottom:`0.5px solid ${C.border}`,
                                background:isMin?C.amberL:C.bg3}}>
                                <td style={{padding:'5px 8px',fontSize:10,
                                  color:isMin?C.amber:C.muted,fontWeight:isMin?600:400}}>
                                  {isMin?'★ ':''}{m.name.split('—')[0].trim()}
                                </td>
                                <td style={{padding:'5px 8px',textAlign:'right',
                                  fontFamily:'IBM Plex Mono,monospace'}}>
                                  {m.T_core_C?.toFixed(1)}°C
                                </td>
                                <td style={{padding:'5px 8px',textAlign:'right',
                                  fontFamily:'IBM Plex Mono,monospace',fontWeight:600,
                                  color:pass?C.green:C.red}}>
                                  {key==='method3'
                                    ? (m.life_years_uncapped > 100 ? '>100' : m.life_years)
                                    : m.life_years}
                                </td>
                                <td style={{padding:'5px 8px',textAlign:'center',fontWeight:600,
                                  color:pass?C.green:C.red}}>
                                  {pass?'✓':'✗'}
                                </td>
                              </tr>
                            )
                          })}
                        </tbody>
                      </table>
                    </div>

                    {/* Governing result banner */}
                    <div style={{padding:'8px 12px',borderRadius:7,fontSize:11,fontWeight:600,
                      background:lifetime.pass_15yr?C.greenL:C.redL,
                      border:`0.5px solid ${lifetime.pass_15yr?C.green:C.red}44`,
                      color:lifetime.pass_15yr?C.green:C.red}}>
                      {lifetime.pass_15yr
                        ? `✓ Min life = ${lifetime.min_life_years} yr (${lifetime.governing_method}) — PASS ≥ 15 yr target`
                        : `⚠ Min life = ${lifetime.min_life_years} yr (${lifetime.governing_method}) — FAIL < 15 yr target`}
                    </div>
                  </>
                )}
              </div>
            )}
              </div>
            </div>
          </div>
        )}
      </Card>

      {/* ── 5. Available Parts Table ─────────────────────────────────────────── */}
      {selectedCapUF && (
        <Card>
          <SecHead
            icon="📋"
            label={`Parts — ${selectedCapUF}µF (${selectedQty} in parallel)`}
            sub={loadingTable
              ? 'Loading parts…'
              : `${capTable.length} parts · showing I/cap for ${selectedQty}× parallel · click to select`}
          />

          {loadingTable && (
            <div style={{display:'flex',gap:10,color:C.muted,padding:'10px 0'}}>
              <Spinner/>&nbsp;Loading parts for {selectedCapUF}µF × {selectedQty}…
            </div>
          )}

          {!loadingTable && capTable.length > 0 && (
            <div style={{border:`0.5px solid ${C.border}`,borderRadius:8,overflow:'auto'}}>
              <table style={{width:'100%',borderCollapse:'collapse',fontSize:11,minWidth:900}}>
                <thead>
                  <tr style={{background:C.bg3,borderBottom:`0.5px solid ${C.border}`}}>
                    {['','Manufacturer','Part Number','V (V)',
                      'ESR each (mΩ)','ESR par. (mΩ)',
                      'I_rated (A)','I/cap (A)','Ripple',
                      'Lifetime','Op Temp','⌀ (mm)','H (mm)',
                      'Lead (mm)','RoHS'].map(h=>(
                      <th key={h} style={{padding:'6px 8px',textAlign:'left',color:C.hint,
                        fontFamily:'IBM Plex Mono,monospace',fontWeight:400,fontSize:9,
                        whiteSpace:'nowrap'}}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {capTable.slice(0,60).map((row:any, i:number) => {
                    const isSel     = chosenPart?.part_number === row.part_number
                    const rip_ok    = row.ripple_pass
                    const esr_par_mohm = row.esr_each_ohm * 1000 / selectedQty
                    return (
                      <tr key={row.part_number} onClick={()=>setChosenPart(row)}
                        style={{borderBottom:`0.5px solid ${C.border}`,cursor:'pointer',
                          background:isSel?C.accentL:i%2===0?C.bg2:C.bg3}}>
                        <td style={{padding:'5px 8px'}}>
                          <span style={{color:isSel?C.accent:C.hint}}>{isSel?'●':'○'}</span>
                        </td>
                        <td style={{padding:'5px 8px',fontWeight:isSel?600:400,
                          color:isSel?C.accent:C.text,whiteSpace:'nowrap'}}>
                          {row.manufacturer}
                        </td>
                        <td style={{padding:'5px 8px',fontFamily:'IBM Plex Mono,monospace',
                          fontSize:10,color:isSel?C.accent:C.text,whiteSpace:'nowrap'}}>
                          {row.part_number}
                        </td>
                        <td style={{padding:'5px 8px',fontFamily:'IBM Plex Mono,monospace'}}>
                          {row.voltage_V}
                        </td>
                        <td style={{padding:'5px 8px',fontFamily:'IBM Plex Mono,monospace',
                          color:row.esr_each_ohm*1000<500?C.green:row.esr_each_ohm*1000<2000?C.teal:C.amber}}>
                          {(row.esr_each_ohm*1000).toFixed(0)}
                        </td>
                        <td style={{padding:'5px 8px',fontFamily:'IBM Plex Mono,monospace',
                          color:C.green}}>
                          {esr_par_mohm.toFixed(1)}
                        </td>
                        <td style={{padding:'5px 8px',fontFamily:'IBM Plex Mono,monospace'}}>
                          {row.I_rated_120hz_A?.toFixed(3) ?? '—'}
                        </td>
                        <td style={{padding:'5px 8px',fontFamily:'IBM Plex Mono,monospace',
                          color:rip_ok===false?C.red:rip_ok?C.green:C.muted}}>
                          {row.I_rms_per_cap_A?.toFixed(3)}
                        </td>
                        <td style={{padding:'5px 8px',fontSize:10,fontWeight:600,
                          color:rip_ok===null?C.hint:rip_ok?C.green:C.red}}>
                          {rip_ok===null?'—':rip_ok?'PASS':'FAIL'}
                        </td>
                        <td style={{padding:'5px 8px',fontSize:10,color:C.muted,whiteSpace:'nowrap'}}>
                          {row.lifetime}
                        </td>
                        <td style={{padding:'5px 8px',fontSize:10,color:C.muted,whiteSpace:'nowrap'}}>
                          {row.op_temp}
                        </td>
                        <td style={{padding:'5px 8px',fontFamily:'IBM Plex Mono,monospace'}}>
                          {row.diameter_mm}
                        </td>
                        <td style={{padding:'5px 8px',fontFamily:'IBM Plex Mono,monospace'}}>
                          {row.height_mm}
                        </td>
                        <td style={{padding:'5px 8px',fontFamily:'IBM Plex Mono,monospace'}}>
                          {row.lead_spacing_mm}
                        </td>
                        <td style={{padding:'5px 8px',fontSize:10,
                          color:row.rohs?C.green:C.hint}}>
                          {row.rohs?'✓':'—'}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
              {capTable.length > 60 && (
                <div style={{padding:'6px 12px',fontSize:11,color:C.hint}}>
                  Showing 60 of {capTable.length} parts — tighten filters to narrow
                </div>
              )}
            </div>
          )}

          {!loadingTable && capTable.length === 0 && selectedCapUF && (
            <div style={{padding:'20px',textAlign:'center',color:C.hint,fontSize:12}}>
              No parts found for {selectedCapUF}µF with current filters
            </div>
          )}
        </Card>
      )}

      {/* ── Selected Capacitors Summary ──────────────────────────────────────── */}
      {canApprove && (
        <div style={{background:C.bg3,border:`1px solid ${C.border}`,borderRadius:10,
          padding:'14px 18px',marginBottom:4}}>
          <div style={{fontSize:13,fontWeight:600,color:C.text,marginBottom:10}}>
            Selected Capacitors
          </div>
          <div style={{border:`0.5px solid ${C.border}`,borderRadius:8,overflow:'hidden'}}>
            <table style={{width:'100%',borderCollapse:'collapse',fontSize:12}}>
              <thead>
                <tr style={{background:'#1e2438',borderBottom:`0.5px solid ${C.border}`}}>
                  {['Qty','Supplier','Part Number','Capacitance','Voltage','ESR each','ESR effective','Min Life (yr)','Pass 15yr?'].map(h=>(
                    <th key={h} style={{padding:'7px 12px',textAlign:'left',color:C.hint,
                      fontFamily:'IBM Plex Mono,monospace',fontWeight:400,fontSize:10}}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                <tr style={{background:C.bg3}}>
                  <td style={{padding:'8px 12px',fontFamily:'IBM Plex Mono,monospace',
                    fontWeight:700,color:C.accent,fontSize:16}}>{selectedQty}</td>
                  <td style={{padding:'8px 12px',fontWeight:600}}>{chosenPart.manufacturer}</td>
                  <td style={{padding:'8px 12px',fontFamily:'IBM Plex Mono,monospace',fontSize:11}}>
                    {chosenPart.part_number}
                  </td>
                  <td style={{padding:'8px 12px',fontFamily:'IBM Plex Mono,monospace'}}>
                    {chosenPart.capacitance_uF} µF
                  </td>
                  <td style={{padding:'8px 12px',fontFamily:'IBM Plex Mono,monospace'}}>
                    {chosenPart.voltage_V} V
                  </td>
                  <td style={{padding:'8px 12px',fontFamily:'IBM Plex Mono,monospace'}}>
                    {esr_each_mohm.toFixed(0)} mΩ
                  </td>
                  <td style={{padding:'8px 12px',fontFamily:'IBM Plex Mono,monospace',color:C.green}}>
                    {esr_eff_mohm.toFixed(1)} mΩ
                  </td>
                  <td style={{padding:'8px 12px',fontFamily:'IBM Plex Mono,monospace',fontWeight:700,
                    color:lifetime?.pass_15yr===false?C.red:lifetime?.pass_15yr?C.green:C.muted}}>
                    {lifetime ? `${lifetime.min_life_years} yr` : '—'}
                  </td>
                  <td style={{padding:'8px 12px',fontWeight:600,
                    color:lifetime?.pass_15yr===false?C.red:lifetime?.pass_15yr?C.green:C.muted}}>
                    {lifetime ? (lifetime.pass_15yr ? '✓ PASS' : '✗ FAIL') : '—'}
                  </td>
                </tr>
                <tr style={{background:'#0d1625',borderTop:`0.5px solid ${C.border}`}}>
                  <td colSpan={3} style={{padding:'7px 12px',fontFamily:'IBM Plex Mono,monospace',
                    fontWeight:600,color:C.green}}>
                    Total: {C_total} µF ({selectedQty} × {selectedCapUF}µF)
                  </td>
                  <td colSpan={7} style={{padding:'7px 12px',fontSize:11,color:C.muted}}>
                    ESR∥={esr_eff_mohm.toFixed(1)}mΩ · I/cap={I_per_cap.toFixed(3)}A ·
                    {ripple_pass
                      ? <span style={{color:C.green}}> ✓ Ripple PASS</span>
                      : <span style={{color:C.red}}> ⚠ Ripple FAIL</span>}
                    {lifetime && (
                      <span style={{marginLeft:10,fontWeight:600,
                        color:lifetime.pass_15yr?C.green:C.red}}>
                        · Life={lifetime.min_life_years}yr ({lifetime.governing_method})
                        {lifetime.pass_15yr?' ✓':' ✗ FAIL <15yr'}
                      </span>
                    )}
                    <span style={{marginLeft:10}}>
                      T_amb={fAmbientC}°C ·
                      {chosenPart.diameter_mm}mm×{chosenPart.height_mm}mm ·
                      {chosenPart.lead_spacing_mm}mm lead · {chosenPart.rohs?'RoHS✓':'—'}
                    </span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ── Action bar ──────────────────────────────────────────────────────── */}
      <div style={{display:'flex',gap:8,paddingTop:12,borderTop:`0.5px solid ${C.border}`,
        alignItems:'center',marginTop:4}}>
        <Btn variant="ghost" onClick={onBack}>← Back</Btn>
        <div style={{flex:1,display:'flex',flexDirection:'column',alignItems:'center',gap:4}}>
          {rptError && (
            <div style={{fontSize:12,color:'#c0392b',background:'#fdf2f2',border:'1px solid #e8b4b8',
              borderRadius:6,padding:'5px 10px',maxWidth:360,textAlign:'center'}}>
              ⚠ Report failed: {rptError}
            </div>
          )}
          <Btn variant="ghost" disabled={rptLoading} onClick={handleReport}>
            {rptLoading?'⏳ Generating…':'📄 Generate Report (Steps 1–15)'}
          </Btn>
        </div>
        <Btn variant="primary" disabled={!canApprove}
          onClick={() => onConfirm({
            supplier:       chosenPart?.manufacturer ?? '',
            series:         chosenPart?.series ?? '',
            voltage_rating: chosenPart?.voltage_V ?? 0,
            configuration:  [{
              value_uF:    selectedCapUF ?? 0,
              qty:         selectedQty,
              part_number: chosenPart?.part_number,
            }],
            C_total_uF:         C_total,
            ESR_parallel_mohm:  esr_eff_mohm,
            thermal_table:      [],
            worst_case:         {} as OperatingPointResult,
            low_line:           {} as OperatingPointResult,
            selected_cap: chosenPart ? {
              supplier:         chosenPart.manufacturer ?? '',
              series:           chosenPart.series       ?? '',
              voltage_rating_V: chosenPart.voltage_V    ?? 450,
              value_uF:         selectedCapUF           ?? 0,
              qty:              selectedQty,
              part_number:      chosenPart.part_number  ?? '',
              lifetime:         chosenPart.lifetime     ?? '—',
              op_temp:          chosenPart.temp_rating_C != null
                                  ? `${chosenPart.temp_rating_C}°C` : '—',
              ESR_each_mohm:    (chosenPart.esr_each_ohm ?? 0) * 1000,
              I_rated_A:        chosenPart.I_rated_120hz_A ?? null,
              temp_rating_C:    chosenPart.temp_rating_C  ?? 85,
            } : undefined,
          })}>
          ✓ Approve &amp; Go to Control Design
        </Btn>
      </div>
    </div>
  )
}
