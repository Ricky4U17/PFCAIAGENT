c = open('../frontend/src/components/DonePanel.tsx', encoding='utf-8').read()

# First remove the broken guidance that was inserted in the wrong place
bad = """      <Card style={{marginBottom:16,background:'rgba(55,138,221,0.06)',border:'0.5px solid rgba(55,138,221,0.3)'}}>
        <div style={{fontSize:13,color:'#378ADD',fontWeight:500,marginBottom:8}}>
          \u24d8 Designer Guidance \u2014 Next Steps
        </div>
        <div style={{fontSize:12,lineHeight:1.8,color:'#a0aec0'}}>
          <strong style={{color:'#e2e8f0'}}>1. Review the calculation report</strong> \u2014 Download and examine the Mode B PDF report. 
          It contains the full CCM analysis, worst-case duty cycle, inductor sizing, waveform reconstruction, 
          and all operating point calculations across the 9-point Vin/Pout matrix.<br/>
          <strong style={{color:'#e2e8f0'}}>2. Validate against your specifications</strong> \u2014 Confirm that the selected topology, 
          phase count, switching frequency, and inductor value align with your thermal budget, 
          footprint constraints, and compliance requirements.<br/>
          <strong style={{color:'#e2e8f0'}}>3. Iterate if needed</strong> \u2014 If any parameter requires adjustment, use the Back button 
          to return to Mode A and modify your inputs. All downstream calculations will update automatically.<br/>
          <strong style={{color:'#e2e8f0'}}>4. Proceed to magnetic design</strong> \u2014 Once the report is approved, launch Step 7 to 
          run the full HITL magnetic design workflow: material selection, grade ranking, core sizing 
          across the complete catalog, and time-domain core loss analysis (Step 14).
        </div>
      </Card>
"""
c = c.replace(bad, '')

# Now insert in the right place - after the header div
marker = 'All five HITL gates passed. Parameters confirmed and'
idx = c.find(marker)
end_of_header = c.find('</div>', c.find('</div>', idx) + 1) + len('</div>')

guidance = """
      <div style={{background:'rgba(55,138,221,0.06)',border:'0.5px solid rgba(55,138,221,0.3)',borderRadius:10,padding:'14px 18px',marginTop:16,marginBottom:4}}>
        <div style={{fontSize:13,color:'#378ADD',fontWeight:500,marginBottom:8}}>Designer Guidance — Next Steps</div>
        <div style={{fontSize:12,lineHeight:1.9,color:'#a0aec0'}}>
          <b style={{color:'#e2e8f0'}}>1. Review the report</b> — Download the Mode B PDF and verify the CCM analysis, worst-case duty cycle, inductor sizing, and 9-point operating matrix against your specifications.<br/>
          <b style={{color:'#e2e8f0'}}>2. Validate constraints</b> — Confirm topology, phase count, switching frequency, and inductance align with your thermal budget, footprint, and compliance requirements.<br/>
          <b style={{color:'#e2e8f0'}}>3. Iterate if required</b> — Use Back to return to Mode A and adjust any parameter. All calculations update automatically.<br/>
          <b style={{color:'#e2e8f0'}}>4. Proceed to Step 7</b> — Once satisfied, launch the full HITL magnetic design: material selection, agent-ranked grade comparison, catalog-wide core sizing, and time-domain core loss analysis.
        </div>
      </div>"""

c = c[:end_of_header] + guidance + c[end_of_header:]
open('../frontend/src/components/DonePanel.tsx', 'w', encoding='utf-8').write(c)
print('Done')