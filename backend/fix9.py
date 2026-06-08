c = open('../frontend/src/components/DonePanel.tsx', encoding='utf-8').read()

guidance = """      <Card style={{marginBottom:16,background:'rgba(55,138,221,0.06)',border:'0.5px solid rgba(55,138,221,0.3)'}}>
        <div style={{fontSize:13,color:'#378ADD',fontWeight:500,marginBottom:8}}>
          ⓘ Designer Guidance — Next Steps
        </div>
        <div style={{fontSize:12,lineHeight:1.8,color:'#a0aec0'}}>
          <strong style={{color:'#e2e8f0'}}>1. Review the calculation report</strong> — Download and examine the Mode B PDF report. 
          It contains the full CCM analysis, worst-case duty cycle, inductor sizing, waveform reconstruction, 
          and all operating point calculations across the 9-point Vin/Pout matrix.<br/>
          <strong style={{color:'#e2e8f0'}}>2. Validate against your specifications</strong> — Confirm that the selected topology, 
          phase count, switching frequency, and inductor value align with your thermal budget, 
          footprint constraints, and compliance requirements.<br/>
          <strong style={{color:'#e2e8f0'}}>3. Iterate if needed</strong> — If any parameter requires adjustment, use the Back button 
          to return to Mode A and modify your inputs. All downstream calculations will update automatically.<br/>
          <strong style={{color:'#e2e8f0'}}>4. Proceed to magnetic design</strong> — Once the report is approved, launch Step 7 to 
          run the full HITL magnetic design workflow: material selection, grade ranking, core sizing 
          across the complete catalog, and time-domain core loss analysis (Step 14).
        </div>
      </Card>
"""

# Insert before the MB_STEPS section
marker = '<Card style={{marginBottom:12}}'
idx = c.find(marker)
c = c[:idx] + guidance + c[idx:]

open('../frontend/src/components/DonePanel.tsx', 'w', encoding='utf-8').write(c)
print('Done')