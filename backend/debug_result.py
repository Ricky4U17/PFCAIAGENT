import sys, numpy as np
sys.path.insert(0, '.')
from app.magnetics.db import MagneticsDB
from app.mode_b.step7_magnetic_calc import design_one_core

db = MagneticsDB()
cores = db.filter_cores(
    'magnetics_inc', max_height_mm=44.45,
    max_stacks=3, material_line='EDGE', mu=60
)

# Use reference design params
OPS = np.array([
    [90,  1700, 0.945, 0.9987, 10.07, 28.30, 0.676],
    [180, 3600, 0.945, 0.9987, 10.07, 29.97, 0.352],
])

wire = {'designation':'0.1x150','Cu_area_mm2':1.178,
        'R_per_m_20C':0.01462,'n_strands':150,'strand_dia_mm':0.1}

core = cores[1]  # 2-stack
print(f"Testing: {core['part_number']} stacks={core['stacks']} AL_nom_total={core.get('AL_nom_total')}")

r = design_one_core(
    core=core, material_key='edge_60',
    L_target_H=240e-6, Ipk_A=16.73,
    Irms_A=10.07, IL_HF_rms_A=1.15,
    dIL_pp_A=5.161, fsw_Hz=70000,
    wire=wire, N_phases=2,
    OPS=OPS, T_amb_C=50, dT_budget_C=60
)
print(f"N={r.N} L0_nom_uH={r.L0_nom_uH} L0_min_uH={r.L0_min_uH}")
print(f"FFcu={r.FFcu} dT={r.dT_rise_C} passed={r.passed}")
print(f"fail_reasons={r.fail_reasons}")