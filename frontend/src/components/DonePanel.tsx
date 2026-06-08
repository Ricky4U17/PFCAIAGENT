import React from 'react'
import { Card, SecHead, Btn, C } from './ui'
import type { DocReportStatus } from '../api/client'

interface Summary {
  topology: string; mode: string; channels: number
  controllerMode: string; fsw: string; crest: string
  controller: string; ctrlMode: string
  appClass?: string; leakage?: number
  analogIcUpdate?: boolean
}

const TOPO_LABEL: Record<string,string> = {
  single_boost_ccm:'Single Boost — CCM', interleaved_boost_ccm:'Interleaved Boost — CCM',
  boost_crcm:'Single Boost — CrCM', boost_dcm:'Single Boost — DCM',
  totem_pole_ccm:'Totem-Pole PFC — CCM', totem_pole_interleaved_ccm:'Totem-Pole Interleaved — CCM',
}
const ML: Record<string,string> = {ccm:'CCM',crcm:'CrCM',dcm:'DCM'}

const MB_STEPS = [
  ['input_processing','Steps 1-12 PDF ✓'],['duty_and_ripple','Steps 1-12 PDF ✓'],
  ['inductor_sizing','Steps 1-12 PDF ✓'],['worst_case_angle','Steps 1-12 PDF ✓'],
  ['waveform_reconstruction','Steps 1-12 PDF ✓'],['magnetic_design','Step 6 API ✓'],
  ['magnetic_design_v2_advisory','Step 7 ✓ — HITL Magnetic Design (Step 13)'],['magnetic_fea_advisory','Step 8 ✓ — Time-Domain Pcore(t) (Step 14)'],
  ['protection_compliance','Queued'],['emi_filter','Queued'],
  ['layout_parasitics_advisory','Queued'],['control_loops','Queued'],
  ['state_space_analysis','Queued'],['guardrail_v2_advisory','Queued'],
  ['bidirectional_thermal','Queued'],['cad_thermal_integration_advisory','Queued'],
  ['vendor_scout','Queued'],['supply_chain_advisory','Queued'],
  ['reliability_mtbf_advisory','Queued'],['design_graphs','Queued'],
  ['simulation_export','Queued'],['closed_loop_simulation_advisory','Queued'],
  ['firmware_generation_advisory','Queued'],['pcb_floorplanning_advisory','Queued'],
  ['altium_export','Queued'],
]

interface Props {
  summary: Summary
  onRestart: () => void
  onStartStep7?: () => void
  onGenerateReport: () => void
  reportLoading: boolean
  reportReady: boolean
  reportBytes: ArrayBuffer | null
  docStatus?: DocReportStatus | null
  docStatusLoading?: boolean
}

export const DonePanel: React.FC<Props> = ({summary, onRestart, onGenerateReport, reportLoading, reportReady, reportBytes, onStartStep7, docStatus, docStatusLoading}) => {
  const isMedical = summary.appClass === 'Medical'

  const downloadReport = () => {
    if (!reportBytes) return
    const blob = new Blob([reportBytes], { type: 'application/pdf' })
    const url  = URL.createObjectURL(blob)
    const a    = document.createElement('a')
    a.href = url
    a.download = 'PFC_Design_Report_Steps1_12.pdf'
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    setTimeout(() => URL.revokeObjectURL(url), 150)
  }

  return (
    <div style={{display:'grid',gridTemplateColumns:'1fr 400px',gap:20,alignItems:'start'}}>
    <div>{/* LEFT: spec + mode-B pipeline */}
      <div style={{textAlign:'center',padding:'28px 0 30px'}}>
        <div style={{fontSize:52,marginBottom:12}}>✅</div>
        <div style={{fontSize:22,fontWeight:500,marginBottom:6}}>Mode A complete</div>
      </div>
      <div style={{background:'rgba(55,138,221,0.06)',border:'0.5px solid rgba(55,138,221,0.3)',borderRadius:10,padding:'14px 18px',marginTop:16,marginBottom:4}}>
        <div style={{fontSize:13,color:'#a0aec0',lineHeight:1.7}}>
          Download the report and review. If you agree, go to the next step of Magnetic Design. If you want to change anything, return to Mode A.
        </div>
      </div>

      {isMedical && (
        <Card style={{background:C.amberL,border:`1px solid ${C.amber}55`,marginBottom:14}}>
          <div style={{fontWeight:500,fontSize:13,color:C.amber,marginBottom:6}}>⚕ Medical class summary</div>
          <div style={{fontSize:12,color:C.muted,lineHeight:1.6}}>
            <div>Leakage limit: {summary.leakage||500} µA (locked from Gate 1) · Topology confirmed safe (Interleaved Boost avoids TTP zero-crossing leakage)</div>
            {summary.analogIcUpdate && <div style={{marginTop:4}}>Controller IC updated Gate 3→Gate 4: <strong style={{color:C.green}}>UCC28070A / NCP1631 / FAN9612</strong> (dedicated 2-phase analog PFC ICs)</div>}
          </div>
        </Card>
      )}

      <Card style={{marginBottom:14}}>
        <SecHead icon="📋" label="Specification and Criteria Selection" />
        <div style={{display:'grid',gridTemplateColumns:'repeat(5,1fr)',gap:8,marginBottom:12}}>
          {[
            ['Gate 1','Intake','3.6 kW · 90–264 Vac'],
            ['Gate 2','Topology', `${TOPO_LABEL[summary.topology]||summary.topology}`],
            ['Gate 3','Controller', `${summary.ctrlMode==='digital'?'Digital':'Analog'}`],
            ['Gate 4','Channels', `${summary.channels} phase${summary.channels>1?'s':''}`],
            ['Gate 5','Mini', `${summary.fsw} · r=${summary.crest}`],
          ].map(([g,s,v]) => (
            <div key={g} style={{padding:'10px 12px',borderRadius:7,background:C.greenL,border:`0.5px solid ${C.green}44`,textAlign:'center'}}>
              <div style={{fontSize:10,color:C.green,fontWeight:500,marginBottom:3}}>{g} · {s} ✓</div>
              <div style={{fontSize:11,color:C.muted,lineHeight:1.4}}>{v}</div>
            </div>
          ))}
        </div>
        <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:9}}>
          {[
            ['Selected topology', TOPO_LABEL[summary.topology]||summary.topology],
            ['Operating mode',    ML[summary.mode]||summary.mode],
            ['Interleaved phases',String(summary.channels)],
            ['Controller type',  `${summary.ctrlMode==='digital'?'Digital':'Analog'} control`],
            ['Switching frequency',summary.fsw],
            ['Crest ripple ratio', summary.crest],
            ...(isMedical ? [['Application class','Medical · '+summary.leakage+' µA leakage'],['EMI','FCC Class B · EN 61000-3-2']] : []),
          ].map(([k,v]) => (
            <div key={k} style={{padding:'12px 14px',background:C.bg4,borderRadius:7,border:`0.5px solid ${C.border}`}}>
              <div style={{fontSize:11,color:C.hint,marginBottom:4}}>{k}</div>
              <div style={{fontWeight:600,fontSize:14,color:C.text}}>{v}</div>
            </div>
          ))}
        </div>
      </Card>

      <Card>
        <SecHead icon="🔄" label="Mode B — 25-step engineering sequence" />
        <div style={{display:'flex',flexWrap:'wrap',gap:5,marginBottom:10}}>
          {MB_STEPS.map(([s,status],i) => (
            <div key={s} style={{padding:'3px 9px',borderRadius:5,fontSize:11,
              background:status.includes('✓')?C.greenL:C.bg4,
              border:`0.5px solid ${status.includes('✓')?C.green:C.border}`,
              color:status.includes('✓')?C.green:C.hint}}>
              {i+1}. {s.replace(/_/g,' ')} {status.includes('✓')?'✓':''}
            </div>
          ))}
        </div>
        <div style={{fontSize:12,color:C.hint,lineHeight:1.5}}>
          Steps 1–5 (green): covered by this report. Step 6 magnetic_design: available via{' '}
          <code style={{background:C.bg4,padding:'1px 5px',borderRadius:3}}>POST /mode-b/step6-magnetic-design</code>.
          Steps 7–25: queued — each will pause at{' '}
          <code style={{background:C.bg4,padding:'1px 5px',borderRadius:3}}>mode_b_hitl</code>{' '}
          for designer approval.
        </div>
      </Card>

    </div>{/* end LEFT column */}

    {/* ── RIGHT column: report + quick actions ── */}
    <div style={{position:'sticky',top:16,display:'flex',flexDirection:'column',gap:12}}>

      {/* ── Documentation Agent: Report Status ── */}
      <Card style={{marginBottom:0}}>
        <SecHead icon="📊" label="Report coverage" />
        {docStatusLoading && (
          <div style={{display:'flex',alignItems:'center',gap:8,fontSize:12,color:C.hint,padding:'4px 0 8px'}}>
            <span style={{display:'inline-block',width:14,height:14,border:`2px solid ${C.border2}`,borderTopColor:C.accent,borderRadius:'50%',animation:'spin .6s linear infinite'}}/>
            Checking chapters…
          </div>
        )}
        {docStatus && !docStatusLoading && (
          <div>
            <div style={{fontSize:12,color:C.muted,marginBottom:8}}>
              Ready to generate: <strong style={{color:C.green}}>{docStatus.ready_label}</strong>
            </div>
            <div style={{display:'flex',flexDirection:'column',gap:4}}>
              {docStatus.chapters.map(ch => (
                <div key={ch.chapter} style={{
                  display:'flex',alignItems:'center',gap:8,padding:'6px 10px',
                  borderRadius:6,fontSize:11,
                  background: ch.status==='ready' ? C.greenL : C.bg4,
                  border:`0.5px solid ${ch.status==='ready' ? C.green+'44' : C.border}`,
                }}>
                  <span style={{fontSize:13}}>{ch.status==='ready' ? '✅' : '⏳'}</span>
                  <div style={{flex:1}}>
                    <span style={{fontWeight:600,color: ch.status==='ready' ? C.green : C.text}}>
                      Ch.{ch.chapter} {ch.title}
                    </span>
                    {ch.status!=='ready' && ch.missing[0] && (
                      <div style={{color:C.hint,marginTop:1,fontSize:10}}>{ch.missing[0]}</div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
        {!docStatus && !docStatusLoading && (
          <div style={{fontSize:11,color:C.hint}}>Chapter status loads automatically after Mode A.</div>
        )}
      </Card>

      <Card style={{marginBottom:0}}>
        <SecHead icon="📄" label="Download the report" />
        {!reportReady && !reportLoading && (
          <button onClick={onGenerateReport} style={{width:'100%',padding:'13px 20px',borderRadius:9,cursor:'pointer',
            fontSize:14,fontWeight:600,fontFamily:'inherit',border:'none',background:C.accent,color:'#fff',
            display:'flex',alignItems:'center',justifyContent:'center',gap:10}}>
            📄 Generate Report
          </button>
        )}
        {reportLoading && (
          <div style={{background:C.bg4,border:`1px solid ${C.border2}`,borderRadius:9,padding:'20px 24px',display:'flex',alignItems:'center',gap:14}}>
            <span style={{display:'inline-block',width:22,height:22,border:`2px solid ${C.border2}`,borderTopColor:C.accent,borderRadius:'50%',animation:'spin .6s linear infinite',flexShrink:0}}/>
            <div><div style={{fontSize:14,fontWeight:600,color:C.text}}>Generating report…</div></div>
          </div>
        )}
        {reportReady && reportBytes && (
          <div style={{background:C.greenL,border:`1px solid ${C.green}44`,borderRadius:9,padding:'16px 20px'}}>
            <div style={{display:'flex',alignItems:'center',gap:10,marginBottom:12}}>
              <span style={{fontSize:20}}>✅</span>
              <div>
                <div style={{fontSize:14,fontWeight:600,color:C.green}}>Report ready</div>
                <div style={{fontSize:11,color:C.muted}}>PFC_Design_Report_Steps1_12.pdf</div>
              </div>
            </div>
            <button onClick={downloadReport} style={{width:'100%',padding:'11px 20px',borderRadius:8,cursor:'pointer',
              fontSize:14,fontWeight:600,fontFamily:'inherit',background:C.green,color:'#0a2a20',border:'none',
              display:'flex',alignItems:'center',justifyContent:'center',gap:8}}>
              ⬇ Download PDF Report
            </button>
          </div>
        )}
      </Card>

      {onStartStep7 && (
        <button onClick={onStartStep7}
          style={{width:'100%',padding:'16px 20px',borderRadius:9,cursor:'pointer',
            fontSize:15,fontWeight:600,border:'none',fontFamily:'inherit',
            background:'#166534',color:'#2dd4a0'}}>
          🧲 Go to Magnetic Design
        </button>
      )}
      <Btn variant="ghost" onClick={onRestart} style={{width:'100%'}}>↺ Start new Mode A design</Btn>
    </div>
    </div>
  )
}
