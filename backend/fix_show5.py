c = open('../frontend/src/components/Step7Wizard.tsx', encoding='utf-8').read()

# Replace the single result display with a candidate picker + detail
old = """          {/* Result header */}
          <div style={{background:result.passed?C.greenL:C.amberL,"""

new = """          {/* Top candidates list */}
          {allCandidates.length > 1 && (
            <div style={{marginBottom:14}}>
              <div style={{fontSize:11,color:C.hint,fontFamily:'IBM Plex Mono,monospace',
                textTransform:'uppercase',letterSpacing:'.06em',marginBottom:8}}>
                Top {allCandidates.length} candidates — click to select
              </div>
              {allCandidates.map((c:any, i:number) => {
                const r = c.result ?? {}
                const isSelected = result?.part_number === r.part_number && result?.stacks === r.stacks
                return (
                  <div key={i} onClick={() => {
                    const t = {...r}
                    t.kbias = t.kreq_nom ?? 0.8
                    t.H_dc_Oe = t.H_Oe_design ?? 0
                    t.dT_rise_C = t.dT_rise_C ?? 0
                    t.Rth = t.dT_rise_C / Math.max((t.Pcu_100C_W??0)+(t.Pcore_W??0), 0.001)
                    t.Bsat_T = t.Bsat_at_Tcore ?? 0
                    t.L_no_load_uH = Math.round(t.L0_nom_uH ?? 0)
                    t.L_full_load_uH = Math.round((t.L0_nom_uH??0)*(t.kreq_nom??0.8))
                    t.L_variation_pct = Math.round((1-(t.kreq_nom??0.8))*100)
                    t.n_parallel = result?.n_parallel ?? 1
                    t.winding = result?.winding ?? 'single'
                    setResult(t)
                  }} style={{
                    display:'flex',alignItems:'center',gap:10,padding:'9px 14px',
                    borderRadius:8,marginBottom:5,cursor:'pointer',
                    border:`1.5px solid ${isSelected?C.accent:r.passed?C.green+'44':C.border}`,
                    background:isSelected?C.accentL:C.bg2,
                  }}>
                    <span style={{fontSize:11,color:C.hint,minWidth:20}}>#{i+1}</span>
                    <span style={{fontFamily:'IBM Plex Mono,monospace',fontWeight:500,fontSize:13,
                      color:isSelected?C.accent:C.text}}>
                      {r.part_number}
                      {r.stacks>1&&<span style={{fontSize:11,color:C.teal,marginLeft:6}}>×{r.stacks} stack</span>}
                    </span>
                    <span style={{fontSize:11,fontFamily:'IBM Plex Mono,monospace',color:C.muted}}>
                      N={r.N} · L={Math.round(r.L0_nom_uH??0)}µH · FFcu={(r.FFcu*100).toFixed(0)}% · ΔT={r.dT_rise_C?.toFixed(0)}°C
                    </span>
                    <span style={{marginLeft:'auto',fontSize:10,
                      color:r.passed?C.green:C.amber}}>{r.passed?'✓ pass':'⚠'}</span>
                  </div>
                )
              })}
            </div>
          )}

          {/* Result header */}
          <div style={{background:result.passed?C.greenL:C.amberL,"""

c = c.replace(old, new)
open('../frontend/src/components/Step7Wizard.tsx', 'w', encoding='utf-8').write(c)
print('Done' if 'Top candidates list' in c else 'FAILED')