import React, { useState, useEffect } from 'react'
import { Card, SecHead, Btn, Badge, ErrBanner, C } from './ui'
import type { MiniDefaults } from '../api/client'

interface Props {
  selectedTopology: string
  selectedMode: string
  defaults: MiniDefaults
  validationErrors: string[]
  onSubmit: (feedback: Record<string, unknown>) => void
  onBack: () => void
  loading: boolean
  pout_lo?: number
  vin_min?: number
  vout?: number
  nPhases?: number
  appClass?: string
}

// Correct formula matching Python backend
function calcElec(pout_lo=1700, vin_min=90, vout=393, fsw=70000, crest=0.095, N=2) {
  const eta=0.945, PF=0.9987
  const Vin_pk = vin_min * Math.sqrt(2)
  const D      = Math.max(0.001, 1 - Vin_pk / vout)
  const Iin_pk = Math.sqrt(2) * (pout_lo / eta) / (vin_min * PF)
  const dIin   = crest * Iin_pk
  const KD     = D >= 0.5 ? (2*D-1)/D : (1-2*D)/(1-D)
  const dIL    = dIin / Math.max(0.001, KD)
  const L      = Vin_pk * D / (fsw * dIL)
  const Ipk_ph = Iin_pk/N + dIL/2
  return { L_uH: Math.round(L*1e6), dIL: parseFloat(dIL.toFixed(3)), Iin_pk: parseFloat(Iin_pk.toFixed(2)),
           Ipk_ph: parseFloat(Ipk_ph.toFixed(2)), Tsw_us: parseFloat((1e6/fsw).toFixed(1)) }
}

const STYLE_DEFS = {
  fixed:    {tag:'★ Default for CCM + Analog',tagColor:C.green,  title:'Fixed frequency',   desc:'Constant fsw. Predictable EMI. Required for CCM analog ICs (UCC28070A, NCP1631).'},
  variable: {tag:'★ Default for CrCM',        tagColor:C.amber,  title:'Variable frequency', desc:'Variable fsw. Required for CrCM. Not valid for CCM + analog controllers.'},
  recommend:{tag:'System decides',             tagColor:C.hint,   title:'System recommend',   desc:'Agent picks optimal frequency. No Hz entry needed.'},
}
const FSW_PRESETS = [50000, 70000, 100000, 140000, 200000]

const ZONE_GUIDE = [
  {range:'0.05 – 0.15', color:C.green,  star:false, desc:'Low ripple: large L, smooth Iin, best THD. Preferred for Medical/low-harmonic.'},
  {range:'0.15 – 0.30', color:C.accent, star:true,  desc:'★ Recommended: balanced inductor size vs switching stress.'},
  {range:'0.30 – 0.45', color:C.amber,  star:false, desc:'Moderate: smaller L, higher Ipk, more EMI filter work.'},
  {range:'0.45 – 0.60', color:C.red,    star:false, desc:'High ripple: very small L, significant peak current stress.'},
]

export const MiniIntakeGate: React.FC<Props> = ({
  selectedTopology, selectedMode, defaults, validationErrors, onSubmit, onBack, loading,
  pout_lo=1700, vin_min=90, vout=393, nPhases=2, appClass,
}) => {
  const [style, setStyle] = useState<string>(defaults.switching_frequency_style || 'fixed')
  const [fsw,   setFsw]   = useState<number>(defaults.recommended_frequency_hz || 70000)
  const [crest, setCrest] = useState<number>(defaults.default_crest_ripple_ratio || 0.20)
  const [elec,  setElec]  = useState(calcElec(pout_lo, vin_min, vout, defaults.recommended_frequency_hz||70000, defaults.default_crest_ripple_ratio||0.20, nPhases))

  const isCCM     = selectedMode === 'ccm'
  const isCrCM    = selectedMode === 'crcm'
  const isMedical = appClass === 'Medical'
  const showFsw   = style === 'fixed'
  const showCrest = !isCrCM
  const varLocked = isCCM && style === 'variable'

  useEffect(() => {
    setElec(calcElec(pout_lo, vin_min, vout, fsw, isCrCM ? 2.0 : crest, nPhases))
  }, [fsw, crest, pout_lo, vin_min, vout, nPhases, isCrCM])

  const handleFsw = (v: number) => { setFsw(v); }
  const handleCrest = (v: number) => { setCrest(parseFloat(v.toFixed(3))); }

  const crColor = crest <= 0.15 ? C.green : crest <= 0.30 ? C.accent : crest <= 0.45 ? C.amber : C.red

  const styleOptions = isCCM ? ['fixed','recommend'] : isCrCM ? ['variable','recommend'] : ['fixed','variable','recommend']

  function doSubmit() {
    onSubmit({
      switching_frequency_style: style,
      switching_frequency_hz: style === 'fixed' ? fsw : null,
      crest_ripple_ratio: isCrCM ? 2.0 : crest,
    })
  }

  return (
    <div>
      <div style={{fontSize:20,fontWeight:500,marginBottom:3}}>Topology-specific mini-intake</div>
      <div style={{fontSize:13,color:C.muted,marginBottom:18,display:'flex',alignItems:'center',gap:8,flexWrap:'wrap'}}>

        <Badge color="green">{selectedTopology.replace(/_/g,' ')}</Badge>
        <Badge color="gray">{selectedMode.toUpperCase()}</Badge>
        {isMedical && <Badge color="amber">Medical · 500 µA</Badge>}
      </div>

      {validationErrors.length > 0 && <ErrBanner errors={validationErrors} />}

      <Card style={{marginBottom:14}}>
        <SecHead icon="🔄" label="Switching frequency style" />
        <div style={{display:'grid',gridTemplateColumns:`repeat(${styleOptions.length},1fr)`,gap:9,marginBottom:8}}>
          {styleOptions.map(s => {
            const d = STYLE_DEFS[s as keyof typeof STYLE_DEFS]
            const isSel = style === s
            return (
              <div key={s} onClick={() => setStyle(s)}
                style={{padding:'12px 14px',borderRadius:8,cursor:'pointer',
                  border:`1.5px solid ${isSel?C.accent:C.border}`,background:isSel?C.accentL:C.bg3}}>
                <div style={{display:'inline-flex',padding:'1px 7px',borderRadius:4,fontSize:10,marginBottom:5,
                  background:`${d.tagColor}22`,color:d.tagColor,border:`1px solid ${d.tagColor}44`}}>{d.tag}</div>
                <div style={{fontSize:13,fontWeight:500,marginBottom:3,color:isSel?C.accent:C.muted}}>{d.title}</div>
                <div style={{fontSize:11,color:C.hint,lineHeight:1.4}}>{d.desc}</div>
              </div>
            )
          })}
        </div>
        {varLocked && (
          <div style={{padding:'8px 12px',background:C.amberL,borderRadius:6,fontSize:11,color:C.amber}}>
            <strong>✗ Variable frequency not valid for CCM</strong> — fixed fsw required by current-mode control loop.
          </div>
        )}
      </Card>

      {showFsw && (
        <Card style={{marginBottom:14}}>
          <SecHead icon="📡" label={`Switching frequency — all 3 analog ICs support 50–200 kHz ✓`} />
          <div style={{display:'flex',gap:6,flexWrap:'wrap',marginBottom:9}}>
            {FSW_PRESETS.map(p => (
              <button key={p} onClick={() => handleFsw(p)}
                style={{padding:'3px 10px',borderRadius:6,cursor:'pointer',fontSize:12,fontFamily:'inherit',
                  border:`1px solid ${fsw===p?C.green:C.border}`,background:fsw===p?C.greenL:C.bg3,color:fsw===p?C.green:C.muted}}>
                {p/1000} kHz{p===70000?' ★':''}
              </button>
            ))}
          </div>
          <input type="range" min={20000} max={300000} step={1000} value={fsw}
            onChange={e => handleFsw(+e.target.value)} style={{width:'100%',marginBottom:4,accentColor:C.accent}} />
          <div style={{display:'flex',justifyContent:'space-between',fontSize:10,color:C.hint,marginBottom:9}}>
            <span>20 kHz</span>
            <span style={{color:C.green,fontWeight:500}}>{fsw.toLocaleString()} Hz · Tsw = {elec.Tsw_us} µs</span>
            <span>300 kHz</span>
          </div>
          <input type="number" value={fsw} min={20000} max={300000} step={1000}
            onChange={e => handleFsw(+e.target.value)}
            style={{width:130,padding:'5px 8px',borderRadius:6,border:`1px solid ${C.border}`,background:C.bg3,color:C.text,fontSize:12}} />
        </Card>
      )}

      {showCrest && (
        <Card style={{marginBottom:14}}>
          <SecHead icon="〰" label="Crest ripple ratio — r = ΔIin_pp / Iin_pk at line crest" />
          <input type="range" min={0.05} max={0.60} step={0.005} value={crest}
            onChange={e => handleCrest(+e.target.value)} style={{width:'100%',marginBottom:4,accentColor:C.accent}} />
          <div style={{display:'flex',justifyContent:'space-between',fontSize:10,color:C.hint,marginBottom:9}}>
            <span>0.05 (large L)</span>
            <span style={{color:crColor,fontWeight:500}}>{crest.toFixed(3)}</span>
            <span>0.60 (small L)</span>
          </div>
          <input type="number" value={crest.toFixed(3)} min={0.05} max={0.60} step={0.005}
            onChange={e => handleCrest(+e.target.value)} style={{width:100,padding:'5px 8px',borderRadius:6,border:`1px solid ${C.border}`,background:C.bg3,color:C.text,fontSize:12}} />
          <div style={{background:C.bg4,borderRadius:7,padding:'10px 12px',marginTop:10}}>
            <div style={{fontSize:10,fontWeight:500,textTransform:'uppercase',letterSpacing:'.07em',color:C.hint,marginBottom:8}}>
              Ripple zone guide{isMedical?' · low ripple zone preferred for Medical (better THD)':''}
            </div>
            {ZONE_GUIDE.map(z => (
              <div key={z.range} style={{display:'flex',alignItems:'flex-start',gap:7,marginBottom:4,fontSize:11,lineHeight:1.4}}>
                <div style={{width:7,height:7,borderRadius:'50%',flexShrink:0,marginTop:3,background:z.color}}/>
                <div style={{color:z.color,minWidth:86,fontWeight:500}}>{z.range}{z.star?' ★':''}</div>
                <div style={{color:C.muted}}>{z.desc}</div>
              </div>
            ))}
          </div>
        </Card>
      )}

      <Card style={{marginBottom:14}}>
        <SecHead icon="⚡" label="Live electrical estimates — per phase · worst-case 90 Vac · Python formula" />
        <div style={{display:'grid',gridTemplateColumns:'repeat(4,1fr)',gap:9}}>
          {[
            ['L / phase', `${elec.L_uH} µH`,  crest<=0.15?C.green:crest<=0.30?C.accent:C.amber,  'corrected Python formula'],
            ['ΔIL (pp)',  `${elec.dIL} A`,     C.accent,                                           '= dIin / K(D)'],
            ['Peak I/ph.',`${elec.Ipk_ph} A`,  elec.Ipk_ph>35?C.amber:C.accent,                   `= Iin_pk/${nPhases} + ΔIL/2`],
            ['Tsw',       `${elec.Tsw_us} µs`, C.green,                                            '= 1 / fsw'],
          ].map(([k,v,col,sub]) => (
            <div key={k as string} style={{background:C.bg3,border:`0.5px solid ${C.border}`,borderRadius:7,padding:'10px 12px'}}>
              <div style={{fontSize:10,color:C.hint,marginBottom:3}}>{k}</div>
              <div style={{fontSize:17,fontWeight:500,color:col as string}}>{v}</div>
              <div style={{fontSize:10,color:C.hint,marginTop:2}}>{sub}</div>
            </div>
          ))}
        </div>
        {isMedical && crest <= 0.15 && (
          <div style={{marginTop:8,fontSize:11,color:C.green}}>✓ Low ripple zone — advantageous for EN 61000-3-2 THD compliance (Medical)</div>
        )}
        {isMedical && crest > 0.30 && (
          <div style={{marginTop:8,fontSize:11,color:C.amber}}>⚠ Higher ripple zone — verify EN 61000-3-2 harmonics compliance for Medical class</div>
        )}
      </Card>

      <div style={{display:'flex',alignItems:'center',justifyContent:'space-between',paddingTop:12,borderTop:`0.5px solid ${C.border}`}}>
        <div style={{display:'flex',gap:8}}>
          <Btn variant="ghost" onClick={onBack} disabled={loading}>← Back</Btn>
          <Btn variant="primary" onClick={doSubmit} disabled={loading || varLocked}>
            {loading ? 'Validating…' : 'Validate & submit →'}
          </Btn>
        </div>
      </div>
    </div>
  )
}
