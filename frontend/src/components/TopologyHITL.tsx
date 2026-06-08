import React, { useState } from 'react'
import { Card, SecHead, Btn, Badge, ScoreBar, C } from './ui'
import type { Candidate, ModeScore } from '../api/client'

interface Props {
  ranking: Candidate[]
  modeScores: ModeScore[]
  recommendedTopology: string
  recommendedMode: string
  appClass?: string
  onSubmit: (fb: { approved: boolean; selected_topology: string }) => void
  onBack: () => void
  loading: boolean
}

const TOPO_LABEL: Record<string,string> = {
  single_boost_ccm:'Single Boost — CCM', interleaved_boost_ccm:'Interleaved Boost — CCM',
  boost_crcm:'Single Boost — CrCM', boost_dcm:'Single Boost — DCM',
  totem_pole_ccm:'Totem-Pole PFC — CCM', totem_pole_interleaved_ccm:'Totem-Pole Interleaved — CCM',
}
const MODE_LABEL: Record<string,string> = {ccm:'CCM',crcm:'CrCM',dcm:'DCM'}
const DIMS = ['high_power_fit','emi_predictability','thermal_current_stress','fixed_frequency_fit','implementation_risk','power_density_fit']
const DIM_LABEL: Record<string,string> = {high_power_fit:'High power fit',emi_predictability:'EMI predictability',thermal_current_stress:'Thermal stress',fixed_frequency_fit:'Fixed freq fit',implementation_risk:'Impl. risk',power_density_fit:'Power density'}
const IS_TTP = (t: string) => t.includes('totem_pole')
const MEDICAL_SAFE_TOPOS = new Set(['single_boost_ccm','interleaved_boost_ccm','boost_crcm','boost_dcm'])

export const TopologyHITL: React.FC<Props> = ({ranking,modeScores,recommendedTopology,recommendedMode,appClass,onSubmit,onBack,loading}) => {
  const [sel, setSel] = useState(recommendedTopology)
  const isMedical = appClass === 'Medical'

  return (
    <div>
      <div style={{fontSize:20,fontWeight:500,marginBottom:3}}>Topology selection</div>
      <div style={{marginBottom:18}} />

      {isMedical && (
        <Card style={{background:C.amberL,border:`1px solid ${C.amber}55`,marginBottom:14}}>
          <div style={{fontWeight:500,fontSize:13,color:C.amber,marginBottom:8,display:'flex',alignItems:'center',gap:8}}>
            ⚕ Medical class advisory — leakage 500 µA (not scored automatically)
          </div>
          <div style={{fontSize:12,color:C.muted,lineHeight:1.6}}>
            <div style={{marginBottom:4}}>→ Totem-pole (#2/#3): leakage risk at 500 µA — switch body diodes + SiC Coss charge at zero-crossing. Requires careful Y-cap management.</div>
            <div style={{marginBottom:4}}>→ Interleaved Boost CCM (#1): <strong style={{color:C.green}}>Medical ✓ safe</strong> — rectifier bridge always in-circuit, straightforward 500 µA compliance with Y-caps ≤ 2.2 nF.</div>
            <div>Confirm Interleaved Boost CCM unless TTP leakage has been verified with your specific SiC device Coss.</div>
          </div>
        </Card>
      )}

      <Card style={{marginBottom:14}}>
        <SecHead icon="📊" label="Mode scoring" />
        <div style={{display:'grid',gridTemplateColumns:'1fr 1fr 1fr',gap:10}}>
          {modeScores.map(m => {
            const isWinner = m.mode === recommendedMode
            return (
              <div key={m.mode} style={{borderRadius:8,padding:'12px 14px',border:`1.5px solid ${isWinner?C.accent:C.border}`,background:isWinner?C.accentL:C.bg3}}>
                {isWinner && <div style={{fontSize:10,fontWeight:500,padding:'1px 6px',borderRadius:3,background:C.accent,color:'#fff',display:'inline-block',marginBottom:6}}>WINNER</div>}
                <div style={{fontSize:13,fontWeight:500,color:isWinner?C.accent:C.muted,marginBottom:2}}>{MODE_LABEL[m.mode]||m.mode}</div>
                <div style={{fontSize:20,fontWeight:500,color:isWinner?C.accent:C.muted,marginBottom:3}}>{m.final_score.toFixed(3)}<span style={{fontSize:10,opacity:.6}}>/5</span></div>
                {m.penalty>0 && <div style={{fontSize:10,color:C.amber,marginBottom:5}}>−{m.penalty.toFixed(2)} penalty</div>}
                {DIMS.map(d => (
                  <div key={d} style={{marginBottom:2}}>
                    <div style={{display:'flex',justifyContent:'space-between',fontSize:10,color:C.hint}}><span>{DIM_LABEL[d]}</span><span>{(m.raw_scores||{})[d]||0}/5</span></div>
                    <ScoreBar value={((m.raw_scores||{})[d]||0)/5} />
                  </div>
                ))}
              </div>
            )
          })}
        </div>
      </Card>

      <Card>
        <SecHead icon="🏆" label="Topology ranking" />
        {ranking.map((r, i) => {
          const isSel = r.topology === sel
          const isRec = r.topology === recommendedTopology
          const isTTP = IS_TTP(r.topology)
          const isMedSafe = MEDICAL_SAFE_TOPOS.has(r.topology)
          return (
            <div key={r.topology} onClick={() => setSel(r.topology)}
              style={{padding:'12px 14px',borderRadius:8,cursor:'pointer',marginBottom:8,
                border:`1.5px solid ${isSel?C.accent:C.border}`,background:isSel?C.accentL:C.bg3,transition:'all .15s'}}>
              <div style={{display:'flex',justifyContent:'space-between',alignItems:'flex-start'}}>
                <div style={{flex:1}}>
                  <div style={{fontSize:10,color:C.hint,marginBottom:3}}>
                    #{i+1} · base {r.base_score.toFixed(3)}{r.bonus!==0?` bonus `:''}
                    {r.bonus!==0 && <span style={{color:r.bonus>0?C.green:C.red}}>{r.bonus>0?'+':''}{r.bonus.toFixed(3)}</span>}
                  </div>
                  <div style={{fontSize:13,fontWeight:500,marginBottom:5,color:isSel?C.accent:C.text}}>
                    {TOPO_LABEL[r.topology]||r.topology}
                  </div>
                  <div style={{display:'flex',gap:5,flexWrap:'wrap',marginBottom:4}}>
                    {isRec && <Badge color="blue">Recommended</Badge>}
                    {isMedical && isMedSafe && <Badge color="green">Medical ✓ safe</Badge>}
                    {isMedical && !isMedSafe && <Badge color="amber">Medical ⚠ verify leakage</Badge>}
                    <Badge color="gray">{MODE_LABEL[r.mode]||r.mode}</Badge>
                  </div>
                  {(r.penalty_details||[]).slice(0,3).map((n,j) => (
                    <div key={j} style={{fontSize:11,color:n.toLowerCase().includes('penali')||n.toLowerCase().includes('de-pri')?C.amber:C.muted,marginBottom:2}}>
                      {n.toLowerCase().includes('penali')||n.toLowerCase().includes('de-pri')?'⚠':'✓'} {n}
                    </div>
                  ))}
                </div>
                <div style={{textAlign:'right',minWidth:80,marginLeft:10}}>
                  <div style={{fontSize:20,fontWeight:500,color:isSel?C.accent:r.final_score<0?C.red:C.text}}>
                    {r.final_score.toFixed(3)}<span style={{fontSize:10,opacity:.55}}>/6.6</span>
                  </div>
                  <ScoreBar value={Math.max(0,r.final_score)/6.6} />
                </div>
              </div>
            </div>
          )
        })}
        <div style={{display:'flex',alignItems:'center',justifyContent:'space-between',paddingTop:12,borderTop:`0.5px solid ${C.border}`,marginTop:4,flexWrap:'wrap',gap:10}}>
          <div>
            <div style={{fontSize:11,color:C.hint}}>Selected</div>
            <div style={{fontSize:14,fontWeight:500,color:C.accent}}>{TOPO_LABEL[sel]||sel}</div>
            {isMedical && IS_TTP(sel) && <div style={{fontSize:11,color:C.amber,marginTop:3}}>⚠ Verify 500 µA leakage before proceeding</div>}
          </div>
          <div style={{display:'flex',gap:8}}>
            <Btn variant="ghost" onClick={onBack} disabled={loading}>← Back</Btn>
            <Btn variant="primary" onClick={() => onSubmit({approved:true,selected_topology:sel})} disabled={loading || !sel}>
              {loading ? 'Processing…' : 'Approve & continue →'}
            </Btn>
          </div>
        </div>
      </Card>
    </div>
  )
}
