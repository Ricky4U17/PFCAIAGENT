import React, { useState } from 'react'
import { Card, SecHead, Btn, Badge, C } from './ui'
import type { FullIntake } from '../api/client'

interface Props {
  selectedTopology: string
  controllerMode: string
  intake?: FullIntake
  onSubmit: (fb: { approved: boolean; n_channels: number }) => void
  onBack: () => void
  loading: boolean
}

// Correct inductance formula — matches Python backend exactly
// L is SAME for all N (L independent of phase count)
function calcLPy(intake: any, crest = 0.095, fsw = 70000) {
  const app = intake?.application || {}
  const pout_lo = parseFloat(app.output_power_w_low_line  || 1700)
  const vin_min = parseFloat(app.vin_rms_min              || 90)
  const vout    = parseFloat(app.output_bus_voltage_v     || 393)
  const eta = 0.945, PF = 0.9987
  const Vin_pk = vin_min * Math.sqrt(2)
  const D      = Math.max(0.001, 1 - Vin_pk / vout)
  const Iin_pk = Math.sqrt(2) * (pout_lo / eta) / (vin_min * PF)
  const dIin   = crest * Iin_pk
  const KD     = D >= 0.5 ? (2*D-1)/D : (1-2*D)/(1-D)
  const dIL    = dIin / Math.max(0.001, KD)
  const L      = Vin_pk * D / (fsw * dIL)
  return { L_uH: Math.round(L * 1e6), dIL: parseFloat(dIL.toFixed(3)), Iin_pk: parseFloat(Iin_pk.toFixed(2)) }
}

const PHASE_COLORS = ['#4f7cff','#2dd4a0','#f5a623','#a78bfa']

export const ChannelSelect: React.FC<Props> = ({ selectedTopology, controllerMode, intake, onSubmit, onBack, loading }) => {
  const [selN, setSelN] = useState(2)
  const isAnalog = controllerMode === 'analog'

  const { L_uH, dIL, Iin_pk } = calcLPy(intake)
  const Ipk = (N: number) => parseFloat((Iin_pk/N + dIL/2).toFixed(2))

  const COMPAT: Record<number,{label:string;color:string;notes:string[]}> = {
    2: {
      label: isAnalog ? 'Analog ✓ UCC28070A / NCP1631 / FAN9612' : 'Digital ✓ C2000 / STM32G4',
      color: C.green,
      notes: [
        `Simplest layout — 2 inductors, 2 switches, 1 bridge`,
        `L/phase: ${L_uH} µH (same for all N — sized from input ripple spec)`,
        `Ipk/phase: ${Ipk(2)} A at 90 Vac crest`,
        isAnalog ? 'Best analog IC support: UCC28070A hardwires 180° shift internally' : 'Standard for digital 2-phase PFC (C2000 TIDM-02013)',
      ]
    },
    3: {
      label: isAnalog ? 'Analog ✓ FAN9613 (ON Semi) — dedicated 3-phase' : 'Digital ✓ recommended',
      color: isAnalog ? C.amber : C.green,
      notes: [
        `L/phase: ${L_uH} µH (same for all N)`,
        `Ipk/phase: ${Ipk(3)} A — lower than 2-phase by ${((1-Ipk(3)/Ipk(2))*100).toFixed(0)}%`,
        isAnalog ? '⚠ No single-chip 3-phase analog PFC IC available' : '★ Optimal ripple/complexity at this power level',
        isAnalog ? 'Would need 3× single-phase IC + external 120° phase-shift RC network' : 'Phase balancing via TI C2000 or STM32G4 MCSDK',
      ]
    },
    4: {
      label: isAnalog ? 'Analog ✗ digital required' : 'Digital ✓ lowest Ipk',
      color: isAnalog ? C.red : C.accent,
      notes: [
        `L/phase: ${L_uH} µH (same for all N)`,
        `Ipk/phase: ${Ipk(4)} A — lowest per-switch current`,
        isAnalog ? '✗ No analog IC supports 4-phase interleaved PFC' : '4 gate drivers + 4 current sensors — complex layout',
        isAnalog ? '→ Switch back to Digital (Gate 3) if 4-phase needed' : 'Best EMI performance at 280 kHz effective ripple',
      ]
    },
  }

  const D_duty = 0.68
  const phaseColors = ['#4f7cff','#2dd4a0','#f5a623','#a78bfa']

  return (
    <div>
      <div style={{fontSize:20,fontWeight:500,marginBottom:3}}>Phase count</div>
      <div style={{fontSize:13,color:C.muted,marginBottom:14,display:'flex',alignItems:'center',gap:8,flexWrap:'wrap'}}>
        <Badge color="amber">Interleaved topologies only</Badge>
      </div>

      

      

      <div style={{display:'flex',gap:10,marginBottom:14}}>
        {[2,3,4].map((N: number) => {
          const isSel = selN === N
          const rec = N === (isAnalog ? 2 : 3)
          const compat = COMPAT[N]
          const selColor = N===2?C.green:N===3?(isAnalog?C.amber:C.green):isAnalog?C.red:C.accent
          return (
            <div key={N} data-testid="gate-option" onClick={() => setSelN(N)}
              style={{borderRadius:10,border:`2px solid ${isSel?selColor:C.border}`,background:isSel?`${selColor}18`:C.bg3,
                cursor:'pointer',overflow:'hidden',flex:1,transition:'all .2s'}}>
              <div style={{padding:'12px 14px 9px',borderBottom:`0.5px solid ${C.border}`,position:'relative'}}>
                {rec && <div style={{position:'absolute',top:8,right:8,fontSize:9,fontWeight:500,padding:'1px 5px',borderRadius:3,background:selColor,color:N<4?'#0a2a20':'#fff'}}>★ Rec</div>}
                <div style={{fontSize:38,fontWeight:500,lineHeight:1,color:isSel?selColor:C.muted}}>{N}</div>
                <div style={{fontSize:11,color:C.muted,marginTop:2}}>phases</div>
                <div style={{fontSize:10,padding:'2px 6px',borderRadius:4,display:'inline-block',marginTop:5,
                  background:`${selColor}22`,color:selColor,border:`0.5px solid ${selColor}55`}}>{compat.label}</div>
              </div>
              <div style={{padding:'11px 14px'}}>
                {[['L / phase',`${L_uH} µH`],['Ipk / phase',`${Ipk(N)} A`],[`Ripple freq`,`${N*70} kHz`],['Phase shift',`${360/N}°`]].map(([k,v]) => (
                  <div key={k} style={{display:'flex',justifyContent:'space-between',fontSize:11,marginBottom:4}}>
                    <span style={{color:C.hint}}>{k}</span>
                    <span style={{color:isSel?selColor:C.muted,fontWeight:500}}>{v}</span>
                  </div>
                ))}
                <div style={{height:3,background:C.border,borderRadius:2,overflow:'hidden',margin:'7px 0'}}>
                  <div style={{height:'100%',borderRadius:2,background:selColor,width:`${N===2?36:N===3?68:100}%`}}/>
                </div>
                <div style={{fontSize:10,color:C.hint,lineHeight:1.5}}>
                  {compat.notes.map((n,i)=><div key={i}>{n.startsWith('⚠')||n.startsWith('✗')?n:`→ ${n}`}</div>)}
                </div>
              </div>
            </div>
          )
        })}
      </div>

      <Card style={{marginBottom:14}}>
        <SecHead icon="📈" label="Phase gate timing — 360° / N interleave (D ≈ 0.68 at 90 Vac crest)" />
        {Array.from({length:selN},(_,ph) => {
          const off = (ph/selN)*100
          const segments: React.ReactNode[] = []
          for(let rep=0;rep<2;rep++){
            const s=((off+rep*100)%200), l=s/2, w=D_duty*50
            segments.push(<div key={`${ph}-${rep}`} style={{position:'absolute',top:0,height:'100%',borderRadius:2,left:`${l}%`,width:`${w}%`,background:phaseColors[ph%4],opacity:.85}}/>)
            if(l+w>100) segments.push(<div key={`${ph}-${rep}-wrap`} style={{position:'absolute',top:0,height:'100%',borderRadius:2,left:0,width:`${l+w-100}%`,background:phaseColors[ph%4],opacity:.85}}/>)
          }
          return (
            <div key={ph} style={{display:'flex',alignItems:'center',gap:9,marginBottom:7}}>
              <div style={{fontSize:11,color:C.hint,minWidth:54}}>Phase {ph+1}</div>
              <div style={{flex:1,height:20,background:C.bg4,borderRadius:4,position:'relative',overflow:'hidden'}}>{segments}</div>
            </div>
          )
        })}
        <div style={{fontSize:11,color:C.hint,marginTop:4}}>{selN}-phase · {360/selN}° apart · {selN*70} kHz effective ripple frequency</div>
      </Card>

      <div style={{display:'grid',gridTemplateColumns:'repeat(5,1fr)',gap:9,marginBottom:14}}>
        {[['Phases',String(selN)],[`L / phase`,`${L_uH} µH`],[`Ipk / phase`,`${Ipk(selN)} A`],[`Ripple freq`,`${selN*70} kHz`],['Phase shift',`${360/selN}°`]].map(([k,v])=>(
          <div key={k} style={{background:C.bg3,border:`0.5px solid ${C.border}`,borderRadius:7,padding:'9px 11px'}}>
            <div style={{fontSize:10,color:C.hint,marginBottom:3}}>{k}</div>
            <div style={{fontSize:15,fontWeight:500,color:C.accent}}>{v}</div>
          </div>
        ))}
      </div>

      <div style={{display:'flex',alignItems:'center',justifyContent:'space-between',paddingTop:12,borderTop:`0.5px solid ${C.border}`}}>
        <div>
          <div style={{fontSize:11,color:C.hint}}>Selected</div>
          <div style={{fontSize:14,fontWeight:500,color:C.accent}}>{selN}-phase interleaved</div>
          {isAnalog && selN > 2 && <div style={{fontSize:11,color:selN===3?C.amber:C.red,marginTop:3}}>{COMPAT[selN].label}</div>}
        </div>
        <div style={{display:'flex',gap:8}}>
          <Btn variant="ghost" onClick={onBack} disabled={loading}>← Back</Btn>
          <Btn variant="primary" onClick={() => onSubmit({approved:true,n_channels:selN})} disabled={loading}>
            {loading ? 'Processing…' : 'Confirm →'}
          </Btn>
        </div>
      </div>
    </div>
  )
}
