import React from 'react'

export const C = {
  bg:'#0b0e14', bg2:'#111520', bg3:'#181d2d', bg4:'#1e2438',
  border:'#252b3d', border2:'#2e3650',
  text:'#e4e9f5', muted:'#7a86a3', hint:'#4a5270',
  accent:'#4f7cff', accent2:'#3561e0', accentL:'#0d1a3a',
  green:'#2dd4a0', greenL:'#0a2a20', greenD:'#166534',
  amber:'#f5a623', amberL:'#2a1e08',
  red:'#f05252', redL:'#2a0e0e',
  teal:'#22d3ee', tealL:'#062830',
} as const

export const inp: React.CSSProperties = {
  width:'100%', boxSizing:'border-box', padding:'9px 12px',
  background:C.bg, border:`1px solid ${C.border2}`, borderRadius:8,
  color:C.text, fontSize:14, fontFamily:'inherit', outline:'none',
}

export const Card:React.FC<{children:React.ReactNode;style?:React.CSSProperties}> = ({children,style}) => (
  <div style={{background:C.bg2,border:`1px solid ${C.border}`,borderRadius:12,padding:'20px 24px',marginBottom:14,...style}}>
    {children}
  </div>
)

export const SecHead:React.FC<{icon:string;label:string;sub?:string}> = ({icon,label,sub}) => (
  <div style={{display:'flex',alignItems:'center',gap:8,fontSize:12,fontWeight:600,
    textTransform:'uppercase',letterSpacing:'.06em',color:C.hint,
    marginBottom:16,paddingBottom:11,borderBottom:`1px solid ${C.border}`}}>
    <span style={{fontSize:15}}>{icon}</span>{label}
    {sub && <span style={{marginLeft:'auto',fontWeight:400,textTransform:'none',letterSpacing:0,
      fontFamily:'IBM Plex Mono, monospace',fontSize:11,color:C.hint}}>{sub}</span>}
  </div>
)

export const Field:React.FC<{label:string;children:React.ReactNode}> = ({label,children}) => (
  <div style={{marginBottom:14}}>
    <div style={{fontSize:11,fontWeight:600,letterSpacing:'.07em',textTransform:'uppercase',
      color:C.muted,marginBottom:6}}>{label}</div>
    {children}
  </div>
)

export const Inp:React.FC<{value:number|string;onChange:(v:number|string)=>void;type?:string;
  min?:number;max?:number;step?:number;disabled?:boolean}> = ({value,onChange,type='number',min,max,step,disabled}) => (
  <input style={{...inp,opacity:disabled?.5:1}} type={type} value={value} min={min} max={max}
    step={step} disabled={disabled}
    onChange={e=>onChange(type==='number'?Number(e.target.value):e.target.value)}/>
)

export const Sel:React.FC<{value:string|number;onChange:(v:string)=>void;options:(string|{value:string|number;label:string})[]}> =
  ({value,onChange,options}) => (
  <select style={{...inp,cursor:'pointer',appearance:'none',
    backgroundImage:`url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%234a5270' stroke-width='2'%3E%3Cpath d='M6 9l6 6 6-6'/%3E%3C/svg%3E")`,
    backgroundRepeat:'no-repeat',backgroundPosition:'right 12px center'} as React.CSSProperties}
    value={value} onChange={e=>onChange(e.target.value)}>
    {options.map(o=>{const v=typeof o==='string'?o:String(o.value);const l=typeof o==='string'?o:o.label;
      return <option key={v} value={v} style={{background:C.bg2}}>{l}</option>})}
  </select>
)

type BV='primary'|'ghost'|'success'
export const Btn:React.FC<{children:React.ReactNode;onClick?:()=>void;variant?:BV;disabled?:boolean;style?:React.CSSProperties}> =
  ({children,onClick,variant='primary',disabled,style}) => {
  const vs:Record<BV,React.CSSProperties>={
    primary:{background:C.accent,color:'#fff'},
    ghost:{background:'transparent',color:C.text,border:`1px solid ${C.border2}`},
    success:{background:C.greenD,color:C.green,border:`1px solid ${C.green}44`},
  }
  return <button onClick={onClick} disabled={disabled}
    style={{padding:'10px 22px',borderRadius:8,fontSize:14,fontWeight:600,border:'none',
      cursor:disabled?'not-allowed':'pointer',opacity:disabled?.4:1,transition:'opacity .15s',
      fontFamily:'inherit',...vs[variant],...style}}>{children}</button>
}

// Named colour → hex map (used by Badge and other components)
const NAMED: Record<string,string> = {
  blue:C.accent, green:C.green, amber:C.amber, red:C.red,
  gray:C.muted,  teal:C.teal,  hint:C.hint,
}
const resolveColor = (c?: string) => (c && NAMED[c]) ? NAMED[c] : (c || C.accent)

// Badge — supports both label prop (legacy) and children (new), named or hex colors
export const Badge:React.FC<{label?:string;color?:string;children?:React.ReactNode}> =
  ({label,color,children}) => {
  const c = resolveColor(color)
  return (
    <span style={{display:'inline-flex',alignItems:'center',padding:'2px 9px',borderRadius:20,
      fontSize:11,fontWeight:600,fontFamily:'IBM Plex Mono,monospace',
      background:c+'20',color:c,border:`1px solid ${c}44`}}>{children??label}</span>
  )
}

// ScoreBar — supports val/max (legacy) and value 0-1 normalised (new)
export const ScoreBar:React.FC<{val?:number;value?:number;max?:number;color?:string}> =
  ({val,value,max=6.6,color=C.accent}) => {
  const pct = value !== undefined
    ? Math.max(0, Math.min(100, value * 100))
    : Math.max(0, Math.min(100, ((val??0)/max)*100))
  return (
    <div style={{height:5,borderRadius:3,background:C.border,overflow:'hidden',marginTop:5}}>
      <div style={{height:'100%',width:`${pct}%`,
        background:color,borderRadius:3,transition:'width .4s'}}/>
    </div>
  )
}

export const Chip:React.FC<{label:string;on:boolean;onClick:()=>void}> = ({label,on,onClick}) => (
  <div onClick={onClick} style={{padding:'6px 14px',borderRadius:8,cursor:'pointer',fontSize:13,
    fontFamily:'IBM Plex Mono,monospace',fontWeight:on?600:400,userSelect:'none',transition:'all .15s',
    background:on?C.accentL:C.bg3,border:`1px solid ${on?C.accent:C.border}`,
    color:on?C.accent:C.muted}}>{label}</div>
)

export const ErrBanner:React.FC<{errors:string[]}> = ({errors}) => {
  if(!errors.length) return null
  return <div style={{background:C.redL,border:`1px solid ${C.red}55`,borderRadius:8,
    padding:'11px 14px',marginBottom:14,fontSize:13,color:'#fca5a5'}}>
    <strong>⚠ Validation error</strong>
    {errors.map((e,i)=><div key={i} style={{fontSize:12,fontFamily:'IBM Plex Mono,monospace',marginTop:4}}>→ {e}</div>)}
  </div>
}

export const Spinner:React.FC = () => (
  <span style={{display:'inline-block',width:15,height:15,border:`2px solid ${C.border2}`,
    borderTopColor:C.accent,borderRadius:'50%',animation:'spin .6s linear infinite'}}/>
)

export const ActionBar:React.FC<{
  label:string;value:string;valueColor?:string;sub?:string;
  onBack?:()=>void;backLabel?:string;
  onNext:()=>void;nextLabel:string;nextDisabled?:boolean;nextVariant?:BV
}> = ({label,value,valueColor=C.accent,sub,onBack,backLabel='← Back',onNext,nextLabel,nextDisabled,nextVariant='primary'}) => (
  <div style={{display:'flex',alignItems:'center',justifyContent:'space-between',
    padding:'16px 0 0',borderTop:`1px solid ${C.border}`,marginTop:6}}>
    <div>
      <div style={{fontSize:11,color:C.hint,fontFamily:'IBM Plex Mono,monospace'}}>{label}</div>
      <div style={{fontSize:14,fontWeight:600,color:valueColor}}>{value}</div>
      {sub && <div style={{fontSize:11,color:C.hint,fontFamily:'IBM Plex Mono,monospace',marginTop:2}}>{sub}</div>}
    </div>
    <div style={{display:'flex',gap:10}}>
      {onBack && <Btn variant="ghost" onClick={onBack}>{backLabel}</Btn>}
      <Btn variant={nextVariant} onClick={onNext} disabled={nextDisabled}>{nextLabel}</Btn>
    </div>
  </div>
)

export const TopBar:React.FC<{sub:string;status:'ok'|'error'|'checking'}> = ({sub,status}) => (
  <div style={{background:C.bg2,borderBottom:`1px solid ${C.border}`,display:'flex',
    alignItems:'center',justifyContent:'space-between',padding:'0 28px',height:56,
    position:'sticky',top:0,zIndex:50}}>
    <div style={{display:'flex',alignItems:'center',gap:10}}>
      <div style={{width:32,height:32,borderRadius:'50%',border:`1.5px solid ${C.accent}`,
        display:'flex',alignItems:'center',justifyContent:'center',fontSize:15}}>⚡</div>
      <div>
        <div style={{fontWeight:600,fontSize:15}}>PFC AI Agent</div>
        <div style={{fontSize:11,color:C.muted,fontFamily:'IBM Plex Mono,monospace'}}>{sub}</div>
      </div>
    </div>
    <div style={{display:'flex',alignItems:'center',gap:8,fontSize:12,color:C.muted,fontFamily:'IBM Plex Mono,monospace'}}>
      <div style={{width:7,height:7,borderRadius:'50%',
        background:status==='ok'?C.green:status==='error'?C.red:C.amber,
        boxShadow:status==='ok'?`0 0 6px ${C.green}`:'none'}}/>
      {status==='ok'?'backend connected':status==='error'?'backend offline':'connecting…'}
    </div>
  </div>
)
