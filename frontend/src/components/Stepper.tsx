import React from 'react'
import { C } from './ui'

/** Chip icon modelled on NVIDIA A-series package — square die, 3 pins per side, NVIDIA green #76b900 */
const ChipIcon: React.FC<{active:boolean;done:boolean}> = ({active,done}) => {
  const pin  = done ? C.green : active ? '#76b900' : '#4a5568'
  const body = done ? C.green : active ? '#76b900' : '#4a5568'
  const fill = done ? C.greenL : active ? 'rgba(118,185,0,.18)' : 'rgba(74,85,104,.12)'
  return (
    <svg viewBox="0 0 24 24" width="16" height="16" style={{display:'block'}}>
      {/* Chip body */}
      <rect x="4" y="4" width="16" height="16" rx="1.5"
        fill={fill} stroke={body} strokeWidth="1.5"/>
      {/* Left pins */}
      <rect x="1" y="6.5"  width="3" height="2" rx="0.5" fill={pin}/>
      <rect x="1" y="11"   width="3" height="2" rx="0.5" fill={pin}/>
      <rect x="1" y="15.5" width="3" height="2" rx="0.5" fill={pin}/>
      {/* Right pins */}
      <rect x="20" y="6.5"  width="3" height="2" rx="0.5" fill={pin}/>
      <rect x="20" y="11"   width="3" height="2" rx="0.5" fill={pin}/>
      <rect x="20" y="15.5" width="3" height="2" rx="0.5" fill={pin}/>
      {/* Top pins */}
      <rect x="6.5"  y="1" width="2" height="3" rx="0.5" fill={pin}/>
      <rect x="11"   y="1" width="2" height="3" rx="0.5" fill={pin}/>
      <rect x="15.5" y="1" width="2" height="3" rx="0.5" fill={pin}/>
      {/* Bottom pins */}
      <rect x="6.5"  y="20" width="2" height="3" rx="0.5" fill={pin}/>
      <rect x="11"   y="20" width="2" height="3" rx="0.5" fill={pin}/>
      <rect x="15.5" y="20" width="2" height="3" rx="0.5" fill={pin}/>
      {/* Die surface grid (3×3 dots representing GPU cores) */}
      {[7,11,15].map(cx => [7,11,15].map(cy => (
        <circle key={`${cx}-${cy}`} cx={cx+1} cy={cy+1} r="1"
          fill={done ? C.green : active ? '#76b900' : '#4a5568'} opacity="0.7"/>
      )))}
    </svg>
  )
}

export const STEPS = [
  {id:'intake',    icon:'📋',  label:'Intake'},
  {id:'topology',  icon:'🔀',  label:'Topology'},
  {id:'controller',icon:'🎛️', label:'Controller'},
  {id:'channels',  icon:'🔢',  label:'Channels'},
  {id:'mini',      icon:'⚡',  label:'Mini-intake'},
  {id:'done',      icon:'✅',  label:'Mode B'},
  {id:'step7',     icon:'🧲',  label:'Magnetic Material'},
  {id:'step15',    icon:'🔋',  label:'DC Bus Capacitor'},
  {id:'step16',    icon:'chip',label:'Control Design'},   // uses ChipIcon SVG
]

export const Stepper:React.FC<{current:string}> = ({current}) => {
  const idx = STEPS.findIndex(s=>s.id===current)
  return (
    <div style={{display:'flex',alignItems:'center',padding:'20px 28px 0',maxWidth:1560,margin:'0 auto',width:'100%'}}>
      {STEPS.map((s,i)=>{
        const done=i<idx, active=i===idx
        const isChip = s.icon === 'chip'
        return <React.Fragment key={s.id}>
          <div style={{display:'flex',flexDirection:'column',alignItems:'center',gap:4,minWidth:62}}>
            <div style={{width:30,height:30,borderRadius:'50%',display:'flex',alignItems:'center',
              justifyContent:'center',fontSize:12,transition:'all .3s',
              background:done?C.greenL:active?(isChip?'rgba(118,185,0,.12)':C.accentL):C.bg3,
              border:`1.5px solid ${done?C.green:active?(isChip?'#76b900':C.accent):C.border2}`,
              color:done?C.green:active?C.accent:C.hint}}>
              {done ? '✓' : isChip
                ? <ChipIcon active={active} done={false}/>
                : s.icon}
            </div>
            <div style={{fontSize:9,fontFamily:'IBM Plex Mono,monospace',textAlign:'center',
              whiteSpace:'nowrap',
              color:active?(isChip?'#76b900':C.accent):done?C.green:C.hint,
              fontWeight:active?700:400}}>{s.label}</div>
          </div>
          {i<STEPS.length-1&&<div style={{flex:1,height:1,margin:'0 2px',marginBottom:18,
            background:done?C.green:C.border,transition:'background .3s'}}/>}
        </React.Fragment>
      })}
    </div>
  )
}
