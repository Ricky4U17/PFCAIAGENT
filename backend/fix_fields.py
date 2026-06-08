c = open('../frontend/src/components/Step7Wizard.tsx', encoding='utf-8').read()

old = """      top.kbias = top.kbias ?? top.k_bias ?? top.kbias_dc ?? 0.8
      top.H_dc_Oe = top.H_dc_Oe ?? top.H_dc ?? 0
      top.dT_rise_C = top.dT_rise_C ?? top.dT ?? top.delta_T_C ?? 0
      top.Rth = top.Rth ?? top.R_th ?? top.Rth_C_per_W ?? 0
      top.Bsat_T = top.Bsat_T ?? top.Bsat ?? 0
      const AL = (top.AL_nom_total ?? top.AL_nom_nH ?? 75)
      const st = top.stacks ?? 1
      top.L_no_load_uH = Math.round((top.N ?? 0) ** 2 * AL * st * 1e-9 * 1e6)
      top.L_full_load_uH = Math.round(top.L_no_load_uH * top.kbias)
      top.L_variation_pct = Math.round((1 - top.kbias) * 100)"""

new = """      top.kbias = top.kreq_nom ?? 0.8
      top.H_dc_Oe = top.H_Oe_design ?? 0
      top.Bsat_T = top.Bsat_at_Tcore ?? 0
      top.Rth = top.dT_budget_C > 0 ? (top.dT_rise_C / Math.max(top.Pcu_100C_W + top.Pcore_W, 0.001)) : 0
      top.Pcu_100C_W = top.Pcu_100C_W ?? 0
      top.FFcu = top.FFcu ?? 0
      top.Bmax_FL_T = top.Bmax_FL_T ?? 0
      const AL = 75
      const st = top.stacks ?? 1
      top.L_no_load_uH = Math.round((top.L0_nom_uH ?? 0))
      top.L_full_load_uH = Math.round(top.L0_nom_uH * (top.kreq_nom ?? 0.8))
      top.L_variation_pct = Math.round((1 - (top.kreq_nom ?? 0.8)) * 100)"""

c = c.replace(old, new)

# Fix result card field references
c = c.replace("result.Pcu_100C_W?.toFixed(3)", "result.Pcu_100C_W?.toFixed(2)")
c = c.replace("result.dT_rise_C?.toFixed(1)", "result.dT_rise_C?.toFixed(1)")
c = c.replace("result.kbias?.toFixed(3)", "result.kreq_nom?.toFixed(3)")
c = c.replace("result.H_dc_Oe?.toFixed(1)+'Oe'", "result.H_Oe_design?.toFixed(1)+'Oe'")
c = c.replace("result.FFcu?(result.FFcu*100).toFixed(1)+'%':'—'", "(result.FFcu*100).toFixed(1)+'%'")
c = c.replace("result.Bmax_FL_T?.toFixed(4)", "result.Bmax_FL_T?.toFixed(4)")
c = c.replace("result.Bsat_T?(((result.Bsat_T-result.Bmax_FL_T)/result.Bsat_T*100).toFixed(0)+'%'):'—'",
              "result.sat_margin_pct?.toFixed(0)+'%'")
c = c.replace("result.Pcore_W?.toFixed(3)", "result.Pcore_W?.toFixed(3)")
c = c.replace("((result.Pcu_100C_W??0)+(result.Pcore_W??0)).toFixed(3)",
              "result.Ptotal_100C_W?.toFixed(3)")
c = c.replace("(((result.Pcu_100C_W??0)+(result.Pcore_W??0))/3600*100).toFixed(3)",
              "(result.Ptotal_100C_W/3600*100).toFixed(3)")
c = c.replace("result.dT_rise_C<60?'✓ within budget':'⚠ exceeds 60°C budget'",
              "result.dT_rise_C<result.dT_budget_C?'✓ within budget':'⚠ exceeds budget'")
c = c.replace("result.dT_rise_C<60", "result.dT_rise_C<result.dT_budget_C")

open('../frontend/src/components/Step7Wizard.tsx', 'w', encoding='utf-8').write(c)
print('Done')