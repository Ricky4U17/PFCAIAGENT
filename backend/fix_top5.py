c = open('../frontend/src/components/Step7Wizard.tsx', encoding='utf-8').read()

# Fix n_top to 5
c = c.replace('n_top:3,', 'n_top:5,')

# Add allCandidates state
c = c.replace(
    '  const [result,   setResult]   = useState<any>(null)',
    '  const [result,   setResult]   = useState<any>(null)\n  const [allCandidates, setAllCandidates] = useState<any[]>([])'
)

# Store all candidates
c = c.replace(
    'setResult(top); setSub(',
    'setAllCandidates(candidates); setResult(top); setSub('
)

# Fix undefined fields
c = c.replace(
    "top.n_parallel = nPar; top.winding = winding",
    """top.n_parallel = nPar; top.winding = winding
      top.kbias = top.kbias ?? top.k_bias ?? top.kbias_dc ?? 0.8
      top.H_dc_Oe = top.H_dc_Oe ?? top.H_dc ?? 0
      top.dT_rise_C = top.dT_rise_C ?? top.dT ?? top.delta_T_C ?? 0
      top.Rth = top.Rth ?? top.R_th ?? top.Rth_C_per_W ?? 0
      top.Bsat_T = top.Bsat_T ?? top.Bsat ?? 0
      const AL = (top.AL_nom_total ?? top.AL_nom_nH ?? 75)
      const st = top.stacks ?? 1
      top.L_no_load_uH = Math.round((top.N ?? 0) ** 2 * AL * st * 1e-9 * 1e6)
      top.L_full_load_uH = Math.round(top.L_no_load_uH * top.kbias)
      top.L_variation_pct = Math.round((1 - top.kbias) * 100)"""
)

open('../frontend/src/components/Step7Wizard.tsx', 'w', encoding='utf-8').write(c)
print('Done')