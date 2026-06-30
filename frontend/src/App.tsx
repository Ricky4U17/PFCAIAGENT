import React, { useState, useEffect } from 'react'
import { api, docReportStatus, docGenerateReport } from './api/client'
import type { Candidate, ModeScore, ControllerStrategy, MiniDefaults, DocReportStatus } from './api/client'
import { TopBar, ErrBanner, Spinner, C } from './components/ui'
import { Stepper } from './components/Stepper'
import { IntakeForm } from './components/IntakeForm'
import type { IntakeData } from './components/IntakeForm'
import { TopologyHITL } from './components/TopologyHITL'
import { ControllerHITL } from './components/ControllerHITL'
import { ChannelSelect } from './components/ChannelSelect'
import { MiniIntakeGate } from './components/MiniIntakeGate'
import { DonePanel } from './components/DonePanel'
import { Step7Wizard } from './components/Step7Wizard'
import { Step15Wizard } from './components/Step15Wizard'
import { ControlDesign } from './components/ControlDesign'
import { CapacitorSimAgent } from './components/CapacitorSimAgent'
import { SemiconductorSelection } from './components/SemiconductorSelection'
import { InputProtection } from './components/InputProtection'
import { InputFilter } from './components/InputFilter'
import type { CapacitorResult } from './components/Step15Capacitor'

type Step = 'intake'|'topology'|'controller'|'channels'|'mini'|'done'|'step7'|'step15'|'capsim'|'step16'|'semiconductors'|'inputprotection'|'inputfilter'

interface AppState {
  step: Step; loading: boolean; error: string|null; backendStatus: 'ok'|'error'|'checking'
  graphState: Record<string,unknown>|null
  ranking: Candidate[]; modeScores: ModeScore[]; recommendedTopology: string; recommendedMode: string
  selectedTopology: string; selectedMode: string
  controllerStrategy: ControllerStrategy|null; selectedControllerMode: string
  isInterleaved: boolean; selectedChannels: number
  miniDefaults: MiniDefaults|null; miniErrors: string[]
  summary: { topology:string;mode:string;channels:number;controllerMode:string;fsw:string;crest:string;
             controller:string;ctrlMode:string;appClass?:string;leakage?:number;analogIcUpdate?:boolean }|null
  reportLoading: boolean; reportReady: boolean; reportBytes: ArrayBuffer|null
  // carry-through
  intakeData: IntakeData|null
  approvedInductorDesign:  Record<string,unknown>|null
  approvedCapacitorDesign: CapacitorResult|null
  // documentation agent
  docStatus: DocReportStatus|null; docStatusLoading: boolean
}

const INIT: AppState = {
  step:'intake',loading:false,error:null,backendStatus:'checking',
  graphState:null,ranking:[],modeScores:[],recommendedTopology:'',recommendedMode:'',
  selectedTopology:'',selectedMode:'',controllerStrategy:null,selectedControllerMode:'',
  isInterleaved:false,selectedChannels:1,miniDefaults:null,miniErrors:[],summary:null,
  reportLoading:false,reportReady:false,reportBytes:null,intakeData:null,
  approvedInductorDesign:null, approvedCapacitorDesign:null,
  docStatus:null, docStatusLoading:false,
}

// ── E2E test seam ────────────────────────────────────────────────────────────
// Lets the Playwright control-report test land directly on the Control Design
// step with minimal mock carry-through, so it can exercise the REAL ControlDesign
// component + iframe + "Control-Loop Report" button against the live backend
// without scripting the DB-backed Step-7/Step-15 selection UIs. Activated only
// when window.__E2E_CONTROL__ is set (via Playwright addInitScript); inert in
// normal use.
function _e2eInit(): AppState | null {
  if (typeof window === 'undefined' || !(window as any).__E2E_CONTROL__) return null
  const intake = {
    application: {
      vin_rms_min: 90, vin_rms_max: 264, output_bus_voltage_v: 393.7,
      output_power_w_low_line: 1700, output_power_w_high_line: 3600,
    },
  } as unknown as IntakeData
  return {
    ...INIT, step: 'step16', backendStatus: 'ok',
    graphState: { project_id: 'e2e', intake, topology_specific_inputs: { recommended_frequency_hz: 70000 } },
    intakeData: intake, selectedChannels: 2,
    approvedInductorDesign: { L_target_uH: 235, DCR_100C_mOhm: 28 } as Record<string, unknown>,
    approvedCapacitorDesign: { C_total_uF: 2200, ESR_parallel_mohm: 5 } as unknown as CapacitorResult,
  }
}

const TOPO_LABEL: Record<string,string> = {
  single_boost_ccm:'Single Boost — CCM',interleaved_boost_ccm:'Interleaved Boost — CCM',
  boost_crcm:'Single Boost — CrCM',boost_dcm:'Single Boost — DCM',
  totem_pole_ccm:'Totem-Pole PFC — CCM',totem_pole_interleaved_ccm:'Totem-Pole Interleaved — CCM',
}
const ML: Record<string,string> = {ccm:'CCM',crcm:'CrCM',dcm:'DCM'}
const SS: Record<Step,string> = {
  intake:'mode-a / intake',topology:'mode-a / topology-hitl',controller:'mode-a / controller-hitl',
  channels:'mode-a / channel-selection',mini:'mode-a / mini-intake',done:'mode-a / complete',
  step7:'mode-b / step-7-magnetic-design', step15:'mode-b / step-15-capacitor',
  capsim:'mode-b / dc-bus-cap-simulation', step16:'mode-b / step-16-control-design',
  semiconductors:'mode-b / chapter-7-semiconductor-selection',
  inputprotection:'mode-b / input-protection-mov-ntc',
  inputfilter:'mode-b / input-emi-filter',
}

export default function App() {
  const [s, setS] = useState<AppState>(() => _e2eInit() ?? INIT)

  useEffect(() => {
    api.health().then(() => setS(p=>({...p,backendStatus:'ok'}))).catch(() => setS(p=>({...p,backendStatus:'error'})))
  }, [])

  const setLoading = (v: boolean) => setS(p=>({...p,loading:v}))
  const setError   = (e: string|null) => setS(p=>({...p,error:e}))

  const appClass = s.intakeData?.compliance?.application_class as string|undefined
  const leakage  = s.intakeData?.compliance?.leakage_current_limit_ua as number|undefined

  const handleIntake = async (intake: IntakeData) => {
    setLoading(true); setError(null)
    try {
      const r = await api.start('pfc-'+Date.now(), intake)
      setS(p=>({...p,loading:false,step:'topology',graphState:r.state,intakeData:intake,
        ranking:r.ranking,modeScores:r.mode_scores,
        recommendedTopology:r.recommended_topology,recommendedMode:r.recommended_mode}))
    } catch(e) { setLoading(false); setError((e as Error).message) }
  }

  const handleTopology = async (fb:{approved:boolean;selected_topology:string}) => {
    setLoading(true); setError(null)
    try {
      const r = await api.approveTopology(s.graphState, fb)
      setS(p=>({...p,loading:false,step:'controller',graphState:r.state,
        selectedTopology:r.selected_topology,selectedMode:r.selected_mode,
        controllerStrategy:r.controller_strategy}))
    } catch(e) { setLoading(false); setError((e as Error).message) }
  }

  const handleController = async (fb:{approved:boolean;controller_mode:string}) => {
    setLoading(true); setError(null)
    try {
      const r = await api.approveController(s.graphState, fb)
      const ctrl = r.selected_controller_mode
      if (r.status === 'wait_channels') {
        setS(p=>({...p,loading:false,step:'channels',graphState:r.state,selectedControllerMode:ctrl,isInterleaved:true}))
      } else {
        setS(p=>({...p,loading:false,step:'mini',graphState:r.state,selectedControllerMode:ctrl,
          isInterleaved:false,selectedChannels:1,miniDefaults:r.mini_intake_defaults??null,miniErrors:[]}))
      }
    } catch(e) { setLoading(false); setError((e as Error).message) }
  }

  const handleChannels = async (fb:{approved:boolean;n_channels:number}) => {
    setLoading(true); setError(null)
    try {
      const r = await api.approveChannels(s.graphState, fb)
      setS(p=>({...p,loading:false,step:'mini',graphState:r.state,
        selectedChannels:r.selected_channels,miniDefaults:r.mini_intake_defaults??null,miniErrors:r.validation_errors??[]}))
    } catch(e) { setLoading(false); setError((e as Error).message) }
  }

  const handleMini = async (fb: Record<string,unknown>) => {
    setLoading(true); setError(null)
    try {
      const r = await api.submitMiniIntake(s.graphState, fb)
      if (r.status === 'wait_mini_intake') {
        setS(p=>({...p,loading:false,miniErrors:r.validation_errors??[],
          miniDefaults:r.mini_intake_defaults??p.miniDefaults,graphState:r.state})); return
      }
      const tsi = (r.topology_specific_inputs ?? {}) as Record<string,unknown>
      const style = tsi.switching_frequency_style as string
      const hz    = tsi.recommended_frequency_hz as number|null
      const range = tsi.recommended_frequency_range_hz as [number,number]|null
      const crest = tsi.default_crest_ripple_ratio as number
      const isAnalogInterleaved = s.selectedControllerMode==='analog' && s.isInterleaved
      setS(p=>({...p,loading:false,step:'done',graphState:r.state,
        reportLoading:false,reportReady:false,reportBytes:null,
        docStatus:null,docStatusLoading:true,
        summary:{
          topology:r.selected_topology??p.selectedTopology,
          mode:r.selected_mode??p.selectedMode,
          channels:r.selected_channels??p.selectedChannels,
          controllerMode:r.selected_controller_mode??p.selectedControllerMode,
          ctrlMode:r.selected_controller_mode??p.selectedControllerMode,
          controller:`${(r.selected_controller_mode??'digital')==='digital'?'Digital':(r.selected_controller_mode??'digital')==='digital_arm'?'Digital ARM':'Analog'} · ${r.selected_channels??p.selectedChannels} phases`,
          fsw:style==='fixed'?`${(hz??70000).toLocaleString()} Hz`
             :style==='variable'?`${range?.map(v=>v.toLocaleString()).join(' – ')} Hz`:'System recommended',
          crest:String(crest??'—'),
          appClass, leakage,
          analogIcUpdate: isAnalogInterleaved,
        }}))
      // Fetch doc status silently in background — non-blocking
      docReportStatus({ state: r.state })
        .then(ds => setS(p=>({...p, docStatus:ds, docStatusLoading:false})))
        .catch(() => setS(p=>({...p, docStatusLoading:false})))
    } catch(e) { setLoading(false); setError((e as Error).message) }
  }

  const handleGenerateReport = async () => {
    setS(p=>({...p,reportLoading:true,reportReady:false,reportBytes:null})); setError(null)
    try {
      const blob  = await docGenerateReport({ state: s.graphState as Record<string, unknown> })
      const bytes = await blob.arrayBuffer()
      setS(p=>({...p,reportLoading:false,reportReady:true,reportBytes:bytes}))
    } catch(e) {
      setS(p=>({...p,reportLoading:false})); setError(`Report generation failed: ${(e as Error).message}`)
    }
  }

  const handleStep7Approve = (design: Record<string,unknown>) => {
    setS(p => ({...p, step:'step15', approvedInductorDesign:design}))
  }

  const handleStep15Approve = (cap: CapacitorResult) => {
    // Approving the capacitor now routes through the DC-bus simulation check
    // before Control Design (Step 16).
    setS(p => ({...p, step:'capsim', approvedCapacitorDesign:cap}))
  }

  const restart = () => setS({...INIT, backendStatus:s.backendStatus})
  const goBack  = (step: Step) => setS(p=>({...p,step,error:null}))

  const intake = s.intakeData
  const ctxItems = [
    s.selectedTopology && `🔒 ${TOPO_LABEL[s.selectedTopology]||s.selectedTopology}`,
    s.selectedMode     && `🔒 ${ML[s.selectedMode]||s.selectedMode}`,
    s.selectedControllerMode && `🔒 ${s.selectedControllerMode==='digital'?'Digital':s.selectedControllerMode==='digital_arm'?'Digital ARM':'Analog'}`,
    (s.step==='mini'||s.step==='done')&&s.isInterleaved&&s.selectedChannels&&`🔒 ${s.selectedChannels} phases`,
  ].filter(Boolean) as string[]

  return (
    <div style={{minHeight:'100vh',background:C.bg}}>
      <style>{`
        @keyframes spin { to { transform: rotate(360deg); } }
        input[type=range] { accent-color: ${C.accent}; }
        * { box-sizing: border-box; }
        input, select { padding: 6px 10px; border-radius: 6px; border: 1px solid ${C.border}; background: ${C.bg3}; color: ${C.text}; font-size: 13px; font-family: inherit; width: 100%; }
        input:focus, select:focus { outline: none; border-color: ${C.accent}; }
        code { background: ${C.bg4}; padding: 1px 5px; border-radius: 3px; font-family: 'IBM Plex Mono', monospace; font-size: 12px; }
        @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@300;400;500;600&display=swap');
      `}</style>

      <TopBar sub={SS[s.step]} status={s.backendStatus} />
      <Stepper current={s.step} />

      <div style={{maxWidth:1560,margin:'0 auto',padding:'24px 28px 64px',fontFamily:'IBM Plex Sans,sans-serif'}}>
        {s.backendStatus==='error' && (
          <div style={{background:C.redL,border:`1px solid ${C.red}55`,borderRadius:8,padding:'12px 16px',marginBottom:20,fontSize:13,color:'#fca5a5'}}>
            ⚠ Backend offline. Start with: <code>cd backend && uvicorn app.main:app --reload --port 8000</code>
          </div>
        )}
        {s.error && (
          <div style={{background:C.redL,border:`1px solid ${C.red}55`,borderRadius:8,padding:'12px 16px',marginBottom:20,fontSize:13,color:'#fca5a5',display:'flex',justifyContent:'space-between',alignItems:'flex-start'}}>
            <div>⚠ {s.error}</div>
            <button onClick={()=>setError(null)} style={{background:'none',border:'none',color:'#fca5a5',cursor:'pointer',fontSize:16}}>✕</button>
          </div>
        )}
        {ctxItems.length > 0 && s.step !== 'intake' && s.step !== 'topology' && (
          <div style={{background:C.bg3,border:`1px solid ${C.border}`,borderRadius:10,padding:'10px 16px',marginBottom:18,display:'flex',alignItems:'center',flexWrap:'wrap',gap:8}}>
            {ctxItems.map((t,i,arr) => (
              <React.Fragment key={i}>
                <span style={{fontSize:11,fontFamily:'IBM Plex Mono,monospace',color:C.muted}}>
                  <strong style={{color:'#2dd4a0'}}>{t}</strong>
                </span>
                {i<arr.length-1 && <div style={{width:1,height:12,background:C.border2}}/>}
              </React.Fragment>
            ))}
          </div>
        )}

        {s.step==='intake'     && <IntakeForm onSubmit={handleIntake} loading={s.loading} />}
        {s.step==='topology'   && <TopologyHITL ranking={s.ranking} modeScores={s.modeScores}
          recommendedTopology={s.recommendedTopology} recommendedMode={s.recommendedMode}
          appClass={appClass} onSubmit={handleTopology} onBack={()=>goBack('intake')} loading={s.loading} />}
        {s.step==='controller' && s.controllerStrategy && <ControllerHITL
          strategy={s.controllerStrategy} selectedTopology={s.selectedTopology}
          isInterleaved={s.isInterleaved} appClass={appClass} nPhases={s.selectedChannels||2}
          onSubmit={handleController} onBack={()=>goBack('topology')} loading={s.loading} />}
        {s.step==='channels'   && <ChannelSelect selectedTopology={s.selectedTopology}
          controllerMode={s.selectedControllerMode} intake={s.intakeData as any}
          onSubmit={handleChannels} onBack={()=>goBack('controller')} loading={s.loading} />}
        {s.step==='mini'       && s.miniDefaults && <MiniIntakeGate
          selectedTopology={s.selectedTopology} selectedMode={s.selectedMode}
          defaults={s.miniDefaults} validationErrors={s.miniErrors}
          pout_lo={intake?.application?.output_power_w_low_line as number||1700}
          vin_min={intake?.application?.vin_rms_min as number||90}
          vout={intake?.application?.output_bus_voltage_v as number||393}
          nPhases={s.isInterleaved?s.selectedChannels:1}
          appClass={appClass}
          onSubmit={handleMini} onBack={()=>goBack(s.isInterleaved?'channels':'controller')} loading={s.loading} />}
        {s.step==='done'       && s.summary && <DonePanel
          summary={s.summary} onRestart={restart} onGenerateReport={handleGenerateReport}
          reportLoading={s.reportLoading} reportReady={s.reportReady} reportBytes={s.reportBytes}
          onStartStep7={() => setS(p=>({...p, step:'step7'}))}
          docStatus={s.docStatus} docStatusLoading={s.docStatusLoading} />}
        {s.step==='step7'  && s.graphState && <Step7Wizard
          confirmedState={s.graphState as Record<string, unknown>}
          onBack={() => setS(p=>({...p, step:'done'}))}
          onRestart={restart}
          onApprove={handleStep7Approve} />}
        {s.step==='step15' && s.graphState && s.approvedInductorDesign && <Step15Wizard
          confirmedState={s.graphState as Record<string,unknown>}
          approvedDesign={s.approvedInductorDesign}
          onBack={() => setS(p=>({...p, step:'step7'}))}
          onRestart={restart}
          onApprove={handleStep15Approve} />}
        {s.step==='capsim' && s.graphState && s.approvedCapacitorDesign && <CapacitorSimAgent
          confirmedState={s.graphState as Record<string,unknown>}
          result={s.approvedCapacitorDesign}
          onBack={() => setS(p=>({...p, step:'step15'}))}
          onApprove={() => setS(p=>({...p, step:'step16'}))}
          onRestart={restart} />}
        {s.step==='step16' && s.graphState && s.approvedInductorDesign && <ControlDesign
          confirmedState={s.graphState as Record<string,unknown>}
          approvedInductorDesign={s.approvedInductorDesign}
          approvedCapacitorDesign={s.approvedCapacitorDesign}
          onBack={() => setS(p=>({...p, step:'capsim'}))}
          onRestart={restart}
          onSelectSemiconductors={() => setS(p=>({...p, step:'semiconductors'}))} />}
        {s.step==='semiconductors' && s.graphState && s.approvedInductorDesign && <SemiconductorSelection
          confirmedState={s.graphState as Record<string,unknown>}
          approvedInductorDesign={s.approvedInductorDesign}
          approvedCapacitorDesign={s.approvedCapacitorDesign}
          onBack={() => setS(p=>({...p, step:'step16'}))}
          onNext={() => setS(p=>({...p, step:'inputprotection'}))}
          onRestart={restart} />}
        {s.step==='inputprotection' && s.graphState && s.approvedInductorDesign && <InputProtection
          confirmedState={s.graphState as Record<string,unknown>}
          approvedInductorDesign={s.approvedInductorDesign}
          approvedCapacitorDesign={s.approvedCapacitorDesign}
          onBack={() => setS(p=>({...p, step:'semiconductors'}))}
          onNext={() => setS(p=>({...p, step:'inputfilter'}))}
          onRestart={restart} />}
        {s.step==='inputfilter' && s.graphState && s.approvedInductorDesign && <InputFilter
          confirmedState={s.graphState as Record<string,unknown>}
          approvedInductorDesign={s.approvedInductorDesign}
          approvedCapacitorDesign={s.approvedCapacitorDesign}
          onBack={() => setS(p=>({...p, step:'inputprotection'}))}
          onRestart={restart} />}

        {s.loading && (
          <div style={{position:'fixed',bottom:24,right:24,background:C.bg2,border:`1px solid ${C.border}`,borderRadius:10,
            padding:'10px 16px',display:'flex',alignItems:'center',gap:10,fontSize:13,color:C.muted}}>
            <Spinner /> Running backend…
          </div>
        )}
      </div>
    </div>
  )
}
