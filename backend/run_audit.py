"""Generate full Steps 1–15 report and audit every page for blank/thin content."""
import sys, io, json, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, '.')
import requests
from pypdf import PdfReader

BASE = 'http://localhost:8000'

# ── Mode A flow ──────────────────────────────────────────────────────────────
INTAKE = {
    'application': {
        'vin_rms_min':90,'vin_rms_max':264,'nominal_line_frequency_hz':60,
        'universal_input_frequency':False,'output_bus_voltage_v':393,
        'output_power_w_high_line':3600,'output_power_w_low_line':1700,
        'power_factor_target':0.999,'efficiency_target_percent':97,
        'hold_up_time_ms':20,'dc_bus_voltage_ripple_pk_pk_v':20,
    },
    'thermal':    {'cooling_type':'fan_cooled','ambient_temp_c_max':50,'max_temp_rise_c':60,'hotspot_limit_c':110},
    'control':    {'control_preference':'Recommend'},
    'business':   {'cost_priority':7,'efficiency_priority':9,'power_density_priority':8,
                   'implementation_risk_priority':6,'preferred_switch_technology':['Si','SiC']},
    'mechanical': {'power_density_priority':8},
    'compliance': {'application_class':'Industrial','conducted_emi_class':'FCC Class B',
                   'harmonics_class':'EN61000-3-2','leakage_current_limit_ua':3500},
    'supply':     {'preferred_vendors':[],'avoid_vendors':[]},
}

r = requests.post(f'{BASE}/mode-a/start', json={'project_id':'audit','intake':INTAKE})
d = r.json(); state = d['state']
topo = d['recommended_topology']; mode = d['recommended_mode']

r = requests.post(f'{BASE}/mode-a/approve-topology',
    json={'state':state,'feedback':{'selected_topology':topo,'selected_mode':mode}})
state = r.json()['state']
ctrl  = r.json()['controller_strategy']['recommended_controller_mode']

r = requests.post(f'{BASE}/mode-a/approve-controller',
    json={'state':state,'feedback':{'controller_mode':ctrl}})
state = r.json()['state']

r = requests.post(f'{BASE}/mode-a/approve-channels',
    json={'state':state,'feedback':{'n_channels':2}})
state = r.json()['state']

r = requests.post(f'{BASE}/mode-a/submit-mini-intake',
    json={'state':state,'feedback':{'switching_frequency_hz':70000,'crest_ripple_ratio':0.20}})
state = r.json()['state']
print(f'State built: {topo}')

# ── Step 15 result ────────────────────────────────────────────────────────────
from app.mode_b.step15_cap_db import _load, calculate_lifetime

d15  = requests.post(f'{BASE}/mode-b/step15/capacitor-design', json={'state':state}).json()
db   = _load()
cap  = next((r for r in db if r['capacitance_uF']==470.0 and r['voltage_V']==450), None)
qty  = 5
lt   = calculate_lifetime(
    cap, qty,
    d15['worst_case']['I_LF_A'],
    d15['worst_case']['I_HF_A'],
    45.0, d15['inputs']['Vout_V']
)

step15 = {
    **d15,
    'lifetime': lt,
    'verified': {
        'C_total_uF':       qty * cap['capacitance_uF'],
        'total_cap_count':  qty,
        'valid':            True,
        'margin_pct':       11.0,
        'ESR_parallel_mohm': round(cap['esr_ohm']*1000/qty, 1),
        'I_rated_per_cap_A': cap['ripple_120hz_A'],
        'ripple_current_pass': True,
        'cap_specs': [{
            'value_uF':       cap['capacitance_uF'],
            'qty':            qty,
            'voltage_rating_V': cap['voltage_V'],
            'ESR_each_mohm':  round(cap['esr_ohm']*1000, 1),
            'I_rated_A':      cap['ripple_120hz_A'],
            'temp_rating_C':  cap['op_temp_max_C'],
            'part_number':    cap['part_number'],
            'lifetime':       cap['lifetime_raw'],
            'op_temp':        cap['op_temp_raw'],
        }],
        'supplier':         cap['manufacturer'],
        'series':           cap['series'],
        'voltage_rating':   cap['voltage_V'],
        'temp_rating_C':    cap['op_temp_max_C'],
        'worst_case': {
            'V_ripple_pp_V': 10.8, 't_holdup_ms': 22.2,
            'I_rms_per_cap_A': 2.59, 'I_rms_total_A': 12.97,
            'I_rated_per_cap_A': cap['ripple_120hz_A'],
            'ripple_current_pass': True, 'V_esr_pk_V': 0.52,
        },
        'low_line': {
            'V_ripple_pp_V': 5.2, 't_holdup_ms': 47.0,
            'I_rms_per_cap_A': 1.25, 'I_rms_total_A': 6.25,
            'I_rated_per_cap_A': cap['ripple_120hz_A'],
            'ripple_current_pass': True, 'V_esr_pk_V': 0.25,
        },
    },
    'thermal': None,
}
print(f'Step15 built: cap={cap["part_number"]} x{qty}, life={lt["min_life_years"]}yr')

# ── Inductor result ───────────────────────────────────────────────────────────
approved = {
    'part_number':'0059937A2','stacks':3,'material_key':'edge_75','N':44,
    'Ae_total_mm2':196.2,'Wa_total_mm2':156.0,'Ve_total_cm3':12.45,
    'Le_single_mm':63.5,'h_effective_mm':42.1,'OD_mm':27.69,'ID_mm':14.1,'HT_mm':11.94,
    'Ae_single_mm2':65.4,'Wa_single_mm2':156.0,'AL_nom_nH':75.0,'AL_tol_pct':8.0,
    'supplier':'Magnetics','L0_nom_uH':240.0,'L0_min_uH':220.0,'L0_max_uH':260.0,
    'kreq_nom':0.85,'H_Oe_design':48.5,'dBpp_T':0.054,'Bac_pk_T':0.027,
    'Bdc_T':0.21,'Bmin_FL_T':0.183,'Bmax_FL_T':0.237,'Bsat_at_Tcore':1.05,'sat_margin_pct':77.6,
    'wire_designation':'0.1x200','n_strands':200,'d_strand_mm':0.1,'wire_OD_mm':2.0,
    'Cu_area_mm2':3.14,'R_per_m_20C':0.0055,'FFcu':0.35,'Ku':0.35,
    'wound_HT_actual_mm':42.1,'wound_OD_actual_mm':29.4,'mounting':'horizontal','installed_height_mm':42.1,
    'MLT_mm':65.0,'Cu_length_m':2.86,'DCR_25C_mOhm':17.5,'DCR_100C_mOhm':22.1,
    'Rac_Rdc':1.0,'Pcu_25C_W':1.78,'Pcu_100C_W':2.24,'P_fringing_W':0.0,
    'Pcore_W':2.12,'Ptotal_25C_W':3.9,'Ptotal_100C_W':4.36,
    'loss_table_25C':[],'loss_table_100C':[],'L_vs_Vin_table':[],'T_amb_C':50.0,
    'T_core_C':95.0,'dT_rise_C':45.0,'dT_budget_C':60.0,'creepage_ok':True,'creepage_mm':0.0,
    'passed':True,'fail_reasons':[],'score':0.48,'core_name':'EDGE','core_type':'powder',
    'lg_mm':0.0,'AT_design':616.0,'all_candidates':[],
}

# ── Generate ──────────────────────────────────────────────────────────────────
from app.mode_b.generate_report import generate_full_report
from app.mode_b.generate_combined_report import generate_combined_report

t0 = time.time()
pdf_1_12 = generate_full_report(state)
pdf_full  = generate_combined_report(state, approved, pdf_1_12, step15)
elapsed   = time.time() - t0
print(f'PDF: {len(pdf_full):,} bytes in {elapsed:.1f}s')

# ── Audit every page ──────────────────────────────────────────────────────────
reader = PdfReader(io.BytesIO(pdf_full))
total  = len(reader.pages)
print(f'Total pages: {total}')

blank = []
for i, pg in enumerate(reader.pages, 1):
    wc = len((pg.extract_text() or '').split())
    if wc == 0:
        blank.append(i)

print(f'Blank pages: {blank}')
print()
print('All pages:')
for i, pg in enumerate(reader.pages, 1):
    txt = (pg.extract_text() or '').strip().replace('\n',' ')
    wc  = len(txt.split())
    flag = '  <-- BLANK' if wc==0 else ''
    print(f'  p{i:2}: {wc:4}w  {txt[:65]}{flag}')

with open('C:/tmp/fresh_report.pdf', 'wb') as f:
    f.write(pdf_full)
print('\nSaved: C:/tmp/fresh_report.pdf')
