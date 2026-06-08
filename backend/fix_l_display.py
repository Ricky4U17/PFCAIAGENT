c = open('../frontend/src/components/Step7Wizard.tsx', encoding='utf-8').read()

old = """      const AL = 75
      const st = top.stacks ?? 1
      top.L_no_load_uH = Math.round((top.L0_nom_uH ?? 0))
      top.L_full_load_uH = Math.round(top.L0_nom_uH * (top.kreq_nom ?? 0.8))
      top.L_variation_pct = Math.round((1 - (top.kreq_nom ?? 0.8)) * 100)"""

new = """      top.L_no_load_uH = Math.round(top.L0_nom_uH ?? 0)
      top.L_full_load_uH = Math.round((top.L0_nom_uH ?? 0) * (top.kreq_nom ?? 0.8))
      top.L_variation_pct = Math.round((1 - (top.kreq_nom ?? 0.8)) * 100)"""

c = c.replace(old, new)
open('../frontend/src/components/Step7Wizard.tsx', 'w', encoding='utf-8').write(c)
print('Done' if 'top.L_no_load_uH = Math.round(top.L0_nom_uH' in c else 'FAILED')